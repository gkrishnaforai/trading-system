-- Market-level AI-capex regime — weighted consensus across approved
-- demand_evidence claims. One row per day; recomputed per FV run,
-- never driven by a single company's guidance.
CREATE TABLE IF NOT EXISTS market_ai_regime (
    as_of_date    DATE PRIMARY KEY,
    regime        TEXT NOT NULL,        -- accelerating | expanding |
                                        -- growth_moderating | flat |
                                        -- contracting | stress | unknown
    warning_score NUMERIC(5,1),         -- ai_cycle_warning 0-100
    groups        JSONB,                -- spending/orders/monetization/utilization/financing directions
    down_groups   JSONB,
    up_groups     JSONB,
    computed_by   TEXT NOT NULL DEFAULT 'fv_engine',
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_market_ai_regime_regime
    ON market_ai_regime(regime);
