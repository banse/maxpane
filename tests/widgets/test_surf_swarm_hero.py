from textual.app import App

from maxpane_dashboard.widgets.surf.swarm_hero import CARD_IDS, SurfSwarmHero, UNAVAILABLE
from tests.widgets.surf_compositing import composite_lines

KW = {"swarm_agents_online": 2, "swarm_agents_enrolled": 3, "swarm_working_now": 0,
      "swarm_accepted_today": 13, "swarm_jobs_in_flight": 2, "swarm_jobs_blocked": 6,
      "swarm_services_up": {"verifier": True, "publisher": True, "deployer": True}}


async def _hero(**kwargs):
    merged = {**KW, **kwargs}
    lines = await composite_lines(SurfSwarmHero, (120, 8), **merged)
    return "\n".join(lines)


async def _card_text(card_id, **kwargs):
    """Composited text of one hero card's own region, never a whole-screen slice.

    The three cards sit side by side (``Horizontal``), so a whole-screen
    string joined by rows puts all three titles on physical row 0 -- slicing
    on ``"IN FLIGHT"...."ACCEPTED"`` only ever captures the padding between
    two titles, never the value/subtitle rows underneath either one.

    ``composite_lines``'s own bare-mount-and-composite harness (mount the
    widget alone, feed it ``update_data``, read
    ``app.screen._compositor.render_strips()``), plus
    ``tests/screens/test_surf_screen.py``'s ``_region_text`` idea of slicing
    those strips to one queried widget's own ``region`` rather than the
    screen's -- applied to a *card*, found by the id in :data:`CARD_IDS`,
    rather than to the hero itself (``composite_lines``'s own
    ``region_only=True`` would still return all three cards, since the
    widget it mounts and queries is the hero, not one card inside it).
    """
    merged = {**KW, **kwargs}

    class _A(App):
        def compose(self):
            yield SurfSwarmHero()

    async with _A().run_test(size=(120, 8)) as pilot:
        hero = pilot.app.query_one(SurfSwarmHero)
        hero.update_data(**merged)
        await pilot.pause()
        card = pilot.app.query_one(f"#{card_id}")
        strips = pilot.app.screen._compositor.render_strips()
        rows = ["".join(seg.text for seg in strip) for strip in strips]
        region = card.region
        sliced = [
            rows[y][region.x : region.x + region.width]
            for y in range(max(region.y, 0), min(region.y + region.height, len(rows)))
        ]
        return "\n".join(row.rstrip() for row in sliced)


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
    text = await _card_text(
        CARD_IDS[1], swarm_jobs_in_flight=0, swarm_jobs_blocked=0
    )
    assert "0 in flight" in text
    assert "0 blocked" in text
    assert UNAVAILABLE not in text


async def test_a_service_that_is_down_is_named():
    text = await _hero(swarm_services_up={"verifier": False, "publisher": True, "deployer": True})
    assert "verifier down" in text
