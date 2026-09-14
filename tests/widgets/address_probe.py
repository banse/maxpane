"""Read copy icons off composited output: where each is and what it copies."""

from __future__ import annotations

import re

from rich.cells import cell_len

from maxpane_dashboard.widgets.address import COPY_GLYPH

_ACTION = re.compile(r"app\.copy_address\('(0x[0-9a-fA-F]{40})'\)")


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
                    match = _ACTION.fullmatch(str(meta.get("@click", "")))
                    out.append((x, y, match.group(1) if match else None))
                x += cell_len(ch)
    return out


class CopyRecorder:
    """Mix into a harness ``App`` ahead of ``App``: records copies, touches no clipboard."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.copied: list[str] = []

    async def action_copy_address(self, address: str) -> None:
        self.copied.append(address)
