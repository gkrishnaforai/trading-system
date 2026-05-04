from __future__ import annotations

import pathlib
import sys
import os
import uuid
from datetime import datetime, timezone

_here = pathlib.Path(__file__).resolve()
_python_worker_root = _here.parents[2]
if str(_python_worker_root) not in sys.path:
    sys.path.insert(0, str(_python_worker_root))

from app.fair_value_v2.service import FairValueV2Service
from app.fair_value_v2.schemas import FairValueV2Result


def main() -> None:
    symbol = os.getenv("SYMBOL", "JPM")
    all_methods = os.getenv("FAIR_VALUE_V2_ALL_METHODS", "0").strip().lower() in {"1", "true", "yes", "y", "on"}

    svc = FairValueV2Service()

    if not all_methods:
        r = svc.calculate(symbol)
        print(r.model_dump())
        return

    ts = datetime.now(timezone.utc)
    run_id = str(uuid.uuid4())

    method_results = []
    features_hashes = []
    for method_key in sorted(svc.registry.definitions.keys()):
        mr, fh = svc.runner._run_method(method_key, symbol=symbol, as_of_ts=ts)
        method_results.append(mr)
        features_hashes.append(fh)

    r = FairValueV2Result(
        run_id=run_id,
        symbol=symbol,
        as_of_ts=ts,
        fair_value=None,
        scenario_fair_values={},
        regime="all_methods",
        method_results=method_results,
        features_hash=None,
        warnings=[],
    )
    print(r.model_dump())


if __name__ == "__main__":
    main()
