"""Append-oriented writer for canonical portfolio-agent history tables."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Callable, List, Optional
from uuid import UUID, uuid4

from app.database import db

from .contracts import (
    DecisionSnapshot, PortfolioSnapshot, RealizedOutcome, TimelineEvent,
    TradeThesis,
)


class DecisionHistoryWriter:
    """Persist lineage records; never updates yesterday's decision in place."""

    def __init__(
        self,
        execute: Optional[Callable[..., Any]] = None,
        query: Optional[Callable[..., Any]] = None,
    ):
        self._execute = execute or db.execute_update
        self._query = query or db.execute_query

    def write_snapshot(self, snapshot: PortfolioSnapshot) -> str:
        snapshot_id = str(uuid4())
        self._execute(
            """
            INSERT INTO portfolio_agent_snapshots (
                snapshot_id, portfolio_id, as_of, account_equity,
                settled_cash, unsettled_cash, buying_power, invested_value,
                portfolio_heat, price_freshness, reconciliation_status,
                missing_fields, source
            ) VALUES (
                CAST(:snapshot_id AS uuid), :portfolio_id, :as_of,
                :account_equity, :settled_cash, :unsettled_cash,
                :buying_power, :invested_value, :portfolio_heat,
                :price_freshness, :reconciliation_status,
                CAST(:missing_fields AS jsonb), :source
            )
            """,
            self._params(
                snapshot_id=snapshot_id,
                portfolio_id=snapshot.portfolio_id,
                as_of=snapshot.as_of,
                account_equity=snapshot.account_equity,
                settled_cash=snapshot.settled_cash,
                unsettled_cash=snapshot.unsettled_cash,
                buying_power=snapshot.buying_power,
                invested_value=snapshot.invested_value,
                portfolio_heat=snapshot.portfolio_heat,
                price_freshness=snapshot.price_freshness.value,
                reconciliation_status=snapshot.reconciliation_status,
                missing_fields=snapshot.missing_fields,
                source=snapshot.source,
            ),
        )
        for position in snapshot.positions:
            self._execute(
                """
                INSERT INTO portfolio_agent_position_states (
                    snapshot_id, portfolio_id, symbol, asset_type, side,
                    quantity, average_entry_price, current_price, current_value,
                    unrealized_pnl, unrealized_pnl_pct, sector, industry,
                    stop_price, target_price, thesis_id, decision_id,
                    opened_at, as_of, price_as_of, status, source
                ) VALUES (
                    CAST(:snapshot_id AS uuid), :portfolio_id, :symbol,
                    :asset_type, :side, :quantity, :average_entry_price,
                    :current_price, :current_value, :unrealized_pnl,
                    :unrealized_pnl_pct, :sector, :industry, :stop_price,
                    :target_price, CAST(:thesis_id AS uuid),
                    CAST(:decision_id AS uuid), :opened_at, :as_of,
                    :price_as_of, :status, :source
                )
                """,
                self._params(
                    snapshot_id=snapshot_id,
                    portfolio_id=position.portfolio_id,
                    symbol=position.symbol,
                    asset_type=position.asset_type,
                    side=position.side,
                    quantity=position.quantity,
                    average_entry_price=position.average_entry_price,
                    current_price=position.current_price,
                    current_value=position.current_value,
                    unrealized_pnl=position.unrealized_pnl,
                    unrealized_pnl_pct=position.unrealized_pnl_pct,
                    sector=position.sector,
                    industry=position.industry,
                    stop_price=position.stop_price,
                    target_price=position.target_price,
                    thesis_id=position.thesis_id,
                    decision_id=position.decision_id,
                    opened_at=position.opened_at,
                    as_of=position.as_of or snapshot.as_of,
                    price_as_of=position.price_as_of,
                    status=position.status.value,
                    source=position.source,
                ),
            )
        return snapshot_id

    def write_thesis(self, thesis: TradeThesis) -> str:
        thesis_id = thesis.thesis_id or str(uuid4())
        self._execute(
            """
            INSERT INTO portfolio_agent_trade_theses (
                thesis_id, portfolio_id, symbol, setup_type, status, version,
                technical_score, fundamental_score, valuation_score,
                catalyst_score, market_environment_score, bull_case,
                base_case, bear_case, invalidation_conditions, created_at,
                updated_at, source
            ) VALUES (
                CAST(:thesis_id AS uuid), :portfolio_id, :symbol, :setup_type,
                :status, :version, :technical_score, :fundamental_score,
                :valuation_score, :catalyst_score, :market_environment_score,
                :bull_case, :base_case, :bear_case,
                CAST(:invalidation_conditions AS jsonb), :created_at,
                :updated_at, :source
            )
            ON CONFLICT (thesis_id) DO NOTHING
            """,
            self._params(**{**thesis.model_dump(mode="json"), "thesis_id": thesis_id}),
        )
        return thesis_id

    def write_decision(self, decision: DecisionSnapshot) -> str:
        self._execute(
            """
            INSERT INTO portfolio_agent_decisions (
                decision_id, portfolio_id, symbol, thesis_id, action,
                decision_confidence, regime_confidence, outcome_probability,
                market_regime, strategy_environment, setup_type, risk_status,
                risk_allowed, entry_price, stop_price, target_price,
                reward_risk, reasons, vetoes, rules_version, model_version,
                prompt_version, created_at, expires_at
            ) VALUES (
                CAST(:decision_id AS uuid), :portfolio_id, :symbol,
                CAST(:thesis_id AS uuid), :action, :decision_confidence,
                :regime_confidence, :outcome_probability, :market_regime,
                :strategy_environment, :setup_type, :risk_status,
                :risk_allowed, :entry_price, :stop_price, :target_price,
                :reward_risk, CAST(:reasons AS jsonb), CAST(:vetoes AS jsonb),
                :rules_version, :model_version, :prompt_version, :created_at,
                :expires_at
            )
            ON CONFLICT (decision_id) DO NOTHING
            """,
            self._params(**{
                **decision.model_dump(mode="json"),
                "action": decision.action.value,
                "reasons": decision.reasons,
                "vetoes": decision.vetoes,
            }),
        )
        return decision.decision_id

    def write_timeline_event(self, event: TimelineEvent) -> str:
        self._execute(
            """
            INSERT INTO portfolio_agent_position_events (
                position_event_id, portfolio_id, symbol, event_type,
                occurred_at, decision_id, thesis_id, payload, created_at
            ) VALUES (
                CAST(:event_id AS uuid), :portfolio_id, :symbol, :event_type,
                :occurred_at, CAST(:decision_id AS uuid), CAST(:thesis_id AS uuid),
                CAST(:payload AS jsonb), NOW()
            )
            ON CONFLICT (position_event_id) DO NOTHING
            """,
            self._params(**event.model_dump(mode="json")),
        )
        return event.event_id

    def write_outcome(self, outcome: RealizedOutcome) -> str:
        self._execute(
            """
            INSERT INTO portfolio_agent_outcomes (
                outcome_id, decision_id, thesis_id, symbol, horizon, as_of,
                return_pct, pnl, maximum_favorable_excursion,
                maximum_adverse_excursion, stop_hit, target_hit,
                holding_period_days, fees, slippage, created_at
            ) VALUES (
                CAST(:outcome_id AS uuid), CAST(:decision_id AS uuid),
                CAST(:thesis_id AS uuid), :symbol, :horizon, :as_of,
                :return_pct, :pnl, :maximum_favorable_excursion,
                :maximum_adverse_excursion, :stop_hit, :target_hit,
                :holding_period_days, :fees, :slippage, NOW()
            )
            ON CONFLICT (outcome_id) DO NOTHING
            """,
            self._params(**outcome.model_dump(mode="json")),
        )
        return outcome.outcome_id

    def latest_decisions(
        self,
        portfolio_id: str,
        *,
        symbol: Optional[str] = None,
        limit: int = 100,
    ) -> List[DecisionSnapshot]:
        """Read prior decisions for review; does not mutate history."""
        rows = self._query(
            """
            SELECT decision_id, portfolio_id, symbol, thesis_id, action,
                   decision_confidence, regime_confidence, outcome_probability,
                   market_regime, strategy_environment, setup_type, risk_status,
                   risk_allowed, entry_price, stop_price, target_price,
                   reward_risk, reasons, vetoes, rules_version, model_version,
                   prompt_version, created_at, expires_at
            FROM portfolio_agent_decisions
            WHERE portfolio_id = :portfolio_id
              AND (CAST(:symbol AS text) IS NULL OR symbol = :symbol)
            ORDER BY created_at DESC
            LIMIT :limit
            """,
            {"portfolio_id": portfolio_id, "symbol": symbol, "limit": limit},
        )
        return [DecisionSnapshot.model_validate({
            **row,
            "action": row.get("action"),
            "reasons": self._decode_json(row.get("reasons"), []),
            "vetoes": self._decode_json(row.get("vetoes"), []),
        }) for row in rows]

    def active_thesis(self, portfolio_id: str, symbol: str) -> Optional[TradeThesis]:
        """Read the latest active thesis for a position/symbol."""
        rows = self._query(
            """
            SELECT thesis_id, portfolio_id, symbol, setup_type, status, version,
                   technical_score, fundamental_score, valuation_score,
                   catalyst_score, market_environment_score, bull_case,
                   base_case, bear_case, invalidation_conditions, created_at,
                   updated_at, source
            FROM portfolio_agent_trade_theses
            WHERE portfolio_id = :portfolio_id
              AND symbol = :symbol
              AND status = 'ACTIVE'
            ORDER BY version DESC, updated_at DESC
            LIMIT 1
            """,
            {"portfolio_id": portfolio_id, "symbol": symbol.upper()},
        )
        if not rows:
            return None
        row = rows[0]
        return TradeThesis.model_validate({
            **row,
            "invalidation_conditions": self._decode_json(
                row.get("invalidation_conditions"), []),
        })

    @staticmethod
    def _decode_json(value: Any, default: Any) -> Any:
        if value is None:
            return default
        if isinstance(value, (dict, list)):
            return value
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _params(**values: Any) -> dict[str, Any]:
        for key, value in list(values.items()):
            if isinstance(value, (list, dict)):
                values[key] = json.dumps(value)
        return values
