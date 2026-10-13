"""Deterministic hub display cases; no transport, clock or user cache."""
from copy import deepcopy

STAMP = 1791496800.0


def hub_payload(kind="normal"):
    """Normal, stress, unavailable and hostile prose at the same source instant."""
    definitions = (
        ("announce", "SURFBOARD", "dashboard", "You can now deploy via the swarm on rh and mainnet. More networks soon.", "7 new replies", 4, 11),
        ("swarm", "SWARM", "swarm", "863 online", "9 working", None, None),
        ("agent", "AGENT", "agent", "IDMD #420", "0 of 3 slots", 43200, 86400),
        ("board", "LEADERBOARD", "board", "527", "4,176 accepted jobs", 86400, 86400),
        ("launchpad", "LAUNCHPAD", "launchpad", "208", "0 new", 0, 208),
        ("pool4", "POOL4", "pool4_user", "7.90", "USD", None, None),
        ("protocol", "PROTOCOL", "pool4", "★ burned 33k IMD\n★ rewarded 6k IMD\n★ fees 4k IMD", "0.47% of supply", 60, 100),
        ("swarm-tokens", "TOKENS", "swarm-tokens", "116", "4 new", None, None),
    )
    cards = []
    for key, title, destination, primary, secondary, numerator, denominator in definitions:
        cards.append(dict(key=key, title=title, destination=destination,
                          seat_slot=0 if key == "agent" else None,
                          token_id=420 if key == "agent" else None,
                          status="experimental" if key == "protocol" else "idle" if key == "agent" else "working" if key == "board" else "active",
                          primary=primary, secondary=secondary, token_ranking=None, top_agents=None,
                          detail=f"{title} · exact {numerator}/{denominator} · read 22:00 · source cache ≤10m",
                          meter_kind="sparkline" if key in ("swarm", "launchpad") else "activity" if key in ("agent", "board") else "ratio" if key != "swarm-tokens" else None,
                          meter_state={"agent": "idle", "board": "busy", "launchpad": "ok"}.get(key),
                          share_price=1.3029864737732294 if key == "pool4" else None,
                          numerator=numerator, denominator=denominator,
                          points=([1, 2, 3, 4, 3, 2, 1, 8] if key == "swarm" else
                                  [1200, 900, 1500, 2100, 1800, 3600, 2400, 4200]
                                  if key == "launchpad" else None)))
        if key in ("agent", "board"):
            cards[-1]["detail"] = (f"{title} · workers read 22:00 · observed stop 12h ago"
                                   if key == "agent" else f"{title} · workers read 22:00 · busy")
        elif key == "pool4":
            cards[-1]["detail"] = "POOL4 · 1 sIMD = 1.302986 IMD · pool4 ok · read 22:00"
        elif key == "swarm-tokens":
            cards[-1]["detail"] = "TOKENS · USD volume 24h · 4/4 eligible markets · ok · source 22:00 · SFPT $300 · RAI $200 · TDEMO $0"
    cards[-1]['token_ranking'] = dict(rows=[
        dict(id='eth:sfpt', age_s=7200, symbol='SFPT', chain='eth', volume_usd=300., price_direction='up'),
        dict(id='rh:rai', age_s=18000, symbol='RAI', chain='rh', volume_usd=200., price_direction='down'),
        dict(id='eth:tdemo', age_s=14400, symbol='TDEMO', chain='eth', volume_usd=0., price_direction=None),
    ], newest=dict(id='eth:new', age_s=300, symbol='FRESH', chain='eth'),
        state='ok', read_ts=STAMP, known=4, total=4)
    next(card for card in cards if card['key'] == 'board')['top_agents'] = [
        dict(rank=1, token_id=527, accepted=4176), dict(rank=2, token_id=12, accepted=3001),
        dict(rank=3, token_id=3, accepted=987)]
    cards.append(dict(key="work", title="WORK IN PROGRESS", destination="work", status="active",
                      seat_slot=None, token_id=None, primary="5", secondary="1 workflow",
                      detail="WORK IN PROGRESS · 5 jobs · 1 workflow · 5 build · 4 review · read 22:00",
                      meter_kind="work", meter_state="ok", share_price=None,
                      numerator=None, denominator=None, points=None, token_ranking=None, top_agents=None,
                      work_summary=dict(jobs=5, workflows=1, seats=7, build=5, review=4, blocked=0)))
    for slot, key in enumerate(("agent-2", "agent-3", "agent-4"), start=1):
        cards.append(dict(key=key, title="AGENT", destination=None, status="empty",
                          primary="", secondary="type in", detail="AGENT · empty seat",
                          seat_slot=slot, token_id=None, meter_kind="activity", meter_state="empty",
                          share_price=None, numerator=None, denominator=None, points=None, token_ranking=None, top_agents=None))
    overview = dict(agents_online=863, working_now=9, jobs_24h=1094, oracles_24h=237,
                    accepted_24h=32579, seats_enrolled=894,
                    services=dict(verifier=True, publisher=True, deployer=True))
    footer = dict(market_value_usd=33690000., market_basis="market_cap", market_state="ok",
                  market_read_ts=STAMP, inference_tokens=189121393249,
                  overview_state="ok", overview_read_ts=STAMP,
                  provider_ts=STAMP-10, as_of=STAMP)
    events = [dict(key=f"event-{i}", timestamp=STAMP+i, kind="node", job_id=f"aaaaaaaa-aaaa-4aaa-8aaa-{i//3:012d}",
                   token_id=420+i, agent_id=None, role="reviewer", step="review", state="accepted",
                   objective=f"Review dashboard change {i}") for i in range(60)]
    sources = {name: dict(state="ok", read_ts=STAMP, attempt_ts=STAMP, provider_ts=None,
                         version="display-fixture", payload=None) for name in ("overview", "records", "hourly")}
    if kind == "stress":
        for card in cards[:8]:
            card["primary"] = "999.9K units"
            card["secondary"] = "100.0% accepted"
        next(card for card in cards if card["key"] == "agent").update(
            status="working", primary="IDMD #99999", token_id=99999, secondary="99,999 of 99,999 slots",
            meter_state="busy", numerator=86400, denominator=86400)
        next(card for card in cards if card["key"] == "announce").update(
            primary="You can now deploy via the swarm on rh and mainnet. " * 4, secondary="99,999 new replies")
        next(card for card in cards if card["key"] == "board").update(
            primary="99999", secondary="99,999,999 accepted jobs", top_agents=[
                dict(rank=1, token_id=99999, accepted=99999999),
                dict(rank=2, token_id=9999, accepted=9999999),
                dict(rank=3, token_id=999, accepted=999999)])
        next(card for card in cards if card["key"] == "launchpad").update(
            primary="999,999", secondary="999,999 new")
        next(card for card in cards if card["key"] == "pool4").update(
            primary="999,999.99", secondary="USD")
        next(card for card in cards if card["key"] == "protocol").update(
            primary="★ burned 1M IMD\n★ rewarded 100k IMD\n★ fees 10k IMD", secondary="17.40% of supply")
        next(card for card in cards if card["key"] == "swarm-tokens").update(
            primary="1,234,567", secondary="99,999 new")
        next(card for card in cards if card["key"] == "work").update(
            primary="124", secondary="100 workflows",
            work_summary=dict(jobs=124, workflows=100, seats=4800, build=4800, review=4800, blocked=0))
        overview = dict(agents_online=99999, working_now=99999, jobs_24h=999999,
                        oracles_24h=99999, accepted_24h=99999999, seats_enrolled=99999,
                        services=dict(verifier=False, publisher=None, deployer=True))
        footer.update(market_value_usd=999999999999., inference_tokens=999999999999999,
                      market_basis="fdv", market_state="stale", overview_state="stale")
    elif kind == "unavailable":
        for card in cards[:8]:
            card.update(status="unavailable", primary="unavailable",
                        secondary={"pool4":"USD", "protocol":"unavailable"}.get(card["key"], "unavailable"),
                        meter_state="unavailable", share_price=None,
                        numerator=None, denominator=None, points=None)
            card['token_ranking'] = None
            card['top_agents'] = None
        next(card for card in cards if card["key"] == "work").update(
            status="unavailable", primary="—", secondary="unavailable", meter_state="unavailable",
            work_summary=dict.fromkeys(("jobs", "workflows", "seats", "build", "review", "blocked")))
        overview, events = None, None
        footer.update(market_value_usd=None, market_basis=None, market_state="unavailable",
                      market_read_ts=None, inference_tokens=None, overview_state="unavailable",
                      overview_read_ts=None, provider_ts=None)
        sources = {name: dict(source, state="unavailable", read_ts=None) for name, source in sources.items()}
    elif kind == "wide":
        events[-1]["objective"] = "測試界面 " * 30 + "[bold] literal ANSI \x1b[31m"
    return deepcopy(dict(surfboard_cards=cards, surfboard_overview=overview,
                         surfboard_events=events, surfboard_hourly=None, surfboard_sources=sources,
                         surfboard_footer=footer,
                         last_updated_seconds_ago=0, error_count=0, poll_interval=30))


class HubPayloadManager:
    def __init__(self, payload):
        self.payload = payload

    async def fetch_hub_snapshot(self):
        return deepcopy(self.payload)
