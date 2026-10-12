"""Dip character — WHEN the tape dips, what kind is it?

The forward card answers "how likely is a deeper dip?" This answers the
question that actually changes positioning: "if a dip comes, does AI
infra get dragged with it (2022) or does it hold (rotation)?"

Professional desks distinguish dips by where the money GOES:

  broad_deleveraging   correlation → 1, defensives + bonds + dollar bid,
                       credit stressed, breadth collapsed. Money LEAVES
                       equities entirely. High-beta (AI infra) falls
                       hardest — liquidation doesn't read theses.
                       → 2022 pattern: cut beta, no dip-buys.

  rotation_out_of_ai   index holds while AI/semis bleed, dispersion
                       high. Money MOVES within equities. The stealth
                       unwind — Oct-2025: SPY at ATH while crowded
                       books lost 1.8%/day.
                       → cut AI-infra specifically; index hides it.

  narrow_leadership    everything red EXCEPT AI — money concentrating
                       INTO the theme, not leaving. AI is the shelter,
                       not the victim. Two exits: laggards catch up
                       (healthy broadening) or leaders finally crack
                       (then it goes fast — 'generals die last').
                       → dips in leaders are buys WHILE AI RS widens;
                         the trigger to cut is AI RS rolling over with
                       breadth still collapsed.

  sympathetic          AI falls WITH the market (beta ~1), nothing
                       AI-specific. Normal correction mechanics.
                       → treat as ordinary dip; buy leaders on
                         stabilization.

  idiosyncratic_ai     AI down while broad market holds — a theme
                       event (Deepseek-type), not a market dip.
                       → the capex engine's domain; don't generalize
                         to 'market is bearish'.

Inputs (all daily_bars, ~60d window, zero fetches):
  ai_rs       SMH ret20 − SPY ret20, and its 5d slope
  defen_bid   mean ret5 of XLU/GLD/TLT — money leaving risk
  credit      HYG ret5 − LQD ret5 — negative = credit pricing risk
  dispersion  |SMH−SPY| + |ARKK−QQQ| + |XLU−SPY| on 20d — divergence
              between theme and market = selective market
  corr_regime rolling 20d corr(SMH, SPY) minus its 60d mean —
              correlation SPIKES in liquidation, fades in rotation
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

_ETFS = ["SPY", "QQQ", "SMH", "ARKK", "XLU", "GLD", "TLT", "UUP",
         "HYG", "LQD"]


def _closes(books: dict, sym: str) -> list[float]:
    return [b.close for b in (books.get(sym) or [])]


def _ret(closes: list[float], n: int, back: int = 0) -> Optional[float]:
    """n-day return ending `back` days ago (back=0 → latest)."""
    if len(closes) < n + 1 + back:
        return None
    end = len(closes) - back
    a, b = closes[end - n - 1], closes[end - 1]
    return b / a - 1 if a else None


def _corr20(a: list[float], b: list[float]) -> Optional[float]:
    """Pearson corr of the last 20 daily returns of two series."""
    if len(a) < 21 or len(b) < 21:
        return None
    ra = [a[i] / a[i - 1] - 1 for i in range(len(a) - 20, len(a))]
    rb = [b[i] / b[i - 1] - 1 for i in range(len(b) - 20, len(b))]
    ma, mb = sum(ra) / len(ra), sum(rb) / len(rb)
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    va = sum((x - ma) ** 2 for x in ra)
    vb = sum((y - mb) ** 2 for y in rb)
    if va <= 0 or vb <= 0:
        return None
    return cov / (va * vb) ** 0.5


def _corr_series(a: list[float], b: list[float],
                 window: int = 20) -> list[float]:
    """Rolling pairwise corr — for the 60d baseline mean."""
    out = []
    for i in range(window + 1, len(a) + 1):
        c = _corr20(a[i - window - 1:i], b[i - window - 1:i])
        if c is not None:
            out.append(c)
    return out


def classify() -> Optional[dict[str, Any]]:
    """Compute the current dip character + what it implies for the
    AI-infra book. Cheap — reads daily_bars only."""
    from app.market_data import bars as bars_mod
    try:
        books = bars_mod.load(_ETFS, days=120)
    except Exception as exc:
        logger.debug("dip_character load failed: %s", exc)
        return None
    px = {s: _closes(books, s) for s in _ETFS}
    if len(px["SPY"]) < 45 or len(px["SMH"]) < 45:
        return None

    spy5, spy20 = _ret(px["SPY"], 5), _ret(px["SPY"], 20)
    smh5, smh20 = _ret(px["SMH"], 5), _ret(px["SMH"], 20)
    if spy5 is None or smh20 is None:
        return None

    ai_rs20 = smh20 - (spy20 or 0)              # AI vs market, 20d
    ai_rs20_prev = None
    _smh_prev = _ret(px["SMH"], 20, back=5)
    _spy_prev = _ret(px["SPY"], 20, back=5)
    if _smh_prev is not None and _spy_prev is not None:
        ai_rs20_prev = _smh_prev - _spy_prev
    ai_rs_slope = (ai_rs20 - ai_rs20_prev
                   if ai_rs20_prev is not None else None)

    defensives = [_ret(px[s], 5) for s in ("XLU", "GLD", "TLT")]
    defen_bid = (sum(d for d in defensives if d is not None)
                 / len([d for d in defensives if d is not None])
                 if any(d is not None for d in defensives) else None)

    hyg5, lqd5 = _ret(px["HYG"], 5), _ret(px["LQD"], 5)
    credit = (hyg5 - lqd5) if None not in (hyg5, lqd5) else None

    arkk20, qqq20, xlu20 = (_ret(px["ARKK"], 20), _ret(px["QQQ"], 20),
                            _ret(px["XLU"], 20))
    legs = [abs(x) for x in (ai_rs20,
                             (arkk20 - qqq20)
                             if None not in (arkk20, qqq20) else None,
                             (xlu20 - spy20)
                             if None not in (xlu20, spy20) else None)
            if x is not None]
    dispersion = sum(legs) / len(legs) if legs else None

    cs = _corr_series(px["SMH"], px["SPY"], 20)
    corr_now = cs[-1] if cs else None
    corr_base = (sum(cs[-40:-1]) / len(cs[-40:-1])
                 if len(cs) > 5 else None)
    corr_delta = (corr_now - corr_base
                  if None not in (corr_now, corr_base) else None)

    # ---------- classify ----------
    in_dip = (spy5 or 0) < -0.01 or (spy20 or 0) < -0.03
    drivers = [f"AI RS {ai_rs20 * 100:+.1f}pts/20d"]
    if ai_rs_slope is not None:
        drivers.append(f"RS slope {ai_rs_slope * 100:+.1f}pts/5d")
    if corr_delta is not None:
        drivers.append(f"SMH↔SPY corr {corr_now:.2f} "
                       f"({corr_delta:+.2f} vs base)")
    if defen_bid is not None:
        drivers.append(f"defensives {defen_bid * 100:+.1f}%/5d")
    if credit is not None and credit < 0:
        drivers.append(f"credit stress (HYG−LQD {credit * 100:+.1f}%)")

    if not in_dip:
        character = "no_dip"
        read = ("no active dip — the read arms when SPY loses ~1%/5d "
                "or ~3%/20d")
        action = None
    elif (corr_delta or 0) > 0.15 and (defen_bid or 0) > 0 \
            and (credit or 0) < -0.002:
        character = "broad_deleveraging"
        read = ("money LEAVING equities — correlation spiking, "
                "defensives+bonds bid, credit stressed. The 2022 "
                "pattern: liquidation doesn't read theses.")
        action = ("AI infra falls HARDER than the market (beta "
                  "~1.4×) — cut beta, no dip-buys, hedge with puts")
    elif ai_rs20 < -0.03 and (spy20 or 0) > smh20 + 0.02:
        character = "rotation_out_of_ai"
        read = ("AI bleeding while the index holds — money rotating "
                "within equities. The stealth unwind; SPY hides it.")
        action = ("reduce AI-infra specifically — don't wait for the "
                  "index to confirm; it won't")
    elif ai_rs20 > 0.02 and (dispersion or 0) > 0.03:
        character = "narrow_leadership"
        read = ("everything red EXCEPT AI — money concentrating into "
                "the theme, not leaving it. AI is the shelter. Ends "
                "either in broadening (bull) or leaders cracking "
                "(then it's fast).")
        if ai_rs_slope is not None and ai_rs_slope < -0.01:
            read += (" ⚠ but AI RS is now rolling — the 'generals "
                     "die last' trigger is arming.")
        action = ("leader dips are buys WHILE AI RS keeps widening — "
                  "the cut trigger is RS rolling over with breadth "
                  "still collapsed")
    elif ai_rs20 < -0.05 and abs(spy20 or 0) < 0.02:
        character = "idiosyncratic_ai"
        read = ("AI down alone — a theme event, not a market dip. "
                "The capex engine's domain.")
        action = ("check the capex score + transcript language — is "
                  "this narrative or numbers?")
    else:
        character = "sympathetic"
        read = ("AI falling WITH the market at roughly market beta — "
                "ordinary correction mechanics, no AI-specific stress.")
        action = ("normal dip protocol — buy quality leaders on "
                  "stabilization (dip_phase turning_up)")

    return {
        "character": character, "in_dip": in_dip,
        "ai_rs20": round(ai_rs20, 4),
        "ai_rs_slope_5d": (round(ai_rs_slope, 4)
                           if ai_rs_slope is not None else None),
        "smh_ret20": round(smh20, 4), "spy_ret20": round(spy20, 4),
        "spy_ret5": round(spy5, 4),
        "defensive_bid_5d": (round(defen_bid, 4)
                             if defen_bid is not None else None),
        "credit_stress_hyg_lqd_5d": (round(credit, 4)
                                    if credit is not None else None),
        "dispersion_20d": (round(dispersion, 4)
                           if dispersion is not None else None),
        "corr_smh_spy_20d": (round(corr_now, 3)
                             if corr_now is not None else None),
        "corr_vs_baseline": (round(corr_delta, 3)
                             if corr_delta is not None else None),
        "read": read, "action": action,
        "drivers": drivers,
    }
