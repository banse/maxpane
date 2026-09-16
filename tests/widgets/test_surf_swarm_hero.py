from maxpane_dashboard.widgets.surf.swarm_hero import SurfSwarmHero, UNAVAILABLE
from tests.widgets.surf_compositing import composite_lines

KW = {"swarm_agents_online": 2, "swarm_agents_enrolled": 3, "swarm_working_now": 0,
      "swarm_accepted_today": 13, "swarm_jobs_in_flight": 2, "swarm_jobs_blocked": 6,
      "swarm_services_up": {"verifier": True, "publisher": True, "deployer": True}}


async def _hero(**kwargs):
    merged = {**KW, **kwargs}
    lines = await composite_lines(SurfSwarmHero, (120, 8), **merged)
    return "\n".join(lines)


async def test_the_three_cards_carry_their_numbers():
    text = await _hero()
    assert "AGENTS" in text and "2 of 3" in text
    assert "IN FLIGHT" in text and "2" in text
    assert "ACCEPTED TODAY" in text and "13" in text


async def test_a_blocked_count_is_named_beside_in_flight():
    assert "6 blocked" in await _hero()


async def test_an_unread_count_says_so_and_never_prints_zero():
    text = await _hero(swarm_agents_online=None, swarm_agents_enrolled=None)
    assert UNAVAILABLE in text
    assert "0 of 0" not in text


async def test_a_real_zero_is_a_zero():
    text = await _hero(swarm_jobs_in_flight=0, swarm_jobs_blocked=0)
    assert UNAVAILABLE not in text.split("IN FLIGHT")[1].split("ACCEPTED")[0]


async def test_a_service_that_is_down_is_named():
    text = await _hero(swarm_services_up={"verifier": False, "publisher": True, "deployer": True})
    assert "verifier down" in text
