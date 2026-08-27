"""The announce-channel feed: decoded posts, threaded, honestly styled.

The panel is titled ``ANNOUNCE FEED`` (PRD §4), exported as ``FEED_TITLE``
because the screen WP asserts it against composited output -- including as
the *negative* half of the ``c``-swap test, where its absence is what proves
the dev-activity panel replaced this one.  Import the constant; do not
retype or shorten the string.

One logical row per channel tx, newest thread first::

    08-07 04:27  POST    I moved 33 eth to the LP on mainnet https://…  ▾ 2 replies

     08-07 09:14  REPLY   nice

      08-07 09:31  ANSWER thanks

The toggle sits on the post's own last line, and every row -- post, reply
and answer alike -- is followed by one blank line.

Kinds and their styling (classification happens upstream in
``analytics/surf_signals.classify_channel_tx``; this widget renders the
``kind`` string it is given):

* ``self``   -- ``POST`` in cyan: the dev's own broadcast.
* ``reply``  -- ``REPLY`` dim: the channel is permissionless and replies
  are anyone's text.  A reply is never styled like a dev post and its
  links are never highlighted (PRD §6.4).
* ``answer`` -- ``ANSWER`` in **cyan, the same colour as ``POST``**: an
  answer is the announce wallet's own zero-value calldata sent back to
  whoever asked, so it carries the same authenticated author a ``POST``
  does.  It wore ``ACTION``'s yellow while it was folded into that kind,
  which is precisely what made an answer read as a contract call; giving
  it ``POST``'s colour is the whole point of separating the two.
* ``action`` -- ``ACTION`` in yellow (the Rich-safe stand-in for
  ``$warning`` -- see the ``_KIND_STYLES`` note): an outbound contract call
  (the ERC-8004 register() was exactly this shape -- NEW DEPLOY fuel).
* ``fund``   -- ``FUND`` magenta: dev-wallet funding of the channel.
* ``failed`` -- ``FAILED`` red: the receipt says the tx reverted, so it is
  not the post/answer/call its calldata describes -- it is an attempt. Shown
  rather than dropped (0xTXT drops it): a dev whose call reverted is worth
  seeing, and the badge is what stops it being read as the thing it tried
  to be.

Threading
---------

``analytics/surf_feed.build_threads`` does the grouping; this module only
renders what it returns.  A root's replies (and the answers nested under
them) are **collapsed behind one toggle line** and revealed together, which
is the shape the channel actually has: a dev post with a tail of strangers'
questions is one conversation, not six peers.  Each depth is indented
exactly one column past its parent -- one column, because the indent is
paid for out of the message's own text budget and this panel's width is
what sets the surf screen's full-layout number.

Expansion state is keyed by the root's ``tx_hash`` and is **never cleared
by ``update_data``**: the screen repaints this panel every 30 s, and
collapsing what the reader just opened, twice a minute, makes the feature
unusable.  Keyed by hash rather than by row index so a new post arriving at
the top does not shift which thread is open.

Width tiers: at ``FULL_TEXT_WIDTH`` columns and above the message renders
*in full*, wrapped with a hanging indent -- the feed is the product here,
and the dev's posts are the payload.  Below that, one truncated line per
post with a visible ``…`` and ``‹ widen`` in the title (house rule: a
clipped row is always announced).  Only *visible* rows can light that
marker: a row inside a collapsed thread is not on screen, so advertising a
truncation the reader cannot see would be a lie in the other direction.

On-chain messages contain raw newlines (nonce 8 does today); they are
flattened to single spaces *before* truncation, and ``safe_markup`` runs
**after** all slicing so an escape sequence can never be cut in half.

A row with nothing to say still says something: an ``action`` or ``fund``
whose calldata is empty has no ``text`` and no decoded ``label``, and the
panel used to render its badge followed by a blank line -- indistinguishable
from a rendering bug.  ``_message_of`` falls back ``text`` -> ``label`` ->
``sent <n> ETH`` -> ``(no message)``, so every row carries evidence of why
it is on screen.

``feed_items=None`` means the source is dead (explicit unavailable state);
``[]`` means the window is genuinely empty.  Never a blank panel.

Rendering primitive: one ``Static`` subclass per row inside a
``VerticalScroll``, **never a ``RichLog``** (which has no click targets) and
never a ``DataTable``.  Rows are handed a pre-built ``rich.text.Text``, not a
markup string, and that is the load-bearing half of this widget's safety
story: ``Static.update()`` defers ``Content.from_markup`` into the message
pump, so a malformed attacker-authored name would raise *outside* the
screen's ``try/except`` and kill the app -- the exact ``DataTable`` crash
``widgets/markup_safety`` documents.  ``Text.from_markup`` is called here,
inside ``_row_text``'s own ``try``, where a parse failure degrades to a
skipped row exactly as a malformed ``ts`` already did.  ``safe_markup``
still runs on every third-party string before it is interpolated:
escaping and pre-parsing are independent guards, and neither replaces the
other -- escaping is what keeps ``[/x]`` from *being* markup, pre-parsing is
what keeps a parse failure inside a ``try`` we own.

Primitives only -- this module imports nothing from the data layer.  It does
import one *pure* analytics module (``analytics/surf_feed``: stdlib-only, no
I/O, no clock, no Textual), which is the repo-wide pattern for shared pure
helpers; ``tests/widgets/test_surf_widget_contract.py`` pins that exception
by name and re-proves the module's purity transitively rather than trusting
the import list here.
"""

from __future__ import annotations

import math
import re
import textwrap

from rich.cells import cell_len
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Static

from maxpane_dashboard.analytics.surf_feed import build_threads
from maxpane_dashboard.widgets.cell_fitting import fit_cell
from maxpane_dashboard.widgets.markup_safety import safe_markup
from maxpane_dashboard.widgets.surf._fmt import DASH, fmt_age, hhmm, mmdd

#: Panel title, PRD §4 spelling.  **Interface**: the screen tests assert this
#: exact string reaches the compositor, and assert its *absence* when the
#: ``c`` key swaps in the dev-activity panel.  Import it, never retype it.
FEED_TITLE = "ANNOUNCE FEED"

#: Columns at or above which messages render in full (wrapped).
#:
#: Lowered 76 -> 71 on request, and the reason is worth recording because the
#: obvious lever was the wrong one.  The columns were re-seamed 3:2 -> 7:6 to
#: bring the screen's full-layout width down from 176 to 152, which narrowed
#: this panel's share: at 76 the feed only began wrapping at a 151-column
#: terminal, so between 135 and 150 it showed one truncated line per post.
#: The instinct was to widen the feed's column back, but that trade was bad --
#: a 9:7 seam wrapped from 144 and cost 9 columns of full-layout width (152 ->
#: 161), because the *dev activity* panel was what bound at 152, not this one.
#: Moving this threshold instead wrapped from 142 and cost the full-layout
#: width **nothing**; all three of 76/71/66 left it at 152 (measured then).
#:
#: **That free ride is over, and the paragraph above is the old regime.** The
#: activity row's cells were sized to their producer's vocabularies, which
#: took that panel 66 -> 58 columns, so it clears from 135 and *this* panel is
#: what binds the screen. This threshold now sets the screen's full-layout
#: width directly: re-measured on the real screen, 66 -> 135, **71 -> 142**,
#: 76 -> 151. Lowering it is now the cheapest width there is; raising it is
#: paid in full-layout columns, one for one.
#:
#: What it does cost is rows: a wrapped post is taller than a cut one, so at
#: 143 columns the feed spends 9 rows on the two sweep posts where it spent 3.
#: That is what wrapping *is*, and this panel is the one the layout hands all
#: its slack height to, so it is the cheapest place in the screen to spend it.
#: 66 would wrap from 132 if an even narrower terminal ever matters.
#:
#: Threading spends *rows*, not columns: a nested row's one-column indent is
#: taken out of its own text budget, so the tier boundary is unchanged and a
#: collapsed thread is strictly cheaper than the flat list ever was.
FULL_TEXT_WIDTH = 71

#: Marker appended to the title when a message had to be truncated.
WIDEN_HINT = "‹ widen"

#: The explicit degraded line.  Tested verbatim.
UNAVAILABLE_LINE = "feed unavailable"

#: Badge for the announce wallet's own answer to a question.  **Interface**:
#: exported because the threading tests assert it separately from ``ACTION``,
#: which is the kind it used to be folded into.
ANSWER_BADGE = "ANSWER"

#: Toggle glyphs.  **Interface**: exported so a test can assert the *absence*
#: of both on a thread with no replies without retyping either character.
TOGGLE_COLLAPSED = "▸"
TOGGLE_EXPANDED = "▾"

#: Max feed items rendered per refresh.  Applied to the *items*, newest
#: first, **before** threading -- which is what slices a conversation, not
#: what keeps one whole: 25 replies newer than the post they answer push
#: that post out of the window, and each of them then renders as its own
#: top-level ``REPLY`` root with no post above it and no toggle (the
#: "a reply that predates the first self-post" fallback in
#: ``analytics/surf_feed``). That is the honest outcome of a cap measured in
#: rows -- nothing is silently dropped and the replies stay readable -- but
#: it is a cap on *rows*, not on threads, and this comment used to claim the
#: opposite. A thread-aware cap would have to walk the threads first and
#: count roots, which is a different budget than the one the panel's height
#: is sized against.
_MAX_ROWS = 25

#: ``MM-DD HH:MM`` (11) + 2 spaces + badge column (6) + 1 space.
_PREFIX_WIDTH = 20

#: Minimum text budget: below this we stop shrinking and let CSS clip.
_MIN_TEXT_BUDGET = 10

#: Shown when a row has no text, no decoded label and no value to report.
#: A badge with an empty line beside it reads as a rendering bug; this reads
#: as what it is.
NO_MESSAGE = "(no message)"

#: badge text + colour per kind.  Unknown kinds render dim ``?``.
#:
#: Literal Rich colour names, not Textual ``$warning``-style design tokens:
#: rows reach the screen as ``rich.text.Text`` built by ``Text.from_markup``
#: -- Rich's own parser, the one ``rich.markup.escape`` is built against --
#: not Textual's ``Content.from_markup``/``$token`` extension.  ``[$warning]``
#: is not valid Rich markup and raised ``MarkupError`` on every ACTION row
#: until this was caught by the test suite; ``yellow`` is the same warning
#: colour already used literally elsewhere in this module (``_set_title``,
#: ``UNAVAILABLE_LINE``).
#:
#: ``answer`` shares ``self``'s cyan on purpose -- see the module docstring.
_KIND_STYLES = {
    "self": ("POST", "cyan"),
    "reply": ("REPLY", "dim"),
    "answer": (ANSWER_BADGE, "cyan"),
    "action": ("ACTION", "yellow"),
    "fund": ("FUND", "magenta"),
    # A tx the chain rejected. Six characters like ANSWER and ACTION, so it
    # rides the existing badge cell and this panel's width does not move.
    "failed": ("FAILED", "red"),
}

#: Characters Textual accepts in a widget ``id``.  A ``tx_hash`` is
#: third-party text, so it is filtered rather than trusted: a hash carrying
#: anything else would raise ``BadIdentifier`` at mount time, which is the
#: pump-side crash this module exists to make impossible.
_ID_SAFE = re.compile(r"[^A-Za-z0-9_-]")


#: Above this the amount is printed in exponent form rather than grouped.
#: More ETH than exists (supply is ~120 M), so anything past it is a decode
#: artefact or a hostile value, and ``sent 1,000,000,000,000,000,019,884,624,838,656 ETH``
#: is a 40-column cell in a panel whose whole budget is 71.
_ABSURD_ETH = 1e9


def _eth_amount(value) -> str | None:
    """``0.05`` -> ``"0.05"``; junk, ``None`` and non-finite -> ``None``.

    Trailing zeros are trimmed because this string is a *fallback* for a row
    that has nothing else to say, and ``0.050000 ETH`` reads like a precision
    claim the chain never made.  Six decimals first, then ``%g`` for anything
    that would round to a bare ``0`` -- a 1-gwei dust transfer is a real row
    on this channel and ``sent 0 ETH`` would be a false zero, which is the
    one thing this repo never renders.

    The input is a wei value divided by 1e18 and wei is attacker-influenced,
    so the two shapes a naive ``float()`` lets through are closed here:
    ``nan``/``inf`` (``float("nan")`` succeeds, and ``sent nan ETH`` is a
    string this panel would print in full sincerity) and magnitudes past
    :data:`_ABSURD_ETH`, whose comma-grouped form is wider than the panel.
    Both fall back to a form the reader can see is not a normal amount --
    ``None`` for the non-finite ones, which drops the row to
    :data:`NO_MESSAGE` rather than inventing a number.
    """
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(number):
        return None
    if abs(number) >= _ABSURD_ETH:
        return f"{number:.6g}"
    trimmed = f"{number:,.6f}".rstrip("0").rstrip(".")
    if trimmed in ("", "0", "-0") and number != 0:
        return f"{number:g}"
    return trimmed or "0"


def _has_readable_ts(item) -> bool:
    """Would :func:`build_threads` keep this row, or silently drop it?

    It drops anything whose ``ts`` will not coerce -- and ``ts`` comes from
    ``SurfManager._feed_items``' ``_opt_float``, which returns ``None`` for a
    missing or unparseable Blockscout timestamp, so this is reachable rather
    than theoretical.  A dropped row is worse than an undated one: at best a
    real message disappears, and when *every* row is undated the panel falls
    through to ``no posts in window`` -- claiming the window was empty when
    the truth is that we could not read it.  That is the one distinction
    this panel exists to keep, so the widget partitions the rows itself and
    renders the undated ones as their own top-level entries, stamped
    ``??-?? ??:??`` by ``mmdd``/``hhmm``.

    The rule is a deliberate mirror of ``analytics/surf_feed._coerce_ts``
    rather than an import of it -- that function is private to a pure module
    with its own tests -- and
    ``test_the_feed_partitions_exactly_what_build_threads_drops`` is the
    agreement test that fails if the two ever disagree.
    """
    value = item.get("ts") if isinstance(item, dict) else None
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, str):
        try:
            float(value)
        except ValueError:
            return False
        return True
    return False


def _message_of(item) -> str:
    """The row's message, or the best evidence available that it happened.

    ``text`` is the decoded calldata and is what nearly every row carries.
    An outbound call with no UTF-8 payload has none, so the decoded method
    ``label`` speaks for it; a plain value transfer has neither -- empty
    calldata is what makes it a transfer -- and then the *amount* is the
    only fact there is.  Falling through all three to a blank line is what
    this chain does not do: the announce channel's own funding tx (0.054 ETH,
    ``input: 0x``) rendered as ``FUND`` and nothing at all.
    """
    raw = " ".join(str(item.get("text") or "").split())
    if raw:
        return raw
    raw = " ".join(str(item.get("label") or "").split())
    if raw:
        return raw
    amount = _eth_amount(item.get("value_eth"))
    if amount is not None:
        return f"sent {amount} ETH"
    return NO_MESSAGE


def _char_budget(raw: str, budget: int) -> int:
    """``budget`` columns expressed as the character count that fills them.

    ``textwrap`` has no notion of cell width, so the only lever it offers is
    the number it counts.  Dividing the column budget by the text's own mean
    cell width lands each wrapped chunk near the right *width* instead of
    the right *length* -- exact for a uniform script, and for mixed text the
    residue is trimmed by :func:`_cell_fit`.
    """
    chars = len(raw)
    if not chars:
        return budget
    mean_cells = cell_len(raw) / chars
    if mean_cells <= 1.0:
        return budget
    return max(int(budget / mean_cells), _MIN_TEXT_BUDGET)


# Compatibility name: tests and older Surf callers import this private helper.
_cell_fit = fit_cell


def _wrap_no_widow(raw: str, budget: int) -> list[str]:
    """Greedy word-wrap ``raw`` at ``budget`` columns, avoiding widows.

    Plain ``textwrap.wrap`` fills greedily from the front, which can strand
    a short final fragment on its own line -- a real captured 227-char post
    ends ``"...as always 0 promises."`` and a plain greedy fill at this
    panel's real column budget splits ``"0"`` from ``"promises."``, putting
    the tail of the message on a line by itself.  That is not a hostile
    input -- it is what a genuine dev post does to an honest word-wrapper,
    and it is what this widget's own tests caught.

    The fix is bounded widow control: if the last line is much shorter than
    the budget, retry at a narrower target width (never wider -- a wider
    retry could produce a line wider than the column it goes in, which the
    compositor would then clip with no visible marker; this function is what
    every caller relies on to have already fit each line). The search is
    capped and always falls back to the plain wrap if no narrower width
    helps, so this never loops unboundedly and never exceeds ``budget`` on
    any line.
    """
    wrapped = textwrap.wrap(
        raw, budget, break_long_words=False, break_on_hyphens=False
    ) or [""]
    if len(wrapped) <= 1:
        return wrapped

    widow_floor = max(budget // 3, _MIN_TEXT_BUDGET)
    if len(wrapped[-1]) >= widow_floor:
        return wrapped

    floor = max(budget // 2, _MIN_TEXT_BUDGET)
    for trial in range(budget - 1, floor - 1, -1):
        candidate = textwrap.wrap(
            raw, trial, break_long_words=False, break_on_hyphens=False
        ) or [""]
        if len(candidate[-1]) >= widow_floor:
            return candidate
    return wrapped


def _item_lines(item, width: int, depth: int = 0) -> tuple[list[str], bool] | None:
    """Render one feed item at ``width`` columns, indented by ``depth``.

    Returns ``(markup_lines, clipped)`` or ``None`` for malformed input.
    Escaping happens after wrapping/truncation, per token, so a cut can
    never bisect an escape sequence.

    ``depth`` is paid out of the *text* budget, never added to the line: a
    nested row is exactly one column narrower than its parent, so no tier
    boundary and no full-layout width moves when a thread is opened.
    """
    if not isinstance(item, dict):
        return None
    try:
        pad = " " * depth
        stamp = f"{mmdd(item.get('ts'))} {hhmm(item.get('ts'))}"
        kind = str(item.get("kind") or "").strip().lower()
        badge, color = _KIND_STYLES.get(kind, ("?", "dim"))
        prefix = f"{pad}{stamp}  [{color}]{badge:<6}[/] "
        indent = " " * (_PREFIX_WIDTH + depth)

        # Flatten on-chain newlines/tabs to single spaces first.
        raw = _message_of(item)
        budget = max(width - _PREFIX_WIDTH - depth, _MIN_TEXT_BUDGET)

        if width >= FULL_TEXT_WIDTH:
            # `textwrap` counts characters and the budget is columns, so the
            # target width is scaled by the text's own average cell width
            # before wrapping: pure ASCII scales by 1.0 and wraps exactly as
            # it always has, a wall of CJK scales by 2.0 and wraps at half
            # the character count, which is the same number of columns.
            # Approximate on mixed text by construction -- `_cell_fit` below
            # is the exact backstop, and it announces whatever it takes.
            wrapped = _wrap_no_widow(raw, _char_budget(raw, budget))
            # An unbreakable token -- a base64 blob, a long URL, a hash --
            # is exactly what ``textwrap.wrap(..., break_long_words=False)``
            # will not split: it lands on its own line wider than ``budget``
            # and passes through untouched.  The compositor would then clip
            # it itself with no visible sign at all, which breaks the house
            # rule that a clipped row is always announced.  Force it to the
            # same visible ``…`` truncation the narrow tier uses, and light
            # the widen hint -- never widen a retry (that risks the identical
            # silent clip), only ever shrink to fit.
            clipped = False
            fitted = []
            for chunk in wrapped:
                chunk, was_cut = _cell_fit(chunk, budget)
                clipped = clipped or was_cut
                fitted.append(chunk)
            lines = [prefix + safe_markup(fitted[0])]
            lines += [indent + safe_markup(chunk) for chunk in fitted[1:]]
            return lines, clipped

        fitted, clipped = _cell_fit(raw, budget)
        return [prefix + safe_markup(fitted)], clipped
    except Exception:
        # A single malformed item must never take down the panel.
        return None


def _row_line_texts(item, width: int, depth: int = 0) -> tuple[list[Text], bool] | None:
    """One parsed ``Text`` per *rendered line*, or ``None`` if it will not render.

    The same work :func:`_row_text` does, stopping one step earlier. A root
    that carries a toggle needs its final line as a widget of its own — the
    toggle sits beside it, on that line — while the lines above it stay one
    row, so this returns the pieces and lets the caller decide how many
    widgets to make of them.

    Splitting here rather than at the markup level is deliberate: a line's
    colour tags are opened and closed inside that line, so parsing per line
    and parsing the joined block give the same spans, and doing it per line
    keeps every parse inside this function's own ``try`` (see
    :func:`_row_text` for why that ``try`` is load-bearing).
    """
    try:
        rendered = _item_lines(item, width, depth)
        if rendered is None:
            return None
        lines, clipped = rendered
        return [Text.from_markup(line) for line in lines], clipped
    except Exception:
        return None


def _row_text(item, width: int, depth: int = 0) -> tuple[Text, bool] | None:
    """``(Text, clipped)`` for one item, or ``None`` if it will not render.

    The markup is parsed **here**, synchronously, inside this function's own
    ``try`` -- not handed to ``Static.update()`` as a string.  Textual defers
    ``Content.from_markup`` into the message pump, so a parse failure there
    raises outside the screen's ``try/except`` and takes the app with it;
    parsed here, the identical failure degrades to a skipped row, which is
    the contract ``_item_lines`` has always had for a malformed ``ts``.

    Nothing here asks the ``Text`` not to wrap, and that is deliberate
    rather than an omission: Textual 8's ``visualize()`` funnels a Rich
    ``Text`` through ``Content.from_rich_text``, which carries the *spans*
    and drops ``no_wrap``/``overflow`` entirely -- setting them reads as a
    guarantee and is a no-op.  The real guarantee is ``text-wrap: nowrap``
    on :class:`SurfFeedRow`, plus ``_cell_fit`` having already measured
    every line in terminal cells so there is nothing left to wrap.
    """
    rendered = _row_line_texts(item, width, depth)
    if rendered is None:
        return None
    lines, clipped = rendered
    return Text("\n").join(lines), clipped


class SurfFeedRow(Static):
    """One rendered feed item: its badge line plus any wrapped continuation.

    A plain ``Static`` rather than a line in a shared log because the
    threaded feed needs per-row widgets to hang click targets off; this class
    carries no behaviour of its own and exists so the CSS (and the tests) can
    name a feed row without matching every ``Static`` on the screen.

    ``text-wrap: nowrap`` is load-bearing and is the *only* thing that
    enforces it.  ``RichLog(wrap=False)`` used to do this job; a ``Static``
    wraps by default, and the Rich ``Text`` handed to it cannot say
    otherwise -- Textual 8's ``visualize()`` rebuilds it through
    ``Content.from_rich_text``, which does not carry ``no_wrap`` or
    ``overflow``.  Without this rule a message of double-width glyphs
    reflowed onto continuation rows: the badge line rendered
    ``08-07 06:27  POST`` and then *nothing*, the text landed on the rows
    below at column zero, and every nested row lost its indent -- a
    regression the ``RichLog`` never had.  ``text-overflow: clip`` matches:
    the ``…`` this panel prints is put there by ``_cell_fit``, which also
    lights ``‹ widen``; an ellipsis the compositor adds silently would be a
    cut with no announcement.
    """

    DEFAULT_CSS = """
    SurfFeedRow {
        width: 100%;
        height: auto;
        text-wrap: nowrap;
        text-overflow: clip;
    }
    SurfFeedRow.surf-feed-gap {
        height: 1;
    }
    SurfFeedRow.surf-feed-inline {
        width: auto;
    }
    """


class SurfFeedToggle(Static):
    """The ``▸ 2 replies`` line: one per root that has any.

    Focusable and clickable, and both routes call the same ``action_toggle``
    so the keyboard is never a second implementation of the mouse.  It holds
    the root's ``tx_hash`` rather than its row index: the feed repaints every
    30 s and a new post arrives at the top, which renumbers every index below
    it but changes no hash.
    """

    can_focus = True

    BINDINGS = [
        Binding("enter", "toggle", "expand replies", show=False),
        Binding("space", "toggle", "expand replies", show=False),
    ]

    DEFAULT_CSS = """
    SurfFeedToggle {
        width: 100%;
        height: 1;
        text-wrap: nowrap;
        text-overflow: clip;
    }
    SurfFeedToggle.surf-feed-toggle-inline {
        width: auto;
    }
    SurfFeedToggle:focus {
        text-style: reverse;
    }
    """

    def __init__(self, renderable, *, tx_hash: str, **kwargs) -> None:
        super().__init__(renderable, **kwargs)
        self.tx_hash = tx_hash

    def _feed(self) -> "SurfFeed | None":
        for node in self.ancestors:
            if isinstance(node, SurfFeed):
                return node
        return None

    def action_toggle(self) -> None:
        feed = self._feed()
        if feed is not None:
            feed.toggle_thread(self.tx_hash)

    def on_click(self, event) -> None:
        event.stop()
        self.action_toggle()


class SurfFeed(Vertical):
    """Announce-channel feed: threaded, collapsible, with kind badges."""

    DEFAULT_CSS = """
    SurfFeed > .surf-feed-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    SurfFeed > #surf-feed-body {
        height: 1fr;
        padding: 0 1;
        overflow-y: scroll;
        overflow-x: hidden;
        scrollbar-size: 1 1;
    }
    SurfFeed .surf-feed-rows {
        width: 100%;
        height: auto;
    }
    SurfFeed .surf-feed-headline {
        width: 100%;
        height: auto;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._payload: dict = {}
        #: ``root tx_hash -> is expanded``.  Never cleared by ``update_data``
        #: -- see the module docstring; a 30-second repaint that re-collapses
        #: what the reader opened is what makes this feature unusable.
        self._expanded: dict[str, bool] = {}
        self._rendered_width: int | None = None

    def compose(self) -> ComposeResult:
        yield Static(FEED_TITLE, classes="surf-feed-title", id="surf-feed-title")
        yield Static(" ", classes="surf-feed-spacer")
        yield VerticalScroll(id="surf-feed-body")

    def update_data(
        self,
        feed_nonce=None,
        feed_last_post_age_s=None,
        feed_items=None,
        **_kwargs,
    ) -> None:
        """Rewrite the feed.  Kwargs are exactly the PRD §5 feed keys."""
        self._payload = {
            "nonce": feed_nonce,
            "age_s": feed_last_post_age_s,
            "items": feed_items,
        }
        # A repaint rebuilds every row, so a reader who has a thread open and
        # focused loses both their focus and their scroll position -- twice a
        # minute, on a panel they were in the middle of reading. Restoring
        # them is only correct while the panel *is* being read, which is what
        # a focused toggle means; with nothing focused the feed still scrolls
        # home, because the newest post is the point of a refresh.
        focus_tx = self._focused_toggle_tx()
        self._render_view(keep_position=focus_tx is not None, focus_tx=focus_tx)

    def _focused_toggle_tx(self) -> str | None:
        """The hash of the toggle this feed currently has focus on, if any."""
        try:
            focused = self.screen.focused
        except Exception:  # no screen yet
            return None
        if not isinstance(focused, SurfFeedToggle):
            return None
        # Two feeds could be mounted at once (a test harness, a future
        # split view); only this one's toggle is ours to restore.
        return focused.tx_hash if self in focused.ancestors else None

    def on_resize(self, _event=None) -> None:
        """Re-lay out: the tier and every wrap depend on the width.

        Guarded on the width rather than run unconditionally: the render
        mounts widgets, and a height-only resize (the rail growing, a status
        line appearing) would otherwise tear down and rebuild every row --
        and with it the reader's focus and scroll position -- for a layout
        that cannot have changed.
        """
        if self._payload and self._body_width() != self._rendered_width:
            self._render_view()

    # -- expansion -----------------------------------------------------

    def toggle_thread(self, tx_hash: str) -> None:
        """Flip one root's collapsed state and repaint in place.

        The repaint keeps the scroll offset and re-focuses the same toggle:
        the widgets are rebuilt, so a reader who opened a thread ten posts
        down would otherwise be thrown back to the top of the panel with
        nothing focused -- and the keyboard route, which needs the toggle to
        still be focused to be pressed twice, would work exactly once.
        """
        self._expanded[tx_hash] = not self._expanded.get(tx_hash, False)
        self._render_view(keep_position=True, focus_tx=tx_hash)

    # -- rendering -----------------------------------------------------

    def _body(self) -> VerticalScroll | None:
        try:
            return self.query_one("#surf-feed-body", VerticalScroll)
        except Exception:  # not composed yet
            return None

    def _body_width(self) -> int:
        """Columns a row may occupy, measured the way the row is painted.

        ``scrollable_content_region`` and not ``content_size``: the body
        reserves its vertical scrollbar gutter unconditionally
        (``overflow-y: scroll``, the same always-on gutter ``RichLog`` used
        to give this panel), so ``content_size.width`` is one column wider
        than anything can actually paint into.  Measuring against the wider
        number silently clipped the last character of a narrow-tier row --
        dropping the truncation ``…`` this module exists to guarantee.
        """
        body = self._body()
        if body is None:
            return 0
        width = body.scrollable_content_region.width
        if width <= 0:
            width = max(self.content_size.width - 3, 0)
        return width

    def _set_title(self, nonce, age_s, clipped: bool, unavailable: bool) -> None:
        title = self.query_one("#surf-feed-title", Static)
        parts = [FEED_TITLE]
        try:
            parts.append(f"· #{int(nonce)}")
        except (TypeError, ValueError):
            pass
        age = fmt_age(age_s)
        if age != DASH:
            parts.append(f"· last {age} ago")
        if unavailable:
            parts.append("· [yellow]unavailable[/]")
        text = " ".join(parts)
        if clipped:
            text += f"  [yellow]{WIDEN_HINT}[/]"
        title.update(text)

    def _toggle_line(self, count: int, expanded: bool) -> Text:
        glyph = TOGGLE_EXPANDED if expanded else TOGGLE_COLLAPSED
        word = "reply" if count == 1 else "replies"
        return Text(f" {glyph} {count} {word}", style="dim")

    def _build_rows(self, items, width: int) -> tuple[list, bool, list]:
        """Widgets for every visible row, whether any clipped, and the toggles.

        Only visible rows can set the clipped flag: a truncation inside a
        collapsed thread is not on screen, and ``‹ widen`` promises the
        reader that widening the terminal will show them something more.

        The toggles come back as their own list because most of them are no
        longer *in* ``rows``: one that renders beside its post's last line is
        a child of a ``Horizontal``, and a caller scanning ``rows`` for
        ``SurfFeedToggle`` would silently miss exactly those. Reaching into
        the container instead would mean reading Textual's
        ``_pending_children`` -- an unmounted container's ``children`` is
        empty -- and a private attribute is not something focus restoration
        should be resting on.
        """
        rows: list = []
        toggles: list = []
        clipped_any = False
        used_ids: set[str] = set()

        datable = [item for item in items if _has_readable_ts(item)]
        undated = [item for item in items if not _has_readable_ts(item)]

        for root in build_threads(datable):
            replies = root.get("replies") or []
            # The count is *direct* replies, not every hidden row: an answer
            # nested under a question is part of that question, so offering
            # "4 replies" for two conversations would name rows rather than
            # the thing the reader is being offered. A depth-1 answer (one
            # addressed to nobody the thread knows) counts, because at that
            # depth it really is a reply to the post.
            direct = sum(1 for r in replies if int(r.get("depth") or 1) <= 1)
            tx_hash = str(root["item"].get("tx_hash") or "")
            # A root with no ``tx_hash`` has no key to remember an expansion
            # under and no id to hang a click target off, so its replies are
            # shown rather than locked behind a toggle nothing can open.
            # Losing them would be silent data loss; the channel is
            # permissionless and this row shape is reachable.
            expanded = self._expanded.get(tx_hash, False) if tx_hash else True

            toggle = None
            toggle_text = None
            if replies and tx_hash:
                toggle_text = self._toggle_line(direct, expanded)
                toggle = SurfFeedToggle(
                    toggle_text,
                    tx_hash=tx_hash,
                    id=self._toggle_id(tx_hash, used_ids),
                    classes="surf-feed-toggle-inline",
                )
                toggles.append(toggle)

            rendered = _row_line_texts(root["item"], width, 0)
            lines = None
            if rendered is not None:
                lines, clipped = rendered
                clipped_any = clipped_any or clipped

            if lines is not None:
                # The toggle belongs *beside the message it opens*, on the
                # post's own final line, not stranded at column zero under
                # it. Two widgets on one row, so the focus ring and the click
                # target still cover the toggle alone and not the post.
                #
                # It goes back to its own line when it will not fit, and that
                # branch is not decoration: a `Horizontal` whose children
                # overrun it clips them with no `…` and no `‹ widen`, which
                # is the silent cut this panel exists not to make. Measured
                # in terminal cells rather than characters -- a post ending
                # in CJK or emoji fits half as much as `len()` claims.
                inline = (
                    toggle is not None
                    and lines[-1].cell_len + toggle_text.cell_len <= width
                )
                if inline:
                    if len(lines) > 1:
                        rows.append(SurfFeedRow(Text("\n").join(lines[:-1])))
                    rows.append(
                        Horizontal(
                            SurfFeedRow(lines[-1], classes="surf-feed-inline"),
                            toggle,
                            classes="surf-feed-headline",
                        )
                    )
                else:
                    rows.append(SurfFeedRow(Text("\n").join(lines)))
                    if toggle is not None:
                        rows.append(toggle)
                rows.append(self._gap())
            elif toggle is not None:
                # The root itself would not render -- a malformed item is
                # dropped, never raised on. Its replies are still real and
                # still reachable, so the toggle stays.
                rows.append(toggle)
                rows.append(self._gap())

            if expanded:
                for reply in replies:
                    rendered = _row_text(
                        reply["item"], width, int(reply.get("depth") or 1)
                    )
                    if rendered is None:
                        continue
                    text, clipped = rendered
                    clipped_any = clipped_any or clipped
                    rows.append(SurfFeedRow(text))
                    rows.append(self._gap())

        # Undated rows last, which is where the producer already puts them:
        # ``_feed_items`` sorts on ``(ts is not None, ts)`` descending, so a
        # row it could not date sits at the end of the list it hands over.
        # They are never threaded -- an undated row has no position in a
        # conversation, and guessing one would be worse than showing it flat.
        for item in undated:
            rendered = _row_text(item, width, 0)
            if rendered is None:
                continue
            text, clipped = rendered
            clipped_any = clipped_any or clipped
            rows.append(SurfFeedRow(text))
            rows.append(self._gap())

        return rows, clipped_any, toggles

    @staticmethod
    def _gap():
        """One blank line, after every rendered row without exception.

        Posts, replies and answers are all multi-line and none of them has
        any other separator, so without this a post's last wrapped line runs
        straight into the next row's date and the two read as one message.
        It used to be one blank per *thread*, which separated conversations
        from each other but left the rows inside a conversation packed --
        exactly where the reader most needs to tell an answer from the next
        question. Trailing blanks cost nothing here: the panel scrolls, and
        omitting the last one would drop the separator precisely when the
        final row is what got scrolled to.
        """
        return SurfFeedRow(Text(" "), classes="surf-feed-gap")

    @staticmethod
    def _toggle_id(tx_hash: str, used: set[str]) -> str:
        """A Textual-legal, collision-free id for one root's toggle.

        Stable across repaints because it is derived from the hash, which is
        what makes an open thread survive a new post arriving above it.
        Filtered because a ``tx_hash`` is third-party text and an illegal
        character would raise ``BadIdentifier`` at mount; de-duplicated
        because two different hostile hashes can filter down to the same
        string, and a duplicate id inside one container is a hard crash
        rather than a cosmetic clash.
        """
        base = f"surf-feed-toggle-{_ID_SAFE.sub('', tx_hash)}"
        candidate = base
        suffix = 1
        while candidate in used:
            candidate = f"{base}-{suffix}"
            suffix += 1
        used.add(candidate)
        return candidate

    def _render_view(
        self, keep_position: bool = False, focus_tx: str | None = None
    ) -> None:
        body = self._body()
        if body is None:
            return

        items = self._payload.get("items")
        nonce = self._payload.get("nonce")
        age_s = self._payload.get("age_s")
        width = self._body_width()
        self._rendered_width = width
        offset = body.scroll_offset

        if items is None:
            # Source dead: explicit state, never a blank panel (PRD §5 meta).
            self._set_title(nonce, age_s, clipped=False, unavailable=True)
            self._mount_rows(
                body, [SurfFeedRow(Text(f"⚠ {UNAVAILABLE_LINE}", style="yellow"))]
            )
            return

        try:
            item_list = [i for i in list(items)[:_MAX_ROWS] if isinstance(i, dict)]
        except TypeError:
            item_list = []

        rows, clipped_any, toggles = self._build_rows(item_list, width)
        self._set_title(nonce, age_s, clipped=clipped_any, unavailable=False)
        if not rows:
            self._mount_rows(
                body, [SurfFeedRow(Text("  no posts in window", style="dim"))]
            )
            return

        self._mount_rows(body, rows)
        if focus_tx is not None:
            # Searched in the freshly built list, never with ``self.query``:
            # Textual prunes on a later pump cycle, so at this instant the
            # *outgoing* toggle for this hash is still in the DOM and is what
            # a query would find first. Focusing it moved the focus onto a
            # widget one tick from deletion, and Textual then handed focus to
            # the scroll container instead -- so the keyboard route opened a
            # thread once and did nothing on the second press.
            for toggle in toggles:
                if toggle.tx_hash == focus_tx:
                    self._take_focus(toggle)
                    break
        if keep_position:
            body.scroll_to(y=offset.y, animate=False)
        else:
            self.call_after_refresh(body.scroll_home, animate=False)

    def _take_focus(self, row: "SurfFeedToggle") -> None:
        """Focus *row* now, not on a later tick.

        ``Widget.focus()`` defers through ``App.call_later``, and the deferred
        callback silently does nothing when the repaint was driven from
        outside the message pump -- which is exactly how a refresh arrives:
        the screen calls ``update_data`` from its worker, not from a key
        handler. The keyboard route (inside the pump) worked and the
        30-second repaint did not, which is the harder half to notice.
        ``Screen.set_focus`` is the synchronous form and behaves the same in
        both. ``scroll_visible=False`` because the caller restores the exact
        offset the reader was at a few lines below; letting focus scroll
        first would fight it.
        """
        try:
            self.screen.set_focus(row, scroll_visible=False)
        except Exception:  # no screen, or the row is not focusable yet
            row.focus()

    @staticmethod
    def _mount_rows(body: VerticalScroll, rows: list) -> None:
        """Replace the body's contents with ``rows``, in one synchronous pass.

        The rows go inside a fresh, **id-less** container rather than
        straight into the body, and that indirection is the whole point:
        Textual removes widgets by posting a ``Prune`` message, so the
        outgoing rows are still registered when the incoming ones mount, and
        an incoming toggle carrying the same stable ``id`` as the outgoing
        one it replaces raises ``DuplicateIds`` -- on the *second* repaint of
        any thread, i.e. 30 seconds after launch.  ``_ensure_unique_id`` is
        scoped to one parent's node list, so giving each generation its own
        parent makes the two sets of ids invisible to each other, and the old
        generation is gone by the next pump cycle.
        """
        body.remove_children()
        body.mount(Vertical(*rows, classes="surf-feed-rows"))
