from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import json

import pandas as pd

from app.database import db
from app.services.base import BaseService


@dataclass(frozen=True)
class FeatureSnapshot:
    close: float
    prev_close: Optional[float]
    ema20: Optional[float]
    sma50: Optional[float]
    sma50_trend_up: bool
    rsi: Optional[float]
    vol_ratio: Optional[float]
    pct_from_ema20: Optional[float]
    pct_from_sma50: Optional[float]
    day_change_pct: Optional[float]
    is_red_day: bool
    no_chase_zone: bool
    days_below_sma50: int
    reclaim_sma50: bool
    support_holding: bool
    above_ema20: bool
    below_ema20: bool
    below_sma50: bool
    vol_high: bool
    vol_low: bool


@dataclass(frozen=True)
class TradingDecisionV3:
    symbol: str
    as_of_date: str
    state: str
    phase: str
    extension: str
    action: str
    confidence: float
    price: Optional[float]
    features: Dict[str, Any]
    entry: Dict[str, Any]
    risk: Dict[str, Any]
    reasons: List[str]


class TradingDecisionV3Service(BaseService):
    ENGINE_NAME = "trading_decision_v3"
    SIGNAL_TYPE = "trading_decision_v3"

    def __init__(self):
        super().__init__()

    def run_for_symbol(self, symbol: str, *, as_of_date: Optional[str] = None) -> TradingDecisionV3:
        sym = (symbol or "").strip().upper()
        if not sym:
            raise ValueError("symbol is required")

        price_rows = self._get_recent_price_rows(sym, as_of_date=as_of_date, limit=80)
        if not price_rows:
            return TradingDecisionV3(
                symbol=sym,
                as_of_date=as_of_date or "",
                state="base",
                phase="consolidation",
                extension="controlled",
                action="hold",
                confidence=0.0,
                price=None,
                features={},
                entry={},
                risk={"risk_level": "medium"},
                reasons=["missing_price_data"],
            )

        df = pd.DataFrame(price_rows)
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date")

        latest_date = str(df.iloc[-1]["date"].date())
        latest_close = self._safe_float(df.iloc[-1].get("close"))
        latest_volume = self._safe_float(df.iloc[-1].get("volume"))
        prev_close = self._safe_float(df.iloc[-2].get("close")) if len(df) >= 2 else None

        ind = self._get_latest_indicators(sym, latest_date)
        low_20_prev: Optional[float] = None
        try:
            if len(df) >= 21 and "low" in df.columns:
                low_20_prev = float(pd.to_numeric(df.iloc[-21:-1]["low"], errors="coerce").dropna().min())
        except Exception:
            low_20_prev = None

        indicators_used: Dict[str, Any] = {
            "close": latest_close,
            "volume": latest_volume,
            "prev_close": prev_close,
            "rsi_14": self._safe_float(ind.get("rsi_14")) if ind else None,
            "ema_20": self._safe_float(ind.get("ema_20")) if ind else None,
            "sma_50": self._safe_float(ind.get("sma_50")) if ind else None,
            "low_20_prev": low_20_prev,
        }

        avg_vol_20 = self._avg_volume(df, window=20)
        indicators_used["avg_volume_20d"] = avg_vol_20
        indicators_used["vol_ratio"] = (
            (latest_volume / avg_vol_20)
            if (latest_volume is not None and avg_vol_20 not in (None, 0))
            else None
        )

        # DB-free SMA50 slope (institutional "rising support" proxy).
        # Uses the same df price history already loaded for the symbol.
        sma50_trend_up = False
        try:
            if "close" in df.columns:
                closes_series = pd.to_numeric(df["close"], errors="coerce")
                sma50_series = closes_series.rolling(window=50).mean()
                # "Institutional" definition: rising SMA50 over ~20 sessions.
                # With a 50-day SMA, you typically need ~70+ bars to reliably compare today vs 20 sessions ago.
                if len(sma50_series) >= 21:
                    sma50_today = sma50_series.iloc[-1]
                    sma50_20d_ago = sma50_series.iloc[-21]
                    if pd.notna(sma50_today) and pd.notna(sma50_20d_ago):
                        sma50_trend_up = float(sma50_today) > float(sma50_20d_ago)
        except Exception:
            sma50_trend_up = False
        indicators_used["sma50_trend_up"] = bool(sma50_trend_up)

        # DB-free structural context derived from price history + latest SMA50.
        sma50_value = indicators_used.get("sma_50")
        days_below_sma50 = 0
        try:
            if sma50_value not in (None, 0) and "close" in df.columns:
                closes = pd.to_numeric(df["close"], errors="coerce").dropna().tolist()
                for c in reversed(closes):
                    if c < float(sma50_value):
                        days_below_sma50 += 1
                    else:
                        break
        except Exception:
            days_below_sma50 = 0
        indicators_used["days_below_sma50"] = int(days_below_sma50)

        features = self._compute_features(indicators_used)
        state, state_reasons = self._detect_state(features)
        phase = self._classify_phase(features)
        extension = self._classify_extension(features)
        action, action_reasons = self._map_action(state, phase, extension, features)
        action, safety_reasons, phase = self._apply_safety_overrides(state, phase, extension, action, features)

        reasons = self._dedupe_reasons(state_reasons + action_reasons + safety_reasons)

        opportunity_score = self._score_opportunity(state, phase, extension, features)
        volume_context = self._classify_volume_context(features)

        entry, risk = self._build_entry_and_risk(indicators_used)
        risk["risk_level"] = self._classify_risk(features)

        confidence = self._score_confidence(state, features)

        return TradingDecisionV3(
            symbol=sym,
            as_of_date=latest_date,
            state=state,
            phase=phase,
            extension=extension,
            action=action,
            confidence=confidence,
            price=latest_close,
            features={
                **self._features_to_dict(features),
                "opportunity_score": opportunity_score,
                "volume_context": volume_context,
            },
            entry=entry,
            risk=risk,
            reasons=reasons,
        )

    def persist_decision(self, decision: TradingDecisionV3) -> None:
        ts = datetime.now(timezone.utc)
        deduped_reasons = self._dedupe_reasons(list(decision.reasons or []))

        payload_metadata = {
            "state": decision.state,
            "phase": decision.phase,
            "extension": decision.extension,
            "action": decision.action,
            "as_of_date": decision.as_of_date,
            "entry": decision.entry,
            "risk": decision.risk,
            "features": decision.features,
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

    def run_and_persist(self, symbols: List[str], *, as_of_date: Optional[str] = None) -> List[TradingDecisionV3]:
        out: List[TradingDecisionV3] = []
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

    def _compute_features(self, ind: Dict[str, Any]) -> FeatureSnapshot:
        close = ind.get("close")
        prev_close = ind.get("prev_close")
        ema20 = ind.get("ema_20")
        sma50 = ind.get("sma_50")
        sma50_trend_up = bool(ind.get("sma50_trend_up") or False)
        rsi = ind.get("rsi_14")
        vol_ratio = ind.get("vol_ratio")

        if close is None:
            close = 0.0

        pct_from_ema20 = None
        if ema20 not in (None, 0):
            pct_from_ema20 = (close - ema20) / ema20 * 100.0

        pct_from_sma50 = None
        if sma50 not in (None, 0):
            pct_from_sma50 = (close - sma50) / sma50 * 100.0

        day_change_pct = None
        if prev_close not in (None, 0) and close is not None:
            day_change_pct = (close - prev_close) / prev_close * 100.0

        is_red_day = bool(day_change_pct is not None and day_change_pct < 0)
        no_chase_zone = bool(pct_from_ema20 is not None and 7 <= pct_from_ema20 <= 12)

        days_below_sma50 = int(ind.get("days_below_sma50") or 0)
        reclaim_sma50 = bool(
            sma50 not in (None, 0)
            and prev_close is not None
            and close is not None
            and float(prev_close) < float(sma50)
            and float(close) > float(sma50)
        )
        low_20_prev = ind.get("low_20_prev")
        support_holding = bool(low_20_prev is not None and close is not None and float(close) >= float(low_20_prev))

        above_ema20 = bool(ema20 is not None and close > ema20)
        below_ema20 = bool(ema20 is not None and close < ema20)
        below_sma50 = bool(sma50 is not None and close < sma50)

        vol_high = bool(vol_ratio is not None and vol_ratio > 1.5)
        vol_low = bool(vol_ratio is not None and vol_ratio < 0.8)

        return FeatureSnapshot(
            close=float(close),
            prev_close=float(prev_close) if prev_close is not None else None,
            ema20=float(ema20) if ema20 is not None else None,
            sma50=float(sma50) if sma50 is not None else None,
            sma50_trend_up=sma50_trend_up,
            rsi=float(rsi) if rsi is not None else None,
            vol_ratio=float(vol_ratio) if vol_ratio is not None else None,
            pct_from_ema20=float(pct_from_ema20) if pct_from_ema20 is not None else None,
            pct_from_sma50=float(pct_from_sma50) if pct_from_sma50 is not None else None,
            day_change_pct=float(day_change_pct) if day_change_pct is not None else None,
            is_red_day=is_red_day,
            no_chase_zone=no_chase_zone,
            days_below_sma50=days_below_sma50,
            reclaim_sma50=reclaim_sma50,
            support_holding=support_holding,
            above_ema20=above_ema20,
            below_ema20=below_ema20,
            below_sma50=below_sma50,
            vol_high=vol_high,
            vol_low=vol_low,
        )

    def _detect_state(self, f: FeatureSnapshot) -> Tuple[str, List[str]]:
        reasons: List[str] = []

        rules: List[Tuple[str, int, Any]] = [
            ("climax", 100, lambda x: x.pct_from_ema20 is not None and x.pct_from_ema20 > 25 and x.vol_ratio is not None and x.vol_ratio > 1.8),
            ("breakdown", 90, lambda x: x.below_ema20 and x.below_sma50 and x.vol_ratio is not None and x.vol_ratio > 1.5),
            ("pullback", 50, lambda x: x.below_ema20),
            ("trend", 10, lambda x: x.above_ema20),
            ("base", 0, lambda x: True),
        ]

        for name, _, cond in sorted(rules, key=lambda r: r[1], reverse=True):
            if cond(f):
                reasons.append(f"state:{name}")
                return name, reasons

        return "base", ["state:base"]

    def _classify_phase(self, f: FeatureSnapshot) -> str:
        pct = f.pct_from_ema20
        vol = f.vol_ratio

        if pct is not None:
            if pct > 25:
                if vol is not None and vol > 1.8:
                    return "climax_exhaustion"
                return "extended_trend"

            if pct > 15:
                if vol is not None and vol >= 1.5:
                    return "momentum_trend"
                return "late_trend"

            if pct > 3:
                if f.vol_low:
                    return "low_volume_uptrend"
                if f.vol_high:
                    return "high_volume_trend"
                return "healthy_trend"

        if f.above_ema20:
            if f.vol_low:
                return "low_volume_uptrend"
            if f.vol_high:
                return "high_volume_trend"
            return "healthy_trend"

        if f.below_ema20:
            if f.vol_high:
                return "distribution"
            return "pullback"

        return "consolidation"

    def _classify_extension(self, f: FeatureSnapshot) -> str:
        pct = f.pct_from_ema20
        if pct is None:
            return "controlled"
        if pct > 25:
            return "extreme"
        if pct > 12:
            return "extended"
        return "controlled"

    def _map_action(self, state: str, phase: str, extension: str, f: FeatureSnapshot) -> Tuple[str, List[str]]:
        reasons: List[str] = []

        if state == "trend":

            if extension == "extreme" and f.is_red_day:
                return "trim_light", ["extreme_but_weakening"]

            if (
                f.day_change_pct is not None
                and f.day_change_pct <= -1.5
                and not f.vol_high
            ):
                return "hold", ["pullback_inside_trend"]

            if f.no_chase_zone and not f.vol_high:
                return "hold", ["mid_extension_no_chase"]

            if extension == "extreme":
                if f.vol_high:
                    return "trim", ["extreme_extension_with_volume"]
                return "trim_light", ["extreme_extension_no_volume"]

            if extension == "extended":
                if f.rsi is not None and f.rsi > 75:
                    return "trim_light", ["extended_overbought"]
                return "hold", ["extended_no_overbought"]

            if f.vol_high:
                return "add_light", ["trend_high_volume"]

            return "add_light", ["trend_continuation"]

        if state == "pullback":

            # 1. Strongest signal → reclaim
            if f.reclaim_sma50:
                return "add_light", ["reclaim_sma50"]

            # 2. Immediate distribution (no delay)
            if f.below_sma50 and f.vol_high:
                return "reduce", ["below_sma50_distribution"]

            # 3. Early shakeout / undercut
            if f.below_sma50 and f.vol_low and f.support_holding and f.days_below_sma50 <= 3 and f.sma50_trend_up:
                return "add_light", ["below_sma50_low_volume_accumulation"]

            # 4. Prolonged weakness → reduce
            if f.below_sma50 and f.days_below_sma50 >= 7:
                return "reduce", ["prolonged_below_sma50"]

            # 5. BELOW SMA50 but unclear → HOLD (THIS IS THE BIG FIX)
            if f.below_sma50:
                return "hold", ["below_sma50_wait"]

            # 6. Distribution near EMA
            if f.vol_high and f.below_ema20:
                return "reduce", ["distribution_pressure"]

            # 7. Weak momentum
            if f.rsi is not None and f.rsi < 45:
                return "hold", ["weak_pullback"]

            # 8. Constructive pullback
            if f.vol_low:
                return "add", ["constructive_pullback"]

            return "add_light", ["standard_pullback"]
        if state == "climax":
            if extension == "extreme":
                return "trim", ["extreme_climax"]
            return "trim_light", ["early_climax"]

        if state == "breakdown":
            if f.vol_high:
                return "exit", ["confirmed_breakdown"]
            return "reduce", ["early_breakdown"]

        return "hold", ["base_no_edge"]

    def _apply_safety_overrides(
        self,
        state: str,
        phase: str,
        extension: str,
        action: str,
        f: FeatureSnapshot,
    ) -> Tuple[str, List[str], str]:
        reasons: List[str] = []

        if action == "hold" and f.no_chase_zone:
            phase = "late_trend"

        if action in ("reduce", "exit") and f.above_ema20:
            if f.vol_high:
                reasons.append("override_reduce_on_high_volume")
            else:
                reasons.append("override_no_reduce_above_ema20")
                action = "hold"

        if state == "breakdown" and action in ("add", "add_light"):
            reasons.append("override_no_add_in_breakdown")
            action = "reduce"

        if state == "climax" and not action.startswith("trim"):
            reasons.append("override_climax_must_trim")
            action = "trim_light"

        if state == "pullback" and phase in ("momentum_trend", "healthy_trend"):
            reasons.append("override_pullback_phase")
            phase = "pullback"

        return action, reasons, phase

    def _classify_risk(self, f: FeatureSnapshot) -> str:
        pct = f.pct_from_ema20
        rsi = f.rsi

        if pct is not None and pct > 30:
            if f.vol_high:
                return "extreme"   # true blow-off
            return "high"         # extended but still trending
        if rsi is not None and rsi > 85:
            return "extreme"

        if pct is not None and pct > 20:
            return "high"
        if rsi is not None and rsi > 75:
            return "high"
        if f.below_ema20 and f.vol_high:
            return "high"

        if pct is not None and abs(pct) <= 5:
            return "low"

        return "medium"

    def _score_confidence(self, state: str, f: FeatureSnapshot) -> float:
        base = {
            "trend": 0.62,
            "pullback": 0.60,
            "breakdown": 0.70,
            "base": 0.55,
            "climax": 0.65,
        }.get(state, 0.55)

        bump = 0.0
        if state == "trend" and f.rsi is not None and 55 <= f.rsi <= 70:
            bump += 0.05
        if state == "breakdown" and f.vol_ratio is not None and f.vol_ratio >= 2.0:
            bump += 0.05

        return float(max(0.0, min(1.0, base + bump)))

    def _score_opportunity(self, state: str, phase: str, extension: str, f: FeatureSnapshot) -> int:
        score = 50

        # 1) Trend quality
        if state == "trend":
            score += 10
        if phase in ("healthy_trend", "low_volume_uptrend"):
            score += 10
        if phase == "late_trend":
            score -= 5

        # 2) Volume quality
        if f.vol_high and not f.is_red_day:
            score += 10
        elif f.vol_high and f.is_red_day:
            score -= 10
        elif f.vol_low:
            score += 5

        # 3) Position vs key levels
        if not f.below_sma50:
            score += 10
        else:
            score -= 15

        if f.reclaim_sma50:
            score += 10

        # 4) Pullback quality
        if f.days_below_sma50 <= 3:
            score += 5
        elif f.days_below_sma50 >= 7:
            score -= 10

        # 5) Extension control
        if extension == "extended":
            score -= 5
        if extension == "extreme":
            score -= 15

        # 6) Optional institutional filter
        if f.sma50_trend_up:
            score += 10

        score = max(0, min(100, score))
        return int(score)

    def _classify_volume_context(self, f: FeatureSnapshot) -> str:
        vol = f.vol_ratio
        if vol is None:
            return "unknown"

        if f.vol_high:
            return "distribution" if f.is_red_day else "accumulation"

        if f.vol_low:
            return "quiet"

        return "neutral"

    def _features_to_dict(self, f: FeatureSnapshot) -> Dict[str, Any]:
        return {
            "close": f.close,
            "prev_close": f.prev_close,
            "ema20": f.ema20,
            "sma50": f.sma50,
            "sma50_trend_up": f.sma50_trend_up,
            "rsi": f.rsi,
            "vol_ratio": f.vol_ratio,
            "pct_from_ema20": f.pct_from_ema20,
            "pct_from_sma50": f.pct_from_sma50,
            "day_change_pct": f.day_change_pct,
            "is_red_day": f.is_red_day,
            "no_chase_zone": f.no_chase_zone,
            "days_below_sma50": f.days_below_sma50,
            "reclaim_sma50": f.reclaim_sma50,
            "support_holding": f.support_holding,
            "above_ema20": f.above_ema20,
            "below_ema20": f.below_ema20,
            "below_sma50": f.below_sma50,
            "vol_high": f.vol_high,
            "vol_low": f.vol_low,
        }

    def _build_entry_and_risk(self, ind: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        ema20 = ind.get("ema_20")
        sma50 = ind.get("sma_50")
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
            "invalid_level": float(sma50) if sma50 is not None else None,
        }
        return entry, risk

    def _get_recent_price_rows(self, symbol: str, *, as_of_date: Optional[str], limit: int) -> List[Dict[str, Any]]:
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

    def _get_latest_indicators(self, symbol: str, as_of_date: str) -> Optional[Dict[str, Any]]:
        q = """
            SELECT indicator_name, indicator_value
            FROM indicators_daily
            WHERE symbol = :symbol
              AND date = CAST(:as_of_date AS date)
              AND interval = '1d'
              AND LOWER(indicator_name) IN ('rsi_14','ema_20','sma_50')
        """
        rows = db.execute_query(q, {"symbol": symbol, "as_of_date": as_of_date})
        if not rows:
            return None
        out: Dict[str, Any] = {}
        for r in rows:
            out[(r.get("indicator_name") or "").lower()] = r.get("indicator_value")
        return out

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

    def _dedupe_reasons(self, reasons: List[str]) -> List[str]:
        seen = set()
        out: List[str] = []
        for r in reasons:
            if r in seen:
                continue
            seen.add(r)
            out.append(r)
        return out
