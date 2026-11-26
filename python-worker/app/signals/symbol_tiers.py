"""symbol_tiers — explicit coverage tiers so refresh work follows a
priority schedule instead of a flat universe.

Tiers
-----
active    books ∪ watchlist ∪ scan members ∪ futureStocks — the
          nightly full-stack universe every job already unions
monthly   data-covered names outside active, plus names that just
          reported earnings — a monthly pass keeps fundamentals warm
          so the discovery scan can see them
registry  the wide stocks table — metadata only; nothing is fetched
          until earnings or a promotion moves it up

Promotion
---------
`promote()` inserts a tracking unit into the `futureStocks` book —
which makes the symbol `active` for free, because every downstream
universe query already unions portfolio positions. One insert, every
job picks it up. `discovery_scan()` applies the triggers
(rev growth ≥ 30%, accelerating fundamentals, A-grade revisions,
high spring score) over the monthly tier and promotes hits.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

FUTURES_BOOK = "futureStocks"

# Discovery triggers — a monthly-tier name earns promotion when ANY
# of these fire. Thresholds are deliberately few and legible.
PROMOTE_RULES = {
    "rev_growth": 0.30,          # growth >30% — the user's trigger
    "revision_grades": {"A", "A+"},
    "fund_states": {"accelerating"},
    "spring": 70,                # coiled-spring rebound setup
}


def _q(sql: str, p: Optional[dict] = None) -> list[dict]:
    from app.database import db
    return db.execute_query(sql, p or {})


def _u(sql: str, p: Optional[dict] = None) -> Any:
    from app.database import db
    return db.execute_update(sql, p or {})


def _active_sql() -> str:
    # book (canonical view) ∪ scan memberships — coverage extends
    # beyond the book, but the book itself is defined once.
    return ("SELECT symbol FROM book_symbols"
            " UNION SELECT symbol FROM rule_breaker_members"
            " UNION SELECT symbol FROM smallcap_members")


def _covered_sql() -> str:
    """Names that have ANY thesis/fundamental source data."""
    return ("SELECT symbol FROM symbol_flywheel"
            " UNION SELECT symbol FROM symbol_sec_facts"
            " UNION SELECT symbol FROM doc_analyses"
            " UNION SELECT symbol FROM stocks"
            "   WHERE fundamental_detail IS NOT NULL")


def sync() -> dict:
    """Recompute the tier table. Idempotent — reason strings say why
    each row sits where it does."""
    active = {r["symbol"] for r in _q(
        f"SELECT symbol FROM ({_active_sql()}) x")}
    covered = {r["symbol"] for r in _q(
        f"SELECT symbol FROM ({_covered_sql()}) x")}
    # post-earnings names earn a monthly slot even without coverage
    earn = {r["symbol"] for r in _q(
        "SELECT symbol FROM stocks"
        " WHERE next_earnings_date <= CURRENT_DATE"
        " AND next_earnings_date >= CURRENT_DATE - 21")}
    futures = {r["symbol"] for r in _q(
        "SELECT s.symbol FROM stocks s"
        " JOIN portfolio_positions pp ON pp.stock_id=s.id"
        " AND pp.quantity>0"
        " JOIN portfolios p ON p.id=pp.portfolio_id"
        " AND p.name=:b", {"b": FUTURES_BOOK})}

    n = {"active": 0, "monthly": 0, "registry": 0}
    for sym in active:
        reason = ("promoted" if sym in futures else "tracked")
        _u("INSERT INTO symbol_tiers (symbol,tier,reason,promoted_at)"
           " VALUES (:s,'active',:r, CASE WHEN :r='promoted'"
           " THEN now() ELSE NULL END)"
           " ON CONFLICT (symbol) DO UPDATE SET tier='active',"
           " reason=EXCLUDED.reason, updated_at=now()",
           {"s": sym, "r": reason})
        n["active"] += 1
    for sym in (covered | earn) - active:
        _u("INSERT INTO symbol_tiers (symbol,tier,reason)"
           " VALUES (:s,'monthly',:r)"
           " ON CONFLICT (symbol) DO UPDATE SET tier='monthly',"
           " reason=EXCLUDED.reason, updated_at=now()",
           {"s": sym, "r": "earnings" if sym in earn - covered
            else "covered"})
        n["monthly"] += 1
    # demote: rows that are neither active nor monthly anymore
    keep = active | covered | earn
    _u("UPDATE symbol_tiers SET tier='registry', updated_at=now()"
       " WHERE tier <> 'registry' AND symbol <> ALL(:k)",
       {"k": list(keep)})
    return n


def tier(sym: str) -> str:
    r = _q("SELECT tier FROM symbol_tiers WHERE symbol=:s",
           {"s": sym.upper()})
    return r[0]["tier"] if r else "registry"


def monthly_universe() -> list[str]:
    return [r["symbol"] for r in _q(
        "SELECT symbol FROM symbol_tiers WHERE tier='monthly'")]


def _futures_portfolio() -> Any:
    r = _q("SELECT id FROM portfolios WHERE name=:b",
           {"b": FUTURES_BOOK})
    if r:
        return r[0]["id"]
    import uuid
    pid = uuid.uuid4()
    # Owner resolution by book, not by hard-coded book names: the
    # base portfolio's owner, else the owner of the most-positioned book.
    owner = _q("SELECT p.user_id FROM portfolios p"
               " JOIN portfolio_positions pp ON pp.portfolio_id = p.id"
               " WHERE p.name = 'base-portfolio' LIMIT 1") or _q(
        "SELECT p.user_id, COUNT(*) n FROM portfolios p"
        " JOIN portfolio_positions pp ON pp.portfolio_id = p.id"
        " WHERE p.name <> :f"
        " GROUP BY p.user_id ORDER BY n DESC LIMIT 1",
        {"f": FUTURES_BOOK})
    _u("INSERT INTO portfolios (id,user_id,name,description,"
       " portfolio_type,is_active)"
       " VALUES (:i,:u,:n,:d,'custom',true)",
       {"i": pid, "u": owner[0]["user_id"], "n": FUTURES_BOOK,
        "d": "Auto-promoted names — discovery scan found a trigger "
             "(growth >30%, accelerating fundamentals, A revisions, "
             "spring setup). Tracking units, not purchases."})
    return pid


def promote(sym: str, reason: str) -> bool:
    """Insert a tracking unit into futureStocks → the symbol becomes
    `active` everywhere (every universe union already reads the book).
    Returns False if already a member."""
    from app.market_data import bars as bars_mod
    sym = sym.upper()
    pid = _futures_portfolio()
    if _q("SELECT 1 FROM portfolio_positions pp"
          " JOIN stocks s ON s.id=pp.stock_id"
          " WHERE pp.portfolio_id=:p AND s.symbol=:s"
          " AND pp.quantity>0", {"p": pid, "s": sym}):
        return False
    st = _q("SELECT id FROM stocks WHERE symbol=:s", {"s": sym})
    if not st:
        return False
    px = None
    try:
        b = bars_mod.live(sym, period="5d")
        px = float(b[-1].close) if len(b) else None
    except Exception:
        pass
    if px is None:
        return False
    _u("INSERT INTO portfolio_positions (portfolio_id,stock_id,"
       " quantity,avg_price,metadata) VALUES"
       " (:p,:i,1,:px,CAST(:m AS jsonb))",
       {"p": pid, "i": st[0]["id"], "px": px,
        "m": json.dumps({"tracking": True, "promotion": reason})})
    _u("INSERT INTO portfolio_holdings (portfolio_id,symbol,"
       " asset_type,shares_held,average_cost,status,notes)"
       " VALUES (:p,:s,'stock',1,:px,'active',:n)"
       " ON CONFLICT DO NOTHING",
       {"p": pid, "s": sym, "px": px,
        "n": f"tracking unit — promoted: {reason}"})
    _u("INSERT INTO symbol_tiers (symbol,tier,reason,promoted_at)"
       " VALUES (:s,'active',:r,now())"
       " ON CONFLICT (symbol) DO UPDATE SET tier='active',"
       " reason=EXCLUDED.reason, promoted_at=now(),"
       " updated_at=now()", {"s": sym, "r": f"promoted:{reason}"})
    logger.info("promoted %s → %s (%s)", sym, FUTURES_BOOK, reason)
    return True


def _promotion_reasons(row: dict) -> list[str]:
    """Which triggers fire for one symbol row. Returns [] if none."""
    reasons = []
    fd = row.get("fundamental_detail")
    fd = json.loads(fd) if isinstance(fd, str) else (fd or {})
    cur = fd.get("cur") or {}
    rg = cur.get("rev_growth")
    if rg is not None and rg >= PROMOTE_RULES["rev_growth"]:
        reasons.append(f"growth{rg:.0%}")
    if row.get("fundamental_state") in PROMOTE_RULES["fund_states"]:
        reasons.append(f"fund_{row['fundamental_state']}")
    if row.get("revision_grade") in PROMOTE_RULES["revision_grades"]:
        reasons.append(f"rev_{row['revision_grade']}")
    md = row.get("momentum_detail")
    md = json.loads(md) if isinstance(md, str) else (md or {})
    sp = (md or {}).get("spring")
    if sp is not None and sp >= PROMOTE_RULES["spring"]:
        reasons.append(f"spring{sp:.0f}")
    return reasons


def discovery_scan(symbols: Optional[list[str]] = None) -> dict:
    """Sweep the monthly tier (or an explicit list) for promotion
    triggers. Cheap — reads only already-computed stocks columns."""
    if symbols is None:
        symbols = monthly_universe()
    if not symbols:
        return {"scanned": 0, "promoted": []}
    rows = _q("SELECT symbol, fundamental_state, fundamental_detail,"
              " revision_grade, momentum_detail FROM stocks"
              " WHERE symbol = ANY(:s)", {"s": symbols})
    promoted, errs = [], []
    for r in rows:
        reasons = _promotion_reasons(r)
        if not reasons:
            continue
        try:
            if promote(r["symbol"], ",".join(reasons)):
                promoted.append(
                    {"symbol": r["symbol"], "why": reasons})
        except Exception as exc:
            errs.append(f"{r['symbol']}: {exc}")
    return {"scanned": len(rows), "promoted": promoted,
            "errors": errs}
