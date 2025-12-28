#!/bin/bash
# View fundamentals data from raw_market_data JSON field
# Usage: ./scripts/view_fundamentals.sh [SYMBOL]

set -e

DB_PATH="${DB_PATH:-./db/trading.db}"
SYMBOL="${1:-AAPL}"

if [ ! -f "$DB_PATH" ]; then
    echo "❌ Database file not found at: $DB_PATH"
    exit 1
fi

echo "📊 Fundamentals Data for $SYMBOL"
echo "=================================="
echo ""

sqlite3 -header -column "$DB_PATH" <<EOF
SELECT 
    stock_symbol,
    date,
    json_extract(fundamental_data, '$.market_cap') as market_cap,
    json_extract(fundamental_data, '$.pe_ratio') as pe_ratio,
    json_extract(fundamental_data, '$.forward_pe') as forward_pe,
    json_extract(fundamental_data, '$.dividend_yield') as dividend_yield,
    json_extract(fundamental_data, '$.eps') as eps,
    json_extract(fundamental_data, '$.revenue') as revenue,
    json_extract(fundamental_data, '$.profit_margin') as profit_margin,
    json_extract(fundamental_data, '$.sector') as sector,
    json_extract(fundamental_data, '$.industry') as industry
FROM raw_market_data
WHERE stock_symbol = '$SYMBOL'
AND fundamental_data IS NOT NULL
ORDER BY date DESC
LIMIT 1;
EOF

echo ""
echo "📰 News Count:"
sqlite3 "$DB_PATH" "SELECT COUNT(*) as news_articles FROM raw_market_data WHERE stock_symbol='$SYMBOL' AND news_metadata IS NOT NULL;"

echo ""
echo "💡 To see full JSON data:"
echo "   sqlite3 $DB_PATH \"SELECT fundamental_data FROM raw_market_data WHERE stock_symbol='$SYMBOL' AND fundamental_data IS NOT NULL ORDER BY date DESC LIMIT 1;\" | python3 -m json.tool"

