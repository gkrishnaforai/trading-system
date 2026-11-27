"""Explainability contract — every direction/suggestion the system
emits carries a canonical `why` block, journaled alongside the
verdict. The user sees the reasoning, not just the call.

The block (jsonb):

    verdict    the suggestion itself (deploy / accumulate / trim /
               exit / watch / risk-on / fading …)
    summary    one line — the case in plain terms
    basis      the evidence legs that drove it
               [{name, score?, value}] — journaled inputs only
    drivers    what changed to produce the call
               ["checks 2→3", "reserves +19B/1w"]
    counter    honest counter-evidence — REQUIRED for investable
               direction; a suggestion with no stated risk is an
               incomplete suggestion
    coverage   share of the scorecard that was measurable (0-1);
               weak coverage degrades confidence, never fills in
    refs       provenance — [{table, id}] or claim ids
    rule       the deterministic rule/gate that produced the verdict
               ("score≥55 + not broken + valuation ok → deploy")

Rules (baked in, not conventional):
  - journaled fields only — never asserts what the data doesn't show
  - missing evidence degrades coverage; it never invents support
  - theme/topic direction, stock suggestions, portfolio actions and
    the brain artifacts (topic_forecasts, topic_edges, stress tests)
    carry this block as a REQUIRED journaled field — a forecast
    without basis is not a forecast, it's a number
"""
from __future__ import annotations

from typing import Any, Iterable, Optional


def _txt(v: Any) -> str:
    """Leg value → short text (numbers compact, strings as-is)."""
    if isinstance(v, float):
        return f"{v:.2f}".rstrip("0").rstrip(".")
    return str(v)


def explain(verdict: Any, *, summary: Optional[str] = None,
            basis: Iterable = (), drivers: Iterable[str] = (),
            counter: Iterable[str] = (), coverage: Optional[float] = None,
            refs: Iterable = (), rule: Optional[str] = None) -> dict:
    """Canonical why-block. Every field optional except verdict —
    but `counter` should accompany anything investable."""
    w = {
        "verdict": str(verdict),
        "summary": summary,
        "basis": [b if isinstance(b, dict) else {"name": str(b)}
                  for b in basis if b is not None],
        "drivers": [str(d) for d in drivers if d],
        "counter": [str(c) for c in counter if c],
        "coverage": coverage,
        "refs": list(refs),
        "rule": rule,
    }
    if not w["summary"]:
        w["summary"] = line(w, verdict=False)
    return w


def line(w: dict, *, verdict: bool = True) -> str:
    """Render the one-line case: 'deploy — growth 28 + tape 22 +
    theme 12 · capped: valuation elevated'."""
    parts: list[str] = []
    if verdict and w.get("verdict"):
        parts.append(str(w["verdict"]))
    basis = " + ".join(
        f"{b.get('name')}"
        + (f" {_txt(b['value'])}" if b.get("value") not in (None, "")
           else f" {b['score']}" if b.get("score") is not None else "")
        for b in (w.get("basis") or []))
    if basis:
        parts.append(basis)
    if w.get("counter"):
        parts.append("capped: " + " · ".join(w["counter"]))
    elif w.get("drivers"):
        parts.append(" · ".join(str(d) for d in w["drivers"][:3]))
    if w.get("coverage") is not None and w["coverage"] < 1:
        parts.append(f"coverage {w['coverage']:.0%}")
    return " — ".join(p for p in parts if p)


def coverage(live: int, total: int) -> Optional[float]:
    """Scorecard measurability — None when the denominator is zero."""
    return round(live / total, 2) if total else None
