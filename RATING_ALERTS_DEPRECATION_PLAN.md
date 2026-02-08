# Rating Alerts API Deprecation Plan

## Overview
Migrate from `/api/v1/rating-alerts/*` to `/api/v1/universal-alerts/*` for unified alert management.

## Deprecation Timeline
- **Phase 1** (Immediate): Mark rating-alerts as deprecated
- **Phase 2** (2 weeks): Add migration helpers
- **Phase 3** (1 month): Remove rating-alerts endpoints

## Functionality Mapping

### 1. Alert Management
| Rating Alerts | Universal Alerts | Status |
|--------------|------------------|---------|
| `POST /rating-alerts/alerts` | `POST /universal-alerts/alerts` | ✅ Direct mapping |
| `GET /rating-alerts/alerts` | `GET /universal-alerts/alerts` | ✅ Direct mapping |
| `PUT /rating-alerts/alerts/{id}` | `PUT /universal-alerts/alerts/{id}` | ✅ Direct mapping |
| `DELETE /rating-alerts/alerts/{id}` | `DELETE /universal-alerts/alerts/{id}` | ✅ Direct mapping |
| `GET /rating-alerts/alerts/{id}` | `GET /universal-alerts/alerts/{id}` | ✅ Direct mapping |

### 2. Rating Data Management
| Rating Alerts | Universal Alerts | Migration Strategy |
|--------------|------------------|------------------|
| `GET /rating-alerts/ratings/{symbol}` | Use data collection plugins | 🔄 Create rating-data plugin |
| `POST /rating-alerts/ratings/update/{symbol}` | Use data collection plugins | 🔄 Create rating-data plugin |
| `POST /rating-alerts/ratings/batch-update` | Use data collection plugins | 🔄 Create rating-data plugin |
| `GET /rating-alerts/ratings/statistics` | `GET /universal-alerts/statistics` | ✅ Direct mapping |

### 3. Alert-Specific Features
| Rating Alerts | Universal Alerts | Migration Strategy |
|--------------|------------------|------------------|
| `POST /rating-alerts/alerts/{id}/add-symbols` | Update alert entity_filters | ✅ Entity filter approach |
| `DELETE /rating-alerts/alerts/{id}/symbols/{symbol}` | Update alert entity_filters | ✅ Entity filter approach |
| `GET /rating-alerts/alerts/{id}/symbols` | Get alert entity_filters | ✅ Entity filter approach |
| `GET /rating-alerts/alert-types` | Use alert_type field | ✅ Built-in functionality |

### 4. Subscriptions & Setup
| Rating Alerts | Universal Alerts | Migration Strategy |
|--------------|------------------|------------------|
| `POST /rating-alerts/subscriptions` | Create alerts with subscription filters | 🔄 Alert templates |
| `GET /rating-alerts/subscriptions` | Filter alerts by subscription type | 🔄 Alert templates |
| `POST /rating-alerts/setup/top-stocks` | Create alerts with predefined entity_filters | 🔄 Alert templates |
| `POST /rating-alerts/setup/watchlist` | Create alerts with predefined entity_filters | 🔄 Alert templates |
| `GET /rating-alerts/summary` | `GET /universal-alerts/statistics` | ✅ Enhanced statistics |

## Implementation Steps

### Step 1: Add Deprecation Headers
Add deprecation warnings to all rating-alerts endpoints:
```http
HTTP/1.1 200 OK
Deprecation: true
Link: </api/v1/universal-alerts/alerts>; rel="successor-version"
Warning: 299 - "This endpoint is deprecated. Use /api/v1/universal-alerts/alerts instead"
```

### Step 2: Create Migration Helpers
Add helper endpoints to assist migration:
```python
# Migrate rating alerts to universal alerts
POST /api/v1/migration/rating-to-universal-alerts

# Get migration status
GET /api/v1/migration/status

# Validate migration
POST /api/v1/migration/validate
```

### Step 3: Update Alert Types
Add rating-specific alert types to universal alerts:
```python
RATING_ALERT_TYPES = [
    "rating_upgrade",
    "rating_downgrade", 
    "rating_initiated",
    "rating_suspended",
    "price_target_change",
    "analyst_recommendation"
]
```

### Step 4: Create Rating Data Plugin
Implement rating data collection as a universal alerts plugin:
```python
class RatingDataPlugin:
    def collect_data(self, symbols):
        # Rating data collection logic
        pass
    
    def process_events(self, data):
        # Convert rating changes to alert events
        pass
```

### Step 5: Alert Templates
Create predefined alert templates for common rating setups:
```python
ALERT_TEMPLATES = {
    "top_stocks_alert": {
        "alert_type": "rating_change",
        "entity_filters": {"symbols": ["AAPL", "MSFT", "GOOGL"]},
        "event_filters": {"include_upgrades": True, "include_downgrades": True}
    },
    "watchlist_alert": {
        "alert_type": "rating_change", 
        "entity_filters": {"symbols": []},  # User's watchlist
        "event_filters": {"tier_1_firms_only": True}
    }
}
```

## Client Migration Guide

### Before (Rating Alerts):
```python
# Create rating alert
response = requests.post("/api/v1/rating-alerts/alerts", json={
    "name": "My Rating Alert",
    "symbols": ["AAPL", "MSFT"],
    "alert_types": ["upgrade", "downgrade"]
})

# Add symbols
requests.post(f"/api/v1/rating-alerts/alerts/{alert_id}/add-symbols", json={
    "symbols": ["GOOGL"]
})
```

### After (Universal Alerts):
```python
# Create equivalent universal alert
response = requests.post("/api/v1/universal-alerts/alerts", json={
    "alert_name": "My Rating Alert",
    "alert_type": "grade_change",
    "entity_filters": {"symbols": ["AAPL", "MSFT"]},
    "event_filters": {
        "include_upgrades": True,
        "include_downgrades": True
    }
})

# Add symbols (update entity filters)
requests.put(f"/api/v1/universal-alerts/alerts/{alert_id}", json={
    "entity_filters": {"symbols": ["AAPL", "MSFT", "GOOGL"]}
})
```

## Benefits of Migration

1. **Unified Interface**: Single API for all alert types
2. **Enhanced Features**: Access to analytics, bulk operations, templates
3. **Better Performance**: Optimized data collection and event processing
4. **Future-Proof**: Extensible plugin architecture
5. **Consistent UX**: Standardized alert management across all types

## Rollback Plan
If issues arise during migration:
1. Keep rating-alerts endpoints functional for 30 days post-deprecation
2. Provide automatic rollback for failed migrations
3. Maintain data compatibility layer
4. Monitor error rates and performance metrics

## Success Metrics
- 100% of rating-alerts traffic migrated to universal-alerts
- Zero data loss during migration
- Performance improvement >20%
- Client adoption rate >90% within 2 weeks
