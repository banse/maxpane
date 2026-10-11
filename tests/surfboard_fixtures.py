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
        ("swarm-tokens", "LAUNCHES", "swarm-tokens", "116", "2 new", None, None),
    )
    cards = []
    for key, title, destination, primary, secondary, numerator, denominator in definitions:
        cards.append(dict(key=key, title=title, destination=destination,
                          status="experimental" if key == "protocol" else "idle" if key == "agent" else "working" if key == "board" else "active",
                          primary=primary, secondary=secondary,
                          detail=f"{title} · exact {numerator}/{denominator} · read 22:00 · source cache ≤10m",
                          meter_kind="sparkline" if key in ("swarm", "swarm-tokens", "launchpad") else "activity" if key in ("agent", "board") else "ratio",
                          meter_state={"agent": "idle", "board": "busy", "swarm-tokens": "ok", "launchpad": "ok"}.get(key),
                          share_price=1.3029864737732294 if key == "pool4" else None,
                          numerator=numerator, denominator=denominator,
                          points=([1, 2, 3, 4, 3, 2, 1, 8] if key == "swarm" else
                                  [1200, 900, 1500, 2100, 1800, 3600, 2400, 4200]
                                  if key in ("swarm-tokens", "launchpad") else None)))
        if key in ("agent", "board"):
            cards[-1]["detail"] = (f"{title} · workers read 22:00 · observed stop 12h ago"
                                   if key == "agent" else f"{title} · workers read 22:00 · busy")
        elif key == "pool4":
            cards[-1]["detail"] = "POOL4 · 1 sIMD = 1.302986 IMD · pool4 ok · read 22:00"
        elif key == "swarm-tokens":
            cards[-1]["detail"] = "LAUNCHES · USD volume 24h · 116/116 markets · read 22:00"
    cards[-1]['latest_launches'] = [
        dict(age_s=7200, symbol='SFPT', chain='eth', lp_state='two-sided', liquidity_state='ok', paired_symbol='ETH'),
        dict(age_s=14400, symbol='RAI', chain='rh', lp_state='one-token', liquidity_state='ok', paired_symbol='IMD'),
        dict(age_s=18000, symbol='TDEMO', chain='eth', lp_state='unknown', liquidity_state='unknown', paired_symbol=None),
    ]
    for key, title in (("portfolio", "PORTFOLIO"),):
        cards.append(dict(key=key, title=title, destination=None, status="planned",
                          primary="coming soon", secondary="future dashboard", detail="planned / coming soon",
                          meter_kind=None, meter_state=None, share_price=None,
                          numerator=None, denominator=None, points=None))
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
            status="working", primary="IDMD #99999", secondary="99,999 of 99,999 slots",
            meter_state="busy", numerator=86400, denominator=86400)
        next(card for card in cards if card["key"] == "announce").update(
            primary="You can now deploy via the swarm on rh and mainnet. " * 4, secondary="99,999 new replies")
        next(card for card in cards if card["key"] == "board").update(
            primary="99999", secondary="99,999,999 accepted jobs")
        next(card for card in cards if card["key"] == "launchpad").update(
            primary="999,999", secondary="999,999 new")
        next(card for card in cards if card["key"] == "pool4").update(
            primary="999,999.99", secondary="USD")
        next(card for card in cards if card["key"] == "protocol").update(
            primary="★ burned 1M IMD\n★ rewarded 100k IMD\n★ fees 10k IMD", secondary="17.40% of supply")
        next(card for card in cards if card["key"] == "swarm-tokens").update(
            primary="1,234,567", secondary="99,999 new")
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
            card['latest_launches'] = None
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
