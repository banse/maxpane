"""``widgets/surf/swarm_record_filter``: RECORD's ``f`` editor over THE LIST's chrome.

The shared chrome (error line, grid, ranges, dropdowns, APPLY / RESET) is
``tests/widgets/test_filter_editor.py``'s; this file is what surf adds -- the
three checkbox groups built from the seat's own rows, the dropdown vocabularies
bound to the analytics module, and the footer summary. Composited output, no
network.
"""

from __future__ import annotations

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Checkbox, Select, Static

from maxpane_dashboard.analytics.surf_record_filter import (
    ANSWER_STATES,
    PANEL_STATES,
    WHEN_SECONDS,
    RecordFilter,
    parse_record_filter,
)
from maxpane_dashboard.widgets.filter_editor import APPLY_ID, RESET_ID, field_id
from maxpane_dashboard.widgets.surf._fmt import mmdd_hhmm
from maxpane_dashboard.widgets.surf.swarm_record_filter import (
    ANSWER_LABELS,
    BOX_GROUPS,
    PANEL_LABELS,
    WHEN_LABELS,
    RecordFilterApplyRequested,
    RecordFilterResetRequested,
    SurfRecordFilterEditor,
    choice_label,
    filter_summary,
)

NOW = 1_790_000_000.0
CHOICES = {
    "nodes": ("oracle_assess", "codex-14", "[red]evil[/red]"),
    "states": ("completed", "failed"),
    # Two raw ids, one short label: one box stands for both.
    "models": ("claude-opus-4-1", "[b]claude-opus-4-1[/b]", "gpt-6-astra"),
}


class _Harness(App):
    def __init__(self) -> None:
        super().__init__()
        self.editor = SurfRecordFilterEditor()
        self.messages: list[str] = []

    def compose(self) -> ComposeResult:
        yield self.editor

    def on_record_filter_apply_requested(self, _event) -> None:
        self.messages.append("apply")

    def on_record_filter_reset_requested(self, _event) -> None:
        self.messages.append("reset")


def _screen_text(app) -> str:
    strips = app.screen._compositor.render_strips()
    return "\n".join("".join(seg.text for seg in strip) for strip in strips)


def _box(editor, label: str) -> Checkbox:
    matches = [box for box in editor.query(Checkbox) if str(box.label) == label]
    assert len(matches) == 1, (label, [str(box.label) for box in editor.query(Checkbox)])
    return matches[0]


# -- vocabularies -------------------------------------------------------------


@pytest.mark.parametrize(("labels", "keys"), [
    (WHEN_LABELS, WHEN_SECONDS), (PANEL_LABELS, PANEL_STATES), (ANSWER_LABELS, ANSWER_STATES),
])
def test_every_dropdown_word_has_a_label_and_nothing_else_does(labels, keys):
    assert set(labels) == set(keys)


def test_the_dropdowns_offer_any_then_the_analytics_words_in_order():
    options = SurfRecordFilterEditor.SELECT_OPTIONS
    assert options["when"] == (("Any", "any"), *((WHEN_LABELS[k], k) for k in WHEN_SECONDS))
    assert [value for _label, value in options["panel"]] == ["any", *PANEL_STATES]
    assert [value for _label, value in options["answer"]] == ["any", *ANSWER_STATES]


def test_the_apply_message_is_surfs_own_not_curators():
    from maxpane_dashboard.widgets.curator.list_filter import FilterApplyRequested, FilterResetRequested
    assert SurfRecordFilterEditor.APPLY_MESSAGE is RecordFilterApplyRequested
    assert SurfRecordFilterEditor.RESET_MESSAGE is RecordFilterResetRequested
    assert not issubclass(RecordFilterApplyRequested, FilterApplyRequested)
    assert not issubclass(RecordFilterResetRequested, FilterResetRequested)


# -- labels and summary -------------------------------------------------------


@pytest.mark.parametrize(("field", "value", "expected"), [
    ("nodes", "oracle_assess", "oracle"),
    ("nodes", "adversarial_review", "review"),
    ("nodes", "codex-14", "codex-14"),
    ("nodes", "[red]evil[/red]", "evil"),
    ("nodes", "a_very_long_unknown_node_key", "a_very_long_unk…"),
    ("models", "claude-opus-4-1", "opus 4.1"),
    ("models", "[b]claude-opus-4-1[/b]", "opus 4.1"),
    ("models", "x" * 30, "x" * 15 + "…"),
    ("states", "completed", "completed"),
    ("states", "[i]odd[/i]", "odd"),
])
def test_choice_label(field, value, expected):
    assert choice_label(field, value) == expected


def test_summary_reads_in_the_editors_order_with_or_inside_a_group():
    spec = parse_record_filter({
        "nodes": frozenset({"oracle_assess", "codex-14"}), "states": frozenset({"failed"}),
        "when": "7d", "models": frozenset({"claude-opus-4-1"}), "panel": "no_quorum",
        "answer": "no_reply", "took_min": "2", "took_max": "10", "tok_min": "500",
    }, now_ts=NOW)
    assert filter_summary(spec) == (
        f"codex-14 or oracle · failed · since {mmdd_hhmm(NOW - 7 * 86_400)} · opus 4.1"
        " · panel no quorum · no reply · took 2-10 min · tok >=500"
    )


def test_summary_of_one_group_and_of_nothing():
    assert filter_summary(RecordFilter(answer="replied")) == "replied"
    assert filter_summary(RecordFilter()) == ""


# -- the editor ---------------------------------------------------------------


async def test_load_builds_one_box_per_label_with_third_party_words_literal():
    app = _Harness()
    async with app.run_test(size=(140, 40)) as pilot:
        await app.editor.load(CHOICES, {})
        await pilot.pause()
        labels = [str(box.label) for box in app.editor.query(Checkbox)]
        assert labels == ["oracle", "codex-14", "evil", "completed", "failed", "opus 4.1", "astra 6"]
        text = _screen_text(app)
        for title in ("NODE", "STATE", "WHEN", "MODEL", "PANEL", "ANSWER", "TOOK · minutes", "TOK · output"):
            assert title in text, title
        assert "[red]" not in text and "evil" in text
        assert "rows not read yet are counted under RECORD" in text


async def test_values_union_every_raw_id_behind_a_ticked_box():
    app = _Harness()
    async with app.run_test(size=(140, 40)) as pilot:
        await app.editor.load(CHOICES, {})
        _box(app.editor, "opus 4.1").value = True
        _box(app.editor, "oracle").value = True
        app.editor.query_one(f"#{field_id('when')}", Select).value = "24h"
        await pilot.pause()
        values = app.editor.values()
        assert values["models"] == frozenset({"claude-opus-4-1", "[b]claude-opus-4-1[/b]"})
        assert values["nodes"] == frozenset({"oracle_assess"})
        assert values["states"] == frozenset()
        assert values["when"] == "24h"
        assert values["took_min"] == ""


async def test_load_shows_stored_values_and_set_values_resets_the_draft():
    app = _Harness()
    stored = {"nodes": frozenset({"codex-14"}), "models": frozenset({"[b]claude-opus-4-1[/b]"}),
              "panel": "outvoted", "tok_max": 900}
    async with app.run_test(size=(140, 40)) as pilot:
        await app.editor.load(CHOICES, stored)
        await pilot.pause()
        assert _box(app.editor, "codex-14").value is True
        assert _box(app.editor, "opus 4.1").value is True, "one raw id ticks its shared box"
        assert _box(app.editor, "oracle").value is False
        assert app.editor.query_one(f"#{field_id('panel')}", Select).value == "outvoted"
        assert app.editor.values()["tok_max"] == "900"
        app.editor.set_values({})
        await pilot.pause()
        assert not any(box.value for box in app.editor.query(Checkbox))
        assert app.editor.values()["panel"] == "any"
        assert app.editor.values()["tok_max"] == ""


async def test_reloading_replaces_the_boxes_without_an_id_collision():
    app = _Harness()
    async with app.run_test(size=(140, 40)) as pilot:
        await app.editor.load(CHOICES, {})
        await app.editor.load({"nodes": ("hunt_d",)}, {})
        await pilot.pause()
        assert [str(box.label) for box in app.editor.query(Checkbox)] == ["hunt_d"]
        empties = [str(w.render()) for w in app.editor.query(".record-filter-empty").results(Static)]
        assert empties == ["no states yet", "no models read yet"]
        assert app.editor.values()["models"] == frozenset()


@pytest.mark.parametrize(("raw", "selected"), [
    ("codex-14", frozenset()),  # a string is not a selection
    (None, frozenset()),
    (3, frozenset()),
])
async def test_a_malformed_stored_group_ticks_nothing(raw, selected):
    app = _Harness()
    async with app.run_test(size=(140, 40)) as pilot:
        await app.editor.load(CHOICES, {"nodes": raw})
        await pilot.pause()
        assert app.editor.values()["nodes"] == selected


async def test_apply_and_reset_post_surfs_messages():
    app = _Harness()
    async with app.run_test(size=(140, 40)) as pilot:
        await app.editor.load(CHOICES, {})
        await pilot.pause()
        await pilot.click(f"#{APPLY_ID}")
        await pilot.click(f"#{RESET_ID}")
        await pilot.pause()
        assert app.messages == ["apply", "reset"]


@pytest.mark.parametrize("field", [field for field, *_rest in BOX_GROUPS])
def test_every_box_group_is_a_record_filter_set(field):
    assert isinstance(getattr(RecordFilter(), field), frozenset)


async def test_the_last_option_of_the_tallest_group_is_drawn():
    """A grid row is sized to its tallest group, then a margin is taken out of it.

    THE LIST's ``margin-bottom`` gap costs its one-line controls only a blank
    line; on a box group it cut the last option off with nothing to say so
    (found 2026-10-02: three NODE boxes, two drawn). Asserted on the
    compositor, not on the widget tree, which held the box all along.
    """
    nodes = tuple(f"node-{i}" for i in range(6))
    app = _Harness()
    async with app.run_test(size=(140, 40)) as pilot:
        await app.editor.load({"nodes": nodes}, {})
        await pilot.pause()
        text = _screen_text(app)
        for node in nodes:
            assert node in text, (node, text)
        last = _box(app.editor, "node-5")
        group = last.parent.parent
        assert group.region.contains_region(last.region)


async def test_a_one_line_dropdown_still_opens_its_options():
    app = _Harness()
    async with app.run_test(size=(140, 40)) as pilot:
        await app.editor.load(CHOICES, {})
        await pilot.pause()
        select = app.editor.query_one(f"#{field_id('when')}", Select)
        assert select.region.height == 1
        await pilot.click(f"#{field_id('when')}")
        await pilot.pause()
        assert select.expanded
        assert "Last 7 days" in _screen_text(app)
