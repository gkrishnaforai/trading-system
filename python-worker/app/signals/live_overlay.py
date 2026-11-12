"""Live-price overlay — one batched fetch feeds every downstream
read. Writes symbol_live_ticks; consumers stitch the live close
onto daily_bars and recompute the legs that CAN move intraday
(tape/rel-strength). EOD-derived inputs (XBRL, estimates,
transcripts) don't move — the canonical daily/weekly journal is
untouched. Same overlay contract as intraday-regime over the
daily baseline."""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")


def ensure_table() -> None:
    from app.database import db
    db.execute_update(
        "CREATE TABLE IF NOT EXISTS symbol_live_ticks ("
        " symbol TEXT NOT NULL, as_of DATE NOT NULL,"
        " last_px NUMERIC, volume NUMERIC,"
        " ts TIMESTAMPTZ NOT NULL DEFAULT now(),"
        " PRIMARY KEY (symbol, as_of))")


def refresh(symbols: list[str]) -> dict[str, Any]:
    """One batched download → one table → all readers share it."""
    import yfinance as yf
    from app.database import db
    ensure_table()
    if not symbols:
        return {"updated": 0}
    df = yf.download(" ".join(symbols), period="1d",
                     group_by="column", threads=True, progress=False, timeout=30)
    if df is None or df.empty:
        return {"updated": 0, "note": "no live data"}
    closes = df["Close"].ffill().iloc[-1] if "Close" in df else None
    vols = df["Volume"].ffill().iloc[-1] if "Volume" in df else None
    if closes is None:
        return {"updated": 0}
    n = 0
    for sym in symbols:
        try:
            # symbol-keyed lookup — positional iloc[i] MISALIGNS when
            # a symbol fails to download (columns shift, SPY got $12)
            px = (closes[sym] if hasattr(closes, 'get') else closes)
            px = float(px)
            if px != px or px <= 0:
                continue
            v = float(vols[sym]) if vols is not None \
                and hasattr(vols, 'get') and sym in vols else 0
            db.execute_update(
                "INSERT INTO symbol_live_ticks"
                " (symbol, as_of, last_px, volume)"
                " VALUES (:s,:d,:p,:v)"
                " ON CONFLICT (symbol,as_of) DO UPDATE SET"
                " last_px=EXCLUDED.last_px, volume=EXCLUDED.volume,"
                " ts=now()",
                {"s": sym, "d": date.today(), "p": px, "v": v})
            n += 1
        except Exception:
            continue
    return {"updated": n}


def live_px(sym: str) -> float | None:
    from app.database import db
    try:
        r = db.execute_query(
            "SELECT last_px FROM symbol_live_ticks"
            " WHERE symbol=:s AND as_of=CURRENT_DATE", {"s": sym})
        return float(r[0]["last_px"]) if r else None
    except Exception:
        return None


def tape_live(sym: str, spy_live: float | None = None) -> dict | None:
    """Tape legs recomputed with the live close stitched onto
    daily bars — same math as the score, intraday overlay only."""
    from app.database import db
    from app.signals.resilience_engine import _map
    px = live_px(sym)
    spy = spy_live if spy_live is not None else live_px("SPY")
    if not px or not spy:
        return None
    try:
        rows = db.execute_query(
            "SELECT close FROM daily_bars WHERE symbol=:s"
            " ORDER BY date DESC LIMIT 61", {"s": sym})
        spy_rows = db.execute_query(
            "SELECT close FROM daily_bars WHERE symbol='SPY'"
            " ORDER BY date DESC LIMIT 61")
        if len(rows) < 21 or len(spy_rows) < 21:
            return None
        closes = [px] + [float(r["close"]) for r in rows]
        sc = [spy] + [float(r["close"]) for r in spy_rows]

        def rel(n):
            if len(closes) < n + 1 or len(sc) < n + 1:
                return None
            a = closes[0] / closes[n] - 1 if closes[n] else None
            b = sc[0] / sc[n] - 1 if sc[n] else None
            return a - b if a is not None and b is not None else None

        legs = [(_map(rel(1), -0.08, 0.08), .05),
                (_map(rel(5), -0.10, 0.10), .15),
                (_map(rel(20), -0.15, 0.15), .25),
                (_map(rel(60), -0.20, 0.20), .25)]
        live = [(s, w) for s, w in legs if s is not None]
        if not live:
            return None
        # legs are already 0-100 maps — weighted avg, no renorm
        score = round(sum(s * w for s, w in live)
                      / sum(w for _, w in live))
        return {"tape_live": score,
                "rel1": round(rel(1) or 0, 4),
                "rel5": round(rel(5) or 0, 4),
                "rel20": round(rel(20) or 0, 4),
                "as_of": datetime.now(_ET).isoformat(timespec="seconds")}
    except Exception:
        return None


def swing_live(sym: str) -> dict | None:
    """Intraday swing read — dip_phase recomputed with the live
    close stitched as a synthetic bar. Overlay only; the daily
    checklist stays canonical. Flat synthetic bar (o=h=l=c) is a
    conservative stitch — honest caveat, never fabricated lows."""
    from app.database import db
    px = live_px(sym)
    if not px:
        return None
    try:
        import types as _t
        from app.signals import momentum_regime as mr
        rows = db.execute_query(
            "SELECT open, high, low, close, volume, date"            " FROM daily_bars"
            " WHERE symbol=:s ORDER BY date DESC LIMIT 70",
            {"s": sym})
        if len(rows) < 60:
            return None
        # adj_close=None → indicators fall back to close (same
        # attr shape as OHLCVBar — SimpleNamespace must match)
        bars = [_t.SimpleNamespace(
            open=float(r["open"]), high=float(r["high"]),
            low=float(r["low"]), close=float(r["close"]),
            adj_close=None, timestamp=r["date"],
            volume=float(r["volume"] or 0)) for r in reversed(rows)]
        # today's live bar stitched on — flat range, conservative
        bars.append(_t.SimpleNamespace(open=px, high=px, low=px,
                                       close=px, adj_close=None,
                                       timestamp=date.today(),
                                       volume=0))
        closes = [b.close for b in bars]
        from app.options.leaps import (_technicals,
                                       _macd_hist_prev)
        tech = _technicals(bars)
        h = mr.dip_health(tech, _macd_hist_prev(bars), bars)
        if not h:
            return None
        return {"dip_phase_live": h.get("dip_phase"),
                "stab_live": h.get("stabilization_score"),
                "stab_cls_live": h.get("stab_cls"),
                "dip_health_live": h.get("dip_health"),
                "as_of": datetime.now(_ET).isoformat(
                    timespec="seconds")}
    except Exception:
        return None
        return {"dip_phase_live": h.get("dip_phase"),
                "stab_live": h.get("stabilization_score"),
                "stab_cls_live": h.get("stab_cls"),
                "as_of": datetime.now(_ET).isoformat(
                    timespec="seconds")}
    except Exception:
        return None
