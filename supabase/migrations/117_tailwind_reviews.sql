-- tailwind_reviews — weekly LLM classification of the deterministic
-- tailwind screen's candidates: what KIND of tailwind is repricing the
-- name (AI direct/indirect/adopter vs cyclical vs idiosyncratic).
-- Bounded-LLM rule: the screen's flags are the facts— the model only
-- attributes the driver, with rationale journaled for later grading.

CREATE TABLE IF NOT EXISTS tailwind_reviews (
    id            bigserial    PRIMARY KEY,
    as_of         date         NOT NULL,
    symbol        text         NOT NULL,
    linkage       text,         -- ai_direct|ai_indirect|ai_adopter|
                                --  non_ai_cyclical|idiosyncratic|unclear
    confidence    text,         -- high|medium|low
    theme         text,         -- structural theme the model assigns
    rationale     text,         -- <=160 chars, journaled
    screen_flags  jsonb         DEFAULT '{}',
    screen        jsonb         DEFAULT '{}',   -- the numbers shown to it
    model         text,
    created_at    timestamptz   DEFAULT now(),
    UNIQUE (as_of, symbol)
);

CREATE INDEX IF NOT EXISTS idx_tailwind_reviews_sym_asof
    ON tailwind_reviews (symbol, as_of DESC);
CREATE INDEX IF NOT EXISTS idx_tailwind_reviews_linkage
    ON tailwind_reviews (as_of, linkage);

-- weekly classification — Saturday 22:00 UTC, after Friday's data and
-- the week's flywheel/FV refreshes have settled
insert into job_definitions (name, label, purpose, kind, cron, enabled, depends_on, priority)
values ('tailwind-review', 'Tailwind LLM attribution',
        'Weekly LLM pass over the deterministic tailwind screen — classifies what kind of tailwind is repricing each candidate (AI direct/indirect/adopter vs cyclical/idiosyncratic) -> tailwind_reviews',
        'job', '0 22 * * 6', true, null, 30)
on conflict (name) do update set cron=excluded.cron, purpose=excluded.purpose,
       priority=excluded.priority;
