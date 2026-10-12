"""Canonical momentum-regime flag — ONE classifier, ONE stored state
per symbol, read by every surface (Options scan/verdict, Market Movers
boards, 5x Scout, the LEAPS book).

Why this exists: three places were independently reconstructing the
same tape picture (_direction, the backtest _phase, per-page tech
reads). A persisted flag makes the state visible at the symbol level
("what regime is NVDA in right now?") instead of only inside a screen.

Deterministic, stateless per-bar — sequence state (cooldowns, ladders)
lives in leaps_positions, NOT here. Written by:
  - tracked_phase_scan (already pulls bars for ~400 symbols — free)
  - compute_flywheel (per-symbol whenever a symbol is refreshed)
  - refresh_momentum_all() for board-wide/eval-tail batch updates

States (precedence order top→bottom — first match wins):
  climax        rsi≥75 or %B>0.95            euphoria — trim, no entries
  knife         washed & hist<0 & %B<0.35    still collapsing — wait
  capitulation  not uptrend & (rsi≤30 or %B≤0.05)  deep wash, no trend
  breakout      fresh 60d-high close & hist>0      momentum igniting
  breakdown     fresh 60d-low close & hist<0       momentum collapsing
  rolling_over  extended-ish & fresh hist<0 crack  first exhaustion
  pullback      uptrend & washed & stabilizing     THE dip-buy zone
  basing        tight 20d range & |vs50|<4%        coiling — wait
  downtrend     px<s200                            trend broken
  recovery      px>s200 but s50<s200               early turn repair
  uptrend       px>s200 & s50>s200                 healthy trend
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

import pandas as pd

logger = logging.getLogger(__name__)

# state → (emoji, one-line user guidance). The "actions" language
# mirrors the options verdicts so every surface speaks the same words.
STATES = {
    "climax":       ("🔥", "euphoria — trim calls, enter nothing new"),
    "breakout":     ("🚀", "momentum igniting — calls OK if not "
                           "chasing >5% above the break"),
    "uptrend":      ("📈", "healthy trend — hold calls; new entries "
                           "only on pullbacks"),
    "recovery":     ("🌱", "reclaimed 200dma — early turn; small "
                           "starter calls OK"),
    "basing":       ("😴", "coiling in a tight range — wait for the "
                           "break to pick a side"),
    "pullback":     ("🟢", "washed inside uptrend — THE call-buy zone"),
    "rolling_over": ("🟠", "extended + fresh momentum crack — puts "
                           "eligible (cyclicals) / trim calls"),
    "knife":        ("🔪", "still collapsing — no calls; puts are "
                           "late. Let it base"),
    "capitulation": ("💥", "deep wash with trend broken — watch for "
                           "stabilization before calls"),
    "breakdown":    ("⬇️", "fresh 60d low — momentum collapsing; "
                           "puts are late, calls forbidden"),
    "downtrend":    ("📉", "below 200dma — 'on sale' vs 'broken' is "
                           "unknowable on tape; both sides blocked"),
    "unknown":      ("⚪", "insufficient data"),
}


def classify(tech: dict, hist_prev: Optional[float],
             bars=None) -> str:
    """tech = _technicals(bars) output; hist_prev = _macd_hist_prev.
    bars optional — enables fresh-high/low detection (breakout/
    breakdown) when provided."""
    px, s50, s200 = tech.get("price"), tech.get("sma50"), \
        tech.get("sma200")
    rsi, hist = tech.get("rsi14"), tech.get("macd_hist")
    pct_b = (tech.get("bollinger") or {}).get("pct_b")
    dd, vs50 = tech.get("dd52w"), tech.get("vs_sma50")
    if not all([px, s50, s200]) or rsi is None or hist is None:
        return "unknown"

    up = px > s200 and s50 > s200
    extended = (pct_b is not None and pct_b > 0.9) or rsi >= 68 \
        or (vs50 is not None and vs50 > 0.12)
    washed = (dd is not None and dd <= -0.15) or rsi <= 40 \
        or (pct_b is not None and pct_b < 0.25)
    knife = hist < 0 and (pct_b is not None and pct_b < 0.35)
    fresh_stall = hist < 0 and hist_prev is not None \
        and hist_prev >= 0
    stabilizing = hist_prev is None or hist > hist_prev

    # range compression → basing (20d high-low span < 12% of price)
    tight = False
    if bars is not None and len(bars) >= 20:
        rng = (max(b.high for b in bars[-20:])
               - min(b.low for b in bars[-20:])) / px
        tight = rng < 0.12 and abs(vs50 or 0) < 0.04

    # fresh 60d extreme closes → breakout / breakdown
    hi60 = lo60 = None
    if bars is not None and len(bars) >= 61:
        hi60 = max(b.high for b in bars[-61:-1])
        lo60 = min(b.low for b in bars[-61:-1])

    # --- precedence: violence & climax first, extremes before trend ---
    if rsi >= 75 or (pct_b is not None and pct_b > 0.95):
        return "climax"
    if hi60 is not None and px >= hi60 and hist > 0:
        return "breakout"
    if lo60 is not None and px <= lo60 and hist < 0:
        return "breakdown"
    if up and washed and knife:
        return "knife"
    if not up and (rsi <= 30 or (pct_b is not None and pct_b <= 0.05)):
        return "capitulation"
    if up and washed and not stabilizing and (
            rsi <= 38 or (pct_b is not None and pct_b <= 0.2)
            or (vs50 is not None and vs50 <= -0.08)):
        return "knife"                      # violence signature —
                                            # below the 50dma/deep
                                            # oversold, still bleeding.
                                            # a -15% dip on a high-vol
                                            # name with RSI mid-band is
                                            # a pullback that hasn't
                                            # stabilized, not a knife
    if up and washed:
        return "pullback"
    if extended and fresh_stall:
        return "rolling_over"
    if not up and px < s200 and s50 < s200:
        return "downtrend"
    if not up:
        return "capitulation" if washed else "downtrend"
    if tight:
        return "basing"
    if s50 < s200:
        return "recovery"
    return "uptrend"


def _rsi_simple(closes: list[float], n: int = 14) -> Optional[float]:
    """Lightweight RSI over a close slice — direction accuracy only."""
    if len(closes) < n + 1:
        return None
    diffs = [b - a for a, b in zip(closes[-n - 1:-1], closes[-n:])]
    ag = sum(d for d in diffs if d > 0) / n
    al = sum(-d for d in diffs if d < 0) / n
    if al == 0:
        return 100.0
    return 100 - 100 / (1 + ag / al)


def dip_health(tech: dict, hist_prev: Optional[float],
               bars=None) -> Optional[dict]:
    """Direction-of-travel INSIDE a dip — the 'is this pullback turning
    up or becoming a knife' read. Five deterministic legs:

      hist_dir    MACD histogram rising = momentum healing first
      low_streak  higher-lows minus lower-lows over the last 5 bars —
                  a healing dip stops printing fresh lows
      vs50_drift  distance to the 50dma now vs 3 bars ago — shrinking
                  = the dip is being bought back toward the trend line
      rsi_dir     RSI hooking up vs still falling
      vol_dip     down-day volume vs 20d avg — <1 = sellers exhausting

    → dip_phase: turning_up (≥3 legs) | stabilizing (2) | still_falling
    """
    if bars is None or len(bars) < 60:
        return None
    h: dict[str, Any] = {}
    hist = tech.get("macd_hist")
    h["hist_dir"] = (round(hist - hist_prev, 4)
                     if hist is not None and hist_prev is not None
                     else None)
    closes = [b.close for b in bars]
    lows = [b.low for b in bars[-6:]]
    h["low_streak"] = sum(1 for a, b in zip(lows, lows[1:]) if b > a) \
        - sum(1 for a, b in zip(lows, lows[1:]) if b < a)
    s50_now = sum(closes[-50:]) / 50
    s50_then = sum(closes[-53:-3]) / 50
    h["vs50_drift"] = round(closes[-1] / s50_now
                            - closes[-4] / s50_then, 4)
    r_now, r_prev = _rsi_simple(closes), _rsi_simple(closes[:-1])
    h["rsi_dir"] = (round(r_now - r_prev, 1)
                    if r_now is not None and r_prev is not None
                    else None)
    dn = [b.volume for b in bars[-10:] if b.close < b.open]
    al = [b.volume for b in bars[-20:]]
    h["vol_dip"] = (round((sum(dn) / len(dn))
                          / (sum(al) / len(al)), 2)
                    if dn and al and sum(al) else None)
    pts = sum(1 for k, cond in (
        ("hist_dir", (h["hist_dir"] or 0) > 0),
        ("low_streak", h["low_streak"] > 0),
        ("vs50_drift", (h["vs50_drift"] or 0) > 0),
        ("rsi_dir", (h["rsi_dir"] or 0) > 0),
        ("vol_dip", h["vol_dip"] is not None
         and h["vol_dip"] < 1.0)) if cond)
    h["dip_health"] = pts
    h["dip_phase"] = ("turning_up" if pts >= 3 else
                      "stabilizing" if pts == 2 else "still_falling")
    return h


def detail(tech: dict) -> dict:
    """The evidence pack stored beside the flag — boards/UI show the
    numbers that produced it, never a bare label."""
    bb = tech.get("bollinger") or {}
    return {"rsi": tech.get("rsi14"), "pct_b": bb.get("pct_b"),
            "hist": tech.get("macd_hist"),
            "vs_sma200": tech.get("vs_sma200"),
            "vs_sma50": tech.get("vs_sma50"),
            "dd52w": tech.get("dd52w"),
            "hv20": tech.get("hv20"), "atr_pct": tech.get("atr_pct")}


def write_state(sym: str, state: str, tech: dict, dip: dict = None):
    from app.database import db
    import json
    d = detail(tech)
    if dip:
        d.update(dip)
    db.execute_update(
        "UPDATE stocks SET momentum_state=:s, "
        "momentum_detail=CAST(:d AS jsonb), "
        "momentum_updated_at=now() WHERE symbol=:y",
        {"s": state, "d": json.dumps(d), "y": sym.upper()})
    db.execute_update(
        "INSERT INTO momentum_state_log (symbol, as_of, state, detail) "
        "VALUES (:y, CURRENT_DATE, :s, CAST(:d AS jsonb)) "
        "ON CONFLICT (symbol, as_of) DO UPDATE SET "
        "state=EXCLUDED.state, detail=EXCLUDED.detail",
        {"s": state, "d": json.dumps(d), "y": sym.upper()})


def refresh_symbol(sym: str, tech: dict, hist_prev,
                   bars=None) -> str:
    """Classify + persist. Called from any path that already computed
    bars/tech — free writes, zero extra fetches."""
    try:
        state = classify(tech, hist_prev, bars)
        dip = dip_health(tech, hist_prev, bars)
        # swing-point structure — higher-low detection only matters on
        # pullback-ish states; run it whenever bars are present so the
        # 'broken' phase can flag knives too
        if bars:
            try:
                from app.signals.swing_lows import higher_low_setup
                s50p = None
                closes = [b.close for b in bars]
                if len(closes) >= 55:
                    s50p = sum(closes[-55:-5]) / 50
                sw = higher_low_setup(bars, sma50=tech.get("sma50"),
                                      sma50_prev=s50p)
                if sw:
                    dip = {**(dip or {}), "swing": sw}
            except Exception:
                pass
        write_state(sym, state, tech, dip)
        return state
    except Exception as exc:
        logger.debug("momentum write %s failed: %s", sym, exc)
        return "unknown"


def refresh_momentum_all() -> dict:
    """Board-wide batch: ONE yf.download over every tracked symbol
    (RB + 5x + portfolio + watchlist), classify each, write stocks.
    ~75-90s — the daily scheduled path."""
    from types import SimpleNamespace
    from app.database import db
    from app.options.leaps import _technicals, _macd_hist_prev

    syms = [r["symbol"] for r in db.execute_query(
        """WITH t AS (
            SELECT symbol FROM rule_breaker_members
            UNION SELECT symbol FROM smallcap_members
            UNION SELECT s.symbol FROM stocks s
                JOIN portfolio_positions pp
                    ON pp.stock_id = s.id AND pp.quantity > 0
            UNION SELECT s.symbol FROM stocks s
                JOIN watchlist_stocks ws ON ws.stock_id = s.id)
           SELECT symbol FROM t""")]
    if not syms:
        return {"refreshed": 0}
    # ONE batched fetch, canonical store — every other consumer reads
    # daily_bars via market_data.bars.load() instead of re-downloading.
    # Sector/theme ETFs ride along so rotation + dip-character reads
    # stay stored-data (they're not 'stocks', so skip classification).
    from app.market_data import bars as bars_mod
    from app.market_regime.rotation import SECTOR_NAMES, THEME_ETFS
    etf_syms = [s for s in (*SECTOR_NAMES, *THEME_ETFS, "^VIX")
                if s not in syms]
    books = bars_mod.refresh(syms + etf_syms, period="2y")
    counts: dict[str, int] = {}
    for s in syms:
        try:
            bars = books.get(s) or []
            if len(bars) < 60:
                continue
            tech = _technicals(bars)
            st = refresh_symbol(s, tech, _macd_hist_prev(bars), bars)
            counts[st] = counts.get(st, 0) + 1
        except Exception as exc:
            logger.debug("momentum %s: %s", s, exc)
    # --- context layers over the same bars — zero extra fetches -------
    extra = {}
    try:                                        # RS percentile ranking
        from app.signals import relative_strength as _rs
        rs = _rs.compute_universe_rs(books)
        extra["rs_written"] = _rs.merge_into_momentum_detail(rs)
    except Exception as exc:
        logger.warning("rs pass failed: %s", exc)
    try:                                        # universe internals
        from app.signals import breadth as _br
        extra["breadth"] = _br.universe_internals()
    except Exception as exc:
        logger.debug("breadth pass failed: %s", exc)
    try:                                        # book beta/concentration
        from app.signals import book_risk as _bk
        extra["book"] = _bk.compute_book_risk()
    except Exception as exc:
        logger.debug("book risk pass failed: %s", exc)
    try:                                        # defensive flows + headlines
        from app.signals import geo_context as _geo
        extra["geo"] = _geo.refresh()
    except Exception as exc:
        logger.debug("geo context pass failed: %s", exc)
    try:                                        # AI capex-cycle engine
        from app.signals import capex_cycle as _cx
        extra["capex"] = _cx.refresh()
    except Exception as exc:
        logger.debug("capex cycle pass failed: %s", exc)
    try:                                        # lean regime snapshot —
        extra["regime_snap"] = _regime_snapshot(books, extra)  # version
    except Exception as exc:                    # the read even when the
        logger.debug("regime snapshot: %s", exc) # page isn't opened
    try:                                        # crash alpha — version
        from app.options import crash_alpha as _ca
        extra["alpha_snap"] = _ca.snapshot()    # PUT/CAP scores daily
    except Exception as exc:
        logger.debug("crash-alpha snapshot: %s", exc)
    try:                                        # rotation events — did
        from app.market_regime import rotation_backtest as _rb
        extra["rotation_events"] = _rb.journal_today()  # a theme flip
    except Exception as exc:                    # fire today?
        logger.debug("rotation journal: %s", exc)
    return {"refreshed": sum(counts.values()), "states": counts,
            **extra,
            "at": datetime.now().isoformat(timespec="seconds")}


def label(state: Optional[str]) -> str:
    ic, _ = STATES.get(state or "unknown", STATES["unknown"])
    return f"{ic} {state or 'unknown'}"


def _regime_snapshot(books: dict, extra: dict) -> Optional[dict]:
    """Version the day's regime read even when the board page isn't
    opened — forward probs + dip character + allocation, journaled to
    regime_snapshots. Reuses the stored context the job just computed."""
    from app.database import db
    from app.market_regime.forward import forward_probs
    from app.market_regime.dip_character import classify as _dip
    from app.market_regime.allocation import plan as _alloc
    from app.signals.board_tracking import snapshot_regime
    from app.signals import geo_context as _geo, breadth as _br
    from app.market_data import bars as bars_mod

    spy = books.get("SPY") or []
    if len(spy) < 200:
        return None
    px = spy[-1].close
    vs200 = px / (sum(b.close for b in spy[-200:]) / 200) - 1
    vs200 = round(vs200, 4)
    s5 = round(px / spy[-6].close - 1, 4) if len(spy) > 6 else None

    # VIX — the daily fetch doesn't carry it; pull one bar cheaply
    vix, vix_rising = None, False
    try:
        vb = bars_mod.load(["^VIX"], days=10).get("^VIX") or []
        if vb:
            vix = vb[-1].close
            vix_rising = len(vb) > 1 and vix > vb[-2].close * 1.05
    except Exception:
        pass

    # transition score — the stored bullish-transition snapshot
    rd = {}
    try:
        ts = db.execute_query(
            "SELECT score, delta_5d FROM market_transition_snapshots"
            " ORDER BY as_of DESC LIMIT 1")
        if ts:
            rd = {"bullish_transition_score": float(ts[0]["score"]),
                  "transition_delta_5d": float(ts[0]["delta_5d"] or 0)}
    except Exception:
        pass

    geo = extra.get("geo") or _geo.read()
    breadth = extra.get("breadth") or _br.read()
    forward = forward_probs({**rd, "spy_vs_200": vs200}, breadth, geo,
                            vix=vix, vix_rising=vix_rising)
    dip_char = _dip()
    alloc = _alloc(dip_char, forward, vix)
    posture = {"stance": "AUTO-SNAPSHOT", "vix": vix,
               "spy_vs_200": vs200, "spy_5d": s5,
               "forward": forward, "dip_character": dip_char,
               "allocation": alloc, "breadth": breadth, "geo": geo}
    snapshot_regime(posture)
    return {"lead": forward.get("lead_scenario"),
            "p_deep": forward.get("p_deeper_dip_20d"),
            "dip": dip_char.get("character") if dip_char else None,
            "cash": (alloc or {}).get("cash_buffer_pct")}
