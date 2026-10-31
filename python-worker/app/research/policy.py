"""Research recommendation evaluator — first-match over policy.yaml.

Same _cond engine as the other yaml specs; ctx is the scoring ctx
plus derived score fields and hard-gate evaluation. Hard gates are
data-driven (sector yaml risk_gates evaluated in run.py → ctx).
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import yaml

from app.signals.pulse_engine import _cond, _eval_when

logger = logging.getLogger(__name__)

_SPEC_PATH = Path(__file__).parent / "policy.yaml"


@lru_cache(maxsize=4)
def _spec() -> dict:
    return yaml.safe_load(_SPEC_PATH.read_text())


# ------------------------------------------------------------------
# stance explanation — deterministic "why" from the fired rule.
# The recommendation is useless to a human if it can't say WHICH
# evidence crossed WHICH line. `because` restates each matched
# condition with its actual ctx value; `closest` names the nearest
# unfired positive rule so 'research'/'watch' reads as "needs X"
# rather than an opaque verdict.
# ------------------------------------------------------------------
_OP_TXT = {"gte": "≥", "gt": ">", "lt": "<", "lte": "≤",
           "eq": "=", "neq": "≠"}
_POSITIVE = ("accumulate_candidate", "starter_candidate",
             "watch", "hold_review")
# conviction ladder — 'closest' prefers the LOWEST unfired rung,
# not the highest-tier near-miss (watch/hold_review are the rung
# directly above research; starter/accumulate sit higher)
_TIER = {"hold_review": 0, "watch": 0,
         "starter_candidate": 1, "accumulate_candidate": 2}
_NO_CLOSEST = {"exit_thesis", "exit_risk", "trim_candidate"}


def _split_key(k: str) -> tuple[str, str]:
    """Mirror _cond's suffix parsing — multi-word suffixes first."""
    if k.endswith("_not_in"):
        return k[:-7], "not_in"
    if k.endswith("_in"):
        return k[:-3], "in"
    if k.endswith("_is_not"):
        return k[:-7], "is_not"
    if k.endswith("_is"):
        return k[:-3], "is"
    if k.endswith("_gte"):
        return k[:-4], "gte"
    if k.endswith("_gt"):
        return k[:-3], "gt"
    if k.endswith("_lte"):
        return k[:-4], "lte"
    if k.endswith("_lt"):
        return k[:-3], "lt"
    return k, "eq"


def _fmt_actual(v: Any) -> str:
    if v is None:
        return "unknown"
    if isinstance(v, bool):
        return str(v).lower()
    if isinstance(v, float):
        return f"{v:g}"
    return f"'{v}'" if isinstance(v, str) else str(v)


def _explain_cond(k: str, v: Any, c: dict,
                  groups: dict) -> str:
    """One {k: v} when-key → human phrase carrying the ACTUAL value:
    'ai_tailwind 74 ≥ 70', 'thesis_status = deteriorating',
    'hard gate fired (severe_financing)'."""
    if k in ("any", "all"):
        subs = [_explain_cond(kk, vv, c, groups)
                for s in v for kk, vv in s.items()]
        return f"({' or '.join(subs)})" if k == "any" \
            else f"({' and '.join(subs)})"
    if k == "flag":
        return f"flag '{v}' set"
    if k == "not_flag":
        return f"flag '{v}' absent"
    if k == "any_missing":
        return "missing " + ", ".join(str(f) for f in v)
    field, suffix = _split_key(k)
    actual = c.get(field)
    if suffix in _OP_TXT and suffix != "eq":
        return (f"{field} unknown (needs {_OP_TXT[suffix]} {v})"
                if actual is None else
                f"{field} {_fmt_actual(actual)} "
                f"{_OP_TXT[suffix]} {v}")
    if suffix in ("in", "not_in"):
        allowed = v if isinstance(v, (list, tuple)) else \
            (groups.get(v) or [v])
        word = "∈" if suffix == "in" else "∉"
        return (f"{field} unknown (needs {word} "
                f"{', '.join(map(str, allowed))})"
                if actual is None else
                f"{field} {_fmt_actual(actual)} {word} "
                f"{', '.join(map(str, allowed))}")
    if suffix in ("is", "is_not"):
        word = "is" if suffix == "is" else "is not"
        return f"{field} {word} {_fmt_actual(v)}"
    if field == "hard_gate" and v and actual:
        names = c.get("hard_gate_names") or []
        return ("hard gate fired" +
                (f" ({', '.join(names)})" if names else ""))
    return f"{field} = {_fmt_actual(actual)}"


def _explain_when(when: dict, c: dict, groups: dict) -> list[str]:
    return [_explain_cond(k, v, c, groups)
            for k, v in (when or {}).items() if k != "default"]


def _closest(ctx: dict, rules: list, fired: str,
             groups: dict) -> Optional[dict]:
    """Nearest unfired POSITIVE rule — 'research' is opaque without
    'needs X'. Fewest failing conditions wins; ties prefer the
    later (higher-conviction) rule."""
    if fired in _NO_CLOSEST:
        return None
    best = None
    for rule in rules:
        if rule.get("default") or rule.get("action") == fired:
            continue
        if rule.get("action") not in _POSITIVE:
            continue
        when = rule.get("when") or {}
        matched, log = _eval_when(ctx, when, groups)
        if matched:
            continue
        failed = [k for k, s in (log.get("conditions") or {}).items()
                  if s != "pass"]
        # rank (fails, tier): fewest fails wins; ties prefer the
        # lowest conviction rung — 'watch needs tw≥50' is nearer
        # than 'starter needs tw≥70'
        cand = (len(failed), _TIER.get(rule["action"], 9), rule)
        if best is None or cand[:2] < best[:2]:
            best = (*cand[:2], rule, failed)
    if best is None:
        return None
    rule, failed = best[2], best[3]
    return {"action": rule["action"],
            "needs": [_explain_cond(k, rule["when"][k], ctx, groups)
                      for k in failed]}


def _reason(ctx: dict, action: str, note: Optional[str],
            when: dict, flags_detail: list[str],
            missing: list, groups: dict,
            rules: list, is_default: bool) -> dict:
    because = [] if is_default else _explain_when(when, ctx, groups)
    out = {"meaning": note, "because": because}
    if flags_detail:
        out["flags"] = flags_detail
    gaps = sorted({m.split(":", 1)[-1] for m in missing})
    if gaps:
        out["gaps"] = gaps[:8]
    closest = _closest(ctx, rules, action, groups)
    if closest:
        out["closest"] = closest
    return out


def evaluate(ctx: dict) -> dict:
    spec = _spec()
    groups = spec.get("groups") or {}
    rules = spec.get("rules") or []
    missing: list = []
    flags: list = []
    flags_detail: list = []
    for f in spec.get("flags") or []:
        matched, log = _eval_when(ctx, f.get("when") or {}, groups)
        missing.extend(log.get("missing") or [])
        if matched:
            flags.append(f["flag"])
            flags_detail.append(
                f"{f['flag']} — "
                + ", ".join(_explain_when(f.get("when"), ctx,
                                          groups)))
    for rule in rules:
        is_default = bool(rule.get("default"))
        matched = True
        log = {"missing": []}
        if not is_default:
            matched, log = _eval_when(ctx, rule.get("when") or {},
                                      groups)
        missing.extend(log.get("missing") or [])
        if matched:
            action = rule["action"]
            return {
                "action": action,
                "note": rule.get("note"),
                "flags": flags,
                "reason": _reason(ctx, action, rule.get("note"),
                                  rule.get("when"), flags_detail,
                                  missing, groups, rules,
                                  is_default),
                "rules_version": f"research@{spec.get('version')}",
                "missing": sorted(set(missing))}
    return {"action": "research", "flags": flags,
            "rules_version": f"research@{spec.get('version')}",
            "missing": sorted(set(missing))}
