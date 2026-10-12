"""Book-level risk — beta and concentration the position list hides.

Three "diversified" picks in the same sector are one bet. This computes
what the book is actually exposed to:

    book_beta        Σ(weight × beta_to_SPY) — true market sensitivity
    sector_share     risk share of the largest sector cluster
    corr_warning     >40% of book risk in one sector, or book_beta >1.3

Betas come from canonical daily_bars (126d returns vs SPY); persisted
to engine_weights['book:risk'] by the momentum job so readers are free.
"""
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def _rets(closes: list[float]) -> list[float]:
    return [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes))
            if closes[i - 1]]


def compute_book_risk() -> dict[str, Any]:
    from app.database import db
    from app.market_data import bars as bars_mod

    pos = db.execute_query(
        "SELECT s.symbol, s.sector, pp.quantity, pp.current_price,"
        "       pp.avg_price "
        "FROM portfolio_positions pp JOIN stocks s ON s.id = pp.stock_id "
        "WHERE pp.quantity > 0")
    if not pos:
        return {"positions": 0}
    syms = [p["symbol"] for p in pos]
    books = bars_mod.load(syms + ["SPY"], days=140)
    spy = {str(b.date): b.close for b in books.get("SPY") or []}

    rows, tot_val = [], 0.0
    for p in pos:
        bars = books.get(p["symbol"]) or []
        px = float(p["current_price"] or p["avg_price"] or 0)
        val = float(p["quantity"]) * px
        beta = None
        if len(bars) >= 60 and spy:
            sm, bm = {}, {}
            for b in bars:
                if str(b.date) in spy:
                    sm[str(b.date)], bm[str(b.date)] = b.close, spy[str(b.date)]
            dts = sorted(sm)
            sr = _rets([sm[d] for d in dts]); br = _rets([bm[d] for d in dts])
            n = min(len(sr), len(br), 126)
            if n >= 30:
                sr, br = sr[-n:], br[-n:]
                ms, mb = sum(sr) / n, sum(br) / n
                cov = sum((a - ms) * (c - mb) for a, c in zip(sr, br)) / n
                var = sum((c - mb) ** 2 for c in br) / n
                beta = round(cov / var, 2) if var else None
        rows.append({"symbol": p["symbol"], "sector": p["sector"] or "?",
                     "value": round(val, 0), "beta": beta})
        tot_val += val

    if not tot_val:
        return {"positions": len(rows)}
    book_beta = sum(r["value"] * (r["beta"] or 1.0)
                    for r in rows) / tot_val
    sec = {}
    for r in rows:
        sec[r["sector"]] = sec.get(r["sector"], 0) + r["value"]
    top_sec = max(sec.items(), key=lambda kv: kv[1])
    out = {
        "positions": len(rows),
        "book_value": round(tot_val, 0),
        "book_beta": round(book_beta, 2),
        "top_sector": top_sec[0],
        "top_sector_pct": round(100 * top_sec[1] / tot_val, 1),
        "sector_mix": {k: round(100 * v / tot_val, 1)
                       for k, v in sorted(sec.items(), key=lambda kv: -kv[1])},
        "legs": sorted(rows, key=lambda r: -r["value"]),
        "warnings": ([f"book beta {book_beta:.2f} — amplifying the tape"]
                     if book_beta > 1.3 else [])
                    + ([f"{100 * top_sec[1] / tot_val:.0f}% of book in "
                        f"{top_sec[0]} — one sector = one bet"]
                       if top_sec[1] / tot_val > 0.4 else []),
    }
    try:
        db.execute_query(
            "INSERT INTO engine_weights(key, value, updated_at)"
            " VALUES ('book:risk', CAST(:v AS jsonb), now())"
            " ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value,"
            "   updated_at = now()",
            {"v": json.dumps(out)})
    except Exception as exc:
        logger.debug("book risk persist: %s", exc)
    return out


def read() -> dict[str, Any]:
    from app.database import db
    rows = db.execute_query(
        "SELECT value FROM engine_weights WHERE key='book:risk'")
    if rows:
        v = rows[0]["value"]
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return {}
        return v or {}
    return {}
