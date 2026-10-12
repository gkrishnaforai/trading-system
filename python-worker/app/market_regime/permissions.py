"""Market permissions — the Layer-1 gate.

Regime answers "how aggressive can we be?" — not "what to buy".
This module translates (regime, facts, confirmation signals) into a
deterministic permission set + continuous size multiplier for
downstream stock-setup agents.

Deterministic on purpose: this is policy, not interpretation. The LLM
may narrate it but never sets it. Missing data biases conservative —
unknown breadth/macro means tighter permissions, not looser.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from .models import DimensionFacts, MarketPermissions, MarketSnapshot, RegimeLabel


# base policy per regime label — modulated below by scores/signals
_BASE: Dict[RegimeLabel, dict] = {
    RegimeLabel.BULL_LOW_VOL: dict(
        aggressive_long=True, normal_long=True, dip_buying=True,
        breakout_buying="allowed", shorts_allowed=False, leverage=True,
        size_multiplier=1.0),
    RegimeLabel.BULL_HIGH_VOL: dict(
        aggressive_long=False, normal_long=True, dip_buying=True,
        breakout_buying="limited", shorts_allowed=False, leverage=False,
        size_multiplier=0.6),
    RegimeLabel.BULLISH_CORRECTION: dict(
        aggressive_long=False, normal_long=True, dip_buying=True,
        breakout_buying="limited", shorts_allowed=False, leverage=False,
        size_multiplier=0.5),
    RegimeLabel.DISTRIBUTION_RISK: dict(
        aggressive_long=False, normal_long=True, dip_buying=True,
        breakout_buying="limited", shorts_allowed=False, leverage=False,
        size_multiplier=0.5),
    RegimeLabel.DISTRIBUTION: dict(
        aggressive_long=False, normal_long=False, dip_buying=False,
        breakout_buying="avoid", shorts_allowed=True, leverage=False,
        size_multiplier=0.25),
    RegimeLabel.MACRO_RISK_OFF: dict(
        aggressive_long=False, normal_long=True, dip_buying=True,
        breakout_buying="avoid", shorts_allowed=False, leverage=False,
        size_multiplier=0.3),
    RegimeLabel.BEAR: dict(
        aggressive_long=False, normal_long=False, dip_buying=False,
        breakout_buying="avoid", shorts_allowed=True, leverage=False,
        size_multiplier=0.0),
    RegimeLabel.TRANSITION: dict(
        aggressive_long=False, normal_long=False, dip_buying=True,
        breakout_buying="avoid", shorts_allowed=False, leverage=False,
        size_multiplier=0.25),
}

_BREAKOUT_LEVELS = ["allowed", "limited", "avoid"]


def _downgrade_breakout(level: str) -> str:
    i = _BREAKOUT_LEVELS.index(level)
    return _BREAKOUT_LEVELS[min(i + 1, len(_BREAKOUT_LEVELS) - 1)]


def derive_permissions(
    regime: RegimeLabel,
    facts: DimensionFacts,
    snapshot: Optional[MarketSnapshot] = None,
    confirmations: Optional[Dict[str, Dict[str, bool]]] = None,
) -> MarketPermissions:
    """Deterministic permission set for downstream agents."""
    p = dict(_BASE.get(regime, _BASE[RegimeLabel.TRANSITION]))
    notes: List[str] = list(p.pop("notes", []))

    det = facts.deterioration_score
    if det is not None and det < -0.5:
        p["size_multiplier"] *= 0.7
        p["breakout_buying"] = _downgrade_breakout(p["breakout_buying"])
        notes.append(f"deterioration {det:+.2f} — sizing tightened")
        if det < -0.7:
            p["size_multiplier"] *= 0.5
            p["dip_buying"] = False
            notes.append("severe deterioration — dip buying suspended")

    # checklist grew 9 → 13 keys (persistence/absorption/VIX-spike/
    # rates-level) — 6/13 keeps the ~56%-of-signals bar the 5/9 set
    bearish_met = sum(
        1 for v in (confirmations or {}).get("bearish_transition", {}).values()
        if v)
    if bearish_met >= 7:
        p["size_multiplier"] *= 0.75
        p["breakout_buying"] = "avoid"
        notes.append(f"{bearish_met} bearish confirmations met — "
                     "breakouts avoided")

    # conservative bias on missing data
    if facts.breadth == "unknown" or (
        snapshot is not None and snapshot.coverage.get("breadth", 0) < 30
    ):
        p["breakout_buying"] = "avoid"
        notes.append("breadth coverage thin — no breakout confirmation data")
    if facts.trend in ("unknown", "mixed"):
        p["normal_long"] = False
        notes.append("trend unclear — new longs paused")

    p["size_multiplier"] = round(max(0.0, min(1.0, p["size_multiplier"])), 2)
    p["selective_long"] = bool(
        p.get("dip_buying") and p["size_multiplier"] > 0 and
        regime not in {RegimeLabel.BEAR, RegimeLabel.DISTRIBUTION}
    )
    if p["selective_long"] and not p.get("normal_long"):
        notes.append("selective longs allowed only with confirmed stock setup")
    return MarketPermissions(**p, notes=notes)
