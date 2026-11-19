"""Valuation decision — quality × priced-in matrix + bands + thesis
integrity. Spec docs/specs/valuation-priced-in.md Phase 2 + Phase 3.

Composition over journaled rows — growth_priced_in_daily (Phase 1),
symbol_earnings_quality, growth_quality_runs, symbol_flywheel, and the
FV run's decision_scalars. Advisory only: journaled decisions, never
orders — posture/permissions still gate expression.

Three signals, one matrix — never a product:

  business_quality      eq + gq + flywheel, renormalized over present
  priced_in_attractiveness  100 − Phase-1 score (high = reasonable
                        expectations, not "lots priced in")
  thesis_integrity      intact | watch | deteriorating | broken —
                        evidence families like recovery_verdicts; an
                        attractive valuation never overrides broken

Bands:
  entry  price ≤ fv_base × (1−mos), mos = clamp(0.15+0.20×disp,15,30%)
  trim   price ≥ fv_bull → trim; ≥1.10× → exit_core_review
  exit   cheapness alone is NEVER an exit — price < fv_bear +
         integrity intact → reassess (often MORE attractive);
         + deteriorating → thesis_review/exit

Phase 3 alerts (alert_items, fingerprinted):
  expectation_expansion — price outran fwd-EPS drift over the week
  multiple_compression  — drag ≤ −10%/yr within 10% of fv_bull
"""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from typing import Any, Optional

logger = logging.getLogger(__name__)

MODEL_VERSION = "valdec.v1"
_DISPERSION_K = 0.20            # mos = 0.15 + k×dispersion, clamped
_MOS_LO, _MOS_HI = 0.15, 0.30


def _f(x) -> Optional[float]:
    try:
        v = float(x)
        return v if v == v else None
    except (TypeError, ValueError):
        return None


def _load(o) -> Any:
    return json.loads(o) if isinstance(o, str) else o


# ── quality composite ───────────────────────────────────────────────

def _quality(sym: str) -> tuple[Optional[float], list[str]]:
    """business_quality 0-100 — earnings-quality + growth-quality +
    flywheel, renormalized over what exists. Thin inputs → None + note."""
    from app.database import db
    legs, srcs = [], []
    try:
        eq = db.execute_query(
            "SELECT quality FROM symbol_earnings_quality"
            " WHERE symbol=:s ORDER BY as_of DESC LIMIT 1", {"s": sym})
        if eq and _f(eq[0].get("quality")) is not None:
            legs.append(_f(eq[0]["quality"])); srcs.append("eq")
    except Exception:
        pass
    try:
        gq = db.execute_query(
            "SELECT score FROM growth_quality_runs"
            " WHERE symbol=:s ORDER BY as_of DESC LIMIT 1", {"s": sym})
        if gq and _f(gq[0].get("score")) is not None:
            legs.append(_f(gq[0]["score"])); srcs.append("gq")
    except Exception:
        pass
    try:
        fw = db.execute_query(
            "SELECT gap_score FROM symbol_flywheel"
            " WHERE symbol=:s ORDER BY as_of DESC LIMIT 1", {"s": sym})
        if fw and _f(fw[0].get("gap_score")) is not None:
            legs.append(_f(fw[0]["gap_score"])); srcs.append("fw")
    except Exception:
        pass
    if not legs:
        return None, srcs
    return round(sum(legs) / len(legs), 1), srcs


# ── thesis integrity — evidence families ────────────────────────────

def _thesis_integrity(sym: str, scalars: dict) -> tuple[str, list]:
    """intact | watch | deteriorating | broken — each verdict carries
    its named evidence. Cheapness is a valuation condition; THIS is the
    investment condition — they are deliberately separate."""
    from app.database import db
    ev = []                    # {family, level, note}
    rev = _f(scalars.get("est_revision_pct"))
    if rev is None:
        try:
            r = db.execute_query(
                "SELECT est_revision_pct FROM symbol_flywheel"
                " WHERE symbol=:s ORDER BY as_of DESC LIMIT 1",
                {"s": sym})
            rev = _f(r[0]["est_revision_pct"]) if r else None
        except Exception:
            rev = None
    if rev is not None:
        if rev <= -0.15:
            ev.append({"family": "estimates", "level": "deteriorating",
                       "note": f"fwd EPS revised {rev*100:.0f}% — street is cutting"})
        elif rev <= -0.05:
            ev.append({"family": "estimates", "level": "watch",
                       "note": f"fwd EPS revised {rev*100:.0f}%"})
        elif rev >= 0.05:
            ev.append({"family": "estimates", "level": "intact",
                       "note": f"fwd EPS revised +{rev*100:.0f}%"})
    dil = _f(scalars.get("dilution_overhang"))
    if dil is not None and dil > 0.08:
        ev.append({"family": "dilution",
                   "level": "deteriorating" if dil > 0.15 else "watch",
                   "note": f"dilution overhang {dil*100:.0f}%"})
    cc = _f(scalars.get("cash_conversion"))
    if cc is not None and cc < 0.5:
        ev.append({"family": "fcf_conversion", "level": "watch",
                   "note": f"cash conversion {cc*100:.0f}% — earnings not turning to cash"})
    sbc = _f(scalars.get("sbc_to_revenue_ttm"))
    if sbc is not None and sbc > 0.15:
        ev.append({"family": "sbc", "level": "watch",
                   "note": f"SBC {sbc*100:.0f}% of revenue"})
    roic = _f(scalars.get("roic_ttm"))
    if roic is not None and roic < 0:
        ev.append({"family": "capital_returns", "level": "watch",
                   "note": f"ROIC {roic*100:.0f}% — value-destroying on capital"})
    try:
        eq = db.execute_query(
            "SELECT flags FROM symbol_earnings_quality"
            " WHERE symbol=:s ORDER BY as_of DESC LIMIT 1", {"s": sym})
        flags = _load(eq[0]["flags"]) if eq else []
        for fl in (flags or []):
            name = fl if isinstance(fl, str) else str(fl.get("flag", ""))
            if any(k in name for k in ("accrual", "audit", "revenue_quality",
                                       "aggressive")):
                ev.append({"family": "accounting", "level": "deteriorating",
                           "note": f"earnings-quality flag: {name}"})
    except Exception:
        pass
    rank = {"intact": 0, "watch": 1, "deteriorating": 2, "broken": 3}
    worst = max((rank[e["level"]] for e in ev), default=0)
    state = [k for k, v in rank.items() if v == worst][0]
    if rev is not None and rev <= -0.25:
        state = "broken"
    return state, ev


# ── the decision ────────────────────────────────────────────────────

def evaluate(symbol: str, as_of: Optional[date] = None) -> dict:
    from app.database import db
    from app.valuation import growth_priced_in as gpi
    sym = symbol.upper()
    d = as_of or date.today()
    pi_rows = db.execute_query(
        "SELECT * FROM growth_priced_in_daily WHERE symbol=:s"
        " ORDER BY as_of DESC LIMIT 1", {"s": sym})
    pi = dict(pi_rows[0]) if pi_rows else gpi.evaluate(sym, d)

    quality, q_srcs = _quality(sym)
    priced_attr = (round(100 - pi["score"], 1)
                   if _f(pi.get("score")) is not None else None)

    # scalars for integrity — from the FV run the priced-in row cites
    scalars = {}
    try:
        r = db.execute_query(
            "SELECT decision_scalars FROM fair_value_v2_runs"
            " WHERE run_id=:r LIMIT 1", {"r": pi.get("run_id")})
        scalars = _load(r[0]["decision_scalars"]) if r else {}
    except Exception:
        pass
    integrity, evidence = _thesis_integrity(sym, scalars or {})

    price, fv_bear = _f(pi.get("price")), _f(pi.get("fv_bear"))
    fv_base, fv_bull = _f(pi.get("fv_base")), _f(pi.get("fv_bull"))
    disp = _f(pi.get("valuation_dispersion"))
    gap = _f(pi.get("expectation_gap"))
    drag = _f(pi.get("compression_drag"))

    # quadrant matrix — high priced_attr = reasonable expectations
    hi_q = quality is not None and quality >= 60
    lo_q = quality is not None and quality < 60
    hi_a = priced_attr is not None and priced_attr >= 60
    lo_a = priced_attr is not None and priced_attr < 40
    if hi_q and hi_a:
        quadrant = "accumulate"
    elif hi_q and not lo_a:
        quadrant = "hold_wait_pullback"
    elif hi_q:
        quadrant = "wait_valuation_risk"
    elif not lo_q and hi_a:
        quadrant = "selective_watch"
    elif lo_q and hi_a:
        quadrant = "value_trap_watch"
    elif lo_q and lo_a:
        quadrant = "avoid"
    else:
        quadrant = "wait"

    # bands
    mos_req = (max(_MOS_LO, min(_MOS_HI, 0.15 + _DISPERSION_K * disp))
               if disp is not None else _MOS_LO)
    entry_zone = round(fv_base * (1 - mos_req), 2) if fv_base else None

    band, decision, reasons = None, "hold", []
    risk_flags = []
    if integrity == "broken":
        decision, reasons = "avoid", ["thesis broken — valuation irrelevant"]
        risk_flags.append("thesis_broken")
    elif price and fv_bear and price < fv_bear:
        if integrity in ("deteriorating", "broken"):
            decision, band = "exit_review", "thesis_review"
            reasons = [f"price below bear FV ${fv_bear:.0f} AND integrity {integrity}"
                       " — cheapness is not a thesis"]
        else:
            decision, band = "reassess", "below_bear_intact"
            reasons = [f"price below bear FV ${fv_bear:.0f} with integrity intact"
                       " — likely MORE attractive, not less"]
    elif price and fv_bull and price >= fv_bull * 1.10:
        decision, band = "exit_core_review", "extended_beyond_bull"
        reasons = [f"price {price/fv_bull:.0%}× bull FV"]
    elif price and fv_bull and price >= fv_bull:
        decision, band = "trim", "at_bull"
        reasons = [f"price at/above bull FV ${fv_bull:.0f}"]
    elif (price and entry_zone and price <= entry_zone
          and quadrant == "accumulate" and integrity in ("intact", "watch")):
        decision, band = "enter", "entry_zone"
        reasons = [f"price ≤ entry ${entry_zone:.0f} "
                   f"(mos {mos_req*100:.0f}% on dispersion "
                   f"{(disp or 0)*100:.0f}%)"]
    elif quadrant == "avoid":
        decision = "avoid"
        reasons = ["low quality + high priced-in expectations"]
    elif quadrant in ("wait_valuation_risk",):
        decision = "wait"
        reasons = ["good business, expectations too rich — wait for pullback"]
    if drag is not None and drag <= -0.10 and fv_bull and price and \
            price >= 0.90 * fv_bull:
        risk_flags.append("compression_zone")
    return {
        "symbol": sym, "as_of": str(d), "model_version": MODEL_VERSION,
        "business_quality": quality, "quality_sources": q_srcs,
        "priced_in_attractiveness": priced_attr,
        "thesis_integrity": integrity, "integrity_evidence": evidence,
        "quadrant": quadrant, "band": band, "decision": decision,
        "decision_reasons": reasons, "risk_flags": risk_flags,
        "price": price, "fv_bear": fv_bear, "fv_base": fv_base,
        "fv_bull": fv_bull, "entry_zone": entry_zone,
        "mos_required": round(mos_req, 3),
        "expectation_gap": gap, "compression_drag": drag,
        "missing_inputs": pi.get("missing_inputs") or [],
    }


# ── Phase-3 alerts ──────────────────────────────────────────────────

def _emit(sym: str, fp: str, title: str, detail: dict,
          direction: str = "DOWN", materiality: str = "medium") -> bool:
    from app.database import db
    try:
        db.execute_update(
            "INSERT INTO alert_items (symbol, event_type, direction,"
            " materiality, title, detail, fingerprint, source,"
            " source_timestamp, status) VALUES"
            " (:s,'priced_in',:di,:mat,:t,CAST(:de AS jsonb),:fp,"
            " 'valuation_decision',now(),'new')"
            " ON CONFLICT (fingerprint) DO NOTHING",
            {"s": sym, "di": direction, "mat": materiality, "t": title,
             "de": json.dumps(detail, default=str), "fp": fp})
        return True
    except Exception as exc:
        logger.debug("priced_in alert %s: %s", sym, exc)
        return False


def _alerts(sym: str, v: dict, pi_hist: list[dict]) -> int:
    """expectation_expansion + multiple_compression — fingerprinted per
    week so a persistent condition re-fires, never floods."""
    from app.database import db
    n = 0
    wk = date.today().isocalendar()[:2]
    # compression — heavy drag near the bull band
    if "compression_zone" in (v.get("risk_flags") or []):
        n += _emit(sym, f"priced_in:compression:{sym}:{wk[0]}w{wk[1]}",
                   f"{sym}: multiple compression −{abs((v['compression_drag'] or 0))*100:.0f}%/yr "
                   "near bull FV",
                   {"compression_drag": v["compression_drag"],
                    "price": v["price"], "fv_bull": v["fv_bull"]})
    # expectation expansion — price +>15%/wk while fwd EPS flat:
    # the market paying a bigger multiple for the same earnings
    try:
        rows = pi_hist or db.execute_query(
            "SELECT as_of, price, eps_fwd, required_cagr"
            " FROM growth_priced_in_daily WHERE symbol=:s"
            " AND as_of >= :d ORDER BY as_of DESC LIMIT 6",
            {"s": sym, "d": str(date.today() - timedelta(days=8))})
        if len(rows) >= 2:
            newest, oldest = dict(rows[0]), dict(rows[-1])
            dp = _f(newest.get("price"))
            op = _f(oldest.get("price"))
            de = _f(newest.get("eps_fwd"))
            oe = _f(oldest.get("eps_fwd"))
            if dp and op and de and oe and oe > 0:
                pc, ec = dp / op - 1, de / oe - 1
                if pc >= 0.15 and ec <= 0.03:
                    n += _emit(
                        sym, f"priced_in:expansion:{sym}:{wk[0]}w{wk[1]}",
                        f"{sym}: price +{pc*100:.0f}% on +{ec*100:.0f}% fwd EPS "
                        "— multiple expanding",
                        {"price_chg": round(pc, 3), "eps_chg": round(ec, 3),
                         "required_cagr": newest.get("required_cagr")})
    except Exception:
        pass
    return n


def run(symbols: Optional[list[str]] = None) -> dict:
    from app.database import db
    if symbols is None:
        rows = db.execute_query(
            "SELECT DISTINCT symbol FROM growth_priced_in_daily"
            " WHERE as_of >= current_date - interval '10 days'")
        symbols = [r["symbol"] for r in rows]
    out, errs, alerts = {}, [], 0
    for sym in symbols:
        try:
            v = evaluate(sym)
            db.execute_update(
                "INSERT INTO valuation_decisions (symbol, as_of,"
                " business_quality, priced_in_attractiveness,"
                " thesis_integrity, integrity_evidence, quadrant, band,"
                " decision, decision_reasons, risk_flags, price,"
                " fv_bear, fv_base, fv_bull, entry_zone, mos_required,"
                " expectation_gap, compression_drag, model_version,"
                " missing_inputs, detail) VALUES"
                " (:s,:d,:q,:a,:ti,CAST(:ie AS jsonb),:qd,:b,:de,"
                " CAST(:dr AS jsonb),CAST(:rf AS jsonb),:p,:fb,:fv,:fu,"
                " :ez,:mr,:eg,:cd,:mv,CAST(:mi AS jsonb),"
                " CAST(:dt AS jsonb))"
                " ON CONFLICT (symbol, as_of) DO UPDATE SET"
                " business_quality=EXCLUDED.business_quality,"
                " priced_in_attractiveness=EXCLUDED.priced_in_attractiveness,"
                " thesis_integrity=EXCLUDED.thesis_integrity,"
                " quadrant=EXCLUDED.quadrant, band=EXCLUDED.band,"
                " decision=EXCLUDED.decision,"
                " risk_flags=EXCLUDED.risk_flags,"
                " price=EXCLUDED.price, detail=EXCLUDED.detail",
                {"s": sym, "d": v["as_of"], "q": v["business_quality"],
                 "a": v["priced_in_attractiveness"],
                 "ti": v["thesis_integrity"],
                 "ie": json.dumps(v["integrity_evidence"], default=str),
                 "qd": v["quadrant"], "b": v["band"], "de": v["decision"],
                 "dr": json.dumps(v["decision_reasons"]),
                 "rf": json.dumps(v["risk_flags"]),
                 "p": v["price"], "fb": v["fv_bear"], "fv": v["fv_base"],
                 "fu": v["fv_bull"], "ez": v["entry_zone"],
                 "mr": v["mos_required"], "eg": v["expectation_gap"],
                 "cd": v["compression_drag"], "mv": v["model_version"],
                 "mi": json.dumps(v["missing_inputs"]),
                 "dt": json.dumps(v, default=str)})
            out[sym] = v["decision"]
            alerts += _alerts(sym, v, None)
        except Exception as exc:
            errs.append(f"{sym}: {exc}")
    return {"evaluated": len(out), "decisions": out,
            "alerts": alerts, "errors": errs}


def read(symbol: str, days: int = 90) -> list[dict]:
    from app.database import db
    try:
        return db.execute_query(
            "SELECT symbol, as_of, business_quality,"
            " priced_in_attractiveness, thesis_integrity,"
            " integrity_evidence, quadrant, band, decision,"
            " decision_reasons, risk_flags, price, fv_bear, fv_base,"
            " fv_bull, entry_zone, mos_required, expectation_gap,"
            " compression_drag, missing_inputs"
            " FROM valuation_decisions WHERE symbol=:s"
            " ORDER BY as_of DESC LIMIT :n",
            {"s": symbol.upper(), "n": days})
    except Exception:
        return []
