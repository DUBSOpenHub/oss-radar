"""SSRF-safe HTTP client with tenacity retries for OSS Radar scrapers.

Security notes:
- Blocks localhost/link-local/RFC1918/private/reserved IP ranges (IPv4 + IPv6)
- Fails closed on DNS resolution errors
- Re-validates each redirect hop (no follow_redirects fail-open)
"""

from __future__ import annotations

import ipaddress
import socket
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

# Networks that must never be reachable from scrapers.
# Includes RFC1918, loopback, link-local, CGNAT, multicast, and reserved blocks.
_DISALLOWED_NETWORKS = [
    # IPv4
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),  # CGNAT
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("192.0.2.0/24"),   # TEST-NET-1
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("198.18.0.0/15"),  # benchmark
    ipaddress.ip_network("198.51.100.0/24"),  # TEST-NET-2
    ipaddress.ip_network("203.0.113.0/24"),   # TEST-NET-3
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("240.0.0.0/4"),
    # IPv6
    ipaddress.ip_network("::/128"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),   # unique local
    ipaddress.ip_network("fe80::/10"),  # link-local
    ipaddress.ip_network("ff00::/8"),   # multicast
]


def _is_disallowed_ip(ip_str: str) -> bool:
    """Return True if *ip_str* is private/loopback/link-local/reserved."""
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return True  # fail closed

    if any(addr in net for net in _DISALLOWED_NETWORKS):
        return True

    # Also block any non-globally-routable addresses.
    # (is_global=False covers private, loopback, link-local, multicast, reserved, etc.)
    return not addr.is_global


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
    max_redirects:
        Maximum number of redirects to follow while re-validating each hop.
    """

    def __init__(
        self,
        timeout: int = 10,
        max_retries: int = 3,
        min_wait: float = 2.0,
        max_wait: float = 30.0,
        max_redirects: int = 5,
    ) -> None:
        self.timeout = timeout
        self.max_retries = max_retries
        self.min_wait = min_wait
        self.max_wait = max_wait
        self.max_redirects = max_redirects
        self._client = httpx.Client(
            timeout=httpx.Timeout(timeout),
            follow_redirects=False,  # redirect hops must be re-validated
            headers={"User-Agent": "oss-radar/1.0"},
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        """SSRF-protected GET with tenacity retries."""
        return self._request_with_retry("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        """SSRF-protected POST with tenacity retries."""
        return self._request_with_retry("POST", url, **kwargs)

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
        """Block non-http(s), localhost, and private/loopback IPs via DNS pre-check."""
        parsed = urlparse(url)

        if parsed.scheme not in ("http", "https"):
            raise SSRFError(f"Disallowed URL scheme: {parsed.scheme!r}")

        if parsed.username or parsed.password:
            raise SSRFError("Credentials in URL are not allowed")

        host = (parsed.hostname or "").strip().lower()
        if not host:
            raise SSRFError(f"Cannot determine host from URL: {url!r}")

        if host == "localhost" or host.endswith(".localhost"):
            raise SSRFError(f"SSRF protection: hostname not allowed: {host!r}")

        # Resolve host to IPs and check each one. Fail closed if DNS fails.
        try:
            addr_infos = socket.getaddrinfo(host, None)
        except socket.gaierror:
            raise SSRFError(f"DNS resolution failed for host: {host!r}")

        for ai in addr_infos:
            ip_str = ai[4][0]
            if _is_disallowed_ip(ip_str):
                raise SSRFError(
                    f"SSRF protection: {host!r} resolves to disallowed IP {ip_str!r}"
                )

    def _request_follow_redirects(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """Perform request, manually following redirects with per-hop re-validation."""
        current = url
        for _hop in range(self.max_redirects + 1):
            self._assert_safe(current)
            resp = self._client.request(method, current, **kwargs)

            if resp.status_code in (301, 302, 303, 307, 308):
                location = resp.headers.get("location")
                if not location:
                    return resp

                # Close redirect response before following to avoid leaking connections.
                resp.close()

                # Make the redirect absolute, then re-validate the target.
                current = urljoin(current, location)
                continue

            return resp

        raise SSRFError(f"Too many redirects (>{self.max_redirects}) for URL: {url!r}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type(
            (httpx.TimeoutException, httpx.NetworkError, httpx.ConnectError)
        ),
        reraise=True,
    )
    def _request_with_retry(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        response = self._request_follow_redirects(method, url, **kwargs)
        response.raise_for_status()
        return response
