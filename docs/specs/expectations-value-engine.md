# Spec — Expectations & Value engine delta

The four pieces the review found missing. Everything else in the
proposal already exists — `growth_priced_in` (market expectations),
`fair_value_v2` (scenarios/reverse-DCF), `valuation_decision`
(quality × priced-in matrix, integrity, bands), tape/momentum/
positioning (sentiment), `thesis_health` (hypotheses), `journal_grades`
(falsification). This spec adds only the delta, as journaled
compositions — never a second engine.

Locked decisions:

- **Deterministic-first, journaled-everything.** LLM touches edges
  only (claim extraction, critic review) through `llm_completion`,
  and every LLM-authored claim lands as `llm_hypothesis` — never
  promoted to `confirmed` without a data leg.
- **Composition, not parallel computation.** Every read composes
  existing journaled rows; new tables hold only things no current
  table expresses.
- **Expectations ≠ sentiment.** They stay separate axes through the
  whole pipeline — sentiment may shift `timing`, never `fair_value`.

---

## Phase 1 — `narrative_ledger` + `timing_quadrant`

### `narrative_ledger` — claims with provenance, journaled

The gap: `thesis_health` tracks hypotheses but carries no provenance
taxonomy — a rumor and a 10-Q sentence look identical downstream.
New table `narrative_claims` — **type and status are separate
dimensions, never one taxonomy.** `claim_type` is immutable
provenance (a guidance claim stays guidance even when later data
supports it); `status` is the mutable evidentiary state that only
journaled evidence may move:

```
claim_id (stable public id), symbol, entity?, claim,
direction (positive|negative|mixed),
claim_type (reported_fact|management_guidance|analyst_estimate|
            industry_research|model_assumption|llm_hypothesis)  -- immutable
status (proposed|supported|confirmed|speculative|contradicted|
        expired|unresolved)                                       -- mutable
source, source_date,
evidence_confidence 0-1,        -- strength of evidence FOR the claim
outcome_confidence 0-1,         -- that the predicted outcome lands;
                                  mgmt-confirmed program ≠ produced
                                  revenue — never collapse the two
valid_from, valid_until,
evidence_refs jsonb,            -- row ids behind each status change
first_seen, last_confirmed, created_by,
supersedes (parent claim_id), as_of
```

**Status rule:** transitions require new journaled evidence — an LLM
repeating a claim never confirms it; every move writes a
`claim_reviews` row carrying the evidence row id. `speculative` and
`contradicted` both surface; nothing silently deletes.

**Writers (deterministic first):**
- `earnings_watch` — its `release.claims` extraction already emits
  guidance claims; persist them as `management_guidance` rows
- `earnings-quality` flags → `reported_fact` negative claims
- `driver_commitments` (raised/cut guidance) → `management_guidance`
- Flywheel `est_revision_pct` swings → `analyst_estimate` claims
  (revisions are street beliefs, journaled as such — not facts)

**Status transitions are evidence-gated:** a claim moves to
`confirmed`/`contradicted` only when a journaled data row supports it
(earnings print, sec_facts, revision series) — promotion carries the
evidence row's id. `speculative` and `contradicted` claims both
surface; nothing silently deletes.

**LLM leg (bounded):** a `claim-extract` pass over new `doc_analyses`
may propose `llm_hypothesis` claims; a `critic` pass (one
`llm_completion` call per symbol, capped, journaled as
`claim_reviews`) marks each `supported | weak | contradicted` with
cited evidence ids — the critic can downgrade, never self-promote.

### `timing_quadrant` — expectations × sentiment

Inside `valuation_decision.evaluate` — the orthogonal second axis the
review called out. `quality × priced-in` answers *what to own*;
`timing` answers *when*:

- expectations axis: `priced_in_attractiveness` (existing)
- sentiment axis: composite of `tape_state`, `momentum_regime`,
  `muted_reaction`, put/call + short-interest where journaled → 0-100
- quadrants (conceptual, not buy/sell signals — thresholds need
  calibration):
  - low exp + positive sentiment → `recovery_improving` — check if
    price already anticipated it
  - high exp + positive → `crowded_optimism` — execution may be
    priced in
  - low exp + negative → `potential_opportunity` — only with
    `thesis_integrity` intact
  - high exp + negative → `expectations_breaking` — investigate
    estimate cuts, execution, compression

Expectations and sentiment are computed **independently** — low
expectations is not cheap valuation; the valuation bands and
`thesis_integrity` are gates on the quadrant, not axes in it. New
`timing` column on `valuation_decisions` (mig 214) + surfaced on the
priced-in card.

---

## Phase 2 — `driver_bridge`

The gap the proposal got right: our scenarios vary *multipliers*;
defensible scenarios should vary *drivers* — TAM, share, price,
margin — per industry.

`driver_assumptions` table — every material assumption carries its
own provenance (`assumption_type`) and forecast `confidence`; when
`rationale_claim_id` is null the row must declare itself
`model_assumption` — an unsupported assumption can never quietly
become a forecast:

```
symbol, scenario (bear|base|bull), driver_key, value, unit, period,
assumption_type (analyst_estimate|management_guidance|model_assumption|
                 industry_research|reported_fact),
rationale_claim_id, confidence 0-1, as_of
```

More granular than TAM × share wherever evidence allows — design
wins vs production programs, units × revenue-per-unit, pricing/mix,
capex/wc/dilution. The bridge explains *why* revenue grows 30%, never
just that it might.

Driver catalog keyed off the FV engine's existing `_detect_regime`
output (no second taxonomy): semis → design_wins/content_per_system;
saas → arr_growth/seat_expansion/retention; banks → nim/loan_growth;
utilities → rate_base/power_price; industrial → backlog/conversion;
plus generic → market_growth/share/margin/fcf_conversion.

`driver_bridge.run(sym)`: reads bear/base/bull rows → collapses to
the growth/margin/duration scalars `decision_scalars` already
consumes → writes a `driver_forecast` JSONB on the run. The FV
resolver keeps its contract — this is an *input* leg, never a
parallel valuation.

Seeding honesty: initial rows come from journaled evidence (backlog,
RPO, `symbol_sec_facts`, management drivers) and explicit analyst
entries — not auto-invented bottom-up forecasts. Missing drivers
→ `missing_inputs`, scenario falls back to multipliers.

---

## Phase 3 — `company_report` + `claim_reviews`

### `GET /symbol/{sym}/expectations-report`

The five answers, pure composition over journaled rows:

1. **What the market believes** — `growth_priced_in` latest +
   `narrative_claims` by direction/status
2. **Growth drivers with evidence** — `driver_assumptions` joined to
   claims + `tailwinds`/`pipeline` legs
3. **Priced-in** — required vs forecast CAGR, gap, drag, score
4. **FV bands** — bear/base/bull + dispersion + `driver_forecast`
   provenance
5. **What would change it** — `thesis_integrity` evidence +
   `watch`/`contradicted` claims + open `driver_commitments`

Rendered as an "Expectations" card under the priced-in card on the
stock page — same five-section layout, `None` where a leg is missing.

### `claim_reviews` journal — three `review_kind`s

`transition` — every status change with the evidence row id.
`critic` — bounded LLM review of new/changed claims only: flags
unsupported assertions, requests missing evidence, flags
contradictions; can downgrade, never rewrite forecasts or flip
status alone.
`grade` — outcome grading at 3/6/12mo horizons: did the ramp
happen, did the margin improve, did the commitment convert? This is
what calibrates `evidence_confidence`/`outcome_confidence` priors
over time instead of trusting arbitrary scores — the ledger's own
falsification trail.

---

## Migrations

| # | Table | Purpose |
|---|---|---|
| 214 | `narrative_claims` + `valuation_decisions` ALTER `timing` | claims ledger + quadrant column |
| 215 | `driver_assumptions` | scenario driver inputs |
| 216 | `claim_reviews` | status transitions + critic verdicts |

## Endpoints + jobs

- `GET /symbol/{sym}/narrative-claims` — current claims + history
- `GET /symbol/{sym}/expectations-report` — Phase-3 composition
- `narrative-claims` job — collect deterministic writers (after
  `earnings-watch`, `earnings-quality`, `flywheel`)
- `critic` job — bounded LLM review, weekly + on new-hypothesis

## Acceptance

1. AVGO claims: guidance claims journaled post-print carry
   `management_guidance` + source; none show `confirmed` without an
   evidence row
2. Quadrant: a priced-in-cheap name with broken tape →
   `potential_opportunity` only when integrity intact; deteriorating
   → `avoid_investigate`
3. A `driver_assumptions` bear case changes the FV run's inputs, not
   its contract — same output schema, `driver_forecast` provenance
   attached
4. The report answers all five questions for NVDA/AVGO/CEG with
   `None` (not fabricated values) where legs are missing

## Non-goals

- No agent farm — no "researcher/sentiment/forecaster" LLM roles;
  deterministic collectors + one bounded critic
- Sentiment never enters `fair_value` — it shifts `timing` only
- No second classification taxonomy — driver catalog keys off
  `_detect_regime`
- No auto-generated bottom-up forecasts until the ledger has quarters
  of graded claims to calibrate against
