from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from app.db_storage.repositories import get_database_service
from app.services.fred_client import FredClient


DEFAULT_SERIES: Dict[str, List[str]] = {
    "growth": ["INDPRO", "RSAFS"],
    "labor": ["UNRATE", "ICSA"],
    "inflation": ["CPIAUCSL"],
    "rates": ["DFF", "DGS2", "DGS10"],
    "credit": ["BAMLH0A0HYM2"],
    "liquidity": ["M2SL"],
    "housing": ["HOUST", "PERMIT"],
    "manufacturing": ["INDPRO", "TCU"],
}


def _clip(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _is_month_end(d: date) -> bool:
    return (d + timedelta(days=1)).month != d.month


def _latest_value(points: List[Dict[str, Any]]) -> Optional[float]:
    for p in reversed(points):
        v = p.get("value")
        if v is None:
            continue
        try:
            return float(v)
        except Exception:
            continue
    return None


def _pct_change(curr: Optional[float], prev: Optional[float]) -> Optional[float]:
    if curr is None or prev is None:
        return None
    if prev == 0:
        return None
    return (curr / prev - 1.0) * 100.0


def _score_from_z(z: Optional[float], invert: bool = False) -> Optional[float]:
    if z is None:
        return None
    # Simple sigmoid-like mapping around 0.
    s = 50.0 + (z * 15.0)
    if invert:
        s = 100.0 - s
    return _clip(s, 0.0, 100.0)


def _zscore(values: List[float]) -> Optional[float]:
    if len(values) < 10:
        return None
    mean = sum(values) / float(len(values))
    var = sum((x - mean) ** 2 for x in values) / float(len(values))
    if var <= 0:
        return None
    std = var ** 0.5
    if std == 0:
        return None
    return (values[-1] - mean) / std


@dataclass
class MacroRunResult:
    ok: bool
    as_of_date: date
    updated_series: List[str]
    snapshot_written: bool
    message: str


class MacroOrchestrator:
    def __init__(self, fred_client: Optional[FredClient] = None):
        self.fred = fred_client or FredClient()
        self.db = get_database_service()

    def run_daily(self, as_of_date: Optional[date] = None, lookback_days: int = 3650) -> MacroRunResult:
        d = as_of_date or datetime.utcnow().date()

        updated_series: List[str] = []
        inputs_used: Dict[str, Any] = {"series": {}, "as_of_date": d.isoformat()}

        for module, series_list in DEFAULT_SERIES.items():
            for sid in series_list:
                latest = self.db.macro.get_latest_observation_date(sid)
                start = latest or (d - timedelta(days=lookback_days))

                obs = self.fred.get_observations(series_id=sid, observation_start=start)
                points: List[Dict[str, Any]] = []
                for o in obs:
                    ds = o.get("date")
                    if not ds:
                        continue
                    try:
                        od = datetime.fromisoformat(ds).date()
                    except Exception:
                        continue
                    points.append(
                        {
                            "observation_date": od,
                            "value": o.get("value"),
                            "source": "fred",
                            "retrieved_at": datetime.utcnow(),
                        }
                    )

                if not points:
                    continue

                # store all points (upsert)
                self.db.macro.upsert_series_points(series_id=sid, points=points)

                new_latest = self.db.macro.get_latest_observation_date(sid)
                if latest is None or (new_latest is not None and new_latest > latest):
                    updated_series.append(sid)

                inputs_used["series"][sid] = {
                    "latest_observation_date": new_latest.isoformat() if new_latest else None,
                }

        if not updated_series:
            return MacroRunResult(
                ok=True,
                as_of_date=d,
                updated_series=[],
                snapshot_written=False,
                message="No new FRED data detected",
            )

        module_scores, overall = self._compute_module_scores(as_of_date=d)
        regime_probs = self._classify_regime(module_scores)
        portfolio_alloc = self._map_portfolio(module_scores)
        signals = self._summarize_signals(module_scores)

        wrote = self.db.macro_snapshots.upsert_snapshot(
            as_of_date=d,
            module_scores=module_scores,
            overall_score=overall,
            regime_probs=regime_probs,
            portfolio_alloc=portfolio_alloc,
            signals=signals,
            inputs_used=inputs_used,
            is_month_end=_is_month_end(d),
        )

        return MacroRunResult(
            ok=bool(wrote),
            as_of_date=d,
            updated_series=updated_series,
            snapshot_written=bool(wrote),
            message="Macro snapshot recomputed",
        )

    def _compute_module_scores(self, as_of_date: date) -> Tuple[Dict[str, Any], Optional[float]]:
        # Pull last ~24 months of data for each series.
        start = as_of_date - timedelta(days=900)

        def get_series(sid: str) -> List[Dict[str, Any]]:
            pts = self.db.macro.get_series_points(series_id=sid, start_date=start, end_date=as_of_date) or []
            # normalize values
            out = []
            for p in pts:
                v = p.get("value")
                if v is None:
                    continue
                try:
                    out.append({"date": p.get("observation_date"), "value": float(v)})
                except Exception:
                    continue
            return out

        # Simple scoring rules (MVP): use z-score of last 24m level/momentum depending on series.
        # This is intentionally transparent and easy to replace later.

        scores: Dict[str, Any] = {}

        # Growth: INDPRO YoY proxy + Retail Sales YoY proxy
        indpro = get_series("INDPRO")
        rsafs = get_series("RSAFS")
        growth_score = self._blend_scores(
            [
                self._yoy_z_score(indpro, invert=False),
                self._yoy_z_score(rsafs, invert=False),
            ]
        )
        scores["growth"] = {"score": growth_score}

        # Labor: unemployment (lower better) + jobless claims (lower better)
        unrate = get_series("UNRATE")
        icsa = get_series("ICSA")
        labor_score = self._blend_scores(
            [
                self._level_z_score(unrate, invert=True),
                self._level_z_score(icsa, invert=True),
            ]
        )
        scores["labor"] = {"score": labor_score}

        # Inflation: CPI YoY (lower better)
        cpi = get_series("CPIAUCSL")
        inflation_score = self._blend_scores([self._yoy_z_score(cpi, invert=True)])
        scores["inflation"] = {"score": inflation_score}

        # Rates: Fed Funds + 10Y (lower better), yield curve slope (steeper better)
        dff = get_series("DFF")
        dgs2 = get_series("DGS2")
        dgs10 = get_series("DGS10")
        curve_score = self._curve_score(dgs10, dgs2)
        rates_score = self._blend_scores(
            [
                self._level_z_score(dff, invert=True),
                self._level_z_score(dgs10, invert=True),
                curve_score,
            ]
        )
        scores["rates"] = {"score": rates_score}

        # Credit: HY spread (lower better)
        hy = get_series("BAMLH0A0HYM2")
        credit_score = self._blend_scores([self._level_z_score(hy, invert=True)])
        scores["credit"] = {"score": credit_score}

        # Liquidity: M2 YoY (higher better)
        m2 = get_series("M2SL")
        liquidity_score = self._blend_scores([self._yoy_z_score(m2, invert=False)])
        scores["liquidity"] = {"score": liquidity_score}

        # Housing: starts YoY + permits YoY
        houst = get_series("HOUST")
        permit = get_series("PERMIT")
        housing_score = self._blend_scores(
            [
                self._yoy_z_score(houst, invert=False),
                self._yoy_z_score(permit, invert=False),
            ]
        )
        scores["housing"] = {"score": housing_score}

        # Manufacturing proxy: INDPRO YoY + Capacity utilization level
        tcu = get_series("TCU")
        mfg_score = self._blend_scores(
            [
                self._yoy_z_score(indpro, invert=False),
                self._level_z_score(tcu, invert=False),
            ]
        )
        scores["manufacturing"] = {"score": mfg_score}

        module_scores = {k: v["score"] for k, v in scores.items() if isinstance(v, dict)}
        overall_vals = [v for v in module_scores.values() if isinstance(v, (int, float))]
        overall = sum(overall_vals) / float(len(overall_vals)) if overall_vals else None

        # store expanded module details (score only for now; keep shape extensible)
        out = {k: {"score": v["score"]} for k, v in scores.items()}
        return out, overall

    def _blend_scores(self, scores: List[Optional[float]]) -> Optional[float]:
        vals = [s for s in scores if isinstance(s, (int, float))]
        if not vals:
            return None
        return float(sum(vals) / float(len(vals)))

    def _level_z_score(self, series: List[Dict[str, Any]], invert: bool) -> Optional[float]:
        vals = [float(p["value"]) for p in series if p.get("value") is not None]
        z = _zscore(vals)
        return _score_from_z(z, invert=invert)

    def _yoy_z_score(self, series: List[Dict[str, Any]], invert: bool) -> Optional[float]:
        # compute yoy % change on last point vs ~12 months prior (nearest).
        if len(series) < 15:
            return None

        latest = series[-1]
        latest_val = latest.get("value")
        if latest_val is None:
            return None

        # find point approx 12 months earlier
        latest_date = datetime.fromisoformat(latest["date"]).date() if isinstance(latest.get("date"), str) else None
        if latest_date is None:
            return None

        target = latest_date - timedelta(days=365)
        prev_val: Optional[float] = None
        for p in reversed(series):
            pd = datetime.fromisoformat(p["date"]).date() if isinstance(p.get("date"), str) else None
            if pd is None:
                continue
            if pd <= target and p.get("value") is not None:
                prev_val = float(p["value"])
                break

        yoy = _pct_change(float(latest_val), prev_val)
        if yoy is None:
            return None

        # z-score of yoy over history (rough): compute yoy for trailing points
        yoy_hist: List[float] = []
        for i in range(len(series)):
            # skip early points
            if i < 12:
                continue
            curr = series[i].get("value")
            if curr is None:
                continue
            curr_date = datetime.fromisoformat(series[i]["date"]).date() if isinstance(series[i].get("date"), str) else None
            if curr_date is None:
                continue
            tgt = curr_date - timedelta(days=365)
            pv = None
            for j in range(i - 1, -1, -1):
                jd = datetime.fromisoformat(series[j]["date"]).date() if isinstance(series[j].get("date"), str) else None
                if jd is None:
                    continue
                if jd <= tgt and series[j].get("value") is not None:
                    pv = float(series[j]["value"])
                    break
            yy = _pct_change(float(curr), pv)
            if yy is not None:
                yoy_hist.append(float(yy))

        z = _zscore(yoy_hist) if yoy_hist else None
        # If zscore can't be computed, map yoy directly.
        if z is None:
            s = 50.0 + (yoy * 2.0)
            if invert:
                s = 100.0 - s
            return _clip(s, 0.0, 100.0)

        return _score_from_z(z, invert=invert)

    def _curve_score(self, dgs10: List[Dict[str, Any]], dgs2: List[Dict[str, Any]]) -> Optional[float]:
        v10 = _latest_value(dgs10)
        v2 = _latest_value(dgs2)
        if v10 is None or v2 is None:
            return None
        slope = v10 - v2
        # Map slope: -1.0 -> 20, 0 -> 50, +1.0 -> 80
        s = 50.0 + (slope * 30.0)
        return _clip(s, 0.0, 100.0)

    def _classify_regime(self, module_scores: Dict[str, Any]) -> Dict[str, Any]:
        # Rule-based probabilistic classifier.
        g = (module_scores.get("growth") or {}).get("score")
        l = (module_scores.get("labor") or {}).get("score")
        i = (module_scores.get("inflation") or {}).get("score")
        c = (module_scores.get("credit") or {}).get("score")
        r = (module_scores.get("rates") or {}).get("score")

        def safe(v):
            return float(v) if isinstance(v, (int, float)) else 50.0

        g, l, i, c, r = safe(g), safe(l), safe(i), safe(c), safe(r)

        expansion = _clip((g * 0.35 + l * 0.25 + c * 0.20 + i * 0.10 + r * 0.10), 0.0, 100.0)
        recession = _clip((100.0 - g) * 0.40 + (100.0 - l) * 0.25 + (100.0 - c) * 0.25 + (100.0 - i) * 0.05 + (100.0 - r) * 0.05, 0.0, 100.0)
        late = _clip((100.0 - i) * 0.35 + (100.0 - r) * 0.25 + g * 0.20 + l * 0.10 + c * 0.10, 0.0, 100.0)
        slowdown = _clip((100.0 - g) * 0.40 + l * 0.20 + c * 0.20 + i * 0.10 + r * 0.10, 0.0, 100.0)

        total = expansion + late + slowdown + recession
        if total <= 0:
            return {"expansion": 0.25, "late_cycle": 0.25, "slowdown": 0.25, "recession": 0.25}

        return {
            "expansion": expansion / total,
            "late_cycle": late / total,
            "slowdown": slowdown / total,
            "recession": recession / total,
        }

    def _map_portfolio(self, module_scores: Dict[str, Any]) -> Dict[str, Any]:
        g = (module_scores.get("growth") or {}).get("score")
        i = (module_scores.get("inflation") or {}).get("score")
        c = (module_scores.get("credit") or {}).get("score")
        r = (module_scores.get("rates") or {}).get("score")

        def safe(v):
            return float(v) if isinstance(v, (int, float)) else 50.0

        g, i, c, r = safe(g), safe(i), safe(c), safe(r)

        # Institutional-style static rules
        if g > 75 and i > 60 and c > 70:
            return {"growth": 0.80, "value": 0.15, "cash": 0.05}
        if g > 65 and c > 60:
            return {"growth": 0.70, "value": 0.20, "cash": 0.10}
        if g < 45 or c < 45:
            return {"growth": 0.35, "value": 0.35, "cash": 0.30}
        if r < 45 and i < 55:
            return {"growth": 0.50, "value": 0.30, "cash": 0.20}

        return {"growth": 0.55, "value": 0.25, "cash": 0.20}

    def _summarize_signals(self, module_scores: Dict[str, Any]) -> Dict[str, Any]:
        def bucket(v: Optional[float]) -> str:
            if v is None:
                return "unknown"
            if v >= 70:
                return "strong"
            if v >= 50:
                return "neutral"
            return "weak"

        out: Dict[str, Any] = {}
        for k in ["growth", "labor", "inflation", "rates", "credit", "liquidity", "housing", "manufacturing"]:
            s = (module_scores.get(k) or {}).get("score")
            out[k] = {
                "score": float(s) if isinstance(s, (int, float)) else None,
                "bucket": bucket(float(s)) if isinstance(s, (int, float)) else "unknown",
            }
        return out
