"""
build_baseline_rates.py

Consolidates every per-figure/per-table raw file under data/raw/ into ONE canonical
long-format table, data/baseline_rates.json, which is the engine's sole runtime data
source.

Each output row has the fields:

    source            "BIO/QLS 2021" | "Wong 2019"
    source_ref        exact figure/table, e.g. "Figure 2", "Table 2 (all indications)"
    category_type     disease_area | modality | novelty_class | all_indications
                      | biomarker | rare_chronic | oncology_subtype
                      | therapeutic_group | therapeutic_group_lead
                      | biomarker_wong | orphan
    category          the specific bucket, e.g. "Hematology", "CAR-T", "Oncology: with_biomarker"
    phase_transition  phase1_to_2 | phase2_to_3 | phase3_to_filing | filing_to_approval
                      | phase3_to_approval (Wong, combines filing+approval) | loa
    n                 advanced+suspended transitions (BIO/QLS) or development paths (Wong)
    rate              probability in [0, 1]
    method            "phase-by-phase" (BIO/QLS) | "path-by-path" (Wong headline)

Run:  python scripts/build_baseline_rates.py
The output is deterministic (rows sorted, no timestamps) so re-running never churns the file.
"""

import json
import os
import sys

# Make the pos_engine package importable when run as a plain script.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "src"))

from pos_engine import DATA_DIR, PHASE_KEYS, load_data  # noqa: E402

OUTPUT_PATH = os.path.join(DATA_DIR, "baseline_rates.json")

# BIO/QLS raw file -> (category_type, source_ref). All are phase-by-phase, 4 phases.
BIOQLS_FILES = {
    "baselines_disease_phase.json": ("disease_area", "Figure 2"),
    "baselines_modality.json": ("modality", "Figure 10b"),
    "baselines_novelty.json": ("novelty_class", "Figure 9"),
    "baselines_biomarker.json": ("biomarker", "Figure 11"),
    "baselines_rare_chronic.json": ("rare_chronic", "Figure 8b"),
    "baselines_oncology_subtype.json": ("oncology_subtype", "Figure 7"),
    "baselines_all_indications.json": ("all_indications", "Figure 1"),
}

# Wong stores 3 transitions + loa; map its keys -> (canonical phase_transition, count key).
WONG_PHASES = [
    ("pos1_2", "phase1_to_2", "phase1"),
    ("pos2_3", "phase2_to_3", "phase2"),
    ("pos3_app", "phase3_to_approval", "phase3"),  # NOT phase3_to_filing: Wong merges filing+approval
]


def _row(source, source_ref, category_type, category, phase_transition, n, rate, method):
    return {
        "source": source,
        "source_ref": source_ref,
        "category_type": category_type,
        "category": category,
        "phase_transition": phase_transition,
        "n": n,
        "rate": rate,
        "method": method,
    }


def build_bioqls_rows():
    rows = []
    for fname, (category_type, ref) in BIOQLS_FILES.items():
        data = load_data(f"raw/{fname}")
        for category, phases in data.items():
            if category.startswith("_"):
                continue
            for phase in PHASE_KEYS:
                entry = phases.get(phase)
                if not entry:
                    continue
                rows.append(_row(
                    "BIO/QLS 2021", ref, category_type, category, phase,
                    entry["n"], entry["pos"], "phase-by-phase",
                ))
    return rows


def _wong_group_rows(vals, source_ref, category_type, category, counts_key, method):
    """Emit phase + loa rows for one Wong group entry, skipping null / zero-n cells."""
    rows = []
    counts = vals[counts_key]
    for wong_key, phase_transition, count_field in WONG_PHASES:
        rate = vals.get(wong_key)
        n = counts.get(count_field, 0)
        if rate is None or n == 0:
            continue
        rows.append(_row("Wong 2019", source_ref, category_type, category,
                         phase_transition, n, rate, method))
    # loa (POS1,APP): denominator is the Phase-1 entry cohort.
    if vals.get("loa") is not None and counts.get("phase1", 0) > 0:
        rows.append(_row("Wong 2019", source_ref, category_type, category,
                         "loa", counts["phase1"], vals["loa"], method))
    return rows


def build_wong_rows():
    rows = []
    w = load_data("raw/wong2019.json")

    # Table 2 — therapeutic groups (all & lead indications), path-by-path.
    for subset, category_type in (("all_indications", "therapeutic_group"),
                                  ("lead_indications", "therapeutic_group_lead")):
        ref = f"Table 2 ({subset.replace('_', ' ')})"
        for group, vals in w["table2_therapeutic_group"][subset].items():
            rows += _wong_group_rows(vals, ref, category_type, group, "total_paths", "path-by-path")

    # Table 3 — biomarkers (phase-by-phase). Category encodes group + biomarker status.
    for group, statuses in w["table3_biomarker"].items():
        if group.startswith("_") or not isinstance(statuses, dict):
            continue  # skip scalar metadata keys (method, time_window, ...)
        for status, vals in statuses.items():
            category = f"{group}: {status}"
            rows += _wong_group_rows(vals, "Table 3", "biomarker_wong", category,
                                     "total_transitions", "phase-by-phase")

    # Table 4 — orphan drugs, path-by-path.
    for group, vals in w["table4_orphan"].items():
        if group.startswith("_") or not isinstance(vals, dict):
            continue  # skip scalar metadata keys (method, sample, ...)
        rows += _wong_group_rows(vals, "Table 4", "orphan", group, "total_paths", "path-by-path")

    return rows


def build():
    rows = build_bioqls_rows() + build_wong_rows()
    # Deterministic ordering so regeneration never churns the file.
    rows.sort(key=lambda r: (r["source"], r["category_type"], r["category"], r["phase_transition"]))

    return {
        "_meta": {
            "description": (
                "Canonical long-format baseline table. GENERATED by "
                "scripts/build_baseline_rates.py from data/raw/*.json — do not edit by hand; "
                "edit the raw files and regenerate."
            ),
            "row_fields": [
                "source", "source_ref", "category_type", "category",
                "phase_transition", "n", "rate", "method",
            ],
            "sources": ["BIO/QLS 2021", "Wong 2019"],
            "phase_transition_notes": (
                "BIO/QLS uses four transitions (phase1_to_2, phase2_to_3, phase3_to_filing, "
                "filing_to_approval), phase-by-phase. Wong uses three (phase1_to_2, phase2_to_3, "
                "phase3_to_approval — the last merges filing+approval), path-by-path, plus 'loa' "
                "(overall Phase 1 -> Approval). Wong and BIO/QLS rows are NOT interchangeable at "
                "phase3; the engine's default fallback uses only BIO/QLS phase-by-phase rows."
            ),
            "row_count": len(rows),
        },
        "rows": rows,
    }


def main():
    table = build()
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(table, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"Wrote {table['_meta']['row_count']} rows to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
