"""thesis_health — archetype-scoped upside tracking.

Answers "is THIS name's specific upside case getting stronger" — not
"is the company good." Each archetype (archetype_checklists.yaml)
carries standing hypotheses with falsifiable metric checks sourced
from the flywheel, SEC facts, or extracted doc KPIs. Statuses roll up
into symbol_thesis; every check also materializes as a thesis_watches
row so the existing check_watches() grader and review surfaces stay
the single journal — no parallel tracker.

Status vocabulary (controlled, per the design):
  on_track               all checks pass
  improving              evidence moving the right way (pass + evidence mix)
  mixed                  some pass, some weaken
  deteriorating          a check failed
  severely_deteriorating a CORE hypothesis's hard check failed — the
                         load-bearing operating requirement is missing,
                         triggering review rather than impairment
  broken                 structural impairment — a hard check failed
                         across ≥2 DISTINCT reporting periods WITH
                         corroboration, or a fatal veto fired. One bad
                         print can never break a thesis.
  unknown                data missing — never treated as neutral or positive

Failure semantics:
  - hard check fail, 1st period    → hypothesis deteriorating (warning)
  - hard check fail, ≥2 periods    → severely_deteriorating
  - hard fail ≥2 + corroboration   → broken (another leg failing too)
  - hypothesis criticality: 'core' failures can break the symbol;
    'optional' failures cap the symbol at deteriorating, never broken
  - recovery: a broken status can't heal while the broken leg still
    fails; once healed it sits in a 30d review window before improving
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger(__name__)

_CFG: Optional[dict] = None

# 'improving' resolves against a companion trend field when one exists
# on the flywheel — same data the classifier already trusts
_TREND_OF = {
    "fcf_ttm": "fcf_growth",
    "rev_growth": "rev_accel",
    "rev_accel": None,
    "om_now": "om_slope",
    "gm_now": "gm_slope",
}

_RANK = {"broken": 0, "severely_deteriorating": 1, "deteriorating": 2,
         "mixed": 3, "improving": 4, "on_track": 5, "unknown": -1}
_SCORE = {"on_track": 2, "improving": 1, "mixed": 0, "unknown": 0,
          "deteriorating": -1, "severely_deteriorating": -2,
          "broken": -2}

# a value change <30d after the streak last moved is a data refresh,
# not a new print — fundamentals publish ~quarterly
_MIN_PERIOD_GAP_DAYS = 30
# below this share of answered core checks no full grade is claimed
_CORE_COVERAGE_BAR = 0.70
# days a healed break stays capped at 'deteriorating' under review
_RECOVERY_REVIEW_DAYS = 30


def _cfg() -> dict:
    global _CFG
    if _CFG is None:
        _CFG = yaml.safe_load(
            Path(__file__).with_name("archetype_checklists.yaml")
            .read_text())
    return _CFG


def archetypes_for(sym: str, sector: str = "",
                   industry: str = "") -> list[str]:
    """symbol override → sector/industry rules → 'generic'."""
    cfg = _cfg()
    ovr = (cfg.get("symbols") or {}).get(sym.upper())
    if ovr:
        return list(ovr) if isinstance(ovr, list) else [ovr]
    ind, sec = (industry or "").lower(), (sector or "").lower()
    for r in cfg.get("archetype_rules") or []:
        w = r.get("when") or {}
        ind_ok = (not w.get("industry_contains")
                  or any(n in ind for n in w["industry_contains"]))
        sec_ok = (not w.get("sector_contains")
                  or any(n in sec for n in w["sector_contains"]))
        if ind_ok and sec_ok:
            return [r["archetype"]]
    return ["generic"]


def _flywheel(sym: str) -> dict:
    from app.database import db
    r = db.execute_query(
        "SELECT * FROM symbol_flywheel WHERE symbol=:s", {"s": sym})
    return dict(r[0]) if r else {}


def _sec(sym: str) -> dict:
    from app.database import db
    r = db.execute_query(
        "SELECT * FROM symbol_sec_facts WHERE symbol=:s", {"s": sym})
    return dict(r[0]) if r else {}


def _doc_kpi(sym: str, kpi: str) -> dict:
    """Latest extracted claim matching the KPI name → {value, period,
    quote} or {}. Company-defined KPIs (NRR, GMV, utilization) only
    exist via doc_extract — verbatim-grounded or absent."""
    from app.database import db
    import re as _re
    rows = db.execute_query(
        "SELECT claims, created_at FROM doc_analyses WHERE symbol=:s"
        " ORDER BY created_at DESC LIMIT 5", {"s": sym})
    want = _re.sub(r"\s+", " ", kpi.lower().replace("_", " ")).strip()
    for r in rows:
        import json
        claims = r.get("claims")
        claims = json.loads(claims) if isinstance(claims, str) \
            else (claims or [])
        for c in claims:
            met = _re.sub(r"\s+", " ",
                          str(c.get("metric") or "").lower()).strip()
            if want in met or met in want:
                return {"value": c.get("value"),
                        "period": c.get("period"),
                        "as_of": str(r.get("created_at"))[:10]}
    return {}


def _f(x) -> Optional[float]:
    try:
        return float(x) if x is not None else None
    except Exception:
        return None


def _check(fly: dict, sec: dict, sym: str, m: dict) -> dict:
    """One metric check → {status, value, note}."""
    src, name = m.get("source"), m.get("name")
    op, target = m.get("op"), m.get("target")
    note_src = src
    if src == "doc":
        k = _doc_kpi(sym, name)
        if not k or k.get("value") is None:
            return {"status": "unknown", "metric": name,
                    "note": f"{name} not yet extracted from filings"}
        v = _f(k["value"])
        v = v / 100 if v is not None and abs(v) > 3 else v
        return {"status": "evidence", "metric": name, "value": v,
                "note": f"{name} ~{v} ({k.get('period') or 'latest'})"}
    v = _f((fly if src == "flywheel" else sec).get(name))
    if op in ("improving", "declining"):
        tr = _TREND_OF.get(name)
        tv = _f(fly.get(tr)) if tr else None
        if tv is None:
            return {"status": "unknown", "metric": name,
                    "note": f"no trend series for {name}"}
        good = tv > 0 if op == "improving" else tv < 0
        return {"status": "pass" if good else "fail",
                "metric": name, "value": tv,
                "note": f"{tr} {tv:+.2f}"}
    if v is None:
        return {"status": "unknown", "metric": name,
                "note": f"{name} not populated"}
    ok = True
    if target is not None and op:
        ok = {">": v > target, ">=": v >= target,
              "<": v < target, "<=": v <= target}.get(op, True)
    elif op == "positive":
        ok = v > 0
    return {"status": "pass" if ok else "fail", "metric": name,
            "value": round(v, 4), "op": op, "target": target,
            "note": f"{name} {v:+.3f} vs {op} {target}"}


def _periods(c: dict, prev: dict) -> None:
    """Consecutive-PRINT bookkeeping on a check — a hard leg must fail
    across distinct reporting periods to escalate; nightly re-evals of
    the same print don't count. 'New period' = the observed value
    changed AND ≥_MIN_PERIOD_GAP_DAYS since the streak last moved:
    fundamentals print quarterly, intra-quarter jitter isn't evidence.
    State rides on the check dict inside the hypotheses JSONB — the
    existing journal is the memory, no schema needed."""
    st = c.get("status")
    pf, pp = prev.get("fail_streak") or 0, prev.get("pass_streak") or 0
    sa = prev.get("streak_at")
    if st not in ("pass", "fail"):
        c.update(fail_streak=pf, pass_streak=pp, streak_at=sa)
        return
    v, pv = c.get("value"), prev.get("value")
    new_period = v is not None and (pv is None or v != pv)
    if new_period and sa:
        try:
            new_period = (date.today() - date.fromisoformat(
                str(sa)[:10])).days >= _MIN_PERIOD_GAP_DAYS
        except Exception:
            new_period = True
    if not prev:
        new_period = True
    today = date.today().isoformat()
    if st == "fail":
        c.update(fail_streak=(pf + 1) if new_period else max(pf, 1),
                 pass_streak=0, streak_at=today if new_period else sa)
    else:
        c.update(fail_streak=0,
                 pass_streak=(pp + 1) if new_period else max(pp, 1),
                 streak_at=today if new_period else sa)


def _hyp_status(checks: list[dict], hards: set) -> str:
    """Persistence ladder — the reviewer-mandated semantics:
    hard-fail streak 1 → deteriorating (warning), streak ≥2 →
    severely_deteriorating, streak ≥2 WITH corroboration (a second leg
    also failing) → broken. A single print never breaks a leg."""
    sts = [c["status"] for c in checks]
    hard_fail = [c for c in checks
                 if c["status"] == "fail" and c.get("hard")]
    if hard_fail:
        worst = max(c.get("fail_streak") or 1 for c in hard_fail)
        corroborated = len(hard_fail) > 1 or any(
            c["status"] == "fail" and not c.get("hard") for c in checks)
        if worst >= 2 and corroborated:
            return "broken"
        if worst >= 2:
            return "severely_deteriorating"
        return "deteriorating"
    if any(s == "fail" for s in sts):
        return "deteriorating"
    if all(s in ("pass", "evidence") for s in sts) \
            and any(s == "pass" for s in sts):
        return "on_track"
    if any(s in ("pass", "evidence") for s in sts):
        return "improving"
    return "unknown"


def _rollup_status(hyps: list[dict], score: int) -> str:
    """Hypothesis statuses → symbol status. Only a broken CORE leg
    breaks the thesis; a core hard-fail at any streak is severe
    (review, not impairment); broken optional legs cap the symbol at
    deteriorating — a failed side-bet isn't structural impairment."""
    if not hyps or all(h["status"] == "unknown" for h in hyps):
        return "unknown"
    core = [h for h in hyps if h.get("criticality") != "optional"]
    if any(h["status"] == "broken" for h in core):
        return "broken"
    if any(h.get("hard_fail") for h in core):
        return "severely_deteriorating"
    base = ("on_track" if score >= 4 else "improving" if score >= 1
            else "deteriorating" if score <= -2 else "mixed")
    if _RANK[base] > _RANK["deteriorating"] and any(
            h["status"] in ("broken", "severely_deteriorating")
            for h in hyps):
        return "deteriorating"
    return base


def _core_coverage(hyps: list[dict]) -> float:
    """Share of CORE checks that produced real evidence — unknown is
    absent data, never a soft answer."""
    checks = [c for h in hyps if h.get("criticality") != "optional"
              for c in (h.get("checks") or [])]
    if not checks:
        return 0.0
    return round(sum(1 for c in checks if c.get("status") != "unknown")
                 / len(checks), 2)


def evaluate(sym: str) -> dict:
    """Full archetype-scoped thesis evaluation → persist + watch sync."""
    import json
    from app.database import db
    sym = sym.upper()
    st = db.execute_query(
        "SELECT sector, industry FROM stocks WHERE symbol=:s",
        {"s": sym})
    sec_i = (st[0]["sector"], st[0]["industry"]) if st else ("", "")
    archs = archetypes_for(sym, sec_i[0] or "", sec_i[1] or "")
    primary, secondary = archs[0], (archs[1] if len(archs) > 1 else None)
    fly, sec = _flywheel(sym), _sec(sym)

    # previous state loads FIRST — streak bookkeeping, delta tracking
    # and recovery hysteresis all read it
    prev = db.execute_query(
        "SELECT status, hypotheses, status_since, detail"
        " FROM symbol_thesis WHERE symbol=:s", {"s": sym})
    prev = dict(prev[0]) if prev else {}
    prev_status = prev.get("status")
    prev_hyps = prev.get("hypotheses")
    if isinstance(prev_hyps, str):
        prev_hyps = json.loads(prev_hyps)
    prev_detail = prev.get("detail") or {}
    if isinstance(prev_detail, str):
        prev_detail = json.loads(prev_detail)
    prev_check = {}
    for ph in (prev_hyps or []):
        for c in (ph.get("checks") or []):
            prev_check[(ph.get("archetype"), ph.get("id"),
                        c.get("metric"))] = c

    hyps, vetoes_fired, unresolved = [], [], []
    cfg = _cfg()
    for arch in archs:
        spec = (cfg.get("archetypes") or {}).get(arch) or {}
        for h in spec.get("hypotheses") or []:
            hards = {m["name"] for m in h.get("metrics", [])
                     if m.get("hard")}
            checks = [_check(fly, sec, sym, m)
                      for m in h.get("metrics", [])]
            for c in checks:
                c["hard"] = c["metric"] in hards
                _periods(c, prev_check.get(
                    (arch, h["id"], c["metric"])) or {})
            status = _hyp_status(checks, hards)
            if status in ("unknown", "deteriorating",
                          "severely_deteriorating", "broken"):
                unresolved.append(
                    f"{h['id']}: {status} — "
                    + "; ".join(c["note"] for c in checks
                                if c["status"] in ("fail", "unknown"))[:160])
            hyps.append({"id": h["id"], "archetype": arch,
                         "stage": h.get("stage"),
                         "label": h.get("label"), "status": status,
                         "criticality": h.get("criticality") or "core",
                         "hard_fail": any(
                             c["status"] == "fail" and c.get("hard")
                             for c in checks),
                         "checks": checks,
                         "failure_condition": h.get("failure_condition"),
                         "valuation_impact": h.get("valuation_impact")})
            _sync_watch(sym, arch, h, checks)
        for v in spec.get("vetoes") or []:
            # a veto fires ONLY on its own `when` evidence — a linked
            # hypothesis gone bad, or every listed condition verifying
            # true. Unknown evidence never fires one.
            w = v.get("when") or {}
            fired = None
            if w.get("hypothesis"):
                tgt = next((hp for hp in hyps
                            if hp["id"] == w["hypothesis"]
                            and hp["archetype"] == arch), None)
                if tgt and tgt["status"] in ("deteriorating",
                                             "severely_deteriorating",
                                             "broken"):
                    fired = f"{w['hypothesis']}={tgt['status']}"
            elif w.get("metrics"):
                vcs = [_check(fly, sec, sym, m) for m in w["metrics"]]
                if vcs and all(c["status"] == "pass" for c in vcs):
                    fired = "; ".join(c["note"] for c in vcs)[:160]
            if fired:
                vetoes_fired.append({"id": v["id"], "cap": v["cap"],
                                     "flag": v["flag"],
                                     "fatal": bool(v.get("fatal")),
                                     "evidence": fired})

    score = sum(_SCORE[h["status"]] for h in hyps)
    status = _rollup_status(hyps, score)
    for v in vetoes_fired:
        if _RANK.get(v["cap"], 4) < _RANK.get(status, 4):
            status = v["cap"]
    # an unverifiable core thesis (e.g. lender credit quality with no
    # extracted data yet) can't claim on_track — cap at improving
    if _RANK[status] > _RANK["improving"] and any(
            h["status"] == "unknown" and h.get("criticality") == "core"
            for h in hyps):
        status = "improving"

    core_cov = _core_coverage(hyps)
    detail = {"unresolved": unresolved[:6],
              "archetype_label": ((cfg.get("archetypes") or {})
                                  .get(primary) or {}).get("label"),
              "evidence": {"core_coverage": core_cov,
                           "tier": "assessed" if core_cov
                           >= _CORE_COVERAGE_BAR else "provisional"}}
    # thin core coverage can't claim a confident on_track either
    if core_cov < _CORE_COVERAGE_BAR \
            and _RANK[status] > _RANK["improving"]:
        status = "improving"

    # --- recovery hysteresis ------------------------------------------
    # broken must not heal on one eval: the leg that broke has to
    # actually PASS again, then survive a review window capped at
    # 'deteriorating' before the status can climb back. broken_legs is
    # journaled so the window keeps its reference legs across evals.
    today_str = date.today().isoformat()
    rec = (prev_detail.get("recovery") or {}) \
        if isinstance(prev_detail.get("recovery"), dict) else {}
    if status == "broken":
        rec = {}
        detail["broken_at"] = \
            prev_detail.get("broken_at") or today_str
        detail["broken_legs"] = [
            f"{h['archetype']}:{h['id']}" for h in hyps
            if h["status"] == "broken"
            and h.get("criticality") == "core"]
    elif prev_status == "broken" or rec.get("under_review"):
        legs = prev_detail.get("broken_legs") or []
        prev_broken_keys = {tuple(k.split(":", 1)) for k in legs} \
            if legs else {
                (h.get("archetype"), h.get("id"))
                for h in (prev_hyps or [])
                if h.get("status") == "broken"}
        cur = {(h["archetype"], h["id"]): h for h in hyps}
        still_failing = any(
            c["status"] == "fail"
            for k in prev_broken_keys if k in cur
            for c in cur[k].get("checks") or [] if c.get("hard"))
        fatal_now = any(v.get("cap") == "broken" for v in vetoes_fired)
        if still_failing or fatal_now:
            # greens elsewhere can't heal a leg that's still failing
            status = "broken"
            detail["broken_at"] = \
                prev_detail.get("broken_at") or today_str
            detail["broken_legs"] = legs
        else:
            since = rec.get("since") or today_str
            try:
                probated = (date.today() - date.fromisoformat(
                    str(since)[:10])).days >= _RECOVERY_REVIEW_DAYS
            except Exception:
                probated = False
            if probated:
                rec = {}
                detail["recovered_at"] = today_str
            else:
                rec = {"under_review": True, "since": since}
                detail["broken_legs"] = legs
                if _RANK[status] > _RANK["deteriorating"]:
                    status = "deteriorating"
    if rec:
        detail["recovery"] = rec
    # standing driver commitments — management's forward numbers
    # (SMCI raised FY27 Q1 revenue +28% while trailing legs show
    # decel). Evidence, never a grade — surfaced so a deteriorating
    # verdict sits beside the raise that management just printed.
    try:
        detail["drivers"] = [dict(d) for d in db.execute_query(
            "SELECT metric, period, value, prior_value, delta_dir,"
            " delta_pct FROM driver_commitments WHERE symbol=:s"
            " AND status='open'"
            " ORDER BY created_at DESC LIMIT 8", {"s": sym})]
    except Exception:
        detail["drivers"] = []

    # --- delta vs the prior nightly eval ----------------------------
    # status_dir flags the direction of the thesis itself (improving
    # vs deteriorating vs continuing); hyp_changes names WHICH legs
    # moved so the UI can say "credit_quality: unknown→on_track —
    # confirmed" rather than just "up".
    if not prev_status:
        status_dir, status_since = "new", date.today().isoformat()
    else:
        d = _RANK[status] - _RANK.get(prev_status, 2)
        status_dir = "up" if d > 0 else "down" if d < 0 else "flat"
        status_since = (date.today().isoformat() if status_dir != "flat"
                        else (prev.get("status_since")
                              or date.today().isoformat()))
    prev_hyp = {(h.get("archetype"), h.get("id")): h.get("status")
                for h in (prev_hyps or [])}
    hyp_changes = [{"id": h["id"], "archetype": h["archetype"],
                    "from": prev_hyp.get((h["archetype"], h["id"]),
                                         "new"),
                    "to": h["status"]}
                   for h in hyps
                   if prev_hyp.get((h["archetype"], h["id"]))
                   != h["status"]]
    detail["status_dir"] = status_dir
    detail["hyp_changes"] = hyp_changes[:8]

    row = {"symbol": sym, "archetype": primary, "secondary": secondary,
           "hypotheses": hyps, "status": status, "score": score,
           "prev_status": prev_status, "status_dir": status_dir,
           "status_since": status_since, "hyp_changes": hyp_changes,
           "vetoes": vetoes_fired or None, "detail": detail,
           "as_of": date.today().isoformat()}
    db.execute_update(
        "INSERT INTO symbol_thesis (symbol, archetype, secondary,"
        " hypotheses, status, score, prev_status, status_dir,"
        " status_since, hyp_changes, vetoes, detail, as_of,"
        " checked_at)"
        " VALUES (:s,:a,:sec,CAST(:h AS jsonb),:st,:sc,:ps,:sd,:ss,"
        " CAST(:hc AS jsonb),CAST(:v AS jsonb),CAST(:d AS jsonb),:ao,"
        " now())"
        " ON CONFLICT (symbol) DO UPDATE SET"
        " archetype=EXCLUDED.archetype, secondary=EXCLUDED.secondary,"
        " hypotheses=EXCLUDED.hypotheses, status=EXCLUDED.status,"
        " score=EXCLUDED.score, prev_status=EXCLUDED.prev_status,"
        " status_dir=EXCLUDED.status_dir,"
        " status_since=EXCLUDED.status_since,"
        " hyp_changes=EXCLUDED.hyp_changes, vetoes=EXCLUDED.vetoes,"
        " detail=EXCLUDED.detail, as_of=EXCLUDED.as_of,"
        " checked_at=now(), updated_at=now()",
        {"s": sym, "a": primary, "sec": secondary,
         "h": json.dumps(hyps), "st": status, "sc": score,
         "ps": prev_status, "sd": status_dir, "ss": status_since,
         "hc": json.dumps(hyp_changes) if hyp_changes else None,
         "v": json.dumps(vetoes_fired) if vetoes_fired else None,
         "d": json.dumps(detail), "ao": row["as_of"]})
    try:
        _journal_change(sym, primary, row, hyps, prev_status,
                        hyp_changes, vetoes_fired, detail)
    except Exception:
        logger.exception("thesis change journal failed for %s", sym)
    return row


def _journal_change(sym: str, primary: str, row: dict,
                    hyps: list[dict], prev_status: Optional[str],
                    hyp_changes: list, vetoes_fired: list,
                    detail: dict) -> None:
    """Journal a thesis_change_events row + a thesis_change alert on
    material movement — the timeline symbol_thesis can't hold.

    event kinds:
      coverage_start      first eval — history anchor, never alerts
      status_transition   top-line moved up/down — alerts
      leg_change          flat top status but a CORE hypothesis moved —
                          the quiet deterioration the rollup hides.
                          Journaled, not alerted: a leg that matters
                          enough to page on moves the top status too.
    Flat days with only optional-leg shuffles journal nothing.
    """
    import json
    from app.database import db
    status_dir = row["status_dir"]
    status = row["status"]
    if not prev_status:
        kind = "coverage_start"
    elif status_dir in ("up", "down"):
        kind = "status_transition"
    elif hyp_changes and any(
            next((h for h in hyps
                  if h["id"] == c["id"]
                  and h["archetype"] == c["archetype"]), {})
            .get("criticality") == "core"
            for c in hyp_changes):
        kind = "leg_change"
    else:
        return

    # evidence snapshot — for each changed hypothesis, the checks that
    # produced the move, so the row answers 'why' without reconstructing
    changed = {(c["archetype"], c["id"]) for c in (hyp_changes or [])}
    evidence = [
        {"hypothesis_id": h["id"], "archetype": h["archetype"],
         "status": h["status"], "label": h.get("label"),
         "checks": [{"metric": c.get("metric"),
                     "status": c.get("status"),
                     "note": c.get("note"),
                     "hard": bool(c.get("hard"))}
                    for c in h.get("checks") or []]}
        for h in hyps if (h["archetype"], h["id"]) in changed]

    alert_id = None
    if kind == "status_transition":
        down = status_dir == "down"
        rank = _RANK.get(status, 4)
        fatal = any(v.get("fatal") for v in (vetoes_fired or []))
        materiality = "HIGH" if rank <= 1 or fatal else "MEDIUM"
        priority = (160 if rank == 0 or fatal else
                    140 if rank == 1 else
                    120 if down else 110)
        # reason: the firing veto, else the worst changed leg
        worst = None
        for h in hyps:
            if (h["archetype"], h["id"]) in changed and (
                    worst is None
                    or _RANK.get(h["status"], 4)
                    < _RANK.get(worst["status"], 4)):
                worst = h
        veto = vetoes_fired[0] if vetoes_fired else None
        reason = (veto["flag"] if veto else
                  worst["id"].replace("_", " ") if worst else "")
        title = (f"{sym} thesis: {prev_status} → {status}"
                 + (f" — {reason[:90]}" if reason else ""))
        in_book = bool(db.execute_query(
            "SELECT 1 FROM held_symbols WHERE symbol=:s LIMIT 1",
            {"s": sym}))
        in_wl = bool(db.execute_query(
            "SELECT 1 FROM watchlist_stocks ws JOIN stocks s"
            " ON s.id=ws.stock_id WHERE s.symbol=:s LIMIT 1",
            {"s": sym}))
        fp = f"thesis_change:{sym}:{prev_status}:{status}:{row['as_of']}"
        det = {"thesis": {"before": prev_status, "after": status},
               "archetype": primary, "hyp_changes": hyp_changes,
               "veto": veto, "score": row["score"]}
        db.execute_update(
            "INSERT INTO alert_items (symbol, event_type, direction,"
            " materiality, title, detail, fingerprint, source,"
            " source_timestamp, in_portfolio, in_watchlist, status,"
            " priority_score) VALUES"
            " (:s,'thesis_change',:di,:mat,:t,CAST(:de AS jsonb),:fp,"
            " 'thesis_health',now(),:ib,:iw,'new',:pr)"
            " ON CONFLICT (fingerprint) DO NOTHING",
            {"s": sym, "di": "DOWN" if down else "UP",
             "mat": materiality, "t": title,
             "de": json.dumps(det, default=str), "fp": fp,
             "ib": in_book, "iw": in_wl, "pr": priority})
        aid = db.execute_query(
            "SELECT id FROM alert_items WHERE fingerprint=:fp",
            {"fp": fp})
        alert_id = str(aid[0]["id"]) if aid else None

    db.execute_update(
        "INSERT INTO thesis_change_events (symbol, as_of, event_kind,"
        " archetype, prev_status, status, status_dir, score,"
        " hyp_changes, veto_fired, evidence, drivers, alert_id,"
        " detail) VALUES (:s,:ao,:k,:a,:ps,:st,:sd,:sc,"
        " CAST(:hc AS jsonb),CAST(:v AS jsonb),CAST(:e AS jsonb),"
        " CAST(:dr AS jsonb),:aid,CAST(:d AS jsonb))"
        " ON CONFLICT DO NOTHING",
        {"s": sym, "ao": row["as_of"], "k": kind, "a": primary,
         "ps": prev_status, "st": status, "sd": status_dir,
         "sc": row["score"],
         "hc": json.dumps(hyp_changes or []),
         "v": json.dumps(vetoes_fired or []),
         "e": json.dumps(evidence, default=str),
         "dr": json.dumps(detail.get("drivers") or [], default=str),
         "aid": alert_id,
         "d": json.dumps(detail, default=str)})


def _sync_watch(sym: str, arch: str, h: dict, checks: list[dict]) -> None:
    """Materialize each check as a thesis_watches row — the existing
    journal/grader stays the source of record; hypothesis linkage rides
    on the new columns. Skips doc-sourced checks (no numeric target)."""
    from app.database import db
    for m in h.get("metrics", []):
        if m.get("source") == "doc":
            continue
        metric = f"{h['id']}:{m['name']}"
        thr = f"{m.get('op') or ''}{m.get('target')}" \
            if m.get("target") is not None else (m.get("op") or "")
        db.execute_update(
            "INSERT INTO thesis_watches (symbol, metric, threshold,"
            " horizon, direction, source, hypothesis_id, stage,"
            " archetype, expected_direction, failure_condition,"
            " valuation_impact) VALUES"
            " (:s,:m,:t,'standing','confirm',:src,:hid,:stg,:a,:ed,"
            " :fc,:vi)"
            " ON CONFLICT (symbol, metric, horizon) DO UPDATE SET"
            " source=EXCLUDED.source, hypothesis_id=EXCLUDED.hypothesis_id,"
            " stage=EXCLUDED.stage, archetype=EXCLUDED.archetype",
            {"s": sym, "m": metric[:80], "t": thr[:80],
             "src": f"thesis:{arch}", "hid": h["id"],
             "stg": h.get("stage"), "a": arch,
             "ed": m.get("op"), "fc": h.get("failure_condition"),
             "vi": h.get("valuation_impact")})


def _universe() -> list[str]:
    """The nightly refresh set — the 'rebuilt on earnings/news'
    contract:

      curated  every symbol in the config
      existing every symbol that ever earned a thesis row — a lazy
               card-open eval stays fresh instead of going stale
      earnings book/watchlist names that reported since their last
               thesis check (or have never been checked) — the
               quarterly-rebuild trigger
      tracked  every tracked name (books, watchlist, rule-breaker
               and small-cap members) that has source data — the
               same universe the other nightly scans cover; the
               37k-row stocks table is NOT evaluated because the
               upstream flywheel/sec/doc data only exists for ~530
               names — an all-unknown row is noise, not signal
      news     handled implicitly: an event review lands after the
               last thesis check → the row is stale by day, so the
               nightly sweep re-reads it
    """
    from app.database import db
    cfg = _cfg()
    base = set((cfg.get("symbols") or {}).keys())
    have = {r["symbol"] for r in db.execute_query(
        "SELECT symbol FROM symbol_thesis")}
    try:
        from app.signals import symbol_tiers
        tracked = symbol_tiers._active_sql()
        # tracked ∩ has-thesis-source-data — skip names with nothing
        # to check against (every leg would read 'not populated')
        covered = {r["symbol"] for r in db.execute_query(
            f"SELECT t.symbol FROM ({tracked}) t WHERE EXISTS"
            " (SELECT 1 FROM symbol_flywheel f"
            "  WHERE f.symbol=t.symbol) OR EXISTS"
            " (SELECT 1 FROM symbol_sec_facts f"
            "  WHERE f.symbol=t.symbol) OR EXISTS"
            " (SELECT 1 FROM doc_analyses d"
            "  WHERE d.symbol=t.symbol)")}
        earn = {r["symbol"] for r in db.execute_query(
            f"SELECT s.symbol FROM stocks s"
            f" WHERE s.symbol IN ({tracked})"
            " AND s.next_earnings_date <= CURRENT_DATE"
            " AND s.next_earnings_date >= CURRENT_DATE - 5"
            " AND NOT EXISTS (SELECT 1 FROM symbol_thesis t"
            "   WHERE t.symbol=s.symbol"
            "   AND t.checked_at::date > s.next_earnings_date)")}
    except Exception:
        covered, earn = set(), set()

    # tier gate — if symbol_tiers exists, monthly-tier names refresh
    # only when their thesis row is ≥30 days stale; the active tier
    # stays nightly. Degrades to covered|earn when the table's absent.
    try:
        tiers = {r["symbol"]: r["tier"] for r in db.execute_query(
            "SELECT symbol, tier FROM symbol_tiers")}
        if tiers:
            active = base | earn | {
                s for s, t in tiers.items() if t == "active"
            } | (have - set(tiers))          # untiered rows stay nightly
            stale_monthly = {r["symbol"] for r in db.execute_query(
                "SELECT s.symbol FROM symbol_tiers s"
                " LEFT JOIN symbol_thesis t ON t.symbol=s.symbol"
                " WHERE s.tier='monthly' AND (t.checked_at IS NULL"
                " OR t.checked_at < now() - interval '30 days')")}
            return sorted(active | stale_monthly)
    except Exception:
        pass
    return sorted(base | have | covered | earn)


def run(symbols: Optional[list[str]] = None) -> dict:
    """Pilot refresh — curated ∪ existing rows ∪ post-earnings names."""
    cfg = _cfg()
    syms = symbols or _universe()
    out, errs = {}, []
    for s in syms:
        try:
            out[s] = evaluate(s)["status"]
        except Exception as exc:
            errs.append(f"{s}: {exc}")
    return {"symbols": syms, "status": out, "errors": errs}


_METRIC_LABEL = {
    "rev_growth": "revenue growth", "rev_accel": "revenue acceleration",
    "fcf_margin": "FCF margin", "fcf_ttm": "free cash flow",
    "om_slope": "operating-margin slope", "gm_slope": "gross-margin slope",
    "est_revision_pct": "street revisions",
    "rev_breadth_30d": "revision breadth",
    "beat_streak": "consecutive beats",
    "eps_rep_growth": "reported EPS growth",
    "rpo_yoy": "backlog (RPO) growth",
    "def_rev_yoy": "deferred-revenue growth",
    "acq_rev_pct": "acquisition spend vs revenue",
    "capex_eff": "capex efficiency",
    "net_debt_ebitda": "net debt/EBITDA",
    "shares_step_ratio": "share-count step",
    # doc KPIs — company-defined, extracted only
    "gmv_growth": "GMV growth", "take_rate": "take rate",
    "delinquencies": "delinquencies", "charge_offs": "charge-offs",
    "provisions": "loan-loss provisions",
    "contracted_revenue": "contracted revenue",
    "organic_growth": "disclosed organic growth",
    "data_center_growth": "data-center growth",
    "segment_growth": "strategic-segment growth",
    "product_revenue_growth": "product-revenue growth",
}


def _label(metric: str) -> str:
    return _METRIC_LABEL.get(metric, metric.replace("_", " "))


def _fmt_val(metric: str, v) -> str:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "n/a"
    if metric in ("fcf_ttm",):
        return f"${v / 1e9:.1f}B" if abs(v) >= 1e9 \
            else f"${v / 1e6:.0f}M" if abs(v) >= 1e6 else f"${v:.0f}"
    if abs(v) >= 1e9:
        return f"${v / 1e9:.1f}B"
    if abs(v) >= 1e6:
        return f"${v / 1e6:.0f}M"
    if metric in ("beat_streak",):
        return f"{v:.0f}"
    if metric in ("net_debt_ebitda", "rev_breadth_30d",
                  "shares_step_ratio", "capex_eff"):
        return f"{v:.1f}x"
    return f"{v * 100:+.1f}%"


def _check_line(c: dict) -> str:
    """'revenue growth +48% vs ≥15% bar' — one passing/failing check."""
    if c.get("status") == "evidence":
        return f"{_label(c['metric'])} extracted ({c.get('note', '')[-40:]})"
    v = c.get("value")
    if v is None:
        return _label(c["metric"])
    out = f"{_label(c['metric'])} {_fmt_val(c['metric'], v)}"
    if c.get("op") and c.get("target") is not None:
        op = {"<=": "≤", ">=": "≥", "<": "<", ">": ">"}.get(
            c["op"], c["op"])
        out += f" vs {op} {_fmt_val(c['metric'], c['target']).lstrip('+')} bar"
    return out


def stance_for(status: str, fv_upside_pct: Optional[float],
               mom_state: Optional[str] = None) -> str:
    """Deterministic stance line — thesis status × whether the market
    already paid for the improvement, annotated with tape context.

    This is a THESIS verdict (business confirmed + valuation), not a
    timing call — so the tape clause names the missing leg instead of
    pretending the stance covers it. The FV leg gates on the same
    plausibility band the pulse engine uses (pulse_engine.fv_usable):
    an |upside| outside ±75% is model-blind, not 'cheap'/'pricey'."""
    if status == "broken":
        return "Avoid — thesis broken"
    if status == "severely_deteriorating":
        return ("Reduce / under review — a core thesis leg failed; "
                "persistent failure breaks it")
    if status == "deteriorating":
        return "Reduce / no new adds — legs moving against the thesis"
    if status == "unknown":
        return "No standing thesis — insufficient data"
    from app.signals.pulse_engine import fv_usable, tape_groups
    up = fv_upside_pct
    usable = fv_usable(up)[0]
    cheap = usable and up >= 25
    pricey = usable and up <= -20
    suspect = up is not None and not usable
    if status == "on_track":
        if cheap:
            out = "Accumulate candidate — confirmed and still cheap"
        elif pricey:
            out = "Hold — thesis on track, price already paid for it"
        else:
            out = "On track — hold / add on weakness"
    elif status == "improving":
        if cheap:
            out = "Watch / staged entry — progress, unconfirmed legs, cheap"
        elif pricey:
            out = "Watch — improving but priced ahead of the evidence"
        else:
            out = "Watch / staged entry — improving, legs still open"
    else:
        out = "Watch — mixed evidence"
    if suspect:
        out += f" · FV gap {up:+.0f}% suspect — valuation unverified"
    if mom_state:
        groups = tape_groups()
        if mom_state in (groups.get("tape_hostile_entry") or []):
            out += f" · tape {mom_state} — stalk the base, don't chase"
        elif mom_state in (groups.get("tape_weak") or []):
            out += f" · tape {mom_state}"
    return out


def build_report(t: dict, fv_upside_pct: Optional[float] = None,
                 mom_state: Optional[str] = None) -> dict:
    """'What I like / what I want confirmed' — deterministic prose from
    a persisted symbol_thesis row. Passing legs are the likes; unknown,
    deteriorating or broken legs are the open confirmations. No LLM —
    every line cites the check that produced it."""
    likes, confirm = [], []
    for h in (t.get("hypotheses") or []):
        label = h.get("label") or h["id"].replace("_", " ")
        st = h.get("status")
        checks = h.get("checks") or []
        passing = [c for c in checks if c.get("status") == "pass"]
        failing = [c for c in checks if c.get("status") == "fail"]
        unknown = [c for c in checks if c.get("status") == "unknown"]
        if st in ("on_track", "improving"):
            line = label[0].upper() + label[1:]
            if passing:
                line += f" — {_check_line(passing[0])}"
            elif any(c.get("status") == "evidence" for c in checks):
                line += " — supporting evidence extracted"
            likes.append(line)
        elif st in ("broken", "severely_deteriorating"):
            why = (_check_line(failing[0]) if failing
                   else (h.get("failure_condition") or "hard check failed"))
            tag = "broken" if st == "broken" else "severe"
            confirm.append(f"{label} — {tag}: {why}")
        elif st == "deteriorating":
            why = (_check_line(failing[0]) if failing
                   else (h.get("failure_condition") or ""))
            confirm.append(f"{label} — {why}".rstrip(" —"))
        else:  # unknown — the 'want confirmed' list
            need = ", ".join(_label(c["metric"]) for c in unknown) \
                or "confirmation data"
            fc = h.get("failure_condition")
            line = f"{label} — awaiting {need}"
            if fc:
                line += f" (fails if: {fc})"
            confirm.append(line)
    # driver commitments — forward evidence beside the legs: raises
    # read as 'guide raised' likes, cuts as 'want confirmed' flags
    for d in ((t.get("detail") or {}).get("drivers") or [])[:4]:
        met = str(d.get("metric") or "").replace("_", " ")
        per = d.get("period") or ""
        dp = d.get("delta_pct")
        if d.get("delta_dir") == "raised":
            likes.append(f"Guide {met} {per} raised"
                         + (f" {dp:+.0%}" if dp is not None else ""))
        elif d.get("delta_dir") == "cut":
            confirm.append(f"Guide {met} {per} cut"
                           + (f" {dp:.0%}" if dp is not None else "")
                           + " — management's own number, not ours")
    det = t.get("detail") or {}
    return {"stance": stance_for(str(t.get("status") or "unknown"),
                                 fv_upside_pct, mom_state),
            "likes": likes[:6], "confirm": confirm[:6],
            "status": t.get("status"), "dir": t.get("status_dir"),
            "archetype": t.get("archetype"),
            "evidence": det.get("evidence"),
            "recovery": det.get("recovery")}
