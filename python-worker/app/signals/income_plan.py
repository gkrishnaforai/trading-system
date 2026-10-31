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
        return {"posture": "unknown",
                "new_longs": posture_mod.NO_SNAPSHOT["new_longs"]}


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


_FEAR = {"defensive", "caution"}
_GREED = {"constructive", "aggressive"}


def _bias(pos: dict) -> str:
    """Contrarian frame: fear regime is the greedy window (LEAP calls,
    CSP on sound names); broad strength is the fearful window (LEAP
    puts, hedges cheap). Neutral otherwise."""
    p = str(pos.get("posture") or "")
    if p in _FEAR:
        return "fear"
    if p in _GREED:
        return "greed"
    return "neutral"


def _journal(lanes: dict, pos: dict, bias: str) -> int:
    """Write today's suggestions into board_decisions so the existing
    outcome grader forward-grades them — the plan lanes join the
    learning loop. Action vocabulary maps direction: PUT flips the
    sign (declines grade positive), everything else is long-side.
    Dedup is (as_of, symbol, action) — re-renders don't multiply."""
    from app.database import db
    import json
    # lane-specific actions keep the (as_of, symbol, action) dedup
    # from colliding with board rows and give track_record per-lane
    # cells; grader flips sign only for PUT/EXIT — all bullish lanes
    # get long-side grading, the put lane keeps the PUT action
    _ACT = {"swing": ("SWING", "stock"),
            "csp": ("CSP", "cash-secured put"),
            "covered_call": ("CC", "covered call"),
            "leap_call": ("LEAP_CALL", "LEAPS call"),
            "leap_put": ("PUT", "LEAPS put")}
    n = 0
    for lane, (act, inst) in _ACT.items():
        for s in (lanes.get(lane) or [])[:10]:
            try:
                ev = [f"lane:{lane}", f"bias:{bias}",
                      f"posture:{pos.get('posture')}",
                      *[f for f in s.get("flags") or []],
                      f"thesis:{s['thesis']}" if s.get("thesis") else "",
                      f"iv/hv {s['iv_hv']}" if s.get("iv_hv") else ""]
                from app.signals import pulse_engine as _pe
                db.execute_update(
                    "INSERT INTO board_decisions (as_of, symbol, action,"
                    " instrument, score, momentum_state, posture, price,"
                    " entry, stop, target, evidence, rules_version)"
                    " VALUES (:d,:s,:a,:i,:sc,:m,:p,:px,:e,:st,:t,"
                    " CAST(:ev AS jsonb), :rv)"
                    " ON CONFLICT (as_of, symbol, action) DO NOTHING",
                    {"d": date.today(), "s": s["symbol"], "a": act,
                     "i": inst,
                     "sc": s.get("score") or s.get("rank"),
                     "m": s.get("mom") or s.get("state"),
                     "p": pos.get("posture"),
                     "px": s.get("spot") or s.get("entry_px"),
                     "e": s.get("entry_px") or s.get("strike")
                         or s.get("spot"),
                     "st": s.get("stop_px"),
                     "t": s.get("target_px"),
                     "ev": json.dumps([e for e in ev if e]),
                     "rv": _pe.rules_version()})
                n += 1
            except Exception:
                pass
    return n


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


def _leaps(use_case: str, th: dict, bias: str = "neutral") -> list[dict]:
    """Readiness lane top names (ready first, rank-ordered) — the
    deep-ITM long-dated candidates. Contrarian rule: LEAP calls are
    the 'greedy when fearful' instrument — they keep running under a
    fear posture but only on names whose fundamentals/thesis hold up.
    Under greed they're the fearful window's hedge candidates."""
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
        t = th.get(r["symbol"]) or {}
        # fear-regime LEAP calls: greedy requires quality — broken or
        # deteriorating theses don't get the contrarian benefit
        if (use_case == "leap_call" and bias == "fear"
                and t.get("status") in ("broken", "deteriorating")):
            continue
        flags = []
        if use_case == "leap_call" and bias == "fear":
            flags.append("fear regime — the greedy window; "
                         "long-dated, quality-filtered")
        if use_case == "leap_call" and bias == "greed":
            flags.append("greed regime — demand a deeper discount; "
                         "premium and upside both thinner here")
        if use_case == "leap_put" and bias == "greed":
            flags.append("greed regime — the fearful window; hedges "
                         "are cheap when nobody wants them")
        if use_case == "leap_put" and bias == "fear":
            flags.append("fear regime — puts are expensive here; "
                         "pay only for real invalidation risk")
        d = _draft(r["symbol"], use_case)
        out.append({"symbol": r["symbol"], "sector": r["sector"],
                    "flags": flags,
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
        "SELECT s.symbol, s.company_name, s.sector, s.priced_status,"
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
        if t.get("status") in ("broken", "severely_deteriorating",
                               "deteriorating"):
            continue                          # never sell puts on a
        # broken thesis — assignment risk is the point of the trade
        # "potential to come back": fundamentals must be improving and
        # the improvement can't already be fully priced in
        if r["fundamental_state"] not in ("accelerating", "growing"):
            continue
        if r.get("priced_status") in ("substantial", "full"):
            continue                          # improvement already
            # priced — assignment buys a name with no room to run
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
        earn_flag = ([f"earnings in {ed}d — IV event inside window"]
                     if ed is not None and 0 <= ed <= 35 else [])
        base = {
            "symbol": sym, "name": r.get("company_name"),
            "sector": r["sector"], "use_case": "csp",
            "spot": px, "dte": "30-45d", "iv_hv": round(iv_hv, 2),
            "atm_iv": _f(v.get("atm_iv")),
            "fund": r["fundamental_state"], "mom": r["momentum_state"],
            "thesis": t.get("status"), "thesis_dir": t.get("status_dir"),
            "priced_status": r.get("priced_status"),
            "fcf_margin": _f(r.get("fcf_margin")),
            "earn_days": ed,
        }
        # intent 1 — ACQUIRE: strike at support; you WANT assignment.
        # premium is the discount on an entry you'd take anyway.
        cands.append({
            **base, "instrument": "CSP · acquire", "intent": "acquire",
            "strike": strike, "collateral": strike * 100,
            "contracts": int(funds // (strike * 100)) if funds else None,
            "entry_px": strike,
            "exit_rule": ("assignment is the goal — own at "
                          f"{strike}; roll only if thesis breaks"),
            "flags": ["acquire intent — engineered to be assigned at "
                      "support; size as a stock buy, not a yield play"]
            + earn_flag,
            "plan": _draft(sym, "csp", strike)})
        # intent 2 — PREMIUM: strike ~4% deeper / ~2.2 ATR under spot;
        # income is the goal, assignment is the accepted tail risk.
        prem = round(min(strike * 0.96, px * (1 - 2.2 * atr)) * 2) / 2
        if prem < px * 0.97:                  # must sit below spot
            cands.append({
                **base, "instrument": "CSP · premium",
                "intent": "premium",
                "strike": prem, "collateral": prem * 100,
                "contracts": int(funds // (prem * 100)) if funds
                else None,
                "entry_px": prem,
                "exit_rule": ("close at 50% decay; roll down/out if "
                              f"px approaches {prem}"),
                "flags": ["premium intent — assignment is the tail "
                          "risk, not the plan; only sell at a strike "
                          "you'd still want to own"] + earn_flag,
                "plan": _draft(sym, "csp", prem)})
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
        " s.sector, s.priced_status,"
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
        strike = max(px * 1.08, _f(sw.get("confirm_level")) or 0)
        strike = round(strike * 2) / 2
        ed = _earnings_in(r)
        t = th.get(sym) or {}
        fund_bad = r["fundamental_state"] in ("deteriorating",
                                              "declining", "pressured")
        thesis_bad = t.get("status") in ("broken", "deteriorating")
        flags = []
        if fund_bad:
            flags.append("fundamentals deteriorating — a call cap on a "
                         "broken name isn't income, it's delay; "
                         "consider exit instead")
        if thesis_bad:
            flags.append(f"thesis {t['status']} — selling premium "
                         "doesn't fix a broken thesis")
        # "mostly we shouldn't be selling the underlying" — don't cap
        # names whose thesis is working with upside still unpriced
        if (t.get("status") in ("on_track", "improving")
                and r.get("priced_status") in ("partial",
                                               "not_priced")):
            flags.append("thesis working + upside unpriced — a cap "
                         "here sells the upside; skip or strike way "
                         "OTM")
        if ed is not None and 0 <= ed <= 35:
            flags.append(f"earnings in {ed}d — assignment risk around "
                         "the print")
        if iv_hv is not None and iv_hv < 0.9:
            flags.append(f"iv/hv {iv_hv:.2f} — premium thin, barely "
                         "pays for the cap")
        base = {
            "symbol": sym, "name": r.get("company_name"),
            "sector": r["sector"], "use_case": "covered_call",
            "spot": px, "dte": "30-45d",
            "iv_hv": round(iv_hv, 2) if iv_hv else None,
            "fund": r["fundamental_state"], "mom": r["momentum_state"],
            "thesis": t.get("status"), "thesis_dir": t.get("status_dir"),
            "priced_status": r.get("priced_status"),
            "earn_days": ed,
            "shares": int(_f(r["quantity"]) or 0),
            "contracts": int((_f(r["quantity"]) or 0) // 100),
        }
        # intent 1 — INCOME: far-OTM strike; premium on shares you'd
        # keep anyway. You mostly do NOT want to be called away.
        out.append({
            **base, "instrument": "CC · income", "intent": "income",
            "strike": strike, "entry_px": strike,
            "exit_rule": ("hold shares under "
                          f"{strike}; roll up/out if approached"),
            "flags": flags,
            "plan": _draft(sym, "covered_call", px)})
        # intent 2 — EXIT: only where the engine already says the
        # underlying should be sold. Tighter strike (~4% OTM) is
        # engineered to be called away — premium + a tidy exit beats
        # a market order when IV is rich. Never offered on working
        # theses — selling a winner early is not an intent.
        if fund_bad or thesis_bad:
            ex_strike = round(max(px * 1.04,
                                  _f(sw.get("confirm_level")) or 0)
                              * 2) / 2
            out.append({
                **base, "instrument": "CC · exit", "intent": "exit",
                "strike": ex_strike, "entry_px": ex_strike,
                "exit_rule": ("engineered to be called away — let "
                              "assignment take the shares; this is "
                              "the exit"),
                "flags": ["exit intent — tighter strike wants "
                          "assignment; if you're not ready to sell "
                          "the stock, don't sell this call"],
                "plan": _draft(sym, "covered_call", px)})
    out.sort(key=lambda c: (
        bool(c["flags"]), -(c["iv_hv"] or 0)))
    return out


_LANE_KEYS = ("swing", "csp", "covered_call", "leap_call", "leap_put")


def _pick_score(s: dict, lane: str, bias: str) -> float:
    """Deterministic conviction score — what's most likely to pay.
    Combines thesis direction, tape state, fundamental slope, premium
    richness, engine rank, and flag penalties. Not a promise of
    profit — the ranking of today's least-bad risk."""
    sc = 0.0
    sc += {"on_track": 3, "improving": 2, "mixed": 1,
           "deteriorating": -2, "broken": -3}.get(
        s.get("thesis") or "", 0)
    if s.get("thesis_dir") == "up":
        sc += 1
    elif s.get("thesis_dir") == "down":
        sc -= 1
    sc += {"uptrend": 2, "recovery": 2, "basing": 1.5,
           "stabilizing": 1, "pullback": 1, "range": 0.5,
           "downtrend": -2, "breakdown": -2, "knife": -3}.get(
        s.get("mom") or s.get("state") or "", 0)
    sc += {"accelerating": 2, "growing": 1, "steady": 0.5,
           "slowing": -0.5, "deteriorating": -2,
           "declining": -2, "pressured": -1.5}.get(
        s.get("fund") or "", 0)
    iv = s.get("iv_hv") or 0
    if lane in ("csp", "covered_call"):
        sc += 2 if iv >= 1.3 else 1 if iv >= 1.0 else -1
    if lane == "swing" and s.get("rr"):
        sc += min(float(s["rr"]), 3)
    if lane in ("leap_call", "leap_put"):
        sc += 1.5 if s.get("lane_state") == "ready" else 0.5
    for f in s.get("flags") or []:
        sc -= 2 if "earnings" in f else 0.75
    # contrarian bonus — the regime window the bias says is open
    if bias == "fear" and lane in ("leap_call", "csp"):
        sc += 1
    if bias == "greed" and lane == "leap_put":
        sc += 1
    return sc


def _rank_picks(lanes: dict, bias: str, n: int = 4) -> None:
    """Mark the top-n suggestions across all lanes (one star per
    symbol — acquire and premium intents on the same name don't
    double-count). Only marks rows scoring above the bar so a thin
    day shows fewer stars, not four weak ones."""
    cands = []
    for lane, items in lanes.items():
        for s in items or []:
            s["pick_score"] = round(_pick_score(s, lane, bias), 1)
            cands.append(s)
    cands.sort(key=lambda c: -c["pick_score"])
    seen = set()
    for s in cands:
        if len(seen) >= n or s["pick_score"] < 4:
            break
        if s["symbol"] in seen:
            continue
        seen.add(s["symbol"])
        s["top"] = True


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
    """The full daily plan — posture gate + contrarian regime bias +
    per-lane suggestions journaled into the learning loop."""
    pos = _posture()
    bias = pos.get("bias") or _bias(pos)
    th, iv = _thesis_map(), _iv_map()
    lanes = {
        # swing is short-horizon — it doesn't get the contrarian pass;
        # posture (and the daily-calls engine itself) still gates it
        "swing": _swing() if pos.get("new_longs", True) else [],
        # LEAP calls ARE the fear-regime instrument — long-dated time
        # lets the thesis survive the drawdown; quality filter applied
        # inside _leaps when bias == fear
        "leap_call": _leaps("leap_call", th, bias),
        "leap_put": _leaps("leap_put", th, bias),
        # CSPs run in any posture — the lane's own filters (sound
        # fundamentals, structure support, valuation room, premium
        # richness, no broken thesis) are the gate, not the regime
        "csp": _csp(funds, th, iv),
        "covered_call": _covered_calls(th, iv),
    }
    # wheel overlap — a held name that also qualifies as a CSP is a
    # valid setup (the wheel strategy) but NOT two independent ideas:
    # running both doubles the bullish exposure. Flag both sides.
    overlap = ({s["symbol"] for s in lanes["csp"]}
               & {s["symbol"] for s in lanes["covered_call"]})
    for lane in ("csp", "covered_call"):
        for s in lanes[lane]:
            if s["symbol"] in overlap:
                s.setdefault("flags", []).append(
                    "held + qualifies as CSP — a wheel setup: shares "
                    "cap upside, assignment adds more; run both only "
                    "if you intend double exposure")
    _rank_picks(lanes, bias)
    _journal(lanes, pos, bias)
    return {"as_of": str(date.today()), "posture": pos,
            "bias": bias,
            "bias_note": {
                "fear": "fear regime — be greedy selectively: LEAP "
                        "calls + CSPs on quality names are the "
                        "contrarian windows; short-horizon swings "
                        "still gated",
                "greed": "greed regime — be fearful: LEAP puts and "
                         "hedges are the smart side; demand deeper "
                         "discounts on long entries",
                "neutral": "standard playbook — no regime edge "
                           "either way",
            }[bias],
            "funds": funds, "lanes": lanes,
            "sectors": _by_sector(lanes),
            "note": ("advisory — levels are engine-suggested; premium "
                     "isn't modeled (no options chain feed). Verify "
                     "bid/ask at the broker before entering.")}
