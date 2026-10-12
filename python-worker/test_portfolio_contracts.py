from datetime import datetime, timezone

from app.portfolio import (
    CanonicalPortfolioSnapshot, DataFreshness, DecisionSnapshot,
    PositionStatus, RealizedOutcome, TradeThesis,
    portfolio_snapshot_from_api_rows,
)


def test_adapts_existing_holdings_fields():
    snapshot = portfolio_snapshot_from_api_rows(
        "portfolio-1",
        [{
            "holding_id": "holding-1",
            "symbol": "RBRK",
            "quantity": 24,
            "avg_price": 104.03,
            "current_price": 110.20,
            "current_value": 2644.80,
            "unrealized_gain_loss": 143.28,
            "unrealized_gain_loss_percent": 5.73,
            "sector": "Technology",
            "updated_at": "2026-09-16T15:00:00+00:00",
        }],
        account_equity=100000,
        settled_cash=97355.20,
    )
    assert isinstance(snapshot, CanonicalPortfolioSnapshot)
    assert snapshot.positions[0].symbol == "RBRK"
    assert snapshot.positions[0].status == PositionStatus.OPEN
    assert snapshot.positions[0].current_price == 110.20
    assert snapshot.symbol_exposure["RBRK"] > 0
    assert snapshot.sector_exposure["Technology"] > 0
    assert snapshot.price_freshness == DataFreshness.ACCEPTABLE


def test_missing_cash_and_price_are_explicit():
    snapshot = portfolio_snapshot_from_api_rows(
        "portfolio-1",
        [{"id": "p1", "symbol": "CRDO", "quantity": 10, "avg_price": 100}],
    )
    assert snapshot.account_equity is None
    assert snapshot.settled_cash is None
    assert snapshot.missing_fields
    assert snapshot.price_freshness == DataFreshness.UNKNOWN
    assert snapshot.reconciliation_status == "UNRECONCILED"


def test_decision_history_separates_confidence_types():
    decision = DecisionSnapshot(
        decision_id="decision-1",
        symbol="RBRK",
        action="ADD",
        decision_confidence=0.73,
        regime_confidence=0.75,
        outcome_probability=None,
        rules_version="trade-decision-v1",
        created_at=datetime.now(timezone.utc),
    )
    assert decision.decision_confidence == 0.73
    assert decision.outcome_probability is None


def test_thesis_and_outcome_are_lineage_records():
    now = datetime.now(timezone.utc)
    thesis = TradeThesis(
        thesis_id="thesis-1", symbol="RBRK", setup_type="PULLBACK",
        created_at=now, updated_at=now,
    )
    outcome = RealizedOutcome(
        outcome_id="outcome-1", decision_id="decision-1", thesis_id=thesis.thesis_id,
        symbol="RBRK", horizon="5d", as_of=now, return_pct=2.1,
    )
    assert outcome.thesis_id == thesis.thesis_id
