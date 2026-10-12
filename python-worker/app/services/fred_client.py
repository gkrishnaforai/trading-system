import os
from datetime import date
from typing import Any, Dict, List, Optional

import requests


class FredClient:
    def __init__(self, api_key: Optional[str] = None, base_url: str = "https://api.stlouisfed.org/fred"):
        self.api_key = api_key or os.getenv("FRED_API_KEY")
        if not self.api_key:
            raise ValueError("FRED_API_KEY is required")
        self.base_url = base_url.rstrip("/")

    def get_observations(
        self,
        series_id: str,
        observation_start: Optional[date] = None,
        observation_end: Optional[date] = None,
        limit: int = 100000,
        sort_order: str = "asc",
    ) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {
            "api_key": self.api_key,
            "file_type": "json",
            "series_id": series_id,
            "limit": limit,
            "sort_order": sort_order,
        }
        if observation_start is not None:
            params["observation_start"] = observation_start.isoformat()
        if observation_end is not None:
            params["observation_end"] = observation_end.isoformat()

        url = f"{self.base_url}/series/observations"
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        payload = resp.json() or {}
        obs = payload.get("observations") or []
        out: List[Dict[str, Any]] = []
        for o in obs:
            # FRED uses '.' for missing values
            val_raw = o.get("value")
            val: Optional[float]
            try:
                if val_raw is None or str(val_raw).strip() == ".":
                    val = None
                else:
                    val = float(val_raw)
            except Exception:
                val = None

            out.append(
                {
                    "date": o.get("date"),
                    "value": val,
                }
            )
        return out
