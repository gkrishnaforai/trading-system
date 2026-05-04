"""
Fair Value Analysis Service
Implements institutional-grade fair value calculation using multiple valuation methods
"""

from dataclasses import dataclass
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta
import logging
import math
import os
import json
import uuid

from sqlalchemy import text
from app.database import db
from app.observability.logging import get_logger

logger = get_logger(__name__)

_TRUE_VALUES = {"1", "true", "yes", "y", "on"}
ENABLE_PEG_RULE_OF_40_FORWARD_CAGR = os.getenv("ENABLE_PEG_RULE_OF_40_FORWARD_CAGR", "true").strip().lower() in _TRUE_VALUES
ENABLE_FAIR_VALUE_GROWTH_PROXY = os.getenv("ENABLE_FAIR_VALUE_GROWTH_PROXY", "true").strip().lower() in _TRUE_VALUES
ENABLE_FAIR_VALUE_FORWARD_EPS_CLAMP = os.getenv("ENABLE_FAIR_VALUE_FORWARD_EPS_CLAMP", "true").strip().lower() in _TRUE_VALUES
ENABLE_FAIR_VALUE_REGIME_GATING = os.getenv("ENABLE_FAIR_VALUE_REGIME_GATING", "true").strip().lower() in _TRUE_VALUES
ENABLE_FAIR_VALUE_LIVE_PRICE_FALLBACK = os.getenv("ENABLE_FAIR_VALUE_LIVE_PRICE_FALLBACK", "false").strip().lower() in _TRUE_VALUES
try:
    FAIR_VALUE_DISCOUNT_RATE_SHIFT = float(os.getenv("FAIR_VALUE_DISCOUNT_RATE_SHIFT", "0.0") or 0.0)
except Exception:
    FAIR_VALUE_DISCOUNT_RATE_SHIFT = 0.0

@dataclass
class FairValueResult:
    run_id: Optional[str]
    symbol: str
    current_price: float
    fair_value: float
    valuation_metrics: Dict[str, Any]
    quality_score: float
    individual_valuations: Dict[str, Any]
    fundamentals: Dict[str, Any]
    updated_at: datetime


_METHOD_SEVERITY = {
    "ok": 0,
    "missing_data": 1,
    "disabled_by_regime": 2,
    "invalid_assumption": 3,
}

_REGIME_UNPROFITABLE_GROWTH = "unprofitable_growth"
_REGIME_GROWTH_COMPOUNDER = "profitable_growth_compounder"
_REGIME_MATURE_VALUE = "mature_value"
_REGIME_CYCLICAL = "cyclical"

@dataclass
class FundamentalData:
    current_price: float
    eps_ttm: float
    eps_forward: float
    eps_yoy_growth: float
    revenue: float
    revenue_yoy_growth: float
    gross_margin: float
    operating_margin: float
    net_margin: float
    roic: float
    debt_to_equity: float
    current_pe: float
    forward_pe: float
    peg_ratio: float
    industry: str
    market_cap: float
    shares_outstanding: float
    cash_and_equivalents: float
    total_debt: float
    free_cash_flow: float
    book_value: float
    data_quality: Dict[str, Any]

class FairValueService:
    """Service for calculating fair value using multiple valuation methods"""
    
    def __init__(self):
        self.industry_benchmarks = self._load_industry_benchmarks()
        self.quality_thresholds = self._load_quality_thresholds()
        self.method_reliability: Dict[str, float] = {
            "dcf_simple": 0.8,
            "pe_forward": 1.0,
            "peg_legacy": 0.7,
            "peg_rule_of_40_forward_cagr": 1.1,
            "ev_sales": 0.6,
            "adjusted_pe": 1.0,
            "pb_bank": 1.0,
        }
        self.method_known = {
            "dcf_simple": {"name": "DCF (Simple)", "category": "intrinsic"},
            "pe_forward": {"name": "Forward P/E", "category": "multiples"},
            "peg_legacy": {"name": "PEG", "category": "multiples"},
            "peg_rule_of_40_forward_cagr": {"name": "PEG (Rule of 40, Forward CAGR)", "category": "multiples"},
            "adjusted_pe": {"name": "Adjusted P/E", "category": "multiples"},
            "ev_sales": {"name": "EV/Sales", "category": "multiples"},
            "pb_bank": {"name": "P/B (Bank)", "category": "financials"},
        }

    def _safe_float(self, value: Any, *, default: float = 0.0) -> float:
        try:
            if value is None:
                return float(default)
            v = float(value)
            if math.isnan(v) or math.isinf(v):
                return float(default)
            return v
        except Exception:
            return float(default)

    def _clamp(self, v: float, lo: float, hi: float) -> float:
        try:
            return float(max(float(lo), min(float(hi), float(v))))
        except Exception:
            return float(lo)

    def _get_growth_proxy_pct(self, fundamentals: FundamentalData) -> float:
        if not ENABLE_FAIR_VALUE_GROWTH_PROXY:
            eps_growth = float(fundamentals.eps_yoy_growth or 0.0)
            rev_growth = float(fundamentals.revenue_yoy_growth or 0.0)
            return eps_growth if eps_growth > 0 else max(0.0, rev_growth)

        dq = fundamentals.data_quality or {}
        v = dq.get("growth_proxy_pct")
        try:
            if v is not None:
                return float(v)
        except Exception:
            pass

        eps_growth = float(fundamentals.eps_yoy_growth or 0.0)
        rev_growth = float(fundamentals.revenue_yoy_growth or 0.0)
        proxy = eps_growth if eps_growth > 0 else rev_growth
        return max(0.0, float(proxy or 0.0))

    def _cap_growth_proxy_pct(self, growth_proxy_pct: float, regime: Optional[str]) -> float:
        if not ENABLE_FAIR_VALUE_GROWTH_PROXY:
            return float(max(0.0, growth_proxy_pct))
        try:
            g = float(growth_proxy_pct)
        except Exception:
            return 0.0
        g = max(0.0, g)

        cap_growth = float(os.getenv("FAIR_VALUE_GROWTH_PROXY_CAP_GROWTH", "60") or 60.0)
        cap_mature = float(os.getenv("FAIR_VALUE_GROWTH_PROXY_CAP_MATURE", "20") or 20.0)
        cap_cyclical = float(os.getenv("FAIR_VALUE_GROWTH_PROXY_CAP_CYCLICAL", "15") or 15.0)
        cap_unprofitable = float(os.getenv("FAIR_VALUE_GROWTH_PROXY_CAP_UNPROFITABLE", "25") or 25.0)

        if regime == _REGIME_GROWTH_COMPOUNDER:
            return min(g, cap_growth)
        if regime == _REGIME_MATURE_VALUE:
            return min(g, cap_mature)
        if regime == _REGIME_CYCLICAL:
            return min(g, cap_cyclical)
        if regime == _REGIME_UNPROFITABLE_GROWTH:
            return min(g, cap_unprofitable)
        return min(g, cap_mature)

    def _sigmoid(self, x: float) -> float:
        try:
            return 1.0 / (1.0 + math.exp(-float(x)))
        except Exception:
            return 0.5
        
    def _load_industry_benchmarks(self) -> Dict[str, Dict[str, float]]:
        """Load industry-specific benchmarks for valuation"""
        return {
            'Technology': {
                'avg_pe': 25.0,
                'avg_peg': 1.2,
                'avg_growth': 15.0,
                'avg_margin': 70.0,
                'avg_roic': 18.0,
                'avg_debt_equity': 0.3
            },
            'Healthcare': {
                'avg_pe': 20.0,
                'avg_peg': 1.0,
                'avg_growth': 12.0,
                'avg_margin': 65.0,
                'avg_roic': 15.0,
                'avg_debt_equity': 0.4
            },
            'Finance': {
                'avg_pe': 12.0,
                'avg_peg': 0.8,
                'avg_growth': 8.0,
                'avg_margin': 25.0,
                'avg_roic': 10.0,
                'avg_debt_equity': 1.0
            },
            'Financial Data & Stock Exchanges': {
                'avg_pe': 22.0,
                'avg_peg': 1.1,
                'avg_growth': 20.0,
                'avg_margin': 40.0,
                'avg_roic': 15.0,
                'avg_debt_equity': 0.2
            },
            'Consumer': {
                'avg_pe': 18.0,
                'avg_peg': 1.0,
                'avg_growth': 10.0,
                'avg_margin': 30.0,
                'avg_roic': 12.0,
                'avg_debt_equity': 0.5
            },
            'Energy': {
                'avg_pe': 15.0,
                'avg_peg': 0.9,
                'avg_growth': 5.0,
                'avg_margin': 20.0,
                'avg_roic': 8.0,
                'avg_debt_equity': 0.6
            },
            'Industrial': {
                'avg_pe': 16.0,
                'avg_peg': 0.9,
                'avg_growth': 8.0,
                'avg_margin': 25.0,
                'avg_roic': 11.0,
                'avg_debt_equity': 0.4
            },
            'Materials': {
                'avg_pe': 14.0,
                'avg_peg': 0.8,
                'avg_growth': 6.0,
                'avg_margin': 22.0,
                'avg_roic': 9.0,
                'avg_debt_equity': 0.5
            },
            'Utilities': {
                'avg_pe': 17.0,
                'avg_peg': 1.1,
                'avg_growth': 4.0,
                'avg_margin': 35.0,
                'avg_roic': 7.0,
                'avg_debt_equity': 0.8
            },
            'Real Estate': {
                'avg_pe': 19.0,
                'avg_peg': 1.0,
                'avg_growth': 7.0,
                'avg_margin': 28.0,
                'avg_roic': 8.0,
                'avg_debt_equity': 0.9
            },
            'Telecommunications': {
                'avg_pe': 16.0,
                'avg_peg': 0.9,
                'avg_growth': 6.0,
                'avg_margin': 40.0,
                'avg_roic': 9.0,
                'avg_debt_equity': 0.7
            }
        }

    def _detect_regime(self, fundamentals: FundamentalData) -> str:
        eps_ttm = float(fundamentals.eps_ttm or 0.0)
        eps_forward = float(fundamentals.eps_forward or 0.0)
        eps_growth = float(fundamentals.eps_yoy_growth or 0.0)
        revenue_growth = float(fundamentals.revenue_yoy_growth or 0.0)
        growth = float(self._get_growth_proxy_pct(fundamentals) or 0.0)
        gross_margin = float(fundamentals.gross_margin or 0.0)
        net_margin = float(fundamentals.net_margin or 0.0)
        free_cash_flow = float(fundamentals.free_cash_flow or 0.0)

        # Normalize margin units: some upstream sources store margins as fractions (0-1)
        # while regime thresholds are expressed in percent.
        try:
            if 0.0 < float(gross_margin) <= 1.5:
                gross_margin = float(gross_margin) * 100.0
        except Exception:
            pass

        compounder_threshold = 35.0
        stability_floor = 20.0

        if eps_ttm <= 0 and eps_forward <= 0:
            return _REGIME_UNPROFITABLE_GROWTH

        industry_l = ""
        try:
            industry_l = str(fundamentals.industry or "").lower()
        except Exception:
            industry_l = ""

        # Financials heuristic: banks/insurers/capital markets do not fit EV/Sales or growth-PEG logic.
        # Treat as mature/stable by default.
        try:
            if ENABLE_FAIR_VALUE_REGIME_GATING:
                if (
                    "bank" in industry_l
                    or "banks" in industry_l
                    or "insurance" in industry_l
                    or "financial" in industry_l
                    or "capital markets" in industry_l
                    or "credit" in industry_l
                ):
                    return _REGIME_MATURE_VALUE
        except Exception:
            pass

        # Healthcare/pharma heuristic: generally stable cash generators with mature valuation profiles.
        try:
            if ENABLE_FAIR_VALUE_REGIME_GATING:
                if (
                    "health" in industry_l
                    or "pharma" in industry_l
                    or "pharmaceutical" in industry_l
                    or "drug" in industry_l
                    or "biotech" in industry_l
                    or "medical" in industry_l
                ) and float(eps_ttm) > 0:
                    return _REGIME_MATURE_VALUE
        except Exception:
            pass

        # Stable consumer heuristic: classify as mature value early to avoid FCF-noise mislabeling.
        try:
            if ENABLE_FAIR_VALUE_REGIME_GATING:
                if (
                    ("beverage" in industry_l or "consumer" in industry_l or "household" in industry_l)
                    and float(eps_ttm) > 0.0
                ):
                    return _REGIME_MATURE_VALUE
        except Exception:
            pass

        # Unprofitable growth gating: allow negative net margin OR nonpositive FCF to trigger,
        # but only for growth/tech-like profiles (high gross margin or SaaS-ish industries).
        try:
            if ENABLE_FAIR_VALUE_REGIME_GATING:
                tech_like = (
                    "software" in industry_l
                    or "data" in industry_l
                    or "internet" in industry_l
                    or "application" in industry_l
                    or "cloud" in industry_l
                    or "saas" in industry_l
                )
                high_gm = float(gross_margin) >= 40.0
                if (float(net_margin) < 0.0 or float(free_cash_flow) <= 0.0) and (tech_like or high_gm):
                    return _REGIME_UNPROFITABLE_GROWTH
        except Exception:
            pass

        # Light cyclical heuristic: semiconductors frequently exhibit boom/bust earnings.
        # Only apply when explicit gating is enabled.
        try:
            if ENABLE_FAIR_VALUE_REGIME_GATING:
                industry = str(fundamentals.industry or "").lower()
                if "semi" in industry or "semiconductor" in industry:
                    if growth >= 10.0 and gross_margin < 60.0:
                        return _REGIME_CYCLICAL
        except Exception:
            pass

        if growth >= 10.0 and gross_margin >= 35.0:
            return _REGIME_GROWTH_COMPOUNDER

        if growth < 10.0 and gross_margin >= stability_floor:
            return _REGIME_MATURE_VALUE

        return _REGIME_CYCLICAL

    def _severity_for_status(self, status: str) -> int:
        return int(_METHOD_SEVERITY.get(status, 3))

    def _build_reason(self, code: str, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return {
            "code": code,
            "details": details or {},
        }

    def _build_method_result(
        self,
        *,
        method_key: str,
        enabled: bool,
        fair_price: Optional[float],
        status_if_missing: str,
        metrics: Optional[Dict[str, Any]] = None,
        score: Optional[float] = None,
        reason_code_if_missing: str = "DATA_NOT_AVAILABLE",
        reason_details_if_missing: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if fair_price is not None and float(fair_price) > 0:
            status = "ok"
            reason = None
        else:
            status = status_if_missing
            reason = self._build_reason(reason_code_if_missing, reason_details_if_missing)

        return {
            "method_key": method_key,
            "enabled": bool(enabled),
            "status": status,
            "severity": self._severity_for_status(status),
            "reason": reason,
            "fair_price": float(fair_price) if fair_price is not None and float(fair_price) > 0 else None,
            "score": float(score) if score is not None else None,
            "metrics": metrics or {},
        }

    def _build_disabled_or_invalid_method(
        self,
        *,
        method_key: str,
        enabled: bool,
        status: str,
        reason_code: str,
        reason_details: Optional[Dict[str, Any]] = None,
        metrics: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return {
            "method_key": method_key,
            "enabled": bool(enabled),
            "status": status,
            "severity": self._severity_for_status(status),
            "reason": self._build_reason(reason_code, reason_details),
            "fair_price": None,
            "score": None,
            "metrics": metrics or {},
        }

    def _calculate_ev_sales_value(self, fundamentals: FundamentalData) -> Tuple[Optional[float], Dict[str, Any]]:
        metrics: Dict[str, Any] = {
            "base_multiple": 3.0,
            "growth_weight": 0.8,
            "margin_weight": 0.6,
            "growth_margin_shrink": 0.5,
            "op_leverage_boost_max": 0.15,
            "fcf_margin_adjustment_min": 0.75,
            "fcf_margin_adjustment_max": 1.05,
            "min_cap": 2.0,
            "max_cap": 20.0,
        }

        # EV/Sales is not meaningful for financials (revenue definitions differ materially).
        try:
            industry_l = str(fundamentals.industry or "").lower()
            if (
                "bank" in industry_l
                or "banks" in industry_l
                or "insurance" in industry_l
                or "financial" in industry_l
                or "capital markets" in industry_l
                or "credit" in industry_l
            ):
                return None, {**metrics, "reason": "ev_sales_not_applicable_financials"}
        except Exception:
            pass

        if fundamentals.revenue is None or float(fundamentals.revenue) <= 0:
            return None, {**metrics, "reason": "revenue_missing_or_nonpositive"}
        if fundamentals.shares_outstanding is None or float(fundamentals.shares_outstanding) <= 0:
            return None, {**metrics, "reason": "shares_outstanding_missing_or_nonpositive"}

        revenue = float(fundamentals.revenue)
        growth_pct = float(fundamentals.revenue_yoy_growth or 0.0)
        gross_margin = float(fundamentals.gross_margin or 0.0)

        # Unprofitable growth (esp. software/SaaS) often trades at materially higher EV/S multiples.
        # Make caps adaptive for high gross margin / software-like industries.
        try:
            industry_l = str(fundamentals.industry or "").lower()
        except Exception:
            industry_l = ""
        try:
            tech_like = (
                "software" in industry_l
                or "data" in industry_l
                or "internet" in industry_l
                or "application" in industry_l
                or "cloud" in industry_l
                or "saas" in industry_l
            )
            high_gm = float(gross_margin) >= 55.0
            if tech_like or high_gm:
                metrics["base_multiple"] = float(os.getenv("FAIR_VALUE_EV_SALES_TECH_BASE", "6.0") or 6.0)
                metrics["max_cap"] = float(os.getenv("FAIR_VALUE_EV_SALES_TECH_MAX", "40.0") or 40.0)
                metrics["min_cap"] = float(os.getenv("FAIR_VALUE_EV_SALES_TECH_MIN", "3.0") or 3.0)
                metrics["policy"] = "tech_ev_sales"
        except Exception:
            pass

        growth_component = (max(0.0, min(growth_pct, 60.0)) / 10.0) * float(metrics["growth_weight"])
        margin_component = (max(0.0, min(gross_margin, 80.0)) / 10.0) * float(metrics["margin_weight"])
        shrink = float(metrics.get("growth_margin_shrink", 0.5))
        target_multiple_raw = float(metrics["base_multiple"]) + (growth_component * shrink) + (margin_component * shrink)

        try:
            fcf_margin_pct = None
            if revenue and float(revenue) > 0:
                fcf_margin_pct = 100.0 * float(fundamentals.free_cash_flow or 0.0) / float(revenue)
            if fcf_margin_pct is not None:
                metrics["fcf_margin_pct"] = float(fcf_margin_pct)
                fcf_adj = 1.0
                if float(fcf_margin_pct) < 0.0:
                    fcf_adj = 0.75
                elif float(fcf_margin_pct) < 5.0:
                    fcf_adj = 0.85
                elif float(fcf_margin_pct) < 10.0:
                    fcf_adj = 0.95
                elif float(fcf_margin_pct) > 20.0:
                    fcf_adj = 1.05

                fcf_adj = max(float(metrics.get("fcf_margin_adjustment_min", 0.75)), min(float(metrics.get("fcf_margin_adjustment_max", 1.05)), float(fcf_adj)))
                if fcf_adj != 1.0:
                    target_multiple_raw = float(target_multiple_raw) * float(fcf_adj)
                metrics["fcf_margin_adjustment"] = float(fcf_adj)
        except Exception:
            pass

        # Operating leverage / scalability signal (kept small to avoid re-introducing double counting).
        try:
            op_boost = 0.0
            if float(fundamentals.gross_margin or 0.0) >= 60.0:
                op_boost += 0.08
            if float(fundamentals.operating_margin or 0.0) >= 15.0:
                op_boost += 0.07
            op_boost = min(op_boost, float(metrics.get("op_leverage_boost_max", 0.15)))
            if op_boost > 0:
                target_multiple_raw = target_multiple_raw * (1.0 + op_boost)
                metrics["operating_leverage_boost"] = op_boost
        except Exception:
            pass

        if float(fundamentals.net_margin or 0.0) < 0.0:
            target_multiple_raw = target_multiple_raw * 0.8
            metrics["profitability_adjustment"] = 0.8

        target_multiple = max(float(metrics["min_cap"]), min(float(metrics["max_cap"]), target_multiple_raw))

        shares_outstanding = float(fundamentals.shares_outstanding)
        projected_shares = None
        try:
            projected_shares = float((fundamentals.data_quality or {}).get("projected_shares_outstanding") or 0.0)
        except Exception:
            projected_shares = None
        shares_used = projected_shares if projected_shares and projected_shares > shares_outstanding else shares_outstanding

        enterprise_value = target_multiple * revenue
        equity_value = enterprise_value - float(fundamentals.total_debt or 0.0) + float(fundamentals.cash_and_equivalents or 0.0)
        fair_price = equity_value / shares_used

        return fair_price if fair_price > 0 else None, {
            **metrics,
            "revenue": revenue,
            "revenue_yoy_growth_pct": growth_pct,
            "gross_margin_pct": gross_margin,
            "target_multiple_raw": target_multiple_raw,
            "target_multiple": target_multiple,
            "enterprise_value": enterprise_value,
            "equity_value": equity_value,
            "shares_used": shares_used,
            "shares_outstanding": shares_outstanding,
            "projected_shares_outstanding": projected_shares,
            "caps_hit": {
                "min": target_multiple_raw < float(metrics["min_cap"]),
                "max": target_multiple_raw > float(metrics["max_cap"]),
            },
        }

    def _calculate_adjusted_pe_value(self, fundamentals: FundamentalData) -> Tuple[Optional[float], Dict[str, Any]]:
        metrics: Dict[str, Any] = {
            "policy": "cyclical_adjusted_pe",
            "target_pe_cap": 25.0,
        }

        # Prefer TTM EPS for mature/stable profiles where forward EPS can be noisy/depressed.
        try:
            regime = str((fundamentals.data_quality or {}).get("regime") or "")
        except Exception:
            regime = ""
        try:
            industry_l = str(fundamentals.industry or "").lower()
        except Exception:
            industry_l = ""
        prefer_ttm = False
        try:
            if regime == _REGIME_MATURE_VALUE:
                prefer_ttm = True
            if "beverage" in industry_l or "consumer" in industry_l or "household" in industry_l:
                prefer_ttm = True
        except Exception:
            prefer_ttm = False

        eps_input = None
        try:
            eps_input = float((fundamentals.data_quality or {}).get("normalized_eps") or 0.0)
        except Exception:
            eps_input = None
        if eps_input is None or float(eps_input) <= 0:
            if prefer_ttm:
                eps_input = float(fundamentals.eps_ttm or 0.0)
                metrics["eps_fallback"] = "eps_ttm"
            else:
                eps_input = float(fundamentals.eps_forward or 0.0)
                metrics["eps_fallback"] = "eps_forward"
        else:
            metrics["eps_fallback"] = "normalized_eps"
        if eps_input <= 0:
            return None, {**metrics, "reason": "eps_forward_or_normalized_missing_or_nonpositive"}

        # If forward EPS looks depressed relative to TTM for an otherwise stable profitable business,
        # avoid anchoring cyclical/stable valuation entirely on it.
        try:
            eps_ttm = float(fundamentals.eps_ttm or 0.0)
            if metrics.get("eps_fallback") == "eps_forward" and eps_ttm > 0 and float(eps_input) > 0:
                nm = float(fundamentals.net_margin or 0.0)
                gm = float(fundamentals.gross_margin or 0.0)
                if 0.0 < gm <= 1.5:
                    gm = gm * 100.0

                stable_profitable = (nm >= 5.0 and gm >= 20.0)
                ratio = float(eps_input) / float(eps_ttm)
                min_ratio = float(os.getenv("FAIR_VALUE_ADJUSTED_PE_FORWARD_EPS_MIN_RATIO", "0.55") or 0.55)
                if stable_profitable and ratio < min_ratio:
                    eps_input = eps_ttm
                    metrics["eps_forward_depressed_ratio"] = float(ratio)
                    metrics["eps_forward_depressed_action"] = "use_eps_ttm"
        except Exception:
            pass

        # Clamp EPS inputs using fundamentals-only sanity checks.
        # Goal: prevent absurd EPS values from stale/wrong-unit estimates from dominating cyclical valuation.
        eps_caps_hit: List[str] = []
        try:
            eps_ttm = float(fundamentals.eps_ttm or 0.0)
            if eps_ttm > 0 and float(eps_input) > 0 and metrics.get("eps_fallback") == "eps_forward":
                max_ratio = float(os.getenv("FAIR_VALUE_ADJUSTED_PE_FORWARD_EPS_MAX_RATIO", "3.0") or 3.0)
                if float(eps_input) > float(eps_ttm) * float(max_ratio):
                    eps_input = float(eps_ttm) * float(max_ratio)
                    eps_caps_hit.append("eps_forward_vs_ttm")
        except Exception:
            pass

        try:
            revenue = float(fundamentals.revenue or 0.0)
            shares = float(fundamentals.shares_outstanding or 0.0)
            if revenue > 0 and shares > 0 and float(eps_input) > 0:
                revenue_per_share = revenue / shares
                nm = float(fundamentals.net_margin or 0.0)
                nm_frac = max(0.0, min(0.6, nm / 100.0))
                # If net margin isn't available/positive, assume a very conservative sustainable conversion.
                # For mature/staple profiles we often have missing margin fields in snapshots;
                # avoid crushing EPS by using an overly conservative default.
                conv_default = 0.10
                try:
                    if prefer_ttm and nm_frac == 0.0:
                        conv_default = float(os.getenv("FAIR_VALUE_STAPLES_EPS_CAP_CONV_DEFAULT", "0.18") or 0.18)
                except Exception:
                    conv_default = 0.10

                conv = nm_frac * 1.5 if nm_frac > 0 else float(conv_default)
                conv = max(0.08, min(0.50, conv))
                eps_cap = float(revenue_per_share) * float(conv)
                metrics.update({
                    "revenue_per_share": float(revenue_per_share),
                    "eps_sanity_cap": float(eps_cap),
                    "eps_sanity_cap_conv": float(conv),
                })
                # Apply cap less aggressively for mature/staple profiles.
                cap_buffer = 1.25
                try:
                    if prefer_ttm:
                        cap_buffer = float(os.getenv("FAIR_VALUE_STAPLES_EPS_CAP_BUFFER", "1.60") or 1.60)
                except Exception:
                    cap_buffer = 1.25

                if eps_cap > 0 and float(eps_input) > float(eps_cap) * float(cap_buffer):
                    eps_input = float(eps_cap) * float(cap_buffer)
                    eps_caps_hit.append("eps_vs_revenue_per_share")
        except Exception:
            pass

        if eps_caps_hit:
            metrics["eps_caps_hit"] = eps_caps_hit

        industry = fundamentals.industry
        industry_pe = float(self.industry_benchmarks.get(industry, {}).get('avg_pe', 18.0))
        target_pe_cap = float(metrics["target_pe_cap"])
        try:
            if (
                "bank" in industry_l
                or "banks" in industry_l
                or "insurance" in industry_l
                or "financial" in industry_l
                or "capital markets" in industry_l
                or "credit" in industry_l
            ):
                target_pe_cap = min(target_pe_cap, float(os.getenv("FAIR_VALUE_FINANCIALS_PE_CAP", "14.0") or 14.0))
                metrics["policy"] = "financials_adjusted_pe"
        except Exception:
            pass

        target_pe = min(industry_pe, float(target_pe_cap))
        fair_price = float(eps_input) * target_pe
        return fair_price if fair_price > 0 else None, {
            **metrics,
            "industry_pe": industry_pe,
            "target_pe": target_pe,
            "eps_used": float(eps_input),
            "eps_used_source": "normalized_eps" if (fundamentals.data_quality or {}).get("normalized_eps") else "eps_forward",
        }

    def _estimate_normalized_eps(self, symbol: str, fundamentals: FundamentalData) -> Tuple[Optional[float], Dict[str, Any]]:
        metrics: Dict[str, Any] = {
            "policy": "normalized_eps_annual_income_statements",
            "window_max_periods": 10,
            "min_periods": 3,
        }

        try:
            with db.get_session() as session:
                cols = session.execute(
                    text(
                        """
                        SELECT column_name
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = 'income_statements'
                        """
                    )
                ).fetchall()
                colset = {str(r[0]) for r in cols if r and r[0]}

                period_cols = ["period_end", "date", "report_date"]
                period_col = next((c for c in period_cols if c in colset), None)
                if not period_col:
                    return None, {**metrics, "reason": "income_statements_missing_period_col"}

                eps_col_candidates = ["net_income_per_share", "eps", "eps_diluted", "earnings_per_share"]
                eps_col = next((c for c in eps_col_candidates if c in colset), None)
                if not eps_col:
                    return None, {**metrics, "reason": "income_statements_missing_eps_col"}

                query = f"""
                SELECT {eps_col} as eps
                FROM income_statements
                WHERE stock_symbol = :symbol
                  AND (timeframe = 'annual' OR timeframe IS NULL)
                ORDER BY {period_col} DESC NULLS LAST, fiscal_year DESC NULLS LAST
                LIMIT :lim
                """
                rows = session.execute(text(query), {"symbol": symbol, "lim": int(metrics["window_max_periods"]) }).fetchall()

                eps_series: List[float] = []
                for r in rows or []:
                    try:
                        v = float(r[0])
                    except Exception:
                        continue
                    if math.isnan(v) or math.isinf(v):
                        continue
                    if v <= 0:
                        continue
                    eps_series.append(float(v))

                metrics["periods_found"] = int(len(rows or []))
                metrics["periods_used"] = int(len(eps_series))
                if len(eps_series) < int(metrics["min_periods"]):
                    return None, {**metrics, "reason": "insufficient_positive_eps_history"}

                eps_series.sort()
                mid = len(eps_series) // 2
                median = eps_series[mid] if (len(eps_series) % 2 == 1) else (eps_series[mid - 1] + eps_series[mid]) / 2.0
                if median <= 0:
                    return None, {**metrics, "reason": "median_nonpositive"}

                lo = 0.5 * float(median)
                hi = 2.0 * float(median)
                clipped = [min(hi, max(lo, v)) for v in eps_series]
                normalized = sum(clipped) / float(len(clipped))
                metrics.update({
                    "median_eps": float(median),
                    "clip_bounds": {"lo": float(lo), "hi": float(hi)},
                })

                return float(normalized) if normalized > 0 else None, metrics
        except Exception as e:
            return None, {**metrics, "reason": "error", "error": str(e)}

    def _get_regime_default_weights(self, regime: str) -> Dict[str, float]:
        if regime == _REGIME_UNPROFITABLE_GROWTH:
            return {"ev_sales": 0.65, "dcf_simple": 0.35}
        if regime == _REGIME_GROWTH_COMPOUNDER:
            return {"pe_forward": 0.35, "peg_legacy": 0.35, "peg_rule_of_40_forward_cagr": 0.35, "dcf_simple": 0.30}
        if regime == _REGIME_MATURE_VALUE:
            return {"pe_forward": 0.40, "dcf_simple": 0.30, "adjusted_pe": 0.15, "pb_bank": 0.15}
        return {"adjusted_pe": 1.0}

    def _calculate_pb_bank_value(self, fundamentals: FundamentalData) -> Tuple[Optional[float], Dict[str, Any]]:
        metrics: Dict[str, Any] = {
            "enabled": True,
            "method": "pb_bank",
        }

        industry_l = str(getattr(fundamentals, "industry", "") or "").strip().lower()
        is_financial = (
            "bank" in industry_l
            or "banks" in industry_l
            or "insurance" in industry_l
            or "financial" in industry_l
            or "capital markets" in industry_l
            or "credit" in industry_l
        )
        if not is_financial:
            return None, {**metrics, "enabled": False, "reason": "not_financial"}

        bvps = None
        try:
            bvps = float(fundamentals.book_value or 0.0)
        except Exception:
            bvps = None
        if bvps is None or bvps <= 0:
            return None, {**metrics, "reason": "missing_book_value_per_share", "book_value_per_share": bvps}

        dq = fundamentals.data_quality or {}
        roe_pct = None
        try:
            roe_pct = float(dq.get("roe") or 0.0)
        except Exception:
            roe_pct = None
        if roe_pct is None or roe_pct <= 0:
            return None, {**metrics, "reason": "missing_roe", "roe_pct": roe_pct, "book_value_per_share": bvps}

        # Convert to decimal if it looks like percentage
        roe = float(roe_pct)
        if roe > 1.5:
            roe = roe / 100.0

        cost_of_equity = float(os.getenv("FAIR_VALUE_FINANCIALS_COST_OF_EQUITY", "0.10") or 0.10)
        g = float(os.getenv("FAIR_VALUE_FINANCIALS_LONG_RUN_G", "0.03") or 0.03)
        # Guardrails
        cost_of_equity = max(0.06, min(0.16, float(cost_of_equity)))
        g = max(0.0, min(0.05, float(g)))
        roe = max(0.02, min(0.35, float(roe)))

        denom = float(cost_of_equity - g)
        if denom <= 0:
            return None, {**metrics, "reason": "invalid_cost_of_equity_minus_g", "roe": roe, "r": cost_of_equity, "g": g}

        justified_pb = (roe - g) / denom
        pb_cap = float(os.getenv("FAIR_VALUE_FINANCIALS_PB_CAP", "2.2") or 2.2)
        pb_floor = float(os.getenv("FAIR_VALUE_FINANCIALS_PB_FLOOR", "0.7") or 0.7)
        justified_pb_capped = max(pb_floor, min(pb_cap, float(justified_pb)))

        fair_price = float(bvps) * float(justified_pb_capped)
        metrics.update(
            {
                "book_value_per_share": float(bvps),
                "roe_pct": float(roe_pct),
                "roe": float(roe),
                "r": float(cost_of_equity),
                "g": float(g),
                "justified_pb_raw": float(justified_pb),
                "justified_pb": float(justified_pb_capped),
                "pb_cap": float(pb_cap),
                "pb_floor": float(pb_floor),
                "fair_price": float(fair_price),
            }
        )
        return float(fair_price) if fair_price > 0 else None, metrics

    def _apply_max_influence_cap(self, weights: Dict[str, float], max_weight: float = 0.7) -> Dict[str, float]:
        if not weights:
            return weights

        capped = {k: float(v) for k, v in weights.items()}
        total = sum(capped.values())
        if total <= 0:
            return capped
        capped = {k: v / total for k, v in capped.items()}

        if len(capped) <= 1:
            return capped

        # Cap any overweight method and redistribute proportionally among others.
        over = {k: v for k, v in capped.items() if v > max_weight}
        if not over:
            return capped

        for k in over:
            excess = capped[k] - max_weight
            capped[k] = max_weight
            others = [x for x in capped.keys() if x != k]
            other_total = sum(capped[x] for x in others)
            if other_total <= 0:
                continue
            for x in others:
                capped[x] += excess * (capped[x] / other_total)

        # Renormalize after redistribution
        total2 = sum(capped.values())
        if total2 <= 0:
            return capped
        return {k: v / total2 for k, v in capped.items()}

    def _blend_fair_values(
        self,
        regime: str,
        method_results: List[Dict[str, Any]],
        *,
        weight_multipliers: Optional[Dict[str, float]] = None,
    ) -> Tuple[float, Dict[str, float]]:
        ok_methods = [
            m for m in method_results
            if m.get("enabled") is True and m.get("status") == "ok" and m.get("fair_price")
        ]
        if not ok_methods:
            return 0.0, {}

        defaults = self._get_regime_default_weights(regime)
        weights = {m["method_key"]: float(defaults.get(m["method_key"], 0.0)) for m in ok_methods}
        # If regime defaults don't include a method (future additions), give small equal weight.
        if sum(weights.values()) <= 0:
            weights = {m["method_key"]: 1.0 for m in ok_methods}

        # Reliability adjustment: not all methods are equally stable.
        weights = {k: float(v) * float(self.method_reliability.get(k, 1.0)) for k, v in weights.items()}

        # Policy overlay multipliers (quality/speculative gating, etc.)
        if weight_multipliers:
            for k in list(weights.keys()):
                weights[k] = float(weights[k]) * float(weight_multipliers.get(k, 1.0))

        # Growth factor normalization: many methods are growth-driven; normalize so growth isn't
        # implicitly counted multiple times in the blend.
        growth_methods = {
            "dcf_simple",
            "pe_forward",
            "peg_legacy",
            "peg_rule_of_40_forward_cagr",
            "ev_sales",
        }
        enabled_growth = [k for k in weights.keys() if k in growth_methods and float(weights.get(k, 0.0)) > 0]
        if len(enabled_growth) > 1:
            growth_factor = 1.0 / float(len(enabled_growth))
            for k in enabled_growth:
                weights[k] = float(weights[k]) * float(growth_factor)

        weights = self._apply_max_influence_cap(weights, max_weight=0.7)

        # Outlier-robust downweighting: prevent one extreme method from skewing blend.
        fair_prices = [float(m["fair_price"]) for m in ok_methods if m.get("fair_price")]
        fair_prices.sort()
        median = None
        if fair_prices:
            mid = len(fair_prices) // 2
            median = fair_prices[mid] if (len(fair_prices) % 2 == 1) else (fair_prices[mid - 1] + fair_prices[mid]) / 2.0
        if median and median > 0:
            for m in ok_methods:
                mk = m.get("method_key")
                fp = float(m.get("fair_price") or 0.0)
                if not mk or fp <= 0:
                    continue
                if fp > 2.0 * median:
                    weights[mk] = float(weights.get(mk, 0.0)) * 0.2
                elif fp < 0.5 * median:
                    weights[mk] = float(weights.get(mk, 0.0)) * 0.7

        total = sum(weights.values())
        if total <= 0:
            return 0.0, {}
        weights = {k: v / total for k, v in weights.items()}

        fair_value = 0.0
        for m in ok_methods:
            fair_value += float(m["fair_price"]) * float(weights.get(m["method_key"], 0.0))

        return float(fair_value), weights

    def _compute_dispersion_ratio(self, method_results: List[Dict[str, Any]]) -> Tuple[Optional[float], bool]:
        fair_values = [float(m["fair_price"]) for m in method_results if m.get("status") == "ok" and m.get("fair_price")]
        if len(fair_values) < 2:
            return None, False
        min_v = min(fair_values)
        max_v = max(fair_values)
        if min_v <= 0:
            return None, False
        ratio = max_v / min_v
        return float(ratio), bool(ratio > 5.0)

    def _compute_confidence_score(self, method_results: List[Dict[str, Any]], *, dispersion_ratio: Optional[float]) -> Tuple[float, Dict[str, Any]]:
        enabled = [m for m in method_results if m.get("enabled") is True]
        ok = [m for m in enabled if m.get("status") == "ok"]
        invalid = [m for m in enabled if m.get("status") == "invalid_assumption"]

        enabled_count = len(enabled)
        ok_count = len(ok)
        invalid_count = len(invalid)

        coverage = (ok_count / enabled_count) if enabled_count > 0 else 0.0
        invalid_ratio = (invalid_count / enabled_count) if enabled_count > 0 else 0.0

        dispersion_penalty = 0.0
        if dispersion_ratio is not None and dispersion_ratio > 1.0:
            # Use a gentler, graded penalty so moderate dispersion doesn't immediately
            # collapse confidence to the floor.
            # ratio=10 => penalty ~1.0, ratio=3.16 => penalty ~0.5
            dispersion_penalty = min(1.0, float(math.log(dispersion_ratio) / math.log(10.0)))

        # If nothing is usable, force floor confidence.
        if enabled_count == 0 or ok_count == 0:
            confidence = 5.0
        else:
            confidence = 100.0 * float(coverage) * (1.0 - float(invalid_ratio)) * (1.0 - float(dispersion_penalty))
            confidence = max(confidence, 5.0)

        return float(confidence), {
            "methods_enabled_count": enabled_count,
            "methods_ok_count": ok_count,
            "methods_invalid_count": invalid_count,
            "coverage": coverage,
            "invalid_ratio": invalid_ratio,
            "dispersion_penalty": dispersion_penalty,
        }
    
    def _load_quality_thresholds(self) -> Dict[str, Dict[str, float]]:
        """Load quality assessment thresholds"""
        return {
            'eps_growth': {
                'excellent': 20.0,
                'good': 10.0,
                'average': 5.0,
                'poor': 0.0
            },
            'gross_margin': {
                'excellent': 60.0,
                'good': 40.0,
                'average': 20.0,
                'poor': 10.0
            },
            'roic': {
                'excellent': 15.0,
                'good': 10.0,
                'average': 5.0,
                'poor': 0.0
            },
            'debt_to_equity': {
                'excellent': 0.3,
                'good': 0.6,
                'average': 1.0,
                'poor': 2.0
            }
        }
    
    def calculate_fair_value(self, symbol: str) -> FairValueResult:
        """Calculate comprehensive fair value analysis"""
        
        try:
            # Get fundamental data
            fundamentals = self._get_fundamentals(symbol)
            
            if not fundamentals:
                logger.warning(f"No fundamental data available for {symbol}")
                return self._create_empty_result(symbol)

            regime = self._detect_regime(fundamentals)

            # Growth proxy: used for regime inference and multiple-based methods.
            try:
                growth_proxy_pct = float(self._get_growth_proxy_pct(fundamentals) or 0.0)
            except Exception:
                growth_proxy_pct = 0.0
            try:
                growth_proxy_pct_capped = float(self._cap_growth_proxy_pct(growth_proxy_pct, regime) or 0.0)
            except Exception:
                growth_proxy_pct_capped = float(max(0.0, growth_proxy_pct))
            try:
                (fundamentals.data_quality or {}).update(
                    {
                        "regime": str(regime),
                        "growth_proxy_pct": float(growth_proxy_pct),
                        "growth_proxy_pct_capped": float(growth_proxy_pct_capped),
                    }
                )
            except Exception:
                pass

            quality_score = self._assess_quality(fundamentals)

            # Continuous risk overlay (0..1) to avoid binary cliff effects.
            risk_score = 0.0
            rev = 0.0
            fcf = 0.0
            nm = 0.0
            fcf_trusted = False
            try:
                rev = float(fundamentals.revenue or 0.0)
                fcf = float(fundamentals.free_cash_flow or 0.0)
                nm = float(fundamentals.net_margin or 0.0)
            except Exception:
                pass

            try:
                dq = fundamentals.data_quality or {}
                flags = set(dq.get("flags") or [])
                fcf_source = dq.get("free_cash_flow_source")
                trusted_sources = {
                    "financial_statements.cash_flow.freeCashFlow",
                    "fmp_key_metrics_ttm.freeCashFlow*",
                    "inferred_operatingCashFlow_minus_abs_capex",
                }
                if fcf_source in trusted_sources and "fcf_suspicious_negative" not in flags:
                    fcf_trusted = True
            except Exception:
                fcf_trusted = False

            try:
                if rev > 0 and rev < 100_000_000:
                    risk_score = max(risk_score, 0.8)
                if fcf <= 0 and fcf_trusted:
                    risk_score = max(risk_score, 0.6)
                if nm < 0:
                    risk_score = max(risk_score, 0.6)
                if quality_score < 45.0:
                    risk_score = max(risk_score, 0.7)
                elif quality_score < 60.0:
                    risk_score = max(risk_score, 0.4)
            except Exception:
                pass

            # Soft regime blending factor to reduce cliff effects near thresholds.
            try:
                growth_proxy = float(growth_proxy_pct_capped)
            except Exception:
                growth_proxy = 0.0
            # ~0 when growth <<10, ~1 when growth >>10
            growth_compounder_score = self._sigmoid((float(growth_proxy) - 10.0) / 2.0)
            mature_value_score = 1.0 - float(growth_compounder_score)
            regime_mix = {
                "growth_compounder": float(growth_compounder_score),
                "mature_value": float(mature_value_score),
            }

            overlay_multipliers: Dict[str, float] = {}
            # PEG should fade out as we move toward mature-value or higher risk.
            peg_base = 0.2 + 0.8 * float(growth_compounder_score)

            # Risk budget normalization: prevent risk from being applied multiple times
            # (weights + model haircuts) from over-dampening fair value.
            risk_budget_cap = 0.45
            risk_budget_min_multiplier = 1.0 - float(risk_budget_cap)

            peg_mult = max(risk_budget_min_multiplier, float(peg_base) * (1.0 - 0.85 * float(risk_score)))
            overlay_multipliers["peg_legacy"] = peg_mult
            overlay_multipliers["peg_rule_of_40_forward_cagr"] = peg_mult

            # Forward PE is moderately penalized under risk.
            overlay_multipliers["pe_forward"] = max(risk_budget_min_multiplier, 1.0 - 0.40 * float(risk_score))

            # DCF/EV-sales slightly penalized under risk (but not disabled).
            overlay_multipliers["dcf_simple"] = max(risk_budget_min_multiplier, 1.0 - 0.25 * float(risk_score))
            overlay_multipliers["ev_sales"] = max(risk_budget_min_multiplier, 1.0 - 0.20 * float(risk_score))

            try:
                (fundamentals.data_quality or {}).update({
                    "risk_score": float(risk_score),
                    "free_cash_flow_trusted": bool(fcf_trusted),
                    "risk_budget_cap": float(risk_budget_cap),
                    "risk_budget_min_multiplier": float(risk_budget_min_multiplier),
                    "pe_forward_weight_multiplier": float(overlay_multipliers.get("pe_forward", 1.0)),
                })
            except Exception:
                pass

            method_results: List[Dict[str, Any]] = []
            extra_valuation_metrics: Dict[str, Any] = {}

            peg_rule_of_40_value: Optional[float] = None
            peg_rule_of_40_metrics: Dict[str, Any] = {}
            if ENABLE_PEG_RULE_OF_40_FORWARD_CAGR:
                try:
                    peg_value_candidate, peg_metrics = self._calculate_peg_rule_of_40_forward_cagr_value(symbol, fundamentals)
                    if peg_metrics:
                        peg_rule_of_40_metrics = peg_metrics
                        extra_valuation_metrics["peg_rule_of_40_forward_cagr"] = peg_metrics
                    if peg_metrics and peg_metrics.get("enabled") is True and peg_value_candidate is not None:
                        peg_rule_of_40_value = float(peg_value_candidate)
                except Exception as e:
                    logger.warning(f"Rule-of-40 forward CAGR PEG valuation failed for {symbol}: {e}")

            if regime == _REGIME_UNPROFITABLE_GROWTH:
                ev_sales_value, ev_sales_metrics = self._calculate_ev_sales_value(fundamentals)
                method_results.append(self._build_method_result(
                    method_key="ev_sales",
                    enabled=True,
                    fair_price=ev_sales_value,
                    status_if_missing="missing_data",
                    metrics=ev_sales_metrics,
                ))

                dcf_value, dcf_metrics = self._calculate_dcf_value_with_metrics(fundamentals)
                method_results.append(self._build_method_result(
                    method_key="dcf_simple",
                    enabled=True,
                    fair_price=dcf_value,
                    status_if_missing="invalid_assumption" if fundamentals.free_cash_flow <= 0 else "missing_data",
                    reason_code_if_missing="FCF_NONPOSITIVE" if fundamentals.free_cash_flow <= 0 else "DATA_NOT_AVAILABLE",
                    reason_details_if_missing={"free_cash_flow": fundamentals.free_cash_flow},
                    metrics=dcf_metrics,
                ))

                method_results.append(self._build_disabled_or_invalid_method(
                    method_key="pe_forward",
                    enabled=False,
                    status="invalid_assumption",
                    reason_code="EPS_NONPOSITIVE",
                    reason_details={"eps_ttm": fundamentals.eps_ttm, "eps_forward": fundamentals.eps_forward},
                ))
                method_results.append(self._build_disabled_or_invalid_method(
                    method_key="peg_legacy",
                    enabled=False,
                    status="invalid_assumption",
                    reason_code="EPS_OR_GROWTH_INVALID",
                    reason_details={"eps_ttm": fundamentals.eps_ttm, "eps_yoy_growth": fundamentals.eps_yoy_growth},
                ))
                method_results.append(self._build_disabled_or_invalid_method(
                    method_key="peg_rule_of_40_forward_cagr",
                    enabled=False,
                    status="invalid_assumption",
                    reason_code="EPS_OR_GROWTH_INVALID",
                    reason_details={"eps_ttm": fundamentals.eps_ttm, "eps_yoy_growth": fundamentals.eps_yoy_growth},
                ))

                extra_valuation_metrics["rule_of_40"] = {
                    "value": self._calculate_rule_of_40(fundamentals.revenue_yoy_growth, fundamentals.net_margin),
                    "inputs": {"revenue_growth_pct": fundamentals.revenue_yoy_growth, "net_margin_pct": fundamentals.net_margin},
                }

            elif regime == _REGIME_GROWTH_COMPOUNDER:
                peg_legacy_value = self._calculate_peg_value(fundamentals)
                peg_selected = "peg_rule_of_40_forward_cagr" if peg_rule_of_40_value is not None else "peg_legacy"
                pe_value = self._calculate_pe_value(fundamentals)
                dcf_value, dcf_metrics = self._calculate_dcf_value_with_metrics(fundamentals)

                if dcf_metrics:
                    extra_valuation_metrics["dcf_simple"] = dcf_metrics

                method_results.append(self._build_method_result(
                    method_key="peg_legacy",
                    enabled=peg_selected == "peg_legacy",
                    fair_price=peg_legacy_value,
                    status_if_missing="invalid_assumption" if fundamentals.eps_ttm <= 0 or fundamentals.eps_yoy_growth <= 0 else "missing_data",
                    reason_code_if_missing="EPS_OR_GROWTH_INVALID" if fundamentals.eps_ttm <= 0 or fundamentals.eps_yoy_growth <= 0 else "DATA_NOT_AVAILABLE",
                    reason_details_if_missing={"eps_ttm": fundamentals.eps_ttm, "eps_yoy_growth": fundamentals.eps_yoy_growth},
                    metrics={"selected_variant": peg_selected},
                ))
                method_results.append(self._build_method_result(
                    method_key="peg_rule_of_40_forward_cagr",
                    enabled=peg_selected == "peg_rule_of_40_forward_cagr",
                    fair_price=peg_rule_of_40_value,
                    status_if_missing="missing_data" if not peg_rule_of_40_metrics else "missing_data",
                    reason_code_if_missing="DATA_NOT_AVAILABLE",
                    reason_details_if_missing={"enabled_flag": bool(peg_rule_of_40_metrics.get("enabled"))},
                    metrics={"rule_of_40": peg_rule_of_40_metrics, "selected_variant": peg_selected},
                ))
                method_results.append(self._build_method_result(
                    method_key="pe_forward",
                    enabled=True,
                    fair_price=pe_value,
                    status_if_missing="invalid_assumption" if fundamentals.eps_forward <= 0 else "missing_data",
                    reason_code_if_missing="EPS_FORWARD_NONPOSITIVE" if fundamentals.eps_forward <= 0 else "DATA_NOT_AVAILABLE",
                    reason_details_if_missing={"eps_forward": fundamentals.eps_forward},
                ))
                method_results.append(self._build_method_result(
                    method_key="dcf_simple",
                    enabled=True,
                    fair_price=dcf_value,
                    status_if_missing="invalid_assumption" if fundamentals.free_cash_flow <= 0 else "missing_data",
                    reason_code_if_missing="FCF_NONPOSITIVE" if fundamentals.free_cash_flow <= 0 else "DATA_NOT_AVAILABLE",
                    reason_details_if_missing={"free_cash_flow": fundamentals.free_cash_flow},
                    metrics=dcf_metrics,
                ))

            elif regime == _REGIME_MATURE_VALUE:
                pe_value = self._calculate_pe_value(fundamentals)
                dcf_value, dcf_metrics = self._calculate_dcf_value_with_metrics(fundamentals)

                if dcf_metrics:
                    extra_valuation_metrics["dcf_simple"] = dcf_metrics

                adjusted_pe_value = None
                adjusted_pe_metrics: Dict[str, Any] = {}
                try:
                    if dcf_value is None:
                        adjusted_pe_value, adjusted_pe_metrics = self._calculate_adjusted_pe_value(fundamentals)
                except Exception:
                    adjusted_pe_value = None
                    adjusted_pe_metrics = {}

                pb_bank_value = None
                pb_bank_metrics: Dict[str, Any] = {}
                try:
                    pb_bank_value, pb_bank_metrics = self._calculate_pb_bank_value(fundamentals)
                except Exception:
                    pb_bank_value = None
                    pb_bank_metrics = {}

                method_results.append(self._build_method_result(
                    method_key="pe_forward",
                    enabled=True,
                    fair_price=pe_value,
                    status_if_missing="invalid_assumption" if fundamentals.eps_forward <= 0 else "missing_data",
                    reason_code_if_missing="EPS_FORWARD_NONPOSITIVE" if fundamentals.eps_forward <= 0 else "DATA_NOT_AVAILABLE",
                    reason_details_if_missing={"eps_forward": fundamentals.eps_forward},
                ))
                method_results.append(self._build_method_result(
                    method_key="dcf_simple",
                    enabled=True,
                    fair_price=dcf_value,
                    status_if_missing="invalid_assumption" if fundamentals.free_cash_flow <= 0 else "missing_data",
                    reason_code_if_missing="FCF_NONPOSITIVE" if fundamentals.free_cash_flow <= 0 else "DATA_NOT_AVAILABLE",
                    reason_details_if_missing={"free_cash_flow": fundamentals.free_cash_flow},
                    metrics=dcf_metrics,
                ))
                method_results.append(self._build_method_result(
                    method_key="adjusted_pe",
                    enabled=True,
                    fair_price=adjusted_pe_value,
                    status_if_missing="missing_data",
                    metrics=adjusted_pe_metrics,
                ))
                method_results.append(self._build_method_result(
                    method_key="pb_bank",
                    enabled=True,
                    fair_price=pb_bank_value,
                    status_if_missing="missing_data",
                    metrics=pb_bank_metrics,
                ))
                method_results.append(self._build_disabled_or_invalid_method(
                    method_key="peg_legacy",
                    enabled=False,
                    status="disabled_by_regime",
                    reason_code="DISABLED_FOR_MATURE_VALUE",
                    reason_details={"growth": fundamentals.eps_yoy_growth},
                ))
                method_results.append(self._build_disabled_or_invalid_method(
                    method_key="peg_rule_of_40_forward_cagr",
                    enabled=False,
                    status="disabled_by_regime",
                    reason_code="DISABLED_FOR_MATURE_VALUE",
                    reason_details={"growth": fundamentals.eps_yoy_growth},
                ))

            else:
                try:
                    normalized_eps, normalized_eps_metrics = self._estimate_normalized_eps(symbol, fundamentals)
                    if normalized_eps is not None and float(normalized_eps) > 0:
                        (fundamentals.data_quality or {}).update({
                            "normalized_eps": float(normalized_eps),
                            "normalized_eps_metrics": normalized_eps_metrics,
                        })
                except Exception:
                    pass

                adjusted_pe_value, adjusted_pe_metrics = self._calculate_adjusted_pe_value(fundamentals)
                method_results.append(self._build_method_result(
                    method_key="adjusted_pe",
                    enabled=True,
                    fair_price=adjusted_pe_value,
                    status_if_missing="invalid_assumption" if fundamentals.eps_forward <= 0 else "missing_data",
                    reason_code_if_missing="EPS_FORWARD_NONPOSITIVE" if fundamentals.eps_forward <= 0 else "DATA_NOT_AVAILABLE",
                    reason_details_if_missing={"eps_forward": fundamentals.eps_forward},
                    metrics=adjusted_pe_metrics,
                ))
                method_results.append(self._build_disabled_or_invalid_method(
                    method_key="dcf_simple",
                    enabled=False,
                    status="disabled_by_regime",
                    reason_code="DISABLED_FOR_CYCLICAL",
                ))
                method_results.append(self._build_disabled_or_invalid_method(
                    method_key="peg_legacy",
                    enabled=False,
                    status="disabled_by_regime",
                    reason_code="DISABLED_FOR_CYCLICAL",
                ))
                method_results.append(self._build_disabled_or_invalid_method(
                    method_key="peg_rule_of_40_forward_cagr",
                    enabled=False,
                    status="disabled_by_regime",
                    reason_code="DISABLED_FOR_CYCLICAL",
                ))

            weighted_fair_value, method_weights = self._blend_fair_values(
                regime,
                method_results,
                weight_multipliers=overlay_multipliers,
            )
            dispersion_ratio, high_dispersion = self._compute_dispersion_ratio(method_results)
            confidence_score, confidence_breakdown = self._compute_confidence_score(
                method_results,
                dispersion_ratio=dispersion_ratio,
            )

            data_quality_penalty = 0.0
            if fundamentals.data_quality:
                data_quality_penalty = float(fundamentals.data_quality.get("confidence_penalty", 0.0) or 0.0)

            method_penalty = 0.0
            for m in method_results:
                if m.get("enabled") is True and m.get("status") == "ok":
                    try:
                        method_penalty += float((m.get("metrics") or {}).get("confidence_penalty", 0.0) or 0.0)
                    except Exception:
                        pass

            combined_penalty = float(data_quality_penalty) + float(method_penalty)
            if combined_penalty > 0:
                confidence_score = max(5.0, float(confidence_score) * (1.0 - min(0.8, combined_penalty)))

            valuation_metrics = self._calculate_valuation_metrics(weighted_fair_value, fundamentals)
            if extra_valuation_metrics:
                valuation_metrics.update(extra_valuation_metrics)

            valuation_metrics.update({
                "regime": regime,
                "confidence_score": confidence_score,
                "dispersion_ratio": dispersion_ratio,
                "high_dispersion": high_dispersion,
                "methods_enabled_count": confidence_breakdown.get("methods_enabled_count"),
                "methods_ok_count": confidence_breakdown.get("methods_ok_count"),
                "methods_invalid_count": confidence_breakdown.get("methods_invalid_count"),
                "confidence_breakdown": confidence_breakdown,
                "method_weights": method_weights,
                "max_weight_per_method": 0.7,
                "data_quality": fundamentals.data_quality,
                "confidence_penalties": {
                    "fundamentals": data_quality_penalty,
                    "methods": method_penalty,
                    "combined": combined_penalty,
                },
                "risk_score": risk_score,
                "risk_budget": {
                    "cap": float(risk_budget_cap),
                    "min_multiplier": float(risk_budget_min_multiplier),
                },
                "risk_effective": {
                    "pe_forward_weight_multiplier": float(overlay_multipliers.get("pe_forward", 1.0)),
                    "peg_weight_multiplier": float(overlay_multipliers.get("peg_legacy", 1.0)),
                    "dcf_weight_multiplier": float(overlay_multipliers.get("dcf_simple", 1.0)),
                    "ev_sales_weight_multiplier": float(overlay_multipliers.get("ev_sales", 1.0)),
                    "pe_forward_eps_multiplier": float((fundamentals.data_quality or {}).get("pe_forward_eps_multiplier") or 1.0),
                    "pe_forward_combined_multiplier": float((fundamentals.data_quality or {}).get("pe_forward_combined_multiplier") or 1.0),
                },
                "regime_mix": regime_mix,
                "blend_overlay_multipliers": overlay_multipliers,
            })
            
            # Quality assessment
            
            updated_at = datetime.now()
            run_id = self._persist_fair_value_run(
                symbol=symbol,
                fundamentals=fundamentals,
                weighted_fair_value=weighted_fair_value,
                valuation_metrics=valuation_metrics,
                quality_score=quality_score,
                individual_valuations={m["method_key"]: m.get("fair_price") for m in method_results},
                method_results=method_results,
                updated_at=updated_at
            )

            return FairValueResult(
                run_id=run_id,
                symbol=symbol,
                current_price=fundamentals.current_price,
                fair_value=weighted_fair_value,
                valuation_metrics=valuation_metrics,
                quality_score=quality_score,
                individual_valuations={m["method_key"]: m.get("fair_price") for m in method_results},
                fundamentals={
                    'eps_ttm': fundamentals.eps_ttm,
                    'eps_forward': fundamentals.eps_forward,
                    'eps_yoy_growth': fundamentals.eps_yoy_growth,
                    'revenue_yoy_growth': fundamentals.revenue_yoy_growth,
                    'gross_margin': fundamentals.gross_margin,
                    'operating_margin': fundamentals.operating_margin,
                    'net_margin': fundamentals.net_margin,
                    'roic': fundamentals.roic,
                    'debt_to_equity': fundamentals.debt_to_equity,
                    'current_pe': fundamentals.current_pe,
                    'forward_pe': fundamentals.forward_pe,
                    'peg_ratio': fundamentals.peg_ratio,
                    'industry': fundamentals.industry,
                    'market_cap': fundamentals.market_cap,
                    'free_cash_flow': fundamentals.free_cash_flow,
                    'data_quality': fundamentals.data_quality or {},
                },
                updated_at=updated_at
            )
            
        except Exception as e:
            logger.error(f"Error calculating fair value for {symbol}: {e}")
            return self._create_empty_result(symbol)
    
    def _get_fundamentals(self, symbol: str) -> Optional[FundamentalData]:
        """Get fundamental data for a symbol using enhanced FMP data"""
        
        try:
            with db.get_session() as session:
                # Get latest price
                price_query = """
                SELECT date, close
                FROM raw_market_data_daily
                WHERE symbol = :symbol
                ORDER BY date DESC
                LIMIT 1
                """
                result = session.execute(text(price_query), {"symbol": symbol})
                price_row = result.fetchone()

                db_price_date = price_row[0] if price_row else None
                current_price = price_row[1] if price_row else None
                price_source = "raw_market_data_daily.close" if current_price is not None else None
                price_recency_days = None
                price_quote_timestamp = None
                price_quote_date = None
                try:
                    if db_price_date is not None:
                        price_recency_days = int((datetime.utcnow().date() - db_price_date).days)
                except Exception:
                    price_recency_days = None

                price_fallback_to_fmp = False
                try:
                    stale_threshold_days = 3
                    if ENABLE_FAIR_VALUE_LIVE_PRICE_FALLBACK and (
                        current_price is None
                        or (price_recency_days is not None and int(price_recency_days) > int(stale_threshold_days))
                    ):
                        from app.providers.financial_modeling_prep.client import EnhancedFMPClient
                        client = EnhancedFMPClient.from_settings()
                        quote = client.get_real_time_quote(symbol) or {}
                        quote_price = self._safe_float((quote or {}).get("price"))
                        try:
                            price_quote_timestamp = (quote or {}).get("timestamp")
                        except Exception:
                            price_quote_timestamp = None
                        try:
                            if price_quote_timestamp is not None:
                                price_quote_date = datetime.utcfromtimestamp(float(price_quote_timestamp)).date()
                        except Exception:
                            price_quote_date = None
                        if quote_price is not None and float(quote_price) > 0:
                            current_price = float(quote_price)
                            price_source = "fmp_quote.price"
                            price_fallback_to_fmp = True
                            try:
                                price_recency_days = 0
                            except Exception:
                                pass
                except Exception:
                    pass
                
                # Get key metrics TTM data (enhanced FMP data)
                key_metrics_query = """
                SELECT payload->'key_metrics_ttm' as metrics, generated_at
                FROM stock_insights_snapshots
                WHERE stock_symbol = :symbol
                  AND source = 'fmp_key_metrics_ttm'
                ORDER BY generated_at DESC
                LIMIT 1
                """
                result = session.execute(text(key_metrics_query), {"symbol": symbol})
                key_metrics_row = result.fetchone()

                key_metrics = {}
                key_metrics_generated_at = None
                if key_metrics_row and key_metrics_row[0]:
                    key_metrics = key_metrics_row[0]
                    key_metrics_generated_at = key_metrics_row[1]

                shares_outstanding_value = 0.0
                shares_outstanding_source = None
                shares_outstanding_haircut = 1.0
                if (key_metrics or {}).get('sharesOutstanding') is not None:
                    shares_outstanding_value = self._safe_float((key_metrics or {}).get('sharesOutstanding'))
                    shares_outstanding_source = "fmp_key_metrics_ttm.sharesOutstanding"
                elif (key_metrics or {}).get('weightedAverageShsOutDilTTM') is not None:
                    shares_outstanding_value = self._safe_float((key_metrics or {}).get('weightedAverageShsOutDilTTM'))
                    shares_outstanding_source = "fmp_key_metrics_ttm.weightedAverageShsOutDilTTM"
                    shares_outstanding_haircut = 0.95
                elif (key_metrics or {}).get('weightedAverageShsOut') is not None:
                    shares_outstanding_value = self._safe_float((key_metrics or {}).get('weightedAverageShsOut'))
                    shares_outstanding_source = "fmp_key_metrics_ttm.weightedAverageShsOut"
                    shares_outstanding_haircut = 0.95
                
                # Get financial growth data from multiple sources.
                # Preference order matters for reproducibility and correctness:
                # 1) fmp_income_statement_growth (has growthEPS/growthEPSDiluted)
                # 2) fmp_financial_growth (has epsgrowth)
                # 3) fmp_cash_flow_growth (fallback; usually lacks EPS)
                growth_data: Dict[str, Any] = {}
                growth_generated_at = None
                growth_source_used = None

                def _normalize_growth_payload(src: str, payload_obj: Any) -> Dict[str, Any]:
                    obj = payload_obj
                    try:
                        if isinstance(obj, list) and obj and isinstance(obj[0], dict):
                            obj = obj[0]
                    except Exception:
                        pass
                    if not isinstance(obj, dict):
                        return {}
                    if src == 'fmp_income_statement_growth':
                        obj = obj.get('income_statement_growth', obj)
                    elif src == 'fmp_cash_flow_growth':
                        obj = obj.get('cash_flow_growth', obj)
                    elif src == 'fmp_financial_growth':
                        # Stored as {"financial_growth": {...}} or {"financial_growth": [{...}]}
                        if 'financial_growth' in obj:
                            inner = obj.get('financial_growth')
                            if isinstance(inner, list) and inner and isinstance(inner[0], dict):
                                obj = inner[0]
                            elif isinstance(inner, dict):
                                obj = inner
                    return obj if isinstance(obj, dict) else {}

                def _ensure_epsgrowth(d: Dict[str, Any]) -> Dict[str, Any]:
                    if not isinstance(d, dict):
                        return {}
                    if 'growthNetIncome' in d and d.get('epsgrowth') in (None, 0, 0.0, '0', '0.0'):
                        d['epsgrowth'] = d.get('growthNetIncome')
                    try:
                        if 'epsgrowth' not in d or d.get('epsgrowth') in (None, 0, 0.0, '0', '0.0'):
                            for k in (
                                'growthEPSDiluted',
                                'growthEPS',
                                'growthEpsDiluted',
                                'growthEps',
                                'epsgrowth',
                                'epsGrowth',
                                'epsGrowthTTM',
                                'epsGrowthRate',
                            ):
                                if k in d and d.get(k) not in (None, 0, 0.0, '0', '0.0'):
                                    d['epsgrowth'] = d.get(k)
                                    break
                    except Exception:
                        pass
                    return d

                growth_sources = (
                    'fmp_income_statement_growth',
                    'fmp_financial_growth',
                    'fmp_cash_flow_growth',
                )
                for src in growth_sources:
                    row = session.execute(
                        text(
                            """
                            SELECT payload, generated_at
                            FROM stock_insights_snapshots
                            WHERE stock_symbol = :symbol AND source = :source
                            ORDER BY generated_at DESC
                            LIMIT 1
                            """
                        ),
                        {"symbol": symbol, "source": src},
                    ).fetchone()
                    if not row or not row[0]:
                        continue
                    candidate = _normalize_growth_payload(src, row[0])
                    candidate = _ensure_epsgrowth(candidate)
                    if candidate:
                        growth_data = candidate
                        growth_generated_at = row[1]
                        growth_source_used = src
                        # If we found an EPS growth key, stop early.
                        if candidate.get('epsgrowth') not in (None, 0, 0.0, '0', '0.0'):
                            break
                
                # Get financial ratios data for margins and debt metrics
                ratios_query = """
                SELECT roe, roa, roic, debt_to_equity, gross_profit_margin, operating_margin, net_profit_margin, data_source
                FROM financial_ratios
                WHERE symbol = :symbol
                ORDER BY fiscal_date_ending DESC
                LIMIT 1
                """
                result = session.execute(text(ratios_query), {"symbol": symbol})
                ratios_row = result.fetchone()
                
                # Get basic fundamentals data as fallback
                fundamentals_query = """
                SELECT payload
                FROM fundamentals_snapshots
                WHERE UPPER(symbol) = UPPER(:symbol)
                ORDER BY as_of_date DESC
                LIMIT 1
                """
                result = session.execute(text(fundamentals_query), {"symbol": symbol})
                fundamentals_row = result.fetchone()

                fmp_fundamentals_query = """
                SELECT payload
                FROM stock_insights_snapshots
                WHERE stock_symbol = :symbol
                  AND source = 'fmp_fundamentals'
                ORDER BY generated_at DESC
                LIMIT 1
                """
                result = session.execute(text(fmp_fundamentals_query), {"symbol": symbol})
                fmp_fundamentals_row = result.fetchone()
                
                # Get balance sheet data for ROIC calculation
                balance_sheet_query = """
                SELECT payload->>'totalAssets' as total_assets,
                       payload->>'totalStockholdersEquity' as total_stockholders_equity,
                       payload->>'totalDebt' as total_debt,
                       payload->>'cashAndCashEquivalents' as cash_and_equivalents,
                       payload->>'cashAndShortTermInvestments' as cash_and_short_term_investments
                FROM financial_statements
                WHERE stock_symbol = :symbol 
                  AND statement_type = 'balance_sheet'
                ORDER BY fiscal_period DESC
                LIMIT 1
                """
                result = session.execute(text(balance_sheet_query), {"symbol": symbol})
                balance_sheet = result.fetchone()
                
                income_statement_query = """
                SELECT payload->>'revenue' as revenue,
                       payload->>'grossProfit' as gross_profit,
                       payload->>'operatingIncome' as operating_income,
                       payload->>'netIncome' as net_income,
                       payload->>'depreciationAndAmortization' as depreciation_amortization,
                       payload->>'weightedAverageShsOutDiluted' as weighted_average_shs_out_diluted,
                       payload->>'weightedAverageShsOut' as weighted_average_shs_out,
                       payload->>'weightedAverageShsOutDil' as weighted_average_shs_out_dil
                FROM financial_statements
                WHERE stock_symbol = :symbol
                  AND statement_type = 'income_statement'
                ORDER BY fiscal_period DESC
                LIMIT 1
                """
                result = session.execute(text(income_statement_query), {"symbol": symbol})
                income_statement_row = result.fetchone()
                
                # Get cash flow statement data for owner earnings calculation
                cash_flow_query = """
                SELECT fiscal_period,
                       payload->>'date' as statement_date,
                       payload->>'operatingCashFlow' as operating_cash_flow,
                       payload->>'capitalExpenditure' as capital_expenditure,
                       payload->>'freeCashFlow' as free_cash_flow
                FROM financial_statements
                WHERE stock_symbol = :symbol 
                  AND statement_type = 'cash_flow'
                ORDER BY (payload->>'date')::date DESC NULLS LAST, fiscal_period DESC
                LIMIT 1
                """
                result = session.execute(text(cash_flow_query), {"symbol": symbol})
                cash_flow_row = result.fetchone()

                cash_flow_ttm_query = """
                SELECT fiscal_period,
                       period_type,
                       payload->>'date' as statement_date,
                       payload->>'operatingCashFlow' as operating_cash_flow,
                       payload->>'capitalExpenditure' as capital_expenditure,
                       payload->>'freeCashFlow' as free_cash_flow
                FROM financial_statements
                WHERE stock_symbol = :symbol 
                  AND statement_type = 'cash_flow'
                ORDER BY (payload->>'date')::date DESC NULLS LAST, fiscal_period DESC
                LIMIT 4
                """
                result = session.execute(text(cash_flow_ttm_query), {"symbol": symbol})
                cash_flow_rows = result.fetchall()

                # Only compute a "sum of last 4" when the rows are quarterly.
                # For annual rows, summing 4 periods would incorrectly produce a ~4-year sum.
                try:
                    if cash_flow_rows:
                        period_types = [r[1] for r in cash_flow_rows if r and len(r) > 1]
                        # Keep the 4-row series only when it looks quarterly.
                        if period_types and not any((pt or '').lower() in ('quarter', 'quarterly', 'q', 'qtr') for pt in period_types):
                            cash_flow_rows = []
                except Exception:
                    pass
                
                # Extract key metrics data
                key_metrics = {}
                if key_metrics_row and key_metrics_row[0]:
                    key_metrics = key_metrics_row[0]
                
                # Extract financial ratios data
                ratios_data = {}
                if ratios_row:
                    ratios_data = {
                        'roe': ratios_row[0],
                        'roa': ratios_row[1],
                        'roic': ratios_row[2],
                        'debt_to_equity': ratios_row[3],
                        'gross_profit_margin': ratios_row[4],
                        'operating_margin': ratios_row[5],
                        'net_profit_margin': ratios_row[6],
                        'data_source': ratios_row[7]
                    }
                
                # Calculate ROIC from balance sheet and income statement if not available
                calculated_roic = 0.0
                owner_earnings = 0.0
                
                if balance_sheet and income_statement_row:
                    try:
                        total_assets = float(balance_sheet[0] or 0)
                        total_equity = float(balance_sheet[1] or 0)
                        total_debt = float(balance_sheet[2] or 0)

                        net_income_value = float(income_statement_row[3] or 0)
                        
                        # Calculate invested capital (equity + debt)
                        invested_capital = total_equity + total_debt
                        if invested_capital > 0 and net_income_value > 0:
                            calculated_roic = (net_income_value / invested_capital) * 100  # Convert to percentage
                        elif total_assets > 0 and net_income_value > 0:
                            # Fallback: use total assets (ROA approximation)
                            calculated_roic = (net_income_value / total_assets) * 100
                            
                        logger.info(f"Calculated ROIC for {symbol}: net_income={net_income_value}, invested_capital={invested_capital}, roic={calculated_roic}%")
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Error calculating ROIC for {symbol}: {e}")
                        calculated_roic = 0.0
                else:
                    calculated_roic = 0.0

                calculated_gross_margin = 0.0
                calculated_operating_margin = 0.0
                calculated_net_margin = 0.0
                if income_statement_row:
                    try:
                        is_revenue = float(income_statement_row[0] or 0.0)
                        is_gross_profit = float(income_statement_row[1] or 0.0)
                        is_operating_income = float(income_statement_row[2] or 0.0)
                        is_net_income = float(income_statement_row[3] or 0.0)
                        if is_revenue and is_revenue > 0:
                            calculated_gross_margin = (is_gross_profit / is_revenue) * 100.0
                            calculated_operating_margin = (is_operating_income / is_revenue) * 100.0
                            calculated_net_margin = (is_net_income / is_revenue) * 100.0
                    except (ValueError, TypeError):
                        calculated_gross_margin = 0.0
                        calculated_operating_margin = 0.0
                        calculated_net_margin = 0.0

                # Calculate Owner Earnings (Warren Buffett metric)
                if cash_flow_row:
                    try:
                        # Method 1: Use cash flow data if available
                        if cash_flow_row[4]:  # free_cash_flow
                            owner_earnings = float(cash_flow_row[4])
                        else:
                            # Method 2: Calculate from operating cash flow - capital expenditures
                            operating_cash_flow = float(cash_flow_row[2] or 0)
                            capital_expenditure = float(cash_flow_row[3] or 0)
                            owner_earnings = operating_cash_flow - capital_expenditure
                            
                        logger.info(f"Calculated Owner Earnings for {symbol}: {owner_earnings}")
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Error calculating Owner Earnings for {symbol}: {e}")
                        owner_earnings = 0.0

                free_cash_flow_value = None
                free_cash_flow_source = None
                try:
                    # Key-metrics payloads are often *ratio packs* (yields / EV multiples / returns).
                    # Only use absolute $ FCF fields here. Do NOT treat ratio-style fields like
                    # freeCashFlowToFirmTTM as an amount.
                    fcf_key_metrics = self._safe_float(
                        (key_metrics or {}).get('freeCashFlowTTM')
                        or (key_metrics or {}).get('freeCashFlow')
                    )

                    fcf_cash_flow_stmt = None
                    fcf_cash_flow_stmt_ttm = None
                    fcf_inferred = None
                    cash_flow_statement_date = None
                    cash_flow_statement_recency_days = None
                    if cash_flow_row:
                        try:
                            cash_flow_statement_date = self._safe_datetime(cash_flow_row[1])
                        except Exception:
                            cash_flow_statement_date = None
                        try:
                            if cash_flow_statement_date:
                                cash_flow_statement_recency_days = (datetime.now(timezone.utc) - cash_flow_statement_date).days
                        except Exception:
                            cash_flow_statement_recency_days = None

                        fcf_cash_flow_stmt = self._safe_float(cash_flow_row[4])
                        ocf = self._safe_float(cash_flow_row[2])
                        capex_raw = self._safe_float(cash_flow_row[3])

                        # Normalize capex sign: many providers store capex as negative (cash outflow).
                        # True reinvestment outflow magnitude is abs(capex).
                        capex_outflow = abs(float(capex_raw))
                        if ocf and ocf > 0:
                            fcf_inferred = float(ocf) - float(capex_outflow)

                    # Compute a simple TTM from last 4 statement rows when available.
                    # This reduces the risk of using a single quarterly cash flow point.
                    try:
                        if cash_flow_rows and len(cash_flow_rows) >= 4:
                            vals = []
                            for row in cash_flow_rows:
                                vals.append(float(self._safe_float(row[4]) or 0.0))
                            if any(v != 0.0 for v in vals):
                                fcf_cash_flow_stmt_ttm = float(sum(vals))
                    except Exception:
                        fcf_cash_flow_stmt_ttm = None

                    # Detect obviously stale statement payloads (e.g., statement_date years old).
                    # If stale, prefer key-metrics TTM numbers.
                    statement_stale = False
                    try:
                        if cash_flow_statement_recency_days is not None and int(cash_flow_statement_recency_days) > 550:
                            statement_stale = True
                    except Exception:
                        statement_stale = False
                    if statement_stale:
                        confidence_penalty += 0.10
                        data_quality_flags.append("fcf_statement_stale")

                    if cash_flow_statement_recency_days is not None:
                        data_quality_flags.append(f"cash_flow_recency_days:{int(cash_flow_statement_recency_days)}")

                    # Prefer a positive, sane FCF number.
                    if statement_stale is False and fcf_cash_flow_stmt_ttm is not None and float(fcf_cash_flow_stmt_ttm) > 0:
                        free_cash_flow_value = float(fcf_cash_flow_stmt_ttm)
                        free_cash_flow_source = "financial_statements.cash_flow.freeCashFlow_ttm_sum4"
                        data_quality_flags.append("fcf_ttm_computed")
                        confidence_penalty += 0.03
                    elif statement_stale is False and fcf_cash_flow_stmt is not None and float(fcf_cash_flow_stmt) > 0:
                        free_cash_flow_value = float(fcf_cash_flow_stmt)
                        free_cash_flow_source = "financial_statements.cash_flow.freeCashFlow"
                    elif fcf_inferred is not None and float(fcf_inferred) > 0:
                        free_cash_flow_value = float(fcf_inferred)
                        free_cash_flow_source = "inferred_operatingCashFlow_minus_abs_capex"
                        confidence_penalty += 0.05
                        data_quality_flags.append("fcf_inferred")
                    elif fcf_key_metrics and float(fcf_key_metrics) > 0:
                        free_cash_flow_value = float(fcf_key_metrics)
                        free_cash_flow_source = "fmp_key_metrics_ttm.freeCashFlow*"

                    # If we still don't have a positive value but the statement value exists,
                    # keep it (even if negative) for transparency, but flag as suspicious when
                    # profitability is strong.
                    if free_cash_flow_value is None and statement_stale is False and fcf_cash_flow_stmt is not None and float(fcf_cash_flow_stmt) != 0.0:
                        free_cash_flow_value = float(fcf_cash_flow_stmt)
                        free_cash_flow_source = "financial_statements.cash_flow.freeCashFlow"
                        if float(net_margin_value or 0.0) > 10.0 and revenue_value and float(revenue_value) > 1_000_000_000:
                            confidence_penalty += 0.10
                            data_quality_flags.append("fcf_suspicious_negative")
                except Exception:
                    free_cash_flow_value = None
                    free_cash_flow_source = None
                
                # Extract basic fundamentals as fallback
                basic_fundamentals = {}
                if fundamentals_row and fundamentals_row[0]:
                    basic_fundamentals = fundamentals_row[0] if isinstance(fundamentals_row[0], dict) else json.loads(fundamentals_row[0]) if isinstance(fundamentals_row[0], str) else fundamentals_row[0]

                if fmp_fundamentals_row and fmp_fundamentals_row[0]:
                    fmp_payload = fmp_fundamentals_row[0]
                    if isinstance(fmp_payload, str):
                        try:
                            fmp_payload = json.loads(fmp_payload)
                        except json.JSONDecodeError:
                            fmp_payload = None
                    if isinstance(fmp_payload, dict):
                        fmp_fundamentals = fmp_payload.get("fundamentals") if isinstance(fmp_payload.get("fundamentals"), dict) else None
                        if isinstance(fmp_fundamentals, dict):
                            if not isinstance(basic_fundamentals, dict):
                                basic_fundamentals = {}
                            for k, v in fmp_fundamentals.items():
                                if k not in basic_fundamentals or basic_fundamentals.get(k) in (None, "", 0, 0.0):
                                    basic_fundamentals[k] = v

                # Offline price fallback from persisted snapshots (reporting only).
                # If we don't have market data rows and live quote fallback is disabled,
                # attempt to use a stored snapshot price.
                try:
                    current_price_f = self._safe_float(current_price)
                    if current_price is None or float(current_price_f) <= 0.0:
                        if isinstance(basic_fundamentals, dict):
                            for k in (
                                "price",
                                "current_price",
                                "currentPrice",
                                "last",
                                "last_price",
                                "close",
                                "prev_close",
                            ):
                                if basic_fundamentals.get(k) is not None:
                                    snap_price = self._safe_float(basic_fundamentals.get(k))
                                    if snap_price > 0:
                                        current_price = float(snap_price)
                                        price_source = f"fundamentals_snapshots.{k}"
                                        break
                except Exception:
                    pass

                # Final offline fallback: use latest persisted fair_value_runs.current_price (reporting only).
                try:
                    current_price_f = self._safe_float(current_price)
                    if current_price is None or float(current_price_f) <= 0.0:
                        last_price_row = session.execute(
                            text(
                                """
                                SELECT current_price, as_of
                                FROM fair_value_runs
                                WHERE symbol = :symbol AND current_price IS NOT NULL AND current_price > 0
                                ORDER BY as_of DESC
                                LIMIT 1
                                """
                            ),
                            {"symbol": symbol},
                        ).fetchone()
                        if last_price_row and last_price_row[0] is not None and float(last_price_row[0]) > 0:
                            current_price = float(last_price_row[0])
                            price_source = "fair_value_runs.current_price"
                            try:
                                price_quote_date = last_price_row[1].date() if last_price_row[1] is not None else None
                            except Exception:
                                pass
                except Exception:
                    pass

                if (shares_outstanding_value in (0.0, 0) or shares_outstanding_value <= 0) and isinstance(basic_fundamentals, dict):
                    for k in ("sharesOutstanding", "shares_outstanding", "shareOutstanding"):
                        if basic_fundamentals.get(k) is not None:
                            shares_outstanding_value = self._safe_float(basic_fundamentals.get(k))
                            if shares_outstanding_value > 0:
                                shares_outstanding_source = f"fundamentals_snapshots.{k}"
                                break

                if (shares_outstanding_value in (0.0, 0) or shares_outstanding_value <= 0) and income_statement_row:
                    try:
                        for idx, k in (
                            (5, "weightedAverageShsOutDiluted"),
                            (7, "weightedAverageShsOutDil"),
                            (6, "weightedAverageShsOut"),
                        ):
                            v = self._safe_float(income_statement_row[idx])
                            if v > 0:
                                shares_outstanding_value = float(v)
                                shares_outstanding_source = f"financial_statements.income_statement.{k}"
                                shares_outstanding_haircut = 0.98
                                break
                    except Exception:
                        pass

                market_cap_hint = self._safe_float(
                    (key_metrics or {}).get('marketCap')
                    or (basic_fundamentals or {}).get('marketCap')
                    or (basic_fundamentals or {}).get('market_cap')
                )
                if (shares_outstanding_value in (0.0, 0) or shares_outstanding_value <= 0) and market_cap_hint > 0 and current_price is not None:
                    current_price_f = self._safe_float(current_price)
                    if current_price_f > 0:
                        shares_outstanding_value = market_cap_hint / current_price_f
                        shares_outstanding_source = "derived_market_cap_over_price"
                        shares_outstanding_haircut = 0.90

                # Offline price derivation: if we don't have a usable price (raw_market_data_daily missing)
                # and live quote fallback is disabled/unavailable, compute price from market cap and shares.
                try:
                    current_price_f = self._safe_float(current_price)
                    if (current_price_f is None or float(current_price_f) <= 0.0) and market_cap_hint > 0 and shares_outstanding_value > 0:
                        derived_price = float(market_cap_hint) / float(shares_outstanding_value)
                        if derived_price > 0:
                            current_price = derived_price
                            price_source = "derived_market_cap_over_shares"
                except Exception:
                    pass

                if shares_outstanding_value > 0 and shares_outstanding_haircut != 1.0:
                    shares_outstanding_value = shares_outstanding_value * float(shares_outstanding_haircut)

                # Calculate PEG ratio if not available
                current_pe = float(basic_fundamentals.get('pe_ratio', 0))
                def _normalize_growth_pct(value: float) -> float:
                    try:
                        v = float(value)
                    except (TypeError, ValueError):
                        return 0.0
                    if v == 0.0:
                        return 0.0
                    if 0.0 < abs(v) < 2.0:
                        return v * 100.0
                    return v

                eps_growth = _normalize_growth_pct(float(growth_data.get('epsgrowth', 0)) if growth_data else 0.0)
                peg_ratio = current_pe / eps_growth if current_pe > 0 and eps_growth > 0 else 0.0
                
                # Create enhanced FundamentalData object using FMP data
                revenue_yoy_growth = _normalize_growth_pct(float(growth_data.get('revenueGrowth', 0)) if growth_data else 0.0)
                eps_growth_source = growth_source_used or "unknown"
                if revenue_yoy_growth in (0.0, 0) and isinstance(basic_fundamentals, dict):
                    for k in ("revenueGrowth", "revenue_growth", "revenue_yoy_growth", "revenue_growth_pct"):
                        if basic_fundamentals.get(k) is not None:
                            try:
                                revenue_yoy_growth = _normalize_growth_pct(float(basic_fundamentals.get(k)))
                                break
                            except Exception:
                                pass

                net_margin_value = None
                if ratios_data.get('net_profit_margin') is not None:
                    try:
                        net_margin_value = float(ratios_data.get('net_profit_margin'))
                    except Exception:
                        net_margin_value = None
                if (net_margin_value is None or net_margin_value in (0.0, 0)) and key_metrics:
                    km_val = key_metrics.get('netProfitMarginTTM')
                    if km_val is not None:
                        try:
                            km_val_f = float(km_val)
                            if km_val_f not in (0.0, 0):
                                net_margin_value = km_val_f
                        except Exception:
                            pass
                if (net_margin_value is None or net_margin_value in (0.0, 0)) and isinstance(basic_fundamentals, dict):
                    for k in ("net_margin", "netProfitMargin", "netProfitMarginTTM", "net_profit_margin"):
                        if basic_fundamentals.get(k) is not None:
                            try:
                                net_margin_value = float(basic_fundamentals.get(k))
                                break
                            except Exception:
                                pass
                if net_margin_value is None or net_margin_value in (0.0, 0):
                    if calculated_net_margin not in (0.0, 0):
                        net_margin_value = calculated_net_margin
                if net_margin_value is None:
                    net_margin_value = 0.0

                cash_and_equivalents_value = 0.0
                total_debt_value = 0.0
                if balance_sheet:
                    total_debt_value = self._safe_float(balance_sheet[2])
                    cash_and_equivalents_value = self._safe_float(balance_sheet[3])
                    if cash_and_equivalents_value in (0.0, 0):
                        cash_and_equivalents_value = self._safe_float(balance_sheet[4])

                confidence_penalty = 0.0
                data_quality_flags: List[str] = []
                try:
                    if price_source == "derived_market_cap_over_shares":
                        confidence_penalty += 0.12
                        data_quality_flags.append("price_derived")
                except Exception:
                    pass
                try:
                    if price_source == "fair_value_runs.current_price":
                        confidence_penalty += 0.05
                        data_quality_flags.append("price_from_last_run")
                except Exception:
                    pass
                if shares_outstanding_source in ("fmp_key_metrics_ttm.weightedAverageShsOutDilTTM", "fmp_key_metrics_ttm.weightedAverageShsOut"):
                    confidence_penalty += 0.05
                    data_quality_flags.append("shares_weighted_average")
                if shares_outstanding_source == "derived_market_cap_over_price":
                    confidence_penalty += 0.10
                    data_quality_flags.append("shares_derived")

                now = datetime.utcnow()
                recency_days = {}
                if key_metrics_generated_at:
                    try:
                        recency_days["fmp_key_metrics_ttm"] = float((now - key_metrics_generated_at).days)
                    except Exception:
                        pass
                if growth_generated_at:
                    try:
                        recency_days["growth_snapshot"] = float((now - growth_generated_at).days)
                    except Exception:
                        pass
                if recency_days:
                    max_days = max(recency_days.values())
                    if max_days > 90:
                        confidence_penalty += 0.10
                        data_quality_flags.append("stale_inputs")

                eps_ttm_value = self._safe_float(
                    (basic_fundamentals or {}).get('eps')
                    or (basic_fundamentals or {}).get('eps_ttm')
                    or (basic_fundamentals or {}).get('epsTTM')
                    or (basic_fundamentals or {}).get('epsTtm')
                    or (key_metrics or {}).get('epsTTM')
                    or (key_metrics or {}).get('netIncomePerShareTTM')
                    or (key_metrics or {}).get('netIncomePerShare')
                    or (key_metrics or {}).get('netIncomePerShareTTM')
                )

                # Fallback: compute EPS from income statement net income / shares outstanding.
                # Some FMP snapshot payloads omit EPS fields entirely.
                if eps_ttm_value <= 0 and income_statement_row:
                    try:
                        net_income_value = self._safe_float(income_statement_row[3])
                        if net_income_value > 0 and shares_outstanding_value > 0:
                            eps_ttm_value = net_income_value / shares_outstanding_value
                    except Exception:
                        pass

                # If shares are still missing, derive them from net income and EPS.
                if (shares_outstanding_value in (0.0, 0) or shares_outstanding_value <= 0) and income_statement_row:
                    try:
                        net_income_value = self._safe_float(income_statement_row[3])
                        if net_income_value > 0 and float(eps_ttm_value or 0.0) > 0:
                            shares_outstanding_value = float(net_income_value) / float(eps_ttm_value)
                            if shares_outstanding_value > 0:
                                shares_outstanding_source = "derived_net_income_over_eps"
                                shares_outstanding_haircut = 0.95
                    except Exception:
                        pass

                # Second-pass offline price derivation after shares/EPS fallbacks.
                try:
                    current_price_f = self._safe_float(current_price)
                    if (current_price_f is None or float(current_price_f) <= 0.0) and market_cap_hint > 0 and shares_outstanding_value > 0:
                        derived_price = float(market_cap_hint) / float(shares_outstanding_value)
                        if derived_price > 0:
                            current_price = derived_price
                            price_source = "derived_market_cap_over_shares"
                except Exception:
                    pass

                eps_forward_value = self._safe_float(
                    (basic_fundamentals or {}).get('eps_forward')
                    or (basic_fundamentals or {}).get('epsForward')
                    or (basic_fundamentals or {}).get('forwardEps')
                    or (basic_fundamentals or {}).get('forward_eps')
                    or (basic_fundamentals or {}).get('epsForwardTTM')
                )

                # Clamp forward EPS against TTM EPS to prevent blow-ups from stale/wrong-unit estimates.
                # This is fundamentals-only (does not use price).
                try:
                    if ENABLE_FAIR_VALUE_FORWARD_EPS_CLAMP:
                        eps_ttm_for_clamp = float(eps_ttm_value or 0.0)
                        eps_forward_for_clamp = float(eps_forward_value or 0.0)
                        if eps_ttm_for_clamp > 0 and eps_forward_for_clamp > 0:
                            min_ratio = float(os.getenv("FAIR_VALUE_FORWARD_EPS_MIN_RATIO", "0.25") or 0.25)
                            max_ratio = float(os.getenv("FAIR_VALUE_FORWARD_EPS_MAX_RATIO", "4.0") or 4.0)
                            ratio = eps_forward_for_clamp / eps_ttm_for_clamp
                            if ratio < min_ratio:
                                eps_forward_value = eps_ttm_for_clamp * float(min_ratio)
                                data_quality_flags.append("eps_forward_clamped_low")
                            elif ratio > max_ratio:
                                eps_forward_value = eps_ttm_for_clamp * float(max_ratio)
                                data_quality_flags.append("eps_forward_clamped_high")
                except Exception:
                    pass

                revenue_value = 0.0
                revenue_source = None
                if key_metrics:
                    revenue_value = self._safe_float(
                        (key_metrics or {}).get('revenueTTM')
                        or (key_metrics or {}).get('revenueTtm')
                        or (key_metrics or {}).get('revenue')
                    )
                    if revenue_value not in (0.0, 0):
                        revenue_source = "key_metrics"
                if revenue_value in (0.0, 0) and key_metrics:
                    revenue_per_share_ttm = self._safe_float((key_metrics or {}).get('revenuePerShareTTM'))
                    if revenue_per_share_ttm > 0 and shares_outstanding_value > 0:
                        revenue_value = revenue_per_share_ttm * shares_outstanding_value
                        if revenue_value not in (0.0, 0):
                            revenue_source = "revenue_per_share_ttm"
                if revenue_value in (0.0, 0) and income_statement_row:
                    revenue_value = self._safe_float(income_statement_row[0])
                    if revenue_value not in (0.0, 0):
                        revenue_source = "income_statement"
                if revenue_value in (0.0, 0):
                    revenue_value = self._safe_float(
                        (basic_fundamentals or {}).get('revenue')
                        or (basic_fundamentals or {}).get('revenue_ttm')
                        or (basic_fundamentals or {}).get('revenueTTM')
                        or (basic_fundamentals or {}).get('revenueTtm')
                        or (key_metrics or {}).get('revenuePerShareTTM')
                    )
                    if revenue_value not in (0.0, 0):
                        revenue_source = "basic_fundamentals"

                # Revenue sanity: if implied P/S is implausibly high, we likely have quarterly revenue.
                # Annualize to avoid EV/Sales collapsing for unprofitable growth names.
                try:
                    market_cap_hint = self._safe_float((key_metrics or {}).get('marketCap') or (basic_fundamentals or {}).get('market_cap'))
                    if market_cap_hint > 0 and revenue_value and float(revenue_value) > 0:
                        implied_ps = float(market_cap_hint) / float(revenue_value)
                        ps_annualize_threshold = float(os.getenv("FAIR_VALUE_REVENUE_ANNUALIZE_PS_THRESHOLD", "80") or 80.0)
                        if implied_ps > ps_annualize_threshold:
                            revenue_value = float(revenue_value) * 4.0
                            revenue_source = f"{revenue_source}_annualized" if revenue_source else "annualized"
                            data_quality_flags.append(f"revenue_annualized_implied_ps:{round(implied_ps, 1)}")
                except Exception:
                    pass

                fundamentals = FundamentalData(
                    current_price=float(current_price) if current_price is not None else 0.0,
                    eps_ttm=eps_ttm_value,
                    eps_forward=eps_forward_value,
                    eps_yoy_growth=eps_growth,
                    revenue=revenue_value,
                    revenue_yoy_growth=revenue_yoy_growth,
                    gross_margin=float(ratios_data.get('gross_profit_margin')) if ratios_data.get('gross_profit_margin') is not None else float(key_metrics.get('grossProfitMarginTTM', 0)) if key_metrics and key_metrics.get('grossProfitMarginTTM') not in (None, 0, 0.0) else calculated_gross_margin,  # Already in percentage
                    operating_margin=float(ratios_data.get('operating_margin')) if ratios_data.get('operating_margin') is not None else float(key_metrics.get('operatingMarginTTM', 0)) if key_metrics and key_metrics.get('operatingMarginTTM') not in (None, 0, 0.0) else calculated_operating_margin,
                    net_margin=net_margin_value,
                    roic=float(ratios_data.get('roic')) if ratios_data.get('roic') is not None else float(key_metrics.get('returnOnCapitalEmployedTTM', 0)) if key_metrics else calculated_roic,  # Use database ROIC first, calculated as fallback
                    debt_to_equity=float(ratios_data.get('debt_to_equity')) if ratios_data.get('debt_to_equity') is not None else 0.0,
                    current_pe=float(basic_fundamentals.get('pe_ratio', 0)),
                    forward_pe=float(basic_fundamentals.get('forward_pe', 0)),
                    peg_ratio=peg_ratio,
                    industry=basic_fundamentals.get('industry', 'Unknown'),
                    market_cap=float(key_metrics.get('marketCap', basic_fundamentals.get('market_cap', 0))),
                    shares_outstanding=shares_outstanding_value,
                    cash_and_equivalents=cash_and_equivalents_value,
                    total_debt=total_debt_value,
                    free_cash_flow=float(free_cash_flow_value) if free_cash_flow_value is not None else self._safe_float(owner_earnings),
                    book_value=float(key_metrics.get('bookValueperShareTTM', 0)) if key_metrics else 0.0,
                    data_quality={
                        "price_source": price_source,
                        "price_date": str(price_quote_date) if (price_fallback_to_fmp and price_quote_date is not None) else (str(db_price_date) if db_price_date is not None else None),
                        "price_recency_days": float(price_recency_days) if price_recency_days is not None else None,
                        "db_price_date": str(db_price_date) if db_price_date is not None else None,
                        "price_quote_timestamp": float(price_quote_timestamp) if price_quote_timestamp is not None else None,
                        "price_quote_date": str(price_quote_date) if price_quote_date is not None else None,
                        "eps_growth_source": eps_growth_source,
                        "roe": self._safe_float(ratios_data.get('roe')) if ratios_data else 0.0,
                        "shares_outstanding_source": shares_outstanding_source,
                        "shares_outstanding_haircut": shares_outstanding_haircut,
                        "confidence_penalty": confidence_penalty,
                        "flags": data_quality_flags,
                        "recency_days": recency_days,
                        "free_cash_flow_source": free_cash_flow_source,
                    },
                )

                try:
                    if price_fallback_to_fmp:
                        (fundamentals.data_quality or {}).setdefault("flags", []).append("price_from_fmp_quote")
                except Exception:
                    pass

                try:
                    dilution_horizon_years = 5
                    dilution_rate = 0.0
                    if shares_outstanding_source in (
                        "fmp_key_metrics_ttm.weightedAverageShsOutDilTTM",
                        "fmp_key_metrics_ttm.weightedAverageShsOut",
                    ):
                        dilution_rate = max(dilution_rate, 0.03)
                    if float(fundamentals.free_cash_flow or 0.0) <= 0 and float(fundamentals.net_margin or 0.0) < 0:
                        dilution_rate = max(dilution_rate, 0.08)
                    if float(fundamentals.revenue or 0.0) > 0 and float(fundamentals.revenue) < 100_000_000:
                        dilution_rate = max(dilution_rate, 0.10)

                    projected_shares_outstanding = None
                    if float(fundamentals.shares_outstanding or 0.0) > 0 and dilution_rate > 0:
                        projected_shares_outstanding = float(fundamentals.shares_outstanding) * (1.0 + dilution_rate) ** int(dilution_horizon_years)

                    (fundamentals.data_quality or {}).update(
                        {
                            "dilution_rate_est": dilution_rate,
                            "dilution_horizon_years": dilution_horizon_years,
                            "projected_shares_outstanding": projected_shares_outstanding,
                        }
                    )
                except Exception:
                    pass
                
                logger.info(f"Enhanced fundamentals for {symbol}: eps_growth={fundamentals.eps_yoy_growth}%, revenue_growth={fundamentals.revenue_yoy_growth}%, roic={fundamentals.roic}%, market_cap={fundamentals.market_cap}, peg_ratio={fundamentals.peg_ratio}, debt_to_equity={fundamentals.debt_to_equity}")
                
                return fundamentals
                
        except Exception as e:
            logger.error(f"Error getting fundamentals for {symbol}: {e}")
            return None

    def _persist_fair_value_run(
        self,
        symbol: str,
        fundamentals: FundamentalData,
        weighted_fair_value: float,
        valuation_metrics: Dict[str, Any],
        quality_score: float,
        individual_valuations: Dict[str, Any],
        updated_at: datetime,
        method_results: Optional[List[Dict[str, Any]]] = None
    ) -> Optional[str]:
        try:
            run_id = f"fv_{uuid.uuid4().hex[:16]}"
            valuation_ratio = None
            undervaluation_pct = None
            if weighted_fair_value and weighted_fair_value > 0 and fundamentals.current_price is not None:
                valuation_ratio = float(fundamentals.current_price) / float(weighted_fair_value)
                undervaluation_pct = (1.0 - valuation_ratio) * 100.0

            query = """
                INSERT INTO fair_value_runs
                (run_id, symbol, as_of, current_price, fair_value, valuation_ratio,
                 undervaluation_pct, valuation_rating, quality_score,
                 valuation_metrics, fundamentals, individual_valuations, model_version)
                VALUES
                (:run_id, :symbol, :as_of, :current_price, :fair_value, :valuation_ratio,
                 :undervaluation_pct, :valuation_rating, :quality_score,
                 :valuation_metrics, :fundamentals, :individual_valuations, :model_version)
            """

            db.execute_update(query, {
                "run_id": run_id,
                "symbol": symbol,
                "as_of": updated_at,
                "current_price": fundamentals.current_price,
                "fair_value": weighted_fair_value,
                "valuation_ratio": valuation_ratio,
                "undervaluation_pct": undervaluation_pct,
                "valuation_rating": valuation_metrics.get("valuation_rating"),
                "quality_score": quality_score,
                "valuation_metrics": json.dumps(valuation_metrics),
                "fundamentals": json.dumps({
                    "eps_ttm": fundamentals.eps_ttm,
                    "eps_forward": fundamentals.eps_forward,
                    "eps_yoy_growth": fundamentals.eps_yoy_growth,
                    "revenue": fundamentals.revenue,
                    "revenue_yoy_growth": fundamentals.revenue_yoy_growth,
                    "gross_margin": fundamentals.gross_margin,
                    "operating_margin": fundamentals.operating_margin,
                    "net_margin": fundamentals.net_margin,
                    "roic": fundamentals.roic,
                    "debt_to_equity": fundamentals.debt_to_equity,
                    "current_pe": fundamentals.current_pe,
                    "forward_pe": fundamentals.forward_pe,
                    "peg_ratio": fundamentals.peg_ratio,
                    "industry": fundamentals.industry,
                    "market_cap": fundamentals.market_cap,
                    "free_cash_flow": fundamentals.free_cash_flow,
                    "book_value": fundamentals.book_value
                }),
                "individual_valuations": json.dumps(individual_valuations),
                "model_version": "fair_value_v1"
            })

            self._persist_fair_value_method_results(
                run_id=run_id,
                fundamentals=fundamentals,
                weighted_fair_value=weighted_fair_value,
                valuation_metrics=valuation_metrics,
                individual_valuations=individual_valuations,
                method_results=method_results,
            )

            return run_id
        except Exception as e:
            logger.warning(f"Fair value persistence skipped for {symbol}: {e}")
            return None

    def _persist_fair_value_method_results(
        self,
        run_id: str,
        fundamentals: FundamentalData,
        weighted_fair_value: float,
        valuation_metrics: Dict[str, Any],
        individual_valuations: Dict[str, Any],
        method_results: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        methods: List[Dict[str, Any]] = []

        if method_results:
            for m in method_results:
                methods.append({
                    "method_key": m.get("method_key"),
                    "enabled": bool(m.get("enabled")),
                    "status": m.get("status"),
                    "fair_price": m.get("fair_price"),
                    "metrics": {
                        "severity": m.get("severity"),
                        "reason": m.get("reason"),
                        "score": m.get("score"),
                        **(m.get("metrics") or {}),
                    },
                })

            methods.append({
                "method_key": "weighted_blend",
                "enabled": True,
                "status": "ok" if weighted_fair_value and float(weighted_fair_value) > 0 else "missing_data",
                "fair_price": float(weighted_fair_value) if weighted_fair_value and float(weighted_fair_value) > 0 else None,
                "metrics": {
                    "valuation_rating": valuation_metrics.get("valuation_rating"),
                    "valuation_ratio": valuation_metrics.get("valuation_ratio"),
                    "undervaluation_pct": valuation_metrics.get("undervaluation_pct"),
                },
            })
        else:
            # Backward compatible persistence path
            peg_legacy_fair = individual_valuations.get("peg_legacy_method")
            if peg_legacy_fair is None:
                peg_legacy_fair = individual_valuations.get("peg_method")
            methods.append({
                "method_key": "peg_legacy",
                "enabled": True,
                "status": "ok" if peg_legacy_fair and float(peg_legacy_fair) > 0 else "missing_data",
                "fair_price": float(peg_legacy_fair) if peg_legacy_fair and float(peg_legacy_fair) > 0 else None,
                "metrics": valuation_metrics.get("peg_score") or {}
            })

            rule_of_40_metrics = valuation_metrics.get("peg_rule_of_40_forward_cagr") or {}
            rule_of_40_enabled = bool(rule_of_40_metrics.get("enabled"))
            rule_of_40_fair = individual_valuations.get("peg_rule_of_40_forward_cagr_method")
            if rule_of_40_fair is None:
                rule_of_40_fair = rule_of_40_metrics.get("fair_price")
            methods.append({
                "method_key": "peg_rule_of_40_forward_cagr",
                "enabled": rule_of_40_enabled,
                "status": "ok" if rule_of_40_enabled and rule_of_40_fair and float(rule_of_40_fair) > 0 else ("disabled_by_regime" if not rule_of_40_enabled else "missing_data"),
                "fair_price": float(rule_of_40_fair) if rule_of_40_fair and float(rule_of_40_fair) > 0 else None,
                "metrics": rule_of_40_metrics
            })

            pe_fair = individual_valuations.get("pe_method")
            methods.append({
                "method_key": "pe_forward",
                "enabled": True,
                "status": "ok" if pe_fair and float(pe_fair) > 0 else "missing_data",
                "fair_price": float(pe_fair) if pe_fair and float(pe_fair) > 0 else None,
                "metrics": valuation_metrics.get("pe_score") or {}
            })

            dcf_fair = individual_valuations.get("dcf_method")
            methods.append({
                "method_key": "dcf_simple",
                "enabled": True,
                "status": "ok" if dcf_fair and float(dcf_fair) > 0 else "missing_data",
                "fair_price": float(dcf_fair) if dcf_fair and float(dcf_fair) > 0 else None,
                "metrics": valuation_metrics.get("dcf_score") or {}
            })

            methods.append({
                "method_key": "weighted_blend",
                "enabled": True,
                "status": "ok" if weighted_fair_value and float(weighted_fair_value) > 0 else "missing_data",
                "fair_price": float(weighted_fair_value) if weighted_fair_value and float(weighted_fair_value) > 0 else None,
                "metrics": {
                    "valuation_rating": valuation_metrics.get("valuation_rating"),
                    "valuation_ratio": valuation_metrics.get("valuation_ratio"),
                    "undervaluation_pct": valuation_metrics.get("undervaluation_pct")
                }
            })

        insert_query = """
            INSERT INTO fair_value_method_results
            (run_id, method_key, method_version_id, enabled, status, fair_price, upside_pct, metrics_json)
            VALUES
            (:run_id, :method_key, :method_version_id, :enabled, :status, :fair_price, :upside_pct, :metrics_json)
        """

        missing_logged: set[str] = set()
        for m in methods:
            method_key = m["method_key"]

            # Self-heal: ensure known method keys are registered in DB so persistence doesn't warn.
            # This is necessary because historical migrations may have run before we added new methods.
            try:
                self._ensure_method_registered(method_key)
            except Exception:
                pass

            if not self._method_key_exists(method_key):
                if method_key not in missing_logged:
                    logger.warning(
                        f"Skipping persistence for unknown fair value method_key='{method_key}' (run_id={run_id}). "
                        "Add it to fair_value_methods to enable persistence."
                    )
                    missing_logged.add(method_key)
                continue

            method_version_id = self._get_active_method_version_id(m["method_key"])
            fair_price = m.get("fair_price")
            upside_pct = None
            if fair_price and fundamentals.current_price and float(fundamentals.current_price) > 0:
                upside_pct = (float(fair_price) / float(fundamentals.current_price) - 1.0) * 100.0

            db.execute_update(insert_query, {
                "run_id": run_id,
                "method_key": m["method_key"],
                "method_version_id": method_version_id,
                "enabled": bool(m.get("enabled")),
                "status": m.get("status"),
                "fair_price": fair_price,
                "upside_pct": upside_pct,
                "metrics_json": json.dumps(m.get("metrics") or {})
            })

    def _ensure_method_registered(self, method_key: str) -> None:
        """Best-effort registry bootstrap for newly added method keys."""
        method_key = str(method_key or "").strip()
        if not method_key:
            return

        known: Dict[str, Dict[str, Any]] = {
            "adjusted_pe": {
                "name": "Adjusted P/E Method",
                "description": "Industry P/E adjusted for growth and quality (used primarily in cyclical/other regimes)",
                "definition_json": {
                    "inputs": ["eps_ttm", "industry_avg_pe", "eps_yoy_growth"],
                    "notes": "Adjusted P/E variant used by engine; persisted for audit/reproducibility.",
                },
            },
            "ev_sales": {
                "name": "EV/Sales Method",
                "description": "EV/Sales heuristic based on growth and margin proxies (used primarily in unprofitable growth)",
                "definition_json": {
                    "inputs": ["revenue", "revenue_yoy_growth", "gross_margin", "shares_outstanding", "total_debt", "cash_and_equivalents"],
                    "notes": "Simplified EV/Sales method used by engine; persisted for audit/reproducibility.",
                },
            },
        }

        if method_key not in known:
            return

        meta = known[method_key]

        # Insert into fair_value_methods
        db.execute_update(
            """
            INSERT INTO fair_value_methods(method_key, name, description)
            VALUES (:method_key, :name, :description)
            ON CONFLICT (method_key) DO NOTHING
            """,
            {
                "method_key": method_key,
                "name": meta.get("name"),
                "description": meta.get("description"),
            },
        )

        # Ensure at least one active version exists
        existing = db.execute_query(
            """
            SELECT method_version_id
            FROM fair_value_method_versions
            WHERE method_key = :method_key AND is_active = true
            ORDER BY version DESC
            LIMIT 1
            """,
            {"method_key": method_key},
        )
        if existing:
            return

        db.execute_update(
            """
            INSERT INTO fair_value_method_versions(method_version_id, method_key, version, is_active, definition_json)
            VALUES (:method_version_id, :method_key, :version, true, CAST(:definition_json AS jsonb))
            ON CONFLICT (method_key, version) DO NOTHING
            """,
            {
                "method_version_id": f"fv_method_{uuid.uuid4().hex[:16]}",
                "method_key": method_key,
                "version": 1,
                "definition_json": json.dumps(meta.get("definition_json") or {}),
            },
        )

    def _get_active_method_version_id(self, method_key: str) -> Optional[str]:
        try:
            query = """
                SELECT method_version_id
                FROM fair_value_method_versions
                WHERE method_key = :method_key AND is_active = true
                ORDER BY version DESC
                LIMIT 1
            """
            rows = db.execute_query(query, {"method_key": method_key})
            if rows:
                return rows[0].get("method_version_id")
            return None
        except Exception:
            return None

    def _method_key_exists(self, method_key: str) -> bool:
        try:
            query = """
                SELECT 1
                FROM fair_value_methods
                WHERE method_key = :method_key
                LIMIT 1
            """
            rows = db.execute_query(query, {"method_key": method_key})
            return bool(rows)
        except Exception:
            return False
    
    def _calculate_peg_value(self, fundamentals: FundamentalData) -> Optional[float]:
        """Calculate fair value based on PEG ratio"""
        
        growth_pct = None
        try:
            growth_pct = float((fundamentals.data_quality or {}).get("growth_proxy_pct_capped"))
        except Exception:
            growth_pct = None
        if growth_pct is None:
            growth_pct = max(0.0, float(fundamentals.eps_yoy_growth or 0.0))

        if fundamentals.eps_ttm <= 0 or float(growth_pct or 0.0) <= 0:
            return None
        
        # Get industry PEG benchmark
        industry = fundamentals.industry
        industry_peg = self.industry_benchmarks.get(industry, {}).get('avg_peg', 1.0)
        
        fair_pe = (math.sqrt(growth_pct) * float(industry_peg) * 10.0) if growth_pct > 0 else 0.0
        
        cap = 40.0
        if float(growth_pct or 0.0) > 50:
            cap = 80.0
        elif float(growth_pct or 0.0) > 30:
            cap = 60.0
        fair_pe = min(fair_pe, cap)
        
        # Calculate fair price
        fair_price = fundamentals.eps_ttm * fair_pe
        
        return fair_price if fair_price and fair_price > 0 else None

    def _calculate_rule_of_40(self, revenue_growth_pct: float, profit_margin_pct: float) -> float:
        return float(revenue_growth_pct or 0.0) + float(profit_margin_pct or 0.0)

    def _calculate_target_peg_from_rule_of_40(self, rule_of_40: float) -> float:
        if rule_of_40 < 40:
            return 1.0
        if rule_of_40 < 60:
            return 1.2
        if rule_of_40 < 80:
            return 1.5
        if rule_of_40 < 100:
            return 2.0
        return 2.5

    def _cap_growth(self, cagr: float, cap: float = 0.70) -> float:
        return float(min(float(cagr), float(cap)))

    def _cap_target_pe(self, target_pe: float, cap: float = 60.0) -> float:
        return float(min(float(target_pe), float(cap)))

    def _compute_cagr(self, start: float, end: float, years: int) -> float:
        start = float(start)
        end = float(end)
        years = int(years)
        if years <= 0 or start <= 0 or end <= 0:
            raise ValueError("invalid CAGR inputs")
        return (end / start) ** (1.0 / years) - 1.0

    def _parse_estimate_date(self, value: Any) -> Optional[datetime]:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
        return None
    
    def _calculate_pe_value(self, fundamentals: FundamentalData) -> Optional[float]:
        """Calculate fair value based on forward P/E"""
        
        if fundamentals.eps_forward <= 0:
            return None
        
        # Get industry P/E benchmark
        industry = fundamentals.industry
        industry_pe = self.industry_benchmarks.get(industry, {}).get('avg_pe', 18.0)
        
        growth_for_adjustment = None
        try:
            growth_for_adjustment = float((fundamentals.data_quality or {}).get("growth_proxy_pct_capped"))
        except Exception:
            growth_for_adjustment = None
        if growth_for_adjustment is None:
            growth_for_adjustment = max(0.0, float(fundamentals.eps_yoy_growth or 0.0))
        growth_for_adjustment = max(0.0, float(growth_for_adjustment))
        growth_adjustment = min(float(math.log1p(growth_for_adjustment / 10.0)), 1.5)
        try:
            regime = str((fundamentals.data_quality or {}).get("regime") or "")
        except Exception:
            regime = ""
        try:
            industry_l = str(fundamentals.industry or "").lower()
        except Exception:
            industry_l = ""
        try:
            if regime == _REGIME_MATURE_VALUE:
                growth_adjustment = min(float(growth_adjustment), 0.8)
                if "beverage" in industry_l or "consumer" in industry_l or "household" in industry_l:
                    growth_adjustment = min(float(growth_adjustment), 0.6)
        except Exception:
            pass
        adjusted_pe_raw = industry_pe * (1 + growth_adjustment)

        # Guardrail (fundamentals-only): cap the multiple itself, not the resulting fair price.
        # This prevents runaway valuations from bad growth inputs while keeping valuation
        # independent of market price.
        pe_cap = 60.0
        try:
            regime = str((fundamentals.data_quality or {}).get("regime") or "")
        except Exception:
            regime = ""
        try:
            industry_l = str(fundamentals.industry or "").lower()
        except Exception:
            industry_l = ""
        try:
            if regime == _REGIME_MATURE_VALUE:
                pe_cap = float(os.getenv("FAIR_VALUE_MATURE_PE_CAP", "35.0") or 35.0)
            if "beverage" in industry_l or "consumer" in industry_l or "household" in industry_l:
                pe_cap = min(pe_cap, float(os.getenv("FAIR_VALUE_STAPLES_PE_CAP", "28.0") or 28.0))
        except Exception:
            pass

        adjusted_pe = min(float(adjusted_pe_raw), float(pe_cap))
        
        # Calculate fair price
        eps_forward_used = float(fundamentals.eps_forward)
        try:
            risk_score = float((fundamentals.data_quality or {}).get("risk_score") or 0.0)
            risk_score = max(0.0, min(1.0, risk_score))

            # Forward EPS tends to be optimistic in low-quality / speculative profiles.
            # Risk budget normalization: ensure risk isn't applied twice (blend weights + EPS haircut)
            # beyond the configured cap.
            eps_haircut_max = 0.20
            eps_multiplier_raw = 1.0 - float(eps_haircut_max) * float(risk_score)

            weight_mult = float((fundamentals.data_quality or {}).get("pe_forward_weight_multiplier") or 1.0)
            min_mult = float((fundamentals.data_quality or {}).get("risk_budget_min_multiplier") or 0.55)
            if weight_mult <= 0:
                weight_mult = 1.0

            # Ensure combined risk impact (weight multiplier * EPS multiplier) is not below min_mult.
            eps_multiplier_floor = min(1.0, float(min_mult) / float(weight_mult))
            eps_multiplier_used = max(float(eps_multiplier_raw), float(eps_multiplier_floor))
            eps_forward_used = eps_forward_used * float(eps_multiplier_used)

            try:
                if fundamentals.data_quality is not None:
                    fundamentals.data_quality["pe_forward_eps_multiplier"] = float(eps_multiplier_used)
                    fundamentals.data_quality["pe_forward_combined_multiplier"] = float(weight_mult) * float(eps_multiplier_used)
            except Exception:
                pass
        except Exception:
            pass

        fair_price = eps_forward_used * adjusted_pe
        
        return fair_price if fair_price and fair_price > 0 else None
    
    def _calculate_dcf_value(self, fundamentals: FundamentalData) -> Optional[float]:
        """Calculate fair value using simplified DCF analysis"""

        fair_price, _metrics = self._calculate_dcf_value_with_metrics(fundamentals)
        return fair_price

    def _calculate_dcf_value_with_metrics(self, fundamentals: FundamentalData) -> Tuple[Optional[float], Dict[str, Any]]:
        discount_rate_base = 0.10
        macro_shift = float(FAIR_VALUE_DISCOUNT_RATE_SHIFT or 0.0)
        discount_rate_effective = float(discount_rate_base) + float(macro_shift)
        metrics: Dict[str, Any] = {
            "discount_rate": discount_rate_effective,
            "discount_rate_base": discount_rate_base,
            "discount_rate_macro_shift": macro_shift,
            "terminal_growth_cap": 0.03,
            "growth_cap": 0.20,
            "reinvestment_drag": 0.7,
            "instability_drag_max": 0.40,
            "confidence_penalty": 0.0,
            "terminal_dominance_haircut": 0.0,
            "scenarios": {},
        }

        risk_score_for_caps = 0.0
        free_cash_flow_trusted = None
        try:
            risk_score_for_caps = float((fundamentals.data_quality or {}).get("risk_score") or 0.0)
        except Exception:
            risk_score_for_caps = 0.0
        risk_score_for_caps = max(0.0, min(1.0, float(risk_score_for_caps)))
        try:
            free_cash_flow_trusted = bool((fundamentals.data_quality or {}).get("free_cash_flow_trusted"))
        except Exception:
            free_cash_flow_trusted = None

        if fundamentals.free_cash_flow <= 0:
            return None, {**metrics, "reason": "free_cash_flow_missing_or_nonpositive"}
        if fundamentals.shares_outstanding <= 0:
            return None, {**metrics, "reason": "shares_outstanding_missing_or_nonpositive"}

        growth_rate = None
        if fundamentals.revenue_yoy_growth is not None and float(fundamentals.revenue_yoy_growth) != 0.0:
            growth_rate = float(fundamentals.revenue_yoy_growth) / 100.0
            metrics["growth_proxy"] = "revenue_growth"
        if growth_rate is None or growth_rate == 0.0:
            growth_proxy_pct = None
            try:
                growth_proxy_pct = float((fundamentals.data_quality or {}).get("growth_proxy_pct_capped"))
            except Exception:
                growth_proxy_pct = None
            if growth_proxy_pct is None:
                growth_proxy_pct = float(fundamentals.eps_yoy_growth or 0.0)
            growth_rate = (float(growth_proxy_pct or 0.0) / 100.0) * 0.6
            metrics["growth_proxy"] = "growth_proxy_pct_capped_weighted" if (fundamentals.data_quality or {}).get("growth_proxy_pct_capped") is not None else "eps_growth_weighted"
        growth_rate = float(min(float(growth_rate), float(metrics["growth_cap"])))

        effective_growth = float(growth_rate) * float(metrics["reinvestment_drag"])

        # Volatility / instability adjustment: DCF assumes smooth compounding; for unstable profiles
        # we reduce effective growth to avoid optimistic paths.
        instability_score = 0.0
        try:
            rg = float(fundamentals.revenue_yoy_growth or 0.0)
            eg = float(fundamentals.eps_yoy_growth or 0.0)
            # Divergence between revenue and EPS growth is a common sign of noisy/temporary growth.
            divergence = abs(rg - eg)

            # Direction-awareness: EPS and revenue can legitimately diverge in healthy ways.
            # - EPS >> revenue often indicates margin expansion / operating leverage (less penalize)
            # - EPS << revenue can be investment phase or margin compression (penalize more unless
            #   high gross margin + strong revenue growth suggests deliberate reinvestment).
            direction = "eps_above_revenue" if eg > rg else "eps_below_revenue" if eg < rg else "aligned"
            metrics["growth_divergence_pct"] = float(divergence)
            metrics["growth_divergence_direction"] = direction

            base_score = 0.0
            if divergence >= 60.0:
                base_score = 1.0
            elif divergence >= 30.0:
                base_score = 0.6
            elif divergence >= 15.0:
                base_score = 0.3

            gross_margin = float(fundamentals.gross_margin or 0.0)
            adjustment_factor = 1.0
            if direction == "eps_above_revenue":
                # Common in strong franchises scaling efficiently; reduce penalty.
                adjustment_factor = 0.45 if gross_margin >= 45.0 else 0.65
            elif direction == "eps_below_revenue":
                # If revenue is strong and gross margin is high, treat as investment phase.
                if rg >= 15.0 and gross_margin >= 50.0:
                    adjustment_factor = 0.55
                else:
                    adjustment_factor = 1.0

            metrics["instability_adjustment_factor"] = float(adjustment_factor)
            instability_score = float(base_score) * float(adjustment_factor)

            # Loss-making businesses often have higher forecast error.
            if float(fundamentals.free_cash_flow or 0.0) <= 0 and float(fundamentals.net_margin or 0.0) < 0:
                instability_score = max(instability_score, 0.8)
        except Exception:
            instability_score = 0.0

        if instability_score > 0:
            drag = min(float(metrics.get("instability_drag_max", 0.40)), 0.10 + 0.40 * float(instability_score))
            effective_growth = float(effective_growth) * (1.0 - float(drag))
            metrics["instability_score"] = float(instability_score)
            metrics["instability_drag"] = float(drag)
        discount_rate = float(metrics["discount_rate"])
        terminal_growth = min(float(metrics["terminal_growth_cap"]), float(effective_growth) * 0.4)

        fcf_projections = []
        current_fcf = float(fundamentals.free_cash_flow)
        for year in range(1, 6):
            projected_fcf = current_fcf * (1 + effective_growth) ** year
            fcf_projections.append(projected_fcf)

        terminal_fcf = fcf_projections[-1]
        terminal_value = terminal_fcf * (1 + terminal_growth) / (discount_rate - terminal_growth)

        pv_projections = sum(fcf / ((1 + discount_rate) ** year) for year, fcf in enumerate(fcf_projections, 1))
        pv_terminal = terminal_value / ((1 + discount_rate) ** 5)

        enterprise_value = pv_projections + pv_terminal
        terminal_share = (pv_terminal / enterprise_value) if enterprise_value > 0 else None

        # Terminal dominance haircut (hybrid):
        # - Raise thresholds (terminal-heavy DCFs are common, especially with 5-year explicit forecasts)
        # - Quality-gate: high-quality compounders should not be heavily penalized solely for terminal share
        # - Risk-cap: haircut can't exceed a risk-scaled cap
        dominance_haircut = 0.0
        dominance_haircut_raw = 0.0
        dominance_haircut_cap = 0.0
        quality_gate = False
        try:
            gross_margin = float(fundamentals.gross_margin or 0.0)
            net_margin = float(fundamentals.net_margin or 0.0)
            quality_gate = (
                net_margin >= 25.0
                and gross_margin >= 50.0
                and risk_score_for_caps <= 0.45
                and (free_cash_flow_trusted is not False)
            )
        except Exception:
            quality_gate = False

        if terminal_share is not None:
            # Less aggressive schedule
            if terminal_share > 0.95:
                dominance_haircut_raw = 0.35
            elif terminal_share > 0.90:
                dominance_haircut_raw = 0.20
            elif terminal_share > 0.85:
                dominance_haircut_raw = 0.10
            else:
                dominance_haircut_raw = 0.0

            # Risk-based cap; low-risk names can't get slammed by terminal mechanics.
            dominance_haircut_cap = 0.10 + 0.20 * float(risk_score_for_caps)

            # Quality gate: scale down (not fully remove) the haircut for high-quality compounders.
            if quality_gate and dominance_haircut_raw > 0:
                dominance_haircut_raw = float(dominance_haircut_raw) * 0.35
                dominance_haircut_cap = min(float(dominance_haircut_cap), 0.10)

            dominance_haircut = min(float(dominance_haircut_raw), float(dominance_haircut_cap))

        if dominance_haircut > 0:
            metrics["terminal_dominance_haircut"] = float(dominance_haircut)
            metrics["confidence_penalty"] = float(metrics.get("confidence_penalty", 0.0)) + float(dominance_haircut)

        metrics["terminal_dominance_haircut_raw"] = float(dominance_haircut_raw)
        metrics["terminal_dominance_haircut_cap"] = float(dominance_haircut_cap)
        metrics["terminal_dominance_quality_gate"] = bool(quality_gate)
        metrics["terminal_dominance_risk_score"] = float(risk_score_for_caps)

        equity_value = enterprise_value - float(fundamentals.total_debt or 0.0) + float(fundamentals.cash_and_equivalents or 0.0)

        shares_outstanding = float(fundamentals.shares_outstanding)
        projected_shares = None
        try:
            projected_shares = float((fundamentals.data_quality or {}).get("projected_shares_outstanding") or 0.0)
        except Exception:
            projected_shares = None
        shares_used = projected_shares if projected_shares and projected_shares > shares_outstanding else shares_outstanding

        fair_price_per_share = equity_value / float(shares_used)
        if dominance_haircut > 0:
            fair_price_per_share = float(fair_price_per_share) * (1.0 - float(dominance_haircut))

        metrics.update({
            "growth_rate": growth_rate,
            "effective_growth": effective_growth,
            "terminal_growth": terminal_growth,
            "pv_projections": pv_projections,
            "pv_terminal": pv_terminal,
            "enterprise_value": enterprise_value,
            "equity_value": equity_value,
            "terminal_value_share": terminal_share,
            "shares_used": shares_used,
            "shares_outstanding": shares_outstanding,
            "projected_shares_outstanding": projected_shares,
        })

        try:
            fcf0 = float(fundamentals.free_cash_flow)
            debt = float(fundamentals.total_debt or 0.0)
            cash = float(fundamentals.cash_and_equivalents or 0.0)

            def _dcf_scenario(*, scenario_key: str, effective_growth_s: float, discount_rate_s: float) -> Dict[str, Any]:
                discount_rate_s = float(max(0.05, min(0.18, discount_rate_s)))
                effective_growth_s = float(max(-0.20, min(0.25, effective_growth_s)))

                terminal_growth_s = float(min(float(metrics["terminal_growth_cap"]), float(effective_growth_s) * 0.4))
                fcf_proj_s = [fcf0 * (1.0 + effective_growth_s) ** year for year in range(1, 6)]
                pv_proj_s = sum(fcf / ((1.0 + discount_rate_s) ** year) for year, fcf in enumerate(fcf_proj_s, 1))
                terminal_fcf_s = fcf_proj_s[-1]
                denom = float(discount_rate_s - terminal_growth_s)
                if denom <= 0:
                    return {
                        "scenario": scenario_key,
                        "enabled": False,
                        "reason": "invalid_terminal_denom",
                        "discount_rate": discount_rate_s,
                        "effective_growth": effective_growth_s,
                        "terminal_growth": terminal_growth_s,
                    }

                terminal_value_s = terminal_fcf_s * (1.0 + terminal_growth_s) / denom
                pv_terminal_s = terminal_value_s / ((1.0 + discount_rate_s) ** 5)
                enterprise_value_s = pv_proj_s + pv_terminal_s
                terminal_share_s = (pv_terminal_s / enterprise_value_s) if enterprise_value_s > 0 else None

                haircut_s = 0.0
                haircut_s_raw = 0.0
                haircut_s_cap = 0.0
                if terminal_share_s is not None:
                    if terminal_share_s > 0.95:
                        haircut_s_raw = 0.35
                    elif terminal_share_s > 0.90:
                        haircut_s_raw = 0.20
                    elif terminal_share_s > 0.85:
                        haircut_s_raw = 0.10
                    else:
                        haircut_s_raw = 0.0

                    haircut_s_cap = 0.10 + 0.20 * float(risk_score_for_caps)
                    if quality_gate and haircut_s_raw > 0:
                        haircut_s_raw = float(haircut_s_raw) * 0.35
                        haircut_s_cap = min(float(haircut_s_cap), 0.10)
                    haircut_s = min(float(haircut_s_raw), float(haircut_s_cap))

                equity_value_s = enterprise_value_s - debt + cash
                fair_price_s = (equity_value_s / float(shares_used)) if shares_used and float(shares_used) > 0 else None
                if fair_price_s is not None and haircut_s > 0:
                    fair_price_s = float(fair_price_s) * (1.0 - float(haircut_s))

                return {
                    "scenario": scenario_key,
                    "enabled": fair_price_s is not None and float(fair_price_s) > 0,
                    "fair_price": float(fair_price_s) if fair_price_s is not None and float(fair_price_s) > 0 else None,
                    "discount_rate": discount_rate_s,
                    "effective_growth": effective_growth_s,
                    "terminal_growth": terminal_growth_s,
                    "pv_projections": pv_proj_s,
                    "pv_terminal": pv_terminal_s,
                    "enterprise_value": enterprise_value_s,
                    "equity_value": equity_value_s,
                    "terminal_value_share": terminal_share_s,
                    "terminal_dominance_haircut": haircut_s,
                    "terminal_dominance_haircut_raw": haircut_s_raw,
                    "terminal_dominance_haircut_cap": haircut_s_cap,
                }

            base_s = _dcf_scenario(scenario_key="base", effective_growth_s=float(effective_growth), discount_rate_s=float(discount_rate))
            bear_s = _dcf_scenario(scenario_key="bear", effective_growth_s=float(effective_growth) * 0.70, discount_rate_s=float(discount_rate) + 0.02)
            bull_s = _dcf_scenario(scenario_key="bull", effective_growth_s=float(effective_growth) * 1.15, discount_rate_s=float(discount_rate) - 0.01)

            metrics["scenarios"] = {
                "bear": bear_s,
                "base": base_s,
                "bull": bull_s,
            }

            bear_fp = bear_s.get("fair_price")
            bull_fp = bull_s.get("fair_price")
            if bear_fp and bull_fp and float(bear_fp) > 0:
                dispersion_ratio = float(bull_fp) / float(bear_fp)
                metrics["scenario_dispersion_ratio"] = dispersion_ratio
                if dispersion_ratio > 3.0:
                    metrics["confidence_penalty"] = float(metrics.get("confidence_penalty", 0.0)) + 0.10
                elif dispersion_ratio > 2.0:
                    metrics["confidence_penalty"] = float(metrics.get("confidence_penalty", 0.0)) + 0.05
        except Exception:
            pass

        fair_price = fair_price_per_share if fair_price_per_share and fair_price_per_share > 0 else None
        return fair_price, metrics

    def _calculate_valuation_metrics(self, fair_value: float, fundamentals: FundamentalData) -> Dict[str, Any]:
        """Calculate valuation metrics"""
        
        current_price = fundamentals.current_price
        if fair_value is None or float(fair_value) <= 0 or current_price is None or float(current_price) <= 0:
            return {
                'valuation_ratio': None,
                'undervaluation_pct': None,
                'pe_vs_industry': None,
                'margin_vs_industry': None,
                'valuation_rating': 'Unknown'
            }

        valuation_ratio = float(current_price) / float(fair_value)
        
        # P/E comparison
        industry = fundamentals.industry
        industry_pe = self.industry_benchmarks.get(industry, {}).get('avg_pe', 18.0)
        pe_vs_industry = fundamentals.current_pe - industry_pe if fundamentals.current_pe else 0
        
        # Margin comparison
        industry_margin = self.industry_benchmarks.get(industry, {}).get('avg_margin', 30.0)
        margin_vs_industry = fundamentals.gross_margin - industry_margin
        
        return {
            'valuation_ratio': valuation_ratio,
            'undervaluation_pct': (1 - valuation_ratio) * 100,
            'pe_vs_industry': pe_vs_industry,
            'margin_vs_industry': margin_vs_industry,
            'valuation_rating': self._get_valuation_rating(valuation_ratio)
        }
    
    def _get_valuation_rating(self, valuation_ratio: float) -> str:
        """Get valuation rating based on price/fair value ratio"""
        if valuation_ratio < 0.7:
            return "Deeply Undervalued"
        elif valuation_ratio < 0.85:
            return "Undervalued"
        elif valuation_ratio < 1.0:
            return "Slightly Undervalued"
        elif valuation_ratio < 1.15:
            return "Fair Value"
        elif valuation_ratio < 1.3:
            return "Slightly Overvalued"
        else:
            return "Overvalued"
    
    def _assess_quality(self, fundamentals: FundamentalData) -> float:
        """Calculate overall quality score (0-100)"""
        
        scores = {}
        
        # EPS Growth Quality (25% weight)
        eps_growth = fundamentals.eps_yoy_growth
        scores['eps_growth'] = self._score_eps_growth(eps_growth)
        
        # Margin Quality (20% weight)
        gross_margin = fundamentals.gross_margin
        industry_avg = self.industry_benchmarks.get(fundamentals.industry, {}).get('avg_margin', 30.0)
        scores['margin'] = self._score_margin(gross_margin, industry_avg)
        
        # ROIC Quality (20% weight)
        roic = fundamentals.roic
        scores['roic'] = self._score_roic(roic)
        
        # Debt Quality (15% weight)
        debt_to_equity = fundamentals.debt_to_equity
        scores['debt'] = self._score_debt(debt_to_equity)
        
        # PEG Quality (20% weight)
        peg_ratio = fundamentals.peg_ratio
        scores['peg'] = self._score_peg(peg_ratio)
        
        # Weighted average
        weights = {
            'eps_growth': 0.25,
            'margin': 0.20,
            'roic': 0.20,
            'debt': 0.15,
            'peg': 0.20
        }
        
        total_score = sum(scores[key] * weights[key] for key in scores)
        return min(total_score, 100)
    
    def _score_eps_growth(self, eps_growth: float) -> float:
        """Score EPS growth (0-100)"""
        thresholds = self.quality_thresholds['eps_growth']
        
        if eps_growth >= thresholds['excellent']:
            return 90
        elif eps_growth >= thresholds['good']:
            return 75
        elif eps_growth >= thresholds['average']:
            return 60
        elif eps_growth >= thresholds['poor']:
            return 40
        else:
            return 20
    
    def _score_margin(self, margin: float, industry_avg: float) -> float:
        """Score gross margin relative to industry (0-100)"""
        if industry_avg == 0:
            return 50
        
        margin_vs_industry = margin - industry_avg
        
        if margin_vs_industry >= 10:
            return 90
        elif margin_vs_industry >= 5:
            return 75
        elif margin_vs_industry >= 0:
            return 60
        elif margin_vs_industry >= -5:
            return 40
        else:
            return 20
    
    def _score_roic(self, roic: float) -> float:
        """Score ROIC (0-100)"""
        thresholds = self.quality_thresholds['roic']
        
        if roic >= thresholds['excellent']:
            return 90
        elif roic >= thresholds['good']:
            return 75
        elif roic >= thresholds['average']:
            return 60
        elif roic >= thresholds['poor']:
            return 40
        else:
            return 20
    
    def _score_debt(self, debt_to_equity: float) -> float:
        """Score debt-to-equity (0-100) - lower is better"""
        thresholds = self.quality_thresholds['debt_to_equity']
        
        if debt_to_equity <= thresholds['excellent']:
            return 90
        elif debt_to_equity <= thresholds['good']:
            return 75
        elif debt_to_equity <= thresholds['average']:
            return 60
        elif debt_to_equity <= thresholds['poor']:
            return 40
        else:
            return 20
    
    def _score_peg(self, peg_ratio: float) -> float:
        """Score PEG ratio (0-100) - lower is better"""
        if peg_ratio <= 0:
            return 50  # Neutral for invalid data
        elif peg_ratio <= 0.5:
            return 90
        elif peg_ratio <= 1.0:
            return 75
        elif peg_ratio <= 1.5:
            return 60
        elif peg_ratio <= 2.0:
            return 40
        else:
            return 20

    def _get_latest_analyst_estimates_payload(self, symbol: str) -> Optional[Any]:
        try:
            with db.get_session() as session:
                analyst_query = """
                SELECT payload
                FROM stock_insights_snapshots
                WHERE stock_symbol = :symbol
                  AND source = 'fmp_analyst_estimates'
                ORDER BY generated_at DESC
                LIMIT 1
                """
                result = session.execute(text(analyst_query), {"symbol": symbol})
                row = result.fetchone()
                payload = row[0] if row else None
                if payload is None:
                    fallback_query = """
                    SELECT payload
                    FROM stock_insights_snapshots
                    WHERE stock_symbol = :symbol
                      AND source = 'fmp_fundamentals'
                    ORDER BY generated_at DESC
                    LIMIT 1
                    """
                    result = session.execute(text(fallback_query), {"symbol": symbol})
                    row = result.fetchone()
                    payload = row[0] if row else None

                if payload is None:
                    return None

                if isinstance(payload, str):
                    try:
                        payload = json.loads(payload)
                    except json.JSONDecodeError:
                        return None

                if isinstance(payload, dict) and "analyst_estimates" in payload:
                    return payload.get("analyst_estimates")

                return payload
        except Exception as e:
            logger.warning(f"Error loading analyst estimates snapshot for {symbol}: {e}")
            return None

    def _extract_forward_eps_series(self, payload: Any) -> List[Tuple[datetime, float, Optional[int]]]:
        if payload is None:
            return []

        records: Any = payload
        if isinstance(payload, dict):
            for key in ("analyst_estimates", "data", "results"):
                if key in payload and isinstance(payload[key], list):
                    records = payload[key]
                    break

        if not isinstance(records, list):
            return []

        series: List[Tuple[datetime, float, Optional[int]]] = []
        for rec in records:
            if not isinstance(rec, dict):
                continue

            dt = self._parse_estimate_date(rec.get("date"))
            if not dt:
                continue

            try:
                eps_avg = float(rec.get("epsAvg"))
            except Exception:
                continue
            if eps_avg <= 0:
                continue

            num_analysts_raw = rec.get("numAnalystsEps")
            try:
                num_analysts = int(num_analysts_raw) if num_analysts_raw is not None else None
            except Exception:
                num_analysts = None

            series.append((dt, eps_avg, num_analysts))

        series.sort(key=lambda x: x[0])
        return series

    def _select_forward_cagr_window(
        self,
        series: List[Tuple[datetime, float, Optional[int]]],
        preferred_years: int = 3,
        as_of: Optional[datetime] = None,
    ) -> Optional[Dict[str, Any]]:
        if len(series) < 2:
            return None
        if as_of is None:
            as_of = datetime.utcnow()

        start_idx: Optional[int] = None
        for i, (dt, _eps, _na) in enumerate(series):
            if dt.date() > as_of.date():
                start_idx = i
                break
        if start_idx is None:
            start_idx = 0

        start_dt, start_eps, start_na = series[start_idx]
        best_any: Optional[Dict[str, Any]] = None
        best_preferred: Optional[Dict[str, Any]] = None

        for j in range(start_idx + 1, len(series)):
            end_dt, end_eps, end_na = series[j]
            years = int(round((end_dt - start_dt).days / 365.25))
            if years < 1:
                continue

            candidate = {
                "start_dt": start_dt,
                "end_dt": end_dt,
                "start_eps": float(start_eps),
                "end_eps": float(end_eps),
                "years": years,
                "start_num_analysts": start_na,
                "end_num_analysts": end_na,
            }
            if best_any is None or years > int(best_any["years"]):
                best_any = candidate
            if years == preferred_years:
                best_preferred = candidate

        if best_preferred is not None:
            best_preferred["window_policy"] = "preferred_3y"
            return best_preferred
        if best_any is not None:
            best_any["window_policy"] = "fallback_longest"
            return best_any
        return None

    def _calculate_peg_rule_of_40_forward_cagr_value(
        self,
        symbol: str,
        fundamentals: FundamentalData,
    ) -> Tuple[Optional[float], Dict[str, Any]]:
        metrics: Dict[str, Any] = {
            "enabled": False,
            "reason_disabled": None,
            "cagr_cap": 0.30,
            "target_pe_cap": 60.0,
        }

        if fundamentals.revenue is not None and float(fundamentals.revenue) > 0:
            if float(fundamentals.revenue) < 100_000_000:
                metrics["reason_disabled"] = "rule_of_40_ineligible_low_revenue"
                return None, metrics
        if fundamentals.gross_margin is not None:
            if float(fundamentals.gross_margin) < 30.0:
                metrics["reason_disabled"] = "rule_of_40_ineligible_low_gross_margin"
                return None, metrics

        payload = self._get_latest_analyst_estimates_payload(symbol)
        if payload is None:
            metrics["reason_disabled"] = "missing_analyst_estimates"
            return None, metrics

        series = self._extract_forward_eps_series(payload)
        if len(series) < 2:
            metrics["reason_disabled"] = "insufficient_forward_eps_points"
            return None, metrics

        analyst_count = None
        try:
            analyst_count = int(series[0][2]) if series and series[0][2] is not None else None
        except Exception:
            analyst_count = None

        window = self._select_forward_cagr_window(series, preferred_years=3)
        if not window:
            metrics["reason_disabled"] = "unable_to_select_window"
            return None, metrics

        try:
            cagr_raw = float(self._compute_cagr(window["start_eps"], window["end_eps"], int(window["years"])))
        except Exception:
            metrics["reason_disabled"] = "cagr_compute_failed"
            return None, metrics

        cagr_used = self._cap_growth(cagr_raw, cap=float(metrics["cagr_cap"]))
        if cagr_used <= 0:
            metrics["reason_disabled"] = "non_positive_forward_cagr"
            metrics.update(
                {
                    "cagr_raw": cagr_raw,
                    "cagr_used": cagr_used,
                    "years": int(window["years"]),
                    "eps_start": float(window["start_eps"]),
                    "eps_end": float(window["end_eps"]),
                    "eps_start_date": window["start_dt"].isoformat() if window.get("start_dt") else None,
                    "eps_end_date": window["end_dt"].isoformat() if window.get("end_dt") else None,
                    "window_policy": window.get("window_policy"),
                }
            )
            return None, metrics

        revenue_growth_pct = float(fundamentals.revenue_yoy_growth or 0.0)
        profit_margin_pct = float(fundamentals.net_margin or 0.0)

        if -1.0 <= revenue_growth_pct <= 1.0:
            revenue_growth_pct *= 100.0
        if -1.0 <= profit_margin_pct <= 1.0:
            profit_margin_pct *= 100.0
        rule_of_40 = self._calculate_rule_of_40(revenue_growth_pct, profit_margin_pct)
        peg_target = float(self._calculate_target_peg_from_rule_of_40(rule_of_40))

        if rule_of_40 < 40:
            peg_target_reason = "rule_of_40_lt_40"
        elif rule_of_40 < 60:
            peg_target_reason = "rule_of_40_40_60"
        elif rule_of_40 < 80:
            peg_target_reason = "rule_of_40_60_80"
        elif rule_of_40 < 100:
            peg_target_reason = "rule_of_40_80_100"
        else:
            peg_target_reason = "rule_of_40_gt_100"

        growth_pct_used = cagr_used * 100.0
        target_pe_raw = peg_target * growth_pct_used
        target_pe_used = self._cap_target_pe(target_pe_raw, cap=60.0)

        forward_eps_estimate = float(window["start_eps"])
        forward_eps_base = forward_eps_estimate
        if fundamentals.eps_forward is not None and float(fundamentals.eps_forward) > 0:
            forward_eps_base = min(float(fundamentals.eps_forward), forward_eps_estimate)
        fair_price = forward_eps_base * target_pe_used

        confidence_penalty = 0.0
        diff_ratio = None
        if analyst_count is not None and analyst_count < 3:
            confidence_penalty += 0.20

        if fundamentals.eps_forward is not None and float(fundamentals.eps_forward) > 0:
            denom = float(fundamentals.eps_forward)
            if denom > 0:
                diff_ratio = abs(float(fundamentals.eps_forward) - float(forward_eps_estimate)) / denom
                if diff_ratio > 0.3:
                    confidence_penalty += 0.15

        current_price = float(fundamentals.current_price or 0.0)
        upside_pct = ((fair_price - current_price) / current_price * 100.0) if current_price > 0 else None

        metrics.update(
            {
                "enabled": True,
                "current_price": current_price,
                "revenue_growth_pct": revenue_growth_pct,
                "profit_margin_pct": profit_margin_pct,
                "rule_of_40": rule_of_40,
                "peg_target": peg_target,
                "peg_target_reason": peg_target_reason,
                "eps_start_date": window["start_dt"].isoformat() if window.get("start_dt") else None,
                "eps_end_date": window["end_dt"].isoformat() if window.get("end_dt") else None,
                "eps_start": float(window["start_eps"]),
                "eps_end": float(window["end_eps"]),
                "years": int(window["years"]),
                "num_analysts_start": window.get("start_num_analysts"),
                "num_analysts_end": window.get("end_num_analysts"),
                "cagr_raw": cagr_raw,
                "cagr_used": cagr_used,
                "growth_pct_used": growth_pct_used,
                "target_pe_raw": target_pe_raw,
                "target_pe_used": target_pe_used,
                "forward_eps_estimate": forward_eps_estimate,
                "forward_eps_base": forward_eps_base,
                "analyst_count_hint": analyst_count,
                "eps_forward": float(fundamentals.eps_forward or 0.0),
                "eps_forward_vs_estimate_diff_ratio": diff_ratio if fundamentals.eps_forward and float(fundamentals.eps_forward) > 0 else None,
                "confidence_penalty": confidence_penalty,
                "fair_price": fair_price,
                "upside_pct": upside_pct,
                "window_policy": window.get("window_policy"),
            }
        )

        return fair_price, metrics
    
    def _create_empty_result(self, symbol: str) -> FairValueResult:
        """Create empty result when data is unavailable"""
        return FairValueResult(
            run_id=None,
            symbol=symbol,
            current_price=0.0,
            fair_value=0.0,
            valuation_metrics={},
            quality_score=0.0,
            individual_valuations={},
            fundamentals={},
            updated_at=datetime.now()
        )
    
    def get_top_undervalued_stocks(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get top undervalued stocks based on fair value analysis"""
        
        try:
            with db.get_session() as session:
                # Get list of stocks with fundamental data
                query = """
                SELECT DISTINCT symbol
                FROM fundamentals_snapshots
                WHERE payload->>'eps' IS NOT NULL
                AND (payload->>'eps')::numeric > 0
                AND as_of_date >= CURRENT_DATE - INTERVAL '7 days'
                LIMIT 100
                """
                
                result = session.execute(text(query))
                symbols = [row[0] for row in result.fetchall()]
                
                # Analyze each symbol
                undervalued_stocks = []
                
                for symbol in symbols:
                    try:
                        result = self.calculate_fair_value(symbol)
                        
                        if result.fair_value > 0 and result.current_price > 0:
                            valuation_ratio = result.current_price / result.fair_value
                            
                            if valuation_ratio < 0.9 and result.quality_score > 50:  # Undervalued + decent quality
                                undervalued_stocks.append({
                                    'symbol': symbol,
                                    'current_price': result.current_price,
                                    'fair_value': result.fair_value,
                                    'valuation_ratio': valuation_ratio,
                                    'undervaluation_pct': (1 - valuation_ratio) * 100,
                                    'quality_score': result.quality_score,
                                    'industry': result.fundamentals.get('industry', 'Unknown')
                                })
                    except Exception:
                        continue
                
                # Sort by undervaluation and quality
                undervalued_stocks.sort(key=lambda x: (x['undervaluation_pct'], x['quality_score']), reverse=True)
                
                return undervalued_stocks[:limit]
                
        except Exception as e:
            logger.error(f"Error getting top undervalued stocks: {e}")
            return []
    
    def get_industry_comparison(self, symbol: str) -> Dict[str, Any]:
        """Get industry comparison for a symbol"""
        
        try:
            result = self.calculate_fair_value(symbol)
            industry = result.fundamentals.get('industry', 'Unknown')
            
            if industry == 'Unknown':
                return {}
            
            # Get industry averages
            industry_bench = self.industry_benchmarks.get(industry, {})
            
            # Calculate comparisons
            comparisons = {
                'pe_vs_industry': result.fundamentals.get('current_pe', 0) - industry_bench.get('avg_pe', 0),
                'peg_vs_industry': result.fundamentals.get('peg_ratio', 0) - industry_bench.get('avg_peg', 0),
                'growth_vs_industry': result.fundamentals.get('eps_yoy_growth', 0) - industry_bench.get('avg_growth', 0),
                'margin_vs_industry': result.fundamentals.get('gross_margin', 0) - industry_bench.get('avg_margin', 0),
                'roic_vs_industry': result.fundamentals.get('roic', 0) - industry_bench.get('avg_roic', 0),
                'debt_vs_industry': result.fundamentals.get('debt_to_equity', 0) - industry_bench.get('avg_debt_equity', 0)
            }
            
            return {
                'industry': industry,
                'benchmarks': industry_bench,
                'comparisons': comparisons,
                'symbol_metrics': {
                    'pe': result.fundamentals.get('current_pe', 0),
                    'peg': result.fundamentals.get('peg_ratio', 0),
                    'growth': result.fundamentals.get('eps_yoy_growth', 0),
                    'margin': result.fundamentals.get('gross_margin', 0),
                    'roic': result.fundamentals.get('roic', 0),
                    'debt_to_equity': result.fundamentals.get('debt_to_equity', 0)
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting industry comparison for {symbol}: {e}")
            return {}
