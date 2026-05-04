---
description: Fair Value Engine v2 (Formula DSL + As-Of Timestamp Feature Store)
updated: 2026-04-21
status: draft
---

# Context
`python-worker/app/services/fair_value_service.py` has grown into a monolithic service that mixes:
- Feature sourcing (many DB queries + fallbacks)
- Feature normalization + data quality
- Valuation methods (DCF/PE/PEG/EV/Sales/PB)
- Policy (regime classification, gating, weights)
- Persistence/audit

This makes iteration slow and risky. The goal of v2 is to enable **spreadsheet-like iteration** (change formulas, not orchestration code) while maintaining **institutional-grade reproducibility** and **AI-agent friendly** interfaces.

# Goals
- Deterministic fair value for a symbol at a specific **as-of timestamp** (`as_of_ts`).
- Point-in-time correctness (no lookahead bias) for backtests and audit.
- Fast iteration: define valuation methods as **YAML/JSON** formulas (XLS-like).
- DRY/SOLID separation of concerns.
- Explainability: structured explanation of regime, inputs used, caps hit, and method contributions.
- Performance: avoid many per-symbol DB round trips; support batch evaluation.

# Non-goals
- Full rewrite in one step.
- Unsafe formula evaluation via Python `eval`.
- Baking strategy/trading logic into valuation service.

# Recommended decisions (confirmed)
- **Formulas** live in YAML/JSON configs evaluated in Python.
- Feature store is **as-of timestamp** (`as_of_ts`) based (more control than daily-only).
- DSL supports helper transforms like **winsorize** and **rolling median**.
- Default `as_of_ts` is `now_utc()` when not supplied, but callers can pass explicit `as_of_ts`.
- Default bounded history windows:
  - Quarterly series: last **8** quarters
  - Annual series: last **6** years

# High-level architecture (SOLID)
## Components
1. **Feature Store** (data retrieval only)
2. **Policy Engine** (regime + method applicability + caps/weights)
3. **Formula Engine** (evaluate method definitions)
4. **Blender** (blend method outputs)
5. **Persistence/Audit** (store reproducible run artifacts)

Each component is testable in isolation.

## Data flow
1. `features = FeatureStore.get(symbol, as_of_ts)`
2. `policy = PolicyEngine.evaluate(features)`
3. `method_results = FormulaEngine.evaluate_all(features, policy)`
4. `blend = Blender.blend(method_results, policy)`
5. `persist(run, features_hash, policy_version, method_versions, method_results, blend)`

# Proposed module layout
Create a new package:

`python-worker/app/fair_value_v2/`
- `schemas.py` (Pydantic models)
- `service.py` (orchestrator)
- `feature_store/`
  - `base.py` (protocol/ABC)
  - `postgres_point_in_time.py`
- `router.py` (category routing; YAML rules)
- `regime_router.py` (regime routing + regime-specific method selection; YAML rules)
- `policy/`
  - `engine.py`
  - `rules/` (financials, healthcare, staples, growth, cyclical)
- `dsl/`
  - `ast.py` (expression types)
  - `parser.py` (YAML/JSON to AST)
  - `evaluator.py` (safe interpreter)
  - `functions.py` (whitelisted functions + transforms)
- `methods/`
  - `registry.py` (load YAML, versioning, overrides)
  - `definitions/` (`*.yaml` method specs)
- `blending.py`
- `persistence.py`

# Data contracts (AI-agent friendly)
Use Pydantic models with stable JSON structure.

## `FeatureRow`
- `symbol: str`
- `as_of_ts: datetime`
- `scalars: dict[str, float | int | str | None]`
- `series: dict[str, list[dict]]`
  - Each series element is `{ "ts": <datetime>, "value": <float|int|None>, ... }`
- `sources: dict[str, str]` (per-feature provenance)
- `quality: dict[str, Any]` (missing fields, recency, flags)

## `MethodDefinition`
- `method_key: str`
- `version: str | int`
- `category: str`
- `requires: { scalars: [...], series: [...] }`
- `params: dict[str, Any]`
- `formula: dict` (DSL AST)
- `validations: list` (optional)

## `MethodResult`
- `method_key: str`
- `version: str | int`
- `enabled: bool`
- `status: Literal["ok","missing_data","invalid_assumption","disabled"]`
- `fair_price: float | None`
- `inputs_used: dict[str, Any]` (resolved scalar values + params)
- `metrics: dict[str, Any]` (intermediates, caps hit, diagnostics)
- `reason_code: str | None`
- `reason_details: dict[str, Any] | None`

## `PolicyDecision`
- `regime: str`
- `method_enablement: dict[str, bool]`
- `weight_overrides: dict[str, float]`
- `param_overrides: dict[str, dict[str, Any]]` (by method_key)
- `notes: list[str]`

## `FairValueResult`
- `run_id: str`
- `symbol: str`
- `as_of_ts: datetime`
- `fair_value: float | None`
- `scenario_fair_values: dict[str, float]`
- `regime: str` (format: `<category>:<regime>`)
- `method_results: list[MethodResult]`
- `features_hash: str`
- `model_version: str`

# Routing and policy (category + regime)
Routing is fully data-driven and defined in YAML, with an auditable override mechanism for boundary cases.

## Category routing
- YAML: `python-worker/app/fair_value_v2/methods/category_router.yaml`
- Implementation: `python-worker/app/fair_value_v2/router.py` (`CategoryRouter`)
- Inputs available to routing rules:
  - `symbol`
  - `sector`, `industry`
  - `company_name`, `description` (from `fmp_company_profiles` when present)

This supports finer classification for cases where sector/industry are too coarse (e.g., AI infrastructure names) by using company profile text.

## Regime routing
- YAML: `python-worker/app/fair_value_v2/methods/regime_router.yaml`
- Implementation: `python-worker/app/fair_value_v2/regime_router.py` (`RegimeRouter`)
- Regime selection uses a small explicit scalar set for determinism and debuggability.

Current regime selection scalars include:
- `eps_ttm`
- `eps_forward`
- `market_cap`
- `revenue_growth_ttm`
- `forward_growth_pct_1y`
- `operating_margin_ttm`

Pre-earnings / loss-making detection considers not just `eps_ttm <= 0`, but also negative forward EPS and deeply negative operating margins so loss-making stocks do not get incorrectly routed into PE/PEG regimes.

## Regime method selection
- YAML: `python-worker/app/fair_value_v2/methods/regime_methods.yaml`

Regime method selection is explicit for categories where fallback chains would produce incorrect behavior. In particular, the `cyclical` category defines explicit `standard` and `mega_cap` regime method blends so cyclical names do not fall back into `value` methods.

# Category overrides (DB-backed, auditable)
Some symbols are true boundary cases (e.g., sector/industry ambiguity, inconsistent vendor metadata). FV2 supports an **auditable** override mechanism without hardcoding symbols in YAML.

## Storage
- Table: `fair_value_v2_category_overrides`
- Baseline schema: `migrations/init_database_complete.sql`
- Columns:
  - `symbol` (PK)
  - `category_override`
  - `enabled`
  - `reason`
  - `updated_by`
  - `created_at`, `updated_at`

## Application semantics
- Overrides are applied *before* category routing.
- When an override is applied, the run emits a structured warning with metadata (`category_override_applied`) so downstream consumers can see category provenance.

## Admin API
FastAPI admin endpoints exist to manage overrides:
- `POST /admin/fair-value-v2/category-overrides/ensure-table`
- `GET /admin/fair-value-v2/category-overrides`
- `POST /admin/fair-value-v2/category-overrides` (upsert)
- `POST /admin/fair-value-v2/category-overrides/{symbol}/disable`

# Coverage / completeness diagnostics
FV2 includes a coverage report that evaluates routing + required features per routed method.

- Implementation: `python-worker/app/fair_value_v2/coverage_report.py`
- Coverage routing behavior matches production:
  - Applies enabled category overrides
  - Uses the same regime scalar set as the runner

This is the primary tool for diagnosing missing growth/margin features that cause method-level missing-data failures.

# Runtime flags
- `ENABLE_FAIR_VALUE_V2`: turns on FV2 in the API.
- `FAIR_VALUE_V2_STRICT`: strict mode for canonical feature enforcement (used to avoid silently emitting results when required features are missing).

# DSL (spreadsheet-like) design
## Constraints
- Deterministic.
- No Python `eval`.
- Only whitelisted ops.
- Explicit `require(...)` and validations to control missing/invalid cases.

## Core AST nodes
- Literals: `{ "const": 1.23 }`
- Variables: `{ "var": "eps_forward" }`
- Params: `{ "param": "r" }`

## Arithmetic
- `{ "add": [a, b, ...] }`
- `{ "sub": [a, b] }`
- `{ "mul": [a, b, ...] }`
- `{ "div": [a, b] }`

## Functions
- `{ "min": [a, b] }`, `{ "max": [a, b] }`
- `{ "clamp": { "value": x, "lo": lo, "hi": hi } }`
- `{ "abs": x }`, `{ "log": x }`, `{ "exp": x }`, `{ "pow": [a, b] }`

## Null/guard handling
- `{ "coalesce": [a, b, c] }`
- `{ "require": { "value": x, "reason": "missing_eps" } }`

`require` fails if the value is null/NaN/inf or (optionally) <=0 depending on method validation.

## Conditionals
- `{ "if": { "cond": c, "then": a, "else": b } }`
- Comparisons: `{ "gt": [a, b] }`, `{ "gte": [a, b] }`, `{ "lt": [a, b] }`, `{ "lte": [a, b] }`, `{ "eq": [a, b] }`
- Boolean: `{ "and": [c1, c2] }`, `{ "or": [...] }`, `{ "not": c }`

## Helper transforms (operate on series provided by FeatureStore)
These must **not** query the DB; they only transform bounded series arrays.
- `{ "winsorize": { "series": {"series": "fcf_quarter"}, "p_low": 0.05, "p_high": 0.95 } }`
- `{ "rolling_median": { "series": {"series": "eps_annual"}, "window": 5 } }`
- `{ "rolling_mean": { "series": {"series": "revenue_quarter"}, "window": 4 } }`
- `{ "ttm_sum": { "series": {"series": "fcf_quarter"} } }`
- `{ "cagr": { "start": a, "end": b, "years": n } }`

# Method definition format (YAML)
## Example: Bank justified P/B
```yaml
method_key: pb_bank
version: 1
category: financials
requires:
  scalars: [book_value_per_share, roe]
  series: []
params:
  r: 0.10
  g: 0.03
  pb_floor: 0.7
  pb_cap: 2.2
formula:
  fair_price:
    mul:
      - var: book_value_per_share
      - clamp:
          value:
            div:
              - sub: [{var: roe}, {param: g}]
              - sub: [{param: r}, {param: g}]
          lo: {param: pb_floor}
          hi: {param: pb_cap}
validations:
  - require_positive: book_value_per_share
  - require_positive: roe
```

# Feature store: point-in-time requirements
## Principle
For every feature, use the latest record **at or before** `as_of_ts`. For series, gather a bounded set of rows **<= as_of_ts**.

## Suggested features (initial)
Scalars:
- `current_price` (reporting only)
- `eps_ttm`, `eps_forward`
- `revenue_ttm`, `free_cash_flow_ttm`
- `gross_margin`, `operating_margin`, `net_margin`
- `roe`, `roic`, `debt_to_equity`
- `market_cap`, `shares_outstanding`
- `book_value_per_share`
- `industry`, `sector`

Series:
- `eps_annual` (6 years)
- `revenue_quarter` (8 quarters)
- `fcf_quarter` (8 quarters)

Quality/provenance:
- per-feature sources
- staleness (days) per major source
- flags (missing, derived, clamped)

# Policy engine (regime + gating)
Policy outputs should be entirely derived from `FeatureRow` (no DB access).

Examples:
- Financials: enable `pb_bank`, disable `ev_sales`, tighten PE caps.
- Mature value: disable PEG, favor PE/DCF/Adjusted PE, but allow PB for banks.
- Healthcare: sector-specific caps and method weights.

Policy should also support per-method parameter overrides (e.g., financials cost of equity).

# Blending
Blend only `ok` methods.
- Start from default weights by regime.
- Apply reliability scaling.
- Apply policy multipliers.
- Apply dispersion/consistency penalties.
- Cap max influence (e.g., no single method >70% weight).

# Persistence and reproducibility
Institutional requirement: every result must be reproducible.

Persist:
- `run_id`, `symbol`, `as_of_ts`
- `features_hash` (hash of `FeatureRow` scalars+series used)
- `policy_version`, `model_version`
- Per-method:
  - `method_key`, `method_version`, `definition_json`
  - `inputs_used`, `metrics`, `fair_price`, `status`
- Blend weights and blended fair value

# AI-agent friendly interfaces
## Python
- `FairValueV2Service.calculate(symbol: str, as_of_ts: datetime | None = None) -> FairValueResult`
- `FairValueV2Service.explain(symbol: str, as_of_ts: datetime | None = None) -> FairValueResult` (includes richer metrics/intermediates)
- `FairValueV2Service.calculate_batch(symbols: list[str], as_of_ts: datetime | None = None) -> list[FairValueResult]`

## HTTP (incremental; keep existing stable)
Keep:
- `POST /fair-value` (existing)

Add:
- `POST /fair-value:explain`
- `POST /fair-value:batch`

All responses must be structured JSON with stable Pydantic schemas.

# Migration plan
1. Implement v2 behind `ENABLE_FAIR_VALUE_V2` flag.
2. Shadow-run v2 alongside v1 for a subset of symbols to compare outputs.
3. Move one method at a time into DSL (start with `pb_bank`, `pe_forward`, `adjusted_pe`).
4. Replace monolithic `_get_fundamentals` with FeatureStore outputs.
5. Switch API endpoint to v2 once parity and benchmarks are satisfied.
