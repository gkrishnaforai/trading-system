"""Custodian — the self-healing supervisor's console.

Sensors → diagnosis → tier-gated remediation → verify next pass.
Tier 1/2 issues auto-remediate (retry cap 3, 15-min cooldown);
tier 3 and exhausted retries escalate to a technical alert with
manual intervention steps. Advisory — nothing here restarts
containers or touches data.
"""
import sys
import os

import streamlit as st

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api_client import APIClient
from api_config import api_config
from utils import render_top_nav

client = APIClient(api_config.python_worker_url, timeout=60)

st.set_page_config(page_title="Custodian", page_icon="🛡️", layout="wide")
render_top_nav()
st.title("🛡️ Custodian — self-healing supervisor")
st.caption("detect → diagnose → bounded auto-remediation → verify next "
           "pass → escalate. Auto-retries: 3 attempts · 15-min cooldown. "
           "Escalated = technical alert + manual runbook below.")


@st.cache_data(ttl=60, show_spinner=False)
def _incidents():
    try:
        return client.get("api/v1/board/incidents") or {}
    except Exception:
        return {}


_top = st.columns([1, 4])[0]
if _top.button("▶️ Run pass now", help="Run a custodian supervisor "
               "cycle immediately"):
    try:
        client.post("api/v1/board/refresh/custodian")
        _incidents.clear()
        st.toast("custodian pass kicked")
    except Exception as e:
        st.error(f"kick failed: {e}")

_inc = _incidents()
_open = _inc.get("open") or []
_acts = _inc.get("actions") or []
_res = _inc.get("resolved") or []
_cfg = _inc.get("config") or {}
_cap = _cfg.get("max_attempts", 3)
_cd = _cfg.get("cooldown_min", 15)

_esc = [i for i in _open if i.get("status") == "escalated"]
_mit = [i for i in _open if i.get("status") == "mitigated"]
_new = [i for i in _open if i.get("status") == "open"]

_m1, _m2, _m3, _m4 = st.columns(4)
_m1.metric("escalated", len(_esc))
_m2.metric("auto-mitigating", len(_mit))
_m3.metric("new/open", len(_new))
_m4.metric("recently resolved", len(_res))

# ── technical alerts — manual intervention required ─────────────────────
if _esc:
    st.error(f"🚨 {len(_esc)} escalated issue(s) — auto-remediation "
             f"exhausted ({_cap} attempts) or requires human access. "
             "Technical alerts were raised to universal_events.")
    for i in _esc:
        with st.expander(f"🔴 `{i['signature']}` — {i.get('diagnosis') or 'needs eyes'}",
                         expanded=True):
            _c1, _c2 = st.columns([3, 2])
            _d = i.get("detail") or {}
            _c1.markdown(
                f"**severity** `{i.get('severity')}` · **attempts** "
                f"{i.get('attempts')}/{_cap} · **occurrences** "
                f"{i.get('occurrences')} · first seen "
                f"`{str(i.get('first_seen'))[:16]}` · last "
                f"`{str(i.get('last_seen'))[:16]}`")
            if _d:
                _tail = (_d.get("log_tail") or []) if isinstance(_d, dict) \
                    else []
                if _tail:
                    _c1.caption("📄 related log lines (worker, "
                                "most recent last):")
                    _c1.code("\n".join(_tail[-12:]), language="log")
                _extra = {k: v for k, v in _d.items()
                          if k != "log_tail"} if isinstance(_d, dict) \
                    else {}
                if _extra:
                    with _c1.expander("sensor detail"):
                        st.json(_extra)
            _c2.markdown("**🛠️ Manual intervention:**")
            _c2.markdown(i.get("manual_steps") or
                         "Inspect worker logs, fix root cause, "
                         "resolve here.")
            if i.get("alerted_at"):
                _c2.caption(f"technical alert raised "
                            f"{str(i['alerted_at'])[:19]} UTC")
            if _c2.button("🧠 Analyze root cause", key=f"an_{i['signature']}",
                          help="research agent — pattern-matched triage "
                               "first, bounded LLM analysis when a key "
                               "is configured"):
                with st.spinner("analyzing…"):
                    try:
                        _an = client.post(
                            "api/v1/board/incidents/"
                            f"{i['signature']}/analyze") or {}
                        st.session_state[f"an_{i['signature']}"] = _an
                    except Exception as e:
                        st.error(f"analyze failed: {e}")
            _an = st.session_state.get(f"an_{i['signature']}")
            if _an:
                _src = _an.get("source")
                _tag = {"llm": "🧠 LLM research agent",
                        "rules": "📐 deterministic triage",
                        "none": "—"}.get(_src, _src)
                _c2.markdown(
                    f"**{_tag} · {_an.get('confidence', '?')} conf**")
                _c2.markdown(f"**Root cause:** {_an.get('root_cause')}")
                _ft = _an.get("fix_type")
                _ft_lbl = {"infra": "🧰 infra fix — runbook above",
                           "code": "💻 code fix — needs a ticket",
                           "enhancement": "✨ enhancement — ticket it"}.get(_ft)
                if _ft_lbl:
                    _c2.markdown(f":violet[{_ft_lbl}]")
                _c2.markdown(f"**Proposed fix:** {_an.get('proposed_fix')}")
                if _an.get("patch"):
                    _c2.caption("proposed patch — review before "
                                "applying:")
                    _c2.code(_an["patch"], language="diff")
                _tk = _an.get("ticket") or {}
                if _ft in ("code", "enhancement") and _tk:
                    _cc0 = _an.get("code_context") or {}
                    with _c2.form(key=f"tk_{i['signature']}"):
                        _tt = st.text_input("ticket title",
                                            value=str(_tk.get("title") or "")[:200])
                        _td = st.text_area("description",
                                           value=str(_tk.get("description") or ""),
                                           height=140)
                        if st.form_submit_button("📋 File ticket"):
                            try:
                                client.post("api/v1/board/tickets", json_data={
                                    "signature": i["signature"],
                                    "issue_type": _ft,
                                    "title": _tt, "description": _td,
                                    "root_cause": _an.get("root_cause"),
                                    "proposed_fix": _an.get("proposed_fix"),
                                    "patch": _an.get("patch"),
                                    "evidence": {
                                        "log_tail": _an.get("log_tail") or [],
                                        "handler": _cc0.get("file")},
                                    "source": _an.get("source")})
                                _incidents.clear()
                                st.toast("ticket filed to custodian_tickets")
                            except Exception as e:
                                st.error(f"file failed: {e}")
                _cc = _an.get("code_context") or {}
                if _cc.get("source"):
                    with _c1.expander(
                            f"🧩 handler source — {_cc.get('name')} "
                            f"({os.path.basename(_cc.get('file') or '')})"):
                        st.code(_cc["source"], language="python")
                if _an.get("verify"):
                    _c2.caption(f"verify: {_an['verify']}")
            if st.button("✅ Mark resolved", key=f"res_{i['signature']}"):
                try:
                    client.post("api/v1/board/incidents/"
                                f"{i['signature']}/resolve")
                    _incidents.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"resolve failed: {e}")

# ── in-flight issues — auto-remediation running ──────────────────────────
_act = _mit + _new
if _act:
    st.subheader(f"⚙️ Auto-remediation in flight ({len(_act)})")
    for i in _act:
        _ic = "🟡" if i["status"] == "mitigated" else "⚪"
        st.caption(
            f"{_ic} `{i['signature']}` — {i.get('diagnosis') or '—'} · "
            f"attempts {i.get('attempts')}/{_cap} · next retry ≥{_cd}m "
            f"after last action · remediation: `{i.get('remediation') or '—'}`")
elif not _esc:
    st.success("No open incidents — all sensors clean.")

# ── action ledger ────────────────────────────────────────────────────────
if _acts:
    with st.expander(f"📋 Remediation log — last {len(_acts)} actions",
                     expanded=True):
        for a in _acts:
            st.caption(
                f"`{str(a.get('created_at'))[:19]}` T{a.get('tier')} "
                f"`{a['signature']}` → **{a['action']}** — "
                f"{a.get('result') or '—'}")

# ── ticket backlog — analyst-proposed work, JIRA staging ────────────────
try:
    _tks = (client.get("api/v1/board/tickets") or {}).get("tickets") or []
except Exception:
    _tks = []
if _tks:
    with st.expander(f"📋 Tickets — filed by the analyst "
                     f"({len(_tks)})", expanded=True):
        for t in _tks:
            _it = {"code": "💻", "infra": "🧰",
                   "enhancement": "✨"}.get(t.get("issue_type"), "📋")
            st.caption(
                f"**{t.get('ticket_key') or '—'}** {_it} "
                f"`{t.get('issue_type')}` [{t.get('status')}] — "
                f"{t.get('title')} · `{t.get('signature')}` · "
                f"{str(t.get('created_at'))[:10]}")

# ── recently resolved ────────────────────────────────────────────────────
if _res:
    with st.expander(f"✅ Recently resolved ({len(_res)})"):
        for r in _res:
            st.caption(
                f"`{str(r.get('resolved_at'))[:16]}` `{r['signature']}` — "
                f"{r.get('attempts')}/{_cap} attempts · "
                f"×{r.get('occurrences')} occurrences")
