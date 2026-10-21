"""read_through — basket-level repricing detection in extended hours.

The 2026-10-20 case: SMCI raised FQ1 revenue guide ~+28% above
consensus and Musk's SPCX call talked up "insatiable" compute demand —
APLD/CRWV/IREN/NBIS/DELL/HPE/HUT/CORZ all repriced +3-6% after hours
BEFORE any regular-session bar existed. Daily bars never see it until
the next open; by then the move is half over.

This detector runs after close / pre-open: pulls extended-hours prices
(yfinance fast_info) for every theme-book member, and when a whole
book reprices together — ≥3 members ≥3% the same direction, or a
bellwether ≥6% — it journals a read_through_evals row the morning
regime reads as evidence.

Deterministic; advisory only.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# A book repriced "together" when any of these fire
_MIN_MOVERS = 3            # ≥3 members same direction
_MIN_MOVE_PCT = 3.0        # each moved ≥3%
_MIN_BELLWETHER = 6.0      # or a single member ≥6%
_MIN_BREADTH = 0.40        # or ≥40% of the book ≥2% same way


def _books() -> dict[str, list[str]]:
    """Theme/custom books → member symbols. Read-through is a basket
    phenomenon, so books (AIInfra, GridTech, Crypto, futureStocks…)
    are the natural unit."""
    from app.database import db
    rows = db.execute_query(
        "SELECT p.name book, s.symbol FROM portfolios p"
        " JOIN portfolio_positions pp ON pp.portfolio_id=p.id"
        "   AND pp.quantity>0"
        " JOIN stocks s ON s.id=pp.stock_id"
        " WHERE p.is_active")
    out: dict[str, list[str]] = {}
    for r in rows:
        out.setdefault(r["book"], []).append(r["symbol"])
    return {k: v for k, v in out.items() if len(v) >= 3}


def _session() -> str:
    """ET wall clock → which tape last_price is printing on."""
    from datetime import datetime
    try:
        from zoneinfo import ZoneInfo
        h = datetime.now(ZoneInfo("America/New_York"))
        if h.hour < 9 or (h.hour == 9 and h.minute < 30):
            return "pre"
        if h.hour >= 16:
            return "post"
    except Exception:
        pass
    return "regular"


def _extended_moves(symbols: list[str]) -> dict[str, dict]:
    """{sym: {pct, session, px, ref}} — last_price vs the prior
    regular close. In extended hours last_price IS the post/pre-market
    print; in regular hours it's the day's move (still a repricing)."""
    import yfinance as yf
    session = _session()
    out = {}
    for sym in symbols:
        try:
            fi = yf.Ticker(sym).fast_info
            px = fi.get("last_price")
            ref = (fi.get("regular_market_previous_close")
                   or fi.get("previous_close"))
            if px and ref:
                out[sym] = {"pct": round((px / ref - 1) * 100, 2),
                            "session": session, "px": px, "ref": ref}
        except Exception as exc:
            logger.debug("read_through %s: %s", sym, exc)
    return out


def _repricing(moves: dict[str, dict]) -> Optional[dict]:
    """Detect a same-direction basket repricing from member moves."""
    ups = {s: m for s, m in moves.items() if m["pct"] >= _MIN_MOVE_PCT}
    dns = {s: m for s, m in moves.items() if m["pct"] <= -_MIN_MOVE_PCT}
    n = len(moves)
    for direction, grp in (("up", ups), ("down", dns)):
        if len(grp) >= _MIN_MOVERS:
            pass
        elif n and len([1 for m in moves.values()
                        if abs(m["pct"]) >= 2
                        and (m["pct"] > 0) == (direction == "up")]
                       ) / n >= _MIN_BREADTH:
            grp = {s: m for s, m in moves.items()
                   if abs(m["pct"]) >= 2
                   and (m["pct"] > 0) == (direction == "up")}
            if not grp:
                continue
        else:
            continue
        leader = max(grp, key=lambda s: abs(grp[s]["pct"]))
        return {"direction": direction, "n_moved": len(grp),
                "max_move": grp[leader]["pct"], "leader": leader,
                "members": [{"sym": s, "pct": m["pct"]}
                            for s, m in sorted(
                                grp.items(),
                                key=lambda kv: -abs(kv[1]["pct"]))]}
    # bellwether — one member's outsized repricing
    for s, m in moves.items():
        if abs(m["pct"]) >= _MIN_BELLWETHER:
            return {"direction": "up" if m["pct"] > 0 else "down",
                    "n_moved": 1, "max_move": m["pct"], "leader": s,
                    "members": [{"sym": s, "pct": m["pct"]}]}
    return None


def scan() -> dict:
    """Extended-hours sweep over every theme book → journaled
    repricing events. Call ~16:30 ET (post) and ~08:30 ET (pre)."""
    from app.database import db
    from datetime import date
    books = _books()
    evals = []
    for book, syms in sorted(books.items()):
        moves = _extended_moves(syms)
        if not moves:
            continue
        rep = _repricing(moves)
        if not rep:
            continue
        session = moves[rep["leader"]]["session"]
        db.execute_update(
            "INSERT INTO read_through_evals (as_of, session, basket,"
            " direction, n_members, n_moved, max_move, leader, members)"
            " VALUES (:d,:se,:b,:di,:n,:nm,:mx,:l,"
            " CAST(:m AS jsonb))",
            {"d": date.today(), "se": session, "b": book,
             "di": rep["direction"], "n": len(syms),
             "nm": rep["n_moved"], "mx": rep["max_move"],
             "l": rep["leader"], "m": json.dumps(rep["members"])})
        evals.append({"basket": book, **rep, "session": session})
        logger.info("read_through %s %s %+0.1f%% leader=%s n=%d",
                    book, rep["direction"], rep["max_move"],
                    rep["leader"], rep["n_moved"])
    return {"books": len(books), "repricings": evals}


def latest(days: int = 1) -> list[dict]:
    """Recent repricing events — the regime/alert surface."""
    from app.database import db
    rows = db.execute_query(
        "SELECT as_of, session, basket, direction, n_members,"
        " n_moved, max_move, leader, members, created_at"
        " FROM read_through_evals"
        " WHERE as_of >= CURRENT_DATE - :d"
        " ORDER BY created_at DESC", {"d": days})
    out = []
    for r in rows:
        row = dict(r)
        row["as_of"] = str(row["as_of"])
        row["created_at"] = str(row["created_at"])[:19]
        m = row.get("members")
        row["members"] = json.loads(m) if isinstance(m, str) else m
        out.append(row)
    return out


def overnight_context() -> Optional[dict]:
    """Compact repricing summary for the morning regime's evidence —
    {'up': ['GridTech +4.2% led by CRDO'], 'down': []} style strings."""
    evs = latest(1)
    if not evs:
        return None
    return {
        "repricings": [
            {"basket": e["basket"], "direction": e["direction"],
             "leader": e["leader"], "max_move": float(e["max_move"]),
             "n_moved": e["n_moved"], "n_members": e["n_members"],
             "session": e["session"]}
            for e in evs],
        "plain": "; ".join(
            f"{e['basket']} repriced {'up' if e['direction']=='up' else 'down'} "
            f"{'+' if e['direction']=='up' else ''}{float(e['max_move']):.1f}% "
            f"{e['session']}-market, led by {e['leader']} "
            f"({e['n_moved']}/{e['n_members']} members)"
            for e in evs)}
