"""Every 0x address a widget renders, with the copy icon beside it.

PRD: ``docs/address_copy_PRD.md``. One module owns every address on screen,
so the rule "a displayed address carries a ``⧉`` that copies it" lives in one
place and the 21 private formatters it replaced cannot drift apart again.

Pure: Rich only. No Textual, no I/O, no clock, no ``data/``. The copy itself
happens in ``maxpane_dashboard/clipboard.py`` via ``copy_action.CopyAddressMixin``;
this module only renders the icon and names the action it triggers.
"""

from __future__ import annotations

import re

from rich.cells import cell_len
from rich.style import Style
from rich.text import Text

__all__ = [
    "ADDRESS_RE", "COPY_GLYPH", "ICON_COLS", "MIN_SHORT_COLS", "PROSE_ADDRESS_RE",
    "address_prose", "address_text", "copy_action", "is_address", "is_copy_click",
    "short_address", "short_hex",
]

#: An address, matched with ``fullmatch`` and **never** with ``^…$``: Python's
#: ``$`` also matches before a trailing newline, so an anchored pattern accepts
#: ``"0x…\n"``, which is exactly the value this check exists to keep out of an
#: action string (PRD §3.1 AMENDED).
ADDRESS_RE = re.compile(r"0x[0-9a-fA-F]{40}")

#: An address inside prose. Hex boundaries on both sides: a 64-hex transaction
#: hash starts with a 40-hex run, and without the lookahead every hash in a
#: post would get an icon that copies a truncated, meaningless value.
PROSE_ADDRESS_RE = re.compile(r"(?<![0-9a-fA-F])0x[0-9a-fA-F]{40}(?![0-9a-fA-F])")

_HEX_RE = re.compile(r"0x[0-9a-fA-F]+")

#: U+29C9 TWO JOINED SQUARES, one cell wide; chosen by the owner after seeing
#: it render cleanly in their terminal. ``📋`` is two cells and inconsistent.
COPY_GLYPH = "⧉"

#: What one icon costs a layout: a separating space and the one-cell glyph.
ICON_COLS = 2

#: The narrowest window: ``0x`` + 4 + ``…`` + 4, curator's former form.
MIN_SHORT_COLS = 11

_ELLIPSIS = "…"
_TAIL_MAX = 6
_ACTION_PREFIX = "app.copy_address("


def is_address(value: object) -> bool:
    """True only for a whole, well-formed 0x address."""
    return isinstance(value, str) and ADDRESS_RE.fullmatch(value) is not None


def _window(value: str, width: int) -> str:
    """The anti-poisoning window (PRD §3.2 AMENDED).

    ``budget = width - 3`` for ``0x`` and ``…``; ``tail = min(6, budget // 2)``;
    ``head = budget - tail``. At 17 cells that is 8/6 (surf's ``long_addr``,
    which exists because live spoofs collide with real addresses on 6/4), at
    11 it is 4/4 (curator's ``short_addr``). Case is preserved.
    """
    width = max(width, MIN_SHORT_COLS)
    if cell_len(value) <= width:
        return value
    budget = width - 3
    tail = min(_TAIL_MAX, budget // 2)
    head = budget - tail
    return f"0x{value[2:2 + head]}{_ELLIPSIS}{value[-tail:]}"


def short_address(address: str, width: int) -> str:
    """``address`` windowed to ``width`` cells; a non-address passes through."""
    return _window(address, width) if is_address(address) else address


def short_hex(value: str, width: int) -> str:
    """Any other 0x hex (a transaction hash) windowed the same way. No icon."""
    if isinstance(value, str) and _HEX_RE.fullmatch(value):
        return _window(value, width)
    return value


def copy_action(address: str) -> str:
    """The action string for a **validated** address. Never call it otherwise."""
    return f"{_ACTION_PREFIX}{address!r})"


def _fit(text: str, width: int | None) -> str:
    """``text`` fitted to ``width`` cells with a trailing ellipsis."""
    if width is None or cell_len(text) <= width:
        return text
    out = ""
    for ch in text:
        if cell_len(out) + cell_len(ch) > width - 1:
            break
        out += ch
    return out + _ELLIPSIS


def _clean_label(value: object) -> str:
    """Third-party display text made safe to sit on one row beside an icon.

    Every whitespace run (a newline, a tab, a run of spaces) becomes one
    space, so a name cannot break or stretch the row it is in; and every
    :data:`COPY_GLYPH` is removed, so a name like ``"x ⧉"`` cannot paint a
    dead second icon beside the real one.
    """
    return " ".join(value.replace(COPY_GLYPH, "").split())


def _icon(address: str) -> tuple[str, Style]:
    return COPY_GLYPH, Style(meta={"@click": copy_action(address)})


def address_text(
    address: str | None,
    *,
    label: str | None = None,
    width: int | None = None,
    style: str | Style = "",
) -> Text:
    """Display text plus ``" ⧉"``, the click action on the glyph only.

    ``label`` is shown instead of the address (an ENS or player name); the icon
    still copies ``address``. ``width`` is the budget for the displayed part and
    **excludes** :data:`ICON_COLS`; ``None`` shows the whole address. A value
    that is not a valid address renders plain, with no icon and no action.
    ``style`` must be a Rich style, never a ``$theme`` token.

    ``label`` is third-party text and is hardened here, once, for every
    caller: a non-string label is ignored (the address is shown, nothing
    raises), whitespace runs collapse to single spaces and any copy glyph in
    it is removed. A label left empty by that falls back to the address. An
    invalid value shown in place of an address gets the same treatment.
    """
    valid = is_address(address)
    label = _clean_label(label) if isinstance(label, str) else None
    if label:
        shown = _fit(label, width)
    elif valid:
        shown = address if width is None else short_address(address, width)
    else:
        shown = _fit(_clean_label(str(address)) if address else "--", width)
    out = Text(shown, style=style)
    if valid:
        out.append(" ")
        out.append(*_icon(address))
    return out


def address_prose(text: str, *, style: str | Style = "") -> Text:
    """``text`` with ``" ⧉"`` inserted after every valid address in it."""
    out = Text(style=style)
    pos = 0
    for match in PROSE_ADDRESS_RE.finditer(text):
        out.append(text[pos:match.end()])
        out.append(" ")
        out.append(*_icon(match.group(0)))
        pos = match.end()
    out.append(text[pos:])
    return out


def is_copy_click(event: object) -> bool:
    """True when a click landed on a copy icon.

    A widget with its own ``on_click`` returns early when this is true, so the
    icon's copy fires and the widget's own behaviour does not (PRD §3.4).
    """
    meta = getattr(getattr(event, "style", None), "meta", None) or {}
    action = meta.get("@click")
    return isinstance(action, str) and action.startswith(_ACTION_PREFIX)
