# Recovery Verdict — Phase-1 spec (read-only composition layer)

The composition layer that reconciles what six engines see
independently into one journaled answer per stock: **current state,
what must happen next, what invalidates it, and where the engines
disagree.** Phase 1 is read-only — it explains, never instructs.

## 1. Module contract

```python
# app/signals/recovery_verdict.py

def build_recovery_verdict(
    ticker: str,
    as_of: datetime,
    regime:     RegimeSnapshot,        # market_regime (transition store)
    selloff:    SelloffSnapshot,       # selloff_candidates row or live eval
    tape:       TapeSnapshot,          # tape_diagnosis attribution
    intraday:   IntradaySnapshot,      # latest intraday_recovery_evals rows
    permission: PermissionSnapshot,    # market_permissions
    fundamental: FundamentalSnapshot,  # thesis_health + guidance/flywheel
    prev_state: Optional[str] = None,  # last journaled state for hysteresis
) -> RecoveryVerdict
```

**Input rules:**
- Snapshots are read from journals wherever a journal exists
  (`transition_store`, `intraday_recovery_evals`, `selloff_candidates`,
  `symbol_thesis`, `market_permissions`). Live compute is wrapped
  behind the same snapshot dataclass — callers never see the
  difference; tests inject historical snapshots.
- Every snapshot carries `{available: bool, as_of, source_ref}` —
  unavailable ≠ negative. `missing_inputs` lists them in the verdict.
- The orchestrator never reaches into engine internals; it consumes
  their persisted output only.

## 2. Journal schema — `recovery_verdicts` (mig 206)

```sql
symbol          TEXT NOT NULL,
as_of           DATE NOT NULL,
engine_version  TEXT NOT NULL,         -- 'recovery_verdict_v1'
state           TEXT NOT NULL,         -- state machine (below)
prev_state      TEXT,                  -- NULL on coverage_start
state_changed   BOOLEAN NOT NULL,
transition_reason TEXT,                -- human-readable why
event_type      TEXT,                  -- selloff class or NULL
market          JSONB,                 -- regime, dip_char, fragility,
                                       -- stress_direction
stock           JSONB,                 -- attribution split, peer RS
recovery        JSONB,                 -- daily stage flags + intraday
decision        TEXT,                  -- WATCH|STARTER|ADD|HOLD|TRIM|
                                       -- AVOID|EXIT  (advisory only)
decision_confidence TEXT,              -- provisional|normal|low
gates           JSONB,                 -- {name: passed} each hard gate
conflicts       JSONB,                 -- [{layer_a, layer_b, note}]
required_confirmation JSONB,
invalidation_conditions  JSONB,
evidence_refs   JSONB,                 -- [{engine, row_ref, as_of}]
missing_inputs  JSONB,                 -- [engine names]
detail          JSONB,
created_at      TIMESTAMPTZ DEFAULT now(),
PRIMARY KEY (symbol, as_of, engine_version)
```

`state_changed` + `transition_reason` make the COHR Nov 5–17 replay
a pure journal read — no reconstruction needed.

## 3. State machine

```
NORMAL ──selloff event──> EXHAUSTION ──selling fades, lows hold──> STABILIZATION
STABILIZATION ──daily confirm (hold low, reclaim avg, RS+)──> RECOVERY
STABILIZATION ──bounce then pullback holds──> RETEST ──holds──> RECOVERY
any ──thesis deteriorates/broken──> STRUCTURAL_IMPAIRMENT
EXHAUSTION/STABILIZATION ──new selling wave──> back one stage
RECOVERY/RETEST ──momentum lost──> STABILIZATION
STABILIZATION ~10 sessions no progress──> decay to NORMAL-watch
STRUCTURAL_IMPAIRMENT exits when thesis clears deteriorating (NOT
full repair — asymmetric: hard to enter RECOVERY, easy to fall back)
```

Transition discipline (same hysteresis family as thesis broken→review):
- Promotion requires ≥2 sessions of confirming evidence UNLESS a
  defined exceptional event (capitulation bar + next-day reclaim).
- Demotion fires on one session — protecting capital beats elegance.
- Every transition stores `transition_reason` with the evidence rows
  that triggered it.

## 4. Evidence families — the double-counting rule

Same mechanism as `derive_confirmations`' family rollup, applied
cross-engine. One underlying observation = one vote:

| Family | Feeds (don't count twice) |
|---|---|
| volatility_stress | VIX in regime, selloff class, permissions |
| breadth | regime breadth, selloff dislocation, market gate |
| relative_strength | tape attribution, intraday RS leg, peer RS |
| volume_exhaustion | selloff volume spike, exhaustion flag, intraday volume |
| thesis | fundamental gate, attribution idiosyncratic leg |

A family fires once regardless of how many engines observe it.
`conflicts` records family-vs-family disagreement (e.g.,
`volume_exhaustion` firing while `volatility_stress` still firing).

## 5. Hard gates (advisory layer in Phase 1, journaled)

- `thesis broken/deteriorating` → STRUCTURAL_IMPAIRMENT state, gate fails
- `market liquidation active` (dip_character=broad_deleveraging
  AND stress_direction worsening) → caps decision at WATCH
- `volatility_too_high` — ATR% > 95th pctl of own 1y → flags, does
  not silently permit (Phase-2 input to sizing)
- `earnings within window` — binary-event gate (reuse earnings_watch)
- Missing fundamental snapshot → `missing_inputs`, decision capped
  at provisional WATCH — absent evidence is not evidence

## 6. Phase-2 math contracts (declared now, built later)

- `atr_pct = ATR14 / close`; `atr_pctl` = percentile vs own 1y
- `vol_adj = min(1.0, f(atr_pctl))` — **one-sided only**, never
  scales size up. `size = regime_multiplier × vol_adj`, then capped
  by portfolio correlated-exposure (book_risk).
- `peer_rs_20 = r_stock20 − r_peer_basket20` + red-day resilience
  (extend relative_strength down_cap/up_cap to peer basket;
  peer sets hand-seeded for pilot, not provider lists).

## 7. Pilot universe (20 names)

Book + watchlist volatile names where selloff dynamics matter:
COHR CRDO VRT ALAB NBIS IREN INTC MU NVDA AMD AVGO UBER SE UPST
NOW ZS NET APLD UAL + one defensive anchor (PFE or PEP) as the
negative control — its verdict should almost always say NORMAL.

## 8. Acceptance test — the COHR replay

For each trading day Nov 5–17, read the journal for that as_of and
assert the sequence is *reconstructable*:
Nov 5 → EXHAUSTION (capitulation-volume event); Nov 6–9 → rebound
attempt noted, not yet promoted (insufficient confirmation);
Nov 10–11 → STABILIZATION with conflicts recorded;
Nov 12–17 → RETEST or STABILIZATION with required_confirmation
listing the same checks a human would name.
No day may show a state the evidence for that as_of didn't support —
that IS the test of point-in-time integrity.

## 9. Phase-1 file list

| File | Change |
|---|---|
| `signals/recovery_verdict.py` | orchestrator + state machine |
| `signals/recovery_snapshots.py` | typed snapshot dataclasses + readers |
| `supabase/migrations/206_recovery_verdicts.sql` | journal |
| `board_api.py` | `/symbol/{sym}/recovery-verdict` + `recovery-watch` job |
| `frontend` | `RecoveryCard` under health card on /stock |
| `tests/test_recovery_verdict.py` | state transitions, conflicts, gates, missing-inputs semantics |

Non-negotiables carried from the design review: one-sided vol sizing,
evidence-family rollup, conflicts journaled not averaged.
