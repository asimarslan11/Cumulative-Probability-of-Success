"""
test_asset.py

Validates the asset input schema: construction, coercion, defaults, validation
errors, and that the committed data/asset_schema.json matches the generator.

Run with:  python -m pytest tests/test_asset.py -v
"""

import pytest

from pos_engine import load_data
from pos_engine.asset import Asset, Modality, Phase, TrialOutcome, build_json_schema
from pos_engine.taxonomy import DiseaseArea


def test_full_asset_constructs_and_coerces_strings():
    a = Asset(
        current_phase="phase2",
        disease_area="Oncology",
        modality="CAR-T",
        biomarker_flag=True,
        rare_disease_flag=True,
        prior_approval_flag=True,
        breakthrough_flag=True,
        trial_outcome="positive",
        lead_indication_flag=True,
    )
    assert a.current_phase is Phase.PHASE_II
    assert a.disease_area is DiseaseArea.ONCOLOGY
    assert a.modality is Modality.CAR_T
    assert a.trial_outcome is TrialOutcome.POSITIVE
    assert a.biomarker_flag is True


def test_minimal_asset_uses_defaults():
    a = Asset(current_phase="phase1")
    assert a.disease_area is None
    assert a.modality is None
    assert a.trial_outcome is TrialOutcome.UNKNOWN
    assert a.biomarker_flag is False
    assert a.lead_indication_flag is False


def test_accepts_enum_members_directly():
    a = Asset(current_phase=Phase.PHASE_III, disease_area=DiseaseArea.HEMATOLOGY,
              modality=Modality.SMALL_MOLECULE, trial_outcome=TrialOutcome.NEGATIVE)
    assert a.current_phase is Phase.PHASE_III
    assert a.modality is Modality.SMALL_MOLECULE


def test_current_phase_is_required():
    with pytest.raises(ValueError):
        Asset(current_phase=None)


def test_invalid_enum_values_raise():
    with pytest.raises(ValueError):
        Asset(current_phase="phase9")
    with pytest.raises(ValueError):
        Asset(current_phase="phase1", disease_area="Podiatry")
    with pytest.raises(ValueError):
        Asset(current_phase="phase1", modality="Telepathy")
    with pytest.raises(ValueError):
        Asset(current_phase="phase1", trial_outcome="great")


def test_non_bool_flag_raises():
    with pytest.raises(TypeError):
        Asset(current_phase="phase1", biomarker_flag="yes")


def test_remaining_transitions_depend_on_current_phase():
    assert Asset(current_phase="phase1").remaining_transitions() == [
        "phase1_to_2", "phase2_to_3", "phase3_to_filing", "filing_to_approval"]
    assert Asset(current_phase="phase3").remaining_transitions() == [
        "phase3_to_filing", "filing_to_approval"]
    assert Asset(current_phase="filing").remaining_transitions() == ["filing_to_approval"]


def test_round_trips_through_dict():
    a = Asset(current_phase="phase2", disease_area="Neurology", modality="Gene therapy",
              breakthrough_flag=True)
    restored = Asset.from_dict(a.to_dict())
    assert restored == a


def test_committed_json_schema_matches_generator():
    """Guard against a stale hand-edited data/asset_schema.json."""
    assert load_data("asset_schema.json") == build_json_schema()


def test_json_schema_lists_all_nine_fields():
    schema = build_json_schema()
    assert set(schema["properties"]) == {
        "current_phase", "disease_area", "modality", "biomarker_flag",
        "rare_disease_flag", "prior_approval_flag", "breakthrough_flag",
        "trial_outcome", "lead_indication_flag",
    }
    assert schema["required"] == ["current_phase"]
