"""Nowflation open-data ingest — a daily inflation read between BLS
prints.

The official CPI lands monthly, weeks stale. Nowflation publishes a
daily gauge (what CPI would read refreshed today), a live Realtime
measure, and a pre-registered forecast for the next print — as flat
JSON, no key. We journal what they publish, decompose the fields the
engine consumes, and grade their forecast against the real print
when it lands.

Consumers:
- `fed_path`   inflation-leg fallback — macro_snapshots has been
               empty, so the module never contributed; the gauge is a
               deterministic 0-100 score on the same scale.
- `morning`    catalyst enrichment — 'expected' on the upcoming CPI
               calendar event.
- ledger       `industry_research` claims — the forecast becomes a
               journaled call we grade at print day, independent of
               their own scoreboard.

Nothing here overrides a gate — it feeds scores and narratives.
"""

from __future__ import annotations

import json
import logging
import urllib.request
from datetime import date, datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

REALTIME_URL = "https://nowflation.com/data/realtime.json"
FORECAST_URL = "https://nowflation.com/data/forecast.json"
_TIMEOUT_S = 20

# Inflation module score scale: macro_snapshots module_scores are
# 0-100 where high = disinflation. Map the gauge YoY the same way —
# anchored so a 2% gauge (Fed target) reads ~85 and a 5%+ gauge reads
# ~10. Documented, linear, clamped.
def gauge_to_inflation_score(gauge_yoy: Optional[float]) -> Optional[float]:
    if gauge_yoy is None:
        return None
    return round(max(0.0, min(100.0, 100.0 - (gauge_yoy - 1.5) * 30.0)), 1)


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "trading-system/1.0"})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=_TIMEOUT_S).read())
    except Exception as e:
        try:                                    # terminal fetch failure →
            from app.utils.http_resilience import fail   # ledger + breaker
            fail("nowflation", url, e)
        except Exception:
            pass
        raise


def fetch() -> dict:
    """Pull both flat files and decompose the journaled fields. Raw
    payloads ride along in `raw` — anything we didn't decompose stays
    recoverable."""
    rt = _get(REALTIME_URL)
    fc = _get(FORECAST_URL)
    t = rt.get("today") or {}

    official_gap = None
    if (t.get("cpi_gauge_yoy_pct") is not None and
            t.get("official_cpi_yoy_pct") is not None):
        official_gap = round(float(t["cpi_gauge_yoy_pct"]) -
                             float(t["official_cpi_yoy_pct"]), 3)

    # the displayed headline call is official_projection[0]; the
    # component model alone is forecast[0].central — journal both so
    # the ledger can grade the number they actually publish.
    proj = (fc.get("official_projection") or [])
    model = (fc.get("forecast") or [])
    anchor = fc.get("official_projection_anchor") or {}

    as_of = t.get("date") or rt.get("asof") or fc.get("asof")
    return {
        "as_of": as_of,
        "realtime_yoy_pct": t.get("realtime_yoy_pct"),
        "realtime_dod_pp": t.get("realtime_dod_pp"),
        "realtime_wow_pp": t.get("realtime_wow_pp"),
        "cpi_gauge_yoy_pct": t.get("cpi_gauge_yoy_pct"),
        "cpi_gauge_method": t.get("cpi_gauge_method_version"),
        "official_cpi_yoy_pct": t.get("official_cpi_yoy_pct"),
        "official_cpi_month": t.get("official_cpi_month"),
        "gauge_gap_pp": official_gap,
        "truflation_yoy_pct": t.get("truflation_yoy_pct"),
        "print_forecast_month": (proj[0] or {}).get("month") if proj else anchor.get("month"),
        "print_forecast_yoy": (proj[0] or {}).get("yoy") if proj else anchor.get("yoy"),
        "model_forecast_yoy": (model[0] or {}).get("central") if model else None,
        "model_version": fc.get("model") or rt.get("method_version"),
        "record_type": t.get("record_type"),
        "raw": {"realtime": rt, "forecast": fc},
    }


def journal(row: dict) -> bool:
    """Idempotent per publish date — a same-day republish updates the
    mutable fields (their 'live' record can revise intraday)."""
    if not row.get("as_of"):
        return False
    from app.database import db
    db.execute_update(
        """INSERT INTO nowflation_daily
             (as_of, realtime_yoy_pct, realtime_dod_pp, realtime_wow_pp,
              cpi_gauge_yoy_pct, cpi_gauge_method, official_cpi_yoy_pct,
              official_cpi_month, gauge_gap_pp, truflation_yoy_pct,
              print_forecast_month, print_forecast_yoy,
              model_forecast_yoy, model_version, record_type, raw)
           VALUES
             (CAST(:a AS date), :ry, :rd, :rw, :gy, :gm, :oy, :om, :gap,
              :tf, :pm, :py, :my, :mv, :rt, CAST(:raw AS jsonb))
           ON CONFLICT (as_of) DO UPDATE SET
              realtime_yoy_pct=EXCLUDED.realtime_yoy_pct,
              realtime_dod_pp=EXCLUDED.realtime_dod_pp,
              realtime_wow_pp=EXCLUDED.realtime_wow_pp,
              cpi_gauge_yoy_pct=EXCLUDED.cpi_gauge_yoy_pct,
              cpi_gauge_method=EXCLUDED.cpi_gauge_method,
              official_cpi_yoy_pct=EXCLUDED.official_cpi_yoy_pct,
              official_cpi_month=EXCLUDED.official_cpi_month,
              gauge_gap_pp=EXCLUDED.gauge_gap_pp,
              truflation_yoy_pct=EXCLUDED.truflation_yoy_pct,
              print_forecast_month=EXCLUDED.print_forecast_month,
              print_forecast_yoy=EXCLUDED.print_forecast_yoy,
              model_forecast_yoy=EXCLUDED.model_forecast_yoy,
              model_version=EXCLUDED.model_version,
              record_type=EXCLUDED.record_type,
              raw=EXCLUDED.raw,
              fetched_at=now()""",
        {"a": row["as_of"], "ry": row.get("realtime_yoy_pct"),
         "rd": row.get("realtime_dod_pp"), "rw": row.get("realtime_wow_pp"),
         "gy": row.get("cpi_gauge_yoy_pct"),
         "gm": row.get("cpi_gauge_method"),
         "oy": row.get("official_cpi_yoy_pct"),
         "om": row.get("official_cpi_month"), "gap": row.get("gauge_gap_pp"),
         "tf": row.get("truflation_yoy_pct"),
         "pm": row.get("print_forecast_month"),
         "py": row.get("print_forecast_yoy"),
         "my": row.get("model_forecast_yoy"),
         "mv": row.get("model_version"), "rt": row.get("record_type"),
         "raw": json.dumps(row.get("raw") or {}, default=str)})
    return True


def latest(as_of: Optional[date] = None) -> Optional[dict]:
    from app.database import db
    rows = db.execute_query(
        "SELECT * FROM nowflation_daily WHERE as_of <= CAST(:d AS date)"
        " ORDER BY as_of DESC LIMIT 1",
        {"d": str(as_of or date.today())})
    return rows[0] if rows else None


def inflation_score(as_of: Optional[date] = None) -> Optional[float]:
    """The fed-path inflation-leg value — None when no journal row
    exists (caller keeps its own fallback)."""
    row = latest(as_of)
    if not row:
        return None
    return gauge_to_inflation_score(
        _f(row.get("cpi_gauge_yoy_pct")))


def cpi_event_expected(events: list[dict]) -> list[dict]:
    """Attach the pre-registered forecast to upcoming CPI calendar
    events whose release month matches the forecast month. Returns the
    same list, enriched in place."""
    row = latest()
    if not row or not row.get("print_forecast_month"):
        return events
    fmonth = str(row["print_forecast_month"])       # '2026-11'
    fyoy = _f(row.get("print_forecast_yoy"))
    for e in events:
        if e.get("kind") != "cpi" or fyoy is None:
            continue
        # the CPI release for month M lands in month M+1 — the event's
        # date is the release date, so the covered month is the prior
        # one ('2026-12-10' release covers '2026-11')
        rel = str(e.get("date") or "")[:7]
        try:
            y, m = int(rel[:4]), int(rel[5:7])
            covered = f"{y:04d}-{m - 1:02d}" if m > 1 else f"{y - 1:04d}-12"
        except Exception:
            continue
        if covered == fmonth:
            e["expected"] = fyoy
            e["expected_source"] = "nowflation"
            e["expected_asof"] = str(row.get("as_of"))
    return events


# ------------------------------------------------------------------
# claims — the forecast + the gauge-vs-print gap as journaled,
# gradable industry_research claims
# ------------------------------------------------------------------

def _emit_claims(row: dict) -> int:
    from app.signals import narrative_ledger as nl
    n = 0
    as_of = str(row.get("as_of") or "")
    g, o, om = row.get("cpi_gauge_yoy_pct"), \
        row.get("official_cpi_yoy_pct"), row.get("official_cpi_month")
    if g is not None:
        gap = row.get("gauge_gap_pp")
        direction = ("positive" if (gap or 0) < 0 else
                     "negative" if (gap or 0) > 0.25 else "neutral")
        n += bool(nl.emit(
            "MARKET",
            f"Nowflation CPI gauge {float(g):.2f}% YoY vs official "
            f"{float(o):.1f}% ({om})" if o is not None else
            f"Nowflation CPI gauge {float(g):.2f}% YoY",
            direction=direction, claim_type="industry_research",
            source="nowflation", source_date=as_of,
            evidence_confidence=0.6, outcome_confidence=0.5,
            status="supported",
            created_by="nowflation",
            evidence_refs=[{"kind": "nowflation_daily", "as_of": as_of,
                            "gauge": g, "official": o, "gap_pp": gap}]))
    pm, py = row.get("print_forecast_month"), row.get("print_forecast_yoy")
    if pm and py is not None:
        n += bool(nl.emit(
            "MARKET",
            f"Nowflation forecast: {pm} CPI prints "
            f"{float(py):.2f}% YoY (model {row.get('model_forecast_yoy')})",
            direction="neutral", claim_type="industry_research",
            source="nowflation", source_date=as_of,
            evidence_confidence=0.6, outcome_confidence=0.5,
            status="proposed", created_by="nowflation",
            evidence_refs=[{"kind": "cpi_forecast", "month": pm,
                            "forecast_yoy": py,
                            "model_yoy": row.get("model_forecast_yoy"),
                            "as_of": as_of}]))
    return n


def _grade_forecasts(row: dict) -> int:
    """Resolve forecast claims once the real print is known. The
    newest journal row carries official_cpi_month/yoy — a claim whose
    forecast month has now printed gets confirmed (|err| <= 0.3pp) or
    contradicted, journaled as a 'grade' review."""
    om, oy = row.get("official_cpi_month"), row.get("official_cpi_yoy_pct")
    if not om or oy is None:
        return 0
    from app.database import db
    from app.signals import narrative_ledger as nl
    pend = db.execute_query(
        "SELECT claim_id, claim, evidence_refs FROM narrative_claims"
        " WHERE symbol='MARKET' AND claim_type='industry_research'"
        " AND source='nowflation' AND status='proposed'"
        " AND claim LIKE 'Nowflation forecast%'"
        " ORDER BY id DESC")
    n = 0
    for c in pend or []:
        refs = c.get("evidence_refs") or []
        ref = refs[0] if isinstance(refs, list) and refs else {}
        if ref.get("month") != om:
            continue
        fc = _f(ref.get("forecast_yoy"))
        if fc is None:
            continue
        err = abs(fc - float(oy))
        verdict = "confirmed" if err <= 0.3 else "contradicted"
        if nl.transition(
                c["claim_id"], verdict,
                evidence_refs=[{"kind": "cpi_print", "month": om,
                                "actual_yoy": float(oy),
                                "error_pp": round(err, 3)}],
                actor="nowflation-grade",
                note=f"print {om}: actual {oy}% vs forecast {fc}% "
                     f"(err {err:.2f}pp)",
                review_kind="grade"):
            n += 1
    return n


def _f(v: Any) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except Exception:
        return None


def run() -> dict:
    """Job entry — fetch, journal, emit claims, grade stale
    forecasts. Returns counts for the job journal."""
    try:
        row = fetch()
    except Exception as exc:
        logger.warning("nowflation fetch failed: %s", exc)
        return {"fetched": 0, "error": str(exc)[:200]}
    ok = journal(row)
    claims = 0
    graded = 0
    if ok:
        try:
            claims = _emit_claims(row)
        except Exception as exc:
            logger.warning("nowflation claims failed: %s", exc)
        try:
            graded = _grade_forecasts(row)
        except Exception as exc:
            logger.warning("nowflation grading failed: %s", exc)
    return {"as_of": row.get("as_of"), "journaled": int(ok),
            "gauge_yoy": row.get("cpi_gauge_yoy_pct"),
            "gap_pp": row.get("gauge_gap_pp"),
            "print_forecast": row.get("print_forecast_yoy"),
            "claims_emitted": claims, "claims_graded": graded}
