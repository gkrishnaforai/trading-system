-- Blog posts — the public content surface.
-- Deterministic post engine writes daily briefs, receipts recaps,
-- event verdicts and mover explainers from journaled data; the
-- /insights pages read this table. LLM polish is optional later —
-- the evidence in `payload` is what makes the post ours.
CREATE TABLE IF NOT EXISTS blog_posts (
    id            BIGSERIAL PRIMARY KEY,
    slug          TEXT NOT NULL UNIQUE,          -- kind-YYYY-MM-DD[-sym]
    kind          TEXT NOT NULL,                 -- daily_brief | receipts | event_verdict | mover | explainer
    title         TEXT NOT NULL,
    dek           TEXT,                          -- one-line standfirst
    body_md       TEXT NOT NULL,
    symbols       TEXT[] NOT NULL DEFAULT '{}',
    tier          TEXT NOT NULL DEFAULT 'public',
    payload       JSONB,                         -- the evidence the post renders
    as_of         DATE NOT NULL DEFAULT CURRENT_DATE,
    published_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Schema repair: the table pre-exists on some deployments with an
-- older drifted shape (the /posts 500). CREATE IF NOT EXISTS can't
-- add columns — add any the engine needs, idempotently.
ALTER TABLE blog_posts ADD COLUMN IF NOT EXISTS slug TEXT;
ALTER TABLE blog_posts ADD COLUMN IF NOT EXISTS kind TEXT;
ALTER TABLE blog_posts ADD COLUMN IF NOT EXISTS title TEXT;
ALTER TABLE blog_posts ADD COLUMN IF NOT EXISTS dek TEXT;
ALTER TABLE blog_posts ADD COLUMN IF NOT EXISTS body_md TEXT;
ALTER TABLE blog_posts ADD COLUMN IF NOT EXISTS symbols TEXT[] DEFAULT '{}';
ALTER TABLE blog_posts ADD COLUMN IF NOT EXISTS tier TEXT DEFAULT 'public';
ALTER TABLE blog_posts ADD COLUMN IF NOT EXISTS payload JSONB;
ALTER TABLE blog_posts ADD COLUMN IF NOT EXISTS as_of DATE DEFAULT CURRENT_DATE;
ALTER TABLE blog_posts ADD COLUMN IF NOT EXISTS published_at TIMESTAMPTZ DEFAULT now();

-- slug must be unique for the post engine's ON CONFLICT — the
-- legacy table may already hold rows with NULL slugs; only add the
-- constraint shape that survives them: a partial unique index.
CREATE UNIQUE INDEX IF NOT EXISTS uq_blog_posts_slug
    ON blog_posts (slug) WHERE slug IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_blog_posts_kind
    ON blog_posts (kind, published_at DESC);
