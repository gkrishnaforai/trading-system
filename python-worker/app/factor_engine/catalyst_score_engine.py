from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, Optional

from app.factor_engine.models import FactorSnapshot
from app.factor_engine.providers.catalyst_provider import CatalystProvider


@dataclass
class CatalystScoreResult:
    symbol: str
    as_of_date: date
    source: str
    factors: Dict[str, FactorSnapshot]
    metadata: Dict[str, Any]


class CatalystScoreEngine:
    """CatalystScoreEngine v1.

    v1 policy: earnings-centric catalyst.

    Score interpretation (0-100): higher means nearer-term catalyst.
    """

    def __init__(self):
        self._provider = CatalystProvider()

    def get_latest(self, symbol: str) -> Optional[CatalystScoreResult]:
        return self.get_asof(symbol, date.today())

    def get_asof(self, symbol: str, as_of_date: date) -> Optional[CatalystScoreResult]:
        symbol = symbol.upper()

        prov = self._provider.get_asof(symbol, as_of_date)
        if prov is None:
            return None

        days_to: Optional[int] = None
        snap = (prov.factors or {}).get("catalyst.earnings_days_to")
        if snap is not None:
            try:
                days_to = int(snap.value)
            except Exception:
                days_to = None

        earnings_score: Optional[float] = None
        if days_to is not None and days_to >= 0:
            earnings_score = self._score_from_days_to(days_to)

        ai_recent = False
        ai_count: Optional[int] = None
        ai_recent_snap = (prov.factors or {}).get("catalyst.ai_news_recent_30d")
        if ai_recent_snap is not None:
            try:
                ai_recent = bool(ai_recent_snap.value)
            except Exception:
                ai_recent = False

        ai_count_snap = (prov.factors or {}).get("catalyst.ai_news_30d_count")
        if ai_count_snap is not None:
            try:
                ai_count = int(ai_count_snap.value)
            except Exception:
                ai_count = None

        ai_score: Optional[float] = None
        if ai_recent:
            # Heuristic v1: presence of recent AI/model/product news is a catalyst.
            # Keep it below near-term earnings to avoid over-dominating.
            c = ai_count or 1
            ai_score = min(85.0, 60.0 + (float(c) * 5.0))

        if earnings_score is None and ai_score is None:
            return None

        score = max([s for s in [earnings_score, ai_score] if s is not None])
        confidence = self._confidence(prov)

        src = "catalyst_score_engine.v1"
        factors: Dict[str, FactorSnapshot] = {
            "catalyst.score": FactorSnapshot(
                factor_id="catalyst.score",
                symbol=symbol,
                as_of_date=as_of_date,
                value=score,
                confidence=confidence,
                source=src,
                source_timestamp=None,
                metadata={
                    "days_to_earnings": days_to,
                    "ai_news_recent_30d": ai_recent,
                    "ai_news_30d_count": ai_count,
                },
            )
        }

        # Pass-through AI catalyst factors to enable filtering/ranking downstream.
        for fid in ["catalyst.ai_news_recent_30d", "catalyst.ai_news_30d_count"]:
            psnap = (prov.factors or {}).get(fid)
            if psnap is not None:
                factors[fid] = psnap

        return CatalystScoreResult(
            symbol=symbol,
            as_of_date=as_of_date,
            source=src,
            factors=factors,
            metadata={
                "days_to_earnings": days_to,
                "bucket": self._bucket(days_to) if days_to is not None and days_to >= 0 else None,
                "provider_source": prov.source,
                "ai_news_recent_30d": ai_recent,
                "ai_news_30d_count": ai_count,
            },
        )

    def _score_from_days_to(self, days_to: int) -> float:
        # Deterministic bucketed policy (easy to iterate later)
        if days_to <= 7:
            return 90.0
        if days_to <= 14:
            return 70.0
        if days_to <= 21:
            return 55.0
        if days_to <= 30:
            return 40.0
        if days_to <= 45:
            return 25.0
        return 10.0

    def _bucket(self, days_to: int) -> str:
        if days_to <= 7:
            return "<=7d"
        if days_to <= 14:
            return "<=14d"
        if days_to <= 21:
            return "<=21d"
        if days_to <= 30:
            return "<=30d"
        if days_to <= 45:
            return "<=45d"
        return ">45d"

    def _confidence(self, prov) -> int:
        # v1: use provider factor confidence if present
        snap = (prov.factors or {}).get("catalyst.earnings_days_to")
        if snap is None:
            return 50
        try:
            return int(snap.confidence)
        except Exception:
            return 50
