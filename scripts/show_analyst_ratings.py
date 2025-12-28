#!/usr/bin/env python3
"""
Script to display analyst ratings for a stock symbol
Usage: python scripts/show_analyst_ratings.py NVDA
"""
import sys
import os
from pathlib import Path

# Add python-worker to path
sys.path.insert(0, str(Path(__file__).parent.parent / "python-worker"))

from app.database import init_database, db
from app.services.analyst_ratings_service import AnalystRatingsService

def show_ratings(symbol: str):
    """Display analyst ratings for a symbol"""
    init_database()
    service = AnalystRatingsService()
    
    print('\n' + '='*80)
    print(f'ANALYST RATINGS FOR {symbol.upper()}')
    print('='*80)
    
    # Get ratings from database
    ratings = service.get_analyst_ratings(symbol)
    consensus = service.get_consensus(symbol)
    
    print(f'\nTotal Ratings in Database: {len(ratings)}')
    
    if ratings:
        print('\n📊 Individual Ratings:')
        print('-'*80)
        for i, rating in enumerate(ratings, 1):
            print(f'\n{i}. Analyst: {rating.get("analyst_name", "Unknown")}')
            if rating.get('firm_name'):
                print(f'   Firm: {rating.get("firm_name")}')
            rating_display = rating.get("rating", "N/A").upper().replace("_", " ")
            print(f'   Rating: {rating_display}')
            if rating.get('price_target'):
                print(f'   Price Target: ${rating.get("price_target"):,.2f}')
            if rating.get('rating_date'):
                print(f'   Date: {rating.get("rating_date")}')
            print(f'   Source: {rating.get("source", "N/A")}')
    else:
        print('\n⚠️  No ratings found in database')
        print('\nTo fetch ratings:')
        print('1. Set FINNHUB_API_KEY environment variable')
        print('2. Run: curl -X POST http://localhost:8001/api/v1/stock/NVDA/analyst-ratings/fetch')
        print('   OR')
        print('   python -c "from app.services.analyst_ratings_service import AnalystRatingsService;')
        print('             service = AnalystRatingsService();')
        print('             service.fetch_and_save_ratings(\'NVDA\')"')
    
    if consensus:
        print('\n' + '='*80)
        print('📈 CONSENSUS RATING')
        print('='*80)
        consensus_rating = consensus.get("consensus_rating", "N/A").upper().replace("_", " ")
        print(f'\nConsensus Rating: {consensus_rating}')
        if consensus.get('consensus_price_target'):
            print(f'Consensus Price Target: ${consensus.get("consensus_price_target"):,.2f}')
        print(f'\nRating Breakdown:')
        print(f'  🟢 Strong Buy: {consensus.get("strong_buy_count", 0)}')
        print(f'  🟢 Buy: {consensus.get("buy_count", 0)}')
        print(f'  🟡 Hold: {consensus.get("hold_count", 0)}')
        print(f'  🔴 Sell: {consensus.get("sell_count", 0)}')
        print(f'  🔴 Strong Sell: {consensus.get("strong_sell_count", 0)}')
        print(f'  📊 Total Ratings: {consensus.get("total_ratings", 0)}')
    else:
        print('\n⚠️  No consensus data available')
        print('   (Consensus is calculated from individual ratings)')
    
    print('\n' + '='*80)
    
    # Also show raw database query
    print('\n📋 Raw Database Query:')
    print('-'*80)
    query = """
        SELECT analyst_name, firm_name, rating, price_target, rating_date, source
        FROM analyst_ratings
        WHERE stock_symbol = :symbol
        ORDER BY rating_date DESC
    """
    result = db.execute_query(query, {"symbol": symbol})
    if result:
        for r in result:
            print(f"  {r.get('analyst_name', 'N/A')} ({r.get('firm_name', 'N/A')}): "
                  f"{r.get('rating', 'N/A')} - ${r.get('price_target', 'N/A')} "
                  f"({r.get('rating_date', 'N/A')})")
    else:
        print("  No ratings in database")
    
    print('\n' + '='*80)

if __name__ == "__main__":
    symbol = sys.argv[1] if len(sys.argv) > 1 else "NVDA"
    show_ratings(symbol)

