"""5x Scout — small-cap multibagger hunter. Separate engine from
Rule Breakers: RB catches names ALREADY accelerating (2x zone,
$1-500B); this finds the PLTR-2022 fingerprint BEFORE the repricing
in the $1-30B zone:

  PLTR Q3 2022 told the story: rev +22% (moderate) BUT US commercial
  +53-120% YoY hidden inside, GM 80%, $2.4B cash / no debt, customer
  count +66%, price ~-80% from ATH. A moderate-looking total hid a
  ramping engine, a fortress balance sheet let it survive the winter,
  and beaten-down price meant the market hadn't paid for it yet.

Quant gates (the fingerprint):
  mcap $1-30B      — the 5x compounding zone (hard boundary)
  rev>=15% YoY     — growing, but pre-inflection bar (not 25%)
  GM>=40%          — platform economics / scalability
  net cash         — cash > debt: survives to the S-curve
  profit path      — op margin > 0 or FCF > 0: self-funding

Score components add the asymmetric-entry and hidden-engine legs:
size sweet spot, rev acceleration streak, hidden segment >40% YoY
(the masked engine), drawdown-from-high (early, not late).

Tiers:  watch → inflecting (>=4 gates) → runner (all gates + hidden
        engine or agent-proven thesis). Checklist research reuses the
        same agent contract as Rule Breakers (engine-agnostic
        secular-engine scoring).

Discovery: FMP /company-screener gives the whole $1-30B pool
(~2100 names) server-side; we sweep it in slices (light eval:
income+profile+quote, 3 calls) with a persisted cursor; names
passing the light pre-gates get a deep eval (adds balance sheet +
cash flow + segmentation) and auto-join as 'watch'/'inflecting'.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import date, datetime, timezone
from typing import Any, Optional

from app.screener.rule_breakers import _segments

logger = logging.getLogger(__name__)

REV_MIN = 0.15            # pre-inflection bar — PLTR was +22%
GM_MIN = 0.40             # platform economics
MCAP_MIN, MCAP_MAX = 1e9, 30e9     # the 5x zone
HIDDEN_ENGINE_YOY = 0.40  # a segment quietly compounding >40%
CHECKLIST_MIN = 4

DISCOVERY_SLICE = 350     # light evals per discovery run (~1k calls)

_state: dict[str, Any] = {
    "running": False, "last_run_at": None, "evaluated": 0,
    "error": None}


def sc_status() -> dict[str, Any]:
    return dict(_state)


# --- data -------------------------------------------------------------


async def _eval_symbol(fmp, sym: str, deep: bool = False) -> Optional[dict]:
    """Light (3 calls): income(9q) + profile + quote — computes mcap,
    rev growth/streak, margins, drawdown. Deep adds balance-sheet,
    cash-flow, product-segmentation — net cash, FCF, hidden engine."""
    reqs = [
        asyncio.to_thread(fmp._make_request, "/income-statement",
                          {"symbol": sym, "period": "quarter",
                           "limit": 9}),
        asyncio.to_thread(fmp._make_request, "/profile",
                          {"symbol": sym}),
        asyncio.to_thread(fmp._make_request, "/quote",
                          {"symbol": sym})]
    if deep:
        reqs += [
            asyncio.to_thread(fmp._make_request,
                              "/balance-sheet-statement",
                              {"symbol": sym, "period": "quarter",
                               "limit": 1}),
            asyncio.to_thread(fmp._make_request,
                              "/cash-flow-statement",
                              {"symbol": sym, "period": "quarter",
                               "limit": 1}),
            asyncio.to_thread(fmp._make_request,
                              "/revenue-product-segmentation",
                              {"symbol": sym})]
    try:
        res = await asyncio.gather(*reqs)
        income, profile, quote = res[0], res[1], res[2]
        bs, cash, seg_rows = (res[3], res[4], res[5]) if deep \
            else (None, None, None)
    except Exception as exc:
        logger.debug("sc eval %s failed: %s", sym, exc)
        return None

    inc = income or []
    q = inc[0] if inc else {}
    p = (profile[0] if isinstance(profile, list) and profile
         else profile) or {}
    qt = (quote[0] if isinstance(quote, list) and quote
          else quote) or {}

    def _yoy(field: str) -> Optional[float]:
        cur, prev = q.get(field), (inc[4] if len(inc) > 4 else {})
        prev = prev.get(field)
        return (cur / prev - 1) if cur is not None and prev else None

    # consecutive quarters of ACCELERATING YoY revenue growth
    streak = 0
    for i in range(min(4, len(inc) - 5)):
        a, b = inc[i], inc[i + 1]
        ya, yb = inc[i + 4], inc[i + 5]
        if not all(x.get("revenue") for x in (a, b, ya, yb)):
            break
        if (a["revenue"] / ya["revenue"] - 1) > \
                (b["revenue"] / yb["revenue"] - 1):
            streak += 1
        else:
            break

    qy = inc[4] if len(inc) > 4 else {}
    gm = (q.get("grossProfit") / q["revenue"]
          if q.get("grossProfit") and q.get("revenue") else None)
    gm_prev = (qy.get("grossProfit") / qy["revenue"]
               if qy.get("grossProfit") and qy.get("revenue") else None)
    opm = (q.get("operatingIncome") / q["revenue"]
           if q.get("operatingIncome") is not None and q.get("revenue")
           else None)

    year_high = qt.get("yearHigh")
    price = qt.get("price") or p.get("price")
    dd52w = (price / year_high - 1) if price and year_high else None
    sma200 = qt.get("priceAvg200")
    vs_sma200 = (price / sma200 - 1) if price and sma200 else None

    m: dict[str, Any] = {
        "symbol": sym, "rev_growth": _yoy("revenue"),
        "eps_growth": _yoy("netIncome"), "rev_streak": streak,
        "gross_margin": gm, "gross_margin_prev": gm_prev,
        "op_margin": opm, "market_cap": p.get("marketCap"),
        "price": price, "dd52w": dd52w, "vs_sma200": vs_sma200}

    if deep:
        b = (bs[0] if isinstance(bs, list) and bs else bs) or {}
        c = (cash[0] if isinstance(cash, list) and cash else cash) or {}
        m["cash"] = ((b.get("cashAndCashEquivalents") or 0)
                     + (b.get("shortTermInvestments") or 0)) or None
        m["total_debt"] = ((b.get("shortTermDebt") or 0)
                           + (b.get("longTermDebt") or 0)) or None
        if m["rev_growth"] is not None:
            fcf = ((c.get("operatingCashFlow") or 0)
                   - abs(c.get("capitalExpenditure") or 0))
            rev = q.get("revenue")
            m["fcf_margin"] = fcf / rev if rev else None
        m["segments"] = _segments(seg_rows, q.get("revenue"))
    return m


# --- gates + score ------------------------------------------------------


def _gates(m: dict) -> dict[str, bool]:
    rev, gm, mcap = (m.get("rev_growth"), m.get("gross_margin"),
                     m.get("market_cap"))
    cash, debt = m.get("cash"), m.get("total_debt")
    opm, fcf = m.get("op_margin"), m.get("fcf_margin")
    return {
        "mcap $1-30B": bool(mcap and MCAP_MIN <= mcap <= MCAP_MAX),
        "rev>=15%": bool(rev is not None and rev >= REV_MIN),
        "GM>=40%": bool(gm is not None and gm >= GM_MIN),
        "net cash": bool(cash is not None and debt is not None
                         and cash > debt),
        "profit path": bool((opm is not None and opm > 0)
                            or (fcf is not None and fcf > 0)),
    }


def _light_gates(m: dict) -> int:
    """Discovery pre-filter on the 3-call eval — mcap + rev + GM +
    op-margin proxy; net-cash/FCF need the deep pass."""
    return sum([
        bool(m.get("market_cap")
             and MCAP_MIN <= m["market_cap"] <= MCAP_MAX),
        bool(m.get("rev_growth") is not None
             and m["rev_growth"] >= REV_MIN),
        bool(m.get("gross_margin") is not None
             and m["gross_margin"] >= GM_MIN),
        bool(m.get("op_margin") is not None and m["op_margin"] > -0.05)])


def _hidden_engine(segments: dict) -> dict:
    """The masked-engine detector — reported product lines growing
    >40% YoY. PLTR's US commercial +53-120% while total showed +22%."""
    return {n: {"yoy": s["yoy"], "share": s.get("share")}
            for n, s in (segments or {}).items()
            if s.get("yoy") is not None and s["yoy"] >= HIDDEN_ENGINE_YOY}


def _score(m: dict, cl: dict, hidden: dict) -> float:
    """0-100 multibagger composite. Sweet spots:
    size (15) + growth (25) + platform (14) + fortress (10)
    + hidden engine (17) + early-not-late (13) + checklist bonus."""
    s = 0.0
    mc = m.get("market_cap") or 0
    if MCAP_MIN <= mc <= 10e9:
        s += 15          # the sweet spot — 5x from $3B needs only $15B
    elif mc <= MCAP_MAX:
        s += 8
    rev = m.get("rev_growth") or 0
    s += 15 if rev >= 0.50 else 12 if rev >= 0.25 else 8 if rev >= 0.15 else 0
    s += min(10, (m.get("rev_streak") or 0) * 3)      # acceleration
    gm = m.get("gross_margin") or 0
    s += 10 if gm >= 0.60 else 6 if gm >= 0.40 else 0
    if m.get("gross_margin_prev") and gm and gm > m["gross_margin_prev"]:
        s += 4
    if m.get("cash") is not None and m.get("total_debt") is not None \
            and m["cash"] > m["total_debt"]:
        s += 10                                       # fortress
    if len(hidden) >= 2:
        s += 17                                       # multiple engines
    elif hidden:
        s += 12                                       # one hidden engine
    dd = m.get("dd52w")
    if dd is not None:
        s += 10 if dd <= -0.30 else 5 if dd <= -0.15 else 0
    if (m.get("vs_sma200") or 0) < 0:
        s += 3                                        # still early
    s += min(6, (sum(1 for k in ("tam", "moat", "vectors", "optionality",
                                "proven") if cl.get(k))))
    return round(min(100.0, s), 1)


def _letter(score: float) -> str:
    return ("A+" if score >= 85 else "A" if score >= 75
            else "B" if score >= 60 else "C" if score >= 45 else "D")


def _kv_get(key: str) -> Optional[str]:
    from app.database import db
    rows = db.execute_query(
        "SELECT value FROM rb_state WHERE key=:k",
        {"k": "sc_" + key})
    return rows[0]["value"] if rows else None


def _kv_set(key: str, value: str) -> None:
    from app.database import db
    db.execute_update(
        "INSERT INTO rb_state (key, value) VALUES (:k,:v) "
        "ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value",
        {"k": "sc_" + key, "v": value})


def _pool() -> list[str]:
    """The $1-30B actively-trading NASDAQ/NYSE universe — cached a
    week in rb_state; ~2100 symbols, one provider call."""
    cached = _kv_get("pool")
    if cached:
        try:
            d = json.loads(cached)
            if (date.today()
                    - date.fromisoformat(d["fetched"])).days < 7:
                return d["symbols"]
        except (ValueError, KeyError, TypeError):
            pass
    from app.providers.financial_modeling_prep.client import (
        EnhancedFMPClient)
    fmp = EnhancedFMPClient.from_settings()
    rows = fmp._make_request(
        "/company-screener",
        {"marketCapMoreThan": int(MCAP_MIN),
         "marketCapLowerThan": int(MCAP_MAX),
         "isEtf": "false", "isFund": "false",
         "isActivelyTrading": "true",
         "exchange": "NASDAQ,NYSE", "limit": 5000}) or []
    syms = [r["symbol"] for r in rows if r.get("symbol")]
    _kv_set("pool", json.dumps(
        {"fetched": date.today().isoformat(), "symbols": syms}))
    return syms


# --- persistence ---------------------------------------------------------


def upsert_member(symbol: str, tier: str = "watch",
                  checklist: Optional[dict] = None) -> dict:
    from app.database import db
    db.execute_update(
        """
        INSERT INTO smallcap_members (symbol, tier, checklist)
        VALUES (:s, :t, CAST(:c AS jsonb))
        ON CONFLICT (symbol) DO UPDATE SET
            tier = EXCLUDED.tier,
            checklist = smallcap_members.checklist || EXCLUDED.checklist,
            promoted_at = CASE WHEN EXCLUDED.tier
                          <> smallcap_members.tier
                          THEN now() ELSE smallcap_members.promoted_at END
        """,
        {"s": symbol.upper(), "t": tier,
         "c": json.dumps(checklist or {})})
    return {"symbol": symbol.upper(), "tier": tier}


def remove_member(symbol: str) -> dict:
    from app.database import db
    db.execute_update(
        "DELETE FROM smallcap_members WHERE symbol=:s",
        {"s": symbol.upper()})
    return {"removed": symbol.upper()}


# --- eval loop ------------------------------------------------------------


async def run_smallcap(discover: bool = False) -> dict[str, Any]:
    """Deep-eval all members (gates + hidden engine + score + snapshot);
    tier transitions and thesis-breaks alert. With `discover`, sweep a
    slice of the $1-30B pool: light eval → deep eval qualifiers →
    auto-add. Auto-added names drop when gates collapse; manual adds
    never do."""
    from app.alerts import scanner as alert_scanner
    from app.alerts.models import AlertItem
    from app.database import db
    from app.providers.financial_modeling_prep.client import (
        EnhancedFMPClient)

    if _state["running"]:
        return {"status": "already_running"}
    _state.update(running=True, error=None)
    try:
        fmp = EnhancedFMPClient.from_settings()
        members = db.execute_query(
            "SELECT symbol, tier, checklist FROM smallcap_members "
            "ORDER BY symbol")
        scope = alert_scanner.universe()
        today = date.today()
        alerts: list[AlertItem] = []
        evaluated = 0

        def _alert(sym, direction, title, detail_extra):
            flags = scope.get(sym) or {}
            alerts.append(AlertItem(
                symbol=sym, event_type="sc_transition",
                direction=direction, materiality="HIGH",
                title=title,
                detail={"bucket": "actionable", "kind": "analyst",
                        **detail_extra},
                fingerprint=("sctr:" + hashlib.sha1(
                    f"{sym}|{today}|{direction}|{title[:40]}".encode()
                ).hexdigest()[:16]),
                source="smallcap_scout",
                source_timestamp=datetime.now(timezone.utc),
                in_portfolio=bool(flags.get("in_portfolio")),
                in_watchlist=bool(flags.get("in_watchlist")),
                priority_score=None))

        member_syms = set()
        for mem in members:
            sym = mem["symbol"]
            member_syms.add(sym)
            cl = mem.get("checklist") or {}
            m = await _eval_symbol(fmp, sym, deep=True)
            if not m:
                continue
            gates = _gates(m)
            gates_met = sum(gates.values())
            hidden = _hidden_engine(m.get("segments"))
            cl_met = sum(1 for k in ("tam", "moat", "ai_exposure",
                                     "vectors", "optionality", "proven")
                         if cl.get(k))
            score = _score(m, cl, hidden)
            runner = (gates_met == len(gates)
                      and (bool(hidden) or cl.get("proven")))
            suggested = ("runner" if runner
                         else "inflecting" if gates_met >= 4
                         else "watch")
            tier = mem["tier"]
            if tier == "watch" and suggested in ("inflecting", "runner"):
                upsert_member(sym, suggested, {})
                _alert(sym, "POSITIVE",
                       f"{sym} promoted to {suggested.upper()} — "
                       f"{gates_met}/5 gates, score {score}",
                       {"from": tier, "to": suggested, "gates": gates})
            elif tier != "runner" and runner:
                upsert_member(sym, "runner", {})
                _alert(sym, "POSITIVE",
                       f"{sym} auto-promoted to RUNNER — 5x signature "
                       f"complete ({gates_met}/5 gates, score {score}"
                       + (f", hidden engine: "
                          + ", ".join(f"{n} {s['yoy'] * 100:+.0f}%"
                                      for n, s in hidden.items())
                          if hidden else ", agent-proven thesis") + ")",
                       {"from": tier, "to": "runner",
                        "auto_promoted": True, "gates": gates,
                        "hidden_engine": hidden})
            elif (tier in ("inflecting", "runner")
                  and m.get("rev_growth") is not None
                  and m["rev_growth"] < 0.10):
                _alert(sym, "NEGATIVE",
                       f"{sym} 5x thesis check — rev growth "
                       f"{m['rev_growth'] * 100:+.0f}% (<10%)",
                       {"kind": "thesis_check",
                        "rev_growth": m["rev_growth"]})
            elif tier in ("inflecting", "runner") and not runner \
                    and gates_met < 4 and cl.get("auto") \
                    and suggested == "watch":
                # auto-added name decayed below the bar — drop it
                remove_member(sym)
                _alert(sym, "NEGATIVE",
                       f"{sym} dropped from 5x Scout — gates collapsed "
                       f"to {gates_met}/5", {"dropped": True})
                member_syms.discard(sym)
                evaluated += 1
                continue

            db.execute_update(
                """INSERT INTO smallcap_snapshots
                   (symbol, as_of, rev_growth, eps_growth, rev_streak,
                    gross_margin, gross_margin_prev, op_margin,
                    fcf_margin, cash, total_debt, net_cash, dd52w,
                    vs_sma200, market_cap, price, segments,
                    hidden_engine, gates_met, gates_detail, sc_score,
                    grade)
                   VALUES (:s,:d,:rg,:eg,:rs,:gm,:gmp,:om,:fcf,:c,:td,:nc,
                           :dd,:vs,:mc,:px,CAST(:sg AS jsonb),
                           CAST(:he AS jsonb),:g,CAST(:gd AS jsonb),
                           :sc,:gr)
                   ON CONFLICT (symbol, as_of) DO UPDATE SET
                    rev_growth=EXCLUDED.rev_growth,
                    eps_growth=EXCLUDED.eps_growth,
                    rev_streak=EXCLUDED.rev_streak,
                    gross_margin=EXCLUDED.gross_margin,
                    gross_margin_prev=EXCLUDED.gross_margin_prev,
                    op_margin=EXCLUDED.op_margin,
                    fcf_margin=EXCLUDED.fcf_margin,
                    cash=EXCLUDED.cash, total_debt=EXCLUDED.total_debt,
                    net_cash=EXCLUDED.net_cash, dd52w=EXCLUDED.dd52w,
                    vs_sma200=EXCLUDED.vs_sma200,
                    market_cap=EXCLUDED.market_cap, price=EXCLUDED.price,
                    segments=EXCLUDED.segments,
                    hidden_engine=EXCLUDED.hidden_engine,
                    gates_met=EXCLUDED.gates_met,
                    gates_detail=EXCLUDED.gates_detail,
                    sc_score=EXCLUDED.sc_score, grade=EXCLUDED.grade""",
                {"s": sym, "d": today, "rg": m["rev_growth"],
                 "eg": m["eps_growth"], "rs": m["rev_streak"],
                 "gm": m["gross_margin"], "gmp": m["gross_margin_prev"],
                 "om": m["op_margin"], "fcf": m.get("fcf_margin"),
                 "c": m.get("cash"), "td": m.get("total_debt"),
                 "nc": gates["net cash"], "dd": m.get("dd52w"),
                 "vs": m.get("vs_sma200"), "mc": m["market_cap"],
                 "px": m["price"], "sg": json.dumps(m.get("segments") or {}),
                 "he": json.dumps(hidden), "g": gates_met,
                 "gd": json.dumps(gates), "sc": score,
                 "gr": _letter(score)})
            evaluated += 1

        # --- discovery sweep: a slice of the $1-30B pool per run -----
        discovered = 0
        if discover:
            pool = [s for s in _pool() if s not in member_syms]
            cur = int(_kv_get("cursor") or 0)
            sl = pool[cur:cur + DISCOVERY_SLICE]
            _kv_set("cursor",
                    str(cur + len(sl) if sl and cur + len(sl) < len(pool)
                        else 0))
            sem = asyncio.Semaphore(6)

            async def _one(sym):
                async with sem:
                    try:
                        return sym, await asyncio.wait_for(
                            _eval_symbol(fmp, sym), timeout=45)
                    except Exception:
                        return sym, None

            results = await asyncio.gather(*(_one(s) for s in sl))
            shortlist = [s for s, m in results
                         if m and _light_gates(m) >= 3]

            async def _deep(sym):
                async with sem:
                    try:
                        return sym, await asyncio.wait_for(
                            _eval_symbol(fmp, sym, deep=True),
                            timeout=60)
                    except Exception:
                        return sym, None

            deep_results = await asyncio.gather(
                *(_deep(s) for s in shortlist))
            for sym, m in deep_results:
                if not m:
                    continue
                gates = _gates(m)
                gates_met = sum(gates.values())
                if gates_met < 3:
                    continue
                hidden = _hidden_engine(m.get("segments"))
                score = _score(m, {}, hidden)
                tier = ("inflecting" if gates_met >= 4 else "watch")
                upsert_member(sym, tier, {"auto": True})
                discovered += 1
                _alert(sym, "POSITIVE",
                       f"{sym} discovered by 5x Scout — {gates_met}/5 "
                       f"gates, score {score}, rev "
                       f"{(m['rev_growth'] or 0) * 100:+.0f}%, mcap "
                       f"${(m['market_cap'] or 0) / 1e9:.1f}B"
                       + (f", engine: {next(iter(hidden))}"
                          if hidden else ""),
                       {"discovered": True, "tier": tier,
                        "gates": gates, "score": score})
            evaluated += len(sl)

        try:
            inserted, skipped = alert_scanner.persist(alerts)
            logger.info("sc alerts: %s inserted, %s skipped",
                        inserted, skipped)
        except Exception as exc:
            logger.debug("sc alert persist failed: %s", exc)

        # auto-research: agent-scores checklists for members it hasn't
        # covered — bounded to 2/run (LLM cost + latency)
        try:
            from app.screener.ai_research import research_missing
            await research_missing(limit=2, engine="smallcap")
        except Exception as exc:
            logger.debug("sc research_missing failed: %s", exc)
        # refresh the expectation-gap layer for all members
        try:
            from app.signals.expectation_gap import refresh_flywheel
            await refresh_flywheel(sorted(member_syms))
        except Exception as exc:
            logger.debug("sc flywheel refresh failed: %s", exc)
        # canonical momentum flags for all tracked names — one batched
        # price pull, writes stocks.momentum_state for every surface
        try:
            from app.signals.momentum_regime import (
                refresh_momentum_all)
            await asyncio.to_thread(refresh_momentum_all)
        except Exception as exc:
            logger.debug("sc momentum refresh failed: %s", exc)
        _state.update(last_run_at=datetime.now(timezone.utc).isoformat(),
                      evaluated=evaluated)
        return {"status": "completed", "evaluated": evaluated,
                "discovered": discovered if discover else 0,
                "alerts": len(alerts)}
    except Exception as exc:
        logger.error("smallcap run failed: %s", exc, exc_info=True)
        _state["error"] = str(exc)
        return {"status": "error", "error": str(exc)}
    finally:
        _state["running"] = False


# --- board -----------------------------------------------------------------


def sc_board() -> dict[str, Any]:
    """Members + latest snapshot — the 5x ladder view."""
    from app.database import db
    from app.alerts import scanner as alert_scanner
    rows = db.execute_query(
        """
        SELECT m.symbol, m.tier, m.checklist, m.promoted_at,
               s.as_of, s.rev_growth, s.eps_growth, s.rev_streak,
               s.gross_margin, s.gross_margin_prev, s.op_margin,
               s.fcf_margin, s.cash, s.total_debt, s.net_cash,
               s.dd52w, s.vs_sma200, s.segments, s.hidden_engine,
               s.market_cap, s.price, s.gates_met, s.gates_detail,
               s.sc_score, s.grade, st.cyclical, st.next_earnings_date,
               st.momentum_state, st.fundamental_state, st.fundamental_risk,
               fw.gap_score, fw.beat_streak, fw.est_revision_pct,
               fw.fwd_pe, fw.num_analysts, fw.muted_reaction,
               fw.rev_accel
        FROM smallcap_members m
        LEFT JOIN stocks st ON st.symbol = m.symbol
        LEFT JOIN symbol_flywheel fw ON fw.symbol = m.symbol
        LEFT JOIN LATERAL (
            SELECT * FROM smallcap_snapshots s
            WHERE s.symbol = m.symbol
            ORDER BY s.as_of DESC LIMIT 1
        ) s ON true
        ORDER BY COALESCE(s.sc_score, 0) DESC, m.symbol
        """)
    try:
        scope = alert_scanner.universe()
    except Exception:
        scope = {}
    out = []
    for r in rows:
        cl = r.get("checklist") or {}
        flags = scope.get(r["symbol"]) or {}
        mc = r.get("market_cap")
        cl_met = sum(1 for k in ("tam", "moat", "ai_exposure",
                                 "vectors", "optionality", "proven")
                     if cl.get(k))
        out.append({
            "symbol": r["symbol"], "tier": r["tier"],
            "cyclical": r.get("cyclical"),
            "momentum": r.get("momentum_state"),
            "fund_state": r.get("fundamental_state"),
            "fund_risk": r.get("fundamental_risk"),
            "next_earnings": (str(r["next_earnings_date"])
                              if r.get("next_earnings_date") else None),
            "gap_score": r.get("gap_score"),
            "beat_streak": r.get("beat_streak"),
            "est_revision_pct": r.get("est_revision_pct"),
            "fwd_pe": r.get("fwd_pe"),
            "num_analysts": r.get("num_analysts"),
            "muted_reaction": r.get("muted_reaction"),
            "rev_accel": r.get("rev_accel"),
            "as_of": str(r["as_of"]) if r.get("as_of") else None,
            "rev_growth": r.get("rev_growth"),
            "rev_streak": r.get("rev_streak"),
            "gross_margin": r.get("gross_margin"),
            "gross_margin_prev": r.get("gross_margin_prev"),
            "op_margin": r.get("op_margin"),
            "fcf_margin": r.get("fcf_margin"),
            "cash_b": round((r.get("cash") or 0) / 1e9, 2)
                      if r.get("cash") is not None else None,
            "debt_b": round((r.get("total_debt") or 0) / 1e9, 2)
                      if r.get("total_debt") is not None else None,
            "net_cash": r.get("net_cash"),
            "dd52w": r.get("dd52w"),
            "vs_sma200": r.get("vs_sma200"),
            "segments": r.get("segments") or {},
            "hidden_engine": r.get("hidden_engine") or {},
            "market_cap_b": round(mc / 1e9, 2) if mc else None,
            "price": r.get("price"),
            "gates_met": r.get("gates_met"),
            "gates": r.get("gates_detail") or {},
            "sc_score": r.get("sc_score"),
            "grade": r.get("grade"),
            "checklist": cl,
            "checklist_met": cl_met,
            "checklist_pending": not cl.get("checklist_sources"),
            "ai_rev_pct": cl.get("ai_rev_pct"),
            "thesis": cl.get("thesis"),
            "promoted_at": str(r["promoted_at"])
                          if r.get("promoted_at") else None,
            "in_portfolio": bool(flags.get("in_portfolio")),
            "in_watchlist": bool(flags.get("in_watchlist")),
        })
    return {"members": out, "count": len(out)}
