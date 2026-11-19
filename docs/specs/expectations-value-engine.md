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
New table `narrative_claims`:

```
symbol, claim, direction (positive|negative|mixed),
claim_type (reported_fact|management_guidance|analyst_estimate|
            industry_research|model_assumption|llm_hypothesis),
source, source_date, evidence_strength 0-1, confidence 0-1,
status (proposed|supported|confirmed|speculative|contradicted|expired),
first_seen, last_confirmed, created_by, supersedes (parent id), as_of
```

Status changes are new rows with `supersedes` — the append-only
pattern from `thesis_change_events`; the full chain stays auditable.

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
- quadrants: `best_setup | dangerous_euphoria |
  potential_opportunity | avoid_investigate`

`potential_opportunity` = depressed expectations + negative sentiment
+ `thesis_integrity` intact — the review's "market pessimistic,
opportunity intact" case, explicitly gated on integrity so a falling
knife doesn't read as opportunity. New column on `valuation_decisions`
(mig 214 ALTER) + surfaced on the priced-in card.

---

## Phase 2 — `driver_bridge`

The gap the proposal got right: our scenarios vary *multipliers*;
defensible scenarios should vary *drivers* — TAM, share, price,
margin — per industry.

`driver_assumptions` table: `(symbol, scenario, driver_key, value,
unit, rationale_claim_id)` — `rationale_claim_id` links every
assumption to a `narrative_claims` row, so a driver that loses its
evidence can't keep anchoring a scenario silently.

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

### `claim_reviews` journal

Critic output + every status transition — who/what moved a claim,
with the evidence row id. This is the ledger's own falsification
trail and the audit answer to "why does the system believe X".

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
