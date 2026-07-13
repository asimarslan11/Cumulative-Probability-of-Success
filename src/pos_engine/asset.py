"""
asset.py

The asset input schema: the structured description of a drug development program that
the engine will score (Days 2-3). Day 1 defines and validates it.

Fields (from the brief):
    current_phase        Phase          where the asset is now (required)
    disease_area         DiseaseArea    canonical disease area (optional)
    modality             Modality       drug modality (optional)
    biomarker_flag       bool           patient-preselection biomarker used
    rare_disease_flag    bool           rare / orphan indication
    prior_approval_flag  bool           drug already approved for another indication
    breakthrough_flag    bool           FDA Breakthrough Therapy designation
    trial_outcome        TrialOutcome   latest pivotal trial read-out
    lead_indication_flag bool           this is the drug's lead indication

Strings are accepted and coerced to enums (e.g. "Oncology", "phase2", "positive"), so
callers can build an Asset from JSON without importing the enums.
"""

from dataclasses import asdict, dataclass, field
from enum import Enum

from pos_engine import PHASE_KEYS
from pos_engine.taxonomy import DiseaseArea


class Phase(Enum):
    """The phase the asset is currently in (the starting point for compounding)."""

    PHASE_I = "phase1"
    PHASE_II = "phase2"
    PHASE_III = "phase3"
    FILING = "filing"


class Modality(Enum):
    """Drug modalities as reported in BIO/QLS Figure 10b."""

    CAR_T = "CAR-T"
    SIRNA_RNAI = "siRNA/RNAi"
    MONOCLONAL_ANTIBODY = "Monoclonal antibody"
    ADC = "ADCs"
    GENE_THERAPY = "Gene therapy"
    VACCINE = "Vaccine"
    PROTEIN = "Protein"
    PEPTIDE = "Peptide"
    SMALL_MOLECULE = "Small molecule"
    ANTISENSE = "Antisense"


class TrialOutcome(Enum):
    """Read-out of the asset's latest pivotal trial (BIO/QLS Fig 14 uses trial outcome
    as a predictive feature)."""

    POSITIVE = "positive"
    NEGATIVE = "negative"
    UNKNOWN = "unknown"


# Which phase transitions remain to be compounded, given the current phase (used by
# the Day 3 pipeline; defined here because it is a property of the current_phase field).
_REMAINING_TRANSITIONS = {
    Phase.PHASE_I: PHASE_KEYS[0:],
    Phase.PHASE_II: PHASE_KEYS[1:],
    Phase.PHASE_III: PHASE_KEYS[2:],
    Phase.FILING: PHASE_KEYS[3:],
}


def _coerce(value, enum_cls, field_name, allow_none):
    """Coerce a value into ``enum_cls``, accepting a member, its value, or its name."""
    if value is None:
        if allow_none:
            return None
        raise ValueError(f"{field_name} is required")
    if isinstance(value, enum_cls):
        return value
    if isinstance(value, str):
        # Try by value (e.g. "Oncology", "phase2"), then by NAME (e.g. "ONCOLOGY").
        for member in enum_cls:
            if member.value == value:
                return member
        key = value.strip().upper().replace("-", "_").replace("/", "_").replace(" ", "_")
        if key in enum_cls.__members__:
            return enum_cls[key]
    valid = [m.value for m in enum_cls]
    raise ValueError(f"Invalid {field_name}: {value!r}. Expected one of {valid}"
                     + (" or None" if allow_none else ""))


def _coerce_bool(value, field_name):
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be a bool, got {type(value).__name__}")
    return value


@dataclass
class Asset:
    """A drug development program to be scored. Validates and normalises its fields
    on construction."""

    current_phase: Phase
    disease_area: DiseaseArea = None
    modality: Modality = None
    biomarker_flag: bool = False
    rare_disease_flag: bool = False
    prior_approval_flag: bool = False
    breakthrough_flag: bool = False
    trial_outcome: TrialOutcome = TrialOutcome.UNKNOWN
    lead_indication_flag: bool = False

    def __post_init__(self):
        self.current_phase = _coerce(self.current_phase, Phase, "current_phase", allow_none=False)
        self.disease_area = _coerce(self.disease_area, DiseaseArea, "disease_area", allow_none=True)
        self.modality = _coerce(self.modality, Modality, "modality", allow_none=True)
        self.trial_outcome = _coerce(self.trial_outcome, TrialOutcome, "trial_outcome", allow_none=False)
        for flag in ("biomarker_flag", "rare_disease_flag", "prior_approval_flag",
                     "breakthrough_flag", "lead_indication_flag"):
            setattr(self, flag, _coerce_bool(getattr(self, flag), flag))

    def remaining_transitions(self):
        """The phase transitions still ahead of this asset, to be compounded (Day 3)."""
        return list(_REMAINING_TRANSITIONS[self.current_phase])

    def to_dict(self):
        """Plain JSON-serialisable dict (enum values as strings)."""
        out = asdict(self)
        for key, val in out.items():
            if isinstance(val, Enum):
                out[key] = val.value
        return out

    @classmethod
    def from_dict(cls, data):
        return cls(**data)


def build_json_schema():
    """Return a JSON-Schema (draft-07) description of the asset input, with enum
    options sourced directly from the enums so the doc can never drift from the code."""
    return {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": "iWisdom PoS Engine — Asset Input",
        "description": "Structured description of a drug development program to be scored.",
        "type": "object",
        "required": ["current_phase"],
        "additionalProperties": False,
        "properties": {
            "current_phase": {"type": "string", "enum": [m.value for m in Phase],
                              "description": "Phase the asset is currently in."},
            "disease_area": {"type": ["string", "null"], "enum": [m.value for m in DiseaseArea] + [None],
                             "description": "Canonical disease area (BIO/QLS taxonomy)."},
            "modality": {"type": ["string", "null"], "enum": [m.value for m in Modality] + [None],
                         "description": "Drug modality (BIO/QLS Figure 10b)."},
            "biomarker_flag": {"type": "boolean", "default": False},
            "rare_disease_flag": {"type": "boolean", "default": False},
            "prior_approval_flag": {"type": "boolean", "default": False},
            "breakthrough_flag": {"type": "boolean", "default": False},
            "trial_outcome": {"type": "string", "enum": [m.value for m in TrialOutcome],
                              "default": TrialOutcome.UNKNOWN.value},
            "lead_indication_flag": {"type": "boolean", "default": False},
        },
    }


__all__ = ["Asset", "Phase", "Modality", "TrialOutcome", "build_json_schema"]


if __name__ == "__main__":
    # Regenerate data/asset_schema.json.
    import json
    import os

    from pos_engine import DATA_DIR

    path = os.path.join(DATA_DIR, "asset_schema.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(build_json_schema(), f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"Wrote {path}")
