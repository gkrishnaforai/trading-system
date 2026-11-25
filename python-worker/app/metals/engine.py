"""Metals Pulse engine — orchestration + journal.

  evaluate()  fetch prices + FRED + liquidity journal → macro regime
              → per-metal fundamentals/fear/verdict. Pure read, no DB
              writes — safe for lazy endpoint eval and tests.
  run()       evaluate() + journal to metals_snapshots (daily job).
  read()      latest journal row for the regime page — fast path.

Price/FRED fetch failures degrade components to missing — the score
renormalizes and reports gaps rather than fabricating. If too many
legs die, the metal reports no_score, never a guess.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import date
from typing import Any, Optional

from app.market_data.indicators import (closes, ema, pct_from_sma,
                                        returns, rsi, sma)
from app.signals.correction_alarms import _delta, _fred_series

from . import macro as _macro
from . import scoring as _sc
from .narratives import STAGE2_PENDING, STRUCTURAL

logger = logging.getLogger(__name__)

# Yahoo futures + proxies. FXI stands in for China-demand expectations
# until a real China-PMI source is wired (stage 2).
SYMBOLS = {
    "gold": "GC=F",
    "silver": "SI=F",
    "copper": "HG=F",
    "dxy": "DX-Y.NYB",
    "china": "FXI",
    "bitcoin": "BTC-USD",
    "ethereum": "ETH-USD",
    "solana": "SOL-USD",
}


def _pct_chg_bars(bars, periods: int) -> Optional[float]:
    r = returns(bars, periods)
    return r * 100 if r is not None else None


def _fred_chg(sid: str, days: int = 220,
              lookback: int = 20) -> tuple[Optional[float],
                                           Optional[float]]:
    """(level, delta over lookback obs) from a FRED series."""
    pts = _fred_series(sid, days=days)
    if not pts:
        return None, None
    return pts[-1][1], _delta(pts, lookback)


def _fetch_bars() -> dict:
    """Sync wrapper over the async market-data service — same shape
    morning.py uses for the regime snapshot."""
    async def _all() -> dict:
        from app.market_data import MarketDataService
        svc = MarketDataService()

        async def one(k: str, sym: str):
            try:
                b = await svc.get_ohlcv(sym, period="1y",
                                        interval="1d",
                                        prefer=["yahoo_finance"])
                return k, b or None
            except Exception as e:                          # noqa: BLE001
                logger.debug("metals fetch %s: %s", sym, e)
                return k, None
        import asyncio as _a
        pairs = await _a.gather(*(one(k, s)
                                  for k, s in SYMBOLS.items()))
        return dict(pairs)
    return asyncio.run(_all())


def _metrics(bars) -> dict[str, Any]:
    """Per-metal price/technical facts from daily bars."""
    if not bars or len(bars) < 60:
        return {}
    px = bars[-1].close
    cs = closes(bars)
    hi52 = float(cs.iloc[-252:].max()) if len(cs) >= 2 else None
    lo52 = float(cs.iloc[-252:].min()) if len(cs) >= 2 else None
    e20 = ema(bars, 20)
    return {
        "price": round(px, 2),
        "off_52w_high_pct":
            round(px / hi52 - 1, 4) if hi52 else None,
        "dist_sma200_pct": pct_from_sma(bars, 200),
        "sma200": sma(bars, 200),
        "ema20": e20,
        "above_ema20": (px > e20) if e20 is not None else None,
        "rsi14": rsi(bars, 14),
        "rsi14_5ago": rsi(bars, 14, offset=5),
        "ret5": _pct_chg_bars(bars, 5),
        "ret20": _pct_chg_bars(bars, 20),
        "ret60": _pct_chg_bars(bars, 60),
        "hi_52w": round(hi52, 2) if hi52 else None,
        "lo_52w": round(lo52, 2) if lo52 else None,
        "as_of": str(getattr(bars[-1], "timestamp", ""))[:10],
    }


def _ratio_pctile(num_bars, den_bars) -> Optional[float]:
    """num/den price-ratio percentile vs its own 1y history — G/S
    elevated = silver cheap vs gold; ETH/BTC low = ether cheap vs
    bitcoin (relative-value legs)."""
    if not num_bars or not den_bars:
        return None
    ac, sc = closes(num_bars), closes(den_bars)
    ratio = (ac / sc).dropna()
    if len(ratio) < 120:
        return None
    cur = float(ratio.iloc[-1])
    hist = ratio.iloc[-252:]
    return round(float((hist < cur).mean()) * 100, 1)


def _macro_inputs(bars: dict) -> dict[str, Any]:
    """Assemble macro legs from FRED + the liquidity journal + DXY
    bars. Every leg None-tolerant."""
    m: dict[str, Any] = {}
    m["real_yield_level"], m["real_yield_chg20"] = \
        _fred_chg("DFII10")
    _, m["breakeven_chg20"] = _fred_chg("T10YIE")
    m["hy_level"], m["hy_chg20"] = _fred_chg("BAMLH0A0HYM2")
    ind = _fred_series("INDPRO", days=760)
    if len(ind) > 22:                        # monthly — YoY needs ~12 obs
        try:
            m["indpro_yoy"] = round(
                (ind[-1][1] / ind[-13][1] - 1) * 100, 2)
        except Exception:                                   # noqa: BLE001
            m["indpro_yoy"] = None
    try:
        from app.signals import liquidity_engine, liquidity_forward
        liq = liquidity_engine.read() or {}
        m["liquidity_score"] = liq.get("liquidity_score")
        m["liquidity_direction"] = liq.get("liquidity_direction")
        # where money is actually going — a defensive/gold-led
        # destination is a direct metals bid signal, not a proxy
        m["flow_destination"] = ((liq.get("flow_matrix") or {})
                                 .get("destination"))
        fwd = liquidity_forward.read() or {}
        m["liq_forward_hint_8w"] = fwd.get("posture_hint")
    except Exception:                                       # noqa: BLE001
        m["liquidity_score"] = m["liquidity_direction"] = \
            m["flow_destination"] = m["liq_forward_hint_8w"] = None
    if bars.get("dxy"):
        m["dxy_chg20"] = _pct_chg_bars(bars["dxy"], 20)
    if bars.get("china"):
        m["fxi_ret60"] = _pct_chg_bars(bars["china"], 60)
    if bars.get("copper"):
        m["copper_ret60"] = _pct_chg_bars(bars["copper"], 60)
    return m


def evaluate() -> dict[str, Any]:
    bars = _fetch_bars()
    m = _macro_inputs(bars)
    reg = _macro.classify(m)

    # relative-value legs — the live ratio percentiles
    m["gs_ratio_pctile"] = _ratio_pctile(bars.get("gold"),
                                         bars.get("silver"))
    m["eth_btc_pctile"] = _ratio_pctile(bars.get("ethereum"),
                                        bars.get("bitcoin"))
    m["sol_btc_pctile"] = _ratio_pctile(bars.get("solana"),
                                        bars.get("bitcoin"))

    out: dict[str, Any] = {"metals": {}, "crypto": {}}
    for asset in _sc.ASSETS:
        cls = _sc.ASSET_CLASS[asset]
        b = bars.get(asset)
        met = _metrics(b)
        mm = {**m, **met}
        f, f_miss, f_legs = _sc.fundamental(asset, mm)
        e, e_miss, e_legs = _sc.fear(met, asset)
        stab, knife = _sc.stabilization(met, asset)
        # each class gets the regime label meant for it — metals see
        # precious/industrial, crypto sees liquidity_sponge/risk_off
        label = (reg["crypto_label"] if cls == "crypto"
                 else reg["label"])
        v = _sc.verdict(asset, f, e, label, stab, knife)
        missing = sorted(set(f_miss + e_miss))
        out[cls][asset] = {
            "class": cls,
            "opportunity": _sc.opportunity(f, e),
            "fundamental": f,
            "fear": e,
            "verdict": v,
            "reason": _sc.verdict_reason(asset, v, f, e, label,
                                         stab, knife),
            "legs": {"fundamental": f_legs, "fear": e_legs},
            "price": met.get("price"),
            "hi_52w": met.get("hi_52w"),
            "lo_52w": met.get("lo_52w"),
            "off_52w_high_pct": met.get("off_52w_high_pct"),
            "rsi14": met.get("rsi14"),
            "ret20": met.get("ret20"),
            "ret60": met.get("ret60"),
            "falling_knife": knife,
            "stabilized": stab,
            "thesis": STRUCTURAL[asset]["thesis"],
            "recovery_drivers": STRUCTURAL[asset]["recovery_drivers"],
            "invalidates_when": STRUCTURAL[asset]["invalidates_when"],
            "missing": missing,
            "stage2_pending": STAGE2_PENDING[cls],
            "price_as_of": met.get("as_of"),
        }
    return {"as_of": str(date.today()), "macro": reg,
            "macro_inputs": {k: v for k, v in m.items()
                             if not k.endswith("_pctile")},
            "gs_ratio_pctile": m.get("gs_ratio_pctile"),
            **out}


def _prev_payload() -> Optional[dict[str, Any]]:
    """Previous journaled row for transition diffing."""
    from app.database import db
    try:
        rows = db.execute_query(
            "SELECT as_of, payload FROM metals_snapshots"
            " WHERE as_of < :d ORDER BY as_of DESC LIMIT 1",
            {"d": date.today()})
        if not rows:
            return None
        p = rows[0].get("payload")
        if isinstance(p, str):
            p = json.loads(p)
        p = p or {}
        p["as_of"] = str(rows[0]["as_of"])
        return p
    except Exception:                                       # noqa: BLE001
        return None


def run() -> dict[str, Any]:
    """Compute + journal a metals_snapshots row. Daily cadence —
    FRED series lag a day anyway; futures prices refresh nightly.
    Diffs against the prior journal row so the payload carries
    'what just turned', not only 'what is'."""
    from app.database import db
    prev = _prev_payload()
    st = evaluate()
    st["transitions"] = _sc.transitions(prev, st)
    try:
        db.execute_update(
            "INSERT INTO metals_snapshots (as_of, macro_regime,"
            " payload) VALUES (:d,:r, CAST(:p AS jsonb))"
            " ON CONFLICT (as_of) DO UPDATE SET"
            " macro_regime=EXCLUDED.macro_regime,"
            " payload=EXCLUDED.payload",
            {"d": date.today(), "r": st["macro"]["label"],
             "p": json.dumps(st, default=str)})
    except Exception as exc:
        logger.warning("metals journal: %s", exc)
        st["journal_error"] = str(exc)[:120]
    return st


def read() -> Optional[dict[str, Any]]:
    """Latest journaled state — the regime page's fast read."""
    from app.database import db
    try:
        rows = db.execute_query(
            "SELECT as_of, payload FROM metals_snapshots"
            " ORDER BY as_of DESC LIMIT 1")
        if not rows:
            return None
        p = rows[0].get("payload")
        if isinstance(p, str):
            p = json.loads(p)
        p = p or {}
        d = rows[0]["as_of"]
        p["as_of"] = str(d)
        if isinstance(d, str):
            d = date.fromisoformat(d[:10])
        p["age_days"] = (date.today() - d).days
        return p
    except Exception:                                       # noqa: BLE001
        return None
