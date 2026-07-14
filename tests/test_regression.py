"""
test_regression.py

Golden-master regression for the engine's end-to-end output. The scenarios in
scripts/build_golden_scenarios.py cover the Day-3 behaviours with no external published
anchor (evidence stacking, the double-count guard, temporality routing, shrinkage), so a
committed snapshot is the only guard against a later refactor silently changing a number.

Two checks, mirroring the baseline_rates "committed matches generator" invariant:
    1. every committed scenario still matches a fresh engine run;
    2. regenerating reproduces the committed file exactly (catches a forgotten rebuild).

Run with:  python -m pytest tests/test_regression.py -v
"""

import importlib.util
import os

import pytest

from pos_engine import load_data
from pos_engine.asset import Asset
from pos_engine.engine import PoSEngine

COMMITTED = load_data("golden_scenarios.json")
ENGINE = PoSEngine()


def _load_builder():
    """Import scripts/build_golden_scenarios.py the same way test_baseline_rates does."""
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                        "scripts", "build_golden_scenarios.py")
    spec = importlib.util.spec_from_file_location("build_golden_scenarios", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_committed_golden_is_non_empty():
    assert COMMITTED, "golden_scenarios.json is empty -- run scripts/build_golden_scenarios.py"


@pytest.mark.parametrize("scenario", COMMITTED, ids=[s["name"] for s in COMMITTED])
def test_committed_scenario_matches_fresh_engine(scenario):
    """Each committed snapshot must equal what the engine produces today."""
    result = ENGINE.compound_pos(Asset(**scenario["asset"]))
    assert result["cumulative_pos"] == pytest.approx(scenario["cumulative_pos"], abs=1e-9)
    for step in result["per_phase"]:
        assert step["adjusted_prob"] == pytest.approx(
            scenario["per_phase_adjusted"][step["phase"]], abs=1e-9)


def test_regenerating_reproduces_committed_file():
    """Regenerating from the builder must reproduce data/golden_scenarios.json exactly
    (guards against a stale committed file after an intended engine change)."""
    regenerated = _load_builder().build()
    assert regenerated == COMMITTED
