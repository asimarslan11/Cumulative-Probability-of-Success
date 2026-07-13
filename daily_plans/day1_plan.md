# Day 1 — Data Extraction & Architecture (iWisdom PoS Engine)

## Context

We are building the **iWisdom PoS Engine**: a transparent, Bayesian-style odds-adjustment
tool that computes a drug program's cumulative probability of success (PoS) from its current
clinical phase through FDA approval. Every number must trace to one of two published sources
(no invented figures):

- **BIO/QLS Advisors (2021)** — *Clinical Development Success Rates 2011–2020*
- **Wong, Siah & Lo (2019)** — *Biostatistics* 20(2), 273–286

The brief lives in `../Cumulative-Probability-of-Success/README.md`; both source PDFs are now
provided in-context, so **no PDF-parsing library or network install is needed** — the tables are
transcribed directly.

**Current state (partial Day 1 done):** `pos_engine/` has 7 per-figure BIO/QLS JSON tables in
`data/`, a `BaselineLookup` class with a 3-tier fallback, and passing pytest tests. I
cross-checked **all 7 files against the source figures — every value is accurate** (Fig 2, 7, 8b,
9, 10b, 11). Missing Day 1 items: Wong et al. tables, taxonomy reconciliation, the single
consolidated table, the novelty fallback tier, the asset schema, and repo scaffolding.

**Confirmed decisions:**
1. **Refactor to one canonical `baseline_rates.json`** as the engine's sole runtime data source;
   rewrite `baseline_lookup` + tests to read it. The 7 per-figure JSONs + a new Wong file are
   demoted to auditable provenance inputs under `data/raw/` (not read at runtime).
2. **Transcribe directly from the in-context PDFs** (both fully verified), rather than installing
   a PDF tool.

**Outcome:** a package-structured repo whose engine reads one provenance-tagged long-format table
(BIO/QLS + Wong), with a reconciled disease taxonomy, a validated asset schema, a written 4-tier
fallback spec, and full pytest coverage — the foundation Days 2–5 build on.

---

## Target layout

```
pos_engine/
  README.md                     # NEW  stub: description + both citations + how to run
  pyproject.toml                # NEW  project meta + pytest config (pythonpath=src)
  requirements.txt              # NEW  pytest only (no PDF deps)
  .gitignore                    # NEW  .venv, __pycache__, *.pyc
  data/
    baseline_rates.json         # NEW  CANONICAL long-format table (engine reads only this)
    taxonomy.json               # NEW  canonical enum + BIO/QLS<->canonical<->Wong mapping
    asset_schema.json           # NEW  JSON-Schema doc of the asset input
    raw/                        # provenance inputs to the build script (not runtime)
      baselines_*.json          # MOVED here (the 7 existing, verified files)
      wong2019.json             # NEW  Wong Tables 1-4, transcribed + verified
  docs/
    fallback_hierarchy.md       # NEW  written 4-tier spec
  scripts/
    build_baseline_rates.py     # NEW  raw/*.json -> canonical baseline_rates.json (reproducible)
  src/pos_engine/
    __init__.py                 # NEW  public API surface + project-root/data path helper
    baseline_lookup.py          # REWRITE  reads baseline_rates.json, 4-tier fallback
    taxonomy.py                 # NEW  canonical enum + to_canonical(name, source)
    asset.py                    # NEW  Asset dataclass + enums + validation
  tests/
    test_baseline_rates.py      # REWRITE of test_baselines.py (schema + anchors + fallback)
    test_wong.py                # NEW  Wong anchors
    test_taxonomy.py            # NEW  mapping completeness/round-trip
    test_asset.py               # NEW  schema validation
```

---

## Canonical `baseline_rates.json` schema (long format)

One row per published rate; engine indexes rows by `(source, category_type, category, phase_transition)`.

```json
{
  "source": "BIO/QLS 2021",          // or "Wong 2019"
  "source_ref": "Figure 2",           // exact figure/table
  "category_type": "disease_area",    // disease_area | modality | novelty_class | all_indications
                                      // | biomarker | rare_chronic | oncology_subtype
                                      // | therapeutic_group | orphan
  "category": "Hematology",           // the specific bucket (or "all_indications")
  "phase_transition": "phase2_to_3",  // phase1_to_2|phase2_to_3|phase3_to_filing|filing_to_approval|"loa"
  "n": 106,
  "rate": 0.481,
  "method": "phase-by-phase"          // BIO/QLS = phase-by-phase; Wong = path-by-path (or its own phase-by-phase)
}
```

Wong phase-key mapping: P1→P2 = `phase1_to_2`, P2→P3 = `phase2_to_3`, P3→NDA/BLA(APP) =
`phase3_to_filing`, plus overall `POS1,APP` → `phase_transition:"loa"`. Documented in a `_meta` header.

---

## Wong et al. numbers to transcribe (from the in-context tables)

**Table 2 — all-indications, path-by-path (9 therapeutic groups)** — `POS1,2 / POS2,3 / POS3,APP / LOA`:
- Oncology 57.6 / 32.7 / 35.5 / **3.4**; Metabolic-Endocrinology 76.2 / 59.7 / 51.6 / 19.6;
  Cardiovascular 73.3 / 65.7 / 62.2 / 25.5; CNS 73.2 / 51.9 / 51.1 / 15.0;
  Autoimmune-Inflammation 69.8 / 45.7 / 63.7 / 15.1; Genitourinary 68.7 / 57.1 / 66.5 / 21.6;
  Infectious disease 70.1 / 58.3 / 75.3 / 25.2; Ophthalmology 87.1 / 60.7 / 74.9 / 32.6;
  Vaccines(ID) 76.8 / 58.2 / 85.4 / 33.4; **Overall 66.4 / 48.6 / 59.0 / 13.8**;
  All-without-oncology 73.0 / 55.7 / 63.6 / 20.9. (SEs + total-paths captured too.)
- **Table 3 — biomarker (phase-by-phase), Overall:** no-biomarker 34.7 / 26.8 / 59.0 / **5.5**;
  with-biomarker 44.5 / 38.6 / 60.2 / **10.3** (+ per-group rows, e.g. oncology 1.6% vs 10.7%).
- **Table 4 — orphan (path-by-path), Overall:** 75.9 / 48.8 / 46.7 / **6.2**;
  all-except-oncology 81.5 / 59.2 / 66.3 / 13.6.
- **Documented discrepancy:** the paper's *text/abstract* says "POS₂,₃ = 58.3%", but Table 1/2
  overall POS₂,₃ is **48.6%** (58.3% is actually the Infectious-disease group value). Record the
  table value as authoritative and note this in `_meta` (this is the "document, don't silently
  reconcile" item the brief calls for on Day 4).

---

## Taxonomy reconciliation (`taxonomy.json` + `taxonomy.py`)

Canonical enum = union of areas, with an explicit many-to-one mapping. Non-trivial merges Wong makes:
- Wong **Metabolic/Endocrinology** ← BIO/QLS *Metabolic* + *Endocrine*
- Wong **CNS** ← BIO/QLS *Neurology* + *Psychiatry*
- Wong **Genitourinary** ← BIO/QLS *Urology*
- Wong **Autoimmune/Inflammation** ← BIO/QLS *Autoimmune*
- Direct: Oncology, Cardiovascular, Infectious disease, Ophthalmology.
- BIO/QLS-only (no Wong group): Hematology, Allergy, Gastroenterology, Respiratory, Others.

`to_canonical(name, source)` maps either taxonomy's label to a canonical value; unmapped/ambiguous
cases documented, not guessed.

---

## Fallback hierarchy (spec — `docs/fallback_hierarchy.md`)

Most specific → most general; the tier that fires is always logged:
1. **disease + phase** (BIO/QLS Fig 2 — default, phase-by-phase for method consistency)
2. **modality** (BIO/QLS Fig 10b)
3. **novelty class** (BIO/QLS Fig 9) — *new tier, missing from current code*
4. **all-indications** (BIO/QLS Fig 1) — always available, last resort

`biomarker`, `rare_chronic`, `oncology_subtype`, and all Wong rows live in the table but are **not**
in this chain (Wong is kept for Day-4 cross-validation; modifiers become LRs on Day 2). `get()`
returns `{rate, n, source, source_ref, source_level}`.

---

## Implementation order (each step ships with its pytest)

**Step 0 — Scaffolding.** `pyproject.toml` (`[tool.pytest.ini_options] pythonpath=["src"]`),
`requirements.txt` (pytest), `.gitignore`, `src/pos_engine/` package, optional `.venv`. Confirm
`python -m pytest` runs. Move the 7 `data/baselines_*.json` into `data/raw/`.

**Step 1 — Wong extraction.** Author `data/raw/wong2019.json` (Tables 1–4 + `_meta` noting
path-by-path vs phase-by-phase and the 58.3%/48.6% discrepancy). → `tests/test_wong.py` asserts
LOA 13.8%, oncology 3.4%, biomarker 10.3% vs 5.5%, orphan 6.2%.

**Step 2 — Taxonomy.** `data/taxonomy.json` + `src/pos_engine/taxonomy.py`. →
`tests/test_taxonomy.py`: every BIO/QLS + Wong label maps to a canonical value; the documented
merges hold; no orphans.

**Step 3 — Consolidated table.** `scripts/build_baseline_rates.py` reads `data/raw/*.json`, emits
`data/baseline_rates.json`. → tests: every row has all fields, `0 ≤ rate ≤ 1`, `n > 0`, row count
matches sources, spot rows equal their raw source.

**Step 4 — Rewrite lookup (4-tier).** Rewrite `baseline_lookup.py` to load `baseline_rates.json`,
index rows, and walk disease+phase → modality → **novelty** → all-indications. Preserve existing
anchor assertions (Hematology 0.481/106, Urology 0.150/40, CAR-T 0.442/43, all-ind 0.520/4414,
fallback ordering) and add a novelty-tier test.

**Step 5 — Asset schema.** `src/pos_engine/asset.py`: `Asset` dataclass + enums (`Phase`,
`DiseaseArea`, `Modality`, `TrialOutcome`) + validation for the 9 brief fields. Stdlib only. Emit
`data/asset_schema.json`. → `tests/test_asset.py`: valid asset builds; bad phase/enum raises;
flag defaults correct.

**Step 6 — Docs.** `docs/fallback_hierarchy.md` + `README.md` stub (description, both citations,
layout, `python -m pytest`).

---

## Verification

- `python -m pytest -v` from `pos_engine/` — all green (existing anchors preserved + new
  Wong/taxonomy/asset/novelty tests).
- `python scripts/build_baseline_rates.py` regenerates `data/baseline_rates.json` deterministically.
- Manual smoke: `BaselineLookup().get("phase2_to_3", disease="Hematology")` → 0.481/n=106/
  `disease+phase`; unknown disease + `novelty="Biosimilar"` fires the novelty tier; unknown
  everything falls to `all_indications`.

## Notes

- Engine's default fallback uses BIO/QLS (phase-by-phase) for method consistency; Wong
  (path-by-path) is stored for Day-4 cross-validation, not mixed into the live chain.
- `pos_engine/` is not a git repo (the sibling brief folder is). I can `git init` here on request;
  deferred unless wanted now (Day 5 tags v0.1.0).
