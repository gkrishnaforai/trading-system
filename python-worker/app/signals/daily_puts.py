"""Daily puts — the board's short-side distilled output: top-3 put
calls with a concrete plan, journaled and graded like daily_calls.

The calls engine answers "what longs today?"; this answers "what
short-side trades today?" — driven by the leap_put readiness board
(the put_entry.score composite, reused as its rank — no duplicate
scorer). Sources only names the readiness gate already vetted:
broken/fragile tape + valuation excess, not random weak stocks.

Posture gate: emits only when posture.shorts is true — shorts are
trades, not hedges, so caution means stand aside here too.

Plan geometry is mirrored: stop ABOVE entry (the stock rallying
kills the put), target BELOW (the fall pays). Resolution uses the
same first-touch rule; returns are measured put-side — a -8% drop
is +8 to the put thesis (not a contract-Greek estimate, just the
underlying move the plan was betting on).
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

_TOP = 3
_PUT_SCORE_MIN = 60                       # same floor as the planner


def generate(today: Optional[date] = None) -> dict[str, Any]:
    """Pick today's top-3 put calls from the leap_put-ready board."""
    from app.database import db
    from app.signals.swing_pilot import weight
    from app.market_data import bars as bars_mod

    today = today or datetime.now(timezone.utc).date()
    from app.signals import posture as _pos
    pos = _pos.current()
    if not pos.get("shorts", True):
        return {"date": str(today), "calls": [], "posture": pos,
                "note": f"posture {pos.get('posture')} — shorts not "
                        f"permitted ({pos.get('matched')}); no put "
                        "calls today"}

    evals = sorted(db.execute_query(
        "SELECT DISTINCT ON (symbol) symbol, rank, mom, fund, fails"
        " FROM readiness_evals WHERE use_case='leap_put'"
        " AND as_of=(SELECT max(as_of) FROM readiness_evals"
        "  WHERE use_case='leap_put')"
        " AND state='ready' AND rank >= :m"
        " ORDER BY symbol, id DESC",
        {"m": _PUT_SCORE_MIN}),
        key=lambda r: -(r["rank"] or 0))[:_TOP]
    if not evals:
        return {"date": str(today), "calls": [], "posture": pos,
                "note": "no leap_put-ready names clearing the score "
                        "floor today"}

    mom_map = {r["symbol"]: r for r in db.execute_query(
        "SELECT symbol, momentum_state, momentum_detail"
        " FROM stocks WHERE symbol = ANY(:syms)",
        {"syms": [e["symbol"] for e in evals]})}
    books = bars_mod.load([e["symbol"] for e in evals], days=30)

    # learned plan params — own keys so put geometry can be tuned
    # independently of call geometry
    _bm, _rr = weight("puts:band_mult"), weight("puts:rr_target")
    band_mult = _bm if isinstance(_bm, (int, float)) else 1.5
    rr_t = _rr if isinstance(_rr, (int, float)) else 2.0
    made = []
    for i, e in enumerate(evals, 1):
        sym = e["symbol"]
        bars = books.get(sym) or []
        px = bars[-1].close if bars else None
        if not px:
            continue
        det = (mom_map.get(sym) or {}).get("momentum_detail") or {}
        atr_pct = det.get("atr_pct")
        band = min(0.10, max(0.04, band_mult * (atr_pct or 0.03)))
        stop = round(px * (1 + band), 2)
        tgt = round(px - rr_t * (stop - px), 2)
        evidence = [f"put score {e['rank']}"]
        if e.get("mom"):
            evidence.append(f"tape {e['mom']}")
        if e.get("fund"):
            evidence.append(f"fund {e['fund']}")
        row = {"call_date": str(today), "rank": i, "symbol": sym,
               "score": round(float(e["rank"] or 0), 1),
               "entry_px": round(px, 2), "stop_px": stop,
               "target_px": tgt,
               "rr": round((px - tgt) / (stop - px), 2),
               "state": (mom_map.get(sym) or {}).get("momentum_state"),
               "dip_phase": det.get("dip_phase"),
               "evidence": evidence[:8]}
        db.execute_update(
            "INSERT INTO daily_puts (call_date, rank, symbol, score,"
            " entry_px, stop_px, target_px, rr, state, dip_phase,"
            " evidence) VALUES (:d,:k,:s,:sc,:e,:sp,:t,:rr,:st,:dp,"
            " CAST(:ev AS jsonb))"
            " ON CONFLICT (call_date, symbol) DO UPDATE SET"
            " rank=:k, score=:sc, entry_px=:e, stop_px=:sp,"
            " target_px=:t, rr=:rr, state=:st, dip_phase=:dp,"
            " evidence=CAST(:ev AS jsonb)",
            {"d": today, "k": i, "s": sym, "sc": row["score"],
             "e": row["entry_px"], "sp": stop, "t": tgt,
             "rr": row["rr"], "st": row["state"],
             "dp": row["dip_phase"],
             "ev": __import__("json").dumps(row["evidence"])})
        made.append(row)
    return {"date": str(today), "calls": made, "posture": pos}


def report(days: int = 10) -> dict[str, Any]:
    """Recent put calls — today's first, then history."""
    from app.database import db
    rows = db.execute_query(
        "SELECT * FROM daily_puts ORDER BY call_date DESC, rank"
        " LIMIT :n", {"n": days * _TOP})
    from app.signals import posture as _pos
    return {"calls": rows, "record": puts_record(),
            "posture": _pos.current()}


def evaluate_puts(days_back: int = 60) -> dict[str, Any]:
    """Grade journaled put calls — mirrored first-touch resolution.

    For a put thesis: target = the drop paying out (b.low <= target),
    stop = the rally killing it (b.high >= stop). Same-bar ambiguity
    resolves as stop_first (conservative, as with calls). ret_* are
    put-side: (entry - close)/entry*100 — what the underlying move
    was worth to the put thesis."""
    from app.database import db
    from app.signals.board_tracking import _bars
    rows = db.execute_query(
        """SELECT c.id, c.call_date, c.symbol, c.entry_px, c.stop_px,
                  c.target_px, o.id AS oid, o.resolution,
                  o.ret_5d IS NOT NULL AS has5,
                  o.ret_10d IS NOT NULL AS has10,
                  o.ret_20d IS NOT NULL AS has20
           FROM daily_puts c
           LEFT JOIN daily_put_outcomes o ON o.call_id = c.id
           WHERE c.call_date > now()::date - :d
             AND c.entry_px IS NOT NULL
             AND (o.id IS NULL OR o.resolution = 'open'
                  OR o.ret_20d IS NULL)
           ORDER BY c.call_date DESC""", {"d": days_back})
    done, errors = 0, []
    for c in rows:
        try:
            bars = _bars(c["symbol"], c["call_date"])
            if not bars:
                continue
            entry = float(c["entry_px"])
            stop = float(c["stop_px"] or 0)
            tgt = float(c["target_px"] or 0)
            day0 = bars[0]
            eod = day0.close
            fwd = [b for b in bars
                   if b.timestamp.date() > day0.timestamp.date()]

            res, res_date, held = c["resolution"] or "open", None, None
            if res == "open" and fwd:
                for i, b in enumerate(fwd[:20], 1):
                    hit_stop = stop and b.high >= stop
                    hit_tgt = tgt and b.low <= tgt
                    if hit_stop or hit_tgt:
                        res = "stop_first" if hit_stop else "target_first"
                        res_date, held = b.timestamp.date(), i
                        break
                if res == "open" and len(fwd) >= 20:
                    res, res_date, held = ("expired",
                                           fwd[19].timestamp.date(), 20)

            def _ret(n):
                w = fwd[:n]
                if len(w) < min(n, 2):
                    return None
                return round((entry - w[-1].close) / entry * 100, 2)

            window = fwd[:20]
            mfe = (round((entry - min(b.low for b in window))
                         / entry * 100, 2) if window else None)
            mae = (round((entry - max(b.high for b in window))
                         / entry * 100, 2) if window else None)
            vals = {"eod": round(eod, 2),
                    "re": round((entry - eod) / entry * 100, 2),
                    "r5": _ret(5) if not c["has5"] else None,
                    "r10": _ret(10) if not c["has10"] else None,
                    "r20": _ret(20) if not c["has20"] else None,
                    "mfe": mfe, "mae": mae, "res": res,
                    "rd": res_date, "dh": held, "cid": c["id"],
                    "d": c["call_date"], "s": c["symbol"],
                    "e": entry, "sp": stop or None,
                    "t": tgt or None}
            if c["oid"] is None:
                db.execute_update(
                    """INSERT INTO daily_put_outcomes
                       (call_id, call_date, symbol, entry_px, stop_px,
                        target_px, eod_close, ret_eod, ret_5d, ret_10d,
                        ret_20d, mfe, mae, resolution, resolved_date,
                        days_held)
                       VALUES (:cid,:d,:s,:e,:sp,:t,:eod,:re,:r5,:r10,
                        :r20,:mfe,:mae,:res,:rd,:dh)
                       ON CONFLICT (call_id) DO NOTHING""", vals)
            else:
                db.execute_update(
                    """UPDATE daily_put_outcomes SET
                        eod_close=:eod, ret_eod=:re,
                        ret_5d=COALESCE(:r5, ret_5d),
                        ret_10d=COALESCE(:r10, ret_10d),
                        ret_20d=COALESCE(:r20, ret_20d),
                        mfe=GREATEST(mfe, :mfe),
                        mae=LEAST(mae, :mae),
                        resolution=:res, resolved_date=:rd,
                        days_held=:dh, graded_at=now()
                       WHERE id=:oid""", {**vals, "oid": c["oid"]})
            done += 1
        except Exception as exc:
            errors.append(f"{c['symbol']}: {exc}")
    return {"evaluated": done, "errors": errors[:10]}


def puts_record() -> dict[str, Any]:
    """Track record of the put-calls engine itself — resolution mix
    and hit rate, put-side returns."""
    from app.database import db
    rows = db.execute_query(
        """SELECT count(*) FILTER (WHERE resolution='target_first') tgt,
                  count(*) FILTER (WHERE resolution='stop_first') stp,
                  count(*) FILTER (WHERE resolution='expired') exp,
                  count(*) FILTER (WHERE resolution='open') open,
                  round(avg(ret_eod)::numeric, 2) avg_eod,
                  round(avg(ret_20d)::numeric, 2) avg_20d,
                  round(avg(days_held) FILTER
                        (WHERE resolution != 'open')::numeric, 1)
                        avg_held
           FROM daily_put_outcomes""")
    return rows[0] if rows else {}
