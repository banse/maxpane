"""``widgets/filter_editor.FilterEditorBase``: the chrome THE LIST and surf RECORD share."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from textual.app import App, ComposeResult
from textual.containers import Grid
from textual.message import Message
from textual.widgets import Button

from maxpane_dashboard.widgets import filter_editor
from maxpane_dashboard.widgets.filter_editor import FilterEditorBase, field_id


class ProbeApplied(Message):
    pass


class ProbeReset(Message):
    pass


class _Editor(FilterEditorBase):
    ERROR_ID = "probe-error"
    RANGE_FIELDS = ("size_min", "size_max")
    SELECT_OPTIONS = {"kind": (("Any", "any"), ("Red", "red"), ("Blue", "blue"))}
    APPLY_MESSAGE = ProbeApplied
    RESET_MESSAGE = ProbeReset

    def __init__(self) -> None:
        super().__init__()
        self.others: list[str] = []

    def compose(self) -> ComposeResult:
        yield self.error_line()
        with Grid(classes="filter-groups"):
            yield self.range_group("SIZE", (("size_min", "from"), ("size_max", "to")))
            yield self.select_group("KIND", "kind")
            yield self.titled_group("EXTRA", Button("+", id="probe-extra", compact=True))
        yield self.section_title("MORE")
        yield self.actions()

    def other_button_pressed(self, event: Button.Pressed) -> None:
        self.others.append(str(event.button.id))


class _Harness(App):
    def __init__(self, editor) -> None:
        super().__init__()
        self.editor = editor
        self.messages: list[str] = []

    def compose(self) -> ComposeResult:
        yield self.editor

    def on_probe_applied(self, _event) -> None:
        self.messages.append("apply")

    def on_probe_reset(self, _event) -> None:
        self.messages.append("reset")


def _screen_text(app) -> str:
    strips = app.screen._compositor.render_strips()
    return "\n".join("".join(seg.text for seg in strip) for strip in strips)


def test_field_id_is_the_curator_spelling():
    assert field_id("join_min") == "filter-join-min"
    assert field_id("ens") == "filter-ens"


async def test_builders_composite_titles_controls_and_actions():
    app = _Harness(_Editor())
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        text = _screen_text(app)
        for word in ("SIZE", "KIND", "EXTRA", "MORE", "Any", "APPLY FILTER", "RESET ALL"):
            assert word in text, word
        for control_id in ("filter-size-min", "filter-size-max", "filter-kind", "probe-error"):
            assert app.editor.query_one(f"#{control_id}") is not None


async def test_values_round_trip_and_set_values_resets_first():
    editor = _Editor()
    app = _Harness(editor)
    async with app.run_test(size=(120, 30)) as pilot:
        editor.set_values({"size_min": 3, "size_max": "9", "kind": "red"})
        await pilot.pause()
        assert editor.values() == {"size_min": "3", "size_max": "9", "kind": "red"}
        assert "Red" in _screen_text(app)

        editor.set_values({"size_max": None, "kind": "green"})
        await pilot.pause()
        assert editor.values() == {"size_min": "", "size_max": "", "kind": "any"}


async def test_apply_and_reset_post_the_subclasss_messages_and_other_buttons_reach_the_hook_once():
    """Textual dispatches ``on_button_pressed`` on every class in the MRO, so a
    subclass handler would run beside the base's: the hook is called once and
    apply/reset never reach it."""
    editor = _Editor()
    app = _Harness(editor)
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.click("#filter-apply")
        await pilot.click("#filter-reset-all")
        await pilot.click("#probe-extra")
        await pilot.pause()
        assert app.messages == ["apply", "reset"]
        assert editor.others == ["probe-extra"]


async def test_show_error_marks_focuses_and_clear_error_unmarks():
    editor = _Editor()
    app = _Harness(editor)
    async with app.run_test(size=(120, 30)) as pilot:
        editor.show_error("size_max", "size_min must not exceed size_max")
        await pilot.pause()
        control = editor.query_one("#filter-size-max")
        assert control.has_class("filter-invalid") and control.has_focus
        assert "size_min must not exceed size_max" in _screen_text(app)

        editor.show_error("size_min", "size_min must be a non-negative number")
        await pilot.pause()
        assert not control.has_class("filter-invalid")
        assert editor.query_one("#filter-size-min").has_class("filter-invalid")

        editor.clear_error()
        await pilot.pause()
        assert not editor.query(".filter-invalid")
        assert "non-negative" not in _screen_text(app)


async def test_an_error_for_a_field_with_no_control_still_shows_its_message():
    editor = _Editor()
    app = _Harness(editor)
    async with app.run_test(size=(120, 30)) as pilot:
        editor.show_error("nowhere", "something is off")
        await pilot.pause()
        assert "something is off" in _screen_text(app)
        assert not editor.query(".filter-invalid")


@pytest.mark.parametrize(("width", "compact"), ((80, True), (103, True), (104, False), (140, False)))
async def test_the_grid_goes_compact_below_its_threshold(width, compact):
    """``padding: 0 2`` makes 104 the first terminal width with 100 content columns."""
    editor = _Editor()
    app = _Harness(editor)
    async with app.run_test(size=(width, 30)) as pilot:
        await pilot.pause()
        assert editor.has_class("compact-filter") is compact
        grid = editor.query_one(".filter-groups", Grid)
        assert grid.styles.grid_size_columns == (2 if compact else 4)


@pytest.mark.guard
def test_the_shared_editor_imports_neither_data_nor_analytics():
    tree = ast.parse(Path(filter_editor.__file__).read_text())
    modules = {
        node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    } | {
        alias.name
        for node in ast.walk(tree) if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert not any(".data" in name or ".analytics" in name for name in modules), modules
