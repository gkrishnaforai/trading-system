"""
API Log Viewer Utility
Helper functions to view and filter API logs from the Universal Alert System
"""

import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from app.observability.constants import (
    LOG_PATTERNS, 
    DEFAULT_LOG_PATHS,
    validate_tracking_id,
    validate_user_id,
    validate_alert_id,
    format_timestamp,
    truncate_id
)

class APILogViewer:
    """Utility class for viewing and analyzing API logs"""
    
    def __init__(self, log_file_path: str = None):
        self.log_file_path = log_file_path or DEFAULT_LOG_PATHS["api"]
        self.log_patterns = LOG_PATTERNS
    
    def parse_log_line(self, line: str) -> Optional[Dict[str, Any]]:
        """Parse a single log line and extract structured data"""
        parsed = {
            "timestamp": None,
            "level": None,
            "component": None,
            "message": line.strip(),
            "tracking_id": None,
            "user_id": None,
            "alert_id": None,
            "operation": None,
            "method": None,
            "path": None,
            "success": None,
            "error": None
        }
        
        # Extract timestamp, level, component
        timestamp_match = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) \| (\w+) \| (\w+)", line)
        if timestamp_match:
            parsed["timestamp"] = timestamp_match.group(1)
            parsed["level"] = timestamp_match.group(2)
            parsed["component"] = timestamp_match.group(3)
        
        # Extract tracking ID
        tracking_match = re.search(self.log_patterns["tracking_id"], line)
        if tracking_match:
            parsed["tracking_id"] = tracking_match.group(1)
        
        # Extract user ID
        user_match = re.search(self.log_patterns["user_id"], line)
        if user_match:
            parsed["user_id"] = user_match.group(1)
        
        # Extract alert ID
        alert_match = re.search(self.log_patterns["alert_id"], line)
        if alert_match:
            parsed["alert_id"] = alert_match.group(1)
        
        # Determine operation type and success
        if "🚀 API Call Started" in line:
            request_match = re.search(self.log_patterns["request_start"], line)
            if request_match:
                parsed["operation"] = "api_call"
                parsed["method"] = request_match.group(2)
                parsed["path"] = request_match.group(3)
                parsed["success"] = None  # In progress
        
        elif "✅ API Call Completed" in line:
            request_match = re.search(self.log_patterns["request_success"], line)
            if request_match:
                parsed["operation"] = "api_call"
                parsed["method"] = request_match.group(2)
                parsed["path"] = request_match.group(3)
                parsed["success"] = True
        
        elif "❌ API Call Failed" in line:
            request_match = re.search(self.log_patterns["request_error"], line)
            if request_match:
                parsed["operation"] = "api_call"
                parsed["method"] = request_match.group(2)
                parsed["path"] = request_match.group(3)
                parsed["success"] = False
        
        elif "🚀 STARTING" in line:
            operation_match = re.search(self.log_patterns["operation_start"], line)
            if operation_match:
                parsed["operation"] = operation_match.group(1)
                parsed["success"] = None  # In progress
        
        elif "✅ COMPLETED" in line:
            operation_match = re.search(self.log_patterns["operation_success"], line)
            if operation_match:
                parsed["operation"] = operation_match.group(1)
                parsed["success"] = True
        
        elif "❌ FAILED" in line:
            operation_match = re.search(self.log_patterns["operation_failure"], line)
            if operation_match:
                parsed["operation"] = operation_match.group(1)
                parsed["success"] = False
        
        return parsed
    
    def get_recent_logs(self, minutes: int = 10, component: str = None) -> List[Dict[str, Any]]:
        """Get recent logs from the last N minutes"""
        logs = []
        cutoff_time = datetime.now() - timedelta(minutes=minutes)
        
        try:
            with open(self.log_file_path, 'r') as f:
                for line in f:
                    parsed = self.parse_log_line(line)
                    if parsed and parsed["timestamp"]:
                        try:
                            log_time = datetime.strptime(parsed["timestamp"], "%Y-%m-%d %H:%M:%S,%f")
                            if log_time >= cutoff_time:
                                if component is None or parsed["component"] == component:
                                    logs.append(parsed)
                        except ValueError:
                            continue
        except FileNotFoundError:
            print(f"Log file not found: {self.log_file_path}")
        
        return logs
    
    def get_api_calls_by_tracking_id(self, tracking_id: str) -> List[Dict[str, Any]]:
        """Get all log entries for a specific tracking ID"""
        logs = []
        
        try:
            with open(self.log_file_path, 'r') as f:
                for line in f:
                    if tracking_id in line:
                        parsed = self.parse_log_line(line)
                        if parsed:
                            logs.append(parsed)
        except FileNotFoundError:
            print(f"Log file not found: {self.log_file_path}")
        
        return logs
    
    def get_user_activity(self, user_id: str, minutes: int = 60) -> List[Dict[str, Any]]:
        """Get all activity for a specific user"""
        logs = []
        cutoff_time = datetime.now() - timedelta(minutes=minutes)
        
        try:
            with open(self.log_file_path, 'r') as f:
                for line in f:
                    if user_id in line:
                        parsed = self.parse_log_line(line)
                        if parsed and parsed["timestamp"]:
                            try:
                                log_time = datetime.strptime(parsed["timestamp"], "%Y-%m-%d %H:%M:%S,%f")
                                if log_time >= cutoff_time:
                                    logs.append(parsed)
                            except ValueError:
                                continue
        except FileNotFoundError:
            print(f"Log file not found: {self.log_file_path}")
        
        return logs
    
    def get_error_logs(self, minutes: int = 60) -> List[Dict[str, Any]]:
        """Get all error logs"""
        logs = []
        cutoff_time = datetime.now() - timedelta(minutes=minutes)
        
        try:
            with open(self.log_file_path, 'r') as f:
                for line in f:
                    if "ERROR" in line or "❌" in line:
                        parsed = self.parse_log_line(line)
                        if parsed and parsed["timestamp"]:
                            try:
                                log_time = datetime.strptime(parsed["timestamp"], "%Y-%m-%d %H:%M:%S,%f")
                                if log_time >= cutoff_time:
                                    logs.append(parsed)
                            except ValueError:
                                continue
        except FileNotFoundError:
            print(f"Log file not found: {self.log_file_path}")
        
        return logs
    
    def get_performance_summary(self, minutes: int = 60) -> Dict[str, Any]:
        """Get performance summary of API calls"""
        logs = self.get_recent_logs(minutes)
        
        summary = {
            "total_api_calls": 0,
            "successful_calls": 0,
            "failed_calls": 0,
            "endpoints": {},
            "average_response_time": 0,
            "slowest_calls": [],
            "error_rate": 0
        }
        
        response_times = []
        
        for log in logs:
            if log["operation"] == "api_call" and log["success"] is not None:
                summary["total_api_calls"] += 1
                
                if log["success"]:
                    summary["successful_calls"] += 1
                else:
                    summary["failed_calls"] += 1
                
                # Track by endpoint
                endpoint = f"{log['method']} {log['path']}"
                if endpoint not in summary["endpoints"]:
                    summary["endpoints"][endpoint] = {"calls": 0, "successes": 0, "failures": 0}
                
                summary["endpoints"][endpoint]["calls"] += 1
                if log["success"]:
                    summary["endpoints"][endpoint]["successes"] += 1
                else:
                    summary["endpoints"][endpoint]["failures"] += 1
        
        # Calculate error rate
        if summary["total_api_calls"] > 0:
            summary["error_rate"] = (summary["failed_calls"] / summary["total_api_calls"]) * 100
        
        return summary
    
    def format_log_entry(self, log: Dict[str, Any]) -> str:
        """Format a log entry for display"""
        timestamp = log.get("timestamp", "Unknown")
        level = log.get("level", "Unknown")
        message = log.get("message", "")
        
        formatted = f"[{timestamp}] {level}: {message}"
        
        # Add tracking info
        if log.get("tracking_id"):
            formatted += f" | Tracking: {log['tracking_id']}"
        
        # Add user info
        if log.get("user_id"):
            formatted += f" | User: {truncate_id(log['user_id'])}"
        
        # Add alert info
        if log.get("alert_id"):
            formatted += f" | Alert: {truncate_id(log['alert_id'])}"
        
        return formatted
    
    def print_recent_activity(self, minutes: int = 10):
        """Print recent activity to console"""
        logs = self.get_recent_logs(minutes)
        
        print(f"\n📊 Recent API Activity (Last {minutes} minutes)")
        print("=" * 80)
        
        if not logs:
            print("No recent activity found.")
            return
        
        for log in logs[-20:]:  # Show last 20 entries
            print(self.format_log_entry(log))
        
        print("=" * 80)
        print(f"Total entries: {len(logs)}")
    
    def print_user_activity(self, user_id: str, minutes: int = 60):
        """Print user activity to console"""
        logs = self.get_user_activity(user_id, minutes)
        
        print(f"\n👤 User Activity: {user_id[:8]}... (Last {minutes} minutes)")
        print("=" * 80)
        
        if not logs:
            print("No activity found for this user.")
            return
        
        for log in logs:
            print(self.format_log_entry(log))
        
        print("=" * 80)
        print(f"Total entries: {len(logs)}")
    
    def print_errors(self, minutes: int = 60):
        """Print recent errors to console"""
        logs = self.get_error_logs(minutes)
        
        print(f"\n❌ Recent Errors (Last {minutes} minutes)")
        print("=" * 80)
        
        if not logs:
            print("No errors found.")
            return
        
        for log in logs:
            print(self.format_log_entry(log))
        
        print("=" * 80)
        print(f"Total errors: {len(logs)}")
    
    def print_performance_summary(self, minutes: int = 60):
        """Print performance summary to console"""
        summary = self.get_performance_summary(minutes)
        
        print(f"\n📈 Performance Summary (Last {minutes} minutes)")
        print("=" * 80)
        print(f"Total API Calls: {summary['total_api_calls']}")
        print(f"Successful: {summary['successful_calls']}")
        print(f"Failed: {summary['failed_calls']}")
        print(f"Error Rate: {summary['error_rate']:.2f}%")
        
        print(f"\n📊 Endpoint Breakdown:")
        for endpoint, stats in summary["endpoints"].items():
            success_rate = (stats["successes"] / stats["calls"] * 100) if stats["calls"] > 0 else 0
            print(f"  {endpoint}: {stats['calls']} calls ({success_rate:.1f}% success)")
        
        print("=" * 80)

# Create a global log viewer instance
log_viewer = APILogViewer()

# Convenience functions for quick access
def show_recent_logs(minutes: int = 10):
    """Show recent logs"""
    log_viewer.print_recent_activity(minutes)

def show_user_activity(user_id: str, minutes: int = 60):
    """Show user activity"""
    log_viewer.print_user_activity(user_id, minutes)

def show_errors(minutes: int = 60):
    """Show recent errors"""
    log_viewer.print_errors(minutes)

def show_performance_summary(minutes: int = 60):
    """Show performance summary"""
    log_viewer.print_performance_summary(minutes)
