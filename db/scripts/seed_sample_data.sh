#!/bin/bash
# Seed database with sample data for testing

set -e

DB_PATH="${DB_PATH:-./db/trading.db}"

echo "🌱 Seeding sample data..."

sqlite3 "$DB_PATH" <<EOF
-- Insert sample users
INSERT OR IGNORE INTO users (user_id, username, email, password_hash, subscription_level)
VALUES 
    ('user1', 'john_doe', 'john@example.com', 'hashed_password_1', 'basic'),
    ('user2', 'jane_smith', 'jane@example.com', 'hashed_password_2', 'pro'),
    ('user3', 'bob_trader', 'bob@example.com', 'hashed_password_3', 'elite');

-- Insert sample portfolios
INSERT OR IGNORE INTO portfolios (portfolio_id, user_id, portfolio_name)
VALUES 
    ('portfolio1', 'user1', 'My First Portfolio'),
    ('portfolio2', 'user2', 'Growth Portfolio'),
    ('portfolio3', 'user3', 'Elite Trading Portfolio');

-- Insert sample holdings for portfolio1 (user1)
INSERT OR IGNORE INTO holdings (holding_id, portfolio_id, stock_symbol, quantity, avg_entry_price, position_type, strategy_tag, purchase_date)
VALUES 
    ('holding1', 'portfolio1', 'NVDA', 20, 450.00, 'long', NULL, date('now', '-30 days')),
    ('holding2', 'portfolio1', 'TSLA', 15, 250.00, 'long', NULL, date('now', '-28 days')),
    ('holding3', 'portfolio1', 'AVGO', 10, 1200.00, 'long', NULL, date('now', '-25 days')),
    ('holding4', 'portfolio1', 'MU', 30, 80.00, 'long', NULL, date('now', '-22 days')),
    ('holding5', 'portfolio1', 'PLTR', 50, 20.00, 'long', NULL, date('now', '-20 days')),
    ('holding6', 'portfolio1', 'GOOGL', 8, 140.00, 'long', NULL, date('now', '-18 days')),
    ('holding7', 'portfolio1', 'MSFT', 12, 380.00, 'long', NULL, date('now', '-15 days')),
    -- Additional holdings for other portfolios
    ('holding8', 'portfolio2', 'GOOGL', 8, 120.00, 'long', 'covered_call', date('now', '-15 days')),
    ('holding9', 'portfolio3', 'TSLA', 15, 200.00, 'long', 'protective_put', date('now', '-10 days'));

-- Note: Raw market data and indicators will be populated by the batch worker
-- This script only creates sample users, portfolios, and holdings

EOF

echo "✅ Sample data seeded successfully!"
echo ""
echo "Sample users created:"
echo "  - user1 (basic) - john@example.com"
echo "  - user2 (pro) - jane@example.com"
echo "  - user3 (elite) - bob@example.com"
echo ""
echo "Sample portfolios created:"
echo "  - portfolio1 (user1) - 7 stocks: NVDA, TSLA, AVGO, MU, PLTR, GOOGL, MSFT"
echo "  - portfolio2 (user2)"
echo "  - portfolio3 (user3)"

