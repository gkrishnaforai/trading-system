"""Selloff Opportunity Engine — buy temporary fear in durable
businesses, not permanent deterioration disguised as a bargain.

Separate from the accumulate/hold/trim engine: that one decides
whether a business deserves to be owned; this one decides whether the
current price offers an unusually attractive entry — prices that fell
more than the underlying business value deteriorated.

Pipeline (all deterministic):
  1. market dislocation    — breadth, VIX/VXN, SPY drawdown
  2. price dislocation     — returns vs market/sector, drawdown,
                             volume, trend distance
  3. business integrity    — revisions, cash flow, guidance beats,
                             leverage, thesis health
  4. classification        — macro_panic / sector_contagion /
                             positioning_unwind / fundamental_repricing
                             / structural_impairment
  5. 100-pt score          — dislocation 25 · durability 25 ·
                             valuation 20 · recovery 15 · r/r 15
  6. staged entry plan     — 25/25/25/25 with triggers + invalidation

Hard gates override the score: broken thesis, deteriorating
fundamentals, imminent binary events, leverage distress. Candidates
journal to selloff_candidates + board_decisions for forward grading.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

# universe tiers — tagged, not favored: a quality non-AI name outranks
# a deteriorating AI name every time
_CORE = {"GOOGL", "AMZN", "MSFT", "META", "NVDA", "AVGO", "TSM",
         "SNPS", "CDNS"}
_AI_INFRA = {"CRDO", "ANET", "MRVL", "ALAB", "COHR", "LITE", "NBIS",
             "IREN", "CRWV", "APLD"}


def _f(v) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except Exception:
        return None


# ---------------------------- market dislocation -----------------------------

def _market() -> dict:
    """Is there a market dislocation right now? Read the latest
    journaled regime snapshot — breadth collapse, elevated vol,
    index drawdown. The engine only hunts when the tape is afraid."""
    from app.database import db
    import json
    r = db.execute_query(
        "SELECT as_of, payload FROM regime_snapshots"
        " ORDER BY as_of DESC, created_at DESC LIMIT 1")
    if not r:
        return {"active": False, "reason": "no regime snapshot"}
    p = r[0]["payload"]
    if isinstance(p, str):
        p = json.loads(p)
    b = p.get("breadth") or {}
    breadth = _f(b.get("breadth_score"))
    pct_low = _f(b.get("pct_20d_low"))
    spy5 = _f(p.get("spy_5d"))
    vix = _f(p.get("vix"))
    vxn = _f(p.get("vxn"))
    p_deep = _f((p.get("forward") or {}).get("p_deeper_dip_20d"))
    spy_vs200 = _f(p.get("spy_vs_200"))
    sig = 0
    if breadth is not None and breadth < 35:
        sig += 2
    if pct_low is not None and pct_low > 8:
        sig += 1
    if spy5 is not None and spy5 < -0.025:
        sig += 2
    if vix is not None and vix > 22:
        sig += 1
    if p_deep is not None and p_deep > 55:
        sig += 1
    level = "severe" if sig >= 5 else "mild" if sig >= 2 else "calm"
    return {"active": sig >= 2, "level": level, "sig": sig,
            "as_of": str(r[0]["as_of"]),
            "breadth_score": breadth, "pct_20d_low": pct_low,
            "spy_5d": spy5, "spy_vs_200": spy_vs200,
            "vix": vix, "vxn": vxn, "p_deeper": p_deep,
            "reason": (f"breadth {breadth}, spy_5d {spy5}, "
                       f"vix {vix}")}


# ------------------------------ tape metrics ---------------------------------

_METRICS_SQL = """
WITH w AS (
  SELECT symbol, date, close, high, low, volume,
    LAG(close, 1) OVER wnd AS c1,
    LAG(close, 5) OVER wnd AS c5,
    MAX(high) OVER (PARTITION BY symbol ORDER BY date
                    ROWS 59 PRECEDING) AS h60,
    AVG(volume) OVER (PARTITION BY symbol ORDER BY date
                      ROWS 4 PRECEDING) AS v5,
    AVG(volume) OVER (PARTITION BY symbol ORDER BY date
                      ROWS 59 PRECEDING) AS v60,
    AVG(close) OVER (PARTITION BY symbol ORDER BY date
                     ROWS 19 PRECEDING) AS s20,
    AVG(close) OVER (PARTITION BY symbol ORDER BY date
                     ROWS 49 PRECEDING) AS s50,
    AVG(close) OVER (PARTITION BY symbol ORDER BY date
                     ROWS 199 PRECEDING) AS s200,
    ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
  FROM daily_bars
  WINDOW wnd AS (PARTITION BY symbol ORDER BY date)
)
SELECT symbol, date, close, c1, c5, h60, v5, v60, s20, s50, s200
FROM w WHERE rn = 1
"""


def _tape_metrics() -> tuple[dict, float, dict]:
    """Per-symbol tape metrics, SPY 5d return, sector-median 5d
    returns — one window pass over daily_bars."""
    from app.database import db
    rows = db.execute_query(_METRICS_SQL)
    mets = {}
    sector_rets: dict[str, list] = {}
    spy_5d = None
    for r in rows:
        c, c1, c5 = _f(r["close"]), _f(r["c1"]), _f(r["c5"])
        if not c:
            continue
        ret1 = (c / c1 - 1) if c1 else None
        ret5 = (c / c5 - 1) if c5 else None
        m = {"close": c, "ret_1d": ret1, "ret_5d": ret5,
             "dd_60d": (c / _f(r["h60"]) - 1) if _f(r["h60"]) else None,
             "vol_ratio": (_f(r["v5"]) / _f(r["v60"]))
             if _f(r["v60"]) else None,
             "d_sma20": (c / _f(r["s20"]) - 1) if _f(r["s20"]) else None,
             "d_sma50": (c / _f(r["s50"]) - 1) if _f(r["s50"]) else None,
             "d_sma200": (c / _f(r["s200"]) - 1) if _f(r["s200"]) else None,
             "as_of": str(r["date"])}
        mets[r["symbol"]] = m
        if r["symbol"] == "SPY":
            spy_5d = ret5
    return mets, (spy_5d if spy_5d is not None else 0.0), sector_rets


def _rsi(sym: str) -> Optional[float]:
    """RSI-14 for shortlisted names only — small per-symbol read."""
    from app.database import db
    rows = db.execute_query(
        "SELECT close FROM daily_bars WHERE symbol=:s"
        " ORDER BY date DESC LIMIT 16", {"s": sym})
    if len(rows) < 15:
        return None
    closes = [_f(r["close"]) for r in rows][::-1]
    gains, losses = [], []
    for a, b in zip(closes[-15:-1], closes[-14:]):
        d = (b or 0) - (a or 0)
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    ag, al = sum(gains) / 14, sum(losses) / 14
    if al == 0:
        return 100.0
    return round(100 - 100 / (1 + ag / al), 1)


# ------------------------------ classification -------------------------------

def _classify(d: dict) -> tuple[str, str]:
    """What KIND of selloff is this? Ordered rules — first match wins.
    Returns (classification, action_bias)."""
    fund, thesis = d["fund"], d["thesis"]
    rev_bad = (d.get("est_rev") is not None and d["est_rev"] < -5)
    if thesis == "broken" or d["fund_state"] == "declining" and rev_bad:
        return ("structural_impairment",
                "reject — the business itself is impaired")
    if (rev_bad or d["fund_state"] in ("deteriorating", "pressured")
            or (d.get("last_surprise") is not None
                and d["last_surprise"] < -8)):
        return ("fundamental_repricing",
                "recalculate fair value — estimates are moving")
    if (abs(d.get("rel_5d") or 0) > 0.08
            and (d.get("vol_ratio") or 1) > 1.8 and fund >= 15):
        return ("positioning_unwind",
                "wait for stabilization — a crowded exit, not a "
                "business problem, but don't catch it mid-unwind")
    sector = d.get("sector_rel")
    if (sector is not None and sector < -0.04
            and abs((d.get("rel_5d") or 0) - sector) < 0.05
            and fund >= 15):
        return ("sector_contagion",
                "investigate — falling with peers, not on its own "
                "merits")
    if (d["market"]["active"] and (d.get("rel_5d") or 0) < -0.03
            and fund >= 15):
        return ("macro_panic",
                "staged buys — the business didn't fall, only the "
                "price did")
    return ("idiosyncratic_weakness",
            "caution — falling harder than its peers without a "
            "market excuse")


# --------------------------------- scoring -----------------------------------

def _score(d: dict) -> dict:
    """100-pt opportunity score. Weights are design choices, not a
    proven model — the learning loop will grade them."""
    legs = {}

    # 1) price dislocation — /25. Bigger drop vs market/sector, deeper
    # drawdown, heavier volume, further below trend.
    rel = d.get("rel_5d") or 0
    dd = d.get("dd_60d") or 0
    vr = d.get("vol_ratio") or 1
    d50 = d.get("d_sma50") or 0
    pts = 0
    pts += min(max(-rel * 100, 0), 10)          # up to 10 for -10% rel
    pts += min(max(-dd * 40, 0), 8)             # up to 8 for -20% dd
    pts += min(max((vr - 1) * 4, 0), 4)         # volume spike
    pts += min(max(-d50 * 30, 0), 3)            # below 50dma
    legs["dislocation"] = round(min(pts, 25), 1)

    # 2) fundamental durability — /25. Is the business still the
    # business?
    pts = 0
    pts += {"accelerating": 8, "growing": 6, "steady": 4,
            "slowing": 2}.get(d["fund_state"], 0)
    if d.get("rev_growth") is not None:
        pts += 4 if d["rev_growth"] > 0.15 else 3 if d["rev_growth"] > 0 else -4
    if d.get("fcf_margin") is not None:
        pts += 4 if d["fcf_margin"] > 0.10 else 3 if d["fcf_margin"] > 0 else -4
    if d.get("est_rev") is not None:
        pts += (4 if d["est_rev"] > 2 else 3 if d["est_rev"] > -2
                else 0 if d["est_rev"] > -5 else -5)
    pts += {"on_track": 4, "improving": 3, "mixed": 1.5,
            "unknown": 0.5}.get(d["thesis"] or "unknown", 0)
    if d.get("beats") is not None:
        pts += min(max(d["beats"], 0), 2)
    legs["durability"] = round(min(max(pts, 0), 25), 1)

    # 3) valuation opportunity — /20. Price vs defensible value.
    pts = 0
    fv = d.get("fv_upside")
    if fv is not None:
        pts += min(max(fv / 10, 0), 12)         # +30% upside → ~4… +120% → 12
    if d.get("priced_status") in ("partial", "not_priced"):
        pts += 5
    elif d.get("priced_status") in ("full", "substantial"):
        pts += 0
    if d.get("below_bear"):
        pts += 3                                # priced under bear case
    legs["valuation"] = round(min(pts, 20), 1)

    # 4) recovery confirmation — /15. Is selling pressure fading?
    pts = 0
    pts += {"stabilizing": 7, "basing": 6, "recovery": 5,
            "pullback": 4, "uptrend": 3,
            "knife": -4, "capitulation": -3,
            "breakdown": -5, "downtrend": -3}.get(d["mom"], 0)
    rsi = d.get("rsi")
    if rsi is not None:
        pts += 4 if 30 <= rsi <= 45 else 2 if rsi < 55 else 0
    if d.get("dip_phase") in ("basing", "turning_up", "reversal"):
        pts += 4
    # short-covering overlay — a bounce driven by shorts buying to
    # close is NOT durable stabilization; it exhausts when covering
    # runs out. Shorts still pressing is additional downside fuel.
    sq = d.get("sq_verdict")
    if sq == "likely_covering":
        pts -= 5
    elif sq == "new_shorts_pressing":
        pts -= 4
    elif sq == "squeeze_setup":
        pts += 2                            # fuel for a violent bounce
    legs["recovery"] = round(min(max(pts, 0), 15), 1)

    # 5) catalyst + risk/reward — /15. Payoff shape + a driver.
    pts = 0
    rr = d.get("rr")
    if rr is not None:
        pts += min(rr * 3, 8)                   # rr≥2.7 caps
    if d.get("earn_days") is not None:
        ed = d["earn_days"]
        pts += 3 if ed > 30 else 1 if ed > 10 else -4
    if d.get("sector") in ("Technology", "Communication Services"):
        pts += 1                                # demand visibility —
        # not an AI bonus, just where dislocations have been recovering
    if (d.get("fv_upside") or 0) > 30:
        pts += 3                                # credible recovery path
    legs["catalyst_rr"] = round(min(max(pts, 0), 15), 1)

    total = round(sum(legs.values()), 1)
    decision = ("priority" if total >= 85 else
                "starter" if total >= 75 else
                "watch" if total >= 65 else "pass")
    return {"score": total, "legs": legs, "decision": decision}


def _gates(d: dict) -> list[str]:
    """Hard gates — override the score entirely."""
    g = []
    if d["thesis"] == "broken":
        g.append("thesis broken — structural impairment, not a dip")
    if (d["fund_state"] in ("deteriorating", "declining")
            and (d.get("est_rev") or 0) < -2):
        g.append("fundamentals deteriorating + estimates falling — "
                 "repricing, not mispricing")
    if d.get("earn_days") is not None and 0 <= d["earn_days"] <= 10:
        g.append(f"earnings in {d['earn_days']}d — binary event, "
                 "not a dip-buy")
    if d["mom"] in ("knife", "capitulation"):
        g.append(f"{d['mom']} — no entry while the knife is falling; "
                 "watch for stabilization")
    if (d.get("net_debt_ebitda") or 0) > 6:
        g.append("net debt/EBITDA >6 — leverage makes a dip "
                 "potentially permanent")
    if d.get("sq_verdict") == "new_shorts_pressing":
        g.append("short-sale ratio rising — shorts are pressing "
                 "into strength, not covering")
    return g


def _entry_plan(d: dict) -> dict:
    """Staged entry — deploy 25/25/25/25 with explicit triggers.
    Finding the candidate ≠ timing the entry."""
    px = d["close"]
    inv = d.get("invalidation")
    return {
        "stages": [
            {"pct": 25, "trigger": f"now — dislocation + thesis "
                                   f"verified, px {px:.2f}"},
            {"pct": 25, "trigger": "further weakness — only if the "
                                   "thesis still verifies at the "
                                   "lower price"},
            {"pct": 25, "trigger": "stabilization — higher low, "
                                   "relative strength improving, or "
                                   "reclaim of the 20dma"},
            {"pct": 25, "trigger": "confirmation reserve — deploy on "
                                   "confirmed recovery or keep dry"},
        ],
        "invalidation": inv,
        "invalidation_note": (f"thesis fails below "
                              f"{inv:.2f}" if inv else
                              "no structural invalidation — "
                              "thesis-based exit only")}


def _invalidation(det: dict, px: float) -> Optional[float]:
    """Where is the thesis wrong? Structure support minus a margin —
    below that, the 'dip' was really a break."""
    import json
    sw = det.get("swing") or {}
    lv = _f(sw.get("swing_low")) or _f(sw.get("prior_low"))
    if lv and lv < px:
        return round(lv * 0.985, 2)         # 1.5% under support
    atr = _f(det.get("atr_pct")) or 0.03
    return round(px * (1 - 2.5 * atr), 2)


# ----------------------------------- scan ------------------------------------

def scan(funds: Optional[float] = None,
         persist: bool = True) -> dict[str, Any]:
    """Full selloff scan → ranked candidates with classification,
    score legs, gates and staged entry plans."""
    from app.database import db
    import json
    market = _market()
    mets, mets_spy5, _ = _tape_metrics()
    # benchmark: regime snapshot carries SPY 5d (fetched live at
    # snapshot time); daily_bars SPY only as fallback
    spy5 = _f(market.get("spy_5d"))
    if spy5 is None:
        spy5 = mets_spy5 or 0.0

    rows = db.execute_query(
        "SELECT s.symbol, s.company_name, s.sector,"
        " s.fundamental_state, s.momentum_state, s.momentum_detail,"
        " s.priced_status, s.next_earnings_date,"
        " fw.rev_growth, fw.rev_accel, fw.fcf_margin, fw.fcf_ttm,"
        " fw.est_revision_pct, fw.beat_streak, fw.last_surprise_pct,"
        " fw.net_debt_ebitda, fw.num_analysts,"
        " t.status AS thesis_status, t.status_dir AS thesis_dir,"
        " fv.fair_value, fv.fv_upside_pct, fv.buy_below,"
        " fv.scenario_fair_values, fv.valuation_confidence"
        " FROM stocks s"
        " LEFT JOIN symbol_flywheel fw ON fw.symbol=s.symbol"
        " LEFT JOIN symbol_thesis t ON t.symbol=s.symbol"
        " LEFT JOIN LATERAL ("
        "   SELECT fair_value, fv_upside_pct, buy_below,"
        "          scenario_fair_values, valuation_confidence"
        "   FROM symbol_fair_values v WHERE v.symbol=s.symbol"
        "   ORDER BY as_of DESC LIMIT 1) fv ON true"
        " WHERE s.is_active AND s.sector IS NOT NULL"
        " AND s.momentum_state IS NOT NULL")

    # sector median 5d returns for relative dislocation
    by_sec: dict[str, list] = {}
    for r in rows:
        m = mets.get(r["symbol"])
        if m and m.get("ret_5d") is not None:
            by_sec.setdefault(r["sector"] or "?", []).append(m["ret_5d"])
    sec_med = {k: sorted(v)[len(v) // 2] for k, v in by_sec.items()}

    # short-squeeze overlay — journaled verdicts only; a missing flag
    # means no data, not a clean bill
    try:
        from app.signals import short_squeeze
        sq_flags = short_squeeze.flags(
            [r["symbol"] for r in rows])
    except Exception:                                       # noqa: BLE001
        sq_flags = {}

    cands = []
    for r in rows:
        sym = r["symbol"]
        m = mets.get(sym)
        if not m or m.get("ret_5d") is None:
            continue
        rel5 = m["ret_5d"] - spy5
        dd60 = m.get("dd_60d") or 0
        # intake gate — the name must have actually FELL. Permissive
        # by design: classification + score do the discriminating.
        # -3% underperforming the market, -4% absolute, or -10% off
        # the 60d high — any one makes it a selloff event to examine
        if rel5 > -0.03 and (m["ret_5d"] or 0) > -0.04 \
                and dd60 > -0.10:
            continue
        det = r.get("momentum_detail") or {}
        if isinstance(det, str):
            try:
                det = json.loads(det)
            except Exception:
                det = {}
        scfv = r.get("scenario_fair_values") or {}
        if isinstance(scfv, str):
            try:
                scfv = json.loads(scfv)
            except Exception:
                scfv = {}
        fv_px = _f(r.get("fair_value"))
        bear = _f(scfv.get("bear"))
        px = m["close"]
        inv = _invalidation(det, px)
        ed = None
        ne = r.get("next_earnings_date")
        if ne:
            d0 = ne.date() if hasattr(ne, "date") else ne
            try:
                ed = (d0 - date.today()).days
            except Exception:
                pass
        d = {
            "symbol": sym, "name": r.get("company_name"),
            "sector": r["sector"],
            "tier": ("core" if sym in _CORE else
                     "ai_infra" if sym in _AI_INFRA else "durable"),
            "market": market,
            "close": px, "ret_1d": m["ret_1d"], "ret_5d": m["ret_5d"],
            "rel_5d": round(rel5, 4),
            "sector_rel": sec_med.get(r["sector"] or "?", 0),
            "dd_60d": m.get("dd_60d"), "vol_ratio": m.get("vol_ratio"),
            "d_sma20": m.get("d_sma20"), "d_sma50": m.get("d_sma50"),
            "d_sma200": m.get("d_sma200"),
            "mom": r["momentum_state"],
            "dip_phase": (det.get("dip") or {}).get("phase"),
            "fund_state": r["fundamental_state"] or "unknown",
            "priced_status": r.get("priced_status"),
            "rev_growth": _f(r["rev_growth"]),
            "fcf_margin": _f(r["fcf_margin"]),
            "est_rev": _f(r["est_revision_pct"]),
            "last_surprise": _f(r["last_surprise_pct"]),
            "beats": _f(r["beat_streak"]),
            "net_debt_ebitda": _f(r["net_debt_ebitda"]),
            "thesis": r.get("thesis_status"),
            "thesis_dir": r.get("thesis_dir"),
            "fv": fv_px, "fv_upside": _f(r["fv_upside_pct"]),
            "buy_below": _f(r["buy_below"]),
            "below_bear": bool(bear and px < bear),
            "fv_conf": r.get("valuation_confidence"),
            "earn_days": ed, "invalidation": inv,
            "rr": ((fv_px - px) / (px - inv)
                   if fv_px and inv and px > inv else None),
        }
        sq = sq_flags.get(sym) or {}
        d["sq_verdict"] = sq.get("verdict")
        d["sq_fuel"] = sq.get("fuel")
        d["sq_covering_prob"] = sq.get("covering_probability")
        d["fund"] = _score({**d, "est_rev": d["est_rev"]})["legs"][
            "durability"]
        classification, action = _classify(d)
        scored = _score(d)
        gates = _gates(d)
        if gates:
            scored["decision"] = ("reject"
                                  if classification in
                                  ("structural_impairment",
                                   "fundamental_repricing")
                                  else "watch")
        cands.append({**d, "classification": classification,
                      "action": action, **scored, "gates": gates,
                      "rsi": None,
                      "entry_plan": _entry_plan(d)})

    # RSI only for shortlisted names — bound the reads
    cands.sort(key=lambda c: -c["score"])
    for c in cands[:40]:
        c["rsi"] = _rsi(c["symbol"])
        legs = _score(c)["legs"]          # rescore with RSI present
        c["legs"] = legs
        c["score"] = round(sum(legs.values()), 1)
        c["decision"] = ("priority" if c["score"] >= 85 else
                         "starter" if c["score"] >= 75 else
                         "watch" if c["score"] >= 65 else "pass")
        if c["gates"] and c["decision"] not in ("reject",):
            c["decision"] = "watch" if not any(
                "structural" in g or "repricing" in g
                for g in c["gates"]) else "reject"
    cands.sort(key=lambda c: -c["score"])

    if persist and cands:
        _persist(market, cands)
    return {"as_of": str(date.today()), "market": market,
            "candidates": cands[:30],
            "note": ("dip vs deterioration — buys are staged and "
                     "invalidation-bounded; a low score means 'not "
                     "mispriced', not 'bad company'")}


def _persist(market: dict, cands: list[dict]) -> None:
    """Journal the scan — candidates join the learning loop via
    selloff_candidates (full record) and board_decisions (forward
    grading)."""
    from app.database import db
    import json
    try:
        db.execute_many(
            "INSERT INTO selloff_candidates"
            " (as_of, market_level, market_ctx, rank, symbol, sector,"
            "  tier, classification, score, score_legs, tape, fund,"
            "  decision, gates, entry_plan)"
            " VALUES (:d,:lv,CAST(:mc AS jsonb),:rk,:s,:sec,:ti,:cl,"
            " :sc,CAST(:sl AS jsonb),CAST(:tp AS jsonb),"
            " CAST(:fd AS jsonb),:de,CAST(:g AS jsonb),"
            " CAST(:ep AS jsonb))"
            " ON CONFLICT (as_of, symbol) DO NOTHING",
            [{"d": date.today(), "lv": market.get("level"),
              "mc": json.dumps(market, default=str),
              "rk": i + 1, "s": c["symbol"],
              "sec": c.get("sector"), "ti": c["tier"],
              "cl": c["classification"], "sc": c["score"],
              "sl": json.dumps(c["legs"]),
              "tp": json.dumps({k: c[k] for k in
                                ("close", "ret_5d", "rel_5d", "dd_60d",
                                 "vol_ratio", "d_sma50", "rsi", "mom",
                                 "sq_verdict", "sq_fuel")},
                               default=str),
              "fd": json.dumps({k: c[k] for k in
                                ("fund_state", "thesis", "fv", "fv_upside",
                                 "est_rev", "fcf_margin", "rev_growth")},
                               default=str),
              "de": c["decision"], "g": json.dumps(c["gates"]),
              "ep": json.dumps(c["entry_plan"], default=str)}
             for i, c in enumerate(cands[:30])])
        # forward grading — top candidates become journaled decisions
        for c in cands[:10]:
            if c["decision"] in ("reject",):
                continue
            from app.signals import pulse_engine as _pe
            db.execute_update(
                "INSERT INTO board_decisions (as_of, symbol, action,"
                " instrument, score, momentum_state, posture, price,"
                " entry, stop, target, evidence, rules_version)"
                " VALUES (:d,:s,'SELLOFF','stock',:sc,:m,:p,:px,:e,"
                " :st,:t,CAST(:ev AS jsonb),:rv)"
                " ON CONFLICT (as_of, symbol, action) DO NOTHING",
                {"d": date.today(), "s": c["symbol"], "sc": c["score"],
                 "m": c["mom"], "p": market.get("level"),
                 "px": c["close"], "e": c["close"],
                 "st": c.get("invalidation"), "t": c.get("fv"),
                 "rv": _pe.rules_version(),
                 "ev": json.dumps(
                     [f"selloff:{c['classification']}",
                      f"score {c['score']} {c['decision']}",
                      *c["gates"], c["action"]])})
    except Exception:
        pass
