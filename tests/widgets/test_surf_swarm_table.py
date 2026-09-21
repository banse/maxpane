"""``widgets/surf/_swarm_table.SwarmTableBase`` on its own (WP7 hoist).

The six tables' files test their columns and cells; this file tests the
mechanics they share, on a three-column stand-in, composited. Three things
are pinned here because a subclass test cannot see them fail cleanly:

* a **tier change re-installs the columns** on the ``DataTable`` (never a
  zero-width column left behind for the sweep's ``max_scroll_x`` to miss);
* the **footer / ``No data`` rule** in both homes -- an in-table degraded word
  when ``EMPTY_LINE`` is unset, a sentence under the table when it is set --
  and ``None`` never reading as ``[]`` in either;
* **``on_mount`` installs once.** Textual dispatches ``on_mount`` for every
  class in the MRO, so an explicit ``super().on_mount()`` in the base's
  handler would run ``TableLeaderboard.on_mount`` twice and double every
  column (mutation: add the super call, the column-count test goes red).
"""

from __future__ import annotations

from textual.app import App
from textual.widgets import DataTable, Static

from maxpane_dashboard.widgets import rowfit
from maxpane_dashboard.widgets.panels import TableLeaderboard
from maxpane_dashboard.widgets.surf._swarm_table import (
    CELL_PADDING,
    SwarmTableBase,
    table_cols,
)
from tests.widgets.surf_compositing import composite_lines

#: ``alpha`` is 12 so ``unavailable`` (11) has a column that shows it whole.
_SPECS = (("a", "alpha", 12), ("b", "beta", 8), ("c", "gamma", 6))
_ALL = ("a", "b", "c")
_COMPACT = ("a", "c")
FULL = table_cols([12, 8, 6])        # 32
COMPACT = table_cols([12, 6])        # 22
ROWS = [{"a": "one", "b": "two", "c": "3"}, {"a": "four", "b": "five", "c": "6"}]


class _Table(SwarmTableBase):
    TITLE = "STAND-IN"
    TABLE_ID = "stand-in-table"
    CURSOR_TYPE = "none"
    COLUMN_SPECS = _SPECS
    TIER_COLUMNS = {"full": _ALL, "compact": _COMPACT}
    LADDER = rowfit.Ladder(("full", FULL), ("compact", COMPACT))
    EMPTY_ROW = ("No data", "", "")

    def update_data(self, rows=None, as_of=None, summary=None, **_kwargs):
        self.store(rows, as_of, summary)

    def build_cells(self, item):
        return {key: str(item.get(key, "")) for key in _ALL}

    def build_footer(self, summary):
        return None if summary is None else tuple(summary)


class _Sentence(_Table):
    TABLE_ID = "stand-in-sentence-table"
    EMPTY_LINE = "nothing here yet"


class _A(App):
    def __init__(self, cls):
        super().__init__()
        self._cls = cls

    def compose(self):
        yield self._cls()


async def _mounted(cls, size, **kwargs):
    """``(rows, table, footer)`` after one ``update_data``."""
    app = _A(cls)
    async with app.run_test(size=size) as pilot:
        widget = pilot.app.query_one(cls)
        widget.update_data(**kwargs)
        await pilot.pause()
        strips = pilot.app.screen._compositor.render_strips()
        rows = ["".join(seg.text for seg in strip) for strip in strips]
        table = pilot.app.query_one(f"#{cls.TABLE_ID}", DataTable)
        footer = pilot.app.query_one(f"#{cls.TABLE_ID}-footer", Static)
        return rows, {
            "columns": [str(c.label) for c in table.columns.values()],
            "widths": [c.width for c in table.columns.values()],
            "row_count": table.row_count,
            "footer_display": footer.display,
            "footer_text": footer.render().plain if footer.display else "",
        }


# -- table_cols -------------------------------------------------------------


def test_table_cols_charges_every_column_its_padding_including_the_last():
    assert table_cols([12, 8, 6]) == 12 + 8 + 6 + CELL_PADDING * 3
    assert table_cols([]) == CELL_PADDING


# -- one mount, one install -------------------------------------------------


async def test_on_mount_installs_the_columns_exactly_once():
    _rows, facts = await _mounted(_Table, (FULL + 4, 10), rows=ROWS, as_of="04:06")
    assert facts["columns"] == ["alpha", "beta", "gamma"], facts
    assert facts["widths"] == [12, 8, 6], facts


async def test_the_base_declares_no_super_mount_and_the_leaderboard_mount_still_runs():
    """Both handlers run (MRO dispatch): the base's seeds ``_installed``, the
    leaderboard's sets the cursor type -- and the columns are not doubled."""
    _rows, facts = await _mounted(_Table, (FULL + 4, 10), rows=ROWS)
    assert len(facts["columns"]) == len(_SPECS)
    assert TableLeaderboard.on_mount is not SwarmTableBase.on_mount


async def test_a_payload_stored_before_mount_is_painted_after_it():
    class _Early(App):
        def compose(self):
            widget = _Table()
            widget.update_data(rows=ROWS, as_of="04:06")   # before compose returns
            yield widget

    async with _Early().run_test(size=(FULL + 4, 10)) as pilot:
        await pilot.pause()
        table = pilot.app.query_one(f"#{_Table.TABLE_ID}", DataTable)
        assert table.row_count == 2
        assert len(table.columns) == 3
        strips = pilot.app.screen._compositor.render_strips()
        text = "\n".join("".join(seg.text for seg in strip) for strip in strips)
        assert "four" in text and "as of 04:06" in text


# -- tier change ------------------------------------------------------------


async def test_a_narrower_panel_removes_the_shed_column_from_the_table():
    wide, facts_wide = await _mounted(_Table, (FULL + 2, 10), rows=ROWS)
    assert facts_wide["columns"] == ["alpha", "beta", "gamma"]
    assert "beta" in "\n".join(wide)
    narrow, facts_narrow = await _mounted(_Table, (FULL + 1, 10), rows=ROWS)
    assert facts_narrow["columns"] == ["alpha", "gamma"], "shed, not zero-width"
    text = "\n".join(narrow)
    assert "beta" not in text and "five" not in text
    assert "‹ widen" in text


async def test_a_resize_across_the_threshold_reinstalls_columns_in_place():
    app = _A(_Table)
    async with app.run_test(size=(FULL + 2, 10)) as pilot:
        widget = pilot.app.query_one(_Table)
        widget.update_data(rows=ROWS)
        await pilot.pause()
        table = pilot.app.query_one(f"#{_Table.TABLE_ID}", DataTable)
        assert [str(c.label) for c in table.columns.values()] == ["alpha", "beta", "gamma"]
        await pilot.resize_terminal(FULL + 1, 10)
        await pilot.pause()
        assert [str(c.label) for c in table.columns.values()] == ["alpha", "gamma"]
        assert table.row_count == 2
        await pilot.resize_terminal(FULL + 2, 10)
        await pilot.pause()
        assert [str(c.label) for c in table.columns.values()] == ["alpha", "beta", "gamma"]


async def test_the_full_tier_at_exactly_its_width_shows_no_hint():
    lines = await composite_lines(_Table, (FULL + 2, 10), rows=ROWS)
    assert "‹ widen" not in "\n".join(lines)


# -- footer and No data, in-table home --------------------------------------


async def test_an_empty_list_with_no_footer_paints_no_data_in_the_table():
    _rows, facts = await _mounted(_Table, (FULL + 4, 10), rows=[])
    assert facts["row_count"] == 1 and not facts["footer_display"]
    assert "No data" in "\n".join(_rows)


async def test_an_empty_list_under_a_footer_paints_the_footer_and_no_no_data():
    rows, facts = await _mounted(_Table, (FULL + 4, 10), rows=[], summary=("0 things", "none"))
    text = "\n".join(rows)
    assert facts["row_count"] == 0 and facts["footer_display"]
    assert "0 things · none" in text and "No data" not in text


async def test_none_is_unavailable_never_no_data_even_under_a_footer():
    rows, facts = await _mounted(_Table, (FULL + 4, 10), rows=None, summary=("2 things",))
    text = "\n".join(rows)
    assert "unavailable" in text and "No data" not in text
    assert facts["row_count"] == 1 and facts["footer_display"]


async def test_the_footer_is_one_line_clipped_to_the_panel():
    rows, facts = await _mounted(
        _Table, (FULL + 4, 10), rows=ROWS,
        summary=("a very long first part", "a very long second part", "and a third"),
    )
    footer = next(line for line in rows if "a very long first" in line)
    assert "…" in footer and "and a third" not in footer
    assert len(footer.rstrip()) <= FULL + 4


async def test_a_footer_word_is_stripped_of_markup_not_parsed():
    rows, facts = await _mounted(_Table, (FULL + 4, 10), rows=ROWS, summary=("3 [red]x[/] things",))
    assert facts["footer_text"] == "3 x things"


async def test_the_degraded_word_lands_in_the_first_column_wide_enough():
    class _Narrow(_Table):
        TABLE_ID = "stand-in-narrow-table"
        COLUMN_SPECS = (("a", "#", 4), ("b", "beta", 12), ("c", "gamma", 6))
        EMPTY_ROW = ("No data", "", "")

    rows, facts = await _mounted(_Narrow, (FULL + 4, 10), rows=None)
    line = next(line for line in rows if "unavailable" in line)
    # column ``#`` is 4 cells; the word sits under ``beta``, whole.
    header = next(line for line in rows if "beta" in line)
    assert line.index("unavailable") >= header.index("beta") - 1


# -- footer sentence home ---------------------------------------------------


async def test_a_sentence_table_writes_its_empty_line_under_an_empty_table():
    """``EMPTY_ROW`` is inherited and non-empty here on purpose: the sentence
    home never consults it."""
    rows, facts = await _mounted(_Sentence, (FULL + 4, 10), rows=[])
    text = "\n".join(rows)
    assert facts["row_count"] == 0 and facts["footer_display"]
    assert "nothing here yet" in text and "No data" not in text
    assert "alpha" in text, "the header stays"


async def test_a_sentence_table_says_unavailable_for_none_and_for_a_non_list():
    rows, _f = await _mounted(_Sentence, (FULL + 4, 10), rows=None)
    assert "unavailable" in "\n".join(rows) and "nothing here yet" not in "\n".join(rows)
    rows, _f = await _mounted(_Sentence, (FULL + 4, 10), rows={"not": "a list"})
    assert "unavailable" in "\n".join(rows) and "nothing here yet" not in "\n".join(rows)


async def test_a_sentence_table_hides_the_footer_once_rows_arrive():
    rows, facts = await _mounted(_Sentence, (FULL + 4, 10), rows=ROWS)
    assert not facts["footer_display"] and facts["row_count"] == 2
    assert "nothing here yet" not in "\n".join(rows)


# -- rows -------------------------------------------------------------------


async def test_a_non_dict_item_is_skipped_and_the_rest_render():
    rows, facts = await _mounted(_Table, (FULL + 4, 10), rows=[ROWS[0], "garbage", ROWS[1]])
    assert facts["row_count"] == 2
    assert "four" in "\n".join(rows)


async def test_a_none_from_build_cells_skips_the_item():
    class _Picky(_Table):
        TABLE_ID = "stand-in-picky-table"

        def build_cells(self, item):
            return None if item.get("a") == "one" else super().build_cells(item)

    rows, facts = await _mounted(_Picky, (FULL + 4, 10), rows=ROWS)
    assert facts["row_count"] == 1 and "one" not in "\n".join(rows)


async def test_the_title_carries_the_marker_only_when_real_and_clips_it():
    lines = await composite_lines(_Table, (FULL + 4, 10), rows=ROWS, as_of=None)
    assert "as of" not in "\n".join(lines)
    lines = await composite_lines(_Table, (FULL + 4, 10), rows=ROWS, as_of="04:06:59 tampered")
    title = next(line for line in lines if "STAND-IN" in line)
    assert "as of 04:0…" in title and "tampered" not in title
