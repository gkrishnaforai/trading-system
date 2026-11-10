"""live_overlay regression tests — the iloc misalignment bug class.

Bug: yf.download drops failed symbols, so a batch DataFrame's
columns are the SUBSET that succeeded. Positional lookup
`closes.iloc[i]` against `enumerate(symbols)` then maps index i
to the wrong symbol — SPY journaled a $12 price from a failed
neighbor and every rel-strength leg divided by garbage.

Two guards: (1) symbol-keyed lookup must produce correct prices
even with missing columns; (2) a repo-wide contract test —
no file that batch-downloads may index results positionally
by symbol order.
"""
import ast
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# ------------------------------------------------------------------
# 1. the misalignment itself — refresh() must map by symbol, not i
# ------------------------------------------------------------------
def _fake_download(symbols_cols: dict[str, float]):
    """Build a yf.download-shaped frame with only `symbols_cols` —
    i.e., the SUCCESSFUL subset; requested-but-failed symbols are
    absent entirely (that's what real download does)."""
    cols = list(symbols_cols)
    idx = pd.to_datetime(["2026-11-10"])
    df = pd.concat({f: pd.DataFrame(
        {s: [v] for s, v in symbols_cols.items()}, index=idx)
        for f in ("Close", "Volume")}, axis=1)
    df.columns = pd.MultiIndex.from_tuples(df.columns)
    return df


def test_refresh_maps_by_symbol_not_position(monkeypatch):
    """3 requested, 1 failed to download — position 2 must NOT be
    assigned symbol 1's price."""
    from app.signals import live_overlay

    # requested: AAA, SPY, JUNK — JUNK absent (download failure)
    df = _fake_download({"AAA": 10.0, "SPY": 750.0})
    fake_yf = types.SimpleNamespace(download=MagicMock(return_value=df))
    monkeypatch.setitem(sys.modules, "yfinance", fake_yf)

    written = {}

    class _DB:
        @staticmethod
        def execute_update(q, p=None):
            if q.strip().startswith("INSERT"):
                written[p["s"]] = p["p"]
            return 1
        execute_query = staticmethod(lambda q, p=None: [])

    monkeypatch.setitem(sys.modules, "app.database",
                        types.SimpleNamespace(db=_DB()))
    monkeypatch.setattr(live_overlay, "ensure_table", lambda: None)
    # db import inside refresh is `from app.database import db`
    import app.database as _adb
    monkeypatch.setattr(_adb, "db", _DB())

    res = live_overlay.refresh(["AAA", "SPY", "JUNK"])
    assert res["updated"] == 2
    assert written.get("SPY") == 750.0, \
        f"SPY got {written.get('SPY')} — positional shift bug"
    assert written.get("AAA") == 10.0
    assert "JUNK" not in written


# ------------------------------------------------------------------
# 2. tape_live math — stitched live close produces sane 0-100 score
# ------------------------------------------------------------------
def test_tape_live_math(monkeypatch):
    """Live close stitched onto bars — rel legs bounded, score in
    range. A poisoned SPY ($12 vs $750) must NOT produce 100."""
    from app.signals import live_overlay

    bars = [{"close": c} for c in
            [100 + i * 0.1 for i in range(61)]]       # gentle uptrend
    spy = [{"close": c} for c in
           [500 - i * 0.05 for i in range(61)]]      # gentle downtrend
    calls = {"n": 0}

    def fake_q(q, p=None):
        calls["n"] += 1
        return spy if "symbol='SPY'" in q else bars

    monkeypatch.setattr(live_overlay, "live_px",
                        lambda s: 110.0 if s == "SYM" else 500.0)
    import app.database as _adb
    monkeypatch.setattr(_adb, "db", types.SimpleNamespace(
        execute_query=staticmethod(fake_q)))
    monkeypatch.setitem(sys.modules, "app.database",
                        types.SimpleNamespace(
                            db=types.SimpleNamespace(
                                execute_query=staticmethod(fake_q))))

    out = live_overlay.tape_live("SYM")
    assert out is not None
    assert 0 <= out["tape_live"] <= 100, \
        f"score {out['tape_live']} out of range — divisor bug"
    assert abs(out["rel1"]) < 0.2, \
        f"rel1 {out['rel1']} absurd — poisoned baseline"


def test_tape_live_none_without_prices(monkeypatch):
    """No live tick → None, never a fabricated score."""
    from app.signals import live_overlay
    monkeypatch.setattr(live_overlay, "live_px", lambda s: None)
    assert live_overlay.tape_live("SYM") is None


# ------------------------------------------------------------------
# 3. repo-wide contract — no positional symbol indexing in batch
#    download consumers. This is the guard that would've caught it.
# ------------------------------------------------------------------
def test_no_positional_symbol_indexing_in_download_consumers():
    root = Path(__file__).resolve().parents[1] / "app"
    offenders = []
    for f in root.rglob("*.py"):
        src = f.read_text()
        if "yf.download" not in src:
            continue
        tree = ast.parse(src)
        # dangerous shape: `.iloc[i]` inside a loop over symbols
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(
                    node.func, ast.Attribute) \
                    and node.func.attr == "__getitem__":
                pass
        # simpler lint: the exact anti-pattern strings
        for pat in ("closes.iloc[i", "vols.iloc[i",
                    "opens.iloc[i", "Close'].iloc[i"):
            if pat in src:
                offenders.append(f"{f.name}: {pat}")
    assert not offenders, \
        f"positional symbol indexing on batch download: {offenders}"
