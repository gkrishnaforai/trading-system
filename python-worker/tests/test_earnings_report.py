from datetime import date
from app.signals import earnings_report as er


def _stub(monkeypatch, *, print_row=None, watch_row=None,
          quarters=None, fly=None, drivers=None, stock=None,
          prior=None):
    queries = {
        "FROM stocks": [stock or {"symbol": "PLTR",
                                  "company_name": "Palantir Tech",
                                  "sector": "Software",
                                  "market_cap": 442e9}],
        "FROM earnings_data WHERE": [print_row] if print_row else [],
        "FROM earnings_watch WHERE": [watch_row] if watch_row else [],
        "FROM driver_commitments": drivers or [],
        "FROM fundamental_quarterly": quarters or [],
        "FROM symbol_flywheel": [fly] if fly else [],
        "FROM research_runs": [],
        "FROM earnings_data ed": prior or [],
    }

    def fake_q(sql, p=None):
        for k, rows in queries.items():
            if k in sql:
                return rows
        return []

    monkeypatch.setattr(er, "_q", fake_q)


def test_build_compose_full_report(monkeypatch):
    _stub(
        monkeypatch,
        print_row={"earnings_date": date(2026, 11, 3),
                   "eps_estimate": 0.41, "eps_actual": 0.44,
                   "revenue_estimate": 2.18e9, "revenue_actual": 2.31e9,
                   "surprise_percentage": 7.3},
        watch_row={"verdict": "improving",
                   "thesis_before": "on_track",
                   "thesis_after": "improving",
                   "detail": {"surprise_pct": 7.3,
                              "rev_surprise_pct": 5.96,
                              "narrative": "beat on all lines"},
                   "surprise_pct": 7.3},
        quarters=[
            {"period_end": "2026-09-30", "revenue": 2.31e9,
             "operating_income": 1.08e9, "net_income": 0.8e9,
             "free_cf": 1.2e9, "eps_diluted": 0.44},
            {"period_end": "2026-06-30", "revenue": 2.0e9},
            {"period_end": "2026-03-31", "revenue": 1.8e9},
            {"period_end": "2025-12-31", "revenue": 1.5e9},
            {"period_end": "2025-09-30", "revenue": 1.18e9,
             "operating_income": 0.39e9, "free_cf": 0.6e9},
        ] + [{"period_end": f"{2025 - i//4}-"
              f"{['09-30', '06-30', '03-31', '12-31'][i % 4]}",
              "revenue": 1e9 - i * 1e7} for i in range(1, 17)],
        fly={"rev_growth": 95.9, "fwd_eps_avg": 1.9, "fwd_pe": 60,
             "beat_streak": 4, "num_analysts": 25,
             "fwd_rev_avg": 9.8e9, "gap_score": 71},
        drivers=[{"metric": "revenue", "period": "Q4-26",
                  "value_text": "~$2.65B", "delta_dir": "raised",
                  "consensus_pct": 7.7}],
        prior=[{"earnings_date": date(2026, 8, 3), "eps_actual": 0.3,
                "verdict": "improving", "report_version": 1}],
    )
    rep = er.build("pltr", date(2026, 11, 3))
    assert rep is not None
    assert rep["quarter_label"] == "Q3 2026"
    assert rep["verdict"] == "improving"
    assert "Palantir" in rep["headline"]
    hl = {h["metric"]: h for h in rep["highlights"]}
    assert abs(hl["EPS"]["delta_pct"] - 7.3) < 0.5
    assert hl["Revenue"]["delta_pct"] > 5
    assert hl["Revenue"]["unit"] == "$B"
    assert rep["growth"]["quarter_yoy"] > 90
    assert rep["quality"]["operating_margin"] > 40
    assert rep["quality"]["operating_margin_yoy_pp"] > 0
    assert rep["expectations"]["fwd_eps_avg"] == 1.9
    assert rep["thesis"] == {"before": "on_track",
                            "after": "improving"}
    assert rep["takeaways"][0].startswith("Palantir")
    assert rep["prior_prints"][0]["earnings_date"] == "2026-08-03"


def test_build_returns_none_without_print(monkeypatch):
    _stub(monkeypatch)
    assert er.build("PLTR", date(2026, 11, 3)) is None


def test_quarter_label_boundaries():
    assert er._quarter_label(date(2026, 11, 3)) == "Q3 2026"
    assert er._quarter_label(date(2026, 2, 10)) == "Q4 2025"
    assert er._quarter_label(date(2026, 5, 6)) == "Q1 2026"
    assert er._quarter_label(date(2026, 8, 4)) == "Q2 2026"


def test_journal_appends_versions(monkeypatch):
    _stub(monkeypatch,
          print_row={"earnings_date": date(2026, 11, 3),
                     "eps_estimate": 0.41, "eps_actual": 0.44},
          watch_row={"verdict": "improving", "detail": {},
                     "surprise_pct": 7.3})
    inserts = []
    calls = {"n": 0}

    def fake_q(sql, p=None):
        if "MAX(version)" in sql:
            calls["n"] += 1
            return [{"v": calls["n"]}]
        return _q_default(sql, p)

    def _q_default(sql, p=None):
        for k, rows in {
            "FROM stocks": [{"symbol": "PLTR", "market_cap": 1e9}],
            "FROM earnings_data WHERE": [
                {"earnings_date": date(2026, 11, 3),
                 "eps_estimate": 0.41, "eps_actual": 0.44}],
            "FROM earnings_watch WHERE": [
                {"verdict": "improving", "detail": {}}],
        }.items():
            if k in sql:
                return rows
        return []

    monkeypatch.setattr(er, "_q", fake_q)
    monkeypatch.setattr(er, "_u",
                        lambda sql, p=None: inserts.append(p))
    r1 = er.journal("PLTR", date(2026, 11, 3))
    r2 = er.journal("PLTR", date(2026, 11, 3))
    assert r1["version"] == 1 and r2["version"] == 2
    assert len(inserts) == 2
    assert inserts[0]["v"] == 1 and inserts[1]["v"] == 2
