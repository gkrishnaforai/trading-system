-- 050_book_symbols_view.sql — ONE canonical book membership.
-- Before this, "book" was defined in four places with different
-- semantics (board uni, calendar tier, earnings_watch._TIER,
-- symbol_tiers) — GOOGL/MSFT were holdings-only and invisible to
-- every gate that forgot the holdings union. Every consumer now
-- asks the same question: symbol IN (SELECT symbol FROM
-- book_symbols). Book = held positions + book holdings (active or
-- inactive — the board shows both) + explicit watchlist. Scan/theme
-- memberships (rule_breaker, smallcap) stay OUT — they extend
-- coverage in symbol_tiers, they are not the book.
SELECT pg_advisory_xact_lock(715050);

CREATE OR REPLACE VIEW book_symbols AS
SELECT DISTINCT s.symbol
FROM stocks s
WHERE EXISTS (SELECT 1 FROM portfolio_positions pp
              WHERE pp.stock_id = s.id AND pp.quantity > 0)
   OR EXISTS (SELECT 1 FROM portfolio_holdings h
              WHERE h.symbol = s.symbol
              AND h.status IN ('active','inactive'))
   OR EXISTS (SELECT 1 FROM watchlist_stocks ws
              WHERE ws.stock_id = s.id);
