"""Shared, network-free AGENT hero projection for committed screen fixtures."""


def project_agent_payload(payload: dict | None) -> dict:
    """Give legacy layout captures the new hero through its production fold.

    The observations are synthetic and fixed; underlying seat/worker/record
    facts remain the committed captures. No manager, clock or cache is read.
    Reproject after overrides so missing-source and busy fixtures stay honest.
    """
    from maxpane_dashboard.data.surf_agent_hero import project

    data = dict(payload or {})
    now = 1_791_806_400.0
    def observation(known):
        return dict(state="ok" if known else "unavailable", read_ts=now if known else None)

    live = data.get("swarm_seat_live")
    selected = data.get("swarm_seat_selected") or {}
    sources = {
        "seat": observation(data.get("swarm_seat_state") in ("ok", "unknown_seat")),
        "rewards": observation(data.get("swarm_seat_rewards_state") == "ok"),
        "market": observation(isinstance(data.get("swarm_seat_rewards"), dict)
                              and data["swarm_seat_rewards"].get("usd") is not None),
        "records": dict(data.get("swarm_outcomes_source") or observation(False)),
        "workers": observation(isinstance(live, dict)),
        "contributors": observation(isinstance(data.get("swarm_seat_contrib"), dict)),
        "runtime": {key: observation(version is not None)
                    for key, version in (data.get("swarm_runtime_latest") or {}).items()},
    }
    activity = None
    if isinstance(live, dict) and selected.get("token_id") is not None:
        state = live.get("live_state")
        point = dict(state="busy" if state == "working" else "idle",
                     known=state in ("working", "idle", "paused", "offline"),
                     stopped_ts=None, seen_ts=now)
        activity = dict(attempt_ts=now, read_ts=now, ok=True, complete=True,
                        seats={str(selected["token_id"]): point})
    data["surf_agent_hero"] = project(data=data, sources=sources, now=now, activity=activity)
    return data
