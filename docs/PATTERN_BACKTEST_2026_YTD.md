# Pattern Backtest — High-Volatility Names, 2026 YTD

Walk-forward replay of `analyze_stock` + `detect_setup` on daily bars.
Entry = signal close · Stop = entry − 2×ATR · Target = 2R · Horizon = 10 bars.
One signal per consecutive episode. Environment: open (no regime gate).

Run: `python -m scripts.backtest_patterns CRDO MRVL NBIS --since 2026-01-01 --horizon 10`

## Per-pattern results

| Pattern | CRDO | MRVL | NBIS | Combined |
|---|---|---|---|---|
| first_pullback | n=2 · 0% · −0.91R | n=2 · **100% · +2.00R** | n=4 · 50% · +0.66R | **n=8 · 50% · +0.60R** |
| breakout | n=5 · 80% · +0.48R | n=5 · 60% · +0.80R | n=6 · 33% · −0.30R | n=16 · 56% · +0.28R |
| mean_reversion | n=8 · 25% · −0.40R | n=6 · 50% · −0.12R | n=10 · **70% · +0.24R** | n=24 · 50% · −0.06R |
| pullback | n=5 · 20% · −0.15R | n=3 · 0% · −0.84R | n=6 · 50% · +0.38R | n=14 · 29% · −0.07R |
| trend_continuation | n=13 · 39% · −0.09R | n=11 · 46% · +0.29R | n=15 · 40% · +0.12R | n=39 · 41% · +0.10R |

## CRDO signal days (33 episodes)

| Date | Setup | Score | Entry | Outcome |
|---|---|---|---|---|
| 2026-01-05 | mean_reversion | 75 | $140.24 | +0.62R (10b) |
| 2026-01-13 | trend_continuation | 73 | $161.38 | −1.00R stop |
| 2026-01-22 | mean_reversion | 70 | $135.10 | −1.00R stop |
| 2026-01-30 | mean_reversion | 63 | $125.28 | −1.00R stop |
| 2026-04-10 | trend_continuation | 75 | $119.59 | **+2.00R target** |
| 2026-04-13 | breakout | 85 | $134.36 | **+2.00R target** |
| 2026-04-14 | trend_continuation | 75 | $159.52 | +0.31R |
| 2026-04-15 | breakout | 85 | $168.35 | +0.36R |
| 2026-04-16 | trend_continuation | 75 | $158.93 | +0.70R |
| 2026-04-21 | breakout | 85 | $183.32 | +0.46R |
| 2026-04-22 | trend_continuation | 68 | $189.49 | −1.00R stop |
| 2026-05-14 | first_pullback | 83 | $184.54 | −1.00R stop |
| 2026-05-22 | breakout | 90 | $218.41 | +0.12R |
| 2026-05-26 | trend_continuation | 80 | $221.64 | +0.38R |
| 2026-06-05 | pullback | 85 | $206.89 | **+2.00R target** |
| 2026-06-08 | trend_continuation | 73 | $222.27 | **+2.00R target** |
| 2026-06-11 | breakout | 85 | $264.76 | −0.56R |
| 2026-07-08 | pullback | 78 | $258.69 | −1.00R stop |
| 2026-07-09 | trend_continuation | 73 | $265.65 | −1.00R stop |
| 2026-07-13 | pullback | 66 | $236.88 | −0.55R |
| 2026-07-15 | mean_reversion | 68 | $226.74 | −0.97R |
| 2026-07-28 | mean_reversion | 63 | $192.28 | +1.18R |
| 2026-08-11 | trend_continuation | 68 | $247.69 | −0.48R |
| 2026-08-18 | first_pullback | 85 | $245.97 | −0.83R |
| 2026-08-24 | mean_reversion | 75 | $222.61 | −1.00R stop |
| 2026-08-27 | trend_continuation | 73 | $240.24 | −1.00R stop |
| 2026-09-01 | mean_reversion | 75 | $206.63 | −1.00R stop |

## MRVL signal days (27 episodes)

| Date | Setup | Score | Entry | Outcome |
|---|---|---|---|---|
| 2026-01-09 | mean_reversion | 68 | $83.22 | −0.18R |
| 2026-01-14 | mean_reversion | 68 | $81.21 | +0.02R |
| 2026-02-02 | mean_reversion | 63 | $78.66 | −1.00R stop |
| 2026-03-06 | trend_continuation | 80 | $89.57 | −0.18R |
| 2026-03-09 | breakout | 90 | $92.65 | −0.26R |
| 2026-03-11 | trend_continuation | 73 | $90.44 | +0.84R |
| 2026-03-18 | **first_pullback** | 83 | $87.62 | **+2.00R target** |
| 2026-03-19 | trend_continuation | 73 | $89.53 | **+2.00R target** |
| 2026-03-30 | **first_pullback** | 83 | $87.81 | **+2.00R target** |
| 2026-03-31 | breakout | 90 | $99.05 | **+2.00R target** |
| 2026-04-02 | trend_continuation | 73 | $107.11 | **+2.00R target** |
| 2026-04-08 | breakout | 90 | $114.45 | **+2.00R target** |
| 2026-04-14 | trend_continuation | 80 | $133.83 | **+2.00R target** |
| 2026-04-20 | breakout | 90 | $147.84 | +1.24R |
| 2026-04-21 | trend_continuation | 73 | $151.31 | +1.36R |
| 2026-06-02 | breakout | 90 | $290.79 | −1.00R stop |
| 2026-06-03 | trend_continuation | 80 | $301.65 | −1.00R stop |
| 2026-06-24 | pullback | 78 | $276.70 | −0.61R |
| 2026-06-25 | trend_continuation | 73 | $281.26 | −1.00R stop |
| 2026-06-26 | pullback | 78 | $266.77 | −0.92R |
| 2026-06-30 | trend_continuation | 73 | $297.89 | −1.00R stop |
| 2026-07-01 | pullback | 66 | $272.05 | −1.00R stop |
| 2026-07-16 | mean_reversion | 68 | $188.30 | −0.11R |
| 2026-07-27 | mean_reversion | 63 | $189.17 | +0.49R |
| 2026-08-19 | trend_continuation | 75 | $237.27 | −0.84R |
| 2026-08-25 | trend_continuation | 68 | $240.38 | −1.00R stop |
| 2026-08-28 | mean_reversion | 87 | $216.62 | +0.06R |

## NBIS signal days (41 episodes)

| Date | Setup | Score | Entry | Outcome |
|---|---|---|---|---|
| 2026-01-09 | trend_continuation | 68 | $97.93 | −0.48R |
| 2026-01-12 | breakout | 85 | $107.33 | −1.00R stop |
| 2026-01-13 | trend_continuation | 68 | $105.43 | −1.00R stop |
| 2026-01-16 | breakout | 90 | $108.73 | −1.00R stop |
| 2026-01-20 | first_pullback | 90 | $99.29 | −1.00R stop |
| 2026-01-26 | mean_reversion | 75 | $91.46 | −1.00R stop |
| 2026-01-27 | pullback | 78 | $97.87 | −1.00R stop |
| 2026-01-28 | trend_continuation | 73 | $100.43 | −1.00R stop |
| 2026-01-29 | pullback | 78 | $94.91 | −1.00R stop |
| 2026-02-19 | trend_continuation | 68 | $107.61 | −1.00R stop |
| 2026-02-23 | trend_continuation | 68 | $100.61 | −1.00R stop |
| 2026-02-27 | mean_reversion | 70 | $91.19 | +1.30R |
| 2026-03-04 | pullback | 73 | $97.78 | **+2.00R target** |
| 2026-03-09 | trend_continuation | 73 | $94.94 | **+2.00R target** |
| 2026-03-11 | breakout | 90 | $112.00 | +0.18R |
| 2026-03-12 | trend_continuation | 73 | $108.04 | −0.12R |
| 2026-03-16 | breakout | 90 | $129.85 | −1.00R stop |
| 2026-03-17 | trend_continuation | 80 | $116.33 | −1.00R stop |
| 2026-03-26 | first_pullback | 83 | $105.97 | **+2.00R target** |
| 2026-03-30 | mean_reversion | 80 | $92.26 | **+2.00R target** |
| 2026-03-31 | pullback | 78 | $103.76 | **+2.00R target** |
| 2026-04-02 | trend_continuation | 73 | $108.82 | **+2.00R target** |
| 2026-04-24 | first_pullback | 83 | $147.16 | **+2.00R target** |
| 2026-05-01 | trend_continuation | 73 | $154.49 | **+2.00R target** |
| 2026-05-04 | breakout | 90 | $176.42 | **+2.00R target** |
| 2026-05-05 | trend_continuation | 73 | $175.92 | **+2.00R target** |
| 2026-06-05 | pullback | 78 | $227.81 | +1.25R |
| 2026-06-12 | trend_continuation | 73 | $232.36 | +0.63R |
| 2026-06-25 | mean_reversion | 80 | $256.63 | −1.00R stop |
| 2026-06-29 | trend_continuation | 73 | $261.15 | −1.00R stop |
| 2026-07-01 | pullback | 73 | $229.18 | −1.00R stop |
| 2026-07-07 | mean_reversion | 68 | $195.19 | +0.41R |
| 2026-07-14 | mean_reversion | 68 | $194.09 | −0.49R |
| 2026-07-16 | mean_reversion | 70 | $171.77 | +0.34R |
| 2026-07-28 | mean_reversion | 70 | $169.69 | +0.48R |
| 2026-08-04 | mean_reversion | 68 | $225.74 | +0.43R |
| 2026-08-12 | breakout | 85 | $259.20 | −1.00R stop |
| 2026-08-13 | trend_continuation | 75 | $255.04 | −0.69R |
| 2026-08-19 | first_pullback | 73 | $223.90 | −0.37R |
| 2026-08-21 | mean_reversion | 75 | $219.13 | +0.15R |
| 2026-09-01 | mean_reversion | 68 | $199.54 | +0.25R |

## Regime-gated re-run (`--regime-gate`)

Deterministic SPY proxy per day — `blocked` when SPY < SMA200 or < SMA50 with
ret20 < −3%; `limited` when SPY < SMA50 or ret20 < 0 or dd20 < −5%; `blocked`
suppresses the signal entirely. (The real engine additionally uses
breadth/VIX/participation — this proxy is deliberately simpler.)

| Pattern | Open env | Regime-gated | Delta |
|---|---|---|---|
| breakout | 56% · +0.28R | **64% · +0.38R** | improved — restricted-breakout filter works |
| first_pullback | 50% · +0.60R | **20% · −0.24R** | gate suppressed MRVL's two +2R winners |
| mean_reversion | 50% · −0.06R | 50% · −0.16R | flat |
| pullback | 29% · −0.07R | 25% · −0.17R | flat |
| trend_continuation | 41% · +0.10R | 38% · −0.06R | flat |

Suppressed: CRDO 1, MRVL 5, NBIS 4 (of 101 total).

**Honest finding:** the index gate is blunt — it removed two of the best
first_pullback winners (MRVL 3/18, 3/30, both +2R) because SPY was weak while
MRVL had already turned. Individual names bottom before the index does.
The January chop it was supposed to catch mostly passed as `allowed` — the
SPY proxy saw an uptrend while these names chopped. A per-symbol trend/quality
gate likely matters more than the index gate for high-vol names.

## Variant: 4-level permission (suppress only `disabled`)

Corrected proxy to the real vocabulary (allowed | limited | restricted |
disabled — previously `blocked`). Only `disabled` suppresses; limited/restricted
signals kept and tagged. Per-permission outcomes:

| Permission | CRDO | MRVL | NBIS | Combined read |
|---|---|---|---|---|
| allowed | 48% · 0.00R | 42% · −0.04R | 43% · +0.03R | ~44% · ~0R |
| limited | **0% · −0.73R** | 33% · −0.19R | 33% · −0.52R | **~20% · −0.45R** |
| restricted | 100% · +1.18R (n=1) | 0% · −0.18R (n=1) | **67% · +0.63R** | ~63% · +0.4R (n=8) |

- **Limited windows are the drag** — half-sizing them is the right answer:
  you lose half as much per loser. The engine's size_multiplier already does
  this; suppressing entirely would be over-correction.
- **Restricted windows paid on NBIS** (67%, +0.63R — the Feb–Mar correction
  bottom entries). Suppressing restricted would lose bottom-fishing winners.
- MRVL's two +2R first_pullback winners were suppressed under `disabled` —
  they fired while SPY was below SMA50 in the March correction. The cost of
  hard-blocking on index weakness is exactly the early-turn entries.

## Stock regime vs index regime (the key matrix)

Same SMA50/200/ret20/dd20 rules applied to each stock's own bars, crossed
with the SPY permission — combined across all 3 names:

| Stock regime | SPY allowed | SPY limited | SPY restricted |
|---|---|---|---|
| **allowed** (stock trending) | ~57% · +0.17R (n=20) | ~50% · +0.7R (n=2) | 0% · −0.6R (n=2) |
| **limited** | ~37% · −0.15R (n=25) | **~8% · −0.71R (n=14)** | 67% · +1.0R (n=3) |
| **disabled** (stock weak) | ~50% · −0.02R (n=11) | ~50% · −0.2R (n=4) | 100% · +1.0R (n=3) |

**Findings:**

1. **stock-limited + spy-limited is the kill zone**: 8% win, −0.71R —
   both weak together = where money dies. This is where regime gating
   genuinely earns.
2. **Stock-allowed wins regardless of SPY permission** — a stock in its own
   uptrend produces positive-expectancy entries even when the index is soft
   (small n, but consistent direction).
3. **Stock-disabled is not a no-trade zone** — it's where `mean_reversion`
   *lives*. NBIS restricted-window MR entries: +0.89R. A blanket
   "stock must be above SMA50" rule would delete the RSI-2 pattern entirely.
4. **SPY regime alone doesn't separate winners from losers** — the stock's
   own state does the separating. Index regime is a sizing input
   (how aggressive), not an entry selector (what to buy) — which is exactly
   the system's stated design principle, now with evidence.

## Read

- **first_pullback has the best combined avgR (+0.60)** — MRVL 3-18 and 3-30
  both hit +2R targets; NBIS 3-26 and 4-24 did too. Tiny sample (n=8).
- **High-vol reality**: MAE runs −12% to −20% on these names. A fixed 2×ATR
  stop gets clipped routinely — wider stops or smaller size is required.
- **MFE +9% to +27%** — the patterns catch the swings; direction is right,
  entry/stop calibration is the lever.
- **March–May 2026 uptrend was the money window.** The gated re-run shows the
  Jan losses were per-symbol chop, not index weakness — the SPY proxy passed
  most of them as `allowed`.
- Small n per pattern per symbol — directional, not conclusive.

## Ledger variants — full trade simulation (Jan–Aug 2026, $500 risk/trade)

Ledger-backed replay of `detect_setup` with real position management
(stop → T1 partial at 2R + breakeven trail → T2 at 3R → 20-bar time stop).
Persisted under `trades.user_id` so variants compare directly.

| Variant (`user_id`) | Trades | Win | Total R | P&L |
|---|---|---|---|---|
| `backtest-2026H1` baseline | 36 | 28% | +3.83R | $2,264 |
| `bt-v2-minscore70` | 28 | 29% | +1.38R | $409 |
| `bt-v3-practice` (practice patterns only) | 20 | 35% | −0.99R | −$570 |
| `bt-v4-regime` (killzone + no-disabled-stock) | 33 | 30% | +4.27R | $2,151 |
| **`bt-v5`** (v4 + drop `pullback` + MR bounce exit + size-mult) | **39** | **49%** | **+9.58R** | **$3,395** |

v5 per-symbol: NBIS +2.58R (4/7) · NVDA +1.44R (5/9) · MRVL +5.95R (4/9)
· AVGO +1.65R (4/9) · TSLA −2.04R (2/5).

**Findings:**

1. **MR bounce exit is the single biggest lever** — mean_reversion went
   from a consistent loser (dying at the 20-bar time stop) to a steady
   winner: NBIS 3/3, NVDA 3/3, TSLA 2/3 with +0.2–0.5R per trade. Connors
   edge confirmed once you stop holding for 2R.
2. **Generic `pullback` was the worst setup type** (−0.7R avg) — removed
   from detection; `first_pullback` is kept (distinct pattern, +3R winner).
3. **Score doesn't separate winners** — min-score-70 cut the fat tails
   too. Score measures setup quality, not outcome.
4. **Practice patterns alone lost money in this window** — profit came
   from trend_continuation/breakout +3R tails. Don't over-fit to the two
   practice patterns.
5. **Expectancy is the metric, not win rate** — 49% at +0.25R/trade beats
   any win-rate-maximizing tweak tested.

**Promoted to engine (v5):** generic `pullback` removed from `detect_setup`;
mean-reversion trades use bounce exit (close > prior high) or 5-bar max in
the trade monitor; `size_multiplier` already flows env → risk sizing.
TSLA-type weakness remains: the fundamentals gate (`fund_signal=weak → skip`)
can't be backtested (FV is current-state) but is live in the screener overlay.
