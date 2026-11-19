# Sector Rotation Early Warning — Phase-1 spec (read-only journal)

The early-warning layer for leadership deterioration — legs
journaled before any composite acts. Phase 1 answers "is the leader
getting weaker and where is strength building?" from stored bars
only. ETF flow confirmation is a declared leg, journaled
`unavailable` until a real source exists — never proxied, never zero.

## 1. Module contract

```python
# app/signals/sector_rotation_ew.py

def evaluate(source_etf: str, as_of: date,
             destinations: Optional[list[str]] = None) -> dict
    """Point-in-time: only bars with date <= as_of — the replay
    harness and the daily job share this path, so backtests can't
    leak forward data."""

def run(sources: Optional[list[str]] = None) -> dict
    """Daily journal over watched leaders (pilot: SMH only)."""

def replay(source_etf: str, start: date, end: date) -> list[dict]
    """evaluate() for every trading day in [start,end] — the
    June-2026 acceptance harness."""
```

## 2. Legs (all from `daily_bars` — close, high, low, volume)

| Leg | Weight | Inputs |
|---|---|---|
| `pairwise_rs` | 30% | RS ratios source/{QQQ,SPY,IWM} + source/each destination; deterioration = 5/10/20d RS deltas rolling negative (absolute price can still be rising — that's the tell) |
| `constituent_breadth` | 25% | % of `SECTORS[sector].theme` names above 20d SMA, above 50d SMA, positive ret5/ret20, net new-20d-highs − lows. **Labeled `tracked_subset` — the ~10-name lists, not the full index** |
| `distribution` | 20% | down-vol/up-vol ratio (5d, 10d — flag >1.2), mean close-location, OBV slope sign |
| `etf_flows` | 15% | **unavailable Phase 1** → missing, excluded from renormalization |
| `destination_leadership` | 10% | best destination's (RS-vs-SPY delta + breadth delta) |

Missing-leg renormalization: weights renormalize over *available*
legs (the metals `score()` pattern); each leg carries
`{score, available, inputs, missing}` — never counted as zero.

## 3. Two scores, not one

```
rotation_risk_score         0–100 — is the leader losing it?
destination_attractiveness  per destination — RS gain + breadth
                            gain (flow confirm reserved for Phase 2)
```

States (advisory, journaled — no actions in Phase 1):

```
score <25      healthy
25–39          early_deterioration      monitor
40–54          rotation_developing      reduce new adds
55–69          rotation_probable        selective trims
70–84          rotation_confirmed       **requires flow leg —
                                         unreachable until Phase 2**
85+            severe_distribution      **same**
```

Flow-dependent states stay structurally unreachable while the leg
is missing — a score can't launder a confirmation it never saw.
`flow_status`: `unavailable|pending|confirmed|absent` journaled
per row so Phase 2 fills without schema change.

## 4. Destination leaderboard (not a matrix)

`DESTINATIONS = 11 SPDR + themes (IGV XBI KRE ITA ARKK TAN XRT)
+ IWM`. For each: `{etf, rs_delta_5d/20d vs SPY, breadth_delta,
attractiveness_score}` sorted desc. The answer is a rank list —
money can go to cash; the leaderboard reports who leads without
claiming a pairwise transfer.

## 5. Journal — `sector_rotation_daily` (mig 210)

```sql
sector            TEXT NOT NULL,          -- 'SMH' ...
as_of             DATE NOT NULL,
state             TEXT NOT NULL,
risk_score        NUMERIC,                -- legs renormalized
dest_scores       JSONB,                  -- leaderboard (top 5)
legs              JSONB,                  -- per-leg score+inputs+missing
flow_status       TEXT,                   -- unavailable|pending|...
breadth_coverage  NUMERIC,                -- tracked names with data /
                                          --   tracked names expected
missing_inputs    JSONB,
detail            JSONB,
created_at        TIMESTAMPTZ DEFAULT now(),
PRIMARY KEY (sector, as_of)
```

`breadth_coverage` names the tracked-subset caveat in every row.

## 6. June-2026 acceptance test — `replay("SMH", 2026-05-15, 2026-06-30)`

| Checkpoint | Assertion |
|---|---|
| breadth_break < price_break | constituent % above-20d-SMA rolls below ~50% *before* SMH ret20 goes negative — the win condition |
| leaderboard by ~Jun 12 | XLI in top-3 destinations (the user's flow data says Industrials, not Energy — the engine must name the real destination) |
| SMH/QQQ RS delta negative before SMH absolute | RS roll-over precedes price roll-over |
| flow_status = 'unavailable' all rows | no confirmation claims the engine couldn't see |
| quiet-window false alarms (Mar 2026) | zero days in rotation_probable+ — if it cries wolf in a normal tape, thresholds are wrong |

Second replay window for falsification: a known *false* scare —
the engine must show early_deterioration without confirming.

## 7. Files

| File | Change |
|---|---|
| `signals/sector_rotation_ew.py` | legs + scores + journal |
| `supabase/migrations/210_sector_rotation.sql` | journal |
| `board_api.py` | `/sector-rotation/{etf}` + `sector-rotation` job (daily 06:55) |
| `market_regime/morning.py` | surface latest risk score + top destination in the regime call card |
| `tests/test_sector_rotation_ew.py` | leg math, missing-leg renormalization, hysteresis-free demotion, replay determinism |
| `python-worker/scripts/replay_june2026.py` | the acceptance harness + assertion report |

Non-negotiables carried from review: tracked-subset breadth
labeled everywhere, missing flow never scores as zero, leaderboard
not matrix, legs before composites, replay and daily share one code
path.
