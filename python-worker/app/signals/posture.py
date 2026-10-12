"""Daily trade posture — 'should we initiate anything today?'

Not a day predictor: a permission layer over the regime card's
breadth / forward-prob / stance fields. posture_rules in
pulse_action_rules.yaml is first-match-wins; every eval is journaled
to posture_evals and graded against forward index returns in
posture_outcomes — the journal IS the backtest. Retro-filling evals
over regime_snapshots history gives the backtest its sample without
waiting months.
"""
import json
from datetime import date
from typing import Any, Optional

_BENCH = "QQQ"      # book beta ~1.9 — the book trades like the Nasdaq
_HORIZONS = (1, 5, 10, 20)


def _n(v) -> Optional[float]:
    try:
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def _spec() -> dict:
    from app.signals import pulse_engine
    return pulse_engine._load().get("posture_rules") or {}


def _ctx(payload: dict, stance: Optional[str]) -> dict:
    """regime_snapshots.payload → flat posture condition ctx."""
    b = payload.get("breadth") or {}
    h = payload.get("hedge") or {}
    return {
        "breadth_score": _n(b.get("breadth_score")),
        "hl_broken": _n(b.get("pct_hl_broken")),
        "pct_above_50": _n(b.get("pct_above_50")),
        "pct_20d_low": _n(b.get("pct_20d_low")),
        "pct_up_5d": _n(b.get("pct_up_5d")),
        "p_deeper": _n((payload.get("forward") or {})
                       .get("p_deeper_dip_20d")),
        "stance": stance,
        "regime": payload.get("regime"),
        "hedge_tier": h.get("tier"),
    }


def _pcond(c: dict, when: dict) -> bool:
    """Mini condition eval: <k>_lt/<k>_gt/<k>_in/<k>. Missing ctx
    value fails the rule — you can't prove risk with absent data."""
    for k, v in (when or {}).items():
        cur = c.get(k[:-3] if k.endswith(("_lt", "_gt", "_in")) else k)
        if k.endswith("_lt"):
            if cur is None or not cur < v:
                return False
        elif k.endswith("_gt"):
            if cur is None or not cur > v:
                return False
        elif k.endswith("_in"):
            if cur not in (v or []):
                return False
        elif cur != v:
            return False
    return True


def _thresh(rule: str, cond_key: str, default: float) -> float:
    """meta-learned threshold override — engine_weights carries
    bounded corrections (`posture:{rule}:{cond_key}`); YAML stays
    the structural default."""
    try:
        from app.signals.meta_learn import _weight_num
        return _weight_num(f"posture:{rule}:{cond_key}", default)
    except Exception:
        return default


def evaluate(stance: Optional[str], payload: dict) -> dict:
    """(stance, payload) → {posture, new_longs, shorts, hedge_on,
    note, matched, evidence, instruments}."""
    spec = _spec()
    c = _ctx(payload or {}, stance)
    for r in spec.get("rules") or []:
        when = {k: (_thresh(r["name"], k, v)
                    if k.endswith(("_lt", "_gt")) else v)
                for k, v in (r.get("when") or {}).items()}
        if _pcond(c, when):
            return {"posture": r["posture"], "matched": r["name"],
                    "new_longs": bool(r.get("new_longs")),
                    "shorts": bool(r.get("shorts")),
                    "hedge_on": bool(r.get("hedge_on")),
                    "note": r.get("note"), "evidence": c,
                    "instruments": spec.get("instruments") or {}}
    d = spec.get("default") or {}
    return {"posture": d.get("posture", "neutral"), "matched": "default",
            "new_longs": bool(d.get("new_longs", True)),
            "shorts": bool(d.get("shorts")),
            "hedge_on": bool(d.get("hedge_on")),
            "note": d.get("note"), "evidence": c,
            "instruments": spec.get("instruments") or {}}


def _journal(res: dict, as_of) -> None:
    from app.database import db
    from app.signals import pulse_engine
    db.execute_update(
        "INSERT INTO posture_evals (as_of, posture, new_longs,"
        " shorts, hedge_on, matched_rule, note, evidence,"
        " rules_version) VALUES (:d,:p,:l,:s,:h,:m,:n,"
        " CAST(:e AS jsonb),:rv)"
        " ON CONFLICT (as_of, rules_version) DO NOTHING",
        {"d": as_of, "p": res["posture"], "l": res["new_longs"],
         "s": res["shorts"], "h": res["hedge_on"],
         "m": res.get("matched"), "n": res.get("note"),
         "e": json.dumps(res.get("evidence") or {}),
         "rv": pulse_engine.rules_version()})


def current() -> dict:
    """Latest regime snapshot → posture; journals today's eval
    (first write per day per rules_version wins)."""
    from app.database import db
    r = db.execute_query(
        "SELECT as_of, stance, payload FROM regime_snapshots"
        " ORDER BY as_of DESC, created_at DESC LIMIT 1")
    if not r:
        return {"posture": "unknown",
                "note": "no regime snapshot journaled yet",
                "new_longs": True, "shorts": False, "hedge_on": False}
    row = r[0]
    p = row["payload"]
    if isinstance(p, str):
        p = json.loads(p)
    res = evaluate(row.get("stance"), p)
    res["regime_as_of"] = str(row["as_of"])
    try:
        _journal(res, row["as_of"])
    except Exception:
        pass
    return res


def backfill() -> int:
    """Replay every journaled regime snapshot through the posture
    rules — historical evals give the outcome grading its sample.
    Same first-write-per-day dedup as the live path."""
    from app.database import db
    n = 0
    for row in db.execute_query(
            "SELECT as_of, stance, payload FROM regime_snapshots"
            " ORDER BY as_of"):
        p = row["payload"]
        if isinstance(p, str):
            p = json.loads(p)
        _journal(evaluate(row.get("stance"), p), row["as_of"])
        n += 1
    return n


def grade() -> dict:
    """Fill forward QQQ returns for matured posture_evals rows —
    the accountability half: does the posture predict the tape."""
    from app.database import db
    rows = db.execute_query(
        "SELECT e.id, e.as_of, e.posture FROM posture_evals e"
        " LEFT JOIN posture_outcomes o ON o.eval_id = e.id"
        " WHERE o.eval_id IS NULL OR o.graded_at IS NULL")
    graded = 0
    for r in rows or []:
        bars = db.execute_query(
            "SELECT date, close FROM daily_bars WHERE symbol=:b"
            " AND date >= :d ORDER BY date LIMIT 22",
            {"b": _BENCH, "d": r["as_of"]})
        if not bars:
            continue
        base = float(bars[0]["close"])
        fw = {}
        for h in _HORIZONS:
            if len(bars) > h:
                fw[f"fwd_{h}d"] = round(
                    (float(bars[h]["close"]) / base - 1) * 100, 2)
        full = all(f"fwd_{h}d" in fw for h in _HORIZONS)
        db.execute_update(
            "INSERT INTO posture_outcomes (eval_id, as_of, posture,"
            " fwd_1d, fwd_5d, fwd_10d, fwd_20d, graded_at)"
            " VALUES (:i,:d,:p,:f1,:f5,:f10,:f20,"
            " CASE WHEN :full THEN now() ELSE NULL END)"
            " ON CONFLICT (eval_id) DO UPDATE SET"
            " fwd_1d=EXCLUDED.fwd_1d, fwd_5d=EXCLUDED.fwd_5d,"
            " fwd_10d=EXCLUDED.fwd_10d, fwd_20d=EXCLUDED.fwd_20d,"
            " graded_at=EXCLUDED.graded_at",
            {"i": r["id"], "d": r["as_of"], "p": r["posture"],
             "f1": fw.get("fwd_1d"), "f5": fw.get("fwd_5d"),
             "f10": fw.get("fwd_10d"), "f20": fw.get("fwd_20d"),
             "full": full})
        graded += 1
    return {"graded": graded}


def stats() -> list[dict]:
    """Posture → avg forward returns over matured evals — the
    answer to 'does this permission layer have edge'."""
    from app.database import db
    return [dict(r) for r in db.execute_query(
        "SELECT posture, count(*) AS n,"
        " round(avg(fwd_1d),2) AS avg_1d,"
        " round(avg(fwd_5d),2) AS avg_5d,"
        " round(avg(fwd_20d),2) AS avg_20d,"
        " round(avg(fwd_20d) FILTER (WHERE graded_at IS NOT NULL),2)"
        "   AS avg_20d_mature"
        " FROM posture_outcomes GROUP BY posture ORDER BY avg_20d")]
