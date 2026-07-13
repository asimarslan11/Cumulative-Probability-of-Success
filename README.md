# iWisdom PoS Engine

We are building a Python-based tool for iWisdom that calculates the cumulative probability of success (PoS) of a drug development program, from its current clinical phase through to FDA approval. Rather than training a machine-learning model on synthetic data — which would look sophisticated but wouldn't be scientifically defensible given we only have aggregated statistics rather than row-level trial data — we are building a transparent, Bayesian-style odds-adjustment engine. For each phase transition (Phase I→II, II→III, III→Filing, Filing→Approval), the engine follows four steps: first, it selects the most specific reliable baseline success rate available, using a fallback hierarchy from disease-and-phase-specific data down to modality-based and finally industry-wide averages; second, it converts that baseline probability into odds; third, it applies likelihood ratios for each relevant piece of evidence about the asset (e.g. biomarker use, rare disease status, modality, prior approval, breakthrough designation, trial outcome), with a shrinkage mechanism that dampens overlapping or correlated evidence so it isn't double-counted; and fourth, it converts the adjusted odds back into a probability. These adjusted phase probabilities are then compounded (multiplied) together, rather than applying a single adjustment to the overall likelihood, to produce the final cumulative PoS. All baseline rates and likelihood ratios are derived directly from two published sources — the BIO/QLS Advisors (2021) Clinical Development Success Rates report and Wong, Siah & Lo (2019) — rather than invented figures, and every calculation is validated against known results from these reports. 


See @README.md. I want you to plan the day 1's tasks. Then, start implementing one by one, add tests with pytest.

# 5-Day Build Plan

A transparent, Bayesian-style odds-adjustment engine for calculating cumulative probability of success (PoS) of a drug development program, from its current clinical phase through FDA approval. Grounded entirely in published, aggregated statistics from:

- **BIO/QLS Advisors (2021)** — *Clinical Development Success Rates and Contributing Factors 2011–2020*
- **Wong, Siah & Lo (2019)** — *Estimation of clinical trial success rates and related parameters*, Biostatistics 20(2)

No synthetic data, no invented figures — every baseline and likelihood ratio traces back to a specific table or figure in these two sources.

---

## Day 1 (Today) — Data Extraction & Architecture Design

**Goal:** Get every baseline rate into structured, machine-readable tables before writing any engine code.

- [ ] Extract BIO/QLS 2021 tables: Fig 2/5b (14 disease areas × 4 phases + LOA), Fig 7 (oncology sub-groups: hematologic/solid/IO), Fig 8b (rare vs. chronic disease), Fig 9 (novel vs. off-patent; NME/biologic/vaccine/non-NME/biosimilar), Fig 10b (modality: CAR-T, siRNA, mAb, ADC, gene therapy, etc.), Fig 11 (biomarker vs. no biomarker)
- [ ] Extract Wong et al. 2019 tables: Table 1 (aggregate, path-by-path vs. phase-by-phase), Table 2 (9 therapeutic groups, lead vs. all indications), Table 3 (biomarker by therapeutic group), Table 4 (orphan drugs)
- [ ] Reconcile the two taxonomies (BIO/QLS's 14 disease areas vs. Wong et al.'s 9 groups) into one canonical enum with an explicit mapping table
- [ ] Build a single `baseline_rates.json`/CSV with fields: `source, disease_area, phase_transition, n, rate, method`
- [ ] Write the fallback hierarchy spec on paper and get it right before coding: disease+phase-specific (BIO/QLS or Wong et al.) → modality-specific (Fig 10b) → novelty-class (Fig 9) → industry-wide all-indications
- [ ] Define the asset input schema: `current_phase, disease_area, modality, biomarker_flag, rare_disease_flag, prior_approval_flag, breakthrough_flag, trial_outcome, lead_indication_flag`
- [ ] Repo scaffolding: package structure, venv, pytest, `data/` folder, README stub with both citations

---

## Day 2 — Likelihood Ratio Derivation & Odds Engine Core

**Goal:** Build the statistical primitives: odds conversion, LR derivation from published contrasts, and shrinkage for stacked evidence.

- [ ] Implement `prob_to_odds()` / `odds_to_prob()` with trivial-case unit tests
- [ ] Derive an LR per evidence type wherever a real contrast exists in the sources:
  - **Biomarker:** Wong et al. Table 3 (10.3% vs. 5.5% overall, phase-specific) + BIO/QLS Fig 11 (15.9% vs. 7.6% LOA; per-phase 52.4/46.3/68.2/96.0% vs. 52.0/28.3/57.1/90.3%)
  - **Rare disease:** BIO/QLS Fig 8b (rare vs. chronic vs. all)
  - **Modality:** Fig 10b (CAR-T 17.3%, siRNA 13.5%, mAb 12.1%, etc. vs. small molecule 7.5%)
  - **Novelty:** Fig 9 (novel vs. off-patent, NME vs. biologic vs. vaccine)
  - **Prior approval / lead indication:** proxy via Wong et al. Table 2 (lead vs. all indications) — flag this explicitly as a proxy, not a direct LR
  - **Breakthrough designation & trial outcome:** only quantified in BIO/QLS Fig 14's single decomposition example (+20.6pp breakthrough, +6.4pp positive trial outcome, +3.6pp prior approval, +4.6pp validated target) — treat as a lower-confidence, illustrative LR and document that limitation clearly
- [ ] Build `lr_lookup(evidence_type, phase_transition, disease_area/modality)` — if a specific rate isn't published at that phase, skip the adjustment rather than guessing
- [ ] Design the shrinkage mechanism: each LR raised to an exponent `w_i` that shrinks as correlated evidence stacks (e.g., biomarker + targeted modality both signal "precision medicine" — define an explicit correlation-group map and a tunable dampening constant `k`, not a magic number)
- [ ] Unit test shrinkage on synthetic cases: confirm monotonic dampening and outputs always stay in (0,1)
 
---

## Day 3 — Fallback Hierarchy, Compounding & Full Pipeline

**Goal:** Wire baseline selection, LR adjustment, and multiplicative compounding into one auditable pipeline.

- [ ] `select_baseline(asset, phase_transition)`: walks the fallback hierarchy, returns `(rate, n, source, specificity_tier)` — always log which tier fired
- [ ] `adjust_phase_probability(...)`: baseline → odds → apply shrinkage-weighted LRs → back to probability, clipped to a sane range (e.g., 0.1%–99%)
- [ ] `compound_pos(asset)`: loop from current phase through Filing→Approval, calling the phase adjuster each time and **multiplying** results — never a single adjustment to the whole product
- [ ] Add a per-phase audit trail (baseline used, fallback tier, LRs applied, shrinkage weights, resulting probability) — essentially your own version of the Fig 14 waterfall, but for every calculation
- [ ] Move all tunable constants (shrinkage `k`, clip bounds, correlation groups) into a config file
- [ ] Smoke-test on 3–4 hand-built assets (e.g., "Phase 3 oncology, biomarker-selected" vs. "Phase 1 rare disease, CAR-T") and sanity-check direction and magnitude

---

## Day 4 — Validation Against Published Benchmarks

**Goal:** Prove the engine reproduces the reports' own numbers before trusting it on anything novel.

- [ ] Baseline-only ("no extra evidence") pass for every disease area, checked against Fig 5b (Hematology 23.9%, Oncology 5.3%, Urology 3.6%, all-indications 7.9%)
- [ ] Modality baselines vs. Fig 10b (CAR-T 17.3%, siRNA 13.5%, small molecule 7.5%)
- [ ] Biomarker LR check: run identical asset with/without biomarker flag, confirm the output ratio approximates the ~2x effect in both Fig 11 (15.9% vs. 7.6%) and Wong et al. Table 3 (10.3% vs. 5.5%)
- [ ] Rare disease / oncology sub-category paths vs. Fig 7 and Fig 8b
- [ ] Cross-check aggregate and phase-specific rates against Wong et al. Table 1/2 (13.8% overall LOA, POS2,3 = 58.3%, oncology 3.4%) — document rather than silently reconcile the known discrepancies between the two papers (different time windows and path-by-path vs. phase-by-phase methods)
- [ ] Turn every validated benchmark into a pytest regression test
- [ ] Run a shrinkage sensitivity sweep (k = 0, 0.25, 0.5, 1) to justify the default and show how much 3+ stacked correlated LRs move the output

---

## Day 5 — Documentation, Packaging & Handoff

**Goal:** Make this something a colleague or the iWisdom product team can run and trust.

- [ ] Methodology README: fallback hierarchy, LR derivation, shrinkage rationale, and an explicit limitations section (Fig 14 LRs are a single illustrative case; prior-approval LR is a lead-indication proxy; the two sources use different windows/methods)
- [ ] Inline citations to specific figures/tables in code and docstrings wherever a number is used
- [ ] Package as an installable module with a clean public API, e.g. `calculate_pos(asset_dict) -> {phase_probabilities, cumulative_pos, audit_trail}`
- [ ] Build a small CLI/notebook that reproduces an iWisdom-style summary (cumulative PoS by stage, similar to the dashboard screenshot) so the team can visually sanity-check against current tooling
- [ ] Peer review: have someone else run the validation suite plus 2–3 real pipeline assets, capture feedback
- [ ] Tag a v0.1.0 release and note open questions for later (e.g., adding confidence intervals from Wong et al.'s reported standard errors)

---

## Sources

1. BIO, QLS Advisors, Informa Pharma Intelligence (2021). *Clinical Development Success Rates and Contributing Factors 2011–2020.*
2. Wong, C.H., Siah, K.W., Lo, A.W. (2019). Estimation of clinical trial success rates and related parameters. *Biostatistics*, 20(2), 273–286. doi: 10.1093/biostatistics/kxx069