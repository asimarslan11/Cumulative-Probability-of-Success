# Day 2 — Likelihood Ratio Derivation & Odds Engine Core

> Day 1 (data extraction & architecture) is complete: canonical `data/baseline_rates.json`,
> `BaselineLookup` (4-tier fallback), taxonomy, asset schema, 46 tests passing. This plan is Day 2.

## Context

The engine adjusts a baseline probability using **evidence about the asset**. Day 2 builds the
statistical core that does the adjusting, in **odds space** (odds multiply cleanly; probabilities
don't):

`adjusted_odds = baseline_odds × ∏ LRᵢ^{wᵢ}` → back to probability.

Each **likelihood ratio (LR)** is derived from a published two-arm contrast; the **shrinkage**
exponents `wᵢ` dampen correlated evidence so overlapping signals aren't double-counted. Day 2
produces the primitives (`prob↔odds`), the LR table, and shrinkage — Day 3 wires them into the
per-phase pipeline and compounding.

**Confirmed decisions:**
1. An LR is an **odds ratio**: `LR(evidence, phase) = odds(evidence arm) / odds(reference arm)`,
   computed **per phase transition**.
2. **Reference arm = all-indications average (Fig 1)** for modality & novelty. Biomarker and rare
   keep their figure's own two-arm reference (Fig 11 without-biomarker; Fig 8b all-diseases).
3. **Fig 14 illustrative LRs are included, flagged low-confidence** (breakthrough, trial-outcome,
   prior-approval, validated-target), derived as `odds(0.35+Δ)/odds(0.35)`.

## New files

```
src/pos_engine/
  odds.py                 prob_to_odds / odds_to_prob / clip
  config.py               tunables: clip bounds, shrinkage k, correlation groups, LR reference map, Fig-14 deltas
  likelihood_ratios.py    LikelihoodRatios: derive LRs from baseline_rates.json + lr_lookup + combine (shrinkage)
docs/
  likelihood_ratios.md    derivation spec (references, formulas, limitations) — sibling to fallback_hierarchy.md
tests/
  test_odds.py
  test_likelihood_ratios.py
  test_shrinkage.py
```

Reuses Day 1: `load_data`, `PHASE_KEYS` (`pos_engine/__init__.py`), the row-indexing pattern from
`baseline_lookup.py`, and `data/baseline_rates.json` (LRs are computed from its rows — no new data
file, single source of truth).

## 1. `odds.py`

- `prob_to_odds(p)` → `p/(1-p)`, with `p` clipped to `[MIN_PROB, MAX_PROB]` (avoids div-by-zero /
  infinities from 0% and 100% cells like Allergy filing→approval).
- `odds_to_prob(o)` → `o/(1+o)`.
- `clip_prob(p)` → clamp into `[MIN_PROB, MAX_PROB]`.
- Trivial-case tests: 0.5↔1.0, 0.2↔0.25, 0.8↔4.0, round-trip identity, 0%/100% clip.

## 2. `config.py` (tunables — Day 3 extends this)

- `MIN_PROB = 0.001`, `MAX_PROB = 0.99` (the brief's 0.1%–99% clip range).
- `SHRINKAGE_K = 0.5` (Day 4 sweeps k ∈ {0, 0.25, 0.5, 1}).
- `MIN_ARM_N = 10` — below this, an arm's rate is too noisy to trust as an LR (skip/flag; e.g.
  CAR-T filing→approval n=4 at 100% would otherwise yield an absurd LR).
- `LR_REFERENCE`: evidence_type → (present category_type, reference category_type/category):
  biomarker→(biomarker/with, biomarker/without); rare_disease→(rare_chronic/rare, all_indications);
  modality→(modality/X, all_indications); novelty→(novelty_class/X, all_indications);
  oncology_subtype→(oncology_subtype/X, disease_area/Oncology).
- `LEAD_INDICATION_PROXY`: Wong Table 2 lead vs all (path-by-path), phase1_to_2 & phase2_to_3 only
  (Wong's merged phase-3 step doesn't map cleanly to BIO/QLS's two late phases) — flagged proxy.
- `ILLUSTRATIVE_LRS` (Fig 14, baseline 0.35): breakthrough Δ+0.206, trial_outcome_positive +0.064,
  prior_approval +0.036, validated_target +0.046 → LR = odds(0.35+Δ)/odds(0.35), confidence="low".
- `CORRELATION_GROUPS`:
  - `precision_medicine` = {biomarker, modality:CAR-T/siRNA/ADCs/Gene therapy, oncology_subtype:immuno_oncology}
  - `regulatory_facilitation` = {rare_disease, breakthrough, prior_approval}
  - everything else → independent (singleton, w=1).

## 3. `likelihood_ratios.py`

`LikelihoodRatios` loads `baseline_rates.json`, indexes rows (like `BaselineLookup`), and:

- `lr(evidence_type, phase, value=None)` → `{lr, source, source_ref, confidence, arms}` or **None**
  (skip) when the contrast isn't published at that phase, or an arm's n < `MIN_ARM_N`. Computes
  `odds(present)/odds(reference)` with clipping.
- `combine(baseline_prob, evidence_items)` → adjusted probability. Steps: baseline→odds; for each
  item resolve its correlation group, `m_g` = present-count in that group, weight
  `wᵢ = 1/(1 + k·(m_g − 1))`; `adjusted_odds = baseline_odds · ∏ LRᵢ^{wᵢ}`; back to prob; clip to
  `[MIN_PROB, MAX_PROB]`. Guarantees output in (0,1).
- Returns an **audit list** (each LR, its weight, group, confidence) for the Day-3 waterfall trail.

**Derived-LR anchors (for tests):** biomarker P2→3 ≈ 2.18 (P1→2 ≈ 1.0); rare P2→3 ≈ 1.98; CAR-T
P1→2 ≈ 0.73 (below-average early, the LR honestly reflects the phase contrast); Biosimilar P1→2 ≈
3.69; Fig-14 breakthrough ≈ 2.33; lead-indication P1→2 ≈ 1.59.

## 4. `docs/likelihood_ratios.md`

Spec: the odds-ratio definition, the reference-arm table, the small-n guard, the shrinkage formula
and correlation groups, and a **Limitations** section (Fig-14 single-example caveat; lead-indication
is a Wong proxy; modality/novelty double-count is avoided by Day-3 not applying an LR for the tier
that was itself the baseline).

## 5. Tests

- `test_odds.py` — conversions, round-trip, clipping.
- `test_likelihood_ratios.py` — the anchor LRs above; `lr(...)` returns None for unknown/absent
  contrasts and for sub-`MIN_ARM_N` arms; provenance fields present; Fig-14 LRs tagged low-confidence.
- `test_shrinkage.py` — **monotonic dampening** (2 correlated LRs combine to *less* than their naive
  product; higher k → result closer to baseline; k=0 → full product); **independent LRs** (different
  groups) get no dampening; **outputs always in (0,1)** even for extreme stacked LRs.

## Verification

- `python -m pytest -v` — all green (Day-1 suite still passes + new odds/LR/shrinkage tests).
- Manual smoke: `LikelihoodRatios().lr("biomarker", "phase2_to_3")` ≈ 2.18;
  `combine(0.25, [biomarker, CAR-T modality])` returns a sane probability in (0,1) with the
  precision-medicine pair dampened vs the naive product.
- Confirm no runtime dependency added (stdlib only) and `baseline_rates.json` remains the sole data source.

## Notes / boundaries (kept for Day 3)

- Day 2 only **derives and combines** LRs. *Which* LRs apply to a given asset, avoiding
  double-counting the baseline tier, and compounding across phases, are Day 3.
- `config.py` is the seed of the Day-3 "move tunables to a config file" task.
