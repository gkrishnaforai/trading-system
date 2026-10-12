from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from math import sqrt
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app.database import db
from app.factor_engine.models import FactorSnapshot


_DEFAULT_RISK_FACTOR_IDS: List[str] = [
    "risk.volatility_30d",
    "risk.max_drawdown_1y",
    "risk.var_95",
    "risk.sharpe_ratio",
]


@dataclass(frozen=True)
class RiskProviderResult:
    symbol: str
    as_of_date: date
    source: str
    factors: Dict[str, FactorSnapshot]


class RiskProvider:
    """v1 RiskProvider.

    Canonical v1 policy: compute deterministically from `raw_market_data_daily`.

    Notes:
    - Uses close-to-close simple returns.
    - Annualization (where used) assumes 252 trading days.
    """

    def get_latest(
        self,
        symbol: str,
        factor_ids: Optional[Iterable[str]] = None,
    ) -> Optional[RiskProviderResult]:
        symbol = symbol.upper()
        factor_ids_list = list(factor_ids) if factor_ids is not None else list(_DEFAULT_RISK_FACTOR_IDS)

        latest_date = self._get_latest_price_date(symbol)
        if latest_date is None:
            return None

        return self.get_asof(symbol, latest_date, factor_ids=factor_ids_list)

    def get_asof(
        self,
        symbol: str,
        as_of_date: date,
        factor_ids: Optional[Iterable[str]] = None,
    ) -> Optional[RiskProviderResult]:
        symbol = symbol.upper()
        factor_ids_list = list(factor_ids) if factor_ids is not None else list(_DEFAULT_RISK_FACTOR_IDS)

        closes = self._fetch_closes(symbol=symbol, as_of_date=as_of_date, limit=260)
        if len(closes) < 10:
            return None

        returns = self._simple_returns(closes)

        factors: Dict[str, FactorSnapshot] = {}

        def put(fid: str, value: Any, confidence: int) -> None:
            if fid not in factor_ids_list:
                return
            if value is None:
                return
            factors[fid] = FactorSnapshot(
                factor_id=fid,
                symbol=symbol,
                as_of_date=as_of_date,
                value=value,
                confidence=confidence,
                source="raw_market_data_daily",
                source_timestamp=None,
            )

        if "risk.volatility_30d" in factor_ids_list:
            vol_30d, conf = self._volatility_30d(returns)
            put("risk.volatility_30d", vol_30d, conf)

        if "risk.max_drawdown_1y" in factor_ids_list:
            mdd_1y, conf = self._max_drawdown_1y(closes)
            put("risk.max_drawdown_1y", mdd_1y, conf)

        if "risk.var_95" in factor_ids_list:
            var_95, conf = self._var_95(returns)
            put("risk.var_95", var_95, conf)

        if "risk.sharpe_ratio" in factor_ids_list:
            sharpe, conf = self._sharpe_ratio(returns)
            put("risk.sharpe_ratio", sharpe, conf)

        return RiskProviderResult(
            symbol=symbol,
            as_of_date=as_of_date,
            source="raw_market_data_daily",
            factors=factors,
        )

    # -------------------------
    # Core computations
    # -------------------------

    def _volatility_30d(self, returns: List[float]) -> Tuple[Optional[float], int]:
        # Use last 30 returns.
        window = 30
        if len(returns) < window:
            return None, 0
        r = returns[:window]
        std = self._stddev(r)
        if std is None:
            return None, 0
        # Annualized volatility.
        return float(std * sqrt(252.0)), 80

    def _max_drawdown_1y(self, closes: List[float]) -> Tuple[Optional[float], int]:
        # Use up to last ~252 closes (already ordered desc).
        if len(closes) < 30:
            return None, 0
        # Reverse into chronological order.
        series = list(reversed(closes[:252]))
        peak = None
        max_dd = 0.0
        for p in series:
            if p is None:
                continue
            if peak is None or p > peak:
                peak = p
            if peak and peak > 0:
                dd = (p / peak) - 1.0
                if dd < max_dd:
                    max_dd = dd
        # Return as negative number (e.g., -0.35).
        return float(max_dd), 80

    def _var_95(self, returns: List[float]) -> Tuple[Optional[float], int]:
        # Historical 95% VaR on daily returns over ~1y window.
        if len(returns) < 60:
            return None, 0
        window = min(len(returns), 252)
        r = returns[:window]
        p5 = self._percentile(r, 5.0)
        if p5 is None:
            return None, 0
        # Return as negative return threshold.
        return float(p5), 70

    def _sharpe_ratio(self, returns: List[float]) -> Tuple[Optional[float], int]:
        # Simple Sharpe with rf=0 using last ~252 returns.
        if len(returns) < 60:
            return None, 0
        window = min(len(returns), 252)
        r = returns[:window]
        mean = sum(r) / float(len(r))
        std = self._stddev(r)
        if std is None or std == 0:
            return None, 0
        sharpe = (mean / std) * sqrt(252.0)
        return float(sharpe), 70

    # -------------------------
    # Data access
    # -------------------------

    def _get_latest_price_date(self, symbol: str) -> Optional[date]:
        q = """
            SELECT date
            FROM raw_market_data_daily
            WHERE symbol = :symbol
            ORDER BY date DESC
            LIMIT 1
        """
        rows = db.execute_query(q, {"symbol": symbol})
        if not rows:
            return None
        v = rows[0].get("date")
        if isinstance(v, date):
            return v
        try:
            return date.fromisoformat(str(v)[:10])
        except Exception:
            return None

    def _fetch_closes(self, symbol: str, as_of_date: date, limit: int) -> List[float]:
        q = """
            SELECT date, close
            FROM raw_market_data_daily
            WHERE symbol = :symbol
              AND date <= CAST(:as_of_date AS date)
            ORDER BY date DESC
            LIMIT :limit
        """
        rows = db.execute_query(
            q,
            {
                "symbol": symbol,
                "as_of_date": as_of_date.isoformat(),
                "limit": int(limit),
            },
        )
        out: List[float] = []
        for r in rows:
            try:
                c = r.get("close")
                if c is None:
                    continue
                out.append(float(c))
            except Exception:
                continue
        return out

    # -------------------------
    # Math helpers
    # -------------------------

    def _simple_returns(self, closes_desc: List[float]) -> List[float]:
        # closes are in descending date order; returns aligned with that ordering.
        out: List[float] = []
        for i in range(0, len(closes_desc) - 1):
            c0 = closes_desc[i]
            c1 = closes_desc[i + 1]
            if c0 is None or c1 is None or c1 == 0:
                continue
            out.append((c0 / c1) - 1.0)
        return out

    def _stddev(self, xs: List[float]) -> Optional[float]:
        if not xs:
            return None
        n = len(xs)
        if n < 2:
            return None
        mean = sum(xs) / float(n)
        var = sum((x - mean) ** 2 for x in xs) / float(n - 1)
        if var < 0:
            return None
        return sqrt(var)

    def _percentile(self, xs: List[float], p: float) -> Optional[float]:
        if not xs:
            return None
        if p <= 0:
            return min(xs)
        if p >= 100:
            return max(xs)
        s = sorted(xs)
        k = (len(s) - 1) * (p / 100.0)
        f = int(k)
        c = min(f + 1, len(s) - 1)
        if f == c:
            return float(s[f])
        d0 = s[f] * (c - k)
        d1 = s[c] * (k - f)
        return float(d0 + d1)
