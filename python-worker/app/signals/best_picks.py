"""Best-picks engine — evaluates best_picks.yaml over the ACTIVE-TIER
universe (portfolio ∪ watchlist ∪ rule_breaker ∪ smallcap — never the
37k registry) and journals every candidate to best_picks_evals.

The YAML is the policy; this file holds NO business rules, only
mechanics:

  bulk ctx adapter  — one query per source (stock_health.board()
                      pattern); the per-symbol eval is pure dict math.
                      No provider fetches anywhere in this file.
  evaluator         — gates → pillar scoring → adjust → routing caps →
                      tier requirements, conditions interpreted by
                      pulse_engine._eval_when with THIS spec's group set
                      (group names in in/not_in resolve from
                      best_picks.yaml's `groups:` — binding the wrong
                      spec silently degrades them to singletons).
  selection         — A+B fill `top_n` (tier-first, then score); C is
                      the side `watch` lane; gated + X are journaled
                      only and can never occupy a pick slot.

Advisory only — ranked research shortlists with reasons. Nothing here
sizes, orders, or executes.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

import yaml

SPEC_PATH = Path(__file__).parent / "best_picks.yaml"
ENGINE_VERSION = "best_picks.v1"

logger = logging.getLogger(__name__)

_spec: Optional[dict] = None


def _load() -> dict:
    global _spec
    if _spec is None:
        _spec = yaml.safe_load(SPEC_PATH.read_text())
    return _spec


def rules_version() -> str:
    s = _load()
    h = hashlib.sha1(SPEC_PATH.read_bytes()).hexdigest()[:8]
    return f"best_picks.v{s['version']}+{h}"


_SECTIONS = ("growth_swing", "long_term", "compounder_3_5y")
_TIER_ORDER = {"A": 0, "B": 1, "C": 2, "X": 3}


# ---------------- spec lint -------------------------------------------

_COND_VERBS = {"any", "all", "flag", "not_flag", "default"}


def _cond_fields(when: Any) -> set[str]:
    """Fields a `when` block references — same suffix grammar as
    pulse_engine._cond (multi-word suffixes first)."""
    out: set[str] = set()
    if not isinstance(when, dict):
        return out
    for k, v in when.items():
        if k in ("any", "all"):
            for sub in v or []:
                out |= _cond_fields(sub)
        elif k == "any_missing":
            out.update(v or [])
        elif k in _COND_VERBS:
            continue
        else:
            for suf in ("_not_in", "_is_not", "_in", "_is"):
                if k.endswith(suf):
                    out.add(k[:-len(suf)])
                    break
            else:
                base, _, op = k.rpartition("_")
                out.add(base if op in ("gt", "gte", "lt", "lte")
                        else k)
    return out


def lint() -> list[str]:
    """Every field referenced by any `when` must be declared in ctx —
    a rule on an undeclared field is a spec error, not a silent miss."""
    spec = _load()
    declared = set(spec.get("ctx") or {})
    bad: list[str] = []
    for sec in _SECTIONS:
        cfg = spec.get(sec) or {}
        for stage in ("gates", "scoring", "adjust", "routing"):
            for r in cfg.get(stage) or []:
                for f in _cond_fields(r.get("when")):
                    if f not in declared:
                        bad.append(f"{sec}.{stage}: {f}")
        for t in cfg.get("tiers") or []:
            for f in _cond_fields(t.get("require")):
                if f not in declared:
                    bad.append(f"{sec}.tiers: {f}")
    return sorted(set(bad))


# ---------------- ctx adapter -----------------------------------------

def _num(v) -> Optional[float]:
    """finite float or None — same contract as pulse_engine._num."""
    import math
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _j(v) -> Any:
    return json.loads(v) if isinstance(v, str) else v


def _age(ts) -> Optional[int]:
    if ts is None:
        return None
    try:
        d = ts.date() if isinstance(ts, datetime) else ts
        return (date.today() - d).days
    except Exception:
        return None


# momentum-state ordering for tape_dir — same rank map trade_plans
# and the pulse board use (one vocabulary, one direction calc)
_MOM_RANK = {"knife": 0, "capitulation": 1, "breakdown": 2,
             "downtrend": 3, "rolling_over": 3, "basing": 4,
             "stabilizing": 5, "recovery": 6, "pullback": 7,
             "uptrend": 8, "breakout": 9, "climax": 10}


def _bulk_ctx() -> dict[str, dict]:
    """All sources → {symbol: ctx}. One query per source; every join is
    latest-row-per-symbol. Scoped to the active tier via
    symbol_tiers._active_sql()."""
    from app.database import db
    from app.signals import symbol_tiers
    from app.signals import pulse_engine as pe

    active = symbol_tiers._active_sql()
    today = date.today()

    rows = db.execute_query(f"""
        SELECT s.symbol, s.company_name, s.sector, s.industry,
               s.market_cap, s.cyclical,
               s.momentum_state, s.momentum_detail, s.momentum_updated_at,
               s.fundamental_state, s.fundamental_risk,
               s.revision_grade, s.priced_status, s.emerging_growth,
               s.next_earnings_date,
               CASE
                 WHEN fp.is_etf IS NOT NULL THEN fp.is_etf
                 WHEN s.industry ILIKE 'Asset Management%%'
                      OR s.company_name ~* '\\m(ETF|Fund|Trust)\\M'
                   THEN true
                 WHEN s.company_name IS NOT NULL
                      OR s.industry IS NOT NULL
                   THEN false
                 ELSE NULL END AS is_etf,
               px.close,
               w52.hi52, w52.lo52,
               fv.expected_fair_value, fv.scenario_fair_values,
               fv.method_results, fv.regime AS fv_regime,
               gq.score AS gq_score, gq.percentile AS gq_pct,
               gq.components AS gq_components, gq.flags AS gq_flags,
               gq.detail AS gq_detail,
               fw.rev_growth, fw.eps_growth, fw.rev_accel, fw.eps_accel,
               fw.beat_streak, fw.est_revision_pct, fw.fwd_pe,
               fw.fcf_margin, fw.num_analysts, fw.muted_reaction,
               fw.updated_at AS flywheel_at,
               prev.state AS prev_state,
               th.status AS thesis, th.status_dir AS thesis_dir,
               cv.future_score, cv.lane AS conv_lane,
               so.classification AS selloff_class,
               so.tape AS selloff_tape,
               ew.verdict AS last_print,
               sq.verdict AS sq_verdict
        FROM stocks s
        LEFT JOIN fmp_company_profiles fp ON fp.symbol = s.symbol
        LEFT JOIN LATERAL (
            SELECT close FROM daily_bars b
            WHERE b.symbol = s.symbol
            ORDER BY b.date DESC LIMIT 1) px ON true
        LEFT JOIN LATERAL (
            SELECT max(high) AS hi52, min(low) AS lo52 FROM daily_bars b
            WHERE b.symbol = s.symbol
              AND b.date > CURRENT_DATE - 370) w52 ON true
        LEFT JOIN LATERAL (
            SELECT expected_fair_value, scenario_fair_values,
                   method_results, regime
            FROM fair_value_v2_runs f
            WHERE f.symbol = s.symbol
            ORDER BY f.as_of DESC, f.run_id DESC LIMIT 1) fv ON true
        LEFT JOIN LATERAL (
            SELECT score, percentile, components, flags, detail
            FROM growth_quality_runs g
            WHERE g.symbol = s.symbol
            ORDER BY g.as_of DESC, g.id DESC LIMIT 1) gq ON true
        LEFT JOIN symbol_flywheel fw ON fw.symbol = s.symbol
        LEFT JOIN LATERAL (
            SELECT state FROM momentum_state_log l
            WHERE l.symbol = s.symbol AND l.as_of < CURRENT_DATE
            ORDER BY l.as_of DESC LIMIT 1) prev ON true
        LEFT JOIN symbol_thesis th ON th.symbol = s.symbol
        LEFT JOIN LATERAL (
            SELECT future_score, lane FROM conviction_snapshots c
            WHERE c.symbol = s.symbol
            ORDER BY c.snap_date DESC LIMIT 1) cv ON true
        LEFT JOIN LATERAL (
            SELECT classification, tape FROM selloff_candidates so
            WHERE so.symbol = s.symbol
            ORDER BY so.as_of DESC LIMIT 1) so ON true
        LEFT JOIN LATERAL (
            SELECT verdict FROM earnings_watch e
            WHERE e.symbol = s.symbol
            ORDER BY e.earnings_date DESC LIMIT 1) ew ON true
        LEFT JOIN LATERAL (
            SELECT verdict FROM short_squeeze_evals q
            WHERE q.symbol = s.symbol
            ORDER BY q.created_at DESC LIMIT 1) sq ON true
        WHERE s.symbol IN ({active})""")

    # negative HIGH-materiality alerts inside 72h — the veto set
    neg = set()
    try:
        neg = {r["symbol"] for r in db.execute_query(
            "SELECT DISTINCT symbol FROM alert_items"
            " WHERE direction='NEGATIVE' AND materiality='HIGH'"
            " AND created_at > now() - interval '72 hours'")}
    except Exception:
        pass

    # pattern priors — (symbol, pattern_key) → hit_rate_10d; the
    # '__ALL__' pooled row backs symbols with thin history (same
    # n-thresholds prior_for() enforces)
    priors: dict[tuple, dict] = {}
    try:
        for r in db.execute_query(
                "SELECT symbol, pattern_key, n, hit_rate_10d"
                " FROM pattern_priors"):
            priors[(r["symbol"], r["pattern_key"])] = dict(r)
    except Exception:
        pass

    # memberships — the `member` ctx field
    try:
        rb = {r["symbol"] for r in db.execute_query(
            "SELECT symbol FROM rule_breaker_members")}
        sc = {r["symbol"] for r in db.execute_query(
            "SELECT symbol FROM smallcap_members")}
        from app.signals import focus_intel
        fo = set(focus_intel.members() or [])
    except Exception:
        rb, sc, fo = set(), set(), set()

    # tailwinds — strongest active channel tier per symbol
    tw: dict[str, str] = {}
    try:
        for r in db.execute_query(
                "SELECT DISTINCT ON (t.symbol) t.symbol, t.tier"
                " FROM tailwinds t WHERE t.status='active'"
                " ORDER BY t.symbol,"
                " CASE t.tier WHEN 'revenue' THEN 0"
                " WHEN 'shipping' THEN 1 WHEN 'announced' THEN 2"
                " ELSE 3 END, t.hit_count DESC"):
            tw[r["symbol"]] = r["tier"]
    except Exception:
        pass

    # sector flow — same cached map the pulse board / health board use
    flow, sec2etf = {}, {}
    try:
        from app.api.board_api import _sector_flow_map, _SECTOR_TO_ETF
        flow = _sector_flow_map() or {}
        sec2etf = _SECTOR_TO_ETF
    except Exception:
        pass

    # posture — regime permission. An absent snapshot is MISSING
    # (None), not True: the spec's posture gate must fail loud.
    new_longs: Optional[bool] = None
    try:
        from app.signals import posture
        cur = posture.current() or {}
        if cur.get("posture") and cur["posture"] != "unknown":
            new_longs = bool(cur.get("new_longs"))
    except Exception:
        pass

    # rev_class map — borrowed from pulse_action_rules (single source
    # for letter→class semantics)
    rev_map = ((pe._load().get("computed") or {})
               .get("rev_class") or {}).get("map") or {}
    rev_fallback = ((pe._load().get("computed") or {})
                    .get("rev_class") or {}) \
        .get("unmapped_non_null", "malformed")

    def _rev_class(rev: Optional[str]) -> str:
        g = pe._norm_grade(rev)
        if g is None:
            return "missing"
        for cls, grades in rev_map.items():
            if cls != "missing" and g in grades:
                return cls
        return rev_fallback

    out: dict[str, dict] = {}
    for r in rows:
        sym = r["symbol"]
        det = _j(r.get("momentum_detail")) or {}
        sw = det.get("swing") if isinstance(det.get("swing"), dict) else {}
        gq_flags = _j(r.get("gq_flags")) or []
        gq_comp = _j(r.get("gq_components")) or {}
        gq_det = _j(r.get("gq_detail")) or {}
        gq_known = r.get("gq_score") is not None or gq_flags or gq_det
        lev_flag = any(str(f).startswith("leverage") for f in gq_flags)

        px = _num(r.get("close"))
        hi52, lo52 = _num(r.get("hi52")), _num(r.get("lo52"))

        # valuation — expected FV vs TODAY'S close; validity contract
        # identical to pulse (finite, |fv| ≤ 75)
        efv = _num(r.get("expected_fair_value"))
        fv = round((efv / px - 1) * 100, 1) if efv and px else None
        fv_valid = fv is not None and abs(fv) <= 75
        mrs = _j(r.get("method_results")) or []
        fv_methods = sum(
            1 for m in mrs
            if isinstance(m, dict) and m.get("status") == "ok"
            and _num(m.get("fair_value")) is not None)
        scen = _j(r.get("scenario_fair_values")) or {}
        bear, bull = _num(scen.get("bear")), _num(scen.get("bull"))
        fv_asym = (round((bull - px) / (px - bear), 2)
                   if bull is not None and bear is not None and px
                   and px > bear else None)
        fv_rel = ("corroborated" if fv_methods >= 2 else
                  "single" if fv_methods == 1 else "none")

        # stop geometry — same choice chain as pulse stage0 /
        # trade_plans (swing_low → prior_low → 2×ATR → −8%)
        atr = _num(det.get("atr_pct"))
        stop = _num(sw.get("swing_low")) or _num(sw.get("prior_low"))
        if stop is None and px and atr:
            stop = px * (1 - 2 * atr)
        elif stop is None and px:
            stop = px * 0.92
        risk_atr = (round(abs(px - stop) / (px * atr), 2)
                    if px and stop and atr else None)
        confirm = _num(sw.get("confirm_level"))
        rr = (round((confirm - px) / (px - stop), 2)
              if confirm and px and stop and px > stop else None)

        tape = r.get("momentum_state")
        if tape in (None, "", "unknown", "—"):
            tape = None
        prev = r.get("prev_state")
        cur_r, prv_r = _MOM_RANK.get(tape), _MOM_RANK.get(prev)
        tape_dir = ("improving" if prv_r is not None and cur_r > prv_r
                    else "degrading"
                    if prv_r is not None and cur_r is not None
                    and cur_r < prv_r
                    else "flat" if prv_r is not None else None)

        ne = r.get("next_earnings_date")
        earn_days = ((ne.date() if hasattr(ne, "date") else ne)
                     - today).days if ne else None

        eps_g = _num(r.get("eps_growth"))
        fwd_pe = _num(r.get("fwd_pe"))
        peg = (round(fwd_pe / (eps_g * 100), 2)
               if fwd_pe is not None and eps_g and eps_g > 0 else None)

        prior_key = f"{tape}|{det.get('dip_phase') or 'none'}"
        pr = priors.get((sym, prior_key))
        hit_rate = _num(pr["hit_rate_10d"]) \
            if pr and (pr.get("n") or 0) >= 4 else None
        if hit_rate is None:
            pr = priors.get(("__ALL__", prior_key))
            hit_rate = _num(pr["hit_rate_10d"]) \
                if pr and (pr.get("n") or 0) >= 8 else None

        selloff_tape = _j(r.get("selloff_tape")) or {}
        member = ("rule_breaker" if sym in rb else
                  "smallcap" if sym in sc else
                  "focus" if sym in fo else "none")

        out[sym] = {
            # tape
            "tape": tape, "tape_dir": tape_dir,
            "dip_phase": det.get("dip_phase"),
            "rsi": _num(det.get("rsi")),
            "vs50": _num(det.get("vs_sma50")),
            "pct_b": _num(det.get("pct_b")),
            "hist_dir": _num(det.get("hist_dir")),
            "atr_pct": atr, "rs_pct": _num(det.get("rs_pct")),
            "off_high": round(px / hi52 - 1, 4)
                        if px and hi52 else None,
            "off_low": round(px / lo52 - 1, 4)
                       if px and lo52 else None,
            "dd_60d": _num(selloff_tape.get("dd_60d")),
            "swing_struct": bool(sw.get("hl_seq") or sw.get("phase")
                                 or sw.get("confirm_level")),
            "swing_phase": sw.get("phase"),
            "confirm_level": confirm,
            "swing_low": _num(sw.get("swing_low")),
            "prior_low": _num(sw.get("prior_low")),
            "risk_atr": risk_atr, "rr": rr,
            "hit_rate": hit_rate,
            "sector_score": _num((flow.get(sec2etf.get(
                (r.get("sector") or "").lower(), "")) or {})
                .get("score")),
            "tape_fields_missing": sum(
                1 for k in ("rsi", "pct_b", "hist_dir", "vs_sma50")
                if det.get(k) is None),
            # fundamentals
            "fund": r.get("fundamental_state"),
            "fund_risk": r.get("fundamental_risk"),
            "cyclical": bool(
                r.get("cyclical") or "cyclical" in gq_flags
                or str(r.get("fv_regime") or "")
                .startswith("cyclical")),
            "rev": pe._norm_grade(r.get("revision_grade")),
            "rev_class": _rev_class(r.get("revision_grade")),
            "priced": r.get("priced_status"),
            # stocks.emerging_growth is a TEXT tier
            # (material|emerging|option|NULL — compute_uplift writes
            # NULL explicitly), not a bool — any stored tier means the
            # emerging-growth flag is on; NULL means it checked negative
            "emerging": r.get("emerging_growth") in
                        ("material", "emerging", "option"),
            "rev_growth": _num(r.get("rev_growth")),
            "eps_growth": eps_g,
            "rev_accel": _num(r.get("rev_accel")),
            "eps_accel": _num(r.get("eps_accel")),
            "est_rev": _num(r.get("est_revision_pct")),
            "beat_streak": _num(r.get("beat_streak")),
            "fwd_pe": fwd_pe, "peg": peg,
            "fcf_margin": _num(r.get("fcf_margin")),
            "num_analysts": _num(r.get("num_analysts")),
            "muted_reaction": (bool(r["muted_reaction"])
                               if r.get("muted_reaction") is not None
                               else None),
            "leverage_ok": (not lev_flag) if gq_known else None,
            "dilution_ok": (("dilutive" not in gq_flags)
                            if gq_known else None),
            "tailwind": tw.get(sym),
            # valuation
            "fv": fv, "fv_valid": fv_valid,
            "fv_methods": fv_methods if mrs else (0 if efv else None),
            "fv_asym": fv_asym, "fv_reliability": fv_rel,
            # quality / thesis / events
            "gq_score": _num(r.get("gq_score")),
            "gq_pct": _num(r.get("gq_pct")),
            "structural_proof": _num(gq_comp.get("structural_proof")),
            "margin_trend": _num(gq_det.get("margin_trend")),
            "gq_flags": gq_flags,
            "hard_risk_active": ("fcf_negative" in gq_flags or lev_flag)
                                if gq_known else False,
            "risk_unverifiable": not gq_known,
            "thesis": r.get("thesis"), "thesis_dir": r.get("thesis_dir"),
            "last_print": r.get("last_print"),
            "future_score": _num(r.get("future_score")),
            "conv_lane": r.get("conv_lane"),
            "selloff_class": r.get("selloff_class"),
            "sq_verdict": r.get("sq_verdict"),
            "earn_days": earn_days,
            "alert_neg_72h": sym in neg,
            "member": member,
            "momentum_age_days": _age(r.get("momentum_updated_at")),
            "flywheel_age_days": _age(r.get("flywheel_at")),
            "is_etf": r.get("is_etf"),
            "new_longs": new_longs,
            # display context (not rule inputs)
            "_name": r.get("company_name"),
            "_sector": r.get("sector"),
            "_px": px,
            "_mcap_b": round((r.get("market_cap") or 0) / 1e9, 1)
                       if r.get("market_cap") else None,
        }
    return out


# ---------------- evaluator -------------------------------------------

def _render(t: Optional[str], c: dict) -> Optional[str]:
    """Render {field} placeholders in spec why/note text; absent
    fields render '—' (never raise)."""
    if not t:
        return t
    class _S(dict):
        def __missing__(self, k):
            return "—"
    try:
        return " ".join(str(t).format_map(_S(c)).split())
    except Exception:
        return t


def _eval_section(sec_cfg: dict, c: dict) -> dict:
    """One section × one symbol → journal dict.
    Order is fixed and down-only: gates → score → routing caps →
    tier requires. Nothing promotes a name."""
    from app.signals import pulse_engine as pe
    groups = _load().get("groups") or {}
    missing: set[str] = set()

    # 1 — gates: first-match-wins veto
    for g in sec_cfg.get("gates") or []:
        ok, log = pe._eval_when(c, g.get("when") or {}, groups)
        missing.update(log["missing"])
        if ok:
            return {"gated": True, "gate": g["name"],
                    "reason": _render(g.get("why"), c),
                    "tier": "X", "label": "gated",
                    "score": None, "pillars": {}, "hits": [],
                    "routing": [g["name"]],
                    "missing": sorted(missing)}

    # 2 — scoring: pillar sums, capped; every fired rule journals its
    # note so the audit trail explains the number
    pillars: dict[str, float] = {}
    hits: list[str] = []
    for r in sec_cfg.get("scoring") or []:
        ok, log = pe._eval_when(c, r.get("when") or {}, groups)
        missing.update(log["missing"])
        if ok:
            p = r.get("pillar") or "_unassigned"
            pillars[p] = pillars.get(p, 0) + (r.get("pts") or 0)
            hits.append(_render(r.get("note"), c) or "")
    caps = {}
    for r in sec_cfg.get("scoring") or []:
        p = r.get("pillar")
        if p:
            caps[p] = r.get("cap")
    pillars = {p: min(v, caps[p]) if caps.get(p) is not None else v
               for p, v in pillars.items()}
    score = sum(pillars.values())

    # 3 — adjust: additive modifiers after pillars
    for a in sec_cfg.get("adjust") or []:
        ok, log = pe._eval_when(c, a.get("when") or {}, groups)
        missing.update(log["missing"])
        if ok:
            score += a.get("pts") or 0
            n = _render(a.get("note"), c)
            if n:
                hits.append(n)

    # 4 — routing: demotion caps + labels; never promotes
    routing: list[str] = []
    tier_cap: Optional[str] = None
    for r in sec_cfg.get("routing") or []:
        ok, log = pe._eval_when(c, r.get("when") or {}, groups)
        missing.update(log["missing"])
        if ok:
            routing.append(r.get("label") or "routed")
            cap = r.get("tier_cap")
            if cap and (tier_cap is None
                        or _TIER_ORDER[cap] > _TIER_ORDER[tier_cap]):
                tier_cap = cap

    # 5 — tiers: top-down; a failed `require` demotes to the next tier
    tier, label, note = "X", "reject", "below bar"
    for t in sec_cfg.get("tiers") or []:
        if score < (t.get("min") or 0):
            continue
        req = t.get("require")
        if req:
            ok, log = pe._eval_when(c, req, groups)
            missing.update(log["missing"])
            if not ok:
                continue          # demote — never promote
        tier, label = t["tier"], t.get("label")
        note = _render(t.get("note"), c)
        break
    if tier_cap and _TIER_ORDER[tier] < _TIER_ORDER[tier_cap]:
        tier = tier_cap           # routing cap binds after requires

    return {"gated": False, "gate": None, "reason": note,
            "tier": tier, "label": label, "score": round(score, 1),
            "pillars": pillars, "hits": hits, "routing": routing,
            "missing": sorted(missing)}


# ---------------- run + read ------------------------------------------

def _journal(rows: list[dict]) -> None:
    from app.database import db
    db.execute_many(
        "INSERT INTO best_picks_evals"
        " (as_of, section, symbol, score, tier, lane, label,"
        "  routing, gate, reason, pillars, hits, missing,"
        "  ctx_snapshot, rules_version)"
        " VALUES (CURRENT_DATE, :sec, :sym, :score, :tier, :lane,"
        "  :label, CAST(:routing AS jsonb), :gate, :reason,"
        "  CAST(:pillars AS jsonb), CAST(:hits AS jsonb),"
        "  CAST(:missing AS jsonb), CAST(:ctx AS jsonb), :rv)"
        " ON CONFLICT (as_of, section, symbol) DO NOTHING",
        rows)


def run() -> dict:
    """Evaluate all three sections over the active universe, journal
    every candidate, return the plan-page payload."""
    spec = _load()
    undeclared = lint()
    if undeclared:
        raise RuntimeError(f"best_picks spec references undeclared "
                           f"ctx fields: {undeclared}")

    ctxs = _bulk_ctx()
    rv = rules_version()
    journal_rows: list[dict] = []
    sections: dict[str, dict] = {}

    for sec_name in _SECTIONS:
        cfg = spec[sec_name]
        sel = cfg.get("selection") or {}
        include = sel.get("include_tiers") or ["A", "B"]
        side = (sel.get("side_lane") or "C")
        top_n = (cfg.get("output") or {}).get("top_n") or 10

        picks: list[dict] = []
        watch: list[dict] = []
        excluded = 0
        for sym, c in ctxs.items():
            try:
                e = _eval_section(cfg, c)
            except Exception as exc:
                logger.warning("best_picks %s/%s eval failed: %r",
                               sec_name, sym, exc)
                continue
            lane = ("excluded" if e["gated"] or e["tier"] == "X"
                    else "pick" if e["tier"] in include
                    else "watch" if e["tier"] == side
                    else "excluded")
            journal_rows.append({
                "sec": sec_name, "sym": sym,
                "score": e["score"], "tier": e["tier"],
                "lane": lane, "label": e["label"],
                "routing": json.dumps(e["routing"]),
                "gate": e["gate"], "reason": e["reason"],
                "pillars": json.dumps(e["pillars"]),
                "hits": json.dumps(e["hits"]),
                "missing": json.dumps(e["missing"]),
                "ctx": json.dumps(c, default=str),
                "rv": rv})
            if lane == "excluded":
                excluded += 1
                continue
            row = {"symbol": sym, "name": c.get("_name"),
                   "sector": c.get("_sector"), "px": c.get("_px"),
                   "mcap_b": c.get("_mcap_b"),
                   "score": e["score"], "tier": e["tier"],
                   "label": e["label"], "routing": e["routing"],
                   "reason": e["reason"],
                   "pillars": e["pillars"],
                   "fv": c.get("fv"), "fv_reliability":
                       c.get("fv_reliability"),
                   "mom": c.get("tape"), "fund": c.get("fund"),
                   "thesis": c.get("thesis"),
                   "selloff": c.get("selloff_class"),
                   "missing": e["missing"]}
            (picks if lane == "pick" else watch).append(row)
        t_ord = lambda r: (_TIER_ORDER.get(r["tier"], 9),
                           -(r["score"] or 0), r["symbol"])
        picks.sort(key=t_ord)
        watch.sort(key=t_ord)
        sections[sec_name] = {
            "horizon": cfg.get("horizon"),
            "picks": picks[:top_n],
            "watch": watch[:top_n],
            "counts": {"picks": len(picks), "watch": len(watch),
                       "excluded": excluded}}

    _journal(journal_rows)
    return {"as_of": str(date.today()), "rules_version": rv,
            "sections": sections, "evaluated": len(ctxs)}


def latest() -> dict:
    """The most recent journaled pass → same payload shape as run().
    The plan page reads the journal, never re-evaluates. Degrades to
    an empty payload when the table hasn't been migrated yet — a
    missing journal is 'no eval yet', not a 500."""
    from app.database import db
    try:
        last = db.execute_query(
            "SELECT max(as_of) AS d FROM best_picks_evals")
    except Exception as exc:
        logger.warning("best_picks_evals unreadable: %s", exc)
        return {"as_of": None, "sections": {}}
    if not last or not last[0]["d"]:
        return {"as_of": None, "sections": {}}
    as_of = last[0]["d"]
    meta = db.execute_query(
        "SELECT count(*) AS n, max(rules_version) AS rv"
        " FROM best_picks_evals WHERE as_of = :d", {"d": as_of})
    rows = db.execute_query(
        "SELECT section, symbol, score, tier, lane, label, routing,"
        " gate, reason, pillars, missing,"
        " ctx_snapshot->>'_name' AS name,"
        " ctx_snapshot->>'_sector' AS sector,"
        " ctx_snapshot->>'_px' AS px,"
        " ctx_snapshot->>'_mcap_b' AS mcap_b,"
        " ctx_snapshot->>'fv' AS fv,"
        " ctx_snapshot->>'fv_reliability' AS fv_reliability,"
        " ctx_snapshot->>'tape' AS mom,"
        " ctx_snapshot->>'fund' AS fund,"
        " ctx_snapshot->>'thesis' AS thesis,"
        " ctx_snapshot->>'selloff_class' AS selloff"
        " FROM best_picks_evals WHERE as_of = :d",
        {"d": as_of})
    spec = _load()
    sections: dict[str, dict] = {}
    for sec_name in _SECTIONS:
        cfg = spec.get(sec_name) or {}
        top_n = (cfg.get("output") or {}).get("top_n") or 10
        picks: list[dict] = []
        watch: list[dict] = []
        excluded = 0
        for r in rows:
            if r["section"] != sec_name:
                continue
            if r["lane"] == "excluded":
                excluded += 1
                continue
            row = {"symbol": r["symbol"], "name": r.get("name"),
                   "sector": r.get("sector"),
                   "px": _num(r.get("px")),
                   "mcap_b": _num(r.get("mcap_b")),
                   "score": _num(r.get("score")),
                   "tier": r["tier"], "label": r.get("label"),
                   "routing": _j(r.get("routing")) or [],
                   "reason": r.get("reason"),
                   "pillars": _j(r.get("pillars")) or {},
                   "fv": _num(r.get("fv")),
                   "fv_reliability": r.get("fv_reliability"),
                   "mom": r.get("mom"), "fund": r.get("fund"),
                   "thesis": r.get("thesis"),
                   "selloff": r.get("selloff"),
                   "missing": _j(r.get("missing")) or []}
            (picks if r["lane"] == "pick" else watch).append(row)
        t_ord = lambda r: (_TIER_ORDER.get(r["tier"], 9),
                           -(r["score"] or 0), r["symbol"])
        picks.sort(key=t_ord)
        watch.sort(key=t_ord)
        sections[sec_name] = {"horizon": cfg.get("horizon"),
                              "picks": picks[:top_n],
                              "watch": watch[:top_n],
                              "counts": {"picks": len(picks),
                                         "watch": len(watch),
                                         "excluded": excluded}}
    return {"as_of": str(as_of), "sections": sections,
            "rules_version": (meta[0].get("rv") if meta else None),
            "evaluated": int(meta[0]["n"] / 3) if meta and
                        meta[0].get("n") else 0}
