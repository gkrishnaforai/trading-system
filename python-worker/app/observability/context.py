from __future__ import annotations

from contextvars import ContextVar
from typing import Optional
from uuid import UUID


ingestion_run_id: ContextVar[Optional[UUID]] = ContextVar("ingestion_run_id", default=None)


def set_ingestion_run_id(run_id: UUID) -> None:
    ingestion_run_id.set(run_id)


def get_ingestion_run_id() -> Optional[UUID]:
    return ingestion_run_id.get()
