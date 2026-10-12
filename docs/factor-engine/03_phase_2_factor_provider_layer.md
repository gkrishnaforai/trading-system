# Phase 2 — Factor Provider Layer

## Purpose
Implement a clean separation where:
- **Providers** retrieve raw facts from canonical sources and output standardized snapshots.
- **Registries** map factors to providers (discovery).
- **Derived factors / scores** are computed above the provider layer.

This prevents reach-around dependencies and makes it possible to swap underlying tables/services without touching downstream screeners.

## Architectural principle (locked)
Providers own data retrieval. Registries own discovery. Scoring engines own computation. Screeners own weighting.

No layer should reach around another layer.

## Provider contract (conceptual)
Each provider supports:
- `get_latest(symbol) -> list[RawFactorSnapshot]`
- `get_asof(symbol, as_of_date) -> list[RawFactorSnapshot]`

All returned snapshots must include:
- `factor_id` (dotted namespace)
- `value`
- `as_of_date`
- `generated_at`
- `provider_id`
- `provider_version`
- `source_ref` (table/service)
- `confidence` (0–100)

## Confidence (locked)
Confidence is 0–100 integer derived from:
- source reliability
- freshness
- coverage
- calculation stability

Providers are responsible for computing these components and outputting the final confidence.

## Providers (v1)

### 1) MetaProvider
Owns `meta.*` fields used by universes and filters.
Examples:
- `meta.market_cap`
- `meta.sector`
- `meta.industry`
- `meta.exchange`
- `meta.country`
- `meta.currency`
- `meta.avg_dollar_volume_20d`

### 2) TechnicalProvider (canonical read source locked)
- Canonical read source (Phase 2): `indicators_daily`
- Owns `technical.*` factors.
Examples:
- `technical.rsi_14`
- `technical.ema_20`
- `technical.sma_50`
- `technical.macd`

Notes:
- Trading Decision V3 currently reads `indicators_daily`; this aligns with canonical choice.
- Long-term storage migration (optional): `stock_technical_indicators`, but only after parity.

### 3) FinancialProvider
Owns `fundamental.*` raw factors.
Canonical sources in v1 may include:
- `fundamentals_snapshots` for latest snapshot values
- `fmp_financial_statements` for multi-year derived-from-statements fields (if treated as provider-produced raw metrics)

### 4) ValuationProvider (canonical engine locked)
- Canonical engine: Fair Value v2.
Owns `valuation.*` factors.
Examples:
- `valuation.fair_value`
- `valuation.fair_value_gap_pct`
- `valuation.forward_pe`

Legacy:
- Fair Value v1 should be run as a **validation comparator** producing diffs, not as a canonical provider.

### 5) AIProvider
Owns `ai.*` factors.
Examples:
- `ai.exposure_score`

Expected near-term state:
- coverage may be partial; confidence should reflect this.

### 6) CatalystProvider
Owns `catalyst.*` factors.
Examples:
- `catalyst.days_to_earnings`
- `catalyst.eps_surprise_pct_last`

Expected gaps:
- `catalyst.eps_revision_90d` likely missing in v1; record as ❌ in Phase -1 and gate profiles accordingly.

### 7) RiskProvider
Owns `risk.*` factors.
Examples:
- `risk.beta`
- `risk.max_drawdown_1y`
- `risk.leverage`

Risk is orthogonal and should remain separate from `technical.*` and `valuation.*`.

## Factor discovery (registry)
The registry is not a datastore.
It maps:
- `FactorDefinition.id -> Provider`

Additionally, each FactorDefinition includes immutable metadata:
- id, name, unit, frequency, provider_id, version, explainable, deprecated

## Output requirements for Phase 2
- A single call site (Go API or python-worker orchestration) can request a symbol’s raw factor set and receive consistent `RawFactorSnapshot` objects.
- Downstream systems do not query raw tables directly.
- SoTR is updated to record canonical provider/table decisions.
