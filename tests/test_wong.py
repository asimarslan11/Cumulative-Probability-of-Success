"""
test_wong.py

Validates that our transcription of Wong, Siah & Lo (2019) reproduces numbers we
can point to directly in the paper (Tables 1-4) and in the README's cited anchors.

Run with:  python -m pytest tests/test_wong.py -v
"""

from pos_engine import load_data

WONG = load_data("raw/wong2019.json")


def _approx(a, b, tol=0.0005):
    return abs(a - b) <= tol


# --- Table 1 / 2: aggregate all-indications path-by-path -------------------

def test_overall_loa_is_13_8_percent():
    """Abstract & Table 1/2: overall path-by-path LOA (POS1,APP) = 13.8%."""
    assert WONG["table1_aggregate"]["this_study_all_indications"]["loa"] == 0.138
    assert WONG["table2_therapeutic_group"]["all_indications"]["Overall"]["loa"] == 0.138


def test_table1_and_table2_overall_agree():
    """The aggregate row in Table 1 must match the Overall row in Table 2."""
    t1 = WONG["table1_aggregate"]["this_study_all_indications"]
    t2 = WONG["table2_therapeutic_group"]["all_indications"]["Overall"]
    for key in ("pos1_2", "pos2_3", "pos3_app", "loa"):
        assert t1[key] == t2[key]


def test_documented_pos2_3_discrepancy():
    """The paper's text says 58.3%, but the authoritative table value is 48.6%.
    We record 0.486 and flag the discrepancy in _meta."""
    assert WONG["table2_therapeutic_group"]["all_indications"]["Overall"]["pos2_3"] == 0.486
    assert "58.3" in WONG["_meta"]["known_discrepancy"]
    # 58.3% is really the Infectious-disease group value:
    assert WONG["table2_therapeutic_group"]["all_indications"]["Infectious disease"]["pos2_3"] == 0.583


def test_prior_literature_columns_are_internally_consistent():
    """Each phase-by-phase comparison row: loa == pos1_2 * pos2_3 * pos3_app."""
    prior = WONG["table1_aggregate"]["prior_literature_phase_by_phase"]
    for name, row in prior.items():
        if name.startswith("_"):
            continue
        product = row["pos1_2"] * row["pos2_3"] * row["pos3_app"]
        assert _approx(product, row["loa"], tol=0.002), f"{name}: {product} vs {row['loa']}"


# --- Table 2: therapeutic groups -------------------------------------------

def test_oncology_overall_pos_is_lowest_at_3_4_percent():
    """Table 2 / README: oncology overall POS = 3.4%, the minimum across groups."""
    groups = WONG["table2_therapeutic_group"]["all_indications"]
    assert groups["Oncology"]["loa"] == 0.034
    loas = [v["loa"] for k, v in groups.items()
            if k not in ("Overall", "All without oncology")]
    assert min(loas) == 0.034


def test_vaccines_have_highest_group_pos():
    """Table 2: vaccines (infectious disease) have the max overall POS at 33.4%."""
    groups = WONG["table2_therapeutic_group"]["all_indications"]
    loas = {k: v["loa"] for k, v in groups.items()
            if k not in ("Overall", "All without oncology")}
    assert max(loas, key=loas.get) == "Vaccines (Infectious Disease)"
    assert loas["Vaccines (Infectious Disease)"] == 0.334


def test_wong_has_nine_therapeutic_groups():
    """The README reconciles BIO/QLS's 14 areas against Wong's 9 therapeutic groups."""
    groups = WONG["table2_therapeutic_group"]["all_indications"]
    real_groups = [k for k in groups if k not in ("Overall", "All without oncology")]
    assert len(real_groups) == 9


# --- Table 3: biomarkers ----------------------------------------------------

def test_biomarker_overall_10_3_vs_5_5():
    """Table 3 / README: biomarker trials ~2x overall POS (10.3% vs 5.5%)."""
    overall = WONG["table3_biomarker"]["Overall"]
    assert overall["with_biomarker"]["loa"] == 0.103
    assert overall["no_biomarker"]["loa"] == 0.055
    assert overall["with_biomarker"]["loa"] > overall["no_biomarker"]["loa"]


def test_biomarker_effect_strongest_in_oncology():
    """Table 3: oncology biomarker LOA (10.7%) dwarfs no-biomarker (1.6%)."""
    onc = WONG["table3_biomarker"]["Oncology"]
    assert onc["with_biomarker"]["loa"] == 0.107
    assert onc["no_biomarker"]["loa"] == 0.016


def test_biomarker_na_cells_are_null():
    """Very-small-sample cells (e.g. Genitourinary with-biomarker) are recorded as null."""
    gu = WONG["table3_biomarker"]["Genitourinary"]["with_biomarker"]
    assert gu["loa"] is None
    assert gu["total_transitions"]["phase2"] == 0


# --- Table 4: orphan drugs --------------------------------------------------

def test_orphan_overall_is_6_2_percent():
    """Table 4: orphan-drug overall POS = 6.2%, rising to 13.6% excluding oncology."""
    assert WONG["table4_orphan"]["Overall"]["loa"] == 0.062
    assert WONG["table4_orphan"]["All except oncology"]["loa"] == 0.136
