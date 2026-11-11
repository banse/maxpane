"""Validated independent IMD snapshots and plain rack projections.

No I/O here. The existing SurfManager owns source tasks and persists these whole
source envelopes. Overview seats are intentionally never outcome authority.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime
from functools import cmp_to_key
from typing import Any

from maxpane_dashboard.analytics.surf_ids import parse_job_id
from maxpane_dashboard.analytics.surfboard import count, number, ratio, hourly_points, compact_age, SURFBOARD_AGENT_KEYS, seat_token
from maxpane_dashboard.data import surf_swarm as sw
from maxpane_dashboard.data import surfboard_activity as work_activity
from maxpane_dashboard.data import surf_launchpad_volume as launch_volume
from maxpane_dashboard.data import surf_leaderboard_hero as leaderboard_hero
from maxpane_dashboard.data.surf_oracles import PAGE_LIMIT as ORACLE_PAGE_LIMIT
from maxpane_dashboard.analytics.surf_launch_checks import address
from maxpane_dashboard.data.surf_models import (
    SURFBOARD_CARD_FIELDS, SURFBOARD_OVERVIEW_FIELDS, SURFBOARD_SUPPLY_FIELDS, SWARM_SEAT_OUTCOME_FIELDS,
    SURF_WORK_SUMMARY_KEYS, SURFBOARD_FLEET_FIELDS,
)

OUTCOME_COUNTERS = ("attempts", "accepted", "rejected", "failed", "pending")
SOURCE_SLOTS = {"overview": "surfboard_overview", "records": "surfboard_records", "hourly": "surfboard_hourly",
                "supply": "surfboard_supply"}
RANK_BASIS = "seat-records-v1"
_EVENT_TEXT = {"token": "token", "ens_name": "ensName", "cid": "cid", "failure": "failure", "reason": "reason"}
_EVENT_COUNTS = {"launch_number": "launchNumber", "chain_id": "chainId", "steps": "steps", "scores": "scores", "accepted": "accepted"}


def timestamp(value: object) -> float | None:
    try:
        if isinstance(value, str):
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                return None
            stamp = parsed.timestamp()
        elif number(value) is not None:
            stamp = float(value)
        else:
            return None
        # Finite alone is insufficient: libc/datetime cannot render 1e300.
        # Reject at the boundary so neither restored data nor a live read can
        # crash a rack projection outside the full-collection exception guard.
        if stamp < 0:
            return None
        datetime.fromtimestamp(stamp)
        return stamp
    except (ValueError, OverflowError, OSError):
        return None


def _text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _compare(a: dict, b: dict) -> int:
    if a["accepted"] != b["accepted"]:
        return -1 if a["accepted"] > b["accepted"] else 1
    if bool(a["attempts"]) != bool(b["attempts"]):
        return -1 if a["attempts"] else 1
    cross_a = a["accepted"] * b["attempts"]
    cross_b = b["accepted"] * a["attempts"]
    if cross_a != cross_b:
        return -1 if cross_a > cross_b else 1
    return (a["token_id"] > b["token_id"]) - (a["token_id"] < b["token_id"])


def normalize_records(raw: object) -> dict | None:
    if not isinstance(raw, dict) or count(raw.get("count")) is None or not isinstance(raw.get("seats"), list):
        return None
    rows, seen = [], set()
    for item in raw["seats"]:
        if not isinstance(item, dict):
            return None
        token = sw._served_token(item.get("tokenId"))
        if token is None or token in seen or any(count(item.get(k)) is None for k in OUTCOME_COUNTERS):
            return None
        if item["attempts"] != sum(item[k] for k in OUTCOME_COUNTERS[1:]):
            return None
        seen.add(token)
        rows.append({"token_id": token, "agent_id": _text(item.get("agentId")),
                     **{k: item[k] for k in OUTCOME_COUNTERS}})
    if raw["count"] != len(rows):
        return None
    return {"count": len(rows), "seats": sorted(rows, key=cmp_to_key(_compare))}


def _coerce_records(raw: object) -> dict | None:
    if not isinstance(raw, dict) or not isinstance(raw.get("seats"), list):
        return None
    converted = []
    for row in raw["seats"]:
        if not isinstance(row, dict):
            return None
        converted.append({"tokenId": row.get("token_id"), "agentId": row.get("agent_id"),
                          **{k: row.get(k) for k in OUTCOME_COUNTERS}})
    return normalize_records({"count": raw.get("count"), "seats": converted})


def seat_outcome(records: dict | None, token: int | None) -> dict | None:
    if records is None or token is None:
        return None
    out = dict.fromkeys(SWARM_SEAT_OUTCOME_FIELDS)
    out.update(token_id=token, listed=False, ranked_of=records["count"])
    for rank, row in enumerate(records["seats"], 1):
        if row["token_id"] == token:
            out.update({k: row[k] for k in OUTCOME_COUNTERS})
            out.update(listed=True, rank=rank, accept_rate=ratio(row["accepted"], row["attempts"]))
            break
    return out


def _event_owners(raw: object) -> dict[int, str]:
    items = enumerate(raw) if isinstance(raw, list) else raw.items() if isinstance(raw, dict) else ()
    return {sw._served_token(token): address(owner) for token, owner in items
            if sw._served_token(token) is not None and address(owner) is not None}


def _event_details(item: dict, seats: object, owners: dict[int, str], holdings: Counter) -> dict:
    details = {key: item[field] for key, field in _EVENT_TEXT.items() if isinstance(item.get(field), str)}
    details.update({key: item[field] for key, field in _EVENT_COUNTS.items() if count(item.get(field)) is not None})
    token = sw._served_token(item.get("tokenId"))
    if item["kind"] == "agent" and token is not None:
        seat = seats.get(str(token)) if isinstance(seats, dict) else None
        if isinstance(seat, dict):
            for field in ("accepted", "failed"):
                if count(seat.get(field)) is not None:
                    details["seat_" + field] = seat[field]
            last = timestamp(seat.get("last"))
            if last is not None:
                details["last_work"] = last
        owner = owners.get(token)
        if owner is not None:
            details.update(owner=owner, owner_seats=holdings[owner])
    return details


def _working_seats(seats):
    """The full seat map counts identities, independently of daemon/node totals."""
    if not isinstance(seats, dict):
        return None
    identities = set()
    busy = 0
    for key, row in seats.items():
        token = sw._served_token(key)
        if (token is None or token in identities or not isinstance(row, dict)
                or sw._served_token(row.get('tokenId')) != token or type(row.get('working')) is not bool):
            return None
        identities.add(token)
        busy += row['working']
    return busy


def normalize_overview(raw: object) -> dict | None:
    if not isinstance(raw, dict) or not isinstance(raw.get("health"), dict) or not isinstance(raw.get("counts"), dict) or not isinstance(raw.get("events"), list):
        return None
    health, counts = raw["health"], raw["counts"]
    out = dict.fromkeys(SURFBOARD_OVERVIEW_FIELDS)
    mapping = {"agents_online": "agentsOnline", "working_now": "workingNow", "accepted_24h": "acceptedLastDay",
               "jobs_24h": "jobsDoneLastDay", "oracles_24h": "oraclesDoneLastDay", "seats_enrolled": "seatsEnrolled"}
    for target, key in mapping.items():
        out[target] = count(health.get(key))
    if any(out[key] is None for key in mapping):
        return None
    out["jobs"] = count(counts.get("jobs"))
    out["inference_tokens"] = count(counts.get("inferenceTokens"))
    out["tasks_in_progress"] = count(counts.get("tasksInProgress"))
    out["launches_live"] = count(counts.get("launchesLive"))
    out["working_seats"] = _working_seats(raw.get("seats"))
    states = counts.get("jobStates")
    if not isinstance(states, dict) or any(not isinstance(k, str) or count(v) is None for k, v in states.items()):
        return None
    out["job_states"] = dict(states)
    out["services"] = {key: health.get(key + "Up") if type(health.get(key + "Up")) is bool else None
                       for key in ("verifier", "publisher", "deployer")}
    owners = raw.get("owners")
    out["owners"] = [v for v in owners if isinstance(v, str) and address(v)] if isinstance(owners, list) else None
    event_owners = _event_owners(owners)
    holdings = Counter(event_owners.values())
    events = []
    for item in reversed(raw["events"][:60]):
        if not isinstance(item, dict):
            return None
        ts = timestamp(item.get("at"))
        if ts is None or not isinstance(item.get("kind"), str):
            return None
        state = _text(item.get("state"))
        role = _text(item.get("role"))
        kind = item["kind"]
        if state is None and kind == "job":
            state = "posted"
        row = {"timestamp": ts, "kind": kind, "job_id": parse_job_id(item.get("jobId")),
               "token_id": sw._served_token(item.get("tokenId")), "agent_id": _text(item.get("agentId")),
               "role": role, "step": _text(item.get("step")), "state": state,
               "objective": _text(item.get("objective"))}
        row["key"] = version(row)
        row["details"] = _event_details(item, raw.get("seats"), event_owners, holdings)
        events.append(row)
    return {"overview": out, "events": sorted({e["key"]: e for e in events}.values(), key=lambda e: e["timestamp"])}


def normalize_hourly(raw: object) -> dict | None:
    if not isinstance(raw, dict) or type(raw.get("hours")) is not int or raw["hours"] != 24:
        return None
    points = hourly_points(raw.get("accepted"))
    until = timestamp(raw.get("until"))
    return {"until": until, "accepted": list(raw["accepted"]), "points": points} if points is not None and until is not None else None


def version(payload: object) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def normalize_supply(raw: object) -> dict | None:
    if not isinstance(raw, dict) or set(raw) != set(SURFBOARD_SUPPLY_FIELDS):
        return None
    supply = number(raw.get("total_supply"))
    return {"total_supply": supply} if supply is not None and supply > 0 else None


def source_envelope(payload: dict | None, now: float, *, prior: dict | None = None, provider_ts: float | None = None) -> dict:
    if payload is None:
        out = dict(prior or {"payload": None, "read_ts": None, "provider_ts": None, "version": None})
        out.update(attempt_ts=now, state="stale" if out["payload"] is not None else "unavailable")
        return out
    return {"payload": payload, "read_ts": now, "provider_ts": provider_ts,
            "version": version(payload), "attempt_ts": now, "state": "ok"}


def coerce_source(value: object, name: str, *, now: float) -> dict | None:
    if not isinstance(value, dict) or set(value) != {"payload", "read_ts", "provider_ts", "version", "attempt_ts", "state"}:
        return None
    if value["state"] not in ("ok", "stale", "unavailable"):
        return None
    for key in ("read_ts", "attempt_ts"):
        if value[key] is not None and (timestamp(value[key]) is None or value[key] > now + 300):
            return None
    if value["provider_ts"] is not None and timestamp(value["provider_ts"]) is None:
        return None
    if value["attempt_ts"] is None or value["read_ts"] is not None and value["read_ts"] > value["attempt_ts"]:
        return None
    payload = value["payload"]
    if payload is None:
        return dict(value) if value["read_ts"] is None and value["version"] is None and value["state"] == "unavailable" else None
    if not isinstance(payload, dict) or value["state"] == "unavailable" or value["read_ts"] is None:
        return None
    if name == "overview":
        # Check the original hash before adding optional legacy fields, so
        # migration cannot bless edited snapshots or lose useful old events.
        try:
            if value["version"] != version(payload):
                return None
        except (TypeError, ValueError, OverflowError):
            return None
        upgraded = _coerce_overview(payload)
        if upgraded is None:
            return None
        return dict(value, payload=upgraded, version=version(upgraded))
    if name == "records":
        clean = _coerce_records(payload)
    elif name == "hourly":
        clean = normalize_hourly({"hours":24,"until":payload.get("until"),"accepted":payload.get("accepted")})
    elif name == "supply":
        clean = normalize_supply(payload)
    else:
        clean = _coerce_overview(payload)
    if clean != payload or clean is None or value["version"] != version(clean):
        return None
    return dict(value)


def _coerce_overview(payload: dict) -> dict | None:
    o, events = payload.get("overview"), payload.get("events")
    if isinstance(o, dict):
        o = dict(o)
        for key in ("inference_tokens", "launches_live", "working_seats"):
            o.setdefault(key, None)
    if not isinstance(o, dict) or set(o) != set(SURFBOARD_OVERVIEW_FIELDS) or not isinstance(events, list) or len(events) > 60:
        return None
    for key in ("agents_online", "working_now", "accepted_24h", "jobs_24h", "oracles_24h", "seats_enrolled", "jobs", "tasks_in_progress", "inference_tokens", "launches_live", "working_seats"):
        if o[key] is not None and count(o[key]) is None:
            return None
    if not isinstance(o["services"], dict) or set(o["services"]) != {"verifier", "publisher", "deployer"}:
        return None
    if any(v is not None and type(v) is not bool for v in o["services"].values()):
        return None
    if not isinstance(o["job_states"], dict) or any(not isinstance(k,str) or count(v) is None for k,v in o["job_states"].items()):
        return None
    if o["owners"] is not None and (not isinstance(o["owners"],list) or any(address(v) is None for v in o["owners"])):
        return None
    from maxpane_dashboard.data.surf_models import SURFBOARD_EVENT_FIELDS
    cleaned_events = []
    for row in events:
        if not isinstance(row, dict) or set(row) not in (set(SURFBOARD_EVENT_FIELDS), set(SURFBOARD_EVENT_FIELDS) - {"details"}) or timestamp(row["timestamp"]) is None:
            return None
        if row["job_id"] is not None and parse_job_id(row["job_id"]) is None:
            return None
        if row["token_id"] is not None and count(row["token_id"]) is None:
            return None
        if any(row[k] is not None and not isinstance(row[k], str) for k in ("key", "kind", "agent_id", "role", "step", "state", "objective")):
            return None
        if row["key"] != version({k:v for k,v in row.items() if k not in ("key", "details")}):
            return None
        details = row.get("details", {})
        if not _valid_event_details(details):
            return None
        cleaned_events.append(dict(row, details=details))
    return dict(payload, overview=o, events=cleaned_events)


def _valid_event_details(details: object) -> bool:
    if not isinstance(details, dict):
        return False
    for key, value in details.items():
        if key == "owner":
            valid = address(value) is not None
        elif key in _EVENT_TEXT:
            valid = isinstance(value, str)
        elif key in (*_EVENT_COUNTS, "seat_accepted", "seat_failed", "owner_seats"):
            valid = count(value) is not None
        elif key == "last_work":
            valid = number(value) is not None and timestamp(value) is not None
        else:
            return False
        if not valid:
            return False
    return True


def footer(market: dict | None, market_source: dict, overview_source: dict, *, now: float) -> dict:
    """Keep network totals and verified-pair valuation on their own read clocks.

    Source state describes the read, while a missing optional value stays None.
    Persisted market values are revalidated before selecting cap or labelled FDV.
    """
    market = market if isinstance(market, dict) else {}
    cap, fdv = number(market.get("market_cap_usd")), number(market.get("fdv_usd"))
    overview = (overview_source["payload"] or {}).get("overview") or {}
    return {
        "market_value_usd": cap if cap is not None else fdv,
        "market_basis": "market_cap" if cap is not None else "fdv" if fdv is not None else None,
        "market_state": market_source["state"], "market_read_ts": market_source["read_ts"],
        "inference_tokens": overview.get("inference_tokens"),
        "overview_state": overview_source["state"], "overview_read_ts": overview_source["read_ts"],
        "provider_ts": overview_source["provider_ts"], "as_of": now,
    }


def canonical_board(records: dict | None, contributors: dict | None, workers: dict | None) -> tuple[list[dict] | None, dict]:
    summary = sw._board_summary_from_slots(contributors, workers)
    for key in ("seats", "attempts", "accepted", "rejected", "pending"):
        summary["receipt_" + key] = summary[key]
    for key in ("seats", *OUTCOME_COUNTERS):
        summary[key] = None
    if records is None:
        return None, summary
    summary.update(seats=records["count"], **{k:sum(r[k] for r in records["seats"]) for k in OUTCOME_COUNTERS})
    effort = {r["token_id"]: r for r in sw._board_rows_from_slots(contributors, workers) or []}
    groups = sw._worker_groups(workers)
    rows = []
    from maxpane_dashboard.data.surf_models import SURF_ROW_KEYS
    for rank, item in enumerate(records["seats"], 1):
        row = dict.fromkeys(SURF_ROW_KEYS["swarm_board_rows"])
        token = item["token_id"]
        live = sw._seat_live_from_slot(workers, token, groups=groups)
        row.update(effort.get(token, {}))
        row.update({k:item[k] for k in OUTCOME_COUNTERS})
        live_rows = groups.get(token, [])
        row.update(rank=rank, token_id=token, agent_id=item["agent_id"], accept_rate=ratio(item["accepted"], item["attempts"]),
                   runtime=sw._runtime_bucket(sw._metadata_union(live_rows,"runtimes")) if live_rows else "offline" if workers is not None else None,
                   live_state=live["live_state"] if live else None,
                   working=live["working"] if live else None,
                   paused_until_ts=live["paused_until_ts"] if live else None,
                   failures=live["failures"] if live else None)
        rows.append(row)
    return rows, summary


def hhmm(ts: object) -> str:
    stamp = timestamp(ts)
    return datetime.fromtimestamp(stamp).strftime("%H:%M") if stamp is not None else "—"


def _value(value: object, suffix: str = "") -> str:
    if number(value) is None:
        return "—"
    return f"{value:,.0f}{suffix}" if type(value) is int else f"{value:,.2f}{suffix}"


def _protocol_stats(burn, reward, fee) -> str:
    lines = []
    for label, value in (("burned", burn), ("rewarded", reward), ("fees", fee)):
        shown = "—"
        if number(value) is not None:
            amount = value
            for suffix in ("", "k", "M", "B", "T"):
                if round(amount) < 1000 or suffix == "T":
                    break
                amount /= 1000
            shown = f"{amount:.0f}{suffix}"
        lines.append(f"★ {label} {shown} IMD")
    return "\n".join(lines)


def _launchpad_volume(data, launchpad, families, now):
    snapshot = launch_volume.coerce_snapshot((launchpad or {}).get("volume_2h"), now=now)
    quote_source = families.get("quote") or {}
    quote, quote_ts = number(data.get("eth_usd")), timestamp(quote_source.get("read_ts"))
    state, points = "unavailable", None
    if snapshot is not None:
        state = snapshot["state"]
        if state == "ok":
            state = "unavailable"
            if (quote is not None and quote > 0 and quote_source.get("state") == "ok"
                    and quote_ts is not None and 0 <= now - quote_ts <= 90):
                try:
                    converted = [number(value / 10**18 * quote) for value in snapshot["points_wei"]]
                except OverflowError:
                    converted = [None]
                if all(value is not None for value in converted):
                    points = converted
                    state = "stale" if (
                        now - snapshot["read_ts"] > launch_volume.SNAPSHOT_TTL
                        or now - snapshot["head_ts"] > launch_volume.SNAPSHOT_TTL
                        or now // launch_volume.BUCKET_SECONDS * launch_volume.BUCKET_SECONDS > snapshot["until"]
                        or (families.get("launchpad") or {}).get("state", "ok") != "ok"
                        or "pad" in (data.get("degraded") or [])
                    ) else "ok"
    observed = snapshot or {}
    detail = (f"USD volume 2h · 15m buckets · {state} · {observed.get('known', '—')}/{observed.get('total', '—')} pools"
              f" · read {hhmm(observed.get('read_ts'))} · until {hhmm(observed.get('until'))}"
              f" · current ETH/USD {_value(quote)} · quote read {hhmm(quote_ts)}")
    return points, state, detail


def fleet_summary(workers, source):
    """Worker-only facts; no canonical ranking or contributor receipt denominator."""
    source = source or dict(state='unavailable', read_ts=None)
    facts = dict.fromkeys(SURFBOARD_FLEET_FIELDS)
    facts.update(leaderboard_hero._roster_source(workers, source))
    runtimes = leaderboard_hero._runtime_counts(workers, source)
    facts.update(online=runtimes['total'], runtime_known=runtimes['known'])
    if runtimes['counts'] is not None and runtimes['total']:
        counts = {row['value']: row['count'] for row in runtimes['counts']}
        for runtime in ('codex', 'claude'):
            facts[runtime + '_percent'] = counts.get(runtime, 0) / runtimes['total'] * 100
    if leaderboard_hero._complete_workers(workers, source):
        daemons = [row['daemon'].split('+', 1)[0].strip() if row['daemon'] else None
                   for row in workers['workers']]
        if daemons and all(daemons):
            facts['daemon'] = sw._mix(daemons)[0]['value']
        model = next((row for row in sw._fleet_from_slot(workers)['models']
                      if row['model'] and row['model'].strip()), None)
        if model:
            facts.update(model=model['model'], effort=model['effort'])
    return facts


def cards(data: dict, sources: dict, *, now: float, launchpad: dict | None = None, announce_read_ts: float | None = None, announce_items: list | None = None, family_sources: dict | None = None, tokens_catalogue: dict | None = None, nft_catalogue: dict | None = None, activity: dict | None = None, agent_seats: list[dict] | None = None, pool4_price_direction: str | None = None, workers: dict | None = None, worker_source: dict | None = None, current_work: dict | None = None) -> list[dict]:
    from maxpane_dashboard.analytics.surf_signals import SIGNAL_NAMES, FIRED_TTL_S, _tx_hash
    result = []
    def card(key,title,primary,secondary,detail,destination,n=None,d=None,points=None,source=None):
        state = (sources.get(source) or {}).get("state", "unavailable") if source else "active"
        if state == "ok":state="active"
        fraction=ratio(n,d)
        if source:
            detail += f" · {source} read {hhmm((sources.get(source) or {}).get('read_ts'))}"
        if n is not None and d is not None:
            detail += f" · {n:,} / {d:,}" if fraction is not None else (" · no attempts" if key in ("agent", "board") else " · no coins" if key == "launchpad" else " · no supply" if key == "pool4" else " · no flow") if d==0 else " · invalid ratio"
        row=dict.fromkeys(SURFBOARD_CARD_FIELDS)
        if state == "active" and primary in ("unavailable", "—") and secondary in ("unavailable", "—", "signals unavailable"):
            state = "unavailable"
        row.update(key=key,title=title,status=state,primary=primary,secondary=secondary,detail=detail,destination=destination,
                   meter_kind="sparkline" if points is not None else "ratio",numerator=n if fraction is not None or number(n) is not None and number(d) is not None and n == d == 0 else None,
                   denominator=d if fraction is not None or number(n) is not None and number(d) is not None and n == d == 0 else None,points=points)
        result.append(row)
    def activity_meter(token, live_state):
        observed = work_activity.project(activity, token, now=now)
        meter = work_activity.meter(observed, live_state, now=now)
        state = meter["meter_state"]
        result[-1].update(meter, status="working" if state == "busy" else state)
        activity_label = f"activity {state}" if state in ("busy", "idle", "offline", "paused") else "activity"
        result[-1]["detail"] += (f" · {activity_label} · workers read {hhmm(observed['as_of'])}"
                                f" · last work / observed stop {hhmm(observed['stopped_ts'])} · green to orange 0–24h · orange to empty 24–72h")
    states=[data.get(f"sig_{name}_state") for name in SIGNAL_NAMES]
    known=sum(s in ("ok","watch","fired") for s in states); fired=states.count("fired")
    latest = None
    replies = None
    if isinstance(announce_items, list):
        items = [item for item in announce_items if isinstance(item, dict)
                 and (stamp := timestamp(item.get("ts"))) is not None and stamp <= now
                 and _tx_hash(item.get("tx_hash")) is not None]
        posts = [item for item in items if item.get("kind") == "self"
                 and isinstance(item.get("text"), str) and item["text"].strip()]
        latest = max(posts, key=lambda item: (timestamp(item["ts"]), item["tx_hash"]), default=None)
        replies = len({_tx_hash(item["tx_hash"]) for item in items
                       if item.get("kind") in ("reply", "answer") and now-timestamp(item["ts"]) < FIRED_TTL_S})
    age = now-timestamp(latest["ts"]) if latest else None
    new_announcement = age is not None and age < FIRED_TTL_S
    reply_text = f"{replies:,} new {'reply' if replies == 1 else 'replies'}" if replies is not None else "unavailable"
    card("announce", "SURFBOARD", latest["text"] if latest else "—", reply_text,
         f"ALERT · {known}/{len(states)} detectors known · {fired} signals · 24h replies (cached channel) · last announcement {compact_age(age) if age is not None else '—'}"
         f" · post read {hhmm(announce_read_ts)} · snapshot {hhmm(data.get('as_of'))}", "dashboard",fired if known==len(states) else None,len(states) if known==len(states) else None)
    overview=data.get("surfboard_overview") or {}; hourly=data.get("surfboard_hourly") or {}
    points=hourly.get("points")
    spark_detail="24H · accepted steps per 3h"
    if points is not None:
        spark_detail+=f" · range {min(points):,}–{max(points):,} · until {hhmm(hourly.get('until'))}"
        if not any(points):spark_detail+=" · quiet 24h"
    current_work = current_work or {}
    shipped_total = count(overview.get('launches_live'))
    completed_workflows = count(current_work.get('completed_workflows'))
    card("swarm", "SHIPPED", _value(shipped_total), _value(completed_workflows, " workflows"),
         "SHIPPED · completed launches: live launches reported by the swarm"
         + " · successfully completed workflows, including superseded releases"
         + f" · workflows read {hhmm(current_work.get('workflows_read_ts'))} · " + spark_detail,
         "swarm", points=points, source='overview')
    if result[-1]['status'] == 'active':
        result[-1]['status'] = 'idle' if shipped_total is not None else 'unavailable'
    if agent_seats is None:
        agent_seats = [dict(token_id=(data.get('swarm_seat_selected') or {}).get('token_id'),
                            live=data.get('swarm_seat_live'), outcome=data.get('swarm_seat_outcome'))] + [{}]*3
    for slot, key in enumerate(SURFBOARD_AGENT_KEYS):
        seat = agent_seats[slot] if isinstance(agent_seats, (list, tuple)) and slot < len(agent_seats) else {}
        seat = seat if isinstance(seat, dict) else {}
        token = seat_token(seat.get('token_id'))
        if token is None:
            card(key, 'AGENT', '', 'type in', 'EMPTY SEAT', None)
            result[-1].update(seat_slot=slot, status='empty', meter_state='empty', meter_kind='activity')
            continue
        outcome = seat.get('outcome') if isinstance(seat.get('outcome'), dict) else {}
        if outcome.get('token_id') != token:
            outcome = {}
        live = seat.get('live') if isinstance(seat.get('live'), dict) else {}
        presence = seat.get('presence') or {}
        if presence.get('token_id') != token:
            presence = {}
        observed = work_activity.project(activity, token, now=now)
        worker_seen = live.get('live_state') in ('idle', 'working', 'paused')
        worker_known = worker_seen and observed['state'] in ('idle', 'busy')
        retained = bool(presence) and presence.get('state') != 'ok'
        use_presence = bool(presence) and (not retained or not worker_known)
        if use_presence:
            live = presence
        elif not worker_seen:
            live = {}  # Absence from /workers cannot prove disconnection or zero capacity.
        acceptance = outcome.get('accept_rate')
        active,capacity=count(live.get('working')),count(live.get('max_concurrency'))
        live_state=live.get('live_state')
        slot_text=f'{active:,}' if active is not None else '—'
        slot_text+=f' of {capacity:,} slots' if capacity is not None else ' of — slots'
        if active is not None and capacity is not None and active>capacity:
            slot_text=f'{active:,} working'  # Oracle work may exceed maxConcurrency.
        acceptance_text=(f'{acceptance:.1%} accepted' if acceptance is not None else
                         'no submitted record' if outcome.get('listed') is False else 'acceptance —')
        presence_label = 'standing' if use_presence else 'workers'
        presence_time = hhmm(presence.get('read_ts')) if use_presence else data.get('swarm_workers_as_of_hhmm') or '—'
        card(key,'AGENT',f'IDMD #{token}',slot_text,
             f"{acceptance_text} · summary cache ≤10m"
             f" · {presence_label} {live_state or '—'} · as of {presence_time}",
             'agent',source='records')
        result[-1].update(seat_slot=slot, token_id=token)
        activity_meter(token, live_state)
        if use_presence:
            state = live['live_state']
            result[-1].update(status='stale' if retained else state,
                              meter_state='busy' if state == 'working' else state)
            if retained:
                result[-1]['meter_kind'] = 'presence'
            elif state == 'idle' and (observed['state'] != 'idle' or observed['remaining'] is None):
                result[-1].update(meter_kind='presence', numerator=None)
            if state == 'offline':
                result[-1]['secondary'] = 'offline'
        elif not worker_known:
            state = 'stale' if worker_seen and observed['state'] == 'stale' else 'unavailable'
            result[-1].update(status=state, meter_state=state, numerator=None)
        if presence:
            accepting = {True: 'yes', False: 'no', None: 'unknown'}.get(presence.get('accepting_work'))
            result[-1]['detail'] += (f" · standing read {hhmm(presence.get('read_ts'))}"
                                     f" · accepting work: {accepting}"
                                     + (' · last observed presence' if retained else ''))
    fleet = fleet_summary(workers, worker_source)
    board_hero = data.get('surf_leaderboard_hero') or {}
    effort_facts, worker_facts, rate_facts = (board_hero.get(key) or {} for key in ('effort', 'workers', 'rate'))
    fleet.update(tokens=count(effort_facts.get('tokens')), jobs=count((overview.get('job_states') or {}).get('completed')),
                 capacity=count(worker_facts.get('capacity')), accept_rate=number(rate_facts.get('percent')))
    online, working = count(overview.get('agents_online')), count(overview.get('working_seats'))
    overview_state = (sources.get('overview') or {}).get('state', 'unavailable')
    card("board", "SWARM", _value(online), f'{working:,} working' if working is not None else '— working',
         f"SWARM · {_value(online)} online agents · {_value(working)} distinct working seats"
         f" · workers read {hhmm(fleet['read_ts'])}"
         f" · runtime metadata {_value(fleet['runtime_known'])}/{_value(fleet['online'])} online seats"
         " · each distinct seat counts once per runtime; both counts in each"
         " · current advertised model and effort; daemon builds combined by base version"
         + " · daemon versions " + (", ".join(row['value'] for row in sw._mix(
             worker['daemon'] for worker in workers['workers'])) if workers is not None else "—"), "board", source='overview')
    status = ('active' if working else 'idle') if working is not None else 'unavailable'
    result[-1].update(fleet_summary=fleet, status=status if overview_state == 'ok' else overview_state,
                      meter_state=fleet['state'])
    worked_ms = count((data.get('swarm_board_summary') or {}).get('wall_clock_ms'))
    result[-1].update(meter_kind='duration', numerator=worked_ms, denominator=None)
    result[-1]['detail'] += (f" · fleet worked {_value(worked_ms)} ms across all contributor devices"
                            f" · contributors read {data.get('swarm_contributors_as_of_hhmm') or '—'}"
                            f" · effort read {hhmm(effort_facts.get('read_ts'))}"
                            f" ({effort_facts.get('state', 'unavailable')})"
                            f" · capacity read {hhmm(worker_facts.get('read_ts'))}"
                            f" ({worker_facts.get('state', 'unavailable')})"
                            f" · acceptance read {hhmm(rate_facts.get('read_ts'))}"
                            f" ({rate_facts.get('state', 'unavailable')})"
                            f" · completed jobs read {hhmm((sources.get('overview') or {}).get('read_ts'))}"
                            " · successfully completed jobs; excludes cancelled, blocked and executing"
                            " · 365-day years, whole days only")
    research = current_work.get('research') or {}
    assessing, chains = count(research.get('count')), count(research.get('chains'))
    oracle_state = research.get('state', 'unavailable')
    agents = count(current_work.get('oracle_agents'))
    subtitle = f'{agents:,} agents' if agents is not None else '— agents'
    card("oracles", "RESEARCH", f"{assessing:,}" if assessing is not None else "—", subtitle,
         "RESEARCH · assessing requests from filtered active-query coverage"
         + f" · {_value(assessing)} assessing · {_value(chains)} chains"
         + f" · read {hhmm(research.get('read_ts'))}"
         + f" · agents read {hhmm(research.get('read_ts') if oracle_state == 'ok' else current_work.get('read_ts'))}"
         + f" · {current_work.get('reason') or 'Current node coverage incomplete'}"
         + " · Enter to open", "oracles")
    result[-1].update(meter_kind="oracles", meter_state=oracle_state, numerator=chains, denominator=assessing,
                     status=("assessing" if assessing else "idle") if oracle_state == "ok" else oracle_state)
    price = number(data.get("pool4_price_usd"))
    change = data.get("imd_change_24h_pct")
    valid_change = type(change) in (int, float) and number(abs(change)) is not None
    change_text = f"{change:+.2f}%" if valid_change else "—"
    share_price = number(data.get("pool4_share_price"))
    share_text = f"{share_price:,.6f}" if share_price is not None else "—"
    card("pool4","POOL4",f"{price:,.2f}" if price is not None else "unavailable","USD",
         f"1 sIMD = {share_text} IMD · 24h {change_text}"
         +f" · {data.get('pool4_network') or 'unknown network'} · price arrow compares consecutive reads","pool4_user")
    result[-1]["share_price"] = share_price
    result[-1]["status"] = ("unavailable" if price is None else
                            {"up": "active", "down": "falling"}.get(pool4_price_direction, "idle"))
    nft = dict(nft_catalogue or {})
    deployed, building, mint_open = (count(nft.get(key)) for key in ('deployed', 'building', 'mint_open'))
    primary = f"{deployed:,}" if deployed is not None else "—"
    secondary = f"{building:,} building" if building is not None else "—"
    coverage_label = "partial catalog" if nft.get('partial') is True else "observed catalog"
    card("surf-nft", "NFTS", primary, secondary,
         f"NFTS · {coverage_label} · {primary} collections · {secondary}"
         f" · {mint_open if mint_open is not None else '—'} mint open"
         f" · read {hhmm(nft.get('observed_at'))}", "surf-nft")
    result[-1].update(nft_summary=nft, meter_kind='nft',
                      meter_state='partial' if nft.get('partial') else 'ok' if deployed is not None else 'unavailable',
                      status='active' if deployed is not None else 'unavailable')
    families = family_sources or {}
    for row in result:
        names = {"announce": ("announce", "signals"), "swarm": ("hourly",),
                 "pool4": ("pool4", "quote")}.get(row["key"], ())
        states = []
        for name in names:
            source = sources.get(name) if name == "hourly" else families.get(name)
            if source is None:
                continue
            state = source.get("state", "unavailable")
            states.append(state)
            clock_label = "evaluated" if name == "signals" else "read"
            row["detail"] += f" · {name} · {clock_label} {hhmm(source.get('read_ts'))}"
        # The pure projection remains honest when callers only have the
        # legacy degradation list, even before per-family metadata is ready.
        degraded = data.get("degraded") or []
        relevant = {"announce": ("channel",),
                    "pool4": ("p4",)}.get(row["key"], ())
        if any(group in degraded for group in relevant):
            states.append("stale")
        if "unavailable" in states:
            row["status"] = "unavailable"
        elif "stale" in states:
            row["status"] = "stale"
    # Activity colors describe the event window, independently of source health;
    # retained-source states and observation clocks remain explicit in detail.
    result[0]["status"] = "active" if new_announcement else "idle" if latest else "unavailable"
    catalogue = tokens_catalogue or {}
    total = count(catalogue.get("count"))
    catalogue_state = catalogue.get("state", "unavailable")
    primary = f"{total:,}" if total is not None else "unavailable"
    if total is not None and catalogue_state == "partial":
        primary = "≥" + primary
    ranking = catalogue.get("ranking") or {}
    new = count(ranking.get("total"))
    card("swarm-tokens", "TOKENS", primary, f"{new:,} new" if new is not None else "unavailable",
         f"TOKENS · {primary if total is not None else '—'} tokens · production-chain markets · catalogue read {hhmm(catalogue.get('as_of'))}"
         f" · launched in last 24h · evaluated {hhmm(now)}", "swarm-tokens")
    result[-1]["status"] = "unavailable" if new is None else "active" if new else "idle"
    volume = catalogue.get("turnover") or {}
    result[-1].update(token_ranking=catalogue.get("ranking"), meter_kind="volume",
                     numerator=number(volume.get("value")), meter_state=volume.get("state", "unavailable"))
    volumes = [number(row.get("volume_usd")) for row in ranking.get("rows") or []]
    result[-1]["detail"] += (f" · inset: latest three launches, newest first, all ages"
                            f" · market coverage: launched in last 24h · ranked by selected-pool 24h USD volume"
                            f" · {ranking.get('known', 0)}/{ranking.get('total') if ranking.get('total') is not None else '—'} tokens"
                            f" · {'partial · ' if ranking.get('state') == 'partial' else ''}read {hhmm(ranking.get('read_ts'))}"
                            f" · ranked USD volumes {', '.join(f'{v:,.2f}' for v in volumes if v is not None) or '—'}"
                            " · price arrows compare successive loads"
                            " · rolling USD volume 24h across all launched tokens · unique selected pools"
                            f" · {volume.get('known', 0)}/{volume.get('total', '—')} tokens"
                            f" · {'partial · ' if volume.get('state') == 'partial' else ''}read {hhmm(volume.get('as_of'))}"
                            )
    work = data.get("surf_work") or {}
    summary = {key: count((work.get("summary") or {}).get(key)) for key in SURF_WORK_SUMMARY_KEYS}
    jobs, workflows = summary["jobs"], summary["workflows"]
    state = work.get("state", "unavailable")
    working_seats = count(overview.get('working_seats'))
    waiting = count(current_work.get('waiting_jobs'))
    subtitle = f'{working_seats:,} working' if working_seats is not None else '— working'
    card("work", "WORK IN PROGRESS", f"{jobs:,}" if jobs is not None else "—", subtitle,
         "WORK IN PROGRESS · " + " · ".join(f"{_value(summary[key])} {key}" for key in SURF_WORK_SUMMARY_KEYS)
         + f" · loaded {_value(work.get('jobs_loaded'))} jobs · {_value(work.get('workflows_loaded'))} workflows"
         + f" · {_value(work.get('details_loaded'))}/{_value(work.get('details_expected'))} details"
         + f" · current nodes {_value(current_work.get('jobs_loaded'))}/{_value(current_work.get('jobs_expected'))} jobs"
         + f" · nodes read {hhmm(current_work.get('read_ts'))}"
         + " · working agents: distinct busy seats in the full swarm roster"
         + f" · agents read {hhmm((sources.get('overview') or {}).get('read_ts'))}"
         + f" · {_value(waiting)} unfinished jobs without a working node"
         + (" · partial" if work.get("partial") else "")
         + f" · read {hhmm(work.get('read_ts'))} · Enter to open", "work")
    result[-1].update(work_summary=summary, meter_kind="work", meter_state=state,
                     status=("active" if working_seats else "idle") if state == "ok" and jobs is not None else
                     "stale" if state == "stale" else "unavailable")
    return result


def coerce_rank_basis(payload: object) -> dict | None:
    if not isinstance(payload, dict) or payload.get("basis") != RANK_BASIS:
        return {"basis": RANK_BASIS, "ranks": {}}
    ranks = sw.coerce_rank_slot(payload.get("ranks"))
    return {"basis": RANK_BASIS, "ranks": ranks} if ranks is not None else None
