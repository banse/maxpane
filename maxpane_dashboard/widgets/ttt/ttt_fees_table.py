"""α-view (Top Fee Engines) DataTable for the TTT dashboard.

Renders the top 10 launched tokens ranked by 24h FeeSplitter deposits.
Each row carries:

* ``#``         -- rank
* ``SYM``       -- token symbol (cleaned + truncated)
* ``24h FEES``  -- 24h fee deposits in ETH
* ``LIFETIME``  -- lifetime fee deposits in ETH
* ``24h FEE/VOL`` -- 24h fees divided by 24h DEX volume (effective tax
  rate); reads ``"--"`` when volume is zero/None.

All cells handle ``None`` and malformed inputs by collapsing to ``"--"``.
This widget is a sibling of ``TTTClaimsTable`` -- the screen toggles
``display`` between them via the ``c`` keybinding (WP5).

``SYM`` is a name standing in for the row's ERC20 contract address (``row
["address"]``, always present -- ``TTTLaunchedToken.address`` is a
non-optional field): the symbol is shown, and its copy icon copies the
address, per PRD §1 ("a name shown in place of the address gets the
icon"). The cell is built with ``address_text``, never markup, so the
symbol (attacker-chosen ERC20 metadata) never has to be escaped for a
markup parse it no longer goes through. A missing symbol renders the
placeholder ``"--"`` (``_fmt.safe_symbol`` -> ``DASH``, unchanged from
before this file carried an icon) rather than the bare address: the icon still
copies the real address regardless of what label is shown, so nothing
about "every address gets a working copy icon" depends on which label
text address_text is given, and this way the column never has to size
itself for address_text's own MIN_SHORT_COLS floor (see the width note
below -- that floor does not fit this table's measured budget).
"""

from __future__ import annotations

from maxpane_dashboard.widgets.address import ICON_COLS, address_text
from maxpane_dashboard.widgets.fmt import DASH
from maxpane_dashboard.widgets.panels import TableLeaderboard
from maxpane_dashboard.widgets.ttt._chain import EXPLORER
from maxpane_dashboard.widgets.ttt._fmt import safe_symbol

#: Display budget for the SYM cell's label text, excluding ICON_COLS --
#: **measured against the real screen, not this widget in isolation.**
#: ``TTTFeesTable`` is ``width: 2fr`` against ``TTTActivityFeed``'s ``3fr``
#: in ``#bottom-row`` (themes/minimal.tcss), the tighter of TTT's two
#: address-bearing DataTables: at the app-wide pin,
#: ``__main__.FULL_LAYOUT_COLUMNS = 143``, this table's region is 56
#: columns, and the DataTable itself spends 2 cells of ``cell_padding``
#: (Textual's own default) on *every* one of its 5 columns -- 10 cells the
#: naive "sum the declared widths" arithmetic below missed the first time.
#:
#: Composed the real ``TTTScreen`` (a fake, no-network manager, per
#: ``tests/screens/test_talismans_screen.py``'s pattern) and read
#: ``DataTable.show_horizontal_scrollbar`` at 143, sweeping this constant:
#:
#:   label width -> SYM column -> table needs -> region 56 -> scrollbar
#:   3            5             54              margin 2    False
#:   4            6             55              margin 1    False
#:   5            7             56              margin 0    False  <- here
#:   6            8             57              over by 1   True
#:   7            9             58              over by 2   True
#:   8 (pre-icon) 10            59              over by 3   True
#:
#: **A width=8 SYM column (no icon at all) already needed 57 against this
#: same 56-column region -- one column over, with ``show_horizontal_scrollbar
#: == True`` at the app's own documented pin, before this file had ever
#: seen an icon.** That pre-existing 1-column deficit is why growing SYM by
#: exactly ICON_COLS (the naive "grow first" reading of recipe step 6.2,
#: 8 -> 10, tried first and reverted) does not clear it, and why the first
#: icon pass here (8 -> 11 + ICON_COLS, sized for ``address_text``'s
#: ``MIN_SHORT_COLS`` floor so a no-symbol row could fall back to showing
#: the bare address) made it three columns over instead of fixing it. **5**
#: is the largest label width that clears both the icon's own 2 columns and
#: the table's pre-existing 1-column deficit at once, with the address
#: fallback removed (see the module docstring) so this column never has to
#: cover ``MIN_SHORT_COLS`` in the first place. It spends every cell the
#: region has -- a wider label was tried and is the row marked "over by 1"
#: above at 6, i.e. the ICON_COLS-only grow this file started with. See
#: ``tests/screens/test_ttt_address_icon_layout.py`` for the swept,
#: both-directions proof.
_SYM_WIDTH = 5


# Not widgets/fmt.fmt_eth: ungrouped -- probe 1234.5678 renders "1234.5678 Ξ" here,
# "1,234.5678 Ξ" there; True renders "1.0000 Ξ" here, "--" there. Four decimal
# places, pinned by tests/widgets/test_ttt_address_icons.py:128.
def _fmt_eth(value, digits: int = 4) -> str:
    if value is None:
        return DASH
    try:
        return f"{float(value):.{digits}f} Ξ"
    except (TypeError, ValueError):
        return DASH


def _fmt_ratio_pct(value) -> str:
    """``value`` is already a percent (e.g. ``12.3`` -> ``12.3%``)."""
    if value is None:
        return DASH
    try:
        v = float(value)
    except (TypeError, ValueError):
        return DASH
    if v <= 0:
        return DASH
    return f"{v:.1f}%"


class TTTFeesTable(TableLeaderboard):
    """α view -- top 10 tokens by 24h fee deposits.

    The title, its blank row, the columns, the seed row and the
    clear-then-repopulate contract are
    :class:`~maxpane_dashboard.widgets.panels.TableLeaderboard`'s
    (Branch 7, WP-B). :data:`_SYM_WIDTH` and the address cell stay here:
    the base owns mechanics, never a measured column.
    """

    TITLE = "α TOP FEE ENGINES (24h)"

    TABLE_ID = "ttt-fees-table"

    COLUMNS = (
        ("#", 3),
        ("SYM", _SYM_WIDTH + ICON_COLS),
        ("24h FEES", 12),
        ("LIFETIME", 12),
        ("24h FEE/VOL", 12),
    )

    LOADING_ROW = (DASH, "Loading...", DASH, DASH, DASH)

    EMPTY_ROW = (DASH, "No data", DASH, DASH, DASH)

    #: Geometry only: the title and its blank row are ``PanelBase``'s.
    DEFAULT_CSS = """
    TTTFeesTable > DataTable {
        height: 1fr;
    }
    """

    def update_data(
        self,
        top_fee_engines=None,
        **_kwargs,
    ) -> None:
        """Refresh the table with up to 10 ranked fee-engine rows."""
        self.render_table(top_fee_engines)

    def build_row(self, index: int, row) -> tuple | None:
        """One fee engine's row. Rank 1 is bold; SYM carries the icon."""
        if not isinstance(row, dict):
            return None
        is_top = index == 0
        rank = row.get("rank", index + 1)
        sym_cell = address_text(
            row.get("address"),
            label=safe_symbol(row.get("symbol")),
            width=_SYM_WIDTH,
            style="bold" if is_top else "",
            explorer=EXPLORER,
        )
        fees_24h = _fmt_eth(row.get("fees_24h_eth"))
        fees_life = _fmt_eth(row.get("fees_lifetime_eth"))
        fees_per_vol = _fmt_ratio_pct(row.get("fees_per_vol_pct"))

        if is_top:
            rank_str = f"[bold]{rank}[/]"
            fees_24h = f"[bold]{fees_24h}[/]"
        else:
            rank_str = str(rank)

        return (rank_str, sym_cell, fees_24h, fees_life, fees_per_vol)
