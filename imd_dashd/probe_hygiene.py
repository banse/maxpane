"""Shared public-IP detection for publishable probe reports and fixture guards.

No address exceptions: stdlib ``is_global`` decides after parsing candidates.
The runtime redactor remains independently byte-identical and imports only re.
"""
from __future__ import annotations

import ipaddress
import re

_IP_CANDIDATE = re.compile(
    r"(?<![A-Za-z0-9_])(?:\d{1,3}(?:\.\d{1,3}){3}|[0-9A-Fa-f]{1,4}:[0-9A-Fa-f:.]*:[0-9A-Fa-f:.]*|::[0-9A-Fa-f:.]+)"
    r"(?:/\d{1,3})?(?![A-Za-z0-9_])"
)


def public_ip_matches(text: str) -> list[re.Match[str]]:
    """Return spans of globally routable IP literals or networks in text."""
    matches = []
    for match in _IP_CANDIDATE.finditer(text):
        token = match.group()
        try:
            address = (ipaddress.ip_network(token, strict=False) if "/" in token
                       else ipaddress.ip_address(token))
        except ValueError:
            continue
        if address.is_global:
            matches.append(match)
    return matches


def redact_public_ips(text: str) -> str:
    """Mask address bits, retaining a CIDR suffix for useful deny-list output."""
    for match in reversed(public_ip_matches(text)):
        suffix = "/" + match.group().split("/", 1)[1] if "/" in match.group() else ""
        text = text[:match.start()] + "[public-ip]" + suffix + text[match.end():]
    return text
