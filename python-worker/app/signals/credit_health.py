"""Canonical market-credit health block — one source of truth for
credit stress as a RISK MODIFIER.

Axis 1 of the two-axis design: market-wide credit conditions. Axis 2
(company balance-sheet vulnerability) lives in pulse_engine's
balance_sheet_state / credit_leg — the axes meet only in the
decision matrix, never merged into one score.

Inputs (per approved spec):
  primary     HY OAS level + 5/20-obs change (BAMLH0A0HYM2)
              IG OAS 20-obs change          (BAMLC0A0CM)
  secondary   HYG/LQD + HYG/IEF relative strength — read from the
              journaled regime payload (dip_character); corroborates
              confidence, never substitutes for spreads
  freshness   mandatory quality gate — stale FRED degrades
              confidence; missing data never infers healthy

States: healthy | caution | stress | severe | unknown.
Hysteresis: enter severe on one corroborated observation; leave it
only after 3 consecutive DISTINCT FRED observations at or below
caution — weekends/holidays/repeats do not advance the exit counter.
severe→stress IS an immediate exit (still restrictive); the hold
only guards the permissive exit.

Journaled to credit_health_snapshots keyed by as_of with fred_asof
for point-in-time replay; backfill() reconstructs history from the
same FRED series so posture backfill grades what credit actually
said on each date.
"""
import logging
import urllib.request
import csv
import io
from datetime import date, timedelta
from typing import Any, Optional

logger = logging.getLogger(__name__)

_HY_OAS = "BAMLH0A0HYM2"     # ICE BofA US High Yield Index OAS
_IG_OAS = "BAMLC0A0CM"       # ICE BofA US Corporate Index OAS (broad IG)
_FRED_CSV = ("https://fred.stlouisfed.org/graph/fredgraph.csv"
             "?id={sid}&cosd={start}")

# state vocabulary — ordered; index = severity rank
_STATES = ("healthy", "caution", "stress", "severe")
_PERMISSIVE = ("healthy", "caution")        # below-the-exit set
_EXIT_OBS = 3                               # distinct obs to leave severe


def _f(v) -> Optional[float]:
    try:
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


# --------------------------- FRED (keyless) ----------------------------

def _fred_series(sid: str, days: int = 120
                 ) -> list[tuple[date, float]]:
    """fredgraph.csv — public, no API key. Same path as
    correction_alarms; (date, value) ascending."""
    start = (date.today() - timedelta(days=days)).isoformat()
    try:
        req = urllib.request.Request(
            _FRED_CSV.format(sid=sid, start=start),
            headers={"User-Agent": "trading-system/credit-health"})
        txt = urllib.request.urlopen(req, timeout=20).read().decode()
        out = []
        for row in csv.DictReader(io.StringIO(txt)):
            v = _f(row.get(sid))
            if v is not None:
                out.append((date.fromisoformat(row["observation_date"]),
                            v))
        return out
    except Exception as e:                                  # noqa: BLE001
        logger.debug("fred csv %s: %s", sid, e)
        return []


def _d(series: list[tuple[date, float]], back: int
       ) -> Optional[float]:
    """Trailing change over `back` observations (business days)."""
    if len(series) <= back:
        return None
    return series[-1][1] - series[-1 - back][1]


def _at(series: list[tuple[date, float]], asof: date
        ) -> tuple[Optional[tuple], Optional[tuple]]:
    """Point-in-time slice: last obs ≤ asof plus the series up to it."""
    hist = [o for o in series if o[0] <= asof]
    return (hist[-1] if hist else None), hist


# ------------------------- the classifier ------------------------------

def _classify(hy: Optional[float], hy_d5: Optional[float],
              hy_d20: Optional[float], ig_d20: Optional[float]
              ) -> tuple[str, str]:
    """Raw state (pre-hysteresis) + why. Bands mirror the alarm's
    existing 3.5/4.5/6% levels and 25/50/75bp velocity bands — the
    alarm warns, this state modifies risk limits; keeping the bands
    identical makes the audit trail readable. Missing velocity →
    level-only bands at one notch lower confidence (handled by the
    caller via `velocity_seen`)."""
    if hy is None:
        return "unknown", "no HY OAS observation"
    legs = []
    # severe — crisis level, or fast widening CONFIRMED by quality
    # credit widening too (stress spreading from junk to IG)
    if hy >= 6.0:
        return "severe", f"HY OAS {hy:.2f}% — crisis level"
    if (hy_d20 is not None and ig_d20 is not None
            and hy_d20 >= 0.75 and ig_d20 >= 0.25):
        return "severe", (f"HY +{hy_d20*100:.0f}bp/20obs widening "
                          f"WITH IG +{ig_d20*100:.0f}bp — stress "
                          f"spreading to quality")
    # stress — elevated level still widening, or fast widening alone
    if hy >= 4.5 and (hy_d20 or 0) >= 0.25:
        legs.append(f"HY {hy:.2f}% elevated AND widening "
                    f"{hy_d20*100:+.0f}bp/20obs")
        return "stress", "; ".join(legs)
    if hy_d20 is not None and hy_d20 >= 0.75:
        return "stress", (f"HY +{hy_d20*100:.0f}bp/20obs — fast "
                          f"widening at {hy:.2f}%")
    if (hy_d20 is not None and ig_d20 is not None
            and hy_d20 >= 0.5 and ig_d20 >= 0.15):
        return "stress", (f"HY +{hy_d20*100:.0f}bp with IG "
                          f"+{ig_d20*100:.0f}bp corroborating")
    # caution — elevated level (≥4.5 flat, ≥3.5 not meaningfully
    # tightening), or meaningful velocity off any base
    if hy >= 4.5:
        return "caution", (f"HY {hy:.2f}% elevated — not widening "
                           f"but above the 4.5% band")
    if hy >= 3.5 and (hy_d20 is None or hy_d20 > -0.10):
        return "caution", (f"HY {hy:.2f}% elevated "
                           f"(d5 {((hy_d5 or 0)*100):+.0f}bp)")
    if hy_d20 is not None and hy_d20 >= 0.5:
        return "caution", (f"HY +{hy_d20*100:.0f}bp/20obs off a "
                           f"{hy:.2f}% base — worth noting")
    return "healthy", f"HY {hy:.2f}% — spreads contained"


def _apply_hysteresis(raw: str, prev_state: Optional[str],
                      below_run: int) -> tuple[str, int]:
    """(raw, previous effective state, distinct-obs run ≤ permissive)
    → (effective, new_run). Enter severe instantly — a brake's
    false-positive cost is low. Exit severe only after _EXIT_OBS
    distinct FRED observations at/below caution. severe→stress is
    immediate — still restrictive; only the permissive exit is held.
    Missing prev (first row): raw rules."""
    if raw == "severe":
        return "severe", 0
    run = (below_run if raw in _PERMISSIVE else 0)
    if prev_state == "severe":
        if raw in ("stress", "severe"):
            return raw, run
        return (raw if run >= _EXIT_OBS else "severe"), run
    return raw, run


def compute(*, hy_oas=None, hy_oas_d5=None, hy_oas_d20=None,
            ig_oas=None, ig_oas_d20=None, hyg_lqd_5d=None,
            hyg_lqd_20d=None, hyg_ief_20d=None, fred_asof=None,
            stale_days=None, prev_state=None, below_run=0,
            velocity_seen=True) -> dict:
    """Pure: inputs → the credit block. Unit-test surface; current()
    and backfill() both call this."""
    raw, why = _classify(hy_oas, hy_oas_d5, hy_oas_d20, ig_oas_d20)
    if raw == "unknown":
        state, run = "unknown", 0
    else:
        state, run = _apply_hysteresis(raw, prev_state, below_run)
    # confidence — the freshness/completeness gate. Missing HY →
    # unknown+low (never inferred healthy); stale >7d → low; stale
    # 4-7d or missing velocity/ETF corroboration → medium.
    if hy_oas is None:
        conf = "low"
    elif (stale_days or 0) > 7:
        conf = "low"
    elif ((stale_days or 0) > 4 or not velocity_seen
          or ig_oas_d20 is None):
        conf = "medium"
    else:
        conf = "high"
    if state != raw:
        why += f" · hysteresis: held {state} ({run}/{_EXIT_OBS} obs)"
    return {
        "hy_oas": hy_oas, "hy_oas_d5": hy_oas_d5,
        "hy_oas_d20": hy_oas_d20, "ig_oas": ig_oas,
        "ig_oas_d20": ig_oas_d20,
        "hyg_lqd_5d": hyg_lqd_5d, "hyg_lqd_20d": hyg_lqd_20d,
        "hyg_ief_20d": hyg_ief_20d,
        "fred_asof": str(fred_asof) if fred_asof else None,
        "stale_days": stale_days,
        "raw_state": raw, "credit_state": state,
        "below_run": run, "confidence": conf, "why": why}


# --------------------- regime-payload confirms -------------------------

def _etf_confirms() -> dict:
    """HYG/LQD + HYG/IEF RS from the latest journaled regime
    snapshot's dip_character — canonical, PIT, no new fetch path."""
    out = {"hyg_lqd_5d": None, "hyg_lqd_20d": None, "hyg_ief_20d": None}
    try:
        from app.database import db
        import json
        r = db.execute_query(
            "SELECT payload FROM regime_snapshots"
            " ORDER BY as_of DESC, created_at DESC LIMIT 1")
        if not r:
            return out
        p = r[0]["payload"]
        if isinstance(p, str):
            p = json.loads(p)
        dc = (p or {}).get("dip_character") or {}
        out["hyg_lqd_5d"] = _f(dc.get("credit_stress_hyg_lqd_5d"))
        out["hyg_lqd_20d"] = _f(dc.get("hyg_lqd_20d"))
        out["hyg_ief_20d"] = _f(dc.get("hyg_ief_20d"))
    except Exception:
        pass
    return out


# ------------------------- journal + live ------------------------------

def _journal_rows(limit: int = 10) -> list[dict]:
    from app.database import db
    try:
        return [dict(r) for r in db.execute_query(
            "SELECT as_of, fred_asof, raw_state, credit_state,"
            " days_in_state FROM credit_health_snapshots"
            " ORDER BY as_of DESC LIMIT :n", {"n": limit})]
    except Exception:
        return []


def _below_run(rows_desc: list[dict], raw_today: str,
               fred_asof: Optional[date]) -> int:
    """Distinct FRED observation dates in the trailing permissive
    run — today's obs plus journaled raw ≤ caution rows. Same
    fred_asof repeated across journal days counts ONCE: weekends,
    holidays and unchanged FRED prints never advance the counter."""
    seen = set()
    if raw_today in _PERMISSIVE and fred_asof:
        seen.add(str(fred_asof))
    for r in rows_desc:
        if r["credit_state"] != "severe":
            break
        if r["raw_state"] in _PERMISSIVE and r.get("fred_asof"):
            seen.add(str(r["fred_asof"]))
        else:
            break
    return len(seen)


def current(fetch: bool = True, asof: Optional[date] = None,
            hy: Optional[list] = None, ig: Optional[list] = None,
            confirms: Optional[dict] = None,
            prior_rows: Optional[list] = None) -> dict:
    """Fetch/inputs → the live credit block (also the backfill path
    when series+prior_rows are passed). Missing HY → unknown/low —
    never inferred healthy."""
    asof = asof or date.today()
    hy = _fred_series(_HY_OAS, days=1500) if hy is None and fetch \
        else (hy or [])
    ig = _fred_series(_IG_OAS, days=1500) if ig is None and fetch \
        else (ig or [])
    hy_last, hy_hist = _at(hy, asof)
    ig_last, ig_hist = _at(ig, asof)
    hy_lv = hy_last[1] if hy_last else None
    fred_asof = hy_last[0] if hy_last else None
    stale = (asof - fred_asof).days if fred_asof else None
    conf = confirms if confirms is not None else _etf_confirms()
    rows = prior_rows if prior_rows is not None else _journal_rows()
    raw_state_preview = _classify(
        hy_lv, _d(hy_hist, 5), _d(hy_hist, 20),
        _d(ig_hist, 20))[0] if hy_lv is not None else "unknown"
    prev_state = rows[0]["credit_state"] if rows else None
    blk = compute(
        hy_oas=round(hy_lv, 2) if hy_lv is not None else None,
        hy_oas_d5=(round(_d(hy_hist, 5), 2)
                   if _d(hy_hist, 5) is not None else None),
        hy_oas_d20=(round(_d(hy_hist, 20), 2)
                    if _d(hy_hist, 20) is not None else None),
        ig_oas=round(ig_last[1], 2) if ig_last else None,
        ig_oas_d20=(round(_d(ig_hist, 20), 2)
                    if _d(ig_hist, 20) is not None else None),
        fred_asof=fred_asof, stale_days=stale,
        prev_state=prev_state,
        below_run=_below_run(rows, raw_state_preview, fred_asof),
        velocity_seen=len(hy_hist) > 20,
        **{k: conf.get(k) for k in
           ("hyg_lqd_5d", "hyg_lqd_20d", "hyg_ief_20d")})
    if rows and blk["credit_state"] == rows[0]["credit_state"]:
        blk["days_in_state"] = (rows[0].get("days_in_state") or 0) + 1
    else:
        blk["days_in_state"] = 1
    return blk


def snapshot() -> dict:
    """current() journaled — idempotent per day (first write wins;
    a later same-day call returns the journaled row)."""
    from app.database import db
    blk = current()
    try:
        db.execute_update(
            "INSERT INTO credit_health_snapshots (as_of, fred_asof,"
            " hy_oas, hy_oas_d5, hy_oas_d20, ig_oas, ig_oas_d20,"
            " hyg_lqd_5d, hyg_lqd_20d, hyg_ief_20d, raw_state,"
            " credit_state, days_in_state, confidence, stale_days,"
            " below_run, why) VALUES (:d,:fa,:hy,:hd5,:hd20,:ig,:igd,"
            ":hl5,:hl20,:hi20,:raw,:st,:dis,:cf,:sd,:br,:w)"
            " ON CONFLICT (as_of) DO NOTHING",
            {"d": date.today(), "fa": blk["fred_asof"],
             "hy": blk["hy_oas"], "hd5": blk["hy_oas_d5"],
             "hd20": blk["hy_oas_d20"], "ig": blk["ig_oas"],
             "igd": blk["ig_oas_d20"], "hl5": blk["hyg_lqd_5d"],
             "hl20": blk["hyg_lqd_20d"], "hi20": blk["hyg_ief_20d"],
             "raw": blk["raw_state"], "st": blk["credit_state"],
             "dis": blk["days_in_state"], "cf": blk["confidence"],
             "sd": blk["stale_days"], "br": blk["below_run"],
             "w": blk["why"]})
    except Exception as e:                                  # noqa: BLE001
        logger.warning("credit snapshot journal failed: %s", e)
    return blk


def latest(asof: Optional[date] = None) -> Optional[dict]:
    """Latest journaled block ≤ asof — the PIT read for posture ctx
    and backfill. fred_asof ≤ asof, not created_at: the observation
    is what was knowable."""
    from app.database import db
    try:
        r = db.execute_query(
            "SELECT credit_state, confidence, raw_state, fred_asof,"
            " stale_days, hy_oas, why FROM credit_health_snapshots"
            " WHERE fred_asof <= :d ORDER BY fred_asof DESC LIMIT 1",
            {"d": asof or date.today()})
        return dict(r[0]) if r else None
    except Exception:
        return None


def backfill(days: int = 1500) -> int:
    """Replay FRED history → journal rows as_of each observation date.
    The state machine replays IN MEMORY — prev_state, below_run and
    days_in_state carry forward inside the walk (each obs is a
    distinct fred_asof by construction), so the journal reconstructs
    exactly what the live path would have said on each date. PIT by
    construction; ETF confirms absent → confidence notes it."""
    from app.database import db
    hy, ig = _fred_series(_HY_OAS, days=days), _fred_series(_IG_OAS,
                                                           days=days)
    if not hy:
        return 0
    prev_state, run, dis = None, 0, 0
    n = 0
    for i, (obs_date, hy_lv) in enumerate(hy):
        hy_hist, ig_hist = hy[:i + 1], [o for o in ig if o[0] <= obs_date]
        ig_last = ig_hist[-1] if ig_hist else None
        hy_d5, hy_d20, ig_d20 = (_d(hy_hist, 5), _d(hy_hist, 20),
                                 _d(ig_hist, 20))
        raw, _ = _classify(hy_lv, hy_d5, hy_d20, ig_d20)
        # live _below_run includes today's obs in the run — mirror it
        pre_run = (run + 1) if raw in _PERMISSIVE else 0
        blk = compute(
            hy_oas=round(hy_lv, 2),
            hy_oas_d5=round(hy_d5, 2) if hy_d5 is not None else None,
            hy_oas_d20=round(hy_d20, 2) if hy_d20 is not None else None,
            ig_oas=round(ig_last[1], 2) if ig_last else None,
            ig_oas_d20=round(ig_d20, 2) if ig_d20 is not None else None,
            fred_asof=obs_date, stale_days=0,
            prev_state=prev_state, below_run=pre_run,
            velocity_seen=len(hy_hist) > 20)
        state = blk["credit_state"]
        run = blk["below_run"]
        dis = dis + 1 if state == prev_state else 1
        prev_state = state
        try:
            db.execute_update(
                "INSERT INTO credit_health_snapshots (as_of,"
                " fred_asof, hy_oas, hy_oas_d5, hy_oas_d20, ig_oas,"
                " ig_oas_d20, hyg_lqd_5d, hyg_lqd_20d, hyg_ief_20d,"
                " raw_state, credit_state, days_in_state, confidence,"
                " stale_days, below_run, why) VALUES (:d,:fa,:hy,"
                ":hd5,:hd20,:ig,:igd,:hl5,:hl20,:hi20,:raw,:st,:dis,"
                ":cf,:sd,:br,:w) ON CONFLICT (as_of) DO NOTHING",
                {"d": obs_date, "fa": obs_date, "hy": blk["hy_oas"],
                 "hd5": blk["hy_oas_d5"], "hd20": blk["hy_oas_d20"],
                 "ig": blk["ig_oas"], "igd": blk["ig_oas_d20"],
                 "hl5": None, "hl20": None, "hi20": None,
                 "raw": blk["raw_state"], "st": state,
                 "dis": dis, "cf": blk["confidence"],
                 "sd": blk["stale_days"], "br": run,
                 "w": blk["why"]})
            n += 1
        except Exception as e:                              # noqa: BLE001
            logger.debug("credit backfill %s: %s", obs_date, e)
    return n
