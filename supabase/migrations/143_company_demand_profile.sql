-- Canonical business-demand exposure profile per symbol.
-- Persisted, evidence-tagged, versioned — never re-inferred per page.
CREATE TABLE IF NOT EXISTS company_demand_profile (
    symbol                TEXT PRIMARY KEY,
    demand_model          TEXT,          -- capex_project | capacity_rental | usage_consumption | recurring_software | maintenance_services | power_generation | mixed | speculative | unknown
    capex_sensitivity     TEXT,          -- very_high | high | medium | low | unknown
    demand_durability     TEXT,          -- contracted | recurring | usage_based | replacement_cycle | discretionary | speculative | unknown
    utilization_health    TEXT,          -- rising | stable_high | stable | falling | unknown
    capital_funding_risk  TEXT,          -- low | moderate | high | critical | unknown
    ai_monetization       TEXT,          -- proven | scaling | early | unproven | unknown
    archetypes            JSONB,         -- fv classification at write time
    evidence              JSONB,         -- source evidence / notes / override reason
    source                TEXT NOT NULL DEFAULT 'rules',   -- rules | symbol_seed | llm_draft | manual
    updated_by            TEXT,
    as_of                 TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_demand_profile_model
    ON company_demand_profile(demand_model);
CREATE INDEX IF NOT EXISTS idx_demand_profile_sensitivity
    ON company_demand_profile(capex_sensitivity);
