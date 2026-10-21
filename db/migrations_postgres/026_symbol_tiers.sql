-- symbol_tiers — explicit coverage tiers so expensive refresh work
-- follows a priority schedule instead of a flat universe.
--
--   active    books ∪ watchlist ∪ scan members ∪ futureStocks —
--             the nightly full-stack universe every job already uses
--   monthly   data-covered names outside active, plus names that
--             just reported earnings — a monthly pass keeps their
--             fundamentals/technicals warm for discovery
--   registry  the wide stocks table — metadata only; nothing is
--             fetched until earnings or a screen hit promotes it
--
-- reason records WHY a row sits where it does (position, watchlist,
-- member, promoted:growth30, …) so the audit trail survives demotions.

CREATE TABLE IF NOT EXISTS symbol_tiers (
    symbol       TEXT PRIMARY KEY,
    tier         TEXT NOT NULL CHECK (tier IN ('active','monthly','registry')),
    reason       TEXT,
    promoted_at  TIMESTAMPTZ,
    checked_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS symbol_tiers_tier_idx ON symbol_tiers (tier);
