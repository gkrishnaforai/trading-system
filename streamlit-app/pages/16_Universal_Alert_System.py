import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, timezone
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api_client import APIClient, APIError, APIConnectionError
from api_config import api_config


python_client = APIClient(api_config.python_worker_url, timeout=30)


def get_user_id() -> str:
    return st.session_state.get('user_id', '4f8b2cb1-4ed6-4fb5-bd44-48e5acc830a4')


def ua_get(endpoint: str, params=None):
    try:
        return python_client.get(f"api/v1/universal-alerts/{endpoint.lstrip('/')}", params=params)
    except (APIConnectionError, APIError) as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def ua_post(endpoint: str, data=None, params=None):
    try:
        return python_client.post(f"api/v1/universal-alerts/{endpoint.lstrip('/')}", json_data=data, params=params)
    except (APIConnectionError, APIError) as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def ua_put(endpoint: str, data=None, params=None):
    try:
        return python_client.put(f"api/v1/universal-alerts/{endpoint.lstrip('/')}", json_data=data, params=params)
    except (APIConnectionError, APIError) as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def ua_delete(endpoint: str, params=None):
    try:
        return python_client.delete(f"api/v1/universal-alerts/{endpoint.lstrip('/')}", params=params)
    except (APIConnectionError, APIError) as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _ensure_list(x):
    if not x:
        return []
    if isinstance(x, list):
        return x
    return [x]


def _parse_dt(value: str):
    try:
        if not value:
            return None
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def main():
    st.set_page_config(page_title="Universal Alert System", page_icon="🚨", layout="wide")
    st.title("🚨 Universal Alert System")

    user_id = get_user_id()

    with st.expander("➕ Create Alert", expanded=False):
        with st.form("ua_create_alert_form"):
            c1, c2, c3 = st.columns([2, 1, 1])
            with c1:
                alert_name = st.text_input("Alert name", value="Global Grade Changes", key="ua_create_alert_name").strip()
            with c2:
                alert_type = st.text_input("Alert type", value="grade_change", key="ua_create_alert_type").strip()
            with c3:
                priority_level = st.number_input("Priority (1-5)", min_value=1, max_value=5, value=3, step=1, key="ua_create_priority")

            symbols_csv = st.text_input("Symbols (comma-separated) - leave blank for global", value="", key="ua_create_symbols").strip()
            channels = st.multiselect("Notification channels", options=["email", "sms", "push"], default=["email"], key="ua_create_channels")
            is_test = st.checkbox("Test alert", value=False, key="ua_create_is_test")

            submitted = st.form_submit_button("Create")

        if submitted:
            if not alert_name:
                st.error("Alert name cannot be empty")
            elif not alert_type:
                st.error("Alert type cannot be empty")
            elif not channels:
                st.error("Select at least one notification channel")
            else:
                entity_filters = {"entity_types": ["stock"]}
                if symbols_csv:
                    symbols = [s.strip().upper() for s in symbols_csv.split(",") if s.strip()]
                    if symbols:
                        entity_filters["symbols"] = symbols

                payload = {
                    "alert_name": alert_name,
                    "alert_type": alert_type,
                    "alert_category": "custom",
                    "entity_filters": entity_filters,
                    "event_filters": {},
                    "trigger_conditions": {},
                    "suppression_rules": {},
                    "notification_config": {"channels": channels},
                    "template_config": {},
                    "priority_level": int(priority_level),
                    "is_test": bool(is_test),
                }

                resp = ua_post("alerts", data=payload, params={"user_id": user_id})
                if resp.get("success"):
                    st.success(f"Created alert: {resp.get('alert_id')}")
                else:
                    st.error(resp.get("error") or "Failed to create alert")

    with st.expander("🧭 Event Type Coverage (Capabilities vs Observed)", expanded=False):
        st.caption("Shows which event types the system supports (plugins/evaluators), which event types are being produced, and whether you have alerts configured.")
        coverage_resp = ua_get("admin/event-type-coverage", params={"user_id": user_id})
        if not coverage_resp.get("success"):
            st.error(coverage_resp.get("error") or "Failed to load coverage report")
        else:
            report = coverage_resp.get("report") or {}
            rows = report.get("coverage") or []
            if not rows:
                st.info("No coverage data")
            else:
                df = pd.DataFrame(rows)
                preferred_cols = [
                    "event_type",
                    "supported",
                    "has_evaluator",
                    "observed_total",
                    "observed_pending",
                    "active_alerts",
                    "inactive_alerts",
                    "supported_by_data_source",
                    "last_event_at",
                ]
                cols = [c for c in preferred_cols if c in df.columns]
                st.dataframe(df[cols] if cols else df, width="stretch")

                st.markdown("#### Quick actions")
                event_types = sorted([r.get("event_type") for r in rows if r.get("event_type")])
                selected_type = st.selectbox("Event type", options=event_types, key="ua_cov_event_type")

                c1, c2, c3 = st.columns(3)
                with c1:
                    if st.button("Create global alert for this type", key="ua_cov_create_global"):
                        payload = {
                            "alert_name": f"Global {selected_type}",
                            "alert_type": selected_type,
                            "alert_category": "custom",
                            "entity_filters": {"entity_types": ["stock"]},
                            "event_filters": {},
                            "trigger_conditions": {},
                            "suppression_rules": {},
                            "notification_config": {"channels": ["email"]},
                            "template_config": {},
                            "priority_level": 3,
                            "is_test": False,
                        }
                        resp = ua_post("alerts", data=payload, params={"user_id": user_id})
                        if resp.get("success"):
                            st.success(f"Created: {resp.get('alert_id')}")
                        else:
                            st.error(resp.get("error") or "Failed to create alert")

                with c2:
                    if st.button("Activate all alerts of this type", key="ua_cov_activate_type"):
                        ids = []
                        all_alerts = ua_get("alerts", params={"user_id": user_id}).get("alerts", [])
                        for a in all_alerts:
                            if a.get("alert_type") == selected_type and a.get("alert_id"):
                                ids.append(a.get("alert_id"))
                        if not ids:
                            st.info("No alerts of this type found")
                        else:
                            resp = ua_post(
                                "admin/alerts/bulk-action",
                                data={"alert_ids": ids, "action": "activate"},
                                params={"user_id": user_id},
                            )
                            if resp.get("success"):
                                st.success(f"Activated: {resp.get('processed', 0)}, Failed: {resp.get('failed', 0)}")
                            else:
                                st.error(resp.get("error") or "Failed to activate alerts")

                with c3:
                    if st.button("Deactivate all alerts of this type", key="ua_cov_deactivate_type"):
                        ids = []
                        all_alerts = ua_get("alerts", params={"user_id": user_id}).get("alerts", [])
                        for a in all_alerts:
                            if a.get("alert_type") == selected_type and a.get("alert_id"):
                                ids.append(a.get("alert_id"))
                        if not ids:
                            st.info("No alerts of this type found")
                        else:
                            resp = ua_post(
                                "admin/alerts/bulk-action",
                                data={"alert_ids": ids, "action": "deactivate"},
                                params={"user_id": user_id},
                            )
                            if resp.get("success"):
                                st.success(f"Deactivated: {resp.get('processed', 0)}, Failed: {resp.get('failed', 0)}")
                            else:
                                st.error(resp.get("error") or "Failed to deactivate alerts")

    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        st.caption(f"User: {user_id}")
    with col2:
        lookback_minutes = st.number_input("New alerts lookback (minutes)", min_value=5, max_value=7 * 24 * 60, value=120, step=5)
    with col3:
        auto_refresh = st.checkbox("Auto-refresh", value=False)

    if auto_refresh:
        st.caption("Auto-refresh is enabled. Use sparingly in development.")
        st.session_state["_ua_last_refresh"] = datetime.utcnow().isoformat()
        st.rerun()

    tabs = st.tabs([
        "🔔 New Alerts",
        "📋 All Alerts",
        "📨 Notifications",
        "⚙️ Event Processing"
    ])

    with tabs[0]:
        st.markdown("### 🔔 New Alerts")
        st.markdown("*Alerts created recently (polling by created_at)*")

        alerts_resp = ua_get("alerts", params={"user_id": user_id})
        if not alerts_resp.get("success"):
            st.error(alerts_resp.get("error") or "Failed to load alerts")
        else:
            alerts = alerts_resp.get("alerts", [])
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=int(lookback_minutes))
            recent = []
            for a in alerts:
                created_at = _parse_dt(a.get("created_at"))
                if created_at and created_at >= cutoff:
                    recent.append(a)

            st.write(f"**Recent alerts:** {len(recent)}")
            if recent:
                df = pd.DataFrame(recent)
                cols = [c for c in ["alert_name", "alert_type", "priority_level", "is_active", "created_at"] if c in df.columns]
                st.dataframe(df[cols] if cols else df, width='stretch')
            else:
                st.info("No new alerts in the selected window")

    with tabs[1]:
        st.markdown("### 📋 All Alerts")

        alerts_resp = ua_get("alerts", params={"user_id": user_id})
        if not alerts_resp.get("success"):
            st.error(alerts_resp.get("error") or "Failed to load alerts")
        else:
            alerts = alerts_resp.get("alerts", [])
            if not alerts:
                st.info("No alerts")
            else:
                options = {
                    f"{a.get('alert_name','(no name)')} [{a.get('alert_type','')}]": a
                    for a in alerts
                    if a.get("alert_id")
                }

                st.markdown("#### Manage")
                selected_label = st.selectbox("Select alert", options=list(options.keys()), key="ua_manage_alert_select")
                selected_alert = options[selected_label]

                with st.expander("Update alert", expanded=False):
                    with st.form("ua_update_alert_form"):
                        c1, c2, c3 = st.columns([2, 1, 1])
                        with c1:
                            upd_name = st.text_input(
                                "Alert name",
                                value=str(selected_alert.get("alert_name") or ""),
                                key="ua_update_name",
                            ).strip()
                        with c2:
                            upd_type = st.text_input(
                                "Alert type",
                                value=str(selected_alert.get("alert_type") or ""),
                                key="ua_update_type",
                            ).strip()
                        with c3:
                            upd_priority = st.number_input(
                                "Priority (1-5)",
                                min_value=1,
                                max_value=5,
                                value=int(selected_alert.get("priority_level") or 3),
                                step=1,
                                key="ua_update_priority",
                            )

                        current_symbols = (selected_alert.get("entity_filters") or {}).get("symbols") or []
                        upd_symbols_csv = st.text_input(
                            "Symbols (comma-separated) - leave blank for global",
                            value=",".join(current_symbols),
                            key="ua_update_symbols",
                        ).strip()
                        current_channels = (selected_alert.get("notification_config") or {}).get("channels") or []
                        upd_channels = st.multiselect(
                            "Notification channels",
                            options=["email", "sms", "push"],
                            default=list(current_channels) if current_channels else ["email"],
                            key="ua_update_channels",
                        )
                        upd_is_test = st.checkbox(
                            "Test alert",
                            value=bool(selected_alert.get("is_test") or False),
                            key="ua_update_is_test",
                        )
                        upd_is_active = st.checkbox(
                            "Active",
                            value=bool(selected_alert.get("is_active") if selected_alert.get("is_active") is not None else True),
                            key="ua_update_is_active",
                        )

                        save = st.form_submit_button("Save changes")

                    if save:
                        if not upd_name:
                            st.error("Alert name cannot be empty")
                        elif not upd_type:
                            st.error("Alert type cannot be empty")
                        elif not upd_channels:
                            st.error("Select at least one notification channel")
                        else:
                            entity_filters = {"entity_types": ["stock"]}
                            if upd_symbols_csv:
                                symbols = [s.strip().upper() for s in upd_symbols_csv.split(",") if s.strip()]
                                if symbols:
                                    entity_filters["symbols"] = symbols

                            payload = {
                                "alert_name": upd_name,
                                "alert_type": upd_type,
                                "alert_category": selected_alert.get("alert_category") or "custom",
                                "entity_filters": entity_filters,
                                "event_filters": selected_alert.get("event_filters") or {},
                                "trigger_conditions": selected_alert.get("trigger_conditions") or {},
                                "suppression_rules": selected_alert.get("suppression_rules") or {},
                                "notification_config": {"channels": upd_channels},
                                "template_config": selected_alert.get("template_config") or {},
                                "priority_level": int(upd_priority),
                                "is_test": bool(upd_is_test),
                            }

                            resp = ua_put(f"alerts/{selected_alert.get('alert_id')}", data=payload, params={"user_id": user_id})
                            if resp.get("success"):
                                st.success("Alert updated")
                            else:
                                st.error(resp.get("error") or "Failed to update alert")

                            active_update = ua_post(
                                "admin/alerts/bulk-action",
                                data={
                                    "alert_ids": [selected_alert.get("alert_id")],
                                    "action": "activate" if upd_is_active else "deactivate",
                                },
                                params={"user_id": user_id},
                            )
                            if not active_update.get("success"):
                                st.warning(active_update.get("error") or "Failed to update active flag")

                with st.expander("Delete alert", expanded=False):
                    confirm_one = st.checkbox("I understand this will permanently delete the alert", value=False, key="ua_delete_one_confirm")
                    if st.button("Delete selected alert", disabled=not confirm_one, key="ua_delete_one"):
                        resp = ua_delete(f"alerts/{selected_alert.get('alert_id')}", params={"user_id": user_id})
                        if resp.get("success"):
                            st.success("Alert deleted")
                            st.rerun()
                        else:
                            st.error(resp.get("error") or "Failed to delete alert")

                with st.expander("Delete ALL alerts", expanded=False):
                    confirm_all = st.checkbox("I understand this will permanently delete ALL alerts for this user", value=False, key="ua_delete_all_confirm")
                    if st.button("Delete ALL alerts", disabled=not confirm_all, key="ua_delete_all"):
                        deleted = 0
                        failed = 0
                        for a in alerts:
                            aid = a.get("alert_id")
                            if not aid:
                                continue
                            resp = ua_delete(f"alerts/{aid}", params={"user_id": user_id})
                            if resp.get("success"):
                                deleted += 1
                            else:
                                failed += 1
                        st.success(f"Deleted: {deleted}, Failed: {failed}")
                        st.rerun()

                df = pd.DataFrame(alerts)
                cols = [c for c in ["alert_name", "alert_type", "priority_level", "is_active", "created_at", "alert_id"] if c in df.columns]
                st.dataframe(df[cols] if cols else df, width='stretch')

    with tabs[2]:
        st.markdown("### 📨 Notifications")
        st.markdown("*Shows queued/sent notifications per alert*\n")

        alerts_resp = ua_get("alerts", params={"user_id": user_id})
        if not alerts_resp.get("success"):
            st.error(alerts_resp.get("error") or "Failed to load alerts")
        else:
            alerts = alerts_resp.get("alerts", [])
            options = {f"{a.get('alert_name','(no name)')} [{a.get('alert_type','')}]": a.get("alert_id") for a in alerts if a.get("alert_id")}
            if not options:
                st.info("No alerts found")
            else:
                selected_label = st.selectbox("Select alert", options=list(options.keys()))
                alert_id = options[selected_label]

                with st.expander("Clear notifications", expanded=False):
                    confirm_clear_one = st.checkbox("I understand this will permanently delete notification records for this alert", value=False, key="ua_clear_notif_one_confirm")
                    if st.button("Clear notifications for selected alert", disabled=not confirm_clear_one, key="ua_clear_notif_one"):
                        resp = ua_delete(f"notifications/alert/{alert_id}", params={"user_id": user_id})
                        if resp.get("success"):
                            st.success(f"Cleared: {resp.get('deleted_count', 0)}")
                        else:
                            st.error(resp.get("error") or "Failed to clear notifications")

                    confirm_clear_all = st.checkbox("I understand this will permanently delete ALL notification records for this user", value=False, key="ua_clear_notif_all_confirm")
                    if st.button("Clear ALL notifications for this user", disabled=not confirm_clear_all, key="ua_clear_notif_all"):
                        resp = ua_delete("notifications/clear", params={"user_id": user_id})
                        if resp.get("success"):
                            st.success(f"Cleared: {resp.get('deleted_count', 0)}")
                        else:
                            st.error(resp.get("error") or "Failed to clear notifications")

                notif = ua_get(f"notifications/alert/{alert_id}")
                if not notif.get("success"):
                    st.error(notif.get("error") or "Failed to load notifications")
                else:
                    notifications = notif.get("notifications", [])
                    st.write(f"**Notifications:** {len(notifications)}")
                    if notifications:
                        st.dataframe(pd.DataFrame(notifications), width='stretch')
                    else:
                        st.info("No notifications for this alert yet")

    with tabs[3]:
        st.markdown("### ⚙️ Event Processing")
        st.markdown("*Collects events from plugins and processes pending events*\n")

        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**Collect grade events (DB-backed)**")
            symbol = st.text_input("Symbol", value="MU", key="ua_collect_symbol").strip().upper()
            days = st.number_input("Days", min_value=1, max_value=365, value=30, step=1, key="ua_collect_days")
            if st.button("📥 Collect", key="ua_collect"):
                payload = {
                    "analyst_grades": {"sources": ["fmp"], "symbols": [symbol], "days": int(days)}
                }
                st.json(ua_post("data-collection/collect", data=payload))

        with col_b:
            st.markdown("**Pending events**")
            pending = ua_get("events/pending", params={"event_type": "grade_change", "limit": 50})
            if pending.get("success"):
                events = pending.get("events", [])
                st.write(f"**Pending grade_change:** {len(events)}")
                if events:
                    if st.button("⚡ Process first", key="ua_process_first"):
                        st.json(ua_post("events", data={
                            "event_type": events[0].get("event_type"),
                            "entity_type": events[0].get("entity_type"),
                            "entity_id": events[0].get("entity_id"),
                            "event_data": events[0].get("event_data"),
                            "previous_data": events[0].get("previous_data"),
                            "change_metadata": events[0].get("change_metadata"),
                            "event_timestamp": events[0].get("event_timestamp"),
                            "data_source": events[0].get("data_source"),
                            "source_id": events[0].get("source_id"),
                            "confidence_score": events[0].get("confidence_score"),
                            "priority": events[0].get("priority"),
                            "correlation_id": events[0].get("correlation_id"),
                            "tags": events[0].get("tags", [])
                        }))
                else:
                    st.info("No pending events")
            else:
                st.error(pending.get("error") or "Failed to load pending events")


if __name__ == "__main__":
    main()

