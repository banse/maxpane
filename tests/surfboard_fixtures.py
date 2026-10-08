"""Deterministic hub display cases; no transport, clock or user cache."""
from copy import deepcopy

STAMP = 1791496800.0


def hub_payload(kind="normal"):
    """Normal, stress, unavailable and hostile prose at the same source instant."""
    definitions = (
        ("announce", "ANNOUNCE", "dashboard", "2d 19h ago", "4 fired", 4, 11),
        ("swarm", "SWARM", "swarm", "863 online", "9 working", None, None),
        ("agent", "AGENT", "agent", "IDMD #420", "95.9% accepted", 3253, 3392),
        ("board", "BOARD", "board", "892 seats", "rank #69", 3253, 3392),
        ("launchpad", "LAUNCHPAD", "launchpad", "208 coins", "0 new / 24h", 0, 208),
        ("pool4", "POOL4", "pool4_user", "7.90 USD", "1.40% / 7d", 350, 1000),
        ("protocol", "PROTOCOL", "pool4", "33.3K burned", "5.9K rewarded", 60, 100),
    )
    cards = []
    for key, title, destination, primary, secondary, numerator, denominator in definitions:
        cards.append(dict(key=key, title=title, destination=destination,
                          status="experimental" if key == "protocol" else "active",
                          primary=primary, secondary=secondary,
                          detail=f"{title} · exact {numerator}/{denominator} · read 22:00 · source cache ≤10m",
                          meter_kind="sparkline" if key == "swarm" else "ratio",
                          numerator=numerator, denominator=denominator,
                          points=[1, 2, 3, 4, 3, 2, 1, 8] if key == "swarm" else None))
    for key, title in (("swarm-tokens", "SWARM TOKENS"), ("portfolio", "PORTFOLIO"), ("earnings", "EARNINGS")):
        cards.append(dict(key=key, title=title, destination=None, status="planned",
                          primary="coming soon", secondary="future dashboard", detail="planned / coming soon",
                          meter_kind=None, numerator=None, denominator=None, points=None))
    overview = dict(agents_online=863, working_now=9, jobs_24h=1094, oracles_24h=237,
                    accepted_24h=32579, seats_enrolled=894)
    events = [dict(key=f"event-{i}", timestamp=STAMP+i, kind="node", job_id=f"aaaaaaaa-aaaa-4aaa-8aaa-{i//3:012d}",
                   token_id=420+i, agent_id=None, role="reviewer", step="review", state="accepted",
                   objective=f"Review dashboard change {i}") for i in range(60)]
    sources = {name: dict(state="ok", read_ts=STAMP, attempt_ts=STAMP, provider_ts=None,
                         version="display-fixture", payload=None) for name in ("overview", "records", "hourly")}
    if kind == "stress":
        for card in cards[:7]:
            card["primary"] = "999.9K units"
            card["secondary"] = "100.0% accepted"
        overview = dict(agents_online=99999, working_now=99999, jobs_24h=999999,
                        oracles_24h=99999, accepted_24h=99999999, seats_enrolled=99999)
    elif kind == "unavailable":
        for card in cards[:7]:
            card.update(status="unavailable", primary="unavailable", secondary="unavailable",
                        numerator=None, denominator=None, points=None)
        overview, events = None, None
        sources = {name: dict(source, state="unavailable", read_ts=None) for name, source in sources.items()}
    elif kind == "wide":
        events[-1]["objective"] = "測試界面 " * 30 + "[bold] literal ANSI \x1b[31m"
    return deepcopy(dict(surfboard_cards=cards, surfboard_overview=overview,
                         surfboard_events=events, surfboard_hourly=None, surfboard_sources=sources,
                         last_updated_seconds_ago=0, error_count=0, poll_interval=30))


class HubPayloadManager:
    def __init__(self, payload):
        self.payload = payload

    async def fetch_hub_snapshot(self):
        return deepcopy(self.payload)
