-- Theme registry — the runtime source for Conviction's future-thesis
-- layer. Code FUTURE_THEMES seeds this; the quarterly theme-review job
-- re-stages themes on evidence and the LLM discovery path inserts
-- 'candidate' rows that must earn promotion. Code dict = fallback
-- when the table is empty or a theme key is missing.
CREATE TABLE IF NOT EXISTS theme_registry (
    id           bigserial PRIMARY KEY,
    theme_key    text NOT NULL UNIQUE,
    name         text NOT NULL,
    thesis       text,
    stage        text NOT NULL DEFAULT 'emerging',
                 -- emerging | inflecting | mainstream | exhausted
    status       text NOT NULL DEFAULT 'active',
                 -- candidate | active | retired
    members      jsonb NOT NULL DEFAULT '{}',   -- {SYM: pure|derivative}
    keywords     jsonb,                          -- headline-matching terms
    evidence     jsonb,                          -- accrued counts/scores
    source       text,                           -- seed | llm | manual
    first_seen   date DEFAULT CURRENT_DATE,
    last_review  date,
    promoted_at  date,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS theme_reg_status_idx
    ON theme_registry (status, stage);
