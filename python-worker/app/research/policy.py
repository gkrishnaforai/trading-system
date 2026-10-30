"""Research recommendation evaluator — first-match over policy.yaml.

Same _cond engine as the other yaml specs; ctx is the scoring ctx
plus derived score fields and hard-gate evaluation. Hard gates are
data-driven (sector yaml risk_gates evaluated in run.py → ctx).
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.signals.pulse_engine import _cond, _eval_when

logger = logging.getLogger(__name__)

_SPEC_PATH = Path(__file__).parent / "policy.yaml"


@lru_cache(maxsize=4)
def _spec() -> dict:
    return yaml.safe_load(_SPEC_PATH.read_text())


def evaluate(ctx: dict) -> dict:
    spec = _spec()
    groups = spec.get("groups") or {}
    missing: list = []
    flags: list = []
    for f in spec.get("flags") or []:
        matched, log = _eval_when(ctx, f.get("when") or {}, groups)
        missing.extend(log.get("missing") or [])
        if matched:
            flags.append(f["flag"])
    for rule in spec.get("rules") or []:
        if rule.get("default"):
            return {"action": rule["action"],
                    "note": rule.get("note"),
                    "flags": flags,
                    "rules_version": f"research@{spec.get('version')}",
                    "missing": sorted(set(missing))}
        matched, log = _eval_when(ctx, rule.get("when") or {}, groups)
        missing.extend(log.get("missing") or [])
        if matched:
            return {"action": rule["action"],
                    "note": rule.get("note"),
                    "flags": flags,
                    "rules_version": f"research@{spec.get('version')}",
                    "missing": sorted(set(missing))}
    return {"action": "research", "flags": flags,
            "rules_version": f"research@{spec.get('version')}",
            "missing": sorted(set(missing))}
