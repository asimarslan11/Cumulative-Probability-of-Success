"""
test_engine.py

The Day-3 pipeline: select_baseline -> evidence routing -> adjust_phase_probability
-> compound_pos. Anchors trace to specific BIO/QLS figures (cited per test); the
behavioural tests pin the Day-3 decisions (temporality, the baseline-tier
double-count guard, config-driven shrinkage) so they can't silently regress.

Run with:  python -m pytest tests/test_engine.py -v
"""

import pytest

from pos_engine.asset import Asset
from pos_engine.config import EngineConfig
from pos_engine.engine import PoSEngine

ENGINE = PoSEngine()


def _evidence_types(per_phase_step):
    """The evidence types applied at one per-phase waterfall step."""
    return [a["evidence_type"] for a in per_phase_step["audit"]]


def _phase(result, phase):
    """Pull one transition's waterfall entry out of a compound_pos result."""
    return next(s for s in result["per_phase"] if s["phase"] == phase)


# --- compounding sanity: the Fig 5b Phase I LOA ----------------------------

def test_bare_phase1_reproduces_fig5b_loa():
    """A Phase-I asset with no evidence compounds the four all-indications rates
    (Fig 1) to the published Phase I LOA ~= 7.9% (BIO/QLS Fig 5b):
    0.520 x 0.289 x 0.578 x 0.906 = 0.0787."""
    result = ENGINE.compound_pos(Asset(current_phase="phase1"))
    assert result["cumulative_pos"] == pytest.approx(0.0787, abs=0.001)
    assert result["n_transitions"] == 4


def test_no_evidence_adjusted_equals_baseline():
    """With no LRs, each phase's adjusted probability is just its baseline rate."""
    result = ENGINE.compound_pos(Asset(current_phase="phase1"))
    for step in result["per_phase"]:
        assert step["adjusted_prob"] == pytest.approx(step["baseline_rate"], abs=1e-9)
        assert step["audit"] == []


# --- select_baseline maps onto the Day-1 fallback tiers --------------------

def test_select_baseline_disease_tier():
    """Hematology, Phase II->III -> disease+phase tier, rate 0.481 (Fig 2)."""
    base = ENGINE.select_baseline(Asset(current_phase="phase2", disease_area="Hematology"),
                                  "phase2_to_3")
    assert base["source_level"] == "disease+phase"
    assert base["rate"] == pytest.approx(0.481, abs=0.001)


def test_select_baseline_modality_tier_when_no_disease():
    """No disease but a CAR-T modality -> the modality tier (Fig 10b)."""
    base = ENGINE.select_baseline(Asset(current_phase="phase1", modality="CAR-T"),
                                  "phase1_to_2")
    assert base["source_level"] == "modality"
    assert base["source_key"] == "CAR-T"


def test_select_baseline_falls_all_the_way_back():
    """Nothing specific -> the all-indications average (Fig 1)."""
    base = ENGINE.select_baseline(Asset(current_phase="phase1"), "phase1_to_2")
    assert base["source_level"] == "all_indication"


# --- evidence moves the number the right way -------------------------------

def test_biomarker_raises_cumulative_pos():
    """A biomarker-defined program should out-score the same program without one."""
    plain = ENGINE.compound_pos(Asset(current_phase="phase1", disease_area="Oncology"))
    with_bm = ENGINE.compound_pos(Asset(current_phase="phase1", disease_area="Oncology",
                                        biomarker_flag=True))
    assert with_bm["cumulative_pos"] > plain["cumulative_pos"]


def test_cart_modality_lr_dampens_early_transition():
    """CAR-T under-performs early (LR ~0.73 at Phase I->II, Fig 10b vs Fig 1), so on a
    disease-tier baseline the modality LR pulls the adjusted probability below it."""
    step = ENGINE.adjust_phase_probability(
        Asset(current_phase="phase1", disease_area="Oncology", modality="CAR-T"),
        "phase1_to_2",
    )
    assert "modality" in _evidence_types(step)
    assert step["adjusted_prob"] < step["baseline"]["rate"]


# --- the baseline-tier double-count guard ----------------------------------

def test_modality_lr_skipped_when_baseline_is_modality_tier():
    """No disease -> every baseline falls back to the modality tier, so the modality
    LR must NOT be applied on top (it would count CAR-T twice)."""
    result = ENGINE.compound_pos(Asset(current_phase="phase1", modality="CAR-T"))
    for step in result["per_phase"]:
        assert step["baseline_source_level"] == "modality"
        assert "modality" not in _evidence_types(step)


def test_modality_lr_applied_when_baseline_is_disease_tier():
    """With a disease-specific baseline, the modality LR is a distinct contrast and
    IS applied (no double-count)."""
    result = ENGINE.compound_pos(Asset(current_phase="phase1", disease_area="Oncology",
                                       modality="CAR-T"))
    step = _phase(result, "phase1_to_2")
    assert step["baseline_source_level"] == "disease+phase"
    assert "modality" in _evidence_types(step)


# --- temporality: signals apply only to the transitions they should --------

def test_trial_outcome_applies_to_next_transition_only():
    """A positive readout is evidence about the step just completed -> it applies to
    the immediate next transition only, never re-counted down the pipeline."""
    result = ENGINE.compound_pos(Asset(current_phase="phase1", disease_area="Oncology",
                                       trial_outcome="positive"))
    assert "trial_outcome_positive" in _evidence_types(_phase(result, "phase1_to_2"))
    for later in ("phase2_to_3", "phase3_to_filing", "filing_to_approval"):
        assert "trial_outcome_positive" not in _evidence_types(_phase(result, later))


def test_breakthrough_applies_to_filing_facing_transitions_only():
    """Breakthrough designation eases the regulatory path -> filing-facing transitions
    only (phase3_to_filing, filing_to_approval)."""
    result = ENGINE.compound_pos(Asset(current_phase="phase1", disease_area="Oncology",
                                       breakthrough_flag=True))
    for early in ("phase1_to_2", "phase2_to_3"):
        assert "breakthrough" not in _evidence_types(_phase(result, early))
    for late in ("phase3_to_filing", "filing_to_approval"):
        assert "breakthrough" in _evidence_types(_phase(result, late))


# --- waterfall integrity ---------------------------------------------------

def test_cumulative_equals_product_of_adjusted():
    """cumulative_pos is exactly the product of the per-phase adjusted probabilities
    (when it doesn't hit the clip bounds)."""
    result = ENGINE.compound_pos(Asset(current_phase="phase1", disease_area="Oncology",
                                       biomarker_flag=True, breakthrough_flag=True))
    product = 1.0
    for step in result["per_phase"]:
        product *= step["adjusted_prob"]
    assert result["cumulative_pos"] == pytest.approx(product, abs=1e-9)


def test_waterfall_carries_provenance():
    """Every per-phase step names its baseline source, and every applied LR carries a
    weight and a source_ref -- the audit trail must be readable back to a figure."""
    result = ENGINE.compound_pos(Asset(current_phase="phase3", disease_area="Oncology",
                                       breakthrough_flag=True))
    step = _phase(result, "phase3_to_filing")
    assert step["baseline_source_ref"]
    bt = next(a for a in step["audit"] if a["evidence_type"] == "breakthrough")
    assert "weight" in bt and bt["source_ref"]


# --- starting phase & bounds -----------------------------------------------

def test_start_phase_limits_remaining_transitions():
    """A Phase-III asset compounds only the last two transitions."""
    result = ENGINE.compound_pos(Asset(current_phase="phase3"))
    assert result["n_transitions"] == 2
    assert [s["phase"] for s in result["per_phase"]] == ["phase3_to_filing", "filing_to_approval"]


def test_compound_pos_accepts_a_plain_dict():
    """A dict asset is coerced via Asset.from_dict, so callers can pass raw JSON."""
    from_obj = ENGINE.compound_pos(Asset(current_phase="phase2", disease_area="Oncology"))
    from_dict = ENGINE.compound_pos({"current_phase": "phase2", "disease_area": "Oncology"})
    assert from_dict["cumulative_pos"] == pytest.approx(from_obj["cumulative_pos"])


def test_cumulative_pos_strictly_in_unit_interval():
    """Even stacking strong positive signals, the result stays inside (0, 1)."""
    result = ENGINE.compound_pos(Asset(
        current_phase="filing",
        disease_area="Oncology",
        biomarker_flag=True,
        breakthrough_flag=True,
        prior_approval_flag=True,
    ))
    assert 0.0 < result["cumulative_pos"] < 1.0


# --- config-driven shrinkage (EngineConfig) --------------------------------

def test_shrinkage_k_dampens_correlated_stack():
    """biomarker + CAR-T are both precision_medicine signals; with k>0 their combined
    lift is dampened vs the naive product (k=0). EngineConfig makes k injectable so
    Day 4 can sweep it without editing code."""
    asset = Asset(current_phase="phase2", disease_area="Oncology",
                  biomarker_flag=True, modality="CAR-T")
    full = PoSEngine(EngineConfig(k=0.0)).adjust_phase_probability(asset, "phase2_to_3")
    damped = PoSEngine(EngineConfig(k=0.5)).adjust_phase_probability(asset, "phase2_to_3")
    # Both LRs > 1 and correlated, so dampening pulls the adjusted probability down.
    assert "biomarker" in _evidence_types(full) and "modality" in _evidence_types(full)
    assert damped["adjusted_prob"] < full["adjusted_prob"]
