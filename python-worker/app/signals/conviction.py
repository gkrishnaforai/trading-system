"""Conviction List — the meta-engine. Every engine feeds candidates;
this scores them like an adviser would and journals The List nightly.

Candidate pool (the "all our engines" union):
  hidden_gem_snapshots · daily_calls · mover_snapshots (passed) ·
  rule_breaker_members · symbol_flywheel top by gap/eps · theme
  members of the leading sectors.

Score 0-100, adviser criteria:
  growth      30  eps_growth / rev_growth / rev_accel / beat_streak /
                  est_revision_pct — the expectation engine
  quality     20  LTM ROE / FCF / dilution / debt from
                  fundamental_quarterly — real, not proxy
  tape        20  momentum_state + distance off 52w high + vs_sma50
  consensus   15  how many engines surfaced it today
  theme_money 15  sector/theme rotation score (money-flow weighted)

Lanes — the user's rule made mechanical:
  deploy   fundamentals right + valuation reasonable + tape confirms
           → "current investment" (momentum NOW)
  watch    fundamentals right but fwd_pe extreme or tape unconfirmed
           → "future" bucket — early-NVDA/PLTR shelf. Expensive stays
           watch, never deploy.

Cadence:
  daily    top-5 List + best-2 flagged (daily_pick)
  Friday   weekly_pick — the week's most persistent high scorer
  month-end monthly_pick — top-2 for next month
Journal rows carry ret_5d/20d/60d + vs_spy_20d — graded as they
mature, so "how are the picks doing" is a query, not a memory.
"""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from typing import Any, Optional

logger = logging.getLogger(__name__)

ENGINE_VERSION = "conv_v1"

_MOM_SCORE = {"breakout": 20, "climax": 16, "uptrend": 14,
              "rolling_over": 8, "recovery": 10, "basing": 9,
              "pullback": 12, "knife": 0, "capitulation": 2,
              "breakdown": 1, "downtrend": 3, "unknown": 5}
_BROKEN = {"knife", "capitulation", "breakdown", "downtrend"}

# ------------------------------------------------------------------
# FUTURE THESES — "what does the future need, and who sells it".
# The thesis list is deliberately curated (human judgment, like Motley
# Fool's thesis teams — the engine validates exposure with numbers,
# it doesn't invent narratives). Each theme:
#   stage    emerging | inflecting | mainstream — earlier = more
#            headroom, and a bigger slice of the future score
#   members  symbol → exposure: 'pure' (the product IS the thesis —
#            VRT cooling, MU HBM) | 'derivative' (sells into it but
#            has other businesses — ETN, ARM)
# ------------------------------------------------------------------
FUTURE_THEMES = {
    "ai_inference": {
        "name": "AI inference silicon & edge",
        "thesis": "training built the GPUs; inference volume runs "
                  "forever — edge/custom/accelerator chips compound",
        "stage": "inflecting",
        "members": {"ALAB": "pure", "MRVL": "pure", "ARM": "pure",
                    "QCOM": "derivative", "AVGO": "derivative",
                    "MU": "derivative", "TSM": "derivative"}},
    "ai_optics": {
        "name": "Optical interconnect / CPO",
        "thesis": "GPU clusters outgrow copper — co-packaged optics "
                  "and lasers become the bottleneck product",
        "stage": "emerging",
        "members": {"COHR": "pure", "LITE": "pure", "FN": "pure",
                    "CIEN": "derivative", "MRVL": "derivative",
                    "ALAB": "derivative", "AVGO": "derivative"}},
    "dc_power_cooling": {
        "name": "DC power & cooling",
        "thesis": "MW/rack is exploding — liquid cooling, power "
                  "conversion and backup are mandatory picks/shovels",
        "stage": "inflecting",
        "members": {"VRT": "pure", "MOD": "pure", "TT": "pure",
                    "POWL": "pure", "NVT": "derivative",
                    "ETN": "derivative", "JCI": "derivative"}},
    "grid_electrification": {
        "name": "Grid & electrification",
        "thesis": "AI load + reshoring overload a 50-year-old grid — "
                  "transformers, switchgear, EPC firms see decades "
                  "of backlog",
        "stage": "inflecting",
        "members": {"PWR": "pure", "GEV": "pure", "ETN": "pure",
                    "POWL": "derivative", "VRT": "derivative"}},
    "hbm_memory": {
        "name": "HBM & AI memory chain",
        "thesis": "every accelerator ships with more HBM; supply is "
                  "constrained and pricing power follows demand",
        "stage": "inflecting",
        "members": {"MU": "pure", "SNDK": "pure", "WDC": "derivative",
                    "AMAT": "derivative", "LRCX": "derivative",
                    "KLAC": "derivative", "ONTO": "pure",
                    "CAMT": "pure", "ACMR": "derivative"}},
    "robotics_edge": {
        "name": "Robotics & physical AI",
        "thesis": "inference leaves the data center — warehouse "
                  "robots, humanoids, machine vision",
        "stage": "emerging",
        "members": {"SYM": "pure", "SERV": "pure", "ISRG": "pure",
                    "TER": "derivative", "FANUY": "derivative"}},
    "ai_software": {
        "name": "AI software monetization",
        "thesis": "the capex must earn — platforms that convert AI "
                  "spend into enterprise revenue",
        "stage": "inflecting",
        "members": {"PLTR": "pure", "RBRK": "pure", "SNOW": "pure",
                    "DDOG": "derivative", "CRWD": "derivative",
                    "NOW": "derivative", "CRM": "derivative"}},
    "space_defense": {
        "name": "Space, launch & defense tech",
        "thesis": "launch costs collapse + defense autonomy budgets "
                  "expand — dual-use demand",
        "stage": "emerging",
        "members": {"RKLB": "pure", "PL": "pure", "LUNR": "pure",
                    "AVAV": "pure", "KTOS": "derivative"}},
}
_STAGE_W = {"emerging": 30, "inflecting": 24, "mainstream": 15,
            "watching": 10}
_EXPO_W = {"pure": 1.0, "derivative": 0.55, "speculative": 0.35}


def _future(sym: str, f: dict, q: dict,
            mcap: Optional[float]) -> tuple[float, list[str]]:
    """0-95 future-compounder score — 'small now, huge TAM later'.
    Theme exposure is the gate (first select the future), then
    evidence that it's already showing in the numbers, then the
    headroom math NVDA-2019 had: small mcap vs a thesis that runs
    for a decade."""
    # DB registry is the truth (seeds from FUTURE_THEMES, LLM/quarterly
    # review can add and restage); code dict is the fallback
    from app.signals.future_themes import registry
    memberships = [(t, t["members"][sym]) for t in
                   registry().values() if sym in t["members"]]
    if not memberships:
        # no theme tag — but a corroborated channel still counts as
        # future evidence, capped low (no thesis framing behind it)
        from app.signals import tailwinds as _tw
        b = _tw.bonus(sym)
        return (round(min(15.0, max(0.0, b)), 1),
                [f"tailwind +{b:.0f}"] if b >= 2 else
                ([f"headwind {b:.0f}"] if b <= -2 else []))
    memberships.sort(key=lambda x: -_STAGE_W.get(x[0]["stage"], 8))
    top, e = memberships[0]
    s = _STAGE_W.get(top["stage"], 8) * _EXPO_W.get(e, 0.4)
    if len(memberships) > 1:
        s += 5                         # multi-thesis exposure
    s += _growth_score(f) * 0.83       # evidence — ≤25
    if mcap:
        s += (20 if mcap < 2e9 else 15 if mcap < 10e9 else
              10 if mcap < 50e9 else 5 if mcap < 200e9 else 0)
    s += _quality_score(q) * 0.75      # ≤15 — early names get some
    from app.signals import tailwinds as _tw
    tw_b = _tw.bonus(sym)              # ±10 — pre-revenue channels
    s += tw_b
    names = [f"{t['name']}({e[:4]})" for t, e in memberships]
    if tw_b >= 2:
        names.append(f"tailwind +{tw_b:.0f}")
    elif tw_b <= -2:
        names.append(f"headwind {tw_b:.0f}")
    return round(min(95.0, max(0.0, s)), 1), names


def _pool(today: date) -> dict[str, dict]:
    """Union of every engine's candidates → {symbol: {sources, raw}}."""
    from app.database import db
    pool: dict[str, dict] = {}

    def add(sym: str, src: str, **kw):
        e = pool.setdefault(sym.upper(), {"sources": []})
        e["sources"].append(src)
        e.update(kw)

    for r in db.execute_query(
            "SELECT symbol, score, aligned FROM hidden_gem_snapshots"
            " WHERE snap_date=:d AND score >= 40", {"d": today}):
        add(r["symbol"], "gems", gem_score=r["score"])
    for r in db.execute_query(
            "SELECT symbol, score, rank FROM daily_calls"
            " WHERE call_date=:d", {"d": today}):
        add(r["symbol"], "calls", call_rank=r["rank"])
    for r in db.execute_query(
            "SELECT symbol, verdict, change_pct FROM mover_snapshots"
            " WHERE as_of_date=:d AND passed > 0", {"d": today}):
        add(r["symbol"], "movers", mover_verdict=r["verdict"])
    for r in db.execute_query(
            "SELECT symbol, tier FROM rule_breaker_members"):
        add(r["symbol"], "rule_breaker", rb_tier=r["tier"])
    for r in db.execute_query(
            "SELECT symbol, gap_score FROM symbol_flywheel"
            " WHERE gap_score IS NOT NULL"
            " ORDER BY gap_score DESC LIMIT 30"):
        add(r["symbol"], "flywheel")
    # future-thesis members are candidates by construction — the
    # 'first select the areas' leg; engines don't have to surface them
    from app.signals.future_themes import registry
    for t in registry().values():
        for s in t["members"]:
            add(s, "future_thesis")
    return pool


def _theme_map() -> dict[str, dict]:
    """Latest strategy snapshot → per-symbol theme score/name — the
    sector money-movement input (flows weighted in theme_scores)."""
    from app.database import db
    out = {}
    try:
        r = db.execute_query(
            "SELECT payload FROM strategy_snapshots"
            " ORDER BY snap_date DESC LIMIT 1")
        if r:
            p = r[0]["payload"]
            p = p if isinstance(p, dict) else json.loads(p)
            for t in p.get("themes") or []:
                for s in t.get("members") or []:
                    out[s] = {"theme": t["name"], "theme_key": t["key"],
                              "theme_score": t["score"],
                              "money_flow": (t.get("parts") or {})
                              .get("money_flow")}
    except Exception as exc:
        logger.debug("theme map: %s", exc)
    return out


def _quality(sym: str) -> dict[str, Optional[float]]:
    """Real LTM fundamentals from the quarterly journal."""
    from app.database import db
    try:
        rows = db.execute_query(
            "SELECT net_income, free_cf, revenue, equity, total_debt,"
            " shares_diluted FROM fundamental_quarterly"
            " WHERE symbol=:s ORDER BY period_end DESC LIMIT 5",
            {"s": sym})
    except Exception:
        return {}
    if not rows:
        return {}
    ltm = rows[:4]
    ni = sum(r["net_income"] for r in ltm
             if r.get("net_income") is not None) or None
    fcf = sum(r["free_cf"] for r in ltm
              if r.get("free_cf") is not None) or None
    rev = sum(r["revenue"] for r in ltm
              if r.get("revenue") is not None) or None
    eq = rows[0].get("equity")
    dil = None
    if len(rows) >= 5 and rows[0].get("shares_diluted") and \
            rows[4].get("shares_diluted"):
        dil = rows[0]["shares_diluted"] / rows[4]["shares_diluted"] - 1
    return {"net_income_ltm": ni, "free_cf_ltm": fcf, "rev_ltm": rev,
            "roe": (ni / eq if ni and eq else None),
            "fcf_margin": (fcf / rev if fcf is not None and rev else None),
            "dilution": dil,
            "debt_to_equity": (rows[0].get("total_debt") / eq
                               if rows[0].get("total_debt") and eq
                               else 0)}


def _growth_score(f: dict) -> float:
    """0-30: expectation engine."""
    s = 0.0
    eg, rg = f.get("eps_growth"), f.get("rev_growth")
    ra, bs = f.get("rev_accel"), f.get("beat_streak") or 0
    rev = f.get("est_revision_pct")
    if eg is not None:
        s += 8 if eg >= 0.5 else 6 if eg >= 0.25 else 3 if eg > 0 else 0
    if rg is not None:
        s += 7 if rg >= 0.4 else 5 if rg >= 0.2 else 2 if rg > 0 else 0
    if ra is not None:
        s += 5 if ra > 0.05 else 2.5 if ra > 0 else 0
    s += min(5, bs * 1.25)
    if rev is not None:
        s += 5 if rev > 0.10 else 3 if rev > 0 else 0
    return min(30.0, s)


def _quality_score(q: dict) -> float:
    """0-20: real balance-sheet/fundamental quality."""
    s = 0.0
    if q.get("roe") is not None:
        s += 7 if q["roe"] >= 0.25 else 5 if q["roe"] >= 0.12 \
            else 2 if q["roe"] > 0 else 0
    if q.get("fcf_margin") is not None:
        s += 7 if q["fcf_margin"] >= 0.15 else 4 if q["fcf_margin"] > 0 \
            else 0
    dil = q.get("dilution")
    if dil is not None:
        s += 4 if dil <= 0.02 else 2 if dil <= 0.08 else 0
    de = q.get("debt_to_equity")
    if de is not None:
        s += 2 if de <= 0.5 else 1 if de <= 1.5 else 0
    return min(20.0, s)


def _tape_score(state: Optional[str], det: dict) -> float:
    """0-20: momentum state + proximity to highs."""
    s = _MOM_SCORE.get(state or "unknown", 5)
    dd = det.get("dd52w")
    if dd is not None:
        if dd > -0.10:
            s = min(20, s + 2)          # pressing highs
        elif dd < -0.35:
            s = max(0, s - 4)           # deep off highs — not leaders
    return min(20.0, s)


def run() -> dict[str, Any]:
    """Build today's Conviction List + journal + rollups + grading."""
    from app.database import db
    today = date.today()
    pool = _pool(today)
    themes = _theme_map()
    fly = {r["symbol"]: dict(r) for r in db.execute_query(
        "SELECT symbol, eps_growth, rev_growth, rev_accel,"
        " beat_streak, est_revision_pct, fwd_pe, gap_score"
        " FROM symbol_flywheel")}
    mom = {r["symbol"]: (r.get("momentum_state"),
                         r.get("momentum_detail") or {})
           for r in db.execute_query(
               "SELECT symbol, momentum_state, momentum_detail"
               " FROM stocks WHERE momentum_state IS NOT NULL")}
    mcap = {r["symbol"]: r.get("market_cap") for r in db.execute_query(
        "SELECT symbol, market_cap FROM stocks"
        " WHERE market_cap IS NOT NULL")}
    try:
        gq_pct = {r["symbol"]: float(r["percentile"]) for r in
                  db.execute_query(
                      "SELECT DISTINCT ON (symbol) symbol, percentile"
                      " FROM growth_quality_runs WHERE percentile IS NOT NULL"
                      " ORDER BY symbol, as_of DESC, id DESC")}
    except Exception:
        gq_pct = {}

    rows = []
    for sym, p in pool.items():
        f = fly.get(sym) or {}
        q = _quality(sym)
        state, det = mom.get(sym) or (None, {})
        th = themes.get(sym) or {}
        n_src = len(set(p["sources"]))
        parts = {
            "growth": round(_growth_score(f), 1),
            "quality": round(_quality_score(q), 1),
            "tape": round(_tape_score(state, det), 1),
            "consensus": min(15, n_src * 5),
            "theme_money": round((th.get("theme_score") or 50) / 100
                                 * 15, 1),
        }
        # growth-quality composite nudge — percentile vs the tracked
        # universe shifts the composite ±4pts: structural growers earn
        # the benefit of the doubt, cyclical-peak/fcf-negative lose it.
        pctl = gq_pct.get(sym)
        gq_adj = round((pctl - 50) / 50 * 4, 1) if pctl is not None else 0.0
        parts["growth_quality"] = gq_adj
        score = round(sum(parts.values()), 1)

        pe = f.get("fwd_pe")
        valuation = ("extreme" if pe and pe > 60 else
                     "elevated" if pe and pe > 35 else
                     "reasonable" if pe else "unknown")
        broken = state in _BROKEN
        # the lane rule: good+fundamental+value+tape → deploy;
        # good but expensive/unconfirmed → watch. Future-compounders
        # enter watch on THEIR score — thesis+evidence+headroom — not
        # just because the deploy profile failed on valuation.
        fut, fut_themes = _future(sym, f, q, mcap.get(sym))
        if score >= 55 and not broken and valuation in (
                "reasonable", "elevated", "unknown"):
            lane = "deploy"
        elif score >= 50 or fut >= 45:
            lane = "watch"
        else:
            lane = "off"

        rows.append({"symbol": sym, "score": score, "lane": lane,
                     "future_score": fut, "future_themes": fut_themes,
                     "parts": parts, "sources": sorted(set(p["sources"])),
                     "n_sources": n_src, "theme": th.get("theme"),
                     "theme_score": th.get("theme_score"),
                     "fwd_pe": round(pe, 0) if pe else None,
                     "valuation": valuation, "momentum": state,
                     "dd52w": round(det["dd52w"], 3)
                     if det.get("dd52w") is not None else None,
                     "gem_score": p.get("gem_score"),
                     "gap_score": f.get("gap_score")})

    # deploy ranks on the composite; watch ranks on the FUTURE score —
    # thesis exposure + evidence + headroom, not today's tape
    deploy = sorted((r for r in rows if r["lane"] == "deploy"),
                    key=lambda r: -r["score"])
    watch = sorted((r for r in rows if r["lane"] == "watch"),
                   key=lambda r: -r["future_score"])

    # The List = deploy first (current investments), then watch
    # (future shelf). Daily best-2 = top two deploy names.
    the_list = (deploy + watch)[:15]
    picks = [r["symbol"] for r in deploy[:2]]
    for i, r in enumerate(the_list):
        r["rank"] = i + 1
        r["daily_pick"] = r["symbol"] in picks

    _journal(today, the_list)
    graded = _grade()

    weekly = _weekly_rollup() if today.weekday() == 4 else None
    monthly = _monthly_rollup() if _last_biz_day(today) else None

    return {"as_of": str(today), "engine_version": ENGINE_VERSION,
            "pool": len(pool), "the_list": the_list,
            "daily_picks": picks,
            "watch": [{"symbol": r["symbol"],
                       "future_score": r["future_score"],
                       "themes": r["future_themes"]}
                      for r in watch[:10]],
            "weekly_pick": weekly, "monthly_picks": monthly,
            "graded": graded}


def _journal(today: date, rows: list[dict]):
    from app.database import db
    for r in rows:
        db.execute_update(
            "INSERT INTO conviction_snapshots"
            " (snap_date, symbol, rank, score, lane, parts, sources,"
            " n_sources, theme, theme_score, fwd_pe, valuation,"
            " momentum_state, dd52w, daily_pick, engine_version,"
            " future_score)"
            " VALUES (:d,:s,:rk,:sc,:ln,CAST(:pa AS jsonb),"
            " CAST(:so AS jsonb),:ns,:th,:ts,:pe,:va,:mo,:dd,:dp,:v,"
            " :fs)"
            " ON CONFLICT (snap_date, symbol) DO UPDATE SET"
            " rank=EXCLUDED.rank, score=EXCLUDED.score,"
            " lane=EXCLUDED.lane, parts=EXCLUDED.parts,"
            " sources=EXCLUDED.sources, n_sources=EXCLUDED.n_sources,"
            " theme=EXCLUDED.theme, theme_score=EXCLUDED.theme_score,"
            " fwd_pe=EXCLUDED.fwd_pe, valuation=EXCLUDED.valuation,"
            " momentum_state=EXCLUDED.momentum_state,"
            " dd52w=EXCLUDED.dd52w, daily_pick=EXCLUDED.daily_pick,"
            " future_score=EXCLUDED.future_score",
            {"d": today, "s": r["symbol"], "rk": r["rank"],
             "sc": r["score"], "ln": r["lane"],
             "fs": r.get("future_score"),
             "pa": json.dumps(r["parts"]), "so": json.dumps(r["sources"]),
             "ns": r["n_sources"], "th": r.get("theme"),
             "ts": r.get("theme_score"), "pe": r.get("fwd_pe"),
             "va": r.get("valuation"), "mo": r.get("momentum"),
             "dd": r.get("dd52w"), "dp": bool(r.get("daily_pick")),
             "v": ENGINE_VERSION})


def _grade() -> int:
    """Fill ret_5d/20d/60d + vs_spy_20d on matured rows."""
    from app.database import db
    rows = db.execute_query(
        "SELECT id, symbol, snap_date FROM conviction_snapshots"
        " WHERE ret_60d IS NULL AND snap_date <= :c",
        {"c": date.today() - timedelta(days=6)})
    n = 0
    for r in rows:
        fwd = db.execute_query(
            "SELECT close FROM daily_bars WHERE symbol=:s"
            " AND date > :d ORDER BY date LIMIT 60",
            {"s": r["symbol"], "d": r["snap_date"]})
        base = db.execute_query(
            "SELECT close FROM daily_bars WHERE symbol=:s"
            " AND date <= :d ORDER BY date DESC LIMIT 1",
            {"s": r["symbol"], "d": r["snap_date"]})
        spy_f = db.execute_query(
            "SELECT close FROM daily_bars WHERE symbol='SPY'"
            " AND date > :d ORDER BY date LIMIT 22",
            {"d": r["snap_date"]})
        spy_b = db.execute_query(
            "SELECT close FROM daily_bars WHERE symbol='SPY'"
            " AND date <= :d ORDER BY date DESC LIMIT 1",
            {"d": r["snap_date"]})
        if not base or len(fwd) < 5:
            continue
        b = base[0]["close"]
        r5 = fwd[min(4, len(fwd) - 1)]["close"] / b - 1
        r20 = (fwd[min(19, len(fwd) - 1)]["close"] / b - 1
               if len(fwd) >= 19 else None)
        r60 = (fwd[min(59, len(fwd) - 1)]["close"] / b - 1
               if len(fwd) >= 55 else None)
        vs_spy = None
        if r20 is not None and spy_b and len(spy_f) >= 19:
            vs_spy = r20 - (spy_f[19]["close"] / spy_b[0]["close"] - 1)
        db.execute_update(
            "UPDATE conviction_snapshots SET ret_5d=:a, ret_20d=:b,"
            " ret_60d=:c, vs_spy_20d=:v WHERE id=:i",
            {"a": round(r5, 4),
             "b": round(r20, 4) if r20 is not None else None,
             "c": round(r60, 4) if r60 is not None else None,
             "v": round(vs_spy, 4) if vs_spy is not None else None,
             "i": r["id"]})
        n += 1
    return n


def _weekly_rollup() -> Optional[str]:
    """Friday: the week's best — most persistent on The List, highest
    latest score wins ties. Marks weekly_pick on today's row."""
    from app.database import db
    wk = date.today() - timedelta(days=7)
    rows = db.execute_query(
        "SELECT symbol, count(*) days, max(score) mx,"
        " bool_or(lane='deploy') dep FROM conviction_snapshots"
        " WHERE snap_date > :w GROUP BY symbol"
        " ORDER BY dep DESC, days DESC, mx DESC LIMIT 1",
        {"w": wk})
    if not rows:
        return None
    sym = rows[0]["symbol"]
    db.execute_update(
        "UPDATE conviction_snapshots SET weekly_pick=true"
        " WHERE snap_date=:d AND symbol=:s",
        {"d": date.today(), "s": sym})
    return sym


def _monthly_rollup() -> Optional[list[str]]:
    """Last business day: top-2 among this month's weekly picks +
    list persistence — next month's conviction names."""
    from app.database import db
    first = date.today().replace(day=1)
    rows = db.execute_query(
        "SELECT symbol, count(*) days, max(score) mx,"
        " count(*) FILTER (WHERE weekly_pick) wp,"
        " count(*) FILTER (WHERE daily_pick) dp"
        " FROM conviction_snapshots WHERE snap_date >= :f"
        " GROUP BY symbol ORDER BY wp DESC, dp DESC, days DESC,"
        " mx DESC LIMIT 2", {"f": first})
    syms = [r["symbol"] for r in rows]
    for s in syms:
        db.execute_update(
            "UPDATE conviction_snapshots SET monthly_pick=true"
            " WHERE snap_date=:d AND symbol=:s",
            {"d": date.today(), "s": s})
    return syms or None


def _last_biz_day(d: date) -> bool:
    nxt = d
    while True:
        nxt += timedelta(days=1)
        if nxt.weekday() < 5:
            break
    return nxt.month != d.month and d.weekday() < 5
