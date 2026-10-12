"""LEAP-put hedge universe — scored in four buckets, hedging-frame:
which names give the most expected downside convexity per dollar of
premium, FOR THE BOOK YOU ACTUALLY HOLD.

  1. fundamental vulnerability   0-30  extreme valuation, growth-
     dependent, decelerating revenue, negative FCF, dilution,
     theme concentration — the "most to lose" profile
  2. volatility discount         0-20  HV/IV — paying for vol the
     stock actually delivers, not a premium
  3. convexity                   0-20  β×HV÷IV — expected downside
     move per unit of implied vol purchased
  4. hedge correlation           0-30  60d return correlation to the
     hedge target — a put that crashes when CRDO crashes, not one
     that crashes on its own schedule
  5. extension                   0-15  the 'ATH + overbought' leg —
     dd52w/RSI/%B/vs_sma50 — scored separately from the `setup`
     window: extension picks the candidate, `rolling_over` marks
     the entry. Buying raw extension is the top-picking trap.
Liquidity (OI/spread/LEAPS) is a gate, not a score — thin chains get
flagged and tier-capped, not silently ranked.

hedge_roi() is the decisive test: expected payout on a −30% move ÷
premium, priced on the actual contract (BS with vol-bump + time
decay) — compared against QQQ and the hedge target itself.
"""
from __future__ import annotations

import logging
import math
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from statistics import mean, pstdev
from typing import Any, Optional

logger = logging.getLogger(__name__)

# theme dependence — names whose valuation embeds the AI-infra trade;
# a capex-cycle break hits them hardest (the book's real exposure)
_THEME_BETA = {"VRT", "ETN", "CRDO", "ALAB", "ONTO", "NVDA", "AVGO",
               "MU", "MRVL", "ARM", "IREN", "NBIS", "APLD", "CRWV",
               "EQIX", "TSM", "SMCI", "POWL", "COHR", "LITE", "ANET"}
RISK_FREE = 0.045


def _bars(sym: str, days: int = 200) -> dict[date, float]:
    from app.database import db
    return {r["date"]: float(r["close"]) for r in db.execute_query(
        "SELECT date, close FROM daily_bars WHERE symbol=:s "
        "AND date > :c ORDER BY date DESC LIMIT 160",
        {"s": sym, "c": date.today() - timedelta(days=days)})}


def _returns(px: dict[date, float]) -> dict[date, float]:
    ds = sorted(px, reverse=True)
    return {ds[i]: px[ds[i]] / px[ds[i + 1]] - 1
            for i in range(len(ds) - 1)}


def _beta_hv_corr(sym: str, target: str) -> dict[str, Optional[float]]:
    """60d beta vs QQQ, HV20/60, and 60d correlation vs hedge target —
    one bar pull per symbol."""
    spx = _bars(sym)
    q, tg = _bars("QQQ"), _bars(target)
    if len(spx) < 25 or len(q) < 25:
        return {}
    sr, qr, tr = _returns(spx), _returns(q), _returns(tg)
    common = sorted(set(sr) & set(qr))
    if len(common) < 20:
        return {}
    xs, ys = [qr[d] for d in common], [sr[d] for d in common]
    mx, my = mean(xs), mean(ys)
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / len(xs)
    var = sum((x - mx) ** 2 for x in xs) / len(xs)
    beta = cov / var if var else None
    hv20 = pstdev(ys[:20]) * math.sqrt(252) if len(ys) >= 20 else None
    hv60 = pstdev(ys[:60]) * math.sqrt(252) if len(ys) >= 60 else None
    # hedge correlation — vs the target, not QQQ
    tcommon = sorted(set(sr) & set(tr))
    corr = None
    if len(tcommon) >= 20:
        xa, ya = [tr[d] for d in tcommon], [sr[d] for d in tcommon]
        mx2, my2 = mean(xa), mean(ya)
        c = sum((x - mx2) * (y - my2) for x, y in zip(xa, ya))
        s_x = math.sqrt(sum((x - mx2) ** 2 for x in xa))
        s_y = math.sqrt(sum((y - my2) ** 2 for y in ya))
        corr = c / (s_x * s_y) if s_x and s_y else None
    return {"beta_qqq": beta, "hv20": hv20, "hv60": hv60,
            "corr_target": corr}


def _vulnerability(f: dict, q: dict, sym: str) -> float:
    """0-30: how much expectation is embedded in the price."""
    s = 0.0
    pe = f.get("fwd_pe")
    if pe is None and (q.get("net_income_ltm") or 0) <= 0:
        s += 10                                # pre-profit pure hope
    elif pe is not None:
        s += min(10, max(0, (pe - 25) / 45 * 10))
    if (f.get("rev_accel") or 0) < 0:
        s += 5                                 # growth decelerating
    if (q.get("free_cf_ltm") or 0) < 0:
        s += 5                                 # burning cash
    if (q.get("dilution_yoy") or 0) > 0.08:
        s += 4                                 # printing shares
    if sym in _THEME_BETA:
        s += 4                                 # one-theme exposure
    if (f.get("beat_streak") or 0) >= 4 and \
            (f.get("est_revision_pct") or 0) < 0:
        s += 2                                 # streak ending risk
    return min(30.0, s)


def _setup(state: Optional[str], det: dict
           ) -> tuple[Optional[float], str]:
    """Extension bonus 0-15 + put-window label — the 'ATH + overbought'
    technical leg the profile buckets can't see. Two separate answers,
    deliberately: extension says the name is stretched at highs (the
    candidate); the window says the stall is printing NOW (the entry).
    Buying puts on raw extension is the AMD-replay trap — run over 5x."""
    if not state:
        return None, "no tape"
    rsi, pct_b = det.get("rsi"), det.get("pct_b")
    dd, vs50 = det.get("dd52w"), det.get("vs_sma50")
    ext = 0.0
    if dd is not None:                    # distance below 52w high
        ext += (6 if dd > -0.03 else 4 if dd > -0.08 else
                1 if dd > -0.15 else 0)
    if rsi is not None:
        ext += 4 if rsi >= 70 else 2.5 if rsi >= 60 else 0
    if pct_b is not None:
        ext += 3 if pct_b > 0.9 else 1.5 if pct_b > 0.75 else 0
    if vs50 is not None:
        ext += 2 if vs50 > 0.12 else 1 if vs50 > 0.06 else 0
    ext = min(15.0, ext)
    if state == "rolling_over":
        win = "PUT WINDOW — fresh crack at extension"
    elif state == "climax":
        win = "euphoria — right candidate, too early; wait for stall"
    elif state == "breakout":
        win = "momentum igniting — puts forbidden"
    elif state in ("knife", "capitulation", "breakdown", "downtrend"):
        win = "already broke — the entry was earlier"
    elif state in ("pullback", "recovery", "basing"):
        win = "wrong side — dip-buy territory"
    else:                                 # uptrend / unknown
        win = ("extended, no stall — watch" if ext >= 8
               else "not extended")
    return ext, win


def _iv_score(ivhv: Optional[float]) -> Optional[float]:
    """Volatility-discount leg: HV/IV — 1.0 is fair, >1.0 means the
    market sells vol cheaper than the stock delivers."""
    if ivhv is None or ivhv <= 0:
        return None
    hv_over_iv = 1.0 / ivhv
    return (20 if hv_over_iv >= 1.1 else
            15 if hv_over_iv >= 0.95 else
            8 if hv_over_iv >= 0.75 else
            3)                                  # IV ≳1.4×HV — rich


def _chain(sym: str, spot: float, hedge_otm: float = 0.75
           ) -> dict[str, Any]:
    """Far-expiry chain → ATM IV + liquidity + the actual ~25% OTM
    hedge contract (exact strike/expiry/mid — the user's caution:
    compare contracts, not headline IV)."""
    try:
        import yfinance as yf
        t = yf.Ticker(sym)
        exps = t.options or ()
        if not exps:
            return {}
        def _d(e):
            return (e if isinstance(e, date) else
                    date.fromisoformat(str(e)[:10]))
        days = {e: (_d(e) - date.today()).days for e in exps}
        far = max((e for e, d in days.items() if d >= 300),
                  key=days.get, default=None)
        if far is None:
            far = max(exps, key=days.get)
        puts = t.option_chain(far).puts
        if puts is None or puts.empty:
            return {}
        atm = puts[(puts["strike"] > 0.8 * spot)
                   & (puts["strike"] < 1.3 * spot)]
        otm = puts[(puts["strike"] > 0.65 * spot)
                   & (puts["strike"] <= 1.0 * spot)]
        out: dict[str, Any] = {"leaps_expiry": str(far),
                               "leaps_dte": days[far]}
        if not atm.empty:
            ivs = [float(x) for x in atm["impliedVolatility"]
                   if x and float(x) > 0.01]
            ois = [int(x or 0) for x in atm["openInterest"]]
            spr = [(float(r["ask"]) - float(r["bid"]))
                   / float(r["ask"]) for _, r in atm.iterrows()
                   if r.get("ask") and float(r["ask"]) > 0]
            if ivs:
                out["atm_iv"] = sorted(ivs)[len(ivs) // 2]
            out["median_oi"] = (sorted(ois)[len(ois) // 2]
                                if ois else None)
            out["median_spread_pct"] = (round(
                sorted(spr)[len(spr) // 2] * 100, 1)
                if spr else None)
        if not otm.empty:
            # the actual hedge contract at the requested OTM depth
            tgt = hedge_otm * spot
            r = min(otm.to_dict("records"),
                    key=lambda x: abs(x["strike"] - tgt))
            bid, ask = float(r.get("bid") or 0), float(r.get("ask") or 0)
            mid = (bid + ask) / 2 if ask else bid
            out["put"] = {"strike": float(r["strike"]),
                          "mid": round(mid, 2),
                          "iv": float(r.get("impliedVolatility") or 0),
                          "oi": int(r.get("openInterest") or 0),
                          "expiry": str(far),
                          "otm_pct": round(
                              (1 - r["strike"] / spot) * 100, 1)}
        return out
    except Exception as exc:
        logger.debug("chain %s: %s", sym, exc)
        return {}


def _qual(sym: str) -> dict:
    """LTM net income / FCF / dilution from the quarterly journal."""
    from app.database import db
    try:
        rows = db.execute_query(
            "SELECT net_income, free_cf, shares_diluted "
            "FROM fundamental_quarterly WHERE symbol=:s "
            "ORDER BY period_end DESC LIMIT 5", {"s": sym})
    except Exception:
        return {}
    if not rows:
        return {}
    out: dict[str, float] = {}
    ni = [r["net_income"] for r in rows[:4]
          if r.get("net_income") is not None]
    fcf = [r["free_cf"] for r in rows[:4]
           if r.get("free_cf") is not None]
    if ni:
        out["net_income_ltm"] = sum(ni)
    if fcf:
        out["free_cf_ltm"] = sum(fcf)
    if len(rows) >= 5:
        s0, s4 = rows[0].get("shares_diluted"), \
            rows[4].get("shares_diluted")
        if s0 and s4:
            out["dilution_yoy"] = s0 / s4 - 1
    return out


def scan(hedge_target: str = "CRDO", top_n: int = 25,
         with_chains: bool = True) -> dict[str, Any]:
    """Four-bucket hedge scoring over the flywheel universe."""
    from app.database import db
    fly = {r["symbol"]: dict(r) for r in db.execute_query(
        "SELECT symbol, eps_growth, rev_growth, rev_accel, "
        "est_revision_pct, fwd_pe, beat_streak FROM symbol_flywheel")}
    mom = {r["symbol"]: (r.get("momentum_state"),
                         r.get("momentum_detail") or {},
                         r.get("fundamental_state"),
                         r.get("next_earnings_date"))
           for r in db.execute_query(
               "SELECT symbol, momentum_state, momentum_detail, "
               "fundamental_state, next_earnings_date "
               "FROM stocks WHERE momentum_state IS NOT NULL")}
    px = {r["symbol"]: float(r["close"]) for r in db.execute_query(
        "SELECT DISTINCT ON (symbol) symbol, close FROM daily_bars "
        "ORDER BY symbol, date DESC")}
    out = []
    for sym, f in fly.items():
        if sym == hedge_target:
            continue                       # can't hedge target w/ itself
        m = _beta_hv_corr(sym, hedge_target)
        q = _qual(sym)
        parts: dict[str, Any] = {
            "vulnerability": _vulnerability(f, q, sym)}

        hv = m.get("hv20") or m.get("hv60")
        # bucket 2 placeholder — real IV lands in pass 2
        parts["vol_discount"] = None
        parts["convexity"] = None
        corr = m.get("corr_target")
        parts["corr"] = (min(30, max(0, corr * 33)) if corr is not None
                         else None)
        state, det, fund_state, next_earn = \
            mom.get(sym) or (None, {}, None, None)
        ext, win = _setup(state, det)
        parts["extension"] = ext          # the ATH/overbought leg

        out.append({"symbol": sym,
                    "_pre": parts["vulnerability"] + (parts["corr"] or 0)
                            + (ext or 0) * 0.5,
                    "momentum": state, "setup": win,
                    "extension": ext,
                    "rsi": det.get("rsi"),
                    "pct_b": det.get("pct_b"),
                    "dd52w": round(det["dd52w"], 3)
                    if det.get("dd52w") is not None else None,
                    "beta": round(m["beta_qqq"], 2)
                    if m.get("beta_qqq") else None,
                    "hv20": round(hv, 2) if hv else None,
                    "corr": round(corr, 2) if corr is not None else None,
                    "fwd_pe": round(f["fwd_pe"], 0)
                    if f.get("fwd_pe") else None,
                    "parts": parts, "spot": px.get(sym),
                    "fund_state": fund_state,
                    "next_earnings": next_earn})

    # pass 2 — real chains on the shortlist: IV → vol-discount +
    # convexity + liquidity gate + the actual hedge contract
    out.sort(key=lambda r: -r["_pre"])
    cands = out[:top_n] if with_chains else []
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {c["symbol"]: ex.submit(_chain, c["symbol"],
                                       c.get("spot") or 0)
                for c in cands if c.get("spot")}
        for c in cands:
            fu = futs.get(c["symbol"])
            ch = fu.result() if fu else {}
            c["chain"] = ch or None
            iv = ch.get("atm_iv")
            if iv and c.get("hv20"):
                ivhv = iv / c["hv20"]
                c["atm_iv"], c["iv_hv"] = round(iv, 3), round(ivhv, 2)
                c["parts"]["vol_discount"] = _iv_score(ivhv)
                if c.get("beta"):
                    c["convexity"] = round(
                        c["beta"] * c["hv20"] / iv, 2)
                    c["parts"]["convexity"] = min(
                        20, max(0, (c["convexity"] - 1) / 3 * 20))
            oi, spr = ch.get("median_oi"), ch.get("median_spread_pct")
            c["thin_chain"] = bool(
                (oi is not None and oi < 25)
                or (spr is not None and spr > 25))
            if ch.get("put"):
                c["put"] = ch["put"]
                c["hedge_roi"] = _hedge_roi(c["spot"], ch["put"])
            c["score"] = round(sum(v for v in c["parts"].values()
                                   if v is not None), 1)
    for c in out:
        if "score" not in c:
            c["score"] = c.pop("_pre")
        c.pop("_pre", None)
        c["tier"] = ("prime" if c["score"] >= 65 else
                     "watch" if c["score"] >= 45 else
                     "poor" if c["score"] >= 30 else "no")
        # narrative-risk gate — an improving story can gap +25% on one
        # headline (contract / partnership / guidance) no matter how
        # extended the tape. Gate, not a score adjustment.
        from app.signals.put_entry import narrative_risk
        nr = narrative_risk(c.get("fund_state"),
                            fly.get(c["symbol"]) or {},
                            sym=c["symbol"],
                            next_earnings=c.get("next_earnings"))
        c["narrative_risk"] = nr["flag"]
        if nr["flag"] == "high":
            c["narrative_reasons"] = nr["reasons"]
            if c["tier"] == "prime":
                c["tier"] = "watch"
        # option economics verdict — breakeven on the actual contract
        roi = (c.get("hedge_roi") or {}).get("roi")
        if roi is not None:
            c["ev_verdict"] = ("economics work" if roi >= 1.0 else
                               "marginal" if roi >= 0.5 else
                               "premium too rich")
        if c.get("thin_chain") and c["tier"] == "prime":
            c["tier"] = "watch"
    out.sort(key=lambda r: -r["score"])
    try:
        from app.signals import theme_rotation
        _env = theme_rotation.current()
        env = {"score": _env["score"], "band": _env["band"],
               "data_partial": _env["data_partial"]}
    except Exception:
        env = None
    return {"as_of": str(date.today()), "hedge_target": hedge_target,
            "theme_rotation": env,
            "scored": len(out), "with_chains": len(cands),
            "prime": [r["symbol"] for r in out if r["tier"] == "prime"],
            "rows": out[:30]}


def _hedge_roi(spot: float, put: dict,
               drop: float = -0.30) -> Optional[dict]:
    """Expected hedge ROI on a −30% move — BS-priced, with a +15% vol
    bump (crashes expand IV) and ~90d of decay passing during the
    decline. This is the decisive test: payout ÷ premium."""
    from app.options.leaps import _bs_value
    if not spot or not put.get("mid") or not put.get("iv"):
        return None
    K, mid, iv = put["strike"], put["mid"], put["iv"]
    T = (date.fromisoformat(put["expiry"]) - date.today()).days / 365
    if T <= 0:
        return None
    # post-shock: spot down 30%, IV +15% (crash vol expansion),
    # ~3 months of time consumed during the decline
    post_iv = min(iv * 1.15, 3.0)
    post_T = max(T - 0.25, 0.05)
    new_val = _bs_value(spot * (1 + drop), K, post_T, RISK_FREE,
                        post_iv, call=False)
    if new_val is None or mid <= 0:
        return None
    return {"premium": round(mid * 100, 0),
            "value_after": round(new_val * 100, 0),
            "roi": round(new_val / mid - 1, 2)}


def _corr_move(sym: str, target: str) -> Optional[float]:
    """Expected move in `sym` per +1 move in `target` — the regression
    beta of sym on target (corr × σi/σt), not beta vs QQQ."""
    a, b = _bars(sym), _bars(target)
    ra, rb = _returns(a), _returns(b)
    common = sorted(set(ra) & set(rb))[:60]
    if len(common) < 20:
        return None
    xs, ys = [rb[d] for d in common], [ra[d] for d in common]
    mx, my = mean(xs), mean(ys)
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / len(xs)
    var = sum((x - mx) ** 2 for x in xs) / len(xs)
    return cov / var if var else None


def hedge_roi_table(symbols: list[str], target: str = "CRDO",
                    drop: float = -0.30, otm: float = 0.75
                    ) -> list[dict]:
    """The user's decisive test, on exact contracts — but scored under
    a CORRELATED scenario, because a hedge is paid for the book's
    fall, not its own: given target −30%, each candidate moves by its
    regression beta to target (corr×σi/σt). QQQ pays on QQQ's move,
    which is why single-name convexity can beat it for THIS book."""
    rows = []
    todo = list(dict.fromkeys(symbols + ["QQQ", target]))
    px = {s: _bars(s) for s in todo}
    spots = {s: (max(v.items(), key=lambda x: x[0])[1] if v else None)
             for s, v in px.items()}
    betas = {s: (1.0 if s == target else _corr_move(s, target))
             for s in todo}
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {s: ex.submit(_chain, s, spots[s] or 0, otm)
                for s in todo if spots.get(s)}
        for s in todo:
            spot = spots.get(s)
            if not spot:
                continue
            ch = futs.get(s).result() if s in futs else {}
            put = (ch or {}).get("put")
            beta = betas.get(s)
            # the name's expected move when the book's exposure drops
            exp_move = (beta or 1.0) * drop
            roi = _hedge_roi(spot, put, exp_move) if put else None
            raw = _hedge_roi(spot, put, drop) if put else None
            rows.append({"symbol": s, "spot": round(spot, 2),
                         "beta_to_target": round(beta, 2)
                         if beta is not None else None,
                         "exp_move": round(exp_move * 100, 1)
                         if beta is not None else None,
                         "put": put, "hedge_roi": roi,
                         "raw_roi_same_drop": roi and raw,
                         "benchmark": s in ("QQQ", target)})
    rows.sort(key=lambda r: -(r["hedge_roi"]["roi"]
                              if r.get("hedge_roi") else -9))
    return rows


ENGINE_VERSION = "hedge_v1"


def journal(hedge_target: str = "CRDO", top_n: int = 25
            ) -> dict[str, Any]:
    """Nightly snapshot — freeze the scored universe + exact-contract
    ROI rows so tomorrow diffs against a stored yesterday and matured
    snapshots get graded on 'did it pay when the target fell'.
    Benchmarks (QQQ + target) journal too — they're the baseline."""
    from app.database import db
    today = date.today()
    res = scan(hedge_target, top_n=top_n)
    rows = res["rows"]

    # beta_to_target for the scored names — grading needs the
    # expected-move denominator; compute once here, not per-row in scan
    for r in rows:
        b = _corr_move(r["symbol"], hedge_target)
        r["beta_to_target"] = round(b, 2) if b is not None else None
        if r.get("put") and b is not None:
            # correlated-scenario ROI — the real hedge math
            r["hedge_roi_corr"] = _hedge_roi(
                r["spot"], r["put"], b * -0.30)

    # benchmarks ride along so the journal carries its own baseline
    bench = hedge_roi_table([], hedge_target)   # QQQ + target only
    for b in bench:
        rows.append({"symbol": b["symbol"], "tier": "benchmark",
                     "score": None, "spot": b.get("spot"),
                     "beta": None, "hv20": None, "corr": None,
                     "beta_to_target": b.get("beta_to_target"),
                     "momentum": None, "parts": {},
                     "put": b.get("put"),
                     "hedge_roi_corr": b.get("hedge_roi"),
                     "thin_chain": None, "fwd_pe": None,
                     "chain": None, "convexity": None,
                     "atm_iv": (b.get("put") or {}).get("iv"),
                     "iv_hv": None})

    wrote = 0
    for r in rows:
        import json
        db.execute_update(
            "INSERT INTO hedge_universe_snapshots"
            " (snap_date, symbol, hedge_target, engine_version, score,"
            " tier, spot, beta_qqq, hv20, atm_iv, iv_hv, convexity,"
            " corr_target, beta_to_target, parts, put, hedge_roi,"
            " thin_chain, extension, setup)"
            " VALUES (:d,:s,:t,:v,:sc,:ti,:sp,:b,:hv,:iv,:ih,:cx,:co,"
            " :bt,CAST(:pa AS jsonb),CAST(:pu AS jsonb),"
            " CAST(:ro AS jsonb),:th,:ex,:su)"
            " ON CONFLICT (snap_date, symbol, hedge_target) DO UPDATE"
            " SET score=EXCLUDED.score, tier=EXCLUDED.tier,"
            " spot=EXCLUDED.spot, beta_qqq=EXCLUDED.beta_qqq,"
            " hv20=EXCLUDED.hv20, atm_iv=EXCLUDED.atm_iv,"
            " iv_hv=EXCLUDED.iv_hv, convexity=EXCLUDED.convexity,"
            " corr_target=EXCLUDED.corr_target,"
            " beta_to_target=EXCLUDED.beta_to_target,"
            " parts=CAST(:pa AS jsonb), put=CAST(:pu AS jsonb),"
            " hedge_roi=CAST(:ro AS jsonb),"
            " thin_chain=EXCLUDED.thin_chain,"
            " extension=EXCLUDED.extension, setup=EXCLUDED.setup",
            {"d": today, "s": r["symbol"], "t": hedge_target,
             "v": ENGINE_VERSION, "sc": r.get("score"),
             "ti": r.get("tier"), "sp": r.get("spot"),
             "b": r.get("beta"), "hv": r.get("hv20"),
             "iv": r.get("atm_iv"), "ih": r.get("iv_hv"),
             "cx": r.get("convexity"), "co": r.get("corr"),
             "bt": r.get("beta_to_target"),
             "pa": json.dumps(r.get("parts") or {}),
             "pu": json.dumps(r.get("put")),
             "ro": json.dumps(r.get("hedge_roi_corr")
                             or r.get("hedge_roi")),
             "th": r.get("thin_chain"),
             "ex": r.get("extension"), "su": r.get("setup")})
        wrote += 1
    return {"snap_date": str(today), "hedge_target": hedge_target,
            "engine_version": ENGINE_VERSION, "journaled": wrote,
            "prime": res.get("prime")}


def grade_snapshots(hedge_target: str = "CRDO") -> dict[str, int]:
    """Forward grading — for snapshots ≥20 trading days old, fill
    ret_20d / target_ret_20d / capture_20d. capture = how much of the
    target's fall the candidate actually mirrored — the honest score
    for 'did the hedge pay when the book fell'."""
    from app.database import db
    rows = db.execute_query(
        "SELECT id, symbol, snap_date FROM hedge_universe_snapshots"
        " WHERE hedge_target=:t AND ret_20d IS NULL"
        " AND snap_date <= :cut", {"t": hedge_target, "cut": (
            date.today() - timedelta(days=28))})
    graded = 0
    for r in rows:
        sym = db.execute_query(
            "SELECT close FROM daily_bars WHERE symbol=:s"
            " AND date > :d ORDER BY date ASC LIMIT 22",
            {"s": r["symbol"], "d": r["snap_date"]})
        tgt = db.execute_query(
            "SELECT close FROM daily_bars WHERE symbol=:s"
            " AND date > :d ORDER BY date ASC LIMIT 22",
            {"s": hedge_target, "d": r["snap_date"]})
        base_s = db.execute_query(
            "SELECT close FROM daily_bars WHERE symbol=:s"
            " AND date <= :d ORDER BY date DESC LIMIT 1",
            {"s": r["symbol"], "d": r["snap_date"]})
        base_t = db.execute_query(
            "SELECT close FROM daily_bars WHERE symbol=:s"
            " AND date <= :d ORDER BY date DESC LIMIT 1",
            {"s": hedge_target, "d": r["snap_date"]})
        if len(sym) < 19 or not base_s:
            continue
        ret = sym[min(len(sym) - 1, 20)]["close"] / \
            base_s[0]["close"] - 1
        t_ret = None
        if len(tgt) >= 19 and base_t:
            t_ret = tgt[min(len(tgt) - 1, 20)]["close"] / \
                base_t[0]["close"] - 1
        capture = (ret / t_ret if t_ret and abs(t_ret) > 0.001
                   else None)
        db.execute_update(
            "UPDATE hedge_universe_snapshots SET ret_20d=:r,"
            " target_ret_20d=:t, capture_20d=:c WHERE id=:i",
            {"r": round(ret, 4), "t": round(t_ret, 4)
             if t_ret is not None else None,
             "c": round(capture, 2) if capture is not None else None,
             "i": r["id"]})
        graded += 1
    return {"graded": graded, "hedge_target": hedge_target}
