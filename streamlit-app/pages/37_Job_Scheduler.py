"""Job Scheduler — CRUD for both scheduling layers.

Engine jobs (job_definitions): the AutoSys-style registry the worker
dispatcher fires — edit cron (UTC) + enable/disable + run-now.

Data schedules (schedules table): the go-api tick layer — timezone-aware
data_load / fair_value_warmup profiles with full create/edit/delete.
"""
import sys
import os
import json

import streamlit as st

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api_client import APIClient, get_go_api_client
from api_config import api_config
from utils import render_top_nav

client = APIClient(api_config.python_worker_url, timeout=120)
go = get_go_api_client()

st.set_page_config(page_title="Job Scheduler", page_icon="⏰", layout="wide")
render_top_nav()
st.title("⏰ Job Scheduler")
st.caption("engine jobs run on UTC crons via the worker dispatcher "
           "(missed slots catch up within dep_max_age_h) · data "
           "schedules run via the go-api tick with per-row timezone. "
           "Editing a cron is advisory plumbing — deterministic jobs "
           "still own the math.")


def _ago(ts):
    if not ts:
        return "—"
    from datetime import datetime, timezone
    try:
        t = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        s = (datetime.now(timezone.utc) - t).total_seconds()
        if s < 0:
            return f"in {-s/60:.0f}m"
        return (f"{s/86400:.1f}d ago" if s >= 86400 else
                f"{s/3600:.1f}h ago" if s >= 3600 else f"{s/60:.0f}m ago")
    except Exception:
        return str(ts)[:16]


# ============================================================
# ⚙️ engine jobs — job_definitions, worker dispatcher (UTC)
# ============================================================
st.subheader("⚙️ Engine jobs — worker dispatcher (UTC crons)")

try:
    _cat = (client.get("api/v1/board/jobs/catalog") or {}).get("jobs") or []
except Exception as e:
    st.error(f"catalog unavailable: {e}")
    _cat = []

if _cat:
    import pandas as pd
    _df = pd.DataFrame(_cat)[[
        "name", "label", "purpose", "kind", "cron", "enabled",
        "priority", "depends_on", "last_run", "next_run",
        "last_error"]]
    _df["last_run"] = _df["last_run"].apply(_ago)
    _df["next_run"] = _df["next_run"].astype(str).str[:16]

    _ed = st.data_editor(
        _df, hide_index=True, use_container_width=True,
        disabled=["name", "label", "purpose", "kind", "priority",
                  "depends_on", "last_run", "next_run", "last_error"],
        column_config={
            "cron": st.column_config.TextColumn(
                "cron (UTC)", help="min hour dom month dow — "
                "e.g. */30 12-22 * * 1-5"),
            "enabled": st.column_config.CheckboxColumn("enabled?"),
            "last_error": st.column_config.TextColumn(
                "last error", width="medium"),
        }, key="job_editor")

    c1, c2 = st.columns([1, 5])
    with c1:
        if st.button("💾 Save", key="job_save"):
            try:
                _orig = {r["name"]: r for r in _cat}
                _saved = 0
                for _, _r in _ed.iterrows():
                    _o = _orig.get(_r["name"]) or {}
                    _nc = (str(_r["cron"]).strip()
                           if str(_r["cron"]) != "nan" else "") or None
                    _ne = bool(_r["enabled"])
                    if _nc != (_o.get("cron") or None) \
                            or _ne != bool(_o.get("enabled")):
                        res = client.post(
                            f"api/v1/board/jobs/{_r['name']}/schedule",
                            json_data={"cron": _nc, "enabled": _ne})
                        if res.get("ok") is False:
                            st.error(f"{_r['name']}: {res.get('error')}")
                        else:
                            _saved += 1
                st.toast(f"saved {_saved} change(s)")
                st.cache_data.clear()
            except Exception as e:
                st.error(f"save failed: {e}")
    with c2:
        st.caption("cron is 5-field **UTC** · blank cron = manual-only · "
                   "`enabled` unchecked = never fires (buttons still work)")

    with st.expander("▶️ Run a job now"):
        _job = st.selectbox("job", [r["name"] for r in _cat],
                            key="run_job_sel")
        if st.button("Run now", key="run_job_btn"):
            try:
                r = client.post(f"api/v1/board/refresh/{_job}")
                st.toast(f"{_job}: {r.get('status', 'started')}")
            except Exception as e:
                st.error(f"{_job} failed to start: {e}")

    with st.expander("🧾 Recent runs (job_runs ledger)"):
        try:
            _runs = (client.get("api/v1/board/jobs/runs",
                                params={"limit": 80}) or {}
                     ).get("runs") or []
        except Exception:
            _runs = []
        if _runs:
            _rdf = pd.DataFrame(_runs)
            _rdf["ran_at"] = _rdf["ran_at"].astype(str).str[:19]
            _rdf["failed"] = _rdf["error"].notna()
            _rdf = _rdf[["name", "ran_at", "duration_s", "failed",
                         "error"]]
            st.dataframe(_rdf, hide_index=True, use_container_width=True)
        else:
            st.caption("no runs recorded yet")

# ============================================================
# 📥 data schedules — go-api `schedules` (TZ-aware)
# ============================================================
st.subheader("📥 Data schedules — go-api tick (per-row timezone)")

try:
    _sched = (go.get("api/v1/schedules") or {}).get("schedules") or []
except Exception as e:
    st.error(f"schedules unavailable: {e}")
    _sched = []

if _sched:
    import pandas as pd
    _sdf = pd.DataFrame(_sched)[[
        "schedule_id", "profile", "kind", "cron_expression", "timezone",
        "enabled", "next_run_at", "last_run_at"]]
    _sdf["schedule_id"] = _sdf["schedule_id"].astype(str).str[:8] + "…"
    _sdf["next_run_at"] = _sdf["next_run_at"].astype(str).str[:16]
    _sdf["last_run_at"] = _sdf["last_run_at"].apply(_ago)
    st.dataframe(_sdf, hide_index=True, use_container_width=True)

    st.markdown("**edit / delete / trigger**")
    for s in _sched:
        sid = s["schedule_id"]
        label = f"{s.get('profile') or '(unnamed)'} — {s['kind']} · " \
                f"`{s['cron_expression']}` {s['timezone']}"
        with st.expander(label):
            with st.form(f"sched_edit_{sid}"):
                a, b, c = st.columns(3)
                _cron = a.text_input("cron", value=s["cron_expression"])
                _tz = b.text_input("timezone", value=s["timezone"])
                _enabled = c.checkbox("enabled", value=s["enabled"])
                _cfg = st.text_area(
                    "config (JSON)",
                    value=s["config"] if isinstance(s.get("config"), str)
                    else json.dumps(s.get("config") or {}))
                _save = st.form_submit_button("💾 save")
            b1, b2, b3, _ = st.columns([1, 1, 1, 4])
            if b1.button("▶️ run now", key=f"rn_{sid}"):
                try:
                    go.post(f"api/v1/schedules/{sid}/run-now")
                    st.toast("run queued")
                except Exception as e:
                    st.error(str(e))
            if b2.button("⏰ make due now", key=f"dn_{sid}"):
                try:
                    go.post(f"api/v1/schedules/{sid}/make-due-now")
                    st.toast("marked due — next tick fires it")
                except Exception as e:
                    st.error(str(e))
            if b3.button("🗑 delete", key=f"del_{sid}"):
                try:
                    go.delete(f"api/v1/schedules/{sid}")
                    st.toast("deleted")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))
            if _save:
                try:
                    cfg = json.loads(_cfg) if _cfg.strip() else {}
                    go.patch(f"api/v1/schedules/{sid}", json_data={
                        "cron_expression": _cron, "timezone": _tz,
                        "enabled": _enabled, "config": cfg})
                    st.toast("saved")
                    st.rerun()
                except Exception as e:
                    st.error(f"save failed: {e}")

with st.expander("➕ Create data schedule"):
    _pid = (_sched[0]["portfolio_id"] if _sched else "")
    with st.form("sched_create"):
        c1, c2 = st.columns(2)
        _profile = c1.text_input("profile", placeholder="my_data_load")
        _kind = c2.selectbox("kind", ["data_load", "fair_value_warmup"])
        c3, c4, c5 = st.columns(3)
        _cron = c3.text_input("cron", placeholder="*/30 13-21 * * 1-5")
        _tz = c4.text_input("timezone", value="America/New_York")
        _en = c5.checkbox("enabled", value=True)
        _cfg = st.text_area("config (JSON)", value="{}")
        _pid_in = st.text_input("portfolio_id", value=str(_pid))
        if st.form_submit_button("create"):
            try:
                go.post("api/v1/schedules", json_data={
                    "profile": _profile, "kind": _kind,
                    "cron_expression": _cron, "timezone": _tz,
                    "enabled": _en, "portfolio_id": _pid_in,
                    "config": json.loads(_cfg) if _cfg.strip() else {}})
                st.toast("created")
                st.rerun()
            except Exception as e:
                st.error(f"create failed: {e}")
