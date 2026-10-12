"""Swing-point structure — the higher-low read.

dip_phase answers "is momentum healing?" — this answers the structural
question the dip_phase can't: has the stock carved a HIGHER LOW inside
a confirmed uptrend, and has it proven it by breaking the pullback's
counter-swing high?

    uptrend (HH + HL pivots, px > sma50 rising)
      → pullback from last pivot high
        → new pivot low > prior significant pivot low  = higher low
          → close > pullback swing high                 = CONFIRMED

The classic failure this guards against: buying "a 5% dip" that is in
fact the first leg of a breakdown (lower low prints, pivot chain
breaks). You can't know the bottom in real-time — you CAN know when
the structure has stopped falling and buyers have reclaimed the
pullback high.

Volume tells you whether the pullback is resting or distributing:
  healthy   rally volume > pullback volume, bounce volume expanding
  suspect   pullback volume ≥ rally volume (institutional selling)
"""
from __future__ import annotations

from typing import Any, Optional


def pivots(bars, k: int = 3) -> list[dict[str, Any]]:
    """Confirmed swing points: bar i is a pivot high iff its high is the
    max over [i-k, i+k] (needs k bars after it to confirm — the last k
    bars can never pivot, which is what makes 'still falling' honest).
    Same-magnitude runs are deduped keeping the extreme."""
    pts = []
    n = len(bars)
    for i in range(k, n - k):
        hi, lo = bars[i].high, bars[i].low
        if hi >= max(b.high for b in bars[i - k:i + k + 1]):
            pts.append({"i": i, "date": str(bars[i].date), "px": hi,
                        "kind": "H"})
        if lo <= min(b.low for b in bars[i - k:i + k + 1]):
            pts.append({"i": i, "date": str(bars[i].date), "px": lo,
                        "kind": "L"})
    # collapse consecutive same-kind runs to their extreme
    out = []
    for p in pts:
        if out and out[-1]["kind"] == p["kind"]:
            better = (p["px"] > out[-1]["px"]) if p["kind"] == "H" \
                else (p["px"] < out[-1]["px"])
            if better:
                out[-1] = p
        else:
            out.append(p)
    return out


def higher_low_setup(bars, sma50: Optional[float] = None,
                     sma50_prev: Optional[float] = None) -> Optional[dict]:
    """The pullback→higher-low→confirmation read. Returns the structure
    dict or None when there aren't enough pivots to say anything."""
    if not bars or len(bars) < 60:
        return None
    pts = pivots(bars, k=3)
    highs = [p for p in pts if p["kind"] == "H"]
    lows = [p for p in pts if p["kind"] == "L"]
    if len(highs) < 2 or len(lows) < 2:
        return None

    px = bars[-1].close
    last_hi, prev_hi = highs[-1], highs[-2]
    last_lo, prev_lo = lows[-1], lows[-2]

    # --- trend leg ---------------------------------------------------
    hh = last_hi["px"] > prev_hi["px"]
    hl_seq = last_lo["px"] > prev_lo["px"]
    s50_rising = (sma50 is not None and sma50_prev is not None
                  and sma50 > sma50_prev)
    above50 = sma50 is not None and px > sma50
    trend_ok = hh and hl_seq

    # --- pullback leg -------------------------------------------------
    pull_from = last_hi if last_hi["i"] < len(bars) - 1 else prev_hi
    # the decline since that pivot high: lowest low after it
    lo_bars = bars[pull_from["i"]:]
    dip_low = min(b.low for b in lo_bars)
    pullback_pct = dip_low / pull_from["px"] - 1 if pull_from["px"] else 0

    # --- higher low? ---------------------------------------------------
    # the current swing low = lowest low since the last pivot high;
    # a HIGHER low needs it above the PRIOR significant swing low
    # (last_lo if it formed before the pullback started, else prev_lo)
    ref_lo = last_lo if last_lo["i"] < pull_from["i"] else prev_lo
    higher_low = dip_low > ref_lo["px"]

    # --- confirmation level -------------------------------------------
    # the counter-swing high inside the pullback — the price buyers must
    # reclaim. Minor pivots (k=2) catch the bounce high; if none formed
    # yet, the last 5 bars' high is the live line.
    minor = [p for p in pivots(bars, k=2)
             if p["kind"] == "H" and p["i"] > pull_from["i"]]
    confirm_level = (minor[-1]["px"] if minor
                     else max(b.high for b in bars[-5:]))

    # anchored VWAP from the pivot high — the institutional line in the
    # sand for this pullback; reclaiming it means the dip-buyers who
    # sold the top are being forced back in
    leg = bars[pull_from["i"]:]
    pv = vv = 0.0
    for b in leg:
        tp = (b.high + b.low + b.close) / 3
        pv += tp * (b.volume or 0)
        vv += (b.volume or 0)
    avwap = pv / vv if vv else None
    avwap_reclaimed = avwap is not None and px > avwap
    # proof = close over BOTH the counter-swing high and the anchored
    # VWAP — either alone can be a squeeze; together it's structure
    confirmed = (higher_low and px > confirm_level
                 and (avwap_reclaimed or avwap is None))

    # --- support zone: prior breakout high = old resistance → support -
    prior_res = [p for p in highs[:-1] if p["px"] < pull_from["px"]]
    support = prior_res[-1] if prior_res else None
    near_support = (support is not None and
                    abs(dip_low / support["px"] - 1) < 0.04)

    # --- volume character ---------------------------------------------
    def _avg_vol(sl):
        vs = [b.volume for b in sl if (b.volume or 0) > 0]
        return sum(vs) / len(vs) if vs else None
    rally = bars[max(0, ref_lo["i"]):pull_from["i"] + 1]
    dip = bars[pull_from["i"]:]
    bounce = bars[-3:]
    rv = _avg_vol([b for b in rally if b.close >= b.open])
    dv = _avg_vol([b for b in dip if b.close < b.open])
    bv = _avg_vol([b for b in bounce if b.close >= b.open])
    vol_ok = (dv is not None and rv is not None and dv < rv)

    phase = ("confirmed" if confirmed else
             "higher_low" if higher_low else
             "unconfirmed" if pullback_pct > -0.25 else "broken")
    if not higher_low and dip_low < ref_lo["px"] * 0.98:
        phase = "broken"                       # pivot chain violated
    return {
        "phase": phase,
        "trend_ok": trend_ok, "hh": hh, "hl_seq": hl_seq,
        "s50_rising": s50_rising, "above50": above50,
        "pullback_pct": round(pullback_pct, 4),
        "swing_low": round(dip_low, 2),
        "swing_low_vs_prior": round(dip_low / ref_lo["px"] - 1, 4),
        "prior_low": round(ref_lo["px"], 2),
        "prior_low_date": ref_lo["date"],
        "confirm_level": round(confirm_level, 2),
        "avwap": round(avwap, 2) if avwap else None,
        "avwap_reclaimed": bool(avwap_reclaimed),
        "confirmed": confirmed,
        "near_support": bool(near_support),
        "support_px": round(support["px"], 2) if support else None,
        "support_date": support["date"] if support else None,
        "vol_pullback_vs_rally": (round(dv / rv, 2)
                                 if dv and rv else None),
        "vol_ok": bool(vol_ok),
        "bounce_vol": (round(bv / rv, 2) if bv and rv else None),
    }


# --- the trigger list ---------------------------------------------------------
#
# momentum_detail.swing is refreshed by the `momentum` job (13:30/21:30
# UTC); this is a pure stored-state read — symbol → distance from the
# last close to its higher-low confirmation level. Zero fetches.

_GOOD_FUND = {"accelerating", "growing"}
_GOOD_TAPE = {"pullback", "basing", "uptrend", "recovery", "breakout"}


def triggers(max_dist: float = 0.03, limit: int = 30) -> dict:
    """Names at/near the higher-low confirmation trigger.

    confirmed = structure already proven (close > pullback swing high)
    watch     = higher_low carved, within max_dist of the trigger close
    """
    import json as _j
    from app.database import db
    rows = db.execute_query(
        """
        SELECT s.symbol, s.momentum_state, s.fundamental_state,
               s.fundamental_risk, s.momentum_detail->'swing' AS sw,
               b.close, b.date AS px_date
        FROM stocks s
        JOIN LATERAL (SELECT close, date FROM daily_bars d
                      WHERE d.symbol = s.symbol
                      ORDER BY date DESC LIMIT 1) b ON true
        WHERE s.momentum_detail->'swing'->>'phase'
              IN ('higher_low', 'confirmed')
        """)
    conf, watch = [], []
    for r in rows:
        sw = r.get("sw")
        if isinstance(sw, str):
            try:
                sw = _j.loads(sw)
            except Exception:
                continue
        px, cf = r.get("close"), sw.get("confirm_level")
        if not px or not cf:
            continue
        dist = cf / px - 1
        row = {"symbol": r["symbol"], "px": round(px, 2),
               "px_date": str(r.get("px_date")),
               "momentum": r.get("momentum_state"),
               "fund_state": r.get("fundamental_state"),
               "risk": r.get("fundamental_risk"),
               "swing_low": sw.get("swing_low"),
               "prior_low": sw.get("prior_low"),
               "confirm_level": cf,
               "dist_pct": round(dist * 100, 2),
               "pullback_pct": sw.get("pullback_pct"),
               "vol_pullback_vs_rally": sw.get("vol_pullback_vs_rally"),
               "near_support": sw.get("near_support")}
        if sw.get("phase") == "confirmed":
            conf.append(row)
        elif 0 < dist <= max_dist:
            watch.append(row)
    watch.sort(key=lambda x: x["dist_pct"])
    conf.sort(key=lambda x: x["dist_pct"])
    return {"confirmed": conf, "triggers": watch[:limit],
            "scanned": len(rows)}
