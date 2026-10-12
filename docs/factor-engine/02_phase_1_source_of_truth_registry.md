# Phase 1 — Source of Truth Registry (SoTR)

## Purpose
Create an authoritative registry for every factor and score used by the platform.

This registry answers:
- What is the canonical owner (provider) for this factor?
- What is the canonical read source (table/service) right now?
- What refresh frequency applies?
- Who consumes it?
- Is any existing implementation deprecated?

## Key distinction (locked)
- **Canonical provider** is the stable abstraction.
- **Canonical storage/read source** may change later.

Example:
- Today: `TechnicalProvider` reads from `indicators_daily`.
- Future: it may read from `stock_technical_indicators`.
- Consumers must only depend on the provider layer.

## Registry record format (template)

| Item ID | Kind (meta/raw/derived/score) | Canonical Owner | Canonical Table/Service | Refresh Frequency | Consumers | Deprecated? | Deprecated By | Notes |
|---|---|---|---|---|---|---|---|---|

## Seeded SoTR (v1)

Notes:
- This is the first-pass registry for the **v1 factor set** discovered in Phase -1.
- “Consumers” reflects **current** repo consumers plus planned consumers (screeners/scores) where that is already implied by architecture.
- `Deprecated? = Yes` is used for **legacy/compat** sources that should not be used by new configs.

| Item ID | Kind (meta/raw/derived/score) | Canonical Owner | Canonical Table/Service | Refresh Frequency | Consumers | Deprecated? | Deprecated By | Notes |
|---|---|---|---|---|---|---|---|---|
| meta.market_cap | meta | MetaProvider | `stocks.market_cap` | periodic | Universes, filters, screeners | No |  | Stocks schema exists in multiple migration sets; provider normalizes. |
| meta.sector | meta | MetaProvider | `stocks.sector` | periodic | Universes, filters, screeners | No |  | Confidence drops when sector missing/unknown. |
| meta.industry | meta | MetaProvider | `stocks.industry` | periodic | Universes, filters, screeners | No |  | Same as sector. |
| meta.exchange | meta | MetaProvider | `stocks.exchange` | periodic | Universes, filters | No |  |  |
| meta.country | meta | MetaProvider | `stocks.country` | periodic | Universes, filters | No |  |  |
| meta.currency | meta | MetaProvider | `stocks.currency` | periodic | Universes, filters | No |  |  |
| meta.avg_dollar_volume_20d | meta | MetaProvider | computed from `raw_market_data_daily` | daily | Universes, liquidity gates | No |  | Not persisted canonically; computed in provider v1. |
| technical.rsi_14 | raw | TechnicalProvider | `indicators_daily` (canonical read) | daily | Trading Decision V3, Entry scoring, screeners | No |  | `indicators_daily` schema drift (wide vs narrow) must be normalized in provider. |
| technical.ema_20 | raw | TechnicalProvider | `indicators_daily` | daily | Trading Decision V3, Entry scoring | No |  |  |
| technical.sma_50 | raw | TechnicalProvider | `indicators_daily` | daily | Trading Decision V3, Entry scoring | No |  |  |
| technical.sma_200 | raw | TechnicalProvider | `indicators_daily` | daily | Composite/Entry, filters | No |  |  |
| technical.macd | raw | TechnicalProvider | `indicators_daily` | daily | Composite/Entry | No |  |  |
| technical.macd_signal | raw | TechnicalProvider | `indicators_daily` | daily | Composite/Entry | No |  |  |
| technical.macd_hist | raw | TechnicalProvider | `indicators_daily` | daily | Composite/Entry | No |  | Normalize naming variants (`macd_hist`, `macd_histogram`). |
| technical.relative_volume_20d | raw | TechnicalProvider | computed from `raw_market_data_daily.volume` | daily | Trading Decision V3 (`vol_ratio`), Entry | No |  | Not stored canonically; computed in provider v1. |
| fundamental.revenue_growth_yoy | raw | FinancialProvider | `fundamentals_snapshots.payload` | quarterly/periodic | Go fundamentals screeners, Quality scoring | No |  | JSON key drift exists; provider must normalize payload keys. |
| fundamental.operating_margin | raw | FinancialProvider | `fundamentals_snapshots.payload` | quarterly/periodic | Go fundamentals screeners, Quality scoring | No |  |  |
| fundamental.debt_to_equity | raw | FinancialProvider | `fundamentals_snapshots.payload` | quarterly/periodic | Go fundamentals screeners, Risk scoring | No |  |  |
| fundamental.revenue_cagr_3y | raw | FinancialProvider | computed from `fmp_financial_statements` | quarterly/periodic | Investment Health (today), future Quality | No |  | Table existence must be confirmed in prod migrations; keep confidence lower until confirmed. |
| fundamental.eps_cagr_3y | raw | FinancialProvider | computed from `fmp_financial_statements` | quarterly/periodic | Investment Health (today), future Quality | No |  | Same as above. |
| valuation.fair_value | raw | ValuationProvider | Fair Value v2 service | daily/periodic | Valuation scoring, profiles, UI | No |  | Canonical engine v2. |
| valuation.fair_value_gap_pct | raw | ValuationProvider | computed from FV2 + price | daily/periodic | Valuation scoring, Opportunity | No |  | Canonical price source should be `raw_market_data_daily` latest. |
| valuation.forward_pe | raw | ValuationProvider | FV2 method inputs_used | quarterly/periodic | Investment Health (PEG), valuation scoring | No |  | Coverage may be partial; factor confidence reflects missing features. |
| ai.exposure_score | raw | AIProvider | `stock_ai_insights.ai_exposure_score` | manual/periodic | Universes, profiles, explainability | No |  | Automated ingestion not yet confirmed; treat as partial coverage. |
| catalyst.earnings_calendar | raw | CatalystProvider | `earnings_calendar` | daily/periodic | Catalyst scoring, profiles, UI | No |  | Canonical earnings storage locked in Phase -1. |
| catalyst.days_to_earnings | raw | CatalystProvider | computed from `earnings_calendar.earnings_date` | daily/periodic | Catalyst scoring, profiles | No |  |  |
| catalyst.eps_estimate | raw | CatalystProvider | `earnings_calendar.eps_estimate` | event-driven | Catalyst scoring | No |  |  |
| catalyst.eps_actual | raw | CatalystProvider | `earnings_calendar.eps_actual` | event-driven | Catalyst scoring | No |  |  |
| catalyst.eps_surprise_pct_last | raw | CatalystProvider | `earnings_calendar.surprise_pct` | event-driven | Catalyst scoring | No |  | Column name differs across schemas (`surprise_pct` vs `surprise_percentage`); canonicalize via provider. |
| catalyst.eps_revision_90d | raw | CatalystProvider | N/A | N/A | ECS (future) | No |  | Missing: no provider/table. Gate ECS-dependent profiles. |
| risk.volatility_30d | raw | RiskProvider | computed from `raw_market_data_daily` | daily | Risk score, filters, sizing | No |  | Canonical v1 policy: compute deterministically from prices. |
| risk.max_drawdown_1y | raw | RiskProvider | computed from `raw_market_data_daily` | daily | Risk score, filters, sizing | No |  | Canonical v1 policy: compute deterministically from prices. |
| risk.var_95 | raw | RiskProvider | computed from `raw_market_data_daily` | daily | Risk score, filters | No |  | Canonical v1 policy: compute deterministically from prices. |
| risk.sharpe_ratio | raw | RiskProvider | computed from `raw_market_data_daily` | daily | Risk score | No |  | Optional in v1; compute deterministically if used. |
| risk.beta | raw | RiskProvider | `fundamentals_summary.beta` (fallback) | periodic | Risk score, filters | No |  | Ingestion/coverage unclear; compute confidence accordingly. |

### Quality domain (v1 placeholders)

| Item ID | Kind (meta/raw/derived/score) | Canonical Owner | Canonical Table/Service | Refresh Frequency | Consumers | Deprecated? | Deprecated By | Notes |
|---|---|---|---|---|---|---|---|---|
| quality.business_quality_score | score | ScoreEngine | ScoreDefinition (config; computed above providers) | quarterly/periodic | Investment score, profiles | No |  | v1 implementation should be computed from `fundamental.*` + `valuation.*` + `risk.*` availability; do not depend on growth-quality engines until they are factorized. |
| quality.financial_strength_score | score | ScoreEngine | ScoreDefinition (config; computed above providers) | quarterly/periodic | Investment score, profiles | No |  | v1 likely uses leverage + liquidity proxies from snapshots/statements; requires SoTR-confirmed fundamentals history. |
| quality.growth_quality_state | raw | QualityProvider | Growth-quality engines (runtime only) | periodic | Explainability (future), optional gating | No |  | Exists via `python-worker/app/api/growth_quality_endpoints.py` and underlying engines; **not** canonical for v1 ranking due to placeholder inputs + unclear persistence. |
| quality.early_warning_overall_risk | raw | QualityProvider | Early warning engine (runtime only) | periodic | Explainability (future), optional gating | No |  | Same as above; treat as informational until wired deterministically to DB-backed factor inputs. |

### Cross-domain synthesized (derived.* reserved)

| Item ID | Kind (meta/raw/derived/score) | Canonical Owner | Canonical Table/Service | Refresh Frequency | Consumers | Deprecated? | Deprecated By | Notes |
|---|---|---|---|---|---|---|---|---|
| derived.market_phase | derived | DerivedFactorEngine | DerivedFactorDefinition (config; computed above providers) | daily | Entry score, opportunity score, profiles | No |  | Depends on `technical.*` + price history; implementation in Phase 3. |
| derived.fgbi | derived | DerivedFactorEngine | DerivedFactorDefinition (config; computed above providers) | daily/periodic | Opportunity score, valuation reset | No |  | New factor; depends on valuation history / dispersion; blocked until valuation history percentiles are available. |
| derived.ecs | derived | DerivedFactorEngine | DerivedFactorDefinition (config; computed above providers) | daily/event-driven | Catalyst score, opportunity score | No |  | New factor; blocked until revisions provider exists (`catalyst.eps_revision_*`). |
| derived.opportunity_score | score | ScoreEngine | ScoreDefinition (config; computed above providers) | daily | Profiles, ranking | No |  | Requires derived.fgbi + derived.ecs + technical reset + risk adjustment; Phase 5+.

### Legacy / compat entries (do not use in new configs)

| Item ID | Kind (meta/raw/derived/score) | Canonical Owner | Canonical Table/Service | Refresh Frequency | Consumers | Deprecated? | Deprecated By | Notes |
|---|---|---|---|---|---|---|---|---|
| legacy.technical.stock_technical_indicators | raw | TechnicalProvider | `stock_technical_indicators` | daily | legacy/normalized schema consumers | Yes | `technical.*` via `indicators_daily` | Kept for future migration target; not canonical read source now. |
| legacy.catalyst.earnings_data | raw | CatalystProvider | `earnings_data` | event-driven | legacy loaders/table_mapping | Yes | `earnings_calendar` | Exists in `db/migrations/003_add_news_earnings_industry.sql` and referenced by `table_mapping.py`; treat as compat until migrated. |
| legacy.risk.risk_factors_table | raw | RiskProvider | `risk_factors` | daily | data summary admin API (possible) | Yes | computed risk from `raw_market_data_daily` | Table exists but no confirmed producer; optional v2 source later. |
| legacy.valuation.fair_value_v1 | raw | ValuationProvider | `python-worker/app/services/fair_value_service.py` | daily/periodic | validation diffs | Yes | FV2 | Keep as shadow comparator until parity is proven. |
| legacy.signals.stock_signals | raw |  | `stock_signals` (supabase baseline) | event-driven | legacy consumers | Yes | `signals` (or unified signal store) | Duplicate signal persistence exists (`stock_signals` vs `signals` vs `stock_signals_snapshots` in python-worker migrations). Canonical signal store to be selected later; screeners should not depend on signals tables directly. |
| legacy.signals.signals | raw |  | `signals` (python-worker) | event-driven | Trading Decision V3 | No |  | Current Trading Decision V3 persists to `signals`; keep until signal persistence is unified. |
| legacy.signals.stock_signals_snapshots | raw |  | `stock_signals_snapshots` (python-worker migrations) | event-driven | legacy signal architecture | Yes | `signals` (or unified) | Present in `python-worker/migrations/create_signal_tables.sql`; not canonical for factor engine. |
| legacy.fundamentals.stock_financials | raw | FinancialProvider | `stock_financials` (supabase baseline) | quarterly | normalized fundamentals consumers | Yes | `fundamentals_snapshots` (v1) | Normalized schema exists but current screeners largely use `fundamentals_snapshots.payload`; treat normalized as future migration target once provider layer is stable. |
| legacy.fundamentals.fundamentals_summary | raw | FinancialProvider | `fundamentals_summary` (python-worker init schema) | periodic | legacy UI/ingestion | Yes | `fundamentals_snapshots` (v1) | Exists in python-worker init migration; not canonical for factor engine unless adopted explicitly. |

### Field definitions
- **Canonical Owner**: `MetaProvider | FinancialProvider | TechnicalProvider | ValuationProvider | AIProvider | CatalystProvider | RiskProvider | DerivedFactorEngine | ScoreEngine`
- **Refresh Frequency**: `intraday|daily|weekly|quarterly|event-driven|manual`
- **Deprecated?**
  - `Yes` means not used by any new configs and scheduled for removal.
  - `No` means still active.

## Seeded canonical decisions (locked)

### Technical
- Canonical Owner: `TechnicalProvider`
- Canonical read source (Phase 2): `indicators_daily`
- Rationale:
  - Trading Decision V3 already depends on it
  - minimizes disruption

### Valuation
- Canonical Owner: `ValuationProvider`
- Canonical engine: Fair Value v2 (`python-worker/app/fair_value_v2/*`)
- Fair Value v1 remains:
  - non-canonical
  - used for regression comparison and validation diffs

## Known duplicate ecosystems to track here
These must be captured explicitly as SoTR rows with deprecation status.

### Technical tables
- `indicators_daily` (canonical read for now)
- `stock_technical_indicators` (normalized, non-canonical read for now)

### Fundamentals storage
- `fundamentals_snapshots` (canonical latest snapshot for Go screeners)
- `stock_financials` (normalized fundamentals)
- `fmp_financial_statements` (historical statements store used by some scorers)

### Signals / decisions persistence
- `signals` table (Trading Decision V3)
- `stock_signals` table (baseline schema)

### Fair value engines
- v2 (canonical)
- v1 (legacy validation)

## Output requirements
By the end of Phase 1:
- Every factor referenced by a UniverseDefinition, ScoreDefinition, or ScreeningProfile exists in SoTR.
- Every canonical decision is explicitly recorded.
- Every duplicate implementation has a deprecation plan entry (even if deprecation is “not yet”).
