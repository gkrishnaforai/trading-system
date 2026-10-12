"""Alert service: inbox reads, swing-review orchestration, concise summaries."""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from app.database import db
from app.market_regime.context_store import MarketContextStore

from .models import AlertItem

logger = logging.getLogger(__name__)

MAX_AUTO_REVIEWS_PER_SCAN = 5
FRESH_REVIEW_HOURS = 24

# In-process scan job state (single uvicorn worker; a multi-worker deploy
# would need this in Redis instead).
_scan_state: dict[str, Any] = {
    "running": False,
    "last_run_at": None,
    "last_result": None,
    "last_error": None,
}


def scan_status() -> dict[str, Any]:
    return dict(_scan_state)


async def run_scan_job(lookback_days: float = 0.5, auto_review_enabled: bool = True,
                       max_reviews: int = MAX_AUTO_REVIEWS_PER_SCAN,
                       portfolio_only: bool = False) -> dict[str, Any]:
    """Background scan job: collect alerts, then auto-review qualifying ones."""
    from . import scanner

    if _scan_state["running"]:
        return {"status": "already_running", **_scan_state}
    _scan_state["running"] = True
    _scan_state["last_error"] = None
    try:
        # Freshness gap-cover: a scan after a quiet stretch (weekend, worker
        # down) looks back as far as the gap, so headlines that landed while
        # nobody was scanning aren't lost. Clamped: never below the normal
        # 12h window, never beyond 72h (stale news isn't a fresh alert).
        freshness = scanner.NEWS_FRESHNESS_HOURS
        last = _scan_state.get("last_run_at")
        if last:
            try:
                gap_h = (datetime.now(timezone.utc)
                         - datetime.fromisoformat(last)).total_seconds() / 3600
                freshness = int(min(72, max(freshness, gap_h)))
            except (ValueError, TypeError):
                pass
        new_items, skipped, errors, scanned = await scanner.scan(
            lookback_days=lookback_days, news_freshness_hours=freshness,
            portfolio_only=portfolio_only)
        reviews = 0
        if auto_review_enabled and new_items:
            reviews = await auto_review(new_items, max_reviews=max_reviews)
        try:
            outcome_eval = await evaluate_alert_outcomes()
        except Exception as exc:
            outcome_eval = {}
            logger.debug("alert outcome evaluation skipped: %s", exc)
        try:
            from app.screener.service import check_breakout_triggers
            breakout = await check_breakout_triggers()
        except Exception as exc:
            breakout = {}
            logger.debug("breakout trigger check skipped: %s", exc)
        try:
            from app.screener.quality import evaluate_mover_outcomes
            mover_eval = await evaluate_mover_outcomes()
        except Exception as exc:
            mover_eval = {}
            logger.debug("mover outcome evaluation skipped: %s", exc)
        try:
            from app.screener.pick_outcomes import evaluate_pick_outcomes
            pick_eval = await evaluate_pick_outcomes()
        except Exception as exc:
            pick_eval = {}
            logger.debug("pick outcome evaluation skipped: %s", exc)
        # Extended-hours boards — only meaningful inside their windows:
        # post ≈ 4:30–8pm ET (20:30–00:00 UTC), pre ≈ 7–9:30am ET
        # (11:00–13:30 UTC); yfinance carries the live fields then.
        ah = {}
        try:
            from datetime import datetime as _dt, timezone as _tz
            now_utc = _dt.now(_tz.utc)
            if now_utc.hour >= 20 or now_utc.hour < 1:
                from app.screener.afterhours import run_session_job
                ah = await run_session_job("post")
            elif 11 <= now_utc.hour <= 13:
                from app.screener.afterhours import run_session_job
                ah = await run_session_job("pre")
        except Exception as exc:
            logger.debug("extended-hours scan skipped: %s", exc)
        # PT watch — once per day at most (snapshots are per-date; the
        # table's UNIQUE(symbol, as_of) makes reruns idempotent anyway).
        ptw = {}
        try:
            from app.screener.pt_watch import run_pt_watch
            have_today = db.execute_query(
                "SELECT 1 FROM pt_snapshots WHERE as_of = current_date "
                "LIMIT 1")
            if not have_today:
                ptw = await run_pt_watch()
        except Exception as exc:
            logger.debug("pt watch skipped: %s", exc)
        # Analyst tape — event-level upgrades/downgrades/PT changes from
        # FMP's latest-news firehoses (2 calls, ~8h window). Runs every
        # scan; rows dedupe on fingerprint so reruns are cheap.
        try:
            from app.screener.analyst_tape import run_analyst_tape
            await run_analyst_tape()
        except Exception as exc:
            logger.debug("analyst tape skipped: %s", exc)
        # Level watch — names sitting within ~3% of a swing_low /
        # confirm_level / avwap get a 'decision level' ping; the
        # fingerprint dedupes to one per level per day.
        try:
            from app.signals.level_watch import run as _level_watch
            _level_watch()
        except Exception as exc:
            logger.debug("level watch skipped: %s", exc)
        # Rule Breakers — daily member eval (light); weekly universe
        # discovery auto-adds qualifying names.
        try:
            from app.screener.rule_breakers import (
                run_rule_breakers, discovery_due)
            await run_rule_breakers(discover=discovery_due())
        except Exception as exc:
            logger.debug("rule breakers skipped: %s", exc)
        _scan_state["last_result"] = {
            "scanned_symbols": scanned,
            "new_alerts": len(new_items),
            "duplicates_skipped": skipped,
            "reviews_triggered": reviews,
            "errors": errors,
            "outcomes_evaluated": outcome_eval.get("evaluated"),
            "mover_outcomes_evaluated": mover_eval.get("evaluated"),
            "breakout_triggers": breakout.get("triggered"),
            "afterhours": ah.get("scanned") if ah else None,
        }
    except Exception as exc:
        logger.error("alert scan job failed: %s", exc, exc_info=True)
        _scan_state["last_error"] = str(exc)
    finally:
        _scan_state["running"] = False
        _scan_state["last_run_at"] = datetime.now(timezone.utc).isoformat()
    return {"status": "completed", **_scan_state}


ALERT_OUTCOME_HORIZONS = (1, 5, 10)


async def evaluate_alert_outcomes(
    svc=None, horizons: tuple = ALERT_OUTCOME_HORIZONS,
) -> dict[str, int]:
    """Forward-return evaluation for persisted alerts — the honesty loop.

    For every alert old enough to have forward bars, entry = the mover
    alert's recorded price when present, else the alert-day close; then
    ret/mfe/mae per horizon. Runs at the tail of each scan so outcomes
    accumulate without a separate cron.
    """
    from app.market_data import MarketDataService

    svc = svc or MarketDataService()
    rows = db.execute_query(
        """
        SELECT a.id, a.symbol, a.created_at::date AS alert_date,
               a.detail->>'price' AS detail_price
        FROM alert_items a
        WHERE a.created_at <= :cutoff
          AND NOT EXISTS (
              SELECT 1 FROM alert_outcomes o
              WHERE o.alert_id = a.id AND o.horizon_days = :max_h
          )
        ORDER BY a.created_at DESC
        LIMIT 500
        """,
        {"cutoff": datetime.now(timezone.utc).isoformat(), "max_h": max(horizons)},
    )
    done, errors = 0, []
    for a in rows:
        try:
            bars = await svc.get_ohlcv(a["symbol"], start=a["alert_date"], interval="1d")
            if not bars:
                continue
            entry = float(a["detail_price"]) if a.get("detail_price") else float(bars[0].close)
            # Anchor on the entry bar's own date — a weekend alert's first bar
            # is Monday, and outcomes must be measured strictly after it.
            anchor_date = bars[0].timestamp.date()
            forward = [b for b in bars if b.timestamp.date() > anchor_date]
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
                    INSERT INTO alert_outcomes
                        (alert_id, horizon_days, entry_price, ret_pct, mfe_pct, mae_pct)
                    VALUES (:aid, :h, :entry, :ret, :mfe, :mae)
                    ON CONFLICT (alert_id, horizon_days) DO NOTHING
                    """,
                    {"aid": a["id"], "h": h, "entry": entry,
                     "ret": round(ret, 2), "mfe": round(mfe, 2), "mae": round(mae, 2)},
                )
            done += 1
        except Exception as exc:
            logger.error("alert outcome eval failed for %s: %s", a["symbol"], exc)
            errors.append(f"{a['symbol']}: {exc}")
    return {"evaluated": done, "errors": len(errors)}


def alert_stats() -> list[dict[str, Any]]:
    return db.execute_query(
        "SELECT * FROM alert_stats ORDER BY event_type, direction, horizon_days")


def regime_card(horizon: str = "swing") -> Optional[dict[str, Any]]:
    row = MarketContextStore().latest(date.today(), horizon)
    if not row:
        rows = db.execute_query(
            """
            SELECT snapshot, facts, regime, transition, strategy_environments,
                   event_context, event_reaction, as_of, session_date
            FROM market_context_snapshots
            WHERE horizon = :horizon AND rules_version = 'market-context-v1'
            ORDER BY as_of DESC LIMIT 1
            """,
            {"horizon": horizon},
        )
        row = rows[0] if rows else None
    if not row:
        return None
    regime = row.get("regime") or {}
    envs = row.get("strategy_environments") or {}
    env = (envs.get("base") or envs).get("swing") or {}
    return {
        "as_of": row["as_of"].isoformat() if isinstance(row.get("as_of"), datetime) else row.get("as_of"),
        "session_date": row["session_date"].isoformat() if isinstance(row.get("session_date"), date) else row.get("session_date"),
        "regime": regime.get("regime") or regime.get("label"),
        "regime_detail": regime,
        "swing_environment": env,
    }


def inbox(
    status: Optional[str] = None,
    symbol: Optional[str] = None,
    hours: int = 72,
    limit: int = 100,
) -> list[dict[str, Any]]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    rows = db.execute_query(
        """
        SELECT a.id, a.symbol, a.event_type, a.direction, a.materiality, a.title, a.detail,
               a.fingerprint, a.source, a.source_timestamp, a.in_portfolio, a.in_watchlist,
               a.status, a.priority_score, a.swing_run_id, a.swing_action, a.swing_summary,
               a.created_at, a.reviewed_at,
               s.momentum_state AS momentum, s.momentum_detail AS momentum_detail,
               s.fundamental_state AS fund_state, s.fundamental_risk AS fund_risk,
               s.fundamental_detail->>'alert' AS fund_alert
        FROM alert_items a
        LEFT JOIN stocks s ON s.symbol = a.symbol
        WHERE a.created_at >= :cutoff
          AND (CAST(:status AS text) IS NULL OR a.status = :status)
          AND (CAST(:symbol AS text) IS NULL OR a.symbol = :symbol)
        ORDER BY a.created_at DESC
        LIMIT :limit
        """,
        {"cutoff": cutoff, "status": status, "symbol": symbol, "limit": min(500, max(1, limit))},
    )
    from app.catalyst_intelligence.engine import rating_action
    for i in rows:
        d = i.get("detail") or {}
        i["rating_action"] = rating_action(
            i.get("title"), event_type=i.get("event_type") or "",
            action=d.get("action") or "", direction=i.get("direction") or "",
            prev_grade=d.get("prev_grade") or "",
            new_grade=d.get("new_grade") or "")
    return rows


def get_alert(alert_id: str) -> Optional[dict[str, Any]]:
    rows = db.execute_query(
        "SELECT * FROM alert_items WHERE id = :id", {"id": alert_id}
    )
    return rows[0] if rows else None


def dismiss_alert(alert_id: str) -> bool:
    return db.execute_update(
        "UPDATE alert_items SET status = 'dismissed' WHERE id = :id AND status = 'new'",
        {"id": alert_id},
    ) > 0


def _position_qty(symbol: str) -> float:
    rows = db.execute_query(
        """
        SELECT COALESCE(sum(pp.quantity), 0) AS qty
        FROM portfolio_positions pp JOIN stocks s ON s.id = pp.stock_id
        WHERE s.symbol = :symbol AND pp.quantity > 0
        """,
        {"symbol": symbol},
    )
    return float(rows[0]["qty"]) if rows else 0.0


def _fresh_review_exists(symbol: str, hours: int = FRESH_REVIEW_HOURS) -> bool:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    rows = db.execute_query(
        """
        SELECT 1 FROM alert_items
        WHERE symbol = :symbol AND swing_run_id IS NOT NULL AND reviewed_at >= :cutoff
        LIMIT 1
        """,
        {"symbol": symbol, "cutoff": cutoff},
    )
    return bool(rows)


def _risk_constraints() -> dict[str, Any]:
    """Latest account equity + live heat from the trade ledger — lets the
    risk gate actually size positions instead of vetoing on missing data."""
    out: dict[str, Any] = {}
    try:
        r = db.execute_query(
            "SELECT account_equity FROM portfolio_account_states "
            "ORDER BY as_of DESC LIMIT 1")
        if r and r[0]["account_equity"]:
            out["account_equity"] = float(r[0]["account_equity"])
    except Exception:
        pass
    try:
        r = db.execute_query(
            """
            SELECT count(*) AS n,
                   COALESCE(sum((t.entry_price - t.initial_stop) *
                       (t.shares - COALESCE((
                           SELECT sum(e.qty) FROM trade_exits e
                           WHERE e.trade_id = t.id), 0))), 0) AS open_risk
            FROM trades t
            WHERE t.status IN ('open', 'partial') AND t.user_id = 'manual'
              AND t.initial_stop IS NOT NULL
            """)
        if r:
            out["open_trades"] = int(r[0]["n"])
            equity = out.get("account_equity")
            if equity:
                out["current_portfolio_risk"] = float(r[0]["open_risk"]) / equity
    except Exception:
        pass
    return out


async def run_swing_review(symbol: str, *, source: str = "alert_review",
                           run_id: Optional[str] = None) -> dict[str, Any]:
    """In-process swing graph run — same path as POST /api/v1/agent-runs.

    Also records a setup signal for the pattern-learning loop.
    """
    from app.swing_opportunity import build_swing_opportunity_graph

    qty = _position_qty(symbol)
    result = await build_swing_opportunity_graph(use_llm=False).ainvoke({
        "symbol": symbol.upper(),
        "current_position": qty,
        "current_weight": None,
        "target_weight": None,
        "reconciliation_safe": True,
        "risk_constraints": _risk_constraints(),
    })
    try:
        from app.pattern_learning import record_signal
        record_signal(result, source=source, run_id=run_id)
    except Exception as exc:
        logger.warning("signal capture failed for %s: %s", symbol, exc)
    return result


def format_summary(item: AlertItem | dict, result: dict[str, Any]) -> str:
    """Concise deterministic message — LLM-free, built from structured output."""
    symbol = item["symbol"] if isinstance(item, dict) else item.symbol
    title = item["title"] if isinstance(item, dict) else item.title
    direction = item["direction"] if isinstance(item, dict) else item.direction
    arrow = {"POSITIVE": "▲", "NEGATIVE": "▼", "MIXED": "◆"}.get(direction, "●")

    if result.get("error"):
        return f"{symbol} {arrow} {title} | Swing review failed: {result['error']}"

    decision = result.get("decision") or {}
    action = decision.get("action", "N/A")
    reasons = decision.get("reasons") or []
    reason = reasons[0] if reasons else "no reason recorded"

    fundamentals = result.get("fundamentals") or {}
    valuation = fundamentals.get("valuation") or {}
    fv_pct = valuation.get("price_vs_base_fv_pct")

    env = result.get("event_aware_swing_environment") or result.get("swing_environment") or {}
    permission = env.get("long_permission") or env.get("permission") or ""
    multiplier = env.get("size_multiplier")

    parts = [f"{symbol} {arrow} {title}", f"Swing: {action} — {reason}"]
    if fv_pct is not None:
        parts.append(f"FV: {fv_pct:+.1f}% vs base ({decision.get('valuation_label', 'n/a')})")
    if decision.get("position_size_pct"):
        parts.append(f"size {decision['position_size_pct'] * 100:.0f}%")
    if permission:
        size_txt = f" {multiplier:g}×" if multiplier is not None else ""
        parts.append(f"regime: {permission}{size_txt}")
    return " | ".join(parts)


def _should_auto_review(item: AlertItem) -> bool:
    if item.materiality in {"HIGH", "MODERATE"}:
        return True
    return item.direction == "NEGATIVE" and item.in_portfolio


async def auto_review(
    new_items: list[AlertItem],
    max_reviews: int = MAX_AUTO_REVIEWS_PER_SCAN,
) -> int:
    """Run swing reviews for qualifying new alerts; link results back."""
    candidates = sorted(
        (i for i in new_items if _should_auto_review(i)),
        key=lambda i: i.priority_score or 0,
        reverse=True,
    )
    triggered = 0
    for item in candidates:
        if triggered >= max_reviews:
            break
        if _fresh_review_exists(item.symbol):
            continue
        run_id = uuid.uuid4().hex[:12]
        try:
            result = await run_swing_review(item.symbol, source="alert_auto", run_id=run_id)
            action = (result.get("decision") or {}).get("action")
            summary = format_summary(item, result)
            db.execute_update(
                """
                UPDATE alert_items
                SET status = 'reviewed', swing_run_id = :run_id,
                    swing_action = :action, swing_summary = :summary,
                    reviewed_at = now()
                WHERE id = :id
                """,
                {"run_id": run_id, "action": action, "summary": summary, "id": item.id},
            )
            triggered += 1
        except Exception as exc:
            logger.error("auto-review failed for %s: %s", item.symbol, exc)
    return triggered


_review_jobs: dict[str, dict[str, Any]] = {}


def review_status(alert_id: str) -> dict[str, Any]:
    return _review_jobs.get(alert_id) or {"status": "idle"}


async def _do_review(alert_id: str):
    """Background review — the swing graph can run >120s; the HTTP call
    returns instantly and the UI polls review_status."""
    _review_jobs[alert_id] = {"status": "running"}
    try:
        result = await _review_body(alert_id)
        _review_jobs[alert_id] = {"status": "done", "result": result}
    except Exception as exc:
        logger.error("review %s failed: %s", alert_id, exc)
        _review_jobs[alert_id] = {"status": "error", "error": str(exc)}


async def review_alert(alert_id: str) -> dict[str, Any]:
    """Kick the swing review as a background job (was: synchronous —
    timed out at 120s on heavy symbols)."""
    import asyncio
    row = get_alert(alert_id)
    if not row:
        raise KeyError(f"alert not found: {alert_id}")
    if _review_jobs.get(alert_id, {}).get("status") == "running":
        return {"status": "already_running", "alert_id": alert_id}
    asyncio.create_task(_do_review(alert_id))
    return {"status": "started", "alert_id": alert_id}


async def _review_body(alert_id: str) -> dict[str, Any]:
    """Synchronous review body — the actual work."""
    row = get_alert(alert_id)
    fields = {k: row[k] for k in AlertItem.model_fields if k in row}
    fields["id"] = str(fields["id"])
    item = AlertItem.model_validate(fields)
    run_id = uuid.uuid4().hex[:12]
    result = await run_swing_review(item.symbol, source="alert_review", run_id=run_id)
    action = (result.get("decision") or {}).get("action")
    summary = format_summary(item, result)
    db.execute_update(
        """
        UPDATE alert_items
        SET status = 'reviewed', swing_run_id = :run_id,
            swing_action = :action, swing_summary = :summary,
            reviewed_at = now()
        WHERE id = :id
        """,
        {"run_id": run_id, "action": action, "summary": summary, "id": alert_id},
    )
    return {"alert_id": alert_id, "swing_run_id": run_id, "action": action,
            "summary": summary, "result": result}
