"""LEAPS screen — long-dated option selection (>400 DTE), the way a
desk would pick them.

FMP serves no options endpoints on this tier, so the chain comes from
yfinance (full chains incl. bid/ask/IV/OI out to Jan-2029 on AMD).
Greeks are computed locally — Black-Scholes on each contract's own IV
(stdlib NormalDist; no scipy).

Selection philosophy for buying calls:
  - deep-ish ITM: delta 0.70–0.80 — behaves like stock, theta drag low
  - minimize extrinsic% — time value is what you're renting
  - tight bid/ask and real open interest — LEAPS exits are the risk
  - IV vs realized vol — don't overpay for implied
  - breakeven + gearing shown so the trade-off is explicit

For puts the same logic mirrors (|delta| target ~0.45 — protective/
bearish-spec rather than stock-replacement).

Direction verdict is deterministic technicals: trend (SMA50/200),
RSI regime, MACD histogram, Bollinger %B — CALL / PUT / WAIT with
the reasons listed.
"""
from __future__ import annotations

import asyncio
import logging
import math
import pandas as pd
from datetime import date, datetime, timedelta, timezone
from statistics import NormalDist
from typing import Any, Optional

logger = logging.getLogger(__name__)

_N = NormalDist()
MIN_DTE = 400
RISK_FREE = 0.045
CALL_DELTA_TARGET = 0.72
PUT_DELTA_TARGET = 0.45   # abs value
THESIS_DRIFT = 0.25       # bull thesis: +25%/yr real drift — "sees new
                          # highs within ~a year"


# --- Black-Scholes --------------------------------------------------------


def _bs(S: float, K: float, T: float, r: float, iv: float,
        call: bool) -> tuple[Optional[float], Optional[float],
                             Optional[float]]:
    """(delta, theta_per_day, gamma). None when iv/T degenerate.
    Gamma matters here because the burst-exit goal (sell into +50%/
    +100% news spikes) lives on delta expansion — ATM contracts carry
    peak gamma."""
    if S <= 0 or K <= 0 or T <= 0 or not iv or iv <= 0.001 or iv > 5:
        return None, None, None
    sq = iv * math.sqrt(T)
    d1 = (math.log(S / K) + (r + iv * iv / 2) * T) / sq
    d2 = d1 - sq
    gamma = _N.pdf(d1) / (S * sq)
    if call:
        delta = _N.cdf(d1)
        theta = (-(S * _N.pdf(d1) * iv) / (2 * math.sqrt(T))
                 - r * K * math.exp(-r * T) * _N.cdf(d2)) / 365
    else:
        delta = _N.cdf(d1) - 1
        theta = (-(S * _N.pdf(d1) * iv) / (2 * math.sqrt(T))
                 + r * K * math.exp(-r * T) * _N.cdf(-d2)) / 365
    return delta, theta, gamma


def _bs_value(S: float, K: float, T: float, r: float, iv: float,
              call: bool) -> Optional[float]:
    """Closed-form BS value — needed for 'sell in ~60 days' ROI, where
    the exit price is NOT terminal intrinsic: the contract still
    carries time value. The intrinsic-only scenario math understated
    near-term ATM/slightly-ITM exits (gamma expansion + retained
    extrinsic) — the exact contracts the flip strategy trades."""
    if S <= 0 or K <= 0 or T <= 0 or not iv or iv <= 0.001 or iv > 5:
        return None
    sq = iv * math.sqrt(T)
    d1 = (math.log(S / K) + (r + iv * iv / 2) * T) / sq
    d2 = d1 - sq
    if call:
        return S * _N.cdf(d1) - K * math.exp(-r * T) * _N.cdf(d2)
    return K * math.exp(-r * T) * _N.cdf(-d2) - S * _N.cdf(-d1)


# --- technicals + direction ------------------------------------------------


def _technicals(bars) -> dict[str, Any]:
    from app.market_data import indicators as ind
    c = ind.closes(bars)
    if len(c) < 50:
        return {}
    price = float(c.iloc[-1])
    sma50, sma200 = ind.sma(bars, 50), ind.sma(bars, 200)
    rsi14 = ind.rsi(bars, 14)
    m_line, m_sig, m_hist = ind.macd(bars)
    # Bollinger (20, 2σ)
    m20, sd20 = c.rolling(20).mean().iloc[-1], c.rolling(20).std().iloc[-1]
    bb = {"mid": float(m20), "upper": float(m20 + 2 * sd20),
          "lower": float(m20 - 2 * sd20),
          "pct_b": float((price - (m20 - 2 * sd20)) / (4 * sd20))
          if sd20 else None,
          "width": float(4 * sd20 / m20) if m20 else None}
    return {
        "price": price,
        "sma50": sma50, "sma200": sma200,
        "vs_sma50": price / sma50 - 1 if sma50 else None,
        "vs_sma200": price / sma200 - 1 if sma200 else None,
        "sma50_slope_5d": ind.sma_slope(bars, 50, 5),
        "rsi14": rsi14,
        "macd_line": m_line, "macd_signal": m_sig, "macd_hist": m_hist,
        "bollinger": bb,
        "atr_pct": ind.atr_pct(bars),
        "hv20": ind.realized_vol(bars, 20),
        "hv60": ind.realized_vol(bars, 60),
        "dd52w": ind.drawdown_from_high(bars, 252),
        "perf_1m": ind.roc(bars, 21), "perf_6m": ind.roc(bars, 126),
    }


def _fundamentals(fmp, sym: str) -> dict[str, Any]:
    """The qualifier — the pull-back-and-rally strategy only makes
    sense on companies that KEEP making highs. 'Solid' = rev growth
    ≥15% YoY AND GM ≥40% AND a profit path (op margin or FCF > 0).
    'Deteriorating' — the structural-name PUT gate — is quantitative:
    2 consecutive QoQ revenue declines, GM compression >3pts QoQ, or
    YoY growth gone negative. Membership in our engines is surfaced
    as extra evidence."""
    out: dict[str, Any] = {"solid": False}
    try:
        inc = fmp._make_request("/income-statement",
                                {"symbol": sym, "period": "quarter",
                                 "limit": 8}) or []
        q, qy = (inc[0] if inc else {}), (inc[4] if len(inc) > 4 else {})
        rev_yoy = (q["revenue"] / qy["revenue"] - 1
                   if q.get("revenue") and qy.get("revenue") else None)
        gm = (q["grossProfit"] / q["revenue"]
              if q.get("grossProfit") and q.get("revenue") else None)
        gm_prev = (inc[1]["grossProfit"] / inc[1]["revenue"]
                   if len(inc) > 1 and inc[1].get("grossProfit")
                   and inc[1].get("revenue") else None)
        opm = (q["operatingIncome"] / q["revenue"]
               if q.get("operatingIncome") is not None and q.get("revenue")
               else None)
        out.update({"rev_growth": rev_yoy, "gross_margin": gm,
                    "op_margin": opm})
        out["solid"] = bool(rev_yoy is not None and rev_yoy >= 0.15
                            and gm is not None and gm >= 0.40
                            and opm is not None and opm > -0.05)
        det = []
        if len(inc) > 2 and all(r.get("revenue") for r in inc[:3]) \
                and inc[0]["revenue"] < inc[1]["revenue"] \
                < inc[2]["revenue"]:
            det.append("revenue declined 2 quarters in a row")
        if gm is not None and gm_prev is not None \
                and gm < gm_prev - 0.03:
            det.append(f"gross margin compressed "
                       f"{(gm_prev - gm) * 100:.0f}pts QoQ")
        if rev_yoy is not None and rev_yoy < 0:
            det.append("YoY revenue growth negative")
        out["deteriorating"] = bool(det)
        out["deterioration"] = det
    except Exception as exc:
        logger.debug("leaps fundamentals %s failed: %s", sym, exc)
    try:
        from app.database import db
        rows = db.execute_query(
            "SELECT 'rb' src, tier, NULL grade FROM rule_breaker_members "
            "WHERE symbol=:s UNION ALL "
            "SELECT '5x', tier, NULL FROM smallcap_members WHERE symbol=:s",
            {"s": sym})
        out["engine_membership"] = [
            f"{r['src']}:{r['tier']}" for r in rows]
        fw = db.execute_query(
            "SELECT gap_score, beat_streak, est_revision_pct "
            "FROM symbol_flywheel WHERE symbol=:s", {"s": sym})
        if fw:
            out["gap_score"] = fw[0]["gap_score"]
            out["beat_streak"] = fw[0]["beat_streak"]
            out["est_revision_pct"] = fw[0]["est_revision_pct"]
        st_row = db.execute_query(
            "SELECT next_earnings_date, next_earnings_eps_est "
            "FROM stocks WHERE symbol=:s", {"s": sym})
        if st_row and st_row[0].get("next_earnings_date"):
            out["next_earnings"] = str(st_row[0]["next_earnings_date"])
            out["next_earnings_eps_est"] = st_row[0]["next_earnings_eps_est"]
    except Exception:
        out["engine_membership"] = []
    return out


def _macd_hist_prev(bars, back: int = 5):
    """MACD histogram N bars ago — needed for momentum-stall checks
    (a falling histogram vetoes puts-at-highs)."""
    from app.market_data import indicators as ind
    from app.indicators.momentum import calculate_macd
    c = ind.closes(bars)
    if len(c) < 40 + back:
        return None
    _, _, hist = calculate_macd(c)
    if len(hist.dropna()) < back + 1:
        return None
    v = hist.dropna().iloc[-1 - back]
    return None if pd.isna(v) else float(v)


def _direction(t: dict, fund: dict, hist_prev: Optional[float] = None,
               cyclical: bool = False) -> tuple:
    """Cycle-aware verdict for the pull-back-and-rally strategy.
    Returns (verdict, cycle_stage, reasons, actions).

    The rule: solid fundamentals qualify the name; then buys PUTS at
    all-time-high extension (harvest the pullback) and CALLS at washed
    pullbacks inside the uptrend (ride it back to highs). Puts on
    STRUCTURAL names additionally require quantified fundamental
    deterioration — overextension alone isn't a short thesis. The
    euphoria zone (RSI≥75 / %B>0.95, still ripping) is a TRIM signal
    for held calls, not an entry signal for anything.
    """
    px, s50, s200 = t.get("price"), t.get("sma50"), t.get("sma200")
    rsi, hist = t.get("rsi14"), t.get("macd_hist")
    pct_b = (t.get("bollinger") or {}).get("pct_b")
    dd, vs50 = t.get("dd52w"), t.get("vs_sma50")
    if not all([px, s50, s200, rsi is not None, hist is not None]):
        return "WAIT", "unknown", ["insufficient technical data"], []

    if not fund.get("solid"):
        return ("SKIP", "disqualified",
                ["fundamentals gate failed — the pull-back-and-rally "
                 "strategy needs a company that keeps making highs: "
                 f"rev {(fund.get('rev_growth') or 0) * 100:+.0f}% "
                 f"(need ≥+15%), GM {(fund.get('gross_margin') or 0) * 100:.0f}% "
                 f"(need ≥40%), op margin "
                 f"{(fund.get('op_margin') or 0) * 100:+.0f}%"], [])

    up_trend = px > s200 and s50 > s200
    extended = (pct_b is not None and pct_b > 0.9) or rsi >= 68 \
        or (vs50 is not None and vs50 > 0.12)
    washed = (dd is not None and dd <= -0.15) or rsi <= 40 \
        or (pct_b is not None and pct_b < 0.25)
    # --- timing guards learned from the Jan-Sep 2026 replay ---------
    # PUTs must wait for the stall: hist falling/negative or price
    # rolled under the BB mid — AMD's "extended" puts fired while the
    # melt-up was still accelerating and got run over 5x.
    stalling = hist < 0 or (pct_b is not None and pct_b < 0.55) \
        or (hist_prev is not None and hist < hist_prev)
    # the put ENTRY is the crack itself, not the persistent stall:
    # hist crossing negative from ≥0 = first exhaustion evidence.
    # Without this, extended-stall re-fires every bar and the engine
    # re-enters puts 4 days after each invalidation — the AMD-2026
    # whipsaw machine (-43% book vs +571% buy-hold in the replay).
    fresh_stall = hist < 0 and (hist_prev is not None
                              and hist_prev >= 0)
    # CALLs veto the falling knife: deep wash + still-collapsing tape
    # (hist<0 AND below the BB mid) means the dip isn't done. And a
    # wash only becomes an entry once momentum STOPS falling —
    # dead-cat bounces inside bear legs satisfy "washed" forever.
    knife = hist < 0 and (pct_b is not None and pct_b < 0.35)
    stabilizing = hist_prev is None or hist > hist_prev
    # euphoria zone — the take-profit trigger for held calls
    climax = rsi >= 75 or (pct_b is not None and pct_b > 0.95)
    deteriorating = fund.get("deteriorating")
    # a put is sanctioned if cyclical (cycle turns on tape alone) OR
    # structural with the business itself weakening
    put_ok = cyclical or bool(deteriorating)

    reasons = [
        f"fundamentals ✓ (rev {(fund.get('rev_growth') or 0) * 100:+.0f}%, "
        f"GM {(fund.get('gross_margin') or 0) * 100:.0f}%)"
        + (" · ⚠ deteriorating: " + "; ".join(fund["deterioration"])
           if fund.get("deterioration") else ""),
        f"{'↑' if up_trend else '↓'} trend: px "
        f"{'>' if px > s200 else '<'} SMA200, "
        f"SMA50 {'>' if s50 > s200 else '<'} SMA200",
        f"RSI14 {rsi:.0f} · MACD hist {hist:+.2f} · BB %B "
        f"{pct_b if pct_b is not None else 0:.2f} · "
        f"vs SMA50 {(vs50 or 0) * 100:+.0f}% · "
        f"vs 52wH {(dd or 0) * 100:+.0f}%",
    ]
    if fund.get("engine_membership"):
        reasons.insert(1, "on our boards: "
                          + ", ".join(fund["engine_membership"]))
    reasons.insert(1 if not fund.get("engine_membership") else 2,
                   "cyclical (full CALL→PUT→CALL rotation)" if cyclical
                   else "structural (puts need fundamental "
                        "deterioration, not just extension)")

    # the cycle: ATH extension → PUT (once it stalls); washed inside
    # uptrend + not still collapsing + momentum stabilizing → CALL
    if up_trend and washed and not knife and not stabilizing:
        return ("WAIT", "wash_not_stabilized",
                reasons + ["pulled back and not knife-deep, but MACD "
                           "hist is still falling — the wash isn't "
                           "done. CRDO's 2026 bear leg showed why: "
                           "'washed' bounces inside downtrends were "
                           "three consecutive -45% stops. Wait for "
                           "momentum to tick up."],
                ["no action — accumulation needs momentum "
                 "stabilizing (hist > 5d-ago), not just depth"])

    if up_trend and washed and not knife:
        return ("CALL", "pullback_in_uptrend",
                reasons + ["PULLED BACK inside a strong uptrend — the "
                           "CRDO-at-$150 setup. Buy LEAPS calls, ride "
                           "the re-rally toward prior highs. Exit/flip "
                           "to puts at the next ATH extension."],
                ["enter calls in tranches: 50-60% of the options "
                 "allocation now, 20-30% on trend confirmation, "
                 "keep ~20% reserve",
                 "prefer δ0.70-0.85 strikes (≥70% intrinsic) — not "
                 "cheap-looking OTM"])

    if up_trend and washed and knife:
        return ("WAIT", "falling_knife",
                reasons + ["pulled back but still collapsing (MACD "
                           "hist<0, below BB mid) — the knife zone. "
                           "Let it base; calls once momentum stops "
                           "bleeding."],
                ["no action — let the wash finish; revisit when MACD "
                 "hist stops falling or price reclaims the BB mid"])

    if extended and stalling and put_ok and not fresh_stall:
        return ("WAIT", "stale_stall",
                reasons + ["extended and put-eligible, but the "
                           "momentum crack is OLD — the put entry was "
                           "the day hist crossed negative. Re-entering "
                           "late into a persistent stall is the "
                           "whipsaw zone; wait for the next "
                           "extension."],
                ["no action — puts enter on the FRESH crack (hist "
                 "crossing <0), not a stale stall",
                 "if holding calls from lower: they're already "
                 "trimmed at climax — sit in cash for the next "
                 "extension"])

    if extended and stalling and put_ok:
        stage = "ath_extension" if dd is not None and dd > -0.08 \
            else "extended"
        return ("PUT", stage,
                reasons + ["momentum stalled at extension"
                           + (" — cyclical name, the cycle WILL turn: "
                              if cyclical else
                              " AND fundamentals deteriorating — "),
                           "harvest the pullback with LEAPS puts. "
                           "Flip back to calls once it washes."],
                ["if holding calls: EXIT them — this is the flip",
                 "use put DEBIT SPREADS when IV is elevated (buy "
                 "|δ|~0.45 put / sell |δ|~0.20 put) — cuts cost ~35% "
                 "and shrinks vega",
                 "size the put at 20-30% of the call allocation — "
                 "counter-trend legs are always smaller",
                 "TIME-STOP: exit/roll if no −15% within ~90 days or "
                 "if price makes a new high post-stall — thesis "
                 "invalidated, don't martyr to it"])

    if extended and stalling and not put_ok:
        return ("WAIT", "climax_structural",
                reasons + ["extended AND stalling, but fundamentals "
                           "are INTACT — overextension alone isn't a "
                           "short thesis on a structural grower. Cash "
                           "the calls; don't invert."],
                ["if holding calls: EXIT — momentum stall at "
                 "extension is the sell signal",
                 "do NOT buy puts while fundamentals are intact — "
                 "overextension ≠ reversal on structural names",
                 "alternative: keep a LEAPS call and SELL 30-60d "
                 "calls against it (PMCC) — monetize the inflated IV "
                 "instead of paying for it"])

    if extended:
        return ("WAIT", "climax" if climax else "extended_no_stall",
                reasons + [("EUPHORIA — RSI/BB pinned and momentum "
                            "still ripping. This is the TRIM zone, "
                            "not an entry zone."
                            if climax else
                            "extended BUT momentum still ripping "
                            "(MACD hist positive/rising) — don't "
                            "short a repricing; puts here get run "
                            "over. Wait for the stall.")],
                ["if holding calls: TRIM 50-70% now — don't wait for "
                 "the exact top; keep a runner for the stall signal"]
                + (["cyclical name: the cycle WILL turn — but puts "
                    "ONLY after the momentum stall prints (hist<0 or "
                    "roll under BB mid), not on extension alone"]
                   if cyclical else
                   ["structural name: overextension is NOT a short "
                    "signal while fundamentals are intact — sell "
                    "30-60d covered calls (PMCC) over the trimmed "
                    "core to harvest the IV spike instead"]))

    if up_trend:
        return ("WAIT", "mid_range",
                reasons + ["mid-range in uptrend — neither washed nor "
                           "stretched. Wait for the cycle: puts at "
                           "extension, calls at the wash."],
                ["no position warranted — capital is a position too"])
    return ("WAIT", "downtrend",
            reasons + ["below SMA200 — trend broken, not a pullback in "
                       "an uptrend. LEAPS calls here fight the tape; "
                       "revisit when it reclaims the 200-day."],
            ["do not buy calls on broken-trend names regardless of "
             "how 'cheap' they look"])


# --- chain enrichment -------------------------------------------------------


def _f(row, k, default=None):
    v = row.get(k)
    try:
        return default if v is None or pd.isna(v) else float(v)
    except (TypeError, ValueError):
        return default


def _mid(row) -> Optional[float]:
    bid, ask = _f(row, "bid"), _f(row, "ask")
    if bid and ask and ask > 0:
        return (bid + ask) / 2
    lp = _f(row, "lastPrice")
    return lp if lp and lp > 0 else None


def _enrich(row, S: float, T_days: int, r: float, call: bool,
            delta_target: float, hv: Optional[float]) -> Optional[dict]:
    mid = _mid(row)
    if not mid or mid < 0.5:
        return None
    bid, ask = _f(row, "bid", 0), _f(row, "ask", 0)
    spread_pct = (ask - bid) / mid if ask and bid else 1.0
    oi = int(_f(row, "openInterest", 0))
    K, iv = float(row["strike"]), _f(row, "impliedVolatility", 0)
    delta, theta, gamma = _bs(S, K, T_days / 365, r, iv, call)
    if delta is None:
        return None
    intrinsic = max(0.0, (S - K) if call else (K - S))
    extrinsic = mid - intrinsic
    extrinsic_pct = extrinsic / mid if mid else 0
    # hard liquidity floors — a LEAPS you can't exit is a loan
    if oi < 25 or spread_pct > 0.25:
        return None
    breakeven = (K + mid) if call else (K - mid)
    gearing = abs(delta) * S / mid
    iv_hv = iv / hv if hv else None
    # score: delta closeness (35) + low extrinsic (25) + tight spread
    # (15) + liquidity (15) + IV discipline (10)
    d_close = max(0.0, 1 - abs(abs(delta) - delta_target) / 0.45)
    s_extr = max(0.0, 1 - extrinsic_pct / 0.45)
    s_sprd = max(0.0, 1 - spread_pct / 0.25)
    s_oi = min(1.0, math.log10(oi + 1) / 3)
    s_iv = (max(0.0, 1 - (iv_hv - 1) / 1.0) if iv_hv else 0.5)
    score = round(35 * d_close + 25 * s_extr + 15 * s_sprd
                  + 15 * s_oi + 10 * s_iv, 1)
    return {
        "contract": row.get("contractSymbol"), "strike": K,
        "mid": round(mid, 2), "bid": bid, "ask": ask,
        "spread_pct": round(spread_pct * 100, 1),
        "delta": round(delta, 3),
        "gamma": round(gamma, 5) if gamma else None,
        "theta_day": round(theta, 4) if theta else None,
        "theta_annual_pct": round(abs(theta) * 365 / mid * 100, 1)
        if theta and mid else None,
        "iv": round(iv * 100, 1),
        "iv_vs_hv": round(iv_hv, 2) if iv_hv else None,
        "oi": oi, "volume": int(_f(row, "volume", 0)),
        "intrinsic": round(intrinsic, 2),
        "extrinsic_pct": round(extrinsic_pct * 100, 1),
        "breakeven": round(breakeven, 2),
        "breakeven_vs_spot": round((breakeven / S - 1) * 100, 1)
        if call else round((1 - breakeven / S) * 100, 1),
        "gearing": round(gearing, 2),
        "itm": bool(row.get("inTheMoney")),
        "moneyness": ("ATM" if abs(K / S - 1) <= 0.03 else
                     ("ITM" if K < S else "OTM") if call else
                     ("ITM" if K > S else "OTM")),
        "score": score,
        "capital": round(mid * 100),
        "_delta_raw": delta, "_K": K, "_T": T_days, "_iv": iv,
    }


def _spread(contracts: list[dict], call: bool) -> Optional[dict]:
    """Debit-spread suggestion: buy the best-scored contract, sell a
    cheaper same-expiry leg ~delta 0.2-0.35 further OTM. Caps cost and
    vega — the right structure when IV is elevated. Reports net debit,
    max gain and ROI on debit."""
    if not contracts:
        return None
    long_leg = contracts[0]                       # score-max
    short_pool = [c for c in contracts
                  if (c["strike"] > long_leg["strike"] if call
                      else c["strike"] < long_leg["strike"])]
    if not short_pool:
        return None
    tgt = 0.30
    short_leg = min(short_pool,
                    key=lambda c: abs(abs(c["delta"]) - tgt))
    debit = round(long_leg["mid"] - short_leg["mid"], 2)
    if debit <= 0.05:
        return None
    width = abs(short_leg["strike"] - long_leg["strike"])
    max_gain = round(width - debit, 2)
    return {"buy": long_leg["contract"], "buy_strike": long_leg["strike"],
            "buy_mid": long_leg["mid"], "buy_delta": long_leg["delta"],
            "sell": short_leg["contract"],
            "sell_strike": short_leg["strike"],
            "sell_mid": short_leg["mid"], "sell_delta": short_leg["delta"],
            "net_debit": debit, "capital": round(debit * 100),
            "max_gain": max_gain,
            "roi_max": round(max_gain / debit * 100)
            if debit > 0 else None,
            "vs_straight_premium": round(
                (1 - debit / long_leg["mid"]) * 100)
            if long_leg["mid"] else None}


async def leaps_screen(sym: str, beta: Optional[float] = None,
                       risk_free: float = RISK_FREE) -> dict[str, Any]:
    """Technicals + direction verdict + ranked LEAPS per expiry."""
    import yfinance as yf
    from app.market_data import MarketDataService
    from app.providers.financial_modeling_prep.client import (
        EnhancedFMPClient)

    sym = sym.upper().strip()
    svc = MarketDataService()
    bars = await svc.get_ohlcv(
        sym, start=date.today() - timedelta(days=560), interval="1d")
    if not bars or len(bars) < 60:
        return {"error": f"insufficient price history for {sym}"}
    tech = _technicals(bars)
    S = tech["price"]
    try:
        from app.signals.momentum_regime import refresh_symbol
        momentum = refresh_symbol(sym, tech, _macd_hist_prev(bars),
                                  bars)
    except Exception:
        momentum = None
    fmp = EnhancedFMPClient.from_settings()
    try:
        from app.signals.expectation_gap import compute_flywheel
        await asyncio.to_thread(compute_flywheel, fmp, sym, S, bars)
    except Exception as exc:
        logger.debug("flywheel %s failed: %s", sym, exc)
    fund = await asyncio.to_thread(_fundamentals, fmp, sym)
    from app.symbol_classification import get_cyclicality
    cyc = await asyncio.to_thread(get_cyclicality, fmp, sym)
    cyclical = cyc["cyclical"]
    verdict, cycle, reasons, actions = _direction(
        tech, fund, _macd_hist_prev(bars), cyclical)

    if beta is None:
        try:
            prof = fmp._make_request("/profile", {"symbol": sym})
            p = prof[0] if isinstance(prof, list) and prof else {}
            beta = p.get("beta")
        except Exception:
            beta = None

    def _chain():
        t = yf.Ticker(sym)
        exps = [e for e in (t.options or [])
                if (date.fromisoformat(e) - date.today()).days > MIN_DTE]
        return {e: t.option_chain(e) for e in exps}

    chains = await asyncio.to_thread(_chain)
    hv = tech.get("hv20") or tech.get("hv60")

    # payoff scenarios: revisit the 52w high (the user's 'it will see
    # highs again' thesis) plus fixed +30%/+60% upside legs. ROI is on
    # premium paid — the profit-per-dollar axis the score doesn't see.
    hi52 = max(b.high for b in bars[-252:]) if bars else S
    scenarios = {"to_52w_high": hi52 if hi52 > S else None,
                 "+30%": round(S * 1.30, 2),
                 "+50%": round(S * 1.50, 2),
                 "+60%": round(S * 1.60, 2),
                 "+100%": round(S * 2.00, 2)}

    def _roi(e, target, call):
        if not target or not e:
            return None
        intrinsic = (max(0.0, target - e["_K"]) if call
                     else max(0.0, e["_K"] - target))
        return round((intrinsic / e["mid"] - 1) * 100)

    def _ev(e, call):
        """(ev_roi%, p_itm%, p_profit%) at expiry under a lognormal
        terminal distribution with THESIS_DRIFT real drift and the
        contract's own IV. EV ROI is what a desk actually maximizes —
        a scenario ROI means nothing without its probability."""
        mid, iv = e["mid"], e.get("_iv") or 0
        if mid <= 0 or iv <= 0.001:
            return None, None, None
        T = e["_T"] / 365.0
        F = S * math.exp(THESIS_DRIFT * T)
        sq = iv * math.sqrt(T)
        K = e["_K"]
        d1 = (math.log(F / K) + 0.5 * iv * iv * T) / sq
        d2 = d1 - sq
        if call:
            epay = F * _N.cdf(d1) - K * _N.cdf(d2)
            be = K + mid
            p_itm = _N.cdf(d2)
            p_profit = (_N.cdf((math.log(F / be)
                                - 0.5 * iv * iv * T) / sq)
                        if be > 0 else None)
        else:
            epay = K * _N.cdf(-d2) - F * _N.cdf(-d1)
            be = K - mid
            p_itm = _N.cdf(-d2)
            p_profit = (_N.cdf(-(math.log(F / be)
                                 - 0.5 * iv * iv * T) / sq)
                        if be > 0 else None)
        return (round((epay / mid - 1) * 100), round(p_itm * 100),
                round(p_profit * 100) if p_profit is not None else None)

    out_exps = []
    for expiry, ch in chains.items():
        T = (date.fromisoformat(expiry) - date.today()).days
        calls, puts = [], []
        for _, row in ch.calls.iterrows():
            e = _enrich(row, S, T, risk_free, True,
                        CALL_DELTA_TARGET, hv)
            if e:
                calls.append(e)
        for _, row in ch.puts.iterrows():
            e = _enrich(row, S, T, risk_free, False,
                        PUT_DELTA_TARGET, hv)
            if e:
                puts.append(e)
        def _flip(e, move: float, hold_days: int = 60):
            """Honest 'sell in ~2 months' ROI: BS reprice at the moved
            spot with hold_days of theta already bled, vs premium paid.
            The intrinsic-at-expiry columns answer 'hold to expiry';
            these answer the actual flip strategy. IV held at the
            contract's own level (IV-crush is a separate gate)."""
            T_left = e["_T"] - hold_days
            if T_left <= 0 or not e.get("_iv"):
                return None
            v = _bs_value(S * (1 + move), e["_K"], T_left / 365,
                          risk_free, e["_iv"], True)
            return round((v / e["mid"] - 1) * 100) if v else None

        for e in calls:
            e["roi_hi52"] = _roi(e, scenarios["to_52w_high"], True)
            e["roi_30"] = _roi(e, scenarios["+30%"], True)
            e["roi_50"] = _roi(e, scenarios["+50%"], True)
            e["roi_60"] = _roi(e, scenarios["+60%"], True)
            e["roi_100"] = _roi(e, scenarios["+100%"], True)
            e["roi_flip15"] = _flip(e, 0.15)
            e["roi_flip30"] = _flip(e, 0.30)
            e["roi_dn10"] = _flip(e, -0.10)   # the honest downside
            e["ev_roi"], e["p_itm"], e["p_profit"] = _ev(e, True)
            for k in ("_delta_raw", "_K", "_T"):
                e.pop(k)
        for e in puts:
            e["ev_roi"], e["p_itm"], e["p_profit"] = _ev(e, False)
            for k in ("_delta_raw", "_K", "_T"):
                e.pop(k)
        calls.sort(key=lambda x: -x["score"])
        puts.sort(key=lambda x: -x["score"])
        # three objectives, three picks — a desk would show the
        # frontier, not one number:
        #   safe     — score-max: δ≈0.72, low extrinsic (stock
        #              replacement: expert consensus δ0.70-0.85, ≥70%
        #              intrinsic)
        #   balanced — max EV ROI under the +25%/yr drift thesis among
        #              strikes with ≥40% chance of profit and ≤65%
        #              extrinsic (the leverage sweet spot, not a rental)
        #   growth   — max EV ROI among strikes with ≥45% modeled
        #              chance of finishing ITM (unconstrained EV argmax
        #              lands on δ0.1-0.4 lottery tickets)
        ev_cands = [c for c in calls if c.get("ev_roi") is not None]

        def _best(pool):
            return max(pool, key=lambda c: c["ev_roi"]) if pool \
                else None

        balanced_pool = [c for c in ev_cands
                         if (c.get("p_profit") or 0) >= 40
                         and c["extrinsic_pct"] <= 65]
        if not balanced_pool:
            # relax extrinsic, never probability — if nothing clears
            # 40% P(profit), the honest balanced pick is "none exists"
            balanced_pool = [c for c in ev_cands
                             if (c.get("p_profit") or 0) >= 40]
        growth_pool = [c for c in ev_cands if (c.get("p_itm") or 0) >= 45] \
            or ev_cands
        # burst — the user's goal: dip-buy a quality name, encash +50%/
        # +100% on capital into a news spike. Research consensus for
        # that job is slightly-ITM δ0.55-0.75: high directional capture,
        # moderate extrinsic (less IV-crush exposed than pure ATM),
        # gamma still accelerating. Rank by roi_50 (the actual exit
        # target), floor p_profit ≥30.
        burst_pool = [c for c in ev_cands
                      if 0.55 <= c["delta"] <= 0.75
                      and (c.get("p_profit") or 0) >= 30]
        burst = (max(burst_pool, key=lambda c: c.get("roi_50") or 0)
                 if burst_pool else None)
        # flip — the user's actual horizon: profit in 1-2 months, can
        # hold longer on the long DTE. Rank δ0.55-0.85 (swing band per
        # desk consensus: enough delta stability to survive a dip,
        # enough gearing to matter) by the BS-repriced +15%-in-60d
        # scenario — NOT intrinsic-at-expiry, which misprices the
        # real exit.
        flip_pool = [c for c in ev_cands
                     if 0.55 <= c["delta"] <= 0.85
                     and c.get("roi_flip15") is not None]
        flip = (max(flip_pool, key=lambda c: c["roi_flip15"])
                if flip_pool else None)
        # atm — nearest strike to spot, pure at-the-money. The score
        # rubric ranks it low (δ~0.50, ~100% extrinsic — opposite of
        # stock-replacement), so surface it as its own pick instead of
        # letting it fall off the table.
        atm = (min(calls, key=lambda c: abs(c["strike"] - S))
               if calls else None)
        # every named pick must appear in the table — a recommended
        # contract that's invisible in the rows is a UI lie. Score
        # order stays the default view; picks get appended if they
        # didn't crack the top-6.
        table_calls = calls[:6]
        for pick in (atm, flip, burst,
                     _best(balanced_pool), _best(growth_pool)):
            if pick and all(p["contract"] != pick["contract"]
                            for p in table_calls):
                table_calls.append(pick)
        # empty table with a non-empty chain = dead feed (zero bids or
        # sub-25 OI everywhere) — say so; silence reads like a bug
        chain_note = None
        if not table_calls and len(ch.calls):
            chain_note = (f"{len(ch.calls)} calls scanned, none liquid "
                          "(dead bids or OI<25) — likely a stale feed; "
                          "retry in market hours")
        out_exps.append({
            "expiry": expiry, "dte": T,
            "calls": table_calls, "puts": puts[:4],
            "chain_note": chain_note,
            "safe_pick_call": calls[0] if calls else None,
            "atm_pick_call": atm,
            "flip_pick_call": flip,
            "balanced_pick_call": _best(balanced_pool),
            "growth_pick_call": _best(growth_pool),
            "burst_pick_call": burst,
            "_calls_all": calls, "_puts_all": puts,
            "n_calls_scanned": len(ch.calls),
            "n_puts_scanned": len(ch.puts)})

    # --- vol regime + spread structures ----------------------------------
    # IV vs realized vol decides whether you BUY options or spread them:
    # elevated IV → debit spreads (cut cost, shrink vega); cheap IV →
    # straight contracts. The hedge playbook's IVR>50 rule, expressed
    # via IV/HV since we have no IV-history endpoint.
    atm_ivs = [c["_iv"] for ex in out_exps for c in ex["_calls_all"]
               if c.get("_iv") and 0.8 * S < c["strike"] < 1.2 * S]
    med_iv = sorted(atm_ivs)[len(atm_ivs) // 2] if atm_ivs else None
    iv_elevated = bool(hv and med_iv and med_iv > hv * 1.15)
    # --- persist the daily IV print → true IV rank accrues --------------
    # one row per symbol/day; the rank is today's IV vs its own 1y
    # history. Thin history → fall back to the iv_hv ratio flag.
    iv_rank = None
    if med_iv and hv:
        try:
            from app.database import db
            db.execute_update(
                "INSERT INTO iv_snapshots (symbol, as_of, atm_iv, hv20,"
                " iv_hv) VALUES (:s, CURRENT_DATE, :iv, :hv, :r)"
                " ON CONFLICT (symbol, as_of) DO UPDATE SET"
                " atm_iv=EXCLUDED.atm_iv, hv20=EXCLUDED.hv20,"
                " iv_hv=EXCLUDED.iv_hv",
                {"s": sym, "iv": round(med_iv, 5), "hv": round(hv, 5),
                 "r": round(med_iv / hv, 3)})
            hist = db.execute_query(
                "SELECT count(*) n, count(*) FILTER (WHERE atm_iv < :iv)"
                "  AS below FROM iv_snapshots WHERE symbol = :s"
                "  AND as_of > CURRENT_DATE - 365",
                {"s": sym, "iv": med_iv})
            if hist and (hist[0]["n"] or 0) >= 20:
                iv_rank = round(100 * hist[0]["below"] / hist[0]["n"])
        except Exception:
            pass
    vol_regime = ("elevated — IV {0:.0f}% vs HV {1:.0f}%; prefer DEBIT "
                  "SPREADS / premium-selling over straight contracts"
                  .format(med_iv * 100, hv * 100) if iv_elevated else
                  ("normal — IV {0:.0f}% vs HV {1:.0f}%; straight "
                   "contracts are fairly priced"
                   .format(med_iv * 100, hv * 100)
                   if med_iv and hv else "unknown (no IV/HV)"))
    if iv_rank is not None:
        vol_regime += f" · IV rank {iv_rank} (vs own 1y history)"

    # IV-crush timing: the burst pick is ~100% extrinsic — buying it
    # into a near-term print on elevated IV is how you lose money on a
    # green day. Warn explicitly; post-print or quiet-window entries
    # skip the tax.
    try:
        _ne = fund.get("next_earnings")
        if _ne:
            _d_out = (date.fromisoformat(str(_ne)) - date.today()).days
            if 0 <= _d_out <= 21 and iv_elevated:
                actions.append(
                    f"⚠️ earnings in {_d_out}d with IV elevated — "
                    "extrinsic-heavy picks (esp. burst) face IV crush "
                    "even on a good print: enter AFTER earnings, in a "
                    "quiet window, or use the debit spread instead")
            elif 0 <= _d_out <= 21:
                actions.append(
                    f"earnings in {_d_out}d — a binary event inside "
                    "the hold window; size accordingly")
    except Exception:
        pass

    # AI capex-cycle exposure — a long-dated call on new-build equipment
    # beta during an ACTIVE/CONTRACTION regime fights the allocation
    # shift even if the company is fine; warn, don't veto
    try:
        from app.signals import capex_cycle as _cx
        _cxp = _cx.read() or {}
        _cxfl = _cx.symbol_flag(sym, _cxp)
        if _cxfl == "capex-beta":
            actions.append(
                f"🏗 CAPEX-BETA — capex engine {_cxp.get('score')}/100 "
                f"{_cxp.get('band')}: new-build equipment exposure "
                "faces allocation headwind; prefer shorter holds / "
                "smaller size, or the operator-rotation names")
        elif _cxfl == "capex-watch":
            actions.append(
                f"capex watch — engine {_cxp.get('score')}/100 early-"
                "warning; monitor hyperscaler prints")
        elif _cxfl == "rotation-candidate":
            actions.append(
                "capex rotation candidate — lifecycle/inference "
                "beneficiary as new-build spend normalizes")
    except Exception:
        pass

    for ex in out_exps:
        calls, puts = ex.pop("_calls_all"), ex.pop("_puts_all")
        for c in calls + puts:
            c.pop("_iv", None)
        ex["call_spread"] = _spread(calls, True)
        ex["put_spread"] = _spread(puts, False)

    return {
        "symbol": sym, "spot": round(S, 2), "beta": beta,
        "risk_free": risk_free, "verdict": verdict,
        "momentum": momentum,
        "cycle_stage": cycle, "cyclical": cyclical,
        "cyclicality": cyc,
        "fundamentals": fund, "vol_regime": vol_regime,
        "iv_elevated": iv_elevated, "iv_rank": iv_rank,
        "reasons": reasons, "actions": actions,
        "technicals": tech, "hv20": hv, "expiries": out_exps,
        "as_of": datetime.now().isoformat(timespec="seconds"),
    }


# per-stage "why the other side is blocked" — single deterministic
# map so the scan can tell the user WHY a CALL or PUT is off the table,
# not just what the verdict is
_STAGE_BLOCKS = {
    "pullback_in_uptrend": "PUT✗ inside an uptrend — the wash IS "
                           "the call setup, not a short",
    "ath_extension": "CALL✗ buying calls at ATH extension = buying "
                     "the top of the range",
    "extended": "CALL✗ extended above band — poor call entry",
    "stale_stall": "PUT✗ momentum crack is stale — the put window "
                   "was the crack day, wait for next extension",
    "climax_structural": "PUT✗ structural name, fundamentals intact — "
                         "overextension alone isn't a short thesis",
    "climax": "CALL/PUT✗ euphoria zone — trim existing calls only",
    "extended_no_stall": "PUT✗ no stall evidence yet — extended ≠ "
                         "reversal; wait for the crack",
    "falling_knife": "CALL✗ still collapsing (hist<0 below BB mid); "
                     "PUT✗ too late — the crash already happened",
    "wash_not_stabilized": "CALL✗ MACD hist still falling — wash "
                           "isn't done; dead-cat filter",
    "downtrend": "CALL✗ trend broken — 'on sale' vs 'broken' can't "
                 "be told apart on tape; PUT✗ already crashed — late",
    "mid_range": "no edge — mid-range chop, wait for the cycle",
    "disqualified": "fundamentals gate failed — neither side is "
                    "sanctioned on a weak name",
    "no_data": "insufficient price history",
    "unknown": "insufficient technicals"}


async def tracked_phase_scan(concurrency: int = 6) -> dict:
    """Phase sweep over every tracked symbol — portfolio positions,
    watchlist, RB/5x board members — WITHOUT option chains.

    Built for speed: ONE batched yf.download for all bars, ONE DB join
    for flywheel/cyclicality/earnings context, and _fundamentals only
    for symbols with no flywheel row yet. Verdict path is the same
    _technicals + _direction as the single-symbol screen."""
    from types import SimpleNamespace
    from app.database import db
    from app.providers.financial_modeling_prep.client import (
        EnhancedFMPClient)

    rows = db.execute_query(
        """
        WITH tracked AS (
            SELECT symbol, 'RB' AS board FROM rule_breaker_members
            UNION SELECT symbol, '5x' FROM smallcap_members
            UNION SELECT s.symbol, 'portfolio'
                FROM stocks s JOIN portfolio_positions pp
                    ON pp.stock_id = s.id AND pp.quantity > 0
            UNION SELECT s.symbol, 'watchlist'
                FROM stocks s JOIN watchlist_stocks ws
                    ON ws.stock_id = s.id
        )
        SELECT symbol, string_agg(DISTINCT board, '+' ORDER BY board)
               AS boards FROM tracked GROUP BY symbol
        """)
    syms = [r["symbol"] for r in rows]
    boards = {r["symbol"]: r["boards"] for r in rows}
    if not syms:
        return {"calls": [], "puts": [], "watch": [], "skipped": [],
                "counts": {}}

    # fundamentals context for the whole universe in one query —
    # flywheel metrics approximate the screen's gate; symbols with no
    # row fall through to a live _fundamentals fetch.
    ctx = {r["symbol"]: r for r in db.execute_query(
        """
        SELECT s.symbol, s.cyclical, s.next_earnings_date,
               f.rev_growth, f.gm_now, f.gm_slope, f.rev_accel,
               f.gap_score, f.beat_streak, f.est_revision_pct
        FROM stocks s
        LEFT JOIN symbol_flywheel f ON f.symbol = s.symbol
        WHERE s.symbol = ANY(:syms)
        """, {"syms": syms})}

    # book memory — symbols whose last thesis failed sit in cooldown:
    # the scan still reports the signal but flags it, so a bounce that
    # merely *looks* like accumulation doesn't trigger re-entry at the
    # same level that just stopped us out
    cooldowns = {}
    try:
        for r in db.execute_query(
                """SELECT DISTINCT ON (stock_symbol) stock_symbol,
                          closed_at, close_reason, mark_spot
                   FROM leaps_positions
                   WHERE status='CLOSED'
                     AND close_reason IN ('thesis_broken',
                                          'invalidated', 'time_stop')
                     AND closed_at > now() - interval '28 days'
                   ORDER BY stock_symbol, closed_at DESC"""):
            cooldowns[r["stock_symbol"]] = r
    except Exception:
        pass

    def _bars_all():
        import yfinance as yf
        return yf.download(syms + ["SPY", "^VIX"], period="2y",
                           interval="1d", group_by="ticker",
                           threads=True, progress=False,
                           auto_adjust=True)

    df = await asyncio.to_thread(_bars_all)

    # market regime — the CANONICAL posture read (posture.py over the
    # journaled regime card): the same permission layer the daily calls,
    # puts and capital planner obey. SPY/VIX stay as raw context; the
    # tape verdict + note come from one place so this page can't
    # contradict the Daily Board. A leap call is a new long — it obeys
    # new_longs; a leap put obeys shorts.
    market = {}
    try:
        spy_c = df["SPY"]["Close"].dropna()
        spy_s200 = spy_c.rolling(200).mean().iloc[-1]
        spy_px = spy_c.iloc[-1]
        vix = float(df["^VIX"]["Close"].dropna().iloc[-1])
        from app.signals import posture as _pos
        pos = _pos.current()
        market = {"spy": round(float(spy_px), 1),
                  "spy_vs_sma200": round(
                      float(spy_px / spy_s200 - 1) * 100, 1)
                  if spy_s200 == spy_s200 else None,
                  "vix": round(vix, 1),
                  "tape": pos.get("posture"),
                  "tape_rule": pos.get("matched"),
                  "new_longs": pos.get("new_longs"),
                  "shorts": pos.get("shorts"),
                  "posture_as_of": pos.get("regime_as_of"),
                  "note": pos.get("note")}
    except Exception:
        market = {}

    def _bars_for(sym: str):
        try:
            sub = df[sym].dropna(subset=["Close"])
        except (KeyError, TypeError):
            return []
        return [SimpleNamespace(
            timestamp=i.to_pydatetime(), date=i.date(),
            open=float(r.Open), high=float(r.High), low=float(r.Low),
            close=float(r.Close), adj_close=None,
            volume=float(r.Volume) if pd.notna(r.Volume) else 0)
            for i, r in sub.iterrows()]

    fmp = EnhancedFMPClient.from_settings()
    sem = asyncio.Semaphore(concurrency)

    async def _one(sym: str):
        async with sem:
            try:
                bars = _bars_for(sym)
                if len(bars) < 60:
                    return {"symbol": sym, "boards": boards[sym],
                            "verdict": "WAIT", "stage": "no_data"}
                tech = _technicals(bars)
                c = ctx.get(sym) or {}
                if c.get("rev_growth") is not None:
                    # flywheel approximation of the _fundamentals gate —
                    # same thresholds, already-computed metrics
                    det = []
                    if (c.get("rev_growth") or 0) < 0:
                        det.append("YoY revenue growth negative")
                    if (c.get("gm_slope") or 0) < -0.03:
                        det.append("gross margin compressing")
                    if (c.get("rev_accel") or 0) < 0 \
                            and (c.get("rev_growth") or 0) < 0.15:
                        det.append("growth decelerating")
                    fund = {"solid": bool(
                                (c.get("rev_growth") or 0) >= 0.15
                                and (c.get("gm_now") or 0) >= 0.40),
                            "rev_growth": c.get("rev_growth"),
                            "gross_margin": c.get("gm_now"),
                            "deteriorating": bool(det),
                            "deterioration": det,
                            "gap_score": c.get("gap_score"),
                            "beat_streak": c.get("beat_streak"),
                            "engine_membership": [boards[sym]],
                            "next_earnings": c.get("next_earnings_date")}
                else:
                    fund = await asyncio.to_thread(
                        _fundamentals, fmp, sym)
                hp = _macd_hist_prev(bars)
                # canonical momentum flag — the scan already computed
                # bars+tech, so persisting the regime is a free write
                # that every other surface (boards, book) reads
                try:
                    from app.signals.momentum_regime import \
                        refresh_symbol
                    mom = refresh_symbol(sym, tech, hp, bars)
                except Exception:
                    mom = None
                verdict, stage, reasons, _ = _direction(
                    tech, fund, hp,
                    bool(c.get("cyclical")))
                return {"symbol": sym, "boards": boards[sym],
                        "momentum": mom,
                        "verdict": verdict, "stage": stage,
                        "spot": tech.get("price"),
                        "rsi": tech.get("rsi14"),
                        "pct_b": (tech.get("bollinger") or {})
                        .get("pct_b"),
                        "vs_sma200": tech.get("vs_sma200"),
                        "dd52w": tech.get("dd52w"),
                        "cyclical": bool(c.get("cyclical")),
                        "solid": fund.get("solid"),
                        "gap_score": fund.get("gap_score"),
                        "beat_streak": fund.get("beat_streak"),
                        "next_earnings": fund.get("next_earnings"),
                        "cooldown": sym in cooldowns,
                        "cooldown_until": (
                            str(cooldowns[sym]["closed_at"].date())
                            if sym in cooldowns and cooldowns[sym]
                            .get("closed_at") else None),
                        "cooldown_reason": cooldowns[sym]
                        .get("close_reason") if sym in cooldowns
                        else None,
                        "blocks": _STAGE_BLOCKS.get(stage),
                        "why": reasons[-1] if reasons else None}
            except Exception as exc:
                return {"symbol": sym, "boards": boards[sym],
                        "verdict": "ERROR", "stage": str(exc)[:80]}

    results = await asyncio.gather(*(_one(s) for s in syms))
    out = {"calls": [], "puts": [], "watch": [], "skipped": [],
           "cooling": [], "market": market,
           "as_of": datetime.now().isoformat(timespec="seconds")}
    for r in results:
        if r.get("cooldown") and r["verdict"] in ("CALL", "PUT"):
            out["cooling"].append(r)      # signal suppressed by memory
        elif r["verdict"] == "CALL":
            out["calls"].append(r)
        elif r["verdict"] == "PUT":
            out["puts"].append(r)
        elif r["verdict"] in ("WAIT", "ERROR"):
            out["watch"].append(r)
        else:
            out["skipped"].append(r)
    out["counts"] = {k: len(v) for k, v in out.items()
                     if isinstance(v, list)}
    return out
