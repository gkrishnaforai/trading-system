"""Daily Action Board endpoints — the board itself + refresh dispatcher.

Every data layer the board reads gets a named refresh job so the UI can
offer one button per layer (plus 'all'). Jobs run in the background;
GET /board/refresh/status reports last-run state for the poll banner.
"""
from __future__ import annotations

import asyncio
import logging
import time
import traceback
import uuid
from datetime import date, datetime, timezone
from typing import Any, Callable, Optional

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

# symbol → epoch of last fv self-heal attempt — the health endpoint's
# stale-inputs heal fetches a ~6-leg provider bundle; per-view would
# burn the rate limit, so attempts are throttled to hourly
_fv_heal_last: dict[str, float] = {}


def _mark(job: str, run_id: str = "", **kw):
    at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if kw.get("running"):
        _jobs[job] = {"at": at, "started_at": at,
                      "run_id": run_id or None, **kw}
        return
    started = (_jobs.get(job) or {}).get("started_at")
    rid = run_id or (_jobs.get(job) or {}).get("run_id") or None
    dur = None
    if started:
        try:
            dur = round((datetime.now(timezone.utc)
                         - datetime.fromisoformat(started))
                        .total_seconds(), 1)
        except Exception:
            pass
    _jobs[job] = {"at": at, "run_id": rid, **kw}
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
            " result, run_id) VALUES (:n, now(), :d, :e,"
            " CAST(:r AS jsonb), :rid)",
            {"n": job, "d": dur, "e": (kw.get("error") or "")[:500]
             or None,
             "r": payload, "rid": rid})
    except Exception as exc:
        # silent ledger failure hid a missing column for days once —
        # log it; the job result itself is already in memory
        logger.warning("job_runs ledger write failed for %s: %s",
                       job, exc)


async def _tracked_symbols() -> list[str]:
    """The working set every per-symbol job runs on — the active
    coverage tier (portfolio ∪ watchlist ∪ book members ∪
    promoted futureStocks), NOT the whole stocks registry."""
    from app.database import db
    from app.signals import symbol_tiers
    rows = await asyncio.to_thread(
        db.execute_query, symbol_tiers._active_sql())
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
    try:                                    # lane picks → realized
        from app.screener.pick_outcomes import evaluate_pick_outcomes
        picks = await evaluate_pick_outcomes()
    except Exception:                       # forward returns
        picks = None
    try:                                    # selloff candidates → did
        from app.signals import selloff_review
        so = await asyncio.to_thread(selloff_review.grade)
    except Exception:                       # the beat-downs rebound?
        so = None
    return {"alerts": out, "patterns": pat, "board": bd, "puts": puts,
            "calls": calls, "regime": reg, "crash_alpha": alpha,
            "rotation": rot, "event_day": ev, "morning": mr,
            "picks": picks, "selloff": so}


async def _j_rule_breakers():
    """RB eval — gates, tier transitions, discovery, then flywheel +
    momentum refresh at the tail (already wired)."""
    from app.screener.rule_breakers import run_rule_breakers, rb_status, \
        discovery_due
    if rb_status()["running"]:
        return {"skipped": "already_running"}
    return await run_rule_breakers(discover=discovery_due())


async def _j_smallcap():
    """5x Scout full pass — manual; the scheduler runs the stages."""
    from app.screener.smallcap import run_smallcap, sc_status
    if sc_status()["running"]:
        return {"skipped": "already_running"}
    return await run_smallcap(discover=True)


async def _j_smallcap_eval():
    """5x Scout stage 1 — parallel deep eval of members."""
    from app.screener.smallcap import eval_members, sc_status
    if sc_status()["running"] or sc_status()["running_eval"]:
        return {"skipped": "already_running"}
    return await eval_members()


async def _j_smallcap_discovery():
    """5x Scout stage 2 — pool cursor sweep, auto-add qualifiers."""
    from app.screener.smallcap import discovery_sweep, sc_status
    if sc_status()["running"] or sc_status()["running_discovery"]:
        return {"skipped": "already_running"}
    return await discovery_sweep()


async def _j_smallcap_tail():
    """5x Scout stage 3 — research + flywheel + momentum refresh."""
    from app.screener.smallcap import sc_status, tail_refresh
    if sc_status()["running"] or sc_status()["running_tail"]:
        return {"skipped": "already_running"}
    return await tail_refresh()


async def _j_after_hours():
    """Extended-hours movers board — only meaningful inside its
    windows: post ≈ 4:30–8pm ET (20:30–00:00 UTC), pre ≈ 7–9:30am ET
    (11:00–13:30 UTC); yfinance carries the live fields then."""
    from app.screener.afterhours import run_session_job
    now_utc = datetime.now(timezone.utc)
    if now_utc.hour >= 20 or now_utc.hour < 1:
        return await run_session_job("post")
    if 11 <= now_utc.hour <= 13:
        return await run_session_job("pre")
    return {"skipped": "outside_session"}


async def _j_pt_watch():
    """Analyst-PT watch — one snapshot per date; the table's
    UNIQUE(symbol, as_of) makes reruns idempotent anyway."""
    from app.database import db
    from app.screener.pt_watch import run_pt_watch
    if db.execute_query(
            "SELECT 1 FROM pt_snapshots WHERE as_of = current_date "
            "LIMIT 1"):
        return {"skipped": "already_ran_today"}
    return await run_pt_watch()


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
    from app.database import db
    from app.market_regime.morning import snapshot
    today = date.today()
    res = await asyncio.to_thread(snapshot)
    if res:
        return res
    existing = db.execute_query(
        "SELECT id FROM morning_regime_snapshots WHERE as_of=:d",
        {"d": today})
    if existing:
        return {"skipped": "already journaled today",
                "as_of": str(today)}
    raise RuntimeError(
        "morning-regime produced no snapshot — check worker logs for "
        "'morning: canonical engine failed'")


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


async def _j_fed_path():
    """Fed path — hike/hold/cut odds for the next FOMC + 3-6m lean.
    Market baseline (^IRX pricing) + bounded econ-pressure shift,
    journaled to fed_predictions for meta grading. Market-only when
    FRED is missing — confidence drops, never invents."""
    from app.signals import fed_path
    res = await asyncio.to_thread(fed_path.run)
    return {"p_hold": res["next_fomc"]["p_hold"],
            "lean_3_6m": res["path_3_6m"]["lean"],
            "confidence": res["data_quality"]["confidence"]}


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


async def _j_agentic_infra():
    """Agentic infrastructure engine — scores the software
    picks-and-shovels layer for agentic AI (data plane, streaming,
    edge, gateways, NHI, agent security, observability)."""
    from app.signals import agentic_infra
    return await asyncio.to_thread(agentic_infra.refresh)


async def _j_calendar_audit():
    """Weekly calendar audit — diffs the next 45d of macro events and
    the tracked universe's earnings dates vs last week; refreshes
    stale dates; journals every move into calendar_audit."""
    from app.market_events.audit import run
    return await asyncio.to_thread(run)


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
    """Expectation-gap / flywheel scores for tracked symbols — ordered
    stalest-first so a timeout mid-run rotates coverage instead of
    starving a fixed tail (alphabetical order under the 50m cap is how
    AVGO's row fossilized at its June print)."""
    from app.signals.expectation_gap import refresh_flywheel
    syms = await _tracked_symbols()
    try:
        rows = await asyncio.to_thread(
            db.execute_query,
            "SELECT x.symbol FROM unnest(string_to_array(:s,','))"
            " WITH ORDINALITY AS x(symbol, ord)"
            " LEFT JOIN symbol_flywheel f ON f.symbol = x.symbol"
            " ORDER BY f.updated_at ASC NULLS FIRST, x.ord",
            {"s": ",".join(syms)})
        syms = [r["symbol"] for r in rows] or syms
    except Exception:
        pass
    return await refresh_flywheel(syms, concurrency=8)


async def _j_fwd_eps_repair():
    """Audit every stored fwd_eps_avg vs reported TTM + snapshot-year
    checks, recompute suspects through the guarded flywheel path, and
    re-resolve FV where the estimate moved >10% — the earnings-driven
    FV legs were priced on the same wrong basis."""
    from app.signals import expectation_gap
    return await expectation_gap.repair_fwd_eps(
        await _tracked_symbols())


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
    return await asyncio.to_thread(theme_rotation.current)


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
    # bounded fan-out — ~3k symbols × 8 dtypes serially was the
    # timeout; 6 workers respects FMP rate budgets, cuts wall ~6x
    sem = asyncio.Semaphore(6)

    async def _one(sym: str):
        nonlocal ok, failed
        async with sem:
            try:
                res = await asyncio.to_thread(
                    mgr.refresh_data, sym, dtypes,
                    RefreshMode.SCHEDULED, False)
                if res.total_successful > 0:
                    ok += 1
                else:
                    failed += 1
            except Exception as exc:
                failed += 1
                errs.append(f"{sym}: {exc}")

    await asyncio.gather(*(_one(s) for s in symbols))
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


async def _j_sec_facts() -> dict:
    """SEC XBRL fundamentals — RPO/backlog, goodwill, acquisition
    cash, and share-count split detection (the NOW 5:1 that poisoned
    eps_ttm gets caught at the source). Free EDGAR data, ~4 req/s
    self-throttled, sequential over the tracked universe."""
    from app.signals import sec_fundamentals
    symbols = await _tracked_symbols()
    return await asyncio.to_thread(sec_fundamentals.run, symbols)


async def _j_sec_filings() -> dict:
    """8-K earnings-release extraction — item 2.02 press releases
    through doc_extract: verbatim-quote validation, guidance →
    thesis_watches, channels → tailwinds journal. Deduped on
    accession; each release is analyzed exactly once."""
    from app.signals import earnings_release
    symbols = await _tracked_symbols()
    return await asyncio.to_thread(earnings_release.run, symbols)


async def _j_weekly_review() -> dict:
    """Weekly 5-question review — what changed / funding / earnings
    outlook / market recognition / action, journaled per symbol so
    each verdict is gradable. Deterministic; events between Sundays
    trigger the same review via alert/SEC hooks."""
    from app.signals import event_review
    symbols = await _tracked_symbols()
    return await asyncio.to_thread(event_review.run_universe, symbols)


async def _j_thesis_check() -> dict:
    """Archetype thesis tracker — evaluates each pilot symbol's
    standing hypotheses (what must improve for upside) against
    flywheel/SEC/doc evidence, persists symbol_thesis, and syncs the
    checks into thesis_watches for grading. Deterministic."""
    from app.signals import thesis_health
    return await asyncio.to_thread(thesis_health.run)


async def _j_sector_rotation() -> dict:
    """Sector rotation early warning — leadership deterioration legs
    (pairwise RS, tracked-subset breadth, distribution, destination
    leadership) journaled daily per watched leader. Flow-confirmation
    states unreachable until a real flow source exists."""
    from app.signals import sector_rotation_ew
    return await asyncio.to_thread(sector_rotation_ew.run)


async def _j_journal_grades() -> dict:
    """Journal grading — forward returns after every journaled
    signal (recovery states, thesis transitions, crypto stance,
    selloff classes, insider clusters) -> journal_kind_stats.
    The substrate→feedback bridge; descriptive, not prescriptive."""
    from app.signals import journal_grades
    return await asyncio.to_thread(journal_grades.run)


async def _j_crypto_positioning() -> dict:
    """Crypto positioning — stablecoin supply, futures OI, ETF flows,
    BTC trend/leadership. Banded votes journaled daily; feeds the
    x-asset macro read."""
    from app.signals import crypto_positioning
    return await asyncio.to_thread(crypto_positioning.run)


async def _j_recovery_watch() -> dict:
    """Recovery verdicts — Phase-1 read-only composition: reconciles
    regime/selloff/tape/intraday/permissions/fundamental snapshots
    into one journaled state per pilot symbol. Advises, never acts."""
    from app.signals import recovery_verdict
    return await asyncio.to_thread(recovery_verdict.run)


async def _j_insider_flow() -> dict:
    """Insider flow — open-market insider buys/sells over book +
    watchlist. Journals every Form-4-style filing; clusters (≥2
    distinct buyers / ≥3 sellers in 90d) emit 'insider' alerts that
    feed the same NEGATIVE/HIGH gate daily_calls already enforces."""
    from app.signals import insider_flow
    return await asyncio.to_thread(insider_flow.run)


async def _j_selloff() -> dict:
    """Selloff Opportunity Engine — detects market dislocation, scores
    fallen-but-sound names (price dislocation vs business integrity),
    classifies the drop, journals candidates for forward grading.
    Deterministic; advisory staged-entry plans only."""
    from app.signals import selloff
    return await asyncio.to_thread(selloff.scan)


async def _j_tier_sync() -> dict:
    """Coverage-tier sync — recomputes symbol_tiers (active = books ∪
    watchlist ∪ members ∪ futureStocks; monthly = data-covered or
    post-earnings; registry = the rest). Then runs the discovery scan
    over the monthly tier and promotes trigger hits into the
    futureStocks book — which makes them active everywhere."""
    from app.signals import symbol_tiers
    def _go():
        tiers = symbol_tiers.sync()
        disc = symbol_tiers.discovery_scan()
        return {"tiers": tiers, "discovery": disc}
    return await asyncio.to_thread(_go)


async def _j_read_through() -> dict:
    """Extended-hours basket repricing — detects when a theme book
    moves together post-close/pre-open (peer earnings, guidance,
    sector commentary). Journals read_through_evals for the morning
    regime. Run ~16:30 ET and ~08:30 ET."""
    from app.signals import read_through
    return await asyncio.to_thread(read_through.scan)


async def _j_earnings_watch() -> dict:
    """Earnings-day watcher — active-tier names printing today. When
    actuals land: captures the print, runs the 8-K through doc_extract,
    re-scores the thesis (before→after = improving/deteriorating), and
    fires an alert carrying the analysis. Idempotent per print; schedule
    every 30 min 16:00-20:00 ET."""
    from app.signals import earnings_watch
    return await asyncio.to_thread(earnings_watch.poll)


async def _j_research() -> dict:
    """AI-tailwind research engine — deterministic evidence → versioned
    scores → skeptical review → recommendation, journaled PIT to
    research_runs. Same-day runs are skipped (event-triggered, not
    every-tick): rerun happens on next day's tick or a manual POST."""
    from app.research import run as research_run
    from app.research import sectors
    from app.database import db
    todo = []
    seen = set()
    n_syms = 0
    fresh = {r["symbol"] for r in db.execute_query(
        "SELECT symbol FROM research_runs WHERE as_of=CURRENT_DATE")}
    for sector, syms in sectors.all_universes().items():
        n_syms += len(syms)
        for s in syms:
            if s not in fresh and s not in seen:
                seen.add(s)
                todo.append((s, sector))
    # FDCE-only names (PLTR, NOW, SYM…) — not in any sector universe;
    # run() routes their sector and layers the domain eval on top
    from app.research import fdce
    for s in fdce.universe():
        if s not in fresh and s not in seen:
            seen.add(s)
            n_syms += 1
            todo.append((s, sectors.sector_for_symbol(s)))
    done, errs = [], []
    # bounded fan-out — the book is a few hundred names; serial was
    # the 25m-timeout failure mode. 6 workers keeps provider/LLM
    # rate budgets intact while cutting wall time ~6x.
    sem = asyncio.Semaphore(6)

    async def _one(s: str, sector: str):
        async with sem:
            try:
                await asyncio.to_thread(research_run.run, s, sector)
                done.append(s)
            except Exception as exc:
                errs.append(f"{s}: {str(exc)[:80]}")

    await asyncio.gather(*(_one(s, sec) for s, sec in todo))
    return {"ran": len(done), "skipped_fresh": n_syms - len(todo),
            "errors": errs[:10], "symbols": done}


async def _j_liquidity() -> dict:
    """Liquidity & new-money flow monitor — Fed BS/TGA/RRP/reserves +
    credit conditions + equity-transmission proxies → 0-100 impulse
    score journaled to liquidity_snapshots. Answers 'is liquidity
    becoming more supportive AND is it reaching stocks' — informs
    aggressiveness, never picks names."""
    from app.signals import liquidity_engine, liquidity_forward
    st = await asyncio.to_thread(liquidity_engine.run)
    try:
        fwd = await asyncio.to_thread(liquidity_forward.run)
        st["forward"] = {"posture_hint": fwd.get("posture_hint"),
                         "h8": ((fwd.get("horizons") or {})
                                .get("8w") or {})
                         .get("projected_liquidity_score")}
    except Exception:
        pass                                # forward is additive —
    return st                               # never fails the live job


async def _j_market_stability() -> dict:
    """Market stability — are buyers actually returning TODAY? QQQ/
    SMH VWAP persistence, VIX, breadth, AI leadership, credit tone,
    session persistence → raw fields journaled at fixed marks."""
    from app.signals import market_stability
    return await asyncio.to_thread(market_stability.run)


async def _j_metals() -> dict:
    """Metals Pulse — shared macro metals regime (real yields/DXY/
    liquidity/credit/growth) + per-metal fundamental & fear scores →
    accumulate/watch/wait/reduce, journaled to metals_snapshots.
    Fear-entry engine: discounts are the window, intact structural
    demand is the thesis. Stage-1 price/FRED legs only; supply-
    demand legs (COT, inventories, flows) flagged stage-2, not faked."""
    from app.metals import engine as metals_engine
    st = await asyncio.to_thread(metals_engine.run)
    return {"macro": st.get("macro", {}).get("label"),
            "verdicts": {k: v.get("verdict")
                         for k, v in (st.get("metals") or {}).items()}}


async def _j_themes() -> dict:
    """Theme Intelligence — 12m scenario probs × per-theme
    sensitivity + 6-factor opportunity score (macro/earnings/
    valuation/demand/momentum/resilience) + capped index weights.
    Journals theme_intelligence_snapshots + theme_index_membership.
    Weekly — ranks themes for capital, never picks names."""
    from app.themes import engine as themes_engine
    st = await asyncio.to_thread(themes_engine.run)
    return {"probs": st.get("scenario_probs"),
            "verdicts": {k: v.get("verdict")
                         for k, v in (st.get("themes") or {}).items()}}


async def _j_short_data() -> dict:
    """Massive short-data pull → short_interest / short_volume /
    share_float. Staleness-aware and rate-budgeted — the shared key
    is ~5 req/min. Runs every night; a partial run is success."""
    from app.signals import short_data
    return await asyncio.to_thread(short_data.refresh)


async def _j_short_squeeze() -> dict:
    """Short-squeeze eval — squeeze_fuel + covering_probability per
    symbol with short data, journaled for forward grading. Flags
    covering rallies (fade risk), new shorts pressing, and
    squeeze setups. Deterministic; advisory."""
    from app.signals import short_squeeze
    r = await asyncio.to_thread(short_squeeze.scan)
    return {"count": r["count"],
            "verdicts": {v: sum(1 for e in r["evals"]
                              if e["verdict"] == v)
                         for v in ("likely_covering",
                                   "new_shorts_pressing",
                                   "squeeze_setup")}}


async def _j_intraday_regime() -> dict:
    """Hourly intraday regime overlay — timestamped baseline × tape
    read for the regime page; does not overwrite the daily journal."""
    from app.market_regime.intraday import snapshot
    return await asyncio.to_thread(snapshot)


async def _j_intraday() -> dict:
    """Intraday tape eval — 15-min journaled state during RTH
    (VWAP/breadth/VIX/leadership/macro). Off-hours it no-ops; the
    /intraday endpoint lazy-evals too, so the tape stays fresh
    whenever anyone is looking. Next-day grading of prior evals."""
    from app.signals import intraday_pulse as ip
    graded = await asyncio.to_thread(ip.grade)
    if not ip.market_open_now():
        return {"skipped": "market closed", **graded}
    return await asyncio.to_thread(ip.evaluate)


async def _j_premarket() -> dict:
    """Pre-market snapshot — equity gap vs prior close (SPY/QQQ/SMH
    extended-hours) + crypto 24h change. Fires every 30 min from
    4:00 ET — hourly versioned slots (h04..h08, final) so the gap's
    firm/fade drift is journaled per hour into the open."""
    from app.signals import premarket
    return await asyncio.to_thread(premarket.snapshot)


async def _j_tape_purge() -> dict:
    """Weekly session-tape retention — intermediate marks older than
    7d drop; the day-spine (premarket/open/close/afterhours) persists
    as the graded-prediction record."""
    from app.signals import market_stability
    return await asyncio.to_thread(market_stability.purge)


async def _j_intraday_recovery() -> dict:
    """5-min recovery-confirmation engine — fetch session bars for the
    AI-infra watch scope, evaluate VWAP/RS/RVOL/OR/breadth on the
    latest completed bar, journal one eval per (symbol, bar_ts).
    Off-hours the fetch still lands but evals journal only RTH bars."""
    from app.signals import intraday_recovery
    return await asyncio.to_thread(intraday_recovery.run)


async def _j_ai_cycle() -> dict:
    """AI cycle rotation tracker — quarterly per-name composite over
    journaled evidence: 8 component legs, three-peak detection,
    demand-peak windows, policy decisions. Weekly job."""
    from app.signals import cycle_tracker
    return await asyncio.to_thread(cycle_tracker.refresh)


async def _j_demand_evidence() -> dict:
    """Demand-evidence feed — deterministic capex + FCF claims per
    ingest group auto-approved; news extraction lands as drafts for
    review. Feeds market_ai_regime + the cycle ladder's evidence leg.
    Was dormant: run before expecting regime/rotation to grade."""
    from app.fair_value_v2.demand_ingest import (
        ingest_group, ingest_groups)
    out: dict = {}
    for g in sorted(ingest_groups()):
        try:
            r = await asyncio.to_thread(
                ingest_group, g, True, False)
            out[g] = {"approved": r.get("approved_claims"),
                      "drafts": r.get("draft_claims")}
        except Exception as exc:
            out[g] = {"error": str(exc)}
    return out


async def _j_ai_cycle_ladder() -> dict:
    """AI-cycle theme ladder — per-stage rungs (build → deploy →
    utilize) with tape/growth/evidence/funding legs + rotation_state,
    journaled daily to ai_cycle_ladder_daily."""
    from app.signals import inference_ladder
    out = await asyncio.to_thread(inference_ladder.run)
    return {"as_of": out.get("as_of"),
            "regime": (out.get("regime") or {}).get("regime"),
            "rungs": len(out.get("rungs") or {})}


async def _j_competitive_risk() -> dict:
    """Competitive disruption & substitution — seeds threat claims,
    then scores CRS per name over the approved-claims journal."""
    from app.signals import competitive_risk
    seeded = await asyncio.to_thread(competitive_risk.seed_threats)
    res = await asyncio.to_thread(competitive_risk.refresh)
    return {**res, **seeded}


async def _j_correction_alarms() -> dict:
    """Correction alarms — revision breadth (flywheel), labor/credit
    + real yields (keyless FRED CSV), valuation decomposition.
    Answers 'dip or regime break?' — informs, never overrides
    posture."""
    from app.signals import correction_alarms as ca
    r = await asyncio.to_thread(ca.evaluate)
    return {"character": r["correction_character"],
            "severity": r["severity"]}


async def _j_priced_in() -> dict:
    """Growth priced-in — required CAGR / expectation gap / compression
    drag / bear-base-bull bands journaled per symbol with a fresh FV
    run. Composition over journaled runs; never re-runs the methods."""
    from app.valuation import growth_priced_in as gpi
    return await asyncio.to_thread(gpi.run)


async def _j_valuation_decision() -> dict:
    """Valuation decision — quality × priced-in matrix + thesis
    integrity + entry/trim/exit bands. Chained after priced-in:
    reads its journaled rows, advisory decisions, alerts on
    compression + expectation expansion."""
    from app.valuation import decision as vd
    return await asyncio.to_thread(vd.run)


async def _j_narrative_claims() -> dict:
    """Narrative claims collector — gathers provenance-typed claims
    from journaled engine outputs (guidance, quality flags, driver
    commitments, revision swings) into the claims ledger."""
    from app.signals import narrative_ledger as nl
    return await asyncio.to_thread(nl.run)


async def _j_driver_bridge() -> dict:
    """Driver bridge — seeds driver_assumptions from journaled
    evidence (commitments, measured inputs) and collapses them to
    driver_forecasts the priced-in layer consumes as an input leg."""
    from app.valuation import driver_bridge as dbx
    return await asyncio.to_thread(dbx.run_all)


async def _j_index_valuation() -> dict:
    """Index valuation — SPY/QQQ trailing P/E + tracked-universe fwd
    P/E + earnings-yield/10Y spread, journaled daily. The market-level
    'is the tape expensive' read."""
    from app.signals import index_valuation
    return await asyncio.to_thread(index_valuation.run)


async def _j_nowflation() -> dict:
    """Nowflation daily — journals the CPI gauge/realtime read and
    the pre-registered print forecast; fills the fed-path inflation
    leg and enriches CPI catalysts with an expected value."""
    from app.signals import nowflation
    return await asyncio.to_thread(nowflation.run)


async def _j_posture_eval() -> dict:
    """Posture eval + outcome grading. Backfills evals over all
    journaled regime snapshots (dedup is first-write-per-day), then
    grades matured evals against forward QQQ returns — the journal
    IS the backtest."""
    from app.signals import posture
    try:                          # reconstruct credit history once —
        from app.signals import credit_health  # old snapshots then
        from app.database import db as _db     # grade credit-aware
        have = (_db.execute_query(
            "SELECT count(*) AS n FROM credit_health_snapshots")
            or [{}])[0]
        if (have.get("n") or 0) < 200:
            credit_health.backfill()
    except Exception:
        pass
    backfilled = posture.backfill()
    graded = posture.grade()
    cur = posture.current()
    return {"evals": backfilled, "graded": graded,
            "today": cur.get("posture"), "rule": cur.get("matched")}


async def _j_fv_sweep() -> dict:
    """Weekly fair-value sweep over the tracked universe — refetches
    the fundamentals bundle for any symbol whose last quarterly print
    is newer than its stored fmp_fundamentals snapshot (eps_forward
    stays post-print), then resolves FV. Unchanged inputs reuse."""
    from app.signals import fv_sweep
    symbols = await _tracked_symbols()
    return await asyncio.to_thread(fv_sweep.run, symbols)


async def _j_universe_fill() -> dict:
    """Universe snapshot — chunked rollup refresh (stalest-first);
    every rule job reads this row instead of per-symbol compute."""
    from app.signals.universe_fill import fill
    return await asyncio.to_thread(fill)


async def _j_sector_timing() -> dict:
    """Sector timing — daily two-score state machine per sector."""
    from app.signals.sector_timing import run
    return await asyncio.to_thread(run)


async def _j_fragility() -> dict:
    """Systematic selling early warning — leverage/positioning
    fragility + heuristic trigger probabilities, journaled daily."""
    from app.market_regime.fragility import run
    return await asyncio.to_thread(run)


async def _j_resilience() -> dict:
    """Weekly resilience scorecards — health/AI/tape + validation
    flags, journaled and diffed into alerts. Book names only —
    positions + holdings + watchlist, not the 3k universe."""
    from app.database import db
    from app.signals.resilience_engine import run
    syms = [r["symbol"] for r in db.execute_query(
        "SELECT symbol FROM book_symbols")]
    return await asyncio.to_thread(run, syms)


async def _j_live_bars() -> dict:
    """15-min live-price overlay — one batched fetch lands in
    symbol_live_ticks; every downstream read stitches from it."""
    from app.database import db
    from app.signals.live_overlay import refresh
    syms = [r["symbol"] for r in db.execute_query(
        "SELECT symbol FROM book_symbols")]
    return await asyncio.to_thread(refresh, syms)


async def _j_earnings_today() -> dict:
    """Intraday extraction — book symbols reporting TODAY (plus
    yesterday's BMO prints still landing). Fetches the fresh 8-K,
    extracts claims, then re-scores guidance immediately so the
    badge appears within the hour, not overnight."""
    from app.database import db
    from app.signals import earnings_release
    from app.signals import guidance_intel
    # skip symbols whose earnings filing already landed in
    # sec_filings_processed — the 45-min cadence is for WAITING
    # on filings, not re-touching done ones
    syms = [r["symbol"] for r in db.execute_query(
        "SELECT DISTINCT ew.symbol FROM earnings_watch ew"
        " JOIN book_symbols b ON b.symbol = ew.symbol"
        " WHERE ew.earnings_date >= CURRENT_DATE - 1"
        "   AND ew.earnings_date <= CURRENT_DATE + 1"
        "   AND NOT EXISTS (SELECT 1 FROM sec_filings_processed p"
        "                   WHERE p.symbol = ew.symbol"
        "                     AND p.filed >= ew.earnings_date - 1)")]
    if not syms:
        return {"symbols_reporting": 0}
    rel = await asyncio.to_thread(earnings_release.run, syms, 3)
    # only re-score guidance when something actually extracted —
    # an all-done cycle costs nothing downstream
    gui = (await asyncio.to_thread(guidance_intel.run, syms)
           if rel.get("analyzed") else {"skipped": "no new filings"})
    return {"symbols_reporting": len(syms), "extract": rel,
            "guidance": gui}


async def _j_guidance() -> dict:
    """Nightly guidance intel — normalize doc_analyses guidance
    claims, score outlook + quality. Book symbols only."""
    from app.database import db
    from app.signals.guidance_intel import run
    syms = [r["symbol"] for r in db.execute_query(
        "SELECT symbol FROM book_symbols")]
    return await asyncio.to_thread(run, syms)


async def _j_earnings_quality() -> dict:
    """Nightly forensic screen — accruals/DSO/inventory/FCF
    conversion/goodwill from XBRL. Slow, book-only."""
    from app.database import db
    from app.signals.earnings_quality import run
    syms = [r["symbol"] for r in db.execute_query(
        "SELECT symbol FROM book_symbols")]
    return await asyncio.to_thread(run, syms)


async def _j_flow() -> dict:
    """Nightly flow footprint — EOD institutional signature per
    book symbol (zvol + CLV streaks, journaled to symbol_flow)."""
    from app.database import db
    from app.signals.flow_footprint import run
    syms = [r["symbol"] for r in db.execute_query(
        "SELECT symbol FROM book_symbols")]
    return await asyncio.to_thread(run, syms)


async def _j_resilience_validate() -> dict:
    """Nightly fact-check pass — XBRL cross-validation, slow OK.
    Book names only."""
    from app.database import db
    from app.signals.resilience_engine import run
    syms = [r["symbol"] for r in db.execute_query(
        "SELECT symbol FROM book_symbols")]
    return await asyncio.to_thread(run, syms, True)


async def _j_best_picks() -> dict:
    """Best-picks eval — the three-lane declarative selection
    (best_picks.yaml): growth_swing / long_term / compounder_3_5y
    over the active tier. Bulk-loads ctx once, pure-dict eval, every
    candidate journaled to best_picks_evals (gated names too).
    Advisory — ranked shortlists, never orders."""
    from app.signals import best_picks
    r = await asyncio.to_thread(best_picks.run)
    return {"evaluated": r["evaluated"],
            "sections": {k: v["counts"]
                         for k, v in r["sections"].items()}}


async def _j_lev_swings() -> dict:
    """3x semis swing detector — SOXS fade-the-extension and SOXL
    confirmed-rebound over the stored index tape (SMH proxy). Runs
    after momentum so today's bars are in; journals both verdicts to
    lev_etf_evals for grading. Advisory levels only — never orders."""
    from app.signals import leveraged_swings
    r = await asyncio.to_thread(leveraged_swings.evaluate)
    return {etf: row["state"] for etf, row in r["etfs"].items()}


async def _j_signal_evals() -> dict:
    """Signal contract evals — the regression net for the decision
    layer (spec lint / scenarios / invariants, all offline). A red
    run means engine contract drift — dead imports, unknown `when`
    fields, gate semantics that changed — before it ships to the
    board. Failures land as warnings; custodian watches the log."""
    from app.signals import signal_evals
    res = await asyncio.to_thread(signal_evals.run)
    if not res["ok"]:
        logger.error("signal-evals: %d/%d checks FAILED — %s",
                     len(res["failed"]), res["total"],
                     [f["id"] for f in res["failed"]])
    return {"ok": res["ok"], "passed": res["passed"],
            "total": res["total"], "failed": res["failed"]}


JOBS: dict[str, tuple[str, Callable]] = {
    "momentum":      ("Momentum flags", _j_momentum),
    "swing-scan":    ("Swing screener", _j_swing_scan),
    "alerts":        ("Catalyst alerts", _j_alerts),
    "insider-flow":  ("Insider buy/sell flow", _j_insider_flow),
    "crypto-positioning": ("Crypto positioning", _j_crypto_positioning),
    "journal-grades": ("Journal signal grading", _j_journal_grades),
    "sector-rotation": ("Sector rotation EW", _j_sector_rotation),
    "recovery-watch":("Recovery verdicts (pilot)", _j_recovery_watch),
    "after-hours":   ("Extended-hours movers", _j_after_hours),
    "pt-watch":      ("Analyst PT watch", _j_pt_watch),
    "outcomes":      ("Alert outcomes", _j_outcomes),
    "rule-breakers": ("Rule Breaker eval", _j_rule_breakers),
    "smallcap":      ("5x Scout eval (full pass)", _j_smallcap),
    "smallcap-eval": ("5x Scout — member eval", _j_smallcap_eval),
    "smallcap-discovery": ("5x Scout — discovery sweep",
                           _j_smallcap_discovery),
    "smallcap-tail": ("5x Scout — tail refresh", _j_smallcap_tail),
    "leaps-mark":    ("LEAPS book marks", _j_leaps_mark),
    "regime":        ("Market regime card", _j_regime),
    "flywheel":      ("Expectation gap", _j_flywheel),
    "fwd-eps-repair": ("Forward-EPS audit + repair",
                       _j_fwd_eps_repair),
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
    "fed-path":     ("Fed path — rate probabilities", _j_fed_path),
    "econ-cal-verify": ("Macro calendar verification",
                        _j_econ_cal_verify),
    "calendar-audit": ("Weekly calendar audit", _j_calendar_audit),
    "agentic-infra":  ("Agentic infrastructure engine",
                       _j_agentic_infra),
    "econ-cal-poll":  ("Due-print watcher (hourly)",
                       _j_econ_cal_poll),
    "etf-flows":    ("ETF AUM → fund flows", _j_etf_flows),
    "strategy":     ("Portfolio strategy snapshot", _j_strategy),
    "hidden-gems":  ("Hidden gems scanner", _j_hidden_gems),
    "fund-journal": ("Quarterly fundamentals journal", _j_fund_journal),
    "hedge-universe": ("LEAP-put hedge journal", _j_hedge_universe),
    "conviction":   ("Conviction List", _j_conviction),
    "themes-pulse": ("Theme Intelligence — opportunity + indices",
                     _j_themes),
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
    "sec-facts":    ("SEC XBRL fundamentals",
                     _j_sec_facts),
    "sec-filings":  ("8-K earnings-release extraction",
                     _j_sec_filings),
    "weekly-review": ("Weekly 5-question review",
                      _j_weekly_review),
    "thesis-check": ("Archetype thesis tracker", _j_thesis_check),
    "tier-sync": ("Coverage tiers + discovery", _j_tier_sync),
    "read-through": ("Extended-hours repricing", _j_read_through),
    "earnings-watch": ("Earnings-day watcher", _j_earnings_watch),
    "research":     ("AI-tailwind research engine", _j_research),
    "selloff":     ("Selloff opportunity engine", _j_selloff),
    "short-data":  ("Short interest/volume pull", _j_short_data),
    "short-squeeze": ("Squeeze + covering eval", _j_short_squeeze),
    "premarket-tape": ("Pre-market gap + crypto snapshot",
                       _j_premarket),
    "tape-purge":   ("Session tape retention (weekly)", _j_tape_purge),
    "intraday-tape": ("Intraday tape classifier", _j_intraday),
    "intraday-regime": ("Intraday regime overlay",
                        _j_intraday_regime),
    "intraday-recovery": ("Intraday recovery confirm (5-min)",
                          _j_intraday_recovery),
    "ai-cycle":    ("AI cycle rotation tracker (weekly)", _j_ai_cycle),
    "demand-evidence": ("Demand-evidence feed (capex/FCF + news drafts)",
                        _j_demand_evidence),
    "ai-cycle-ladder": ("AI cycle theme ladder (daily)",
                        _j_ai_cycle_ladder),
    "competitive-risk": ("Competitive disruption & substitution",
                         _j_competitive_risk),
    "correction-alarms": ("Correction-alarm engine",
                          _j_correction_alarms),
    "priced-in":   ("Growth priced-in — required CAGR / gap / drag",
                    _j_priced_in),
    "valuation-decision": ("Valuation decision bands — enter/trim/exit",
                           _j_valuation_decision),
    "narrative-claims": ("Narrative claims ledger", _j_narrative_claims),
    "driver-bridge":   ("Driver → forecast bridge", _j_driver_bridge),
    "nowflation":     ("Nowflation daily inflation gauge", _j_nowflation),
    "index-valuation": ("Index valuation daily", _j_index_valuation),
    "liquidity":   ("Liquidity & new-money flow", _j_liquidity),
    "market-stability": ("Market stability — buyers returning?",
                         _j_market_stability),
    "metals-pulse": ("Metals Pulse — regime + opportunity", _j_metals),
    "fv-sweep":    ("Weekly fair-value sweep", _j_fv_sweep),
    "universe-fill": ("Universe snapshot chunked fill",
                      _j_universe_fill),
    "sector-timing": ("Sector bottom/rebound scores",
                      _j_sector_timing),
    "fragility":    ("Systematic selling early warning",
                      _j_fragility),
    "resilience":   ("Company resilience scorecards",
                      _j_resilience),
    "resilience-validate": ("Resilience fact-check (XBRL)",
                      _j_resilience_validate),
    "flow":         ("Institutional flow footprint", _j_flow),
    "earnings-quality": ("Forensic earnings-quality screen",
                      _j_earnings_quality),
    "guidance":     ("Guidance intelligence", _j_guidance),
    "earnings-today": ("Same-day earnings extraction",
                       _j_earnings_today),
    "live-bars":    ("Live price overlay", _j_live_bars),
    "best-picks":  ("Best picks — 3-lane selection", _j_best_picks),
    "lev-etf-swings": ("3x semis swing detector", _j_lev_swings),
    "signal-evals": ("Signal contract evals", _j_signal_evals),
}

# order matters for 'all': posture first, then signals, then evals
# (evals already tail-refresh momentum+flywheel — harmless overlap)
_ALL_ORDER = ["regime", "tier-sync", "momentum",
              "fred-macro", "fed-path", "morning-regime",
              "fragility", "flow", "earnings-quality", "earnings-today",
              "live-bars",
              "guidance",
              "resilience",
              "resilience-validate",
              "econ-cal-verify",
              "etf-flows",
              "strategy", "event-day",
              "flywheel", "fund-flags", "alerts",
              "after-hours", "pt-watch",
              "fwd-flags",
              "focus-scan",
              "swing-scan", "rule-breakers",
              "smallcap-eval", "smallcap-discovery", "smallcap-tail",
              "hidden-gems",
              "fund-journal", "hedge-universe", "tailwinds", "conviction",
              "theme-review", "daily-sheet", "outcomes",
              "leaps-mark", "priors", "pilot", "daily-calls",
              "daily-puts", "spec-incubator", "meta",
              "sec-facts", "short-data", "short-squeeze",
              "correction-alarms", "selloff", "best-picks",
              "priced-in", "valuation-decision", "narrative-claims",
              "driver-bridge",
              "lev-etf-swings", "signal-evals", "custodian"]


_JOB_TIMEOUT = {
    "priors": 20 * 60, "rule-breakers": 15 * 60, "smallcap": 15 * 60,
    "smallcap-eval": 12 * 60, "smallcap-discovery": 12 * 60,
    "smallcap-tail": 25 * 60,
    "swing-scan": 15 * 60, "alerts": 15 * 60, "focus-scan": 10 * 60,
    "after-hours": 8 * 60, "pt-watch": 8 * 60,
    "custodian": 10 * 60, "momentum": 8 * 60, "flywheel": 50 * 60,
    "fwd-eps-repair": 15 * 60,
    "universe-fill": 10 * 60,
    "sector-timing": 5 * 60,
    "fragility":    5 * 60,
    "macro-snapshot": 3 * 60, "fund-snapshots": 120 * 60,
    "fund-flags": 8 * 60, "outcomes": 8 * 60, "leaps-mark": 5 * 60,
    "regime": 5 * 60, "pilot": 8 * 60, "daily-calls": 5 * 60,
    "daily-puts": 5 * 60, "spec-incubator": 3 * 60,
    "meta": 5 * 60, "event-day": 3 * 60, "morning-regime": 4 * 60,
    "etf-flows": 2 * 60, "strategy": 5 * 60, "hidden-gems": 5 * 60,
    "fred-macro": 3 * 60, "econ-cal-verify": 2 * 60,
    "econ-cal-poll": 2 * 60, "fv-backtest": 20 * 60,
    "fund-journal": 60 * 60, "hedge-universe": 15 * 60,
    "sec-facts": 20 * 60, "sec-filings": 20 * 60,
    "weekly-review": 15 * 60,
    "thesis-check": 40 * 60, "tier-sync": 5 * 60,
    "read-through": 8 * 60, "earnings-watch": 8 * 60,
    "research": 90 * 60,
    "selloff": 5 * 60,
    "short-data": 75 * 60, "short-squeeze": 8 * 60,
    "intraday-tape": 3 * 60, "intraday-regime": 3 * 60,
    "correction-alarms": 3 * 60, "priced-in": 5 * 60,
    "valuation-decision": 5 * 60, "narrative-claims": 10 * 60,
    "driver-bridge": 10 * 60, "nowflation": 2 * 60,
    "best-picks": 5 * 60,
    "lev-etf-swings": 2 * 60,
    "signal-evals": 3 * 60,
    "conviction": 8 * 60, "theme-review": 10 * 60,
    "tailwinds": 15 * 60, "tailwind-review": 15 * 60,
    "theme-rotation": 5 * 60,
    "daily-sheet": 15 * 60,
    "mover-quality": 10 * 60,
    "posture-eval": 5 * 60,
    "index-valuation": 2 * 60,
}


async def _run_job(name: str):
    label, fn = JOBS[name]
    # run_id — minted here, journaled into job_runs, and stamped on the
    # JOB_START/END/FAIL log markers so an external watchdog can
    # correlate ledger rows with log lines end to end.
    run_id = uuid.uuid4().hex[:12]
    logger.info("JOB_START job=%s run=%s", name, run_id)
    _mark(name, run_id=run_id, running=True)
    t0 = time.monotonic()
    try:
        res = await asyncio.wait_for(
            fn(), timeout=_JOB_TIMEOUT.get(name, 10 * 60))
        dur = round(time.monotonic() - t0, 1)
        _mark(name, running=False, result=res)
        logger.info("JOB_END job=%s run=%s ok=true duration_s=%.1f",
                    name, run_id, dur)
    except asyncio.TimeoutError:
        logger.error("JOB_FAIL job=%s run=%s error=timeout",
                     name, run_id)
        _mark(name, running=False,
              error=f"timed out after "
                    f"{_JOB_TIMEOUT.get(name, 600) // 60}m")
    except Exception as exc:
        logger.error("job %s failed: %s", name, exc, exc_info=True)
        # last_error is what the catalog/admin page shows — carry the
        # crash site (file:line) not just the message, or every job
        # failure needs a server log dig to even locate
        tb = traceback.extract_tb(exc.__traceback__)
        site = f" [{tb[-1].filename.split('/')[-1]}:{tb[-1].lineno}]" \
            if tb else ""
        logger.error("JOB_FAIL job=%s run=%s error=%.300r site=%s",
                     name, run_id, exc, site.strip())
        _mark(name, running=False, error=f"{exc}{site}")


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
        return await asyncio.to_thread(theme_rotation.current)
    return await asyncio.to_thread(theme_rotation.compute_board)


# ---------------- brain — vitals, inputs, evolution, intake ----------

def _try(fn, default=None):
    """Vitals must never 500 on a missing table — prod may lag the
    migration tree. Each panel degrades to its default."""
    try:
        return fn()
    except Exception:
        return default if default is not None else {}


@router.get("/brain")
async def brain_vitals():
    """Admin view of the intelligence layer — three questions:

    how big is it     themes by stage, claims by status, edges,
                      forecasts, docs, evidence rows
    what did it eat   today's inputs: jobs that ran, claims emitted,
                      docs analyzed, evidence observed, intake items
    how is it moving  recent promotions, claim transitions, forecast
                      grades, intake verdicts
    """
    from app.database import db

    vitals = {}
    vitals["themes"] = _try(lambda: {
        "by_stage": {r["stage"]: r["n"] for r in db.execute_query(
            "SELECT stage, count(*) n FROM theme_registry"
            " WHERE status='active' GROUP BY stage")},
        "candidates": sum(r["n"] for r in db.execute_query(
            "SELECT count(*) n FROM theme_registry"
            " WHERE status='candidate'")),
        "retired": sum(r["n"] for r in db.execute_query(
            "SELECT count(*) n FROM theme_registry"
            " WHERE status='retired'"))})
    vitals["claims"] = _try(lambda: {
        "by_status": {r["status"]: r["n"] for r in db.execute_query(
            "SELECT status, count(*) n FROM narrative_claims"
            " WHERE version=1 GROUP BY status")},
        "total": sum(r["n"] for r in db.execute_query(
            "SELECT count(*) n FROM narrative_claims"
            " WHERE version=1"))})
    vitals["edges"] = _try(lambda: sum(r["n"] for r in db.execute_query(
        "SELECT count(*) n FROM supplier_relationships")))
    vitals["forecasts"] = _try(lambda: {
        "driver_forecasts": sum(r["n"] for r in db.execute_query(
            "SELECT count(*) n FROM driver_forecasts")),
        "graded_kinds": sum(r["n"] for r in db.execute_query(
            "SELECT count(DISTINCT kind) n FROM journal_kind_stats")),
        "reliable": sum(r["n"] for r in db.execute_query(
            "SELECT count(*) n FROM journal_kind_stats"
            " WHERE reliable"))})
    vitals["docs"] = _try(lambda: {
        "analyzed": sum(r["n"] for r in db.execute_query(
            "SELECT count(*) n FROM doc_analyses")),
        "watches_open": sum(r["n"] for r in db.execute_query(
            "SELECT count(*) n FROM thesis_watches"
            " WHERE status='open'"))})
    vitals["evidence"] = _try(lambda: sum(r["n"] for r in db.execute_query(
        "SELECT count(*) n FROM demand_evidence")))
    vitals["intake"] = _try(lambda: {
        r["status"]: r["n"] for r in db.execute_query(
            "SELECT status, count(*) n FROM brain_intake"
            " GROUP BY status")})

    today = {}
    today["jobs"] = _try(lambda: [dict(r) for r in db.execute_query(
        "SELECT name, ran_at, duration_s, error FROM job_runs"
        " WHERE ran_at::date = current_date"
        " ORDER BY ran_at")], [])
    today["claims_emitted"] = _try(lambda: sum(r["n"] for r in
        db.execute_query(
            "SELECT count(*) n FROM narrative_claims"
            " WHERE as_of = current_date")), 0)
    today["docs_analyzed"] = _try(lambda: sum(r["n"] for r in
        db.execute_query(
            "SELECT count(*) n FROM doc_analyses"
            " WHERE created_at::date = current_date")), 0)
    today["evidence_rows"] = _try(lambda: sum(r["n"] for r in
        db.execute_query(
            "SELECT count(*) n FROM demand_evidence"
            " WHERE created_at::date = current_date")), 0)
    today["intake"] = _try(lambda: sum(r["n"] for r in
        db.execute_query(
            "SELECT count(*) n FROM brain_intake"
            " WHERE submitted_at::date = current_date")), 0)

    evolution = {}
    evolution["promotions"] = _try(lambda: [dict(r) for r in
        db.execute_query(
            "SELECT theme_key, name, stage, promoted_at"
            " FROM theme_registry WHERE promoted_at IS NOT NULL"
            " AND promoted_at >= current_date - 30"
            " ORDER BY promoted_at DESC")], [])
    evolution["claim_moves"] = _try(lambda: [dict(r) for r in
        db.execute_query(
            "SELECT claim_id, review_kind, verdict, created_at"
            " FROM claim_reviews"
            " WHERE created_at >= now() - interval '7 days'"
            " ORDER BY created_at DESC LIMIT 20")], [])
    evolution["intake_verdicts"] = _try(lambda: [dict(r) for r in
        db.execute_query(
            "SELECT id, title, status, submitted_at FROM brain_intake"
            " ORDER BY submitted_at DESC LIMIT 10")], [])
    evolution["restaged"] = _try(lambda: [dict(r) for r in
        db.execute_query(
            "SELECT theme_key, name, stage, last_review"
            " FROM theme_registry WHERE status='active'"
            " AND last_review >= current_date - 30"
            " ORDER BY last_review DESC")], [])

    return {"vitals": vitals, "today": today, "evolution": evolution}


@router.get("/brain/intake")
async def brain_intake_queue(limit: int = 25):
    """The intake queue — admin submissions with accept/partial/
    rejected verdicts and the canonical why behind each."""
    from app.brain import intake
    return {"queue": await asyncio.to_thread(intake.list_recent, limit)}


@router.post("/brain/intake")
async def brain_intake_submit(body: dict):
    """Feed the brain — admin submits a doc/news/URL. It runs the
    same extraction pipeline as every other source (verbatim-quote
    grounding, deterministic validation) and journals the verdict:
    accepted / partial / rejected, always with why."""
    from app.brain import intake
    symbols = body.get("symbols") or []
    if isinstance(symbols, str):
        symbols = [s.strip() for s in symbols.split(",") if s.strip()]
    enq = await asyncio.to_thread(
        intake.submit, body.get("text") or "", body.get("url") or "",
        body.get("title") or "", symbols,
        body.get("by") or "admin", body.get("kind") or "doc")
    if enq.get("deduped"):
        return enq
    return await asyncio.to_thread(
        intake.process, enq["id"], body.get("text") or "",
        body.get("url") or "", body.get("title") or "", symbols)


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
        # Layer-B slowing severity — cause/demand context the
        # classifier journaled in fundamental_detail; the raw
        # fund_state label stays canonical
        "decel_cause": row.get("decel_cause"),
        "demand_health": row.get("demand_health"),
        "rev_growth": row.get("rev_growth"),
        "eps_growth": row.get("eps_growth"),
        "gm_slope": row.get("gm_slope"),
        "est_revision_pct": row.get("est_revision_pct"),
        "beat_streak": row.get("beat_streak"),
        # earnings-trajectory fact — direction of the last-3 journaled
        # earnings_watch verdicts; 'insufficient' when unwatched, so
        # the add gate only blocks on MEASURED deterioration
        "earn_traj": row.get("earn_traj"),
        # balance-sheet vulnerability (axis 2) — flywheel leverage +
        # cash generation; banded sector-aware in stage 0
        "net_debt_ebitda": row.get("net_debt_ebitda"),
        "debt_to_equity": row.get("debt_to_equity"),
        "fcf_ttm": row.get("fcf_ttm"),
        "fcf_margin": row.get("fcf_margin"),
        # market credit (axis 1) — same block for every row on the
        # board; the caller injects it once per request
        "credit_state": row.get("credit_state"),
        "credit_confidence": row.get("credit_confidence"),
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
        SECTOR_NAMES, THEME_ETFS, _flow_tag, _momentum_score)
    etfs = list(SECTOR_NAMES) + list(THEME_ETFS) + ["SPY"]
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


def _earn_quarters(syms: list[str]) -> dict:
    """Last-3 journaled prints per symbol — earnings_data backbone
    (surprise %, eps est/actual, revenue) + the earnings_watch verdict
    overlay where the watcher covered the print. Display evidence,
    not a score: the columns show what the last 3 quarters DID."""
    if not syms:
        return {}
    from app.database import db
    out: dict[str, list] = {}
    try:
        for r in db.execute_query("""
            SELECT ed.stock_symbol AS symbol, ed.earnings_date AS d,
                   ed.surprise_percentage AS surp,
                   ed.eps_estimate, ed.eps_actual,
                   ew.verdict
            FROM (SELECT stock_symbol, earnings_date,
                         surprise_percentage, eps_estimate, eps_actual,
                         row_number() OVER (
                             PARTITION BY stock_symbol
                             ORDER BY earnings_date DESC) rn
                  FROM earnings_data
                  WHERE stock_symbol = ANY(:syms)
                    AND earnings_date <= CURRENT_DATE
                    AND (eps_actual IS NOT NULL
                         OR surprise_percentage IS NOT NULL)) ed
            LEFT JOIN earnings_watch ew
              ON ew.symbol = ed.stock_symbol
             AND ew.earnings_date = ed.earnings_date
            WHERE ed.rn <= 3
            ORDER BY ed.stock_symbol, ed.earnings_date DESC""",
                {"syms": list(syms)}):
            out.setdefault(r["symbol"], []).append({
                "d": str(r["d"]),
                "surp": round(float(r["surp"]), 1)
                        if r["surp"] is not None else None,
                "verdict": r.get("verdict")})
    except Exception:
        logger.info("pulse: earn quarters lookup failed",
                    exc_info=True)
    return out


def _earn_traj(quarters: list[dict]) -> str:
    """Direction of the last-3 journaled verdicts — improving |
    deteriorating | mixed | insufficient. 'insufficient' is an
    explicit value, never null: the add gate must see MEASURED
    deterioration to act, and absent coverage must not invent one.
    Majority of verdicted prints decides; ties are mixed."""
    vs = [q["verdict"] for q in quarters
          if q.get("verdict") in ("improving", "deteriorating")]
    if not vs:
        return "insufficient"
    imp, det = vs.count("improving"), vs.count("deteriorating")
    if det > imp:
        return "deteriorating"
    if imp > det:
        return "improving"
    return "mixed"


def _eq_flags(syms: list[str]) -> dict:
    """Latest earnings-quality row per symbol — quality score + flags
    (cash_gen_deteriorating, channel_stuffing_risk…)."""
    if not syms:
        return {}
    from app.database import db
    out = {}
    try:
        for r in db.execute_query(
            "SELECT DISTINCT ON (symbol) symbol, quality, flags"
            " FROM symbol_earnings_quality WHERE symbol = ANY(:syms)"
            " ORDER BY symbol, as_of DESC",
                {"syms": list(syms)}):
            out[r["symbol"]] = {"quality": r.get("quality"),
                                "flags": r.get("flags") or []}
    except Exception:
        logger.info("pulse: earnings-quality lookup failed",
                    exc_info=True)
    return out


@router.get("/portfolio-pulse")
async def portfolio_pulse(portfolio_id: str = None):
    """One-row-per-holding board: tape state + transition, fundamental
    state, FV gap, GQ percentile, and a deterministic action hint.
    This is the 'what needs attention today' surface. Scoped to one
    book when portfolio_id is passed; else the aggregated 'book'."""
    from app.database import db
    import uuid as _uuid
    pid = None
    if portfolio_id:
        try:
            pid = str(_uuid.UUID(str(portfolio_id)))
        except (ValueError, AttributeError):
            return {"rows": [], "book": {},
                    "error": "invalid portfolio_id"}
    try:
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
              AND pp.portfolio_id::text
                  = COALESCE(:pid, pp.portfolio_id::text)
            GROUP BY s.symbol
            UNION ALL
            SELECT h.symbol, h.shares_held, h.average_cost,
                   p.name, h.status
            FROM portfolio_holdings h
            JOIN portfolios p ON p.id = h.portfolio_id
            WHERE h.status IN ('active','inactive')
              AND h.portfolio_id::text
                  = COALESCE(:pid, h.portfolio_id::text)
              AND NOT EXISTS (
                  SELECT 1 FROM portfolio_positions pp
                  JOIN stocks s2 ON s2.id = pp.stock_id
                  WHERE s2.symbol = h.symbol AND pp.quantity > 0
                    AND pp.portfolio_id::text = h.portfolio_id::text)
        )
        SELECT u.symbol, u.qty, u.cost, u.status, u.portfolio,
               px.close, ppx.close AS prev_close, spark.closes AS spark,
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
               fw.rev_growth, fw.eps_growth, fw.gm_slope,
               fw.est_revision_pct, fw.beat_streak,
               fw.net_debt_ebitda, fw.debt_to_equity,
               fw.fcf_ttm, fw.fcf_margin,
               s.fundamental_detail->>'decel_cause' AS decel_cause,
               s.fundamental_detail->>'demand_health' AS demand_health,
               prev.state AS prev_state
        FROM uni u
        LEFT JOIN stocks s ON s.symbol = u.symbol
        LEFT JOIN fmp_company_profiles fp ON fp.symbol = u.symbol
        LEFT JOIN LATERAL (
            SELECT close FROM daily_bars b
            WHERE b.symbol = u.symbol
            ORDER BY b.date DESC LIMIT 1) px ON true
        LEFT JOIN LATERAL (
            SELECT close FROM daily_bars b
            WHERE b.symbol = u.symbol
            ORDER BY b.date DESC LIMIT 1 OFFSET 1) ppx ON true
        LEFT JOIN LATERAL (
            SELECT json_agg(c ORDER BY d ASC) AS closes FROM (
                SELECT close AS c, date AS d FROM daily_bars b
                WHERE b.symbol = u.symbol
                ORDER BY b.date DESC LIMIT 30) t) spark ON true
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
        ORDER BY u.status, u.symbol""", {"pid": pid})
    except Exception as e:
        logger.exception("portfolio-pulse: universe query failed")
        return {"rows": [], "book": {},
                "error": f"{type(e).__name__}: {e}"}
    try:
        out = []
        from app.market_regime.rotation import _SECTOR_TO_ETF
        etf_ctx = _sector_flow_map()
        from app.signals.spec_pulse import spec_symbols
        spec_set = spec_symbols()
        # market-credit axis — one block per board, journaled read;
        # missing journal → None → stage0 'unknown', never 'healthy'
        try:
            from app.signals import credit_health as _ch
            _cr = _ch.latest() or _ch.snapshot() or {}
        except Exception:
            _cr = {}
        _cr_state, _cr_conf = (_cr.get("credit_state"),
                               _cr.get("confidence"))
        _syms = [r["symbol"] for r in rows]
        _qmap = _earn_quarters(_syms)
        _eqmap = _eq_flags(_syms)
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
            ppx = r.get("prev_close")
            day_chg = (float(px) / float(ppx) - 1) * 100 \
                if px and ppx else None
            fv_ev = r.get("expected_fair_value")
            fv_up = (float(fv_ev) / float(px) - 1) * 100 \
                if fv_ev and px else None
            det = r.get("momentum_detail") or {}
            spark_v = r.get("spark")
            if isinstance(det, str) or isinstance(spark_v, str):
                import json as _j
                if isinstance(det, str):
                    det = _j.loads(det)
                if isinstance(spark_v, str):
                    spark_v = _j.loads(spark_v)
            _qs = _qmap.get(sym) or []
            _traj = _earn_traj(_qs)
            _eq = _eqmap.get(sym) or {}
            ev = _pulse_action_eval(
                {**r, "mom_state": r.get("momentum_state"),
                 "prev_state": r.get("prev_state"),
                 "fund_state": r.get("fundamental_state"),
                 "fv_upside": fv_up,
                 "earn_traj": _traj,
                 "credit_state": _cr_state,
                 "credit_confidence": _cr_conf}, det)
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
                "prev_close": (float(ppx) if ppx is not None else None),
                "day_chg_pct": (round(day_chg, 2)
                                if day_chg is not None else None),
                "spark": spark_v,
                "mom_state": r.get("momentum_state"),
                "mom_prev": r.get("prev_state"),
                "rsi": round(det["rsi"], 1) if det.get("rsi") else None,
                "vs_sma50": det.get("vs_sma50"),
                "dd52w": det.get("dd52w"),
                "dip_phase": det.get("dip_phase"),
                "spring": (det.get("spring") or {}).get("score")
                          if isinstance(det.get("spring"), dict) else None,
                "stoch_w_up": ((det.get("stoch") or {}).get("w") or {})
                              .get("up"),
                "stoch_w_zone": ((det.get("stoch") or {}).get("w") or {})
                                .get("zone"),
                "stoch_d_cross": ((det.get("stoch") or {}).get("d") or {})
                                 .get("cross"),
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
                "next_earnings_date": (
                    str(r["next_earnings_date"])
                    if r.get("next_earnings_date") else None),
                "action": act, "bucket": bucket, "why": why,
                "action_label": ev.get("label"),
                "action_confidence": ev.get("confidence"),
                "matched_rule": ev.get("matched_rule"),
                # last-3 journaled prints + trajectory — evidence the
                # columns render; traj already fed the eval above
                "quarters": _qs, "earn_traj": _traj,
                "eq_quality": _eq.get("quality"),
                "eq_flags": _eq.get("flags"),
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
        day_pnl = sum(
            r["shares"] * (float(r["price"]) - float(r["prev_close"]))
            for r in pos if r["price"] and r["prev_close"])
        prev_val = val - day_pnl
        book = {"positions": len(pos),
                "cost": round(cost), "value": round(val),
                "pnl": round(pnl),
                "pnl_pct": round(pnl / priced_cost * 100, 1)
                           if priced_cost else None,
                "day_pnl": round(day_pnl),
                "day_chg_pct": round(day_pnl / prev_val * 100, 2)
                               if prev_val else None,
                "unpriced_cost": round(cost - priced_cost),
                "target_pct": tgt * 100,
                "pace_month": round(((1 + tgt) ** (1 / 12) - 1) * 100, 2),
                "pace_week": round(((1 + tgt) ** (1 / 52) - 1) * 100, 2),
                "target_value_12m": round(cost * (1 + tgt)),
                "goal_month": round(cost * ((1 + tgt) ** (1 / 12) - 1))}
        # daily book snapshot — first write wins; the pace series.
        # Scoped calls journal under that book's id, so user books get
        # their own track record too.
        _BOOK_ID = "00000000-0000-0000-0000-00000000000b"
        snap_pid = pid or _BOOK_ID
        try:
            db.execute_update(
                "INSERT INTO portfolio_snapshots (portfolio_id,"
                " snapshot_date, total_value, invested_value, cash_balance)"
                " VALUES (:pid, CURRENT_DATE, :v, :c, 0)"
                " ON CONFLICT (portfolio_id, snapshot_date) DO UPDATE SET"
                " total_value=EXCLUDED.total_value,"
                " invested_value=EXCLUDED.invested_value",
                {"pid": snap_pid, "v": val, "c": cost})
            base = db.execute_query(
                "SELECT snapshot_date, total_value FROM portfolio_snapshots"
                " WHERE portfolio_id::text = CAST(:pid AS text)"
                " ORDER BY snapshot_date LIMIT 1",
                {"pid": snap_pid})
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
    except Exception as e:
        logger.exception("portfolio-pulse: processing failed")
        return {"rows": out, "book": {},
                "error": f"{type(e).__name__}: {e}"}


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


@router.post("/research/{sym}")
async def research_one(sym: str):
    """Run the research engine for one symbol — same path as the
    'research' job and POST /admin/research/{sym}; this route exists
    so the admin-proxied UI button can reach it."""
    from app.research import run as research_run
    return {"report": await asyncio.to_thread(
        research_run.run, sym.upper())}


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
        try:                       # second-leg risk — blocks adds
            import json as _j
            from app.database import db as _db
            fr = _db.execute_query(
                "SELECT signals FROM fragility_daily"
                " ORDER BY as_of DESC LIMIT 1")
            if fr:
                sig = fr[0].get("signals")
                sig = _j.loads(sig) if isinstance(sig, str)                     else (sig or {})
                sl = sig.get("second_leg_down") or {}
                if sl.get("risk"):
                    d["second_leg"] = {"risk": sl["risk"],
                                       "block": sl.get(
                                           "block_additional_tranches")}
        except Exception:
            pass
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


@router.get("/symbol/{sym}/fv-resolve")
async def fv_resolve(sym: str, force: bool = False):
    """Resolve FV for one symbol — reuse-friendly by default;
    force=true skips the reuse check and recomputes under the
    current code. The escape hatch for 'engine changed, old cache'
    (a code update doesn't advance the inputs watermark, so cached
    runs would otherwise serve until max-age)."""
    from app.fair_value_v2.resolver import FairValueV2Resolver
    res, meta = await asyncio.to_thread(
        FairValueV2Resolver().resolve, sym.upper(), force)
    return {
        "symbol": sym.upper(),
        "forced": force,
        "reused": meta.get("reused"),
        "reason": meta.get("reason"),
        "run_as_of": meta.get("run_as_of"),
        "fair_value": res.fair_value,
        "expected_fair_value": res.expected_fair_value,
        "scenarios": res.scenario_fair_values,
        "method_results": [
            {"key": m.method_key, "fv": m.fair_price,
             "status": str(m.status),
             "role": (m.metrics or {}).get("role"),
             "demoted": (m.metrics or {}).get("eligibility_demoted")}
            for m in (res.method_results or [])],
        "classification": res.classification,
        "quality_flags": res.quality_flags,
    }


@router.get("/theme/{key}/composition")
async def theme_composition(key: str):
    """Cross-sectional member comparison inside a theme — fwd P/E,
    PEG, FY+2 growth, backlog, FCF, lifecycle stage, FV upside,
    confidence — ranked deterministically. 'Which two of these 8 do
    I add' as data, not narrative."""
    from app.signals.theme_composition import composition
    return await asyncio.to_thread(composition, key)


@router.get("/sector-timing")
async def sector_timing():
    """Per-sector bottom-opportunity vs rebound-confirmation scores
    + state (selloff/capitulation/potential_bottom/bottom_forming/
    rebound_confirmed). 'Cheap' and 'recovering' stay separate."""
    from app.signals.sector_timing import current
    return await asyncio.to_thread(current)


@router.get("/guidance/{symbol}")
async def guidance_one(symbol: str):
    """Latest guidance card — normalized claims + outlook/quality."""
    import asyncio
    from app.signals.guidance_intel import latest
    card = await asyncio.to_thread(latest, symbol.upper())
    if card is None:
        from app.signals.guidance_intel import compute
        card = await asyncio.to_thread(compute, symbol.upper())
    return card


@router.get("/guidance")
async def guidance_all():
    """Latest outlook/quality per book symbol — calendar badges."""
    import asyncio
    from app.database import db
    rows = await asyncio.to_thread(
        db.execute_query,
        "SELECT DISTINCT ON (symbol) symbol, outlook, quality"
        " FROM symbol_guidance ORDER BY symbol, as_of DESC")
    return {"items": rows}


@router.get("/resilience")
async def resilience_all():
    """Latest resilience scorecard per symbol — the screener read."""
    import asyncio
    from app.signals import resilience_engine as re_mod
    return {"items": await asyncio.to_thread(re_mod.read_all)}


@router.get("/resilience/{symbol}")
async def resilience_one(symbol: str):
    """Full score card for one symbol — scores + checks + flags."""
    import asyncio
    from app.signals import resilience_engine as re_mod
    card = await asyncio.to_thread(re_mod.read, symbol.upper())
    if card is None:
        # lazy compute so first deploy doesn't wait for the weekly job
        card = await asyncio.to_thread(re_mod.compute, symbol.upper())
    return card


@router.get("/fragility")
async def fragility_report():
    """Systematic selling early warning — how much leverage/fragility
    sits under the tape: vulnerability 0-100 (six legs, per-leg
    observed|estimated|missing status) + heuristic 1/3/5/10d trigger
    probabilities. Fragile ≠ bearish — a bullish tape can be loaded."""
    from app.market_regime.fragility import current
    return await asyncio.to_thread(current)


@router.get("/universe-snapshot/stats")
async def universe_snapshot_stats():
    """How fresh is the shared base-data layer — total, filled,
    stale, and oldest rows in universe_snapshot."""
    rows = await asyncio.to_thread(db.execute_query,
        "SELECT count(*) total,"
        " count(*) FILTER (WHERE u.snapshot_as_of IS NOT NULL) filled,"
        " count(*) FILTER (WHERE u.snapshot_as_of"
        "   > now() - interval '1 day') fresh,"
        " max(u.snapshot_as_of) newest,"
        " min(u.snapshot_as_of) oldest"
        " FROM stocks s LEFT JOIN universe_snapshot u"
        " ON u.symbol = s.symbol")
    return rows[0] if rows else {}


@router.get("/symbol/{sym}/health")
async def symbol_health(sym: str):
    """The per-stock health card — fundamental state + tape state +
    growth/quality + conviction/gem/hedge reads + future themes,
    synthesized into a verdict that names conflicts (strong
    fundamentals + broken tape = 'watch, don't catch the knife')."""
    from app.signals.stock_health import card
    out = await asyncio.to_thread(card, sym.upper())
    # self-heal: the card serves stored runs, so when one is stale
    # (age/model drift) kick a background recompute — the next view
    # is fresh. Stale INPUTS or an extreme_gap flag need the deeper
    # heal (refetch the provider bundle, then re-resolve) — a plain
    # recompute reproduces the same broken blend with a fresh stamp.
    fv = out.get("fv") or {}
    needs_input_refresh = False
    try:
        from datetime import date as _d
        wm = str(fv.get("inputs_as_of") or "")[:10]
        if wm and (_d.today() - _d.fromisoformat(wm)).days > 45:
            needs_input_refresh = True
    except Exception:
        pass
    if "extreme_gap" in (fv.get("flags") or []):
        needs_input_refresh = True
    if needs_input_refresh:
        # every page view would otherwise trigger a ~6-call provider
        # bundle fetch — one heal attempt per symbol per hour per
        # process; a failed fetch then can't hammer the rate limit
        import time
        now = time.time()
        if now - _fv_heal_last.get(sym.upper(), 0) < 3600:
            needs_input_refresh = False
        else:
            _fv_heal_last[sym.upper()] = now
    if fv.get("stale") or needs_input_refresh:
        async def _fv_bg() -> None:
            try:
                if needs_input_refresh:
                    from app.signals import fv_sweep
                    await asyncio.to_thread(
                        fv_sweep.refresh_after_print, sym.upper())
                else:
                    from app.fair_value_v2.resolver import (
                        FairValueV2Resolver)
                    await asyncio.to_thread(
                        FairValueV2Resolver().resolve, sym.upper())
            except Exception:
                pass
        asyncio.create_task(_fv_bg())
    return out


@router.get("/symbol/{sym}/thesis-history")
async def symbol_thesis_history(sym: str, days: int = 180, limit: int = 50):
    """The thesis timeline — every journaled coverage_start /
    status_transition / leg_change for a symbol, newest first, with
    the evidence snapshot that produced each change. Flat days are
    absent by design: the timeline is changes, not a heartbeat."""
    from app.database import db
    rows = await asyncio.to_thread(
        db.execute_query,
        "SELECT id, symbol, as_of::text, event_kind, archetype,"
        " prev_status, status, status_dir, score, hyp_changes,"
        " veto_fired, evidence, drivers, fv_delta_pct, priced_in,"
        " alert_id::text, detail, created_at::text"
        " FROM thesis_change_events WHERE symbol=:s"
        " AND as_of >= CURRENT_DATE - (:d * INTERVAL '1 day')"
        " ORDER BY as_of DESC, id DESC LIMIT :n",
        {"s": sym.upper(), "d": days, "n": limit})
    return {"symbol": sym.upper(), "events": rows}


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


@router.get("/sector-rotation/{etf}")
async def sector_rotation_read(etf: str, days: int = 30):
    """Latest + history of the rotation early-warning journal for a
    sector ETF — state, renormalized risk score, destination
    leaderboard, per-leg detail, flow status."""
    from app.signals import sector_rotation_ew
    rows = sector_rotation_ew.read(etf.upper(), days)
    return {"sector": etf.upper(),
            "latest": rows[0] if rows else None, "history": rows}


@router.get("/sector-rotation/{etf}/replay")
async def sector_rotation_replay(etf: str, start: str, end: str):
    """Point-in-time replay of the EW legs over a window — the
    June-2026 acceptance test as an API surface. Reads only bars
    <= each as_of, so no forward leakage is possible."""
    from datetime import date
    from app.signals import sector_rotation_ew
    rows = sector_rotation_ew.replay(
        etf.upper(), date.fromisoformat(start),
        date.fromisoformat(end))
    return {"sector": etf.upper(), "start": start, "end": end,
            "days": len(rows), "rows": rows}


@router.get("/symbol/{sym}/priced-in")
async def symbol_priced_in(sym: str, days: int = 90):
    """Growth priced-in — the inverse read over the latest FV run:
    required CAGR under our exit multiple, forecast-vs-required gap,
    compression drag, bear/base/bull bands, 0-100 priced-in score."""
    from app.valuation import growth_priced_in as gpi
    rows = await asyncio.to_thread(gpi.read, sym, days)
    if not rows:                       # thin journal — compose live
        latest = await asyncio.to_thread(gpi.evaluate, sym)
        return {"symbol": sym.upper(), "latest": latest, "history": []}
    return {"symbol": sym.upper(), "latest": rows[0], "history": rows}


@router.get("/symbol/{sym}/valuation-decision")
async def symbol_valuation_decision(sym: str, days: int = 90):
    """Valuation decision — quality × priced-in matrix, thesis
    integrity, entry/trim/exit bands. Advisory, journaled daily."""
    from app.valuation import decision as vd
    rows = await asyncio.to_thread(vd.read, sym, days)
    if not rows:
        latest = await asyncio.to_thread(vd.evaluate, sym)
        return {"symbol": sym.upper(), "latest": latest, "history": []}
    return {"symbol": sym.upper(), "latest": rows[0], "history": rows}


@router.get("/symbol/{sym}/narrative-claims")
async def symbol_narrative_claims(sym: str, history: bool = False):
    """What the market believes — provenance-typed claims (guidance,
    estimates, facts, hypotheses) with evidentiary status. Claims are
    collected from journaled engine outputs; LLM hypotheses never
    self-promote."""
    from app.signals import narrative_ledger as nl
    rows = await asyncio.to_thread(nl.read, sym, history)
    if not rows:
        await asyncio.to_thread(nl.collect, sym)
        rows = await asyncio.to_thread(nl.read, sym, history)
    return {"symbol": sym.upper(), "claims": rows}


@router.get("/symbol/{sym}/expectations-report")
async def symbol_expectations_report(sym: str):
    """The five answers, composed from journaled rows — what the
    market believes, evidence-backed drivers, priced-in, FV bands,
    and what would change the conclusion. None where a leg is
    missing — never fabricated."""
    from app.signals import narrative_ledger as nl
    from app.valuation import growth_priced_in as gpi
    from app.valuation import driver_bridge as dbx
    from app.database import db
    s = sym.upper()
    pi = (await asyncio.to_thread(gpi.read, s, 1) or [])
    pi = pi[0] if pi else {}
    claims = await asyncio.to_thread(nl.read, s)
    dec = db.execute_query(
        "SELECT * FROM valuation_decisions WHERE symbol=:s"
        " ORDER BY as_of DESC LIMIT 1", {"s": s})
    dec = dec[0] if dec else {}
    df = await asyncio.to_thread(dbx.latest, s)
    commits = db.execute_query(
        "SELECT metric, period, value, delta_dir, status"
        " FROM driver_commitments WHERE symbol=:s"
        " AND status='open' ORDER BY created_at DESC LIMIT 6",
        {"s": s})
    live = [c for c in claims if c.get("status") != "expired"]
    report = {
        "symbol": s, "as_of": str(pi.get("as_of") or
                                 dec.get("as_of") or ""),
        "market_believes": {
            "claims": [{"claim": c["claim"], "type": c["claim_type"],
                        "status": c["status"],
                        "direction": c["direction"],
                        "source": c.get("source"),
                        "source_date": str(c.get("source_date") or "")}
                       for c in live],
            "priced_in_score": pi.get("score"),
            "required_cagr": pi.get("required_cagr"),
            "implied_growth": pi.get("implied_growth"),
            "implied_status": pi.get("implied_status"),
            "sentiment_timing": dec.get("timing"),
        },
        "growth_drivers": {
            "forecast": (df or {}).get("forecast"),
            "provenance": (df or {}).get("provenance"),
            "coverage": (df or {}).get("coverage"),
            "missing_inputs": (df or {}).get("missing_inputs"),
        },
        "priced_in": {
            "forecast_cagr": pi.get("forecast_cagr"),
            "forecast_src": pi.get("forecast_src"),
            "required_cagr": pi.get("required_cagr"),
            "expectation_gap": pi.get("expectation_gap"),
            "compression_drag": pi.get("compression_drag"),
            "score": pi.get("score"),
        },
        "fair_value": {
            "price": pi.get("price"),
            "bear": pi.get("fv_bear"), "base": pi.get("fv_base"),
            "bull": pi.get("fv_bull"),
            "dispersion": pi.get("valuation_dispersion"),
            "margin_of_safety": pi.get("margin_of_safety"),
            "driver_forecast": pi.get("driver_forecast"),
        },
        "what_would_change": {
            "thesis_integrity": dec.get("thesis_integrity"),
            "integrity_evidence": dec.get("integrity_evidence"),
            "contradicted": [{"claim": c["claim"],
                              "status": c["status"]}
                             for c in claims
                             if c.get("status") == "contradicted"],
            "open_commitments": commits,
            "decision": dec.get("decision"),
            "quadrant": dec.get("quadrant"),
        },
    }
    return report


@router.get("/journal-grades")
async def journal_grades_read(kind: Optional[str] = None):
    """The substrate→feedback scoreboard — forward returns after
    each journaled signal bucket (5/10/20d). reliable=n>=20."""
    from app.signals import journal_grades
    return {"stats": journal_grades.read(kind)}


@router.get("/symbol/{sym}/recovery-verdict")
async def symbol_recovery_verdict(sym: str):
    """Latest recovery verdict + 30d of journaled history — the
    composition layer's answer: state, advisory decision, gates,
    conflicts, required confirmation, invalidation."""
    from app.database import db
    s = sym.upper()
    try:
        rows = db.execute_query(
            "SELECT symbol, as_of, engine_version, state, prev_state,"
            " state_changed, transition_reason, event_type, market,"
            " stock, recovery, decision, decision_confidence, gates,"
            " conflicts, required_confirmation,"
            " invalidation_conditions, evidence_refs, missing_inputs"
            " FROM recovery_verdicts WHERE symbol=:s"
            " ORDER BY as_of DESC, id DESC LIMIT 30", {"s": s})
    except Exception:
        rows = []
    return {"symbol": s, "latest": rows[0] if rows else None,
            "history": rows}


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


@router.post("/symbol/{sym}/fv-refresh")
async def symbol_fv_refresh(sym: str):
    """Full one-symbol FV refresh: refetch the FMP fundamentals bundle
    (eps_forward, estimates, TTM actuals) then re-resolve — the
    post-print path on demand. The plain recompute only re-prices on
    stored inputs; this fixes stale/missing inputs too."""
    from app.signals import fv_sweep
    return await asyncio.to_thread(fv_sweep.refresh_after_print, sym.upper())


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


@router.get("/calendar-audit")
async def calendar_audit_latest():
    """Last weekly audit's change rows — what moved in the macro
    calendar and tracked earnings dates since the previous run."""
    from app.market_events import audit
    return await asyncio.to_thread(audit.latest)


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
    from app.market_regime import intraday as intraday_regime
    from app.database import db
    today = await asyncio.to_thread(
        lambda: db.execute_query(
            "SELECT as_of, regime, ai_regime, score, confidence, "
            "buckets, llm, verdict, horizon_1m, horizon_3m "
            "FROM morning_regime_snapshots "
            "ORDER BY as_of DESC LIMIT 1"))
    t = today[0] if today else None
    if t is not None:
        # fed block rides the snapshot's structural lane, but the
        # snapshot is once-a-day — live-merge the latest journal row
        # so a fresh fed_predictions write shows today, not tomorrow
        try:
            import json as _j
            from app.signals import (
                fed_path, liquidity_engine, liquidity_forward,
                market_stability)
            fed = await asyncio.to_thread(fed_path.read)
            liq = await asyncio.to_thread(liquidity_engine.read)
            liq_fwd = await asyncio.to_thread(liquidity_forward.read)
            stab = await asyncio.to_thread(market_stability.read)
            if fed or liq or liq_fwd or stab:
                b = t.get("buckets")
                if isinstance(b, str):
                    b = _j.loads(b)
                if isinstance(b, dict):
                    st = b.get("structural")
                    if not isinstance(st, dict):
                        st = {}
                    if fed:
                        st["fed"] = fed
                    if liq:
                        st["liquidity"] = liq
                    if liq_fwd:
                        st["liquidity_forward"] = liq_fwd
                    if stab:
                        st["market_stability"] = stab
                    # synthesis — the reviewer's three-question frame
                    # kept separate: financial liquidity (4-12w
                    # terrain) vs market stability (buyers back
                    # today). Non-override BOTH ways: intraday
                    # strength can't paper over a severe liquidity
                    # warning; a poor 8w outlook can't veto a genuine
                    # stabilization.
                    if liq or liq_fwd or stab:
                        fin = (liq.get("band")
                               if liq else None) or "unknown"
                        stab_lbl = ((stab or {}).get("stability_label")
                                    or "insufficient_evidence")
                        credit = ((liq or {}).get("sub_scores") or {}) \
                            .get("credit_stress")
                        fwd_hint = (liq_fwd or {}).get("posture_hint")
                        severe = (fin == "severe"
                                  or (isinstance(credit, (int, float))
                                      and credit < 25))
                        stab_pos = stab_lbl in ("stable",
                                                "stabilizing")
                        if severe:
                            regime = "severe_warning"
                        elif fwd_hint == "defensive" and not stab_pos:
                            regime = "defensive"
                        elif stab_pos and (fwd_hint
                                           in ("supportive",
                                               "neutral", "caution",
                                               None)):
                            regime = "recovery_attempt"
                        elif fwd_hint == "caution":
                            regime = "caution"
                        else:
                            regime = fin
                        st["market_synthesis"] = {
                            "financial_liquidity": fin,
                            "forward_hint_8w": fwd_hint,
                            "market_stability": stab_lbl,
                            "regime": regime,
                            "posture_hint":
                                ("capital preservation" if severe else
                                 "demand confirmation" if regime
                                 in ("defensive", "caution") else
                                 "tactical entries permitted, sized"
                                 if regime == "recovery_attempt" else
                                 "selective"),
                            "calibration": {"mode": "shadow",
                                            "decision_weight": 0}}
                    b["structural"] = st
                    t["buckets"] = b
        except Exception:
            pass
    intraday = await asyncio.to_thread(intraday_regime.latest)
    try:
        from app.market_regime import fragility as frag
        fragility = await asyncio.to_thread(frag.latest)
    except Exception:
        fragility = None
    try:
        from app.market_regime import movement as mv
        movement = await asyncio.to_thread(mv.movement)
    except Exception:
        movement = None
    try:
        from app.signals import index_valuation
        valuation = await asyncio.to_thread(index_valuation.latest)
    except Exception:
        valuation = None
    try:
        # posture = environment stance x selloff character x fed
        # lean — the "build cash vs buy the dip" synthesis
        from app.signals import correction_alarms as ca, equity_posture
        alarms = await asyncio.to_thread(ca.latest)
        fed_blk = (((t.get("buckets") if isinstance(t, dict) else None)
                    or {}).get("structural") or {}).get("fed")
        posture = equity_posture.compose(
            stance=(valuation or {}).get("stance"),
            alarms=alarms, fed=fed_blk)
    except Exception:
        posture = None
    try:
        from app.signals import rates_outlook
        wti = (((((t.get("buckets") if isinstance(t, dict) else None)
                  or {}).get("macro") or {}).get("detail") or {})
               .get("wti"))
        rates = await asyncio.to_thread(rates_outlook.compose, wti=wti)
    except Exception:
        rates = None
    try:
        # direction — the heading: weighted vote of the three
        # journaled verdicts + live tape + alarm severity
        from app.signals import equity_posture as _ep
        direction = _ep.compose_direction(
            valuation=valuation, posture=posture,
            alarms=alarms, intraday=intraday,
            rates=rates)
    except Exception:
        direction = None
    try:
        # horizon ladder — the same evidence at three scales;
        # journaled once/day so each horizon grades on its own clock
        from app.signals import equity_posture as _epo
        from app.signals import correction_alarms as _ca2
        _alarms = await asyncio.to_thread(_ca2.latest)
        _fed = (((t.get("buckets") if isinstance(t, dict) else None)
                 or {}).get("structural") or {}).get("fed")
        outlook = _epo.compose_outlook(
            intraday=intraday, fragility=fragility,
            valuation=valuation, rates=rates,
            alarms=_alarms,
            regime=(t or {}).get("regime"), fed=_fed)
        if outlook:
            try:
                from app.database import db as _odb
                import json as _json
                _odb.execute_update(
                    "INSERT INTO outlook_daily (date, horizons)"
                    " VALUES (CURRENT_DATE, :h)"
                    " ON CONFLICT (date) DO NOTHING",
                    {"h": _json.dumps(outlook, default=str)})
            except Exception:
                pass
    except Exception:
        outlook = None
    try:
        # tape overlay — the session-tape verdict on the daily call:
        # refreshes at each 15m mark; never overwrites the regime
        # verdict, only the tactical part of "so today:"
        from app.signals import market_stability as _ms
        tape_overlay = await asyncio.to_thread(
            _ms.tape_overlay, (t or {}).get("regime"))
    except Exception:
        tape_overlay = None
    return {"today": t, "intraday": intraday, "fragility": fragility,
            "movement": movement, "valuation": valuation,
            "posture": posture, "rates": rates, "direction": direction,
            "outlook": outlook, "tape": tape_overlay,
            "record": await asyncio.to_thread(morning.record)}


@router.get("/metals-pulse")
async def metals_pulse_report():
    """Metals Pulse — latest journaled dashboard (macro metals regime +
    gold/silver/copper scores + verdicts). Lazy-evals on an empty
    journal so first deploys don't wait for the nightly job."""
    from app.metals import engine as metals_engine
    latest = await asyncio.to_thread(metals_engine.read)
    if latest is None:
        latest = await asyncio.to_thread(metals_engine.run)
    return {"today": latest}


@router.get("/theme-intelligence")
async def theme_intelligence_report():
    """Theme Intelligence — latest journaled dashboard (scenario
    probabilities + per-theme opportunity/downside/robustness +
    index weights). Lazy-evals on an empty journal."""
    from app.themes import engine as themes_engine
    latest = await asyncio.to_thread(themes_engine.read)
    if latest is None:
        latest = await asyncio.to_thread(themes_engine.run)
    return {"today": latest}


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
    jobs = await asyncio.to_thread(scheduler.catalog)
    for j in jobs:
        st = _jobs.get(j.get("name")) or {}
        if st.get("running"):
            j["running"] = True
            j["started_at"] = st.get("started_at")
    return {"jobs": jobs}


@router.post("/jobs/{name}/schedule")
async def set_job_schedule(name: str, body: dict):
    """Enable/disable + cron for a job — the only write path the
    dispatcher honors."""
    from app.support import scheduler
    return await asyncio.to_thread(
        scheduler.set_schedule, name, body.get("cron"),
        bool(body.get("enabled")), body.get("timezone"))


@router.get("/jobs/runs")
async def job_runs(limit: int = 50):
    """Recent dispatcher executions — the durable ledger the scheduler
    page shows under the catalog."""
    from app.database import db
    rows = await asyncio.to_thread(
        db.execute_query,
        "SELECT run_id, name, ran_at, duration_s, error, result"
        " FROM job_runs ORDER BY ran_at DESC LIMIT :n",
        {"n": min(limit, 200)})
    return {"runs": rows}


@router.get("/jobs/failures")
async def job_failures(hours: float = 24, limit: int = 50):
    """Failed runs in the window — the external watchdog contract.
    Poll this, alert on new run_ids, then grep the worker log for
    `JOB_FAIL`/`run=<run_id>` to pull the traceback context."""
    from app.database import db
    rows = await asyncio.to_thread(
        db.execute_query,
        "SELECT run_id, name, ran_at, duration_s, error"
        " FROM job_runs WHERE error IS NOT NULL"
        " AND ran_at >= now() - CAST(:h || ' hours' AS interval)"
        " ORDER BY ran_at DESC LIMIT :n",
        {"h": hours, "n": min(limit, 200)})
    return {"failures": rows, "hours": hours}


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
    """Book coverage — every symbol the deep watcher tracks, with the
    book(s) that make it a member (real portfolio names, or
    'watchlist')."""
    from app.database import db
    q = """
        SELECT s.symbol,
               string_agg(DISTINCT x.book, ', ' ORDER BY x.book) AS books
        FROM stocks s
        JOIN (
            SELECT pp.stock_id AS sid, p.name AS book
            FROM portfolio_positions pp
            JOIN portfolios p ON p.id = pp.portfolio_id
            WHERE pp.quantity > 0
            UNION
            SELECT st2.id, p2.name
            FROM portfolio_holdings h
            JOIN portfolios p2 ON p2.id = h.portfolio_id
            JOIN stocks st2 ON st2.symbol = h.symbol
            WHERE h.status IN ('active', 'inactive')
            UNION
            SELECT ws.stock_id, 'watchlist'
            FROM watchlist_stocks ws
        ) x ON x.sid = s.id
        GROUP BY s.symbol ORDER BY s.symbol
    """
    return await asyncio.to_thread(db.execute_query, q)


@router.post("/focus/{symbol}")
async def focus_add(symbol: str, thesis: str = ""):
    """Track a name you don't hold — writes a tracking unit into the
    `futureStocks` book, which makes the symbol canonical coverage
    (book_symbols → every job, incl. the deep watcher)."""
    sym = symbol.upper().strip()
    if not (1 <= len(sym) <= 10 and sym.replace(".", "").isalnum()):
        raise HTTPException(400, f"bad symbol '{symbol}'")
    from app.database import db
    from app.signals import symbol_tiers
    db.execute_query(
        "INSERT INTO stocks (symbol) VALUES (:s) "
        "ON CONFLICT (symbol) DO NOTHING", {"s": sym})
    ok = await asyncio.to_thread(
        symbol_tiers.promote, sym, f"focus:{thesis.strip() or 'manual'}")
    return {"tracked": sym, "promoted": ok}


@router.delete("/focus/{symbol}")
async def focus_remove(symbol: str):
    """Stop tracking a name — removes its watchlist row or futureStocks
    tracking unit. Real positions stay: you can't unwatch a holding,
    its membership comes from the book itself."""
    sym = symbol.upper().strip()
    from app.database import db
    from app.signals import symbol_tiers

    def _go():
        held = db.execute_query(
            "SELECT p.name FROM portfolio_positions pp"
            " JOIN portfolios p ON p.id = pp.portfolio_id"
            " JOIN stocks s ON s.id = pp.stock_id"
            " WHERE s.symbol = :s AND pp.quantity > 0"
            " AND p.name <> :f",
            {"s": sym, "f": symbol_tiers.FUTURES_BOOK})
        if held:
            return {"held_in": [r["name"] for r in held]}
        rm_wl = db.execute_update(
            "DELETE FROM watchlist_stocks ws USING stocks s"
            " WHERE ws.stock_id = s.id AND s.symbol = :s", {"s": sym})
        rm_trk = db.execute_update(
            "DELETE FROM portfolio_positions pp USING stocks s,"
            " portfolios p WHERE pp.stock_id = s.id"
            " AND pp.portfolio_id = p.id AND p.name = :f"
            " AND s.symbol = :s",
            {"s": sym, "f": symbol_tiers.FUTURES_BOOK})
        return {"removed_watchlist": bool(rm_wl),
                "removed_tracking": bool(rm_trk)}
    out = await asyncio.to_thread(_go)
    if out.get("held_in"):
        raise HTTPException(
            409, f"{sym} is held in {out['held_in']} — a position can't "
                 "be unwatched; sell it or archive the position instead")
    if not (out["removed_watchlist"] or out["removed_tracking"]):
        raise HTTPException(404, f"{sym} has no tracking membership")
    return {"untracked": sym, **out}


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


@router.get("/receipts")
async def receipts(limit: int = 100):
    """The public ledger — every journaled board pick with its graded
    forward returns at 5/10/20d (LEAPS out to 60d), plus the regime
    calls. Hits and misses in the same list."""
    from app.signals import board_tracking as bt
    return await asyncio.to_thread(bt.receipts, limit)


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
    "engine_weights_log": "logged_at",
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
                 "milestones": [], "calibration": None,
                 "migrations": getattr(db, "migration_report", None)}

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
            " WHERE key ~ '^(dip:|gate:|meta:|feat:|calls:|alpha:"
            "|posture:)' ORDER BY key")
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

    # --- version grade — the 'is it learning?' view: outcomes ------
    # grouped by the rules_version that produced them. Each block is
    # a journal→outcome join; a version with better hit/median is a
    # better spec iteration. Blocks degrade independently so a
    # missing outcome table can't blank the whole card.
    grade = []
    _GRADE_SQL = {
        # board decisions → forward returns at the 10d horizon
        "board": (
            "SELECT d.rules_version rv, count(*) n,"
            " round(avg(CASE WHEN o.ret_pct>0 THEN 1 ELSE 0 END),3) hit,"
            " round(avg(o.ret_pct)::numeric,2) avg_ret,"
            " min(d.as_of) first, max(d.as_of) last"
            " FROM board_outcomes o JOIN board_decisions d"
            "  ON d.id=o.decision_id"
            " WHERE o.horizon_days=10"
            " GROUP BY d.rules_version ORDER BY min(d.as_of)"),
        # top-3 calls → stop/target resolution + forward returns
        "daily_calls": (
            "SELECT c.rules_version rv, count(*) n,"
            " round(avg(CASE WHEN o.resolution='target_first'"
            "           THEN 1 ELSE 0 END),3) hit,"
            " round(avg(o.ret_10d)::numeric,2) avg_ret,"
            " min(c.call_date) first, max(c.call_date) last"
            " FROM daily_call_outcomes o JOIN daily_calls c"
            "  ON c.id=o.call_id WHERE o.resolution<>'open'"
            " GROUP BY c.rules_version ORDER BY min(c.call_date)"),
        # posture permission → forward index returns
        "posture": (
            "SELECT e.rules_version rv, count(*) n,"
            " round(avg(CASE WHEN o.fwd_10d>0 THEN 1 ELSE 0 END),3) hit,"
            " round(avg(o.fwd_10d)::numeric,2) avg_ret,"
            " min(o.as_of) first, max(o.as_of) last"
            " FROM posture_outcomes o JOIN posture_evals e"
            "  ON e.id=o.eval_id"
            " GROUP BY e.rules_version ORDER BY min(o.as_of)"),
        # lev paper positions → realized R by spec iteration
        "lev_swings": (
            "SELECT spec rv, count(*) n,"
            " round(avg(CASE WHEN realized_r>0 THEN 1 ELSE 0 END),3) hit,"
            " round(avg(realized_r)::numeric,2) avg_ret,"
            " min(opened_as_of) first, max(opened_as_of) last"
            " FROM lev_etf_positions WHERE state='closed'"
            "  AND realized_r IS NOT NULL"
            " GROUP BY spec ORDER BY min(opened_as_of)"),
    }
    for eng, q in _GRADE_SQL.items():
        try:
            for r in db.execute_query(q):
                grade.append({"engine": eng,
                              "rules_version": r.get("rv"),
                              "n": r["n"], "hit": r.get("hit"),
                              "avg_ret": r.get("avg_ret"),
                              "first": str(r.get("first")),
                              "last": str(r.get("last"))})
        except Exception:
            pass
    # best_picks — picks journaled per version; forward returns are
    # computed ad hoc off daily_bars (no outcome table yet).
    try:
        bp = db.execute_query(
            "SELECT e.rules_version rv, count(*) n,"
            " round(avg(CASE WHEN r.f10>0 THEN 1 ELSE 0 END),3) hit,"
            " round(avg(r.f10)::numeric,2) avg_ret,"
            " min(e.as_of) first, max(e.as_of) last"
            " FROM best_picks_evals e"
            " LEFT JOIN LATERAL ("
            "   SELECT (c10.close/c0.close-1)*100 f10"
            "   FROM LATERAL (SELECT close FROM daily_bars b"
            "     WHERE b.symbol=e.symbol AND b.date<=e.as_of"
            "     ORDER BY b.date DESC LIMIT 1) c0,"
            "   LATERAL (SELECT close FROM daily_bars b"
            "     WHERE b.symbol=e.symbol AND b.date>e.as_of"
            "     ORDER BY b.date OFFSET 9 LIMIT 1) c10"
            " ) r ON true"
            " WHERE e.lane='pick'"
            "  AND e.as_of > now() - interval '180 days'"
            " GROUP BY e.rules_version ORDER BY min(e.as_of)")
        for r in bp:
            grade.append({"engine": "best_picks",
                          "rules_version": r.get("rv"),
                          "n": r["n"], "hit": r.get("hit"),
                          "avg_ret": r.get("avg_ret"),
                          "first": str(r.get("first")),
                          "last": str(r.get("last"))})
    except Exception:
        pass
    # spec registry — what each version string actually was
    try:
        out["spec_versions"] = db.execute_query(
            "SELECT engine, version,"
            " to_char(created_at,'YYYY-MM-DD') first_seen"
            " FROM spec_versions ORDER BY created_at")
    except Exception:
        out["spec_versions"] = []
    out["version_grade"] = grade

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

@router.get("/selloff")
async def selloff_scan():
    """Selloff Opportunity Engine — market dislocation status +
    ranked candidates: fallen-but-sound names scored on price
    dislocation vs business integrity, with classification, gates and
    staged entry plans. Advisory only."""
    from app.signals import (selloff, market_stability,
                             liquidity_forward, liquidity_engine,
                             selloff_review)
    out = await asyncio.to_thread(selloff.scan)
    # the third-question context: dip names + whether buyers are
    # actually returning. Journaled reads — display context, the
    # scan itself stays advisory and ungated on it.
    try:
        stab = await asyncio.to_thread(market_stability.read)
        fwd = await asyncio.to_thread(liquidity_forward.read)
        liq = await asyncio.to_thread(liquidity_engine.read)
        out["context"] = {
            "stability_label": (stab or {}).get("stability_label"),
            "stable_sessions": (stab or {}).get("stable_sessions"),
            "recovery_status": (stab or {}).get("recovery_status"),
            "forward_hint_8w": (fwd or {}).get("posture_hint"),
            "flow_destination":
                ((liq or {}).get("flow_matrix") or {})
                .get("destination"),
            "liquidity_score": (liq or {}).get("liquidity_score"),
            "market_stability_score":
                ((stab or {}).get("session_entries") or {})
                .get("market_stability_score"),
            "engine_record": selloff_review.read_report(),
        }
        # session entries — per-candidate staged-entry verdicts from
        # the stability job's last run; attached to scan rows by
        # symbol so /plan shows WHO is accumulating, not just who fell
        entries = ((stab or {}).get("session_entries") or {}) \
            .get("entries") or {}
        if entries:
            for c in out.get("candidates") or []:
                e = entries.get(c.get("symbol"))
                if e:
                    c["session_entry"] = e
    except Exception:
        pass
    return out


@router.get("/short-squeeze")
async def short_squeeze_board():
    """Short-squeeze board — latest journaled eval per symbol, ranked:
    covering rallies first (fade risk), then shorts-pressing, then
    squeeze setups. Includes SI%, days-to-cover and short-sale-ratio
    trend evidence."""
    from app.database import db
    rows = db.execute_query(
        "SELECT DISTINCT ON (e.symbol) e.symbol, e.as_of, e.fuel,"
        " e.covering_probability, e.verdict, e.data_quality, e.rally,"
        " e.ret_5d, e.rel_vol, e.si_pct, e.days_to_cover,"
        " e.sv_ratio_latest, e.sv_trend, e.evidence,"
        " s.company_name, s.momentum_state"
        " FROM short_squeeze_evals e"
        " LEFT JOIN stocks s ON s.symbol = e.symbol"
        " ORDER BY e.symbol, e.as_of DESC")
    rank = {"likely_covering": 0, "new_shorts_pressing": 1,
            "squeeze_setup": 2, "no_clear_signal": 3,
            "genuine_accumulation": 4, "insufficient_data": 5}
    rows.sort(key=lambda r: (rank.get(r["verdict"], 6),
                             -(r["fuel"] or 0)))
    return {"count": len(rows), "evals": rows}


@router.get("/short-squeeze/{symbol}")
async def short_squeeze_symbol(symbol: str):
    """Live squeeze eval for one symbol + recent SI/SV series — the
    evidence behind the verdict."""
    from app.signals import short_squeeze
    from app.database import db
    ev = await asyncio.to_thread(short_squeeze.evaluate, symbol.upper())
    ev["si_series"] = db.execute_query(
        "SELECT short_interest_date AS d, short_interest AS si,"
        " short_percent AS pct, days_to_cover AS dtc"
        " FROM short_interest WHERE symbol=:s"
        " ORDER BY short_interest_date DESC LIMIT 8",
        {"s": symbol.upper()})
    ev["sv_series"] = db.execute_query(
        "SELECT short_volume_date AS d, short_volume_percent AS ratio"
        " FROM short_volume WHERE symbol=:s"
        " ORDER BY short_volume_date DESC LIMIT 15",
        {"s": symbol.upper()})
    return ev


@router.get("/intraday")
async def intraday_tape():
    """Session tape — latest journaled state + today's timeline.
    Lazy-evals during RTH when the last journal row is >14 min old,
    so opening this page is what keeps the tape alive."""
    from app.signals import intraday_pulse as ip
    out = await asyncio.to_thread(ip.latest)
    if ip.market_open_now() and out.get("eval"):
        try:
            from datetime import datetime, timezone, timedelta
            last_ts = out.get("ts")
            stale = True
            if last_ts:
                dt = datetime.fromisoformat(str(last_ts))
                stale = (datetime.now(timezone.utc)
                         - dt.astimezone(timezone.utc)
                         ) > timedelta(minutes=14)
            if stale:
                await asyncio.to_thread(ip.evaluate)
                out = await asyncio.to_thread(ip.latest)
        except Exception:                                   # noqa: BLE001
            pass
    elif ip.market_open_now() and not out.get("eval"):
        await asyncio.to_thread(ip.evaluate)
        out = await asyncio.to_thread(ip.latest)
    return out


@router.get("/correction-alarms")
async def correction_alarms():
    """Latest correction-alarm eval — the four legs + character.
    Computes live if nothing is journaled today (self-healing)."""
    from app.signals import correction_alarms as ca
    out = await asyncio.to_thread(ca.latest)
    if not out or out.get("as_of") != str(date.today()):
        out = await asyncio.to_thread(ca.evaluate)
    return out


@router.get("/read-through")
async def read_through_latest(days: int = 1):
    """Extended-hours basket repricing events — peers lifting whole
    themes post-close/pre-open. Fed into the morning regime."""
    from app.signals import read_through
    return {"events": await asyncio.to_thread(read_through.latest,
                                              days)}


@router.get("/earnings-watch")
async def earnings_watch_latest(days: int = 7):
    """Earnings-day captures — prints + improving/deteriorating
    verdicts from the 30-min after-hours watcher."""
    from app.signals import earnings_watch
    return {"reporters": await asyncio.to_thread(
        earnings_watch.todays_reporters),
        "captures": await asyncio.to_thread(earnings_watch.latest,
                                            days)}


@router.get("/forward-outlook")
async def forward_outlook(sym: Optional[str] = None):
    """Engine A+B output for the regime page — market analogs →
    forward outcome stats at 5d..252d, plus (when sym) the stock's
    unconditional forward distribution and the event study."""
    from app.signals import forward_analogs, event_study
    out = {"market": await asyncio.to_thread(
        forward_analogs.market_outlook)}
    if sym:
        out["stock_forward"] = await asyncio.to_thread(
            forward_analogs.stock_forward_distribution, sym)
        out["event_study"] = await asyncio.to_thread(
            event_study.run, sym)
    else:
        out["event_study"] = await asyncio.to_thread(event_study.run)
    return out


@router.get("/expected-option-pnl")
async def expected_option_pnl(sym: str, strike: float, expiry: str,
                              premium: float, iv: Optional[float] = None):
    """Engine C — Σ p_i × (BS(S_i, IV_i) − premium) under the FV
    scenario distribution. Contract params come from the chain quote
    the user is evaluating."""
    from app.options import expected_pnl
    return await asyncio.to_thread(
        expected_pnl.expected_call_pnl, sym, strike, expiry, premium, iv)


@router.get("/fwd-eps-audit")
async def fwd_eps_audit():
    """Read-only audit — every stored fwd_eps_avg that fails the
    TTM-ratio or snapshot-year checks. The fwd-eps-repair job
    recomputes these through the guarded path and re-resolves FV."""
    from app.signals import expectation_gap
    return {"suspects": await asyncio.to_thread(
        expectation_gap.audit_fwd_eps, await _tracked_symbols())}


@router.get("/earnings-report/{symbol}")
async def earnings_report(symbol: str, date: str | None = None,
                          version: int | None = None):
    """The versioned per-print earnings report — headline, vs-
    consensus highlights, growth, quality, guidance, verdict.
    ?date=YYYY-MM-DD pins a print, ?version=N pins a version."""
    from app.signals import earnings_report as er
    r = await asyncio.to_thread(er.report, symbol.upper(), date,
                                version)
    if r is None and not version:
        # lazy-compose — prints captured before this feature exist as
        # earnings_data/earnings_watch rows with no report; journal v1
        # on first read rather than making the user call /rebuild
        r = await asyncio.to_thread(er.journal, symbol.upper(), date,
                                    "lazy-read")
        if r:
            r = await asyncio.to_thread(er.report, symbol.upper(),
                                        date, None)
    if r is None:
        raise HTTPException(404, f"no earnings report for {symbol}")
    return r


@router.get("/earnings-report/{symbol}/versions")
async def earnings_report_versions(symbol: str):
    """Every journaled report version for a symbol — the audit list."""
    from app.signals import earnings_report as er
    return {"symbol": symbol.upper(),
            "versions": await asyncio.to_thread(er.versions,
                                                symbol.upper())}


@router.get("/earnings-reports")
async def earnings_reports_feed(days: int = 30):
    """Latest-version earnings reports across the book — the feed."""
    from app.signals import earnings_report as er
    return {"reports": await asyncio.to_thread(er.recent, days)}


@router.post("/earnings-report/{symbol}/rebuild")
async def earnings_report_rebuild(symbol: str, date: str | None = None):
    """Recompose + append a new version — e.g. after a surprise %
    backfill or a manual driver edit. Never overwrites history."""
    from app.signals import earnings_report as er
    from datetime import date as _date
    d = _date.fromisoformat(date) if date else None
    r = await asyncio.to_thread(er.journal, symbol.upper(), d,
                                "manual")
    if r is None:
        raise HTTPException(404, f"no print to report for {symbol}")
    return r


@router.get("/income-plan")
async def income_plan(funds: float | None = None):
    """Daily income & swing plan — posture-gated suggestions across
    swing / LEAP call / LEAP put / cash-secured put / covered call,
    each bound to a trade-plans draft for one-click entry."""
    from app.signals import income_plan as ip
    return await asyncio.to_thread(ip.today, funds)


@router.get("/best-picks")
async def best_picks():
    """The three-lane best-picks read — growth_swing / long_term /
    compounder_3_5y picks + watch lanes from the latest journaled
    eval pass. Reads the journal; never re-evaluates."""
    from app.signals import best_picks as bp
    return await asyncio.to_thread(bp.latest)


@router.get("/leveraged-swings")
async def leveraged_swings(funds: float | None = None):
    """3x semis swing setups — SOXS fade-the-extension / SOXL
    confirmed-rebound over today's stored index tape (SMH proxy).
    Lazy-evals so the page reflects the freshest close and journals
    the day's verdict; levels are advisory with index-anchored
    invalidation — never orders."""
    from app.signals import leveraged_swings as ls
    return await asyncio.to_thread(ls.evaluate, funds)


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
    closed, outcomes = [], {}
    if all:
        closed = [dict(r) for r in db.execute_query(
            "SELECT * FROM trade_plans WHERE status != 'open'"
            " ORDER BY closed_at DESC NULLS LAST LIMIT 100")]
        outcomes = trade_plans.outcome_stats()
    return {"open": plans, "closed": closed, "outcomes": outcomes}


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
    try:                          # grade the close into outcomes now —
        from app.signals import trade_plans as _tp
        _tp.grade()               # the feedback loop sees it immediately
    except Exception:
        pass
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


@router.get("/readiness-states")
async def readiness_states():
    """Every book symbol bucketed by use-case state — the 'which
    stocks are ready vs close vs no' view for technical decisions."""
    from app.database import db
    rows = db.execute_query("""
        SELECT DISTINCT ON (symbol, use_case)
               symbol, use_case, state, score, of, rank, as_of
        FROM readiness_evals
        WHERE as_of >= CURRENT_DATE - 3
        ORDER BY symbol, use_case, as_of DESC, created_at DESC""")
    by_uc: dict = {}
    for r in rows:
        uc = r["use_case"]
        by_uc.setdefault(uc, {"ready": [], "close": [], "no": []})
        bucket = r["state"] if r["state"] in ("ready", "close") else "no"
        by_uc[uc][bucket].append(
            {"symbol": r["symbol"], "score": r["score"],
             "of": r.get("of"), "rank": r.get("rank")})
    for uc in by_uc.values():
        for b in uc.values():
            b.sort(key=lambda x: -(x["score"] or 0))
    return {"as_of": str(rows[0]["as_of"]) if rows else None,
            "use_cases": by_uc}


@router.get("/intraday-recovery")
async def intraday_recovery_board():
    """Latest 5-min recovery-confirmation eval per universe symbol —
    who's attracting sustained buying vs relief rally vs failing.
    Session overlay; never a checklist input."""
    from app.signals import intraday_recovery
    cur = await asyncio.to_thread(intraday_recovery.current)
    order = {"STRONG_RECOVERY": 0, "CONFIRMED_RECOVERY": 1,
             "IMPROVING": 2, "WATCH": 3, "DISTRIBUTION": 4,
             "FAILED_REBOUND": 5, "DATA_BLOCKED": 6}
    rows = sorted(cur.values(),
                  key=lambda r: (order.get(r["signal"], 6),
                                 -(r["score"] or 0), r.get("symbol") or ""))
    stale = None
    if rows:
        try:
            from datetime import datetime, timezone, timedelta
            latest = max(datetime.fromisoformat(r["bar_ts"])
                         for r in rows)
            stale = (datetime.now(timezone.utc) - latest
                     > timedelta(minutes=10))
        except Exception:
            pass
    evald = [r for r in rows if r.get("signal") != "DATA_BLOCKED"]
    participation = (round(
        sum(1 for r in evald if (r.get("vwap_hold_min") or 0) > 0)
        / len(evald) * 100, 1) if evald else None)
    return {"as_of": rows[0]["bar_ts"] if rows else None,
            "stale": stale, "participation": participation,
            "symbols": rows}


@router.get("/intraday-recovery/{symbol}/session")
async def intraday_recovery_session(symbol: str):
    """One symbol's session story — 5m bars + vwap path + journaled
    eval timeline + signal transitions + overnight gap. Read-only
    over stored rows; powers the expandable row on the regime page."""
    from app.signals import intraday_recovery
    return await asyncio.to_thread(intraday_recovery.session, symbol)


@router.get("/cycle")
async def cycle_board():
    """AI cycle rotation board — latest snapshot per universe symbol:
    8-leg composite, decision, three-peak state, demand-peak window,
    cohort aggregates. Read-only over journaled rows."""
    from app.signals import cycle_tracker
    return await asyncio.to_thread(cycle_tracker.current)


@router.get("/ai-cycle-ladder")
async def ai_cycle_ladder():
    """AI-cycle theme ladder — where the cycle is and where it's
    moving next (6-12m). Per-stage rungs (build → deploy → utilize)
    with four checkable legs: tape vs SPY, forward growth, approved
    demand-evidence axes, funding worst-case. rotation_state is the
    honest verdict: evidence_led = disclosures improving while tape
    lags (the rotation signal), tape_led = price moving unconfirmed.
    Lazy-evals on an empty journal."""
    from app.signals import inference_ladder
    latest = await asyncio.to_thread(inference_ladder.latest)
    if latest is None:
        latest = await asyncio.to_thread(inference_ladder.run)
    return latest or {}


@router.get("/competitive")
async def competitive_board():
    """Competitive resilience board — latest CRS per symbol: six legs,
    revenue-at-risk range, displacement state, top threats with
    provenance. Read-only over journaled rows."""
    from app.signals import competitive_risk
    return await asyncio.to_thread(competitive_risk.current)


@router.get("/competitive/{symbol}")
async def competitive_detail(symbol: str):
    """One name's competitive picture — latest CRS plus every
    journaled threat claim (source, stage, status, share range)."""
    from app.signals import competitive_risk
    return await asyncio.to_thread(competitive_risk.detail, symbol)


@router.get("/agentic-infra")
async def agentic_infra_board():
    """Agentic infrastructure board — latest AIS per symbol grouped
    by tier: sublayer tags, monetization fit, evidence counts.
    Read-only over journaled snapshots."""
    from app.signals import agentic_infra
    return await asyncio.to_thread(agentic_infra.current)


@router.get("/agentic-infra/{symbol}")
async def agentic_infra_detail(symbol: str):
    """One name's agentic-infrastructure picture — AIS, legs with
    notes, sublayers, seed status."""
    from app.signals import agentic_infra
    return await asyncio.to_thread(agentic_infra.evaluate_symbol,
                                   symbol)


@router.get("/cycle/{symbol}/history")
async def cycle_history(symbol: str):
    """Quarter-over-quarter snapshots for one name — composite, legs,
    decision, peak-window movement. The evidence behind 'pulled
    forward' / 'pushed out'."""
    from app.signals import cycle_tracker
    return await asyncio.to_thread(cycle_tracker.history, symbol)


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


@router.get("/posts")
async def posts(kind: str | None = None, limit: int = 50,
                sym: str | None = None):
    """Published insights — daily briefs, receipts recaps, mover
    explainers. Lazy-publishes today's brief when missing so the
    insights page never waits on a cron."""
    from app.signals import post_engine
    today_slug = f"daily-brief-{date.today().isoformat()}"
    rows = await asyncio.to_thread(post_engine.list_posts, kind, limit)
    if not any(r["slug"] == today_slug for r in rows):
        await asyncio.to_thread(post_engine.run)
        rows = await asyncio.to_thread(post_engine.list_posts, kind,
                                       limit)
    if sym:
        mslug = f"mover-{sym.lower()}-{date.today().isoformat()}"
        if not any(r["slug"] == mslug for r in rows):
            try:
                from app.signals import stock_health
                card = await asyncio.to_thread(stock_health.card, sym)
                if card:
                    await asyncio.to_thread(post_engine.mover_post,
                                            sym, card)
                    rows = await asyncio.to_thread(
                        post_engine.list_posts, kind, limit)
            except Exception:
                pass
    return {"posts": rows}


@router.get("/posts/{slug}")
async def post(slug: str):
    from app.signals import post_engine
    r = await asyncio.to_thread(post_engine.get_post, slug)
    if not r:
        raise HTTPException(status_code=404, detail="post not found")
    return r


@router.post("/posts/generate")
async def posts_generate(sym: str | None = None):
    """Manual post generation — daily brief, receipts recap, and
    optionally a mover explainer for one symbol."""
    from app.signals import post_engine
    made = await asyncio.to_thread(post_engine.run)
    if sym:
        try:
            from app.signals import stock_health
            card = await asyncio.to_thread(stock_health.card, sym)
            if card:
                r = await asyncio.to_thread(post_engine.mover_post,
                                            sym, card)
                if r:
                    made["mover"] = r["slug"]
        except Exception as exc:
            made["mover_error"] = str(exc)
    return {"generated": made}


@router.get("/passive")
async def passive_board():
    """Passive-investor overlay — monthly DCA verdict, model ETF book
    with journaled tilt suggestion, drawdown context. Advisory only;
    tilts are journaled in passive_tilts for later grading."""
    from app.signals import passive
    return await asyncio.to_thread(passive.payload)
