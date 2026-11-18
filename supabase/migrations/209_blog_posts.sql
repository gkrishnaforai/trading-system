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
CREATE INDEX IF NOT EXISTS idx_blog_posts_kind
    ON blog_posts (kind, published_at DESC);
