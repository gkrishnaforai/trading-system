from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional

from app.database import db
from app.factor_engine.models import FactorSnapshot


_DEFAULT_TECHNICAL_FACTOR_IDS: List[str] = [
    "technical.rsi_14",
    "technical.ema_20",
    "technical.sma_50",
    "technical.sma_200",
    "technical.macd",
    "technical.macd_signal",
    "technical.macd_hist",
]


@dataclass(frozen=True)
class TechnicalProviderResult:
    symbol: str
    as_of_date: date
    source: str
    factors: Dict[str, FactorSnapshot]


class TechnicalProvider:
    """Canonical technical factor access.

    Normalizes the repo's known `indicators_daily` schema variants:
    - *Narrow schema*: rows keyed by (symbol, date, indicator_name) -> indicator_value
    - *Wide schema*: one row per (symbol, date, interval) containing many indicator columns

    This is intentionally minimal and designed for Factor Engine usage.
    """

    def get_latest(
        self,
        symbol: str,
        factor_ids: Optional[Iterable[str]] = None,
    ) -> Optional[TechnicalProviderResult]:
        symbol = symbol.upper()
        factor_ids_list = list(factor_ids) if factor_ids is not None else list(_DEFAULT_TECHNICAL_FACTOR_IDS)

        latest_date = self._get_latest_date(symbol)
        if latest_date is None:
            return None

        return self.get_asof(symbol, latest_date, factor_ids=factor_ids_list)

    def get_asof(
        self,
        symbol: str,
        as_of_date: date,
        factor_ids: Optional[Iterable[str]] = None,
    ) -> Optional[TechnicalProviderResult]:
        symbol = symbol.upper()
        factor_ids_list = list(factor_ids) if factor_ids is not None else list(_DEFAULT_TECHNICAL_FACTOR_IDS)

        # Prefer narrow schema when present.
        if self._supports_narrow_schema():
            rows = self._fetch_narrow_rows(symbol=symbol, as_of_date=as_of_date)
            if rows:
                return self._build_from_narrow_rows(symbol, as_of_date, rows, factor_ids_list)

        if self._supports_wide_schema():
            wide_row = self._fetch_wide_row(symbol=symbol, as_of_date=as_of_date)
            if wide_row:
                return self._build_from_wide_row(symbol, as_of_date, wide_row, factor_ids_list)

        return None

    # -------------------------
    # Schema normalization
    # -------------------------

    def _fetch_narrow_rows(self, symbol: str, as_of_date: date) -> List[Dict[str, Any]]:
        if not self._supports_narrow_schema():
            return []
        # Try with interval first; if interval column doesn't exist, fallback.
        q = """
            SELECT indicator_name, indicator_value, date, created_at
            FROM indicators_daily
            WHERE symbol = :symbol
              AND date = CAST(:as_of_date AS date)
              AND interval = '1d'
              AND indicator_name IS NOT NULL
        """
        try:
            return db.execute_query(q, {"symbol": symbol, "as_of_date": as_of_date.isoformat()})
        except Exception as e:
            msg = str(e).lower()
            if "undefinedcolumn" in msg and "interval" in msg:
                q2 = """
                    SELECT indicator_name, indicator_value, date, created_at
                    FROM indicators_daily
                    WHERE symbol = :symbol
                      AND date = CAST(:as_of_date AS date)
                      AND indicator_name IS NOT NULL
                """
                return db.execute_query(q2, {"symbol": symbol, "as_of_date": as_of_date.isoformat()})
            raise

    def _fetch_wide_row(self, symbol: str, as_of_date: date) -> Optional[Dict[str, Any]]:
        if not self._supports_wide_schema():
            return None
        # Wide schema: columns like rsi_14, ema_20, sma_50, macd, macd_signal, macd_hist.
        # Some environments include interval + as_of_ts.
        has_interval = self._has_column("indicators_daily", "interval")
        has_as_of_ts = self._has_column("indicators_daily", "as_of_ts")

        # In some schemas there is an `indicator_name` column used to distinguish row-shapes.
        # In wide-only schemas, that column may not exist.
        has_indicator_name = self._has_column("indicators_daily", "indicator_name")
        wide_shape_predicate = "AND indicator_name IS NULL" if has_indicator_name else ""

        if has_interval and has_as_of_ts:
            q = """
                SELECT *
                FROM indicators_daily
                WHERE symbol = :symbol
                  AND date = CAST(:as_of_date AS date)
                  AND interval = '1d'
                  {wide_shape_predicate}
                ORDER BY as_of_ts DESC
                LIMIT 1
            """
            rows = db.execute_query(
                q.format(wide_shape_predicate=wide_shape_predicate),
                {"symbol": symbol, "as_of_date": as_of_date.isoformat()},
            )
            return rows[0] if rows else None

        if has_interval:
            q = """
                SELECT *
                FROM indicators_daily
                WHERE symbol = :symbol
                  AND date = CAST(:as_of_date AS date)
                  AND interval = '1d'
                  {wide_shape_predicate}
                ORDER BY date DESC
                LIMIT 1
            """
            rows = db.execute_query(
                q.format(wide_shape_predicate=wide_shape_predicate),
                {"symbol": symbol, "as_of_date": as_of_date.isoformat()},
            )
            return rows[0] if rows else None

        q = """
            SELECT *
            FROM indicators_daily
            WHERE symbol = :symbol
              AND date = CAST(:as_of_date AS date)
              {wide_shape_predicate}
            ORDER BY date DESC
            LIMIT 1
        """
        rows = db.execute_query(
            q.format(wide_shape_predicate=wide_shape_predicate),
            {"symbol": symbol, "as_of_date": as_of_date.isoformat()},
        )
        return rows[0] if rows else None

    # -------------------------
    # Result building
    # -------------------------

    def _build_from_narrow_rows(
        self,
        symbol: str,
        as_of_date: date,
        rows: List[Dict[str, Any]],
        factor_ids: List[str],
    ) -> TechnicalProviderResult:
        indicator_map: Dict[str, Any] = {}
        source_ts: Optional[datetime] = None

        for r in rows:
            name = (r.get("indicator_name") or "").strip().lower()
            if not name:
                continue
            indicator_map[name] = r.get("indicator_value")
            if source_ts is None:
                source_ts = self._coerce_datetime(r.get("created_at"))

        factors: Dict[str, FactorSnapshot] = {}
        for fid in factor_ids:
            col = self._factor_id_to_indicator_key(fid)
            if col is None:
                continue
            if col not in indicator_map:
                if col == "macd_hist" and "macd_histogram" in indicator_map:
                    indicator_map[col] = indicator_map.get("macd_histogram")
                else:
                    continue
            factors[fid] = FactorSnapshot(
                factor_id=fid,
                symbol=symbol,
                as_of_date=as_of_date,
                value=indicator_map.get(col),
                confidence=self._confidence_for_value(indicator_map.get(col)),
                source="indicators_daily(narrow)",
                source_timestamp=source_ts,
            )

        return TechnicalProviderResult(
            symbol=symbol,
            as_of_date=as_of_date,
            source="indicators_daily(narrow)",
            factors=factors,
        )

    def _build_from_wide_row(
        self,
        symbol: str,
        as_of_date: date,
        row: Dict[str, Any],
        factor_ids: List[str],
    ) -> TechnicalProviderResult:
        source_ts = self._coerce_datetime(row.get("as_of_ts")) or self._coerce_datetime(row.get("updated_at"))

        factors: Dict[str, FactorSnapshot] = {}
        for fid in factor_ids:
            col = self._factor_id_to_wide_column(fid)
            if col is None:
                continue
            if col not in row:
                continue
            value = row.get(col)
            if value is None:
                continue
            factors[fid] = FactorSnapshot(
                factor_id=fid,
                symbol=symbol,
                as_of_date=as_of_date,
                value=value,
                confidence=self._confidence_for_value(value),
                source="indicators_daily(wide)",
                source_timestamp=source_ts,
            )

        return TechnicalProviderResult(
            symbol=symbol,
            as_of_date=as_of_date,
            source="indicators_daily(wide)",
            factors=factors,
        )

    # -------------------------
    # Helpers
    # -------------------------

    def _get_latest_date(self, symbol: str) -> Optional[date]:
        if not (self._supports_narrow_schema() or self._supports_wide_schema()):
            return None
        has_interval = self._has_column("indicators_daily", "interval")
        has_as_of_ts = self._has_column("indicators_daily", "as_of_ts")

        if has_interval and has_as_of_ts:
            q = """
                SELECT date
                FROM indicators_daily
                WHERE symbol = :symbol
                  AND interval = '1d'
                ORDER BY as_of_ts DESC
                LIMIT 1
            """
            rows = db.execute_query(q, {"symbol": symbol})
            return self._coerce_date(rows[0].get("date")) if rows else None

        if has_interval:
            q = """
                SELECT date
                FROM indicators_daily
                WHERE symbol = :symbol
                  AND interval = '1d'
                ORDER BY date DESC
                LIMIT 1
            """
            rows = db.execute_query(q, {"symbol": symbol})
            return self._coerce_date(rows[0].get("date")) if rows else None

        q = """
            SELECT date
            FROM indicators_daily
            WHERE symbol = :symbol
            ORDER BY date DESC
            LIMIT 1
        """
        rows = db.execute_query(q, {"symbol": symbol})
        return self._coerce_date(rows[0].get("date")) if rows else None

    def _supports_narrow_schema(self) -> bool:
        return self._has_column("indicators_daily", "indicator_name") and self._has_column(
            "indicators_daily", "indicator_value"
        )

    def _supports_wide_schema(self) -> bool:
        # Wide schema is assumed if at least one expected indicator column exists.
        return (
            self._has_column("indicators_daily", "rsi_14")
            or self._has_column("indicators_daily", "ema_20")
            or self._has_column("indicators_daily", "sma_50")
            or self._has_column("indicators_daily", "macd")
        )

    def _has_column(self, table: str, column: str) -> bool:
        q = """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema='public'
              AND table_name = :table
              AND column_name = :column
            LIMIT 1
        """
        rows = db.execute_query(q, {"table": table, "column": column})
        return bool(rows)

    def _factor_id_to_indicator_key(self, factor_id: str) -> Optional[str]:
        # For narrow schema we use indicator_name values.
        if factor_id == "technical.macd_hist":
            return "macd_hist"  # also seen as macd_histogram in some sources
        return factor_id.split("technical.", 1)[1] if factor_id.startswith("technical.") else None

    def _factor_id_to_wide_column(self, factor_id: str) -> Optional[str]:
        # For wide schema we use column names.
        if not factor_id.startswith("technical."):
            return None
        key = factor_id.split("technical.", 1)[1]
        if key == "macd_hist":
            # common wide-column naming in migrations
            return "macd_hist"
        return key

    def _confidence_for_value(self, value: Any) -> int:
        # Minimal v1 confidence placeholder:
        # - present numeric/non-null -> 80
        # - missing -> 0
        if value is None:
            return 0
        return 80

    def _coerce_date(self, v: Any) -> Optional[date]:
        if v is None:
            return None
        if isinstance(v, date) and not isinstance(v, datetime):
            return v
        if isinstance(v, datetime):
            return v.date()
        try:
            return date.fromisoformat(str(v)[:10])
        except Exception:
            return None

    def _coerce_datetime(self, v: Any) -> Optional[datetime]:
        if v is None:
            return None
        if isinstance(v, datetime):
            return v
        try:
            return datetime.fromisoformat(str(v))
        except Exception:
            return None
