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
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Static

from maxpane_dashboard.widgets.curator._fmt import (
    DASH,
    EMDASH,
    as_float,
    fmt_eth,
    fmt_pct,
    fmt_points,
)
from maxpane_dashboard.widgets.curator.hero import (
    EOA_SUBTITLE,
    EOA_SUBTITLE_SHORT,
    EOA_SUBTITLE_TINY,
    CuratorHeroBox,
    _tier_for,
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
    "WALLET_TITLE",
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
    "NO_WALLET_SET",
    "NO_ENS",
    "ENS_PENDING",
    "UNKNOWN_VALUE",
    "NOT_LINKED",
    "LINKED_UNSIZED",
    "CLEAN_RANK_SUFFIX",
    "CLEAN_RANK_REMOVED",
    "STANDING_WIDTH_PROBE",
    "STANDING_FULL_WIDTH",
    "measure_standing_width",
    "CuratorWalletLadder",
    "CuratorWalletStanding",
    "CuratorWalletNext",
    "CuratorWalletTarget",
    "CuratorWalletAddress",
    "CuratorWalletHero",
    "HERO_BOX_IDS",
]

WALLET_TITLE = "YOUR WALLET"
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
#: No wallet configured -- the panel names the two ways to fix it, the same
#: pair the signals rail's YOU row names.
#: Kept in step with the signals rail's YOU row, which says the same thing in
#: the same words -- two spellings of one instruction on one screen is how a
#: reader learns to distrust both.
NO_WALLET_SET = "no wallet set · press w to set one"
#: A wallet with no reverse ENS record, which is most of them.
NO_ENS = "no ENS record"
#: Set for the moment between "you typed an address" and "the next refresh
#: resolved it".  `NO_ENS` there would be a confident negative about a lookup
#: that has not happened -- and it is wrong for exactly the reader who just
#: typed a wallet that does have a name.
ENS_PENDING = "resolving…"
#: "We looked and could not tell" — the same two words the signal rail spends
#: on the same fact, deliberately not a second spelling of it.  It is the
#: rendering of ``None`` for **both** linkage lines, and the reason neither of
#: them may fall back to its reassuring arm.
UNKNOWN_VALUE = f"{DASH} unknown"
#: The linkage sweep ran and this wallet is in no group.  A *representable*
#: negative, which is what makes ``UNKNOWN_VALUE`` distinguishable: the FARM
#: rail row shipped with "none yet" and "-- unknown" folded into one string,
#: and a reader could not tell an answer from an outage.
NOT_LINKED = "not linked to any group"
#: Linked, with a group size that would not read.  Neither "not linked" nor a
#: number invented to stand in for one.
LINKED_UNSIZED = "in a group of unknown size"
#: What the clean rank is a rank *in* — PRD §6's "#412 raw, #47 with clear
#: farms removed", minus the word "clear", which the panel has no evidence for
#: on any particular wallet.  Pattern language: a farm is a shape in the
#: deposit data, not an accusation about a person.
CLEAN_RANK_SUFFIX = "with farms removed"
#: The reader is themselves one of the removed wallets, so there is no number
#: to print — and a dash here would read as a failed computation rather than
#: as the answer it is.
CLEAN_RANK_REMOVED = "removed as a linked wallet"
#: The minimum legal send buys points but not the place above.
HOLDS_RANK = "not enough to move up"
TAKES_RANK = "enough to move up"
AT_THE_CAP = "at the credit cap — no send buys weight"
#: Marks a deposit that credited nothing because it was above the cap.
CAPPED_MARK = "capped"

MAX_LADDER_ROWS = 12

#: Label column, shared by all three facts panels so every value in the rail
#: starts in the same column -- `to beat` and `to pass` are the longest, and a
#: per-panel width would step the values in and out down the rail.
LABEL_COLS = len("to beat")

#: A comparison glyph rides in the two-column gutter between the label and the
#: value, so `≥ 491.00` and `490.90` and `4 of 10,643` all start their value in
#: the same column -- the glyph is spent out of the gutter rather than out of
#: the number's position.  Exactly as wide as the gutter, which is what makes
#: that work.
GE = "≥ "
GUTTER = "  "
assert len(GE) == len(GUTTER)

_HOUR_COLS = 5
_AMOUNT_COLS = 10
_CREDIT_COLS = 10
_WEIGHT_COLS = 10
_EARLY_COLS = 6
#: 44,721 is the ceiling this deployment's cap allows (see leaderboard's own
#: note), so six columns hold every score with the thousands separator.
_PTS_COLS = 6
_RANK_COLS = 6

_LADDER_COLUMNS = (
    ("hour", "HOUR", _HOUR_COLS),
    ("amount", "SENT", _AMOUNT_COLS),
    ("credited", "CREDITED", _CREDIT_COLS),
    ("weight", "WEIGHT", _WEIGHT_COLS),
    ("early", "MULT", _EARLY_COLS),
    ("points", "PTS", _PTS_COLS),
    ("rank", "RANK", _RANK_COLS),
)

#: Widest first.  Columns are shed from the *derived* end: the score after a
#: rung can be read off the leaderboard, the multiplier that rung got cannot be
#: read anywhere else, and the amount sent is the row's identity.
_LADDER_TIERS = tuple(
    (name, tier_cost(_LADDER_COLUMNS[:keep]), _LADDER_COLUMNS[:keep], hint)
    for name, keep, hint in (
        ("full", 7, ""),
        ("no-rank", 6, "‹ widen for rank"),
        ("no-points", 5, "‹ widen for pts"),
        ("no-weight", 4, "‹ widen for weight"),
        ("sent-only", 3, "‹ widen for credit"),
    )
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
        "points": fmt_points(row.get("points")),
        # `--` when the history was capped: see `analytics.you_ladder`.
        "rank": f"#{rank:,}" if isinstance((rank := row.get("rank")), int) else DASH,
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
        for line in self._lines():
            label, parts = line[0], line[1]
            # An empty label is a *continuation* line: its value hangs under
            # the value above it rather than starting a new column.  A third
            # element is a gutter marker (see GE) and never widens the head.
            marker = line[2] if len(line) > 2 else GUTTER
            head = f"{label:<{LABEL_COLS}}{marker}"
            kept = list(parts)
            while kept and len(head + " · ".join(kept)) > width and len(kept) > 1:
                kept.pop()
                shed = True
            if kept and len(head + " · ".join(kept)) > width:
                shed = True
            if not kept:
                rendered.append(safe_markup(head.rstrip()))
                continue
            # Escaped part by part, then marked up: `safe_markup` over the
            # assembled line would escape this panel's own emphasis.  The
            # headline value -- the first part of a labelled line -- is the one
            # a reader is looking for; a continuation line is a sentence and
            # gets none.
            escaped = [safe_markup(part) for part in kept]
            if label:
                escaped[0] = f"[bold $success]{escaped[0]}[/]"
            rendered.append(safe_markup(head) + " · ".join(escaped))

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


class CuratorWalletAddress(_FactsPanel):
    """Which wallet this whole view is about — the address, and its ENS if any.

    Every other panel here describes *a* wallet without ever naming it; with
    two wallets configured on two machines the pages are indistinguishable.
    This one names it, and it is the only place the ENS name is shown **whole**:
    the tables cap a name at the address cell's width so a stranger's 200-column
    name cannot widen a measured layout, but here there is room, and a
    truncated name is exactly the case where a reader needs the full one.
    """

    TITLE = WALLET_TITLE

    def update_data(self, you_address=None, you_ens=None, **_kwargs) -> None:
        """The normal path: a payload the manager computed for this address.

        Always clears the pending state -- this payload IS the lookup's answer,
        so a ``None`` name here means "no record" rather than "not yet asked".
        """
        self._payload = {"address": you_address, "ens": you_ens, "pending": False}
        self._seen = True
        self._render_view()

    def mark_pending(self, address: str | None) -> None:
        """Show *address* before any payload has been computed for it.

        Not a kwarg on :meth:`update_data`, because it is not data the manager
        produces: it is the screen saying "the reader just typed this, and the
        lookup has not run".  A structural test forbids a widget kwarg that is
        not a ``CURATOR_KEYS`` entry, and it is right to.
        """
        self._payload = {"address": address, "ens": None, "pending": True}
        self._seen = True
        self._render_view()

    def _lines(self) -> list[tuple]:
        address = self._payload.get("address")
        name = self._payload.get("ens")
        if not isinstance(address, str) or not address.strip():
            # Not "wallet --": nothing is configured, and the fix is a keypress.
            return [("wallet", [NO_WALLET_SET])]

        lines: list[tuple] = [("wallet", [address.strip().lower()])]
        # `no ENS record` rather than a dash: most wallets have none, and the
        # blank would read as a lookup that failed.
        if isinstance(name, str) and name.strip():
            lines.append(("ens", [name.strip()]))
        else:
            # `no ENS record` is a claim; make it only after looking.
            lines.append(("ens", [ENS_PENDING if self._payload.get("pending")
                                  else NO_ENS]))
        return lines


#: The three states ``you_linked_state`` may hold, ``None`` (= the sweep has
#: not run) aside.  A **fourth spelling is a silent fallback arm**, and the arm
#: this one would fall into is the reassuring one — so anything not in here
#: renders :data:`UNKNOWN_VALUE`, exactly as the hero treats a phase word it
#: does not know.  The widget may not import ``data/``, so the literal lives
#: here and the agreement with the contract lives in the suite.
LINKED_STATES: tuple[str, ...] = ("clean", "linked")


def _reason_parts(reasons) -> list[str]:
    """The producer's pattern-language phrases, hardened, never raising.

    Whitespace is collapsed the way ``short_label`` collapses it: a newline
    inside a reason would break a line/value layout that assumes one row per
    line, and it arrives from a fold over data an attacker chooses.  A payload
    that is not a list of strings costs the *reasons*, never the panel.
    """
    if isinstance(reasons, str):        # a bare phrase, not a list of chars
        candidates: list = [reasons]
    else:
        try:
            candidates = list(reasons or [])
        except TypeError:
            candidates = []
    return [
        " ".join(reason.split())
        for reason in candidates
        if isinstance(reason, str) and reason.strip()
    ]


def _linked_parts(state, group_size, reasons) -> list[str]:
    """The ``linked`` line's value: the group, then why it is a group.

    Three states, three sentences, and the ``None`` one is the whole reason
    this line exists in this shape.  A wallet the sweep has not looked at must
    not read as a wallet the sweep cleared: the reassuring rendering is the
    dangerous one here, and it is the one a "default to clean" would produce
    on every dashboard that has never finished an analysis.
    """
    if state not in LINKED_STATES:
        # `None`, and every spelling this widget does not know.
        return [UNKNOWN_VALUE]
    if state == "clean":
        # Reasons are `[]` for a clean wallet by contract; a producer that
        # sent some anyway is contradicting itself, and the verdict wins.
        return [NOT_LINKED]

    size = group_size if isinstance(group_size, int) and not isinstance(
        group_size, bool
    ) and group_size > 0 else None
    head = f"{size:,}-wallet group" if size is not None else LINKED_UNSIZED
    # Parts, not one joined string: `_FactsPanel` sheds from the end, so a
    # narrow rail keeps the group and drops the evidence rather than cutting
    # a phrase mid-word.  The group size is the part a reader acts on.
    return [head, *_reason_parts(reasons)]


def _standing_state(payload: dict) -> dict:
    """The flat manager dict projected onto this panel's own short keys.

    One projection, used by :meth:`CuratorWalletStanding.update_data` and by
    :func:`measure_standing_width`, so the width the module publishes is
    measured through the very builder that renders — a second copy is how a
    published width stops describing the panel it names.
    """
    return {
        "rank": payload.get("you_rank"),
        "points": payload.get("you_points"),
        "credit": payload.get("you_credit_eth"),
        "weight": payload.get("you_weight_eth"),
        "sends": payload.get("you_tx_count"),
        "share": payload.get("you_weight_share_pct"),
        "first_hour": payload.get("you_first_hour"),
        "joined": payload.get("you_joined_utc"),
        "total": payload.get("contributors_total"),
        "linked_state": payload.get("you_linked_state"),
        "linked_reasons": payload.get("you_linked_reasons"),
        "linked_group_size": payload.get("you_linked_group_size"),
        "clean_rank": payload.get("you_clean_rank"),
    }


def _clean_rank_parts(clean_rank, state) -> list[str]:
    """The ``clean`` line's value — the rank with the linked groups removed.

    ``None`` carries **two** facts and the widget can only tell them apart by
    the state beside it: WP3's contract makes a removed wallet's clean rank
    ``None``, and so is the clean rank of every wallet before the sweep has
    ever run.  "removed" is an answer; "-- unknown" is the absence of one, and
    collapsing them is the FARM-row defect repeated on the reader's own line.

    What it must never do is echo the raw rank.  Two identical numbers under
    each other read as "the farms cost you nothing" — a finding, drawn from a
    computation nobody performed.
    """
    if isinstance(clean_rank, int) and not isinstance(clean_rank, bool):
        # `#47` alone is a second number with no relation to the first; the
        # suffix is what makes the pair a sentence.
        return [f"#{clean_rank:,} {CLEAN_RANK_SUFFIX}"]
    if state == "linked":
        return [CLEAN_RANK_REMOVED]
    return [UNKNOWN_VALUE]


def _standing_lines(data: dict) -> list[tuple]:
    """This panel's label/value lines, pure — see :class:`_FactsPanel`."""
    rank = data.get("rank")
    total = data.get("total")

    if isinstance(rank, int):
        place = f"{rank}" + (f" of {total:,}" if isinstance(total, int) else "")
    elif rank is None and data.get("points") is None:
        # A stranger, not a zero.  See the module docstring.
        place = NOT_ON_THE_LIST
    else:
        place = DASH

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

    linked_parts = _linked_parts(
        data.get("linked_state"),
        data.get("linked_group_size"),
        data.get("linked_reasons"),
    )

    return [
        ("rank", [place]),
        # Beside the raw rank and directly under it: PRD §6's "#412 raw, #47
        # with clear farms removed" is one thought, and the gap between the
        # two numbers is the whole of what it says.
        ("clean", _clean_rank_parts(data.get("clean_rank"),
                                    data.get("linked_state"))),
        ("score", score),
        ("banked", banked),
        ("share", share_parts),
        ("joined", joined_parts),
        # Last, and that is deliberate: it is the only line here whose value
        # comes from a producer rather than from the contract, so it is the
        # one that grows, and the shedding contract works from the end.
        ("linked", linked_parts),
    ]


class CuratorWalletStanding(_FactsPanel):
    """Rank, score, credit, share of all weight, when this wallet joined —
    and whether it is one of the wallets the linkage sweep grouped."""

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
        you_linked_state=None,
        you_linked_reasons=None,
        you_linked_group_size=None,
        you_clean_rank=None,
        **_kwargs,
    ) -> None:
        self._payload = _standing_state(
            {
                "you_rank": you_rank,
                "you_points": you_points,
                "you_credit_eth": you_credit_eth,
                "you_weight_eth": you_weight_eth,
                "you_tx_count": you_tx_count,
                "you_weight_share_pct": you_weight_share_pct,
                "you_first_hour": you_first_hour,
                "you_joined_utc": you_joined_utc,
                "contributors_total": contributors_total,
                "you_linked_state": you_linked_state,
                "you_linked_reasons": you_linked_reasons,
                "you_linked_group_size": you_linked_group_size,
                "you_clean_rank": you_clean_rank,
            }
        )
        self._seen = True
        self._render_view()

    def _lines(self) -> list[tuple]:
        return _standing_lines(self._payload)


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

        send_parts = [f"{fmt_eth(required)} ETH" if required is not None else DASH]
        # The rule in one line: only beating your own high-water mark counts.
        beat_parts = [f"{fmt_eth(credit)} ETH" if credit is not None else DASH]

        return [
            ("send", send_parts, GE if required is not None else GUTTER),
            ("to beat", beat_parts),
        ]


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
        # The verdict is a sentence, not another statistic, so it hangs on its
        # own line under the points rather than trailing them behind a `·`.
        verdict = None
        if passes is True:
            verdict = TAKES_RANK
        elif passes is False:
            verdict = HOLDS_RANK

        # `to pass` is prefixed only to the priced form.  The other two are
        # already whole sentences, and prefixing them pushed the cap sentence
        # past the panel's width, where it wrapped mid-phrase.
        priced = False
        if isinstance(next_rank, int) and needs is not None:
            pass_parts = [f"rank {next_rank} needs {fmt_eth(needs)} ETH"]
            priced = True
        elif isinstance(next_rank, int):
            # Ranked, a target above, and no price: the cap is the only way
            # that happens, and saying so beats a dash.
            pass_parts = [AT_THE_CAP]
        elif rank == 1:
            pass_parts = [TOP_OF_THE_LIST]
        else:
            pass_parts = [DASH]

        # The verdict and the price of the place above are two halves of one
        # sentence about the same send, so both hang under the points with a
        # blank line separating them from the number itself.
        lines: list[tuple] = [("gain", gain_parts), ("", [""])]
        if verdict is not None:
            lines.append(("", [verdict]))
        head = f"to pass {pass_parts[0]}" if priced else pass_parts[0]
        lines.append(("", [head] + pass_parts[1:]))
        return lines


#: The wallet hero's three boxes.  Deliberately not the game's CLOCK / LIST /
#: CURVE: in this view the reader is asking about themselves, and the phase and
#: the hour stay legible in the title bar above.
HERO_BOX_IDS = (
    "curator-wallet-hero-rank",
    "curator-wallet-hero-score",
    "curator-wallet-hero-next",
)


def _wallet_hero_lines(title: str, big: str, *rest: str) -> list[str]:
    """Five rows: title, a blank, the loud line, then up to two details.

    The box is seven rows with its border, so five is the budget.  The game's
    hero spends it on three detail lines; these boxes have at most two, so the
    spare row buys the blank under the title rather than sitting at the bottom.
    """
    body = list(rest[:2]) + [""] * (2 - len(rest[:2]))
    return [f"[dim]{title}[/]", "", big, *body]


def _hero_rank_lines(data: dict, tier: str) -> list[str]:
    """Where this wallet sits, and out of how many."""
    rank = data.get("rank")
    total = data.get("total")
    if not isinstance(rank, int):
        # Not on the list is not rank zero, and a failed read is not either.
        note = NOT_ON_THE_LIST if data.get("points") is None else DASH
        return _wallet_hero_lines("YOUR RANK", f"[dim]{EMDASH}[/]", f"[dim]{note}[/]")
    of = f"of {total:,} wallets" if isinstance(total, int) else ""
    return _wallet_hero_lines("YOUR RANK", f"[bold]#{rank:,}[/]", f"[dim]{of}[/]")


def _hero_score_lines(data: dict, tier: str) -> list[str]:
    """What is banked: the score, the credit behind it, the share it is of."""
    points = data.get("points")
    big = f"[bold]{fmt_points(points)} pts[/]" if points is not None else f"[dim]{EMDASH}[/]"
    credit = as_float(data.get("credit"))
    share = as_float(data.get("share"))
    rest = []
    if credit is not None:
        rest.append(f"[dim]{fmt_eth(credit)} ETH credit[/]")
    if share is not None and tier != "minimal":
        rest.append(f"[dim]{fmt_pct(share)} of all weight[/]")
    if not rest:
        rest = [f"[dim]{NOT_ON_THE_LIST}[/]"]
    return _wallet_hero_lines("YOUR SCORE", big, *rest)


def _hero_next_lines(data: dict, tier: str) -> list[str]:
    """The one actionable number, and whether it is enough to move up."""
    required = as_float(data.get("required"))
    big = (
        f"[bold]{GE}{fmt_eth(required)} ETH[/]"
        if required is not None
        else f"[dim]{EMDASH}[/]"
    )
    rest = []
    marginal = data.get("marginal")
    if isinstance(marginal, int):
        rest.append(f"[dim]+{marginal:,} pts[/]")
    passes = data.get("passes")
    if passes is True:
        rest.append(f"[$success]{TAKES_RANK}[/]")
    elif passes is False:
        rest.append(f"[dim]{HOLDS_RANK}[/]")
    if not rest:
        rest = [f"[dim]{DASH}[/]"]
    return _wallet_hero_lines("YOUR NEXT SEND", big, *rest)


_HERO_BUILDERS = {
    HERO_BOX_IDS[0]: _hero_rank_lines,
    HERO_BOX_IDS[1]: _hero_score_lines,
    HERO_BOX_IDS[2]: _hero_next_lines,
}


class CuratorWalletHero(Vertical):
    """The `y` view's hero: three boxes about the reader, not about the game.

    Same geometry as :class:`CuratorHero` -- three boxes over the EOA subtitle,
    eight rows -- so swapping bodies never moves the row below it, and the one
    honest capital sentence stays on screen in both views.
    """

    DEFAULT_CSS = """
    CuratorWalletHero {
        height: 8;
    }
    CuratorWalletHero > #curator-wallet-hero-boxes {
        height: 7;
    }
    CuratorWalletHero CuratorHeroBox {
        width: 1fr;
        height: 7;
        padding: 0 2;
        margin: 0 1;
        border: solid $panel;
        background: $surface;
        content-align: center middle;
        text-align: center;
        text-wrap: nowrap;
        text-overflow: ellipsis;
        border-subtitle-color: $warning;
    }
    CuratorWalletHero > #curator-wallet-hero-note {
        width: 100%;
        height: 1;
        padding: 0 2;
        color: $text-muted;
        text-align: center;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._payload: dict = {}

    def compose(self) -> ComposeResult:
        with Horizontal(id="curator-wallet-hero-boxes"):
            for box_id in HERO_BOX_IDS:
                yield CuratorHeroBox(
                    "[dim]Loading...[/]", id=box_id, classes="curator-hero-box"
                )
        yield Static(EOA_SUBTITLE, id="curator-wallet-hero-note")

    def update_data(
        self,
        you_rank=None,
        you_points=None,
        you_credit_eth=None,
        you_weight_share_pct=None,
        you_required_next_eth=None,
        you_marginal_points=None,
        you_next_send_passes=None,
        contributors_total=None,
        **_kwargs,
    ) -> None:
        self._payload = {
            "rank": you_rank,
            "points": you_points,
            "credit": you_credit_eth,
            "share": you_weight_share_pct,
            "required": you_required_next_eth,
            "marginal": you_marginal_points,
            "passes": you_next_send_passes,
            "total": contributors_total,
            "seen": True,
        }
        self._render_view()

    def on_resize(self, _event=None) -> None:
        if self._payload:
            self._render_view()

    def _render_view(self) -> None:
        data = self._payload
        try:
            boxes = {
                box_id: self.query_one(f"#{box_id}", CuratorHeroBox)
                for box_id in HERO_BOX_IDS
            }
            note = self.query_one("#curator-wallet-hero-note", Static)
        except Exception:  # not composed yet
            return

        for box_id, box in boxes.items():
            builder = _HERO_BUILDERS[box_id]
            box.render_lines_at_tier(lambda tier, fn=builder: fn(data, tier))

        width = max(self.content_size.width - 4, 0)
        for text in (EOA_SUBTITLE, EOA_SUBTITLE_SHORT, EOA_SUBTITLE_TINY):
            if width <= 0 or len(text) <= width:
                note.update(text)
                break
        else:
            note.update(EOA_SUBTITLE_TINY)
