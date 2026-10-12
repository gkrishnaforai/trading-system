"""Deterministic fundamental intelligence rules over canonical provider data."""
from __future__ import annotations

from typing import Dict, Optional

from app.market_data.models import CompanyProfile, FundamentalsSnapshot, Quote

from .models import (
    BusinessType, DimensionAssessment, DimensionLabel, FundamentalAssessment,
    ValuationDiagnostics,
)
from .momentum import FundamentalMomentumAssessment


def _percent(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return value * 100 if abs(value) <= 2 else value


def _avg(values: list[Optional[float]]) -> tuple[Optional[float], float]:
    available = [v for v in values if v is not None]
    return (sum(available) / len(available), len(available) / len(values)) if available else (None, 0.0)


def _band(score: Optional[float], *, negative_below: Optional[float] = None) -> str:
    if score is None:
        return DimensionLabel.UNAVAILABLE.value
    if negative_below is not None and score < negative_below:
        return DimensionLabel.NEGATIVE.value
    if score >= 85:
        return DimensionLabel.EXCEPTIONAL.value
    if score >= 70:
        return DimensionLabel.HIGH.value
    if score >= 50:
        return DimensionLabel.MEDIUM.value
    return DimensionLabel.LOW.value


def _growth(snapshot: FundamentalsSnapshot) -> DimensionAssessment:
    revenue = _percent(snapshot.revenue_growth)
    earnings = _percent(snapshot.earnings_growth)
    values = [revenue, earnings]
    avg, coverage = _avg(values)
    score = None if avg is None else max(0.0, min(100.0, 50 + avg * 1.5))
    return DimensionAssessment(
        label=("negative" if avg is not None and avg < 0 else _band(score)),
        score=score, coverage=coverage,
        metrics={"revenue_growth": revenue, "earnings_growth": earnings},
        reasons=["TTM growth only; CAGR and forward growth unavailable"] if coverage < 1 else [],
    )


def _profitability(snapshot: FundamentalsSnapshot) -> DimensionAssessment:
    metrics = {
        "gross_margin": _percent(snapshot.gross_margin),
        "operating_margin": _percent(snapshot.operating_margin),
        "profit_margin": _percent(snapshot.profit_margin),
        "roe": _percent(snapshot.roe),
        "roa": _percent(snapshot.roa),
    }
    avg, coverage = _avg(list(metrics.values()))
    score = None if avg is None else max(0.0, min(100.0, 45 + avg * 1.5))
    return DimensionAssessment(label=_band(score), score=score, coverage=coverage, metrics=metrics)


def _cash_flow(snapshot: FundamentalsSnapshot) -> DimensionAssessment:
    # Do not derive FCF conversion here: current providers may report FCF
    # per-share while net income is absolute. Mixing units would fabricate
    # a cash-flow-quality signal.
    metrics = {
        "operating_cash_flow": snapshot.operating_cash_flow,
        "free_cash_flow": snapshot.free_cash_flow,
    }
    available = [v for v in metrics.values() if v is not None]
    score = None
    if snapshot.operating_cash_flow is not None and snapshot.free_cash_flow is not None:
        score = 65.0 if snapshot.operating_cash_flow > 0 and snapshot.free_cash_flow > 0 else 25.0
    elif snapshot.free_cash_flow is not None:
        score = 60.0 if snapshot.free_cash_flow > 0 else 25.0
    return DimensionAssessment(
        label=_band(score), score=score,
        coverage=len(available) / 2, metrics=metrics,
        reasons=["FCF units/provider mapping require normalization; SBC, capex intensity, and multi-year trend unavailable"],
    )


def _balance_sheet(snapshot: FundamentalsSnapshot) -> DimensionAssessment:
    metrics = {
        "current_ratio": snapshot.current_ratio,
        "quick_ratio": snapshot.quick_ratio,
        "debt_to_equity": snapshot.debt_to_equity,
    }
    components = []
    if snapshot.current_ratio is not None:
        components.append(min(100.0, max(0.0, snapshot.current_ratio / 2 * 100)))
    if snapshot.quick_ratio is not None:
        components.append(min(100.0, max(0.0, snapshot.quick_ratio / 1.5 * 100)))
    if snapshot.debt_to_equity is not None:
        components.append(min(100.0, max(0.0, 100 - snapshot.debt_to_equity * 40)))
    score = sum(components) / len(components) if components else None
    return DimensionAssessment(
        label=_band(score), score=score, coverage=len(components) / 3,
        metrics=metrics, reasons=["debt maturity and interest coverage unavailable"],
    )


def _capital_efficiency(snapshot: FundamentalsSnapshot) -> DimensionAssessment:
    metrics = {"roe": _percent(snapshot.roe), "roa": _percent(snapshot.roa)}
    avg, coverage = _avg(list(metrics.values()))
    score = None if avg is None else max(0.0, min(100.0, 45 + avg * 1.5))
    return DimensionAssessment(
        label=_band(score), score=score, coverage=coverage,
        metrics=metrics, reasons=["ROIC and incremental ROIC unavailable"],
    )


def _business_type(profile: Optional[CompanyProfile], snapshot: FundamentalsSnapshot) -> BusinessType:
    sector = (profile.sector if profile else "") or ""
    sector_lower = sector.lower()
    if "financial" in sector_lower or "bank" in sector_lower:
        return BusinessType.FINANCIAL
    if "real estate" in sector_lower:
        return BusinessType.REIT
    if "energy" in sector_lower or "material" in sector_lower:
        return BusinessType.COMMODITY
    growth = _percent(snapshot.revenue_growth)
    if growth is not None and growth >= 20:
        return BusinessType.SECULAR_GROWTH
    if growth is not None and growth < 0:
        return BusinessType.CYCLICAL
    if snapshot.profit_margin is not None and snapshot.profit_margin > 0:
        return BusinessType.MATURE_COMPOUNDER
    return BusinessType.UNKNOWN


def _valuation(
    snapshot: FundamentalsSnapshot,
    quote: Optional[Quote],
    fair_value_band: Optional[Dict[str, Any]] = None,
) -> ValuationDiagnostics:
    price = quote.price if quote else None
    forward_pe = snapshot.forward_pe
    peg = snapshot.peg_ratio
    fv_bear = fv_base = fv_bull = None
    price_vs_fv = None
    fv_source = fv_regime = None
    dcf_available = False
    if fair_value_band:
        fv_bear = fair_value_band.get("fair_value_bear")
        fv_base = fair_value_band.get("fair_value_base")
        fv_bull = fair_value_band.get("fair_value_bull")
        fv_source = fair_value_band.get("source")
        fv_regime = fair_value_band.get("v2_regime")
        dcf_available = fv_bear is not None or fv_bull is not None
    if fv_base and price:
        price_vs_fv = (float(price) / float(fv_base)) - 1.0
        label = (DimensionLabel.VALUE.value if price_vs_fv <= -0.15 else
                 DimensionLabel.FAIR.value if price_vs_fv <= 0.10 else
                 DimensionLabel.PREMIUM.value if price_vs_fv <= 0.40 else
                 DimensionLabel.EXTREME_PREMIUM.value)
        reasons = [f"fair-value band from {fv_source or 'fair_value_engine'}"]
    elif peg is not None:
        label = (DimensionLabel.VALUE.value if peg <= 1 else
                 DimensionLabel.FAIR.value if peg <= 1.5 else
                 DimensionLabel.PREMIUM.value)
        reasons = ["peer and historical multiples unavailable", "justified P/E unavailable"]
    elif forward_pe is not None:
        label = (DimensionLabel.VALUE.value if forward_pe <= 15 else
                 DimensionLabel.FAIR.value if forward_pe <= 25 else
                 DimensionLabel.PREMIUM.value)
        reasons = ["peer and historical multiples unavailable", "justified P/E unavailable"]
    else:
        label = DimensionLabel.UNAVAILABLE.value
        reasons = ["peer and historical multiples unavailable", "justified P/E unavailable"]
    return ValuationDiagnostics(
        current_price=price,
        trailing_pe=snapshot.pe_ratio,
        forward_pe=forward_pe,
        peg=peg,
        price_to_sales=snapshot.price_to_sales,
        price_to_book=snapshot.pb_ratio,
        dcf_available=dcf_available,
        fair_value_bear=fv_bear,
        fair_value_base=fv_base,
        fair_value_bull=fv_bull,
        price_vs_base_fv_pct=price_vs_fv,
        fair_value_source=fv_source,
        fair_value_regime=fv_regime,
        valuation_label=label,
        reasons=reasons,
    )


def assess_fundamentals(
    symbol: str,
    snapshot: Optional[FundamentalsSnapshot],
    *,
    profile: Optional[CompanyProfile] = None,
    quote: Optional[Quote] = None,
    momentum: Optional[FundamentalMomentumAssessment] = None,
    fair_value_band: Optional[Dict[str, Any]] = None,
) -> FundamentalAssessment:
    """Build an honest multi-dimensional assessment; missing data stays missing."""
    if snapshot is None:
        return FundamentalAssessment(symbol=symbol, data_quality="insufficient", thesis=["fundamentals unavailable"])

    growth = _growth(snapshot)
    profitability = _profitability(snapshot)
    cash_flow = _cash_flow(snapshot)
    balance = _balance_sheet(snapshot)
    capital = _capital_efficiency(snapshot)
    unavailable = DimensionAssessment(
        label=DimensionLabel.UNAVAILABLE.value, reasons=["structured provider data unavailable"])
    risk = DimensionAssessment(
        label=DimensionLabel.UNAVAILABLE.value,
        reasons=["business-specific risk inputs and point-in-time events unavailable"],
    )
    dimensions = [growth, profitability, cash_flow, balance, capital]
    scores = [d.score for d in dimensions if d.score is not None]
    quality_score = sum(scores) / len(scores) if scores else None
    coverage = len(scores) / len(dimensions)
    btype = _business_type(profile, snapshot)
    flags = list(risk.reasons)
    if btype in {BusinessType.CYCLICAL, BusinessType.COMMODITY}:
        flags.append("cyclical or commodity-sensitive business type")
    if btype == BusinessType.FINANCIAL:
        flags.append("financial/regulatory/cycle-specific analysis required")
    thesis = []
    if growth.label in {"high", "exceptional"}:
        thesis.append("growth metrics are supportive")
    if profitability.label in {"high", "exceptional"}:
        thesis.append("profitability metrics are supportive")
    if not thesis:
        thesis.append("fundamental evidence is incomplete")
    valuation = _valuation(snapshot, quote, fair_value_band)
    assessment = FundamentalAssessment(
        symbol=symbol, as_of=snapshot.as_of.isoformat() if snapshot.as_of else None,
        provider=snapshot.provider, business_type=btype, growth=growth,
        profitability=profitability, cash_flow_quality=cash_flow,
        balance_sheet=balance, capital_efficiency=capital,
        competitive_advantage=unavailable, earnings_revision=unavailable,
        risk=risk, momentum=(momentum.model_dump(mode="json") if momentum else {}),
        quality_score=quality_score, quality_coverage=coverage,
        field_coverage={**snapshot.coverage, "quality_dimensions": coverage},
        missing_fields=list(snapshot.missing_fields),
        valuation=valuation,
        style_tags=[btype.value] if btype != BusinessType.UNKNOWN else [],
        risk_flags=flags, thesis=thesis,
        data_quality="good" if coverage >= 0.6 else "partial",
        provenance={"rules_version": "fundamental-intelligence-v1", "source": snapshot.provider},
    )
    from .value_classification import classify_growth_value
    growth_class, class_reasons = classify_growth_value(assessment)
    return assessment.model_copy(update={
        "growth_value_class": growth_class.value,
        "classification_reasons": class_reasons,
    })
