-- 107_tailwinds.sql — pre-revenue channel journal.
-- The tailwind extractor reads alert_items catalysts (the live news
-- pipeline), LLM-extracts "new revenue channel" claims per symbol,
-- and journals them here. Tiers promote ONLY on corroboration —
-- recurrence across independent headlines lifts rumor→announced→
-- shipping→revenue; one headline can never declare 'revenue'.
-- Graded like every journal: when quarterly numbers confirm a
-- channel, status→confirmed; when it dies, →dead.

CREATE TABLE IF NOT EXISTS tailwinds (
    id          bigserial PRIMARY KEY,
    symbol      text NOT NULL,
    channel     text NOT NULL,          -- 'ai glasses', 'robotaxi'…
    direction   text NOT NULL,          -- tailwind | headwind
    tier        text NOT NULL,          -- rumor|announced|shipping|revenue
    summary     text,                   -- one-line what/why
    confidence  real,                   -- extractor self-rating 0-1
    sources     jsonb,                  -- [{title, published_at, src}]
    hit_count   integer DEFAULT 1,      -- distinct corroborating items
    first_seen  timestamptz,
    last_seen   timestamptz,
    status      text DEFAULT 'active',  -- active|confirmed|dead
    created_at  timestamptz DEFAULT now(),
    updated_at  timestamptz DEFAULT now(),
    UNIQUE (symbol, channel)
);

CREATE INDEX IF NOT EXISTS tailwinds_sym_idx ON tailwinds (symbol, status);
CREATE INDEX IF NOT EXISTS tailwinds_tier_idx ON tailwinds (tier, status);
