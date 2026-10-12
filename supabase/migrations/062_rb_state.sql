-- 062: rb_state — tiny kv store for rule-breakers scheduler state
-- (last discovery pass timestamp). Auto-added members carry
-- checklist.auto=true so the discovery pass can demote what it added.
CREATE TABLE IF NOT EXISTS rb_state (
    key TEXT PRIMARY KEY,
    value TEXT
);
