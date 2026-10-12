from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.database import db
from app.observability.logging import get_logger
from app.services.investment_health_service import InvestmentHealthService


logger = get_logger("company_profile_scores_auto_service")


@dataclass
class CompanyProfileAutoScoreRow:
    symbol: str
    as_of_date: str
    scoring_version: str

    moat_score: Optional[float]
    leadership_score: Optional[float]
    recurring_revenue_score: Optional[float]
    ai_optionality_score: Optional[float]

    reason_json: Dict[str, Any]


class CompanyProfileScoresAutoService:
    def __init__(self) -> None:
        self._health = InvestmentHealthService()

    def ensure_tables(self) -> None:
        db.execute_query(
            """
            CREATE TABLE IF NOT EXISTS company_profile_scores_auto (
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

            CREATE INDEX IF NOT EXISTS idx_company_profile_scores_auto_symbol_date
                ON company_profile_scores_auto(symbol, as_of_date DESC, scoring_version DESC);
            """
        )

    def compute_for_symbol(
        self,
        *,
        symbol: str,
        as_of_date_str: str,
        scoring_version: str = "v1",
    ) -> CompanyProfileAutoScoreRow:
        self.ensure_tables()
        sym = (symbol or "").strip().upper()

        # Proxy mapping (v1):
        # - moat_score ~ quantitative business quality (margins, ROIC, FCF)
        # - leadership_score ~ financial quality proxy (balance sheet + Altman/Piotroski)
        # - recurring_revenue_score ~ stability/profitability proxy blended from the above
        # - ai_optionality_score ~ transcript AI signal intensity (separate from growth)

        bq_score, bq_inputs, bq_reasons = self._health._compute_business_quality(sym)
        fq_score, fq_inputs, fq_reasons = self._health._compute_financial_quality(sym)
        ai_growth_score, ai_inputs, ai_reasons = self._health._compute_ai_growth(sym)

        ai_hits = None
        try:
            ai_hits = int((ai_inputs or {}).get("ai_transcript_keyword_hits") or 0)
        except Exception:
            ai_hits = None

        ai_opt_score: Optional[float] = None
        try:
            if ai_hits is None:
                ai_opt_score = None
            elif ai_hits <= 0:
                ai_opt_score = 40.0
            else:
                ai_opt_score = float(min(95.0, 55.0 + 10.0 * float(min(ai_hits, 4))))
        except Exception:
            ai_opt_score = None

        moat_score = float(bq_score) if bq_score is not None else None
        leadership_score = float(fq_score) if fq_score is not None else None

        recurring_score: Optional[float] = None
        try:
            vals = []
            if moat_score is not None:
                vals.append((moat_score, 0.6))
            if leadership_score is not None:
                vals.append((leadership_score, 0.4))
            if vals:
                denom = sum(w for _, w in vals)
                recurring_score = sum(v * w for v, w in vals) / denom
        except Exception:
            recurring_score = None

        reason_json: Dict[str, Any] = {
            "version": "auto_v1",
            "inputs": {
                "business_quality": {"score": bq_score, "inputs": bq_inputs, "reasons": bq_reasons},
                "financial_quality": {"score": fq_score, "inputs": fq_inputs, "reasons": fq_reasons},
                "ai_growth": {"score": ai_growth_score, "inputs": ai_inputs, "reasons": ai_reasons},
                "ai_optionality": {"ai_hits": ai_hits},
            },
            "mapping": {
                "moat_score": "business_quality.score",
                "leadership_score": "financial_quality.score",
                "recurring_revenue_score": "0.6*moat + 0.4*leadership",
                "ai_optionality_score": "transcript keyword intensity",
            },
        }

        return CompanyProfileAutoScoreRow(
            symbol=sym,
            as_of_date=as_of_date_str,
            scoring_version=scoring_version,
            moat_score=moat_score,
            leadership_score=leadership_score,
            recurring_revenue_score=recurring_score,
            ai_optionality_score=ai_opt_score,
            reason_json=reason_json,
        )

    def upsert(self, row: CompanyProfileAutoScoreRow) -> None:
        self.ensure_tables()
        db.execute_update(
            """
            INSERT INTO company_profile_scores_auto (
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

    def get_latest_asof(
        self,
        *,
        symbol: str,
        as_of_date_str: str,
        scoring_version: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        self.ensure_tables()
        sym = (symbol or "").strip().upper()
        if not sym:
            return None

        if scoring_version:
            q = """
                SELECT *
                FROM company_profile_scores_auto
                WHERE symbol = :symbol
                  AND scoring_version = :scoring_version
                  AND as_of_date <= CAST(:as_of_date AS date)
                ORDER BY as_of_date DESC
                LIMIT 1
            """
            params = {"symbol": sym, "scoring_version": scoring_version, "as_of_date": as_of_date_str}
        else:
            q = """
                SELECT *
                FROM company_profile_scores_auto
                WHERE symbol = :symbol
                  AND as_of_date <= CAST(:as_of_date AS date)
                ORDER BY as_of_date DESC, scoring_version DESC
                LIMIT 1
            """
            params = {"symbol": sym, "as_of_date": as_of_date_str}

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
            FROM company_profile_scores_auto
            WHERE symbol = :symbol
            ORDER BY as_of_date DESC, scoring_version DESC
            LIMIT :lim
            """,
            {"symbol": sym, "lim": int(limit)},
        )
        return [dict(r) for r in (rows or [])]


company_profile_scores_auto_service = CompanyProfileScoresAutoService()
