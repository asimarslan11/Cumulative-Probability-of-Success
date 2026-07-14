"""
engine.py

The Day-3 orchestration layer: from an ``Asset`` to a **cumulative probability of
success**, with a per-phase audit trail. Days 1-2 built the ingredients
(``BaselineLookup``, ``LikelihoodRatios``, the odds primitives); this module is the
recipe that turns them into an end-to-end pipeline.

For each transition still ahead of the asset it:

    1. select_baseline        -- pick the most specific reliable baseline (Day-1 fallback)
    2. route the evidence      -- which of the asset's signals apply *at this transition*,
                                  honouring temporality and not double-counting the
                                  baseline tier (see docs/pipeline.md)
    3. adjust_phase_probability-- derive each applicable LR and fold it on (Day-2 combine)
    4. compound_pos            -- multiply the adjusted per-phase probabilities into the
                                  cumulative PoS

Every step emits provenance, so the returned result is a full waterfall you can read
back to the source figure behind each number.

Day 5 wraps this core in the public ``calculate_pos(asset)`` API and a CLI/notebook demo.
"""

from enum import Enum

from pos_engine.asset import Asset
from pos_engine.baseline_lookup import BaselineLookup
from pos_engine.config import (
    EVIDENCE_ROUTING,
    REGULATORY_PHASES,
    EngineConfig,
)
from pos_engine.likelihood_ratios import LikelihoodRatios


def _asset_value(asset, field):
    """Read ``field`` off the asset, unwrapping enums to their string value."""
    value = getattr(asset, field)
    if isinstance(value, Enum):
        return value.value
    return value


def _trigger_fires(asset, trigger):
    """Evaluate an EVIDENCE_ROUTING trigger against an asset."""
    kind = trigger[0]
    if kind == "flag":
        return getattr(asset, trigger[1]) is True
    if kind == "present":
        return getattr(asset, trigger[1]) is not None
    if kind == "equals":
        return _asset_value(asset, trigger[1]) == trigger[2]
    raise ValueError(f"Unknown trigger kind {kind!r}")


def _temporality_includes(temporality, phase, remaining):
    """Does a signal with this temporality apply at ``phase``?

    ``remaining`` is the ordered list of transitions still ahead of the asset, so
    ``remaining[0]`` is the immediate next step.
    """
    if temporality == "persistent":
        return True
    if temporality == "next_only":
        return bool(remaining) and phase == remaining[0]
    if temporality == "regulatory":
        return phase in REGULATORY_PHASES
    raise ValueError(f"Unknown temporality {temporality!r}")


class PoSEngine:
    """The end-to-end estimator. Constructs the Day-1/Day-2 components once (so the
    canonical table is loaded a single time) and exposes the three pipeline
    operations."""

    def __init__(self, config=None):
        self.config = config or EngineConfig()
        self.baseline = BaselineLookup()
        self.lr_engine = LikelihoodRatios()

    # -- baseline selection -------------------------------------------------

    def select_baseline(self, asset, phase):
        """Pick the baseline for one transition via the Day-1 fallback hierarchy.

        Maps the asset's canonical fields onto ``BaselineLookup.get``; the returned
        dict carries ``source_level`` / ``source_key``, which the double-count guard
        reads. (An ``Asset`` has no novelty field, so that tier is never supplied.)
        """
        disease = asset.disease_area.value if asset.disease_area else None
        modality = asset.modality.value if asset.modality else None
        return self.baseline.get(phase, disease=disease, modality=modality)

    # -- evidence routing ---------------------------------------------------

    def _applicable_evidence(self, asset, phase, baseline, remaining):
        """Return the ``(evidence_type, value)`` pairs to derive LRs for at ``phase``.

        An entry applies when its trigger fires, its temporality includes this phase,
        and it is not the tier the baseline was itself selected at (the double-count
        guard, evaluated per transition).
        """
        evidence = []
        for entry in EVIDENCE_ROUTING:
            if not _trigger_fires(asset, entry["trigger"]):
                continue
            if not _temporality_includes(entry["temporality"], phase, remaining):
                continue
            if entry["baseline_tier"] is not None and \
                    baseline["source_level"] == entry["baseline_tier"]:
                continue  # baseline already IS this signal -> don't count it twice
            value_from = entry["value_from"]
            value = _asset_value(asset, value_from) if value_from else None
            evidence.append((entry["evidence_type"], value))
        return evidence

    # -- per-phase adjustment ----------------------------------------------

    def adjust_phase_probability(self, asset, phase, remaining=None):
        """Adjust one transition's baseline by the asset's applicable evidence.

        Returns ``{phase, baseline, adjusted_prob, evidence, combine}``; the per-LR
        audit lives in ``combine["audit"]``. ``remaining`` (the ordered remaining
        transitions) is only needed to resolve ``next_only`` temporality; it defaults
        to the asset's full remaining list.
        """
        if remaining is None:
            remaining = asset.remaining_transitions()
        baseline = self.select_baseline(asset, phase)
        evidence = self._applicable_evidence(asset, phase, baseline, remaining)
        # lr() returns None for absent / too-small contrasts; combine drops those.
        lrs = [self.lr_engine.lr(etype, phase, value) for etype, value in evidence]
        combine = self.lr_engine.combine(baseline["rate"], lrs, k=self.config.k)
        return {
            "phase": phase,
            "baseline": baseline,
            "adjusted_prob": combine["adjusted_prob"],
            "evidence": evidence,
            "audit": combine["audit"],
            "combine": combine,
        }

    # -- compounding --------------------------------------------------------

    def _clip(self, p):
        """Clamp a probability into the engine's configured bounds."""
        return min(max(p, self.config.min_prob), self.config.max_prob)

    def compound_pos(self, asset):
        """Estimate the cumulative PoS from the asset's current phase through approval.

        Compounds the adjusted per-phase probabilities:
        ``cumulative_pos = PROD_t adjusted_prob_t`` over the remaining transitions,
        clipped to the engine's bounds. Returns the cumulative number plus a per-phase
        waterfall (baseline provenance, applied LRs + weights, adjusted probability,
        running cumulative).
        """
        if not isinstance(asset, Asset):
            asset = Asset.from_dict(asset)

        remaining = asset.remaining_transitions()
        cumulative = 1.0
        per_phase = []
        for phase in remaining:
            step = self.adjust_phase_probability(asset, phase, remaining)
            cumulative *= step["adjusted_prob"]
            per_phase.append({
                "phase": phase,
                "baseline_rate": step["baseline"]["rate"],
                "baseline_source_level": step["baseline"]["source_level"],
                "baseline_source_key": step["baseline"]["source_key"],
                "baseline_source_ref": step["baseline"]["source_ref"],
                "adjusted_prob": step["adjusted_prob"],
                "cumulative_after": cumulative,
                "audit": step["combine"]["audit"],
            })

        return {
            "cumulative_pos": self._clip(cumulative),
            "starting_phase": asset.current_phase.value,
            "n_transitions": len(remaining),
            "per_phase": per_phase,
            "asset": asset.to_dict(),
        }


# -- module-level convenience wrappers -------------------------------------
# A shared default engine so one-off calls don't reload the table each time. For
# batch scoring, construct a PoSEngine once and reuse it (or pass a custom config).
_DEFAULT_ENGINE = None


def _default_engine():
    global _DEFAULT_ENGINE
    if _DEFAULT_ENGINE is None:
        _DEFAULT_ENGINE = PoSEngine()
    return _DEFAULT_ENGINE


def select_baseline(asset, phase):
    """Thin wrapper over :meth:`PoSEngine.select_baseline` using a shared engine."""
    return _default_engine().select_baseline(asset, phase)


def adjust_phase_probability(asset, phase):
    """Thin wrapper over :meth:`PoSEngine.adjust_phase_probability`."""
    return _default_engine().adjust_phase_probability(asset, phase)


def compound_pos(asset):
    """Thin wrapper over :meth:`PoSEngine.compound_pos`."""
    return _default_engine().compound_pos(asset)


__all__ = [
    "PoSEngine",
    "select_baseline",
    "adjust_phase_probability",
    "compound_pos",
]


if __name__ == "__main__":
    # Quick manual check when running this file directly.
    engine = PoSEngine()

    print("Bare Phase-I asset (all-indications baselines, no evidence):")
    base = engine.compound_pos(Asset(current_phase="phase1"))
    print(f"  cumulative PoS = {base['cumulative_pos']:.4f}  (Fig 5b Phase I LOA ~= 0.079)")

    print("\nPhase-I biomarker + breakthrough asset:")
    rich = engine.compound_pos(Asset(
        current_phase="phase1",
        disease_area="Oncology",
        biomarker_flag=True,
        breakthrough_flag=True,
    ))
    print(f"  cumulative PoS = {rich['cumulative_pos']:.4f}")
    for step in rich["per_phase"]:
        lrs = ", ".join(f"{a['evidence_type']}={a['lr']:.2f}^{a['weight']:.2f}" for a in step["audit"]) or "-"
        print(f"  {step['phase']:<18} base={step['baseline_rate']:.3f}"
              f" [{step['baseline_source_level']}]  adj={step['adjusted_prob']:.3f}  LRs: {lrs}")
