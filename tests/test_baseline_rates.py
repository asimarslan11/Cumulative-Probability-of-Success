"""
test_baseline_rates.py

Two concerns, both about the canonical consolidated table data/baseline_rates.json:

    1. The table itself: schema completeness, value ranges, provenance, and that the
       committed file still matches what the build script generates.
    2. The BaselineLookup engine that reads it (fallback hierarchy + anchor values).

Run with:  python -m pytest tests/test_baseline_rates.py -v
"""

import importlib.util
import os

from pos_engine import PHASE_KEYS, load_data
from pos_engine.baseline_lookup import BaselineLookup

TABLE = load_data("baseline_rates.json")
ROWS = TABLE["rows"]

REQUIRED_FIELDS = {
    "source", "source_ref", "category_type", "category",
    "phase_transition", "n", "rate", "method",
}
VALID_SOURCES = {"BIO/QLS 2021", "Wong 2019"}
VALID_CATEGORY_TYPES = {
    "disease_area", "modality", "novelty_class", "all_indications",
    "biomarker", "rare_chronic", "oncology_subtype",
    "therapeutic_group", "therapeutic_group_lead", "biomarker_wong", "orphan",
}
VALID_PHASE_TRANSITIONS = set(PHASE_KEYS) | {"phase3_to_approval", "loa"}


# --- table schema & integrity ----------------------------------------------

def test_every_row_has_all_required_fields():
    for r in ROWS:
        assert set(r) == REQUIRED_FIELDS, f"bad fields: {r}"


def test_rates_are_probabilities_and_n_is_positive():
    for r in ROWS:
        assert 0.0 <= r["rate"] <= 1.0, f"rate out of range: {r}"
        assert isinstance(r["n"], int) and r["n"] > 0, f"bad n: {r}"


def test_enumerated_fields_are_valid():
    for r in ROWS:
        assert r["source"] in VALID_SOURCES, r
        assert r["category_type"] in VALID_CATEGORY_TYPES, r
        assert r["phase_transition"] in VALID_PHASE_TRANSITIONS, r
        assert r["method"] in ("phase-by-phase", "path-by-path"), r


def test_row_count_matches_meta():
    assert TABLE["_meta"]["row_count"] == len(ROWS)


def test_bioqls_disease_area_is_15_areas_x_4_phases():
    disease_rows = [r for r in ROWS
                    if r["source"] == "BIO/QLS 2021" and r["category_type"] == "disease_area"]
    assert len(disease_rows) == 15 * 4
    assert all(r["method"] == "phase-by-phase" for r in disease_rows)


def test_wong_rows_use_path_or_phase_method_never_bioqls_filing():
    """Wong must never emit a BIO/QLS-only phase3_to_filing / filing_to_approval row."""
    wong = [r for r in ROWS if r["source"] == "Wong 2019"]
    assert wong, "expected Wong rows"
    for r in wong:
        assert r["phase_transition"] not in ("phase3_to_filing", "filing_to_approval")


def test_spot_rows_match_their_raw_source():
    """A few rows must equal the exact value in the raw per-figure file."""
    def find(source, ctype, category, phase):
        hits = [r for r in ROWS if r["source"] == source and r["category_type"] == ctype
                and r["category"] == category and r["phase_transition"] == phase]
        assert len(hits) == 1, (source, ctype, category, phase, len(hits))
        return hits[0]

    # BIO/QLS Fig 2: Hematology Phase II->III = 48.1%, n=106
    hema = find("BIO/QLS 2021", "disease_area", "Hematology", "phase2_to_3")
    assert hema["rate"] == 0.481 and hema["n"] == 106 and hema["source_ref"] == "Figure 2"
    # BIO/QLS Fig 10b: CAR-T Phase I->II = 44.2%, n=43
    cart = find("BIO/QLS 2021", "modality", "CAR-T", "phase1_to_2")
    assert cart["rate"] == 0.442 and cart["n"] == 43
    # Wong Table 2: oncology overall POS (loa) = 3.4%
    onc = find("Wong 2019", "therapeutic_group", "Oncology", "loa")
    assert onc["rate"] == 0.034 and onc["method"] == "path-by-path"


def test_committed_table_matches_the_build_script():
    """Regenerating from data/raw/ must reproduce the committed rows exactly
    (guards against a stale hand-edited baseline_rates.json)."""
    script_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "scripts", "build_baseline_rates.py"
    )
    spec = importlib.util.spec_from_file_location("build_baseline_rates", script_path)
    build_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build_mod)

    regenerated = build_mod.build()
    assert regenerated["rows"] == ROWS
    assert regenerated["_meta"]["row_count"] == TABLE["_meta"]["row_count"]


# --- BaselineLookup: fallback hierarchy ------------------------------------

def test_hematology_phase2_to_3_matches_figure2():
    """Figure 2: Hematology Phase II->III = 48.1%, n=106 (disease+phase tier)."""
    result = BaselineLookup().get("phase2_to_3", disease="Hematology")
    assert result["rate"] == 0.481
    assert result["n"] == 106
    assert result["source_level"] == "disease+phase"


def test_urology_phase2_to_3_is_lowest():
    """Figure 3: Urology has the lowest Phase II rate (15.0%, n=40)."""
    result = BaselineLookup().get("phase2_to_3", disease="Urology")
    assert result["rate"] == 0.150
    assert result["n"] == 40


def test_all_indications_phase1_to_2_baseline():
    """Figure 1: overall Phase I->II = 52.0%, n=4414 (last-resort tier)."""
    result = BaselineLookup().get("phase1_to_2")
    assert result["rate"] == 0.520
    assert result["n"] == 4414
    assert result["source_level"] == "all_indication"


def test_fallback_disease_beats_modality():
    result = BaselineLookup().get("phase1_to_2", disease="Hematology", modality="CAR-T")
    assert result["source_level"] == "disease+phase"
    assert result["rate"] == 0.696  # Hematology's own rate, not CAR-T's


def test_fallback_modality_beats_novelty_and_all():
    result = BaselineLookup().get(
        "phase1_to_2", disease="NotARealDisease", modality="CAR-T", novelty="Biosimilar"
    )
    assert result["source_level"] == "modality"
    assert result["rate"] == 0.442


def test_fallback_novelty_tier_fires_when_disease_and_modality_miss():
    """The NEW tier: no disease, no modality, but a known novelty class (Fig 9)."""
    result = BaselineLookup().get(
        "phase1_to_2", disease="NotARealDisease", modality=None, novelty="Biosimilar"
    )
    assert result["source_level"] == "novelty_class"
    assert result["rate"] == 0.800  # Fig 9: biosimilar Phase I->II = 80.0%


def test_fallback_lands_on_all_indication_as_last_resort():
    result = BaselineLookup().get(
        "phase2_to_3", disease="NotARealDisease", modality="NotAModality", novelty="NotAClass"
    )
    assert result["source_level"] == "all_indication"
    assert result["rate"] == 0.289


def test_get_returns_provenance():
    result = BaselineLookup().get("phase2_to_3", disease="Hematology")
    assert result["source"] == "BIO/QLS 2021"
    assert result["source_ref"] == "Figure 2"


def test_unknown_phase_raises():
    import pytest
    with pytest.raises(ValueError):
        BaselineLookup().get("phaseX_to_Y", disease="Hematology")
