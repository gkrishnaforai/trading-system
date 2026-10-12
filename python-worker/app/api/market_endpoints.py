"""
Market Movers API Endpoints
Industry-standard market movers and sector analysis
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import asyncio
import requests
import pandas as pd
from datetime import datetime, date
import logging

from app.observability.logging import get_logger

# ========================================
# IMPORTANT: Router Configuration Rules
# ========================================
# DO NOT ADD PREFIX HERE! Prefixes are managed in api_server.py
# WRONG: router = APIRouter(prefix="/api/v1/market", tags=["market"])
# CORRECT: router = APIRouter(tags=["market"])
# ========================================
router = APIRouter(tags=["market"])
logger = get_logger(__name__)

class MarketMover(BaseModel):
    symbol: str
    company: str
    price: float
    change: float
    change_percent: float
    volume: str = ""
    market_cap: str = ""
    kind: str = ""              # gainers | losers | most_active
    in_portfolio: bool = False
    in_watchlist: bool = False

class MarketMoversResponse(BaseModel):
    universe_movers: List[MarketMover]   # top bucket: portfolio/watchlist names
    gainers: List[MarketMover]
    losers: List[MarketMover]
    most_active: List[MarketMover]
    market_status: str
    last_updated: str

class SectorPerformance(BaseModel):
    sector: str
    change: float
    status: str

class MarketOverview(BaseModel):
    sp500: Dict[str, float]
    nasdaq: Dict[str, float]
    dow: Dict[str, float]
    vix: Dict[str, float]

@router.get("/movers", response_model=MarketMoversResponse)
async def get_market_movers():
    """Market-wide movers from FMP, bucketed by universe membership.

    `universe_movers` = portfolio/watchlist names that are moving (the
    actionable bucket — these carry positions/watch intent); the market
    lists below are discovery candidates.
    """
    from app.alerts import scanner as alert_scanner
    from app.providers.financial_modeling_prep.client import EnhancedFMPClient

    try:
        logger.info("📈 Fetching market movers data")
        raw = EnhancedFMPClient.from_settings().get_market_movers()
        uni = alert_scanner.universe()

        def _fmt_vol(v) -> str:
            v = v or 0
            return f"{v / 1e6:.1f}M" if v >= 1e6 else f"{v / 1e3:.0f}K" if v else ""

        def _fmt_cap(v) -> str:
            v = v or 0
            return (f"{v / 1e12:.1f}T" if v >= 1e12 else
                    f"{v / 1e9:.0f}B" if v >= 1e9 else
                    f"{v / 1e6:.0f}M" if v else "")

        buckets: Dict[str, List[MarketMover]] = {}
        universe_movers: Dict[str, MarketMover] = {}
        for kind in ("gainers", "losers", "most_active"):
            movers = []
            for r in raw.get(kind) or []:
                sym = str(r.get("symbol") or "").upper()
                if not sym:
                    continue
                flags = uni.get(sym) or {}
                mv = MarketMover(
                    symbol=sym,
                    company=str(r.get("companyName") or r.get("name") or ""),
                    price=float(r.get("price") or 0),
                    change=float(r.get("change") or 0),
                    change_percent=float(r.get("changesPercentage") or 0),
                    volume=_fmt_vol(r.get("volume")),
                    market_cap=_fmt_cap(r.get("marketCap")),
                    kind=kind,
                    in_portfolio=bool(flags.get("in_portfolio")),
                    in_watchlist=bool(flags.get("in_watchlist")),
                )
                movers.append(mv)
                if mv.in_portfolio or mv.in_watchlist:
                    universe_movers[sym] = mv
            buckets[kind] = movers

        response = MarketMoversResponse(
            universe_movers=sorted(universe_movers.values(),
                                   key=lambda m: abs(m.change_percent), reverse=True),
            gainers=buckets["gainers"],
            losers=buckets["losers"],
            most_active=buckets["most_active"],
            market_status="real-time",
            last_updated=datetime.now().isoformat(),
        )
        logger.info(f"✅ Market movers: {len(universe_movers)} universe, "
                    f"{len(buckets['gainers'])} gainers, {len(buckets['losers'])} losers")
        return response

    except Exception as e:
        logger.error(f"❌ Error fetching market movers: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch market movers: {str(e)}")


@router.get("/movers/orb")
async def get_orb_watchlist():
    """Last ORB watchlist results. The screen runs as a background job —
    POST /movers/orb/run to refresh."""
    from app.daytrade.orb import orb_results
    return orb_results()


@router.post("/movers/orb/run")
async def run_orb_screen():
    """Kick off the ORB screen in the background — intraday fetches over
    movers take too long to hold an HTTP request on a cold cache."""
    import asyncio as _aio
    from app.daytrade.orb import run_orb_job, orb_status
    if orb_status()["running"]:
        return {"status": "already_running"}
    _aio.create_task(run_orb_job())
    return {"status": "started"}


@router.get("/movers/orb/status")
async def orb_screen_status():
    from app.daytrade.orb import orb_status
    return orb_status()


@router.get("/movers/earnings-week")
async def earnings_week(days: int = 7):
    """Upcoming earnings for tracked symbols — boards, portfolio,
    watchlist — grouped by report date. Backed by stocks.next_earnings_*
    (kept fresh by the flywheel/calendar refresh) joined with the
    expectation-gap metrics so each print carries context."""
    from app.database import db
    rows = db.execute_query(
        """
        WITH tracked AS (
            SELECT symbol, 'RB' AS board FROM rule_breaker_members
            UNION SELECT symbol, '5x' FROM smallcap_members
            UNION SELECT s.symbol, 'portfolio'
                FROM stocks s
                JOIN portfolio_positions pp
                    ON pp.stock_id = s.id AND pp.quantity > 0
            UNION SELECT s.symbol, 'watchlist'
                FROM stocks s
                JOIN watchlist_stocks ws ON ws.stock_id = s.id
        )
        SELECT st.symbol, st.next_earnings_date AS date,
               st.next_earnings_eps_est AS eps_est,
               st.next_earnings_rev_est AS rev_est,
               st.next_earnings_session AS session,
               st.next_earnings_date - CURRENT_DATE AS days_out,
               fw.gap_score, fw.beat_streak, fw.est_revision_pct,
               fw.muted_reaction,
               string_agg(DISTINCT t.board, '+' ORDER BY t.board) AS boards
        FROM stocks st
        JOIN tracked t ON t.symbol = st.symbol
        LEFT JOIN symbol_flywheel fw ON fw.symbol = st.symbol
        WHERE st.next_earnings_date BETWEEN CURRENT_DATE
              AND CURRENT_DATE + :d
        GROUP BY st.symbol, st.next_earnings_date, st.next_earnings_eps_est,
                 st.next_earnings_rev_est, st.next_earnings_session,
                 fw.gap_score, fw.beat_streak, fw.est_revision_pct,
                 fw.muted_reaction
        ORDER BY st.next_earnings_date, st.symbol
        """, {"d": days})
    by_day: dict[str, list] = {}
    for r in rows:
        d = str(r["date"])
        r["date"] = d
        r["days_out"] = int(r["days_out"])
        by_day.setdefault(d, []).append(dict(r))
    return {"days": days, "count": len(rows), "by_day": by_day}


@router.get("/movers/quality")
async def get_quality_movers():
    """Last quality-screen results. The screen runs as a background job —
    POST /movers/quality/run to start one."""
    from app.screener.quality import quality_results
    return quality_results()


@router.post("/movers/quality/run")
async def run_quality_screen():
    """Kick off the quality screen in the background — the fundamental
    fetches take ~1-2 min cold, too long to hold an HTTP request."""
    import asyncio as _aio
    from app.screener.quality import run_quality_job, quality_status
    if quality_status()["running"]:
        return {"status": "already_running"}
    _aio.create_task(run_quality_job())
    return {"status": "started"}


@router.get("/movers/quality/status")
async def quality_screen_status():
    from app.screener.quality import quality_status
    return quality_status()


@router.get("/movers/sector-rotation")
async def sector_rotation_board():
    """Sector momentum + capital-flow board — computed from sector/theme ETF
    daily bars (cached EOD). 'flow' is the funding proxy: price×volume
    action, since no fund-flow feed is on the plan."""
    from app.market_regime.rotation import sector_rotation
    return await sector_rotation()


@router.get("/movers/sectors/candidates")
async def get_sector_candidates():
    """Last sector-candidate ranking — top ~10 names per sector/theme scored
    on CANSLIM fundamentals. Background job: POST .../run to refresh."""
    from app.screener.sector_candidates import candidates_results
    return candidates_results()


@router.post("/movers/sectors/candidates/run")
async def run_sector_candidates():
    import asyncio as _aio
    from app.screener.sector_candidates import candidates_status, run_candidates_job
    if candidates_status()["running"]:
        return {"status": "already_running"}
    _aio.create_task(run_candidates_job())
    return {"status": "started"}


@router.get("/movers/sectors/candidates/status")
async def sector_candidates_status():
    from app.screener.sector_candidates import candidates_status
    return candidates_status()


@router.get("/movers/themes/catalysts")
async def theme_catalyst_feed(days: int = 7):
    """Positive catalyst/EPS events for theme members — the 'fundamentals
    improving' feed next to the theme rankings. Pure DB read."""
    from app.screener.sector_candidates import theme_catalysts
    return theme_catalysts(days=min(days, 30))


@router.get("/movers/sectors/candidates/moves")
async def sector_candidate_moves():
    """Rank deltas between the two most recent candidate runs — climbers,
    new entries, and dropped names per basket."""
    from app.screener.sector_candidates import rank_moves
    return rank_moves()


@router.get("/movers/afterhours")
async def get_afterhours():
    """Latest after-hours board — top gainers + universe movers, persisted."""
    from app.screener.afterhours import afterhours_results
    return afterhours_results()


@router.post("/movers/afterhours/run")
async def run_afterhours():
    import asyncio as _aio
    from app.screener.afterhours import afterhours_status, run_afterhours_job
    if afterhours_status()["running"]:
        return {"status": "already_running"}
    _aio.create_task(run_afterhours_job())
    return {"status": "started"}


@router.get("/movers/afterhours/status")
async def afterhours_scan_status():
    from app.screener.afterhours import afterhours_status
    return afterhours_status()


@router.get("/movers/premarket")
async def get_premarket():
    """Latest pre-market board — top gainers + universe movers, persisted."""
    from app.screener.afterhours import session_results
    return session_results("pre")


@router.post("/movers/premarket/run")
async def run_premarket():
    import asyncio as _aio
    from app.screener.afterhours import run_session_job, session_status
    if session_status("pre")["running"]:
        return {"status": "already_running"}
    _aio.create_task(run_session_job("pre"))
    return {"status": "started"}


@router.get("/movers/premarket/status")
async def premarket_scan_status():
    from app.screener.afterhours import session_status
    return session_status("pre")


@router.get("/movers/fear-greed")
async def fear_greed_index():
    """Computed fear/greed gauge — momentum + breadth + near-highs + VIX."""
    from app.market_regime.sentiment import fear_greed
    return await fear_greed()


@router.get("/movers/macro")
async def movers_macro():
    """Regime card + upcoming macro calendar (FOMC/jobs/CPI/PPI/PCE) +
    forward probabilities + global-risk context — the scheduled dates
    and the world-events read that can flip the regime."""
    from app.alerts import service as alert_service
    from app.market_events.calendar import upcoming_macro_events
    from app.signals import (breadth as _br, capex_cycle as _cx,
                             geo_context as _geo)
    from app.market_regime.forward import forward_probs
    regime = await asyncio.to_thread(alert_service.regime_card)
    breadth = await asyncio.to_thread(_br.read)
    geo = await asyncio.to_thread(_geo.read)
    capex = await asyncio.to_thread(_cx.read)
    rd = (regime or {}).get("regime_detail") or {}
    fwd = forward_probs(rd, breadth, geo,
                        vix=(rd.get("vix") or {}).get("vix")
                        if isinstance(rd.get("vix"), dict) else None)
    return {"regime": regime, "forward": fwd, "geo": geo or None,
            "breadth": breadth or None, "capex": capex or None,
            "events": await asyncio.to_thread(upcoming_macro_events, 45)}


@router.get("/movers/option-ideas")
async def options_ideas():
    """Rules-based option structure ideas over held + ready names."""
    from app.screener.option_ideas import option_ideas
    return option_ideas()


class WheelPositionIn(BaseModel):
    symbol: str
    kind: str                      # 'csp' | 'cc'
    strike: float
    expiry: str                    # ISO date
    contracts: int = 1
    premium: Optional[float] = None   # per share
    notes: Optional[str] = None


@router.get("/movers/pt-watch")
async def pt_watch_board_ep():
    """Latest PT snapshot per symbol — analyst repricing board."""
    from app.screener.pt_watch import pt_watch_board
    return pt_watch_board()


@router.post("/movers/pt-watch/run")
async def pt_watch_run():
    from app.screener.pt_watch import run_pt_watch, pt_watch_status
    if pt_watch_status()["running"]:
        return {"status": "already_running"}
    asyncio.create_task(run_pt_watch())
    return {"status": "started"}


@router.get("/movers/pt-watch/status")
async def pt_watch_status_ep():
    from app.screener.pt_watch import pt_watch_status
    return pt_watch_status()


@router.get("/movers/analyst-tape")
async def analyst_tape_board_ep(hours: int = 48):
    """Event-level analyst actions (upgrade/downgrade/PT change) on
    universe symbols — the early upgrade catch."""
    from app.screener.analyst_tape import analyst_tape_board
    return analyst_tape_board(hours=hours)


@router.post("/movers/analyst-tape/run")
async def analyst_tape_run(symbol: Optional[str] = None):
    from app.screener.analyst_tape import run_analyst_tape, analyst_tape_status
    if analyst_tape_status()["running"]:
        return {"status": "already_running"}
    asyncio.create_task(run_analyst_tape(symbol=symbol))
    return {"status": "started", "symbol": symbol}


@router.get("/movers/analyst-tape/status")
async def analyst_tape_status_ep():
    from app.screener.analyst_tape import analyst_tape_status
    return analyst_tape_status()


@router.get("/movers/daily-edge")
async def daily_edge_ep(hours: int = 48):
    """Morning confluence board — top swing candidates (catalyst × setup)
    and breakout-watch names. Reads persisted data only."""
    from app.screener.daily_edge import compute_edge
    return compute_edge(hours=hours)


@router.post("/movers/daily-edge/persist")
async def daily_edge_persist():
    """Persist today's picks to daily_picks for outcome tracking."""
    from app.screener.daily_edge import persist_picks
    return persist_picks()


@router.post("/movers/daily-edge/evaluate")
async def daily_edge_evaluate():
    """Forward-evaluate persisted picks — returns/MFE/MAE/vs-SPY and
    stop-vs-target-first, the edge board's report card."""
    from app.screener.pick_outcomes import evaluate_pick_outcomes
    return await evaluate_pick_outcomes()


@router.get("/movers/daily-edge/scorecard")
async def daily_edge_scorecard(horizon: int = 5):
    """Win-rate / avg-return / beat-SPY summary per lane."""
    from app.screener.pick_outcomes import pick_scorecard
    return pick_scorecard(horizon)


class RBMemberBody(BaseModel):
    symbol: str
    tier: str = "watchlist"
    checklist: dict = {}


class CyclicalityBody(BaseModel):
    symbol: str
    cyclical: bool


@router.get("/movers/rule-breakers")
async def rule_breakers_board_ep():
    """Rule Breaker ladder — confirmed/emerging/watchlist with gate
    evidence per member."""
    from app.screener.rule_breakers import rb_board
    return rb_board()


@router.post("/movers/rule-breakers/run")
async def rule_breakers_run(discover: bool = False):
    from app.screener.rule_breakers import run_rule_breakers, rb_status
    if rb_status()["running"]:
        return {"status": "already_running"}
    asyncio.create_task(run_rule_breakers(discover=discover))
    return {"status": "started", "discover": discover}


@router.get("/movers/rule-breakers/status")
async def rule_breakers_status_ep():
    from app.screener.rule_breakers import rb_status
    return rb_status()


@router.post("/movers/rule-breakers/research-ai")
async def rule_breakers_research_ai(symbol: str = "", force: bool = False):
    """LLM researches AI exposure for one member (or all missing
    ai_rev_pct) and writes the checklist — agent values carry provenance
    and never overwrite human-set fields."""
    from app.screener import ai_research
    if symbol:
        return await ai_research.research_symbol(symbol, force=force)
    return await ai_research.research_missing()


@router.post("/movers/rule-breakers/member")
async def rule_breakers_upsert(body: RBMemberBody):
    from app.screener.rule_breakers import upsert_member
    return upsert_member(body.symbol, body.tier, body.checklist)


@router.delete("/movers/rule-breakers/member/{symbol}")
async def rule_breakers_delete(symbol: str):
    from app.screener.rule_breakers import remove_member
    return remove_member(symbol)


# --- 5x Scout (small-cap multibagger hunter, separate from RB) -----------

@router.get("/movers/smallcap")
async def smallcap_board_ep():
    """5x Scout ladder — watch/inflecting/runner with gate evidence,
    hidden-engine segments, and multibagger score per member."""
    from app.screener.smallcap import sc_board
    return sc_board()


@router.post("/movers/smallcap/run")
async def smallcap_run(discover: bool = False):
    from app.screener.smallcap import run_smallcap, sc_status
    if sc_status()["running"]:
        return {"status": "already_running"}
    asyncio.create_task(run_smallcap(discover=discover))
    return {"status": "started", "discover": discover}


@router.get("/movers/smallcap/status")
async def smallcap_status_ep():
    from app.screener.smallcap import sc_status
    return sc_status()


@router.post("/movers/smallcap/research")
async def smallcap_research(symbol: str = "", force: bool = False):
    from app.screener import ai_research
    if symbol:
        return await ai_research.research_symbol(
            symbol, force=force, engine="smallcap")
    return await ai_research.research_missing(engine="smallcap")


@router.post("/movers/smallcap/member")
async def smallcap_upsert(body: RBMemberBody):
    from app.screener.smallcap import upsert_member
    return upsert_member(body.symbol, body.tier, body.checklist)


@router.delete("/movers/smallcap/member/{symbol}")
async def smallcap_delete(symbol: str):
    from app.screener.smallcap import remove_member
    return remove_member(symbol)


# --- Options / LEAPS -------------------------------------------------------

@router.get("/options/leaps")
async def options_leaps(symbol: str, beta: Optional[float] = None,
                        risk_free: float = 0.045):
    """LEAPS screen — technicals + direction verdict + ranked
    calls/puts per >400d expiry. Chain via yfinance; greeks computed
    locally (Black-Scholes on contract IV)."""
    from app.options.leaps import leaps_screen
    return await leaps_screen(symbol, beta=beta, risk_free=risk_free)


@router.get("/options/phase-scan")
async def options_phase_scan():
    """Portfolio/watchlist/board sweep: which tracked names sit in the
    CALL zone (washed-out inside uptrend) vs the PUT zone (extended +
    stalling, cyclical or deteriorating). Same verdict path as the
    single-symbol screen, minus option chains."""
    from app.options.leaps import tracked_phase_scan
    return await tracked_phase_scan()


class LeapsPositionBody(BaseModel):
    symbol: str
    side: str                          # CALL | PUT
    expiry: str                        # ISO date
    strike: float
    contracts: int = 1
    entry_mid: Optional[float] = None
    entry_spot: Optional[float] = None
    entry_delta: Optional[float] = None
    entry_iv: Optional[float] = None
    entry_hv: Optional[float] = None
    thesis_stage: Optional[str] = None
    gap_score: Optional[int] = None
    cyclical: Optional[bool] = None
    entry_hi_60d: Optional[float] = None
    entry_lo_60d: Optional[float] = None
    notes: Optional[str] = None
    meta: Optional[dict] = None


@router.get("/options/leaps-book")
async def options_leaps_book(mark: bool = False):
    """The sequential-convexity position book: open positions with
    marks + live exit alerts, recent closed, per-symbol cooldowns
    (the memory layer — post-failure symbols are suppressed ~20
    trading days). mark=true reprices first (slow — chains + bars)."""
    from app.options.leaps_book import get_book, mark_book
    result = {"mark": mark_book() if mark else None}
    result.update(get_book())
    return result


@router.post("/options/leaps-book/open")
async def options_leaps_open(body: LeapsPositionBody):
    """Record a CALL/PUT LEAPS position the user decided to take —
    advisory book-keeping, never order placement."""
    from app.options.leaps_book import open_position
    return open_position(body.model_dump())


@router.post("/options/leaps-book/close/{pos_id}")
async def options_leaps_close(pos_id: int,
                              close_mid: Optional[float] = None,
                              reason: str = "manual"):
    from app.options.leaps_book import close_position
    return close_position(pos_id, close_mid=close_mid, reason=reason)


@router.post("/options/leaps-book/mark")
async def options_leaps_mark():
    """Reprice open positions + evaluate exit rules (ladder tiers,
    invalidation, time-stops) → writes exit_alert per position."""
    from app.options.leaps_book import mark_book
    return mark_book()


@router.post("/options/cyclicality")
async def options_cyclicality(body: CyclicalityBody):
    """Human override for the cyclical/structural gate. source
    'human' always wins over the agent verdict until cleared.
    Stored on the stocks master row — every engine reads it."""
    from app.symbol_classification import set_cyclicality
    return set_cyclicality(body.symbol, body.cyclical)


@router.delete("/options/cyclicality/{symbol}")
async def options_cyclicality_clear(symbol: str):
    """Clear the classification — next consumer re-classifies via
    the agent."""
    from app.symbol_classification import clear_cyclicality
    return clear_cyclicality(symbol)


@router.get("/stock/{symbol}/cyclicality")
async def stock_cyclicality(symbol: str):
    """Read the stored cyclical/structural classification (no agent
    call — returns classification only if already resolved)."""
    from app.database import db
    rows = db.execute_query(
        "SELECT symbol, cyclical, cyclical_source, cyclical_confidence,"
        " cyclical_rationale, cyclical_updated_at FROM stocks "
        "WHERE symbol=:s", {"s": symbol.upper().strip()})
    if not rows:
        return {"symbol": symbol.upper(), "cyclical": None,
                "source": "unresolved"}
    r = rows[0]
    return {"symbol": r["symbol"], "cyclical": r["cyclical"],
            "source": r["cyclical_source"],
            "confidence": r["cyclical_confidence"],
            "rationale": r["cyclical_rationale"],
            "updated_at": (r["cyclical_updated_at"].isoformat()
                           if r["cyclical_updated_at"] else None)}


@router.get("/movers/acceleration")
async def acceleration_board():
    """Acceleration watch — growth-streak basket, deceleration warnings on
    held names, and streak-broken names vs the previous candidates run."""
    from app.screener.sector_candidates import acceleration_watch
    return acceleration_watch()


@router.get("/movers/wheel")
async def wheel_list(include_closed: bool = False):
    """Open wheel positions with live status vs latest screen-run price."""
    from app.screener.wheel import list_positions
    return list_positions(include_closed)


@router.post("/movers/wheel")
async def wheel_add(body: WheelPositionIn):
    from app.screener.wheel import add_position
    return add_position(body.symbol, body.kind, body.strike, body.expiry,
                        body.contracts, body.premium, body.notes)


@router.post("/movers/wheel/{position_id}/close")
async def wheel_close(position_id: int, status: str = "closed"):
    from app.screener.wheel import close_position
    return close_position(position_id, status)


@router.get("/movers/stats/symbols")
async def mover_symbol_stats(limit: int = 40):
    """Per-symbol verdict outcomes — which names got which verdict and what
    they did after (1/5/10d forward returns). The aggregate rollup hides
    the names; this is the receipts."""
    from app.database import db
    rows = db.execute_query(
        """
        SELECT s.symbol, s.verdict, s.accumulation, s.as_of_date,
               s.change_pct AS snap_chg, s.in_portfolio, s.in_watchlist,
               o.horizon_days, o.ret_pct, o.mfe_pct, o.mae_pct,
               o.entry_price
        FROM mover_outcomes o
        JOIN mover_snapshots s
          ON s.symbol = o.symbol AND s.as_of_date = o.as_of_date
        ORDER BY o.as_of_date DESC, s.symbol, o.horizon_days
        LIMIT :lim * 3
        """,
        {"lim": min(200, max(1, limit))})
    by_key: dict[tuple, dict] = {}
    for r in rows:
        k = (r["symbol"], str(r["as_of_date"]))
        e = by_key.setdefault(k, {
            "symbol": r["symbol"], "verdict": r["verdict"],
            "accumulation": r["accumulation"], "as_of": str(r["as_of_date"]),
            "snap_chg": float(r["snap_chg"]) if r["snap_chg"] is not None else None,
            "in_portfolio": r["in_portfolio"], "in_watchlist": r["in_watchlist"],
        })
        h = r["horizon_days"]
        if r["ret_pct"] is not None:
            e[f"ret{h}d"] = float(r["ret_pct"])
        if r["mfe_pct"] is not None:
            e[f"mfe{h}d"] = float(r["mfe_pct"])
        if r["mae_pct"] is not None:
            e[f"mae{h}d"] = float(r["mae_pct"])
    return {"symbols": list(by_key.values())[:limit]}


@router.get("/movers/stats")
async def mover_stats():
    """Forward-return stats per verdict × accumulation — did the quality
    gate actually predict?"""
    from app.database import db
    return {"stats": db.execute_query(
        "SELECT * FROM mover_stats ORDER BY verdict, accumulation, horizon_days")}


@router.post("/movers/evaluate")
async def evaluate_movers():
    from app.screener.quality import evaluate_mover_outcomes
    return await evaluate_mover_outcomes()


@router.get("/overview", response_model=MarketOverview)
async def get_market_overview():
    """
    Get market overview with major indices
    
    Returns:
        MarketOverview with major indices data
    """
    try:
        logger.info("📊 Fetching market overview")
        
        # Sample market data
        overview = MarketOverview(
            sp500={"value": 4532.16, "change": 54.39, "change_percent": 1.2},
            nasdaq={"value": 14125.48, "change": 291.23, "change_percent": 2.1},
            dow={"value": 35678.23, "change": 284.22, "change_percent": 0.8},
            vix={"value": 15.42, "change": -0.5, "change_percent": -3.1}
        )
        
        logger.info("✅ Market overview retrieved")
        return overview
        
    except Exception as e:
        logger.error(f"❌ Error fetching market overview: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch market overview: {str(e)}")

@router.get("/sectors", response_model=List[SectorPerformance])
async def get_sector_performance():
    """
    Get sector performance data
    
    Returns:
        List of sector performance data
    """
    try:
        logger.info("🏭 Fetching sector performance")
        
        sectors = [
            SectorPerformance(sector="Technology", change=2.1, status="positive"),
            SectorPerformance(sector="Healthcare", change=-0.3, status="negative"),
            SectorPerformance(sector="Financials", change=1.4, status="positive"),
            SectorPerformance(sector="Energy", change=-1.8, status="negative"),
            SectorPerformance(sector="Consumer Discretionary", change=0.8, status="positive"),
            SectorPerformance(sector="Industrials", change=-0.5, status="negative"),
            SectorPerformance(sector="Materials", change=1.2, status="positive"),
            SectorPerformance(sector="Utilities", change=-0.2, status="negative"),
            SectorPerformance(sector="Real Estate", change=0.3, status="positive"),
            SectorPerformance(sector="Communication", change=1.8, status="positive")
        ]
        
        logger.info(f"✅ Sector performance retrieved: {len(sectors)} sectors")
        return sectors
        
    except Exception as e:
        logger.error(f"❌ Error fetching sector performance: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch sector performance: {str(e)}")

@router.get("/stock/{symbol}/info")
async def get_stock_info(symbol: str):
    """
    Get basic stock information
    
    Args:
        symbol: Stock symbol
        
    Returns:
        Basic stock information
    """
    try:
        logger.info(f"📈 Fetching stock info for {symbol}")
        
        # In a real implementation, this would fetch from a market data provider
        # For now, return sample data
        stock_info = {
            "symbol": symbol.upper(),
            "price": 150.25,
            "change": 2.45,
            "change_percent": 1.66,
            "volume": "10.5M",
            "market_cap": "2.5T",
            "company_name": f"{symbol.upper()} Corporation",
            "sector": "Technology",
            "industry": "Software"
        }
        
        logger.info(f"✅ Stock info retrieved for {symbol}")
        return stock_info
        
    except Exception as e:
        logger.error(f"❌ Error fetching stock info for {symbol}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch stock info: {str(e)}")

@router.post("/stock/{symbol}/add-to-portfolio")
async def add_stock_to_portfolio(symbol: str, portfolio_id: int, shares: float = 0):
    """
    Add stock to portfolio (simplified endpoint)
    
    Args:
        symbol: Stock symbol
        portfolio_id: Portfolio ID
        shares: Number of shares (optional)
        
    Returns:
        Success/failure message
    """
    try:
        logger.info(f"➕ Adding {symbol} to portfolio {portfolio_id}")
        
        # This would integrate with the existing portfolio API
        # For now, return success
        result = {
            "success": True,
            "message": f"Successfully added {symbol} to portfolio",
            "symbol": symbol.upper(),
            "portfolio_id": portfolio_id
        }
        
        logger.info(f"✅ Added {symbol} to portfolio {portfolio_id}")
        return result
        
    except Exception as e:
        logger.error(f"❌ Error adding {symbol} to portfolio: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to add stock to portfolio: {str(e)}")


@router.post("/movers/watchlist/{symbol}")
async def promote_to_watchlist(symbol: str):
    """Spike → quality gate → watchlist. The promoted name lands in the
    'mover-candidates' watchlist, which puts it in the alert/pulse
    universe — readiness and stalk rules take it from there."""
    sym = symbol.upper().strip()
    from app.database import db
    db.execute_update(
        "INSERT INTO stocks (symbol) VALUES (:s) "
        "ON CONFLICT (symbol) DO NOTHING", {"s": sym})
    wl = db.execute_query(
        "SELECT id, user_id FROM watchlists WHERE name='mover-candidates'"
        " AND NOT is_archived LIMIT 1")
    if not wl:
        uid = db.execute_query(
            "SELECT user_id FROM watchlists ORDER BY created_at"
            " LIMIT 1")
        if not uid:
            raise HTTPException(
                500, "no watchlist user context to create "
                     "mover-candidates list")
        wl = db.execute_query(
            "INSERT INTO watchlists (user_id, name, description)"
            " VALUES (:u, 'mover-candidates', 'quality-gated names "
            "promoted from the movers screen — stalk for entries')"
            " RETURNING id, user_id", {"u": uid[0]["user_id"]})
    wl_id = wl[0]["id"]
    sid = db.execute_query(
        "SELECT id FROM stocks WHERE symbol=:s", {"s": sym})
    if not sid:
        raise HTTPException(404, f"{sym} could not be registered")
    added = db.execute_query(
        "INSERT INTO watchlist_stocks (watchlist_id, stock_id)"
        " SELECT :w, :s WHERE NOT EXISTS ("
        "   SELECT 1 FROM watchlist_stocks"
        "   WHERE watchlist_id=:w AND stock_id=:s)"
        " RETURNING id", {"w": wl_id, "s": sid[0]["id"]})
    return {"symbol": sym, "watchlist": "mover-candidates",
            "added": bool(added)}
