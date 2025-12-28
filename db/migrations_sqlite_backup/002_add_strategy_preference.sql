-- Add strategy preference to users table
-- Allows users to select their preferred trading strategy

ALTER TABLE users ADD COLUMN preferred_strategy TEXT DEFAULT 'technical' CHECK(preferred_strategy IN ('technical', 'hybrid_llm', 'custom'));

-- Add strategy preference to portfolios (allows per-portfolio strategy)
ALTER TABLE portfolios ADD COLUMN strategy_name TEXT DEFAULT NULL;

-- Create index for strategy lookups
CREATE INDEX IF NOT EXISTS idx_users_strategy ON users(preferred_strategy);
CREATE INDEX IF NOT EXISTS idx_portfolios_strategy ON portfolios(strategy_name);

