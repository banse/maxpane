"""Copy icons inside surf text that is fitted *before* it is painted.

``widgets/address.py`` owns every address and every icon; this module owns
nothing of either. It exists for one shape the helper cannot serve on its own:
**third-party prose that a surf panel wraps or cuts to a column budget** -- an
announce post (``feed.py``), a signal detail (``signals.py``), the HATCHES
discovery sentence (``pool4_hatches.py``). ``address_prose`` returns a finished
``Text`` with its icons already inserted, so fitting its result would measure
and cut a string that already carries two cells per address -- and fitting the
raw text first would leave the icons unpaid for, overflowing a
``RichLog(wrap=False)``/``nowrap`` line by two cells per address with nothing
on screen saying so.

So the work is split in two, around whatever fitting the panel already does:

1. :func:`mark_addresses` puts each icon into the *plain* text first -- after
   stripping any ``⧉`` the third party typed themselves -- so every width
   calculation downstream pays for it without knowing it exists;
2. :func:`link_prose` / :func:`link_in_order` then attach the copy action to
   the glyphs that survived the fit, reusing the helper's own icon style.

A glyph cut off by the fit simply is not there to link; an address whose
glyph survived is linked to exactly that address. Pure: Rich only, no
Textual, no ``data/``.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from rich.style import Style
from rich.text import Text

from maxpane_dashboard.widgets.address import (
    COPY_GLYPH,
    PROSE_ADDRESS_RE,
    address_text,
    short_address,
)

__all__ = [
    "NBSP",
    "keep_units",
    "link_in_order",
    "link_prose",
    "mark_addresses",
    "unmark",
]

#: Joins an address to its icon inside marked text. Not a breaking space for
#: ``textwrap`` (whose whitespace set is ASCII-only), so a wrap can never put
#: the icon at the start of the next line, away from the address it copies.
#: One cell, like the space it becomes again in :func:`unmark`.
NBSP = " "

#: A whole address followed by its icon, in painted text.
_LINKED_RE = re.compile(
    rf"(?<![0-9a-fA-F])(0x[0-9a-fA-F]{{40}})[ {NBSP}]{re.escape(COPY_GLYPH)}"
)


def mark_addresses(
    raw: str, width: int | None = None
) -> tuple[str, list[str], list[tuple[int, int]]]:
    """``raw`` with an icon after every address, ready to be fitted.

    Returns ``(marked, addresses, spans)``: the plain text, the addresses in
    the order their icons appear, and each ``shown address + NBSP + ⧉`` unit's
    ``(start, end)`` in ``marked`` -- a fitter that must never bisect a unit
    reads the spans. ``width`` windows each address through
    :func:`~widgets.address.short_address`; ``None`` keeps it whole.

    A ``⧉`` already in ``raw`` is removed first. The text is third-party, and
    a glyph its author typed would be an icon that copies nothing -- or, next
    to an address, one this module would link on their behalf. Whitespace is
    then flattened to single spaces, so a removed glyph leaves no double
    space behind and a fitter that flattens whitespace itself (HATCHES'
    ``fit_cell``) cannot shift the spans this returns.
    """
    text = " ".join(str(raw or "").replace(COPY_GLYPH, "").split())
    parts: list[str] = []
    addresses: list[str] = []
    spans: list[tuple[int, int]] = []
    pos = cursor = 0
    for match in PROSE_ADDRESS_RE.finditer(text):
        before = text[pos:match.start()]
        parts.append(before)
        cursor += len(before)
        address = match.group(0)
        shown = address if width is None else short_address(address, width)
        unit = f"{shown}{NBSP}{COPY_GLYPH}"
        parts.append(unit)
        spans.append((cursor, cursor + len(unit)))
        cursor += len(unit)
        addresses.append(address)
        pos = match.end()
    parts.append(text[pos:])
    return "".join(parts), addresses, spans


def keep_units(marked: str, spans: list[tuple[int, int]], cut: str) -> str:
    """``cut`` -- a fitter's prefix of ``marked`` plus ``…`` -- with no unit bisected.

    A window-and-icon unit (:func:`mark_addresses`' ``spans``) is kept whole
    or dropped whole. A fitter that knows nothing of addresses would happily
    cut one mid-window -- ``adopted 0xa1B997A9…`` is a window's own ellipsis
    followed by the cut's, an address that looks shortened rather than cut,
    and its icon gone with it. When the cut lands inside a unit, the text is
    re-cut in front of that unit instead; ``""`` when nothing would be left.

    ``cut == marked`` (nothing was cut) and ``cut == ""`` pass through.
    """
    if cut == marked or not cut:
        return cut
    kept = len(cut) - 1                                  # without the "…"
    for start, end in spans:
        if start < kept < end:
            head = marked[:start].rstrip()
            return f"{head}…" if head else ""
    return cut


def unmark(text: str) -> str:
    """Marked text as it is painted: each ``NBSP ⧉`` back to ``" ⧉"``."""
    return text.replace(f"{NBSP}{COPY_GLYPH}", f" {COPY_GLYPH}")


def _icon_style(address: str) -> Style | None:
    """The helper's own icon style for ``address`` -- never rebuilt here."""
    icon = address_text(address)
    for span in reversed(icon.spans):
        if span.end == len(icon.plain) and isinstance(span.style, Style):
            return span.style
    return None


def link_prose(text: Text) -> Text:
    """Attach the copy action to every ``0x…40 ⧉`` in ``text``, in place.

    For prose that keeps each address **whole**. The address is read back off
    the painted text, so a wrap or a cut that dropped some icons and kept
    others can never link a glyph to a neighbour's address.
    """
    for match in _LINKED_RE.finditer(text.plain):
        style = _icon_style(match.group(1))
        if style is not None:
            text.stylize(style, match.end() - 1, match.end())
    return text


def link_in_order(texts: Iterable[Text], addresses: list[str]) -> None:
    """Link the glyphs in ``texts`` to ``addresses``, first to first.

    For prose whose addresses are **windowed**, where the painted text no
    longer holds the address. Correct only when fitting can drop a *suffix* of
    the icons and never one from the middle -- a single line cut from the
    right, which is what a signal detail is. Every glyph is ours
    (:func:`mark_addresses` removed the author's), so the n-th glyph is the
    n-th address.
    """
    remaining = iter(addresses)
    for text in texts:
        for index, char in enumerate(text.plain):
            if char != COPY_GLYPH:
                continue
            address = next(remaining, None)
            if address is None:
                return
            style = _icon_style(address)
            if style is not None:
                text.stylize(style, index, index + 1)
