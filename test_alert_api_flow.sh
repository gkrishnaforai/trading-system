#!/bin/bash

# Universal Alert System API Test Suite
# Tests complete flow: Create Alert -> Schedule -> Run -> Send Notification
# For Analyst Grades and Earnings Calendar alerts

set -e  # Exit on any error

# Configuration
API_BASE="http://localhost:8001/api/v1/universal-alerts"
USER_ID="4f8b2cb1-4ed6-4fb5-bd44-48e5acc830a4"
TIMESTAMP=$(date +%s)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Test API connectivity
test_api_connectivity() {
    log_info "Testing API connectivity..."
    
    response=$(curl -s -w "%{http_code}" "$API_BASE/health" || echo "000")
    http_code="${response: -3}"
    body="${response%???}"
    
    if [ "$http_code" = "200" ]; then
        log_success "API is accessible"
        echo "$body" | jq '.'
    else
        log_error "API not accessible (HTTP $http_code)"
        exit 1
    fi
}

# Test 1: Create Analyst Grade Change Alert
test_analyst_grade_alert() {
    log_info "=== Test 1: Creating Analyst Grade Change Alert ==="
    
    alert_data='{
        "alert_name": "Test Analyst Grade Alert '$TIMESTAMP'",
        "alert_type": "grade_change",
        "alert_category": "custom",
        "entity_filters": {
            "symbols": ["AAPL", "MSFT", "GOOGL"]
        },
        "event_filters": {
            "min_confidence": 0.7,
            "min_priority": 2,
            "data_sources": ["fmp"],
            "include_upgrades": true,
            "include_downgrades": true,
            "tier_1_firms_only": false
        },
        "trigger_conditions": {
            "cooldown_minutes": 60,
            "max_alerts_per_day": 10
        },
        "suppression_rules": {
            "suppress_duplicates": true,
            "suppress_weekends": false
        },
        "notification_config": {
            "channels": ["email"]
        },
        "template_config": {
            "email_template": "grade_change"
        },
        "priority_level": 3,
        "is_test": true
    }'
    
    log_info "Sending alert creation request..."
    response=$(curl -s -w "%{http_code}" \
        -X POST \
        -H "Content-Type: application/json" \
        -d "$alert_data" \
        "$API_BASE/alerts?user_id=$USER_ID" || echo "000")
    
    http_code="${response: -3}"
    body="${response%???}"
    
    if [ "$http_code" = "200" ]; then
        log_success "Analyst grade alert created successfully"
        alert_id=$(echo "$body" | jq -r '.alert_id')
        log_info "Alert ID: $alert_id"
        echo "$body" | jq '.'
        
        # Store alert ID for later tests
        echo "$alert_id" > /tmp/grade_alert_id.txt
    else
        log_error "Failed to create analyst grade alert (HTTP $http_code)"
        echo "$body"
        return 1
    fi
}

# Test 2: Create Earnings Calendar Alert
test_earnings_calendar_alert() {
    log_info "=== Test 2: Creating Earnings Calendar Alert ==="
    
    alert_data='{
        "alert_name": "Test Earnings Calendar Alert '$TIMESTAMP'",
        "alert_type": "earnings",
        "alert_category": "custom",
        "entity_filters": {
            "symbols": ["AAPL", "MSFT", "GOOGL", "TSLA"]
        },
        "event_filters": {
            "min_confidence": 0.8,
            "min_priority": 1,
            "data_sources": ["fmp"],
            "min_days_ahead": 7,
            "max_days_ahead": 1,
            "include_surprises": true
        },
        "trigger_conditions": {
            "cooldown_minutes": 120,
            "max_alerts_per_day": 5
        },
        "suppression_rules": {
            "suppress_duplicates": true,
            "suppress_weekends": true
        },
        "notification_config": {
            "channels": ["email"]
        },
        "template_config": {
            "email_template": "earnings"
        },
        "priority_level": 2,
        "is_test": true
    }'
    
    log_info "Sending earnings alert creation request..."
    response=$(curl -s -w "%{http_code}" \
        -X POST \
        -H "Content-Type: application/json" \
        -d "$alert_data" \
        "$API_BASE/alerts?user_id=$USER_ID" || echo "000")
    
    http_code="${response: -3}"
    body="${response%???}"
    
    if [ "$http_code" = "200" ]; then
        log_success "Earnings calendar alert created successfully"
        alert_id=$(echo "$body" | jq -r '.alert_id')
        log_info "Alert ID: $alert_id"
        echo "$body" | jq '.'
        
        # Store alert ID for later tests
        echo "$alert_id" > /tmp/earnings_alert_id.txt
    else
        log_error "Failed to create earnings calendar alert (HTTP $http_code)"
        echo "$body"
        return 1
    fi
}

# Test 3: List User Alerts
test_list_alerts() {
    log_info "=== Test 3: Listing User Alerts ==="
    
    response=$(curl -s -w "%{http_code}" \
        -X GET \
        "$API_BASE/alerts?user_id=$USER_ID" || echo "000")
    
    http_code="${response: -3}"
    body="${response%???}"
    
    if [ "$http_code" = "200" ]; then
        log_success "Alerts retrieved successfully"
        alert_count=$(echo "$body" | jq '.alerts | length')
        log_info "Found $alert_count alerts"
        echo "$body" | jq '.alerts[] | {alert_id, alert_name, alert_type, is_active}'
    else
        log_error "Failed to list alerts (HTTP $http_code)"
        echo "$body"
        return 1
    fi
}

# Test 4: Trigger Data Collection for Analyst Grades
test_collect_analyst_grades() {
    log_info "=== Test 4: Collecting Analyst Grades Data ==="
    
    collection_data='{
        "analyst_grades": {
            "sources": ["fmp"],
            "fmp_api_key": "demo",
            "symbols": ["AAPL", "MSFT", "GOOGL"]
        }
    }'
    
    log_info "Triggering analyst grades data collection..."
    response=$(curl -s -w "%{http_code}" \
        -X POST \
        -H "Content-Type: application/json" \
        -d "$collection_data" \
        "$API_BASE/data-collection/collect" || echo "000")
    
    http_code="${response: -3}"
    body="${response%???}"
    
    if [ "$http_code" = "200" ]; then
        log_success "Analyst grades data collection triggered"
        events_collected=$(echo "$body" | jq -r '.total_events_collected // 0')
        log_info "Events collected: $events_collected"
        echo "$body" | jq '.'
    else
        log_error "Failed to collect analyst grades data (HTTP $http_code)"
        echo "$body"
        return 1
    fi
}

# Test 5: Trigger Data Collection for Earnings Calendar
test_collect_earnings_calendar() {
    log_info "=== Test 5: Collecting Earnings Calendar Data ==="
    
    collection_data='{
        "earnings_calendar": {
            "sources": ["fmp"],
            "fmp_api_key": "demo"
        }
    }'
    
    log_info "Triggering earnings calendar data collection..."
    response=$(curl -s -w "%{http_code}" \
        -X POST \
        -H "Content-Type: application/json" \
        -d "$collection_data" \
        "$API_BASE/data-collection/collect" || echo "000")
    
    http_code="${response: -3}"
    body="${response%???}"
    
    if [ "$http_code" = "200" ]; then
        log_success "Earnings calendar data collection triggered"
        events_collected=$(echo "$body" | jq -r '.total_events_collected // 0')
        log_info "Events collected: $events_collected"
        echo "$body" | jq '.'
    else
        log_error "Failed to collect earnings calendar data (HTTP $http_code)"
        echo "$body"
        return 1
    fi
}

# Test 6: Process Events (Manual Trigger)
test_process_events() {
    log_info "=== Test 6: Processing Events ==="
    
    response=$(curl -s -w "%{http_code}" \
        -X POST \
        "$API_BASE/events/process" || echo "000")
    
    http_code="${response: -3}"
    body="${response%???}"
    
    if [ "$http_code" = "200" ]; then
        log_success "Event processing triggered"
        events_processed=$(echo "$body" | jq -r '.events_processed // 0')
        alerts_triggered=$(echo "$body" | jq -r '.alerts_triggered // 0')
        log_info "Events processed: $events_processed"
        log_info "Alerts triggered: $alerts_triggered"
        echo "$body" | jq '.'
    else
        log_error "Failed to process events (HTTP $http_code)"
        echo "$body"
        return 1
    fi
}

# Test 7: Check Alert Status
test_check_alert_status() {
    log_info "=== Test 7: Checking Alert Status ==="
    
    if [ -f "/tmp/grade_alert_id.txt" ]; then
        grade_alert_id=$(cat /tmp/grade_alert_id.txt)
        log_info "Checking grade alert status: $grade_alert_id"
        
        response=$(curl -s -w "%{http_code}" \
            -X GET \
            "$API_BASE/alerts/$grade_alert_id?user_id=$USER_ID" || echo "000")
        
        http_code="${response: -3}"
        body="${response%???}"
        
        if [ "$http_code" = "200" ]; then
            log_success "Grade alert status retrieved"
            echo "$body" | jq '.'
        else
            log_error "Failed to get grade alert status (HTTP $http_code)"
            echo "$body"
        fi
    fi
    
    if [ -f "/tmp/earnings_alert_id.txt" ]; then
        earnings_alert_id=$(cat /tmp/earnings_alert_id.txt)
        log_info "Checking earnings alert status: $earnings_alert_id"
        
        response=$(curl -s -w "%{http_code}" \
            -X GET \
            "$API_BASE/alerts/$earnings_alert_id?user_id=$USER_ID" || echo "000")
        
        http_code="${response: -3}"
        body="${response%???}"
        
        if [ "$http_code" = "200" ]; then
            log_success "Earnings alert status retrieved"
            echo "$body" | jq '.'
        else
            log_error "Failed to get earnings alert status (HTTP $http_code)"
            echo "$body"
        fi
    fi
}

# Test 8: Check Notification Queue
test_notification_queue() {
    log_info "=== Test 8: Checking Notification Queue ==="
    
    response=$(curl -s -w "%{http_code}" \
        -X GET \
        "$API_BASE/notifications/queue" || echo "000")
    
    http_code="${response: -3}"
    body="${response%???}"
    
    if [ "$http_code" = "200" ]; then
        log_success "Notification queue retrieved"
        queue_count=$(echo "$body" | jq '.notifications | length // 0')
        log_info "Notifications in queue: $queue_count"
        echo "$body" | jq '.notifications[] | {queue_id, channel_type, status, recipient}' 2>/dev/null || echo "$body"
    else
        log_error "Failed to get notification queue (HTTP $http_code)"
        echo "$body"
    fi
}

# Test 9: Process Notifications
test_process_notifications() {
    log_info "=== Test 9: Processing Notifications ==="
    
    response=$(curl -s -w "%{http_code}" \
        -X POST \
        "$API_BASE/notifications/process" || echo "000")
    
    http_code="${response: -3}"
    body="${response%???}"
    
    if [ "$http_code" = "200" ]; then
        log_success "Notification processing triggered"
        notifications_sent=$(echo "$body" | jq -r '.notifications_sent // 0')
        notifications_failed=$(echo "$body" | jq -r '.notifications_failed // 0')
        log_info "Notifications sent: $notifications_sent"
        log_info "Notifications failed: $notifications_failed"
        echo "$body" | jq '.'
    else
        log_error "Failed to process notifications (HTTP $http_code)"
        echo "$body"
        return 1
    fi
}

# Test 10: Check Audit Trail
test_audit_trail() {
    log_info "=== Test 10: Checking Audit Trail ==="
    
    response=$(curl -s -w "%{http_code}" \
        -X GET \
        "$API_BASE/audit-trail?limit=10" || echo "000")
    
    http_code="${response: -3}"
    body="${response%???}"
    
    if [ "$http_code" = "200" ]; then
        log_success "Audit trail retrieved"
        audit_count=$(echo "$body" | jq '.audit_records | length // 0')
        log_info "Audit records: $audit_count"
        echo "$body" | jq '.audit_records[] | {entity_type, operation_type, status, started_at}' 2>/dev/null || echo "$body"
    else
        log_error "Failed to get audit trail (HTTP $http_code)"
        echo "$body"
    fi
}

# Test 11: Get System Metrics
test_system_metrics() {
    log_info "=== Test 11: Getting System Metrics ==="
    
    response=$(curl -s -w "%{http_code}" \
        -X GET \
        "$API_BASE/metrics" || echo "000")
    
    http_code="${response: -3}"
    body="${response%???}"
    
    if [ "$http_code" = "200" ]; then
        log_success "System metrics retrieved"
        echo "$body" | jq '.metrics | {counters, gauges}'
    else
        log_error "Failed to get system metrics (HTTP $http_code)"
        echo "$body"
    fi
}

# Test 12: Update Alert (Test Edit Functionality)
test_update_alert() {
    log_info "=== Test 12: Updating Alert ==="
    
    if [ -f "/tmp/grade_alert_id.txt" ]; then
        grade_alert_id=$(cat /tmp/grade_alert_id.txt)
        
        update_data='{
            "alert_name": "Updated Analyst Grade Alert '$TIMESTAMP'",
            "alert_type": "grade_change",
            "alert_category": "custom",
            "entity_filters": {
                "symbols": ["AAPL", "MSFT"]
            },
            "event_filters": {
                "min_confidence": 0.8,
                "min_priority": 3,
                "data_sources": ["fmp"],
                "include_upgrades": true,
                "include_downgrades": false,
                "tier_1_firms_only": true
            },
            "trigger_conditions": {
                "cooldown_minutes": 30,
                "max_alerts_per_day": 15
            },
            "suppression_rules": {
                "suppress_duplicates": true,
                "suppress_weekends": false
            },
            "notification_config": {
                "channels": ["email"]
            },
            "priority_level": 4,
            "is_test": true
        }'
        
        log_info "Updating alert: $grade_alert_id"
        response=$(curl -s -w "%{http_code}" \
            -X PUT \
            -H "Content-Type: application/json" \
            -d "$update_data" \
            "$API_BASE/alerts/$grade_alert_id?user_id=$USER_ID" || echo "000")
        
        http_code="${response: -3}"
        body="${response%???}"
        
        if [ "$http_code" = "200" ]; then
            log_success "Alert updated successfully"
            echo "$body" | jq '.'
        else
            log_error "Failed to update alert (HTTP $http_code)"
            echo "$body"
        fi
    fi
}

# Test 13: Deactivate Alert
test_deactivate_alert() {
    log_info "=== Test 13: Deactivating Alert ==="
    
    if [ -f "/tmp/earnings_alert_id.txt" ]; then
        earnings_alert_id=$(cat /tmp/earnings_alert_id.txt)
        
        log_info "Deactivating alert: $earnings_alert_id"
        response=$(curl -s -w "%{http_code}" \
            -X PUT \
            -H "Content-Type: application/json" \
            -d '{"is_active": false}' \
            "$API_BASE/alerts/$earnings_alert_id?user_id=$USER_ID" || echo "000")
        
        http_code="${response: -3}"
        body="${response%???}"
        
        if [ "$http_code" = "200" ]; then
            log_success "Alert deactivated successfully"
            echo "$body" | jq '.'
        else
            log_error "Failed to deactivate alert (HTTP $http_code)"
            echo "$body"
        fi
    fi
}

# Test 14: Delete Alert (Cleanup)
test_delete_alert() {
    log_info "=== Test 14: Deleting Test Alerts ==="
    
    # Delete grade alert
    if [ -f "/tmp/grade_alert_id.txt" ]; then
        grade_alert_id=$(cat /tmp/grade_alert_id.txt)
        log_info "Deleting grade alert: $grade_alert_id"
        
        response=$(curl -s -w "%{http_code}" \
            -X DELETE \
            "$API_BASE/alerts/$grade_alert_id?user_id=$USER_ID" || echo "000")
        
        http_code="${response: -3}"
        body="${response%???}"
        
        if [ "$http_code" = "200" ]; then
            log_success "Grade alert deleted successfully"
        else
            log_error "Failed to delete grade alert (HTTP $http_code)"
            echo "$body"
        fi
        rm -f /tmp/grade_alert_id.txt
    fi
    
    # Delete earnings alert
    if [ -f "/tmp/earnings_alert_id.txt" ]; then
        earnings_alert_id=$(cat /tmp/earnings_alert_id.txt)
        log_info "Deleting earnings alert: $earnings_alert_id"
        
        response=$(curl -s -w "%{http_code}" \
            -X DELETE \
            "$API_BASE/alerts/$earnings_alert_id?user_id=$USER_ID" || echo "000")
        
        http_code="${response: -3}"
        body="${response%???}"
        
        if [ "$http_code" = "200" ]; then
            log_success "Earnings alert deleted successfully"
        else
            log_error "Failed to delete earnings alert (HTTP $http_code)"
            echo "$body"
        fi
        rm -f /tmp/earnings_alert_id.txt
    fi
}

# Test 15: Test Scheduled Jobs
test_scheduled_jobs() {
    log_info "=== Test 15: Testing Scheduled Jobs ==="
    
    # Get scheduled jobs status
    response=$(curl -s -w "%{http_code}" \
        -X GET \
        "$API_BASE/scheduled-jobs" || echo "000")
    
    http_code="${response: -3}"
    body="${response%???}"
    
    if [ "$http_code" = "200" ]; then
        log_success "Scheduled jobs retrieved"
        job_count=$(echo "$body" | jq '.jobs | length // 0')
        log_info "Scheduled jobs: $job_count"
        echo "$body" | jq '.jobs[] | {job_name, job_type, is_active, status}' 2>/dev/null || echo "$body"
    else
        log_error "Failed to get scheduled jobs (HTTP $http_code)"
        echo "$body"
    fi
}

# Main test execution
main() {
    log_info "Starting Universal Alert System API Test Suite"
    log_info "API Base: $API_BASE"
    log_info "User ID: $USER_ID"
    log_info "Timestamp: $TIMESTAMP"
    echo ""
    
    # Run all tests
    test_api_connectivity || exit 1
    echo ""
    
    test_analyst_grade_alert || exit 1
    echo ""
    
    test_earnings_calendar_alert || exit 1
    echo ""
    
    test_list_alerts || exit 1
    echo ""
    
    test_collect_analyst_grades || exit 1
    echo ""
    
    test_collect_earnings_calendar || exit 1
    echo ""
    
    test_process_events || exit 1
    echo ""
    
    test_check_alert_status || exit 1
    echo ""
    
    test_notification_queue || exit 1
    echo ""
    
    test_process_notifications || exit 1
    echo ""
    
    test_audit_trail || exit 1
    echo ""
    
    test_system_metrics || exit 1
    echo ""
    
    test_update_alert || exit 1
    echo ""
    
    test_deactivate_alert || exit 1
    echo ""
    
    test_scheduled_jobs || exit 1
    echo ""
    
    test_delete_alert || exit 1
    echo ""
    
    log_success "All tests completed successfully!"
    log_info "Test execution finished at $(date)"
}

# Check if jq is installed
if ! command -v jq &> /dev/null; then
    log_error "jq is required but not installed. Please install jq to run this test suite."
    log_info "Install with: brew install jq (macOS) or apt-get install jq (Ubuntu)"
    exit 1
fi

# Run main function
main "$@"
