from __future__ import annotations

from datetime import datetime
import re
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from app.database import db
from app.fair_value_v2.schemas import FeatureRow


class PostgresPointInTimeFeatureStore:
    def get_category_override(self, symbol: str) -> Tuple[Optional[str], Optional[str]]:
        """Return (category_override, reason) when an enabled override exists."""
        with db.get_session() as session:
            try:
                row = session.execute(
                    text(
                        """
                        SELECT category_override, reason
                        FROM fair_value_v2_category_overrides
                        WHERE symbol = :symbol
                          AND enabled = TRUE
                        LIMIT 1
                        """
                    ),
                    {"symbol": symbol},
                ).fetchone()
            except ProgrammingError:
                return None, None
            except Exception:
                return None, None

            if not row:
                return None, None
            return row[0], row[1]

    def upsert_category_override(
        self,
        *,
        symbol: str,
        category_override: str,
        enabled: bool = True,
        reason: Optional[str] = None,
        updated_by: Optional[str] = None,
    ) -> None:
        with db.get_session() as session:
            session.execute(
                text(
                    """
                    INSERT INTO fair_value_v2_category_overrides (
                        symbol, category_override, enabled, reason, updated_by, created_at, updated_at
                    ) VALUES (
                        :symbol, :category_override, :enabled, :reason, :updated_by, NOW(), NOW()
                    )
                    ON CONFLICT (symbol) DO UPDATE SET
                        category_override = EXCLUDED.category_override,
                        enabled = EXCLUDED.enabled,
                        reason = EXCLUDED.reason,
                        updated_by = EXCLUDED.updated_by,
                        updated_at = NOW()
                    """
                ),
                {
                    "symbol": symbol,
                    "category_override": category_override,
                    "enabled": bool(enabled),
                    "reason": reason,
                    "updated_by": updated_by,
                },
            )
            session.commit()

    def disable_category_override(self, symbol: str, *, updated_by: Optional[str] = None) -> None:
        with db.get_session() as session:
            session.execute(
                text(
                    """
                    UPDATE fair_value_v2_category_overrides
                    SET enabled = FALSE,
                        updated_by = COALESCE(:updated_by, updated_by),
                        updated_at = NOW()
                    WHERE symbol = :symbol
                    """
                ),
                {"symbol": symbol, "updated_by": updated_by},
            )
            session.commit()

    def get_company_classification(self, symbol: str) -> Tuple[Optional[str], Optional[str]]:
        with db.get_session() as session:
            row = session.execute(
                text(
                    """
                    SELECT sector, industry
                    FROM fmp_company_profiles
                    WHERE symbol = :symbol
                    LIMIT 1
                    """
                ),
                {"symbol": symbol},
            ).fetchone()

            if row:
                return row[0], row[1]

            snap_row = session.execute(
                text(
                    """
                    SELECT payload
                    FROM stock_insights_snapshots
                    WHERE stock_symbol = :symbol
                      AND source = 'fmp_fundamentals'
                    ORDER BY generated_at DESC
                    LIMIT 1
                    """
                ),
                {"symbol": symbol},
            ).fetchone()
            if not snap_row:
                return None, None

            payload = snap_row[0] or {}
            fundamentals = (payload or {}).get("fundamentals") or {}
            sector = fundamentals.get("sector")
            industry = fundamentals.get("industry")
            return sector, industry

    def get_company_profile_text(self, symbol: str) -> Tuple[Optional[str], Optional[str]]:
        with db.get_session() as session:
            row = session.execute(
                text(
                    """
                    SELECT company_name, description
                    FROM fmp_company_profiles
                    WHERE symbol = :symbol
                    LIMIT 1
                    """
                ),
                {"symbol": symbol},
            ).fetchone()

            company_name = row[0] if row else None
            description = row[1] if row else None

            if (company_name and str(company_name).strip()) or (description and str(description).strip()):
                return company_name, description

            snap_row = session.execute(
                text(
                    """
                    SELECT payload
                    FROM stock_insights_snapshots
                    WHERE stock_symbol = :symbol
                      AND source = 'fmp_fundamentals'
                    ORDER BY generated_at DESC
                    LIMIT 1
                    """
                ),
                {"symbol": symbol},
            ).fetchone()
            if not snap_row:
                return company_name, description

            payload = snap_row[0] or {}
            fundamentals = (payload or {}).get("fundamentals") or {}

            def _pick(*keys: str) -> Optional[str]:
                for k in keys:
                    v = fundamentals.get(k)
                    if v is None:
                        continue
                    s = str(v).strip()
                    if s:
                        return s
                return None

            company_name = company_name or _pick("company_name", "companyName", "name")
            description = description or _pick("description", "businessSummary", "summary")
            return company_name, description

    def get_snapshot_payload(self, symbol: str, as_of_ts: datetime, source: str) -> Tuple[Optional[Dict[str, Any]], Optional[datetime]]:
        with db.get_session() as session:
            row = session.execute(
                text(
                    """
                    SELECT payload, generated_at
                    FROM stock_insights_snapshots
                    WHERE stock_symbol = :symbol
                      AND source = :source
                      AND generated_at <= :as_of_ts
                    ORDER BY generated_at DESC
                    LIMIT 1
                    """
                ),
                {"symbol": symbol, "source": source, "as_of_ts": as_of_ts},
            ).fetchone()

            if not row:
                return None, None
            return row[0], row[1]

    def get_table_scalar(
        self,
        symbol: str,
        as_of_ts: datetime,
        table: str,
        column: str,
        as_of_column: str,
        order_by_column: str,
        where_not_null: bool,
        where: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Optional[float], Optional[Any]]:
        ident_re = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
        for ident_name, ident in (
            ("table", table),
            ("column", column),
            ("as_of_column", as_of_column),
            ("order_by_column", order_by_column),
        ):
            if not ident_re.match(str(ident or "")):
                raise ValueError(f"invalid identifier for {ident_name}: {ident}")
        if order_by_column != as_of_column:
            raise ValueError("order_by_column must equal as_of_column")

        where = where or {}
        for k in where.keys():
            if not ident_re.match(str(k or "")):
                raise ValueError(f"invalid identifier for where column: {k}")

        as_of_value: Any
        if table == "financial_ratios":
            as_of_value = as_of_ts.date()
        else:
            as_of_value = as_of_ts

        where_extra = f" AND {column} IS NOT NULL" if where_not_null else ""
        where_filters_sql = "".join([f" AND {k} = :w_{k}" for k in where.keys()])
        sql = f"""
        SELECT {column}, {as_of_column}
        FROM {table}
        WHERE symbol = :symbol
          AND {as_of_column} <= :as_of
          {where_extra}
          {where_filters_sql}
        ORDER BY {order_by_column} DESC
        LIMIT 1
        """

        with db.get_session() as session:
            params: Dict[str, Any] = {"symbol": symbol, "as_of": as_of_value}
            for k, v in where.items():
                params[f"w_{k}"] = v
            row = session.execute(
                text(sql),
                params,
            ).fetchone()
            if not row:
                return None, None
            raw = row[0]
            ts = row[1]
            try:
                v = float(raw) if raw is not None else None
            except Exception:
                v = None
            return v, ts

    def get_macro_scalar(
        self,
        as_of_ts: datetime,
        column: str,
        as_of_column: str = "data_date",
    ) -> Tuple[Optional[float], Optional[Any]]:
        ident_re = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
        for ident_name, ident in (("column", column), ("as_of_column", as_of_column)):
            if not ident_re.match(str(ident or "")):
                raise ValueError(f"invalid identifier for {ident_name}: {ident}")

        # macro_market_data is keyed by date.
        as_of_value = as_of_ts.date()
        sql = f"""
        SELECT {column}, {as_of_column}
        FROM macro_market_data
        WHERE {as_of_column} <= :as_of
          AND {column} IS NOT NULL
        ORDER BY {as_of_column} DESC
        LIMIT 1
        """

        with db.get_session() as session:
            row = session.execute(text(sql), {"as_of": as_of_value}).fetchone()
            if not row:
                return None, None
            raw = row[0]
            ts = row[1]
            try:
                v = float(raw) if raw is not None else None
            except Exception:
                v = None
            return v, ts

    def get_features_for_pb_bank(self, symbol: str, as_of_ts: datetime) -> FeatureRow:
        scalars: Dict[str, Any] = {}
        sources: Dict[str, str] = {}
        quality: Dict[str, Any] = {}

        with db.get_session() as session:
            # book_value_per_share from fmp_key_metrics_ttm snapshot, point-in-time by generated_at
            key_metrics_row = session.execute(
                text(
                    """
                    SELECT payload->'key_metrics_ttm' as metrics, generated_at
                    FROM stock_insights_snapshots
                    WHERE stock_symbol = :symbol
                      AND source = 'fmp_key_metrics_ttm'
                      AND generated_at <= :as_of_ts
                    ORDER BY generated_at DESC
                    LIMIT 1
                    """
                ),
                {"symbol": symbol, "as_of_ts": as_of_ts},
            ).fetchone()

            bvps = None
            quality["book_value_per_share_row_found"] = bool(key_metrics_row)
            quality["book_value_per_share_payload_found"] = bool(key_metrics_row and key_metrics_row[0])
            if key_metrics_row and key_metrics_row[0]:
                metrics = key_metrics_row[0]
                try:
                    raw = (metrics or {}).get("bookValueperShareTTM")
                    quality["book_value_per_share_raw"] = raw
                    quality["book_value_per_share_key_present"] = "bookValueperShareTTM" in (metrics or {})
                    bvps = float(raw) if raw is not None else None
                    sources["book_value_per_share"] = "stock_insights_snapshots.fmp_key_metrics_ttm.payload.key_metrics_ttm.bookValueperShareTTM"
                    quality["book_value_per_share_generated_at"] = str(key_metrics_row[1]) if key_metrics_row[1] is not None else None
                except Exception:
                    quality["book_value_per_share_parse_error"] = True
                    bvps = None

            scalars["book_value_per_share"] = bvps

            # roe from financial_ratios as-of fiscal_date_ending (date)
            ratios_row = session.execute(
                text(
                    """
                    SELECT roe, fiscal_date_ending
                    FROM financial_ratios
                    WHERE symbol = :symbol
                      AND fiscal_date_ending <= :as_of_date
                      AND roe IS NOT NULL
                    ORDER BY fiscal_date_ending DESC
                    LIMIT 1
                    """
                ),
                {"symbol": symbol, "as_of_date": as_of_ts.date()},
            ).fetchone()

            roe = None
            quality["roe_row_found"] = bool(ratios_row)
            quality["roe_nulls_skipped"] = True
            if ratios_row:
                try:
                    raw_roe = ratios_row[0]
                    quality["roe_raw"] = raw_roe
                    roe = float(raw_roe) if raw_roe is not None else None
                    sources["roe"] = "financial_ratios.roe"
                    quality["roe_fiscal_date_ending"] = str(ratios_row[1]) if ratios_row[1] is not None else None
                except Exception:
                    quality["roe_parse_error"] = True
                    roe = None

            scalars["roe"] = roe

        return FeatureRow(
            symbol=symbol,
            as_of_ts=as_of_ts,
            scalars=scalars,
            series={},
            sources=sources,
            quality=quality,
        )

    def get_features_for_pe_forward(self, symbol: str, as_of_ts: datetime) -> FeatureRow:
        scalars: Dict[str, Any] = {}
        sources: Dict[str, str] = {}
        quality: Dict[str, Any] = {}

        with db.get_session() as session:
            key_metrics_row = session.execute(
                text(
                    """
                    SELECT payload->'key_metrics_ttm' as metrics, generated_at
                    FROM stock_insights_snapshots
                    WHERE stock_symbol = :symbol
                      AND source = 'fmp_key_metrics_ttm'
                      AND generated_at <= :as_of_ts
                    ORDER BY generated_at DESC
                    LIMIT 1
                    """
                ),
                {"symbol": symbol, "as_of_ts": as_of_ts},
            ).fetchone()

            eps_forward = None
            quality["eps_forward_row_found"] = bool(key_metrics_row)
            quality["eps_forward_payload_found"] = bool(key_metrics_row and key_metrics_row[0])
            if key_metrics_row and key_metrics_row[0]:
                metrics = key_metrics_row[0]
                keys = [
                    "epsForward",
                    "epsForwardTTM",
                    "epsNextYear",
                    "epsEstimatedNextYear",
                ]
                quality["eps_forward_candidate_keys"] = keys
                raw = None
                key_used = None
                for k in keys:
                    if k in (metrics or {}) and (metrics or {}).get(k) is not None:
                        raw = (metrics or {}).get(k)
                        key_used = k
                        break
                quality["eps_forward_raw"] = raw
                quality["eps_forward_key_used"] = key_used
                quality["eps_forward_generated_at"] = str(key_metrics_row[1]) if key_metrics_row[1] is not None else None
                try:
                    eps_forward = float(raw) if raw is not None else None
                    if key_used:
                        sources["eps_forward"] = (
                            "stock_insights_snapshots.fmp_key_metrics_ttm.payload.key_metrics_ttm." + str(key_used)
                        )
                except Exception:
                    quality["eps_forward_parse_error"] = True
                    eps_forward = None

            scalars["eps_forward"] = eps_forward

        return FeatureRow(
            symbol=symbol,
            as_of_ts=as_of_ts,
            scalars=scalars,
            series={},
            sources=sources,
            quality=quality,
        )

    def get_features_for_pe_basic(self, symbol: str, as_of_ts: datetime) -> FeatureRow:
        scalars: Dict[str, Any] = {}
        sources: Dict[str, str] = {}
        quality: Dict[str, Any] = {}

        with db.get_session() as session:
            key_metrics_row = session.execute(
                text(
                    """
                    SELECT payload->'key_metrics_ttm' as metrics, generated_at
                    FROM stock_insights_snapshots
                    WHERE stock_symbol = :symbol
                      AND source = 'fmp_key_metrics_ttm'
                      AND generated_at <= :as_of_ts
                    ORDER BY generated_at DESC
                    LIMIT 1
                    """
                ),
                {"symbol": symbol, "as_of_ts": as_of_ts},
            ).fetchone()

            eps_ttm = None
            quality["eps_ttm_row_found"] = bool(key_metrics_row)
            quality["eps_ttm_payload_found"] = bool(key_metrics_row and key_metrics_row[0])
            metrics = None
            if key_metrics_row and key_metrics_row[0]:
                metrics = key_metrics_row[0]
                keys = [
                    "netIncomePerShareTTM",
                    "epsTTM",
                    "epsDilutedTTM",
                    "eps",
                ]
                quality["eps_ttm_candidate_keys"] = keys
                try:
                    metric_keys = list((metrics or {}).keys())
                    quality["metrics_key_count"] = len(metric_keys)
                    quality["metrics_eps_like_keys"] = sorted(
                        [k for k in metric_keys if ("eps" in str(k).lower() or "pershare" in str(k).lower())]
                    )[:50]
                    quality["metrics_pe_like_keys"] = sorted([k for k in metric_keys if "pe" in str(k).lower()])[:50]
                except Exception:
                    pass
                raw = None
                key_used = None
                for k in keys:
                    if k in (metrics or {}) and (metrics or {}).get(k) is not None:
                        raw = (metrics or {}).get(k)
                        key_used = k
                        break
                quality["eps_ttm_raw"] = raw
                quality["eps_ttm_key_used"] = key_used
                quality["eps_ttm_generated_at"] = str(key_metrics_row[1]) if key_metrics_row[1] is not None else None
                try:
                    eps_ttm = float(raw) if raw is not None else None
                    if key_used:
                        sources["eps_ttm"] = (
                            "stock_insights_snapshots.fmp_key_metrics_ttm.payload.key_metrics_ttm." + str(key_used)
                        )
                except Exception:
                    quality["eps_ttm_parse_error"] = True
                    eps_ttm = None

            if eps_ttm is None and metrics:
                pe_keys = ["peRatioTTM", "peRatio", "trailingPE", "pe"]
                pe_raw = None
                pe_key_used = None
                for k in pe_keys:
                    if k in (metrics or {}) and (metrics or {}).get(k) is not None:
                        pe_raw = (metrics or {}).get(k)
                        pe_key_used = k
                        break

                quality["pe_ttm_candidate_keys"] = pe_keys
                quality["pe_ttm_raw"] = pe_raw
                quality["pe_ttm_key_used"] = pe_key_used

                price_row = session.execute(
                    text(
                        """
                        SELECT price, price_timestamp
                        FROM fmp_real_time_prices
                        WHERE symbol = :symbol
                          AND price_timestamp <= :as_of_ts
                        ORDER BY price_timestamp DESC
                        LIMIT 1
                        """
                    ),
                    {"symbol": symbol, "as_of_ts": as_of_ts},
                ).fetchone()

                price = None
                quality["price_row_found"] = bool(price_row)
                if price_row:
                    try:
                        price = float(price_row[0]) if price_row[0] is not None else None
                        quality["price_raw"] = price_row[0]
                        quality["price_timestamp"] = str(price_row[1]) if price_row[1] is not None else None
                        sources["current_price"] = "fmp_real_time_prices.price"
                    except Exception:
                        quality["price_parse_error"] = True
                        price = None

                try:
                    pe = float(pe_raw) if pe_raw is not None else None
                except Exception:
                    pe = None
                    quality["pe_parse_error"] = True

                if price is not None and pe is not None and pe > 0:
                    eps_ttm = price / pe
                    scalars["eps_ttm"] = eps_ttm
                    sources["eps_ttm"] = (
                        "derived: fmp_real_time_prices.price / stock_insights_snapshots.fmp_key_metrics_ttm.payload.key_metrics_ttm."
                        + str(pe_key_used)
                    )
                    quality["eps_ttm_derived"] = True
                else:
                    quality["eps_ttm_derived"] = False

            scalars["eps_ttm"] = eps_ttm

        return FeatureRow(
            symbol=symbol,
            as_of_ts=as_of_ts,
            scalars=scalars,
            series={},
            sources=sources,
            quality=quality,
        )
