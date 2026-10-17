"""Offline normalization of explicit public site/IPFS links; never probes URLs."""
import base64
import re
from urllib.parse import urlsplit

_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")

_SITE_SUFFIXES = (".sites.imd.fun", ".site.identitymd.eth.limo")

def _valid_cid(value):
    """Accept complete common SHA-256 CIDv0/CIDv1 values, never CID paths."""
    if not isinstance(value, str):
        return False
    if re.fullmatch(r"Qm[1-9A-HJ-NP-Za-km-z]{44}", value):
        alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
        number = 0
        for character in value:
            number = number * 58 + alphabet.index(character)
        decoded = number.to_bytes((number.bit_length() + 7) // 8, "big")
        return len(decoded) == 34 and decoded[:2] == b"\x12\x20"
    if not re.fullmatch(r"b[a-z2-7]{58}", value):
        return False
    try:
        data = value[1:].upper()
        decoded = base64.b32decode(data + "=" * ((-len(data)) % 8))
    except ValueError:
        return False
    # Version 1; raw, dag-pb or dag-cbor codec; SHA-256 with 32-byte digest.
    return (len(decoded) == 36 and decoded[0] == 1 and decoded[1] in (0x55, 0x70, 0x71)
            and decoded[2:4] == b"\x12\x20")

def _parsed_public_url(url):
    if not isinstance(url, str) or re.search(r"[\x00-\x20\x7f\\]", url):
        return None
    try:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.port not in (None, 443):
            return None
        if parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment:
            return None
        return parsed
    except ValueError:
        return None

def normalize_site(site: dict) -> dict:
    """Return a copy with a canonical IMD URL and preserved originalUrl.

This function is deterministic/offline. The optional
ipfsUrl is a clearly separate immutable-CID fallback; it is not automatically
fetched and is not substituted for a failed site.
"""
    output = dict(site)
    if (site.get("takenDownAt") or site.get("supersededBy") or site.get("holdReason")
            or site.get("status") in {"failed", "held", "blocked", "taken_down", "removed"}):
        return output
    label = site.get("label")
    parsed = _parsed_public_url(site.get("url"))
    if not isinstance(label, str) or not _LABEL.fullmatch(label) or parsed is None:
        return output
    if parsed.hostname not in {label + suffix for suffix in _SITE_SUFFIXES} or parsed.path not in ("", "/"):
        return output
    canonical = f"https://{label}.sites.imd.fun/"
    output.setdefault("originalUrl", site["url"])
    output["url"] = canonical
    if _valid_cid(site.get("cid")):
        output["ipfsUrl"] = f"https://ipfs.io/ipfs/{site['cid']}/"
    return output
