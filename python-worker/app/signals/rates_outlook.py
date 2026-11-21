"""Rates outlook — the inflation-trajectory x Fed-pricing forward read.

Two journaled sources, composed on read:

  nowflation_daily — the day-to-day inflation tape: realtime gauge
  yoy, week-over-week direction, the official CPI it lags against,
  and the forecast for the next print. The official-vs-realtime
  gap is the pipeline read: prints converge toward the gauge.

  fed_predictions — what the front end prices for the next FOMC
  and 3-6 months out (hike/hold/cut probabilities, expected bps).

The verdict is the interaction: cooling inflation against priced
hikes is a divergence — the hike pricing is vulnerable to
unwinding, which becomes a tailwind if the data holds. Reheating
inflation with priced cuts is the same divergence pointing the
other way. Direction and pricing together are the forward
information; either alone is half a story.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from app.signals import fed_path, nowflation

_WOW_COOL = -0.05     # pp/week moves below this = cooling trend
_WOW_HEAT = 0.05      # above = reheating
_GAP_PIPE = 0.3       # realtime-vs-official gap implying pipeline direction


def _direction(rt: Optional[float], wow: Optional[float],
               gap: Optional[float]) -> str:
    """Where inflation is headed — wow trend first, confirmed by the
    realtime-vs-official gap (the pipeline pull)."""
    votes = 0
    if wow is not None:
        votes += -1 if wow < _WOW_COOL else 1 if wow > _WOW_HEAT else 0
    if gap is not None:
        # gauge below official → prints should keep rolling down
        votes += -1 if gap < -_GAP_PIPE else 1 if gap > _GAP_PIPE else 0
    if votes < 0:
        return "cooling"
    if votes > 0:
        return "reheating"
    return "flat"


def compose() -> Optional[Dict[str, Any]]:
    nf = nowflation.latest() or {}
    fed = fed_path.read() or {}
    if not nf and not fed:
        return None

    rt = nf.get("realtime_yoy_pct")
    wow = nf.get("realtime_wow_pp")
    off = nf.get("official_cpi_yoy_pct")
    gap = nf.get("gauge_gap_pp")
    pfc = nf.get("print_forecast_yoy")
    off_m = nf.get("official_cpi_month")
    fomc = fed.get("next_fomc") or {}
    p36 = fed.get("path_3_6m") or {}
    lean = p36.get("lean")
    exp_bps = p36.get("expected_bps")

    direction = _direction(
        float(rt) if rt is not None else None,
        float(wow) if wow is not None else None,
        float(gap) if gap is not None else None)
    tight = lean in ("tightening_bias", "tightening_priced") \
        or (lean == "hike")
    easy = lean in ("easing_bias", "easing_priced") or (lean == "cut")

    # direction x pricing — the forward read
    if direction == "cooling":
        if tight:
            tone = "ok"
            headline = ("Inflation cooling but hikes are priced — "
                        "the tightening is vulnerable to unwinding "
                        "if the data holds")
        else:
            tone = "ok"
            headline = ("Inflation cooling — supports rate relief "
                        "ahead")
    elif direction == "reheating":
        if tight:
            tone = "bad"
            headline = ("Inflation reheating and tightening is "
                        "priced — the headwind is real")
        else:
            tone = "warn"
            headline = ("Inflation reheating while markets price "
                        "relief — dovish pricing exposed to a "
                        "hawkish repricing")
    else:
        tone = "warn"
        headline = ("Inflation steady — Fed likely stays on hold; "
                    "watch the next prints")

    return {
        "rates_direction": direction,
        "rates_tone": tone,
        "rates_headline": headline,
        "rates_detail": (
            f"realtime {rt}% ({(wow or 0):+}pp/wk) vs official {off}%"
            f" → {direction}; fed {str(lean or '—').replace('_', ' ')}"
            f" {exp_bps:+}bp"),
        "nf_as_of": str(nf.get("as_of")) if nf.get("as_of") else None,
        "realtime_yoy": float(rt) if rt is not None else None,
        "realtime_wow_pp": float(wow) if wow is not None else None,
        "official_yoy": float(off) if off is not None else None,
        "official_month": off_m,
        "print_forecast_yoy": float(pfc) if pfc is not None else None,
        "fed_lean": lean,
        "fed_expected_bps": exp_bps,
        "fomc_date": fomc.get("date"),
        "fomc_days": fomc.get("days_away"),
        "p_hike": fomc.get("p_hike"),
        "p_hold": fomc.get("p_hold"),
        "p_cut": fomc.get("p_cut"),
    }
