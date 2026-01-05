from __future__ import annotations

import math
from typing import Any


def sanitize_json_value(value: Any) -> Any:
    if value is None:
        return None

    if isinstance(value, float):
        return value if math.isfinite(value) else None

    try:
        import numpy as np  # type: ignore

        if isinstance(value, (np.floating,)):
            fv = float(value)
            return fv if math.isfinite(fv) else None
    except Exception:
        pass

    if isinstance(value, dict):
        return {k: sanitize_json_value(v) for k, v in value.items()}

    if isinstance(value, (list, tuple)):
        return [sanitize_json_value(v) for v in value]

    return value


def json_dumps_sanitized(payload: Any) -> str:
    import json

    sanitized = sanitize_json_value(payload)
    return json.dumps(sanitized, allow_nan=False)
