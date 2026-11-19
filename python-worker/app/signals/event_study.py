"""Earnings event study — how prints actually traded afterward.

Deterministic: joins earnings_watch (print + surprise + verdict) to
daily_bars and measures forward returns at +1/+5/+20/+60d from the
close on/after the print date. Grouped by surprise sign and by
verdict — the evidence the engine cites when sizing event risk.

n < 8 in a bucket → 'low_evidence': true — with tiny samples the
median is anecdote, not signal.
"""

from typing import Any

from app.database import db

HORIZONS = (1, 5, 20, 60)
MIN_SAMPLE = 8


def _forward_bars(sym: str, after: str, n: int) -> list[float]:
    return [float(r["close"]) for r in db.execute_query(
        "SELECT close FROM daily_bars WHERE symbol=:s AND date >= :d"
        " ORDER BY date LIMIT :n",
        {"s": sym, "d": after, "n": n + 1})]


def _stats(rets: list[float]) -> dict:
    if not rets:
        return {"n": 0, "low_evidence": True}
    rets = sorted(rets)
    n = len(rets)
    return {"n": n, "low_evidence": n < MIN_SAMPLE,
            "median_pct": round(rets[n // 2] * 100, 1),
            "avg_pct": round(sum(rets) / n * 100, 1),
            "pct_positive": round(sum(1 for r in rets if r > 0)
                                  / n * 100, 0),
            "worst_pct": round(rets[0] * 100, 1),
            "best_pct": round(rets[-1] * 100, 1)}


def _bucket(eps_surprise: float | None) -> str:
    if eps_surprise is None:
        return "unknown"
    if eps_surprise >= 5:
        return "strong beat (≥5%)"
    if eps_surprise > 0:
        return "small beat (0-5%)"
    if eps_surprise <= -5:
        return "strong miss (≤-5%)"
    return "small miss (-5-0%)"


def run(sym: str | None = None) -> dict[str, Any]:
    p: dict = {}
    sql = ("SELECT symbol AS stock_symbol, earnings_date, verdict,"
           "       surprise_pct, eps_actual"
           " FROM earnings_watch"
           " WHERE earnings_date IS NOT NULL")
    if sym:
        sql += " AND symbol=:s"
        p["s"] = sym.upper()
    sql += " ORDER BY earnings_date"
    rows = db.execute_query(sql, p)

    by_bucket: dict[str, dict[int, list]] = {}
    by_verdict: dict[str, dict[int, list]] = {}
    events = []
    for r in rows:
        sym_r, d = r["stock_symbol"], str(r["earnings_date"])[:10]
        bars = _forward_bars(sym_r, d, max(HORIZONS))
        if len(bars) < 2:
            continue
        base = bars[0]
        rets = {h: (bars[h] / base - 1)
                for h in HORIZONS if len(bars) > h}
        events.append({
            "symbol": sym_r, "date": d,
            "verdict": r.get("verdict"),
            "surprise_pct": r.get("surprise_pct"),
            "returns": {f"{h}d": round(v * 100, 1)
                        for h, v in rets.items()}})
        b = _bucket(r.get("surprise_pct"))
        v = str(r.get("verdict") or "unknown")
        for h, ret in rets.items():
            by_bucket.setdefault(b, {}).setdefault(h, []).append(ret)
            by_verdict.setdefault(v, {}).setdefault(h, []).append(ret)

    return {
        "symbols": len({e["symbol"] for e in events}),
        "events_n": len(events),
        "by_surprise": {
            b: {f"{h}d": _stats(v) for h, v in sorted(hz.items())}
            for b, hz in by_bucket.items()},
        "by_verdict": {
            v: {f"{h}d": _stats(rets) for h, rets in sorted(hz.items())}
            for v, hz in by_verdict.items()},
        "recent": events[-10:],
        "method": "post-print close-to-close returns by surprise bucket",
    }
