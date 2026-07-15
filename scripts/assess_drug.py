"""
assess_drug.py

Score a named drug / vaccine program and print a critical paragraph. No UI: a name goes in,
prose comes out.

    python scripts/assess_drug.py "EXAMPLE-001"

The name is resolved against data/drug_registry.json. Because neither source contains any
per-drug data, a name that isn't registered cannot be scored from the name alone -- supply
its attributes instead (at minimum the phase), and they'll be used for this run only:

    python scripts/assess_drug.py "Some Program" --phase phase2 --disease Oncology \
        --modality "Monoclonal antibody" --biomarker

Flags override registry values, which is the right way to correct a stale current_phase
without editing the file.

    --list      show every registered name
    --json      emit the full audit trail as JSON instead of prose
"""

import argparse
import json
import os
import sys

# Make the pos_engine package importable when run as a plain script.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "src"))

from pos_engine.asset import DiseaseArea, Modality, Phase, TrialOutcome  # noqa: E402
from pos_engine.config import EngineConfig  # noqa: E402
from pos_engine.engine import PoSEngine  # noqa: E402
from pos_engine.registry import UnknownAssetError, known_names  # noqa: E402
from pos_engine.report import assess  # noqa: E402


def build_parser():
    p = argparse.ArgumentParser(
        prog="assess_drug.py",
        description="Estimate a drug/vaccine program's cumulative probability of success "
                    "and explain, critically, how much to trust it.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("name", nargs="?", help="drug or vaccine name (see --list)")
    p.add_argument("--list", action="store_true", help="list registered names and exit")
    p.add_argument("--json", action="store_true", help="emit the full audit trail as JSON")
    p.add_argument("-k", type=float, default=None,
                   help="shrinkage strength override (default: config's 0.5)")

    a = p.add_argument_group("attributes (override the registry, or score an unregistered name)")
    a.add_argument("--phase", choices=[m.value for m in Phase],
                   help="current phase -- required for an unregistered name")
    a.add_argument("--disease", choices=[m.value for m in DiseaseArea], metavar="AREA",
                   help="canonical disease area")
    a.add_argument("--modality", choices=[m.value for m in Modality], metavar="MODALITY",
                   help="drug modality")
    a.add_argument("--trial-outcome", choices=[m.value for m in TrialOutcome],
                   help="latest pivotal read-out")
    for flag, helptext in [
        ("biomarker", "patient-preselection biomarker used"),
        ("rare-disease", "rare / orphan indication"),
        ("prior-approval", "already approved for another indication"),
        ("breakthrough", "FDA Breakthrough Therapy designation"),
        ("lead-indication", "this is the drug's lead indication"),
    ]:
        a.add_argument(f"--{flag}", action="store_true", default=None, help=helptext)
    return p


def overrides_from_args(args):
    """Only pass through what the user actually set; None means 'don't override'."""
    return {
        "current_phase": args.phase,
        "disease_area": args.disease,
        "modality": args.modality,
        "trial_outcome": args.trial_outcome,
        "biomarker_flag": args.biomarker,
        "rare_disease_flag": args.rare_disease,
        "prior_approval_flag": args.prior_approval,
        "breakthrough_flag": args.breakthrough,
        "lead_indication_flag": args.lead_indication,
    }


def main(argv=None):
    args = build_parser().parse_args(argv)

    if args.list:
        for name in known_names():
            print(name)
        return 0

    if not args.name:
        build_parser().print_usage()
        print("\nerror: a name is required (or use --list)", file=sys.stderr)
        return 2

    engine = PoSEngine(EngineConfig(k=args.k)) if args.k is not None else PoSEngine()
    try:
        assessment = assess(args.name, overrides_from_args(args), engine=engine)
    except UnknownAssetError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except (ValueError, TypeError) as exc:  # invalid attribute values
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps({k: v for k, v in assessment.items()}, indent=2, ensure_ascii=False))
    else:
        print(assessment["paragraph"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
