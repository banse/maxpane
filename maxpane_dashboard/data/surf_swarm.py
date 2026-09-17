"""Fold the IMD swarm control plane's reads into rows the panels render.

Pure: stdlib only.  No network, no clock (callers pass ``now``), no Textual.
The shapes this folds are recorded in ``docs/imd_swarm_api.md``; the reader
that fetches them is ``surf_swarm_client.py``.

Every value here is ``None`` when it was not read.  A zero is a zero.
"""
from __future__ import annotations

import datetime
import statistics
from collections.abc import Mapping, Sequence
from typing import Any

__all__ = [
    "TERMINAL_STATES", "blocked_rows", "field_rows", "health_facts",
    "network_of", "queue_rows", "score_rows", "shipped_rows", "throughput",
    "unfinished_ids",
]

#: A job in one of these states is finished; nothing else is.
TERMINAL_STATES = frozenset({"completed", "cancelled"})

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
                "queue_depths": None, "services_up": None, "network": None}
    depths = {
        key[len("pending"):].lower(): _int(value)
        for key, value in health.items()
        if key.startswith("pending")
    }
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
        "queue_depths": depths or None,
        "services_up": services_up,
        "network": network_of(chain),
    }


def queue_rows(jobs: Sequence[Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    """``[{"state", "count"}]``, biggest first, ties by state name."""
    if not jobs:
        return []
    counts: dict[str, int] = {}
    for job in jobs:
        state = job.get("state")
        if isinstance(state, str) and state:
            counts[state] = counts.get(state, 0) + 1
    return [{"state": s, "count": c}
            for s, c in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]


def blocked_rows(jobs: Sequence[Mapping[str, Any]] | None, *,
                 limit: int = 8) -> list[dict[str, Any]]:
    """Blocked jobs, newest move first, with the reason the host gave."""
    if not jobs:
        return []
    rows = [
        {
            "job_id": job.get("id"),
            "template": job.get("template"),
            "reason": job.get("blockedReason"),
            "moved_ts": _ts(job.get("updatedAt")),
        }
        for job in jobs
        if job.get("state") == "blocked"
    ]
    rows.sort(key=lambda r: (r["moved_ts"] is None, -(r["moved_ts"] or 0.0)))
    return rows[:limit]


def unfinished_ids(jobs: Sequence[Mapping[str, Any]] | None) -> list[str]:
    """Ids of jobs still moving — the only details worth fetching."""
    if not jobs:
        return []
    return [
        job["id"] for job in jobs
        if isinstance(job.get("id"), str)
        and job.get("state") not in TERMINAL_STATES
    ]


def field_rows(details: Sequence[Mapping[str, Any]] | None, *,
               now: float) -> list[dict[str, Any]]:
    """One row per subtask of every unfinished job, newest move first."""
    if not details:
        return []
    rows: list[dict[str, Any]] = []
    for job in details:
        for node in job.get("nodes") or ():
            seat = node.get("seat") if isinstance(node.get("seat"), Mapping) else {}
            moved = _ts(node.get("updatedAt")) or _ts(job.get("updatedAt"))
            rows.append({
                "job_id": job.get("id"),
                "template": job.get("template"),
                "objective": job.get("objective"),
                "node_key": node.get("key"),
                "role": node.get("role"),
                "node_state": node.get("state"),
                "agent_token": seat.get("tokenId"),
                "agent_id": seat.get("agentId"),
                "revisions": _int(node.get("revisions")),
                "dispatch_note": node.get("dispatchNote") or None,
                "moved_ts": moved,
                "age_s": max(0.0, now - moved) if moved is not None else None,
            })
    rows.sort(key=lambda r: (r["moved_ts"] is None, -(r["moved_ts"] or 0.0)))
    return rows


def score_rows(details: Sequence[Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    """One row per agent: how many scores, their mean, and the last tx.

    agent_token is populated from the node's seat by matching nodeKey.
    """
    if not details:
        return []
    per: dict[str, dict[str, Any]] = {}
    for job in details:
        # Build a map of nodeKey -> tokenId for this job
        node_seats: dict[str, object] = {}
        for node in job.get("nodes") or ():
            node_key = node.get("key")
            if isinstance(node_key, str):
                seat = node.get("seat") if isinstance(node.get("seat"), Mapping) else {}
                node_seats[node_key] = seat.get("tokenId")

        for review in job.get("reviews") or ():
            chain = review.get("chainId")
            tx = review.get("txHash")
            sent = _ts(review.get("sentAt"))
            for entry in review.get("entries") or ():
                agent = entry.get("agentId")
                value = entry.get("value")
                node_key = entry.get("nodeKey")
                if not isinstance(agent, str) or not isinstance(value, (int, float)):
                    continue
                token_id = node_seats.get(node_key) if isinstance(node_key, str) else None
                row = per.setdefault(agent, {
                    "agent_id": agent, "agent_token": token_id, "values": [],
                    "last_tx_hash": None, "last_chain_id": None, "_last": None,
                })
                row["values"].append(float(value))
                if row["_last"] is None or (sent or 0.0) >= row["_last"]:
                    row["_last"] = sent or 0.0
                    row["last_tx_hash"] = tx
                    row["last_chain_id"] = chain
                    row["agent_token"] = token_id
    out = []
    for row in per.values():
        values = row.pop("values")
        row.pop("_last")
        row["jobs_scored"] = len(values)
        row["mean_score"] = round(statistics.fmean(values), 1) if values else None
        out.append(row)
    out.sort(key=lambda r: (-(r["mean_score"] or 0.0), r["agent_id"]))
    return out


def shipped_rows(jobs: Sequence[Mapping[str, Any]] | None,
                 details: Sequence[Mapping[str, Any]] | None,
                 launches: Sequence[Mapping[str, Any]] | None,
                 sites: Sequence[Mapping[str, Any]] | None, *,
                 limit: int = 12) -> list[dict[str, Any]]:
    """Deliveries, deployed contracts and published sites, newest first."""
    rows: list[dict[str, Any]] = []
    for job in jobs or ():
        delivery = job.get("delivery")
        if not isinstance(delivery, Mapping):
            continue
        rows.append({
            "kind": "delivery", "job_id": job.get("id"),
            "label": job.get("template"), "commit": delivery.get("commit"),
            "chain_id": None, "address": None, "tx_hash": None,
            "ens_name": None, "cid": None,
            "at_ts": _ts(delivery.get("deliveredAt")),
        })
    for launch in launches or ():
        chain = launch.get("chainId")
        at = _ts(launch.get("updatedAt"))
        for artifact in launch.get("artifacts") or ():
            rows.append({
                "kind": "launch", "job_id": launch.get("id"),
                "label": artifact.get("name") or artifact.get("role"),
                "commit": launch.get("sourceCommit"), "chain_id": chain,
                "address": artifact.get("address"),
                "tx_hash": artifact.get("txHash"),
                "ens_name": None, "cid": None, "at_ts": at,
            })
    for site in sites or ():
        rows.append({
            "kind": "site", "job_id": site.get("jobId"),
            "label": site.get("label"), "commit": None, "chain_id": None,
            "address": None, "tx_hash": site.get("txHash"),
            "ens_name": site.get("ensName"), "cid": site.get("cid"),
            "at_ts": _ts(site.get("namedAt")) or _ts(site.get("pinnedAt")),
        })
    rows.sort(key=lambda r: (r["at_ts"] is None, -(r["at_ts"] or 0.0)))
    return rows[:limit]


def throughput(jobs: Sequence[Mapping[str, Any]] | None,
               details: Sequence[Mapping[str, Any]] | None, *,
               now: float, window_days: int = 7) -> dict[str, Any]:
    """Accepted per day, median delivery time, revision rate over a window.

    ``jobs is None`` means the tier was never read: every rate field is
    ``None``. ``jobs == []`` (or any other empty-but-not-``None`` sequence)
    is a genuine read that found no jobs, and that is not the same state --
    F10, the curator-rail conflation one layer down from the one the hero's
    ``swarm_jobs_in_flight``/``swarm_jobs_blocked`` split already fixed
    (``widgets/surf/swarm_hero.py``). The two inputs get told apart *before*
    either is folded through a ``for x in <arg> or ()`` idiom, which is
    exactly the idiom that hid the original defect: fold first and ``None``
    and ``[]`` are indistinguishable by the time you'd branch on them.

    The three fields do not all get the same treatment on a genuine empty
    read, because only one of them has a value that can honestly mean
    "measured, and it is zero":

    * ``accepted_per_day`` gets its real, representable zero
      (``round(0 / window_days, 2)``) -- zero jobs accepted in the window is
      exactly what a genuine empty read *is*.
    * ``median_delivery_s`` has no representable zero: ``0`` would claim
      "delivered instantly", which nothing did. It stays ``None`` on a
      genuine empty read exactly as it does on no read at all.
    * ``revision_rate`` has the same problem and gets the same answer.

    So ``median_delivery_s``/``revision_rate`` are ``None`` for both
    "never read" and "read, nothing to measure" -- this function cannot tell
    those two apart for a field with no honest zero to give one of them. The
    panel does not need a new gate to make that visible, though: it already
    prints this tier's own ``as of`` marker (``swarm_scores_as_of_hhmm``) in
    its title whenever a read has actually happened, which is the same
    marker the agent-score section below it already uses to tell
    "unavailable" apart from "read, no agents yet". A ``None`` row beside a
    real marker reads as "read, nothing here"; the same row with no marker
    at all reads as "never read" -- the distinguishing instrument this body
    already has, not a new one.

    Revision rate filters to nodes with a non-None updatedAt within the window.
    Nodes without timestamps are excluded from the sample, not counted as zero.
    Empty revision sample returns None, not 0.0.
    """
    if jobs is None:
        return {"accepted_per_day": None, "median_delivery_s": None,
                "revision_rate": None, "window_days": window_days}
    floor = now - window_days * 86400
    delivered: list[float] = []
    accepted = 0
    for job in jobs:
        created = _ts(job.get("createdAt"))
        delivery = job.get("delivery")
        at = _ts(delivery.get("deliveredAt")) if isinstance(delivery, Mapping) else None
        if at is None or at < floor:
            continue
        accepted += 1
        if created is not None and at > created:
            delivered.append(at - created)
    revisions = [
        _int(node.get("revisions")) or 0
        for job in details or ()
        for node in job.get("nodes") or ()
        if _ts(node.get("updatedAt")) is not None and _ts(node.get("updatedAt")) >= floor
    ]
    return {
        "accepted_per_day": round(accepted / window_days, 2),
        "median_delivery_s": round(statistics.median(delivered)) if delivered else None,
        "revision_rate": (
            round(sum(1 for r in revisions if r) / len(revisions), 3)
            if revisions else None
        ),
        "window_days": window_days,
    }
