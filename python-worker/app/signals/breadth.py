"""Universe breadth internals — our own transition-score evidence.

The regime engine's breadth input rides on provider data; this computes
the same internals from canonical daily_bars — zero fetches:

    pct_above_50   % of universe above its 50dma        — participation
    highs_20d      % at a 20d high                     — expansion
    lows_20d       % at a 20d low                      — contraction
    adv_5d         % up over the last 5 sessions       — direction
    hl_confirmed   % of universe with confirmed higher lows — our own
                   structure metric: healing breadth

Read of the tape: a correction with pct_above_50 climbing toward 60+
while the transition score is <55 is the early-repair tell; <25 is a
tape to stay defensive on regardless of what the index prints.
"""
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def universe_internals() -> dict[str, Any]:
    from app.database import db
    rows = db.execute_query(
        """
        WITH last60 AS (
            SELECT symbol, close, high, low, date,
                   ROW_NUMBER() OVER (PARTITION BY symbol
                                    ORDER BY date DESC) rn
            FROM daily_bars
            WHERE date > (SELECT max(date) FROM daily_bars) - 95)
        , agg AS (
            SELECT symbol,
                   MAX(close) FILTER (WHERE rn = 1)                    AS px,
                   AVG(close) FILTER (WHERE rn <= 50)                  AS sma50,
                   MAX(high)  FILTER (WHERE rn <= 20 AND rn > 1)       AS hi20,
                   MIN(low)   FILTER (WHERE rn <= 20 AND rn > 1)       AS lo20,
                   MAX(close) FILTER (WHERE rn = 6)                    AS px5
            FROM last60 GROUP BY symbol)
        SELECT a.symbol,
               (a.px > a.sma50)                                   AS above50,
               (a.px >= a.hi20)                                  AS at_20h,
               (a.px <= a.lo20)                                  AS at_20l,
               (a.px > a.px5)                                    AS up_5d,
               (s.momentum_detail->'swing'->>'phase')            AS sw
        FROM agg a LEFT JOIN stocks s ON s.symbol = a.symbol
        """)
    n = len(rows)
    if not n:
        return {}
    def _pct(pred):
        return round(100 * sum(1 for r in rows if pred(r)) / n, 1)
    out = {
        "universe": n,
        "pct_above_50": _pct(lambda r: r["above50"]),
        "pct_20d_high": _pct(lambda r: r["at_20h"]),
        "pct_20d_low": _pct(lambda r: r["at_20l"]),
        "pct_up_5d": _pct(lambda r: r["up_5d"]),
        "pct_hl_confirmed": _pct(lambda r: r["sw"] == "confirmed"),
        "pct_hl_broken": _pct(lambda r: r["sw"] == "broken"),
    }
    # composite read: participation + direction - contraction
    out["breadth_score"] = round(
        0.4 * out["pct_above_50"] + 0.3 * out["pct_up_5d"]
        + 0.2 * out["pct_hl_confirmed"]
        - 0.1 * out["pct_hl_broken"], 1)
    try:
        db.execute_query(
            "INSERT INTO engine_weights(key, value, updated_at)"
            " VALUES ('breadth:universe', CAST(:v AS jsonb), now())"
            " ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value,"
            "   updated_at = now()",
            {"v": json.dumps(out)})
    except Exception as exc:
        logger.debug("breadth persist: %s", exc)
    return out


def read() -> dict[str, Any]:
    from app.database import db
    rows = db.execute_query(
        "SELECT value FROM engine_weights WHERE key='breadth:universe'")
    if rows:
        v = rows[0]["value"]
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return {}
        return v or {}
    return {}
