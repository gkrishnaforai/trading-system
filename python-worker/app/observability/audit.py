from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy import text

from app.database import db
from app.observability.context import get_ingestion_run_id
from app.observability.logging import get_logger, log_exception


logger = get_logger(__name__)


def start_run(
    run_id: UUID,
    *,
    environment: Optional[str] = None,
    git_sha: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    payload = {
        "run_id": str(run_id),
        "environment": environment,
        "git_sha": git_sha,
        "metadata": metadata or {},
    }

    with db.get_session() as session:
        session.execute(
            text(
                """
                INSERT INTO data_ingestion_runs (run_id, started_at, status, environment, git_sha, metadata)
                VALUES (:run_id::uuid, NOW(), 'running', :environment, :git_sha, :metadata::jsonb)
                ON CONFLICT (run_id) DO NOTHING
                """
            ),
            payload,
        )


def finish_run(run_id: UUID, *, status: str, metadata: Optional[Dict[str, Any]] = None) -> None:
    payload = {
        "run_id": str(run_id),
        "status": status,
        "metadata": metadata or {},
    }

    with db.get_session() as session:
        session.execute(
            text(
                """
                UPDATE data_ingestion_runs
                SET finished_at = NOW(),
                    status = :status,
                    metadata = COALESCE(metadata, '{}'::jsonb) || :metadata::jsonb
                WHERE run_id = :run_id::uuid
                """
            ),
            payload,
        )


def log_event(
    *,
    level: str,
    operation: str,
    provider: Optional[str] = None,
    symbol: Optional[str] = None,
    message: Optional[str] = None,
    duration_ms: Optional[int] = None,
    records_in: Optional[int] = None,
    records_saved: Optional[int] = None,
    context: Optional[Dict[str, Any]] = None,
    exception: Optional[Exception] = None,
    run_id: Optional[UUID] = None,
) -> None:
    rid = run_id or get_ingestion_run_id()
    if rid is None:
        return

    error_type = None
    error_message = None
    root_cause_type = None
    root_cause_message = None

    if exception is not None:
        error_type = type(exception).__name__
        error_message = str(exception)
        root = _root_exception(exception)
        root_cause_type = type(root).__name__
        root_cause_message = str(root)

    payload = {
        "run_id": str(rid),
        "level": level,
        "provider": provider,
        "operation": operation,
        "symbol": symbol,
        "duration_ms": duration_ms,
        "records_in": records_in,
        "records_saved": records_saved,
        "message": message,
        "error_type": error_type,
        "error_message": error_message,
        "root_cause_type": root_cause_type,
        "root_cause_message": root_cause_message,
        "context": context or {},
    }

    try:
        with db.get_session() as session:
            session.execute(
                text(
                    """
                    INSERT INTO data_ingestion_events (
                        run_id, event_ts, level, provider, operation, symbol,
                        duration_ms, records_in, records_saved, message,
                        error_type, error_message, root_cause_type, root_cause_message, context
                    ) VALUES (
                        :run_id::uuid, NOW(), :level, :provider, :operation, :symbol,
                        :duration_ms, :records_in, :records_saved, :message,
                        :error_type, :error_message, :root_cause_type, :root_cause_message, :context::jsonb
                    )
                    """
                ),
                payload,
            )
    except Exception as e:
        log_exception(logger, e, "audit.log_event")


def _root_exception(exc: Exception) -> Exception:
    current = exc
    while True:
        if getattr(current, "__cause__", None) is not None:
            current = current.__cause__  # type: ignore[assignment]
            continue
        if getattr(current, "__context__", None) is not None:
            current = current.__context__  # type: ignore[assignment]
            continue
        return current
