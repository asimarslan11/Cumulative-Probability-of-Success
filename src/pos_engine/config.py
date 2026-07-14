"""
config.py

All of Day 2's tunable knobs and lookup tables in one place, so the statistics in
``odds.py`` / ``likelihood_ratios.py`` stay pure and the numbers you might want to
sweep (Day 4) or move into an external config file (Day 3) are collected here.

Nothing in this module reads data or does arithmetic; it only *declares* constants
and the maps that say **which two published arms** define each likelihood ratio.

References are to:
    - BIO/QLS Advisors (2021), Clinical Development Success Rates 2011-2020
    - Wong, Siah & Lo (2019), Biostatistics 20(2)
"""

from dataclasses import dataclass

# --- clip range (odds arithmetic) ------------------------------------------
# The brief's 0.1%-99% clamp. Keeps 0% / 100% source cells from producing 0 or
# infinite odds when we convert prob <-> odds.
MIN_PROB = 0.001
MAX_PROB = 0.99

# --- shrinkage ------------------------------------------------------------
# Dampening strength for correlated evidence. Each member of a correlation group
# of size m gets exponent w = 1 / (1 + k*(m-1)); k=0 disables shrinkage (full
# product), larger k pulls a stack of correlated LRs back toward the baseline.
# Day 4 sweeps k in {0, 0.25, 0.5, 1}.
SHRINKAGE_K = 0.5

# --- small-arm guard ------------------------------------------------------
# Below this, a published arm's rate is too noisy to trust as half of an odds
# ratio. e.g. CAR-T filing->approval is 100% on n=4 -> an LR of "infinity" that is
# an artefact of sample size, not signal. lr() returns None (skip) for such arms.
MIN_ARM_N = 10

# --- likelihood-ratio reference map ----------------------------------------
# An LR is an odds ratio between two arms of a published contrast:
#     LR = odds(present arm) / odds(reference arm),   computed per phase.
#
# Each entry says where to find those two arms in baseline_rates.json:
#     present   = (category_type, category)   category=None -> filled from the
#                                              caller-supplied `value` (e.g. modality)
#     reference = (category_type, category)
#     source_ref, confidence  provenance carried onto the result.
#
# Reference-arm policy (confirmed Day-2 decision):
#   * modality & novelty are contrasted against the all-indications average (Fig 1);
#   * biomarker & rare keep their own figure's two-arm reference
#     (Fig 11 without-biomarker; Fig 8b rare vs the all-indications average);
#   * oncology subtype is contrasted against the Oncology disease-area rate (Fig 2).
LR_REFERENCE = {
    "biomarker": {
        "present": ("biomarker", "with_biomarker"),
        "reference": ("biomarker", "without_biomarker"),
        "source_ref": "BIO/QLS Fig 11 (with vs without biomarker)",
        "confidence": "high",
    },
    "rare_disease": {
        "present": ("rare_chronic", "rare_disease"),
        "reference": ("all_indications", "all_indications"),
        "source_ref": "BIO/QLS Fig 8b (rare) vs Fig 1 (all indications)",
        "confidence": "high",
    },
    "modality": {
        "present": ("modality", None),  # None -> caller supplies the modality name
        "reference": ("all_indications", "all_indications"),
        "source_ref": "BIO/QLS Fig 10b (modality) vs Fig 1 (all indications)",
        "confidence": "high",
    },
    "novelty": {
        "present": ("novelty_class", None),  # None -> caller supplies the novelty class
        "reference": ("all_indications", "all_indications"),
        "source_ref": "BIO/QLS Fig 9 (novelty class) vs Fig 1 (all indications)",
        "confidence": "high",
    },
    "oncology_subtype": {
        "present": ("oncology_subtype", None),  # None -> caller supplies the subtype
        "reference": ("disease_area", "Oncology"),
        "source_ref": "BIO/QLS Fig 7 (subtype) vs Fig 2 (Oncology)",
        "confidence": "high",
    },
}

# --- lead-indication proxy (Wong Table 2) ----------------------------------
# Wong reports success both "per lead indication" and "per indication (all)".
# The lead-vs-all odds ratio is our best published proxy for "this asset's program
# is being run on its strongest indication". It is a PROXY, not a like-for-like
# contrast (different study, path-by-path, different phase scheme), so it is flagged
# and only defined for the two early transitions: Wong merges filing+approval into
# one phase3_to_approval step that does not map onto BIO/QLS's two late phases.
LEAD_INDICATION_PROXY = {
    "present": ("therapeutic_group_lead", "Overall"),
    "reference": ("therapeutic_group", "Overall"),
    "phases": ("phase1_to_2", "phase2_to_3"),
    "source_ref": "Wong 2019 Table 2 (lead vs all indications)",
    "confidence": "proxy",
}

# --- illustrative LRs (BIO/QLS Fig 14) -------------------------------------
# Fig 14 gives a single worked example (baseline 35%) of how various signals move
# the number. We turn each delta into an odds ratio against that same 0.35 anchor:
#     LR = odds(0.35 + delta) / odds(0.35).
# These are single-example illustrations, NOT population contrasts, so they are
# phase-independent and flagged confidence="low".
ILLUSTRATIVE_BASELINE = 0.35
ILLUSTRATIVE_LRS = {
    "breakthrough": {"delta": 0.206, "source_ref": "BIO/QLS Fig 14 (breakthrough designation)"},
    "trial_outcome_positive": {"delta": 0.064, "source_ref": "BIO/QLS Fig 14 (positive trial outcome)"},
    "prior_approval": {"delta": 0.036, "source_ref": "BIO/QLS Fig 14 (prior approval in class)"},
    "validated_target": {"delta": 0.046, "source_ref": "BIO/QLS Fig 14 (validated target)"},
}

# --- correlation groups (shrinkage) ----------------------------------------
# Evidence in the same group tells overlapping stories, so stacking their LRs at
# full strength would double-count. Members are matched on (evidence_type, value);
# value=None means "any value of this evidence type". Anything not matched here is
# treated as independent (its own singleton group, weight 1).
CORRELATION_GROUPS = {
    # Precision-medicine signals: a biomarker-defined program, one of the targeted
    # advanced modalities, or immuno-oncology all lean on the same underlying story.
    "precision_medicine": {
        "biomarker": None,
        "modality": {"CAR-T", "siRNA/RNAi", "ADCs", "Gene therapy"},
        "oncology_subtype": {"immuno_oncology"},
    },
    # Regulatory-facilitation signals: rare-disease status, breakthrough designation,
    # and prior approval in class all correlate with a smoother regulatory path.
    "regulatory_facilitation": {
        "rare_disease": None,
        "breakthrough": None,
        "prior_approval": None,
    },
}


# --- Day-3 pipeline config -------------------------------------------------
@dataclass(frozen=True)
class EngineConfig:
    """The run-time knobs the Day-3 pipeline reads, bundled so Day 4 can sweep them
    without editing code (e.g. ``EngineConfig(k=0.25)``).

    ``k``                 shrinkage strength passed to ``LikelihoodRatios.combine``.
    ``min_prob``/``max_prob``  bounds the engine clips the *cumulative* PoS to, so a
                          deep pipeline can't report a number outside the stated
                          0.1%-99% range. (Per-phase probabilities are already clipped
                          inside ``combine`` using the module constants.)

    Defaults mirror the module-level constants above, so an ``EngineConfig()`` behaves
    exactly like the un-parameterised engine.
    """

    k: float = SHRINKAGE_K
    min_prob: float = MIN_PROB
    max_prob: float = MAX_PROB


# --- evidence routing (asset field -> likelihood ratio) --------------------
# The single table that turns an Asset's fields into LR requests. Day 3's pipeline
# walks this list; nothing else decides which LRs an asset gets.
#
# Each entry:
#   evidence_type   passed to LikelihoodRatios.lr(evidence_type, phase, value)
#   trigger         how to tell the signal is present on the asset:
#                     ("flag", field)             -> getattr(asset, field) is True
#                     ("present", field)          -> getattr(asset, field) is not None
#                     ("equals", field, value)    -> asset field's value == value
#   value_from      asset attribute supplying the LR `value` (modality/novelty names),
#                   or None for fixed contrasts
#   temporality     which of the remaining transitions the signal applies to:
#                     "persistent"  every remaining transition (a standing program
#                                   attribute)
#                     "next_only"   only the immediate next transition (a one-time
#                                   readout, not re-counted down the pipeline)
#                     "regulatory"  only the filing-facing transitions in
#                                   REGULATORY_PHASES
#   baseline_tier   the fallback tier this LR would double-count if that tier was
#                   itself the baseline for the transition (skip it then); None if the
#                   contrast never coincides with a baseline tier
REGULATORY_PHASES = ("phase3_to_filing", "filing_to_approval")

EVIDENCE_ROUTING = (
    {
        "evidence_type": "biomarker",
        "trigger": ("flag", "biomarker_flag"),
        "value_from": None,
        "temporality": "persistent",
        "baseline_tier": None,
    },
    {
        "evidence_type": "rare_disease",
        "trigger": ("flag", "rare_disease_flag"),
        "value_from": None,
        "temporality": "persistent",
        "baseline_tier": None,
    },
    {
        # A program's modality is a standing attribute, but if the baseline itself
        # fell back to the modality tier (no disease-specific rate), applying the
        # modality LR too would double-count -> baseline_tier guards that per phase.
        "evidence_type": "modality",
        "trigger": ("present", "modality"),
        "value_from": "modality",
        "temporality": "persistent",
        "baseline_tier": "modality",
    },
    {
        # Evidence about the readout just completed -> the immediate next step only.
        "evidence_type": "trial_outcome_positive",
        "trigger": ("equals", "trial_outcome", "positive"),
        "value_from": None,
        "temporality": "next_only",
        "baseline_tier": None,
    },
    {
        "evidence_type": "breakthrough",
        "trigger": ("flag", "breakthrough_flag"),
        "value_from": None,
        "temporality": "regulatory",
        "baseline_tier": None,
    },
    {
        "evidence_type": "prior_approval",
        "trigger": ("flag", "prior_approval_flag"),
        "value_from": None,
        "temporality": "regulatory",
        "baseline_tier": None,
    },
    {
        # Persistent in principle, but LEAD_INDICATION_PROXY caps its phases to the
        # two early transitions and lr() returns None elsewhere, so no phase filter
        # is needed here.
        "evidence_type": "lead_indication",
        "trigger": ("flag", "lead_indication_flag"),
        "value_from": None,
        "temporality": "persistent",
        "baseline_tier": None,
    },
)


__all__ = [
    "MIN_PROB",
    "MAX_PROB",
    "SHRINKAGE_K",
    "MIN_ARM_N",
    "LR_REFERENCE",
    "LEAD_INDICATION_PROXY",
    "ILLUSTRATIVE_BASELINE",
    "ILLUSTRATIVE_LRS",
    "CORRELATION_GROUPS",
    "EngineConfig",
    "REGULATORY_PHASES",
    "EVIDENCE_ROUTING",
]
