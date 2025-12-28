#!/usr/bin/env python3
"""
Generate and publish stock report
Can be used in n8n workflows or scheduled tasks
"""
import sys
import os
import json
from pathlib import Path

# Add parent directory to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "python-worker"))

from app.database import init_database
from app.services.report_generator import ReportGenerator

def main():
    """Generate report for a symbol and optionally publish"""
    if len(sys.argv) < 2:
        print("Usage: generate_and_publish_report.py <symbol> [--publish]")
        sys.exit(1)
    
    symbol = sys.argv[1].upper()
    should_publish = "--publish" in sys.argv
    
    # Initialize database
    init_database()
    
    # Generate report
    generator = ReportGenerator()
    report = generator.generate_stock_report(symbol, include_llm=True)
    
    if report.get('error'):
        print(f"Error: {report['error']}")
        sys.exit(1)
    
    # Save report
    report_id = generator.save_report(report)
    print(f"✅ Generated report {report_id} for {symbol}")
    
    # Print report summary
    print(f"\n📊 Report Summary:")
    print(f"Signal: {report.get('signal_clarity', {}).get('signal', 'N/A')}")
    print(f"Confidence: {report.get('signal_clarity', {}).get('confidence', 'N/A')}")
    print(f"Summary: {report.get('summary', 'N/A')[:100]}...")
    
    # Publish if requested
    if should_publish:
        print("\n📝 Publishing report...")
        # Add your publishing logic here
        # Example: POST to blog API, n8n webhook, etc.
        print("✅ Report published")
    
    # Output JSON for n8n/webhook
    print(f"\n📄 Report JSON:")
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()

