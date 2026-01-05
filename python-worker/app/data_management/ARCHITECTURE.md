# Data Management Architecture Context

## Goals

- Centralize provider SDK/HTTP logic in provider clients.
- Keep data sources as thin adapters implementing `BaseDataSource`.
- Ensure ingestion, validation, refresh state, and audit are Postgres-backed and observable.
- Make adding new providers low-risk and consistent.

## Layering (clean architecture)

- `app/providers/<provider>/client.py`
  - Owns SDK/HTTP calls, auth, retries, rate limiting, pagination, response normalization.
  - Returns internal normalized objects (e.g., `pd.DataFrame`, `dict`, `list[dict]`).
- `app/data_sources/<provider>_source.py`
  - Thin adapter implementing `BaseDataSource`.
  - Delegates to the provider client. No networking, no rate limiting.
- `app/data_management/refresh_manager.py`
  - Orchestrates which datasets to refresh and when.
  - Persists refresh state and audit into Postgres tables.
- Repositories/utilities
  - Own DB access patterns and UPSERT logic.

## Provider client contract (recommended)

Every provider client should implement a consistent internal API (methods may return empty values if the provider doesn’t support them):

- `fetch_price_data(symbol: str, **kwargs) -> pd.DataFrame`
- `fetch_current_price(symbol: str) -> Optional[float]`
- `fetch_symbol_details(symbol: str) -> Dict[str, Any]`
- `fetch_fundamentals(symbol: str) -> Dict[str, Any]`
- `fetch_news(symbol: str, limit: int = 10) -> List[Dict[str, Any]]`
- `fetch_earnings(symbol: str) -> List[Dict[str, Any]]`
- `fetch_technical_indicators(symbol: str, indicator_type: str, **kwargs) -> Dict[str, Any]`
- `fetch_industry_peers(symbol: str) -> Dict[str, Any]`
- `is_available() -> bool`

## Adding a brand-new data source (template)

### 1) Create the provider client

- Add: `app/providers/<new_provider>/client.py`
- Responsibilities:
  - Configuration from `settings` (API key, base URL, timeouts)
  - Rate limiting
  - Retries/backoff
  - Response parsing + normalization
  - Consistent error typing (raise provider-specific exceptions only here)

### 2) Create the thin adapter source

- Add: `app/data_sources/<new_provider>_source.py`
- Responsibilities:
  - Implement `BaseDataSource` methods.
  - Construct and hold `self._client`.
  - Delegate all calls to `self._client`.

### 3) Register in the factory/selection logic

- Update the selection logic (wherever `get_data_source()` or adapter registry lives) to allow choosing the provider by config.

### 4) Integrate with DataRefreshManager

- Ensure `DataRefreshManager` uses `BaseDataSource` methods only.
- Add/confirm mappings in refresh strategies so each `DataType` refresh:
  - Fetches via the data source
  - Writes to the correct Postgres tables
  - Updates `data_ingestion_state`
  - Emits audit rows/events

### 5) Add tests

- Unit-level (fast): provider client parsing/normalization with mocked HTTP responses.
- Integration-level (optional): real provider API + Postgres writes.
- E2E: run a refresh end-to-end and assert table rows exist via SQL.

## Notes on workflows vs refresh_manager

- Prefer `DataRefreshManager` as the authoritative ingestion/refresh orchestrator.
- If workflows are used for multi-stage pipelines (ingestion → validation → indicators → signals), ensure:
  - Workflow state is persisted (tables/migrations exist).
  - Each stage delegates to existing services (`DataRefreshManager`, `IndicatorService`, validators) rather than duplicating ingestion logic.

## Data completeness and missing-fields management (implementation)

### Goals

- Make signal engines deterministic by separating:
  - Provider fetch (raw)
  - Derived calculations (time series + cohort stats)
  - Persisted snapshots (fast reads for engines)
- Avoid on-the-fly computation of cohort metrics (sector medians/percentiles).
- Track provenance and freshness so engines can degrade gracefully when inputs are missing.

### Missing field categories

- **Provider-available point-in-time**
  - Examples: `market_cap`, `pe`, `pb`, current price.
  - Strategy: fetch regularly; cache into Postgres; treat provider gaps as nullable.
- **Provider-available time series (raw statements / OHLCV)**
  - Examples: quarterly revenue, quarterly operating income, daily OHLCV.
  - Strategy: persist raw series; derive indicators in a second stage.
- **Derived per-stock indicators**
  - Examples: revenue YoY growth, growth acceleration, margin trends, volatility.
  - Strategy: compute from persisted time series and store as derived tables.
- **Derived cohort/benchmark indicators**
  - Examples: sector median PE, sector 75th percentile operating margin.
  - Strategy: nightly batch job across a defined universe and store as sector snapshots.
- **Narrative tags / qualitative overlays**
  - Examples: AI exposure.
  - Strategy: compute nightly (or weekly) and store as a multiplier overlay; do not block MVP.

### Data quality + provenance fields (recommended)

Each derived dataset should carry enough metadata to let engines reason about reliability:

- `as_of` / `date`
- `source` (provider name or internal job)
- `confidence` (e.g., `low|medium|high`)
- `sample_size` for cohort stats (e.g., number of stocks contributing to sector medians)
- `freshness_hours` (optional convenience field)

Engines should:

- Prefer derived/snapshotted values over ad-hoc provider reads.
- Fall back to simpler logic when a metric is missing.
- Include missing-metric notes in reasoning.

## Derived datasets (tables) for signal engines

### 1) Sector daily metrics (benchmarks)

Purpose:

- Relative valuation discipline (e.g., PE vs sector median)
- Sector percentiles (e.g., operating margin vs sector 75th)

Recommended table (illustrative):

- `sector_daily_metrics`
  - `date`
  - `universe_id` (e.g., `all_us`, `watchlist_v1`)
  - `sector_schema` (e.g., `yahoo`, `gics`, `internal_v1`)
  - `sector_key` (normalized)
  - `median_revenue_yoy_growth`
  - `median_operating_margin`
  - `p75_operating_margin`
  - `median_pe`
  - `median_ps` (optional)
  - `median_pb` (optional)
  - `stock_count`
  - `valid_pe_count` (optional)

Notes:

- Compute nightly in a batch job; do not compute on-demand per request.
- Store counts so engines can reduce confidence when sample sizes are small.

### 2) Stock growth + margin time series (per-stock derived)

Purpose:

- Growth engines (acceleration)
- Margin trajectory (QoQ / multi-quarter trend)

Recommended table (illustrative):

- `stock_growth_timeseries`
  - `symbol`
  - `period_end_date`
  - `revenue`
  - `revenue_yoy_growth`
  - `revenue_yoy_growth_accel`
  - `gross_profit` (optional)
  - `operating_income` (optional)
  - `gross_margin`
  - `operating_margin`
  - `as_of`
  - `source`

Notes:

- Prefer computing margins from statements (`gross_profit/revenue`, `operating_income/revenue`) over relying on provider precomputed ratios.
- Acceleration requires at least two YoY growth points (typically 8 quarters of revenue).

### 3) Liquidity + volatility daily

Purpose:

- Risk/confidence scoring
- Trade feasibility (especially for momentum/swing engines)

Recommended table (illustrative):

- `stock_liquidity_daily`
  - `symbol`
  - `date`
  - `avg_volume_30d`
  - `avg_dollar_volume_30d`
  - `volatility_20d` (std dev of returns) and/or `atr_pct_14`
  - `liquidity_tier` (derived, optional)
  - `as_of`
  - `source`

## AI classification overlay (nightly symbol tagging)

### Why store AI tagging on the symbol record

- Keeps signal engines fast and deterministic.
- Avoids repeated NLP / keyword logic inside each engine.
- Enables auditing and backtesting (tag is stable for a given date).

### Recommended storage

Prefer one of these patterns:

- **Option A: columns on symbol table** (simple MVP)
  - `ai_flag` (bool)
  - `ai_score` (float multiplier or 0..1 score)
  - `ai_confidence` (text)
  - `ai_reasoning` (text or JSON)
  - `ai_as_of` (timestamp/date)
  - `ai_source` (text)
- **Option B: separate daily history table** (better for backtests)
  - `symbol_ai_classification_daily(symbol, date, ai_flag, ai_score, ai_confidence, ai_reasoning, source)`

Engines should consume:

- `ai_score` as a capped multiplier (e.g., within `[0.7, 1.3]`), not as a core valuation pillar.
- `ai_confidence` / `ai_as_of` to reduce weight when stale or low confidence.

### Classification approach (phased)

- **Phase 1 (no LLM required)**
  - Use sector/industry/subindustry mapping + keyword frequency from provider business summary.
  - Output: `ai_flag`, `ai_score`, `ai_reasoning`.
- **Phase 2 (optional, higher cost)**
  - Use earnings transcripts / filings and compute AI density and consistency.
  - Output: richer `ai_reasoning` and higher confidence.

### Nightly job contract

The AI tagging job should:

- Read:
  - symbol list (universe)
  - provider symbol details (summary/industry)
  - existing tags (for incremental updates)
- Write:
  - updated tag fields + provenance (`ai_as_of`, `ai_source`)
- Emit:
  - audit events and counts (classified, changed, unchanged, failed)

## Refresh orchestration and dependency ordering

Recommended ordering for nightly pipelines:

- Price/OHLCV refresh (daily)
  - Yahoo: `fetch_price_data(symbol, interval="1d")`
  - Persist raw OHLCV into `raw_market_data_daily` (keyed by `stock_symbol`, `trade_date`).
- Symbol metadata refresh (daily/weekly)
  - Yahoo: `fetch_symbol_details(symbol)`
  - Persist: name/sector/industry/market cap/currency/exchange + business summary (used by overlays).
- Fundamentals refresh (daily)
  - Yahoo: `fetch_fundamentals(symbol)`
    - Internally uses Yahoo `ticker.financials`, `ticker.balance_sheet`, `ticker.cashflow` and `ticker.info/fast_info`.
  - Persist snapshots into `fundamentals_snapshots` (UPSERT on `(stock_symbol, as_of_date)`).
- News refresh (daily, best-effort)
  - Yahoo: `fetch_news(symbol, limit=N)`
  - Persist into the news table(s) used by the app (or store as provider snapshots if not normalized yet).
- Earnings refresh (daily)
  - Yahoo: `fetch_earnings(symbol)` (per-symbol)
  - Yahoo: `fetch_earnings_calendar(symbols, start_date, end_date)` / `fetch_earnings_for_date(date)` (universe-level)
  - Persist into earnings table(s) / calendar table(s) used by the app.
- Industry peers refresh (weekly or when sector/industry changes)
  - Yahoo: `fetch_industry_peers(symbol)`
  - Persist into `industry_peers`.
- Derived technical indicators refresh (daily)
  - Yahoo-derived (computed from persisted OHLCV): `fetch_technical_indicators(symbol, ...)`
  - Persist into `indicators_daily` (keyed by `stock_symbol`, `trade_date`).
- Derived per-stock fundamentals indicators refresh (nightly)
  - Compute growth, margins, volatility, liquidity, etc. from persisted statements + OHLCV.
- Cohort benchmarks refresh (nightly)
  - Compute sector medians/percentiles over a defined universe using persisted per-stock metrics.
- Symbol overlays refresh (nightly)
  - AI tagging based on Yahoo business summary/industry metadata.
- Signal caching/snapshots (optional)
  - Precompute signals/summaries for low-latency UI/API reads.

Engines should rely on the persisted outputs of these jobs rather than re-fetching provider data during scoring.
