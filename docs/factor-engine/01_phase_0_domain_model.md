# Phase 0 — Domain Model (Authoritative)

## Purpose
Define exactly what the system owns so the platform does not reintroduce overlapping concepts (e.g., “Investment Health”, “Composite Score”, “Trading Decision”, etc.).

Every future feature must map to one or more of these concepts.

## Architectural principle (locked)
- **Providers own data retrieval**
- **Registries own discovery**
- **Scoring engines own computation**
- **Screeners own weighting**
- **No layer reaches around another layer**

## Naming + factor ID conventions (locked)
### Factor IDs
- Dotted namespace IDs, e.g.:
  - `technical.rsi_14`
  - `valuation.fair_value_gap_pct`
  - `fundamental.roic`

### Namespaces (top-level)
- `meta.*`
- `fundamental.*`
- `quality.*`
- `valuation.*`
- `technical.*`
- `ai.*`
- `catalyst.*`
- `risk.*`
- `derived.*` (reserved for **cross-domain synthesized** metrics only)

## Domain entities

### Stock
A tradable instrument.
- Identity: `symbol` (plus internal id if available)
- Metadata: sector, industry, exchange, market cap, currency

### UniverseDefinition
A reusable, versioned definition that returns a set of stocks.
- Inputs:
  - rules over `meta.*` and optionally factor thresholds (e.g., `ai.exposure_score > 40`)
- Output:
  - an evaluated set of stocks at an `as_of_date`

### FactorDefinition
Immutable metadata for a factor.
Minimum fields:
- `id`: string (dotted namespace)
- `name`: string
- `namespace`: string
- `unit`: `currency|ratio|percentage|score|boolean|count|text|enum`
- `frequency`: `intraday|daily|weekly|quarterly|event|manual`
- `owner_provider_id`: string
- `explainable`: bool
- `deprecated`: bool
- `version`: string

### RawFactorSnapshot
A point-in-time value of a raw factor returned by a provider.
Fields:
- `symbol`
- `factor_id`
- `as_of_date` (or as-of timestamp where applicable)
- `value`
- `confidence` (0–100)
- `provider_id`
- `provider_version`
- `source_ref` (table/service)
- `generated_at`

Constraint:
- Raw factors do not depend on other factors.

### DerivedFactorDefinition
A definition for derived factors (computation owned by scoring/derived layer).
Fields:
- `id`, `name`, `unit`, `version`
- `inputs`: list of raw factor IDs
- `formula` / algorithm reference (ideally config-driven)

Constraint:
- Derived factors may depend on **raw factors only**.
- Derived factors should be limited to cross-domain synthesized metrics in `derived.*`.

### DerivedFactorSnapshot
A computed point-in-time value for a derived factor.
Fields:
- all RawFactorSnapshot fields plus:
  - `inputs_hash` (hash of input factor snapshots)
  - optional `explanation` payload

### FactorGroupDefinition
A stable category used for weighting and explainability.
Examples:
- `quality`
- `valuation`
- `technical`
- `ai`
- `catalyst`
- `risk`

### ScoreDefinition
Configurable composition of factors and/or groups.
- Versioned
- Must declare:
  - inputs
  - weights
  - normalization policies
  - confidence aggregation policy

Notes:
- Group scores (e.g., `quality.business_quality_score`) are ScoreDefinitions.
- Headline scores (e.g., investment/entry/catalyst/opportunity) are ScoreDefinitions.

### ScoreSnapshot
A point-in-time computed score.
Fields:
- `symbol`
- `score_id`
- `as_of_date`
- `value` (0–100)
- `confidence` (0–100)
- `version`
- `profile_id` (optional)
- `inputs_hash`
- `generated_at`

### ScreeningProfile
Fully declarative configuration that produces ranked recommendations.
Fields (conceptual):
- `id`, `name`, `version`
- `universe_id`
- `ranking_score_id`
- `filters` (meta + factor + score thresholds)
- `weights` (group + factor overrides)
- `explain: true|false`
- `rebalance: daily|weekly|manual`

### Recommendation
A ranked result for `UniverseDefinition × ScreeningProfile × as_of_date`.
- Includes:
  - rank
  - score snapshots (headline + group)
  - top drivers + risks
  - explanation payload

### Catalyst
A discrete event or evolving signal feeding `catalyst.*` factors.
Examples:
- earnings, guidance, analyst estimate changes, contracts, product launches

### InvestmentTheme
A taxonomy label used for:
- Universe construction
- UI navigation
- explainability

## Explicit non-entities (must not become domain concepts)
These can exist as **legacy implementations** or **providers**, but are not first-class nouns in the domain:
- Investment Health
- Composite Score
- Trading Decision
- Opportunity Score (as a separate noun outside ScoreDefinition)

They should be expressed as:
- providers returning factors
- or ScoreDefinitions built on factors
