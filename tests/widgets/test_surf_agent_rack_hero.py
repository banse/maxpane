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
        effort=dict(source, listed=True, hours=320., output_tokens=1800000,
                    premium_percent=75., premium_jobs=3, model_jobs=4, work_jobs=10),
        rewards=dict(source, imd=12.84, usd=120.82, seats=3, usd_state="ok", usd_read_ts=1791775800., last_paid_ts=1791775680., paid_recent=True),
        rank=dict(source, listed=True, rank=27, ranked_of=1024, delta=2),
        status=dict(source, live_state="working", working=2, capacity=3, devices=2,
                    current_action="reviewing",
                    paused_until_ts=None, failures=0, last_work_ts=1791775680., last_work_kind="worked",
                    work_state="ok", work_read_ts=1791775800., meter_kind="activity", meter_state="busy", numerator=1., denominator=1.),
        owner=dict(source, address="0x0000000000000000000000000000000000000001", name="example.eth", paired_ts=1790812800.),
        runtime=dict(source, runtime="codex v1.2.3", daemon="v1.2", devices=2, update_state="current", latest_version="1.2.3",
                     checked_ts=1791775800., fleet_daemon="v1.2", fleet_count=900, fleet_total=966, daemon_differs=False,
                     connected_ts=1791774000.),
        models=dict(source, rows=[dict(model="model A", effort="high"), dict(model="model B", effort="medium")]),
        earnings=dict(source, earned=12, worked_on=7, earned_24h=4, worked_on_24h=2, worked_recent=True,
                      owner="0x0000000000000000000000000000000000000001"),
        collab=dict(source, count=12, rows=[dict(token_id=527, shared_jobs=84), dict(token_id=1, shared_jobs=52)]),
        nodes=dict(source, oracle=120, oracle_total=160, launches=340, launches_total=400, other=500, known_jobs=840, total_jobs=840,
                   rows=[dict(node_key="adversarial_review", accepted=500, attempts=510),
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


def body_rows(app, key):
    """Read the actual inset cells without either its or the card's frame."""
    rows = []
    for strip in strips(app, key)[3:6]:
        edges = [n for n, char in enumerate(strip.text) if char == "│"]
        assert len(edges) >= 4, strip.text
        rows.append(strip.crop(edges[1] + 1, edges[-2]))
    return rows


def word_styles(row, word):
    start = row.text.index(word)
    return [segment.style for segment in row.crop(start, start + len(word)) if segment.text.strip()]


@pytest.mark.parametrize("width", [132, 149])
async def test_owner_and_runtime_keep_padded_labels_and_values(width):
    from rich.color import Color
    data = payload()
    data["models"]["rows"] = [dict(model="gpt-5.1-fable", effort="high")]
    data["owner"]["name"] = "owner-name-that-needs-windowing.eth"
    data["runtime"].update(daemon="0.1.2+long-postfix", daemon_differs=True,
                           update_state="outdated")
    async with Harness(data).run_test(size=(width, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        label = app.query_one('#hero-runtime').rich_style.color.get_truecolor()
        value = Color.parse(app.get_css_variables()["foreground"]).get_truecolor()
        for key in ("owner", "runtime"):
            rows = body_rows(app, key)
            assert all(row.text.startswith(" ") and row.text.endswith(" ") for row in rows), (key, painted(app, key))
        model_row = body_rows(app, "runtime")[2]
        assert all(style.color.get_truecolor() == value for style in word_styles(model_row, "fable"))
        assert ("…" in model_row.text) == (width == 132)
        assert "high" in strips(app, "runtime")[6].text
        owner_row = body_rows(app, "owner")[1]
        icon = [segment for segment in owner_row if "⧉" in segment.text]
        assert icon and all("@click" in segment.style.meta for segment in icon)
        assert any(segment.style.link for segment in owner_row)
        assert all(segment.style.color.get_truecolor() == value for segment in owner_row if segment.text.strip())
        daemon_row = body_rows(app, "runtime")[1]
        assert ("0.1…↑" if width == 132 else "0.1.2↑") in daemon_row.text
        assert "+" not in daemon_row.text
        assert all(style.color.get_truecolor() == label for style in word_styles(daemon_row, "daemon"))
        assert all(style.color.get_truecolor() == value for style in word_styles(daemon_row, "↑"))
        assert border_color(app, "runtime") == app.ansi_theme.ansi_colors[3]


@pytest.mark.parametrize("working,capacity,live,meter", [(2, 3, "working", "busy"),
                                                          (0, 3, "idle", "idle"),
                                                          (0, 3, "offline", "offline"),
                                                          (999, 999, "working", "busy")])
async def test_status_readout_uses_final_frame_color_and_padded_compact_fallback(working, capacity, live, meter):
    from rich.color import Color
    data = payload()
    data["status"].update(working=working, capacity=capacity, live_state=live, meter_state=meter)
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        expected = (app.ansi_theme.ansi_colors[2] if meter == "busy" else
                    app.ansi_theme.ansi_colors[3] if meter == "offline" else
                    app.query_one("#hero-status").rich_style.color.get_truecolor())
        rows = body_rows(app, "status")
        segments = [segment for row in rows for segment in row if segment.text.strip()]
        assert segments
        assert {segment.style.color.get_truecolor() for segment in segments} == {expected, (98, 98, 98)}
        if working == 999:
            assert rows[1].text.strip() == "999 0F 999"
            assert all(row.text.startswith(" ") and row.text.endswith(" ") for row in rows)


@pytest.mark.parametrize("width", [129, 130, 132, 149])
@pytest.mark.parametrize("name", [None, "⧉"])
async def test_owner_address_window_keeps_copy_and_explorer_inside_padding(width, name):
    data = payload()
    data["owner"]["name"] = name
    async with Harness(data).run_test(size=(width, 45)) as pilot:
        await pilot.pause()
        row = body_rows(pilot.app, "owner")[1]
        assert row.text.startswith(" ") and row.text.endswith(" ")
        assert "⧉" in row.text
        # Eleven address cells, copy glyph + gap, and padding on both sides.
        if row.cell_length >= 15:
            assert "0x" in row.text and "…" in row.text
        else:
            assert "wallet" in row.text
            assert data["owner"]["address"] in str(pilot.app.query_one("#hero-owner").tooltip)
        assert any(segment.style.link for segment in row)
        assert any("⧉" in segment.text and "@click" in segment.style.meta for segment in row)


async def test_approved_twelve_cards_form_two_equal_rows_with_live_facts():
    async with Harness(payload()).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        hero = app.query_one(SurfSwarmAgentRackHero)
        cards = list(hero.children)
        assert [card.data.key for card in cards] == [
            "seat", "status", "accepted", "nodes", "models", "effort",
            "runtime", "owner", "rank", "collab", "rewards", "earnings",
        ]
        assert len(cards) == 12 and hero.region.height == 19
        assert {card.region.height for card in cards} == {9}
        assert len({card.region.y for card in cards}) == 2
        assert [(card.region.x, card.region.width) for card in cards[:6]] == [(card.region.x, card.region.width) for card in cards[6:]]
        assert cards[6].region.y - cards[0].region.bottom == 1
        for key, words in {
            "seat": ("AGENT", "SEAT", "swarming", "ERC-8004 #8127"),
            "accepted": ("JOBS", "ACCEPTED", "96%"),
            "effort": ("HOURS", "1.8M tokens"),
            "rewards": ("IMD", "$120.82"),
            "rank": ("POSITION", "of 1,024", "↑ 2"),
            "status": ("WORKER", "reviewing", "BUSY", "▰"),
            "owner": ("WALLET", "example.eth ⧉", "paired"),
            "runtime": ("codex", "v1.2.3", "daemon", "v1.2", "model… +1", "high"),
            "models": ("ORACLE", "JOBS", "75%"),
            "earnings": ("EARNINGS", "TOKENS", "4 new"),
            "collab": ("SEATS", "collaborators"),
            "nodes": ("LAUNCHES", "JOBS", "85%"),
        }.items():
            text = painted(app, key)
            assert all(word in text for word in words), (key, text)
            footer = strips(app, key)[-1].text
            label = footer.strip("╰─╯ ")
            if key in ("owner", "models", "nodes", "runtime", "accepted", "effort", "earnings", "collab", "rewards"):
                assert not label, (key, footer)
                continue
            left = footer.index(label)
            assert abs(left - (len(footer) - left - len(label))) <= 1, (key, footer)
        # 420 and 960, asserted as digit glyphs that actually reach the terminal.
        assert "  ╵╰─╴╰─╯" in painted(app, "seat")
        assert "╶─╯╰─╯╰─╯" in painted(app, "accepted")
        assert strips(app, "accepted")[0].text.strip("╭─╮ ⊙") == "ACCEPTED"
        assert strips(app, "accepted")[2].text.split("┌")[1].split("┐")[0].strip("─ ") == "JOBS"
        assert strips(app, "nodes")[0].text.strip("╭─╮ ⊙") == "LAUNCHES"


@pytest.mark.parametrize("width", [132, 149])
async def test_acceptance_rate_moves_inside_and_updates_without_an_outer_meter(width):
    data = payload()
    async with Harness(data).run_test(size=(width, 45)) as pilot:
        app = pilot.app
        for accepted, attempts, percent, expected in (
            (3271, 3413, 100 * 3271 / 3413, "95.84%"),
            (1, 2, 50., "50%"), (0, 10, 0., "0%"),
            (10, 10, 100., "100%"), (None, None, None, "--%"),
            (11, 10, 110., "--%"), (0, 0, None, ""),
        ):
            data["accepted"].update(accepted=accepted, attempts=attempts, percent=percent)
            app.query_one(SurfSwarmAgentRackHero).update_data(surf_agent_hero=data)
            await pilot.pause()
            rows = strips(app, "accepted")
            inner_footer = next(row.text for row in rows if "└" in row.text)
            caption = inner_footer.split("└", 1)[1].split("┘", 1)[0].strip("─ ")
            assert caption == expected
            assert not rows[-1].text.strip("╰─╯ ")
            assert not any(char in painted(app, "accepted") for char in "▰▱")
            assert "of " not in painted(app, "accepted")
            if attempts == 0:
                assert "no attempts" in painted(app, "accepted")
            if accepted == 3271:
                assert "3,271 / 3,413" in str(app.query_one("#hero-accepted").tooltip)


async def test_working_status_uses_current_action_and_clears_it_on_idle_or_unknown():
    data = payload()
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        hero = pilot.app.query_one(SurfSwarmAgentRackHero)
        for action in ("oracling", "auditing", "reviewing", "building", "manifesting",
                       "researching", "testing", "designing", "frontending", "implementing"):
            data["status"]["current_action"] = action
            hero.update_data(surf_agent_hero=data)
            await pilot.pause()
            text = painted(pilot.app, "status")
            assert action in text and "active" not in text and "worked" not in text, text
        for invalid in (None, "", "active", "[/x]\x1b[31m researching", [], {}, True):
            data["status"]["current_action"] = invalid
            hero.update_data(surf_agent_hero=data)
            await pilot.pause()
            text = painted(pilot.app, "status")
            assert "working" in text and "implementing" not in text and "active" not in text, text
        data["status"].update(current_action="building", working=0, live_state="idle", meter_state="idle")
        hero.update_data(surf_agent_hero=data)
        await pilot.pause()
        text = painted(pilot.app, "status")
        assert "worked" in text and "building" not in text, text


async def test_owner_keeps_copy_and_explorer_links_when_name_is_hostile_or_long():
    data = payload()
    data["owner"]["name"] = "[/x]\x1b[31m evil " + "owner" * 20
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        segments = [segment for strip in strips(pilot.app, "owner") for segment in strip]
        icons = [s for s in segments if "⧉" in s.text]
        assert icons and all("@click" in s.style.meta for s in icons)
        assert any(s.style and s.style.link and "explorer.imd.fun/wallet/" in s.style.link for s in segments)
        assert "‹" in painted(pilot.app, "owner") and "\x1b" not in painted(pilot.app, "owner")


@pytest.mark.parametrize("state", ["pending", "busy", "unknown_seat", "empty", "unavailable"])
async def test_detail_failure_preserves_selected_id_and_independent_records(state):
    data = payload()
    for key in ("seat", "owner", "runtime", "models", "earnings", "collab", "nodes"):
        data[key]["state"] = state
    data["seat"]["token_id"] = 9876543210
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        assert "9876543210" in painted(pilot.app, "seat")
        assert "96%" in painted(pilot.app, "accepted")
        assert "example.eth" not in painted(pilot.app, "owner")
        assert "up to date" not in painted(pilot.app, "runtime")
        expected = "never paired" if state == "unknown_seat" else "--"
        assert expected in painted(pilot.app, "owner")


async def test_zero_empty_and_unknown_facts_are_distinct_then_refresh_clears_every_card():
    data = payload()
    data["accepted"].update(accepted=0, attempts=0, percent=None)
    data["models"]["rows"] = []
    data["nodes"].update(rows=[], oracle=0, oracle_total=0, launches=0, launches_total=0, other=0, known_jobs=0, total_jobs=0)
    data["collab"].update(count=0, rows=[])
    data["earnings"].update(earned=0, worked_on=0, earned_24h=0, worked_on_24h=0, worked_recent=False)
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        assert "no attempts" in painted(app, "accepted") and "0%" not in painted(app, "accepted")
        assert "model" in painted(app, "runtime") and "none" in painted(app, "runtime")
        assert "not advertised" in str(app.query_one("#hero-runtime").tooltip)
        assert "ORACLE" in painted(app, "models") and "collaborators" in painted(app, "collab")
        assert "0 new" in painted(app, "earnings")
        app.query_one(SurfSwarmAgentRackHero).update_data(surf_agent_hero=None)
        await pilot.pause()
        assert all("loading" not in painted(app, key) and "unavailable" not in painted(app, key) for key in data)
        assert "up to date" not in painted(app, "runtime") and "example.eth" not in painted(app, "owner")
        app.query_one(SurfSwarmAgentRackHero).update_data(surf_agent_hero=payload())
        await pilot.pause()
        assert "example.eth ⧉" in painted(app, "owner") and "960" not in painted(app, "accepted")


@pytest.mark.parametrize("live,meter,word", [("working", "busy", "BUSY"), ("idle", "idle", "IDLE"),
                                               ("offline", "offline", "OFF"), ("paused", "idle", "IDLE"), (None, "unavailable", "—")])
async def test_status_meter_colors_and_unknown_worker_never_claim_offline(live, meter, word):
    data = payload()
    data["seat"]["api_status"] = "revoked"
    data["status"].update(live_state=live, meter_state=meter, working=0 if live != "working" else 1,
                          meter_kind="activity-cooldown", numerator=.5)
    if live == "paused":
        data["status"].update(paused_until_ts=1791776800., failures=3)
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        text = painted(app, "status")
        if live is None:
            assert "status --" in painted(app, "seat")
            assert "revoked" not in painted(app, "seat")
            assert border_color(app, "seat") != app.ansi_theme.ansi_colors[1]
        assert word in text, text
        assert ("reviewing" in text) == (live == "working")
        if live == "working":
            assert "worked" not in text
        elif live in ("idle", "offline"):
            assert "worked" in text
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
        assert "+4" in painted(app, "runtime") and "+2 more" not in painted(app, "nodes")
        assert "model-4[/x]" in str(app.query_one("#hero-runtime").tooltip)
        assert "unknown[/x]" not in str(app.query_one("#hero-nodes").tooltip)
        assert "510 attempts" not in str(app.query_one("#hero-nodes").tooltip)
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
        assert 'high' in strips(pilot.app, 'runtime')[6].text
        assert 'daemon differs' in str(pilot.app.query_one('#hero-runtime').tooltip)
        assert 'model' in text and 'opus 4.1' in text
        assert '0.1.0+aca0ff06' in str(pilot.app.query_one('#hero-runtime').tooltip)
        await pilot.resize_terminal(211, 45)
        await pilot.pause()
        assert '0.1.0↑' in painted(pilot.app, 'runtime')
        assert '+aca0ff06' not in painted(pilot.app, 'runtime')


async def test_narrow_runtime_preserves_version_with_named_compact_label_then_restores():
    data = payload()
    data["runtime"].update(runtime="claude 2.1.278 (Claude Code)", daemon="0.1.2+long-postfix")
    data["models"]["rows"] = [dict(model="tiny", effort="high")]
    async with Harness(data).run_test(size=(132, 45)) as pilot:
        await pilot.pause()
        row = body_rows(pilot.app, "runtime")[0].text
        assert "cld" in row and "2.1.278" in row, row
        assert row.startswith(" ") and row.endswith(" ")
        assert "‹" not in painted(pilot.app, "runtime")
        assert "claude 2.1.278 (Claude Code)" in str(pilot.app.query_one("#hero-runtime").tooltip)
        await pilot.resize_terminal(149, 45)
        await pilot.pause()
        assert "claude" in body_rows(pilot.app, "runtime")[0].text
        data["runtime"]["runtime"] = "experimental-runtime 2.1.278"
        pilot.app.query_one(SurfSwarmAgentRackHero).update_data(surf_agent_hero=data)
        await pilot.pause()
        assert "‹" in painted(pilot.app, "runtime")
        assert "2.1.278" in body_rows(pilot.app, "runtime")[0].text


async def test_compact_status_removes_grouping_before_losing_exact_counts():
    data = payload()
    data["status"].update(working=99999, capacity=99999)
    async with Harness(data).run_test(size=(139, 45)) as pilot:
        await pilot.pause()
        row = body_rows(pilot.app, "status")[1].text
        assert row.strip() == "99999 0F 99999", row
        assert row.startswith(" ") and row.endswith(" ")
        assert "‹" not in painted(pilot.app, "status")
        await pilot.resize_terminal(170, 45)
        await pilot.pause()
        assert "99,999 0F 99,999" in body_rows(pilot.app, "status")[1].text


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
            source = data['nodes'] if key == 'models' else section
            assert hhmm(source['read_ts']) in tooltip
            if key != 'runtime':
                assert 'stale' not in tooltip
        assert '96%' in painted(pilot.app, 'accepted')
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
    data['nodes'].update(rows=[False], oracle=True, oracle_total=True, launches=-1, launches_total=-1, other=float('nan'))
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


@pytest.mark.parametrize('state', ['pending', 'unavailable', 'unknown_seat', 'stale_unknown_seat', 'empty'])
async def test_unknown_runtime_check_fixed_wording_fits_owner_terminal(state):
    data = payload()
    data['runtime']['state'] = state
    data['models']['rows'] = [dict(model='tiny', effort='high')]
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        text = painted(pilot.app, 'runtime')
        assert 'check unknown' not in text
        assert 'high' in strips(pilot.app, 'runtime')[6].text
        assert 'never paired' not in text
        assert '‹' not in text


async def test_owner_researched_shipped_runtime_outer_footers_stay_blank_in_every_source_state():
    data = payload()
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        for state in ("ok", "partial", "stale", "unavailable", "pending", "busy",
                      "unknown_seat", "stale_unknown_seat", "empty", "failed", "malformed"):
            for key in ("owner", "models", "nodes", "runtime"):
                data[key]["state"] = state
            pilot.app.query_one(SurfSwarmAgentRackHero).update_data(surf_agent_hero=data)
            await pilot.pause()
            for key in ("owner", "models", "nodes", "runtime"):
                footer = strips(pilot.app, key)[-1].text
                assert set(footer) <= set(" ╰─╯"), (state, key, footer)
                if state in ("unknown_seat", "stale_unknown_seat") and key == "owner":
                    assert "never paired" in painted(pilot.app, key)
            if state in ("ok", "partial", "stale"):
                for key, word in (("owner", "paired"), ("models", "ORACLE"), ("nodes", "LAUNCHES"), ("runtime", "high")):
                    assert word in painted(pilot.app, key)


def border_color(app, key):
    frames = [segment for strip in strips(app, key) for segment in strip if "┌" in segment.text]
    assert frames
    return frames[0].style.color.get_truecolor()


@pytest.mark.parametrize("live,word,color", [("working", "swarming", "accent"), ("idle", "ready", "accent"),
                                          ("paused", "ON", "accent"), ("offline", "offline", "red")])
@pytest.mark.parametrize("api_status", [None, "revoked", "suspended", "", "  ", 123])
async def test_seat_uses_worker_presence_and_erc8004_registration(live, word, color, api_status):
    from rich.color import Color
    data = payload()
    data["seat"]["state"] = "stale"
    data["seat"]["api_status"] = api_status
    data["status"].update(live_state=live, meter_state='unavailable')
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        assert strips(app, "seat")[0].text.strip("╭─╮ ⊙") == "AGENT"
        assert "SEAT" in strips(app, "seat")[2].text
        assert strips(app, "seat")[6].text.split("└")[1].split("┘")[0].strip("─ ") == word
        assert "ERC-8004 #8127" in painted(app, "seat")
        assert "IDMD" not in painted(app, "seat")
        assert "stale" not in painted(app, "seat")
        expected = (Color.parse(app.get_css_variables()["accent"]).get_truecolor() if color == "accent"
                    else app.ansi_theme.ansi_colors[1])
        assert border_color(app, "seat") == expected


@pytest.mark.parametrize("width", [149, 211])
async def test_accepted_keeps_formatted_digits_and_only_status_has_a_footer_meter(width):
    data = payload()
    data["accepted"].update(accepted=3264, attempts=3405, percent=95.86)
    async with Harness(data).run_test(size=(width, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        assert "95.86%" in strips(app, "accepted")[6].text
        assert "," in strips(app, "accepted")[5].text
        assert not strips(app, "accepted")[-1].text.strip("╰─╯ ")
        card = app.query_one("#hero-status")
        footer = strips(app, "status")[-1].text
        assert footer.count("▰") + footer.count("▱") == card.region.width - 6 - len("BUSY") - 1, footer
        status = painted(app, "status")
        assert all(word not in status for word in ("working", "capacity", "devices"))
        # Three tall groups: two active slots, a muted 0F, three capacity slots.
        assert "╶─╮ ╭─╮╭─╴ ╶─╮" in status
        assert "reviewing" in status
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
        assert "paid " not in painted(app, "rewards") and "OWNER SHARE" not in painted(app, "rewards")
        for delta, recent, arrow, expected in [(2, True, "↑ 2", green), (-3, False, "↓ 3", app.ansi_theme.ansi_colors[1]),
                                               (0, False, "", neutral), (None, None, "", neutral)]:
            data["rank"]["delta"] = delta
            data["rewards"]["paid_recent"] = recent
            app.query_one(SurfSwarmAgentRackHero).update_data(surf_agent_hero=data)
            await pilot.pause()
            if arrow:
                assert arrow in strips(app, "rank")[-1].text
            else:
                assert set(strips(app, "rank")[-1].text) <= set(" ╰─╯")
            assert border_color(app, "rank") == expected
            assert border_color(app, "rewards") == (green if recent else neutral)


async def test_pending_uses_loading_indicator_without_masking_failed_sources():
    async with Harness(None).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        assert all("loading" not in painted(app, key) for key in payload())
        assert all("unavailable" not in painted(app, key) for key in payload())
        data = payload()
        data["rewards"]["state"] = "unavailable"
        data["runtime"]["state"] = "pending"
        app.query_one(SurfSwarmAgentRackHero).update_data(surf_agent_hero=data)
        await pilot.pause()
        assert "unavailable" not in painted(app, "rewards")
        assert "loading" not in painted(app, "runtime")
        assert "ERC-8004 #8127" in painted(app, "seat")


@pytest.mark.parametrize("width", [132, 134])
async def test_reward_payment_time_stays_in_hover_with_no_outer_footer(width):
    from maxpane_dashboard.widgets.surf._fmt import mmdd_hhmm
    data = payload()
    async with Harness(data).run_test(size=(width, 45)) as pilot:
        await pilot.pause()
        card = pilot.app.query_one("#hero-rewards")
        date = mmdd_hhmm(data["rewards"]["last_paid_ts"])
        text = painted(pilot.app, "rewards")
        assert not strips(pilot.app, "rewards")[-1].text.strip("╰─╯ ")
        assert "$120.82" in text
        assert "‹" not in text
        assert "last paid " + date in str(card.tooltip)
        await pilot.resize_terminal(170, 45)
        await pilot.pause()
        assert not strips(pilot.app, "rewards")[-1].text.strip("╰─╯ ")
        assert "$120.82" in painted(pilot.app, "rewards")


@pytest.mark.parametrize("width,working,glyph", [(149, 2, "╭─╮╭─╴"), (132, None, "0F")])
async def test_status_separator_uses_midpoint_gray_in_tall_and_compact_readouts(width, working, glyph):
    data = payload()
    data["status"]["working"] = working
    async with Harness(data).run_test(size=(width, 45)) as pilot:
        await pilot.pause()
        rendered = strips(pilot.app, "status")
        card = pilot.app.query_one("#hero-status")
        middle = card.region.width // 2
        background = next(iter(rendered[1].crop(middle, middle + 1))).style.bgcolor.get_truecolor()
        separator = [segment for strip in rendered for segment in strip if glyph in segment.text]
        assert separator, painted(pilot.app, "status")
        # Matrix outer background #262626, original dim text #9e9e9e.
        assert background == (38, 38, 38)
        assert all(segment.style.color.get_truecolor() == (98, 98, 98) for segment in separator)


@pytest.mark.parametrize("percent,listed", [(75., True), (0., True), (None, True), (101., True), (75., False)])
async def test_effort_keeps_model_coverage_in_hover_without_outer_caption(percent, listed):
    data = payload()
    data["effort"].update(premium_percent=percent, listed=listed)
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        assert not strips(app, "effort")[-1].text.strip("╰─╯ ")
        assert "CONTRIBUTORS" not in painted(app, "effort")
        assert "Premium models: 3/4 known-model work attempts; model coverage 4/10 recorded attempts. Astra, Opus, Fable." in str(app.query_one("#hero-effort").tooltip)
        assert border_color(app, "effort") == border_color(app, "accepted")


@pytest.mark.parametrize("state", ["pending", "unavailable"])
async def test_premium_hover_survives_independent_contributor_failure(state):
    data = payload()
    data["effort"].update(state=state, hours=None, output_tokens=None)
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        assert not strips(pilot.app, "effort")[-1].text.strip("╰─╯ ")
        assert "Premium models: 3/4" in str(pilot.app.query_one("#hero-effort").tooltip)
        data["effort"].update(premium_percent=None, premium_jobs=None, model_jobs=None, work_jobs=None)
        pilot.app.query_one(SurfSwarmAgentRackHero).update_data(surf_agent_hero=data)
        await pilot.pause()
        assert not strips(pilot.app, "effort")[-1].text.strip("╰─╯ ")
        assert "Premium models: --/--" in str(pilot.app.query_one("#hero-effort").tooltip)


async def test_second_row_uses_neutral_frames_except_outdated_runtime():
    data = payload()
    async with Harness(data).run_test(size=(151, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        neutral = border_color(app, "accepted")
        for key in ("owner", "runtime", "models", "collab", "nodes"):
            assert border_color(app, key) == neutral, key
        for update, differs, orange in (("outdated", False, True), ("current", True, False),
                                         ("unknown", False, False), ("unavailable", True, False), ("current", False, False)):
            data["runtime"].update(update_state=update, daemon_differs=differs,
                                   daemon="0.1.0+long-build-identifier")
            app.query_one(SurfSwarmAgentRackHero).update_data(surf_agent_hero=data)
            await pilot.pause()
            text = painted(app, "runtime")
            assert "‹" not in text and "widen" not in text
            assert "check unknown" not in text
            if update in ("unknown", "unavailable"):
                assert "daemon differs" not in text
            assert border_color(app, "runtime") == (app.ansi_theme.ansi_colors[3] if orange else neutral)
            assert "0.1.0+long-build-identifier" in str(app.query_one("#hero-runtime").tooltip)


@pytest.mark.parametrize("width", [132, 149, 211])
async def test_model_moves_to_runtime_third_row_with_effort_in_inner_footer(width):
    from rich.color import Color
    data = payload()
    data["models"]["rows"] = [dict(model="gpt-5.1-fable", effort="high")]
    async with Harness(data).run_test(size=(width, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        rendered = strips(app, "runtime")
        text = [strip.text for strip in rendered]
        assert "model" in text[5] and ("fable 5.1" if width >= 149 else "fable") in text[5], text
        assert "high" in text[6]
        inner_right = [index for index, char in enumerate(text[5]) if char == "│"][-2]
        model_end = inner_right - 1  # one blank cell between value and inner edge
        assert text[6].index("high") + len("high") == model_end
        foreground = Color.parse(app.get_css_variables()["foreground"]).get_truecolor()
        assert all(style.color.get_truecolor() == foreground and not style.dim
                   for style in word_styles(rendered[6], "high"))
        assert "devices" not in painted(app, "runtime")
        assert not text[-1].strip("╰─╯ ")
        assert "gpt-5.1-fable · high" in str(app.query_one("#hero-runtime").tooltip)


async def test_researched_uses_production_oracle_count_independently_of_models():
    data = payload()
    data["models"].update(state="unavailable", read_ts=None, rows=None)
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        app = pilot.app
        for state, oracle, glyphs in (
            ("ok", 120, ("╶╮ ╶─╮╭─╮", " │ ┌─┘│ │", "╶┴╴╰─╴╰─╯")),
            ("partial", 0, ("╭─╮", "│ │", "╰─╯")),
            ("partial", None, ("--",)),
            ("pending", 999, ("--",)),
        ):
            data["nodes"].update(state=state, oracle=oracle, oracle_total=oracle)
            app.query_one(SurfSwarmAgentRackHero).update_data(surf_agent_hero=data)
            await pilot.pause()
            text = painted(app, "models")
            assert strips(app, "models")[0].text.strip("╭─╮ ⊙") == "ORACLE"
            assert "JOBS" in strips(app, "models")[2].text
            assert all(any(glyph in row.text for row in body_rows(app, "models")) for glyph in glyphs), text
            assert strips(app, "models")[6].text.split("└")[1].split("┘")[0].strip("─ ") == ("100%" if state == "ok" else "--%")
            assert strips(app, "nodes")[6].text.split("└")[1].split("┘")[0].strip("─ ") == ("--%" if state == "pending" else "85%")
            card = app.query_one("#hero-models")
            assert card.data.state == state and card.data.read_ts == data["nodes"]["read_ts"]
            assert "production networks; testnets excluded" in str(card.tooltip)


async def test_long_model_keeps_effort_visible_with_ellipsis_and_hover():
    data = payload()
    model = 'claude-experimental-frontier-preview-2026-10-01-long-context'
    data['models']['rows'] = [dict(model=model, effort='xhigh')]
    async with Harness(data).run_test(size=(132, 45)) as pilot:
        await pilot.pause()
        text = painted(pilot.app, 'runtime')
        assert 'xhigh' in text and '…' in text and '‹' in text
        assert model in str(pilot.app.query_one('#hero-runtime').tooltip)


@pytest.mark.parametrize("width", [132, 149])
async def test_runtime_retains_model_count_and_independent_model_source(width):
    data = payload()
    data["runtime"].update(state="unavailable")
    long_model = "claude-experimental-frontier-preview-2026-10-01-long-context"
    data["models"]["rows"] = [dict(model=long_model, effort="xhigh"), dict(model="second", effort="low")]
    async with Harness(data).run_test(size=(width, 45)) as pilot:
        app = pilot.app
        await pilot.pause()
        row = body_rows(app, "runtime")[2].text
        assert "model" in row and "… +1" in row
        assert "xhigh" in strips(app, "runtime")[6].text
        assert "‹" in strips(app, "runtime")[0].text
        tip = str(app.query_one("#hero-runtime").tooltip)
        assert long_model + " · xhigh" in tip and "second · low" in tip
        for state, rows, value in (("ok", [], "none"), ("pending", data["models"]["rows"], "--"),
                                   ("unavailable", None, "--")):
            data["runtime"]["state"] = "ok"
            data["models"].update(state=state, rows=rows)
            app.query_one(SurfSwarmAgentRackHero).update_data(surf_agent_hero=data)
            await pilot.pause()
            assert body_rows(app, "runtime")[2].text.split() == ["model", value]
            assert strips(app, "runtime")[6].text.split("└")[1].split("┘")[0].strip("─ ") == "--"
            assert "xhigh" not in str(app.query_one("#hero-runtime").tooltip)


@pytest.mark.parametrize("width", [132, 149, 211])
async def test_runtime_has_no_outer_footer_but_retains_connection_hover(width):
    from maxpane_dashboard.widgets.surf._fmt import mmdd_hhmm
    data = payload()
    async with Harness(data).run_test(size=(width, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        footer = strips(app, "runtime")[-1].text
        assert not footer.strip("╰─╯ ")
        assert "VERSION" not in footer
        tip = str(app.query_one("#hero-runtime").tooltip)
        assert "last connected " + mmdd_hhmm(data["runtime"]["connected_ts"]) in tip
        assert "not a verified restart" in tip
        data["runtime"]["connected_ts"] = None
        app.query_one(SurfSwarmAgentRackHero).update_data(surf_agent_hero=data)
        await pilot.pause()
        assert not strips(app, "runtime")[-1].text.strip("╰─╯ ")


async def test_earnings_counts_distinct_tokens_with_neutral_highlighting():
    from rich.color import Color
    data = payload()
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        text = painted(app, "earnings")
        assert "TOKENS" in text and "4 new" in text
        assert "╶┴╴╰─╴" in text  # tall 12
        green = Color.parse(app.get_css_variables()["accent"]).get_truecolor()
        assert border_color(app, "earnings") == border_color(app, "accepted")
        assert "Green means" not in str(app.query_one("#hero-earnings").tooltip)
        for recent in (False, None, True):
            data["earnings"]["worked_recent"] = recent
            app.query_one(SurfSwarmAgentRackHero).update_data(surf_agent_hero=data)
            await pilot.pause()
            assert border_color(app, "earnings") == border_color(app, "accepted")
            for key in ("seat", "rewards", "rank", "status"):
                assert border_color(app, key) == green
        data["earnings"].update(earned=None, worked_on=None, earned_24h=None, worked_on_24h=None, state="partial")
        app.query_one(SurfSwarmAgentRackHero).update_data(surf_agent_hero=data)
        await pilot.pause()
        text = painted(app, "earnings")
        assert "-- new" in text
        assert "0 new" not in text


@pytest.mark.parametrize("new,worked", [(4, 2), (4, 0), (4, None), (0, 0), (None, None), (None, 2)])
async def test_earnings_inner_footer_shows_new_tokens_from_last_24h(new, worked):
    data = payload()
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        data["earnings"].update(earned_24h=new, worked_on_24h=worked)
        app.query_one(SurfSwarmAgentRackHero).update_data(surf_agent_hero=data)
        await pilot.pause()
        footer = strips(app, "earnings")[-1].text
        assert not footer.strip("╰─╯ ")
        assert "CLAIMED" not in painted(app, "earnings")
        inner_footer = next(row.text for row in strips(app, "earnings") if "└" in row.text)
        caption = inner_footer.split("└", 1)[1].split("┘", 1)[0].strip("─ ")
        assert caption == f"{new if new is not None else '--'} new"
        assert "worked on" not in painted(app, "earnings")
        tooltip = str(app.query_one("#hero-earnings").tooltip)
        assert "this agent's accepted work" in tooltip
        assert "owner's wallet:" not in tooltip
        assert "earliest launch/earned timestamp" in tooltip
        assert f"Last 24h: {new if new is not None else '--'} earned" in tooltip
        assert f"{worked if worked is not None else '--'} worked on by this agent" in tooltip
        if new is None or worked is None:
            assert "unknown" in tooltip


async def test_earnings_keeps_exact_hover_counts_and_blank_footer_across_resize():
    data = payload()
    data["earnings"].update(earned=4096, worked_on=4096, earned_24h=4096, worked_on_24h=4096)
    async with Harness(data).run_test(size=(132, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        footer = strips(app, "earnings")[-1].text
        assert not footer.strip("╰─╯ ")
        tooltip = str(app.query_one("#hero-earnings").tooltip)
        assert "Last 24h: 4,096 earned" in tooltip and "4,096 worked on by this agent" in tooltip
        assert "4,096 new" in painted(app, "earnings")
        await pilot.resize_terminal(211, 45)
        await pilot.pause()
        assert not strips(app, "earnings")[-1].text.strip("╰─╯ ")
        assert "4,096 new" in painted(app, "earnings")


def test_agent_card_states_match_declared_contract():
    from maxpane_dashboard.data.surf_models import SURF_AGENT_HERO_STATES
    from maxpane_dashboard.widgets.surf.agent_rack_hero import _STATES
    assert _STATES == SURF_AGENT_HERO_STATES


async def test_removed_outer_captions_stay_empty_across_source_states_and_recovery():
    data = payload()
    async with Harness(data).run_test(size=(132, 45)) as pilot:
        app = pilot.app
        keys = ("accepted", "effort", "earnings", "collab", "rewards")
        for state in ("ok", "partial", "stale", "pending", "busy", "failed", "unavailable",
                      "unknown_seat", "stale_unknown_seat", "empty", "ok"):
            for key in keys:
                data[key]["state"] = state
            app.query_one(SurfSwarmAgentRackHero).update_data(surf_agent_hero=data)
            await pilot.pause()
            for key in keys:
                assert not strips(app, key)[-1].text.strip("╰─╯ "), (key, state)
        assert "4 new" in painted(app, "earnings")
        assert "$120.82" in painted(app, "rewards")
        assert "last paid " in str(app.query_one("#hero-rewards").tooltip)
        assert "#527 x84" in str(app.query_one("#hero-collab").tooltip)


async def test_ship_counts_launch_jobs_and_labels_the_unit():
    data = payload()
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        for values, digits in (
            (dict(oracle=120, launches=340, other=500, known_jobs=840, total_jobs=840),
             ("╶─╮╷ ╷╭─╮", " ─┤╰─┤│ │", "╶─╯  ╵╰─╯")),
            (dict(state="partial", oracle=120, launches=None, other=None, known_jobs=17, total_jobs=840),
             ("--",)),
            (dict(state="partial", oracle=None, launches=12, known_jobs=840, total_jobs=840),
             ("╶╮ ╶─╮", " │ ┌─┘", "╶┴╴╰─╴")),
            (dict(state="ok", oracle=0, launches=0, other=0, known_jobs=0, total_jobs=0),
             ("╭─╮", "│ │", "╰─╯")),
        ):
            data["nodes"].update(values, launches_total=values["launches"])
            app.query_one(SurfSwarmAgentRackHero).update_data(surf_agent_hero=data)
            await pilot.pause()
            text = painted(app, "nodes")
            assert strips(app, "nodes")[0].text.strip("╭─╮ ⊙") == "LAUNCHES"
            assert "LAUNCHES" in text
            assert "NODES" not in text and "work by type" not in text and "other" not in text
            for glyph in digits:
                assert any(glyph in row.text for row in body_rows(app, "nodes")), text
            assert strips(app, "nodes")[6].text.split("└")[1].split("┘")[0].strip("─ ") == ("100%" if values["launches"] else "--%")
            assert not strips(app, "nodes")[-1].text.strip("╰─╯ ")
            assert border_color(app, "nodes") == border_color(app, "accepted")
            tooltip = str(app.query_one("#hero-nodes").tooltip)
            assert "Distinct jobs on production networks; testnets excluded." in tooltip
            assert f"launch evidence known for {values['known_jobs']} of {values['total_jobs']} accepted non-oracle jobs" in tooltip
            assert "attempts" not in tooltip


async def test_job_cards_show_total_digits_and_acceptance_percentages_independently():
    data = payload()
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        app = pilot.app
        for accepted, total, caption in ((3, 4, '75%'), (0, 4, '0%'), (4, 4, '100%'),
                                         (0, 0, '--%'), (None, 4, '--%'), (3, None, '--%'),
                                         (5, 4, '--%'), (True, 4, '--%')):
            data['nodes'].update(launches=accepted, launches_total=total, oracle=accepted, oracle_total=total)
            app.query_one(SurfSwarmAgentRackHero).update_data(surf_agent_hero=data)
            await pilot.pause()
            for key, title in (('nodes', 'LAUNCHES'), ('models', 'ORACLE')):
                rendered = strips(app, key)
                assert rendered[0].text.strip('╭─╮ ⊙') == title
                assert rendered[2].text.split('┌')[1].split('┐')[0].strip('─ ') == 'JOBS'
                assert rendered[6].text.split('└')[1].split('┘')[0].strip('─ ') == caption
                body = '\n'.join(row.text for row in body_rows(app, key))
                assert ('--' in body) == (total is None)
                if total == 4:
                    assert '╷ ╷' in body and '╰─┤' in body and '  ╵' in body, body
                assert not rendered[-1].text.strip('╰─╯ ')
        data['nodes'].update(state='pending', launches=3, launches_total=4)
        app.query_one(SurfSwarmAgentRackHero).update_data(surf_agent_hero=data)
        await pilot.pause()
        assert '--%' in painted(app, 'nodes') and '--' in body_rows(app, 'nodes')[1].text


async def test_mixed_job_card_keeps_any_accepted_work_in_the_oracle_rate():
    from maxpane_dashboard.data.surf_agent_work import summarize
    from tests.data.test_surf_agent_work import LIVE, NOW, point, row
    data = payload()
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        app = pilot.app
        for accepted_node, rejected_node in [('implement', 'oracle_assess'), ('oracle_assess', 'implement')]:
            rows = [row(LIVE, accepted_node), row(LIVE, rejected_node, 'rejected')]
            for ordered in (rows, list(reversed(rows))):
                facts = summarize({'work': ordered}, {LIVE: point(True)}, NOW, oracle_chains={LIVE: 1})
                data['nodes'].update(facts)
                app.query_one(SurfSwarmAgentRackHero).update_data(surf_agent_hero=data)
                await pilot.pause()
                assert '100%' in strips(app, 'models')[6].text
                assert 'Accepted / total jobs: 1 / 1' in str(app.query_one('#hero-models').tooltip)
                assert 'Accepted / total jobs: 0 / 0' in str(app.query_one('#hero-nodes').tooltip)
                assert '--%' in strips(app, 'nodes')[6].text
