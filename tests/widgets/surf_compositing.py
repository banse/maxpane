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


async def composite_lines(
    widget_cls, size, css_path=None, region_only=False, **kwargs
) -> list[str]:
    """Mount *widget_cls* alone at *size*, feed it *kwargs*, composite it.

    Returns **one string per painted terminal row**, right-stripped.

    The widget is mounted as the only child of a bare ``App`` rather than
    inside the real screen on purpose: these are the panels' own width and
    line-count measurements, and a screen harness would fold the screen's CSS
    into every one of them. The screen-level measurements live in
    ``tests/screens/`` and are made against the themed harness there.

    ``css_path`` opts *into* one stylesheet -- pass ``maxpane_dashboard.app
    .CSS_PATH`` and the harness loads ``minimal.tcss`` as the **app**
    stylesheet, which is where it lives in production and which outranks every
    widget's ``DEFAULT_CSS``. That is the harness a *convention* test needs
    (``test_title_blank_row.py``): the same rule written in only one of the
    two places renders differently in the app than in a bare mount, and a
    bare mount cannot see it. It is still not a screen harness -- no screen
    CSS, no sibling panels, no row seams -- so the default above is unchanged
    and the surf measurements it was written for are untouched.

    ``region_only`` returns the rows of the widget's **own rectangle** instead
    of the whole screen. The two differ the moment a stylesheet gives the
    panel a margin: eight of the ``SIGNALS`` panels carry ``margin: 1 0 0 0``
    in ``minimal.tcss``, so under ``css_path`` their screen row 0 is that
    margin and their title is on row 1. A caller asking "what is directly
    under this title" must not have to guess how many leading blanks belong to
    somebody else, and must not simply skip them either -- skipping is how a
    panel with **no** title passes a title assertion.
    """

    class _A(App):
        CSS_PATH = css_path

        def compose(self):
            yield widget_cls()

    async with _A().run_test(size=size) as pilot:
        widget = pilot.app.query_one(widget_cls)
        widget.update_data(**kwargs)
        await pilot.pause()
        strips = pilot.app.screen._compositor.render_strips()
        rows = ["".join(seg.text for seg in strip) for strip in strips]
        if region_only:
            region = widget.region
            rows = [
                rows[y][region.x : region.x + region.width]
                for y in range(
                    max(region.y, 0), min(region.y + region.height, len(rows))
                )
            ]
        return [row.rstrip() for row in rows]
