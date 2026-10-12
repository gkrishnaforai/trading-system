-- Capex-efficiency legs for buildout-phase names (NBIS: +454% growth
-- on $20-25B capex — the question is whether each $ converts to GP).
--   capex_eff  annualized incremental gross profit / capex TTM
--   capex_rev  capex TTM / revenue TTM (capital-intensity gate)
ALTER TABLE symbol_flywheel
    ADD COLUMN IF NOT EXISTS capex_eff double precision,
    ADD COLUMN IF NOT EXISTS capex_rev double precision;
