"""The recent window reconciles without destroying draft, replies or anchors."""
from textual.app import App
from textual.widgets import RichLog
import pytest
from maxpane_dashboard.widgets.surfboard import SurfboardTerminal
from tests.widgets.test_surfboard_rack import painted


class TerminalApp(App):
    def compose(self):
        yield SurfboardTerminal()


def events(start=0, end=40):
    return [dict(key=str(i), timestamp=1_700_000_000 + i, kind="job", job_id=f"job-{i//2}",
                 token_id=420, agent_id="50939", role="builder", step="building", state="building",
                 objective=f"objective {i}") for i in range(start, end)]


async def test_repeated_and_overlapping_snapshots_preserve_replies_draft_and_scroll_anchor():
    async with TerminalApp().run_test(size=(100, 20)) as pilot:
        terminal = pilot.app.query_one(SurfboardTerminal)
        terminal.update_data(surfboard_events=events())
        terminal.add_reply(["test reply"])
        terminal.focus_input()
        terminal.command_input.value = "find q/m/t/r420"
        await pilot.pause()
        terminal.command_input.cursor_position = 6
        await pilot.pause()
        log = terminal.query_one(RichLog)
        log.scroll_to(y=10, animate=False, immediate=True)
        await pilot.pause()
        before = painted(pilot.app)
        assert "objective 10" in before
        terminal.update_data(surfboard_events=events(5, 45))
        await pilot.pause()
        assert "objective 10" in painted(pilot.app)
        assert terminal.command_input.value == "find q/m/t/r420"
        assert terminal.command_input.cursor_position == 6
        assert terminal.command_input.has_focus
        assert len(log.lines) == 41
        terminal.update_data(surfboard_events=events(5, 45))
        await pilot.pause()
        log.scroll_end(animate=False, immediate=True)
        await pilot.pause()
        assert "test reply" in painted(pilot.app)
        assert len(log.lines) == 41


async def test_clear_removes_replies_only_and_buffers_are_bounded():
    async with TerminalApp().run_test(size=(100, 20)) as pilot:
        terminal = pilot.app.query_one(SurfboardTerminal)
        terminal.update_data(surfboard_events=events(0, 80))
        terminal.add_reply([f"reply {i}" for i in range(250)])
        await pilot.pause()
        assert len(terminal.query_one(RichLog).lines) == 260
        terminal.clear_replies()
        await pilot.pause()
        assert len(terminal.query_one(RichLog).lines) == 60
        assert "reply" not in painted(pilot.app)
        assert "objective 79" in painted(pilot.app)


async def test_submission_emits_literal_bounded_command_without_io():
    class Commands(TerminalApp):
        seen = []

        def on_surfboard_terminal_command_requested(self, event):
            self.seen.append(event.command)

    async with Commands().run_test(size=(100, 20)) as pilot:
        terminal = pilot.app.query_one(SurfboardTerminal)
        terminal.focus_input()
        await pilot.press("q", "m", "t", "r", "/", "4", "2", "0", "enter")
        assert pilot.app.seen == ["qmtr/420"]
        assert terminal.command_input.value == ""
        terminal.command_input.insert_text_at_cursor("x" * 600)
        assert len(terminal.command_input.value) <= 512


async def test_hostile_text_is_literal_and_address_links_use_shared_helpers():
    from tests.widgets.address_probe import icon_targets, link_targets
    address = "0x1234567890123456789012345678901234567890"
    async with TerminalApp().run_test(size=(149, 20)) as pilot:
        terminal = pilot.app.query_one(SurfboardTerminal)
        rows = events(0, 1)
        rows[0]["objective"] = f"[/x] {address} \x1b]8;;https://evil.invalid\x07escape"
        terminal.update_data(surfboard_events=rows)
        terminal.add_reply("[link=https://evil.invalid]literal[/link]")
        await pilot.pause()
        text = painted(pilot.app)
        assert "[/x]" in text and "\x1b" not in text
        assert address in [target[2] for target in icon_targets(pilot.app)]
        assert not any("evil.invalid" in str(target) for target in link_targets(pilot.app))


async def test_unknown_and_successfully_empty_feeds_differ_and_overview_is_explicit():
    async with TerminalApp().run_test(size=(100, 20)) as pilot:
        terminal = pilot.app.query_one(SurfboardTerminal)
        terminal.update_data()
        await pilot.pause()
        assert "events unavailable" in painted(pilot.app)
        terminal.update_data(surfboard_events=[], surfboard_overview=dict(agents_online=0, working_now=0,
            jobs_24h=0, oracles_24h=0, accepted_24h=0))
        await pilot.pause()
        text = painted(pilot.app)
        assert "no recent events" in text and "0 online" in text and "0 jobs" in text


async def test_fitting_literal_ellipsis_and_windowed_address_do_not_claim_lost_content():
    async with TerminalApp().run_test(size=(149, 20)) as pilot:
        terminal = pilot.app.query_one(SurfboardTerminal)
        rows = events(0, 1)
        rows[0]["objective"] = "waiting… 0x1234567890123456789012345678901234567890"
        terminal.update_data(surfboard_events=rows)
        await pilot.pause()
        assert "‹ widen" not in painted(pilot.app)
        rows[0]["objective"] += "word " * 100
        terminal.update_data(surfboard_events=rows)
        await pilot.pause()
        assert "‹ widen" in painted(pilot.app)


async def test_new_live_event_is_visible_after_command_replies_and_updates_stay_in_place():
    async with TerminalApp().run_test(size=(100, 14)) as pilot:
        terminal = pilot.app.query_one(SurfboardTerminal)
        terminal.update_data(surfboard_events=events(0, 10))
        terminal.add_reply(["> status", "reply to command"])
        await pilot.pause()
        changed = events(0, 11)
        changed[0]["objective"] = "updated old event"
        terminal.update_data(surfboard_events=list(reversed(changed)) + [changed[-1]])
        await pilot.pause()
        rows = painted(pilot.app).splitlines()
        reply = next(i for i, row in enumerate(rows) if "reply to command" in row)
        newest = next(i for i, row in enumerate(rows) if "objective 10" in row)
        assert newest > reply
        log = terminal.query_one(RichLog)
        assert len(log.lines) == 13
        log.scroll_home(animate=False, immediate=True)
        await pilot.pause()
        assert "updated old event" in painted(pilot.app)
        terminal.update_data(surfboard_events=None)
        terminal.update_data(surfboard_events=changed)
        await pilot.pause()
        assert len(log.lines) == 13
        log.scroll_end(animate=False, immediate=True)
        await pilot.pause()
        assert "objective 10" in painted(pilot.app)


@pytest.mark.parametrize("role,step,state,expected", [
    ("implement", None, "working", "building"), (None, "build_contract_project", "accepted", "built"),
    (None, "build_dapp", "accepted", "built"), ("test", None, "accepted", "tested"),
    (None, "tests", "working", "testing"), ("review", None, "leased", "reviewing"),
    (None, "contract_review", "accepted", "reviewed"), ("integrate", None, "working", "integrating"),
    ("manifest", None, "accepted", "attested"), ("deploy", None, "working", "deploying"),
    ("publish", None, "accepted", "published"), ("unknown", "unknown", "accepted", "accepted"),
    ("implement", None, "future_state", "future_state"), ("implement", None, "failed", "failed"),
    ("implement", None, "ready", "called"),
])
async def test_web_columns_and_known_step_words_are_literal(role, step, state, expected):
    async with TerminalApp().run_test(size=(100, 14)) as pilot:
        terminal = pilot.app.query_one(SurfboardTerminal)
        row = dict(events(0, 1)[0], kind="node", role=role, step=step, state=state)
        terminal.update_data(surfboard_events=[row])
        await pilot.pause()
        line = next(line for line in painted(pilot.app).splitlines() if "objective 0" in line)
        assert "job     agent #420   " + expected.ljust(13) + "objective 0" in line


async def test_grouped_job_suppresses_repeated_objective_but_replies_break_the_group():
    async with TerminalApp().run_test(size=(100, 18)) as pilot:
        terminal = pilot.app.query_one(SurfboardTerminal)
        rows = events(0, 2)
        rows[1]["objective"] = rows[0]["objective"]
        terminal.update_data(surfboard_events=rows)
        await pilot.pause()
        assert painted(pilot.app).count("objective 0") == 1
        assert "└" in painted(pilot.app)
        terminal.add_reply("reply breaks adjacent job group")
        rows.append(dict(rows[1], key="2"))
        terminal.update_data(surfboard_events=rows)
        await pilot.pause()
        assert painted(pilot.app).count("objective 0") == 2


FOOTER = dict(market_value_usd=33_690_000, market_basis="market_cap", market_state="ok",
              market_read_ts=1_700_000_000, inference_tokens=189_100_000_000,
              overview_state="ok", overview_read_ts=1_700_000_010,
              provider_ts=1_700_000_000, as_of=1_700_000_010)


async def test_footer_age_tick_updates_only_footer_and_keeps_live_log_draft_and_scroll(monkeypatch):
    from textual.widgets import Static
    async with TerminalApp().run_test(size=(96, 18)) as pilot:
        terminal = pilot.app.query_one(SurfboardTerminal)
        terminal.update_data(surfboard_events=events(), surfboard_footer=FOOTER)
        terminal.focus_input()
        terminal.command_input.value = "find saved draft"
        await pilot.pause()
        terminal.command_input.cursor_position = 5
        log = terminal.query_one(RichLog)
        log.scroll_to(y=5, animate=False, immediate=True)
        await pilot.pause()
        def forbidden(*args, **kwargs):
            raise AssertionError("age repaint rewrote the live transcript")
        monkeypatch.setattr(log, "clear", forbidden)
        monkeypatch.setattr(log, "write", forbidden)
        terminal.update_age(3)
        await pilot.pause()
        text = painted(pilot.app)
        assert "$33.69M" in text and "$1B goal" in text and "189.1B tokens used" in text
        assert "[=" in text  # The website gives every positive cap one lit cell.
        assert "13s ago last updated" in text
        assert log.scroll_y == 5 and terminal.command_input.value == "find saved draft"
        assert terminal.command_input.cursor_position == 5 and terminal.command_input.has_focus
        assert terminal.query_one("#surfboard-terminal-footer", Static).region.height >= 1


@pytest.mark.parametrize("changes,expected,excluded", [
    ({"market_basis": "fdv"}, "FDV", ""),
    ({"market_value_usd": None}, "$IMD unavailable", "[····"),
    ({"market_value_usd": True}, "$IMD unavailable", "$1.00"),
    ({"market_value_usd": float("nan")}, "$IMD unavailable", "nan"),
    ({"market_state": "stale"}, "mkt stale", ""),
    ({"overview_state": "stale"}, "swarm stale", ""),
    ({"provider_ts": None}, "age unknown", "10s ago"),
    ({"provider_ts": float("inf")}, "age unknown", "inf"),
    ({"provider_ts": 1_700_000_011}, "0s ago", "-1s"),
    ({"as_of": True}, "age unknown", ""),
    ({"inference_tokens": True}, "tokens unavailable", "1.0 tokens"),
])
async def test_footer_unknown_stale_fdv_and_future_timestamp_are_explicit(changes, expected, excluded):
    async with TerminalApp().run_test(size=(96, 14)) as pilot:
        terminal = pilot.app.query_one(SurfboardTerminal)
        terminal.update_data(surfboard_footer=dict(FOOTER, **changes))
        await pilot.pause()
        text = painted(pilot.app)
        assert expected in text
        if excluded:
            assert excluded not in text


@pytest.mark.parametrize("width", [90, 96])
async def test_header_keeps_all_network_figures_and_named_service_states_at_rack_widths(width):
    async with TerminalApp().run_test(size=(width, 18)) as pilot:
        terminal = pilot.app.query_one(SurfboardTerminal)
        overview = dict(agents_online=856, working_now=14, jobs_24h=1271, oracles_24h=32,
                        accepted_24h=2485, services=dict(verifier=True, publisher=False, deployer=None))
        terminal.update_data(surfboard_overview=overview, surfboard_footer=FOOTER)
        await pilot.pause()
        text = painted(pilot.app)
        for word in ("856 online", "14 working", "1,271 jobs", "32 oracles", "2,485 steps", "V* P! D?"):
            assert word in text
        assert "IMD TERMINAL" not in text  # The web header replaces the separate title.


async def test_bounded_transcript_drops_departed_events_and_old_replies_independently():
    async with TerminalApp().run_test(size=(100, 20)) as pilot:
        terminal = pilot.app.query_one(SurfboardTerminal)
        terminal.update_data(surfboard_events=events(0, 50))
        terminal.add_reply([f"reply {index}" for index in range(250)])
        terminal.update_data(surfboard_events=events(20, 80))
        await pilot.pause()
        assert len(terminal._transcript) == 260
        assert len(terminal._events) == 60 and len(terminal._replies) == 200
        log = terminal.query_one(RichLog)
        assert len(log.lines) == 260
        log.scroll_home(animate=False, immediate=True)
        await pilot.pause()
        assert "objective 20" in painted(pilot.app) and "objective 0" not in painted(pilot.app)
        log.scroll_to(y=30, animate=False, immediate=True)
        await pilot.pause()
        assert "reply 50" in painted(pilot.app)
        log.scroll_end(animate=False, immediate=True)
        await pilot.pause()
        assert "objective 79" in painted(pilot.app)


async def test_footer_zero_goal_and_invalid_elapsed_are_distinct_from_unavailable():
    async with TerminalApp().run_test(size=(96, 14)) as pilot:
        terminal = pilot.app.query_one(SurfboardTerminal)
        terminal.update_data(surfboard_footer=dict(FOOTER, market_value_usd=0))
        await pilot.pause()
        assert "$0.00 [··" in painted(pilot.app) and "[=" not in painted(pilot.app)
        terminal.update_age(float("nan"))
        await pilot.pause()
        assert "age unknown" in painted(pilot.app)


@pytest.mark.parametrize("state,expected", [("failed", "#8b342a"), ("working", "#b0edba"),
                                           ("future_state", "#9fc99c")])
async def test_event_state_has_bold_muted_failure_live_or_neutral_ink(state, expected):
    from rich.color import Color
    async with TerminalApp().run_test(size=(100, 14)) as pilot:
        terminal = pilot.app.query_one(SurfboardTerminal)
        row = dict(events(0, 1)[0], state=state, role="unknown", step="unknown")
        terminal.update_data(surfboard_events=[row])
        await pilot.pause()
        lines = painted(pilot.app).splitlines()
        y = next(i for i, line in enumerate(lines) if "objective 0" in line)
        x = lines[y].index(state)
        style = pilot.app.screen.get_style_at(x, y)
        assert style.bold
        assert style.color.get_truecolor() == Color.parse(expected).get_truecolor()


async def test_long_event_hint_keeps_every_stale_header_fact_and_service_at_live_rack_width():
    async with TerminalApp().run_test(size=(96, 18)) as pilot:
        terminal = pilot.app.query_one(SurfboardTerminal)
        row = dict(events(0, 1)[0], objective="long live objective " * 40)
        overview = dict(agents_online=869, working_now=35, jobs_24h=944, oracles_24h=237,
                        accepted_24h=32451, services=dict(verifier=True, publisher=True, deployer=True))
        terminal.update_data(surfboard_events=[row], surfboard_overview=overview,
                             surfboard_sources={"overview": {"state": "stale"}})
        await pilot.pause()
        header = next(line for line in painted(pilot.app).splitlines() if "869 online" in line)
        for fact in ("stale", "35 working", "944 jobs", "237 oracles", "V*", "P*", "D*", "‹ widen"):
            assert fact in header, header
        assert "32,451 steps" in header or "32.5K steps" in header


async def test_footer_figures_are_emphasized_without_bolding_the_labels():
    async with TerminalApp().run_test(size=(96, 14)) as pilot:
        terminal = pilot.app.query_one(SurfboardTerminal)
        terminal.update_data(surfboard_footer=FOOTER)
        await pilot.pause()
        lines = painted(pilot.app).splitlines()
        y = next(i for i, line in enumerate(lines) if "$33.69M" in line)
        for value in ("$33.69M", "189.1B", "10s"):
            assert pilot.app.screen.get_style_at(lines[y].index(value), y).bold
        assert not pilot.app.screen.get_style_at(lines[y].index("tokens used"), y).bold


async def test_both_stale_sources_and_fdv_keep_age_visible_at_narrow_rack_footer():
    async with TerminalApp().run_test(size=(90, 14)) as pilot:
        terminal = pilot.app.query_one(SurfboardTerminal)
        terminal.update_data(surfboard_footer=dict(FOOTER, market_basis="fdv", market_state="stale", overview_state="stale"))
        await pilot.pause()
        line = next(line for line in painted(pilot.app).splitlines() if "$33.69M" in line)
        for phrase in ("FDV", "mkt stale", "swarm stale", "189.1B", "10s", "$1B goal"):
            assert phrase in line, line
        assert "…" not in line and "‹ widen" not in line


async def test_joined_agent_ready_is_not_a_called_step_and_unassigned_node_is_queued():
    async with TerminalApp().run_test(size=(100, 16)) as pilot:
        terminal = pilot.app.query_one(SurfboardTerminal)
        joined = dict(events(0, 1)[0], kind="agent", role=None, step=None, state="ready")
        node = dict(events(1, 2)[0], kind="node", token_id=None, state="waiting", role=None, step=None)
        terminal.update_data(surfboard_events=[joined, node])
        await pilot.pause()
        text = painted(pilot.app)
        assert "joined  agent #420   ready" in text
        assert "job     swarm        queued" in text
        assert "called" not in text
