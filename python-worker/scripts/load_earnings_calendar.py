#!/usr/bin/env python3
"""
Script to load earnings calendar data following our architecture.
"""

import sys
import os
from datetime import datetime, date, timedelta

# Add project root so imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.services.earnings_calendar_service import EarningsCalendarService
from app.observability.logging import get_logger
from app.database import init_database

logger = get_logger("load_earnings_calendar")

def load_major_symbols():
    """Load earnings for major market symbols."""
    # Initialize database first
    init_database()
    
    service = EarningsCalendarService()
    
    # Major symbols across different sectors
    symbols = [
        # Technology
        "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA", "META", "ADBE", "CRM", "PYPL",
        "INTC", "CSCO", "CMCSA", "PEP", "COST", "AVGO", "TXN", "QCOM", "IBM", "ORCL",
        
        # Financial Services
        "JPM", "BAC", "WFC", "GS", "MS", "C", "AXP", "BLK", "SPGI", "V", "MA",
        
        # Healthcare
        "JNJ", "UNH", "PFE", "ABBV", "TMO", "ABT", "MRK", "MDT", "AMGN", "GILD",
        
        # Consumer
        "WMT", "HD", "MCD", "NKE", "DIS", "NFLX", "LOW", "TGT", "COST", "KO",
        
        # Industrial
        "BA", "CAT", "GE", "MMM", "HON", "UPS", "RTX", "LMT", "DE", "GM",
        
        # Energy
        "XOM", "CVX", "COP", "EOG", "SLB", "BP", "SHEL", "TOT", "ENB", "KMI",
        
        # Other notable
        "BRK-A", "BRK-B", "VZ", "T", "F", "GM", "TSLA", "SPOT", "UBER", "LYFT"
    ]
    
    # Load data for next 90 days
    start_date = date.today().strftime("%Y-%m-%d")
    end_date = (date.today() + timedelta(days=90)).strftime("%Y-%m-%d")
    
    logger.info(f"Loading earnings calendar for {len(symbols)} symbols from {start_date} to {end_date}")
    
    result = service.refresh_earnings_calendar(symbols, start_date, end_date)
    
    if result["status"] == "success":
        logger.info(f"✅ Successfully loaded {result['count']} earnings entries")
        print(f"✅ Loaded {result['count']} earnings entries")
    else:
        logger.error(f"❌ Failed to load earnings: {result.get('error')}")
        print(f"❌ Failed: {result.get('error')}")
    
    # Get summary
    summary = service.get_earnings_summary(
        start_date=datetime.strptime(start_date, "%Y-%m-%d").date(),
        end_date=datetime.strptime(end_date, "%Y-%m-%d").date()
    )
    
    print(f"\n📊 Summary:")
    print(f"  Total companies: {summary['total_companies']}")
    print(f"  Unique symbols: {summary['unique_symbols']}")
    print(f"  Sectors represented: {len(summary['by_sector'])}")
    
    if summary['by_sector']:
        print(f"\n📈 By Sector:")
        for sector, count in list(summary['by_sector'].items())[:5]:
            print(f"  {sector}: {count}")

if __name__ == "__main__":
    load_major_symbols()
