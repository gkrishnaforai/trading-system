-- 233_held_symbols_view.sql — the held half of book_symbols.
--
-- book_symbols = held ∪ watchlist ("things we track"). Held alone —
-- positions with real quantity, plus book holdings rows — is its own
-- concept: every "is this in my portfolio?" check should resolve
-- against this view, not a hand-rolled positions-only query.
CREATE OR REPLACE VIEW held_symbols AS
SELECT DISTINCT s.symbol
  FROM stocks s
 WHERE EXISTS (SELECT 1
                 FROM portfolio_positions pp
                WHERE pp.stock_id = s.id AND pp.quantity > 0)
    OR EXISTS (SELECT 1
                 FROM portfolio_holdings h
                WHERE h.symbol = s.symbol
                  AND h.status IN ('active', 'inactive'));
