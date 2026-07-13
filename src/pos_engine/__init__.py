"""
pos_engine
==========

The iWisdom PoS Engine: a transparent, source-grounded estimator of the cumulative
probability of success (PoS) of a drug development program, from its current clinical
phase through FDA approval.

Every baseline rate traces back to a specific figure or table in one of two published
sources (see the README):

    - BIO/QLS Advisors (2021), Clinical Development Success Rates 2011-2020
    - Wong, Siah & Lo (2019), Biostatistics 20(2)

Day 1 exposes the data layer only:

    - PHASE_KEYS               the four canonical phase transitions, in order
    - load_data(filename)      load a JSON file from the package's data/ folder
    - DATA_DIR                 absolute path to the data/ folder
    - BaselineLookup           the fallback-hierarchy baseline selector (Step 4)
    - to_canonical, DiseaseArea, ... taxonomy helpers (Step 2)
    - Asset, Phase, Modality, TrialOutcome  the asset input schema (Step 5)
"""

import json
import os

# Project root is two levels up from this file: src/pos_engine/__init__.py -> project root.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(_THIS_DIR))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")

# The four phase transitions we track, in order, from Phase I to Approval.
PHASE_KEYS = ["phase1_to_2", "phase2_to_3", "phase3_to_filing", "filing_to_approval"]


def load_data(filename):
    """Load one JSON file from the package's ``data/`` folder.

    ``filename`` may be a bare name ("baseline_rates.json") or a relative path
    inside data/ ("raw/wong2019.json").
    """
    path = os.path.join(DATA_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


__all__ = [
    "PROJECT_ROOT",
    "DATA_DIR",
    "PHASE_KEYS",
    "load_data",
]
