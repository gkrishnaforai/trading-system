"""Crash alpha — the PUT side of the hedge book, plus the PUT→CALL
rotation link. Two scores, both journaled + graded so the learning
loop can calibrate them:

  PUT_ENTRY_SCORE (per symbol, 0-100)
    "Good company, temporarily overextended" — the names a put spread
    pays on AND that stay rotatable into LEAPS calls afterward. Needs
    extension + a fresh crack; extension alone isn't shortable.

      crack     rolling_over +30 · breakdown +18 · climax +12
      extension rsi≥75 +14 · 68-75 +8 · pct_b>0.9 +10 · vs_200dma
                >40% +10 / >25% +5 · vs_50dma >15% +4
      fuel      fwd P/E ≥40 +8 · cyclical +5
      quality   fundamentals intact → +6 and flagged rotatable
                (this becomes the CALL candidate later);
                declining → +10 but marked one-way
      gates     earnings ≤7d excluded (binary), score <35 suppressed

  CAPITULATION_SCORE (market, 0-100)
    "Is the washout deep enough to monetize hedges and start shopping
    calls?" Built from stored internals — zero fetches:

      VIX       ≥35 +30 · 28-35 +20 · 22-28 +10
      breadth   pct_above_50 ≤15 +20 · ≤25 +12 · ≤35 +5
                pct_20d_low ≥40 +15 · ≥25 +8
      washout   % universe in capitulation/knife ≥40 +15 · ≥25 +8
      tape      SPY dd from 52w high ≥20% +10 · ≥15% +5
      regime    broad_deleveraging +5 (the tail is fattest exactly
                when the score should say so)

    ≥60 = capitulation zone: final monetization tranche + flip the
    board to LEAPS-call shopping. The hedge ladder handles the
    progressive trims; this score is the "sell the insurance, buy the
    recovery" trigger.

  REDEPLOY LINK
    When a hedge spreads hits ≥80% of width or the score crosses 60,
    redeploy_candidates() ranks the quality-at-distress names — the
    PUT→CALL rotation the desk document describes. Proceeds ×
    redeploy fraction, advisory only.

  LEARNING
    snapshot() journals the day's scores (crash_alpha_snapshots,
    migration 091) — called from the momentum job so it accrues
    without page views. evaluate() grades at 20/60d: cap_score≥60 →
    did SPY bounce? put candidates → did they underperform?
    Meta reads the graded mix into alpha:* threshold weights.

  IV GATE
    Buying puts at max panic = buying insurance at peak premium.
    iv_gate() returns an entry-quality read from iv_snapshots;
    stubbed 'insufficient history' until ~20 trading days accrue.
"""
from __future__ import annotations

import json
import logging
import statistics as st
from datetime import date
from typing import Any, Optional

logger = logging.getLogger(__name__)

_PUT_MIN = 35                # suppress noise below this
_CAP_ZONE = 60               # capitulation threshold (meta-adjustable)


def _learned(key: str, default: float) -> float:
    """engine_weights scalar — meta-learned overrides, defaults until
    the graded cohort is big enough to write one."""
    try:
        from app.database import db
        rows = db.execute_query(
            "SELECT value FROM engine_weights WHERE key=:k",
            {"k": key})
        if not rows:
            return default
        v = rows[0]["value"]
        if isinstance(v, dict):
            v = v.get("value", default)
        return float(v)
    except Exception:
        return default


# ---------------------------------------------------- PUT_ENTRY_SCORE

def put_entry_scores(limit: int = 8) -> list[dict[str, Any]]:
    """Rank the alpha-put candidates across the covered universe —
    delegates to the single shared engine signals.put_entry.score so
    the board ranker and the Stock-page readiness lane can never
    disagree. Keeps the scan-level contract: earnings ≤7d exclusion,
    put_min floor, rotatable flag (category == valuation_put)."""
    from app.database import db
    from app.signals import put_entry
    mom = {r["symbol"]: r for r in db.execute_query(
        "SELECT symbol, momentum_state, momentum_detail,"
        " fundamental_state, next_earnings_date FROM stocks"
        " WHERE momentum_state IS NOT NULL")}
    fw = {r["symbol"]: r for r in db.execute_query(
        "SELECT symbol, fwd_pe, rev_growth, eps_growth,"
        " est_revision_pct FROM symbol_flywheel")}
    fv = {r["symbol"]: r.get("scenario_fair_values") for r in
          db.execute_query(
              "SELECT DISTINCT ON (symbol) symbol,"
              " scenario_fair_values FROM fair_value_v2_runs"
              " ORDER BY symbol, as_of DESC, run_id DESC")}
    px = {r["symbol"]: float(r["close"]) for r in db.execute_query(
        "SELECT DISTINCT ON (symbol) symbol, close FROM daily_bars"
        " ORDER BY symbol, date DESC")}
    regime = put_entry._regime()

    out = []
    today = date.today()
    put_min = _learned("alpha:put_min", _PUT_MIN)
    for sym, m in mom.items():
        state = m["momentum_state"]
        # two entry species: crack-at-extension (valuation/top-tick
        # scorer) and failed-bounce continuation (lower-high inside a
        # de-risking theme — the Oct-7-26 ARM/CRWV/ORCL gap)
        crack = state in {"rolling_over", "breakdown", "climax",
                          "knife", "capitulation"}
        cont = state in {"pullback", "downtrend"}
        if not crack and not cont:
            continue
        d = m.get("momentum_detail") or {}

        # earnings gate — a put spread that crosses the print is a
        # binary bet on the reaction, not insurance on the tape
        ned = m.get("next_earnings_date")
        if ned and (ned - today).days <= 7:
            continue

        if crack:
            res = put_entry.score(
                d, state, m.get("fundamental_state"),
                fw.get(sym) or {}, fv.get(sym) or {},
                px.get(sym), regime, sym=sym)
            mode = "valuation"
        else:
            res = put_entry.continuation_score(
                d, state, fw.get(sym) or {},
                px.get(sym), regime, sym=sym)
            mode = "continuation"
        if res["chase_block"] or res["score"] < put_min:
            continue
        # narrative-risk gate — an improving story can gap +25% on one
        # headline regardless of tape extension. Gate, not score adj.
        nr = put_entry.narrative_risk(
            m.get("fundamental_state"), fw.get(sym) or {}, sym=sym,
            next_earnings=m.get("next_earnings_date"))
        if nr["flag"] == "high":
            continue
        factors = sorted(res.get("factors") or [],
                         key=lambda f: -f["pts"])
        why = " · ".join(f'{f["name"]} {f["pts"]:.0f}/{f["weight"]}'
                         for f in factors if f["pts"] > 0)[:220]
        out.append({"symbol": sym, "score": res["score"],
                    "band": res["band"], "category": res["category"],
                    "state": state, "mode": mode,
                    "rotatable": res["category"] == "valuation_put",
                    "rsi": round(d["rsi"], 0) if d.get("rsi") else None,
                    "vs_sma200": round(d["vs_sma200"] * 100, 0)
                    if d.get("vs_sma200") is not None else None,
                    "stage": res.get("stage"),
                    "why": why})
    return sorted(out, key=lambda r: -r["score"])[:limit]


# --------------------------------------------------- CAPITULATION_SCORE

def capitulation_score() -> dict[str, Any]:
    """Market-level washout composite — the 'monetize the hedge, shop
    the calls' trigger. Stored inputs only."""
    from app.database import db
    from app.market_data import bars as bars_mod

    score, why = 0.0, []

    # VIX — stored bars or the latest regime snapshot
    vix = None
    try:
        vb = bars_mod.load(["^VIX"], days=5).get("^VIX") or []
        vix = vb[-1].close if vb else None
    except Exception:
        pass
    if vix is None:
        rs = db.execute_query(
            "SELECT vix FROM regime_snapshots WHERE vix IS NOT NULL"
            " ORDER BY as_of DESC LIMIT 1")
        vix = rs[0]["vix"] if rs else None
    if vix is not None:
        if vix >= 35:
            score += 30
            why.append(f"VIX {vix:.0f} — panic pricing")
        elif vix >= 28:
            score += 20
            why.append(f"VIX {vix:.0f} — stress")
        elif vix >= 22:
            score += 10
            why.append(f"VIX {vix:.0f} — elevated")

    # breadth internals — stored by the momentum job
    try:
        from app.signals import breadth as _br
        b = _br.read() or {}
    except Exception:
        b = {}
    a50, l20 = b.get("pct_above_50"), b.get("pct_20d_low")
    if a50 is not None:
        if a50 <= 15:
            score += 20
            why.append(f"{a50:.0f}% above 50dma — washed out")
        elif a50 <= 25:
            score += 12
            why.append(f"{a50:.0f}% above 50dma — thin tape")
        elif a50 <= 35:
            score += 5
            why.append(f"{a50:.0f}% above 50dma")
    if l20 is not None:
        if l20 >= 40:
            score += 15
            why.append(f"{l20:.0f}% at 20d lows — capitulation breadth")
        elif l20 >= 25:
            score += 8
            why.append(f"{l20:.0f}% at 20d lows")

    # universe washout — share of names in capitulation/knife states
    try:
        w = db.execute_query(
            """SELECT round(100.0 * count(*) FILTER (
                   WHERE momentum_state IN ('capitulation','knife'))
                   / nullif(count(*),0), 1) w
               FROM stocks WHERE momentum_state IS NOT NULL""")
        washed = float(w[0]["w"]) if w and w[0]["w"] else 0.0
        if washed >= 40:
            score += 15
            why.append(f"{washed:.0f}% of universe washed — extreme")
        elif washed >= 25:
            score += 8
            why.append(f"{washed:.0f}% of universe washed")
    except Exception:
        washed = None

    # SPY drawdown from 52w high
    dd52 = None
    try:
        sb = bars_mod.load(["SPY"], days=270).get("SPY") or []
        if sb:
            hi = max(b.high for b in sb)
            dd52 = (sb[-1].close / hi - 1) if hi else None
    except Exception:
        pass
    if dd52 is not None:
        if dd52 <= -0.20:
            score += 10
            why.append(f"SPY {dd52 * 100:.0f}% off high — bear depth")
        elif dd52 <= -0.15:
            score += 5
            why.append(f"SPY {dd52 * 100:.0f}% off high")

    # regime character — deleveraging is where capitulation forms
    dip_char = None
    try:
        rs = db.execute_query(
            "SELECT dip_character FROM regime_snapshots"
            " ORDER BY as_of DESC LIMIT 1")
        dip_char = rs[0]["dip_character"] if rs else None
        if dip_char == "broad_deleveraging":
            score += 5
            why.append("broad_deleveraging — everything falls together")
    except Exception:
        pass

    cap_zone = _learned("alpha:cap_zone", _CAP_ZONE)
    score = round(min(100.0, score))
    tier = ("capitulating" if score >= 80 else
            "cap_zone" if score >= cap_zone else
            "watch" if score >= 35 else "none")
    return {"score": score, "tier": tier, "vix": vix,
            "pct_above_50": a50, "pct_20d_low": l20,
            "pct_washed": washed, "spy_dd52w": round(dd52 * 100, 1)
            if dd52 is not None else None,
            "dip_character": dip_char, "why": why}


# ------------------------------------------------------------ IV gate

def iv_gate() -> dict[str, Any]:
    """Is insurance reasonably priced? iv_snapshots needs ~20 trading
    days of accrual before a rank means anything — until then the gate
    honestly reports 'insufficient history' rather than guess."""
    from app.database import db
    try:
        rows = db.execute_query(
            "SELECT count(DISTINCT as_of) n, min(as_of) first,"
            " max(as_of) last FROM iv_snapshots")
        n = int(rows[0]["n"]) if rows else 0
        latest = db.execute_query(
            "SELECT atm_iv, hv20 FROM iv_snapshots WHERE symbol='QQQ'"
            " ORDER BY as_of DESC LIMIT 1")
    except Exception:
        return {"status": "insufficient history",
                "note": "iv_snapshots table not readable yet"}
    if n < 20:
        return {"status": "insufficient history", "days": n,
                "note": f"{n}/20 days accrued — IV rank needs a "
                        "month of prints before 'expensive' means "
                        "anything"}
    iv = float(latest[0]["atm_iv"]) if latest else None
    ranks = db.execute_query(
        "SELECT atm_iv FROM iv_snapshots WHERE symbol='QQQ'")
    ivs = [float(r["atm_iv"]) for r in ranks if r["atm_iv"]]
    rank = (round(100 * sum(1 for x in ivs if x <= iv) / len(ivs))
            if iv is not None and ivs else None)
    verdict = ("expensive — spreads only, prefer wider shorts"
               if rank and rank >= 75 else
               "cheap-ish — insurance reasonably priced"
               if rank is not None and rank <= 40 else
               "neutral")
    return {"status": "live", "days": n, "iv_rank": rank,
            "verdict": verdict}


# -------------------------------------------------------- redeploy link

def redeploy_candidates(proceeds: float, limit: int = 5
                        ) -> list[dict[str, Any]]:
    """The PUT→CALL rotation — quality names at distressed prices to
    spend hedge proceeds on. Fundamentals intact + washed momentum;
    sized to the proceeds so the human sees real allocations."""
    from app.signals.daily_board import _accumulate_scores
    rows = _accumulate_scores()
    out = []
    for r in rows:
        fund = r.get("fund_state") or r.get("fundamental_state") or ""
        if fund in {"declining", "deteriorating", "pressured"}:
            continue                    # broken thesis — not a CALL
        d = r.get("momentum_detail") or {}
        dip = r.get("dip_phase")
        state = r.get("momentum") or r.get("momentum_state")
        # want capitulation that is healing, or an intact name dragged
        # down with the tape — not knives still falling
        if state in {"knife", "breakdown"}:
            continue
        if dip not in {"turning_up", "stabilizing"} \
                and state != "capitulation":
            continue
        out.append({"symbol": r["symbol"],
                    "score": round(r.get("score") or 0, 1),
                    "momentum": state, "dip_phase": dip,
                    "dd52w": round((d.get("dd52w") or 0) * 100, 0),
                    "rsi": round(d.get("rsi"), 0)
                    if d.get("rsi") else None,
                    "note": "LEAPS call candidate — thesis intact, "
                            "price distressed"})
        if len(out) >= limit:
            break
    for i, c in enumerate(out):
        c["alloc_pct"] = round([40, 25, 15, 10, 10][i] if i < 5
                               else 5)
        c["alloc_usd"] = round(proceeds * c["alloc_pct"] / 100)
    return out


# ------------------------------------------------------------ composite

def state() -> dict[str, Any]:
    """The crash-alpha card — cap score, top put candidates, IV gate,
    and (when the hedge has monetized) the redeploy list."""
    from app.database import db
    cap = capitulation_score()
    puts = put_entry_scores()
    gate = iv_gate()

    # redeploy link fires when a hedge realized ≥80% of width recently
    # or cap score is in the zone — cash is ammo either way
    proceeds = 0.0
    try:
        hp = db.execute_query(
            """SELECT mark_value, realized_pct FROM hedge_positions
               WHERE status IN ('trimmed','closed')
                 AND realized_pct >= 80
                 AND updated_at > now() - interval '30 days'""")
        proceeds = sum(float(h["mark_value"] or 0)
                       for h in hp) * 100   # per-contract → dollars
    except Exception:
        pass
    cap_zone = _learned("alpha:cap_zone", _CAP_ZONE)
    deploy = (proceeds > 0 or cap["score"] >= cap_zone)
    rd = (redeploy_candidates(proceeds or 10000)
          if deploy else [])

    return {"capitulation": cap, "put_candidates": puts,
            "iv_gate": gate,
            "redeploy": {"armed": deploy,
                         "proceeds_est": round(proceeds),
                         "candidates": rd},
            "cap_zone": cap_zone}


# ------------------------------------------------------- journal + grade

def snapshot() -> dict[str, Any]:
    """Journal the day's crash-alpha read — idempotent per day, called
    from the momentum job so it accrues without page views."""
    from app.database import db
    cap = capitulation_score()
    puts = put_entry_scores(limit=5)
    try:
        db.execute_update(
            """INSERT INTO crash_alpha_snapshots
               (as_of, capitulation_score, cap_tier, put_candidates,
                spy_vs_200, vix, pct_above_50, pct_20d_low,
                pct_washed, dip_character, payload)
               VALUES (:d, :cs, :ct, CAST(:pc AS jsonb), :s2, :v,
                       :a50, :l20, :w, :dc, CAST(:p AS jsonb))
               ON CONFLICT (as_of) DO NOTHING""",
            {"d": date.today(), "cs": cap["score"], "ct": cap["tier"],
             "pc": json.dumps(puts), "s2": cap.get("spy_dd52w"),
             "v": cap.get("vix"), "a50": cap.get("pct_above_50"),
             "l20": cap.get("pct_20d_low"), "w": cap.get("pct_washed"),
             "dc": cap.get("dip_character"),
             "p": json.dumps({"cap": cap, "puts": puts}, default=str)})
        return {"journaled": True, "cap": cap["score"],
                "puts": len(puts)}
    except Exception as exc:
        logger.debug("crash-alpha snapshot: %s", exc)
        return {"journaled": False, "error": str(exc)}


def evaluate(days_back: int = 120) -> dict:
    """Grade journaled reads: cap≥60 → did SPY bounce in 20d? Put
    candidates → did they underperform SPY (the alpha-put test)?"""
    from app.database import db
    from app.signals.board_tracking import _bars
    rows = db.execute_query(
        """SELECT id, as_of, cap_tier, put_candidates
           FROM crash_alpha_snapshots
           WHERE as_of > now()::date - :d
             AND spy_ret_20d IS NULL""", {"d": days_back})
    done = 0
    for r in rows:
        try:
            spy = _bars("SPY", r["as_of"])
            fwd = [b for b in spy if b.timestamp.date() > r["as_of"]]
            if len(fwd) < 20:
                continue
            entry = spy[0].close
            r20 = round((fwd[19].close / entry - 1) * 100, 2)
            r60 = (round((fwd[59].close / entry - 1) * 100, 2)
                   if len(fwd) >= 60 else None)
            cap_ok = (r20 > 2.0 if r["cap_tier"]
                      in ("cap_zone", "capitulating") else None)
            # put candidates: share that fell over the next 20d
            cands = r["put_candidates"] or []
            if isinstance(cands, str):
                cands = json.loads(cands)
            hits = []
            for c in cands:
                bars = _bars(c["symbol"], r["as_of"])
                cf = [b for b in bars if b.timestamp.date() > r["as_of"]]
                if len(cf) >= 20:
                    ret = cf[19].close / bars[0].close - 1
                    hits.append(ret < r20 / 100)  # underperform SPY
            put_hr = (round(100 * sum(hits) / len(hits), 1)
                      if hits else None)
            db.execute_update(
                """UPDATE crash_alpha_snapshots SET
                    spy_ret_20d=:r20, spy_ret_60d=:r60,
                    cap_bounce=:ok, put_hit_rate=:hr,
                    graded_at=now() WHERE id=:i""",
                {"r20": r20, "r60": r60, "ok": cap_ok,
                 "hr": put_hr, "i": r["id"]})
            done += 1
        except Exception as exc:
            logger.debug("crash-alpha grade %s: %s", r["as_of"], exc)
    return {"evaluated": done}


def record() -> dict[str, Any]:
    """The graded read — is the cap score actually calling bounces,
    and do put candidates actually underperform?"""
    from app.database import db
    rows = db.execute_query(
        """SELECT cap_tier, count(*) n,
              round(avg(spy_ret_20d)::numeric, 2) avg_spy_20d,
              round(100.0 * avg(CASE WHEN cap_bounce THEN 1
                                ELSE 0 END), 0) bounce_rate,
              round(avg(put_hit_rate)::numeric, 1) avg_put_hit
           FROM crash_alpha_snapshots
           WHERE spy_ret_20d IS NOT NULL
           GROUP BY cap_tier ORDER BY cap_tier""")
    n = db.execute_query(
        "SELECT count(*) n FROM crash_alpha_snapshots"
        " WHERE spy_ret_20d IS NOT NULL")
    return {"cells": rows, "graded": n[0]["n"] if n else 0}


# ------------------------------------------------------------- backtest

def backtest() -> dict[str, Any]:
    """Replay the capitulation score over stored daily_bars history —
    the honest 'would this have fired usefully?' check before trusting
    a threshold.

    What's replayable: VIX level, SPY drawdown-from-high, universe
    breadth (pct_above_50 / pct_20d_low) — all recomputed per day from
    canonical bars. What's NOT: momentum_state washout (state machine
    isn't journaled per-day) and dip_character (needs SMH/defensive
    RS) — the replay omits their +15/+5 max, so backtest scores
    UNDERSTATE the live score by ≤20pts. Grading question stays the
    same: score≥60 days → did SPY bounce in 20d?"""
    from app.database import db
    rows = db.execute_query(
        """
        WITH sym_day AS (
            SELECT b.date, b.symbol, b.close, b.high, b.low,
                   AVG(b.close) OVER (PARTITION BY b.symbol
                       ORDER BY b.date ROWS BETWEEN 49 PRECEDING
                       AND CURRENT ROW)            AS sma50,
                   MIN(b.low) OVER (PARTITION BY b.symbol
                       ORDER BY b.date ROWS BETWEEN 20 PRECEDING
                       AND 1 PRECEDING)            AS lo20
            FROM daily_bars b)
        , breadth AS (
            SELECT date,
                   round(100.0*avg(CASE WHEN close>sma50
                         THEN 1 ELSE 0 END),1)  pct_above_50,
                   round(100.0*avg(CASE WHEN low<=lo20
                         THEN 1 ELSE 0 END),1)  pct_20d_low
            FROM sym_day WHERE sma50 IS NOT NULL
            GROUP BY date)
        , spy AS (
            SELECT date, close,
                   MAX(high) OVER (ORDER BY date
                       ROWS BETWEEN 251 PRECEDING AND CURRENT ROW) hi52,
                   LEAD(close, 20) OVER (ORDER BY date) f20,
                   LEAD(close, 60) OVER (ORDER BY date) f60
            FROM daily_bars WHERE symbol='SPY')
        , vix AS (
            SELECT date, close vix FROM daily_bars
            WHERE symbol='^VIX')
        SELECT s.date, s.close spy, s.f20, s.f60,
               s.close/s.hi52 - 1 AS dd52, v.vix,
               br.pct_above_50, br.pct_20d_low
        FROM spy s
        LEFT JOIN vix v ON v.date = s.date
        LEFT JOIN breadth br ON br.date = s.date
        WHERE s.f20 IS NOT NULL ORDER BY s.date""")
    if not rows:
        return {"note": "no stored bars to replay"}

    def _score(r):
        s = 0
        v = r["vix"]
        if v is not None:
            s += 30 if v >= 35 else 20 if v >= 28 else 10 if v >= 22 else 0
        a, l = r["pct_above_50"], r["pct_20d_low"]
        if a is not None:
            s += 20 if a <= 15 else 12 if a <= 25 else 5 if a <= 35 else 0
        if l is not None:
            s += 15 if l >= 40 else 8 if l >= 25 else 0
        dd = r["dd52"]
        if dd is not None:
            s += 10 if dd <= -0.20 else 5 if dd <= -0.15 else 0
        return s

    buckets: dict[str, list] = {"<35": [], "35-59": [],
                              "60-79": [], "80+": []}
    for r in rows:
        sc = _score(r)
        fwd = (r["f20"] / r["spy"] - 1) * 100
        (buckets["<35"] if sc < 35 else
         buckets["35-59"] if sc < 60 else
         buckets["60-79"] if sc < 80 else
         buckets["80+"]).append((sc, fwd, r["f60"] / r["spy"] - 1
                                 if r["f60"] else None))
    cells = []
    for k, v in buckets.items():
        if len(v) < 3:
            continue
        f20 = [x[1] for x in v]
        cells.append({
            "score_band": k, "n": len(v),
            "avg_spy_fwd20d": round(st.mean(f20), 2),
            "bounce_rate": round(100 * sum(1 for x in f20
                                           if x > 0) / len(f20)),
            "worst_20d": round(min(f20), 2)})
    fired = [x for band in ("60-79", "80+")
             for x in buckets.get(band, [])]
    return {"days_replayed": len(rows), "cells": cells,
            "zone_fires": len(fired),
            "zone_avg_bounce": round(st.mean([x[1] for x in fired]), 2)
            if fired else None,
            "honest": ("replay omits momentum-washout (+15) and "
                       "deleveraging (+5) components — live scores "
                       "run up to 20pts hotter than replayed")}
