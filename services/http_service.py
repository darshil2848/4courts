"""Generic HTTP client service.

A thin, reusable wrapper around ``requests`` that provides consistent:
    - Timeout enforcement
    - Error handling via ``HttpServiceError``
    - Optional Bearer-token injection
    - JSON and form-data support

Usage example::

    from services.http_service import HttpService

    svc = HttpService(base_url="https://api.example.com", bearer_token="abc123")
    data = svc.get("/users/42")
    svc.post("/users", json={"name": "Alice"})
    svc.put("/users/42", json={"name": "Alice B."})
    svc.delete("/users/42")
"""

from __future__ import annotations

import logging
from typing import Any

import requests
from requests import Response

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 15  # seconds


# ─────────────────────────────────────────────────────────────────────────────
# Custom exception
# ─────────────────────────────────────────────────────────────────────────────
class HttpServiceError(Exception):
    """Raised when an HTTP call returns a non-2xx status code."""

    def __init__(self, method: str, url: str, status_code: int, body: Any) -> None:
        self.method = method
        self.url = url
        self.status_code = status_code
        self.body = body
        super().__init__(f"HTTP {method} {url} failed with status {status_code}: {body}")


# ─────────────────────────────────────────────────────────────────────────────
# Service class
# ─────────────────────────────────────────────────────────────────────────────
class HttpService:
    """Generic HTTP service for communicating with external REST APIs.

    Args:
        base_url:     Base URL prepended to every request path.
        bearer_token: Optional Bearer token added to the Authorization header.
        default_headers: Additional headers applied to every request.
        timeout:      Request timeout in seconds (default 15).
    """

    def __init__(
        self,
        base_url: str = "",
        bearer_token: str | None = None,
        default_headers: dict[str, str] | None = None,
        timeout: int = _DEFAULT_TIMEOUT,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._session = requests.Session()

        if default_headers:
            self._session.headers.update(default_headers)

        if bearer_token:
            self._session.headers["Authorization"] = f"Bearer {bearer_token}"

    # ─── private helpers ─────────────────────────────────────────────────────
    def _url(self, path: str) -> str:
        return f"{self._base_url}/{path.lstrip('/')}" if path else self._base_url

    def _handle(self, response: Response) -> dict | list | str:
        """Raise ``HttpServiceError`` on non-2xx; otherwise return parsed body."""
        method = response.request.method or "?"
        url = response.url

        logger.debug("%s %s → %s", method, url, response.status_code)

        if not response.ok:
            try:
                body = response.json()
            except ValueError:
                body = response.text
            raise HttpServiceError(method, url, response.status_code, body)

        if not response.content:
            return {}

        try:
            return response.json()
        except ValueError:
            return response.text

    # ─── public methods ───────────────────────────────────────────────────────
    def get(
        self,
        path: str = "",
        *,
        params: dict | None = None,
        headers: dict | None = None,
    ) -> dict | list | str:
        """Perform a GET request.

        Args:
            path:    URL path relative to ``base_url``.
            params:  Query-string parameters.
            headers: Per-request extra headers.

        Returns:
            Parsed JSON (dict or list) or raw response text.
        """
        response = self._session.get(
            self._url(path),
            params=params,
            headers=headers,
            timeout=self._timeout,
        )
        return self._handle(response)

    def post(
        self,
        path: str = "",
        *,
        json: dict | list | None = None,
        data: dict | None = None,
        params: dict | None = None,
        headers: dict | None = None,
    ) -> dict | list | str:
        """Perform a POST request.

        Args:
            path:    URL path relative to ``base_url``.
            json:    Request body serialised as JSON.
            data:    Request body as form-encoded data.
            params:  Query-string parameters.
            headers: Per-request extra headers.

        Returns:
            Parsed JSON (dict or list) or raw response text.
        """
        response = self._session.post(
            self._url(path),
            json=json,
            data=data,
            params=params,
            headers=headers,
            timeout=self._timeout,
        )
        return self._handle(response)

    def put(
        self,
        path: str = "",
        *,
        json: dict | list | None = None,
        data: dict | None = None,
        params: dict | None = None,
        headers: dict | None = None,
    ) -> dict | list | str:
        """Perform a PUT request.

        Args:
            path:    URL path relative to ``base_url``.
            json:    Request body serialised as JSON.
            data:    Request body as form-encoded data.
            params:  Query-string parameters.
            headers: Per-request extra headers.

        Returns:
            Parsed JSON (dict or list) or raw response text.
        """
        response = self._session.put(
            self._url(path),
            json=json,
            data=data,
            params=params,
            headers=headers,
            timeout=self._timeout,
        )
        return self._handle(response)

    def patch(
        self,
        path: str = "",
        *,
        json: dict | list | None = None,
        data: dict | None = None,
        params: dict | None = None,
        headers: dict | None = None,
    ) -> dict | list | str:
        """Perform a PATCH request.

        Args:
            path:    URL path relative to ``base_url``.
            json:    Request body serialised as JSON.
            data:    Request body as form-encoded data.
            params:  Query-string parameters.
            headers: Per-request extra headers.

        Returns:
            Parsed JSON (dict or list) or raw response text.
        """
        response = self._session.patch(
            self._url(path),
            json=json,
            data=data,
            params=params,
            headers=headers,
            timeout=self._timeout,
        )
        return self._handle(response)

    def delete(
        self,
        path: str = "",
        *,
        params: dict | None = None,
        json: dict | None = None,
        headers: dict | None = None,
    ) -> dict | list | str:
        """Perform a DELETE request.

        Args:
            path:    URL path relative to ``base_url``.
            params:  Query-string parameters.
            json:    Optional request body serialised as JSON.
            headers: Per-request extra headers.

        Returns:
            Parsed JSON (dict or list) or raw response text.
        """
        response = self._session.delete(
            self._url(path),
            params=params,
            json=json,
            headers=headers,
            timeout=self._timeout,
        )
        return self._handle(response)
