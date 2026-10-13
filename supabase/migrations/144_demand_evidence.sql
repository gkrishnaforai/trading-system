-- Evidence feed for the demand layer: structured, source-dated claims
-- that inform canonical demand axes. Append-only — rows are never
-- edited; status transitions draft->approved/rejected/stale only, so
-- every classification change has an auditable evidence trail.
CREATE TABLE IF NOT EXISTS demand_evidence (
    id                 BIGSERIAL PRIMARY KEY,
    symbol             TEXT NOT NULL,
    axis               TEXT NOT NULL,   -- demand_model | capex_sensitivity |
                                        -- demand_durability | utilization_health |
                                        -- capital_funding_risk | ai_monetization
    signal             TEXT NOT NULL,   -- controlled vocab from demand_profile.signal_map
    claim              TEXT NOT NULL,   -- human-readable statement of fact
    value              JSONB,           -- optional structured payload (numbers, dates)
    source             TEXT NOT NULL,   -- filing | earnings_call | guidance | news | manual | llm_extract
    source_ref         TEXT,            -- url, filing id, or quote excerpt
    source_date        TIMESTAMPTZ,     -- when the fact was stated (PIT anchor)
    confidence         TEXT NOT NULL DEFAULT 'medium',  -- high | medium | low
    status             TEXT NOT NULL DEFAULT 'draft',   -- draft | approved | rejected | stale
    extractor_version  TEXT NOT NULL DEFAULT 'demand_evidence_v1',
    reviewed_by        TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (symbol, axis, signal, source_ref)
);

CREATE INDEX IF NOT EXISTS idx_demand_evidence_symbol
    ON demand_evidence(symbol, status);
CREATE INDEX IF NOT EXISTS idx_demand_evidence_axis
    ON demand_evidence(axis, status);
CREATE INDEX IF NOT EXISTS idx_demand_evidence_source_date
    ON demand_evidence(source_date);
