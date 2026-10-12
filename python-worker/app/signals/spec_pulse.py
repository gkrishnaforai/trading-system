"""Speculative pulse — the spec sleeve's action board. Same one-row-
per-name shape as portfolio pulse, different playbook: the thesis IS
the position, dips are never averaged, exits are fast.

What makes a name speculative here (deterministic):
  engine   — a member of rule_breaker_members / smallcap_members at a
             promoted tier (emerging/confirmed/inflecting/runner), or
             in the latest hidden-gem snapshot
  unpriced — held names the core model can't value: no FV run AND
             (analyst coverage <= 3 OR negative op margin). A position
             the valuation engine can't anchor is speculative whether
             or not it was bought that way.
ETFs and mega-caps are excluded.

Action semantics (first-match-wins) — deliberately NOT the core
pulse's bucket logic:
  cut            tape broken OR thesis fundamentals failing — no
                 averaging down on story stocks, ever
  thesis_check   a leg is degrading, a binary event (earnings <=5d)
                 is ahead, or the engine wants to demote the tier —
                 decide within days, not lazy weak-holds
  harvest        climax / parabolic extension — sell a tranche into
                 strength, keep a runner
  buy_a_lot      promoted tier + constructive tape + not extended +
                 clear event window
  buy_a_little   early thesis + improving tape — starter size only
  runner         promoted tier, tape fine — let it work, trail it
  hold           nothing failing, nothing set up

Every eval is journaled (first-write-per-day) so meta can later
answer: did HARVEST precede tops, did THESIS_CHECK precede cuts?
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

_TAPE_BROKEN = {"knife", "capitulation", "breakdown"}
_TAPE_DEGRADED = {"downtrend", "rolling_over"}
_TAPE_CLIMX = {"climax"}
_TAPE_GOOD = {"uptrend", "pullback", "recovery", "basing"}
_TAPE_HOT = {"breakout"}
_FUND_FAIL = {"declining", "deteriorating"}
_FUND_COOL = {"slowing", "pressured", "watch"}
_FUND_STRONG = {"accelerating", "growing"}
_TIER_PROMOTED = {"emerging", "confirmed", "inflecting", "runner"}

_EXT_VS50 = 0.15          # >15% above the 50dma = extended
_EARN_CHECK_DAYS = 5      # binary event window — decide before print
_EARN_BUY_DAYS = 7        # don't add this close to a binary
_FORTRESS_MCAP = 50e9     # fortress veto: big + profitable + covered
_FORTRESS_ANALYSTS = 10   # is not a speculative position

# STS — Spec Thesis Score. Thesis legs (business, 0-60) vs tape legs
# (timing, 0-40): institutions exit on business breaks and time on
# price — the decomposition keeps those two jobs separate.
_FUND_STS = {"accelerating": 20, "growing": 15, "watch": 8,
             "cyclical": 8, "slowing": 4, "pressured": 2,
             "declining": 0, "deteriorating": 0}
_TIER_STS = {"confirmed": 15, "runner": 15, "emerging": 10,
             "inflecting": 10, "watchlist": 5, "watch": 5}
_MOM_STS = {"breakout": 15, "uptrend": 15, "pullback": 12,
            "recovery": 12, "basing": 8, "climax": 6,
            "rolling_over": 4, "downtrend": 0, "knife": 0,
            "capitulation": 0, "breakdown": 0}
_DIP_STS = {"turning_up": 5, "confirmed": 5, "basing": 3}

_STS_FULL = 70            # buy-a-lot floor
_STS_HALF = 50            # buy-a-little floor / loss-review cut line
_STS_DROP = 15            # pts vs last eval → thesis_check (score mom)
_DD_STRUCT = -0.45        # dd52w this deep = thesis priced as failed
_BROKEN_SESS = 10         # tape broken this many recent sessions
_REV_FLOOR = 0.15         # ARK-style growth floor for promoted tiers
_PNL_REVIEW = -30         # first ladder rung — forced loss review
_PNL_CUT = -50            # second rung — cut unless thesis strong
_PNL_DOUBLE = 100         # doubled → harvest the house's money


def _fortress(r: dict[str, Any]) -> bool:
    """A large, profitable, analyst-covered company cannot be a
    speculative position even when an engine tracks its growth
    optionality — the thesis is a driver, not an existential bet."""
    opm = r.get("op_margin") if r.get("op_margin") is not None \
        else r.get("rb_opm") if r.get("rb_opm") is not None \
        else r.get("sc_opm")
    return ((r.get("market_cap") or 0) >= _FORTRESS_MCAP
            and (r.get("num_analysts") or 0) >= _FORTRESS_ANALYSTS
            and ((opm or 0) > 0
                 or r.get("expected_fair_value") is not None))


def _score(r: dict[str, Any]) -> dict[str, int]:
    """STS = thesis legs (0-60) + tape legs (0-40)."""
    thesis = (_FUND_STS.get(r.get("fund_state") or "", 4)
              + _TIER_STS.get(r.get("tier") or "", 0)
              + (10 if (r.get("gates_met") or 0) >= 4
                 else 7 if (r.get("gates_met") or 0) == 3
                 else 3 if (r.get("gates_met") or 0) == 2 else 0)
              + (5 if (r.get("rev_streak") or 0) >= 2 else 0)
              + (5 if (r.get("revision_grade") or "")[:1]
                 in ("A", "B") else 0)
              + (5 if r.get("net_cash") else 0))
    tape = (_MOM_STS.get(r.get("mom_state") or "", 5)
            + _DIP_STS.get(r.get("dip_phase") or "", 0))
    vs50 = r.get("vs_sma50")
    if vs50 is not None and vs50 > _EXT_VS50:
        tape -= 15                               # extension tax
    if (r.get("dd52w") or 0) <= _DD_STRUCT:
        tape -= 10                               # structure damage
    return {"thesis": min(thesis, 60),
            "tape": max(min(tape, 40), -25),
            "sts": min(thesis, 60) + max(min(tape, 40), -25)}


def _classify(r: dict[str, Any], broken_days: int = 0,
              prev_sts: Optional[int] = None
              ) -> tuple[str, Optional[str], list[str]]:
    """First-match-wins spec rules on the STS axes. Returns
    (bucket, driver, evidence) — driver splits CUT into
    'thesis' (business broke) vs 'tape' (structure killed)."""
    mom = r.get("mom_state")
    fund = r.get("fund_state")
    tier = r.get("tier")
    promoted = tier in _TIER_PROMOTED
    vs50 = r.get("vs_sma50")
    ext = vs50 is not None and vs50 > _EXT_VS50
    edays = r.get("earn_days")
    sts = (r.get("sts") or {}).get("sts", 0)
    pnl = r.get("pnl_pct")
    rev = r.get("rev_growth")
    ev: list[str] = []

    if tier:
        ev.append(f"{r['engine']}:{tier}" if r.get("engine")
                  else tier)
    if r.get("gates_met") is not None:
        ev.append(f"gates {r['gates_met']}")
    if r.get("rev_streak"):
        ev.append(f"rev streak {r['rev_streak']}q")
    if rev is not None:
        ev.append(f"rev {rev * 100:+.0f}%")
    if r.get("hidden_engine") and isinstance(r["hidden_engine"], dict):
        he = sorted(r["hidden_engine"].items(),
                    key=lambda kv: -(kv[1].get("yoy") or 0))[0]
        ev.append(f"hidden engine {he[0]} "
                  f"{(he[1].get('yoy') or 0) * 100:+.0f}%")
    ev.append(f"sts {sts}")

    # ── CUT·thesis — the business broke (ARK kill criteria +
    # Millennium's auto-terminate on a broken allocation)
    if fund in _FUND_FAIL:
        return ("cut", "thesis", ev +
                [f"fundamentals {fund} — thesis broken"])
    if r.get("demoting"):
        return ("cut", "thesis", ev +
                [f"engine wants {r['demoting']} — tier regressing"])
    if promoted and rev is not None and rev < _REV_FLOOR \
            and (r.get("rev_streak") or 0) == 0:
        return ("cut", "thesis", ev +
                [f"rev {rev * 100:.0f}% under the 15% floor, "
                 "streak gone — the thesis stopped proving"])
    if pnl is not None and pnl <= _PNL_CUT and sts < _STS_HALF:
        # still-proving exception (ARK-style): a validated growth
        # streak + strong fund + street covering it up = the thesis
        # is alive even at −50% — review it, don't auto-cut
        if (r.get("rev_streak") or 0) >= 3 \
                and fund in _FUND_STRONG \
                and (r.get("revision_grade") or "")[:1] in ("A", "B"):
            return ("thesis_check", None, ev +
                    [f"position {pnl:+.0f}% but still proving "
                     f"({r['rev_streak']}q streak · {fund} · grade "
                     f"{r.get('revision_grade')}) — re-underwrite, "
                     "don't auto-cut"])
        return ("cut", "thesis", ev +
                [f"position {pnl:+.0f}% with sts {sts} — the ladder "
                 "doesn't refund broken allocations"])

    # ── CUT·tape — price structure killed it (deep AND persistent,
    # not volatile — spec names swing 20% on nothing)
    if mom in _TAPE_BROKEN and fund not in _FUND_STRONG:
        deep = (r.get("dd52w") or 0) <= _DD_STRUCT
        if deep or broken_days >= _BROKEN_SESS:
            return ("cut", "tape", ev +
                    [f"tape {mom}"
                     + (f", {r['dd52w'] * 100:.0f}% off high" if deep
                        else f" {broken_days} sessions broken")
                     + " — structure failed, not noise"])

    # ── HARVEST — sell a tranche into strength (or the double rule:
    # position doubled → take the house's money back)
    if pnl is not None and pnl >= _PNL_DOUBLE:
        return ("harvest", None, ev +
                [f"position {pnl:+.0f}% — the double rule: bank the "
                 "stake, let the rest ride"])
    if mom in _TAPE_CLIMX or (mom in _TAPE_HOT and ext):
        return ("harvest", None, ev +
                [f"tape {mom}"
                 + (f", +{vs50 * 100:.0f}% vs 50dma" if ext else "")
                 + " — sell a tranche, keep a runner"])

    # ── THESIS CHECK — ARK's weekly review: something is off and
    # gets a deadline, not a lazy hold
    if pnl is not None and pnl <= _PNL_REVIEW:
        return ("thesis_check", None, ev +
                [f"position {pnl:+.0f}% — loss review: re-underwrite "
                 "or exit, don't drift"])
    if edays is not None and edays <= _EARN_CHECK_DAYS:
        return ("thesis_check", None, ev +
                [f"earnings in {edays}d — binary on a spec name"])
    if mom in _TAPE_DEGRADED or mom in _TAPE_BROKEN:
        return ("thesis_check", None, ev +
                [f"tape {mom}"
                 + (f" on {fund} fundamentals" if fund in _FUND_STRONG
                    else "")
                 + " — watch for repair, don't add"])
    if fund in _FUND_COOL:
        return ("thesis_check", None, ev +
                [f"fundamentals {fund} — verify the story"])
    if prev_sts is not None and sts <= prev_sts - _STS_DROP:
        return ("thesis_check", None, ev +
                [f"sts {prev_sts}→{sts} — score declining, review it"])

    # ── BUYS — metrics support the size (ARK); starter discipline
    # otherwise
    if promoted and sts >= _STS_FULL and mom in _TAPE_GOOD \
            and not ext and (edays is None or edays > _EARN_BUY_DAYS) \
            and (r.get("engine") != "5x-scout" or r.get("net_cash")):
        return ("buy_a_lot", None, ev +
                [f"{tier} + sts {sts} + tape {mom} — metrics "
                 "support full size"])
    if sts >= _STS_HALF and mom in (_TAPE_GOOD | _TAPE_HOT) and not ext:
        return ("buy_a_little", None, ev +
                [f"sts {sts} + tape {mom} — starter size while it "
                 "proves"])
    if promoted and sts >= 60:
        return ("runner", None, ev +
                [f"{tier} + sts {sts} — let it work, trail it"])
    return ("hold", None, ev + [f"sts {sts} — nothing set up"])


def spec_symbols() -> set[str]:
    """Symbols the spec board owns via engine membership — promoted
    tiers minus the fortress veto. Portfolio pulse uses this to keep
    the two boards exclusive: a name lives on exactly one."""
    from app.database import db
    rows = db.execute_query("""
        SELECT m.symbol, m.tier, s.op_margin, st.market_cap,
               fw.num_analysts,
               (SELECT expected_fair_value FROM fair_value_v2_runs f
                WHERE f.symbol = m.symbol
                ORDER BY as_of DESC LIMIT 1) AS expected_fair_value
        FROM rule_breaker_members m
        LEFT JOIN LATERAL (
            SELECT op_margin FROM rule_breaker_snapshots x
            WHERE x.symbol = m.symbol
            ORDER BY x.as_of DESC LIMIT 1) s ON true
        LEFT JOIN stocks st ON st.symbol = m.symbol
        LEFT JOIN symbol_flywheel fw ON fw.symbol = m.symbol
        UNION ALL
        SELECT m.symbol, m.tier, s.op_margin, st.market_cap,
               fw.num_analysts,
               (SELECT expected_fair_value FROM fair_value_v2_runs f
                WHERE f.symbol = m.symbol
                ORDER BY as_of DESC LIMIT 1)
        FROM smallcap_members m
        LEFT JOIN LATERAL (
            SELECT op_margin FROM smallcap_snapshots x
            WHERE x.symbol = m.symbol
            ORDER BY x.as_of DESC LIMIT 1) s ON true
        LEFT JOIN stocks st ON st.symbol = m.symbol
        LEFT JOIN symbol_flywheel fw ON fw.symbol = m.symbol""")
    return {r["symbol"] for r in rows
            if r["tier"] in _TIER_PROMOTED and not _fortress(r)}


def board() -> dict[str, Any]:
    """Spec sleeve board: held spec names + watch candidates, each
    with thesis-progress context and the spec action hint."""
    from app.database import db
    from app.market_regime.rotation import _SECTOR_TO_ETF

    rows = db.execute_query("""
        WITH uni AS (
            SELECT s.symbol, SUM(pp.quantity) AS qty,
                   SUM(pp.quantity * pp.avg_price)
                       / NULLIF(SUM(pp.quantity), 0) AS cost,
                   string_agg(DISTINCT p.name, ', ') AS portfolio
            FROM portfolio_positions pp
            JOIN stocks s ON s.id = pp.stock_id
            JOIN portfolios p ON p.id = pp.portfolio_id
            WHERE pp.quantity > 0 AND length(s.symbol) > 1
            GROUP BY s.symbol
            UNION ALL
            SELECT h.symbol, h.shares_held, h.average_cost, p.name
            FROM portfolio_holdings h
            JOIN portfolios p ON p.id = h.portfolio_id
            WHERE h.status IN ('active','inactive')
              AND NOT EXISTS (
                  SELECT 1 FROM portfolio_positions pp
                  JOIN stocks s2 ON s2.id = pp.stock_id
                  WHERE s2.symbol = h.symbol AND pp.quantity > 0)
        ), allpos AS (
            SELECT u.symbol, u.qty, u.cost, u.portfolio,
                   px.close,
                   s.momentum_state, s.momentum_detail,
                   s.fundamental_state, s.revision_grade,
                   s.priced_status, s.emerging_growth,
                   s.next_earnings_date,
                   s.sector, s.market_cap,
                   fw.fwd_pe, fw.num_analysts,
                   fv.expected_fair_value,
                   CASE
                     WHEN fp.is_etf IS NOT NULL THEN fp.is_etf
                     WHEN s.industry ILIKE 'Asset Management%'
                          OR s.company_name ~* '\m(ETF|Fund|Trust)\M'
                       THEN true
                     ELSE false
                   END AS is_etf
            FROM uni u
            LEFT JOIN fmp_company_profiles fp ON fp.symbol = u.symbol
            LEFT JOIN stocks s ON s.symbol = u.symbol
            LEFT JOIN symbol_flywheel fw ON fw.symbol = u.symbol
            LEFT JOIN LATERAL (
                SELECT close FROM daily_bars b
                WHERE b.symbol = u.symbol
                ORDER BY b.date DESC LIMIT 1) px ON true
            LEFT JOIN LATERAL (
                SELECT expected_fair_value FROM fair_value_v2_runs f
                WHERE f.symbol = u.symbol
                ORDER BY f.as_of DESC, f.run_id DESC LIMIT 1) fv ON true
        )
        SELECT a.*,
               rb.tier AS rb_tier, rbs.suggested_tier AS rb_suggested,
               rbs.gates_met AS rb_gates, rbs.rev_streak AS rb_streak,
               rbs.rev_growth AS rb_rev, rbs.op_margin AS rb_opm,
               sc.tier AS sc_tier, scs.op_margin AS sc_opm,
               scs.gates_met AS sc_gates, scs.rev_streak AS sc_streak,
               scs.rev_growth AS sc_rev, scs.hidden_engine,
               scs.net_cash, scs.dd52w,
               hg.score AS gem_score, hg.snap_date AS gem_date
        FROM allpos a
        LEFT JOIN rule_breaker_members rb ON rb.symbol = a.symbol
        LEFT JOIN LATERAL (
            SELECT * FROM rule_breaker_snapshots x
            WHERE x.symbol = a.symbol
            ORDER BY x.as_of DESC LIMIT 1) rbs ON true
        LEFT JOIN smallcap_members sc ON sc.symbol = a.symbol
        LEFT JOIN LATERAL (
            SELECT * FROM smallcap_snapshots x
            WHERE x.symbol = a.symbol
            ORDER BY x.as_of DESC LIMIT 1) scs ON true
        LEFT JOIN LATERAL (
            SELECT score, snap_date FROM hidden_gem_snapshots g
            WHERE g.symbol = a.symbol
            ORDER BY g.snap_date DESC LIMIT 1) hg ON true""")

    held_syms = [r["symbol"] for r in rows]
    broken_map = {r["symbol"]: r["n"] for r in db.execute_query(
        """SELECT symbol, count(*) FILTER (WHERE state = ANY(:b)) n
           FROM (SELECT symbol, state,
                        row_number() OVER (PARTITION BY symbol
                        ORDER BY as_of DESC) rn
                 FROM momentum_state_log
                 WHERE symbol = ANY(:s)) t
           WHERE rn <= 20 GROUP BY symbol""",
        {"s": held_syms,
         "b": list(_TAPE_BROKEN)})}
    prev_sts = {r["symbol"]: r["sts"] for r in db.execute_query(
        """SELECT DISTINCT ON (symbol) symbol, sts
           FROM spec_pulse_evals WHERE as_of < CURRENT_DATE
           AND symbol = ANY(:s)
           ORDER BY symbol, as_of DESC""",
        {"s": held_syms})}

    out, spec_syms, total_val, spec_val = [], set(), 0.0, 0.0
    for r in rows:
        det = r.get("momentum_detail") or {}
        qty = float(r.get("qty") or 0)
        cost = float(r.get("cost") or 0)
        px = float(r["close"]) if r.get("close") is not None else None
        val = qty * (px or 0)
        total_val += val
        if r.get("is_etf"):
            continue                   # funds are never speculative

        rb_t, sc_t = r.get("rb_tier"), r.get("sc_tier")
        tiers = [t for t in (rb_t, sc_t) if t in _TIER_PROMOTED]
        engine = ("rule-breakers" if rb_t in _TIER_PROMOTED else
                  "5x-scout" if sc_t in _TIER_PROMOTED else
                  ("rule-breakers" if rb_t else
                   "5x-scout" if sc_t else "hidden-gems"
                   if r.get("gem_score") else None))
        promoted = bool(tiers) and not _fortress(r)
        unpriced = (r.get("expected_fair_value") is None
                    and ((r.get("num_analysts") or 0) <= 3
                         or (r.get("rb_opm") is not None
                             and r["rb_opm"] < 0))
                    and r.get("sector") not in (None, ""))
        if not (promoted or unpriced):
            continue                       # core name — stays on pulse
        spec_val += val

        tier = rb_t if rb_t in _TIER_PROMOTED else (
            sc_t if sc_t in _TIER_PROMOTED else rb_t or sc_t)
        sug = r.get("rb_suggested")
        demoting = (tier and sug and tier in _TIER_PROMOTED
                    and sug not in _TIER_PROMOTED
                    and sug != tier)

        ned = r.get("next_earnings_date")
        edays = ((ned - __import__("datetime").date.today()).days
                 if ned else None)
        row = {
            "symbol": r["symbol"], "kind": "position",
            "qty": round(qty, 2), "cost": round(cost, 2),
            "portfolio": r.get("portfolio"), "price": px,
            "pnl_pct": (round((px - cost) / cost * 100, 1)
                        if px and cost else None),
            "value": round(val, 0),
            "mom_state": r.get("momentum_state"),
            "vs_sma50": det.get("vs_sma50"),
            "dip_phase": det.get("dip_phase"),
            "atr_pct": det.get("atr_pct"),
            "fund_state": r.get("fundamental_state"),
            "revision_grade": r.get("revision_grade"),
            "emerging_growth": r.get("emerging_growth"),
            "earn_days": edays,
            "engine": engine, "tier": tier or "unpriced",
            "gates_met": (r.get("rb_gates") if engine == "rule-breakers"
                          else r.get("sc_gates")),
            "rev_streak": (r.get("rb_streak") if engine == "rule-breakers"
                           else r.get("sc_streak")),
            "rev_growth": (r.get("rb_rev") if engine == "rule-breakers"
                           else r.get("sc_rev")),
            "hidden_engine": r.get("hidden_engine"),
            "net_cash": r.get("net_cash"),
            "dd52w": r.get("dd52w"),
            "demoting": sug if demoting else None,
            "gem_score": r.get("gem_score"),
        }
        row["sts"] = _score(row)
        b, drv, why = _classify(
            row, broken_map.get(row["symbol"], 0) or 0,
            prev_sts.get(row["symbol"]))
        row["bucket"], row["driver"] = b, drv
        row["why"] = " · ".join(str(x) for x in why)
        spec_syms.add(row["symbol"])
        out.append(row)

    # watch candidates — engine members not currently held
    watch_rows = db.execute_query("""
        SELECT m.symbol, m.tier, 'rule-breakers' AS engine,
               s.suggested_tier, s.gates_met, s.rev_streak,
               s.rev_growth, NULL AS hidden_engine, NULL AS net_cash,
               NULL AS dd52w, s.op_margin,
               st.market_cap, fw.num_analysts,
               (SELECT expected_fair_value FROM fair_value_v2_runs f
                WHERE f.symbol = m.symbol
                ORDER BY as_of DESC LIMIT 1) AS expected_fair_value
        FROM rule_breaker_members m
        LEFT JOIN LATERAL (
            SELECT * FROM rule_breaker_snapshots x
            WHERE x.symbol = m.symbol
            ORDER BY x.as_of DESC LIMIT 1) s ON true
        LEFT JOIN stocks st ON st.symbol = m.symbol
        LEFT JOIN symbol_flywheel fw ON fw.symbol = m.symbol
        WHERE m.symbol <> ALL(:held)
        UNION ALL
        SELECT m.symbol, m.tier, '5x-scout', NULL,
               s.gates_met, s.rev_streak, s.rev_growth,
               s.hidden_engine, s.net_cash, s.dd52w, s.op_margin,
               st.market_cap, fw.num_analysts,
               (SELECT expected_fair_value FROM fair_value_v2_runs f
                WHERE f.symbol = m.symbol
                ORDER BY as_of DESC LIMIT 1)
        FROM smallcap_members m
        LEFT JOIN LATERAL (
            SELECT * FROM smallcap_snapshots x
            WHERE x.symbol = m.symbol
            ORDER BY x.as_of DESC LIMIT 1) s ON true
        LEFT JOIN stocks st ON st.symbol = m.symbol
        LEFT JOIN symbol_flywheel fw ON fw.symbol = m.symbol
        WHERE m.symbol <> ALL(:held)""",
        {"held": list(spec_syms) or ["__none__"]})
    for w in watch_rows:
        if w["symbol"] in spec_syms or _fortress(w):
            continue
        spec_syms.add(w["symbol"])
        trow = {"symbol": w["symbol"], "kind": "watch",
                "tier": w["tier"], "engine": w["engine"],
                "gates_met": w["gates_met"],
                "rev_streak": w["rev_streak"],
                "rev_growth": w["rev_growth"],
                "hidden_engine": w["hidden_engine"],
                "net_cash": w["net_cash"], "dd52w": w["dd52w"],
                "demoting": (w["suggested_tier"]
                             if w["tier"] in _TIER_PROMOTED
                             and w["suggested_tier"]
                             not in _TIER_PROMOTED
                             and w["suggested_tier"] != w["tier"]
                             else None)}
        trow["sts"] = _score(trow)
        b, drv, why = _classify(trow)
        trow["bucket"], trow["driver"] = b, drv
        trow["why"] = " · ".join(str(x) for x in why)
        out.append(trow)

    # tape state for watch names comes from stocks
    need = [w["symbol"] for w in out
            if w["kind"] == "watch" and w.get("mom_state") is None]
    if need:
        mom_map = {r["symbol"]: r for r in db.execute_query(
            "SELECT symbol, momentum_state, momentum_detail,"
            " fundamental_state FROM stocks WHERE symbol = ANY(:s)",
            {"s": need})}
        for w in out:
            if w["kind"] == "watch" and w["symbol"] in mom_map:
                m = mom_map[w["symbol"]]
                w["mom_state"] = m.get("momentum_state")
                w["fund_state"] = m.get("fundamental_state")
                det = m.get("momentum_detail") or {}
                w["vs_sma50"], w["dip_phase"] = (det.get("vs_sma50"),
                                               det.get("dip_phase"))
                w["sts"] = _score(w)         # re-grade with real tape
                b, drv, why = _classify(w)
                w["bucket"], w["driver"] = b, drv
                w["why"] = " · ".join(str(x) for x in why)

    _journal(out)
    counts: dict[str, int] = {}
    for r in out:
        if r["kind"] == "position":
            counts[r["bucket"]] = counts.get(r["bucket"], 0) + 1
    spec_pct = (round(spec_val / total_val * 100, 1)
                if total_val else None)
    # over-cap rotation (Millennium/ARK): when the sleeve exceeds the
    # cap, the weakest theses fund the strongest — the trim list is
    # the lowest-STS positions, not the worst performers
    rotation = []
    if spec_pct is not None and spec_pct > 15:
        rotation = [r["symbol"] for r in sorted(
            (r for r in out if r["kind"] == "position"),
            key=lambda r: (r.get("sts") or {}).get("sts", 0))[:5]]
    try:
        from app.signals.spec_incubator import report as _inc
        candidates = _inc().get("candidates") or []
    except Exception:
        candidates = []
    return {"rows": out,
            "candidates": candidates,
            "sleeve": {"spec_value": round(spec_val, 0),
                       "total_value": round(total_val, 0),
                       "spec_pct": spec_pct,
                       "cap_pct": 15,
                       "counts": counts,
                       "rotation": rotation}}


def _journal(rows: list[dict[str, Any]]) -> None:
    """First-write-per-day eval journal — the training ledger for
    'did the spec buckets predict?'."""
    import json as _json
    from app.database import db
    for r in rows:
        try:
            db.execute_update(
                "INSERT INTO spec_pulse_evals"
                " (as_of, symbol, kind, bucket, tier, engine,"
                "  mom_state, fund_state, gates_met, rev_growth,"
                "  sts, driver, evidence)"
                " VALUES (now()::date, :s, :k, :b, :t, :e, :m, :f,"
                "         :g, :rg, :sts, :drv, CAST(:ev AS jsonb))"
                " ON CONFLICT (as_of, symbol) DO NOTHING",
                {"s": r["symbol"], "k": r["kind"], "b": r["bucket"],
                 "t": r.get("tier"), "e": r.get("engine"),
                 "m": r.get("mom_state"), "f": r.get("fund_state"),
                 "g": r.get("gates_met"), "rg": r.get("rev_growth"),
                 "sts": (r.get("sts") or {}).get("sts"),
                 "drv": r.get("driver"),
                 "ev": _json.dumps({"why": r.get("why")},
                                   default=str)})
        except Exception as exc:
            logger.warning("spec pulse journal %s: %s",
                           r["symbol"], exc)
