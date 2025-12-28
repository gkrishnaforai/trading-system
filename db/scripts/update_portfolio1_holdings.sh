#!/bin/bash
# Update portfolio1 holdings with default stock list
# Use this if you've already seeded the database and want to update it

set -e

DB_PATH="${DB_PATH:-./db/trading.db}"

echo "🔄 Updating portfolio1 holdings with default stocks..."

sqlite3 "$DB_PATH" <<EOF
-- Delete existing holdings for portfolio1
DELETE FROM holdings WHERE portfolio_id = 'portfolio1';

-- Insert default stock list for portfolio1
INSERT INTO holdings (holding_id, portfolio_id, stock_symbol, quantity, avg_entry_price, position_type, strategy_tag, purchase_date)
VALUES 
    ('holding1', 'portfolio1', 'NVDA', 20, 450.00, 'long', NULL, date('now', '-30 days')),
    ('holding2', 'portfolio1', 'TSLA', 15, 250.00, 'long', NULL, date('now', '-28 days')),
    ('holding3', 'portfolio1', 'AVGO', 10, 1200.00, 'long', NULL, date('now', '-25 days')),
    ('holding4', 'portfolio1', 'MU', 30, 80.00, 'long', NULL, date('now', '-22 days')),
    ('holding5', 'portfolio1', 'PLTR', 50, 20.00, 'long', NULL, date('now', '-20 days')),
    ('holding6', 'portfolio1', 'GOOGL', 8, 140.00, 'long', NULL, date('now', '-18 days')),
    ('holding7', 'portfolio1', 'MSFT', 12, 380.00, 'long', NULL, date('now', '-15 days'));

EOF

echo "✅ Portfolio1 holdings updated!"
echo ""
echo "Default stocks added to portfolio1:"
echo "  - NVDA (20 shares @ \$450)"
echo "  - TSLA (15 shares @ \$250)"
echo "  - AVGO (10 shares @ \$1200)"
echo "  - MU (30 shares @ \$80)"
echo "  - PLTR (50 shares @ \$20)"
echo "  - GOOGL (8 shares @ \$140)"
echo "  - MSFT (12 shares @ \$380)"

