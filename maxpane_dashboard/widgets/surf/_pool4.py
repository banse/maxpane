"""Shared primitives for the POOL4 body's panels (four since POOL4 FLOW left it on 2026-09-14).

**Why this module exists.** WP4 and WP5 independently wrote the same title
helper with *different semantics on unknown input* -- one allowlisted against
``POOL4_NETWORKS``, the other passed the string through. Together those were a
defect, not two opinions: one pool4 body could paint ``THE SPLIT · —`` beside
``THE RATCHET · BASE``, five panels disagreeing about which chain the numbers
above them came from, which is plan §5 R4 exactly. Amendment A13 ruled for the
allowlist and for **one implementation**, and this is it.

The allowlist, and why the objection to it is answered
------------------------------------------------------
The network word is each panel's **claim about the provenance of its own
numbers**, on a view that exists to render testnet data before mainnet exists.
``—`` says "cannot stand behind this label", which is honest; ``BASE`` derived
from an unrecognised string is a confident provenance claim nothing supports.

The standing objection -- that an allowlist blanks every title the day a third
network is added -- is real, and it is answered by the repo's own pattern
rather than by loosening the gate: :data:`NETWORK_WORDS` is a restatement of
``surf_models.POOL4_NETWORKS`` (a closed vocabulary, amendment A5), and
``tests/widgets/test_surf_pool4_shared.py`` imports both and asserts they
agree **in both directions**. So a third network reddens the suite until it is
added here, exactly the way ``_GAME_CYCLE`` and the ``--game`` choices are
kept honest. A pass-through has no such tripwire: it renders a typo'd network
word forever, in silence.

**The tuple is restated here rather than imported** because a pool4 widget may
not import ``data/`` (contract §0.5), and because redundancy-plus-an-agreement-
test is the shape this repo mandates -- deriving one from the other would make
the agreement test compare a constant against itself. WP5's ``pool4_flow.py``
established that shape for this same tuple and it is kept.

What is here and what is not
----------------------------
Here: what more than one panel renders -- the title and its network word, the
two widen-marker spellings and the fitter that chooses between them, the
markup-escaping and ``Text``-building helpers every panel funnels its lines
through, and the line-width measurement the tier decisions share.

**Two title functions, one fitter (2026-09-12).** The ``p`` auditor body calls
:func:`panel_title` and prints the network word on all five of its titles; the
``4`` market body calls :func:`market_panel_title`, which leaves
:data:`QUIET_NETWORK` unsaid and prints everything else. Two functions rather
than a flag, because the two bodies want two different answers for one input
and a shared default is a thing a body can forget to pass. The marker-fitting
half is *not* duplicated -- both go through ``_with_hint`` -- which is this
module's own founding lesson applied to its own growth.

One clock on the `4` body
-------------------------
**The ``4`` MARKET body prints exactly one ``as of`` marker, on the screen's
own title row.** Its five panels each carried their own until 2026-09-12; the
owner read the live screen and asked for all of them gone, and they are.

It costs almost nothing to give up, and that was measured rather than assumed.
Four of the five ran on ``pool4_as_of_hhmm`` -- ``TIER_POOL4``'s 600 s clock --
which on the live cache read **15:29 against a 15:33 title bar**. Four minutes
apart is the same clock twice, and four panels saying so is four rows spent
restating the title row.

**STAKERS is the one this does not settle**, and it is why this section exists
rather than a one-line note. Its rows come off ``TIER_POOL4_STAKERS``, a
1800 s tier, and the same live cache had it at **13:52 against that 15:33
title bar** -- an hour and thirty-seven minutes behind. Deleting its marker
alone would leave hour-old rows sitting under a title row that reads *now*,
which is precisely the failure CLAUDE.md's ``as of`` rule exists to prevent.
So that panel keeps a **conditional** signal instead of a timestamp: its
existing footer gains the word ``stale`` when, and only when, the fold is
further behind than healthy operation can put it. See
``pool4u_stakers.STALE_AFTER_S`` for the threshold and its derivation. The
shape is :data:`QUIET_NETWORK`'s -- a word that prints when something is worth
saying and is silent when it is not -- and it spends no row in the ordinary
case, because it rides a line the panel was already painting.

The ``p`` auditor body is untouched: all five of its panels keep their
markers, exactly as they keep their network word.

**Not** here, deliberately: ``FULL_WIDTH`` / ``COMPACT_WIDTH`` / ``TITLE`` /
``UNAVAILABLE_LINE`` (per-panel *measurements* and per-panel copy -- the whole
point of a pin is that it lives beside the code it governs), each panel's
``_TITLE_PADDING_COLS`` (derived from that panel's own ``DEFAULT_CSS``; a
shared copy would keep answering after one panel's CSS diverged, which is
action at a distance of the worst kind), and ``pool4_hatches.window`` (one
caller).

Purity
------
Stdlib, ``rich`` and nothing else, with one named exception:
``widgets/markup_safety.strip_tags`` (Branch 2 of
``docs/refactor_programme_2026_09.md`` hoisted this module's own
``strip_tags`` there and re-exports it here under the same name so its 14
importers are untouched). That module is itself stdlib-plus-``rich`` --
it only additionally imports ``widgets/rowfit``, also pure -- so the
property this section states still holds transitively. No ``data/``, no
``analytics/``, no ``textual``, no clock, no I/O.

The ``$`` trap
--------------
Every pool4 panel parses its own markup with ``rich.text.Text.from_markup``
(CLAUDE.md's pre-built-``Text`` rule) rather than handing ``Static.update()``
a markup *string*. Rich cannot resolve Textual's ``$``-prefixed theme
variables: ``[bold $success]`` parses cleanly and then raises ``MissingStyle``
at **render** time, inside ``Static.update``, i.e. outside the widget's own
``try`` -- it took the app down once during this build. Use a Rich colour name
(``green``, ``cyan``, ``yellow``, ``dim``). ``test_no_pool4_widget_puts_a_
theme_token_inside_its_own_markup`` discovers every pool4 widget module and
enforces it.
"""

from __future__ import annotations

from rich.cells import cell_len
from rich.text import Text

from maxpane_dashboard.widgets.markup_safety import strip_tags

#: ``join_lines`` / ``parse_line`` / ``widest_line`` are spelled with their
#: nouns on purpose. Their first names -- ``body``, ``line``, ``widest`` --
#: shadowed each panel's own ``body = self.query_one(...)`` local the moment
#: they were imported, which turned every render into a ``TypeError``. A
#: helper that is imported into five modules does not get to claim a word
#: those modules already use for something else.
__all__ = [
    "GLYPH_HINT",
    "NETWORK_UNKNOWN",
    "NETWORK_WORDS",
    "QUIET_NETWORK",
    "TITLE_CLASS",
    "TITLE_SEP",
    "WIDEN_HINT",
    "join_lines",
    "market_panel_title",
    "market_title_text",
    "network_word",
    "panel_title",
    "parse_line",
    "strip_tags",
    "title_text",
    "widest_line",
]

#: The two networks a pool4 read can be about -- ``surf_models.POOL4_NETWORKS``
#: restated, because a widget may not import ``data/`` (contract §0.5). A test
#: imports both and asserts they agree in both directions, so this cannot
#: drift; see the module docstring.
NETWORK_WORDS = ("SEPOLIA", "MAINNET")

#: Rendered where the network word would go when there is none to name.
#: ``pool4_network is None`` means no sweep has ever completed -- it does not
#: mean mainnet and it does not mean Sepolia. An em dash rather than the
#: numeric ``--``: a panel *title* never goes networkless, and ``--`` in a
#: title reads as a truncated word.
NETWORK_UNKNOWN = "—"

#: The separator between a panel's name and its network word. Its own constant
#: because it is a **rendered interface string**: WP8's screen tests grep
#: composited output for ``TITLE + TITLE_SEP + word``.
TITLE_SEP = " · "

#: What a pool4 panel appends to its own title when it had to shed a column.
#: The repo-wide spelling (``activity.py``, ``launchpad_activity.py``,
#: ``pool4_flow.py``) -- do not redefine it to mean anything narrower.
WIDEN_HINT = "‹ widen"

#: One tier below :data:`WIDEN_HINT`: the bare marker glyph, for a panel too
#: narrow to say it in words. It exists because a pool4 title carries the
#: network word as well as the panel name, so ``THE RATCHET · SEPOLIA
#: ‹ widen`` genuinely does not fit a narrow rail where a bare
#: ``LAUNCHPAD ACTIVITY  ‹ widen`` would.
#:
#: **Deliberately not called ``SHORT_HINT``.** That name already means
#: ``"‹ widen"`` in three other modules; reusing it for a narrower thing on
#: the same view would make one name stand for two spellings, which is the
#: same class of defect as the network word this module exists to unify.
GLYPH_HINT = "‹"

#: The one network word the ``4`` MARKET body leaves **unsaid** -- and only
#: that body, through :func:`market_panel_title`. The ``p`` auditor body goes
#: on printing it.
#:
#: The request behind it was "mainnet shouldn't be mentioned", and the
#: temptation was to delete the word from the title altogether. That would
#: have thrown away the property the word exists for: this view was built
#: against a live *Sepolia* deployment and still renders it whenever no
#: mainnet hook has been adopted, so a reader must never be able to mistake
#: testnet numbers for real ones. **Silence is therefore only ever available
#: for the default case.** ``SEPOLIA`` still prints, ``—`` (nothing swept, or
#: a network outside :data:`NETWORK_WORDS`) still prints, and the reader who
#: sees no word at all is looking at mainnet -- the one state where the
#: absence of a warning is itself correct.
#:
#: A member of :data:`NETWORK_WORDS` by construction rather than by comment:
#: :func:`market_panel_title` compares against :func:`network_word`'s output,
#: so this constant cannot go quiet on a word the allowlist does not know.
#: ``test_the_quiet_network_is_one_the_allowlist_recognises`` pins that, and
#: is what reddens if this is ever retyped as something the vocabulary
#: dropped.
QUIET_NETWORK = "MAINNET"

#: The class every ``4``-body panel's title ``Static`` carries, so one CSS
#: rule can put the mandatory blank line under it.
#:
#: The blank row under a panel title is a **repo-wide convention** this body
#: missed: ``ActivityFeed > .feed-title``, ``VolumeSparklines >
#: .volspark-title``, ``PriceSparklines > .spark-title``, ``TopMovers >
#: .movers-title``, ``GeckoPools > .gecko-title`` and ``LaunchFeed >
#: .launch-feed-title`` all carry ``margin: 0 0 1 0`` in ``minimal.tcss``.
#: The name is restated in each panel's own ``DEFAULT_CSS`` (a CSS selector
#: is text, not an import), and
#: ``test_every_market_panel_paints_a_blank_row_under_its_title`` asserts the
#: *rendered* consequence against composited output rather than the spelling
#: -- so a panel that carries the class and loses the rule still reddens.
TITLE_CLASS = "pool4u-title"

#: ``strip_tags`` itself is no longer defined here: it is imported from
#: ``widgets/markup_safety`` above (Branch 2 hoist) and re-exported under the
#: same name via ``__all__``, so this module's own 14 importers -- ``from
#: maxpane_dashboard.widgets.surf._pool4 import ... strip_tags`` -- are
#: untouched. See the module docstring's "Purity" section for why importing
#: it does not reopen this module's own stdlib-plus-``rich`` boundary.


def network_word(network: object) -> str:
    """The panel-title word for ``pool4_network``.

    A member of :data:`NETWORK_WORDS` renders as itself; **everything else,
    including ``None``**, renders :data:`NETWORK_UNKNOWN`. Naming a network
    this build has not been taught would assert which chain the numbers above
    it came from, which is the one thing R4 says must never be guessed. See
    the module docstring for why the allowlist has a tripwire and a
    pass-through does not.

    Whitespace and case are normalised before the check -- ``" sepolia "`` is
    the same claim as ``"SEPOLIA"``, spelled sloppily, not an unknown chain.
    """
    if isinstance(network, str):
        word = strip_tags(network).upper()
        if word in NETWORK_WORDS:
            return word
    return NETWORK_UNKNOWN


def panel_title(title: str, network: object) -> str:
    """``THE RATCHET · SEPOLIA`` -- the title every pool4 panel renders.

    Plain text, no markup: the caller styles it. The network word is never
    dropped to save columns; a hint is appended *after* it, and a panel too
    narrow for the whole thing keeps the word and loses the hint rather than
    going networkless.
    """
    return f"{title}{TITLE_SEP}{network_word(network)}"


def market_panel_title(title: str, network: object) -> str:
    """:func:`panel_title` with :data:`QUIET_NETWORK` left unsaid.

    The ``4`` MARKET body's title, and **only** that body's -- the ``p``
    auditor body calls :func:`panel_title` and goes on printing ``· MAINNET``
    on all five of its panels. Two functions rather than a flag on one,
    because the two bodies want two different answers for the same input and
    a shared default would make whichever body forgot to pass the flag print
    the other one's title.

    Everything :func:`network_word` is careful about survives: the word is
    still resolved through the allowlist first, so ``SEPOLIA`` prints,
    anything outside :data:`NETWORK_WORDS` (``None`` included) prints
    :data:`NETWORK_UNKNOWN`, and the *only* input that renders a bare title
    is the one the allowlist itself resolved to :data:`QUIET_NETWORK`. See
    that constant for why silence is available for exactly one network.
    """
    word = network_word(network)
    if word == QUIET_NETWORK:
        return title
    return f"{title}{TITLE_SEP}{word}"


def _with_hint(base: str, widen: bool, budget: int) -> str:
    """Append the longest widen marker that fits *base* within *budget*.

    The body of :func:`title_text`, factored out so
    :func:`market_title_text` cannot acquire a second, subtly different
    fitting rule -- which is the exact failure ``_pool4.py`` exists to have
    fixed once already, one layer up.
    """
    if not widen:
        return base
    for candidate in (WIDEN_HINT, GLYPH_HINT):
        if not budget or cell_len(base) + 2 + cell_len(candidate) <= budget:
            return f"{base}  {candidate}"
    return base


def title_text(title: str, network: object, widen: bool, budget: int) -> str:
    """:func:`panel_title` with the widen marker **appended**, never
    substituted, and never wider than the panel it is marking.

    ``launchpad_activity._set_title``'s contract, adapted to a panel with no
    log to fall back into: the longest hint that fits is placed
    (:data:`WIDEN_HINT`, then :data:`GLYPH_HINT`), and if neither fits **none**
    is placed. A marker that does not fit is a marker CSS eats before the
    reader sees it, so appending it anyway would buy nothing and cost the
    network word beside it -- and at that width the title itself is already
    being clipped, which is a louder signal than any hint.

    ``budget`` of ``0`` means "not laid out yet": the marker is placed
    unconditionally rather than suppressed on a geometry nobody has measured.
    """
    return _with_hint(panel_title(title, network), widen, budget)


def market_title_text(title: str, network: object, widen: bool,
                      budget: int) -> str:
    """:func:`title_text` over :func:`market_panel_title`'s base.

    The ``4`` body's four panels call this and nothing else does. The marker
    rules are :func:`title_text`'s, shared through ``_with_hint``: a bare
    mainnet title is nine cells shorter than the ``p`` body's, so it reaches
    the full ``‹ widen`` spelling at a width where the other body would only
    fit the glyph -- which is a consequence of the shorter title, not a
    second policy.
    """
    return _with_hint(market_panel_title(title, network), widen, budget)


def parse_line(markup: str) -> Text | None:
    """``(markup) -> Text``, parsed here inside its own ``try``.

    ``None`` on a parse failure, so one malformed line is dropped rather than
    reaching ``Static.update()`` as a string and raising inside the message
    pump, outside the screen's ``try/except`` (``SurfFeed._row_text``'s
    pattern). See the module docstring for the ``$``-token half of the same
    trap, which this cannot catch and a test does.
    """
    try:
        return Text.from_markup(markup)
    except Exception:
        return None


def join_lines(lines: list[Text]) -> Text:
    """Join parsed lines with newlines -- ``Text``, never a joined string."""
    return Text("\n").join(lines)


def widest_line(lines: list[Text]) -> int:
    """The widest rendered line, in terminal cells.

    ``Text.cell_len``, never ``len()``: a CJK glyph is one character and two
    cells, and a tier chosen on ``len()`` overflows its budget and hands the
    overflow to CSS ``text-overflow: ellipsis`` to eat in silence.
    """
    return max((text.cell_len for text in lines), default=0)
