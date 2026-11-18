"""Recovery-verdict snapshots — the read-only input contract.

Every snapshot = {available, as_of, source_ref, ...}. Unavailable is
NOT negative — the verdict lists missing inputs rather than scoring
on guesses. Readers pull journaled state; engines that compute on
demand are wrapped behind the same shape so tests can inject history.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Snap:
    available: bool = False
    as_of: Optional[str] = None
    source_ref: Optional[str] = None
    data: dict = field(default_factory=dict)


def regime_snapshot() -> Snap:
    """Latest morning regime — journaled daily. permissions +
    dip_character ride in buckets."""
    from app.database import db
    rows = db.execute_query(
        "SELECT as_of, regime, ai_regime, score, confidence, buckets"
        " FROM morning_regime_snapshots ORDER BY as_of DESC LIMIT 2")
    if not rows:
        return Snap(source_ref="morning_regime_snapshots")
    r = rows[0]
    b = r.get("buckets") or {}
    perm = b.get("_permissions") or {}
    # stress direction: score improving vs worsening day-over-day
    stress_dir = None
    if len(rows) > 1 and r.get("score") is not None \
            and rows[1].get("score") is not None:
        d = r["score"] - rows[1]["score"]
        stress_dir = ("improving" if d >= 4 else "worsening" if d <= -4
                      else "flat")
    dip = (b.get("dip_character") or b.get("_dip") or {})
    return Snap(available=True, as_of=str(r["as_of"]),
                source_ref="morning_regime_snapshots",
                data={"regime": r.get("regime"), "score": r.get("score"),
                      "confidence": r.get("confidence"),
                      "ai_regime": r.get("ai_regime"),
                      "dip_character": dip.get("label") or dip.get("kind"),
                      "stress_direction": stress_dir,
                      "fragility": (b.get("_fragility") or {}).get("score"),
                      "permissions": perm})


def selloff_snapshot(sym: str) -> Snap:
    from app.database import db
    rows = db.execute_query(
        "SELECT * FROM selloff_candidates WHERE symbol=:s"
        " ORDER BY as_of DESC LIMIT 1", {"s": sym})
    if not rows:
        return Snap(source_ref="selloff_candidates")
    r = rows[0]
    d = r.get("detail") or {}
    return Snap(available=True, as_of=str(r.get("as_of")),
                source_ref="selloff_candidates",
                data={"event_type": r.get("classification")
                                   or d.get("classification"),
                      "score": r.get("score"), "detail": d})


def intraday_snapshot(sym: str) -> Snap:
    from app.database import db
    try:
        rows = db.execute_query(
            "SELECT bar_ts, signal, legs FROM intraday_recovery_evals"
            " WHERE symbol=:s ORDER BY bar_ts DESC LIMIT 1", {"s": sym})
    except Exception:
        return Snap(source_ref="intraday_recovery_evals")
    if not rows:
        return Snap(source_ref="intraday_recovery_evals")
    r = rows[0]
    legs = r.get("legs") or {}
    ctx = legs.get("ctx") or legs
    return Snap(available=True, as_of=str(r.get("bar_ts")),
                source_ref="intraday_recovery_evals",
                data={"signal": r.get("signal"), "detail": ctx})


def tape_snapshot(sym: str) -> Snap:
    """Attribution is compute-on-demand today — needs the inputs
    stock_health gathers, so best-effort with None defaults;
    Phase 2 journals it properly for full point-in-time replay."""
    from app.database import db
    try:
        st = (db.execute_query(
            "SELECT sector, fundamental_state FROM stocks"
            " WHERE symbol=:s", {"s": sym}) or [{}])[0]
        from app.signals.tape_diagnosis import diagnose
        d = diagnose(sym, sector=st.get("sector"),
                     momentum_state=None, momentum_detail={},
                     fundamental_state=st.get("fundamental_state"),
                     priced_status=None, next_earnings=None) or {}
    except Exception:
        return Snap(source_ref="tape_diagnosis(live)")
    return Snap(available=True, as_of=str(d.get("as_of") or ""),
                source_ref="tape_diagnosis(live)", data=d)


def fundamental_snapshot(sym: str) -> Snap:
    from app.database import db
    rows = db.execute_query(
        "SELECT status, status_dir, score, archetype, as_of"
        " FROM symbol_thesis WHERE symbol=:s", {"s": sym})
    fw = db.execute_query(
        "SELECT fundamental_state, fundamental_risk FROM stocks"
        " WHERE symbol=:s", {"s": sym})
    if not rows and not fw:
        return Snap(source_ref="symbol_thesis+stocks")
    t = rows[0] if rows else {}
    f = fw[0] if fw else {}
    return Snap(available=bool(rows or fw),
                as_of=str(t.get("as_of") or ""),
                source_ref="symbol_thesis+stocks",
                data={"thesis_status": t.get("status"),
                      "thesis_dir": t.get("status_dir"),
                      "thesis_score": t.get("score"),
                      "archetype": t.get("archetype"),
                      "fundamental_state": f.get("fundamental_state"),
                      "fundamental_risk": f.get("fundamental_risk")})
