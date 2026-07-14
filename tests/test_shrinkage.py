"""
test_shrinkage.py

LikelihoodRatios.combine() and the correlation-group shrinkage: correlated evidence
is dampened (a pair combines to *less* than its naive product), higher k pulls the
result toward the baseline, k=0 recovers the full product, independent evidence is
untouched, and the output is always strictly inside (0, 1).

These use small synthetic LR dicts so the arithmetic is exact and independent of the
source data; the shape of a synthetic item matches what lr() returns.

Run with:  python -m pytest tests/test_shrinkage.py -v
"""

import pytest

from pos_engine.config import MAX_PROB, MIN_PROB
from pos_engine.likelihood_ratios import LikelihoodRatios, resolve_correlation_group
from pos_engine.odds import odds_to_prob, prob_to_odds

ENGINE = LikelihoodRatios()


def item(evidence_type, lr, value=None):
    """A minimal LR item of the shape combine() consumes (as lr() returns)."""
    return {"evidence_type": evidence_type, "value": value, "lr": lr, "confidence": "high"}


def naive_prob(baseline, *lrs):
    """The baseline adjusted by the full, un-shrunk product of LRs."""
    odds = prob_to_odds(baseline)
    for lr in lrs:
        odds *= lr
    return odds_to_prob(odds)


# --- correlation-group resolution ------------------------------------------

def test_group_resolution():
    assert resolve_correlation_group("biomarker") == "precision_medicine"
    assert resolve_correlation_group("modality", "CAR-T") == "precision_medicine"
    assert resolve_correlation_group("oncology_subtype", "immuno_oncology") == "precision_medicine"
    assert resolve_correlation_group("rare_disease") == "regulatory_facilitation"
    assert resolve_correlation_group("breakthrough") == "regulatory_facilitation"
    # Non-matching values and unlisted types fall through to independent singletons.
    assert resolve_correlation_group("modality", "Small molecule").startswith("independent")
    assert resolve_correlation_group("oncology_subtype", "solid_tumor").startswith("independent")
    assert resolve_correlation_group("lead_indication").startswith("independent")


# --- monotonic dampening ---------------------------------------------------

def test_correlated_pair_is_less_than_naive_product():
    """Two precision-medicine LRs must combine to strictly less than their product."""
    baseline, lr1, lr2 = 0.3, 2.0, 3.0
    correlated = [item("biomarker", lr1), item("oncology_subtype", lr2, "immuno_oncology")]
    result = ENGINE.combine(baseline, correlated, k=0.5)

    naive = naive_prob(baseline, lr1, lr2)
    # Dampened, but still moved above the baseline (both LRs > 1).
    assert baseline < result["adjusted_prob"] < naive
    # Both members share one group and get the same pair weight 1/(1+0.5) = 2/3.
    assert all(a["group"] == "precision_medicine" for a in result["audit"])
    assert all(a["weight"] == pytest.approx(2 / 3) for a in result["audit"])


def test_higher_k_pulls_result_toward_baseline():
    baseline, lr1, lr2 = 0.3, 2.0, 3.0
    correlated = [item("biomarker", lr1), item("oncology_subtype", lr2, "immuno_oncology")]

    low_k = ENGINE.combine(baseline, correlated, k=0.25)["adjusted_prob"]
    high_k = ENGINE.combine(baseline, correlated, k=1.0)["adjusted_prob"]

    # Both above baseline (LRs > 1); more shrinkage (higher k) sits closer to baseline.
    assert baseline < high_k < low_k


def test_k_zero_recovers_full_product():
    baseline, lr1, lr2 = 0.3, 2.0, 3.0
    correlated = [item("biomarker", lr1), item("oncology_subtype", lr2, "immuno_oncology")]
    result = ENGINE.combine(baseline, correlated, k=0.0)

    assert result["adjusted_prob"] == pytest.approx(naive_prob(baseline, lr1, lr2))
    assert all(a["weight"] == 1.0 for a in result["audit"])


def test_correlated_triple_weight():
    """A group of three at k=0.5 gives each member weight 1/(1+0.5*2) = 1/2."""
    trio = [
        item("biomarker", 1.5),
        item("modality", 1.5, "CAR-T"),
        item("oncology_subtype", 1.5, "immuno_oncology"),
    ]
    result = ENGINE.combine(0.3, trio, k=0.5)
    assert all(a["group"] == "precision_medicine" for a in result["audit"])
    assert all(a["weight"] == pytest.approx(0.5) for a in result["audit"])


# --- independent evidence is untouched -------------------------------------

def test_independent_lrs_get_no_dampening():
    """Evidence in different groups keeps weight 1 -> full product, no shrinkage."""
    baseline, lr1, lr2 = 0.3, 2.0, 3.0
    # biomarker -> precision_medicine, rare_disease -> regulatory_facilitation.
    independent = [item("biomarker", lr1), item("rare_disease", lr2)]
    result = ENGINE.combine(baseline, independent, k=0.5)

    assert result["adjusted_prob"] == pytest.approx(naive_prob(baseline, lr1, lr2))
    assert all(a["weight"] == 1.0 for a in result["audit"])
    assert len({a["group"] for a in result["audit"]}) == 2


# --- output always in (0, 1) ----------------------------------------------

def test_extreme_upward_stack_clips_below_one():
    extreme = [item(f"signal_{i}", 50.0) for i in range(10)]  # 10 huge independent LRs
    result = ENGINE.combine(0.5, extreme, k=0.0)
    assert 0.0 < result["adjusted_prob"] < 1.0
    assert result["adjusted_prob"] == pytest.approx(MAX_PROB)


def test_extreme_downward_stack_clips_above_zero():
    extreme = [item(f"signal_{i}", 0.01) for i in range(10)]  # 10 tiny independent LRs
    result = ENGINE.combine(0.5, extreme, k=0.0)
    assert 0.0 < result["adjusted_prob"] < 1.0
    assert result["adjusted_prob"] == pytest.approx(MIN_PROB)


# --- bookkeeping -----------------------------------------------------------

def test_combine_ignores_none_items():
    """None entries (skipped LRs) pass through combine harmlessly."""
    result = ENGINE.combine(0.3, [item("biomarker", 2.0), None, item("rare_disease", 3.0)])
    assert len(result["audit"]) == 2


def test_combine_with_no_evidence_returns_baseline():
    result = ENGINE.combine(0.3, [])
    assert result["adjusted_prob"] == pytest.approx(0.3)
    assert result["audit"] == []


def test_audit_trail_records_each_lr():
    result = ENGINE.combine(0.3, [item("biomarker", 2.0), item("rare_disease", 3.0)])
    audit = result["audit"]
    assert len(audit) == 2
    for entry in audit:
        for field in ("evidence_type", "value", "lr", "weight", "group", "confidence"):
            assert field in entry


def test_combine_with_real_derived_lrs_dampens_precision_pair():
    """End-to-end smoke: biomarker + CAR-T (both precision_medicine) at Phase II->III."""
    bm = ENGINE.lr("biomarker", "phase2_to_3")
    cart = ENGINE.lr("modality", "phase2_to_3", "CAR-T")
    result = ENGINE.combine(0.25, [bm, cart])

    naive = naive_prob(0.25, bm["lr"], cart["lr"])
    assert 0.0 < result["adjusted_prob"] < 1.0
    assert result["adjusted_prob"] < naive  # the pair is dampened
    assert all(a["group"] == "precision_medicine" for a in result["audit"])
