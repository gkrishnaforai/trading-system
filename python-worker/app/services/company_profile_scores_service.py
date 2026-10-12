from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.database import db
from app.observability.logging import get_logger


logger = get_logger("company_profile_scores_service")


@dataclass
class CompanyProfileScoreRow:
    symbol: str
    as_of_date: str
    scoring_version: str
    moat_score: Optional[float]
    leadership_score: Optional[float]
    recurring_revenue_score: Optional[float]
    ai_optionality_score: Optional[float]
    reason_json: Dict[str, Any]


class CompanyProfileScoresService:
    def ensure_tables(self) -> None:
        db.execute_query(
            """
            CREATE TABLE IF NOT EXISTS company_profile_scores (
                symbol VARCHAR(32) NOT NULL,
                as_of_date DATE NOT NULL,
                scoring_version VARCHAR(32) NOT NULL,

                moat_score DOUBLE PRECISION,
                leadership_score DOUBLE PRECISION,
                recurring_revenue_score DOUBLE PRECISION,
                ai_optionality_score DOUBLE PRECISION,

                reason_json JSONB NOT NULL DEFAULT '{}'::jsonb,

                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

                PRIMARY KEY (symbol, as_of_date, scoring_version)
            );

            CREATE INDEX IF NOT EXISTS idx_company_profile_scores_symbol_date
                ON company_profile_scores(symbol, as_of_date DESC, scoring_version DESC);
            """
        )

    def upsert(self, row: CompanyProfileScoreRow) -> None:
        self.ensure_tables()
        db.execute_update(
            """
            INSERT INTO company_profile_scores (
                symbol,
                as_of_date,
                scoring_version,
                moat_score,
                leadership_score,
                recurring_revenue_score,
                ai_optionality_score,
                reason_json
            ) VALUES (
                :symbol,
                CAST(:as_of_date AS date),
                :scoring_version,
                :moat_score,
                :leadership_score,
                :recurring_revenue_score,
                :ai_optionality_score,
                CAST(:reason_json AS jsonb)
            )
            ON CONFLICT (symbol, as_of_date, scoring_version)
            DO UPDATE SET
                moat_score = EXCLUDED.moat_score,
                leadership_score = EXCLUDED.leadership_score,
                recurring_revenue_score = EXCLUDED.recurring_revenue_score,
                ai_optionality_score = EXCLUDED.ai_optionality_score,
                reason_json = EXCLUDED.reason_json;
            """,
            {
                "symbol": row.symbol.upper(),
                "as_of_date": row.as_of_date,
                "scoring_version": row.scoring_version,
                "moat_score": row.moat_score,
                "leadership_score": row.leadership_score,
                "recurring_revenue_score": row.recurring_revenue_score,
                "ai_optionality_score": row.ai_optionality_score,
                "reason_json": json.dumps(row.reason_json or {}),
            },
        )

    def get_latest(self, *, symbol: str, scoring_version: Optional[str] = None) -> Optional[Dict[str, Any]]:
        self.ensure_tables()
        sym = (symbol or "").strip().upper()
        if not sym:
            return None

        if scoring_version:
            q = """
                SELECT *
                FROM company_profile_scores
                WHERE symbol = :symbol AND scoring_version = :scoring_version
                ORDER BY as_of_date DESC
                LIMIT 1
            """
            params = {"symbol": sym, "scoring_version": scoring_version}
        else:
            q = """
                SELECT *
                FROM company_profile_scores
                WHERE symbol = :symbol
                ORDER BY as_of_date DESC, scoring_version DESC
                LIMIT 1
            """
            params = {"symbol": sym}

        rows = db.execute_query(q, params)
        if not rows:
            return None
        return dict(rows[0])

    def get_history(self, *, symbol: str, limit: int = 60) -> List[Dict[str, Any]]:
        self.ensure_tables()
        sym = (symbol or "").strip().upper()
        if not sym:
            return []

        rows = db.execute_query(
            """
            SELECT *
            FROM company_profile_scores
            WHERE symbol = :symbol
            ORDER BY as_of_date DESC, scoring_version DESC
            LIMIT :lim
            """,
            {"symbol": sym, "lim": int(limit)},
        )
        return [dict(r) for r in (rows or [])]


company_profile_scores_service = CompanyProfileScoresService()
