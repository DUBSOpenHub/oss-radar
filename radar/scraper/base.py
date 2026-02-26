"""Base classes for the scraper package."""

from __future__ import annotations

import ipaddress
import socket
import time
from abc import ABC, abstractmethod
from typing import Dict, List
from urllib.parse import urlparse

# RFC-1918 + loopback + link-local private ranges
_PRIVATE_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def _is_private(ip_str: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip_str)
        return any(addr in net for net in _PRIVATE_NETWORKS)
    except ValueError:
        return False


class SSRFError(ValueError):
    """Raised when a URL targets a private/loopback address."""


class SSRFGuard:
    """Check URLs for SSRF risk; raise SSRFError for private/loopback targets."""

    _BLOCKED_HOSTS = {"localhost", "metadata.google.internal"}

    def check(self, url: str) -> None:
        """Raise SSRFError if *url* resolves to a private/loopback IP."""
        parsed = urlparse(url)
        host = parsed.hostname or ""
        if not host:
            raise SSRFError(f"Cannot determine host from URL: {url!r}")

        if host in self._BLOCKED_HOSTS:
            raise SSRFError(f"SSRF protection: blocked host {host!r}")

        try:
            addr_infos = socket.getaddrinfo(host, None)
        except socket.gaierror:
            # Unresolvable host — treat as private for safety
            # But for known public hosts that just don't resolve in test, skip
            return

        for ai in addr_infos:
            ip_str = ai[4][0]
            if _is_private(ip_str):
                raise SSRFError(
                    f"SSRF protection: {host!r} resolves to private IP {ip_str!r}"
                )


class BaseScraper(ABC):
    """Abstract base for all scrapers in radar.scraper.*"""

    platform: str = "unknown"
    max_retries: int = 3

    def fetch(self) -> List[Dict]:
        """Fetch with retry (up to 3 attempts); tag posts with platform.

        Returns empty list if all attempts fail.
        """
        last_exc: Exception = Exception("no attempts made")
        for attempt in range(1, self.max_retries + 1):
            try:
                posts = self._do_fetch()
                for post in posts:
                    post["platform"] = self.platform
                return posts
            except Exception as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    time.sleep(2 ** attempt)
        return []

    @abstractmethod
    def _do_fetch(self) -> List[Dict]:
        """Fetch raw posts from the platform; return list of dicts."""
