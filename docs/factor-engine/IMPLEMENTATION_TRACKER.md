# Factor Engine — Implementation Tracker (Living Doc)

## Purpose
Single source of truth for **where we are**, **what’s next**, and **what “done” means**.

This doc is intended to be updated continuously during implementation so any contributor can:
- understand the current phase/status
- know exactly what to implement next
- avoid scope drift (no new nouns, no reach-around dependencies)

---

## Locked architectural decisions
- **Canonical technical read source (Phase 2)**: `indicators_daily`
- **Canonical fair value provider (Phase 2)**: Fair Value v2
- **Fair value v1**: legacy validation comparator (diff reports)
- **Factor IDs**: dotted namespaces
- **Namespaces**:
  - `meta.*`, `fundamental.*`, `quality.*`, `valuation.*`, `technical.*`, `ai.*`, `catalyst.*`, `risk.*`, `derived.*`
- **derived.* reserved** for cross-domain synthesized metrics only (e.g., `derived.fgbi`, `derived.ecs`, `derived.opportunity_score`)
- **Confidence**: 0–100 integer, computed via:
  - `0.40*source_reliability + 0.30*data_freshness + 0.20*coverage + 0.10*calculation_stability`
- **Layering principle**:
  - Providers own retrieval
  - Registries own discovery
  - Scoring engines own computation
  - Screeners own weighting
  - No layer reaches around another layer

---

## Reference docs (by phase)
- Phase -1: `docs/factor-engine/00_phase_-1_data_capability_audit.md`
- Phase 0: `docs/factor-engine/01_phase_0_domain_model.md`
- Phase 1: `docs/factor-engine/02_phase_1_source_of_truth_registry.md`
- Phase 2: `docs/factor-engine/03_phase_2_factor_provider_layer.md`

---

## Current status (update this first)
- **Current phase**: Phase 2 — Factor Provider Layer
- **Last updated**: 2026-07-25
- **In progress**:
  - Implement providers (MetaProvider, TechnicalProvider, FinancialProvider, ValuationProvider, AIProvider, CatalystProvider, RiskProvider)
- **Next step**:
  - Implement TechnicalProvider first (must normalize `indicators_daily` schema drift), then MetaProvider; follow with CatalystProvider (earnings_calendar canonical)

---

## Execution roadmap (phases + acceptance criteria)

### Phase -1 — Data Capability Audit (required before coding)
**Goal**: confirm factor availability, coverage, history, refresh cadence, and gaps.

**Deliverables**:
- Data Capability Matrix populated for v1 factor set
- Readiness tags for initial universes and profiles: `ready_now | gated | blocked`

**Acceptance criteria**:
- Every factor referenced in any config has:
  - owner (provider)
  - canonical source
  - availability + historical assessment
  - documented gap if missing

**Status**: DONE

**Decisions locked by Phase -1**:
- **Canonical earnings storage** for CatalystProvider: `earnings_calendar` (treat `earnings_data` as legacy/compat)
- **v1 risk factors** (`risk.volatility_30d`, `risk.max_drawdown_1y`, `risk.var_95`): computed deterministically from `raw_market_data_daily` (treat `risk_factors` table as optional v2 source)

**Repo-backed findings so far (high signal)**:
- **Technical**: `indicators_daily` has **schema drift** across migration sets (wide vs narrow).
  - Action: TechnicalProvider must normalize both schemas or we must standardize on one applied schema.
- **Fundamentals**: `fundamentals_snapshots` has **history ambiguity** depending on which migration set is active.
  - In one schema it is `(symbol UNIQUE)` which prevents multiple as-of rows.
  - Action: canonicalize snapshot history semantics in SoTR; ensure prod schema supports multiple as-of rows.
- **Catalysts**: `catalyst.eps_revision_*` has **no repo-backed provider/table** yet.
  - Action: gate ECS-dependent profiles until a revisions provider exists.
- **Earnings storage**: competing schemas exist (`earnings_calendar` vs `earnings_data`).
  - `EarningsCalendarRepository` creates/uses `earnings_calendar`.
  - `python-worker/app/data_management/table_mapping.py` maps `DataType.EARNINGS` -> `earnings_data`.
  - Action: pick one canonical table in SoTR and align refresh/summary endpoints.
- **AI**: `stock_ai_insights` storage exists but ingestion/automation is unclear.
  - Action: treat as ⚠️ partial with low confidence until ingestion pipeline is confirmed.
- **Quality factors**: growth-quality / early-warning engines exist, but persistence + standardized factor outputs are not defined.
  - Action: treat as ⚠️ until we extract deterministic factor snapshots from the engines and remove placeholder inputs.

---

### Phase 0 — Domain Model
**Goal**: enforce vocabulary boundaries so new “scores” don’t become new nouns.

**Deliverables**:
- Domain Model doc finalized (already drafted)

**Acceptance criteria**:
- New PRs map to domain entities (no new first-class nouns)

**Status**: DRAFTED (docs exist)

---

### Phase 1 — Source of Truth Registry (SoTR)
**Goal**: canonical owner + canonical read source documented per factor.

**Deliverables**:
- SoTR table seeded for v1 factors
- Duplicate ecosystem entries captured (technical tables, fundamentals stores, fair value v1/v2)

**Acceptance criteria**:
- Any factor used by any runtime component appears in SoTR

**Status**: DONE (SoTR seeded in `docs/factor-engine/02_phase_1_source_of_truth_registry.md`)

---

### Phase 2 — Factor Provider Layer (first implementation milestone)
**Goal**: runtime layer to fetch raw factor snapshots consistently.

**Providers**:
- MetaProvider → `meta.*`
- TechnicalProvider → `technical.*` (canonical read: `indicators_daily`)
- FinancialProvider → `fundamental.*`
- ValuationProvider → `valuation.*` (canonical engine: FV2)
- AIProvider → `ai.*`
- CatalystProvider → `catalyst.*`
- RiskProvider → `risk.*`

**Deliverables**:
- Provider interfaces + concrete implementations
- Standard `RawFactorSnapshot` output w/ provenance + confidence + version

**Acceptance criteria**:
- A single caller can request `(symbol, as_of_date)` and receive a consistent set of raw factors
- Downstream code stops querying raw tables directly for canonical factors

**Status**: NOT STARTED

---

### Phase 3 — Raw vs Derived registries + dependency validation
**Goal**: keep factor graph acyclic and explainable.

**Deliverables**:
- Raw Factor Registry
- Derived Factor Registry (config-driven)
- Validator that enforces layer boundaries:
  - raw factors have no dependencies
  - derived depends on raw only
  - group scores depend on raw+derived
  - headline scores depend on group scores

**Status**: NOT STARTED

---

### Phase 4 — Factor Groups + ScoreDefinitions (configurable headline scores)
**Goal**: groups are stable; headline scores are configs, not hardcoded.

**Deliverables**:
- Group score definitions (including `risk_score`)
- Headline score definitions (initially: investment/entry/catalyst/opportunity) as configs
- Versioning embedded in ScoreSnapshot outputs

**Status**: NOT STARTED

---

### Phase 5 — Universes + fully declarative Screening Profiles
**Goal**: new screener requires config only.

**Deliverables**:
- Dynamic UniverseDefinitions (rule-based)
- ScreeningProfile schema includes:
  - universe
  - ranking
  - filters
  - min scores
  - sorting
  - explain
  - rebalance

**Status**: NOT STARTED

---

### Phase 6 — Regression harness (parity before deprecation)
**Goal**: compare old vs new results and explain diffs.

**Deliverables**:
- Old screener results vs new profile results
- Diff report + deterministic reason breakdown

**Status**: NOT STARTED

---

### Phase 7 — Explainability engine (two-layer)
**Goal**: deterministic contributions + human-friendly narrative.

**Deliverables**:
- Contribution report per recommendation:
  - factor contribution
  - group contribution
  - confidence propagation
- Narrative report (templated/LLM-assisted) that references deterministic facts

**Status**: NOT STARTED

---

### Phase 8 — Historical snapshots
**Goal**: daily storage of profile outputs for rank history, alerts, and backtests.

**Deliverables**:
- Persist per day/run:
  - universe
  - profile
  - ranks
  - scores
  - drivers/risks (or references)

**Status**: NOT STARTED

---

### Phase 9 — Deprecation and consolidation
**Goal**: retire duplicates only after parity + snapshots.

**Deliverables**:
- Deprecation schedule tracked in SoTR
- Remove reach-around dependencies

**Status**: NOT STARTED

---

## Working agreements
- No new factor/score concept is introduced without:
  - FactorDefinition (id, unit, provider, frequency)
  - SoTR entry
  - confidence strategy
  - explainability strategy

---

## Change log
- 2026-07-25: Created tracker doc; locked canonical sources (indicators_daily, FV2), namespaces, confidence model.
