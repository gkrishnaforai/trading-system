#!/usr/bin/env python3
"""
Discover all available Yahoo Finance fields for a symbol
"""
import yfinance as yf
import json

def get_all_yahoo_fields(symbol="IREN"):
    """Get all available fields from Yahoo Finance"""
    
    print(f"=" * 60)
    print(f"Discovering all Yahoo Finance fields for {symbol}")
    print(f"=" * 60)
    
    ticker = yf.Ticker(symbol)
    
    # 1. ticker.info - Full info dict
    print(f"\n--- ticker.info (quoteSummary) ---")
    try:
        info = ticker.info
        print(f"Total fields: {len(info)}")
        
        # Group fields by category
        categories = {
            "Price/Valuation": ["currentPrice", "regularMarketPrice", "previousClose", "open", "dayLow", "dayHigh", 
                               "fiftyTwoWeekLow", "fiftyTwoWeekHigh", "volume", "averageVolume", "averageVolume10days",
                               "marketCap", "enterpriseValue"],
            "PE/Ratios": ["trailingPE", "forwardPE", "pegRatio", "priceToSalesTrailing12Months", "priceToBook",
                         "enterpriseToRevenue", "enterpriseToEbitda"],
            "Dividends": ["dividendRate", "dividendYield", "trailingAnnualDividendRate", "trailingAnnualDividendYield",
                         "exDividendDate", "payoutRatio"],
            "EPS/Earnings": ["trailingEps", "forwardEps", "epsTrailingTwelveMonths", "epsForward", "epsCurrentYear"],
            "Profitability": ["profitMargins", "grossMargins", "operatingMargins", "ebitdaMargins"],
            "Growth": ["revenueGrowth", "earningsGrowth", "earningsQuarterlyGrowth", "revenueQuarterlyGrowth"],
            "Returns": ["returnOnAssets", "returnOnEquity"],
            "Financial Health": ["currentRatio", "quickRatio", "debtToEquity", "totalDebt", "totalCash",
                                "totalCashPerShare", "freeCashflow", "operatingCashflow"],
            "Revenue/Income": ["totalRevenue", "revenuePerShare", "grossProfits", "ebitda", "netIncomeToCommon"],
            "Company Info": ["symbol", "shortName", "longName", "sector", "industry", "country", "currency", "exchange"],
            "Risk": ["beta", "52WeekChange", "SandP52WeekChange"],
        }
        
        for cat_name, fields in categories.items():
            print(f"\n  {cat_name}:")
            for field in fields:
                value = info.get(field)
                if value is not None:
                    print(f"    ✅ {field}: {value}")
                else:
                    print(f"    ❌ {field}: None")
        
        # Show any fields we might have missed
        all_known = set()
        for fields in categories.values():
            all_known.update(fields)
        
        other_fields = set(info.keys()) - all_known
        if other_fields:
            print(f"\n  Other fields ({len(other_fields)}):")
            for field in sorted(other_fields)[:20]:
                value = info.get(field)
                if value is not None and value != "":
                    print(f"    {field}: {value}")
                    
    except Exception as e:
        print(f"Error getting info: {e}")
    
    # 2. ticker.fast_info - Lighter weight
    print(f"\n--- ticker.fast_info ---")
    try:
        fast_info = ticker.fast_info
        fast_dict = dict(fast_info)
        print(f"Total fields: {len(fast_dict)}")
        for k, v in fast_dict.items():
            if v is not None:
                print(f"  ✅ {k}: {v}")
            else:
                print(f"  ❌ {k}: None")
    except Exception as e:
        print(f"Error getting fast_info: {e}")
    
    # 3. Financial statement fields
    print(f"\n--- ticker.financials (Income Statement) ---")
    try:
        financials = ticker.financials
        if not financials.empty:
            print(f"Shape: {financials.shape}")
            print(f"Row labels (first 15):")
            for idx in financials.index[:15]:
                print(f"  - {idx}")
    except Exception as e:
        print(f"Error: {e}")
    
    print(f"\n--- ticker.balance_sheet ---")
    try:
        bs = ticker.balance_sheet
        if not bs.empty:
            print(f"Shape: {bs.shape}")
            print(f"Row labels (first 15):")
            for idx in bs.index[:15]:
                print(f"  - {idx}")
    except Exception as e:
        print(f"Error: {e}")
    
    # Summary of key fields for our client
    print(f"\n" + "=" * 60)
    print(f"RECOMMENDATION: Key fields to extract for fundamentals")
    print(f"=" * 60)
    
    key_fields = {
        "price_to_sales": "priceToSalesTrailing12Months",
        "roe (returnOnEquity)": "returnOnEquity",
        "revenue_growth": "revenueGrowth",
        "profit_margin": "profitMargins",
        "current_ratio": "currentRatio",
        "forward_pe": "forwardPE",
        "dividend_yield": "dividendYield",
        "gross_margin": "grossMargins",
        "operating_margin": "operatingMargins",
        "roa (returnOnAssets)": "returnOnAssets",
        "debt_to_equity": "debtToEquity",
        "quick_ratio": "quickRatio",
        "earnings_growth": "earningsGrowth",
        "peg_ratio": "pegRatio",
        "enterprise_to_revenue": "enterpriseToRevenue",
        "enterprise_to_ebitda": "enterpriseToEbitda",
        "free_cash_flow": "freeCashflow",
    }
    
    print(f"\nField availability for {symbol}:")
    for our_name, yahoo_name in key_fields.items():
        value = info.get(yahoo_name)
        status = "✅" if value is not None else "❌"
        print(f"  {status} {our_name} <- info['{yahoo_name}']: {value}")

if __name__ == "__main__":
    get_all_yahoo_fields("IREN")
    print("\n\n")
    get_all_yahoo_fields("AAPL")  # Compare with a well-covered stock
