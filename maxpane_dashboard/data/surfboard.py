"""Validated independent IMD snapshots and plain rack projections.

No I/O here. The existing SurfManager owns source tasks and persists these whole
source envelopes. Overview seats are intentionally never outcome authority.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from functools import cmp_to_key
from typing import Any

from maxpane_dashboard.analytics.surf_ids import parse_job_id
from maxpane_dashboard.analytics.surfboard import count, number, ratio, hourly_points, compact_age
from maxpane_dashboard.data import surf_swarm as sw
from maxpane_dashboard.analytics.surf_launch_checks import address
from maxpane_dashboard.data.surf_models import (
    SURFBOARD_CARD_FIELDS, SURFBOARD_OVERVIEW_FIELDS, SWARM_SEAT_OUTCOME_FIELDS,
)

OUTCOME_COUNTERS = ("attempts", "accepted", "rejected", "failed", "pending")
SOURCE_SLOTS = {"overview": "surfboard_overview", "records": "surfboard_records", "hourly": "surfboard_hourly"}
RANK_BASIS = "seat-records-v1"


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
    states = counts.get("jobStates")
    if not isinstance(states, dict) or any(not isinstance(k, str) or count(v) is None for k, v in states.items()):
        return None
    out["job_states"] = dict(states)
    out["services"] = {key: health.get(key + "Up") if type(health.get(key + "Up")) is bool else None
                       for key in ("verifier", "publisher", "deployer")}
    owners = raw.get("owners")
    out["owners"] = [v for v in owners if isinstance(v, str) and address(v)] if isinstance(owners, list) else None
    events = []
    for item in raw["events"][:60]:
        if not isinstance(item, dict):
            return None
        ts = timestamp(item.get("at"))
        if ts is None or not isinstance(item.get("kind"), str):
            return None
        state = _text(item.get("state"))
        role = _text(item.get("role"))
        kind = item["kind"]
        if state in ("running", "assigned", "executing"):
            state = "reviewing" if role in ("review", "judge", "audit") else "building"
        elif state is None and kind == "job":
            state = "posted"
        row = {"timestamp": ts, "kind": kind, "job_id": parse_job_id(item.get("jobId")),
               "token_id": sw._served_token(item.get("tokenId")), "agent_id": _text(item.get("agentId")),
               "role": role, "step": _text(item.get("step")), "state": state,
               "objective": _text(item.get("objective"))}
        row["key"] = version(row)
        events.append(row)
    return {"overview": out, "events": sorted({e["key"]: e for e in events}.values(), key=lambda e: (e["timestamp"], e["key"]))}


def normalize_hourly(raw: object) -> dict | None:
    if not isinstance(raw, dict) or type(raw.get("hours")) is not int or raw["hours"] != 24:
        return None
    points = hourly_points(raw.get("accepted"))
    until = timestamp(raw.get("until"))
    return {"until": until, "accepted": list(raw["accepted"]), "points": points} if points is not None and until is not None else None


def version(payload: object) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


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
    if name == "overview" and isinstance(payload.get("overview"), dict) and "inference_tokens" not in payload["overview"]:
        # This optional field was added after overview envelopes shipped. Check
        # the original hash before upgrading, so migration cannot bless edits.
        try:
            if value["version"] != version(payload):
                return None
        except (TypeError, ValueError, OverflowError):
            return None
        upgraded = dict(payload, overview=dict(payload["overview"], inference_tokens=None))
        if _coerce_overview(upgraded) is None:
            return None
        return dict(value, payload=upgraded, version=version(upgraded))
    if name == "records":
        clean = _coerce_records(payload)
    elif name == "hourly":
        clean = normalize_hourly({"hours":24,"until":payload.get("until"),"accepted":payload.get("accepted")})
    else:
        clean = _coerce_overview(payload)
    if clean != payload or clean is None or value["version"] != version(clean):
        return None
    return dict(value)


def _coerce_overview(payload: dict) -> dict | None:
    o, events = payload.get("overview"), payload.get("events")
    if not isinstance(o, dict) or set(o) != set(SURFBOARD_OVERVIEW_FIELDS) or not isinstance(events, list) or len(events) > 60:
        return None
    for key in ("agents_online", "working_now", "accepted_24h", "jobs_24h", "oracles_24h", "seats_enrolled", "jobs", "tasks_in_progress", "inference_tokens"):
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
    for row in events:
        if not isinstance(row, dict) or set(row) != set(SURFBOARD_EVENT_FIELDS) or timestamp(row["timestamp"]) is None:
            return None
        if row["job_id"] is not None and parse_job_id(row["job_id"]) is None:
            return None
        if row["token_id"] is not None and count(row["token_id"]) is None:
            return None
        if any(row[k] is not None and not isinstance(row[k], str) for k in ("key", "kind", "agent_id", "role", "step", "state", "objective")):
            return None
        if row["key"] != version({k:v for k,v in row.items() if k != "key"}):
            return None
    return payload


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
        live = sw._seat_live_from_slot(workers, token)
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
        return "unavailable"
    return f"{value:,.0f}{suffix}" if type(value) is int else f"{value:,.2f}{suffix}"


def cards(data: dict, sources: dict, *, now: float, launchpad: dict | None = None, announce_read_ts: float | None = None, family_sources: dict | None = None) -> list[dict]:
    from maxpane_dashboard.analytics.surf_signals import SIGNAL_NAMES
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
        if state == "active" and primary == "unavailable" and (secondary == "unavailable" or secondary == "signals unavailable"):
            state = "unavailable"
        if key == "protocol":
            state = "experimental"
        row.update(key=key,title=title,status=state,primary=primary,secondary=secondary,detail=detail,destination=destination,
                   meter_kind="sparkline" if points is not None else "ratio",numerator=n if fraction is not None or number(n) is not None and number(d) is not None and n == d == 0 else None,
                   denominator=d if fraction is not None or number(n) is not None and number(d) is not None and n == d == 0 else None,points=points)
        result.append(row)
    states=[data.get(f"sig_{name}_state") for name in SIGNAL_NAMES]
    known=sum(s in ("ok","watch","fired") for s in states); fired=states.count("fired")
    age=data.get("feed_last_post_age_s")
    card("announce","ANNOUNCE",compact_age(age),f"{fired} fired" if known else "signals unavailable",
         f"ALERT · {known}/{len(states)} detectors known · post read {hhmm(announce_read_ts)} · snapshot {hhmm(data.get('as_of'))}", "dashboard",fired if known==len(states) else None,len(states) if known==len(states) else None)
    overview=data.get("surfboard_overview") or {}; hourly=data.get("surfboard_hourly") or {}
    points=hourly.get("points")
    spark_detail="24H · accepted steps per 3h"
    if points is not None:
        spark_detail+=f" · range {min(points):,}–{max(points):,} · until {hhmm(hourly.get('until'))}"
        if not any(points):spark_detail+=" · quiet 24h"
    card("swarm","SWARM",_value(overview.get("agents_online")," online"),_value(overview.get("working_now")," working"),spark_detail,"swarm",points=points,source="overview")
    outcome=data.get("swarm_seat_outcome") or {}; selected=data.get("swarm_seat_selected") or {}
    token=selected.get("token_id"); acceptance=outcome.get("accept_rate")
    card("agent","AGENT",f"IDMD #{token}" if token is not None else "choose a seat",
         f"{acceptance:.1%} accepted" if acceptance is not None else "no submitted record" if outcome.get("listed") is False else "acceptance unavailable",
         "PASS · submitted work · summary cache ≤10m","agent",outcome.get("accepted"),outcome.get("attempts"),source="records")
    summary=data.get("swarm_board_summary") or {}; rank=outcome.get("rank")
    card("board","BOARD",_value(summary.get("seats")," seats"),f"rank #{rank}" if rank is not None else "rank unavailable",
         "PASS · recorded-seat fleet · summary cache ≤10m","board",summary.get("accepted"),summary.get("attempts"),source="records")
    lp=launchpad or {}; swaps=lp.get("swaps_by_coin");cursor=lp.get("cursor");population=lp.get("coin_count")
    complete=(count(population) is not None and lp.get("launch_count")==population and isinstance(cursor,dict)
              and count(cursor.get("last_block")) is not None and isinstance(cursor.get("launches"),dict) and len(cursor["launches"])==population and isinstance(swaps,dict)
              and set(swaps)<=set(cursor["launches"]) and all(count(n) is not None for n in swaps.values()))
    active=sum(n>0 for n in swaps.values()) if complete else None
    card("launchpad","LAUNCHPAD",_value(data.get("launchpad_coin_count")," coins"),_value(data.get("launchpad_new_24h")," new / 24h"),
         "TRADE · coins traded / full factory"+(" · incomplete coverage" if not complete else "")+f" · as of {data.get('launchpad_as_of_hhmm') or '—'}","launchpad",active,population if complete else None)
    card("pool4","POOL4",_value(data.get("pool4_price_usd")," USD"),_value(data.get("pool4_trailing_return_pct"),"% / 7d"),
         "STAKE · vault assets / token supply"+f" · {data.get('pool4_network') or 'unknown network'}","pool4_user",data.get("pool4_vault_assets"),data.get("pool4_total_supply"))
    burn=data.get("pool4_total_burned");reward=data.get("pool4_total_rewarded");fee=data.get("pool4_total_fee_token")
    denominator=sum((burn,reward,fee)) if all(number(x) is not None for x in (burn,reward,fee)) else None
    card("protocol","PROTOCOL",_value(burn," burned"),_value(reward," rewarded"),
         "BURN · measured flow · EXPERIMENTAL"+f" · {data.get('pool4_network') or 'unknown network'} · as of {data.get('pool4_as_of_hhmm') or '—'}","pool4",burn,denominator)
    families = family_sources or {}
    for row in result:
        names = {"announce": ("announce", "signals"), "swarm": ("hourly",),
                 "launchpad": ("launchpad",), "pool4": ("pool4", "market"),
                 "protocol": ("pool4",)}.get(row["key"], ())
        states = []
        for name in names:
            source = sources.get(name) if name == "hourly" else families.get(name)
            if source is None:
                continue
            state = source.get("state", "unavailable")
            states.append(state)
            clock_label = "evaluated" if name == "signals" else "read"
            row["detail"] += f" · {name} {state} · {clock_label} {hhmm(source.get('read_ts'))}"
        # The pure projection remains honest when callers only have the
        # legacy degradation list, even before per-family metadata is ready.
        degraded = data.get("degraded") or []
        relevant = {"announce": ("channel",), "launchpad": ("pad",),
                    "pool4": ("p4", "market"), "protocol": ("p4",)}.get(row["key"], ())
        if any(group in degraded for group in relevant):
            states.append("stale")
        if "unavailable" in states:
            row["status"] = "unavailable"
        elif "stale" in states:
            row["status"] = "stale"
    for key,title in (("swarm-tokens","SWARM TOKENS"),("portfolio","PORTFOLIO"),("earnings","EARNINGS")):
        row=dict.fromkeys(SURFBOARD_CARD_FIELDS);row.update(key=key,title=title,status="planned",primary="planned",secondary="coming soon",detail=f"{title} · planned dashboard")
        result.append(row)
    return result


def coerce_rank_basis(payload: object) -> dict | None:
    if not isinstance(payload, dict) or payload.get("basis") != RANK_BASIS:
        return {"basis": RANK_BASIS, "ranks": {}}
    ranks = sw.coerce_rank_slot(payload.get("ranks"))
    return {"basis": RANK_BASIS, "ranks": ranks} if ranks is not None else None
