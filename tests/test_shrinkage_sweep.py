"""
test_shrinkage_sweep.py

Day-4 sensitivity analysis of the one free parameter, the shrinkage strength k. Every
other number in the engine is pinned to a published contrast; k is a modelling choice, so
it gets a sweep over {0, 0.25, 0.5, 1} (the range the plan calls out) with the properties
we rely on asserted, not just eyeballed.

The correlated stack is a biomarker + CAR-T program (both members of the precision_medicine
correlation group). CAR-T's small-n late cells (n=3, n=4) fall below MIN_ARM_N, so the LR is
derived only at the early transitions -- at Phase II->III both the biomarker and CAR-T LRs
are > 1 and share a group, which is exactly where shrinkage should bite.

Run with:  python -m pytest tests/test_shrinkage_sweep.py -v
"""

import pytest

from pos_engine.asset import Asset
from pos_engine.config import EngineConfig
from pos_engine.engine import PoSEngine

K_VALUES = [0.0, 0.25, 0.5, 1.0]

# Oncology keeps the baseline at the disease tier, so the CAR-T modality LR is applied
# (not dropped by the double-count guard) and can share the precision_medicine group with
# the biomarker LR. Starting at Phase II isolates the correlated pair to a single
# transition (Phase II->III), so the compound's dependence on k is unambiguous.
CORRELATED = dict(current_phase="phase2", disease_area="Oncology",
                  modality="CAR-T", biomarker_flag=True)


def _compound(asset_kwargs, k):
    return PoSEngine(EngineConfig(k=k)).compound_pos(Asset(**asset_kwargs))["cumulative_pos"]


def _correlated_audit(k, phase="phase2_to_3"):
    step = PoSEngine(EngineConfig(k=k)).adjust_phase_probability(Asset(**CORRELATED), phase)
    return [a for a in step["audit"] if a["group"] == "precision_medicine"]


def test_correlated_stack_compound_is_monotonic_in_k():
    """More shrinkage (higher k) pulls a correlated, positive stack back toward the
    baseline, so the cumulative PoS strictly decreases across the sweep."""
    vals = [_compound(CORRELATED, k) for k in K_VALUES]
    assert all(a > b for a, b in zip(vals, vals[1:])), vals


def test_phase_adjusted_is_monotonic_in_k():
    """At Phase II->III both LRs are > 1 and correlated, so the adjusted probability
    strictly decreases as k increases."""
    vals = [PoSEngine(EngineConfig(k=k)).adjust_phase_probability(
        Asset(**CORRELATED), "phase2_to_3")["adjusted_prob"] for k in K_VALUES]
    assert all(a > b for a, b in zip(vals, vals[1:])), vals


def test_single_evidence_is_k_invariant():
    """A singleton correlation group has weight 1 for every k, so k must not move a
    single-evidence result at all."""
    solo = dict(current_phase="phase1", disease_area="Oncology", biomarker_flag=True)
    vals = [_compound(solo, k) for k in K_VALUES]
    assert all(v == pytest.approx(vals[0], abs=1e-12) for v in vals)


def test_k_zero_is_the_naive_product():
    """k=0 disables shrinkage: every correlated LR keeps weight 1 (full-strength product)."""
    correlated = _correlated_audit(0.0)
    assert len(correlated) >= 2  # biomarker + CAR-T both present at Phase II->III
    assert all(a["weight"] == pytest.approx(1.0) for a in correlated)


def test_positive_k_dampens_correlated_weights():
    """k>0 down-weights each member of a correlation group of size m>1: w = 1/(1+k(m-1))."""
    for k in (0.25, 0.5, 1.0):
        correlated = _correlated_audit(k)
        expected = 1.0 / (1.0 + k * (len(correlated) - 1))
        assert all(a["weight"] == pytest.approx(expected) for a in correlated)
        assert all(a["weight"] < 1.0 for a in correlated)
