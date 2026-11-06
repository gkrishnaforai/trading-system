"""Systematic Selling Early Warning (SSEW) — fragility, not direction.

The regime engine answers "what is the market doing"; deterioration
answers "is it weakening". This module answers the third, orthogonal
question: how much leverage and crowded positioning sits UNDER the
surface, and how close the mechanical sell triggers are. A market can
be bullish and fragile at the same time — calm tape with leverage
stacked on top is the state this exists to catch.

Two outputs, kept separate (same discipline as sector-timing's
opp/conf split — 'vulnerable' and 'about to trigger' are not the
same thing):

  selloff_vulnerability   0-100 — how fragile the market is today.
                          Weighted composite of six legs; missing legs
                          are excluded and weights renormalized (never
                          inferred healthy).

  trigger_probability     {1d,3d,5d,10d} — heuristic odds that a
                          systematic-selling event fires within the
                          horizon. Deliberately a labeled prior, NOT a
                          fitted model — journaled daily so realized
                          outcomes can calibrate it later (the same
                          journal-then-weigh pattern as forward_probs
                          and correction_evals).

Legs (weights are starting hypotheses, not fitted — see proposal):
  positioning        25  crowded positioning — leveraged-ETF volume
                         share + AUM change (etf_aum_snapshots), CFTC
                         TFF leveraged-fund net position (weekly,
                         obs-dated), put/call when the feed exists
  vol_control        20  vol-compression fragility (observed) +
                         modeled vol-target exposure (estimated)
  market_structure   20  dealer-gamma fragility PROXY — term
                         structure, VVIX, SKEW. No OI feed → this leg
                         is always `estimated`, never `observed`
  trigger_proximity  15  distance-to-MA systematic triggers across
                         SPY/QQQ/IWM/DIA/MDY/SMH (observed)
  credit_funding     15  HY/IG OAS + credit-ETF RS + MOVE (observed,
                         reuses credit_health's classifier)
  liquidity           5  system-liquidity direction — read from the
                         liquidity engine's journal

Status vocabulary per leg: observed | estimated | missing.
`estimated` means modeled, not measured — the payload says so and
confidence degrades; missing legs never count as neutral.

Event definition (fixed BEFORE any calibration):
  systematic-selling event = SPY 5d return < -2.5% AND
  (VIX +20% vs 5d ago OR SPY volume_ratio_20d > 1.4)

Phase-3 notes: margin debt is monthly + ~3-4wk lagged → surfaced as a
slow validator, never a scored leg. Dealer gamma needs an options-OI
provider — until one lands, market_structure is a labeled proxy.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import urllib.parse
import urllib.request
from datetime import date, datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)

# leg weights — the proposal's starting hypotheses; renormalized over
# legs with data each run so a missing feed degrades gracefully
WEIGHTS = {
    "positioning": 25,
    "vol_control": 20,
    "market_structure": 20,
    "trigger_proximity": 15,
    "credit_funding": 15,
    "liquidity": 5,
}

# index set for trigger proximity — the book's semis sleeve gets a
# real weight because SOX underperformance is itself a listed tell,
# but SPY/QQQ dominate: this is a market model, not a book model
_TRIGGER_UNIVERSE = {
    "SPY": 0.30, "QQQ": 0.25, "IWM": 0.10,
    "MDY": 0.10, "DIA": 0.10, "SMH": 0.15,
}

# leveraged-ETF set — crowding proxy: share of index volume
# these products absorb + their AUM trend
_LEV_ETFS = ["TQQQ", "SQQQ", "SOXL", "SOXS", "SPXL", "SPXS", "UPRO", "UVXY"]
_LEV_BENCH = ["QQQ", "SPY", "SOXX"]

_CFTC_BASE = "https://publicreporting.cftc.gov/resource/gpe5-46if.json"
_CFTC_MARKET = ("NASDAQ-100 Consolidated - CHICAGO MERCANTILE EXCHANGE")
_SKEW_CSV = ("https://cdn-api.cboe.com/api/global/us_indices/"
             "daily_prices/SKEW_History.csv")
# legacy put/call host retired with CBOE's site redesign — kept as a
# best-effort stub; leg reports missing when nothing parses
_PC_URLS = [
    "https://cdn.cboe.com/resources/historical_data/totalpc.csv",
    "https://www.cboe.com/publish/scheduledtask/mktdata/datahouse/"
    "totalpc.csv",
]

# vol-target cohort assumption — vol-control/risk-parity equity sleeve
# sized off ~10% target vol. Industry estimates put the cohort's
# equity exposure in the low hundreds of $B; the SCORE uses the
# exposure multiple (target/realized), not the AUM guess, so the
# number stays transparent and labeled `estimated`
_VOL_TARGET = 10.0
_VOL_CONTROL_MAX_MULT = 2.0   # position cap the cohort is assumed to run

_BANDS = [(75, "critical"), (60, "fragile"), (45, "elevated"),
          (25, "guarded"), (0, "calm")]

_EVENT_DEF = ("SPY 5d return < -2.5% AND (VIX +20% vs 5d ago OR "
              "SPY volume_ratio_20d > 1.4)")

# heuristic 5d trigger base rates by vulnerability band — priors
# journaled for calibration, not fitted
_BASE_P5 = {"critical": 0.25, "fragile": 0.18, "elevated": 0.11,
            "guarded": 0.06, "calm": 0.03}


def _f(v) -> Optional[float]:
    try:
        x = float(v)
        return x if x == x else None
    except (TypeError, ValueError):
        return None


def _nf(v) -> Optional[float]:
    """Native-float coercion — yfinance hands back np.float64 which
    silently poisons json.dumps at persist time."""
    return float(v) if v is not None else None


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def _pctile(hist: list[float], v: float) -> Optional[float]:
    """Percentile of v within hist — 0-100."""
    h = [x for x in hist if x is not None]
    if len(h) < 10:
        return None
    return round(sum(1 for x in h if x <= v) / len(h) * 100, 1)


def _band(score: float) -> str:
    for lo, name in _BANDS:
        if score >= lo:
            return name
    return "calm"


# ============================ data helpers ============================

def _closes(sym: str, n: int, as_of: Optional[date] = None
            ) -> list[float]:
    """daily_bars closes ascending, ≤ as_of. [] when absent."""
    from app.database import db
    try:
        rows = db.execute_query(
            "SELECT close FROM daily_bars WHERE symbol=:s AND date<=:d"
            " ORDER BY date DESC LIMIT :n",
            {"s": sym, "d": as_of or date.today(), "n": n})
        return [float(r["close"]) for r in reversed(rows)]
    except Exception:
        return []


def _ohlcv(sym: str, n: int, as_of: Optional[date] = None
           ) -> list[tuple]:
    """(close, volume) ascending — the volume legs need both."""
    from app.database import db
    try:
        rows = db.execute_query(
            "SELECT close, volume FROM daily_bars WHERE symbol=:s"
            " AND date<=:d ORDER BY date DESC LIMIT :n",
            {"s": sym, "d": as_of or date.today(), "n": n})
        return [(float(r["close"]), float(r.get("volume") or 0))
                for r in reversed(rows)]
    except Exception:
        return []


def _yf_closes(symbols: str, period: str = "1y") -> dict[str, list]:
    """yfinance daily closes — the vol-index family and leveraged ETFs
    mostly aren't in daily_bars, so these come straight from Yahoo.
    Returns {sym: closes ascending}."""
    try:
        import yfinance as yf
        import pandas as pd
        d = yf.download(symbols, period=period, interval="1d",
                        group_by="ticker", progress=False,
                        auto_adjust=True, timeout=25)
        out = {}
        if isinstance(d.columns, pd.MultiIndex):
            for s in symbols.split():
                if s in d:
                    vol = d[s]["Volume"].dropna() if "Volume" in d[s] \
                        else None
                    close = d[s]["Close"].dropna()
                    out[s] = (list(close.values),
                              list(vol.values) if vol is not None
                              else None)
        else:
            close = d["Close"].dropna()
            vol = d["Volume"].dropna() if "Volume" in d else None
            out[symbols.split()[0]] = (list(close.values),
                                       list(vol.values)
                                       if vol is not None else None)
        return out
    except Exception as exc:
        logger.debug("yf closes %s: %s", symbols, exc)
        return {}


def _sma(c: list[float], n: int) -> Optional[float]:
    return sum(c[-n:]) / n if len(c) >= n else None


def _rvol_series(c: list[float], n: int = 20) -> list[float]:
    """Rolling annualized realized vol (%) of daily log returns."""
    import math
    out = []
    rets = [math.log(c[i] / c[i - 1]) for i in range(1, len(c))
            if c[i - 1] > 0]
    for i in range(n, len(rets) + 1):
        w = rets[i - n:i]
        m = sum(w) / n
        var = sum((x - m) ** 2 for x in w) / (n - 1)
        out.append((var ** 0.5) * (252 ** 0.5) * 100)
    return out


def _vol_indices() -> dict[str, list]:
    """^VIX ^VIX3M ^VVIX ^MOVE daily closes, 1y — one yfinance call."""
    raw = _yf_closes("^VIX ^VIX3M ^VVIX ^MOVE", "1y")
    return {k: v[0] for k, v in raw.items()}


def _skew_series() -> list[tuple[date, float]]:
    """CBOE SKEW daily history — keyless CSV on cdn-api.cboe.com."""
    try:
        req = urllib.request.Request(
            _SKEW_CSV, headers={"User-Agent": "trading-system/ssew"})
        txt = urllib.request.urlopen(req, timeout=20).read().decode()
        out = []
        for row in csv.DictReader(io.StringIO(txt)):
            v = _f(row.get("SKEW"))
            if v is not None:
                out.append(
                    (datetime.strptime(row["DATE"], "%m/%d/%Y").date(),
                     v))
        return out
    except Exception as exc:
        logger.debug("skew csv: %s", exc)
        return []


def _put_call() -> dict[str, Optional[float]]:
    """Equity/total put-call ratio — best effort. CBOE retired the
    datahouse CSVs with the site redesign; whatever still parses wins.
    Returns {'equity_pc': f, 'total_pc': f, 'as_of': str} or {}."""
    for url in _PC_URLS:
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "trading-system/ssew"})
            raw = urllib.request.urlopen(req, timeout=12).read()
            txt = raw.decode("utf-8", errors="replace")
            rows = list(csv.DictReader(io.StringIO(txt)))
            if not rows:
                continue
            last = rows[-1]
            # the datahouse layout was wide — pick whatever exists
            out = {"as_of": last.get("DATE") or last.get("date")}
            for k, v in last.items():
                kl = (k or "").lower()
                if "equity" in kl and "ratio" in kl:
                    out["equity_pc"] = _f(v)
                elif "total" in kl and "ratio" in kl:
                    out["total_pc"] = _f(v)
            if out.get("equity_pc") or out.get("total_pc"):
                return out
        except Exception:
            continue
    return {}


def _cot() -> dict[str, Any]:
    """CFTC TFF — leveraged-fund net position in Nasdaq-100 futures
    (% of open interest) and its trailing-1y percentile + 4w change.
    Weekly report dated Tuesday, published Friday — the report date
    IS the observation date (PIT by construction)."""
    try:
        url = _CFTC_BASE + "?" + urllib.parse.urlencode({
            "market_and_exchange_names": _CFTC_MARKET,
            "$order": "report_date_as_yyyy_mm_dd DESC",
            "$limit": "110",
            "$select": "report_date_as_yyyy_mm_dd,"
                       "lev_money_positions_long,"
                       "lev_money_positions_short,"
                       "open_interest_all"})
        req = urllib.request.Request(
            url, headers={"User-Agent": "trading-system/ssew"})
        rows = json.loads(urllib.request.urlopen(
            req, timeout=20).read().decode())
        if not rows:
            return {}
        nets = []
        for r in rows:
            lo, sh = _f(r.get("lev_money_positions_long")), \
                     _f(r.get("lev_money_positions_short"))
            oi = _f(r.get("open_interest_all"))
            if lo is None or sh is None or not oi:
                continue
            nets.append({"date": r["report_date_as_yyyy_mm_dd"][:10],
                         "net_pct": (lo - sh) / oi * 100})
        if not nets:
            return {}
        latest = nets[0]
        hist = [n["net_pct"] for n in nets]
        pctile = _pctile(hist, latest["net_pct"])
        chg4w = (nets[0]["net_pct"] - nets[4]["net_pct"]
                 if len(nets) > 4 else None)
        return {"report_date": latest["date"],
                "net_pct_oi": round(latest["net_pct"], 2),
                "pctile_1y": pctile,
                "chg_4w": round(chg4w, 2) if chg4w is not None else None}
    except Exception as exc:
        logger.debug("cot: %s", exc)
        return {}


def _lev_flows(as_of: Optional[date] = None) -> dict[str, Any]:
    """Leveraged-ETF crowding — two reads:
      volume share: lev-ETF $volume / (lev + index $volume), 20d vs
                    its own distribution — speculative demand proxy
      aum trend   : total lev-ETF AUM 20d change from the journal —
                    real money in/out once history accrues
    Bars come from daily_bars when present, yfinance otherwise."""
    out: dict[str, Any] = {}
    # volume share — prefer daily_bars; yf for whatever's absent
    books = {s: _ohlcv(s, 30, as_of) for s in _LEV_ETFS + _LEV_BENCH}
    absent = [s for s, b in books.items() if len(b) < 20]
    if absent:
        yf = _yf_closes(" ".join(absent), "3mo")
        for s in absent:
            close, vol = yf.get(s, ([], None))
            if vol and len(close) >= 20:
                books[s] = list(zip(close, vol))
    lev_dv = bench_dv = 0.0
    lev_dv_prev = bench_dv_prev = 0.0
    for s, b in books.items():
        if len(b) < 25:
            continue
        dv20 = sum(c * v for c, v in b[-20:]) / 20
        dv_prev = sum(c * v for c, v in b[-40:-20]) / 20 \
            if len(b) >= 40 else None
        if s in _LEV_ETFS:
            lev_dv += dv20
            if dv_prev:
                lev_dv_prev += dv_prev
        else:
            bench_dv += dv20
            if dv_prev:
                bench_dv_prev += dv_prev
    if lev_dv and bench_dv:
        out["lev_vol_share"] = round(
            float(lev_dv / (lev_dv + bench_dv)), 3)
    if lev_dv_prev and bench_dv_prev:
        prev = float(lev_dv_prev / (lev_dv_prev + bench_dv_prev))
        out["lev_vol_share_prev"] = round(prev, 3)
        out["lev_vol_share_trend"] = round(
            out["lev_vol_share"] - prev, 3)

    # AUM trend — journal read; accruing until ≥5 snapshots
    try:
        from app.database import db
        rows = db.execute_query(
            "SELECT snap_date, sum(aum) aum FROM etf_aum_snapshots"
            " WHERE symbol = ANY(:s) GROUP BY snap_date"
            " ORDER BY snap_date DESC LIMIT :n",
            {"s": _LEV_ETFS, "n": 25})
        if len(rows) >= 5:
            newest, oldest = float(rows[0]["aum"]), \
                             float(rows[min(19, len(rows) - 1)]["aum"])
            out["lev_aum"] = newest
            out["lev_aum_chg_pct"] = round(
                (newest / oldest - 1) * 100, 2) if oldest else None
            out["aum_days"] = len(rows)
        else:
            out["aum_days"] = len(rows)
    except Exception as exc:
        logger.debug("lev aum: %s", exc)
    return out


def _snapshot_lev_aum() -> int:
    """Persist today's leveraged-ETF AUM into the shared flows journal
    so the trend leg accrues real history — reuses the FMP fetcher."""
    try:
        from app.portfolio_strategy import flows
        return flows.snapshot_aum(_LEV_ETFS)
    except Exception as exc:
        logger.debug("lev aum snapshot: %s", exc)
        return 0


# ============================ leg scorers ============================

def score_trigger_proximity(dist: dict[str, dict[str, Optional[float]]]
                            ) -> dict[str, Any]:
    """Distance to systematic sell triggers — the mechanical leg.

    For each index ETF: how far price sits above/below the MAs that
    trend-following and vol-target strategies actually key on. The
    50d is the primary CTA trigger; 200d is the regime trigger; 20d
    catches the fast money. Score per symbol = worst of the legs —
    hovering just above a trigger is fragile even while green."""
    legs, signals = {}, {}
    for sym, d in dist.items():
        d20, d50, d200 = d.get("d20"), d.get("d50"), d.get("d200")
        below50 = d.get("days_below_50") or 0
        if d50 is None and d200 is None:
            continue
        scores = []
        if d50 is not None:
            if d50 < 0:
                # already broken — systematic selling is firing, not
                # approaching. Persistence deepens it
                s = 85 + min(10, below50 * 2)
            elif d50 < 1:
                s = 75    # sitting on the trigger
            elif d50 < 2.5:
                s = 55
            elif d50 < 5:
                s = 30
            else:
                s = 10
            scores.append(s)
        if d200 is not None:
            if d200 < 0:
                scores.append(95)
            elif d200 < 1:
                scores.append(65)
            elif d200 < 3:
                scores.append(35)
            else:
                scores.append(10)
        # 20d is the fast trigger — lower ceiling, still informative
        if d20 is not None and d20 < 0:
            scores.append(40)
        legs[sym] = min(100, max(scores))
        signals[sym] = {"d20_pct": d20, "d50_pct": d50,
                        "d200_pct": d200, "below_50_streak": below50,
                        "score": legs[sym]}
    if not legs:
        return {"score": None, "status": "missing",
                "read": "no index distance data", "signals": {}}
    tot_w = sum(_TRIGGER_UNIVERSE.get(s, 0.05) for s in legs)
    score = sum(legs[s] * _TRIGGER_UNIVERSE.get(s, 0.05)
                for s in legs) / tot_w
    worst = sorted(legs.items(), key=lambda kv: -kv[1])[:2]
    def _lbl(s: str) -> str:
        d = signals[s].get("d50_pct")
        if d is None:
            return f"{s} —"
        return (f"{s} {'below' if d < 0 else 'on'} SMA50 "
                f"({d:+.1f}%)")
    read = "; ".join(_lbl(s) for s, _ in worst)
    return {"score": round(_clamp(score), 1), "status": "observed",
            "read": f"closest triggers — {read}",
            "signals": signals}


def score_vol_compression(rvol20: Optional[float],
                          rvol_pctile: Optional[float],
                          vix: Optional[float],
                          vix_pctile: Optional[float],
                          dd52: Optional[float]) -> dict[str, Any]:
    """Vol-compression fragility — the loaded-spring read. Compression
    is only fragility when it pairs with height: low realized vol near
    52w highs means the vol-target cohort is leveraged up; the same
    low vol after a correction means nothing."""
    if rvol20 is None or rvol_pctile is None:
        return {"score": None, "status": "missing",
                "read": "no realized-vol series", "signals": {}}
    compression = 100 - rvol_pctile     # low vol percentile = high
    if vix_pctile is not None:
        compression = 0.6 * compression + 0.4 * (100 - vix_pctile)
    # height multiplier — full weight within ~6% of the 52w high,
    # fading to a floor when the market has already corrected
    height = 1.0 if dd52 is None else min(
        1.0, max(0.3, (dd52 + 12.0) / 12.0))   # dd52 is negative %
    score = _clamp(compression * height)
    signals = {"rvol20": round(rvol20, 1),
               "rvol_pctile_1y": rvol_pctile,
               "vix": vix, "vix_pctile_1y": vix_pctile,
               "off_52w_high_pct": dd52,
               "height_weight": round(height, 2)}
    read = (f"realized vol {rvol20:.1f}% at {rvol_pctile:.0f}th pctile"
            + (f", VIX {vix_pctile:.0f}th pctile"
               if vix_pctile is not None else "")
            + (f" — compression near highs"
               if score >= 60 and (dd52 or -99) > -6 else ""))
    return {"score": round(score, 1), "status": "observed",
            "read": read, "signals": signals}


def score_vol_control_pressure(rvol20: Optional[float],
                               rvol5: Optional[float]
                               ) -> dict[str, Any]:
    """Modeled vol-control exposure — ESTIMATED, never observed.

    The vol-target cohort scales equity exposure by target/realized.
    rvol below target → they're over-allocated (fragility building);
    rvol above target → de-leveraging is already firing. Score is the
    assumed exposure multiple mapped 0-100 — the $ AUM isn't scored
    because it's a guess."""
    if rvol20 is None:
        return {"score": None, "status": "missing",
                "read": "no realized vol", "signals": {}}
    mult = min(_VOL_CONTROL_MAX_MULT,
               _VOL_TARGET / max(rvol20, 4.0))
    score = _clamp((mult - 0.5) / 1.5 * 100)   # 0.5×→0, 2×→100
    firing = bool(rvol5 and rvol20
                  and rvol5 > rvol20 * 1.5
                  and rvol20 > _VOL_TARGET)
    if firing:
        score = max(score, 85)
    signals = {"est_exposure_multiple": round(mult, 2),
               "vol_target_pct": _VOL_TARGET,
               "rvol20": round(rvol20, 1),
               "rvol5": round(rvol5, 1) if rvol5 else None,
               "deleveraging_firing": firing}
    read = (f"est {mult:.1f}× target-vol exposure"
            + (" — vol spike tripped de-leveraging"
               if firing else
               " — cohort over-allocated" if mult > 1.2
               else " — inside target band"))
    return {"score": round(score, 1), "status": "estimated",
            "read": read, "signals": signals}


def score_market_structure(vix: Optional[float],
                           vix_term_ratio: Optional[float],
                           vvix: Optional[float],
                           skew: Optional[float],
                           skew_pctile: Optional[float],
                           pc: dict) -> dict[str, Any]:
    """Dealer-gamma fragility PROXY — always `estimated` (no OI feed).

    Negative-gamma environments amplify declines; positive dampens.
    We can't observe gamma — we read the hedging-demand surface that
    surrounds it: term-structure inversion, tail-hedge pricing (VVIX),
    skew expensiveness, and put/call when a feed exists."""
    score = 0.0
    got = []
    if vix_term_ratio is not None:
        got.append("term")
        if vix_term_ratio < 1.0:
            score += 40           # backwardation = hedging stress
        elif vix_term_ratio < 1.08:
            score += 15
    if vvix is not None:
        got.append("vvix")
        score += 25 if vvix > 120 else 15 if vvix > 110 else 5 \
            if vvix > 100 else 0
    if skew_pctile is not None:
        got.append("skew")
        score += 25 if skew_pctile > 90 else 20 if skew_pctile > 80 \
            else 10 if skew_pctile > 60 else 0
    pc_eq = pc.get("equity_pc") if pc else None
    if pc_eq is not None:
        got.append("put_call")
        score += 15 if pc_eq > 1.1 else 8 if pc_eq > 0.9 else 0
    if not got:
        return {"score": None, "status": "missing",
                "read": "no vol-surface data", "signals": {}}
    signals = {"vix": vix, "vix_term_ratio":
               round(vix_term_ratio, 3)
               if vix_term_ratio is not None else None,
               "vvix": vvix, "skew": skew,
               "skew_pctile_1y": skew_pctile,
               "equity_pc": pc_eq, "inputs": got}
    parts = []
    if vix_term_ratio is not None and vix_term_ratio < 1.0:
        parts.append("term structure inverted")
    if vvix and vvix > 110:
        parts.append(f"VVIX {vvix:.0f} tail-hedge demand")
    if skew_pctile and skew_pctile > 80:
        parts.append(f"SKEW {skew_pctile:.0f}th pctile — tails rich")
    return {"score": round(_clamp(score), 1), "status": "estimated",
            "read": "; ".join(parts) or "vol surface calm",
            "signals": signals}


def score_positioning(lev: dict, cot: dict, pc: dict
                      ) -> dict[str, Any]:
    """Crowded positioning — how much of the same trade everyone is
    already in. Sub-legs, each scored 0-100, weighted by what's real:
      lev volume share (observed, daily)         40%
      lev AUM 20d trend (observed, accruing)     20%
      COT leveraged-fund net/OI (observed, wkly) 30%
      put/call complacency (observed, when live) 10%"""
    subs, signals = {}, {}
    share = lev.get("lev_vol_share")
    if share is not None:
        # historical norm for the lev/index volume mix runs ~0.10-0.20
        # on this universe — crowding reads off the level + the trend
        s = _clamp((share - 0.10) / 0.25 * 100)
        tr = lev.get("lev_vol_share_trend")
        if tr is not None and tr > 0.03:
            s = min(100, s + 15)
        subs["lev_vol_share"] = (s, 40)
        signals["lev_vol_share"] = share
        signals["lev_vol_share_trend"] = tr
    aum_chg = lev.get("lev_aum_chg_pct")
    if aum_chg is not None:
        subs["lev_aum"] = (_clamp(50 + aum_chg * 5), 20)
        signals["lev_aum_chg_20d_pct"] = aum_chg
    net_pct = cot.get("net_pct_oi")
    if net_pct is not None:
        pctile = cot.get("pctile_1y")
        # crowded = leveraged funds' net long in the top of its range
        s = _clamp(pctile if pctile is not None else 50)
        chg = cot.get("chg_4w")
        if chg is not None and chg < -1.5:
            s = max(0, s - 15)     # already de-grossing — less fuel
        subs["cot"] = (s, 30)
        signals["cot_net_pct_oi"] = net_pct
        signals["cot_pctile_1y"] = pctile
        signals["cot_chg_4w"] = chg
        signals["cot_report_date"] = cot.get("report_date")
    pc_eq = pc.get("equity_pc") if pc else None
    if pc_eq is not None:
        # LOW p/c = complacency = crowded long
        subs["put_call"] = (_clamp((0.9 - pc_eq) / 0.45 * 100), 10)
        signals["equity_pc"] = pc_eq
    if not subs:
        return {"score": None, "status": "missing",
                "read": "no positioning data", "signals": {}}
    tw = sum(w for _, w in subs.values())
    score = sum(s * w for s, w in subs.values()) / tw
    observed = [k for k in subs if k != "lev_aum"
                or (lev.get("aum_days") or 0) >= 5]
    status = ("observed" if len(observed) >= 2 else "estimated")
    bits = []
    if share is not None:
        bits.append(f"lev-vol share {share:.0%}")
    if aum_chg is not None:
        bits.append(f"lev AUM {aum_chg:+.0f}%/20d")
    if net_pct is not None:
        bits.append(f"COT lev-fund net {net_pct:+.1f}% OI"
                    f" ({cot.get('pctile_1y'):.0f}th pctile)"
                    if cot.get("pctile_1y") is not None else
                    f"COT lev-fund net {net_pct:+.1f}% OI")
    return {"score": round(score, 1), "status": status,
            "read": " · ".join(bits) or "no reads",
            "signals": signals}


def score_credit_funding(credit: dict, hyg_lqd_20d: Optional[float],
                         move: Optional[float]) -> dict[str, Any]:
    """Credit/funding deterioration — the real-money canary. Reuses
    credit_health's journaled HY/IG classifier rather than re-
    implementing FRED reads; ETF RS and bond vol layer on top."""
    st = credit.get("credit_state")
    if st in (None, "unknown"):
        return {"score": None, "status": "missing",
                "read": "credit data unavailable", "signals": {}}
    base = {"healthy": 10, "caution": 35, "stress": 70,
            "severe": 95}[st]
    score = base
    hy_d20, hy_d5 = credit.get("hy_oas_d20"), credit.get("hy_oas_d5")
    ig_d20 = credit.get("ig_oas_d20")
    if hy_d20 is not None and hy_d20 >= 0.5:
        score += 10
    elif hy_d20 is not None and hy_d20 >= 0.25:
        score += 5
    if hy_d5 is not None and hy_d5 >= 0.15:
        score += 5
    if ig_d20 is not None and ig_d20 >= 0.15:
        score += 5
    if hyg_lqd_20d is not None and hyg_lqd_20d < -0.01:
        score += 10
    elif hyg_lqd_20d is not None and hyg_lqd_20d < -0.005:
        score += 5
    if move is not None and move > 130:
        score += 10
    elif move is not None and move > 110:
        score += 5
    signals = {"credit_state": st, "hy_oas": credit.get("hy_oas"),
               "hy_oas_d5": hy_d5, "hy_oas_d20": hy_d20,
               "ig_oas_d20": ig_d20, "hyg_lqd_20d": hyg_lqd_20d,
               "move": move,
               "credit_confidence": credit.get("confidence"),
               "fred_asof": credit.get("fred_asof")}
    read = (credit.get("why") or f"credit {st}")
    if hyg_lqd_20d is not None and hyg_lqd_20d < -0.005:
        read += f" · HYG/LQD {hyg_lqd_20d:+.1%}/20d"
    return {"score": round(_clamp(score), 1), "status": "observed",
            "read": read, "signals": signals}


def score_liquidity(liq: Optional[dict]) -> dict[str, Any]:
    """System-liquidity direction — read from the journaled engine.
    Liquidity tightening is the substrate deleveraging feeds on."""
    if not liq or liq.get("score") is None:
        return {"score": None, "status": "missing",
                "read": "no liquidity journal", "signals": {}}
    s = float(liq["score"])         # engine: 0 tightening → 100 strong
    score = _clamp(100 - s)
    return {"score": round(score, 1), "status": "observed",
            "read": f"liquidity {liq.get('bucket') or round(s)}"
                    f" — engine score {round(s)}",
            "signals": {"liquidity_score": round(s),
                        "bucket": liq.get("bucket"),
                        "as_of": liq.get("as_of")}}


# ============================ composite ============================

def _trigger_probs(vuln: float, band: str,
                   firing: list[str]) -> dict[str, float]:
    """Heuristic trigger probabilities — PRIORS for calibration, not
    a fitted model. Base rate by band scaled across horizons via the
    hazard approximation; live triggers bump it."""
    p5 = _BASE_P5.get(band, 0.06)
    firing_mult = 1.0 + min(0.5, 0.18 * len(firing))
    p5 = min(0.60, p5 * firing_mult)
    out = {}
    for h in (1, 3, 5, 10):
        p = 1 - (1 - p5) ** (h / 5)
        out[f"{h}d"] = round(min(0.60, p), 3)
    return out


def _assemble(legs: dict[str, dict], firing: list[str],
              as_of: date, extra_signals: dict,
              missing_extra: list[str]) -> dict[str, Any]:
    have = {k: v for k, v in legs.items() if v.get("score") is not None}
    missing = [k for k in WEIGHTS if k not in have] + missing_extra
    tw = sum(WEIGHTS[k] for k in have)
    vuln = (sum(have[k]["score"] * WEIGHTS[k] for k in have) / tw
            if tw else 0.0)
    observed_w = sum(WEIGHTS[k] for k in have
                     if have[k].get("status") == "observed")
    coverage = round(observed_w / sum(WEIGHTS.values()) * 100)
    confidence = ("high" if coverage >= 85 else
                  "medium" if coverage >= 55 else "low")
    band = _band(vuln)
    probs = _trigger_probs(vuln, band, firing)
    worst = sorted(have.items(), key=lambda kv: -kv[1]["score"])[:3]
    read = (f"{band} — " + " · ".join(
        f"{k.replace('_', ' ')} {v['score']:.0f}"
        for k, v in worst))
    return {"as_of": str(as_of),
            "vulnerability": round(vuln, 1),
            "band": band,
            "probabilities": probs,
            "prob_model": "heuristic_prior",
            "event_def": _EVENT_DEF,
            "confidence": confidence,
            "coverage_pct": coverage,
            "firing": firing,
            "legs": legs,
            "validators": extra_signals.get("validators", {}),
            "signals": {k: v.get("signals") for k, v in legs.items()},
            "missing": missing,
            "read": read}


def compute(as_of: Optional[date] = None) -> dict[str, Any]:
    """Fetch → score → assemble. Everything degrades honestly: a dead
    feed becomes a missing leg, never a neutral one."""
    as_of = as_of or date.today()
    missing_extra: list[str] = []

    # ---- trigger proximity (daily_bars only — cheap) ----
    dist = {}
    for sym in _TRIGGER_UNIVERSE:
        c = _closes(sym, 220, as_of)
        if len(c) < 60:
            continue
        s20, s50, s200 = _sma(c, 20), _sma(c, 50), _sma(c, 200)
        streak = 0
        if s50:
            for px in reversed(c):
                if px < s50:
                    streak += 1
                else:
                    break
        dist[sym] = {
            "d20": round((c[-1] / s20 - 1) * 100, 2) if s20 else None,
            "d50": round((c[-1] / s50 - 1) * 100, 2) if s50 else None,
            "d200": round((c[-1] / s200 - 1) * 100, 2) if s200 else None,
            "days_below_50": streak}
    trig = score_trigger_proximity(dist)

    # ---- vol family — SPY realized vol + Yahoo vol indices ----
    spy = _closes("SPY", 300, as_of)
    rv_series = _rvol_series(spy, 20) if len(spy) > 60 else []
    rvol20 = rv_series[-1] if rv_series else None
    rvol_pct = _pctile(rv_series[:-1] or rv_series, rvol20) \
        if rvol20 is not None else None
    rv5 = _rvol_series(spy, 5)
    hi52 = max(spy[-250:]) if len(spy) >= 250 else \
        (max(spy) if spy else None)
    dd52 = round((spy[-1] / hi52 - 1) * 100, 2) \
        if spy and hi52 else None
    vol_ix = _vol_indices()
    vix_c = vol_ix.get("^VIX") or []
    vix3m_c = vol_ix.get("^VIX3M") or []
    vvix_c = vol_ix.get("^VVIX") or []
    move_c = vol_ix.get("^MOVE") or []
    vix = _nf(vix_c[-1]) if vix_c else None
    vix_pct = _pctile(vix_c[:-1], vix) if vix else None
    v3 = _nf(vix3m_c[-1]) if vix3m_c else None
    term = round(v3 / vix, 3) if vix and v3 else None
    vvix = _nf(vvix_c[-1]) if vvix_c else None
    move = _nf(move_c[-1]) if move_c else None
    skew_s = _skew_series()
    skew = _nf(skew_s[-1][1]) if skew_s else None
    skew_pct = _pctile([v for _, v in skew_s[-260:-1]], skew) \
        if skew is not None else None

    compress = score_vol_compression(rvol20, rvol_pct, vix, vix_pct,
                                     dd52)
    pressure = score_vol_control_pressure(
        rvol20, rv5[-1] if rv5 else None)
    vc_score = None
    if compress["score"] is not None or pressure["score"] is not None:
        parts = [(l["score"], 0.55 if l is compress else 0.45)
                 for l in (compress, pressure)
                 if l["score"] is not None]
        vc_score = round(sum(s * w for s, w in parts)
                         / sum(w for _, w in parts), 1)
    vol_control = {"score": vc_score,
                   "status": "observed" if compress["score"] is not None
                             else pressure["status"],
                   "read": " · ".join(l["read"] for l in
                                     (compress, pressure)
                                     if l["score"] is not None),
                   "signals": {"compression": compress["signals"],
                               "pressure": pressure["signals"]}}

    pc = _put_call()
    structure = score_market_structure(vix, term, vvix, skew, skew_pct,
                                       pc)

    # ---- positioning — lev ETFs + COT (+ AUM snapshot accrual) ----
    lev = _lev_flows(as_of)
    cot = _cot()
    position = score_positioning(lev, cot, pc)

    # ---- credit/funding — reuse the journaled classifier ----
    try:
        from app.signals import credit_health
        credit = credit_health.current()
    except Exception:
        credit = {}
    hyg = _closes("HYG", 30, as_of)
    lqd = _closes("LQD", 30, as_of)
    hyg_lqd_20d = ((hyg[-1] / hyg[-21] - 1) - (lqd[-1] / lqd[-21] - 1)
                   if len(hyg) > 21 and len(lqd) > 21 else None)
    credit_leg = score_credit_funding(credit,
                                      round(hyg_lqd_20d, 4)
                                      if hyg_lqd_20d is not None
                                      else None, move)

    # ---- liquidity — journal read ----
    try:
        from app.signals import liquidity_engine
        liq = liquidity_engine.read()
    except Exception:
        liq = None
    liquidity = score_liquidity(liq)

    legs = {"positioning": position, "vol_control": vol_control,
            "market_structure": structure,
            "trigger_proximity": trig,
            "credit_funding": credit_leg,
            "liquidity": liquidity}

    # firing — legs that aren't fragile-but-quiet, they're already
    # selling: triggers broken, credit stressed, term inverted,
    # vol-target de-levering tripped
    firing = []
    if (trig["score"] or 0) >= 80:
        firing.append("ma_triggers_broken")
    if (credit_leg["score"] or 0) >= 70:
        firing.append("credit_stress")
    if term is not None and term < 1.0:
        firing.append("term_structure_inverted")
    if pressure["signals"].get("deleveraging_firing"):
        firing.append("vol_control_deleveraging")
    if vix is not None and vix >= 28:
        firing.append("vix_shock")

    validators = {
        "margin_debt": {"status": "unavailable",
                        "note": "FINRA margin stats are monthly with "
                                "~3-4wk publication lag — a slow "
                                "validator, never a scored leg at a "
                                "1-10d horizon"},
        "put_call": {"status": "observed" if pc else "unavailable",
                     "note": "CBOE datahouse retired with the site "
                             "redesign" if not pc else
                             pc.get("as_of")},
        "dealer_gamma": {"status": "proxy_estimated",
                         "note": "no options-OI feed — market_structure"
                                 " is a labeled estimate, not observed "
                                 "gamma"},
        "aum_days": lev.get("aum_days", 0),
    }

    return _assemble(legs, firing, as_of,
                     {"validators": validators}, missing_extra)


# ============================ journal ============================

def _persist(row: dict[str, Any]) -> None:
    from app.database import db
    db.execute_update(
        "INSERT INTO fragility_daily"
        " (as_of, vulnerability, band, probabilities, legs, signals,"
        "  firing, validators, confidence, coverage_pct, missing, read)"
        " VALUES (:d,:v,:b,:p,:l,:s,:f,:val,:c,:cv,:m,:r)"
        " ON CONFLICT (as_of) DO UPDATE SET"
        " vulnerability=EXCLUDED.vulnerability, band=EXCLUDED.band,"
        " probabilities=EXCLUDED.probabilities, legs=EXCLUDED.legs,"
        " signals=EXCLUDED.signals, firing=EXCLUDED.firing,"
        " validators=EXCLUDED.validators,"
        " confidence=EXCLUDED.confidence,"
        " coverage_pct=EXCLUDED.coverage_pct,"
        " missing=EXCLUDED.missing, read=EXCLUDED.read",
        {"d": row["as_of"], "v": row["vulnerability"],
         "b": row["band"], "p": json.dumps(row["probabilities"]),
         "l": json.dumps(row["legs"]), "s": json.dumps(row["signals"]),
         "f": json.dumps(row["firing"]),
         "val": json.dumps(row["validators"]),
         "c": row["confidence"], "cv": row["coverage_pct"],
         "m": json.dumps(row["missing"]), "r": row["read"]})


def run() -> dict[str, Any]:
    """Daily job entry — snapshot leveraged-ETF AUM first (its trend
    accrues inside the same journal the positioning leg reads), then
    compute + persist."""
    _snapshot_lev_aum()
    row = compute()
    _persist(row)
    return row


def latest() -> Optional[dict[str, Any]]:
    """Latest journaled block — the read layer for endpoints."""
    from app.database import db
    try:
        rows = db.execute_query(
            "SELECT as_of, vulnerability, band, probabilities, legs,"
            " signals, firing, validators, confidence, coverage_pct,"
            " missing, read, computed_at"
            " FROM fragility_daily ORDER BY as_of DESC LIMIT 1")
        if not rows:
            return None
        r = dict(rows[0])
        for k in ("probabilities", "legs", "signals", "firing",
                  "validators", "missing"):
            if isinstance(r.get(k), str):
                r[k] = json.loads(r[k])
        r["as_of"] = str(r["as_of"])
        return r
    except Exception:
        return None


def current() -> dict[str, Any]:
    """GET entry — journaled row, lazy-compute on an empty journal so
    first deploys don't wait for the nightly job."""
    row = latest()
    if row is None:
        try:
            row = run()
        except Exception as exc:
            logger.warning("fragility lazy compute failed: %s", exc)
            row = {"error": str(exc)}
    return row
