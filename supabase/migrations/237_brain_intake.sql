-- 237_brain_intake.sql — admin intake queue for the intelligence brain.
--
-- Admin pastes a doc/news/URL; the system runs it through the same
-- extraction pipeline as every other source (doc_extract: verbatim-
-- quote grounding, deterministic validation) and journals the
-- verdict: accepted (claims landed), partial (some survived),
-- rejected (nothing usable) — always with the canonical why block.
-- The intake row is the queue admin sees on the /brain page; the
-- knowledge itself lands in the existing stores (doc_analyses,
-- tailwinds journal, thesis_watches, driver_commitments).

CREATE TABLE IF NOT EXISTS brain_intake (
    id           bigserial PRIMARY KEY,
    submitted_at timestamptz NOT NULL DEFAULT now(),
    submitted_by text,
    kind         text NOT NULL DEFAULT 'doc',       -- doc | url | note
    title        text,
    url          text,
    text_sha     text,                               -- content hash — dedupe
    symbols      jsonb NOT NULL DEFAULT '[]'::jsonb, -- resolved symbols
    status       text NOT NULL DEFAULT 'queued',
                 -- queued | processing | accepted | partial |
                 -- rejected | error
    verdict      jsonb,                              -- canonical why block
    landed       jsonb NOT NULL DEFAULT '{}'::jsonb, -- {destination: n}
    dropped      jsonb NOT NULL DEFAULT '[]'::jsonb, -- [{symbol, reason}]
    created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_brain_intake_sha
    ON brain_intake (text_sha) WHERE text_sha IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_brain_intake_status
    ON brain_intake (status, submitted_at DESC);
