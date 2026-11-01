"""Macro metals regime — the shared layer.

One classification for the whole metals complex, then per-metal
scores decide whether THIS metal benefits from it. The four states
answer "which economic force dominates":

  precious_bullish    real yields falling + dollar weakening +
                      liquidity not deteriorating → gold/silver bid
  industrial_bullish  growth improving + credit calm → copper bid
  stagflationary      weak growth + elevated/rising inflation +
                      credit stress → gold favored, copper hurt
  deflationary_risk   weak demand + falling inflation + credit
                      tightening → copper warned, gold mixed
  neutral             no alignment — scores revert to fundamentals

Crucially the same fact diverges per metal: rising credit stress
helps gold (haven) while hurting copper (recession fear). That is
the whole point of a metals regime separate from the equity regime.
"""
from __future__ import annotations

from typing import Any, Optional


def _f(v) -> Optional[float]:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def classify(m: dict[str, Any]) -> dict[str, Any]:
    """m keys (None-tolerant): real_yield_level, real_yield_chg20
    (points), dxy_chg20 (%), breakeven_level, breakeven_chg20
    (points), hy_level, hy_chg20 (points), indpro_yoy (%),
    liquidity_score, liquidity_direction, copper_ret60 (%)."""
    ry_c = _f(m.get("real_yield_chg20"))
    ry_l = _f(m.get("real_yield_level"))
    dx = _f(m.get("dxy_chg20"))
    be_c = _f(m.get("breakeven_chg20"))
    hy_c = _f(m.get("hy_chg20"))
    hy_l = _f(m.get("hy_level"))
    indpro = _f(m.get("indpro_yoy"))
    liq_s = _f(m.get("liquidity_score"))
    liq_d = m.get("liquidity_direction")
    cu60 = _f(m.get("copper_ret60"))

    # ---- component reads -------------------------------------------------
    yields_falling = ry_c is not None and ry_c <= -0.10
    yields_rising = ry_c is not None and ry_c >= 0.10
    dollar_weak = dx is not None and dx <= -0.8
    dollar_firm = dx is not None and dx >= 0.8
    liq_ok = (liq_d in ("improving", "neutral")
              or (liq_s is not None and liq_s >= 50))
    growth_weak = ((indpro is not None and indpro <= 0.0)
                   or (cu60 is not None and cu60 <= -5.0))
    growth_ok = ((indpro is not None and indpro > 0.5)
                 or (cu60 is not None and cu60 >= 5.0))
    inflation_firm = be_c is not None and be_c >= 0.05
    inflation_soft = be_c is not None and be_c <= -0.05
    credit_stress = ((hy_c is not None and hy_c >= 0.30)
                     or (hy_l is not None and hy_l >= 5.0))
    credit_calm = ((hy_c is not None and hy_c <= 0.05)
                   or (hy_l is not None and hy_l <= 3.5))

    drivers: list[str] = []
    if yields_falling:
        drivers.append(f"real yields falling ({ry_c:+.2f}pt/20d)")
    elif yields_rising:
        drivers.append(f"real yields rising ({ry_c:+.2f}pt/20d)")
    if dollar_weak:
        drivers.append(f"DXY weakening ({dx:+.1f}%/20d)")
    elif dollar_firm:
        drivers.append(f"DXY firm ({dx:+.1f}%/20d)")
    if credit_stress:
        drivers.append("credit stress rising — haven bid helps gold, "
                       "recession read hurts copper")
    if growth_weak:
        drivers.append("growth/demand weak")
    elif growth_ok:
        drivers.append("industrial demand improving")
    if inflation_firm:
        drivers.append(f"inflation expectations rising ({be_c:+.2f}pt)")
    if liq_d == "improving":
        drivers.append("liquidity expanding")
    elif liq_d == "deteriorating":
        drivers.append("liquidity deteriorating")

    # ---- classification — stress states win over benign ones -------------
    label = "neutral"
    if growth_weak and credit_stress and inflation_soft:
        label = "deflationary_risk"
    elif growth_weak and (inflation_firm or yields_rising) \
            and (credit_stress or dollar_firm):
        label = "stagflationary"
    elif yields_falling and dollar_weak and liq_ok:
        label = "precious_bullish"
    elif growth_ok and (credit_calm or not credit_stress) and liq_ok:
        label = "industrial_bullish"

    # crypto reads the same inputs through a different lens — it is a
    # liquidity asset, not a haven. The best crypto regime is metals'
    # precious_bullish MINUS the credit stress: expansion + soft
    # dollar + calm credit. Stress alone = risk_off regardless of
    # what gold is doing.
    if credit_stress:
        crypto_label = "risk_off"
    elif (yields_falling or liq_d == "improving"
          or (liq_s is not None and liq_s >= 65)) \
            and not dollar_firm:
        crypto_label = "liquidity_sponge"
    else:
        crypto_label = "neutral"

    return {
        "label": label,
        "crypto_label": crypto_label,
        "drivers": drivers[:6],
        "components": {
            "yields": ("falling" if yields_falling else
                       "rising" if yields_rising else "flat"),
            "dollar": ("weak" if dollar_weak else
                       "firm" if dollar_firm else "flat"),
            "growth": ("weak" if growth_weak else
                       "improving" if growth_ok else "mixed"),
            "inflation": ("firm" if inflation_firm else
                          "soft" if inflation_soft else "flat"),
            "credit": ("stress" if credit_stress else
                       "calm" if credit_calm else "neutral"),
            "liquidity": liq_d or ("improving" if liq_s and liq_s >= 60
                                   else "neutral"),
            "real_yield_level": ry_l,
        },
    }
