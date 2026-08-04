from __future__ import annotations

from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Any, Mapping
import logging
import random
import time

import requests


LOGGER = logging.getLogger(__name__)


class HttpRequestError(RuntimeError):
    pass


@dataclass(slots=True)
class RetryPolicy:
    attempts: int = 4
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 20.0


class HttpClient:
    def __init__(
        self,
        *,
        user_agent: str = "PCGameDealScout/1.0 (personal GitHub Actions project)",
        timeout_seconds: float = 20.0,
        retry_policy: RetryPolicy | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self.session = session or requests.Session()
        self.timeout_seconds = timeout_seconds
        self.retry_policy = retry_policy or RetryPolicy()
        self.default_headers = {
            "User-Agent": user_agent,
            "Accept": "application/json, text/plain, text/html;q=0.9, */*;q=0.8",
        }
        self._cache: dict[tuple[str, str], requests.Response] = {}

    def get(
        self,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        cache: bool = False,
    ) -> requests.Response:
        cache_key = (url, repr(sorted((params or {}).items())))
        if cache and cache_key in self._cache:
            return self._cache[cache_key]
        response = self._request("GET", url, params=params, headers=headers)
        if cache:
            self._cache[cache_key] = response
        return response

    def post(
        self,
        url: str,
        *,
        json_body: Any,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> requests.Response:
        return self._request(
            "POST", url, params=params, headers=headers, json_body=json_body
        )

    def _request(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, Any] | None,
        headers: Mapping[str, str] | None,
        json_body: Any | None = None,
    ) -> requests.Response:
        merged_headers = dict(self.default_headers)
        if headers:
            merged_headers.update(headers)

        last_error: Exception | None = None
        for attempt in range(1, self.retry_policy.attempts + 1):
            try:
                response = self.session.request(
                    method,
                    url,
                    params=params,
                    json=json_body,
                    headers=merged_headers,
                    timeout=self.timeout_seconds,
                )
                if response.status_code == 429:
                    delay = self._retry_after_seconds(response)
                    LOGGER.warning(
                        "Rate limited by %s; retrying in %.2fs (attempt %d/%d)",
                        response.url,
                        delay,
                        attempt,
                        self.retry_policy.attempts,
                    )
                    if attempt == self.retry_policy.attempts:
                        response.raise_for_status()
                    time.sleep(delay)
                    continue
                if response.status_code >= 500:
                    if attempt == self.retry_policy.attempts:
                        response.raise_for_status()
                    delay = self._backoff(attempt)
                    LOGGER.warning(
                        "Server error %s from %s; retrying in %.2fs",
                        response.status_code,
                        response.url,
                        delay,
                    )
                    time.sleep(delay)
                    continue
                response.raise_for_status()
                return response
            except (requests.Timeout, requests.ConnectionError, requests.HTTPError) as exc:
                last_error = exc
                if attempt == self.retry_policy.attempts:
                    break
                delay = self._backoff(attempt)
                LOGGER.warning(
                    "Request failed for %s: %s; retrying in %.2fs",
                    url,
                    exc,
                    delay,
                )
                time.sleep(delay)

        raise HttpRequestError(f"Request failed after retries: {method} {url}: {last_error}")

    def _backoff(self, attempt: int) -> float:
        raw = self.retry_policy.base_delay_seconds * (2 ** (attempt - 1))
        jitter = random.uniform(0, min(0.5, raw / 4))
        return min(self.retry_policy.max_delay_seconds, raw + jitter)

    def _retry_after_seconds(self, response: requests.Response) -> float:
        header = response.headers.get("Retry-After")
        if header:
            try:
                return max(0.1, float(header))
            except ValueError:
                try:
                    retry_at = parsedate_to_datetime(header)
                    return max(0.1, retry_at.timestamp() - time.time())
                except (TypeError, ValueError):
                    pass
        try:
            body = response.json()
            return max(0.1, float(body.get("retry_after", 1.0)))
        except (ValueError, TypeError, AttributeError):
            return self._backoff(1)
