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
markup parse it no longer goes through.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Static
from maxpane_dashboard.widgets.address import ICON_COLS, MIN_SHORT_COLS, address_text

_DASH = "--"

#: Display budget for the SYM cell's symbol/address text, excluding
#: ICON_COLS. An up-to-8-char symbol alone would fit width=8, but this cell
#: now sometimes renders the bare address instead (no known symbol --
#: ``_safe_symbol`` returns ``None``), and ``address_text``'s own window
#: has a floor, ``MIN_SHORT_COLS``, below which it will not go: a rendered
#: check with width=8 on a no-symbol row still produced an 11-cell address,
#: overflowing an 8+ICON_COLS=10 column (caught on the composited strip,
#: not by inspection). Pinning this to ``MIN_SHORT_COLS`` covers both
#: branches -- the symbol case has room to spare, the bare-address case
#: fits exactly.
_SYM_WIDTH = MIN_SHORT_COLS


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


def _safe_symbol(sym) -> str | None:
    """Cleaned, truncated symbol, or ``None`` when there is nothing to show.

    ``None`` (rather than ``_DASH``) so ``address_text``'s own ``label or
    None`` fallback shows the real address instead of a placeholder dash
    when the token has a valid address but no known symbol -- the address
    is strictly more informative. No ``safe_markup`` here: the cleaned
    string is handed to ``address_text`` as a ``label``, which appends it
    as plain ``Text``, never through a markup parse (unlike the old
    ``f"[bold]{symbol}[/]"`` string this replaces).
    """
    if sym is None:
        return None
    try:
        cleaned = "".join(ch for ch in str(sym) if ch.isprintable())
    except Exception:
        return None
    cleaned = cleaned.strip()
    return cleaned[:8] if cleaned else None


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
