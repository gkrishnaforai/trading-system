# Alerts Architecture (Python Worker)

## Purpose

The alerts system is a **pluggable evaluation + notification framework** that can be triggered by:

- On-demand user actions (UI/API)
- Scheduled/periodic workers
- Event-driven pipelines (e.g., earnings/day-bound events)

It is designed to stay **DRY** (single source of truth per concept) and **SOLID** (clear separation of responsibilities).

---

## Core Components

### 1) `AlertService` (`app/alerts/service.py`)

**Responsibilities**

- CRUD for user alerts (`alerts` table)
- Evaluate alerts against an `AlertContext`
- Send notifications via channel plugins
- Persist notification history (`alert_notifications` table)

**Not responsible for**

- Fetching market data
- Scheduling/cron
- Building complex event timelines (earnings calendar, etc.)

Those belong in refresh/index services and workers.

### 2) Plugin Interface (`app/alerts/base.py`)

- `BaseAlertPlugin.evaluate(context, config) -> AlertResult`
- `BaseAlertPlugin.send_notification(...)`

New alert types should be implemented as plugins (or as sub-logic in an existing plugin) and registered via the registry.

### 3) Registry (`app/alerts/registry.py`)

- Central registry for alert plugins.
- Supports mapping DB `alert_types.plugin_name` to a Python plugin class.

---

## Data Model (Conceptual)

Alerts are evaluated against a **context**, not directly against raw tables.

- `alerts`: user configuration (what to watch, thresholds, channels)
- `alert_types`: catalog of alert types (name, plugin, schema)
- `alert_notifications`: history
- `notification_channels`: how to reach the user

---

## Earnings-Driven Alerts / Scheduling (Best Practice)

### Source of Truth vs Read Model

- **Source of truth** (event history): `earnings_data`
  - Contains `earnings_date` plus best-practice fields: `earnings_at TIMESTAMPTZ`, `earnings_timezone`, `earnings_session`.
- **Read model** (fast lookup for UI/schedulers/alerts): `stocks.next_earnings_*`
  - `next_earnings_at` is the canonical timestamp for scheduling.

### Indexing Contract

`EarningsIndexService` (service layer) maintains:

- `stocks.next_earnings_at`
- `stocks.next_earnings_timezone`
- `stocks.next_earnings_session`
- `stocks.next_earnings_time` (display)

**Trigger points**

- After earnings refresh/upsert completes (e.g., `DataRefreshManager._refresh_earnings`).

**Why**

- UI calendar, schedulers, alerts, and agents should not each re-derive “next earnings”.
- They should all depend on `stocks.next_earnings_at` (DRY).

---

## Where to Add Functionality

### A) Add a new alert type (example: `earnings_upcoming`)

1. **DB**: insert row into `alert_types`
   - `alert_type_id`: `earnings_upcoming`
   - `plugin_name`: choose existing channel plugin (email/sms) or new plugin
   - `config_schema`: e.g. `{ "days_before": int, "sessions": [..] }`

2. **Plugin**: implement evaluation logic
   - Prefer reading from `stocks.next_earnings_at` (read model)
   - Do not query provider APIs from alert evaluation

3. **Context Builder** (outside alerts)
   - Ensure `AlertContext.metadata` includes earnings fields if the plugin needs them.

### B) Add a new event-driven data source

Example: dividends, splits, FDA approvals, economic events.

Pattern:

1. Create/extend an **events table** (source of truth)
2. Create a **read model** on `stocks` (or a dedicated materialized table)
3. Add an **index service** to keep the read model updated after refresh
4. Alerts read the read model, not the raw provider output

### C) Add new notification channels

- Implement a new plugin that supports `NotificationChannel` (push/webhook).
- Extend `AlertService._get_plugin_for_channel` mapping.

---

## Guardrails (DRY/SOLID)

- **Alerts evaluate; they do not fetch.**
- **Workers refresh data; services build derived indexes.**
- **UI reads read models / endpoints, not provider APIs.**
- Prefer one canonical place to compute a derived concept (e.g. “next earnings”).

---

## Quick References

- CRUD + evaluate: `app/alerts/service.py`
- Plugin contract: `app/alerts/base.py`
- Plugin registry: `app/alerts/registry.py`
- Earnings indexing: `app/services/earnings_index_service.py`
- Calendar UI query endpoint: `GET /admin/upcoming-earnings`
