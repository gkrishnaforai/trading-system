"""Income & swing plan composer — today's actionable plan per lane.

Reads the already-computed engine layers (posture gate, daily calls/
puts, readiness lanes, IV-vs-HV coverage, holdings, thesis flags) and
binds each suggestion to a trade_plans draft so one click opens a
journaled plan. Advisory: suggests levels and use-case; the human
enters and exits the trade.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Optional

_TOP = 3


def _f(v) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except Exception:
        return None


def _posture() -> dict:
    from app.signals import posture
    try:
        return posture.current()
    except Exception:
        return {"posture": "unknown", "new_longs": True}


def _thesis_map() -> dict:
    from app.database import db
    try:
        return {r["symbol"]: dict(r) for r in db.execute_query(
            "SELECT symbol, status, status_dir FROM symbol_thesis")}
    except Exception:
        return {}


def _iv_map() -> dict:
    from app.database import db
    try:
        return {r["symbol"]: dict(r) for r in db.execute_query(
            "SELECT DISTINCT ON (symbol) symbol, atm_iv, hv20, iv_hv"
            " FROM iv_snapshots ORDER BY symbol, as_of DESC")}
    except Exception:
        return {}


def _earnings_in(row: dict) -> Optional[int]:
    ne = row.get("next_earnings_date")
    if not ne:
        return None
    d = ne.date() if hasattr(ne, "date") else ne
    try:
        return (d - date.today()).days
    except Exception:
        return None


def _draft(sym: str, uc: str, entry: Optional[float] = None) -> dict:
    """trade_plans.suggest() bound for one-click POST /trade-plans."""
    from app.signals import trade_plans
    try:
        return trade_plans.suggest(sym, uc, entry)
    except Exception:
        return {"symbol": sym, "use_case": uc, "entry_px": entry}


# ------------------------------- lanes --------------------------------------

def _swing() -> list[dict]:
    """Today's daily_calls picks — the engine's qualified swing names."""
    from app.database import db
    rows = db.execute_query(
        "SELECT c.symbol, s.sector, c.rank, c.score, c.entry_px,"
        " c.stop_px, c.target_px, c.rr, c.state, c.dip_phase,"
        " c.evidence FROM daily_calls c"
        " LEFT JOIN stocks s ON s.symbol=c.symbol"
        " WHERE c.call_date=(SELECT max(call_date) FROM daily_calls)"
        " ORDER BY c.rank")
    return [{"symbol": r["symbol"], "sector": r["sector"],
             "instrument": "shares",
             "use_case": "swing", "score": r["score"],
             "entry_px": _f(r["entry_px"]), "stop_px": _f(r["stop_px"]),
             "target_px": _f(r["target_px"]), "rr": _f(r["rr"]),
             "state": r["state"], "dip_phase": r["dip_phase"],
             "evidence": r["evidence"] if isinstance(r["evidence"], list)
             else [],
             "plan": _draft(r["symbol"], "swing", _f(r["entry_px"]))}
            for r in rows]


def _leaps(use_case: str, th: dict) -> list[dict]:
    """Readiness lane top names (ready first, rank-ordered) — the
    deep-ITM long-dated candidates."""
    from app.database import db
    rows = db.execute_query(
        "SELECT e.symbol, s.sector, e.state, e.rank, e.mom, e.fund"
        " FROM readiness_evals e"
        " LEFT JOIN stocks s ON s.symbol=e.symbol"
        " WHERE e.use_case=:u"
        " AND e.as_of=(SELECT max(as_of) FROM readiness_evals"
        "            WHERE use_case=:u)"
        " AND e.state IN ('ready','close') ORDER BY e.rank DESC"
        " LIMIT :n",
        {"u": use_case, "n": 40})
    out = []
    for r in rows:
        d = _draft(r["symbol"], use_case)
        t = th.get(r["symbol"]) or {}
        out.append({"symbol": r["symbol"], "sector": r["sector"],
                    "instrument": "LEAP "
                    + ("call" if use_case == "leap_call" else "put"),
                    "use_case": use_case, "lane_state": r["state"],
                    "rank": _f(r["rank"]),
                    "mom": r["mom"], "fund": r["fund"],
                    "thesis": t.get("status"),
                    "thesis_dir": t.get("status_dir"),
                    "entry_px": d.get("spot"),
                    "stop_px": d.get("stop_px"), "target_px":
                        d.get("target1_px"),
                    "spot": d.get("spot"), "plan": d})
    return out


def _csp(funds: Optional[float], th: dict, iv: dict) -> list[dict]:
    """Cash-secured puts — sell a put at structure support on a
    fundamentally-sound, premium-rich name. Strike = the level you'd
    happily own at; income if it holds, assignment at support if not.
    iv_hv >= 1.0 means options are paying above realized vol."""
    from app.database import db
    import json
    rows = db.execute_query(
        "SELECT s.symbol, s.company_name, s.sector,"
        " s.fundamental_state,"
        " s.momentum_state, s.momentum_detail, s.next_earnings_date,"
        " px.close, fw.fcf_margin, fw.rev_growth"
        " FROM stocks s"
        " JOIN LATERAL (SELECT close FROM daily_bars b"
        "              WHERE b.symbol=s.symbol"
        "              ORDER BY b.date DESC LIMIT 1) px ON true"
        " LEFT JOIN symbol_flywheel fw ON fw.symbol=s.symbol"
        " WHERE s.momentum_state IN"
        "  ('basing','stabilizing','pullback','uptrend','recovery')"
        " AND s.fundamental_state IN ('accelerating','growing')")
    cands = []
    for r in rows:
        sym = r["symbol"]
        v = iv.get(sym) or {}
        iv_hv = _f(v.get("iv_hv"))
        if iv_hv is None or iv_hv < 1.0:
            continue                          # premium not paying
        t = th.get(sym) or {}
        if t.get("status") in ("broken", "deteriorating"):
            continue                          # never sell puts on a
        # broken thesis — assignment risk is the point of the trade
        ed = _earnings_in(r)
        det = r.get("momentum_detail") or {}
        if isinstance(det, str):
            det = json.loads(det)
        sw = det.get("swing") or {}
        px = _f(r["close"])
        if not px:
            continue
        atr = _f(det.get("atr_pct")) or 0.03
        strike = None
        for k in ("swing_low", "prior_low"):
            lv = _f(sw.get(k))
            if lv and lv < px * 0.985:
                strike = lv
                break
        if strike is None:
            strike = px * (1 - 1.5 * atr)
        strike = round(strike * 2) / 2        # quarter-dollar-ish grid
        collat = strike * 100
        contracts = int(funds // collat) if funds else None
        cands.append({
            "symbol": sym, "name": r.get("company_name"),
            "sector": r["sector"],
            "instrument": "cash-secured put", "use_case": "csp",
            "spot": px, "strike": strike, "collateral": collat,
            "contracts": contracts,
            "dte": "30-45d", "iv_hv": round(iv_hv, 2),
            "entry_px": strike,
            "exit_rule": ("close at 50% decay or roll if px < "
                          f"{strike}"),
            "atm_iv": _f(v.get("atm_iv")),
            "fund": r["fundamental_state"], "mom": r["momentum_state"],
            "thesis": t.get("status"), "thesis_dir": t.get("status_dir"),
            "fcf_margin": _f(r.get("fcf_margin")),
            "earn_days": ed,
            "flags": ([f"earnings in {ed}d — IV event inside window"]
                      if ed is not None and 0 <= ed <= 35 else []),
            "plan": _draft(sym, "csp", strike)})
    cands.sort(key=lambda c: -(c["iv_hv"] or 0))
    return cands


def _covered_calls(th: dict, iv: dict) -> list[dict]:
    """Covered calls on held lots — sell calls into strength on names
    you'd keep anyway. Strike above spot near confirm/structure;
    flags fire when the underlying thesis is breaking (sell-the-stock
    territory, not premium territory)."""
    from app.database import db
    import json
    rows = db.execute_query(
        "SELECT DISTINCT ON (s.symbol) s.symbol, s.company_name,"
        " s.sector,"
        " s.fundamental_state, s.momentum_state, s.momentum_detail,"
        " s.next_earnings_date, pp.quantity, pp.avg_price, px.close"
        " FROM portfolio_positions pp"
        " JOIN stocks s ON s.id = pp.stock_id"
        " JOIN LATERAL (SELECT close FROM daily_bars b"
        "              WHERE b.symbol=s.symbol"
        "              ORDER BY b.date DESC LIMIT 1) px ON true"
        " WHERE pp.quantity >= 100"
        " ORDER BY s.symbol, pp.opened_at")
    out = []
    for r in rows:
        sym = r["symbol"]
        v = iv.get(sym) or {}
        iv_hv = _f(v.get("iv_hv"))
        px = _f(r["close"])
        if not px:
            continue
        det = r.get("momentum_detail") or {}
        if isinstance(det, str):
            det = json.loads(det)
        sw = det.get("swing") or {}
        strike = max(px * 1.06, _f(sw.get("confirm_level")) or 0)
        strike = round(strike * 2) / 2
        ed = _earnings_in(r)
        t = th.get(sym) or {}
        flags = []
        if r["fundamental_state"] in ("deteriorating", "declining",
                                    "pressured"):
            flags.append("fundamentals deteriorating — a call cap on a "
                         "broken name isn't income, it's delay; "
                         "consider exit instead")
        if t.get("status") in ("broken", "deteriorating"):
            flags.append(f"thesis {t['status']} — selling premium "
                         "doesn't fix a broken thesis")
        if ed is not None and 0 <= ed <= 35:
            flags.append(f"earnings in {ed}d — assignment risk around "
                         "the print")
        if iv_hv is not None and iv_hv < 0.9:
            flags.append(f"iv/hv {iv_hv:.2f} — premium thin, barely "
                         "pays for the cap")
        out.append({
            "symbol": sym, "name": r.get("company_name"),
            "sector": r["sector"],
            "instrument": "covered call", "use_case": "covered_call",
            "spot": px, "strike": strike,
            "entry_px": strike,
            "exit_rule": ("hold shares under "
                          f"{strike}; roll or let go above"),
            "shares": int(_f(r["quantity"]) or 0),
            "contracts": int((_f(r["quantity"]) or 0) // 100),
            "dte": "30-45d", "iv_hv": round(iv_hv, 2) if iv_hv else None,
            "fund": r["fundamental_state"], "mom": r["momentum_state"],
            "thesis": t.get("status"), "thesis_dir": t.get("status_dir"),
            "earn_days": ed, "flags": flags,
            "plan": _draft(sym, "covered_call", px)})
    out.sort(key=lambda c: (
        bool(c["flags"]), -(c["iv_hv"] or 0)))
    return out


_LANE_KEYS = ("swing", "csp", "covered_call", "leap_call", "leap_put")


def _by_sector(lanes: dict) -> list[dict]:
    """Sector × lane matrix — top 3 candidates per sector per lane.
    Sectors with no qualifying picks in any lane are omitted; lane
    slots inside a present sector stay blank (frontend renders —)."""
    sectors: dict[str, dict] = {}
    for key in _LANE_KEYS:
        for item in lanes.get(key) or []:
            sec = item.get("sector") or "Other"
            slot = sectors.setdefault(sec, {k: [] for k in _LANE_KEYS})
            if len(slot[key]) < _TOP:
                slot[key].append(item)
    out = [{"sector": sec, "lanes": slot}
           for sec, slot in sectors.items()
           if any(slot.values())]
    out.sort(key=lambda s: -(max(len(v) for v in s["lanes"].values())))
    return out


def today(funds: Optional[float] = None) -> dict[str, Any]:
    """The full daily plan — posture gate + per-lane suggestions."""
    pos = _posture()
    th, iv = _thesis_map(), _iv_map()
    lanes = {
        "swing": _swing() if pos.get("new_longs", True) else [],
        "leap_call": _leaps("leap_call", th)
        if pos.get("new_longs", True) else [],
        "leap_put": _leaps("leap_put", th),
        "csp": _csp(funds, th, iv)
        if pos.get("new_longs", True) else [],
        "covered_call": _covered_calls(th, iv),
    }
    return {"as_of": str(date.today()), "posture": pos,
            "funds": funds, "lanes": lanes,
            "sectors": _by_sector(lanes),
            "note": ("advisory — levels are engine-suggested; premium "
                     "isn't modeled (no options chain feed). Verify "
                     "bid/ask at the broker before entering.")}
