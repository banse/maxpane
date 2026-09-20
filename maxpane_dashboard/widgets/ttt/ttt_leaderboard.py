"""Top tokens by volume leaderboard for the TTT dashboard.

Renders a ``DataTable`` of the top-10 launched ERC20 tokens, ranked by
24h DexScreener volume.  Format helpers are local to this file so the
widget has no dependency on game-specific analytics modules.

All format helpers tolerate ``None`` -- rendering ``"--"`` rather than
crashing -- because newly-launched tokens may not yet be indexed by
DexScreener and the manager forwards those gaps verbatim.

``SYM`` is a name standing in for the row's ERC20 contract address (``token
["address"]``, always present -- ``TTTLaunchedToken.address`` is a
non-optional field): the symbol is shown, and its copy icon copies the
address, per PRD §1 ("a name shown in place of the address gets the
icon"). The cell is built with ``address_text``, never markup, so the
symbol (attacker-chosen ERC20 metadata) never has to be escaped for a
markup parse it no longer goes through. A missing symbol renders the
placeholder ``"--"`` rather than the bare address (see ``_fmt.safe_symbol`` and
``ttt_fees_table.py``'s matching note) -- the icon copies the real address
regardless of the label shown, so this costs nothing the rule requires and
keeps this column off ``address_text``'s ``MIN_SHORT_COLS`` floor.
"""

from __future__ import annotations

from maxpane_dashboard.widgets.address import ICON_COLS, address_text
from maxpane_dashboard.widgets.fmt import DASH
from maxpane_dashboard.widgets.panels import TableLeaderboard
from maxpane_dashboard.widgets.ttt._chain import EXPLORER
from maxpane_dashboard.widgets.ttt._fmt import safe_symbol

_SUBSCRIPT = "₀₁₂₃₄₅₆₇₈₉"

#: Display budget for the SYM cell's label text, excluding ICON_COLS --
#: measured against the real screen, matching ``ttt_fees_table.py``'s
#: identical column. ``TTTLeaderboard`` is ``width: 3fr`` against
#: ``#right-col``'s ``2fr`` in ``#middle-row`` (themes/minimal.tcss), so it
#: is NOT the binding table -- at the app-wide pin,
#: ``__main__.FULL_LAYOUT_COLUMNS = 143``, this table's region is 83
#: columns and, at this same width=5 label, its DataTable needs 68
#: (``show_horizontal_scrollbar`` False, 15 columns of margin; even the
#: pre-icon width=8 label only needed 71, 12 columns of margin -- this
#: table was never in danger). Kept equal to ``ttt_fees_table.py``'s
#: binding-table value anyway: the two DataTables sit one above the other
#: on the same screen and a reader comparing symbols across them should
#: not see the same-length name truncate differently in one and not the
#: other. See ``tests/screens/test_ttt_address_icon_layout.py``.
_SYM_WIDTH = 5


# -- format helpers ----------------------------------------------------


def _format_price(p) -> str:
    """Render a USD price with DexScreener-style subscript-zero for sub-cent values.

    Examples:
        12.345     -> "$12.3450"
        0.0312     -> "$0.0312"
        0.000123   -> "$0.0₃123"   # 3 leading zeros after the decimal
        0.0000012  -> "$0.0₆12"
        2.7e-9     -> "$0.0₉27"    # 9 leading zeros
    """
    if p is None:
        return DASH
    try:
        v = float(p)
    except (TypeError, ValueError):
        return DASH
    if v <= 0:
        return DASH
    if v >= 0.01:
        return f"${v:.4f}"
    # Sub-cent: count leading zeros after the decimal point.
    # Build a fixed-precision string with lots of digits to find the zero run.
    s = f"{v:.18f}"            # "0.000001234567000000"
    # Drop "0." prefix
    frac = s.split(".", 1)[1]
    # Count leading zeros in frac
    zeros = 0
    for ch in frac:
        if ch == "0":
            zeros += 1
        else:
            break
    # Take the next 3 significant digits after the zero run
    sig = frac[zeros:zeros + 3].rstrip("0") or "0"
    # If zeros < 4 we don't need subscript; just render plainly.
    if zeros < 4:
        return f"${v:.6f}".rstrip("0").rstrip(".")
    subscript = "".join(_SUBSCRIPT[int(d)] for d in str(zeros))
    return f"$0.0{subscript}{sig}"


def _fmt_price(p) -> str:
    """Backwards-compatible alias for :func:`_format_price`."""
    return _format_price(p)


def _fmt_change(c) -> str:
    if c is None:
        return DASH
    try:
        v = float(c)
    except (TypeError, ValueError):
        return DASH
    if v > 0:
        return f"[green]+{v:.1f}%[/]"
    if v < 0:
        return f"[red]{v:.1f}%[/]"
    return f"[dim]{v:.1f}%[/]"


def _fmt_humanized_usd(value) -> str:
    if value is None:
        return DASH
    try:
        v = float(value)
    except (TypeError, ValueError):
        return DASH
    if v < 0:
        return DASH
    if v >= 1_000_000:
        return f"${v / 1e6:.2f}M"
    if v >= 1_000:
        return f"${v / 1e3:.1f}K"
    return f"${v:.0f}"


def _fmt_age(age_str) -> str:
    """Age comes pre-rendered from the manager; render as-is or dash."""
    if not age_str:
        return DASH
    return str(age_str)


# -- widget ------------------------------------------------------------


class TTTLeaderboard(TableLeaderboard):
    """DataTable leaderboard showing top-10 TTT tokens by 24h volume.

    The title, its blank row, the columns, the seed row and the
    clear-then-repopulate contract are
    :class:`~maxpane_dashboard.widgets.panels.TableLeaderboard`'s
    (Branch 7, WP-B). :data:`_SYM_WIDTH`, the address cell, the
    subscript-zero price and the rank-1 bolding stay here.
    """

    TITLE = "TOP TOKENS BY VOLUME"

    TABLE_ID = "ttt-leaderboard-table"

    COLUMNS = (
        ("#", 3),
        ("SYM", _SYM_WIDTH + ICON_COLS),
        ("PRICE", 10),
        ("24h%", 8),
        ("VOL", 10),
        ("AGE", 6),
        ("MCAP", 10),
    )

    LOADING_ROW = (DASH, "Loading...", DASH, DASH, DASH, DASH, DASH)

    EMPTY_ROW = (DASH, "No data", DASH, DASH, DASH, DASH, DASH)

    #: Geometry only: the title and its blank row are ``PanelBase``'s.
    DEFAULT_CSS = """
    TTTLeaderboard > DataTable {
        height: 1fr;
    }
    """

    def update_data(
        self,
        top_tokens_by_volume=None,
        **_kwargs,
    ) -> None:
        """Refresh the leaderboard with up to 10 ranked tokens."""
        self.render_table(top_tokens_by_volume)

    def build_row(self, index: int, token) -> tuple | None:
        """One token's row. Rank 1 is bold; SYM carries the icon."""
        if not isinstance(token, dict):
            return None
        is_top = index == 0
        rank = token.get("rank", index + 1)
        sym_cell = address_text(
            token.get("address"),
            label=safe_symbol(token.get("symbol")),
            width=_SYM_WIDTH,
            style="bold" if is_top else "",
            explorer=EXPLORER,
        )
        price = _fmt_price(token.get("price_usd"))
        change = _fmt_change(token.get("change_h24"))
        volume = _fmt_humanized_usd(token.get("vol_usd_h24"))
        age = _fmt_age(token.get("age_str"))
        mcap = _fmt_humanized_usd(token.get("mcap_usd"))

        # Bold row 1
        if is_top:
            rank_str = f"[bold]{rank}[/]"
            price = f"[bold]{price}[/]"
        else:
            rank_str = str(rank)

        return (rank_str, sym_cell, price, change, volume, age, mcap)
