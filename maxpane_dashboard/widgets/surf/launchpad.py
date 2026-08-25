"""IMD launchpad panels: the coin table, the curve-swap flow, the burn pipe.

Three render-only widgets, added for the v4 migration (2026-08-19 -- 146
coins by 73 distinct creators, 4,683 curve swaps by 673 traders, 3,299 IMD
burned, all in four days):

* :class:`SurfLaunchpadCoins` -- one row per launched coin, already ranked
  and capped upstream (``LAUNCHPAD_RENDER_LIMIT`` = 20, ``data/surf_client.py``).
* :class:`SurfCurveFlow` -- the aggregate swap/trader/creator-revenue numbers
  for the whole launchpad, read from the same slow tier as the coin table.
* :class:`SurfBurnPipeline` -- the permissionless bridge-and-burn executor's
  own state.  **Read-only** (CLAUDE.md hard constraint 1 -- no signer, no
  transactor, no calldata construction anywhere in this repo): this panel
  *displays* that ``bridgeToBaseBurnReceiver()`` is callable by anyone, the
  same framing ``hero.py``'s BURN box and ``data/surf_addresses.py`` already
  use for the same executor.  It never offers to call it, never builds
  calldata and never quotes gas for the purpose of sending.

**Ticker and name are attacker-chosen.**  ``LaunchpadFactory.launch(string,
string)`` is permissionless and costs only gas, so any wallet can name a coin
``[/x]`` or ``[bold red]pwn[/]`` -- this is the first surf panel whose text is
picked by a hostile party rather than merely quoted from the announce
channel (``data/surf_client.py``'s own docstring: "escaping is Task 11's job,
never this layer's" -- ticker/name reach this module completely raw).

Every ``ticker`` and ``name`` goes through :func:`_sanitize`, which does
three things in a fixed order -- flatten, strip, escape:

1. flatten embedded newlines/control whitespace to single spaces (the same
   first step ``feed.py`` uses for announce-channel text);
2. **strip complete ``[...]``-shaped bracket runs outright**, rather than
   merely escaping them.  A ticker or a coin name has no legitimate use for
   a literal square bracket (unlike a free-form announce post, which
   ``feed.py`` handles by escaping alone) -- this is the same "strip the
   known-hostile shape, then escape whatever remains" pattern
   ``widgets/frenpet/wallet/fpw_pets.py`` already uses for emoji in pet
   names.  It is also load-bearing here in a way the emoji case is not: a
   *well-formed* Rich style tag like ``[bold red]pwn[/]`` parses without
   error (verified against this repo's live Rich/Textual versions) and would
   silently apply arbitrary styling to an attacker's choice of text if it
   ever reached ``Text.from_markup`` unescaped -- escaping alone would still
   neutralise it, but the literal tag characters would then render *as
   text*, which is a second, milder but still unwanted, form of the same
   problem (a coin's display name showing raw markup punctuation instead of
   the coin's actual name);
3. truncate to the cell's column budget, then escape via
   ``widgets/markup_safety.safe_markup`` -- truncation always runs before
   escaping so a cut can never bisect an escape sequence (the ``feed.py``
   ordering), and ``safe_markup`` still runs unconditionally, last, as the
   actual crash-safety net for anything step 2 does not catch (an unbalanced
   bracket with no matching close, for one -- see the mutation-proof note on
   :func:`_sanitize`).

``creator`` is never freeform text -- it is always a 20-byte address the
client formats as ``0x`` + 40 hex chars -- so it only gets ``safe_markup``
through :func:`_creator_cell`, the same treatment ``activity.py`` gives
``counterparty``, no stripping needed.

Three-state rendering rules this module holds itself to (CLAUDE.md, "a
failed read is None, never 0"):

* ``change_24h_pct is None`` means fewer than two priced swaps landed in the
  coin's day-long ranking window (Task 7's widened window, Task 1's renamed
  row shape) -- rendered as a dash, never ``0%``, which would assert a
  measured flat day that never occurred.  A genuine ``0.0`` (traded, ended
  flat) still renders ``+0.0%``, honestly distinct from the dash.
* ``burn_ready`` is tri-state.  ``hero.py``'s BURN box already renders this
  exact field as ``READY``/``NOT READY``/an em-dash; this panel says the
  same three facts in different words (``ready``/``not yet``/``unknown``,
  deliberately lower-case) so a reader never has to reconcile two
  vocabularies for one field, while ``None`` still never collapses into
  either a confident "ready" or a confident "not yet".
* ``burn_accrued``/``burn_staged``/``burn_min_bridge`` have a representable
  zero -- ``0`` means "we looked and nothing has accrued/is required" --
  formatted through ``fmt_compact`` (turns ``None`` into ``"--"``, never
  ``"0"``), the same helper and the same reasoning ``hero.py`` uses for the
  same three fields.  ``launchpad_burned_total`` (the ``burned_total`` param)
  is the one exception: it is the headline cumulative figure, so it gets
  exact comma-grouped digits (:func:`_fmt_total`) rather than a K/M
  abbreviation, mirroring ``hero.py``'s own non-short-tier ``cum_line``.

Primitives only -- this module imports nothing from ``data/`` or
``analytics/``.
"""

from __future__ import annotations

import re

from rich.cells import cell_len

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Static

from maxpane_dashboard.widgets.markup_safety import safe_markup
from maxpane_dashboard.widgets.surf._fmt import (
    DASH,
    as_float,
    fmt_age,
    fmt_compact,
    fmt_imd,
)

__all__ = ["SurfBurnPipeline", "SurfCurveFlow", "SurfLaunchpadCoins"]

# ---------------------------------------------------------------------------
# shared text-cleaning helpers (ticker / name -- attacker-chosen)
# ---------------------------------------------------------------------------

#: A complete ``[...]`` bracket run with no nested bracket -- catches both a
#: well-formed style tag (``[bold red]``) and a bare closing tag
#: (``[/x]``).  Deliberately *not* anchored to Rich's own tag grammar: a
#: ticker/name has no legitimate use for literal brackets at all, so every
#: complete pair is dropped rather than only the ones that would parse.
_TAG_LIKE = re.compile(r"\[[^\[\]]*\]")


def _flatten(value: object) -> str:
    """Collapse embedded newlines/control whitespace to single spaces.

    On-chain strings can contain raw newlines the same way announce-channel
    posts can (``feed.py``), and this has to run before both stripping and
    truncation so neither operates on a string that still has embedded line
    breaks in it.
    """
    if value is None:
        return ""
    return " ".join(str(value).split())


def _clip(value: str, width: int) -> str:
    """Truncate already-flattened, already-stripped, still-unescaped text to
    ``width`` columns, marked with ``…`` when it was cut.

    Must run before :func:`safe_markup` -- escaping first and truncating
    after can cut a ``\\[`` escape pair in half at the boundary.
    """
    if width <= 0 or len(value) <= width:
        return value
    if width == 1:
        return "…"
    return value[: width - 1] + "…"


def _sanitize(value: object, width: int) -> str:
    """Flatten, strip bracket-tag-shaped noise, truncate, escape -- in that
    order.  See the module docstring for why each step exists and why the
    order is fixed.

    Mutation-proof note (Task 11, Step 5): removing the final
    ``safe_markup`` call here does **not** turn
    ``test_hostile_ticker_and_name_never_reach_markup`` red for the exact
    fixture in that test, because step 2 already removes every complete
    ``[...]`` pair before ``safe_markup`` would ever run on it -- there is
    nothing left for the escape call to neutralise in that specific input.
    ``safe_markup`` still matters for anything step 2 does not catch (a lone
    unmatched ``[`` with no closing bracket, which ``_TAG_LIKE`` cannot
    match and therefore cannot strip); see ``task-11-report.md`` for the
    empirical follow-up that demonstrates the crash with stripping disabled.
    """
    flat = _flatten(value)
    stripped = _TAG_LIKE.sub("", flat)
    stripped = " ".join(stripped.split())
    clipped = _clip(stripped, width)
    return safe_markup(clipped)


# ---------------------------------------------------------------------------
# SurfLaunchpadCoins -- the ranked coin table
# ---------------------------------------------------------------------------

COINS_TITLE = "LAUNCHPAD COINS"
COINS_UNAVAILABLE = "launchpad unavailable"
COINS_EMPTY = "no coins launched yet"

#: The bare hint (SurfMarket's ``SHORT_HINT``/curator's own convention):
#: this panel has exactly one tier, whole or clipped, so there is no
#: shorter-but-still-descriptive form to fall back to the way SurfMarket's
#: ``WIDEN_HINTS`` ladder does -- one word is both the widest and the only
#: one that ever needs to fit beside ``LAUNCHPAD COINS``.
COINS_WIDEN_HINT = "‹ widen"

#: This panel's own binding width, in ``self.size.width`` terms (Task 13,
#: measured against composited output in
#: ``tests/screens/test_surf_screen.py``'s ``l``-body sweep -- see
#: ``SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS`` in ``screens/surf.py`` for the
#: screen-width counterpart, two columns higher for the panel's own
#: ``padding: 0 1``).
#:
#: **Cannot be read off ``DataTable.show_horizontal_scrollbar``.** That flag
#: reads ``True`` several columns before any character is actually lost --
#: at ``self.size.width == 95`` (two above this constant) the whole header
#: still reaches the compositor, ``BURNED`` and all, yet the scrollbar flag
#: is already lit. A marker keyed off it would fire early and disagree with
#: what the screen actually shows, so this is a literal measured threshold
#: instead: the nine fixed columns (``_TICKER_COLS`` .. ``_BURNED_COLS``, now
#: including ``_SWAPS_ALL_COLS`` -- still 79) plus the DataTable's own
#: internal cell gutter, swept column by column until the compositor
#: stopped truncating ``BURNED``'s last character.
#:
#: **91 -> 93, re-measured by Task 13 (2026-08-24), and the two columns were
#: a live silent clip.** The column *count* went 8 -> 9 in Task 11 (SWAPS
#: ALL), which buys one more ``DataTable`` cell gutter even though the
#: width-constant sum held at 79 -- 91 was swept for eight columns and had
#: been stale for nine ever since. Task 11 left it alone deliberately rather
#: than guessing, and the guess would have been wrong in the dangerous
#: direction: swept again with the panel rendered full width, the header
#: reads ``BURNE`` at a content width of 92 and ``BURN`` at 91, so at both
#: of those widths the table was losing a character with the marker dark --
#: exactly the silent clipping CLAUDE.md forbids, and the reason this is a
#: measured literal rather than arithmetic over the column constants.
#: 93 is the first content width at which the whole header, ``BURNED``
#: included, reaches the compositor.
#:
#: In screen terms that is 95 (this panel's own ``padding: 0 1``), which is
#: what ``SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS``'s seam arithmetic is built on.
#: Re-sweep -- never re-derive -- if a column is ever added or removed again.
_TABLE_FULL_WIDTH = 93

#: Defensive re-cap.  The manager already caps ``launchpad_coins`` at
#: ``LAUNCHPAD_RENDER_LIMIT`` (20, ``data/surf_client.py``); this widget
#: cannot import that constant (primitives only) so it re-states the same
#: number rather than trusting the payload never to grow.
MAX_COIN_ROWS = 20

#: Column budget, in rendered columns.  Ticker/name width is no longer a
#: security control (:func:`_sanitize` strips hostile bracket content before
#: truncation ever runs), so these are sized for legibility against the real
#: fixture's tickers (``ICE``, ``DAOs``, ``K-256``) and generous coin names,
#: not against the length of an attack payload.
#:
#: Fixed total, 79, unchanged by Task 11 (``test_the_table_still_needs_
#: exactly_seventy_nine_columns``): SWAPS ALL is a new column paid for by
#: shrinking CREATOR, not by widening the panel -- this repo's rule ("when a
#: new value would widen a sized cell, shorten the value") applied literally,
#: because a truncated address is an honest short form and there was no
#: honest way to shrink SWAPS ALL itself (it is already a bare integer).
_TICKER_COLS = 8
_NAME_COLS = 18
#: 11, was 17 (``activity.py``'s own ``ADDR_COLS`` still uses the wider
#: form unchanged -- that panel never needed to pay for a tenth column).
#: :func:`_short_addr`, not ``_fmt.long_addr``, renders to this width: six
#: leading characters (``0x`` + 4 hex) + an ellipsis + four trailing, an
#: honest short form of the same anti-poisoning idea at half the window.
_ADDR_COLS = 11
_AGE_COLS = 4
_PRICE_COLS = 10
_PCT_COLS = 7
#: ``SW 24H`` on screen -- the day-long ranking window (Task 7).  The header
#: is the short form because 6 columns is all there is; see ``on_mount``.
_SWAPS_COLS = 6
#: ``SW ALL`` on screen -- the all-time tiebreak (Task 7), new in Task 11.
#: What pays
#: for this column is CREATOR's 17 -> 11 shrink above, not a widened total.
_SWAPS_ALL_COLS = 6
_BURNED_COLS = 9
# 8+18+11+4+10+7+6+6+9 = 79


def _ticker_cell(ticker: object) -> str:
    cleaned = _sanitize(ticker, _TICKER_COLS)
    return f"[bold]{cleaned}[/]" if cleaned else f"[dim]{DASH}[/]"


def _name_cell(name: object) -> str:
    cleaned = _sanitize(name, _NAME_COLS)
    return f"[dim]{cleaned}[/]" if cleaned else f"[dim]{DASH}[/]"


def _short_addr(value: object) -> str:
    """``0x`` + first 4 hex + ``…`` + last 4 -- this table's own 11-column
    anti-poisoning window (:data:`_ADDR_COLS`), narrower than
    ``_fmt.long_addr``'s shared 17-column form.  Kept as a local helper
    rather than widening ``long_addr``'s own contract with a width
    parameter: ``activity.py``'s ``ADDR_COLS`` still needs the wider
    8-hex/6-hex split unchanged, and that call site has no reason to grow a
    parameter it would never vary.

    Six leading characters (``0x`` + 4 hex), an ellipsis, four trailing --
    half of ``long_addr``'s collision-resistance window, but this column
    lost half its own width to pay for SWAPS ALL (Task 11) and a truncated
    address is still an honest short form of the same idea, per this
    repo's "shorten the value, not the constant" rule.
    """
    if not value:
        return DASH
    s = str(value).strip()
    if not s:
        return DASH
    if len(s) <= _ADDR_COLS:
        return s
    return f"{s[:6]}…{s[-4:]}"


def _creator_cell(creator: object, known: bool) -> str:
    """The anti-poisoning window (:func:`_short_addr`, :data:`_ADDR_COLS`),
    never a friendly label: ``creator_known`` is a bool the manager derives
    against its own allowlist (Task 1's frozen ``SURF_ROW_KEYS
    ["launchpad_coins"]`` carries no label field alongside it), so this
    widget has nothing to substitute even when it is ``True`` -- it can only
    style the raw address, cyan when known, dim otherwise (``activity.py``'s
    exact convention for ``counterparty``).
    """
    window = _short_addr(creator)
    escaped = safe_markup(window)
    colour = "cyan" if known else "dim"
    return f"[{colour}]{escaped}[/]"


def _price_cell(value: object) -> str:
    """Curve price in ETH, no unit suffix (the column header carries it)."""
    v = as_float(value)
    if v is None:
        return DASH
    if v == 0:
        return "0"
    a = abs(v)
    if a >= 1:
        return f"{v:,.3f}"
    if a >= 0.0001:
        return f"{v:.5f}"
    return f"{v:.2e}"


def _pct_cell(value: object) -> str:
    """24h change (Task 7's day-long ranking window).  ``None`` -> dash,
    never ``0%`` -- see the module docstring.  A genuine ``0.0`` (traded,
    ended flat) still renders ``+0.0%``, honestly distinct from the dash.

    Plain Rich colour names, never a ``$``-prefixed theme token: this cell
    is a ``DataTable`` value, and ``DataTable``'s ``default_cell_formatter``
    calls plain ``rich.text.Text.from_markup`` directly rather than
    Textual's CSS-variable-aware renderer, so ``[$success]`` raises
    ``MarkupError`` there even though the identical token works fine in a
    ``Static`` (``hero.py``/``market.py``/``signals.py`` all rely on that
    ``Static``-only resolution).  Discovered empirically while implementing
    this module: :func:`_pct_cell` originally read ``[$success]``/
    ``[$error]`` and crashed the very first render.  ``activity.py`` and
    every curator ``DataTable`` widget already avoid the token for the same
    reason, using plain names (``"cyan"``, ``"dim"``, ``"yellow"``) instead.
    """
    v = as_float(value)
    if v is None:
        return DASH
    if v > 0:
        return f"[green]+{v:.1f}%[/]"
    if v < 0:
        return f"[red]{v:.1f}%[/]"
    return "[dim]+0.0%[/]"


def _swaps_cell(value: object) -> str:
    """Shared by SWAPS 24H and SWAPS ALL: both are a representable ``int``
    zero, never ``None``, per ``LaunchpadCoin``'s own docstring (a coin that
    has never traded really has ``0`` swaps in either window -- that is a
    fact worth ranking on, not a failed read to hide), so this one formatter
    already renders both honestly without a second copy.
    """
    try:
        return str(int(value))
    except (TypeError, ValueError):
        return DASH


def _coin_row(coin: object) -> tuple[str, ...] | None:
    """One coin dict -> the table row's cells; ``None`` drops it.

    A single malformed row must never take down the whole panel (the
    ``activity.py``/``leaderboard.py`` precedent).
    """
    if not isinstance(coin, dict):
        return None
    try:
        return (
            _ticker_cell(coin.get("ticker")),
            _name_cell(coin.get("name")),
            _creator_cell(coin.get("creator"), bool(coin.get("creator_known"))),
            fmt_age(coin.get("age_s")),
            _price_cell(coin.get("price_eth")),
            _pct_cell(coin.get("change_24h_pct")),
            _swaps_cell(coin.get("swaps_24h")),
            _swaps_cell(coin.get("swaps_all")),
            fmt_compact(coin.get("imd_burned")),
        )
    except Exception:
        return None


class SurfLaunchpadCoins(Vertical):
    """One row per launched coin: ticker, name, creator, age, price, 24h
    change, swaps in the last 24h, all-time swaps, IMD burned -- ranked on
    the 24h window with an all-time tiebreak (Task 7) and capped upstream.
    """

    DEFAULT_CSS = """
    SurfLaunchpadCoins > .surf-lpc-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    SurfLaunchpadCoins > .surf-lpc-gap {
        width: 100%;
        height: 1;
        padding: 0 1;
    }
    SurfLaunchpadCoins > DataTable {
        height: 1fr;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # Raw payload, not formatted rows -- kept so a later refresh always
        # starts from the same source the first render did.
        self._payload: dict = {}

    def compose(self) -> ComposeResult:
        yield Static(COINS_TITLE, classes="surf-lpc-title", id="surf-lpc-title")
        # A permanently empty row between the title and the table. It was
        # `#surf-lpc-note` and carried the population/staleness line; that
        # line now shares the title's row, so this widget's whole job is the
        # blank. The id follows the responsibility -- a `note` that can never
        # carry a note is a lie left for the next reader.
        yield Static("", classes="surf-lpc-gap", id="surf-lpc-gap")
        yield DataTable(id="surf-lpc-table", classes="surf-lpc-table")

    def on_mount(self) -> None:
        table = self.query_one("#surf-lpc-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_column("TICKER", width=_TICKER_COLS)
        table.add_column("NAME", width=_NAME_COLS)
        table.add_column("CREATOR", width=_ADDR_COLS)
        table.add_column("AGE", width=_AGE_COLS)
        table.add_column("PRICE", width=_PRICE_COLS)
        table.add_column("24H%", width=_PCT_COLS)
        # ``SW 24H``/``SW ALL``, not ``SWAPS 24H``/``SWAPS ALL``: these two
        # columns are 6 wide, and ``DataTable`` truncates a header to its
        # column width with no ellipsis and no other trace, so both of the
        # long forms rendered as the bare word ``SWAPS`` -- two adjacent
        # columns, one header, different numbers under it (41 and 977), at
        # EVERY width including the full layout. That defeats the column
        # Task 11 added and is worse than not adding it, because the two
        # counts invite being read as each other. Both short forms are
        # exactly 6 cells, so they fit whole and the 79-column total is
        # untouched -- this repo's "shorten the value, not the constant"
        # rule applied to a header instead of a cell.
        #
        # ``SW`` and not ``24H``/``ALL`` alone: the neighbouring column is
        # ``24H%``, and ``24H%`` beside a bare ``24H`` is the same collision
        # one column to the left. The ``SW`` prefix is what says these two
        # count swaps while the ``%`` says the other is a price move.
        table.add_column("SW 24H", width=_SWAPS_COLS)
        table.add_column("SW ALL", width=_SWAPS_ALL_COLS)
        table.add_column("BURNED", width=_BURNED_COLS)
        self._set_title()

    def on_resize(self, _event=None) -> None:
        """Keep the title's marker honest across a live resize.

        This panel is composed hidden (``#surf-launchpad-body``'s
        ``display`` starts ``False``) and only laid out once ``l`` shows
        it, so this is also what lights the marker correctly on the very
        first reveal -- ``on_mount`` runs before the widget has a real
        size (``self.size.width`` is ``0``), and :meth:`_set_title` treats
        that as "not measured yet" rather than "too narrow", the same
        optimistic reading ``SurfMarket._tier_for`` gives ``width <= 0``.
        """
        self._set_title()

    def update_data(
        self, coins=None, coin_count=None, launch_count=None, as_of_hhmm=None,
        **_kwargs,
    ) -> None:
        """Refresh the table.

        ``coins=None`` means the launchpad sweep failed outright; ``[]``
        means it ran and genuinely found nothing (the current chain state
        has 146 coins, but the contract has to say so honestly regardless).

        ``launch_count`` (Task 8's ``launchpad_launch_count``, Task 6's
        cursor-resumed full-history sweep) is the population the sweep
        actually *read*, kept separate from ``coin_count`` (the factory's
        own ``coinCount()`` claim) so :meth:`_note_parts` can compare the two
        rather than silently rendering whichever subset the sweep produced
        as though it were the whole population -- see the module-level note
        on Task 6's review finding for why that comparison exists at all.
        """
        self._payload = {
            "coins": coins,
            "coin_count": coin_count,
            "launch_count": launch_count,
            "as_of_hhmm": as_of_hhmm,
            "seen": True,
        }
        self._render_view()

    def _note_parts(self) -> tuple[str, bool]:
        """The population/staleness phrase, or the degraded warning --
        plain, unmarked, unescaped, and paired with whether it *is* the
        degraded warning.

        This is the plain form :meth:`_set_title` measures with
        ``rich.cells.cell_len`` to decide what fits (fix round 2: measuring
        a markup-wrapped string with ``len()`` either counts tag characters
        that never reach a pixel, or -- the defect this repo has shipped
        before -- undercounts a wide cell if it ever measured rendered
        codepoints with plain ``len()`` instead), and it is also the source
        both the title and the old note row used to render from.

        Unchanged logic, moved twice now: ``146 coins`` when the sweep read
        the whole population and ``146 coins · 66 read`` when it did not --
        the detector that would have caught a truncating sweep returning 2
        of 146 launches as a success. ``launch_count is None`` means the
        sweep failed outright, so this stays silent about the population
        rather than asserting either agreement or disagreement.
        """
        if not self._payload:
            return "", False
        coins = self._payload.get("coins")
        if coins is None:
            return f"⚠ {COINS_UNAVAILABLE}", True
        coin_count = self._payload.get("coin_count")
        launch_count = self._payload.get("launch_count")
        try:
            count_str = str(int(coin_count))
        except (TypeError, ValueError):
            count_str = DASH
        population = f"{count_str} coins"
        if launch_count is not None and coin_count is not None:
            try:
                disagree = int(launch_count) != int(coin_count)
            except (TypeError, ValueError):
                disagree = False  # can't compare -- say nothing extra
            if disagree:
                try:
                    read_str = str(int(launch_count))
                except (TypeError, ValueError):
                    read_str = DASH
                population = f"{count_str} coins · {read_str} read"
        parts = [population]
        as_of = self._payload.get("as_of_hhmm")
        if as_of:
            parts.append(f"as of {str(as_of)}")
        return " · ".join(parts), False

    #: Visible width of the fixed separator this title inserts before a
    #: shown note (``"  "`` + a dim ``"·"`` + ``" "``) / before a shown
    #: marker (``"  "``) -- both are literal, styling-only strings with no
    #: user content in them, so their cell width is a constant rather than
    #: something to measure per render.
    _NOTE_SEP_COLS = 4
    _MARKER_SEP_COLS = 2

    #: ``.surf-lpc-title``'s own ``padding: 0 1`` (DEFAULT_CSS above) eats
    #: one column on each side of the Static's content box, so the text
    #: budget available to :meth:`_set_title` is ``self.size.width`` (the
    #: *container's* width) minus these two columns, never
    #: ``self.size.width`` itself. Getting this wrong is exactly how round
    #: 1's fix regressed: the fit check compared a candidate's plain width
    #: against the unpadded container width, so it could accept a tier
    #: that was two columns too wide, hand it to the CSS ellipsis, and
    #: have the ellipsis eat the last two columns of the marker -- the
    #: same silent-clipping shape as the wrap it was fixing.
    _TITLE_PADDING_COLS = 2

    def _title_markup(self, show_note: bool, show_marker: bool,
                       note_plain: str, is_warning: bool) -> str:
        """Build the title's markup for one tier. Pure -- no DOM access,
        no width decision -- so :meth:`_set_title` can call it once it has
        already decided which tier fits."""
        text = COINS_TITLE
        if show_note and note_plain:
            note_markup = (
                f"[$warning]{note_plain}[/]" if is_warning
                else f"[dim]{safe_markup(note_plain)}[/]"
            )
            text += f"  [dim]·[/] {note_markup}"
        if show_marker:
            text += f"  [yellow]{COINS_WIDEN_HINT}[/]"
        return text

    def _title_plain_width(self, show_note: bool, show_marker: bool,
                            note_plain: str) -> int:
        """Rendered width of the same tier :meth:`_title_markup` would
        build, measured on plain text with ``rich.cells.cell_len`` --
        never on the markup string, and never with ``len()``."""
        n = cell_len(COINS_TITLE)
        if show_note and note_plain:
            n += self._NOTE_SEP_COLS + cell_len(note_plain)
        if show_marker:
            n += self._MARKER_SEP_COLS + cell_len(COINS_WIDEN_HINT)
        return n

    def _set_title(self) -> None:
        """``LAUNCHPAD COINS · 146 coins · as of 01:14   ‹ widen``, fitted
        to the panel's own width rather than left to CSS to clip.

        Fix round 2: ``text-overflow: ellipsis`` alone (round 1's fix for
        the title *wrapping*) silently ate the ``‹ widen`` marker itself in
        exactly the width band the marker exists to warn about -- the
        silent-clipping failure this repo forbids outright, on the one
        panel whose whole job this task series is. The CSS stays as the
        last-resort net (a truly cramped width still needs something to
        stop a wrap), but this method now fits the row itself first, so
        the ellipsis never has anything meaningful left to eat.

        Order of sacrifice, most to least important (the ``_budget``
        pattern in ``activity.py``, applied to a title instead of a row):
        the title text is never dropped; the ``‹ widen`` marker is a
        correctness signal (the table itself is clipping columns) and
        outranks the note, which is only context (population, staleness),
        so the note is what gets shed first when the two don't both fit.

        One deliberate exception: when the sweep failed outright
        (``coins is None``), the note *is* the warning -- the most
        important thing on the row, because there is nothing else to say
        -- so it outranks the marker instead, and the marker is what gets
        shed in that case. Both tiers are still measured, never assumed:
        this only changes which piece is sacrificed, not whether fitting
        is attempted.
        """
        try:
            title = self.query_one("#surf-lpc-title", Static)
        except Exception:  # not composed yet
            return

        width = self.size.width
        note_plain, is_warning = self._note_parts()
        note_wanted = bool(note_plain)
        marker_wanted = bool(width) and width < _TABLE_FULL_WIDTH

        if width <= 0:
            # Not measured yet -- render everything, the same optimistic
            # reading `SurfMarket._tier_for` gives `width <= 0`.
            title.update(self._title_markup(note_wanted, False, note_plain,
                                             is_warning))
            return

        # The title's own left+right padding is not text budget -- see
        # `_TITLE_PADDING_COLS`.
        budget = width - self._TITLE_PADDING_COLS

        # Tier 1: title + note + marker, if everything wanted actually fits.
        if self._title_plain_width(note_wanted, marker_wanted,
                                    note_plain) <= budget:
            title.update(self._title_markup(note_wanted, marker_wanted,
                                             note_plain, is_warning))
            return

        # Tier 2: shed the lower-priority one of {note, marker}. Normally
        # that is the note (see the docstring); in the degraded case the
        # note IS the warning and outranks the marker, so the marker is
        # shed instead -- the asymmetry is deliberate, not a special case
        # left over from a bug.
        if is_warning:
            title.update(self._title_markup(True, False, note_plain,
                                             is_warning))
        else:
            title.update(self._title_markup(False, marker_wanted, note_plain,
                                             is_warning))
        # Below this tier, `text-wrap: nowrap` / `text-overflow: ellipsis`
        # (the CSS) is the last-resort net, and at that width the panel has
        # bigger problems than this title.

    def _render_view(self) -> None:
        try:
            table = self.query_one("#surf-lpc-table", DataTable)
        except Exception:  # not composed yet
            return
        # Geometry-plus-note, correct whether or not there is a payload yet
        # -- a refresh must never blank a marker a resize already lit, nor
        # light one a resize has not earned, and an empty payload's note is
        # simply the empty string (see ``_note_parts``).
        self._set_title()
        if not self._payload:
            return

        table.clear()

        coins = self._payload.get("coins")
        if coins is None:
            # Plain "yellow", not "$warning" -- see the note on `$`-tokens
            # in _pct_cell; this is a DataTable cell too. 8 dashes: nine
            # columns total since Task 11 added SWAPS ALL, minus this cell.
            table.add_row(f"[yellow]{COINS_UNAVAILABLE}[/]", *([DASH] * 8))
            return

        try:
            usable = list(coins)[:MAX_COIN_ROWS]
        except TypeError:
            usable = []

        if not usable:
            table.add_row(f"[dim]{COINS_EMPTY}[/]", *([DASH] * 8))
            return

        for coin in usable:
            row = _coin_row(coin)
            if row is not None:
                table.add_row(*row)


# ---------------------------------------------------------------------------
# SurfCurveFlow -- swap/trader/creator-revenue aggregate
# ---------------------------------------------------------------------------

FLOW_TITLE = "CURVE FLOW"


def _fmt_eth_owed(value: object) -> str:
    v = as_float(value)
    if v is None:
        return DASH
    return f"{v:,.4f}"


def _flow_lines(swap_count, trader_count, creator_eth_owed, as_of_hhmm) -> list[str]:
    try:
        swap_str = str(int(swap_count))
    except (TypeError, ValueError):
        swap_str = DASH
    try:
        trader_str = str(int(trader_count))
    except (TypeError, ValueError):
        trader_str = DASH

    swaps_v = as_float(swap_count)
    traders_v = as_float(trader_count)
    if swaps_v is not None and traders_v is not None and traders_v > 0:
        avg_str = f"{swaps_v / traders_v:.1f} swaps/trader"
    else:
        avg_str = f"{DASH} swaps/trader"

    owed = _fmt_eth_owed(creator_eth_owed)

    lines = [
        f"[dim]{FLOW_TITLE}[/]",
        # A blank line under the title. The rail's panels sat flush against
        # their own headings and read as one block of text; this is the same
        # breathing room `SurfDevActivity`'s `.surf-activity-spacer` Static
        # gives its own log, spent as a row rather than a widget because
        # these panels are one `Static` each.
        "",
        f"{swap_str} swaps · {trader_str} traders",
        f"[dim]{avg_str}[/]",
        f"[dim]owed {owed} ETH to creators[/]",
    ]
    if as_of_hhmm:
        lines.append(f"[dim]as of {safe_markup(str(as_of_hhmm))}[/]")
    return lines


class SurfCurveFlow(Vertical):
    """Aggregate bonding-curve activity: swaps, traders, creator ETH owed.

    Read from the same slow "launchpad" tier as :class:`SurfLaunchpadCoins`
    and :class:`SurfBurnPipeline` (``data/surf_manager.py``'s
    ``_launchpad_payload`` -- one combined cache slot), so ``as_of_hhmm``
    carries the same slower-clock staleness marker curator's analysis panels
    already use for the same reason: this tier ticks slower than the title
    bar's own clock, on purpose.
    """

    DEFAULT_CSS = """
    SurfCurveFlow {
        height: auto;
    }
    SurfCurveFlow > Static {
        width: 100%;
        padding: 0 1;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(f"[dim]{FLOW_TITLE}[/]", id="surf-flow-body")

    def update_data(
        self,
        swap_count=None,
        trader_count=None,
        creator_eth_owed=None,
        as_of_hhmm=None,
        **_kwargs,
    ) -> None:
        lines = _flow_lines(swap_count, trader_count, creator_eth_owed, as_of_hhmm)
        try:
            self.query_one("#surf-flow-body", Static).update("\n".join(lines))
        except Exception:  # not composed yet
            pass


# ---------------------------------------------------------------------------
# SurfBurnPipeline -- the permissionless bridge-and-burn executor
# ---------------------------------------------------------------------------

BURN_TITLE = "BURN PIPELINE"


def _ready_word(ready) -> str:
    """``ready`` / ``not yet`` / ``unknown`` -- deliberately lower-case and
    deliberately different words from ``hero.py``'s ``READY``/``NOT
    READY``/em-dash for the *same* ``burn_ready`` field: this panel is a
    full standalone view rather than a five-line box, so it can afford
    words instead of a compressed headline, and ``"not yet"``/``"unknown"``
    share no substring with ``"ready"`` -- unlike ``"NOT READY"``, which
    contains ``"ready"`` -- so a reader (or a test) grepping for the word
    can never mistake an indeterminate read for a confident negative one.
    ``None`` must never render as ready and never as a confident "not
    ready" (CLAUDE.md, the tri-state sibling of "a failed read is None,
    never 0").
    """
    if ready is True:
        return "[bold $success]ready[/]"
    if ready is False:
        return "[bold]not yet[/]"
    return "[dim]unknown[/]"


def _fmt_total(value: object) -> str:
    """Exact, comma-grouped -- the headline cumulative figure, unlike the
    compact ``fmt_compact`` used for the smaller/faster-moving accrued,
    staged and min-bridge amounts.  Mirrors ``hero.py``'s own non-short-tier
    ``cum_line`` (``f"burned {cum:,.0f} observed"``), which draws the same
    distinction for the same reason.
    """
    v = as_float(value)
    if v is None:
        return DASH
    return f"{v:,.0f}"


def _pipeline_lines(
    burn_accrued, burn_staged, burn_min_bridge, burn_ready, burned_total,
    as_of_hhmm, burn_bridgeable=None,
) -> list[str]:
    # `fmt_imd`, not `fmt_compact`: this pipeline sits below 1 IMD for the
    # minutes after every sweep and the house helper renders all of that as
    # `0`. See `_fmt.fmt_imd`.
    acc = fmt_imd(burn_accrued)
    stg = fmt_imd(burn_staged)
    min_b = fmt_imd(burn_min_bridge)
    burned = _fmt_total(burned_total)

    # The quantity behind the status word, on the same line as the word:
    # `previewBridge()` already clamped it to the executor's balance, the
    # OFT's limits and its dust, so it is what a call would move right now.
    # `accrued` below is the *hook's* and moves the other way -- a sweep
    # empties one and fills the other.
    sendable = as_float(burn_bridgeable)
    status = _ready_word(burn_ready)
    if sendable is not None:
        status = f"{status} · {fmt_imd(sendable)} IMD"

    lines = [
        f"[dim]{BURN_TITLE}[/]",
        # A blank line under the title. The rail's panels sat flush against
        # their own headings and read as one block of text; this is the same
        # breathing room `SurfDevActivity`'s `.surf-activity-spacer` Static
        # gives its own log, spent as a row rather than a widget because
        # these panels are one `Static` each.
        "",
        f"status: {status}",
        f"[dim]accrued {acc} IMD · staged {stg} IMD[/]",
        f"[dim]min bridge {min_b} IMD[/]",
        f"[dim]burned {burned} IMD (all-time)[/]",
    ]
    if as_of_hhmm:
        lines.append(f"[dim]as of {safe_markup(str(as_of_hhmm))}[/]")
    return lines


class SurfBurnPipeline(Vertical):
    """The permissionless bridge-and-burn executor's own state.

    Read-only (CLAUDE.md hard constraint 1 -- no signer, no transactor, no
    calldata construction anywhere in this repo): this panel *displays*
    that ``bridgeToBaseBurnReceiver()`` is callable by anyone; it never
    offers to call it, never builds calldata, and never quotes gas for the
    purpose of sending.  See the module docstring and ``hero.py``'s BURN
    box for the same framing applied to the same executor.
    """

    DEFAULT_CSS = """
    SurfBurnPipeline {
        height: auto;
    }
    SurfBurnPipeline > Static {
        width: 100%;
        padding: 0 1;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(f"[dim]{BURN_TITLE}[/]", id="surf-burn-body")

    def update_data(
        self,
        burn_accrued=None,
        burn_staged=None,
        burn_ready=None,
        burn_min_bridge=None,
        burn_bridgeable=None,
        burned_total=None,
        as_of_hhmm=None,
        **_kwargs,
    ) -> None:
        """Refresh the panel.

        ``**_kwargs`` swallows any keyword a caller passes that this
        signature does not name -- ``burn_events`` in particular has no
        ``SURF_KEYS`` home: no sweep counts individual burn events, only
        the cumulative ``launchpad_burned_total`` (this widget's
        ``burned_total``), so it is accepted and silently ignored rather
        than raising, the same contract ``SurfHero.update_data`` documents
        for its own un-rewired callers.
        """
        lines = _pipeline_lines(
            burn_accrued, burn_staged, burn_min_bridge, burn_ready,
            burned_total, as_of_hhmm, burn_bridgeable,
        )
        try:
            self.query_one("#surf-burn-body", Static).update("\n".join(lines))
        except Exception:  # not composed yet
            pass
