"""Future-theme registry + review — the thesis engine behind
Conviction's watch lane.

Data flow:
  code dict (conviction.FUTURE_THEMES) seeds theme_registry once;
  after that the TABLE is the truth — code is only a fallback.

  weekly accrual (every run):
    · keyword hits in alert_items titles, last 90d, per theme
    · member evidence: median rev growth / revisions / quality
    → evidence jsonb on the registry row

  quarterly deep review (first run of Jan/Apr/Jul/Oct):
    · re-stage active themes on evidence (emerging → inflecting →
      mainstream → exhausted)
    · LLM discovery: clustered recurring headline phrases → proposed
      new themes → deterministic validation (members must exist,
      ≥3, need flywheel/fundamental rows) → status 'candidate'
    · candidates promote to 'active' once evidence is real;
      exhausted themes retire to 'mainstream' weight (still tracked,
      minimal score) or 'retired'.

LLM proposes, evidence disposes — a theme never earns score weight
until its members show real numbers.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, timedelta
from typing import Any, Optional

logger = logging.getLogger(__name__)

# headline-matching terms per theme — the news-discovery hook.
# Keys must match conviction.FUTURE_THEMES / theme_registry.theme_key.
_KEYWORDS = {
    "ai_inference": ["inference", "edge ai", "custom silicon", "asic",
                     "accelerator"],
    "ai_optics": ["co-packaged optics", "cpo", "optical", "photonics",
                  "laser", "silicon photonics"],
    "dc_power_cooling": ["liquid cooling", "data center cooling",
                         "thermal", "backup power", "diesel generator",
                         "mw per rack", "power density"],
    "grid_electrification": ["grid", "transformer", "switchgear",
                             "electrification", "transmission",
                             "utility capex"],
    "hbm_memory": ["hbm", "high bandwidth memory", "dram shortage",
                   "nand", "memory pricing"],
    "robotics_edge": ["humanoid", "warehouse robot", "automation",
                      "machine vision", "physical ai", "robot"],
    "ai_software": ["ai monetization", "copilot", "agentic",
                    "ai revenue", "enterprise ai"],
    "space_defense": ["launch", "satellite", "defense contract",
                      "hypersonic", "drone", "golden dome"],
}


def _seed_registry():
    """First-run: copy the code dict into the table. Idempotent —
    existing rows (including LLM-discovered) are never clobbered."""
    from app.database import db
    from app.signals.conviction import FUTURE_THEMES
    for key, t in FUTURE_THEMES.items():
        db.execute_update(
            "INSERT INTO theme_registry (theme_key, name, thesis,"
            " stage, status, members, keywords, source)"
            " VALUES (:k,:n,:th,:st,'active',CAST(:m AS jsonb),"
            " CAST(:kw AS jsonb),'seed')"
            " ON CONFLICT (theme_key) DO NOTHING",
            {"k": key, "n": t["name"], "th": t.get("thesis"),
             "st": t["stage"], "m": json.dumps(t["members"]),
             "kw": json.dumps(_KEYWORDS.get(key) or [])})


def registry(include_candidates: bool = False) -> dict[str, dict]:
    """Runtime theme map — DB first, code dict as fallback for keys
    the table doesn't know yet. Candidates only when asked (the
    review pipeline sees them; scoring doesn't)."""
    from app.database import db
    try:
        _seed_registry()
        status = "('active','candidate')" if include_candidates \
            else "('active')"
        rows = db.execute_query(
            f"SELECT theme_key, name, thesis, stage, status, members"
            f" FROM theme_registry WHERE status IN {status}")
        out = {}
        for r in rows:
            mem = r.get("members") or {}
            if isinstance(mem, str):
                mem = json.loads(mem)
            out[r["theme_key"]] = {"name": r["name"],
                                   "thesis": r.get("thesis"),
                                   "stage": r["stage"],
                                   "status": r["status"],
                                   "members": mem}
        if out:
            return out
    except Exception as exc:
        logger.debug("registry fallback: %s", exc)
    from app.signals.conviction import FUTURE_THEMES
    return FUTURE_THEMES


def _keyword_hits(theme_key: str, keywords: list[str],
                  days: int = 90) -> dict[str, Any]:
    """Count headline hits per keyword in alert_items — the cheap,
    deterministic 'is this theme getting louder' signal (the live
    catalyst corpus; stock_news is the dead legacy table)."""
    from app.database import db
    if not keywords:
        return {}
    pats = [f"%{k}%" for k in keywords]
    hits = {}
    total = 0
    for k, p in zip(keywords, pats):
        n = db.execute_query(
            "SELECT count(*) c FROM alert_items WHERE title ILIKE :p"
            " AND created_at > :c",
            {"p": p, "c": date.today() - timedelta(days=days)})[0]["c"]
        if n:
            hits[k] = n
            total += n
    return {"hits": hits, "total": total}


def _member_evidence(members: dict) -> dict[str, Any]:
    """Median member fundamentals — is the thesis showing in numbers.
    rev growth, estimate revisions, coverage breadth."""
    from app.database import db
    if isinstance(members, str):
        members = json.loads(members)
    syms = list(members.keys())
    if not syms:
        return {}
    rows = db.execute_query(
        "SELECT symbol, rev_growth, est_revision_pct, gap_score,"
        " num_analysts FROM symbol_flywheel WHERE symbol = ANY(:s)",
        {"s": syms})
    have = {r["symbol"] for r in rows}
    rgs = [r["rev_growth"] for r in rows
           if r.get("rev_growth") is not None]
    ers = [r["est_revision_pct"] for r in rows
           if r.get("est_revision_pct") is not None]
    mom = db.execute_query(
        "SELECT momentum_state FROM stocks WHERE symbol = ANY(:s)"
        " AND momentum_state IS NOT NULL", {"s": syms})
    pos = sum(1 for m in mom if m["momentum_state"] in
              ("breakout", "uptrend", "climax", "pullback"))
    return {"member_coverage": len(have) / len(syms),
            "median_rev_growth": sorted(rgs)[len(rgs) // 2] if rgs
            else None,
            "median_revision": sorted(ers)[len(ers) // 2] if ers
            else None,
            "tape_breadth": pos / len(mom) if mom else None}


def accrue_evidence() -> dict[str, int]:
    """Weekly leg — refresh keyword hits + member evidence for every
    registry row. Cheap; keeps the quarterly review fed."""
    from app.database import db
    _seed_registry()
    rows = db.execute_query(
        "SELECT theme_key, keywords, members FROM theme_registry")
    n = 0
    for r in rows:
        kws = r.get("keywords") or _KEYWORDS.get(r["theme_key"]) or []
        ev = {"news": _keyword_hits(r["theme_key"], kws),
              "members": _member_evidence(r.get("members") or {}),
              "as_of": str(date.today())}
        db.execute_update(
            "UPDATE theme_registry SET evidence=CAST(:e AS jsonb),"
            " updated_at=now() WHERE theme_key=:k",
            {"e": json.dumps(ev), "k": r["theme_key"]})
        n += 1
    return {"refreshed": n}


def _restage(key: str, ev: dict, cur_stage: str) -> Optional[str]:
    """Evidence → stage transition. Returns new stage or None."""
    m, news = ev.get("members") or {}, ev.get("news") or {}
    rg = m.get("median_rev_growth") or 0
    breadth = m.get("tape_breadth") or 0
    hits = news.get("total") or 0
    if cur_stage == "emerging":
        # inflecting = thesis confirmed by accelerating numbers +
        # headline volume
        if rg >= 0.25 and (hits >= 5 or breadth >= 0.5):
            return "inflecting"
    elif cur_stage == "inflecting":
        if rg >= 0.35 and breadth >= 0.6:
            return "mainstream"      # the trade is consensus now
        if rg < 0.05 and hits == 0 and breadth < 0.3:
            return "exhausted"       # thesis stalling
    elif cur_stage == "mainstream":
        if rg < 0.0 and breadth < 0.2:
            return "exhausted"
    return None


def _discover(model: Optional[str] = None) -> list[dict]:
    """LLM theme proposals from clustered headlines — bounded by
    validation: members must be real, tradeable, with data."""
    from app.database import db
    # the corpus: live catalyst/analyst headlines (alert_items is the
    # current ingestion — stock_news is the dead legacy table)
    titles = [r["title"] for r in db.execute_query(
        "SELECT title FROM alert_items"
        " WHERE event_type IN ('catalyst','analyst_action',"
        "   'eps_revision') AND created_at > :c AND title IS NOT NULL"
        " ORDER BY created_at DESC LIMIT 400",
        {"c": date.today() - timedelta(days=30)})]
    known = [r["theme_key"] for r in db.execute_query(
        "SELECT theme_key FROM theme_registry")]
    if len(titles) < 30:
        return []
    try:
        from litellm import completion
        from app.config import settings
        mdl = model or getattr(settings, "litellm_model", None) \
            or "gpt-4o-mini"
        resp = completion(
            model=mdl, temperature=0.2, max_tokens=1200, timeout=45,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content":
                 "You spot emerging multi-year INVESTMENT THEMES in "
                 "newsflow (picks-and-shovels, like 'AI needs GPUs'). "
                 "Return JSON: {\"themes\": [{\"key\": snake_case, "
                 "\"name\": short, \"thesis\": one sentence, "
                 "\"members\": {\"TICKER\": \"pure|derivative\"}}]}. "
                 "Only themes with ≥3 plausible public-company members. "
                 "Skip anything already covered by the existing themes "
                 "listed — they track AI infra, optics, DC cooling, "
                 "grid, HBM, robotics, AI software, space/defense."},
                {"role": "user", "content":
                 f"Existing themes: {', '.join(known)}\n\n"
                 f"Recent headlines ({len(titles)}):\n" +
                 "\n".join(titles[:250])}])
        raw = json.loads(resp.choices[0].message.content)
    except Exception as exc:
        logger.warning("theme discovery LLM failed: %s", exc)
        return []
    # deterministic validation — the 'evidence disposes' gate
    props = []
    for t in (raw.get("themes") or [])[:6]:
        members = t.get("members") or {}
        if len(members) < 3 or not t.get("key") or \
                t["key"] in known:
            continue
        syms = [s for s in members if re.fullmatch(r"[A-Z]{1,5}", s)]
        real = {r["symbol"] for r in db.execute_query(
            "SELECT symbol FROM stocks WHERE symbol = ANY(:s)",
            {"s": syms})}
        valid = {s: v for s, v in members.items() if s in real
                 and v in ("pure", "derivative")}
        if len(valid) >= 3:
            props.append({"key": t["key"][:40], "name": t.get("name"),
                          "thesis": t.get("thesis"), "members": valid})
    return props


def _quarter_due() -> bool:
    """Deep review owed? — last_review is stamped on every row a deep
    pass processes, so 'no row reviewed inside the current quarter'
    means the quarterly pass is due. Survives missed Sundays — a
    catch-up run sees the flag and does the deep pass whenever it
    fires."""
    from app.database import db
    today = date.today()
    qstart = date(today.year, ((today.month - 1) // 3) * 3 + 1, 1)
    return db.execute_query(
        "SELECT count(*) c FROM theme_registry"
        " WHERE last_review >= :d", {"d": qstart})[0]["c"] == 0


def review(quarterly: Optional[bool] = None,
           model: Optional[str] = None) -> dict[str, Any]:
    """Weekly evidence accrual always; the quarterly deep pass
    (restaging + LLM discovery + promotion) fires whenever the
    quarter hasn't been reviewed — not just on a calendar day."""
    from app.database import db
    if quarterly is None:
        quarterly = _quarter_due()
    out = accrue_evidence()
    result: dict[str, Any] = {"evidence": out["refreshed"],
                              "quarterly": quarterly}
    if not quarterly:
        return result

    rows = db.execute_query(
        "SELECT theme_key, stage, status, evidence"
        " FROM theme_registry")
    restaged, promoted, retired = [], [], []
    for r in rows:
        ev = r.get("evidence") or {}
        if isinstance(ev, str):
            ev = json.loads(ev)
        # every row reviewed stamps last_review — the quarter-due flag
        db.execute_update(
            "UPDATE theme_registry SET last_review=CURRENT_DATE"
            " WHERE theme_key=:k", {"k": r["theme_key"]})
        if r["status"] == "candidate":
            # promote when members show real data coverage + some
            # headline traction
            me = (ev.get("members") or {})
            if (me.get("member_coverage") or 0) >= 0.6 and \
                    ((me.get("median_rev_growth") or 0) > 0.1 or
                     (ev.get("news") or {}).get("total", 0) >= 5):
                db.execute_update(
                    "UPDATE theme_registry SET status='active',"
                    " promoted_at=CURRENT_DATE WHERE theme_key=:k",
                    {"k": r["theme_key"]})
                promoted.append(r["theme_key"])
            continue
        new = _restage(r["theme_key"], ev, r["stage"])
        if new and new != r["stage"]:
            db.execute_update(
                "UPDATE theme_registry SET stage=:s"
                " WHERE theme_key=:k",
                {"s": new, "k": r["theme_key"]})
            (retired if new == "exhausted" else restaged).append(
                f"{r['theme_key']}→{new}")

    proposals = _discover(model)
    wrote = 0
    for p in proposals:
        db.execute_update(
            "INSERT INTO theme_registry (theme_key, name, thesis,"
            " stage, status, members, source)"
            " VALUES (:k,:n,:t,'emerging','candidate',"
            " CAST(:m AS jsonb),'llm')"
            " ON CONFLICT (theme_key) DO NOTHING",
            {"k": p["key"], "n": p["name"], "t": p["thesis"],
             "m": json.dumps(p["members"])})
        wrote += 1
    result.update({"restaged": restaged, "retired": retired,
                   "promoted": promoted,
                   "proposals": len(proposals), "candidates": wrote})
    return result


def candidates() -> list[dict]:
    """LLM-proposed themes awaiting evidence — review queue for the
    user (a theme stays candidate until the numbers confirm it)."""
    from app.database import db
    try:
        return [dict(r) for r in db.execute_query(
            "SELECT theme_key, name, thesis, members, evidence,"
            " first_seen, source FROM theme_registry"
            " WHERE status='candidate' ORDER BY first_seen DESC")]
    except Exception:
        return []
