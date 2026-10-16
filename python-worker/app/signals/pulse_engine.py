"""Deterministic action engine — a small interpreter over
pulse_action_rules.yaml. The YAML is the policy; this file holds NO
business rules, only mechanics:

  normalize → stage0 (computed inputs) → stage1 (annotations) →
  stage2 (first-match-wins rules; `add` candidates pass add_policy).

Missing-data contract: a condition on a missing/non-finite input is
FALSE and journals `missing:<field>`. `in`/`not_in` on null are both
false — "not in D" is not the same as "is C". Every fv_* condition
implicitly requires fv_valid — suspect FV is invisible to rules.

The result dict is the journal row: matched rule, every evaluated
condition, annotations, gate outcomes, input snapshot, versions.
"""
from __future__ import annotations

import math
import operator
from pathlib import Path
from typing import Any, Optional

import yaml

RULES_PATH = Path(__file__).parent / "pulse_action_rules.yaml"
ENGINE_VERSION = "pulse_engine.v1"

_OPS = {"gt": operator.gt, "gte": operator.ge,
        "lt": operator.lt, "lte": operator.le}

_spec: Optional[dict] = None


def _load() -> dict:
    global _spec
    if _spec is None:
        _spec = yaml.safe_load(RULES_PATH.read_text())
    return _spec


def rules_version() -> str:
    return f"rules.v{_load()['version']}"


def _num(v) -> Optional[float]:
    """finite float or None — NaN/inf/str/bool are all missing."""
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


# ---------------- stage -1: normalize ---------------------------------

_MISSING_TOKENS = {"", "N/A", "NA", "NONE", "-", "—", "UNKNOWN",
                   "NULL"}


def _norm_grade(v) -> Optional[str]:
    """revision_grade → canonical letter or None. Strips whitespace,
    uppercases, maps missing-tokens to None. A non-null value that
    maps to no class later becomes rev_class=malformed."""
    if v is None:
        return None
    g = str(v).strip().upper()
    return None if g in _MISSING_TOKENS else g


def _normalize(row: dict) -> dict:
    """Raw pulse row → typed input ctx. 'unknown'/'—' states are
    unclassified = missing, not a value."""
    def _state(v):
        return v if v not in (None, "", "unknown", "—") else None
    det = row.get("momentum_detail") or {}
    if isinstance(det, str):
        import json
        det = json.loads(det)
    if not isinstance(det, dict):
        det = {}
    # free-form jsonb: swing can arrive as a string/list — normalizing
    # once here keeps every (det.get("swing") or {}).get() below safe
    _sw = det.get("swing") if isinstance(det.get("swing"), dict) else {}
    return {
        "tape": _state(row.get("mom_state")),
        "tape_dir": row.get("tape_dir"),          # improving|degrading|flat
        "fund": _state(row.get("fund_state")),
        "rev": _norm_grade(row.get("revision_grade")),
        "priced": _state(row.get("priced_status")),
        "fv": _num(row.get("fv_upside")),
        "rsi": _num(row.get("rsi") if row.get("rsi") is not None
                    else det.get("rsi")),
        "vs50": _num(row.get("vs_sma50") if row.get("vs_sma50") is not None
                     else det.get("vs_sma50")),
        "pct_b": _num(det.get("pct_b")),
        "earn_days": _num(row.get("earn_days")),
        "num_analysts": _num(row.get("num_analysts")),
        "flywheel_age_days": _num(row.get("flywheel_age_days")),
        "momentum_age_days": _num(row.get("momentum_age_days")),
        "flags": set(row.get("gq_flags") or []),
        "flags_known": row.get("gq_flags") is not None,
        "sector": (row.get("sector") or "").lower() or None,
        "is_etf": row.get("is_etf"),   # tri-state: True/False/None
        # readiness / repair inputs — momentum_detail subfields plus
        # flywheel, conviction and growth-quality scalars the use-case
        # checklists reference
        "dip_phase": det.get("dip_phase") or row.get("dip_phase"),
        "hist_dir": _num(det.get("hist_dir")
                         if row.get("hist_dir") is None
                         else row.get("hist_dir")),
        "swing_struct": bool(
            _sw.get("hl_seq") or _sw.get("phase")
            or _sw.get("confirm_level")),
        "swing_phase": _sw.get("phase"),
        "confirm_level": _num(_sw.get("confirm_level")),
        "rev_growth": _num(row.get("rev_growth")),
        "eps_growth": _num(row.get("eps_growth")),
        "future_score": _num(row.get("future_score")),
        "lane": row.get("lane"),
        "gq_score": _num(row.get("gq_score")),
        "structural_proof": _num(row.get("structural_proof")),
        # rank inputs — the candidate-ordering layer reads these
        "rs_pct": _num(det.get("rs_pct")),
        "vol_dip": _num(det.get("vol_dip")),
        "atr_pct": _num(det.get("atr_pct")),
        "px": _num(row.get("px") or row.get("close")),
        "swing_low": _num(_sw.get("swing_low")),
        "prior_low": _num(_sw.get("prior_low")),
        "gq_pct": _num(row.get("gq_pct")),
        "emerging": _state(row.get("emerging_growth")),
        "beat_streak": _num(row.get("beat_streak")),
        "est_rev": _num(row.get("est_revision_pct")),
        "sector_score": _num(row.get("sector_score")),
    }


# ---------------- stage 0: computed ------------------------------------

def _stage0(c: dict) -> dict:
    """Single-assignment derived inputs — precedence explicit."""
    spec = _load()
    # fv_valid — null/non-finite or |fv|>75 → unusable
    fv = c["fv"]
    if fv is None:
        fv_valid, fv_note = False, "missing"
    elif fv > 75 or fv < -75:
        fv_valid, fv_note = False, "suspect band"
    else:
        fv_valid, fv_note = True, None
    # rev_class — letter → policy class. Three outcomes: a real class,
    # `missing` (no grade at all), or the spec's configured fallback
    # (default `malformed`) for non-null unrecognized values — a feed
    # defect, not "no coverage"
    rev_spec = spec["computed"]["rev_class"]
    fallback = rev_spec.get("unmapped_non_null", "malformed")
    rev_class = "missing" if c["rev"] is None else fallback
    for cls, grades in rev_spec["map"].items():
        if cls != "missing" and c["rev"] in grades:
            rev_class = cls
            break
    # instrument — TRI-STATE: never default an unresolved instrument
    # to equity. unknown routes to its own review-only policy.
    instrument = ("etf" if c["is_etf"] is True
                  else "unknown" if c["is_etf"] is None else "equity")
    # stop geometry — same stop choice as trade_plans.suggest
    # (swing_low → prior_low → 2×ATR → −8%); distance in ATRs feeds
    # the rank's risk_atr component
    px, atr = c.get("px"), c.get("atr_pct")
    stop = c.get("swing_low") or c.get("prior_low")
    if stop is None and px and atr:
        stop = px * (1 - 2 * atr)
    elif stop is None and px:
        stop = px * 0.92
    risk_atr = (abs(px - stop) / (px * atr)
                if px and stop and atr else None)
    return {"fv_valid": fv_valid, "fv_note": fv_note,
            "rev_class": rev_class, "instrument": instrument,
            "stop_px": round(stop, 2) if stop else None,
            "risk_atr": round(risk_atr, 2) if risk_atr else None}


# ---------------- condition interpreter ---------------------------------

def _resolve_set(v, groups) -> set:
    """Condition value → set of allowed values. Resolves group names
    and {union: [groups]}; explicit lists pass through."""
    if isinstance(v, dict) and "union" in v:
        out = set()
        for g in v["union"]:
            out |= set(groups.get(g, []))
        return out
    if isinstance(v, str) and v in groups:
        return set(groups[v])
    if isinstance(v, (list, set, tuple)):
        return set(v)
    return {v}


def _cond(c: dict, cond: dict, missing: list) -> bool:
    """One {k: v} condition dict → bool; missing inputs record into
    `missing` and evaluate False."""
    groups = _load().get("groups") or {}
    for k, v in cond.items():
        if k == "any":
            # sub-conditions share the same missing log
            return any(_cond(c, s, missing) for s in v)
        if k == "all":
            return all(_cond(c, s, missing) for s in v)
        # multi-word suffixes first — rpartition alone would split
        # `priced_not_in` into field `priced_not` + suffix `in`
        if k.endswith("_not_in"):
            field, suffix = k[:-7], "not_in"
        elif k.endswith("_in"):
            field, suffix = k[:-3], "in"
        elif k.endswith("_is_not"):
            field, suffix = k[:-7], "is_not"
        elif k.endswith("_is"):
            field, suffix = k[:-3], "is"
        else:
            field, _, suffix = k.rpartition("_")
        if suffix in _OPS and field in c:
            actual = c.get(field)
            if field.startswith("fv") and not c["fv_valid"] \
                    and k != "fv_valid":
                missing.append("fv")
                return False
            if actual is None:
                missing.append(field)
                return False
            try:
                if not _OPS[suffix](actual, float(v)):
                    return False
            except TypeError:
                missing.append(field)
                return False
        elif suffix in ("in", "not_in"):
            actual = c.get(field)
            allowed = _resolve_set(v, groups)
            if actual is None:
                missing.append(field)
                return False                 # missing ∈ in AND ∉ not_in
            if suffix == "in" and actual not in allowed:
                return False
            if suffix == "not_in" and actual in allowed:
                return False
        elif suffix == "is":
            if (c.get(field) is None) != (v is None):
                return False
        elif suffix == "is_not":
            if (c.get(field) is not None) != (v is not None):
                return False
        elif k in ("flag", "not_flag"):
            has = v in c["flags"]
            if (k == "flag") != has:
                return False
        elif k == "any_missing":
            if not any(c.get(f) is None for f in v):
                return False
        elif k == "tape_dir":
            if c.get("tape_dir") != v:
                return False
        elif k == "default":
            if not v:
                return False
        elif k in c or k == "extended_metrics":
            # exact equality — bool, str class, or number. A missing
            # computed field is fail, never vacuous-true.
            actual = c.get(k)
            if actual is None:
                missing.append(k)
                return False
            if actual != v:
                return False
        elif k.endswith(("_gt", "_gte", "_lt", "_lte")):
            fld = k.rsplit("_", 1)[0]
            actual = c.get(fld)
            if actual is None:
                missing.append(fld)
                return False
            op = "gte" if k.endswith("_gte") else \
                 "lte" if k.endswith("_lte") else \
                 "gt" if k.endswith("_gt") else "lt"
            try:
                if not _OPS[op](actual, float(v)):
                    return False
            except TypeError:
                missing.append(fld)
                return False
        else:
            missing.append(f"unknown:{k}")    # unknown key ≠ pass
            return False
    return True


def _eval_when(c: dict, when: dict) -> tuple[bool, dict]:
    """Whole `when` block ANDed; returns (matched, per-cond log)."""
    log, miss = {}, []
    ok = True
    for k, v in (when or {}).items():
        r = _cond(c, {k: v}, miss)
        log[k] = ("missing" if any(m.startswith(k.rsplit("_", 1)[0])
                                   for m in miss) else
                  "pass" if r else "fail")
        ok = ok and r
    return ok, {"conditions": log, "missing": sorted(set(miss))}


# ---------------- stage 1: annotations -----------------------------------

def _stage1(c: dict) -> dict:
    spec = _load()["annotations"]
    blocking, confidence_notes = [], []
    for a in spec["blocking"]:
        if _cond(c, a["when"], []):
            blocking.append(a["name"])
    for a in spec["confidence"]:
        m: list = []
        if _cond(c, a.get("when") or {}, m):
            confidence_notes.append(a["name"])
    # risk flags — the contract is 4-state per flag:
    #   true           confirmed risk
    #   false          sufficient valid data confirms the risk absent
    #   unknown        active source, insufficient data to decide —
    #                  blocks `add`, never invents severity
    #   not_applicable sector-exempt — excluded from unverifiable AND
    #                  active (an exempt flag can't block an add)
    #   pending        uncalibrated calc — journaled, exempt from the
    #                  gate until calibrated
    flags, pending = {}, []
    for name, spec_f in (spec.get("risk_flags") or {}).items():
        exempt = {str(s).lower() for s in
                  spec_f.get("sector_exempt") or []}
        if c.get("sector") and c["sector"] in exempt:
            flags[name] = "not_applicable"
            continue
        if spec_f.get("status") == "pending_calibration":
            flags[name] = "pending"
            pending.append(name)
        elif name == "fcf_negative":
            flags[name] = ("fcf_negative" in c["flags"]
                           if c["flags_known"] else "unknown")
        else:
            flags[name] = "unknown"
    return {"blocking": blocking, "confidence": confidence_notes,
            "risk_flags": flags, "risk_pending": pending,
            "hard_risk_active": any(v is True for v in flags.values()),
            "risk_unverifiable": any(v == "unknown"
                                     for v in flags.values())}


# ---------------- formatting ---------------------------------------------

def _fmt(why: str, c: dict, extra: dict) -> str:
    def _fv():
        return f"{c['fv']:+.0f}%" if c["fv_valid"] else "—"
    def _pctf(k):
        return (f"{c[k]:+.0%}" if c.get(k) is not None else "—")
    def _numf(k, d=0):
        return (f"{c[k]:.{d}f}" if c.get(k) is not None else "—")
    vals = {"tape": c.get("tape") or "—", "fund": c.get("fund") or "—",
            "rev": c.get("rev") or "—", "fv": _fv(),
            "priced": c.get("priced") or "—",
            "rsi": _numf("rsi"),
            "vs50": (f"{c['vs50']:+.1%}" if c.get("vs50") is not None
                     else "—"),
            "pct_b": _numf("pct_b", 2),
            "dip_phase": c.get("dip_phase") or "—",
            "hist_dir": _numf("hist_dir", 2),
            "swing_phase": c.get("swing_phase") or "—",
            "confirm": (f"${c['confirm_level']:.0f}"
                        if c.get("confirm_level") is not None else "—"),
            "rev_growth": _pctf("rev_growth"),
            "eps_growth": _pctf("eps_growth"),
            "future_score": _numf("future_score"),
            "lane": c.get("lane") or "—",
            "gq_score": _numf("gq_score"),
            "structural_proof": _numf("structural_proof"),
            "n": (f"{int(c['num_analysts'])}"
                  if c.get("num_analysts") is not None else "—"),
            "age": "—", "gate": "—", "flags": "—",
            "notes": " · ".join(extra.get("notes") or []) or "—"}
    vals.update(extra)
    try:
        return why.format_map(vals)
    except Exception:
        return why


def _confidence(spec_val, c: dict) -> str:
    """'high' | '{high if fv_valid else low}' templates — the only
    supported form is `{A if <ctx_field> else B}` evaluated against
    Stage-0/normalized ctx (never raw inputs), so a template can
    downgrade but can never compute a different action."""
    if not isinstance(spec_val, str):
        return "medium"
    if spec_val.startswith("{"):
        try:
            expr = spec_val.strip("{}")
            a, _, rest = expr.partition(" if ")
            cond, _, b = rest.partition(" else ")
            return a if c.get(cond.strip()) else b
        except Exception:
            return "medium"
    return spec_val


# ---------------- the evaluator -------------------------------------------

def evaluate(row: dict) -> dict:
    spec = _load()
    c = _normalize(row)
    c.update(_stage0(c))
    c["extended_metrics"] = ((c["rsi"] or 0) > 65
                             or (c["vs50"] or 0) > 0.20)
    ann = _stage1(c)
    c["dq_block"] = bool(ann["blocking"])
    c["hard_risk_active"] = ann["hard_risk_active"]
    c["risk_unverifiable"] = ann["risk_unverifiable"]
    c["hard_risk_count"] = sum(1 for v in ann["risk_flags"].values()
                             if v is True)

    rules = (spec["etf_policy"]["rules"] if c["instrument"] == "etf"
             else spec["unknown_policy"]["rules"]
             if c["instrument"] == "unknown"
             else spec["rules"])
    journal: list[dict] = []
    gate_log: dict = {}
    action, label, matched, conf, why = "hold", None, "hold", "medium", \
        "no leg failing, no setup triggering"

    for rule in rules:
        ok, detail = _eval_when(c, rule.get("when"))
        detail["rule"] = rule["name"]
        journal.append(detail)
        if not ok:
            continue
        cand = rule["action"]
        why = _fmt(rule.get("why") or rule["name"], c, {})
        matched, conf = rule["name"], _confidence(
            rule.get("confidence"), c)
        label = rule.get("label")
        if cand == "add":
            # gate evaluates ONLY now — it can never downgrade a rule
            # that selected reduce/trim/watch
            fails = [g for g in spec["add_policy"]["require"]
                     if not _cond(c, g, [])]
            gate_log = {next(iter(g)): ("fail" if g in fails else "pass")
                        for g in spec["add_policy"]["require"]}
            if fails:
                gate = next(iter(fails[0]))
                cand = spec["add_policy"].get("on_fail", "watch")
                label = spec["add_policy"].get("on_fail_label")
                why = (f"add blocked — {gate}") + (
                    f" ({why})" if why else "")
        action = cand
        break

    # dq_block contract: it VETOES `add` via add_policy, and it caps
    # confidence on risk-reducing actions — but it never converts a
    # reduce/trim into hold. Stale data must not force holding risk.
    if ann["blocking"] and action in ("reduce", "trim"):
        conf = "low"

    notes = (ann["blocking"] + ann["confidence"])
    if c.get("tape_dir") == "degrading" and matched != "reduce":
        notes.append("tape degrading vs prior day")
    if c.get("tape_dir") == "improving" and action == "add":
        notes.append("tape improving vs prior day")
    if notes and label not in ("add_blocked",):
        why = f"{why} — {'; '.join(notes)}" if notes else why

    return {"action": action, "label": label, "matched_rule": matched,
            "confidence": conf, "why": why,
            "stage0": {k: c.get(k) for k in
                       ("fv_valid", "rev_class", "instrument",
                        "extended_metrics")},
            "annotations": ann,
            "condition_log": journal,
            "gate_results": gate_log or None,
            "input_snapshot": c,
            "rules_version": rules_version(),
            "engine_version": ENGINE_VERSION}


# ---------------- use-case readiness (Stock page) ----------------------

def eval_use_case(row: dict, name: str) -> dict:
    """YAML-driven readiness checklist — `use_cases.<name>.checks` are
    the same `when` conditions evaluated by the same interpreter with
    the same missing-data semantics as the action rules. State:
    all-pass → ready, n-1 → close, else no."""
    spec = _load()
    c = _normalize(row)
    c.update(_stage0(c))
    checks = (spec.get("use_cases") or {}).get(name, {}) \
                  .get("checks") or []
    rules = []
    for ck in checks:
        miss: list = []
        ok = _cond(c, ck.get("when") or {}, miss)
        rules.append({"ok": bool(ok),
                      "line": _fmt(ck.get("line") or
                                   ck.get("name") or "check", c, {})})
    n = sum(r["ok"] for r in rules)
    state = ("ready" if rules and n == len(rules)
             else "close" if rules and n == len(rules) - 1 else "no")
    return {"state": state, "score": n, "of": len(rules),
            "rules": rules}


# ---------------- candidate ranking -----------------------------------
# Continuous 0-100 ordering INSIDE a use-case's `ready` set. The
# checklist is the binary gate; rank is the order the planner
# deploys capital by. Weights come from YAML `rank_weights`; the
# normalizer per component key lives here — each maps its ctx
# inputs to 0-100, None-able so a missing input drops the weight
# rather than scoring zero (the fv_unusable contract).

def _clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


def _dip(c):
    return {"confirmed": 100, "turning_up": 70,
            "stabilizing": 40}.get(c.get("dip_phase"), 10)


def _tapedir(c):
    return {"improving": 100, "flat": 50,
            "degrading": 0}.get(c.get("tape_dir"), 50)


def _room(c):
    pb = c.get("pct_b")
    rs = c.get("rsi")
    pb_part = (1 - min(pb, 1.3)) * 60 if pb is not None else 30
    rs_part = ((70 - min(rs, 70)) / 20) * 40 if rs is not None else 20
    return _clamp(pb_part + rs_part)


_RANK_NORM = {
    "rs_pct":        lambda c: _clamp(c["rs_pct"]),
    "gq_pct":        lambda c: _clamp(c["gq_pct"]),
    "sector_score":  lambda c: _clamp(c["sector_score"]),
    "dip_phase":     _dip,
    "tape_dir":      _tapedir,
    "vol_dip":       lambda c: _clamp(160 - c["vol_dip"] * 100),
                     # 0.6×vol→100, 1.0→60, ≥1.6→0 (dry-up → climax)
    "risk_atr":      lambda c: _clamp(100 - c["risk_atr"] * 40),
                     # 0.5ATR stop→80, 1.0→60, 2.0→20 — tighter is better
    "revision_grade": lambda c:
        {"A": 100, "B": 70, "C": 30, "D": 0}
        .get((c.get("rev") or "")[:1]),
    "priced_status": lambda c:
        {"not_priced": 100, "partial": 70, "substantial": 40,
         "full": 15, "beyond_lt_avg": 0, "unknown": 50}
        .get(c.get("priced")),
    "fv_upside":     lambda c: _clamp(50 + c["fv"] * 1.5),
                     # +33%→100, 0→50, −33%→0 (only called when fv_valid)
    "fwd_flags":     lambda c: _clamp(
        {"material": 100, "emerging": 70, "option": 40}
        .get(c.get("emerging"), 0)
        + min(c.get("beat_streak") or 0, 5) * 8),
    "trend_intact":  lambda c: 100 if (
        (c.get("vs50") or 0) > 0 and c.get("tape") != "climax") else 0,
    "room_to_run":   _room,
    # penalties — w<0 in YAML; 1.0 = triggered, 0.0 = not
    "earn_risk":     lambda c:
        1.0 if (c.get("earn_days") is not None
                and c["earn_days"] <= 7) else 0.0,
}


_RANK_RAW_ALIAS = {"revision_grade": "rev", "priced_status": "priced"}
                   # yaml component name → normalized ctx key; without
                   # the alias the presence check reads a key that never
                   # exists and the weight silently drops out


def _rank_raw(k: str, c: dict):
    """Presence + raw value for `parts`. None → the component drops
    out and its weight renormalizes (missing ≠ zero)."""
    if k == "fv_upside":
        return c.get("fv") if c.get("fv_valid") else None
    if k == "fwd_flags":
        if c.get("emerging") is None and c.get("beat_streak") is None:
            return None
        return f"emerging={c.get('emerging') or '—'}·beats={c.get('beat_streak') or 0}"
    if k == "trend_intact":
        return c.get("vs50")
    if k == "room_to_run":
        if c.get("pct_b") is None and c.get("rsi") is None:
            return None
        return f"%B={c.get('pct_b')}·rsi={c.get('rsi')}"
    if k == "earn_risk":
        return c.get("earn_days")
    return c.get(_RANK_RAW_ALIAS.get(k, k))


def rank(use_case: str, c: dict) -> dict:
    """ctx (normalized + stage0) → {rank, parts} for a use-case.
    score = Σ(w·norm)/Σw over present components, minus flat
    penalties, then clamped by the first matching `caps` rule."""
    spec = (_load().get("rank_weights") or {}).get(use_case) or {}
    num = den = pens = 0.0
    parts: dict = {}
    for comp in spec.get("weights") or []:
        k = comp.get("k")
        w = _num(comp.get("w"))
        fn = _RANK_NORM.get(k)
        if not fn or w is None:
            continue
        raw = _rank_raw(k, c)
        if raw is None:
            continue
        n = fn(c)
        if w < 0:                       # flat penalty, not a component
            if n:
                pens += abs(w)
            parts[k] = {"raw": raw, "penalty": abs(w) if n else 0}
            continue
        parts[k] = {"raw": raw, "norm": round(n, 1), "w": w}
        num += w * n
        den += w
    score = _clamp((num / den) if den else 0.0)
    score = _clamp(score - pens)
    for cap in spec.get("caps") or []:
        ok, _ = _eval_when(c, cap.get("when") or {})
        if ok:
            parts["_cap"] = {"cap": cap.get("cap"),
                             "when": cap.get("when")}
            score = min(score, _num(cap.get("cap")) or score)
            break
    return {"rank": round(score, 1), "parts": parts}
