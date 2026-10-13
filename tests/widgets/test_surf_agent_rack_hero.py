"""Twelve AGENT rack cards: composited facts, source state and affordances."""
import pytest
from textual.app import App

from maxpane_dashboard.themes import THEMES
from maxpane_dashboard.widgets.surf.agent_rack_hero import SurfSwarmAgentRackHero


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    async def refuse(*args, **kwargs):
        raise AssertionError("widget tests must not use the network")
    monkeypatch.setattr("httpx.AsyncClient.send", refuse)


def payload():
    source = dict(state="ok", read_ts=1791775800.)
    return dict(
        seat=dict(source, token_id=420, agent_id="8127", selected_by="saved", read_error=False),
        accepted=dict(source, listed=True, accepted=960, attempts=1000, percent=96.),
        effort=dict(source, listed=True, hours=320., output_tokens=1800000),
        rewards=dict(source, imd=12.84, usd=120.82, seats=3, usd_state="ok", usd_read_ts=1791775800., last_paid_ts=1791775680., paid_recent=True),
        rank=dict(source, listed=True, rank=27, ranked_of=1024, delta=2),
        status=dict(source, live_state="working", working=2, capacity=3, devices=2,
                    paused_until_ts=None, failures=0, last_work_ts=1791775680., last_work_kind="worked",
                    work_state="ok", work_read_ts=1791775800., meter_kind="activity", meter_state="busy", numerator=1., denominator=1.),
        owner=dict(source, address="0x0000000000000000000000000000000000000001", name="example.eth", paired_ts=1790812800.),
        runtime=dict(source, runtime="codex v1.2.3", daemon="v1.2", devices=2, update_state="current", latest_version="1.2.3",
                     checked_ts=1791775800., fleet_daemon="v1.2", fleet_count=900, fleet_total=966, daemon_differs=False),
        models=dict(source, rows=[dict(model="model A", effort="high"), dict(model="model B", effort="medium")]),
        feedback=dict(source, sent=186, submitted=4, queued=2),
        collab=dict(source, count=12, rows=[dict(token_id=527, shared_jobs=84), dict(token_id=1, shared_jobs=52)]),
        nodes=dict(source, rows=[dict(node_key="adversarial_review", accepted=500, attempts=510),
                                dict(node_key="build_contract_project", accepted=340, attempts=360),
                                dict(node_key="oracle_assess", accepted=120, attempts=130)]),
    )


class Harness(App):
    CSS = "Screen { padding: 1; background: $background; color: $text; }"
    def __init__(self, data):
        super().__init__()
        self.data = data
        self.register_theme(THEMES["matrix"])
        self.theme = "matrix"
    def compose(self):
        yield SurfSwarmAgentRackHero()
    def on_mount(self):
        self.query_one(SurfSwarmAgentRackHero).update_data(surf_agent_hero=self.data)


def strips(app, key):
    card = app.query_one(SurfSwarmAgentRackHero).query_one(f"#hero-{key}")
    region = card.region
    return [strip.crop(region.x, region.right)
            for strip in app.screen._compositor.render_strips()[region.y:region.bottom]]


def painted(app, key):
    return "\n".join(strip.text for strip in strips(app, key))


async def test_approved_twelve_cards_form_two_equal_rows_with_live_facts():
    async with Harness(payload()).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        hero = app.query_one(SurfSwarmAgentRackHero)
        cards = list(hero.children)
        assert len(cards) == 12 and hero.region.height == 19
        assert {card.region.height for card in cards} == {9}
        assert len({card.region.y for card in cards}) == 2
        assert [(card.region.x, card.region.width) for card in cards[:6]] == [(card.region.x, card.region.width) for card in cards[6:]]
        assert cards[6].region.y - cards[0].region.bottom == 1
        for key, words in {
            "seat": ("IDMD", "working", "AGENT #8127"),
            "accepted": ("of 1,000", "96%", "▰"),
            "effort": ("HOURS", "1.8M tokens", "CONTRIBUTORS"),
            "rewards": ("IMD", "$120.82", "paid "),
            "rank": ("POSITION", "of 1,024", "↑ 2"),
            "status": ("WORKER", "worked", "BUSY", "▰"),
            "owner": ("WALLET", "example.eth ⧉", "paired", "OPEN / COPY"),
            "runtime": ("codex", "v1.2.3", "daemon", "v1.2", "up to date"),
            "models": ("model A", "high", "model B", "medium", "2 models"),
            "feedback": ("sent", "186", "submitted", "4", "2 QUEUED"),
            "collab": ("SEATS", "collaborators", "TOP #527 x84"),
            "nodes": ("review", "500", "build", "340", "oracle", "120"),
        }.items():
            text = painted(app, key)
            assert all(word in text for word in words), (key, text)
        # 420 and 960, asserted as digit glyphs that actually reach the terminal.
        assert "  ╵╰─╴╰─╯" in painted(app, "seat")
        assert "╶─╯╰─╯╰─╯" in painted(app, "accepted")


async def test_owner_keeps_copy_and_explorer_links_when_name_is_hostile_or_long():
    data = payload()
    data["owner"]["name"] = "[/x]\x1b[31m evil " + "owner" * 20
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        segments = [segment for strip in strips(pilot.app, "owner") for segment in strip]
        icons = [s for s in segments if "⧉" in s.text]
        assert icons and all("@click" in s.style.meta for s in icons)
        assert any(s.style and s.style.link and "etherscan.io/address/" in s.style.link for s in segments)
        assert "‹" in painted(pilot.app, "owner") and "\x1b" not in painted(pilot.app, "owner")


@pytest.mark.parametrize("state", ["pending", "busy", "unknown_seat", "empty", "unavailable"])
async def test_detail_failure_preserves_selected_id_and_independent_records(state):
    data = payload()
    for key in ("seat", "owner", "runtime", "models", "feedback", "collab", "nodes"):
        data[key]["state"] = state
    data["seat"]["token_id"] = 9876543210
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        assert "9876543210" in painted(pilot.app, "seat")
        assert "of 1,000" in painted(pilot.app, "accepted")
        assert "example.eth" not in painted(pilot.app, "owner")
        assert "up to date" not in painted(pilot.app, "runtime")
        expected = {"unknown_seat": "never paired", "empty": "EMPTY", "pending": "loading", "busy": "busy"}.get(state, state)
        assert expected in painted(pilot.app, "owner")


async def test_zero_empty_and_unknown_facts_are_distinct_then_refresh_clears_every_card():
    data = payload()
    data["accepted"].update(accepted=0, attempts=0, percent=None)
    data["models"]["rows"] = []
    data["nodes"]["rows"] = []
    data["collab"].update(count=0, rows=[])
    data["feedback"].update(sent=0, submitted=0, queued=0)
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        assert "no attempts" in painted(app, "accepted") and "0%" not in painted(app, "accepted")
        assert "not advertised" in painted(app, "models")
        assert "no nodes yet" in painted(app, "nodes") and "NONE YET" in painted(app, "collab")
        assert "0 QUEUED" in painted(app, "feedback")
        app.query_one(SurfSwarmAgentRackHero).update_data(surf_agent_hero=None)
        await pilot.pause()
        assert all("loading" in painted(app, key) for key in data)
        assert "up to date" not in painted(app, "runtime") and "example.eth" not in painted(app, "owner")
        app.query_one(SurfSwarmAgentRackHero).update_data(surf_agent_hero=payload())
        await pilot.pause()
        assert "example.eth ⧉" in painted(app, "owner") and "960" not in painted(app, "accepted")


@pytest.mark.parametrize("live,meter,word", [("working", "busy", "BUSY"), ("idle", "idle", "IDLE"),
                                               ("offline", "offline", "OFF"), ("paused", "idle", "IDLE"), (None, "unavailable", "—")])
async def test_status_meter_colors_and_unknown_worker_never_claim_offline(live, meter, word):
    data = payload()
    data["status"].update(live_state=live, meter_state=meter, working=0 if live != "working" else 2,
                          meter_kind="activity-cooldown", numerator=.5)
    if live == "paused":
        data["status"].update(paused_until_ts=1791776800., failures=3)
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        text = painted(app, "status")
        assert word in text, text
        if live == "offline":
            assert "▱" in text and "▰" not in text
        elif live == "idle":
            assert "▱" in text and "▰" in text
        elif live == "paused":
            assert "until" in str(app.query_one("#hero-status").tooltip)
        frames = [segment for strip in strips(app, "status") for segment in strip if "┌" in segment.text]
        if live == "offline":
            assert all(segment.style.color.get_truecolor() == app.ansi_theme.ansi_colors[1] for segment in frames)


async def test_more_rows_have_visible_count_and_literal_full_tooltips():
    data = payload()
    data["models"]["rows"] = [dict(model=f"model-{n}[/x]", effort="high") for n in range(5)]
    data["nodes"]["rows"] += [dict(node_key="unknown[/x]", accepted=4, attempts=5)]
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        assert "+3 more" in painted(app, "models") and "+2 more" in painted(app, "nodes")
        assert "model-4[/x]" in str(app.query_one("#hero-models").tooltip)
        assert "unknown[/x]" in str(app.query_one("#hero-nodes").tooltip)
        assert "510 attempts" in str(app.query_one("#hero-nodes").tooltip)
        assert "#1 x52" in str(app.query_one("#hero-collab").tooltip)


async def test_stale_usd_and_runtime_checks_do_not_claim_current_values(monkeypatch):
    data = payload()
    data["rewards"].update(usd_state="stale", usd_read_ts=1791773400.)
    data["runtime"].update(state="stale", read_ts=1791774000.)
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        assert "stale" not in painted(pilot.app, "rewards")
        assert "stale" not in painted(pilot.app, "runtime") and "up to date" not in painted(pilot.app, "runtime")


async def test_tiny_and_large_numbers_fit_or_advertise_loss_on_resize():
    data = payload()
    data["rewards"]["imd"] = 4.2e-9
    data["effort"]["hours"] = 4.2e-9
    data["status"].update(working=99999, capacity=99999, devices=99999)
    async with Harness(data).run_test(size=(100, 45)) as pilot:
        await pilot.pause()
        assert "‹" in painted(pilot.app, "status")
        await pilot.resize_terminal(170, 45)
        await pilot.pause()
        for key in ("rewards", "effort"):
            assert "4.2e-09" in painted(pilot.app, key)
        assert "99,999" in painted(pilot.app, "status")


async def test_live_runtime_qualifier_and_daemon_difference_remain_readable():
    data = payload()
    data['runtime'].update(runtime='claude 2.1.296 (Claude Code)', daemon='0.1.0+aca0ff06',
        daemon_differs=True, fleet_daemon='0.1.0+20b2eed8', latest_version='2.1.296')
    data['models']['rows'] = [dict(model='claude-opus-4-1', effort='high')]
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        text = painted(pilot.app, 'runtime')
        assert 'claude' in text and '2.1.296' in text
        assert 'daemon' in text and '↑' in text
        assert 'daemon differs' in text and 'up to date' not in text
        assert '1 model' in painted(pilot.app, 'models') and '1 models' not in painted(pilot.app, 'models')
        assert '0.1.0+aca0ff06' in str(pilot.app.query_one('#hero-runtime').tooltip)
        await pilot.resize_terminal(211, 45)
        await pilot.pause()
        assert '0.1.0+aca0ff06↑' in painted(pilot.app, 'runtime')


@pytest.mark.parametrize('state', ['partial', 'stale'])
async def test_retained_facts_keep_independent_tooltip_clocks_without_source_badges(state):
    from maxpane_dashboard.widgets.fmt import hhmm
    data = payload()
    for n, section in enumerate(data.values()):
        section.update(state=state, read_ts=1791775800. - 60 * n)
    async with Harness(data).run_test(size=(170, 45)) as pilot:
        await pilot.pause()
        for key, section in data.items():
            text = painted(pilot.app, key)
            assert state not in text, (key, text)
            tooltip = str(pilot.app.query_one(f'#hero-{key}').tooltip)
            assert hhmm(section['read_ts']) in tooltip and 'stale' not in tooltip
        assert 'of 1,000' in painted(pilot.app, 'accepted')
        assert 'example.eth ⧉' in painted(pilot.app, 'owner')
        assert 'up to date' not in painted(pilot.app, 'runtime')


async def test_malformed_numbers_dates_and_nested_values_clear_old_facts_safely():
    data = payload()
    data['seat'].update(token_id=True, selected_by='[/x]')
    data['accepted'].update(accepted=float('nan'), attempts=-1, percent=float('inf'))
    data['rewards'].update(imd=True, usd=-2)
    data['owner'].update(address='0xBAD[/x]', paired_ts=1e300)
    data['status'].update(live_state='[/x]', meter_state='[/x]', last_work_ts=1e300, paused_until_ts=-2)
    data['runtime'].update(runtime='[/x]\x1b suspicious', daemon=None, devices=True, checked_ts=1e300)
    data['models']['rows'] = [None]
    data['nodes']['rows'] = [False]
    async with Harness(payload()).run_test(size=(170, 45)) as pilot:
        await pilot.pause()
        pilot.app.query_one(SurfSwarmAgentRackHero).update_data(surf_agent_hero=data)
        await pilot.pause()
        for key in ('seat', 'accepted', 'rewards', 'owner', 'models', 'nodes'):
            assert '--' in painted(pilot.app, key), (key, painted(pilot.app, key))
        assert '—' in painted(pilot.app, 'status')
        assert 'OFF' not in painted(pilot.app, 'status')
        assert 'up to date' not in painted(pilot.app, 'runtime')
        assert '⧉' not in painted(pilot.app, 'owner')
        assert '[/x]' in str(pilot.app.query_one('#hero-runtime').tooltip)


@pytest.mark.parametrize('state', ['pending', 'unavailable', 'unknown_seat', 'empty'])
async def test_unknown_runtime_check_fixed_wording_fits_owner_terminal(state):
    data = payload()
    data['runtime']['state'] = state
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        text = painted(pilot.app, 'runtime')
        assert ('never paired' if state == 'unknown_seat' else 'check unknown') in text
        assert '‹' not in text


@pytest.mark.parametrize('state,word,ansi', [
    ('pending', 'loading', 3), ('busy', 'busy', 3), ('unknown_seat', 'never paired', 3),
])
async def test_warning_footer_colors_reach_actual_compositor(state, word, ansi):
    data = payload()
    key = 'status' if state in ('paused', 'unknown_worker') else 'owner'
    if key == 'status':
        data[key]['live_state'] = 'paused' if state == 'paused' else None
    else:
        data[key]['state'] = state
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        segments = [segment for segment in strips(pilot.app, key)[-1] if word in segment.text]
        assert segments, painted(pilot.app, key)
        assert all(segment.style.color.get_truecolor() == pilot.app.ansi_theme.ansi_colors[ansi]
                   for segment in segments)


def border_color(app, key):
    frames = [segment for strip in strips(app, key) for segment in strip if "┌" in segment.text]
    assert frames
    return frames[0].style.color.get_truecolor()


@pytest.mark.parametrize("live,word,color", [("working", "working", "accent"), ("idle", "online", "accent"),
                                          ("paused", "online", "accent"), ("offline", "offline", "red")])
async def test_seat_uses_worker_presence_and_erc8004_registration(live, word, color):
    from rich.color import Color
    data = payload()
    data["seat"]["state"] = "stale"
    data["status"].update(live_state=live, meter_state='unavailable')
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        assert word in painted(app, "seat")
        assert "AGENT #8127" in painted(app, "seat")
        assert "stale" not in painted(app, "seat")
        expected = (Color.parse(app.get_css_variables()["accent"]).get_truecolor() if color == "accent"
                    else app.ansi_theme.ansi_colors[1])
        assert border_color(app, "seat") == expected


@pytest.mark.parametrize("width", [149, 211])
async def test_accepted_and_status_tracks_fill_footer_and_show_formatted_digits(width):
    data = payload()
    data["accepted"].update(accepted=3264, attempts=3405, percent=95.86)
    async with Harness(data).run_test(size=(width, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        assert "of 3,405" in painted(app, "accepted")
        assert "," in strips(app, "accepted")[5].text
        for key in ("accepted", "status"):
            card = app.query_one(f"#hero-{key}")
            footer = strips(app, key)[-1].text
            label = "95.86%" if key == "accepted" else "BUSY"
            assert footer.count("▰") + footer.count("▱") == card.region.width - 6 - len(label) - 1, footer
        status = painted(app, "status")
        assert all(word not in status for word in ("working", "capacity", "devices"))
        # Three tall groups: two active slots, a muted 0F, three capacity slots.
        assert "╶─╮ ╭─╮╭─╴ ╶─╮" in status
        assert "worked" in status
        middle = [segment for strip in strips(app, "status") for segment in strip
                  if "╭─╮╭─╴" in segment.text]
        assert middle
        white = app.query_one("#hero-status").rich_style.color.get_truecolor()
        assert all(segment.style.color.get_truecolor() != white for segment in middle)
        assert border_color(app, "accepted") != border_color(app, "seat")
        assert border_color(app, "effort") == border_color(app, "accepted")


async def test_rank_and_reward_borders_follow_read_changes_and_payment_recency():
    from rich.color import Color
    data = payload()
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        green = Color.parse(app.get_css_variables()["accent"]).get_truecolor()
        neutral = border_color(app, "accepted")
        assert "paid " in painted(app, "rewards") and "OWNER SHARE" not in painted(app, "rewards")
        for delta, recent, arrow, expected in [(2, True, "↑ 2", green), (-3, False, "↓ 3", app.ansi_theme.ansi_colors[1]),
                                               (0, False, "—", neutral), (None, None, "—", neutral)]:
            data["rank"]["delta"] = delta
            data["rewards"]["paid_recent"] = recent
            app.query_one(SurfSwarmAgentRackHero).update_data(surf_agent_hero=data)
            await pilot.pause()
            assert arrow in painted(app, "rank")
            assert border_color(app, "rank") == expected
            assert border_color(app, "rewards") == (green if recent else neutral)


async def test_pending_uses_loading_indicator_without_masking_failed_sources():
    async with Harness(None).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        assert all("loading" in painted(app, key) for key in payload())
        assert all("unavailable" not in painted(app, key) for key in payload())
        data = payload()
        data["rewards"]["state"] = "unavailable"
        data["runtime"]["state"] = "pending"
        app.query_one(SurfSwarmAgentRackHero).update_data(surf_agent_hero=data)
        await pilot.pause()
        assert "unavailable" in painted(app, "rewards")
        assert "loading" in painted(app, "runtime")
        assert "AGENT #8127" in painted(app, "seat")


@pytest.mark.parametrize("width", [132, 134])
async def test_reward_payment_time_fits_narrow_footer_without_losing_date(width):
    from maxpane_dashboard.widgets.surf._fmt import mmdd_hhmm
    data = payload()
    async with Harness(data).run_test(size=(width, 45)) as pilot:
        await pilot.pause()
        card = pilot.app.query_one("#hero-rewards")
        date = mmdd_hhmm(data["rewards"]["last_paid_ts"])
        text = painted(pilot.app, "rewards")
        assert date in strips(pilot.app, "rewards")[-1].text
        assert "‹" not in text
        assert "last paid " + date in str(card.tooltip)
        await pilot.resize_terminal(170, 45)
        await pilot.pause()
        assert "paid " + date in strips(pilot.app, "rewards")[-1].text
