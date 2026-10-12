"""Go-API-only Agent Workbench with structured result rendering."""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import pandas as pd
import streamlit as st

from api_client import APIError, get_go_api_client
from utils import render_sidebar, setup_page_config

setup_page_config("Agent Workbench", "🤖")
render_sidebar()

st.title("🤖 Agent Workbench")
st.caption("Select an agent, provide required inputs, and review structured evidence through the Go API.")

client = get_go_api_client()


def _status_color(value: str) -> str:
    value = str(value).upper()
    if value in {"BUY", "BUY_SMALL", "ADD", "HIGH", "GOOD", "ALLOWED", "RISK_ON", "INTACT"}:
        return "#198754"
    if value in {"HOLD", "MEDIUM", "REVIEW", "PARTIAL", "INCONCLUSIVE", "UNKNOWN", "NORMAL"}:
        return "#b58105"
    return "#c0392b"


def _badge(label: str, value: Any) -> None:
    text = str(value if value is not None else "n/a")
    st.markdown(
        f"<div style='display:flex;justify-content:space-between;padding:.55rem .7rem;"
        f"margin:.2rem 0;border-radius:.4rem;background:#f5f7fa'>"
        f"<strong>{label}</strong><span style='color:{_status_color(text)};font-weight:700'>{text}</span></div>",
        unsafe_allow_html=True,
    )


def _render_explanation(result: dict) -> None:
    explanation = result.get("explanation") if isinstance(result, dict) else None
    if not explanation:
        return
    st.subheader("Trading Explanation")
    _badge("Source", explanation.get("source", "deterministic_fallback"))
    st.markdown(f"### {explanation.get('headline', 'Analysis summary')}")
    st.write(explanation.get("action_summary", ""))
    columns = st.columns(3)
    with columns[0]:
        st.markdown("**Why**")
        for item in explanation.get("why", []):
            st.write(f"- {item}")
    with columns[1]:
        st.markdown("**Risks**")
        for item in explanation.get("risks", []):
            st.write(f"- {item}")
    with columns[2]:
        st.markdown("**Next confirmation**")
        for item in explanation.get("next_confirmation", []):
            st.write(f"- {item}")
    if explanation.get("data_gaps"):
        st.warning("Data gaps: " + "; ".join(explanation["data_gaps"]))


def _render_portfolio_review(result: dict) -> None:
    _render_explanation(result)
    actions = result.get("actions", [])
    counts = Counter(item.get("action", "REVIEW") for item in actions)
    st.subheader("Portfolio Review Summary")
    cols = st.columns(4)
    for col, action in zip(cols, ["ADD", "TRIM", "HOLD", "REVIEW"]):
        col.metric(action, counts.get(action, 0))
    c1, c2, c3 = st.columns(3)
    c1.metric("Positions analyzed", result.get("position_count", len(actions)))
    c2.metric("Manual only", str(result.get("manual_only", True)))
    c3.metric("Orders created", str(not result.get("no_orders_created", True)))

    rows = []
    for item in actions:
        rows.append({
            "Symbol": item.get("symbol"),
            "Action": item.get("action"),
            "Quantity": item.get("quantity"),
            "Price": item.get("current_price"),
            "Setup": item.get("setup_type"),
            "Opportunity": item.get("opportunity_quality"),
            "Fundamentals": item.get("fundamental_quality"),
            "Event": item.get("event_policy"),
            "Risk": item.get("risk_status"),
            "Thesis": item.get("thesis_status"),
            "Position": item.get("position_state"),
            "Entry": item.get("entry_state"),
            "Reduce Qty": item.get("reduce_quantity"),
            "Confidence": item.get("confidence"),
        })
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.subheader("Position Evidence")
        for item in actions:
            with st.expander(f"{item.get('symbol')} · {item.get('action', 'REVIEW')}"):
                st.markdown("**Reasons**")
                for reason in item.get("reasons", []):
                    st.write(f"- {reason}")
                st.json(item)


def _entry_permission(opportunity: dict, risk: dict) -> str:
    if not opportunity.get("event_new_entries_allowed", True):
        return "BLOCKED_BY_EVENT"
    if not risk.get("allowed", False):
        return "BLOCKED_BY_RISK"
    market_permission = opportunity.get("market_entry_permission", "UNKNOWN")
    if market_permission == "BLOCKED":
        return "BLOCKED_BY_MARKET"
    if market_permission == "SELECTIVE":
        return "SELECTIVE"
    if market_permission == "NORMAL":
        return "NORMAL"
    return "UNKNOWN"


def _render_swing_review(result: dict) -> None:
    _render_explanation(result)
    opportunity = result.get("opportunity", result)
    stock = opportunity.get("stock", {})
    technicals = stock.get("technicals", {})
    setup = opportunity.get("setup", {})
    risk = result.get("risk", {})
    decision = result.get("decision", {})

    st.subheader(f"Stock Review · {opportunity.get('symbol', 'Unknown')}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Price", f"${technicals.get('price'):.2f}" if technicals.get("price") is not None else "n/a")
    c2.metric("Action", decision.get("action", "REVIEW"))
    c3.metric("Setup", str(setup.get("type", "n/a")).upper())
    c4.metric("Confidence", f"{decision.get('confidence', 0):.0%}")
    _badge("Business quality", opportunity.get("business_quality"))
    _badge("Thesis", opportunity.get("thesis_status"))
    _badge("Setup readiness", opportunity.get("setup_readiness"))
    _badge("Entry permission", _entry_permission(opportunity, risk))
    _badge("Final entry action", decision.get("entry_action", decision.get("action", "REVIEW")))
    position_management = opportunity.get("position_management", {})
    _badge("Position action", position_management.get("position_action"))
    _badge("Position state", position_management.get("position_state"))
    _badge("Position reason", position_management.get("reason_code"))
    _badge("Analysis source", opportunity.get("provenance", {}).get("source", "deterministic"))
    _badge("Price provider", stock.get("data_quality", {}).get("provider", "unknown"))

    left, right = st.columns(2)
    with left:
        st.markdown("### Market & Event")
        _badge("Regime", opportunity.get("market_regime"))
        _badge("Condition", opportunity.get("market_condition"))
        _badge("Swing environment", opportunity.get("swing_environment"))
        event_allowed = opportunity.get("event_new_entries_allowed")
        event_permission = "PERMITTED" if event_allowed else "BLOCKED_BY_EVENT"
        _badge("Event entry policy", event_permission)
        _badge("Market entry permission", opportunity.get("market_entry_permission"))
        _badge("Transition stage", opportunity.get("transition_stage"))
        _badge("Dip-buying", opportunity.get("dip_buying_environment"))
        _badge("Transition score", opportunity.get("bullish_transition_score"))
    with right:
        st.markdown("### Setup & Risk")
        _badge("Opportunity", opportunity.get("opportunity_quality"))
        _badge("Setup quality", setup.get("quality"))
        _badge("Risk status", risk.get("status"))
        _badge("Risk allowed", risk.get("allowed"))
        _badge("Falling knife", setup.get("falling_knife"))
        plan = opportunity.get("accumulation_plan", {})
        _badge("Accumulation phase", plan.get("phase"))
        _badge("Accumulation eligible", plan.get("eligible"))
        _badge("Target weight", plan.get("target_weight"))
        _badge("Next confirmation", ", ".join(plan.get("next_confirmation", [])) or "none")

    st.markdown("### Technicals")
    st.dataframe(pd.DataFrame([technicals]), use_container_width=True, hide_index=True)
    st.markdown("### Fundamentals")
    fundamentals = opportunity.get("fundamentals", {})
    _badge("Business type", fundamentals.get("business_type"))
    _badge("Quality score", fundamentals.get("quality_score"))
    _badge("Valuation", fundamentals.get("valuation", {}).get("valuation_label"))
    _badge("Data quality", fundamentals.get("data_quality"))
    _badge("Fundamentals provider", fundamentals.get("provenance", {}).get("source", "unknown"))
    catalyst = opportunity.get("catalyst", {})
    st.markdown("### Catalyst / Earnings / News")
    catalyst_direction = catalyst.get("catalyst_direction", catalyst.get("direction"))
    _badge("Overall catalyst direction", catalyst_direction)
    _badge("Headline aggregate direction", catalyst.get("news_direction", catalyst.get("direction")))
    _badge("Catalyst type / risk", catalyst.get("catalyst_type"))
    _badge("Materiality", catalyst.get("materiality"))
    _badge("Reaction", catalyst.get("reaction_state"))
    _badge("Catalyst severity", catalyst.get("severity"))
    _badge("Days to earnings", catalyst.get("days_to_earnings"))
    _badge("New-entry policy", catalyst.get("new_entry_policy"))
    _badge("News source", ", ".join(catalyst.get("providers", [])) or "unknown")
    for headline in catalyst.get("recent_news", [])[:5]:
        headline = headline if isinstance(headline, dict) else {"title": str(headline)}
        title = headline.get("title", "")
        headline_direction = headline.get("headline_direction", "NEUTRAL")
        if headline_direction == "POSITIVE":
            st.success(f"Positive headline: {title}")
        elif headline_direction == "NEGATIVE":
            st.error(f"Negative headline: {title}")
        elif headline_direction == "MIXED":
            st.warning(f"Mixed headline: {title}")
        else:
            st.info(f"Neutral/uncertain headline: {title}")

    if decision.get("reasons"): 
        st.markdown("### Decision Reasons")
        for reason in decision["reasons"]:
            st.write(f"- {reason}")
    with st.expander("Deterministic evidence"):
        st.json(result)


def _render_fundamentals(result: dict) -> None:
    _render_explanation(result)
    assessment = result.get("assessment", result)
    st.subheader(f"Fundamental Intelligence · {assessment.get('symbol', 'Unknown')}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Business type", assessment.get("business_type", "UNKNOWN"))
    c2.metric("Quality score", assessment.get("quality_score", "n/a"))
    c3.metric("Coverage", f"{assessment.get('quality_coverage', 0):.0%}")
    c4.metric("Data quality", assessment.get("data_quality", "unknown"))
    st.markdown("### Field Coverage")
    coverage = assessment.get("field_coverage", {})
    st.dataframe(pd.DataFrame([coverage]), use_container_width=True, hide_index=True)
    if assessment.get("missing_fields"):
        st.warning("Missing: " + ", ".join(assessment["missing_fields"]))
    estimates = assessment.get("forward_estimates", [])
    if estimates:
        st.markdown("### Forward Estimates")
        st.dataframe(pd.DataFrame(estimates), use_container_width=True, hide_index=True)
    momentum = assessment.get("momentum", {})
    st.markdown("### Fundamental Momentum")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Momentum", momentum.get("label", "UNAVAILABLE"))
    m2.metric("Score", momentum.get("score", "n/a"))
    m3.metric("EPS revision 14d", f"{momentum.get('eps_revision_14d'):.1%}" if momentum.get("eps_revision_14d") is not None else "n/a")
    m4.metric("Net analyst breadth", f"{momentum.get('net_revision_breadth'):.1%}" if momentum.get("net_revision_breadth") is not None else "n/a")
    dimensions = []
    for name in ["growth", "profitability", "cash_flow_quality", "balance_sheet", "capital_efficiency", "competitive_advantage", "earnings_revision", "risk"]:
        item = assessment.get(name, {})
        dimensions.append({"Dimension": name, "Label": item.get("label"), "Score": item.get("score"), "Coverage": item.get("coverage")})
    st.dataframe(pd.DataFrame(dimensions), use_container_width=True, hide_index=True)
    valuation = assessment.get("valuation", {})
    st.markdown("### Valuation Diagnostics")
    st.dataframe(pd.DataFrame([valuation]), use_container_width=True, hide_index=True)
    with st.expander("Full fundamental evidence"):
        st.json(result)


def _render_market(result: dict) -> None:
    _render_explanation(result)
    regime = result.get("regime", {})
    st.subheader("Market Regime")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Direction", regime.get("direction", "unknown").upper())
    c2.metric("Condition", regime.get("condition", "unknown").upper())
    c3.metric("Risk", regime.get("risk_level", "unknown").upper())
    c4.metric("Confidence", f"{regime.get('confidence', 0):.0%}")
    c5.metric("Analysis source", regime.get("source", "unknown").upper())
    st.markdown("### Bullish Transition / Dip-Buying")
    t1, t2, t3, t4 = st.columns(4)
    t1.metric("Transition score", f"{regime.get('bullish_transition_score', 0):.0f}/100" if regime.get("bullish_transition_score") is not None else "n/a")
    t2.metric("Stage", regime.get("transition_stage", "UNKNOWN"))
    t3.metric("Dip-buying", regime.get("dip_buying_environment", "UNKNOWN"))
    t4.metric("5d change", regime.get("transition_delta_5d", "n/a"))
    snapshot = result.get("snapshot", {})
    _badge("Market data provider", snapshot.get("provider", "unknown"))
    volatility = snapshot.get("volatility", {})
    st.markdown("### Volatility / Fear Context")
    v1, v2, v3, v4 = st.columns(4)
    v1.metric("VIX", volatility.get("vix", "n/a"))
    v2.metric("VXN", volatility.get("vxn", "n/a"))
    v3.metric("VIX 5d", volatility.get("vix_chg_5d", "n/a"))
    v4.metric("VXN/VIX", volatility.get("vxn_vix_ratio", "n/a"))
    st.markdown("### Strategy Environments")
    envs = result.get("event_aware_strategy_environments") or result.get("strategy_environments", {})
    rows = []
    for horizon, env in envs.items():
        rows.append({
            "Horizon": horizon,
            "Quality": env.get("quality"),
            "Score": env.get("score"),
            "Entries": env.get("new_entries_allowed", env.get("long_permission")),
            "Breakouts": env.get("breakout_permission"),
            "Size": env.get("size_multiplier"),
            "Event Policy": env.get("event_policy", "NORMAL"),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    outlook = result.get("next_session_outlook")
    if outlook:
        st.markdown("### Next Session Outlook")
        st.caption(outlook.get("disclaimer", ""))
        o1, o2, o3 = st.columns(3)
        o1.metric("Bias", outlook.get("bias", "neutral").replace("_", " ").upper())
        o2.metric("Outlook confidence", outlook.get("confidence", "low").upper())
        o3.metric("Sizing guidance", outlook.get("sizing_guidance", "unknown").upper())
        for key, title in (("base_case", "Base case"), ("alternative", "Alternative"), ("tail_risk", "Tail risk")):
            scenario = outlook.get(key)
            if not scenario:
                continue
            with st.expander(f"{title}: {scenario.get('label', 'unknown').replace('_', ' ')}"):
                st.write(scenario.get("narrative", ""))
                if scenario.get("confirmations"):
                    st.markdown("**Would confirm:**")
                    for item in scenario["confirmations"]:
                        st.write(f"- {item}")
                if scenario.get("invalidations"):
                    st.markdown("**Would invalidate:**")
                    for item in scenario["invalidations"]:
                        st.write(f"- {item}")
        if outlook.get("event_risks"):
            st.markdown("**Event risks:**")
            for risk in outlook["event_risks"]:
                st.write(f"- {risk}")
        if outlook.get("drivers"):
            with st.expander("Evidence drivers"):
                for driver in outlook["drivers"]:
                    st.write(f"- {driver}")
        if outlook.get("watch_levels"):
            with st.expander("Watch levels"):
                st.json(outlook["watch_levels"])
    event = result.get("market_event")
    if event:
        st.markdown("### Event Context")
        _badge("Event", event.get("event_name"))
        _badge("Severity", event.get("severity"))
        _badge("Status", event.get("status"))
        _badge("Policy bias", event.get("policy_bias"))
        _badge("Event source", event.get("source", "unknown"))
    with st.expander("Full market evidence"):
        st.json(result)


def _normalize_persisted_run(record: dict) -> tuple[str, dict]:
    metadata = record.get("metadata", {})
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except ValueError:
            metadata = {}
    metadata = metadata if isinstance(metadata, dict) else {}
    agent = metadata.get("agent", "market_regime")
    result = metadata.get("agent_result")
    if not isinstance(result, dict):
        result = {"run_record": record, "error": "No persisted agent result in this run."}
    return agent, {"run_id": record.get("run_id"), "status": record.get("status"), "result": result}


def _recent_run_options(runs: list[dict]) -> dict[str, str]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=2)
    options = {}
    for run in runs or []:
        if not isinstance(run, dict):
            continue
        started = run.get("started_at")
        try:
            timestamp = datetime.fromisoformat(str(started).replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            continue
        if timestamp < cutoff:
            continue
        metadata = run.get("metadata", {})
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except ValueError:
                metadata = {}
        metadata = metadata if isinstance(metadata, dict) else {}
        if metadata.get("workflow") not in {None, "agent_run"}:
            continue
        request = metadata.get("request", {}) if isinstance(metadata.get("request"), dict) else {}
        agent = metadata.get("agent") or request.get("agent") or "unknown"
        scope = request.get("scope") or "unknown"
        symbol = request.get("symbol") or ""
        portfolio = request.get("portfolio_id") or ""
        target = symbol or (f"portfolio:{portfolio}" if portfolio else scope)
        run_id = str(run.get("run_id") or "")
        if not run_id:
            continue
        label = f"{timestamp.astimezone().strftime('%Y-%m-%d %H:%M')} · {agent} · {target} · {run.get('status', 'unknown')} · {run_id[:8]}"
        options[label] = run_id
    return options


def render_result(agent_id: str, result: dict) -> None:
    if agent_id == "portfolio_review" or "actions" in result:
        _render_portfolio_review(result)
    elif agent_id in {"swing_review", "risk_assessment"} or "opportunity" in result:
        _render_swing_review(result)
    elif agent_id == "fundamental_intelligence" or "assessment" in result:
        _render_fundamentals(result)
    elif agent_id in {"market_regime", "event_review"} or "regime" in result:
        _render_market(result)
    else:
        st.subheader("Agent Result")
        st.json(result)


try:
    catalog_response = client.list_agents()
    agents = catalog_response.get("agents", [])
except APIError as exc:
    st.error(f"Unable to load agent catalog from Go API: {exc}")
    st.stop()

available = [agent for agent in agents if agent.get("status") in {"available", "manual_only"}]
if not available:
    st.error("No runnable agents are currently available from the Go API.")
    st.stop()

agent_labels = {f"{agent['name']} ({agent['status']})": agent for agent in available}

st.subheader("1. Select Agent")
selected_label = st.selectbox("Agent", list(agent_labels.keys()), key="workbench_agent")
selected_agent = agent_labels[selected_label]
agent_id = selected_agent["id"]
scopes = selected_agent.get("scopes", ["market"])

st.subheader("2. Provide Required Inputs")
input_columns = st.columns(2)
with input_columns[0]:
    scope = st.selectbox("Scope", scopes, key="workbench_scope")
    horizon_options = ["swing", "investing"]
    if agent_id in {"market_regime", "event_review"}:
        horizon_options = ["swing", "investing", "day_trading"]
    horizon = st.selectbox("Horizon", horizon_options, key="workbench_horizon")
with input_columns[1]:
    mode = st.selectbox("Mode", ["analysis", "paper"], key="workbench_mode")

symbol = ""
portfolio_id = ""
current_position = 0.0
current_weight = None
user_id = "4f8b2cb1-4ed6-4fb5-bd44-48e5acc830a4"
if scope == "stock":
    symbol = st.text_input("Stock symbol", value="RBRK", key="workbench_symbol").strip().upper()
    current_position = st.number_input(
        "Existing position quantity",
        min_value=0.0,
        value=0.0,
        step=1.0,
        help="Use 0 when you do not own this stock. This controls position-management analysis only.",
        key="workbench_current_position",
    )
    current_weight_input = st.number_input(
        "Current portfolio weight % (optional)",
        min_value=0.0,
        max_value=100.0,
        value=0.0,
        step=0.5,
        key="workbench_current_weight",
    )
    current_weight = current_weight_input / 100 if current_weight_input > 0 else None
elif scope == "portfolio":
    st.info("Position quantities will be loaded from the selected portfolio; no manual quantity input is used.")
    user_id = st.text_input("Portfolio owner/user ID", value=user_id, key="workbench_user_id").strip()
    try:
        portfolio_response = client.get(f"api/v1/portfolios/user/{user_id}")
        portfolios = portfolio_response.get("portfolios", [])
    except APIError as exc:
        portfolios = []
        st.warning(f"Unable to load portfolios: {exc}")
    if portfolios:
        portfolio_options = {f"{p.get('name', p.get('id'))} · {p.get('id')}": p.get("id") for p in portfolios}
        selected_portfolio_label = st.selectbox("Portfolio", list(portfolio_options.keys()), key="workbench_portfolio")
        portfolio_id = portfolio_options[selected_portfolio_label]
    else:
        portfolio_id = st.text_input("Portfolio ID", value="501b90e3-68cd-48a6-9cde-db9ebf975018", key="workbench_portfolio_id").strip()
else:
    st.info("This agent runs current market analysis without a symbol or portfolio input.")

if agent_id == "swing_review" and scope == "portfolio":
    st.info("Swing Review will inspect every current position and assign ADD/TRIM/HOLD/REVIEW.")
if selected_agent.get("status") == "unavailable_intraday_contract":
    st.warning("Day trading is unavailable until the intraday data contract is implemented.")
if selected_agent.get("status") == "disabled":
    st.error("Live execution is disabled by architecture policy.")

st.subheader("3. Previous Runs (last 2 days)")
try:
    recent_runs_response = client.list_agent_runs(limit=100)
    recent_runs = recent_runs_response.get("runs", [])
    run_options = _recent_run_options(recent_runs)
except APIError as exc:
    run_options = {}
    st.warning(f"Unable to load previous runs: {exc}")

if run_options:
    selected_run_label = st.selectbox(
        "Select a previous run",
        ["-- choose a run --"] + list(run_options.keys()),
        key="workbench_previous_run",
    )
    if st.button("Load Selected Previous Run", use_container_width=True):
        if selected_run_label != "-- choose a run --":
            with st.spinner("Loading saved run result..."):
                try:
                    record = client.get_agent_run(run_options[selected_run_label])
                    loaded_agent, loaded_response = _normalize_persisted_run(record)
                    st.session_state["workbench_result"] = loaded_response
                    st.session_state["workbench_result_agent"] = loaded_agent
                    st.success(f"Loaded run {run_options[selected_run_label]}")
                except APIError as exc:
                    st.error(f"Unable to load run: {exc}")
else:
    st.caption("No persisted agent runs found in the last two days.")

if scope == "portfolio" and portfolio_id:
    st.subheader("Portfolio Snapshot History")
    try:
        snapshot_response = client.list_portfolio_agent_snapshots(portfolio_id, limit=30)
        snapshots = snapshot_response.get("snapshots", [])
    except APIError as exc:
        snapshots = []
        st.warning(f"Unable to load portfolio snapshots: {exc}")
    if snapshots:
        snapshot_options = {
            f"{str(item.get('as_of', 'unknown')).replace('T', ' ')} · {item.get('reconciliation_status', 'UNKNOWN')} · {item.get('snapshot_id', '')[:8]}": item.get("snapshot_id")
            for item in snapshots
        }
        selected_snapshot_label = st.selectbox("Historical snapshot", list(snapshot_options.keys()), key="workbench_snapshot")
        if st.button("Load Historical Snapshot", use_container_width=True):
            try:
                snapshot = client.get_portfolio_agent_snapshot(portfolio_id, snapshot_options[selected_snapshot_label])
                positions = snapshot.get("positions", [])
                st.session_state["workbench_result"] = {
                    "run_id": snapshot.get("snapshot_id"),
                    "status": "persisted_snapshot",
                    "result": {
                        "actions": positions,
                        "position_count": len(positions),
                        "manual_only": True,
                        "no_orders_created": True,
                        "reasons": ["loaded from persisted portfolio snapshot"],
                        "snapshot": snapshot,
                    },
                }
                st.session_state["workbench_result_agent"] = "portfolio_review"
            except APIError as exc:
                st.error(f"Unable to load historical snapshot: {exc}")
    else:
        st.caption("No persisted portfolio snapshots are available for this portfolio.")

st.subheader("4. Run")
run_column, load_column = st.columns(2)
with run_column:
    run_clicked = st.button("▶ Run Selected Agent", type="primary", use_container_width=True)
with load_column:
    load_run_id = st.text_input("Load previous Run ID", key="workbench_load_run_id").strip()
    load_clicked = st.button("Load Saved Result", use_container_width=True)

if load_clicked:
    if not load_run_id:
        st.error("Enter a Run ID to load.")
        st.stop()
    with st.spinner("Loading persisted run from Go API..."):
        try:
            record = client.get_agent_run(load_run_id)
            loaded_agent, loaded_response = _normalize_persisted_run(record)
            st.session_state["workbench_result"] = loaded_response
            st.session_state["workbench_result_agent"] = loaded_agent
            st.success(f"Loaded run {load_run_id}")
        except APIError as exc:
            st.error(f"Unable to load run: {exc}")
            st.stop()

if run_clicked:
    validation_error = None
    if scope == "stock" and not symbol:
        validation_error = "A stock symbol is required."
    elif scope == "portfolio" and not portfolio_id:
        validation_error = "A portfolio ID is required."
    elif selected_agent.get("status") not in {"available", "manual_only"}:
        validation_error = "This agent is not currently available."
    if validation_error:
        st.error(validation_error)
        st.stop()

    execution_agent = "portfolio_review" if agent_id == "swing_review" and scope == "portfolio" else agent_id
    payload = {
        "agent": execution_agent,
        "scope": scope,
        "horizon": horizon,
        "mode": mode,
        "explain": True,
        "persist": scope == "portfolio" and execution_agent == "portfolio_review",
        "current_position": current_position if scope == "stock" else 0.0,
        "current_weight": current_weight if scope == "stock" else None,
        "reconciliation_safe": True if scope == "stock" else False,
    }
    if symbol:
        payload["symbol"] = symbol
    if portfolio_id:
        payload["portfolio_id"] = portfolio_id

    with st.spinner(f"Running {selected_agent['name']} through Go API..."):
        try:
            response = client.run_agent(payload, timeout=1800)
        except APIError as exc:
            st.error(f"Agent run failed: {exc}")
            st.stop()
    st.session_state["workbench_result"] = response
    st.session_state["workbench_result_agent"] = execution_agent

response = st.session_state.get("workbench_result")
if response:
    display_agent = st.session_state.get("workbench_result_agent", agent_id)
    st.success(f"Run completed: {response.get('run_id', 'unknown')}")
    render_result(display_agent, response.get("result", response))
    st.info("Advisory result only. Review evidence, data freshness, event policy, and risk controls before acting.")
else:
    st.subheader("Ready to run")
    st.markdown("Select an agent above, enter its required input, and click **Run Selected Agent**.")
