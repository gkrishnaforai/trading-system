"""Rule Breakers — milestone-ladder tracking for emerging/confirmed
high-conviction growers (ALGM-style "early transition" names).

The framework from the desk analysis: a name graduates when the numbers
prove the secular engine (AI/space/cyber) is becoming the company's
dominant driver — not just a fast-growing vertical inside an old
business. Quantitative gates auto-verify every evaluation run;
qualitative thesis (TAM, moat, vectors, proven) is agent-researched.

Tiers:  watchlist → emerging (auto when >=3 quant gates) → confirmed
        (auto when all gates + proven + checklist>=4/6 + the secular
        share bar: ai_rev_pct>=20 for AI names, waived for non-AI
        engines). Streak breaks / growth collapse flag a thesis-check
        alert — the early warning, mirroring accel_watch.

Quant gates (computed from provider data, ~3 calls/member/run):
  rev>=25% · rev_streak>=2 · gm rising QoQ · mcap $1-500B (room to 2x)
Promotion needs all four + proven + checklist>=4/6 + share bar.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from datetime import date, datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

REV_MIN = 0.25            # company-wide revenue growth (fraction)
REV_STREAK_MIN = 2        # consecutive YoY-improvement quarters
MCAP_MIN, MCAP_MAX = 1e9, 500e9  # room to ~2x — AMD/PLTR both
                                 # doubled from $300-400B; the binding
                                 # constraint is tailwind-vs-revenue,
                                 # not size. Only truly mega ($500B+)
                                 # names are structurally capped.
AI_REV_PROMOTE = 20.0     # % of revenue from the secular engine
CHECKLIST_MIN = 4         # of tam/moat/ai_exposure/vectors/optionality/proven
THESIS_CHECK_REV = 0.15   # below this on an emerging/confirmed name = warn

_state: dict[str, Any] = {
    "running": False, "last_run_at": None, "evaluated": 0, "error": None}


def rb_status() -> dict[str, Any]:
    return dict(_state)


DISCOVERY_INTERVAL_DAYS = 7


def _kv_get(key: str) -> Optional[str]:
    from app.database import db
    rows = db.execute_query(
        "SELECT value FROM rb_state WHERE key=:k", {"k": key})
    return rows[0]["value"] if rows else None


def _kv_set(key: str, value: str) -> None:
    from app.database import db
    db.execute_update(
        "INSERT INTO rb_state (key, value) VALUES (:k,:v) "
        "ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value",
        {"k": key, "v": value})


def discovery_due() -> bool:
    """Weekly discovery pass over the universe — auto-add names that
    start satisfying the gates, auto-drop auto-added names that stop."""
    last = _kv_get("last_discovery")
    if not last:
        return True
    try:
        return (date.today() - date.fromisoformat(last)).days \
            >= DISCOVERY_INTERVAL_DAYS
    except ValueError:
        return True


def _gates(m: dict, prev_gm: Optional[float]) -> dict[str, bool]:
    rev = m.get("rev_growth")
    streak = m.get("rev_streak") or 0
    gm, mcap = m.get("gross_margin"), m.get("market_cap")
    return {
        "rev>25%": bool(rev is not None and rev >= REV_MIN),
        "rev streak>=2": streak >= REV_STREAK_MIN,
        "gm rising": bool(gm is not None and prev_gm is not None
                          and gm > prev_gm),
        "mcap $1-500B": bool(mcap and MCAP_MIN <= mcap <= MCAP_MAX),
    }


def _checklist_met(cl: dict) -> int:
    return sum(1 for k in ("tam", "moat", "ai_exposure", "vectors",
                           "optionality", "proven") if cl.get(k))


async def _eval_symbol(fmp, sym: str, deep: bool = False) -> Optional[dict]:
    """Fetch income-statement + profile, compute the gate metrics.
    YoY paths computed directly — FMP's growthRevenue is QoQ sequential.
    `deep` (members only) adds cash-flow + product-segmentation so the
    traction layer — FCF margin and product-line mix — can be tracked."""
    reqs = [
        asyncio.to_thread(fmp._make_request, "/income-statement",
                          {"symbol": sym, "period": "quarter",
                           "limit": 9}),
        asyncio.to_thread(fmp._make_request, "/profile",
                          {"symbol": sym})]
    if deep:
        reqs += [
            asyncio.to_thread(fmp._make_request, "/cash-flow-statement",
                              {"symbol": sym, "period": "quarter",
                               "limit": 1}),
            asyncio.to_thread(fmp._make_request,
                              "/revenue-product-segmentation",
                              {"symbol": sym})]
    try:
        res = await asyncio.gather(*reqs)
        income, profile = res[0], res[1]
        cash, seg_rows = (res[2], res[3]) if deep else (None, None)
    except Exception as exc:
        logger.debug("rb fetch %s failed: %s", sym, exc)
        return None

    inc = income or []
    q = inc[0] if inc else {}
    gm = (q.get("grossProfit") / q["revenue"]
          if q.get("grossProfit") and q.get("revenue") else None)
    # YoY margin comparison — "GM up from a year earlier", the way the
    # desk reads it, not QoQ noise.
    qy = inc[4] if len(inc) > 4 else {}
    gm_prev = (qy.get("grossProfit") / qy["revenue"]
               if qy.get("grossProfit") and qy.get("revenue") else None)
    opm = (q.get("operatingIncome") / q["revenue"]
           if q.get("operatingIncome") is not None and q.get("revenue")
           else None)
    p = (profile or [{}])[0]
    rev_path, eps_path = [], []
    for i in range(len(inc) - 4):
        a, b = inc[i].get("revenue"), inc[i + 4].get("revenue")
        rev_path.append(a / b - 1 if a and b else None)
        a, b = inc[i].get("netIncome"), inc[i + 4].get("netIncome")
        eps_path.append(a / b - 1
                        if a is not None and b not in (None, 0) else None)
    rev_g = rev_path[0] if rev_path else None
    rev_streak = 0
    cur = rev_g
    for nxt in rev_path[1:]:
        if cur is None or nxt is None or cur <= nxt:
            break
        rev_streak += 1
        cur = nxt
    # --- traction layer (deep) ---------------------------------------
    cq = (cash or [{}])[0]
    fcfm = (cq.get("freeCashFlow") / q["revenue"]
            if cq.get("freeCashFlow") is not None and q.get("revenue")
            else None)
    segments = _segments(seg_rows, q.get("revenue"))
    return {"rev_growth": rev_g,
            "eps_growth": eps_path[0] if eps_path else None,
            "rev_streak": rev_streak, "gross_margin": gm,
            "gross_margin_prev": gm_prev, "op_margin": opm,
            "fcf_margin": fcfm, "segments": segments,
            "market_cap": p.get("marketCap"), "price": p.get("price")}


def _segments(seg_rows: Optional[list],
              latest_q_rev: Optional[float]) -> dict:
    """Product-line mix from /revenue-product-segmentation — the
    'product traction' leg: {name: {rev, share(FY), yoy}}. FMP reports
    product lines, not end-markets — so 'data-center %' stays a manual
    checklist field, but real lines like ALGM's Power ICs compute."""
    if not seg_rows:
        return {}
    latest = next((r for r in seg_rows if r.get("data")), None)
    prior = next((r for r in seg_rows[1:] if r.get("data")), None)
    if not latest:
        return {}
    ldata, pdata = latest["data"], (prior or {}).get("data") or {}
    total = sum(v for v in ldata.values() if isinstance(v, (int, float)))
    out = {}
    for name, rev in ldata.items():
        if not isinstance(rev, (int, float)):
            continue
        prev = pdata.get(name)
        out[name] = {
            "rev": rev,
            "share": rev / total if total else None,
            "yoy": rev / prev - 1 if prev else None,
        }
    return out


_OPS = {
    ">": lambda a, b: a > b, ">=": lambda a, b: a >= b,
    "<": lambda a, b: a < b, "<=": lambda a, b: a <= b,
    "==": lambda a, b: abs(a - b) < 1e-9,
}


def _milestone_metrics(m: dict, cl: dict) -> dict:
    """Metric vocabulary milestones can reference. Financial ratios are
    fractions (0.52); ai_rev_pct stays in percent as entered (17);
    segment keys are 'segment_share:<name>' / 'segment_growth:<name>'."""
    mm = {"rev_growth": m.get("rev_growth"),
          "eps_growth": m.get("eps_growth"),
          "rev_streak": m.get("rev_streak"),
          "gross_margin": m.get("gross_margin"),
          "op_margin": m.get("op_margin"),
          "fcf_margin": m.get("fcf_margin"),
          "market_cap": m.get("market_cap")}
    if cl.get("ai_rev_pct") is not None:
        mm["ai_rev_pct"] = cl["ai_rev_pct"]
    for name, seg in (m.get("segments") or {}).items():
        mm[f"segment_share:{name.lower()}"] = seg.get("share")
        mm[f"segment_growth:{name.lower()}"] = seg.get("yoy")
    return mm


# Segment names that *read* as AI-adjacent — used only to SUGGEST tags;
# most AI exposure hides in neutral names (ALGM "Power ICs" feeds AI
# racks), so the authoritative tag is checklist.ai_segments, set once
# from the 10-K/earnings read.
_AI_SEG_RX = re.compile(
    r"data ?cent(er|re)|accelerat|\bai\b|gpu|hpc|high[- ]performance|"
    r"inference|compute|network|connectivity|cloud|automo", re.I)


def _ai_traction(cl: dict, m: dict, mentions: int) -> tuple[float, dict]:
    """Tailwind score: declared revenue share (strongest), tagged-
    segment growth + share, multi-channel/dominant-line growth
    detection, corroborating AI tape mentions.
    Returns (score, evidence-detail for the snapshot)."""
    ai_pct = cl.get("ai_rev_pct") or 0
    score = min(15.0, ai_pct * 0.6)                    # 25% rev → 15 pts
    segs = m.get("segments") or {}
    declared = {s.lower() for s in cl.get("ai_segments") or []}
    tagged = {n: s for n, s in segs.items() if n.lower() in declared}
    suggested = [n for n in segs
                 if n.lower() not in declared and _AI_SEG_RX.search(n)]
    tag_yoy = [s["yoy"] for s in tagged.values()
               if s.get("yoy") is not None]
    tag_share = sum(s["share"] or 0 for s in tagged.values())
    if tag_yoy:
        mean_yoy = sum(tag_yoy) / len(tag_yoy)
        score += 8 if mean_yoy > 0.25 else 4 if mean_yoy > 0 else 0
    if tag_share > 0.15:
        score += 2
    # 2x signature from the AMD/CRDO/PLTR runs: EITHER several revenue
    # channels compounding >25% YoY (CRDO: AEC+optical+retimer; PLTR:
    # gov+commercial) OR one dominant line carrying the company (ALAB).
    # Channels are ANY reported segment — they don't need AI-sounding
    # names, the tailwind shows up as the growth itself.
    channels = {n: s for n, s in segs.items()
                if s.get("yoy") is not None and s["yoy"] > 0.25}
    if len(channels) >= 2:
        score += 6                                  # multi-channel
    elif len(channels) == 1:
        ch = next(iter(channels.values()))
        if (ch.get("share") or 0) > 0.5:
            score += 4                              # dominant tailwind
    score += min(5.0, float(mentions or 0))
    return round(score, 1), {
        "ai_rev_pct": ai_pct or None,
        "tagged_segments": {n: {"yoy": s.get("yoy"), "share": s.get("share")}
                            for n, s in tagged.items()},
        "suggested_segments": suggested,
        "growth_channels": {n: round(s["yoy"], 3)
                            for n, s in channels.items()},
        "mentions_30d": mentions}


def _check_milestones(cl: dict, metrics: dict) -> dict:
    """Typed entries in checklist.milestones — dicts like
    {"metric": "gross_margin", "op": ">", "target": 0.52} — get
    evaluated each run; plain strings remain display-only notes."""
    results = {}
    for ms in cl.get("milestones") or []:
        if not isinstance(ms, dict):
            continue
        label = ms.get("label") or (
            f"{ms.get('metric')} {ms.get('op', '>=')} {ms.get('target')}")
        val, tgt = metrics.get(ms.get("metric")), ms.get("target")
        op = _OPS.get(ms.get("op") or ">=")
        results[label] = (bool(op(val, tgt))
                          if val is not None and tgt is not None and op
                          else None)
    return results


async def run_rule_breakers(discover: bool = False) -> dict[str, Any]:
    """Evaluate all members against the gate ladder; snapshot + alert
    on tier transitions and thesis-check warnings. With `discover`,
    scan the whole universe for names starting to satisfy the gates
    (auto-add) and demote auto-added names that stop qualifying."""
    from app.alerts import scanner as alert_scanner
    from app.alerts.models import AlertItem
    from app.database import db
    from app.providers.financial_modeling_prep.client import EnhancedFMPClient

    if _state["running"]:
        return {"status": "already_running"}
    _state.update(running=True, error=None)
    try:
        fmp = EnhancedFMPClient.from_settings()
        members = db.execute_query(
            "SELECT symbol, tier, checklist FROM rule_breaker_members "
            "ORDER BY symbol")
        if not members and not discover:
            _state.update(last_run_at=datetime.now(timezone.utc).isoformat(),
                          evaluated=0)
            return {"status": "completed", "evaluated": 0}
        scope = alert_scanner.universe()
        today = date.today()
        alerts: list[AlertItem] = []
        evaluated = 0
        # AI-tailwind tape corroboration — AI-keyword catalyst mentions
        # per symbol over 30d, one grouped query for all members.
        try:
            ai_mentions = {r["symbol"]: r["n"] for r in db.execute_query(
                """SELECT symbol, count(*) n FROM alert_items
                   WHERE created_at > now() - interval '30 days'
                   AND title ~* :rx GROUP BY symbol""",
                {"rx": r"(^|[^a-z])ai([^a-z]|$)|artificial intelligence|"
                       r"data ?cent(er|re)|\bgpu\b|inference|agentic|"
                       r"hyperscal|\bllm\b|accelerat"})}
        except Exception:
            ai_mentions = {}

        def _alert(sym, direction, title, detail_extra):
            flags = scope.get(sym) or {}
            alerts.append(AlertItem(
                symbol=sym, event_type="rb_transition",
                direction=direction, materiality="HIGH",
                title=title,
                detail={"bucket": "actionable", "kind": "analyst",
                        **detail_extra},
                fingerprint=("rbtr:" + hashlib.sha1(
                    f"{sym}|{today}|{direction}|{title[:40]}".encode()
                ).hexdigest()[:16]),
                source="rule_breakers",
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
            gates = _gates(m, m["gross_margin_prev"])
            gm, gm_prev = m["gross_margin"], m["gross_margin_prev"]
            opm, rev_g, rev_streak = (
                m["op_margin"], m["rev_growth"], m["rev_streak"])
            p = {"marketCap": m["market_cap"], "price": m["price"]}
            gates_met = sum(gates.values())
            cl_met = _checklist_met(cl)
            ai_pct = cl.get("ai_rev_pct")
            # 'proven' is the CRDO/ALAB test — the secular engine already
            # visible in the financials, not a roadmap. Required for
            # confirmed; without it the name is speculative by definition.
            # the AI-share proof bar only applies to AI-exposed names —
            # a non-AI secular engine (rare earths, EVs, fintech)
            # confirms on proven + all gates + checklist alone
            ai_ok = (cl.get("ai_exposure") is False
                     or (ai_pct or 0) >= AI_REV_PROMOTE)
            eligible = (gates_met == len(gates) and cl.get("proven")
                        and cl_met >= CHECKLIST_MIN and ai_ok)
            suggested = ("confirmed" if eligible
                         else "emerging" if gates_met >= 3
                         else "watchlist")

            ai_score, ai_detail = _ai_traction(
                cl, m, ai_mentions.get(sym, 0))
            mm = _milestone_metrics(m, cl)
            mm["ai_traction"] = ai_score
            milestones = _check_milestones(cl, mm)
            db.execute_update(
                """
                INSERT INTO rule_breaker_snapshots
                    (symbol, as_of, rev_growth, eps_growth, rev_streak,
                     eps_streak, gross_margin, gross_margin_prev,
                     op_margin, fcf_margin, segments, milestones,
                     ai_traction, ai_detail,
                     market_cap, price, gates_met,
                     gates_detail, suggested_tier)
                VALUES (:s,:d,:rg,:eg,:rs,:es,:gm,:gmp,:om,:fm,:sg,:ms,
                        :at,:ad,:mc,:px,:gm2,:gd,:st)
                ON CONFLICT (symbol, as_of) DO UPDATE SET
                    rev_growth=EXCLUDED.rev_growth,
                    eps_growth=EXCLUDED.eps_growth,
                    rev_streak=EXCLUDED.rev_streak,
                    gross_margin=EXCLUDED.gross_margin,
                    gross_margin_prev=EXCLUDED.gross_margin_prev,
                    op_margin=EXCLUDED.op_margin,
                    fcf_margin=EXCLUDED.fcf_margin,
                    segments=EXCLUDED.segments,
                    milestones=EXCLUDED.milestones,
                    ai_traction=EXCLUDED.ai_traction,
                    ai_detail=EXCLUDED.ai_detail,
                    market_cap=EXCLUDED.market_cap, price=EXCLUDED.price,
                    gates_met=EXCLUDED.gates_met,
                    gates_detail=EXCLUDED.gates_detail,
                    suggested_tier=EXCLUDED.suggested_tier
                """,
                {"s": sym, "d": today, "rg": rev_g,
                 "eg": m["eps_growth"], "rs": rev_streak,
                 "es": None, "gm": gm, "gmp": gm_prev, "om": opm,
                 "fm": m.get("fcf_margin"), "sg": json.dumps(m.get("segments")),
                 "ms": json.dumps(milestones),
                 "at": ai_score, "ad": json.dumps(ai_detail),
                 "mc": m["market_cap"], "px": m["price"],
                 "gm2": gates_met, "gd": json.dumps(gates), "st": suggested})
            evaluated += 1

            # milestone transitions — a typed milestone flipping hit/lost
            # vs the previous snapshot is the "thesis proving itself" (or
            # breaking) signal; one alert per flip.
            if milestones:
                prev_rows = db.execute_query(
                    "SELECT milestones FROM rule_breaker_snapshots "
                    "WHERE symbol=:s AND as_of < :d "
                    "ORDER BY as_of DESC LIMIT 1",
                    {"s": sym, "d": today})
                prev_ms = ((prev_rows[0] or {}).get("milestones")
                           if prev_rows else None) or {}
                for label, hit in milestones.items():
                    if hit is None:
                        continue
                    was = prev_ms.get(label)
                    if hit and was is not True:
                        _alert(sym, "POSITIVE",
                               f"{sym} RB milestone hit — {label}",
                               {"kind": "rb_milestone", "milestone": label,
                                "hit": True})
                    elif not hit and was is True:
                        _alert(sym, "NEGATIVE",
                               f"{sym} RB milestone LOST — {label}",
                               {"kind": "rb_milestone", "milestone": label,
                                "hit": False})

            tier = mem["tier"]
            if tier == "watchlist" and suggested in ("emerging", "confirmed"):
                db.execute_update(
                    "UPDATE rule_breaker_members SET tier='emerging',"
                    " promoted_at=now() WHERE symbol=:s", {"s": sym})
                _alert(sym, "POSITIVE",
                       f"{sym} promoted to EMERGING Rule Breaker — "
                       f"{gates_met}/4 gates "
                       f"(rev {rev_g * 100:+.0f}%, streak {rev_streak})",
                       {"from": tier, "to": "emerging", "gates": gates,
                        "rev_growth": rev_g, "rev_streak": rev_streak,
                        "gross_margin": gm, "market_cap": m["market_cap"]})
            elif tier != "confirmed" and eligible:
                # no human in the loop — gates + proven + checklist +
                # AI% all pass → the system promotes itself.
                db.execute_update(
                    "UPDATE rule_breaker_members SET tier='confirmed',"
                    " promoted_at=now() WHERE symbol=:s", {"s": sym})
                _alert(sym, "POSITIVE",
                       f"{sym} promoted to CONFIRMED Rule Breaker — "
                       f"all gates + AI rev {ai_pct:.0f}% + "
                       f"checklist {cl_met}/6 + proven",
                       {"from": tier, "to": "confirmed",
                        "auto_promoted": True, "gates": gates})
            elif (tier in ("emerging", "confirmed")
                  and rev_g is not None and rev_g < THESIS_CHECK_REV):
                _alert(sym, "NEGATIVE",
                       f"{sym} RB thesis check — revenue growth "
                       f"{rev_g * 100:.0f}% below {THESIS_CHECK_REV * 100:.0f}% floor",
                       {"thesis_check": True, "tier": tier,
                        "rev_growth": rev_g, "gates": gates})
            # auto-added names that stop qualifying get demoted out;
            # human-curated members stay — thesis is a human call.
            if cl.get("auto") and gates_met < 2:
                db.execute_update(
                    "DELETE FROM rule_breaker_members WHERE symbol=:s",
                    {"s": sym})
                _alert(sym, "NEGATIVE",
                       f"{sym} dropped from Rule Breaker watchlist — "
                       f"{gates_met}/4 gates "
                       f"(rev {rev_g * 100:+.0f}%, streak {rev_streak})",
                       {"auto_removed": True, "gates": gates,
                        "rev_growth": rev_g})

        # --- AI-exposure autofill — members missing ai_rev_pct get
        # researched by the agent (bounded: 2 per eval run).
        ai_research_done = []
        try:
            from app.screener import ai_research
            missing = [m["symbol"] for m in members
                       if ai_research._needs_research(
                           m.get("checklist") or {})]
            for sym in missing[:2]:
                ai_research_done.append(await asyncio.wait_for(
                    ai_research.research_symbol(sym), timeout=90))
        except Exception as exc:
            logger.debug("rb ai research skipped: %s", exc)

        # --- discovery pass (weekly) — scan the universe for names
        # starting to satisfy the gates; auto-add what qualifies.
        discovered = 0
        if discover:
            sem = asyncio.Semaphore(6)

            async def _one(sym):
                async with sem:
                    try:
                        return sym, await asyncio.wait_for(
                            _eval_symbol(fmp, sym), timeout=45)
                    except Exception:
                        return sym, None

            disc_results = await asyncio.gather(
                *(_one(s) for s in sorted(set(scope) - member_syms)))
            for sym, m in disc_results:
                if not m:
                    continue
                gates = _gates(m, m["gross_margin_prev"])
                gates_met = sum(gates.values())
                if gates_met < 2:
                    continue
                tier = "emerging" if gates_met >= 3 else "watchlist"
                upsert_member(sym, tier, {"auto": True})
                member_syms.add(sym)
                discovered += 1
                _alert(sym, "POSITIVE",
                       f"{sym} discovered as {tier.upper()} Rule Breaker "
                       f"candidate — {gates_met}/4 gates "
                       f"(rev {(m['rev_growth'] or 0) * 100:+.0f}%, "
                       f"streak {m['rev_streak']}, "
                       f"mcap ${(m['market_cap'] or 0)/1e9:.1f}B)",
                       {"discovered": True, "tier": tier, "gates": gates,
                        "rev_growth": m["rev_growth"],
                        "market_cap": m["market_cap"]})
                evaluated += 1
            _kv_set("last_discovery", today.isoformat())

        for a in alerts:
            a.priority_score = alert_scanner.priority_score(a)
        inserted, skipped = alert_scanner.persist(alerts)
        # refresh the expectation-gap layer so the board's gap_score
        # stays current with the eval cadence
        try:
            from app.signals.expectation_gap import refresh_flywheel
            await refresh_flywheel(sorted(member_syms))
        except Exception as exc:
            logger.debug("flywheel refresh failed: %s", exc)
        # canonical momentum flags for all tracked names — one batched
        # price pull, writes stocks.momentum_state for every surface
        try:
            from app.signals.momentum_regime import (
                refresh_momentum_all)
            await asyncio.to_thread(refresh_momentum_all)
        except Exception as exc:
            logger.debug("momentum refresh failed: %s", exc)
        _state.update(evaluated=evaluated,
                      last_run_at=datetime.now(timezone.utc).isoformat())
        return {"status": "completed", "evaluated": evaluated,
                "discovered": discovered, "alerts": inserted,
                "skipped": skipped,
                "ai_research": ai_research_done}
    except Exception as exc:
        logger.error("rule breakers run failed: %s", exc, exc_info=True)
        _state["error"] = str(exc)
        return {"status": "error", "error": str(exc)}
    finally:
        _state["running"] = False


def _rb_grade(r: dict, cl_met: int) -> tuple[int, Optional[str], bool]:
    """Composite 0–100: gates (0-40) + proof/checklist (0-30)
    + tailwind traction (0-30). Returns (score, letter, pending) —
    pending means the agent has never scored the checklist, so the
    grade is a floor rather than a verdict."""
    gates = (r.get("gates_met") or 0) * 10
    cl = r.get("checklist") or {}
    proof = min(15.0, cl_met * 2.5) + (15 if cl.get("proven") else 0)
    tail = min(30.0, r.get("ai_traction") or 0)
    score = int(round(gates + proof + tail))
    pending = not cl.get("checklist_sources")
    letter = ("A+" if score >= 85 else "A" if score >= 75
              else "B" if score >= 60 else "C" if score >= 45 else "D")
    return score, letter, pending


def rb_board() -> dict[str, Any]:
    """Members + latest snapshot each — the ladder view."""
    from app.database import db
    from app.alerts import scanner as alert_scanner
    rows = db.execute_query(
        """
        SELECT m.symbol, m.tier, m.checklist, m.promoted_at,
               s.as_of, s.rev_growth, s.eps_growth, s.rev_streak,
               s.gross_margin, s.gross_margin_prev, s.op_margin,
               s.fcf_margin, s.segments, s.milestones,
               s.ai_traction, s.ai_detail,
               s.market_cap, s.price, s.gates_met, s.gates_detail,
               s.suggested_tier, st.cyclical, st.next_earnings_date,
               st.momentum_state, st.fundamental_state, st.fundamental_risk,
               fw.gap_score, fw.beat_streak, fw.est_revision_pct,
               fw.fwd_pe, fw.num_analysts, fw.muted_reaction,
               fw.rev_accel
        FROM rule_breaker_members m
        LEFT JOIN stocks st ON st.symbol = m.symbol
        LEFT JOIN symbol_flywheel fw ON fw.symbol = m.symbol
        LEFT JOIN LATERAL (
            SELECT * FROM rule_breaker_snapshots s
            WHERE s.symbol = m.symbol
            ORDER BY s.as_of DESC LIMIT 1
        ) s ON true
        ORDER BY CASE m.tier WHEN 'confirmed' THEN 0
                 WHEN 'emerging' THEN 1 WHEN 'speculative' THEN 2
                 ELSE 3 END, m.symbol
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
        cl_met = _checklist_met(cl)
        rb_score, rb_letter, rb_pending = _rb_grade(r, cl_met)
        out.append({
            "symbol": r["symbol"], "tier": r["tier"],
            "suggested_tier": r.get("suggested_tier"),
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
            "segments": r.get("segments") or {},
            "milestones": r.get("milestones") or {},
            "ai_traction": r.get("ai_traction"),
            "ai_detail": r.get("ai_detail") or {},
            "market_cap_b": round(mc / 1e9, 1) if mc else None,
            "price": r.get("price"),
            "gates_met": r.get("gates_met"),
            "gates": r.get("gates_detail") or {},
            "checklist": cl,
            "checklist_met": cl_met,
            "rb_score": rb_score,
            "rb_grade": rb_letter,
            "rb_grade_pending": rb_pending,
            "ai_rev_pct": cl.get("ai_rev_pct"),
            "thesis": cl.get("thesis"),
            "promoted_at": str(r["promoted_at"]) if r.get("promoted_at") else None,
            "in_portfolio": bool(flags.get("in_portfolio")),
            "in_watchlist": bool(flags.get("in_watchlist")),
        })
    return {"members": out, "count": len(out)}


def upsert_member(symbol: str, tier: str = "watchlist",
                  checklist: Optional[dict] = None) -> dict:
    from app.database import db
    db.execute_update(
        """
        INSERT INTO rule_breaker_members (symbol, tier, checklist)
        VALUES (:s, :t, CAST(:c AS jsonb))
        ON CONFLICT (symbol) DO UPDATE SET
            tier = EXCLUDED.tier,
            checklist = rule_breaker_members.checklist || EXCLUDED.checklist,
            promoted_at = CASE WHEN EXCLUDED.tier <> rule_breaker_members.tier
                          THEN now() ELSE rule_breaker_members.promoted_at END
        """,
        {"s": symbol.upper(), "t": tier,
         "c": json.dumps(checklist or {})})
    return {"symbol": symbol.upper(), "tier": tier}


def remove_member(symbol: str) -> dict:
    from app.database import db
    db.execute_update(
        "DELETE FROM rule_breaker_members WHERE symbol=:s",
        {"s": symbol.upper()})
    return {"removed": symbol.upper()}
