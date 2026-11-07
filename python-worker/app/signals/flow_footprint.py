"""Flow footprint — EOD institutional-signature detector.

Daily bars only, book symbols only. The spec it answers:

  zvol   log-volume z-score vs the trailing 15d median/MAD —
         how anomalous today's volume is (log because volume is
         right-skewed; MAD because z on raw volume lies)
  clv    close location value — Chaikin's: where the close sat in
         the day's range, +1 ask-swept / -1 bid-smashed
  signal a day qualifies when |clv| >= .75 AND zvol >= 2.0
  streak net qualifying direction over the last 10 sessions —
         a single big day is never 'accumulation'

Honesty contract:
- 'institutional footprint' is inferred, never measured — the label
  is high-conviction directional volume. No borrow/OI data means a
  short squeeze looks identical to accumulation.
- event days (earnings, index rebalance, quad witching) are
  annotated 'event' and EXCLUDED from streaks — the highest-volume
  days are exactly the ones the footprint means least.
- footprint adjusts posture (tape leg, entry sizing, badges) —
  never overrides gates or issues a bare BUY/SELL.
"""
from __future__ import annotations

import json
import logging
import math
from datetime import date
from typing import Any, Optional

logger = logging.getLogger(__name__)

LOOKBACK = 15          # baseline window, excluding the signal day
STREAK_WIN = 10        # sessions the streak counts over
Z_MIN = 2.0            # volume anomaly threshold
CLV_MIN = 0.75         # directional-close threshold
STREAK_MIN = 3         # minimum qualifying days for a signature
MIN_BARS = 22          # LOOKBACK + STREAK_WIN + margin


def _f(v) -> Optional[float]:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _mad(xs: list[float]) -> float:
    m = sorted(xs)[len(xs) // 2]
    return sorted(abs(x - m) for x in xs)[len(xs) // 2] or 1e-9


def _clv(b: dict) -> Optional[float]:
    h, l, c = _f(b.get("high")), _f(b.get("low")), _f(b.get("close"))
    if h is None or l is None or c is None or h <= l:
        return None
    return ((c - l) - (h - c)) / (h - l)


def _bars(sym: str, n: int = 45) -> list[dict]:
    from app.database import db
    try:
        rows = db.execute_query(
            "SELECT date, open, high, low, close, volume FROM"
            " (SELECT date, open, high, low, close, volume,"
            "  ROW_NUMBER() OVER (ORDER BY date DESC) rn"
            "  FROM daily_bars WHERE symbol=:s) t"
            " WHERE rn<=:n ORDER BY rn DESC", {"s": sym, "n": n})
        return [dict(r) for r in rows]
    except Exception as e:
        logger.debug("flow bars %s: %s", sym, e)
        return []


def _event_days(sym: str, days: set) -> set:
    """Days where the footprint means least — earnings prints and
    earnings-day moves. earnings_watch journals event_date."""
    from app.database import db
    try:
        rows = db.execute_query(
            "SELECT DISTINCT earnings_date FROM earnings_watch"
            " WHERE symbol=:s AND earnings_date >= :d",
            {"s": sym, "d": min(days) if days else date.today()})
        return {r["event_date"] for r in rows
                if r.get("earnings_date")}
    except Exception:
        return set()


def compute(sym: str) -> dict[str, Any]:
    """One symbol → footprint card: today's zvol/clv, streak, posture."""
    bars = _bars(sym)
    if len(bars) < MIN_BARS:
        return {"symbol": sym, "footprint": "none",
                "note": "insufficient history"}
    win = bars[-STREAK_WIN:]
    ev = _event_days(sym, {b["date"] for b in win})
    days = []
    for i, b in enumerate(win):
        base = [x for x in bars[:len(bars) - STREAK_WIN + i][-LOOKBACK:]
                if _f(x.get("volume"))]
        if len(base) < LOOKBACK - 2 or not _f(b.get("volume")):
            continue
        lv = [math.log(max(float(x["volume"]), 1)) for x in base]
        med = sorted(lv)[len(lv) // 2]
        mad = _mad(lv)
        zvol = (math.log(max(float(b["volume"]), 1)) - med) / (1.4826 * mad)
        clv = _clv(b)
        is_ev = b["date"] in ev
        sig = None
        if not is_ev and zvol >= Z_MIN and clv is not None:
            sig = "acc" if clv >= CLV_MIN else (
                "dist" if clv <= -CLV_MIN else None)
        days.append({"date": str(b["date"]), "zvol": round(zvol, 2),
                     "clv": round(clv, 2) if clv is not None else None,
                     "sig": sig, "event": is_ev})
    acc = sum(1 for d in days if d["sig"] == "acc")
    dist = sum(1 for d in days if d["sig"] == "dist")
    streak_dir = acc - dist
    footprint = ("accumulating" if streak_dir >= STREAK_MIN
                 else "distributing" if streak_dir <= -STREAK_MIN
                 else "none")
    last = days[-1] if days else {}
    return {"symbol": sym, "footprint": footprint,
            "streak": streak_dir, "acc_days": acc, "dist_days": dist,
            "today": last,
            "signal_days": [d for d in days if d["sig"]],
            "window": STREAK_WIN}


def ensure_table() -> None:
    from app.database import db
    db.execute_update(
        "CREATE TABLE IF NOT EXISTS symbol_flow ("
        " symbol TEXT NOT NULL, as_of DATE NOT NULL,"
        " zvol NUMERIC, clv NUMERIC, sig TEXT, event BOOLEAN,"
        " footprint TEXT, streak INT, payload JSONB,"
        " created_at TIMESTAMPTZ NOT NULL DEFAULT now(),"
        " PRIMARY KEY (symbol, as_of))")


def run(symbols: list[str]) -> dict[str, Any]:
    """Nightly job — compute + journal every book symbol."""
    from app.database import db
    ensure_table()
    n = 0
    out: dict[str, Any] = {}
    for sym in symbols:
        try:
            c = compute(sym)
            last = c.get("today") or {}
            db.execute_update(
                "INSERT INTO symbol_flow"
                " (symbol, as_of, zvol, clv, sig, event,"
                "  footprint, streak, payload)"
                " VALUES (:s,:d,:z,:cl,:sg,:ev,:fp,:st,CAST(:p AS jsonb))"
                " ON CONFLICT (symbol,as_of) DO UPDATE SET"
                " zvol=EXCLUDED.zvol, clv=EXCLUDED.clv,"
                " sig=EXCLUDED.sig, event=EXCLUDED.event,"
                " footprint=EXCLUDED.footprint,"
                " streak=EXCLUDED.streak, payload=EXCLUDED.payload",
                {"s": sym, "d": date.today(),
                 "z": last.get("zvol"), "cl": last.get("clv"),
                 "sg": last.get("sig"), "ev": last.get("event"),
                 "fp": c["footprint"], "st": c["streak"],
                 "p": json.dumps(c, default=str)})
            out[sym] = {"footprint": c["footprint"], "streak": c["streak"]}
            n += 1
        except Exception as e:
            logger.debug("flow %s: %s", sym, e)
    return {"scored": n, "footprints": out}


def read(sym: str) -> Optional[dict[str, Any]]:
    from app.database import db
    try:
        rows = db.execute_query(
            "SELECT payload FROM symbol_flow"
            " WHERE symbol=:s ORDER BY as_of DESC LIMIT 1", {"s": sym})
        if not rows:
            return None
        p = rows[0].get("payload")
        return json.loads(p) if isinstance(p, str) else p
    except Exception:
        return None


def read_map() -> dict[str, dict]:
    """symbol → {footprint, streak} for the screener read."""
    from app.database import db
    try:
        rows = db.execute_query(
            "SELECT DISTINCT ON (symbol) symbol, footprint, streak"
            " FROM symbol_flow ORDER BY symbol, as_of DESC")
        return {r["symbol"]: {"footprint": r["footprint"],
                              "streak": r["streak"]} for r in rows}
    except Exception:
        return {}
