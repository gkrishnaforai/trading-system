"""Intraday recovery engine — deterministic feature math + signal
priority. Synthetic 5-min bars only; no DB, no network."""
from app.signals import intraday_recovery as ir


def _bar(o, h, l, c, v=1000):
    return {"open": o, "high": h, "low": l, "close": c, "volume": v}


def _rising_session(n=30, start=100.0, step=0.15):
    """Steadily rising session — every close above session VWAP."""
    out = []
    px = start
    for _ in range(n):
        out.append(_bar(px, px + 0.06, px - 0.06, px + step))
        px += step
    return out


def _flat_bench(n=30, px=100.0):
    return [px] * (n + 1)


def _closes(bars):
    return [b["close"] for b in bars]


def test_vwap_cumulative_typical_price():
    bars = [_bar(10, 12, 10, 11, 100), _bar(11, 13, 11, 12, 300)]
    vw = ir._vwap(bars)
    tp1, tp2 = 11.0, 12.0                     # (h+l+c)/3
    assert abs(vw[0] - tp1) < 1e-9
    assert abs(vw[1] - (tp1 * 100 + tp2 * 300) / 400) < 1e-9


def test_consec_counts_from_latest():
    closes = [10, 11, 12, 13]
    vw = [9.5, 9.8, 10.5, 11.9]                # every close above vwap
    assert ir._consec(closes, vw, above=True) == 4
    closes[-1] = 10.0                          # last bar dips below
    assert ir._consec(closes, vw, above=True) == 0
    assert ir._consec(closes, vw, above=False) == 1


def test_rs_is_return_spread_vs_benchmark():
    closes = [100, 101, 102, 103, 104, 105, 106]   # +5 over 6 bars
    bench = [100, 100.5, 100.7, 101, 101.2, 101.5, 101.8]
    rs = ir._rs(closes, bench, 6)
    expected = (106 / 100 - 1 - (101.8 / 100 - 1)) * 100
    assert abs(rs - expected) < 1e-9
    assert ir._rs(closes[:5], bench, 6) is None    # not enough bars


def test_rvol_is_time_of_day_adjusted():
    today = [_bar(10, 10, 10, 10, 5000)] * 3        # cum 15k at idx 2
    hist = [[_bar(10, 10, 10, 10, 4000)] * 6,       # cum@idx2 = 12k
            [_bar(10, 10, 10, 10, 6000)] * 6]       # cum@idx2 = 18k
    rvol = ir._rvol(today, hist)
    # avg cum at same slot = (12000+18000)/2 = 15000 → 1.0
    assert abs(rvol - 1.0) < 1e-9
    assert ir._rvol(today, []) is None


def test_data_blocked_on_thin_session():
    res = ir._eval_symbol("X", _rising_session(3), {"SMH": _flat_bench()},
                          60, True, 18, ir._eng())
    assert res["signal"] == "DATA_BLOCKED"


def test_data_blocked_without_benchmark():
    res = ir._eval_symbol("X", _rising_session(30), {},
                          60, True, 18, ir._eng())
    assert res["signal"] == "DATA_BLOCKED"


def test_confirmed_recovery_on_sustained_buying():
    sess = _rising_session(40, step=0.12)
    bench = {"SMH": _flat_bench(40), "QQQ": _flat_bench(40)}
    res = ir._eval_symbol("X", sess, bench, 60, True, 18, ir._eng())
    ir._apply_rvol(res, 1.2, ir._eng())
    res = ir._signal(res)
    assert res["signal"] in ("CONFIRMED_RECOVERY", "STRONG_RECOVERY",
                             "IMPROVING")
    assert res["score"] >= 55
    assert res["_ctx"]["consec_up"] >= 3
    assert res["_ctx"]["rs30"]["SMH"] > 0


def test_failed_rebound_below_vwap_broken_or():
    bars = _rising_session(8, step=0.1)          # opening range up
    px = bars[-1]["close"]
    for _ in range(10):                           # then a hard fade
        px -= 0.5
        bars.append(_bar(px + 0.4, px + 0.45, px - 0.05, px))
    bench = {"SMH": _flat_bench(40), "QQQ": _flat_bench(40)}
    res = ir._eval_symbol("X", bars, bench, 20, False, 26, ir._eng())
    ir._apply_rvol(res, 0.9, ir._eng())
    res = ir._signal(res)
    assert res["signal"] == "FAILED_REBOUND"
    assert res["_ctx"]["consec_dn"] >= 2
    assert res["_ctx"]["or"]["broke_below"]


def test_extension_caps_confirmed_at_improving():
    """A vertical last bar can be >3% over VWAP — strong but a chase,
    not a confirmed entry."""
    sess = _rising_session(30, step=0.12)
    last = sess[-1]["close"]
    sess.append(_bar(last, last * 1.045, last, last * 1.04, 5000))
    bench = {"SMH": _flat_bench(40), "QQQ": _flat_bench(40)}
    res = ir._eval_symbol("X", sess, bench, 70, True, 18, ir._eng())
    ir._apply_rvol(res, 1.8, ir._eng())
    res = ir._signal(res)
    if res["_ctx"]["ext_pct"] > 3.0:
        assert res["signal"] not in ("CONFIRMED_RECOVERY",
                                     "STRONG_RECOVERY")


def test_up_8pct_alone_is_not_a_signal():
    """The core contract: a single big move without VWAP hold,
    breadth or structure doesn't pass."""
    sess = [_bar(100, 100.5, 99.5, 100.2, 800)] * 7
    sess.append(_bar(100.2, 109.5, 100.0, 108.5, 4000))   # +8% bar
    bench = {"SMH": _flat_bench(40), "QQQ": _flat_bench(40)}
    res = ir._eval_symbol("X", sess, bench, 30, False, 18, ir._eng())
    ir._apply_rvol(res, None, ir._eng())
    res = ir._signal(res)
    assert res["signal"] in ("WATCH", "IMPROVING", "DATA_BLOCKED")


def test_bars_fetch_uses_symbol_keyed_lookup():
    """The misalignment contract — batch fetch must index columns by
    symbol, never positionally (the SPY-got-$12 bug class)."""
    import inspect
    src = inspect.getsource(ir.refresh_bars)
    assert "df[sym]" in src or "px[sym]" in src
    assert ".iloc[" not in src


def test_load_bars_coerces_decimal(monkeypatch):
    """Postgres NUMERIC returns Decimal — _load_bars must coerce to
    float or _vwap dies on float += Decimal (the 11-11 prod crash)."""
    from decimal import Decimal
    import datetime as dt

    rows = [{"bar_ts": dt.datetime(2026, 11, 11, 9, 30),
             "open": Decimal("10.1"), "high": Decimal("10.2"),
             "low": Decimal("9.9"), "close": Decimal("10.0"),
             "volume": Decimal("1500")}]

    class _DB:
        @staticmethod
        def execute_query(*a, **k):
            return rows

    import app.database
    monkeypatch.setattr(app.database, "db", _DB)
    bars = ir._load_bars("X")
    assert all(isinstance(b[k], float)
               for b in bars
               for k in ("open", "high", "low", "close", "volume"))
    assert abs(ir._vwap(bars)[0] - (10.2 + 9.9 + 10.0) / 3) < 1e-9
