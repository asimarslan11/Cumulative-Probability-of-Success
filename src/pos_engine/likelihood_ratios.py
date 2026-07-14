"""
likelihood_ratios.py

The statistical core of the engine. A baseline probability answers "what happens on
average at this phase"; a **likelihood ratio (LR)** answers "how much does *this*
piece of evidence move that number", derived from a published two-arm contrast:

    LR(evidence, phase) = odds(present arm) / odds(reference arm)

computed per phase transition (see docs/likelihood_ratios.md for the derivation).

Two public operations:

    lr(evidence_type, phase, value=None)
        Derive one LR from baseline_rates.json (or, for Fig-14 signals, from the
        illustrative deltas in config). Returns a provenance-carrying dict, or
        None when the contrast is not published at that phase or an arm is too
        small to trust (n < MIN_ARM_N).

    combine(baseline_prob, evidence_items)
        Fold a set of derived LRs onto a baseline, in odds space, with shrinkage
        so correlated evidence is not double-counted. Returns the adjusted
        probability plus a per-LR audit trail (weight, group, confidence).

Day 2 only *derives and combines*. Choosing which LRs apply to a given asset,
avoiding double-counting the baseline tier, and compounding across phases are Day 3.
"""

from pos_engine import PHASE_KEYS, load_data
from pos_engine.config import (
    CORRELATION_GROUPS,
    ILLUSTRATIVE_BASELINE,
    ILLUSTRATIVE_LRS,
    LEAD_INDICATION_PROXY,
    LR_REFERENCE,
    MIN_ARM_N,
    MIN_PROB,
    MAX_PROB,
    SHRINKAGE_K,
)
from pos_engine.odds import clip_prob, odds_to_prob, prob_to_odds

# Evidence types whose two arms live in baseline_rates.json and are contrasted the
# same way (odds ratio of two rows). Lead-indication shares the shape but has a
# phase restriction, so it is merged in with its own entry below.
_ROW_REFERENCE = dict(LR_REFERENCE)
_ROW_REFERENCE["lead_indication"] = LEAD_INDICATION_PROXY


def resolve_correlation_group(evidence_type, value=None):
    """Return the name of the correlation group ``(evidence_type, value)`` belongs
    to, or a unique singleton name when the evidence is independent.

    Members are matched on evidence type and, where the group restricts them, on
    value (``None`` in the config means "any value of this type").
    """
    for group_name, members in CORRELATION_GROUPS.items():
        if evidence_type not in members:
            continue
        allowed = members[evidence_type]
        if allowed is None or value in allowed:
            return group_name
    # Independent: its own group so it never shares (and thus never dampens) with
    # another item. Weight will be 1.
    return "independent:" + evidence_type + (f":{value}" if value is not None else "")


class LikelihoodRatios:
    """Derives likelihood ratios from the canonical baseline table and combines
    them onto a baseline with shrinkage.

    Loads ``baseline_rates.json`` once and indexes its rows by
    ``(category_type, category, phase_transition)`` -- the same pattern as
    ``BaselineLookup`` -- for O(1) arm lookups.
    """

    def __init__(self, table_file="baseline_rates.json"):
        table = load_data(table_file)
        self._index = {}
        for row in table["rows"]:
            key = (row["category_type"], row["category"], row["phase_transition"])
            self._index[key] = row

    # -- deriving one LR ----------------------------------------------------

    def lr(self, evidence_type, phase, value=None):
        """Derive the likelihood ratio for one piece of evidence at one phase.

        Returns a dict::

            {lr, evidence_type, value, phase, source, source_ref, confidence, arms}

        or ``None`` when the contrast is not usable: the evidence type is unknown,
        the phase is not published for that contrast, a required arm row is
        missing, or an arm's sample size is below ``MIN_ARM_N``.

        ``value`` names the specific category for evidence types that vary
        (modality, novelty, oncology_subtype); it is ignored for fixed contrasts
        (biomarker, rare_disease, lead_indication, and the Fig-14 signals).
        """
        if phase not in PHASE_KEYS:
            raise ValueError(f"Unknown phase {phase!r}. Must be one of {PHASE_KEYS}")

        if evidence_type in ILLUSTRATIVE_LRS:
            return self._illustrative_lr(evidence_type, phase)
        if evidence_type in _ROW_REFERENCE:
            return self._row_lr(evidence_type, phase, value)
        # Unknown evidence type: no contrast to compute.
        return None

    def _row_lr(self, evidence_type, phase, value):
        spec = _ROW_REFERENCE[evidence_type]

        # Phase-restricted contrasts (lead-indication) skip phases they don't map to.
        allowed_phases = spec.get("phases")
        if allowed_phases is not None and phase not in allowed_phases:
            return None

        present = self._arm(spec["present"], phase, value)
        reference = self._arm(spec["reference"], phase, value)
        if present is None or reference is None:
            return None
        # Small-arm guard: an odds ratio is only as trustworthy as its noisiest arm.
        if present["n"] < MIN_ARM_N or reference["n"] < MIN_ARM_N:
            return None

        lr_value = present["odds"] / reference["odds"]
        return {
            "lr": lr_value,
            "evidence_type": evidence_type,
            "value": value,
            "phase": phase,
            "source": present["source"],
            "source_ref": spec["source_ref"],
            "confidence": spec.get("confidence", "high"),
            "arms": {"present": present, "reference": reference},
        }

    def _arm(self, arm_spec, phase, value):
        """Resolve one arm of a contrast to a row + its odds, or None if missing.

        ``arm_spec`` is ``(category_type, category)``; a ``None`` category is
        filled from the caller-supplied ``value`` (e.g. the modality name).
        """
        category_type, category = arm_spec
        if category is None:
            if value is None:
                raise ValueError(
                    f"Evidence type needs a `value` to select the {category_type!r} arm"
                )
            category = value
        row = self._index.get((category_type, category, phase))
        if row is None:
            return None
        return {
            "category_type": category_type,
            "category": category,
            "phase": phase,
            "n": row["n"],
            "rate": row["rate"],
            "odds": prob_to_odds(row["rate"]),
            "source": row["source"],
        }

    def _illustrative_lr(self, evidence_type, phase):
        """Fig-14 illustrative LR: odds(0.35 + delta) / odds(0.35).

        Phase-independent (a single worked example, not a population contrast) and
        always flagged confidence="low".
        """
        spec = ILLUSTRATIVE_LRS[evidence_type]
        delta = spec["delta"]
        present_rate = ILLUSTRATIVE_BASELINE + delta
        present_odds = prob_to_odds(present_rate)
        reference_odds = prob_to_odds(ILLUSTRATIVE_BASELINE)
        return {
            "lr": present_odds / reference_odds,
            "evidence_type": evidence_type,
            "value": None,
            "phase": phase,
            "source": "BIO/QLS 2021",
            "source_ref": spec["source_ref"],
            "confidence": "low",
            "arms": {
                "present": {"rate": present_rate, "odds": present_odds},
                "reference": {"rate": ILLUSTRATIVE_BASELINE, "odds": reference_odds},
            },
        }

    # -- combining LRs onto a baseline -------------------------------------

    def combine(self, baseline_prob, evidence_items, k=None):
        """Fold a set of derived LRs onto ``baseline_prob`` in odds space, with
        shrinkage for correlated evidence.

        ``evidence_items`` is a list of dicts as returned by :meth:`lr` (``None``
        entries are ignored, so the output of a batch of ``lr(...)`` calls can be
        passed straight through). Each must carry at least ``lr`` and
        ``evidence_type`` (and ``value`` where the correlation group depends on it).

        For each item, its correlation group of size ``m`` gives an exponent
        ``w = 1 / (1 + k*(m-1))`` (``k`` defaults to ``SHRINKAGE_K``); then::

            adjusted_odds = baseline_odds * PROD_i  LR_i ** w_i

        The result is converted back to a probability and clipped to
        ``[MIN_PROB, MAX_PROB]``, so it is always strictly inside (0, 1).

        Returns a dict with the adjusted probability and a per-LR audit trail
        (each LR, its weight, group, and confidence) for the Day-3 waterfall.
        """
        if k is None:
            k = SHRINKAGE_K
        items = [it for it in evidence_items if it is not None]

        # Group membership counts drive the shrinkage weights.
        groups = [resolve_correlation_group(it["evidence_type"], it.get("value")) for it in items]
        group_sizes = {}
        for g in groups:
            group_sizes[g] = group_sizes.get(g, 0) + 1

        baseline_odds = prob_to_odds(baseline_prob)
        adjusted_odds = baseline_odds
        audit = []
        for it, group in zip(items, groups):
            m = group_sizes[group]
            weight = 1.0 / (1.0 + k * (m - 1))
            lr_value = it["lr"]
            adjusted_odds *= lr_value ** weight
            audit.append({
                "evidence_type": it["evidence_type"],
                "value": it.get("value"),
                "lr": lr_value,
                "weight": weight,
                "group": group,
                "group_size": m,
                "confidence": it.get("confidence"),
                "source_ref": it.get("source_ref"),
            })

        adjusted_prob = clip_prob(odds_to_prob(adjusted_odds))
        return {
            "baseline_prob": baseline_prob,
            "adjusted_prob": adjusted_prob,
            "baseline_odds": baseline_odds,
            "adjusted_odds": adjusted_odds,
            "k": k,
            "audit": audit,
        }


if __name__ == "__main__":
    # Quick manual check when running this file directly.
    lr_engine = LikelihoodRatios()

    print("biomarker, Phase II->III:")
    print(lr_engine.lr("biomarker", "phase2_to_3"))

    print("\nCAR-T modality, Phase I->II (below-average early -> LR < 1):")
    print(lr_engine.lr("modality", "phase1_to_2", "CAR-T"))

    print("\nCAR-T filing->approval (n=4 -> skipped):")
    print(lr_engine.lr("modality", "filing_to_approval", "CAR-T"))

    print("\ncombine(0.25, [biomarker P2->3, CAR-T P2->3]) -- precision-medicine pair:")
    bm = lr_engine.lr("biomarker", "phase2_to_3")
    cart = lr_engine.lr("modality", "phase2_to_3", "CAR-T")
    print(lr_engine.combine(0.25, [bm, cart]))
