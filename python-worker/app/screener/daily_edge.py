"""Daily edge — the morning confluence board.

Two lanes, all persisted data, zero provider calls:

  swing     — catalyst × setup: a fresh analyst action (upgrade, PT
              raise, repricing wave, RB promotion) on a name that also
              has a live technical setup (breakout_retest, first_pullback,
              rsi2_extreme, trend_turn). "Why now" × "where to enter".
  breakout  — takeoff watch: within 3% of the 20-day high with relative
              strength, volume expansion, or squeeze coiling. No catalyst
              required — the getting-ready names.

conviction = catalyst(0-40) + setup(0-35) + proof(0-15) + empirical(±10)
empirical = the alert kind's own 5-day win rate vs the 50% baseline,
bounded ±10 — the trained layer: kinds that historically preceded gains
score up, junk kinds score down.

Vetoes are hard: fresh downgrade, falling_knife flag, dilution <72h.
Regime (fear/greed) shows as an aggression chip — it scales size, it
doesn't block. Picks persist to daily_picks for outcome measurement.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

CATALYST_SCORE = {
    "upgrade": 38, "raise": 32, "pt_repricing": 28, "rb_transition": 25,
    "earnings": 30, "contract": 26, "ma": 30, "regulatory": 26,
    "management": 18, "capital": 16,
}
SETUP_SCORE = {
    "breakout_retest": 35, "first_pullback": 30, "breakout": 24,
    "rsi2_extreme": 25, "mean_reversion": 20,
}
TIER_PROOF = {"confirmed": 8, "emerging": 6, "speculative": 4}
BREAKOUT_PROXIMITY = -0.03          # within 3% of 20d high
VETO_HOURS_DOWNGRADE = 48
VETO_HOURS_DILUTION = 72


def _latest_screen() -> dict[str, dict]:
    """symbol → latest screen_runs row (the full technical blob)."""
    from app.database import db
    rows = db.execute_query(
        "SELECT results FROM screen_runs ORDER BY ran_at DESC LIMIT 1")
    if not rows or not rows[0].get("results"):
        return {}
    res = rows[0]["results"]
    if isinstance(res, str):
        res = json.loads(res)
    return {r["symbol"]: r for r in res if r.get("symbol")}


def _fresh_events(hours: int = 48) -> dict[str, list[dict]]:
    """symbol → actionable alerts inside the window."""
    from app.database import db
    rows = db.execute_query(
        """
        SELECT symbol, event_type, direction, title, detail, created_at
        FROM alert_items
        WHERE created_at > now() - make_interval(hours => :h)
          AND (detail->>'bucket') = 'actionable'
        ORDER BY created_at DESC
        """, {"h": hours})
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(r["symbol"], []).append(r)
    return out


def _empirical_adj() -> dict[tuple, float]:
    """(kind, direction) → ±10 score adj from demonstrated 5d win rates."""
    from app.database import db
    try:
        rows = db.execute_query(
            "SELECT kind, direction, win_rate, n FROM alert_kind_stats "
            "WHERE horizon_days = 5 AND n >= 10")
    except Exception:
        return {}
    return {(r["kind"], r["direction"]):
            max(-10.0, min(10.0, (float(r["win_rate"]) - 0.5) * 20))
            for r in rows}


def _proof_maps() -> tuple[dict, dict, dict]:
    """rb tier, accel streak, pt momentum per symbol."""
    from app.database import db
    rb = {r["symbol"]: r["tier"] for r in db.execute_query(
        "SELECT symbol, tier FROM rule_breaker_members")}
    accel = {r["symbol"]: max(r["rev_streak"] or 0, r["eps_streak"] or 0)
             for r in db.execute_query(
                 "SELECT symbol, rev_streak, eps_streak FROM accel_watch "
                 "WHERE run_id = (SELECT run_id FROM accel_watch "
                 "ORDER BY id DESC LIMIT 1)")}
    pt = {}
    for r in db.execute_query(
            "SELECT DISTINCT ON (symbol) symbol, month_avg, quarter_avg "
            "FROM pt_snapshots ORDER BY symbol, as_of DESC"):
        ma, qa = r.get("month_avg"), r.get("quarter_avg")
        if ma and qa:
            pt[r["symbol"]] = float(ma) / float(qa) - 1
    return rb, accel, pt


def _swing_map() -> dict[str, dict]:
    """symbol → stored swing structure (higher-low read) from
    momentum_detail — one query, zero extra fetches."""
    from app.database import db
    out: dict[str, dict] = {}
    try:
        for r in db.execute_query(
                "SELECT symbol, momentum_detail->'swing' AS sw,"
                " momentum_detail->>'rs_pct' AS rs_pct"
                " FROM stocks WHERE momentum_detail->'swing' IS NOT NULL"
                "    OR momentum_detail->>'rs_pct' IS NOT NULL"):
            sw = r.get("sw")
            if isinstance(sw, str):
                import json as _j
                try:
                    sw = _j.loads(sw)
                except Exception:
                    sw = None
            d = dict(sw) if isinstance(sw, dict) else {}
            try:
                d["rs_pct"] = (int(float(r["rs_pct"]))
                               if r.get("rs_pct") is not None else None)
            except Exception:
                d["rs_pct"] = None
            if d.get("phase") or d.get("rs_pct") is not None:
                out[r["symbol"]] = d
    except Exception:
        pass
    return out


def _catalyst_pts(events: list[dict], emp: dict) -> tuple[float, str]:
    """Best fresh event's points (recency-decayed) + a short label."""
    best, label = 0.0, ""
    now = datetime.now(timezone.utc)
    for e in events:
        d = e.get("detail") or {}
        kind = (d.get("action") if e["event_type"] == "analyst_action"
                else "pt_repricing" if e["event_type"] == "pt_repricing"
                else "rb_transition" if e["event_type"] == "rb_transition"
                else d.get("kind") or "")
        if e["event_type"] == "analyst_action" and d.get("new_grade"):
            kind = {"upgrade": "upgrade", "raise": "raise",
                    "downgrade": "downgrade", "lower": "downgrade"}.get(
                d.get("action"), kind)
        base = CATALYST_SCORE.get(kind, 12 if e["event_type"] == "catalyst"
                                  else 0)
        if not base:
            continue
        try:
            ts = e["created_at"]
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            age_h = (now - ts).total_seconds() / 3600
        except Exception:
            age_h = 12
        pts = base * (1.0 if age_h < 24 else 0.6)
        adj = emp.get((kind, e.get("direction")), 0.0)
        pts += adj
        if pts > best:
            best, label = pts, f"{kind} ({age_h:.0f}h)"
    return best, label


def _setup_pts(row: dict) -> tuple[float, str]:
    pats = row.get("detected_patterns") or []
    best = max((SETUP_SCORE.get(p, 0) for p in pats), default=0)
    label = "+".join(pats) if pats else (row.get("setup_type") or "")
    if not best and row.get("bb_squeeze"):
        best, label = 15, "squeeze"
    return best, label


def _vetoes(sym: str, row: dict, events: list[dict]) -> Optional[str]:
    if row.get("falling_knife"):
        return "falling knife flag"
    now = datetime.now(timezone.utc)
    for e in events:
        d = e.get("detail") or {}
        try:
            ts = e["created_at"]
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            age_h = (now - ts).total_seconds() / 3600
        except Exception:
            age_h = 0
        if (e["event_type"] == "analyst_action"
                and e.get("direction") == "NEGATIVE"
                and age_h < VETO_HOURS_DOWNGRADE):
            return f"downgrade {age_h:.0f}h ago"
        if (d.get("kind") == "dilution" and age_h < VETO_HOURS_DILUTION):
            return "dilution alert"
    return None


def compute_edge(top_n: int = 5, hours: int = 48) -> dict[str, Any]:
    """The morning board — confluence-ranked top picks per lane."""
    screen = _latest_screen()
    events = _fresh_events(hours)
    emp = _empirical_adj()
    rb, accel, ptm = _proof_maps()
    swmap = _swing_map()

    # --- lane A: catalyst × setup -------------------------------------
    swing, vetoed = [], []
    for sym, evs in events.items():
        row = screen.get(sym) or {}
        cat_pts, cat_label = _catalyst_pts(evs, emp)
        if cat_pts <= 0:
            continue
        setup_pts, setup_label = _setup_pts(row)
        proof = (TIER_PROOF.get(rb.get(sym), 0)
                 + (5 if (accel.get(sym) or 0) >= 2 else 0)
                 + (5 if abs(ptm.get(sym) or 0) >= 0.10 else 0))
        proof = min(proof, 15)
        veto = _vetoes(sym, row, evs)
        swd = swmap.get(sym) or {}
        swp = swd.get("phase")
        # proven pullback structure adds conviction; a broken pivot
        # chain subtracts — same rule as the board
        sw_adj = (6 if swp == "confirmed" else 3 if swp == "higher_low"
                  else -8 if swp == "broken" else 0)
        conviction = round(cat_pts + setup_pts + proof + sw_adj, 1)
        entry = {
            "symbol": sym, "conviction": conviction,
            "catalyst": cat_label, "setup": setup_label,
            "swing_phase": swp,
            "swing_low": swd.get("swing_low"),
            "confirm_level": swd.get("confirm_level")
            if swp in ("higher_low", "confirmed") else None,
            "rs_pct": swd.get("rs_pct"),
            "cat_pts": round(cat_pts, 1), "setup_pts": setup_pts,
            "proof_pts": proof,
            "entry": row.get("entry"), "stop": row.get("stop"),
            "target": row.get("target"), "dd20": row.get("dd20"),
            "vs_spy20": row.get("vs_spy20"),
            "volume_ratio": row.get("volume_ratio"),
            "rsi2": row.get("rsi2"), "rb_tier": rb.get(sym),
            "in_portfolio": bool(row.get("in_portfolio")),
            "in_watchlist": bool(row.get("in_watchlist")),
            "size_mult": row.get("size_multiplier"),
        }
        if veto:
            entry["veto"] = veto
            vetoed.append(entry)
        else:
            swing.append(entry)
    swing.sort(key=lambda r: -r["conviction"])

    # --- lane B: breakout watch ---------------------------------------
    breakout = []
    for sym, row in screen.items():
        dd20 = row.get("dd20")
        vs = row.get("vs_spy20") or 0
        vol = row.get("volume_ratio") or 0
        near_high = dd20 is not None and dd20 >= BREAKOUT_PROXIMITY
        squeeze = bool(row.get("bb_squeeze"))
        pats = row.get("detected_patterns") or []
        if not (near_high or squeeze or "breakout" in pats
                or "breakout_retest" in pats):
            continue
        pts = 0.0
        if near_high:
            pts += 25 + (dd20 + BREAKOUT_PROXIMITY) * 300  # closer = more
        if squeeze:
            pts += 15
        if vol and vol >= 1.5:
            pts += 10
        if vs > 0:
            pts += min(15, vs * 100)
        if "breakout_retest" in pats:
            pts += 15
        elif "breakout" in pats:
            pts += 10
        if row.get("trend_turn_bars") is not None \
                and row["trend_turn_bars"] <= 8:
            pts += 8
        if row.get("falling_knife"):
            pts -= 40
        rb_bonus = 5 if rb.get(sym) in ("emerging", "confirmed") else 0
        breakout.append({
            "symbol": sym, "score": round(pts + rb_bonus, 1),
            "dd20": dd20, "vs_spy20": row.get("vs_spy20"),
            "volume_ratio": vol, "bb_squeeze": squeeze,
            "patterns": pats, "entry": row.get("entry"),
            "stop": row.get("stop"), "target": row.get("target"),
            "rb_tier": rb.get(sym),
            "in_portfolio": bool(row.get("in_portfolio")),
            "in_watchlist": bool(row.get("in_watchlist")),
            "has_catalyst": sym in events,
        })
    breakout.sort(key=lambda r: -r["score"])

    return {
        "swing": swing[:top_n], "breakout": breakout[:top_n],
        "vetoed": vetoed[:5],
        "candidates_considered": len(events),
        "screen_symbols": len(screen), "as_of": str(date.today()),
        "window_hours": hours,
    }


def persist_picks(edge: Optional[dict] = None) -> dict[str, Any]:
    """Persist today's board to daily_picks — the outcome loop."""
    from app.database import db
    edge = edge or compute_edge()
    today = date.today()
    written = 0
    for lane in ("swing", "breakout"):
        for rank, p in enumerate(edge.get(lane) or [], 1):
            db.execute_update(
                """
                INSERT INTO daily_picks
                    (pick_date, lane, rank, symbol, conviction, components,
                     entry, stop, target)
                VALUES (:d,:l,:r,:s,:c,CAST(:comp AS jsonb),:e,:st,:t)
                ON CONFLICT (pick_date, lane, symbol) DO UPDATE SET
                    rank=EXCLUDED.rank, conviction=EXCLUDED.conviction,
                    components=EXCLUDED.components, entry=EXCLUDED.entry,
                    stop=EXCLUDED.stop, target=EXCLUDED.target
                """,
                {"d": today, "l": lane, "r": rank, "s": p["symbol"],
                 "c": p.get("conviction") or p.get("score"),
                 "comp": json.dumps({k: v for k, v in p.items()
                                     if k not in ("symbol", "entry",
                                                  "stop", "target")}),
                 "e": p.get("entry"), "st": p.get("stop"),
                 "t": p.get("target")})
            written += 1
    return {"status": "persisted", "picks": written,
            "date": str(today)}
