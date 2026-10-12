# Phase -1 — Data Capability Audit

## Purpose
The biggest risk is not architecture. It is **data availability and quality**.

Before implementing the Factor Provider Layer, establish what data exists today, what is missing, and what is reliable enough to use in rankings.

This audit produces a single artifact: the **Data Capability Matrix**.

## Architectural constraints (locked)
- **Canonical technical read source (Phase 2)**: `indicators_daily`
- **Canonical valuation provider (Phase 2)**: Fair Value v2 (`python-worker/app/fair_value_v2/*`)
- **Factor IDs**: dotted namespaces (e.g., `technical.rsi_14`)
- **Confidence**: integer 0–100, derived from structured components (see below)

## Data Capability Matrix (template)
Fill one row per **Raw Factor**, **Derived Factor**, and **ScoreDefinition** that will be used by any screening profile.

| ID | Kind (meta/raw/derived/score) | Namespace | Owner (Provider/Engine) | Available (✅/⚠️/❌) | Historical (✅/⚠️/❌) | Refresh Frequency | Canonical Source (table/service) | Current Consumers | Gaps / Notes |
|---|---|---|---|---|---|---|---|---|---|

## Current findings (repo-backed, v1 scope)

Notes on evidence:
- **Schema evidence** comes from migrations in:
  - `supabase/migrations/*`
  - `python-worker/migrations/*`
  - `db/migrations/*`
- **Refresh evidence** comes from `python-worker/app/data_management/refresh_manager.py` (and related ingestion/services).
- “Available” below means **the system has a storage + access path implemented in code/migrations**. It does not guarantee data exists for every symbol in your DB today.

| ID | Kind (meta/raw/derived/score) | Namespace | Owner (Provider/Engine) | Available (✅/⚠️/❌) | Historical (✅/⚠️/❌) | Refresh Frequency | Canonical Source (table/service) | Current Consumers | Gaps / Notes |
|---|---|---|---|---|---|---|---|---|---|
| meta.market_cap | meta | meta | MetaProvider | ✅ | ✅ | periodic | `stocks.market_cap` (`supabase/migrations/001_baseline_schema.sql`; `python-worker/migrations/init_database_complete.sql`) | Go screeners, Streamlit filters, future universes | Two stocks schemas exist (UUID vs SERIAL id); treat provider as canonical interface. |
| meta.sector | meta | meta | MetaProvider | ✅ | ✅ | periodic | `stocks.sector` (baseline + python-worker init schema) | Go screeners, future universes | Sector/industry quality depends on vendor mapping; confidence should reflect missing/unknown. |
| meta.industry | meta | meta | MetaProvider | ✅ | ✅ | periodic | `stocks.industry` | Go screeners, future universes | Same as sector. |
| meta.exchange | meta | meta | MetaProvider | ✅ | ✅ | periodic | `stocks.exchange` (baseline + python-worker init schema) | Screeners/universes | None. |
| meta.country | meta | meta | MetaProvider | ✅ | ✅ | periodic | `stocks.country` | Screeners/universes | None. |
| meta.currency | meta | meta | MetaProvider | ✅ | ✅ | periodic | `stocks.currency` | Screeners/universes | None. |
| meta.avg_dollar_volume_20d | meta | meta | MetaProvider | ⚠️ | ✅ | daily | Derived by provider from `raw_market_data_daily` (close*volume rolling), storage varies | Watchlists/screeners (future) | Not stored as canonical column today; compute on demand or persist later. Requires reliable daily price+volume coverage. |
| technical.rsi_14 | raw | technical | TechnicalProvider | ⚠️ | ✅ | daily | Canonical read: `indicators_daily` | Trading Decision V3, Composite Score, future profiles | **Schema drift risk**: `supabase/migrations/020_add_missing_tables.sql` defines wide `indicators_daily(rsi_14, ema_20, sma_50, ...)` but `python-worker/migrations/init_database_complete.sql` defines narrow `(indicator_name, indicator_value, time_period)`. Provider must normalize both or pick one runtime schema. |
| technical.ema_20 | raw | technical | TechnicalProvider | ⚠️ | ✅ | daily | `indicators_daily` | Trading Decision V3, Composite Score | Same schema drift as above. |
| technical.sma_50 | raw | technical | TechnicalProvider | ⚠️ | ✅ | daily | `indicators_daily` | Trading Decision V3, Composite Score | Same schema drift as above. |
| technical.sma_200 | raw | technical | TechnicalProvider | ⚠️ | ✅ | daily | `indicators_daily` (or normalized `stock_technical_indicators.sma_200`) | Composite Score, screeners (future) | Not present in wide `indicators_daily` migration in `020_add_missing_tables.sql` (only sma_50/sma_200 exist there; yes). Narrow schema requires `indicator_name='sma_200'`. |
| technical.macd | raw | technical | TechnicalProvider | ⚠️ | ✅ | daily | `indicators_daily.macd` / (`indicator_name='macd'`) | Trading Decision V3 (features), Composite Score | Same schema drift. |
| technical.macd_signal | raw | technical | TechnicalProvider | ⚠️ | ✅ | daily | `indicators_daily.macd_signal` / (`indicator_name='macd_signal'`) | Composite Score | Same schema drift. |
| technical.macd_hist | raw | technical | TechnicalProvider | ⚠️ | ✅ | daily | `indicators_daily.macd_hist` / (`indicator_name='macd_histogram'`) | Composite Score | Same schema drift + naming variants (`macd_hist`, `macd_histogram`). |
| technical.relative_volume_20d | raw | technical | TechnicalProvider | ⚠️ | ✅ | daily | Derived by provider from `raw_market_data_daily.volume` | Trading Decision V3 (`vol_ratio` concept), Entry/Opportunity | Not persisted as canonical factor; computed on demand. Requires price history coverage. |
| fundamental.revenue_growth_yoy | raw | fundamental | FinancialProvider | ✅ | ⚠️ | quarterly/periodic | `fundamentals_snapshots.payload` (supabase `020_add_missing_tables.sql`; also python-worker init schema has `fundamentals_snapshots`) | Go fundamentals screeners | Payload key drift exists (Go repo checks multiple JSON keys). Historical is limited unless snapshot history is stored (supabase snapshot uses `(stock_symbol, as_of_date)` primary key; python-worker init schema uses `symbol UNIQUE` (!) which limits history). |
| fundamental.operating_margin | raw | fundamental | FinancialProvider | ✅ | ⚠️ | quarterly/periodic | `fundamentals_snapshots.payload` | Go fundamentals screeners | Same snapshot-history ambiguity as above. |
| fundamental.gross_margin | raw | fundamental | FinancialProvider | ⚠️ | ✅ | quarterly/periodic | `fmp_financial_statements` (queried by `InvestmentHealthService`) | Investment Health | `fmp_financial_statements` is referenced in code but not confirmed in supabase baseline migrations; ensure table exists in prod DB schema. |
| fundamental.debt_to_equity | raw | fundamental | FinancialProvider | ✅ | ⚠️ | quarterly/periodic | `fundamentals_snapshots.payload` | Go fundamentals screeners | Same snapshot-history ambiguity. |
| fundamental.revenue_cagr_3y | raw | fundamental | FinancialProvider | ⚠️ | ✅ | quarterly/periodic | Computed by provider from `fmp_financial_statements` (see `InvestmentHealthService._revenue_cagr_3y`) | Investment Health | Requires statements table coverage (annual income). Not yet standardized as a stored factor. |
| fundamental.eps_cagr_3y | raw | fundamental | FinancialProvider | ⚠️ | ✅ | quarterly/periodic | Computed by provider from `fmp_financial_statements` (see `InvestmentHealthService._eps_cagr_3y`) | Investment Health | Same as above. |
| valuation.fair_value | raw | valuation | ValuationProvider | ✅ | ✅ | daily/periodic | Fair Value v2 (`python-worker/app/fair_value_v2/*`) | Stock overview, valuation scoring, future profiles | Engine exists and is already used for feature sourcing in `InvestmentHealthService` via `FairValueV2Service`. Persistence for FV2 results is not yet standardized at factor level. |
| valuation.fair_value_gap_pct | raw | valuation | ValuationProvider | ✅ | ✅ | daily/periodic | Derived from FV2 fair value + current price in provider | Profiles, valuation scoring (future) | Must define canonical `current_price` source (likely `raw_market_data_daily` latest). |
| valuation.forward_pe | raw | valuation | ValuationProvider | ⚠️ | ⚠️ | quarterly/periodic | FV2 method inputs_used (see `InvestmentHealthService._compute_valuation`) | Investment Health (PEG) | Depends on FV2 feature availability (`eps_forward`) and growth proxy. Not guaranteed for all symbols. |
| ai.exposure_score | raw | ai | AIProvider | ⚠️ | ❌ | manual/periodic | `stock_ai_insights.ai_exposure_score` (`supabase/migrations/001_baseline_schema.sql`) | Watchlist engines (partial), future universes/profiles | Storage exists, but repo evidence of automated refresh/ingestion is unclear. Historical coverage not established. |
| catalyst.days_to_earnings | raw | catalyst | CatalystProvider | ✅ | ✅ | daily/periodic | **Canonical**: `earnings_calendar` (`python-worker/app/repositories/earnings_calendar_repository.py`; also created in `python-worker/migrations/fix_missing_tables.sql`) | Earnings UI, future catalyst score | Canonical decision: use `earnings_calendar` for CatalystProvider. Treat `earnings_data` as legacy/compat until migrated. |
| catalyst.eps_surprise_pct_last | raw | catalyst | CatalystProvider | ⚠️ | ✅ | event-driven | `earnings_data.surprise_percentage` (`db/migrations/003_add_news_earnings_industry.sql`) | Earnings UI, future ECS | Existence depends on which migration set is applied (supabase vs db/migrations vs python-worker init). Canonicalize in SoTR. |
| catalyst.eps_revision_90d | raw | catalyst | CatalystProvider | ❌ | ❌ | N/A | N/A | Future Catalyst Score / ECS | No repo-backed provider/table for revisions yet; must be added before profiles depend on it (or gate). |
| risk.beta | raw | risk | RiskProvider | ⚠️ | ✅ | periodic | `fundamentals_summary.beta` (`python-worker/migrations/init_database_complete.sql`) OR `risk_factors.beta` (`python-worker/migrations/031_create_missing_tables.sql`) | Future risk score, universes, sizing | Multiple potential sources; ingestion not confirmed. Provider should expose one canonical and compute confidence accordingly. |
| risk.max_drawdown_1y | raw | risk | RiskProvider | ✅ | ✅ | daily | **Canonical v1**: computed from `raw_market_data_daily` history | Future risk score, opportunity | v2 optional: read from `risk_factors.max_drawdown` once a producer exists. |
| catalyst.earnings_calendar | raw | catalyst | CatalystProvider | ✅ | ✅ | daily/periodic | **Canonical**: `earnings_calendar` (repo + migration) | Earnings calendar UI/services | Legacy/compat: `earnings_data` exists via `db/migrations/003_add_news_earnings_industry.sql` and is referenced in `python-worker/app/data_management/table_mapping.py`. Align SoTR + table_mapping later. |
| catalyst.eps_estimate | raw | catalyst | CatalystProvider | ✅ | ✅ | event-driven | **Canonical**: `earnings_calendar.eps_estimate` | Earnings calendar, future ECS | Legacy/compat: `earnings_data.eps_estimate`. Normalize naming and ensure ingestion writes to canonical table. |
| catalyst.eps_actual | raw | catalyst | CatalystProvider | ✅ | ✅ | event-driven | **Canonical**: `earnings_calendar.eps_actual` | Earnings calendar | Legacy/compat: `earnings_data.eps_actual`. |
| risk.volatility_30d | raw | risk | RiskProvider | ✅ | ✅ | daily | **Canonical v1**: computed from `raw_market_data_daily` returns | Future risk score | v2 optional: read from `risk_factors.volatility` once producer exists. |
| risk.sharpe_ratio | raw | risk | RiskProvider | ✅ | ✅ | daily | **Canonical v1**: computed from `raw_market_data_daily` returns | Future risk score | v2 optional: read from `risk_factors.sharpe_ratio` once producer exists. |
| risk.var_95 | raw | risk | RiskProvider | ✅ | ✅ | daily | **Canonical v1**: computed from `raw_market_data_daily` returns distribution | Future risk score | v2 optional: read from `risk_factors.var_95` once producer exists. |
| risk.risk_score | raw | risk | RiskProvider | ⚠️ | ✅ | daily | v2 candidate: `risk_factors.risk_score` | Future risk score | Keep as non-canonical until producer is identified; v1 can compute a simple composite risk score later via ScoreDefinitions. |
| quality.growth_quality_state | raw | quality | QualityProvider (or Derived/ScoreEngine) | ⚠️ | ⚠️ | periodic | Growth quality ecosystem exists (`python-worker/app/api/growth_quality_endpoints.py`, `app/signal_engines/growth_quality_engine.py`, `app/indicators/growth_health_classifier.py`) | Growth-quality API, potential quality group score | There is an analysis engine, but persistence/canonical factor snapshots are not defined. Inputs may use placeholders and not fully wired to DB in all code paths. |
| quality.early_warning_overall_risk | raw | quality | QualityProvider (or Derived/ScoreEngine) | ⚠️ | ⚠️ | periodic | Early warning engine exists (`EarlyWarningEngine` used in `growth_quality_endpoints.py`) | Growth-quality API | Similar: exists as computation, but needs factorization + standard inputs to be reliable.
| derived.market_phase | derived | derived | DerivedFactorEngine | ⚠️ | ✅ | daily | Derived from technical raw factors (RSI/MA alignment/price history) | Entry/opportunity scoring | No canonical implementation exists yet; must be defined in Derived registry (Phase 3). |
| derived.fgbi | derived | derived | DerivedFactorEngine | ❌ | ❌ | daily/periodic | N/A | Opportunity / Valuation reset | New derived factor; depends on valuation history percentiles and/or method dispersion; not implemented. |
| derived.ecs | derived | derived | DerivedFactorEngine | ❌ | ❌ | daily/event | N/A | Catalyst score / Opportunity | New derived factor; likely blocked until revisions provider exists. |
| derived.opportunity_score | score | derived | ScoreEngine | ❌ | ❌ | daily | N/A | Opportunity layer | Depends on derived.fgbi + derived.ecs + technical reset factors; not implemented. |

### Field definitions
- **Available**
  - ✅ present for most symbols in target universes
  - ⚠️ partially present (coverage gaps, manual refresh, sparse symbols)
  - ❌ not present
- **Historical**
  - ✅ sufficient history for backtests / trend-derived factors
  - ⚠️ limited history
  - ❌ no history
- **Refresh Frequency**
  - `intraday`, `daily`, `weekly`, `quarterly`, `event-driven`, `manual`

## Confidence model (locked)
Confidence is stored as **0–100 integer** for UI and filtering.

Internally, compute components (each 0–100):
- `source_reliability`
- `data_freshness`
- `coverage`
- `calculation_stability`

Then:

```
confidence = round(
  0.40 * source_reliability
+ 0.30 * data_freshness
+ 0.20 * coverage
+ 0.10 * calculation_stability
)
```

## Initial v1 audit scope (minimum viable factor set)
This list is intentionally small: it is the minimum needed to support v1 universes and a few screening profiles.

### meta.* (MetaProvider)
- `meta.market_cap`
- `meta.sector`
- `meta.industry`
- `meta.exchange`
- `meta.country`
- `meta.currency`
- `meta.avg_dollar_volume_20d`

### technical.* (TechnicalProvider, canonical read: indicators_daily)
- `technical.rsi_14`
- `technical.ema_20`
- `technical.sma_50`
- `technical.sma_200` (if available)
- `technical.macd`
- `technical.macd_signal`
- `technical.macd_hist`
- `technical.relative_volume_20d` (may be computed from price/volume if not stored)

### fundamental.* (FinancialProvider)
- `fundamental.revenue_growth_yoy`
- `fundamental.operating_margin`
- `fundamental.gross_margin`
- `fundamental.debt_to_equity`
- `fundamental.revenue_cagr_3y`
- `fundamental.eps_cagr_3y`

### quality.* (Derived Factor Engine / ScoreDefinitions)
- `quality.business_quality_score`
- `quality.financial_strength_score`

### valuation.* (ValuationProvider, canonical engine: Fair Value v2)
- `valuation.fair_value`
- `valuation.fair_value_gap_pct`
- `valuation.forward_pe`

### ai.* (AIProvider)
- `ai.exposure_score`

### catalyst.* (CatalystProvider)
- `catalyst.days_to_earnings`
- `catalyst.eps_surprise_pct_last` (if available)

### risk.* (RiskProvider)
- `risk.max_drawdown_1y` (if available)
- `risk.beta` (if available)
- `risk.leverage` (can map from debt metrics)

### derived.* (reserved for cross-domain synthesized)
- `derived.market_phase`
- `derived.fgbi`
- `derived.ecs`
- `derived.opportunity_score`

## Output: Screening readiness
For each planned **UniverseDefinition** and **ScreeningProfile**, include a “readiness assessment”:
- **Ready now**: all required raw factors available + sufficient confidence
- **Gated**: profile can run but must skip/relax certain filters or downgrade weights
- **Blocked**: required factors missing
