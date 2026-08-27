"""THE LIST's published analysis, read from clustermap's keyless HTTP API.

One version check per tick, and the two bulk reads only when the publisher has
shipped a new analysis.  A published version is immutable and content-addressed,
so a tick that finds the same ``content_hash`` has nothing to download.

This module imports no ``sybilkit`` and knows no pattern language: it fetches and
shape-checks, and ``data/curator_clusters.py`` -- the translation boundary -- is
what turns a payload into something a screen may see.

Socket discipline: with neither ``client`` nor ``transport`` every entry point
returns ``None`` without constructing a client, so a test that forgets to inject
cannot reach the network by accident.
"""
from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

#: The published analysis service.  Keyless, read-only, GET only.
PUBLISHED_BASE_URL = "https://clustermap.vibingco.de/api/v1"

#: Bodies are capped BEFORE they are parsed.  The live export measures 8.3 MB
#: over 19,522 wallets, so 64 MiB is headroom for a larger population rather
#: than a limit anything real approaches; a body past the cap is a failure, not
#: a truncation.
MAX_VERSIONS_BYTES = 1 << 20
MAX_OVERVIEW_BYTES = 16 << 20
MAX_EXPORT_BYTES = 64 << 20

_TIMEOUT = 60.0
_HEADERS = {"Accept": "application/json", "User-Agent": "maxpane"}


@dataclass(frozen=True)
class PublishedVersion:
    version_id: str
    content_hash: str
    detector_version: str | None
    rule_set: str | None
    rules_sha256: str | None
    snapshot_block: int | None
    cluster_count: int | None
    status_counts: dict[str, int]


@dataclass(frozen=True)
class PublishedAnalysis:
    version: PublishedVersion
    clusters: tuple[dict, ...]
    totals: dict
    rows: tuple[dict, ...]


def version_label(version: PublishedVersion | None) -> str | None:
    """``"sybilkit 0.2.0 · 2026-08-25"`` -- what the panels render."""
    if version is None:
        return None
    detector = version.detector_version
    stamp = version.version_id.split("-sybilkit-")[0] if version.version_id else None
    parts = [p for p in (f"sybilkit {detector}" if detector else None, stamp) if p]
    return " · ".join(parts) or None


@asynccontextmanager
async def _session(client: httpx.AsyncClient | None, transport: httpx.AsyncBaseTransport | None):
    """Yield the borrowed ``client``, a short-lived one over ``transport``, or nothing.

    A caller-owned ``client`` is never closed here -- it belongs to the caller.
    A client built from ``transport`` is closed on every exit path, including
    an exception.  With neither, this yields nothing at all: no
    ``httpx.AsyncClient`` is ever constructed, so nothing can reach the
    network by accident.
    """
    if client is not None:
        yield client
        return
    if transport is None:
        yield None
        return
    owned = httpx.AsyncClient(transport=transport, timeout=_TIMEOUT)
    try:
        yield owned
    finally:
        await owned.aclose()


async def _get_json(
    client: httpx.AsyncClient,
    url: str,
    params: dict[str, Any] | None,
    cap: int,
) -> dict | None:
    """GET ``url``, cap-then-parse, ``None`` on any failure. Logs the reason."""
    try:
        resp = await client.get(url, params=params, headers=_HEADERS)
    except Exception as exc:  # noqa: BLE001 -- a dead source degrades, never escapes
        logger.warning("published analysis: request to %s failed: %s", url, exc)
        return None

    if resp.status_code != 200:
        logger.warning("published analysis: %s answered HTTP %s", url, resp.status_code)
        return None

    content_type = resp.headers.get("content-type", "")
    if "application/json" not in content_type:
        logger.warning(
            "published analysis: %s answered content-type %r, not JSON", url, content_type
        )
        return None

    body = resp.content
    if len(body) > cap:
        logger.warning(
            "published analysis: %s body of %d bytes exceeds the %d-byte cap",
            url, len(body), cap,
        )
        return None

    try:
        parsed = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.warning("published analysis: %s body was not valid JSON: %s", url, exc)
        return None

    if not isinstance(parsed, dict):
        logger.warning(
            "published analysis: %s body parsed to %s, not a JSON object",
            url, type(parsed).__name__,
        )
        return None

    return parsed


async def fetch_published_version(
    *,
    client: httpx.AsyncClient | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    base_url: str = PUBLISHED_BASE_URL,
) -> PublishedVersion | None:
    """Read ``/versions`` and return the entry the service names as published."""
    async with _session(client, transport) as session:
        if session is None:
            return None
        body = await _get_json(session, f"{base_url}/versions", None, MAX_VERSIONS_BYTES)
        if body is None:
            return None

        published_id = body.get("published_version")
        entries = body.get("versions")
        if not published_id or not isinstance(entries, list):
            logger.warning("published analysis: /versions body missing published_version/versions")
            return None

        entry = next(
            (e for e in entries if isinstance(e, dict) and e.get("id") == published_id), None
        )
        if entry is None:
            logger.warning(
                "published analysis: no entry in /versions matches published_version %r",
                published_id,
            )
            return None

        content_hash = entry.get("content_hash")
        if not content_hash:
            logger.warning("published analysis: matched entry %r has no content_hash", published_id)
            return None

        return PublishedVersion(
            version_id=published_id,
            content_hash=content_hash,
            detector_version=entry.get("detector_version"),
            rule_set=entry.get("rule_set"),
            rules_sha256=entry.get("rules_sha256"),
            snapshot_block=entry.get("snapshot_block"),
            cluster_count=entry.get("cluster_count"),
            status_counts=entry.get("status_counts") or {},
        )


async def fetch_published_analysis(
    version: PublishedVersion,
    *,
    client: httpx.AsyncClient | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    base_url: str = PUBLISHED_BASE_URL,
) -> PublishedAnalysis | None:
    """Read ``/overview`` and ``/list/export`` for ``version``.

    Both bodies land or the call returns ``None`` -- never a
    :class:`PublishedAnalysis` built from only one of the two.
    """
    async with _session(client, transport) as session:
        if session is None:
            return None

        params = {"version": version.version_id}
        overview = await _get_json(session, f"{base_url}/overview", params, MAX_OVERVIEW_BYTES)
        if overview is None:
            return None

        export = await _get_json(session, f"{base_url}/list/export", params, MAX_EXPORT_BYTES)
        if export is None:
            return None

        clusters = overview.get("clusters")
        totals = overview.get("totals")
        rows = export.get("rows")
        if not isinstance(clusters, list) or not isinstance(totals, dict) or not isinstance(rows, list):
            logger.warning("published analysis: overview/export shape unexpected for %s", version.version_id)
            return None

        return PublishedAnalysis(
            version=version,
            clusters=tuple(clusters),
            totals=totals,
            rows=tuple(rows),
        )
