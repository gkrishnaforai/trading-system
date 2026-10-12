"""Sector candidate ranking — "the ~10 best stocks inside each sector right
now", ranked on industry-standard (CANSLIM/Minervini) fundamentals.

Pools are curated sector-leader lists — FMP's screener and ETF-holdings
endpoints are 403 on the current plan, so discovery is manual but the
ranking is fully computed: each candidate is scored on quarterly EPS growth,
revenue growth (validates the EPS isn't engineered), ROE, estimate-revision
direction (the measurable proxy for product-pipeline strength — analysts
price future products into estimates), fair-value upside, and technical
confirmation. Runs as a background job; ~150 symbols x 3 provider calls is
too heavy for a request.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from app.market_regime.rotation import SECTOR_NAMES, THEME_ETFS
from app.screener.quality import _quality_row

logger = logging.getLogger(__name__)

# Curated leader pools — liquid sector names + high-growth entrants. Ranking,
# not membership, does the work; refresh quarterly as leadership rotates.
SECTOR_POOLS: dict[str, list[str]] = {
    "XLK": ["AAPL", "MSFT", "NVDA", "AVGO", "ORCL", "CRM", "AMD", "PLTR",
            "CSCO", "ANET", "SNPS", "CDNS", "MRVL", "PANW"],
    "XLF": ["JPM", "V", "MA", "BAC", "GS", "MS", "WFC", "AXP", "BLK",
            "SPGI", "CME", "SCHW", "HOOD", "COIN"],
    "XLE": ["XOM", "CVX", "COP", "SLB", "EOG", "OXY", "MPC", "VLO",
            "PSX", "WMB", "KMI", "OKE"],
    "XLV": ["LLY", "UNH", "JNJ", "ABBV", "MRK", "TMO", "ISRG", "VRTX",
            "REGN", "AMGN", "SYK", "NVO", "PFE"],
    "XLY": ["AMZN", "TSLA", "HD", "MCD", "NKE", "SBUX", "LOW", "TJX",
            "BKNG", "CMG", "ORLY", "ROST"],
    "XLP": ["WMT", "COST", "PG", "KO", "PEP", "PM", "MO", "CL",
            "MDLZ", "EL", "TGT", "KR"],
    "XLI": ["GE", "CAT", "RTX", "HON", "BA", "UPS", "LMT", "DE",
            "UNP", "ETN", "PH", "ROK"],
    "XLU": ["NEE", "SO", "DUK", "CEG", "VST", "SRE", "AEP", "EXC",
            "D", "PCG", "PEG", "ED"],
    "XLRE": ["PLD", "AMT", "EQIX", "SPG", "CCI", "O", "PSA", "WELL",
             "DLR", "EXR", "VICI", "SBAC"],
    "XLB": ["LIN", "SHW", "APD", "FCX", "NEM", "NUE", "ECL", "DD",
            "CTVA", "DOW", "PPG", "ALB"],
    "XLC": ["GOOGL", "META", "NFLX", "DIS", "CMCSA", "VZ", "T", "TMUS",
            "EA", "TTWO", "RBLX", "SNAP"],
    # themes — finer grain where the funding question lives
    "SMH": ["NVDA", "TSM", "AVGO", "AMD", "QCOM", "TXN", "INTC", "MU",
            "AMAT", "LRCX", "KLAC", "ARM", "MRVL", "ALAB"],
    "IGV": ["MSFT", "ORCL", "CRM", "NOW", "ADBE", "PLTR", "SNPS", "CDNS",
            "INTU", "PANW", "CRWD", "DDOG", "NET", "FTNT"],
    "XBI": ["VRTX", "REGN", "AMGN", "GILD", "BIIB", "INCY", "MRNA",
            "NBIX", "ALNY", "BMRN", "EXEL", "UTHR"],
    "KRE": ["WAL", "ZION", "CMA", "FITB", "HBAN", "RF", "KEY", "CFG",
            "MTB", "PNFP", "VLY", "ONB"],
    "ITA": ["GE", "RTX", "LMT", "NOC", "GD", "BA", "TDG", "HWM",
            "LHX", "TXT", "RKLB", "AXON"],
    "ARKK": ["TSLA", "ROKU", "COIN", "CRSP", "SHOP", "PLTR", "HOOD",
             "PATH", "RKLB", "EXAS", "SQ", "U"],
    "TAN": ["ENPH", "FSLR", "SEDG", "NXT", "ARRY", "RUN", "CSIQ",
            "JKS", "DQ", "MAXN", "SHLS", "SPWR"],
    "XRT": ["AMZN", "TJX", "ROST", "ORLY", "AZO", "BURL", "FIVE",
            "GPS", "BBY", "DKS", "WSM", "ULTA"],
}

TOP_N = 10

# --- Thematic baskets — cross-sector, MSCI "Relevance Score"-style: -------
# tier = economic-linkage proxy (we can't measure revenue-exposure %, so
# purity is curated): 1 = pure play / flagship product, 2 = major platform
# beneficiary, 3 = enabler/infrastructure. angle = the product evidence.
THEME_BASKETS: dict[str, dict] = {
    "agentic_ai": {
        "name": "Agentic AI",
        "thesis": "who wins the agent layer — platforms shipping agent "
                  "products + the compute/data layer underneath",
        "members": {
            "CRM":  (1, "Agentforce — flagship enterprise agent platform"),
            "NOW":  (1, "ServiceNow AI agents embedded in IT workflows"),
            "PLTR": (1, "AIP — ontology-driven operational agents"),
            "PATH": (1, "UiPath — RPA pivoting to agentic automation"),
            "AI":   (1, "C3.ai — enterprise agentic apps, small pure play"),
            "SOUN": (1, "voice agents — restaurants, auto, healthcare"),
            "MSFT": (2, "Copilot agents + AI Foundry; 400M-seat distribution"),
            "GOOGL": (2, "Gemini + Agentspace; frontier model + ads/cloud base"),
            "META": (2, "Llama open weights + consumer-scale distribution"),
            "AMZN": (2, "Bedrock Agents on AWS enterprise base"),
            "ORCL": (2, "agents embedded in Fusion/NetSuite ERP base"),
            "NVDA": (3, "agent compute layer — NIM microservices + GPUs"),
            "AVGO": (3, "custom AI silicon + networking for agent clusters"),
            "ANET": (3, "AI-datacenter networking"),
            "SNOW": (3, "Cortex agents on the enterprise data layer"),
            "MDB":  (3, "operational DB agents read/write"),
            "PANW": (3, "agentic SOC automation"),
            "CRWD": (3, "Charlotte AI — agentic security ops"),
        },
    },
    "tokenization": {
        "name": "Tokenization / On-chain Finance",
        "thesis": "who grows as real-world assets move on-chain — issuers, "
                  "rails, and institutional infrastructure",
        "members": {
            "CRCL": (1, "USDC issuer — the settlement asset of tokenization"),
            "COIN": (1, "exchange + institutional custody + Base L2"),
            "HOOD": (1, "tokenized stocks live in EU; own L2 roadmap"),
            "GLXY": (1, "institutional digital-asset merchant bank"),
            "SOFI": (1, "retail crypto + blockchain remittances relaunched"),
            "BLK":  (2, "BUIDL — largest tokenized fund; unmatched distribution"),
            "JPM":  (2, "Kinexys — $1B+ daily on-chain settlement"),
            "BEN":  (2, "Franklin OnChain funds — early institutional mover"),
            "V":    (2, "stablecoin settlement on card rails"),
            "MA":   (2, "Multi-Token Network"),
            "PYPL": (2, "PYUSD stablecoin"),
            "FI":   (2, "FIUSD stablecoin for merchant settlement"),
            "IBKR": (2, "24/7 tokenized trading + crypto access"),
            "ICE":  (2, "market infrastructure"),
            "CME":  (2, "regulated crypto derivatives"),
            "IREN": (3, "miner pivoting to AI/HPC — crypto beta"),
            "MARA": (3, "BTC treasury beta"),
            "CLSK": (3, "miner/HPC beta"),
        },
    },
}

_PURITY_PTS = {1: 40, 2: 25, 3: 12}   # relevance weight — the theme linkage


def _theme_score(fund_score: float, tier: int,
                 rd_intensity: Optional[float]) -> tuple[float, list[str]]:
    """0.6 × fundamentals + purity points + R&D-intensity bonus — the theme
    analogue of MSCI's relevance score. Pure plays outrank diversified
    giants when fundamentals are comparable."""
    score = min(60.0, fund_score * 0.6) + _PURITY_PTS.get(tier, 10)
    notes = []
    if rd_intensity is not None:
        if rd_intensity >= 0.12:
            score += 10; notes.append(f"R&D {rd_intensity * 100:.0f}% of revenue")
        elif rd_intensity >= 0.06:
            score += 5; notes.append(f"R&D {rd_intensity * 100:.0f}% of revenue")
    return max(0.0, min(100.0, score)), notes


async def _rd_intensity(fmp, symbol: str) -> Optional[float]:
    """Annual R&D ÷ revenue — the measurable 'upstream activity' MSCI counts."""
    try:
        rows = await asyncio.to_thread(fmp.get_income_statement, symbol, "annual")
        if not rows:
            return None
        rd = rows[0].get("researchAndDevelopmentExpenses")
        rev = rows[0].get("revenue")
        if rd and rev:
            return rd / rev
    except Exception:
        pass
    return None


def _rank_score(row: dict[str, Any], ov: dict) -> tuple[float, list[str]]:
    """CANSLIM-weighted score 0-100 + the 'why' bullets.

    Earnings growth dominates (C+A factors); revenue confirms it isn't
    engineered; ROE proves capital efficiency; estimate revisions are the
    product-pipeline proxy; FV upside + trend add valuation/timing context.
    """
    score, why = 0.0, []
    eps, rev, roe = row.get("eps_growth"), row.get("rev_growth"), row.get("roe")

    if eps is not None and eps >= 25:
        score += 30; why.append(f"EPS +{eps:.0f}% QoQ")
    elif eps is not None and eps >= 15:
        score += 20; why.append(f"EPS +{eps:.0f}%")
    elif eps is not None and eps > 0:
        score += 10
    elif eps is not None and eps < 0:
        score -= 10; why.append(f"EPS {eps:.0f}% — shrinking")

    if rev is not None and rev >= 25:
        score += 20; why.append(f"rev +{rev:.0f}% — real demand")
    elif rev is not None and rev >= 10:
        score += 10; why.append(f"rev +{rev:.0f}%")
    elif rev is not None and rev <= 0:
        score -= 5

    # Acceleration — growth RATE rising QoQ on both lines = early inflection,
    # the "find it before institutions do" signature. Worth more than level.
    if row.get("accelerating"):
        score += 8
        ea, ra = row.get("eps_accel"), row.get("rev_accel")
        why.append(f"📈 accelerating (EPS {ea:+.0f}pp · rev {ra:+.0f}pp QoQ)")
    elif (row.get("eps_accel") or 0) < -10 and (row.get("rev_accel") or 0) < 0:
        score -= 6; why.append("growth decelerating")

    if roe is not None and roe >= 15:
        score += 15; why.append(f"ROE {roe:.0f}%")
    elif roe is not None and roe < 0:
        score -= 10; why.append("negative ROE — cash burn")

    delta = ov.get("eps_delta_pct")
    if delta is not None and delta > 0:
        score += 10; why.append(f"estimates revised +{delta:.0f}%")
    elif delta is not None and delta <= -5:
        score -= 10; why.append(f"estimates cut {delta:.0f}%")

    fv, price = ov.get("fair_value"), row.get("price")
    if fv and price:
        upside = fv / price - 1
        if upside >= 0.15:
            score += 10; why.append(f"FV upside +{upside * 100:.0f}%")
        elif upside <= -0.10:
            score -= 10; why.append(f"{-upside * 100:.0f}% over fair value")

    vs50, dd20 = row.get("vs_sma50"), row.get("dd20_pct")
    if vs50 is not None and vs50 > 0:
        score += 10; why.append("above SMA50")
    if dd20 is not None and dd20 >= -5:
        score += 5; why.append("near 20d high")
    if str(ov.get("catalyst_direction") or "").upper() == "POSITIVE":
        score += 5; why.append("positive catalyst")

    return max(0.0, min(100.0, score)), why


_cand_state: dict[str, Any] = {
    "running": False, "last_run_at": None, "results": None, "error": None,
}


def candidates_status() -> dict[str, Any]:
    return {
        "running": _cand_state["running"],
        "last_run_at": _cand_state["last_run_at"],
        "error": _cand_state["error"],
    }


def candidates_results() -> dict[str, Any]:
    res = _cand_state["results"]
    if res is None:
        # restart fallback — the last persisted run
        try:
            from app.database import db
            row = db.execute_query(
                "SELECT ran_at, scored, results FROM sector_candidate_runs "
                "ORDER BY ran_at DESC LIMIT 1")
            if row:
                res = row[0]["results"] or {}
                res["as_of"] = str(row[0]["ran_at"])
                _cand_state["results"] = res
        except Exception:
            res = None
    res = res or {"sectors": {}}
    return {**res, "as_of": res.get("as_of") or _cand_state["last_run_at"]}


def theme_catalysts(days: int = 7) -> dict[str, Any]:
    """Positive catalysts + EPS events for theme members — a filtered lens on
    alert_items. The Alerts page stays the canonical all-symbol feed; this
    answers 'which name in this theme just got fundamentally better'."""
    from app.database import db
    members = {s: (k, tier, angle)
               for k, t in THEME_BASKETS.items()
               for s, (tier, angle) in t["members"].items()}
    try:
        rows = db.execute_query(
            """
            SELECT symbol, event_type, direction, materiality, title,
                   detail, created_at
            FROM alert_items
            WHERE symbol = ANY(:symbols)
              AND direction = 'POSITIVE'
              AND event_type IN ('catalyst', 'eps_revision', 'mover',
                                 'breakout_trigger')
              AND created_at >= now() - make_interval(days => :days)
            ORDER BY created_at DESC
            """,
            {"symbols": list(members), "days": days},
        )
    except Exception as exc:
        logger.debug("theme catalysts query failed: %s", exc)
        return {"themes": {}}
    out: dict[str, list] = {}
    for r in rows:
        theme = members.get(r["symbol"].upper())
        if not theme:
            continue
        det = r.get("detail") or {}
        out.setdefault(theme[0], []).append({
            "symbol": r["symbol"],
            "angle": theme[2],
            "event": r["event_type"],
            "materiality": r["materiality"],
            "title": r["title"],
            "eps_surprise_pct": det.get("eps_surprise_pct"),
            "catalyst_type": det.get("catalyst_type"),
            "reaction": det.get("reaction_state"),
            "when": str(r["created_at"]),
        })
    return {"themes": out, "days": days}


def _persist_results(results: dict):
    """Persist the run blob + normalized per-symbol ranks (the versioned
    history that makes rank movement between runs queryable).
    Returns the run_id so streak history can hang off the same run."""
    try:
        import json
        from app.database import db
        row = db.execute_query(
            "INSERT INTO sector_candidate_runs (scored, results) "
            "VALUES (:scored, :res) RETURNING id",
            {"scored": results.get("scored"), "res": json.dumps(results)},
        )
        run_id = row[0]["id"] if row else None
        if not run_id:
            return None
        for basket, kind, cands in (
            [(e, "sector", s["candidates"])
             for e, s in (results.get("sectors") or {}).items()]
            + [(k, "theme", t["candidates"])
               for k, t in (results.get("themes") or {}).items()]
        ):
            for i, c in enumerate(cands):
                try:
                    db.execute_update(
                        """
                        INSERT INTO candidate_ranks
                            (run_id, basket, basket_kind, symbol, rank,
                             score, fund_score, tier, verdict, eps_growth,
                             rev_growth, roe, rd_intensity, price, dd20_pct)
                        VALUES (:run, :basket, :kind, :sym, :rank, :score,
                                :fund, :tier, :verdict, :eps, :rev, :roe,
                                :rd, :price, :dd20)
                        """,
                        {"run": run_id, "basket": basket, "kind": kind,
                         "sym": c["symbol"], "rank": i + 1,
                         "score": c.get("theme_score", c.get("rank_score")),
                         "fund": c.get("fund_score", c.get("rank_score")),
                         "tier": c.get("purity"), "verdict": c.get("verdict"),
                         "eps": c.get("eps_growth"), "rev": c.get("rev_growth"),
                         "roe": c.get("roe"), "rd": c.get("rd_intensity"),
                         "price": c.get("price"), "dd20": c.get("dd20_pct")},
                    )
                except Exception as exc:
                    logger.debug("rank persist failed %s/%s: %s",
                                 basket, c["symbol"], exc)
        return run_id
    except Exception as exc:
        logger.debug("sector candidates persist failed: %s", exc)
        return None


def _persist_streaks(run_id, rows: dict) -> None:
    """Snapshot growth streaks for every scored symbol — the history that
    lets the API detect streak breaks (was accelerating, now not)."""
    if not run_id:
        return
    try:
        from app.database import db
        for sym, r in rows.items():
            try:
                db.execute_update(
                    """
                    INSERT INTO accel_watch
                        (run_id, symbol, rev_streak, eps_streak, rev_decel,
                         eps_decel, rev_path, eps_path, verdict, price,
                         in_portfolio, in_watchlist)
                    VALUES (:run, :sym, :rs, :es, :rd, :ed, :rp, :ep,
                            :v, :p, :port, :watch)
                    """,
                    {"run": run_id, "sym": sym,
                     "rs": r.get("rev_streak") or 0,
                     "es": r.get("eps_streak") or 0,
                     "rd": r.get("rev_decel") or 0,
                     "ed": r.get("eps_decel") or 0,
                     "rp": r.get("rev_path") or [],
                     "ep": r.get("eps_path") or [],
                     "v": r.get("verdict"), "p": r.get("price"),
                     "port": bool(r.get("in_portfolio")),
                     "watch": bool(r.get("in_watchlist"))})
            except Exception as exc:
                logger.debug("streak persist failed %s: %s", sym, exc)
    except Exception as exc:
        logger.debug("accel watch persist failed: %s", exc)


def acceleration_watch() -> dict[str, Any]:
    """The acceleration board — three reads off the two latest snapshots:
    basket (either streak >=2), deceleration watch on held names, and
    streak-broken (was accelerating last run, isn't now = thesis dead)."""
    empty = {"basket": [], "decelerating": [], "broken": [], "as_of": None}
    try:
        from app.database import db
        runs = db.execute_query(
            "SELECT DISTINCT run_id FROM accel_watch "
            "ORDER BY run_id DESC LIMIT 2")
        if not runs:
            return empty
        ids = [r["run_id"] for r in runs]
        rows = db.execute_query(
            """SELECT a.*, r.ran_at FROM accel_watch a
               JOIN sector_candidate_runs r ON r.id = a.run_id
               WHERE a.run_id = ANY(:ids)""",
            {"ids": ids})
    except Exception as exc:
        logger.debug("accel watch read failed: %s", exc)
        return empty
    cur_id = ids[0]
    prev_id = ids[1] if len(ids) > 1 else None
    as_of = None
    cur, prev = [], {}
    for r in rows:
        if r["run_id"] == cur_id:
            as_of = str(r["ran_at"])
            cur.append(r)
        else:
            prev[r["symbol"]] = r

    def _shape(r):
        return {
            "symbol": r["symbol"], "rev_streak": r["rev_streak"],
            "eps_streak": r["eps_streak"],
            "rev_decel": r["rev_decel"], "eps_decel": r["eps_decel"],
            "rev_path": [float(v) for v in (r.get("rev_path") or [])],
            "eps_path": [float(v) for v in (r.get("eps_path") or [])],
            "verdict": r.get("verdict"), "price": float(r["price"])
            if r.get("price") else None,
            "in_portfolio": r.get("in_portfolio"),
            "in_watchlist": r.get("in_watchlist"),
        }

    basket = [_shape(r) for r in cur
              if (r["rev_streak"] or 0) >= 2 or (r["eps_streak"] or 0) >= 2]
    basket.sort(key=lambda r: -max(r["rev_streak"], r["eps_streak"]))
    decel = [_shape(r) for r in cur if r.get("in_portfolio")
             and ((r["rev_decel"] or 0) >= 2 or (r["eps_decel"] or 0) >= 2)]
    broken = [_shape(r) for r in cur
              if max(r["rev_streak"] or 0, r["eps_streak"] or 0) < 2
              and max((prev.get(r["symbol"]) or {}).get("rev_streak") or 0,
                      (prev.get(r["symbol"]) or {}).get("eps_streak") or 0)
              >= 2]
    return {"basket": basket, "decelerating": decel, "broken": broken,
            "as_of": as_of, "scored": len(cur)}


def rank_moves() -> dict[str, Any]:
    """Rank deltas between the two most recent runs — 'who's climbing'
    per basket. NEW = entered the list, — = held, dropped names listed."""
    try:
        from app.database import db
        runs = db.execute_query(
            "SELECT id, ran_at FROM sector_candidate_runs "
            "ORDER BY ran_at DESC LIMIT 2")
        if not runs:
            return {"moves": {}}
        ids = [r["id"] for r in runs]
        rows = db.execute_query(
            "SELECT run_id, basket, basket_kind, symbol, rank, score "
            "FROM candidate_ranks WHERE run_id = ANY(:ids)",
            {"ids": ids},
        )
    except Exception as exc:
        logger.debug("rank moves query failed: %s", exc)
        return {"moves": {}}
    cur_id, prev_id = ids[0], ids[1] if len(ids) > 1 else None
    cur: dict[str, dict] = {}
    prev: dict[str, dict] = {}
    for r in rows:
        slot = cur if r["run_id"] == cur_id else prev
        slot.setdefault(r["basket"], {})[r["symbol"]] = {
            "rank": r["rank"], "score": float(r["score"]) if r["score"] else None,
            "kind": r["basket_kind"],
        }
    moves: dict[str, list] = {}
    for basket, syms in cur.items():
        p = prev.get(basket) or {}
        entries = []
        for sym, c in syms.items():
            old = p.get(sym)
            entries.append({
                "symbol": sym, "rank": c["rank"], "score": c["score"],
                "prev_rank": old["rank"] if old else None,
                "delta": (old["rank"] - c["rank"]) if old else None,
                "status": "held" if old else "NEW",
            })
        for sym in p:
            if sym not in syms:
                entries.append({"symbol": sym, "rank": None,
                                "prev_rank": p[sym]["rank"], "delta": None,
                                "status": "OUT"})
        entries.sort(key=lambda e: (e["rank"] or 99))
        moves[basket] = entries
    return {"moves": moves,
            "current_run": str(runs[0]["ran_at"]),
            "previous_run": str(runs[1]["ran_at"]) if len(runs) > 1 else None}


async def run_candidates_job() -> dict[str, Any]:
    """Rank each pool; keep the top 10 per sector/theme."""
    if _cand_state["running"]:
        return {"status": "already_running"}
    _cand_state["running"] = True
    _cand_state["error"] = None
    try:
        from app.alerts import scanner as alert_scanner
        from app.market_data import MarketDataService
        from app.providers.financial_modeling_prep.client import EnhancedFMPClient
        from app.symbol_overlay import persisted_overlay

        svc, fmp = MarketDataService(), EnhancedFMPClient.from_settings()
        uni = alert_scanner.universe()
        sector_syms = {s for pool in SECTOR_POOLS.values() for s in pool}
        theme_syms = {s for t in THEME_BASKETS.values() for s in t["members"]}
        all_syms = sorted(sector_syms | theme_syms)
        overlay = await asyncio.to_thread(persisted_overlay, all_syms)

        sem = asyncio.Semaphore(8)

        async def _one(sym: str, need_rd: bool):
            async with sem:
                try:
                    row = await _quality_row(
                        svc, fmp, sym, uni, set(), overlay.get(sym, {}), None)
                    if row and need_rd:
                        row["rd_intensity"] = await _rd_intensity(fmp, sym)
                    return row
                except Exception as exc:
                    logger.debug("candidate fetch failed %s: %s", sym, exc)
                    return None

        rows = {r["symbol"]: r for r in await asyncio.gather(
            *(_one(s, s in theme_syms) for s in all_syms)) if r}

        sectors: dict[str, dict] = {}
        names = {**SECTOR_NAMES, **THEME_ETFS}
        for etf, pool in SECTOR_POOLS.items():
            ranked = []
            for sym in pool:
                r = rows.get(sym)
                if not r:
                    continue
                score, why = _rank_score(r, overlay.get(sym, {}))
                ranked.append({**r, "rank_score": score, "why": why})
            ranked.sort(key=lambda r: -r["rank_score"])
            sectors[etf] = {
                "name": names.get(etf, etf),
                "candidates": ranked[:TOP_N],
                "pool_size": len(pool),
            }

        themes: dict[str, dict] = {}
        for key, tb in THEME_BASKETS.items():
            ranked = []
            for sym, (tier, angle) in tb["members"].items():
                r = rows.get(sym)
                if not r:
                    continue
                fund, why = _rank_score(r, overlay.get(sym, {}))
                tscore, tnotes = _theme_score(fund, tier, r.get("rd_intensity"))
                ranked.append({
                    **r, "fund_score": fund, "theme_score": tscore,
                    "purity": tier, "angle": angle,
                    "why": (tnotes + why)[:4],
                })
            ranked.sort(key=lambda r: -r["theme_score"])
            themes[key] = {
                "name": tb["name"], "thesis": tb["thesis"],
                "candidates": ranked,
            }

        _cand_state["results"] = {
            "sectors": sectors,
            "themes": themes,
            "scored": len(rows),
            "note": "Pools are curated leader lists — ranking is computed "
                    "(EPS/rev/ROE/revisions/FV/trend). Product pipeline is "
                    "proxied by revenue growth + estimate revisions.",
        }
        _run_id = await asyncio.to_thread(
            _persist_results, _cand_state["results"])
        await asyncio.to_thread(_persist_streaks, _run_id, rows)
        return {"status": "completed", "scored": len(rows)}
    except Exception as exc:
        logger.error("sector candidates failed: %s", exc)
        _cand_state["error"] = str(exc)
        return {"status": "error", "error": str(exc)}
    finally:
        _cand_state["running"] = False
        _cand_state["last_run_at"] = datetime.now(timezone.utc).isoformat()
