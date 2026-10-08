"""The recent window reconciles without destroying draft, replies or anchors."""
from textual.app import App
from textual.widgets import RichLog
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
