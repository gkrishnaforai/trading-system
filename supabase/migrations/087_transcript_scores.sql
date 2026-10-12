-- Language scores — one row per symbol-period, scored once per doc.
-- Evidence-backed: verbatim quotes required. source: fmp_transcript
-- (if plan upgrades) | sec_8k (EDGAR earnings-release exhibits).
-- NOTE: this file re-runs on every worker boot — must be fully
-- idempotent. No DROP statements.
CREATE TABLE IF NOT EXISTS transcript_scores (
    symbol              varchar(12)  NOT NULL,
    doc_period          varchar(12)  NOT NULL,   -- e.g. 2026Q1
    role                varchar(16)  NOT NULL,   -- hyperscaler|equipment
    source              varchar(20)  NOT NULL,   -- fmp_transcript|sec_8k
    demand_score        numeric,                  -- -2 .. +2
    capex_dir           varchar(16),              -- accelerate|flat|decelerate|cut
    orders_language     varchar(20),              -- accelerating|stable|...
    key_quotes          jsonb        NOT NULL DEFAULT '[]',
    confidence          numeric,
    note                varchar(400),
    model               varchar(60),
    scored_at           timestamptz  NOT NULL DEFAULT now(),
    PRIMARY KEY (symbol, doc_period)
);

CREATE INDEX IF NOT EXISTS transcript_scores_sym_idx
    ON transcript_scores (symbol, doc_period DESC);
