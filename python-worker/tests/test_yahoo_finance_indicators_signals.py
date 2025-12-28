import pandas as pd


def test_yahoo_finance_can_fetch_and_generate_indicators_and_signal(monkeypatch):
    from app.providers.yahoo_finance.client import YahooFinanceClient
    from app.services.indicator_service import IndicatorService
    from app.database import db

    captured = {"queries": []}

    def _capture_execute_update(query: str, params=None):
        captured["queries"].append((query, params or {}))
        return 1

    monkeypatch.setattr(db, "execute_update", _capture_execute_update)

    client = YahooFinanceClient.from_settings()

    df = client.fetch_price_data("AAPL", period="3mo", interval="1d")
    assert isinstance(df, pd.DataFrame)
    assert not df.empty

    required_cols = {"date", "open", "high", "low", "close", "volume"}
    assert required_cols.issubset(set(df.columns))

    service = IndicatorService()
    ok = service.calculate_indicators("AAPL", data=df)
    assert ok is True

    # Ensure we attempted to persist indicators including signal/confidence.
    indicator_writes = [q for q in captured["queries"] if "INSERT INTO indicators_daily" in q[0]]
    assert indicator_writes, "Expected indicators_daily upsert to run"

    _, params = indicator_writes[-1]
    assert "signal" in params
    assert "confidence_score" in params
