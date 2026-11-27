"""In-process ring buffer of recent log lines.

The custodian's sensors see WHERE something failed, not WHY — the why
lives in log lines seconds earlier. Attaching a filtered tail of the
last warnings/errors to each incident gives the page (and the analyst
agent) real evidence instead of a bare signature.

Zero-infrastructure: a logging.Handler on the root logger inside the
worker process. Install once at import of app.observability.logging so
the buffer fills from process start.
"""
from __future__ import annotations

import logging
import re
from collections import deque
from typing import List, Optional

_BUF: deque = deque(maxlen=2000)


class _RingHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            _BUF.append((
                record.levelname,
                record.name,
                self.format(record)))
        except Exception:
            pass


def install() -> None:
    """Attach the ring handler to the root logger once."""
    root = logging.getLogger()
    if any(isinstance(h, _RingHandler) for h in root.handlers):
        return
    h = _RingHandler(level=logging.INFO)
    h.setFormatter(logging.Formatter("%(asctime)s %(name)s %(message)s"))
    root.addHandler(h)


def tail(patterns: Optional[List[str]] = None,
         n: int = 15,
         min_level: str = "WARNING") -> List[str]:
    """Last n buffered lines at >= min_level, optionally regex-filtered."""
    levels = {"DEBUG": 10, "INFO": 20, "WARNING": 30,
              "ERROR": 40, "CRITICAL": 50}
    floor = levels.get(min_level, 30)
    rx = re.compile("|".join(patterns), re.I) if patterns else None
    hits = []
    for lvl, name, line in _BUF:
        if levels.get(lvl, 0) < floor:
            continue
        if rx and not rx.search(line) and not rx.search(name):
            continue
        hits.append(f"[{lvl}] {line}"[:500])
    return hits[-n:]


def signature_patterns(sig: str) -> List[str]:
    """Map an incident signature to log-grep terms — pull the lines
    most likely to contain the actual error."""
    parts = sig.split(":")
    if parts[0] == "job" and len(parts) > 1:
        return [parts[1], r"traceback|exception|failed|error"]
    if parts[0] == "stale" and len(parts) > 1:
        return [parts[1], r"ingest|refresh|provider|fetch"]
    if parts[0] == "db":
        return [r"psycopg|postgres|connection|refused|timeout|pgbouncer"]
    if parts[0] == "scan":
        return [r"alert|scan"]
    return [re.escape(sig)]
