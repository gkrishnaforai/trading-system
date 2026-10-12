from datetime import datetime, timezone

import pytest

from app.execution import PaperBroker, PaperOrderStatus
from app.orders import OrderPlan, OrderSide, OrderType, create_order_plan
from app.portfolio import PortfolioSnapshot, allocate_portfolio
from app.risk import RiskAssessment, RiskStatus
from app.trade_decision import DecisionAction, TradeDecision
from app.trading_intent import TradingHorizon, TradingIntent, TradingMode, validate_horizon_support


def _decision(action=DecisionAction.BUY):
    return TradeDecision(
        symbol="TEST", action=action, confidence=0.8,
        opportunity_quality="high", fundamental_quality="high",
        valuation_label="fair", risk_status="allowed",
    )


def _risk(allowed=True):
    return RiskAssessment(
        symbol="TEST", status=RiskStatus.ALLOWED if allowed else RiskStatus.BLOCKED,
        allowed=allowed, entry=100, stop=96, target=108,
        risk_per_share=4, reward_risk=2, risk_amount=400,
        position_size_pct=0.05, shares=25,
        portfolio_heat_before=0.01, portfolio_heat_after=0.014,
        blocking_reasons=[] if allowed else ["risk veto"],
    )


def _intent(mode=TradingMode.PAPER, horizon=TradingHorizon.SWING):
    return TradingIntent(
        account_equity=100000, horizon=horizon, mode=mode,
        max_risk_per_trade=0.01, max_portfolio_heat=0.05,
        max_position_pct=0.10, approval_required=True,
    )


def test_daily_graph_does_not_authorize_day_trading():
    reasons = validate_horizon_support(_intent(horizon=TradingHorizon.DAY_TRADING), daily_data_only=True)
    assert reasons


def test_allocator_applies_capital_and_market_multiplier():
    result = allocate_portfolio(
        _intent(),
        PortfolioSnapshot(cash=100000, equity=100000, invested_value=0),
        _decision(), _risk(), price=100,
    )
    assert result.allowed
    assert result.allocated_shares == 50
    assert result.allocated_value == 5000


def test_allocator_blocks_nonbuy_decision():
    result = allocate_portfolio(
        _intent(), PortfolioSnapshot(cash=100000, equity=100000, invested_value=0),
        _decision(DecisionAction.WAIT), _risk(), price=100,
    )
    assert not result.allowed
    assert result.blocking_reasons


def test_order_plan_is_side_effect_free_and_validated():
    allocation = allocate_portfolio(
        _intent(), PortfolioSnapshot(cash=100000, equity=100000, invested_value=0),
        _decision(), _risk(), price=100,
    )
    plan = create_order_plan(_intent(), _decision(), allocation, _risk())
    assert plan.side == OrderSide.BUY
    assert plan.quantity == 50
    assert plan.stop_price < plan.limit_price < plan.target_price
    assert plan.approval_required


def test_paper_broker_requires_approval_then_fills():
    allocation = allocate_portfolio(
        _intent(), PortfolioSnapshot(cash=100000, equity=100000, invested_value=0),
        _decision(), _risk(), price=100,
    )
    plan = create_order_plan(_intent(), _decision(), allocation, _risk())
    broker = PaperBroker(starting_cash=100000)
    rejected = broker.submit_order(plan, market_price=99)
    assert rejected.status == PaperOrderStatus.REJECTED
    filled = broker.submit_order(plan, market_price=99, approved=True)
    assert filled.status == PaperOrderStatus.FILLED
    assert broker.account.positions["TEST"].quantity == 50


def test_paper_broker_target_exit():
    broker = PaperBroker(starting_cash=100000)
    plan = OrderPlan(
        plan_id="plan-1", symbol="TEST", side=OrderSide.BUY,
        order_type=OrderType.LIMIT, quantity=10, limit_price=100,
        stop_price=90, target_price=110, approval_required=False,
    )
    buy = broker.submit_order(plan, market_price=99, approved=True)
    assert buy.status == PaperOrderStatus.FILLED
    exits = broker.check_exits({"TEST": 111})
    assert len(exits) == 1
    assert exits[0].status == PaperOrderStatus.FILLED
    assert "TEST" not in broker.account.positions
    assert broker.account.cash > 0
