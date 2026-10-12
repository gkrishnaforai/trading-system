from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional

from app.database import db
from app.factor_engine.models import FactorSnapshot


_DEFAULT_META_FACTOR_IDS: List[str] = [
    "meta.market_cap",
    "meta.sector",
    "meta.industry",
    "meta.exchange",
    "meta.country",
    "meta.currency",
    "meta.avg_dollar_volume_20d",
]


@dataclass(frozen=True)
class MetaProviderResult:
    symbol: str
    as_of_date: date
    source: str
    factors: Dict[str, FactorSnapshot]


class MetaProvider:
    def get_latest(
        self,
        symbol: str,
        as_of_date: Optional[date] = None,
        factor_ids: Optional[Iterable[str]] = None,
    ) -> Optional[MetaProviderResult]:
        symbol = symbol.upper()
        as_of = as_of_date or date.today()
        factor_ids_list = list(factor_ids) if factor_ids is not None else list(_DEFAULT_META_FACTOR_IDS)

        stock_row = self._fetch_stock_row(symbol)
        if not stock_row:
            return None

        source_ts = self._coerce_datetime(stock_row.get("updated_at")) or self._coerce_datetime(
            stock_row.get("created_at")
        )

        factors: Dict[str, FactorSnapshot] = {}

        def put(fid: str, value: Any, source: str) -> None:
            if fid not in factor_ids_list:
                return
            if value is None:
                return
            factors[fid] = FactorSnapshot(
                factor_id=fid,
                symbol=symbol,
                as_of_date=as_of,
                value=value,
                confidence=self._confidence_for_value(value),
                source=source,
                source_timestamp=source_ts,
            )

        put("meta.market_cap", stock_row.get("market_cap"), "stocks")
        put("meta.sector", stock_row.get("sector"), "stocks")
        put("meta.industry", stock_row.get("industry"), "stocks")
        put("meta.exchange", stock_row.get("exchange"), "stocks")
        put("meta.country", stock_row.get("country"), "stocks")
        put("meta.currency", stock_row.get("currency"), "stocks")

        if "meta.avg_dollar_volume_20d" in factor_ids_list:
            adv20 = self._avg_dollar_volume_20d(symbol)
            if adv20 is not None:
                factors["meta.avg_dollar_volume_20d"] = FactorSnapshot(
                    factor_id="meta.avg_dollar_volume_20d",
                    symbol=symbol,
                    as_of_date=as_of,
                    value=adv20,
                    confidence=self._confidence_for_value(adv20),
                    source="raw_market_data_daily",
                    source_timestamp=None,
                )

        return MetaProviderResult(
            symbol=symbol,
            as_of_date=as_of,
            source="stocks (+ raw_market_data_daily)",
            factors=factors,
        )

    def _fetch_stock_row(self, symbol: str) -> Optional[Dict[str, Any]]:
        q = """
            SELECT *
            FROM stocks
            WHERE symbol = :symbol
            LIMIT 1
        """
        rows = db.execute_query(q, {"symbol": symbol})
        return rows[0] if rows else None

    def _avg_dollar_volume_20d(self, symbol: str) -> Optional[float]:
        q = """
            SELECT close, volume
            FROM raw_market_data_daily
            WHERE symbol = :symbol
            ORDER BY date DESC
            LIMIT 20
        """
        rows = db.execute_query(q, {"symbol": symbol})
        if not rows:
            return None

        total = 0.0
        count = 0
        for r in rows:
            try:
                close = r.get("close")
                volume = r.get("volume")
                if close is None or volume is None:
                    continue
                total += float(close) * float(volume)
                count += 1
            except Exception:
                continue

        if count == 0:
            return None
        return float(total / count)

    def _confidence_for_value(self, value: Any) -> int:
        if value is None:
            return 0
        return 90

    def _coerce_datetime(self, v: Any) -> Optional[datetime]:
        if v is None:
            return None
        if isinstance(v, datetime):
            return v
        try:
            return datetime.fromisoformat(str(v))
        except Exception:
            return None
