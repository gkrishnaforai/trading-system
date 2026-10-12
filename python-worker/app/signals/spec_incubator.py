"""Spec incubator — the pipeline between the daily quality-mover
screen and engine membership. One big day is noise; institutional
research promotes leaders on *sustained* strength:

  admit    a quality-gate-passed mover appearing >=3 times in the
           last 20 sessions (repeated strength = accumulation, not
           a pump) — journaled with its admit price
  track    update appearances/peak; expires if it gives back most
           of the move or the tape breaks — a real leader doesn't
           round-trip
  promote  after 5+ sessions holding the move on healthy tape,
           insert into smallcap_members (<=$30B) or
           rule_breaker_members (>$30B) at watch tier — the engines
           deep-eval and own the thesis from there
  expire   gave back >=50% of the move, tape broke, went quiet for
           20+ sessions, or below the engines' $1B mcap floor

Promotion is research-tier only (watch), never a buy — posture and
readiness still gate any actual action downstream.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_APPEAR_MIN = 3         # appearances in 20 sessions = accumulation
_LOOKBACK_D = 20
_HOLD_MIN = 5           # sessions holding before promotion
_RETAIN_MIN = 0.5       # must keep >=50% of the admitted move
_MCAP_FLOOR = 1e9       # both engines start at $1B
_MCAP_SC = 30e9         # <= $30B → 5x-scout, above → rule-breakers

_TAPE_BROKEN = {"knife", "capitulation", "breakdown", "downtrend"}
_TAPE_OK = {"uptrend", "pullback", "recovery", "basing", "breakout"}


def evaluate(today: date | None = None) -> dict[str, Any]:
    """Nightly: admit persistent quality movers, track incumbents,
    promote graduates to engine watch tiers."""
    from app.database import db
    today = today or datetime.now(timezone.utc).date()

    # ── admit: quality movers appearing repeatedly in the window
    hist = db.execute_query(
        """SELECT symbol, count(*) apps, max(change_pct) best_chg,
                  max(as_of_date) last_seen,
                  (array_agg(verdict ORDER BY as_of_date DESC))[1]
                      AS last_verdict,
                  (array_agg(passed ORDER BY as_of_date DESC))[1]
                      AS last_passed
           FROM mover_snapshots
           WHERE as_of_date > :today - :lb
           GROUP BY symbol HAVING count(*) >= :m""",
        {"today": today, "lb": _LOOKBACK_D, "m": _APPEAR_MIN})
    members = {r["symbol"] for r in db.execute_query(
        "SELECT symbol FROM rule_breaker_members"
        " UNION SELECT symbol FROM smallcap_members")}
    active = {r["symbol"] for r in db.execute_query(
        "SELECT symbol FROM spec_candidates"
        " WHERE state = 'incubating'")}
    px_map = {r["symbol"]: r["close"] for r in db.execute_query(
        """SELECT DISTINCT ON (symbol) symbol, close
           FROM daily_bars WHERE symbol = ANY(:s)
           ORDER BY symbol, date DESC""",
        {"s": [h["symbol"] for h in hist] or ["__none__"]})}

    admitted = []
    for h in hist:
        sym = h["symbol"]
        if sym in members or sym in active:
            continue
        if (h["last_passed"] or 0) < 4 \
                and h["last_verdict"] != "GROWTH MOVER":
            continue                       # quality gate holds
        px = px_map.get(sym)
        if not px:
            continue
        db.execute_update(
            """INSERT INTO spec_candidates
               (symbol, first_seen, last_seen, appearances,
                best_chg_pct, admit_price, peak_price, verdict)
               VALUES (:s, :fs, :ls, :ap, :bc, :px, :px, :v)
               ON CONFLICT (symbol, first_seen) DO NOTHING""",
            {"s": sym, "fs": h["last_seen"], "ls": today,
             "ap": h["apps"], "bc": h["best_chg"], "px": px,
             "v": h["last_verdict"]})
        admitted.append(sym)
        active.add(sym)

    # ── track incumbents: appearances, peak, tape, retention
    inc = db.execute_query(
        "SELECT * FROM spec_candidates WHERE state='incubating'")
    syms = [r["symbol"] for r in inc] or ["__none__"]
    mom_map = {r["symbol"]: r for r in db.execute_query(
        "SELECT symbol, momentum_state FROM stocks"
        " WHERE symbol = ANY(:s)", {"s": syms})}
    cur_px = {r["symbol"]: r["close"] for r in db.execute_query(
        """SELECT DISTINCT ON (symbol) symbol, close
           FROM daily_bars WHERE symbol = ANY(:s)
           ORDER BY symbol, date DESC""", {"s": syms})}
    mc_map = {r["symbol"]: r["mcap"] for r in db.execute_query(
        "SELECT symbol, market_cap mcap FROM stocks"
        " WHERE symbol = ANY(:s)", {"s": syms})}
    recent_apps = {r["symbol"]: r["n"] for r in db.execute_query(
        """SELECT symbol, count(*) n FROM mover_snapshots
           WHERE symbol = ANY(:s) AND as_of_date > :t - :lb
           GROUP BY symbol""",
        {"s": syms, "t": today, "lb": _LOOKBACK_D})}

    promoted, expired = [], []
    for c in inc:
        sym = c["symbol"]
        mom = (mom_map.get(sym) or {}).get("momentum_state")
        px = cur_px.get(sym) or c.get("admit_price")
        peak = max(c.get("peak_price") or 0, px or 0)
        apps = (recent_apps.get(sym) or 0) + c["appearances"]
        days_in = (today - c["first_seen"]).days
        upd = {"id": c["id"], "apps": apps, "pk": peak, "ls": today,
               "mom": mom, "vc": c.get("verdict")}

        # expire — gave back the move, tape broke, or went quiet
        gain = (peak or 0) - (c.get("admit_price") or 0)
        faded = (gain > 0 and px is not None
                 and (peak - px) / gain > (1 - _RETAIN_MIN))
        quiet = (today - c["last_seen"]).days > _LOOKBACK_D \
            and (recent_apps.get(sym) or 0) == 0
        reason = ("round-tripped >50% of the move" if faded else
                  f"tape {mom}" if mom in _TAPE_BROKEN else
                  "quiet for 20+ sessions" if quiet else
                  "below the $1B engine floor"
                  if days_in >= _HOLD_MIN
                  and (mc_map.get(sym) or 0) < _MCAP_FLOOR else None)
        if reason:
            db.execute_update(
                """UPDATE spec_candidates SET state='expired',
                   expired_reason=:r, appearances=:apps, peak_price=:pk,
                   mom_state=:mom, updated_at=now() WHERE id=:id""",
                {**upd, "r": reason})
            expired.append(f"{sym}({reason})")
            continue

        # promote — held the move 5+ sessions on healthy tape
        if days_in >= _HOLD_MIN and mom in _TAPE_OK and not faded:
            mc = mc_map.get(sym) or 0
            engine = "5x-scout" if mc <= _MCAP_SC else "rule-breakers"
            tier = "watch" if engine == "5x-scout" else "watchlist"
            tbl = ("smallcap_members" if engine == "5x-scout"
                   else "rule_breaker_members")
            db.execute_update(
                f"INSERT INTO {tbl} (symbol, tier) VALUES (:s,:t)"
                " ON CONFLICT (symbol) DO NOTHING",
                {"s": sym, "t": tier})
            db.execute_update(
                """UPDATE spec_candidates SET state='promoted',
                   engine=:e, promoted_tier=:t, appearances=:apps,
                   peak_price=:pk, mom_state=:mom, updated_at=now()
                   WHERE id=:id""", {**upd, "e": engine, "t": tier})
            promoted.append(f"{sym}→{engine}")
            continue

        db.execute_update(
            """UPDATE spec_candidates SET appearances=:apps,
               peak_price=:pk, mom_state=:mom, last_seen=:ls,
               updated_at=now() WHERE id=:id""", upd)

    return {"admitted": admitted, "promoted": promoted,
            "expired": expired, "incubating":
            len(active) - len(promoted) - len(expired)}


def report(days: int = 30) -> dict[str, Any]:
    """The funnel for the page — incubating plus recent outcomes."""
    from app.database import db
    rows = db.execute_query(
        """SELECT * FROM spec_candidates
           WHERE state = 'incubating'
              OR updated_at > now() - make_interval(days => :d)
           ORDER BY state, last_seen DESC LIMIT 60""",
        {"d": days})
    for r in rows:
        r["days_in"] = ((r["last_seen"] - r["first_seen"]).days
                        if r.get("first_seen") and r.get("last_seen")
                        else None)
        if r.get("peak_price") and r.get("admit_price"):
            r["retained_pct"] = round(
                (r["peak_price"] - r["admit_price"])
                / r["admit_price"] * 100, 1)
    return {"candidates": rows}
