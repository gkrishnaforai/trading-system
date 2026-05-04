from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import json

import pandas as pd

from app.database import db
from app.services.base import BaseService


@dataclass(frozen=True)
class TradingDecisionV2:
    symbol: str
    as_of_date: str
    state: str
    action: str
    confidence: float
    price: Optional[float]
    indicators: Dict[str, Any]
    entry: Dict[str, Any]
    risk: Dict[str, Any]
    reasons: List[str]


class TradingDecisionV2Service(BaseService):
    """EOD trading decision engine based on stored technicals.

    Produces a deterministic state + action with explainability and persists to the generic `signals` table.
    """

    ENGINE_NAME = "trading_decision_v2"
    SIGNAL_TYPE = "trading_decision_v2"

    def __init__(self):
        super().__init__()

    def run_for_symbol(self, symbol: str, *, as_of_date: Optional[str] = None) -> TradingDecisionV2:
        sym = (symbol or "").strip().upper()
        if not sym:
            raise ValueError("symbol is required")

        price_rows = self._get_recent_price_rows(sym, as_of_date=as_of_date, limit=80)
        if not price_rows:
            return TradingDecisionV2(
                symbol=sym,
                as_of_date=as_of_date or "",
                state="base",
                action="hold",
                confidence=0.0,
                price=None,
                indicators={},
                entry={},
                risk={},
                reasons=["missing_price_data"],
            )

        df = pd.DataFrame(price_rows)
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date")

        latest_date = str(df.iloc[-1]["date"].date())
        latest_close = self._safe_float(df.iloc[-1].get("close"))
        latest_volume = self._safe_float(df.iloc[-1].get("volume"))
        latest_open = self._safe_float(df.iloc[-1].get("open"))
        latest_high = self._safe_float(df.iloc[-1].get("high"))
        latest_low = self._safe_float(df.iloc[-1].get("low"))
        prev_close = self._safe_float(df.iloc[-2].get("close")) if len(df) >= 2 else None

        ind = self._get_latest_indicators(sym, latest_date)

        indicators_used: Dict[str, Any] = {
            "close": latest_close,
            "volume": latest_volume,
            "open": latest_open,
            "high": latest_high,
            "low": latest_low,
            "prev_close": prev_close,
            "rsi_14": self._safe_float(ind.get("rsi_14")) if ind else None,
            "ema_20": self._safe_float(ind.get("ema_20")) if ind else None,
            "sma_50": self._safe_float(ind.get("sma_50")) if ind else None,
            "sma_200": self._safe_float(ind.get("sma_200")) if ind else None,
            "atr": self._safe_float(ind.get("atr")) if ind else None,
        }

        # Compute volume ratio from raw volume history when available.
        avg_vol_20 = self._avg_volume(df, window=20)
        indicators_used["avg_volume_20d"] = avg_vol_20
        indicators_used["vol_ratio"] = (latest_volume / avg_vol_20) if (latest_volume is not None and avg_vol_20) else None

        # Location proxy: prior 20D high (resistance) / low (support).
        try:
            if len(df) >= 21:
                indicators_used["high_20_prev"] = float(df.iloc[-21:-1]["high"].max())
                indicators_used["low_20_prev"] = float(df.iloc[-21:-1]["low"].min())
        except Exception:
            indicators_used["high_20_prev"] = None
            indicators_used["low_20_prev"] = None

        state, reasons = self._detect_state(df, indicators_used)
        action, action_reasons = self._map_action(state, indicators_used)
        reasons.extend(action_reasons)

        reasons = self._dedupe_reasons(reasons)

        entry, risk = self._build_entry_and_risk(indicators_used)
        risk["risk_level"] = self._classify_risk(indicators_used)

        confidence = self._score_confidence(state, indicators_used)

        return TradingDecisionV2(
            symbol=sym,
            as_of_date=latest_date,
            state=state,
            action=action,
            confidence=confidence,
            price=latest_close,
            indicators=indicators_used,
            entry=entry,
            risk=risk,
            reasons=reasons,
        )

    def persist_decision(self, decision: TradingDecisionV2) -> None:
        """Persist decision to the generic `signals` table."""

        ts = datetime.now(timezone.utc)
        deduped_reasons = self._dedupe_reasons(list(decision.reasons or []))

        warnings: List[str] = []
        if decision.indicators.get("sma_50") is None:
            warnings.append("missing_sma50")
        if decision.indicators.get("sma_200") is None:
            warnings.append("missing_sma200")
        if decision.indicators.get("ema_20") is None:
            warnings.append("missing_ema20")

        extension_metrics = self._compute_extension_metrics(decision.indicators)
        extension_type = self._classify_extension_type(decision.indicators, extension_metrics, deduped_reasons)
        no_weakness_signal = self._compute_no_weakness_signal(decision.indicators, deduped_reasons)
        market_phase = self._classify_market_phase(decision.indicators, extension_metrics, deduped_reasons)

        payload_metadata = {
            "rules": [
                "Overbought ≠ exit. Only exit if structure breaks with confirmation.",
                "Respect structure over indicators. Break support → EXIT even if RSI looks fine.",
                "Volume confirms everything. No volume = no conviction.",
            ],
            "rsi_model": {
                "rsi_pullback_zone": "40-50",
                "rsi_trend_zone": "55-70",
                "rsi_strong_trend": "65-75",
                "rsi_extreme": ">75",
            },
            "state": decision.state,
            "action": decision.action,
            "as_of_date": decision.as_of_date,
            "entry": decision.entry,
            "risk": decision.risk,
            "no_weakness_signal": no_weakness_signal,
            "extension_metrics": extension_metrics,
            "extension_type": extension_type,
            "market_phase": market_phase,
            "warnings": warnings,
            "indicators": decision.indicators,
            "reasons": deduped_reasons,
        }

        insert_query = """
            INSERT INTO signals (
                symbol,
                signal_type,
                signal_value,
                confidence,
                price_at_signal,
                timestamp,
                engine_name,
                reasoning,
                metadata
            ) VALUES (
                :symbol,
                :signal_type,
                :signal_value,
                :confidence,
                :price_at_signal,
                :timestamp,
                :engine_name,
                :reasoning,
                :metadata
            )
            ON CONFLICT (symbol, signal_type, timestamp, engine_name)
            DO NOTHING
        """

        db.execute_update(
            insert_query,
            {
                "symbol": decision.symbol,
                "signal_type": self.SIGNAL_TYPE,
                "signal_value": decision.action,
                "confidence": float(decision.confidence),
                "price_at_signal": decision.price,
                "timestamp": ts,
                "engine_name": self.ENGINE_NAME,
                "reasoning": ";".join(deduped_reasons[:50]),
                "metadata": json.dumps(payload_metadata),
            },
        )

    def run_and_persist(self, symbols: List[str], *, as_of_date: Optional[str] = None) -> List[TradingDecisionV2]:
        out: List[TradingDecisionV2] = []
        for s in symbols:
            d = self.run_for_symbol(s, as_of_date=as_of_date)
            self.persist_decision(d)
            out.append(d)
        return out

    def get_latest_decision(self, symbol: str) -> Optional[Dict[str, Any]]:
        sym = (symbol or "").strip().upper()
        if not sym:
            return None
        q = """
            SELECT symbol, signal_value, confidence, price_at_signal, timestamp, metadata
            FROM signals
            WHERE symbol = :symbol
              AND signal_type = :signal_type
              AND engine_name = :engine_name
            ORDER BY timestamp DESC
            LIMIT 1
        """
        rows = db.execute_query(q, {"symbol": sym, "signal_type": self.SIGNAL_TYPE, "engine_name": self.ENGINE_NAME})
        if not rows:
            return None
        row = rows[0]
        return {
            "symbol": row.get("symbol"),
            "action": row.get("signal_value"),
            "confidence": float(row.get("confidence")) if row.get("confidence") is not None else None,
            "price": float(row.get("price_at_signal")) if row.get("price_at_signal") is not None else None,
            "timestamp": row.get("timestamp").isoformat() if row.get("timestamp") else None,
            "metadata": row.get("metadata"),
        }

    def _get_recent_price_rows(self, symbol: str, *, as_of_date: Optional[str], limit: int) -> List[Dict[str, Any]]:
        # Resolve as-of date to latest <= as_of_date when provided.
        if as_of_date:
            q = """
                SELECT date, open, high, low, close, volume
                FROM raw_market_data_daily
                WHERE symbol = :symbol
                  AND date <= CAST(:as_of_date AS date)
                ORDER BY date DESC
                LIMIT :limit
            """
            rows = db.execute_query(q, {"symbol": symbol, "as_of_date": as_of_date, "limit": limit})
        else:
            q = """
                SELECT date, open, high, low, close, volume
                FROM raw_market_data_daily
                WHERE symbol = :symbol
                ORDER BY date DESC
                LIMIT :limit
            """
            rows = db.execute_query(q, {"symbol": symbol, "limit": limit})

        return list(reversed(rows or []))

    def _get_latest_wide_indicators(self, symbol: str, as_of_date: str) -> Optional[Dict[str, Any]]:
        # Wide-format rows are identified by having at least one of the wide columns present.
        q = """
            SELECT *
            FROM indicators_daily
            WHERE symbol = :symbol
              AND date = CAST(:as_of_date AS date)
              AND interval = '1d'
              AND (rsi_14 IS NOT NULL OR ema_20 IS NOT NULL OR sma_50 IS NOT NULL OR sma_200 IS NOT NULL)
            ORDER BY updated_at DESC NULLS LAST, created_at DESC NULLS LAST
            LIMIT 1
        """
        rows = db.execute_query(q, {"symbol": symbol, "as_of_date": as_of_date})
        return rows[0] if rows else None

    def _get_latest_indicators(self, symbol: str, as_of_date: str) -> Optional[Dict[str, Any]]:
        """Return a dict of indicator fields for decisioning.

        Supports both:
        - wide-format columns (rsi_14, ema_20, sma_50, ...)
        - long-format rows (indicator_name, indicator_value)
        """
        # Prefer FMP long-format indicators when present so decisions align with the upstream source.
        # Fall back to wide/calculated indicators and then to any long-format indicators.
        fmp_long = self._get_latest_long_indicators(symbol, as_of_date, data_source="fmp_api")
        if fmp_long:
            return fmp_long

        try:
            wide = self._get_latest_wide_indicators(symbol, as_of_date)
            if wide:
                return wide
        except Exception:
            # If the DB schema does not have wide columns, this query can fail.
            wide = None

        return self._get_latest_long_indicators(symbol, as_of_date, data_source=None)

    def _get_latest_long_indicators(
        self, symbol: str, as_of_date: str, *, data_source: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        names = [
            "rsi_14",
            "ema_20",
            "sma_50",
            "sma_200",
            "atr",
            "macd",
            "macd_signal",
            "macd_hist",
        ]

        q = """
            SELECT indicator_name, indicator_value
            FROM indicators_daily
            WHERE symbol = :symbol
              AND date = CAST(:as_of_date AS date)
              AND interval = '1d'
              AND LOWER(indicator_name) = ANY(:names)
        """
        params: Dict[str, Any] = {"symbol": symbol, "as_of_date": as_of_date, "names": names}
        if data_source:
            q += "\n              AND data_source = :data_source"
            params["data_source"] = data_source
        try:
            rows = db.execute_query(q, params)
        except Exception:
            # Fallback for DB helpers that don't support array params.
            in_list = ",".join([f"'{n}'" for n in names])
            q2 = f"""
                SELECT indicator_name, indicator_value
                FROM indicators_daily
                WHERE symbol = :symbol
                  AND date = CAST(:as_of_date AS date)
                  AND interval = '1d'
                  AND LOWER(indicator_name) IN ({in_list})
            """
            params2: Dict[str, Any] = {"symbol": symbol, "as_of_date": as_of_date}
            if data_source:
                q2 += "\n                  AND data_source = :data_source"
                params2["data_source"] = data_source
            rows = db.execute_query(q2, params2)

        if not rows:
            return None

        out: Dict[str, Any] = {}
        for r in rows:
            k = (r.get("indicator_name") or "").lower()
            out[k] = r.get("indicator_value")

        return out

    def _detect_state(self, df: pd.DataFrame, ind: Dict[str, Any]) -> Tuple[str, List[str]]:
        reasons: List[str] = []

        close = ind.get("close")
        rsi = ind.get("rsi_14")
        ema20 = ind.get("ema_20")
        sma50 = ind.get("sma_50")
        vol_ratio = ind.get("vol_ratio")

        if close is None:
            return "base", ["missing_close"]

        pct_from_ema20 = None
        if ema20 not in (None, 0):
            pct_from_ema20 = (close - ema20) / ema20 * 100

        # ----------------------------
        # RSI CONTEXT
        # ----------------------------
        if rsi is not None:
            if rsi > 85:
                reasons.append("rsi_extreme")
            elif rsi > 75:
                reasons.append("rsi_strong")
            elif rsi >= 55:
                reasons.append("rsi_trend")
            elif rsi < 45:
                reasons.append("rsi_weak")

        # ----------------------------
        # EXTENSION
        # ----------------------------
        if pct_from_ema20 is not None:
            if pct_from_ema20 > 30:
                reasons.append("extreme_extension")
            elif pct_from_ema20 > 20:
                reasons.append("late_extension")
            elif pct_from_ema20 > 10:
                reasons.append("extended")

        # ----------------------------
        # CLIMAX (FIXED: STRICT + CONSISTENT)
        # ----------------------------
        if (
            pct_from_ema20 is not None
            and pct_from_ema20 > 25
            and vol_ratio is not None
            and vol_ratio > 1.8
        ):
            reasons.append("climax")
            reasons.append("volume_spike")
            return "climax", reasons

        # ----------------------------
        # BREAKDOWN (CLEAR STRUCTURE)
        # ----------------------------
        below_ema = ema20 is not None and close < ema20
        below_50 = sma50 is not None and close < sma50

        if below_ema and below_50:
            if vol_ratio is not None and vol_ratio > 1.5:
                reasons.append("distribution")
                reasons.append("heavy_volume")
                return "breakdown", reasons

            # still weak but not confirmed breakdown
            reasons.append("below_sma50")
            return "pullback", reasons

        # ----------------------------
        # BASE (REAL CONSOLIDATION ONLY)
        # ----------------------------
        if (
            pct_from_ema20 is not None
            and abs(pct_from_ema20) <= 3
            and vol_ratio is not None
            and vol_ratio < 0.8
            and rsi is not None
            and 45 <= rsi <= 60
        ):
            reasons.append("base_consolidation")
            return "base", reasons

        # ----------------------------
        # TREND vs PULLBACK (CRITICAL FIX)
        # ----------------------------
        if ema20 is not None:

            # ✅ STRONG TREND ONLY IF RSI CONFIRMS
            if close > ema20:
                if rsi is not None and rsi >= 55:
                    reasons.append("above_ema20")
                    return "trend", reasons

                # weak trend = actually pullback
                reasons.append("weak_trend_structure")
                return "pullback", reasons

            # below ema = pullback (not breakdown unless above triggered)
            if close < ema20:
                reasons.append("below_ema20")
                return "pullback", reasons

        # ----------------------------
        # FALLBACK
        # ----------------------------
        reasons.append("fallback")
        return "base", reasons

    def _map_action(self, state: str, ind: Dict[str, Any]) -> Tuple[str, List[str]]:
        reasons: List[str] = []

        rsi = ind.get("rsi_14")
        vol_ratio = ind.get("vol_ratio")
        close = ind.get("close")
        ema20 = ind.get("ema_20")
        sma50 = ind.get("sma_50")

        pct_from_ema20 = None
        if close is not None and ema20 not in (None, 0):
            pct_from_ema20 = (close - ema20) / ema20 * 100

        # ----------------------------
        # PULLBACK (SMART ADD ZONE)
        # ----------------------------
        if state == "pullback":
            # ----------------------------
            # TRUE RISK (only reduce here)
            # ----------------------------
            if sma50:
                pct_from_sma50 = (close - sma50) / sma50 * 100

                if pct_from_sma50 < -2:
                    if vol_ratio and vol_ratio > 1.3:
                        return "reduce", ["confirmed_breakdown_sma50"]
                    return "hold", ["minor_break_below_sma50"]

            # ----------------------------
            # DISTRIBUTION (early warning)
            # ----------------------------
            if vol_ratio and vol_ratio > 1.5 and close < ema20:
                return "reduce", ["distribution_pressure"]

            # ----------------------------
            # WEAK PULLBACK
            # ----------------------------
            if rsi and rsi < 45:
                return "hold", ["weak_pullback"]

            # ----------------------------
            # BEST SETUP (your edge)
            # ----------------------------
            if vol_ratio and vol_ratio < 1.0:
                return "add", ["constructive_pullback"]

            # ----------------------------
            # NORMAL PULLBACK
            # ----------------------------
            return "add_light", ["standard_pullback"]

        # ----------------------------
        # TREND (MOST IMPORTANT FIX)
        # ----------------------------
        if state == "trend":
            # ----------------------------
            # EXTREME EXTENSION (rare)
            # ----------------------------
            if pct_from_ema20 is not None and pct_from_ema20 > 25:
                if vol_ratio and vol_ratio > 1.5:
                    return "trim", ["climax_extension_with_volume"]
                return "trim_light", ["extended_trend_no_volume"]

            # ----------------------------
            # LATE EXTENSION (smart handling)
            # ----------------------------
            if pct_from_ema20 is not None and pct_from_ema20 > 12:
                if rsi and rsi > 75:
                    return "trim_light", ["late_extension_overbought"]
                return "hold", ["late_extension"]

            # ----------------------------
            # OVERBOUGHT (without extension)
            # ----------------------------
            if rsi and rsi > 75:
                return "hold", ["overbought_but_not_extended"]

            # ----------------------------
            # HEALTHY TREND
            # ----------------------------
            if vol_ratio and vol_ratio > 1.2:
                return "add_light", ["strong_trend_with_volume"]

            return "add_light", ["trend_continuation"]

        # ----------------------------
        # CLIMAX (TRUE EXIT ZONE)
        # ----------------------------
        if state == "climax":
            # Only aggressive trim when BOTH extension + volume
            if pct_from_ema20 and pct_from_ema20 > 30:
                return "trim", ["extreme_climax"]

            return "trim_light", ["early_climax"]

        # ----------------------------
        # BREAKDOWN (STRUCTURE FIRST)
        # ----------------------------
        if state == "breakdown":
            if sma50 and close < sma50:
                if vol_ratio and vol_ratio > 1.2:
                    return "exit", ["confirmed_breakdown"]
                return "reduce", ["weak_below_sma50"]

            return "reduce", ["early_breakdown"]

        # ----------------------------
        # BASE
        # ----------------------------
        if state == "base":
            return "hold", ["no_edge"]

        return "hold", []

    def _score_confidence(self, state: str, ind: Dict[str, Any]) -> float:
        # Simple deterministic confidence score from rule alignment.
        base = {
            "trend": 0.62,
            "pullback": 0.60,
            "breakdown": 0.70,
            "base": 0.55,
            "climax": 0.65,
        }.get(state, 0.55)

        rsi = ind.get("rsi_14")
        vol_ratio = ind.get("vol_ratio")

        bump = 0.0
        if state == "trend" and rsi is not None and 55 <= rsi <= 70:
            bump += 0.05
        if state == "breakdown" and vol_ratio is not None and vol_ratio >= 2.0:
            bump += 0.05

        return float(max(0.0, min(1.0, base + bump)))

    def _build_entry_and_risk(self, ind: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Build execution (entry) and risk metadata while keeping core action schema stable."""

        ema20 = ind.get("ema_20")
        sma50 = ind.get("sma_50")
        close = ind.get("close")

        entry: Dict[str, Any] = {
            "type": "pullback",
            "levels": [
                {
                    "ma": "ema20",
                    "priority": 1,
                    "label": "strong_trend_support",
                    "value": float(ema20) if ema20 is not None else None,
                },
                {
                    "ma": "sma50",
                    "priority": 2,
                    "label": "secondary_support",
                    "value": float(sma50) if sma50 is not None else None,
                },
            ],
        }

        risk: Dict[str, Any] = {
            # For now keep this conservative and deterministic: SMA50 break is trend risk.
            "invalid_level": float(sma50) if sma50 is not None else None,
        }

        # If the stock is already below SMA50, signal elevated risk explicitly.
        if close is not None and sma50 is not None and close < sma50:
            risk["trend_risk"] = True

        return entry, risk

    def _classify_risk(self, ind: Dict[str, Any]) -> str:
        close = ind.get("close")
        ema20 = ind.get("ema_20")
        rsi = ind.get("rsi_14")

        if close and ema20:
            pct = (close - ema20) / ema20 * 100

            if pct > 30 or (rsi and rsi > 85):
                return "extreme"

            if pct > 20 or (rsi and rsi > 75):
                return "high"

            if abs(pct) < 5:
                return "low"

        return "medium"

    def _dedupe_reasons(self, reasons: List[str]) -> List[str]:
        seen = set()
        out: List[str] = []
        for r in reasons:
            if r in seen:
                continue
            seen.add(r)
            out.append(r)
        return out

    def _compute_extension_metrics(self, ind: Dict[str, Any]) -> Dict[str, Any]:
        close = ind.get("close")
        ema20 = ind.get("ema_20")
        sma50 = ind.get("sma_50")

        def pct_from(level: Optional[float]) -> Optional[float]:
            try:
                if close is None or level in (None, 0):
                    return None
                return float((close - level) / level * 100.0)
            except Exception:
                return None

        return {
            "pct_from_ema20": pct_from(ema20),
            "pct_from_sma50": pct_from(sma50),
        }

    def _compute_no_weakness_signal(self, ind: Dict[str, Any], reasons: List[str]) -> bool:
        """True when no obvious weakness flags are present given current signals."""
        close = ind.get("close")
        ema20 = ind.get("ema_20")
        sma50 = ind.get("sma_50")

        if close is None:
            return False
        if ema20 is not None and close < ema20:
            return False
        if sma50 is not None and close < sma50:
            return False
        if "structure_weak" in reasons or "breakdown_20d" in reasons:
            return False
        return True

    def _classify_extension_type(
        self,
        ind: Dict[str, Any],
        extension_metrics: Dict[str, Any],
        reasons: List[str],
    ) -> str:
        """Classify extension type: controlled / momentum / parabolic.

        Deterministic heuristic using only EOD inputs we already have.
        """
        rsi = ind.get("rsi_14")
        vol_ratio = ind.get("vol_ratio")
        pct_from_ema20 = extension_metrics.get("pct_from_ema20")
        pct_from_sma50 = extension_metrics.get("pct_from_sma50")

        has_exhaustion = any(
            r in reasons
            for r in (
                "climax_volume",
                "rejection_near_resistance",
                "reversal_candle",
            )
        )

        # Momentum/parabolic should not be triggered by RSI alone.
        # Require an acceleration/behavioral confirmation: elevated volume or an exhaustion marker.
        has_acceleration = bool(vol_ratio is not None and vol_ratio >= 1.5) or has_exhaustion

        # Parabolic: very extended + clear exhaustion marker or extreme volume.
        if (
            (vol_ratio is not None and vol_ratio >= 2.0)
            or has_exhaustion
        ) and (
            (pct_from_ema20 is not None and pct_from_ema20 >= 20.0)
            or (pct_from_sma50 is not None and pct_from_sma50 >= 25.0)
        ):
            return "parabolic"

        # Momentum: crowded trade, extended but not blow-off.
        if has_acceleration and (rsi is not None and rsi > 75) and (
            (pct_from_ema20 is not None and pct_from_ema20 >= 10.0)
            or (pct_from_sma50 is not None and pct_from_sma50 >= 15.0)
        ):
            return "momentum"

        return "controlled"

    def _classify_market_phase(
        self,
        ind: Dict[str, Any],
        extension_metrics: Dict[str, Any],
        reasons: List[str],
    ) -> str:
        """Human-friendly market phase aligned with action + state logic."""

        close = ind.get("close")
        ema20 = ind.get("ema_20")
        vol_ratio = ind.get("vol_ratio")
        pct_from_ema20 = extension_metrics.get("pct_from_ema20")

        if close is None:
            return "consolidation"

        # ----------------------------
        # EXTENSION / CLIMAX (TOP PRIORITY)
        # ----------------------------
        if pct_from_ema20 is not None:
            # TRUE CLIMAX → exhaustion
            if pct_from_ema20 > 25:
                if vol_ratio is not None and vol_ratio > 1.8:
                    return "climax_exhaustion"   # 🔥 real blow-off
                return "extended_trend"         # extended but healthy

            # MOMENTUM ZONE
            if pct_from_ema20 > 15:
                if vol_ratio is not None and vol_ratio >= 1.5:
                    return "momentum_trend"
                return "late_trend"

            # EARLY / HEALTHY TREND
            if pct_from_ema20 > 3:
                if vol_ratio is not None and vol_ratio < 1.0:
                    return "low_volume_uptrend"
                return "healthy_trend"

        # ----------------------------
        # EMA LOCATION LOGIC
        # ----------------------------
        if close is not None and ema20 is not None:
            # ABOVE EMA → TREND CONTEXT
            if close > ema20:
                if vol_ratio < 0.8:
                    return "low_volume_uptrend"
                elif 0.8 <= vol_ratio <= 1.2:
                    return "healthy_trend"
                else:
                    return "high_volume_trend"

            # BELOW EMA → WEAKNESS
            if close < ema20:
                if vol_ratio is not None and vol_ratio > 1.5:
                    return "distribution"   # 🔴 institutional selling
                return "pullback"

        # ----------------------------
        # FALLBACK
        # ----------------------------
        return "consolidation"

    def _avg_volume(self, df: pd.DataFrame, window: int = 20) -> Optional[float]:
        try:
            if "volume" not in df.columns or len(df) < 5:
                return None
            s = pd.to_numeric(df["volume"], errors="coerce").dropna()
            if s.empty:
                return None
            return float(s.tail(window).mean())
        except Exception:
            return None

    def _safe_float(self, x: Any) -> Optional[float]:
        try:
            if x is None:
                return None
            v = float(x)
            if pd.isna(v):
                return None
            return v
        except Exception:
            return None
