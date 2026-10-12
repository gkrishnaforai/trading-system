from app.risk.models import RiskAssessment, RiskStatus
from app.swing_opportunity.models import (
    OpportunityQuality, SetupAssessment, SetupType, StockAnalysis,
    StockDataQuality, StockTechnicals, SwingOpportunity,
)
from app.trade_decision import DecisionAction, decide_trade


def _opportunity(*, setup=SetupType.PULLBACK, quality=OpportunityQuality.HIGH,
                 falling=False, fundamentals=None):
    return SwingOpportunity(
        symbol="TEST",
        swing_environment="medium",
        swing_size_multiplier=0.5,
        stock=StockAnalysis(
            symbol="TEST",
            technicals=StockTechnicals(price=100, atr_pct=0.02),
            data_quality=StockDataQuality(bars=220, required_bars=200, sufficient=True),
        ),
        fundamentals=fundamentals or {
            "data_quality": "good",
            "quality_score": 80,
            "valuation": {"valuation_label": "fair"},
        },
        setup=SetupAssessment(type=setup, quality=quality, score=80,
                              confirmation="confirmed", falling_knife=falling),
        opportunity_quality=quality,
        opportunity_score=80,
        next_step="RISK_ASSESSMENT",
    )


def _risk(allowed=True, status=RiskStatus.ALLOWED, blockers=None):
    return RiskAssessment(
        symbol="TEST", status=status, allowed=allowed,
        entry=100, stop=96, target=108, risk_per_share=4,
        reward_risk=2, risk_amount=500, position_size_pct=0.05,
        shares=50, portfolio_heat_before=0.01, portfolio_heat_after=0.015,
        blocking_reasons=blockers or [],
    )


def test_falling_knife_is_avoid():
    decision = decide_trade(_opportunity(falling=True), _risk(False, RiskStatus.BLOCKED, ["falling-knife setup rejected"]))
    assert decision.action == DecisionAction.AVOID


def test_no_setup_waits():
    decision = decide_trade(_opportunity(setup=SetupType.NO_SETUP, quality=OpportunityQuality.LOW), _risk(False, RiskStatus.BLOCKED, ["no qualifying setup"]))
    assert decision.action == DecisionAction.WAIT


def test_risk_permission_veto_waits():
    decision = decide_trade(_opportunity(), _risk(False, RiskStatus.BLOCKED, ["market permissions do not allow normal longs"]))
    assert decision.action == DecisionAction.WAIT
    assert decision.vetoes


def test_complete_high_quality_setup_can_buy_pending_approval():
    decision = decide_trade(_opportunity(), _risk())
    assert decision.action == DecisionAction.BUY
    assert decision.requires_approval
    assert decision.position_size_pct == 0.05


def test_incomplete_fundamentals_reduce_action():
    decision = decide_trade(
        _opportunity(fundamentals={"data_quality": "partial", "quality_score": None}),
        _risk(),
    )
    assert decision.action == DecisionAction.BUY_SMALL
    assert decision.confidence <= 0.65


def test_insufficient_risk_data_waits():
    decision = decide_trade(
        _opportunity(), _risk(False, RiskStatus.INSUFFICIENT_DATA, ["account equity required"]),
    )
    assert decision.action == DecisionAction.WAIT
    assert not decision.requires_approval


def _valued_fundamentals(gvc=None, price=None, bull=None, source="fair_value_v2"):
    valuation = {"valuation_label": "fair", "fair_value_source": source}
    if price is not None:
        valuation["current_price"] = price
    if bull is not None:
        valuation["fair_value_bull"] = bull
    return {
        "data_quality": "good",
        "quality_score": 80,
        "valuation": valuation,
        "growth_value_class": gvc,
    }


def test_price_above_bull_band_downgrades_buy():
    decision = decide_trade(
        _opportunity(fundamentals=_valued_fundamentals(price=350, bull=310)),
        _risk(),
    )
    assert decision.action == DecisionAction.BUY_SMALL
    assert any("bull-case fair value" in r for r in decision.reasons)


def test_value_trap_downgrades_buy_and_caps_confidence():
    decision = decide_trade(
        _opportunity(fundamentals=_valued_fundamentals(gvc="VALUE_TRAP")),
        _risk(),
    )
    assert decision.action == DecisionAction.BUY_SMALL
    assert decision.confidence <= 0.65
    assert any("VALUE_TRAP" in r for r in decision.reasons)


def test_speculative_growth_flags_and_caps_confidence():
    decision = decide_trade(
        _opportunity(fundamentals=_valued_fundamentals(gvc="SPECULATIVE_GROWTH")),
        _risk(),
    )
    assert decision.action == DecisionAction.BUY  # flags, does not downgrade
    assert decision.confidence <= 0.65
    assert any("SPECULATIVE_GROWTH" in r for r in decision.reasons)


def test_undervalued_does_not_boost():
    decision = decide_trade(
        _opportunity(quality=OpportunityQuality.MEDIUM,
                     fundamentals=_valued_fundamentals(gvc="UNDERVALUED_GROWTH")),
        _risk(),
    )
    assert decision.action == DecisionAction.BUY_SMALL  # medium → BUY_SMALL, no boost


def test_user_override_source_flagged():
    decision = decide_trade(
        _opportunity(fundamentals=_valued_fundamentals(source="user_override")),
        _risk(),
    )
    assert decision.action == DecisionAction.BUY
    assert any("user override" in r for r in decision.reasons)


def test_growth_value_class_propagates():
    decision = decide_trade(
        _opportunity(fundamentals=_valued_fundamentals(gvc="FAIRLY_VALUED_GROWTH")),
        _risk(),
    )
    assert decision.growth_value_class == "FAIRLY_VALUED_GROWTH"
