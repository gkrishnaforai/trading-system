from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests
from requests.adapters import HTTPAdapter

try:
    from urllib3.util.retry import Retry
except Exception:  # pragma: no cover
    Retry = None  # type: ignore


class GoApiError(RuntimeError):
    def __init__(self, message: str, *, status_code: Optional[int] = None, url: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.url = url


@dataclass(frozen=True)
class GoApiClientConfig:
    connect_timeout_s: float = 5.0
    read_timeout_s: float = 30.0
    total_retries: int = 2
    backoff_factor: float = 0.3


class GoApiClient:
    def __init__(self, base_url: str, config: Optional[GoApiClientConfig] = None):
        self.base_url = base_url.rstrip("/")
        self.config = config or GoApiClientConfig()
        self.session = requests.Session()

        if Retry is not None:
            retry = Retry(
                total=self.config.total_retries,
                connect=self.config.total_retries,
                read=self.config.total_retries,
                status=self.config.total_retries,
                backoff_factor=self.config.backoff_factor,
                status_forcelist=(429, 500, 502, 503, 504),
                allowed_methods=frozenset({"GET", "POST", "PUT", "DELETE", "PATCH"}),
                raise_on_status=False,
            )
            adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
            self.session.mount("http://", adapter)
            self.session.mount("https://", adapter)

    def _url(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        return self.base_url + path

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        url = self._url(path)
        try:
            resp = self.session.request(
                method=method,
                url=url,
                params=params or {},
                json=json,
                timeout=(self.config.connect_timeout_s, self.config.read_timeout_s),
            )
        except requests.RequestException as e:
            raise GoApiError(str(e), url=url) from e

        if resp.status_code >= 400:
            body = (resp.text or "").strip()
            msg = body if body else f"HTTP {resp.status_code}"
            raise GoApiError(msg, status_code=resp.status_code, url=url)

        try:
            data = resp.json()
        except ValueError as e:
            raise GoApiError("Invalid JSON response", status_code=resp.status_code, url=url) from e

        if not isinstance(data, dict):
            raise GoApiError("Unexpected response type", status_code=resp.status_code, url=url)
        return data

    def get(self, path: str, *, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self.request("GET", path, params=params)

    def post(
        self,
        path: str,
        *,
        payload: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return self.request("POST", path, params=params, json=payload)

    def put(
        self,
        path: str,
        *,
        payload: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return self.request("PUT", path, params=params, json=payload)

    def delete(self, path: str, *, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self.request("DELETE", path, params=params)
