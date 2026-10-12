from app.market_regime.models import MarketPermissions, MarketRegime, RegimeLabel
from app.risk import PortfolioConstraints, RiskStatus, assess_risk
from app.swing_opportunity.models import (
    OpportunityQuality, RelativeStrength, SetupAssessment, SetupType,
    StockAnalysis, StockDataQuality, StockTechnicals, SwingOpportunity,
)


def _regime(size=0.5, normal_long=True):
    return MarketRegime(
        regime=RegimeLabel.BULLISH_CORRECTION,
        direction="bullish",
        condition="correction",
        confidence=0.8,
        market_permissions=MarketPermissions(
            normal_long=normal_long, size_multiplier=size),
    )


def _opportunity(*, setup=SetupType.PULLBACK, quality=OpportunityQuality.HIGH, falling=False):
    return SwingOpportunity(
        symbol="TEST",
        market_regime="bullish",
        market_condition="correction",
        swing_environment="medium",
        swing_size_multiplier=0.5,
        stock=StockAnalysis(
            symbol="TEST",
            technicals=StockTechnicals(price=100, atr_pct=0.02),
            relative_strength=RelativeStrength(vs_spy20=0.08, tier="outperformer"),
            data_quality=StockDataQuality(bars=220, required_bars=200, sufficient=True),
            sector_alignment="aligned",
        ),
        setup=SetupAssessment(
            type=setup, quality=quality, score=80,
            confirmation="confirmed", falling_knife=falling),
        opportunity_quality=quality,
        opportunity_score=80,
        next_step="RISK_ASSESSMENT",
    )


def test_no_setup_is_blocked():
    risk = assess_risk(_opportunity(setup=SetupType.NO_SETUP), _regime(), PortfolioConstraints(account_equity=100000))
    assert risk.status == RiskStatus.BLOCKED
    assert not risk.allowed


def test_missing_account_is_not_assumed_safe():
    risk = assess_risk(_opportunity(), _regime(), PortfolioConstraints())
    assert risk.status == RiskStatus.INSUFFICIENT_DATA
    assert not risk.allowed
    assert "account equity" in risk.blocking_reasons[0]


def test_valid_setup_is_sized_by_stop_and_market_multiplier():
    risk = assess_risk(_opportunity(), _regime(size=0.5), PortfolioConstraints(account_equity=100000))
    assert risk.allowed
    assert risk.status == RiskStatus.REDUCED
    assert risk.shares and risk.shares > 0
    assert risk.reward_risk == 2.0
    assert risk.position_size_pct <= 0.05


def test_portfolio_heat_blocks_new_trade():
    risk = assess_risk(
        _opportunity(), _regime(),
        PortfolioConstraints(account_equity=100000, current_portfolio_risk=0.05),
    )
    assert risk.status == RiskStatus.BLOCKED
    assert not risk.allowed
    assert "position size rounds to zero" in risk.blocking_reasons


def test_market_long_permission_blocks_risk():
    risk = assess_risk(_opportunity(), _regime(normal_long=False), PortfolioConstraints(account_equity=100000))
    assert risk.status == RiskStatus.BLOCKED
    assert not risk.allowed
