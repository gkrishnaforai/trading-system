# Trading System Implementation Architecture Bible

**Status:** Active architecture decision record
**Owner:** Trading system
**Scope:** Python worker, market analysis, strategy suitability, stock setup, risk, decision, execution, and observability

This document is the implementation authority for the trading system. New code must follow these boundaries. Existing code that conflicts with this document is legacy and must be migrated or removed; it is not a second source of truth.

## 1. Core principle

The system separates market context from trade opportunity:

```text
Market data
  -> data quality
  -> market regime
  -> strategy environment
  -> stock opportunity/setup
  -> risk and portfolio constraints
  -> trade decision
  -> execution and monitoring
```

- **Market Regime:** What environment is the market in?
- **Strategy Environment:** Which horizons and tactics are permitted or favorable?
- **Stock Opportunity:** Is this particular symbol attractive for the selected horizon?
- **Risk Engine:** Can the opportunity be taken within risk and portfolio constraints?
- **Decision Engine:** Should the system BUY, BUY_SMALL, WAIT, AVOID, EXIT, or HOLD?
- **Execution:** Can an approved decision be implemented safely?

Market regime never directly chooses a stock. Stock analysis never bypasses risk policy.

## 2. Canonical modules

The canonical market implementation is `python-worker/app/market_regime/`.

| Responsibility | Canonical location |
|---|---|
| Provider routing and canonical market data | `app/market_data/` |
| Indicator mathematics | `app/indicators/` and delegated helpers in `app/market_data/indicators.py` |
| Market snapshot construction | `app/market_regime/state.py` |
| Deterministic market facts and scores | `app/market_regime/facts.py` |
| Market regime interpretation | `app/market_regime/agent.py` |
| Market-regime orchestration | `app/market_regime/graph.py` |
| Market-regime presentation | `app/market_regime/report.py` |
| Deterministic market permissions | `app/market_regime/permissions.py` |
| Strategy environment | `app/strategy_environment/` |
| Stock features and setup detection | `app/swing_opportunity/` |
| Fundamental intelligence | `app/fundamental_intelligence/` |
| Valuation and fair value | future `app/valuation/` (separate from quality) |
| Risk and portfolio controls | `app/risk/` and future `app/portfolio/` |
| Final trade policy | future `app/trade_decision/` |
| Execution | future execution adapter, separate from analysis |

There must be one canonical implementation for each responsibility. Compatibility adapters may exist temporarily, but they may not calculate a second regime.

## 2A. Graph state ownership and contracts

The future trading graph uses a typed, namespaced `TradingState`. It is a shared case file for the current run, not an unstructured dictionary that every node may mutate.

```text
TradingState
├── identity
├── market
├── strategy_environment
├── stock
├── setup
├── catalyst
├── risk
├── decision
└── provenance
```

Each namespace has an owning engine and an explicit write scope:

| Engine/node | Reads | May write |
|---|---|---|
| Data quality | provider responses, timestamps | `provenance.data_quality` |
| Market regime | market snapshot, data quality | `market.snapshot`, `market.facts`, `market.regime`, `market.permissions` |
| Strategy environment | market namespace, horizon data, data quality | `strategy_environment` |
| Stock analysis | identity, market context, symbol data | `stock` |
| Setup detection | stock, strategy environment, catalyst | `setup` |
| Catalyst/event overlay | identity, event/news data | `catalyst` and bounded setup/risk restrictions |
| Risk engine | market permissions, strategy environment, stock, setup, portfolio | `risk` |
| Decision engine | all validated prior namespaces | `decision` |
| Execution | approved decision, account/execution state | `execution` and execution provenance only |

Nodes must return partial state updates rather than mutate arbitrary state in place. A node may not overwrite another engine's namespace. Cross-namespace effects must be represented as explicit typed fields or policy decisions; for example, an event overlay may restrict risk, but it cannot directly create a BUY decision.

### Reducer policy for parallel agents

LangGraph reducers are part of the multi-agent state design, but they are not a general-purpose merge mechanism. Every state field must declare one of these update semantics:

1. **Replace:** the owning node writes the complete value. Use for snapshots, facts, regime, permissions, scores, risk assessments, and final decisions.
2. **Append/merge:** parallel nodes contribute independent records. Use for evidence, warnings, provider attempts, candidate setups, research citations, and audit events. Reducers must be deterministic and preserve provenance.
3. **Validated aggregate:** parallel nodes contribute compatible measurements that are combined by a named rule. Use only where the aggregation is mathematically defined, such as coverage counts or a bounded collection of votes. The aggregation rule, missing-data behavior, and conflict behavior must be documented.

Reducers must not silently merge competing values for:

- market regime
- strategy permissions
- position size
- risk limits
- stop or target
- final action
- confidence or probability

Those fields use replace semantics and have one authoritative owner. If multiple agents produce competing proposals, store them as proposals/evidence and route them to a deterministic arbiter or decision node. Do not use `last write wins` for financial decisions.

For parallel strategy environments, each branch writes only its own keyed namespace, for example:

```text
strategy_environment.day_trading
strategy_environment.swing
strategy_environment.positional
strategy_environment.investing
```

A reducer may collect these independent horizon assessments into `strategy_environment.assessments`, but it must not average or overwrite them into one generic suitability value. A later policy node may compare them and select an allowed horizon using explicit rules.

Reducer requirements:

- reducer type and identity must be declared in the state schema
- updates must be idempotent or carry a stable event/update ID
- ordering must not change the result
- conflicts must be preserved or rejected, not hidden
- provenance must identify the contributing node, version, and timestamp
- tests must cover parallel execution, duplicate updates, missing branches, and conflicts

Every node/agent has a written contract containing:

```text
INPUT STATE FIELDS
OUTPUT STATE FIELDS
READ-ONLY DEPENDENCIES
DATA QUALITY REQUIREMENTS
FAILURE / INSUFFICIENT-DATA BEHAVIOR
RULES VERSION AND FEATURE VERSION
```

The current `RegimeGraphState` is intentionally narrow and transitional. It is not permission for future agents to share one untyped mega-object. As more phases are added, use typed namespace models and preserve the narrow graph state for each subgraph where possible.

## 2B. State, checkpoints, and memory

State means information needed for one graph execution, such as today's analysis of one symbol. Memory means information that persists across executions, such as portfolio holdings, user preferences, prior decisions, research, or realized outcomes.

The initial implementation order is:

1. Typed state contracts.
2. Deterministic node boundaries and partial updates.
3. Checkpoint persistence for resumability and replay.
4. Long-term memory only for explicitly defined domain records.

LangGraph checkpoints are required before introducing human approval, scheduled workflows, long-running research, or live execution. Checkpoints must be keyed by a stable run/thread identifier and retain schema/version metadata. Checkpoint persistence is not a substitute for durable domain storage: portfolio, orders, fills, and realized outcomes belong in durable repositories and are referenced by state.

Do not place all historical research or user memory into `TradingState`. Load the minimum required context into the current run and record provenance for what was loaded.

## 3. LLM and deterministic boundaries

Deterministic Python owns:

- indicator calculations
- data-quality decisions
- dimension labels and scores
- market regime rules
- transition priors
- market permissions
- strategy environment scores
- position sizing limits
- risk limits
- final trade eligibility
- execution validation

LLM agents may provide:

- interpretation
- research summaries
- catalyst interpretation
- explanations
- bounded proposals that are validated by deterministic policy

An LLM may not create or override a permission, risk limit, position size, probability, or execution instruction without deterministic validation. Rules/LLM disagreement is recorded for evaluation.

## 4. Canonical market-regime contract

`app.market_regime` is the only market-regime implementation.

It produces:

- `MarketSnapshot`
- `DimensionFacts`
- `MarketRegime`
- deterministic `MarketPermissions`

The regime contains descriptive state (`direction`, `condition`, dimensions, scores, confidence) and permissions (`normal_long`, `breakout_buying`, `leverage`, `size_multiplier`). These are related but not interchangeable.

Legacy regime enums, legacy market-context defaults, and legacy regime services must not be used by new code.

## 5. Strategy Environment phase

The next implementation phase is a deterministic **Strategy Environment Engine**, not a generic LLM agent. It consumes the canonical market regime plus horizon-specific data and produces one environment assessment per supported horizon:

- `day_trading`
- `swing`
- `positional`
- `investing`

Each assessment includes:

- environment quality
- score and confidence
- long/short permissions
- tactic permissions
- size/pacing guidance
- required data quality
- blocking reasons
- timestamp and feature/version metadata

The engine must not claim that a symbol is buyable. That is the responsibility of stock-level opportunity and setup layers.

### Day trading

Requires intraday data and should not run from daily regime data alone:

- intraday trend, VWAP, opening range
- relative volume and liquidity/spread
- intraday breadth
- SPY/QQQ and sector intraday structure
- catalyst/news state
- market-hours and freshness checks

Without sufficiently fresh intraday data, day trading is `UNAVAILABLE` or `AVOID`, never inferred from daily data.

### Swing

This is the first strategy consumer because the current data foundation is daily:

- daily trend and momentum
- breadth and participation
- sector/benchmark relative strength
- pullback and breakout environment
- volatility and macro pressure
- earnings/event proximity

### Positional

Uses daily/weekly trend, industry leadership, fundamentals, earnings revisions, valuation, and cycle context.

### Investing

Uses point-in-time fundamentals and valuation. Market regime influences pacing and portfolio exposure, not business quality. A high-quality company may remain investable in a riskier market through staged accumulation.

## 6. Bullish transition and dip-buying policy

The market regime engine has three distinct questions:

```text
trend_score
  Is the market structurally bullish?

deterioration_score
  Is the current regime weakening?

bullish_transition_score
  Is evidence of recovery/dip-buying safety increasing?
```

`bullish_transition_score` is deterministic and persisted daily in `market_transition_snapshots`. It is not an LLM score and is not a probability of a profitable trade. It combines trend repair, breadth, momentum, leadership, volatility, macro, and structure. The score has a stage and trajectory deltas:

```text
NO_DIP_BUYING
WATCH
SELECTIVE
ACTIVE
CONFIRMED
NORMAL
```

Dip-buying permissions are staged and must still pass stock-level setup, risk, event, and portfolio constraints. The transition engine must not predict an exact bottom or override a falling-knife veto. Stored daily scores enable walk-forward evaluation of whether rising transition evidence improves future 5/10/20-day expectancy.

## 7. Macro policy

Macro data is useful, but not every macro series belongs in every decision.

- **Rates/yields:** core cross-horizon input; affects valuation, growth leadership, and risk appetite.
- **VIX/volatility:** core for swing and day trading; secondary for investing.
- **Breadth/participation:** core for market regime and swing; intraday breadth is required for day trading.
- **Oil:** not a standalone buy/sell signal. Use as a conditional risk input when the move is large, persistent, inflation-relevant, or sector-relevant. It is more important for energy, airlines, transports, chemicals, inflation-sensitive growth, and macro risk than for every stock.
- **DXY, gold, BTC, MOVE:** optional cross-asset context with explicit coverage and freshness. They must not add risk merely because they are available.

Every macro feature must state its horizon relevance and economic interpretation. Isolated oil movement should not flip a regime; oil shock plus rising yields, inflation pressure, and deteriorating breadth may tighten strategy permissions.

## 8. Scores and decisions

Environment score and opportunity score are separate:

```text
Environment score = how favorable the horizon is
Opportunity score = how attractive the symbol/setup is
```

Do not initially treat their product as a probability. Apply hard gates first, then use a transparent weighted combination and environment-based sizing. All score bands are uncalibrated quality bands until validated with walk-forward outcomes.

Risk is a mandatory gate after setup detection and before final decision. Position size must consider portfolio risk, stop distance, liquidity, correlation, event risk, and market size multiplier.

## 9. Event trading

Events begin as an overlay, not a completely separate decision universe:

```text
base horizon + event-risk overlay
```

Earnings, CPI, FOMC, employment reports, FDA decisions, and regulatory events can restrict entries, overnight holds, leverage, sizing, and stops. Event data must be timestamped and point-in-time correct.

## 10. LangGraph, LangChain, Langfuse

- **LangGraph:** orchestration, branching, retries, typed partial state updates, checkpoint persistence, approvals, and re-evaluation.
- **LangChain:** structured LLM output, prompts, tools, and model adapters where useful.
- **Langfuse:** traces, prompt/model versions, provider attempts, data quality, rule/LLM disagreement, state transitions, decisions, executions, and realized outcomes.

The current market-regime graph is not yet checkpointed; it is a short-lived analysis graph. Add a checkpointer when the graph gains human approval, scheduled resumption, long-running research, or execution state. Do not claim resumability until checkpoint persistence and thread/run identifiers are tested.

Pure indicators and deterministic finance rules remain ordinary Python; they should not be hidden inside prompts or unnecessary graph nodes.

## 11. Required evaluation discipline

Every engine/agent receives focused deterministic evals before integration:

- Market regime: facts, score invariants, transition normalization, missing-data behavior.
- Strategy environment: horizon-specific score cases, hard gates, permission mapping, insufficient-data behavior.
- Stock setup: positive, negative, ambiguous, and missing-data cases.
- Risk: sizing, stop distance, liquidity, concentration, event blocks.
- Decision: BUY/BUY_SMALL/WAIT/AVOID/EXIT matrix and veto behavior.
- LLM interpretation: schema validity, bounded output, disagreement capture; never use narrative quality as a substitute for policy tests.

Evaluation must use point-in-time data and walk-forward validation. Every result records data cutoff, feature version, rules version, model version, and outcome horizon.

## 12. Decision lineage, portfolio memory, and outcomes

The database is the system of record for portfolio facts and decision history; it is not the agent's brain. Agents retrieve structured, versioned state, compare it with current facts, and produce a new decision. Previous decisions are never overwritten.

The canonical lineage is:

```text
Trade Thesis
    ↓
Decision Run / Decision Snapshot
    ↓
Risk Assessment
    ↓
Portfolio Allocation
    ↓
Order Plan
    ↓
Order / Fill
    ↓
Position State
    ↓
Position Review
    ↓
Realized Outcome
```

Required conceptual entities:

```text
market_snapshots
market_regimes
strategy_environments
market_events
fundamental_snapshots
technical_snapshots
valuation_snapshots
trade_theses
trade_decisions
decision_reasons
invalidation_conditions
portfolio_snapshots
positions
position_events
portfolio_exposure
risk_budgets
allocations
order_plans
orders
fills
agent_runs
tool_calls
validation_results
decision_timeline
performance_outcomes
```

Existing tables/services may be adapted, but new code must not create parallel meanings for the same event. Every record needs `as_of`, `created_at`, source/provider, rules version, feature version, and model/prompt version where applicable. Decision facts and LLM interpretation are stored separately.

### Existing-storage mapping status

| Existing structure | Current role | Canonical mapping/status |
|---|---|---|
| `portfolio_positions` | Go/API v2 normalized positions keyed by portfolio and stock | Primary candidate for `PositionState`; needs cash/equity/as-of enrichment |
| legacy `holdings` | Older Python services/tests and legacy portfolio paths | Compatibility source only; do not create new writes |
| `portfolio_holdings` migrations | Historical/alternate schema variants | Migration evidence; resolve physical source of truth before use |
| `signals` / `stock_signals_snapshots` | Generic or engine-specific signal history | Candidate input to `DecisionSnapshot`; not yet a complete decision ledger |
| `fair_value_runs` | Versioned valuation runs and scenarios | Maps to `valuation_snapshots`/valuation lineage |
| `swing_trades` / `swing_trade_signals` | Legacy swing trade records and signals | Candidate execution/thesis history; must be mapped before reuse |
| `workflow_executions` / stages | Operational workflow audit | Maps to `agent_runs` and orchestration provenance, not positions or trades |
| orders/fills | No canonical repository-backed lifecycle currently identified | Required before durable execution/reconciliation; paper broker remains in-memory only |

The new `app/portfolio/contracts.py` models and `app/portfolio/adapters.py` are storage-independent mapping contracts. They do not create tables or select a final physical schema. Missing `settled_cash`, `account_equity`, current-price timestamps, sector classification, or reconciliation status remains explicit in `missing_fields`/`reconciliation_status`.

The portfolio-agent implementation gate remains closed until this mapping is validated against the deployed database schema and active Go/Python callers.

### Additive physical history schema

The first physical contract migration is:

```text
supabase/migrations/033_create_portfolio_agent_history.sql
```

It creates namespaced `portfolio_agent_*` tables for snapshots, position states, theses, decisions, allocations, order plans, orders, fills, position events, and realized outcomes. It is intentionally additive and does not replace or delete legacy portfolio/holdings/signal tables. The migration must be applied through the project migration runner or the documented Docker Postgres command, then verified against the deployed schema before any portfolio-agent writer is enabled.

The current implementation adds `PortfolioSnapshotProvider` and `DecisionHistoryWriter` only. The provider reads the existing normalized `portfolio_positions` projection and requires account/cash inputs explicitly; it does not invent buying power or reconciliation. The writer appends snapshots, theses, decisions, timeline events, and outcomes to the namespaced tables through an injectable database executor. No portfolio review orchestration, ADD/TRIM/HOLD policy, scheduler, or broker integration is enabled by these contracts.

### Phase-1 manual portfolio review

The first portfolio graph is manual-only and review-only:

```text
PortfolioSnapshotProvider
    ↓
per-position canonical swing analysis
    ↓
manual PortfolioAction policy
    ↓
ADD / TRIM / HOLD / REVIEW
```

It must display the full per-symbol evidence and persist a snapshot plus decision history when requested, but it must not create `OrderPlan`, invoke `PortfolioAllocator`, call `PaperBroker`, or execute trades. `PortfolioAction.REVIEW` is the fail-closed result for missing price/account/reconciliation data. `AVOID` for a new entry is not automatically an existing-position `EXIT`.

The current implementation is `app/portfolio_review/`; portfolio orchestration remains separate from the execution pipeline until account state and reconciliation are ready.

### Daily position-review behavior

Every review starts with current portfolio state and the previous thesis/decision. It does not anchor on yesterday's action:

```text
previous thesis + previous decision
              ↓
current market, stock, fundamentals, valuation, events, position
              ↓
Decision Delta / Thesis Review
              ↓
new deterministic risk and portfolio policy
              ↓
ADD / TRIM / HOLD / EXIT / REVIEW
```

A position review must answer:

- What changed since the last decision?
- Is the original thesis still valid?
- Which invalidation conditions fired?
- Did market regime or event risk change?
- Is current exposure within target/risk limits?
- What evidence supports ADD, TRIM, HOLD, EXIT, or REVIEW?

`AVOID` for a new entry is not automatically `EXIT` for an existing position. Existing holdings require a separate portfolio-action policy.

### Decision confidence semantics

Store these separately:

```text
decision_confidence       # support for the current policy action
regime_confidence         # confidence in market classification
outcome_probability       # only after historical calibration
```

A confidence value must never be presented as the probability of profit.

### RBRK-style output invariant

Risk sizing and portfolio allocation are different quantities and must have distinct names:

```text
risk_recommended_shares  # quantity implied by stop/risk budget
allocated_shares         # quantity approved after portfolio/environment policy
order_quantity           # quantity placed in the order plan
filled_quantity          # quantity actually executed
```

For example, 48 risk-recommended shares and 24 allocated shares is valid if the market or strategy multiplier reduced exposure. Reports must display the distinction explicitly.

### Outcomes and backtesting

Every decision should be eligible for later outcome evaluation without reconstructing state from prose. Store forward labels/outcomes at defined horizons:

```text
1d, 5d, 10d, 20d, until stop, until target, until exit
```

Evaluate:

- realized return
- maximum favorable excursion
- maximum adverse excursion
- stop/target outcome
- holding period
- slippage and fees
- decision versus counterfactual decision
- market/strategy regime at decision time

This creates a walk-forward evaluation dataset for rules, strategies, allocations, and agent explanations.

## 13. Event-driven trading policy

Market regime and events are first-class inputs for swing and day trading. An expected event is not automatically bullish or bearish; the system measures surprise and post-event reaction.

Event lifecycle:

```text
scheduled event
    ↓
pre-event risk policy
    ↓
announcement capture
    ↓
market reaction snapshot
    ↓
confirmation window
    ↓
strategy environment update
    ↓
new decision
```

For FOMC, CPI, employment, earnings, FDA, regulatory, and major product events, store:

- event type and severity
- scheduled and actual timestamps
- expected versus actual result
- source and freshness
- affected symbols/sectors
- pre-event permissions
- post-event reaction
- confirmation status

For an extreme macro event, the default pre-event policy is:

```text
aggressive_long: false
leverage: false
breakout_buying: limited or avoid
new entries: reduced or blocked by horizon policy
```

Do not immediately reclassify the market from the headline alone. Require a reaction/confirmation window using the relevant instruments:

```text
SPY / QQQ
10Y yields
VIX
DXY
oil
semiconductors
breadth
```

Day trading requires intraday confirmation. Swing trading requires the post-event daily/overnight policy. Investing may use the event as a pacing or thesis input rather than a short-term trade veto.

## 14. Portfolio agent readiness gate

The portfolio agent must not be implemented against ambiguous portfolio data. Before enabling automated portfolio review or any add/trim/hold/exit workflow, the following questions must have an explicit answer, owner, source of truth, freshness SLA, and test fixture.

### Required portfolio/account questions

| Question | Required resolution |
|---|---|
| Is `current_value` refreshed reliably? | Define source, refresh job, freshness threshold, stale behavior, and reconciliation test. Cached value must carry `as_of` and `fetched_at`. |
| Is `current_price` live or end-of-day? | Store `price_type`, market status, exchange timestamp, timezone, provider, and quote age. Never use an EOD price as live execution truth. |
| Where is account cash stored? | Define settled cash, unsettled cash, pending withdrawals/deposits, buying power, margin cash, and currency. |
| Where is portfolio equity stored? | Define mark-to-market equity, prior close equity, realized/unrealized P&L, and valuation timestamp. |
| Are short positions supported? | Explicitly model long/short quantity, borrow availability, borrow fee, locate status, margin, and buy-to-cover. Until complete, shorting is disabled. |
| Are options or ETFs supported? | Define instrument taxonomy. ETFs may use equity rules; options require contract, expiry, strike, multiplier, Greeks, IV, bid/ask, open interest, assignment, and margin. Unsupported instruments must be rejected, not treated as stocks. |
| Are stops and targets stored? | Store protective orders and intended levels separately from positions, including order IDs, trigger source, status, and replacement history. |
| Is `portfolio_heat` persisted? | Derive it from open position risk and persist the calculation inputs/version; do not trust a manually entered number. |
| Are sector classifications available for every position? | Store sector/industry provider, classification date, and unknown state. Unknown exposure must tighten concentration controls. |
| Are duplicate positions possible? | Enforce a position identity policy by account, portfolio, instrument, and side; aggregate or reject duplicates deterministically. |
| How are closed positions represented? | Preserve immutable fills/trades and realized P&L; do not delete positions needed for audit and performance evaluation. |
| What timezone/as-of timestamp applies? | Every price, holding, decision, order, fill, cash balance, and event carries timezone-aware `as_of`, `fetched_at`, and source timestamps. |

### Current repository status

The existing portfolio API exposes symbol, quantity, average price, cached current price/value, and unrealized P&L through `/api/v1/portfolio/portfolios/{portfolio_id}/holdings`. It also has a refresh-metrics endpoint. However, the new canonical portfolio read model still needs explicit contracts for settled cash, buying power, equity timestamp, portfolio heat, sector exposure, stops/targets, short/options support, duplicate identity, and as-of semantics. The current holdings response labels records as stock positions, so options and multi-leg instruments are not yet supported by the canonical portfolio agent.

The existing `/api/v1/trading-v3/decisions/run-portfolio` endpoint is a legacy batch decision path. It must not become the new portfolio agent because it does not run the canonical technical/fundamental/risk/order workflow.

### API consolidation decision

- `app/api_server.py` is the only supported Python-worker runtime entrypoint. The former `app/api_app.py` alternate application was retired, and deployment checks/docs now reference `api_server.py`.
- Portfolio v1 and v2 remain temporarily registered under `/api/v1/portfolio` and `/api/v2/portfolio` because they overlap on CRUD but each still has unique consumers/capabilities. Portfolio v1 currently owns refresh metrics, valuation, analysis, and schedules; v2 owns richer holding update/delete and stock enrichment. They will be merged behind one canonical portfolio service/contract before either router is removed.
- `stocks_api.py` and `stock_symbols.py` are complementary today: stock management/search versus symbol details/batch metadata. They are not deleted as duplicates until their response contracts and callers are unified.
- Legacy trading decision v2/v3 endpoints remain compatibility surfaces only; the canonical case-file graph owns new analysis and decision behavior.

### Portfolio truth and reconciliation

Use an internal portfolio projection/IBOR for analysis, but treat broker/custodian execution state as authoritative when connected. Reconcile at minimum:

```text
positions
transactions/fills
cash
```

Cash must distinguish trade-date cash from settlement-date cash. Equity and buying power must not be conflated. Reconciliation breaks require classification, remediation, audit evidence, and a safe trading response; unresolved breaks block new orders.

### Market and event readiness

For every portfolio review, capture:

- market-regime snapshot and freshness
- horizon policy (`swing`, `investing`, or `day_trading`)
- market-hours and exchange calendar
- earnings and corporate-action proximity
- macro/event risk relevant to the horizon
- provider/API budget and data completeness

Day trading requires intraday prices, VWAP, opening range, spreads, liquidity, intraday breadth, and catalyst freshness. Swing trading requires daily technicals, sector/benchmark relative strength, and event-aware overnight rules. Cached fundamentals may be reused according to the freshness policy: core statements up to 30 days, valuation/forward estimates up to 15 days, event data daily, and prices/technicals every run. A filing, earnings release, guidance change, or material corporate action invalidates the normal TTL.

### Short-squeeze and short-risk readiness

Before supporting short recommendations, the system must evaluate:

- short interest and float
- days to cover
- borrow availability and borrow fee
- utilization and locate status
- gap/news/catalyst risk
- options open interest, implied volatility, and gamma where relevant
- liquidity, spread, and halt risk

Missing short-risk data disables shorting; it must not be treated as neutral.

### Implementation gate

Portfolio-agent implementation is blocked until the above contracts are resolved and tested with:

1. stale price/value data
2. unsettled cash and pending fills
3. partial fills and cancel/replace
4. duplicate position records
5. corporate actions and symbol changes
6. long, short, ETF, and unsupported option fixtures
7. missing sector classification
8. timezone/as-of mismatches
9. unresolved reconciliation breaks
10. short-squeeze data missing or extreme

Research basis: the design follows IBOR/OBOR reconciliation, explicit order lifecycle, settled/unsettled cash separation, and layered pre-trade controls described by the [SEC books-and-records rule](https://www.sec.gov/files/investment/pfa-vacatur-reverted-rule-text.pdf), [FIA automated-trading risk-control guidance](https://www.fia.org/sites/default/files/2024-07/FIA_WP_AUTOMATED%20TRADING%20RISK%20CONTROLS_FINAL_0.pdf), [FCA algorithmic-control observations](https://www.fca.org.uk/publications/multi-firm-reviews/algorithmic-trading-controls), and [investment-operations engineering references](https://handbook.fintechengineer.io/chapters/money/investment-operations.html). These sources inform engineering controls; they do not replace applicable legal or broker requirements.

## 15. Implementation phases

1. **Canonicalization:** remove legacy regime implementations and migrate consumers to `app.market_regime`.
2. **Strategy Environment:** implement daily swing/positional/investing environment first; day trading remains unavailable until intraday data contracts exist.
3. **Swing stock opportunity:** daily stock features, relative strength, setup detection, and focused evals.

### Swing opportunity contract

The swing subgraph accepts `identity.symbol`, the canonical market snapshot/regime/environment, and daily OHLCV for the symbol, SPY, and (when available) its sector ETF. It writes only the stock and setup namespaces:

```text
stock.technicals
stock.relative_strength
stock.volume
stock.sector_alignment
stock.data_quality
setup.type
setup.quality
setup.confirmation
setup.falling_knife
setup.reasons
```

It may recommend `NEXT: RISK_ASSESSMENT`, but it may not emit BUY, set a stop, calculate portfolio size, or bypass market permissions. Missing sector/profile data lowers confidence; missing or stale price data makes the opportunity unavailable. Relative strength is measured against both SPY and the mapped sector ETF when available.

### Integrated stock-analysis case file

The swing case graph fetches shared symbol inputs once, then fans out into independent technical and fundamental branches:

```text
symbol_data (read-only shared inputs)
       ├── technical_analysis  -> case.stock
       └── fundamental_analysis -> case.fundamentals
                    \           /
                     setup_detection
                           ↓
                      risk_assessment
```

The technical branch owns `stock`; the fundamental branch owns `fundamentals`; setup reads both and owns `setup`/`opportunity`; risk reads validated outputs and owns `risk`. Branches may not overwrite one another. The graph uses separate keyed state fields rather than merging competing scores. Fundamental unavailability lowers confidence and is recorded in reasons; it does not fabricate a neutral score or automatically invalidate every short-term technical setup.

4. **Risk and decision:** portfolio-aware sizing and deterministic decision gate.

### Risk-engine contract

The risk engine consumes the validated swing opportunity, market permissions, setup, entry/stop/target proposal, account equity, open-trade risk, and portfolio constraints. It writes only the `risk` namespace:

```text
risk.entry
risk.stop
risk.target
risk.risk_per_share
risk.reward_risk
risk.position_size
risk.portfolio_heat
risk.allowed
risk.blocking_reasons
risk.provenance
```

The risk engine may reject or reduce an opportunity, but it may not create a setup or issue the final BUY/WAIT/AVOID action. Position sizing is fixed-fractional and constrained by market size multiplier, maximum position size, portfolio heat, open-trade count, liquidity, and event restrictions. Missing account or portfolio data is insufficient information, not permission to assume a safe trade.

Database/account adapters may provide inputs to the pure risk engine, but risk rules and sizing remain in the canonical risk package and are independently evaluated. The former database-backed `SwingRiskManager` implementation has been removed.

5. **Fundamental Intelligence:** typed multi-dimensional business and financial assessment; no universal P/E category rules.

### Fundamental intelligence contract

Fundamental intelligence is separate from technical opportunity and valuation. It produces orthogonal dimensions rather than one opaque stock score:

```text
Growth
Profitability
Cash-flow quality
Balance sheet
Capital efficiency
Competitive advantage
Earnings revision
Fundamental risk
Business type
Style tags
```

A `FundamentalAssessment` may include an overall screening score, but every dimension retains its own score, label, coverage, raw metrics, and unavailable state. Missing moat evidence, revisions, peer history, or point-in-time statements must remain `UNAVAILABLE`; the engine must not infer them from price or assign a default neutral score.

Business quality and stock valuation are separate outputs:

```text
business quality: exceptional
valuation: premium
```

is valid and must not be collapsed into either `BUY` or `BAD BUSINESS`.

The initial canonical fundamentals provider contract supports TTM metrics from `FundamentalsSnapshot`. It does not yet justify historical/peer multiple distributions, estimate revisions, or DCF fair value. Those require separate versioned data contracts. Until then:

- forward P/E, PEG, P/S, P/B, and FCF yield are valuation diagnostics
- no universal fair P/E is assigned by business category
- PEG is a relative growth/valuation diagnostic, not intrinsic value
- DCF and Bear/Base/Bull/Stress fair values belong in a future `app/valuation/` package
- valuation methods must be selected by business type and data sufficiency

COIN-like businesses also require explicit cyclicality, regulatory, commodity/crypto sensitivity, and earnings-event risk flags rather than being scored only as generic growth companies.

6. **Intraday/day trading:** intraday data, VWAP, opening range, freshness, liquidity, and event handling.
7. **Investing:** point-in-time fundamentals and staged accumulation.
8. **Trading Intent and allocation:** explicit capital, horizon, mode, universe, risk, and permission policy; deterministic portfolio allocation.
9. **Order planning:** validated entry/stop/target/order parameters derived from an approved decision; no broker side effects.
10. **Execution and monitoring:** paper trading, approvals, order state, reconciliation, and realized-outcome evaluation.

### Final decision contract

The Final Decision Engine is the only canonical owner of the action namespace. It consumes validated `market`, `strategy_environment`, `stock`, `fundamentals`, `setup`, `catalyst`, and `risk` namespaces and writes only:

```text
decision.action              # BUY | BUY_SMALL | WAIT | AVOID | EXIT
decision.confidence
decision.reasons
decision.vetoes
decision.requires_approval
decision.provenance
```

Decision precedence is deterministic:

1. Insufficient or stale required data -> `WAIT`.
2. Falling knife, invalid setup, or explicit safety veto -> `AVOID`.
3. Risk not allowed because of market permissions, portfolio heat, event restrictions, or position limits -> `WAIT`.
4. Valid risk and high-quality setup with strong supporting evidence -> `BUY` or `BUY_SMALL` according to environment, valuation, and size policy.
5. No qualifying setup -> `WAIT`.

The decision engine cannot create a setup, change a stop, increase position size, or bypass a risk veto. `BUY` is an analysis recommendation only until a separate approval/execution boundary validates it.

### Trading intent, allocation, order planning, and paper execution

`TradingIntent` is the explicit user/system policy input:

```text
capital
horizon
mode (analysis | paper | live)
universe
risk limits
position limits
short/leverage permissions
approval requirement
```

The strategy router must reject unsupported horizons instead of silently using another horizon's data. Daily data cannot authorize day trading.

`PortfolioAllocator` consumes the intent, validated `TradeDecision`, `RiskAssessment`, and a point-in-time portfolio snapshot. It owns capital allocation only; it cannot create a setup, change risk limits, or bypass a veto. It must account for available cash, current portfolio heat, open positions, concentration, and market size multipliers.

`OrderPlan` is a side-effect-free, validated representation of an intended order. It owns order type, side, quantity, limit/stop/target, time-in-force, slippage tolerance, expiry, and approval requirements. It cannot submit orders.

`PaperBroker` is the first execution adapter. It owns simulated cash, orders, fills, positions, fees, slippage, and lifecycle events. It must expose the same conceptual interface as a future live broker and must never call a real broker. Execution state is authoritative for simulated positions; graph checkpoints only reference it.

No live autonomous trading is enabled merely because an analysis graph succeeds. Paper-trade and human-approval gates are required before execution.

## 16. UI, Go API BFF, and agent boundary

All user interfaces must communicate through the Go API. This applies to Streamlit now and future React/Next.js/web clients later.

```text
Streamlit / Web UI
        ↓ HTTP/JSON/SSE
Go API BFF
  - authentication and authorization
  - portfolio ownership checks
  - request validation
  - idempotency
  - job/run lifecycle
  - human approvals
  - audit and API contracts
        ↓ internal HTTP/job queue
Python worker
  - LangGraph orchestration
  - deterministic quant/risk engines
  - LLM interpretation
  - provider/data adapters
        ↓
Postgres / market providers
```

The UI must not call the Python worker directly, import Python domain code, calculate trading rules, or treat Streamlit session state as durable memory. Go API response models are the frontend contract and must be reusable by future web clients.

### Canonical agent-run API

Agent workflows should be exposed by Go as durable runs, not synchronous UI-specific functions:

```text
POST /api/v1/agent-runs
GET  /api/v1/agent-runs/{run_id}
GET  /api/v1/agent-runs/{run_id}/events
GET  /api/v1/agent-runs/{run_id}/result
POST /api/v1/agent-runs/{run_id}/approve
POST /api/v1/agent-runs/{run_id}/reject
POST /api/v1/agent-runs/{run_id}/feedback
```

A run request must include:

```text
portfolio_id
agent/workflow kind
horizon
mode (analysis | paper | live-disabled)
as_of / timezone
requested scope (market | portfolio | watchlist | symbol)
idempotency key
```

The Go API owns run authorization, status, retries, cancellation, progress events, and human decisions. Python returns typed graph results and observability metadata; it does not own browser sessions or user authorization.

### Agentic UI behavior

The UI should expose the agent loop without hiding deterministic controls:

```text
request
  ↓
plan / route
  ↓
tool and graph progress
  ↓
deterministic evidence
  ↓
LLM synthesis/explanation
  ↓
validation gates
  ↓
human approval or rejection
  ↓
persisted feedback/outcome
```

Every recommendation page must show:

- run ID and as-of timestamp
- data freshness and missing fields
- deterministic facts and rule versions
- agent interpretation and model version
- risk vetoes and event policy
- prior decision/thesis delta
- human approval/rejection controls

No UI button may directly submit a broker order. In the manual phase, the UI records approval/rejection and optionally creates a reviewable order plan; execution remains disabled.

### Current migration requirement

Existing Streamlit pages that call Python worker endpoints directly or calculate their own portfolio/technical logic must be migrated behind Go API BFF endpoints before being used as the canonical cockpit. The current enhanced portfolio page contains direct Python-worker URL configuration and is therefore a legacy exception, not the target architecture.

The Go API may proxy Python worker calls internally, but the browser-facing contract remains Go-owned. This keeps Streamlit replaceable by web pages without changing agent workflows.

## 17. Definition of done for each phase

A phase is complete only when:

- one canonical implementation exists
- typed input/output contracts are documented
- deterministic rules are covered by evals
- missing and stale data behavior is tested
- the graph can run without an LLM
- LLM disagreement is observable but cannot bypass policy
- Langfuse metadata is emitted or explicitly marked pending
- walk-forward/evaluation hooks exist
- downstream consumers use the canonical contract
