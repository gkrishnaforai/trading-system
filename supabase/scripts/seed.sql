-- Seed data for Supabase/PostgreSQL
-- Sample users, portfolios, and holdings

-- Insert sample users
INSERT INTO users (user_id, username, email, password_hash, subscription_level)
VALUES 
    ('user1', 'john_doe', 'john@example.com', 'hashed_password_1', 'basic'),
    ('user2', 'jane_smith', 'jane@example.com', 'hashed_password_2', 'pro'),
    ('user3', 'bob_trader', 'bob@example.com', 'hashed_password_3', 'elite')
ON CONFLICT (user_id) DO NOTHING;

-- Insert sample portfolios
INSERT INTO portfolios (portfolio_id, user_id, portfolio_name)
VALUES 
    ('portfolio1', 'user1', 'My First Portfolio'),
    ('portfolio2', 'user2', 'Growth Portfolio'),
    ('portfolio3', 'user3', 'Elite Trading Portfolio')
ON CONFLICT (portfolio_id) DO NOTHING;

-- Insert sample holdings for portfolio1 (user1)
INSERT INTO holdings (holding_id, portfolio_id, stock_symbol, quantity, avg_entry_price, position_type, strategy_tag, purchase_date)
VALUES 
    ('holding1', 'portfolio1', 'NVDA', 20, 450.00, 'long', NULL, CURRENT_DATE - INTERVAL '30 days'),
    ('holding2', 'portfolio1', 'TSLA', 15, 250.00, 'long', NULL, CURRENT_DATE - INTERVAL '28 days'),
    ('holding3', 'portfolio1', 'AVGO', 10, 1200.00, 'long', NULL, CURRENT_DATE - INTERVAL '25 days'),
    ('holding4', 'portfolio1', 'MU', 30, 80.00, 'long', NULL, CURRENT_DATE - INTERVAL '22 days'),
    ('holding5', 'portfolio1', 'PLTR', 50, 20.00, 'long', NULL, CURRENT_DATE - INTERVAL '20 days'),
    ('holding6', 'portfolio1', 'GOOGL', 8, 140.00, 'long', NULL, CURRENT_DATE - INTERVAL '18 days'),
    ('holding7', 'portfolio1', 'MSFT', 12, 380.00, 'long', NULL, CURRENT_DATE - INTERVAL '15 days'),
    -- Additional holdings for other portfolios
    ('holding8', 'portfolio2', 'GOOGL', 8, 120.00, 'long', 'covered_call', CURRENT_DATE - INTERVAL '15 days'),
    ('holding9', 'portfolio3', 'TSLA', 15, 200.00, 'long', 'protective_put', CURRENT_DATE - INTERVAL '10 days')
ON CONFLICT (holding_id) DO NOTHING;

-- Note: Raw market data and indicators will be populated by the batch worker
-- This script only creates sample users, portfolios, and holdings

