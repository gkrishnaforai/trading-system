"""Opening-range-breakout day-trade screen.

Universe ∩ movers → gap + relative volume + first-15-min range break.
ORB is only worth watching on names already moving with institutional
interest — that's exactly what the movers feed supplies, so candidates
come from FMP's gainers/losers/most-active lists rather than the whole
market.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date
from typing import Any, Optional

logger = logging.getLogger(__name__)

OR_BARS = 3            # first 3 x 5-min bars = 15-min opening range
MIN_GAP_PCT = 1.0      # meaningful overnight repricing
MIN_RVOL = 1.5         # real interest vs average pace
EXTRA_CANDIDATES = 10  # top non-universe movers to include


async def _orb_row(svc, symbol: str, uni: dict[str, dict],
                   mover_kinds: set[str]) -> Optional[dict[str, Any]]:
    try:
        daily, m5 = await asyncio.gather(
            svc.get_ohlcv(symbol, period="3mo"),
            svc.get_ohlcv(symbol, period="1d", interval="5m"),
        )
    except Exception:
        return None
    if len(daily) < 21 or not m5:
        return None

    today = m5[-1].timestamp.date()
    m5_today = [b for b in m5 if b.timestamp.date() == today]
    if len(m5_today) < 2:
        return None

    # prior close = last daily bar before today's session date
    prior = [b for b in daily if b.timestamp.date() < today]
    if not prior:
        return None
    prior_close = prior[-1].close
    session_open = m5_today[0].open
    price = m5_today[-1].close
    if not prior_close or not session_open or not price:
        return None

    gap_pct = (session_open - prior_close) / prior_close * 100

    # RVOL: today's 5m volume so far vs average-day volume pro-rated to
    # the same point in the session (78 x 5m bars = full RTH session)
    avg_vol = sum(b.volume or 0 for b in prior[-20:]) / min(len(prior), 20)
    elapsed = len(m5_today) / 78.0
    today_vol = sum(b.volume or 0 for b in m5_today)
    rvol = (today_vol / (avg_vol * elapsed)) if avg_vol and elapsed else None

    or_bars = m5_today[:OR_BARS]
    or_high = max(b.high for b in or_bars)
    or_low = min(b.low for b in or_bars)
    or_range_pct = (or_high - or_low) / price * 100 if price else None
    if len(m5_today) <= OR_BARS:
        or_state = "forming"
    elif price > or_high:
        or_state = "long_break"
    elif price < or_low:
        or_state = "short_break"
    else:
        or_state = "inside"

    # trend context for the "keep for swing" question — above SMA50 =
    # the day-trade has the daily trend behind it
    from app.market_data import indicators as ind
    sma50 = ind.sma(list(daily), 50)
    atr_pct = ind.atr_pct(list(daily))

    flags = uni.get(symbol.upper()) or {}
    qualified = abs(gap_pct) >= MIN_GAP_PCT and (rvol or 0) >= MIN_RVOL
    if or_state == "long_break" and qualified and gap_pct > 0:
        verdict = "ORB LONG — broke opening range on gap+volume"
    elif or_state == "short_break" and qualified and gap_pct < 0:
        verdict = "ORB SHORT — broke range low on gap-down+volume"
    elif qualified:
        verdict = "WATCH — gap+RVOL qualify, wait for range break"
    else:
        verdict = "weak — gap or volume below threshold"

    return {
        "symbol": symbol.upper(),
        "in_portfolio": bool(flags.get("in_portfolio")),
        "in_watchlist": bool(flags.get("in_watchlist")),
        "mover_kinds": sorted(mover_kinds),
        "session_date": today.isoformat(),
        "prior_close": round(prior_close, 2),
        "session_open": round(session_open, 2),
        "gap_pct": round(gap_pct, 2),
        "price": round(price, 2),
        "change_pct": round((price - prior_close) / prior_close * 100, 2),
        "rvol": round(rvol, 2) if rvol else None,
        "or_high": round(or_high, 2),
        "or_low": round(or_low, 2),
        "or_range_pct": round(or_range_pct, 2) if or_range_pct else None,
        "or_state": or_state,
        "verdict": verdict,
        "atr_pct": round(atr_pct * 100, 1) if atr_pct else None,
        "above_sma50": bool(price > sma50) if sma50 else None,
    }


def _orb_score(row: dict, spy_chg: Optional[float]) -> tuple[float, list[str]]:
    """Stocks-in-play ORB scoring — the factors Zarattini/Aziz found drive
    win rate: catalyst + abnormal volume, tight opening range vs ATR,
    trading with the gap direction, and a trend tailwind."""
    score, why = 0.0, []
    brk = row.get("or_state")
    gap = row.get("gap_pct") or 0
    rvol = row.get("rvol") or 0
    direction = "long" if gap > 0 else "short"

    if brk in ("long_break", "short_break") and (
            (brk == "long_break") == (direction == "long")):
        score += 3
        why.append(f"opening range already broken {direction} — trigger live")
    elif brk == "inside":
        score += 1
        why.append("inside the range — trigger pending")

    if rvol >= 3:
        score += 3
        why.append(f"RVOL {rvol}× — heavy institutional interest")
    elif rvol >= 2:
        score += 2
        why.append(f"RVOL {rvol}×")
    elif rvol >= 1.5:
        score += 1

    if 1 <= abs(gap) <= 10:
        score += 2
        why.append(f"gap {gap:+.1f}% — real repricing, not fade-sized")
    elif abs(gap) > 15:
        score -= 1
        why.append(f"gap {gap:+.1f}% — oversized, fade risk")

    # tight OR vs daily ATR = coiled break
    atr = row.get("atr_pct")
    if row.get("or_range_pct") and atr:
        if row["or_range_pct"] < atr * 0.5:
            score += 2
            why.append(f"tight range {row['or_range_pct']}% vs ATR {atr}%")
        elif row["or_range_pct"] > atr:
            score -= 1
            why.append("opening range already wide vs ATR — late")

    if row.get("in_portfolio") or row.get("in_watchlist"):
        score += 1
        why.append("in your universe — fundamentals known")

    if spy_chg is not None:
        tail = (direction == "long" and spy_chg > 0) or \
               (direction == "short" and spy_chg < 0)
        if tail:
            score += 1
            why.append("market tailwind (SPY moving same way)")
        else:
            why.append("against the market tape — lower odds")

    if direction == "long" and row.get("above_sma50"):
        score += 1
        why.append("above SMA50 — daily trend behind it")
    return score, why


async def _swing_check(svc, fmp, row: dict) -> dict:
    """Is this day-trade worth holding for a swing? Fundamental screen:
    real revenue, EPS growth or positive revisions, not over our fair value,
    above SMA50. Only run on the top-scoring rows (provider calls)."""
    from app.symbol_overlay import persisted_overlay
    sym = row["symbol"]
    out = {"swing_ok": False, "swing_reasons": []}
    if row.get("or_state") != "long_break" and (row.get("gap_pct") or 0) <= 0:
        out["swing_reasons"] = ["short-side trade — swing holds are long-only"]
        return out
    try:
        growth_rows, fund = await asyncio.gather(
            asyncio.to_thread(fmp.get_income_statement_growth, sym, "quarter"),
            svc.get_fundamentals(sym),
        )
        ov = persisted_overlay([sym]).get(sym, {})
    except Exception:
        out["swing_reasons"] = ["fundamentals unavailable"]
        return out
    g = growth_rows[0] if isinstance(growth_rows, list) and growth_rows else {}
    rev_g = g.get("growthRevenue")
    eps_g = g.get("growthEPS") or g.get("growthDilutedEPS")
    reasons, ok = [], True
    if rev_g is not None and rev_g > 0:
        reasons.append(f"revenue +{rev_g*100:.0f}% YoY")
    else:
        ok = False
        reasons.append("no revenue growth — product story unproven")
    if eps_g is not None and eps_g > 0:
        reasons.append(f"EPS +{eps_g*100:.0f}%")
    elif (ov.get("eps_delta_pct") or 0) > 0:
        reasons.append("EPS estimates being revised UP")
    else:
        reasons.append("earnings not growing — revenue-only story")
    fv = ov.get("fair_value")
    px = row.get("price")
    if fv and px and px > fv * 1.15:
        ok = False
        reasons.append(f"price {((px/fv-1)*100):.0f}% above our fair value")
    if not row.get("above_sma50"):
        ok = False
        reasons.append("below SMA50 — daily trend not confirmed")
    if ov.get("catalyst_direction") and str(ov["catalyst_direction"]).upper() == "POSITIVE":
        reasons.append("positive catalyst in play")
        ok = ok and True
    out["swing_ok"] = bool(ok and reasons)
    out["swing_reasons"] = reasons
    return out


async def orb_watchlist(svc, uni: dict[str, dict],
                        movers: dict[str, list[dict]],
                        max_symbols: int = 20) -> dict[str, Any]:
    """movers ∩ universe first, then top market movers — ORB candidates."""
    cand: dict[str, set[str]] = {}
    for kind in ("gainers", "losers", "most_active"):
        for r in movers.get(kind) or []:
            sym = str(r.get("symbol") or "").upper()
            if sym:
                cand.setdefault(sym, set()).add(kind)

    in_uni = [s for s in cand if s in uni]
    by_move = sorted(
        (s for s in cand if s not in uni),
        key=lambda s: -max(
            abs(float(r.get("changesPercentage") or 0))
            for k in cand[s] for r in movers.get(k) or []
            if str(r.get("symbol") or "").upper() == s),
    )
    ordered = (in_uni + by_move)[:max_symbols]

    # Bound the burst — 20 symbols × daily+5m at once trips provider
    # throttling; intraday bars are also rarely cached.
    sem = asyncio.Semaphore(8)

    async def _one(sym: str):
        async with sem:
            return await _orb_row(svc, sym, uni, cand[sym])

    rows = [r for r in await asyncio.gather(*(_one(s) for s in ordered)) if r]

    # Market tailwind — SPY's session direction
    spy_chg = None
    try:
        spy = await svc.get_ohlcv("SPY", period="5d", interval="5m")
        if spy:
            today_spy = [b for b in spy if b.timestamp.date() == spy[-1].timestamp.date()]
            prior = [b for b in spy if b.timestamp.date() < spy[-1].timestamp.date()]
            if today_spy and prior:
                spy_chg = (today_spy[-1].close - prior[-1].close) / prior[-1].close * 100
    except Exception:
        pass

    for r in rows:
        r["orb_score"], r["why"] = _orb_score(r, spy_chg)

    # Swing-hold check on the top candidates only — fundamentals calls are
    # provider-bound, so bound them to the rows that could matter.
    from app.providers.financial_modeling_prep.client import EnhancedFMPClient
    fmp = EnhancedFMPClient.from_settings()
    top_candidates = sorted(rows, key=lambda r: -r["orb_score"])[:6]
    swing = dict(zip(
        (r["symbol"] for r in top_candidates),
        await asyncio.gather(*(_swing_check(svc, fmp, r) for r in top_candidates))))
    for r in rows:
        r.update(swing.get(r["symbol"]) or
                 {"swing_ok": None, "swing_reasons": []})

    rank = {"long_break": 0, "short_break": 1, "inside": 2, "forming": 3}
    rows.sort(key=lambda r: (
        not (r["in_portfolio"] or r["in_watchlist"]),
        rank.get(r["or_state"], 4), -abs(r["gap_pct"])))
    top = sorted(rows, key=lambda r: -r["orb_score"])[:3]
    for r in rows:
        r["top_pick"] = r in top
    return {
        "session_date": rows[0]["session_date"] if rows else date.today().isoformat(),
        "items": rows,
        "top_picks": top,
        "spy_change_pct": round(spy_chg, 2) if spy_chg is not None else None,
        "universe_count": sum(1 for r in rows if r["in_portfolio"] or r["in_watchlist"]),
    }


_orb_state: dict[str, Any] = {
    "running": False, "last_run_at": None, "results": None, "error": None,
}


def orb_status() -> dict[str, Any]:
    return {
        "running": _orb_state["running"],
        "last_run_at": _orb_state["last_run_at"],
        "result_count": len((_orb_state["results"] or {}).get("items") or []),
        "error": _orb_state["error"],
    }


def orb_results() -> dict[str, Any]:
    res = _orb_state["results"] or {"items": []}
    return {**res, "as_of": _orb_state["last_run_at"]}


async def run_orb_job(max_symbols: int = 20) -> dict[str, Any]:
    """Background job — intraday fetches over movers take too long to hold
    an HTTP request open on a cold cache."""
    from datetime import datetime, timezone
    if _orb_state["running"]:
        return {"status": "already_running"}
    _orb_state["running"] = True
    _orb_state["error"] = None
    try:
        from app.alerts import scanner as alert_scanner
        from app.market_data import MarketDataService
        from app.providers.financial_modeling_prep.client import EnhancedFMPClient
        movers = EnhancedFMPClient.from_settings().get_market_movers()
        uni = alert_scanner.universe()
        _orb_state["results"] = await orb_watchlist(
            MarketDataService(), uni, movers, max_symbols=max_symbols)
        return {"status": "completed"}
    except Exception as exc:
        logger.error("ORB screen failed: %s", exc)
        _orb_state["error"] = str(exc)
        return {"status": "error", "error": str(exc)}
    finally:
        _orb_state["running"] = False
        _orb_state["last_run_at"] = datetime.now(timezone.utc).isoformat()
