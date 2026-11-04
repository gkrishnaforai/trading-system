"""Universe snapshot fill — rollup of journaled tables into one
per-symbol base row. Chunked: each run refreshes the N stalest rows
(and rows never filled), so the 3k universe spreads across weekend
runs and a timeout resumes, not restarts."""

from __future__ import annotations

from typing import Any, Dict

from app.database import db

_CHUNK = 300


def fill(chunk: int = _CHUNK) -> Dict[str, Any]:
    syms = [r["symbol"] for r in db.execute_query(
        "SELECT s.symbol FROM stocks s"
        " LEFT JOIN universe_snapshot u ON u.symbol = s.symbol"
        " ORDER BY COALESCE(u.snapshot_as_of, '1970-01-01') ASC"
        " LIMIT :n", {"n": chunk})]
    if not syms:
        return {"refreshed": 0, "note": "universe fresh"}

    upsert = """
    INSERT INTO universe_snapshot
      (symbol, spot, spot_date, eps_ttm, fwd_eps, fy0_eps, fy2_eps,
       est_revision_pct, num_analysts, rev_growth, fcf_ttm, market_cap,
       momentum_state, fv_expected, fv_upside_pct, lifecycle_stage,
       category, backlog_yoy, book_to_bill, snapshot_as_of)
    SELECT s.symbol,
        b.close, b.bdate,
        f.eps_ttm, f.fwd_eps_avg,
        (SELECT DISTINCT ON (period_end) eps_avg
           FROM symbol_estimate_snapshots e
           WHERE e.symbol = s.symbol
             AND period_end > CURRENT_DATE + INTERVAL '30 days'
             AND eps_avg IS NOT NULL
           ORDER BY period_end, as_of DESC LIMIT 1),
        (SELECT DISTINCT ON (period_end) eps_avg
           FROM symbol_estimate_snapshots e
           WHERE e.symbol = s.symbol
             AND period_end > CURRENT_DATE + INTERVAL '18 months'
             AND eps_avg IS NOT NULL
           ORDER BY period_end, as_of DESC LIMIT 1),
        f.est_revision_pct, f.num_analysts, f.rev_growth,
        fin.free_cash_flow_ttm, fin.market_cap,
        s.momentum_state,
        fv.expected_fair_value,
        CASE WHEN fv.expected_fair_value IS NOT NULL AND b.close > 0
             THEN (fv.expected_fair_value / b.close - 1) * 100 END,
        (fv.decision->'lifecycle'->>'stage')::int,
        (fv.classification->>'primary'),
        bk.backlog_yoy, bk.book_to_bill,
        now()
    FROM stocks s
    LEFT JOIN LATERAL (
        SELECT close, date AS bdate FROM daily_bars d
        WHERE d.symbol = s.symbol ORDER BY date DESC LIMIT 1
    ) b ON true
    LEFT JOIN symbol_flywheel f ON f.symbol = s.symbol
    LEFT JOIN LATERAL (
        SELECT free_cash_flow_ttm, market_cap FROM stock_financials sf
        WHERE sf.stock_symbol = s.symbol ORDER BY as_of_date DESC LIMIT 1
    ) fin ON true
    LEFT JOIN LATERAL (
        SELECT expected_fair_value, decision, classification
        FROM fair_value_v2_runs r
        WHERE r.symbol = s.symbol ORDER BY run_ts DESC LIMIT 1
    ) fv ON true
    LEFT JOIN LATERAL (
        SELECT backlog_yoy, book_to_bill FROM backlog_conversion bc
        WHERE bc.symbol = s.symbol ORDER BY as_of DESC LIMIT 1
    ) bk ON true
    WHERE s.symbol = ANY(:syms)
    ON CONFLICT (symbol) DO UPDATE SET
      spot=EXCLUDED.spot, spot_date=EXCLUDED.spot_date,
      eps_ttm=EXCLUDED.eps_ttm, fwd_eps=EXCLUDED.fwd_eps,
      fy0_eps=EXCLUDED.fy0_eps, fy2_eps=EXCLUDED.fy2_eps,
      est_revision_pct=EXCLUDED.est_revision_pct,
      num_analysts=EXCLUDED.num_analysts,
      rev_growth=EXCLUDED.rev_growth, fcf_ttm=EXCLUDED.fcf_ttm,
      market_cap=EXCLUDED.market_cap,
      momentum_state=EXCLUDED.momentum_state,
      fv_expected=EXCLUDED.fv_expected,
      fv_upside_pct=EXCLUDED.fv_upside_pct,
      lifecycle_stage=EXCLUDED.lifecycle_stage,
      category=EXCLUDED.category,
      backlog_yoy=EXCLUDED.backlog_yoy,
      book_to_bill=EXCLUDED.book_to_bill,
      snapshot_as_of=EXCLUDED.snapshot_as_of"""
    db.execute_update(upsert, {"syms": syms})
    remaining = (db.execute_query(
        "SELECT count(*) AS n FROM stocks s"
        " LEFT JOIN universe_snapshot u ON u.symbol = s.symbol"
        " WHERE u.snapshot_as_of IS NULL"
        " OR u.snapshot_as_of < now() - interval '3 days'") or [{}])[0] \
        .get("n")
    return {"refreshed": len(syms), "stale_remaining": remaining}
