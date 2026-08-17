"""The `y` view's three panels — the reader's own standing on THE LIST.

The dashboard answers "is the list still alive"; this view answers "where do I
stand on it, and what does the next rung cost".  Nothing here fetches: every
number is folded from the six wallet views the fast tier already reads and the
`Deposited` history the log sweep already holds.

Three honesty rules run through all of it, and each one is a claim the panel
must NOT make:

* **A stranger is not a wallet scoring zero.**  A wallet that never deposited
  has no rank and no points; `rank --, 0 pts` would be a statement about
  somebody.  It gets the entry ticket instead — the one number it can act on.
* **A capped send credited nothing, and that is a fact about the cap.**  Above
  `creditCap` a deposit still counts in full toward its hour's survival while
  adding no weight, so the ladder marks it rather than printing a bare `0`
  that reads as a failed decode.
* **A share is one key's share, never a person's.**  The sqrt curve pays more
  for the same ETH split across wallets, which is why the fan-out patterns
  panel exists; `2.9% of all weight` is true of an address and says nothing
  about who holds it.

Width: the ladder is a `DataTable` on the shared `_table` tiers; the two facts
panels are label/value lines that shed their *value tails* — never their labels
— and hand the marker to the title, the same contract the rail keeps.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Static

from maxpane_dashboard.widgets.curator._fmt import (
    DASH,
    as_float,
    fmt_eth,
    fmt_pct,
    fmt_points,
)
from maxpane_dashboard.widgets.curator._table import (
    WIDEN_HINT,
    cells,
    install_columns,
    pick_tier,
    tier_cost,
    title_with_hint,
)
from maxpane_dashboard.widgets.markup_safety import safe_markup

__all__ = [
    "LADDER_TITLE",
    "STANDING_TITLE",
    "NEXT_TITLE",
    "TARGET_TITLE",
    "NO_LADDER",
    "NOT_ON_THE_LIST",
    "LADDER_UNAVAILABLE",
    "CAPPED_MARK",
    "AT_THE_CAP",
    "TOP_OF_THE_LIST",
    "CuratorWalletLadder",
    "CuratorWalletStanding",
    "CuratorWalletNext",
    "CuratorWalletTarget",
]

LADDER_TITLE = "YOUR LADDER"
STANDING_TITLE = "YOUR STANDING"
NEXT_TITLE = "YOUR NEXT MOVE"
TARGET_TITLE = "WHERE IT GETS YOU"

#: Explicit states, tested verbatim.  Each is a different sentence because each
#: is a different fact: nothing sent, nothing readable, nothing above you.
NO_LADDER = "no sends from this wallet yet"
NOT_ON_THE_LIST = "not on the list yet"
LADDER_UNAVAILABLE = "ladder unavailable"
TOP_OF_THE_LIST = "nobody above you"
#: The minimum legal send buys points but not the place above.
HOLDS_RANK = "not enough to move up"
TAKES_RANK = "enough to move up"
AT_THE_CAP = "at the credit cap — no send buys weight"
#: Marks a deposit that credited nothing because it was above the cap.
CAPPED_MARK = "capped"

MAX_LADDER_ROWS = 12

_HOUR_COLS = 5
_AMOUNT_COLS = 10
_CREDIT_COLS = 10
_WEIGHT_COLS = 10
_EARLY_COLS = 6

_LADDER_TIERS = (
    (
        "full",
        tier_cost(
            (
                ("hour", "HOUR", _HOUR_COLS),
                ("amount", "SENT", _AMOUNT_COLS),
                ("credited", "CREDITED", _CREDIT_COLS),
                ("weight", "WEIGHT", _WEIGHT_COLS),
                ("early", "MULT", _EARLY_COLS),
            )
        ),
        (
            ("hour", "HOUR", _HOUR_COLS),
            ("amount", "SENT", _AMOUNT_COLS),
            ("credited", "CREDITED", _CREDIT_COLS),
            ("weight", "WEIGHT", _WEIGHT_COLS),
            ("early", "MULT", _EARLY_COLS),
        ),
        "",
    ),
    (
        "no-weight",
        tier_cost(
            (
                ("hour", "HOUR", _HOUR_COLS),
                ("amount", "SENT", _AMOUNT_COLS),
                ("credited", "CREDITED", _CREDIT_COLS),
                ("early", "MULT", _EARLY_COLS),
            )
        ),
        (
            ("hour", "HOUR", _HOUR_COLS),
            ("amount", "SENT", _AMOUNT_COLS),
            ("credited", "CREDITED", _CREDIT_COLS),
            ("early", "MULT", _EARLY_COLS),
        ),
        "‹ widen for weight",
    ),
    (
        "sent-only",
        tier_cost(
            (
                ("hour", "HOUR", _HOUR_COLS),
                ("amount", "SENT", _AMOUNT_COLS),
                ("early", "MULT", _EARLY_COLS),
            )
        ),
        (
            ("hour", "HOUR", _HOUR_COLS),
            ("amount", "SENT", _AMOUNT_COLS),
            ("early", "MULT", _EARLY_COLS),
        ),
        "‹ widen for credit",
    ),
)


def _early_x(value) -> str:
    """``1.94×`` — the multiplier that send actually got, not today's."""
    number = as_float(value)
    return DASH if number is None else f"{number:.2f}×"


def _ladder_values(row: dict) -> dict:
    """One ladder row projected onto the column vocabulary.

    ``capped`` turns the credited cell from a bare ``0.00`` — which reads as a
    decode that failed — into the word that explains it.
    """
    credited = as_float(row.get("credited_eth"))
    capped = row.get("capped") is True
    hour = row.get("hour")
    return {
        "hour": str(hour) if isinstance(hour, int) else DASH,
        "amount": fmt_eth(row.get("amount_eth")),
        "credited": CAPPED_MARK if capped else fmt_eth(credited),
        "weight": fmt_eth(row.get("weight_eth")),
        "early": _early_x(row.get("early_x")),
    }


class _FactsPanel(Vertical):
    """A title and label/value lines, with the rail's shedding contract.

    Values are built as ``·``-separated parts and parts are dropped from the
    **end** when a line does not fit; the label never shrinks, because it is
    the line's identity.  Any drop lights ``‹ widen`` on the title, so a
    half-rendered line is always announced.
    """

    TITLE = ""
    ID_PREFIX = "curator-wallet"

    DEFAULT_CSS = """
    /* `margin-bottom: 1` is the blank row between the title and the first
       value line -- the ladder gets one for free from its (usually empty) note
       Static, and without this the two halves of the view do not line up. */
    _FactsPanel > .curator-facts-title {
        width: 100%;
        margin: 0 0 1 0;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    /* auto, never 1fr: inside an auto-height row a 1fr body claims the whole
       remaining screen and starves the panels beside it down to their title
       line -- measured, and it is the same shape as the `#bottom-row` note in
       minimal.tcss. */
    _FactsPanel > .curator-facts-body {
        width: 100%;
        height: auto;
        padding: 0 1;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._payload: dict = {}
        self._seen = False

    def compose(self) -> ComposeResult:
        yield Static(self.TITLE, classes="curator-facts-title")
        yield Static("", classes="curator-facts-body")

    def on_resize(self, _event=None) -> None:
        if self._seen:
            self._render_view()

    # -- rendering ---------------------------------------------------------

    def _lines(self) -> list[tuple[str, list[str]]]:  # pragma: no cover - abstract
        raise NotImplementedError

    def _render_view(self) -> None:
        try:
            title = self.query_one(".curator-facts-title", Static)
            body = self.query_one(".curator-facts-body", Static)
        except Exception:  # not composed yet
            return

        width = max(self.content_size.width - 2, 0)
        rendered: list[str] = []
        shed = False
        for label, parts in self._lines():
            kept = list(parts)
            while kept and len(f"{label}  {' · '.join(kept)}") > width and len(kept) > 1:
                kept.pop()
                shed = True
            if kept and len(f"{label}  {' · '.join(kept)}") > width:
                shed = True
            rendered.append(safe_markup(f"{label}  {' · '.join(kept)}" if kept else label))

        text, placed = title_with_hint(self.TITLE, WIDEN_HINT if shed else "", width)
        title.update(text)
        if shed and not placed:
            rendered.insert(0, f"[yellow]{WIDEN_HINT}[/]")
        body.update("\n".join(rendered))


class CuratorWalletLadder(Vertical):
    """Every send this wallet made, oldest first, with the multiplier it got."""

    DEFAULT_CSS = """
    CuratorWalletLadder > .curator-ladder-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    CuratorWalletLadder > .curator-ladder-note {
        width: 100%;
        height: auto;
        min-height: 1;
        padding: 0 1;
    }
    CuratorWalletLadder > DataTable {
        height: 1fr;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._payload: dict = {}
        self._columns: tuple = ()
        self._hint: str = ""
        self._hint_placed = True

    def compose(self) -> ComposeResult:
        yield Static(
            LADDER_TITLE, classes="curator-ladder-title", id="curator-ladder-title"
        )
        yield Static("", classes="curator-ladder-note", id="curator-ladder-note")
        yield DataTable(id="curator-ladder-table", classes="curator-ladder-table")

    def on_mount(self) -> None:
        table = self.query_one("#curator-ladder-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        columns = self._apply_columns(table)
        table.add_row(*cells({"hour": "[dim]…[/]"}, columns, default=""))

    def on_resize(self, _event=None) -> None:
        if self._payload:
            self._render_view()

    def _apply_columns(self, table: DataTable) -> tuple:
        width = table.content_size.width or self.content_size.width
        _name, columns, hint = pick_tier(_LADDER_TIERS, width)
        install_columns(table, columns, self._columns)
        self._columns = columns
        self._hint = hint
        return columns

    def _set_title(self) -> None:
        width = max(self.content_size.width - 2, 0)
        text, placed = title_with_hint(LADDER_TITLE, self._hint, width)
        self.query_one("#curator-ladder-title", Static).update(text)
        self._hint_placed = placed or not self._hint

    def _set_note(self, text: str) -> None:
        if not self._hint_placed:
            marker = f"[yellow]{WIDEN_HINT}[/]"
            text = f"{marker} {text}" if text else marker
        self.query_one("#curator-ladder-note", Static).update(text)

    def update_data(self, you_ladder_rows=None, you_address=None, **_kwargs) -> None:
        self._payload = {"rows": you_ladder_rows, "address": you_address, "seen": True}
        self._render_view()

    def _render_view(self) -> None:
        try:
            table = self.query_one("#curator-ladder-table", DataTable)
        except Exception:  # not composed yet
            return
        if not self._payload:
            return

        columns = self._apply_columns(table)
        self._set_title()
        table.clear()

        rows = self._payload["rows"]
        if rows is None:
            # None is "the logs pool did not read", never "you never sent".
            self._set_note(f"[$warning]⚠ {LADDER_UNAVAILABLE}[/]")
            table.add_row(*cells({}, columns, default=DASH))
            return

        try:
            usable = [row for row in list(rows) if isinstance(row, dict)]
        except TypeError:
            usable = []

        if not usable:
            self._set_note(f"[dim]{NO_LADDER}[/]")
            table.add_row(*cells({}, columns, default=DASH))
            return

        self._set_note("")
        for row in usable[-MAX_LADDER_ROWS:]:
            try:
                values = _ladder_values(row)
            except Exception:
                values = {"hour": f"[dim]{DASH}[/]"}
            table.add_row(*cells(values, columns, default=DASH))


class CuratorWalletStanding(_FactsPanel):
    """Rank, score, credit, share of all weight, and when this wallet joined."""

    TITLE = STANDING_TITLE

    def update_data(
        self,
        you_rank=None,
        you_points=None,
        you_credit_eth=None,
        you_weight_eth=None,
        you_tx_count=None,
        you_weight_share_pct=None,
        you_first_hour=None,
        you_joined_utc=None,
        contributors_total=None,
        **_kwargs,
    ) -> None:
        self._payload = {
            "rank": you_rank,
            "points": you_points,
            "credit": you_credit_eth,
            "weight": you_weight_eth,
            "sends": you_tx_count,
            "share": you_weight_share_pct,
            "first_hour": you_first_hour,
            "joined": you_joined_utc,
            "total": contributors_total,
        }
        self._seen = True
        self._render_view()

    def _lines(self) -> list[tuple[str, list[str]]]:
        data = self._payload
        rank = data.get("rank")
        total = data.get("total")

        if isinstance(rank, int):
            place = f"rank {rank}" + (f" of {total:,}" if isinstance(total, int) else "")
        elif rank is None and data.get("points") is None:
            # A stranger, not a zero.  See the module docstring.
            place = NOT_ON_THE_LIST
        else:
            place = f"rank {DASH}"

        # Two short lines rather than one long one: measured at the panel's
        # 2fr share of 138 columns, a single score line sheds its tail and
        # lights the marker on a screen that is not actually too narrow.
        score = [f"{fmt_points(data.get('points'))} pts"]
        credit = as_float(data.get("credit"))
        if credit is not None:
            score.append(f"{fmt_eth(credit)} credit")

        banked: list[str] = []
        weight = as_float(data.get("weight"))
        if weight is not None:
            banked.append(f"{fmt_eth(weight)} weight")
        sends = data.get("sends")
        if isinstance(sends, int):
            banked.append(f"{sends} send{'' if sends == 1 else 's'}")
        if not banked:
            banked = [DASH]

        share = as_float(data.get("share"))
        share_parts = [f"{fmt_pct(share)} of all weight" if share is not None else DASH]

        joined = data.get("joined")
        hour = data.get("first_hour")
        joined_parts: list[str] = []
        if isinstance(hour, int):
            joined_parts.append(f"hour {hour}")
        if isinstance(joined, str) and joined.strip():
            joined_parts.append(joined.strip())
        if not joined_parts:
            joined_parts = [DASH]

        return [
            ("", [place]),
            ("score", score),
            ("banked", banked),
            ("share", share_parts),
            ("joined", joined_parts),
        ]


class CuratorWalletNext(_FactsPanel):
    """What the next legal send must be, what it buys, and what passing costs."""

    TITLE = NEXT_TITLE

    def update_data(
        self,
        you_required_next_eth=None,
        you_credit_eth=None,
        **_kwargs,
    ) -> None:
        self._payload = {
            "required": you_required_next_eth,
            "credit": you_credit_eth,
        }
        self._seen = True
        self._render_view()

    def _lines(self) -> list[tuple[str, list[str]]]:
        """The requirement only.  What it *buys* is the panel beside this one:
        the contract's escalation rule and its consequences are two different
        thoughts, and a reader deciding what to type wants the first one alone.
        """
        data = self._payload
        required = as_float(data.get("required"))
        credit = as_float(data.get("credit"))

        send_parts = [f"≥ {fmt_eth(required)} ETH" if required is not None else DASH]
        # The rule in one line: only beating your own high-water mark counts.
        beat_parts = [f"{fmt_eth(credit)} ETH" if credit is not None else DASH]

        return [("send", send_parts), ("to beat", beat_parts)]


class CuratorWalletTarget(_FactsPanel):
    """What the next legal send buys, and what the place above would cost."""

    TITLE = TARGET_TITLE

    def update_data(
        self,
        you_marginal_points=None,
        you_rank=None,
        you_next_rank=None,
        you_next_rank_needs_eth=None,
        you_next_send_passes=None,
        **_kwargs,
    ) -> None:
        self._payload = {
            "marginal": you_marginal_points,
            "rank": you_rank,
            "next_rank": you_next_rank,
            "needs": you_next_rank_needs_eth,
            "passes": you_next_send_passes,
        }
        self._seen = True
        self._render_view()

    def _lines(self) -> list[tuple[str, list[str]]]:
        data = self._payload
        marginal = data.get("marginal")
        rank = data.get("rank")
        next_rank = data.get("next_rank")
        needs = as_float(data.get("needs"))
        passes = data.get("passes")

        # 0 is real: at the cap the next legal send buys no points at all.
        gain_parts = [f"+{marginal:,} pts" if isinstance(marginal, int) else DASH]
        if passes is True:
            gain_parts.append(TAKES_RANK)
        elif passes is False:
            gain_parts.append(HOLDS_RANK)

        if isinstance(next_rank, int) and needs is not None:
            pass_parts = [f"rank {next_rank} needs {fmt_eth(needs)} ETH"]
        elif isinstance(next_rank, int):
            # Ranked, a target above, and no price: the cap is the only way
            # that happens, and saying so beats a dash.
            pass_parts = [AT_THE_CAP]
        elif rank == 1:
            pass_parts = [TOP_OF_THE_LIST]
        else:
            pass_parts = [DASH]

        return [("gain", gain_parts), ("to pass", pass_parts)]
