"""AI capex-cycle engine — detect a pacing slowdown 3-6 months before
reported revenue shows it.

Composite 0-100 (higher = stronger slowdown evidence) across seven
convergent components:

    hyperscaler capex trajectory  20%  reported YoY growth DECELERATION
    AI monetization               18%  revenue growth vs capex growth
    equipment orders proxy        18%  basket revenue-growth decel
    market-implied rotation       14%  new-build vs operator RS, 63d
    data-center construction      10%  manual CBRE input + EQIX/DLR proxy
    semis AI demand               10%  MU/NVDA/AVGO/MRVL decel + RS
    financing / macro             10%  ^TYX level+delta, HYG/LQD stress

Honesty rules:
- every component reports what it measured vs proxied
- regime flags require CONVERGENCE (>=2 components elevated), not the
  composite alone — one signal is noise
- bands: 0-25 expansion · 25-50 normalization · 50-70 slowing ·
  70-85 serious · 85+ contraction
- flags on score level AND 3m/6m deltas — direction beats level

Fundamentals move quarterly: the statement layer is cached ~7d in
engine_weights['capex:fundamentals']; market/financing legs refresh
every momentum pass. Snapshots append to capex_snapshots so the meta
loop can later correlate score with realized basket returns.

read() → latest payload for board/UI. refresh() → the job's call.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

HYPERSCALERS = ["MSFT", "AMZN", "GOOGL", "META", "ORCL"]

# revenue-growth-deceleration proxies for the orders layer
EQUIPMENT = ["VRT", "ETN", "TT", "JCI", "AMAT", "LRCX", "ASML", "KLAC",
             "ONTO", "AVGO", "MRVL", "CRDO", "ALAB"]
SEMIS_AI = ["NVDA", "MU", "AVGO", "MRVL"]

# market-implied layer — whose revenue depends on NEW builds vs the
# installed-base / inference beneficiaries the cycle rotates INTO
NEW_BUILD = ["VRT", "ETN", "CRDO", "ALAB", "ONTO", "NVDA", "AVGO", "MU"]
OPERATORS = ["IREN", "NBIS", "APLD", "CRWV", "EQIX", "MSFT", "AMZN",
             "GOOGL", "ORCL"]

_CONSTRUCTION_PROXY = ["EQIX"]          # DLR absent from daily_bars
_CREDIT = ["HYG", "LQD"]                # high-yield / IG credit ETFs
_RATES = ["^TYX", "^TNX"]

_WEIGHTS = {"capex": 0.20, "monetization": 0.18, "equipment": 0.18,
            "market": 0.14, "construction": 0.10, "semis": 0.10,
            "financing": 0.10}
_FUND_TTL_DAYS = 7                       # statements are quarterly


def _get(k: str) -> dict | None:
    from app.database import db
    rows = db.execute_query(
        "SELECT value FROM engine_weights WHERE key=:k", {"k": k})
    return rows[0]["value"] if rows else None


def _put(k: str, v: Any):
    from app.database import db
    db.execute_query(
        "INSERT INTO engine_weights(key, value, updated_at)"
        " VALUES (:k, CAST(:v AS jsonb), now())"
        " ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value,"
        " updated_at=now()", {"k": k, "v": json.dumps(v)})


# ------------------------------------------------------------------
# fundamentals layer — quarterly statements via FMP (cached weekly)
# ------------------------------------------------------------------

def _q_capex_growth(sym: str) -> tuple[float | None, float | None]:
    """Latest two quarters of capex YoY growth (%), or Nones."""
    try:
        from app.providers.financial_modeling_prep.client import (
            EnhancedFMPClient)
        rows = EnhancedFMPClient.from_settings().get_cash_flow_statement(
            sym, period="quarter") or []
    except Exception:
        return None, None
    by_date = {}
    for r in rows:
        d = str(r.get("date") or "")[:10]
        v = r.get("capitalExpenditure") or r.get("capitalExpenditures")
        if v is not None:
            by_date[d] = abs(float(v))
    if len(by_date) < 5:
        return None, None
    dates = sorted(by_date, reverse=True)
    latest, prior = dates[0], dates[1]
    prev_yr = {d[:4]: d for d in dates}        # first seen = latest per yr
    def _yoy(cur_d):
        yr, rest = cur_d[:4], cur_d[4:]
        base = by_date.get(f"{int(yr) - 1}{rest}")
        if not base:
            return None
        return (by_date[cur_d] / base - 1) * 100
    return _yoy(latest), _yoy(prior)


def _q_rev_growth(sym: str) -> tuple[float | None, float | None]:
    """Latest two quarters of revenue YoY growth (%)."""
    try:
        from app.providers.financial_modeling_prep.client import (
            EnhancedFMPClient)
        rows = EnhancedFMPClient.from_settings().get_income_statement(
            sym, period="quarter") or []
    except Exception:
        return None, None
    by_date = {}
    for r in rows:
        d = str(r.get("date") or "")[:10]
        v = r.get("revenue")
        if v:
            by_date[d] = float(v)
    if len(by_date) < 5:
        return None, None
    dates = sorted(by_date, reverse=True)

    def _yoy(cur_d):
        yr, rest = cur_d[:4], cur_d[4:]
        base = by_date.get(f"{int(yr) - 1}{rest}")
        if not base:
            return None
        return (by_date[cur_d] / base - 1) * 100
    return _yoy(dates[0]), _yoy(dates[1])


def _decel_score(g_now: float | None, g_prior: float | None) -> float:
    """Growth-rate deceleration → 0-100 slowdown score. An absolute
    DECLINE scores worst; negative growth with negative prior = 90."""
    if g_now is None:
        return 30.0                          # unknown → neutral-ish
    if g_now < 0:
        return 90.0                          # spending actually falling
    if g_prior is None:
        return 25.0 if g_now < 30 else 10.0
    decel = g_prior - g_now                  # pts of growth lost QoQ
    if decel <= 0:
        return 8.0                           # accelerating
    if decel < 10:
        return 25.0
    if decel < 20:
        return 50.0
    if decel < 40:
        return 75.0
    return 90.0


def _fundamentals() -> dict[str, Any]:
    """Cached quarterly layer: hyperscaler capex+rev, equipment rev."""
    cached = _get("capex:fundamentals") or {}
    try:
        age = (date.today() - date.fromisoformat(
            str(cached.get("as_of", "2000-01-01"))[:10])).days
        if age < _FUND_TTL_DAYS and cached.get("per_symbol"):
            return cached
    except Exception:
        pass
    per = {}
    for sym in set(HYPERSCALERS + EQUIPMENT + SEMIS_AI +
                   _CONSTRUCTION_PROXY):
        cg_now, cg_prior = _q_capex_growth(sym)
        rg_now, rg_prior = _q_rev_growth(sym)
        per[sym] = {"capex_yoy": _rnd(cg_now), "capex_yoy_prev":
                    _rnd(cg_prior), "rev_yoy": _rnd(rg_now),
                    "rev_yoy_prev": _rnd(rg_prior)}
    out = {"as_of": date.today().isoformat(), "per_symbol": per}
    _put("capex:fundamentals", out)
    try:                                    # transcripts expire with it
        from app.signals import transcript_lang as _tl
        _tl.refresh()
    except Exception as exc:
        logger.debug("transcript language pass: %s", exc)
    return out


def _rnd(v):
    return round(v, 1) if isinstance(v, (int, float)) else None


# ------------------------------------------------------------------
# components — each returns {score, detail, measured|proxy}
# ------------------------------------------------------------------

def _capex_component(per: dict, lang: dict | None = None) -> dict:
    """Hyperscaler capex growth DECELERATION — the user's core insight:
    +100 → +60 → +30 is already a slowdown even as absolute spend grows.
    Management language blends in at 30% when scored (demand tone +
    capex-guidance direction from the transcripts layer)."""
    lang = lang or {}
    scores, rows = [], []
    for sym in HYPERSCALERS:
        p = per.get(sym) or {}
        s = _decel_score(p.get("capex_yoy"), p.get("capex_yoy_prev"))
        lg = (lang.get(sym) or {}).get("slowdown")
        blended = round(0.7 * s + 0.3 * lg, 1) if lg is not None else s
        scores.append(blended)
        rows.append({"sym": sym, "capex_yoy": p.get("capex_yoy"),
                     "prev": p.get("capex_yoy_prev"), "score": round(s),
                     "lang": lg, "blended": round(blended),
                     "lang_note": (lang.get(sym) or {}).get("note")})
    return {"score": round(sum(scores) / len(scores), 1),
            "detail": rows, "kind": "measured + transcript language"}


def _monetization_component(per: dict) -> dict:
    """AI_Monetization ≈ revenue growth minus capex growth per
    hyperscaler — separates 'slowing because ROI improved' from
    'slowing because demand failed'. Segment AI revenue isn't
    separable via FMP → total revenue is the honest proxy."""
    scores, rows = [], []
    for sym in HYPERSCALERS:
        p = per.get(sym) or {}
        rev, cap = p.get("rev_yoy"), p.get("capex_yoy")
        if rev is None or cap is None:
            scores.append(30.0)
            continue
        gap = cap - rev                        # capex outrunning revenue
        s = (8.0 if gap <= -20 else            # rev ≫ capex = healthy
             25.0 if gap <= 10 else
             50.0 if gap <= 20 else
             75.0 if gap <= 40 else 90.0)
        scores.append(s)
        rows.append({"sym": sym, "rev_yoy": rev, "capex_yoy": cap,
                     "gap": round(gap, 1), "score": round(s)})
    return {"score": round(sum(scores) / len(scores), 1),
            "detail": rows, "kind": "proxy:total-rev (AI segment "
            "revenue not separable)"}


def _equipment_component(per: dict, lang: dict | None = None) -> dict:
    """Orders/book-to-bill aren't API-visible → revenue-growth
    deceleration across the equipment basket is the leading proxy,
    blended 30% with transcript order/backlog language when scored —
    the language often turns a quarter before the revenue print."""
    lang = lang or {}
    scores, rows = [], []
    for sym in EQUIPMENT:
        p = per.get(sym) or {}
        s = _decel_score(p.get("rev_yoy"), p.get("rev_yoy_prev"))
        lg = (lang.get(sym) or {}).get("slowdown")
        blended = round(0.7 * s + 0.3 * lg, 1) if lg is not None else s
        scores.append(blended)
        rows.append({"sym": sym, "rev_yoy": p.get("rev_yoy"),
                     "prev": p.get("rev_yoy_prev"), "score": round(s),
                     "lang": lg, "blended": round(blended),
                     "orders_language":
                         (lang.get(sym) or {}).get("orders_language")})
    return {"score": round(sum(scores) / len(scores), 1),
            "detail": rows, "kind": "proxy:rev-decel + order language"}


def _market_component() -> dict:
    """Equities reprice order flow ~1-2 quarters before reported data.
    63d RS of new-build basket vs SPY, and the rotation spread
    (operators minus new-build) — positive spread = smart money
    already rotating out of construction beta."""
    try:
        from app.market_data import bars as bars_mod
        books = bars_mod.load(NEW_BUILD + OPERATORS + ["SPY"], days=90)
    except Exception:
        return {"score": 30.0, "detail": [], "kind": "unavailable"}

    def _rs(b, spy):
        if len(b) < 64 or len(spy) < 64:
            return None
        return (b[-1].close / b[-64].close) - (spy[-1].close /
                                               spy[-64].close)

    spy = books.get("SPY") or []
    nb, ops = [], []
    for sym in NEW_BUILD:
        r = _rs(books.get(sym) or [], spy)
        if r is not None:
            nb.append((sym, r))
    for sym in OPERATORS:
        r = _rs(books.get(sym) or [], spy)
        if r is not None:
            ops.append((sym, r))
    if not nb or not ops:
        return {"score": 30.0, "detail": [], "kind": "unavailable"}
    nb_rs = sum(r for _, r in nb) / len(nb)
    op_rs = sum(r for _, r in ops) / len(ops)
    spread = op_rs - nb_rs                     # + = rotating away
    # score: new-build underperformance + positive rotation spread
    raw = 20.0
    raw += min(40, max(-20, -nb_rs * 300))     # nb_rs -10% → +30
    raw += min(40, max(-15, spread * 250))     # spread +8% → +20
    return {"score": round(max(0, min(100, raw)), 1),
            "detail": {
                "new_build_rs_63d": round(nb_rs * 100, 1),
                "operator_rs_63d": round(op_rs * 100, 1),
                "rotation_spread": round(spread * 100, 1),
                "nb_members": sorted(nb, key=lambda t: t[1])[:3],
                "op_members": sorted(ops, key=lambda t: t[1],
                                     reverse=True)[:3]},
            "kind": "measured"}


def _construction_component(per: dict) -> dict:
    """CBRE MW/preleasing isn't API-able → manual override slot
    (engine_weights['capex:manual']) + EQIX proxy. Never pretends to
    be measured when it isn't."""
    manual = _get("capex:manual") or {}
    if isinstance(manual.get("construction_score"), (int, float)):
        return {"score": float(manual["construction_score"]),
                "detail": {"manual": manual},
                "kind": "manual (CBRE input)"}
    rows = []
    for sym in _CONSTRUCTION_PROXY:
        p = per.get(sym) or {}
        rows.append({"sym": sym, "rev_yoy": p.get("rev_yoy")})
    scores = [_decel_score(p.get("rev_yoy"), p.get("rev_yoy_prev"))
              for sym in _CONSTRUCTION_PROXY
              for p in [per.get(sym) or {}]]
    base = sum(scores) / len(scores) if scores else 30.0
    return {"score": round(base, 1), "detail": rows,
            "kind": "proxy:EQIX (awaiting manual CBRE input)"}


def _semis_component(per: dict) -> dict:
    """HBM/GPU/networking demand — guards against misreading an
    infra-layer rotation as a broad capex contraction."""
    scores, rows = [], []
    for sym in SEMIS_AI:
        p = per.get(sym) or {}
        s = _decel_score(p.get("rev_yoy"), p.get("rev_yoy_prev"))
        scores.append(s)
        rows.append({"sym": sym, "rev_yoy": p.get("rev_yoy"),
                     "prev": p.get("rev_yoy_prev"), "score": round(s)})
    return {"score": round(sum(scores) / len(scores), 1),
            "detail": rows, "kind": "measured"}


def _financing_component() -> dict:
    """^TYX level bands (the user's 30Y framework) + 63d rate drift +
    HYG/LQD credit stress — higher cost of capital kills marginal
    projects first."""
    try:
        from app.market_data import bars as bars_mod
        books = bars_mod.load(_RATES + _CREDIT + ["SPY"], days=90)
    except Exception:
        return {"score": 30.0, "detail": {}, "kind": "unavailable"}
    tyx = books.get("^TYX") or []
    tnx = books.get("^TNX") or []
    lvl = tyx[-1].close if tyx else (tnx[-1].close + 0.5 if tnx else None)
    if lvl is None:
        return {"score": 30.0, "detail": {}, "kind": "unavailable"}
    drift = (tyx[-1].close - tyx[-64].close) if len(tyx) > 64 else 0.0
    # credit stress: HYG underperforming SPY over 63d
    hyg, spy = books.get("HYG") or [], books.get("SPY") or []
    hyg_rs = ((hyg[-1].close / hyg[-64].close) -
              (spy[-1].close / spy[-64].close)) if len(hyg) > 64 and \
        len(spy) > 64 else 0.0
    credit_stress = hyg_rs < -0.03
    s = (5.0 if lvl < 5.2 else 25.0 if lvl < 5.4 else
         50.0 if lvl < 5.6 else 75.0)
    if drift > 0.30:
        s += 10.0                              # rates rising fast
    if credit_stress:
        s += 15.0
    return {"score": round(min(100, s), 1),
            "detail": {"tyx": round(lvl, 2),
                       "tyx_drift_63d_bp": round(drift * 100),
                       "hyg_rs_63d": round(hyg_rs * 100, 1),
                       "credit_stress": bool(credit_stress)},
            "kind": "measured"}


# ------------------------------------------------------------------
# composite + flags
# ------------------------------------------------------------------

def _band(score: float) -> str:
    return ("expansion" if score < 25 else "normalization"
            if score < 50 else "slowing" if score < 70 else
            "serious_slowdown" if score < 85 else "contraction")


def _guidance(score: float, band: str, flags: list[str],
              n_elevated: int, comps: dict, d3m, d6m) -> dict:
    """Plain-English meaning + actions — deterministic, driven by band +
    which legs are elevated. This is a capital-allocation dial, never
    a sell signal; the text keeps that framing explicit."""
    legs = {k: (v or {}).get("score") for k, v in comps.items()}
    rot = (comps.get("market") or {}).get("detail") or {}
    meaning = {
        "expansion": ("Buildout accelerating — capex growth rising, "
                      "orders and language strong. Capex-beta names "
                      "carry full weight; confirmed setups on "
                      "new-build names get no discount."),
        "normalization": ("Still building — the spend itself hasn't "
                          "slowed, but growth is decelerating or "
                          "monetization hasn't caught up. Nothing to "
                          "sell; this is the watch zone."),
        "slowing": ("Capex pacing is rolling — orders flattening, "
                    "language softening, financing tightening. Tilt "
                    "NEW money toward lifecycle/inference names; no "
                    "forced exits on existing positions."),
        "serious_slowdown": ("Broad slowdown — multiple legs elevated "
                             "with convergence. Reduce new-build "
                             "equipment beta; operators and "
                             "recurring-revenue names take priority."),
        "contraction": ("Capex contraction — spending itself is being "
                        "cut. Avoid capex-beta entirely; "
                        "cash-generative businesses only."),
    }[band]
    actions = []
    if band in ("expansion", "normalization"):
        actions.append("no position changes — confirmed setups on "
                       "capex names remain valid")
    if band == "normalization":
        actions.append("watch Δ3m: a +10-15pt climb in 3 months is the "
                       "early warning, the level itself is not")
    if band in ("slowing", "serious_slowdown"):
        actions.append("new capital → operators/lifecycle "
                       "(IREN/NBIS/APLD/CRWV-style) over new-build "
                       "(VRT/CRDO/ALAB-style)")
        actions.append("halve new entries on capex-beta names; tighten "
                       "stops on existing ones")
    if band == "serious_slowdown":
        actions.append("options: prefer PUT spreads or shorter-dated "
                       "structures on new-build names")
    if band == "contraction":
        actions.append("no new capex-beta entries; raise cash / "
                       "defensive sleeve")
    if (flags or []) and "CAPEX_EARLY_WARNING" in flags:
        actions.append("EARLY_WARNING: score under 50 but rising fast —"
                       " pre-position the rotation list, don't act yet")
    if "CAPEX_SLOWDOWN_ACTIVE" in (flags or []):
        actions.append("ACTIVE: board/GARP rows already discount "
                       "capex-beta; LEAPS warns on new-build contracts")
    if "CAPEX_CONTRACTION" in (flags or []):
        actions.append("CONTRACTION: capex-beta is a structural "
                       "headwind — positions need their own thesis")
    watch = []
    if legs.get("monetization", 0) >= 50:
        watch.append("monetization gap is the bear case — watch "
                     "hyperscaler prints for rev growth catching capex")
    if legs.get("financing", 0) >= 50:
        watch.append("financing leg elevated — watch ^TYX; marginal "
                     "projects die at expensive capital first")
    if legs.get("market", 0) >= 40 and (rot.get("rotation_spread")
                                      or 0) > 0:
        watch.append("tape is rotating out of new-build before "
                     "reported data — the earliest tell, watch it widen")
    if legs.get("equipment", 0) >= 50:
        watch.append("equipment orders proxy decelerating — next VRT/"
                     "ETN/CRDO backlog language is the confirmation")
    if not watch:
        watch.append("next hyperscaler prints — capex growth-rate "
                     "DECELERATION (+80→+60→+30) is the trigger, not "
                     "absolute declines")
    return {"meaning": meaning, "actions": actions, "watch": watch}


def _flags(score: float, d3m: float | None, d6m: float | None,
           n_elevated: int) -> list[str]:
    """Convergence required: level flags demand >=2 elevated components;
    pure-delta early warning is the exception (it exists to be early)."""
    out = []
    if score >= 80 and n_elevated >= 3:
        out.append("CAPEX_CONTRACTION")
    elif score >= 65 and (d3m or 0) >= 10 and n_elevated >= 2:
        out.append("CAPEX_SLOWDOWN_ACTIVE")
    elif score >= 50 and (d3m or 0) >= 10 and n_elevated >= 2:
        out.append("CAPEX_SLOWDOWN_WARNING")
    elif score < 50 and (d3m or 0) >= 15:
        out.append("CAPEX_EARLY_WARNING")
    return out


def _history() -> list[dict]:
    rows = _get("capex:history") or []
    return rows if isinstance(rows, list) else []


def _delta(hist: list[dict], days: int) -> float | None:
    """Score delta vs the snapshot nearest `days` ago."""
    target = date.today().toordinal() - days
    best = None
    for h in hist:
        try:
            dd = date.fromisoformat(str(h["as_of"])[:10]).toordinal()
        except Exception:
            continue
        if best is None or abs(dd - target) < abs(best[0] - target):
            best = (dd, h.get("score"))
    if best and best[1] is not None and abs(best[0] - target) <= 45:
        return round(best[1], 1)
    return None


# ------------------------------------------------------------------
# public API
# ------------------------------------------------------------------

def refresh() -> dict[str, Any]:
    """Momentum-job call. Fundamentals cached weekly; market+financing
    legs live; composite + momentum + flags persisted + snapshotted."""
    try:                                    # rates + credit top-up
        from app.market_data import bars as bars_mod
        bars_mod.refresh(_RATES + _CREDIT, period="1y")
    except Exception as exc:
        logger.debug("rates/credit bar refresh: %s", exc)
    per = (_fundamentals() or {}).get("per_symbol") or {}
    try:                                    # transcript language layer
        from app.signals import transcript_lang as _tl
        lang = _tl.language_map()
    except Exception:
        lang = {}
    comps = {"capex": _capex_component(per, lang),
             "monetization": _monetization_component(per),
             "equipment": _equipment_component(per, lang),
             "market": _market_component(),
             "construction": _construction_component(per),
             "semis": _semis_component(per),
             "financing": _financing_component()}
    score = sum(comps[k]["score"] * w for k, w in _WEIGHTS.items())
    n_elevated = sum(1 for c in comps.values() if c["score"] >= 50)
    hist = _history()
    d3 = _delta(hist, 91)
    d6 = _delta(hist, 182)
    cur = round(score, 1)
    flags = _flags(cur, None if d3 is None else cur - d3,
                   None if d6 is None else cur - d6, n_elevated)
    out = {"score": cur, "band": _band(cur), "flags": flags,
           "guidance": _guidance(cur, _band(cur), flags, n_elevated,
                                 comps,
                                 None if d3 is None else cur - d3,
                                 None if d6 is None else cur - d6),
           "score_3m_ago": d3, "score_6m_ago": d6,
           "d3m": round(cur - d3, 1) if d3 is not None else None,
           "d6m": round(cur - d6, 1) if d6 is not None else None,
           "n_elevated": n_elevated,
           "components": {k: v for k, v in comps.items()},
           "rotation": (comps["market"].get("detail") or {}),
           "as_of": datetime.now(timezone.utc).isoformat(
               timespec="seconds"),
           "note": ("convergence gauge, not prophecy — flags need "
                    ">=2 components elevated; construction leg is "
                    "manual until CBRE input lands")}
    _put("capex:cycle", out)
    # history: one snapshot per calendar day
    hist = [h for h in hist
            if str(h.get("as_of"))[:10] != date.today().isoformat()]
    hist.append({"as_of": date.today().isoformat(), "score": cur,
                 "components": {k: v["score"] for k, v in
                                comps.items()}})
    _put("capex:history", hist[-400:])
    try:
        from app.database import db
        db.execute_query(
            "INSERT INTO capex_snapshots(as_of, score, components)"
            " VALUES (:d, :s, CAST(:c AS jsonb))"
            " ON CONFLICT (as_of) DO UPDATE SET score=EXCLUDED.score,"
            " components=EXCLUDED.components",
            {"d": date.today().isoformat(), "s": cur,
             "c": json.dumps({k: v["score"] for k, v in
                              comps.items()})})
    except Exception as exc:
        logger.debug("capex snapshot persist: %s", exc)
    return out


def read() -> dict[str, Any]:
    return _get("capex:cycle") or {}


def symbol_flag(sym: str, payload: dict | None = None) -> str | None:
    """Selection-layer hook: which basket does this symbol belong to,
    and does the current regime flag it? Returns a short tag or None."""
    p = payload if payload is not None else read()
    flags = set(p.get("flags") or [])
    slowing = bool(flags & {"CAPEX_SLOWDOWN_WARNING",
                            "CAPEX_SLOWDOWN_ACTIVE",
                            "CAPEX_CONTRACTION",
                            "CAPEX_EARLY_WARNING"})
    if sym in NEW_BUILD and slowing:
        return "capex-beta"                  # new-build exposure, slow
    if sym in OPERATORS and "CAPEX_SLOWDOWN_ACTIVE" in flags:
        return "rotation-candidate"          # lifecycle beneficiary
    return None
