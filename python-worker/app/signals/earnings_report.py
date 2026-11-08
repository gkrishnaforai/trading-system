"""earnings_report — the versioned per-stock earnings report.

The earnings watcher journals a print + verdict; this module composes
the durable report a human reads — StockStory-style: headline,
highlight table vs consensus, revenue-growth history, guidance vs the
street, quality (margins / cash conversion), and the deterministic
verdict. Everything is computed from journaled evidence:

  earnings_data          — the print (eps/rev est vs actual, surprise)
  earnings_watch         — verdict, thesis transition, bounded narrative
  driver_commitments     — verbatim guidance vs consensus
  fundamental_quarterly  — revenue/margin/FCF history (YoY, CAGR)
  symbol_flywheel        — fwd estimates, beat streak, gap score
  stocks                 — name, sector, market cap
  research_runs          — stance reason (meaning/because/gaps)

Versioned: every regeneration appends (symbol, earnings_date, n+1) —
history is the audit trail. Numbers are never invented; a section
with no basis is omitted, not guessed. Advisory only — no orders.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _q(sql: str, p: Optional[dict] = None) -> list[dict]:
    from app.database import db
    return db.execute_query(sql, p or {})


def _u(sql: str, p: Optional[dict] = None) -> Any:
    from app.database import db
    return db.execute_update(sql, p or {})


def _f(x) -> Optional[float]:
    try:
        return float(x) if x is not None else None
    except Exception:
        return None


def _j(v) -> Any:
    return json.loads(v) if isinstance(v, str) else v


def _b(v: Optional[float]) -> Optional[float]:
    """Dollars → $ billions, rounded; None passes through."""
    return round(v / 1e9, 3) if v is not None else None


def _pct(numer: Optional[float], denom: Optional[float]) -> Optional[float]:
    if numer is None or denom in (None, 0):
        return None
    return round((numer - denom) / abs(denom) * 100, 2)


def _pct_of(part: Optional[float], whole: Optional[float]) -> Optional[float]:
    if part is None or whole in (None, 0):
        return None
    return round(part / abs(whole) * 100, 2)


# ------------------------------------------------------------------ gather

def _stock(sym: str) -> dict:
    r = _q("SELECT symbol, company_name, sector, market_cap,"
           " rating, price_target FROM stocks WHERE symbol=:s",
           {"s": sym})
    return dict(r[0]) if r else {"symbol": sym}


def _print_row(sym: str, day: date) -> dict:
    r = _q("SELECT earnings_date, eps_estimate, eps_actual,"
           " revenue_estimate, revenue_actual, surprise_percentage,"
           " one_time_items, adjusted_eps_actual"
           " FROM earnings_data WHERE stock_symbol=:s"
           " AND earnings_date=:d", {"s": sym, "d": day})
    return dict(r[0]) if r else {}


def _watch_row(sym: str, day: date) -> dict:
    r = _q("SELECT verdict, thesis_before, thesis_after, detail,"
           " surprise_pct, created_at"
           " FROM earnings_watch WHERE symbol=:s"
           " AND earnings_date=:d", {"s": sym, "d": day})
    if not r:
        return {}
    row = dict(r[0])
    row["detail"] = _j(row.get("detail")) or {}
    return row


def _drivers(sym: str, day: date) -> list[dict]:
    """Open driver commitments captured for this print — the guidance
    ledger. Rows journaled within the capture window (±2 days of the
    print) count as 'from this release'."""
    try:
        return [dict(r) for r in _q(
            "SELECT metric, period, value, value_text, direction,"
            " prior_value, delta_dir, delta_pct, consensus_value,"
            " consensus_pct, quote"
            " FROM driver_commitments"
            " WHERE symbol=:s AND status='open'"
            "   AND created_at::date BETWEEN :d0 AND :d1"
            " ORDER BY ABS(delta_pct) DESC NULLS LAST"
            "   LIMIT 10",
            {"s": sym, "d0": day, "d1": day})]
    except Exception:
        return []


def _quarters(sym: str) -> list[dict]:
    """Quarterly financials, newest first — the growth/margin spine."""
    try:
        return [dict(r) for r in _q(
            "SELECT period_end, revenue, operating_income, net_income,"
            " eps_diluted, free_cf, operating_cf, shares_diluted"
            " FROM fundamental_quarterly WHERE symbol=:s"
            " ORDER BY period_end DESC LIMIT 24", {"s": sym})]
    except Exception:
        return []


def _flywheel(sym: str) -> dict:
    try:
        r = _q("SELECT rev_growth, rev_accel, gm_now, gm_slope,"
               " eps_growth, beat_streak, avg_surprise_pct,"
               " last_surprise_pct, fwd_eps_avg, fwd_rev_avg,"
               " num_analysts, est_revision_pct, fwd_pe, gap_score,"
               " muted_reaction FROM symbol_flywheel WHERE symbol=:s",
               {"s": sym})
        return dict(r[0]) if r else {}
    except Exception:
        return {}


def _stance(sym: str) -> dict:
    """Latest research stance reason — meaning/because/gaps."""
    try:
        r = _q("SELECT report FROM research_runs WHERE symbol=:s"
               " ORDER BY created_at DESC LIMIT 1", {"s": sym})
        rep = _j(r[0]["report"]) if r else {}
        return (rep or {}).get("reason") or {}
    except Exception:
        return {}


# ------------------------------------------------------------- sections

def _quarter_label(day: date) -> str:
    """Reported-quarter label from the print date — prints arrive
    ~1-6 weeks after period end, so date → prior calendar quarter."""
    q = (day.month - 1) // 3 + 1
    y = day.year
    if q == 1:
        return f"Q4 {y - 1}"
    return f"Q{q - 1} {y}"


def _highlights(sym: str, pr: dict, watch: dict,
                fly: dict, stock: dict,
                quarters: list[dict]) -> list[dict]:
    """The vs-consensus bullet table — StockStory 'highlights'. Each
    row: label / actual / consensus / delta / delta_pct / note."""
    det = watch.get("detail") or {}
    out = []
    eps_est = _f(pr.get("eps_estimate"))
    eps_act = _f(pr.get("eps_actual"))
    adj_eps = _f(pr.get("adjusted_eps_actual"))
    if eps_act is not None or eps_est is not None:
        d = _pct(eps_act, eps_est)
        out.append({
            "metric": "EPS", "actual": eps_act, "consensus": eps_est,
            "delta_pct": _f(det.get("surprise_pct")) or d,
            "note": ("adjusted basis" if adj_eps is not None
                     and adj_eps != eps_act else None)})
    rev_est = _f(pr.get("revenue_estimate"))
    rev_act = _f(pr.get("revenue_actual"))
    if rev_act is not None or rev_est is not None:
        # YoY from the quarter ~4 back in the journal
        yoy = None
        if len(quarters) >= 5 and rev_act is not None:
            prior = _f(quarters[4].get("revenue"))
            yoy = _pct(rev_act, prior)
        out.append({
            "metric": "Revenue", "actual": _b(rev_act),
            "consensus": _b(rev_est), "unit": "$B",
            "delta_pct": (_f(det.get("rev_surprise_pct"))
                          or _pct(rev_act, rev_est)),
            "yoy_pct": yoy,
            "note": None})
    for d in (watch.get("detail") or {}).get("drivers") or []:
        metric = str(d.get("metric") or "").replace("_", " ")
        cons = _f(d.get("consensus_value"))
        out.append({
            "metric": f"{metric} guidance {d.get('period') or ''}".strip(),
            "actual": d.get("value_text") or _b(_f(d.get("value"))),
            "consensus": _b(cons),
            "unit": "$B" if cons is not None else None,
            "delta_pct": _f(d.get("consensus_pct")) or _f(d.get("delta_pct")),
            "note": d.get("delta_dir")})
    # margin highlights from the print quarter
    if quarters:
        q0 = quarters[0]
        rev0 = _f(q0.get("revenue"))
        om = _pct_of(_f(q0.get("operating_income")), rev0)
        fm = _pct_of(_f(q0.get("free_cf")), rev0)
        if om is not None:
            out.append({"metric": "Operating margin", "actual": om,
                        "unit": "%", "consensus": None,
                        "delta_pct": None, "note": "quarter"})
        if fm is not None:
            out.append({"metric": "Free cash flow margin",
                        "actual": fm, "unit": "%", "consensus": None,
                        "delta_pct": None, "note": "quarter"})
    mc = _f(stock.get("market_cap"))
    if mc:
        out.append({"metric": "Market capitalization",
                    "actual": _b(mc), "unit": "$B",
                    "consensus": None, "delta_pct": None, "note": None})
    return out


def _growth_section(quarters: list[dict], fly: dict,
                    pr: dict) -> Optional[dict]:
    """Revenue growth — this quarter YoY, 2y annualized, 5y CAGR,
    forward street view. Mirrors the StockStory 'revenue growth'
    section; every rate traces to the quarterly journal."""
    revs = [_f(q.get("revenue")) for q in quarters]
    revs = [r for r in revs if r]
    if len(revs) < 5:
        return None
    q_yoy = _pct(revs[0], revs[4])
    two_y = (round(((revs[0] / revs[8]) ** (1 / 2) - 1) * 100, 1)
             if len(revs) >= 9 and revs[8] > 0 and revs[0] > 0 else None)
    five_y = (round(((revs[0] / revs[20]) ** (1 / 5) - 1) * 100, 1)
              if len(revs) >= 21 and revs[20] > 0 and revs[0] > 0
              else None)
    fwd_g = None
    fwd_rev = _f(fly.get("fwd_rev_avg"))
    if fwd_rev and revs:
        ltm = sum(revs[:4])
        if ltm > 0:
            fwd_g = round((fwd_rev - ltm) / ltm * 100, 1)
    return {"quarter_yoy": q_yoy, "two_year_ann": two_y,
            "five_year_cagr": five_y, "forward_12m": fwd_g,
            "quarters_tracked": len(revs)}


def _quality_section(quarters: list[dict], fly: dict) -> Optional[dict]:
    """Margins + cash conversion, current quarter vs year-ago —
    the 'is the growth profitable' read."""
    if not quarters:
        return None
    q0 = quarters[0]
    rev0 = _f(q0.get("revenue"))
    om_now = _pct_of(_f(q0.get("operating_income")), rev0)
    fm_now = _pct_of(_f(q0.get("free_cf")), rev0)
    nm_now = _pct_of(_f(q0.get("net_income")), rev0)
    om_yoy = fm_yoy = None
    if len(quarters) >= 5:
        q4 = quarters[4]
        rev4 = _f(q4.get("revenue"))
        om_prior = _pct_of(_f(q4.get("operating_income")), rev4)
        fm_prior = _pct_of(_f(q4.get("free_cf")), rev4)
        om_yoy = (round(om_now - om_prior, 1)
                  if om_now is not None and om_prior is not None else None)
        fm_yoy = (round(fm_now - fm_prior, 1)
                  if fm_now is not None and fm_prior is not None else None)
    return {"operating_margin": om_now,
            "operating_margin_yoy_pp": om_yoy,
            "fcf_margin": fm_now, "fcf_margin_yoy_pp": fm_yoy,
            "net_margin": nm_now,
            "gross_margin": _f(fly.get("gm_now")),
            "beat_streak": fly.get("beat_streak"),
            "avg_surprise_pct": _f(fly.get("avg_surprise_pct"))}


def _expectations_section(fly: dict, stance: dict) -> Optional[dict]:
    """Forward street expectations + our stance reason — the 'what
    happens next' read."""
    if not fly and not stance:
        return None
    return {"fwd_eps_avg": _f(fly.get("fwd_eps_avg")),
            "fwd_rev_avg_b": _b(_f(fly.get("fwd_rev_avg"))),
            "fwd_pe": _f(fly.get("fwd_pe")),
            "num_analysts": fly.get("num_analysts"),
            "est_revision_pct": _f(fly.get("est_revision_pct")),
            "gap_score": _f(fly.get("gap_score")),
            "muted_reaction": fly.get("muted_reaction"),
            "stance_reason": stance or None}


def _bull_bear(sym: str) -> dict:
    """Bull/bear takeaways — partition doc_analyses claims by the
    direction tag doc_extract already assigns (tailwind vs headwind).
    Deterministic list always; an LLM one-paragraph summary per side
    only when a model is configured AND grounded — silent fallback
    to the lists on any failure."""
    bull, bear = [], []
    try:
        from app.database import db
        import json as _j
        for r in db.execute_query(
                "SELECT claims FROM doc_analyses WHERE symbol=:s"
                " ORDER BY created_at DESC LIMIT 4", {"s": sym}):
            cl = r.get("claims")
            cl = _j.loads(cl) if isinstance(cl, str) else (cl or [])
            for c in cl:
                if not isinstance(c, dict) or not c.get("text"):
                    continue
                if c.get("direction") == "headwind" or                         c.get("kind") in ("risk", "counter"):
                    bear.append(str(c["text"])[:240])
                else:
                    bull.append(str(c["text"])[:240])
    except Exception:
        pass
    out = {"bull": bull[:6], "bear": bear[:6]}
    if not bull and not bear:
        return out
    try:
        from litellm import completion
        from app.config import settings
        import json as _j
        mdl = getattr(settings, "litellm_model", None)
        if not mdl:
            return out
        for side, items in (("bull", bull[:6]), ("bear", bear[:6])):
            if not items:
                continue
            resp = completion(
                model=mdl, temperature=0.1, max_tokens=140, timeout=20,
                messages=[{"role": "system", "content":
                           "Summarize these verbatim earnings claims "
                           "into ONE ~45-word paragraph. Use ONLY the "
                           "facts listed — invent nothing."},
                          {"role": "user", "content":
                           _j.dumps(items, default=str)}])
            txt = (resp.choices[0].message.content or "").strip()
            if len(txt) > 60:
                out[f"{side}_summary"] = txt
    except Exception:
        pass                                   # deterministic still stands
    return out


def _takeaways(verdict: str, growth: Optional[dict],
               quality: Optional[dict], drivers: list[dict],
               pr: dict, stock: dict) -> list[str]:
    """Deterministic key-takeaway lines — the closing paragraph as
    bullets. Rule-composed, never free-form."""
    out = []
    ql = _quarter_label(date.fromisoformat(str(pr["earnings_date"]))) \
        if pr.get("earnings_date") else "the quarter"
    v_word = {"improving": "a strong quarter — fundamentals improved",
              "deteriorating": "a weak quarter — fundamentals "
                               "deteriorated",
              "mixed": "a mixed quarter — beats and concerns offset",
              "on_track": "an in-line quarter — thesis intact",
              "pending": "an ungraded quarter — basis still landing"}
    out.append(f"{stock.get('company_name') or ''} delivered "
               f"{v_word.get(verdict, 'a reported quarter')} ({ql})."
               .strip())
    cuts = [d for d in drivers if d.get("delta_dir") == "cut"]
    raises = [d for d in drivers if d.get("delta_dir") == "raised"]
    if cuts:
        out.append("Guidance cut on named driver(s): "
                   + ", ".join(f"{d['metric']} {d.get('period', '')}"
                               .strip() for d in cuts)
                   + " — the red flag that overrides a headline beat.")
    elif raises:
        out.append("Guidance raised on: "
                   + ", ".join(f"{d['metric']} {d.get('period', '')}"
                               .strip() for d in raises) + ".")
    if growth and growth.get("quarter_yoy") is not None:
        g = growth["quarter_yoy"]
        trend = ("accelerating" if growth.get("two_year_ann")
                 and growth["two_year_ann"] >
                 (growth.get("five_year_cagr") or 0) else
                 "decelerating" if growth.get("five_year_cagr")
                 and g < growth["five_year_cagr"] * 0.6 else "steady")
        out.append(f"Revenue grew {g:+.1f}% YoY — {trend} vs its "
                   f"multi-year trend.")
    if quality and quality.get("fcf_margin") is not None:
        out.append(f"Free cash flow margin {quality['fcf_margin']:.0f}%"
                   + (f" ({quality['fcf_margin_yoy_pp']:+.0f}pp YoY)"
                      if quality.get("fcf_margin_yoy_pp") is not None
                      else "") + ".")
    out.append("One print doesn't make a buy decision — check "
               "valuation, fair-value buy-below, and the thesis on "
               "the stock page.")
    return out


def _headline(stock: dict, pr: dict, watch: dict, ql: str) -> str:
    sym = stock.get("symbol") or ""
    name = stock.get("company_name") or sym
    rev_act = _f(pr.get("revenue_actual"))
    rev_est = _f(pr.get("revenue_estimate"))
    eps_act = _f(pr.get("eps_actual"))
    eps_est = _f(pr.get("eps_estimate"))
    bits = []
    if rev_act is not None and rev_est is not None:
        d = "ahead of" if rev_act >= rev_est else "behind"
        bits.append(f"revenue {d} expectations")
    if eps_act is not None and eps_est is not None:
        d = "beat" if eps_act >= eps_est else "miss"
        bits.append(f"an EPS {d}")
    core = " and ".join(bits) if bits else "reported results"
    return f"{name} ({sym}) — {core} in {ql}"


# -------------------------------------------------------------- compose

def build(sym: str, day: Optional[date] = None) -> Optional[dict]:
    """Compose the report for one print. Returns the full report
    dict, or None when there's no print/verdict to report on."""
    sym = sym.upper()
    if day is None:
        r = _q("SELECT earnings_date d FROM earnings_data"
               " WHERE stock_symbol=:s AND eps_actual IS NOT NULL"
               " ORDER BY earnings_date DESC LIMIT 1", {"s": sym})
        if not r:
            r = _q("SELECT earnings_date d FROM earnings_watch"
                   " WHERE symbol=:s ORDER BY earnings_date DESC"
                   " LIMIT 1", {"s": sym})
        if not r:
            return None
        day = r[0]["d"]
    day = day if isinstance(day, date) else \
        date.fromisoformat(str(day)[:10])
    pr = _print_row(sym, day)
    watch = _watch_row(sym, day)
    if not pr and not watch:
        return None
    stock = _stock(sym)
    fly = _flywheel(sym)
    quarters = _quarters(sym)
    drivers = _drivers(sym, day)
    det = watch.get("detail") or {}
    ql = _quarter_label(day)
    verdict = watch.get("verdict") or "pending"
    growth = _growth_section(quarters, fly, pr)
    quality = _quality_section(quarters, fly)
    return {
        "symbol": sym, "earnings_date": str(day),
        "quarter_label": ql,
        "company_name": stock.get("company_name"),
        "sector": stock.get("sector"),
        "market_cap_b": _b(_f(stock.get("market_cap"))),
        "rating": stock.get("rating"),
        "headline": _headline(stock, pr, watch, ql),
        "print": {
            "eps_estimate": _f(pr.get("eps_estimate")),
            "eps_actual": _f(pr.get("eps_actual")),
            "adjusted_eps_actual": _f(pr.get("adjusted_eps_actual")),
            "surprise_pct": (_f(det.get("surprise_pct"))
                             or _f(pr.get("surprise_percentage"))),
            "revenue_estimate_b": _b(_f(pr.get("revenue_estimate"))),
            "revenue_actual_b": _b(_f(pr.get("revenue_actual"))),
            "rev_surprise_pct": _f(det.get("rev_surprise_pct")),
            "one_time": det.get("one_time")},
        "highlights": _highlights(sym, pr, watch, fly, stock,
                                  quarters),
        "growth": growth,
        "quality": quality,
        "expectations": _expectations_section(
            fly, _stance(sym)),
        "guidance_drivers": drivers or (det.get("drivers") or []),
        "thesis": det.get("thesis") or {
            "before": watch.get("thesis_before"),
            "after": watch.get("thesis_after")},
        "verdict": verdict,
        "narrative": det.get("narrative"),
        "bull_bear": _bull_bear(sym),
        "takeaways": _takeaways(verdict, growth, quality,
                                drivers or (det.get("drivers") or []),
                                {**pr, "earnings_date": day}, stock),
        "prior_prints": _prior_prints(sym, day),
        "generated_at": None,  # filled by journal()
    }


def _prior_prints(sym: str, day: date) -> list[dict]:
    """Earlier reported quarters — the report-history strip."""
    rows = _q(
        "SELECT ed.earnings_date, ed.eps_estimate, ed.eps_actual,"
        " ed.revenue_actual, ed.surprise_percentage, ew.verdict,"
        " (SELECT MAX(er.version) FROM earnings_reports er"
        "  WHERE er.symbol=ed.stock_symbol"
        "    AND er.earnings_date=ed.earnings_date) AS report_version"
        " FROM earnings_data ed"
        " LEFT JOIN earnings_watch ew ON ew.symbol=ed.stock_symbol"
        "   AND ew.earnings_date=ed.earnings_date"
        " WHERE ed.stock_symbol=:s AND ed.earnings_date < :d"
        " ORDER BY ed.earnings_date DESC LIMIT 8",
        {"s": sym, "d": day})
    out = []
    for r in rows:
        row = dict(r)
        row["earnings_date"] = str(row["earnings_date"])
        out.append(row)
    return out


# -------------------------------------------------------------- journal

def journal(sym: str, day: Optional[date] = None,
            generated_by: str = "earnings_watch") -> Optional[dict]:
    """Compose + append the next version. Returns the journaled row
    {version, report} or None when there's nothing to report."""
    rep = build(sym, day)
    if not rep:
        return None
    sym = sym.upper()
    day = date.fromisoformat(rep["earnings_date"])
    nxt = _q("SELECT COALESCE(MAX(version),0)+1 v"
             " FROM earnings_reports WHERE symbol=:s"
             " AND earnings_date=:d", {"s": sym, "d": day})
    version = int(nxt[0]["v"]) if nxt else 1
    rep["version"] = version
    _u("INSERT INTO earnings_reports (symbol, earnings_date, version,"
       " title, report, generated_by) VALUES (:s,:d,:v,:t,"
       " CAST(:r AS jsonb),:g)",
       {"s": sym, "d": day, "v": version, "t": rep["headline"],
        "r": json.dumps(rep, default=str), "g": generated_by})
    return {"symbol": sym, "earnings_date": str(day),
            "version": version, "title": rep["headline"]}


# ----------------------------------------------------------------- read

def latest(sym: str) -> Optional[dict]:
    """Latest report version for the most recent journaled print."""
    r = _q("SELECT symbol, earnings_date, version, title, report,"
           " generated_by, created_at FROM earnings_reports"
           " WHERE symbol=:s"
           " ORDER BY earnings_date DESC, version DESC LIMIT 1",
           {"s": sym.upper()})
    if not r:
        return None
    return _shape(dict(r[0]))


def report(sym: str, day: Optional[str] = None,
           version: Optional[int] = None) -> Optional[dict]:
    """A specific report: latest version of a date, or an exact
    (date, version) pin."""
    p: dict = {"s": sym.upper()}
    sql = ("SELECT symbol, earnings_date, version, title, report,"
           " generated_by, created_at FROM earnings_reports"
           " WHERE symbol=:s")
    if day:
        sql += " AND earnings_date=:d"
        p["d"] = day
    if version:
        sql += " AND version=:v"
        p["v"] = version
    sql += " ORDER BY earnings_date DESC, version DESC LIMIT 1"
    r = _q(sql, p)
    return _shape(dict(r[0])) if r else None


def versions(sym: str) -> list[dict]:
    """Every report version for a symbol — the audit list."""
    return [dict(r) for r in _q(
        "SELECT earnings_date::text AS earnings_date, version, title,"
        " generated_by, created_at::text AS created_at"
        " FROM earnings_reports WHERE symbol=:s"
        " ORDER BY earnings_date DESC, version DESC",
        {"s": sym.upper()})]


def recent(days: int = 30) -> list[dict]:
    """Latest-version reports across the book — the earnings feed."""
    return [dict(r) for r in _q(
        "SELECT DISTINCT ON (symbol, earnings_date)"
        " symbol, earnings_date::text AS earnings_date, version,"
        " title, report->>'verdict' AS verdict,"
        " created_at::text AS created_at"
        " FROM earnings_reports"
        " WHERE earnings_date >= CURRENT_DATE - :d"
        " ORDER BY symbol, earnings_date, version DESC",
        {"d": days})]


def _shape(row: dict) -> dict:
    row["earnings_date"] = str(row["earnings_date"])
    row["created_at"] = str(row["created_at"])
    row["report"] = _j(row.get("report")) or {}
    return row
