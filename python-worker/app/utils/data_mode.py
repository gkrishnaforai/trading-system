"""MP_DATA_MODE kill-switch — Phase E of the public-data spine.

`MP_DATA_MODE=full`        — all providers callable (default, dev/desk)
`MP_DATA_MODE=public_only` — fail-closed: every call into a licensed
                             provider raises LicensedDataBlocked,
                             whatever the caller's role. Jobs skip
                             cleanly; the violation is logged.

The gate lives at the provider-client request methods — jobs, API
handlers and admin paths share it, so "public release" can't be
defeated by an admin session. What's PUBLIC vs LICENSED is decided
by lineage.SOURCE_LICENSE — one map, no second list to drift.

Public-surface disclaimer ships in /api/meta for the frontend.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

FULL = "full"
PUBLIC_ONLY = "public_only"

# shown on every public surface — the SEC attribution the frozen spec
# requires; data provenance is EDGAR only in public_only mode
PUBLIC_DISCLAIMER = (
    "Financial data sourced from SEC EDGAR public filings. "
    "Scores measure reported financial condition — not investment "
    "recommendations, probability of bankruptcy, or expected returns.")


class LicensedDataBlocked(RuntimeError):
    """A licensed provider was called while MP_DATA_MODE=public_only.
    Carries the source name so the job runner can skip-vs-error and
    the log line stays auditable."""
    def __init__(self, source: str, callsite: str = ""):
        self.source = source
        self.callsite = callsite
        super().__init__(f"licensed source '{source}' blocked "
                         f"(MP_DATA_MODE=public_only) {callsite}")


def data_mode() -> str:
    """Current mode — env-read per call so a worker restart or a test
    monkeypatch flips it without a settings reload."""
    mode = os.environ.get("MP_DATA_MODE", FULL).strip().lower()
    return PUBLIC_ONLY if mode == PUBLIC_ONLY else FULL


def public_only() -> bool:
    return data_mode() == PUBLIC_ONLY


def guard_source(source: Optional[str],
                 callsite: str = "") -> None:
    """The fail-closed door every licensed provider request goes
    through. Public sources pass; licensed ones raise — in
    public_only mode there is no role that overrides this."""
    if not public_only():
        return
    from app.utils import lineage
    if lineage.license_class(source) == "public":
        return
    logger.error("MP_DATA_MODE=public_only blocked licensed call: "
                 "%s via %s", source, callsite)
    raise LicensedDataBlocked(str(source), callsite)


def status() -> dict:
    """API-visible mode report — what the frontend renders."""
    return {"data_mode": data_mode(),
            "public_only": public_only(),
            "disclaimer": PUBLIC_DISCLAIMER if public_only() else None}
