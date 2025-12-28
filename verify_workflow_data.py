#!/usr/bin/env python3
"""
Quick verification script to check if workflow data is populated
Can be run directly or inside Docker container
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'python-worker'))

from app.database import db
import json

def verify_all(symbol: str = "AAPL"):
    """Verify all data for a symbol"""
    print(f"\n{'='*70}")
    print(f"Verifying Workflow Data for {symbol}")
    print(f"{'='*70}\n")
    
    # Initialize database
    db.initialize()
    
    # 1. Check workflow executions
    print("📋 Workflow Executions:")
    workflows = db.execute_query(
        """
        SELECT workflow_id, workflow_type, status, current_stage, started_at
        FROM workflow_executions
        ORDER BY started_at DESC
        LIMIT 5
        """,
        {}
    )
    if workflows:
        for wf in workflows:
            print(f"   ✅ {wf['workflow_id'][:8]}... | {wf['workflow_type']} | {wf['status']} | Stage: {wf['current_stage']}")
    else:
        print("   ❌ No workflow executions found")
    
    # 2. Check workflow stages
    print("\n📊 Workflow Stages (Latest Workflow):")
    if workflows:
        latest_wf_id = workflows[0]['workflow_id']
        stages = db.execute_query(
            """
            SELECT stage_name, status, symbols_succeeded, symbols_failed
            FROM workflow_stage_executions
            WHERE workflow_id = :workflow_id
            ORDER BY started_at ASC
            """,
            {'workflow_id': latest_wf_id}
        )
        if stages:
            for stage in stages:
                status_icon = "✅" if stage['status'] == 'completed' else "❌" if stage['status'] == 'failed' else "⏳"
                print(f"   {status_icon} {stage['stage_name']}: {stage['status']} (✓{stage['symbols_succeeded']}, ✗{stage['symbols_failed']})")
        else:
            print("   ❌ No stages found")
    
    # 3. Check financial data
    print(f"\n💰 Financial Data for {symbol}:")
    
    income = db.execute_query(
        "SELECT COUNT(*) as count FROM income_statements WHERE stock_symbol = :symbol",
        {'symbol': symbol}
    )
    print(f"   {'✅' if income and income[0]['count'] > 0 else '❌'} Income Statements: {income[0]['count'] if income else 0} records")
    
    balance = db.execute_query(
        "SELECT COUNT(*) as count FROM balance_sheets WHERE stock_symbol = :symbol",
        {'symbol': symbol}
    )
    print(f"   {'✅' if balance and balance[0]['count'] > 0 else '❌'} Balance Sheets: {balance[0]['count'] if balance else 0} records")
    
    cashflow = db.execute_query(
        "SELECT COUNT(*) as count FROM cash_flow_statements WHERE stock_symbol = :symbol",
        {'symbol': symbol}
    )
    print(f"   {'✅' if cashflow and cashflow[0]['count'] > 0 else '❌'} Cash Flow Statements: {cashflow[0]['count'] if cashflow else 0} records")
    
    # 4. Check enhanced fundamentals
    print(f"\n📈 Enhanced Fundamentals for {symbol}:")
    fundamentals = db.execute_query(
        """
        SELECT as_of_date, revenue_growth, earnings_growth, eps_growth, pe_ratio, market_cap
        FROM enhanced_fundamentals
        WHERE stock_symbol = :symbol
        ORDER BY as_of_date DESC
        LIMIT 1
        """,
        {'symbol': symbol}
    )
    if fundamentals and fundamentals[0]:
        f = fundamentals[0]
        print(f"   ✅ Latest (as of {f['as_of_date']}):")
        if f['revenue_growth'] is not None:
            print(f"      Revenue Growth: {f['revenue_growth']:.2f}%")
        if f['earnings_growth'] is not None:
            print(f"      Earnings Growth: {f['earnings_growth']:.2f}%")
        if f['eps_growth'] is not None:
            print(f"      EPS Growth: {f['eps_growth']:.2f}%")
        if f['pe_ratio'] is not None:
            print(f"      P/E Ratio: {f['pe_ratio']:.2f}")
    else:
        print("   ❌ No enhanced fundamentals found")
    
    # 5. Check weekly aggregation
    print(f"\n📅 Weekly Aggregation for {symbol}:")
    weekly = db.execute_query(
        """
        SELECT COUNT(*) as count, MIN(date) as earliest, MAX(date) as latest
        FROM multi_timeframe_data
        WHERE stock_symbol = :symbol AND timeframe = 'weekly'
        """,
        {'symbol': symbol}
    )
    if weekly and weekly[0]['count'] > 0:
        w = weekly[0]
        print(f"   ✅ {w['count']} weekly bars (from {w['earliest']} to {w['latest']})")
    else:
        print("   ❌ No weekly data found")
    
    # 6. Check daily price data (prerequisite)
    print(f"\n💹 Daily Price Data for {symbol}:")
    daily = db.execute_query(
        """
        SELECT COUNT(*) as count, MIN(date) as earliest, MAX(date) as latest
        FROM raw_market_data
        WHERE stock_symbol = :symbol
        """,
        {'symbol': symbol}
    )
    if daily and daily[0]['count'] > 0:
        d = daily[0]
        print(f"   ✅ {d['count']} daily bars (from {d['earliest']} to {d['latest']})")
    else:
        print("   ❌ No daily price data found")
    
    print(f"\n{'='*70}\n")

if __name__ == "__main__":
    symbol = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    verify_all(symbol)

