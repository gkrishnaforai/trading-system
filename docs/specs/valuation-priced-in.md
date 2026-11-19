# Growth priced-in + decision bands — spec (all phases)

Status: proposed · Phase 1 buildable now (all inputs already flow)

The question this answers is not "what is the stock worth" — the FV
engine already blends that. It answers: **what is the market assuming,
what do we believe differently, and at what prices do we enter, trim,
and exit.** Explanation engine, not another stock score.

## Existing substrate (do not rebuild)

- `fair_value_service` — regime-detected multi-method FV blender
  (dcf_simple, pe_forward, peg×2, ev_sales, adjusted_pe, pb_bank,
  normalized EPS), dispersion + confidence, journaled runs
- `expectation_gap` (flywheel) — estimate-momentum gap (accel/beats/
  revisions/coverage) → gap_score
- `earnings-quality` job — forensic quality score
- `growth-quality` — growth composite
- `fund-journal` — quarterly financials history (cycle normalization)
- `journal_grades` — forward-return grading substrate for new buckets

## Honesty rules (locked)

- None when inputs are missing or the metric is inappropriate — never
  substitute zero, never manufacture an EPS CAGR for an unprofitable
  name (revenue/gross-profit/burn-path variant instead)
- Required CAGR is labeled: *growth needed under OUR chosen exit
  multiple + return target* — not "the market's forecast". Implied
  growth from reverse DCF is the triangulation, reported separately
- Two scores always separate: business quality ≠ valuation
  attractiveness

---

## Phase 1 — `growth_priced_in/` (the inverse solve)

New module `app/valuation/growth_priced_in.py`. Pure math over inputs
already in `stock_insights_snapshots` / flywheel / FV method results.

### Metrics per symbol (all nullable)

- `forecast_cagr` — analyst fwd EPS curve (flywheel's fwd_eps_avg +
  estimate snapshots) crossed with our accel-based forecast; CAGR over
  the analyst horizon, clipped to sanity bounds (−50%…+60%)
- `required_cagr(price, starting_eps, exit_pe, required_return=0.10,
  years=3)` — solve `g = (P×(1+r)^n / (EPS_fwd × PE_exit))^(1/n) − 1`.
  Horizon and hurdle are parameters, not constants. Reject nonpositive
  EPS / exit PE / missing price → None, never a misleading CAGR.
  starting_eps must be the fiscal-year EPS matching the horizon's
  first year — not a blended fwd number (EPS consistency rule below)
- `implied_growth` — reverse DCF: solve g so a 2-stage DCF (FCF base,
  WACC, terminal 2.5%) reproduces price. Bisection over g ∈
  [−50%, +100%]. Status taxonomy, not silent None:
  `valid | negative_fcf | insufficient_fcf_history |
  unstable_cash_flows` (|FCF stdev / FCF mean| > 1.0 over 8q).
  Burning names get the revenue→FCF pathway note, not a fake number
- `expectation_gap` = forecast_cagr − required_cagr (pp)
- `compression_drag` — annualized return impact of multiple
  normalization: `(pe_normal/pe_now)^(1/n) − 1`. Stored alongside
  `expected_annual_return` (growth + drag + yield) — drag is a
  component of the total, never conflated with it
- `fv_bear / fv_base / fv_bull` — the existing blend re-run under
  scenario inputs; scenario ranges derive from the FV regime —
  compounders tighter, unprofitable_growth wider, cyclicals on the
  normalized-EPS path — not one flat multiplier for every name.
  Weights unchanged — scenarios vary INPUTS, not the blending contract
- `margin_of_safety` = fv_base/price − 1
- `growth_priced_in_score` 0-100 — composite: gap sign/size,
  compression_drag, MOS. High score = little growth left to prove

### EPS consistency (hard rule — we have scar tissue here)

Never mix GAAP/non-GAAP, fiscal/calendar year, split-adjusted/
unadjusted, or fwd-year vs exit-year EPS in one calculation. The
fwd_eps audit+repair job exists because this bit us before.

### EPS growth ≠ business growth

Track rev growth / NI growth / diluted share count / EPS growth / SBC
alongside — buybacks can manufacture the EPS CAGR the price demands;
the journal keeps all five so the gap is graded on business reality.

### Journal

Mig 212 `growth_priced_in_daily`: (symbol, as_of, price, eps_fwd,
forecast_cagr, required_cagr, implied_growth, implied_growth_status,
expectation_gap, compression_drag, expected_annual_return,
fv_bear/base/bull, valuation_dispersion, mos_pct, score, model_version,
inputs jsonb, missing_inputs, UNIQUE(symbol, as_of)). Daily job
`priced-in` — slot 05:45 UTC weekdays (empty; before the 06:xx batch).

### Endpoint

`GET /symbol/{sym}/priced-in` — latest + 90d history. Renders a card
on /stock: "market needs X% growth · forecast says Y% · compression
cost Z%/yr · FV bear/base/bull".

### Acceptance

- Known-rich name: required_cagr > forecast → gap < 0, high score
- Known-cheap: gap > 0, positive MOS
- Unprofitable name: required_cagr = None + note, score still emits
- Every row: missing_inputs journaled, never zero-filled

---

## Phase 2 — `valuation_decision/` (bands + two-score split)

Consumes Phase 1 + existing quality engines. Advisory only — journaled
decisions, no auto-trading (recovery_verdicts pattern).

### Two scores + thesis integrity (three signals, one matrix)

- `business_quality` 0-100 — earnings-quality + growth-quality +
  flywheel coverage/moat legs, weighted renormalized over what's present
- `priced_in_attractiveness` — Phase-1 score (high = reasonable
  expectations, NOT "lots of growth already priced in")
- `thesis_integrity` — first-class output, evidence families like
  recovery_verdicts: estimate deterioration, backlog/RPO conversion
  break, FCF-conversion decay, dilution/financing risk, moat erosion,
  accounting flags. intact | watch | deteriorating | broken — an
  attractive valuation never overrides broken integrity
- Decision matrix (never a product of scores — a 90×20 and a 20×90 are
  different investments):
  quality ≥60 & attractiveness high → accumulate_on_valid_entry |
  quality ≥60 & medium → hold_wait_pullback | quality ≥60 & low →
  wait_valuation_risk | 40-60 & high → selective_watch |
  <60 & high → value_trap_watch | <60 & low → avoid

### Bands (deterministic, journaled)

- `valuation_dispersion` = (fv_bull − fv_bear)/fv_base — kept separate
  from confidence, MOS and the zones; wide dispersion can be upside,
  downside, or both
- `entry_zone` — price ≤ fv_base × (1 − mos_required);
  `mos_required = clamp(0.15 + f × dispersion, 0.15, 0.30)`,
  dispersion_factor calibrated on the journaled history. Entry is a
  zone, never a point
- `trim_zone` — price ≥ fv_bull → trim signal; ≥ fv_bull × 1.10 →
  exit-core review (subject to concentration/thesis — thresholds, not
  automatic orders)
- `exit` — cheapness alone is NEVER an exit. Three-way split:
  price < fv_bear + fundamentals intact → reassess (often more
  attractive, not less — required CAGR improved with the lower entry);
  price < fv_bear + thesis_integrity deteriorating → thesis_review /
  exit. The reliable exit trigger is thesis invalidation with named
  evidence, not a price level
- `decision` per symbol/day: enter | hold | trim | exit_review |
  avoid — with the band that fired + why

### Journal + surfacing

Mig 213 `valuation_decisions`: (symbol, as_of, business_quality,
priced_in_attractiveness, thesis_integrity, quadrant, band, decision,
decision_reasons jsonb, risk_flags jsonb, price, fv refs, model_version,
missing_inputs). Daily job chained after `priced-in` (05:50).
Surfaces: badge on /stock ("accumulate — quality 72, priced-in 38"),
column on the portfolio page, feeds daily-sheet's expression picker.

---

## Phase 3 — `falsification/` (compounding the journal)

Three fields kept distinct throughout — they answer different questions:
`multiple_compression_risk` (could the multiple normalize),
`compression_drag` (annualized return cost under our exit multiple),
`valuation_extension` (price vs fair value). A stock can carry heavy
drag and still return well if growth outruns it.

- `multiple_compression_alert` — compression_drag ≤ −10%/yr AND price
  within 10% of fv_bull → universal-alerts `PricedIn`
- `expectation_expansion_alert` — the drift signal: price +30% while
  fwd EPS +2% means the market paid a bigger multiple for the same
  earnings. Weekly journaled delta on required_cagr vs forecast —
  valuation expanding faster than the earnings outlook, flagged before
  it breaks
- estimate-revision tracking — flywheel already snapshots; Phase 3
  adds priced-in revision deltas to the weekly learnings post
- **grading — the load-bearing piece.** Every journaled row preserves
  the ORIGINAL assumptions at write time (price, starting EPS/FCF,
  bear/base/bull growth inputs, exit multiples, required/implied CAGR,
  bands, confidence, quality, thesis_integrity, model_version) — never
  overwritten by later revisions, or the engine grades its latest view
  instead of its forecast. Graded at 3/6/12/24mo (a valuation
  horizon, not the signal engines' 5/10/20d): growth forecast vs
  actual EPS, exit-multiple assumption vs realized multiple, FV band
  vs realized price, thesis_integrity vs subsequent fundamentals —
  plus `journal_grades` bucket `growth_priced_in` for the short-horizon
  scoreboard. The journal reproduces every decision from the data
  available at that as_of (inputs jsonb + model_version — the row IS
  the reproducibility record; no separate snapshot registry needed)

## What this deliberately is not

- Not a single target price — bands + scenarios, because FV is a
  distribution
- Not auto-trading — advisory rows; posture/permissions still gate
- Not a new scoring system — it explains what must happen for the
  trade to work, then grades itself on whether it did
