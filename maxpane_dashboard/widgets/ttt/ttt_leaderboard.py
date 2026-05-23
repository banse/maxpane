"""Top tokens by volume leaderboard for the TTT dashboard.

Renders a ``DataTable`` of the top-10 launched ERC20 tokens, ranked by
24h DexScreener volume.  Format helpers are local to this file so the
widget has no dependency on game-specific analytics modules.

All format helpers tolerate ``None`` -- rendering ``"--"`` rather than
crashing -- because newly-launched tokens may not yet be indexed by
DexScreener and the manager forwards those gaps verbatim.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Static

_DASH = "--"
_SUBSCRIPT = "₀₁₂₃₄₅₆₇₈₉"


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
        return _DASH
    try:
        v = float(p)
    except (TypeError, ValueError):
        return _DASH
    if v <= 0:
        return _DASH
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
        return _DASH
    try:
        v = float(c)
    except (TypeError, ValueError):
        return _DASH
    if v > 0:
        return f"[green]+{v:.1f}%[/]"
    if v < 0:
        return f"[red]{v:.1f}%[/]"
    return f"[dim]{v:.1f}%[/]"


def _fmt_humanized_usd(value) -> str:
    if value is None:
        return _DASH
    try:
        v = float(value)
    except (TypeError, ValueError):
        return _DASH
    if v < 0:
        return _DASH
    if v >= 1_000_000:
        return f"${v / 1e6:.2f}M"
    if v >= 1_000:
        return f"${v / 1e3:.1f}K"
    return f"${v:.0f}"


def _fmt_age(age_str) -> str:
    """Age comes pre-rendered from the manager; render as-is or dash."""
    if not age_str:
        return _DASH
    return str(age_str)


def _safe_symbol(sym) -> str:
    """Strip non-printable chars from symbol; truncate to 8 chars."""
    if sym is None:
        return _DASH
    try:
        cleaned = "".join(ch for ch in str(sym) if ch.isprintable())
    except Exception:
        return _DASH
    cleaned = cleaned.strip()
    if not cleaned:
        return _DASH
    return cleaned[:8]


# -- widget ------------------------------------------------------------


class TTTLeaderboard(Vertical):
    """DataTable leaderboard showing top-10 TTT tokens by 24h volume."""

    DEFAULT_CSS = """
    TTTLeaderboard > Static {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    TTTLeaderboard > DataTable {
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("TOP TOKENS BY VOLUME", classes="ttt-leaderboard-title")
        yield Static(" ", classes="ttt-leaderboard-spacer")
        table = DataTable(id="ttt-leaderboard-table", classes="ttt-leaderboard-table")
        yield table

    def on_mount(self) -> None:
        table = self.query_one("#ttt-leaderboard-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_column("#", width=3)
        table.add_column("SYM", width=8)
        table.add_column("PRICE", width=10)
        table.add_column("24h%", width=8)
        table.add_column("VOL", width=10)
        table.add_column("AGE", width=6)
        table.add_column("MCAP", width=10)
        table.add_row(_DASH, "Loading...", _DASH, _DASH, _DASH, _DASH, _DASH)

    def update_data(
        self,
        top_tokens_by_volume=None,
        **_kwargs,
    ) -> None:
        """Refresh the leaderboard with up to 10 ranked tokens."""
        table = self.query_one("#ttt-leaderboard-table", DataTable)
        table.clear()

        tokens = top_tokens_by_volume or []
        if not tokens:
            table.add_row(_DASH, "No data", _DASH, _DASH, _DASH, _DASH, _DASH)
            return

        for idx, token in enumerate(tokens[:10], start=1):
            if not isinstance(token, dict):
                continue
            rank = token.get("rank", idx)
            symbol = _safe_symbol(token.get("symbol"))
            price = _fmt_price(token.get("price_usd"))
            change = _fmt_change(token.get("change_h24"))
            volume = _fmt_humanized_usd(token.get("vol_usd_h24"))
            age = _fmt_age(token.get("age_str"))
            mcap = _fmt_humanized_usd(token.get("mcap_usd"))

            # Bold row 1
            if idx == 1:
                rank_str = f"[bold]{rank}[/]"
                symbol = f"[bold]{symbol}[/]"
                price = f"[bold]{price}[/]"
            else:
                rank_str = str(rank)

            table.add_row(rank_str, symbol, price, change, volume, age, mcap)
