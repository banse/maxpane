"""SIGNALS: four states a reader changes behaviour on, in label/value columns.

``templates/signals_template.py``'s shape with its last line **deleted**. The
template ends on a **recommendation** -- ``→ Recommendation: BUY`` -- which is
fine for a cookie game and is something else entirely on a market panel. This
repo ships a strictly read-only tool that never signs and never quotes a trade,
so a bottom-line verdict would be the first thing on screen that reads as
advice (PRD §8.4).

What replaced it until 2026-09-12 was a **state summary** -- the same four
rows flattened into one descriptive sentence. It was dropped in the
screenshot-review pass, and the reason is worth keeping because it is not the
reason it was written for. PRD §8.4's constraint was that nothing here may
read as advice, and that constraint is now held by
``test_no_reachable_state_of_this_panel_gives_advice``, which greps the
**whole composited panel** in five payload states -- a strictly stronger guard
than one aimed at a single line, and one that does not depend on that line
existing. What the summary had left to offer after that was a restatement of
three of the four rows immediately above it, and once those rows were laid out
in a label column it was also the one ragged line in a panel whose whole point
had become that a reader's eye runs down a single column. It cost a row of
``SURF_POOL4_USER_FULL_LAYOUT_ROWS`` for that.

**This is a deliberate deviation from PRD §6.3**, which specifies "four rows
and a flat state summary line beneath". Recorded here rather than quietly:
if the summary comes back, it comes back as a line that says something the
rows do not.

The four rows, and why each earns a line (PRD §6.3)
---------------------------------------------------
``burning``
    ``ON · headroom 0`` / ``OFF · headroom N`` / ``unknown``. **Three states,
    asserted as three.** ``pool4_cap_headroom`` is ``inventoryCap -
    tokensInPool``: at zero the cap binds and every net sell into the hook is
    burned rather than pooled. ``None`` is "we could not read the cap", which
    is not ``OFF`` -- a checker that compares only the ``None`` word is a
    logged defect in this repo, which is why :func:`burning_state` returns a
    word from a closed vocabulary rather than a bool.

``cheaper pool``
    ``REFERENCE −1.50%`` / ``HERE −1.50%`` / :data:`NO_EDGE` / ``unknown``.
    The venue word is only named once the gap clears the two pools' fees summed
    -- the producer does that gating and publishes ``pool4_cheaper_venue`` as
    ``None`` when it does not clear (PRD §8.3). Below that threshold the gap is
    not arbitrageable, and naming a venue over it would be telling a reader to
    lose the spread.

    **The sign is fixed and the magnitude is what varies.** ``−`` here means
    "that much cheaper *on the named venue*", never the payload's own
    orientation (``pool4_venue_gap_pct`` is signed ``+ = IMD dearer here``).
    Rendering the payload's sign beside a venue word is a double negative a
    reader has to unpick, and the venue word already carries the direction.

    At the full tier the row also carries the **two ticks the verdict was
    derived from**, ``pool4_current_tick`` and ``pool4_reference_pool_tick``.
    That is disclosure, not decoration: PRD §8.3 records a live contradiction
    between two implementations of this gap that is *unresolved*, and a verdict
    whose inputs are on screen beside it is one a reader can check. It is the
    same instinct as THE SPLIT putting its drift line above the shares it
    reconciles.

``backstop``
    ``0.84% under · 24.51 ETH`` / :data:`NO_BAND` / ``unknown``. Is there a bid
    under me. The distance comes from
    :func:`~maxpane_dashboard.analytics.surf_pool4_depth.band_distance_pct` --
    **imported, not derived here**, and the same function the hero's DOWNSIDE
    BID card calls, so the two surfaces cannot print different numbers for one
    fact (carry-over C1).

    PRD §6.3 also lists *share used* on this row and it is deliberately absent.
    How much of the band a fall consumes is a function of how far the fall goes,
    which is precisely what IF IMD FALLS' ``band used`` column tabulates one
    panel over. A single summarised copy of it here would be a second number
    for one quantity, free to disagree with the table; one number, one place.

``drip backlog``
    ``none`` / ``deep · 3.2d`` / ``unknown``. The only dripper internal that
    earns screen space, and only for one reason: it says whether STAKING's
    trailing return **understates**. sIMD yield is rate-limited, not
    flow-limited, so IMD sitting in the dripper is return the last seven days
    did not contain and the next seven may.

Shared primitives, purity and the ``$`` trap
--------------------------------------------
Title, network word and widen marker come from ``widgets/surf/_pool4.py``;
``clip``/``pad`` from ``widgets/surf/_rowfit.py``, both on
:func:`rich.cells.cell_len` and never ``len()``. No ``data/``, no clock, no
I/O; the one ``analytics/`` import is stdlib-only and is named on
``test_surf_widget_contract._PURE_ANALYTICS_ALLOWED``, whose purity walk
recurses through that module's own imports to a fixed point.

Every line reaches ``Static`` as a pre-built ``rich.text.Text``, parsed inside
``_pool4.parse_line``'s own ``try``: ``Static.update("…[/x]…")`` parses nothing
at call time, and the deferred failure raises in the message pump outside this
module's ``try``. And Rich cannot resolve Textual's ``$``-prefixed theme
variables -- such a token parses cleanly and raises ``MissingStyle`` at render
time, inside ``Static.update`` -- so the styles here are Rich colour names only.
"""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from maxpane_dashboard.analytics.surf_pool4_depth import band_distance_pct
from maxpane_dashboard.widgets.markup_safety import safe_markup
from maxpane_dashboard.widgets.surf._fmt import DASH, as_float
from maxpane_dashboard.widgets.surf._pool4 import (
    TITLE_CLASS,
    join_lines,
    market_title_text,
    parse_line,
    strip_tags,
    widest_line,
)
from maxpane_dashboard.widgets.surf._rowfit import pad

__all__ = [
    "BURNING_OFF",
    "BURNING_ON",
    "COMPACT_WIDTH",
    "DEEP_BACKLOG_DAYS",
    "FULL_WIDTH",
    "LABEL_COLS",
    "NO_BACKLOG",
    "NO_BAND",
    "NO_EDGE",
    "ROW_LABELS",
    "TITLE",
    "UNAVAILABLE_LINE",
    "UNKNOWN",
    "VENUE_WORDS",
    "SurfPool4USignals",
    "backlog_cell",
    "backstop_cell",
    "burning_cell",
    "burning_state",
    "venue_cell",
]

TITLE = "SIGNALS"

#: Not one of this panel's four inputs was read. Rendered in place of the rows
#: rather than as four repetitions of :data:`UNKNOWN`, which would fill the
#: panel with a word that means the same thing four times.
UNAVAILABLE_LINE = "signals unavailable"

#: What a single row says when *its own* input was not read. A distinct word
#: from every state below, so "we could not look" is never paintable by a state
#: we did look at -- the curator rail bug, where a dead group's ``-- unknown``
#: and a genuine ``none yet`` both read confident and green.
UNKNOWN = "unknown"

BURNING_ON = "ON"
BURNING_OFF = "OFF"

#: The cheaper-pool row when the gap was read and does **not** clear the two
#: pools' fees summed, so the producer published no venue word (PRD §8.3).
#:
#: Deliberately the same *claim* as ``pool4u_hero.NO_VENUE_EDGE`` and
#: deliberately a shorter spelling of it: the hero card has a subtitle line of
#: its own to fill and this is a value cell whose label already says ``cheaper
#: pool``. Neither contains a venue word, which is the half §8.3 actually
#: constrains -- the panel may say an edge does not exist, never which side it
#: would have been on. ``test_the_two_no_edge_spellings_make_the_same_claim``
#: imports both and pins that.
NO_EDGE = "no edge"

#: ``pool4_backstop_state == "none"``: we looked and there is no band. **The
#: same spelling as ``pool4u_hero.NO_BAND``, and that is the point** -- one
#: state worded two ways across two panels of one body is the divergence this
#: body's shared module exists to prevent. Restated rather than imported (a
#: widget importing a sibling widget's copy is a coupling, not a hoist) with an
#: agreement test that compares the two in both directions.
NO_BAND = "none deployed"

#: ``pool4_backlog_days == 0``: the dripper holds nothing, so the trailing
#: return is the whole story. A representable zero, never :data:`UNKNOWN`.
NO_BACKLOG = "none"

#: Above this, the backlog is called ``deep`` rather than printed as a bare
#: number. One day, because the drip is rate-limited: a backlog under a day is
#: inside the noise of when the last ``drip()`` happened, and above it there is
#: undelivered IMD that the trailing-7d figure structurally could not contain.
#: A word rather than only a number because the row exists to answer one
#: yes/no question -- *does STAKING understate?* -- and a reader should not have
#: to hold a threshold in their head to answer it.
DEEP_BACKLOG_DAYS = 1.0

#: ``surf_models.POOL4_VENUE_WORDS`` restated, because a widget may not import
#: ``data/``. Redundancy plus an agreement test is the shape this repo mandates;
#: a third venue word reddens the suite rather than falling through this
#: module's ``else`` and rendering as an unread gap.
VENUE_WORDS: tuple[str, ...] = ("here", "reference")

#: The four row labels, in render order. A tuple rather than four constants so
#: a test can assert the panel paints exactly these four and in this order --
#: the order is the reading order PRD §6.3 sets out, cheapest decision first.
ROW_LABELS: tuple[str, ...] = (
    "burning",
    "cheaper pool",
    "backstop",
    "drip backlog",
)

_BODY_ID = "surf-pool4u-signals-body"
_TITLE_ID = "surf-pool4u-signals-title"

#: The label column, in **terminal cells**: ``drip backlog`` and ``cheaper
#: pool`` are twelve, plus one so no value ever abuts its label.
LABEL_COLS = 13

#: Widest full-tier value cell, measured against the widest thing each row can
#: hold rather than against today's data:
#:
#: * burning -- ``OFF · headroom 999,999`` (23);
#: * cheaper pool -- ``REFERENCE −99.99%  887272/887272`` (33);
#: * backstop -- ``99.99% under · 999.99 ETH`` (25);
#: * drip backlog -- ``deep · 999.9d · return understates`` (34).
_VALUE_COLS = 34

#: Widest full-tier row. The tier decision below still measures what was
#: actually built rather than comparing the budget against this constant: the
#: value cells are data-dependent, so a marker keyed off ``budget <
#: FULL_WIDTH`` would stay dark while an unusually wide row was clipped by CSS
#: in silence. This pin is what the rows are laid out to, and a test compares
#: it against composited output with ``==`` so it reddens in both directions.
FULL_WIDTH = LABEL_COLS + _VALUE_COLS

#: One tier down. What is shed, in order, and what is not:
#:
#: * the cheaper-pool row's tick tail -- it is evidence for a verdict that is
#:   still fully rendered above it;
#: * the backstop row's ETH -- the hero's DOWNSIDE BID card carries it with
#:   room to spare, and *distance* is the half this row exists for;
#: * ``headroom`` shortens to ``hr`` and the backlog's ``return understates``
#:   clause goes.
#:
#: **The four rows themselves never go.** A signals panel that sheds a signal
#: has not got narrower, it has started lying by omission -- and the state
#: that would be dropped is exactly as likely to be the one that mattered.
COMPACT_WIDTH = LABEL_COLS + 21


def burning_state(cap_headroom) -> str | None:
    """``BURNING_ON`` / ``BURNING_OFF`` / ``None`` -- three, never a bool.

    ``None`` means the cap could not be read and is returned as ``None`` rather
    than as ``False`` precisely so the caller cannot collapse it into ``OFF``.
    PRD §7.4 names this as the separation that must hold.

    Zero headroom is **ON**: ``pool4_cap_headroom`` is ``inventoryCap -
    tokensInPool``, so at zero the cap binds and net flow into the hook is
    retired instead of pooled. A negative is real (inventory above the cap) and
    is also ON.
    """
    value = as_float(cap_headroom)
    if value is None:
        return None
    return BURNING_ON if value <= 0.0 else BURNING_OFF


def _fmt_imd_amount(value) -> str:
    """A headroom figure, grouped, at whole-IMD precision.

    Grouped rather than compacted below a million: ``headroom 1,240`` and
    ``headroom 1.2K`` are the same number, and only the first lets a reader see
    it move between polls, which on the row that says whether the hook is
    burning is the whole point.
    """
    v = as_float(value)
    if v is None:
        return DASH
    return f"{v:,.0f}"


def burning_cell(cap_headroom, tier: str = "full") -> tuple[str, str]:
    """``("ON · headroom 0", "green")`` -- the value and its Rich colour."""
    state = burning_state(cap_headroom)
    if state is None:
        return UNKNOWN, "dim"
    word = "headroom" if tier == "full" else "hr"
    cell = f"{state} · {word} {_fmt_imd_amount(cap_headroom)}"
    return cell, ("green" if state == BURNING_ON else "dim")


def venue_cell(cheaper_venue, venue_gap_pct, hook_tick, reference_tick,
               tier: str = "full") -> tuple[str, str]:
    """The cross-venue verdict, and at the full tier the ticks behind it.

    Four states and they are four different sentences:

    * a venue word plus the magnitude, once the producer's fee gate passed;
    * :data:`NO_EDGE` -- read, and below the two pools' fees summed;
    * :data:`UNKNOWN` -- the gap itself was not read;
    * an unrecognised venue word falls to :data:`UNKNOWN` rather than being
      laundered into a title, on ``_pool4.network_word``'s allowlist rule.
    """
    word = strip_tags(cheaper_venue)
    gap = as_float(venue_gap_pct)
    if word in VENUE_WORDS and gap is not None:
        cell, style = f"{word.upper()} −{abs(gap):.2f}%", "cyan"
    elif gap is None:
        cell, style = UNKNOWN, "dim"
    else:
        cell, style = NO_EDGE, "dim"

    if tier == "full":
        here = as_float(hook_tick)
        there = as_float(reference_tick)
        if here is not None and there is not None:
            cell = f"{cell}  {int(here)}/{int(there)}"
    return cell, style


def backstop_cell(backstop_state, tick_now, band_lower_tick, backstop_eth,
                  tier: str = "full") -> tuple[str, str]:
    """Distance under spot and the ETH standing there; three states.

    Branches on ``pool4_backstop_state`` and on nothing else. Reading
    ``backstop_eth is None`` instead would make an unread amount
    indistinguishable from a band that genuinely is not deployed, and a
    deployed band whose amount failed to read would claim there is no bid under
    the reader at all.
    """
    word = strip_tags(backstop_state)
    if word == "none":
        return NO_BAND, "yellow"
    if word != "deployed":
        return UNKNOWN, "dim"

    distance = band_distance_pct(tick_now, band_lower_tick)
    shown = f"{distance:.2f}% under" if distance is not None else f"{DASH} under"
    if tier != "full":
        return shown, "green"
    eth = as_float(backstop_eth)
    eth_shown = f"{eth:,.2f} ETH" if eth is not None else f"{DASH} ETH"
    return f"{shown} · {eth_shown}", "green"


def backlog_cell(backlog_days, tier: str = "full") -> tuple[str, str]:
    """``none`` / ``deep · 3.2d`` / ``unknown`` -- does STAKING understate?

    ``0`` is a representable answer and renders :data:`NO_BACKLOG`; only an
    unread backlog reaches :data:`UNKNOWN`. ``pool4_backlog_days`` is already
    ``None`` on a zero or unread drip rate rather than an infinity, so nothing
    here has to defend against one.
    """
    days = as_float(backlog_days)
    if days is None:
        return UNKNOWN, "dim"
    if days <= 0.0:
        return NO_BACKLOG, "dim"
    if days < DEEP_BACKLOG_DAYS:
        return f"{days:.1f}d", "dim"
    cell = f"deep · {days:.1f}d"
    if tier == "full":
        cell = f"{cell} · return understates"
    return cell, "yellow"


class SurfPool4USignals(Vertical):
    """SIGNALS: four market states in one label column, and nothing else."""

    DEFAULT_CSS = """
    SurfPool4USignals {
        height: auto;
    }
    SurfPool4USignals > Static {
        width: 100%;
        padding: 0 1;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    SurfPool4USignals > .pool4u-title {
        margin: 0 0 1 0;
    }
    """

    #: ``> Static``'s own ``padding: 0 1`` eats a column each side of the
    #: child's content box, so a fit decision compares against
    #: ``self.size.width`` minus two, never ``self.size.width``. The same
    #: number, for the same reason, as ``SurfPool4UBurn``'s.
    _TITLE_PADDING_COLS = 2

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # The raw payload, not formatted lines, so a resize re-lays it out.
        self._payload: dict = {}
        self._widen = False

    def compose(self) -> ComposeResult:
        yield Static(Text(TITLE, style="dim"), id=_TITLE_ID,
                     classes=TITLE_CLASS)
        yield Static(Text(""), id=_BODY_ID)

    def on_resize(self, _event=None) -> None:
        if self._payload:
            self._render_view()

    def update_data(
        self,
        pool4_cap_headroom=None,
        pool4_cheaper_venue=None,
        pool4_venue_gap_pct=None,
        pool4_reference_pool_tick=None,
        pool4_current_tick=None,
        pool4_backstop_state=None,
        pool4_backstop_lower_tick=None,
        pool4_backstop_eth=None,
        pool4_backlog_days=None,
        pool4_network=None,
        pool4_as_of_hhmm=None,
        **_kwargs,
    ) -> None:
        """Refresh the panel from the manager's flat dict.

        Every kwarg carries its full ``pool4_`` contract prefix and every one is
        a member of ``SURF_KEYS``; no pool4 panel takes the launchpad trio's
        ``as_of_hhmm`` elision, which is a carve-out for one name on one body.

        ``**_kwargs`` is mandatory: the screen splats the whole payload, so a
        key added tomorrow must be ignored rather than raise.

        **``pool4_as_of_hhmm`` is accepted and not rendered** (2026-09-12).
        The ``4`` MARKET body prints one ``as of`` marker, on the screen's own
        title row, and no panel repeats it -- see ``_pool4``'s *One clock on
        the `4` body* section for the whole of that decision, and for the one
        panel it does not settle.
        The kwarg stays in the signature because every pool4 panel spells
        every contract key in full (``test_no_pool4_widget_needs_a_kwarg_
        alias``), and dropping it would leave the screen's splat handing it to
        ``**_kwargs`` with nothing recording why.
        """
        self._payload = {
            "cap_headroom": pool4_cap_headroom,
            "cheaper_venue": pool4_cheaper_venue,
            "venue_gap_pct": pool4_venue_gap_pct,
            "reference_tick": pool4_reference_pool_tick,
            "current_tick": pool4_current_tick,
            "backstop_state": pool4_backstop_state,
            "backstop_lower_tick": pool4_backstop_lower_tick,
            "backstop_eth": pool4_backstop_eth,
            "backlog_days": pool4_backlog_days,
            "network": pool4_network,
            "seen": True,
        }
        self._render_view()

    def _text_budget(self) -> int:
        return max(self.size.width - self._TITLE_PADDING_COLS, 0)

    def _title_text(self) -> str:
        """``market_title_text``, not ``title_text``: this is the ``4`` body.

        The one difference is that ``MAINNET`` is left unsaid here while the
        ``p`` body's four panels go on printing it -- see
        ``_pool4.QUIET_NETWORK`` for why silence is available for exactly one
        network and for nothing else.
        """
        return market_title_text(
            TITLE, self._payload.get("network"), self._widen, self._text_budget()
        )

    def _is_blank(self) -> bool:
        """True when not one of this panel's four inputs has been read.

        The backstop counts as read when its *state word* is present even if
        every number beside it is ``None`` -- ``none deployed`` is an answer.
        """
        payload = self._payload
        if strip_tags(payload.get("backstop_state")):
            return False
        return all(
            payload.get(name) is None
            for name in ("cap_headroom", "cheaper_venue", "venue_gap_pct",
                         "current_tick", "backlog_days")
        )

    def _cells(self, tier: str) -> list[tuple[str, str, str]]:
        """``(label, value, style)`` for the four rows, in render order."""
        payload = self._payload
        burning = burning_cell(payload.get("cap_headroom"), tier)
        venue = venue_cell(
            payload.get("cheaper_venue"),
            payload.get("venue_gap_pct"),
            payload.get("current_tick"),
            payload.get("reference_tick"),
            tier,
        )
        backstop = backstop_cell(
            payload.get("backstop_state"),
            payload.get("current_tick"),
            payload.get("backstop_lower_tick"),
            payload.get("backstop_eth"),
            tier,
        )
        backlog = backlog_cell(payload.get("backlog_days"), tier)
        return [
            (label, cell, style)
            for label, (cell, style) in zip(
                ROW_LABELS, (burning, venue, backstop, backlog)
            )
        ]

    def _content_lines(self, tier: str) -> list[Text]:
        markup: list[str] = []
        for label, cell, style in self._cells(tier):
            # Pad raw and escape after: ``pad`` measures terminal cells and an
            # escaped ``\\[`` is two characters for one cell, so escaping first
            # misaligns the column.
            markup.append(
                f"[dim]{safe_markup(pad(label, LABEL_COLS))}[/]"
                f"[{style}]{safe_markup(cell)}[/]"
            )
        return [t for t in (parse_line(m) for m in markup) if t is not None]

    def _render_view(self) -> None:
        try:
            title = self.query_one(f"#{_TITLE_ID}", Static)
            body = self.query_one(f"#{_BODY_ID}", Static)
        except Exception:  # not composed yet
            return

        def paint(*content: Text) -> None:
            """Title into its own ``Static``, content into the body's.

            Two ``Static``s and not one joined ``Text``: the blank row under
            the title is CSS (``margin: 0 0 1 0`` on :data:`TITLE_CLASS`),
            the repo-wide convention every reference dashboard already
            carries. A ``Text("")`` spliced between them would paint the same
            pixels today and would be invisible to the rule that keeps the
            eight other dashboards agreeing with each other.
            """
            title.update(Text(self._title_text(), style="dim"))
            body.update(join_lines(list(content)))

        if not self._payload:
            self._widen = False
            paint()
            return

        if self._is_blank():
            self._widen = False
            paint(Text(f"⚠ {UNAVAILABLE_LINE}", style="yellow"))
            return

        # Measure what was actually built rather than comparing the budget
        # against FULL_WIDTH: every value cell is data-dependent, so a marker
        # keyed off the constant would stay dark while CSS clipped a row in
        # silence.
        budget = self._text_budget()
        content = self._content_lines("full")
        if budget and widest_line(content) > budget:
            self._widen = True
            content = self._content_lines("compact")
        else:
            self._widen = False

        paint(*content)
