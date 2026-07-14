# Likelihood Ratios & Shrinkage — Specification

*Day 2 deliverable. Sibling to `fallback_hierarchy.md`: that one picks the baseline,
this one adjusts it.*

## Problem

The baseline (see `fallback_hierarchy.md`) says what happens *on average* at a phase.
A real asset carries **evidence** — it uses a biomarker, it's a rare-disease program,
it's a CAR-T, it has breakthrough designation — and each piece of evidence should move
the number up or down. This document defines how much, and how to combine several
pieces without double-counting.

We work in **odds space**, because odds multiply cleanly and probabilities don't:

```
adjusted_odds = baseline_odds  x  PROD_i  LR_i ** w_i
adjusted_prob = adjusted_odds / (1 + adjusted_odds)   # then clipped to [0.1%, 99%]
```

`LR_i` is the likelihood ratio for the *i*-th piece of evidence; `w_i` is a shrinkage
exponent that dampens correlated evidence.

## 1. An LR is an odds ratio between two published arms

Every LR is derived from a **two-arm contrast** in the source reports:

```
LR(evidence, phase) = odds(present arm) / odds(reference arm)
```

computed **per phase transition** (an LR for Phase I→II is a different number than for
Phase II→III). `odds(p) = p / (1 - p)`, with `p` clipped to `[0.1%, 99%]` first so a
0%/100% source cell can't produce 0 or infinite odds (`odds.py`).

### Reference-arm policy

Which arm is the "reference" depends on how the source figure is built:

| Evidence type | Present arm | Reference arm | Source |
|---|---|---|---|
| `biomarker` | with biomarker | without biomarker | BIO/QLS Fig 11 |
| `rare_disease` | rare disease | all-indications average | BIO/QLS Fig 8b vs Fig 1 |
| `modality` | that modality | all-indications average | BIO/QLS Fig 10b vs Fig 1 |
| `novelty` | that novelty class | all-indications average | BIO/QLS Fig 9 vs Fig 1 |
| `oncology_subtype` | that subtype | Oncology disease-area | BIO/QLS Fig 7 vs Fig 2 |
| `lead_indication` | lead-indication | all-indication (path-by-path) | Wong Table 2 |

**Why two policies?** Biomarker keeps Fig 11's own *with vs without* split — that figure
is explicitly a two-arm comparison. Rare, modality, and novelty each report a single arm,
so we contrast them against the **all-indications average** (Fig 1), the same industry
baseline the fallback hierarchy falls back to. Oncology subtypes are contrasted against
the Oncology disease-area rate (Fig 2), not the whole-industry average, so the LR isolates
the subtype effect *within* oncology rather than re-importing the oncology-vs-industry gap.

### Worked anchors (from `baseline_rates.json`)

- **biomarker, Phase II→III** = odds(0.463) / odds(0.283) = 0.862 / 0.395 ≈ **2.18**
  (a biomarker roughly doubles the Phase II→III odds). Phase I→II ≈ **1.0** — biomarkers
  barely move the earliest transition.
- **rare_disease, Phase II→III** = odds(0.446) / odds(0.289) ≈ **1.98**.
- **CAR-T, Phase I→II** = odds(0.442) / odds(0.520) ≈ **0.73**. Honestly **below 1**:
  early-phase CAR-T under-performs the industry average, and the LR reflects the phase
  contrast rather than flattering the modality.
- **Biosimilar, Phase I→II** = odds(0.800) / odds(0.520) ≈ **3.69**.
- **lead-indication, Phase I→II** = odds(0.758) / odds(0.664) ≈ **1.59** (Wong Table 2).

## 2. Small-arm guard

An odds ratio is only as trustworthy as its noisiest arm. Below `MIN_ARM_N = 10`
observations, a rate is dominated by sampling noise:

> CAR-T filing→approval is **100% on n=4**. Taken literally that's an *infinite* LR — an
> artefact of four lucky trials, not evidence. `lr(...)` returns **None** (skip) whenever
> either arm has `n < MIN_ARM_N`, so the engine simply doesn't apply that contrast at that
> phase. (Biosimilar Phase II→III, n=4, is skipped for the same reason.)

`lr(...)` also returns **None** when the contrast isn't published at a phase (e.g.
lead-indication at the two late phases — see Limitations) or the evidence type is unknown.

## 3. Shrinkage for correlated evidence

If two pieces of evidence tell the *same* underlying story, multiplying both LRs at full
strength double-counts it. We group correlated evidence and down-weight each member.

For an item in a **correlation group** of size `m`, the exponent is:

```
w = 1 / (1 + k * (m - 1))          k = SHRINKAGE_K = 0.5 (default)
```

- A **singleton** (independent evidence): `m = 1` → `w = 1` (no dampening).
- A **pair** in one group at `k = 0.5`: `w = 1 / (1 + 0.5) = 0.667` each — so instead of
  `LR_1 * LR_2` we apply `LR_1^0.667 * LR_2^0.667`, strictly less extreme.
- `k = 0` recovers the full naive product; larger `k` pulls a correlated stack back toward
  the baseline. Day 4 sweeps `k ∈ {0, 0.25, 0.5, 1}`.

### Correlation groups

| Group | Members |
|---|---|
| `precision_medicine` | `biomarker`; `modality` ∈ {CAR-T, siRNA/RNAi, ADCs, Gene therapy}; `oncology_subtype` = immuno_oncology |
| `regulatory_facilitation` | `rare_disease`; `breakthrough`; `prior_approval` |
| *(everything else)* | independent — its own singleton group, weight 1 |

`precision_medicine` reflects that a biomarker-defined program, a targeted advanced
modality, and immuno-oncology lean on the same "we know the mechanism" story.
`regulatory_facilitation` reflects that rare-disease status, breakthrough designation, and
prior approval in class all correlate with a smoother regulatory path.

## 4. Combining — guarantees

`combine(baseline_prob, evidence_items)`:

1. `baseline_prob → baseline_odds`
2. resolve each item's correlation group and group size `m`
3. weight `w_i = 1 / (1 + k*(m-1))`
4. `adjusted_odds = baseline_odds * PROD_i LR_i^{w_i}`
5. `adjusted_odds → adjusted_prob`, **clipped to `[0.1%, 99%]`**

The clip guarantees the output is always strictly inside **(0, 1)**, even for an extreme
stack of large LRs. `combine` also returns a per-LR **audit list** (each LR, its weight,
group, and confidence flag) for the Day-3 waterfall trail.

## 5. Limitations

- **Fig-14 LRs are illustrative, not population contrasts.** `breakthrough`,
  `trial_outcome_positive`, `prior_approval`, and `validated_target` are derived from a
  *single worked example* in BIO/QLS Fig 14 (baseline 35%): `LR = odds(0.35+Δ)/odds(0.35)`.
  They are phase-independent and flagged **`confidence="low"`**. Use them as rough priors,
  not measured effects.
- **Lead-indication is a Wong proxy.** It comes from a different study (Wong 2019),
  path-by-path, and is our proxy for "the program is being run on its strongest
  indication" rather than a like-for-like BIO/QLS contrast — flagged
  **`confidence="proxy"`**. Wong merges filing+approval into one `phase3_to_approval`
  step, which does **not** map onto BIO/QLS's two late phases, so the proxy is defined
  **only for Phase I→II and Phase II→III**; `lr(...)` returns None for the late phases.
- **Modality/novelty double-count with the baseline tier is avoided in Day 3, not here.**
  If the baseline was itself selected from the modality tier (fallback hierarchy tier 2),
  applying a modality LR on top would count that modality twice. Day 2 will happily derive
  both; it is Day 3's job *not to apply* an LR for the tier that already produced the
  baseline. This module is deliberately agnostic about which LRs a given asset should get.
