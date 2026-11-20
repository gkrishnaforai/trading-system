"""Lifecycle classifier — business maturity, not market cap.

Deterministic stage assignment from fundamentals: profitability,
growth, cash generation, payout behavior, margin cyclicality.

Returns stage + evidence + classification_confidence — kept separate
from valuation_confidence (input/method reliability) and
market_expectation_confidence (consensus quality): a company can
have a crystal-clear lifecycle and still have an uncertain FV
because growth duration is hard to estimate (PLTR-class).

Stages:
  1 early/pre-profit   — losses or negative FCF
  2 scaling            — high growth, thin/negative profitability
  3 profitable growth  — positive EPS+FCF and still growing fast
  4 mature cash-gen    — growth slowing, strong FCF, payout/buybacks
  5 cyclical/distress  — volatile margins or declining revenue
"""

from typing import Any, Dict

from app.database import db


def _num(scalars: Dict[str, Any], *keys: str) -> float | None:
    for k in keys:
        v = scalars.get(k)
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                continue
    return None


def _margin_stddev(symbol: str) -> float | None:
    """8-quarter net-margin volatility — the cyclicality tell."""
    try:
        rows = db.execute_query(
            "SELECT (net_income / NULLIF(revenue, 0)) AS m"
            " FROM fundamental_quarterly WHERE symbol=:s"
            " AND revenue IS NOT NULL AND net_income IS NOT NULL"
            " ORDER BY period_end DESC LIMIT 8",
            {"s": symbol})
    except Exception:
        return None
    xs = [float(r["m"]) for r in rows if r.get("m") is not None]
    if len(xs) < 4:
        return None
    mu = sum(xs) / len(xs)
    return (sum((x - mu) ** 2 for x in xs) / len(xs)) ** 0.5


def classify(symbol: str, scalars: Dict[str, Any]) -> Dict[str, Any]:
    net_margin = _num(scalars, "net_margin", "net_margin_ttm",
                      "profit_margin_ttm")
    fcf = _num(scalars, "fcf_ttm", "free_cash_flow_ttm", "fcf")
    rev_g = _num(scalars, "revenue_growth", "revenue_growth_yoy",
                 "rev_growth_ttm", "revenue_yoy_growth")
    eps_g = _num(scalars, "eps_growth", "eps_yoy_growth",
                 "eps_growth_yoy", "eps_growth_ttm", "forward_growth")
    div_yield = _num(scalars, "dividend_yield", "dividends_ttm")
    buybacks = _num(scalars, "buybacks_ttm", "share_buyback_ttm")
    m_sd = _margin_stddev(symbol)

    ev = []
    # stage 5 first — cyclicality/decline overrides growth readings
    if (m_sd is not None and m_sd > 0.04) or (
            rev_g is not None and rev_g < -0.10):
        stage = 5
        if m_sd is not None and m_sd > 0.04:
            ev.append(f"margin volatility {m_sd:.0%} over 8q")
        if rev_g is not None and rev_g < -0.10:
            ev.append(f"revenue declining {rev_g:.0%}")
    elif (net_margin is not None and net_margin <= 0) or \
            (fcf is not None and fcf < 0):
        stage = 1
        if net_margin is not None:
            ev.append(f"net margin {net_margin:.0%}")
        if fcf is not None and fcf < 0:
            ev.append("negative FCF")
    elif (rev_g is not None and rev_g > 0.25) or \
            (eps_g is not None and eps_g > 0.25):
        # high growth — scaling vs profitable splits on margin+FCF
        if (net_margin is not None and net_margin > 0.08
                and fcf is not None and fcf > 0):
            stage = 3
            ev.append(f"growth {rev_g or eps_g:.0%} with positive "
                      "margin + FCF")
        else:
            stage = 2
            ev.append("high growth, thin/negative profitability")
    elif fcf is not None and fcf > 0 and (
            div_yield is not None or buybacks is not None
            or (rev_g is not None and rev_g < 0.15)):
        stage = 4
        ev.append("cash-generative: FCF + payout or slowing growth")
    elif fcf is not None and fcf > 0:
        stage = 3
        ev.append("profitable and growing")
    else:
        stage = 2
        ev.append("insufficient maturity evidence — default scaling")

    # confidence = signal coverage, not a judgment call
    n = sum(1 for v in (net_margin, fcf, rev_g, eps_g, m_sd)
            if v is not None)
    conf = "high" if n >= 4 else "medium" if n >= 2 else "low"
    return {"stage": stage, "evidence": ev, "confidence": conf,
            "signals": {"net_margin": net_margin, "fcf_ttm": fcf,
                        "rev_growth": rev_g, "eps_growth": eps_g,
                        "margin_stddev": m_sd}}


def market_expectation_confidence(
        scalars: Dict[str, Any]) -> Dict[str, Any]:
    """How reliable is the external consensus benchmark — analyst
    coverage and estimate freshness, NOT the engine's own view."""
    n = scalars.get("analyst_count")
    try:
        n = int(n) if n is not None else None
    except (TypeError, ValueError):
        n = None
    drivers = []
    if n is None or n == 0:
        score = "low"
        drivers.append("no analyst coverage")
    elif n < 5:
        score = "low"
        drivers.append(f"thin coverage ({n} analysts)")
    elif n < 15:
        score = "medium"
        drivers.append(f"moderate coverage ({n} analysts)")
    else:
        score = "high"
        drivers.append(f"broad coverage ({n} analysts)")
    return {"score": score, "drivers": drivers,
            "analyst_count": n}
