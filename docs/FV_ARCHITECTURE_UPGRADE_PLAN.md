# Fair Value Engine — Architecture Upgrade Plan

Status: plan · Scope: `app/fair_value_v2/` · Owner: deterministic layer (no LLM may set probabilities, shares, or prices)

Current state (verified 2026-10-14): 17 DSL methods, 10 categories ×
7 regimes, 4-scenario probability-weighted EV (bear .25 / base .50 /
bull .20 / explosive .05, static), Morningstar-style MoS policy
(category bands + 16 data-driven adders), macro stress overlay,
reverse DCF, relative valuation, lt_power repricing lens.
1,499 journaled runs / 460 symbols since 2026-09-19.

---

## P1 — Hypergrowth survival/failure tree (the "going-concern delusion")

**Verified gap.** `pre_earnings` regime = `ev_sales_growth` at weight
1.0 only. Scenarios vary multiple + sales — the bear leg can never
reach distress. EV→equity bridge uses today's diluted share count,
so per-share FV for a −20% FCF-margin name is systematically
overstated. Flat 10% WACC everywhere.

**Design — split expected FV into survival and failure legs:**

```
expected_fv = p_survival × intrinsic_equity(dynamic_shares)
            + p_failure   × distressed_value
```

- `p_survival` — deterministic, bounded [0.05, 0.98], computed from
  observable inputs only:
  - `cash_runway_yrs` = cash / |min(0, fcf_ttm)| (new feature)
  - `capital_funding_risk` (exists — demand layer emits
    low/moderate/high/critical; map to survival deltas)
  - fcf trajectory (improving burn vs accelerating burn)
  - leverage (total_debt > 2× cash already measured)
  No LLM input. Journal the components into `inputs_used`.
- `distressed_value` — bounded [net cash/share, 0.1–0.2 × sales
  fallback]. For tech names an option value on IP; for levered
  compute providers, liquidation is closer to net cash minus wind-
  down costs.
- **Dynamic share count path** (replaces today's static bridge for
  negative-FCF names):
  `shares_{t+1} = shares_t × (1 + funding_gap_t / mktcap_t + sbc_rate)`
  where `sbc_rate` = historical dilution from shares_outstanding
  series (exists in daily/annual data). Correction to the blueprint:
  apply an issue-price discount in stress scenarios — equity raised
  at distressed prices dilutes more per dollar funded; use
  `issue_price_factor` ≈ 0.6–0.8 for the failure-adjacent legs.
- **WACC tiering, not flat 25%** — with explicit `p_failure`, a flat
  venture rate double-counts failure risk. Tier by
  `capital_funding_risk`: low → 10%, moderate → 12%, high → 14%,
  critical → 16–18%. The probability leg carries the default risk;
  the rate carries the path risk.

**Deliverable**: new method `survival_tree` (DSL) that wraps the
survival leg's EV/S anchor + failure leg + dynamic shares; becomes
the `pre_earnings` regime's primary with `ev_sales_growth` as the
survival-leg internals. `single_method` flag resolves since the tree
itself produces two independently-priced legs.

## P2 — Growth ↔ reinvestment binding (Sales-to-Capital)

**Verified gap.** Scenario legs scale revenue with no capital cost —
"free scale illusion." `roic_ttm` feature exists but only feeds a
post-hoc flag.

**Design:**
- New features: `sales_to_capital` (ΔRevenue / (capex + ΔNWC),
  computed from financial statements) + per-category
  `industry_scap` constants (param table).
- In scenario legs (DCF + EV/S where a margin path is implied):
  `reinvestment_t = (rev_{t+1} − rev_t) / scap_eff`
  `fcf_t = op_income_t × (1−t) − reinvestment_t`
  `scap_eff` = coalesce(realized sales_to_capital, industry_scap).
- New flag `growth_unfunded`: scenario revenue growth whose implied
  reinvestment exceeds the company's plausible funding capacity
  (cash + realistic debt + dilution ceiling) → emits with flag +
  MoS adder, doesn't silently pass.

## P3 — GQ-linked fade duration (Competitive Advantage Period)

**Verified gap.** 10y explicit + 5y fade exists only in
`dcf_mega_cap` (>$200B). Morningstar's CAP principle — moat width
sets fade length — is unimplemented.

**Design:**
- `growth_quality_runs.gq_score` (exists, journaled) → fade shape:
  - gq ≥ 70 (wide moat): 10y explicit + 10y linear fade
  - gq 45–70: 7y + 5y fade
  - gq < 45 / missing: 3y + 2y aggressive compression to industry
    margin + terminal growth
- Margin convergence speed scales the same way: low-GQ names
  compress to industry operating margins inside the explicit window;
  high-GQ names hold margin premium into the fade.
- Removes the $200B cliff: any category/regime can get a DCF leg;
  fade params come from GQ, not market cap.

## P4 — Regime-conditional scenario probabilities

**Gap (kept from review — not in blueprint).** Static
25/50/20/5 weights regardless of environment.

**Design:** tilt weights by observable state — VIX/regime bucket,
earnings proximity, the engine's own uncertainty score
(adders_total / range_scale). High uncertainty shifts mass from
base→bear and base→explosive (fatter tails), never changes the
scenario prices themselves. All inputs journaled.

## P5 — Reverse-DCF blind spot (negative-FCF names)

**Verified gap.** Fails closed `fcf_ttm_not_positive` — blind
exactly where implied-expectations matters most.

**Design:** alternate solve targets when fcf_ttm ≤ 0 —
- `implied_normalized_margin`: revenue path = consensus estimates;
  solve the terminal operating margin the current price requires.
  Flag when implied margin > category margin ceiling (per-category
  param, e.g. software ~40%, semis ~30%).
- `implied_inflection_year`: solve years-to-FCF-breakeven the price
  embeds; >10y = speculative flag.
Bounded solver, deterministic; output joins `decision_scalars`.

## P6 — Backtest precompute (corrected fix)

**Blueprint correction.** The O(runs×queries) timeout is not DCF
math — it's per-run forward-price SQL (N+1 over daily_bars). The
parametric DCF-grid idea is still useful but for *sensitivity
analysis*, not this bottleneck.

**Design:**
- `fv_backtest_forwards` materialized table: (symbol, as_of,
  horizon, min_low, end_close) refreshed nightly by one windowed
  SQL pass over daily_bars — O(bars), not O(runs).
- `run_backtest` then reads precomputed forwards → O(1) per run.
- Separately: nightly sensitivity grid (growth × WACC × margin →
  FV surface) for method introspection — offline parametric
  matrix as blueprint suggests.

---

## Blueprint review verdict

| Blueprint step | Verdict |
|---|---|
| Survival/failure split | ✅ correct — Damodaran going-concern decomposition; p_survival must be computed from runway + funding_risk + burn trajectory, never an input |
| Dynamic share count | ✅ correct — add issue-price discount in stress legs |
| Sales-to-capital binding | ✅ correct — needs new feature + per-category S/Cap constants |
| VC WACC | ⚠️ adjust — flat 25% double-counts with explicit p_failure; tier 10→18% by funding_risk instead |
| GQ-linked fade | ✅ correct — gq_score already journaled; also removes the $200B DCF cliff |
| Implied-margin reverse DCF | ✅ correct — solves the fcf_ttm_not_positive blind spot |
| Grid-lookup backtest | ⚠️ reframe — bottleneck is forward-price queries, not valuation math; materialize `fv_backtest_forwards` + keep the grid for sensitivity analysis |

## Non-goals / invariants

- LLM may not set probabilities, share paths, WACC, or distressed
  values — all P1–P6 outputs are deterministic from stored data.
- `expected_fair_value` remains probability-weighted; `buy_below`
  still derives through `mos_policy` (adders may grow).
- Every new input journals into `inputs_used`; every new flag lands
  in `quality_flags` so the decision layer can price it.
