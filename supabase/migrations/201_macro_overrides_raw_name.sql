-- Provenance: keep the provider's raw event label on each verified
-- override row. The normalized `name` hides misclassification (an
-- FMP "FOMC Minutes" row was journaled as kind='fomc' named "FOMC
-- rate decision" — a phantom November meeting). raw_name makes the
-- provider's actual wording auditable without re-fetching.

ALTER TABLE macro_event_overrides
    ADD COLUMN IF NOT EXISTS raw_name text;
