"""Persistence for point-in-time fundamental estimate snapshots."""
from __future__ import annotations

import json
from datetime import date
from typing import Iterable, Optional

from app.database import db

from .momentum import FundamentalEstimateSnapshot


class FundamentalEstimateStore:
    def save(self, snapshot: FundamentalEstimateSnapshot) -> None:
        db.execute_update(
            """
            INSERT INTO fundamental_estimate_snapshots (
                symbol, as_of_date, fiscal_period, fiscal_year,
                eps_estimate, revenue_estimate, eps_growth_estimate,
                revenue_growth_estimate, analyst_count, analysts_up,
                analysts_down, analysts_unchanged, guidance_direction,
                provider, source_timestamp
            ) VALUES (
                :symbol, :as_of_date, :fiscal_period, :fiscal_year,
                :eps_estimate, :revenue_estimate, :eps_growth_estimate,
                :revenue_growth_estimate, :analyst_count, :analysts_up,
                :analysts_down, :analysts_unchanged, :guidance_direction,
                :provider, :source_timestamp
            )
            ON CONFLICT (symbol, as_of_date, fiscal_period, fiscal_year, provider)
            DO UPDATE SET
                eps_estimate = EXCLUDED.eps_estimate,
                revenue_estimate = EXCLUDED.revenue_estimate,
                eps_growth_estimate = EXCLUDED.eps_growth_estimate,
                revenue_growth_estimate = EXCLUDED.revenue_growth_estimate,
                analyst_count = EXCLUDED.analyst_count,
                analysts_up = EXCLUDED.analysts_up,
                analysts_down = EXCLUDED.analysts_down,
                analysts_unchanged = EXCLUDED.analysts_unchanged,
                guidance_direction = EXCLUDED.guidance_direction,
                source_timestamp = EXCLUDED.source_timestamp
            """,
            {**snapshot.model_dump(mode="json"), "as_of_date": snapshot.as_of.isoformat()},
        )

    def latest_as_of(self, symbol: str) -> Optional[date]:
        """High-water mark: most recent snapshot date for the symbol.
        Used to skip provider refetches once today's partition exists —
        durable across restarts, unlike the in-memory market-data cache."""
        rows = db.execute_query(
            "SELECT max(as_of_date) AS d FROM fundamental_estimate_snapshots "
            "WHERE symbol = :symbol",
            {"symbol": symbol.upper()},
        )
        return rows[0]["d"] if rows else None

    def latest_as_of_batch(self, symbols: Iterable[str]
                           ) -> dict[str, Optional[date]]:
        """One GROUP BY query for a whole universe — the per-symbol
        watermark check in the screener used to cost ~170 sync
        roundtrips on the event loop."""
        syms = [s.upper() for s in symbols]
        if not syms:
            return {}
        rows = db.execute_query(
            "SELECT symbol, max(as_of_date) AS d "
            "FROM fundamental_estimate_snapshots "
            "WHERE symbol = ANY(:s) GROUP BY symbol", {"s": syms})
        return {r["symbol"]: r["d"] for r in rows}

    def history(self, symbol: str, fiscal_period: str, fiscal_year: int, limit: int = 100) -> list[FundamentalEstimateSnapshot]:
        rows = db.execute_query(
            """
            SELECT symbol, as_of_date AS as_of, fiscal_period, fiscal_year,
                   eps_estimate, revenue_estimate, eps_growth_estimate,
                   revenue_growth_estimate, analyst_count, analysts_up,
                   analysts_down, analysts_unchanged, guidance_direction,
                   provider, source_timestamp::date AS source_timestamp
            FROM fundamental_estimate_snapshots
            WHERE symbol = :symbol AND fiscal_period = :fiscal_period
              AND fiscal_year = :fiscal_year
            ORDER BY as_of_date DESC
            LIMIT :limit
            """,
            {"symbol": symbol.upper(), "fiscal_period": fiscal_period, "fiscal_year": fiscal_year, "limit": limit},
        )
        return [FundamentalEstimateSnapshot.model_validate(row) for row in rows]
