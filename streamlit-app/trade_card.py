"""Shared trade-card renderer — deterministic swing result → compact plan."""
import streamlit as st

_ACTION_COLOR = {
    "BUY": "🟢", "ADD": "🟢", "STRONG_BUY": "🟢",
    "WAIT": "🟡", "HOLD": "⚪",
    "TRIM": "🟠", "EXIT": "🔴", "AVOID": "🔴", "SELL": "🔴",
}


def _pct(v) -> str:
    return f"{v * 100:+.1f}%" if isinstance(v, (int, float)) else "n/a"


def _px(v) -> str:
    return f"${v:,.2f}" if isinstance(v, (int, float)) else "n/a"


def render_trade_card(result: dict, symbol: str):
    """Compact trade-plan card from a swing graph result — deterministic fields only."""
    if result.get("error"):
        st.error(f"Review failed: {result['error']}")
        return
    decision = result.get("decision") or {}
    risk = result.get("risk") or {}
    setup = result.get("setup") or {}
    stock = result.get("stock") or {}
    tech = stock.get("technicals") or {}
    rs = stock.get("relative_strength") or {}
    catalyst = result.get("catalyst") or {}
    fundamentals = result.get("fundamentals") or {}
    valuation = fundamentals.get("valuation") or {}
    env = result.get("event_aware_swing_environment") or result.get("swing_environment") or {}

    action = decision.get("action", "N/A")
    color = _ACTION_COLOR.get(str(action).upper(), "⚪")

    # Row 1: verdict
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Decision", f"{color} {action}")
    c2.metric("Confidence", f"{decision.get('confidence', 0):.0%}")
    c3.metric("Setup", f"{setup.get('type', 'n/a')} · {setup.get('quality', '?')}")
    c4.metric("Regime", f"{env.get('long_permission', 'n/a')}"
              + (f" {env['size_multiplier']:g}×" if env.get("size_multiplier") is not None else "")
              + (f" · stk {setup['stock_permission']}" if setup.get("stock_permission") not in (None, "unknown") else ""))

    patterns = setup.get("detected_patterns") or []
    if patterns:
        st.markdown("**Patterns:** " + " ".join(f"`{p}`" for p in patterns))

    # Practice checklist — the two high-win-rate patterns
    practice_hit = any(p in patterns for p in ("first_pullback", "rsi2_extreme"))
    regime_ok = str(env.get("long_permission", "")).lower() in {"allowed", "limited"}
    risk_ok = str(risk.get("status", "")).lower() in {"allowed", "reduced"}
    rr_ok = bool(risk.get("reward_risk") and risk["reward_risk"] >= 2)
    no_vetoes = not (decision.get("vetoes") or [])
    checks = [
        ("practice pattern", practice_hit), ("regime ok", regime_ok),
        ("risk ok", risk_ok), ("R:R ≥ 2", rr_ok), ("no vetoes", no_vetoes),
    ]
    verdict = all(ok for _, ok in checks)
    chips = " ".join(f"{'🟩' if ok else '🟥'} {name}" for name, ok in checks)
    st.markdown(
        f"**Practice check → {'✅ TAKE' if verdict else '⛔ SKIP'}** · {chips}")

    # Held-position verdict — the review sees your portfolio_positions qty
    # and rules on the holding itself (EXIT/TRIM/TAKE_PROFIT/HOLD).
    pm = result.get("position_management") or {}
    if pm.get("current_position"):
        _pm_icon = {"EXIT": "🔴", "TRIM": "🟠", "TAKE_PROFIT": "💰",
                    "HOLD": "🟢", "REVIEW": "⚪"}.get(
            str(pm.get("position_action", "")).upper(), "⚪")
        _pm_reason = (pm.get("reasons") or ["—"])[0]
        _pm_qty = pm.get("reduce_quantity")
        st.markdown(
            f"**Held position → {_pm_icon} {pm.get('position_action')}** · "
            f"{pm.get('current_position'):g} shares held"
            + (f" · sell ~{_pm_qty:g}" if _pm_qty else "")
            + f" · {_pm_reason}")

    # Row 2: the trade plan — entry / stop / target / R:R / size
    entry, stop, target = risk.get("entry"), risk.get("stop"), risk.get("target")
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Entry", _px(entry))
    c2.metric("Stop", _px(stop), delta=f"{(stop - entry) / entry * 100:.1f}%" if entry and stop else None)
    c3.metric("Target", _px(target), delta=f"{(target - entry) / entry * 100:+.1f}%" if entry and target else None)
    c4.metric("R:R", f"{risk['reward_risk']:.1f}" if risk.get("reward_risk") else "n/a")
    c5.metric("Shares", f"{risk['shares']:,}" if risk.get("shares") else "n/a")
    c6.metric("Size", _pct(decision.get("position_size_pct") or risk.get("position_size_pct")))
    if risk.get("blocking_reasons"):
        st.warning("Risk gate: " + " · ".join(risk["blocking_reasons"]))
    if setup.get("type") == "mean_reversion":
        st.info("Mean-reversion exit: sell on the first close above the prior day's high, "
                "or after 5 bars — harvest the bounce; the 2R target above does not apply.")
    if setup.get("type") == "breakout_retest":
        st.info("Retest entry: stop just under the breakout level — "
                "a close below it means the former resistance failed as support.")

    # Row 3: evidence grid
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**Technicals**")
        sma50, sma200 = tech.get("sma50"), tech.get("sma200")
        price = tech.get("price")
        st.write(f"Price {_px(price)} · RSI {tech.get('rsi', 'n/a'):.0f}" if isinstance(tech.get("rsi"), (int, float)) else f"Price {_px(price)}")
        st.write(f"vs SMA50 {_pct((price - sma50) / sma50) if price and sma50 else 'n/a'}"
                 f" · vs SMA200 {_pct((price - sma200) / sma200) if price and sma200 else 'n/a'}")
        st.write(f"ATR {_pct(tech.get('atr_pct'))} · vol {tech.get('volume_ratio', 'n/a')}×"
                 if tech.get("volume_ratio") is not None else f"ATR {_pct(tech.get('atr_pct'))}")
        st.write(f"RS vs SPY 20d {_pct(rs.get('vs_spy20'))} · {rs.get('tier', '')}")
    with c2:
        st.markdown("**Fundamentals**")
        st.write(f"Quality {decision.get('fundamental_quality') or fundamentals.get('quality', 'n/a')}"
                 f" · Thesis {decision.get('thesis_status', 'n/a')}")
        fv_pct = valuation.get("price_vs_base_fv_pct")
        if fv_pct is not None:
            st.write(f"Fair value {fv_pct:+.1f}% vs price ({decision.get('valuation_label', 'n/a')})")
        for r in (fundamentals.get("reasons") or [])[:2]:
            st.caption(r)
    with c3:
        st.markdown("**Catalyst**")
        st.write(f"{catalyst.get('catalyst_type', 'NONE')} · {catalyst.get('direction', 'n/a')}"
                 f" · reaction {catalyst.get('reaction_state', 'n/a')}")
        for n in (catalyst.get("recent_news") or [])[:3]:
            st.caption(f"· {n.get('title', '')[:80]}")

    # Row 4: why / why not
    reasons = decision.get("reasons") or []
    vetoes = decision.get("vetoes") or []
    if vetoes:
        st.error("Vetoes: " + " · ".join(vetoes))
    for r in reasons[:6]:
        st.write(f"- {r}")


def render_universe_expander(client):
    """The scanned universe (portfolio ∪ watchlist) — same list used by
    the screener and the alert scans."""
    try:
        uni = client.get("api/v1/screener/universe") or {}
    except Exception:
        return
    items = uni.get("items") or []
    if not items:
        return
    held = [i["symbol"] for i in items if i.get("in_portfolio")]
    watch = [i["symbol"] for i in items
             if i.get("in_watchlist") and not i.get("in_portfolio")]
    with st.expander(f"📋 Screened universe — {len(items)} symbols (portfolio ∪ watchlist)"):
        if held:
            st.markdown(f"**Portfolio ({len(held)}):** "
                        + " ".join(f"`{s}`" for s in held))
        if watch:
            st.markdown(f"**Watchlist-only ({len(watch)}):** "
                        + " ".join(f"`{s}`" for s in watch))
