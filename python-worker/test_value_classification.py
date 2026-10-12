"""Growth-vs-value master classification tests — deterministic, no providers."""
from app.fundamental_intelligence.models import (
    BusinessType, DimensionAssessment, FundamentalAssessment, ValuationDiagnostics,
)
from app.fundamental_intelligence.value_classification import GrowthValueClass, classify_growth_value


def _assessment(
    growth="high", quality=75.0, valuation_label="fair",
    price_vs_fv=None, momentum="NEUTRAL", business=BusinessType.SECULAR_GROWTH,
) -> FundamentalAssessment:
    return FundamentalAssessment(
        symbol="T",
        business_type=business,
        growth=DimensionAssessment(label=growth, score=80 if growth == "high" else 40),
        quality_score=quality,
        momentum={"label": momentum},
        valuation=ValuationDiagnostics(
            forward_pe=20.0, valuation_label=valuation_label,
            price_vs_base_fv_pct=price_vs_fv,
            fair_value_base=100.0 if price_vs_fv is not None else None,
        ),
    )


def test_undervalued_growth():
    cls, reasons = classify_growth_value(
        _assessment(valuation_label="value", price_vs_fv=-0.20, momentum="STRONG"))
    assert cls == GrowthValueClass.UNDERVALUED_GROWTH
    assert reasons


def test_fairly_valued_growth():
    cls, _ = classify_growth_value(_assessment(valuation_label="fair", price_vs_fv=0.02))
    assert cls == GrowthValueClass.FAIRLY_VALUED_GROWTH


def test_premium_justified_needs_exceptional_growth_and_positive_momentum():
    cls, _ = classify_growth_value(
        _assessment(growth="exceptional", quality=80, valuation_label="premium",
                    price_vs_fv=0.25, momentum="IMPROVING"))
    assert cls == GrowthValueClass.PREMIUM_BUT_JUSTIFIED


def test_premium_without_support_is_expensive_growth():
    cls, _ = classify_growth_value(
        _assessment(growth="high", quality=80, valuation_label="premium",
                    price_vs_fv=0.30, momentum="NEUTRAL"))
    assert cls == GrowthValueClass.EXPENSIVE_GROWTH


def test_value_trap():
    cls, reasons = classify_growth_value(
        _assessment(growth="low", quality=35, valuation_label="value",
                    price_vs_fv=-0.30, momentum="DETERIORATING"))
    assert cls == GrowthValueClass.VALUE_TRAP
    assert any("cheap" in r for r in reasons)


def test_speculative_growth_when_earnings_immature():
    cls, _ = classify_growth_value(
        _assessment(growth="exceptional", business=BusinessType.EARLY_STAGE))
    assert cls == GrowthValueClass.SPECULATIVE_GROWTH


def test_unclassified_when_growth_not_high():
    cls, _ = classify_growth_value(_assessment(growth="medium", quality=70))
    assert cls == GrowthValueClass.UNCLASSIFIED
