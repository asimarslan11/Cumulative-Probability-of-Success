"""
report.py

Turns a `compound_pos` result into a **critical paragraph**: prose that states the estimate
and then, in the same breath, tells you how much to trust it.

Everything the paragraph says is read back off the engine's own audit trail -- which
baseline tier each transition landed on, which likelihood ratios were applied and at what
confidence, which routed signals were dropped, whether shrinkage or the clip bit. Nothing
here re-computes or second-guesses the engine; it narrates it.

"Critical" is meant literally. A bare number under a drug's name invites more confidence
than this method can support, so the paragraph is written to surface the weaknesses a reader
would otherwise have to dig for: a baseline that fell back to the industry average, an
illustrative Fig-14 likelihood ratio doing real work, a stale `current_phase`, the fact that
the whole estimate is a reference class rather than a prediction.

    assess("EXAMPLE-001")["paragraph"]  ->  the paragraph, as a string
"""

from pos_engine.asset import Asset
from pos_engine.config import MAX_PROB, MIN_PROB
from pos_engine.engine import PoSEngine
from pos_engine.registry import resolve

PHASE_LABEL = {
    "phase1": "Phase I",
    "phase2": "Phase II",
    "phase3": "Phase III",
    "filing": "filing (NDA/BLA)",
}

TRANSITION_LABEL = {
    "phase1_to_2": "Phase I->II",
    "phase2_to_3": "Phase II->III",
    "phase3_to_filing": "Phase III->NDA/BLA",
    "filing_to_approval": "NDA/BLA->approval",
}

EVIDENCE_LABEL = {
    "biomarker": "a patient-preselection biomarker",
    "rare_disease": "rare-disease status",
    "modality": "its modality",
    "trial_outcome_positive": "a positive trial read-out",
    "breakthrough": "breakthrough designation",
    "prior_approval": "prior approval in class",
    "lead_indication": "lead-indication status",
}

# How a fallback tier should be described when it is the weakest link.
_TIER_LABEL = {
    "disease+phase": "disease-specific",
    "modality": "modality-level",
    "novelty_class": "novelty-class",
    "all_indication": "the all-indications industry average",
}


def _pct(p):
    return f"{p * 100:.1f}%"


def _label(evidence_type):
    return EVIDENCE_LABEL.get(evidence_type, evidence_type.replace("_", " "))


def _oxford(items):
    """Join a list into readable prose: 'a', 'a and b', 'a, b and c'."""
    items = list(items)
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


def critical_paragraph(result, reference_pos, name="This programme", provenance=None, k=None):
    """Render a `compound_pos` result as a single critical paragraph.

    ``reference_pos`` is the all-indications cumulative PoS from the same starting phase --
    the honest comparator, since comparing a Phase-III asset to the Phase-I industry average
    would flatter it purely for having survived.
    """
    pos = result["cumulative_pos"]
    start = result["starting_phase"]
    per_phase = result["per_phase"]
    sentences = []

    # --- the number, against its own reference class -----------------------
    ratio = pos / reference_pos if reference_pos else None
    if ratio is None:
        verdict = ""
    elif ratio >= 1.15:
        verdict = f", about {ratio:.1f}x the {_pct(reference_pos)} industry average from the same phase"
    elif ratio <= 0.85:
        verdict = (f", below the {_pct(reference_pos)} industry average from the same phase "
                   f"({ratio:.2f}x)")
    else:
        verdict = f", essentially in line with the {_pct(reference_pos)} industry average from the same phase"
    sentences.append(
        f"{name} carries an estimated {_pct(pos)} cumulative probability of success from "
        f"{PHASE_LABEL[start]} through FDA approval{verdict}."
    )

    # --- how well grounded are the baselines? ------------------------------
    levels = [s["baseline_source_level"] for s in per_phase]
    generic = [s for s in per_phase if s["baseline_source_level"] == "all_indication"]
    if not generic and all(lvl == "disease+phase" for lvl in levels):
        key = per_phase[0]["baseline_source_key"]
        sentences.append(
            f"Every remaining transition is anchored on {key}-specific baselines "
            f"(BIO/QLS Figure 2), which is the most specific grounding the published data "
            f"supports."
        )
    elif generic:
        which = _oxford([TRANSITION_LABEL[s["phase"]] for s in generic])
        sentences.append(
            f"That number is only weakly specific to this programme: {len(generic)} of "
            f"{len(per_phase)} transitions ({which}) fall back to {_TIER_LABEL['all_indication']}, "
            f"so for those steps it is closer to an industry base rate wearing this drug's name "
            f"than a statement about the drug."
        )
    else:
        tiers = _oxford(sorted({_TIER_LABEL.get(l, l) for l in levels}))
        sentences.append(
            f"Baselines come from {tiers} rows rather than a disease-specific rate, so the "
            f"estimate is coarser than a disease-anchored one would be."
        )
    if "modality" in levels:
        sentences.append(
            "Where the baseline is the modality tier, the modality likelihood ratio is "
            "deliberately withheld so the same signal is not counted twice."
        )

    # --- what actually moved the number ------------------------------------
    applied = {}
    for step in per_phase:
        for a in step["audit"]:
            applied.setdefault(a["evidence_type"], []).append(a)
    if applied:
        described = []
        for etype, entries in applied.items():
            lrs = [e["lr"] for e in entries]
            span = (f"LR {lrs[0]:.2f}" if len(set(round(x, 3) for x in lrs)) == 1
                    else f"LR {min(lrs):.2f}-{max(lrs):.2f}")
            described.append(f"{_label(etype)} ({span})")
        sentences.append(
            f"The adjustment away from those baselines rests on {_oxford(described)}."
        )
        # Confidence flags: the parts a reader should discount.
        low = sorted({e["evidence_type"] for es in applied.values() for e in es
                      if e.get("confidence") == "low"})
        proxy = sorted({e["evidence_type"] for es in applied.values() for e in es
                        if e.get("confidence") == "proxy"})
        if low:
            sentences.append(
                f"Treat {_oxford([_label(e) for e in low])} with real caution: "
                f"{'it is' if len(low) == 1 else 'they are'} derived from a single worked "
                f"example in BIO/QLS Figure 14 (a 35% baseline), not a population contrast, "
                f"so {'it carries' if len(low) == 1 else 'they carry'} an illustrative "
                f"effect size into a number that reads as precise."
            )
        if proxy:
            sentences.append(
                f"{_oxford([_label(e) for e in proxy]).capitalize()} is a cross-study proxy "
                f"taken from Wong (2019), a different dataset and method to the BIO/QLS "
                f"baselines it is being multiplied against."
            )
        # Shrinkage.
        correlated = {e["group"] for es in applied.values() for e in es if e["group_size"] > 1}
        if correlated:
            sentences.append(
                f"Correlated signals were dampened rather than stacked at full strength "
                f"(shrinkage k={k if k is not None else 'default'}), since they tell "
                f"overlapping stories; that dampening is a modelling judgement, not a "
                f"published parameter."
            )
    else:
        sentences.append(
            "No evidence-specific adjustment applies, so this is the bare reference-class "
            "base rate for these attributes."
        )

    # --- signals that were asked for but could not be honoured -------------
    dropped = {}
    for step in per_phase:  # per_phase is already in pipeline order
        got = {a["evidence_type"] for a in step["audit"]}
        for etype in step.get("evidence_routed", []):
            if etype not in got:
                dropped.setdefault(etype, []).append(step["phase"])
    if dropped:
        described = _oxford([
            f"{_label(etype)} at {_oxford([TRANSITION_LABEL[p] for p in phases])}"
            for etype, phases in dropped.items()
        ])
        # Deliberately not naming a single cause: lr() returns None both when the source
        # doesn't publish the contrast at that phase and when an arm is below MIN_ARM_N,
        # and the audit trail can't tell the two apart.
        sentences.append(
            f"Some signals were claimed but could not be honoured -- {described} -- because "
            f"no usable published contrast exists at those transitions (either the source "
            f"does not report it there, or the arm is too small to trust); they are simply "
            f"absent rather than counted as neutral."
        )

    # --- did the arithmetic hit its own guard rails? -----------------------
    clipped = [s for s in per_phase if s["adjusted_prob"] >= MAX_PROB - 1e-9
               or s["adjusted_prob"] <= MIN_PROB + 1e-9]
    if clipped:
        # Two very different causes, and the paragraph must not blame the wrong one:
        # a degenerate published cell (100%/0% on a small sample) vs an evidence stack
        # pushing past the ceiling.
        bits = [f"the published baseline at {TRANSITION_LABEL[s['phase']]} is itself "
                f"{_pct(s['baseline_rate'])}" for s in clipped if not s["audit"]]
        stack_driven = [s for s in clipped if s["audit"]]
        if stack_driven:
            bits.append(
                "the evidence stack pushes "
                f"{_oxford([TRANSITION_LABEL[s['phase']] for s in stack_driven])} past the ceiling"
            )
        sentences.append(
            f"The result leans on the engine's {_pct(MAX_PROB)}/{_pct(MIN_PROB)} clip "
            f"({_oxford(bits)}), so at "
            f"{'that step' if len(clipped) == 1 else 'those steps'} a guard rail rather than "
            f"the data sets the number -- the engine refuses to treat any transition as certain."
        )

    # --- where the inputs came from ----------------------------------------
    if provenance:
        if provenance.get("registered"):
            src = (provenance.get("_source") or "unspecified").rstrip(". ")
            as_of = provenance.get("_as_of")
            sentences.append(
                f"The attributes behind this ({src}"
                + (f"; checked {as_of}" if as_of else "")
                + ") are a declared input, not something the sources provide: neither BIO/QLS "
                  "nor Wong contains per-drug data, and a stale current_phase would move this "
                  "number more than any modelling choice in the engine."
            )
        else:
            sentences.append(
                "The attributes behind this were supplied at run time and are not recorded "
                "anywhere auditable; neither source contains per-drug data, so the estimate "
                "inherits whatever accuracy those inputs had."
            )

    # --- the standing caveat -----------------------------------------------
    sentences.append(
        "Read the figure as a reference class, not a prediction: it says what happened to "
        "2011-2020 programmes sharing these coarse attributes, and it knows nothing about "
        "this molecule's actual trial data, target biology, competition, or sponsor."
    )

    return " ".join(sentences)


def assess(name, overrides=None, engine=None, k=None):
    """Resolve ``name``, score it, and render the critical paragraph.

    Returns ``{name, asset, provenance, result, reference_pos, paragraph}``. Raises
    :class:`~pos_engine.registry.UnknownAssetError` if the name isn't registered and no
    attributes were supplied -- the engine never invents an asset.
    """
    engine = engine or PoSEngine()
    asset_kwargs, provenance = resolve(name, overrides)
    asset = Asset(**asset_kwargs)
    result = engine.compound_pos(asset)

    # The honest comparator: the same starting phase, stripped of all evidence.
    reference_pos = engine.compound_pos(
        Asset(current_phase=asset.current_phase))["cumulative_pos"]

    paragraph = critical_paragraph(
        result, reference_pos, name=provenance.get("resolved_name", name),
        provenance=provenance, k=engine.config.k,
    )
    return {
        "name": provenance.get("resolved_name", name),
        "asset": asset.to_dict(),
        "provenance": provenance,
        "result": result,
        "reference_pos": reference_pos,
        "paragraph": paragraph,
    }


__all__ = ["assess", "critical_paragraph"]
