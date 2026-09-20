"""Read copy icons and explorer links off composited output: where each is and what it does."""

from __future__ import annotations

from rich.cells import cell_len

from maxpane_dashboard.widgets.address import COPY_GLYPH, parse_copy_action
from maxpane_dashboard.widgets.explorer import parse_open_action


def icon_targets(app) -> list[tuple[int, int, str | None]]:
    """Every ``⧉`` on screen as ``(x, y, copied address)``.

    ``x`` is a **cell** column, accumulated with ``cell_len``: a CJK name
    before the icon would put a character index on the wrong cell. The
    address comes from the compositor's style at that cell, which is the
    click target a user would hit; ``None`` means an icon whose action is not
    a well-formed copy.
    """
    out: list[tuple[int, int, str | None]] = []
    for y, strip in enumerate(app.screen._compositor.render_strips()):
        x = 0
        for segment in strip:
            for ch in segment.text:
                if ch == COPY_GLYPH:
                    meta = app.screen.get_style_at(x, y).meta or {}
                    out.append((x, y, parse_copy_action(meta.get("@click"))))
                x += cell_len(ch)
    return out


class CopyRecorder:
    """Mix into a harness ``App`` ahead of ``App``: records copies, touches no clipboard."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.copied: list[str] = []

    async def action_copy_address(self, address: str) -> None:
        self.copied.append(address)


LinkTarget = tuple[int, int, str | None, str | None, str | None, str | None]


def link_targets(app) -> list[LinkTarget]:
    """Every linked cell on screen as ``(x, y, explorer name, kind, value, url)``.

    A cell counts when its style carries an OSC 8 ``link`` **or** an
    ``@click`` that ``parse_open_action`` accepts; the three middle fields are
    ``None`` when the action is absent or not a well-formed open, ``url`` is
    ``None`` when there is no hyperlink. ``x`` is a cell column, as in
    :func:`icon_targets`. One entry per cell, so a sweep can look up the cell
    right before an icon.
    """
    out: list[LinkTarget] = []
    for y, strip in enumerate(app.screen._compositor.render_strips()):
        x = 0
        for segment in strip:
            style = segment.style
            link = style.link if style is not None else None
            parsed = parse_open_action((style.meta or {}).get("@click")) if style is not None else None
            for ch in segment.text:
                if link or parsed:
                    name, kind, value = (parsed[0].name, parsed[1], parsed[2]) if parsed else (None, None, None)
                    out.append((x, y, name, kind, value, link))
                x += cell_len(ch)
    return out


class LinkRecorder:
    """Mix into a harness ``App`` ahead of ``App``: records ``open_url`` calls, opens nothing."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.opened: list[str] = []

    def open_url(self, url: str, *, new_tab: bool = True) -> None:
        self.opened.append(url)
