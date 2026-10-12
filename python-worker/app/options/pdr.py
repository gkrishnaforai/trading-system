"""Portfolio Defense & Recovery card — the composition layer.

NO scoring lives here. Every number is read from an engine that owns
it: defensive_state from the regime graph's persisted snapshots, hedge
card from hedge_book, IV gate + capitulation from crash_alpha, recovery
from options.recovery, put candidates from the shared put_entry scorer.

The card answers three questions: how defensive should we be (state),
how insured are we (hedge book vs target), and what does the recovery
look like once hedges monetize (capital pool + stage)."""
from __future__ import annotations

from typing import Any


def state() -> dict[str, Any]:
    from app.market_regime.defensive_store import DefensiveTransitionStore
    from app.options import crash_alpha, hedge_book, recovery

    ds = {}
    try:
        ds = DefensiveTransitionStore().latest() or {}
    except Exception:
        pass
    try:
        hedge = hedge_book.state()
    except Exception as exc:
        hedge = {"error": str(exc)}
    try:
        iv = crash_alpha.iv_gate()
    except Exception:
        iv = {"status": "unavailable"}
    try:
        cap = crash_alpha.capitulation_score()
    except Exception:
        cap = {}
    try:
        rec = recovery.state()
    except Exception as exc:
        rec = {"error": str(exc)}
    # bear-alpha candidates — journaled only; every row already carries
    # the earnings / chase / narrative gates from the shared scorer
    try:
        puts = crash_alpha.put_entry_scores(limit=5)
    except Exception:
        puts = []
    # AI-rotation environment — the permission layer bear-alpha
    # candidates were scored against
    try:
        from app.signals import theme_rotation
        rot = theme_rotation.current()
        rot = {"score": rot["score"], "band": rot["band"],
               "data_partial": rot["data_partial"]}
    except Exception:
        rot = None

    d_state = ds.get("stage") or "NORMAL"
    return {
        "defensive_state": d_state,
        "theme_rotation": rot,
        "defensive_score": ds.get("score"),
        "defensive_streak": ds.get("streak"),
        "defensive_emergency": ds.get("emergency"),
        "defensive_reasons": ds.get("reasons"),
        "defensive_as_of": str(ds.get("as_of_date") or ""),
        "hedge": hedge,
        "iv_gate": iv,
        "capitulation": {"score": cap.get("score"),
                         "tier": cap.get("tier")},
        "recovery": rec,
        "bear_alpha_candidates": puts,
        "note": "insurance is Engine A; puts are Engine B — journaled "
                "and gated, nothing executes",
    }
