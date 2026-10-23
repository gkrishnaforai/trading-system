"""3x semiconductor ETF swing detector — SOXS / SOXL.

YAML-driven (leveraged_swings.yaml): the policy — thresholds, leg
roles, veto, stop anchor, targets, risk budget — is declarative and
evaluated through pulse_engine._eval_when, the same condition
semantics as the pulse and best-picks engines. This module owns only
the MECHANICS: tape-feature ctx construction, the flat→armed→
triggered→vetoed state derivation, index→ETF stop translation via
the 3x daily-move map, R-multiple targets, sizing, and the daily
journal. Output is advisory — hypotheses to grade, never orders.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import Any, Optional

import yaml

from app.signals.momentum_regime import _rsi_simple
from app.signals.pulse_engine import _eval_when

logger = logging.getLogger(__name__)

_SPEC_PATH = Path(__file__).with_name("leveraged_swings.yaml")
_spec: Optional[dict] = None


def _load() -> dict:
    global _spec
    if _spec is None:
        _spec = yaml.safe_load(_SPEC_PATH.read_text())
    return _spec


def rules_version() -> str:
    return f"lev_swings.v{_load()['version']}"


def _ema(closes: list[float], n: int) -> list[float]:
    """Plain EMA series — same formula as _technicals' ema8."""
    if not closes:
        return []
    k, out = 2 / (n + 1), [closes[0]]
    for c in closes[1:]:
        out.append(c * k + out[-1] * (1 - k))
    return out


def _leader_tape(spec: dict) -> dict[str, Any]:
    """Bulk momentum_state read for the semis leadership list."""
    from app.database import db
    rows = db.execute_query(
        "SELECT symbol, momentum_state FROM stocks"
        " WHERE symbol = ANY(:s)", {"s": list(spec["leaders"])})
    tape = {r["symbol"]: r["momentum_state"] for r in rows}
    constr = {s for s, st in tape.items()
              if st in set(spec["constructive_states"])}
    hostile = {s for s, st in tape.items()
               if st in set(spec["hostile_states"])}
    return {"tracked": len(tape),
            "constructive": sorted(constr), "hostile": sorted(hostile),
            "ratio": (round(len(constr) / len(tape), 2)
                      if tape else None)}


def _semi_alerts(spec: dict) -> dict[str, Any]:
    """Recent HIGH-materiality NEGATIVE alerts on semis — the
    'catalyst that breaks support' caution for SOXL."""
    from app.database import db
    days = spec["catalyst_window_days"]
    syms = list(spec["leaders"]) + list(spec["catalyst_symbols_extra"])
    rows = db.execute_query(
        "SELECT symbol, title, created_at FROM alert_items"
        " WHERE direction = 'NEGATIVE' AND materiality = 'HIGH'"
        " AND symbol = ANY(:s)"
        " AND created_at >= now() - interval :days"
        " ORDER BY created_at DESC LIMIT 5",
        {"s": syms, "days": f"{days} days"})
    return {"count": len(rows),
            "items": [{"symbol": r["symbol"],
                       "title": (r["title"] or "")[:80]} for r in rows]}


def _portfolio_mv() -> Optional[float]:
    """Current portfolio market value for default sizing."""
    from app.database import db
    r = db.execute_query(
        "SELECT COALESCE(SUM(COALESCE(current_value,"
        " quantity * avg_price)), 0) mv"
        " FROM portfolio_positions")[0]
    mv = float(r["mv"] or 0)
    return mv if mv > 0 else None


def _vol_dip(bars) -> Optional[float]:
    """Down-day volume vs 20d average — <1 = sellers exhausting."""
    dn = [b.volume for b in bars[-10:] if b.close < b.open]
    al = [b.volume for b in bars[-20:]]
    if not dn or not al or not sum(al):
        return None
    return (sum(dn) / len(dn)) / (sum(al) / len(al))


def _taped(bars, spec: dict) -> Optional[dict[str, Any]]:
    """Index-tape features — the ctx every YAML leg binds against.

    RSI/stretch extremes are `extreme_window`-bar RECENT peaks, not
    same-bar values: 'RSI reaches 75-80, then closes below the 8EMA'
    is a sequence; by the trigger bar the current RSI has moved off
    the extreme."""
    if not bars or len(bars) < 60:
        return None
    win = spec["extreme_window"]
    sw, sp = spec["support_window"], spec["support_pct"]
    hw = spec["swing_hi_window"]
    closes = [b.close for b in bars]
    highs, lows = [b.high for b in bars], [b.low for b in bars]
    sma50 = sum(closes[-50:]) / 50
    ema8 = _ema(closes, 8)
    hi_i = max(range(len(highs) - hw, len(highs)), key=highs.__getitem__)
    rsis = [_rsi_simple(closes[:i])
            for i in range(len(closes) - win, len(closes) + 1)]
    rsis = [r for r in rsis if r is not None]
    vs50s = [closes[i] / (sum(closes[i - 49:i + 1]) / 50) - 1
             for i in range(len(closes) - win, len(closes))]
    swing_low = min(lows[-sw:-5])
    return {
        "close": closes[-1], "rsi": _rsi_simple(closes),
        "rsi_hi7": max(rsis) if rsis else None,
        "rsi_lo7": min(rsis) if rsis else None,
        "vs50_hi7": max(vs50s) if vs50s else None,
        "rsi_dir": ((_rsi_simple(closes) or 0)
                    - (_rsi_simple(closes[:-1]) or 0)),
        "sma50": sma50, "vs50": closes[-1] / sma50 - 1,
        "ema8": ema8[-1],
        "above_8ema": closes[-1] > ema8[-1],
        "below_8ema": closes[-1] < ema8[-1],
        "swing_low": swing_low,
        "near_support": closes[-1] <= swing_low * (1 + sp),
        "hi20": highs[hi_i],
        "hi20_age": len(highs) - 1 - hi_i,
        "close_lt_hi20": closes[-1] < highs[hi_i],
        "new_20d_high": closes[-1] >= max(highs[-hw - 1:-1]),
        "higher_low": min(lows[-5:]) > swing_low,
        "vol_dip": _vol_dip(bars),
        "stop_hi10": max(highs[-10:]), "stop_lo10": min(lows[-10:]),
    }


def _fmt(line: str, ctx: dict) -> str:
    """Render a leg's display line — {rsi}, {vs50_pct} etc. A missing
    key leaves the placeholder visible rather than lying."""
    vals = {k: v for k, v in ctx.items()}
    vals.update({
        "vs50_pct": f"{(ctx.get('vs50') or 0) * 100:+.0f}",
        "vs50_hi7_pct": f"{(ctx.get('vs50_hi7') or 0) * 100:+.0f}",
        "swing_low": f"{ctx.get('swing_low') or 0:.2f}",
        "rsi": (f"{ctx['rsi']:.0f}" if ctx.get("rsi") else "—"),
        "rsi_hi7": (f"{ctx['rsi_hi7']:.0f}"
                    if ctx.get("rsi_hi7") else "—"),
        "rsi_lo7": (f"{ctx['rsi_lo7']:.0f}"
                    if ctx.get("rsi_lo7") else "—"),
        "leaders_ratio_pct": (f"{ctx['leaders_ratio']:.0%}"
                              if ctx.get("leaders_ratio") is not None
                              else "—"),
    })
    try:
        return line.format_map(vals)
    except (KeyError, ValueError):
        return line


def _evaluate_etf(etf: str, espec: dict, ctx: dict) -> dict[str, Any]:
    """Leg roles → state, per the declared contract:
    vetoed = armed ∧ any veto; triggered = armed ∧ all triggers ∧
    easing_min met; armed = all armed legs; else flat."""
    legs, missing = [], set()
    for leg in espec["legs"]:
        ok, log = _eval_when(ctx, leg["when"])
        missing.update(log["missing"])
        legs.append({"id": leg["id"], "role": leg["role"], "ok": ok,
                     "line": _fmt(leg["line"], ctx)})
    by = lambda role: [l for l in legs if l["role"] == role]
    armed = all(l["ok"] for l in by("armed")) and by("armed") != []
    trig = all(l["ok"] for l in by("trigger"))
    easing = [l for l in legs if l["role"] == "easing"]
    easing_ok = (sum(l["ok"] for l in easing)
                 >= espec.get("easing_min", len(easing)))
    vetoed = armed and any(l["ok"] for l in by("veto"))
    triggered = armed and trig and easing_ok and not vetoed
    state = ("vetoed" if vetoed
             else "triggered" if triggered
             else "armed" if armed else "flat")
    # veto legs evaluate 'ok' when the kill-condition FIRES — invert
    # for display so a ✓ always means 'good for the setup'
    checklist = [{"ok": (l["ok"] if l["role"] != "veto" else not l["ok"]),
                  "line": l["line"], "soft": l["role"] == "soft"}
                 for l in legs]
    if easing:
        checklist.insert(3, {"ok": easing_ok, "line":
                             f"selling pressure easing "
                             f"({sum(l['ok'] for l in easing)}/"
                             f"{len(easing)} >= {espec.get('easing_min', len(easing))})"})
    return {"state": state, "armed": armed,
            "veto": espec.get("veto_reason") if vetoed else None,
            "checklist": checklist, "missing": sorted(missing),
            "easing": easing_ok}


def evaluate(funds: Optional[float] = None,
             risk_pct: Optional[float] = None) -> dict[str, Any]:
    """Both setups over today's stored tape; journal one row/etf/day.

    funds    portfolio value for sizing (defaults to portfolio MV)
    risk_pct planned-loss budget — spec declares the default
    """
    from app.database import db
    from app.market_data import bars as bars_mod

    spec = _load()
    etfs = list(spec["etfs"])
    books = bars_mod.load(
        [spec["signal_src"], spec["signal_confirm"], *etfs], days=400)
    idx = books.get(spec["signal_src"])
    idx2 = books.get(spec["signal_confirm"])
    t = _taped(idx, spec)

    out = {"as_of": (idx[-1].date.isoformat() if idx else
                     date.today().isoformat()),
           "signal_src": spec["signal_src"], "funds": funds,
           "risk_pct": risk_pct or spec["risk_pct"], "etfs": {},
           "rules_version": rules_version(),
           "caveat": spec["caveat"]}
    if t is None:
        out["error"] = "no index tape stored"
        return out

    leaders = _leader_tape(spec)
    alerts = _semi_alerts(spec)
    if funds is None:
        funds = _portfolio_mv()
    risk_pct = risk_pct or spec["risk_pct"]

    ctx = {**t, "leaders_ratio": leaders["ratio"],
           "bear_alerts": alerts["count"],
           "support_pct_disp": f"{spec['support_pct'] * 100:.0f}%",
           "support_window": spec["support_window"]}
    leverage, targets = spec["leverage"], spec["targets"]

    for etf in etfs:
        espec = spec["etfs"][etf]
        row = _evaluate_etf(etf, espec, ctx)
        row["leaders"] = leaders
        row["index"] = {"close": round(t["close"], 2),
                        "rsi": round(t["rsi"], 1) if t["rsi"] else None,
                        "vs50": round(t["vs50"], 4),
                        "ema8": round(t["ema8"], 2),
                        "soxx_close": (round(idx2[-1].close, 2)
                                       if idx2 else None)}
        if alerts["count"] and etf == "SOXL":
            row["warn"] = (f"{alerts['count']} high-materiality bearish"
                           " alerts on semis in "
                           f"{spec['catalyst_window_days']}d — support "
                           "can fail on thesis deterioration")
        # index invalidation → ETF stop via the 3x daily-move map;
        # side=high: index rising kills SOXS; side=low: falling kills SOXL
        eb = books.get(etf) or []
        etf_px = float(eb[-1].close) if eb else None
        side, win = espec["stop"]["side"], espec["stop"]["window"]
        idx_stop = t[f"stop_{'hi' if side == 'high' else 'lo'}{win}"]
        idx_move = (idx_stop / t["close"] - 1 if side == "high"
                    else t["close"] / idx_stop - 1)
        etf_stop = (round(etf_px * (1 - idx_move * leverage), 2)
                    if etf_px else None)
        risk_px = (etf_px - etf_stop
                   if etf_px and etf_stop is not None else None)
        t1 = (round(etf_px + targets[0] * risk_px, 2)
              if risk_px and risk_px > 0 else None)
        t2 = (round(etf_px + targets[1] * risk_px, 2)
              if risk_px and risk_px > 0 else None)
        shares = (int(funds * risk_pct / risk_px)
                  if funds and risk_px and risk_px > 0 else None)
        row["levels"] = {"entry": etf_px, "stop": etf_stop,
                         "t1": t1, "t2": t2,
                         "risk_px": (round(risk_px, 2)
                                     if risk_px else None),
                         "shares": shares,
                         "risk_usd": (round(shares * risk_px, 0)
                                      if shares else None),
                         "idx_stop": round(idx_stop, 2),
                         "idx_move": round(idx_move, 4)}
        out["etfs"][etf] = row
        try:
            db.execute_update(
                "INSERT INTO lev_etf_evals (as_of, etf, signal_src,"
                " state, rsi, vs50, ema8_rel, idx_close, etf_px,"
                " stop_px, t1_px, t2_px, risk_pct_px, checklist,"
                " veto, leaders)"
                " VALUES (:d,:e,:src,:st,:rsi,:v50,:e8,:ic,:ep,:sp,"
                " :t1,:t2,:rp,:ck::jsonb,:v,:ld::jsonb)"
                " ON CONFLICT (as_of, etf) DO UPDATE SET"
                " state=EXCLUDED.state, rsi=EXCLUDED.rsi,"
                " vs50=EXCLUDED.vs50, ema8_rel=EXCLUDED.ema8_rel,"
                " idx_close=EXCLUDED.idx_close,"
                " etf_px=EXCLUDED.etf_px, stop_px=EXCLUDED.stop_px,"
                " t1_px=EXCLUDED.t1_px, t2_px=EXCLUDED.t2_px,"
                " risk_pct_px=EXCLUDED.risk_pct_px,"
                " checklist=EXCLUDED.checklist,"
                " veto=EXCLUDED.veto, leaders=EXCLUDED.leaders",
                {"d": out["as_of"], "e": etf,
                 "src": spec["signal_src"], "st": row["state"],
                 "rsi": row["index"]["rsi"],
                 "v50": row["index"]["vs50"],
                 "e8": (t["close"] / t["ema8"] - 1),
                 "ic": row["index"]["close"], "ep": etf_px,
                 "sp": etf_stop, "t1": t1, "t2": t2,
                 "rp": (risk_px / etf_px
                        if risk_px and etf_px else None),
                 "ck": json.dumps({"spec": rules_version(),
                                   "checklist": row["checklist"]}),
                 "v": row["veto"],
                 "ld": json.dumps(leaders)})
        except Exception as exc:
            logger.debug("lev eval journal %s: %s", etf, exc)
    return out
