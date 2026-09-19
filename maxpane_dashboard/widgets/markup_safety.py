"""Escaping helpers for third-party text rendered through Rich markup.

Textual's ``DataTable`` does **not** parse markup when you call ``add_row``.
It stores the raw ``str`` and defers ``Text.from_markup`` to
``_on_idle -> _update_dimensions -> default_cell_formatter``. A cell value
containing invalid markup (e.g. a player-chosen name like ``"[/x] Bakers"``)
therefore raises ``rich.errors.MarkupError`` *inside the message pump*, well
outside any ``try/except`` around the refresh call that added the row --
which crashes the whole app, on every refresh.

Every string that originates from an HTTP API, an onchain string field, or
any other party's keyboard must go through :func:`safe_markup` before it is
interpolated into a markup string or handed to ``add_row`` / ``Static.update``.

Use :func:`safe_markup` for the value; keep the markup tags around it::

    name = safe_markup(bakery.name)
    table.add_row(f"[bold]{name}[/]", ...)

**The strip-then-clip-then-escape sanitiser** (``TAG_LIKE``, :func:`flatten`,
:func:`strip_tags`, :func:`sanitize_cell`) was declared four times in
``widgets/surf/`` (``launchpad.py``, ``launchpad_activity.py``,
``burnkeepers.py``, ``_pool4.py``) before it was hoisted here
(``docs/refactor_programme_2026_09.md``, Branch 2 / HANDOVER.md §3.2): a
ticker, a coin name or a wallet's free-text label is attacker-chosen
(``LaunchpadFactory.launch(string,string)`` is permissionless and costs only
gas), so every one of those callers needed the same three-step defence and
had each grown its own copy of it. :func:`sanitize_cell` is that defence,
in the fixed order ``flatten -> strip_tags -> clip -> safe_markup`` -- see
its own docstring for why the order does not commute.
"""

from __future__ import annotations

import re

from rich.markup import escape

from maxpane_dashboard.widgets import rowfit

__all__ = [
    "TAG_LIKE",
    "flatten",
    "safe_markup",
    "sanitize_cell",
    "strip_tags",
    "visible_len",
]

#: Matches a Rich/Textual markup tag, so a line can be measured as the user
#: sees it rather than as it is written.
_MARKUP_TAG = re.compile(r"\[/?[^\[\]]*\]")

#: A complete ``[...]`` bracket run with no nested bracket -- catches both a
#: well-formed style tag (``[bold red]``) and a bare closing tag (``[/x]``).
#: Deliberately *not* anchored to Rich's own tag grammar: none of this
#: sanitiser's callers (a launchpad ticker/coin name, a burnkeeper wallet
#: label) has a legitimate use for a literal square bracket at all, so every
#: complete pair is dropped rather than only the ones that would parse.
#: A private module-level constant of this same shape and name (with a
#: leading underscore) used to be declared identically four times, in
#: ``launchpad.py``, ``launchpad_activity.py``, ``burnkeepers.py`` and
#: ``_pool4.py``; this is the hoisted single definition.
TAG_LIKE = re.compile(r"\[[^\[\]]*\]")


def visible_len(markup: str | None) -> int:
    """Rendered width of *markup*, i.e. its length with the tags removed.

    Any widget that decides whether a line fits has to measure it this way --
    ``len("[bold]ODDS BOARD[/]")`` is 19 where the user sees 10, so measuring
    the raw string silently truncates content that would have fitted.

    Lives here rather than in each widget: this was already copied verbatim
    into ``fwa_signals`` and ``fwa_settlement_table``, and a third copy was
    about to be written for the odds board title.
    """
    return len(_MARKUP_TAG.sub("", markup or ""))


def safe_markup(value: object) -> str:
    """Return ``value`` as a string that Rich will render literally.

    ``None`` becomes an empty string; everything else is coerced with
    ``str()`` and then escaped so square brackets are shown rather than
    parsed as markup tags.
    """
    if value is None:
        return ""
    return escape(str(value))


def flatten(value: object) -> str:
    """Collapse embedded newlines/control whitespace to single spaces.

    On-chain strings can contain raw newlines the same way an announce-
    channel post can, and this has to run before both :func:`strip_tags` and
    a caller's own truncation so neither operates on a string that still has
    embedded line breaks in it. ``None`` becomes ``""``; anything else is
    coerced with ``str()`` inside its own ``try`` so an object whose
    ``__str__`` raises degrades to the empty string rather than taking the
    caller down with it -- the same "a single malformed value must never
    crash the panel" rule every calling widget already holds itself to.
    """
    if value is None:
        return ""
    try:
        text = str(value)
    except Exception:
        return ""
    return " ".join(text.split())


def strip_tags(value: object) -> str:
    """Flatten, then strip complete ``[...]``-shaped bracket runs outright.

    Rather than merely escaping them: a ticker, a coin name or a wallet's
    free-text label has no legitimate use for a literal square bracket, and
    an *escaped* ``[/x]`` still renders as the literal text ``[/x]`` once
    Rich's parser unescapes it for display -- escaping alone stops a crash,
    not the tag characters showing up on screen. Never raises: see
    :func:`flatten`.
    """
    flat = flatten(value)
    stripped = TAG_LIKE.sub("", flat)
    return " ".join(stripped.split())


def sanitize_cell(value: object, width: int) -> str:
    """Flatten, strip bracket-tag-shaped noise, clip to ``width`` cells,
    escape -- in that fixed order, never raising.

    The order matters and does not commute:

    1. :func:`flatten` and :func:`strip_tags` remove hostile bracket-shaped
       noise before anything else touches the string;
    2. :func:`~maxpane_dashboard.widgets.rowfit.clip` truncates the
       *already-stripped, still-unescaped* text to ``width`` **terminal
       cells** (``rich.cells.cell_len``, never ``len()``): a ticker, a coin
       name or a counterparty label is third-party text, and eight CJK
       characters are sixteen columns -- a ``len()``-sized clip is then eight
       columns wider than the budget it was checked against, and the
       overflow comes off the end of the line unannounced;
    3. :func:`safe_markup` escapes what is left, **last**, so a clip can
       never bisect an escape pair (clip before escape, always).

    ``safe_markup`` still runs unconditionally at the end as the actual
    crash-safety net for anything step 1 does not catch. :data:`TAG_LIKE`'s
    ``.sub`` is a single left-to-right pass, so a *nested* bracket run can
    make it delete an inner pair and leave the outer fragments sitting next
    to each other, reconstructing a hostile tag it never matched as such:
    ``"[[inner]/word]"`` strips to ``"[/word]"`` -- a closing tag with no
    open tag to match, which raises ``rich.errors.MarkupError`` when parsed
    unescaped. (A genuinely bare, unmatched ``[`` with nothing after it is
    not this case: verified empirically against this repo's live Rich
    version, ``Text.from_markup`` never raises on that shape alone -- it
    renders as literal text regardless of escaping -- so it is the
    reconstruction case above, not a plain lone ``[``, that this step
    exists to catch.) Mutation-proof note: removing this final
    ``safe_markup`` call does not turn a plain bracket-run fixture red (step
    1 already removed every complete, un-nested ``[...]`` pair before
    ``safe_markup`` would ever run on it), but it does turn a
    nested-bracket-reconstruction fixture red, because that is the one
    shape only the escape step catches.
    """
    return safe_markup(rowfit.clip(strip_tags(value), width))
