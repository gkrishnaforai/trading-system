-- Custodian ticket drafts — JIRA staging table
-- The analyst proposes code fixes and enhancements as tickets instead
-- of touching production. Stored here first, pushed to JIRA later

CREATE TABLE IF NOT EXISTS custodian_tickets (
    id          serial PRIMARY KEY,
    ticket_key  text UNIQUE,
    signature   text NOT NULL,
    issue_type  text NOT NULL,         -- code | infra | enhancement
    title       text NOT NULL,
    description text,
    root_cause  text,
    proposed_fix text,
    patch       text,
    evidence    jsonb DEFAULT '{}',
    source      text,                  -- rules | llm | manual
    status      text NOT NULL DEFAULT 'draft',
    created_at  timestamptz DEFAULT now()
);
