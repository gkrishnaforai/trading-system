-- Migration 019: Comprehensive Financial Data Tables
-- Adds tables for all Massive.com financial data endpoints
-- Supports: Income statements, Balance sheets, Cash flow, Ratios, Short interest, Float, Risk factors
-- Designed for easy querying for alerts, blogs, and trading decisions

-- Income Statements (Quarterly and Annual)
-- Based on: https://massive.com/docs/rest/stocks/fundamentals/income-statements
CREATE TABLE IF NOT EXISTS income_statements (
    id BIGSERIAL PRIMARY KEY,
    stock_symbol TEXT NOT NULL,
    period_end DATE NOT NULL,
    filing_date DATE,
    fiscal_year INTEGER,
    fiscal_quarter INTEGER,
    timeframe TEXT CHECK(timeframe IN ('quarterly', 'annual')),
    
    -- Revenue
    revenues REAL,
    total_revenue REAL,
    cost_of_revenue REAL,
    gross_profit REAL,
    
    -- Operating Expenses
    operating_expenses REAL,
    research_and_development REAL,
    selling_general_and_administrative REAL,
    operating_income REAL,
    
    -- Non-operating
    interest_expense REAL,
    interest_income REAL,
    other_income_expense REAL,
    income_before_tax REAL,
    income_tax_expense REAL,
    
    -- Net Income
    net_income REAL,
    net_income_attributable_to_parent REAL,
    net_income_attributable_to_noncontrolling_interests REAL,
    net_income_per_share REAL,
    
    -- Shares
    weighted_average_shares_outstanding REAL,
    weighted_average_diluted_shares_outstanding REAL,
    
    -- Additional fields
    cik TEXT,
    tickers TEXT, -- JSON array
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(stock_symbol, period_end, timeframe)
);

-- Balance Sheets (Quarterly and Annual)
-- Based on: https://massive.com/docs/rest/stocks/fundamentals/balance-sheets
CREATE TABLE IF NOT EXISTS balance_sheets (
    id BIGSERIAL PRIMARY KEY,
    stock_symbol TEXT NOT NULL,
    period_end DATE NOT NULL,
    filing_date DATE,
    fiscal_year INTEGER,
    fiscal_quarter INTEGER,
    timeframe TEXT CHECK(timeframe IN ('quarterly', 'annual')),
    
    -- Current Assets
    cash_and_equivalents REAL,
    short_term_investments REAL,
    receivables REAL,
    inventories REAL,
    other_current_assets REAL,
    total_current_assets REAL,
    
    -- Non-Current Assets
    property_plant_equipment_net REAL,
    goodwill REAL,
    intangible_assets_net REAL,
    other_assets REAL,
    total_assets REAL,
    
    -- Current Liabilities
    accounts_payable REAL,
    debt_current REAL,
    deferred_revenue_current REAL,
    accrued_and_other_current_liabilities REAL,
    total_current_liabilities REAL,
    
    -- Non-Current Liabilities
    long_term_debt_and_capital_lease_obligations REAL,
    other_noncurrent_liabilities REAL,
    total_liabilities REAL,
    
    -- Equity
    common_stock REAL,
    preferred_stock REAL,
    additional_paid_in_capital REAL,
    retained_earnings_deficit REAL,
    accumulated_other_comprehensive_income REAL,
    treasury_stock REAL,
    other_equity REAL,
    noncontrolling_interest REAL,
    total_equity REAL,
    total_equity_attributable_to_parent REAL,
    total_liabilities_and_equity REAL,
    
    -- Additional fields
    shares_outstanding REAL,
    commitments_and_contingencies REAL,
    cik TEXT,
    tickers TEXT, -- JSON array
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(stock_symbol, period_end, timeframe)
);

-- Cash Flow Statements (Quarterly, Annual, TTM)
-- Based on: https://massive.com/docs/rest/stocks/fundamentals/cash-flow-statements
CREATE TABLE IF NOT EXISTS cash_flow_statements (
    id BIGSERIAL PRIMARY KEY,
    stock_symbol TEXT NOT NULL,
    period_end DATE NOT NULL,
    filing_date DATE,
    fiscal_year INTEGER,
    fiscal_quarter INTEGER,
    timeframe TEXT CHECK(timeframe IN ('quarterly', 'annual', 'trailing_twelve_months')),
    
    -- Operating Activities
    net_income REAL,
    depreciation_depletion_and_amortization REAL,
    change_in_other_operating_assets_and_liabilities_net REAL,
    other_operating_activities REAL,
    net_cash_from_operating_activities REAL,
    cash_from_operating_activities_continuing_operations REAL,
    net_cash_from_operating_activities_discontinued_operations REAL,
    
    -- Investing Activities
    purchase_of_property_plant_and_equipment REAL,
    sale_of_property_plant_and_equipment REAL,
    other_investing_activities REAL,
    net_cash_from_investing_activities REAL,
    net_cash_from_investing_activities_continuing_operations REAL,
    net_cash_from_investing_activities_discontinued_operations REAL,
    
    -- Financing Activities
    short_term_debt_issuances_repayments REAL,
    long_term_debt_issuances_repayments REAL,
    dividends REAL,
    other_financing_activities REAL,
    net_cash_from_financing_activities REAL,
    net_cash_from_financing_activities_continuing_operations REAL,
    net_cash_from_financing_activities_discontinued_operations REAL,
    
    -- Other
    effect_of_currency_exchange_rate REAL,
    other_cash_adjustments REAL,
    change_in_cash_and_equivalents REAL,
    income_loss_from_discontinued_operations REAL,
    noncontrolling_interests REAL,
    
    -- Additional fields
    cik TEXT,
    tickers TEXT, -- JSON array
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(stock_symbol, period_end, timeframe)
);

-- Financial Ratios (Pre-calculated for fast queries)
-- Based on: https://massive.com/docs/rest/stocks/fundamentals/ratios
CREATE TABLE IF NOT EXISTS financial_ratios (
    id BIGSERIAL PRIMARY KEY,
    stock_symbol TEXT NOT NULL,
    period_end DATE NOT NULL,
    fiscal_year INTEGER,
    fiscal_quarter INTEGER,
    timeframe TEXT CHECK(timeframe IN ('quarterly', 'annual', 'trailing_twelve_months')),
    
    -- Valuation Ratios
    price_to_earnings REAL,
    price_to_book REAL,
    price_to_sales REAL,
    price_to_free_cash_flow REAL,
    enterprise_value_to_ebitda REAL,
    enterprise_value_to_revenue REAL,
    
    -- Profitability Ratios
    gross_profit_margin REAL,
    operating_margin REAL,
    net_profit_margin REAL,
    return_on_equity REAL,
    return_on_assets REAL,
    return_on_invested_capital REAL,
    
    -- Efficiency Ratios
    asset_turnover REAL,
    inventory_turnover REAL,
    receivables_turnover REAL,
    
    -- Leverage Ratios
    debt_to_equity REAL,
    debt_to_assets REAL,
    equity_multiplier REAL,
    interest_coverage REAL,
    
    -- Liquidity Ratios
    current_ratio REAL,
    quick_ratio REAL,
    cash_ratio REAL,
    
    -- Growth Ratios
    revenue_growth REAL,
    earnings_growth REAL,
    eps_growth REAL,
    
    -- Per Share Metrics
    earnings_per_share REAL,
    book_value_per_share REAL,
    cash_per_share REAL,
    free_cash_flow_per_share REAL,
    
    -- Additional fields
    cik TEXT,
    tickers TEXT, -- JSON array
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(stock_symbol, period_end, timeframe)
);

-- Short Interest Data
-- Based on: https://massive.com/docs/rest/stocks/fundamentals/short-interest
CREATE TABLE IF NOT EXISTS short_interest (
    id BIGSERIAL PRIMARY KEY,
    stock_symbol TEXT NOT NULL,
    settlement_date DATE NOT NULL,
    short_interest REAL, -- Number of shares sold short
    average_volume REAL, -- Average daily volume
    days_to_cover REAL, -- Short interest / average volume
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(stock_symbol, settlement_date)
);

-- Short Volume Data
-- Based on: https://massive.com/docs/rest/stocks/fundamentals/short-volume
CREATE TABLE IF NOT EXISTS short_volume (
    id BIGSERIAL PRIMARY KEY,
    stock_symbol TEXT NOT NULL,
    date DATE NOT NULL,
    short_volume INTEGER, -- Number of shares sold short
    total_volume INTEGER, -- Total volume
    short_volume_ratio REAL, -- short_volume / total_volume
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(stock_symbol, date)
);

-- Float Data (Shares outstanding and float)
-- Based on: https://massive.com/docs/rest/stocks/fundamentals/float
CREATE TABLE IF NOT EXISTS share_float (
    id BIGSERIAL PRIMARY KEY,
    stock_symbol TEXT NOT NULL,
    date DATE NOT NULL,
    shares_outstanding REAL,
    float_shares REAL, -- Shares available for trading
    restricted_shares REAL,
    insider_shares REAL,
    institutional_shares REAL,
    float_percentage REAL, -- float_shares / shares_outstanding
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(stock_symbol, date)
);

-- Risk Factors (SEC filings)
-- Based on: https://massive.com/docs/rest/stocks/filings/risk-factors
CREATE TABLE IF NOT EXISTS risk_factors (
    id BIGSERIAL PRIMARY KEY,
    stock_symbol TEXT NOT NULL,
    filing_date DATE NOT NULL,
    period_end DATE,
    risk_factor_text TEXT NOT NULL, -- Full text of risk factor
    risk_category TEXT, -- Categorized risk type
    severity TEXT CHECK(severity IN ('low', 'medium', 'high', 'critical')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Risk Categories (Categorized risks for easy filtering)
-- Based on: https://massive.com/docs/rest/stocks/filings/risk-categories
CREATE TABLE IF NOT EXISTS risk_categories (
    id BIGSERIAL PRIMARY KEY,
    stock_symbol TEXT NOT NULL,
    filing_date DATE NOT NULL,
    category TEXT NOT NULL, -- e.g., 'market_risk', 'operational_risk', 'financial_risk', 'regulatory_risk'
    category_count INTEGER DEFAULT 1, -- Number of risk factors in this category
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(stock_symbol, filing_date, category)
);

-- Enhanced Fundamentals Table (Denormalized for fast queries)
-- Combines key metrics from all financial statements for easy access
CREATE TABLE IF NOT EXISTS enhanced_fundamentals (
    id BIGSERIAL PRIMARY KEY,
    stock_symbol TEXT NOT NULL,
    as_of_date DATE NOT NULL, -- Latest period_end from financial statements
    
    -- Valuation (from ratios or calculated)
    market_cap REAL,
    enterprise_value REAL,
    pe_ratio REAL,
    forward_pe REAL,
    price_to_book REAL,
    price_to_sales REAL,
    peg_ratio REAL,
    ev_to_ebitda REAL,
    
    -- Profitability (from income statements)
    revenue REAL,
    gross_profit REAL,
    operating_income REAL,
    net_income REAL,
    eps REAL,
    profit_margin REAL,
    operating_margin REAL,
    gross_margin REAL,
    
    -- Returns (from ratios)
    roe REAL, -- Return on Equity
    roa REAL, -- Return on Assets
    roic REAL, -- Return on Invested Capital
    
    -- Growth (calculated)
    revenue_growth REAL,
    earnings_growth REAL,
    eps_growth REAL,
    
    -- Financial Health (from balance sheets)
    total_assets REAL,
    total_liabilities REAL,
    total_equity REAL,
    debt_to_equity REAL,
    debt_to_assets REAL,
    current_ratio REAL,
    quick_ratio REAL,
    
    -- Cash Flow (from cash flow statements)
    operating_cash_flow REAL,
    free_cash_flow REAL,
    cash_and_equivalents REAL,
    
    -- Market Metrics (from float/short interest)
    shares_outstanding REAL,
    float_shares REAL,
    short_interest REAL,
    days_to_cover REAL,
    short_volume_ratio REAL,
    
    -- Dividends
    dividend_yield REAL,
    dividend_per_share REAL,
    dividend_payout_ratio REAL,
    
    -- Company Info
    sector TEXT,
    industry TEXT,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(stock_symbol, as_of_date)
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_income_statements_symbol_period ON income_statements(stock_symbol, period_end DESC);
CREATE INDEX IF NOT EXISTS idx_income_statements_fiscal ON income_statements(stock_symbol, fiscal_year DESC, fiscal_quarter DESC);
CREATE INDEX IF NOT EXISTS idx_balance_sheets_symbol_period ON balance_sheets(stock_symbol, period_end DESC);
CREATE INDEX IF NOT EXISTS idx_balance_sheets_fiscal ON balance_sheets(stock_symbol, fiscal_year DESC, fiscal_quarter DESC);
CREATE INDEX IF NOT EXISTS idx_cash_flow_symbol_period ON cash_flow_statements(stock_symbol, period_end DESC);
CREATE INDEX IF NOT EXISTS idx_cash_flow_fiscal ON cash_flow_statements(stock_symbol, fiscal_year DESC, fiscal_quarter DESC);
CREATE INDEX IF NOT EXISTS idx_financial_ratios_symbol_period ON financial_ratios(stock_symbol, period_end DESC);
CREATE INDEX IF NOT EXISTS idx_financial_ratios_fiscal ON financial_ratios(stock_symbol, fiscal_year DESC, fiscal_quarter DESC);
CREATE INDEX IF NOT EXISTS idx_short_interest_symbol_date ON short_interest(stock_symbol, settlement_date DESC);
CREATE INDEX IF NOT EXISTS idx_short_volume_symbol_date ON short_volume(stock_symbol, date DESC);
CREATE INDEX IF NOT EXISTS idx_share_float_symbol_date ON share_float(stock_symbol, date DESC);
CREATE INDEX IF NOT EXISTS idx_risk_factors_symbol_date ON risk_factors(stock_symbol, filing_date DESC);
CREATE INDEX IF NOT EXISTS idx_risk_categories_symbol_date ON risk_categories(stock_symbol, filing_date DESC);
CREATE INDEX IF NOT EXISTS idx_enhanced_fundamentals_symbol_date ON enhanced_fundamentals(stock_symbol, as_of_date DESC);

-- Composite indexes for common queries (alerts, blogs, screening)
CREATE INDEX IF NOT EXISTS idx_screener_valuation ON enhanced_fundamentals(pe_ratio, price_to_book, peg_ratio, as_of_date DESC);
CREATE INDEX IF NOT EXISTS idx_screener_profitability ON enhanced_fundamentals(profit_margin, roe, roa, as_of_date DESC);
CREATE INDEX IF NOT EXISTS idx_screener_growth ON enhanced_fundamentals(revenue_growth, earnings_growth, eps_growth, as_of_date DESC);
CREATE INDEX IF NOT EXISTS idx_screener_financial_health ON enhanced_fundamentals(debt_to_equity, current_ratio, quick_ratio, as_of_date DESC);
CREATE INDEX IF NOT EXISTS idx_screener_short_interest ON enhanced_fundamentals(short_interest, days_to_cover, short_volume_ratio, as_of_date DESC);

