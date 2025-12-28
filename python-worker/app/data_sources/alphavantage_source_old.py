"""Alpha Vantage legacy module (compatibility shim).

Architecture compliance (see app/data_management/ARCHITECTURE.md):
- Provider logic lives in app/providers/alphavantage/client.py
- Thin adapter lives in app/data_sources/alphavantage_source.py

This file keeps the historical import path but re-exports the compliant
AlphaVantageSource.
"""

from app.data_sources.alphavantage_source import AlphaVantageSource  # noqa: F401
