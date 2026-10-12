"""Global-risk context — geopolitical/macro stress as the market sees it.

Two honest channels, no prediction theater:

  defensive_flows  — money rotating into GLD/TLT/UUP/USO/XLU while
                     equities sag IS the geopolitical tell; it shows up
                     in the tape before headlines explain it. Oil up +
                     gold up + dollar bid = supply/war stress pricing.

  headline_risk    — FMP general-news scan for crisis vocabulary
                     (war, tariffs, sanctions, default, shutdown…),
                     weighted and capped. This reads the news the world
                     is writing; it cannot see the event nobody printed.

Both persist to engine_weights['geo:context'] from the momentum job —
readers stay free.
"""
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

_DEFENSIVE = {"GLD": "gold", "TLT": "long treasuries", "UUP": "dollar",
              "USO": "oil", "XLU": "utilities"}
_CRISIS_TERMS = {
    "war": 3, "invasion": 3, "missile": 3, "airstrike": 3,
    "conflict": 2, "sanctions": 2, "embargo": 3, "tariff": 2,
    "trade war": 3, "default": 3, "shutdown": 1, "crisis": 2,
    "nuclear": 3, "ceasefire": -1, "recession": 2, "emergency": 2,
    "martial": 3, "strike on": 3, "evacuat": 2, "terror": 3,
}


def defensive_flows() -> dict[str, Any]:
    """5d/20d defensive-asset relative strength vs SPY."""
    try:
        from app.market_data import bars as bars_mod
        books = bars_mod.load(list(_DEFENSIVE) + ["SPY"], days=30)
    except Exception as exc:
        logger.debug("defensive flows fetch: %s", exc)
        return {}
    spy = books.get("SPY") or []
    if len(spy) < 22:
        return {}
    s5 = spy[-1].close / spy[-6].close - 1
    s20 = spy[-1].close / spy[-22].close - 1
    legs, score = [], 0.0
    for sym, name in _DEFENSIVE.items():
        b = books.get(sym) or []
        if len(b) < 22:
            continue
        d5 = (b[-1].close / b[-6].close - 1) - s5       # RS vs SPY
        d20 = (b[-1].close / b[-22].close - 1) - s20
        hot = d5 > 0.01 or (d5 > 0.003 and d20 > 0.01)
        legs.append({"etf": sym, "name": name,
                     "rs_5d": round(d5 * 100, 2),
                     "rs_20d": round(d20 * 100, 2),
                     "hot": bool(hot)})
        score += (2.0 if hot else 0) + (1.0 if d5 > 0.005 else 0)
        if sym == "USO" and d5 > 0.03:                   # oil spike
            score += 1.5                               # = supply shock
    flow = ("risk-off" if score >= 6 else
            "cautious" if score >= 3 else "normal")
    return {"flow": flow, "score": round(score, 1), "legs": legs,
            "spy_5d": round(s5 * 100, 2),
            "spy_20d": round(s20 * 100, 2)}


def headline_risk(limit: int = 60) -> dict[str, Any]:
    """FMP general-news crisis scan → bounded 0-100 score + drivers."""
    try:
        from app.providers.financial_modeling_prep.client import (
            EnhancedFMPClient)
        news = EnhancedFMPClient.from_settings().get_general_news(
            limit=limit) or []
    except Exception as exc:
        logger.debug("headline scan: %s", exc)
        return {}
    raw, hits = 0.0, []
    for a in news:
        text = f"{a.get('title', '')} {a.get('text', '')[:300]}".lower()
        w = sum(wt for term, wt in _CRISIS_TERMS.items() if term in text)
        if w >= 3:                          # demand real crisis language,
            raw += min(w, 4)                # not incidental 'crisis' mentions
            hits.append(a.get("title", "")[:90])
    score = min(100, round(raw * 1.5))                # saturation needs ~15
    return {"geo_risk": score, "n_flagged": len(hits),
            "n_scanned": len(news),
            "drivers": hits[:5]}


def refresh() -> dict[str, Any]:
    """The momentum job's call: flows + headlines → engine_weights."""
    from app.database import db
    out = {"defensive": defensive_flows(), **headline_risk(),
           "as_of": __import__("datetime").datetime.now(
               __import__("datetime").timezone.utc).isoformat(
               timespec="seconds")}
    try:                                        # causal event chains
        from app.signals import causal_map, book_risk
        out["causal"] = causal_map.evaluate(out, book=book_risk.read())
    except Exception:
        pass
    if not out.get("defensive") and out.get("geo_risk") is None:
        return out
    try:
        db.execute_query(
            "INSERT INTO engine_weights(key, value, updated_at)"
            " VALUES ('geo:context', CAST(:v AS jsonb), now())"
            " ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value,"
            "   updated_at = now()",
            {"v": json.dumps(out)})
    except Exception as exc:
        logger.debug("geo persist: %s", exc)
    return out


def read() -> dict[str, Any]:
    from app.database import db
    rows = db.execute_query(
        "SELECT value FROM engine_weights WHERE key='geo:context'")
    if not rows:
        return {}
    v = rows[0]["value"]
    if isinstance(v, str):
        try:
            return json.loads(v)
        except Exception:
            return {}
    return v or {}
