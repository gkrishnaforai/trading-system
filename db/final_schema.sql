--
-- PostgreSQL database dump
--

\restrict mIYWcbz73bI83no7FaLO2qnbnjq2lgTEi7qjdQdNGCBY6Mh3Aa8FedmZHBD4ue2

-- Dumped from database version 15.15
-- Dumped by pg_dump version 15.15

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: aggregated_indicators; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.aggregated_indicators (
    id bigint NOT NULL,
    stock_symbol text NOT NULL,
    date date NOT NULL,
    ma7 real,
    ma21 real,
    sma50 real,
    ema20 real,
    ema50 real,
    sma200 real,
    atr real,
    macd real,
    macd_signal real,
    macd_histogram real,
    rsi real,
    bb_upper real,
    bb_middle real,
    bb_lower real,
    long_term_trend text,
    medium_term_trend text,
    signal text,
    pullback_zone_lower real,
    pullback_zone_upper real,
    momentum_score real,
    "timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    volume integer,
    volume_ma real,
    ema9 real,
    ema21 real,
    price_below_sma50 boolean DEFAULT false,
    price_below_sma200 boolean DEFAULT false,
    has_good_fundamentals boolean DEFAULT false,
    is_growth_stock boolean DEFAULT false,
    is_exponential_growth boolean DEFAULT false,
    fundamental_score real,
    sma100 real,
    ema12 real,
    ema26 real,
    ema9_above_ema21 boolean DEFAULT false,
    ema20_above_ema50 boolean DEFAULT false,
    ema12_above_ema26 boolean DEFAULT false,
    sma50_above_sma200 boolean DEFAULT false,
    price_above_sma200 boolean DEFAULT false,
    rsi_zone text,
    volume_above_average boolean DEFAULT false,
    volume_spike boolean DEFAULT false,
    macd_above_signal boolean DEFAULT false,
    macd_histogram_positive boolean DEFAULT false,
    higher_highs boolean DEFAULT false,
    higher_lows boolean DEFAULT false,
    updated_at timestamp without time zone,
    data_source text,
    data_frequency text,
    CONSTRAINT aggregated_indicators_data_frequency_check CHECK ((data_frequency = ANY (ARRAY['intraday'::text, 'daily'::text, 'weekly'::text, 'monthly'::text, 'quarterly'::text, 'yearly'::text]))),
    CONSTRAINT aggregated_indicators_long_term_trend_check CHECK ((long_term_trend = ANY (ARRAY['bullish'::text, 'bearish'::text, 'neutral'::text]))),
    CONSTRAINT aggregated_indicators_medium_term_trend_check CHECK ((medium_term_trend = ANY (ARRAY['bullish'::text, 'bearish'::text, 'neutral'::text]))),
    CONSTRAINT aggregated_indicators_rsi_zone_check CHECK ((rsi_zone = ANY (ARRAY['oversold'::text, 'weak'::text, 'healthy'::text, 'overbought'::text]))),
    CONSTRAINT aggregated_indicators_signal_check CHECK ((signal = ANY (ARRAY['buy'::text, 'sell'::text, 'hold'::text])))
);


--
-- Name: aggregated_indicators_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.aggregated_indicators_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: aggregated_indicators_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.aggregated_indicators_id_seq OWNED BY public.aggregated_indicators.id;


--
-- Name: alert_notifications; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alert_notifications (
    notification_id text NOT NULL,
    alert_id text NOT NULL,
    user_id text NOT NULL,
    portfolio_id text,
    stock_symbol text,
    alert_type_id text NOT NULL,
    message text NOT NULL,
    severity text DEFAULT 'info'::text,
    channel text NOT NULL,
    status text DEFAULT 'pending'::text,
    sent_at timestamp without time zone,
    error_message text,
    metadata json,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT alert_notifications_channel_check CHECK ((channel = ANY (ARRAY['email'::text, 'sms'::text, 'push'::text, 'webhook'::text]))),
    CONSTRAINT alert_notifications_severity_check CHECK ((severity = ANY (ARRAY['info'::text, 'warning'::text, 'critical'::text]))),
    CONSTRAINT alert_notifications_status_check CHECK ((status = ANY (ARRAY['pending'::text, 'sent'::text, 'failed'::text])))
);


--
-- Name: alert_types; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alert_types (
    alert_type_id text NOT NULL,
    name text NOT NULL,
    display_name text NOT NULL,
    description text,
    plugin_name text NOT NULL,
    config_schema json,
    enabled boolean DEFAULT true,
    subscription_level_required text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT alert_types_subscription_level_required_check CHECK ((subscription_level_required = ANY (ARRAY['basic'::text, 'pro'::text, 'elite'::text])))
);


--
-- Name: alerts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alerts (
    alert_id text NOT NULL,
    user_id text NOT NULL,
    portfolio_id text,
    stock_symbol text,
    alert_type_id text NOT NULL,
    name text NOT NULL,
    enabled boolean DEFAULT true,
    config json NOT NULL,
    notification_channels text NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT alerts_check CHECK (((portfolio_id IS NOT NULL) OR (stock_symbol IS NOT NULL)))
);


--
-- Name: analyst_consensus; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.analyst_consensus (
    id bigint NOT NULL,
    stock_symbol text NOT NULL,
    consensus_rating text,
    consensus_price_target real,
    strong_buy_count integer DEFAULT 0,
    buy_count integer DEFAULT 0,
    hold_count integer DEFAULT 0,
    sell_count integer DEFAULT 0,
    strong_sell_count integer DEFAULT 0,
    total_ratings integer DEFAULT 0,
    last_updated timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT analyst_consensus_consensus_rating_check CHECK ((consensus_rating = ANY (ARRAY['strong_buy'::text, 'buy'::text, 'hold'::text, 'sell'::text, 'strong_sell'::text])))
);


--
-- Name: analyst_consensus_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.analyst_consensus_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: analyst_consensus_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.analyst_consensus_id_seq OWNED BY public.analyst_consensus.id;


--
-- Name: analyst_ratings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.analyst_ratings (
    id bigint NOT NULL,
    stock_symbol text NOT NULL,
    analyst_name text,
    firm_name text,
    rating text,
    price_target real,
    rating_date date,
    source text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT analyst_ratings_rating_check CHECK ((rating = ANY (ARRAY['strong_buy'::text, 'buy'::text, 'hold'::text, 'sell'::text, 'strong_sell'::text])))
);


--
-- Name: analyst_ratings_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.analyst_ratings_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: analyst_ratings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.analyst_ratings_id_seq OWNED BY public.analyst_ratings.id;


--
-- Name: balance_sheets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.balance_sheets (
    id bigint NOT NULL,
    stock_symbol text NOT NULL,
    period_end date NOT NULL,
    filing_date date,
    fiscal_year integer,
    fiscal_quarter integer,
    timeframe text,
    cash_and_equivalents real,
    short_term_investments real,
    receivables real,
    inventories real,
    other_current_assets real,
    total_current_assets real,
    property_plant_equipment_net real,
    goodwill real,
    intangible_assets_net real,
    other_assets real,
    total_assets real,
    accounts_payable real,
    debt_current real,
    deferred_revenue_current real,
    accrued_and_other_current_liabilities real,
    total_current_liabilities real,
    long_term_debt_and_capital_lease_obligations real,
    other_noncurrent_liabilities real,
    total_liabilities real,
    common_stock real,
    preferred_stock real,
    additional_paid_in_capital real,
    retained_earnings_deficit real,
    accumulated_other_comprehensive_income real,
    treasury_stock real,
    other_equity real,
    noncontrolling_interest real,
    total_equity real,
    total_equity_attributable_to_parent real,
    total_liabilities_and_equity real,
    shares_outstanding real,
    commitments_and_contingencies real,
    cik text,
    tickers text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT balance_sheets_timeframe_check CHECK ((timeframe = ANY (ARRAY['quarterly'::text, 'annual'::text])))
);


--
-- Name: balance_sheets_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.balance_sheets_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: balance_sheets_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.balance_sheets_id_seq OWNED BY public.balance_sheets.id;


--
-- Name: blog_drafts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.blog_drafts (
    draft_id text NOT NULL,
    topic_id text NOT NULL,
    user_id text NOT NULL,
    symbol text NOT NULL,
    title text NOT NULL,
    meta_description text,
    slug text,
    content text NOT NULL,
    tags json,
    status text DEFAULT 'draft'::text,
    generated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    reviewed_at timestamp without time zone,
    reviewed_by text,
    review_notes text,
    context_used json,
    llm_metadata json,
    CONSTRAINT blog_drafts_status_check CHECK ((status = ANY (ARRAY['draft'::text, 'review'::text, 'approved'::text, 'rejected'::text])))
);


--
-- Name: blog_generation_audit; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.blog_generation_audit (
    audit_id text NOT NULL,
    user_id text,
    topic_id text,
    draft_id text,
    generation_request json NOT NULL,
    context_data json NOT NULL,
    system_prompt text,
    user_prompt text,
    prompt_template text,
    agent_type text,
    agent_config json,
    llm_provider text,
    llm_model text,
    llm_parameters json,
    generation_result json,
    generated_content text,
    generation_metadata json,
    status text DEFAULT 'pending'::text NOT NULL,
    stage text DEFAULT 'topic_ranked'::text NOT NULL,
    error_message text,
    error_details json,
    retry_count integer DEFAULT 0,
    max_retries integer DEFAULT 3,
    last_retry_at timestamp without time zone,
    can_retry boolean DEFAULT true,
    retry_with_llm text,
    recovery_data json,
    started_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    completed_at timestamp without time zone,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    correlation_id text,
    parent_audit_id text,
    CONSTRAINT blog_generation_audit_stage_check CHECK ((stage = ANY (ARRAY['topic_ranked'::text, 'context_built'::text, 'agent_invoked'::text, 'content_generated'::text, 'content_validated'::text, 'draft_created'::text, 'published'::text, 'failed'::text]))),
    CONSTRAINT blog_generation_audit_status_check CHECK ((status = ANY (ARRAY['pending'::text, 'in_progress'::text, 'success'::text, 'failed'::text, 'retrying'::text, 'cancelled'::text])))
);


--
-- Name: blog_generation_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.blog_generation_log (
    log_id bigint NOT NULL,
    audit_id text NOT NULL,
    user_id text,
    topic_id text,
    draft_id text,
    action text NOT NULL,
    status text DEFAULT 'success'::text,
    error_message text,
    metadata json,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT blog_generation_log_action_check CHECK ((action = ANY (ARRAY['topic_ranked'::text, 'context_built'::text, 'blog_generated'::text, 'blog_published'::text, 'blog_failed'::text]))),
    CONSTRAINT blog_generation_log_status_check CHECK ((status = ANY (ARRAY['success'::text, 'failed'::text, 'partial'::text])))
);


--
-- Name: blog_generation_log_log_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.blog_generation_log_log_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: blog_generation_log_log_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.blog_generation_log_log_id_seq OWNED BY public.blog_generation_log.log_id;


--
-- Name: blog_published; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.blog_published (
    published_id text NOT NULL,
    draft_id text NOT NULL,
    user_id text NOT NULL,
    symbol text NOT NULL,
    title text NOT NULL,
    slug text NOT NULL,
    content text NOT NULL,
    meta_description text,
    tags json,
    published_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    published_to json NOT NULL,
    seo_data json,
    view_count integer DEFAULT 0,
    engagement_score real DEFAULT 0.0
);


--
-- Name: blog_publishing_config; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.blog_publishing_config (
    config_id text NOT NULL,
    user_id text NOT NULL,
    auto_generate boolean DEFAULT false,
    auto_publish boolean DEFAULT false,
    min_topic_score real DEFAULT 70.0,
    publishing_destinations json,
    content_preferences json,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: blog_topics; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.blog_topics (
    topic_id text NOT NULL,
    user_id text,
    symbol text NOT NULL,
    topic_type text NOT NULL,
    reason json NOT NULL,
    urgency text DEFAULT 'medium'::text,
    audience text DEFAULT 'basic_to_pro'::text,
    confidence real DEFAULT 0.5,
    score real DEFAULT 0.0,
    context_data json,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    expires_at timestamp without time zone,
    CONSTRAINT blog_topics_audience_check CHECK ((audience = ANY (ARRAY['basic'::text, 'pro'::text, 'elite'::text, 'basic_to_pro'::text, 'all'::text]))),
    CONSTRAINT blog_topics_topic_type_check CHECK ((topic_type = ANY (ARRAY['signal_change'::text, 'golden_cross'::text, 'rsi_extreme'::text, 'earnings_proximity'::text, 'portfolio_heavy'::text, 'volume_spike'::text, 'trend_reversal'::text]))),
    CONSTRAINT blog_topics_urgency_check CHECK ((urgency = ANY (ARRAY['low'::text, 'medium'::text, 'high'::text, 'critical'::text])))
);


--
-- Name: cash_flow_statements; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cash_flow_statements (
    id bigint NOT NULL,
    stock_symbol text NOT NULL,
    period_end date NOT NULL,
    filing_date date,
    fiscal_year integer,
    fiscal_quarter integer,
    timeframe text,
    net_income real,
    depreciation_depletion_and_amortization real,
    change_in_other_operating_assets_and_liabilities_net real,
    other_operating_activities real,
    net_cash_from_operating_activities real,
    cash_from_operating_activities_continuing_operations real,
    net_cash_from_operating_activities_discontinued_operations real,
    purchase_of_property_plant_and_equipment real,
    sale_of_property_plant_and_equipment real,
    other_investing_activities real,
    net_cash_from_investing_activities real,
    net_cash_from_investing_activities_continuing_operations real,
    net_cash_from_investing_activities_discontinued_operations real,
    short_term_debt_issuances_repayments real,
    long_term_debt_issuances_repayments real,
    dividends real,
    other_financing_activities real,
    net_cash_from_financing_activities real,
    net_cash_from_financing_activities_continuing_operations real,
    net_cash_from_financing_activities_discontinued_operations real,
    effect_of_currency_exchange_rate real,
    other_cash_adjustments real,
    change_in_cash_and_equivalents real,
    income_loss_from_discontinued_operations real,
    noncontrolling_interests real,
    cik text,
    tickers text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT cash_flow_statements_timeframe_check CHECK ((timeframe = ANY (ARRAY['quarterly'::text, 'annual'::text, 'trailing_twelve_months'::text])))
);


--
-- Name: cash_flow_statements_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.cash_flow_statements_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: cash_flow_statements_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.cash_flow_statements_id_seq OWNED BY public.cash_flow_statements.id;


--
-- Name: data_fetch_audit; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.data_fetch_audit (
    audit_id text NOT NULL,
    symbol text NOT NULL,
    fetch_type text NOT NULL,
    fetch_mode text NOT NULL,
    fetch_timestamp timestamp without time zone NOT NULL,
    data_source text,
    rows_fetched integer DEFAULT 0,
    rows_saved integer DEFAULT 0,
    fetch_duration_ms integer,
    success boolean NOT NULL,
    error_message text,
    validation_report_id text,
    metadata text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: data_refresh_tracking; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.data_refresh_tracking (
    id bigint NOT NULL,
    stock_symbol text NOT NULL,
    data_type text NOT NULL,
    refresh_mode text NOT NULL,
    last_refresh timestamp without time zone NOT NULL,
    next_refresh timestamp without time zone,
    status text,
    error_message text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT data_refresh_tracking_status_check CHECK ((status = ANY (ARRAY['success'::text, 'failed'::text, 'pending'::text])))
);


--
-- Name: data_refresh_tracking_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.data_refresh_tracking_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: data_refresh_tracking_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.data_refresh_tracking_id_seq OWNED BY public.data_refresh_tracking.id;


--
-- Name: data_validation_reports; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.data_validation_reports (
    report_id text NOT NULL,
    symbol text NOT NULL,
    data_type text NOT NULL,
    validation_timestamp timestamp without time zone NOT NULL,
    report_json text NOT NULL,
    overall_status text NOT NULL,
    critical_issues integer DEFAULT 0,
    warnings integer DEFAULT 0,
    rows_dropped integer DEFAULT 0,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT data_validation_reports_overall_status_check CHECK ((overall_status = ANY (ARRAY['pass'::text, 'warning'::text, 'fail'::text])))
);


--
-- Name: earnings_data; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.earnings_data (
    earnings_id text NOT NULL,
    stock_symbol text NOT NULL,
    earnings_date date NOT NULL,
    eps_estimate real,
    eps_actual real,
    revenue_estimate real,
    revenue_actual real,
    surprise_percentage real,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: enhanced_fundamentals; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.enhanced_fundamentals (
    id bigint NOT NULL,
    stock_symbol text NOT NULL,
    as_of_date date NOT NULL,
    market_cap real,
    enterprise_value real,
    pe_ratio real,
    forward_pe real,
    price_to_book real,
    price_to_sales real,
    peg_ratio real,
    ev_to_ebitda real,
    revenue real,
    gross_profit real,
    operating_income real,
    net_income real,
    eps real,
    profit_margin real,
    operating_margin real,
    gross_margin real,
    roe real,
    roa real,
    roic real,
    revenue_growth real,
    earnings_growth real,
    eps_growth real,
    total_assets real,
    total_liabilities real,
    total_equity real,
    debt_to_equity real,
    debt_to_assets real,
    current_ratio real,
    quick_ratio real,
    operating_cash_flow real,
    free_cash_flow real,
    cash_and_equivalents real,
    shares_outstanding real,
    float_shares real,
    short_interest real,
    days_to_cover real,
    short_volume_ratio real,
    dividend_yield real,
    dividend_per_share real,
    dividend_payout_ratio real,
    sector text,
    industry text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: enhanced_fundamentals_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.enhanced_fundamentals_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: enhanced_fundamentals_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.enhanced_fundamentals_id_seq OWNED BY public.enhanced_fundamentals.id;


--
-- Name: financial_ratios; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.financial_ratios (
    id bigint NOT NULL,
    stock_symbol text NOT NULL,
    period_end date NOT NULL,
    fiscal_year integer,
    fiscal_quarter integer,
    timeframe text,
    price_to_earnings real,
    price_to_book real,
    price_to_sales real,
    price_to_free_cash_flow real,
    enterprise_value_to_ebitda real,
    enterprise_value_to_revenue real,
    gross_profit_margin real,
    operating_margin real,
    net_profit_margin real,
    return_on_equity real,
    return_on_assets real,
    return_on_invested_capital real,
    asset_turnover real,
    inventory_turnover real,
    receivables_turnover real,
    debt_to_equity real,
    debt_to_assets real,
    equity_multiplier real,
    interest_coverage real,
    current_ratio real,
    quick_ratio real,
    cash_ratio real,
    revenue_growth real,
    earnings_growth real,
    eps_growth real,
    earnings_per_share real,
    book_value_per_share real,
    cash_per_share real,
    free_cash_flow_per_share real,
    cik text,
    tickers text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT financial_ratios_timeframe_check CHECK ((timeframe = ANY (ARRAY['quarterly'::text, 'annual'::text, 'trailing_twelve_months'::text])))
);


--
-- Name: financial_ratios_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.financial_ratios_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: financial_ratios_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.financial_ratios_id_seq OWNED BY public.financial_ratios.id;


--
-- Name: holdings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.holdings (
    holding_id text NOT NULL,
    portfolio_id text NOT NULL,
    stock_symbol text NOT NULL,
    quantity real NOT NULL,
    avg_entry_price real NOT NULL,
    position_type text NOT NULL,
    strategy_tag text,
    purchase_date date NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    notes text,
    current_price real,
    current_value real,
    cost_basis real,
    unrealized_gain_loss real,
    unrealized_gain_loss_percent real,
    realized_gain_loss real DEFAULT 0,
    exit_price real,
    exit_date date,
    commission real DEFAULT 0,
    tax_lot_id text,
    cost_basis_method text DEFAULT 'average'::text,
    sector text,
    industry text,
    market_cap_category text,
    dividend_yield real,
    target_price real,
    stop_loss_price real,
    take_profit_price real,
    allocation_percent real,
    target_allocation_percent real,
    last_updated_price timestamp without time zone,
    is_closed boolean DEFAULT false,
    closed_reason text,
    metadata json,
    CONSTRAINT holdings_cost_basis_method_check CHECK ((cost_basis_method = ANY (ARRAY['FIFO'::text, 'LIFO'::text, 'average'::text, 'specific_lot'::text]))),
    CONSTRAINT holdings_market_cap_category_check CHECK ((market_cap_category = ANY (ARRAY['mega'::text, 'large'::text, 'mid'::text, 'small'::text, 'micro'::text]))),
    CONSTRAINT holdings_position_type_check CHECK ((position_type = ANY (ARRAY['long'::text, 'short'::text, 'call_option'::text, 'put_option'::text])))
);


--
-- Name: income_statements; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.income_statements (
    id bigint NOT NULL,
    stock_symbol text NOT NULL,
    period_end date NOT NULL,
    filing_date date,
    fiscal_year integer,
    fiscal_quarter integer,
    timeframe text,
    revenues real,
    total_revenue real,
    cost_of_revenue real,
    gross_profit real,
    operating_expenses real,
    research_and_development real,
    selling_general_and_administrative real,
    operating_income real,
    interest_expense real,
    interest_income real,
    other_income_expense real,
    income_before_tax real,
    income_tax_expense real,
    net_income real,
    net_income_attributable_to_parent real,
    net_income_attributable_to_noncontrolling_interests real,
    net_income_per_share real,
    weighted_average_shares_outstanding real,
    weighted_average_diluted_shares_outstanding real,
    cik text,
    tickers text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT income_statements_timeframe_check CHECK ((timeframe = ANY (ARRAY['quarterly'::text, 'annual'::text])))
);


--
-- Name: income_statements_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.income_statements_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: income_statements_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.income_statements_id_seq OWNED BY public.income_statements.id;


--
-- Name: industry_peers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.industry_peers (
    id bigint NOT NULL,
    stock_symbol text NOT NULL,
    sector text,
    industry text,
    peer_symbol text NOT NULL,
    peer_name text,
    peer_market_cap real,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: industry_peers_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.industry_peers_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: industry_peers_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.industry_peers_id_seq OWNED BY public.industry_peers.id;


--
-- Name: raw_market_data; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.raw_market_data (
    id bigint NOT NULL,
    stock_symbol text NOT NULL,
    date date NOT NULL,
    open real NOT NULL,
    high real NOT NULL,
    low real NOT NULL,
    close real NOT NULL,
    volume bigint NOT NULL,
    fundamental_data jsonb,
    options_data jsonb,
    news_metadata jsonb,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone,
    data_source text,
    data_frequency text,
    CONSTRAINT raw_market_data_data_frequency_check CHECK ((data_frequency = ANY (ARRAY['intraday'::text, 'daily'::text, 'weekly'::text, 'monthly'::text, 'quarterly'::text, 'yearly'::text])))
);


--
-- Name: latest_market_data; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.latest_market_data AS
 SELECT raw_market_data.stock_symbol,
    max(raw_market_data.date) AS latest_date,
    count(*) AS total_records,
    min(raw_market_data.date) AS earliest_date
   FROM public.raw_market_data
  GROUP BY raw_market_data.stock_symbol;


--
-- Name: live_prices; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.live_prices (
    id bigint NOT NULL,
    stock_symbol text NOT NULL,
    price real NOT NULL,
    change real,
    change_percent real,
    volume integer,
    "timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: live_prices_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.live_prices_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: live_prices_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.live_prices_id_seq OWNED BY public.live_prices.id;


--
-- Name: llm_generated_reports; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.llm_generated_reports (
    report_id text NOT NULL,
    portfolio_id text,
    stock_symbol text,
    generated_content text NOT NULL,
    report_type text,
    "timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT llm_generated_reports_report_type_check CHECK ((report_type = ANY (ARRAY['portfolio_analysis'::text, 'stock_analysis'::text, 'signal_explanation'::text, 'blog_post'::text])))
);


--
-- Name: market_movers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.market_movers (
    id bigint NOT NULL,
    stock_symbol text NOT NULL,
    period text NOT NULL,
    price_change real NOT NULL,
    price_change_percent real NOT NULL,
    volume integer,
    market_cap real,
    sector text,
    industry text,
    "timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT market_movers_period_check CHECK ((period = ANY (ARRAY['day'::text, 'week'::text, 'month'::text, 'ytd'::text])))
);


--
-- Name: market_movers_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.market_movers_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: market_movers_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.market_movers_id_seq OWNED BY public.market_movers.id;


--
-- Name: market_overview; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.market_overview (
    id bigint NOT NULL,
    date date NOT NULL,
    market_status text DEFAULT 'closed'::text,
    sp500_price real,
    sp500_change real,
    sp500_change_percent real,
    nasdaq_price real,
    nasdaq_change real,
    nasdaq_change_percent real,
    dow_price real,
    dow_change real,
    dow_change_percent real,
    total_volume bigint,
    advancing_stocks integer,
    declining_stocks integer,
    unchanged_stocks integer,
    new_highs integer,
    new_lows integer,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT market_overview_market_status_check CHECK ((market_status = ANY (ARRAY['open'::text, 'closed'::text, 'pre_market'::text, 'after_hours'::text])))
);


--
-- Name: market_overview_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.market_overview_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: market_overview_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.market_overview_id_seq OWNED BY public.market_overview.id;


--
-- Name: market_trends; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.market_trends (
    id bigint NOT NULL,
    date date NOT NULL,
    trend_type text NOT NULL,
    category text NOT NULL,
    trend_score real,
    price_change_avg real,
    volume_change_avg real,
    momentum_score real,
    strength text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT market_trends_strength_check CHECK ((strength = ANY (ARRAY['very_strong'::text, 'strong'::text, 'moderate'::text, 'weak'::text, 'very_weak'::text]))),
    CONSTRAINT market_trends_trend_type_check CHECK ((trend_type = ANY (ARRAY['sector'::text, 'industry'::text, 'market_cap'::text, 'overall'::text])))
);


--
-- Name: market_trends_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.market_trends_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: market_trends_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.market_trends_id_seq OWNED BY public.market_trends.id;


--
-- Name: multi_timeframe_data; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.multi_timeframe_data (
    id bigint NOT NULL,
    stock_symbol text NOT NULL,
    timeframe text NOT NULL,
    date date NOT NULL,
    open real,
    high real,
    low real,
    close real,
    volume integer,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT multi_timeframe_data_timeframe_check CHECK ((timeframe = ANY (ARRAY['daily'::text, 'weekly'::text, 'monthly'::text])))
);


--
-- Name: multi_timeframe_data_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.multi_timeframe_data_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: multi_timeframe_data_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.multi_timeframe_data_id_seq OWNED BY public.multi_timeframe_data.id;


--
-- Name: notification_channels; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.notification_channels (
    channel_id text NOT NULL,
    user_id text NOT NULL,
    channel_type text NOT NULL,
    address text NOT NULL,
    verified boolean DEFAULT false,
    enabled boolean DEFAULT true,
    config json,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT notification_channels_channel_type_check CHECK ((channel_type = ANY (ARRAY['email'::text, 'sms'::text, 'push'::text, 'webhook'::text])))
);


--
-- Name: portfolio_performance; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.portfolio_performance (
    id bigint NOT NULL,
    portfolio_id text NOT NULL,
    snapshot_date date NOT NULL,
    total_value real NOT NULL,
    cost_basis real NOT NULL,
    total_gain_loss real NOT NULL,
    total_gain_loss_percent real NOT NULL,
    cash_balance real DEFAULT 0,
    invested_amount real NOT NULL,
    day_change real,
    day_change_percent real,
    week_change real,
    week_change_percent real,
    month_change real,
    month_change_percent real,
    year_change real,
    year_change_percent real,
    max_drawdown real,
    sharpe_ratio real,
    beta real,
    alpha real,
    sector_allocation json,
    top_holdings json,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: portfolio_performance_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.portfolio_performance_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: portfolio_performance_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.portfolio_performance_id_seq OWNED BY public.portfolio_performance.id;


--
-- Name: portfolio_signals; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.portfolio_signals (
    signal_id text NOT NULL,
    portfolio_id text NOT NULL,
    stock_symbol text NOT NULL,
    date date NOT NULL,
    signal_type text NOT NULL,
    suggested_allocation real,
    stop_loss real,
    confidence_score real,
    subscription_level_required text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT portfolio_signals_signal_type_check CHECK ((signal_type = ANY (ARRAY['buy'::text, 'sell'::text, 'hold'::text, 'covered_call'::text, 'protective_put'::text]))),
    CONSTRAINT portfolio_signals_subscription_level_required_check CHECK ((subscription_level_required = ANY (ARRAY['basic'::text, 'pro'::text, 'elite'::text])))
);


--
-- Name: portfolios; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.portfolios (
    portfolio_id text NOT NULL,
    user_id text NOT NULL,
    portfolio_name text NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    strategy_name text,
    notes text,
    portfolio_type text DEFAULT 'mixed'::text,
    currency text DEFAULT 'USD'::text,
    benchmark_symbol text,
    target_allocation json,
    risk_tolerance text DEFAULT 'moderate'::text,
    investment_horizon text DEFAULT 'medium_term'::text,
    is_taxable boolean DEFAULT true,
    tax_strategy text,
    rebalancing_frequency text DEFAULT 'manual'::text,
    last_rebalanced date,
    color_code text,
    is_archived boolean DEFAULT false,
    metadata json,
    CONSTRAINT portfolios_investment_horizon_check CHECK ((investment_horizon = ANY (ARRAY['short_term'::text, 'medium_term'::text, 'long_term'::text]))),
    CONSTRAINT portfolios_portfolio_type_check CHECK ((portfolio_type = ANY (ARRAY['long_term'::text, 'swing'::text, 'day_trading'::text, 'options'::text, 'crypto'::text, 'mixed'::text]))),
    CONSTRAINT portfolios_rebalancing_frequency_check CHECK ((rebalancing_frequency = ANY (ARRAY['daily'::text, 'weekly'::text, 'monthly'::text, 'quarterly'::text, 'annually'::text, 'manual'::text]))),
    CONSTRAINT portfolios_risk_tolerance_check CHECK ((risk_tolerance = ANY (ARRAY['conservative'::text, 'moderate'::text, 'aggressive'::text])))
);


--
-- Name: potential_duplicates; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.potential_duplicates AS
 SELECT raw_market_data.stock_symbol,
    raw_market_data.date,
    count(*) AS duplicate_count,
    string_agg((raw_market_data.id)::text, ','::text ORDER BY raw_market_data.id) AS record_ids
   FROM public.raw_market_data
  GROUP BY raw_market_data.stock_symbol, raw_market_data.date
 HAVING (count(*) > 1);


--
-- Name: raw_market_data_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.raw_market_data_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: raw_market_data_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.raw_market_data_id_seq OWNED BY public.raw_market_data.id;


--
-- Name: risk_categories; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.risk_categories (
    id bigint NOT NULL,
    stock_symbol text NOT NULL,
    filing_date date NOT NULL,
    category text NOT NULL,
    category_count integer DEFAULT 1,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: risk_categories_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.risk_categories_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: risk_categories_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.risk_categories_id_seq OWNED BY public.risk_categories.id;


--
-- Name: risk_factors; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.risk_factors (
    id bigint NOT NULL,
    stock_symbol text NOT NULL,
    filing_date date NOT NULL,
    period_end date,
    risk_factor_text text NOT NULL,
    risk_category text,
    severity text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT risk_factors_severity_check CHECK ((severity = ANY (ARRAY['low'::text, 'medium'::text, 'high'::text, 'critical'::text])))
);


--
-- Name: risk_factors_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.risk_factors_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: risk_factors_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.risk_factors_id_seq OWNED BY public.risk_factors.id;


--
-- Name: saved_screeners; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.saved_screeners (
    screener_id text NOT NULL,
    user_id text NOT NULL,
    screener_name text NOT NULL,
    filters json NOT NULL,
    sort_by text,
    sort_order text DEFAULT 'desc'::text,
    max_results integer DEFAULT 100,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT saved_screeners_sort_order_check CHECK ((sort_order = ANY (ARRAY['asc'::text, 'desc'::text])))
);


--
-- Name: sector_performance; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sector_performance (
    id bigint NOT NULL,
    sector text NOT NULL,
    date date NOT NULL,
    total_stocks integer DEFAULT 0,
    avg_price_change real DEFAULT 0,
    avg_price_change_percent real DEFAULT 0,
    gainers_count integer DEFAULT 0,
    losers_count integer DEFAULT 0,
    neutral_count integer DEFAULT 0,
    top_stocks json,
    market_cap_total real,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: sector_performance_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.sector_performance_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: sector_performance_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.sector_performance_id_seq OWNED BY public.sector_performance.id;


--
-- Name: share_float; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.share_float (
    id bigint NOT NULL,
    stock_symbol text NOT NULL,
    date date NOT NULL,
    shares_outstanding real,
    float_shares real,
    restricted_shares real,
    insider_shares real,
    institutional_shares real,
    float_percentage real,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: share_float_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.share_float_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: share_float_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.share_float_id_seq OWNED BY public.share_float.id;


--
-- Name: short_interest; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.short_interest (
    id bigint NOT NULL,
    stock_symbol text NOT NULL,
    settlement_date date NOT NULL,
    short_interest real,
    average_volume real,
    days_to_cover real,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: short_interest_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.short_interest_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: short_interest_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.short_interest_id_seq OWNED BY public.short_interest.id;


--
-- Name: short_volume; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.short_volume (
    id bigint NOT NULL,
    stock_symbol text NOT NULL,
    date date NOT NULL,
    short_volume integer,
    total_volume integer,
    short_volume_ratio real,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: short_volume_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.short_volume_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: short_volume_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.short_volume_id_seq OWNED BY public.short_volume.id;


--
-- Name: signal_readiness; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.signal_readiness (
    readiness_id text NOT NULL,
    symbol text NOT NULL,
    signal_type text NOT NULL,
    readiness_status text NOT NULL,
    required_indicators text NOT NULL,
    available_indicators text NOT NULL,
    missing_indicators text,
    data_quality_score real,
    validation_report_id text,
    readiness_timestamp timestamp without time zone NOT NULL,
    readiness_reason text,
    recommendations text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT signal_readiness_readiness_status_check CHECK ((readiness_status = ANY (ARRAY['ready'::text, 'not_ready'::text, 'partial'::text])))
);


--
-- Name: stock_news; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.stock_news (
    news_id text NOT NULL,
    stock_symbol text NOT NULL,
    title text NOT NULL,
    publisher text,
    link text,
    published_date timestamp without time zone,
    sentiment_score real,
    related_symbols text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: swing_backtest_results; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.swing_backtest_results (
    backtest_id text NOT NULL,
    user_id text NOT NULL,
    strategy_name text NOT NULL,
    stock_symbol text NOT NULL,
    start_date date NOT NULL,
    end_date date NOT NULL,
    initial_capital real NOT NULL,
    final_capital real NOT NULL,
    total_return real,
    total_return_pct real,
    win_rate real,
    profit_factor real,
    sharpe_ratio real,
    max_drawdown real,
    max_drawdown_pct real,
    avg_win real,
    avg_loss real,
    total_trades integer,
    winning_trades integer,
    losing_trades integer,
    avg_hold_days real,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: swing_indicators; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.swing_indicators (
    id bigint NOT NULL,
    stock_symbol text NOT NULL,
    date date NOT NULL,
    timeframe text NOT NULL,
    adx real,
    di_plus real,
    di_minus real,
    stochastic_k real,
    stochastic_d real,
    williams_r real,
    vwap real,
    ichimoku_tenkan real,
    ichimoku_kijun real,
    ichimoku_senkou_a real,
    ichimoku_senkou_b real,
    fib_382 real,
    fib_500 real,
    fib_618 real,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT swing_indicators_timeframe_check CHECK ((timeframe = ANY (ARRAY['daily'::text, 'weekly'::text])))
);


--
-- Name: swing_indicators_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.swing_indicators_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: swing_indicators_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.swing_indicators_id_seq OWNED BY public.swing_indicators.id;


--
-- Name: swing_trade_signals; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.swing_trade_signals (
    signal_id text NOT NULL,
    trade_id text,
    user_id text NOT NULL,
    stock_symbol text NOT NULL,
    strategy_name text NOT NULL,
    signal_type text NOT NULL,
    signal_price real NOT NULL,
    signal_date date NOT NULL,
    signal_reason text,
    timeframe text NOT NULL,
    confidence real,
    risk_reward_ratio real,
    executed boolean DEFAULT false,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT swing_trade_signals_signal_type_check CHECK ((signal_type = ANY (ARRAY['entry'::text, 'exit'::text, 'stop'::text, 'take_profit'::text])))
);


--
-- Name: swing_trades; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.swing_trades (
    trade_id text NOT NULL,
    user_id text NOT NULL,
    stock_symbol text NOT NULL,
    strategy_name text NOT NULL,
    entry_date date NOT NULL,
    entry_price real NOT NULL,
    entry_reason text,
    position_size real NOT NULL,
    stop_loss real NOT NULL,
    take_profit real NOT NULL,
    trailing_stop real,
    max_hold_days integer DEFAULT 7,
    exit_date date,
    exit_price real,
    exit_reason text,
    pnl real,
    pnl_percent real,
    risk_reward_ratio real,
    status text DEFAULT 'open'::text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT swing_trades_status_check CHECK ((status = ANY (ARRAY['open'::text, 'closed'::text, 'stopped'::text])))
);


--
-- Name: trading_activity; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.trading_activity (
    activity_id text NOT NULL,
    user_id text NOT NULL,
    portfolio_id text,
    watchlist_id text,
    stock_symbol text NOT NULL,
    activity_type text NOT NULL,
    quantity real,
    price real,
    commission real DEFAULT 0,
    notes text,
    metadata json,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT trading_activity_activity_type_check CHECK ((activity_type = ANY (ARRAY['buy'::text, 'sell'::text, 'add_to_watchlist'::text, 'remove_from_watchlist'::text, 'move_to_portfolio'::text, 'alert_triggered'::text, 'signal_generated'::text])))
);


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    user_id text NOT NULL,
    username text NOT NULL,
    email text NOT NULL,
    password_hash text NOT NULL,
    subscription_level text DEFAULT 'basic'::text NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    preferred_strategy text DEFAULT 'technical'::text,
    CONSTRAINT users_preferred_strategy_check CHECK ((preferred_strategy = ANY (ARRAY['technical'::text, 'hybrid_llm'::text, 'custom'::text]))),
    CONSTRAINT users_subscription_level_check CHECK ((subscription_level = ANY (ARRAY['basic'::text, 'pro'::text, 'elite'::text])))
);


--
-- Name: watchlist_alerts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.watchlist_alerts (
    alert_id text NOT NULL,
    watchlist_id text NOT NULL,
    stock_symbol text,
    alert_type text NOT NULL,
    name text NOT NULL,
    enabled boolean DEFAULT true,
    config json NOT NULL,
    notification_channels text NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: watchlist_analytics; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.watchlist_analytics (
    id bigint NOT NULL,
    watchlist_id text NOT NULL,
    date date NOT NULL,
    total_stocks integer,
    avg_trend_score real,
    avg_risk_score real,
    bullish_count integer,
    bearish_count integer,
    neutral_count integer,
    high_risk_count integer,
    medium_risk_count integer,
    low_risk_count integer,
    sector_distribution json,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: watchlist_analytics_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.watchlist_analytics_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: watchlist_analytics_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.watchlist_analytics_id_seq OWNED BY public.watchlist_analytics.id;


--
-- Name: watchlist_items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.watchlist_items (
    item_id text NOT NULL,
    watchlist_id text NOT NULL,
    stock_symbol text NOT NULL,
    added_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    notes text,
    priority integer DEFAULT 0,
    tags text,
    alert_config json,
    price_when_added real,
    target_price real,
    target_date date,
    watch_reason text,
    analyst_rating text,
    analyst_price_target real,
    current_price real,
    price_change_since_added real,
    price_change_percent_since_added real,
    sector text,
    industry text,
    market_cap_category text,
    dividend_yield real,
    earnings_date date,
    last_updated_price timestamp without time zone,
    metadata json,
    CONSTRAINT watchlist_items_analyst_rating_check CHECK ((analyst_rating = ANY (ARRAY['strong_buy'::text, 'buy'::text, 'hold'::text, 'sell'::text, 'strong_sell'::text]))),
    CONSTRAINT watchlist_items_market_cap_category_check CHECK ((market_cap_category = ANY (ARRAY['mega'::text, 'large'::text, 'mid'::text, 'small'::text, 'micro'::text])))
);


--
-- Name: watchlist_performance; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.watchlist_performance (
    id bigint NOT NULL,
    watchlist_id text NOT NULL,
    snapshot_date date NOT NULL,
    total_stocks integer NOT NULL,
    avg_price_change real,
    avg_price_change_percent real,
    bullish_count integer,
    bearish_count integer,
    neutral_count integer,
    high_risk_count integer,
    medium_risk_count integer,
    low_risk_count integer,
    sector_distribution json,
    top_gainers json,
    top_losers json,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: watchlist_performance_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.watchlist_performance_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: watchlist_performance_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.watchlist_performance_id_seq OWNED BY public.watchlist_performance.id;


--
-- Name: watchlists; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.watchlists (
    watchlist_id text NOT NULL,
    user_id text NOT NULL,
    watchlist_name text NOT NULL,
    description text,
    tags text,
    is_default boolean DEFAULT false,
    subscription_level_required text DEFAULT 'basic'::text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    color_code text,
    sort_order integer DEFAULT 0,
    view_preferences json,
    is_archived boolean DEFAULT false,
    metadata json,
    CONSTRAINT watchlists_subscription_level_required_check CHECK ((subscription_level_required = ANY (ARRAY['basic'::text, 'pro'::text, 'elite'::text])))
);


--
-- Name: workflow_checkpoints; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.workflow_checkpoints (
    checkpoint_id text NOT NULL,
    workflow_id text NOT NULL,
    stage text NOT NULL,
    state_json text NOT NULL,
    "timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: workflow_dlq; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.workflow_dlq (
    dlq_id text NOT NULL,
    workflow_id text NOT NULL,
    symbol text NOT NULL,
    stage text NOT NULL,
    error_message text NOT NULL,
    error_type text,
    context_json text,
    retry_count integer DEFAULT 0,
    resolved boolean DEFAULT false,
    resolved_at timestamp without time zone,
    resolved_by text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: workflow_executions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.workflow_executions (
    workflow_id text NOT NULL,
    workflow_type text NOT NULL,
    status text NOT NULL,
    current_stage text,
    started_at timestamp without time zone,
    completed_at timestamp without time zone,
    error_message text,
    metadata_json text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT workflow_executions_status_check CHECK ((status = ANY (ARRAY['pending'::text, 'running'::text, 'completed'::text, 'failed'::text, 'paused'::text, 'cancelled'::text])))
);


--
-- Name: workflow_gate_results; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.workflow_gate_results (
    gate_result_id text NOT NULL,
    workflow_id text NOT NULL,
    stage text NOT NULL,
    symbol text NOT NULL,
    gate_name text NOT NULL,
    passed boolean NOT NULL,
    reason text,
    action text,
    checked_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: workflow_stage_executions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.workflow_stage_executions (
    stage_execution_id text NOT NULL,
    workflow_id text NOT NULL,
    stage_name text NOT NULL,
    status text NOT NULL,
    started_at timestamp without time zone,
    completed_at timestamp without time zone,
    error_message text,
    retry_count integer DEFAULT 0,
    symbols_processed integer DEFAULT 0,
    symbols_succeeded integer DEFAULT 0,
    symbols_failed integer DEFAULT 0,
    updated_at timestamp without time zone,
    CONSTRAINT workflow_stage_executions_status_check CHECK ((status = ANY (ARRAY['pending'::text, 'running'::text, 'completed'::text, 'failed'::text, 'skipped'::text])))
);


--
-- Name: workflow_symbol_states; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.workflow_symbol_states (
    id bigint NOT NULL,
    workflow_id text NOT NULL,
    symbol text NOT NULL,
    stage text NOT NULL,
    status text NOT NULL,
    error_message text,
    retry_count integer DEFAULT 0,
    started_at timestamp without time zone,
    completed_at timestamp without time zone,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT workflow_symbol_states_status_check CHECK ((status = ANY (ARRAY['pending'::text, 'running'::text, 'completed'::text, 'failed'::text, 'skipped'::text, 'retrying'::text])))
);


--
-- Name: workflow_symbol_states_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.workflow_symbol_states_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: workflow_symbol_states_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.workflow_symbol_states_id_seq OWNED BY public.workflow_symbol_states.id;


--
-- Name: aggregated_indicators id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.aggregated_indicators ALTER COLUMN id SET DEFAULT nextval('public.aggregated_indicators_id_seq'::regclass);


--
-- Name: analyst_consensus id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analyst_consensus ALTER COLUMN id SET DEFAULT nextval('public.analyst_consensus_id_seq'::regclass);


--
-- Name: analyst_ratings id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analyst_ratings ALTER COLUMN id SET DEFAULT nextval('public.analyst_ratings_id_seq'::regclass);


--
-- Name: balance_sheets id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.balance_sheets ALTER COLUMN id SET DEFAULT nextval('public.balance_sheets_id_seq'::regclass);


--
-- Name: blog_generation_log log_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.blog_generation_log ALTER COLUMN log_id SET DEFAULT nextval('public.blog_generation_log_log_id_seq'::regclass);


--
-- Name: cash_flow_statements id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cash_flow_statements ALTER COLUMN id SET DEFAULT nextval('public.cash_flow_statements_id_seq'::regclass);


--
-- Name: data_refresh_tracking id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.data_refresh_tracking ALTER COLUMN id SET DEFAULT nextval('public.data_refresh_tracking_id_seq'::regclass);


--
-- Name: enhanced_fundamentals id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.enhanced_fundamentals ALTER COLUMN id SET DEFAULT nextval('public.enhanced_fundamentals_id_seq'::regclass);


--
-- Name: financial_ratios id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.financial_ratios ALTER COLUMN id SET DEFAULT nextval('public.financial_ratios_id_seq'::regclass);


--
-- Name: income_statements id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.income_statements ALTER COLUMN id SET DEFAULT nextval('public.income_statements_id_seq'::regclass);


--
-- Name: industry_peers id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.industry_peers ALTER COLUMN id SET DEFAULT nextval('public.industry_peers_id_seq'::regclass);


--
-- Name: live_prices id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.live_prices ALTER COLUMN id SET DEFAULT nextval('public.live_prices_id_seq'::regclass);


--
-- Name: market_movers id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.market_movers ALTER COLUMN id SET DEFAULT nextval('public.market_movers_id_seq'::regclass);


--
-- Name: market_overview id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.market_overview ALTER COLUMN id SET DEFAULT nextval('public.market_overview_id_seq'::regclass);


--
-- Name: market_trends id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.market_trends ALTER COLUMN id SET DEFAULT nextval('public.market_trends_id_seq'::regclass);


--
-- Name: multi_timeframe_data id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.multi_timeframe_data ALTER COLUMN id SET DEFAULT nextval('public.multi_timeframe_data_id_seq'::regclass);


--
-- Name: portfolio_performance id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.portfolio_performance ALTER COLUMN id SET DEFAULT nextval('public.portfolio_performance_id_seq'::regclass);


--
-- Name: raw_market_data id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.raw_market_data ALTER COLUMN id SET DEFAULT nextval('public.raw_market_data_id_seq'::regclass);


--
-- Name: risk_categories id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.risk_categories ALTER COLUMN id SET DEFAULT nextval('public.risk_categories_id_seq'::regclass);


--
-- Name: risk_factors id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.risk_factors ALTER COLUMN id SET DEFAULT nextval('public.risk_factors_id_seq'::regclass);


--
-- Name: sector_performance id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sector_performance ALTER COLUMN id SET DEFAULT nextval('public.sector_performance_id_seq'::regclass);


--
-- Name: share_float id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.share_float ALTER COLUMN id SET DEFAULT nextval('public.share_float_id_seq'::regclass);


--
-- Name: short_interest id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.short_interest ALTER COLUMN id SET DEFAULT nextval('public.short_interest_id_seq'::regclass);


--
-- Name: short_volume id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.short_volume ALTER COLUMN id SET DEFAULT nextval('public.short_volume_id_seq'::regclass);


--
-- Name: swing_indicators id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.swing_indicators ALTER COLUMN id SET DEFAULT nextval('public.swing_indicators_id_seq'::regclass);


--
-- Name: watchlist_analytics id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.watchlist_analytics ALTER COLUMN id SET DEFAULT nextval('public.watchlist_analytics_id_seq'::regclass);


--
-- Name: watchlist_performance id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.watchlist_performance ALTER COLUMN id SET DEFAULT nextval('public.watchlist_performance_id_seq'::regclass);


--
-- Name: workflow_symbol_states id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workflow_symbol_states ALTER COLUMN id SET DEFAULT nextval('public.workflow_symbol_states_id_seq'::regclass);


--
-- Name: aggregated_indicators aggregated_indicators_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.aggregated_indicators
    ADD CONSTRAINT aggregated_indicators_pkey PRIMARY KEY (id);


--
-- Name: aggregated_indicators aggregated_indicators_stock_symbol_date_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.aggregated_indicators
    ADD CONSTRAINT aggregated_indicators_stock_symbol_date_key UNIQUE (stock_symbol, date);


--
-- Name: alert_notifications alert_notifications_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alert_notifications
    ADD CONSTRAINT alert_notifications_pkey PRIMARY KEY (notification_id);


--
-- Name: alert_types alert_types_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alert_types
    ADD CONSTRAINT alert_types_name_key UNIQUE (name);


--
-- Name: alert_types alert_types_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alert_types
    ADD CONSTRAINT alert_types_pkey PRIMARY KEY (alert_type_id);


--
-- Name: alerts alerts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alerts
    ADD CONSTRAINT alerts_pkey PRIMARY KEY (alert_id);


--
-- Name: analyst_consensus analyst_consensus_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analyst_consensus
    ADD CONSTRAINT analyst_consensus_pkey PRIMARY KEY (id);


--
-- Name: analyst_consensus analyst_consensus_stock_symbol_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analyst_consensus
    ADD CONSTRAINT analyst_consensus_stock_symbol_key UNIQUE (stock_symbol);


--
-- Name: analyst_ratings analyst_ratings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analyst_ratings
    ADD CONSTRAINT analyst_ratings_pkey PRIMARY KEY (id);


--
-- Name: analyst_ratings analyst_ratings_stock_symbol_analyst_name_rating_date_sourc_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analyst_ratings
    ADD CONSTRAINT analyst_ratings_stock_symbol_analyst_name_rating_date_sourc_key UNIQUE (stock_symbol, analyst_name, rating_date, source);


--
-- Name: balance_sheets balance_sheets_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.balance_sheets
    ADD CONSTRAINT balance_sheets_pkey PRIMARY KEY (id);


--
-- Name: balance_sheets balance_sheets_stock_symbol_period_end_timeframe_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.balance_sheets
    ADD CONSTRAINT balance_sheets_stock_symbol_period_end_timeframe_key UNIQUE (stock_symbol, period_end, timeframe);


--
-- Name: blog_drafts blog_drafts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.blog_drafts
    ADD CONSTRAINT blog_drafts_pkey PRIMARY KEY (draft_id);


--
-- Name: blog_drafts blog_drafts_slug_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.blog_drafts
    ADD CONSTRAINT blog_drafts_slug_key UNIQUE (slug);


--
-- Name: blog_generation_audit blog_generation_audit_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.blog_generation_audit
    ADD CONSTRAINT blog_generation_audit_pkey PRIMARY KEY (audit_id);


--
-- Name: blog_generation_log blog_generation_log_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.blog_generation_log
    ADD CONSTRAINT blog_generation_log_pkey PRIMARY KEY (log_id);


--
-- Name: blog_published blog_published_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.blog_published
    ADD CONSTRAINT blog_published_pkey PRIMARY KEY (published_id);


--
-- Name: blog_published blog_published_slug_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.blog_published
    ADD CONSTRAINT blog_published_slug_key UNIQUE (slug);


--
-- Name: blog_publishing_config blog_publishing_config_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.blog_publishing_config
    ADD CONSTRAINT blog_publishing_config_pkey PRIMARY KEY (config_id);


--
-- Name: blog_publishing_config blog_publishing_config_user_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.blog_publishing_config
    ADD CONSTRAINT blog_publishing_config_user_id_key UNIQUE (user_id);


--
-- Name: blog_topics blog_topics_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.blog_topics
    ADD CONSTRAINT blog_topics_pkey PRIMARY KEY (topic_id);


--
-- Name: cash_flow_statements cash_flow_statements_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cash_flow_statements
    ADD CONSTRAINT cash_flow_statements_pkey PRIMARY KEY (id);


--
-- Name: cash_flow_statements cash_flow_statements_stock_symbol_period_end_timeframe_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cash_flow_statements
    ADD CONSTRAINT cash_flow_statements_stock_symbol_period_end_timeframe_key UNIQUE (stock_symbol, period_end, timeframe);


--
-- Name: data_fetch_audit data_fetch_audit_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.data_fetch_audit
    ADD CONSTRAINT data_fetch_audit_pkey PRIMARY KEY (audit_id);


--
-- Name: data_refresh_tracking data_refresh_tracking_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.data_refresh_tracking
    ADD CONSTRAINT data_refresh_tracking_pkey PRIMARY KEY (id);


--
-- Name: data_refresh_tracking data_refresh_tracking_stock_symbol_data_type_refresh_mode_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.data_refresh_tracking
    ADD CONSTRAINT data_refresh_tracking_stock_symbol_data_type_refresh_mode_key UNIQUE (stock_symbol, data_type, refresh_mode);


--
-- Name: data_validation_reports data_validation_reports_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.data_validation_reports
    ADD CONSTRAINT data_validation_reports_pkey PRIMARY KEY (report_id);


--
-- Name: earnings_data earnings_data_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.earnings_data
    ADD CONSTRAINT earnings_data_pkey PRIMARY KEY (earnings_id);


--
-- Name: earnings_data earnings_data_stock_symbol_earnings_date_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.earnings_data
    ADD CONSTRAINT earnings_data_stock_symbol_earnings_date_key UNIQUE (stock_symbol, earnings_date);


--
-- Name: enhanced_fundamentals enhanced_fundamentals_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.enhanced_fundamentals
    ADD CONSTRAINT enhanced_fundamentals_pkey PRIMARY KEY (id);


--
-- Name: enhanced_fundamentals enhanced_fundamentals_stock_symbol_as_of_date_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.enhanced_fundamentals
    ADD CONSTRAINT enhanced_fundamentals_stock_symbol_as_of_date_key UNIQUE (stock_symbol, as_of_date);


--
-- Name: financial_ratios financial_ratios_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.financial_ratios
    ADD CONSTRAINT financial_ratios_pkey PRIMARY KEY (id);


--
-- Name: financial_ratios financial_ratios_stock_symbol_period_end_timeframe_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.financial_ratios
    ADD CONSTRAINT financial_ratios_stock_symbol_period_end_timeframe_key UNIQUE (stock_symbol, period_end, timeframe);


--
-- Name: holdings holdings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.holdings
    ADD CONSTRAINT holdings_pkey PRIMARY KEY (holding_id);


--
-- Name: income_statements income_statements_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.income_statements
    ADD CONSTRAINT income_statements_pkey PRIMARY KEY (id);


--
-- Name: income_statements income_statements_stock_symbol_period_end_timeframe_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.income_statements
    ADD CONSTRAINT income_statements_stock_symbol_period_end_timeframe_key UNIQUE (stock_symbol, period_end, timeframe);


--
-- Name: industry_peers industry_peers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.industry_peers
    ADD CONSTRAINT industry_peers_pkey PRIMARY KEY (id);


--
-- Name: industry_peers industry_peers_stock_symbol_peer_symbol_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.industry_peers
    ADD CONSTRAINT industry_peers_stock_symbol_peer_symbol_key UNIQUE (stock_symbol, peer_symbol);


--
-- Name: live_prices live_prices_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.live_prices
    ADD CONSTRAINT live_prices_pkey PRIMARY KEY (id);


--
-- Name: live_prices live_prices_stock_symbol_timestamp_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.live_prices
    ADD CONSTRAINT live_prices_stock_symbol_timestamp_key UNIQUE (stock_symbol, "timestamp");


--
-- Name: llm_generated_reports llm_generated_reports_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.llm_generated_reports
    ADD CONSTRAINT llm_generated_reports_pkey PRIMARY KEY (report_id);


--
-- Name: market_movers market_movers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.market_movers
    ADD CONSTRAINT market_movers_pkey PRIMARY KEY (id);


--
-- Name: market_movers market_movers_stock_symbol_period_timestamp_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.market_movers
    ADD CONSTRAINT market_movers_stock_symbol_period_timestamp_key UNIQUE (stock_symbol, period, "timestamp");


--
-- Name: market_overview market_overview_date_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.market_overview
    ADD CONSTRAINT market_overview_date_key UNIQUE (date);


--
-- Name: market_overview market_overview_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.market_overview
    ADD CONSTRAINT market_overview_pkey PRIMARY KEY (id);


--
-- Name: market_trends market_trends_date_trend_type_category_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.market_trends
    ADD CONSTRAINT market_trends_date_trend_type_category_key UNIQUE (date, trend_type, category);


--
-- Name: market_trends market_trends_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.market_trends
    ADD CONSTRAINT market_trends_pkey PRIMARY KEY (id);


--
-- Name: multi_timeframe_data multi_timeframe_data_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.multi_timeframe_data
    ADD CONSTRAINT multi_timeframe_data_pkey PRIMARY KEY (id);


--
-- Name: multi_timeframe_data multi_timeframe_data_stock_symbol_timeframe_date_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.multi_timeframe_data
    ADD CONSTRAINT multi_timeframe_data_stock_symbol_timeframe_date_key UNIQUE (stock_symbol, timeframe, date);


--
-- Name: notification_channels notification_channels_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notification_channels
    ADD CONSTRAINT notification_channels_pkey PRIMARY KEY (channel_id);


--
-- Name: notification_channels notification_channels_user_id_channel_type_address_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notification_channels
    ADD CONSTRAINT notification_channels_user_id_channel_type_address_key UNIQUE (user_id, channel_type, address);


--
-- Name: portfolio_performance portfolio_performance_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.portfolio_performance
    ADD CONSTRAINT portfolio_performance_pkey PRIMARY KEY (id);


--
-- Name: portfolio_performance portfolio_performance_portfolio_id_snapshot_date_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.portfolio_performance
    ADD CONSTRAINT portfolio_performance_portfolio_id_snapshot_date_key UNIQUE (portfolio_id, snapshot_date);


--
-- Name: portfolio_signals portfolio_signals_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.portfolio_signals
    ADD CONSTRAINT portfolio_signals_pkey PRIMARY KEY (signal_id);


--
-- Name: portfolios portfolios_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.portfolios
    ADD CONSTRAINT portfolios_pkey PRIMARY KEY (portfolio_id);


--
-- Name: raw_market_data raw_market_data_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.raw_market_data
    ADD CONSTRAINT raw_market_data_pkey PRIMARY KEY (id);


--
-- Name: raw_market_data raw_market_data_stock_symbol_date_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.raw_market_data
    ADD CONSTRAINT raw_market_data_stock_symbol_date_key UNIQUE (stock_symbol, date);


--
-- Name: risk_categories risk_categories_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.risk_categories
    ADD CONSTRAINT risk_categories_pkey PRIMARY KEY (id);


--
-- Name: risk_categories risk_categories_stock_symbol_filing_date_category_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.risk_categories
    ADD CONSTRAINT risk_categories_stock_symbol_filing_date_category_key UNIQUE (stock_symbol, filing_date, category);


--
-- Name: risk_factors risk_factors_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.risk_factors
    ADD CONSTRAINT risk_factors_pkey PRIMARY KEY (id);


--
-- Name: saved_screeners saved_screeners_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.saved_screeners
    ADD CONSTRAINT saved_screeners_pkey PRIMARY KEY (screener_id);


--
-- Name: sector_performance sector_performance_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sector_performance
    ADD CONSTRAINT sector_performance_pkey PRIMARY KEY (id);


--
-- Name: sector_performance sector_performance_sector_date_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sector_performance
    ADD CONSTRAINT sector_performance_sector_date_key UNIQUE (sector, date);


--
-- Name: share_float share_float_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.share_float
    ADD CONSTRAINT share_float_pkey PRIMARY KEY (id);


--
-- Name: share_float share_float_stock_symbol_date_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.share_float
    ADD CONSTRAINT share_float_stock_symbol_date_key UNIQUE (stock_symbol, date);


--
-- Name: short_interest short_interest_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.short_interest
    ADD CONSTRAINT short_interest_pkey PRIMARY KEY (id);


--
-- Name: short_interest short_interest_stock_symbol_settlement_date_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.short_interest
    ADD CONSTRAINT short_interest_stock_symbol_settlement_date_key UNIQUE (stock_symbol, settlement_date);


--
-- Name: short_volume short_volume_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.short_volume
    ADD CONSTRAINT short_volume_pkey PRIMARY KEY (id);


--
-- Name: short_volume short_volume_stock_symbol_date_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.short_volume
    ADD CONSTRAINT short_volume_stock_symbol_date_key UNIQUE (stock_symbol, date);


--
-- Name: signal_readiness signal_readiness_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.signal_readiness
    ADD CONSTRAINT signal_readiness_pkey PRIMARY KEY (readiness_id);


--
-- Name: stock_news stock_news_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stock_news
    ADD CONSTRAINT stock_news_pkey PRIMARY KEY (news_id);


--
-- Name: swing_backtest_results swing_backtest_results_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.swing_backtest_results
    ADD CONSTRAINT swing_backtest_results_pkey PRIMARY KEY (backtest_id);


--
-- Name: swing_indicators swing_indicators_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.swing_indicators
    ADD CONSTRAINT swing_indicators_pkey PRIMARY KEY (id);


--
-- Name: swing_indicators swing_indicators_stock_symbol_timeframe_date_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.swing_indicators
    ADD CONSTRAINT swing_indicators_stock_symbol_timeframe_date_key UNIQUE (stock_symbol, timeframe, date);


--
-- Name: swing_trade_signals swing_trade_signals_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.swing_trade_signals
    ADD CONSTRAINT swing_trade_signals_pkey PRIMARY KEY (signal_id);


--
-- Name: swing_trades swing_trades_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.swing_trades
    ADD CONSTRAINT swing_trades_pkey PRIMARY KEY (trade_id);


--
-- Name: trading_activity trading_activity_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.trading_activity
    ADD CONSTRAINT trading_activity_pkey PRIMARY KEY (activity_id);


--
-- Name: users users_email_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (user_id);


--
-- Name: users users_username_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_username_key UNIQUE (username);


--
-- Name: watchlist_alerts watchlist_alerts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.watchlist_alerts
    ADD CONSTRAINT watchlist_alerts_pkey PRIMARY KEY (alert_id);


--
-- Name: watchlist_analytics watchlist_analytics_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.watchlist_analytics
    ADD CONSTRAINT watchlist_analytics_pkey PRIMARY KEY (id);


--
-- Name: watchlist_analytics watchlist_analytics_watchlist_id_date_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.watchlist_analytics
    ADD CONSTRAINT watchlist_analytics_watchlist_id_date_key UNIQUE (watchlist_id, date);


--
-- Name: watchlist_items watchlist_items_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.watchlist_items
    ADD CONSTRAINT watchlist_items_pkey PRIMARY KEY (item_id);


--
-- Name: watchlist_items watchlist_items_watchlist_id_stock_symbol_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.watchlist_items
    ADD CONSTRAINT watchlist_items_watchlist_id_stock_symbol_key UNIQUE (watchlist_id, stock_symbol);


--
-- Name: watchlist_performance watchlist_performance_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.watchlist_performance
    ADD CONSTRAINT watchlist_performance_pkey PRIMARY KEY (id);


--
-- Name: watchlist_performance watchlist_performance_watchlist_id_snapshot_date_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.watchlist_performance
    ADD CONSTRAINT watchlist_performance_watchlist_id_snapshot_date_key UNIQUE (watchlist_id, snapshot_date);


--
-- Name: watchlists watchlists_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.watchlists
    ADD CONSTRAINT watchlists_pkey PRIMARY KEY (watchlist_id);


--
-- Name: workflow_checkpoints workflow_checkpoints_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workflow_checkpoints
    ADD CONSTRAINT workflow_checkpoints_pkey PRIMARY KEY (checkpoint_id);


--
-- Name: workflow_dlq workflow_dlq_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workflow_dlq
    ADD CONSTRAINT workflow_dlq_pkey PRIMARY KEY (dlq_id);


--
-- Name: workflow_executions workflow_executions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workflow_executions
    ADD CONSTRAINT workflow_executions_pkey PRIMARY KEY (workflow_id);


--
-- Name: workflow_gate_results workflow_gate_results_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workflow_gate_results
    ADD CONSTRAINT workflow_gate_results_pkey PRIMARY KEY (gate_result_id);


--
-- Name: workflow_stage_executions workflow_stage_executions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workflow_stage_executions
    ADD CONSTRAINT workflow_stage_executions_pkey PRIMARY KEY (stage_execution_id);


--
-- Name: workflow_symbol_states workflow_symbol_states_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workflow_symbol_states
    ADD CONSTRAINT workflow_symbol_states_pkey PRIMARY KEY (id);


--
-- Name: workflow_symbol_states workflow_symbol_states_workflow_id_symbol_stage_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workflow_symbol_states
    ADD CONSTRAINT workflow_symbol_states_workflow_id_symbol_stage_key UNIQUE (workflow_id, symbol, stage);


--
-- Name: idx_aggregated_indicators_symbol_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_aggregated_indicators_symbol_date ON public.aggregated_indicators USING btree (stock_symbol, date);


--
-- Name: idx_aggregated_indicators_volume; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_aggregated_indicators_volume ON public.aggregated_indicators USING btree (stock_symbol, date DESC, volume);


--
-- Name: idx_alert_notifications_alert_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_alert_notifications_alert_id ON public.alert_notifications USING btree (alert_id);


--
-- Name: idx_alert_notifications_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_alert_notifications_created_at ON public.alert_notifications USING btree (created_at DESC);


--
-- Name: idx_alert_notifications_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_alert_notifications_status ON public.alert_notifications USING btree (status);


--
-- Name: idx_alert_notifications_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_alert_notifications_user_id ON public.alert_notifications USING btree (user_id);


--
-- Name: idx_alerts_enabled; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_alerts_enabled ON public.alerts USING btree (enabled);


--
-- Name: idx_alerts_portfolio_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_alerts_portfolio_id ON public.alerts USING btree (portfolio_id);


--
-- Name: idx_alerts_stock_symbol; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_alerts_stock_symbol ON public.alerts USING btree (stock_symbol);


--
-- Name: idx_alerts_type_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_alerts_type_id ON public.alerts USING btree (alert_type_id);


--
-- Name: idx_alerts_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_alerts_user_id ON public.alerts USING btree (user_id);


--
-- Name: idx_analyst_consensus_symbol; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_analyst_consensus_symbol ON public.analyst_consensus USING btree (stock_symbol);


--
-- Name: idx_analyst_ratings_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_analyst_ratings_date ON public.analyst_ratings USING btree (rating_date DESC);


--
-- Name: idx_analyst_ratings_symbol; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_analyst_ratings_symbol ON public.analyst_ratings USING btree (stock_symbol);


--
-- Name: idx_balance_sheets_fiscal; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_balance_sheets_fiscal ON public.balance_sheets USING btree (stock_symbol, fiscal_year DESC, fiscal_quarter DESC);


--
-- Name: idx_balance_sheets_symbol_period; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_balance_sheets_symbol_period ON public.balance_sheets USING btree (stock_symbol, period_end DESC);


--
-- Name: idx_blog_drafts_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_blog_drafts_status ON public.blog_drafts USING btree (status, generated_at DESC);


--
-- Name: idx_blog_drafts_topic; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_blog_drafts_topic ON public.blog_drafts USING btree (topic_id);


--
-- Name: idx_blog_drafts_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_blog_drafts_user ON public.blog_drafts USING btree (user_id);


--
-- Name: idx_blog_generation_audit_correlation; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_blog_generation_audit_correlation ON public.blog_generation_audit USING btree (correlation_id);


--
-- Name: idx_blog_generation_audit_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_blog_generation_audit_created ON public.blog_generation_audit USING btree (created_at DESC);


--
-- Name: idx_blog_generation_audit_draft; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_blog_generation_audit_draft ON public.blog_generation_audit USING btree (draft_id);


--
-- Name: idx_blog_generation_audit_parent; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_blog_generation_audit_parent ON public.blog_generation_audit USING btree (parent_audit_id);


--
-- Name: idx_blog_generation_audit_retry; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_blog_generation_audit_retry ON public.blog_generation_audit USING btree (can_retry, status, retry_count);


--
-- Name: idx_blog_generation_audit_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_blog_generation_audit_status ON public.blog_generation_audit USING btree (status, stage);


--
-- Name: idx_blog_generation_audit_topic; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_blog_generation_audit_topic ON public.blog_generation_audit USING btree (topic_id);


--
-- Name: idx_blog_generation_audit_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_blog_generation_audit_user ON public.blog_generation_audit USING btree (user_id);


--
-- Name: idx_blog_generation_log_action; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_blog_generation_log_action ON public.blog_generation_log USING btree (action, created_at DESC);


--
-- Name: idx_blog_generation_log_audit; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_blog_generation_log_audit ON public.blog_generation_log USING btree (audit_id);


--
-- Name: idx_blog_generation_log_topic; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_blog_generation_log_topic ON public.blog_generation_log USING btree (topic_id);


--
-- Name: idx_blog_generation_log_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_blog_generation_log_user ON public.blog_generation_log USING btree (user_id);


--
-- Name: idx_blog_published_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_blog_published_date ON public.blog_published USING btree (published_at DESC);


--
-- Name: idx_blog_published_symbol; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_blog_published_symbol ON public.blog_published USING btree (symbol);


--
-- Name: idx_blog_published_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_blog_published_user ON public.blog_published USING btree (user_id);


--
-- Name: idx_blog_publishing_config_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_blog_publishing_config_user ON public.blog_publishing_config USING btree (user_id);


--
-- Name: idx_blog_topics_score; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_blog_topics_score ON public.blog_topics USING btree (score DESC);


--
-- Name: idx_blog_topics_symbol; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_blog_topics_symbol ON public.blog_topics USING btree (symbol);


--
-- Name: idx_blog_topics_urgency; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_blog_topics_urgency ON public.blog_topics USING btree (urgency, created_at DESC);


--
-- Name: idx_blog_topics_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_blog_topics_user ON public.blog_topics USING btree (user_id);


--
-- Name: idx_cash_flow_fiscal; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cash_flow_fiscal ON public.cash_flow_statements USING btree (stock_symbol, fiscal_year DESC, fiscal_quarter DESC);


--
-- Name: idx_cash_flow_symbol_period; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cash_flow_symbol_period ON public.cash_flow_statements USING btree (stock_symbol, period_end DESC);


--
-- Name: idx_checkpoint_workflow; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_checkpoint_workflow ON public.workflow_checkpoints USING btree (workflow_id, "timestamp" DESC);


--
-- Name: idx_dlq_symbol; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_dlq_symbol ON public.workflow_dlq USING btree (symbol, stage);


--
-- Name: idx_dlq_unresolved; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_dlq_unresolved ON public.workflow_dlq USING btree (resolved, created_at DESC);


--
-- Name: idx_earnings_symbol_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_earnings_symbol_date ON public.earnings_data USING btree (stock_symbol, earnings_date DESC);


--
-- Name: idx_enhanced_fundamentals_symbol_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_enhanced_fundamentals_symbol_date ON public.enhanced_fundamentals USING btree (stock_symbol, as_of_date DESC);


--
-- Name: idx_fetch_audit_success; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_fetch_audit_success ON public.data_fetch_audit USING btree (success, fetch_timestamp DESC);


--
-- Name: idx_fetch_audit_symbol; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_fetch_audit_symbol ON public.data_fetch_audit USING btree (symbol, fetch_timestamp DESC);


--
-- Name: idx_fetch_audit_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_fetch_audit_type ON public.data_fetch_audit USING btree (fetch_type, fetch_timestamp DESC);


--
-- Name: idx_financial_ratios_fiscal; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_financial_ratios_fiscal ON public.financial_ratios USING btree (stock_symbol, fiscal_year DESC, fiscal_quarter DESC);


--
-- Name: idx_financial_ratios_symbol_period; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_financial_ratios_symbol_period ON public.financial_ratios USING btree (stock_symbol, period_end DESC);


--
-- Name: idx_gate_workflow; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_gate_workflow ON public.workflow_gate_results USING btree (workflow_id, stage, symbol);


--
-- Name: idx_holdings_closed; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_holdings_closed ON public.holdings USING btree (portfolio_id, is_closed);


--
-- Name: idx_holdings_current_price; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_holdings_current_price ON public.holdings USING btree (portfolio_id, current_price);


--
-- Name: idx_holdings_portfolio_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_holdings_portfolio_id ON public.holdings USING btree (portfolio_id);


--
-- Name: idx_holdings_sector; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_holdings_sector ON public.holdings USING btree (portfolio_id, sector);


--
-- Name: idx_holdings_symbol; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_holdings_symbol ON public.holdings USING btree (stock_symbol);


--
-- Name: idx_holdings_target_price; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_holdings_target_price ON public.holdings USING btree (portfolio_id, target_price);


--
-- Name: idx_holdings_unrealized_gain; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_holdings_unrealized_gain ON public.holdings USING btree (portfolio_id, unrealized_gain_loss);


--
-- Name: idx_income_statements_fiscal; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_income_statements_fiscal ON public.income_statements USING btree (stock_symbol, fiscal_year DESC, fiscal_quarter DESC);


--
-- Name: idx_income_statements_symbol_period; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_income_statements_symbol_period ON public.income_statements USING btree (stock_symbol, period_end DESC);


--
-- Name: idx_indicators_ema21; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_indicators_ema21 ON public.aggregated_indicators USING btree (stock_symbol, date) WHERE (ema21 IS NOT NULL);


--
-- Name: idx_indicators_ema9; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_indicators_ema9 ON public.aggregated_indicators USING btree (stock_symbol, date) WHERE (ema9 IS NOT NULL);


--
-- Name: idx_indicators_symbol_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_indicators_symbol_date ON public.aggregated_indicators USING btree (stock_symbol, date DESC);


--
-- Name: idx_industry_peers_symbol; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_industry_peers_symbol ON public.industry_peers USING btree (stock_symbol);


--
-- Name: idx_live_prices_symbol_timestamp; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_live_prices_symbol_timestamp ON public.live_prices USING btree (stock_symbol, "timestamp" DESC);


--
-- Name: idx_llm_reports_portfolio_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_llm_reports_portfolio_id ON public.llm_generated_reports USING btree (portfolio_id);


--
-- Name: idx_llm_reports_symbol; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_llm_reports_symbol ON public.llm_generated_reports USING btree (stock_symbol);


--
-- Name: idx_market_movers_period; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_market_movers_period ON public.market_movers USING btree (period, "timestamp" DESC);


--
-- Name: idx_market_movers_symbol; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_market_movers_symbol ON public.market_movers USING btree (stock_symbol);


--
-- Name: idx_market_overview_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_market_overview_date ON public.market_overview USING btree (date DESC);


--
-- Name: idx_market_trends_category; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_market_trends_category ON public.market_trends USING btree (category);


--
-- Name: idx_market_trends_date_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_market_trends_date_type ON public.market_trends USING btree (date DESC, trend_type);


--
-- Name: idx_mtf_symbol_timeframe; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_mtf_symbol_timeframe ON public.multi_timeframe_data USING btree (stock_symbol, timeframe, date DESC);


--
-- Name: idx_news_symbol_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_news_symbol_date ON public.stock_news USING btree (stock_symbol, published_date DESC);


--
-- Name: idx_notification_channels_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_notification_channels_type ON public.notification_channels USING btree (channel_type);


--
-- Name: idx_notification_channels_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_notification_channels_user_id ON public.notification_channels USING btree (user_id);


--
-- Name: idx_portfolio_performance_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_portfolio_performance_date ON public.portfolio_performance USING btree (portfolio_id, snapshot_date DESC);


--
-- Name: idx_portfolio_signals_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_portfolio_signals_date ON public.portfolio_signals USING btree (date);


--
-- Name: idx_portfolio_signals_portfolio_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_portfolio_signals_portfolio_id ON public.portfolio_signals USING btree (portfolio_id);


--
-- Name: idx_portfolio_signals_symbol; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_portfolio_signals_symbol ON public.portfolio_signals USING btree (stock_symbol);


--
-- Name: idx_portfolios_archived; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_portfolios_archived ON public.portfolios USING btree (user_id, is_archived);


--
-- Name: idx_portfolios_risk_tolerance; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_portfolios_risk_tolerance ON public.portfolios USING btree (risk_tolerance);


--
-- Name: idx_portfolios_strategy; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_portfolios_strategy ON public.portfolios USING btree (strategy_name);


--
-- Name: idx_portfolios_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_portfolios_type ON public.portfolios USING btree (portfolio_type);


--
-- Name: idx_portfolios_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_portfolios_user_id ON public.portfolios USING btree (user_id);


--
-- Name: idx_raw_market_data_symbol_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_raw_market_data_symbol_date ON public.raw_market_data USING btree (stock_symbol, date);


--
-- Name: idx_raw_market_symbol_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_raw_market_symbol_date ON public.raw_market_data USING btree (stock_symbol, date DESC);


--
-- Name: idx_refresh_tracking_symbol_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_refresh_tracking_symbol_type ON public.data_refresh_tracking USING btree (stock_symbol, data_type);


--
-- Name: idx_risk_categories_symbol_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_risk_categories_symbol_date ON public.risk_categories USING btree (stock_symbol, filing_date DESC);


--
-- Name: idx_risk_factors_symbol_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_risk_factors_symbol_date ON public.risk_factors USING btree (stock_symbol, filing_date DESC);


--
-- Name: idx_saved_screeners_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_saved_screeners_user ON public.saved_screeners USING btree (user_id);


--
-- Name: idx_screener_below_sma200; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_screener_below_sma200 ON public.aggregated_indicators USING btree (price_below_sma200, date DESC);


--
-- Name: idx_screener_below_sma50; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_screener_below_sma50 ON public.aggregated_indicators USING btree (price_below_sma50, date DESC);


--
-- Name: idx_screener_best_practice_buy; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_screener_best_practice_buy ON public.aggregated_indicators USING btree (price_above_sma200, sma50_above_sma200, ema20_above_ema50, macd_above_signal, rsi_zone, volume_above_average, date DESC);


--
-- Name: idx_screener_composite; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_screener_composite ON public.aggregated_indicators USING btree (has_good_fundamentals, price_below_sma50, price_below_sma200, is_growth_stock, date DESC);


--
-- Name: idx_screener_ema20_above_50; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_screener_ema20_above_50 ON public.aggregated_indicators USING btree (ema20_above_ema50, date DESC);


--
-- Name: idx_screener_exponential_growth; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_screener_exponential_growth ON public.aggregated_indicators USING btree (is_exponential_growth, date DESC);


--
-- Name: idx_screener_financial_health; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_screener_financial_health ON public.enhanced_fundamentals USING btree (debt_to_equity, current_ratio, quick_ratio, as_of_date DESC);


--
-- Name: idx_screener_fundamental_score; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_screener_fundamental_score ON public.aggregated_indicators USING btree (fundamental_score DESC, date DESC);


--
-- Name: idx_screener_golden_cross; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_screener_golden_cross ON public.aggregated_indicators USING btree (sma50_above_sma200, date DESC);


--
-- Name: idx_screener_good_fundamentals; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_screener_good_fundamentals ON public.aggregated_indicators USING btree (has_good_fundamentals, date DESC);


--
-- Name: idx_screener_growth; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_screener_growth ON public.aggregated_indicators USING btree (is_growth_stock, date DESC);


--
-- Name: idx_screener_macd_bullish; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_screener_macd_bullish ON public.aggregated_indicators USING btree (macd_above_signal, macd_histogram_positive, date DESC);


--
-- Name: idx_screener_price_above_200; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_screener_price_above_200 ON public.aggregated_indicators USING btree (price_above_sma200, date DESC);


--
-- Name: idx_screener_profitability; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_screener_profitability ON public.enhanced_fundamentals USING btree (profit_margin, roe, roa, as_of_date DESC);


--
-- Name: idx_screener_rsi_zone; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_screener_rsi_zone ON public.aggregated_indicators USING btree (rsi_zone, date DESC);


--
-- Name: idx_screener_short_interest; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_screener_short_interest ON public.enhanced_fundamentals USING btree (short_interest, days_to_cover, short_volume_ratio, as_of_date DESC);


--
-- Name: idx_screener_valuation; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_screener_valuation ON public.enhanced_fundamentals USING btree (pe_ratio, price_to_book, peg_ratio, as_of_date DESC);


--
-- Name: idx_screener_volume_confirmed; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_screener_volume_confirmed ON public.aggregated_indicators USING btree (volume_above_average, date DESC);


--
-- Name: idx_sector_performance_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_sector_performance_date ON public.sector_performance USING btree (date DESC);


--
-- Name: idx_sector_performance_sector; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_sector_performance_sector ON public.sector_performance USING btree (sector);


--
-- Name: idx_share_float_symbol_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_share_float_symbol_date ON public.share_float USING btree (stock_symbol, date DESC);


--
-- Name: idx_short_interest_symbol_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_short_interest_symbol_date ON public.short_interest USING btree (stock_symbol, settlement_date DESC);


--
-- Name: idx_short_volume_symbol_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_short_volume_symbol_date ON public.short_volume USING btree (stock_symbol, date DESC);


--
-- Name: idx_signal_readiness_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_signal_readiness_status ON public.signal_readiness USING btree (readiness_status, readiness_timestamp DESC);


--
-- Name: idx_signal_readiness_symbol; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_signal_readiness_symbol ON public.signal_readiness USING btree (symbol, readiness_timestamp DESC);


--
-- Name: idx_signal_readiness_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_signal_readiness_type ON public.signal_readiness USING btree (signal_type, readiness_timestamp DESC);


--
-- Name: idx_stage_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_stage_status ON public.workflow_stage_executions USING btree (status);


--
-- Name: idx_stage_workflow; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_stage_workflow ON public.workflow_stage_executions USING btree (workflow_id, stage_name);


--
-- Name: idx_stock_news_symbol_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_stock_news_symbol_date ON public.stock_news USING btree (stock_symbol, published_date DESC);


--
-- Name: idx_swing_backtest_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_swing_backtest_user ON public.swing_backtest_results USING btree (user_id, created_at DESC);


--
-- Name: idx_swing_indicators_symbol; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_swing_indicators_symbol ON public.swing_indicators USING btree (stock_symbol, timeframe, date DESC);


--
-- Name: idx_swing_signals_symbol; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_swing_signals_symbol ON public.swing_trade_signals USING btree (stock_symbol, signal_date DESC);


--
-- Name: idx_swing_signals_trade; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_swing_signals_trade ON public.swing_trade_signals USING btree (trade_id);


--
-- Name: idx_swing_signals_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_swing_signals_user ON public.swing_trade_signals USING btree (user_id, signal_date DESC);


--
-- Name: idx_swing_trades_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_swing_trades_status ON public.swing_trades USING btree (status, entry_date DESC);


--
-- Name: idx_swing_trades_symbol; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_swing_trades_symbol ON public.swing_trades USING btree (stock_symbol, status);


--
-- Name: idx_swing_trades_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_swing_trades_user ON public.swing_trades USING btree (user_id, status);


--
-- Name: idx_symbol_stage; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_symbol_stage ON public.workflow_symbol_states USING btree (symbol, stage, status);


--
-- Name: idx_symbol_workflow; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_symbol_workflow ON public.workflow_symbol_states USING btree (workflow_id, symbol);


--
-- Name: idx_trading_activity_portfolio; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_trading_activity_portfolio ON public.trading_activity USING btree (portfolio_id, created_at DESC);


--
-- Name: idx_trading_activity_symbol; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_trading_activity_symbol ON public.trading_activity USING btree (stock_symbol, created_at DESC);


--
-- Name: idx_trading_activity_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_trading_activity_type ON public.trading_activity USING btree (activity_type, created_at DESC);


--
-- Name: idx_trading_activity_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_trading_activity_user ON public.trading_activity USING btree (user_id, created_at DESC);


--
-- Name: idx_users_strategy; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_users_strategy ON public.users USING btree (preferred_strategy);


--
-- Name: idx_users_subscription_level; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_users_subscription_level ON public.users USING btree (subscription_level);


--
-- Name: idx_validation_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_validation_status ON public.data_validation_reports USING btree (overall_status);


--
-- Name: idx_validation_symbol_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_validation_symbol_type ON public.data_validation_reports USING btree (symbol, data_type);


--
-- Name: idx_validation_timestamp; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_validation_timestamp ON public.data_validation_reports USING btree (validation_timestamp DESC);


--
-- Name: idx_watchlist_alerts_enabled; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_watchlist_alerts_enabled ON public.watchlist_alerts USING btree (watchlist_id, enabled);


--
-- Name: idx_watchlist_alerts_watchlist_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_watchlist_alerts_watchlist_id ON public.watchlist_alerts USING btree (watchlist_id);


--
-- Name: idx_watchlist_analytics_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_watchlist_analytics_date ON public.watchlist_analytics USING btree (watchlist_id, date DESC);


--
-- Name: idx_watchlist_analytics_watchlist_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_watchlist_analytics_watchlist_id ON public.watchlist_analytics USING btree (watchlist_id);


--
-- Name: idx_watchlist_items_analyst_rating; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_watchlist_items_analyst_rating ON public.watchlist_items USING btree (watchlist_id, analyst_rating);


--
-- Name: idx_watchlist_items_earnings_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_watchlist_items_earnings_date ON public.watchlist_items USING btree (watchlist_id, earnings_date);


--
-- Name: idx_watchlist_items_priority; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_watchlist_items_priority ON public.watchlist_items USING btree (watchlist_id, priority DESC);


--
-- Name: idx_watchlist_items_sector; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_watchlist_items_sector ON public.watchlist_items USING btree (watchlist_id, sector);


--
-- Name: idx_watchlist_items_symbol; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_watchlist_items_symbol ON public.watchlist_items USING btree (stock_symbol);


--
-- Name: idx_watchlist_items_target_price; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_watchlist_items_target_price ON public.watchlist_items USING btree (watchlist_id, target_price);


--
-- Name: idx_watchlist_items_watchlist_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_watchlist_items_watchlist_id ON public.watchlist_items USING btree (watchlist_id);


--
-- Name: idx_watchlist_performance_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_watchlist_performance_date ON public.watchlist_performance USING btree (watchlist_id, snapshot_date DESC);


--
-- Name: idx_watchlists_archived; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_watchlists_archived ON public.watchlists USING btree (user_id, is_archived);


--
-- Name: idx_watchlists_default; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_watchlists_default ON public.watchlists USING btree (user_id, is_default);


--
-- Name: idx_watchlists_sort_order; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_watchlists_sort_order ON public.watchlists USING btree (user_id, sort_order);


--
-- Name: idx_watchlists_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_watchlists_user_id ON public.watchlists USING btree (user_id);


--
-- Name: idx_workflow_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_workflow_created ON public.workflow_executions USING btree (created_at DESC);


--
-- Name: idx_workflow_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_workflow_status ON public.workflow_executions USING btree (status);


--
-- Name: idx_workflow_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_workflow_type ON public.workflow_executions USING btree (workflow_type);


--
-- Name: alert_notifications alert_notifications_alert_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alert_notifications
    ADD CONSTRAINT alert_notifications_alert_id_fkey FOREIGN KEY (alert_id) REFERENCES public.alerts(alert_id) ON DELETE CASCADE;


--
-- Name: alert_notifications alert_notifications_alert_type_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alert_notifications
    ADD CONSTRAINT alert_notifications_alert_type_id_fkey FOREIGN KEY (alert_type_id) REFERENCES public.alert_types(alert_type_id);


--
-- Name: alert_notifications alert_notifications_portfolio_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alert_notifications
    ADD CONSTRAINT alert_notifications_portfolio_id_fkey FOREIGN KEY (portfolio_id) REFERENCES public.portfolios(portfolio_id) ON DELETE SET NULL;


--
-- Name: alert_notifications alert_notifications_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alert_notifications
    ADD CONSTRAINT alert_notifications_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE CASCADE;


--
-- Name: alerts alerts_alert_type_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alerts
    ADD CONSTRAINT alerts_alert_type_id_fkey FOREIGN KEY (alert_type_id) REFERENCES public.alert_types(alert_type_id);


--
-- Name: alerts alerts_portfolio_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alerts
    ADD CONSTRAINT alerts_portfolio_id_fkey FOREIGN KEY (portfolio_id) REFERENCES public.portfolios(portfolio_id) ON DELETE CASCADE;


--
-- Name: alerts alerts_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alerts
    ADD CONSTRAINT alerts_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE CASCADE;


--
-- Name: blog_drafts blog_drafts_topic_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.blog_drafts
    ADD CONSTRAINT blog_drafts_topic_id_fkey FOREIGN KEY (topic_id) REFERENCES public.blog_topics(topic_id) ON DELETE CASCADE;


--
-- Name: blog_drafts blog_drafts_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.blog_drafts
    ADD CONSTRAINT blog_drafts_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE CASCADE;


--
-- Name: blog_generation_audit blog_generation_audit_draft_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.blog_generation_audit
    ADD CONSTRAINT blog_generation_audit_draft_id_fkey FOREIGN KEY (draft_id) REFERENCES public.blog_drafts(draft_id) ON DELETE SET NULL;


--
-- Name: blog_generation_audit blog_generation_audit_parent_audit_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.blog_generation_audit
    ADD CONSTRAINT blog_generation_audit_parent_audit_id_fkey FOREIGN KEY (parent_audit_id) REFERENCES public.blog_generation_audit(audit_id) ON DELETE SET NULL;


--
-- Name: blog_generation_audit blog_generation_audit_topic_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.blog_generation_audit
    ADD CONSTRAINT blog_generation_audit_topic_id_fkey FOREIGN KEY (topic_id) REFERENCES public.blog_topics(topic_id) ON DELETE SET NULL;


--
-- Name: blog_generation_audit blog_generation_audit_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.blog_generation_audit
    ADD CONSTRAINT blog_generation_audit_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE SET NULL;


--
-- Name: blog_generation_log blog_generation_log_audit_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.blog_generation_log
    ADD CONSTRAINT blog_generation_log_audit_id_fkey FOREIGN KEY (audit_id) REFERENCES public.blog_generation_audit(audit_id) ON DELETE CASCADE;


--
-- Name: blog_generation_log blog_generation_log_draft_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.blog_generation_log
    ADD CONSTRAINT blog_generation_log_draft_id_fkey FOREIGN KEY (draft_id) REFERENCES public.blog_drafts(draft_id) ON DELETE SET NULL;


--
-- Name: blog_generation_log blog_generation_log_topic_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.blog_generation_log
    ADD CONSTRAINT blog_generation_log_topic_id_fkey FOREIGN KEY (topic_id) REFERENCES public.blog_topics(topic_id) ON DELETE SET NULL;


--
-- Name: blog_generation_log blog_generation_log_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.blog_generation_log
    ADD CONSTRAINT blog_generation_log_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE SET NULL;


--
-- Name: blog_published blog_published_draft_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.blog_published
    ADD CONSTRAINT blog_published_draft_id_fkey FOREIGN KEY (draft_id) REFERENCES public.blog_drafts(draft_id) ON DELETE CASCADE;


--
-- Name: blog_published blog_published_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.blog_published
    ADD CONSTRAINT blog_published_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE CASCADE;


--
-- Name: blog_publishing_config blog_publishing_config_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.blog_publishing_config
    ADD CONSTRAINT blog_publishing_config_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE CASCADE;


--
-- Name: blog_topics blog_topics_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.blog_topics
    ADD CONSTRAINT blog_topics_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE CASCADE;


--
-- Name: data_fetch_audit data_fetch_audit_validation_report_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.data_fetch_audit
    ADD CONSTRAINT data_fetch_audit_validation_report_id_fkey FOREIGN KEY (validation_report_id) REFERENCES public.data_validation_reports(report_id);


--
-- Name: holdings holdings_portfolio_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.holdings
    ADD CONSTRAINT holdings_portfolio_id_fkey FOREIGN KEY (portfolio_id) REFERENCES public.portfolios(portfolio_id) ON DELETE CASCADE;


--
-- Name: llm_generated_reports llm_generated_reports_portfolio_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.llm_generated_reports
    ADD CONSTRAINT llm_generated_reports_portfolio_id_fkey FOREIGN KEY (portfolio_id) REFERENCES public.portfolios(portfolio_id) ON DELETE SET NULL;


--
-- Name: notification_channels notification_channels_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notification_channels
    ADD CONSTRAINT notification_channels_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE CASCADE;


--
-- Name: portfolio_performance portfolio_performance_portfolio_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.portfolio_performance
    ADD CONSTRAINT portfolio_performance_portfolio_id_fkey FOREIGN KEY (portfolio_id) REFERENCES public.portfolios(portfolio_id) ON DELETE CASCADE;


--
-- Name: portfolio_signals portfolio_signals_portfolio_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.portfolio_signals
    ADD CONSTRAINT portfolio_signals_portfolio_id_fkey FOREIGN KEY (portfolio_id) REFERENCES public.portfolios(portfolio_id) ON DELETE CASCADE;


--
-- Name: portfolios portfolios_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.portfolios
    ADD CONSTRAINT portfolios_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE CASCADE;


--
-- Name: saved_screeners saved_screeners_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.saved_screeners
    ADD CONSTRAINT saved_screeners_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE CASCADE;


--
-- Name: signal_readiness signal_readiness_validation_report_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.signal_readiness
    ADD CONSTRAINT signal_readiness_validation_report_id_fkey FOREIGN KEY (validation_report_id) REFERENCES public.data_validation_reports(report_id);


--
-- Name: swing_backtest_results swing_backtest_results_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.swing_backtest_results
    ADD CONSTRAINT swing_backtest_results_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE CASCADE;


--
-- Name: swing_trade_signals swing_trade_signals_trade_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.swing_trade_signals
    ADD CONSTRAINT swing_trade_signals_trade_id_fkey FOREIGN KEY (trade_id) REFERENCES public.swing_trades(trade_id) ON DELETE CASCADE;


--
-- Name: swing_trade_signals swing_trade_signals_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.swing_trade_signals
    ADD CONSTRAINT swing_trade_signals_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE CASCADE;


--
-- Name: swing_trades swing_trades_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.swing_trades
    ADD CONSTRAINT swing_trades_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE CASCADE;


--
-- Name: trading_activity trading_activity_portfolio_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.trading_activity
    ADD CONSTRAINT trading_activity_portfolio_id_fkey FOREIGN KEY (portfolio_id) REFERENCES public.portfolios(portfolio_id) ON DELETE SET NULL;


--
-- Name: trading_activity trading_activity_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.trading_activity
    ADD CONSTRAINT trading_activity_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE CASCADE;


--
-- Name: trading_activity trading_activity_watchlist_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.trading_activity
    ADD CONSTRAINT trading_activity_watchlist_id_fkey FOREIGN KEY (watchlist_id) REFERENCES public.watchlists(watchlist_id) ON DELETE SET NULL;


--
-- Name: watchlist_alerts watchlist_alerts_watchlist_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.watchlist_alerts
    ADD CONSTRAINT watchlist_alerts_watchlist_id_fkey FOREIGN KEY (watchlist_id) REFERENCES public.watchlists(watchlist_id) ON DELETE CASCADE;


--
-- Name: watchlist_analytics watchlist_analytics_watchlist_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.watchlist_analytics
    ADD CONSTRAINT watchlist_analytics_watchlist_id_fkey FOREIGN KEY (watchlist_id) REFERENCES public.watchlists(watchlist_id) ON DELETE CASCADE;


--
-- Name: watchlist_items watchlist_items_watchlist_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.watchlist_items
    ADD CONSTRAINT watchlist_items_watchlist_id_fkey FOREIGN KEY (watchlist_id) REFERENCES public.watchlists(watchlist_id) ON DELETE CASCADE;


--
-- Name: watchlist_performance watchlist_performance_watchlist_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.watchlist_performance
    ADD CONSTRAINT watchlist_performance_watchlist_id_fkey FOREIGN KEY (watchlist_id) REFERENCES public.watchlists(watchlist_id) ON DELETE CASCADE;


--
-- Name: watchlists watchlists_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.watchlists
    ADD CONSTRAINT watchlists_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE CASCADE;


--
-- Name: workflow_checkpoints workflow_checkpoints_workflow_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workflow_checkpoints
    ADD CONSTRAINT workflow_checkpoints_workflow_id_fkey FOREIGN KEY (workflow_id) REFERENCES public.workflow_executions(workflow_id);


--
-- Name: workflow_dlq workflow_dlq_workflow_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workflow_dlq
    ADD CONSTRAINT workflow_dlq_workflow_id_fkey FOREIGN KEY (workflow_id) REFERENCES public.workflow_executions(workflow_id);


--
-- Name: workflow_gate_results workflow_gate_results_workflow_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workflow_gate_results
    ADD CONSTRAINT workflow_gate_results_workflow_id_fkey FOREIGN KEY (workflow_id) REFERENCES public.workflow_executions(workflow_id);


--
-- Name: workflow_stage_executions workflow_stage_executions_workflow_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workflow_stage_executions
    ADD CONSTRAINT workflow_stage_executions_workflow_id_fkey FOREIGN KEY (workflow_id) REFERENCES public.workflow_executions(workflow_id);


--
-- Name: workflow_symbol_states workflow_symbol_states_workflow_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workflow_symbol_states
    ADD CONSTRAINT workflow_symbol_states_workflow_id_fkey FOREIGN KEY (workflow_id) REFERENCES public.workflow_executions(workflow_id);


--
-- PostgreSQL database dump complete
--

\unrestrict mIYWcbz73bI83no7FaLO2qnbnjq2lgTEi7qjdQdNGCBY6Mh3Aa8FedmZHBD4ue2

