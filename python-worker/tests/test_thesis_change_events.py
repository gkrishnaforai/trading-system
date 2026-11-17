"""thesis_change_events — the journal + alert emission in
thesis_health.evaluate(). _journal_change is db-bound, so db is
faked: every execute_* call is captured, the alert-id lookup returns
a fixed row. Contract under test:

  coverage_start      first eval → event row, NO alert
  status_transition   up/down → event row + alert_items row linked
  leg_change          flat status + core hypothesis moved → row, no alert
  optional-only moves → nothing journals
"""
import json
from datetime import date

import app.database as appdb
from app.signals import thesis_health


class _FakeDB:
    def __init__(self):
        self.calls = []

    def execute_query(self, sql, params=None):
        self.calls.append(("q", sql, params))
        if "FROM alert_items WHERE fingerprint" in sql:
            return [{"id": "alert-uuid-1"}]
        return []

    def execute_update(self, sql, params=None):
        self.calls.append(("u", sql, params))
        return 1


def _db(monkeypatch):
    fake = _FakeDB()
    monkeypatch.setattr(appdb, "db", fake)
    return fake


def _hyp(hid="capacity_converts", arch="ai_compute", status="on_track",
         crit="core"):
    return {"id": hid, "archetype": arch, "status": status,
            "criticality": crit, "label": hid.replace("_", " "),
            "checks": [{"metric": "rev_growth", "status": "pass",
                        "note": "rev_growth 0.32 >= 0.20",
                        "hard": True}]}


def _row(status="improving", sd="up"):
    return {"status": status, "status_dir": sd, "score": 3,
            "as_of": date.today().isoformat()}


def _events(fake):
    return [c for c in fake.calls
            if "INTO thesis_change_events" in c[1]]


def _alerts(fake):
    return [c for c in fake.calls
            if "INTO alert_items" in c[1]]


class TestJournalChange:
    def test_coverage_start_journals_no_alert(self, monkeypatch):
        fake = _db(monkeypatch)
        thesis_health._journal_change(
            "NBIS", "ai_compute", _row(status="improving", sd="new"),
            [_hyp()], None, [], [], {"drivers": []})
        ev = _events(fake)
        assert len(ev) == 1 and not _alerts(fake)
        assert ev[0][2]["k"] == "coverage_start"
        assert ev[0][2]["ps"] is None

    def test_transition_up_journals_and_alerts(self, monkeypatch):
        fake = _db(monkeypatch)
        hc = [{"id": "capacity_converts", "archetype": "ai_compute",
               "from": "mixed", "to": "on_track"}]
        thesis_health._journal_change(
            "NBIS", "ai_compute", _row("improving", "up"), [_hyp()],
            "mixed", hc, [], {"drivers": []})
        ev, al = _events(fake), _alerts(fake)
        assert len(ev) == 1 and len(al) == 1
        assert ev[0][2]["k"] == "status_transition"
        assert ev[0][2]["aid"] == "alert-uuid-1"   # journal↔alert link
        p = al[0][2]
        assert p["di"] == "UP" and p["mat"] == "MEDIUM" \
            and p["pr"] == 110
        assert "mixed → improving" in p["t"]
        assert p["fp"].startswith("thesis_change:NBIS:mixed:improving:")
        det = json.loads(p["de"])
        assert det["thesis"] == {"before": "mixed", "after": "improving"}
        assert det["hyp_changes"] == hc

    def test_broken_transition_is_high_priority(self, monkeypatch):
        fake = _db(monkeypatch)
        hc = [{"id": "credit_quality", "archetype": "lender",
               "from": "deteriorating", "to": "broken"}]
        hyps = [_hyp("credit_quality", "lender", "broken")]
        thesis_health._journal_change(
            "UPST", "lender", _row("broken", "down"), hyps,
            "deteriorating", hc, [], {"drivers": []})
        p = _alerts(fake)[0][2]
        assert p["di"] == "DOWN" and p["mat"] == "HIGH" and p["pr"] == 160

    def test_fatal_veto_alerts_high(self, monkeypatch):
        fake = _db(monkeypatch)
        vetoes = [{"id": "financing_break", "cap": "broken",
                   "flag": "burn >8x leverage", "fatal": True}]
        thesis_health._journal_change(
            "IREN", "ai_compute", _row("broken", "down"), [_hyp()],
            "mixed", [], vetoes, {"drivers": []})
        p = _alerts(fake)[0][2]
        assert p["mat"] == "HIGH" and p["pr"] == 160
        assert "burn" in p["t"]

    def test_leg_change_flat_status_journals_no_alert(self, monkeypatch):
        fake = _db(monkeypatch)
        hc = [{"id": "capacity_converts", "archetype": "ai_compute",
               "from": "unknown", "to": "on_track"}]
        thesis_health._journal_change(
            "NBIS", "ai_compute", _row("improving", "flat"), [_hyp()],
            "improving", hc, [], {"drivers": []})
        ev = _events(fake)
        assert len(ev) == 1 and not _alerts(fake)
        assert ev[0][2]["k"] == "leg_change"
        evd = json.loads(ev[0][2]["e"])
        assert evd[0]["hypothesis_id"] == "capacity_converts"
        assert evd[0]["checks"][0]["note"].startswith("rev_growth")

    def test_optional_only_change_journals_nothing(self, monkeypatch):
        fake = _db(monkeypatch)
        hc = [{"id": "strategic_segment", "archetype": "ai_compute",
               "from": "unknown", "to": "on_track"}]
        hyps = [_hyp("strategic_segment", crit="optional")]
        thesis_health._journal_change(
            "NBIS", "ai_compute", _row("improving", "flat"), hyps,
            "improving", hc, [], {"drivers": []})
        assert not _events(fake) and not _alerts(fake)

    def test_flat_no_changes_journals_nothing(self, monkeypatch):
        fake = _db(monkeypatch)
        thesis_health._journal_change(
            "NBIS", "ai_compute", _row("improving", "flat"), [_hyp()],
            "improving", [], [], {"drivers": []})
        assert not _events(fake) and not _alerts(fake)

    def test_evidence_snapshot_only_changed_legs(self, monkeypatch):
        fake = _db(monkeypatch)
        hyps = [_hyp("capacity_converts"),
                _hyp("funding_contained", status="unknown")]
        hc = [{"id": "capacity_converts", "archetype": "ai_compute",
               "from": "unknown", "to": "on_track"}]
        thesis_health._journal_change(
            "NBIS", "ai_compute", _row("improving", "flat"), hyps,
            "improving", hc, [], {"drivers": []})
        evd = json.loads(_events(fake)[0][2]["e"])
        assert len(evd) == 1
        assert evd[0]["hypothesis_id"] == "capacity_converts"
