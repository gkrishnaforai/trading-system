"""Trade ledger + open-position monitor.

trades = the manual journal of real fills across horizons
         (investment | swing | day). trade_exits records partial and
         full exits so realized P&L and actual R multiples accumulate —
         the training data for what *you* actually made vs what the
         signal hypothetically offered.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime, timezone
from typing import Any, Optional

from app.database import db

logger = logging.getLogger(__name__)

# Horizon-specific monitor thresholds
TIME_STOP_BARS = {"day": 1, "swing": 15, "investment": None}


def log_trade(t: dict[str, Any]) -> dict[str, Any]:
    trade_id = str(uuid.uuid4())
    db.execute_update(
        """
        INSERT INTO trades (
            id, symbol, trade_type, status, signal_id, entry_date, entry_price,
            shares, initial_stop, target_1, target_2, setup_type,
            regime_snapshot, thesis, user_id
        ) VALUES (
            :id, :symbol, :trade_type, 'open', :signal_id, :entry_date, :entry_price,
            :shares, :initial_stop, :target_1, :target_2, :setup_type,
            CAST(:regime_snapshot AS jsonb), :thesis, :user_id
        )
        """,
        {
            "id": trade_id,
            "symbol": t["symbol"].upper(),
            "user_id": t.get("user_id") or "manual",
            "trade_type": t.get("trade_type") or "swing",
            "signal_id": t.get("signal_id"),
            "entry_date": t.get("entry_date") or date.today().isoformat(),
            "entry_price": t["entry_price"],
            "shares": t["shares"],
            "initial_stop": t.get("initial_stop"),
            "target_1": t.get("target_1"),
            "target_2": t.get("target_2"),
            "setup_type": t.get("setup_type"),
            "regime_snapshot": json.dumps(t.get("regime_snapshot") or {}),
            "thesis": t.get("thesis"),
        },
    )
    return {"id": trade_id, "symbol": t["symbol"].upper()}


def open_trades(user_id: str = "manual") -> list[dict[str, Any]]:
    return db.execute_query(
        """
        SELECT t.*, COALESCE((SELECT sum(e.qty) FROM trade_exits e
                             WHERE e.trade_id = t.id), 0) AS exited_qty
        FROM trades t
        WHERE t.status IN ('open', 'partial') AND t.user_id = :user_id
        ORDER BY t.entry_date DESC
        """,
        {"user_id": user_id},
    )


def record_exit(trade_id: str, price: float, qty: float,
                reason: str = "manual", exit_date: Optional[str] = None) -> dict[str, Any]:
    trade = db.execute_query("SELECT * FROM trades WHERE id = :id", {"id": trade_id})
    if not trade:
        return {"error": "trade not found"}
    trade = trade[0]

    db.execute_update(
        """
        INSERT INTO trade_exits (trade_id, exit_date, price, qty, reason)
        VALUES (:trade_id, :exit_date, :price, :qty, :reason)
        """,
        {"trade_id": trade_id,
         "exit_date": exit_date or date.today().isoformat(),
         "price": price, "qty": qty, "reason": reason},
    )

    exited = db.execute_query(
        "SELECT COALESCE(sum(qty),0) AS q FROM trade_exits WHERE trade_id = :id",
        {"id": trade_id})[0]["q"]
    realized = db.execute_query(
        "SELECT COALESCE(sum((price - :entry) * qty),0) AS pl "
        "FROM trade_exits WHERE trade_id = :id",
        {"id": trade_id, "entry": trade["entry_price"]})[0]["pl"]

    remaining = float(trade["shares"]) - float(exited)
    status = "closed" if remaining <= 0 else "partial"
    db.execute_update(
        """
        UPDATE trades SET status = CAST(:status AS text), realized_pl = :pl,
               closed_at = CASE WHEN CAST(:status AS text) = 'closed' THEN now() ELSE closed_at END
        WHERE id = :id
        """,
        {"status": status, "pl": realized, "id": trade_id},
    )
    return {"trade_id": trade_id, "status": status,
            "remaining_qty": max(0.0, remaining), "realized_pl": float(realized)}


async def monitor_open_trades(svc) -> list[dict[str, Any]]:
    """Evaluate every open trade against its plan: current R, distance to
    stop/target, days held, regime flip, negative catalyst → suggestion."""
    from app.swing_opportunity.engine import analyze_stock, _stock_permission
    from app.symbol_overlay import persisted_overlay

    trades = open_trades()
    if not trades:
        return []
    overlay = persisted_overlay([t["symbol"] for t in trades])
    spy_bars = await svc.get_ohlcv("SPY", period="1y",
                                   prefer=["fmp", "yahoo_finance"])
    out = []
    for tr in trades:
        row = dict(tr)
        bars = []
        try:
            bars = await svc.get_ohlcv(tr["symbol"], period="1y")
            price = bars[-1].close if bars else None
            stock = analyze_stock(tr["symbol"], bars, spy_bars) if len(bars) >= 200 else None
            stock_perm = _stock_permission(stock.technicals) if stock else "unknown"
            bars_held = sum(1 for b in bars
                            if b.timestamp.date() > tr["entry_date"])
        except Exception as exc:
            logger.debug("monitor fetch failed for %s: %s", tr["symbol"], exc)
            price, stock_perm, bars_held = None, "unknown", None

        entry = float(tr["entry_price"])
        stop = tr["initial_stop"]
        t1 = tr["target_1"]
        open_qty = float(tr["shares"]) - float(tr.get("exited_qty") or 0)
        risk = entry - stop if stop else None

        row["current_price"] = price
        row["open_qty"] = open_qty
        row["unrealized_pl"] = round((price - entry) * open_qty, 2) if price else None
        row["gain_pct"] = round((price - entry) / entry * 100, 1) if price else None
        row["r_now"] = round((price - entry) / risk, 2) if price and risk else None
        row["pct_to_stop"] = round((price - stop) / price * 100, 1) if price and stop else None
        row["pct_to_t1"] = round((t1 - price) / price * 100, 1) if price and t1 else None
        row["bars_held"] = bars_held
        row["days_held"] = (date.today() - tr["entry_date"]).days
        row["stock_permission"] = stock_perm

        is_mr = tr.get("setup_type") == "mean_reversion"
        flags = []
        if price and stop and price <= stop:
            flags.append("STOP_HIT")
        if is_mr:
            # Connors exit: sell the bounce (close > prior bar high) or after 5 bars
            if bars and bars_held and bars_held >= 1 \
                    and len(bars) >= 2 and bars[-1].close > bars[-2].high:
                flags.append("BOUNCE")
            if bars_held is not None and bars_held >= 5:
                flags.append("MR_TIME")
        elif price and t1 and price >= t1:
            flags.append("T1_HIT")
        ttype = tr.get("trade_type") or "swing"
        tstop = 5 if is_mr else TIME_STOP_BARS.get(ttype)
        if tstop and bars_held is not None and bars_held >= tstop and \
                (row["r_now"] or 0) < 0.5:
            flags.append("TIME_STOP")
        entry_perm = (tr.get("regime_snapshot") or {}).get("stock_permission")
        if stock_perm == "disabled" and entry_perm not in (None, "disabled"):
            flags.append("REGIME_FLIP")
        ov = overlay.get(tr["symbol"].upper()) or {}
        if str(ov.get("catalyst_direction") or "").upper() == "NEGATIVE" \
                or ov.get("grade_action") == "downgrade" \
                or (ov.get("eps_delta_pct") or 0) <= -5:
            flags.append("NEG_CATALYST")
        # Profit bands — take-profit prompts where T1 doesn't reach
        # (mainly investment trades, which have no target/time stop)
        gain = row["gain_pct"] or 0
        if gain >= 100:
            flags.append("GAIN_100")
        elif gain >= 50:
            flags.append("GAIN_50")

        # --- Exit-phase reads -------------------------------------------------
        # Extension / climax / distribution / consolidation / chandelier trail —
        # the two exit failure modes: selling a healthy base vs riding a
        # climax back down. All deterministic, from the bars already fetched.
        closes = [b.close for b in bars]
        vols = [b.volume or 0 for b in bars]
        sma20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else None
        sma50 = (stock.technicals.sma50 if stock else
                 (sum(closes[-50:]) / 50 if len(closes) >= 50 else None))
        atr_abs = ((stock.technicals.atr_pct if stock else None) or 0.02) \
            * price if price else None

        # Chandelier trail — highest close since entry − 3×ATR, ratchets only
        # up, never below the initial stop. Catches ORCL-type round-trips
        # without exiting AMD-type consolidations (trail sits under the base).
        if price and atr_abs and tr.get("entry_date") and bars:
            post = [b for b in bars if b.timestamp.date() >= tr["entry_date"]]
            trail = max(b.close for b in post or bars[-20:]) - 3 * atr_abs
            if stop:
                trail = max(trail, float(stop))
            row["trail_stop"] = round(trail, 2)
            row["trail_pct_below"] = round((price - trail) / price * 100, 1)
            if price <= trail:
                flags.append("TRAIL_STOP")

        pct_above_sma50 = (price / sma50 - 1) if price and sma50 else None
        row["pct_above_sma50"] = round(pct_above_sma50 * 100, 1) \
            if pct_above_sma50 is not None else None

        # EXTENDED — >20% above SMA50: stretched, trim into strength
        if pct_above_sma50 is not None and pct_above_sma50 > 0.20:
            flags.append("EXTENDED")

        # CLIMAX — a bar in the last 3 that is both the widest range and the
        # highest volume of the last 20, while extended. The sell-into-strength
        # signal — ORCL's top printed this before the breakdown.
        if len(bars) >= 25 and pct_above_sma50 is not None \
                and pct_above_sma50 > 0.15:
            rng = [b.high - b.low for b in bars]
            max_r = max(rng[-20:])
            max_v = max(vols[-20:])
            if any(rng[i] >= max_r * 0.999 and vols[i] >= max_v * 0.999
                   for i in range(len(bars) - 3, len(bars))):
                flags.append("CLIMAX")

        # DISTRIBUTION — under SMA50 with ≥2 heavy-volume down days in the
        # last 10: institutions leaving, not pausing.
        if price and sma50 and price < sma50 and len(bars) >= 25:
            avg_vol = sum(vols[-20:]) / 20 or 1
            heavy_downs = sum(
                1 for i in range(len(bars) - 10, len(bars))
                if bars[i].close < bars[i].open and vols[i] > avg_vol * 1.2)
            if heavy_downs >= 2:
                flags.append("DISTRIBUTION")

        # CONSOLIDATING — tight 10-bar range (<8%), above rising-ish SMA20,
        # volume drying up vs the prior 20 bars. The affirmative hold read:
        # AMD-at-340 looked like this before the next leg.
        if price and sma20 and price > sma20 and len(bars) >= 30:
            consol_range = (max(b.high for b in bars[-10:])
                            - min(b.low for b in bars[-10:])) / price
            vol10 = sum(vols[-10:]) / 10
            vol_prev = sum(vols[-30:-10]) / 20 or 1
            if consol_range < 0.08 and vol10 < vol_prev * 0.9:
                flags.append("CONSOLIDATING")
                row["consol_range_pct"] = round(consol_range * 100, 1)
        row["flags"] = flags

        if "STOP_HIT" in flags:
            suggestion = "EXIT — stop hit"
        elif "TRAIL_STOP" in flags:
            suggestion = f"EXIT — trailing stop hit (${row['trail_stop']})"
        elif "BOUNCE" in flags:
            suggestion = "EXIT — bounce target reached (MR rule)"
        elif "MR_TIME" in flags:
            suggestion = "EXIT — 5 bars, no bounce (MR rule)"
        elif "DISTRIBUTION" in flags:
            suggestion = "EXIT — distribution: under SMA50 on heavy-volume downs"
        elif "REGIME_FLIP" in flags and "NEG_CATALYST" in flags:
            suggestion = "EXIT — regime broke + negative catalyst"
        elif "CLIMAX" in flags:
            suggestion = "TAKE PROFIT — climax signature, sell into strength"
        elif "T1_HIT" in flags:
            suggestion = "TAKE PROFIT — trim ~⅓, trail rest"
        elif "EXTENDED" in flags:
            suggestion = f"TRIM — {row['pct_above_sma50']}% above SMA50, stretched"
        elif "GAIN_100" in flags:
            suggestion = f"TAKE PROFIT — +{row['gain_pct']:.0f}%, trim into strength"
        elif "GAIN_50" in flags:
            suggestion = f"TRIM — +{row['gain_pct']:.0f}%, take partial profits"
        elif "TIME_STOP" in flags:
            suggestion = "REVIEW — flat past time stop"
        elif "CONSOLIDATING" in flags:
            suggestion = "HOLD — base intact (tight range, volume drying up)"
        elif flags:
            suggestion = "WATCH — " + " · ".join(flags)
        else:
            suggestion = "HOLD — plan intact"
        row["suggestion"] = suggestion
        out.append(row)
    return out


def summary(user_id: str = "manual") -> dict[str, Any]:
    r = db.execute_query(
        """
        SELECT count(*) FILTER (WHERE status = 'closed') AS closed_n,
               count(*) FILTER (WHERE status IN ('open','partial')) AS open_n,
               COALESCE(sum(realized_pl) FILTER (WHERE realized_pl IS NOT NULL), 0)
                   AS realized_pl,
               count(*) FILTER (WHERE status='closed' AND realized_pl > 0) AS wins
        FROM trades WHERE user_id = :user_id
        """,
        {"user_id": user_id},
    )[0]
    r["win_rate"] = (r["wins"] / r["closed_n"]) if r["closed_n"] else None
    return r
