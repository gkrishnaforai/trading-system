"""PUT_ENTRY_SCORE — directional long-dated put entry.

Two deliberately separate species (the user's frame):

  A. valuation_put — STRONG business + extreme valuation + extension
     → exhaustion → support failure. Betting on multiple compression,
     not business failure; the post-put PUT→CALL cycle wants the
     business intact on the other side. The preferred core setup.
  B. fundamental_break_put — deteriorating fundamentals + breakdown +
     revisions cut. Bigger potential decline but unknowable bottom —
     NOT core for long-dated puts; labelled and treated separately.

Score is staged, never raw overbought: extension identifies the
candidate, exhaustion + support failure earn the entry. 'already
broke' is a no-chase state — the entry was earlier.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Optional

_TIER = {"major": 85, "add": 70, "starter": 55, "watch": 40}


def _regime() -> dict:
    """Latest market-risk card — raw stance/vix/SPY leg PLUS the
    canonical defensive state (single market-weakness truth; the raw
    fields stay for display, scoring keys off defensive_state)."""
    from app.database import db
    out: dict = {}
    try:
        r = db.execute_query(
            "SELECT stance, vix, spy_vs_200, p_deeper, p_bull"
            " FROM regime_snapshots ORDER BY as_of DESC LIMIT 1")
        out = dict(r[0]) if r else {}
    except Exception:
        pass
    try:
        from app.market_regime.defensive_store import (
            DefensiveTransitionStore)
        d = DefensiveTransitionStore().latest()
        if d:
            out["defensive_state"] = d.get("stage")
            out["defensive_score"] = d.get("score")
    except Exception:
        pass
    return out


def _rotation(rotation: Optional[dict]) -> Optional[dict]:
    """Environment permission — caller may inject a point-in-time row
    for replays; otherwise today's persisted/computed score."""
    if rotation is not None:
        return rotation
    try:
        from app.signals import theme_rotation
        return theme_rotation.current()
    except Exception:
        return None


def _iv_for(sym: Optional[str]) -> Optional[dict]:
    """Latest ATM-IV-vs-realized snapshot — how rich the put premium
    is. None when no coverage; the leg then scores 0 but says so."""
    if not sym:
        return None
    from app.database import db
    try:
        r = db.execute_query(
            "SELECT as_of, atm_iv, hv20, iv_hv FROM iv_snapshots"
            " WHERE symbol=:s ORDER BY as_of DESC LIMIT 1",
            {"s": sym.upper()})
        return dict(r[0]) if r else None
    except Exception:
        return None


def _iv_age(iv: dict) -> str:
    """Snapshot-age suffix — prints only land during market hours, so a
    stale iv_hv should say so rather than read as a fresh premium."""
    try:
        as_of = iv.get("as_of")
        days = (date.today() - as_of).days
        return "" if days <= 0 else f" [{as_of}, {days}d old]"
    except Exception:
        return ""


def _catalyst(sym: Optional[str], fly: dict) -> dict:
    """Is there a scheduled repricing event inside the put horizon,
    plus evidence the fundamental story is already cracking.
    Returns {pts_cap8, notes} — deterministic facts only."""
    pts, notes = 0.0, []
    if sym:
        from app.database import db
        try:
            r = db.execute_query(
                "SELECT earnings_date FROM earnings_calendar"
                " WHERE symbol=:s AND earnings_date >= CURRENT_DATE"
                " ORDER BY earnings_date LIMIT 1", {"s": sym.upper()})
            if r:
                d = (r[0]["earnings_date"] - date.today()).days
                if d <= 150:
                    pts += 4
                    notes.append(f"earnings in {d}d — repricing "
                                 f"event inside horizon")
                else:
                    notes.append(f"next earnings {d}d out — outside "
                                 f"the near window")
        except Exception:
            pass
        try:
            hw = db.execute_query(
                "SELECT tier, summary FROM tailwinds"
                " WHERE symbol=:s AND direction='headwind'"
                " AND status='active'", {"s": sym.upper()})
            hw = [h for h in hw
                  if h["tier"] in ("announced", "revenue", "shipping")]
            if hw:
                pts += 2
                notes.append(f"{len(hw)} confirmed headwind(s) "
                             f"journaled — e.g. "
                             f"{(hw[0]['summary'] or '')[:80]}")
        except Exception:
            pass
    rev = fly.get("est_revision_pct")
    if rev is not None and rev < 0:
        pts += 2
        notes.append(f"estimate revisions negative "
                     f"({rev:+.1f}% 90d)")
    return {"pts": min(8.0, pts),
            "note": " · ".join(notes) if notes
                    else "no scheduled catalyst or crack in the story"}


def narrative_risk(fund: Optional[str], fly: dict,
                   sym: Optional[str] = None,
                   next_earnings: Any = None) -> dict[str, Any]:
    """Binary squeeze-risk flag for bear-alpha candidates.

    A great story that is actively *improving* can gap +25% on one
    headline — government contract, hyperscaler deal, guidance raise —
    no matter how extended the tape. This is a GATE, never a score
    adjustment: HIGH suppresses the candidate outright.

    HIGH only on hard binary risk — an imminent earnings print or a
    confirmed tailwind already repricing the story. "Growing business
    with positive revisions" ALONE is now MEDIUM (annotate, don't
    suppress): it vetoed every A-type candidate on Oct-7-26 — the
    'excellent company, falling stock' puts are the preferred species,
    and a healthy story is their entry criterion, not a blocker.
      · HIGH   — earnings ≤10d, or journaled tailwind(s) AND improving
                 fundamentals (a live repricing engine + a story)
      · MEDIUM — fundamentals improving with positive revisions, no
                 confirmed catalyst — squeeze risk is real but soft"""
    hard: list[str] = []
    soft: list[str] = []
    if next_earnings is not None:
        try:
            d = (next_earnings - date.today()).days
            if 0 <= d <= 10:
                hard.append(f"earnings in {d}d — binary event")
        except Exception:
            pass
    rev = fly.get("est_revision_pct")
    improving = fund in {"accelerating", "growing"} and (rev or 0) > 0
    if sym:
        try:
            from app.database import db
            tw = db.execute_query(
                "SELECT count(*) n FROM tailwinds WHERE symbol=:s"
                " AND direction='tailwind' AND status='active'"
                " AND tier IN ('announced','revenue','shipping')",
                {"s": sym.upper()})
            n = int(tw[0]["n"]) if tw else 0
            if n and improving:
                hard.append(f"{n} active journaled tailwind(s) + "
                            "improving fundamentals — repricing story "
                            "live")
            elif n:
                soft.append(f"{n} active journaled tailwind(s) — "
                            "narrative support")
        except Exception:
            pass
    if improving:
        soft.append(f"fundamentals {fund} + revisions "
                    f"{rev:+.0f}% — squeeze risk")
    flag = ("high" if hard else "medium" if soft else "low")
    return {"flag": flag, "reasons": hard + soft}


def score(det: dict, mom: Optional[str], fund: Optional[str],
          fly: dict, scen: dict, spot: Optional[float],
          regime: dict, sym: Optional[str] = None,
          rotation: Optional[dict] = None) -> dict[str, Any]:
    """Nine weighted factors → 0-100 score + band + category +
    staged entry ladder. Every factor line shows its math."""
    det = det or {}
    fly = fly or {}
    sw = det.get("swing") or {}
    rsi, rdir = det.get("rsi"), det.get("rsi_dir")
    hd, pb = det.get("hist_dir"), det.get("pct_b")
    v50, dd = det.get("vs_sma50"), det.get("dd52w")
    r3m = det.get("ret_3m")
    rsp, rss = det.get("rs_pct"), det.get("rs_score")
    factors: list[dict] = []
    total = 0.0

    def _f(name: str, w: int, pts: float, note: str):
        nonlocal total
        total += pts
        factors.append({"name": name, "weight": w,
                        "pts": round(pts, 1), "note": note})

    # ---------------- valuation excess (18) — fv distance + bull/base
    base = (scen or {}).get("base")
    bull = (scen or {}).get("bull")
    base_up = (base / spot - 1) if base and spot else None
    bull_up = (bull / spot - 1) if bull and spot else None
    pts, note = 0.0, "no fv scenario"
    if base_up is not None:
        pts = (18 if base_up <= -0.40 else 15 if base_up <= -0.30
               else 11 if base_up <= -0.20 else 7 if base_up <= -0.10
               else 3 if base_up <= -0.05 else 0)
        asym = (bull_up is not None and base_up <= -0.15
                and bull_up < 0.15)
        note = (f"base-case {base_up * 100:+.0f}%, bull "
                f"{f'{bull_up * 100:+.0f}%' if bull_up is not None else '—'}"
                + (" — asymmetric: limited upside vs big downside"
                   if asym else ""))
        if asym:
            pts = min(18.0, pts + 2)
    else:
        pe = fly.get("fwd_pe")
        if pe:
            pts = (9 if pe > 60 else 6 if pe > 40
                   else 4 if pe > 30 else 2 if pe > 25 else 0)
            note = f"no fv scenario — fwd PE {pe:.0f} proxy"
    _f("valuation excess", 18, pts, note)

    # ---------------- price extension (13) — ran too far
    pts = ((6 if v50 > 0.20 else 5 if v50 > 0.15 else
            3 if v50 > 0.10 else 2 if v50 > 0.06 else 0) if v50 is not None else 0)
    pts += ((5 if r3m > 0.60 else 4 if r3m > 0.45 else
             3 if r3m > 0.30 else 1 if r3m > 0.15 else 0) if r3m is not None else 0)
    pts += (2 if dd > -0.05 else 1 if dd > -0.10 else 0) \
        if dd is not None else 0
    pts = min(13.0, pts)
    _f("price extension", 13, pts,
       f"vs50 {(v50 or 0) * 100:+.0f}% · 3mo "
       f"{(r3m or 0) * 100:+.0f}% · dd52w {(dd or 0) * 100:+.0f}%")

    # ---------------- momentum exhaustion (8) — rally losing quality
    pts = ((4 if hd < -0.5 else 3 if hd < -0.2 else 1 if hd < 0 else 0)
           if hd is not None else 0)
    pts += ((3 if rdir < -3 else 1.5 if rdir < 0 else 0)
            if rdir is not None else 0)
    if rsi and rsi >= 70 and ((rdir or 0) < 0 or (hd or 0) < 0):
        pts += 1
    pts = min(8.0, pts)
    _f("momentum exhaustion", 8, pts,
       f"hist dir {hd if hd is not None else '—'} · RSI "
       f"{f'{rsi:.0f}' if rsi else '—'} dir "
       f"{rdir if rdir is not None else '—'}")

    # ---------------- failed breakout / lower high (13)
    pts = ({"breakdown": 9, "knife": 9, "capitulation": 9,
            "rolling_over": 6, "climax": 4}.get(mom or "", 0))
    if not sw.get("hl_seq") and sw.get("swing_low") is not None:
        pts += 3                                    # lower-high printed
    pbk = sw.get("pullback_pct")
    pts += (3 if pbk is not None and pbk < -0.10
            else 1.5 if pbk is not None and pbk < -0.05 else 0)
    pts = min(13.0, pts)
    _f("failed breakout", 13, pts,
       f"state `{mom or '—'}` · {'lower-high printed' if not sw.get('hl_seq') else 'hl seq intact'}"
       f" · pullback {f'{pbk * 100:.0f}%' if pbk is not None else '—'}")

    # ---------------- support breakdown (18) — the actual entry leg
    lvl_rows = [("avwap", sw.get("avwap")),
                ("swing_low", sw.get("swing_low")),
                ("support", sw.get("support_px")),
                ("prior_low", sw.get("prior_low"))]
    broke = [n for n, p in lvl_rows
             if p and spot and spot < p]
    pts = ((4 if "avwap" in broke else 0)
           + (7 if "swing_low" in broke else 0)
           + (7 if "support" in broke else 0)
           + (3 if "prior_low" in broke else 0))
    if v50 is not None and v50 < 0:
        pts += 3                                    # 50SMA failure
        broke.append("sma50")
    if pb is not None and pb < 0:
        pts += 2                                    # below 20d band
        broke.append("20d-band")
    pts = min(18.0, pts)
    _f("support breakdown", 18, pts,
       "broke: " + ", ".join(broke) if broke else
       "holding all levels — not an entry yet")

    # ---------------- relative weakness (8)
    pts = ((5 if rsp < 35 else 3 if rsp < 50 else 1.5 if rsp < 65 else 0)
           if rsp is not None else 0)
    pts += ((3 if rss < 0.45 else 1.5 if rss < 0.5 else 0)
            if rss is not None else 0)
    pts = min(8.0, pts)
    _f("relative weakness", 8, pts,
       f"RS pct {rsp if rsp is not None else '—'} · RS score "
       f"{round(rss, 2) if rss is not None else '—'}")

    # ---------------- macro risk (7) — canonical defensive state +
    # AI-rotation environment. The Oct-7-2026 lesson: regime was
    # NEUTRAL while the AI cohort de-risked — a market-level stance
    # alone can't permission directional puts on the theme.
    dstate = str((regime or {}).get("defensive_state") or "").upper()
    rot = _rotation(rotation)
    rot_score = float(rot["score"]) if rot and rot.get("score") \
        is not None else None
    pts = ({"CAPITULATION": 4.0, "DEFENSIVE": 3.5, "HEDGE": 2.5,
            "RECOVERY": 2.0, "WATCH": 1.5}.get(dstate, 0.0))
    if rot_score is not None:
        pts += (3.0 if rot_score >= 60 else 1.5 if rot_score >= 45
                else 0.5 if rot_score >= 30 else 0)
    else:
        # no rotation row — fall back to the raw regime leg so the
        # score stays computable
        stance = str((regime or {}).get("stance") or "").lower()
        pts += (2 if any(k in stance for k in
                         ("bear", "risk", "defen", "caut"))
                else 0)
    vix = (regime or {}).get("vix")
    pts += ((1.0 if vix >= 25 else 0.5 if vix >= 20 else 0)
            if vix is not None else 0)
    pts = min(7.0, pts)
    rot_band = rot.get("band") if rot else None
    _f("macro risk", 7, pts,
       f"defensive `{dstate or '—'}` · rotation "
       f"{rot_score if rot_score is not None else '—'}"
       f"{f' ({rot_band})' if rot_band else ''} · VIX {vix or '—'}")

    # ---------------- catalyst window (8) — scheduled repricing inside
    # the put horizon, or evidence the story is already cracking
    cat = _catalyst(sym, fly)
    _f("catalyst window", 8, cat["pts"], cat["note"])

    # ---------------- put premium / IV (7) — don't overpay for the put
    iv = _iv_for(sym)
    if iv and iv.get("iv_hv") is not None:
        ratio = float(iv["iv_hv"])
        pts = (7 if ratio < 1.2 else 4 if ratio < 1.5
               else 2 if ratio < 1.8 else 0)
        note = (f"IV/HV {ratio:.2f} (atm_iv "
                f"{float(iv['atm_iv']) * 100:.0f}% vs hv20 "
                f"{float(iv['hv20']) * 100:.0f}%)"
                + (" — puts cheap vs realized" if ratio < 1.2
                   else " — acceptable" if ratio < 1.5
                   else " — rich" if ratio < 1.8
                   else " — put premium very rich, wait")
                + _iv_age(iv))
    else:
        pts, note = 0.0, "no IV snapshot — verify premium before sizing"
    _f("put premium (IV)", 7, pts, note)

    # ---------------- category gate — the A/B split
    rg, eg = fly.get("rev_growth"), fly.get("eps_growth")
    strong = (fund in ("accelerating", "growing")
              or (fund not in ("deteriorating", "declining")
                  and (rg or 0) > 0.10 and (eg or 0) > 0))
    weak = (fund in ("deteriorating", "declining")
            or ((eg or 0) < 0 and (fly.get("est_revision_pct") or 0) < 0))
    category = ("valuation_put" if strong
                else "fundamental_break" if weak
                else "speculative")

    band = ("major" if total >= 85 else "add" if total >= 70
            else "starter" if total >= 55 else "watch" if total >= 40
            else "none")
    # 'already broke' no-chase: broke down AND deep decline — the
    # entry was earlier; buying the put now is paying for yesterday.
    # r3m alone misses crash-from-extended-high (a -20% flush off a
    # +80% quarter keeps r3m positive) — dd52w / swing pullback_pct
    # measure the drop off the peak regardless of the 3-month base.
    chase = (mom in ("knife", "capitulation", "breakdown")
             and ((r3m or 0) < -0.20
                  or (dd or 0) < -0.15
                  or (pbk is not None and pbk < -0.15)))
    if chase:
        band = "none"

    # staged ladder — supports below spot, descending → 25/35/40%
    rungs = sorted([(p, n) for n, p in lvl_rows if p and spot
                    and p < spot], reverse=True)[:3]
    stage = [{"level": round(p, 2), "name": n,
              "tranche": t}
             for (p, n), t in zip(rungs, ("25%", "35%", "40%"))]

    return {"score": round(total, 1), "band": band,
            "category": category,
            "category_note": (
                "A-type — multiple-compression bet; the PUT→CALL "
                "cycle wants the business intact" if category ==
                "valuation_put" else
                "B-type — deteriorating business; bigger fall but "
                "unknowable bottom — NOT core for long-dated puts"
                if category == "fundamental_break" else
                "mixed quality — treat like B-type, reduced size"),
            "factors": factors, "stage": stage,
            "base_up": round(base_up * 100, 1) if base_up is not None
            else None,
            "bull_up": round(bull_up * 100, 1) if bull_up is not None
            else None,
            "chase_block": bool(chase),
            "regime": regime.get("stance")}


def continuation_score(det: dict, mom: Optional[str], fly: dict,
                       spot: Optional[float], regime: dict,
                       sym: Optional[str] = None,
                       rotation: Optional[dict] = None
                       ) -> dict[str, Any]:
    """Swing-put entry AFTER the top — downtrend/pullback continuation.

    The valuation scorer deliberately can't take these ('already broke —
    the entry was earlier' is right for LEAP top-ticks). But a lower-
    high failure inside a de-risking theme IS a legitimate 30-90d put
    entry — Oct-7-26: ARM/CRWV/ORCL sat in pullback/downtrend states the
    candidate gate never admitted, then fell 4-7% next day.

    This mode answers: has the bounce failed into resistance while the
    THEME is rotating? The environment leg is mandatory — continuation
    shorts in a healthy tape are how you get squeezed.
    """
    det = det or {}
    fly = fly or {}
    sw = det.get("swing") or {}
    rsp, r3m = det.get("rs_pct"), det.get("ret_3m")
    v50, v200 = det.get("vs_sma50"), det.get("vs_sma200")
    factors: list[dict] = []
    total = 0.0

    def _f(name: str, w: int, pts: float, note: str):
        nonlocal total
        total += pts
        factors.append({"name": name, "weight": w,
                        "pts": round(pts, 1), "note": note})

    # ---- failed reclaim / lower-high (25) -------------------------
    pts = 0.0
    if not sw.get("hl_seq") and sw.get("swing_low") is not None:
        pts += 10                                     # lower-high printed
    if spot and sw.get("avwap") and spot < sw["avwap"]:
        pts += 8                                      # below anchored vwap
    elif sw.get("avwap_reclaimed") is False:
        pts += 4
    if spot and sw.get("swing_low") and spot < sw["swing_low"]:
        pts += 7                                      # through the shelf
    pts = min(25.0, pts)
    _f("failed reclaim", 25, pts,
       f"hl_seq {sw.get('hl_seq')} · vs avwap "
       f"{'below' if spot and sw.get('avwap') and spot < sw['avwap'] else 'above'}"
       f" · vs swing_low "
       f"{'below' if spot and sw.get('swing_low') and spot < sw['swing_low'] else 'above'}")

    # ---- pullback failure (15) -------------------------------------
    pbk = sw.get("pullback_pct")
    pts = ((10 if pbk < -0.10 else 6 if pbk < -0.05
            else 2 if pbk < -0.02 else 0)
           if pbk is not None else 0)
    vpr = sw.get("vol_pullback_vs_rally")
    if vpr is not None and vpr > 1.0:
        pts += 5                                      # selling volume
        # expanding INTO the decline — distribution, not digestion
    pts = min(15.0, pts)
    _f("pullback failure", 15, pts,
       f"pullback {f'{pbk * 100:.0f}%' if pbk is not None else '—'} · "
       f"vol p/r {f'{vpr:.2f}' if vpr is not None else '—'}")

    # ---- trend broken (15) -----------------------------------------
    pts = ((8 if v50 < 0 else 3 if v50 < 0.02 else 0)
           if v50 is not None else 0)
    pts += ((7 if v200 < 0 else 3 if v200 < 0.03 else 0)
            if v200 is not None else 0)
    pts = min(15.0, pts)
    _f("trend broken", 15, pts,
       f"vs50 {(v50 or 0) * 100:+.0f}% · vs200 "
       f"{(v200 or 0) * 100:+.0f}%")

    # ---- relative weakness (10) ------------------------------------
    pts = (10 if rsp < 35 else 6 if rsp < 50 else 2 if rsp < 65 else 0) \
        if rsp is not None else 0
    _f("relative weakness", 10, pts,
       f"RS pct {rsp if rsp is not None else '—'}")

    # ---- theme rotation environment (20) — the permission leg ------
    rot = _rotation(rotation)
    rot_score = float(rot["score"]) if rot and rot.get("score") \
        is not None else None
    pts = ((20 if rot_score >= 60 else 14 if rot_score >= 45
            else 8 if rot_score >= 30 else 0)
           if rot_score is not None else 0)
    rot_band = rot.get("band") if rot else None
    _f("theme rotation", 20, pts,
       f"rotation {rot_score if rot_score is not None else '—'}"
       f"{f' ({rot_band})' if rot_band else ''}")

    # ---- defensive state (10) --------------------------------------
    dstate = str((regime or {}).get("defensive_state") or "").upper()
    pts = {"CAPITULATION": 10.0, "DEFENSIVE": 10.0, "HEDGE": 7.0,
           "WATCH": 4.0, "RECOVERY": 4.0}.get(dstate, 0.0)
    _f("defensive state", 10, pts, dstate or "—")

    # ---- put premium (5) -------------------------------------------
    iv = _iv_for(sym)
    if iv and iv.get("iv_hv") is not None:
        ratio = float(iv["iv_hv"])
        pts = (5 if ratio < 1.2 else 3 if ratio < 1.5
               else 1 if ratio < 1.8 else 0)
        note = f"IV/HV {ratio:.2f}" + _iv_age(iv)
    else:
        pts, note = 0.0, "no IV snapshot"
    _f("put premium (IV)", 5, pts, note)

    # ---- late guard — don't short the capitulation ------------------
    # a 30%+ 3-month decline means the move already happened; buying
    # the put here pays for yesterday's breakdown
    late = (r3m is not None and r3m <= -0.30) or (
        mom in ("capitulation", "knife"))
    band = ("none" if late else
            "candidate" if total >= 55 else
            "watch" if total >= 40 else "none")
    return {"score": round(total, 1), "band": band,
            "category": "continuation_put",
            "category_note": "swing put on a failed bounce inside a "
                             "de-risking theme — not a LEAP top-tick",
            "factors": factors, "stage": [],
            "chase_block": bool(late),
            "late_block_reason": ("3mo decline already >30% — the "
                                  "entry was earlier" if late
                                  else None),
            "regime": (regime or {}).get("stance"),
            "rotation": rot_score}
