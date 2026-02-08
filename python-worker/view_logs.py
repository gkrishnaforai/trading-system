#!/usr/bin/env python3
"""
API Log Viewer CLI
Command-line interface to view Universal Alert API logs
"""

import argparse
import sys
import os

# Add the app directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.observability.log_viewer import log_viewer, show_recent_logs, show_user_activity, show_errors, show_performance_summary

def main():
    parser = argparse.ArgumentParser(description="Universal Alert API Log Viewer")
    parser.add_argument("--minutes", "-m", type=int, default=10, help="Time window in minutes (default: 10)")
    parser.add_argument("--user", "-u", type=str, help="Filter by user ID")
    parser.add_argument("--tracking", "-t", type=str, help="Filter by tracking ID")
    parser.add_argument("--errors", "-e", action="store_true", help="Show only errors")
    parser.add_argument("--performance", "-p", action="store_true", help="Show performance summary")
    parser.add_argument("--component", "-c", type=str, help="Filter by component (universal_alert_api, api_middleware, etc.)")
    parser.add_argument("--log-file", "-f", type=str, help="Path to log file")
    
    args = parser.parse_args()
    
    # Set custom log file if provided
    if args.log_file:
        log_viewer.log_file_path = args.log_file
    
    try:
        if args.errors:
            show_errors(args.minutes)
        elif args.performance:
            show_performance_summary(args.minutes)
        elif args.user:
            show_user_activity(args.user, args.minutes)
        elif args.tracking:
            logs = log_viewer.get_api_calls_by_tracking_id(args.tracking)
            print(f"\n🔍 Tracking ID: {args.tracking}")
            print("=" * 80)
            if logs:
                for log in logs:
                    print(log_viewer.format_log_entry(log))
            else:
                print("No logs found for this tracking ID.")
            print("=" * 80)
            print(f"Total entries: {len(logs)}")
        else:
            show_recent_logs(args.minutes)
    
    except FileNotFoundError:
        print(f"❌ Log file not found: {log_viewer.log_file_path}")
        print("💡 Make sure the Python Worker is running and generating logs.")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
