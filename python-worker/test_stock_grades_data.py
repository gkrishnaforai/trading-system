#!/usr/bin/env python3
"""
Test script to verify stock grades data and alerts
"""

import os
import sys
import psycopg2
from dotenv import load_dotenv

def test_stock_grades_data():
    """Check what stock grades data was loaded and if alerts were triggered"""
    
    load_dotenv()
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("❌ DATABASE_URL not found")
        return False
    
    try:
        conn = psycopg2.connect(database_url)
        cursor = conn.cursor()
        
        print("🔍 Checking Stock Grades System Data...")
        print("=" * 60)
        
        # Check stock_grades table
        cursor.execute("SELECT COUNT(*) FROM stock_grades")
        grades_count = cursor.fetchone()[0]
        print(f"📊 Total stock grades loaded: {grades_count}")
        
        if grades_count > 0:
            cursor.execute("""
                SELECT symbol, grading_company, new_grade, action, grade_date, data_source
                FROM stock_grades 
                ORDER BY grade_date DESC 
                LIMIT 10
            """)
            recent_grades = cursor.fetchall()
            print(f"\n📈 Recent stock grades:")
            for grade in recent_grades:
                print(f"   {grade[0]} - {grade[1]}: {grade[2]} ({grade[3]}) on {grade[4]} from {grade[5]}")
        
        # Check consensus table
        cursor.execute("SELECT COUNT(*) FROM stock_grade_consensus")
        consensus_count = cursor.fetchone()[0]
        print(f"\n🎯 Consensus data for symbols: {consensus_count}")
        
        if consensus_count > 0:
            cursor.execute("""
                SELECT symbol, consensus_rating, consensus_score, total_analysts, last_updated
                FROM stock_grade_consensus 
                ORDER BY total_analysts DESC 
                LIMIT 5
            """)
            consensus_data = cursor.fetchall()
            print(f"\n📊 Top consensus data:")
            for consensus in consensus_data:
                print(f"   {consensus[0]}: {consensus[1]} (score: {consensus[2]}, analysts: {consensus[3]})")
        
        # Check grade change events (trigger should create these)
        cursor.execute("SELECT COUNT(*) FROM grade_change_events")
        events_count = cursor.fetchone()[0]
        print(f"\n🔔 Grade change events triggered: {events_count}")
        
        if events_count > 0:
            cursor.execute("""
                SELECT symbol, event_type, grading_company, previous_grade, new_grade, created_at
                FROM grade_change_events 
                ORDER BY created_at DESC 
                LIMIT 5
            """)
            recent_events = cursor.fetchall()
            print(f"\n📅 Recent grade change events:")
            for event in recent_events:
                print(f"   {event[0]} - {event[1]} by {event[2]}: {event[3]} → {event[4]} at {event[5]}")
        
        # Check consensus change events (trigger should create these)
        cursor.execute("SELECT COUNT(*) FROM consensus_change_events")
        consensus_events_count = cursor.fetchone()[0]
        print(f"\n🔄 Consensus change events triggered: {consensus_events_count}")
        
        if consensus_events_count > 0:
            cursor.execute("""
                SELECT symbol, consensus_change, significance_level, market_impact, created_at
                FROM consensus_change_events 
                ORDER BY created_at DESC 
                LIMIT 5
            """)
            consensus_events = cursor.fetchall()
            print(f"\n📈 Recent consensus change events:")
            for event in consensus_events:
                print(f"   {event[0]}: {event[1]} (significance: {event[2]}, impact: {event[3]}) at {event[4]}")
        
        # Check alert queue (trigger should populate this)
        cursor.execute("SELECT COUNT(*) FROM consensus_alert_queue")
        alert_queue_count = cursor.fetchone()[0]
        print(f"\n📬 Alerts in queue: {alert_queue_count}")
        
        if alert_queue_count > 0:
            cursor.execute("""
                SELECT symbol, consensus_change, priority, severity, status, created_at
                FROM consensus_alert_queue 
                ORDER BY created_at DESC 
                LIMIT 5
            """)
            alerts = cursor.fetchall()
            print(f"\n🚨 Recent alerts queued:")
            for alert in alerts:
                print(f"   {alert[0]}: {alert[1]} ({alert[2]} priority, {alert[3]} severity) - {alert[4]}")
        
        cursor.close()
        conn.close()
        
        print(f"\n✅ Stock grades system test completed!")
        print(f"📈 Grades: {grades_count}, Consensus: {consensus_count}")
        print(f"🔔 Events: {events_count + consensus_events_count}, Alerts: {alert_queue_count}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error testing stock grades data: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_stock_grades_data()
