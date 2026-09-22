"""Fold the IMD swarm control plane's reads into rows the panels render.

Pure: stdlib, the pure ``analytics/surf_swarm_signals`` rollups, the
``data/surf_models`` contract tuples, and one constant from
``surf_swarm_client`` (``UNKNOWN_SEAT``, the client's normalised 404 -- the
fold imports the value, never calls the client).  No network, no clock
(callers pass ``now_ts``), no Textual.  The shapes this
folds are recorded in ``docs/imd_swarm_api.md``; the reader that fetches
them is ``surf_swarm_client.py``.  The v1 folds (field / queue / blocked /
shipped / score rows and the old ``throughput``) retired with their widgets
in WP7 of the swarm v2 plan.

Every value here is ``None`` when it was not read.  A zero is a zero.
"""
from __future__ import annotations

import datetime
import math
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
)
# A constant only: the client owns the normalised ``unknown_seat`` result, so
# the fold recognises it by that one definition rather than a retyped literal.
from maxpane_dashboard.data.surf_swarm_client import UNKNOWN_SEAT

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
                "services_up": None, "network": None}
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
            "failure": _str(site.get("failure")),
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
    finite, non-bool ``value``. Win rate is lifetime accepted / attempts,
    unlike BY NODE's won / reviewed; zero or missing attempts is undefined.
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
            "objective": _str(work.get("objective")),
            "accepted_ts": _ts(work.get("acceptedAt")),
            "launch": _str(work.get("launch")),
            "submission_hash": submission_hash,
        }
        rows.append({key: row[key] for key in keys})
    return rows


def seat_node_rows(payload: object) -> list[dict[str, Any]] | None:
    """Nodes from reviews and won work, sorted reviewed desc, won desc, key asc.

    BY NODE win uses won / reviewed, since attempts are not served per node;
    the hero instead uses lifetime accepted / attempts. Work-only nodes keep
    reviewed zero. Onchain counts sent/submitted reviews carrying a tx hash.
    Both source lists must be served; a missing list makes the rows unavailable.
    """
    if (not isinstance(payload, Mapping) or not isinstance(payload.get("reviews"), list)
            or not isinstance(payload.get("work"), list)):
        return None
    nodes: dict[str, dict[str, Any]] = {}
    for source in ("reviews", "work"):
        items = (_distinct_reviews(_list(payload.get(source))) if source == "reviews"
                 else _mappings(_list(payload.get(source))))
        for item in items:
            key = _str(item.get("nodeKey"))
            if key is None:
                continue
            row = nodes.setdefault(key, {
                "node_key": key, "roles": [], "reviewed": 0, "won": 0,
                "onchain": 0, "queued": 0,
            })
            role = _str(item.get("role"))
            if role is not None and role not in row["roles"]:
                row["roles"].append(role)
            if source == "work":
                row["won"] += 1
            else:
                row["reviewed"] += 1
                status = item.get("status")
                if status in ("sent", "submitted") and _str(item.get("txHash")):
                    row["onchain"] += 1
                if status == "queued":
                    row["queued"] += 1
    for row in nodes.values():
        row["roles"].sort()
    return sorted(nodes.values(), key=lambda row: (-row["reviewed"], -row["won"], row["node_key"]))


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


def _string_list(value: object) -> list[str] | None:
    return list(value) if isinstance(value, list) and all(isinstance(v, str) for v in value) else None


def normalize_contributors(payload: object) -> dict[str, Any] | None:
    """Normalize a served envelope; require every counter before admitting a row.

    All counters use the existing strict ASCII decimal-string/int parser. A
    missing list is unread; malformed members are dropped, never zero-filled.
    The token-accounting counters are retained and aggregated, never ranked.
    """
    if not isinstance(payload, Mapping) or not isinstance(payload.get("contributors"), list):
        return None
    rows = []
    for source in _mappings(payload["contributors"]):
        token = _served_token(source.get("tokenId"))
        device = _str(source.get("deviceKey"))
        counts = {name: _served_token(source.get(field)) for name, field in _CONTRIBUTOR_COUNTERS.items()}
        if token is None or not device or any(value is None for value in counts.values()):
            continue
        rows.append({"device_key": device, "token_id": token, **counts})
    return {
        "receipts": _served_token(payload.get("receipts")),
        "tokens_per_completed_job": _served_token(payload.get("tokensPerCompletedJob")),
        "contributors": rows,
    }


def normalize_workers(payload: object) -> dict[str, Any] | None:
    """Normalize live devices; malformed identity, capacity or pause drops a row.

    Missing optional metadata remains None, distinct from a served empty list.
    A malformed pause is never evidence of an idle worker. LIVE remains the
    served envelope count even when malformed rows were omitted from the list.
    """
    if not isinstance(payload, Mapping) or not isinstance(payload.get("workers"), list):
        return None
    rows = []
    for source in _mappings(payload["workers"]):
        seat = source.get("seat")
        if not isinstance(seat, Mapping):
            continue
        token = _served_token(seat.get("tokenId"))
        device = _str(source.get("deviceKey"))
        working = _served_token(source.get("working"))
        capacity = _served_token(source.get("maxConcurrency"))
        if token is None or not device or working is None or capacity is None:
            continue
        until = failures = None
        if "paused" not in source:
            continue
        pause = source["paused"]
        if pause is not None:
            if not isinstance(pause, Mapping):
                continue
            until = _ts(pause.get("until"))
            failures = _served_token(pause.get("consecutiveFailures"))
            if until is None or failures is None:
                continue
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
            "paused_until_ts": until, "failures": failures,
            "heartbeat_ts": _ts(source.get("lastHeartbeatAt")),
            "runtimes": runtimes, "daemon": _str(source.get("daemonVersion")),
            "profiles": _string_list(source.get("profiles")),
            "skills": _string_list(source.get("skills")), "os": os,
            "platform": f"{os} {arch}" if os is not None and arch is not None else None,
        })
    return {"count": _served_token(payload.get("count")), "workers": rows}


def _valid_count(value: object) -> bool:
    return _seat_id(value) is not None


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
    return {**{key: payload[key] for key in fields}, member: rows}


def coerce_contributors_slot(payload: object) -> dict[str, Any] | None:
    """Validate every normalized field; cached decimal strings are not re-parsed."""
    return _coerce_board_slot(payload, "contributors", {
        "receipts": _optional_count, "tokens_per_completed_job": _optional_count,
    }, {"device_key": lambda v: isinstance(v, str) and bool(v), "token_id": _valid_count,
        **dict.fromkeys(_CONTRIBUTOR_COUNTERS, _valid_count)})


def coerce_workers_slot(payload: object) -> dict[str, Any] | None:
    """Validate every normalized worker field and the paired pause timestamp/count."""
    result = _coerce_board_slot(payload, "workers", {"count": _optional_count}, {
        "device_key": lambda v: isinstance(v, str) and bool(v), "token_id": _valid_count,
        "agent_id": _optional_string, "working": _valid_count, "max_concurrency": _valid_count,
        "paused_until_ts": _optional_stamp, "failures": _optional_count,
        "heartbeat_ts": _optional_stamp, "runtimes": _optional_strings,
        "daemon": _optional_string, "profiles": _optional_strings, "skills": _optional_strings,
        "os": _optional_string, "platform": _optional_string,
    })
    if result is not None and any((row["paused_until_ts"] is None) != (row["failures"] is None)
                                  for row in result["workers"]):
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


def _live_for_workers(rows: list[dict]) -> dict[str, Any]:
    live = dict.fromkeys(SWARM_SEAT_LIVE_FIELDS)
    live.update(live=bool(rows), working=sum(row["working"] for row in rows),
                max_concurrency=sum(row["max_concurrency"] for row in rows), devices=len(rows))
    if not rows:
        return live
    paused = [row for row in rows if row["paused_until_ts"] is not None]
    if paused:
        chosen = min(paused, key=lambda row: (row["paused_until_ts"], row["device_key"]))
        live["paused_until_ts"], live["failures"] = chosen["paused_until_ts"], chosen["failures"]
    live["heartbeat_ts"] = max((row["heartbeat_ts"] for row in rows if row["heartbeat_ts"] is not None), default=None)
    skills = _metadata_union(rows, "skills")
    live["skills"] = len(skills) if skills is not None else None
    live["profiles"] = _metadata_union(rows, "profiles")
    if all(row["platform"] is not None for row in rows):
        live["platform"] = ", ".join(sorted({row["platform"] for row in rows}))
    return live


def _live_state(live: dict) -> str:
    if not live["live"]:
        return "offline"
    if live["working"]:
        return "working"
    return "paused" if live["paused_until_ts"] is not None else "idle"


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
    for row in contributors["contributors"]:
        counts = grouped.setdefault(row["token_id"], {"devices": set(), **dict.fromkeys(_CONTRIBUTOR_COUNTERS, 0)})
        counts["devices"].add(row["device_key"])
        for field in _CONTRIBUTOR_COUNTERS:
            counts[field] += row[field]
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
            "agent_id": next((row["agent_id"] for row in sorted(live_rows, key=lambda row: row["device_key"])
                              if row["agent_id"] is not None), None),
            "devices": len(counts["devices"]),
            "runtime": (_runtime_bucket(_metadata_union(live_rows, "runtimes")) if live_rows
                        else "offline" if workers is not None else None),
            **{field: counts[field] for field in ("attempts", "accepted", "rejected", "pending")},
            "accept_rate": rate, "turns": counts["turns"], "wall_clock_s": _seconds(counts["wall_clock_ms"]),
            "live_state": _live_state(live) if live is not None else None,
            "working": live["working"] if live is not None else None,
            "paused_until_ts": live["paused_until_ts"] if live is not None else None,
            "failures": live["failures"] if live is not None else None,
        }
        result.append(row)
    result.sort(key=lambda row: (-row["accepted"], row["accept_rate"] is None,
                                 -(row["accept_rate"] or 0), row["token_id"]))
    for rank, row in enumerate(result, 1):
        row["rank"] = rank
    return result


def board_rows(contributors: object, workers: object) -> list[dict] | None:
    """One row per contributor seat; workers enrich metadata, never the counters."""
    return _board_rows_from_slots(normalize_contributors(contributors), normalize_workers(workers))


def _board_summary_from_slots(contributors: dict | None, workers: dict | None) -> dict:
    summary = dict.fromkeys(SWARM_BOARD_SUMMARY_FIELDS)
    if contributors is not None:
        rows = contributors["contributors"]
        summary["seats"] = len({row["token_id"] for row in rows})
        for field in ("attempts", "accepted", "rejected", "pending"):
            summary[field] = sum(row[field] for row in rows)
        summary["receipts"] = contributors["receipts"]
        summary["tokens_per_completed_job"] = contributors["tokens_per_completed_job"]
    if workers is not None:
        rows = workers["workers"]
        summary["live"] = workers["count"]
        summary["paused"] = len({row["token_id"] for row in rows if row["paused_until_ts"] is not None})
        summary["capacity"] = sum(row["max_concurrency"] for row in rows)
        summary["working"] = sum(row["working"] for row in rows)
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
        concurrency=_mix(str(row["max_concurrency"]) for row in rows),
    )
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
    if workers is None or wanted is None:
        return None
    return _live_for_workers(_worker_groups(workers).get(wanted, []))


def seat_live(workers: object, token: object) -> dict | None:
    """Selected token's live state; None unread, live=False absent after a read."""
    return _seat_live_from_slot(normalize_workers(workers), token)


def _seat_contrib_from_rows(rows: list[dict] | None, token: object) -> dict | None:
    wanted = _seat_id(token)
    if rows is None or wanted is None:
        return None
    result = dict.fromkeys(SWARM_SEAT_CONTRIB_FIELDS)
    result["listed"] = False
    selected = next((row for row in rows if row["token_id"] == wanted), None)
    if selected is not None:
        result.update(listed=True, ranked_of=len(rows))
        for field in ("attempts", "accepted", "rejected", "pending", "turns", "wall_clock_s", "rank"):
            result[field] = selected[field]
    return result


def seat_contrib(contributors: object, token: object) -> dict | None:
    """Selected token's lifetime contributor counters, independent of /seats."""
    return _seat_contrib_from_rows(board_rows(contributors, None), token)
