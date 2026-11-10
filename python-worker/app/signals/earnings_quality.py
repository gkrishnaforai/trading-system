"""Earnings quality — the forensic screen institutions run first.

High verified growth can still be LOW-QUALITY growth. These legs
catch the divergence, all from SEC XBRL (slow, nightly, book-only):

  accruals_gap   (NI − CFO)/assets — earnings running ahead of cash
  recv_vs_rev    receivables growth − revenue growth — channel
                 stuffing signature (receivables outrun sales)
  inv_vs_rev     inventory growth − revenue growth — unsold build
  fcf_conversion CFO/NI — does reported income become cash
  gw_intensity   goodwill/assets — acquisitive-earnings risk
  def_rev_dir    deferred revenue direction (positive = prepaid
                 demand, supports quality)

Honesty contract: a flag is a REVIEW trigger, not a fraud verdict.
Revenue-model context matters (OEM assembly runs thin accrual
ratios by nature) — flags ride the score card, gates stay supreme.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from typing import Any, Optional

logger = logging.getLogger(__name__)

_FRESH_DAYS = 400      # annual facts older than this are stale


def _f(v) -> Optional[float]:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _annual(gaap: dict, tags: tuple[str, ...]) -> list[tuple[str, float]]:
    """(end, val) for annual frames under the first tag that has
    data, newest two years — mirrors the resilience XBRL pattern."""
    best = None
    for tag in tags:
        rows = ((gaap.get(tag) or {}).get("units") or {}).get("USD") or []
        ann: dict[str, float] = {}
        for r in rows:
            if not r.get("start") or not r.get("end"):
                continue
            span = (date.fromisoformat(r["end"])
                    - date.fromisoformat(r["start"])).days
            if span > 300:
                ann[r["end"]] = max(ann.get(r["end"], 0),
                                    float(r["val"]))
        if ann and (best is None or max(ann) > best[0]):
            best = (max(ann), sorted(ann.items()))
    return best[1] if best else []


def _instant(gaap: dict, tags: tuple[str, ...]) -> list[tuple[str, float]]:
    """(end, val) instant facts, newest two."""
    best = None
    for tag in tags:
        rows = ((gaap.get(tag) or {}).get("units") or {}).get("USD") or []
        pts: dict[str, float] = {}
        for r in rows:
            if r.get("end"):
                pts[r["end"]] = float(r["val"])
        if pts and (best is None or max(pts) > best[0]):
            best = (max(pts), sorted(pts.items()))
    return best[1] if best else []


def _last2(series: list[tuple[str, float]]) -> tuple[Optional[float],
                                                   Optional[float],
                                                   Optional[str]]:
    if not series:
        return None, None, None
    cur = series[-1][1]
    prev = series[-2][1] if len(series) >= 2 else None
    return cur, prev, series[-1][0]


def _growth(cur: Optional[float], prev: Optional[float]
            ) -> Optional[float]:
    if cur is None or prev in (None, 0):
        return None
    return (cur - prev) / abs(prev)


def _map(v: Optional[float], lo: float, hi: float
         ) -> Optional[float]:
    if v is None:
        return None
    return max(0.0, min(100.0, (v - lo) / (hi - lo) * 100))


def compute(sym: str) -> dict[str, Any]:
    """0-100 quality score + flags + leg detail for one symbol."""
    from app.providers import sec_edgar
    blob = sec_edgar.company_facts(sym)
    gaap = (blob.get("facts") or {}).get("us-gaap") or {}

    rev, rev_p, rev_end = _last2(_annual(gaap, (
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues", "SalesRevenueNet")))
    ni, _, _ = _last2(_annual(gaap, (
        "NetIncomeLoss", "ProfitLoss")))
    cfo, cfo_p, _ = _last2(_annual(gaap, (
        "NetCashProvidedByUsedInOperatingActivities",)))
    ni_p = (_last2(_annual(gaap, ("NetIncomeLoss", "ProfitLoss")))
            [1])
    capex, _, _ = _last2(_annual(gaap, (
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets")))
    assets, _, _ = _last2(_instant(gaap, ("Assets",)))
    recv, recv_p, _ = _last2(_instant(gaap, (
        "AccountsReceivableNetCurrent", "ReceivablesNetCurrent",
        "AccountsReceivableNet")))
    inv, inv_p, _ = _last2(_instant(gaap, (
        "InventoryNet", "InventoryFinishedGoodsNetOfReserves",
        "InventoryGross")))
    gw, _, _ = _last2(_instant(gaap, ("Goodwill",)))
    drv, drv_p, _ = _last2(_instant(gaap, (
        "ContractWithCustomerLiability",
        "ContractWithCustomerLiabilityCurrent",
        "DeferredRevenueCurrent")))

    if not rev_end or (date.today()
                       - date.fromisoformat(rev_end)).days > _FRESH_DAYS:
        return {"symbol": sym, "quality": None, "flags": ["eq_stale"],
                "note": f"annual facts stale ({rev_end})"}

    rev_g = _growth(rev, rev_p)
    recv_g = _growth(recv, recv_p)
    inv_g = _growth(inv, inv_p)
    drv_g = _growth(drv, drv_p)

    accr = ((ni - cfo) / assets) if (ni is not None and cfo is not None
                                    and assets) else None
    dsr = (recv_g - rev_g) if (recv_g is not None
                              and rev_g is not None) else None
    isr = (inv_g - rev_g) if (inv_g is not None
                             and rev_g is not None) else None
    conv = (cfo / ni) if (ni and ni > 0 and cfo is not None) else None
    # cash-generation TRAJECTORY — the level checks above miss
    # direction: a name recovering cash (neg→improving) deserves
    # credit; a name bleeding (pos→deteriorating) deserves a flag
    cfo_g = _growth(cfo, cfo_p)
    conv_p = (cfo_p / ni_p) if (ni_p and ni_p > 0
                               and cfo_p is not None) else None
    conv_improving = (conv is not None and conv_p is not None
                      and conv > conv_p + 0.05)
    conv_deteriorating = (conv is not None and conv_p is not None
                          and conv < conv_p - 0.05)
    gw_sh = (gw / assets) if (gw is not None and assets) else None

    # legs -> 0-100, higher = cleaner earnings
    legs = {
        "accruals_gap": _map(accr, 0.15, -0.10) if accr is not None
        else None,
        "recv_vs_rev": _map(dsr, 0.40, -0.15) if dsr is not None else None,
        "inv_vs_rev": _map(isr, 0.40, -0.15) if isr is not None else None,
        "fcf_conversion": _map(conv, 0.40, 1.30),
        "gw_intensity": _map(gw_sh, 0.50, 0.10) if gw_sh is not None
        else None,
        "def_rev_dir": _map(drv_g, -0.20, 0.30) if drv_g is not None
        else None,
        "cash_trend": ((_map(cfo_g, -0.30, 0.40) or 0)
                       + (15 if conv_improving else
                          -15 if conv_deteriorating else 0))
                      if cfo_g is not None else None,
    }
    if legs["cash_trend"] is not None:
        legs["cash_trend"] = max(0.0, min(100.0,
                                        legs["cash_trend"]))
    live = [(s, w) for (s, w) in
            [(legs["accruals_gap"], .20), (legs["recv_vs_rev"], .20),
             (legs["inv_vs_rev"], .10), (legs["fcf_conversion"], .15),
             (legs["gw_intensity"], .10), (legs["def_rev_dir"], .10),
             (legs["cash_trend"], .15)]
            if s is not None]
    quality = (round(sum(s * w for s, w in live)
                     / sum(w for _, w in live))
               if live else None)

    flags = []
    if dsr is not None and dsr > 0.25:
        flags.append(f"channel_stuffing_risk:dsr+{dsr:.0%}")
    if isr is not None and isr > 0.25:
        flags.append(f"inventory_build:+{isr:.0%}")
    if accr is not None and accr > 0.10:
        flags.append(f"accruals_heavy:{accr:.0%}")
    if conv is not None and conv < 0.5:
        flags.append(f"fcf_divergence:{conv:.1f}x")
    # 'improving' needs either real CFO growth or conversion rising
    # on flat-or-better CFO — never a negative number labeled up
    if (cfo_g is not None and cfo_g > 0.25) or             (conv_improving and (cfo_g is None or cfo_g >= 0)):
        flags.append(f"cash_gen_improving:{cfo_g:+.0%}"
                     if cfo_g is not None else "cash_gen_improving")
    elif conv_improving and cfo_g is not None and cfo_g < 0:
        flags.append(f"cash_mix_note:cfo{cfo_g:+.0%}_conv_up")
    if conv_deteriorating or (cfo_g is not None and cfo_g < -0.25
                              and (cfo or 0) > 0):
        flags.append(f"cash_gen_deteriorating:{cfo_g:+.0%}"
                     if cfo_g is not None else
                     "cash_gen_deteriorating")
    if gw_sh is not None and gw_sh > 0.40:
        flags.append(f"goodwill_intensity:{gw_sh:.0%}")
    if not live:
        flags.append("eq_unverifiable")

    return {"symbol": sym, "quality": quality, "flags": flags,
            "legs": {k: (round(v) if v is not None else None)
                     for k, v in legs.items()},
            "facts": {"rev_g": rev_g, "recv_g": recv_g, "inv_g": inv_g,
                      "accruals_ta": accr, "cfo_ni": conv,
                      "cfo_g": cfo_g, "conv_prev": conv_p,
                      "gw_assets": gw_sh, "def_rev_g": drv_g,
                      "fy_end": rev_end}}


def ensure_table() -> None:
    from app.database import db
    db.execute_update(
        "CREATE TABLE IF NOT EXISTS symbol_earnings_quality ("
        " symbol TEXT NOT NULL, as_of DATE NOT NULL,"
        " quality INT, flags JSONB, legs JSONB, payload JSONB,"
        " created_at TIMESTAMPTZ NOT NULL DEFAULT now(),"
        " PRIMARY KEY (symbol, as_of))")


def run(symbols: list[str]) -> dict[str, Any]:
    """Nightly forensic pass — EDGAR is slow, that's fine."""
    from app.database import db
    ensure_table()
    n = 0
    errors = []
    for sym in symbols:
        try:
            c = compute(sym)
            db.execute_update(
                "INSERT INTO symbol_earnings_quality"
                " (symbol, as_of, quality, flags, legs, payload)"
                " VALUES (:s,:d,:q,CAST(:f AS jsonb),CAST(:l AS jsonb),"
                " CAST(:p AS jsonb))"
                " ON CONFLICT (symbol,as_of) DO UPDATE SET"
                " quality=EXCLUDED.quality, flags=EXCLUDED.flags,"
                " legs=EXCLUDED.legs, payload=EXCLUDED.payload",
                {"s": sym, "d": date.today(), "q": c.get("quality"),
                 "f": json.dumps(c["flags"]),
                 "l": json.dumps(c["legs"]),
                 "p": json.dumps(c, default=str)})
            n += 1
        except Exception as e:
            errors.append(f"{sym}: {e}")
            if len(errors) >= 20:
                break
    return {"scored": n, "errors": errors[:10]}


def read(sym: str) -> Optional[dict[str, Any]]:
    from app.database import db
    try:
        rows = db.execute_query(
            "SELECT payload FROM symbol_earnings_quality"
            " WHERE symbol=:s ORDER BY as_of DESC LIMIT 1", {"s": sym})
        if not rows:
            return None
        p = rows[0].get("payload")
        return json.loads(p) if isinstance(p, str) else p
    except Exception:
        return None
