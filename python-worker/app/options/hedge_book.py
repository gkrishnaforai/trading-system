"""Hedge book — the portfolio insurance program.

Structure: QQQ put spreads (index hedge — the book's risk is
systematic AI-beta, not single-name). Long ~5% OTM / short ~20-25%
OTM, 60-90 DTE. Sized to book_beta × book_value so the notional
actually covers a high-beta book — a $100k book at beta 1.4 needs
~$140k of index notional, not $100k.

The regime-scaling the desk actually uses:

  coverage target   how much of the beta-adjusted book to hedge
  budget            annual premium cap — adaptive to the regime read

    calm       VIX<16, det>0, p_deep<40    → 40% cover, 2.5%/yr cap
    watch      det<0 or p_deep 40-55       → 55% cover, 4%/yr
    elevated   VIX 20-25 or p_deep 55-65   → 70% cover, 5%/yr
    fat tail   VIX>25, p_deep>65, or
               broad_deleveraging          → 85% cover, 6%/yr

Insurance is cheapest exactly when it feels unnecessary — the calm
tier exists so you're already hedged when the tail shows up. The
elevated tiers spend MORE per year but buy less insurance per dollar;
that's the honest cost of being late to the hedge.

Monetization ladder — value-realization keyed, not spot-% keyed:
a spread approaching its max payoff has extracted what it can.

  value_pct ≥ 50% of width + SPY −10%   → trim 25%
  value_pct ≥ 65% of width + SPY −15%   → trim to 50%
  value_pct ≥ 80% of width + SPY −20%   → trim to 25%
  value_pct ≥ 90% of width              → monetize remaining — the
                                          insurance did its job

All alerts, no execution — human-in-the-loop stays the operator.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any, Optional

logger = logging.getLogger(__name__)

HEDGE_UNDERLIER = "QQQ"          # best match for the AI-beta book
_LONG_OTM = 0.95                 # buy ~5% out-of-the-money put
_SHORT_OTM = 0.78                # sell ~22% OTM put (the cost offset)
_DTE_MIN, _DTE_MAX = 60, 95      # spread tenor window


# ------------------------------------------------------- regime → targets

_STATE_TIERS = {
    # canonical defensive_state → coverage tier. CAPITULATION keeps max
    # coverage on paper — the monetization ladder owns the unwind there.
    "NORMAL":       ("calm",      0.40, 0.025,
                     "cheap insurance — baseline coverage is the "
                     "discipline"),
    "WATCH":        ("watch",     0.55, 0.04,
                     "tighten coverage; insurance still reasonably "
                     "priced"),
    "HEDGE":        ("elevated",  0.70, 0.05,
                     "confirmed downtrend — top up coverage even at "
                     "higher premium"),
    "DEFENSIVE":    ("fat_tail",  0.85, 0.06,
                     "tail is fat — max coverage"),
    "CAPITULATION": ("fat_tail",  0.85, 0.06,
                     "capitulation zone — existing hedges monetize on "
                     "the ladder, no new insurance at peak IV"),
    "RECOVERY":     ("watch",     0.55, 0.04,
                     "recovery phase — coverage tapers as the book "
                     "re-risks"),
}


def _targets(vix: Optional[float], p_deep: Optional[int],
             deterioration: Optional[float],
             dip_char: Optional[str],
             defensive_state: Optional[str] = None) -> dict[str, Any]:
    """Regime → coverage target + annual premium budget.

    Preferred path: the canonical defensive_state from
    market_defensive_snapshots (hysteresis-gated — the tier inherits
    the streak persistence for free). Legacy path scores raw inputs;
    kept as fallback until snapshots have history."""
    if defensive_state in _STATE_TIERS:
        tier, cov, bud, note = _STATE_TIERS[defensive_state]
        return {"tier": tier, "coverage": cov, "budget_pct": bud,
                "note": note, "source": "defensive_state",
                "state": defensive_state}
    score = 0
    if vix is not None:
        score += (2 if vix >= 25 else 1 if vix >= 20 else 0)
    if p_deep is not None:
        score += (2 if p_deep >= 65 else 1 if p_deep >= 55
                  else 0 if p_deep < 40 else 1)
    if deterioration is not None and deterioration < -0.3:
        score += 1
    if dip_char == "broad_deleveraging":
        score += 3
    if dip_char == "rotation_out_of_ai":
        score += 1

    if score >= 4:
        return {"tier": "fat_tail", "coverage": 0.85, "budget_pct": 0.06,
                "source": "legacy", "state": None,
                "note": "tail is fat — max coverage; also where the "
                        "monetization ladder lives"}
    if score >= 2:
        return {"tier": "elevated", "coverage": 0.70, "budget_pct": 0.05,
                "source": "legacy", "state": None,
                "note": "risk elevated — top up coverage even at "
                        "higher premium"}
    if score == 1:
        return {"tier": "watch", "coverage": 0.55, "budget_pct": 0.04,
                "source": "legacy", "state": None,
                "note": "tighten coverage; insurance still reasonably "
                        "priced"}
    return {"tier": "calm", "coverage": 0.40, "budget_pct": 0.025,
            "source": "legacy", "state": None,
            "note": "cheap insurance — baseline coverage is the "
                    "discipline: you're hedged before the tail shows"}


# ------------------------------------------------------------- book CRUD

def open_spread(p: dict) -> dict:
    """Journal a put-spread the human opened. Required: expiry,
    long_strike, short_strike, cost (net debit)."""
    from app.database import db
    import json
    db.execute_update(
        """INSERT INTO hedge_positions
           (as_of, instrument, underlier, expiry, long_strike,
            short_strike, qty, cost, notional, spot_at_entry,
            vix_at_entry, regime_note)
           VALUES (:d, :i, :u, :e, :l, :s, :q, :c, :n, :sp, :v, :rn)""",
        {"d": p.get("as_of") or date.today(),
         "i": p.get("instrument") or f"{HEDGE_UNDERLIER} put spread",
         "u": p.get("underlier") or HEDGE_UNDERLIER,
         "e": p["expiry"], "l": p["long_strike"], "s": p["short_strike"],
         "q": p.get("qty") or 1, "c": p["cost"],
         "n": p.get("notional"), "sp": p.get("spot_at_entry"),
         "v": p.get("vix_at_entry"), "rn": p.get("regime_note"),
         })
    row = db.execute_query(
        "SELECT * FROM hedge_positions ORDER BY id DESC LIMIT 1")
    return row[0] if row else {}


def close_spread(pos_id: int, close_value: Optional[float] = None,
                 reason: str = "manual") -> dict:
    from app.database import db
    rows = db.execute_query(
        "SELECT * FROM hedge_positions WHERE id=:i", {"i": pos_id})
    if not rows:
        return {"error": "not found"}
    pos = rows[0]
    width = float(pos["long_strike"]) - float(pos["short_strike"])
    realized = None
    if close_value is not None and width:
        realized = round(close_value / width * 100, 1)
    db.execute_update(
        """UPDATE hedge_positions SET status='closed', closed_at=now(),
           close_reason=:r, mark_value=:v, realized_pct=:p,
           updated_at=now() WHERE id=:i""",
        {"r": reason, "v": close_value, "p": realized, "i": pos_id})
    return {"closed": pos_id, "realized_pct_of_width": realized}


def trim_spread(pos_id: int, trim_pct: float,
                mid: Optional[float] = None) -> dict:
    """Journal a partial monetization — the ladder fill."""
    from app.database import db
    rows = db.execute_query(
        "SELECT trim_events, qty FROM hedge_positions WHERE id=:i",
        {"i": pos_id})
    if not rows:
        return {"error": "not found"}
    evs = list(rows[0]["trim_events"] or [])
    evs.append({"date": str(date.today()), "pct": round(trim_pct, 2),
                "mid": mid})
    db.execute_update(
        """UPDATE hedge_positions SET status='trimmed',
           trim_events=CAST(:e AS jsonb), updated_at=now()
           WHERE id=:i""",
        {"e": __import__("json").dumps(evs), "i": pos_id})
    return {"trimmed": pos_id, "pct": trim_pct,
            "events": len(evs)}


# ---------------------------------------------------------- live marks

def _qqq_spread_mid(expiry: date, long_k: float,
                    short_k: float) -> tuple:
    """Live mid of the put spread: long_put − short_put. Returns
    (spread_mid, qqq_spot); either may be None."""
    try:
        import yfinance as yf
        ch = yf.Ticker(HEDGE_UNDERLIER).option_chain(str(expiry))
        puts = ch.puts
        def _mid(k):
            row = puts.iloc[(puts["strike"] - k).abs().argsort()[:1]]
            if row.empty:
                return None
            r = row.iloc[0]
            bid, ask = float(r.get("bid") or 0), float(r.get("ask") or 0)
            last = float(r.get("lastPrice") or 0)
            return (bid + ask) / 2 if bid and ask else last or None
        lp, sp = _mid(long_k), _mid(short_k)
        spot = None
        try:
            spot = float(yf.Ticker(HEDGE_UNDERLIER).history(
                period="2d")["Close"].iloc[-1])
        except Exception:
            pass
        if lp is None:
            return None, spot
        return round(lp - (sp or 0), 2), spot
    except Exception as exc:
        logger.debug("hedge chain mark: %s", exc)
        return None, None


def mark_hedges() -> dict:
    """Daily reprice + monetization-ladder alerts. Wired into the
    leaps-mark job — same cadence, free fetches."""
    from app.database import db
    open_h = db.execute_query(
        "SELECT * FROM hedge_positions WHERE status IN ('open','trimmed')")
    if not open_h:
        return {"marked": 0}
    alerts = []
    for h in open_h:
        mid, spot = _qqq_spread_mid(
            h["expiry"], float(h["long_strike"]),
            float(h["short_strike"]))
        if mid is None:
            continue
        width = float(h["long_strike"]) - float(h["short_strike"])
        value_pct = round(mid / width * 100, 1) if width else None
        dd = None
        if spot and h.get("spot_at_entry"):
            dd = round((spot / float(h["spot_at_entry"]) - 1) * 100, 1)
        # monetization ladder — value realization × market drawdown
        alert = None
        if value_pct is not None:
            if value_pct >= 90:
                alert = ("🏁 spread at ~max value — the insurance did "
                         "its job; monetize remaining and redeploy")
            elif value_pct >= 80 and (dd or 0) <= -20:
                alert = ("💰 hedge deep in profit (80% of width) — "
                         "trim to ~25%, cash is now live ammo")
            elif value_pct >= 65 and (dd or 0) <= -15:
                alert = ("💰 hedge paying (65% of width) — trim "
                         "another 25%")
            elif value_pct >= 50 and (dd or 0) <= -10:
                alert = ("💰 hedge at half its max — first 25% trim "
                         "zone; redeploy on dip_phase turning_up")
        if alert:
            alerts.append({"id": h["id"], "underlier": h["underlier"],
                           "value_pct": value_pct, "dd": dd,
                           "alert": alert})
        db.execute_update(
            """UPDATE hedge_positions SET mark_value=:m,
               spot_mark=:s, realized_pct=:p, mark_at=now(),
               updated_at=now() WHERE id=:i""",
            {"m": mid, "s": spot, "p": value_pct, "i": h["id"]})
    return {"marked": len(open_h), "alerts": alerts}


# ------------------------------------------------------------- state read

def state() -> dict[str, Any]:
    """The hedge card — current coverage vs regime-scaled target,
    spend vs adaptive budget, and where the ladder stands."""
    from app.database import db
    open_h = db.execute_query(
        "SELECT * FROM hedge_positions WHERE status IN ('open','trimmed')")
    # book sizing — beta-adjusted notional is the honest denominator
    try:
        from app.signals import book_risk
        bk = book_risk.read() or {}
        book_val = float(bk.get("book_value") or 0)
        beta = float(bk.get("book_beta") or 1.0)
    except Exception:
        book_val, beta = 0.0, 1.0
    exposure = book_val * beta

    covered = sum(float(h.get("notional") or 0) for h in open_h)
    spent = sum(float(h["cost"]) for h in open_h)
    year = date.today().year
    spent_ytd = db.execute_query(
        """SELECT COALESCE(sum(cost),0) s FROM hedge_positions
           WHERE EXTRACT(year FROM as_of) = :y""",
        {"y": year})
    spent_ytd = float(spent_ytd[0]["s"]) if spent_ytd else 0.0

    # regime inputs for the target — read the stored layers, no fetch
    vix = p_deep = det = dip_char = None
    try:
        rd = db.execute_query(
            "SELECT value FROM engine_weights WHERE key='geo:context'")
        if rd:
            v = rd[0]["value"]
            if isinstance(v, str):
                v = __import__("json").loads(v)
    except Exception:
        pass
    try:
        from app.signals import breadth as _br
        b = _br.read() or {}
    except Exception:
        b = {}
    # forward read carries the freshest p_deep — reuse the stored
    # snapshot if today's was written, else compute light
    try:
        rs = db.execute_query(
            "SELECT p_deeper, dip_character FROM regime_snapshots"
            " ORDER BY as_of DESC LIMIT 1")
        if rs:
            p_deep, dip_char = rs[0]["p_deeper"], rs[0]["dip_character"]
    except Exception:
        pass

    # canonical defensive state first — the hysteresis-gated read the
    # regime graph persists; raw-input scoring only as fallback
    d_state = None
    try:
        from app.market_regime.defensive_store import (
            DefensiveTransitionStore)
        ds = DefensiveTransitionStore().latest()
        if ds:
            d_state = ds.get("stage")
    except Exception:
        pass

    tgt = _targets(vix, p_deep, det, dip_char, defensive_state=d_state)
    target_notional = exposure * tgt["coverage"]
    gap = max(0.0, target_notional - covered)
    budget_cap = book_val * tgt["budget_pct"]
    return {
        "underlier": HEDGE_UNDERLIER,
        "book_value": round(book_val, 0), "book_beta": beta,
        "exposure_beta_adj": round(exposure, 0),
        "tier": tgt["tier"], "coverage_target_pct":
            round(tgt["coverage"] * 100),
        "budget_cap_pct": round(tgt["budget_pct"] * 100, 1),
        "budget_cap_usd": round(budget_cap, 0),
        "spent_ytd": round(spent_ytd, 0),
        "covered_notional": round(covered, 0),
        "coverage_now_pct": round(covered / exposure * 100)
        if exposure else 0,
        "coverage_gap": round(gap, 0),
        "regime_note": tgt["note"],
        "defensive_state": d_state,
        "target_source": tgt.get("source"),
        "open": [{"id": h["id"], "expiry": str(h["expiry"]),
                  "long": float(h["long_strike"]),
                  "short": float(h["short_strike"]),
                  "qty": h["qty"], "cost": float(h["cost"]),
                  "mark": float(h["mark_value"]) if h.get("mark_value")
                          else None,
                  "value_pct": float(h["realized_pct"])
                  if h.get("realized_pct") else None}
                 for h in open_h],
        "n_open": len(open_h),
    }


def suggest_structure() -> dict[str, Any]:
    """What the next tranche looks like — strikes from live QQQ,
    sized to fill the coverage gap. Advisory; the human prices it."""
    from app.market_data import bars as bars_mod
    st_ = state()
    books = bars_mod.load([HEDGE_UNDERLIER], days=5)
    px = (books.get(HEDGE_UNDERLIER) or [None])[-1]
    spot = px.close if px else None
    if not spot or not st_.get("coverage_gap"):
        return {"note": "no coverage gap right now" if not st_.get(
            "coverage_gap") else "QQQ price unavailable"}
    long_k = round(spot * _LONG_OTM)
    short_k = round(spot * _SHORT_OTM)
    # contracts needed: gap / (notional per spread ≈ 100 × spot)
    per_spread = spot * 100
    qty = max(1, round(st_["coverage_gap"] / per_spread))
    exp_lo = date.today() + timedelta(days=_DTE_MIN)
    exp_hi = date.today() + timedelta(days=_DTE_MAX)
    return {
        "underlier": HEDGE_UNDERLIER, "spot": round(spot, 2),
        "long_put": long_k, "short_put": short_k,
        "dte_window": f"{_DTE_MIN}-{_DTE_MAX}d "
                      f"({exp_lo} → {exp_hi})",
        "qty_for_gap": qty,
        "coverage_gap_usd": st_["coverage_gap"],
        "note": ("net debit = (long_put mid − short_put mid) × 100 "
                 "× qty — price it live; insurance is cheapest "
                 "when it feels least needed"),
    }
