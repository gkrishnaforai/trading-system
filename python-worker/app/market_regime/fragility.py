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
        # direction matters — leveraged funds are structurally short
        # index futures, so a raw percentile of net is ambiguous:
        # net at its high percentile could be 'least short', not
        # 'crowded long'. Carry BOTH the directional percentile and
        # the absolute-size percentile; the scorer interprets side.
        chg4w = (nets[0]["net_pct"] - nets[4]["net_pct"]
                 if len(nets) > 4 else None)
        return {"report_date": latest["date"],
                "net_pct_oi": round(latest["net_pct"], 2),
                "direction": ("net_long" if latest["net_pct"] > 0
                              else "net_short"),
                "net_pctile_1y": _pctile(hist, latest["net_pct"]),
                "abs_pctile_1y": _pctile(
                    [abs(x) for x in hist], abs(latest["net_pct"])),
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

    # trigger STATE — 'proximity' was the wrong name once a break has
    # fired: QQQ −10% under its SMA50 isn't near a trigger, it tripped
    # it. Track breached triggers and the distance to the NEXT
    # un-broken threshold separately so a selloff in progress doesn't
    # keep reading as 'approaching'.
    breached = []
    next_dists = []
    for sym, d in dist.items():
        if (d.get("d50") or 0) < 0:
            breached.append(f"{sym.lower()}_sma50")
        if (d.get("d200") or 0) < 0:
            breached.append(f"{sym.lower()}_sma200")
        for k in ("d50", "d200"):
            v = d.get(k)
            if v is not None and v > 0:
                next_dists.append(v)
    n_below50 = sum(1 for b in breached if b.endswith("sma50"))
    n_below200 = sum(1 for b in breached if b.endswith("sma200"))
    nearest = round(min(next_dists), 2) if next_dists else None
    if n_below200 >= 1 or n_below50 >= 3:
        trigger_state = "heavily_breached"
    elif n_below50 >= 1:
        trigger_state = "breached"
    elif nearest is not None and nearest < 2.5:
        trigger_state = "approaching"
    else:
        trigger_state = "distant"

    worst = sorted(legs.items(), key=lambda kv: -kv[1])[:2]
    def _lbl(s: str) -> str:
        d = signals[s].get("d50_pct")
        if d is None:
            return f"{s} —"
        return (f"{s} {'below' if d < 0 else 'on'} SMA50 "
                f"({d:+.1f}%)")
    read = "; ".join(_lbl(s) for s, _ in worst)
    if nearest is not None:
        read += f" · next trigger {nearest:+.1f}% away"
    return {"score": round(_clamp(score), 1), "status": "observed",
            "trigger_state": trigger_state,
            "breached": breached,
            "nearest_unbroken_pct": nearest,
            "read": read, "signals": signals}


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
                               rvol5: Optional[float],
                               rvol20_ago: Optional[float] = None
                               ) -> dict[str, Any]:
    """Modeled vol-control exposure — ESTIMATED, never observed.

    The vol-target cohort scales equity exposure by target/realized.
    Three numbers matter, and conflating them was the review's point:
      entry    what they were carrying BEFORE the shock — sized off
               realized vol ~10d ago (the lag: they lever on stale vol)
      target   where today's vol forces them — target/rvol_now
      remaining entry − target: the mechanical selling still to come.
    remaining ≈ 0 after a vol spike means the wave already fired —
    high vol then stops implying MORE selling, which a flat 'over-
    allocated' score got wrong."""
    if rvol20 is None:
        return {"score": None, "status": "missing",
                "read": "no realized vol", "signals": {}}
    entry = min(_VOL_CONTROL_MAX_MULT,
                _VOL_TARGET / max(rvol20_ago or rvol20, 4.0))
    target = min(_VOL_CONTROL_MAX_MULT,
                 _VOL_TARGET / max(rvol20, 4.0))
    remaining = max(0.0, entry - target)
    firing = bool(remaining > 0.10 and rvol5 and rvol20
                  and rvol5 > rvol20 * 1.3 and rvol20 > _VOL_TARGET)
    # over-allocated quiet (spring) OR large remaining wave (loaded
    # gun mid-selloff) — the bigger threat owns the leg score
    over = _clamp((entry - 0.5) / 1.5 * 100)
    rem = _clamp(remaining / 0.8 * 100)
    score = max(over * 0.7, rem)
    if firing:
        score = max(score, 80)
    signals = {"entry_exposure": round(entry, 2),
               "target_exposure": round(target, 2),
               "remaining_deleveraging": round(remaining, 2),
               "vol_target_pct": _VOL_TARGET,
               "rvol20": round(rvol20, 1),
               "rvol20_ago": round(rvol20_ago, 1)
               if rvol20_ago else None,
               "rvol5": round(rvol5, 1) if rvol5 else None,
               "deleveraging_firing": firing}
    if remaining >= 0.15:
        tail = f" ~{remaining:.1f}× exposure still to cut"
    elif target < entry:
        tail = " de-lever wave largely done"
    else:
        tail = (" — cohort over-allocated" if entry > 1.2
                else " — inside target band")
    read = (f"entry {entry:.1f}× → target {target:.1f}×" + tail)
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
        net_pctile = cot.get("net_pctile_1y")
        abs_pctile = cot.get("abs_pctile_1y")
        direction = cot.get("direction")
        chg = cot.get("chg_4w")
        # interpretation is directional: a crowded LONG is downside
        # fuel (forced sells when the trade breaks); a crowded SHORT
        # is squeeze fuel, not sell pressure — same instability, less
        # selloff contribution. Score = size percentile scaled by side.
        base = abs_pctile if abs_pctile is not None else 50
        if direction == "net_long":
            s = _clamp(base)                    # full downside fuel
        else:
            # net-short crowding — high absolute position still
            # unstable, but it isn't sell pressure; cap at ~60% of it
            s = _clamp(base * 0.6)
        if chg is not None and chg < -1.5:
            s = max(0, s - 15)                  # already de-grossing
        elif chg is not None and chg > 2:
            s = min(100, s + 10)                # still adding exposure
        subs["cot"] = (s, 30)
        signals["cot_net_pct_oi"] = net_pct
        signals["cot_direction"] = direction
        signals["cot_net_pctile_1y"] = net_pctile
        signals["cot_abs_pctile_1y"] = abs_pctile
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
        bits.append(
            f"COT lev-fund {cot.get('direction', 'net').replace('_', ' ')}"
            f" {net_pct:+.1f}% OI"
            + (f" ({cot['net_pctile_1y']:.0f}th pctile)"
               if cot.get("net_pctile_1y") is not None else ""))
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


def score_discharge(lev: dict, cot: dict, pressure_signals: dict,
                    vix: Optional[float], vix_chg5: Optional[float],
                    credit_state: Optional[str]) -> dict[str, Any]:
    """How much of the stored leverage has already been flushed — the
    'fuel burned' read. High discharge + no bottom evidence = mid-
    selloff; high discharge + bottom structure = the dangerous part
    is behind. Selloffs end when the marginal forced seller is done,
    not when price looks low."""
    pts = 0.0
    signals: dict[str, Any] = {}
    # leveraged-ETF redemptions — real leverage leaving the system
    aum = lev.get("lev_aum_chg_pct")
    if aum is not None:
        signals["lev_aum_chg_20d_pct"] = aum
        if aum <= -8:
            pts += 25
        elif aum <= -3:
            pts += 15
        elif aum >= 5:
            pts -= 10              # still adding leverage mid-tape
    share_tr = lev.get("lev_vol_share_trend")
    if share_tr is not None:
        signals["lev_vol_share_trend"] = share_tr
        if share_tr < -0.03:
            pts += 10              # speculative volume leaving
    # COT leveraged funds cutting = systematic books de-grossing
    cot_chg = cot.get("chg_4w")
    if cot_chg is not None:
        signals["cot_chg_4w"] = cot_chg
        if cot_chg <= -1.5:
            pts += 20
        elif cot_chg <= -0.5:
            pts += 10
        elif cot_chg >= 2:
            pts -= 10              # leveraged funds still adding
    # vol-control cohort already forced out — a SMALL remaining wave
    # means the mechanical selling largely fired; a large remaining
    # wave counts against discharge, not for it
    remaining = pressure_signals.get("remaining_deleveraging")
    if remaining is not None:
        signals["vol_control_remaining"] = remaining
        if remaining <= 0.05 and (pressure_signals.get("rvol20") or 0) \
                > _VOL_TARGET:
            pts += 20              # wave fired and mostly spent
        elif remaining >= 0.4:
            pts -= 10              # big mechanical wave still ahead
    if pressure_signals.get("deleveraging_firing"):
        pts += 10
        signals["vol_control_fired"] = True
    rvol = pressure_signals.get("rvol20")
    if rvol is not None and rvol >= 15:
        pts += 10
        signals["rvol20"] = rvol
    # the VIX spring — released AND cresting is the tell; still
    # ramping means discharge hasn't finished
    if vix is not None:
        signals["vix"] = vix
        if vix >= 25:
            pts += 10
        if vix_chg5 is not None:
            signals["vix_chg_5d"] = round(vix_chg5, 1)
            if vix_chg5 <= -3:
                pts += 10          # fear cresting
            elif vix_chg5 >= 5:
                pts -= 10          # fear still building
    # credit still widening = the flush isn't done — counter-evidence
    if credit_state in ("stress", "severe"):
        pts -= 15
        signals["credit_still_widening"] = credit_state
    score = round(_clamp(pts), 1)
    read = (f"discharge evidence {score:.0f}"
            + (" — leverage visibly leaving" if pts >= 40
               else " — discharge incomplete" if pts >= 20
               else " — leverage still loaded"))
    return {"score": score, "status": "observed",
            "read": read, "signals": signals}


def score_bottom_structure(cells: dict[str, dict],
                           smh_rs20: Optional[float]
                           ) -> dict[str, Any]:
    """Index-level bottom evidence — the capitulation-stabilization
    checklist applied to SPY/QQQ/SMH: higher low, no new lows in 5d,
    anchored-VWAP reclaim, meaningful bounce volume. 'Recovering'
    needs the structure, not just a green day."""
    subs = {"SPY": 0.5, "QQQ": 0.3, "SMH": 0.2}
    score = 0.0
    got = 0
    signals: dict[str, Any] = {}
    for sym, w in subs.items():
        bs = cells.get(sym) or {}
        if not bs:
            continue
        got += 1
        s = 0.0
        if bs.get("higher_low"):
            s += 30
        nlows = bs.get("new_lows_5d")
        if nlows == 0:
            s += 20
        elif (nlows or 0) >= 3:
            s -= 15
        if bs.get("above_avwap"):
            s += 25
        if (bs.get("bounce_vol_ratio") or 0) > 1.15:
            s += 25
        signals[sym] = {**bs, "score": round(s, 1)}
        score += _clamp(s) * w
    if smh_rs20 is not None:
        signals["smh_rs20_pct"] = round(smh_rs20 * 100, 1)
        if smh_rs20 > -0.03:
            score += 10            # the weakest sector stabilizing
        elif smh_rs20 < -0.10:
            score -= 10            # still leading the decline
    if not got:
        return {"score": None, "status": "missing",
                "read": "no index bar data", "signals": {}}
    score = round(_clamp(score), 1)
    bits = []
    for sym in subs:
        bs = signals.get(sym)
        if not bs:
            continue
        marks = []
        if bs.get("higher_low"):
            marks.append("higher low")
        if bs.get("new_lows_5d") == 0:
            marks.append("no new lows")
        elif (bs.get("new_lows_5d") or 0) >= 3:
            marks.append("still making lows")
        if bs.get("above_avwap"):
            marks.append("above AVWAP")
        if (bs.get("bounce_vol_ratio") or 0) > 1.15:
            marks.append("bounce volume")
        if marks:
            bits.append(f"{sym}: {'/'.join(marks)}")
    read = (f"bottoming evidence {score:.0f} — "
            + ("; ".join(bits) if bits else "no stabilization yet"))
    return {"score": score, "status": "observed",
            "read": read, "signals": signals}


def score_selling_pressure(firing: list[str], trigger_state: str,
                           credit_score: Optional[float],
                           vix: Optional[float],
                           vix_chg5: Optional[float]) -> dict[str, Any]:
    """How much systematic selling is happening RIGHT NOW — the fourth
    headline, kept separate from stored fragility: a market can carry
    max vulnerability with zero selling pressure (the loaded calm),
    and a market can be discharging hard with vulnerability already
    spent. Firing flags + breached triggers + credit stress + a live
    vol shock compose the read."""
    s = 0.0
    s += min(40, 13 * len(firing))
    if trigger_state == "heavily_breached":
        s += 25
    elif trigger_state == "breached":
        s += 15
    elif trigger_state == "approaching":
        s += 5
    if credit_score is not None and credit_score >= 60:
        s += 20
    elif credit_score is not None and credit_score >= 35:
        s += 8
    if vix is not None and vix >= 28:
        s += 10
    if vix_chg5 is not None and vix_chg5 > 3:
        s += 8
    score = round(_clamp(s), 1)
    band = ("intense" if score >= 70 else "active" if score >= 45
            else "light" if score >= 20 else "quiet")
    return {"score": score, "band": band, "status": "observed",
            "read": f"selling pressure {band}",
            "signals": {"firing": firing,
                        "trigger_state": trigger_state,
                        "credit_score": credit_score,
                        "vix": vix, "vix_chg5": vix_chg5}}


# ================== exhaustion (SSES) — sellers running out =========
# The third axis: vulnerability says 'loaded', selling_pressure says
# 'firing', exhaustion says 'nearly spent'. Forced sellers run out
# when the panic markers crest, the climax volume is behind, breadth
# stops worsening and the leverage flush completes.

_EXH_WEIGHTS = {"discharge": 30, "bottom": 25, "panic": 20,
                "volume": 15, "breadth": 10}
_EXH_BANDS = [(70, "spent"), (50, "maturing"), (30, "developing"),
              (0, "absent")]


def score_panic_cresting(vix: Optional[float],
                         vix_chg5: Optional[float],
                         term: Optional[float],
                         term_ago: Optional[float],
                         vvix: Optional[float],
                         vvix_chg5: Optional[float],
                         rvol5: Optional[float],
                         rvol20: Optional[float]) -> dict[str, Any]:
    """Is the panic wave cresting? Observed — every input is a real
    quote. Forced-selling waves end when fear stops accelerating,
    not when fear is high."""
    pts = 0.0
    got = []
    if vix is not None:
        got.append("vix")
        if vix >= 25 and vix_chg5 is not None and vix_chg5 <= -3:
            pts += 35
        elif vix >= 25 and vix_chg5 is not None and vix_chg5 < 0:
            pts += 20
        elif vix_chg5 is not None and vix_chg5 > 5:
            pts -= 15              # still ramping — not cresting
    if term is not None and term_ago is not None:
        got.append("term")
        if term >= 1.0 and term_ago < 1.0:
            pts += 25              # re-steepened — panic passed
        elif term < 1.0 and term > term_ago:
            pts += 12              # healing, still inverted
    if vvix is not None and vvix_chg5 is not None:
        got.append("vvix")
        if vvix > 110 and vvix_chg5 <= -5:
            pts += 20              # tail-hedge demand rolling over
        elif vvix_chg5 > 10:
            pts -= 10
    if rvol5 is not None and rvol20 is not None:
        got.append("rvol")
        if rvol5 < rvol20:
            pts += 15              # the vol wave itself is decaying
    if not got:
        return {"score": None, "status": "missing",
                "read": "no panic data", "signals": {}}
    signals = {"vix": vix, "vix_chg5": vix_chg5,
               "term": term, "term_ago": term_ago,
               "vvix": vvix, "vvix_chg5": vvix_chg5,
               "rvol5": rvol5, "rvol20": rvol20}
    bits = []
    if vix and vix_chg5 is not None and vix_chg5 <= -3:
        bits.append(f"VIX cresting ({vix_chg5:+.0f}/5d)")
    if term is not None and term_ago is not None \
            and term >= 1.0 and term_ago < 1.0:
        bits.append("term structure re-steepened")
    if vvix and vvix_chg5 is not None and vvix_chg5 <= -5:
        bits.append(f"VVIX rolling ({vvix_chg5:+.0f}/5d)")
    if rvol5 and rvol20 and rvol5 < rvol20:
        bits.append("realized-vol wave decaying")
    return {"score": round(_clamp(pts), 1), "status": "observed",
            "read": "; ".join(bits) or "panic still building",
            "signals": signals}


def score_volume_exhaustion(bars: list[tuple]) -> dict[str, Any]:
    """Climax-volume signature — the classic exhaustion tell: a
    max-volume DOWN day near the low, then declines on shrinking
    volume (forced sellers spent), with up-days starting to out-
    volume down-days. `bars` = (close, volume) ascending, ≥25."""
    if len(bars) < 25:
        return {"score": None, "status": "missing",
                "read": "insufficient bar history", "signals": {}}
    closes = [b[0] for b in bars]
    vols = [b[1] for b in bars]
    w = list(zip(closes[-21:], vols[-21:]))
    # climax = max-volume day inside the window; must be a down day
    ci = max(range(1, len(w)), key=lambda i: w[i][1])
    climax_vol = w[ci][1]
    climax_down = w[ci][0] < w[ci - 1][0]
    days_since = len(w) - 1 - ci
    pts = 0.0
    signals = {"climax_days_ago": days_since,
               "climax_down_day": climax_down,
               "climax_vol": round(climax_vol)}
    if not climax_down or not climax_vol:
        return {"score": round(_clamp(pts), 1), "status": "observed",
                "read": "no down-day volume climax in window",
                "signals": signals}
    pts += 25
    # declines after the climax on shrinking volume — sellers drying
    down_vols_post = [v for (c, v), (pc, _) in
                      zip(w[ci + 1:], w[ci:-1]) if c < pc]
    if down_vols_post and climax_vol > 0:
        mean_post = sum(down_vols_post) / len(down_vols_post)
        signals["post_climax_down_vol_ratio"] = round(
            mean_post / climax_vol, 2)
        if mean_post < climax_vol * 0.6:
            pts += 30
        elif mean_post < climax_vol * 0.8:
            pts += 18
    elif days_since >= 3:
        pts += 15                  # no down days since the climax
    # up/down volume mix in the last 5 sessions — buyers regaining
    up_v = dn_v = 0.0
    for i in range(-5, 0):
        c, v = w[i][0], w[i][1]
        if w[i][0] > w[i - 1][0]:
            up_v += v
        elif w[i][0] < w[i - 1][0]:
            dn_v += v
    if up_v and dn_v:
        mix = up_v / dn_v
        signals["up_down_vol_5d"] = round(mix, 2)
        if mix > 1.3:
            pts += 25
        elif mix > 1.05:
            pts += 12
    # the climax low held — price didn't re-break it
    if closes[-1] >= w[ci][0]:
        pts += 15
        signals["climax_close_held"] = True
    return {"score": round(_clamp(pts), 1), "status": "observed",
            "read": (f"climax {days_since}d ago"
                     + (" — volume drying on declines"
                        if pts >= 40 else "")),
            "signals": signals}


def score_breadth_stabilization(payloads: list[dict]
                                ) -> dict[str, Any]:
    """Breadth stop-worsening — read the journaled regime payloads
    (PIT by construction): % above SMA50 trend + new-lows trend.
    ~5-day spread across the last snapshots."""
    probe = []
    for p in (payloads or [])[:6]:
        br = (p or {}).get("breadth") or {}
        row = {"as_of": p.get("as_of") if isinstance(p, dict) else None}
        for k in ("pct_above_sma50", "new_lows", "new_highs",
                  "breadth_chg_5d"):
            v = _f(br.get(k))
            if v is None:
                v = _f((p or {}).get(k))
            row[k] = v
        probe.append(row)
    have = [r for r in probe if r.get("pct_above_sma50") is not None]
    if len(have) < 2:
        return {"score": None, "status": "missing",
                "read": "no breadth journal", "signals": {}}
    newest, oldest = have[0], have[-1]
    delta = newest["pct_above_sma50"] - oldest["pct_above_sma50"]
    pts = 0.0
    signals = {"pct_above_sma50_now": newest["pct_above_sma50"],
               "pct_above_sma50_delta": round(delta, 1)}
    if delta >= 5:
        pts += 45
    elif delta >= 2:
        pts += 25
    elif delta >= 0:
        pts += 10
    elif delta <= -5:
        pts -= 10                  # still worsening
    nl_now, nl_then = newest.get("new_lows"), oldest.get("new_lows")
    if nl_now is not None and nl_then is not None:
        signals["new_lows_now"] = nl_now
        signals["new_lows_then"] = nl_then
        if nl_now < nl_then * 0.6:
            pts += 30              # new lows contracting hard
        elif nl_now < nl_then:
            pts += 15
        elif nl_now > nl_then * 1.5:
            pts -= 10              # new lows expanding
    nh = newest.get("new_highs")
    if nh is not None and nl_now is not None and nh >= nl_now:
        pts += 15
    return {"score": round(_clamp(pts), 1), "status": "observed",
            "read": (f"breadth {delta:+.0f}pts"
                     + (" — new lows contracting"
                        if (nl_now is not None and nl_then
                            and nl_now < nl_then) else "")),
            "signals": signals}


def score_exhaustion(legs: dict[str, dict]) -> dict[str, Any]:
    """SSES composite — weighted over resolved legs, missing legs
    renormalize (never inferred spent)."""
    have = {k: v for k, v in legs.items()
            if v.get("score") is not None}
    if not have:
        return {"score": None, "band": "unknown", "status": "missing",
                "read": "no exhaustion data", "legs": legs}
    tw = sum(_EXH_WEIGHTS[k] for k in have)
    score = round(sum(have[k]["score"] * _EXH_WEIGHTS[k]
                      for k in have) / tw, 1)
    band = next(name for lo, name in _EXH_BANDS if score >= lo)
    top = sorted(have.items(), key=lambda kv: -kv[1]["score"])[:2]
    read = (f"{band} — " + " · ".join(
        f"{k} {v['score']:.0f}" for k, v in top))
    return {"score": score, "band": band,
            "status": ("observed" if all(
                v.get("status") == "observed"
                for v in have.values()) else "partial"),
            "read": read, "legs": legs}


def _resolution(vuln: float, firing: list, discharge: dict,
                bottom: dict, dd52: Optional[float],
                trigger_state: Optional[str] = None
                ) -> dict[str, Any]:
    """Where in the deleveraging cycle — the 'more selloff or
    recovering' read. Five evidence phases over (stored) × (firing)
    × (flushed) × (structure forming):
      quiet        nothing stored up
      building     fragility stored, nothing tripped yet
      triggering   mechanical triggers just fired — onset happening
      discharging  forced selling underway, no bottom evidence
      stabilizing  bottom structure forming, flush incomplete
      recovering   leverage flushed AND structure confirmed"""
    dis = discharge.get("score")
    bot = bottom.get("score")
    sold_off = (dd52 or 0) <= -4 or len(firing) >= 2 or (vuln >= 60)
    if not sold_off and (vuln or 0) < 30:
        phase, tone = "quiet", "nothing stored up to discharge"
    elif bot is not None and bot >= 55 and (dis or 0) >= 40:
        phase, tone = "recovering", "leverage flushed + bottom structure"
    elif bot is not None and bot >= 45:
        phase, tone = "stabilizing", "bottom evidence forming"
    elif (dis or 0) >= 35 or len(firing) >= 2:
        phase, tone = "discharging", "forced selling in progress"
    elif len(firing) >= 1 or trigger_state in ("breached",
                                               "heavily_breached"):
        phase, tone = "triggering", "mechanical triggers just fired"
    else:
        phase, tone = "building", "fragility stored, not yet tripped"
    read = f"{phase} — {tone}"
    if dis is not None:
        read += f" · discharge {dis:.0f}"
    if bot is not None:
        read += f" · bottoming {bot:.0f}"
    return {"phase": phase, "discharge_score": dis,
            "bottom_score": bot, "read": read,
            "discharge": discharge.get("signals", {}),
            "bottom": bottom.get("signals", {})}


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

def _trigger_probs(vuln: float, band: str, firing: list[str],
                   discharge_score: Optional[float],
                   exhaustion_score: Optional[float]
                   ) -> dict[str, dict[str, float]]:
    """Three probability families — heuristic PRIORS journaled for
    calibration, not a fitted model. The single 'selloff within Nd'
    number conflated two different questions; now explicit:

      onset        a NEW forced-selling event starts within horizon —
                   meaningful pre-event; collapses once it's underway
      continuation significant further selling within horizon —
                   the relevant read while discharging
      exhaustion   forced selling is ~done within horizon — rises as
                   the flush completes and bottom structure forms

    All cumulative-within-horizon via the hazard approximation, so
    each family is non-decreasing in h."""
    def _scale(p5: float, cap: float = 0.60) -> dict[str, float]:
        return {f"{h}d": round(min(cap, 1 - (1 - p5) ** (h / 5)), 3)
                for h in (1, 3, 5, 10)}

    firing_mult = 1.0 + min(0.5, 0.18 * len(firing))
    onset_p5 = min(0.60, _BASE_P5.get(band, 0.06) * firing_mult)
    if firing:
        onset_p5 *= 0.4          # the event already began — onset
                                 # is mostly answered, not a forecast

    cont_p5 = {"critical": 0.35, "fragile": 0.28, "elevated": 0.18,
               "guarded": 0.10, "calm": 0.05}.get(band, 0.10)
    cont_p5 *= (1.0 + min(0.6, 0.15 * len(firing))
                + (0.25 if (discharge_score or 0) < 30 else 0.0))
    if not firing and (discharge_score or 0) < 20:
        cont_p5 *= 0.5           # nothing underway — continuation
                                 # has little to continue

    exh_p5 = min(0.75, (exhaustion_score or 0) / 100 * 0.7
                 + (0.05 if not firing else 0.0))

    return {"onset": _scale(onset_p5),
            "continuation": _scale(min(0.70, cont_p5), cap=0.70),
            "exhaustion": _scale(exh_p5, cap=0.75)}


def _assemble(legs: dict[str, dict], firing: list[str],
              as_of: date, extra_signals: dict,
              missing_extra: list[str],
              discharge_score: Optional[float] = None,
              exhaustion_score: Optional[float] = None,
              selling_pressure: Optional[dict] = None
              ) -> dict[str, Any]:
    have = {k: v for k, v in legs.items() if v.get("score") is not None}
    missing = [k for k in WEIGHTS if k not in have] + missing_extra
    tw = sum(WEIGHTS[k] for k in have)
    vuln = (sum(have[k]["score"] * WEIGHTS[k] for k in have) / tw
            if tw else 0.0)
    total_w = sum(WEIGHTS.values())
    observed_w = sum(WEIGHTS[k] for k in have
                     if have[k].get("status") == "observed")
    estimated_w = sum(WEIGHTS[k] for k in have
                      if have[k].get("status") == "estimated")
    coverage = round(observed_w / total_w * 100)
    est_share = round(estimated_w / total_w * 100)
    confidence = ("high" if coverage >= 85 else
                  "medium" if coverage >= 55 else "low")
    band = _band(vuln)
    probs = _trigger_probs(vuln, band, firing,
                           discharge_score, exhaustion_score)
    worst = sorted(have.items(), key=lambda kv: -kv[1]["score"])[:3]
    read = (f"{band} — " + " · ".join(
        f"{k.replace('_', ' ')} {v['score']:.0f}"
        for k, v in worst))
    return {"as_of": str(as_of),
            "vulnerability": round(vuln, 1),
            "band": band,
            "selling_pressure": selling_pressure,
            "probabilities": probs,
            "prob_model": "heuristic_prior",
            "event_def": _EVENT_DEF,
            "confidence": confidence,
            "coverage_pct": coverage,
            "data_quality": {"completeness_pct": coverage,
                             "estimated_pct": est_share,
                             "missing": missing,
                             "confidence": confidence},
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
        rvol20, rv5[-1] if rv5 else None,
        rvol20_ago=rv_series[-11] if len(rv_series) >= 11 else None)
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
    if trig.get("trigger_state") in ("breached", "heavily_breached"):
        firing.append("ma_triggers_broken")
    if (credit_leg["score"] or 0) >= 70:
        firing.append("credit_stress")
    if term is not None and term < 1.0:
        firing.append("term_structure_inverted")
    if pressure["signals"].get("deleveraging_firing"):
        firing.append("vol_control_deleveraging")
    if vix is not None and vix >= 28:
        firing.append("vix_shock")

    # ---- resolution inputs — deleveraging-cycle evidence, computed
    # before assemble so discharge/bottom can feed the probability
    # families and selling-pressure headline
    try:
        from app.signals.sector_timing import (
            _bottom_structure, _ohlcv as _st_ohlcv)
        cells = {s: _bottom_structure(_st_ohlcv(s, 30, as_of))
                 for s in ("SPY", "QQQ", "SMH")}
    except Exception:
        cells = {}
    smh_c = _closes("SMH", 30, as_of)
    smh_rs20 = ((smh_c[-1] / smh_c[-21] - 1) - (spy[-1] / spy[-21] - 1)
                if len(smh_c) > 21 and len(spy) > 21 else None)
    vix_chg5 = _nf(vix_c[-1] - vix_c[-6]) if len(vix_c) > 6 else None
    discharge = score_discharge(
        lev, cot, pressure["signals"], vix, vix_chg5,
        credit_leg["signals"].get("credit_state"))
    bottom = score_bottom_structure(cells, smh_rs20)
    selling = score_selling_pressure(
        firing, trig.get("trigger_state") or "distant",
        credit_leg.get("score"), vix, vix_chg5)

    # ---- SSES — systematic selling exhaustion: 'are the forced
    # sellers running out?' Panic cresting + climax-volume signature
    # + breadth stabilization ride alongside the flush and bottom
    # reads; the composite is the third axis next to vulnerability
    # and selling pressure.
    spy_cv = _ohlcv("SPY", 30, as_of)
    vol_exh = score_volume_exhaustion(spy_cv)
    term_ago = (round(_nf(vix3m_c[-6]) / _nf(vix_c[-6]), 3)
                if len(vix3m_c) > 6 and len(vix_c) > 6
                and _nf(vix_c[-6]) else None)
    vvix_chg5 = (_nf(vvix_c[-1] - vvix_c[-6])
                 if len(vvix_c) > 6 else None)
    panic = score_panic_cresting(
        vix, vix_chg5, term, term_ago, vvix, vvix_chg5,
        rv5[-1] if rv5 else None, rvol20)
    try:
        from app.database import db as _db
        import json as _jj
        _payloads = []
        for _r in _db.execute_query(
                "SELECT payload FROM regime_snapshots"
                " ORDER BY as_of DESC LIMIT 6"):
            _p = _r["payload"]
            _payloads.append(_jj.loads(_p)
                             if isinstance(_p, str) else _p)
    except Exception:
        _payloads = []
    breadth_stab = score_breadth_stabilization(_payloads)
    exhaustion = score_exhaustion({
        "discharge": discharge, "bottom": bottom,
        "panic": panic, "volume": vol_exh,
        "breadth": breadth_stab})

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

    row = _assemble(legs, firing, as_of,
                    {"validators": validators}, missing_extra,
                    discharge_score=discharge["score"],
                    exhaustion_score=exhaustion["score"],
                    selling_pressure=selling)
    row["resolution"] = _resolution(
        row["vulnerability"], firing, discharge, bottom, dd52,
        trig.get("trigger_state"))
    row["exhaustion"] = exhaustion
    row["signals"] = {**row.get("signals", {}),
                      "exhaustion": exhaustion}
    return row


# ============================ journal ============================

def _persist(row: dict[str, Any]) -> None:
    from app.database import db
    db.execute_update(
        "INSERT INTO fragility_daily"
        " (as_of, vulnerability, band, probabilities, legs, signals,"
        "  firing, validators, resolution, confidence, coverage_pct,"
        "  missing, read)"
        " VALUES (:d,:v,:b,:p,:l,:s,:f,:val,:res,:c,:cv,:m,:r)"
        " ON CONFLICT (as_of) DO UPDATE SET"
        " vulnerability=EXCLUDED.vulnerability, band=EXCLUDED.band,"
        " probabilities=EXCLUDED.probabilities, legs=EXCLUDED.legs,"
        " signals=EXCLUDED.signals, firing=EXCLUDED.firing,"
        " validators=EXCLUDED.validators,"
        " resolution=EXCLUDED.resolution,"
        " confidence=EXCLUDED.confidence,"
        " coverage_pct=EXCLUDED.coverage_pct,"
        " missing=EXCLUDED.missing, read=EXCLUDED.read",
        {"d": row["as_of"], "v": row["vulnerability"],
         "b": row["band"], "p": json.dumps(row["probabilities"]),
         "l": json.dumps(row["legs"]), "s": json.dumps(row["signals"]),
         "f": json.dumps(row["firing"]),
         "val": json.dumps(row["validators"]),
         "res": json.dumps(row.get("resolution") or {}),
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
            " signals, firing, validators, resolution, confidence,"
            " coverage_pct, missing, read, computed_at"
            " FROM fragility_daily ORDER BY as_of DESC LIMIT 1")
        if not rows:
            return None
        r = dict(rows[0])
        for k in ("probabilities", "legs", "signals", "firing",
                  "validators", "resolution", "missing"):
            if isinstance(r.get(k), str):
                r[k] = json.loads(r[k])
        r["as_of"] = str(r["as_of"])
        # hoisted headline — persisted inside signals JSONB
        r["exhaustion"] = (r.get("signals") or {}).get("exhaustion")
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
