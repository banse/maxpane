"""Top of THE LIST — the ten highest scores (PRD §4, middle left).

One row per contributor: rank, truncated address, curve points, credited
ETH (the **high-water mark**, not the gross routed), the ladder's tx count,
and a ``⚑`` when the wallet belongs to a fan-out cluster.

Three rendering rules this dashboard makes load-bearing:

* **``None`` and ``[]`` are different facts and read differently.**  A
  ``None`` list means the fold could not be built — ``leaderboard
  unavailable``.  An empty list means the fold ran and the game has no
  contributors yet — ``no contributors yet``.  Rendering "no contributors"
  over a dead log endpoint would report an empty game.
* **Credit is not volume.**  ``credit_eth`` is the address's credited
  high-water mark; the gross it routed is larger for anyone who escalated,
  and every wei of both was refunded in-transaction.  The column is headed
  ``CREDIT`` and never ``ETH``, ``VALUE`` or anything that reads as held.
* **The flag has four states and four glyphs.**  ``link_conf`` grades it —
  ``"high"`` is ``⚑``, ``"low"`` is ``◌``, ``"clean"`` is an empty cell (a
  real negative) — and where there is no grade the shipped Tier-A bool still
  answers: ``True`` is ``⚑``, ``False`` empty, ``None`` is ``?``, the fold
  did not run, which is not the same as "clean".  ``?`` therefore means
  *neither* fold could judge the row, never "the new one has not run yet";
  see :func:`_link_glyph` for why that fallback is the ruled behaviour and
  not an oversight.

The wallet's own row is emphasised when ``you_address`` matches, compared
**case-insensitively**: addresses reach this dashboard checksummed from
``eth_call`` decodes and lowercase from log topics, and a case-sensitive
match would silently never fire for half the payloads.  The emphasis is a
``▸`` glyph plus bold, never colour alone.

Width behaviour
---------------

=========  ====  =========================================
Tier       Cost  Columns
=========  ====  =========================================
full        48   # WALLET POINTS CREDIT TX ⚑
compact     42   # WALLET POINTS CREDIT ⚑
minimal     32   # WALLET POINTS ⚑
=========  ====  =========================================

``TX`` goes first: the ladder length is the least load-bearing number on the
row.  ``CREDIT`` goes second.  ``POINTS`` and the flag never go — points are
what the board ranks by, and the flag is the one column a reader cannot
reconstruct from anything else on screen.  Each drop is announced in the
title (``‹ widen: TX``); nothing is ever clipped in silence.

Primitives only — this module imports nothing from ``data/`` or ``analytics/``.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Static

from maxpane_dashboard.widgets.curator._fmt import (
    ADDR_COLS,
    DASH,
    fmt_eth_compact,
    fmt_points,
    short_addr,
    NAME_COLS,
    short_label,
)
from maxpane_dashboard.widgets.curator._table import (
    WIDEN_HINT,
    cells,
    install_columns,
    pick_tier,
    title_with_hint,
)
from maxpane_dashboard.widgets.markup_safety import safe_markup

#: Panel title.  A hint is appended to it, never substituted for it, so the
#: screen tests' ``"TOP OF THE LIST" in text`` holds at every width.
LEADERBOARD_TITLE = "TOP OF THE LIST"

#: The two explicit states, tested verbatim and deliberately different.
LEADERBOARD_UNAVAILABLE = "leaderboard unavailable"
LEADERBOARD_EMPTY = "no contributors yet"

#: Rows rendered.  The board is "top 10 by points" (PRD §4); a longer list
#: would not fit the slot and the tail is not what this panel is for.
MAX_ROWS = 10

#: The rank cell carries the ``▸`` you-marker, so it is one column wider than
#: three digits of rank.
_RANK_COLS = 4

#: ``44,721`` is the highest score this curve can produce (weight is capped
#: at ``creditCap`` and ``points = isqrt(weight) * 1000 // 1e9``), so six
#: columns of digits and one of slack.
_POINTS_COLS = 7

#: ``461.10`` / ``8.4K`` — ``fmt_eth_compact``'s measured worst case is six.
_CREDIT_COLS = 8

_TX_COLS = 4
_FLAG_COLS = 2

_TIERS = (
    (
        "full",
        49,
        (
            ("rank", "#", _RANK_COLS),
            ("wallet", "WALLET", NAME_COLS),
            ("points", "POINTS", _POINTS_COLS),
            ("credit", "CREDIT", _CREDIT_COLS),
            ("tx", "TX", _TX_COLS),
            ("flag", "⚑", _FLAG_COLS),
        ),
        "",
    ),
    (
        "compact",
        43,
        (
            ("rank", "#", _RANK_COLS),
            ("wallet", "WALLET", NAME_COLS),
            ("points", "POINTS", _POINTS_COLS),
            ("credit", "CREDIT", _CREDIT_COLS),
            ("flag", "⚑", _FLAG_COLS),
        ),
        "‹ widen: TX",
    ),
    (
        "minimal",
        33,
        (
            ("rank", "#", _RANK_COLS),
            ("wallet", "WALLET", NAME_COLS),
            ("points", "POINTS", _POINTS_COLS),
            ("flag", "⚑", _FLAG_COLS),
        ),
        "‹ widen: TX + CREDIT",
    ),
)


def _same_wallet(address, you_address) -> bool:
    """Case-insensitive address equality; ``None`` on either side is False."""
    if not address or not you_address:
        return False
    return str(address).strip().lower() == str(you_address).strip().lower()


#: The four glyphs the flag column can show, as plain text.  Four, and
#: **distinct in greyscale**: colour is never the sole carrier on this
#: dashboard, and a reader who cannot tell "linked, high confidence" from
#: "not analyzed" is reading the column backwards half the time.
#:
#: They are constants rather than literals in a dict so the suite can name
#: them, and so the empty cell is a *decision* with a name rather than a
#: stray ``""`` — it is the one glyph that says "we looked and found
#: nothing", and it is one keystroke from meaning "we did not look".
LINK_HIGH = "⚑"
LINK_LOW = "◌"
LINK_CLEAN = ""
LINK_UNKNOWN = "?"

#: ``link_conf`` -> markup.  Only the three spellings the contract freezes;
#: everything else (``None`` included) goes to the Tier-A fallback below.
_LINK_GLYPH = {
    "high": f"[yellow]{LINK_HIGH}[/]",
    "low": f"[dim]{LINK_LOW}[/]",
    "clean": LINK_CLEAN,
}


def _flag_cell(flagged) -> str:
    """``⚑`` / empty / ``?`` — flagged, clean, and "the fold did not run".

    Tier A's answer, and still the whole answer wherever the linkage sweep
    has not produced one: see :func:`_link_glyph`.
    """
    if flagged is None:
        return f"[dim]{LINK_UNKNOWN}[/]"
    return f"[yellow]{LINK_HIGH}[/]" if flagged else LINK_CLEAN


def _link_glyph(link_conf, flagged) -> str:
    """The graded marker: ``link_conf`` where there is one, the bool where
    there is not.

    ``link_conf`` is **additive** (``CURATOR_ROW_KEYS`` documents why: the
    bool is produced by a module that must stay byte-identical to what
    shipped), so the two answers coexist on every row and this function is
    where they are reconciled.  The ruling that shapes it:

    * a grade the widget can read **wins**, including ``"low"`` over a
      Tier-A ``True`` — the stronger fold's ``◌`` is a more precise
      statement than the weaker fold's ``⚑``, and showing both would put two
      marks on one wallet;
    * ``None`` — which is *every* row until the sweep first runs — falls
      back to :func:`_flag_cell`.  Rendering ``?`` there instead would take
      a flag off the board that the ``c`` view's cluster table is still
      showing, and two panels contradicting each other about the same wallet
      is worse than either answer alone.  ``?`` is still what a row reads
      when **neither** fold could judge it, which is the honest case it is
      for;
    * a spelling this widget does not know is handed to the same fallback:
      it is not evidence of anything, and the one cell it must never land in
      is the empty one, which means *clean*.

    The grade itself is never rendered — only mapped — so no producer string
    reaches markup from here.
    """
    # `isinstance` first: an unhashable payload (a list, a dict) raises on a
    # dict lookup, and a malformed grade must cost the *grade*, not the row.
    if isinstance(link_conf, str) and link_conf in _LINK_GLYPH:
        return _LINK_GLYPH[link_conf]
    return _flag_cell(flagged)


def _row_values(row: dict, index: int, you: bool) -> dict:
    """One leaderboard row's cells.  Every step degrades on its own.

    A rank that will not parse costs the rank cell, not the row: the address
    and the score are the reason the row exists.
    """
    rank = row.get("rank")
    try:
        rank_str = str(int(rank))
    except (TypeError, ValueError):
        rank_str = str(index)
    if you:
        # A glyph AND weight, never colour alone.
        rank_str = f"▸{rank_str}"

    wallet = safe_markup(short_label(row.get("name"), row.get("address")))
    points = fmt_points(row.get("points"))
    credit = fmt_eth_compact(row.get("credit_eth"))
    tx_count = row.get("tx_count")
    try:
        tx_str = f"{int(tx_count)}"
    except (TypeError, ValueError):
        tx_str = DASH

    values = {
        "rank": rank_str,
        "wallet": wallet,
        "points": points,
        "credit": credit,
        "tx": tx_str,
        "flag": _link_glyph(row.get("link_conf"), row.get("flagged")),
    }
    if you:
        for key in ("rank", "wallet", "points", "credit", "tx"):
            values[key] = f"[bold]{values[key]}[/]"
    return values


class CuratorLeaderboard(Vertical):
    """The top ten by curve points, with cluster flags and announced tiers."""

    DEFAULT_CSS = """
    CuratorLeaderboard > .curator-leaderboard-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    CuratorLeaderboard > .curator-leaderboard-note {
        width: 100%;
        height: 1;
        padding: 0 1;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    CuratorLeaderboard > DataTable {
        height: 1fr;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._payload: dict = {}
        self._columns: tuple = ()
        self._hint: str = ""

    def compose(self) -> ComposeResult:
        yield Static(
            LEADERBOARD_TITLE,
            classes="curator-leaderboard-title",
            id="curator-lb-title",
        )
        # The note line doubles as the spacer: an explicit state needs the
        # panel's whole width, and a DataTable cell is 11 columns wide -- the
        # first draft put "leaderboard unavailable" in the WALLET cell, where
        # the reader saw "leaderboar".  Same row budget, honest copy.
        yield Static("", classes="curator-leaderboard-note", id="curator-lb-note")
        yield DataTable(id="curator-lb-table", classes="curator-leaderboard-table")

    def on_mount(self) -> None:
        table = self.query_one("#curator-lb-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        columns = self._apply_columns(table)
        table.add_row(*cells({"wallet": "[dim]Loading...[/]"}, columns))

    def on_resize(self, _event=None) -> None:
        """Re-render: the column set is a function of the width."""
        if self._payload:
            self._render_view()

    # -- layout ----------------------------------------------------------

    def _apply_columns(self, table: DataTable) -> tuple:
        width = table.content_size.width or self.content_size.width
        _name, columns, hint = pick_tier(_TIERS, width)
        install_columns(table, columns, self._columns)
        self._columns = columns
        self._hint = hint
        return columns

    def _set_note(self, text: str) -> None:
        """The explicit-state line, prefixed with the widen marker when the
        title bar was too narrow to carry it (:func:`title_with_hint`)."""
        if not getattr(self, "_hint_placed", True):
            marker = f"[yellow]{WIDEN_HINT}[/]"
            text = f"{marker} {text}" if text else marker
        self.query_one("#curator-lb-note", Static).update(text)

    def _set_title(self) -> None:
        """Title plus the widen marker; the note carries it when it does not fit."""
        width = max(self.content_size.width - 2, 0)
        text, placed = title_with_hint(LEADERBOARD_TITLE, self._hint, width)
        self.query_one("#curator-lb-title", Static).update(text)
        self._hint_placed = placed or not self._hint

    # -- rendering ---------------------------------------------------------

    def update_data(self, leaderboard_rows=None, you_address=None, **_kwargs) -> None:
        """Refresh the board.

        ``you_address`` is the one kwarg here that is **not** a manager key:
        the screen passes ``MAXPANE_WALLET`` straight through so the reader's
        own row can be emphasised.  ``leaderboard_rows=None`` means the fold
        failed; ``[]`` means it ran and found nobody.
        """
        self._payload = {
            "rows": leaderboard_rows,
            "you": you_address,
            "seen": True,
        }
        self._render_view()

    def _render_view(self) -> None:
        try:
            table = self.query_one("#curator-lb-table", DataTable)
        except Exception:  # not composed yet
            return
        if not self._payload:
            return

        columns = self._apply_columns(table)
        self._set_title()

        rows = self._payload["rows"]
        if rows is None:
            self._set_note(f"[$warning]⚠ {LEADERBOARD_UNAVAILABLE}[/]")
            table.add_row(*cells({}, columns, default=DASH))
            return

        try:
            usable = [r for r in list(rows) if isinstance(r, dict)][:MAX_ROWS]
        except TypeError:
            usable = []

        if not usable:
            self._set_note(f"[dim]{LEADERBOARD_EMPTY}[/]")
            table.add_row(*cells({}, columns, default=DASH))
            return

        self._set_note("")

        you_address = self._payload.get("you")
        for index, row in enumerate(usable, start=1):
            try:
                values = _row_values(
                    row, index, _same_wallet(row.get("address"), you_address)
                )
            except Exception:
                # One malformed row costs its own row, never the panel.
                values = {"wallet": f"[dim]{DASH}[/]"}
            table.add_row(*cells(values, columns, default=DASH))
