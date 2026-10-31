"""Event-review — the standing 5-question deep review per symbol.

Trigger-driven (material events) + weekly cadence. Every run journals
a symbol_reviews row so each verdict is gradable later — same
accountability contract as the rest of the desk.

Deterministic throughout: the five answers are assembled from stored
evidence (alerts, tailwinds, doc claims, flywheel, SEC facts, estimate
snapshots, tape) and the verdict is a scoring rule — not an LLM
opinion. No score → verdict: 'insufficient', never invented.

  Q1 what changed      — events/claims/deltas since the last window
  Q2 how funded        — acq cash, dilution/splits, leverage, FCF
  Q3 future earnings   — revisions + estimate-curve drift only when
                         the evidence supports a change
  Q4 market recognizing— revision grade, RS/momentum, FV gap
  Q5 action            — accumulate | hold | trim | wait + reasons
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import date, timedelta
from typing import Any, Optional

logger = logging.getLogger(__name__)

_LOOKBACK_D = 30            # "what changed" window
_EST_LOOKBACK_D = 60        # estimate-drift compare horizon


def _q(sql: str, params: dict) -> list[dict]:
    """Query with soft-fail — a missing source table yields no
    evidence, never a crashed review."""
    from app.database import db
    try:
        return db.execute_query(sql, params)
    except Exception as exc:
        logger.debug("event_review q: %s", exc)
        return []


def _json(v):
    return json.loads(v) if isinstance(v, str) else (v or {})


def _f(x, nd=1):
    try:
        return float(x)
    except Exception:
        return None


def _b(x) -> str:
    return f"${x / 1e9:.1f}B" if x is not None else "—"


def _pct(x, nd=0) -> str:
    return f"{x * 100:.{nd}f}%" if x is not None else "—"


# ---------------------------------------------------------------- context

def _ctx(sym: str) -> dict[str, Any]:
    c: dict[str, Any] = {"symbol": sym}

    fly = _q("SELECT * FROM symbol_flywheel WHERE symbol=:s",
             {"s": sym})
    c["fly"] = dict(fly[0]) if fly else {}

    st = _q("SELECT fundamental_state, fundamental_risk,"
            " fundamental_detail, momentum_state, momentum_detail,"
            " revision_score, revision_grade, priced_status"
            " FROM stocks WHERE symbol=:s", {"s": sym})
    c["st"] = dict(st[0]) if st else {}
    c["fdet"] = _json(c["st"].get("fundamental_detail"))
    c["mdet"] = _json(c["st"].get("momentum_detail"))

    cut = str(date.today() - timedelta(days=_LOOKBACK_D))
    c["alerts"] = _q(
        "SELECT event_type, direction, materiality, title, created_at"
        " FROM alert_items WHERE symbol=:s"
        " AND created_at > CAST(:cut AS timestamptz)"
        " ORDER BY created_at DESC LIMIT 12",
        {"s": sym, "cut": cut})

    c["claims"] = _q(
        "SELECT title, claims, url FROM doc_analyses WHERE symbol=:s"
        " ORDER BY id DESC LIMIT 2", {"s": sym})

    c["watches"] = _q(
        "SELECT metric, threshold, status, direction, check_note"
        " FROM thesis_watches WHERE symbol=:s AND status != 'open'"
        " AND checked_at > CAST(:cut AS timestamptz)"
        " ORDER BY checked_at DESC LIMIT 8",
        {"s": sym, "cut": cut})

    sec = _q("SELECT * FROM symbol_sec_facts WHERE symbol=:s",
             {"s": sym})
    c["sec"] = dict(sec[0]) if sec else {}

    # estimate-curve drift — latest snapshot per forward period vs the
    # oldest within the lookback, same period_end basis
    est = _q(
        "SELECT DISTINCT ON (period_end) period_end, eps_avg, rev_avg,"
        " as_of FROM symbol_estimate_snapshots WHERE symbol=:s"
        " AND period_end > CAST(:cut AS date) ORDER BY period_end, as_of DESC",
        {"s": sym, "cut": str(date.today())})
    est_cut = str(date.today() - timedelta(days=_EST_LOOKBACK_D))
    c["est_drift"] = {}
    for row in est:
        pe = str(row["period_end"])
        old = _q(
            "SELECT eps_avg, rev_avg, as_of FROM"
            " symbol_estimate_snapshots WHERE symbol=:s AND"
            " period_end=:p AND as_of <= CAST(:cut AS date)"
            " ORDER BY as_of DESC LIMIT 1",
            {"s": sym, "p": pe, "cut": est_cut})
        if old and old[0].get("eps_avg") and row.get("eps_avg"):
            try:
                d = float(row["eps_avg"]) / float(old[0]["eps_avg"]) - 1
                if abs(d) > 0.005:
                    c["est_drift"][pe] = round(d, 4)
            except Exception:
                pass

    fv = _q("SELECT fair_value, scenario_fair_values, as_of"
            " FROM fair_value_v2_runs WHERE symbol=:s"
            " ORDER BY as_of DESC LIMIT 1", {"s": sym})
    c["fv"] = dict(fv[0]) if fv else {}

    try:
        th = _q("SELECT archetype, status, score, hypotheses, vetoes"
                " FROM symbol_thesis WHERE symbol=:s", {"s": sym})
        c["thesis"] = dict(th[0]) if th else {}
    except Exception:
        c["thesis"] = {}

    spot = _q("SELECT close FROM daily_bars WHERE symbol=:s"
              " ORDER BY date DESC LIMIT 1", {"s": sym})
    c["spot"] = _f(spot[0]["close"]) if spot else None
    return c


# ---------------------------------------------------------------- answers

def _q1(c: dict) -> dict:
    """What changed — events, claims, deltas in the lookback window."""
    lines, facts = [], []
    for a in c["alerts"][:6]:
        lines.append(f"{a['event_type']}: {a['title']}")
        facts.append({"type": a["event_type"],
                      "dir": a["direction"],
                      "mat": a["materiality"]})
    for doc in c["claims"]:
        for cl in (_json(doc.get("claims")) or [])[:6]:
            if cl.get("type") in ("fact", "risk", "channel"):
                lines.append(f"{cl['type']}: {str(cl.get('text'))[:110]}")
    changes = c["fdet"].get("changes") or []
    for ch in changes[:4]:
        lines.append(f"metric: {ch}")
    sec = c["sec"]
    if sec.get("split_suspect"):
        lines.append(f"share-count step {sec.get('shares_step_ratio')}×"
                     " — split; per-share history on mixed basis")
    if sec.get("acq_spend_fy"):
        lines.append(f"M&A cash spend {_b(_f(sec['acq_spend_fy']))}"
                     " latest fiscal year")
    rpo, rpy = _f(sec.get("rpo")), _f(sec.get("rpo_yoy"))
    if rpo:
        line = f"backlog (RPO) {_b(rpo)}"
        if rpy is not None:
            line += f" ({rpy * 100:+.0f}% YoY)"
        cs = _f(sec.get("crpo_share"))
        if cs is not None:
            line += f" — {cs * 100:.0f}% due within 12m"
        lines.append(line)
    dy = _f(sec.get("def_rev_yoy"))
    if dy is not None and abs(dy) >= 0.05:
        lines.append(f"deferred revenue {dy * 100:+.0f}% YoY"
                     + (" — billings softening" if dy < 0
                        else " — billings building"))
    if not lines:
        lines.append("no material changes detected in window")
    return {"lines": lines[:10], "facts": {"alerts": facts}}


def _q2(c: dict) -> dict:
    """How was it funded — cash vs dilution vs debt, and cash quality."""
    fly, sec = c["fly"], c["sec"]
    lines = []
    acq_ttm = _f(fly.get("acq_spend_ttm"))
    acq_fy = _f(sec.get("acq_spend_fy"))
    if acq_ttm and acq_ttm > 0:
        lines.append(f"acquisitions cash-funded {_b(acq_ttm)} TTM"
                     f" ({_pct(_f(fly.get('acq_rev_pct')))} of revenue)")
    elif acq_fy:
        lines.append(f"acquisitions {_b(acq_fy)} latest FY")
    else:
        lines.append("no material M&A spend — growth is self-funded")
    if sec.get("split_suspect"):
        lines.append(f"share count stepped {sec.get('shares_step_ratio')}"
                     "× — corporate action, not issuance")
    nde = _f(fly.get("net_debt_ebitda"))
    if nde is not None:
        lines.append(f"leverage {nde:.1f}× net-debt/EBITDA")
    fcf = _f(fly.get("fcf_ttm"))
    if fcf is not None:
        lines.append(f"FCF {_b(fcf)} TTM"
                     + (f" ({_pct(_f(fly.get('fcf_margin')))} margin)"
                        if _f(fly.get("fcf_margin")) else ""))
    gw = _f(sec.get("goodwill_assets_pct"))
    if gw and gw > 0.10:
        lines.append(f"goodwill {gw * 100:.0f}% of assets — past-deal"
                     " residue, watch impairment on misses")
    gwi = _f(sec.get("gw_impair_fy"))
    if gwi and gwi > 0:
        lines.append(f"goodwill impairment {_b(gwi)} latest FY — a"
                     " prior deal already wrote off")
    return {"lines": lines,
            "facts": {"acq_ttm": acq_ttm, "fcf_ttm": fcf,
                      "net_debt_ebitda": nde,
                      "goodwill_pct": gw}}


def _q3(c: dict) -> dict:
    """Future earnings — does the evidence support an outlook change?
    Threshold is |drift|>5% on the estimate curve or |revision|>2%."""
    fly = c["fly"]
    er = _f(fly.get("est_revision_pct"))
    rb = _f(fly.get("rev_breadth_30d"))
    drift = c["est_drift"]
    lines = []
    if er is not None:
        lines.append(f"street revisions {er * 100:+.1f}% (90d)")
    for pe, d in sorted(drift.items()):
        lines.append(f"est {pe}: {d * 100:+.1f}% vs 60d ago")
    if rb is not None:
        lines.append(f"revision breadth {rb:+.0f} (30d up−down)")
    epc = c["fdet"].get("eps_cause")
    if epc:
        lines.append(f"eps cause: {epc}")
    th = c.get("thesis") or {}
    if th.get("status"):
        lines.append(f"thesis ({th.get('archetype')}): {th['status']}"
                     f" score {th.get('score')}")
    # disclosed organic growth — when the company states it (8-K/press
    # release → doc_extract fact claims), compare vs reported total
    for doc in c["claims"]:
        for cl in (_json(doc.get("claims")) or []):
            met = str(cl.get("metric") or "").lower()
            if "organic" in met and isinstance(
                    cl.get("value"), (int, float)):
                rg = _f(fly.get("rev_growth"))
                v = cl["value"]
                vv = v / 100 if abs(v) > 3 else v
                gap = f" vs reported {rg * 100:+.0f}%" \
                    if rg is not None else ""
                lines.append(f"disclosed organic growth ~{vv * 100:.0f}%"
                             f"{gap} — acq share ≈ the difference")
    outlook = "unchanged"
    worst = min(drift.values()) if drift else 0
    best = max(drift.values()) if drift else 0
    if best > 0.05 or (er is not None and er > 0.05):
        outlook = "improving — evidence supports raising the outer-year"
    elif worst < -0.05 or (er is not None and er < -0.05):
        outlook = "weakening — evidence supports cutting the outer-year"
    lines.append(f"outlook: {outlook}")
    return {"lines": lines, "facts": {"est_revision": er,
                                      "drift": drift,
                                      "outlook": outlook}}


def _q4(c: dict) -> dict:
    """Is the market recognizing it — revisions grade, RS, valuation."""
    st, mdet, fly = c["st"], c["mdet"], c["fly"]
    lines = []
    if st.get("revision_grade"):
        lines.append(f"revision grade {st['revision_grade']}"
                     + (f" ({st['revision_score']:.0f})"
                        if st.get("revision_score") else ""))
    ms = st.get("momentum_state")
    if ms:
        lines.append(f"tape {ms.replace('_', ' ')}")
    rs = _f(mdet.get("rs_pct"))
    if rs is not None:
        lines.append(f"relative strength {rs:+.0f} vs QQQ")
    pe = _f(fly.get("fwd_pe"))
    if pe:
        lines.append(f"fwd P/E {pe:.0f}×")
    fv = c["fv"]
    fvv = _f(fv.get("fair_value"))
    if fvv and c["spot"]:
        up = fvv / c["spot"] - 1
        lines.append(f"FV ${_f(fvv):.0f} vs spot ${c['spot']:.0f}"
                     f" → {up * 100:+.0f}%")
        c["fv_upside"] = up
    return {"lines": lines,
            "facts": {"revision_grade": st.get("revision_grade"),
                      "momentum": ms, "rs_pct": rs,
                      "fv_upside": c.get("fv_upside")}}


def _verdict(c: dict, a: dict) -> tuple[str, float, list[str]]:
    """Evidence balance → accumulate|hold|trim|wait|insufficient.
    Deterministic: the score IS the verdict; reasons are the legs."""
    st, fly = c["st"], c["fly"]
    state = st.get("fundamental_state")
    if not fly or (state is None and not c["alerts"]
                   and not c["claims"]):
        return "insufficient", 0.0, ["no fundamentals evidence on file"]

    s, reasons, flags = 0.0, [], []

    def add(pts: float, why: str):
        nonlocal s
        s += pts
        reasons.append(f"{pts:+g} {why}")

    if state in ("accelerating", "growing"):
        add(2, f"fundamentals {state}")
    elif state in ("declining", "slowing"):
        add(-2, f"fundamentals {state}")

    er = _f(fly.get("est_revision_pct"))
    if er is not None and abs(er) <= 1.0:
        if er > 0.02:
            add(1, f"revisions {er * 100:+.0f}%")
        elif er < -0.02:
            add(-1, f"revisions {er * 100:+.0f}%")
    rb = _f(fly.get("rev_breadth_30d"))
    if rb is not None:
        if rb >= 2:
            add(1, f"breadth {rb:+.0f}")
        elif rb <= -2:
            add(-1, f"breadth {rb:+.0f}")
    bs = fly.get("beat_streak")
    if bs and int(bs) >= 3:
        add(1, f"{bs}q beat streak")
    elif bs is not None and int(bs) <= 0:
        add(-1, "no recent beat")

    if _f(fly.get("fcf_ttm")) is not None:
        if _f(fly["fcf_ttm"]) > 0 and (_f(fly.get("fcf_margin")) or 0) \
                > 0.15:
            add(1, "FCF margin >15%")
        elif _f(fly["fcf_ttm"]) < 0:
            add(-1, "FCF negative")

    # thesis layer — the archetype-scoped "is the upside case
    # progressing" read; a broken standing thesis is a hard leg, not a
    # caution (persistent hard-check failure, by definition)
    th = c.get("thesis") or {}
    if th.get("status") in ("on_track", "improving"):
        add(1, f"thesis {th['status']}")
    elif th.get("status") == "deteriorating":
        add(-1, "thesis deteriorating")
    elif th.get("status") == "severely_deteriorating":
        add(-1.5, "core thesis leg failed — under review")
    elif th.get("status") == "broken":
        add(-2, "thesis broken")
        flags.append("standing thesis broken — a hard check failed")

    for w in c["watches"]:
        if w["status"] == "refuted":
            add(-1, f"watch refuted: {w['metric'][:50]}")
        elif w["status"] == "confirmed" and s < 4:
            add(1, f"watch confirmed: {w['metric'][:50]}")

    up = c.get("fv_upside")
    if up is not None:
        if up > 0.15:
            add(1, f"{up * 100:+.0f}% vs FV")
        elif up < -0.20:
            add(-1, f"{up * 100:+.0f}% vs FV — priced ahead of value")

    # caution flags — they don't score, they gate 'accumulate' to 'wait'
    if c["sec"].get("split_suspect"):
        flags.append("share-count step — verify per-share basis")
    if (_f(fly.get("acq_rev_pct")) or 0) > 0.10:
        flags.append("M&A spend >10% of rev — organic share unverifiable")
    if a["q3"]["facts"].get("outlook", "").startswith("weakening"):
        flags.append("outlook evidence weakening")

    if s >= 3 and not flags:
        return "accumulate", s, reasons
    if s >= 3:
        return "wait", s, reasons + [f"flag: {f}" for f in flags]
    if s <= -3:
        return "trim", s, reasons + [f"flag: {f}" for f in flags]
    if s <= -1:
        return "hold", s, reasons + [f"flag: {f}" for f in flags]
    return "hold", s, reasons + ["no decisive evidence either way"]


# ---------------------------------------------------------------- run

def ensure_table() -> None:
    from app.database import db
    db.execute_update(
        "CREATE TABLE IF NOT EXISTS symbol_reviews ("
        " id BIGSERIAL PRIMARY KEY, symbol TEXT NOT NULL,"
        " as_of TIMESTAMPTZ NOT NULL DEFAULT now(),"
        " trigger TEXT NOT NULL, verdict TEXT NOT NULL,"
        " score NUMERIC, answers JSONB NOT NULL, reasons JSONB,"
        " run_id TEXT)")


def review(sym: str, trigger: str = "manual") -> dict[str, Any]:
    """Full 5-question review → journaled row → the answers dict."""
    from app.database import db
    sym = sym.upper().strip()
    ensure_table()
    c = _ctx(sym)
    answers = {"q1": _q1(c), "q2": _q2(c), "q3": _q3(c), "q4": _q4(c)}
    verdict, score, reasons = _verdict(c, answers)
    answers["q5"] = {"verdict": verdict, "score": score,
                     "reasons": reasons}
    run_id = uuid.uuid4().hex[:12]
    db.execute_update(
        "INSERT INTO symbol_reviews (symbol, trigger, verdict, score,"
        " answers, reasons, run_id) VALUES"
        " (:s,:t,:v,:sc,CAST(:a AS jsonb),CAST(:r AS jsonb),:rid)",
        {"s": sym, "t": trigger, "v": verdict, "sc": score,
         "a": json.dumps(answers, default=str),
         "r": json.dumps(reasons), "rid": run_id})
    return {"symbol": sym, "trigger": trigger, "verdict": verdict,
            "score": score, "reasons": reasons, "answers": answers}


def run_universe(symbols: list[str]) -> dict[str, Any]:
    """Weekly pass — deterministic only, journaled per symbol."""
    ensure_table()
    done, errs = 0, []
    for sym in symbols:
        try:
            review(sym, trigger="weekly")
            done += 1
        except Exception as exc:
            errs.append(f"{sym}: {exc}")
            if len(errs) >= 10:
                break
    return {"symbols": len(symbols), "reviewed": done, "errors": errs}


def maybe_review(sym: str, trigger: str,
                 min_gap_h: float = 20) -> Optional[dict]:
    """Event-triggered entry — dedupe so a burst of alerts on one name
    doesn't journal five identical reviews. Returns the review or
    None when a recent one already covers it."""
    from app.database import db
    r = db.execute_query(
        "SELECT as_of FROM symbol_reviews WHERE symbol=:s"
        " ORDER BY as_of DESC LIMIT 1", {"s": sym})
    if r:
        from datetime import datetime, timezone
        try:
            age_h = (datetime.now(timezone.utc)
                     - r[0]["as_of"]).total_seconds() / 3600
            if age_h < min_gap_h:
                return None
        except Exception:
            pass
    try:
        return review(sym, trigger=trigger)
    except Exception as exc:
        logger.debug("event_review %s %s: %s", sym, trigger, exc)
        return None


def latest(sym: str) -> Optional[dict]:
    """Card surface — newest journaled review."""
    r = _q("SELECT as_of, trigger, verdict, score, answers, reasons"
           " FROM symbol_reviews WHERE symbol=:s"
           " ORDER BY as_of DESC LIMIT 1", {"s": sym})
    if not r:
        return None
    row = dict(r[0])
    row["as_of"] = str(row["as_of"])[:19]
    row["answers"] = _json(row["answers"])
    row["reasons"] = _json(row["reasons"])
    return row
