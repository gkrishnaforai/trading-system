"""Daily calls — the board's distilled output: top-3 swing picks with
a concrete trade plan, plus the fundamental-momentum radar.

A swing desk's morning ritual: after all signals refresh, the PM writes
down the 3 names worth acting on today with entry/stop/target and the
evidence. This module is that ritual, deterministically — every call is
journaled in daily_calls so the outcome engine can grade OUR picks
(closes the loop: not just "what the board saw" but "what we called").

Gates are the same hard vetoes the pilot uses — a call must pass:
  momentum  pullback/recovery/basing/breakout/uptrend (not knife/
            capitulation/downtrend/climax/rolling_over)
  dip       turning_up, or stabilizing w/ symbol prior ≥55%,
            or still_falling only w/ own prior ≥60% + healthy fund
  fund      not declining/deteriorating
  alerts    no NEGATIVE/HIGH in 72h
  prior     gate not learned-OFF (engine_weights gate:*)
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

_TOP = 3


def _prior_hit(sym: str, state: str, dip: Optional[str]) -> Optional[float]:
    """Per-symbol pattern prior hit-rate (same lookup the board uses)."""
    from app.signals.pattern_priors import prior_for
    p = prior_for(sym, f"{state}|{dip or 'none'}")
    return p.get("hit_rate_10d") if p else None


def generate(today: Optional[date] = None) -> dict[str, Any]:
    """Pick today's top-3. Reads the already-refreshed board layers —
    never re-fetches (DRY: composite scoring lives in daily_board)."""
    from app.database import db
    from app.signals.daily_board import _accumulate_scores
    from app.signals.swing_pilot import weight
    from app.market_data import bars as bars_mod

    today = today or datetime.now(timezone.utc).date()
    # posture gate — calls are new-long recommendations; when the
    # permission layer says no, the honest output is no calls
    from app.signals import posture as _pos
    pos = _pos.current()
    if not pos.get("new_longs", True):
        return {"date": str(today), "calls": [], "posture": pos,
                "note": f"posture {pos.get('posture')} — no new "
                        f"longs ({pos.get('matched')}); no calls "
                        "today. no-trade is a valid call"}
    rows = _accumulate_scores()
    cands = []
    for r in rows:
        sym = r["symbol"]
        state = r.get("momentum") or r.get("momentum_state")
        dip = r.get("dip_phase")
        det = r.get("momentum_detail") or {}
        fund = (r.get("fund_state") or r.get("fundamental_state") or "")
        if state in {"knife", "capitulation", "downtrend",
                     "breakdown", "climax", "rolling_over"}:
            continue
        if fund in {"declining", "deteriorating", "pressured"}:
            continue                    # pressured = estimates being
        # cut — don't call an entry into a downward revision cycle
        # earnings proximity — a 5-20d swing that hits the print in ≤3d
        # is a coin flip wearing a thesis; the board already penalizes
        # the score, the calls engine excludes it outright
        if r.get("days_to_earnings") is not None \
                and r["days_to_earnings"] <= 3:
            continue
        hit = _prior_hit(sym, state, dip)
        if weight(f"gate:{state}|{dip or 'none'}") == "off":
            continue
        if dip == "turning_up":
            pass
        elif dip == "stabilizing" and (hit or 0) >= 0.55:
            pass
        elif dip == "still_falling" and (hit or 0) >= 0.60 \
                and fund == "accelerating":
            pass
        elif dip in (None, "") :
            pass                                # state itself is clean
        else:
            continue
        cands.append({**r, "_prior_hit": hit})

    cands.sort(key=lambda r: -(r.get("score") or 0))
    picks = cands[:_TOP]
    if not picks:
        return {"date": str(today), "calls": [], "note": "no qualified "
                "setup today — no-trade is a valid call"}

    books = bars_mod.load([p["symbol"] for p in picks], days=90)
    # the readiness-board rank is shown beside the composite score —
    # two different answers to 'how good is this setup'
    try:
        rkmap = {r["symbol"]: r["rank"] for r in db.execute_query(
            "SELECT symbol, rank FROM readiness_evals"
            " WHERE use_case='swing'"
            " AND as_of=(SELECT max(as_of) FROM readiness_evals"
            "  WHERE use_case='swing')")}
    except Exception:
        rkmap = {}
    # learned plan params — meta widens stops when graded calls show
    # stop-outs that recovered, tightens targets when they expire
    _bm, _rr = weight("calls:band_mult"), weight("calls:rr_target")
    band_mult = _bm if isinstance(_bm, (int, float)) else 1.5
    rr_t = _rr if isinstance(_rr, (int, float)) else 2.0
    made = []
    for i, p in enumerate(picks, 1):
        sym = p["symbol"]
        bars = books.get(sym) or []
        px = bars[-1].close if bars else None
        if not px:
            continue
        atr_pct = (p.get("momentum_detail") or {}).get("atr_pct")
        band = min(0.10, max(0.04, band_mult * (atr_pct or 0.03)))
        stop = round(px * (1 - band), 2)
        tgt = round(px + rr_t * (px - stop), 2)
        row = {"call_date": str(today), "rank": i, "symbol": sym,
               "score": round(p.get("score") or 0, 1),
               "entry_px": round(px, 2), "stop_px": stop,
               "target_px": tgt,
               "rr": round((tgt - px) / (px - stop), 2),
               "state": p.get("momentum") or p.get("momentum_state"),
               "dip_phase": p.get("dip_phase"),
               "swing_rank": rkmap.get(sym),
               "evidence": (p.get("why") or [])[:8]}
        db.execute_update(
            "INSERT INTO daily_calls (call_date, rank, symbol, score,"
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
    return {"date": str(today), "calls": made}


def report(days: int = 10) -> dict[str, Any]:
    """Recent calls — today's first, then history for accountability."""
    from app.database import db
    rows = db.execute_query(
        "SELECT * FROM daily_calls ORDER BY call_date DESC, rank"
        " LIMIT :n", {"n": days * _TOP})
    from app.signals import posture as _pos
    return {"calls": rows, "record": calls_record(),
            "posture": _pos.current()}


def evaluate_calls(days_back: int = 60) -> dict[str, Any]:
    """Grade journaled calls — the swing-engine's training ledger.

    Per call: call-day EOD close (did the entry fill well?), then the
    plan's resolution — first touch of stop vs target — plus 5/10/20d
    closes and excursions. Conservative rule: stop+target inside one
    bar counts as stop_first (intraday order unknowable on daily bars).
    Rows stay 'open' and keep updating until resolved or the 20d
    window expires. Runs in the nightly outcomes job — idempotent."""
    from app.database import db
    from app.signals.board_tracking import _bars
    rows = db.execute_query(
        """SELECT c.id, c.call_date, c.symbol, c.entry_px, c.stop_px,
                  c.target_px, o.id AS oid, o.resolution,
                  o.ret_5d IS NOT NULL AS has5,
                  o.ret_10d IS NOT NULL AS has10,
                  o.ret_20d IS NOT NULL AS has20
           FROM daily_calls c
           LEFT JOIN daily_call_outcomes o ON o.call_id = c.id
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

            # first-touch resolution over the plan window
            res, res_date, held = c["resolution"] or "open", None, None
            if res == "open" and fwd:
                for i, b in enumerate(fwd[:20], 1):
                    hit_stop = stop and b.low <= stop
                    hit_tgt = tgt and b.high >= tgt
                    if hit_stop and hit_tgt:
                        res, res_date, held = ("stop_first",
                                               b.timestamp.date(), i)
                        break          # conservative: same bar = stop
                    if hit_stop:
                        res, res_date, held = ("stop_first",
                                               b.timestamp.date(), i)
                        break
                    if hit_tgt:
                        res, res_date, held = ("target_first",
                                               b.timestamp.date(), i)
                        break
                if res == "open" and len(fwd) >= 20:
                    res, res_date, held = ("expired",
                                           fwd[19].timestamp.date(), 20)

            def _ret(n):
                w = fwd[:n]
                if len(w) < min(n, 2):
                    return None
                return round((w[-1].close - entry) / entry * 100, 2)

            window = fwd[:20]
            mfe = (round((max(b.high for b in window) / entry - 1)
                         * 100, 2) if window else None)
            mae = (round((min(b.low for b in window) / entry - 1)
                         * 100, 2) if window else None)
            vals = {"eod": round(eod, 2),
                    "re": round((eod - entry) / entry * 100, 2),
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
                    """INSERT INTO daily_call_outcomes
                       (call_id, call_date, symbol, entry_px, stop_px,
                        target_px, eod_close, ret_eod, ret_5d, ret_10d,
                        ret_20d, mfe, mae, resolution, resolved_date,
                        days_held)
                       VALUES (:cid,:d,:s,:e,:sp,:t,:eod,:re,:r5,:r10,
                        :r20,:mfe,:mae,:res,:rd,:dh)
                       ON CONFLICT (call_id) DO NOTHING""", vals)
            else:
                db.execute_update(
                    """UPDATE daily_call_outcomes SET
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


def calls_record() -> dict[str, Any]:
    """Track record of the calls engine itself — resolution mix,
    entry quality (ret_eod), and hit rate. The training readout."""
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
           FROM daily_call_outcomes""")
    return rows[0] if rows else {}


def fund_momentum(limit: int = 10) -> list[dict[str, Any]]:
    """Fundamental-momentum radar — names whose fundamentals are
    RAPIDLY IMPROVING (consecutive snapshot improvement + revision
    drift) while the tape isn't broken. The 'add to portfolio' list.

    Score = state progression + metric deltas + flywheel accel.
    Improving fundamentals + healthy tape = add candidate.
    Improving fundamentals + falling tape = early — watchlist only."""
    from app.database import db
    snaps = db.execute_query(
        """SELECT DISTINCT ON (symbol) symbol, as_of, state, metrics
           FROM fundamental_snapshots ORDER BY symbol, as_of DESC""")
    prev = {r["symbol"]: r for r in db.execute_query(
        """SELECT DISTINCT ON (symbol) symbol, as_of, state, metrics
           FROM fundamental_snapshots s
           WHERE as_of < (SELECT max(as_of) FROM fundamental_snapshots s2
                          WHERE s2.symbol = s.symbol)
           ORDER BY symbol, as_of DESC""")}
    fw = {r["symbol"]: r for r in db.execute_query(
        "SELECT symbol, gap_score, rev_accel, est_revision_pct,"
        " muted_reaction FROM symbol_flywheel")}
    mom = {r["symbol"]: r for r in db.execute_query(
        "SELECT symbol, momentum_state, momentum_detail FROM stocks")}
    rank = {"accelerating": 4, "improving": 3, "stable": 2,
            "turnaround": 2, "pressured": 1,
            "watch": 1, "declining": 0, "deteriorating": -1}
    out = []
    for r in snaps:
        sym = r["symbol"]
        cur, prv = r["state"], (prev.get(sym) or {}).get("state")
        m, mp = (r.get("metrics") or {}), ((prev.get(sym) or {})
                                         .get("metrics") or {})
        f = fw.get(sym) or {}
        tape = (mom.get(sym) or {})
        state = tape.get("momentum_state")
        if state in {"knife", "capitulation", "downtrend", "breakdown",
                     "rolling_over", "climax"}:
            tape_ok = False
        else:
            tape_ok = True
        score = 0.0
        why = []
        if rank.get(cur or "", 0) > rank.get(prv or "", 0):
            score += 25
            why.append(f"fund flag {prv or '—'}→{cur}")
        elif cur == "accelerating":
            score += 12
            why.append("still accelerating")
        rg_d = (m.get("rev_growth") or 0) - (mp.get("rev_growth") or 0)
        gm_d = (m.get("gross_margin") or 0) - (mp.get("gross_margin") or 0)
        if rg_d > 0.01:
            score += 15; why.append(f"rev growth +{rg_d*100:.0f}pts")
        if gm_d > 0.01:
            score += 10; why.append(f"GM +{gm_d*100:.0f}pts")
        if (f.get("rev_accel") or 0) > 0:
            score += 10; why.append("rev accelerating (flywheel)")
        if (f.get("est_revision_pct") or 0) > 0:
            score += 12
            why.append(f"estimates revised up {f['est_revision_pct']:.0f}%")
        if f.get("muted_reaction"):
            score += 8; why.append("market hasn't repriced it")
        if tape_ok:
            score += 5
        else:
            why.append(f"tape {state} — early, watchlist")
        if score >= 30:
            vs50 = ((tape.get("momentum_detail") or {})
                    .get("vs_sma50"))
            out.append({"symbol": sym, "fm_score": round(score, 1),
                        "fund_state": cur, "tape": state,
                        "dip_phase": (tape.get("momentum_detail") or {})
                        .get("dip_phase"),
                        "extended": bool(vs50 and vs50 > 0.08),
                        "why": why})
    out.sort(key=lambda r: -r["fm_score"])
    return out[:limit]
