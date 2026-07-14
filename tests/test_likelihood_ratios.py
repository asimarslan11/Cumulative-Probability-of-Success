"""
test_likelihood_ratios.py

The LikelihoodRatios.lr() derivation: the anchor LR values, the None-skip cases
(unknown / unpublished contrasts and sub-MIN_ARM_N arms), provenance fields, and
the Fig-14 low-confidence tagging.

Anchors are the odds ratios of two published arms in baseline_rates.json; the
expected values come straight from the Day-2 plan.

Run with:  python -m pytest tests/test_likelihood_ratios.py -v
"""

import pytest

from pos_engine.config import MIN_ARM_N
from pos_engine.likelihood_ratios import LikelihoodRatios

ENGINE = LikelihoodRatios()


# --- anchor LR values ------------------------------------------------------

def test_biomarker_phase2_to_3_roughly_doubles_odds():
    assert ENGINE.lr("biomarker", "phase2_to_3")["lr"] == pytest.approx(2.18, abs=0.01)


def test_biomarker_phase1_to_2_barely_moves():
    assert ENGINE.lr("biomarker", "phase1_to_2")["lr"] == pytest.approx(1.0, abs=0.02)


def test_rare_disease_phase2_to_3_anchor():
    assert ENGINE.lr("rare_disease", "phase2_to_3")["lr"] == pytest.approx(1.98, abs=0.01)


def test_cart_phase1_to_2_is_below_one():
    """CAR-T under-performs the industry average early; the LR honestly reflects it."""
    lr = ENGINE.lr("modality", "phase1_to_2", "CAR-T")["lr"]
    assert lr == pytest.approx(0.73, abs=0.01)
    assert lr < 1.0


def test_biosimilar_phase1_to_2_anchor():
    assert ENGINE.lr("novelty", "phase1_to_2", "Biosimilar")["lr"] == pytest.approx(3.69, abs=0.01)


def test_fig14_breakthrough_anchor():
    assert ENGINE.lr("breakthrough", "phase1_to_2")["lr"] == pytest.approx(2.33, abs=0.01)


def test_lead_indication_phase1_to_2_anchor():
    assert ENGINE.lr("lead_indication", "phase1_to_2")["lr"] == pytest.approx(1.59, abs=0.01)


# --- None-skip cases -------------------------------------------------------

def test_unknown_evidence_type_returns_none():
    assert ENGINE.lr("not_a_real_signal", "phase1_to_2") is None


def test_unknown_modality_value_returns_none():
    assert ENGINE.lr("modality", "phase1_to_2", "NotAModality") is None


def test_lead_indication_skips_unmapped_late_phases():
    """Wong merges filing+approval, so lead-indication is undefined at the late phases."""
    assert ENGINE.lr("lead_indication", "phase3_to_filing") is None
    assert ENGINE.lr("lead_indication", "filing_to_approval") is None
    # ...but defined for the two early phases.
    assert ENGINE.lr("lead_indication", "phase2_to_3") is not None


def test_small_arm_is_skipped_cart_filing_to_approval():
    """CAR-T filing->approval is 100% on n=4 -> would be an absurd LR; skip it."""
    assert ENGINE.lr("modality", "filing_to_approval", "CAR-T") is None


def test_small_arm_is_skipped_biosimilar_phase2_to_3():
    """Biosimilar Phase II->III has n=4 -> skipped."""
    assert ENGINE.lr("novelty", "phase2_to_3", "Biosimilar") is None


def test_min_arm_n_is_the_threshold():
    """Both arms of a returned LR must clear MIN_ARM_N."""
    result = ENGINE.lr("biomarker", "phase2_to_3")
    assert result["arms"]["present"]["n"] >= MIN_ARM_N
    assert result["arms"]["reference"]["n"] >= MIN_ARM_N


def test_unknown_phase_raises():
    with pytest.raises(ValueError):
        ENGINE.lr("biomarker", "phaseX_to_Y")


# --- provenance ------------------------------------------------------------

def test_lr_carries_full_provenance():
    result = ENGINE.lr("biomarker", "phase2_to_3")
    for field in ("lr", "evidence_type", "value", "phase", "source", "source_ref",
                  "confidence", "arms"):
        assert field in result, f"missing provenance field {field!r}"
    assert result["evidence_type"] == "biomarker"
    assert result["phase"] == "phase2_to_3"
    assert "Fig 11" in result["source_ref"]
    # arms record the raw rates and odds that produced the LR.
    assert set(result["arms"]) == {"present", "reference"}
    assert result["arms"]["present"]["rate"] == 0.463
    assert result["arms"]["reference"]["rate"] == 0.283


def test_row_derived_lrs_are_high_confidence():
    assert ENGINE.lr("biomarker", "phase2_to_3")["confidence"] == "high"
    assert ENGINE.lr("modality", "phase1_to_2", "CAR-T")["confidence"] == "high"


def test_lead_indication_is_flagged_proxy():
    assert ENGINE.lr("lead_indication", "phase1_to_2")["confidence"] == "proxy"


def test_fig14_lrs_are_low_confidence():
    for signal in ("breakthrough", "trial_outcome_positive", "prior_approval",
                   "validated_target"):
        result = ENGINE.lr(signal, "phase2_to_3")
        assert result is not None, signal
        assert result["confidence"] == "low", signal


def test_fig14_lrs_are_phase_independent():
    """A single worked example (baseline 0.35) -> same LR at every phase."""
    a = ENGINE.lr("prior_approval", "phase1_to_2")["lr"]
    b = ENGINE.lr("prior_approval", "filing_to_approval")["lr"]
    assert a == pytest.approx(b)
