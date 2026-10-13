-- Custodian escalation hardening
-- manual_steps holds the per-signature intervention runbook shown on
-- the Custodian page and alerted_at gates the one-shot technical alert
-- into universal_events when an incident crosses to escalated

ALTER TABLE custodian_incidents
    ADD COLUMN IF NOT EXISTS manual_steps text,
    ADD COLUMN IF NOT EXISTS alerted_at timestamptz;
