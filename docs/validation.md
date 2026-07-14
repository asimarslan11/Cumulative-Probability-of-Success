# Validation — Results

*Day 4 deliverable. Sibling to `pipeline.md`. Does the engine reproduce the sources' own
published numbers, is it stable, and how sensitive is it to the one free parameter?*

All figures below are produced by the committed tests (`tests/test_benchmarks.py`,
`tests/test_regression.py`, `tests/test_shrinkage_sweep.py`) against the published values in
`data/raw/benchmarks_bioqls.json`. The engine changed **not at all** for Day 4 — this is
measurement, not tuning.

## A clip caveat, stated once

The engine clamps every probability to `[0.1%, 99%]` (a deliberate Day-2 decision so a 0% or
100% source cell can't zero out or blow up the odds product). Where a source NDA/BLA cell is
**100%** (e.g. Allergy, several small-n modalities), the engine reports **99%**. This shifts a
Phase-I LOA by at most ~0.14pp (worst observed: CAR-T, siRNA/RNAi), so disease/modality checks
use `abs=0.003`; all-indications, which has no 100% cell, matches exactly.

## Tier A — internal consistency (tight)

The engine compounds BIO/QLS transition rates; it must reproduce BIO/QLS's own published LOA.
This is a **transcription-integrity check**: the four stored rates for a category must jointly
reproduce the *independently* published LOA, so one mis-keyed rate would break the product.

**All-indications LOA by starting phase (Fig 5b)** — exact:

| From | Published | Engine |
|---|---|---|
| Phase I | 7.9% | 7.9% |
| Phase II | 15.1% | 15.1% |
| Phase III | 52.4% | 52.4% |
| NDA/BLA | 90.6% | 90.6% |

**LOA from Phase I by disease (Fig 5b), all 15 areas** — match within 0.1pp. Spot values:
Hematology 23.9% (eng 23.9), Oncology 5.3% (5.3), Cardiovascular 4.8% (4.8), Urology 3.6% (3.6).

**LOA from Phase I by modality (Fig 10b), all 10 modalities** — match within 0.15pp:
CAR-T 17.3% (eng 17.2), mAb 12.1% (12.1), Small molecule 7.5% (7.5), Antisense 5.2% (5.2).

**Biomarker paths (Fig 11)** — the with/without transition rates compound to their published
LOA: 15.9% (with) and 7.6% (without).

## Tier B — mechanism (loose)

Tier A only re-multiplies stored rates. Tier B checks the **LR machinery** (odds → LR →
compound) lands in the right place.

**Biomarker ~2× (Fig 11).** Applying the biomarker **LR** on top of the all-indications
baseline gives **16.3%**, versus the independently-computed with-biomarker path of **15.9%** —
a **2.07×** lift over the 7.9% baseline, matching the report's "biomarkers roughly double LOA".
The ~0.4pp gap is expected and honest: the LR moves a baseline in odds space rather than
recomputing the biomarker path from its own rates, so this exercises the machinery, not a
tautology.

## Cross-source — Wong 2019 (directional only)

Wong is a **different study** (2000–2015 vs BIO's 2011–2020), a **different method**
(path-by-path vs phase-by-phase), and a **coarser taxonomy** (9 therapeutic groups; Wong "CNS"
= Neurology + Psychiatry, "Metabolic/Endocrinology" = Metabolic + Endocrine). So the numbers are
**not** expected to match; only direction and order of magnitude are checked.

| | Engine (BIO) | Wong | Note |
|---|---|---|---|
| Overall LOA | 7.9% | 13.8% | same order; BIO more conservative (`test_wong_overall_loa_same_order_of_magnitude`) |
| Oncology | 5.3% | 3.4% | both in the bottom tier (`test_oncology_ranks_in_bottom_tier_in_both_sources`) |
| Infectious disease | 13.2% | 25.2% | Wong ~2× higher |
| Ophthalmology | 11.9% | 32.6% | large divergence |
| Cardiovascular | 4.8% | 25.5% | **largest divergence (~5×)** |

The Cardiovascular and Ophthalmology gaps are the sharpest. They are **recorded, not "fixed"**:
they reflect genuine differences between the two datasets/windows/methods, and forcing them to
agree would mean inventing numbers — exactly what this project forbids. Wong stays out of the
live fallback chain (it is cross-validation only).

## Shrinkage sensitivity — the `k` sweep

`k` is the only knob not pinned to a published contrast, so it is swept over `{0, 0.25, 0.5, 1}`
on a correlated stack: an Oncology **biomarker + CAR-T** program (both in the `precision_medicine`
group). At Phase II→III both LRs are > 1 and share the group, so this is where shrinkage bites.

| k | group weight `1/(1+k(m−1))` | Phase II→III adjusted | Cumulative (from Phase II) |
|---|---|---|---|
| 0.0 | 1.00 | 0.714 | 0.411 |
| 0.25 | 0.80 | 0.625 | 0.360 |
| 0.5 (default) | 0.67 | 0.559 | 0.322 |
| 1.0 | 0.50 | 0.475 | 0.273 |

Properties asserted by the tests:
- **Monotonic dampening.** More shrinkage pulls a correlated positive stack back toward the
  baseline; the cumulative strictly decreases across the sweep.
- **`k = 0` is the naive product.** Every correlated LR keeps weight 1.
- **Single evidence is `k`-invariant.** A singleton group has weight 1 for all `k`, so a
  biomarker-only program returns the same PoS at every `k` (verified to 1e-12).

**Recommendation: keep `k = 0.5`.** It halves the second correlated signal's exponent (weight
0.67 for a pair), a middle course between double-counting (`k=0`) and near-ignoring the second
signal (`k=1`). Because the sweep is monotonic and well-behaved, `k` is a transparent dial a
reviewer can move, not a fitted parameter.

## What Day 4 did *not* do

No engine logic changed. If a benchmark ever fails, the cause is a data-transcription error or
a flagged modelling decision (the clip, temporality, `k`) — never a silent tweak to make a
number match. Regression is locked by `data/golden_scenarios.json` (10 scenarios covering the
un-anchored pipeline behaviours), guarded by the same "committed matches generator" invariant as
the baseline table. This document is the seed of Day 5's full methodology + limitations write-up.
