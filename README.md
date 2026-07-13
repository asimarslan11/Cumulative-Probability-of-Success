# iWisdom PoS Engine

A transparent, source-grounded engine that estimates the **cumulative probability of
success (PoS)** of a drug development program, from its current clinical phase through to
FDA approval.

Rather than training a machine-learning model on synthetic data — which would look
sophisticated but wouldn't be scientifically defensible given we only have *aggregated*
statistics, not row-level trial data — this is a Bayesian-style **odds-adjustment**
engine. For each phase transition it (1) selects the most specific reliable baseline via a
fallback hierarchy, (2) converts it to odds, (3) applies likelihood ratios for the asset's
evidence (with shrinkage so correlated evidence isn't double-counted), and (4) converts
back to a probability. Adjusted phase probabilities are then **compounded** to a cumulative
PoS. Every number traces to a published figure or table — no invented values.

> **Status:** Day 1 (data extraction & architecture) complete. Days 2–5 build the odds
> engine, pipeline, validation, and packaging on top of this data layer.

## Sources

All baselines and likelihood ratios derive from two published sources:

1. **BIO, QLS Advisors, Informa Pharma Intelligence (2021).** *Clinical Development
   Success Rates and Contributing Factors 2011–2020.*
2. **Wong, C.H., Siah, K.W., Lo, A.W. (2019).** *Estimation of clinical trial success
   rates and related parameters.* *Biostatistics* 20(2), 273–286.
   doi:10.1093/biostatistics/kxx069

## Layout

```
data/
  baseline_rates.json    canonical long-format table — the engine's ONLY runtime data source
  taxonomy.json          canonical disease-area enum + BIO/QLS <-> Wong mapping
  asset_schema.json      JSON-Schema for the asset input (generated)
  raw/                   provenance inputs (per-figure BIO/QLS files + Wong tables)
docs/
  fallback_hierarchy.md  the baseline-selection specification
scripts/
  build_baseline_rates.py  regenerates data/baseline_rates.json from data/raw/
src/pos_engine/
  baseline_lookup.py     BaselineLookup: 4-tier fallback baseline selector
  taxonomy.py            DiseaseArea enum + to_canonical()
  asset.py               Asset schema (dataclass + enums + validation)
tests/                   pytest suite (data anchors + engine behaviour)
```

Data provenance flows `data/raw/*.json` → `scripts/build_baseline_rates.py` →
`data/baseline_rates.json`. The raw files are the audit trail; the engine reads only the
generated canonical table.

## Baseline fallback hierarchy

Most specific → most general (see [docs/fallback_hierarchy.md](docs/fallback_hierarchy.md)):

1. **disease + phase** (BIO/QLS Fig 2) → 2. **modality** (Fig 10b) →
3. **novelty class** (Fig 9) → 4. **all-indications** (Fig 1)

```python
from pos_engine.baseline_lookup import BaselineLookup

BaselineLookup().get("phase2_to_3", disease="Hematology")
# {'rate': 0.481, 'n': 106, 'source': 'BIO/QLS 2021', 'source_ref': 'Figure 2',
#  'source_level': 'disease+phase', 'source_key': 'Hematology'}
```

## Running

Requires Python ≥ 3.10. The engine itself uses only the standard library; `pytest` is the
only dev dependency.

```bash
# optional: create a virtual environment
python -m venv .venv && source .venv/Scripts/activate   # Windows Git Bash

pip install -r requirements.txt          # installs pytest
python -m pytest                         # run the full suite
python scripts/build_baseline_rates.py   # regenerate the canonical table from data/raw/
```

`pyproject.toml` puts `src/` on the path for pytest, so tests `import pos_engine` directly.
