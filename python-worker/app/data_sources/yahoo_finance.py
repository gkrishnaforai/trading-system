"""Yahoo Finance data source (compatibility shim).

Architecture compliance:
- Provider logic lives in app/providers/yahoo_finance/client.py
- Thin adapter lives in app/data_sources/yahoo_finance_source.py

This module keeps the historical import path (app.data_sources.yahoo_finance)
but delegates all behavior to the compliant thin adapter.
"""

from app.data_sources.yahoo_finance_source import YahooFinanceSource  # noqa: F401


