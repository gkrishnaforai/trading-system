"""Daily Action Board endpoints — the board itself + refresh dispatcher.

Every data layer the board reads gets a named refresh job so the UI can
offer one button per layer (plus 'all'). Jobs run in the background;
GET /board/refresh/status reports last-run state for the poll banner.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Callable

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)
router = APIRouter()


def _js(v):
    """jsonb param — serialize with non-JSON types as str."""
    import json
    if v is None:
        return None
    return json.dumps(v, default=str)

# job name → state — in-memory is fine; refreshes are idempotent anyway
_jobs: dict[str, dict[str, Any]] = {}


def _mark(job: str, **kw):
    at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if kw.get("running"):
        _jobs[job] = {"at": at, "started_at": at, **kw}
        return
    started = (_jobs.get(job) or {}).get("started_at")
    dur = None
    if started:
        try:
            dur = round((datetime.now(timezone.utc)
                         - datetime.fromisoformat(started))
                        .total_seconds(), 1)
        except Exception:
            pass
    _jobs[job] = {"at": at, **kw}
    # durable ledger — last-run staleness must survive worker restarts
    try:
        from app.database import db
        import json, math

        def _jsonable(o):
            # NaN/Infinity serialize as bare literals — invalid jsonb
            if isinstance(o, float):
                return o if math.isfinite(o) else None
            if isinstance(o, dict):
                return {k: _jsonable(v) for k, v in o.items()}
            if isinstance(o, (list, tuple)):
                return [_jsonable(v) for v in o]
            return o

        res = kw.get("result") or ({"finished": True}
                                   if kw.get("finished") else {})
        try:
            payload = json.dumps(_jsonable(res), default=str)
            if len(payload) > 4000:
                # never store a sliced JSON string — invalid jsonb
                payload = json.dumps(
                    {"_truncated": True, "preview": payload[:3500]})
        except Exception:
            payload = json.dumps({"_raw": str(res)[:1500]})
        db.execute_update(
            "INSERT INTO job_runs (name, ran_at, duration_s, error,"
            " result) VALUES (:n, now(), :d, :e, CAST(:r AS jsonb))",
            {"n": job, "d": dur, "e": (kw.get("error") or "")[:500]
             or None,
             "r": payload})
    except Exception:
        pass


async def _tracked_symbols() -> list[str]:
    from app.database import db
    rows = await asyncio.to_thread(db.execute_query,
        "SELECT symbol FROM stocks WHERE momentum_state IS NOT NULL")
    return [r["symbol"] for r in rows]


# --- job implementations (each returns a result dict) ------------------------

async def _j_momentum():
    """Canonical momentum flags for every tracked symbol (~90s)."""
    from app.signals.momentum_regime import refresh_momentum_all
    return await asyncio.to_thread(refresh_momentum_all)


async def _j_swing_scan():
    """Swing screener run — regime buckets + persisted results."""
    from app.screener import service
    if service.screener_status()["running"]:
        return {"skipped": "already_running"}
    return await service.run_screener_job()


async def _j_alerts():
    """Catalyst alert scan over portfolio ∪ watchlist w/ auto-review."""
    from app.alerts import service
    if service.scan_status()["running"]:
        return {"skipped": "already_running"}
    return await service.run_scan_job(lookback_days=1.0,
                                      auto_review_enabled=True)


async def _j_outcomes():
    """Evaluate pending alert + pattern + BOARD outcomes (forward
    returns — the accountability loop for every layer that publishes
    picks)."""
    from app.alerts import service
    out = await service.evaluate_alert_outcomes()
    try:
        from app.pattern_learning import evaluate_outcomes
        pat = await evaluate_outcomes()
    except Exception:
        pat = None
    try:
        from app.signals.board_tracking import evaluate_pending
        bd = await asyncio.to_thread(evaluate_pending)
    except Exception:
        bd = None
    try:                                    # top-3 calls: EOD close +
        from app.signals.daily_calls import evaluate_calls
        calls = await asyncio.to_thread(evaluate_calls)
    except Exception:                       # stop/target resolution
        calls = None
    try:                                    # put calls graded the
        from app.signals.daily_puts import evaluate_puts
        puts = await asyncio.to_thread(evaluate_puts)
    except Exception:                       # same mirrored way
        puts = None
    try:                                    # regime reads → realized
        from app.signals.board_tracking import evaluate_regime
        reg = await asyncio.to_thread(evaluate_regime)
    except Exception:                       # SPY outcomes vs lead call
        reg = None
    try:                                    # crash alpha → cap-bounce +
        from app.options.crash_alpha import evaluate as _ca_eval
        alpha = await asyncio.to_thread(_ca_eval)
    except Exception:                       # put-candidate hit rates
        alpha = None
    try:                                    # rotation events → did the
        from app.market_regime.rotation_backtest import evaluate \
            as _rot_eval
        rot = await asyncio.to_thread(_rot_eval)
    except Exception:                       # theme flip outperform?
        rot = None
    try:                                    # event-day calls → did
        from app.signals.event_day import evaluate as _ev_eval
        ev = await asyncio.to_thread(_ev_eval)
    except Exception:                       # the judge read the tape?
        ev = None
    try:                                    # morning regime → did the
        from app.market_regime.morning import evaluate as _mr_eval
        mr = await asyncio.to_thread(_mr_eval)
    except Exception:                       # regime call match tape?
        mr = None
    return {"alerts": out, "patterns": pat, "board": bd, "puts": puts,
            "calls": calls, "regime": reg, "crash_alpha": alpha,
            "rotation": rot, "event_day": ev, "morning": mr}


async def _j_rule_breakers():
    """RB eval — gates, tier transitions, discovery, then flywheel +
    momentum refresh at the tail (already wired)."""
    from app.screener.rule_breakers import run_rule_breakers, rb_status, \
        discovery_due
    if rb_status()["running"]:
        return {"skipped": "already_running"}
    return await run_rule_breakers(discover=discovery_due())


async def _j_smallcap():
    """5x Scout eval — gates, tiers, discovery (tails refresh too)."""
    from app.screener.smallcap import run_smallcap, sc_status
    if sc_status()["running"]:
        return {"skipped": "already_running"}
    return await run_smallcap(discover=True)


async def _j_leaps_mark():
    """Mark open LEAPS + hedge positions — reprices, exit alerts,
    and the monetization ladder on the hedge book."""
    from app.options.leaps_book import mark_book
    out = await asyncio.to_thread(mark_book)
    try:
        from app.options.hedge_book import mark_hedges
        hedges = await asyncio.to_thread(mark_hedges)
    except Exception:
        hedges = None
    return {**out, "hedges": hedges}


async def _j_focus():
    """Focus book scan — company developments for conviction names
    (press/news, grades, PT moves, SEC filings incl. 8-K contracts)."""
    from app.signals.focus_intel import scan_all
    return await asyncio.to_thread(scan_all)


async def _j_priors():
    """Replay the classifier over 15mo of bars per symbol → empirical
    hit-rates per tape pattern + event→outcome attribution (~10min)."""
    from app.signals.pattern_priors import compute_priors
    return await asyncio.to_thread(compute_priors)


async def _j_pilot():
    """Swing pilot — manage paper exits, open today's entries, fold the
    journal back into learned engine weights."""
    from app.signals import swing_pilot
    return await asyncio.to_thread(swing_pilot.run_daily)


async def _j_custodian():
    """Support-agent pass — sense failures/staleness, diagnose, take
    bounded remediation (job re-kicks), escalate what it can't fix."""
    from app.support.custodian import run_pass
    return await run_pass()


async def _j_daily_calls():
    """Top-3 swing calls — distills the scored board into journaled
    picks with entry/stop/target plans (advisory; nothing executes)."""
    from app.signals import daily_calls
    return await asyncio.to_thread(daily_calls.generate)


async def _j_daily_puts():
    """Top-3 put calls — leap_put-ready names distilled into journaled
    plans (stop above / target below). Posture-gated on shorts."""
    from app.signals import daily_puts
    return await asyncio.to_thread(daily_puts.generate)


async def _j_spec_incubator():
    """Spec incubator — persistent quality movers graduate to engine
    watch tiers; fades/breaks expire. The funnel's nightly pass."""
    from app.signals import spec_incubator
    return await asyncio.to_thread(spec_incubator.evaluate)


async def _j_meta():
    """Nightly self-training — signal lift + calibration over real
    outcomes → bounded engine_weights corrections."""
    from app.signals import meta_learn
    return await asyncio.to_thread(meta_learn.run)


async def _j_fund_flags():
    """Fundamental health flags — distills flywheel metrics into the
    canonical status (accelerating/growing/slowing/declining/...) +
    risk level + 'what changed' alert per symbol."""
    from app.signals.fundamental_health import refresh_all
    return await asyncio.to_thread(refresh_all)


async def _j_regime():
    """Market regime card — deterministic snapshot (no LLM). Honors
    force_refresh to bypass the same-day context cache (event days)."""
    from app.market_regime import build_market_regime_graph
    import os
    force = os.getenv("REGIME_FORCE_REFRESH", "0").strip().lower() in {
        "1", "true", "yes", "y", "on"}
    r = await build_market_regime_graph(
        use_llm=False, force_refresh=force).ainvoke({})
    return {"regime": (r or {}).get("regime"), "forced": force}


async def _j_morning_regime():
    """Daily morning regime — 7-bucket deterministic score → 5-regime
    class → LLM explains (evidence-linked). Runs every day; event
    days layer the event judge on top."""
    from app.market_regime.morning import snapshot
    res = await asyncio.to_thread(snapshot)
    return res or {"skipped": "already journaled today"}


async def _j_fred_macro():
    """FRED structural layer — incremental series fetch (growth/labor/
    inflation/rates/credit/liquidity/housing/manufacturing) → module
    scores → macro_snapshots. Fails visibly without FRED_API_KEY."""
    def _run():
        from app.services.macro_engine import MacroOrchestrator
        res = MacroOrchestrator().run_daily()
        return {"updated": res.updated_series,
                "snapshot": res.snapshot_written,
                "message": res.message}
    return await asyncio.to_thread(_run)


async def _j_econ_cal_verify():
    """Macro calendar verification — Finnhub econ calendar reconciled
    against the hardcoded BLS/Fed dates. Catches reschedules (shutdowns,
    bureau moves) so boards show the real date, not the stale one."""
    from app.market_events.verify import verify_and_store
    return await asyncio.to_thread(verify_and_store)


async def _j_econ_cal_poll():
    """Hourly watch on due macro prints — re-queries Finnhub only
    while a scheduled event is past its date but still missing its
    actual (release lagged, bureau rescheduled, provider slow)."""
    from app.market_events.verify import poll_due
    return await asyncio.to_thread(poll_due)


async def _j_etf_flows():
    """Daily AUM snapshot per sector/theme ETF — real fund flows
    accrue as ΔAUM − market-explained drift."""
    from app.portfolio_strategy import flows
    return await asyncio.to_thread(flows.refresh_flows)


async def _j_strategy():
    """Daily portfolio-strategy snapshot — the top-down allocation
    journal (regime → rotation → themes → weights) so tomorrow's
    deltas are computed against a stored yesterday, not guessed."""
    from app.portfolio_strategy import engine as strategy
    return await asyncio.to_thread(strategy.snapshot)


async def _j_hidden_gems():
    """Evening emerging-growth scan — score, journal, diff vs
    yesterday for the NEW/↑/↓/REMOVED change column."""
    from app.signals import hidden_gems, hidden_gems_backtest as bt
    payload = await asyncio.to_thread(hidden_gems.run)
    # grade matured snapshots on every run — the shadow backtest
    # fills forward returns as the journal ages
    await asyncio.to_thread(bt.grade_snapshots)
    return payload


async def _j_fund_journal():
    """Quarterly financials journal — backfills/upserts
    fundamental_quarterly so Hidden Gems + its backtest get real
    ROE/FCF/revenue history with filingDate as the point-in-time key."""
    from app.signals import fundamental_journal
    return await asyncio.to_thread(fundamental_journal.run)


async def _j_theme_review():
    """Future-theme registry — weekly evidence accrual (news keyword
    hits + member fundamentals); the deep pass (restaging + LLM
    discovery + promotion) fires whenever the quarter hasn't been
    reviewed — the quarter-due flag survives missed Sundays."""
    from app.signals import future_themes
    return await asyncio.to_thread(future_themes.review)


async def _j_conviction():
    """Nightly Conviction List — the meta-engine: every engine's
    candidates pooled, scored on adviser criteria (growth, real
    quality, tape, engine consensus, theme money-flow), laned
    deploy-vs-watch, best-2 flagged; Friday + month-end rollups."""
    from app.signals import conviction
    return await asyncio.to_thread(conviction.run)


async def _j_hedge_universe():
    """Nightly hedge-universe journal — four-bucket LEAP-put scan +
    exact-contract ROI scenario frozen per symbol so the watchlist
    accrues and matured snapshots get graded on 'did it pay when the
    target fell'."""
    from app.options import put_universe as pu
    payload = await asyncio.to_thread(pu.journal)
    await asyncio.to_thread(pu.grade_snapshots)
    return payload


async def _j_daily_sheet():
    """Nightly Daily Sheet — conviction names → expression (stock
    zone / call LEAP / put LEAP / put watch) + armed entry zones from
    swing structure + priced contracts, journaled and graded."""
    from app.signals import daily_sheet
    return await daily_sheet.run()


async def _j_event_day():
    """Macro event-day judge — on scheduled days (NFP/CPI/FOMC…)
    gathers the full context bundle and journals a bounded
    green/red/choppy read. No-op on non-event days."""
    from app.signals.event_day import snapshot
    res = await asyncio.to_thread(snapshot)
    return res or {"skipped": "no scheduled macro event today"}


async def _j_flywheel():
    """Expectation-gap / flywheel scores for tracked symbols."""
    from app.signals.expectation_gap import refresh_flywheel
    return await refresh_flywheel(await _tracked_symbols(), concurrency=8)


async def _j_tailwind_review():
    """Weekly LLM attribution over the deterministic tailwind screen —
    what kind of tailwind is repricing each candidate. Journal-only:
    the model classifies, it cannot change flags or scores."""
    from app.signals import tailwind_review
    return await asyncio.to_thread(tailwind_review.run)


async def _j_theme_rotation():
    """Score every active theme on member tape + evidence + fund growth;
    journals the board so rotations surface as week-over-week deltas."""
    from app.signals import theme_rotation
    return await asyncio.to_thread(theme_rotation.run)


async def _j_iv_coverage():
    """Daily ATM-IV + hv20 print per tracked symbol → iv_snapshots, so
    the put-entry premium leg scores on real data universe-wide rather
    than only the ~18 names with incidental LEAPS coverage."""
    from app.options.iv_coverage import refresh_iv_coverage
    return await asyncio.to_thread(refresh_iv_coverage)


async def _j_macro_snapshot():
    """Daily market-wide macro row (VIX/TNX/IRX/Nasdaq trend) →
    macro_market_data — feeds the FV engine's rates features."""
    from app.services.macro_refresh_service import MacroRefreshService
    return await asyncio.to_thread(
        MacroRefreshService().refresh_daily_macro_snapshot)


async def _j_fund_snapshots():
    """Weekly fundamentals bundle → stock_insights_snapshots for every
    tracked symbol: fundamentals, key_metrics_ttm, financial_growth,
    the three statement-growth feeds, ratios, scores — the inputs the
    fair-value engine resolves (replaces the dead Go-side
    weekly_fundamentals schedule whose profile name never resolved)."""
    from app.data_management.refresh_manager import (
        DataRefreshManager, RefreshMode)
    from app.data_management.refresh_strategy import DataType
    mgr = DataRefreshManager()
    dtypes = [DataType.FUNDAMENTALS, DataType.KEY_METRICS_TTM,
              DataType.FINANCIAL_GROWTH, DataType.INCOME_STATEMENT_GROWTH,
              DataType.BALANCE_SHEET_GROWTH, DataType.CASH_FLOW_GROWTH,
              DataType.FINANCIAL_RATIOS, DataType.FINANCIAL_SCORES]
    symbols = await _tracked_symbols()
    ok = failed = 0
    errs = []
    for sym in symbols:
        try:
            res = await asyncio.to_thread(
                mgr.refresh_data, sym, dtypes, RefreshMode.SCHEDULED, False)
            if res.total_successful > 0:
                ok += 1
            else:
                failed += 1
        except Exception as exc:
            failed += 1
            errs.append(f"{sym}: {exc}")
    return {"symbols": len(symbols), "ok": ok, "failed": failed,
            "errors": errs[:10]}


async def _j_tailwinds():
    """Pre-revenue channel extractor — LLM reads alert_items catalysts
    per symbol, deterministic validation journals tail/headwinds with
    corroboration-based tier promotion."""
    from app.signals import tailwinds as tw
    return await asyncio.to_thread(tw.run)


async def _j_growth_quality():
    """Growth-quality composite over the tracked universe — slope,
    earnings quality, revisions, structural proof — percentile-ranked
    and journaled per symbol."""
    from app.signals import growth_quality
    return await asyncio.to_thread(growth_quality.run_universe)


async def _j_tailwind_review():
    """Weekly re-grade — does each journaled channel still plausibly
    move revenue? Stale single-source rumors decay to 'noise'; an LLM
    pass re-verdicts the rest (live|noise|dead), applied
    deterministically."""
    from app.signals import tailwinds as tw
    return await asyncio.to_thread(tw.review)


async def _j_fwd_flags():
    """Forward-growth flags — batch priced_status (LT curve or FV
    fallback), emerging_growth from product-ramp buckets, then the
    daily forecast journal row."""
    from app.signals import lt_power, forward_growth as fg
    priced = await asyncio.to_thread(lt_power.refresh_priced_status)
    emerging = await asyncio.to_thread(fg.refresh_emerging_growth)
    snaps = await asyncio.to_thread(fg.snapshot_forecasts)
    return {"priced": priced, "emerging": emerging, "snaps": snaps}


async def _j_fwd_grade():
    """Calibration — grade aged forecast snapshots against realized
    flywheel metrics at 90d/365d horizons."""
    from app.signals import forward_growth as fg
    return await asyncio.to_thread(fg.grade_forecasts)


async def _j_mover_quality():
    """Post-close quality-mover screen — CANSLIM gate over the day's
    FMP movers → mover_snapshots (accumulation memory), then grade
    matured picks → mover_outcomes/mover_stats. Weekdays only; the
    day's row is the dedupe flag so catch-up can't double-run."""
    from zoneinfo import ZoneInfo
    from app.database import db
    from app.screener import quality as _q
    today = datetime.now(ZoneInfo("America/New_York")).date()
    if datetime.now(ZoneInfo("America/New_York")).weekday() > 4:
        return {"skipped": "weekend"}
    ran = db.execute_query(
        "SELECT max(as_of_date) d FROM mover_snapshots")
    if ran and ran[0]["d"] == today:
        return {"skipped": "already_ran_today"}
    res = await _q.run_quality_job()
    try:
        outc = await _q.evaluate_mover_outcomes()
    except Exception as e:
        outc = {"error": str(e)}
    return {"items": len(res.get("items") or []),
            "quality_count": res.get("quality_count"),
            "outcomes": outc}


async def _j_fv_backtest() -> dict:
    """Refresh fv_backtest_forwards — one windowed pass over
    daily_bars materializing forward closes for every stored FV
    run, so the backtest page reads a small table instead of an
    N+1 query per run/horizon."""
    from app.fair_value_v2.backtest import refresh_forwards
    return await asyncio.to_thread(refresh_forwards)


async def _j_posture_eval() -> dict:
    """Posture eval + outcome grading. Backfills evals over all
    journaled regime snapshots (dedup is first-write-per-day), then
    grades matured evals against forward QQQ returns — the journal
    IS the backtest."""
    from app.signals import posture
    backfilled = posture.backfill()
    graded = posture.grade()
    cur = posture.current()
    return {"evals": backfilled, "graded": graded,
            "today": cur.get("posture"), "rule": cur.get("matched")}


JOBS: dict[str, tuple[str, Callable]] = {
    "momentum":      ("Momentum flags", _j_momentum),
    "swing-scan":    ("Swing screener", _j_swing_scan),
    "alerts":        ("Catalyst alerts", _j_alerts),
    "outcomes":      ("Alert outcomes", _j_outcomes),
    "rule-breakers": ("Rule Breaker eval", _j_rule_breakers),
    "smallcap":      ("5x Scout eval", _j_smallcap),
    "leaps-mark":    ("LEAPS book marks", _j_leaps_mark),
    "regime":        ("Market regime card", _j_regime),
    "flywheel":      ("Expectation gap", _j_flywheel),
    "macro-snapshot": ("Macro market snapshot", _j_macro_snapshot),
    "fund-snapshots": ("Fundamental snapshots", _j_fund_snapshots),
    "focus-scan":    ("Focus book scan", _j_focus),
    "fund-flags":    ("Fundamental flags", _j_fund_flags),
    "priors":        ("Pattern priors", _j_priors),
    "pilot":         ("Swing pilot", _j_pilot),
    "daily-calls":   ("Top-3 swing calls", _j_daily_calls),
    "daily-puts":    ("Top-3 put calls", _j_daily_puts),
    "spec-incubator": ("Spec candidate incubator", _j_spec_incubator),
    "meta":          ("Signal self-training", _j_meta),
    "custodian":     ("Support agent pass", _j_custodian),
    "event-day":     ("Macro event judge", _j_event_day),
    "morning-regime": ("Morning regime engine", _j_morning_regime),
    "fred-macro":   ("FRED structural layer", _j_fred_macro),
    "econ-cal-verify": ("Macro calendar verification",
                        _j_econ_cal_verify),
    "econ-cal-poll":  ("Due-print watcher (hourly)",
                       _j_econ_cal_poll),
    "etf-flows":    ("ETF AUM → fund flows", _j_etf_flows),
    "strategy":     ("Portfolio strategy snapshot", _j_strategy),
    "hidden-gems":  ("Hidden gems scanner", _j_hidden_gems),
    "fund-journal": ("Quarterly fundamentals journal", _j_fund_journal),
    "hedge-universe": ("LEAP-put hedge journal", _j_hedge_universe),
    "conviction":   ("Conviction List", _j_conviction),
    "theme-review": ("Future theme registry", _j_theme_review),
    "theme-rotation": ("Theme rotation board", _j_theme_rotation),
    "iv-coverage":  ("Daily IV snapshots", _j_iv_coverage),
    "tailwind-review": ("Tailwind LLM attribution",
                        _j_tailwind_review),
    "daily-sheet":  ("Daily Sheet — expression picks", _j_daily_sheet),
    "tailwinds":    ("Pre-revenue channel extractor", _j_tailwinds),
    "tailwind-review": ("Channel re-grade pass", _j_tailwind_review),
    "growth-quality": ("Growth-quality composite", _j_growth_quality),
    "fwd-flags":    ("Forward-growth flags + journal", _j_fwd_flags),
    "fwd-grade":    ("Forecast calibration grading", _j_fwd_grade),
    "mover-quality": ("Quality-mover screen + outcomes",
                      _j_mover_quality),
    "posture-eval": ("Posture eval + outcome grading",
                     _j_posture_eval),
    "fv-backtest":  ("FV backtest forward-price refresh",
                     _j_fv_backtest),
}

# order matters for 'all': posture first, then signals, then evals
# (evals already tail-refresh momentum+flywheel — harmless overlap)
_ALL_ORDER = ["regime", "momentum", "morning-regime", "fred-macro",
              "econ-cal-verify",
              "etf-flows",
              "strategy", "event-day",
              "flywheel", "fund-flags", "alerts",
              "fwd-flags",
              "focus-scan",
              "swing-scan", "rule-breakers", "smallcap", "hidden-gems",
              "fund-journal", "hedge-universe", "tailwinds", "conviction",
              "theme-review", "daily-sheet", "outcomes",
              "leaps-mark", "priors", "pilot", "daily-calls",
              "daily-puts", "spec-incubator", "meta",
              "custodian"]


_JOB_TIMEOUT = {
    "priors": 20 * 60, "rule-breakers": 15 * 60, "smallcap": 15 * 60,
    "swing-scan": 15 * 60, "alerts": 15 * 60, "focus-scan": 10 * 60,
    "custodian": 10 * 60, "momentum": 8 * 60, "flywheel": 50 * 60,
    "macro-snapshot": 3 * 60, "fund-snapshots": 90 * 60,
    "fund-flags": 8 * 60, "outcomes": 8 * 60, "leaps-mark": 5 * 60,
    "regime": 5 * 60, "pilot": 8 * 60, "daily-calls": 5 * 60,
    "daily-puts": 5 * 60, "spec-incubator": 3 * 60,
    "meta": 5 * 60, "event-day": 3 * 60, "morning-regime": 4 * 60,
    "etf-flows": 2 * 60, "strategy": 5 * 60, "hidden-gems": 5 * 60,
    "fred-macro": 3 * 60, "econ-cal-verify": 2 * 60,
    "econ-cal-poll": 2 * 60, "fv-backtest": 20 * 60,
    "fund-journal": 60 * 60, "hedge-universe": 15 * 60,
    "conviction": 8 * 60, "theme-review": 10 * 60,
    "tailwinds": 15 * 60, "tailwind-review": 15 * 60,
    "theme-rotation": 5 * 60,
    "daily-sheet": 15 * 60,
    "mover-quality": 10 * 60,
    "posture-eval": 5 * 60,
}


async def _run_job(name: str):
    label, fn = JOBS[name]
    _mark(name, running=True)
    try:
        res = await asyncio.wait_for(
            fn(), timeout=_JOB_TIMEOUT.get(name, 10 * 60))
        _mark(name, running=False, result=res)
    except asyncio.TimeoutError:
        logger.error("board refresh %s timed out", name)
        _mark(name, running=False,
              error=f"timed out after "
                    f"{_JOB_TIMEOUT.get(name, 600) // 60}m")
    except Exception as exc:
        logger.error("board refresh %s failed: %s", name, exc)
        _mark(name, running=False, error=str(exc))


async def _run_all():
    for name in _ALL_ORDER:
        await _run_job(name)
    _mark("all", running=False, finished=True)


# The Daily Sheet's real dependency chain — each job reads the
# persisted output of the one before it (bars → technicals → flywheel
# → channels → hedge journal → conviction → sheet).
_SHEET_DEPS = ["momentum", "flywheel", "tailwinds",
               "hedge-universe", "conviction", "daily-sheet"]


@router.post("/recompute-sheet")
async def recompute_sheet(fresh_minutes: int = 60):
    """Staleness-aware recompute — run the sheet's dependency chain
    in order, SKIPPING any job that already succeeded within
    `fresh_minutes`. The sheet itself always recomputes — that's the
    point of the button."""
    if _jobs.get("recompute-sheet", {}).get("running"):
        return {"status": "already_running"}
    from app.database import db
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(
        minutes=fresh_minutes)
    last = {r["name"]: r["ran_at"] for r in db.execute_query(
        "SELECT name, max(ran_at) ran_at FROM job_runs"
        " WHERE name = ANY(:n) AND error IS NULL GROUP BY name",
        {"n": _SHEET_DEPS})}
    inflight = {j for j in _SHEET_DEPS
                if _jobs.get(j, {}).get("running")}
    ran = [j for j in _SHEET_DEPS
           if j == "daily-sheet" or
           (j not in inflight and
            (not last.get(j) or last[j] < cutoff))]
    skipped = [j for j in _SHEET_DEPS
               if j not in ran and j not in inflight]
    _mark("recompute-sheet", running=True)

    async def _chain():
        failed = []
        try:
            for j in _SHEET_DEPS:
                if j in inflight:
                    # mid-flight dep — await it, don't re-run; the
                    # sheet still composes on its fresh output
                    import time as _t
                    t0 = _t.monotonic()
                    while _jobs.get(j, {}).get("running") and \
                            _t.monotonic() - t0 < \
                            _JOB_TIMEOUT.get(j, 600):
                        await asyncio.sleep(5)
                elif j in ran:
                    await _run_job(j)
                if _jobs.get(j, {}).get("error"):
                    failed.append(j)
        finally:
            _mark("recompute-sheet", running=False, finished=True,
                  result={"ran": ran, "skipped_fresh": skipped,
                          "awaited_inflight": sorted(inflight),
                          "failed": failed})

    asyncio.create_task(_chain())
    return {"status": "started", "running": ran,
            "skipped_fresh": skipped,
            "awaited_inflight": sorted(inflight)}


_DAILY_CACHE: dict = {}
_DAILY_TTL_S = 90


@router.get("/daily")
async def daily_board(max_items: int = 10):
    """Top actions for today — exits first, then deploys.

    Fear/greed posture from VIX + SPY-vs-200dma + the regime card;
    per-symbol actions synthesized from the canonical momentum flag,
    RB/5x membership, flywheel gap score, swing-screen readiness,
    open-trade monitor flags, and the LEAPS book's exit alerts.
    Advisory only — nothing executes.

    90s TTL: the board reads stored flags (hourly jobs) plus one
    yfinance tape pull — a short cache makes page reloads and the
    regime page's second call instant without changing advice.
    """
    import time
    from app.signals import daily_board
    key = max_items
    ent = _DAILY_CACHE.get(key)
    now = time.time()
    if ent and now - ent[0] < _DAILY_TTL_S:
        return ent[1]
    res = await daily_board.build_board(max_items=max_items)
    _DAILY_CACHE[key] = (now, res)
    return res


@router.get("/strategy")
async def portfolio_strategy():
    """Top-down allocation layer: regime → money rotation → events →
    earnings concentration → theme scores → target weights vs book.
    Journaled daily to strategy_snapshots — advisory, never orders."""
    from app.portfolio_strategy import engine as strategy
    return await asyncio.to_thread(strategy.snapshot)


@router.get("/hidden-gems")
async def hidden_gems():
    """Emerging-growth scanner — rules-based 0–125 score across the
    curated universe, with NEW/↑/↓/REMOVED change column vs the last
    journaled run. Advisory only."""
    from app.signals import hidden_gems as hg
    return await asyncio.to_thread(hg.run)


@router.get("/tailwind-candidates")
async def tailwind_candidates():
    """"Early CAT" screen — deterministic flags over journaled data:
    revisions up + revenue accelerating + price hasn't repriced +
    below fair value + not already filed under a theme. Advisory."""
    from app.signals import tailwind_screen
    return await asyncio.to_thread(tailwind_screen.run)


@router.get("/hidden-gems/backtest")
async def hidden_gems_backtest(days: int = 180, step: int = 20):
    """Mode-B partial-factor replay — growth/accel/tape scored as-of
    each historical date, graded by forward excess vs SPY. Estimate-
    revision & quality factors excluded (no point-in-time data)."""
    from app.signals import hidden_gems_backtest as bt
    from datetime import date, timedelta
    end = date.today() - timedelta(days=30)
    start = end - timedelta(days=days)
    return await asyncio.to_thread(bt.run_replay, start, end, step)


@router.get("/put-universe")
async def put_universe(target: str = "CRDO", top: int = 25):
    """LEAP-put hedge universe — four-bucket score: fundamental
    vulnerability, volatility discount (HV/IV), convexity (β×HV/IV),
    hedge correlation to the book's exposure. Each candidate carries
    the actual hedge contract + BS-priced ROI on a −30% move."""
    from app.options import put_universe as pu
    return await asyncio.to_thread(pu.scan, target.upper(), top)


@router.get("/put-universe/roi")
async def put_hedge_roi(symbols: str = "", target: str = "CRDO",
                        drop: float = -0.30):
    """Hedge ROI on exact contracts — $5K of each name's ~25% OTM LEAP
    put, valued after a `drop` move with vol bump + time decay. QQQ
    and the hedge target benchmark the comparison."""
    from app.options import put_universe as pu
    syms = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not syms:
        base = await asyncio.to_thread(pu.scan, target.upper(), 15)
        syms = [r["symbol"] for r in base.get("rows") or []][:8]
    return {"drop": drop, "target": target.upper(),
            "rows": await asyncio.to_thread(
                pu.hedge_roi_table, syms, target.upper(), drop)}


@router.get("/put-universe/journal")
async def put_universe_journal(target: str = "CRDO", days: int = 30):
    """The journaled hedge watchlist — nightly snapshots with the
    four buckets, exact contract, correlated-scenario ROI, and (once
    matured) capture_20d grading: did it fall when the target fell."""
    from app.database import db
    rows = db.execute_query(
        "SELECT snap_date, symbol, tier, score, beta_to_target,"
        " corr_target, convexity, iv_hv, thin_chain, put, hedge_roi,"
        " ret_20d, target_ret_20d, capture_20d"
        " FROM hedge_universe_snapshots WHERE hedge_target=:t"
        " AND snap_date > :cut ORDER BY snap_date DESC, score DESC"
        " NULLS LAST", {"t": target.upper(), "cut": __import__(
            "datetime").date.today() - __import__(
            "datetime").timedelta(days=days)})
    return {"target": target.upper(), "days": days,
            "rows": [dict(r) for r in rows]}


@router.get("/conviction")
async def conviction_today():
    """Today's Conviction List — the meta-engine's top names pooled
    from every engine: gems, swing calls, movers, rule-breakers,
    flywheel, theme money-flow. deploy lane = current investment;
    watch lane = future compounders (expensive or unconfirmed)."""
    from app.signals import conviction
    return await asyncio.to_thread(conviction.run)


@router.get("/conviction/history")
async def conviction_history(days: int = 60):
    """The journaled List — every pick with grading (ret_5d/20d/60d,
    vs_spy_20d), daily/weekly/monthly pick flags."""
    from app.database import db
    import datetime as _dt
    rows = db.execute_query(
        "SELECT snap_date, symbol, rank, score, lane, parts, sources,"
        " theme, fwd_pe, valuation, momentum_state, daily_pick,"
        " weekly_pick, monthly_pick, ret_5d, ret_20d, ret_60d,"
        " vs_spy_20d FROM conviction_snapshots WHERE snap_date > :c"
        " ORDER BY snap_date DESC, rank",
        {"c": _dt.date.today() - _dt.timedelta(days=days)})
    return {"rows": [dict(r) for r in rows]}


@router.get("/daily-sheet")
async def daily_sheet_today():
    """Latest Daily Sheet — conviction/hedge names expressed as
    stock-zone / call-LEAP / put-LEAP / put-watch rows with armed
    entry zones and priced contracts."""
    from app.signals import daily_sheet
    return await asyncio.to_thread(daily_sheet.latest)


@router.get("/daily-sheet/performance")
async def daily_sheet_performance():
    """Is the sheet's expression actually right — hit rate + returns
    per section (stock zone vs call LEAP vs put LEAP), per symbol."""
    from app.signals import daily_sheet
    return await asyncio.to_thread(daily_sheet.performance)


@router.get("/theme-registry")
async def theme_registry():
    """The future-thesis registry — active themes with accrued
    evidence (news hits, member fundamentals), plus the candidate
    queue: LLM-proposed themes awaiting promotion by evidence."""
    from app.signals import future_themes as ft
    from app.database import db
    active = [dict(r) for r in db.execute_query(
        "SELECT theme_key, name, thesis, stage, members, evidence,"
        " source, last_review FROM theme_registry"
        " WHERE status='active' ORDER BY theme_key")]
    return {"active": active, "candidates": ft.candidates()}


@router.post("/theme-registry/review")
async def theme_review_now(quarterly: bool = True):
    """Manual trigger — evidence accrual + (optionally) the quarterly
    deep pass: restaging, LLM discovery, candidate promotion."""
    from app.signals import future_themes
    return await asyncio.to_thread(future_themes.review, quarterly)


@router.get("/themes/rotation")
async def themes_rotation(refresh: bool = False):
    """The ranked 6-month rotation board — which theme money is moving
    into, computed deterministically from member tape + evidence."""
    from app.signals import theme_rotation
    if refresh:
        return await asyncio.to_thread(theme_rotation.run)
    return await asyncio.to_thread(theme_rotation.compute_board)


@router.get("/growth-quality")
async def growth_quality_board(refresh: bool = False):
    """Ranked growth-quality composite — structural growers vs cyclical
    peaks. Latest journaled run per symbol unless refresh=1."""
    from app.signals import growth_quality
    from app.database import db
    if refresh:
        results = await asyncio.to_thread(growth_quality.run_universe)
        return {"symbols": sorted(results,
                key=lambda r: (r.get("percentile") or 0), reverse=True)}
    rows = db.execute_query(
        """SELECT DISTINCT ON (symbol) symbol, as_of, score, percentile,
                  components, detail, flags
           FROM growth_quality_runs ORDER BY symbol, as_of DESC, id DESC""")
    return {"symbols": sorted([dict(r) for r in rows],
            key=lambda r: (r.get("percentile") or 0), reverse=True)}


_STALK_LABELS = {"accumulation", "cycle_turn", "turnaround",
                 "add_blocked", "base_repair"}
_MOM_RANK = {"breakout": 9, "climax": 8, "uptrend": 7, "pullback": 6,
             "recovery": 5, "basing": 4, "rolling_over": 3, "downtrend": 2,
             "capitulation": 2, "breakdown": 1, "knife": 0, "unknown": -1,
             None: -1}
_FUND_BAD = {"deteriorating", "declining", "slowing", "pressured"}
_FUND_GOOD = {"accelerating", "growing", "turnaround"}
_TAPE_BROKEN = {"downtrend", "breakdown", "knife", "capitulation"}
_TAPE_BUILD = {"pullback", "basing", "recovery", "uptrend", "breakout"}


def _pulse_action_eval(row, det) -> dict:
    """Adapter — build the engine's input row from the pulse query row.
    The policy lives in pulse_action_rules.yaml; _pulse_action (kept
    for tests) is now a thin wrapper around pulse_engine.evaluate."""
    from app.signals.pulse_engine import evaluate
    from datetime import date, datetime, timezone
    mom, mom_prev = row.get("mom_state"), row.get("prev_state")
    cur = _MOM_RANK.get(mom, -1)
    prev = _MOM_RANK.get(mom_prev, None)
    tape_dir = ("improving" if prev is not None and cur > prev else
                "degrading" if prev is not None and cur < prev else
                "flat" if prev is not None else None)
    today = date.today()
    ne = row.get("next_earnings_date")
    earn_days = ((ne.date() if hasattr(ne, "date") else ne) - today).days \
        if ne else None

    def _age(ts):
        if ts is None:
            return None
        if hasattr(ts, "date"):
            ts = ts.date() if isinstance(ts, datetime) else ts
        elif hasattr(ts, "toordinal"):
            pass
        else:
            return None
        try:
            return (today - (ts.date() if isinstance(ts, datetime)
                             else ts)).days
        except Exception:
            return None

    return evaluate({
        "mom_state": mom, "tape_dir": tape_dir,
        "fund_state": row.get("fund_state"),
        "revision_grade": row.get("revision_grade"),
        "priced_status": row.get("priced_status"),
        "fv_upside": row.get("fv_upside"),
        "rsi": (row.get("momentum_detail") or {}).get("rsi")
               or det.get("rsi"),
        "vs_sma50": (row.get("momentum_detail") or {}).get("vs_sma50")
                    or det.get("vs_sma50"),
        "momentum_detail": det,
        "earn_days": earn_days,
        "num_analysts": row.get("num_analysts"),
        "flywheel_age_days": _age(row.get("flywheel_at")),
        "momentum_age_days": _age(row.get("momentum_updated_at")),
        "gq_flags": row.get("gq_flags") or [],
        "is_etf": row.get("is_etf"),
        "fwd_pe": row.get("fwd_pe"),
    })


def _pulse_action(mom, mom_prev, fund, fv_up, det, gq_flags,
                  fwd_pe=None):
    """Deterministic action hint — tape × fundamentals × valuation.
    REDUCE only when BOTH legs fail; TRIM on extension; ADD needs
    constructive tape + good fundamentals + upside; else HOLD/WATCH."""
    det = det or {}
    rsi = det.get("rsi")
    vs50 = det.get("vs_sma50")
    extended = (rsi or 0) > 65 or (vs50 or 0) > 0.20
    cur = _MOM_RANK.get(mom, -1)
    prev = _MOM_RANK.get(mom_prev, None)
    degrading = prev is not None and cur < prev
    why = []
    if mom in _TAPE_BROKEN and fund in _FUND_BAD:
        return ("reduce",
                f"tape `{mom}` + fundamentals `{fund}` — both "
                f"legs failing")
    if mom in _TAPE_BROKEN:
        # overvaluation must be meaningful (>-25%) to count — FV runs
        # trailing data and lags accelerating businesses by design, so
        # a small negative gap is noise, not a second failing leg
        if fv_up is not None and fv_up < -25:
            # symmetric to the +200% upside cap — a >75% premium is
            # usually the model blind on distorted inputs (TLN: $82 FV
            # vs $373 spot on acquisition-restructured trailing FCF),
            # not proof of froth. Suspect premium can't be the second
            # failing leg; surface it, don't act on it
            if fv_up < -75:
                why.append(f"tape `{mom}` + trading "
                           f"{abs(fv_up):.0f}% above FV — model output "
                           f"suspect on distorted inputs")
            else:
                reenter = (f"; fundamentals still `{fund}` — re-entry "
                           f"candidate once the tape stabilizes"
                           if fund in _FUND_GOOD else "")
                return ("reduce", f"tape `{mom}` + trading "
                        f"{abs(fv_up):.0f}% above fair value{reenter}")
        if not any(w.startswith("tape `") for w in why):
            why.append(f"tape `{mom}`")
    if fund in _FUND_BAD:
        why.append(f"fundamentals `{fund}`")
    if degrading and mom_prev:
        why.append(f"tape slipped {mom_prev}→{mom}")
    # Trim = harvest extended profits on a CONSTRUCTIVE tape. The
    # classifier already reserves euphoria for `climax` (RSI≥75 /
    # %B>0.95 checked first) — a row labeled `breakout` has passed that
    # screen by construction, so a bare RSI-65 cross on it is ignition,
    # not a sell signal. Three legitimate triggers:
    #   climax_corr    climax label + absolute extension corroborating
    #   roll_corr      rolling_over — extended + the first momentum
    #                  crack is the textbook trim point
    #   extreme_abs    euphoric levels regardless of state label
    #   trend_stretch  uptrend/breakout at BOTH RSI>70 and >15% vs50 —
    #                  one weak leg (RSI 66 / +5%) is not a trim
    # Extension on a NON-constructive state (pullback, capitulation,
    # downtrend…) is a data contradiction — the level signal reads off
    # a collapsed average or stale detail. Note it; don't act on it.
    climax_corr = (mom == "climax" and
                   ((rsi or 0) > 65 or (vs50 or 0) > 0.10))
    roll_corr = (mom == "rolling_over" and
                 ((vs50 or 0) > 0.10 or (rsi or 0) > 62))
    extreme_abs = (rsi or 0) >= 75 or (vs50 or 0) > 0.30
    trend_stretch = (mom in ("uptrend", "breakout")
                     and (rsi or 0) > 70 and (vs50 or 0) > 0.15)
    if climax_corr or roll_corr or extreme_abs or trend_stretch:
        if climax_corr:
            tag = "`climax` + absolute extension"
        elif roll_corr:
            tag = "`rolling_over` — first crack after extension"
        elif extreme_abs:
            tag = f"`{mom}` + euphoric levels"
        else:
            tag = f"`{mom}` stretched on both legs"
        return ("trim", f"extended — {tag}, RSI {rsi:.0f}, "
                f"{vs50:+.0%} vs 50dma" if rsi and vs50 else
                f"extended — {tag}")
    if extended:
        why.append(f"metrics extended (RSI {rsi:.0f}, {vs50:+.0%} vs "
                   f"50dma) but tape `{mom}` is not a trim state — "
                   f"verify inputs" if rsi and vs50 else
                   "extended metrics on a non-trim state")
    if mom == "climax":
        _rs = f"RSI {rsi:.0f}" if rsi is not None else "RSI —"
        _v5 = (f"{vs50:+.0%} vs 50dma" if vs50 is not None
               else "50dma n/a")
        why.append(f"climax on %B only ({_rs}, {_v5}) — band poke "
                   f"mid-recovery, not absolute extension")
    if why:
        # the star quadrant — fundamentals improving while the tape is
        # weak AND the name is still cheap vs fair value. Weak tape
        # alone is a warning; weak tape + improving fundamentals +
        # discount is the accumulation profile, so name it
        if (fund in _FUND_GOOD and fv_up is not None and fv_up > 0
                and mom in (_TAPE_BROKEN | {"rolling_over"})):
            return ("watch", f"accumulation setup — fundamentals "
                    f"`{fund}` while tape `{mom}`; {fv_up:+.0f}% vs "
                    f"fair value — stalk the base, don't chase")
        return ("watch", " · ".join(why))
    if (mom in _TAPE_BUILD and fund in _FUND_GOOD
            and fv_up is not None and fv_up > 5
            and "fcf_negative" not in (gq_flags or [])):
        # the readiness screen's own no-chase rule — %B<0.7, RSI<65,
        # <15% over the 50dma. 'Add' at a stretched print contradicts
        # the entry checklist; extended = wait for the pullback
        pb = det.get("pct_b")
        if (rsi or 0) > 60 or (pb or 0) > 0.7 or (vs50 or 0) > 0.15:
            return ("watch", f"tape `{mom}` + fundamentals `{fund}` + "
                    f"{fv_up:+.0f}% vs FV — but stretched "
                    f"(RSI {round(rsi) if rsi is not None else '—'}, %B "
                    f"{round(pb, 2) if pb is not None else '—'}, "
                    f"{(vs50 or 0)*100:+.0f}% vs 50dma): add on the "
                    f"pullback")
        rich = (f" · ⚠ fwd PE {fwd_pe:.0f} — multiple-rich even "
                f"though FV says cheap" if (fwd_pe or 0) > 60 else "")
        return ("add", f"tape `{mom}` + fundamentals `{fund}` + "
                f"{fv_up:+.0f}% vs fair value{rich}")
    return ("hold", "no leg failing, no setup triggering")


_flow_map_cache: tuple = (0.0, {})


def _sector_flow_map() -> dict:
    """ETF → {flow, score} — the sector-rotation board's math run on
    cached daily_bars (no provider fetch), so Pulse / Stock Health can
    tag each row with its sector's capital-flow state. Memoized 300s —
    bars refresh daily; repeated per-symbol lookups are near-free."""
    import time
    global _flow_map_cache
    ts, cached = _flow_map_cache
    if cached and time.time() - ts < 300:
        return cached
    from app.database import db
    from app.market_regime.rotation import (
        SECTOR_NAMES, _flow_tag, _momentum_score)
    etfs = list(SECTOR_NAMES) + ["SPY"]
    rows = db.execute_query(
        "SELECT symbol, date, close, volume FROM daily_bars "
        "WHERE symbol = ANY(%s) ORDER BY symbol, date", (etfs,))
    by: dict[str, list] = {}
    for r in rows:
        by.setdefault(r["symbol"], []).append(r)
    spy = by.get("SPY") or []
    spy20 = (spy[-1]["close"] / spy[-21]["close"] - 1) \
        if len(spy) >= 21 else None
    out = {}
    for sym, bars in by.items():
        if sym == "SPY" or len(bars) < 60:
            continue
        cl = [b["close"] for b in bars]
        vol = [b["volume"] or 0 for b in bars]
        r1 = cl[-1] / cl[-2] - 1
        r5 = cl[-1] / cl[-6] - 1
        r20 = cl[-1] / cl[-21] - 1
        r60 = cl[-1] / cl[-61] - 1 if len(cl) >= 61 else None
        base = vol[-21:-1]
        vr = vol[-1] / (sum(base) / len(base)) \
            if base and sum(base) else None
        s50 = sum(cl[-50:]) / 50
        s200 = sum(cl[-200:]) / 200 if len(cl) >= 200 else None
        above50 = cl[-1] > s50
        above200 = cl[-1] > s200 if s200 else None
        vs_spy20 = (r20 - spy20) if spy20 is not None else None
        out[sym] = {
            "flow": _flow_tag(r1, r5, r20, vr, above50),
            "score": round(_momentum_score(
                r5, r20, r60, vs_spy20, above50,
                bool(above200) if above200 is not None else False,
                vr, r1), 1)}
    _flow_map_cache = (time.time(), out)
    return out


@router.get("/portfolio-pulse")
async def portfolio_pulse():
    """One-row-per-holding board: tape state + transition, fundamental
    state, FV gap, GQ percentile, and a deterministic action hint.
    This is the 'what needs attention today' surface."""
    from app.database import db
    rows = db.execute_query("""
        WITH uni AS (
            SELECT s.symbol, SUM(pp.quantity) AS qty,
                   SUM(pp.quantity * pp.avg_price)
                       / NULLIF(SUM(pp.quantity), 0) AS cost,
                   string_agg(DISTINCT p.name, ', ') AS portfolio,
                   'active' AS status
            FROM portfolio_positions pp
            JOIN stocks s ON s.id = pp.stock_id
            JOIN portfolios p ON p.id = pp.portfolio_id
            WHERE pp.quantity > 0 AND length(s.symbol) > 1
            GROUP BY s.symbol
            UNION ALL
            SELECT h.symbol, h.shares_held, h.average_cost,
                   p.name, h.status
            FROM portfolio_holdings h
            JOIN portfolios p ON p.id = h.portfolio_id
            WHERE h.status IN ('active','inactive')
              AND NOT EXISTS (
                  SELECT 1 FROM portfolio_positions pp
                  JOIN stocks s2 ON s2.id = pp.stock_id
                  WHERE s2.symbol = h.symbol AND pp.quantity > 0)
        )
        SELECT u.symbol, u.qty, u.cost, u.status, u.portfolio,
               px.close,
               s.momentum_state,
               s.momentum_detail, s.fundamental_state,
               s.revision_grade, s.priced_status, s.emerging_growth,
               s.next_earnings_date,
               s.momentum_updated_at, s.fundamental_updated_at,
               CASE
                 WHEN fp.is_etf IS NOT NULL THEN fp.is_etf
                 WHEN s.industry ILIKE 'Asset Management%'
                      OR s.company_name ~* '\m(ETF|Fund|Trust)\M'
                   THEN true
                 WHEN s.company_name IS NOT NULL
                      OR s.industry IS NOT NULL
                   THEN false
                 ELSE NULL          -- unresolved → unknown_policy
               END AS is_etf,
               COALESCE(s.sector, fp.sector) AS sector,
               fv.expected_fair_value,
               gq.score AS gq_score, gq.percentile AS gq_pct,
               gq.flags AS gq_flags,
               fw.fwd_pe, fw.num_analysts, fw.updated_at AS flywheel_at,
               prev.state AS prev_state
        FROM uni u
        LEFT JOIN stocks s ON s.symbol = u.symbol
        LEFT JOIN fmp_company_profiles fp ON fp.symbol = u.symbol
        LEFT JOIN LATERAL (
            SELECT close FROM daily_bars b
            WHERE b.symbol = u.symbol
            ORDER BY b.date DESC LIMIT 1) px ON true
        LEFT JOIN LATERAL (
            SELECT expected_fair_value FROM fair_value_v2_runs f
            WHERE f.symbol = u.symbol
            ORDER BY f.as_of DESC, f.run_id DESC LIMIT 1) fv ON true
        LEFT JOIN LATERAL (
            SELECT score, percentile, flags FROM growth_quality_runs g
            WHERE g.symbol = u.symbol
            ORDER BY g.as_of DESC, g.id DESC LIMIT 1) gq ON true
        LEFT JOIN LATERAL (
            SELECT state FROM momentum_state_log l
            WHERE l.symbol = u.symbol AND l.as_of < CURRENT_DATE
            ORDER BY l.as_of DESC LIMIT 1) prev ON true
        LEFT JOIN symbol_flywheel fw ON fw.symbol = u.symbol
        ORDER BY u.status, u.symbol""")
    from app.market_regime.rotation import _SECTOR_TO_ETF
    etf_ctx = _sector_flow_map()
    from app.signals.spec_pulse import spec_symbols
    spec_set = spec_symbols()
    out = []
    for r in rows:
        sym = r["symbol"]
        sec = r.get("sector")
        sec_etf = (_SECTOR_TO_ETF.get(str(sec).lower())
                   if sec else None)
        sec_ctx = etf_ctx.get(sec_etf) if sec_etf else None
        px = r.get("close")
        cost = float(r["cost"] or 0)
        shares = float(r["qty"] or 0)
        pnl = (float(px) / cost - 1) * 100 if px and cost > 0 else None
        fv_ev = r.get("expected_fair_value")
        fv_up = (float(fv_ev) / float(px) - 1) * 100 \
            if fv_ev and px else None
        det = r.get("momentum_detail") or {}
        if isinstance(det, str):
            import json as _j
            det = _j.loads(det)
        ev = _pulse_action_eval(
            {**r, "mom_state": r.get("momentum_state"),
             "prev_state": r.get("prev_state"),
             "fund_state": r.get("fundamental_state"),
             "fv_upside": fv_up}, det)
        act, why = ev["action"], ev["why"]
        kind = "position" if (r["status"] == "active"
                              and shares > 0) else "watch"
        if kind == "watch" and act in ("reduce", "trim"):
            act, why = "avoid", why  # zero shares — nothing to reduce
        # display bucket — engine action stays canonical; `watch`
        # splits into entry candidates (stalk) vs warnings (attention)
        bucket = (act if act != "watch"
                  else "stalk" if ev.get("label") in _STALK_LABELS
                  else "attention")
        try:  # journal the eval — first write of the day wins
            db.execute_update(
                "INSERT INTO pulse_rule_evals (symbol, as_of, kind,"
                " action, label, matched_rule, confidence, stage0,"
                " annotations, condition_log, gate_results,"
                " input_snapshot, rules_version, engine_version)"
                " VALUES (:s, CURRENT_DATE, :k, :a, :l, :m, :c,"
                " CAST(:s0 AS jsonb), CAST(:an AS jsonb),"
                " CAST(:cl AS jsonb), CAST(:gr AS jsonb),"
                " CAST(:inp AS jsonb), :rv, :ev)"
                " ON CONFLICT (symbol, as_of, rules_version)"
                " DO NOTHING",
                {"s": sym, "k": kind, "a": act, "l": ev.get("label"),
                 "m": ev.get("matched_rule"),
                 "c": ev.get("confidence"),
                 "s0": _js(ev.get("stage0")),
                 "an": _js(ev.get("annotations")),
                 "cl": _js(ev.get("condition_log")),
                 "gr": _js(ev.get("gate_results")),
                 "inp": _js(ev.get("input_snapshot")),
                 "rv": ev.get("rules_version"),
                 "ev": ev.get("engine_version")})
        except Exception:
            pass
        out.append({
            "symbol": sym, "portfolio": r["portfolio"],
            "kind": kind,
            "shares": shares, "avg_cost": cost, "price": px,
            "pnl_pct": round(pnl, 1) if pnl is not None else None,
            "mom_state": r.get("momentum_state"),
            "mom_prev": r.get("prev_state"),
            "rsi": round(det["rsi"], 1) if det.get("rsi") else None,
            "vs_sma50": det.get("vs_sma50"),
            "dd52w": det.get("dd52w"),
            "dip_phase": det.get("dip_phase"),
            "fund_state": r.get("fundamental_state"),
            "revision_grade": r.get("revision_grade"),
            "priced_status": r.get("priced_status"),
            "emerging_growth": r.get("emerging_growth"),
            "fv_upside": round(fv_up, 1) if fv_up is not None else None,
            "gq_pct": r.get("gq_pct"),
            "gq_flags": r.get("gq_flags"),
            "fwd_pe": round(r["fwd_pe"], 1)
                      if r.get("fwd_pe") is not None else None,
            "sector": sec,
            "sector_etf": sec_etf,
            "sector_flow": sec_ctx["flow"] if sec_ctx else None,
            "sector_score": sec_ctx["score"] if sec_ctx else None,
            # spec-board membership — the name lives on exactly one
            # board: engine-promoted members (minus fortresses) or
            # names the valuation engine can't anchor
            "spec": bool(
                sym in spec_set
                or (r.get("is_etf") is not True
                    and r.get("expected_fair_value") is None
                    and (r.get("num_analysts") or 0) <= 3)),
            "action": act, "bucket": bucket, "why": why,
            "action_label": ev.get("label"),
            "action_confidence": ev.get("confidence"),
            "matched_rule": ev.get("matched_rule"),
        })
    order = {"reduce": 0, "trim": 1, "add": 2, "stalk": 3,
             "attention": 4, "hold": 5, "avoid": 6}
    out.sort(key=lambda x: (x["kind"] != "position",
                            order.get(x["bucket"], 9),
                            -(x["pnl_pct"] or 0)))
    # ---- book vs target — the "is this beating the goal" strip.
    # The benchmark isn't SPY: it's PORTFOLIO_TARGET_PCT annualized,
    # and pace is measured on journaled book snapshots.
    import os
    tgt = float(os.environ.get("PORTFOLIO_TARGET_PCT", "24")) / 100
    pos = [r for r in out if r["kind"] == "position"]
    cost = sum(r["shares"] * r["avg_cost"] for r in pos
               if r["avg_cost"])
    val = sum(r["shares"] * r["price"] for r in pos if r["price"])
    priced_cost = sum(r["shares"] * r["avg_cost"] for r in pos
                      if r["avg_cost"] and r["price"])
    pnl = val - priced_cost
    book = {"positions": len(pos),
            "cost": round(cost), "value": round(val),
            "pnl": round(pnl),
            "pnl_pct": round(pnl / priced_cost * 100, 1)
                       if priced_cost else None,
            "unpriced_cost": round(cost - priced_cost),
            "target_pct": tgt * 100,
            "pace_month": round(((1 + tgt) ** (1 / 12) - 1) * 100, 2),
            "pace_week": round(((1 + tgt) ** (1 / 52) - 1) * 100, 2),
            "target_value_12m": round(cost * (1 + tgt)),
            "goal_month": round(cost * ((1 + tgt) ** (1 / 12) - 1))}
    # daily book snapshot — first write wins; the pace series.
    _BOOK_ID = "00000000-0000-0000-0000-00000000000b"
    try:
        db.execute_update(
            "INSERT INTO portfolio_snapshots (portfolio_id,"
            " snapshot_date, total_value, invested_value, cash_balance)"
            " VALUES (CAST(:pid AS uuid), CURRENT_DATE, :v, :c, 0)"
            " ON CONFLICT (portfolio_id, snapshot_date) DO UPDATE SET"
            " total_value=EXCLUDED.total_value,"
            " invested_value=EXCLUDED.invested_value",
            {"pid": _BOOK_ID, "v": val, "c": cost})
        base = db.execute_query(
            "SELECT snapshot_date, total_value FROM portfolio_snapshots"
            " WHERE portfolio_id=CAST(:pid AS uuid)"
            " ORDER BY snapshot_date LIMIT 1",
            {"pid": _BOOK_ID})
        if base and base[0]["total_value"] and val:
            days = (datetime.now().date()
                    - base[0]["snapshot_date"]).days
            since = (val / float(base[0]["total_value"]) - 1) * 100
            tgt_since = ((1 + tgt) ** (days / 365.0) - 1) * 100
            book.update({"track_days": days,
                         "track_ret_pct": round(since, 1),
                         "track_target_pct": round(tgt_since, 1),
                         "on_pace": bool(since >= tgt_since)})
            if days > 0:  # SPY context over the same window
                try:
                    from app.market_data import bars as _bars
                    allb = _bars.load(["SPY"],
                                      days=days + 15).get("SPY") or []
                    at = [b for b in allb
                          if b.date <= base[0]["snapshot_date"]]
                    now = [b for b in allb
                           if b.date <= datetime.now().date()]
                    if at and now and at[-1].close:
                        spy = (now[-1].close / at[-1].close - 1) * 100
                        book["spy_ret_pct"] = round(spy, 1)
                        book["excess_pct"] = round(since - spy, 1)
                except Exception:
                    pass
    except Exception:
        pass
    return {"as_of": str(datetime.now().date()), "rows": out,
            "book": book}


@router.get("/conviction/leaderboard")
async def conviction_leaderboard():
    """How the picks are actually performing — per-symbol persistence
    and graded returns; and per-lane hit-rate so 'watch vs deploy'
    is measured, not assumed."""
    from app.database import db
    per_sym = db.execute_query(
        "SELECT symbol, count(*) days_on_list,"
        " count(*) FILTER (WHERE daily_pick) pick_days,"
        " count(*) FILTER (WHERE weekly_pick) weekly_wins,"
        " count(*) FILTER (WHERE monthly_pick) monthly_wins,"
        " max(score) best_score, avg(ret_20d) avg_ret_20d,"
        " avg(vs_spy_20d) avg_vs_spy"
        " FROM conviction_snapshots GROUP BY symbol"
        " ORDER BY days_on_list DESC, best_score DESC")
    by_lane = db.execute_query(
        "SELECT lane, count(*) n,"
        " count(*) FILTER (WHERE ret_20d > 0) hit_20d,"
        " avg(ret_20d) avg_ret_20d, avg(vs_spy_20d) avg_vs_spy"
        " FROM conviction_snapshots WHERE ret_20d IS NOT NULL"
        " GROUP BY lane")
    return {"symbols": [dict(r) for r in per_sym],
            "by_lane": [dict(r) for r in by_lane]}


@router.get("/hidden-gems/performance")
async def hidden_gems_performance():
    """Mode-A — shadow-grading report: fills forward returns on
    matured journal snapshots, then reports hit-rate by score band.
    This is the real out-of-sample backtest once history accrues."""
    from app.signals import hidden_gems_backtest as bt
    await asyncio.to_thread(bt.grade_snapshots)
    return await asyncio.to_thread(bt.performance)


@router.post("/refresh/{job}")
async def refresh(job: str):
    """Kick off a named data refresh in the background."""
    if job == "all":
        if _jobs.get("all", {}).get("running"):
            return {"status": "already_running", "job": job}
        _mark("all", running=True)
        asyncio.create_task(_run_all())
        return {"status": "started", "job": job}
    if job not in JOBS:
        raise HTTPException(404, f"unknown job '{job}' — "
                               f"one of {sorted(JOBS)} or 'all'")
    if _jobs.get(job, {}).get("running"):
        return {"status": "already_running", "job": job}
    asyncio.create_task(_run_job(job))
    return {"status": "started", "job": job}


@router.get("/pilot")
async def pilot_report():
    """Swing pilot book — open paper trades, closed journal, learned
    weights. Advisory simulation; nothing executes."""
    from app.signals import swing_pilot
    return await asyncio.to_thread(swing_pilot.report)


@router.get("/symbol/{sym}/technicals")
async def symbol_technicals(sym: str):
    """On-demand technical read for one symbol — live bars, indicators,
    classification. Bypasses the cache; user-driven lookups want the
    freshest bar, not the last batch's."""
    from app.market_data import bars as bars_mod
    from app.options.leaps import _technicals, _macd_hist_prev
    from app.signals import momentum_regime as mr

    def _go():
        b = bars_mod.live(sym.upper(), period="2y")
        if len(b) < 60:
            return {"error": f"insufficient bars for {sym.upper()}",
                    "bars": len(b)}
        tech = _technicals(b)
        dip = mr.dip_health(tech, _macd_hist_prev(b), b)
        st = mr.classify(tech, _macd_hist_prev(b), b)
        d = mr.detail(tech)
        if dip:
            d.update(dip)
        try:                                # swing-point structure
            from app.signals.swing_lows import higher_low_setup
            closes = [x.close for x in b]
            s50p = (sum(closes[-55:-5]) / 50 if len(closes) >= 55
                    else None)
            sw = higher_low_setup(b, sma50=tech.get("sma50"),
                                  sma50_prev=s50p)
            if sw:
                d["swing"] = sw
        except Exception:
            pass
        last = b[-1]
        return {"symbol": sym.upper(), "as_of": str(last.date),
                "close": last.close, "state": st, "detail": d,
                "bars": len(b)}
    return await asyncio.to_thread(_go)


@router.get("/symbol/{sym}/fundamentals")
async def symbol_fundamentals(sym: str):
    """On-demand fundamental read — stored flags/snapshot + live
    yfinance profile when the DB has nothing on the symbol."""
    from app.database import db

    def _go():
        s = sym.upper()
        row = db.execute_query(
            "SELECT symbol, fundamental_state, fundamental_risk,"
            " fundamental_detail, fundamental_updated_at FROM stocks"
            " WHERE symbol=:s", {"s": s})
        snap = db.execute_query(
            "SELECT as_of, state, metrics FROM fundamental_snapshots"
            " WHERE symbol=:s ORDER BY as_of DESC LIMIT 1",
            {"s": s})
        out = {"symbol": s,
               "stored": row[0] if row else None,
               "last_snapshot": snap[0] if snap else None}
        if not row or not (row[0] or {}).get("fundamental_state"):
            try:                            # live fallback — first look
                import yfinance as yf
                info = yf.Ticker(s).info or {}
                out["live"] = {
                    "name": info.get("shortName"),
                    "sector": info.get("sector"),
                    "mktcap": info.get("marketCap"),
                    "rev_growth": info.get("revenueGrowth"),
                    "gross_margins": info.get("grossMargins"),
                    "fwd_pe": info.get("forwardPE"),
                    "eps_growth": info.get("earningsQuarterlyGrowth")}
            except Exception as exc:
                out["live_error"] = str(exc)[:200]
        return out
    return await asyncio.to_thread(_go)


@router.get("/symbol/{sym}/health")
async def symbol_health(sym: str):
    """The per-stock health card — fundamental state + tape state +
    growth/quality + conviction/gem/hedge reads + future themes,
    synthesized into a verdict that names conflicts (strong
    fundamentals + broken tape = 'watch, don't catch the knife')."""
    from app.signals.stock_health import card
    return await asyncio.to_thread(card, sym.upper())


@router.get("/readiness")
async def readiness_board():
    """Board-wide readiness screen — the per-symbol swing / invest /
    LEAP-call / LEAP-put checklists computed over stored engine data,
    grouped ready → close → no."""
    from app.signals.stock_health import board
    return await asyncio.to_thread(board)


@router.get("/symbol/{sym}/tailwinds")
async def symbol_tailwinds(sym: str):
    """Pre-revenue channel journal for one symbol — extracted from the
    live alert_items catalyst flow, corroboration-promoted."""
    from app.signals import tailwinds as tw
    return await asyncio.to_thread(tw.for_symbol, sym.upper())


@router.post("/symbol/{sym}/analyze-doc")
async def analyze_doc(sym: str, body: dict):
    """Curated-document extraction — paste an article/note, bounded
    LLM pass returns quote-grounded claims; channel/risk claims journal
    into tailwinds, watch items into thesis_watches. The LLM never
    scores — every claim is verbatim-evidenced or dropped."""
    from app.signals import doc_extract
    return await asyncio.to_thread(
        doc_extract.analyze, sym,
        body.get("text") or "", body.get("url") or "",
        body.get("title") or "")


@router.get("/symbol/{sym}/swing-check")
async def symbol_swing_check(sym: str):
    """On-demand: run the real swing-screener evaluation for ONE
    symbol — fresh bars, setup detection, permission, score,
    entry/stop/target — same path the nightly screen uses."""
    from app.screener import service
    from app.market_data import MarketDataService
    from app.symbol_overlay import persisted_overlay
    svc = MarketDataService()
    env, _card = service._current_env()
    regime = service._neutral_regime()
    spy_bars = await svc.get_ohlcv("SPY", period="1y",
                                   prefer=["fmp", "yahoo_finance"])
    overlay = persisted_overlay([sym.upper()])
    row = await service._screen_symbol(
        sym.upper(), {}, spy_bars, regime, env, svc, overlay)
    return row or {"symbol": sym.upper(),
                   "note": "insufficient bars (<200) or no setup"}


@router.get("/symbol/{sym}/options-screen")
async def symbol_options_screen(sym: str):
    """On-demand: LEAPS screen for ONE symbol — direction verdict,
    contract candidates (delta/extrinsic/spread/OI scoring), IV +
    IV/HV, the iv_snapshots write."""
    from app.options.leaps import leaps_screen
    return await leaps_screen(sym.upper())


@router.post("/symbol/{sym}/refresh")
async def symbol_refresh(sym: str):
    """On-demand: fetch this one symbol's bars now, store them, and
    recompute + persist its momentum flag — a single-stock refresh
    without running the whole batch."""
    from app.market_data import bars as bars_mod
    from app.options.leaps import _technicals, _macd_hist_prev
    from app.signals import momentum_regime as mr

    def _go():
        s = sym.upper()
        b = bars_mod.live(s, period="2y")
        if len(b) < 60:
            return {"error": f"insufficient bars for {s}",
                    "bars": len(b)}
        try:
            bars_mod._upsert(s, b)          # keep canonical store fresh
        except Exception:
            pass
        tech = _technicals(b)
        st = mr.refresh_symbol(s, tech, _macd_hist_prev(b), b)
        return {"symbol": s, "state": st, "bars": len(b),
                "as_of": str(b[-1].date), "close": b[-1].close}
    return await asyncio.to_thread(_go)


@router.post("/symbol/{sym}/fundamentals-refresh")
async def symbol_fundamentals_refresh(sym: str):
    """On-demand: rebuild this symbol's flywheel from the provider
    (rev/eps growth, estimate revisions, margins — cascades the
    earnings calendar), then re-classify + persist the fundamental
    state. Same path the nightly job runs, one symbol."""
    def _go():
        s = sym.upper()
        from app.database import db
        from app.providers.financial_modeling_prep.client import (
            EnhancedFMPClient)
        from app.signals.expectation_gap import compute_flywheel
        fly = compute_flywheel(EnhancedFMPClient.from_settings(), s)
        from app.signals.fundamental_health import refresh_all
        refresh_all([s])
        row = db.execute_query(
            "SELECT fundamental_state, fundamental_risk,"
            " fundamental_updated_at FROM stocks WHERE symbol=:s",
            {"s": s})
        r = dict(row[0]) if row else {}
        return {"symbol": s, "state": r.get("fundamental_state"),
                "risk": r.get("fundamental_risk"),
                "as_of": (str(r.get("fundamental_updated_at"))
                          if r.get("fundamental_updated_at") else None),
                "rev_growth": fly.get("rev_growth"),
                "eps_growth": fly.get("eps_growth"),
                "est_revision_pct": fly.get("est_revision_pct"),
                "next_earnings": str((fly.get("earnings") or {}).get(
                    "next_earnings_date") or "") or None}
    return await asyncio.to_thread(_go)


@router.get("/macro-events")
async def macro_events(days: int = 45):
    """Forward macro calendar — FOMC, jobs report, CPI/PPI/PCE — the
    scheduled dates that move regime. Rule-derived entries flagged est."""
    from app.market_events.calendar import upcoming_macro_events
    return {"events": await asyncio.to_thread(
        upcoming_macro_events, min(days, 120))}


@router.get("/event-day")
async def event_day_report():
    """Today's macro-event judge call + the graded track record per
    event kind. Advisory — never overrides deterministic regime."""
    from app.signals import event_day
    return {"today": await asyncio.to_thread(event_day.snapshot),
            "latest": await asyncio.to_thread(event_day.read_call),
            "record": await asyncio.to_thread(event_day.record)}


@router.get("/morning-regime")
async def morning_regime_report():
    """Today's morning regime + graded track record. Daily engine —
    deterministic 7-bucket score → 5-regime class → LLM explains."""
    from app.market_regime import morning
    from app.database import db
    today = await asyncio.to_thread(
        lambda: db.execute_query(
            "SELECT as_of, regime, ai_regime, score, confidence, "
            "buckets, llm, verdict, horizon_1m, horizon_3m "
            "FROM morning_regime_snapshots "
            "ORDER BY as_of DESC LIMIT 1"))
    return {"today": today[0] if today else None,
            "record": await asyncio.to_thread(morning.record)}


@router.get("/calls")
async def calls_report():
    """Top-3 swing calls — today's picks with plans + recent history."""
    from app.signals import daily_calls
    return await asyncio.to_thread(daily_calls.report)


@router.get("/put-calls")
async def put_calls_report():
    """Top-3 put calls — leap_put-ready names with plans + history."""
    from app.signals import daily_puts
    return await asyncio.to_thread(daily_puts.report)


@router.get("/defense")
async def defense_card():
    """Portfolio Defense & Recovery card — canonical defensive state,
    hedge coverage vs target, IV gate, capitulation, recovery capital,
    and the gated bear-alpha candidates. Composition only — every
    number is owned by its engine."""
    from app.options import pdr
    return await asyncio.to_thread(pdr.state)


@router.get("/fund-momentum")
async def fund_momentum_report():
    """Fundamental-momentum radar — names whose fundamentals are
    rapidly improving (snapshot deltas + revisions) on healthy tape.
    The 'add to portfolio' candidate list."""
    from app.signals import daily_calls
    return {"items": await asyncio.to_thread(daily_calls.fund_momentum)}


@router.get("/hl-triggers")
async def hl_triggers(max_dist: float = 0.03):
    """Higher-low trigger watchlist — names within `max_dist` of the
    close that confirms their pullback structure, plus already-confirmed
    names. Pure stored-state read (momentum_detail.swing + latest
    daily_bars close); refreshed by the momentum job."""
    from app.signals.swing_lows import triggers
    return await asyncio.to_thread(triggers, max_dist)


@router.get("/meta")
async def meta_report():
    """Latest self-training report — signal lifts, calibration,
    weight writes."""
    from app.database import db
    rows = db.execute_query(
        "SELECT value, updated_at FROM engine_weights"
        " WHERE key='meta:report'")
    return (rows[0] if rows else
            {"value": {"notes": ["meta has not run yet"]}})


@router.get("/jobs/catalog")
async def jobs_catalog():
    """Job registry — every known job with purpose, schedule and last
    run. The AutoSys-style catalog the page and dispatcher share."""
    from app.support import scheduler
    return {"jobs": await asyncio.to_thread(scheduler.catalog)}


@router.post("/jobs/{name}/schedule")
async def set_job_schedule(name: str, body: dict):
    """Enable/disable + cron for a job — the only write path the
    dispatcher honors."""
    from app.support import scheduler
    return await asyncio.to_thread(
        scheduler.set_schedule, name, body.get("cron"),
        bool(body.get("enabled")))


@router.get("/jobs/runs")
async def job_runs(limit: int = 50):
    """Recent dispatcher executions — the durable ledger the scheduler
    page shows under the catalog."""
    from app.database import db
    rows = await asyncio.to_thread(
        db.execute_query,
        "SELECT name, ran_at, duration_s, error, result"
        " FROM job_runs ORDER BY ran_at DESC LIMIT :n",
        {"n": min(limit, 200)})
    return {"runs": rows}


@router.get("/incidents")
async def custodian_incidents():
    """Open incidents + recent custodian actions — the support agent's
    ledger for the board's health strip."""
    from app.support import custodian
    return await asyncio.to_thread(custodian.incidents)


@router.post("/incidents/{signature}/resolve")
async def incident_resolve(signature: str):
    """Human acknowledgement — mark an incident resolved. If the
    signature fires again the sensor reopens it with occurrences+1
    and a fresh alert gate."""
    from app.database import db
    n = await asyncio.to_thread(
        db.execute_update,
        "UPDATE custodian_incidents SET status='resolved',"
        " resolved_at=now() WHERE signature=:s",
        {"s": signature})
    return {"resolved": n}


@router.post("/incidents/{signature}/analyze")
async def incident_analyze(signature: str):
    """Research agent — bounded root-cause analysis over the incident's
    captured log evidence. Rules first, LLM second when a key exists.
    Output is a diagnosis + fix plan, never an auto-applied change."""
    from app.support.analyst import analyze
    return await asyncio.to_thread(analyze, signature)


@router.get("/tickets")
async def custodian_tickets():
    """Staged tickets — the JIRA-style backlog the analyst proposes.
    Created only via explicit human action on the Custodian page."""
    from app.database import db
    rows = await asyncio.to_thread(
        db.execute_query,
        "SELECT * FROM custodian_tickets ORDER BY id DESC LIMIT 50")
    return {"tickets": rows}


@router.post("/tickets")
async def custodian_ticket_create(body: dict):
    """File a ticket draft — the human-approve step between 'the agent
    proposed a fix' and 'it becomes work'. Key minted as CUST-<id>."""
    import json
    from app.database import db
    row = await asyncio.to_thread(
        db.execute_query,
        """INSERT INTO custodian_tickets
               (signature, issue_type, title, description, root_cause,
                proposed_fix, patch, evidence, source)
           VALUES (:sig, :it, :t, :d, :rc, :pf, :p,
                   CAST(:ev AS jsonb), :src)
           RETURNING id""",
        {"sig": body.get("signature", ""), "it": body.get("issue_type", "code"),
         "t": body.get("title", "untitled")[:200],
         "d": body.get("description"), "rc": body.get("root_cause"),
         "pf": body.get("proposed_fix"), "p": body.get("patch"),
         "ev": json.dumps(body.get("evidence") or {}),
         "src": body.get("source", "manual")})
    tid = row[0]["id"] if row else None
    if tid:
        await asyncio.to_thread(
            db.execute_update,
            "UPDATE custodian_tickets SET ticket_key=:k WHERE id=:i",
            {"k": f"CUST-{tid}", "i": tid})
    return {"id": tid, "ticket_key": f"CUST-{tid}" if tid else None}


@router.get("/refresh/status")
async def refresh_status():
    """Last-run state per job — in-memory first, then the durable
    job_runs ledger so staleness survives worker restarts."""
    jobs = dict(_jobs)
    missing = [k for k in (*JOBS, "all")
               if not jobs.get(k, {}).get("at")]
    if missing:
        try:
            from app.database import db
            rows = await asyncio.to_thread(
                db.execute_query,
                "SELECT DISTINCT ON (name) name, ran_at, duration_s,"
                " error FROM job_runs WHERE name = ANY(:n)"
                " ORDER BY name, ran_at DESC",
                {"n": missing})
            for r in rows:
                jobs[r["name"]] = {
                    "at": (r["ran_at"].isoformat()
                           if hasattr(r["ran_at"], "isoformat")
                           else str(r["ran_at"])),
                    "duration_s": r.get("duration_s"),
                    "error": r.get("error"),
                    "restored": True}
        except Exception:
            pass
    return {"jobs": jobs,
            "catalog": {k: v[0] for k, v in JOBS.items()}}


@router.get("/garp")
async def garp(max_pe: float = 40.0, limit: int = 50,
               states: str = ""):
    """GARP screen — fundamentally accelerating/growing names at a
    reasonable price. Good company × fair price × entry quality."""
    from app.signals.garp import garp_screen
    st = tuple(s.strip() for s in states.split(",") if s.strip()) \
        or ("accelerating", "growing", "cyclical")
    return await asyncio.to_thread(garp_screen, max_pe, limit, st)


@router.get("/styles")
async def styles(limit: int = 15):
    """Style buckets — one flag set, five lanes: compounders (sure-shot),
    value, hypergrowth, multi-bagger watch, cyclical recovery."""
    from app.signals.garp import style_screen
    return await asyncio.to_thread(style_screen, limit)


@router.get("/fund-flags")
async def fund_flags(symbols: str = ""):
    """symbol → fundamental flag/risk/alert for display joins."""
    from app.database import db
    q = ("SELECT symbol, fundamental_state AS state,"
         " fundamental_risk AS risk,"
         " fundamental_detail->>'alert' AS alert,"
         " fundamental_detail->'changes' AS changes,"
         " fundamental_detail->>'cyclical_lean' AS lean "
         "FROM stocks WHERE fundamental_state IS NOT NULL"
         + (" AND symbol = ANY(:s)" if symbols else ""))
    params = {"s": [x.strip().upper() for x in symbols.split(",")
                    if x.strip()]} if symbols else None
    return await asyncio.to_thread(db.execute_query, q, params)


@router.get("/focus/members")
async def focus_members():
    """Active focus-book members with their theses."""
    from app.database import db
    return await asyncio.to_thread(
        db.execute_query,
        "SELECT symbol, thesis, added_at::text AS added_at "
        "FROM focus_members WHERE active ORDER BY symbol")


@router.post("/focus/{symbol}")
async def focus_add(symbol: str, thesis: str = ""):
    """Add (or reactivate) a focus-book member. Also vivifies a stocks
    row so momentum/board scoring can pick it up on the next refresh."""
    sym = symbol.upper().strip()
    if not (1 <= len(sym) <= 10 and sym.replace(".", "").isalnum()):
        raise HTTPException(400, f"bad symbol '{symbol}'")
    from app.database import db

    def _go():
        db.execute_query(
            "INSERT INTO stocks (symbol) VALUES (:s) "
            "ON CONFLICT (symbol) DO NOTHING", {"s": sym})
        return db.execute_query(
            "INSERT INTO focus_members (symbol, thesis, active) "
            "VALUES (:s, :t, TRUE) "
            "ON CONFLICT (symbol) DO UPDATE SET active=TRUE, "
            "thesis=COALESCE(NULLIF(:t,''), focus_members.thesis) "
            "RETURNING symbol, thesis",
            {"s": sym, "t": thesis.strip()})
    out = await asyncio.to_thread(_go)
    return {"added": out}


@router.delete("/focus/{symbol}")
async def focus_remove(symbol: str):
    """Deactivate a focus-book member (keeps its event history)."""
    sym = symbol.upper().strip()
    from app.database import db
    out = await asyncio.to_thread(
        db.execute_query,
        "UPDATE focus_members SET active=FALSE WHERE symbol=:s "
        "RETURNING symbol", {"s": sym})
    if not out:
        raise HTTPException(404, f"{sym} not in focus book")
    return {"removed": sym}


@router.get("/track-record")
async def track_record():
    """Board accuracy by action × momentum state, plus per-instrument
    grading — LEAPS actions grade out to 60 trading days (~3 months),
    stock actions to 20d."""
    from app.signals import board_tracking as bt
    out = await asyncio.to_thread(bt.track_record)
    out["instruments"] = await asyncio.to_thread(bt.instrument_record)
    out["regime"] = await asyncio.to_thread(bt.regime_record)
    try:
        from app.options import crash_alpha
        out["crash_alpha"] = await asyncio.to_thread(crash_alpha.record)
    except Exception:
        out["crash_alpha"] = None
    try:
        from app.market_regime.rotation_backtest import record as _rot_rec
        out["rotation"] = await asyncio.to_thread(_rot_rec)
    except Exception:
        out["rotation"] = None
    return out


@router.get("/hedge")
async def hedge_state():
    """The insurance card — coverage vs regime-scaled target, spend
    vs adaptive budget, open spreads and their realized value."""
    from app.options import hedge_book
    return await asyncio.to_thread(hedge_book.state)


@router.get("/hedge/suggest")
async def hedge_suggest():
    """The next tranche — live QQQ put-spread structure sized to
    fill the coverage gap."""
    from app.options import hedge_book
    return await asyncio.to_thread(hedge_book.suggest_structure)


@router.post("/hedge/open")
async def hedge_open(body: dict):
    """Journal a put-spread the human opened — system remembers,
    marks, and runs the monetization ladder."""
    from app.options import hedge_book
    return await asyncio.to_thread(hedge_book.open_spread, body)


@router.post("/hedge/{pos_id}/trim")
async def hedge_trim(pos_id: int, body: dict):
    """Journal a partial monetization (ladder fill)."""
    from app.options import hedge_book
    return await asyncio.to_thread(
        hedge_book.trim_spread, pos_id,
        float(body.get("pct", 0.25)), body.get("mid"))


@router.post("/hedge/{pos_id}/close")
async def hedge_close(pos_id: int, body: dict):
    """Journal a hedge unwind."""
    from app.options import hedge_book
    return await asyncio.to_thread(
        hedge_book.close_spread, pos_id,
        body.get("close_value"), body.get("reason", "manual"))


@router.get("/hedge/crash-alpha")
async def crash_alpha_state():
    """Crash-alpha card — capitulation score, ranked put-spread
    candidates, IV-pricing gate, and the PUT→CALL redeploy list."""
    from app.options import crash_alpha
    out = await asyncio.to_thread(crash_alpha.state)
    out["record"] = await asyncio.to_thread(crash_alpha.record)
    return out


@router.get("/rotation/backtest")
async def rotation_backtest():
    """Replay the sector-flow classifier over stored bars — do
    rotating_in/inflow signals precede forward outperformance?"""
    from app.market_regime.rotation_backtest import replay
    return await asyncio.to_thread(replay)


@router.get("/rotation/june-audit")
async def rotation_june_audit():
    """Day-by-day SMH/IGV flow trail through the 2026 semis→software
    rotation — how early the signal fired vs. the confirmed flip."""
    from app.market_regime.rotation_backtest import june_audit
    return await asyncio.to_thread(june_audit)


@router.get("/hedge/crash-alpha/backtest")
async def crash_alpha_backtest():
    """Replay the capitulation composite over stored daily_bars —
    score bands vs forward SPY returns. The 'would the threshold
    have fired usefully' check."""
    from app.options import crash_alpha
    return await asyncio.to_thread(crash_alpha.backtest)


@router.get("/hedge/engine")
async def hedge_engine_report():
    """Vehicle comparison — QQQM put spread vs SQQQ sleeve — with a
    3y historical replay of the rolling hedge program on stored bars."""
    from app.options import hedge_engine
    try:
        bt = await asyncio.to_thread(hedge_engine.backtest)
    except Exception as exc:
        bt = {"error": str(exc)}
    cands = await asyncio.to_thread(hedge_engine.candidates)
    return {"backtest": bt, **cands}


# learning tables → the timestamp column that means "last write"
_LEARN_TABLES = {
    "engine_weights": "updated_at",
    "engine_weights_log": "created_at",
    "pattern_priors": "computed_at",
    "swing_pilot_trades": "created_at",
    "board_decisions": "created_at",
    "board_outcomes": None,           # grading rows — no timestamp col
    "daily_calls": "created_at",
    "capex_snapshots": "created_at",
    "transcript_scores": "scored_at",
    "iv_snapshots": "as_of",
    "alert_items": "created_at",
    "focus_events": "detected_at",
}


@router.get("/learning")
async def learning_lab():
    """The training-lab feed — engine status, data accrual, learned
    corrections, calibration, and the next milestone each engine is
    waiting on. All reads of stored state; zero fetches."""
    from app.database import db
    import json as _j

    out: dict = {"engines": [], "tables": {}, "learned": [],
                 "milestones": [], "calibration": None}

    # --- per-table accrual -------------------------------------------
    for t, ts in _LEARN_TABLES.items():
        try:
            q = (f"SELECT count(*) n"
                 + (f", max({ts}) latest" if ts else "")
                 + f" FROM {t}")
            r = db.execute_query(q)[0]
            out["tables"][t] = {"rows": r["n"],
                                "latest": str(r.get("latest"))[:19]
                                if r.get("latest") else None}
        except Exception:
            out["tables"][t] = {"rows": 0, "latest": None,
                                "missing": True}

    # --- learned corrections: every engine_weight that isn't a config
    # snapshot — dip:*, gate:*, meta:* writes are the system changing
    # its own mind -----------------------------------------------------
    try:
        rows = db.execute_query(
            "SELECT key, value, updated_at FROM engine_weights"
            " WHERE key ~ '^(dip:|gate:|meta:)' ORDER BY key")
        for r in rows:
            v = r["value"]
            if isinstance(v, str):
                v = _j.loads(v)
            out["learned"].append({"key": r["key"], "value": v,
                                   "updated": str(r["updated_at"])[:19]})
    except Exception:
        pass

    meta_rep = next((l["value"] for l in out["learned"]
                     if l["key"] == "meta:report"), {}) or {}
    out["calibration"] = meta_rep.get("calibration")

    # --- engine cards --------------------------------------------------
    def _ew(key):
        r = db.execute_query(
            "SELECT value, updated_at FROM engine_weights"
            " WHERE key=:k", {"k": key})
        if not r:
            return None, None
        v = r[0]["value"]
        return (v if not isinstance(v, str) else _j.loads(v)), \
            str(r[0]["updated_at"])[:19]

    engines = []
    # meta learner
    _, meta_at = _ew("meta:report")
    engines.append({
        "engine": "meta_learn", "cadence": "nightly",
        "what": "signal lift + calibration → bounded dip:/gate: "
                "weight writes",
        "last": meta_at,
        "state": (f"{meta_rep.get('outcomes_n', 0)} graded outcomes · "
                  f"{meta_rep.get('pilot_closed', 0)} closed pilot "
                  f"trades · {len(meta_rep.get('writes') or [])} "
                  "writes last run"),
        "waiting": (f"{meta_rep.get('outcomes_n', 0)}/20 outcomes to "
                    "first weight write" if (meta_rep.get("outcomes_n")
                                           or 0) < 20 else None)})
    # swing pilot
    pilot = out["tables"].get("swing_pilot_trades") or {}
    engines.append({
        "engine": "swing_pilot", "cadence": "daily",
        "what": "paper-trades board flags → journal → learned gates",
        "last": pilot.get("latest"),
        "state": f"{pilot.get('rows', 0)} trades journaled",
        "waiting": ("≥10 closed trades per pattern before a gate can "
                    "flip")})
    # pattern priors
    pr = out["tables"].get("pattern_priors") or {}
    engines.append({
        "engine": "pattern_priors", "cadence": "job (~10min replay)",
        "what": "15mo classifier replay → hit-rate priors per tape "
                "pattern",
        "last": None,
        "state": f"{pr.get('rows', 0)} prior rows across symbols",
        "waiting": None})
    # board tracking
    bd, bo = out["tables"].get("board_decisions") or {}, \
        out["tables"].get("board_outcomes") or {}
    engines.append({
        "engine": "board_tracking", "cadence": "outcomes job",
        "what": "grades board picks at 5/10/20d forward returns",
        "last": bd.get("latest"),
        "state": f"{bd.get('rows', 0)} decisions · "
                 f"{bo.get('rows', 0)} graded",
        "waiting": ("outcomes feed meta — each decision needs its "
                    "5/10/20d windows to pass" if not bo.get("rows")
                    else None)})
    # capex engine
    cx, cx_at = _ew("capex:cycle")
    cs = out["tables"].get("capex_snapshots") or {}
    cx_wait = None
    if cx and cx.get("d3m") is None:
        cx_wait = ("Δ3m/Δ6m deltas unlock after ~90 days of snapshots "
                   f"({cs.get('rows', 0)} so far)")
    engines.append({
        "engine": "capex_cycle", "cadence": "with momentum job",
        "what": "7-leg capex slowdown score + language blend + "
                "rotation spread",
        "last": cx_at,
        "state": (f"score {cx.get('score')} · {cx.get('band')} · "
                  f"{cx.get('n_elevated', 0)}/7 legs elevated")
                 if cx else "not run yet",
        "waiting": cx_wait})
    # transcript language
    tl, tl_at = _ew("capex:language")
    ts = out["tables"].get("transcript_scores") or {}
    engines.append({
        "engine": "transcript_lang", "cadence": "weekly (with "
                "fundamentals)",
        "what": "SEC 8-K earnings-release language → demand/capex/"
                "orders scores, verbatim quotes required",
        "last": tl_at,
        "state": f"{ts.get('rows', 0)} symbol-quarters scored",
        "waiting": None})
    # iv context
    iv = out["tables"].get("iv_snapshots") or {}
    engines.append({
        "engine": "iv_context", "cadence": "per options screen",
        "what": "daily ATM-IV prints → true IV rank vs own 1y history",
        "last": iv.get("latest"),
        "state": f"{iv.get('rows', 0)} prints",
        "waiting": ("needs ≥20 daily prints per symbol — accrues "
                    "automatically when the leaps-mark job prices open "
                    "positions (chain ATM-IV piggybacks the mark) or "
                    "when options screens run"
                    if (iv.get("rows") or 0) < 20 else None)})
    out["engines"] = engines
    # capex snapshot trend for the page's calibration section
    try:
        r = db.execute_query(
            "SELECT as_of, score FROM capex_snapshots ORDER BY as_of")
        out["capex_history"] = [{"as_of": str(x["as_of"]),
                                 "score": float(x["score"])}
                                for x in r]
    except Exception:
        out["capex_history"] = []
    return out


# ---------------- trade plans ----------------------------------------------

@router.get("/trade-plans/suggest")
async def tp_suggest(sym: str, uc: str = "swing",
                     px: float | None = None):
    """Engine-proposed plan for a symbol+use-case — structure stop,
    R-targets, trail rule, time stop computed from stored levels.
    The Stock page form pre-fills from this; the human edits then
    POSTs /trade-plans."""
    from app.signals import trade_plans
    return await asyncio.to_thread(trade_plans.suggest, sym.upper(),
                                   uc, px)


@router.post("/trade-plans")
async def tp_create(body: dict):
    """Open a trade plan. Missing levels auto-fill from suggest();
    entry_snapshot journals what the engine saw at entry."""
    from app.database import db
    from app.signals import trade_plans
    import json
    sym = (body.get("symbol") or "").upper()
    uc = body.get("use_case") or "swing"
    if not sym or not body.get("entry_px"):
        return {"ok": False, "error": "symbol and entry_px required"}
    sug = trade_plans.suggest(sym, uc, float(body["entry_px"]))
    r = db.execute_query(
        "INSERT INTO trade_plans (symbol, use_case, direction,"
        " entry_px, entry_date, qty, stop_px, stop_basis, target1_px,"
        " target2_px, trail_rule, time_stop_days, thesis,"
        " entry_snapshot) VALUES (:s,:u,:d,:ep, COALESCE(:ed, CURRENT_DATE),:q,:sp,:sb,:t1,:t2,"
        " :tr,:ts,:th, CAST(:sn AS jsonb)) RETURNING id",
        {"s": sym, "u": uc, "d": sug["direction"],
         "ep": float(body["entry_px"]),
         "ed": body.get("entry_date") or None,
         "q": body.get("qty"),
         "sp": body.get("stop_px") or sug["stop_px"],
         "sb": sug["stop_basis"],
         "t1": body.get("target1_px") or sug["target1_px"],
         "t2": body.get("target2_px") or sug["target2_px"],
         "tr": body.get("trail_rule") or sug["trail_rule"],
         "ts": body.get("time_stop_days") or sug["time_stop_days"],
         "th": body.get("thesis"),
         "sn": json.dumps(sug, default=str)})
    return {"ok": True, "id": r[0]["id"] if r else None, "suggested": sug}


@router.get("/trade-plans")
async def tp_list(all: bool = False):
    """Open plans with live plan_status evals (+closed when all=1)."""
    from app.database import db
    from app.signals import trade_plans
    plans = await asyncio.to_thread(trade_plans.open_plans)
    closed = []
    if all:
        closed = [dict(r) for r in db.execute_query(
            "SELECT * FROM trade_plans WHERE status != 'open'"
            " ORDER BY closed_at DESC NULLS LAST LIMIT 100")]
    return {"open": plans, "closed": closed}


@router.post("/trade-plans/{pid}/close")
async def tp_close(pid: int, body: dict):
    """Close a plan — the human's decision journaled: close_px,
    reason, outcome R."""
    from app.database import db
    r = db.execute_query(
        "UPDATE trade_plans SET status='closed', closed_at=now(),"
        " close_px=:px, close_reason=:rs WHERE id=:p AND status='open'"
        " RETURNING id",
        {"px": body.get("close_px"), "rs": body.get("reason"), "p": pid})
    if not r:
        return {"ok": False, "error": "plan not found or already closed"}
    db.execute_update(
        "INSERT INTO trade_plan_events (plan_id, symbol, as_of, kind,"
        " action_hint, message) SELECT :p, symbol, CURRENT_DATE,"
        " 'closed', 'review', :m FROM trade_plans WHERE id=:p"
        " ON CONFLICT DO NOTHING",
        {"p": pid,
         "m": f"plan closed at {body.get('close_px')} — "
              f"{body.get('reason') or 'manual'}"})
    return {"ok": True}


@router.get("/trade-plans/events")
async def tp_events(limit: int = 50, unseen: bool = False):
    """The alert feed — status transitions journaled by eval_plan."""
    from app.database import db
    rows = db.execute_query(
        "SELECT * FROM trade_plan_events"
        + (" WHERE NOT seen" if unseen else "")
        + " ORDER BY created_at DESC LIMIT :l", {"l": limit})
    return {"events": [dict(r) for r in rows],
            "unseen": (db.execute_query(
                "SELECT count(*) c FROM trade_plan_events"
                " WHERE NOT seen")[0]["c"])}


@router.post("/trade-plans/events/{eid}/seen")
async def tp_event_seen(eid: int):
    from app.database import db
    db.execute_update("UPDATE trade_plan_events SET seen=true"
                      " WHERE id=:i", {"i": eid})
    return {"ok": True}


@router.post("/trade-plans/digest")
async def tp_digest():
    """Run the alert loop now — re-evaluate open plans, sweep unseen
    events into one digest email, mark seen. The scheduler calls the
    same function every 30min; this is the on-demand path."""
    from app.signals import trade_plans
    return await asyncio.to_thread(trade_plans.email_digest)


@router.post("/trade-plans/email-test")
async def tp_email_test(to: str | None = None):
    """Deliverability check — one test email to ALERT_EMAIL or the
    SMTP account itself. Verify it lands before trusting the feed."""
    from app.signals import trade_plans
    return await asyncio.to_thread(trade_plans.email_test, to)


@router.delete("/trade-plans/{pid}")
async def tp_delete(pid: int):
    """Delete a plan + its events — for accidentally-entered rows.
    The UI gates this behind an explicit confirm."""
    from app.database import db
    db.execute_update(
        "DELETE FROM trade_plan_events WHERE plan_id=:p", {"p": pid})
    n = db.execute_update(
        "DELETE FROM trade_plans WHERE id=:p", {"p": pid})
    return {"ok": bool(n)}


@router.get("/transitions")
async def transitions():
    """The 'just moved' feed — latest eval vs prior eval on both
    journals. readiness_evals covers the universe (use-case state
    transitions: no→ready etc.); pulse_rule_evals covers the
    portfolio/watchlist action engine (hold→add, watch→reduce)."""
    from app.database import db
    rd = db.execute_query("""
        WITH daily AS (
            SELECT DISTINCT ON (symbol, use_case, as_of)
                   symbol, use_case, state, score, of, as_of
            FROM readiness_evals
            ORDER BY symbol, use_case, as_of, created_at DESC),
        ranked AS (
            SELECT *, row_number() OVER (PARTITION BY symbol, use_case
                                         ORDER BY as_of DESC) rn
            FROM daily)
        SELECT a.symbol, a.use_case, b.state AS prev_state,
               a.state, a.score, a.of,
               b.as_of::text AS prev_as_of, a.as_of::text AS as_of
        FROM ranked a
        JOIN ranked b ON b.symbol=a.symbol AND b.use_case=a.use_case
                     AND b.rn=2
        WHERE a.rn=1 AND a.state != b.state
        ORDER BY CASE a.state WHEN 'ready' THEN 0
                              WHEN 'close' THEN 1 ELSE 2 END, a.symbol""")
    pu = db.execute_query("""
        WITH daily AS (
            SELECT DISTINCT ON (symbol, as_of)
                   symbol, as_of, action, label, matched_rule
            FROM pulse_rule_evals
            ORDER BY symbol, as_of, created_at DESC),
        ranked AS (
            SELECT *, row_number() OVER (PARTITION BY symbol
                                         ORDER BY as_of DESC) rn
            FROM daily)
        SELECT a.symbol, b.action AS prev_action, a.action,
               a.label, a.matched_rule,
               b.as_of::text AS prev_as_of, a.as_of::text AS as_of
        FROM ranked a
        JOIN ranked b ON b.symbol=a.symbol AND b.rn=2
        WHERE a.rn=1 AND a.action != b.action
        ORDER BY CASE a.action WHEN 'add' THEN 0 WHEN 'trim' THEN 1
                               WHEN 'reduce' THEN 2 ELSE 3 END,
                 a.symbol""")
    return {"readiness": [dict(r) for r in rd],
            "pulse": [dict(r) for r in pu]}


# ---------------- capital planner -----------------------------------------

@router.post("/planner/propose")
async def planner_propose(body: dict):
    """'I have $X — build me a book.' Regime sets the sleeve mix,
    readiness supplies candidates, trade_plans.suggest supplies
    levels; unfilled capacity honestly stays cash."""
    from app.signals import capital_planner
    cap = float(body.get("capital") or 0)
    if cap <= 0:
        return {"ok": False, "error": "capital required"}
    return await asyncio.to_thread(
        capital_planner.propose, cap,
        float(body.get("risk_pct") or 1.0),
        body.get("target_pct"), body.get("sleeves"))


@router.post("/planner/accept")
async def planner_accept(body: dict):
    """Journal the proposal + open a trade_plan per position — the
    status ladder, event feed and email digest then track the book."""
    from app.signals import capital_planner
    if not (body.get("positions") or []):
        return {"ok": False, "error": "nothing to accept"}
    return await asyncio.to_thread(capital_planner.accept, body)


@router.get("/planner/daily")
async def planner_daily(book_id: int | None = None):
    """Today's plan for the accepted book — plan statuses, overnight
    transitions on book symbols, regime shift."""
    from app.signals import capital_planner
    return await asyncio.to_thread(capital_planner.daily, book_id)


@router.get("/spec-pulse")
async def spec_pulse_board():
    """Speculative sleeve board — spec-semantic action hints for
    engine-member + unpriceable holdings and watch candidates.
    Thesis progress replaces fair value; exits are fast."""
    from app.signals import spec_pulse
    return await asyncio.to_thread(spec_pulse.board)


@router.get("/posture")
async def board_posture():
    """Today's trade posture — permission layer over the regime
    card: can we initiate longs, run shorts, is the hedge on.
    Plus the outcome stats: what each posture has meant forward."""
    from app.signals import posture
    res = await asyncio.to_thread(posture.current)
    res["stats"] = await asyncio.to_thread(posture.stats)
    return res


@router.get("/planner/books")
async def planner_books():
    """Proposal history — proposed/accepted books newest first."""
    from app.database import db
    rows = db.execute_query(
        "SELECT id, as_of, capital, target_pct, risk_pct, stance,"
        " regime, status, created_at FROM planner_books"
        " ORDER BY id DESC LIMIT 20")
    return {"books": [dict(r) for r in rows]}
