from app.market_data.models import CompanyProfile, FundamentalsSnapshot, Quote
from app.fundamental_intelligence import BusinessType, assess_fundamentals


def _snapshot(**overrides):
    values = {
        "provider": "test",
        "symbol": "TEST",
        "revenue_growth": 0.25,
        "earnings_growth": 0.30,
        "gross_margin": 0.60,
        "operating_margin": 0.25,
        "profit_margin": 0.20,
        "roe": 0.22,
        "roa": 0.10,
        "current_ratio": 1.8,
        "quick_ratio": 1.4,
        "debt_to_equity": 0.4,
        "net_income": 100,
        "operating_cash_flow": 130,
        "free_cash_flow": 110,
        "forward_pe": 32,
        "peg_ratio": 1.2,
    }
    values.update(overrides)
    return FundamentalsSnapshot(**values)


def test_dimensions_are_separate_and_moat_is_not_invented():
    assessment = assess_fundamentals(
        "TEST", _snapshot(),
        profile=CompanyProfile(provider="test", symbol="TEST", sector="Technology"),
        quote=Quote(provider="test", symbol="TEST", price=100),
    )
    assert assessment.quality_score is not None
    assert assessment.growth.score is not None
    assert assessment.profitability.score is not None
    assert assessment.valuation.forward_pe == 32
    assert assessment.valuation.valuation_label == "fair"
    assert assessment.competitive_advantage.score is None
    assert assessment.earnings_revision.score is None
    assert not assessment.valuation.dcf_available


def test_financial_business_type_is_explicit():
    assessment = assess_fundamentals(
        "COIN", _snapshot(),
        profile=CompanyProfile(provider="test", symbol="COIN", sector="Financial Services"),
    )
    assert assessment.business_type == BusinessType.FINANCIAL
    assert assessment.risk_flags


def test_missing_fundamentals_are_unavailable():
    assessment = assess_fundamentals("UNKNOWN", None)
    assert assessment.data_quality == "insufficient"
    assert assessment.quality_score is None
    assert assessment.growth.score is None
    assert assessment.valuation.valuation_label == "unavailable"


def test_negative_eps_is_not_treated_as_valid_pe_anchor():
    assessment = assess_fundamentals(
        "LOSS", _snapshot(eps=-2, forward_pe=None, peg_ratio=None),
    )
    assert assessment.valuation.forward_pe is None
    assert assessment.valuation.valuation_label == "unavailable"
    assert "peer and historical multiples unavailable" in assessment.valuation.reasons
