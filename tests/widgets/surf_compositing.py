"""The one compositing helper the surf widget tests share.

Carry-over **C5**, closed 2026-09-11 (WP10). Five test files had written the
same private ``_lines`` by hand -- ``test_surf_pool4_left.py`` first, then the
four ``pool4u`` files as the `4` body was built -- because two packages were
writing in this tree at once and creating a shared module mid-wave is a
collision, not convergence. Each of those files says so in its own docstring
and names the hoist as a filed follow-up. This is the hoist.

The divergence, not the typing, is what this saves. Five copies of one helper
means a fix reaches one of them, and this helper is not inert: it encodes the
**join** every layout assertion in those files depends on.

Segments are joined per **strip** first, and then the caller joins rows with
newlines. Joining every segment with a newline instead splits one painted row
into several apparent lines the moment that row carries two styles -- which
every one of these panels does, with a dim label beside a coloured value, and
which a ``DataTable`` does per *cell*. A test written on the other join passes
while the user sees something else.

There is deliberately no ``_text`` sibling here. Each test file keeps its own
one-line ``"\\n".join(...)`` wrapper with its own default size, because those
defaults are per-panel measurements rather than shared behaviour.
"""

from __future__ import annotations

from textual.app import App

__all__ = ["composite_lines"]


async def composite_lines(widget_cls, size, **kwargs) -> list[str]:
    """Mount *widget_cls* alone at *size*, feed it *kwargs*, composite it.

    Returns **one string per painted terminal row**, right-stripped.

    The widget is mounted as the only child of a bare ``App`` rather than
    inside the real screen on purpose: these are the panels' own width and
    line-count measurements, and a screen harness would fold the screen's CSS
    into every one of them. The screen-level measurements live in
    ``tests/screens/`` and are made against the themed harness there.
    """

    class _A(App):
        def compose(self):
            yield widget_cls()

    async with _A().run_test(size=size) as pilot:
        widget = pilot.app.query_one(widget_cls)
        widget.update_data(**kwargs)
        await pilot.pause()
        strips = pilot.app.screen._compositor.render_strips()
        return ["".join(seg.text for seg in strip).rstrip() for strip in strips]
