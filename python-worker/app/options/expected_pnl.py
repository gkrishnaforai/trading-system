"""Expected option P&L — Engine C lite.

The key idea from the design review: a call's attractiveness is NOT
the stock's direction — it's Σ p_i × (option value_i − premium),
where each scenario reprices the contract at expiry under that
scenario's stock price AND implied volatility.

Scenario distribution comes from fair_value_v2 (bear/base/bull FV
probs, regime-tilted). Stock targets scale the FV legs to the
expiry horizon. IV assumption per scenario: bear → current IV × 1.4,
base → ×1.0, bull → ×0.85 (crush on rally is typical).

Output: expected P&L per contract, probability of profit, expected
return %, worst case (premium), breakeven — plus the per-scenario
reprice table so the math is auditable.
"""

import math
from datetime import date
from typing import Any

from app.database import db


def _bs_value(S: float, K: float, T: float, r: float,
              iv: float) -> float:
    """Black-Scholes call value. Matches leaps.py conventions."""
    if S <= 0 or K <= 0 or T <= 0 or not iv or iv <= 0.001 or iv > 5:
        return 0.0
    ncdf = lambda x: (1 + math.erf(x / math.sqrt(2))) / 2
    sq = iv * math.sqrt(T)
    d1 = (math.log(S / K) + (r + iv * iv / 2) * T) / sq
    d2 = d1 - sq
    return max(0.0, S * ncdf(d1) - K * math.exp(-r * T) * ncdf(d2))


def _fv_run(sym: str) -> dict | None:
    rows = db.execute_query(
        "SELECT symbol, fair_value, expected_fair_value,"
        "       bear_fair_value, bull_fair_value, spot_at_run,"
        "       method_results, scenario_probs"
        " FROM fair_value_v2_runs WHERE symbol=:s"
        " ORDER BY as_of DESC LIMIT 1", {"s": sym.upper()})
    return rows[0] if rows else None


def expected_call_pnl(sym: str, strike: float, expiry: str,
                      premium: float, iv: float | None = None,
                      risk_free: float = 0.043) -> dict[str, Any]:
    """Expected P&L for a long call under the FV scenario distribution.

    Contract params are supplied by the caller (from the option chain
    quote the user is evaluating) — no live-chain dependency."""
    run = _fv_run(sym)
    if run is None:
        return {"error": f"no fair_value_v2 run for {sym.upper()}"}
    spot = float(run["spot_at_run"]) if run.get("spot_at_run") else None
    if not spot:
        spot_row = db.execute_query(
            "SELECT close FROM daily_bars WHERE symbol=:s"
            " ORDER BY date DESC LIMIT 1", {"s": sym.upper()})
        spot = float(spot_row[0]["close"]) if spot_row else None
    if not spot:
        return {"error": "no spot price"}
    try:
        exp_d = date.fromisoformat(str(expiry)[:10])
    except ValueError:
        return {"error": "expiry must be YYYY-MM-DD"}
    T = (exp_d - date.today()).days / 365.0
    if T <= 0:
        return {"error": "expiry must be in the future"}
    iv0 = iv if iv and 0.01 < iv < 5 else 0.35

    probs = run.get("scenario_probs") or {"bear": .25, "base": .5, "bull": .25}
    if isinstance(probs, str):
        import json
        probs = json.loads(probs)
    targets = {}
    for k, col in (("bear", "bear_fair_value"),
                   ("base", "expected_fair_value"),
                   ("bull", "bull_fair_value")):
        v = run.get(col)
        if v is not None:
            targets[k] = float(v)
    if not targets:
        return {"error": "FV run has no scenario fair values"}

    iv_mult = {"bear": 1.4, "base": 1.0, "bull": 0.85}
    # scale FV targets (a 12m anchor) to the expiry horizon
    scale = min(1.0, T)
    scenarios = []
    exp_pnl = prob_profit = 0.0
    for k, tgt in targets.items():
        p = float(probs.get(k, probs.get("base", 0.5)))
        s_t = spot + (tgt - spot) * scale
        iv_t = iv0 * iv_mult.get(k, 1.0)
        val = _bs_value(s_t, strike, T, risk_free, iv_t)
        pnl = val - premium
        exp_pnl += p * pnl
        if pnl > 0:
            prob_profit += p
        scenarios.append({"scenario": k, "prob": round(p, 2),
                          "stock_at_expiry": round(s_t, 2),
                          "iv_assumed": round(iv_t, 2),
                          "call_value": round(val, 2),
                          "pnl": round(pnl, 2)})
    if premium <= 0:
        return {"error": "premium must be positive"}
    # breakeven stock price at expiry
    be = strike + premium
    return {
        "symbol": sym.upper(), "strike": strike,
        "expiry": str(exp_d), "premium": premium,
        "iv_entry": iv0, "spot": round(spot, 2),
        "expected_pnl": round(exp_pnl, 2),
        "expected_return_pct": round(exp_pnl / premium * 100, 1),
        "prob_profit": round(prob_profit, 2),
        "max_loss": round(-premium, 2),
        "breakeven_stock": round(be, 2),
        "breakeven_move_pct": round((be / spot - 1) * 100, 1),
        "scenarios": scenarios,
        "method": ("Σ p_i × (BS(S_i, IV_i) − premium) over FV-v2 "
                   "scenario distribution; IV bear×1.4/bull×0.85"),
    }
