"""Pick outcomes — the honesty loop for the daily edge board.

Same pattern as evaluate_mover_outcomes: for each persisted pick,
fetch forward daily bars, compute per-horizon return / MFE / MAE /
return-vs-SPY, and which level (stop/target from the pick's own plan)
was hit first — conservative: if both trip same day, stop wins.

Runs at the tail of the alert scan alongside the other evaluators,
and on demand via the endpoint.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)


async def evaluate_pick_outcomes(
        svc=None, horizons: tuple = (1, 3, 5, 10)) -> dict[str, int]:
    from app.database import db
    from app.market_data import MarketDataService

    svc = svc or MarketDataService()
    rows = db.execute_query(
        """
        SELECT p.pick_date, p.lane, p.symbol, p.entry, p.stop, p.target
        FROM daily_picks p
        WHERE p.pick_date < :today
          AND NOT EXISTS (
              SELECT 1 FROM pick_outcomes o
              WHERE o.pick_date = p.pick_date AND o.lane = p.lane
                AND o.symbol = p.symbol AND o.horizon_days = :max_h
          )
        ORDER BY p.pick_date DESC LIMIT 200
        """, {"today": date.today(), "max_h": max(horizons)})

    spy_cache: dict = {}
    done, errors = 0, 0
    for p in rows:
        try:
            bars = await svc.get_ohlcv(p["symbol"], start=p["pick_date"],
                                       interval="1d")
            if not bars:
                continue
            entry = float(bars[0].close)
            anchor = bars[0].timestamp.date()
            forward = [b for b in bars if b.timestamp.date() > anchor]
            if not forward:
                continue

            if p["pick_date"] not in spy_cache:
                sbars = await svc.get_ohlcv("SPY", start=p["pick_date"],
                                            interval="1d")
                sentry = float(sbars[0].close) if sbars else None
                spy_cache[p["pick_date"]] = {
                    "entry": sentry,
                    "closes": [b.close for b in (sbars or [])
                               if b.timestamp.date() > anchor]}
            spy = spy_cache[p["pick_date"]]

            for h in horizons:
                window = forward[:h]
                if len(window) < min(h, 2):
                    continue
                ret = (window[-1].close - entry) / entry * 100
                mfe = max(b.high for b in window) / entry * 100 - 100
                mae = min(b.low for b in window) / entry * 100 - 100
                vs_spy = None
                if spy["entry"] and len(spy["closes"]) >= len(window):
                    vs_spy = ret - ((spy["closes"][len(window) - 1]
                                     - spy["entry"]) / spy["entry"] * 100)
                hit = None
                stop, target = p.get("stop"), p.get("target")
                for b in window:
                    if stop and b.low <= stop:
                        hit = "stop"
                        break
                    if target and b.high >= target:
                        hit = "target"
                        break
                db.execute_update(
                    """
                    INSERT INTO pick_outcomes
                        (pick_date, lane, symbol, horizon_days,
                         entry_price, ret_pct, ret_vs_spy,
                         mfe_pct, mae_pct, hit)
                    VALUES (:d,:l,:s,:h,:e,:r,:vs,:mf,:ma,:hit)
                    ON CONFLICT (pick_date, lane, symbol, horizon_days)
                    DO NOTHING
                    """,
                    {"d": p["pick_date"], "l": p["lane"], "s": p["symbol"],
                     "h": h, "e": entry, "r": round(ret, 2),
                     "vs": round(vs_spy, 2) if vs_spy is not None else None,
                     "mf": round(mfe, 2), "ma": round(mae, 2), "hit": hit})
            done += 1
        except Exception as exc:
            logger.error("pick outcome eval failed for %s: %s",
                         p["symbol"], exc)
            errors += 1
    return {"evaluated": done, "errors": errors}


def pick_scorecard(horizon: int = 5) -> dict[str, Any]:
    """Win/loss summary per lane — did the picks beat SPY at the horizon?"""
    from app.database import db
    rows = db.execute_query(
        """
        SELECT lane, count(*) n,
               avg(ret_pct) avg_ret,
               avg(ret_vs_spy) avg_vs_spy,
               sum((ret_pct > 0)::int) wins,
               sum((ret_vs_spy > 0)::int) beat_spy,
               sum((hit = 'stop')::int) stopped,
               sum((hit = 'target')::int) targeted
        FROM pick_outcomes
        WHERE horizon_days = :h
        GROUP BY lane
        """, {"h": horizon})
    return {"scorecard": rows, "horizon_days": horizon}
