"""3x semiconductor ETF swing detector — SOXS / SOXL.

YAML-driven (leveraged_swings.yaml): the policy — thresholds, leg
roles, veto, stop anchor, targets, risk budget — is declarative and
evaluated through pulse_engine._eval_when, the same condition
semantics as the pulse and best-picks engines. This module owns only
the MECHANICS: tape-feature ctx construction, the flat→armed→
triggered→vetoed state derivation, the index→ETF stop translation
(conservative linear map — idx_move × leverage × stop_buffer), the
geometry-invalid rejection when the implied stop is unpriceable, the
persisting-state dedupe flag, and the daily journal. Output is
advisory — hypotheses to grade, never orders.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime
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
    """Bulk momentum_state read for the semis leadership list. When
    coverage is thinner than min_leader_coverage the ratio is None —
    an unreadable leadership tape is missing evidence, not health."""
    from app.database import db
    rows = db.execute_query(
        "SELECT symbol, momentum_state FROM stocks"
        " WHERE symbol = ANY(:s)", {"s": list(spec["leaders"])})
    tape = {r["symbol"]: r["momentum_state"] for r in rows}
    coverage = (len(tape) / len(spec["leaders"])
                if spec["leaders"] else 0)
    constr = {s for s, st in tape.items()
              if st in set(spec["constructive_states"])}
    hostile = {s for s, st in tape.items()
               if st in set(spec["hostile_states"])}
    return {"tracked": len(tape), "coverage": round(coverage, 2),
            "constructive": sorted(constr), "hostile": sorted(hostile),
            "ratio": (round(len(constr) / len(tape), 2)
                      if tape
                      and coverage >= spec["min_leader_coverage"]
                      else None)}


def _semi_alerts(spec: dict) -> Optional[dict[str, Any]]:
    """Recent HIGH-materiality NEGATIVE alerts on semis. A failed
    query returns None — ctx bear_alerts goes missing and every leg
    that reads it fails closed; a broken feed must not look like
    'no catalysts'."""
    from app.database import db
    try:
        days = spec["catalyst_window_days"]
        syms = list(spec["leaders"]) + list(spec["catalyst_symbols_extra"])
        rows = db.execute_query(
            "SELECT symbol, title, created_at FROM alert_items"
            " WHERE direction = 'NEGATIVE' AND materiality = 'HIGH'"
            " AND symbol = ANY(:s)"
            " AND created_at >= now() - interval :days"
            " ORDER BY created_at DESC LIMIT 10",
            {"s": syms, "days": f"{days} days"})
        return {"count": len(rows),
                "items": [{"symbol": r["symbol"],
                           "title": (r["title"] or "")[:80]}
                          for r in rows]}
    except Exception as exc:
        logger.debug("semi alerts read: %s", exc)
        return None


def _leaders_earning(spec: dict) -> dict[str, Any]:
    """Leadership earnings inside the gap-risk window — a note, not
    a gate. Derived from next_earnings_date, same as best_picks."""
    from app.database import db
    try:
        w = spec["earnings_window_days"]
        rows = db.execute_query(
            "SELECT symbol, next_earnings_date ne FROM stocks"
            " WHERE symbol = ANY(:s)"
            " AND next_earnings_date IS NOT NULL"
            " AND next_earnings_date >= CURRENT_DATE"
            " AND next_earnings_date <= CURRENT_DATE + :w",
            {"s": list(spec["leaders"]), "w": w})
        return {"count": len(rows),
                "symbols": [r["symbol"] for r in rows]}
    except Exception as exc:
        logger.debug("leaders earning read: %s", exc)
        return {"count": 0, "symbols": []}


def _portfolio_mv() -> Optional[float]:
    """Current portfolio market value for default sizing."""
    from app.database import db
    r = db.execute_query(
        "SELECT COALESCE(SUM(COALESCE(current_value,"
        " quantity * avg_price)), 0) mv"
        " FROM portfolio_positions")[0]
    mv = float(r["mv"] or 0)
    return mv if mv > 0 else None


_fresh_at: Optional[datetime] = None


def _ensure_fresh(books: dict, spec: dict) -> dict:
    """Technical freshness contract: 'if it already ran, we are fine
    — otherwise we run.' Bounded at one batched fetch per hour.

    - signal tape already carries today's bar → fresh, no fetch
    - weekend (latest bar ≤3d) → the last session's close IS the
      freshest possible tape
    - fetched within the last hour → no re-fetch (bounds provider
      calls while still picking up the closing bar an hour later)
    - otherwise → one bars.refresh over the signal set (4 symbols,
      batched — the sanctioned writer path) + reload"""
    global _fresh_at
    now = datetime.now()
    today = now.date()
    idx = books.get(spec["signal_src"]) or []
    latest = idx[-1].date if idx else None
    if latest and latest >= today:
        return books
    if today.weekday() >= 5 and latest \
            and (today - latest).days <= 3:
        return books
    if _fresh_at and (now - _fresh_at).total_seconds() < 3600:
        return books
    try:
        from app.market_data import bars as bars_mod
        syms = [spec["signal_src"], spec["signal_confirm"],
                *spec["etfs"]]
        bars_mod.refresh(syms, period="1y")
        books = bars_mod.load(syms, days=400)
    except Exception as exc:
        logger.debug("lev freshness top-up: %s", exc)
    _fresh_at = now
    return books


def _prev_state(etf: str, as_of: str) -> Optional[str]:
    """The prior journal day's verdict — dedupe contract: a setup
    that persisted overnight is 'persisting', not a fresh signal."""
    from app.database import db
    try:
        r = db.execute_query(
            "SELECT state FROM lev_etf_evals WHERE etf = :e"
            " AND as_of < :d ORDER BY as_of DESC LIMIT 1",
            {"e": etf, "d": as_of})
        return r[0]["state"] if r else None
    except Exception:
        return None


def _vol_dip(bars) -> Optional[float]:
    """Selling-pressure ratio: avg volume on down-close bars in the
    last 5 sessions vs the down-day average over the prior 15. <1 =
    the sellers who did the damage are drying up. Needs down bars in
    both windows; absent or missing volume → None → leg fails closed.
    """
    recent = [b.volume for b in bars[-5:] if b.close < b.open]
    prior = [b.volume for b in bars[-20:-5] if b.close < b.open]
    if not recent or not prior:
        return None
    pa = sum(prior) / len(prior)
    if not pa:
        return None
    return (sum(recent) / len(recent)) / pa


def _taped(bars, spec: dict) -> Optional[dict[str, Any]]:
    """Index-tape features — the ctx every YAML leg binds against.

    RSI/stretch extremes are `extreme_window`-bar RECENT peaks, not
    same-bar values: 'RSI reaches 75-80, then closes below the 8EMA'
    is a sequence; by the trigger bar the current RSI has moved off
    the extreme. The swing low excludes the last 5 bars — support is
    a PRIOR confirmed swing, not the bar doing the testing."""
    if not bars or len(bars) < spec["min_bars"]:
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
        "pct_off_hi20": closes[-1] / highs[hi_i] - 1,
        "close_lt_hi20": closes[-1] < highs[hi_i],
        "new_20d_high": closes[-1] >= max(highs[-hw - 1:-1]),
        "higher_low": min(lows[-5:]) > swing_low,
        "vol_dip": _vol_dip(bars),
        "stop_hi10": max(highs[-10:]), "stop_lo10": min(lows[-10:]),
    }


def _mini_taped(bars) -> dict[str, Any]:
    """Lightweight ctx for the corroboration proxy (SOXX) — just the
    8EMA position legs the spec reads."""
    if not bars or len(bars) < 20:
        return {"soxx_above_8ema": None, "soxx_below_8ema": None,
                "soxx_close": None}
    closes = [b.close for b in bars]
    e = _ema(closes, 8)
    return {"soxx_above_8ema": closes[-1] > e[-1],
            "soxx_below_8ema": closes[-1] < e[-1],
            "soxx_close": closes[-1]}


def _fmt(line: str, ctx: dict) -> str:
    """Render a leg's display line — {rsi}, {vs50_pct} etc. A missing
    key leaves the placeholder visible rather than lying."""
    vals = dict(ctx)
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
                              else "tape thin"),
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
    armed = bool(by("armed")) and all(l["ok"] for l in by("armed"))
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
        n = sum(l["ok"] for l in easing)
        checklist.insert(3, {"ok": easing_ok, "line":
                             f"selling pressure easing "
                             f"({n}/{len(easing)} >= "
                             f"{espec.get('easing_min', len(easing))})"})
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
    books = _ensure_fresh(books, spec)     # today's tape or bust
    idx = books.get(spec["signal_src"])
    idx2 = books.get(spec["signal_confirm"])

    out = {"as_of": (idx[-1].date.isoformat() if idx else
                     date.today().isoformat()),
           "signal_src": spec["signal_src"], "funds": funds,
           "risk_pct": risk_pct or spec["risk_pct"], "etfs": {},
           "rules_version": rules_version(),
           "exit": {"max_hold_bars": spec["max_hold_bars"],
                    "time_stop": spec["time_stop"],
                    "targets": spec["targets"]},
           "caveat": spec["caveat"]}
    t = _taped(idx, spec)
    if t is None:
        out["error"] = ("no index tape stored" if not idx else
                        f"insufficient history "
                        f"({len(idx)} < {spec['min_bars']} bars)")
        return out
    # stale tape → no actionable signal, period
    tape_age = (date.today() - idx[-1].date).days
    if tape_age > spec["max_stale_days"]:
        out["error"] = (f"index tape stale — last bar "
                        f"{idx[-1].date} ({tape_age}d old)")
        return out

    leaders = _leader_tape(spec)
    alerts = _semi_alerts(spec)          # None when the feed broke
    earning = _leaders_earning(spec)
    soxx = _mini_taped(idx2)
    if funds is None:
        funds = _portfolio_mv()
    risk_pct = risk_pct or spec["risk_pct"]

    ctx = {**t, **soxx,
           "leaders_ratio": leaders["ratio"],
           "bear_alerts": (alerts["count"] if alerts is not None
                           else None),
           "catalyst_veto_at": spec["catalyst_veto_at"],
           "support_pct_disp": f"{spec['support_pct'] * 100:.0f}%",
           "support_window": spec["support_window"]}
    leverage = spec["leverage"]
    buffer = spec["stop_buffer"]

    for etf in etfs:
        espec = spec["etfs"][etf]
        row = _evaluate_etf(etf, espec, ctx)
        row["leaders"] = leaders
        row["index"] = {"close": round(t["close"], 2),
                        "rsi": round(t["rsi"], 1) if t["rsi"] else None,
                        "vs50": round(t["vs50"], 4),
                        "ema8": round(t["ema8"], 2),
                        "soxx_close": (round(soxx["soxx_close"], 2)
                                       if soxx["soxx_close"] else None)}
        # the persisting flag — dedupe contract for consumers
        prev = _prev_state(etf, out["as_of"])
        row["persisting"] = bool(prev and prev == row["state"]
                                 and row["state"] != "flat")
        warns = []
        if alerts is None:
            warns.append("catalyst feed unreadable — "
                         "catalyst legs are missing, not clean")
        elif alerts["count"] and etf == "SOXL":
            warns.append(f"{alerts['count']} high-materiality bearish "
                         "alerts on semis in "
                         f"{spec['catalyst_window_days']}d — support "
                         "can fail on thesis deterioration")
        if earning["count"]:
            warns.append(f"{earning['count']} semis leaders report "
                         f"≤{spec['earnings_window_days']}d "
                         f"({', '.join(earning['symbols'])}) — "
                         "overnight-gap risk")
        row["warn"] = " · ".join(warns) or None

        # index invalidation → ETF stop via the stressed 3x map.
        # idx_move is the ADVERSE move magnitude, computed per side —
        # SOXS dies on an index RISE (stop_hi/close - 1), SOXL on an
        # index DROP (close/stop_lo - 1); always a positive fraction
        # or the geometry is invalid.
        eb = books.get(etf) or []
        etf_px = float(eb[-1].close) if eb else None
        side, win = espec["stop"]["side"], espec["stop"]["window"]
        idx_stop = t[f"stop_{'hi' if side == 'high' else 'lo'}{win}"]
        idx_move = (idx_stop / t["close"] - 1 if side == "high"
                    else t["close"] / idx_stop - 1)
        implied_loss = idx_move * leverage * buffer
        geo_ok = (idx_move > 0
                  and implied_loss <= spec["max_etf_stop_pct"]
                  and etf_px is not None)
        if not geo_ok:
            row["levels"] = {"geometry_invalid": True,
                             "idx_move": round(idx_move, 4),
                             "implied_loss_pct":
                                 round(implied_loss, 4)}
            geo_note = ("no ETF price stored"
                        if etf_px is None else
                        "unpriceable stop — implied ETF loss "
                        f"{implied_loss:.0%} exceeds "
                        f"{spec['max_etf_stop_pct']:.0%} cap"
                        if implied_loss > spec["max_etf_stop_pct"]
                        else "invalid index stop geometry")
        else:
            etf_stop = round(etf_px * (1 - implied_loss), 2)
            risk_px = etf_px - etf_stop
            t1 = round(etf_px + spec["targets"][0]["r"] * risk_px, 2)
            t2 = round(etf_px + spec["targets"][1]["r"] * risk_px, 2)
            # risk-based size AND the notional cap — a tight stop
            # must not inflate the position past max_notional_pct
            risk_sh = (int(funds * risk_pct / risk_px)
                       if funds and risk_px > 0 else None)
            cap_sh = (int(funds * spec["max_notional_pct"] / etf_px)
                      if funds and etf_px else None)
            shares = (min(risk_sh, cap_sh)
                      if risk_sh is not None and cap_sh is not None
                      else risk_sh or cap_sh)
            capped = (shares is not None and cap_sh is not None
                      and shares == cap_sh and risk_sh is not None
                      and risk_sh > cap_sh)
            geo_note = (f"size notional-capped at "
                        f"{spec['max_notional_pct']:.0%} of portfolio"
                        if capped else None)
            row["levels"] = {"entry": etf_px, "stop": etf_stop,
                             "t1": t1, "t2": t2,
                             "t1_frac": spec["targets"][0]["close"],
                             "t2_frac": spec["targets"][1]["close"],
                             "risk_px": round(risk_px, 2),
                             "shares": shares,
                             "notional_capped": capped,
                             "risk_usd": (round(shares * risk_px, 0)
                                          if shares else None),
                             "idx_stop": round(idx_stop, 2),
                             "idx_move": round(idx_move, 4),
                             "implied_loss_pct":
                                 round(implied_loss, 4)}

        # actionable contract: triggered + required ctx present +
        # priceable geometry. A trigger with a data gap or an
        # unpriceable stop is a journaled hypothesis, nothing more.
        data_missing = [f for f in espec.get("required_ctx", [])
                        if ctx.get(f) is None]
        row["actionable"] = bool(row["state"] == "triggered"
                                 and geo_ok and not data_missing)
        if data_missing:
            row["data_missing"] = data_missing
        notes = [n for n in (geo_note, ) if n]
        if data_missing:
            notes.append(f"required data missing: "
                         f"{', '.join(data_missing)}")
        if not geo_ok:
            row["levels"]["geometry_invalid"] = True
        row["state_note"] = " · ".join(notes) or row.get("state_note")
        out["etfs"][etf] = row
        try:
            lv = row["levels"]
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
                 "ic": row["index"]["close"],
                 "ep": lv.get("entry"), "sp": lv.get("stop"),
                 "t1": lv.get("t1"), "t2": lv.get("t2"),
                 "rp": lv.get("implied_loss_pct"),
                 "ck": json.dumps({"spec": rules_version(),
                                   "persisting": row["persisting"],
                                   "missing": row["missing"],
                                   "checklist": row["checklist"]}),
                 "v": row["veto"],
                 "ld": json.dumps(leaders)})
        except Exception as exc:
            logger.debug("lev eval journal %s: %s", etf, exc)
    return out
