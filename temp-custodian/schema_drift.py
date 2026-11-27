"""schema_drift — the expected-schema contract.

The tracked migrations ARE the schema contract: every CREATE TABLE
adds a name, every DROP TABLE removes it, and the last op wins.
Deriving the expected set from the migration files themselves means
the contract self-maintains — new tables join the expected set when
their migration lands, deliberate drops (like 136) remove them, and
nothing here needs a hand-curated list that could drift on its own.

`missing_tables()` then asks Postgres which of those expected names
don't resolve — the check that turns 'a table was silently dropped'
or 'a migration never ran' from a runtime INSERT error into a
finding. Used at startup (loud log) and by the custodian sense pass
(incident + escalate — remediation is a human applying migrations,
never the agent touching schema).
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Dict, List, Set

logger = logging.getLogger(__name__)

_CREATE_RE = re.compile(
    r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([\w\".]+)", re.I)
_DROP_RE = re.compile(
    r"\bDROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?([^;]+?)(?:\s+CASCADE)?\s*;",
    re.I | re.S)


def _migration_dirs() -> List[Path]:
    """The tracked migration dirs — same layout logic as
    database.run_migrations: repo-root locally, /app in Docker."""
    root = Path(__file__).resolve().parents[3]
    cands = [root / "supabase" / "migrations",
             root / "db" / "migrations_postgres",
             Path("/app/supabase/migrations"),
             Path("/app/db/migrations_postgres")]
    return [d for d in cands if d.exists()]


def _clean(name: str) -> str:
    return name.strip().strip('"').split(".")[-1]


def expected_tables() -> Set[str]:
    """Table names whose LAST migration op is CREATE — drops and
    recreate-drops cancel correctly by file+statement order."""
    ops: Dict[str, bool] = {}          # name -> created?
    for d in _migration_dirs():
        for f in sorted(d.glob("*.sql")):
            sql = f.read_text(errors="replace")
            # walk CREATEs and DROPs in file order — one stream
            events = sorted(
                [(m.start(), True, [_clean(m.group(1))])
                 for m in _CREATE_RE.finditer(sql)]
                + [(m.start(), False,
                    [_clean(n) for n in m.group(1).split(",")])
                   for m in _DROP_RE.finditer(sql)],
                key=lambda e: e[0])
            for _, created, names in events:
                for n in names:
                    if n:
                        ops[n] = created
    return {n for n, created in ops.items() if created}


def missing_tables() -> List[str]:
    """Expected tables Postgres can't resolve — the drift signal.
    One round trip: VALUES list + to_regclass."""
    expected = expected_tables()
    if not expected:
        return []
    from app.database import db
    vals = ", ".join(f"('{t}')" for t in sorted(expected))
    rows = db.execute_query(
        f"SELECT t.name FROM (VALUES {vals}) t(name)"
        " WHERE to_regclass(t.name) IS NULL")
    return [r["name"] for r in rows]


def check_schema_drift() -> List[str]:
    """Startup check — loud log, no remediation (the agent never
    touches schema; a human applies the missing migration)."""
    try:
        missing = missing_tables()
    except Exception as exc:
        logger.warning("schema-drift check failed: %s", exc)
        return []
    if missing:
        logger.error(
            "SCHEMA DRIFT — %d expected tables missing: %s. "
            "Apply pending migrations or restore dropped tables.",
            len(missing), ", ".join(missing))
    return missing
