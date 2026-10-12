from datetime import date

from app.fundamental_intelligence import FundamentalEstimateSnapshot, FundamentalMomentumStore, assess_fundamental_momentum


def test_revision_momentum_is_deterministic():
    rows = [
        FundamentalEstimateSnapshot(symbol="CRDO", as_of=date(2026, 8, 1), fiscal_period="FY27", fiscal_year=2027, eps_estimate=2.80, revenue_estimate=100, eps_growth_estimate=.24, analyst_count=10, provider="test"),
        FundamentalEstimateSnapshot(symbol="CRDO", as_of=date(2026, 8, 15), fiscal_period="FY27", fiscal_year=2027, eps_estimate=2.92, revenue_estimate=104, eps_growth_estimate=.29, analyst_count=11, analysts_up=8, analysts_down=1, provider="test"),
        FundamentalEstimateSnapshot(symbol="CRDO", as_of=date(2026, 9, 1), fiscal_period="FY27", fiscal_year=2027, eps_estimate=3.05, revenue_estimate=110, eps_growth_estimate=.34, analyst_count=13, analysts_up=10, analysts_down=1, provider="test"),
    ]
    result = assess_fundamental_momentum("CRDO", rows)
    assert result.score is not None
    assert result.eps_revision_14d is not None
    assert result.net_revision_breadth > 0
    assert result.label in {"IMPROVING", "STRONG"}


def test_missing_history_does_not_fabricate_momentum():
    row = FundamentalEstimateSnapshot(symbol="CRDO", as_of=date(2026, 9, 1), fiscal_period="FY27", fiscal_year=2027, eps_estimate=3.05, provider="test")
    result = assess_fundamental_momentum("CRDO", [row])
    assert result.score is None
    assert result.label == "UNAVAILABLE"


def test_persisted_momentum_store_is_readable():
    class Executor:
        def __call__(self, sql, params):
            self.sql = sql
            self.params = params

    executor = Executor()
    store = FundamentalMomentumStore(execute=executor, query=lambda sql, params: [])
    assessment = assess_fundamental_momentum("CRDO", [
        FundamentalEstimateSnapshot(symbol="CRDO", as_of=date(2026, 8, 1), fiscal_period="FY27", fiscal_year=2027, eps_estimate=2.8, provider="test"),
        FundamentalEstimateSnapshot(symbol="CRDO", as_of=date(2026, 9, 1), fiscal_period="FY27", fiscal_year=2027, eps_estimate=3.1, provider="test"),
    ])
    store.save(assessment, as_of_date="2026-09-01")
    assert "fundamental_momentum_assessments" in executor.sql
    assert executor.params["symbol"] == "CRDO"
