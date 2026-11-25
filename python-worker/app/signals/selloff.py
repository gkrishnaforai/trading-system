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


# ---------------------- growth journal + priced-in merges --------------------

def _growth_names() -> dict:
    """Latest growth_compare_daily payload — journaled FY27/28
    revisions, growth quality, dispersion, cyclical flags. Missing
    journal = empty dict, never a fabricated neutral."""
    from app.database import db
    import json
    try:
        r = db.execute_query(
            "SELECT payload FROM growth_compare_daily"
            " ORDER BY as_of DESC LIMIT 1")
        if not r:
            return {}
        p = r[0]["payload"]
        if isinstance(p, str):
            p = json.loads(p)
        return p.get("names") or {}
    except Exception:
        return {}


def _priced_in_map() -> dict:
    """Latest growth_priced_in_daily per symbol — required CAGR vs
    forecast. What the price demands next to what analysts expect."""
    from app.database import db
    try:
        rows = db.execute_query(
            "SELECT DISTINCT ON (symbol) symbol, required_cagr,"
            " expectation_gap, implied_status"
            " FROM growth_priced_in_daily"
            " ORDER BY symbol, as_of DESC")
        return {r["symbol"]: r for r in rows}
    except Exception:
        return {}


def _pf_gap(dd_60d: Optional[float], g: dict
            ) -> Optional[tuple[float, float]]:
    """Price-fundamental gap — how much further the price fell than
    the forward estimates did. Negative gap = dislocation (price
    overreaction); gap tracking the drawdown = the price is
    repricing real deterioration. Returns (gap, est_chg): the gap
    is dd_60d minus a weighted blend of FY28 EPS (0.6) and revenue
    (0.4) revisions — EPS-led because earnings drive multiples.
    30d window preferred, 60d at half weight. No estimate history
    → None, never zero."""
    if dd_60d is None:
        return None
    e30, e60 = _f(g.get("eps_rev28_30d")), _f(g.get("eps_rev28_60d"))
    r30, r60 = _f(g.get("rev_rev28_30d")), _f(g.get("rev_rev28_60d"))
    eps_chg = e30 if e30 is not None else \
        (e60 * 0.5 if e60 is not None else None)
    rev_chg = r30 if r30 is not None else \
        (r60 * 0.5 if r60 is not None else None)
    parts = [x for x in (
        (eps_chg, 0.6), (rev_chg, 0.4)) if x[0] is not None]
    if not parts:
        return None
    wsum = sum(w for _, w in parts)
    est_chg = sum(v * w for v, w in parts) / wsum
    return round(dd_60d - est_chg, 3), round(est_chg, 3)


# ------------------- SBD overlay: four independent dimensions -----------------

def _dimensions(legs: dict) -> dict:
    """Normalize the score legs into the reviewer's four independent
    0-100 dimensions — business health cannot be compensated by
    dislocation, recovery is timing not quality."""
    def _n(leg: str, mx: float) -> Optional[float]:
        v = legs.get(leg)
        return round(v / mx * 100, 1) if v is not None else None
    return {"business_health": _n("durability", 25),
            "stock_dislocation": _n("dislocation", 25),
            "valuation_attractiveness": _n("valuation", 20),
            "recovery_confirmation": _n("recovery", 15)}


def _fund_coverage(d: dict) -> float:
    """Share of durability inputs actually present. Missing data
    scores zero in the leg — this count is what stops a sparse row
    reading as a weak business."""
    known = sum([
        d.get("fund_state") not in (None, "unknown"),
        d.get("rev_growth") is not None,
        d.get("fcf_margin") is not None,
        d.get("est_rev") is not None,
        d.get("thesis") not in (None, "unknown"),
        d.get("beats") is not None])
    return round(known / 6, 2)


def _business_bucket(b: Optional[float], d: dict
                     ) -> tuple[str, list[str]]:
    """Bucket + override notes. severely_impaired requires >=2
    independent fundamental signals — a low score built on missing
    data is not impairment. A weak bucket contradicted by strong
    journaled fundamentals is a false-positive flag for review,
    not a verdict."""
    notes: list[str] = []
    if b is None:
        return "unknown", notes
    bucket = ("strong" if b >= 80 else
              "healthy_with_risks" if b >= 65 else
              "mixed_turnaround" if b >= 50 else
              "deteriorating" if b >= 35 else
              "severely_impaired")
    if bucket == "severely_impaired":
        sigs = sum([
            d.get("fund_state") in ("declining", "deteriorating",
                                    "pressured"),
            d.get("est_rev") is not None and d["est_rev"] < -0.02,
            d.get("rev_growth") is not None and d["rev_growth"] <= 0,
            d.get("fcf_margin") is not None
            and d["fcf_margin"] <= 0,
            d.get("last_surprise") is not None
            and d["last_surprise"] < -8,
            d.get("thesis") in ("severely_deteriorating", "broken")])
        if sigs < 2:
            bucket = "deteriorating"
            notes.append("severe_requires_corroboration")
    if bucket in ("deteriorating", "severely_impaired",
                  "mixed_turnaround"):
        contra = sum([
            d.get("rev_growth") is not None and d["rev_growth"] > 0.15,
            d.get("est_rev") is not None and d["est_rev"] > 0.02,
            d.get("fcf_margin") is not None
            and d["fcf_margin"] > 0.10,
            (d.get("beats") or 0) >= 2])
        if contra >= 2:
            notes.append("fundamental_contradiction")
            bucket = "mixed_turnaround"
    return bucket, notes


def _sbd_classify(dims: dict, gates: list[str],
                  pf_gap: Optional[float]) -> dict:
    """SBD decision table — health × dislocation × valuation →
    bucket + action. Runs alongside our causal classification;
    never issues a buy. A big drawdown alone cannot score this —
    the business-health threshold is independent."""
    b = dims.get("business_health")
    dis = dims.get("stock_dislocation")
    v = dims.get("valuation_attractiveness")
    rec = dims.get("recovery_confirmation")
    if any("structural" in g or "repricing" in g for g in gates):
        return {"class": "structural_risk", "action": "human_review"}
    if b is None or dis is None:
        return {"class": "research_incomplete", "action": "watch"}
    if b < 50:
        return {"class": "beat_down_business",
                "action": "avoid_or_research"}
    if b >= 75 and dis >= 65:
        if pf_gap is None:
            return {"class": "dislocation_unconfirmed",
                    "action": "watch"}
        if v is not None and v < 50:
            return {"class": "quality_but_expensive",
                    "action": "watch"}
        if rec is not None and rec >= 70:
            return {"class": "confirmed_recovery_candidate",
                    "action": "review_for_entry"}
        return {"class": "beat_down_stock",
                "action": "watch_for_confirmation"}
    if dis >= 65:
        return {"class": "turnaround_or_cyclical",
                "action": "research"}
    return {"class": "no_clear_dislocation",
            "action": "hold_or_watch"}


def _gap_note(pf_gap: Optional[float], est_chg: Optional[float],
              dd: Optional[float], bucket: str) -> Optional[str]:
    """The Stock A vs Stock B reading — same drawdown, different
    meaning. If most of the fall is explained by estimate cuts it
    is deterioration, not dislocation; a strong business whose
    estimates barely moved while the price fell is the candidate."""
    if pf_gap is None:
        return None
    if est_chg is not None and est_chg >= 0:
        return "potential_dislocation"
    if dd and est_chg is not None and dd < -0.01 \
            and abs(est_chg) / abs(dd) >= 0.6:
        return "deterioration_explains_most_of_fall"
    if pf_gap <= -0.10 and bucket in ("strong", "healthy_with_risks"):
        return "potential_dislocation"
    return "partial_dislocation"


# Ranking order — the board should surface genuine beaten-down
# businesses first: strong business + verified dislocation on top,
# mixed-quality turnarounds in the middle, deteriorating businesses
# and gated rejects at the bottom. Within a tier, the deeper the
# price-fundamental gap the better the rebound candidate.
_SBD_ORDER = {
    "confirmed_recovery_candidate": 0,
    "beat_down_stock": 1,
    "dislocation_unconfirmed": 2,
    "turnaround_or_cyclical": 3,
    "quality_but_expensive": 4,
    "no_clear_dislocation": 5,
    "research_incomplete": 6,
    "beat_down_business": 7,
    "structural_risk": 8,
}


def _rank_key(c: dict) -> tuple:
    """SBD-aware sort. Rejects always sink; within a tier, deeper
    pf_gap (price fell further than estimates did) ranks above a
    shallow one, then stronger business health, then raw score."""
    if c.get("decision") == "reject":
        return (99, 0.0, 0, 0)
    order = _SBD_ORDER.get((c.get("sbd") or {}).get("class"), 6)
    dims = c.get("dimensions") or {}
    bh = dims.get("business_health") or 0
    gap = c.get("pf_gap")          # more negative = deeper dislocation
    return (order, gap if gap is not None else 9.9,
            -bh, -(c.get("score") or 0))


# ------------------------------ classification -------------------------------

def _classify(d: dict) -> tuple[str, str]:
    """What KIND of selloff is this? Ordered rules — first match wins.
    Returns (classification, action_bias)."""
    fund, thesis = d["fund"], d["thesis"]
    rev_bad = (d.get("est_rev") is not None and d["est_rev"] < -0.05)
    if thesis == "broken" or d["fund_state"] == "declining" and rev_bad:
        return ("structural_impairment",
                "reject — the business itself is impaired")
    if (rev_bad or d["fund_state"] in ("deteriorating", "pressured")
            or d["thesis"] == "severely_deteriorating"
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
    # business? est_rev is a FRACTION (flywheel sanity band ±5 =
    # ±500%); last_surprise is percent. Cyclical is a regime label,
    # not deterioration — scores like steady, not zero.
    pts = 0
    pts += {"accelerating": 8, "growing": 6, "steady": 4,
            "cyclical": 4, "slowing": 2}.get(d["fund_state"], 0)
    if d.get("rev_growth") is not None:
        pts += 4 if d["rev_growth"] > 0.15 else 3 if d["rev_growth"] > 0 else -4
    if d.get("fcf_margin") is not None:
        pts += 4 if d["fcf_margin"] > 0.10 else 3 if d["fcf_margin"] > 0 else -4
    if d.get("est_rev") is not None:
        pts += (4 if d["est_rev"] > 0.02 else 3 if d["est_rev"] > -0.02
                else 0 if d["est_rev"] > -0.05 else -5)
    pts += {"on_track": 4, "improving": 3, "mixed": 1.5,
            "severely_deteriorating": 0,
            "unknown": 0.5}.get(d["thesis"] or "unknown", 0)
    if d.get("beats") is not None:
        pts += min(max(d["beats"], 0), 2)
    legs["durability"] = round(min(max(pts, 0), 25), 1)

    # 3) valuation opportunity — /20. Price vs defensible value.
    pts = 0
    fv = d.get("fv_upside")
    if fv is not None:
        pts += min(max(fv * 10, 0), 12)         # fv is a fraction: +30% → ~3… +120% caps
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
    if (d.get("fv_upside") or 0) > 0.30:
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
    if d["thesis"] == "severely_deteriorating":
        g.append("core thesis leg failed — under review, "
                 "not a confirmed dip")
    if (d["fund_state"] in ("deteriorating", "declining")
            and (d.get("est_rev") or 0) < -0.02):
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
    # journaled estimate deterioration — a consensus cut this sharp
    # means the dip is a repricing, not a mispricing
    if d.get("eps_rev28_30d") is not None and \
            d["eps_rev28_30d"] <= -0.10:
        g.append("FY28 EPS cut >10% in 30d — estimate repricing, "
                 "verify the business before treating as a dip")
    if d.get("rev_rev28_30d") is not None and \
            d["rev_rev28_30d"] <= -0.08:
        g.append("FY28 revenue cut >8% in 30d — forward demand "
                 "is falling with the price")
    if d.get("coverage_shift") is not None and \
            abs(d["coverage_shift"]) >= 2:
        g.append(f"analyst coverage shifted "
                 f"{d['coverage_shift']:+d} — the revision move may "
                 "be coverage churn, not a consensus change")
    return g


def _spiral_mult() -> tuple[float, Optional[dict]]:
    """Fragility's spiral multiplier — de-risking-spiral sizing
    dampener. Read-only: missing journal = multiplier 1.0, never
    blocks entries by itself."""
    try:
        from app.market_regime.fragility import latest
        row = latest() or {}
        sig = row.get("signals") or {}
        m = sig.get("spiral_multiplier")
        return (float(m) if m is not None else 1.0,
                sig.get("positioning_state"))
    except Exception:
        return 1.0, None


def _entry_plan(d: dict) -> dict:
    """Staged entry — deploy 25/25/25/25 with explicit triggers.
    Finding the candidate ≠ timing the entry. Stage sizes scale by
    the fragility spiral multiplier — a crowded unwind in progress
    deploys slower, it doesn't cancel the setup."""
    px = d["close"]
    inv = d.get("invalidation")
    mult, pos_state = _spiral_mult()
    flow = None
    try:
        from app.signals.flow_footprint import read as _fl_read
        flow = _fl_read(d["sym"]) or {}
    except Exception:
        flow = {}
    fp = flow.get("footprint")
    # distribution streak during a dip = institutions exiting —
    # deploy slower; absorption streak is disclosed, not leveraged
    if fp == "distributing":
        mult = round(mult * 0.8, 2)
    stage = round(25 * mult)
    note = None
    if mult < 1.0:
        st = ", ".join(k for k, v in (pos_state or {}).items() if v)
        note = (f"sized {mult:.2f}x — de-risking spiral risk"
                + (f" ({st})" if st else ""))
    if fp == "distributing":
        note = (note or "sized down") + (
            f"; distribution streak {flow.get('streak')}d" if flow.get('streak') else "; distribution streak")
    return {
        "stages": [
            {"pct": stage, "trigger": f"now — dislocation + thesis "
                                      f"verified, px {px:.2f}"},
            {"pct": stage, "trigger": "further weakness — only if the "
                                      "thesis still verifies at the "
                                      "lower price"},
            {"pct": stage, "trigger": "stabilization — higher low, "
                                      "relative strength improving, or "
                                      "reclaim of the 20dma"},
            {"pct": stage, "trigger": "confirmation reserve — deploy on "
                                      "confirmed recovery or keep dry"},
        ],
        "spiral_multiplier": mult,
        "flow": {"footprint": fp, "streak": flow.get("streak")},
        "sizing_note": note,
        "exit_plan": _exit_plan(px, inv),
        "invalidation": inv,
        "invalidation_note": (f"thesis fails below "
                              f"{inv:.2f}" if inv else
                              "no structural invalidation — "
                              "thesis-based exit only")}


def _exit_plan(px: Optional[float], inv: Optional[float]
               ) -> dict:
    """Take-profit policy for fear-rebound trades — this is a trade,
    not an accidental long-term hold. R = entry−invalidation.
    Time stop needs days_held — tracked positions only; the policy
    rides the plan so tranche tracking can enforce it later."""
    if not px or not inv or inv >= px:
        return {"policy": "thesis-invalidated exit only — no R "
                          "ladder without a defined invalidation"}
    R = px - inv
    return {"R": round(R, 2),
            "partials": [
                {"at": round(px + 1.5 * R, 2), "pct": 25,
                 "rule": "1.5R — take a quarter off"},
                {"at": round(px + 2.0 * R, 2), "pct": 30,
                 "rule": "2R — bank another third"}],
            "trail": "remainder trails 20ema / last swing low",
            "time_stop": "reassess at 5d if recovery hasn't started;"
                         " exit-or-reduce by 10d — a failed rebound"
                         " is not a long-term position",
            "invalidate": "thesis fails below "
                          f"{inv:.2f} — exit, never average through"}


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

_ROWS_SQL = """
SELECT s.symbol, s.company_name, s.sector,
 s.fundamental_state, s.momentum_state, s.momentum_detail,
 s.priced_status, s.next_earnings_date,
 fw.rev_growth, fw.rev_accel, fw.fcf_margin, fw.fcf_ttm,
 fw.est_revision_pct, fw.beat_streak, fw.last_surprise_pct,
 fw.net_debt_ebitda, fw.num_analysts,
 t.status AS thesis_status, t.status_dir AS thesis_dir,
 fv.fair_value, fv.fv_upside_pct, fv.buy_below,
 fv.scenario_fair_values, fv.valuation_confidence
 FROM stocks s
 LEFT JOIN symbol_flywheel fw ON fw.symbol=s.symbol
 LEFT JOIN symbol_thesis t ON t.symbol=s.symbol
 LEFT JOIN LATERAL (
   SELECT fair_value, fv_upside_pct, buy_below,
          scenario_fair_values, valuation_confidence
   FROM symbol_fair_values v WHERE v.symbol=s.symbol
   ORDER BY as_of DESC LIMIT 1) fv ON true
"""

# The scan requires sector for the contagion classifier; a single-name
# read doesn't — for_symbol scopes by symbol, not sector.
_ROWS_SCOPE = (" WHERE s.is_active AND s.momentum_state IS NOT NULL"
               " AND s.sector IS NOT NULL")


def _row_to_d(r: dict, m: dict, market: dict,
              sec_med: dict, sq: dict,
              gj: Optional[dict] = None,
              pi: Optional[dict] = None) -> dict:
    """Row + tape metrics → the evidence dict, classified, scored,
    gated, with the staged entry plan. Shared by scan() (bulk) and
    for_symbol() (one name on the stock page) — same rules, same
    inputs, no second classifier."""
    import json
    sym = r["symbol"]
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
    rel5 = (m["ret_5d"] or 0) - (market.get("spy_5d") or 0)
    d = {
        "symbol": sym, "name": r.get("company_name"),
        "sector": r["sector"],
        "tier": ("core" if sym in _CORE else
                 "ai_infra" if sym in _AI_INFRA else "durable"),
        "market": market,
        "close": px, "ret_1d": m["ret_1d"], "ret_5d": m["ret_5d"],
        "rel_5d": round(rel5, 4),
        "sector_rel": (sec_med.get(r["sector"])
                       if r.get("sector") else None),
        "dd_60d": m.get("dd_60d"), "vol_ratio": m.get("vol_ratio"),
        "d_sma20": m.get("d_sma20"), "d_sma50": m.get("d_sma50"),
        "d_sma200": m.get("d_sma200"),
        "mom": r["momentum_state"],
        "dip_phase": det.get("dip_phase"),
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
        "sq_verdict": sq.get("verdict"),
        "sq_fuel": sq.get("fuel"),
        "sq_covering_prob": sq.get("covering_probability"),
    }
    # growth journal + priced-in merges — the forward-estimate detail
    # the durability leg's flywheel aggregate doesn't see
    g = (gj or {}).get(sym) or {}
    p = (pi or {}).get(sym) or {}
    d.update({
        "eps_rev28_30d": _f(g.get("eps_rev28_30d")),
        "eps_rev28_60d": _f(g.get("eps_rev28_60d")),
        "rev_rev28_30d": _f(g.get("rev_rev28_30d")),
        "rev_rev28_60d": _f(g.get("rev_rev28_60d")),
        "growth_quality": (_f(g["growth_quality"].get("score"))
                           if isinstance(g.get("growth_quality"), dict)
                           else _f(g.get("growth_quality"))),
        "coverage_shift": g.get("coverage_shift"),
        "cyclical_flag": bool(g.get("cyclical_flag")),
        "peg_cagr": _f(g.get("peg_cagr")),
        "req_cagr": _f(p.get("required_cagr")),
        "exp_gap": _f(p.get("expectation_gap")),
        "implied_status": p.get("implied_status"),
    })
    _pg = _pf_gap(d.get("dd_60d"), g)
    d["pf_gap"], d["est_deterioration"] = _pg if _pg else (None, None)
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
    dims = _dimensions(scored["legs"])
    cov = _fund_coverage(d)
    if cov < 0.4:
        dims["business_health"] = None       # too sparse to grade
    bucket, bucket_notes = _business_bucket(
        dims.get("business_health"), d)
    sbd = _sbd_classify(dims, gates, d["pf_gap"])
    tech_flags = ([d["mom"]] if d.get("mom") in
                  ("knife", "capitulation", "breakdown", "downtrend")
                  else [])
    if d.get("sq_verdict") in ("new_shorts_pressing", "likely_covering"):
        tech_flags.append(f"shorts:{d['sq_verdict']}")
    return {**d, "classification": classification,
            "action": action, **scored, "gates": gates,
            "rsi": None,
            "dimensions": dims,
            "business_bucket": bucket,
            "bucket_notes": bucket_notes,
            "decline_cause": classification,
            "technical_flags": tech_flags,
            "fund_coverage": cov,
            "confidence": ("low" if cov < 0.4 else
                           "medium" if cov < 0.7 else "high"),
            "pf_gap_note": _gap_note(d["pf_gap"], d["est_deterioration"],
                             d.get("dd_60d"), bucket),
            "sbd": sbd,
            "entry_plan": _entry_plan(d)}


def _one_metrics(sym: str) -> Optional[dict]:
    """The scan's tape-metric window pass scoped to one symbol — the
    stock page's live read, not a separate computation."""
    from app.database import db
    rows = db.execute_query(
        _METRICS_SQL.replace("FROM daily_bars",
                             "FROM daily_bars WHERE symbol = :s"),
        {"s": sym})
    if not rows:
        return None
    r = rows[0]
    c, c1, c5 = _f(r["close"]), _f(r["c1"]), _f(r["c5"])
    if not c:
        return None
    return {"close": c, "ret_1d": (c / c1 - 1) if c1 else None,
            "ret_5d": (c / c5 - 1) if c5 else None,
            "dd_60d": (c / _f(r["h60"]) - 1) if _f(r["h60"]) else None,
            "vol_ratio": (_f(r["v5"]) / _f(r["v60"]))
            if _f(r["v60"]) else None,
            "d_sma20": (c / _f(r["s20"]) - 1) if _f(r["s20"]) else None,
            "d_sma50": (c / _f(r["s50"]) - 1) if _f(r["s50"]) else None,
            "d_sma200": (c / _f(r["s200"]) - 1) if _f(r["s200"]) else None,
            "as_of": str(r["date"])}


def _sector_median(sector: str) -> Optional[float]:
    """Median 5d return of same-sector names — the 'falling with
    peers or on its own merits' input for a single-symbol eval."""
    if not sector:
        return None
    from app.database import db
    rows = db.execute_query(
        "SELECT b.close / b.c5 - 1 AS r5 FROM ("
        " SELECT db.symbol, db.close,"
        "  LAG(db.close,5) OVER wnd AS c5,"
        "  ROW_NUMBER() OVER (PARTITION BY db.symbol"
        "                   ORDER BY db.date DESC) rn"
        "  FROM daily_bars db"
        "  JOIN stocks s ON s.symbol = db.symbol"
        "  WHERE s.sector = :sec AND s.is_active"
        "  WINDOW wnd AS (PARTITION BY db.symbol ORDER BY db.date)"
        " ) b WHERE b.rn = 1 AND b.c5 IS NOT NULL",
        {"sec": sector})
    vals = sorted(_f(r["r5"]) for r in rows if _f(r["r5"]) is not None)
    return vals[len(vals) // 2] if vals else None


def for_symbol(sym: str) -> dict:
    """The stock-page read — the same classify/score/gate/plan the
    scan runs, on stored data, for one name. The intake gate still
    applies: a name that didn't actually fall isn't a 'selloff
    opportunity' — it's just a stock."""
    from app.database import db
    s = sym.upper()
    rows = db.execute_query(
        _ROWS_SQL + " WHERE s.is_active AND s.momentum_state IS NOT NULL"
                    " AND s.symbol = :s", {"s": s})
    if not rows:
        chk = db.execute_query(
            "SELECT is_active, momentum_state FROM stocks"
            " WHERE symbol = :s", {"s": s})
        if not chk:
            why = "not in the stocks registry"
        elif not chk[0]["is_active"]:
            why = "inactive"
        else:
            why = "no momentum state yet — needs a momentum refresh"
        return {"symbol": s, "candidate": False, "reason": why}
    r = dict(rows[0])
    m = _one_metrics(s)
    if not m or m.get("ret_5d") is None:
        return {"symbol": s, "candidate": False,
                "reason": "no tape data"}
    market = _market()
    spy5 = _f(market.get("spy_5d")) or 0.0
    rel5 = m["ret_5d"] - spy5
    dd60 = m.get("dd_60d") or 0
    if rel5 > -0.03 and (m["ret_5d"] or 0) > -0.04 and dd60 > -0.10:
        return {"symbol": s, "candidate": False,
                "reason": "no dislocation — the intake gate reads "
                          "this as an ordinary move, not a selloff"}
    sm = _sector_median(r.get("sector"))
    sec_med = {r["sector"]: sm} if sm is not None else {}
    sq = {}
    try:
        from app.signals import short_squeeze
        sq = (short_squeeze.flags([s]) or {}).get(s) or {}
    except Exception:
        pass
    market = {**market, "spy_5d": spy5}
    c = _row_to_d(r, m, market, sec_med, sq,
                  gj={s: (_growth_names().get(s) or {})},
                  pi={s: (_priced_in_map().get(s) or {})})
    c["rsi"] = _rsi(s)
    legs = _score(c)["legs"]            # rescore with RSI present
    c["legs"] = legs
    c["score"] = round(sum(legs.values()), 1)
    c["dimensions"] = _dimensions(legs)
    if c["fund_coverage"] < 0.4:
        c["dimensions"]["business_health"] = None
    c["business_bucket"], c["bucket_notes"] = _business_bucket(
        c["dimensions"].get("business_health"), c)
    c["pf_gap_note"] = _gap_note(c["pf_gap"], c["est_deterioration"],
                               c.get("dd_60d"), c["business_bucket"])
    c["sbd"] = _sbd_classify(c["dimensions"], c["gates"], c["pf_gap"])
    c["decision"] = ("priority" if c["score"] >= 85 else
                     "starter" if c["score"] >= 75 else
                     "watch" if c["score"] >= 65 else "pass")
    if c["gates"]:
        c["decision"] = "watch" if not any(
            "structural" in g or "repricing" in g
            for g in c["gates"]) else "reject"
    c["sbd_rank"] = _SBD_ORDER.get(
        (c.get("sbd") or {}).get("class"), 6)
    c["candidate"] = True
    c["as_of"] = str(date.today())
    return c


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
    market = {**market, "spy_5d": spy5}

    rows = db.execute_query(_ROWS_SQL + _ROWS_SCOPE)

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

    gj = _growth_names()
    pi = _priced_in_map()

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
        cands.append(_row_to_d(r, m, market, sec_med,
                               sq_flags.get(sym) or {},
                               gj=gj, pi=pi))

    # RSI only for shortlisted names — bound the reads. Shortlist
    # by SBD rank so a true dislocation with a modest composite
    # doesn't get crowded out by a big-drop deteriorating business.
    cands.sort(key=_rank_key)
    for c in cands[:40]:
        c["rsi"] = _rsi(c["symbol"])
        legs = _score(c)["legs"]          # rescore with RSI present
        c["legs"] = legs
        c["score"] = round(sum(legs.values()), 1)
        c["dimensions"] = _dimensions(legs)
        if c["fund_coverage"] < 0.4:
            c["dimensions"]["business_health"] = None
        c["business_bucket"], c["bucket_notes"] = _business_bucket(
            c["dimensions"].get("business_health"), c)
        c["pf_gap_note"] = _gap_note(
            c["pf_gap"], c["est_deterioration"], c.get("dd_60d"),
            c["business_bucket"])
        c["sbd"] = _sbd_classify(c["dimensions"], c["gates"],
                                c["pf_gap"])
        c["decision"] = ("priority" if c["score"] >= 85 else
                         "starter" if c["score"] >= 75 else
                         "watch" if c["score"] >= 65 else "pass")
        if c["gates"] and c["decision"] not in ("reject",):
            c["decision"] = "watch" if not any(
                "structural" in g or "repricing" in g
                for g in c["gates"]) else "reject"
    for c in cands:
        c["sbd_rank"] = _SBD_ORDER.get(
            (c.get("sbd") or {}).get("class"), 6)
    cands.sort(key=_rank_key)

    if persist and cands:
        _persist(market, cands)
    return {"as_of": str(date.today()), "market": market,
            "candidates": cands[:30],
            "note": ("ranked by SBD class — beaten-down businesses "
                     "with verified dislocation first, turnarounds "
                     "next, deteriorating businesses and rejects at "
                     "the bottom; a low score means 'not mispriced', "
                     "not 'bad company'")}


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
              "fd": json.dumps({k: c.get(k) for k in
                                ("fund_state", "thesis", "fv", "fv_upside",
                                 "est_rev", "fcf_margin", "rev_growth",
                                 "pf_gap", "pf_gap_note", "est_deterioration",
                                 "eps_rev28_30d", "rev_rev28_30d",
                                 "dimensions", "business_bucket",
                                 "sbd", "coverage_shift")},
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
