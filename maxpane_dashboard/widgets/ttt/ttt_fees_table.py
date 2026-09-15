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
placeholder ``"--"`` (``_safe_symbol`` -> ``_DASH``, unchanged from before
this file carried an icon) rather than the bare address: the icon still
copies the real address regardless of what label is shown, so nothing
about "every address gets a working copy icon" depends on which label
text address_text is given, and this way the column never has to size
itself for address_text's own MIN_SHORT_COLS floor (see the width note
below -- that floor does not fit this table's measured budget).
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Static
from maxpane_dashboard.widgets.address import ICON_COLS, address_text

_DASH = "--"

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


def _fmt_eth(value, digits: int = 4) -> str:
    if value is None:
        return _DASH
    try:
        return f"{float(value):.{digits}f} Ξ"
    except (TypeError, ValueError):
        return _DASH


def _fmt_ratio_pct(value) -> str:
    """``value`` is already a percent (e.g. ``12.3`` -> ``12.3%``)."""
    if value is None:
        return _DASH
    try:
        v = float(value)
    except (TypeError, ValueError):
        return _DASH
    if v <= 0:
        return _DASH
    return f"{v:.1f}%"


def _safe_symbol(sym) -> str:
    """Cleaned, truncated symbol, or ``_DASH`` when there is nothing to show.

    **``_DASH``, not ``None``** -- reverted from a ``None``-means-"fall back
    to the bare address" design (round 1 of this file's icon conversion)
    after an in-situ screen sweep found that fallback needs
    ``address_text``'s ``MIN_SHORT_COLS`` floor (11 cells), which this
    table's real, CSS-constrained region cannot afford at the app's own
    143-column pin (see ``_SYM_WIDTH``'s ``#:`` block). The icon copies the
    real address regardless of which label ``address_text`` is given, so a
    placeholder label costs nothing the rule (PRD §1: every displayed
    address carries a working copy icon) actually requires -- it is the
    same "name stands in for the address" shape as a known symbol, just
    with ``"unknown"`` as the name instead of the token's. No
    ``safe_markup`` here: the cleaned string is handed to ``address_text``
    as a ``label``, which appends it as plain ``Text``, never through a
    markup parse (unlike the old ``f"[bold]{symbol}[/]"`` string this
    replaces).
    """
    if sym is None:
        return _DASH
    try:
        cleaned = "".join(ch for ch in str(sym) if ch.isprintable())
    except Exception:
        return _DASH
    cleaned = cleaned.strip()
    return cleaned[:8] if cleaned else _DASH


class TTTFeesTable(Vertical):
    """α view -- top 10 tokens by 24h fee deposits."""

    DEFAULT_CSS = """
    TTTFeesTable > Static {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    TTTFeesTable > DataTable {
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("α TOP FEE ENGINES (24h)", classes="ttt-fees-title")
        yield Static(" ", classes="ttt-fees-spacer")
        table = DataTable(id="ttt-fees-table", classes="ttt-fees-table")
        yield table

    def on_mount(self) -> None:
        table = self.query_one("#ttt-fees-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_column("#", width=3)
        table.add_column("SYM", width=_SYM_WIDTH + ICON_COLS)
        table.add_column("24h FEES", width=12)
        table.add_column("LIFETIME", width=12)
        table.add_column("24h FEE/VOL", width=12)
        table.add_row(_DASH, "Loading...", _DASH, _DASH, _DASH)

    def update_data(
        self,
        top_fee_engines=None,
        **_kwargs,
    ) -> None:
        """Refresh the table with up to 10 ranked fee-engine rows."""
        table = self.query_one("#ttt-fees-table", DataTable)
        table.clear()

        engines = top_fee_engines or []
        if not engines:
            table.add_row(_DASH, "No data", _DASH, _DASH, _DASH)
            return

        for idx, row in enumerate(engines[:10], start=1):
            if not isinstance(row, dict):
                continue
            rank = row.get("rank", idx)
            symbol = _safe_symbol(row.get("symbol"))
            sym_cell = address_text(
                row.get("address"),
                label=symbol,
                width=_SYM_WIDTH,
                style="bold" if idx == 1 else "",
            )
            fees_24h = _fmt_eth(row.get("fees_24h_eth"))
            fees_life = _fmt_eth(row.get("fees_lifetime_eth"))
            fees_per_vol = _fmt_ratio_pct(row.get("fees_per_vol_pct"))

            if idx == 1:
                rank_str = f"[bold]{rank}[/]"
                fees_24h = f"[bold]{fees_24h}[/]"
            else:
                rank_str = str(rank)

            table.add_row(rank_str, sym_cell, fees_24h, fees_life, fees_per_vol)
