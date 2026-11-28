"""Filing narrative (Phase C) — section splitting, the verbatim-
grounding gate, and the extract→journal→evidence flow."""
from __future__ import annotations

from app.signals import filing_narrative as N


def _filing_text(form="10-Q"):
    """TOC + body: headers appear twice; body follows the LAST one."""
    body_mda = ("Revenue increased 28% driven by demand. " * 40)
    body_risk = ("We face supply concentration risk. " * 40)
    if form == "10-Q":
        return (
            "Item 1. Financial Statements Item 2. Management's "
            "Discussion and Analysis Item 1A. Risk Factors "
            "PART I Item 1. Financial Statements [tables] "
            "Item 2. Management's Discussion and Analysis "
            + body_mda +
            " Item 3. Quantitative and Qualitative Disclosures x"
            " PART II Item 1. Legal Proceedings y "
            "Item 1A. Risk Factors " + body_risk +
            " Item 2. Unregistered Sales z")
    return (
        "Item 1A. Risk Factors Item 7. Management's Discussion "
        "Item 1. Business x Item 1A. Risk Factors " + body_risk +
        " Item 2. Properties y Item 7. Management's Discussion "
        "and Analysis " + body_mda + " Item 8. Financial "
        "Statements z")


def test_split_10q_sections_uses_last_occurrence():
    """The TOC lists every header — splitting must land on the BODY
    (last occurrence), not the table of contents."""
    s = N._split_sections(_filing_text("10-Q"), "10-Q")
    assert set(s) == {"mda", "risk_factors"}
    assert "Revenue increased 28%" in s["mda"]
    assert "supply concentration" in s["risk_factors"]
    assert "Unregistered" not in s["risk_factors"]   # ends at next item


def test_split_10k_item7_and_1a():
    s = N._split_sections(_filing_text("10-K"), "10-K")
    assert set(s) == {"mda", "risk_factors"}
    assert "Revenue increased" in s["mda"]


def test_split_returns_empty_when_no_sections():
    assert N._split_sections("no items here at all " * 50, "10-Q") == {}


def test_split_rejects_stub_sections():
    """A header followed by <400 chars isn't a body — it's a stray
    TOC-style match; don't emit a 'section' for it."""
    text = "Item 2. Management's Discussion and Analysis too short " \
           + "Item 3. Other " + "padding " * 100
    assert "mda" not in N._split_sections(text, "10-Q")


def test_grounding_gate_drops_paraphrase():
    body = "the quick brown fox " * 30
    ok = {"type": "operating_trend", "text": "claim",
          "quote": "the quick brown fox", "direction": "tailwind"}
    bad = dict(ok, quote="a lazy dog that was never written")
    assert N._valid(ok, body) is None
    assert N._valid(bad, body) == "quote not verbatim in section"


def test_valid_rejects_unknown_type_and_empty_text():
    body = "text " * 100
    assert N._valid({"type": "price_target", "text": "x",
                     "quote": "text"}, body) == "unknown claim type"
    assert N._valid({"type": "risk_factor", "text": "  ",
                     "quote": "text"}, body) == "empty claim text"


def test_extract_filing_no_doc_journals_status(monkeypatch):
    """Fetch failure → status row, no extraction attempted."""
    from app.providers import sec_edgar
    monkeypatch.setattr(sec_edgar, "filing_document", lambda *a: None)
    db = _FakeDB()
    out = N.extract_filing(db, {
        "accession_number": "a1", "symbol": "X", "cik": "1",
        "form": "10-Q", "primary_document": "x.htm"})
    assert out["status"] == "no_doc"
    j = [p for s, p in db.updates
         if "filing_narratives" in s][0]
    assert j["st"] == "no_doc"


def test_extract_filing_full_flow(monkeypatch):
    """Fetch → sections → LLM → validate → emit → evidence + links
    + lineage. Grounded claims land; paraphrases die."""
    from app.providers import sec_edgar
    from app.signals import narrative_ledger
    from app.utils import lineage as lin
    import app.llm.client as llm
    import json as _json

    monkeypatch.setattr(sec_edgar, "filing_document",
                        lambda *a: _filing_text())
    monkeypatch.setattr(llm, "llm_completion",
                        lambda **kw: _Resp({"claims": [
                            {"type": "operating_trend",
                             "text": "revenue grew on demand",
                             "quote": "Revenue increased 28% driven "
                                      "by demand.",
                             "direction": "tailwind",
                             "metric": "revenue", "value": 2.7e9,
                             "prior_value": None, "period": "FY26 Q3"},
                            {"type": "risk_factor",
                             "text": "made-up risk",
                             "quote": "this quote is not in the filing",
                             "direction": "headwind",
                             "metric": None}]}))
    emitted = []
    monkeypatch.setattr(narrative_ledger, "emit",
                        lambda *a, **k: emitted.append((a, k)) or "nc_1")
    edges = []
    monkeypatch.setattr(lin, "record_edge",
                        lambda ot, oid, it, iid, ds, **kw:
                        edges.append((ot, oid, it, iid, ds)))
    db = _FakeDB()
    out = N.extract_filing(db, {
        "accession_number": "a1", "symbol": "NVDA", "cik": "1",
        "form": "10-Q", "primary_document": "x.htm",
        "filing_date": "2026-11-01",
        "document_url": "https://x"})
    assert out["status"] == "done"
    # mda: grounded claim lands, paraphrase dies. risk_factors: the
    # mda-grounded quote isn't a substring of THAT section — dies too
    assert out["emitted"] == 1
    assert out["dropped"] == 3
    kinds = {a[3] for a, k in emitted}      # claim_type positional
    assert kinds == {"reported_fact"}
    assert all(k["source"].startswith("edgar_10-Q")
               for a, k in emitted)
    assert all(k["status"] == "supported" for a, k in emitted)
    ev = [p for s, p in db.updates if "claim_evidence" in s]
    assert len(ev) == 1 and ev[0]["sec"] == "mda"
    links = [p for s, p in db.updates if "claim_metric_links" in s]
    assert links and links[0]["m"] == "revenue"
    assert edges == [("narrative_claim", "nc_1",
                      "edgar_filing", "a1", "sec_edgar")]


class _Resp:
    """Minimal litellm response stub."""
    def __init__(self, payload: dict):
        import json
        msg = type("M", (), {"content": json.dumps(payload)})
        self.choices = [type("C", (), {"message": msg})]


class _FakeDB:
    def __init__(self):
        self.updates = []

    def execute_query(self, *a, **k):
        return []

    def execute_update(self, sql, params=None):
        self.updates.append((sql, params))
        return 1
