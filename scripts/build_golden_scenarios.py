"""
build_golden_scenarios.py

Regenerates data/golden_scenarios.json: a golden-master snapshot of the engine's output
for a fixed set of representative assets. These scenarios exercise the Day-3 pipeline
behaviours that have NO external published anchor (evidence stacking, the double-count
guard, temporality routing, correlation-group shrinkage), so a committed snapshot is the
only way to catch a later refactor silently changing a number.

tests/test_regression.py asserts (a) the committed file still matches a fresh engine run,
and (b) regenerating reproduces the committed file exactly -- the same "committed matches
generator" invariant as build_baseline_rates.py.

Run:  python scripts/build_golden_scenarios.py
Deterministic (engine is pure; values rounded to 10 dp) so re-running never churns the file.
"""

import json
import os
import sys

# Make the pos_engine package importable when run as a plain script.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "src"))

from pos_engine import DATA_DIR  # noqa: E402
from pos_engine.asset import Asset  # noqa: E402
from pos_engine.engine import PoSEngine  # noqa: E402

OUTPUT_PATH = os.path.join(DATA_DIR, "golden_scenarios.json")

# Each scenario is a (name, asset-kwargs) pair chosen to cover a distinct engine behaviour.
SCENARIOS = [
    ("bare_phase1",
     {"current_phase": "phase1"}),
    ("oncology_biomarker_phase1",
     {"current_phase": "phase1", "disease_area": "Oncology", "biomarker_flag": True}),
    ("cart_no_disease_phase1",  # baseline falls back to modality tier -> double-count guard
     {"current_phase": "phase1", "modality": "CAR-T"}),
    ("oncology_cart_biomarker_phase1",  # precision-medicine shrinkage pair (biomarker + CAR-T)
     {"current_phase": "phase1", "disease_area": "Oncology", "modality": "CAR-T",
      "biomarker_flag": True}),
    ("phase3_breakthrough_prior_approval",  # regulatory temporality on the late transitions
     {"current_phase": "phase3", "disease_area": "Oncology", "breakthrough_flag": True,
      "prior_approval_flag": True}),
    ("phase2_positive_trial",  # trial_outcome routes to the next transition only
     {"current_phase": "phase2", "disease_area": "Neurology", "trial_outcome": "positive"}),
    ("lead_indication_phase1",  # Wong proxy LR, capped to the two early transitions
     {"current_phase": "phase1", "lead_indication_flag": True}),
    ("rare_disease_hematology_phase1",
     {"current_phase": "phase1", "disease_area": "Hematology", "rare_disease_flag": True}),
    ("full_stack_from_filing",
     {"current_phase": "filing", "disease_area": "Oncology", "biomarker_flag": True,
      "breakthrough_flag": True, "prior_approval_flag": True}),
    ("full_stack_from_phase1",  # every signal on at once, from the earliest phase
     {"current_phase": "phase1", "disease_area": "Autoimmune", "modality": "Monoclonal antibody",
      "biomarker_flag": True, "breakthrough_flag": True, "prior_approval_flag": True,
      "trial_outcome": "positive", "lead_indication_flag": True}),
]


def build():
    """Run every scenario through the engine and return the snapshot list."""
    engine = PoSEngine()
    out = []
    for name, kwargs in SCENARIOS:
        result = engine.compound_pos(Asset(**kwargs))
        out.append({
            "name": name,
            "asset": kwargs,
            "cumulative_pos": round(result["cumulative_pos"], 10),
            "per_phase_adjusted": {
                step["phase"]: round(step["adjusted_prob"], 10)
                for step in result["per_phase"]
            },
        })
    return out


def main():
    scenarios = build()
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(scenarios, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"Wrote {len(scenarios)} golden scenarios to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
