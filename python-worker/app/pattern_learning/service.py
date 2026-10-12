"""Signal capture, outcome evaluation, and bounded score calibration."""
from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime, timezone
from typing import Any, Optional

from app.database import db

logger = logging.getLogger(__name__)

HORIZONS = (5, 10, 20)
MIN_SAMPLE = 20
MAX_ADJUSTMENT = 8.0
_STATS_TTL_S = 900
_stats_cache: dict[str, Any] = {"at": 0.0, "rows": []}


def record_signal(result: dict[str, Any], *, source: str, run_id: Optional[str]) -> None:
    """Persist one setup signal per swing review (dedup: symbol+type+date).

    Records whenever a real setup was detected — even if the decision was
    WAIT — because the learning target is *pattern* quality, not trade logs.
    """
    setup = result.get("setup") or {}
    setup_type = setup.get("type") or "no_setup"
    if setup_type == "no_setup" or setup.get("falling_knife"):
        return

    stock = result.get("stock") or {}
    tech = stock.get("technicals") or {}
    risk = result.get("risk") or {}
    decision = result.get("decision") or {}
    env = (result.get("event_aware_swing_environment")
           or result.get("swing_environment") or {})
    regime = result.get("market_regime") or {}
    symbol = (result.get("symbol") or (result.get("opportunity") or {}).get("symbol") or "").upper()
    if not symbol:
        return

    price = tech.get("price")
    entry = risk.get("entry") or price
    stop = risk.get("stop")
    target = risk.get("target")
    atr_pct = tech.get("atr_pct")
    if entry and not stop and atr_pct:
        stop = entry - 2 * atr_pct * entry
    if entry and not target and stop:
        target = entry + 2 * (entry - stop)
    if not entry or not stop or entry <= stop:
        return  # no measurable outcome without a defined stop

    today = date.today().isoformat()
    fingerprint = f"sig:{symbol}:{setup_type}:{today}"
    db.execute_update(
        """
        INSERT INTO setup_signals
            (symbol, signal_date, setup_type, detected_patterns, price, entry,
             stop, target, reward_risk, atr_pct, regime, long_permission,
             size_multiplier, decision_action, risk_status, features,
             source, run_id, fingerprint)
        VALUES (:symbol, :signal_date, :setup_type, :detected_patterns, :price,
                :entry, :stop, :target, :reward_risk, :atr_pct, :regime,
                :long_permission, :size_multiplier, :decision_action,
                :risk_status, :features, :source, :run_id, :fingerprint)
        ON CONFLICT (fingerprint) DO NOTHING
        """,
        {
            "symbol": symbol, "signal_date": today, "setup_type": setup_type,
            "detected_patterns": list(setup.get("detected_patterns") or []),
            "price": price, "entry": entry, "stop": stop, "target": target,
            "reward_risk": risk.get("reward_risk"), "atr_pct": atr_pct,
            "regime": regime.get("regime") or regime.get("label") if isinstance(regime, dict) else str(regime),
            "long_permission": env.get("long_permission"),
            "size_multiplier": env.get("size_multiplier"),
            "decision_action": decision.get("action"),
            "risk_status": decision.get("risk_status") or risk.get("status"),
            "features": json.dumps({
                "rsi": tech.get("rsi"), "rsi2": tech.get("rsi2"),
                "volume_ratio": tech.get("volume_ratio"),
                "drawdown20": tech.get("drawdown20"),
                "trend_turn_bars": tech.get("trend_turn_bars"),
                "vs_spy20": (stock.get("relative_strength") or {}).get("vs_spy20"),
                "setup_score": setup.get("score"),
                "stock_permission": setup.get("stock_permission"),
            }),
            "source": source, "run_id": run_id, "fingerprint": fingerprint,
        },
    )


async def evaluate_outcomes(service=None, *, horizons=HORIZONS) -> dict[str, int]:
    """Fill forward outcomes for signals that have enough bars since signal_date.

    Walk each bar after the signal: stop hit → 'stop' (-1R basis), target hit
    → 'target', else exit at horizon close → 'horizon_close'. Conservative on
    same-bar ambiguity: stop is assumed to fill before target.
    """
    from app.market_data import MarketDataService

    svc = service or MarketDataService()
    rows = db.execute_query(
        """
        SELECT s.id, s.symbol, s.signal_date, s.entry, s.stop, s.target
        FROM setup_signals s
        WHERE s.signal_date <= :cutoff
          AND NOT EXISTS (
              SELECT 1 FROM setup_outcomes o
              WHERE o.signal_id = s.id AND o.horizon_bars = :max_h
          )
        ORDER BY s.signal_date DESC
        LIMIT 500
        """,
        {"cutoff": date.today().isoformat(), "max_h": max(horizons)},
    )
    done, errors = 0, []
    for sig in rows:
        try:
            sig_date = sig["signal_date"]
            if isinstance(sig_date, str):
                sig_date = date.fromisoformat(sig_date)
            bars = await svc.get_ohlcv(
                sig["symbol"], start=sig_date, interval="1d",
            )
            forward = [b for b in bars if b.timestamp.date() > sig_date]
            if not forward:
                continue
            entry, stop, target = sig["entry"], sig["stop"], sig["target"]
            risk = entry - stop
            for horizon in horizons:
                window = forward[:horizon]
                if len(window) < min(horizon, 3):
                    continue  # not enough bars to judge this horizon yet
                mfe = max((b.high - entry) / entry for b in window)
                mae = min((b.low - entry) / entry for b in window)
                exit_reason, exit_price, held = "horizon_close", window[-1].close, len(window)
                for i, b in enumerate(window):
                    if b.low <= stop:
                        exit_reason, exit_price, held = "stop", stop, i + 1
                        break
                    if target and b.high >= target:
                        exit_reason, exit_price, held = "target", target, i + 1
                        break
                db.execute_update(
                    """
                    INSERT INTO setup_outcomes
                        (signal_id, horizon_bars, exit_reason, exit_price,
                         mfe_pct, mae_pct, r_multiple, bars_held)
                    VALUES (:sid, :h, :reason, :exit_price, :mfe, :mae, :r, :held)
                    ON CONFLICT (signal_id, horizon_bars) DO NOTHING
                    """,
                    {"sid": sig["id"], "h": horizon, "reason": exit_reason,
                     "exit_price": exit_price, "mfe": mfe, "mae": mae,
                     "r": (exit_price - entry) / risk, "held": held},
                )
            done += 1
        except Exception as exc:
            logger.error("outcome eval failed for %s: %s", sig["symbol"], exc)
            errors.append(f"{sig['symbol']}: {exc}")
    return {"evaluated": done, "errors": len(errors), "error_list": errors[:20]}


def pattern_stats() -> list[dict[str, Any]]:
    return db.execute_query(
        "SELECT * FROM pattern_stats ORDER BY setup_type, horizon_bars"
    )


def _stats_rows() -> list[dict[str, Any]]:
    if time.time() - _stats_cache["at"] > _STATS_TTL_S:
        try:
            _stats_cache["rows"] = pattern_stats()
            _stats_cache["at"] = time.time()
        except Exception:
            pass  # keep stale cache on failure
    return _stats_cache["rows"]


def score_adjustment(setup_type: str) -> tuple[float, Optional[str]]:
    """Bounded score calibration from empirical stats — the learning feedback.

    Prefers the 10-bar horizon (matches swing holding period). Requires
    MIN_SAMPLE evaluated signals before adjusting at all.
    """
    if setup_type == "no_setup":
        return 0.0, None
    rows = [r for r in _stats_rows() if r["setup_type"] == setup_type]
    if not rows:
        return 0.0, None
    row = next((r for r in rows if r["horizon_bars"] == 10), rows[0])
    n = int(row["n"] or 0)
    if n < MIN_SAMPLE:
        return 0.0, None
    win_rate = float(row["win_rate"] or 0)
    avg_r = float(row["avg_r"] or 0)
    adj = max(-MAX_ADJUSTMENT, min(MAX_ADJUSTMENT,
                                 (win_rate - 0.5) * 20 + avg_r * 2))
    note = (f"empirical {setup_type}: n={n}, {win_rate:.0%} win, "
            f"{avg_r:+.2f}R avg → score {adj:+.0f}")
    return adj, note
