-- Narrative claims ledger — provenance-typed claims with a mutable
-- evidentiary status. claim_type is immutable (guidance stays guidance
-- even when data later supports it); status moves ONLY via journaled
-- evidence, every move logged to claim_reviews. Append-only lineage:
-- status changes produce a new version row linked by supersedes.
CREATE TABLE IF NOT EXISTS narrative_claims (
    id                  BIGSERIAL PRIMARY KEY,
    claim_id            TEXT NOT NULL,             -- stable public id nc_<ulid>
    version             INT NOT NULL DEFAULT 1,
    symbol              TEXT NOT NULL,
    entity              TEXT,                      -- when the claim is about
                                                   -- a counterparty/competitor
    claim               TEXT NOT NULL,
    direction           TEXT,                      -- positive|negative|mixed
    claim_type          TEXT NOT NULL,             -- provenance — never changes
    status              TEXT NOT NULL DEFAULT 'proposed',
    source              TEXT,
    source_date         DATE,
    evidence_confidence NUMERIC,                   -- strength of the evidence
    outcome_confidence  NUMERIC,                   -- the predicted outcome lands
    valid_from          TIMESTAMPTZ DEFAULT now(),
    valid_until         TIMESTAMPTZ,
    evidence_refs       JSONB DEFAULT '[]'::jsonb, -- row ids behind each move
    first_seen          TIMESTAMPTZ DEFAULT now(),
    last_confirmed      TIMESTAMPTZ,
    created_by          TEXT DEFAULT 'collector',
    supersedes          TEXT,                      -- parent claim_id
    dedupe_key          TEXT NOT NULL,             -- type|claim-hash|source-date
    as_of               DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at          TIMESTAMPTZ DEFAULT now(),
    UNIQUE (claim_id, version)
);
-- one live lineage per claim: a new version of the same claim shares
-- dedupe_key but supersedes; re-collecting the same claim finds the
-- existing lineage in code — no blind reinsert
CREATE UNIQUE INDEX IF NOT EXISTS idx_nclaims_dedupe_live
    ON narrative_claims (symbol, dedupe_key) WHERE version = 1;
CREATE INDEX IF NOT EXISTS idx_nclaims_symbol ON narrative_claims (symbol, as_of DESC);
CREATE INDEX IF NOT EXISTS idx_nclaims_status ON narrative_claims (status);

-- claim_reviews — the ledger's audit trail. review_kind: transition
-- (status move + evidence row), critic (bounded LLM review), grade
-- (did the claim come true — calibrates confidence priors over time).
CREATE TABLE IF NOT EXISTS claim_reviews (
    id              BIGSERIAL PRIMARY KEY,
    claim_id        TEXT NOT NULL,
    review_kind     TEXT NOT NULL,             -- transition|critic|grade
    actor           TEXT,                      -- collector|critic|grader|user
    verdict         TEXT,                      -- new status / supported|weak|
                                             -- contradicted / hit|miss
    evidence_refs   JSONB DEFAULT '[]'::jsonb,
    note            TEXT,
    created_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_creviews_claim ON claim_reviews (claim_id, created_at DESC);

-- expectations × sentiment quadrant on the decision journal
ALTER TABLE valuation_decisions ADD COLUMN IF NOT EXISTS timing TEXT;
