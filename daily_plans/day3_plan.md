# Day 3 — Per-Phase Pipeline & Cumulative Compounding

> Day 1 (data layer) and Day 2 (odds primitives + LR derivation/`combine` + shrinkage) are complete.
> Day 3 wires those pieces into the end-to-end pipeline: from an `Asset` to a **cumulative PoS** with
> a per-phase audit trail. The three roadmap deliverables are `select_baseline`,
> `adjust_phase_probability`, and `compound_pos`, plus formalising the config.

## Context

Days 1–2 gave us the ingredients but not the recipe: `BaselineLookup.get(...)` picks a baseline for a
single phase, `LikelihoodRatios.lr(...)` derives one LR, and `.combine(baseline, [lrs])` folds a
pre-chosen list of LRs onto a pre-chosen baseline. Nothing yet decides **which** baseline and **which**
LRs apply to a real `Asset`, nor compounds across the phases still ahead of it.

Day 3 is that orchestration layer. For each remaining transition it: (1) selects the baseline, (2)
routes the asset's evidence to the LRs that apply *at that transition* (honouring temporality and not
double-counting the baseline tier), (3) calls the Day-2 `combine`, and (4) multiplies the adjusted
per-phase probabilities into a cumulative PoS — emitting a waterfall audit at every step.

**Confirmed decisions:**

1. **Evidence temporality — routed by type** (not "every LR at every phase", which would re-count a
   one-time signal up to 4×):
   - **Persistent** program attributes apply to **all** remaining transitions: `biomarker`,
     `rare_disease`, `modality`. (`disease_area` shapes the *baseline*, not an LR.)
   - **`trial_outcome` = positive** applies to the **immediate next transition only** — it is evidence
     about the readout just completed, not a standing property of the program.
   - **`breakthrough`, `prior_approval`** (regulatory-facilitation, Fig 14) apply to the
     **filing-facing** transitions only: `phase3_to_filing`, `filing_to_approval`.
   - **`lead_indication`** is persistent in principle, but `config.LEAD_INDICATION_PROXY` already caps
     it to `phase1_to_2` & `phase2_to_3`, and `lr()` returns `None` elsewhere — so no special-casing.
2. **Config stays Python.** `config.py` remains the single tunables module (stdlib, no parser dep). Add
   an **`EngineConfig` dataclass** (`k`, `min_prob`, `max_prob`) so Day 4 can sweep `k` without editing
   code, and add the new Day-3 routing/temporality maps here too. No external JSON, no new dependency.
3. **Baseline-tier double-count guard.** If a transition's baseline was selected at the **modality**
   tier (its `source_level == "modality"`, i.e. no disease-specific rate existed), the modality LR is
   **not** also applied at that transition — the baseline already *is* the modality signal. Evaluated
   **per transition** (a program can be disease-tier at P2→3 but fall back to modality at filing).
   `novelty_class` follows the same rule, but is unreachable from an `Asset` today (see Boundaries).

## New files

```
src/pos_engine/
  engine.py        PoSEngine + select_baseline / adjust_phase_probability / compound_pos
docs/
  pipeline.md      the Day-3 spec: baseline selection -> evidence routing -> compounding + audit format
tests/
  test_engine.py
```

Extends `config.py` (`EngineConfig`, `EVIDENCE_ROUTING`). Reuses Day 1–2 wholesale: `BaselineLookup`,
`LikelihoodRatios`, `Asset` (`remaining_transitions()`, its flags), `odds.py`, and
`data/baseline_rates.json` as the sole data source. No new data file.

## 1. `config.py` additions

- **`EngineConfig`** — a small frozen dataclass carrying the run-time knobs (`k = SHRINKAGE_K`,
  `min_prob = MIN_PROB`, `max_prob = MAX_PROB`). `PoSEngine` takes one; Day 4's sweep just passes
  `EngineConfig(k=0.25)` etc. Module-level constants stay as the defaults so nothing else changes.
- **`EVIDENCE_ROUTING`** — the single table that turns `Asset` fields into LR requests. One entry per
  signal:
  `{asset_field, condition, evidence_type, value_from, temporality, baseline_tier}` where
  `temporality ∈ {"persistent", "next_only", "regulatory"}` and `baseline_tier` names the fallback tier
  this LR would duplicate (only `"modality"` today, else `None`). Example rows:
  - `biomarker_flag == True` → `biomarker`, persistent
  - `rare_disease_flag == True` → `rare_disease`, persistent
  - `modality is not None` → `modality` (value = the modality name), persistent, `baseline_tier="modality"`
  - `trial_outcome == POSITIVE` → `trial_outcome_positive`, next_only
  - `breakthrough_flag == True` → `breakthrough`, regulatory
  - `prior_approval_flag == True` → `prior_approval`, regulatory
  - `lead_indication_flag == True` → `lead_indication`, persistent (config self-caps its phases)
- **`REGULATORY_PHASES = ("phase3_to_filing", "filing_to_approval")`** — the filing-facing set the
  `regulatory` temporality resolves against.

## 2. `engine.py`

`PoSEngine` constructs `BaselineLookup()` + `LikelihoodRatios()` once (data loaded a single time) and
holds an `EngineConfig`. Three operations, also exposed as thin free functions:

- **`select_baseline(asset, phase)`** → `BaselineLookup.get(phase, disease=asset.disease_area.value,
  modality=asset.modality.value)`. Returns the baseline dict, which already carries `source_level` /
  `source_key` — that is what the double-count guard reads. (Asset has no `novelty` field, so the
  novelty tier is simply never passed.)
- **`_applicable_evidence(asset, phase, baseline)`** → walk `EVIDENCE_ROUTING`; keep entries whose
  `condition` holds on the asset, whose `temporality` includes `phase` (persistent → always;
  next_only → `phase == remaining[0]`; regulatory → `phase in REGULATORY_PHASES`), and that are **not**
  the baseline tier for this phase (`baseline["source_level"] != entry.baseline_tier`). Returns
  `(evidence_type, value)` pairs.
- **`adjust_phase_probability(asset, phase)`** → select baseline; derive each applicable LR via
  `lr_engine.lr(evidence_type, phase, value)` (sub-`MIN_ARM_N` / absent contrasts come back `None` and
  are dropped by `combine`); call `combine(baseline["rate"], lrs, k=config.k)`. Return
  `{phase, baseline, adjusted_prob, combine_result}` — the per-phase audit already inside
  `combine_result["audit"]`.
- **`compound_pos(asset)`** → for each `t` in `asset.remaining_transitions()`: adjust, multiply
  `adjusted_prob` into a running `cumulative`, append a waterfall entry. Return
  `{cumulative_pos, per_phase: [...], starting_phase, asset}`. **`cumulative_pos = ∏ adjusted_prob_t`**
  over the remaining transitions — the whole point of the engine.

## 3. `docs/pipeline.md`

Sibling to `fallback_hierarchy.md` / `likelihood_ratios.md`. Documents: the select→route→combine→
compound flow; the `EVIDENCE_ROUTING` table with its temporality column; the baseline-tier double-count
rule with a worked example; the shape of the waterfall audit; and a **Limitations** section (temporality
is a modelling choice, not a published parameter; regulatory-signal phase assignment is a judgement;
`novelty`/`oncology_subtype` LRs are currently unreachable from an `Asset`).

## 4. Tests — `test_engine.py`

Anchored on traceable numbers (cite the figure in each docstring):

- **Compounding sanity (Fig 5b).** `Asset(current_phase="phase1")` with no disease/modality/flags →
  `cumulative_pos ≈ 0.0787` (0.52 × 0.289 × 0.578 × 0.906), i.e. the published **Phase I LOA ≈ 7.9%**.
- **`select_baseline` tier.** Hematology at `phase2_to_3` → `source_level == "disease+phase"`,
  `rate == 0.481` (Fig 2). Unknown disease + CAR-T → modality tier; unknown everything → all-indications.
- **Positive evidence lifts PoS.** Same base asset with `biomarker_flag=True` → strictly higher
  cumulative than without; a `modality="CAR-T"` early asset (LR < 1 at P1→2) shows the honest dampening.
- **Double-count guard.** Construct an asset whose baseline falls back to the modality tier at some
  phase; assert the `modality` LR is **absent** from that phase's audit, yet **present** at a phase whose
  baseline is disease- or all-indications-tier.
- **Temporality.** `trial_outcome="positive"` appears only in the first transition's audit;
  `breakthrough_flag=True` appears only in `phase3_to_filing` / `filing_to_approval` audits, never in
  `phase1_to_2`.
- **Audit integrity.** `cumulative_pos` equals the product of the per-phase `adjusted_prob`; every
  per-phase entry carries baseline provenance and each LR's weight + `source_ref`.
- **Bounds & start phase.** All probabilities strictly in (0,1); `current_phase="phase3"` compounds only
  the last two transitions (`asset.remaining_transitions()`).

## Verification

- `python -m pytest -v` — all green (Day 1–2 suites still pass + new engine tests).
- Manual smoke: `PoSEngine().compound_pos(Asset(current_phase="phase1"))["cumulative_pos"]` ≈ `0.079`;
  adding `biomarker_flag`/`breakthrough_flag` raises it; the waterfall prints one line per remaining
  transition with its baseline, LRs, and adjusted probability.
- Confirm stdlib-only and `baseline_rates.json` remains the single data source.

## Notes / boundaries (kept for Day 4–5)

- **Day 4** validates the compounded outputs against published benchmarks (Fig 5b LOAs by disease, Fig
  10b modality LOAs, biomarker ~2×, Wong Table 1/2), adds regression tests, and sweeps `k` via
  `EngineConfig` — the reason `k` is now injectable.
- **Day 5** wraps this core in the public `calculate_pos(asset)` API + CLI/notebook demo and packages
  v0.1.0; `engine.py` is the thing it calls.
- **Asset schema gap.** `Asset` has no `novelty` or `oncology_subtype` field, so those LR contrasts are
  defined but unreachable from an asset. Noted as a Day-5 schema extension — **not** invented here.
