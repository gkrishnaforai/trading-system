"""Optional Langfuse observation with safe no-op fallback."""
from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Any, Iterator

logger = logging.getLogger(__name__)


@contextmanager
def observe_fundamental_momentum(*, symbol: str, metadata: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Expose a stable observation seam without making Langfuse mandatory."""
    trace = None
    try:
        if os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"):
            from langfuse import Langfuse
            client = Langfuse()
            trace = client.trace(name="fundamental-momentum", metadata={"symbol": symbol, **metadata})
        yield {"trace_id": getattr(trace, "id", None), "observed": trace is not None}
    except Exception as exc:
        logger.warning("Langfuse observation unavailable: %s", exc)
        yield {"trace_id": None, "observed": False}
    finally:
        if trace is not None:
            try:
                trace.update(output={"symbol": symbol})
            except Exception:
                pass
