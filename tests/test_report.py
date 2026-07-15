"""
test_report.py

The name -> asset resolution (registry) and the critical-paragraph renderer.

The paragraph is the only part of this project a non-technical reader will actually read,
so these tests pin the things that make it *critical* rather than merely descriptive: it
must disclose a weak baseline, flag illustrative and proxy likelihood ratios, admit signals
it silently dropped, and never present an unregistered name as if it had been looked up.

Run with:  python -m pytest tests/test_report.py -v
"""

import pytest

from pos_engine.engine import PoSEngine
from pos_engine.registry import UnknownAssetError, known_names, resolve
from pos_engine.report import assess

ENGINE = PoSEngine()


def _paragraph(name, **overrides):
    return assess(name, overrides, engine=ENGINE)["paragraph"]


# --- registry resolution ---------------------------------------------------

def test_registry_resolves_known_name_case_insensitively():
    kwargs, prov = resolve("example-001")
    assert kwargs["current_phase"] == "phase2"
    assert prov["registered"] is True
    assert prov["resolved_name"] == "EXAMPLE-001"


def test_registry_entry_carries_provenance():
    """Every entry must say where its attributes came from and when -- they are declared
    inputs, not source data."""
    _, prov = resolve("EXAMPLE-001")
    assert prov["_source"] and prov["_as_of"]


def test_provenance_keys_are_not_passed_to_asset():
    """_source/_as_of are provenance, not Asset fields; leaking them would raise."""
    kwargs, _ = resolve("EXAMPLE-001")
    assert not [k for k in kwargs if k.startswith("_")]


def test_unknown_name_without_attributes_fails_loudly():
    """A name alone cannot be scored: the sources have no per-drug data. Failing beats
    quietly returning an industry average under a drug's name."""
    with pytest.raises(UnknownAssetError) as exc:
        resolve("Definitely Not A Registered Drug")
    message = str(exc.value)
    assert "not in the registry" in message
    assert "EXAMPLE-001" in message  # tells you what it does know


def test_unknown_name_with_supplied_phase_resolves_as_unregistered():
    kwargs, prov = resolve("Ad-hoc Program", {"current_phase": "phase2"})
    assert kwargs["current_phase"] == "phase2"
    assert prov["registered"] is False


def test_overrides_beat_registry_values():
    """The documented way to correct a stale current_phase without editing the file."""
    kwargs, prov = resolve("EXAMPLE-001", {"current_phase": "phase3"})
    assert kwargs["current_phase"] == "phase3"
    assert kwargs["disease_area"] == "Oncology"  # untouched
    assert prov["overridden_fields"] == ["current_phase"]


def test_known_names_includes_the_demo_entry():
    assert "EXAMPLE-001" in known_names()


# --- the paragraph states the estimate -------------------------------------

def test_paragraph_reports_pos_and_reference_class():
    """The comparator is the same starting phase -- comparing a Phase-III asset to the
    Phase-I industry average would flatter it just for having survived."""
    out = assess("Bare", {"current_phase": "phase3"}, engine=ENGINE)
    assert out["reference_pos"] == pytest.approx(0.524, abs=0.002)
    assert "52.4%" in out["paragraph"]
    assert "Phase III" in out["paragraph"]


def test_paragraph_names_the_programme():
    assert _paragraph("Bare Program", current_phase="phase2").startswith("Bare Program")


# --- the paragraph is CRITICAL ---------------------------------------------

def test_paragraph_flags_all_indications_fallback():
    """No disease/modality -> baselines are the industry average; say so plainly."""
    text = _paragraph("Nothing Specific", current_phase="phase3")
    assert "weakly specific" in text
    assert "industry base rate" in text


def test_paragraph_credits_disease_specific_grounding():
    text = _paragraph("Onc Program", current_phase="phase2", disease_area="Oncology")
    assert "Oncology-specific baselines" in text


def test_paragraph_flags_illustrative_fig14_evidence():
    """Breakthrough is a Fig-14 single-example LR; a reader must be told to discount it."""
    text = _paragraph("BT Program", current_phase="phase3",
                      disease_area="Oncology", breakthrough_flag=True)
    assert "Figure 14" in text
    assert "caution" in text


def test_paragraph_flags_wong_proxy_evidence():
    text = _paragraph("Lead Program", current_phase="phase1",
                      disease_area="Oncology", lead_indication_flag=True)
    assert "proxy" in text and "Wong" in text


def test_paragraph_discloses_dropped_signals():
    """CAR-T's late cells are below MIN_ARM_N, so the modality LR silently vanishes there.
    The paragraph must admit it rather than let the reader assume it was applied."""
    text = _paragraph("CAR-T Program", current_phase="phase1",
                      disease_area="Oncology", modality="CAR-T")
    assert "could not be honoured" in text
    assert "absent rather than counted as neutral" in text


def test_dropped_signal_does_not_assert_a_single_cause():
    """lr() returns None both for unpublished contrasts and small arms; the audit can't
    tell them apart, so the prose must not claim one."""
    text = _paragraph("CAR-T Program", current_phase="phase1",
                      disease_area="Oncology", modality="CAR-T")
    assert "either the source does not report it there, or the arm is too small" in text


def test_paragraph_notes_the_double_count_guard_on_modality_tier():
    text = _paragraph("Vax", current_phase="phase1", modality="Vaccine")
    assert "withheld" in text


def test_paragraph_reports_clipping_when_it_bites():
    """Allergy's NDA/BLA cell is a published 100% (Fig 2, n=20); the engine clips it to
    99%, and the paragraph must surface that a guard rail -- not the data -- set the number."""
    text = _paragraph("Allergy Program", current_phase="filing", disease_area="Allergy")
    assert "clip" in text and "guard rail" in text
    assert "NDA/BLA->approval" in text


def test_clip_blames_the_baseline_not_evidence_when_there_is_no_evidence():
    """Allergy-from-filing clips with NO evidence applied: the published cell is itself
    100%. Blaming an 'evidence stack' there would be plainly false."""
    text = _paragraph("Allergy Program", current_phase="filing", disease_area="Allergy")
    assert "the published baseline at NDA/BLA->approval is itself 100.0%" in text
    assert "evidence stack" not in text


def test_clip_blames_the_stack_when_evidence_pushes_past_the_ceiling():
    """The other cause: a stacked-evidence program whose adjusted probability exceeds 99%."""
    text = assess("EXAMPLE-001", engine=ENGINE)["paragraph"]
    assert "evidence stack pushes" in text


def test_paragraph_flags_runtime_attributes_as_unaudited():
    text = _paragraph("Ad-hoc", current_phase="phase2")
    assert "supplied at run time" in text


def test_paragraph_flags_registry_attributes_as_declared_input():
    text = assess("EXAMPLE-001", engine=ENGINE)["paragraph"]
    assert "declared input" in text
    assert "no per-drug data" in text or "per-drug data" in text


def test_paragraph_always_carries_the_reference_class_caveat():
    """Every paragraph, no matter how favourable, must refuse to be read as a prediction."""
    for overrides in ({"current_phase": "phase1"},
                      {"current_phase": "filing", "disease_area": "Hematology"}):
        text = _paragraph("X", **overrides)
        assert "reference class, not a prediction" in text
