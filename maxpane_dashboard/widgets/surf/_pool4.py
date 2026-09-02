"""Shared primitives for the POOL4 body's five panels.

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

**Not** here, deliberately: ``FULL_WIDTH`` / ``COMPACT_WIDTH`` / ``TITLE`` /
``UNAVAILABLE_LINE`` (per-panel *measurements* and per-panel copy -- the whole
point of a pin is that it lives beside the code it governs), each panel's
``_TITLE_PADDING_COLS`` (derived from that panel's own ``DEFAULT_CSS``; a
shared copy would keep answering after one panel's CSS diverged, which is
action at a distance of the worst kind), and ``pool4_hatches.window`` (one
caller).

Purity
------
Stdlib, ``rich`` and nothing else. No ``data/``, no ``analytics/``, no
``textual``, no clock, no I/O.

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

import re

from rich.cells import cell_len
from rich.text import Text

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
    "TITLE_SEP",
    "WIDEN_HINT",
    "join_lines",
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

#: A complete ``[...]`` bracket run with no nested bracket -- ``launchpad.py``'s
#: ``_TAG_LIKE``, which ``burnkeepers.py`` already copies for the same reason:
#: those modules belong to other packages and their private helpers are not a
#: contract to couple to across an ownership seam. This is the pool4 body's
#: single definition.
_TAG_LIKE = re.compile(r"\[[^\[\]]*\]")


def strip_tags(value: object) -> str:
    """Flatten embedded whitespace, then strip complete ``[...]``-shaped runs.

    Stripping, not merely escaping: an *escaped* ``[/x]`` still renders as the
    literal text ``[/x]`` once Rich unescapes it for display, so a hostile
    ``detail`` would still paint bracket noise into a panel. No legitimate
    address, state word or network name contains a bracket run, so this only
    fires on a malformed payload.

    Never raises; ``None`` becomes ``""``.
    """
    if value is None:
        return ""
    try:
        flat = " ".join(str(value).split())
    except Exception:
        return ""
    return " ".join(_TAG_LIKE.sub("", flat).split())


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
    base = panel_title(title, network)
    if not widen:
        return base
    for candidate in (WIDEN_HINT, GLYPH_HINT):
        if not budget or cell_len(base) + 2 + cell_len(candidate) <= budget:
            return f"{base}  {candidate}"
    return base


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
