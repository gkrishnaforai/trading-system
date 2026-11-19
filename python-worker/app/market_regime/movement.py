"""Money-movement strip — read-time composition for /morning-regime.

The regime page shows today's label but not the *story*: how long the
regime has run, when it flipped, and where sector money is rotating.
Everything here derives from journaled data — no new fetches:

- regime_clock: consecutive days in the current regime + the date it
  began + the regime it replaced (morning_regime_snapshots walk)
- flips: the last regime transitions with dates (risk_off → neutral
  is a risk-off *ending* — the "when did it start/end" answer)
- sectors: per-ETF relative strength vs SPY over 5d/20d — the
  "where's the money going" board (gainers absorbing, losers shedding)
- smh_ew: latest sector-rotation early-warning row for SMH, when the
  journal has one (leadership-deterioration state)
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Sector set the board ranks — SPDR sectors + the AI-infra proxy the
# book actually trades against. Destinations from sector_rotation_ew
# stay consistent with this set.
_BOARD = ["SMH", "XLK", "XLF", "XLE", "XLV", "XLY", "XLP",
          "XLI", "XLU", "XLRE", "XLB", "XLC"]


def _regime_clock() -> tuple[Optional[dict], list]:
    """Walk recent snapshots: current streak + last flips."""
    from app.database import db
    rows = db.execute_query(
        "SELECT as_of, regime FROM morning_regime_snapshots "
        "ORDER BY as_of DESC LIMIT 45")
    if not rows:
        return None, []
    cur = rows[0]["regime"]
    days, since, prev = 0, rows[0]["as_of"], None
    for r in rows:
        if r["regime"] == cur:
            days += 1
            since = r["as_of"]
        else:
            prev = r["regime"]
            break
    flips = [
        {"as_of": str(a["as_of"]), "from": b["regime"], "to": a["regime"]}
        for a, b in zip(rows, rows[1:])
        if a["regime"] != b["regime"]
    ][:3]
    return {"regime": cur, "since": str(since), "days": days,
            "prev": prev}, flips


def _sector_board() -> list[dict]:
    """Per-ETF 5d/20d relative strength vs SPY — sorted, most money
    flowing in at the top. Read-only from daily_bars (populated by the
    daily refresh jobs; missing symbols drop out honestly)."""
    from app.database import db
    syms = ["SPY"] + _BOARD
    rows = db.execute_query(
        "SELECT symbol, date, close FROM (SELECT symbol, date, close,"
        " row_number() OVER (PARTITION BY symbol ORDER BY date DESC)"
        " rn FROM daily_bars WHERE symbol = ANY(:s)) t WHERE rn <= 21",
        {"s": syms})
    px: dict[str, list[float]] = {}
    for r in rows:
        px.setdefault(r["symbol"], []).append(float(r["close"]))
    spy = px.get("SPY") or []
    spy5 = spy[0] / spy[5] - 1 if len(spy) > 5 else None
    spy20 = spy[0] / spy[20] - 1 if len(spy) > 20 else None
    board = []
    for s in _BOARD:
        c = px.get(s) or []
        if len(c) < 6:
            continue
        r5 = c[0] / c[5] - 1
        r20 = c[0] / c[20] - 1 if len(c) > 20 else None
        board.append({
            "symbol": s, "ret5": round(r5, 4),
            "ret20": round(r20, 4) if r20 is not None else None,
            "vs_spy5": (round(r5 - spy5, 4)
                        if spy5 is not None else None),
            "vs_spy20": (round(r20 - spy20, 4)
                         if spy20 is not None and r20 is not None
                         else None)})
    board.sort(key=lambda b: b["vs_spy5"]
               if b["vs_spy5"] is not None else -9,
               reverse=True)
    return board


def _smh_ew() -> Optional[dict]:
    """Latest leadership-deterioration read for SMH, if the EW journal
    has one (unavailable until the 06:55 job lands mig 210)."""
    try:
        from app.database import db
        rows = db.execute_query(
            "SELECT as_of, risk_score, state, dest_scores"
            " FROM sector_rotation_daily WHERE sector='SMH'"
            " ORDER BY as_of DESC LIMIT 1")
        if rows:
            r = rows[0]
            dests = r.get("dest_scores") or []
            if isinstance(dests, str):
                import json
                dests = json.loads(dests)
            return {"as_of": str(r["as_of"]),
                    "risk": r.get("risk_score"),
                    "state": r.get("state"),
                    "destinations": [d.get("etf") for d in dests[:3]]}
    except Exception:
        pass
    return None


def movement() -> dict[str, Any]:
    """The assembled strip — every leg tolerates its own failure so a
    missing journal never blanks the page."""
    clock, flips = _regime_clock()
    try:
        board = _sector_board()
    except Exception as exc:
        logger.debug("movement: sector board failed: %s", exc)
        board = []
    return {"regime_clock": clock, "flips": flips,
            "sectors": board, "smh_ew": _smh_ew()}
