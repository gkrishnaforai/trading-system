"""Deterministic derivation of fundamental fields from financial statements."""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def _value(row: Dict[str, Any], *keys: str) -> Optional[float]:
    for key in keys:
        value = row.get(key)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
    return None


def _sort(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(rows, key=lambda row: str(row.get("date") or row.get("fiscalDateEnding") or ""), reverse=True)


def derive_statement_fields(income: List[Dict[str, Any]], cash_flow: List[Dict[str, Any]]) -> Dict[str, Any]:
    latest = _sort([row for row in income if isinstance(row, dict)])
    cash = _sort([row for row in cash_flow if isinstance(row, dict)])
    current = latest[0] if latest else {}
    prior = latest[1] if len(latest) > 1 else {}

    revenue = _value(current, "revenue", "sales", "totalRevenue")
    prior_revenue = _value(prior, "revenue", "sales", "totalRevenue")
    net_income = _value(current, "netIncome", "netIncomeApplicableToCommonShares")
    prior_net_income = _value(prior, "netIncome", "netIncomeApplicableToCommonShares")
    eps = _value(current, "eps", "epsdiluted", "epsDiluted", "dilutedEPS")
    prior_eps = _value(prior, "eps", "epsdiluted", "epsDiluted", "dilutedEPS")
    latest_cash = cash[0] if cash else {}
    operating_cash_flow = _value(latest_cash, "operatingCashFlow", "netCashProvidedByOperatingActivities")
    free_cash_flow = _value(latest_cash, "freeCashFlow")
    if free_cash_flow is None:
        capex = _value(latest_cash, "capitalExpenditure", "capitalExpenditures")
        if operating_cash_flow is not None and capex is not None:
            free_cash_flow = operating_cash_flow + capex if capex < 0 else operating_cash_flow - capex

    def growth(current_value: Optional[float], prior_value: Optional[float]) -> Optional[float]:
        if current_value is None or prior_value in (None, 0):
            return None
        return (current_value - prior_value) / abs(prior_value)

    values = {
        "revenue": revenue,
        "revenue_growth": growth(revenue, prior_revenue),
        "net_income": net_income,
        "earnings_growth": growth(net_income, prior_net_income),
        "eps": eps,
        "eps_growth": growth(eps, prior_eps),
        "operating_cash_flow": operating_cash_flow,
        "free_cash_flow": free_cash_flow,
        "statement_periods": len(latest),
    }
    required = {
        "revenue_growth": values["revenue_growth"],
        "earnings_growth": values["earnings_growth"],
        "operating_cash_flow": operating_cash_flow,
        "free_cash_flow": free_cash_flow,
    }
    missing = [name for name, value in required.items() if value is None]
    values["coverage"] = round((len(required) - len(missing)) / len(required), 3)
    values["missing_fields"] = missing
    values["derivation"] = "annual_statement_yoy"
    return values
