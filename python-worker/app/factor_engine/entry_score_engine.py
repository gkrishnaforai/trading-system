from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import text

from app.database import db
from app.factor_engine.models import FactorSnapshot
from app.factor_engine.providers.risk_provider import RiskProvider
from app.factor_engine.providers.technical_provider import TechnicalProvider


@dataclass
class EntryScoreResult:
    symbol: str
    as_of_date: date
    source: str
    factors: Dict[str, FactorSnapshot]
    metadata: Dict[str, Any]


class EntryScoreEngine:
    """Compute entry-focused timing scores from canonical technical + risk factors.

    v1 goals:
    - deterministic
    - explainable
    - works with current factor availability

    Output factors:
    - entry.score (0-100)
    - ai_accumulation.score (0-100)  # same as entry.score in v1
    """

    def __init__(self):
        self._technical = TechnicalProvider()
        self._risk = RiskProvider()

    def get_latest(self, symbol: str) -> Optional[EntryScoreResult]:
        tech = self._technical.get_latest(symbol)
        risk = self._risk.get_latest(symbol)
        return self._compute(symbol, tech=tech, risk=risk, as_of_date=None)

    def get_asof(self, symbol: str, as_of_date: date) -> Optional[EntryScoreResult]:
        tech = self._technical.get_asof(symbol, as_of_date)
        risk = self._risk.get_asof(symbol, as_of_date)
        return self._compute(symbol, tech=tech, risk=risk, as_of_date=as_of_date)

    def _get_latest_close(self, symbol: str, as_of_date: Optional[date]) -> Optional[Tuple[date, float]]:
        if as_of_date is None:
            q = text(
                """
                SELECT date, close
                FROM raw_market_data_daily
                WHERE symbol = :symbol
                ORDER BY date DESC
                LIMIT 1
                """
            )
            params = {"symbol": symbol}
        else:
            q = text(
                """
                SELECT date, close
                FROM raw_market_data_daily
                WHERE symbol = :symbol AND date <= :as_of_date
                ORDER BY date DESC
                LIMIT 1
                """
            )
            params = {"symbol": symbol, "as_of_date": as_of_date}

        with db.get_session() as session:
            row = session.execute(q, params).fetchone()

        if row is None:
            return None

        try:
            return (row[0], float(row[1]))
        except Exception:
            return None

    def _compute(self, symbol: str, tech, risk, as_of_date: Optional[date]) -> Optional[EntryScoreResult]:
        close_rec = self._get_latest_close(symbol, as_of_date)
        if close_rec is None:
            return None

        close_date, close_px = close_rec

        # Pick an as_of_date that is consistent (prefer tech, then risk, then close)
        effective_asof = close_date
        if tech is not None:
            effective_asof = tech.as_of_date
        elif risk is not None:
            effective_asof = risk.as_of_date

        # Extract needed factors
        def _f(snapshot, fid: str) -> Optional[float]:
            if snapshot is None:
                return None
            snap = (snapshot.factors or {}).get(fid)
            if snap is None:
                return None
            try:
                return float(snap.value)
            except Exception:
                return None

        rsi = _f(tech, "technical.rsi_14")
        ema20 = _f(tech, "technical.ema_20")
        sma50 = _f(tech, "technical.sma_50")
        sma200 = _f(tech, "technical.sma_200")

        vol30 = _f(risk, "risk.volatility_30d")
        mdd1y = _f(risk, "risk.max_drawdown_1y")

        # Components (0..1)
        components: Dict[str, float] = {}
        missing: Dict[str, bool] = {}

        # Trend: price > sma50 > sma200
        if sma50 is None or sma200 is None:
            missing["trend"] = True
        else:
            missing["trend"] = False
            if close_px > sma50 and sma50 > sma200:
                components["trend"] = 1.0
            elif close_px > sma50:
                components["trend"] = 0.75
            elif close_px > sma200:
                components["trend"] = 0.4
            else:
                components["trend"] = 0.1

        # Momentum: RSI in preferred zones
        if rsi is None:
            missing["momentum"] = True
        else:
            missing["momentum"] = False
            if 55 <= rsi <= 70:
                components["momentum"] = 1.0
            elif 50 <= rsi < 55:
                components["momentum"] = 0.7
            elif 40 <= rsi < 50:
                components["momentum"] = 0.6  # pullback zone (acceptable)
            elif 70 < rsi <= 75:
                components["momentum"] = 0.5  # extended
            else:
                components["momentum"] = 0.2

        # Pullback quality: price near ema20 in an uptrend
        if ema20 is None or sma50 is None:
            missing["pullback"] = True
        else:
            missing["pullback"] = False
            dist = abs(close_px - ema20) / ema20 if ema20 else 1.0
            in_trend = close_px > sma50
            if in_trend and dist <= 0.015:
                components["pullback"] = 1.0
            elif in_trend and dist <= 0.03:
                components["pullback"] = 0.75
            elif in_trend:
                components["pullback"] = 0.4
            else:
                components["pullback"] = 0.2

        # Volatility: lower vol is better (soft penalty)
        if vol30 is None:
            missing["volatility"] = True
        else:
            missing["volatility"] = False
            # Typical daily vol might be ~1-5%. If volatility_30d is annualized, this is still monotonic.
            if vol30 <= 0.2:
                components["volatility"] = 1.0
            elif vol30 <= 0.35:
                components["volatility"] = 0.7
            elif vol30 <= 0.5:
                components["volatility"] = 0.4
            else:
                components["volatility"] = 0.2

        # Risk/reward proxy: penalize big drawdowns
        if mdd1y is None:
            missing["risk_reward"] = True
        else:
            missing["risk_reward"] = False
            dd = abs(mdd1y)
            if dd <= 0.15:
                components["risk_reward"] = 1.0
            elif dd <= 0.3:
                components["risk_reward"] = 0.7
            elif dd <= 0.5:
                components["risk_reward"] = 0.4
            else:
                components["risk_reward"] = 0.2

        # Weighted blend -> 0..100
        weights = {
            "trend": 0.30,
            "momentum": 0.25,
            "pullback": 0.20,
            "volatility": 0.10,
            "risk_reward": 0.15,
        }

        score_sum = 0.0
        weight_sum = 0.0
        for k, w in weights.items():
            if missing.get(k):
                continue
            score_sum += components.get(k, 0.0) * w
            weight_sum += w

        if weight_sum <= 0:
            return None

        score_0_1 = max(0.0, min(1.0, score_sum / weight_sum))
        score_0_100 = round(score_0_1 * 100.0, 2)

        # Confidence: fraction of components present
        present = sum(1 for k in weights.keys() if not missing.get(k))
        total = len(weights)
        confidence = round(present / total, 3)

        src = "entry_score_engine.v1"
        factors = {
            "entry.score": FactorSnapshot(
                factor_id="entry.score",
                symbol=symbol,
                as_of_date=effective_asof,
                value=score_0_100,
                confidence=confidence,
                source=src,
                metadata={"components": components, "weights": weights, "missing": missing},
            ),
            "ai_accumulation.score": FactorSnapshot(
                factor_id="ai_accumulation.score",
                symbol=symbol,
                as_of_date=effective_asof,
                value=score_0_100,
                confidence=confidence,
                source=src,
                metadata={"components": components, "weights": weights, "missing": missing},
            ),
        }

        return EntryScoreResult(
            symbol=symbol,
            as_of_date=effective_asof,
            source=src,
            factors=factors,
            metadata={
                "close": close_px,
                "close_as_of": close_date.isoformat(),
                "components": components,
                "weights": weights,
                "missing": missing,
            },
        )
