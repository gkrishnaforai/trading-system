"""thesis_health — archetype-scoped upside tracking.

Answers "is THIS name's specific upside case getting stronger" — not
"is the company good." Each archetype (archetype_checklists.yaml)
carries standing hypotheses with falsifiable metric checks sourced
from the flywheel, SEC facts, or extracted doc KPIs. Statuses roll up
into symbol_thesis; every check also materializes as a thesis_watches
row so the existing check_watches() grader and review surfaces stay
the single journal — no parallel tracker.

Status vocabulary (controlled, per the design):
  on_track     all checks pass
  improving    evidence moving the right way (pass + evidence mix)
  mixed        some pass, some weaken
  deteriorating a check failed
  broken       a `hard` check failed / failure_condition met
  unknown      data missing — never treated as neutral or positive
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

_RANK = {"broken": 0, "deteriorating": 1, "mixed": 2, "improving": 3,
         "on_track": 4, "unknown": -1}
_SCORE = {"on_track": 2, "improving": 1, "mixed": 0, "unknown": 0,
          "deteriorating": -1, "broken": -2}


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
            "value": round(v, 4),
            "note": f"{name} {v:+.3f} vs {op} {target}"}


def _hyp_status(checks: list[dict], hards: set) -> str:
    sts = [c["status"] for c in checks]
    if any(s == "fail" and checks[i]["metric"] in hards
           for i, s in enumerate(sts)):
        return "broken"
    if any(s == "fail" for s in sts):
        return "deteriorating"
    if all(s in ("pass", "evidence") for s in sts) \
            and any(s == "pass" for s in sts):
        return "on_track"
    if any(s in ("pass", "evidence") for s in sts):
        return "improving"
    return "unknown"


def evaluate(sym: str) -> dict:
    """Full archetype-scoped thesis evaluation → persist + watch sync."""
    from app.database import db
    sym = sym.upper()
    st = db.execute_query(
        "SELECT sector, industry FROM stocks WHERE symbol=:s",
        {"s": sym})
    sec_i = (st[0]["sector"], st[0]["industry"]) if st else ("", "")
    archs = archetypes_for(sym, sec_i[0] or "", sec_i[1] or "")
    primary, secondary = archs[0], (archs[1] if len(archs) > 1 else None)
    fly, sec = _flywheel(sym), _sec(sym)

    hyps, vetoes_fired, unresolved = [], [], []
    cfg = _cfg()
    for arch in archs:
        spec = (cfg.get("archetypes") or {}).get(arch) or {}
        for h in spec.get("hypotheses") or []:
            hards = {m["name"] for m in h.get("metrics", [])
                     if m.get("hard")}
            checks = [_check(fly, sec, sym, m)
                      for m in h.get("metrics", [])]
            status = _hyp_status(checks, hards)
            if status in ("unknown", "deteriorating", "broken"):
                unresolved.append(
                    f"{h['id']}: {status} — "
                    + "; ".join(c["note"] for c in checks
                                if c["status"] in ("fail", "unknown"))[:160])
            hyps.append({"id": h["id"], "archetype": arch,
                         "stage": h.get("stage"),
                         "label": h.get("label"), "status": status,
                         "hard": bool(h.get("hard_thesis")),
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
                if tgt and tgt["status"] in ("deteriorating", "broken"):
                    fired = f"{w['hypothesis']}={tgt['status']}"
            elif w.get("metrics"):
                vcs = [_check(fly, sec, sym, m) for m in w["metrics"]]
                if vcs and all(c["status"] == "pass" for c in vcs):
                    fired = "; ".join(c["note"] for c in vcs)[:160]
            if fired:
                vetoes_fired.append({"id": v["id"], "cap": v["cap"],
                                     "flag": v["flag"],
                                     "evidence": fired})

    score = sum(_SCORE[h["status"]] for h in hyps)
    hard_broken = any(h["status"] == "broken" and h.get("hard")
                      for h in hyps)
    if not hyps:
        status = "unknown"
    elif hard_broken or any(h["status"] == "broken" for h in hyps):
        status = "broken"
    elif all(h["status"] == "unknown" for h in hyps):
        status = "unknown"
    elif score >= 4:
        status = "on_track"
    elif score >= 1:
        status = "improving"
    elif score <= -2:
        status = "deteriorating"
    else:
        status = "mixed"
    for v in vetoes_fired:
        if _RANK.get(v["cap"], 4) < _RANK.get(status, 4):
            status = v["cap"]
    # an unverifiable hard thesis (e.g. lender credit quality with no
    # extracted data yet) can't claim on_track — cap at improving
    if _RANK[status] > _RANK["improving"] and any(
            h["status"] == "unknown" and h.get("hard") for h in hyps):
        status = "improving"

    detail = {"unresolved": unresolved[:6],
              "archetype_label": ((cfg.get("archetypes") or {})
                                  .get(primary) or {}).get("label")}

    # --- delta vs the prior nightly eval ----------------------------
    # status_dir flags the direction of the thesis itself (improving
    # vs deteriorating vs continuing); hyp_changes names WHICH legs
    # moved so the UI can say "credit_quality: unknown→on_track —
    # confirmed" rather than just "up".
    prev = db.execute_query(
        "SELECT status, hypotheses, status_since FROM symbol_thesis"
        " WHERE symbol=:s", {"s": sym})
    prev = dict(prev[0]) if prev else {}
    prev_status = prev.get("status")
    if not prev_status:
        status_dir, status_since = "new", date.today().isoformat()
    else:
        d = _RANK[status] - _RANK.get(prev_status, 2)
        status_dir = "up" if d > 0 else "down" if d < 0 else "flat"
        status_since = (date.today().isoformat() if status_dir != "flat"
                        else (prev.get("status_since")
                              or date.today().isoformat()))
    prev_hyps = prev.get("hypotheses")
    if isinstance(prev_hyps, str):
        import json as _json
        prev_hyps = _json.loads(prev_hyps)
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
    import json
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
    return row


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


def run(symbols: Optional[list[str]] = None) -> dict:
    """Pilot refresh — default the explicit checklist symbols."""
    cfg = _cfg()
    syms = symbols or sorted((cfg.get("symbols") or {}).keys())
    out, errs = {}, []
    for s in syms:
        try:
            out[s] = evaluate(s)["status"]
        except Exception as exc:
            errs.append(f"{s}: {exc}")
    return {"symbols": syms, "status": out, "errors": errs}
