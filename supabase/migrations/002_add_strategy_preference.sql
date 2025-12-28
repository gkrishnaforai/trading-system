-- Add strategy preference to users table
-- PostgreSQL/Supabase compatible

ALTER TABLE users ADD COLUMN IF NOT EXISTS preferred_strategy VARCHAR(50) DEFAULT 'technical' CHECK(preferred_strategy IN ('technical', 'hybrid_llm', 'custom'));

-- Add strategy preference to portfolios (allows per-portfolio strategy)
ALTER TABLE portfolios ADD COLUMN IF NOT EXISTS strategy_name VARCHAR(100) DEFAULT NULL;

-- Create index for strategy lookups
CREATE INDEX IF NOT EXISTS idx_users_strategy ON users(preferred_strategy);
CREATE INDEX IF NOT EXISTS idx_portfolios_strategy ON portfolios(strategy_name);

