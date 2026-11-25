"""Forward analog engine — 'when the market looked like this before,
what happened next?'

Deterministic nearest-neighbor search over SPY + ^VIX daily history:
  state vector per day = (vix level, spy vs 50dma, spy vs 200dma,
                          spy 20d momentum, spy 60d momentum)
Each day's forward returns are recorded at 20/60/120/252 trading
days. The 15 nearest historical states to TODAY's vector define the
outcome distribution — medians, quartiles, hit rates, worst case.

Honest-uncertainty rule: n < 12 usable analogs → the horizon is
reported but flagged LOW EVIDENCE; the probability is the observed
frequency, not a calibrated model output.
"""

import math
from typing import Any, Optional

from app.database import db

HORIZONS = (5, 20, 60, 120, 252)
K_NEAREST = 15
MIN_SAMPLE = 12


def _series(sym: str, limit: int = 3000) -> list[dict]:
    return db.execute_query(
        "SELECT date, close FROM daily_bars WHERE symbol=:s"
        " ORDER BY date DESC LIMIT :n",
        {"s": sym, "n": limit})


def _closes(rows: list[dict]) -> dict[str, float]:
    return {str(r["date"]): float(r["close"]) for r in rows
            if r.get("close") is not None}


def _state(dates, spy, vix, i) -> dict | None:
    d = dates[i]
    s = spy.get(d)
    v = vix.get(d)
    if s is None or v is None or i < 200:
        return None
    sma50 = sum(spy[dates[j]] for j in range(i - 49, i + 1)
                if dates[j] in spy) / 50
    sma200 = sum(spy[dates[j]] for j in range(i - 199, i + 1)
                 if dates[j] in spy) / 200
    m20 = s / spy[dates[i - 20]] - 1 if dates[i - 20] in spy else None
    m60 = s / spy[dates[i - 60]] - 1 if dates[i - 60] in spy else None
    if m20 is None or m60 is None:
        return None
    return {"vix": v, "vs50": s / sma50 - 1, "vs200": s / sma200 - 1,
            "mom20": m20, "mom60": m60}


def _norm(states: list[dict]) -> dict[str, tuple[float, float]]:
    """Per-feature mean/std so no single feature dominates distance."""
    out = {}
    for k in ("vix", "vs50", "vs200", "mom20", "mom60"):
        xs = [s[k] for s in states]
        mu = sum(xs) / len(xs)
        sd = math.sqrt(sum((x - mu) ** 2 for x in xs) / len(xs)) or 1
        out[k] = (mu, sd)
    return out


def _dist(a: dict, b: dict, norm) -> float:
    return math.sqrt(sum(((a[k] - b[k]) / norm[k][1]) ** 2
                         for k in ("vix", "vs50", "vs200", "mom20", "mom60")))


def _stats(rets: list[float]) -> dict:
    if not rets:
        return {"n": 0}
    rets = sorted(rets)
    n = len(rets)
    q = lambda p: rets[min(n - 1, int(p * n))]
    return {"n": n,
            "median_pct": round(q(0.5) * 100, 1),
            "p25_pct": round(q(0.25) * 100, 1),
            "p75_pct": round(q(0.75) * 100, 1),
            "pct_positive": round(sum(1 for r in rets if r > 0)
                                  / n * 100, 0),
            "worst_pct": round(rets[0] * 100, 1),
            "low_evidence": n < MIN_SAMPLE}


def market_outlook() -> dict[str, Any]:
    """The Engine-1 deliverable: today's state + what analogous states
    did next, per horizon."""
    spy = _closes(_series("SPY"))
    vix = _closes(_series("^VIX"))
    dates = sorted(set(spy) & set(vix))
    if len(dates) < 800:
        return {"error": "insufficient history for analog search",
                "days": len(dates)}
    states, fwd = [], []
    for i, d in enumerate(dates):
        s = _state(dates, spy, vix, i)
        if s is None:
            continue
        st = {"date": d, **s}
        fr = {}
        for h in HORIZONS:
            j = i + h                     # forward = later in the
            if j < len(dates):            # ascending date list
                fr[h] = spy[dates[j]] / spy[d] - 1
        states.append(st)
        fwd.append(fr)
    today = states[-1]
    norm = _norm([{k: s[k] for k in s if k != "date"} for s in states])
    tv = {k: today[k] for k in today if k != "date"}
    ranked = sorted(
        ((d := _dist(tv, {k: s[k] for k in s if k != "date"}, norm), i)
         for i, s in enumerate(states[:-1])),
        key=lambda x: x[0])[:K_NEAREST]
    horizons = {}
    for h in HORIZONS:
        rets = [fwd[i][h] for _, i in ranked if h in fwd[i]]
        horizons[f"{h}d"] = _stats(rets)
    return {
        "as_of": dates[-1],
        "current_state": {k: round(tv[k], 3) for k in tv},
        "analogs": [{"date": states[i]["date"],
                     "distance": round(d, 2)} for d, i in ranked],
        "horizons": horizons,
        "method": ("kNN on (vix, spy vs 50/200dma, 20d/60d momentum); "
                   "observed forward outcomes, not a calibrated model"),
    }


# ---------------- liquidity-conditioned analogs ---------------------
# Spec v2 §3.7 — SPY/QQQ/SMH forward distributions with overfitting
# guards: two-stage match (coarse regime first, liquidity/flow as
# secondary conditioning), episode dedupe (overlapping forward
# windows aren't independent samples), reliability tiers.
#
# Honest-data note: the journaled liquidity score only goes back
# weeks — history can't be conditioned on it. The conditioning proxy
# is the 13-week NET-LIQUIDITY SLOPE quintile computed from FRED's
# full-history series (WALCL−TGA−RRP, $B) — labeled a proxy, never
# presented as the live score's own history. Flow conditioning is a
# coarse defensive-bid flag (TLT-or-GLD 20d > SPY 20d).

_LIQ_HORIZONS = (20, 60, 120)
_LIQ_ASSETS = ("SPY", "QQQ", "SMH")
_EPISODE_GAP = 20        # match dates <20 obs apart = one episode
_MIN_HISTORY = 800       # ~3.2y — episodes need depth to mean anything


def _net_liq_history() -> dict[str, float]:
    """date → net-liquidity 13wk slope quintile (0-4), from full-
    history FRED series. $B-normalized (WALCL/WTREGEN are $M)."""
    from app.signals.correction_alarms import _fred_series
    wal = {str(d): v / 1000 for d, v in
           _fred_series("WALCL", days=4000)}
    tg = {str(d): v / 1000 for d, v in
          _fred_series("WTREGEN", days=4000)}
    rp = {str(d): v for d, v in _fred_series("RRPONTSYD", days=4000)}
    nl = {d: wal[d] - tg[d] - rp.get(d, 0.0) for d in wal
          if d in tg and d in rp}
    if len(nl) < 80:
        return {}
    dates = sorted(nl)
    slope = {}                    # $B change over ~13 weekly obs
    for i in range(13, len(dates)):
        slope[dates[i]] = nl[dates[i]] - nl[dates[i - 13]]
    vals = sorted(slope.values())
    n = len(vals)
    def quint(v):
        # rank position → 0..4
        import bisect
        return min(4, bisect.bisect_left(vals, v) * 5 // max(1, n))
    return {d: quint(s) for d, s in slope.items()}


def _regime_key(s: dict) -> tuple:
    vb = 0 if s["vix"] < 15 else 1 if s["vix"] <= 25 else 2
    return (vb, s["vs200"] >= 0, s["mom60"] >= 0)


def _defensive_bid(dates, closes, i) -> Optional[bool]:
    """TLT-or-GLD beating SPY over 20d = defensive rotation."""
    spy, tlt, gld = closes.get("SPY"), closes.get("TLT"), \
        closes.get("GLD")
    if not spy or i < 20:
        return None
    d, d0 = dates[i], dates[i - 20]
    if d not in spy or d0 not in spy:
        return None
    spy_r = spy[d] / spy[d0] - 1
    for px in (tlt, gld):
        if px and d in px and d0 in px:
            if px[d] / px[d0] - 1 > spy_r:
                return True
    return False


def _episodes(match_dates: list[str], all_dates: list[str]
              ) -> list[list[str]]:
    """Cluster matched dates: <_EPISODE_GAP trading days apart = one
    episode — overlapping forward windows aren't independent."""
    idx = {d: i for i, d in enumerate(all_dates)}
    eps, cur, last = [], [], None
    for d in match_dates:
        i = idx[d]
        if last is not None and i - last < _EPISODE_GAP:
            cur.append(d)
        else:
            if cur:
                eps.append(cur)
            cur = [d]
        last = i
    if cur:
        eps.append(cur)
    return eps


def liquidity_conditioned() -> dict[str, Any]:
    """'When liquidity + tape looked like this, what did SPY/QQQ/SMH
    do next?' — conditional distributions, never a forecast."""
    closes = {s: _closes(_series(s)) for s in
              ("SPY", "QQQ", "SMH", "TLT", "GLD", "^VIX")}
    spy, vix = closes["SPY"], closes["^VIX"]
    dates = sorted(set(spy) & set(vix))
    if len(dates) < _MIN_HISTORY:
        return {"error": "insufficient history", "days": len(dates)}
    liq_q = _net_liq_history()
    # FRED obs are weekly — a trading day takes the latest quintile
    # at or before it, never a forward-looking obs
    liq_dates = sorted(liq_q)

    def liq_at(d: str) -> Optional[int]:
        import bisect
        j = bisect.bisect_right(liq_dates, d) - 1
        return liq_q[liq_dates[j]] if j >= 0 else None

    states, fwd = [], {s: [] for s in _LIQ_ASSETS}
    for i, d in enumerate(dates):
        s = _state(dates, spy, vix, i)
        if s is None:
            continue
        states.append({"date": d, "i": i, **s,
                       "liq_q": liq_at(d),
                       "defensive": _defensive_bid(dates, closes, i)})
        for sym in _LIQ_ASSETS:
            px = closes[sym]
            fr = {}
            for h in _LIQ_HORIZONS:
                j = i + h
                if j < len(dates) and dates[j] in px and d in px:
                    fr[h] = px[dates[j]] / px[d] - 1
            fwd[sym].append(fr)

    today = states[-1]
    tv = {k: today[k] for k in ("vix", "vs50", "vs200", "mom20",
                                "mom60")}
    norm = _norm([{k: s[k] for k in tv} for s in states])
    key = _regime_key(tv)

    # stage 1 — coarse regime pool; widen once if too thin (journaled)
    pool = [i for i, s in enumerate(states[:-1])
            if _regime_key(s) == key]
    widened = False
    if len(pool) < MIN_SAMPLE:
        pool = [i for i, s in enumerate(states[:-1])
                if _regime_key(s)[:2] == key[:2]]
        widened = True

    # stage 2 — rank by regime distance + secondary conditioning
    # penalties: liquidity quintile diff + defensive-bid mismatch.
    def rankdist(s):
        base = _dist(tv, {k: s[k] for k in tv}, norm)
        if s.get("liq_q") is not None and today.get("liq_q") is not None:
            base += 0.4 * abs(s["liq_q"] - today["liq_q"])
        if s.get("defensive") is not None \
                and today.get("defensive") is not None \
                and s["defensive"] != today["defensive"]:
            base += 0.3
        return base

    ranked = sorted(pool, key=lambda i: rankdist(states[i]))[:K_NEAREST]
    match_dates = sorted(states[i]["date"] for i in ranked)
    eps = _episodes(match_dates, dates)
    # each episode contributes ONE observation — median of member
    # dates' forward returns, so clustered regimes don't double-count
    idx_of = {s["date"]: i for i, s in enumerate(states)}

    dists = {s: {} for s in _LIQ_ASSETS}
    for sym in _LIQ_ASSETS:
        for h in _LIQ_HORIZONS:
            obs = []
            for ep in eps:
                vals = [fwd[sym][idx_of[d]][h] for d in ep
                        if h in fwd[sym][idx_of[d]]]
                if vals:
                    vals.sort()
                    obs.append(vals[len(vals) // 2])
            st = _stats(obs)
            st["episodes"] = len(eps)
            st["reliability"] = ("adequate" if len(obs) >= 30 else
                                 "moderate" if len(obs) >= MIN_SAMPLE
                                 else "low")
            dists[sym][f"{h}d"] = st

    return {
        "as_of": dates[-1],
        "current": {"vix": round(tv["vix"], 1),
                    "vs200": round(tv["vs200"], 3),
                    "mom60": round(tv["mom60"], 3),
                    "liq_quintile": today.get("liq_q"),
                    "defensive_bid": today.get("defensive")},
        "regime_key": [int(key[0]), bool(key[1]), bool(key[2])],
        "pool_n": len(pool), "pool_widened": widened,
        "matched_obs": len(ranked), "episodes": len(eps),
        "match_dates": match_dates,
        "distributions": dists,
        "method": ("two-stage kNN: coarse VIX×trend×mom60 regime pool "
                   "first, then distance + liquidity-quintile and "
                   "defensive-bid conditioning; episodes dedupe "
                   "overlapping forward windows; liq quintile is a "
                   "13wk net-liquidity-slope proxy (journal history "
                   "is too short to condition on directly)"),
        "low_evidence": len(eps) < MIN_SAMPLE,
    }


def stock_forward_distribution(sym: str) -> dict[str, Any]:
    """Engine-4 lite: the stock's own unconditional forward-return
    distribution at the same horizons — a baseline to compare the
    market-conditional signal against."""
    px = _closes(_series(sym.upper()))
    dates = sorted(px)
    if len(dates) < 320:
        return {"error": "insufficient history", "days": len(dates)}
    out = {}
    for h in HORIZONS:
        rets = [px[dates[i]] / px[dates[i - h]] - 1
                for i in range(h, len(dates))]
        out[f"{h}d"] = _stats(rets)
    return {"symbol": sym.upper(), "horizons": out,
            "method": "unconditional historical forward returns"}
