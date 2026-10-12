from app.accumulation import AccumulationPhase, build_accumulation_plan
from app.risk.models import RiskAssessment, RiskStatus
from app.swing_opportunity.models import OpportunityQuality, SetupAssessment, SetupType, StockAnalysis, StockDataQuality, StockTechnicals, SwingOpportunity
from app.trade_decision.models import DecisionAction, TradeDecision


def _opp(setup=SetupType.PULLBACK, thesis="INTACT", momentum="IMPROVING", readiness="CONFIRMED"):
    return SwingOpportunity(
        symbol="APH", business_quality="HIGH", thesis_status=thesis,
        entry_state="READY" if readiness == "CONFIRMED" else "WAIT",
        setup_readiness=readiness, swing_size_multiplier=0.5,
        stock=StockAnalysis(symbol="APH", technicals=StockTechnicals(price=100), data_quality=StockDataQuality(bars=220, required_bars=200, sufficient=True)),
        fundamentals={"quality_score": 80, "momentum": {"label": momentum}, "valuation": {"valuation_label": "fair"}},
        setup=SetupAssessment(type=setup, quality=OpportunityQuality.HIGH, score=80),
        opportunity_quality=OpportunityQuality.HIGH, opportunity_score=80,
    )


def _decision():
    return TradeDecision(symbol="APH", action=DecisionAction.BUY_SMALL, confidence=.75, risk_status="allowed")


def _risk(allowed=True):
    return RiskAssessment(symbol="APH", status=RiskStatus.ALLOWED if allowed else RiskStatus.BLOCKED, allowed=allowed, target=110)


def test_confirmed_setup_creates_starter_plan_for_new_position():
    plan = build_accumulation_plan(_opp(), _decision(), _risk(), current_position=0)
    assert plan.phase == AccumulationPhase.STARTER
    assert plan.eligible


def test_developing_setup_waits():
    plan = build_accumulation_plan(_opp(readiness="DEVELOPING"), _decision(), _risk())
    assert plan.phase == AccumulationPhase.DEVELOPING
    assert not plan.eligible


def test_deteriorating_momentum_blocks_accumulation():
    plan = build_accumulation_plan(_opp(momentum="DETERIORATING"), _decision(), _risk())
    assert plan.phase == AccumulationPhase.BLOCKED
    assert not plan.eligible


def test_broken_thesis_blocks_accumulation():
    plan = build_accumulation_plan(_opp(thesis="BROKEN"), _decision(), _risk())
    assert plan.phase == AccumulationPhase.BLOCKED
    assert "thesis is broken" in plan.blockers
