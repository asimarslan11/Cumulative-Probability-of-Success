"""
test_benchmarks.py

Day-4 validation: does the engine reproduce the sources' own published likelihood-of-
approval (LOA) figures? Two tiers (see docs/validation.md):

    Tier A -- internal consistency (tight). Compounding BIO transition rates must
              reproduce BIO's independently-published LOA (Fig 5b / 10b / 11). This is
              a transcription-integrity check: one mis-keyed rate breaks the product.
    Tier B -- mechanism & cross-source (loose). The biomarker LR machinery reproduces
              Fig 11's ~2x lift, and disease LOAs agree DIRECTIONALLY with Wong (a
              different study/method, so no exact match is expected).

Published values live in data/raw/benchmarks_bioqls.json (provenance-tagged).

Note on tolerance: the engine clips probabilities to [0.1%, 99%], so where a source
NDA/BLA cell is 100% the engine reports 99%. Phase-I LOA absorbs this in the third
decimal (worst observed 0.0014), so disease/modality checks use abs=0.003.

Run with:  python -m pytest tests/test_benchmarks.py -v
"""

from functools import reduce

import pytest

from pos_engine import PHASE_KEYS, load_data
from pos_engine.asset import Asset
from pos_engine.engine import PoSEngine

ENGINE = PoSEngine()
BENCH = load_data("raw/benchmarks_bioqls.json")
WONG = load_data("raw/wong2019.json")

# BIO rows indexed for direct path products (the biomarker path check works on rates,
# since biomarker is a modifier, not a baseline tier the engine compounds).
_BIO = {
    (r["category_type"], r["category"], r["phase_transition"]): r
    for r in load_data("baseline_rates.json")["rows"]
    if r["source"] == "BIO/QLS 2021"
}


def _path_product(category_type, category):
    """Compound the four BIO transition rates for one category (no engine clipping)."""
    return reduce(lambda a, b: a * b,
                  (_BIO[(category_type, category, p)]["rate"] for p in PHASE_KEYS))


_DISEASES = [d for d in BENCH["fig5b_loa"] if not d.startswith("_") and d != "all_indications"]
_MODALITIES = [m for m in BENCH["fig10b_modality_loa"] if not m.startswith("_")]


# --- Tier A: engine compounding reproduces published LOA --------------------

@pytest.mark.parametrize("start", ["phase1", "phase2", "phase3", "filing"])
def test_all_indications_loa_by_start_phase_matches_fig5b(start):
    """Fig 5b, all indications: LOA from Phase I/II/III/NDA = 7.9/15.1/52.4/90.6%.
    No 100% cells here, so the match is exact to rounding."""
    published = BENCH["fig5b_loa"]["all_indications"][start]
    got = ENGINE.compound_pos(Asset(current_phase=start))["cumulative_pos"]
    assert got == pytest.approx(published, abs=0.002)


@pytest.mark.parametrize("disease", _DISEASES)
def test_disease_phase1_loa_matches_fig5b(disease):
    """Fig 5b: every disease's LOA from Phase I equals the compounded disease baselines."""
    published = BENCH["fig5b_loa"][disease]["phase1"]
    got = ENGINE.compound_pos(Asset(current_phase="phase1", disease_area=disease))["cumulative_pos"]
    assert got == pytest.approx(published, abs=0.003)


@pytest.mark.parametrize("modality", _MODALITIES)
def test_modality_phase1_loa_matches_fig10b(modality):
    """Fig 10b: every modality's LOA from Phase I equals the compounded modality baselines."""
    published = BENCH["fig10b_modality_loa"][modality]
    got = ENGINE.compound_pos(Asset(current_phase="phase1", modality=modality))["cumulative_pos"]
    assert got == pytest.approx(published, abs=0.003)


def test_biomarker_paths_compound_to_fig11_loa():
    """Fig 11: the with- and without-biomarker phase rates compound to LOA 15.9% / 7.6%.
    Validates the Fig-11 transition rates transcription against its own published LOA."""
    fig11 = BENCH["fig11_biomarker_loa"]
    assert _path_product("biomarker", "with_biomarker") == pytest.approx(
        fig11["with_biomarker"]["phase1"], abs=0.002)
    assert _path_product("biomarker", "without_biomarker") == pytest.approx(
        fig11["without_biomarker"]["phase1"], abs=0.002)


# --- Tier B: LR mechanism (biomarker ~2x) -----------------------------------

def test_biomarker_lr_mechanism_roughly_doubles_loa():
    """Fig 11 headline: biomarkers ~double the LOA. Applying the biomarker *LR* on the
    all-indications baseline (odds -> LR -> compound, not re-multiplication) reproduces
    the with-biomarker path (~15.9%) within ~1.5pp and lifts the 7.9% baseline ~2x."""
    base = ENGINE.compound_pos(Asset(current_phase="phase1"))["cumulative_pos"]
    with_bm = ENGINE.compound_pos(Asset(current_phase="phase1", biomarker_flag=True))["cumulative_pos"]
    published_with = BENCH["fig11_biomarker_loa"]["with_biomarker"]["phase1"]
    assert with_bm == pytest.approx(published_with, abs=0.015)
    assert 1.9 <= with_bm / base <= 2.2


# --- Tier B: Wong cross-source (loose / directional) ------------------------

def test_wong_overall_loa_same_order_of_magnitude():
    """Cross-source sanity: Wong (2000-2015, path-by-path) reports overall LOA 13.8%;
    the engine (BIO 2011-2020, phase-by-phase) gives 7.9%. Different study and method,
    so only order-of-magnitude agreement is expected -- not equality."""
    engine_overall = ENGINE.compound_pos(Asset(current_phase="phase1"))["cumulative_pos"]
    wong_overall = WONG["table1_aggregate"]["this_study_all_indications"]["loa"]
    assert 0.5 <= wong_overall / engine_overall <= 3.0


def test_oncology_ranks_in_bottom_tier_in_both_sources():
    """Both sources place Oncology among the lowest-LOA disease areas."""
    eng = {d: ENGINE.compound_pos(Asset(current_phase="phase1", disease_area=d))["cumulative_pos"]
           for d in _DISEASES}
    median = sorted(eng.values())[len(eng) // 2]
    assert eng["Oncology"] < median

    wong_t2 = WONG["table2_therapeutic_group"]["all_indications"]
    aggregates = {"Overall", "All without oncology"}
    others = [v["loa"] for k, v in wong_t2.items()
              if not k.startswith("_") and k not in aggregates | {"Oncology"}
              and isinstance(v, dict) and v.get("loa") is not None]
    assert wong_t2["Oncology"]["loa"] <= min(others)
