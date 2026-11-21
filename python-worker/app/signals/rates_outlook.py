"""Rates outlook — the inflation-trajectory x Fed-pricing forward read.

The chain, instrumented end to end:

  drivers (fuel/shelter/… per-component nowcasts)  →
  headline trajectory (247d daily series + sparkline)  →
  official prints (lagging; converge toward the gauge)  →
  Fed pricing (FOMC odds, 3-6m lean, weekly repricing)

All inputs are journaled — nowflation_daily.raw carries the full
realtime.json (history, components, gap_line); fed_predictions
carries each day's priced path. Composing on read needs no schema.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from app.database import db
from app.signals import fed_path, nowflation

_WOW_COOL = -0.05
_WOW_HEAT = 0.05
_GAP_PIPE = 0.3
_SPARK = "▁▂▃▄▅▆▇"


def _sparkline(vals: List[float]) -> Optional[str]:
    """Unicode sparkline of the daily nowcast — the "is it gradually
    rising or falling" answer at a glance."""
    if len(vals) < 7:
        return None
    lo, hi = min(vals), max(vals)
    if hi - lo < 1e-9:
        return _SPARK[3] * len(vals)
    return "".join(
        _SPARK[min(len(_SPARK) - 1,
                   int((v - lo) / (hi - lo) * (len(_SPARK) - 1)))]
        for v in vals)


def _series(rt_raw: Dict[str, Any]) -> List[Tuple[date, float]]:
    """(date, realtime_yoy) daily series from the journaled payload's
    history array — live tail preferred, reconstructed fills."""
    out: List[Tuple[date, float]] = []
    for h in (rt_raw.get("history") or []):
        try:
            out.append((date.fromisoformat(h["date"]),
                        float(h["realtime"])))
        except Exception:
            continue
    out.sort()
    return out


def _delta_to(series: List[Tuple[date, float]],
              days: int) -> Optional[float]:
    """Latest minus the observation nearest `days` ago, in pp."""
    if len(series) < 2:
        return None
    cur_d, cur_v = series[-1]
    target = cur_d - timedelta(days=days)
    prev = min(series, key=lambda s: abs((s[0] - target).days))
    if prev[0] >= cur_d:
        return None
    return round(cur_v - prev[1], 2)


def _drivers(comps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Per-component contribution = weight x yoy — the 'what is
    pushing inflation' read. Fuel is the oil pass-through leg."""
    out = []
    for c in comps:
        try:
            w, y = float(c["weight_pct"]), float(c["realtime_yoy_pct"])
        except Exception:
            continue
        label = (c.get("label") or c.get("component") or "").split(
            ":")[-1].strip() or c.get("component")
        out.append({
            "key": c.get("component"),
            "label": label,
            "yoy": round(y, 2),
            "contribution": round(w * y / 100, 3),
            "state": "hot" if y >= 4 else "warm" if y >= 2 else "cool",
            "status": c.get("status"),
        })
    out.sort(key=lambda d: -d["contribution"])
    return out[:5]


def _fed_repricing() -> Dict[str, Optional[float]]:
    """Is the market repricing? p_hike + 3-6m expected bps vs the
    journal row ~7d ago — the single most actionable forward delta."""
    try:
        rows = db.execute_query(
            "SELECT as_of, payload FROM fed_predictions"
            " ORDER BY as_of DESC LIMIT 12")
    except Exception:
        return {}
    if len(rows) < 2:
        return {}
    cur = rows[0]
    cur_asof = cur["as_of"]
    cur_asof = (date.fromisoformat(cur_asof)
                if isinstance(cur_asof, str) else cur_asof)
    target = cur_asof - timedelta(days=7)
    prev = min(rows[1:],
               key=lambda r: abs((r["as_of"] if not isinstance(
                   r["as_of"], str) else date.fromisoformat(
                   r["as_of"])) - target))
    prev_asof = prev["as_of"]
    if isinstance(prev_asof, str):
        prev_asof = date.fromisoformat(prev_asof)

    import json as _j

    def _un(p):
        return p if isinstance(p, dict) else _j.loads(p or "{}")

    cp, pp = _un(cur.get("payload")), _un(prev.get("payload"))
    out: Dict[str, Optional[float]] = {}
    ch, ph = (cp.get("next_fomc") or {}).get("p_hike"), \
        (pp.get("next_fomc") or {}).get("p_hike")
    cb, pb = (cp.get("path_3_6m") or {}).get("expected_bps"), \
        (pp.get("path_3_6m") or {}).get("expected_bps")
    if ch is not None and ph is not None:
        out["p_hike_d7"] = round(float(ch) - float(ph))
    if cb is not None and pb is not None:
        out["bps_d7"] = round(float(cb) - float(pb))
    out["compare_to"] = str(prev_asof)
    return out


def _direction(rt: Optional[float], wow: Optional[float],
               gap: Optional[float]) -> str:
    votes = 0
    if wow is not None:
        votes += -1 if wow < _WOW_COOL else 1 if wow > _WOW_HEAT else 0
    if gap is not None:
        votes += -1 if gap < -_GAP_PIPE else 1 if gap > _GAP_PIPE else 0
    if votes < 0:
        return "cooling"
    if votes > 0:
        return "reheating"
    return "flat"


def compose(wti: Optional[Dict[str, Any]] = None
            ) -> Optional[Dict[str, Any]]:
    nf = nowflation.latest() or {}
    fed = fed_path.read() or {}
    if not nf and not fed:
        return None

    rt_raw = (nf.get("raw") or {}).get("realtime") or {}
    if isinstance(rt_raw, str):
        import json as _j
        rt_raw = _j.loads(rt_raw)
    series = _series(rt_raw)
    tail = [v for _, v in series[-28:]]
    drivers = _drivers(rt_raw.get("components") or [])
    reprice = _fed_repricing()

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
    tight = lean in ("tightening_bias", "tightening_priced", "hike")
    easy = lean in ("easing_bias", "easing_priced", "cut")
    # is the market already repricing the divergence?
    unwinding = ((reprice.get("bps_d7") or 0) < -5
                 or (reprice.get("p_hike_d7") or 0) < -10)
    firming = ((reprice.get("bps_d7") or 0) > 5
               or (reprice.get("p_hike_d7") or 0) > 10)

    if direction == "cooling":
        if tight and unwinding:
            tone = "ok"
            headline = ("Disinflation confirmed — hike pricing is "
                        "already unwinding; the tailwind is building")
        elif tight:
            tone = "ok"
            headline = ("Inflation cooling but hikes are priced — "
                        "the tightening is vulnerable to unwinding "
                        "if the data holds")
        else:
            tone = "ok"
            headline = "Inflation cooling — supports rate relief ahead"
    elif direction == "reheating":
        if tight:
            tone = "bad"
            headline = ("Inflation reheating and tightening is "
                        "priced — the headwind is real"
                        + (" and firming" if firming else ""))
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
        "rt_d7_pp": _delta_to(series, 7),
        "rt_d30_pp": _delta_to(series, 30),
        "spark": _sparkline(tail),
        "drivers": drivers,
        "official_yoy": float(off) if off is not None else None,
        "official_month": off_m,
        "print_forecast_yoy": float(pfc) if pfc is not None else None,
        "wti_value": (wti or {}).get("value"),
        "wti_chg5d": (wti or {}).get("chg5d"),
        "fed_lean": lean,
        "fed_expected_bps": exp_bps,
        "fomc_date": fomc.get("date"),
        "fomc_days": fomc.get("days_away"),
        "p_hike": fomc.get("p_hike"),
        "p_hold": fomc.get("p_hold"),
        "p_cut": fomc.get("p_cut"),
        **reprice,
    }
