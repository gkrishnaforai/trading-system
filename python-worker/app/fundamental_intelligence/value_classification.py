"""Deterministic growth-vs-value master classification.

Composes the existing fundamental dimensions into a single honest label:
quality gates eligibility, valuation-vs-fair-value sets conviction, and
estimate-revision momentum confirms or denies the trajectory. Cheap is never
treated as undervalued — deteriorating growth at a low multiple is a trap.
"""
from __future__ import annotations

from enum import Enum
from typing import List, Optional, Tuple

from .models import FundamentalAssessment


class GrowthValueClass(str, Enum):
    UNDERVALUED_GROWTH = "UNDERVALUED_GROWTH"
    FAIRLY_VALUED_GROWTH = "FAIRLY_VALUED_GROWTH"
    PREMIUM_BUT_JUSTIFIED = "PREMIUM_BUT_JUSTIFIED"
    EXPENSIVE_GROWTH = "EXPENSIVE_GROWTH"
    SPECULATIVE_GROWTH = "SPECULATIVE_GROWTH"
    VALUE_TRAP = "VALUE_TRAP"
    UNCLASSIFIED = "UNCLASSIFIED"


_HIGH = {"high", "exceptional"}
_POSITIVE_MOMENTUM = {"STRONG", "IMPROVING"}
_NEGATIVE_MOMENTUM = {"DETERIORATING"}


def classify_growth_value(
    assessment: FundamentalAssessment,
) -> Tuple[GrowthValueClass, List[str]]:
    """Map (growth, quality, valuation, momentum) onto a master class."""
    reasons: List[str] = []

    growth_high = assessment.growth.label in _HIGH
    growth_low = assessment.growth.label in {"low", "negative"}
    quality_high = (assessment.quality_score or 0.0) >= 60
    valuation = assessment.valuation.valuation_label
    price_vs_fv = assessment.valuation.price_vs_base_fv_pct
    momentum_label = str((assessment.momentum or {}).get("label") or "").upper()
    momentum_positive = momentum_label in _POSITIVE_MOMENTUM
    momentum_negative = momentum_label in _NEGATIVE_MOMENTUM
    earnings_immature = (
        assessment.business_type.value in {"early_stage"}
        or (
            assessment.valuation.forward_pe is None
            and assessment.valuation.trailing_pe is None
            and assessment.profitability.label == "unavailable"
        )
    )

    if growth_high:
        reasons.append(f"growth: {assessment.growth.label}")
    if quality_high and assessment.quality_score is not None:
        reasons.append(f"quality score: {assessment.quality_score:.0f}/100")
    if valuation != "unavailable":
        reasons.append(f"valuation: {valuation}")
    if price_vs_fv is not None:
        reasons.append(f"price vs base fair value: {price_vs_fv:+.1%}")
    if momentum_label and momentum_label != "UNAVAILABLE":
        reasons.append(f"estimate momentum: {momentum_label}")

    # Value trap first: cheap multiple with deteriorating evidence is not a buy.
    if growth_low and (momentum_negative or not quality_high):
        reasons.append("weak/negative growth with deteriorating evidence — cheap ≠ undervalued")
        return GrowthValueClass.VALUE_TRAP, reasons

    if earnings_immature:
        reasons.append("earnings/FCF not yet economically mature — valuation is scenario-dependent")
        return GrowthValueClass.SPECULATIVE_GROWTH, reasons

    if not growth_high:
        return GrowthValueClass.UNCLASSIFIED, reasons + ["growth is not in the high/exceptional band"]

    cheap = valuation in {"deep_value", "value"} or (price_vs_fv is not None and price_vs_fv <= -0.15)
    fair = valuation in {"fair"} or (price_vs_fv is not None and -0.15 < price_vs_fv <= 0.10)
    expensive = valuation in {"premium", "extreme_premium"} or (price_vs_fv is not None and price_vs_fv > 0.10)

    if cheap and quality_high and not momentum_negative:
        return GrowthValueClass.UNDERVALUED_GROWTH, reasons + [
            "price is meaningfully below fair value while growth and quality remain high"]

    if fair and quality_high:
        return GrowthValueClass.FAIRLY_VALUED_GROWTH, reasons + [
            "price is near fair value; growth and quality remain high"]

    if expensive and assessment.growth.label == "exceptional" and quality_high and momentum_positive:
        return GrowthValueClass.PREMIUM_BUT_JUSTIFIED, reasons + [
            "valuation is premium but exceptional growth with positive revisions can plausibly support it"]

    if expensive:
        return GrowthValueClass.EXPENSIVE_GROWTH, reasons + [
            "growth is high but the current multiple prices in more than the evidence supports"]

    if quality_high:
        return GrowthValueClass.FAIRLY_VALUED_GROWTH, reasons + [
            "valuation evidence is incomplete; growth and quality remain high"]

    return GrowthValueClass.UNCLASSIFIED, reasons + ["evidence is mixed or incomplete"]
