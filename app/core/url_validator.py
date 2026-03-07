# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""SSRF protection for user-supplied LLM endpoint URLs."""

import ipaddress
import socket
from urllib.parse import urlparse

from app.config import get_settings


class UnsafeURLError(ValueError):
    """Raised when a URL fails SSRF validation."""


def validate_llm_url(url: str) -> str:
    """Validate a user-supplied LLM base URL.

    In selfhost mode, all URLs are allowed.
    In hosted mode:
      - HTTPS is required
      - Private/loopback/link-local IPs are blocked

    Returns the validated URL (unchanged) or raises UnsafeURLError.
    """
    settings = get_settings()
    if settings.deploy_mode == "selfhost":
        return url

    parsed = urlparse(url)

    if parsed.scheme != "https":
        raise UnsafeURLError("Only HTTPS URLs are allowed in hosted mode")

    hostname = parsed.hostname
    if not hostname:
        raise UnsafeURLError("URL must have a hostname")

    try:
        infos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror:
        raise UnsafeURLError(f"Cannot resolve hostname: {hostname}")

    for family, _, _, _, sockaddr in infos:
        ip = ipaddress.ip_address(sockaddr[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise UnsafeURLError(f"URL resolves to blocked IP range: {ip}")

    return url
