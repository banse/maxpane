"""Fold the IMD swarm control plane's reads into rows the panels render.

Pure: stdlib, the pure ``analytics/surf_swarm_signals`` rollups, the
``data/surf_models`` contract tuples, and the constant ``UNKNOWN_SEAT`` / pure UUID validator from
``surf_swarm_client``. The fold never calls the client.  No network, no clock
(callers pass ``now_ts``), no Textual.  The shapes this
folds are recorded in ``docs/imd_swarm_api.md``; the reader that fetches
them is ``surf_swarm_client.py``.  The v1 folds (field / queue / blocked /
shipped / score rows and the old ``throughput``) retired with their widgets
in WP7 of the swarm v2 plan.

Every value here is ``None`` when it was not read.  A zero is a zero.
"""
from __future__ import annotations

import datetime
import json
import unicodedata
import math
import logging
from functools import lru_cache
import re
import statistics
from collections.abc import Mapping
from typing import Any

# Pure, stdlib-only rollups (swarm v2 plan §1.6); the widgets import the same
# module, so the fold and the panels count with one implementation.
from maxpane_dashboard.analytics.surf_swarm_signals import (
    completed_within, count_by, duration_stats, seen_since_ts, state_rollup,
)
from maxpane_dashboard.data.surf_models import (
    SURF_ROW_KEYS, SWARM_SEAT_REVIEW_STATUSES, SWARM_SEAT_SELECTED_FIELDS, SWARM_SEAT_STATES,
    SWARM_SEAT_SUMMARY_FIELDS, SWARM_BOARD_SUMMARY_FIELDS, SWARM_FLEET_FIELDS,
    SWARM_SEAT_LIVE_FIELDS, SWARM_SEAT_CONTRIB_FIELDS,
    SWARM_ORACLE_NODE_KEYS, SWARM_ORACLE_CACHE_FIELDS,
    SWARM_ANSWER_FIELDS, SWARM_ANSWER_CACHE_FIELDS, SWARM_ANSWER_STATES, SWARM_ANSWER_ROW_CAP,
)
# Shared constant and pure validator: the client owns the normalised 404 and
# canonical job-id check; the fold reuses both without calling the client.
from maxpane_dashboard.data.surf_swarm_client import UNKNOWN_SEAT, SUBMISSIONS_NOT_FOUND, parse_job_id

__all__ = [
    "health_facts", "network_of",
    # swarm v2 (WP3)
    "breaker", "inflight_rows", "launch_rows", "merge_seen",
    "queue_total", "parse_seat_token", "seat_rows",
    "seen_entry", "seen_since_ts", "site_rows", "skill_rows",
    "throughput_facts",
    # AGENT body on /seats/{tokenId} (docs/surf_agent_seats_plan.md WP1b)
    "choose_seat", "coerce_seat_slot", "seat_node_rows", "seat_teammates",
    "seat_state", "seat_summary_from_seat", "seat_work_rows",
    "board_rows", "board_summary", "fleet", "seat_live", "seat_contrib",
    "normalize_contributors", "normalize_workers",
    "coerce_contributors_slot", "coerce_workers_slot",
]

#: A job in one of these states is finished; nothing else is.

#: Chain ids this view knows how to name.  An allowlist, so an unknown chain
#: renders the em dash rather than a guess (``_pool4.network_word``'s rule).
_NETWORKS = {1: "MAINNET", 11155111: "SEPOLIA"}

_SERVICES = {"verifier": "verifierUp", "publisher": "publisherUp",
             "deployer": "deployerUp"}


def network_of(chain_id: object) -> str | None:
    """``"MAINNET"`` / ``"SEPOLIA"``, or ``None`` for anything else."""
    try:
        return _NETWORKS.get(int(chain_id))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _ts(value: object) -> float | None:
    """One ISO-8601 stamp as epoch seconds, or ``None``."""
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.datetime.fromisoformat(
            value.replace("Z", "+00:00")
        ).timestamp()
    except ValueError:
        return None


def _int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def health_facts(health: Mapping[str, Any] | None) -> dict[str, Any]:
    """The hero's numbers.  Every one ``None`` when the read failed."""
    if not isinstance(health, Mapping):
        return {"agents_online": None, "agents_enrolled": None,
                "working_now": None, "accepted_today": None,
                "services_up": None, "network": None, "health_status": None}
    identity = health.get("identity")
    chain = identity.get("chainId") if isinstance(identity, Mapping) else None
    services_up = {}
    for name, key in _SERVICES.items():
        value = health.get(key)
        if key not in health:
            services_up[name] = None
        else:
            services_up[name] = bool(value)
    return {
        "agents_online": _int(health.get("connectedDaemons")),
        "agents_enrolled": _int(health.get("activeEnrollments")),
        "working_now": _int(health.get("workingNow")),
        "accepted_today": _int(health.get("acceptedLastDay")),
        "services_up": services_up,
        "network": network_of(chain),
        "health_status": _str(health.get("status")),
    }


# ---------------------------------------------------------------------------
# swarm v2 (plan WP3, 2026-09-21).  Everything below is what the rebuilt
# ``s`` body and the ``a`` AGENT body read; the v1 folds that used to sit
# above retired in WP7.
#
# Rules of this section: stdlib plus the pure imports above (module docstring); ``now_ts`` injected; every enumeration
# open (an unknown state is its own bucket); a value not read is ``None`` and
# a real zero is ``0``; a non-Mapping where a Mapping is expected is skipped,
# never raised on.  Every row dict carries exactly the fields
# ``data/surf_models.SURF_ROW_KEYS[<key>]`` names, in that order.
#
# ``None`` vs ``[]``: every ``*_rows`` fold returns ``[]`` for both a ``None``
# and an empty input.  The manager decides ``None`` (could not look) against
# ``[]`` (looked, nothing there) from whether the read happened -- a fold
# never sees "the read failed", so no fold can be talked into faking a read
# by being handed ``None``.
# ---------------------------------------------------------------------------

_SEEN_ENTRY_FIELDS = ("created_ts", "updated_ts", "state", "template", "nodes")


def _str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _float(value: object) -> float | None:
    """An int or float that is not a bool, else ``None``."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def parse_seat_token(value: object) -> int | None:
    """An IDMD seat token as a caller or a source named it, or ``None``.

    A non-negative, non-``bool`` ``int``, or a string of ASCII digits
    (surrounding whitespace allowed) -- the one strict parser both this fold
    and ``SurfManager`` use (a job node's ``seat.tokenId``, a persisted seen
    summary's ``seat_token``, the ``seat=`` argument, the ROSTER row's text).
    ``int()`` alone would accept a sign, ``_`` separators and non-ASCII
    digits (``"١٥٤٨"``); anything like that is no token, never a guess.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, str):
        text = value.strip()
        if text and text.isascii() and text.isdigit():
            return int(text)
    return None


def _mappings(seq: object) -> list[Mapping[str, Any]]:
    """The Mapping members of a sequence; anything else is skipped, not raised on."""
    if seq is None or isinstance(seq, (str, bytes, Mapping)):
        return []
    try:
        return [item for item in seq if isinstance(item, Mapping)]
    except TypeError:
        return []


def _details_map(details: object) -> dict[str, Mapping[str, Any]]:
    """``job_id -> detail`` for every detail that was read.

    Accepts the manager's Mapping (``job_id -> detail | None``; a ``None``
    means that detail was not read and the job is *uncovered*) or a plain
    sequence of details keyed by their own ``id``.
    """
    out: dict[str, Mapping[str, Any]] = {}
    if isinstance(details, Mapping):
        for key, detail in details.items():
            if isinstance(key, str) and isinstance(detail, Mapping):
                out[key] = detail
        return out
    for detail in _mappings(details):
        job_id = _str(detail.get("id"))
        if job_id is not None:
            out[job_id] = detail
    return out


def _seat(node: Mapping[str, Any]) -> tuple[int | None, str | None]:
    """``(token_id, agent_id)`` off ``node.seat``; ``(None, None)`` when absent."""
    seat = node.get("seat")
    if not isinstance(seat, Mapping):
        return None, None
    return parse_seat_token(seat.get("tokenId")), _str(seat.get("agentId"))


def _verdict(node: Mapping[str, Any]) -> Mapping[str, Any]:
    verdict = node.get("verdict")
    return verdict if isinstance(verdict, Mapping) else {}


def _node_at(node: Mapping[str, Any]) -> float | None:
    """When the node last moved: its ``updatedAt``, else the verdict's ``at``."""
    at = _ts(node.get("updatedAt"))
    return at if at is not None else _ts(_verdict(node).get("at"))


def _newest_first(rows: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    """Sort by a timestamp field, newest first, ``None`` last.  In place."""
    rows.sort(key=lambda r: (r[field] is None, -(r[field] or 0.0)))
    return rows


# -- hero ------------------------------------------------------------------


def queue_total(health: object) -> int | None:
    """The sum of every ``/health.pending*`` counter that is an int.

    An open set -- a counter the host adds tomorrow is counted the day it
    appears.  ``None`` when health is not a mapping or no ``pending*`` key
    carries an int: nothing was read, so no zero is claimed.
    """
    if not isinstance(health, Mapping):
        return None
    counters = [
        _int(value) for key, value in health.items()
        if isinstance(key, str) and key.startswith("pending")
    ]
    present = [c for c in counters if c is not None]
    return sum(present) if present else None


def breaker(health: object) -> dict[str, Any] | None:
    """``{"tripped": bool, "detail": str | None}`` off ``/health.deployBreaker``.

    ``null`` on the wire is "present and not tripped"; anything else is
    tripped, with a string as its detail (a mapping's ``reason``/``detail``/
    first string value).  ``None`` when the key is absent or health is not
    a mapping: could not look, which is not the same fact as not tripped.
    """
    if not isinstance(health, Mapping) or "deployBreaker" not in health:
        return None
    value = health.get("deployBreaker")
    if value is None:
        return {"tripped": False, "detail": None}
    detail: str | None = None
    if isinstance(value, str):
        detail = value
    elif isinstance(value, Mapping):
        for key in ("reason", "detail"):
            if isinstance(value.get(key), str):
                detail = value[key]
                break
        else:
            detail = next((v for v in value.values() if isinstance(v, str)), None)
    return {"tripped": True, "detail": detail}


# -- IN FLIGHT -------------------------------------------------------------


def _active_node(detail: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    """The node in ``working`` if any, else the newest non-``accepted`` node."""
    if not isinstance(detail, Mapping):
        return None
    nodes = _mappings(detail.get("nodes"))
    working = [n for n in nodes if n.get("state") == "working"]
    if working:
        return max(working, key=lambda n: _node_at(n) or float("-inf"))
    open_nodes = [n for n in nodes if n.get("state") != "accepted"]
    if open_nodes:
        return max(open_nodes, key=lambda n: _node_at(n) or float("-inf"))
    return None


def inflight_rows(jobs: object, details: object, *,
                  now_ts: float) -> list[dict[str, Any]]:
    """``swarm_inflight_rows``: jobs in state ``executing``, newest first.

    ``details`` is ``job_id -> detail | None``.  The node fields, including dispatch/failure notes, are
    ``None`` when the detail was not read or has no active node -- the
    attribution is a fact about the detail route, not the list.
    ``agent_token`` is the seat's ``tokenId`` as an int when it parses;
    ``agent_id`` stays a str.  Returns ``[]`` for both ``None`` and ``[]``
    input (see the section header).
    """
    dmap = _details_map(details)
    rows: list[dict[str, Any]] = []
    for job in _mappings(jobs):
        if job.get("state") != "executing":
            continue
        job_id = _str(job.get("id"))
        node = _active_node(dmap.get(job_id)) if job_id is not None else None
        created = _ts(job.get("createdAt"))
        token, agent = _seat(node) if node is not None else (None, None)
        dispatch = _str(node.get("dispatchNote")) if node is not None else None
        failure = _str(node.get("failureReason")) if node is not None else None
        note = dispatch if dispatch else failure or None
        note_kind = "dispatch" if dispatch else "failure" if failure else None
        rows.append({
            "job_id": job_id,
            "template": _str(job.get("template")),
            "objective": _str(job.get("objective")),
            "created_ts": created,
            "age_s": (now_ts - created) if created is not None else None,
            "node_key": _str(node.get("key")) if node is not None else None,
            "node_role": _str(node.get("role")) if node is not None else None,
            "node_state": _str(node.get("state")) if node is not None else None,
            "agent_token": token,
            "agent_id": agent,
            "revisions": _int(node.get("revisions")) if node is not None else None,
            "note": note,
            "note_kind": note_kind,
        })
    return _newest_first(rows, "created_ts")


# -- CAPABILITY / LAUNCHES / SITES -----------------------------------------


def skill_rows(skills: object) -> list[dict[str, Any]]:
    """``swarm_skill_rows`` off ``/skills``, sorted by role then id.

    ``tier``/``judge`` are ``None`` when null; ``requires`` is always a
    ``list[str]`` (a non-list is ``[]``); ``checks`` is ``str | None``.
    """
    rows: list[dict[str, Any]] = []
    for skill in _mappings(skills):
        requires = skill.get("requires")
        record = skill.get("record")
        record = record if isinstance(record, Mapping) else {}
        rows.append({
            "skill_id": _str(skill.get("id")),
            "version": _int(skill.get("version")),
            "role": _str(skill.get("role")),
            "kind": _str(skill.get("kind")),
            "tier": _int(skill.get("tier")),
            "judge": _str(skill.get("judge")),
            "checks": _str(skill.get("checks")),
            "requires": ([r for r in requires if isinstance(r, str)]
                         if isinstance(requires, list) else []),
            "inference": _str(skill.get("inference")),
            **{key: _served_token(record.get(key))
               for key in ("attempts", "accepted", "rejected", "pending")},
        })
    rows.sort(key=lambda r: (r["role"] is None, r["role"] or "",
                             r["skill_id"] is None, r["skill_id"] or ""))
    return rows


def _artifact(artifact: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "role": _str(artifact.get("role")),
        "name": _str(artifact.get("name")),
        "address": _str(artifact.get("address")),
        "tx_hash": _str(artifact.get("txHash")),
        "block_number": _int(artifact.get("blockNumber")),
    }


def launch_rows(launches: object) -> list[dict[str, Any]]:
    """``swarm_launch_rows`` off ``/launches``, newest ``createdAt`` first.

    ``artifacts`` is ``list[dict(role, name, address, tx_hash, block_number)]``;
    ``artifact_count`` is the host's field when it is an int, else the
    number of artifacts actually listed.
    """
    rows: list[dict[str, Any]] = []
    for launch in _mappings(launches):
        artifacts = [_artifact(a) for a in _mappings(launch.get("artifacts"))]
        count = _int(launch.get("artifactCount"))
        rows.append({
            "launch_number": _int(launch.get("launchNumber")),
            "kind": _str(launch.get("kind")),
            "status": _str(launch.get("status")),
            "chain_id": _int(launch.get("chainId")),
            "repo_url": _str(launch.get("sourceRepoUrl")),
            "commit": _str(launch.get("sourceCommit")),
            "parked_reason": _str(launch.get("parkedReason")),
            "artifact_count": count if count is not None else len(artifacts),
            "created_ts": _ts(launch.get("createdAt")),
            "updated_ts": _ts(launch.get("updatedAt")),
            "artifacts": artifacts,
        })
    return _newest_first(rows, "created_ts")


def site_rows(sites: object) -> list[dict[str, Any]]:
    """``swarm_site_rows`` off ``/sites``, newest ``updatedAt`` first."""
    rows: list[dict[str, Any]] = []
    for site in _mappings(sites):
        rows.append({
            "label": _str(site.get("label")),
            "ens_name": _str(site.get("ensName")),
            "cid": _str(site.get("cid")),
            "bytes": _int(site.get("bytes")),
            "status": _str(site.get("status")),
            "tx_hash": _str(site.get("txHash")),
            "block_number": _int(site.get("blockNumber")),
            "job_id": _str(site.get("jobId")),
            "superseded_by": _str(site.get("supersededBy")),
            "_updated_ts": _ts(site.get("updatedAt")),
        })
    _newest_first(rows, "_updated_ts")
    for row in rows:
        del row["_updated_ts"]
    return rows


# -- THROUGHPUT ------------------------------------------------------------


def throughput_facts(jobs: object, seen: object, *,
                     now_ts: float) -> dict[str, Any] | None:
    """``swarm_throughput`` (plan §1.3).

    ``None`` when ``jobs is None`` -- the list was never read.  On a genuine
    empty read every window field is an honest empty (``window_n == 0``,
    ``states == []``, durations ``None``).  The window is what ``/jobs``
    actually returned: ``window_start_ts``/``window_end_ts`` are the min/max
    ``createdAt``, ``window_n`` the number of job mappings.  Durations are
    ``deliveredAt - createdAt`` of completed jobs that carry a delivery.
    ``completed_24h``/``seen_since_ts`` come from the seen slot and are
    ``None`` while it is still accumulating (plan R-A).  ``dur_n`` is the
    size of that duration sample -- how many completed jobs carried a
    delivery -- so a ``None`` median can say *why* (under two samples) and
    a real one can say what it stands on; ``0`` on an empty read is a real
    count of a read list (WP7, additive to §1.3).
    """
    if jobs is None:
        return None
    job_list = _mappings(jobs)
    created = [c for c in (_ts(j.get("createdAt")) for j in job_list) if c is not None]
    durations: list[float] = []
    for job in job_list:
        if job.get("state") != "completed":
            continue
        delivery = job.get("delivery")
        if not isinstance(delivery, Mapping):
            continue
        start, end = _ts(job.get("createdAt")), _ts(delivery.get("deliveredAt"))
        if start is not None and end is not None and end >= start:
            durations.append(end - start)
    reasons = (
        j.get("blockedReason") for j in job_list if j.get("state") == "cancelled"
    )
    completed_24h, since = completed_within(seen, now_ts, 86_400)
    out: dict[str, Any] = {
        "window_start_ts": min(created) if created else None,
        "window_end_ts": max(created) if created else None,
        "window_n": len(job_list),
        "states": state_rollup(j.get("state") for j in job_list),
    }
    out.update(duration_stats(durations))
    out["dur_n"] = len(durations)
    out["cancel_reasons"] = count_by(
        (r for r in reasons if isinstance(r, str) and r), "reason"
    )
    out["completed_24h"] = completed_24h
    out["seen_since_ts"] = since
    return out


# -- the jobs-seen slot (WP4 persists it; its shape is defined here) -------


def _seen_node(node: Mapping[str, Any]) -> dict[str, Any]:
    token, agent = _seat(node)
    verdict = _verdict(node)
    return {
        # ``key`` first: it tells two seen nodes of one seat on one job apart
        # (WP3 review, 2026-09-21). Its window-fold node-rows reader retired
        # with the /seats plan's WP5; the persisted shape is unchanged.
        "key": _str(node.get("key")),
        "seat_token": token,
        "seat_agent": agent,
        "role": _str(node.get("role")),
        "state": _str(node.get("state")),
        "verdict_status": _str(verdict.get("status")),
        "rejection_code": _str(verdict.get("rejectionCode")),
        "revisions": _int(node.get("revisions")),
        "at_ts": _node_at(node),
    }


def seen_entry(job: Mapping[str, Any], detail: object) -> dict[str, Any]:
    """One job's slot entry: the job tuple plus a summary of every node.

    ``nodes`` is ``[]`` when no detail was read for the job -- the seat
    record then extends only as far as the list route can see.
    """
    nodes = _mappings(detail.get("nodes")) if isinstance(detail, Mapping) else []
    return {
        "created_ts": _ts(job.get("createdAt")),
        "updated_ts": _ts(job.get("updatedAt")),
        "state": _str(job.get("state")),
        "template": _str(job.get("template")),
        "nodes": [_seen_node(n) for n in nodes],
    }


def _entry_stamp(entry: Mapping[str, Any]) -> float | None:
    """How recent an entry is: ``updated_ts``, else ``created_ts``."""
    updated = _float(entry.get("updated_ts"))
    return updated if updated is not None else _float(entry.get("created_ts"))


def _load_entry(entry: object) -> dict[str, Any] | None:
    """One persisted entry, validated per point (the slot is third-party input)."""
    if not isinstance(entry, Mapping) or _entry_stamp(entry) is None:
        return None
    nodes = entry.get("nodes")
    return {
        "created_ts": _float(entry.get("created_ts")),
        "updated_ts": _float(entry.get("updated_ts")),
        "state": _str(entry.get("state")),
        "template": _str(entry.get("template")),
        "nodes": [dict(n) for n in _mappings(nodes)],
    }


def _seen_entries(seen: object) -> dict[str, dict[str, Any]]:
    if not isinstance(seen, Mapping):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for key, raw in seen.items():
        entry = _load_entry(raw) if isinstance(key, str) else None
        if entry is not None:
            out[key] = entry
    return out


def merge_seen(seen: object, jobs: object, details: object, *,
               now_ts: float, cap: int | None, max_age_s: float) -> dict[str, Any]:
    """A **new** seen map: ``seen`` folded with this read of ``jobs``/``details``.

    An existing entry is replaced only by a read with a newer (or equal)
    ``updated_ts``; on an equal stamp a read that carries no node summary
    keeps the one already stored (the live tier reads details for
    executing jobs only).  Entries older than ``max_age_s`` -- by
    ``updated_ts``, else ``created_ts`` -- are dropped, then the newest
    ``cap`` are kept.  A ``seen`` that is not a mapping, and any entry that
    is not a stamped mapping, is treated as absent.  ``seen`` is never
    mutated.
    """
    out = _seen_entries(seen)
    dmap = _details_map(details)
    for job in _mappings(jobs):
        job_id = _str(job.get("id"))
        if job_id is None:
            continue
        entry = seen_entry(job, dmap.get(job_id))
        old = out.get(job_id)
        if old is not None:
            old_u, new_u = old["updated_ts"], entry["updated_ts"]
            if old_u is not None and (new_u is None or new_u < old_u):
                continue
            if new_u == old_u and not entry["nodes"] and old["nodes"]:
                entry["nodes"] = old["nodes"]
        out[job_id] = entry
    floor = now_ts - max_age_s
    kept = [
        (job_id, entry) for job_id, entry in out.items()
        if (_entry_stamp(entry) or float("-inf")) >= floor
    ]
    if cap is not None and len(kept) > cap:
        kept.sort(key=lambda kv: -(_entry_stamp(kv[1]) or float("-inf")))
        kept = kept[:cap]
    return dict(kept)


# -- Internal roster: default most-active seat selection ------------------


def _seat_nodes(details: object, seen: object):
    """Every ``(job_id, template, token, agent, node_summary)``.

    Detail nodes first; seen nodes only for jobs no detail covers, so a job
    read both ways is counted once.  Nodes whose seat is absent or whose
    token does not parse are skipped -- there is no seat to attribute to.
    """
    dmap = _details_map(details)
    for job_id, detail in dmap.items():
        template = _str(detail.get("template"))
        for node in _mappings(detail.get("nodes")):
            token, agent = _seat(node)
            if token is None:
                continue
            yield job_id, template, token, agent, _seen_node(node)
    for job_id, entry in _seen_entries(seen).items():
        if job_id in dmap:
            continue
        for summary in entry["nodes"]:
            token = parse_seat_token(summary.get("seat_token"))
            if token is None:
                continue
            yield job_id, entry["template"], token, _str(summary.get("seat_agent")), {
                "key": _str(summary.get("key")),
                "seat_token": token,
                "seat_agent": _str(summary.get("seat_agent")),
                "role": _str(summary.get("role")),
                "state": _str(summary.get("state")),
                "verdict_status": _str(summary.get("verdict_status")),
                "rejection_code": _str(summary.get("rejection_code")),
                "revisions": _int(summary.get("revisions")),
                "at_ts": _float(summary.get("at_ts")),
            }


def _scores_by_agent(details: object) -> dict[str, list[float]]:
    """``agentId -> [value, …]`` across every review entry in the details."""
    out: dict[str, list[float]] = {}
    for detail in _details_map(details).values():
        for review in _mappings(detail.get("reviews")):
            for entry in _mappings(review.get("entries")):
                agent, value = _str(entry.get("agentId")), _float(entry.get("value"))
                if agent is not None and value is not None:
                    out.setdefault(agent, []).append(value)
    return out


def seat_rows(details: object, seen: object) -> list[dict[str, Any]]:
    """Internal roster, one row per distinct seat token; never a payload key.

    Sorted by ``nodes`` desc, then ``last_active_ts`` desc, then token.
    ``mean_score``/``scored`` are over the review entries whose ``agentId``
    is this seat's agent (``None``/``0`` when there are none).
    """
    acc: dict[int, dict[str, Any]] = {}
    for job_id, _template, token, agent, summary in _seat_nodes(details, seen):
        row = acc.setdefault(token, {
            "agent": None, "agent_at": None, "nodes": 0, "jobs": set(),
            "roles": set(), "accepted": 0, "rejected": 0, "revisions": 0,
            "working": False, "last": None,
        })
        at = summary["at_ts"]
        if agent is not None and (row["agent"] is None
                                  or (at or float("-inf")) >= (row["agent_at"] or float("-inf"))):
            row["agent"], row["agent_at"] = agent, at
        row["nodes"] += 1
        row["jobs"].add(job_id)
        if summary["role"] is not None:
            row["roles"].add(summary["role"])
        if summary["verdict_status"] == "accepted":
            row["accepted"] += 1
        elif summary["verdict_status"] == "rejected":
            row["rejected"] += 1
        row["revisions"] += summary["revisions"] or 0
        row["working"] = row["working"] or summary["state"] == "working"
        if at is not None and (row["last"] is None or at > row["last"]):
            row["last"] = at
    scores = _scores_by_agent(details)
    rows: list[dict[str, Any]] = []
    for token, row in acc.items():
        values = scores.get(row["agent"], []) if row["agent"] is not None else []
        rows.append({
            "token_id": token,
            "agent_id": row["agent"],
            "nodes": row["nodes"],
            "jobs": len(row["jobs"]),
            "roles": sorted(row["roles"]),
            "accepted": row["accepted"],
            "rejected": row["rejected"],
            "revisions": row["revisions"],
            "mean_score": round(statistics.fmean(values), 2) if values else None,
            "scored": len(values),
            "working_now": row["working"],
            "last_active_ts": row["last"],
        })
    rows.sort(key=lambda r: (-r["nodes"], r["last_active_ts"] is None,
                             -(r["last_active_ts"] or 0.0), r["token_id"]))
    return rows


# -- AGENT body on /seats/{tokenId} (docs/surf_agent_seats_plan.md WP1b) -----
#
# The seat's lifetime record, read one token at a time by
# ``SwarmClient.fetch_seat``.  Pure like everything above: no clock, no I/O.
# Third-party strings (objective, node keys, roles, runtime, owner) are
# carried raw; escaping and address validation happen at the widget.
# ``agentId`` is carried as the decimal string ``/seats`` and ``/jobs`` serve
# (the roster's ``agent_id`` is the same ``str``); it is never parsed to int.

_ASCII_DIGITS = frozenset("0123456789")


def _seat_id(value: object) -> int | None:
    """A seat token: a non-negative, non-bool ``int``.  Nothing else parses."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _served_token(value: object) -> int | None:
    """``/seats``' ``tokenId``: a decimal string of ASCII digits only, or an int.

    Stricter than :func:`parse_seat_token`: no surrounding whitespace, since a
    served id is compared, not typed.
    """
    if isinstance(value, str):
        if not value or not _ASCII_DIGITS.issuperset(value):
            return None
        try:
            return int(value)
        except ValueError:  # Python's oversized decimal-string safety limit
            return None
    return _seat_id(value)


def _count(value: object) -> int | None:
    """A served counter: a non-negative, non-bool ``int``."""
    return _seat_id(value)


def _score(value: object) -> float | int | None:
    """A review ``value`` that is a finite real number and not a ``bool``."""
    number = _float(value)
    if number is None or not math.isfinite(number):
        return None
    return number


def _list(value: object) -> list | None:
    return value if isinstance(value, list) else None


def seat_state(payload: object, token: object) -> str | None:
    """``"unknown_seat"`` for the client's normalised 404, ``"ok"`` for a seat
    whose ``tokenId`` is ``token``, else ``None`` -- a ``tokenId`` mismatch
    included, so seat A's record never answers for seat B.

    ``"pending"`` is the manager's to say (no read has finished); a payload
    never is.
    """
    wanted = _seat_id(token)
    if wanted is None or not isinstance(payload, Mapping):
        return None
    if dict(payload) == dict(UNKNOWN_SEAT):
        return "unknown_seat"
    if "error" in payload or _served_token(payload.get("tokenId")) != wanted:
        return None
    return "ok"


def _runtime(runtimes: object) -> str | None:
    """``runtimes[0]`` as the raw ``"<id> <version>"`` (plan §1.1, §9 D).

    ``""`` for a served, **empty** list -- a seat that runs nothing (seat #0)
    is a real negative, not "could not look" (CLAUDE.md: never a false
    degradation).  ``None`` only when the source did not carry a usable list:
    absent, not a list, or a first entry with neither ``id`` nor ``version``.
    """
    listed = _list(runtimes)
    if listed is None:
        return None
    if not listed:
        return ""
    if not isinstance(listed[0], Mapping):
        return None
    parts = [p for p in (_str(listed[0].get("id")), _str(listed[0].get("version")))
             if p is not None]
    return " ".join(parts) if parts else None


def _hex64(value: object) -> str | None:
    """A complete off-chain submission hash, shared by work and review folds."""
    if (isinstance(value, str) and len(value) == 64
            and all(c in "0123456789abcdefABCDEF" for c in value)):
        return value
    return None


def _distinct_reviews(reviews: object) -> list[Mapping[str, Any]]:
    """Keep the most advanced entry per valid submission hash; ties keep first."""
    result: list[Mapping[str, Any]] = []
    positions: dict[str, int] = {}
    ranks = {"sent": 3, "submitted": 2, "queued": 1}
    for review in _mappings(reviews):
        key = _hex64(review.get("submissionHash"))
        if key is None:
            result.append(review)
            continue
        if key not in positions:
            positions[key] = len(result)
            result.append(review)
        else:
            index = positions[key]
            if ranks.get(_str(review.get("status")), 0) > ranks.get(_str(result[index].get("status")), 0):
                result[index] = review
    return result


def seat_summary_from_seat(payload: object) -> dict[str, Any]:
    """``swarm_seat_summary``: exactly :data:`SWARM_SEAT_SUMMARY_FIELDS`.

    Every field is ``None`` when the source did not carry it or carried the
    wrong type; a real zero stays ``0``. ``reviewed`` counts distinct submissions,
    pending ones included (Q-M); ``scored`` / ``mean_score`` count only a
    finite, non-bool ``value``. Win rate is lifetime accepted / attempts;
    zero or missing attempts is undefined.
    """
    summary: dict[str, Any] = dict.fromkeys(SWARM_SEAT_SUMMARY_FIELDS)
    if not isinstance(payload, Mapping):
        return summary
    reviews_raw = _list(payload.get("reviews"))
    work_raw = _list(payload.get("work"))
    reviews = _distinct_reviews(reviews_raw) if reviews_raw is not None else None
    work = _mappings(work_raw) if work_raw is not None else None
    summary["attempts"] = _count(payload.get("attempts"))
    summary["accepted"] = _count(payload.get("accepted"))
    attempts, accepted = summary["attempts"], summary["accepted"]
    if attempts is not None and attempts > 0 and accepted is not None and accepted <= attempts:
        summary["win_rate"] = accepted / attempts
    summary["agent_id"] = _str(payload.get("agentId"))
    summary["devices"] = _count(payload.get("devices"))
    if "daemonVersion" in payload:
        daemon = payload["daemonVersion"]
        summary["daemon"] = "" if daemon is None else _str(daemon)
    if reviews is not None:
        summary["reviewed"] = len(reviews)
        summary["review_entries"] = len(reviews_raw)
        statuses = [_str(r.get("status")) for r in reviews]
        summary["review_status"] = {s: statuses.count(s) for s in SWARM_SEAT_REVIEW_STATUSES}
        values = [v for v in (_score(r.get("value")) for r in reviews) if v is not None]
        summary["scored"] = len(values)
        summary["mean_score"] = round(statistics.fmean(values), 2) if values else None
        roles: dict[str, int] = {}
        for review in reviews:
            role = _str(review.get("role"))
            if role is not None:
                roles[role] = roles.get(role, 0) + 1
        summary["roles"] = [{"role": role, "count": n} for role, n in
                            sorted(roles.items(), key=lambda kv: (-kv[1], kv[0]))]
    online = payload.get("online")
    summary["online"] = online if isinstance(online, bool) else None
    summary["owner"] = _str(payload.get("owner"))
    summary["paired_ts"] = _ts(payload.get("pairedAt"))
    won_stamps = [_ts(w.get("acceptedAt")) for w in (work or [])]
    sent_stamps = [_ts(r.get("sentAt")) for r in _mappings(reviews_raw)]
    summary["last_won_ts"] = max((s for s in won_stamps if s is not None), default=None)
    summary["last_sent_ts"] = max((s for s in sent_stamps if s is not None), default=None)
    worked_stamps = [_ts(w.get("submittedAt")) for w in (work or [])]
    summary["last_worked_ts"] = max((s for s in worked_stamps if s is not None), default=None)
    collaborators = _list(payload.get("collaborators"))
    summary["collaborators"] = len(collaborators) if collaborators is not None else None
    summary["runtime"] = _runtime(payload.get("runtimes"))
    return summary


def seat_work_rows(payload: object) -> list[dict[str, Any]]:
    """``swarm_seat_work_rows``: one row per ``work[]`` entry, in source order
    (newest first as served). ``launch`` is None when absent/null; the off-chain
    submission hash is accepted only as 64 ASCII hex characters. ``[]`` when
    there is nothing to fold."""
    if not isinstance(payload, Mapping):
        return []
    keys = SURF_ROW_KEYS["swarm_seat_work_rows"]
    rows = []
    for work in _mappings(_list(payload.get("work"))):
        submission_hash = _hex64(work.get("submissionHash"))
        row = {
            "job_id": _str(work.get("jobId")),
            "node_key": _str(work.get("nodeKey")),
            "role": _str(work.get("role")),
            "job_state": _str(work.get("jobState")),
            "work_status": _str(work.get("status")),
            "objective": _str(work.get("objective")),
            "accepted_ts": _ts(work.get("acceptedAt")),
            "submitted_ts": _ts(work.get("submittedAt")),
            "launch": _str(work.get("launch")),
            "submission_hash": submission_hash,
            "answer": None, "answer_state": "not_read", "model": None, "took_s": None,
            "output_tokens": None,
            "panel_state": "not_read" if work.get("nodeKey") in SWARM_ORACLE_NODE_KEYS else "not_oracle",
            "panel_agreed": None, "panel_quorum": None, "panel_size": None,
            "panel_figure": None, "panel_answer_type": None, "panel_answer_bool": None,
            "oracle_question": None, "oracle_chain_id": None, "oracle_member_ok": None,
            "oracle_member_reason": None, "oracle_seat_answer": None, "oracle_notes": None,
        }
        rows.append({key: row[key] for key in keys})
    return rows


def seat_node_rows(payload: object) -> list[dict[str, Any]] | None:
    """Nodes from reviews and work, sorted reviewed desc, accepted desc, key asc.

    ``accepted`` / ``attempts`` are per node what the hero's ACCEPTED is per
    seat. Since 2026-09-22 ``work[]`` lists every attempt with a ``status``
    (accepted, pending, rejected, failed); before, it held accepted work only
    and carried no status. So ``accepted`` counts ``status == "accepted"`` and
    every entry with no status at all; ``attempts`` counts every
    entry, but only when every entry carries a status -- under the old shape
    per-node attempts were not served, and ``attempts`` is ``None``.
    Work-only nodes keep reviewed zero. Onchain counts sent/submitted reviews
    carrying a tx hash. Both source lists must be served; a missing list
    makes the rows unavailable.
    """
    if (not isinstance(payload, Mapping) or not isinstance(payload.get("reviews"), list)
            or not isinstance(payload.get("work"), list)):
        return None
    work_items = _mappings(_list(payload.get("work")))
    attempts_served = all(isinstance(item.get("status"), str) for item in work_items)
    nodes: dict[str, dict[str, Any]] = {}
    for source in ("reviews", "work"):
        items = (_distinct_reviews(_list(payload.get(source))) if source == "reviews"
                 else _mappings(_list(payload.get(source))))
        for item in items:
            key = _str(item.get("nodeKey"))
            if key is None:
                continue
            row = nodes.setdefault(key, {
                "node_key": key, "roles": [], "reviewed": 0,
                "attempts": 0 if attempts_served else None, "accepted": 0,
                "onchain": 0, "queued": 0,
            })
            role = _str(item.get("role"))
            if role is not None and role not in row["roles"]:
                row["roles"].append(role)
            if source == "work":
                if row["attempts"] is not None:
                    row["attempts"] += 1
                status = item.get("status")
                if status is None or status == "accepted":
                    row["accepted"] += 1
            else:
                row["reviewed"] += 1
                status = item.get("status")
                if status in ("sent", "submitted") and _str(item.get("txHash")):
                    row["onchain"] += 1
                if status == "queued":
                    row["queued"] += 1
    for row in nodes.values():
        row["roles"].sort()
    return sorted(nodes.values(), key=lambda row: (-row["reviewed"], -row["accepted"], row["node_key"]))


def seat_teammates(payload: object) -> list[dict[str, Any]] | None:
    """Collaborators by shared jobs desc, integer token asc; None if not carried.

    Empty/malformed-only lists are real empty results. Drop members without
    a strict served token or a nonnegative integer sharedJobs count.
    """
    members = _list(payload.get("collaborators")) if isinstance(payload, Mapping) else None
    if members is None:
        return None
    rows = []
    for member in _mappings(members):
        token = _served_token(member.get("tokenId"))
        shared = _count(member.get("sharedJobs"))
        if token is None or shared is None:
            continue
        rows.append({"token_id": token, "agent_id": _str(member.get("agentId")),
                     "shared_jobs": shared})
    return sorted(rows, key=lambda row: (-row["shared_jobs"], row["token_id"]))


def _selected(token: int, agent: object, how: str) -> dict[str, Any]:
    picked = {"token_id": token, "agent_id": _str(agent), "selected_by": how}
    return {key: picked[key] for key in SWARM_SEAT_SELECTED_FIELDS}


def choose_seat(rows: object, saved_token: object) -> dict[str, Any] | None:
    """Saved seat, even off the roster; otherwise the most-active internal row.

    With no rows and no saved seat, return None. A token is a nonnegative,
    non-bool int. The manager fills an absent agent ID from the seat read.
    """
    seats = [r for r in _mappings(rows) if _seat_id(r.get("token_id")) is not None]
    by_token = {r["token_id"]: r for r in reversed(seats)}   # first row wins
    saved = _seat_id(saved_token)
    if saved is not None:
        row = by_token.get(saved)
        return _selected(saved, row.get("agent_id") if row else None, "saved")
    if seats:
        return _selected(seats[0]["token_id"], seats[0].get("agent_id"), "most_active")
    return None


#: A persisted seat slot is a *finished* read: ``pending`` is never stored.
_SLOT_STATES = tuple(s for s in SWARM_SEAT_STATES if s != "pending")


def coerce_seat_slot(payload: object) -> dict[str, Any] | None:
    """The persisted ``{token, state, seat}`` slot, validated per field, or
    ``None`` -- the slot is discarded, never half-trusted.

    ``token`` a non-negative non-bool ``int``; ``state`` ``ok`` or
    ``unknown_seat``; ``seat`` a dict whose ``tokenId`` is ``token`` for
    ``ok``, and ``None`` for ``unknown_seat``.
    """
    if not isinstance(payload, Mapping):
        return None
    token = _seat_id(payload.get("token"))
    state = payload.get("state")
    seat = payload.get("seat")
    if token is None or state not in _SLOT_STATES:
        return None
    if state == "unknown_seat":
        if seat is not None:
            return None
    elif not isinstance(seat, dict) or seat_state(seat, token) != "ok":
        return None
    return {"token": token, "state": state, "seat": seat}


# -- BOARD: normalized source slots and pure folds --------------------------
# Endpoint admission drops malformed rows. Persisted normalized slots are a
# different trust boundary: coerce_* rejects a malformed slot as a whole rather
# than quietly changing its counts. The manager normalizes at fetch, validates
# at load/consumption and uses the *_from_slot(s) helpers without parsing twice.

_CONTRIBUTOR_COUNTERS = {
    "attempts": "attempts", "accepted": "accepted", "rejected": "rejected",
    "pending": "pending", "turns": "turns", "wall_clock_ms": "wallClockMs",
    "input_tokens": "inputTokens", "output_tokens": "outputTokens",
    "cached_input_tokens": "cachedInputTokens",
}


_CONTRIBUTOR_REQUIRED = ("attempts", "accepted", "rejected", "pending", "turns", "wall_clock_ms")


def _string_list(value: object) -> list[str] | None:
    return list(value) if isinstance(value, list) and all(isinstance(v, str) for v in value) else None


def normalize_contributors(payload: object) -> dict[str, Any] | None:
    """Admit displayed attempts/accepted/rejected/pending/turns/wallClockMs.

    Device identity is required; undisplayed inputTokens/outputTokens/
    cachedInputTokens are optional None. A valid token with an inadmissible
    row is remembered, never relabelled absent. Missing lists remain unread.
    """
    if not isinstance(payload, Mapping) or not isinstance(payload.get("contributors"), list):
        return None
    rows = []
    malformed_tokens: set[int] = set()
    for source in _mappings(payload["contributors"]):
        token = _served_token(source.get("tokenId"))
        device = _str(source.get("deviceKey"))
        counts = {name: _served_token(source.get(field)) for name, field in _CONTRIBUTOR_COUNTERS.items()}
        if token is None:
            continue
        if not device or any(counts[field] is None for field in _CONTRIBUTOR_REQUIRED):
            malformed_tokens.add(token)
            continue
        rows.append({"device_key": device, "token_id": token, **counts})
    return {
        "receipts": _served_token(payload.get("receipts")),
        "tokens_per_completed_job": _served_token(payload.get("tokensPerCompletedJob")),
        "contributors": rows,
        "malformed_tokens": sorted(malformed_tokens),
    }


def _advertised_models(runtimes: object) -> list[dict]:
    pairs = set()
    for runtime in _mappings(runtimes):
        premium = runtime.get("premiumModel")
        if isinstance(premium, Mapping):
            model = _str(premium.get("model"))
            if model:
                pairs.add((model, _str(premium.get("effort")) or None))
    return [{"model": model, "effort": effort}
            for model, effort in sorted(pairs, key=lambda pair: (pair[0], pair[1] or ""))]


def _valid_advertised_models(value: object) -> bool:
    return (isinstance(value, list) and all(
        isinstance(pair, Mapping) and set(pair) == {"model", "effort"}
        and isinstance(pair["model"], str) and bool(pair["model"])
        and (pair["effort"] is None or isinstance(pair["effort"], str) and bool(pair["effort"]))
        for pair in value))


def normalize_workers(payload: object) -> dict[str, Any] | None:
    """Keep every valid-token worker; other malformed fields remain unknown.

    pause_known distinguishes served null from missing/malformed pause data.
    Only a complete until/failures pair establishes a pause. Unknown counters
    must not become zeros; LIVE remains the independent served count.
    """
    if not isinstance(payload, Mapping) or not isinstance(payload.get("workers"), list):
        return None
    rows = []
    for source in _mappings(payload["workers"]):
        seat = source.get("seat")
        if not isinstance(seat, Mapping):
            continue
        token = _served_token(seat.get("tokenId"))
        device = _str(source.get("deviceKey")) or None
        working = _served_token(source.get("working"))
        capacity = _served_token(source.get("maxConcurrency"))
        if token is None:
            continue
        until = failures = None
        pause = source.get("paused")
        pause_known = "paused" in source and pause is None
        if isinstance(pause, Mapping):
            until = _ts(pause.get("until"))
            failures = _served_token(pause.get("consecutiveFailures"))
            pause_known = until is not None and failures is not None
            if not pause_known:
                until = failures = None
        runtime_source = source.get("runtimes")
        runtimes = None
        if (isinstance(runtime_source, list)
                and all(isinstance(r, Mapping) and isinstance(r.get("id"), str) for r in runtime_source)):
            runtimes = [r["id"] for r in runtime_source]
        platform = source.get("platform")
        os = _str(platform.get("os")) if isinstance(platform, Mapping) else None
        arch = _str(platform.get("arch")) if isinstance(platform, Mapping) else None
        rows.append({
            "device_key": device, "token_id": token, "agent_id": _str(seat.get("agentId")),
            "working": working, "max_concurrency": capacity,
            "paused_until_ts": until, "failures": failures, "pause_known": pause_known,
            "heartbeat_ts": _ts(source.get("lastHeartbeatAt")),
            "runtimes": runtimes, "daemon": _str(source.get("daemonVersion")),
            "advertised_models": _advertised_models(runtime_source),
            "profiles": _string_list(source.get("profiles")),
            "skills": _string_list(source.get("skills")), "os": os,
            "platform": f"{os} {arch}" if os is not None and arch is not None else None,
        })
    return {"count": _served_token(payload.get("count")), "workers": rows, "malformed_tokens": []}


def _valid_count(value: object) -> bool:
    return _seat_id(value) is not None


def _valid_malformed_tokens(value: object) -> bool:
    return (isinstance(value, list) and all(_valid_count(token) for token in value)
            and value == sorted(set(value)))


def _optional_count(value: object) -> bool:
    return value is None or _valid_count(value)


def _optional_string(value: object) -> bool:
    return value is None or isinstance(value, str)


def _optional_strings(value: object) -> bool:
    return value is None or _string_list(value) is not None


def _optional_stamp(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _coerce_board_slot(payload: object, member: str, fields: dict, row_fields: dict) -> dict | None:
    if not isinstance(payload, Mapping) or set(payload) != {*fields, member}:
        return None
    if not all(check(payload[key]) for key, check in fields.items()):
        return None
    if not isinstance(payload[member], list):
        return None
    rows = []
    for row in payload[member]:
        if not isinstance(row, Mapping) or set(row) != set(row_fields):
            return None
        if not all(check(row[key]) for key, check in row_fields.items()):
            return None
        rows.append({key: list(value) if isinstance(value, list) else value for key, value in row.items()})
    return {**{key: list(payload[key]) if isinstance(payload[key], list) else payload[key]
               for key in fields}, member: rows}


def coerce_contributors_slot(payload: object) -> dict[str, Any] | None:
    """Validate every normalized field; cached decimal strings are not re-parsed."""
    return _coerce_board_slot(payload, "contributors", {
        "receipts": _optional_count, "tokens_per_completed_job": _optional_count,
        "malformed_tokens": _valid_malformed_tokens,
    }, {"device_key": lambda v: isinstance(v, str) and bool(v), "token_id": _valid_count,
        **{field: _valid_count if field in _CONTRIBUTOR_REQUIRED else _optional_count
           for field in _CONTRIBUTOR_COUNTERS}})


def coerce_workers_slot(payload: object) -> dict[str, Any] | None:
    """Validate every normalized worker field and the paired pause timestamp/count."""
    result = _coerce_board_slot(payload, "workers", {
        "count": _optional_count, "malformed_tokens": _valid_malformed_tokens,
    }, {
        "device_key": _optional_string, "token_id": _valid_count,
        "agent_id": _optional_string, "working": _optional_count, "max_concurrency": _optional_count,
        "pause_known": lambda value: isinstance(value, bool),
        "paused_until_ts": _optional_stamp, "failures": _optional_count,
        "heartbeat_ts": _optional_stamp, "runtimes": _optional_strings,
        "daemon": _optional_string, "profiles": _optional_strings, "skills": _optional_strings,
        "os": _optional_string, "platform": _optional_string,
        "advertised_models": _valid_advertised_models,
    })
    if result is not None and any(
        (row["paused_until_ts"] is None) != (row["failures"] is None)
        or (not row["pause_known"] and row["paused_until_ts"] is not None)
        for row in result["workers"]
    ):
        return None
    return result


def _worker_groups(slot: dict | None) -> dict[int, list[dict]]:
    groups: dict[int, list[dict]] = {}
    for row in slot["workers"] if slot is not None else []:
        groups.setdefault(row["token_id"], []).append(row)
    return groups


def _metadata_union(rows: list[dict], field: str) -> list[str] | None:
    if any(row[field] is None for row in rows):
        return None
    return sorted({value for row in rows for value in row[field]})


def _sum_known(values) -> int | None:
    values = list(values)
    return None if any(value is None for value in values) else sum(values)


def _contributor_tokens(slot: dict) -> set[int]:
    return {row["token_id"] for row in slot["contributors"]} | set(slot["malformed_tokens"])


def _live_for_workers(rows: list[dict]) -> dict[str, Any]:
    live = dict.fromkeys(SWARM_SEAT_LIVE_FIELDS)
    live.update(live=bool(rows), working=_sum_known(row["working"] for row in rows),
                max_concurrency=_sum_known(row["max_concurrency"] for row in rows), devices=len(rows))
    if not rows:
        live["live_state"] = "offline"
        return live
    pairs = sorted({(pair["model"], pair["effort"]) for row in rows
                    for pair in row["advertised_models"]}, key=lambda pair: (pair[0], pair[1] or ""))
    if pairs:
        live["advertised_model"] = ", ".join(pair[0] for pair in pairs)
        live["advertised_effort"] = ", ".join(pair[1] or "—" for pair in pairs)
    paused = [row for row in rows if row["paused_until_ts"] is not None]
    if paused:
        chosen = min(paused, key=lambda row: (row["paused_until_ts"], row["device_key"] or ""))
        live["paused_until_ts"], live["failures"] = chosen["paused_until_ts"], chosen["failures"]
    live["heartbeat_ts"] = max((row["heartbeat_ts"] for row in rows if row["heartbeat_ts"] is not None), default=None)
    skills = _metadata_union(rows, "skills")
    live["skills"] = len(skills) if skills is not None else None
    live["profiles"] = _metadata_union(rows, "profiles")
    if all(row["platform"] is not None for row in rows):
        live["platform"] = ", ".join(sorted({row["platform"] for row in rows}))
    live["live_state"] = _live_state(live, rows)
    return live


def _live_state(live: dict, rows: list[dict]) -> str | None:
    if not live["live"]:
        return "offline"
    if any(row["working"] is not None and row["working"] > 0 for row in rows):
        return "working"
    if live["paused_until_ts"] is not None:
        return "paused"
    return "idle" if all(row["working"] == 0 and row["pause_known"] for row in rows) else None


def _runtime_bucket(values: list[str] | None) -> str | None:
    if values is None:
        return None
    names = set(values)
    return "both" if names == {"codex", "claude"} else "+".join(sorted(names)) or "none"


def _seconds(milliseconds: int) -> float | None:
    try:
        value = milliseconds / 1000
        return value if math.isfinite(value) else None
    except OverflowError:
        return None


def _board_rows_from_slots(contributors: dict | None, workers: dict | None) -> list[dict] | None:
    if contributors is None:
        return None
    grouped: dict[int, dict] = {}
    malformed_tokens = set(contributors["malformed_tokens"])
    for row in contributors["contributors"]:
        if row["token_id"] in malformed_tokens:
            continue
        counts = grouped.setdefault(row["token_id"], {"devices": set(), **dict.fromkeys(_CONTRIBUTOR_COUNTERS, 0)})
        counts["devices"].add(row["device_key"])
        for field in _CONTRIBUTOR_COUNTERS:
            counts[field] = _sum_known((counts[field], row[field]))
    live_groups = _worker_groups(workers)
    result = []
    for token, counts in grouped.items():
        live_rows = live_groups.get(token, [])
        live = _live_for_workers(live_rows) if workers is not None else None
        try:
            rate = counts["accepted"] / counts["attempts"] if counts["attempts"] else None
        except OverflowError:
            rate = None
        row = {
            "rank": None, "token_id": token,
            "agent_id": next((row["agent_id"] for row in sorted(live_rows, key=lambda row: row["device_key"] or "")
                              if row["agent_id"] is not None), None),
            "devices": len(counts["devices"]),
            "runtime": (_runtime_bucket(_metadata_union(live_rows, "runtimes")) if live_rows
                        else "offline" if workers is not None else None),
            **{field: counts[field] for field in ("attempts", "accepted", "rejected", "pending")},
            "accept_rate": rate, "turns": counts["turns"], "wall_clock_s": _seconds(counts["wall_clock_ms"]),
            "live_state": _live_state(live, live_rows) if live is not None else None,
            "working": live["working"] if live is not None else None,
            "paused_until_ts": live["paused_until_ts"] if live is not None else None,
            "failures": live["failures"] if live is not None else None,
        }
        result.append(row)
    result.sort(key=lambda row: (-row["accepted"], row["accept_rate"] is None,
                                 -(row["accept_rate"] or 0), row["token_id"]))
    for rank, row in enumerate(result, 1):
        row["rank"] = rank if not malformed_tokens else None
    return result


def board_rows(contributors: object, workers: object) -> list[dict] | None:
    """One row per contributor seat; workers enrich metadata, never the counters."""
    return _board_rows_from_slots(normalize_contributors(contributors), normalize_workers(workers))


def _board_summary_from_slots(contributors: dict | None, workers: dict | None) -> dict:
    summary = dict.fromkeys(SWARM_BOARD_SUMMARY_FIELDS)
    if contributors is not None:
        rows = contributors["contributors"]
        summary["seats"] = len(_contributor_tokens(contributors))
        if not contributors["malformed_tokens"]:
            for field in ("attempts", "accepted", "rejected", "pending", "turns", "wall_clock_ms"):
                summary[field] = sum(row[field] for row in rows)
            for field in ("input_tokens", "output_tokens"):
                summary[field] = _sum_known(row[field] for row in rows)
            summary["devices"] = len(rows)
        summary["receipts"] = contributors["receipts"]
        summary["tokens_per_completed_job"] = contributors["tokens_per_completed_job"]
    if workers is not None:
        rows = workers["workers"]
        summary["live"] = workers["count"]
        summary["paused"] = len({row["token_id"] for row in rows if row["paused_until_ts"] is not None})
        summary["capacity"] = _sum_known(row["max_concurrency"] for row in rows)
        summary["working"] = _sum_known(row["working"] for row in rows)
    return summary


def board_summary(contributors: object, workers: object) -> dict:
    """Hero facts; each unread source leaves only its own fields unavailable."""
    return _board_summary_from_slots(normalize_contributors(contributors), normalize_workers(workers))


def _mix(values) -> list[dict]:
    counts: dict[str, int] = {}
    for value in values:
        if value is not None:
            counts[value] = counts.get(value, 0) + 1
    return [{"value": value, "count": count} for value, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))]


def _fleet_from_slot(slot: dict | None) -> dict | None:
    if slot is None:
        return None
    rows = slot["workers"]
    result = dict.fromkeys(SWARM_FLEET_FIELDS)
    result.update(
        runtimes=_mix(_runtime_bucket(row["runtimes"]) for row in rows),
        daemons=_mix(row["daemon"] for row in rows), os=_mix(row["os"] for row in rows),
        profiles=_mix("+".join(sorted(set(row["profiles"]))) or "none" if row["profiles"] is not None else None for row in rows),
        concurrency=_mix(str(row["max_concurrency"]) for row in rows if row["max_concurrency"] is not None),
    )
    model_counts: dict[tuple, int] = {}
    for row in rows:
        pairs = {(pair["model"], pair["effort"]) for pair in row["advertised_models"]} or {(None, None)}
        for pair in pairs:
            model_counts[pair] = model_counts.get(pair, 0) + 1
    result["models"] = [{"model": model, "effort": effort, "count": count}
                        for (model, effort), count in sorted(model_counts.items(),
                            key=lambda item: (-item[1], item[0][0] or "", item[0][1] or ""))]
    stamps = [row["heartbeat_ts"] for row in rows if row["heartbeat_ts"] is not None]
    result["heartbeat_oldest_ts"] = min(stamps, default=None)
    result["heartbeat_newest_ts"] = max(stamps, default=None)
    paused = []
    for token, devices in _worker_groups(slot).items():
        live = _live_for_workers(devices)
        if live["paused_until_ts"] is not None:
            paused.append({"token_id": token, "until_ts": live["paused_until_ts"], "failures": live["failures"]})
    result["paused"] = sorted(paused, key=lambda row: (row["until_ts"], row["token_id"]))
    return result


def fleet(workers: object) -> dict | None:
    """Worker-only mixes, heartbeat bounds, and one paired pause fact per seat."""
    return _fleet_from_slot(normalize_workers(workers))


def _seat_live_from_slot(workers: dict | None, token: object) -> dict | None:
    wanted = _seat_id(token)
    if workers is None or wanted is None or wanted in workers["malformed_tokens"]:
        return None
    return _live_for_workers(_worker_groups(workers).get(wanted, []))


def seat_live(workers: object, token: object) -> dict | None:
    """Selected token's live state; None unread, live=False absent after a read."""
    return _seat_live_from_slot(normalize_workers(workers), token)


def _seat_contrib_from_rows(rows: list[dict] | None, token: object, contributors: dict | None) -> dict | None:
    wanted = _seat_id(token)
    if (rows is None or wanted is None or contributors is None
            or wanted in contributors["malformed_tokens"]):
        return None
    result = dict.fromkeys(SWARM_SEAT_CONTRIB_FIELDS)
    result["listed"] = False
    selected = next((row for row in rows if row["token_id"] == wanted), None)
    if selected is not None:
        result.update(listed=True, ranked_of=len(_contributor_tokens(contributors)))
        for field in ("attempts", "accepted", "rejected", "pending", "turns", "wall_clock_s", "rank"):
            result[field] = selected[field]
    return result


def seat_contrib(contributors: object, token: object) -> dict | None:
    """Selected token's lifetime contributor counters, independent of /seats."""
    slot = normalize_contributors(contributors)
    return _seat_contrib_from_rows(_board_rows_from_slots(slot, None), token, slot)


# ---- Selected RECORD answers: cleaned fields, never raw submission payloads ----


#: Parse only a first-sentence-sized prefix of untrusted summaries. At most eight
#: shrinking cleanup passes; pathological nesting that does not settle is empty.
#: Empty is already a fixed point, so the bound cannot return a half-cleaned value.
ANSWER_TEXT_CAP = 4096
_ANSWER_STRIP_PASSES = 8


def _answer_link_spans(text: str) -> list[tuple[int, int, int]]:
    """Opening label bracket, closing bracket, target end; two linear scans.

    Parenthesis pairs are indexed once. Unclosed targets consume the remaining
    suffix, never trigger another suffix scan. Nested label links remain visible
    to the bracket stack; targets are skipped as a whole.
    """
    parentheses: list[int] = []
    ends = {}
    for index, char in enumerate(text):
        if char == '(':
            parentheses.append(index)
        elif char == ')' and parentheses:
            ends[parentheses.pop()] = index + 1
    brackets: list[int] = []
    spans = []
    index = 0
    while index < len(text):
        char = text[index]
        if char == '[':
            brackets.append(index)
        elif char == ']' and brackets:
            opening = brackets.pop()
            if index + 1 < len(text) and text[index + 1] == '(':
                end = ends.get(index + 1, len(text))
                spans.append((opening, index, end))
                index = end
                continue
        index += 1
    return spans


def _strip_answer_links(text: str) -> str:
    removed = bytearray(len(text))
    for opening, closing, end in _answer_link_spans(text):
        removed[opening] = 1
        removed[closing:end] = b'\1' * (end - closing)
    return ''.join(char for index, char in enumerate(text) if not removed[index])


# One detector is shared by cleaning and persisted-answer safety. HTTP(S) is
# consumed first so its slash components can never be mistaken for local paths.
# Bare home usernames may contain spaces up to the next separator/end/delimiter;
# the prose conjunctions and/or/but/then end an undelimited home path. Quoted
# paths have an exact delimiter and need no such boundary convention.
_HOME_PREFIX = r'(?:/home/|/Users/|[A-Za-z]:[\\/]Users[\\/])'
_HOME_USER = r'''[^\s/\\<>"'`]+(?:[ ]+(?!(?:and|or|but|then)\b)[^\s/\\<>"'`]+)*'''
_ANSWER_PATH_PATTERN = re.compile(
    r'''(?P<url>https?://[^\s<>"'`]+)|'''
    r'''(?P<quoted>(?P<quote>["'`])(?P<qpath>(?:file://|[A-Za-z]:[\\/]|/)[^\r\n]*?)(?P=quote))|'''
    r'''(?P<path>(?<!\w)(?:file://(?:[^/\s]+)?(?=/))?(?:'''
    + _HOME_PREFIX + _HOME_USER + r'''(?:[\\/][^\s<>"'`]*)?'''
    + r'''|(?:[A-Za-z]:[\\/]|/)[^\s<>"'`]*))''', re.IGNORECASE,
)


def _answer_paths(text: str):
    return (match for match in _ANSWER_PATH_PATTERN.finditer(text) if match.group('url') is None)


def _path_basename(raw: str) -> str:
    path = re.sub(r'^file://(?:[^/]+)?(?=/)', '', raw, flags=re.IGNORECASE)
    clean = path.rstrip('.,!?;:)]}')
    parts = [part for part in re.split(r'[/\\]', clean.rstrip('/\\')) if part]
    # Home roots never expose the user segment as if it were a filename.
    home_root = (len(parts) == 2 and parts[0].lower() in ('home', 'users')
                 or len(parts) == 1 and parts[0].lower() == 'root'
                 or len(parts) == 3 and re.fullmatch(r'[A-Za-z]:', parts[0]) is not None
                 and parts[1].lower() == 'users')
    name = '~' if home_root or not parts else parts[-1]
    return name + path[len(clean):]


def _strip_answer_paths(text: str) -> str:
    pieces = []
    cursor = 0
    for match in _answer_paths(text):
        pieces.append(text[cursor:match.start()])
        quote = match.group('quote') or ''
        pieces.append(quote + _path_basename(match.group('qpath') or match.group('path')) + quote)
        cursor = match.end()
    pieces.append(text[cursor:])
    return ''.join(pieces)


def _safe_stored_answer(value: object) -> bool:
    """Safety only: do not re-derive a stored answer's display formatting."""
    return (isinstance(value, str) and 0 < len(value) <= ANSWER_TEXT_CAP
            and not any(ord(char) < 32 or 127 <= ord(char) < 160 for char in value)
            and not _answer_link_spans(value) and next(_answer_paths(value), None) is None)


def answer_sentence(summary: str) -> str:
    """Bounded, idempotent link/path/Markdown cleanup; newline precedes flattening."""
    text = summary[:ANSWER_TEXT_CAP]
    for _ in range(_ANSWER_STRIP_PASSES):
        previous = text
        text = _strip_answer_links(text)
        text = re.sub(r'(?m)^\s*```[^\n]*\n?', '', text)
        text = _strip_answer_paths(text)
        text = text.replace('`', '').replace('**', '').replace('__', '').replace('*', '')
        text = re.sub(r'(?m)^(?:\s*(?:[-+•]|\d+[.)])\s+)+', '', text)
        first = re.split(r'(?<=[.!?])\s+|[\r\n]+', text.strip(), maxsplit=1)[0]
        text = ' '.join(first.split())
        text = ''.join(char for char in text if not (ord(char) < 32 or 127 <= ord(char) < 160))
        if text == previous:
            return text
    return ''



def submission_answer(payload: object, job_id: object, submission_hash: object, token: object) -> dict:
    """Select only the exact job/hash/seat; distinguish failure, absence and no reply."""
    result = dict.fromkeys(SWARM_ANSWER_FIELDS)
    result['state'] = 'unavailable'
    if parse_job_id(job_id) is None or _hex64(submission_hash) is None or _seat_id(token) is None:
        return result
    if payload == SUBMISSIONS_NOT_FOUND:
        result['state'] = 'not_served'
        return result
    if (not isinstance(payload, Mapping) or payload.get('jobId') != job_id
            or not isinstance(payload.get('submissions'), list)):
        return result
    matches = [row for row in _mappings(payload['submissions']) if row.get('hash') == submission_hash]
    if not matches:
        result['state'] = 'not_served'
        return result
    item = matches[0]
    if any(other != item for other in matches[1:]):
        return result
    if 'seat' in item:
        seat = item['seat']
        if not isinstance(seat, Mapping) or _served_token(seat.get('tokenId')) != token:
            return result
    if 'summary' not in item or item['summary'] is not None and not isinstance(item['summary'], str):
        return result
    answer = answer_sentence(item['summary'] or '')
    result.update(answer=answer or None, state='read' if answer else 'no_reply')
    usage = item.get('usage')
    if isinstance(usage, Mapping):
        result['model'] = _str(usage.get('model'))
        tokens = usage.get('outputTokens')
        result['output_tokens'] = tokens if type(tokens) is int and tokens >= 0 else None
        milliseconds = _served_token(usage.get('wallClockMs'))
        result['took_s'] = _seconds(milliseconds) if milliseconds is not None else None
    return result


def _nonnegative_finite(value: object) -> bool:
    return value is not None and _optional_stamp(value) and value >= 0


def coerce_answers_slot(payload: object) -> dict | None:
    """Drop unsafe points independently; retain every valid cached sibling."""
    if not isinstance(payload, Mapping):
        return None
    result = {}
    for job, submissions in payload.items():
        if parse_job_id(job) is None or not isinstance(submissions, Mapping) or not submissions:
            continue
        clean = {}
        for key, point in submissions.items():
            if (_hex64(key) is None or not isinstance(point, Mapping)
                    or set(point) != set(SWARM_ANSWER_CACHE_FIELDS)):
                continue
            answer, state = point['answer'], point['state']
            if (state not in SWARM_ANSWER_STATES or state == 'not_read'
                    or not isinstance(point['terminal'], bool)
                    or not _nonnegative_finite(point['read_ts'])
                    or not _optional_string(point['model'])
                    or point['output_tokens'] is not None and not (type(point['output_tokens']) is int and point['output_tokens'] >= 0)
                    or point['took_s'] is not None and not _nonnegative_finite(point['took_s'])):
                continue
            if state == 'read':
                if not _safe_stored_answer(answer):
                    continue
            elif answer is not None:
                continue
            if state in ('not_served', 'unavailable') and (point['model'] is not None or point['took_s'] is not None or point['output_tokens'] is not None):
                continue
            clean[key] = {field: point[field] for field in SWARM_ANSWER_CACHE_FIELDS}
            if state == 'unavailable':
                clean[key]['terminal'] = False  # repair ambiguous legacy frozen failures
            elif state == 'not_served':
                clean[key]['terminal'] = True   # successful absence is a final answer
        if clean:
            result[job] = clean
    return result


def prune_answers(payload: object, *, now_ts: float, cap: int, max_age_s: float) -> dict:
    """Keep the newest bounded points, with age/future checks against injected time."""
    valid = coerce_answers_slot(payload) or {}
    points = [(job, key, point) for job, items in valid.items() for key, point in items.items()
              if 0 <= now_ts - point['read_ts'] <= max_age_s]
    points.sort(key=lambda item: (-item[2]['read_ts'], item[0], item[1]))
    result: dict[str, dict] = {}
    for job, key, point in points[:max(0, cap)]:
        result.setdefault(job, {})[key] = point
    return result


def enrich_work_rows(rows: list[dict], answers: object) -> list[dict]:
    """Use only exact displayed row identities; revalidate even an in-memory slot."""
    valid = coerce_answers_slot(answers) or {}
    result = []
    for row in rows:
        item = dict(row)
        job, key = row['job_id'], row['submission_hash']
        if parse_job_id(job) is None or _hex64(key) is None:
            item['answer_state'] = 'unavailable'
        elif point := valid.get(job, {}).get(key):
            item.update(answer=point['answer'], answer_state=point['state'],
                        model=point['model'], took_s=point['took_s'], output_tokens=point['output_tokens'])
        result.append(item)
    return result


def answer_jobs_due(rows: list[dict], answers: dict, *, now_ts: float, due_s: float, cap: int) -> list[tuple[str, list[dict]]]:
    """Unread rows first in displayed order; due retries by oldest attempt.

    Group by job so multiple selected submission hashes cost one request. Only
    the first displayed window is eligible; terminal points never re-read while
    retained. Transient unavailable points retry after the normal due interval.
    """
    groups: dict[str, list[dict]] = {}
    priorities = {}
    for index, row in enumerate(rows[:SWARM_ANSWER_ROW_CAP]):
        job, key = row['job_id'], row['submission_hash']
        if parse_job_id(job) is None or _hex64(key) is None:
            continue
        point = answers.get(job, {}).get(key)
        if point is not None and (point['terminal'] or now_ts - point['read_ts'] < due_s):
            continue
        priority = (0, index, index) if point is None else (1, point['read_ts'], index)
        groups.setdefault(job, []).append(row)
        priorities[job] = min(priorities.get(job, priority), priority)
    return [(job, groups[job]) for job in sorted(groups, key=priorities.get)[:cap]]


# ---- Oracle panels: exact submission identities, extracted facts only ------
_ORACLE_FINAL = frozenset(('attested', 'disagreed', 'blocked', 'off_panel'))
_ORACLE_FIGURE = re.compile(r'-?[0-9]{1,80}(\.[0-9]{1,40})?')


def _oracle_count(value: object) -> int | None:
    return value if type(value) is int and value >= 0 else None


def _oracle_figure(value: object) -> str | None:
    return value if isinstance(value, str) and _ORACLE_FIGURE.fullmatch(value) else None


def oracle_empty_point(status: str | None, *, now_ts: float) -> dict:
    """A settled absence or failed read, distinct from a row not fetched yet."""
    point = dict.fromkeys(SWARM_ORACLE_CACHE_FIELDS)
    point.update(status=status, in_cluster=False, on_panel=False, read_ts=now_ts,
                 terminal=status in _ORACLE_FINAL)
    return point


_ORACLE_TEXT_CAPS = {'question': 1000, 'member_reason': 200, 'notes': 4000}
_ORACLE_FACTS = ('question', 'chain_id', 'member_ok', 'member_reason', 'seat_answer', 'notes')
ORACLE_POINT_BYTES = 6000


def _oracle_prefix(text: str, cap: int) -> str | None:
    """Never turn a cut hex run into a different, apparently valid address."""
    if len(text) > cap:
        for run in re.finditer(r'0x[0-9a-fA-F]+', text):
            if run.start() >= cap:
                break
            if cap < run.end():
                cap = run.start()
                break
    return text[:cap].rstrip() or None


def _oracle_text(value: object, cap: int, *, paragraphs: bool = True) -> str | None:
    if not isinstance(value, str):
        return None
    clean = ''.join(c for c in value if c == '\n' or not unicodedata.category(c).startswith('C'))
    clean = '\n'.join(' '.join(line.split()) for line in clean.split('\n')) if paragraphs else ' '.join(clean.split())
    return _oracle_prefix(clean.strip(), cap)


def _seat_answer(value: object, kind: str | None) -> str | None:
    if kind == 'bool':
        return ('true' if value else 'false') if type(value) is bool else None
    if kind == 'uint256':
        return value if isinstance(value, str) and re.fullmatch(r'[0-9]{1,78}', value) else None
    if kind == 'address[]':
        if (not isinstance(value, list) or len(value) > 20
                or any(not isinstance(v, str) or re.fullmatch(r'0x[0-9a-fA-F]{40}', v) is None for v in value)):
            return None
        return ' '.join(value)
    if isinstance(value, str):
        return _oracle_text(value, 200, paragraphs=False)
    if type(value) in (int, float):
        try:
            return _oracle_text(str(value), 200, paragraphs=False) if math.isfinite(value) else None
        except (OverflowError, ValueError):
            return None
    return None


def _oracle_bytes(point: Mapping) -> int:
    try:
        return len(json.dumps(dict(point)).encode())
    except (ValueError, TypeError, OverflowError):
        return ORACLE_POINT_BYTES + 1


def _bound_oracle_point(point: dict) -> dict | None:
    # Match surf_cache's json.dump encoding, including escaped Unicode and quotes.
    for name in ('notes', 'question', 'member_reason'):
        if _oracle_bytes(point) <= ORACLE_POINT_BYTES:
            return point
        text = point[name] or ''
        point[name] = None
        if _oracle_bytes(point) > ORACLE_POINT_BYTES:
            continue
        low, high = 0, len(text)
        while low < high:
            mid = (low + high + 1) // 2
            point[name] = _oracle_prefix(text, mid)
            if _oracle_bytes(point) <= ORACLE_POINT_BYTES:
                low = mid
            else:
                high = mid - 1
        point[name] = _oracle_prefix(text, low)
    return point if _oracle_bytes(point) <= ORACLE_POINT_BYTES else None


def _valid_oracle_facts(point: Mapping) -> bool:
    if _oracle_bytes(point) > ORACLE_POINT_BYTES:
        return False
    if not point['on_panel']:
        return all(point[name] is None for name in _ORACLE_FACTS)
    if type(point['member_ok']) is not bool or (point['chain_id'] is not None and type(point['chain_id']) is not int):
        return False
    for name, cap in _ORACLE_TEXT_CAPS.items():
        text = point[name]
        if text is not None and (not isinstance(text, str) or _oracle_text(text, cap, paragraphs=name != 'member_reason') != text):
            return False
    value, kind = point['seat_answer'], point['answer_type']
    if value is None:
        return True
    if not isinstance(value, str):
        return False
    if kind == 'bool':
        return value in ('true', 'false')
    raw = value.split(' ') if kind == 'address[]' and value else [] if kind == 'address[]' else value
    return _seat_answer(raw, kind) == value


def oracle_point(detail: object, job_id: str, submission_hash: str, *, now_ts: float) -> dict | None:
    """Join only by exact hash; price tolerance is already resolved by cluster membership."""
    if (parse_job_id(job_id) is None or _hex64(submission_hash) is None
            or not isinstance(detail, Mapping) or detail.get('jobId') != job_id
            or parse_job_id(detail.get('id')) is None or not isinstance(detail.get('status'), str)
            or not detail['status'].strip()):
        return None
    status = detail['status']
    members = detail.get('members')
    if members is None and status == 'blocked':
        members = []  # Captured blocked requests serve null (owner-approved).
    agreement = detail.get('agreement')
    if (not isinstance(members, list) or any(not isinstance(m, Mapping) for m in members)
            or agreement is not None and not isinstance(agreement, Mapping)):
        return None
    if agreement is None:
        if status in _ORACLE_FINAL and status != 'blocked':
            return None
        agreement = {'cluster': []}
    cluster = agreement.get('cluster')
    if not isinstance(cluster, list) or any(_hex64(key) is None for key in cluster):
        return None
    matches = [member for member in members if member.get('submissionHash') == submission_hash]
    if matches and any(member != matches[0] for member in matches[1:]):
        return None
    answer_type = detail.get('answerType')
    point = dict(
        request_id=detail['id'], status=status, in_cluster=submission_hash in cluster,
        on_panel=bool(matches), agreed=_oracle_count(agreement.get('agreed')), quorum=_oracle_count(detail.get('quorum')),
        panel_size=_oracle_count(detail.get('panelSize')), figure=_oracle_figure(agreement.get('figure')),
        answer_type=' '.join(answer_type.split()) if isinstance(answer_type, str) else None,
        answer_bool=agreement.get('answer') if type(agreement.get('answer')) is bool else None,
        read_ts=now_ts, terminal=status in _ORACLE_FINAL,
    )
    point.update(dict.fromkeys(_ORACLE_FACTS))
    if matches:
        member = matches[0]
        if type(member.get('ok')) is not bool:
            return None
        answer = member.get('answer')
        answer = answer if isinstance(answer, Mapping) else {}
        point.update(question=_oracle_text(detail.get('question'), 1000),
                     chain_id=detail.get('chainId') if type(detail.get('chainId')) is int else None,
                     member_ok=member['ok'], member_reason=_oracle_text(member.get('reason'), 200, paragraphs=False),
                     seat_answer=_seat_answer(answer.get('answer'), point['answer_type']),
                     notes=_oracle_text(answer.get('notes'), 4000))
    return _bound_oracle_point(point)


def coerce_oracle_slot(payload: object) -> dict | None:
    """Validate each persisted point independently; never retain a raw envelope."""
    if not isinstance(payload, Mapping):
        return None
    result = {}
    for job, items in payload.items():
        if parse_job_id(job) is None or not isinstance(items, Mapping):
            continue
        clean = {}
        for key, point in items.items():
            if (_hex64(key) is None or not isinstance(point, Mapping)
                    or set(point) != set(SWARM_ORACLE_CACHE_FIELDS)):
                continue
            if (point['request_id'] is not None and parse_job_id(point['request_id']) is None
                    or not _optional_string(point['status']) or not _optional_string(point['answer_type'])
                    or point['answer_bool'] is not None and type(point['answer_bool']) is not bool
                    or any(type(point[name]) is not bool for name in ('in_cluster', 'on_panel', 'terminal'))
                    or not _nonnegative_finite(point['read_ts'])
                    or any(point[name] is not None and _oracle_count(point[name]) is None
                           for name in ('agreed', 'quorum', 'panel_size'))
                    or point['figure'] is not None and _oracle_figure(point['figure']) is None):
                continue
            if point['terminal'] != (point['status'] in _ORACLE_FINAL):
                continue
            if not _valid_oracle_facts(point):
                continue
            clean[key] = dict(point)
        if clean:
            result[job] = clean
    return result


def prune_oracle(payload: object, *, now_ts: float, cap: int = 400, max_age_s: float = 48 * 3600) -> dict:
    """Bound retained points, newest first, with an injected clock."""
    points = [(job, key, point) for job, items in (coerce_oracle_slot(payload) or {}).items()
              for key, point in items.items() if 0 <= now_ts - point['read_ts'] <= max_age_s]
    points.sort(key=lambda item: (-item[2]['read_ts'], item[0], item[1]))
    result: dict[str, dict] = {}
    for job, key, point in points[:max(0, cap)]:
        result.setdefault(job, {})[key] = point
    return result


def oracle_rows_due(rows: list[dict], oracle: object, *, now_ts: float, due_s: float) -> list[dict]:
    """Only the displayed oracle window: unread first, then oldest due retries."""
    valid = coerce_oracle_slot(oracle) or {}
    due = []
    for index, row in enumerate(rows[:SWARM_ANSWER_ROW_CAP]):
        job, key = row['job_id'], row['submission_hash']
        if (row['node_key'] not in SWARM_ORACLE_NODE_KEYS
                or parse_job_id(job) is None or _hex64(key) is None):
            continue
        point = valid.get(job, {}).get(key)
        if point is not None and (point['terminal'] or now_ts - point['read_ts'] < due_s):
            continue
        priority = (0, index) if point is None else (1, point['read_ts'])
        due.append((priority, row))
    return [row for _, row in sorted(due, key=lambda item: item[0])]


def oracle_cursor_ts(value: object) -> float | None:
    """Validate a served UTC ISO cursor before comparing it or sending it back."""
    if not isinstance(value, str) or re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?Z", value) is None:
        return None
    return _ts(value)


def empty_oracle_index() -> dict:
    return dict(jobs={}, newest=None, oldest=None, complete=False)


def coerce_oracle_index(payload: object) -> dict | None:
    """The history proof is indivisible: reject any hostile or inconsistent slot."""
    if (not isinstance(payload, dict) or set(payload) != {'jobs', 'newest', 'oldest', 'complete'}
            or not isinstance(payload['jobs'], dict) or type(payload['complete']) is not bool):
        return None
    jobs = payload['jobs']
    if any(parse_job_id(job) != job or job is None
           or request is not None and (parse_job_id(request) != request)
           for job, request in jobs.items()):
        return None
    requests = [request for request in jobs.values() if request is not None]
    if len(set(requests)) != len(requests):
        return None
    if jobs:
        newest, oldest = (oracle_cursor_ts(payload[key]) for key in ('newest', 'oldest'))
        if newest is None or oldest is None or oldest > newest:
            return None
    elif payload['newest'] is not None or payload['oldest'] is not None or payload['complete']:
        # A complete index with no entries is not a history proof (re-review N1).
        return None
    return dict(payload, jobs=dict(jobs))


def oracle_index_page(page: object) -> list[dict] | None:
    """Validate the entire page before extending a history proof."""
    if not isinstance(page, list):
        return None
    clean = []
    for item in page:
        if (not isinstance(item, Mapping) or parse_job_id(item.get('jobId')) is None
                or parse_job_id(item.get('id')) is None
                or oracle_cursor_ts(item.get('createdAt')) is None):
            return None
        clean.append({key: item[key] for key in ('jobId', 'id', 'createdAt')})
    return clean


def add_oracle_index_page(index: dict, page: list[dict]) -> None:
    """Merge identities; repeated sightings are safe, conflicting requests ambiguous."""
    for item in page:
        job, request = item['jobId'], item['id']
        if job in index['jobs'] and index['jobs'][job] != request:
            index['jobs'][job] = None
        else:
            index['jobs'][job] = request


def match_requests(index: object, due_rows: list[dict]) -> tuple[dict, set, set]:
    """Only a complete history covering submission time can prove absence."""
    valid = coerce_oracle_index(index) or empty_oracle_index()
    matched, ambiguous, negative = {}, set(), set()
    newest = oracle_cursor_ts(valid['newest'])
    for row in due_rows:
        job = row['job_id']
        if job in valid['jobs']:
            request = valid['jobs'][job]
            if request is None:
                ambiguous.add(job)
            else:
                matched[job] = request
        elif (valid['complete'] and newest is not None
              and type(row.get('submitted_ts')) in (int, float)
              and newest >= row['submitted_ts']):
            negative.add(job)
    return matched, ambiguous, negative


def enrich_panel_rows(rows: list[dict], oracle: object, node_keys: tuple[str, ...]) -> list[dict]:
    """Add panel evidence without changing the source's work/answer state."""
    valid = coerce_oracle_slot(oracle) or {}
    result = []
    for row in rows:
        item = dict(row, panel_agreed=None, panel_quorum=None, panel_size=None,
                    panel_figure=None, panel_answer_type=None, panel_answer_bool=None)
        item.update({'oracle_' + name: None for name in _ORACLE_FACTS})
        point = valid.get(row['job_id'], {}).get(row['submission_hash'])
        if row['node_key'] not in node_keys:
            state = 'not_oracle'
        elif point is None:
            state = 'not_read'
        else:
            status = point['status']
            if status == 'blocked':
                state = 'blocked'
            elif status == 'off_panel' or status in _ORACLE_FINAL and not point['on_panel']:
                state = 'off_panel'
            elif status == 'attested':
                state = 'agreed' if point['in_cluster'] else 'outvoted'
            elif status == 'disagreed':
                state = 'no_quorum_in' if point['in_cluster'] else 'no_quorum_out'
            elif status == 'assessing':
                state = 'assessing'
            else:
                state = 'unavailable'
                if status is not None:
                    _log_oracle_status(status)
            if point['on_panel']:
                item.update({'oracle_' + name: point[name] for name in _ORACLE_FACTS})
            item.update(panel_agreed=point['agreed'], panel_quorum=point['quorum'],
                        panel_size=point['panel_size'], panel_figure=point['figure'],
                        panel_answer_type=point['answer_type'], panel_answer_bool=point['answer_bool'])
        item['panel_state'] = state
        result.append(item)
    return result


@lru_cache(maxsize=128)
def _log_oracle_status(status: str) -> None:
    logging.getLogger(__name__).debug("Unknown oracle panel status: %s", status)
