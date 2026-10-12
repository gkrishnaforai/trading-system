from datetime import datetime, timezone

from app.portfolio import (
    DecisionHistoryWriter, DecisionSnapshot, PositionState, PortfolioSnapshotProvider,
    RealizedOutcome, TimelineEvent, TradeThesis,
)


class FakeExecutor:
    def __init__(self):
        self.calls = []

    def __call__(self, sql, params=None):
        self.calls.append((sql, params or {}))
        return None


class FakeQuery:
    def __init__(self):
        self.calls = []

    def __call__(self, sql, params=None):
        self.calls.append((sql, params or {}))
        if "FROM portfolio_agent_decisions" in sql:
            return [{
                "decision_id": "00000000-0000-0000-0000-000000000002",
                "portfolio_id": "portfolio-1",
                "symbol": "RBRK",
                "thesis_id": None,
                "action": "HOLD",
                "decision_confidence": 0.73,
                "regime_confidence": 0.75,
                "outcome_probability": None,
                "market_regime": "bullish",
                "strategy_environment": "medium",
                "setup_type": "pullback",
                "risk_status": "allowed",
                "risk_allowed": True,
                "entry_price": 104.03,
                "stop_price": 92.12,
                "target_price": 127.84,
                "reward_risk": 2.0,
                "reasons": '["thesis intact"]',
                "vetoes": '[]',
                "rules_version": "test",
                "model_version": None,
                "prompt_version": None,
                "created_at": datetime.now(timezone.utc),
                "expires_at": None,
            }]
        if "FROM portfolio_agent_trade_theses" in sql:
            return []
        return []


def test_snapshot_provider_reads_without_database():
    provider = PortfolioSnapshotProvider()
    snapshot = provider.from_rows(
        "portfolio-1",
        [{
            "holding_id": "position-1",
            "symbol": "RBRK",
            "quantity": 24,
            "avg_price": 104.03,
            "current_price": 110.20,
            "current_value": 2644.80,
            "sector": "Technology",
        }],
        account_equity=100000,
        settled_cash=97355.20,
    )
    assert snapshot.portfolio_id == "portfolio-1"
    assert snapshot.positions[0].symbol == "RBRK"
    assert snapshot.positions[0].current_value == 2644.80


def test_snapshot_provider_refreshes_through_injected_calculator():
    class Calculator:
        def update_portfolio_holdings(self, portfolio_id):
            assert portfolio_id == "portfolio-1"
            return 3

    provider = PortfolioSnapshotProvider(
        calculator_factory=lambda: Calculator()
    )
    # The method reaches the real row source after refresh; use a row-source
    # subclass to keep this unit test database-free.
    provider.row_source = type("Rows", (), {
        "fetch_positions": lambda self, portfolio_id: []
    })()
    updated, snapshot = provider.refresh_prices("portfolio-1")
    assert updated == 3
    assert snapshot.portfolio_id == "portfolio-1"


def test_history_writer_is_append_oriented_and_injectable():
    execute = FakeExecutor()
    writer = DecisionHistoryWriter(execute=execute)
    now = datetime.now(timezone.utc)
    thesis = TradeThesis(
        thesis_id="00000000-0000-0000-0000-000000000001",
        symbol="RBRK", setup_type="PULLBACK", created_at=now, updated_at=now,
    )
    decision = DecisionSnapshot(
        decision_id="00000000-0000-0000-0000-000000000002",
        symbol="RBRK", thesis_id=thesis.thesis_id, action="ADD",
        decision_confidence=0.73, rules_version="test", created_at=now,
    )
    event = TimelineEvent(
        event_id="00000000-0000-0000-0000-000000000003",
        symbol="RBRK", event_type="DECISION_CREATED", occurred_at=now,
        decision_id=decision.decision_id, thesis_id=thesis.thesis_id,
        source="test",
    )
    outcome = RealizedOutcome(
        outcome_id="00000000-0000-0000-0000-000000000004",
        symbol="RBRK", decision_id=decision.decision_id,
        thesis_id=thesis.thesis_id, horizon="5d", as_of=now,
        return_pct=2.0,
    )

    assert writer.write_thesis(thesis) == thesis.thesis_id
    assert writer.write_decision(decision) == decision.decision_id
    assert writer.write_timeline_event(event) == event.event_id
    assert writer.write_outcome(outcome) == outcome.outcome_id
    assert len(execute.calls) == 4
    assert all("ON CONFLICT" in sql for sql, _ in execute.calls)


def test_history_reader_loads_prior_decision_without_llm_memory():
    query = FakeQuery()
    writer = DecisionHistoryWriter(query=query)
    decisions = writer.latest_decisions("portfolio-1", symbol="RBRK")
    assert len(decisions) == 1
    assert decisions[0].symbol == "RBRK"
    assert decisions[0].decision_confidence == 0.73
    assert decisions[0].reasons == ["thesis intact"]
    assert writer.active_thesis("portfolio-1", "RBRK") is None
