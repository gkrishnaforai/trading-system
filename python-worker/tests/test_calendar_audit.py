"""calendar_audit diff logic — pure functions, no DB.

The audit's job is reporting what moved between weekly snapshots;
the pairing rules (a delete+insert of the same kind+name is a MOVE,
not two changes) are what keep the digest honest.
"""
from app.market_events.audit import _diff_earnings, _diff_macro


def _e(kind, d, name=None):
    return {"kind": kind, "date": d, "name": name or kind.upper()}


def test_macro_moved_event_pairs_not_duplicates():
    before = [_e("fomc", "2026-12-09", "FOMC rate decision"),
              _e("cpi", "2026-12-10", "CPI inflation")]
    after = [_e("fomc", "2026-12-10", "FOMC rate decision"),
             _e("cpi", "2026-12-10", "CPI inflation")]
    out = _diff_macro(before, after)
    assert len(out) == 1
    assert out[0]["change_type"] == "moved"
    assert out[0]["event_kind"] == "fomc"
    assert out[0]["old_date"] == "2026-12-09"
    assert out[0]["new_date"] == "2026-12-10"


def test_macro_added_and_removed():
    before = [_e("cpi", "2026-11-10", "CPI inflation")]
    after = [_e("fomc_minutes", "2026-11-18", "FOMC minutes")]
    out = _diff_macro(before, after)
    kinds = {(c["event_kind"], c["change_type"]) for c in out}
    assert kinds == {("cpi", "removed"), ("fomc_minutes", "added")}


def test_macro_no_changes_is_empty():
    evts = [_e("fomc", "2026-12-09"), _e("nfp", "2026-12-04")]
    assert _diff_macro(evts, evts) == []


def test_macro_same_kind_different_names_not_a_move():
    # two CPI prints in window; if names differ the removed/added
    # pair must NOT collapse into a phantom move
    before = [_e("cpi", "2026-11-10", "CPI inflation")]
    after = [_e("ppi", "2026-11-13", "PPI producer prices")]
    out = _diff_macro(before, after)
    assert {c["change_type"] for c in out} == {"removed", "added"}


def test_earnings_moved_added_removed():
    before = {"NVDA": "2026-11-17", "AMD": None, "MU": "2026-12-16"}
    after = {"NVDA": "2026-11-18", "AMD": "2027-01-27", "MU": None}
    out = _diff_earnings(before, after)
    got = {c["symbol"]: c for c in out}
    assert got["NVDA"]["change_type"] == "moved"
    assert got["NVDA"]["old_date"] == "2026-11-17"
    assert got["NVDA"]["new_date"] == "2026-11-18"
    assert got["AMD"]["change_type"] == "added"
    assert got["MU"]["change_type"] == "removed"


def test_earnings_unchanged_and_new_symbol():
    before = {"NVDA": "2026-11-17"}
    after = {"NVDA": "2026-11-17", "TSM": "2027-01-15"}
    out = _diff_earnings(before, after)
    assert len(out) == 1
    assert out[0]["symbol"] == "TSM"
    assert out[0]["change_type"] == "added"


def test_first_run_everything_is_added_not_moved():
    # empty baseline → every dated entry is an add, never a move
    out = _diff_earnings({}, {"NVDA": "2026-11-17", "AMD": None})
    assert out == [{"symbol": "NVDA", "change_type": "added",
                    "old_date": None, "new_date": "2026-11-17"}]
