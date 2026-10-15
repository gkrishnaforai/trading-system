# Fair Value Engine — Design Reference

Single source of truth for every rule in `python-worker/app/fair_value_v2/`.
Review this document instead of reading the code; update it whenever a rule
changes. Last synced: commit `e8eb939` (P0–P6 upgrade complete).

**Boundary (invariant):** all math is deterministic. Features, methods,
scenario probabilities, MoS, gates, and backtests are code + YAML. LLMs may
explain the output; they never set probabilities, fair values, sizes, or
actions. The engine produces *advice* — the human decides and trades manually.

---

## 1. Pipeline

```
symbol
  → feature resolution (point-in-time, unit-normalized, FX-converted)
  → category classification          (category_router.yaml)
  → regime classification            (regime_router.yaml)
  → method selection by (category, regime)   (regime_methods.yaml)
  → per-method DSL evaluation        (definitions/*.yaml)
  → WeightedBlender (family cap 55%) + scenario ordering
  → regime-conditional scenario probabilities → expected_fair_value
  → decision layer (MoS → buy_below, confidence, risk flags)
  → macro-scenario stress overlay    (archetype_scenarios.yaml)
  → reverse DCF (implied expectations — reference only, never blends)
  → persist to fair_value_v2_runs
  → consumers: lt_power.priced_status → pulse rules / trade plans / spec_pulse
```

**Reuse rule:** a stored run is reused when inputs are fresh
(`inputs_watermark`) **and** `model_version` matches. `model_version` is a
hash of the YAML content — editing any method/policy YAML busts the cache.
`force=True` bypasses reuse.

## 2. Classification

### 2.1 Category (first-match wins, `category_router.yaml`)

| Category | Trigger (industry/sector/description keywords) |
|---|---|
| financials | industry contains bank / banks / insurance / capital markets / asset management / mortgage finance |
| ai_infra | optical, photonic, fiber, data center, cooling, thermal, electrical equipment, power management, semicon equipment, sci/tech instruments, test & measurement, communication equipment — OR description-matched GPU/datacenter/HPC/photonics-semiconductor combos |
| technology | sector=technology, industry=semiconductor; communication+internet; social, advertising; software |
| fintech | sector=financial AND (financial data / exchanges / payment / fintech / credit / financial services / consumer finance / lending) |
| growth | industry contains internet / biotech / software |
| cyclical | autos, airlines, chemicals; sectors industrials/basic materials/energy; oil, gas, steel, aerospace, defense, machinery, railroads, trucking, metals, construction |
| consumer | sector=consumer; restaurants, retail, apparel, footwear |
| healthcare | sector=health; drug, medical |
| value | utilities, real estate, reit, household, beverages |
| (default) | `value` |

Multi-archetype: all matched categories are recorded (`classification.all`);
primary drives method selection; strictest member sets the MoS band.
Manual override: `fair_value_v2_category_overrides` table (admin endpoint).

### 2.2 Regime (first-match wins, `regime_router.yaml`)

| Order | Regime | Condition |
|---|---|---|
| 1 | bank | category=financials OR industry contains "bank" |
| 2 | pre_earnings | eps_ttm ≤ 0 OR eps_forward ≤ 0 OR operating_margin_ttm ≤ 0 |
| 3 | cyclical | eps_ttm ≥ 0.25 AND forward_growth_pct_1y ≤ −15% (peak-EPS decliner — FRO lesson: don't price peak earnings at compounder multiple) |
| 4 | mega_cap_high_growth | market_cap ≥ $200B AND revenue_growth_ttm ≥ 25% |
| 5 | mega_cap | market_cap ≥ $200B |
| 6 | high_growth | revenue_growth_ttm ≥ 25% OR forward_growth_pct_1y ≥ 25% |
| 7 | standard | fallback |

Fallback chain for method selection: `(category, regime)` →
`(category, standard)` → `(value, actual_regime)` → `(value, standard)`.
The regime-preserving middle step matters: without it a pre-earnings
healthcare/consumer/unknown name fell to `(value, standard)` PE methods
that refuse on negative EPS — `no_fair_value` instead of the survival
tree. Fixed; regression test `TestRegimeFallback`.

## 3. Method selection matrix (`regime_methods.yaml`)

| Category ↓ / Regime → | standard | cyclical | pre_earnings | mega_cap | mega_cap_high_growth | high_growth |
|---|---|---|---|---|---|---|
| financials | — | — | — | — | — | — |
| ai_infra | pe_tech_dyn .85 + ev_fcf .15 | pe_cyc .7 + pe_fwd .3 | **ev_sales_survival .7 + ev_sales_growth .3** | pe_fwd .6 + dcf_mega .4 | peg_corr .3 + pe_tech_dyn .5 + dcf_mega .2 | peg_40 .25 + peg_corr .15 + pe_tech_dyn .30 + ev_fcf .15 + **dcf_quality_fade .15** |
| fintech | pe_fwd .6 + pe_growth .4 | pe_cyc .7 + pe_fwd .3 | **ev_sales_survival .7 + ev_sales_fintech .3** | — | — | — |
| technology | pe_tech_dyn .7 + ev_fcf .15 | pe_cyc .7 + pe_fwd .3 | survival .7 + ev_sales_growth .3 | pe_fwd .6 + dcf_mega .4 | peg_corr .3 + pe_tech_dyn .5 + dcf_mega .2 | same as ai_infra |
| value | pe_value .4 + pe_basic .3 + ev_fcf .15 | pe_cyc .85 + pe_fwd .15 | survival .7 + ev_sales_growth .3 | — | — | — |
| general | pe_basic .35 + pe_value .3 + ev_fcf .15 | pe_cyc .85 + pe_fwd .15 | survival .7 + ev_sales_growth .3 | — | — | — |
| growth | pe_growth .55 + pe_fwd .30 | pe_cyc .7 + pe_fwd .3 | survival .7 + ev_sales_growth .3 | pe_fwd .7 + dcf_mega .3 | peg_corr .3 + pe_growth .4 + dcf_mega .3 | peg_40 .3 + peg .25 + pe_growth .2 + ev_fcf .15 + **dcf_quality_fade .15** |
| cyclical | pe_cyc .85 + pe_fwd .15 | pe_cyc 1.0 | survival .7 + ev_sales_growth .3 | pe_cyc .85 + pe_fwd .15 | — | — |

`financials` matches the dedicated `bank` regime (not standard):
pb_bank 1.0. Cells with `—` fall back per §2.2 — `(category, standard)`
then `(value, regime)` then `(value, standard)`; `consumer` and
`healthcare` have no rows at all, so they always resolve through the
fallback (pre_earnings → survival tree via `(value, pre_earnings)`).

Weights sum to <1.0 in several cells — the remainder is intentionally
unpriced (the blend renormalizes over what resolves).

## 4. Method registry (20 methods, `definitions/*.yaml`)

Each YAML declares `requires.scalars` (hard gate — missing → method refused),
`optional_scalars`, `params`, `formula.bindings`, per-scenario `*_fair_price`,
`report` (auditable internals), `validations` (data sanity → refuse).

| Method | Essence |
|---|---|
| pb_bank | P/B for banks |
| pe_basic / pe_value / pe_forward / pe_growth / pe_technology / pe_technology_dynamic | PE variants (trailing, value-tilted, forward, growth-adjusted, tech-sector, dynamically parameterized) |
| pe_cyclical | Normalized/mid-cycle EPS × mid-cycle PE (pe_mid 11) |
| peg / peg_40 / peg_corrected / peg_r40_cagr | PEG family — r40_cagr prices the multi-year analyst EPS curve; rule-of-40 picks the PEG tier |
| ev_fcf | EV/FCF growth-linked multiple — cash-reality check |
| ev_sales_growth | EV/S ≈ implied-PE × normalized margin |
| ev_sales_fintech | EV/S with fintech peer group |
| **ev_sales_survival** | §5.1 hypergrowth survival tree |
| dcf_simple | Simple DCF |
| dcf_mega_cap | 10y explicit + 5y fade, Gordon terminal |
| **dcf_quality_fade** | §5.3 GQ-scaled CAP DCF |
| analyst_consensus | Street target anchor |

### Universal method rules

- **EV→equity bridge (P0, audited):** `equity = EV + cash − max(0, debt)`,
  divided by diluted shares when available (`shares_diluted` else
  `shares_outstanding`). Every EV/DCF method + reverse DCF uses it.
- **Scenario outputs:** bear / base / bull / explosive per method where
  feasible; `fair_price` = base.
- **Ordering enforced post-blend:** bear ≤ base ≤ bull ≤ explosive;
  violations clamped upward + flagged `ordering_violation:<leg>`.
- **Degenerate detection:** if bull ≤ base while bear < base → flag
  `scenario_degenerate` (expected value biased low).
- **`report:` block** exposes internals (p_survival, wacc_eff, runway,
  dilution_mult, gq tier, …) into `metrics` — auditable, never hidden.

## 5. The P1–P5 upgrades (shipped `ac045fa`)

### 5.1 ev_sales_survival — hypergrowth going-concern tree

```
fair_price = p_scenario × PV(survival per-share, diluted)
           + (1 − p_scenario) × distressed per-share
```

**p_survival tiers** (cash runway = cash / annual burn, capped 10y;
leverage_stress = debt > 2× cash):

| Runway | p_survival |
|---|---|
| ≥ 4y | 0.90 |
| 2.5–4y | 0.75 |
| 1.5–2.5y | 0.55 |
| 1.0–1.5y | 0.35 |
| < 1y | 0.15 |
| < 1y AND levered | 0.08 |

Scenario shifts: bear −0.15, bull +0.05, explosive +0.10 (clamped 0.02–0.99).

**Dynamic dilution** over `funding_horizon_yrs = 3`:
`cash_surviving = max(0, cash − burn×3)`; uncovered
`funding_gap` raised at `issue_price_factor = 0.70` (stress discount);
`dilution_mult = 1 + gap/(mcap×0.7) + sbc_rate×3` where
`sbc_rate = sbc_to_rev × rev / mcap` (default 4%, cap 15%).
Flag `dilution_heavy` when mult > 1.30.

**Tiered discount** on the survival horizon (probability leg carries
default risk; rate carries path risk — no flat-25% double count):
runway ≥4y → 10% · ≥2.5y → 13% · ≥1y → 16% · <1y → 18%.

**Distressed leg:** `(0.10 × revenue_ttm + max(0, cash − debt)) / shares`,
discounted at wacc_eff over `distressed_years = 1.5` — a default resolves
sooner than the growth horizon, not today. Survival equity legs floored at
0 (equity can't price negative). Flag `distressed_floor_binds` when the
liquidation leg exceeds going-concern PV.

**Reinvestment binding (P2 folded in):**
`reinvest_need = (sales_base×(1+g)^3 − sales_base) / scap_eff`;
`funding_capacity = cash + max(0,fcf)×3 + mcap×10%`;
`growth_unfunded` when need > capacity.
`scap_eff = sales_to_capital measured, else industry_scap`.

### 5.2 Sales-to-Capital (`industry_assumptions.yaml`)

Injected as params `industry_scap` / `industry_margin_ceiling` by the
runner per category:

| Category | S/Cap | Margin ceiling |
|---|---|---|
| technology / fintech | 2.5 | 0.35 / 0.30 |
| ai_infra | 1.5 | 0.30 |
| growth / pre_earnings / value / unknown | 2.0 | 0.20–0.30 |
| financials | 1.0 | 0.35 |
| consumer | 3.0 | 0.15 |
| healthcare | 1.5 | 0.30 |
| cyclical | 1.5 | 0.15 |

Meaning: $ of new revenue per $1 reinvested (capital-heavy = low S/Cap);
margin ceiling bounds reverse-DCF implied margins.

### 5.3 dcf_quality_fade — GQ-scaled competitive-advantage period

Replaces the $200B cliff for long-duration DCF in high_growth regimes:

| gq_score | Flat yrs | Fade yrs | Horizon |
|---|---|---|---|
| ≥ 70 (wide moat) | 10 | 10 | 20 |
| 45–70 | 7 | 5 | 12 |
| < 45 / unmeasured (default 50) | 3 | 2 | 5 |

WACC 10%, terminal 3%, growth = revenue_growth_ttm (clamp 2–20%);
scenario deltas: bear (+1% wacc, −2% g, −0.5% tg), bull (−1% wacc, +2% g),
explosive (−1.5% wacc, +4% g, +1% tg). Terminal capped at 75% of EV.
Low-GQ runs flag `short_fade`; TV-dominant results flag `tv_dominant`.
gq_score resolved from `growth_quality_runs`.

### 5.4 Regime-conditional scenario probabilities (`blender.tilted_scenario_probs`)

Base prior `{"bear": .25, "base": .50, "bull": .20, "explosive": .05}`
(env `FV_SCENARIO_PROBS` override). Tilts:

| Condition | bear + | explosive + |
|---|---|---|
| vix ≥ 30 | .10 | .03 |
| vix ≥ 24 | .05 | .015 |
| regime = pre_earnings or cyclical | .05 | .02 |
| flag extreme_gap or no_scenarios | .05 | — |
| flag tv_dominant or forward_revenue_inflated | .025 | — |

`base` absorbs shifts; every leg floors at 2%; renormalized. Applied probs
persist in `scenario_probs` field + `scenario_probs_tilted` warning.

### 5.5 Reverse DCF (reference only — never blends)

- **Positive FCF:** bisection-solve implied FCF growth ∈ [−60%, cap] over
  the dcf_mega_cap spec (unclamped below zero — inversion must express
  priced decline). Flags: `implied_above_cap`, `implied_below_floor`,
  `implied_far_above_realized` (>10pts over realized).
- **Negative FCF:** `implied_margin_path` solves the *terminal FCF margin*
  making a 5y-ramp/10y-horizon margin path equal spot, then the latest
  `implied_inflection_year` the burn can stop with margin pinned at the
  industry ceiling. Flags: `implied_margin_speculative` (> ceiling),
  `implied_margin_stretched` (> 0.85× ceiling).

## 6. Blend + expected value

- **Family cap 55%** — `pe_*`/`peg_*`/`ev_*`/`dcf_*` each ≤ 55% of total
  weight (correlated families can't dominate). Recorded `blend_weight`
  shows the capped share.
- Blend includes only `status=ok`, `fair_price > 0`, weight > 0 methods.
- Per-scenario blend is weight-renormalized over methods that emitted
  that leg.
- **expected_fair_value** = `Σ p·FV` over emitted scenarios with the
  tilted probs (renormalized over present legs).

## 7. Decision layer (`mos_policy.yaml` + `decision.py`)

### 7.1 Margin-of-safety bands (category base)

financials/value 10–20% · consumer/healthcare 12–25% · growth/technology
20–30% · fintech 20–35% · cyclical 20–40% · ai_infra 30–50% ·
**pre_earnings 35–55%** · unknown 25–40%. Multi-archetype → strictest band.

### 7.2 Positioning within the band

`score = adders_total / 0.25`; high confidence → ×0.6; low confidence →
floor 0.5. `mos = min(low + (high−low)×score, cap 0.60)`.
**`buy_below = expected_fv × (1 − mos)`** — the entry gate.

### 7.3 Uncertainty adders

| Adder | Pts | Trigger |
|---|---|---|
| negative_fcf | .10 | fcf_ttm ≤ 0 |
| high_leverage | .05 | debt > 2× cash |
| no_scenarios | .10 | no method emitted bear/bull |
| scenarios_partial | .05 | some methods missing legs |
| extreme_gap | .05 | \|fv/spot−1\| > 1.5 |
| no_analyst_coverage | .05 | analyst_count missing/0 |
| capital_funding_risk | .08 | demand layer funding risk high/critical |
| method_dispersion | .06 | ok methods' base-FV spread > 50% of spot |
| weak_cash_conversion | .06 | ocf/net_income < 0.6 |
| reinvestment_below_wacc | .05 | growth > 15% while roic < 10% |
| forward_revenue_inflated | .05 | forward revenue > 3× trailing |
| survival_at_risk | .06 | p_survival below tight tier |
| growth_unfunded | .05 | reinvest_need > funding_capacity |
| share_dilution | .04 | dilution_overhang > 5% |
| tv_dominant | .04 | terminal value dominates a method's EV |
| earnings_divergence | .04 | adverse EPS/rev decoupling ≥ 15pts |
| dilution_heavy | .04 | dynamic path dilutes > 30% |
| distressed_floor_binds | .04 | liquidation leg > going-concern PV |
| scenario_degenerate | .04 | upside collapsed onto base |
| single_method | .03 | one method priced — no cross-check |
| eps_basis_gap | .03 | eps_forward > 1.5× eps_ttm |
| earnings_divergence_watch | .02 | investment-phase divergence |
| short_fade | .02 | low-GQ compressed CAP |

### 7.4 Confidence roll

- high: ≥2 ok methods AND none of {no_scenarios, extreme_gap, tv_dominant}
- medium: ≥1 ok method AND no no_scenarios
- else low.
- Dispersion override: spread > 70% of spot → low; > 35% caps at medium.

### 7.5 Risk gates

`bear_loss_severe` when bear_fv/spot − 1 < −40% · `uninvestable_mos` when
mos = 60% cap · `no_fair_value` when nothing priced.
Also emitted: `earnings_quality` (divergence classified
favorable/funding/dilution/accrual/investment_phase), `capital_quality`
(roic vs growth), two-axis `valuation_uncertainty` vs
`business_uncertainty`, `er2y` ((base/spot)^0.5−1).

### 7.6 Macro-scenario overlay (`archetype_scenarios.yaml`)

4 AI-capex scenarios × per-archetype FV sensitivity (−35% … +10%).
Multi-archetype: primary weight 0.7, mean(secondary) 0.3; `impact_mult`
modulates by demand model (capacity_rental absorbs slowdowns better than
capex_project). Emits `stressed_fv` / `stressed_buy_below` /
`stressed_vs_spot` + `_worst`. Overlay only — base FV unchanged.

## 8. Features (`features.yaml` + `feature_resolver.py`)

Point-in-time resolution; units declared per feature (`usd`, `usd_per_share`,
`decimal`, `percent`, `count`) with percent-scaled names whitelisted
(`*_pct`, `tnx_yield`, `vix_close`…). FX: statement-currency fields
converted at run FX with provenance notes. Derived: `sales_to_capital`
(revenue growth ÷ capex intensity), `cash_conversion`, `dilution_overhang`.
gq_score from `growth_quality_runs`; `capital_funding_risk` from
`company_demand_profile` (demand layer, low→critical). Macro yields/vix
from `raw_market_data_intraday` as-of `data_date`.

## 9. Persistence & consumers

- `fair_value_v2_runs` — one row per run: scenario set, expected_fv,
  decision payload (buy_below, mos, confidence, flags), method_results
  incl. `report` internals, scenario_probs, reverse_dcf, model_version,
  inputs_watermark.
- **lt_power.priced_status** blends LT-curve + expected_fv vs spot →
  `stocks.priced_status` (unpriced/full/beyond_lt_avg…).
- **Downstream gates:** invest lane hard-gates `fv ≥ −20%`; add rules
  need `fv_gte 5` + `fv_valid`; `broken_premium_valid_fv` → reduce;
  leap_call rank +10% fv_upside (no gate); swing ignores FV by design
  (valuation is a weak short-horizon timer — consistent with AQR/
  Morningstar practice); `scenario_fair_values` feed the put scorer.
- `fv_valid` is a Stage-0 contract: missing/suspect FV downgrades
  confidence, never counts as negative evidence.

## 10. Backtest (`backtest.py` + `fv_backtest_forwards`)

- Forwards materialized in one windowed pass over `daily_bars`
  (`refresh_forwards` — job `fv-backtest`, nightly 01:30 UTC, or
  `refresh=true` on the endpoint).
- Metrics per horizon (90/180/365d): `fv_bias` = median(end_px/FV − 1)
  — negative means realized landed **below** FV (engine overshot);
  `fv_mae`; `bear_breach` = fraction of windows where min close ≤ bear
  FV (**calibration target ≈ 25%**, the bear probability);
  `gate_reach` = fraction where min close ≤ buy_below (the gate was
  reachable); `ret_inside_gate` = median forward return for runs where
  spot was already ≤ buy_below at run time vs `ret_outside_gate` —
  whether the gate actually separates good entries.
- `per_symbol=true` breaks all metrics down per symbol.
- API: `GET /admin/fair-value-v2/backtest?symbol=&horizons=90,180,365&refresh=true&per_symbol=true`
- Streamlit: `streamlit-app/pages/42_FV_Backtest.py`.

## 11. Flag catalog (quick reference)

| Flag | Meaning |
|---|---|
| ordering_violation:<a><<b> | scenario legs inverted, clamped |
| scenario_degenerate | bull collapsed onto base |
| no_scenarios / scenarios_partial | missing scenario legs |
| single_method | no cross-method check possible |
| extreme_gap | FV/spot gap > 150% — data or model smell |
| tv_dominant | terminal value dominates EV |
| forward_revenue_inflated | forward rev > 3× trailing |
| survival_at_risk | p_survival < 0.55 |
| dilution_heavy | projected dilution > 30%/3y |
| distressed_floor_binds | worth more dead than alive |
| growth_unfunded | priced growth exceeds fundable reinvestment |
| short_fade | low-GQ name → compressed CAP (3+2y) |
| implied_margin_speculative | spot implies margin > industry ceiling |
| implied_margin_stretched | implied margin > 85% of ceiling |
| implied_above_cap / implied_below_floor | reverse-DCF out of envelope |
| implied_far_above_realized | priced growth >10pts above realized |
| bear_loss_severe | bear leg implies > −40% from spot |
| uninvestable_mos | MoS hit 60% cap — uninvestable, not cheap |
| margin_impossible | margin > 100% — data error, method refused |

## 12. Tuning surfaces (where to change behavior)

| To change… | Edit |
|---|---|
| Method weights / regime wiring | `methods/regime_methods.yaml` |
| Category & regime rules | `methods/category_router.yaml`, `methods/regime_router.yaml` |
| Scenario probs prior | env `FV_SCENARIO_PROBS` or `blender.SCENARIO_PROBS` |
| Tilt magnitudes | `blender.tilted_scenario_probs` |
| MoS bands / adders / cap / confidence | `mos_policy.yaml` |
| S/Cap & margin ceilings | `industry_assumptions.yaml` |
| Macro overlay sensitivities | `archetype_scenarios.yaml` |
| Peer groups | `peer_groups.yaml` |
| Method math / params | `methods/definitions/*.yaml` |
| Survival tiers, dilution, WACC tiers | `ev_sales_survival.yaml` params |
| GQ tiers & fade lengths | `dcf_quality_fade.yaml` params |
| Feature sources/units | `methods/features.yaml` |

Editing any YAML changes `model_version` → forces fresh runs.
