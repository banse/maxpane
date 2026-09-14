"""Review fix round 1 (Task 7, Important finding): the SYM-column growth for
the copy icon was never swept at the **screen** level.

``tests/widgets/test_ttt_address_icons.py`` proves the icon exists and is
clickable, but it mounts each widget alone at ``size=(150, 40)`` where the
widget gets (almost) the whole terminal. In the real ``TTTScreen``,
``TTTFeesTable`` is ``width: 2fr`` against ``TTTActivityFeed``'s ``3fr`` in
``#bottom-row``, and ``TTTLeaderboard`` is ``width: 3fr`` against
``#right-col``'s ``2fr`` in ``#middle-row`` (``themes/minimal.tcss``), so each
table gets only a fraction of the terminal -- exactly the gap the review
finding named.

This file composes the **real** ``TTTScreen`` (a fake, no-network manager, on
``tests/screens/test_talismans_screen.py``'s precedent) and reads
``DataTable.show_horizontal_scrollbar`` -- the same signal the terminal-layout
skill's family of tests treats as authoritative for "did a column budget
overflow its region" -- rather than hand-deriving a "needed columns" number.
That distinction mattered here: a hand computation (sum of declared column
widths) undercounts by ``2 * cell_padding`` per column (Textual's own
``DataTable.get_render_width``, default ``cell_padding = 1``), which is
exactly the gap between the review finding's "52 needed" and this file's
measured 56/57 -- five columns cost ten cells of padding nobody's arithmetic
had accounted for.

**What the sweep found, and why ``_SYM_WIDTH`` is 5, not 8 or 11.**
``TTTFeesTable`` -- the binding table, ``2fr`` against the row's ``3fr`` --
already needed 57 columns against its 56-column region at the pin **before
this branch ever added an icon**: a plain ``width=8`` SYM column, no icon,
was already one column over (measured by temporarily restoring
``ttt_fees_table.py``/``ttt_leaderboard.py`` to their pre-task-7 commit,
``5a84a2b~1``, and running this same probe against it -- the exact numbers
are in ``task-7-report.md``'s fix-round section). Growing the column by
``ICON_COLS`` alone (8 -> 10) made that worse, not better; sizing it for
``address_text``'s own address-fallback floor, ``MIN_SHORT_COLS`` (11 -> 13
after ``+ICON_COLS``, this file's first icon pass) made it three columns
over. ``_SYM_WIDTH = 5`` is the largest label width that clears both the
icon's own two columns and the table's pre-existing one-column deficit at
the pin, made possible by removing the address-fallback path (a missing
symbol now renders the placeholder ``"--"`` rather than the bare address --
see ``ttt_fees_table.py`` / ``ttt_leaderboard.py``'s ``_safe_symbol``
docstrings) so this column never has to cover ``MIN_SHORT_COLS`` at all.
``TTTLeaderboard`` was never close to its own limit (83-column region, needs
68) and is kept at the same width purely so two sibling tables on one screen
truncate symbols the same way.

**Both directions, on the sweep's own numbers rather than an invented
mutation.** 142 -- one column under the pin -- is where ``TTTFeesTable``
itself last shows a horizontal scrollbar with the values landing in this
file; 143 is where it stops. That boundary is asserted directly
(``test_the_fees_table_still_scrolls_one_column_under_the_pin``) rather than
only inferred from the sweep, because a sweep that happened to skip the exact
boundary width would prove nothing about it. The **other** direction --
widening ``_SYM_WIDTH`` back past what the pin can hold -- was proved by
mutation while fixing this (recorded in ``task-7-report.md``): reset
``_SYM_WIDTH`` to 6 (one more than this budget) in each widget file, rerun
``test_neither_ttt_table_scrolls_horizontally_at_the_documented_pin`` alone,
watch it fail, then restore. That mutation is not re-run automatically here
because it would require editing the widget module from inside the test
(shared-tree risk for no lasting benefit); the sweep and the boundary test
are the permanent regression lock, and the mutation evidence lives in the
fix-round report.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from textual.app import App
from textual.widgets import DataTable

import maxpane_dashboard
from maxpane_dashboard.screens.ttt import TTTScreen
from maxpane_dashboard.widgets.ttt import TTTFeesTable, TTTLeaderboard

#: Derived directly from the installed package rather than imported from
#: ``maxpane_dashboard.app``: that module's import graph currently reaches
#: ``screens.surf`` -> ``widgets.surf`` at class-definition time, and another
#: agent's in-progress edit there (a copy-icon pass across ``_fmt.py`` and its
#: callers) intermittently breaks that import while this branch is shared --
#: observed directly while writing this file. This file has no reason to
#: depend on any dashboard but TTT's own for a stylesheet path it can compute
#: itself; ``maxpane_dashboard.app`` states the identical path
#: (``Path(__file__).parent / "themes" / "minimal.tcss"``) one directory up.
_CSS_PATH = Path(maxpane_dashboard.__file__).parent / "themes" / "minimal.tcss"

#: Restated from ``__main__.FULL_LAYOUT_COLUMNS`` for the same reason: this
#: file's only dependency on the app-wide pin is its value, and importing
#: ``__main__`` to read one integer is a heavier and less stable path than
#: typing the number CLAUDE.md already documents as the standing app-wide
#: pin. A future change to that pin is not this test's to catch -- it is
#: caught by the tests that own ``__main__.py`` -- so restating it here does
#: not create a second copy of a number anything else derives from.
FULL_LAYOUT_COLUMNS = 143


def _sample_data() -> dict:
    """One representative TTT payload: enough for every widget's
    ``update_data`` to run without raising, with real 40-hex addresses in the
    two SYM-bearing tables and the activity feed's burn actor."""
    now = int(time.time())
    return {
        "launches": 1234,
        "max_supply": 10_000,
        "unburned": 8_766,
        "burned_pct": 12.3,
        "launches_24h": 5,
        "holder_pool_eth_total": 12.5,
        "holder_pool_eth_24h": 0.5,
        "total_mcap_usd": 100_000.0,
        "total_mcap_eth": 40.0,
        "total_mcap_token_count": 1_234,
        "top_tokens_by_volume": [
            {
                "rank": i,
                "address": "0x" + f"{i:x}".rjust(40, "a"),
                # Row 1 has no symbol on purpose: the placeholder ("--")
                # branch of the SYM cell is exercised in this same sweep,
                # not just the common named-token case.
                "symbol": None if i == 1 else f"TOKEN{i}",
                "price_usd": 1.2345,
                "change_h24": 5.0,
                "vol_usd_h24": 123_456.0,
                "age_str": "2d",
                "mcap_usd": 987_654.0,
            }
            for i in range(1, 11)
        ],
        "burns_history": [],
        "volume_history": [],
        "fresh_launch_signal": None,
        "buybacks_ready_signal": None,
        "decay_window_signal": None,
        "concentration_signal": None,
        "activity_events": [
            {
                "event_type": "burn",
                "timestamp": now,
                "token_symbol": "TTT1",
                "actor_address": "0x" + "ab" * 20,
                "token_id": 42,
            },
        ],
        "top_fee_engines": [
            {
                "rank": i,
                "address": "0x" + f"{i:x}".rjust(40, "b"),
                "symbol": None if i == 1 else f"TOKEN{i}",
                "fees_24h_eth": 1.2345,
                "fees_lifetime_eth": 10.5,
                "fees_per_vol_pct": 3.2,
            }
            for i in range(1, 11)
        ],
        "claim_math_scenarios": [],
        "last_updated_seconds_ago": 0,
        "error_count": 0,
        "poll_interval": 30,
    }


class _FakeManager:
    """Stand-in for TTTManager that never touches the network."""

    def __init__(self) -> None:
        self.calls = 0

    async def fetch_and_compute(self) -> dict:
        self.calls += 1
        return _sample_data()

    async def close(self) -> None:
        pass


class _Harness(App):
    """Push a single TTTScreen for testing, with the real theme loaded.

    ``CSS_PATH`` is the part ``tests/widgets/test_ttt_address_icons.py``'s
    harness does not set -- without it none of ``themes/minimal.tcss``'s
    ``width: 2fr`` / ``3fr`` rules apply and every child in a ``Horizontal``
    falls back to an equal split, which is a different (and wrong) layout
    entirely. Confirmed by running this probe without ``CSS_PATH`` first:
    both tables came back at essentially half the terminal each, which
    matches neither this screen's actual proportions nor the review finding.
    """

    CSS_PATH = _CSS_PATH

    def __init__(self, screen: TTTScreen) -> None:
        super().__init__()
        self._screen = screen

    def on_mount(self) -> None:
        self.push_screen(self._screen)


async def _tables_at(width: int, height: int = 45) -> dict:
    """Compose the real ``TTTScreen`` at *size* and read both SYM tables.

    ``fees``/``lb`` here always mean the mounted ``DataTable`` inside
    ``TTTFeesTable`` / ``TTTLeaderboard`` -- the widget that actually owns
    ``show_horizontal_scrollbar``, not the panel around it.
    """
    manager = _FakeManager()
    screen = TTTScreen(manager, poll_interval=30, name="ttt")
    app = _Harness(screen)
    async with app.run_test(size=(width, height)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()
        await pilot.pause()
        fees = screen.query_one(TTTFeesTable).query_one(DataTable)
        lb = screen.query_one(TTTLeaderboard).query_one(DataTable)
        return {
            "fees_region": fees.region.width,
            "fees_virtual": fees.virtual_size.width,
            "fees_hscroll": fees.show_horizontal_scrollbar,
            "lb_region": lb.region.width,
            "lb_virtual": lb.virtual_size.width,
            "lb_hscroll": lb.show_horizontal_scrollbar,
        }


async def test_neither_ttt_table_scrolls_horizontally_at_the_documented_pin() -> None:
    """The requirement from the coordinator's ruling, asserted directly: at
    ``__main__.FULL_LAYOUT_COLUMNS`` (143), in the real screen composition,
    both SYM-bearing DataTables show their whole column set with no
    horizontal scrollbar.

    Measured at the pin: ``fees`` needs exactly 56 against a 56-column
    region (``_SYM_WIDTH = 5``, zero slack -- the largest label this table's
    real region can hold once the icon and the table's own pre-existing
    one-column deficit are both paid for); ``lb`` needs 68 against an
    83-column region (15 columns of slack, since ``TTTLeaderboard`` was
    never the binding table).
    """
    r = await _tables_at(FULL_LAYOUT_COLUMNS)
    assert r["fees_hscroll"] is False, (
        f"TTTFeesTable needs {r['fees_virtual']} columns but its region at "
        f"the {FULL_LAYOUT_COLUMNS}-column pin is only {r['fees_region']} -- "
        "shrink _SYM_WIDTH further, never raise the pin"
    )
    assert r["lb_hscroll"] is False, (
        f"TTTLeaderboard needs {r['lb_virtual']} columns but its region at "
        f"the pin is only {r['lb_region']}"
    )


async def test_the_fees_table_still_scrolls_one_column_under_the_pin() -> None:
    """Not vacuous: the same table, one column narrower than the pin, still
    shows its own horizontal scrollbar.

    This is the "other direction" the coordinator's ruling asked for, taken
    from the sweep's own numbers rather than a code mutation: at 142
    ``TTTFeesTable``'s region is 55 against its still-56-column need. If this
    ever goes green, the fix above gained a column of slack nobody spent on
    purpose -- worth knowing, but not itself a problem, so re-measure rather
    than "fixing" this test.
    """
    r = await _tables_at(FULL_LAYOUT_COLUMNS - 1)
    assert r["fees_hscroll"] is True, (
        f"TTTFeesTable does not scroll at {FULL_LAYOUT_COLUMNS - 1} columns "
        f"(region={r['fees_region']}, needs={r['fees_virtual']}) -- either "
        "this table gained slack that was not spent deliberately, or this "
        "probe stopped detecting overflow"
    )


@pytest.mark.parametrize("width", list(range(120, 151)))
async def test_no_ttt_table_scrolls_at_or_above_the_pin(width: int) -> None:
    """The sweep the coordinator's ruling asked for, run the whole
    120..150 band rather than only at the boundary: at and above the pin,
    neither table ever shows a horizontal scrollbar, for every width in the
    range -- not merely at 143 itself. Below the pin nothing is asserted:
    PRD §5 allows a narrower terminal to lose columns, and this branch does
    not own re-measuring every width below the app's own documented minimum.
    """
    r = await _tables_at(width)
    if width >= FULL_LAYOUT_COLUMNS:
        assert not r["fees_hscroll"] and not r["lb_hscroll"], (width, r)
