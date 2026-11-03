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
from typing import Any

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
