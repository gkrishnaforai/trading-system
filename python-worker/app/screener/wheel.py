"""Wheel tracker — manages manually logged cash-secured puts / covered calls
and computes the daily management read against the latest screen-run price
(no extra provider calls — reuses the same rows the regime board shows).

Status rules (the wheel playbook):
  csp  price <= strike        → ITM — assignment imminent
       price <  strike*1.05   → threatened — decide: roll or accept
  cc   price >= strike        → ITM — call-away likely
       price >  strike*0.97   → threatened — decide: let go or roll up
  else safe.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Optional

logger = logging.getLogger(__name__)

THREAT_PCT = 0.05   # within 5% of strike = decide zone
CC_THREAT_PCT = 0.03


def _latest_prices() -> dict[str, float]:
    """symbol → latest screen-run price. One query, zero provider calls."""
    try:
        from app.database import db
        run = db.execute_query(
            "SELECT results FROM screen_runs ORDER BY ran_at DESC LIMIT 1")
        return {r["symbol"]: r["price"] for r in (run[0].get("results") or [])
                if r.get("price")}
    except Exception as exc:
        logger.debug("wheel price lookup failed: %s", exc)
        return {}


def _status(kind: str, strike: float, price: Optional[float]) -> tuple[str, str]:
    if price is None:
        return "⚪", "no price in latest scan"
    if kind == "csp":
        if price <= strike:
            return "🔴 ITM", "below strike — assignment imminent at expiry"
        if price < strike * (1 + THREAT_PCT):
            return "🟡 threatened", "within 5% of strike — roll or accept"
        return "🟢 safe", "premium decaying as designed"
    # covered call
    if price >= strike:
        return "🔴 ITM", "above strike — expect call-away at expiry"
    if price > strike * (1 - CC_THREAT_PCT):
        return "🟡 threatened", "near strike — let go or roll up/out"
    return "🟢 safe", "premium decaying as designed"


def add_position(symbol: str, kind: str, strike: float, expiry: str,
                 contracts: int = 1, premium: Optional[float] = None,
                 notes: Optional[str] = None) -> dict[str, Any]:
    from app.database import db
    if kind not in ("csp", "cc"):
        return {"error": "kind must be csp or cc"}
    db.execute_update(
        """INSERT INTO wheel_positions
           (symbol, kind, strike, expiry, contracts, premium, notes)
           VALUES (:s, :k, :st, :e, :c, :p, :n)""",
        {"s": symbol.upper(), "k": kind, "st": strike, "e": expiry,
         "c": contracts, "p": premium, "n": notes})
    return {"status": "added", "symbol": symbol.upper()}


def close_position(position_id: int, status: str) -> dict[str, Any]:
    from app.database import db
    if status not in ("assigned", "called", "closed", "expired"):
        return {"error": "status must be assigned/called/closed/expired"}
    db.execute_update(
        """UPDATE wheel_positions SET status=:s, closed_at=now(),
           updated_at=now() WHERE id=:i""",
        {"s": status, "i": position_id})
    return {"status": status, "id": position_id}


def list_positions(include_closed: bool = False) -> dict[str, Any]:
    from app.database import db
    q = ("SELECT * FROM wheel_positions"
         + ("" if include_closed else " WHERE status='open'")
         + " ORDER BY status='open' DESC, expiry")
    rows = db.execute_query(q)
    prices = _latest_prices()
    out = []
    for r in rows:
        r = dict(r)
        strike = float(r["strike"])
        price = prices.get(r["symbol"])
        icon, note = _status(r["kind"], strike, price)
        premium = float(r["premium"]) if r.get("premium") is not None else None
        be = strike - premium if r["kind"] == "csp" and premium else (
            strike + premium if premium else strike)
        r.update({
            "strike": strike, "price": price,
            "dist_pct": round((price / strike - 1) * 100, 1)
                        if price else None,
            "status_icon": icon, "status_note": note,
            "premium": premium, "breakeven": round(be, 2),
            "dte": (r["expiry"] - date.today()).days
                   if r.get("expiry") else None,
            "expiry": str(r.get("expiry") or ""),
        })
        out.append(r)
    return {"positions": out}
