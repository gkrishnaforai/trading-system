# Data Sources Architecture + FinancialModelingPrep (FMP) Provider Plan

This document describes how the **python-worker** data-source system is structured today and how to add a new provider (Financial Modeling Prep / **FMP**) so that services work by switching the configured provider.

## 1) Current Architecture Overview

### 1.1 Key concepts

- **Provider Client**
  - Owns all HTTP/SDK logic, retries, rate limiting, and response normalization.
  - Example: `app/providers/yahoo_finance/client.py` (`YahooFinanceClient`).

- **Thin Data Source (legacy interface)**
  - Implements `app/data_sources/base.py::BaseDataSource` and delegates to a provider client.
  - Example: `app/data_sources/yahoo_finance_source.py` (`YahooFinanceSource`).

- **Adapter (new plugin architecture)**
  - Wraps/creates a source and adds lifecycle management: initialization, config validation, availability caching, metrics.
  - Base class: `app/data_sources/adapters/base_adapter.py::BaseDataSourceAdapter`.
  - Factory: `app/data_sources/adapters/factory.py`.

- **CompositeDataSource (primary + fallback)**
  - Used when `PRIMARY_DATA_SOURCE` and `FALLBACK_DATA_SOURCE` are configured.
  - Example: `app/data_sources/composite_source.py`.

### 1.2 How a provider is selected

`app/data_sources/__init__.py::get_data_source()`:

- Tries **adapter factory** first (`create_adapter(name)`).
- Builds a config dict per provider name.
- Calls `adapter.initialize(config)`.
- If `use_fallback=True` and the name is the configured primary, returns `CompositeDataSource(primary, fallback)`.
- Falls back to legacy registry if adapter creation fails.

### 1.3 Minimum interface expected by services

The abstract base interface is in:
- `app/data_sources/base.py::BaseDataSource`

Required methods:
- `fetch_price_data(symbol, start_date=None, end_date=None, period="1y", interval="1d") -> Optional[pd.DataFrame]`
- `fetch_current_price(symbol) -> Optional[float]`
- `fetch_fundamentals(symbol) -> Dict[str, Any]`
- `fetch_news(symbol, limit=10) -> List[Dict[str, Any]]`
- `fetch_earnings(symbol) -> List[Dict[str, Any]]`
- `fetch_industry_peers(symbol) -> Dict[str, Any]`
- `is_available() -> bool`
- `name` property

### 1.4 Additional methods used in practice (important for “drop-in” parity)

Several services call provider-specific methods that are not part of `BaseDataSource` but are used by the system:

- `fetch_earnings_calendar(symbols=None, start_date=None, end_date=None)`
  - Used by `app/services/earnings_calendar_service.py`.
- `fetch_earnings_for_date(earnings_date, symbols=None)`
  - Used by `app/services/earnings_calendar_service.py`.
- `fetch_actions(symbol)` / `fetch_dividends(symbol)` / `fetch_splits(symbol)`
  - Used by `DataRefreshManager._refresh_corporate_actions()`.
- `fetch_financial_statements(symbol, quarterly=True)`
  - Used by `DataRefreshManager`.
- `fetch_symbol_details(symbol)`
  - Used by some pages/services.
- `fetch_quarterly_earnings_history(symbol)`
  - Used by some flows.
- `fetch_analyst_recommendations(symbol)`
  - Yahoo implements this.

If you want **provider switching** to be seamless across the app, the new provider should implement these as well.

## 2) Data Normalization Contracts (what providers should return)

These shapes are what downstream code expects.

### 2.1 Price Data (`fetch_price_data`)

Return a `pd.DataFrame` with:
- A datetime-like index (preferred).
- Columns (case-insensitive is sometimes tolerated, but normalize anyway):
  - `open`, `high`, `low`, `close`, `volume`
- Optional but useful:
  - `adj_close`

### 2.2 News (`fetch_news`)

Return `List[Dict]` where items include:
- `title`
- `publisher`
- `url` (or `link`)
- `published` or `published_date` (ISO string or datetime)

### 2.3 Earnings (`fetch_earnings`)

Return items with at least:
- `earnings_date` (required to persist)

Optionally:
- `earnings_at` (datetime / ISO string)
- `earnings_timezone` (e.g., `America/New_York`)
- `earnings_session` (pre/after/unknown)
- `eps_estimate`, `eps_actual`
- `revenue_estimate`, `revenue_actual`
- `surprise_percentage`

### 2.4 Industry peers (`fetch_industry_peers`)

Return dict:
- `sector`
- `industry`
- `peers`: list of peer entries (at least symbol)

### 2.5 Financial statements

Return a dict with keys:
- `income_statement`: list[dict]
- `balance_sheet`: list[dict]
- `cash_flow`: list[dict]

Each row should include a date field (`date` or equivalent) and numeric values.

## 3) FinancialModelingPrep (FMP) Provider: Implementation Plan

FMP docs (requested):
- https://site.financialmodelingprep.com/developer/docs#analyst

### 3.1 New files to add

#### Provider client
- `app/providers/financial_modeling_prep/client.py`

Responsibilities:
- `requests.Session()`
- `RateLimiter`
- retries with exponential backoff for 429/5xx/timeouts
- response normalization into the contracts above

Suggested config dataclass:
- `FinancialModelingPrepConfig`
  - `api_key: str`
  - `base_url: str = "https://financialmodelingprep.com/stable"`
  - `timeout: int = 30`
  - `max_retries: int = 3`
  - `retry_delay: float = 1.0`
  - `rate_limit_calls: int = 60` (example)
  - `rate_limit_window: float = 60.0`

#### Thin source
- `app/data_sources/financial_modeling_prep_source.py`

Pattern:
- mirrors `YahooFinanceSource`: delegates each method to the client.
- `name` returns `"fmp"`.

#### Adapter
- `app/data_sources/adapters/financial_modeling_prep_adapter.py`

Pattern:
- subclass of `BaseDataSourceAdapter`
- `_create_source()` returns `FinancialModelingPrepSource(config)`
- `_validate_config()` ensures `api_key` exists

### 3.2 Settings/env vars

Add to `app/config.py` / settings:
- `fmp_api_key`
- `fmp_enabled` (optional)
- `fmp_base_url` (optional)
- `fmp_timeout`
- `fmp_retry_count` / `fmp_max_retries`
- `fmp_rate_limit_calls`
- `fmp_rate_limit_window`

### 3.3 Adapter registration

Update `app/data_sources/adapters/factory.py::_register_default_adapters()`:

- Conditionally register FMP:
  - only if `settings.fmp_api_key` exists and is non-empty.

Example priority guidance:
- If you want FMP to be preferred over Yahoo:
  - give it a lower `priority` number (higher priority in factory ordering).

### 3.4 `get_data_source()` config mapping

Update `app/data_sources/__init__.py::get_data_source()` config builder:
- add `elif name == "fmp": config = { ... }`

### 3.5 Client method surface area

Implement at least:

**Core (BaseDataSource):**
- `fetch_price_data()`
- `fetch_current_price()`
- `fetch_fundamentals()`
- `fetch_news()`
- `fetch_earnings()`
- `fetch_industry_peers()`
- `is_available()`

**Practical parity (used by services):**
- `fetch_earnings_calendar()`
- `fetch_earnings_for_date()`
- `fetch_actions()`
- `fetch_dividends()`
- `fetch_splits()`
- `fetch_financial_statements()`
- `fetch_symbol_details()`
- `fetch_quarterly_earnings_history()`
- `fetch_analyst_recommendations()`

### 3.6 Analyst endpoints

FMP provides analyst-related endpoints (ratings/recommendations/price targets). The provider should expose:

- `fetch_analyst_recommendations(symbol) -> List[Dict[str, Any]]`

Normalize to a stable list of dicts with:
- `date`
- `rating` / `recommendation`
- `price_target` (if present)
- `analyst_name` / `firm` (if present)
- `source: "fmp"`

### 3.7 “Switch provider and services still work” checklist

To verify drop-in support:

1. Set env:
   - `PRIMARY_DATA_SOURCE=fmp`
   - optionally: `FALLBACK_DATA_SOURCE=yahoo_finance`

2. Confirm `get_data_source()` returns an initialized adapter (or composite).

3. Run refresh endpoints for:
   - price_historical
   - fundamentals
   - market_news
   - earnings
   - industry_peers

4. Confirm inserts happen with `source = "fmp"` and services don’t throw missing-method errors.

## 4) Implementation Notes / Gotchas

- Some services rely on provider-specific methods without `hasattr()` checks. For a seamless provider switch, implement the “practical parity” methods above.
- Rate limiting matters: FMP will likely throttle; treat 429 as retryable.
- Normalize date/time consistently (use UTC timestamps where possible).

## 5) Future Improvements

- Refactor `AnalystRatingsService` to use `get_data_source()` (instead of hard-coded Finnhub) if you want “provider switch” to affect analyst ratings too.
- Add a shared normalization module under `app/providers/common/` to avoid duplicating parsing across clients.
