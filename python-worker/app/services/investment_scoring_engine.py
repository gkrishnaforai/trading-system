from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from app.database import db
from app.observability.logging import get_logger
from app.services.investment_health_service import InvestmentHealthService
from app.services.company_profile_scores_service import company_profile_scores_service
from app.services.company_profile_scores_auto_service import company_profile_scores_auto_service


logger = get_logger("investment_scoring_engine")


@dataclass
class InvestmentScoreRow:
    symbol: str
    company_name: Optional[str]
    as_of_date: str
    scoring_version: str
    business_score: Optional[float]
    growth_score: Optional[float]
    valuation_score: Optional[float]
    technical_score: Optional[float]
    investment_score: Optional[float]
    business_reason_json: Dict[str, Any]
    growth_reason_json: Dict[str, Any]
    valuation_reason_json: Dict[str, Any]
    technical_reason_json: Dict[str, Any]


class InvestmentScoringEngine:
    def __init__(self):
        self._health = InvestmentHealthService()

    def ensure_tables(self) -> None:
        db.execute_query(
            """
            CREATE TABLE IF NOT EXISTS investment_scores (
                symbol VARCHAR(32) NOT NULL,
                company_name TEXT,
                as_of_date DATE NOT NULL,
                scoring_version VARCHAR(32) NOT NULL,

                business_score DOUBLE PRECISION,
                growth_score DOUBLE PRECISION,
                valuation_score DOUBLE PRECISION,
                technical_score DOUBLE PRECISION,
                investment_score DOUBLE PRECISION,

                business_reason_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                growth_reason_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                valuation_reason_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                technical_reason_json JSONB NOT NULL DEFAULT '{}'::jsonb,

                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

                PRIMARY KEY (symbol, as_of_date, scoring_version)
            );

            CREATE INDEX IF NOT EXISTS idx_investment_scores_symbol_date
                ON investment_scores(symbol, as_of_date DESC, scoring_version DESC);
            """
        )

    def _get_company_name(self, symbol: str) -> Optional[str]:
        try:
            rows = db.execute_query(
                """
                SELECT company_name
                FROM fmp_company_profiles
                WHERE symbol = :symbol
                LIMIT 1
                """,
                {"symbol": symbol.upper()},
            )
            if not rows:
                return None
            return str(dict(rows[0]).get("company_name") or "") or None
        except Exception:
            return None

    def _get_latest_company_profile_scores_asof(
        self,
        *,
        symbol: str,
        as_of_date_str: str,
        scoring_version: str,
    ) -> Optional[Dict[str, Any]]:
        """Fetch latest manual qualitative scores with as_of_date <= requested as_of_date.

        This makes quarterly/manual updates naturally apply to all subsequent daily scoring runs.
        """

        company_profile_scores_service.ensure_tables()
        company_profile_scores_auto_service.ensure_tables()

        manual_row: Optional[Dict[str, Any]] = None
        auto_row: Optional[Dict[str, Any]] = None

        try:
            rows = db.execute_query(
                """
                SELECT *
                FROM company_profile_scores
                WHERE symbol = :symbol
                  AND scoring_version = :scoring_version
                  AND as_of_date <= CAST(:as_of_date AS date)
                ORDER BY as_of_date DESC
                LIMIT 1
                """,
                {"symbol": symbol.upper(), "scoring_version": scoring_version, "as_of_date": as_of_date_str},
            )
            if not rows:
                rows = db.execute_query(
                    """
                    SELECT *
                    FROM company_profile_scores
                    WHERE symbol = :symbol
                      AND as_of_date <= CAST(:as_of_date AS date)
                    ORDER BY as_of_date DESC, scoring_version DESC
                    LIMIT 1
                    """,
                    {"symbol": symbol.upper(), "as_of_date": as_of_date_str},
                )
            if rows:
                manual_row = dict(rows[0])
        except Exception:
            manual_row = None

        try:
            auto_row = company_profile_scores_auto_service.get_latest_asof(
                symbol=symbol.upper(),
                as_of_date_str=as_of_date_str,
                scoring_version=scoring_version,
            )
        except Exception:
            auto_row = None

        return {
            "manual": manual_row,
            "auto": auto_row,
            "effective": manual_row if manual_row is not None else auto_row,
        }

    def _renorm_weighted(self, components: Dict[str, Optional[float]], weights: Dict[str, float]) -> Tuple[Optional[float], Dict[str, float]]:
        avail = {k: v for k, v in components.items() if v is not None}
        if not avail:
            return None, {}
        denom = sum(weights.get(k, 0.0) for k in avail.keys())
        if denom <= 0:
            return None, {}
        score = 0.0
        for k, v in avail.items():
            score += (weights.get(k, 0.0) / denom) * float(v)
        return float(score), {k: (weights.get(k, 0.0) / denom) for k in avail.keys()}

    def compute_for_symbol(
        self,
        *,
        symbol: str,
        as_of_date_str: str,
        scoring_version: str = "v1",
    ) -> InvestmentScoreRow:
        self.ensure_tables()

        sym = (symbol or "").strip().upper()
        if not sym:
            raise ValueError("symbol is required")

        company_name = self._get_company_name(sym)

        valuation_score, valuation_inputs, valuation_reasons = self._health._compute_valuation(sym)
        fundamentals_score, fundamentals_inputs, fundamentals_reasons = self._health._compute_fundamentals(sym)
        technical_score, technical_inputs, technical_reasons = self._health._compute_technical(sym, as_of_date_str)

        modules = (fundamentals_inputs or {}).get("modules") or {}
        business_score = None
        growth_score = None
        try:
            bq = (modules.get("business_quality") or {}).get("score")
            business_score = float(bq) if bq is not None else None
        except Exception:
            business_score = None
        try:
            ag = (modules.get("ai_growth") or {}).get("score")
            growth_score = float(ag) if ag is not None else None
        except Exception:
            growth_score = None

        business_reason_json: Dict[str, Any] = {
            "score": business_score,
            "explain": (modules.get("business_quality") or {}),
        }
        growth_reason_json: Dict[str, Any] = {
            "score": growth_score,
            "explain": (modules.get("ai_growth") or {}),
        }
        valuation_reason_json: Dict[str, Any] = {
            "score": valuation_score,
            "inputs": valuation_inputs,
            "reasons": valuation_reasons,
        }
        technical_reason_json: Dict[str, Any] = {
            "score": technical_score,
            "inputs": technical_inputs,
            "reasons": technical_reasons,
        }

        # Blend in manual qualitative company profile scores as an overlay (source-of-truth table).
        manual_bundle = self._get_latest_company_profile_scores_asof(
            symbol=sym,
            as_of_date_str=as_of_date_str,
            scoring_version=scoring_version,
        )
        manual = (manual_bundle or {}).get("effective") if isinstance(manual_bundle, dict) else None
        manual_score = None
        if manual is not None:
            try:
                vals = []
                for k in [
                    "moat_score",
                    "leadership_score",
                    "recurring_revenue_score",
                    "ai_optionality_score",
                ]:
                    v = manual.get(k)
                    if v is not None:
                        vals.append(float(v))
                if vals:
                    manual_score = sum(vals) / float(len(vals))
            except Exception:
                manual_score = None

        business_reason_json["company_profile_overlay"] = manual_bundle
        business_reason_json["manual_company_profile_avg"] = manual_score

        if manual_score is not None and business_score is not None:
            # v1 blend: mostly quantitative, but allow qualitative conviction to move the needle.
            business_score = 0.65 * float(business_score) + 0.35 * float(manual_score)
        elif manual_score is not None and business_score is None:
            business_score = float(manual_score)

        weights = {
            "business": 0.35,
            "growth": 0.25,
            "valuation": 0.25,
            "technical": 0.15,
        }
        components = {
            "business": business_score,
            "growth": growth_score,
            "valuation": valuation_score,
            "technical": technical_score,
        }
        investment_score, weights_normalized = self._renorm_weighted(components, weights)

        # Persist weights used for auditability.
        business_reason_json["weights"] = weights
        business_reason_json["weights_normalized"] = weights_normalized

        return InvestmentScoreRow(
            symbol=sym,
            company_name=company_name,
            as_of_date=as_of_date_str,
            scoring_version=scoring_version,
            business_score=business_score,
            growth_score=growth_score,
            valuation_score=valuation_score,
            technical_score=technical_score,
            investment_score=investment_score,
            business_reason_json=business_reason_json,
            growth_reason_json=growth_reason_json,
            valuation_reason_json=valuation_reason_json,
            technical_reason_json=technical_reason_json,
        )

    def upsert(self, row: InvestmentScoreRow) -> None:
        self.ensure_tables()
        db.execute_update(
            """
            INSERT INTO investment_scores (
                symbol,
                company_name,
                as_of_date,
                scoring_version,
                business_score,
                growth_score,
                valuation_score,
                technical_score,
                investment_score,
                business_reason_json,
                growth_reason_json,
                valuation_reason_json,
                technical_reason_json
            ) VALUES (
                :symbol,
                :company_name,
                CAST(:as_of_date AS date),
                :scoring_version,
                :business_score,
                :growth_score,
                :valuation_score,
                :technical_score,
                :investment_score,
                CAST(:business_reason_json AS jsonb),
                CAST(:growth_reason_json AS jsonb),
                CAST(:valuation_reason_json AS jsonb),
                CAST(:technical_reason_json AS jsonb)
            )
            ON CONFLICT (symbol, as_of_date, scoring_version)
            DO UPDATE SET
                company_name = EXCLUDED.company_name,
                business_score = EXCLUDED.business_score,
                growth_score = EXCLUDED.growth_score,
                valuation_score = EXCLUDED.valuation_score,
                technical_score = EXCLUDED.technical_score,
                investment_score = EXCLUDED.investment_score,
                business_reason_json = EXCLUDED.business_reason_json,
                growth_reason_json = EXCLUDED.growth_reason_json,
                valuation_reason_json = EXCLUDED.valuation_reason_json,
                technical_reason_json = EXCLUDED.technical_reason_json;
            """,
            {
                "symbol": row.symbol,
                "company_name": row.company_name,
                "as_of_date": row.as_of_date,
                "scoring_version": row.scoring_version,
                "business_score": row.business_score,
                "growth_score": row.growth_score,
                "valuation_score": row.valuation_score,
                "technical_score": row.technical_score,
                "investment_score": row.investment_score,
                "business_reason_json": json.dumps(row.business_reason_json or {}),
                "growth_reason_json": json.dumps(row.growth_reason_json or {}),
                "valuation_reason_json": json.dumps(row.valuation_reason_json or {}),
                "technical_reason_json": json.dumps(row.technical_reason_json or {}),
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
                FROM investment_scores
                WHERE symbol = :symbol AND scoring_version = :scoring_version
                ORDER BY as_of_date DESC
                LIMIT 1
            """
            params = {"symbol": sym, "scoring_version": scoring_version}
        else:
            q = """
                SELECT *
                FROM investment_scores
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
            FROM investment_scores
            WHERE symbol = :symbol
            ORDER BY as_of_date DESC, scoring_version DESC
            LIMIT :lim
            """,
            {"symbol": sym, "lim": int(limit)},
        )
        return [dict(r) for r in (rows or [])]


investment_scoring_engine = InvestmentScoringEngine()
