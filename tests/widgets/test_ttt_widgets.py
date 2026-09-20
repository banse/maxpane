"""Composited pins for the TTT dashboard widgets (Branch 7 WP-B, fix round 1).

Every assertion here is on **composited output** (``render_strips()``),
never on a content string, and every test names the mutation it exists to
redden. The review that asked for this module found five constants on
``TTTSignals`` and ``TTTSparkline`` that could be mutated with the whole
named set staying green -- the panel rendered differently and nothing
said so.

There is no ``TTTHeroMetrics`` / table coverage here: those are pinned
elsewhere (``tests/widgets/test_medi38_unavailable_state.py``,
``tests/widgets/test_title_blank_row.py``,
``tests/widgets/test_ttt_address_icons.py`` and the composited screen
sweep). This file covers what nothing else does.
"""

from __future__ import annotations

import pytest
from textual.app import App, ComposeResult

from maxpane_dashboard.widgets.ttt import TTTSignals, TTTSparkline


class _Harness(App):
    """Mount a single widget instance so we can drive ``update_data``."""

    def __init__(self, widget) -> None:
        super().__init__()
        self._widget = widget

    def compose(self) -> ComposeResult:
        yield self._widget


_PIN_SIZE = (120, 24)


async def _composited(widget, **payload) -> list[str]:
    """The widget's composited lines after one poll."""
    app = _Harness(widget)
    async with app.run_test(size=_PIN_SIZE) as pilot:
        widget.update_data(**payload)
        await pilot.pause()
        return [
            "".join(seg.text for seg in strip).rstrip()
            for strip in app.screen._compositor.render_strips()
        ]


def _line_with(lines: list[str], needle: str) -> str:
    matches = [line for line in lines if needle in line]
    assert len(matches) == 1, f"{needle!r} in {matches!r} of {lines!r}"
    return matches[0]


def _signal(value_str: str) -> dict:
    """A well-formed signal dict, the shape ``data/ttt_models.py`` declares."""
    return {
        "label": "ignored",          # the rows are label-less
        "value_str": value_str,
        "indicator": "●",
        "color": "green",
    }


# -- the fresh-launch row's display toggle ----------------------------
#
# ``TTTSignals.update_data`` hides the optional first row when the payload
# carries no fresh launch. Post-migration ``render_signal`` writes
# ``unavailable`` into that row *before* the toggle hides it, so if the
# toggle is lost, every live SIGNALS panel with no fresh launch gains a
# permanent ``● unavailable`` row and the three real rows shift down one.


@pytest.mark.asyncio
async def test_no_fresh_launch_hides_the_row_entirely():
    """Mutation: ``fresh.display = True`` -> this reddens.

    With no fresh launch the panel is buybacks / decay / separator /
    concentration, and the word ``unavailable`` appears nowhere: the row
    the base wrote it into is collapsed.
    """
    lines = await _composited(
        TTTSignals(),
        fresh_launch_signal=None,
        buybacks_ready_signal=_signal("3 ready"),
        decay_window_signal=_signal("2 decaying"),
        concentration_signal=_signal("1.4x vs today"),
    )
    assert not any("unavailable" in line for line in lines), lines
    # title, blank, then the three rows with the separator in place.
    body = [line for line in lines if line.strip()]
    assert body[0].strip().startswith("SIGNALS"), body
    assert "3 ready" in body[1], body
    assert "2 decaying" in body[2], body
    assert "1.4x vs today" in body[3], body
    # The separator really is a blank row between decay and concentration.
    decay_at = next(i for i, line in enumerate(lines) if "2 decaying" in line)
    conc_at = next(i for i, line in enumerate(lines) if "1.4x vs today" in line)
    assert conc_at == decay_at + 2, lines
    assert lines[decay_at + 1].strip() == "", lines


@pytest.mark.asyncio
async def test_a_fresh_launch_shows_the_row_at_the_top_of_the_panel():
    """The other direction: the toggle must not hide a row that exists.

    Mutation: ``fresh.display = False`` (or dropping the ``isinstance``
    test so a dict reads falsey) -> this reddens. Row index 3 is title,
    blank, fresh -- the blank is ``PanelBase``'s title margin, which no
    payload can cancel (CR2.2).
    """
    lines = await _composited(
        TTTSignals(),
        fresh_launch_signal=_signal("NEWT minted 4m ago"),
        buybacks_ready_signal=_signal("3 ready"),
        decay_window_signal=_signal("2 decaying"),
        concentration_signal=_signal("1.4x vs today"),
    )
    row = _line_with(lines, "NEWT minted 4m ago")
    assert lines.index(row) == 2, lines
    assert lines[0].strip().startswith("SIGNALS"), lines
    assert lines[1].strip() == "", lines


# -- the sparkline's four unpinned knobs -------------------------------

#: A rising series whose last value the two candidate formatters spell
#: differently: ``fmt_int`` -> ``1,900``, ``fmt_compact`` -> ``1.9K``.
_RISING = [[1_000 + i * 86_400, 1_000 + i * 100] for i in range(10)]

#: Volume in the millions: ``_fmt_volume_usd`` -> ``$1.23M``,
#: ``fmt_compact`` -> ``1.2M``.
_VOLUME = [[1_000 + i * 86_400, 1_200_000 + i * 34_000] for i in range(10)]


@pytest.mark.asyncio
async def test_both_sparkline_labels_are_padded_to_the_same_twelve_cells():
    """Mutation: ``LABEL_WIDTH = 12`` -> ``8`` -> this reddens.

    ``24H VOLUME $`` is exactly 12 cells, so at 12 both bars start in the
    same column and neither label is cut; at 8 the longer label truncates
    to ``24H VOLU`` and the two bars still line up -- which is why a
    same-column assertion alone would not bite.
    """
    lines = await _composited(
        TTTSparkline(), burns_history=_RISING, volume_history=_VOLUME,
    )
    burns = _line_with(lines, "BURNS")
    volume = _line_with(lines, "24H VOLUME $")
    # The label column is LABEL_WIDTH wide and left-justified, so the
    # shorter label is padded out to where the longer one ends.
    assert burns.index("BURNS") == volume.index("24H VOLUME $"), (burns, volume)
    start = burns.index("BURNS")
    assert burns[start:start + 12] == "BURNS       ", repr(burns)


@pytest.mark.asyncio
async def test_the_sparkline_draws_no_trend_arrow():
    """Mutation: ``SHOW_ARROW = True`` -> this reddens.

    The arrow is the base's default, this panel never drew one, and it
    arrives with a leading space: a ragged trailing cell.
    """
    lines = await _composited(
        TTTSparkline(), burns_history=_RISING, volume_history=_VOLUME,
    )
    for needle in ("BURNS", "24H VOLUME $"):
        row = _line_with(lines, needle)
        assert not any(glyph in row for glyph in ("▲", "▼", "●")), row


@pytest.mark.asyncio
async def test_the_volume_cell_is_dollars_at_two_decimals_not_a_compact_count():
    """Mutation: drop ``TTTSparkline.fmt_value`` -> this reddens.

    Volume is money and sits beside a price on the real screen:
    ``$1.23M``, not ``fmt_compact``'s ``1.2M``. The burns line proves the
    same override's other branch -- a grouped count, not ``1.9K``.
    """
    lines = await _composited(
        TTTSparkline(), burns_history=_RISING, volume_history=_VOLUME,
    )
    volume = _line_with(lines, "24H VOLUME $")
    assert volume.endswith("$1.51M"), volume
    burns = _line_with(lines, "BURNS")
    assert burns.endswith("1,900"), burns


@pytest.mark.asyncio
async def test_a_series_too_short_to_draw_keeps_its_label():
    """Mutation: ``MIN_POINTS = 1`` or ``EMPTY_KEEPS_LABEL = False``.

    One sample is drawn by ``build_sparkline_from_points`` as a flat
    baseline -- a run of zeroes that never happened -- so this panel says
    so in words, **beside the label**, because with two stacked series
    the reader has to be able to tell which one is not ready.
    """
    lines = await _composited(
        TTTSparkline(), burns_history=[[1_000, 5]], volume_history=_VOLUME,
    )
    burns = _line_with(lines, "BURNS")
    assert "waiting for data" in burns, burns
    # The other series is drawn, so this is not a panel that simply failed.
    assert "$1.51M" in _line_with(lines, "24H VOLUME $")
