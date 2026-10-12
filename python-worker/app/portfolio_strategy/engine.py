"""Portfolio strategy engine — regime → rotation → events → earnings
→ theme scores → target weights.

Eight layers, all deterministic and journaled:

  1. market_regime      latest morning snapshot (score, rules, events)
  2. money_rotation     per-ETF rotation score (30% rel-perf / 25% flow /
                        20% breadth / 15% volume / 10% acceleration)
  3. event_risk         macro calendar + election transmission channels
  4. earnings           weekly concentration — % of book reporting
  5. theme_scores       tailwind+fundamentals+momentum+money+valuation
  6. risk_adjustment    earnings/event haircut applied to raw score
  7. target_weights     scores → weights, regime-gated
  8. confirmation       rotation signals need ≥2 independent witnesses

Weights are starting parameters — the journal accrues so they can be
backtested rather than defended by intuition.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

ENGINE_VERSION = "strategy_v1"

# ---- themes: the book's actual bets, expressed as ETF + member basket ----
THEMES = {
    "ai_infra": {
        "name": "AI Infrastructure", "etf": "SMH",
        "members": ["NVDA", "AVGO", "MRVL", "MU", "CRDO", "ALAB",
                    "ONTO", "COHR", "LITE", "GLW", "TSM"],
        "tailwind_src": "capex",
    },
    "ai_ops": {
        "name": "AI Software / Operators", "etf": "IGV",
        "members": ["MSFT", "GOOGL", "AMZN", "ORCL", "CRM", "NOW",
                    "WDAY", "PLTR", "META", "RBRK"],
        "tailwind_src": "ai_regime",
    },
    "dc_power": {
        "name": "Data Center & Power", "etf": "XLU",
        "members": ["IREN", "NBIS", "APLD", "CRWV", "EQIX", "MOD",
                    "POWL", "VRT", "ETN", "STRL"],
        "tailwind_src": "capex",
    },
    "fintech": {
        "name": "Fintech & Crypto", "etf": "XLF",
        "members": ["HOOD", "COIN"],
        "tailwind_src": "market",
    },
    "biotech": {
        "name": "Biotech", "etf": "XBI",
        "members": [],
        "tailwind_src": "market",
    },
    "energy": {
        "name": "Energy & Commodities", "etf": "XLE",
        "members": ["XOM", "CVX", "FCX"],
        "tailwind_src": "inflation",
    },
    "industrials": {
        "name": "Industrials & Reshoring", "etf": "XLI",
        "members": ["CAT", "GEV", "PWR"],
        "tailwind_src": "growth",
    },
    "broad": {
        "name": "Broad Market", "etf": "QQQ",
        "members": [],
        "tailwind_src": "market",
    },
}

# rotation score weights — user's spec, journaled for later refit
ROT_W = {"rel_perf": .30, "flow": .25, "breadth": .20,
         "volume": .15, "accel": .10}
# theme score weights
THEME_W = {"tailwind": .25, "fundamentals": .25, "momentum": .20,
           "money_flow": .20, "valuation": .10}

# election transmission — channels, not predictions (user's spec §6)
_ELECTION_CHANNELS = {
    "trade policy": ["ai_infra", "industrials"],
    "tax policy": ["ai_ops", "fintech", "broad"],
    "energy policy": ["energy", "dc_power"],
    "healthcare policy": ["biotech"],
    "fiscal/deficits": ["broad", "fintech", "industrials"],
    "semiconductor policy": ["ai_infra"],
    "reshoring/tariffs": ["industrials", "energy"],
}

_MOM_SCORE = {"breakout": 90, "uptrend": 75, "pullback": 62,
              "basing": 55, "recovery": 48, "capitulation": 35,
              "rolling_over": 28, "downtrend": 15, "knife": 5,
              "breakdown": 5, "climax": 80}
_FUND_SCORE = {"accelerating": 85, "growing": 68, "watch": 52,
               "cyclical": 50, "slowing": 38, "declining": 20}


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def _books(syms: list[str], days: int = 260):
    from app.market_data import bars as bars_mod
    return bars_mod.load(syms, days=days)


def _closes(books, sym) -> list[float]:
    return [b.close for b in (books.get(sym) or [])]


def _vols(books, sym) -> list[float]:
    return [b.volume or 0 for b in (books.get(sym) or [])]


def _ret(c: list[float], n: int) -> Optional[float]:
    if len(c) < n + 1:
        return None
    a, b = c[-n - 1], c[-1]
    return b / a - 1 if a else None


# ---------------------------------------------------------------- rotation
def money_rotation() -> dict[str, Any]:
    """Money Rotation Score per theme/sector ETF — where capital is
    actually moving, in the spec's weights."""
    from app.market_regime.rotation import SECTOR_NAMES, THEME_ETFS
    etfs = list(dict.fromkeys(
        list(THEME_ETFS) + list(SECTOR_NAMES) + ["SPY", "QQQ"]))
    books = _books(etfs, days=260)
    spy = _closes(books, "SPY")
    if len(spy) < 25:
        return {}
    spy20 = _ret(spy, 20) or 0.0

    # real fund flows when AUM history has accrued — else the
    # price×volume proxy stays, flagged per-row
    try:
        from app.portfolio_strategy import flows as _fl
        real_flows = _fl.fund_flows(etfs)
    except Exception:
        real_flows = {}

    rows = []
    for sym in etfs:
        if sym == "SPY":
            continue
        c = _closes(books, sym)
        if len(c) < 60:
            continue
        v = _vols(books, sym)
        r1, r5, r20 = _ret(c, 1), _ret(c, 5), _ret(c, 20)
        if r5 is None or r20 is None:
            continue
        s50 = sum(c[-50:]) / 50
        s200 = sum(c[-200:]) / min(200, len(c))
        above50, above200 = c[-1] > s50, c[-1] > s200
        vs_spy = r20 - spy20

        # flow proxy — signed money over 5d (same read as allocation.py)
        money5, vol_ratio = None, None
        if len(v) >= 26 and sum(v[-6:-1]) > 0:
            signed = sum((1 if c[-i] >= c[-i - 1] else -1)
                         * v[-i] for i in range(1, 6))
            money5 = signed / sum(v[-6:-1])
            avg20 = sum(v[-26:-6]) / 20
            vol_ratio = (sum(v[-6:-1]) / 5) / avg20 if avg20 else None

        # real AUM-derived flow when available: ±2% of AUM over 20d
        # is a meaningful creation/redemption cycle for a sector ETF
        rf = real_flows.get(sym) or {}
        flow_src = rf.get("source")
        if flow_src == "aum" and rf.get("flow_pct") is not None:
            flow_score = _clamp(50 + rf["flow_pct"] * 25, 0, 100)
        else:
            flow_score = _clamp(50 + (money5 or 0) * 150, 0, 100)

        parts = {
            "rel_perf": _clamp(50 + vs_spy * 800, 0, 100),
            "flow": flow_score,
            "breadth": 50 + (25 if above50 else -25)
                       + (25 if above200 else -25),
            "volume": _clamp(50 + ((vol_ratio or 1) - 1) * 120
                             * (1 if (r1 or 0) > 0 else -1), 0, 100),
            "accel": _clamp(50 + ((r5 or 0) - (r20 or 0) / 4) * 900,
                            0, 100),
        }
        score = sum(parts[k] * ROT_W[k] for k in ROT_W)
        rows.append({
            "etf": sym,
            "name": THEME_ETFS.get(sym) or SECTOR_NAMES.get(sym) or sym,
            "score": round(score, 1),
            "parts": {k: round(x, 1) for k, x in parts.items()},
            "ret5": round(r5, 4), "ret20": round(r20, 4),
            "vs_spy20": round(vs_spy, 4),
            "above50": above50, "above200": above200,
            "money5": round(money5, 2) if money5 is not None else None,
            "vol_ratio": round(vol_ratio, 2) if vol_ratio else None,
            "flow_source": flow_src,
            "flow_5d_usd": rf.get("flow_5d"),
            "flow_20d_usd": rf.get("flow_20d"),
            "flow_pct_aum": rf.get("flow_pct"),
        })
    rows.sort(key=lambda r: -r["score"])
    return {"rows": rows,
            "inflow": [r["etf"] for r in rows if r["score"] >= 65],
            "outflow": [r["etf"] for r in rows if r["score"] <= 35],
            "weights": ROT_W,
            "spy_ret20": round(spy20, 4)}


# ---------------------------------------------------------------- events
def event_layer(now: Optional[datetime] = None) -> dict[str, Any]:
    """Macro calendar + election transmission channels + heatmap."""
    from app.market_events.calendar import upcoming_macro_events
    evts = upcoming_macro_events(days=90, now=now)
    today = (now or datetime.now(timezone.utc)).date()
    elections = [e for e in evts if e.get("kind") == "election"]

    election = None
    if elections:
        e = elections[0]
        days = e.get("days_away")
        sensitivity = ("EXTREME" if days is not None and days <= 14
                       else "HIGH" if days is not None and days <= 32
                       else "MEDIUM" if days is not None and days <= 60
                       else "LOW")
        election = {"name": e["name"], "date": str(e["date"]),
                    "days_away": days, "sensitivity": sensitivity,
                    "channels": _ELECTION_CHANNELS,
                    "note": "transmission map — modifies risk, never "
                            "picks stocks"}

    # month heatmap — the event-density read
    heat = []
    for e in evts[:30]:
        sev = e.get("severity") or "low"
        heat.append({"date": str(e["date"]), "name": e["name"],
                     "kind": e.get("kind"), "severity": sev})
    high_next10 = sum(1 for e in evts
                      if (e.get("days_away") or 99) <= 10
                      and e.get("severity") in ("high", "extreme"))
    density = ("clustered" if high_next10 >= 2 else
               "elevated" if high_next10 == 1 else "normal")
    return {"events": evts, "election": election, "heatmap": heat,
            "density": density, "high_next10": high_next10}


# ---------------------------------------------------------------- earnings
def earnings_layer(book_syms: list[str]) -> dict[str, Any]:
    """Weekly earnings concentration — % of book reporting each week."""
    from app.database import db
    rows = db.execute_query(
        "SELECT symbol, next_earnings_date FROM stocks "
        "WHERE next_earnings_date IS NOT NULL")
    edates = {r["symbol"]: r["next_earnings_date"] for r in rows}

    today = date.today()
    weeks = []          # next 4 calendar weeks
    for w in range(4):
        start = today + timedelta(days=w * 7)
        end = start + timedelta(days=7)
        reporting = [s for s in book_syms
                     if (d := edates.get(s)) and start <= d < end]
        pct = (len(reporting) / len(book_syms) * 100) if book_syms else 0
        risk = ("HIGH" if pct >= 30 or len(reporting) >= 4 else
                "MEDIUM" if pct >= 15 or len(reporting) >= 2 else
                "LOW")
        weeks.append({"week": str(start), "n": len(reporting),
                      "pct_of_book": round(pct, 1), "risk": risk,
                      "symbols": sorted(reporting),
                      "dates": {s: str(edates[s]) for s in reporting}})

    peak = max((w["pct_of_book"] for w in weeks), default=0)
    return {"weeks": weeks,
            "peak_exposure_pct": round(peak, 1),
            "summary": ("HIGH" if peak >= 30 else
                        "MEDIUM" if peak >= 15 else "LOW"),
            "preview": _cluster_preview(book_syms)}


def _cluster_preview(book_syms: list[str]) -> list[dict]:
    """Expectation board for the next ~60d of prints — revision
    direction + beat streak tells you who walks in hot (asymmetric
    downside on a miss) vs. with a lowered bar. This is the setup,
    not the prediction."""
    from app.database import db
    horizon = date.today() + timedelta(days=60)
    fly = {r["symbol"]: r for r in db.execute_query(
        "SELECT symbol, est_revision_pct, beat_streak, "
        "avg_surprise_pct, eps_growth, num_analysts "
        "FROM symbol_flywheel")}
    # whole flywheel universe reports matter — hyperscaler prints move
    # the book even when the book doesn't hold them
    rows = db.execute_query(
        "SELECT stock_symbol, min(earnings_date) d FROM "
        "earnings_data WHERE earnings_date >= CURRENT_DATE "
        "AND earnings_date <= :h AND stock_symbol = ANY(:s) "
        "GROUP BY stock_symbol",
        {"h": horizon, "s": list(fly)})
    out = []
    for r in rows:
        sym, f = r["stock_symbol"], fly.get(r["stock_symbol"]) or {}
        rev = f.get("est_revision_pct")
        streak = f.get("beat_streak") or 0
        thin = (f.get("num_analysts") or 99) < 5
        # setup classification — the asymmetric-risk read; thin
        # coverage makes revision signals unreliable noise
        if thin:
            setup = "➖ thin coverage — signals unreliable"
        elif rev is not None and rev > 0.15 and streak >= 3:
            setup = "🔥 hot — high bar, miss hurts"
        elif rev is not None and rev < -0.10:
            setup = "🧊 fading — bar lowering"
        elif streak >= 4:
            setup = "💪 reliable — streak intact"
        else:
            setup = "➖ neutral"
        out.append({"symbol": sym, "date": str(r["d"]),
                    "rev_pct": round(rev * 100, 1) if rev is not None
                    else None, "streak": streak,
                    "eps_growth": round(f["eps_growth"] * 100)
                    if f.get("eps_growth") is not None else None,
                    "analysts": f.get("num_analysts"),
                    "setup": setup,
                    "held": sym in book_syms})
    out.sort(key=lambda x: x["date"])
    return out


# ---------------------------------------------------------------- themes
def macro_transmission(morning: Optional[dict]) -> dict[str, dict]:
    """Macro buckets → theme tilts. The morning engine already reads
    yields/dollar/inflation/growth; this maps those to WHERE money
    moves — transmission channels, not predictions:
      hot inflation    → energy/commodities up, long-duration down
      strong dollar    → multinational revenue drag, commodities drag
      rising yields    → growth-duration haircut, banks benefit
      growth improving → industrials/capex cyclicals up
      yields + stress  → utilities/defensives up
    """
    b = (morning or {}).get("buckets") or {}
    if isinstance(b, str):
        b = json.loads(b)

    def _s(name: str) -> float:
        try:
            return float((b.get(name) or {}).get("score", 50))
        except Exception:
            return 50.0

    infl, dxy = _s("inflation"), _s("dollar")
    liq, grw = _s("liquidity"), _s("growth")

    # bucket scores are equity-health oriented: high liquidity score
    # = benign rates. A LOW liquidity score = yields rising = long
    # duration haircuts. Same inversion for dollar (low = strong USD).
    adj: dict[str, dict] = {k: {"delta": 0.0, "why": []}
                            for k in THEMES}

    if infl >= 60:                     # breakevens cooling
        adj["energy"]["delta"] += 4
        adj["energy"]["why"].append(
            f"inflation bucket {infl:.0f} — cooling hurts the "
            "commodity trade" if infl >= 75 else
            "inflation cooling — energy demand intact, real-asset "
            "bid softens")
    elif infl <= 40:                   # hot prints — stagflation tape
        adj["energy"]["delta"] += 8
        adj["energy"]["why"].append(
            f"inflation bucket {infl:.0f} — hot prints favor "
            "real assets")
        for k in ("ai_infra", "ai_ops", "dc_power"):
            adj[k]["delta"] -= 5
            adj[k]["why"].append(
                "hot inflation → long-duration valuation haircut")

    if dxy <= 40:                      # strong dollar (low score =
        adj["ai_ops"]["delta"] -= 4    #  DXY rising in this scheme)
        adj["ai_ops"]["why"].append(
            f"dollar bucket {dxy:.0f} — strong USD drags "
            "multinational revenue")
        adj["energy"]["delta"] -= 3
        adj["energy"]["why"].append(
            "strong USD → dollar-priced commodities drag")
    elif dxy >= 65:                    # weak dollar
        adj["ai_ops"]["delta"] += 3
        adj["energy"]["delta"] += 4
        adj["energy"]["why"].append(
            "weak USD → commodity tailwind")

    if liq <= 40:                      # yields rising / curve stress
        for k in ("ai_infra", "ai_ops", "dc_power", "biotech"):
            adj[k]["delta"] -= 4
        adj["ai_ops"]["why"].append(
            f"liquidity bucket {liq:.0f} — rising yields haircut "
            "long-duration")
        adj["energy"]["delta"] += 3
        adj["fintech"]["delta"] += 2
        adj["fintech"]["why"].append(
            "higher-for-longer rates → NII tailwind for brokers")

    if grw >= 60:                      # growth improving — cyclicals
        adj["industrials"]["delta"] += 6
        adj["dc_power"]["delta"] += 3
        adj["industrials"]["why"].append(
            f"growth bucket {grw:.0f} — capex-cycle cyclicals lead")
    elif grw <= 35:                    # growth rolling over
        adj["industrials"]["delta"] -= 5
        adj["broad"]["delta"] -= 3

    return {k: v for k, v in adj.items() if v["delta"] != 0}


# ---------------------------------------------------------------- agentic AI
# The structural split the BofA call makes concrete: agents consume
# more compute/observability/infrastructure but fewer software seats.
# Layers score on the same engines — momentum_state + flywheel — so
# "who owns what agents can't bypass" is a graded number, not a story.
_AGENTIC_LAYERS = {
    "compute": {
        "name": "Compute & silicon",
        "syms": ["NVDA", "AVGO", "MRVL", "TSM", "ARM", "DELL", "SMCI"],
    },
    "memory": {
        "name": "Memory / HBM bottleneck",
        "syms": ["MU", "ONTO"],
        "note": "Micron: supply tight into 2028 — HBM absorbs supply; "
                "the chain (packaging → inspection → networking) is "
                "where the constraint compounds",
    },
    "network": {
        "name": "Networking & optics",
        "syms": ["CRDO", "ALAB", "ANET", "COHR", "LITE", "GLW"],
    },
    "neocloud": {
        "name": "Neo-cloud & DC expansion",
        "syms": ["NBIS", "CRWV", "IREN", "APLD", "EQIX"],
    },
    "power": {
        "name": "Power, cooling & build",
        "syms": ["VRT", "ETN", "POWL", "MOD"],
    },
    "observability": {
        "name": "Observability & ops",
        "syms": ["DDOG", "DT"],
        "note": "agents generate MORE telemetry than humans — the "
                "layer they can't bypass",
    },
    "platform": {
        "name": "Cloud, data & workflow",
        "syms": ["ORCL", "MSFT", "GOOGL", "AMZN", "PLTR", "NOW",
                 "SHOP"],
    },
}
# BofA seat-model exposure list — agents may consume FEWER seats;
# these are the names whose pricing model is per-human
_AGENTIC_EXPOSED = {
    "ASAN": "Asana", "BL": "BlackLine", "DBX": "Dropbox",
    "HNGE": "Hinge Health", "HUBS": "HubSpot", "INTU": "Intuit",
    "MNDY": "Monday.com", "PAYC": "Paycom", "PCTY": "Paylocity",
    "ZM": "Zoom",
}


def agentic_layer(book_syms: list[str]) -> dict[str, Any]:
    """Agentic-AI thematic engine — infra/ops/bypass layers vs the
    seat-model exposure list, both scored on stored momentum +
    fundamentals. DRY: no new data fetches."""
    from app.database import db
    all_syms = sorted({s for l in _AGENTIC_LAYERS.values()
                       for s in l["syms"]} | set(_AGENTIC_EXPOSED))
    ph = ",".join(f"'{s}'" for s in all_syms)
    mom = {r["symbol"]: (r.get("momentum_state") or "")
           for r in db.execute_query(
               f"SELECT symbol, momentum_state FROM stocks "
               f"WHERE symbol IN ({ph})")}
    fst = {r["symbol"]: (r.get("fundamental_state") or "")
           for r in db.execute_query(
               f"SELECT symbol, fundamental_state FROM stocks "
               f"WHERE symbol IN ({ph})")}
    fly = {r["symbol"]: r for r in db.execute_query(
        f"SELECT symbol, rev_growth, rev_accel, est_revision_pct, "
        f"beat_streak, gap_score, fwd_pe FROM symbol_flywheel "
        f"WHERE symbol IN ({ph})")}

    def _name_score(s: str) -> dict:
        m = _MOM_SCORE.get(mom.get(s), 45)
        f = _FUND_SCORE.get(fst.get(s), 50)
        fl = fly.get(s) or {}
        rg = fl.get("rev_growth")
        if rg is not None:
            f = _clamp(f + _clamp(rg * 0.5, -10, 15))
        return {"symbol": s,
                "score": round(m * 0.55 + f * 0.45, 1),
                "momentum": mom.get(s) or "—",
                "fundamental": fst.get(s) or "—",
                "rev_growth": rg,
                "est_rev": fl.get("est_revision_pct"),
                "in_book": s in book_syms}

    layers = []
    for key, l in _AGENTIC_LAYERS.items():
        names = [_name_score(s) for s in l["syms"]]
        score = (sum(n["score"] for n in names) / len(names)
                 if names else 50.0)
        layers.append({"key": key, "name": l["name"],
                       "score": round(score, 1),
                       "note": l.get("note"),
                       "names": sorted(names, key=lambda n: -n["score"]),
                       "in_book": [s for s in l["syms"]
                                   if s in book_syms]})
    layers.sort(key=lambda l: -l["score"])

    exposed = []
    for s, nm in _AGENTIC_EXPOSED.items():
        n = _name_score(s)
        n["name"] = nm
        # seat-risk names the book holds = the names to underwrite now
        n["flag"] = ("⚠️ held" if s in book_syms else
                     "watch" if n["score"] >= 60 else "avoid")
        exposed.append(n)
    exposed.sort(key=lambda n: -n["score"])

    benef_mean = (sum(l["score"] for l in layers) / len(layers)
                  if layers else 50)
    ex_mean = (sum(n["score"] for n in exposed) / len(exposed)
               if exposed else 50)
    return {
        "layers": layers, "exposed": exposed,
        "bifurcation": round(benef_mean - ex_mean, 1),
        "read": ("agents consume more compute/obs/infra, fewer seats — "
                 "the spread between the bypass-layer mean and the "
                 "seat-model mean is the thesis's real-time grade"),
        "beneficiary_mean": round(benef_mean, 1),
        "exposed_mean": round(ex_mean, 1),
        "held_bypass": sorted({s for l in layers for s in l["in_book"]}),
        "held_exposed": [n["symbol"] for n in exposed
                         if n["in_book"]]}


def rotation_direction(themes: list[dict],
                       rotation: dict,
                       macro_adj: dict,
                       book_syms: list[str]) -> list[dict]:
    """The directional call — where money is going NEXT.

    Combines four independent witnesses per theme:
      flow    — money_rotation score + signed money5 (price×volume)
      macro   — bucket-driven transmission tilt (yields/dollar/etc.)
      breadth — % of theme members in positive momentum states
      news    — fresh focus-intel events + alerts on members

    Verdicts: accelerating_in / rotating_in / stable / rotating_out /
    avoid. Two+ aligned witnesses = confirmed; one = watch only —
    same discipline as the rotation-confirmation table.
    """
    from app.database import db
    try:
        fb = {}
        from app.signals.focus_intel import fresh_boosts
        fb = fresh_boosts() or {}
    except Exception:
        fb = {}
    try:
        alerts = {r["symbol"]: r for r in db.execute_query(
            "SELECT DISTINCT ON (symbol) symbol, direction, materiality "
            "FROM alert_items "
            "WHERE created_at > now() - interval '72 hours' "
            "ORDER BY symbol, created_at DESC")}
    except Exception:
        alerts = {}
    mom = {r["symbol"]: (r.get("momentum_state") or "")
           for r in db.execute_query(
               "SELECT symbol, momentum_state FROM stocks "
               "WHERE momentum_state IS NOT NULL")}

    _POS_MOM = {"uptrend", "breakout", "pullback", "basing", "recovery"}
    member_of = {s: k for k, t in THEMES.items() for s in t["members"]}

    out = []
    for t in themes:
        k = t["key"]
        rot = t.get("rotation_row") or {}
        ma = macro_adj.get(k) or {}

        # witness 1 — flow
        flow_pts = 0
        if (rot.get("score") or 50) >= 65:
            flow_pts += 1
        if (rot.get("money5") or 0) > 0.1:
            flow_pts += 1
        if (rot.get("vs_spy20") or 0) < -0.02:
            flow_pts -= 1

        # witness 2 — macro tilt
        macro_pts = 0
        if ma.get("delta", 0) > 0:
            macro_pts += 1
        elif ma.get("delta", 0) < 0:
            macro_pts -= 1

        # witness 3 — member breadth (how many names inside confirm)
        pos = sum(1 for s in t["members"] if mom.get(s) in _POS_MOM)
        breadth = pos / len(t["members"]) if t["members"] else 0.5
        breadth_pts = 1 if breadth >= 0.55 else (-1 if breadth <= 0.3
                                                 else 0)

        # witness 4 — fresh catalysts on members
        pos_news = sum(1 for s in t["members"]
                       if s in fb
                       and fb[s].get("materiality", 0) >= 3)
        neg_news = sum(1 for s in t["members"]
                       if (a := alerts.get(s))
                       and a.get("direction") == "NEGATIVE"
                       and a.get("materiality") == "HIGH")
        news_pts = 1 if pos_news > neg_news else (
            -1 if neg_news > pos_news else 0)

        total = flow_pts + macro_pts + breadth_pts + news_pts
        verdict = ("accelerating_in" if total >= 3 else
                   "rotating_in" if total == 2 else
                   "stable" if total >= 0 else
                   "rotating_out" if total == -2 else
                   "avoid")
        witnesses = sum(x > 0 for x in
                        (flow_pts, macro_pts, breadth_pts, news_pts))

        # where the momentum lands first — strongest members
        members_sc = sorted(
            ({"symbol": s, "state": mom.get(s) or "—",
              "catalyst": (fb.get(s) or {}).get("title"),
              "in_book": s in book_syms}
             for s in t["members"]),
            key=lambda n: -_MOM_SCORE.get(n["state"], 45))
        leaders = [m for m in members_sc
                   if m["state"] in _POS_MOM][:3]

        why = []
        if rot.get("score") is not None:
            why.append(f"rotation {rot['score']:.0f} · "
                       f"vs SPY20 {(rot.get('vs_spy20') or 0)*100:+.1f}%")
        if ma.get("why"):
            why += ma["why"]
        why.append(f"member breadth {pos}/{len(t['members'])} positive")
        if pos_news:
            why.append(f"{pos_news} fresh catalyst(s) ≤72h")
        if neg_news:
            why.append(f"⚠️ {neg_news} negative alert(s) ≤72h")

        out.append({"key": k, "name": t["name"], "etf": t["etf"],
                    "verdict": verdict, "total": total,
                    "witnesses": witnesses,
                    "leaders": leaders, "why": why,
                    "theme_score": t["score"]})
    out.sort(key=lambda r: -r["total"])
    return out


def _book_symbols() -> list[str]:
    """The de-facto book: open positions + open LEAPS + focus members."""
    from app.database import db
    syms = set()
    try:
        for r in db.execute_query(
                "SELECT DISTINCT symbol FROM "
                "portfolio_agent_position_states WHERE status='OPEN'"):
            syms.add(r["symbol"])
    except Exception:
        pass
    try:
        for r in db.execute_query(
                "SELECT DISTINCT stock_symbol AS s FROM leaps_positions "
                "WHERE status='open'"):
            syms.add(r["s"])
    except Exception:
        pass
    try:
        from app.signals.focus_intel import members
        syms |= set(members())
    except Exception:
        pass
    return sorted(syms)


def theme_scores(morning: Optional[dict],
                 rotation: dict) -> list[dict]:
    """Per-theme composite: tailwind+fundamentals+momentum+money+valuation
    in THEME_W. Every sub-score is evidence-linked."""
    from app.database import db
    mom = {r["symbol"]: r.get("momentum_state") for r in db.execute_query(
        "SELECT symbol, momentum_state FROM stocks "
        "WHERE momentum_state IS NOT NULL")}
    fly = {r["symbol"]: r for r in db.execute_query(
        "SELECT symbol, rev_growth, rev_accel, est_revision_pct, "
        "beat_streak, gap_score, fwd_pe FROM symbol_flywheel")}
    fstate = {r["symbol"]: r.get("fundamental_state")
              for r in db.execute_query(
                  "SELECT symbol, fundamental_state FROM stocks "
                  "WHERE fundamental_state IS NOT NULL")}

    rot = {r["etf"]: r for r in (rotation.get("rows") or [])}
    ai_regime = (morning or {}).get("ai_regime") or "neutral"
    regime = (morning or {}).get("regime") or "neutral"
    ai_tw = {"strong_risk_on": 90, "risk_on": 75, "neutral": 55,
             "risk_off": 35, "stress": 15}.get(ai_regime, 55)
    mkt_tw = {"strong_risk_on": 85, "risk_on": 70, "neutral": 50,
              "risk_off": 30, "stress": 15}.get(regime, 50)

    # bucket-score lookups for tailwind sources keyed off macro state —
    # bucket scores are equity-health oriented: high inflation score =
    # cooling = weak energy tailwind; high growth score = expansion.
    bk = (morning or {}).get("buckets") or {}
    if isinstance(bk, str):
        bk = json.loads(bk)

    def _bs(name: str) -> float:
        try:
            return float((bk.get(name) or {}).get("score", 50))
        except Exception:
            return 50.0

    macro_adj = macro_transmission(morning)

    # capex cycle band → AI-infra tailwind
    capex_tw = None
    try:
        from app.signals.capex_cycle import current
        cx = current() or {}
        band = cx.get("band")
        capex_tw = {"acceleration": 90, "expansion": 75,
                    "plateau": 55, "slowdown": 35,
                    "contraction": 20}.get(str(band).lower())
    except Exception:
        pass

    out = []
    for key, t in THEMES.items():
        members = t["members"]
        rot_row = rot.get(t["etf"]) or {}

        tw_src = t["tailwind_src"]
        if tw_src == "capex" and capex_tw:
            tailwind = capex_tw
        elif tw_src == "ai_regime":
            tailwind = ai_tw
        elif tw_src == "inflation":
            # hot inflation = the energy trade's fuel — invert the
            # equity-health bucket score
            tailwind = _clamp(110 - _bs("inflation"))
        elif tw_src == "growth":
            tailwind = _clamp(_bs("growth") + 10)
        else:
            tailwind = mkt_tw

        fscores, fwhy = [], []
        for s in members:
            f = fly.get(s) or {}
            fs = _FUND_SCORE.get(fstate.get(s) or "", 50)
            rg = f.get("rev_growth")
            if rg is not None:
                fs = _clamp(fs + _clamp(rg * 0.5, -10, 15))
            er = f.get("est_revision_pct")
            if er is not None:
                fs = _clamp(fs + _clamp(er * 0.2, -10, 10))
            fscores.append(fs)
        fundamentals = (sum(fscores) / len(fscores)
                        if fscores else 50.0)
        if members:
            n_acc = sum(1 for s in members
                        if fstate.get(s) in ("accelerating", "growing"))
            fwhy.append(f"{n_acc}/{len(members)} members "
                        "accelerating/growing")

        mscores = [_MOM_SCORE.get(mom.get(s), 45) for s in members]
        mom_members = (sum(mscores) / len(mscores)
                       if mscores else 50.0)
        etf_breadth = rot_row.get("above50"), rot_row.get("above200")
        etf_mom = 60 + (15 if etf_breadth[0] else -15) \
                      + (15 if etf_breadth[1] else -15) \
                      + _clamp((rot_row.get("vs_spy20") or 0) * 400,
                               -15, 15)
        momentum = mom_members * 0.6 + etf_mom * 0.4

        money = rot_row.get("score", 50.0)

        pes = [f["fwd_pe"] for s in members
               if (f := fly.get(s)) and f.get("fwd_pe")]
        med_pe = (sorted(pes)[len(pes) // 2] if pes else None)
        valuation = (_clamp(70 - (med_pe - 25) * 1.5, 10, 90)
                     if med_pe else 50.0)

        score = (tailwind * THEME_W["tailwind"]
                 + fundamentals * THEME_W["fundamentals"]
                 + momentum * THEME_W["momentum"]
                 + money * THEME_W["money_flow"]
                 + valuation * THEME_W["valuation"])
        # macro transmission — bucket-driven tilts applied AFTER the
        # composite: the regime modifies the theme score, it doesn't
        # pick the stocks
        ma = macro_adj.get(key) or {}
        if ma.get("delta"):
            score += ma["delta"]
            fwhy += ma["why"]
        out.append({
            "key": key, "name": t["name"], "etf": t["etf"],
            "score": round(score, 1),
            "parts": {"tailwind": round(tailwind, 1),
                      "fundamentals": round(fundamentals, 1),
                      "momentum": round(momentum, 1),
                      "money_flow": round(money, 1),
                      "valuation": round(valuation, 1)},
            "members": members,
            "member_count": len(members),
            "evidence": fwhy,
            "rotation_row": rot_row or None,
        })
    out.sort(key=lambda r: -r["score"])
    return out


# ---------------------------------------------------------------- weights
def _current_weights(book_syms: list[str]) -> dict[str, float]:
    """Current exposure by theme — latest position snapshot values."""
    from app.database import db
    try:
        rows = db.execute_query(
            "SELECT symbol, current_value FROM "
            "portfolio_agent_position_states "
            "WHERE status='OPEN' AND current_value IS NOT NULL")
    except Exception:
        rows = []
    vals: dict[str, float] = {}
    for r in rows:
        vals[r["symbol"]] = (vals.get(r["symbol"], 0)
                             + float(r["current_value"] or 0))
    total = sum(vals.values())
    member_of = {s: k for k, t in THEMES.items() for s in t["members"]}
    by_theme: dict[str, float] = {}
    for s, v in vals.items():
        by_theme[member_of.get(s, "other")] = \
            by_theme.get(member_of.get(s, "other"), 0) + v
    if total:
        by_theme = {k: round(v / total * 100, 1)
                    for k, v in by_theme.items()}
    return {"by_theme": by_theme, "total_value": round(total, 0),
            "symbols": vals}


def target_weights(themes: list[dict], morning: Optional[dict],
                   earn: dict, event: dict,
                   current: dict) -> dict[str, Any]:
    """Theme scores → target weights, regime-gated and event-trimmed.
    Deltas vs current book carry the reason string."""
    regime = (morning or {}).get("regime") or "neutral"
    deploy_cap = {"strong_risk_on": .95, "risk_on": .85, "neutral": .70,
                  "risk_off": .45, "stress": .20}.get(regime, .70)
    if event.get("density") == "clustered":
        deploy_cap -= .05        # event-dense tape → hold more back

    earn_hair = {"LOW": 1.0, "MEDIUM": .95, "HIGH": .85}.get(
        earn.get("summary"), 1.0)
    el = event.get("election") or {}
    el_hair = {"LOW": 1.0, "MEDIUM": .97, "HIGH": .92,
               "EXTREME": .85}.get(el.get("sensitivity"), 1.0)

    raw = {}
    for t in themes:
        s = t["score"]
        raw[t["key"]] = max(1.0, (s - 35) / 10)   # below ~35 → ~0 weight
    tot = sum(raw.values())
    targets = {k: round(v / tot * deploy_cap * 100, 1)
               for k, v in raw.items()}
    cash = round(100 - sum(targets.values()), 1)

    cur = current.get("by_theme") or {}
    deltas = []
    for t in themes:
        k = t["key"]
        tgt = targets.get(k, 0.0)
        cur_w = cur.get(k, 0.0)
        d = round(tgt - cur_w, 1)
        reasons = []
        if t["score"] >= 70:
            reasons.append(f"theme {t['score']:.0f} — structurally strong")
        elif t["score"] <= 45:
            reasons.append(f"theme {t['score']:.0f} — weak composite")
        rot = t.get("rotation_row") or {}
        if rot.get("score") is not None:
            if rot["score"] >= 65:
                reasons.append("money rotating in")
            elif rot["score"] <= 35:
                reasons.append("money rotating out")
        if abs(d) >= 1.5:
            action = "increase" if d > 0 else "decrease"
            deltas.append({"theme": t["name"], "key": k,
                           "current": cur_w, "target": tgt,
                           "delta": d, "action": action,
                           "reasons": reasons})
    deltas.sort(key=lambda r: -abs(r["delta"]))

    # confirmation: count independent witnesses per direction
    confirm = []
    for t in themes:
        w = 0
        rot = t.get("rotation_row") or {}
        if (rot.get("money5") or 0) > 0.1:
            w += 1
        if (rot.get("vs_spy20") or 0) > 0:
            w += 1
        if t["parts"]["fundamentals"] >= 60:
            w += 1
        if t["parts"]["momentum"] >= 60:
            w += 1
        grade = ("🟢🟢🟢 major" if w >= 4 else
                 "🟢🟢 high-quality" if w == 3 else
                 "🟢 developing" if w == 2 else "🟡 watch")
        confirm.append({"theme": t["name"], "key": t["key"],
                        "witnesses": w, "grade": grade})

    return {"targets": targets, "cash_pct": cash,
            "deploy_cap": deploy_cap,
            "haircuts": {"earnings": earn_hair, "election": el_hair},
            "deltas": deltas, "confirmation": confirm,
            "regime": regime}


# ---------------------------------------------------------------- phases
def phase_playbook(book_syms: list[str],
                   morning: Optional[dict],
                   now: Optional[datetime] = None) -> list[dict]:
    """Date-bounded execution phases — derived from the earnings +
    macro calendar, never a prediction.

    The desk pattern: de-risk while insurance is still cheap (trims
    14-20d before the earnings cluster), freeze execution through the
    information dead zone, deploy reactively into correlated selloffs
    once the numbers are actually out.
    """
    from app.database import db
    today = (now or datetime.now(timezone.utc)).date()
    ed = {r["symbol"]: r["next_earnings_date"] for r in db.execute_query(
        "SELECT symbol, next_earnings_date FROM stocks "
        "WHERE next_earnings_date IS NOT NULL")}

    # book reporting dates — the cluster anchor
    book_dates = sorted(d for s in book_syms
                        if (d := ed.get(s)) and d >= today)
    if not book_dates:
        return []
    # biggest cluster = week with most book prints
    weeks: dict[date, list[str]] = {}
    for s in book_syms:
        d = ed.get(s)
        if not d or d < today or d > today + timedelta(days=60):
            continue
        wk = d - timedelta(days=d.weekday())     # Monday bucket
        weeks.setdefault(wk, []).append(s)
    cluster_start = max(weeks, key=lambda w: len(weeks[w]))
    cluster_end = cluster_start + timedelta(days=6)
    cluster_syms = sorted(weeks[cluster_start])

    # freeze window opens at the earlier of: 14d before the cluster,
    # or the first high-severity macro event inside that window
    from app.market_events.calendar import upcoming_macro_events
    evts = [e for e in upcoming_macro_events(days=60, now=now)
            if e.get("severity") in ("high", "extreme")]
    freeze_start = cluster_start - timedelta(days=13)
    for e in evts:
        try:
            ed_ = date.fromisoformat(str(e["date"]))
        except Exception:
            continue
        if freeze_start <= ed_ < cluster_start:
            freeze_start = ed_                  # freeze from first
            break                               # big print, not later
    if freeze_start <= today:
        freeze_start = today + timedelta(days=1)

    # resolution = last high-severity event within ~45d
    end_evts = [date.fromisoformat(str(e["date"])) for e in evts
                if date.fromisoformat(str(e["date"])) > cluster_end]
    resolution = min(end_evts) if end_evts else cluster_end + timedelta(
        days=10)

    # phase-1 trim candidates: book names in extended states whose
    # report sits inside/after the freeze — act before the IV premium
    mom = {r["symbol"]: (r.get("momentum_state") or "")
           for r in db.execute_query(
               "SELECT symbol, momentum_state FROM stocks")}
    extended = [s for s in book_syms
                if mom.get(s) in ("climax", "breakout", "uptrend")
                and (ed.get(s) or date.max) >= freeze_start]
    # names reporting INSIDE the cluster are hold-through-or-nothing —
    # trimming at <14d out pays the IV premium for nothing
    in_cluster = [s for s in book_syms
                  if cluster_start <= (ed.get(s) or date.max)
                  <= cluster_end]

    regime = (morning or {}).get("regime") or "neutral"

    phases = [{
        "n": 1, "name": "Active de-risking & rebalancing",
        "window": [str(today), str(freeze_start - timedelta(days=1))],
        "criterion": "volatility smile — exit extended names before the "
                     "earnings IV premium prices in (14-20d out)",
        "actions": ["trim extended book names toward target weights",
                    "raise cash toward the strategy cash target",
                    "no new speculative entries this window"],
        "candidates": sorted(set(extended) - set(in_cluster)),
        "rule": "trims now, not inside the freeze",
    }, {
        "n": 2, "name": "Execution freeze — information dead zone",
        "window": [str(freeze_start), str(cluster_start - timedelta(days=1))],
        "criterion": "liquidity optionality — macro prints land but the "
                     "earnings cluster hasn't; moves here are noise",
        "actions": ["hold elevated cash — preserve buying power",
                    "no new positions, no reactive trims",
                    "watch the macro prints; they set phase-3 context"],
        "candidates": [],
        "rule": "react to numbers, not rumors",
    }, {
        "n": 3, "name": "Reactive deployment — earnings cluster",
        "window": [str(cluster_start), str(resolution)],
        "criterion": "concentrated prints — don't predict beats, buy "
                     "quality names dragged down by correlation",
        "actions": ["deploy freeze-phase cash into dragged-down quality",
                    "require swing entry gate (setup + score ≥60)",
                    "keep the election/event haircut on adds"],
        "candidates": sorted(set(cluster_syms)),
        "rule": "deploy on facts; a peer's miss is your discount",
    }, {
        "n": 4, "name": "Post-resolution normalization",
        "window": [str(resolution + timedelta(days=1)), "+45d"],
        "criterion": "events resolved — return to target weights, "
                     "re-run the monthly engine",
        "actions": ["normalize to strategy targets",
                    "re-enter watch-zone LEAPS names on repair"],
        "candidates": [],
        "rule": "back to the weights the scores justify",
    }]
    return {"phases": phases,
            "cluster": {"week": str(cluster_start),
                        "symbols": cluster_syms,
                        "n": len(cluster_syms)},
            "resolution": str(resolution),
            "regime": regime,
            "note": "dates derived from earnings + macro calendar — "
                    "the IV gate upgrades to atm_iv once iv_snapshots "
                    "accrues history"}


def active_phase(now: Optional[datetime] = None) -> Optional[dict]:
    """The phase the book is inside right now + its cluster context.
    Used by the daily board to bind execution rules to the calendar."""
    try:
        pb = phase_playbook(_book_symbols(), None)
        today = (now or datetime.now(timezone.utc)).date().isoformat()
        for p in pb.get("phases") or []:
            w0, w1 = p["window"]
            if w0 <= today and (w1 == "+45d" or today <= w1):
                return {**p, "cluster": pb.get("cluster")}
    except Exception as exc:
        logger.debug("active_phase failed: %s", exc)
    return None


def peer_drag_symbols(phase: Optional[dict],
                      threshold: float = -0.025) -> set[str]:
    """Phase-3 reactive flag — names down ≥threshold on the day while a
    theme-mate is printing. A gap on sympathy, not on their own news,
    is the 'unfairly dragged' setup the deploy phase exists to buy."""
    if not phase or phase.get("n") != 3:
        return set()
    cluster = set((phase.get("cluster") or {}).get("symbols") or [])
    member_of = {s: k for k, t in THEMES.items() for s in t["members"]}
    cluster_themes = {member_of.get(s) for s in cluster}
    candidates = cluster | {s for k, t in THEMES.items()
                            if k in cluster_themes for s in t["members"]}
    if not candidates:
        return set()
    from app.database import db
    ph = ",".join(f"'{s}'" for s in candidates)
    try:
        rows = db.execute_query(
            f"SELECT symbol, close FROM daily_bars "
            f"WHERE symbol IN ({ph}) AND date >= "
            f"(SELECT max(date) FROM daily_bars) - 3 "
            f"ORDER BY symbol, date DESC")
    except Exception:
        return set()
    by_sym: dict[str, list[float]] = {}
    for r in rows:
        by_sym.setdefault(r["symbol"], []).append(float(r["close"]))
    out = set()
    for s, c in by_sym.items():
        if len(c) >= 2 and c[1] and c[0] / c[1] - 1 <= threshold:
            out.add(s)
    return out


# ---------------------------------------------------------------- journal
def journal(payload: dict) -> None:
    from app.database import db
    try:
        db.execute_update(
            "INSERT INTO strategy_snapshots "
            "(snap_date, engine_version, payload) "
            "VALUES (:d, :v, CAST(:p AS jsonb)) "
            "ON CONFLICT (snap_date) DO UPDATE SET "
            "engine_version=:v, payload=CAST(:p AS jsonb), "
            "created_at=now()",
            {"d": date.today().isoformat(), "v": ENGINE_VERSION,
             "p": json.dumps(payload, default=str)})
    except Exception as exc:
        logger.debug("strategy journal failed: %s", exc)


def snapshot() -> dict[str, Any]:
    """Full strategy assembly — deterministic, journaled, advisory."""
    from app.database import db
    morning = None
    try:
        r = db.execute_query(
            "SELECT regime, ai_regime, score, verdict, buckets, "
            "horizon_1m, horizon_3m FROM morning_regime_snapshots "
            "ORDER BY as_of DESC LIMIT 1")
        if r:
            morning = dict(r[0])
            v = morning.pop("verdict", None) or {}
            if isinstance(v, str):
                v = json.loads(v)
            morning["event_risk"] = v.get("event_risk")
    except Exception:
        pass

    rotation = money_rotation()
    event = event_layer()
    book = _book_symbols()
    playbook = phase_playbook(book, morning)
    earn = earnings_layer(book)
    agentic = agentic_layer(book)
    themes = theme_scores(morning, rotation)
    current = _current_weights(book)
    weights = target_weights(themes, morning, earn, event, current)
    bk = (morning or {}).get("buckets") or {}
    if isinstance(bk, str):
        bk = json.loads(bk)
    direction = rotation_direction(themes, rotation,
                                   macro_transmission(morning), book)

    payload = {"as_of": datetime.now(timezone.utc).isoformat(
                   timespec="seconds"),
               "engine_version": ENGINE_VERSION,
               "morning": morning,
               "rotation": rotation,
               "events": {k: event[k] for k in
                          ("election", "density", "high_next10",
                           "heatmap")},
               "earnings": earn,
               "playbook": playbook,
               "agentic": agentic,
               "direction": direction,
               "themes": themes,
               "book": {"symbols": book, "n": len(book)},
               "current": current,
               "weights": weights}
    journal(payload)
    return payload
