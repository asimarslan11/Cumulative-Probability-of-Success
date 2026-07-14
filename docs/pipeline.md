# Pipeline & Compounding — Specification

*Day 3 deliverable. Sibling to `fallback_hierarchy.md` (picks the baseline) and
`likelihood_ratios.md` (adjusts it). This one is the orchestration: from an `Asset` to a
cumulative probability of success, across every phase still ahead of it.*

## Problem

Days 1–2 gave us the parts but not the assembly. `BaselineLookup.get(...)` picks a
baseline for **one** phase; `LikelihoodRatios.lr(...)` derives **one** LR; `.combine(...)`
folds a **pre-chosen** list of LRs onto a **pre-chosen** baseline. Nothing yet decides
*which* baseline and *which* LRs a real asset gets at each phase, nor compounds the phases.

`engine.py` is that assembly. For each remaining transition it selects the baseline, routes
the asset's evidence to the LRs that apply there, folds them on (Day-2 `combine`), and
multiplies the adjusted per-phase probabilities:

```
cumulative_pos = PROD_t  adjusted_prob_t          (t over the remaining transitions)
```

Compounding is a plain product because each `adjusted_prob_t` is already a probability in
(0, 1); multiplying them is "pass phase 1 **and** phase 2 **and** …".

## 1. Which transitions remain

The asset's `current_phase` fixes the starting point; `Asset.remaining_transitions()`
returns the ordered transitions from there through approval:

| `current_phase` | Remaining transitions compounded |
|---|---|
| Phase I  | phase1_to_2, phase2_to_3, phase3_to_filing, filing_to_approval |
| Phase II | phase2_to_3, phase3_to_filing, filing_to_approval |
| Phase III| phase3_to_filing, filing_to_approval |
| Filing   | filing_to_approval |

A Phase-I asset with no evidence compounds the four all-indications rates
`0.520 × 0.289 × 0.578 × 0.906 ≈ **0.079**` — exactly the published **Phase I LOA ≈ 7.9%**
(BIO/QLS Fig 5b). That identity is the pipeline's anchoring regression test.

## 2. `select_baseline(asset, phase)`

A thin map from the asset onto the Day-1 fallback hierarchy: pass
`disease = asset.disease_area`, `modality = asset.modality` to `BaselineLookup.get`. The
returned dict carries `source_level` (`disease+phase` / `modality` / `novelty_class` /
`all_indication`) and `source_key` — that `source_level` is what the double-count guard
below reads. An `Asset` has no novelty field, so the novelty tier is never supplied.

## 3. Evidence routing — which LRs apply, and where

The single source of truth is `config.EVIDENCE_ROUTING`. An entry contributes an LR at a
given transition only when **all three** hold:

**(a) its trigger fires** on the asset —

| Evidence | Trigger | LR (`likelihood_ratios.md`) |
|---|---|---|
| `biomarker` | `biomarker_flag` | Fig 11 with/without |
| `rare_disease` | `rare_disease_flag` | Fig 8b vs Fig 1 |
| `modality` | `modality` is set | Fig 10b vs Fig 1 |
| `trial_outcome_positive` | `trial_outcome == positive` | Fig 14 (illustrative) |
| `breakthrough` | `breakthrough_flag` | Fig 14 (illustrative) |
| `prior_approval` | `prior_approval_flag` | Fig 14 (illustrative) |
| `lead_indication` | `lead_indication_flag` | Wong Table 2 (proxy) |

**(b) its temporality includes this transition** — a signal is not automatically applied at
every remaining phase; applying a one-time readout at all four would re-count it:

| Temporality | Applies at | Rationale |
|---|---|---|
| `persistent` | every remaining transition | a standing program attribute (biomarker, rare, modality, lead-indication) |
| `next_only` | the immediate next transition only | evidence about the readout just completed (`trial_outcome_positive`) |
| `regulatory` | the filing-facing transitions (`phase3_to_filing`, `filing_to_approval`) | a smoother regulatory path bites near filing/approval (`breakthrough`, `prior_approval`) |

`lead_indication` is persistent in principle, but `LEAD_INDICATION_PROXY` already caps its
phases to the two early transitions (`lr(...)` returns None elsewhere), so no extra filter
is needed.

**(c) it is not double-counting the baseline tier.** If the baseline for *this* transition
was itself selected at the tier the LR would duplicate, the LR is skipped. Today only
`modality` carries such a `baseline_tier`: if no disease-specific rate existed and the
baseline fell back to the modality tier (`source_level == "modality"`), the baseline *is*
the modality signal, so the modality LR is not applied on top. This is evaluated **per
transition** — a program can be disease-tier at Phase II→III but fall back to modality at
filing, and the guard fires only where it actually coincides.

> **Why (b) and (c) are modelling choices, not published parameters.** The sources report
> rates, not a rule for how long a designation's effect persists or exactly which phase a
> regulatory tailwind lands in. Temporality and the regulatory-phase assignment are
> deliberate, documented conventions — chosen to be conservative (don't re-count) and
> defensible — not measured effects. They are the natural knobs to revisit in review.

## 4. `adjust_phase_probability` and `compound_pos`

`adjust_phase_probability(asset, phase)` runs steps 2–3 for one transition, calls
`combine(baseline_rate, applicable_lrs, k)`, and returns the adjusted probability plus the
Day-2 per-LR audit. Absent or too-small contrasts come back as `None` from `lr(...)` and are
dropped by `combine`, so a routed signal with no usable published arm simply has no effect.

`compound_pos(asset)` loops the remaining transitions, multiplies the adjusted
probabilities, and returns:

```
{
  cumulative_pos,          # PROD adjusted_prob, clipped to the engine's [min_prob, max_prob]
  starting_phase,
  n_transitions,
  per_phase: [ {phase, baseline_rate, baseline_source_level, baseline_source_key,
                baseline_source_ref, adjusted_prob, cumulative_after, audit:[...]}, ... ],
  asset,                   # the normalised input, for reproducibility
}
```

The `per_phase` list is the **waterfall**: for every transition you can read the baseline
(and which figure it came from), each LR applied (with its shrinkage weight, correlation
group, confidence flag, and source), the resulting adjusted probability, and the running
cumulative — every number traceable back to a source figure.

## 5. Config & guarantees

- **`EngineConfig(k, min_prob, max_prob)`** bundles the run-time knobs so Day 4 can sweep
  `k` (`EngineConfig(k=0.25)`) without editing code. `k` is passed straight to `combine`;
  `min_prob`/`max_prob` clip the *cumulative* product so a deep pipeline can't report a
  number outside the stated 0.1%–99% range. Defaults mirror the module constants, so a
  plain `PoSEngine()` behaves exactly like the un-parameterised engine.
- Each per-phase probability is already clipped inside `combine`, and the cumulative is
  clipped again, so `cumulative_pos` is always strictly inside **(0, 1)**.

## 6. Limitations

- **Temporality & regulatory-phase assignment are conventions** (see the note in §3), not
  parameters estimated from the sources.
- **`novelty` and `oncology_subtype` LRs are unreachable from an `Asset`.** Both contrasts
  are defined in Day 2, but the asset schema has no novelty-class or oncology-subtype field
  yet, so the pipeline never routes them. This is a Day-5 schema extension — deliberately
  **not** invented here.
- **Fig-14 signals stay low-confidence.** `breakthrough`, `prior_approval`, and
  `trial_outcome_positive` inherit the illustrative caveat from `likelihood_ratios.md`; the
  waterfall surfaces their `confidence="low"` flag so a reader can discount them.
- **Cross-source compounding.** Baselines and most LRs are BIO/QLS; `lead_indication` is a
  Wong proxy folded into the same odds product. The mixing is explicit in the audit, but it
  is a pragmatic bridge between two studies with different methods, not a unified model.
