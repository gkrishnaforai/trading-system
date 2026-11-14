-- Agentic Infrastructure Engine journal — the software picks-and-
-- shovels layer for agentic AI (data plane, streaming, edge runtime,
-- AI gateways, non-human identity, agent security, observability).
-- Scores come from agentic_infra.yaml seeds + journaled evidence;
-- seed priors are flagged, evidence upgrades status.

CREATE TABLE IF NOT EXISTS agentic_infra_snapshots (
    id             bigserial   PRIMARY KEY,
    symbol         text        NOT NULL,
    as_of          date        NOT NULL,
    ais            numeric,                      -- agentic infra score
    tier           text,                         -- core_infrastructure |
                                                 -- emerging | watch |
                                                 -- candidate
    sublayers      jsonb       NOT NULL DEFAULT '[]',
    monetization   text,
    evidence_n     integer,
    coverage_pct   numeric,
    legs           jsonb       NOT NULL DEFAULT '{}',
    components     jsonb       NOT NULL DEFAULT '{}',
    flags          jsonb       NOT NULL DEFAULT '[]',
    status         text        NOT NULL DEFAULT 'seeded',
                                                 -- seeded |
                                                 -- evidence_backed |
                                                 -- candidate
    rules_version  text,
    created_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (symbol, as_of)
);

CREATE INDEX IF NOT EXISTS idx_agentic_infra_asof
    ON agentic_infra_snapshots (as_of);

-- weekly, after ai-cycle (06:30) + competitive-risk (06:45) Saturday
INSERT INTO job_definitions (name, label, purpose, kind, cron, enabled, depends_on, priority)
VALUES ('agentic-infra', 'Agentic infrastructure engine',
        'Score the software picks-and-shovels layer for agentic AI (data plane, streaming, edge, gateways, NHI, agent security, observability) and journal the board',
        'job', '0 7 * * 6', true, '{competitive-risk}', 13)
ON CONFLICT (name) DO UPDATE SET cron=excluded.cron, purpose=excluded.purpose,
       depends_on=excluded.depends_on, priority=excluded.priority;

-- theme row so /themes carries the cohort — members mirror the seed
-- universe: core names are 'pure', adjacent 'derivative', watch
-- names 'speculative'. Evidence accrues via the normal theme-review.
INSERT INTO theme_registry (theme_key, name, thesis, stage, status,
                            members, keywords, source)
VALUES ('agentic_infra', 'Agentic AI infrastructure (software)',
        'Every application building or hosting agents needs the same base layer: event streaming for fresh context, state/memory stores, retrieval, edge runtimes, AI gateways, non-human identity, agent security and observability. These names sell that layer — consumption-priced names monetize agent query volume directly.',
        'inflecting', 'active',
        '{"SNOW":"pure","MDB":"pure","NET":"pure","CFLT":"pure","ORCL":"pure","PLTR":"pure","ESTC":"derivative","FFIV":"derivative","OKTA":"derivative","SAIL":"derivative","PANW":"derivative","CRWD":"derivative","ZS":"derivative","DDOG":"derivative","RBRK":"derivative","MSFT":"derivative","AMZN":"derivative","GOOGL":"derivative","FSLY":"speculative","BASE":"speculative","AKAM":"speculative","DT":"speculative","GTLB":"speculative","VRNS":"speculative","S":"speculative","PATH":"speculative","AI":"speculative","TDC":"speculative","IBM":"speculative","NTNX":"speculative"}'::jsonb,
        '["agentic ai","ai agents","event streaming","kafka","vector database","agent memory","ai gateway","non-human identity","llm observability","edge runtime"]'::jsonb,
        'agentic_infra_engine')
ON CONFLICT (theme_key) DO UPDATE SET
    members = excluded.members,
    keywords = excluded.keywords,
    thesis = excluded.thesis,
    updated_at = now();
