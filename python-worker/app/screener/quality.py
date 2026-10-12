"""Quality-mover screen: CANSLIM/Minervini-style fundamental gate applied
to market movers.

Universe movers first, then top market movers — each scored against:
  growth    : latest-quarter YoY EPS & revenue growth >= 25%
  quality   : ROE > 15%
  liquidity : price > $10 and session volume > 300K
  trend     : price > SMA20 or SMA50, within 12% of the 20d high
Institutional ownership is not available on the current FMP plan.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from typing import Any, Optional

logger = logging.getLogger(__name__)

def save_mover_snapshots(rows: list[dict]) -> None:
    """Upsert today's screened movers — one row per symbol per day."""
    from app.database import db
    for r in rows:
        try:
            db.execute_update(
                """
                INSERT INTO mover_snapshots (
                    symbol, as_of_date, kinds, change_pct, volume, verdict,
                    passed, risk_level, risks, in_portfolio, in_watchlist)
                VALUES (:symbol, :d, :kinds, :chg, :vol, :verdict,
                        :passed, :risk_level, :risks, :port, :watch)
                ON CONFLICT (symbol, as_of_date) DO UPDATE SET
                    kinds = EXCLUDED.kinds, change_pct = EXCLUDED.change_pct,
                    volume = EXCLUDED.volume, verdict = EXCLUDED.verdict,
                    passed = EXCLUDED.passed, risk_level = EXCLUDED.risk_level,
                    risks = EXCLUDED.risks, updated_at = now()
                """,
                {"symbol": r["symbol"], "d": date.today(),
                 "kinds": r["mover_kinds"],
                 "chg": r.get("change_pct"),
                 "vol": r["volume"], "verdict": r["verdict"],
                 "passed": r["passed"], "risk_level": r["risk_level"],
                 "risks": [x.split(" — ")[0] for x in r["risks"]],
                 "port": r["in_portfolio"], "watch": r["in_watchlist"]},
            )
        except Exception as exc:
            logger.debug("mover snapshot save failed for %s: %s",
                         r["symbol"], exc)


def mover_streaks(symbols: list[str], lookback_days: int = 10) -> dict[str, dict]:
    """{symbol: {days_on_list, volume_trend}} — the accumulation memory.

    days_on_list = distinct days the symbol appeared within the lookback.
    volume_trend = today's volume vs the average of its prior list days.
    """
    from app.database import db
    if not symbols:
        return {}
    try:
        rows = db.execute_query(
            """
            SELECT symbol, as_of_date, volume,
                   max(change_pct) OVER (PARTITION BY symbol) AS change_pct
            FROM mover_snapshots
            WHERE symbol = ANY(:symbols)
              AND as_of_date >= :cutoff
            ORDER BY symbol, as_of_date
            """,
            {"symbols": symbols,
             "cutoff": date.today() - timedelta(days=lookback_days)},
        )
    except Exception as exc:
        logger.debug("mover streak lookup failed: %s", exc)
        return {}
    per: dict[str, list] = {}
    for r in rows:
        per.setdefault(r["symbol"].upper(), []).append(r)
    out = {}
    for sym, days in per.items():
        vols = [float(d["volume"]) for d in days if d["volume"]]
        today_vol = vols[-1] if days and days[-1]["as_of_date"] == date.today() else None
        prior_vols = vols[:-1] if today_vol else vols
        avg_prior = sum(prior_vols) / len(prior_vols) if prior_vols else None
        trend = ("rising" if today_vol and avg_prior and today_vol > avg_prior * 1.1
                 else "falling" if today_vol and avg_prior and today_vol < avg_prior * 0.9
                 else "flat" if avg_prior else "new")
        out[sym] = {"days_on_list": len({d["as_of_date"] for d in days}),
                    "volume_trend": trend,
                    "last_change_pct": float(days[-1]["change_pct"]) if days[-1]["change_pct"] else None}
    return out


def _persist_streak_fields(rows: list[dict]) -> None:
    from app.database import db
    for r in rows:
        try:
            db.execute_update(
                "UPDATE mover_snapshots SET days_on_list=:d, accumulation=:a "
                "WHERE symbol=:s AND as_of_date=:dt",
                {"d": r["days_on_list"], "a": r["accumulation"],
                 "s": r["symbol"], "dt": date.today()})
        except Exception as exc:
            logger.debug("streak persist failed for %s: %s", r["symbol"], exc)


async def evaluate_mover_outcomes(svc=None, horizons: tuple = (1, 5, 10)) -> dict[str, int]:
    """Forward returns after each movers-list snapshot — the honesty loop for
    the quality verdict and the accumulation flag. Runs at the tail of each
    scheduled alert scan so outcomes accumulate with history."""
    from app.database import db
    from app.market_data import MarketDataService

    svc = svc or MarketDataService()
    rows = db.execute_query(
        """
        SELECT s.symbol, s.as_of_date
        FROM mover_snapshots s
        WHERE s.as_of_date <= :cutoff
          AND NOT EXISTS (
              SELECT 1 FROM mover_outcomes o
              WHERE o.symbol = s.symbol AND o.as_of_date = s.as_of_date
                AND o.horizon_days = :max_h
          )
        ORDER BY s.as_of_date DESC
        LIMIT 300
        """,
        {"cutoff": date.today(), "max_h": max(horizons)},
    )
    done, errors = 0, 0
    for s in rows:
        try:
            bars = await svc.get_ohlcv(s["symbol"], start=s["as_of_date"],
                                       interval="1d")
            if not bars:
                continue
            entry = float(bars[0].close)
            anchor = bars[0].timestamp.date()
            forward = [b for b in bars if b.timestamp.date() > anchor]
            if not forward:
                continue
            for h in horizons:
                window = forward[:h]
                if len(window) < min(h, 2):
                    continue
                ret = (window[-1].close - entry) / entry * 100
                mfe = max(b.high for b in window) / entry * 100 - 100
                mae = min(b.low for b in window) / entry * 100 - 100
                db.execute_update(
                    """
                    INSERT INTO mover_outcomes
                        (symbol, as_of_date, horizon_days,
                         entry_price, ret_pct, mfe_pct, mae_pct)
                    VALUES (:sym, :d, :h, :entry, :ret, :mfe, :mae)
                    ON CONFLICT (symbol, as_of_date, horizon_days) DO NOTHING
                    """,
                    {"sym": s["symbol"], "d": s["as_of_date"], "h": h,
                     "entry": entry, "ret": round(ret, 2),
                     "mfe": round(mfe, 2), "mae": round(mae, 2)},
                )
            done += 1
        except Exception as exc:
            logger.error("mover outcome eval failed for %s: %s",
                         s["symbol"], exc)
            errors += 1
    return {"evaluated": done, "errors": errors}


MIN_GROWTH = 0.25
MIN_ROE = 0.15
MIN_PRICE = 10.0
MIN_VOLUME = 300_000
MAX_DRAWDOWN = -0.12   # within 12% of 20d high = consolidation, not breakdown
EXTRA_CANDIDATES = 12


def _risks(checks: dict, eps_growth: Optional[float],
           rev_growth: Optional[float], roe: Optional[float],
           price: Optional[float], vs_sma20: Optional[float],
           dd20: Optional[float], ov: dict) -> list[str]:
    """Deterministic risk flags — the "how could this lose long-term" list.

    Mirrors the revenue-vs-EPS reads: engineered EPS, margin pressure,
    cash burn, priced above our fair value, estimate cuts, extension.
    """
    risks = []
    if checks.get("eps_growth_25") and (rev_growth or 0) < 0.10:
        risks.append("ENGINEERED_EPS — EPS growth without revenue: buybacks/margins, finite")
    if (rev_growth or 0) >= 0.15 and (eps_growth or 0) < 0:
        risks.append("MARGIN_PRESSURE — revenue up but earnings down")
    if roe is not None and roe < 0:
        risks.append("CASH_BURN — negative ROE: growth funded by capital, watch dilution")
    fv = ov.get("fair_value")
    if fv and price and price > fv * 1.10:
        risks.append("ABOVE_FV — priced >10% over our fair value")
    if (ov.get("eps_delta_pct") or 0) <= -5:
        risks.append("ESTIMATE_CUTS — analysts revising EPS down")
    if str(ov.get("catalyst_direction") or "").upper() == "NEGATIVE" \
            or ov.get("grade_action") == "downgrade":
        risks.append("NEG_CATALYST — downgrade/negative event recent")
    if vs_sma20 is not None and vs_sma20 > 12:
        risks.append("EXTENDED — >12% above SMA20, chase risk")
    if dd20 is not None and dd20 < -12:
        risks.append("BREAKDOWN — >12% off 20d high, not a consolidation")
    return risks


async def _quality_row(svc, fmp, symbol: str, uni: dict[str, dict],
                       mover_kinds: set[str], ov: dict,
                       change_pct: Optional[float]) -> Optional[dict[str, Any]]:
    try:
        bars, growth_rows, fund = await asyncio.gather(
            svc.get_ohlcv(symbol, period="6mo"),
            asyncio.to_thread(fmp.get_income_statement_growth, symbol, "quarter"),
            svc.get_fundamentals(symbol),
        )
    except Exception:
        return None
    if len(bars) < 55:
        return None

    closes = [b.close for b in bars]
    price = closes[-1]
    last_vol = bars[-1].volume or 0
    sma20 = sum(closes[-20:]) / 20
    sma50 = sum(closes[-50:]) / 50
    high20 = max(b.high for b in bars[-20:])
    dd20 = price / high20 - 1 if high20 else None
    vs_sma20_val = (price / sma20 - 1) if price and sma20 else None

    g = growth_rows[0] if isinstance(growth_rows, list) and growth_rows else {}
    eps_growth = (g.get("growthEPS") or g.get("growthDilutedEPS")
                  or g.get("growthNetIncome"))
    rev_growth = g.get("growthRevenue")
    roe = fund.roe if fund else None

    # Acceleration = this quarter's YoY growth vs the prior quarter's YoY —
    # the CANSLIM inflection signature (growth RATE rising, not just high).
    # growth_rows is already quarterly-ordered; index 1 = previous period.
    pg = growth_rows[1] if isinstance(growth_rows, list) \
        and len(growth_rows) > 1 else {}
    eps_prev = (pg.get("growthEPS") or pg.get("growthDilutedEPS")
                or pg.get("growthNetIncome"))
    rev_prev = pg.get("growthRevenue")
    eps_accel = (eps_growth - eps_prev
                 if eps_growth is not None and eps_prev is not None else None)
    rev_accel = (rev_growth - rev_prev
                 if rev_growth is not None and rev_prev is not None else None)

    # Streaks — consecutive quarters where the YoY growth rate IMPROVED vs
    # the quarter before it, counting back from latest. One quarter of
    # acceleration is noise; 2-3 in a row is the emerging-leader signature.
    # Decel = the mirror (consecutive declines) — early trim warning on
    # held names. FMP returns ~5 quarters → max streak 4.
    def _grow(g_):
        return (g_.get("growthEPS") or g_.get("growthDilutedEPS")
                or g_.get("growthNetIncome"))

    _gr = growth_rows if isinstance(growth_rows, list) else []
    eps_path = [_grow(g_) for g_ in _gr if g_]
    rev_path = [g_.get("growthRevenue") for g_ in _gr if g_]
    eps_path = [v for v in eps_path if v is not None][:5]
    rev_path = [v for v in rev_path if v is not None][:5]

    def _streak(path, up=True):
        n = 0
        for a, b in zip(path, path[1:]):
            if (a > b) == up:
                n += 1
            else:
                break
        return n

    eps_streak = _streak(eps_path)
    rev_streak = _streak(rev_path)
    eps_decel = _streak(eps_path, up=False)
    rev_decel = _streak(rev_path, up=False)
    # Require positive current growth too — −50%→−10% EPS is "less bad",
    # not acceleration into a growth phase.
    accelerating = bool(eps_accel is not None and rev_accel is not None
                        and eps_accel > 0 and rev_accel > 0
                        and (eps_growth or 0) > 0 and (rev_growth or 0) > 0)

    checks = {
        "eps_growth_25": eps_growth is not None and eps_growth >= MIN_GROWTH,
        "rev_growth_25": rev_growth is not None and rev_growth >= MIN_GROWTH,
        "roe_15": roe is not None and roe >= MIN_ROE,
        "price_gt_10": price is not None and price > MIN_PRICE,
        "volume_300k": last_vol >= MIN_VOLUME,
        "trend_ok": price is not None and (price > sma20 or price > sma50),
        "consolidating": dd20 is not None and dd20 >= MAX_DRAWDOWN,
    }
    passed = sum(checks.values())

    flags = uni.get(symbol.upper()) or {}
    risks = _risks(checks, eps_growth, rev_growth, roe, price,
                   vs_sma20_val, dd20, ov)
    return {
        "symbol": symbol.upper(),
        "in_portfolio": bool(flags.get("in_portfolio")),
        "in_watchlist": bool(flags.get("in_watchlist")),
        "mover_kinds": sorted(mover_kinds),
        "change_pct": change_pct,
        "price": round(price, 2) if price else None,
        "volume": int(last_vol),
        "eps_growth": round(eps_growth * 100, 1) if eps_growth is not None else None,
        "rev_growth": round(rev_growth * 100, 1) if rev_growth is not None else None,
        "roe": round(roe * 100, 1) if roe is not None else None,
        "eps_growth_prev": round(eps_prev * 100, 1) if eps_prev is not None else None,
        "rev_growth_prev": round(rev_prev * 100, 1) if rev_prev is not None else None,
        "eps_accel": round(eps_accel * 100, 1) if eps_accel is not None else None,
        "rev_accel": round(rev_accel * 100, 1) if rev_accel is not None else None,
        "eps_streak": eps_streak,
        "rev_streak": rev_streak,
        "eps_decel": eps_decel,
        "rev_decel": rev_decel,
        "eps_path": [round(v * 100, 1) for v in eps_path],
        "rev_path": [round(v * 100, 1) for v in rev_path],
        "accelerating": accelerating,
        "vs_sma20": round((price / sma20 - 1) * 100, 1) if price and sma20 else None,
        "vs_sma50": round((price / sma50 - 1) * 100, 1) if price and sma50 else None,
        "dd20_pct": round(dd20 * 100, 1) if dd20 is not None else None,
        "checks": checks,
        "passed": passed,
        "risks": risks,
        "risk_level": ("high" if len(risks) >= 3 else
                       "medium" if len(risks) >= 1 else "low"),
        # Fundamentals are the gate; liquidity/trend checks are modifiers.
        # QUALITY = explosive growth + proven ROE. GROWTH = explosive growth
        # without proven capital efficiency — young leaders (SPCX profile).
        "verdict": ("QUALITY MOVER"
                    if (checks["eps_growth_25"] and checks["rev_growth_25"]
                        and checks["roe_15"] and passed >= 5)
                    else "GROWTH MOVER"
                    if (checks["eps_growth_25"] and checks["rev_growth_25"]
                        and passed >= 5)
                    else "partial" if passed >= 4 else "fails quality gate"),
    }


async def quality_movers(svc, fmp, uni: dict[str, dict],
                         movers: dict[str, list[dict]],
                         max_symbols: int = 18) -> dict[str, Any]:
    cand: dict[str, set[str]] = {}
    chg: dict[str, float] = {}
    for kind in ("gainers", "losers", "most_active"):
        for r in movers.get(kind) or []:
            sym = str(r.get("symbol") or "").upper()
            if not sym:
                continue
            cand.setdefault(sym, set()).add(kind)
            v = float(r.get("changesPercentage") or 0)
            if abs(v) > abs(chg.get(sym, 0.0)):
                chg[sym] = v

    in_uni = [s for s in cand if s in uni]
    by_move = sorted((s for s in cand if s not in uni), key=lambda s: -abs(chg[s]))
    ordered = (in_uni + by_move)[:max_symbols]

    from app.symbol_overlay import persisted_overlay
    overlay = persisted_overlay(ordered)

    # Bound the provider burst — 18 symbols × 3 calls at once trips FMP
    # throttling/retries, which is what made cold runs exceed 2 minutes.
    sem = asyncio.Semaphore(8)

    async def _one(sym: str):
        async with sem:
            return await _quality_row(
                svc, fmp, sym, uni, cand[sym], overlay.get(sym, {}), chg.get(sym))

    rows = [r for r in await asyncio.gather(*(_one(s) for s in ordered)) if r]

    # Persist + attach streak memory: days on list, volume trend, and the
    # accumulation flag (repeat appearances + quality verdict + rising vol).
    try:
        await asyncio.to_thread(save_mover_snapshots, rows)
        streaks = await asyncio.to_thread(mover_streaks, [r["symbol"] for r in rows])
    except Exception as exc:
        logger.debug("mover snapshot pipeline failed: %s", exc)
        streaks = {}
    for r in rows:
        st = streaks.get(r["symbol"]) or {}
        r["days_on_list"] = st.get("days_on_list", 1)
        r["volume_trend"] = st.get("volume_trend", "new")
        r["accumulation"] = bool(
            r["days_on_list"] >= 3
            and r["verdict"] in ("QUALITY MOVER", "GROWTH MOVER")
            and r["volume_trend"] in ("rising", "new"))

    # Persist the streak verdict back onto today's snapshot rows so
    # mover_stats can split outcomes by it durably.
    try:
        await asyncio.to_thread(_persist_streak_fields, rows)
    except Exception as exc:
        logger.debug("snapshot streak persist failed: %s", exc)

    rows.sort(key=lambda r: (
        not (r["in_portfolio"] or r["in_watchlist"]),
        not r["accumulation"], -r["passed"], len(r["risks"])))
    return {
        "items": rows,
        "universe_count": sum(1 for r in rows if r["in_portfolio"] or r["in_watchlist"]),
        "quality_count": sum(1 for r in rows if r["verdict"] == "QUALITY MOVER"),
        "accumulation_count": sum(1 for r in rows if r["accumulation"]),
    }


_quality_state: dict[str, Any] = {
    "running": False, "last_run_at": None, "results": None, "error": None,
}


def quality_status() -> dict[str, Any]:
    return {
        "running": _quality_state["running"],
        "last_run_at": _quality_state["last_run_at"],
        "result_count": len((_quality_state["results"] or {}).get("items") or []),
        "error": _quality_state["error"],
    }


def quality_results() -> dict[str, Any]:
    res = _quality_state["results"] or {"items": []}
    return {**res, "as_of": _quality_state["last_run_at"]}


async def run_quality_job(max_symbols: int = 18) -> dict[str, Any]:
    """Background job — the fundamental fetches take ~1-2 min cold, which is
    longer than an HTTP request should block."""
    from datetime import datetime, timezone
    if _quality_state["running"]:
        return {"status": "already_running"}
    _quality_state["running"] = True
    _quality_state["error"] = None
    try:
        from app.alerts import scanner as alert_scanner
        from app.market_data import MarketDataService
        from app.providers.financial_modeling_prep.client import EnhancedFMPClient
        fmp = EnhancedFMPClient.from_settings()
        movers = fmp.get_market_movers()
        uni = alert_scanner.universe()
        _quality_state["results"] = await quality_movers(
            MarketDataService(), fmp, uni, movers, max_symbols=max_symbols)
        return {"status": "completed"}
    except Exception as exc:
        logger.error("quality screen failed: %s", exc)
        _quality_state["error"] = str(exc)
        return {"status": "error", "error": str(exc)}
    finally:
        _quality_state["running"] = False
        _quality_state["last_run_at"] = datetime.now(timezone.utc).isoformat()
