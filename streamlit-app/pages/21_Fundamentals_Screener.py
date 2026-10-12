from typing import Any, Dict, List

import pandas as pd
import streamlit as st

from api_client import get_go_api_client


go_client = get_go_api_client()


st.set_page_config(page_title="Fundamentals Screener", layout="wide")

st.title("Fundamentals Screener")
st.caption("Institution-style fundamentals screen across all symbols in your DB")

st.markdown("---")

screener_label = st.selectbox(
    "Screener",
    options=["Quality Compounders", "Value", "Growth", "GARP", "Inflection"],
    index=0,
)

factor_engine_config_label_to_id = {}
factor_engine_configs = []
try:
    cfg_resp = go_client.get("api/v1/admin/factor-engine/screener-configs")
    factor_engine_configs = (cfg_resp or {}).get("configs") or []
    factor_engine_configs = factor_engine_configs if isinstance(factor_engine_configs, list) else []
    for c in factor_engine_configs:
        cid = str((c or {}).get("id") or "")
        clabel = str((c or {}).get("label") or cid)
        if cid:
            factor_engine_config_label_to_id[clabel] = cid
except Exception:
    factor_engine_configs = []

if factor_engine_configs:
    st.markdown("### Factor Engine Screener Presets")
    preset_label = st.selectbox(
        "Preset (weights)",
        options=list(factor_engine_config_label_to_id.keys()),
        index=0,
    )
    preset_id = factor_engine_config_label_to_id.get(preset_label)
    preset = next((c for c in factor_engine_configs if (c or {}).get("id") == preset_id), None) or {}
    weights = (preset or {}).get("weights") or {}
    try:
        wdf = pd.DataFrame(
            [
                {
                    "Preset": preset_label,
                    "Investment": float(weights.get("investment", 0) or 0),
                    "Entry": float(weights.get("entry", 0) or 0),
                    "Catalyst": float(weights.get("catalyst", 0) or 0),
                }
            ]
        )
        st.dataframe(wdf, width="stretch", hide_index=True)
    except Exception:
        pass

else:
    preset_id = None

desc_by_label = {
    "Quality Compounders": {
        "short": "Durable, high-quality compounders with strong margins and balance sheets.",
        "long": "What it finds:\n- Durable, high-quality businesses with consistent growth and strong profitability.\n- Typically established leaders with solid balance sheets.\n\nWho it’s for:\n- Long-term investors who want fewer blow-ups and smoother compounding.\n- Core portfolio / long-horizon allocations.\n\nTypical risk:\n- Valuation risk (great companies can be overpriced).\n- Can lag in risk-on rallies vs early-stage growth.\n\nTypical reward:\n- Higher probability of steady multi-year compounding.\n- Lower downside than speculative names during drawdowns.",
    },
    "Value": {
        "short": "Cheaper valuation names (yields/multiples) with potential mean reversion.",
        "long": "What it finds:\n- Stocks priced cheap vs earnings/cash flow (lower multiples, higher yields).\n- Often mature businesses, cyclicals, or temporarily out-of-favor companies.\n\nWho it’s for:\n- Investors comfortable buying unpopular/ignored names.\n- Those who want margin of safety and mean-reversion potential.\n\nTypical risk:\n- Value traps (cheap for a reason).\n- Cyclical exposure; earnings can drop in recessions.\n\nTypical reward:\n- Re-rating upside when sentiment improves.\n- Strong returns when fundamentals stabilize and multiples expand.",
    },
    "Growth": {
        "short": "Higher growth companies (revenue/earnings) with acceptable quality checks.",
        "long": "What it finds:\n- Higher growth businesses (revenue/earnings growth), sometimes with decent margins.\n- Often secular tailwinds, expanding TAM, category winners.\n\nWho it’s for:\n- Investors seeking higher upside and comfortable with volatility.\n- People who can hold through drawdowns.\n\nTypical risk:\n- Multiple compression when rates rise or growth slows.\n- Execution risk; growth can decelerate unexpectedly.\n\nTypical reward:\n- Bigger upside if growth persists and margins expand.\n- Multi-bagger potential in strong macro/liquidity regimes.",
    },
    "GARP": {
        "short": "Balanced growth-at-a-reasonable-price (growth + quality + valuation discipline).",
        "long": "What it finds:\n- A blend: solid growth + acceptable valuation + profitability/quality checks.\n- Tends to avoid the most expensive story stocks.\n\nWho it’s for:\n- Investors who want growth exposure without paying any price.\n- Good for an all-weather growth allocation.\n\nTypical risk:\n- Can underperform pure growth in mania phases.\n- Still exposed to growth slowdowns (usually less fragile).\n\nTypical reward:\n- Better risk-adjusted returns than pure growth in many cycles.\n- Captures growth upside with fewer valuation blow-ups.",
    },
    "Inflection": {
        "short": "Early signs of accelerating growth and improving margins (higher upside, higher noise).",
        "long": "What it finds:\n- Early leading indicators of improvement (growth acceleration, margin inflection, reinvestment/R&D signals).\n- Often earlier-cycle names before the crowd.\n\nWho it’s for:\n- Investors who want earlier entries and accept uncertainty.\n- A satellite sleeve around a core portfolio.\n\nTypical risk:\n- False positives; inflection may not persist.\n- Higher volatility and drawdowns; earnings and narrative risk.\n\nTypical reward:\n- Large upside if the inflection becomes sustained growth.\n- Earlier entry points than traditional growth screens.",
    },
}

selected_desc = desc_by_label.get(screener_label) or {}
st.caption(selected_desc.get("short") or "")

with st.expander("What this screener is for"):
    st.markdown((selected_desc.get("long") or "").replace("\n", "  \n"))

endpoint_by_label = {
    "Quality Compounders": "api/v1/screeners/fundamentals/quality-compounders",
    "Value": "api/v1/screeners/fundamentals/value",
    "Growth": "api/v1/screeners/fundamentals/growth",
    "GARP": "api/v1/screeners/fundamentals/garp",
    "Inflection": "api/v1/screeners/fundamentals/inflection",
}

col1, col2, col3, col4 = st.columns(4)
with col1:
    limit = st.number_input("Max symbols to scan", min_value=100, max_value=5000, value=5000, step=100)

profile_params: Dict[str, Any] = {}

if screener_label == "Quality Compounders":
    with col2:
        min_market_cap = st.number_input(
            "Min market cap",
            min_value=0.0,
            value=5_000_000_000.0,
            step=1_000_000_000.0,
            format="%.0f",
        )
    with col3:
        min_rev_growth = st.number_input("Min revenue growth YoY (%)", min_value=-100.0, max_value=200.0, value=8.0, step=1.0)
    with col4:
        min_op_margin = st.number_input("Min operating margin (%)", min_value=-50.0, max_value=100.0, value=15.0, step=1.0)

    max_debt_to_equity = st.number_input("Max debt-to-equity", min_value=0.0, max_value=20.0, value=1.0, step=0.1)
    profile_params = {
        "min_market_cap": float(min_market_cap),
        "min_revenue_growth_yoy_pct": float(min_rev_growth),
        "min_operating_margin_pct": float(min_op_margin),
        "max_debt_to_equity": float(max_debt_to_equity),
    }

elif screener_label == "Value":
    with col2:
        min_market_cap = st.number_input(
            "Min market cap",
            min_value=0.0,
            value=2_000_000_000.0,
            step=1_000_000_000.0,
            format="%.0f",
        )
    with col3:
        max_pe = st.number_input("Max P/E", min_value=0.0, max_value=200.0, value=20.0, step=1.0)
    with col4:
        max_ev_to_ebitda = st.number_input("Max EV/EBITDA", min_value=0.0, max_value=200.0, value=12.0, step=1.0)

    colv1, colv2, colv3 = st.columns(3)
    with colv1:
        min_fcf_yield_pct = st.number_input("Min FCF yield (%)", min_value=0.0, max_value=50.0, value=4.0, step=0.5)
    with colv2:
        min_earnings_yield_pct = st.number_input("Min earnings yield (%)", min_value=0.0, max_value=50.0, value=5.0, step=0.5)
    with colv3:
        max_debt_to_equity = st.number_input("Max debt-to-equity", min_value=0.0, max_value=20.0, value=2.0, step=0.1)

    profile_params = {
        "min_market_cap": float(min_market_cap),
        "max_pe": float(max_pe),
        "max_ev_to_ebitda": float(max_ev_to_ebitda),
        "min_fcf_yield_pct": float(min_fcf_yield_pct),
        "min_earnings_yield_pct": float(min_earnings_yield_pct),
        "max_debt_to_equity": float(max_debt_to_equity),
    }

elif screener_label == "Growth":
    with col2:
        min_market_cap = st.number_input(
            "Min market cap",
            min_value=0.0,
            value=5_000_000_000.0,
            step=1_000_000_000.0,
            format="%.0f",
        )
    with col3:
        min_rev_growth = st.number_input("Min revenue growth YoY (%)", min_value=-100.0, max_value=200.0, value=15.0, step=1.0)
    with col4:
        min_earn_growth = st.number_input("Min earnings growth YoY (%)", min_value=-100.0, max_value=200.0, value=10.0, step=1.0)

    colg1, colg2 = st.columns(2)
    with colg1:
        min_op_margin = st.number_input("Min operating margin (%)", min_value=-50.0, max_value=100.0, value=10.0, step=1.0)
    with colg2:
        max_debt_to_equity = st.number_input("Max debt-to-equity", min_value=0.0, max_value=20.0, value=1.5, step=0.1)

    profile_params = {
        "min_market_cap": float(min_market_cap),
        "min_revenue_growth_yoy_pct": float(min_rev_growth),
        "min_earnings_growth_yoy_pct": float(min_earn_growth),
        "min_operating_margin_pct": float(min_op_margin),
        "max_debt_to_equity": float(max_debt_to_equity),
    }

elif screener_label == "GARP":
    with col2:
        min_market_cap = st.number_input(
            "Min market cap",
            min_value=0.0,
            value=5_000_000_000.0,
            step=1_000_000_000.0,
            format="%.0f",
        )
    with col3:
        min_rev_growth = st.number_input("Min revenue growth YoY (%)", min_value=-100.0, max_value=200.0, value=10.0, step=1.0)
    with col4:
        min_op_margin = st.number_input("Min operating margin (%)", min_value=-50.0, max_value=100.0, value=10.0, step=1.0)

    colp1, colp2, colp3, colp4 = st.columns(4)
    with colp1:
        min_rule_of_40 = st.number_input("Min Rule of 40", min_value=-100.0, max_value=200.0, value=40.0, step=1.0)
    with colp2:
        max_pe = st.number_input("Max P/E", min_value=0.0, max_value=200.0, value=35.0, step=1.0)
    with colp3:
        max_peg = st.number_input("Max PEG", min_value=0.0, max_value=20.0, value=2.5, step=0.1)
    with colp4:
        max_debt_to_equity = st.number_input("Max debt-to-equity", min_value=0.0, max_value=20.0, value=1.5, step=0.1)

    profile_params = {
        "min_market_cap": float(min_market_cap),
        "min_revenue_growth_yoy_pct": float(min_rev_growth),
        "min_operating_margin_pct": float(min_op_margin),
        "min_rule_of_40": float(min_rule_of_40),
        "max_pe": float(max_pe),
        "max_peg": float(max_peg),
        "max_debt_to_equity": float(max_debt_to_equity),
    }

else:  # Inflection
    with col2:
        min_market_cap = st.number_input(
            "Min market cap",
            min_value=0.0,
            value=2_000_000_000.0,
            step=1_000_000_000.0,
            format="%.0f",
        )
    with col3:
        min_score = st.number_input("Min inflection score", min_value=0.0, max_value=100.0, value=60.0, step=1.0)
    with col4:
        min_periods = st.number_input("Min statement periods", min_value=1, max_value=10, value=3, step=1)

    max_debt_to_equity = st.number_input("Max debt-to-equity", min_value=0.0, max_value=20.0, value=2.5, step=0.1)

    profile_params = {
        "min_market_cap": float(min_market_cap),
        "max_debt_to_equity": float(max_debt_to_equity),
        "min_score": float(min_score),
        "min_periods": int(min_periods),
    }

col5, col6 = st.columns(2)
with col5:
    only_pass = st.checkbox(
        "Show only passing symbols",
        value=True,
        help="If enabled, only symbols that pass the screen are returned.",
    )
with col6:
    include_missing = st.checkbox(
        "Include symbols missing fundamentals",
        value=False,
        help="If enabled, includes symbols where required fundamental fields are missing. Useful to find coverage gaps.",
    )

show_factor_engine_risk = st.checkbox(
    "Show Factor Engine risk metrics (v1)",
    value=False,
    help="Adds risk.* columns computed from raw_market_data_daily via Factor Engine (proxied through Go API).",
)

show_factor_engine_technical = st.checkbox(
    "Show Factor Engine technical metrics (v1)",
    value=False,
    help="Adds technical.* columns (RSI/EMA/SMA) via Factor Engine (proxied through Go API).",
)

show_factor_engine_entry_score = st.checkbox(
    "Show Entry Score / AI Accumulation Score (v1)",
    value=False,
    help="Adds entry.score and ai_accumulation.score (0-100) via Factor Engine (proxied through Go API).",
)

show_factor_engine_catalyst_score = st.checkbox(
    "Show Catalyst Score (v1)",
    value=False,
    help="Adds catalyst.score (0-100) via Factor Engine (proxied through Go API).",
)

run = st.button("Run screener", type="primary", width="stretch")

if run:
    with st.spinner("Running fundamentals screener..."):
        params = {
            "limit": int(limit),
            "only_pass": "true" if only_pass else "false",
        }
        if preset_id:
            params["preset_id"] = preset_id
        params.update(profile_params)
        resp = go_client.get(endpoint_by_label[screener_label], params=params)

    api_short = (resp or {}).get("profile_description_short")
    api_long = (resp or {}).get("profile_description_long")
    if api_short or api_long:
        if api_short:
            st.caption(api_short)
        if api_long:
            with st.expander("What this screener is for (from API)"):
                st.markdown(str(api_long).replace("\n", "  \n"))

    results = (resp or {}).get("results") or []
    results = results if isinstance(results, list) else []

    st.success(f"Found {len(results)} matching symbols")

    if results:
        df = pd.DataFrame(results)

        df = df.copy()

        text_cols = ["symbol", "sector", "industry", "fundamentals_as_of", "screen_profile"]
        for c in text_cols:
            if c in df.columns:
                df[c] = df[c].where(df[c].isna(), df[c].astype(str))

        numeric_cols = [
            "market_cap",
            "revenue_growth_yoy_pct",
            "earnings_growth_yoy_pct",
            "operating_margin_pct",
            "debt_to_equity",
            "pe_ratio",
            "peg_ratio",
            "ev_to_ebitda",
            "earnings_yield_pct",
            "fcf_yield_pct",
            "rule_of_40",
            "periods_used",
            "revenue_growth_from_statements_pct",
            "revenue_growth_accel_pct",
            "gross_margin_latest_pct",
            "operating_margin_latest_pct",
            "gross_margin_delta_pct",
            "operating_margin_delta_pct",
            "rnd_pct",
            "sga_pct",
            "inflection_score",
            "missing_required_fields",
            "screen_max_debt_to_equity",
            "screen_max_pe",
            "screen_max_ev_to_ebitda",
            "screen_max_peg",
            "screen_min_market_cap",
            "screen_min_fcf_yield_pct",
            "screen_min_earnings_yield_pct",
            "screen_min_earn_growth_pct",
            "screen_min_op_margin_pct",
            "screen_min_rule_of_40",
            "screen_min_rev_growth_pct",
            "screen_min_periods",
            "screen_min_score",
        ]
        for c in numeric_cols:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")

        if show_factor_engine_risk and "symbol" in df.columns:
            try:
                symbols = [s for s in df["symbol"].dropna().astype(str).tolist() if s]
                symbols = [s.strip().upper() for s in symbols]

                risk_resp = go_client.post(
                    "api/v1/admin/factor-engine/risk",
                    json_data={"symbols": symbols},
                    timeout=60,
                )
                risk_by_symbol = (risk_resp or {}).get("results") or {}

                df["factor_engine_risk_as_of"] = df["symbol"].astype(str).str.upper().map(
                    lambda s: (risk_by_symbol.get(s) or {}).get("as_of_date")
                    if (risk_by_symbol.get(s) or {}).get("ok")
                    else None
                )
                df["factor_engine_risk_source"] = df["symbol"].astype(str).str.upper().map(
                    lambda s: (risk_by_symbol.get(s) or {}).get("source")
                    if (risk_by_symbol.get(s) or {}).get("ok")
                    else None
                )

                def _get_factor(symbol: str, fid: str):
                    entry = risk_by_symbol.get(symbol) or {}
                    if not entry.get("ok"):
                        return None
                    factors = entry.get("factors") or {}
                    rec = factors.get(fid) or {}
                    return rec.get("value")

                df["risk_volatility_30d"] = df["symbol"].astype(str).str.upper().map(
                    lambda s: _get_factor(s, "risk.volatility_30d")
                )
                df["risk_max_drawdown_1y"] = df["symbol"].astype(str).str.upper().map(
                    lambda s: _get_factor(s, "risk.max_drawdown_1y")
                )
                df["risk_var_95"] = df["symbol"].astype(str).str.upper().map(
                    lambda s: _get_factor(s, "risk.var_95")
                )
                df["risk_sharpe_ratio"] = df["symbol"].astype(str).str.upper().map(
                    lambda s: _get_factor(s, "risk.sharpe_ratio")
                )

                numeric_cols.extend(
                    [
                        "risk_volatility_30d",
                        "risk_max_drawdown_1y",
                        "risk_var_95",
                        "risk_sharpe_ratio",
                    ]
                )
                for c in [
                    "risk_volatility_30d",
                    "risk_max_drawdown_1y",
                    "risk_var_95",
                    "risk_sharpe_ratio",
                ]:
                    if c in df.columns:
                        df[c] = pd.to_numeric(df[c], errors="coerce")
            except Exception as e:
                st.warning(f"Factor Engine risk enrichment failed: {e}")

        if show_factor_engine_technical and "symbol" in df.columns:
            try:
                symbols = [s for s in df["symbol"].dropna().astype(str).tolist() if s]
                symbols = [s.strip().upper() for s in symbols]

                tech_resp = go_client.post(
                    "api/v1/admin/factor-engine/technical",
                    json_data={"symbols": symbols},
                    timeout=60,
                )
                tech_by_symbol = (tech_resp or {}).get("results") or {}

                df["factor_engine_technical_as_of"] = df["symbol"].astype(str).str.upper().map(
                    lambda s: (tech_by_symbol.get(s) or {}).get("as_of_date")
                    if (tech_by_symbol.get(s) or {}).get("ok")
                    else None
                )
                df["factor_engine_technical_source"] = df["symbol"].astype(str).str.upper().map(
                    lambda s: (tech_by_symbol.get(s) or {}).get("source")
                    if (tech_by_symbol.get(s) or {}).get("ok")
                    else None
                )

                def _get_t(symbol: str, fid: str):
                    entry = tech_by_symbol.get(symbol) or {}
                    if not entry.get("ok"):
                        return None
                    factors = entry.get("factors") or {}
                    rec = factors.get(fid) or {}
                    return rec.get("value")

                df["technical_rsi_14"] = df["symbol"].astype(str).str.upper().map(
                    lambda s: _get_t(s, "technical.rsi_14")
                )
                df["technical_ema_20"] = df["symbol"].astype(str).str.upper().map(
                    lambda s: _get_t(s, "technical.ema_20")
                )
                df["technical_sma_50"] = df["symbol"].astype(str).str.upper().map(
                    lambda s: _get_t(s, "technical.sma_50")
                )
                df["technical_sma_200"] = df["symbol"].astype(str).str.upper().map(
                    lambda s: _get_t(s, "technical.sma_200")
                )

                numeric_cols.extend(
                    [
                        "technical_rsi_14",
                        "technical_ema_20",
                        "technical_sma_50",
                        "technical_sma_200",
                    ]
                )
                for c in [
                    "technical_rsi_14",
                    "technical_ema_20",
                    "technical_sma_50",
                    "technical_sma_200",
                ]:
                    if c in df.columns:
                        df[c] = pd.to_numeric(df[c], errors="coerce")
            except Exception as e:
                st.warning(f"Factor Engine technical enrichment failed: {e}")

        if show_factor_engine_entry_score and "symbol" in df.columns:
            try:
                symbols = [s for s in df["symbol"].dropna().astype(str).tolist() if s]
                symbols = [s.strip().upper() for s in symbols]

                es_resp = go_client.post(
                    "api/v1/admin/factor-engine/entry-score",
                    json_data={"symbols": symbols},
                    timeout=60,
                )
                es_by_symbol = (es_resp or {}).get("results") or {}

                df["factor_engine_entry_as_of"] = df["symbol"].astype(str).str.upper().map(
                    lambda s: (es_by_symbol.get(s) or {}).get("as_of_date")
                    if (es_by_symbol.get(s) or {}).get("ok")
                    else None
                )
                df["factor_engine_entry_source"] = df["symbol"].astype(str).str.upper().map(
                    lambda s: (es_by_symbol.get(s) or {}).get("source")
                    if (es_by_symbol.get(s) or {}).get("ok")
                    else None
                )

                def _get_es(symbol: str, fid: str):
                    entry = es_by_symbol.get(symbol) or {}
                    if not entry.get("ok"):
                        return None
                    factors = entry.get("factors") or {}
                    rec = factors.get(fid) or {}
                    return rec.get("value")

                df["entry_score"] = df["symbol"].astype(str).str.upper().map(
                    lambda s: _get_es(s, "entry.score")
                )
                df["ai_accumulation_score"] = df["symbol"].astype(str).str.upper().map(
                    lambda s: _get_es(s, "ai_accumulation.score")
                )

                numeric_cols.extend(["entry_score", "ai_accumulation_score"])
                for c in ["entry_score", "ai_accumulation_score"]:
                    if c in df.columns:
                        df[c] = pd.to_numeric(df[c], errors="coerce")
            except Exception as e:
                st.warning(f"Factor Engine entry score enrichment failed: {e}")

        if show_factor_engine_catalyst_score and "symbol" in df.columns:
            try:
                symbols = [s for s in df["symbol"].dropna().astype(str).tolist() if s]
                symbols = [s.strip().upper() for s in symbols]

                cs_resp = go_client.post(
                    "api/v1/admin/factor-engine/catalyst-score",
                    json_data={"symbols": symbols},
                    timeout=60,
                )
                cs_by_symbol = (cs_resp or {}).get("results") or {}

                df["factor_engine_catalyst_as_of"] = df["symbol"].astype(str).str.upper().map(
                    lambda s: (cs_by_symbol.get(s) or {}).get("as_of_date")
                    if (cs_by_symbol.get(s) or {}).get("ok")
                    else None
                )
                df["factor_engine_catalyst_source"] = df["symbol"].astype(str).str.upper().map(
                    lambda s: (cs_by_symbol.get(s) or {}).get("source")
                    if (cs_by_symbol.get(s) or {}).get("ok")
                    else None
                )

                def _get_cs(symbol: str, fid: str):
                    cat = cs_by_symbol.get(symbol) or {}
                    if not cat.get("ok"):
                        return None
                    factors = cat.get("factors") or {}
                    rec = factors.get(fid) or {}
                    return rec.get("value")

                df["catalyst_score"] = df["symbol"].astype(str).str.upper().map(
                    lambda s: _get_cs(s, "catalyst.score")
                )

                numeric_cols.extend(["catalyst_score"])
                if "catalyst_score" in df.columns:
                    df["catalyst_score"] = pd.to_numeric(df["catalyst_score"], errors="coerce")
            except Exception as e:
                st.warning(f"Factor Engine catalyst score enrichment failed: {e}")

        if "pass" in df.columns:
            df["pass"] = df["pass"].astype("boolean")

        for c in df.columns:
            if df[c].dtype == object:
                df[c] = df[c].apply(lambda v: str(v) if isinstance(v, (dict, list)) else v)

        if not include_missing and "missing_required_fields" in df.columns:
            df = df[df["missing_required_fields"].fillna(0).astype(int) == 0]

        if screener_label == "Quality Compounders":
            preferred_cols = [
                "symbol",
                "pass",
                "missing_required_fields",
                "sector",
                "industry",
                "market_cap",
                "revenue_growth_yoy_pct",
                "operating_margin_pct",
                "debt_to_equity",
                "pe_ratio",
                "fundamentals_as_of",
            ]
        elif screener_label == "Value":
            preferred_cols = [
                "symbol",
                "pass",
                "missing_required_fields",
                "sector",
                "industry",
                "market_cap",
                "pe_ratio",
                "ev_to_ebitda",
                "earnings_yield_pct",
                "fcf_yield_pct",
                "debt_to_equity",
                "fundamentals_as_of",
            ]
        elif screener_label == "Growth":
            preferred_cols = [
                "symbol",
                "pass",
                "missing_required_fields",
                "sector",
                "industry",
                "market_cap",
                "revenue_growth_yoy_pct",
                "earnings_growth_yoy_pct",
                "operating_margin_pct",
                "debt_to_equity",
                "pe_ratio",
                "fundamentals_as_of",
            ]
        elif screener_label == "GARP":
            preferred_cols = [
                "symbol",
                "pass",
                "missing_required_fields",
                "sector",
                "industry",
                "market_cap",
                "revenue_growth_yoy_pct",
                "operating_margin_pct",
                "rule_of_40",
                "pe_ratio",
                "peg_ratio",
                "debt_to_equity",
                "fundamentals_as_of",
            ]
        else:  # Inflection
            preferred_cols = [
                "symbol",
                "pass",
                "missing_required_fields",
                "sector",
                "industry",
                "market_cap",
                "inflection_score",
                "periods_used",
                "revenue_growth_from_statements_pct",
                "revenue_growth_accel_pct",
                "gross_margin_latest_pct",
                "gross_margin_delta_pct",
                "operating_margin_latest_pct",
                "operating_margin_delta_pct",
                "rnd_pct",
                "sga_pct",
                "debt_to_equity",
                "fundamentals_as_of",
                "reason_codes",
            ]

        if show_factor_engine_risk:
            preferred_cols.extend(
                [
                    "factor_engine_risk_as_of",
                    "factor_engine_risk_source",
                    "risk_volatility_30d",
                    "risk_max_drawdown_1y",
                    "risk_var_95",
                    "risk_sharpe_ratio",
                ]
            )

        if show_factor_engine_technical:
            preferred_cols.extend(
                [
                    "factor_engine_technical_as_of",
                    "factor_engine_technical_source",
                    "technical_rsi_14",
                    "technical_ema_20",
                    "technical_sma_50",
                    "technical_sma_200",
                ]
            )

        if show_factor_engine_entry_score:
            preferred_cols.extend(
                [
                    "factor_engine_entry_as_of",
                    "factor_engine_entry_source",
                    "entry_score",
                    "ai_accumulation_score",
                ]
            )

        if show_factor_engine_catalyst_score:
            preferred_cols.extend(
                [
                    "factor_engine_catalyst_as_of",
                    "factor_engine_catalyst_source",
                    "catalyst_score",
                ]
            )
        cols = [c for c in preferred_cols if c in df.columns] + [c for c in df.columns if c not in preferred_cols]
        df = df[cols]
        st.dataframe(df, width="stretch", hide_index=True)

        st.markdown("### Result list")
        symbols = [str(r.get("symbol") or "").strip().upper() for r in results]
        symbols = [s for s in symbols if s]
        st.text_area("Symbols (copy/paste)", value="\n".join(symbols), height=200)
    else:
        st.info("No symbols matched. Try loosening thresholds.")
else:
    st.caption("Set thresholds and click 'Run screener'.")
