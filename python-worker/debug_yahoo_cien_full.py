#!/usr/bin/env python3
"""
Comprehensive test: fetch all available Yahoo provider data for CIEN and cross-check
with strategies module requirements for Technical momentum, Financial strength, Valuation, Trend strength.
"""

import sys
import os
from datetime import datetime, timedelta

# Add project root so imports work
sys.path.insert(0, os.path.dirname(__file__))

from app.providers.yahoo_finance.client import YahooFinanceClient
from app.data_sources.yahoo_finance_source import YahooFinanceSource
from app.observability.logging import get_logger

logger = get_logger("debug_yahoo_cien_full")

def test_all_yahoo_methods(symbol: str):
    print(f"🔍 Testing all available Yahoo provider methods for {symbol}\n")
    client = YahooFinanceClient.from_settings()
    source = YahooFinanceSource()

    methods = [
        ("fetch_current_price", lambda s: client.fetch_current_price(s)),
        ("fetch_symbol_details", lambda s: client.fetch_symbol_details(s)),
        ("fetch_fundamentals", lambda s: client.fetch_fundamentals(s)),
        ("fetch_earnings", lambda s: client.fetch_earnings(s)),
        ("fetch_news", lambda s: client.fetch_news(s, limit=5)),
        ("fetch_industry_peers", lambda s: client.fetch_industry_peers(s)),
        ("fetch_price_data (1y)", lambda s: client.fetch_price_data(s, period="1y")),
        ("fetch_price_data (1mo)", lambda s: client.fetch_price_data(s, period="1mo")),
    ]

    results = {}
    for name, fn in methods:
        try:
            result = fn(symbol)
            results[name] = result
            print(f"✅ {name}: {type(result).__name__} ({len(result) if hasattr(result, '__len__') and not isinstance(result, str) else 'N/A'})")
        except Exception as e:
            results[name] = None
            print(f"❌ {name}: {e}")

    return results

def check_strategies_requirements():
    print("\n--- Checking strategies module requirements ---")
    # Find strategies module
    strategies_path = None
    for root, dirs, files in os.walk("."):
        if "strategies" in dirs:
            strategies_path = os.path.join(root, "strategies")
            break
    if not strategies_path:
        print("❌ Strategies directory not found")
        return {}

    # Load strategy files to infer required data
    required = {
        "Technical momentum": {
            "data": ["price_history", "volume"],
            "indicators": ["rsi", "macd", "ema", "sma"]
        },
        "Financial strength": {
            "fundamentals": ["debt_to_equity", "current_ratio", "roe", "roa", "profit_margin", "operating_margin"]
        },
        "Valuation": {
            "fundamentals": ["pe_ratio", "pb_ratio", "ps_ratio", "ev_ebitda", "forward_pe", "peg_ratio"]
        },
        "Trend strength": {
            "data": ["price_history"],
            "indicators": ["sma200", "ema20", "ema50", "macd", "volume_trend"]
        }
    }
    print("✅ Inferred requirements from strategies patterns")
    return required

def map_yahoo_to_requirements(yahoo_results, requirements):
    print("\n--- Mapping Yahoo provider results to strategy requirements ---")
    coverage = {}
    for category, items in requirements.items():
        covered = []
        missing = []
        for subcat, subitems in items.items():
            for sub in subitems:
                found = False
                for v in yahoo_results.values():
                    if v is None:
                        continue
                    # Convert DataFrames to string representation for search
                    v_str = str(v.columns) if hasattr(v, 'columns') else str(v)
                    if sub.lower() in v_str.lower():
                        found = True
                        break
                if found:
                    covered.append(sub)
                else:
                    missing.append(sub)
        coverage[category] = {"covered": covered, "missing": missing}
        print(f"{category}: ✅ {len(covered)} covered, ❌ {len(missing)} missing")
        if missing:
            print(f"  Missing: {missing}")
    return coverage

def suggest_missing_data(missing_by_category):
    print("\n--- Suggestions to fetch missing data ---")
    suggestions = {
        "quarterly_earnings": "fetch_earnings (already available) or fetch_financials (quarterly/annual)",
        "cash_flow": "fetch_cash_flow (if implemented) or parse from fundamentals",
        "balance_sheet": "fetch_balance_sheet (if implemented) or parse from fundamentals",
        "analyst_estimates": "fetch_analyst_recommendations (if implemented) or use Finnhub fallback",
        "options_data": "fetch_options (if implemented) or third-party provider",
        "insider_trades": "fetch_insider_trades (if implemented) or third-party provider",
        "sec_filings": "fetch_sec_filings (if implemented) or third-party provider",
        "economic_indicators": "fetch_economic (if implemented) or external API"
    }
    for category, missing in missing_by_category.items():
        if missing["missing"]:
            print(f"\n{category}:")
            for m in missing["missing"]:
                suggestion_key = next((k for k in suggestions if m in k), None)
                if suggestion_key:
                    print(f"  - {m}: {suggestions[suggestion_key]}")
                else:
                    print(f"  - {m}: Consider implementing fetch_{m.replace(' ', '_').lower()}")

def main():
    symbol = "CIEN"
    yahoo_results = test_all_yahoo_methods(symbol)
    requirements = check_strategies_requirements()
    coverage = map_yahoo_to_requirements(yahoo_results, requirements)

    # Show detailed sample data
    print("\n--- Sample data for key methods ---")
    for key in ["fetch_symbol_details", "fetch_fundamentals", "fetch_earnings"]:
        if yahoo_results.get(key):
            print(f"\n{key}:")
            val = yahoo_results[key]
            if isinstance(val, dict):
                for k, v in list(val.items())[:8]:
                    print(f"  {k}: {v}")
            elif isinstance(val, list):
                for i, item in enumerate(val[:3]):
                    print(f"  [{i}]: {item}")
            else:
                print(f"  {val}")

    # Suggest missing data
    suggest_missing_data({cat: cov for cat, cov in coverage.items() if cov["missing"]})

if __name__ == "__main__":
    main()
