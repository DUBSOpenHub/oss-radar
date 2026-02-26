"""SSRF-safe HTTP client with tenacity retries for OSS Radar scrapers."""

from __future__ import annotations

import ipaddress
import socket
from typing import Any
from urllib.parse import urlparse

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

# RFC-1918 + loopback private ranges
_PRIVATE_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]


def _is_private_ip(ip_str: str) -> bool:
    """Return True if *ip_str* falls within any private/loopback range."""
    try:
        addr = ipaddress.ip_address(ip_str)
        return any(addr in net for net in _PRIVATE_NETWORKS)
    except ValueError:
        return False


class SSRFError(ValueError):
    """Raised when a request targets a disallowed host or private IP."""


class SafeHTTPClient:
    """httpx client wrapper with SSRF protection and tenacity retries.

    Parameters
    ----------
    timeout:
        Per-request timeout in seconds.
    max_retries:
        Maximum tenacity retry attempts.
    min_wait / max_wait:
        Exponential backoff boundaries in seconds.
    """

    def __init__(
        self,
        timeout: int = 10,
        max_retries: int = 3,
        min_wait: float = 2.0,
        max_wait: float = 30.0,
    ) -> None:
        self.timeout = timeout
        self.max_retries = max_retries
        self.min_wait = min_wait
        self.max_wait = max_wait
        self._client = httpx.Client(
            timeout=httpx.Timeout(timeout),
            follow_redirects=True,
            headers={"User-Agent": "oss-radar/1.0"},
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        """SSRF-protected GET with tenacity retries."""
        self._assert_safe(url)
        return self._get_with_retry(url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        """SSRF-protected POST with tenacity retries."""
        self._assert_safe(url)
        return self._post_with_retry(url, **kwargs)

    def close(self) -> None:
        """Close the underlying httpx client."""
        self._client.close()

    def __enter__(self) -> "SafeHTTPClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _assert_safe(self, url: str) -> None:
        """Block private/loopback IPs via DNS pre-check."""
        parsed = urlparse(url)
        host = parsed.hostname or ""
        if not host:
            raise SSRFError(f"Cannot determine host from URL: {url!r}")

        # Resolve host to IPs and check each one
        try:
            addr_infos = socket.getaddrinfo(host, None)
        except socket.gaierror:
            # If DNS fails, block the request to be safe
            raise SSRFError(f"DNS resolution failed for host: {host!r}")

        for ai in addr_infos:
            ip_str = ai[4][0]
            if _is_private_ip(ip_str):
                raise SSRFError(
                    f"SSRF protection: {host!r} resolves to private IP {ip_str!r}"
                )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type(
            (httpx.TimeoutException, httpx.NetworkError, httpx.ConnectError)
        ),
        reraise=True,
    )
    def _get_with_retry(self, url: str, **kwargs: Any) -> httpx.Response:
        response = self._client.get(url, **kwargs)
        response.raise_for_status()
        return response

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type(
            (httpx.TimeoutException, httpx.NetworkError, httpx.ConnectError)
        ),
        reraise=True,
    )
    def _post_with_retry(self, url: str, **kwargs: Any) -> httpx.Response:
        response = self._client.post(url, **kwargs)
        response.raise_for_status()
        return response
