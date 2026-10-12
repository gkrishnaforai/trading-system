from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app.database import db
from app.factor_engine.models import FactorSnapshot


_DEFAULT_CATALYST_FACTOR_IDS: List[str] = [
    "catalyst.earnings_days_to",
    "catalyst.earnings_within_7d",
    "catalyst.earnings_within_14d",
    "catalyst.earnings_within_21d",
    "catalyst.earnings_time",
    "catalyst.ai_news_recent_30d",
    "catalyst.ai_news_30d_count",
]


@dataclass(frozen=True)
class CatalystProviderResult:
    symbol: str
    as_of_date: date
    source: str
    factors: Dict[str, FactorSnapshot]


class CatalystProvider:
    """CatalystProvider v1.

    v1 scope: normalize `earnings_calendar` schema variants and expose upcoming earnings-derived
    catalyst factors.

    Canonical behavior:
    - pick the nearest upcoming earnings date where earnings_date >= as_of_date
    - if none exists, return None

    Schema variants handled:
    - date column: `earnings_date` (preferred) or `report_date`
    - time column: `earnings_time` (preferred) or `time`
    """

    def get_latest(
        self,
        symbol: str,
        factor_ids: Optional[Iterable[str]] = None,
    ) -> Optional[CatalystProviderResult]:
        symbol = symbol.upper()
        factor_ids_list = list(factor_ids) if factor_ids is not None else list(_DEFAULT_CATALYST_FACTOR_IDS)
        return self.get_asof(symbol, date.today(), factor_ids=factor_ids_list)

    def get_asof(
        self,
        symbol: str,
        as_of_date: date,
        factor_ids: Optional[Iterable[str]] = None,
    ) -> Optional[CatalystProviderResult]:
        symbol = symbol.upper()
        factor_ids_list = list(factor_ids) if factor_ids is not None else list(_DEFAULT_CATALYST_FACTOR_IDS)

        date_col, time_col = self._resolve_schema()
        # Earnings calendar can be missing or have unexpected schema in some environments.
        # AI-news catalysts should still work even if earnings_calendar is unavailable.

        factors: Dict[str, FactorSnapshot] = {}

        def put(
            fid: str,
            value: Any,
            confidence: int,
            meta: Optional[Dict[str, Any]] = None,
            source: str = "earnings_calendar",
        ) -> None:
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
                source=source,
                source_timestamp=None,
                metadata=meta,
            )

        if date_col is not None:
            rec = self._fetch_next_earnings(symbol=symbol, as_of_date=as_of_date, date_col=date_col, time_col=time_col)
        else:
            rec = None

        if rec is not None:
            earnings_dt, earnings_time = rec
            try:
                days_to = int((earnings_dt - as_of_date).days)
            except Exception:
                days_to = None

            if days_to is not None and days_to >= 0:
                conf_date = 90
                conf_time = 70 if earnings_time else 40

                put(
                    "catalyst.earnings_days_to",
                    days_to,
                    conf_date,
                    meta={"earnings_date": earnings_dt.isoformat()},
                )
                put("catalyst.earnings_within_7d", days_to <= 7, conf_date)
                put("catalyst.earnings_within_14d", days_to <= 14, conf_date)
                put("catalyst.earnings_within_21d", days_to <= 21, conf_date)

                if "catalyst.earnings_time" in factor_ids_list and time_col is not None:
                    put(
                        "catalyst.earnings_time",
                        earnings_time,
                        conf_time,
                        meta={"column": time_col},
                    )

        ai_count, ai_latest, ai_keyword_hits = self._fetch_ai_news_signal(symbol=symbol, as_of_date=as_of_date)
        if ai_count is not None:
            ai_recent = ai_count > 0
            conf_ai = 80 if ai_recent else 40
            meta = {
                "window_days": 30,
                "latest_published_date": ai_latest,
                "keyword_hit_counts": ai_keyword_hits,
            }
            put("catalyst.ai_news_recent_30d", ai_recent, conf_ai, meta=meta, source="stock_news")
            put("catalyst.ai_news_30d_count", ai_count, conf_ai, meta=meta, source="stock_news")

        if not factors:
            return None

        return CatalystProviderResult(
            symbol=symbol,
            as_of_date=as_of_date,
            source="catalyst_provider.v1",
            factors=factors,
        )

    def _fetch_ai_news_signal(
        self,
        symbol: str,
        as_of_date: date,
    ) -> Tuple[Optional[int], Optional[str], Dict[str, int]]:
        # Heuristic v1: look for recent AI/product/model keywords in market news mentioning the symbol.
        # Uses fmp_market_news.symbols (JSON list) and keyword matching in title/text.
        keywords = [
            "artificial intelligence",
            "generative ai",
            "genai",
            "llm",
            "large language model",
            "foundation model",
            "new model",
            "ai model",
            "agent",
            "copilot",
            "inference",
            "training",
            "gpt",
            "chatgpt",
            "openai",
            "anthropic",
            "claude",
            "llama",
        ]

        where_kw = " OR ".join([f"COALESCE(title,'') ILIKE :kw{i} OR COALESCE(text,'') ILIKE :kw{i}" for i in range(len(keywords))])
        # Extra acronym match for standalone AI (avoid %ai% which matches 'said', etc.)
        # Use raw_json::text so this works for both stock_news and fmp_market_news queries.
        where_ai_acronym = "COALESCE(title,'') ~* :ai_word OR COALESCE(raw_json::text,'') ~* :ai_word"
        params: Dict[str, Any] = {
            "symbol": symbol,
            "as_of_date": as_of_date.isoformat(),
            "ai_word": r"(^|\\W)AI(\\W|$)",
        }
        for i, kw in enumerate(keywords):
            params[f"kw{i}"] = f"%{kw}%"

        where_kw_stock = " OR ".join(
            [
                f"COALESCE(title,'') ILIKE :kw{i} OR COALESCE(raw_json::text,'') ILIKE :kw{i}"
                for i in range(len(keywords))
            ]
        )

        q = f"""
            SELECT
                COUNT(*)::int AS cnt,
                MAX(published_at) AS latest
            FROM stock_news
            WHERE published_at IS NOT NULL
              AND published_at >= (CAST(:as_of_date AS date) - INTERVAL '30 days')
              AND (COALESCE(related_symbols, '{{}}'::jsonb) ? :symbol)
              AND (({where_kw_stock}) OR ({where_ai_acronym}))
        """

        # Fallback: fmp_market_news
        q_fallback = f"""
            SELECT
                COUNT(*)::int AS cnt,
                MAX(published_date) AS latest
            FROM fmp_market_news
            WHERE published_date IS NOT NULL
              AND published_date >= (CAST(:as_of_date AS date) - INTERVAL '30 days')
              AND (COALESCE(CAST(symbols AS jsonb), '[]'::jsonb) ? :symbol)
              AND (({where_kw}) OR ({where_ai_acronym}))
        """

        rows = db.execute_query(q, params)
        if not rows:
            rows = db.execute_query(q_fallback, params)
        if not rows:
            return (0, None, {})

        r = rows[0]
        cnt = r.get("cnt")
        latest = r.get("latest")
        try:
            cnt_i = int(cnt) if cnt is not None else 0
        except Exception:
            cnt_i = 0

        latest_s: Optional[str]
        if latest is None:
            latest_s = None
        else:
            latest_s = str(latest)

        # Provide a lightweight breakdown of keyword hits for transparency.
        keyword_hits: Dict[str, int] = {}
        if cnt_i > 0:
            for kw in keywords:
                keyword_hits[kw] = 0

            q2 = """
                SELECT title, text
                FROM fmp_market_news
                WHERE published_date IS NOT NULL
                  AND published_date >= (CAST(:as_of_date AS date) - INTERVAL '30 days')
                  AND (CAST(symbols AS jsonb) ? :symbol)
                ORDER BY published_date DESC
                LIMIT 25
            """
            rows2 = db.execute_query(q2, {"symbol": symbol, "as_of_date": as_of_date.isoformat()})
            for rr in rows2 or []:
                hay = f"{rr.get('title') or ''} {rr.get('text') or ''}".lower()
                for kw in keywords:
                    if kw in hay:
                        keyword_hits[kw] = keyword_hits.get(kw, 0) + 1

            keyword_hits = {k: v for k, v in keyword_hits.items() if v > 0}

        return (cnt_i, latest_s, keyword_hits)

    def _resolve_schema(self) -> Tuple[Optional[str], Optional[str]]:
        if self._has_column("earnings_calendar", "earnings_date"):
            date_col = "earnings_date"
        elif self._has_column("earnings_calendar", "report_date"):
            date_col = "report_date"
        else:
            return (None, None)

        if self._has_column("earnings_calendar", "earnings_time"):
            time_col: Optional[str] = "earnings_time"
        elif self._has_column("earnings_calendar", "time"):
            time_col = "time"
        else:
            time_col = None

        return (date_col, time_col)

    def _fetch_next_earnings(
        self,
        symbol: str,
        as_of_date: date,
        date_col: str,
        time_col: Optional[str],
    ) -> Optional[Tuple[date, Optional[str]]]:
        time_sel = f", {time_col} AS earnings_time" if time_col else ", NULL::text AS earnings_time"
        q = f"""
            SELECT {date_col} AS earnings_date{time_sel}
            FROM earnings_calendar
            WHERE symbol = :symbol
              AND {date_col} IS NOT NULL
              AND CAST({date_col} AS date) >= CAST(:as_of_date AS date)
            ORDER BY CAST({date_col} AS date) ASC
            LIMIT 1
        """
        rows = db.execute_query(q, {"symbol": symbol, "as_of_date": as_of_date.isoformat()})
        if not rows:
            return None

        r = rows[0]
        dt = r.get("earnings_date")
        if dt is None:
            return None

        if isinstance(dt, date):
            earnings_dt = dt
        else:
            try:
                earnings_dt = date.fromisoformat(str(dt)[:10])
            except Exception:
                return None

        et = r.get("earnings_time")
        earnings_time = str(et) if et is not None and str(et).strip() else None
        return (earnings_dt, earnings_time)

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
