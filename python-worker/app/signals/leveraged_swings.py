"""3x semiconductor ETF swing detector — SOXS / SOXL.

Two deterministic setups over the index tape (SMH primary proxy; the
underlying of both products is the NYSE Semiconductor Index — SMH/SOXX
track it closely but not exactly, and the mismatch is surfaced, not
hidden):

  SOXS (3x inverse — a bet semis FALL)
    armed     index RSI14 >= 75 AND close >= 8% above the 50dma
    trigger   latest close below the 8EMA (fresh roll-over preferred:
              a failed 20d high within ~5 bars counts as evidence)
    veto      broad breakout — new 20d high TODAY with most leaders
              in constructive tape ("strong earnings + broad
              participation" — exactly when the fade is wrong)

  SOXL (3x long — a bet semis REBOUND)
    armed     index RSI14 < 30 AND close within 8% of the prior 60d
              swing low (meaningful support, not mid-air)
    trigger   close back above the 8EMA with easing legs (RSI hooking
              up / higher lows forming / selling volume drying)
    prefer    higher low vs the prior swing — a retest that holds is
              confirmation, a hammer alone is not

Risk framing (per the spec these guardrails are part of the signal,
not an afterthought): the stop lives on the INDEX invalidation level,
translated to the ETF via the 3x daily-move assumption; sizing comes
from a caller-supplied portfolio value and a 0.25-0.5% risk budget;
targets are 1.5R/2R partials. Output is advisory — these are
hypotheses to grade in the journal, not trades to take.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Optional

from app.signals.momentum_regime import _rsi_simple

logger = logging.getLogger(__name__)

SIGNAL_SRC = "SMH"            # closest liquid proxy to the index
SIGNAL_CONFIRM = "SOXX"       # corroboration when stored
PRODUCTS = ("SOXS", "SOXL")
LEVERAGE = 3.0
RSI_HOT, RSI_COLD = 75.0, 30.0
EXT_VS50, NEAR_SUPPORT = 0.08, 0.08

# semis leadership tape — whichever exist in stocks count toward
# the "leaders also weakening / broad participation" leg
_LEADERS = ("NVDA", "AVGO", "TSM", "AMD", "QCOM", "MU",
            "INTC", "ASML", "TXN", "ARM", "ANET")
_CONSTRUCTIVE = {"uptrend", "breakout", "climax", "pullback",
                 "basing", "recovery"}
_HOSTILE = {"rolling_over", "downtrend", "breakdown", "knife",
            "capitulation"}


def _ema(closes: list[float], n: int) -> list[float]:
    """Plain EMA series — same formula as _technicals' ema8."""
    if not closes:
        return []
    k, out = 2 / (n + 1), [closes[0]]
    for c in closes[1:]:
        out.append(c * k + out[-1] * (1 - k))
    return out


def _leader_tape() -> dict[str, Any]:
    """Bulk momentum_state read for the semis leadership list."""
    from app.database import db
    rows = db.execute_query(
        "SELECT symbol, momentum_state FROM stocks"
        " WHERE symbol = ANY(:s)", {"s": list(_LEADERS)})
    tape = {r["symbol"]: r["momentum_state"] for r in rows}
    constr = [s for s, st in tape.items() if st in _CONSTRUCTIVE]
    hostile = [s for s, st in tape.items() if st in _HOSTILE]
    return {"tracked": len(tape), "constructive": constr,
            "hostile": hostile,
            "ratio": (round(len(constr) / len(tape), 2)
                      if tape else None)}


def _semi_alerts() -> dict[str, Any]:
    """Recent HIGH-materiality NEGATIVE alerts on semis — the
    'catalyst that breaks support' caution for SOXL."""
    from app.database import db
    rows = db.execute_query(
        "SELECT symbol, title, created_at FROM alert_items"
        " WHERE direction = 'NEGATIVE' AND materiality = 'HIGH'"
        " AND symbol = ANY(:s)"
        " AND created_at >= now() - interval '5 days'"
        " ORDER BY created_at DESC LIMIT 5",
        {"s": list(_LEADERS) + ["SMH", "SOXX", "SOXL", "SOXS"]})
    return {"count": len(rows),
            "items": [{"symbol": r["symbol"],
                       "title": (r["title"] or "")[:80]} for r in rows]}


def _portfolio_mv() -> Optional[float]:
    """Current portfolio market value for default sizing."""
    from app.database import db
    r = db.execute_query(
        "SELECT COALESCE(SUM(COALESCE(current_value,"
        " quantity * avg_price)), 0) mv"
        " FROM portfolio_positions")[0]
    mv = float(r["mv"] or 0)
    return mv if mv > 0 else None


def _taped(bars, n: int) -> Optional[dict[str, Any]]:
    """Common index-tape features shared by both setups.

    RSI/stretch extremes are 7-bar RECENT peaks, not current-state —
    the spec is a sequence ('RSI reaches 75-80, then closes below the
    8EMA' / 'falls below 30, selling eases, then reclaims'). By the
    trigger bar the current RSI has already moved off the extreme."""
    if not bars or len(bars) < 60:
        return None
    closes = [b.close for b in bars]
    highs, lows = [b.high for b in bars], [b.low for b in bars]
    sma50 = sum(closes[-50:]) / 50
    ema8 = _ema(closes, 8)
    swing_low = min(lows[-60:-5])
    hi20_i = max(range(len(highs) - 20, len(highs)), key=highs.__getitem__)
    rsis = [_rsi_simple(closes[:i]) for i in range(len(closes) - 7,
                                                  len(closes) + 1)]
    vs50s = [closes[i] / (sum(closes[i - 49:i + 1]) / 50) - 1
             for i in range(len(closes) - 7, len(closes))]
    return {
        "close": closes[-1], "rsi": _rsi_simple(closes),
        "rsi_hi7": max(r for r in rsis if r is not None),
        "rsi_lo7": min(r for r in rsis if r is not None),
        "vs50_hi7": max(vs50s) if vs50s else None,
        "rsi_dir": ((_rsi_simple(closes) or 0)
                    - (_rsi_simple(closes[:-1]) or 0)),
        "sma50": sma50, "vs50": closes[-1] / sma50 - 1,
        "ema8": ema8[-1], "ema8_prev": ema8[-2],
        "above8": closes[-1] > ema8[-1],
        "below8": closes[-1] < ema8[-1],
        "fresh_break8": closes[-2] >= ema8[-2] > closes[-1],
        "swing_low": swing_low,
        "near_support": closes[-1] <= swing_low * (1 + NEAR_SUPPORT),
        "hi20": highs[hi20_i], "hi20_age": len(highs) - 1 - hi20_i,
        "stop10_hi": max(highs[-10:]), "stop10_lo": min(lows[-10:]),
        "higher_low": min(lows[-5:]) > swing_low,
        "new_hi_today": closes[-1] >= max(highs[-21:-1]),
        "vol_dip": _vol_dip(bars),
    }


def _vol_dip(bars) -> Optional[float]:
    """Down-day volume vs 20d average — <1 = sellers exhausting."""
    dn = [b.volume for b in bars[-10:] if b.close < b.open]
    al = [b.volume for b in bars[-20:]]
    if not dn or not al or not sum(al):
        return None
    return (sum(dn) / len(dn)) / (sum(al) / len(al))


def _soxs(t: dict, leaders: dict) -> dict[str, Any]:
    """Fade-the-extension: armed on RSI>75 + 8% stretch, triggered on
    the 8EMA break, vetoed on a broad-breakout day."""
    armed = ((t["rsi_hi7"] or 0) >= RSI_HOT
             and (t["vs50_hi7"] or 0) >= EXT_VS50)
    failed_hi = t["hi20_age"] <= 5 and t["close"] < t["hi20"]
    broad = t["new_hi_today"] and (leaders["ratio"] or 0) >= 0.6
    triggered = armed and t["below8"]
    state = ("vetoed" if armed and broad
             else "triggered" if triggered
             else "armed" if armed else "flat")
    veto = ("sector breaking out on broad participation"
            if state == "vetoed" else None)
    checklist = [
        {"ok": (t["rsi_hi7"] or 0) >= RSI_HOT,
         "line": (f"index RSI {t['rsi']:.0f} now / {t['rsi_hi7']:.0f} "
                  f"7-bar peak ≥ {RSI_HOT:.0f}"
                  if t["rsi"] else "index RSI — no tape")},
        {"ok": (t["vs50_hi7"] or 0) >= EXT_VS50,
         "line": f"{t['vs50'] * 100:+.0f}% vs 50dma now / "
                 f"{(t['vs50_hi7'] or 0) * 100:+.0f}% 7-bar peak "
                 "(≥+8% stretch)"},
        {"ok": t["below8"],
         "line": "close below 8EMA (the roll-over trigger)"},
        {"ok": failed_hi, "soft": True,
         "line": "failed 20d high within 5 bars (preferred)"},
        {"ok": not broad,
         "line": ("leaders NOT in broad breakout"
                  f" ({leaders['ratio'] or 0:.0%} constructive)")},
    ]
    # index invalidation = reclaim of the 10d swing high; SOXS falls
    # ~3x that percentage — entry/stop/targets stay R-framed
    idx_move = t["stop10_hi"] / t["close"] - 1
    return {"armed": armed, "state": state, "veto": veto,
            "checklist": checklist, "idx_stop_pct": idx_move,
            "etf_dir": -LEVERAGE, "rr_note":
            "stop = index 10d high; entry only pays if ~1.5R "
            "to the 50dma round-trip is plausible"}


def _soxl(t: dict, leaders: dict, alerts: dict) -> dict[str, Any]:
    """Confirmed-rebound: armed on RSI<30 near the 60d swing low,
    triggered on an 8EMA reclaim with easing pressure."""
    armed = (t["rsi_lo7"] or 100) < RSI_COLD and t["near_support"]
    easing = sum([
        (t["rsi_dir"] or 0) > 0,          # RSI hooking up
        t["higher_low"],                  # stops printing fresh lows
        (t["vol_dip"] or 9) < 1.0,        # sellers exhausting
    ])
    triggered = armed and t["above8"] and easing >= 2
    state = ("triggered" if triggered
             else "armed" if armed else "flat")
    warn = (f"{alerts['count']} high-materiality bearish alerts on "
            "semis in 5d — support can fail on thesis deterioration"
            if alerts["count"] else None)
    checklist = [
        {"ok": (t["rsi_lo7"] or 100) < RSI_COLD,
         "line": (f"index RSI {t['rsi']:.0f} now / {t['rsi_lo7']:.0f} "
                  f"7-bar low < {RSI_COLD:.0f}"
                  if t["rsi"] else "index RSI — no tape")},
        {"ok": t["near_support"],
         "line": f"within {NEAR_SUPPORT:.0%} of 60d swing low "
         f"({t['swing_low']:.2f})"},
        {"ok": t["above8"],
         "line": "close back above 8EMA (the reclaim trigger)"},
        {"ok": easing >= 2,
         "line": f"selling pressure easing ({easing}/3 legs: RSI "
         "turn / higher lows / dry volume)"},
        {"ok": t["higher_low"], "soft": True,
         "line": "higher low vs prior swing (preferred over a "
         "lone hammer)"},
        {"ok": not warn, "soft": True, "line": warn
         or "no fresh bearish catalyst alerts on semis"},
    ]
    idx_move = t["close"] / t["stop10_lo"] - 1
    return {"armed": armed, "state": state, "veto": None,
            "warn": warn, "checklist": checklist,
            "idx_stop_pct": idx_move, "etf_dir": LEVERAGE}


def evaluate(funds: Optional[float] = None,
             risk_pct: float = 0.0035) -> dict[str, Any]:
    """Both setups over today's stored tape; journal one row/etf/day.

    funds    portfolio value for sizing (defaults to portfolio MV)
    risk_pct planned-loss budget — spec says start 0.25-0.5% while
             the strategy is being validated
    """
    from app.database import db
    from app.market_data import bars as bars_mod

    books = bars_mod.load([SIGNAL_SRC, SIGNAL_CONFIRM, *PRODUCTS],
                          days=400)
    idx, idx2 = books.get(SIGNAL_SRC), books.get(SIGNAL_CONFIRM)
    t = _taped(idx, 60)
    leaders, alerts = _leader_tape(), _semi_alerts()
    if funds is None:
        funds = _portfolio_mv()

    out = {"as_of": (idx[-1].date.isoformat() if idx else
                     date.today().isoformat()),
           "signal_src": SIGNAL_SRC, "funds": funds,
           "risk_pct": risk_pct, "etfs": {},
           "caveat": "SMH/SOXX proxy the NYSE Semiconductor Index; "
           "SOXL/SOXS compound daily — multi-day returns diverge "
           "from 3x. Grading the journal is the proof, not the RSI."}
    if t is None:
        out["error"] = "no index tape stored"
        return out

    for etf in PRODUCTS:
        setup = (_soxs(t, leaders) if etf == "SOXS"
                 else _soxl(t, leaders, alerts))
        eb = books.get(etf) or []
        etf_px = float(eb[-1].close) if eb else None
        # index invalidation → ETF stop via the 3x daily-move map
        etf_stop = (round(etf_px * (1 - setup["idx_stop_pct"]
                                   * LEVERAGE), 2)
                    if etf_px else None)
        risk_px = (etf_px - etf_stop
                   if etf_px and etf_stop else None)
        t1 = (round(etf_px + 1.5 * risk_px, 2)
              if risk_px and risk_px > 0 else None)
        t2 = (round(etf_px + 2.0 * risk_px, 2)
              if risk_px and risk_px > 0 else None)
        shares = (int(funds * risk_pct / risk_px)
                  if funds and risk_px and risk_px > 0 else None)
        row = {"state": setup["state"], "armed": setup["armed"],
               "veto": setup.get("veto"), "warn": setup.get("warn"),
               "checklist": setup["checklist"],
               "index": {"close": round(t["close"], 2),
                         "rsi": round(t["rsi"], 1) if t["rsi"] else None,
                         "vs50": round(t["vs50"], 4),
                         "ema8": round(t["ema8"], 2),
                         "soxx_close": (round(idx2[-1].close, 2)
                                        if idx2 else None)},
               "levels": {"entry": etf_px, "stop": etf_stop,
                          "t1": t1, "t2": t2,
                          "risk_px": (round(risk_px, 2)
                                      if risk_px else None),
                          "shares": shares,
                          "risk_usd": (round(shares * risk_px, 0)
                                       if shares else None),
                          "idx_stop": (round(t["stop10_hi"], 2)
                                       if etf == "SOXS" else
                                       round(t["stop10_lo"], 2))},
               "leaders": leaders}
        out["etfs"][etf] = row
        try:
            db.execute_update(
                "INSERT INTO lev_etf_evals (as_of, etf, signal_src,"
                " state, rsi, vs50, ema8_rel, idx_close, etf_px,"
                " stop_px, t1_px, t2_px, risk_pct_px, checklist,"
                " veto, leaders)"
                " VALUES (:d,:e,:src,:st,:rsi,:v50,:e8,:ic,:ep,:sp,"
                " :t1,:t2,:rp,:ck::jsonb,:v,:ld::jsonb)"
                " ON CONFLICT (as_of, etf) DO UPDATE SET"
                " state=EXCLUDED.state, rsi=EXCLUDED.rsi,"
                " vs50=EXCLUDED.vs50, ema8_rel=EXCLUDED.ema8_rel,"
                " idx_close=EXCLUDED.idx_close,"
                " etf_px=EXCLUDED.etf_px, stop_px=EXCLUDED.stop_px,"
                " t1_px=EXCLUDED.t1_px, t2_px=EXCLUDED.t2_px,"
                " risk_pct_px=EXCLUDED.risk_pct_px,"
                " checklist=EXCLUDED.checklist,"
                " veto=EXCLUDED.veto, leaders=EXCLUDED.leaders",
                {"d": out["as_of"], "e": etf, "src": SIGNAL_SRC,
                 "st": row["state"], "rsi": row["index"]["rsi"],
                 "v50": row["index"]["vs50"],
                 "e8": (t["close"] / t["ema8"] - 1),
                 "ic": row["index"]["close"], "ep": etf_px,
                 "sp": etf_stop, "t1": t1, "t2": t2,
                 "rp": (risk_px / etf_px
                        if risk_px and etf_px else None),
                 "ck": __import__("json").dumps(row["checklist"]),
                 "v": setup.get("veto"),
                 "ld": __import__("json").dumps(leaders)})
        except Exception as exc:
            logger.debug("lev eval journal %s: %s", etf, exc)
    return out
