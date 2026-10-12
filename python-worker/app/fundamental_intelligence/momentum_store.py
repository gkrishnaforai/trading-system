"""Persistence/read access for derived fundamental momentum assessments."""
from __future__ import annotations

import json
from typing import Any, Callable, Optional

from app.database import db

from .momentum import FundamentalMomentumAssessment


class FundamentalMomentumStore:
    def __init__(self, *, execute: Optional[Callable[..., Any]] = None, query: Optional[Callable[..., Any]] = None):
        self._execute = execute or db.execute_update
        self._query = query or db.execute_query

    def save(self, assessment: FundamentalMomentumAssessment, *, as_of_date: str) -> None:
        self._execute(
            """
            INSERT INTO fundamental_momentum_assessments (
                symbol, as_of_date, score, label, eps_revision_14d,
                eps_revision_30d, revenue_revision_30d, growth_acceleration,
                revision_breadth, net_revision_breadth, estimate_dispersion,
                guidance_direction, coverage, reasons, source, rules_version
            ) VALUES (
                :symbol, :as_of_date, :score, :label, :eps_revision_14d,
                :eps_revision_30d, :revenue_revision_30d, :growth_acceleration,
                :revision_breadth, :net_revision_breadth, :estimate_dispersion,
                :guidance_direction, :coverage, CAST(:reasons AS jsonb),
                :source, :rules_version
            )
            ON CONFLICT (symbol, as_of_date, rules_version) DO UPDATE SET
                score = EXCLUDED.score,
                label = EXCLUDED.label,
                eps_revision_14d = EXCLUDED.eps_revision_14d,
                eps_revision_30d = EXCLUDED.eps_revision_30d,
                revenue_revision_30d = EXCLUDED.revenue_revision_30d,
                growth_acceleration = EXCLUDED.growth_acceleration,
                revision_breadth = EXCLUDED.revision_breadth,
                net_revision_breadth = EXCLUDED.net_revision_breadth,
                estimate_dispersion = EXCLUDED.estimate_dispersion,
                guidance_direction = EXCLUDED.guidance_direction,
                coverage = EXCLUDED.coverage,
                reasons = EXCLUDED.reasons,
                source = EXCLUDED.source
            """,
            {
                "symbol": assessment.symbol,
                "as_of_date": as_of_date,
                "score": assessment.score,
                "label": assessment.label,
                "eps_revision_14d": assessment.eps_revision_14d,
                "eps_revision_30d": assessment.eps_revision_30d,
                "revenue_revision_30d": assessment.revenue_revision_30d,
                "growth_acceleration": assessment.growth_acceleration,
                "revision_breadth": assessment.revision_breadth,
                "net_revision_breadth": assessment.net_revision_breadth,
                "estimate_dispersion": assessment.estimate_dispersion,
                "guidance_direction": assessment.guidance_direction,
                "coverage": assessment.coverage,
                "reasons": json.dumps(assessment.reasons),
                "source": assessment.source,
                "rules_version": assessment.rules_version,
            },
        )

    def latest(self, symbol: str) -> Optional[FundamentalMomentumAssessment]:
        rows = self._query(
            """
            SELECT symbol, score, label, eps_revision_14d, eps_revision_30d,
                   revenue_revision_30d, growth_acceleration, revision_breadth,
                   net_revision_breadth, estimate_dispersion, guidance_direction,
                   coverage, reasons, source, rules_version
            FROM fundamental_momentum_assessments
            WHERE symbol = :symbol
            ORDER BY as_of_date DESC, created_at DESC
            LIMIT 1
            """,
            {"symbol": symbol.upper()},
        )
        if not rows:
            return None
        row = rows[0]
        reasons = row.get("reasons") or []
        if isinstance(reasons, str):
            try:
                reasons = json.loads(reasons)
            except ValueError:
                reasons = []
        return FundamentalMomentumAssessment.model_validate({**row, "reasons": reasons})
