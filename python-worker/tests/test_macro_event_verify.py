"""pending_due / poll_due — the hourly due-print watcher.

Semantics: a scheduled macro print is "pending" while its date has
arrived (baseline or provider-rescheduled) but no `actual` has been
captured. The poller must only hit the provider when pending exists.
"""
import datetime as dt
from unittest.mock import patch

import pytest

from app.market_events import verify
from app.market_events.calendar import _CPI_DATES, _ET

TODAY = dt.datetime(2026, 10, 14, 20, 0, tzinfo=dt.timezone.utc)


def _patch_db(rows):
    return patch.object(verify.db, "execute_query", return_value=rows)


def test_due_baseline_event_with_no_override_is_pending():
    # Oct-13 CPI in the baseline, no overrides — yesterday's print
    # hasn't landed → pending
    with _patch_db([]):
        pending = verify.pending_due(now=TODAY)
    kinds = {(p["kind"], p["date"]) for p in pending}
    assert ("cpi", "2026-10-13") in kinds
    assert all(p["via"] == "baseline_no_actual" for p in pending)


def test_override_with_actual_covers_baseline():
    # provider row on the baseline date with actual filled → resolved
    rows = [{"kind": "cpi", "event_date": "2026-10-13",
             "original_date": None, "actual": 3.7}]
    with _patch_db(rows):
        pending = verify.pending_due(now=TODAY)
    assert not any(p["kind"] == "cpi" for p in pending)


def test_rescheduled_event_pending_on_provider_date_not_baseline():
    # BLS moved CPI 10-13 → 10-14; provider row has no actual yet →
    # pending on the NEW date; the baseline date must not double-count
    rows = [{"kind": "cpi", "event_date": "2026-10-14",
             "original_date": "2026-10-13", "actual": None}]
    with _patch_db(rows):
        pending = verify.pending_due(now=TODAY)
    cpi = [p for p in pending if p["kind"] == "cpi"]
    assert len(cpi) == 1
    assert cpi[0]["date"] == "2026-10-14"
    assert cpi[0]["via"] == "override_no_actual"


def test_rescheduled_with_actual_is_resolved():
    rows = [{"kind": "cpi", "event_date": "2026-10-14",
             "original_date": "2026-10-13", "actual": 0.6}]
    with _patch_db(rows):
        pending = verify.pending_due(now=TODAY)
    assert not any(p["kind"] == "cpi" for p in pending)


def test_nothing_due_means_no_poll_work():
    # a quiet stretch: no baseline dates in the window → empty pending
    # even if the db explodes
    far = dt.datetime(2026, 8, 20, 20, 0, tzinfo=dt.timezone.utc)
    # sanity: no CPI/PPI/FOMC dates in Aug 16-20 2026 window
    dues = [d for d in _CPI_DATES
            if dt.date(2026, 8, 15) <= d <= dt.date(2026, 8, 20)]
    assert not dues
    with _patch_db([]):
        pending = verify.pending_due(now=far)
    assert pending == []


def test_poll_due_skips_provider_when_nothing_pending():
    with patch.object(verify, "pending_due", return_value=[]), \
         patch.object(verify, "verify_and_store",
                      side_effect=AssertionError("must not fetch")):
        out = verify.poll_due()
    assert out == {"skipped": "no_due_items", "stored": 0}


def test_poll_due_verifies_when_pending():
    fake = {"stored": 3, "rescheduled": 1}
    with patch.object(verify, "pending_due",
                      side_effect=[[{"kind": "cpi", "date": "2026-10-14",
                                     "via": "baseline_no_actual"}], []]), \
         patch.object(verify, "verify_and_store", return_value=fake):
        out = verify.poll_due()
    assert out["stored"] == 3
    assert out["pending_after"] == []


# ------------------------------------------------------------------
# _classify — the fomc/minutes boundary. Regression: FMP emits
# "FOMC Minutes" ~3wk after each decision; it was journaled as
# kind 'fomc' and fed_path rendered a phantom November meeting.
# ------------------------------------------------------------------

def test_fomc_minutes_is_not_a_rate_decision():
    assert verify._classify("FOMC Minutes", "US")[0] == "fomc_minutes"
    assert verify._classify("FOMC Meeting Minutes", "US")[0] == \
        "fomc_minutes"


def test_rate_decision_names_still_classify_fomc():
    assert verify._classify("Fed Interest Rate Decision", "US")[0] == \
        "fomc"
    assert verify._classify("FOMC Statement", "US")[0] == "fomc"
    assert verify._classify("FOMC Economic Projections", "US")[0] == \
        "fomc"


def test_non_us_minutes_are_ignored():
    # RBA/ECB minutes exist on the same feed — country gate drops them
    assert verify._classify("RBA Meeting Minutes", "AU") is None


def test_minutes_override_never_adds_a_fomc_event():
    # a journaled fomc_minutes override must surface as its own kind —
    # upcoming_macro_events must still see exactly one upcoming
    # kind=='fomc' entry (the real Dec-9 decision)
    from app.market_events import calendar
    now = dt.datetime(2026, 11, 13, 20, 0, tzinfo=dt.timezone.utc)
    overrides = {
        "fomc_minutes": {
            "2026-11-18": {"kind": "fomc_minutes", "name": "FOMC minutes",
                           "event_date": "2026-11-18", "status": "confirmed",
                           "time_et": "14:00", "severity": "high",
                           "actual": None, "estimate": None, "prev": None,
                           "source": "fmp", "raw_name": "FOMC Minutes"},
        },
    }
    with patch("app.market_events.verify.load_overrides",
               return_value=overrides), \
         _patch_db([]):
        evts = calendar.upcoming_macro_events(120, now=now)
    fomc = [e for e in evts if e["kind"] == "fomc" and e["days_away"] > 0]
    assert [e["date"] for e in fomc] == ["2026-12-09"]
    mins = [e for e in evts if e["kind"] == "fomc_minutes"]
    assert [e["date"] for e in mins] == ["2026-11-18"]
