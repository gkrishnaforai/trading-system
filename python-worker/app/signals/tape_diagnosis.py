"""Why is it moving? — the tape diagnosis.

The health card NAMES the conflict (accelerating fundamentals vs
knife tape); this explains the CAUSE using the institutional
decomposition:

  1. attribution   market beta → sector rotation → idiosyncratic
                   (stock_5d vs sector-etf_5d vs SPY_5d — the bucket
                   that dominates names the cause class)
  2. event wire    alert_items + analyst grade actions in the
                   weakness window — downgrades, EPS cuts, insider
                   sales, short reports; absence is itself evidence
  3. expectations  priced_status + extension — 'priced for
                   perfection' turns a forward reset into a derating
                   even while trailing fundamentals accelerate
  4. structure     sessions-in-state, avwap/support breaks,
                   earnings proximity (pre-earnings de-risking)

Both directions: weak tape gets the same attribution as strong
tape — a +15% spike with no catalyst and no fundamentals is hype
risk; a catalyst-backed move on strong fundamentals is earned
momentum. Deterministic, first-match-wins; 'unexplained' is a
valid answer — institutions say it, so do we.
"""
from typing import Any, Optional

_WEAK = {"knife", "breakdown", "capitulation", "downtrend",
         "rolling_over"}
_STRONG = {"breakout", "uptrend", "climax"}
_SECTOR_ETF = {
    "technology": "XLK", "information technology": "XLK",
    "communication services": "XLC",
    "financials": "XLF", "financial services": "XLF",
    "healthcare": "XLV", "health care": "XLV",
    "energy": "XLE", "industrials": "XLI",
    "consumer staples": "XLP", "consumer defensive": "XLP",
    "consumer discretionary": "XLY", "consumer cyclical": "XLY",
    "materials": "XLB", "basic materials": "XLB",
    "real estate": "XLRE", "utilities": "XLU",
}
_EVENT_WINDOW_D = 14


def _returns(symbols: list[str]) -> dict[str, dict]:
    """5d/20d simple returns from daily_bars."""
    from app.database import db
    out = {}
    rows = db.execute_query(
        "SELECT symbol, date, close FROM daily_bars"
        " WHERE symbol = ANY(:s) ORDER BY symbol, date",
        {"s": list(symbols)})
    by = {}
    for r in rows:
        by.setdefault(r["symbol"], []).append(float(r["close"]))
    for s, px in by.items():
        out[s] = {
            "5d": round(px[-1] / px[-6] - 1, 4) if len(px) > 5 else None,
            "20d": round(px[-1] / px[-21] - 1, 4) if len(px) > 20
                  else None,
        }
    return out


def _events(sym: str, direction: str) -> list[dict]:
    """Directional alerts inside the window — the event wire."""
    from app.database import db
    rows = db.execute_query(
        "SELECT event_type, direction, title, materiality,"
        " created_at::date AS d FROM alert_items"
        " WHERE symbol=:s AND direction=:d"
        " AND created_at >= now() - (:w || ' days')::interval"
        " ORDER BY created_at DESC LIMIT 12",
        {"s": sym, "d": direction, "w": _EVENT_WINDOW_D})
    seen, out = set(), []
    for r in rows:
        t = (r["title"] or "").strip()
        key = t[:40].lower()
        if key in seen:
            continue
        seen.add(key)
        out.append({"date": str(r["d"]), "type": r["event_type"],
                    "title": t[:90], "materiality": r["materiality"]})
    return out[:5]


def _grade_actions(sym: str) -> list[dict]:
    """Recent analyst grade actions — upgrades/downgrades only."""
    from app.database import db
    rows = db.execute_query(
        "SELECT grade_date, grading_company, previous_grade,"
        " new_grade, action FROM stock_grades"
        " WHERE symbol=:s AND action IN ('upgrade','downgrade')"
        " AND grade_date >= CURRENT_DATE - (:w || ' days')::interval"
        " ORDER BY grade_date DESC LIMIT 5",
        {"s": sym, "w": _EVENT_WINDOW_D})
    return [{"date": str(r["grade_date"]), "firm": r["grading_company"],
             "action": r["action"],
             "title": f"{r['grading_company']} {r['action']} "
                      f"{r['previous_grade']}→{r['new_grade']}"}
            for r in rows]


def _sessions_in_state(sym: str, state: str) -> int:
    from app.database import db
    rows = db.execute_query(
        "SELECT state FROM momentum_state_log WHERE symbol=:s"
        " ORDER BY as_of DESC, id DESC LIMIT 15", {"s": sym})
    n = 0
    for r in rows:
        if r["state"] != state:
            break
        n += 1
    return n


def _explain(sym: str, direction: str, rets: dict,
             events: list, grades: list, *, sector_etf: str,
             fund: Optional[str], priced: Optional[str],
             det: dict, next_earnings: Optional[str]) -> dict:
    """First-match-wins verdict — the named cause class."""
    s5 = (rets.get(sym) or {}).get("5d")
    m5 = (rets.get("SPY") or {}).get("5d")
    e5 = (rets.get(sector_etf) or {}).get("5d")
    causes = [f"{e['date']} · {e['title']}" for e in events]
    causes += [f"{g['date']} · {g['title']}" for g in grades]

    dd52w = det.get("dd52w")
    ext = det.get("vs_sma50")
    pct_b = det.get("pct_b")
    priced_rich = priced in ("substantial", "extreme", "stretched")
    fund_strong = fund in ("accelerating", "growing")
    fund_weak = fund in ("declining", "deteriorating", "pressured")
    note = None

    # excess-return attribution: how much of the stock's move NOT
    # explained by the market is explained by the sector. raw-ratio
    # tests misfire when the stock amplifies the sector (a name down
    # 2.5× its group is idiosyncratic-with-headwind, not rotation).
    x_stock = x_sect = share = None
    if s5 is not None and m5 is not None:
        x_stock = s5 - m5
    if e5 is not None and m5 is not None:
        x_sect = e5 - m5
    if x_stock and x_sect and (x_stock < 0) == (x_sect < 0):
        share = x_sect / x_stock

    if direction == "weak":
        if (x_stock is not None and m5 <= -0.02
                and abs(x_stock) <= abs(m5) * 0.8):
            v, line = "market_beta", (
                "falling with the tape — the market is down and the "
                "stock is moving roughly with it")
        elif (share is not None and share >= 0.5
                and (e5 or 0) <= -0.02):
            v, line = "sector_rotation", (
                f"sector rotation — {sector_etf} {e5:+.1%} 5d "
                f"explains ~{share * 100:.0f}% of the fall; the "
                f"group is being sold, not just this name")
        elif events or grades:
            v = "idiosyncratic_catalyst"
            line = ("documented catalysts — the street had specific "
                    "reasons to sell this name")
        elif priced_rich:
            v = "multiple_compression"
            line = ("multiple compression — priced for perfection; "
                    "forward resets derate the multiple even while "
                    "trailing fundamentals hold")
        else:
            v, line = "unexplained", (
                "unexplained — no market, sector, or documented "
                "catalyst; flow-driven. Watch for the shoe to drop")
        if next_earnings:
            from datetime import date
            try:
                d = (date.fromisoformat(str(next_earnings)[:10])
                     - date.today()).days
                if 0 <= d <= 15:
                    note = (f"earnings in {d}d — pre-earnings "
                            f"de-risking may amplify the drift")
            except Exception:
                pass
        if share is not None and 0.3 <= share < 0.5:
            note = (note or "") + (" · " if note else "") + (
                f"partly sector — {sector_etf} {e5:+.1%} is a "
                f"headwind, but the stock fell harder; "
                f"stock-specific selling dominates")
        if fund_strong and v in ("idiosyncratic_catalyst",
                                 "multiple_compression"):
            note = (note or "") + (" · " if note else "") + (
                f"`{fund}` is trailing — the price is reacting to "
                f"the forward reset, not the reported quarters")
        return {"verdict": v, "line": line, "causes": causes,
                "note": note or None}

    # ---- strong direction ------------------------------------------------
    spike = s5 is not None and s5 >= 0.10
    stretched = ((ext or 0) > 0.15) or ((pct_b or 0) > 1.0)
    if (x_stock is not None and m5 >= 0.02
            and abs(x_stock) <= abs(m5) * 0.8):
        v, line = "market_beta", (
            "riding the tape — the market is up and the stock is "
            "moving with it; beta, not alpha")
    elif (share is not None and share >= 0.5
            and (e5 or 0) >= 0.02):
        v, line = "sector_rotation", (
            f"sector-led move — {sector_etf} {e5:+.1%} 5d explains "
            f"~{share * 100:.0f}% of the move; the tide is lifting "
            f"the group")
    elif events or grades:
        if fund_strong:
            v, line = "earned_momentum", (
                "catalyst-backed and the business confirms — "
                "real momentum, not just a headline pop")
        else:
            v, line = "catalyst_bounce", (
                "headline-driven pop — catalysts present but the "
                "business doesn't confirm yet; fades are common")
    elif fund_strong and not priced_rich:
        v, line = "earned_momentum", (
            "quiet strength — no headline, but fundamentals are "
            "improving and pricing isn't stretched; institutional "
            "accumulation pattern")
    elif (spike or stretched) and fund_weak:
        v, line = "hype_risk", (
            "unexplained spike on weak fundamentals — no visible "
            "catalyst; squeeze/hype risk, don't chase")
    elif spike or stretched:
        v, line = "unexplained_spike", (
            "sharp move, no documented catalyst — could be "
            "positioning or a squeeze; confirm before chasing")
    else:
        v, line = "flow_drift", (
            "momentum without a visible catalyst — positioning/flow; "
            "watch for confirmation")
    return {"verdict": v, "line": line, "causes": causes,
            "note": note}


def diagnose(sym: str, *, sector: Optional[str],
             momentum_state: Optional[str], momentum_detail: dict,
             fundamental_state: Optional[str], priced_status:
             Optional[str], next_earnings: Optional[str]) -> dict:
    """The 'why is it moving' read — attribution + event wire +
    expectation layer → a named cause class."""
    sector_etf = _SECTOR_ETF.get((sector or "").lower())
    syms = [sym, "SPY"] + ([sector_etf] if sector_etf else [])
    rets = _returns(syms)
    s5 = (rets.get(sym) or {}).get("5d")

    # the MOVE decides direction; the state label is context. a −5%
    # week inside an 'uptrend' is a fall to explain (pullback-in-
    # trend), not an up-move — the old state-first gate hid exactly
    # the cases this panel exists for.
    if s5 is not None and s5 <= -0.03:
        direction, direction_lbl = "weak", "falling"
    elif s5 is not None and s5 >= 0.03:
        direction, direction_lbl = "strong", "moving"
    elif momentum_state in _WEAK:
        direction, direction_lbl = "weak", "falling"
    elif momentum_state in _STRONG:
        direction, direction_lbl = "strong", "moving"
    else:
        return {}
    divergence = ((direction == "weak" and momentum_state in _STRONG)
                  or (direction == "strong"
                      and momentum_state in _WEAK))
    ev_dir = "NEGATIVE" if direction == "weak" else "POSITIVE"
    events = _events(sym, ev_dir)
    grades = [g for g in _grade_actions(sym)
              if g["action"] == ("downgrade" if direction == "weak"
                                 else "upgrade")]
    sessions = _sessions_in_state(sym, momentum_state)
    verdict = _explain(sym, direction, rets, events, grades,
                       sector_etf=sector_etf or "SPY",
                       fund=fundamental_state, priced=priced_status,
                       det=momentum_detail or {},
                       next_earnings=next_earnings)
    div_txt = None
    if divergence and momentum_state:
        div_txt = ("pullback inside an uptrend — the week is weak, "
                   "the trend isn't" if direction == "weak" else
                   "bounce inside a broken trend — the week is "
                   "strong, the trend isn't")
        verdict["note"] = (verdict.get("note") or "") + (
            " · " if verdict.get("note") else "") + div_txt
    return {
        "direction": direction, "state": momentum_state,
        "sessions_in_state": sessions,
        "attribution": {
            "stock_5d": s5,
            "stock_20d": (rets.get(sym) or {}).get("20d"),
            "sector_etf": sector_etf,
            "sector_5d": (rets.get(sector_etf) or {}).get("5d")
                         if sector_etf else None,
            "spy_5d": (rets.get("SPY") or {}).get("5d"),
        },
        **verdict,
        "label": (f"why is it {direction_lbl}? "
                  f"{(s5 or 0) * 100:+.1f}% 5d · "
                  f"{momentum_state or '—'} for {sessions} sessions"
                  + (f" ({div_txt.split(' — ')[0]})"
                     if div_txt else "")),
    }
