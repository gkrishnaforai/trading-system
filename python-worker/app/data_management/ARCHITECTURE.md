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
