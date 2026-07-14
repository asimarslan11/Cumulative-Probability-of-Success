# Day 4 — Validation, Regression & Shrinkage Sensitivity

> Days 1–3 are complete: data layer, odds engine, likelihood ratios, and the per-phase
> pipeline (`PoSEngine.compound_pos`), 111 tests passing. Day 4 adds **no new engine
> behaviour**. It proves the outputs are right against the published figures, locks them with
> regression tests, and probes the one free parameter (shrinkage `k`).

## Context

The engine now produces a cumulative PoS with a full audit trail. Day 4 answers three
questions: (1) *Is it correct?* — does compounding reproduce the sources' own published
likelihood-of-approval (LOA) figures? (2) *Is it stable?* — will a later refactor silently
change a number? (3) *How sensitive is it to `k`?* — the shrinkage strength is the only knob
not pinned to a published contrast, so it deserves a sweep.

I verified all the headline checks while planning (numbers below are real, from the engine
against the extracted figures) — Day 4 is about turning those into committed, provenance-
grounded tests.

**Confirmed decisions:**

1. **Published benchmarks are transcribed into `data/raw/benchmarks_bioqls.json`** (Fig 5b,
   10b, 11), each value tagged with its figure — the same provenance pattern as the
   `baselines_*.json` raw files. Validation tests read it; it is **not** engine input and
   **not** part of the `baseline_rates.json` build.
2. **A golden-master `data/golden_scenarios.json`** snapshots representative `asset → PoS`
   outputs for the multi-evidence scenarios that have **no published anchor**, guarded by a
   "committed file matches engine" test — the same invariant as the `baseline_rates`
   generator test.
3. **Wong is cross-source and validated *loosely*.** Different study window (2000–2015 vs
   BIO's 2011–2020), method (path-by-path vs phase-by-phase), and taxonomy mean the numbers
   are **not** expected to match. Wong checks are directional / order-of-magnitude only, and
   the known divergences are **documented, not "fixed"** (see §Tier B).

## Two tiers of validation

**Tier A — internal consistency (tight, exact).** The engine compounds BIO transition rates;
it must reproduce BIO's own published LOA. This is *not* tautological: it is a
**transcription-integrity check** that all four stored rates for a category jointly reproduce
the *independently* published LOA — one mis-keyed rate would break the product. Verified:

| Check (source) | Published | Engine | Result |
|---|---|---|---|
| All-indications LOA, Phase I / II / III / NDA (Fig 5b) | 7.9 / 15.1 / 52.4 / 90.6 % | 7.9 / 15.1 / 52.4 / 90.6 % | exact |
| Disease LOA from Phase I (Fig 5b): Onc / Cardio / Hem / Metab | 5.3 / 4.8 / 23.9 / 15.5 % | 5.3 / 4.8 / 23.9 / 15.5 % | exact |
| Modality LOA from Phase I (Fig 10b): CAR-T / mAb / small-mol / antisense | 17.3 / 12.1 / 7.5 / 5.2 % | 17.3 / 12.1 / 7.5 / 5.2 % | exact |
| Biomarker path LOA, with / without (Fig 11) | 15.9 / 7.6 % | 15.9 / 7.6 % | exact |

**Tier B — mechanism & cross-source (loose).** Does the *LR machinery* (odds → LR → compound),
not just re-multiplication, land in the right place?

- **Biomarker ~2× (Fig 11).** Applying the biomarker **LR** on top of the all-indications
  baseline gives **16.3%** vs the independently-computed with-biomarker path of **15.9%**, a
  **2.07×** lift over the 7.9% baseline — matching the report's "biomarkers roughly double
  LOA". The ~0.4pp gap is expected: the LR moves a baseline in odds space rather than
  recomputing the path, so this is a genuine end-to-end check, not by-construction.
- **Wong cross-source.** Engine disease LOAs agree with Wong Table 2 for some areas and
  diverge sharply for others (Cardiovascular: engine 4.8% vs Wong 25.5%; Ophthalmology 11.9%
  vs 32.6%). Day 4 asserts only **directional** agreement (both rank Oncology in the bottom
  tier; overall LOAs are the same order of magnitude) and **records the divergences** in
  `docs/validation.md` with their cause.

## New files

```
data/raw/benchmarks_bioqls.json     transcribed Fig 5b / 10b / 11 published LOAs (provenance)
data/golden_scenarios.json          committed asset -> PoS snapshots (regression)
scripts/build_golden_scenarios.py   regenerates the golden file from the engine (deterministic)
docs/validation.md                  results write-up: benchmark tables, k-sweep, documented divergences
tests/test_benchmarks.py            Tier-A (Fig 5b/10b/11) + Tier-B (biomarker mechanism, Wong)
tests/test_regression.py            golden-master "committed matches engine" test
tests/test_shrinkage_sweep.py       k in {0, 0.25, 0.5, 1} sensitivity + monotonicity
```

No engine or `config.py` changes are required — `EngineConfig(k=...)` (built Day 3) already
makes the sweep possible without touching code.

## 1. `data/raw/benchmarks_bioqls.json`

Three provenance-tagged blocks, transcribed from the figures (values already extracted):

```jsonc
{
  "fig5b_loa": {                    // LOA by disease, by starting phase
    "_ref": "BIO/QLS 2021 Figure 5b",
    "all_indications": {"phase1": 0.079, "phase2": 0.151, "phase3": 0.524, "filing": 0.906, "n": 12728},
    "Oncology":        {"phase1": 0.053, "phase2": 0.108, "phase3": 0.439, "filing": 0.920, "n": 4179},
    "Hematology":      {"phase1": 0.239, "phase2": 0.344, "phase3": 0.715, "filing": 0.931, "n": 352},
    // ... all 15 disease rows
  },
  "fig10b_modality_loa": {          // LOA from Phase I by modality
    "_ref": "BIO/QLS 2021 Figure 10b",
    "CAR-T": 0.173, "siRNA/RNAi": 0.135, "Monoclonal antibody": 0.121, "ADCs": 0.108,
    "Gene therapy": 0.100, "Vaccine": 0.097, "Protein": 0.094, "Peptide": 0.080,
    "Small molecule": 0.075, "Antisense": 0.052
  },
  "fig11_biomarker_loa": {          // biomarker path LOA, with vs without
    "_ref": "BIO/QLS 2021 Figure 11",
    "with_biomarker":    {"phase1": 0.159, "phase2": 0.303, "phase3": 0.655, "filing": 0.960},
    "without_biomarker": {"phase1": 0.076, "phase2": 0.146, "phase3": 0.515, "filing": 0.903}
  }
}
```

Hand-transcribed like the other `raw/` files (no generator, so no generator-match test); each
block carries its `_ref`.

## 2. `tests/test_benchmarks.py`

**Tier A** (parametrised, `abs=0.003` for published rounding):
- Every disease's LOA from Phase I equals `fig5b_loa[disease]["phase1"]` (15 cases).
- All-indications LOA from each starting phase equals the Fig 5b row (4 cases).
- Every modality's compounded LOA equals `fig10b_modality_loa` (10 cases).
- `with_/without_biomarker` compounded paths equal the Fig 11 LOAs.

**Tier B** (loose):
- Biomarker LR on the all-indications baseline is within ~1.5pp of Fig 11's 15.9% and lifts
  the 7.9% baseline by a ratio in `[1.9, 2.2]`.
- Wong directional: engine and Wong both place Oncology in the lowest-LOA tier; engine overall
  (7.9%) and Wong overall (13.8%) are within one order of magnitude.

## 3. `tests/test_regression.py` + `scripts/build_golden_scenarios.py`

`build_golden_scenarios.py` runs a fixed list of ~10 assets through `compound_pos` and writes
`{asset, cumulative_pos, per_phase_adjusted}` to `data/golden_scenarios.json`. Scenarios span
the Day-3 behaviours that have no external anchor:

- bare Phase-I; Oncology + biomarker; CAR-T no-disease (modality-tier baseline → double-count
  guard fires); Oncology + CAR-T + biomarker (precision-medicine shrinkage pair); Phase-III +
  breakthrough + prior_approval (regulatory temporality); positive trial-outcome (next-only);
  lead-indication Phase-I; full stack from filing.

The test asserts (a) each committed `cumulative_pos` matches a fresh engine run to `1e-9`, and
(b) regenerating equals the committed file — so forgetting to rebuild after an intended change
fails loudly, exactly like the `baseline_rates` invariant.

## 4. `tests/test_shrinkage_sweep.py`

On a fixed correlated-evidence asset (Oncology + biomarker + CAR-T — both precision-medicine):
- **Monotonic dampening:** `cumulative_pos` strictly decreases as `k` goes `0 → 0.25 → 0.5 → 1`
  (both LRs > 1 and correlated, so more shrinkage pulls back toward baseline).
- **k = 0 = naive product:** matches applying both LRs at full strength.
- **Single-evidence is k-invariant:** a biomarker-only asset gives the same PoS at every `k`
  (a singleton group has weight 1 regardless of `k`).
- Emits the sweep table consumed by `docs/validation.md`.

## 5. `docs/validation.md`

The results write-up (sibling to `pipeline.md`): the Tier-A benchmark table (engine vs
published), the Tier-B biomarker-mechanism note (16.3% vs 15.9%, why approximate), the Wong
cross-source table with **documented divergences and their cause** (window / method /
taxonomy), and the `k`-sweep table with the recommendation to keep `k = 0.5` as the default.
This is also the seed of Day 5's methodology doc.

## Verification

- `python -m pytest -v` — all green (existing 111 + new benchmark / regression / sweep tests).
- Benchmark values spot-checked against the extracted figures; golden regeneration is
  deterministic (`build_golden_scenarios.py` twice → identical file).
- Engine remains stdlib-only.

## Notes / boundaries (kept for Day 5)

- **`pypdf` was used once as a transcription aid** to read the published figures out of the
  source PDF; the extracted values are committed as data in `benchmarks_bioqls.json`. It is
  **not** an engine or test dependency — the engine stays stdlib-only.
- **Day 5** packages the public `calculate_pos(asset)` API + CLI/notebook demo, expands
  `validation.md` into the full methodology + limitations doc, and tags v0.1.0.
- Day 4 changes **no** engine logic. If a benchmark ever fails, the fix is in the *data*
  transcription or a flagged modelling decision — never a silent tweak to make a number match.
