"""Forward growth — the own-model side of the expectation gap.

Three deterministic pieces, one module:

1. PRODUCT-RAMP UPLIFT — product_initiatives carry scenario buckets
   (bear/base/bull incremental revenue at FY+1 and FY+3, dollars not
   percentages). compute_uplift() aggregates them into stocks.
   emerging_growth + fwd_detail so every screener reads the same flag.
   Buckets are deliberately coarse: TAM × capture × commercialization
   math on a pre-revenue product manufactures false precision — a
   bounded bucket is the honest estimate.

2. FORECAST JOURNAL — growth_forecast_snapshots writes one
   point-in-time row per symbol per day: the consensus view
   (fwd estimates, revisions) AND our flags (fundamental state,
   revision grade, priced status, emerging growth). Answers "what did
   the engine believe on date X" — the audit trail the calibration
   harness runs on. Never COALESCE-forwarded; missing is missing.

3. CALIBRATION — forecast_actuals grades aged snapshots against the
   realized flywheel metrics at each horizon. The interesting error
   isn't point-forecast accuracy yet — it's conditional outcomes:
   "did A+ revision names' growth hold up" — so actuals store the
   snapshot's metric level vs the realized level at horizon and the
   drift, groupable by any flag cohort.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from typing import Any, Optional

logger = logging.getLogger(__name__)

MODEL_VERSION = "fwd_growth.v1"

# scenario weights — same convention as the FV engine's expected value
_BUCKET_W = {"bear": 0.25, "base": 0.55, "bull": 0.20}
# emerging-growth tiers vs forward revenue
_EMERGING_TIERS = [(0.25, "material"), (0.10, "emerging"),
                   (0.03, "option")]
_GRADE_HORIZONS = (90, 365)


# ---------- product-ramp uplift ----------------------------------------

def compute_uplift(sym: str) -> dict:
    """Σ active product initiatives → expected incremental revenue at
    FY+1 / FY+3 and an emerging_growth tier vs forward revenue.
    Missing data widens honesty: an initiative without buckets adds
    nothing but is still counted."""
    from app.database import db
    s = sym.upper()
    inits = db.execute_query(
        "SELECT name, stage, scenario_buckets, incr_margin, confidence"
        " FROM product_initiatives WHERE symbol=:s AND status='active'",
        {"s": s})
    fy1 = fy3 = 0.0
    counted = []
    for r in inits:
        b = r.get("scenario_buckets") or {}
        if isinstance(b, str):
            b = json.loads(b)
        for key, acc in (("fy_plus_1", "fy1"), ("fy_plus_3", "fy3")):
            sc = b.get(key) or {}
            ev = sum(_BUCKET_W[k] * float(sc.get(k) or 0)
                     for k in _BUCKET_W)
            if key == "fy_plus_1":
                fy1 += ev
            else:
                fy3 += ev
        counted.append({"name": r["name"], "stage": r["stage"],
                        "confidence": r["confidence"]})
    if not inits:
        return {"uplift_fy1": None, "uplift_fy3": None,
                "tier": None, "n_initiatives": 0, "initiatives": []}

    fwd_rev = None
    row = db.execute_query(
        "SELECT fwd_rev_avg FROM symbol_flywheel WHERE symbol=:s",
        {"s": s})
    if row and row[0].get("fwd_rev_avg"):
        fwd_rev = float(row[0]["fwd_rev_avg"])
    ratio = (fy3 / fwd_rev) if (fwd_rev and fwd_rev > 0) else None
    tier = (next((t for floor, t in _EMERGING_TIERS
                  if ratio is not None and ratio >= floor), None))
    return {"uplift_fy1": round(fy1, 2), "uplift_fy3": round(fy3, 2),
            "uplift_ratio_fy3": round(ratio, 4) if ratio else None,
            "tier": tier, "n_initiatives": len(inits),
            "initiatives": counted, "fwd_rev_avg": fwd_rev}


def refresh_emerging_growth(symbols: Optional[list[str]] = None) -> dict:
    """Persist stocks.emerging_growth + fwd_detail.emerging for the
    universe (or the symbols that have initiatives)."""
    from app.database import db
    syms = symbols or [r["symbol"] for r in db.execute_query(
        "SELECT DISTINCT symbol FROM product_initiatives"
        " WHERE status='active'")]
    n = 0
    for s in syms:
        try:
            u = compute_uplift(s)
            db.execute_update(
                "UPDATE stocks SET emerging_growth=:t,"
                " fwd_detail = COALESCE(fwd_detail,'{}'::jsonb)"
                " || CAST(:d AS jsonb) WHERE symbol=:s",
                {"s": s, "t": u["tier"],
                 "d": json.dumps({"emerging": u}, default=str)})
            n += 1
        except Exception as exc:
            logger.debug("emerging %s: %s", s, exc)
    return {"symbols": len(syms), "updated": n}


def upsert_initiative(sym: str, name: str, **kw) -> dict:
    """Create/update a product initiative — the evidence-ledger entry
    the ramp model reads. scenario_buckets shape:
    {"fy_plus_1": {"bear": 0, "base": 0, "bull": 0},
     "fy_plus_3": {"bear": 0, "base": 0, "bull": 0}}"""
    from app.database import db
    db.execute_update(
        "INSERT INTO product_initiatives (symbol, name, channel,"
        " segment, stage, addressable_band, scenario_buckets,"
        " incr_margin, confidence, evidence, status, updated_at)"
        " VALUES (:s,:n,:c,:seg,:st,:ab,CAST(:b AS jsonb),:im,:cf,"
        " CAST(:e AS jsonb),:stt,now())"
        " ON CONFLICT (symbol, name) DO UPDATE SET"
        " channel=EXCLUDED.channel, segment=EXCLUDED.segment,"
        " stage=EXCLUDED.stage, addressable_band=EXCLUDED.addressable_band,"
        " scenario_buckets=EXCLUDED.scenario_buckets,"
        " incr_margin=EXCLUDED.incr_margin,"
        " confidence=EXCLUDED.confidence, evidence=EXCLUDED.evidence,"
        " status=EXCLUDED.status, updated_at=now()",
        {"s": sym.upper(), "n": name, "c": kw.get("channel"),
         "seg": kw.get("segment"),
         "st": kw.get("stage") or "concept",
         "ab": kw.get("addressable_band"),
         "b": json.dumps(kw.get("scenario_buckets") or {}),
         "im": kw.get("incr_margin"), "cf": kw.get("confidence"),
         "e": json.dumps(kw.get("evidence") or []),
         "stt": kw.get("status") or "active"})
    return {"symbol": sym.upper(), "name": name,
            **{k: kw.get(k) for k in ("stage", "confidence")}}


# ---------- forecast journal --------------------------------------------

def snapshot_forecasts(symbols: Optional[list[str]] = None) -> dict:
    """Daily point-in-time journal — the consensus view + our flags,
    one row per symbol per model-version per day. Chains to the prior
    snapshot so a forecast's evolution is walkable."""
    from app.database import db
    syms = symbols or [r["symbol"] for r in db.execute_query(
        "SELECT symbol FROM symbol_flywheel")]
    rows = {r["symbol"]: r for r in db.execute_query(
        "SELECT symbol, fwd_eps_avg, fwd_rev_avg, est_revision_pct,"
        " rev_breadth_30d, num_analysts FROM symbol_flywheel"
        " WHERE symbol = ANY(:s)", {"s": syms})}
    flags = {r["symbol"]: r for r in db.execute_query(
        "SELECT symbol, fundamental_state, revision_score,"
        " revision_grade, priced_status, emerging_growth, fwd_detail"
        " FROM stocks WHERE symbol = ANY(:s)", {"s": syms})}
    prev = {r["symbol"]: r["id"] for r in db.execute_query(
        "SELECT DISTINCT ON (symbol) symbol, id"
        " FROM growth_forecast_snapshots WHERE model_version=:v"
        " ORDER BY symbol, as_of DESC", {"v": MODEL_VERSION})}
    uplift = {s: compute_uplift(s) for s in syms
              if (flags.get(s) or {}).get("emerging_growth")}

    written = 0
    for s in syms:
        f, fl = rows.get(s) or {}, flags.get(s) or {}
        u = uplift.get(s) or {}
        try:
            db.execute_update(
                "INSERT INTO growth_forecast_snapshots (symbol, as_of,"
                " model_version, fwd_eps_avg, fwd_rev_avg,"
                " est_revision_pct, rev_breadth_30d, revision_score,"
                " revision_grade, num_analysts, fundamental_state,"
                " priced_status, emerging_growth, fwd_rev_uplift_fy1,"
                " fwd_rev_uplift_fy3, detail, prev_id)"
                " VALUES (:s,CURRENT_DATE,:v,:fe,:fr,:er,:rb,:rs,:rg,"
                " :na,:fs,:ps,:eg,:u1,:u3,CAST(:d AS jsonb),:p)"
                " ON CONFLICT (symbol, as_of, model_version) DO UPDATE"
                " SET fwd_eps_avg=EXCLUDED.fwd_eps_avg,"
                " fwd_rev_avg=EXCLUDED.fwd_rev_avg,"
                " est_revision_pct=EXCLUDED.est_revision_pct,"
                " rev_breadth_30d=EXCLUDED.rev_breadth_30d,"
                " revision_score=EXCLUDED.revision_score,"
                " revision_grade=EXCLUDED.revision_grade,"
                " fundamental_state=EXCLUDED.fundamental_state,"
                " priced_status=EXCLUDED.priced_status,"
                " emerging_growth=EXCLUDED.emerging_growth,"
                " detail=EXCLUDED.detail",
                {"s": s, "v": MODEL_VERSION,
                 "fe": f.get("fwd_eps_avg"), "fr": f.get("fwd_rev_avg"),
                 "er": f.get("est_revision_pct"),
                 "rb": f.get("rev_breadth_30d"),
                 "rs": fl.get("revision_score"),
                 "rg": fl.get("revision_grade"),
                 "na": f.get("num_analysts"),
                 "fs": fl.get("fundamental_state"),
                 "ps": fl.get("priced_status"),
                 "eg": fl.get("emerging_growth"),
                 "u1": u.get("uplift_fy1"), "u3": u.get("uplift_fy3"),
                 "d": json.dumps({"emerging": u} if u else {},
                                 default=str),
                 "p": prev.get(s)})
            written += 1
        except Exception as exc:
            logger.debug("fwd snapshot %s: %s", s, exc)
    return {"snapshotted": written, "model_version": MODEL_VERSION}


# ---------- calibration --------------------------------------------------

_GRADE_METRICS = {"rev_growth": "rev_growth",
                  "eps_growth": "eps_growth",
                  "est_revision_pct": "est_revision_pct"}


def grade_forecasts() -> dict:
    """Aged snapshots → forecast_actuals. 'Forecast' = the metric level
    the snapshot recorded; 'actual' = the level at horizon. The error is
    drift — groupable by revision_grade / fundamental_state cohorts for
    'do A+ names keep improving' calibration."""
    from app.database import db
    graded = 0
    for horizon in _GRADE_HORIZONS:
        snaps = db.execute_query(
            "SELECT s.id, s.symbol, s.as_of, f.rev_growth,"
            " f.eps_growth, f.est_revision_pct"
            " FROM growth_forecast_snapshots s"
            " JOIN symbol_flywheel f ON f.symbol = s.symbol"
            " WHERE s.as_of <= CURRENT_DATE - :h"
            " AND NOT EXISTS (SELECT 1 FROM forecast_actuals a"
            "   WHERE a.snapshot_id = s.id"
            "   AND a.horizon_days = :h)", {"h": horizon})
        for snap in snaps:
            # 'forecast' = the metric level AT the snapshot's as_of —
            # the value the engine was looking at that day, from the
            # same journaled series the snapshot was taken against
            past = db.execute_query(
                "SELECT metrics FROM fundamental_snapshots"
                " WHERE symbol=:s AND as_of <= :d"
                " ORDER BY as_of DESC LIMIT 1",
                {"s": snap["symbol"], "d": snap["as_of"]})
            if not past:
                continue
            pm = past[0].get("metrics") or {}
            if isinstance(pm, str):
                pm = json.loads(pm)
            for metric in _GRADE_METRICS:
                fc = pm.get(metric)
                ac = snap.get(metric)
                if fc is None or ac is None:
                    continue
                err = round(float(ac) - float(fc), 4)
                try:
                    db.execute_update(
                        "INSERT INTO forecast_actuals (symbol,"
                        " snapshot_id, metric, horizon_days, forecast,"
                        " actual, error) VALUES (:s,:i,:m,:h,:f,:a,:e)"
                        " ON CONFLICT (snapshot_id, metric,"
                        " horizon_days) DO NOTHING",
                        {"s": snap["symbol"], "i": snap["id"],
                         "m": metric, "h": horizon,
                         "f": fc, "a": ac, "e": err})
                    graded += 1
                except Exception as exc:
                    logger.debug("grade %s: %s", snap["symbol"], exc)
    return {"graded": graded}


def accuracy_summary() -> dict:
    """Cohort calibration — mean drift per metric by revision_grade and
    fundamental_state. This is the 'did the flag actually precede the
    outcome' number."""
    from app.database import db
    rows = db.execute_query(
        "SELECT s.revision_grade, s.fundamental_state, a.metric,"
        " a.horizon_days, count(*) n,"
        " avg(a.error) mean_drift,"
        " avg(CASE WHEN a.error > 0 THEN 1.0 ELSE 0.0 END) pct_improved"
        " FROM forecast_actuals a"
        " JOIN growth_forecast_snapshots s ON s.id = a.snapshot_id"
        " GROUP BY s.revision_grade, s.fundamental_state, a.metric,"
        " a.horizon_days ORDER BY a.metric, a.horizon_days, n DESC")
    return {"cohorts": rows}
