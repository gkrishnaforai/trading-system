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
- `required_cagr` — solve g in
  `price = eps_fwd × (1+g)^n × pe_exit / (1+r)^n`
  with n=3y, r=10% required return, pe_exit = the regime's normalized
  multiple (from `_get_regime_default_weights` universe — same honest
  normal, not current PE)
- `implied_growth` — reverse DCF: solve g so a 2-stage DCF (FCF base,
  WACC, terminal 2.5%) reproduces price. Bisection, 60 iters,
  deterministic. None when FCF ≤ 0 (burning names get the
  revenue-path note, not a fake number)
- `expectation_gap` = forecast_cagr − required_cagr (pp)
- `compression_drag` — annualized return impact of multiple
  normalization: `(pe_normal/pe_now)^(1/n) − 1`
- `fv_bear / fv_base / fv_bull` — the existing blend re-run under
  scenario inputs: bear = low-growth (forecast × 0.6) + low multiple
  (normalized × 0.8); bull = forecast × 1.4 + normalized × 1.2;
  base = unchanged blend. Weights unchanged — scenarios vary INPUTS,
  not the blending contract
- `margin_of_safety` = fv_base/price − 1
- `growth_priced_in_score` 0-100 — composite: gap sign/size,
  compression_drag, MOS. High score = little growth left to prove

### Journal

Mig 212 `growth_priced_in_daily`: (symbol, as_of, price, eps_fwd,
forecast_cagr, required_cagr, implied_growth, expectation_gap,
compression_drag, fv_bear/base/bull, mos_pct, score, inputs jsonb,
missing_inputs, UNIQUE(symbol, as_of)). Daily job `priced-in` — slot
05:45 UTC weekdays (empty; before the 06:xx batch).

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

### Two scores

- `business_quality` 0-100 — earnings-quality + growth-quality +
  flywheel coverage/moat legs, weighted renormalized over what's present
- `priced_in` — Phase-1 score
- Quadrant: accumulate (quality ≥60 & priced_in ≤40) /
  wait_for_pullback (≥60 & >40) / value_trap_watch (<60 & ≤40) /
  avoid (<60 & >40)

### Bands (deterministic, journaled)

- `entry_zone` — price ≤ fv_base × (1 − mos_required); mos_required
  scales with FV dispersion: 15% (tight) → 30% (dispersed). Entry is a
  zone, never a point
- `trim_zone` — price ≥ fv_bull → trim; ≥ fv_bull × 1.10 → exit core
- `exit_zone` — price < fv_bear AND expectation_gap < 0 → thesis-
  broken exit. Price < fv_bear alone is NOT an exit — could be deep
  value; the gap flip is what kills the thesis
- `decision` per symbol/day: enter | hold | trim | exit_review |
  avoid — with the band that fired + why

### Journal + surfacing

Mig 213 `valuation_decisions`: (symbol, as_of, business_quality,
priced_in, quadrant, band, decision, price, fv refs, missing_inputs).
Daily job chained after `priced-in` (05:50). Surfaces: badge on
/stock ("accumulate — quality 72, priced-in 38"), column on the
portfolio page, feeds daily-sheet's expression picker.

---

## Phase 3 — tracking + alerts (compounding the journal)

- `multiple_compression_alert` — fires when compression_drag ≤ −10%/yr
  AND price within 10% of fv_bull → universal-alerts `PricedIn`
- `required_cagr drift` — weekly delta journaled; a rising required
  CAGR while forecast stalls = quiet multiple expansion, alert before
  it breaks
- estimate-revision tracking — flywheel already snapshots; Phase 3
  adds priced-in revision deltas to the weekly learnings post
- grading — `journal_grades` bucket `growth_priced_in` + quadrant:
  forward returns after each decision state → the 5/10/20d scoreboard
  grades whether bands predicted (spec's own falsification loop)

## What this deliberately is not

- Not a single target price — bands + scenarios, because FV is a
  distribution
- Not auto-trading — advisory rows; posture/permissions still gate
- Not a new scoring system — it explains what must happen for the
  trade to work, then grades itself on whether it did
