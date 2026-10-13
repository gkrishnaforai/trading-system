# Demand / Capital-Cycle Layer — Phase 2 Roadmap

Phase 1 (shipped, commit `691ae8b`): canonical demand axes persisted
per symbol (`company_demand_profile`), deterministic funding-risk
measurement, demand-model-modulated macro stress, MoS funding adder.

Phase 1.5 (this commit): evidence feed — `demand_evidence` table,
validated claims (LLM-extractable, human-approved), evidence-driven
axis overrides with conflict preservation.

## Phase 2 — remaining work (do not lose)

### Scoring & regime (blocked on evidence volume)
- [ ] `demand_durability_score` 0-100 — weighted dims (contract/backlog
      quality 25, recurring demand 20, essentiality 15, replacement 10,
      diversification 10, AI monetization 10, funding resilience 10),
      scored from `demand_evidence`, confidence reported separately
- [ ] `ai_capex_regime` — accelerating | expanding | growth_moderating
      | flat | contracting | stress | unknown. Weighted consensus across
      ≥3 hyperscaler capex guidance points + supplier orders +
      utilization + monetization + financing. NEVER one company's
      guidance as the signal
- [ ] `ai_cycle_warning_score` 0-100 — requires ≥2 independent
      deteriorating signal groups before escalating
- [ ] Three-scenario stress with real numbers: `revenue_growth_base /
      slowdown / stress`, `fcf_stress_state`,
      `valuation_stress_downside_pct`, `thesis_break_conditions`,
      `scenario_confidence`. `unknown` when not responsibly estimable

### Evidence ingestion feeds
- [ ] Quarterly capex guidance parser (hyperscaler earnings:
      AMZN/GOOGL/MSFT/META) → `demand_evidence` rows
- [ ] Supplier order/guidance feed (NVDA/AVGO/MRVL/CRDO/ANET/TSM/ASML)
- [ ] Contract/backlog disclosure extraction (8-K, 10-Q via llm_extract)
- [ ] Utilization/pricing disclosures (neocloud GPU utilization,
      rental $/hr, lease commencement dates)
- [ ] Financing events (prepayments, debt raises, covenants, dilution)

### Decision-engine integration (shadow first)
- [ ] Modifiers ordered AFTER existing hard gates: data validity →
      hard risk → thesis break → earnings proximity → tape →
      valuation → THEN capex regime + durability
- [ ] Rules: durable+attractive+healthy tape → permit add;
      high capex sensitivity + moderating regime → higher burden of
      proof; high funding risk + neg FCF + falling utilization →
      block adds; moderation + improving recurring → no penalty;
      unknown/stale → lower confidence
- [ ] Tactical vs long-term-compounder separation — low durability
      can qualify tactical, never auto-qualifies compounder
- [ ] Shadow-mode comparison old vs new engine before enabling

### UI / ops
- [ ] Stock page + Fair Value Test: demand axes, evidence list,
      conflicts, scenario stress, durability score
- [ ] Evidence review queue page (draft → approve/reject)
- [ ] Reclassification history + review dates on stale evidence

### Regression tests (framework-mandated)
- [ ] Capex moderates + recurring revenue/utilization rise → no
      automatic downgrade
- [ ] Capex grows + utilization falls + orders weaken → warning rises
- [ ] Big backlog + unsustainable debt/capex → adds blocked
- [ ] Signed lease, delayed commencement → not counted as current
      cash flow
- [ ] Recurring software + AI substitution → durability falls
- [ ] Strong demand + extreme valuation + weak tape → no auto-add
- [ ] Conflicting guidance sources → conflict preserved, confidence
      lowered (implemented in evidence layer — verify E2E)
- [ ] Missing utilization → stays `unknown` (implemented)
- [ ] Low durability → tactical eligible, not compounder
- [ ] PIT evaluation harness: warnings scored early/accurate/late/false
