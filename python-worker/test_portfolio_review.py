from app.portfolio_review import PortfolioAction, assign_position_action
from app.risk import RiskAssessment, RiskStatus
from app.swing_opportunity.models import (
    OpportunityQuality, SetupAssessment, SetupType, StockAnalysis,
    StockDataQuality, StockTechnicals, SwingOpportunity,
)
from app.trade_decision import DecisionAction, TradeDecision


def _opportunity(setup=SetupType.PULLBACK, falling=False, event_allowed=True):
    return SwingOpportunity(
        symbol="RBRK", swing_environment="medium", swing_size_multiplier=0.5,
        event_policy="NORMAL", event_new_entries_allowed=event_allowed,
        stock=StockAnalysis(
            symbol="RBRK", technicals=StockTechnicals(price=105),
            data_quality=StockDataQuality(bars=220, required_bars=200, sufficient=True),
        ),
        setup=SetupAssessment(
            type=setup, quality=OpportunityQuality.HIGH,
            score=80, falling_knife=falling,
        ),
        opportunity_quality=OpportunityQuality.HIGH,
        opportunity_score=80,
    )


def _decision(action=DecisionAction.WAIT):
    return TradeDecision(
        symbol="RBRK", action=action, confidence=0.75,
        opportunity_quality="high", fundamental_quality="medium",
        risk_status="allowed",
    )


def _risk(allowed=True):
    return RiskAssessment(
        symbol="RBRK", status=RiskStatus.ALLOWED if allowed else RiskStatus.BLOCKED,
        allowed=allowed, blocking_reasons=[] if allowed else ["event policy"],
    )


def test_wait_maps_to_hold_for_existing_position():
    review = assign_position_action(_opportunity(), _decision(), _risk(), quantity=24, current_price=110)
    assert review.action == PortfolioAction.HOLD


def test_falling_knife_maps_to_trim():
    review = assign_position_action(
        _opportunity(SetupType.NO_SETUP, falling=True),
        _decision(DecisionAction.AVOID), _risk(False),
        quantity=24, current_price=90,
    )
    assert review.action == PortfolioAction.TRIM


def test_buy_with_allowed_risk_maps_to_add():
    review = assign_position_action(
        _opportunity(), _decision(DecisionAction.BUY), _risk(True),
        quantity=24, current_price=110,
    )
    assert review.action == PortfolioAction.ADD


def test_missing_price_maps_to_review():
    review = assign_position_action(_opportunity(), _decision(), _risk(), quantity=24, current_price=None)
    assert review.action == PortfolioAction.REVIEW


def test_reconciliation_failure_precedes_trim():
    review = assign_position_action(
        _opportunity(SetupType.NO_SETUP, falling=True),
        _decision(DecisionAction.AVOID), _risk(False),
        quantity=24, current_price=90, reconciliation_safe=False,
    )
    assert review.action == PortfolioAction.REVIEW
    assert review.trim_reason is None


def test_broken_thesis_exits_even_with_setup():
    opportunity = _opportunity()
    opportunity.thesis_status = "BROKEN"
    review = assign_position_action(
        opportunity, _decision(DecisionAction.BUY), _risk(True),
        quantity=24, current_price=110,
    )
    assert review.action == PortfolioAction.EXIT
    assert review.exit_reason == "THESIS_BROKEN"


def test_target_reached_maps_to_take_profit():
    opportunity = _opportunity()
    risk = _risk(True)
    risk.target = 100
    review = assign_position_action(
        opportunity, _decision(DecisionAction.WAIT), risk,
        quantity=24, current_price=110,
    )
    assert review.action == PortfolioAction.TAKE_PROFIT
    assert review.take_profit_reason == "TARGET_REACHED"
