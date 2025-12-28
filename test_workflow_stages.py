#!/usr/bin/env python3
"""
Test script for new workflow stages
Tests: Financial Data Ingestion, Weekly Aggregation, Growth Calculations
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'python-worker'))

from app.workflows.orchestrator import WorkflowOrchestrator
from app.workflows.data_frequency import DataFrequency
from app.database import db
import json
from datetime import datetime

def test_workflow(symbol: str = "AAPL"):
    """Test the complete workflow with new stages"""
    print(f"\n{'='*60}")
    print(f"Testing Workflow for {symbol}")
    print(f"{'='*60}\n")
    
    # Initialize orchestrator
    orchestrator = WorkflowOrchestrator()
    
    # Execute workflow
    print("🚀 Executing workflow...")
    result = orchestrator.execute_workflow(
        workflow_type='on_demand',
        symbols=[symbol],
        data_frequency=DataFrequency.DAILY,
        force=True
    )
    
    print(f"\n✅ Workflow completed!")
    print(f"   Success: {result.success}")
    print(f"   Workflow ID: {result.workflow_id}")
    print(f"   Symbols Processed: {result.symbols_processed}")
    print(f"   Symbols Succeeded: {result.symbols_succeeded}")
    print(f"   Symbols Failed: {result.symbols_failed}")
    print(f"   Stages Completed: {result.stages_completed}")
    
    if result.error:
        print(f"   Error: {result.error}")
    
    return result

def verify_workflow_stages(workflow_id: str):
    """Verify workflow stages were executed"""
    print(f"\n{'='*60}")
    print(f"Verifying Workflow Stages: {workflow_id}")
    print(f"{'='*60}\n")
    
    # Get workflow execution
    workflow = db.execute_query(
        """
        SELECT workflow_id, workflow_type, status, current_stage, started_at, completed_at, metadata_json
        FROM workflow_executions
        WHERE workflow_id = :workflow_id
        """,
        {'workflow_id': workflow_id}
    )
    
    if not workflow:
        print(f"❌ Workflow {workflow_id} not found")
        return
    
    wf = workflow[0]
    print(f"Workflow: {wf['workflow_type']}")
    print(f"Status: {wf['status']}")
    print(f"Current Stage: {wf['current_stage']}")
    print(f"Started: {wf['started_at']}")
    print(f"Completed: {wf['completed_at']}")
    
    if wf.get('metadata_json'):
        try:
            metadata = json.loads(wf['metadata_json'])
            print(f"Metadata: {json.dumps(metadata, indent=2)}")
        except:
            pass
    
    # Get stages
    stages = db.execute_query(
        """
        SELECT stage_name, status, started_at, completed_at, symbols_succeeded, symbols_failed
        FROM workflow_stage_executions
        WHERE workflow_id = :workflow_id
        ORDER BY started_at ASC
        """,
        {'workflow_id': workflow_id}
    )
    
    print(f"\n📋 Stages Executed ({len(stages)}):")
    for stage in stages:
        status_icon = "✅" if stage['status'] == 'completed' else "❌" if stage['status'] == 'failed' else "⏳"
        print(f"   {status_icon} {stage['stage_name']}: {stage['status']}")
        print(f"      Started: {stage['started_at']}")
        print(f"      Completed: {stage['completed_at']}")
        print(f"      Succeeded: {stage['symbols_succeeded']}, Failed: {stage['symbols_failed']}")
    
    return stages

def verify_financial_data(symbol: str):
    """Verify financial data is populated"""
    print(f"\n{'='*60}")
    print(f"Verifying Financial Data for {symbol}")
    print(f"{'='*60}\n")
    
    # Check income statements
    income = db.execute_query(
        """
        SELECT COUNT(*) as count, MAX(period_end) as latest_period
        FROM income_statements
        WHERE stock_symbol = :symbol
        """,
        {'symbol': symbol}
    )
    if income and income[0]['count'] > 0:
        print(f"✅ Income Statements: {income[0]['count']} records (Latest: {income[0]['latest_period']})")
    else:
        print(f"❌ Income Statements: No data found")
    
    # Check balance sheets
    balance = db.execute_query(
        """
        SELECT COUNT(*) as count, MAX(period_end) as latest_period
        FROM balance_sheets
        WHERE stock_symbol = :symbol
        """,
        {'symbol': symbol}
    )
    if balance and balance[0]['count'] > 0:
        print(f"✅ Balance Sheets: {balance[0]['count']} records (Latest: {balance[0]['latest_period']})")
    else:
        print(f"❌ Balance Sheets: No data found")
    
    # Check cash flow statements
    cashflow = db.execute_query(
        """
        SELECT COUNT(*) as count, MAX(period_end) as latest_period
        FROM cash_flow_statements
        WHERE stock_symbol = :symbol
        """,
        {'symbol': symbol}
    )
    if cashflow and cashflow[0]['count'] > 0:
        print(f"✅ Cash Flow Statements: {cashflow[0]['count']} records (Latest: {cashflow[0]['latest_period']})")
    else:
        print(f"❌ Cash Flow Statements: No data found")
    
    # Check enhanced fundamentals
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
        print(f"✅ Enhanced Fundamentals (as of {f['as_of_date']}):")
        print(f"   Revenue Growth: {f['revenue_growth']}%")
        print(f"   Earnings Growth: {f['earnings_growth']}%")
        print(f"   EPS Growth: {f['eps_growth']}%")
        print(f"   P/E Ratio: {f['pe_ratio']}")
        print(f"   Market Cap: {f['market_cap']}")
    else:
        print(f"❌ Enhanced Fundamentals: No data found")

def verify_weekly_aggregation(symbol: str):
    """Verify weekly aggregation data"""
    print(f"\n{'='*60}")
    print(f"Verifying Weekly Aggregation for {symbol}")
    print(f"{'='*60}\n")
    
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
        print(f"✅ Weekly Data: {w['count']} bars")
        print(f"   Date Range: {w['earliest']} to {w['latest']}")
        
        # Show sample data
        sample = db.execute_query(
            """
            SELECT date, open, high, low, close, volume
            FROM multi_timeframe_data
            WHERE stock_symbol = :symbol AND timeframe = 'weekly'
            ORDER BY date DESC
            LIMIT 5
            """,
            {'symbol': symbol}
        )
        if sample:
            print(f"\n   Latest 5 Weekly Bars:")
            for bar in sample:
                print(f"   {bar['date']}: O={bar['open']:.2f}, H={bar['high']:.2f}, L={bar['low']:.2f}, C={bar['close']:.2f}, V={bar['volume']:,}")
    else:
        print(f"❌ Weekly Data: No data found")

def verify_growth_calculations(symbol: str):
    """Verify growth calculations"""
    print(f"\n{'='*60}")
    print(f"Verifying Growth Calculations for {symbol}")
    print(f"{'='*60}\n")
    
    # Check if growth metrics are in enhanced_fundamentals
    growth = db.execute_query(
        """
        SELECT as_of_date, revenue_growth, earnings_growth, eps_growth
        FROM enhanced_fundamentals
        WHERE stock_symbol = :symbol
        AND (revenue_growth IS NOT NULL OR earnings_growth IS NOT NULL OR eps_growth IS NOT NULL)
        ORDER BY as_of_date DESC
        LIMIT 1
        """,
        {'symbol': symbol}
    )
    
    if growth and growth[0]:
        g = growth[0]
        print(f"✅ Growth Metrics (as of {g['as_of_date']}):")
        if g['revenue_growth'] is not None:
            print(f"   Revenue Growth: {g['revenue_growth']:.2f}%")
        if g['earnings_growth'] is not None:
            print(f"   Earnings Growth: {g['earnings_growth']:.2f}%")
        if g['eps_growth'] is not None:
            print(f"   EPS Growth: {g['eps_growth']:.2f}%")
    else:
        print(f"❌ Growth Metrics: No data found")

def main():
    """Main test function"""
    symbol = "AAPL"
    
    try:
        # Initialize database
        db.initialize()
        
        # Test workflow
        result = test_workflow(symbol)
        
        if result.workflow_id:
            # Verify stages
            verify_workflow_stages(result.workflow_id)
        
        # Verify data
        verify_financial_data(symbol)
        verify_weekly_aggregation(symbol)
        verify_growth_calculations(symbol)
        
        print(f"\n{'='*60}")
        print("✅ Test Complete!")
        print(f"{'='*60}\n")
        
    except Exception as e:
        print(f"\n❌ Test Failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

