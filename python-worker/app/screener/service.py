"""Setup screener: analyze_stock + detect_setup across portfolio ∪ watchlist.

Ranks by the criteria the pattern backtest validated: practice patterns
(first_pullback / rsi2_extreme) and setup score, with the stock's own regime
visible. Results are in-memory (single worker); a scan also feeds the
pattern-learning signal table.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, datetime, timezone
from typing import Any, Optional

from app.alerts import scanner as alert_scanner
from app.alerts import service as alert_service

logger = logging.getLogger(__name__)

PRACTICE_PATTERNS = {"first_pullback", "rsi2_extreme"}

_screen_state: dict[str, Any] = {
    "running": False,
    "last_run_at": None,
    "results": [],
    "errors": [],
}


def screener_status() -> dict[str, Any]:
    return {
        "running": _screen_state["running"],
        "last_run_at": _screen_state["last_run_at"],
        "result_count": len(_screen_state["results"]),
        "errors": _screen_state["errors"],
    }


def _current_env():
    """Real swing environment from the latest regime snapshot."""
    from app.strategy_environment.models import StrategyEnvironment

    card = alert_service.regime_card()
    env_dict = (card or {}).get("swing_environment") or {}
    try:
        return StrategyEnvironment.model_validate(env_dict), card
    except Exception:
        from app.strategy_environment.models import (
            EnvironmentQuality, StrategyHorizon,
        )
        return StrategyEnvironment(
            horizon=StrategyHorizon.SWING, quality=EnvironmentQuality.MEDIUM,
            score=60, confidence=0.5, long_permission="allowed",
            breakout_permission="allowed", pullback_permission="allowed",
            size_multiplier=1.0, data_sufficient=True,
        ), card


def _neutral_regime():
    from app.market_regime.models import (
        MarketPermissions, MarketRegime, RegimeLabel,
    )
    return MarketRegime(
        regime=RegimeLabel.TRANSITION, direction="neutral",
        condition="transition", confidence=0.5, trend_score=0.0,
        deterioration_score=0.3,
        market_permissions=MarketPermissions(
            normal_long=True, dip_buying=True,
            breakout_buying="allowed", size_multiplier=1.0),
    )


async def _screen_symbol(symbol: str, flags: dict, spy_bars, regime, env,
                         svc, overlay: dict,
                         refresh_estimates: bool = False,
                         est_as_of: Optional[date] = None
                         ) -> Optional[dict[str, Any]]:
    from app.swing_opportunity.engine import analyze_stock, detect_setup

    from app.symbol_overlay import fund_signal

    bars = await svc.get_ohlcv(symbol, period="1y")
    if len(bars) < 200:
        return None
    # Daily estimate snapshot — the morning screen is the only daily pass
    # over the whole universe, so it builds the history eps-revision
    # alerts diff against. Watermark comes from the batched high-water
    # read taken once at job start (per-symbol queries used to sit
    # directly on the event loop).
    try:
        from app.fundamental_intelligence.estimate_history import (
            record_estimate_snapshots,
        )
        if refresh_estimates or est_as_of is None or est_as_of < date.today():
            estimates = await svc.get_financial_estimates(
                symbol, period="annual", limit=10)
            await asyncio.to_thread(record_estimate_snapshots,
                                    symbol, estimates)
    except Exception:
        pass
    # pandas/numpy analysis is CPU-bound — run it in a worker thread so it
    # can't starve the loop (the other semaphore slots, other jobs, and the
    # wait_for timers all share this event loop).
    def _analyze():
        s = analyze_stock(symbol, bars, spy_bars)
        return s, detect_setup(s, regime, env)
    stock, setup = await asyncio.to_thread(_analyze)
    t = stock.technicals
    price = t.price
    atr = (t.atr_pct or 0.02) * price if price else None
    stop = price - 2 * atr if price and atr else None
    target = price + 2 * (price - stop) if price and stop else None
    patterns = list(setup.detected_patterns or [])
    row = {
        "symbol": symbol,
        "setup_type": setup.type.value,
        "detected_patterns": patterns,
        "practice": bool(set(patterns) & PRACTICE_PATTERNS),
        "score": round(setup.score, 1),
        "quality": setup.quality.value,
        "stock_permission": setup.stock_permission,
        "falling_knife": setup.falling_knife,
        "price": price, "rsi": t.rsi, "rsi2": t.rsi2,
        "atr_pct": t.atr_pct, "volume_ratio": t.volume_ratio,
        "ret20": t.ret20, "trend_turn_bars": t.trend_turn_bars,
        "dd20": t.drawdown20,
        "sma20": t.sma20, "pctb": t.bb_pctb, "bb_squeeze": t.bb_squeeze,
        "pivot": round(max(b.high for b in bars[-20:]), 2) if bars else None,
        "vs_spy20": (stock.relative_strength.vs_spy20),
        "entry": price, "stop": stop, "target": target,
        "in_portfolio": flags.get("in_portfolio", False),
        "in_watchlist": flags.get("in_watchlist", False),
        "market_permission": env.long_permission,
        "size_multiplier": env.size_multiplier,
        "reasons": setup.reasons,
    }
    ov = overlay.get(symbol.upper()) or {}
    fv_upside, fund = fund_signal(price, ov)
    row["fv_upside_pct"] = round(fv_upside, 1) if fv_upside is not None else None
    row["fund_signal"] = fund
    row["catalyst_direction"] = (ov.get("catalyst_direction") or "").lower() or None
    if ov.get("catalyst_direction"):
        row["catalyst"] = f"{ov['catalyst_direction'].lower()}:{ov.get('catalyst_event') or ''}"
    if ov.get("grade_action"):
        row["grade_action"] = ov["grade_action"]
        row["grade_detail"] = " ".join(
            p for p in [ov.get("grade_company"), ov.get("grade_date")] if p)
    if ov.get("eps_delta_pct") is not None:
        row["eps_delta_pct"] = ov["eps_delta_pct"]
        row["eps_fiscal_year"] = ov.get("eps_fiscal_year")
        row["eps_revision_date"] = ov.get("eps_revision_date")
    # analyst consensus target — provider call, cached 1h in market_data
    try:
        pt = await svc.get_price_target(symbol)
        mean = pt.target_mean or pt.target_median
        if mean and price:
            row["pt_target"] = round(float(mean), 2)
            row["pt_upside_pct"] = round((float(mean) - price) / price * 100, 1)
            row["pt_analysts"] = pt.analyst_count
    except Exception:
        pass
    # 🔴 technical + 🟢 fundamental = early-turn profile, not a hard skip
    row["turn_candidate"] = bool(
        setup.stock_permission in {"restricted", "disabled"}
        and fund == "strong" and not setup.falling_knife)
    # feed the learning loop — every screened setup is a signal
    try:
        from app.pattern_learning import record_signal
        await asyncio.to_thread(record_signal, {
            "symbol": symbol,
            "setup": {"type": setup.type.value, "score": setup.score,
                      "falling_knife": setup.falling_knife,
                      "detected_patterns": patterns,
                      "stock_permission": setup.stock_permission},
            "stock": {"technicals": {
                "price": price, "rsi": t.rsi, "rsi2": t.rsi2,
                "atr_pct": t.atr_pct, "volume_ratio": t.volume_ratio,
                "trend_turn_bars": t.trend_turn_bars},
                "relative_strength": {"vs_spy20": stock.relative_strength.vs_spy20}},
            "risk": {"entry": price, "stop": stop, "target": target,
                     "reward_risk": 2.0, "status": "screener"},
            "decision": {},
            "market_regime": {},
            "swing_environment": {"long_permission": env.long_permission,
                                  "size_multiplier": env.size_multiplier},
        }, source="screener", run_id=None)
    except Exception as exc:
        logger.debug("screener signal capture skipped for %s: %s", symbol, exc)
    return row


async def run_screener_job(symbols: Optional[list[str]] = None,
                           max_concurrency: int = 8) -> dict[str, Any]:
    """Background screen over the universe. Returns immediately-visible state."""
    from app.market_data import MarketDataService

    if _screen_state["running"]:
        return {"status": "already_running"}
    _screen_state["running"] = True
    try:
        uni = await asyncio.to_thread(alert_scanner.universe)
        targets = {s.upper(): uni.get(s.upper(), {}) for s in symbols} \
            if symbols else uni
        env, card = await asyncio.to_thread(_current_env)
        regime = _neutral_regime()
        svc = MarketDataService()
        from app.symbol_overlay import persisted_overlay, estimate_refresh_triggers
        from app.fundamental_intelligence.store import FundamentalEstimateStore
        # one bulk read per table — replaces ~170 per-symbol watermark
        # queries that used to run on the event loop
        overlay, triggered, as_ofs = await asyncio.gather(
            asyncio.to_thread(persisted_overlay, list(targets.keys())),
            asyncio.to_thread(estimate_refresh_triggers, list(targets.keys())),
            asyncio.to_thread(FundamentalEstimateStore().latest_as_of_batch,
                              list(targets)))
        spy_bars = await svc.get_ohlcv(
            "SPY", period="1y", prefer=["fmp", "yahoo_finance"])

        # pre-warm the OHLCV cache in one I/O burst — on a cache-miss day
        # the per-symbol pass below then overlaps analysis threads with
        # only the estimate/price-target fetches still on the wire
        wsem = asyncio.Semaphore(16)

        async def _warm(sym):
            async with wsem:
                try:
                    await svc.get_ohlcv(sym, period="1y")
                except Exception:
                    pass

        await asyncio.gather(*(_warm(s) for s in targets))

        sem = asyncio.Semaphore(max_concurrency)
        results: list[dict] = []
        errors: list[str] = []

        async def one(sym, flags):
            async with sem:
                try:
                    row = await _screen_symbol(sym, flags, spy_bars,
                                               regime, env, svc, overlay,
                                               refresh_estimates=sym in triggered,
                                               est_as_of=as_ofs.get(sym))
                    if row:
                        results.append(row)
                except Exception as exc:
                    errors.append(f"{sym}: {exc}")

        await asyncio.gather(*(one(s, f) for s, f in targets.items()))

        results.sort(key=lambda r: (r["practice"], r["score"]), reverse=True)
        _screen_state["results"] = results
        _screen_state["errors"] = errors
        try:
            from app.database import db

            def _persist():
                prev = db.execute_query(
                    "SELECT results FROM screen_runs ORDER BY ran_at DESC LIMIT 1")
                prev_items = prev[0]["results"] if prev else []
                breadth = _breadth_of(results, prev_items)
                db.execute_update(
                    "INSERT INTO screen_runs (result_count, errors, results, breadth) "
                    "VALUES (:n, CAST(:errors AS jsonb), CAST(:results AS jsonb), "
                    "CAST(:breadth AS jsonb))",
                    {"n": len(results), "errors": json.dumps(errors),
                     "results": json.dumps(results),
                     "breadth": json.dumps(breadth)},
                )
            await asyncio.to_thread(_persist)
        except Exception as exc:
            logger.debug("screen run persist failed: %s", exc)
        try:
            await asyncio.to_thread(_update_breakout_watch, results)
        except Exception as exc:
            logger.debug("breakout watch update failed: %s", exc)
        return {"status": "completed", "count": len(results)}
    finally:
        _screen_state["running"] = False
        _screen_state["last_run_at"] = datetime.now(timezone.utc).isoformat()


def results() -> dict[str, Any]:
    items = _screen_state["results"]
    as_of = _screen_state["last_run_at"]
    errors = _screen_state["errors"]
    if not items:
        # Memory was wiped (restart) — fall back to the last persisted run.
        try:
            from app.database import db
            row = db.execute_query(
                "SELECT ran_at, results, errors FROM screen_runs "
                "ORDER BY ran_at DESC LIMIT 1")
            if row:
                items = row[0]["results"] or []
                errors = row[0]["errors"] or []
                ran = row[0]["ran_at"]
                as_of = ran.isoformat() if hasattr(ran, "isoformat") else str(ran)
        except Exception:
            pass
    # canonical momentum flag where the candidate is a tracked symbol —
    # context column only. The swing engine's own fine-grained regime
    # (allowed/restricted/turn + pattern) stays authoritative for setup
    # eligibility — episodic_pivot is deliberately counter-trend.
    mom = {}
    try:
        syms = [i.get("symbol") for i in items if i.get("symbol")]
        if syms:
            from app.database import db
            mom = {r["symbol"]: r["momentum_state"]
                   for r in db.execute_query(
                       "SELECT symbol, momentum_state FROM stocks "
                       "WHERE symbol = ANY(:s) AND momentum_state "
                       "IS NOT NULL", {"s": syms})}
    except Exception:
        pass
    for i in items:
        i["momentum"] = mom.get(i.get("symbol"))
    return {
        "as_of": as_of,
        "count": len(items),
        "items": items,
        "errors": errors,
    }


def history(limit: int = 30) -> list[dict[str, Any]]:
    from app.database import db
    return db.execute_query(
        "SELECT id, ran_at, result_count FROM screen_runs "
        "ORDER BY ran_at DESC LIMIT :n", {"n": limit})


def run_results(run_id: str) -> Optional[dict[str, Any]]:
    from app.database import db
    rows = db.execute_query(
        "SELECT id, ran_at, result_count, results, errors "
        "FROM screen_runs WHERE id = :id", {"id": run_id})
    if not rows:
        return None
    r = rows[0]
    ran = r["ran_at"]
    return {
        "id": str(r["id"]),
        "as_of": ran.isoformat() if hasattr(ran, "isoformat") else str(ran),
        "count": r["result_count"],
        "items": r["results"] or [],
        "errors": r["errors"] or [],
    }


# --- Breakout watch ---------------------------------------------------------
# Two-stage breakout capture: the EOD scan populates candidates sitting just
# under their 20d high (the pivot); an intraday check compares live quotes to
# the pivot and alerts the hour it crosses — instead of the breakout only
# appearing "ready" at next day's EOD scan, after the move.

BREAKOUT_WATCH_WINDOW = -0.05   # within 5% below the pivot
BREAKOUT_APPROACH_PCT = -0.01   # within 1% = heads-up alert


def _update_breakout_watch(items: list[dict[str, Any]]) -> None:
    """Maintain breakout_watch from a completed scan.

    - watching  : allowed/limited, not falling knife, within 5% below pivot
    - triggered : setup fired 'breakout' today (EOD confirmation path)
    - expired   : no longer qualifies
    A triggered symbol that pulls back under the pivot and re-qualifies is
    re-watched — second attempts at a level are a real pattern.
    """
    from app.database import db

    watching, fired = [], []
    for r in items:
        dd, pivot = r.get("dd20"), r.get("pivot")
        if pivot is None or dd is None:
            continue
        if r.get("setup_type") == "breakout":
            fired.append(r)
        elif (r.get("stock_permission") in {"allowed", "limited"}
              and not r.get("falling_knife")
              and BREAKOUT_WATCH_WINDOW <= dd < 0
              and (r.get("score") or 0) >= 55):
            watching.append(r)

    keep = {r["symbol"] for r in watching + fired}
    for r in watching:
        db.execute_update(
            """
            INSERT INTO breakout_watch (symbol, pivot, score, setup_type,
                                        last_price, distance_pct)
            VALUES (:s, :pivot, :score, :setup, :px, :dist)
            ON CONFLICT (symbol) DO UPDATE SET
                pivot = EXCLUDED.pivot, score = EXCLUDED.score,
                setup_type = EXCLUDED.setup_type,
                last_price = EXCLUDED.last_price,
                distance_pct = EXCLUDED.distance_pct,
                status = CASE WHEN breakout_watch.status = 'triggered'
                              AND breakout_watch.triggered_at::date = now()::date
                              THEN 'triggered' ELSE 'watching' END,
                days_on_watch = CASE WHEN breakout_watch.status = 'watching'
                                     THEN breakout_watch.days_on_watch + 1
                                     ELSE 1 END,
                added_at = CASE WHEN breakout_watch.status = 'watching'
                                THEN breakout_watch.added_at ELSE now() END,
                updated_at = now()
            """,
            {"s": r["symbol"], "pivot": r["pivot"], "score": r.get("score"),
             "setup": r.get("setup_type"), "px": r.get("price"),
             "dist": round((r["price"] / r["pivot"] - 1) * 100, 2)
                     if r.get("price") and r["pivot"] else None},
        )
    for r in fired:
        db.execute_update(
            """
            INSERT INTO breakout_watch (symbol, pivot, score, setup_type,
                                        last_price, distance_pct, status,
                                        triggered_at, trigger_price)
            VALUES (:s, :pivot, :score, 'breakout', :px, :dist,
                    'triggered', now(), :px)
            ON CONFLICT (symbol) DO UPDATE SET
                pivot = EXCLUDED.pivot, score = EXCLUDED.score,
                last_price = EXCLUDED.last_price,
                status = 'triggered',
                triggered_at = COALESCE(breakout_watch.triggered_at, now()),
                trigger_price = COALESCE(breakout_watch.trigger_price,
                                         EXCLUDED.trigger_price),
                updated_at = now()
            """,
            {"s": r["symbol"], "pivot": r["pivot"], "score": r.get("score"),
             "px": r.get("price"),
             "dist": round((r["price"] / r["pivot"] - 1) * 100, 2)
                     if r.get("price") and r["pivot"] else None},
        )
    if keep:
        db.execute_update(
            "UPDATE breakout_watch SET status = 'expired', updated_at = now() "
            "WHERE status = 'watching' AND symbol != ALL(:syms)",
            {"syms": list(keep)})
    else:
        db.execute_update(
            "UPDATE breakout_watch SET status = 'expired', updated_at = now() "
            "WHERE status = 'watching'")


def breakout_watch_rows() -> list[dict[str, Any]]:
    from app.database import db
    return db.execute_query(
        """
        SELECT symbol, pivot, score, setup_type, added_at, last_price,
               last_checked_at, distance_pct, status, triggered_at,
               trigger_price, days_on_watch
        FROM breakout_watch
        WHERE status = 'watching'
           OR (status = 'triggered' AND triggered_at >= now() - interval '3 days')
        ORDER BY CASE status WHEN 'triggered' THEN 0 ELSE 1 END,
                 distance_pct DESC NULLS LAST
        """)


async def check_breakout_triggers(svc=None) -> dict[str, Any]:
    """Intraday quote check — the "starting the breakout" alert.

    For each watching symbol: quote >= pivot → 'breakout_trigger' alert +
    status triggered; within 1% → 'breakout_approach' heads-up. Fingerprints
    dedup per day. Runs at the tail of the scheduled alert scan (hourly
    during market hours) and from the page's refresh button.
    """
    from app.alerts.models import AlertItem
    from app.alerts.scanner import persist
    from app.database import db
    from app.market_data import MarketDataService

    svc = svc or MarketDataService()
    rows = db.execute_query(
        "SELECT symbol, pivot, score FROM breakout_watch "
        "WHERE status = 'watching'")
    if not rows:
        return {"checked": 0, "triggered": 0, "alerts": 0}

    uni = alert_scanner.universe()

    async def px(sym: str):
        try:
            q = await svc.get_quote(sym)
            return sym, (float(q.price) if q and q.price else None)
        except Exception:
            return sym, None

    quotes = dict(await asyncio.gather(*(px(r["symbol"]) for r in rows)))
    today = date.today()
    items, triggered = [], 0
    for r in rows:
        sym, pivot = r["symbol"], float(r["pivot"])
        price = quotes.get(sym)
        if not price or not pivot:
            continue
        dist = price / pivot - 1
        flags = uni.get(sym) or {}
        if price >= pivot:
            triggered += 1
            items.append(AlertItem(
                symbol=sym, event_type="breakout_trigger",
                direction="POSITIVE", materiality="HIGH",
                title=f"{sym} crossing pivot ${pivot:.2f} — breakout starting",
                detail={"pivot": pivot, "price": round(price, 2),
                        "distance_pct": round(dist * 100, 2),
                        "watch_score": r.get("score")},
                fingerprint=f"brk_trigger:{sym}:{today.isoformat()}",
                source="breakout_watch",
                source_timestamp=datetime.now(timezone.utc),
                in_portfolio=bool(flags.get("in_portfolio")),
                in_watchlist=bool(flags.get("in_watchlist")),
                priority_score=75.0))
            db.execute_update(
                "UPDATE breakout_watch SET status='triggered', "
                "triggered_at=now(), trigger_price=:px, last_price=:px, "
                "distance_pct=:d, last_checked_at=now(), updated_at=now() "
                "WHERE symbol=:s",
                {"s": sym, "px": price, "d": round(dist * 100, 2)})
        else:
            if dist >= BREAKOUT_APPROACH_PCT:
                items.append(AlertItem(
                    symbol=sym, event_type="breakout_approach",
                    direction="POSITIVE", materiality="MODERATE",
                    title=f"{sym} within {abs(dist)*100:.1f}% of pivot ${pivot:.2f}",
                    detail={"pivot": pivot, "price": round(price, 2),
                            "distance_pct": round(dist * 100, 2),
                            "watch_score": r.get("score")},
                    fingerprint=f"brk_approach:{sym}:{today.isoformat()}",
                    source="breakout_watch",
                    source_timestamp=datetime.now(timezone.utc),
                    in_portfolio=bool(flags.get("in_portfolio")),
                    in_watchlist=bool(flags.get("in_watchlist")),
                    priority_score=45.0))
            db.execute_update(
                "UPDATE breakout_watch SET last_price=:px, distance_pct=:d, "
                "last_checked_at=now(), updated_at=now() WHERE symbol=:s",
                {"s": sym, "px": price, "d": round(dist * 100, 2)})
    inserted, _ = persist(items)
    return {"checked": len(rows), "triggered": triggered, "alerts": inserted}


# --- Breadth + run-diff -----------------------------------------------------
# Every run is a full-universe regime census — consecutive runs become a
# market-breadth series and a per-symbol trajectory diff.

def _breadth_of(items: list[dict], prev_items: Optional[list[dict]] = None) -> dict[str, Any]:
    """Regime census for one run; deltas vs the previous run when available."""
    def _down(r):
        return bool(r.get("falling_knife")) or \
            r.get("stock_permission") in {"restricted", "disabled"}

    n = len(items) or 1
    up_syms = {r["symbol"] for r in items if r.get("stock_permission") == "allowed"}
    down_syms = {r["symbol"] for r in items if _down(r)}
    b: dict[str, Any] = {
        "universe": len(items),
        "uptrend_pct": round(len(up_syms) / n * 100, 1),
        "downtrend_pct": round(len(down_syms) / n * 100, 1),
        "turning": sum(1 for r in items if r.get("turn_candidate")),
    }
    if prev_items:
        pn = len(prev_items) or 1
        prev_up = {r["symbol"] for r in prev_items
                   if r.get("stock_permission") == "allowed"}
        prev_down = {r["symbol"] for r in prev_items
                     if r.get("falling_knife")
                     or r.get("stock_permission") in {"restricted", "disabled"}}
        b["uptrend_delta"] = round(
            len(up_syms) / n * 100 - len(prev_up) / pn * 100, 1)
        b["new_uptrends"] = sorted(up_syms - prev_up)
        b["new_downtrends"] = sorted(down_syms - prev_down)
        # Breadth thrust: a rapid breadth improvement — historically one of
        # the stronger market-level buy signals.
        b["thrust"] = bool(
            (b["uptrend_delta"] or 0) >= 8
            or len(b["new_uptrends"]) / n >= 0.10)
    return b


def breadth_history(limit: int = 60) -> dict[str, Any]:
    """The breadth series across runs — newest last for charting."""
    from app.database import db
    rows = db.execute_query(
        "SELECT ran_at, breadth, result_count FROM screen_runs "
        "ORDER BY ran_at DESC LIMIT :n", {"n": limit})
    series = []
    for r in reversed(rows):
        b = r.get("breadth") or {}
        series.append({
            "ran_at": r["ran_at"].isoformat()
                      if hasattr(r["ran_at"], "isoformat") else str(r["ran_at"]),
            "count": r["result_count"],
            **b,
        })
    return {"history": series,
            "current": series[-1] if series else None}


_PERM_RANK = {"disabled": 0, "restricted": 1, "limited": 2, "allowed": 3}


def run_diff() -> dict[str, Any]:
    """Latest run vs previous — who's improving, who's deteriorating, and
    regime migrations. The trajectory read: setups forming before they fire."""
    from app.database import db
    runs = db.execute_query(
        "SELECT ran_at, results FROM screen_runs "
        "ORDER BY ran_at DESC LIMIT 2")
    if len(runs) < 2:
        return {"available": False}
    cur = {r["symbol"]: r for r in runs[0]["results"] or []}
    prev = {r["symbol"]: r for r in runs[1]["results"] or []}

    improving, deteriorating = [], []
    for sym, c in cur.items():
        p = prev.get(sym)
        if not p:
            improving.append({"symbol": sym, "note": "new to universe",
                              "score": c.get("score"),
                              "perm": c.get("stock_permission")})
            continue
        d_perm = _PERM_RANK.get(c.get("stock_permission"), -1) \
            - _PERM_RANK.get(p.get("stock_permission"), -1)
        d_score = (c.get("score") or 0) - (p.get("score") or 0)
        d_dd = None
        if c.get("dd20") is not None and p.get("dd20") is not None:
            d_dd = round((c["dd20"] - p["dd20"]) * 100, 1)
        rec = {"symbol": sym,
               "perm": f"{p.get('stock_permission')}→{c.get('stock_permission')}",
               "score": c.get("score"), "score_delta": round(d_score, 1),
               "dd20_delta": d_dd, "setup": c.get("setup_type"),
               "dist_to_pivot": round((c["dd20"]) * 100, 1)
                                if c.get("dd20") is not None else None}
        if d_perm > 0 or d_score >= 10 or (d_dd is not None and d_dd >= 3):
            improving.append(rec)
        elif d_perm < 0 or d_score <= -10 or (d_dd is not None and d_dd <= -3):
            deteriorating.append(rec)

    improving.sort(key=lambda r: (-(r.get("score_delta") or 0)))
    deteriorating.sort(key=lambda r: (r.get("score_delta") or 0))
    return {
        "available": True,
        "as_of": runs[0]["ran_at"].isoformat()
                 if hasattr(runs[0]["ran_at"], "isoformat") else str(runs[0]["ran_at"]),
        "improving": improving[:25],
        "deteriorating": deteriorating[:25],
        "approaching_pivot": [r for r in improving
                              if r.get("dist_to_pivot") is not None
                              and -5 <= r["dist_to_pivot"] < 0][:15],
    }
