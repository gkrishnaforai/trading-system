# Demand / Capital-Cycle Layer — Phase 2 Roadmap

Phase 1 (`691ae8b`): canonical demand axes persisted
(`company_demand_profile`), measured funding risk, demand-model-
modulated macro stress, MoS funding adder.

Phase 1.5 (`7818952`): evidence feed — `demand_evidence` claims
(draft → human approve → axis upgrade), conflict preservation,
freshness windows, LLM extraction (drafts only), admin endpoints,
evidence review Streamlit page.

Phase 2 core scorers (this commit): `durability_score` 0-100 with
renormalized coverage + confidence; `ai_capex_regime` market
consensus (never one company); `ai_cycle_warning_score` (≥2
independent down groups to escalate); `demand_gate` SHADOW modifier
+ long-term eligibility split; 3-scenario revenue stress from
measured forward growth; `market_ai_regime` daily persistence.

## Still open — Phase 2 tail

### Evidence ingestion feeds
- [x] On-demand ingest — `POST /admin/demand-evidence/ingest` +
      "load evidence" control on the Demand Evidence page. Groups:
      hyperscalers / accelerators / networking / neoclouds / power /
      semi_equipment / software / watchlist.
- [x] Capex actuals — deterministic YoY/QoQ trend from FMP
      cash-flow, auto-approved (`source=fmp_cashflow`), feeds the
      `spending` group of `ai_capex_regime`
- [x] News extraction — FMP stock news → LLM → drafts
- [x] Transcript extraction — latest earnings call (head + Q&A tail)
      → LLM → drafts (opt-in, slower)
- [ ] Guidance-specific parsing — transcripts give drafts today; a
      dedicated capex-guidance extractor could tighten precision
- [ ] Scheduled ingest job (cron) so evidence refreshes without
      manual pulls — currently on-demand only
- [ ] Contract/backlog feed — 8-K/10-Q attachments beyond headlines
- [ ] Utilization/pricing feed — neocloud disclosures are sparse on
      FMP; may need a second provider or manual entry
- [ ] New durability dimensions as feeds land:
      essentiality/switching + customer_diversification currently
      excluded from score (renormalized out) until evidence exists
- [ ] New durability dimensions as feeds land:
      essentiality/switching + customer_diversification currently
      excluded from score (renormalized out) until evidence exists

### Decision-engine integration (shadow → enable)
- [x] `demand_gate` computed + persisted as shadow field —
      `gate.gate` ∈ permit_add | higher_burden | watch | block_adds
      and `gate.long_term_eligible` (durability contracted/recurring
      + funding ok + no conflicts). NOT applied to actions yet.
- [ ] Shadow-mode comparison harness: log old vs gated decisions
      side-by-side for N weeks, review divergences
- [ ] Enable `higher_burden` → requires stronger valuation/tape;
      `block_adds` → hard gate on new adds, AFTER existing gates
      (data validity → hard risk → thesis break → earnings → tape →
      valuation → demand layer → sizing)

### Ops
- [ ] PIT evaluation harness: replay historical claims, score each
      warning early/accurate/late/false
- [ ] Reclassification history + review dates on stale evidence
- [x] Streamlit: FV Test shows demand axes/score/gate/scenarios;
      `41_Demand_Evidence` review queue + manual submit + LLM extract

### Regression tests — remaining cases need feeds
- [ ] Big backlog + unsustainable debt/capex → adds blocked
      (needs backlog evidence volume)
- [ ] Signed lease, delayed commencement → not counted as current
      cash flow (needs lease-commencement signal wiring to FV inputs)
- [ ] Strong demand + extreme valuation + weak tape → no auto-add
      (needs decision-engine integration, shadow first)
- [ ] PIT replay tests once the harness exists

### Done (tested, 26 cases)
- [x] Capex moderates + usage/monetization rise → `growth_moderating`,
      NOT stress
- [x] ≥2 independent down groups required for warning escalation
- [x] Conflicting sources → conflict preserved + confidence low
- [x] Missing utilization/data → stays `unknown`, excluded from score
- [x] Critical funding → `block_adds`; conflict → not LT-eligible,
      tactical unaffected
- [x] Low durability → `watch`/discretionary, never auto-compounder
- [x] One company's guidance ≠ regime
- [x] Stale evidence ignored for axes, kept for audit
- [x] Filing can reclassify demand_model via `evidence_can_set`
