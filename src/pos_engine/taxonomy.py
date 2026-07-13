"""
taxonomy.py

Reconciles the two source taxonomies into one canonical disease-area enum with an
explicit mapping table (Day 1 deliverable).

    - BIO/QLS (2021) reports 14 major disease areas + "Others" (the canonical set).
    - Wong (2019) reports 9 (coarser) therapeutic groups.

A single Wong group can cover several canonical areas (e.g. Wong "CNS" =
Neurology + Psychiatry), so lookups return a *list* of canonical areas.

Public API:
    DiseaseArea                 canonical enum (15 members)
    CANONICAL_DISEASE_AREAS     list of canonical strings
    to_canonical(name, source)  map a source label -> [canonical, ...]
    canonical_to_wong(name)     map a canonical area -> its Wong group (or None)
"""

from enum import Enum

from pos_engine import load_data

_TAX = load_data("taxonomy.json")

_BIOQLS_TO_CANONICAL = _TAX["bioqls_to_canonical"]
_WONG_TO_CANONICAL = _TAX["wong_to_canonical"]
_CANONICAL_TO_WONG = _TAX["canonical_to_wong"]

CANONICAL_DISEASE_AREAS = list(_TAX["canonical_disease_areas"])


class DiseaseArea(Enum):
    """The canonical disease areas (BIO/QLS's 14 major areas + Others)."""

    ALLERGY = "Allergy"
    AUTOIMMUNE = "Autoimmune"
    CARDIOVASCULAR = "Cardiovascular"
    ENDOCRINE = "Endocrine"
    GASTROENTEROLOGY = "Gastroenterology"
    HEMATOLOGY = "Hematology"
    INFECTIOUS_DISEASE = "Infectious disease"
    METABOLIC = "Metabolic"
    NEUROLOGY = "Neurology"
    ONCOLOGY = "Oncology"
    OPHTHALMOLOGY = "Ophthalmology"
    PSYCHIATRY = "Psychiatry"
    RESPIRATORY = "Respiratory"
    UROLOGY = "Urology"
    OTHERS = "Others"


# Guard: the data file and the enum must not drift apart.
assert CANONICAL_DISEASE_AREAS == [d.value for d in DiseaseArea], (
    "taxonomy.json canonical_disease_areas is out of sync with the DiseaseArea enum"
)

_VALID_SOURCES = {"bioqls", "bio/qls", "bio/qls 2021", "bio", "qls", "wong", "wong 2019"}


def _norm(label):
    """Normalise whitespace and case for forgiving lookups."""
    return " ".join(str(label).strip().split()).lower()


_BIOQLS_CI = {_norm(k): v for k, v in _BIOQLS_TO_CANONICAL.items()}
_WONG_CI = {_norm(k): v for k, v in _WONG_TO_CANONICAL.items()}
_CANONICAL_CI = {_norm(k): k for k in CANONICAL_DISEASE_AREAS}


def to_canonical(name, source):
    """Map a source disease/therapeutic-group label to canonical area(s).

    Returns a list of canonical strings (length 1 for BIO/QLS; 1+ for Wong,
    since Wong's groups can be coarser). Raises KeyError on an unknown label
    and ValueError on an unknown source.
    """
    src = _norm(source)
    key = _norm(name)

    if src in ("bioqls", "bio/qls", "bio/qls 2021", "bio", "qls"):
        if key not in _BIOQLS_CI:
            raise KeyError(f"Unknown BIO/QLS disease area: {name!r}")
        return [_BIOQLS_CI[key]]

    if src in ("wong", "wong 2019"):
        if key not in _WONG_CI:
            raise KeyError(f"Unknown Wong therapeutic group: {name!r}")
        return list(_WONG_CI[key])

    raise ValueError(f"Unknown source {source!r}; expected one of {sorted(_VALID_SOURCES)}")


def canonical_to_wong(name):
    """Map a canonical disease area to its Wong therapeutic group, or None if
    Wong does not report that area separately (Hematology, Allergy,
    Gastroenterology, Respiratory, Others)."""
    key = _norm(name)
    if key not in _CANONICAL_CI:
        raise KeyError(f"Unknown canonical disease area: {name!r}")
    return _CANONICAL_TO_WONG[_CANONICAL_CI[key]]


__all__ = [
    "DiseaseArea",
    "CANONICAL_DISEASE_AREAS",
    "to_canonical",
    "canonical_to_wong",
]
