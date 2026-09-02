"""``widgets/surf/_rowfit.py`` -- the shared row-fit ladder, and its fit.

Two things are pinned here, and only the second of them is new behaviour.

**The hoist.** ``_GAP``/``_row_cols``/``_budget``/the tier selector existed
twice in ``widgets/surf/`` and a third panel was about to copy them. The
copies are the defect CLAUDE.md names -- "three copies of one helper means a
fix reaches one of them" -- so the tests here assert that both surviving
callers *delegate* rather than re-implement, which is what stops the count
going back up.

**The fit.** Every measurement in that ladder was ``len()``. ``len()`` counts
characters where the terminal counts cells, so a ``RichLog(wrap=False)`` row
carrying CJK or an emoji was declared to fit a width it painted past -- and
``RichLog`` then narrowed it at write time **with no ``…``, no marker and
nothing in the title** (``.claude/skills/terminal-layout/SKILL.md``). This is
reachable input, not a theoretical edge: ``counterparty`` reaches
``SurfDevActivity`` from an arbitrary on-chain address's label, and the
launchpad's ``ticker`` comes from a permissionless
``launch(string,string)``.

Measured against **composited output** (``_compositor.render_strips()``),
joining segments per ROW first and then rows by newline -- joining every
segment with a newline splits one painted row into several apparent lines the
moment a row carries two styles, and a test written that way passes while the
user sees something else.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
from rich.cells import cell_len
from textual.app import App, ComposeResult
from textual.widgets import RichLog

from maxpane_dashboard.widgets.surf import _rowfit
from maxpane_dashboard.widgets.surf.activity import SurfDevActivity
from maxpane_dashboard.widgets.surf.launchpad_activity import (
    SurfLaunchpadActivity,
)

#: A counterparty label that is eight characters of two cells each plus a
#: two-cell emoji: nine characters, eighteen columns. ``KNOWN_LABELS`` is an
#: allowlist of ASCII labels today, so this is the *shape* of the hazard
#: rather than a live value -- but the widget renders whatever
#: ``counterparty`` it is handed, and the unknown branch runs an arbitrary
#: third-party string through ``_fmt.long_addr``, which measures in
#: characters too (see the note on that function in this file's own report).
_WIDE_LABEL = "海豚海豚海豚海豚🐬"

_WIDE_ROW = {
    "ts": 1786076603,
    "wallet_label": "dev",
    "kind": "transfer",
    "counterparty": _WIDE_LABEL,
    "counterparty_known": True,
    "value_eth": 1.5,
    "tx_hash": "0xabc",
}

#: A launchpad row whose *ticker* is the wide string --
#: ``LaunchpadFactory.launch(string,string)`` is permissionless and costs
#: only gas, so this one is genuinely attacker-chosen.
_WIDE_LP_ROW = {
    "kind": "buy",
    "ticker": _WIDE_LABEL,
    "wallet": "0x047F606fD5b2BaA5f5C6c4aB8958E45CB6B054B7",
    "wallet_known": False,
    "eth": 1.5,
    "age_s": 120.0,
}

#: Rich markup tags, for measuring a markup string the way the terminal will.
#: ``markup_safety.visible_len`` is the repo's own helper for this and is
#: **not** used here on purpose: it ends in ``len()``, so measuring a
#: wide-glyph row with it would reproduce the very defect under test.
_TAG = re.compile(r"\[/?[^\[\]]*\]")


def _visible_cells(markup: str) -> int:
    """Rendered **columns** of a markup string."""
    return cell_len(_TAG.sub("", markup or ""))


class _Harness(App):
    """One widget, alone, so the panel owns the whole terminal width."""

    def __init__(self, widget) -> None:
        super().__init__()
        self._widget = widget

    def compose(self) -> ComposeResult:
        yield self._widget


async def _composite(widget, payload_kwargs, size):
    """Render ``widget`` at ``size`` and return (log width, painted rows).

    Segments are joined per **row** first, then the rows are returned as a
    list -- the caller joins them by newline if it wants one string. The
    widget's own ``padding: 0 1`` means every painted row carries a leading
    space; it is left on, and the assertions allow for it.
    """
    app = _Harness(widget)
    async with app.run_test(size=size) as pilot:
        widget.update_data(**payload_kwargs)
        await pilot.pause()
        strips = pilot.app.screen._compositor.render_strips()
        rows = [
            "".join(segment.text for segment in strip).rstrip()
            for strip in strips
        ]
        log_width = widget.query_one(RichLog).scrollable_content_region.width
        return log_width, rows


# -- the fit ----------------------------------------------------------


def test_a_wide_glyph_row_is_never_built_wider_than_the_width_it_was_fitted_to():
    """``_row_markup``'s contract, on cells rather than on characters.

    The module's own docstring states it: "a markup string that is returned
    is **guaranteed to fit** ``width``, so ``RichLog.write()`` never has to
    shrink -- and therefore never clips without a visible ``…``". Measured
    with ``len()`` that guarantee was false for any row carrying a glyph
    wider than one cell, at 62 (tier, width) pairs for this one row alone.

    Swept across the whole band rather than at one comfortable width: the
    tier ladder sheds cells as the width drops, so the overflow moves, and a
    single-width test sits in whichever tier happens to be clean.
    """
    from maxpane_dashboard.widgets.surf.activity import FULL_WIDTH, _row_markup

    offenders = []
    for tier in ("full", "compact", "minimal"):
        for width in range(10, FULL_WIDTH + 20):
            markup = _row_markup(_WIDE_ROW, tier, width)
            if markup is None:
                continue  # withheld, which is an honest answer
            painted = _visible_cells(markup)
            if painted > width:
                offenders.append((tier, width, painted))

    assert not offenders, (
        "rows were declared to fit a width they paint past -- "
        "`RichLog(wrap=False)` narrows those at write time with no `…` and "
        f"no marker:\n{offenders[:8]}"
    )


@pytest.mark.asyncio
async def test_a_wide_glyph_counterparty_is_painted_whole_or_visibly_elided():
    """The composited half, and the one that shows what the reader loses.

    A value on this panel is rendered **whole**, or cut with a visible ``…``
    that says so. Never simply shortened: a label that stops mid-run reads as
    a complete label, which for the field this panel exists to disambiguate
    is the entire failure mode (``activity.py``'s ``FLOOR_WIDTH`` note --
    both live spoof addresses collide with their targets once the window is
    cut).

    Before the fix this failed at four terminal widths in this band. Three of
    them (30, 31, 32) painted ``海豚海豚海豚海`` -- the label two glyphs
    short with nothing to say so -- and one (49) dropped the emoji the same
    way. In every one of those cases ``‹ widen`` *was* lit, which is why the
    marker alone cannot stand in for this assertion: it was lit about a shed
    *column*, while a second, unannounced cut happened inside a cell.
    """
    offenders = []
    for terminal in range(30, 82):
        log_width, rows = await _composite(
            SurfDevActivity(), {"dev_activity": [_WIDE_ROW]}, (terminal, 14)
        )
        body = [
            row for row in rows if row.strip() and "DEV ACTIVITY" not in row
        ]
        if not body:
            continue  # the panel withheld the batch; honest
        painted = body[0].lstrip()
        if not painted or "widen" in painted:
            continue  # the withheld-rows state, written into the log
        whole = _WIDE_LABEL in painted
        elided = "…" in painted
        if not (whole or elided):
            offenders.append((terminal, log_width, painted))

    assert not offenders, (
        "the counterparty was cut with no `…` -- a shortened label reads as "
        f"a complete one:\n{offenders}"
    )


@pytest.mark.asyncio
async def test_the_launchpad_row_fits_a_wide_glyph_ticker_too():
    """The second caller, on the field that is genuinely attacker-chosen.

    ``launchpad_activity`` already fitted its ticker on ``cell_len`` before
    the hoist, so this one is a **regression guard rather than a biter**: it
    was green on both sides of the change, and it is here so that a future
    edit to the shared ladder cannot quietly take that panel's fit away with
    it. Recorded as such rather than presented as evidence the fix works.
    """
    log_width, rows = await _composite(
        SurfLaunchpadActivity(),
        {"launchpad_activity": [_WIDE_LP_ROW]},
        (60, 14),
    )
    body = [row for row in rows if row.strip() and "LAUNCHPAD" not in row]
    for row in body:
        painted = row.lstrip()
        if not painted or "widen" in painted:
            continue
        assert cell_len(painted) <= log_width, (
            f"a {cell_len(painted)}-column row in a {log_width}-column log: "
            f"{painted!r}"
        )


def test_rowfit_measures_cells_and_not_characters():
    """The primitives, directly. ``clip`` and ``pad`` are mirror images.

    ``clip`` on ``len()`` returns too many columns; ``f"{v:<{w}}"`` pads to a
    character count and so under-pads a wide cell. A cell that is short by
    two columns moves every cell to its right, which is the alignment defect
    ``activity.py``'s batch plan exists to prevent.
    """
    assert cell_len(_WIDE_LABEL) == 18
    assert len(_WIDE_LABEL) == 9

    # Clipped to a cell budget, never a character budget.
    for width in range(2, 20):
        assert cell_len(_rowfit.clip(_WIDE_LABEL, width)) <= width

    # Padded to a cell budget: a wide cell is not under-filled.
    assert cell_len(_rowfit.pad("海", 6)) == 6
    assert cell_len(_rowfit.pad("ab", 6)) == 6

    # And the budget itself. `activity.py`'s own cell widths, so the numbers
    # below are that panel's row: stamp 11, wallet 3, kind 9, amount 12.
    def needed(who_cols: int, wallet: int, stamp: bool) -> int:
        return _rowfit.row_cols((11 if stamp else 0, wallet, 9, who_cols), 12)

    # The narrowest width at which a plan for this label *can* fit: every
    # sheddable cell gone and the label cut to its own floor. Derived rather
    # than typed, so it tracks the constants above instead of going stale.
    floor = needed(cell_len(_rowfit.clip(_WIDE_LABEL, 6)), 0, False)

    offenders = []
    for width in range(floor, 60):
        keep_stamp, wallet_cols, who = _rowfit.budget(
            width, _WIDE_LABEL, True, needed, 3, True, 6
        )
        painted = needed(cell_len(who), wallet_cols, keep_stamp)
        if painted > width:
            offenders.append((width, painted, who))

    assert not offenders, (
        "`budget` handed back a plan that does not fit the width it was "
        "given, at a width where one was available -- it cut and measured "
        f"the label in characters:\n{offenders}"
    )


# -- the hoist --------------------------------------------------------


def test_both_callers_delegate_the_ladder_instead_of_re_implementing_it():
    """The count of copies is what this package exists to hold at one.

    Asserted on the callers' own ASTs rather than on a grep for the helper
    names: both modules keep ``_row_cols``/``_budget``/``_tier_for`` as
    *names* (their own tests import them, and their docstrings carry each
    panel's own reasoning), so the question is not whether the name is there
    but whether the arithmetic behind it is a second copy.
    """
    for name in ("activity", "launchpad_activity"):
        path = (
            Path(__file__).resolve().parents[2]
            / "maxpane_dashboard"
            / "widgets"
            / "surf"
            / f"{name}.py"
        )
        tree = ast.parse(path.read_text(encoding="utf-8"))
        functions = {
            node.name: node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
        }
        for helper in ("_row_cols", "_budget", "_tier_for"):
            node = functions.get(helper)
            if node is None:
                continue
            calls = {
                ast.unparse(child.func)
                for child in ast.walk(node)
                if isinstance(child, ast.Call)
                and isinstance(child.func, ast.Attribute)
            }
            assert any(call.startswith("_rowfit.") for call in calls), (
                f"{name}.{helper} does not call into `_rowfit` -- the ladder "
                "has been copied back out"
            )


def test_rowfit_is_pure_enough_for_a_widget_to_import():
    """It sits under ``widgets/``, so it may reach neither I/O nor a clock.

    The frozen module-boundary table for the pool4 build lists ``_rowfit``
    among the three modules a ``widgets/surf/pool4_*.py`` may import; that is
    only true while this holds.
    """
    path = Path(_rowfit.__file__)
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    forbidden = {"httpx", "aiohttp", "textual", "time", "datetime", "asyncio"}
    assert not (imported & forbidden), (
        f"`_rowfit` reaches {sorted(imported & forbidden)}"
    )
    assert not any(
        name.startswith("maxpane_dashboard.data")
        or name.startswith("maxpane_dashboard.analytics")
        for name in imported
    )
