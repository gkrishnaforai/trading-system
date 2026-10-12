"""Level watch — proximity alerts on the arbiter levels.

When a tracked name closes within ~3% of a decision level — the swing
low (put trigger) or the confirm level (call trigger) — emit an
alert_items event so a branch point resolves itself into the feed
instead of requiring the user to stare at the chart.

Fingerprint dedupes per symbol+level+day: one ping per level per day.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from app.database import db

_PROX = 0.03          # within 3% of the level = "at the arbiter"


def run(max_rows: int = 40) -> dict[str, Any]:
    """Scan tracked symbols' stored swing structure; alert on names
    sitting on a decision level."""
    stocks = [dict(r) for r in db.execute_query(
        "SELECT symbol, momentum_state, momentum_detail FROM stocks"
        " WHERE momentum_detail IS NOT NULL")]
    px = {r["symbol"]: float(r["close"]) for r in db.execute_query(
        "SELECT DISTINCT ON (symbol) symbol, close FROM daily_bars"
        " ORDER BY symbol, date DESC")}
    held = {r["symbol"] for r in db.execute_query(
        "SELECT s.symbol FROM portfolio_positions pp"
        " JOIN stocks s ON s.id = pp.stock_id")}
    watched = {r["symbol"] for r in db.execute_query(
        "SELECT s.symbol FROM watchlist_stocks ws"
        " JOIN stocks s ON s.id = ws.stock_id")}

    fired = 0
    for st in stocks:
        sym = st["symbol"]
        spot = px.get(sym)
        if not spot:
            continue
        det = st.get("momentum_detail") or {}
        if isinstance(det, str):
            det = json.loads(det)
        sw = det.get("swing") or {}
        levels = [(sw.get("swing_low"), "swing_low",
                   "hold = dip-buy lives · break = put tranche-1"),
                  (sw.get("confirm_level"), "confirm_level",
                   "reclaim = momentum back — call side confirms"),
                  (sw.get("avwap"), "avwap",
                   "anchored-vwap — the trend arbiter")]
        for lv, name, meaning in levels:
            if not lv:
                continue
            dist = (spot - lv) / spot
            if abs(dist) > _PROX:
                continue
            side = "above" if dist > 0 else "below"
            in_book = sym in held or sym in watched
            db.execute_update(
                "INSERT INTO alert_items (symbol, event_type,"
                " direction, materiality, title, detail, fingerprint,"
                " source, source_timestamp, in_portfolio,"
                " in_watchlist, priority_score)"
                " VALUES (:s,'level_watch','NEUTRAL',:m,:t,"
                " CAST(:d AS jsonb),:f,'level_watch',now(),:pf,:wl,:p)"
                " ON CONFLICT (fingerprint) DO NOTHING",
                {"s": sym,
                 "m": "HIGH" if in_book else "LOW",
                 "t": f"◆ {sym} at decision level — {abs(dist)*100:.1f}%"
                      f" {side} {name} ${lv:.2f}: {meaning}",
                 "d": json.dumps({"level": name, "level_px": lv,
                                  "spot": spot, "dist_pct": round(
                                      dist * 100, 1),
                                  "state": st.get("momentum_state")}),
                 "f": f"level:{sym}:{name}:{date.today().isoformat()}",
                 "pf": sym in held, "wl": sym in watched,
                 "p": 70 if in_book else 40})
            fired += 1
            if fired >= max_rows:
                return {"fired": fired}
    return {"fired": fired}
