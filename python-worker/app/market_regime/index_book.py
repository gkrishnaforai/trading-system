"""index_book — the `indexes` portfolio: the regime ETF set tracked
as a book so index names flow through the same pages and jobs as
every other holding. Tracking units only — advisory bookkeeping,
never an order. Mirrors the `futureStocks` convention: a 1-share
tracking position makes the symbol `active` everywhere the universe
queries union portfolio positions."""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Optional

from .universe import GLOBAL_OVERLAY, INDEX_UNIVERSE

logger = logging.getLogger(__name__)

INDEX_BOOK = "indexes"
INDEX_SYMBOLS = INDEX_UNIVERSE + GLOBAL_OVERLAY


def _q(sql: str, p: Optional[dict] = None) -> list[dict]:
    from app.database import db
    return db.execute_query(sql, p or {})


def _u(sql: str, p: Optional[dict] = None) -> Any:
    from app.database import db
    return db.execute_update(sql, p or {})


def _book_id() -> Optional[str]:
    r = _q("SELECT id FROM portfolios WHERE name=:n", {"n": INDEX_BOOK})
    if r:
        return r[0]["id"]
    owner = _q("SELECT user_id, COUNT(*) n FROM portfolios"
               " GROUP BY user_id ORDER BY n DESC LIMIT 1")
    if not owner:
        logger.warning("index_book: no portfolios yet — skipping")
        return None
    pid = uuid.uuid4()
    _u("INSERT INTO portfolios (id,user_id,name,description,"
       " portfolio_type,is_active)"
       " VALUES (:i,:u,:n,:d,'custom',true)",
       {"i": pid, "u": owner[0]["user_id"], "n": INDEX_BOOK,
        "d": "Regime index set — tracking units, not positions. "
             "Core US: SPY/QQQ/DIA/IWM/MDY/RSP. Global overlay: "
             "EFA/EEM. Duration (TLT) is macro evidence, not held."})
    return pid


def ensure_index_book() -> int:
    """Idempotent — create the book if missing, insert a tracking
    unit for any regime ETF not already held. Returns # added."""
    from app.market_data import bars as bars_mod
    pid = _book_id()
    if pid is None:
        return 0
    added = 0
    for sym in INDEX_SYMBOLS:
        _u("INSERT INTO stocks (symbol) VALUES (:s)"
           " ON CONFLICT (symbol) DO NOTHING", {"s": sym})
        st = _q("SELECT id FROM stocks WHERE symbol=:s", {"s": sym})
        if not st:
            continue
        if _q("SELECT 1 FROM portfolio_positions"
              " WHERE portfolio_id=:p AND stock_id=:i",
              {"p": pid, "i": st[0]["id"]}):
            continue
        px = None
        try:
            b = bars_mod.live(sym, period="5d")
            px = float(b[-1].close) if len(b) else None
        except Exception:
            pass
        if px is None:
            continue
        _u("INSERT INTO portfolio_positions (portfolio_id,stock_id,"
           " quantity,avg_price,metadata) VALUES"
           " (:p,:i,1,:px,CAST(:m AS jsonb))",
           {"p": pid, "i": st[0]["id"], "px": px,
            "m": json.dumps({"tracking": True,
                             "role": "regime_index"})})
        _u("INSERT INTO portfolio_holdings (portfolio_id,symbol,"
           " asset_type,shares_held,average_cost,status,notes)"
           " VALUES (:p,:s,'stock',1,:px,'active',:n)"
           " ON CONFLICT DO NOTHING",
           {"p": pid, "s": sym, "px": px,
            "n": "tracking unit — regime index set"})
        added += 1
    if added:
        logger.info("index_book: %s tracking units added to '%s'",
                    added, INDEX_BOOK)
    return added
