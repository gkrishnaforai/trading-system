"""Trade plans — the human-in-the-loop exit journal.

A plan binds a recorded entry (px/date/use_case) to the engine's
levels at that moment: structure stop, R-targets, trail rule, time
stop. Status is computed live from stored engine state through the
`plan_status` section of pulse_action_rules.yaml — the same `_cond`
interpreter, first-match-wins, full journaling. Direction and
plan-relative arithmetic (R multiples, level distances, days in
trade) are normalized into ctx booleans here so the rule language
stays declarative.

Transitions journal into trade_plan_events = the alert feed.
The system flags; the human decides and closes the plan.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from app.signals import pulse_engine

_USE_DEFAULTS = {
    # (trail_rule, time_stop_days, direction)
    "swing":     ("hl_ratchet", 15, "long"),
    "invest":    ("ema50", 60, "long"),
    "leap_call": ("hl_ratchet", 60, "long"),
    "leap_put":  ("hl_ratchet", 60, "short"),
}


def _stored(sym: str) -> dict:
    """The per-symbol slice of the pulse board query — same joins,
    same fields, scoped to one symbol. Kept in lockstep with
    board_api.portfolio_pulse's SELECT."""
    from app.database import db
    rows = db.execute_query("""
        SELECT s.symbol, s.momentum_state, s.momentum_detail,
               s.fundamental_state, s.revision_grade, s.priced_status,
               s.next_earnings_date, s.momentum_updated_at,
               s.fundamental_updated_at,
               CASE
                 WHEN fp.is_etf IS NOT NULL THEN fp.is_etf
                 WHEN s.industry ILIKE 'Asset Management%%'
                      OR s.company_name ~* '\\m(ETF|Fund|Trust)\\M'
                   THEN true
                 WHEN s.company_name IS NOT NULL
                      OR s.industry IS NOT NULL
                   THEN false
                 ELSE NULL END AS is_etf,
               COALESCE(s.sector, fp.sector) AS sector,
               fv.expected_fair_value,
               gq.flags AS gq_flags, gq.score AS gq_score,
               fw.fwd_pe, fw.num_analysts,
               fw.updated_at AS flywheel_at,
               fw.rev_growth, fw.eps_growth,
               prev.state AS prev_state,
               px.close AS close
        FROM stocks s
        LEFT JOIN fmp_company_profiles fp ON fp.symbol = s.symbol
        LEFT JOIN LATERAL (
            SELECT close FROM daily_bars b
            WHERE b.symbol = s.symbol
            ORDER BY b.date DESC LIMIT 1) px ON true
        LEFT JOIN LATERAL (
            SELECT expected_fair_value FROM fair_value_v2_runs f
            WHERE f.symbol = s.symbol
            ORDER BY f.as_of DESC, f.run_id DESC LIMIT 1) fv ON true
        LEFT JOIN LATERAL (
            SELECT score, flags FROM growth_quality_runs g
            WHERE g.symbol = s.symbol
            ORDER BY g.as_of DESC, g.id DESC LIMIT 1) gq ON true
        LEFT JOIN LATERAL (
            SELECT state FROM momentum_state_log l
            WHERE l.symbol = s.symbol AND l.as_of < CURRENT_DATE
            ORDER BY l.as_of DESC LIMIT 1) prev ON true
        LEFT JOIN symbol_flywheel fw ON fw.symbol = s.symbol
        WHERE s.symbol = :s""", {"s": sym})
    return dict(rows[0]) if rows else {"symbol": sym}


def _age(ts) -> Optional[int]:
    if ts is None:
        return None
    try:
        d = ts.date() if isinstance(ts, datetime) else ts
        return (date.today() - d).days
    except Exception:
        return None


def _live(sym: str) -> dict:
    """Live ctx for plan evaluation: spot, tape, dip structure, and
    the same pulse_engine verdict the board computes — one source of
    truth for 'has the thesis died'."""
    import json
    r = _stored(sym)
    det = r.get("momentum_detail") or {}
    if isinstance(det, str):
        det = json.loads(det)
    px, fv = r.get("close"), r.get("expected_fair_value")
    fv_up = (float(fv) / float(px) - 1) * 100 if fv and px else None
    # pulse eval — same adapter contract as board_api._pulse_action_eval
    _rank = {"knife": 0, "capitulation": 1, "breakdown": 2, "downtrend": 3,
             "basing": 4, "stabilizing": 5, "recovery": 6, "pullback": 7,
             "uptrend": 8, "breakout": 9, "climax": 10, "rolling_over": 3}
    mom, prev = r.get("momentum_state"), r.get("prev_state")
    cur, prv = _rank.get(mom, -1), _rank.get(prev)
    tape_dir = ("improving" if prv is not None and cur > prv else
                "degrading" if prv is not None and cur < prv else
                "flat" if prv is not None else None)
    ne = r.get("next_earnings_date")
    earn_days = ((ne.date() if hasattr(ne, "date") else ne)
                 - date.today()).days if ne else None
    ev = pulse_engine.evaluate({
        "mom_state": mom, "tape_dir": tape_dir,
        "fund_state": r.get("fundamental_state"),
        "revision_grade": r.get("revision_grade"),
        "priced_status": r.get("priced_status"),
        "fv_upside": fv_up,
        "rsi": det.get("rsi"), "vs_sma50": det.get("vs_sma50"),
        "momentum_detail": det, "earn_days": earn_days,
        "num_analysts": r.get("num_analysts"),
        "flywheel_age_days": _age(r.get("flywheel_at")),
        "momentum_age_days": _age(r.get("momentum_updated_at")),
        "gq_flags": r.get("gq_flags") or [],
        "is_etf": r.get("is_etf"), "sector": r.get("sector"),
        "fwd_pe": r.get("fwd_pe"),
    })
    return {"px": float(px) if px else None, "det": det,
            "mom": mom, "dip_phase": det.get("dip_phase"),
            "pulse_action": ev["action"],
            "pulse_rule": ev["matched_rule"],
            "row": r}


# ---------------- the suggestion engine ----------------------------------

def suggest(sym: str, use_case: str,
            entry_px: Optional[float] = None) -> dict:
    """Engine-proposed plan from stored structure. Structure stop =
    the swing low that defines the setup (else prior low, else 2×ATR);
    targets are R-multiples off that risk. Every field is a suggestion
    the user can override before saving."""
    live = _live(sym.upper())
    det, sw = live["det"], (live["det"].get("swing") or {})
    atr_pct = det.get("atr_pct")
    px = entry_px or live["px"]
    trail, ts_days, direction = _USE_DEFAULTS.get(
        use_case, _USE_DEFAULTS["swing"])

    stop = basis = None
    if direction == "long":
        for k, b in (("swing_low", "swing_low"),
                     ("prior_low", "prior_low")):
            if sw.get(k):
                stop, basis = float(sw[k]), b
                break
        if stop is None and px and atr_pct:
            stop, basis = round(px * (1 - 2 * atr_pct), 2), "atr2"
        elif stop is None and px:
            stop, basis = round(px * 0.92, 2), "pct"
    else:  # leap_put — the stop is the level that invalidates the short
        if sw.get("confirm_level"):
            stop, basis = float(sw["confirm_level"]), "confirm_level"
        elif px and atr_pct:
            stop, basis = round(px * (1 + 2 * atr_pct), 2), "atr2"
        elif px and px is not None:
            stop, basis = round(px * 1.08, 2), "pct"

    t1 = t2 = None
    if px and stop:
        risk = abs(px - stop)
        if risk > 0:
            sgn = 1 if direction == "long" else -1
            t1 = round(px + sgn * 1.5 * risk, 2)
            t2 = round(px + sgn * 2.0 * risk, 2)
            if use_case == "invest":  # long-hold: no hard targets
                t1 = t2 = None
    return {"symbol": sym.upper(), "use_case": use_case,
            "direction": direction, "entry_px": px,
            "spot": live["px"], "stop_px": stop, "stop_basis": basis,
            "target1_px": t1, "target2_px": t2,
            "trail_rule": trail, "time_stop_days": ts_days,
            "mom": live["mom"], "dip_phase": live["dip_phase"],
            "pulse_action": live["pulse_action"],
            "confirm_level": sw.get("confirm_level"),
            "swing_low": sw.get("swing_low"),
            "prior_low": sw.get("prior_low")}


# ---------------- the status evaluator ------------------------------------

def _ctx(plan: dict, live: dict) -> dict:
    """Plan + live state → normalized booleans for the YAML rules.
    Direction collapses long/short into `risk_hit`/`t1_hit`/`t2_hit`
    so rules stay direction-agnostic."""
    px = live["px"]
    entry = float(plan["entry_px"])
    stop = float(plan["stop_px"]) if plan.get("stop_px") else None
    t1 = float(plan["target1_px"]) if plan.get("target1_px") else None
    t2 = float(plan["target2_px"]) if plan.get("target2_px") else None
    short = plan.get("direction") == "short"
    sgn = -1 if short else 1
    risk = abs(entry - stop) if stop else None
    sw = (live["det"].get("swing") or {})

    risk_hit = (px is not None and stop is not None
                and (px <= stop if not short else px >= stop))
    t1_hit = (px is not None and t1 is not None
              and (px >= t1 if not short else px <= t1))
    t2_hit = (px is not None and t2 is not None
              and (px >= t2 if not short else px <= t2))
    days = (date.today() - plan["entry_date"]).days \
        if isinstance(plan.get("entry_date"), date) else None
    ts = plan.get("time_stop_days")
    dip = live["dip_phase"]
    stalled = bool(days is not None and ts is not None
                   and days >= ts and dip != "confirmed" and not t1_hit)
    # trail opportunity: the structure printed a NEW protective level
    # beyond the plan stop — for longs a higher swing_low, for shorts
    # a lower confirm/swing high. Only meaningful after entry.
    trail_to = None
    if not short and sw.get("swing_low") and stop \
            and float(sw["swing_low"]) > stop and not t1_hit:
        trail_to = float(sw["swing_low"])
    if short and sw.get("confirm_level") and stop \
            and float(sw["confirm_level"]) < stop and not t1_hit:
        trail_to = float(sw["confirm_level"])
    r = None
    if px is not None and risk and risk > 0:
        r = round((px - entry) * sgn / risk, 2)
    dist_stop = (round((px - stop) * sgn / px * 100, 1)
                 if px and stop else None)
    return {"px": px, "stop": stop, "t1": t1, "t2": t2,
            "risk_hit": risk_hit, "t1_hit": t1_hit, "t2_hit": t2_hit,
            "stalled": stalled, "trail_up": trail_to is not None,
            "trail_to": trail_to, "days": days, "r": r,
            "dist_stop": dist_stop, "dip_phase": dip,
            "mom": live["mom"], "pulse_action": live["pulse_action"],
            "pulse_rule": live["pulse_rule"],
            "use_case": plan.get("use_case")}


def _fmt_plan(why: str, c: dict) -> str:
    def _p(k, sfx=""):
        return f"{c[k]:.2f}{sfx}" if c.get(k) is not None else "—"
    vals = {k: (c.get(k) if c.get(k) is not None else "—")
            for k in ("pulse_action", "pulse_rule", "dip_phase", "mom",
                      "days", "r", "dist_stop", "trail_to")}
    vals.update({"stop": _p("stop"), "t1": _p("t1"), "t2": _p("t2"),
                 "px": _p("px")})
    try:
        return why.format_map(vals)
    except Exception:
        return why


def _match(c: dict) -> dict:
    """Ctx → first-matching plan_status rule. Pure — the unit-test
    surface; eval_plan wraps it with live data + journaling."""
    for rule in pulse_engine._load().get("plan_status") or []:
        if pulse_engine._eval_when(c, rule.get("when"))[0]:
            return {"status": rule["status"], "matched": rule["name"],
                    "action_hint": rule.get("action_hint"),
                    "why": _fmt_plan(rule.get("why") or "", c)}
    return {"status": "on_track", "matched": None,
            "action_hint": "hold", "why": "no rules configured"}


def eval_plan(plan: dict, live: Optional[dict] = None) -> dict:
    """One plan → YAML plan_status verdict. Journals a
    trade_plan_events row on every status TRANSITION (first write of
    the day per kind wins) — that's the alert feed."""
    live = live or _live(plan["symbol"])
    c = _ctx(plan, live)
    out = {**_match(c), "plan_id": plan["id"], "ctx": c}
    _journal(plan, out)
    return out


def _journal(plan: dict, ev: dict) -> None:
    """Transitions only — same status re-computed all day journals
    once (UNIQUE plan+day+kind)."""
    from app.database import db
    import json
    kind = ev["status"]
    if kind == "on_track" and plan.get("last_status") in (None, "on_track"):
        return                          # opening state + steady state
                                        # are not alerts; a RETURN to
                                        # on_track after a flag is
    try:
        db.execute_update(
            "INSERT INTO trade_plan_events"
            " (plan_id, symbol, as_of, kind, action_hint, message, ctx)"
            " VALUES (:p, :s, CURRENT_DATE, :k, :a, :m,"
            "         CAST(:c AS jsonb))"
            " ON CONFLICT (plan_id, as_of, kind) DO NOTHING",
            {"p": plan["id"], "s": plan["symbol"], "k": kind,
             "a": ev["action_hint"], "m": ev["why"],
             "c": json.dumps(ev["ctx"], default=str)})
        db.execute_update(
            "UPDATE trade_plans SET last_status=:k WHERE id=:p",
            {"k": kind, "p": plan["id"]})
    except Exception:
        pass


def open_plans() -> list[dict]:
    """Every open plan with its live verdict — the board payload."""
    from app.database import db
    plans = [dict(r) for r in db.execute_query(
        "SELECT * FROM trade_plans WHERE status='open'"
        " ORDER BY created_at DESC")]
    live_cache: dict[str, dict] = {}
    for p in plans:
        s = p["symbol"]
        if s not in live_cache:
            live_cache[s] = _live(s)
        ev = eval_plan(p, live_cache[s])
        p.update({"eval": {k: v for k, v in ev.items() if k != "ctx"},
                  "px": ev["ctx"]["px"], "r": ev["ctx"]["r"],
                  "days": ev["ctx"]["days"],
                  "dist_stop": ev["ctx"]["dist_stop"]})
    return plans


# ---------------- email digest ----------------------------------------------

def _send(to: str, subject: str, lines: list[str]) -> dict:
    """Plain smtplib send — same SMTP_* env as notification_service.
    Sync by design (digest runs in a worker thread, no event loop)."""
    import os
    import smtplib
    from email.mime.text import MIMEText
    user, pw = os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD")
    # Google displays app passwords as 'xxxx xxxx xxxx xxxx' — pasted
    # verbatim the spaces break the login (server drops the session)
    pw = pw.replace(" ", "") if pw else pw
    if not (user and pw):
        return {"ok": False, "error": "SMTP not configured"}
    msg = MIMEText("\n".join(lines), "plain")
    msg["Subject"], msg["From"], msg["To"] = subject, user, to
    try:
        with smtplib.SMTP(os.getenv("SMTP_HOST", "smtp.gmail.com"),
                          int(os.getenv("SMTP_PORT", "587")),
                          timeout=20) as s:
            s.starttls()
            s.login(user, pw)
            s.send_message(msg)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def email_test(to: Optional[str] = None) -> dict:
    """Deliverability check — one test email to the recipient."""
    import os
    to = to or os.getenv("ALERT_EMAIL") or os.getenv("SMTP_USER")
    return _send(to, "trading-system — email alerts OK",
                 ["Email alerts are wired.",
                  "Trade-plan status transitions will land here as a",
                  "batched digest. No action needed."])


def email_digest() -> dict:
    """The alert loop: re-evaluate every open plan (journals fresh
    transitions), sweep unseen events into ONE digest email, mark
    them seen. Scheduler calls this on a cadence — cheap when no
    plans, quiet when nothing changed."""
    import os
    from app.database import db
    try:
        open_plans()                      # eval + journal transitions
    except Exception as e:
        return {"ok": False, "error": f"eval failed: {e}"}
    rows = db.execute_query(
        "SELECT id, symbol, kind, action_hint, message, as_of"
        " FROM trade_plan_events WHERE NOT seen"
        " ORDER BY created_at")
    if not rows:
        return {"ok": True, "emailed": 0, "events": 0}
    to = os.getenv("ALERT_EMAIL") or os.getenv("SMTP_USER")
    lines = [f"{len(rows)} trade-plan alert(s):", ""]
    for e in rows:
        lines.append(f"• {e['symbol']} — `{e['kind']}` "
                     f"→ {e.get('action_hint') or ''}")
        if e.get("message"):
            lines.append(f"    {e['message']}")
    lines += ["", "— advisory. Review on the Trade Plans page; "
              "the decision is yours."]
    res = _send(to, f"[trade-plans] {len(rows)} alert(s) — "
                    f"{', '.join(sorted({r['symbol'] for r in rows}))}",
                lines)
    if res.get("ok"):
        ids = ",".join(str(r["id"]) for r in rows)
        db.execute_update(f"UPDATE trade_plan_events SET seen=true"
                          f" WHERE id IN ({ids})")
    return {"ok": res.get("ok"), "emailed": len(rows) if res.get("ok")
            else 0, "events": len(rows), "to": to,
            "error": res.get("error")}
