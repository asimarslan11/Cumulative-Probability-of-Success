"""
test_taxonomy.py

Validates the reconciliation of BIO/QLS's 14 disease areas against Wong's 9
therapeutic groups into one canonical enum.

Run with:  python -m pytest tests/test_taxonomy.py -v
"""

import pytest

from pos_engine import load_data
from pos_engine.taxonomy import (
    CANONICAL_DISEASE_AREAS,
    DiseaseArea,
    canonical_to_wong,
    to_canonical,
)

# The disease-area labels actually present in the two source datasets.
DISEASE_PHASE = load_data("raw/baselines_disease_phase.json")
WONG = load_data("raw/wong2019.json")

BIOQLS_LABELS = [k for k in DISEASE_PHASE if not k.startswith("_")]
WONG_GROUPS = [
    k for k in WONG["table2_therapeutic_group"]["all_indications"]
    if k not in ("Overall", "All without oncology")
]


def test_canonical_set_is_15_areas():
    assert len(CANONICAL_DISEASE_AREAS) == 15
    assert set(CANONICAL_DISEASE_AREAS) == {d.value for d in DiseaseArea}


def test_every_bioqls_label_maps_to_a_canonical_area():
    """No orphans: each of BIO/QLS's disease areas resolves to a canonical value."""
    for label in BIOQLS_LABELS:
        result = to_canonical(label, "bioqls")
        assert len(result) == 1
        assert result[0] in CANONICAL_DISEASE_AREAS


def test_every_wong_group_maps_to_canonical_areas():
    """No orphans: each Wong therapeutic group resolves to >=1 canonical value."""
    for group in WONG_GROUPS:
        result = to_canonical(group, "wong")
        assert len(result) >= 1
        for area in result:
            assert area in CANONICAL_DISEASE_AREAS


def test_wong_coarse_merges_are_explicit():
    """The non-trivial many-to-one merges Wong makes."""
    assert to_canonical("Metabolic/Endocrinology", "wong") == ["Metabolic", "Endocrine"]
    assert to_canonical("CNS", "wong") == ["Neurology", "Psychiatry"]
    assert to_canonical("Genitourinary", "wong") == ["Urology"]
    assert to_canonical("Autoimmune/Inflammation", "wong") == ["Autoimmune"]


def test_reverse_mapping_round_trips_for_covered_areas():
    """Canonical -> Wong -> canonical should return the same area (for areas Wong covers)."""
    for area in CANONICAL_DISEASE_AREAS:
        wong_group = canonical_to_wong(area)
        if wong_group is None:
            continue
        assert area in to_canonical(wong_group, "wong")


def test_areas_wong_does_not_cover_map_to_none():
    for area in ("Hematology", "Allergy", "Gastroenterology", "Respiratory", "Others"):
        assert canonical_to_wong(area) is None


def test_lookup_is_case_and_whitespace_insensitive():
    assert to_canonical("  oncology ", "BIO/QLS") == ["Oncology"]
    assert to_canonical("cns", "Wong") == ["Neurology", "Psychiatry"]


def test_unknown_labels_and_sources_raise():
    with pytest.raises(KeyError):
        to_canonical("Podiatry", "bioqls")
    with pytest.raises(KeyError):
        to_canonical("NotAGroup", "wong")
    with pytest.raises(ValueError):
        to_canonical("Oncology", "madeup_source")
