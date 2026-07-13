# CLAUDE.md

Guidance for working in this repository. Read this before making changes.

## What this is

The **iWisdom PoS Engine**: a transparent, source-grounded engine that estimates the
**cumulative probability of success (PoS)** of a drug development program, from its current
clinical phase through FDA approval. It is a Bayesian-style **odds-adjustment** engine (not
ML, no synthetic data): baseline → odds → likelihood ratios (with shrinkage) → probability,
then **compound** across phases. Every number must trace to a published figure/table — never
invent values.

**Status:** Day 1 (data extraction & architecture) complete; 46 pytest tests pass.
Days 2–5 build the odds engine, pipeline, validation, and packaging on top of the data layer.

## Sources (the only allowed origins of any number)

1. **BIO/QLS Advisors (2021)** — *Clinical Development Success Rates 2011–2020* (phase-by-phase, 4 transitions).
2. **Wong, Siah & Lo (2019)** — *Biostatistics* 20(2), 273–286 (path-by-path, 3 transitions).

⚠️ **The brief and both source PDFs live in a SIBLING folder**, not here:
`../Cumulative-Probability-of-Success/` (README.md = the 5-day plan; `docs/*.pdf` = the sources).
This repo (`pos_engine/`) holds the code and is **not** a git repo yet (Day 5 tags v0.1.0).

## Commands

```bash
python -m pytest                        # full suite (pyproject puts src/ on the path)
python -m pytest tests/test_wong.py -v   # one file
python scripts/build_baseline_rates.py   # regenerate data/baseline_rates.json from data/raw/
```

Python ≥ 3.10. Engine uses **stdlib only**; `pytest` is the sole dev dependency.

## Architecture & data flow

```
data/raw/*.json  ──►  scripts/build_baseline_rates.py  ──►  data/baseline_rates.json
(provenance, per-figure)         (deterministic)              (CANONICAL — engine reads only this)
```

- `data/baseline_rates.json` is the engine's **single source of truth** (long-format rows:
  `source, source_ref, category_type, category, phase_transition, n, rate, method`). It is
  **generated** — never hand-edit it; edit the raw files and regenerate. A test asserts the
  committed file matches the generator.
- `src/pos_engine/baseline_lookup.py` — `BaselineLookup.get(phase, disease, modality, novelty)`,
  a **4-tier fallback**: disease+phase → modality → novelty_class → all-indications
  (see `docs/fallback_hierarchy.md`).
- `src/pos_engine/taxonomy.py` — canonical `DiseaseArea` enum + `to_canonical(name, source)`.
- `src/pos_engine/asset.py` — the `Asset` input schema (dataclass + enums + validation);
  `data/asset_schema.json` is generated from it.

## Key decisions / gotchas (don't relearn these the hard way)

- **Wong is deliberately OUT of the live fallback chain.** `get()` uses only BIO/QLS rows
  (phase-by-phase, 4 transitions). Wong is path-by-path and merges filing+approval into one
  `phase3_to_approval` step, so its rows are stored for Day-4 cross-validation only. **Never map
  Wong `pos3_app` to BIO/QLS `phase3_to_filing`.**
- **Modifiers ≠ baselines.** `biomarker`, `rare_chronic`, `oncology_subtype` (BIO/QLS Fig 11/8b/7)
  live in the table but are **not** fallback tiers — Day 2 turns them into likelihood ratios.
- **Documented discrepancy, do not "fix":** Wong's text says POS₂,₃ = 58.3%, but its tables say
  48.6% (58.3% is the Infectious-disease value). We record 48.6% as authoritative and flag it in
  `data/raw/wong2019.json` `_meta.known_discrepancy`.
- **N.A. cells** (tiny-sample Wong rows) are `null` in JSON and skipped by the build script.
- All 7 original BIO/QLS `data/raw/baselines_*.json` were verified against the source figures.

## Conventions

- Each new capability ships with pytest coverage; tests anchor on values traceable to a specific
  figure/table (cite the figure in the test docstring).
- Generated artifacts (`baseline_rates.json`, `asset_schema.json`) must be reproducible and are
  guarded by a "committed file matches generator" test — keep that invariant.
- Match the existing style: plain stdlib, explanatory docstrings that cite sources, no new deps
  without a strong reason.

## Roadmap (from the sibling README's 5-day plan)

- **Day 2** — `prob_to_odds`/`odds_to_prob`; derive a likelihood ratio per evidence type from
  published contrasts (biomarker, rare, modality, novelty, prior-approval proxy, Fig-14 items);
  shrinkage for correlated evidence.
- **Day 3** — `select_baseline` + `adjust_phase_probability` + `compound_pos`; per-phase audit trail;
  move tunables to a config file.
- **Day 4** — validate against published benchmarks (Fig 5b LOAs, Fig 10b modality, biomarker ~2×,
  Wong Table 1/2); regression tests; shrinkage sensitivity sweep.
- **Day 5** — methodology docs + limitations, installable package with `calculate_pos(asset)` API,
  CLI/notebook demo, tag v0.1.0.
