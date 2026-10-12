"""Rotation backtest — replay the sector/theme flow classifier over
stored daily_bars and ask the two questions that matter:

  1. DETECTION — when a real theme rotation happened (e.g. June-2026
     semis→software), how early did the flow labels fire vs. the
     confirmed 20d trend flip?
  2. EDGE — do "rotating_in"/"inflow" signals actually precede
     forward outperformance vs. the rotated-out theme and vs. SPY?

Method: for each day t with enough history, recompute the exact
_sector_flows logic (5d ret, 20d ret vs SPY, vs 50dma) on the bars
available up to t — no lookahead, the same read the board would have
printed that morning. A ROTATION EVENT fires when:

    theme A flips to outflow  AND
    theme B flips to rotating_in or inflow (wasn't the prior day)

Then measure B−A relative return and B−SPY over +10/+20/+40 sessions.
The honest read: an early signal that doesn't predict forward returns
is noise; one that does is a real edge worth weighting.
"""
from __future__ import annotations

import logging
import statistics as st
from collections import defaultdict
from datetime import date
from typing import Any, Optional

logger = logging.getLogger(__name__)

_PAIRS = [("SMH", "IGV"), ("IGV", "SMH"), ("SMH", "XLK"),
          ("XLY", "XLP"), ("XLK", "XLU"), ("ARKK", "SMH"),
          ("XBI", "XLV"), ("KRE", "XLF")]


def _flow(closes: list[float], spy20: float,
          vols: Optional[list[float]] = None) -> Optional[dict]:
    """The exact classifier from allocation._sector_flows, on a
    closes slice — same thresholds, no lookahead. When vols are
    passed, also computes the money-flow read: signed 5d volume
    share (up-day vol − down-day vol / total) and the 5d/20d
    volume ratio (is the move happening on EXPANDING volume — the
    desk's real 'money moving' tell)."""
    if len(closes) < 51:
        return None
    r5 = closes[-1] / closes[-6] - 1
    r20 = closes[-1] / closes[-21] - 1
    s50 = sum(closes[-50:]) / 50
    above50 = closes[-1] > s50
    if r5 > 0.01 and not above50:
        flow = "rotating_in"
    elif r5 > 0.005 and above50:
        flow = "inflow"
    elif r5 < -0.01 and not above50:
        flow = "outflow"
    else:
        flow = "quiet"
    money5 = vol_ratio = None
    if vols and len(vols) >= 21 and sum(vols[-5:]) > 0:
        signed = sum((1 if closes[-i] >= closes[-i - 1] else -1)
                     * vols[-i] for i in range(1, 6))
        money5 = signed / sum(vols[-5:])          # -1..+1 net direction
        avg5 = sum(vols[-5:]) / 5
        avg20 = sum(vols[-21:-1]) / 20
        vol_ratio = avg5 / avg20 if avg20 else None
    return {"flow": flow, "r5": r5, "r20": r20,
            "vs_spy20": r20 - spy20, "above50": above50,
            "money5": money5, "vol_ratio": vol_ratio}


def replay() -> dict[str, Any]:
    from app.market_data import bars as bars_mod
    syms = list({s for pair in _PAIRS for s in pair} | {"SPY"})
    books = bars_mod.load(syms, days=510)
    closes = {s: [b.close for b in books.get(s) or []] for s in syms}
    vols = {s: [b.volume or 0 for b in books.get(s) or []] for s in syms}
    dates = {s: [b.date for b in books.get(s) or []] for s in syms}
    spy = closes.get("SPY") or []
    if len(spy) < 80:
        return {"error": "insufficient SPY history"}

    events = []          # rotation events with forward outcomes
    daylog = []          # every day's pair-state (for the June audit)
    for i in range(51, len(spy)):
        spy20 = spy[i] / spy[i - 20] - 1
        spy20p = spy[i - 1] / spy[i - 21] - 1
        d = dates["SPY"][i]
        for a, b in _PAIRS:
            ca, cb = closes.get(a) or [], closes.get(b) or []
            va, vb = vols.get(a) or [], vols.get(b) or []
            if len(ca) <= i or len(cb) <= i:
                continue
            fa = _flow(ca[:i + 1], spy20, va[:i + 1])
            fb = _flow(cb[:i + 1], spy20, vb[:i + 1])
            fa0 = _flow(ca[:i], spy20p, va[:i])
            fb0 = _flow(cb[:i], spy20p, vb[:i])
            if not fa or not fb:
                continue
            inb = fb["flow"] in ("rotating_in", "inflow")
            inb0 = fb0 and fb0["flow"] in ("rotating_in", "inflow")
            daylog.append({"date": str(d), "from": a, "to": b,
                           "a_flow": fa["flow"], "b_flow": fb["flow"]})
            if not (fa["flow"] == "outflow" and inb and not inb0):
                continue
            # forward relative returns — the edge question
            fwd = {}
            for h in (10, 20, 40):
                if len(cb) > i + h and len(ca) > i + h:
                    rb = cb[i + h] / cb[i] - 1
                    ra = ca[i + h] / ca[i] - 1
                    rs = spy[i + h] / spy[i] - 1
                    fwd[f"rel_{h}d"] = round((rb - ra) * 100, 2)
                    fwd[f"b_vs_spy_{h}d"] = round((rb - rs) * 100, 2)
            # money confirmation: to-ETF buying on expanding volume,
            # from-ETF bleeding on expanding volume
            b_money = (fb["money5"] or 0) > 0 and \
                (fb["vol_ratio"] or 0) > 1.0
            a_dist = (fa["money5"] or 0) < 0
            events.append({"date": str(d), "from": a, "to": b,
                           "b_flow": fb["flow"],
                           "a_r20": round(fa["r20"] * 100, 1),
                           "b_r20": round(fb["r20"] * 100, 1),
                           "b_money5": round(fb["money5"] or 0, 2),
                           "b_volx": round(fb["vol_ratio"] or 0, 2),
                           "vol_confirmed": bool(b_money and a_dist),
                           **fwd})
    return _summarize(events, daylog)


def _edge_cells(events: list[dict]) -> list[dict]:
    cells = []
    for h in (10, 20, 40):
        rel = [e[f"rel_{h}d"] for e in events if f"rel_{h}d" in e]
        bvs = [e[f"b_vs_spy_{h}d"] for e in events
               if f"b_vs_spy_{h}d" in e]
        if len(rel) < 3:
            continue
        cells.append({
            "horizon": f"{h}d", "n": len(rel),
            "avg_rel": round(st.mean(rel), 2),
            "med_rel": round(st.median(rel), 2),
            "hit_rate": round(100 * sum(1 for x in rel if x > 0)
                              / len(rel)),
            "avg_vs_spy": round(st.mean(bvs), 2) if bvs else None})
    return cells


def _summarize(events: list[dict], daylog: list[dict]) -> dict:
    out = {"events_n": len(events), "events": events[:40]}
    out["edge"] = _edge_cells(events)
    # the money-flow question — does volume confirmation add edge?
    conf = [e for e in events if e.get("vol_confirmed")]
    bare = [e for e in events if not e.get("vol_confirmed")]
    out["vol_confirmed_edge"] = _edge_cells(conf)
    out["unconfirmed_edge"] = _edge_cells(bare)
    out["n_vol_confirmed"] = len(conf)
    # per-pair breakdown — which rotations actually carry signal
    by_pair = defaultdict(list)
    for e in events:
        if "rel_20d" in e:
            by_pair[f"{e['from']}→{e['to']}"].append(e["rel_20d"])
    out["by_pair_20d"] = {
        k: {"n": len(v), "avg": round(st.mean(v), 2),
            "hit": round(100 * sum(1 for x in v if x > 0) / len(v))}
        for k, v in by_pair.items() if len(v) >= 2}
    return out


def june_audit() -> dict[str, Any]:
    """The user's question specifically: did the flow read catch the
    June-2026 semis→software rotation early? Replay SMH/IGV daily
    through May–Aug 2026 and show the day-by-day label trail."""
    from app.market_data import bars as bars_mod
    books = bars_mod.load(["SMH", "IGV", "SPY"], days=510)
    smh = books.get("SMH") or []
    igv = books.get("IGV") or []
    spy = [b.close for b in books.get("SPY") or []]
    dts = [b.date for b in books.get("SPY") or []]
    smh_c = [b.close for b in smh]
    igv_c = [b.close for b in igv]
    trail = []
    for i in range(51, len(spy)):
        d = dts[i]
        if not (d.month in (5, 6, 7, 8) and d.year == 2026):
            continue
        spy20 = spy[i] / spy[i - 20] - 1
        fs = _flow(smh_c[:i + 1], spy20)
        fi = _flow(igv_c[:i + 1], spy20)
        if not fs or not fi:
            continue
        trail.append({"date": str(d),
                      "SMH": fs["flow"], "IGV": fi["flow"],
                      "smh_vs_spy": round(fs["vs_spy20"] * 100, 1),
                      "igv_vs_spy": round(fi["vs_spy20"] * 100, 1)})
    # first day IGV showed accumulation while SMH bled
    first_signal = next(
        (t for t in trail if t["IGV"] in ("rotating_in", "inflow")
         and t["SMH"] in ("outflow", "quiet")), None)
    # the confirmed flip: IGV 20d-vs-SPY crosses above SMH's
    confirm = next(
        (t for t in trail if t["igv_vs_spy"] > t["smh_vs_spy"]), None)
    return {"trail_days": len(trail),
            "first_rotation_signal": first_signal,
            "trend_confirm_day": confirm,
            "lead_days": ((dts.index(
                __import__("datetime").date.fromisoformat(
                    confirm["date"])) if confirm else 0)
                - (dts.index(
                    __import__("datetime").date.fromisoformat(
                        first_signal["date"]))
                   if first_signal else 0))
            if first_signal and confirm else None,
            "trail": trail[-60:]}


# ------------------------------------------------- journal + grade live

def journal_today() -> dict[str, Any]:
    """Detect today's rotation events on the live flow read and journal
    them — idempotent per (day, pair). Called from the momentum job so
    events accrue without page views; evaluate() grades them later."""
    from app.database import db
    from app.market_data import bars as bars_mod
    syms = list({s for pair in _PAIRS for s in pair} | {"SPY"})
    books = bars_mod.load(syms, days=80)
    spy = [b.close for b in books.get("SPY") or []]
    if len(spy) < 55:
        return {"events": 0}
    spy20 = spy[-1] / spy[-21] - 1
    spy20_prev = spy[-2] / spy[-22] - 1
    made = 0
    for a, b in _PAIRS:
        ba, bb = books.get(a) or [], books.get(b) or []
        ca = [x.close for x in ba]
        cb = [x.close for x in bb]
        va = [x.volume or 0 for x in ba]
        vb = [x.volume or 0 for x in bb]
        if len(ca) < 55 or len(cb) < 55:
            continue
        fa = _flow(ca, spy20, va)
        fb = _flow(cb, spy20, vb)
        fb0 = _flow(cb[:-1], spy20_prev, vb[:-1])
        if not (fa and fb and fb0):
            continue
        was_in = fb0["flow"] in ("rotating_in", "inflow")
        if fa["flow"] == "outflow" and fb["flow"] in (
                "rotating_in", "inflow") and not was_in:
            # volume confirmation — the replay's edge filter:
            # money5>0 on expanding volume into B while A bleeds
            vol_conf = bool((fb["money5"] or 0) > 0
                            and (fb["vol_ratio"] or 0) > 1.0
                            and (fa["money5"] or 0) < 0)
            db.execute_update(
                """INSERT INTO rotation_events
                   (as_of, from_etf, to_etf, to_flow, from_r20,
                    to_r20, to_money5, to_vol_ratio, vol_confirmed)
                   VALUES (:d, :a, :b, :f, :ar, :br, :m, :vr, :vc)
                   ON CONFLICT (as_of, from_etf, to_etf) DO NOTHING""",
                {"d": date.today(), "a": a, "b": b,
                 "f": fb["flow"], "ar": round(fa["r20"] * 100, 1),
                 "br": round(fb["r20"] * 100, 1),
                 "m": fb.get("money5"), "vr": fb.get("vol_ratio"),
                 "vc": vol_conf})
            made += 1
    return {"events": made}


def evaluate() -> dict[str, Any]:
    """Grade journaled rotation events — the forward B−A relative
    return at 10/20/40 sessions, plus B vs SPY at 20d."""
    from app.database import db
    from app.market_data import bars as bars_mod
    rows = db.execute_query(
        """SELECT id, as_of, from_etf, to_etf FROM rotation_events
           WHERE rel_20d IS NULL""")
    done = 0
    for r in rows:
        try:
            books = bars_mod.load([r["from_etf"], r["to_etf"], "SPY"],
                                  days=120)
            got = {}
            for sym in (r["from_etf"], r["to_etf"], "SPY"):
                bars = [b for b in (books.get(sym) or [])
                        if b.date >= r["as_of"]]
                got[sym] = bars
            ea, eb, es = (got[r["from_etf"]], got[r["to_etf"]],
                          got["SPY"])
            if len(ea) < 21 or len(eb) < 21:
                continue
            up = {"i": r["id"]}
            for h, col in ((10, "rel_10d"), (20, "rel_20d"),
                           (40, "rel_40d")):
                if len(ea) > h and len(eb) > h:
                    up[col] = round(
                        (eb[h].close / eb[0].close
                         - ea[h].close / ea[0].close) * 100, 2)
            if len(es) > 20 and len(eb) > 20:
                up["vsp"] = round(
                    (eb[20].close / eb[0].close
                     - es[20].close / es[0].close) * 100, 2)
            db.execute_update(
                """UPDATE rotation_events SET
                    rel_10d=:r10, rel_20d=:r20, rel_40d=:r40,
                    to_vs_spy_20d=:vsp, graded_at=now() WHERE id=:i""",
                {"r10": up.get("rel_10d"), "r20": up.get("rel_20d"),
                 "r40": up.get("rel_40d"), "vsp": up.get("vsp"),
                 "i": r["id"]})
            done += 1
        except Exception as exc:
            logger.debug("rotation grade %s %s→%s: %s",
                         r["as_of"], r["from_etf"], r["to_etf"], exc)
    return {"evaluated": done}


def record() -> dict[str, Any]:
    """Graded rotation edge per pair — which direction actually pays."""
    from app.database import db
    rows = db.execute_query(
        """SELECT from_etf || '→' || to_etf pair, count(*) n,
              round(avg(rel_20d)::numeric, 2) avg_rel20,
              round(100.0 * avg(CASE WHEN rel_20d > 0 THEN 1
                                ELSE 0 END), 0) hit_rate,
              round(avg(to_vs_spy_20d)::numeric, 2) avg_vs_spy
           FROM rotation_events WHERE rel_20d IS NOT NULL
           GROUP BY 1 ORDER BY avg_rel20 DESC""")
    vol = db.execute_query(
        """SELECT vol_confirmed, count(*) n,
              round(avg(rel_20d)::numeric, 2) avg_rel20,
              round(100.0 * avg(CASE WHEN rel_20d > 0 THEN 1
                                ELSE 0 END), 0) hit_rate
           FROM rotation_events WHERE rel_20d IS NOT NULL
           GROUP BY vol_confirmed""")
    return {"pairs": rows,
            "by_volume_confirmation": vol,
            "graded": sum(r["n"] for r in rows)}
