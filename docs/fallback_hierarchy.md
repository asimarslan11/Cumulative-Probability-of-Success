# Baseline Fallback Hierarchy — Specification

*Day 1 deliverable. Get this right on paper before the engine leans on it.*

## Problem

The engine needs a **baseline** phase-transition probability for every
`(asset, phase_transition)` it scores. No published source has a number for every
possible combination of disease, modality, and novelty. So we pick the **most specific
reliable baseline available** and fall back gracefully when a specific one is missing —
never failing, never inventing a number.

## The hierarchy (most specific → most general)

`BaselineLookup.get(phase, disease=…, modality=…, novelty=…)` walks these tiers in order
and returns the first hit:

| # | Tier | `category_type` | Source | `source_level` returned |
|---|------|-----------------|--------|-------------------------|
| 1 | disease + phase | `disease_area` | BIO/QLS Fig 2 (14 areas + Others) | `disease+phase` |
| 2 | modality | `modality` | BIO/QLS Fig 10b (CAR-T, siRNA, mAb, …) | `modality` |
| 3 | novelty class | `novelty_class` | BIO/QLS Fig 9 (NME, Biologic, Vaccine, Non-NME, Biosimilar) | `novelty_class` |
| 4 | all-indications | `all_indications` | BIO/QLS Fig 1 (industry-wide average) | `all_indication` |

Tier 4 always exists, so a usable baseline is guaranteed. The tier that fired is always
recorded in the result (`source_level`, plus `source`/`source_ref`) so every calculation
is auditable.

### Worked examples

- `get("phase2_to_3", disease="Hematology")` → tier 1, 48.1% (n=106), Fig 2.
- `get("phase1_to_2", disease="MadeUpDisease", modality="CAR-T")` → tier 2, 44.2% (n=43), Fig 10b.
- `get("phase1_to_2", novelty="Biosimilar")` → tier 3, 80.0% (n=60), Fig 9.
- `get("phase1_to_2")` → tier 4, 52.0% (n=4414), Fig 1.

## Design decisions

- **BIO/QLS only in the live chain.** All four tiers draw from BIO/QLS (2021), which is
  *phase-by-phase* across four transitions (`phase1_to_2`, `phase2_to_3`,
  `phase3_to_filing`, `filing_to_approval`). Mixing methods inside one chain would be
  indefensible.
- **Wong (2019) is for cross-validation, not the chain.** Wong is *path-by-path* and
  collapses filing+approval into a single `phase3_to_approval` step. Its rows live in the
  same table (`therapeutic_group`, `orphan`, `biomarker_wong`) and are used on Day 4 to
  benchmark the engine, but are deliberately excluded from `get()`.
- **Modifiers are not baselines.** `biomarker`, `rare_chronic`, and `oncology_subtype`
  (BIO/QLS Fig 11 / 8b / 7) are present in the table but are **not** fallback tiers. They
  describe a *contrast* between two arms; Day 2 converts each into a **likelihood ratio**
  applied on top of the selected baseline, with shrinkage for correlated evidence.
- **Specificity beats source breadth.** When several inputs are supplied, the more
  specific tier wins (disease over modality over novelty), because a disease-and-phase
  rate reflects more of what actually drives success than an industry average.

## Downstream (Days 2–3, for context)

The baseline chosen here is only step 1 of the per-phase calculation:

1. **select baseline** (this document) → probability `p`
2. convert to odds: `o = p / (1 - p)`
3. multiply by shrinkage-weighted likelihood ratios for each piece of evidence
4. convert back to probability, clip to a sane range

Adjusted phase probabilities are then **compounded** (multiplied) from the asset's current
phase through Filing→Approval to give the cumulative PoS.
