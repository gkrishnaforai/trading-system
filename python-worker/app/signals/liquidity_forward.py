"""Liquidity forward — the 1–3 month liquidity outlook.

Answers ONE question: are financial-liquidity conditions likely to be
more or less supportive of risk assets over the next 4/8/12 weeks —
as a POSTURE input with a conditional distribution, never a point
call. Positioning crashes are out of scope by design (liquidity is
terrain, not trigger — reserves can rise while equities fall).

Corrections from the spec review baked in:

  two measures      fed_net_liquidity = WALCL − TGA − RRP
                    reserve_plus_rrp_buffer = WRESBAL + RRP — custom
                    buffer measure, labeled as such, never definitive

  positive flows    qt_measured / tga_refill / rrp_release are
                    POSITIVE magnitudes with directional names —
                    no signed-arithmetic ambiguity

  QT triangulation  announced cap (config) vs measured (WALCL slope,
                    labeled context not a clean QT measure) vs actual
                    reserve outcome (WRESBAL Δ). Divergence is a
                    FINDING, journaled — not an error.

  RRP               depletion is a warning CONDITION, not an
                    automatic reserve cliff; rrp_release→reserves is
                    scenario-estimated via rrp_to_reserves_share,
                    never silently 1.0

  credit scenarios  base / stress / recovery per horizon — a spike
                    is not auto-optimistic. VIX kept OUT of credit
                    legs (equity-vol is risk appetite, not credit).

  confidence        per-leg coverage × data_quality × horizon
                    reliability × calibration_status — uncalibrated
                    is capped AND labeled, not fake-precise.

Shadow mode: decision_weight 0 until the calibration harness earns
weight. Journaled to liquidity_forward_snapshots (PIT — a replay
sees what was actually published).
"""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import Any, Optional

import yaml

from app.signals.correction_alarms import _fred_series
from app.signals.liquidity_engine import _band, _BUCKETS, _pct_chg

logger = logging.getLogger(__name__)

_CFG_PATH = Path(__file__).parent / "liquidity_forward.yaml"
_HORIZONS = {"4w": 4, "8w": 8, "12w": 12}


def _cfg() -> dict:
    try:
        return yaml.safe_load(_CFG_PATH.read_text()) or {}
    except Exception as exc:
        logger.debug("liq fwd cfg: %s", exc)
        return {}


def _series(sid: str, days: int = 300) -> list[tuple[date, float]]:
    return _fred_series(sid, days=days)


def _wk_slope(pts: list[tuple[date, float]], weeks: int = 4
              ) -> Optional[float]:
    """$B per week over the last `weeks` weekly observations, signed."""
    if len(pts) < weeks + 1:
        return None
    return (pts[-1][1] - pts[-1 - weeks][1]) / weeks


# ---------------------------- measures ---------------------------------

# FRED units are MIXED: WALCL/WTREGEN/WRESBAL report $M, RRPONTSYD
# reports $B. Everything below is normalized to $B at fetch — no
# field ever carries a raw FRED unit.
_MILLION_SERIES = ("WALCL", "WTREGEN", "WRESBAL")


def _to_b(sid: str, pts: list[tuple[date, float]]
          ) -> list[tuple[date, float]]:
    if sid in _MILLION_SERIES:
        return [(d, v / 1000.0) for d, v in pts]
    return pts


def _measures() -> dict[str, Any]:
    """The two liquidity measures, current levels + 4wk deltas — all
    $B. Both journaled — they are different pools and the payload
    says so; an RRP decline does not guarantee the same dollars
    reach reserves or equities."""
    walcl = _to_b("WALCL", _series("WALCL"))
    tga = _to_b("WTREGEN", _series("WTREGEN"))
    rrp = _series("RRPONTSYD")
    wres = _to_b("WRESBAL", _series("WRESBAL"))
    out: dict[str, Any] = {"series_obs": {}}

    def latest(pts):
        return (pts[-1][1], str(pts[-1][0])) if pts else (None, None)

    wal, wal_d = latest(walcl)
    tg, tg_d = latest(tga)
    rp, rp_d = latest(rrp)
    wr, wr_d = latest(wres)
    out["series_obs"] = {"WALCL": wal_d, "WTREGEN": tg_d,
                         "RRPONTSYD": rp_d, "WRESBAL": wr_d}

    if wal is not None and tg is not None and rp is not None:
        out["fed_net_liquidity"] = round(wal - tg - rp, 1)
    if wr is not None and rp is not None:
        out["reserve_plus_rrp_buffer"] = round(wr + rp, 1)
        out["buffer_note"] = ("custom measure — reserves + RRP buffer;"
                              " an RRP decline does not guarantee the"
                              " same dollars reach reserves")
    out["walcl_b"] = wal
    out["tga_b"] = tg
    out["rrp_b"] = rp
    out["wresbal_b"] = wr

    # signed weekly slopes — displayed, never fed into signed math
    out["walcl_slope_b_wk"] = _wk_slope(walcl)
    out["wresbal_slope_b_wk"] = _wk_slope(wres)
    out["tga_slope_b_wk"] = _wk_slope(tga)
    out["rrp_slope_b_wk"] = _wk_slope(rrp)
    return out


# ---------------------------- scheduled --------------------------------

def _scheduled(m: dict[str, Any], cfg: dict) -> dict[str, Any]:
    """Scheduled mechanics — the only genuinely knowable forward
    inputs. All flows POSITIVE magnitudes with directional names."""
    sc = cfg.get("scheduled") or {}
    caveats: list[str] = []
    out: dict[str, Any] = {}

    # --- QT: announced vs measured vs outcome --------------------------
    qt_ann = sc.get("qt_announced_b_wk")
    walcl_slope = m.get("walcl_slope_b_wk")
    # WALCL falling → assets shrinking → runoff positive magnitude.
    # Labeled context: WALCL moves for non-QT reasons too.
    qt_meas = max(0.0, -(walcl_slope or 0.0))
    out["qt_announced_b_wk"] = qt_ann
    out["qt_measured_b_wk"] = round(qt_meas, 1)
    out["qt_measured_note"] = ("WALCL 4wk slope — broad balance-sheet"
                             " context, not a clean QT measure")
    out["wresbal_delta_b_wk"] = (round(m["wresbal_slope_b_wk"], 1)
                                 if m.get("wresbal_slope_b_wk")
                                 is not None else None)
    if qt_ann is not None and qt_ann > 0:
        div = abs(qt_meas - qt_ann) / qt_ann
        if div > 0.20:
            out["qt_divergence"] = round(div, 2)
            caveats.append(
                f"announced QT {qt_ann:.0f}B/wk vs measured "
                f"{qt_meas:.0f}B/wk — runoff isn't landing as planned")
    elif qt_ann is None:
        caveats.append("no announced QT cap configured — measured "
                       "slope is the only runoff read")

    # --- TGA: target vs fallback trend ---------------------------------
    tga_now = m.get("tga_b")
    tgt = sc.get("tga_target_b")
    wk_tgt = sc.get("tga_weeks_to_target") or 8
    if tga_now is not None and tgt is not None:
        tga_refill = max(0.0, (tgt - tga_now) / wk_tgt)
        out["tga_target_b"] = tgt
        out["tga_basis"] = "announced_target"
    elif tga_now is not None:
        tga_slope = m.get("tga_slope_b_wk")
        tga_refill = max(0.0, tga_slope or 0.0)
        out["tga_target_b"] = None
        out["tga_basis"] = "trailing_4wk_trend"
        caveats.append("no TGA target configured — projection uses "
                       "trailing trend, lower scheduled confidence")
    else:
        tga_refill = None
        caveats.append("no TGA data")
    out["tga_refill_b_wk"] = (round(tga_refill, 1)
                              if tga_refill is not None else None)

    # --- RRP: buffer + release, floored at depletion -------------------
    rrp_now = m.get("rrp_b")
    rrp_slope = m.get("rrp_slope_b_wk")
    proj = cfg.get("projection") or {}
    depl = proj.get("rrp_depleted_b") or 75
    rrp_release = max(0.0, -(rrp_slope or 0.0))   # declining = releasing
    if rrp_now is not None:
        depleted = rrp_now < depl
        out["rrp_remaining_b"] = round(rrp_now, 1)
        out["rrp_buffer_depleted"] = depleted
        if depleted:
            rrp_release = 0.0
            caveats.append("RRP buffer effectively empty — nothing "
                           "left to release")
        elif rrp_release > 0:
            out["weeks_to_rrp_zero"] = round(rrp_now / rrp_release, 1)
        # depletion is a warning CONDITION — escalates only when
        # drains are simultaneously active; never auto-subtracted
        if depleted and ((out.get("tga_refill_b_wk") or 0) > 0
                         or qt_meas > 0):
            out["rrp_warning"] = ("buffer gone while TGA/QT drains "
                                  "active — reserves absorb issuance "
                                  "directly")
    out["rrp_release_b_wk"] = round(rrp_release, 1)
    out["rrp_to_reserves_share"] = sc.get("rrp_to_reserves_share", 0.3)
    out["refunding_flag"] = bool(sc.get("refunding_flag"))
    out["caveats"] = caveats
    return out


# --------------------------- projections -------------------------------

def _project_buffer(m: dict, sc: dict, cfg: dict,
                    weeks: int) -> Optional[float]:
    """reserve_plus_rrp_buffer path — positive-magnitude flows only."""
    proj = cfg.get("projection") or {}
    damp = proj.get("damp", 0.85)
    qt = sc.get("qt_measured_b_wk") or 0.0
    tga = sc.get("tga_refill_b_wk") or 0.0
    rrp_rel = sc.get("rrp_release_b_wk") or 0.0
    share = sc.get("rrp_to_reserves_share") or 0.3
    base = m.get("reserve_plus_rrp_buffer")
    if base is None:
        return None
    delta = 0.0
    for i in range(1, weeks + 1):
        d = damp ** (i - 1)
        wk = (-qt - tga + share * rrp_rel) * d
        delta += wk
    return round(base + delta, 1)


def _project_fed_net(m: dict, sc: dict, cfg: dict,
                     weeks: int) -> Optional[float]:
    """fed_net_liquidity path — QT and TGA-refill drain it; the RRP
    leg subtracts from the conventional measure when it DECLINES
    (RRP is already subtracted in the level) — a falling RRP raises
    fed_net_liquidity mechanically regardless of where cash lands."""
    proj = cfg.get("projection") or {}
    damp = proj.get("damp", 0.85)
    qt = sc.get("qt_measured_b_wk") or 0.0
    tga = sc.get("tga_refill_b_wk") or 0.0
    rrp_rel = sc.get("rrp_release_b_wk") or 0.0
    base = m.get("fed_net_liquidity")
    if base is None:
        return None
    delta = 0.0
    for i in range(1, weeks + 1):
        delta += (-qt - tga + rrp_rel) * (damp ** (i - 1))
    return round(base + delta, 1)


# ----------------------- credit scenarios ------------------------------

def _credit_scenarios(cfg: dict) -> dict[str, Any]:
    """HY / IG / VIX at each horizon under base|stress|recovery.
    Base mean-reverts; stress holds elevated + widens; recovery
    tightens faster. VIX is projected separately — it is risk
    appetite, not a credit leg."""
    proj = cfg.get("projection") or {}
    hy_p = proj.get("hy_persistence", 0.9)
    hy_w = proj.get("hy_stress_widen", 0.10)
    hy_r = proj.get("hy_recovery_persistence", 0.8)
    vx_p = proj.get("vix_persistence", 0.9)

    hy = _series("BAMLH0A0HYM2", days=350)
    ig = _series("BAMLC0A0CM", days=350)
    vx = _series("VIXCLS", days=350)

    def mean_n(pts, n):
        tail = [v for _, v in pts[-n:]] if pts else []
        return sum(tail) / len(tail) if tail else None

    def project(v0, mean_, pers, weeks, widen=0.0):
        if v0 is None:
            return None
        m = mean_ if mean_ is not None else v0
        base = v0 + (m - v0) * (1 - pers ** weeks)
        return round(base + widen * v0, 2)

    out: dict[str, Any] = {"hy": {}, "ig": {}, "vix": {}}
    hy0 = hy[-1][1] if hy else None
    ig0 = ig[-1][1] if ig else None
    vx0 = vx[-1][1] if vx else None
    hy_mu, ig_mu, vx_mu = (mean_n(hy, 200), mean_n(ig, 200),
                         mean_n(vx, 200))
    out["obs"] = {"hy": hy0, "ig": ig0, "vix": vx0,
                  "hy_200d_mean": round(hy_mu, 2) if hy_mu else None,
                  "hy_obs": str(hy[-1][0]) if hy else None,
                  "ig_obs": str(ig[-1][0]) if ig else None,
                  "vix_obs": str(vx[-1][0]) if vx else None}

    for label, wk in _HORIZONS.items():
        # spreads — three scenarios
        for sid, v0, mu, name in (("hy", hy0, hy_mu, "hy"),
                                  ("ig", ig0, ig_mu, "ig")):
            out[name][label] = {
                "base": project(v0, mu, hy_p, wk),
                "stress": project(v0, mu, 1.0, wk, widen=hy_w),
                "recovery": project(v0, mu, hy_r, wk),
            }
        out["vix"][label] = {
            "base": project(vx0, vx_mu, vx_p, wk),
            "stress": round(vx0, 1) if vx0 is not None else None,
            "recovery": project(vx0, vx_mu, 0.8, wk),
        }
    return out


# --------------------------- confidence --------------------------------

def _confidence(m: dict, sc: dict, credit: dict, horizon: str,
                cfg: dict) -> dict[str, Any]:
    """Per-leg coverage × staleness × horizon × calibration. Missing
    TGA hits scheduled, missing RRP hits buffer, missing credit hits
    credit — never one blunt number."""
    conf_cfg = cfg.get("confidence") or {}
    legs: dict[str, float] = {}

    today = date.today()
    obs = m.get("series_obs") or {}

    def staleness(d: Optional[str]) -> float:
        if not d:
            return 0.0
        age = (today - date.fromisoformat(d)).days
        return 1.0 if age <= 7 else 0.8 if age <= 14 else 0.5

    legs["scheduled"] = (
        0.5 if sc.get("tga_basis") == "trailing_4wk_trend" else
        0.0 if sc.get("tga_refill_b_wk") is None else 1.0)
    legs["buffer"] = (staleness(obs.get("RRPONTSYD"))
                      if m.get("rrp_b") is not None else 0.0)
    legs["credit"] = staleness(
        ((credit.get("obs") or {}).get("hy_obs")))
    legs["trend"] = staleness(obs.get("WALCL"))

    coverage = round(sum(legs.values()) / len(legs), 2) if legs else 0
    reliability = (conf_cfg.get("horizon_reliability") or {}) \
        .get(horizon, 0.7)
    uncal = conf_cfg.get("uncalibrated_multiplier", 0.5)
    score = round(coverage * reliability * uncal, 2)
    return {"legs": legs, "coverage": coverage,
            "horizon_reliability": reliability,
            "calibration_status": "uncalibrated",
            "confidence": score}


# ---------------------------- scores -----------------------------------

def _score_horizon(m: dict, sc: dict, credit: dict,
                   weeks: int, label: str) -> dict[str, Any]:
    """Projected legs → the SAME band mapping the live engine uses —
    a projected 60 reads the same scale as a live 60, labeled
    'projected' so nobody mistakes it for a calibrated forecast."""
    buf = _project_buffer(m, sc, _cfg(), weeks)
    fed = _project_fed_net(m, sc, _cfg(), weeks)

    def chg_pct(new, old):
        return (new - old) / abs(old) if new is not None and old else None

    fed_chg = chg_pct(fed, m.get("fed_net_liquidity"))
    buf_chg = chg_pct(buf, m.get("reserve_plus_rrp_buffer"))

    # projected liquidity legs — reuse live _band thresholds
    legs = []
    if fed_chg is not None:
        legs.append({"name": "fed_net_liquidity", "weight": 35,
                     "chg_pct": round(fed_chg, 4),
                     "score": _band(fed_chg, False)})
    if buf_chg is not None:
        legs.append({"name": "reserve_plus_rrp_buffer", "weight": 25,
                     "chg_pct": round(buf_chg, 4),
                     "score": _band(buf_chg, False)})
    hy_p = (credit.get("hy") or {}).get(label) or {}
    for scen in ("base", "stress", "recovery"):
        v = hy_p.get(scen)
        if v is not None:
            # spread level → score via live HY level bands
            from app.signals.liquidity_engine import _hy_level
            legs.append({"name": f"hy_{scen}", "weight": 20,
                         "level": v, "score": _hy_level(v)})
    wsum = sum(l["weight"] for l in legs if l.get("score") is not None)
    score = (round(sum(l["score"] * l["weight"] for l in legs
                      if l.get("score") is not None) / wsum)
             if wsum else None)
    band = next((b for thr, b in _BUCKETS
                 if score is not None and score >= thr), None)
    return {"projected_liquidity_score": score, "band": band,
            "projected": {"fed_net_liquidity": fed,
                          "reserve_plus_rrp_buffer": buf,
                          "fed_chg_pct": (round(fed_chg, 4)
                                          if fed_chg is not None
                                          else None),
                          "hy_scenarios": hy_p,
                          "vix_scenarios":
                              (credit.get("vix") or {}).get(label)},
            "legs": legs}


# ----------------------------- analogs ---------------------------------

def _analogs() -> dict[str, Any]:
    """Liquidity + tape conditioned forward distributions — SPY/QQQ/
    SMH. Delegates to forward_analogs with the liquidity-conditioned
    state vector; low-evidence flags pass through unchanged."""
    try:
        from app.signals import forward_analogs
        return forward_analogs.liquidity_conditioned()
    except Exception as exc:
        logger.debug("liq fwd analogs: %s", exc)
        return {"error": str(exc)[:80]}


# ------------------------------ eval -----------------------------------

def evaluate() -> dict[str, Any]:
    cfg = _cfg()
    m = _measures()
    sc = _scheduled(m, cfg)
    credit = _credit_scenarios(cfg)
    horizons = {}
    for label, wk in _HORIZONS.items():
        s = _score_horizon(m, sc, credit, wk, label)
        s["confidence_detail"] = _confidence(m, sc, credit, label,
                                             cfg)
        s["projected_liquidity_confidence"] = \
            s["confidence_detail"]["confidence"]
        horizons[label] = s

    h8 = horizons["8w"]
    h8s = h8.get("projected_liquidity_score")
    hint = ("defensive" if h8s is not None and h8s < 30 else
            "caution" if h8s is not None and h8s < 50 else
            "supportive" if h8s is not None and h8s >= 65 else
            "neutral" if h8s is not None else
            "insufficient_evidence")

    drivers = []
    if sc.get("tga_refill_b_wk"):
        drivers.append(f"TGA refill ~{sc['tga_refill_b_wk']:.0f}B/wk"
                       f" ({sc.get('tga_basis')})")
    if sc.get("qt_measured_b_wk"):
        drivers.append(f"measured runoff ~{sc['qt_measured_b_wk']:.0f}"
                       "B/wk")
    if sc.get("weeks_to_rrp_zero"):
        drivers.append(f"RRP buffer ~{sc['weeks_to_rrp_zero']}wk "
                       "at current drain")
    if sc.get("rrp_warning"):
        drivers.append(sc["rrp_warning"])

    return {
        "as_of": str(date.today()),
        "horizons": horizons,
        "scenario_distribution": {
            "hy": credit.get("hy"), "ig": credit.get("ig"),
            "vix": credit.get("vix")},
        "scheduled": sc,
        "measures": {
            "fed_net_liquidity": m.get("fed_net_liquidity"),
            "reserve_plus_rrp_buffer":
                m.get("reserve_plus_rrp_buffer"),
            "buffer_note": m.get("buffer_note")},
        "analogs": _analogs(),
        "posture_hint": hint,
        "drivers": drivers,
        "caveats": (sc.get("caveats") or []) +
                   ["positioning events not predictable",
                    "projected scores labeled, not calibrated"],
        "calibration": {"mode": "shadow", "decision_weight": 0},
    }


def run() -> dict[str, Any]:
    """Compute + journal. Called by the liquidity job after the live
    snapshot — shares the fetch budget, zero extra FRED calls beyond
    its own series."""
    from app.database import db
    st = evaluate()
    try:
        db.execute_update(
            "INSERT INTO liquidity_forward_snapshots"
            " (as_of, posture_hint, payload)"
            " VALUES (:d, :p, CAST(:pl AS jsonb))"
            " ON CONFLICT (as_of) DO UPDATE SET"
            " posture_hint=EXCLUDED.posture_hint,"
            " payload=EXCLUDED.payload",
            {"d": date.today(), "p": st["posture_hint"],
             "pl": json.dumps(st, default=str)})
    except Exception as exc:
        logger.warning("liq fwd journal: %s", exc)
        st["journal_error"] = str(exc)[:120]
    return st


def read() -> Optional[dict[str, Any]]:
    """Latest journaled forward state — the card's fast read."""
    from app.database import db
    try:
        rows = db.execute_query(
            "SELECT as_of, payload FROM liquidity_forward_snapshots"
            " ORDER BY as_of DESC LIMIT 1")
        if not rows:
            return None
        p = rows[0].get("payload")
        if isinstance(p, str):
            p = json.loads(p)
        p = p or {}
        p["as_of"] = str(rows[0]["as_of"])
        return p
    except Exception:
        return None
