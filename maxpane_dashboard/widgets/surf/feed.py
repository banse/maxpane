"""The announce-channel feed: decoded posts, classified, honestly styled.

The panel is titled ``ANNOUNCE FEED`` (PRD §4), exported as ``FEED_TITLE``
because the screen WP asserts it against composited output -- including as
the *negative* half of the ``c``-swap test, where its absence is what proves
the dev-activity panel replaced this one.  Import the constant; do not
retype or shorten the string.

One logical row per channel tx, newest first::

    08-07 04:27  POST    I moved 33 eth to the LP on mainnet https://…

Kinds and their styling (classification happens upstream in
``analytics/surf_signals.classify_channel_tx``; this widget renders the
``kind`` string it is given):

* ``self``   -- ``POST`` in cyan: the dev's own broadcast.
* ``reply``  -- ``REPLY`` dim: the channel is permissionless and replies
  are anyone's text.  A reply is never styled like a dev post and its
  links are never highlighted (PRD §6.4).
* ``action`` -- ``ACTION`` in yellow (the RichLog-safe stand-in for
  ``$warning`` -- see the ``_KIND_STYLES`` note): an outbound contract call
  (the ERC-8004 register() was exactly this shape -- NEW DEPLOY fuel).
* ``fund``   -- ``FUND`` magenta: dev-wallet funding of the channel.

Width tiers: at ``FULL_TEXT_WIDTH`` columns and above the message renders
*in full*, wrapped with a hanging indent -- the feed is the product here,
and the dev's posts are the payload.  Below that, one truncated line per
post with a visible ``…`` and ``‹ widen`` in the title (house rule: a
clipped row is always announced).

On-chain messages contain raw newlines (nonce 8 does today); they are
flattened to single spaces *before* truncation, and ``safe_markup`` runs
**after** all slicing so an escape sequence can never be cut in half.

``feed_items=None`` means the source is dead (explicit unavailable state);
``[]`` means the window is genuinely empty.  Never a blank panel.

Rendering primitive: this widget writes every message line through
``RichLog`` (``markup=True``), never through ``DataTable.add_row`` --
``DataTable`` defers markup parsing to the message pump and a bad cell can
raise *outside* any local ``try/except``, which is exactly the crash this
module exists to avoid on a feed anyone can post attacker-authored text to.
``RichLog.write`` parses markup through Rich's own parser at call time
(synchronously, once the widget's size is known), which is what
``safe_markup`` (``rich.markup.escape``) is built to neutralise -- so the
one row-formatting failure mode this module still has to guard is a
*formatting* exception inside ``_item_lines`` itself (e.g. a malformed
``ts``), not a markup-parse failure at write time.  ``_item_lines`` never
lets such an exception escape: a malformed item degrades to ``None`` and is
skipped, so one bad row can never blank the whole panel or the app.

Primitives only -- this module imports nothing from the data layer.
"""

from __future__ import annotations

import textwrap

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import RichLog, Static

from maxpane_dashboard.widgets.markup_safety import safe_markup
from maxpane_dashboard.widgets.surf._fmt import DASH, fmt_age, hhmm, mmdd

#: Panel title, PRD §4 spelling.  **Interface**: the screen tests assert this
#: exact string reaches the compositor, and assert its *absence* when the
#: ``c`` key swaps in the dev-activity panel.  Import it, never retype it.
FEED_TITLE = "ANNOUNCE FEED"

#: Columns at or above which messages render in full (wrapped).
#:
#: Lowered 76 -> 71 on request, and the reason is worth recording because the
#: obvious lever was the wrong one.  The columns were re-seamed 3:2 -> 7:6 to
#: bring the screen's full-layout width down from 176 to 152, which narrowed
#: this panel's share: at 76 the feed only began wrapping at a 151-column
#: terminal, so between 135 and 150 it showed one truncated line per post.
#: The instinct was to widen the feed's column back, but that trade was bad --
#: a 9:7 seam wrapped from 144 and cost 9 columns of full-layout width (152 ->
#: 161), because the *dev activity* panel was what bound at 152, not this one.
#: Moving this threshold instead wrapped from 142 and cost the full-layout
#: width **nothing**; all three of 76/71/66 left it at 152 (measured then).
#:
#: **That free ride is over, and the paragraph above is the old regime.** The
#: activity row's cells were sized to their producer's vocabularies, which
#: took that panel 66 -> 58 columns, so it clears from 135 and *this* panel is
#: what binds the screen. This threshold now sets the screen's full-layout
#: width directly: re-measured on the real screen, 66 -> 135, **71 -> 142**,
#: 76 -> 151. Lowering it is now the cheapest width there is; raising it is
#: paid in full-layout columns, one for one.
#:
#: What it does cost is rows: a wrapped post is taller than a cut one, so at
#: 143 columns the feed spends 9 rows on the two sweep posts where it spent 3.
#: That is what wrapping *is*, and this panel is the one the layout hands all
#: its slack height to, so it is the cheapest place in the screen to spend it.
#: 66 would wrap from 132 if an even narrower terminal ever matters.
FULL_TEXT_WIDTH = 71

#: Marker appended to the title when a message had to be truncated.
WIDEN_HINT = "‹ widen"

#: The explicit degraded line.  Tested verbatim.
UNAVAILABLE_LINE = "feed unavailable"

#: Max feed items rendered per refresh.
_MAX_ROWS = 25

#: ``MM-DD HH:MM`` (11) + 2 spaces + badge column (6) + 1 space.
_PREFIX_WIDTH = 20

#: Minimum text budget: below this we stop shrinking and let CSS clip.
_MIN_TEXT_BUDGET = 10

#: badge text + colour per kind.  Unknown kinds render dim ``?``.
#:
#: Literal Rich colour names, not Textual ``$warning``-style design tokens:
#: this widget renders through ``RichLog`` (``markup=True``), which parses
#: with Rich's own ``Text.from_markup`` -- the parser ``rich.markup.escape``
#: is built against -- not Textual's ``Content.from_markup``/``$token``
#: extension that ``Static.update()`` understands.  ``[$warning]`` is not
#: valid Rich markup and raised ``MarkupError`` on every ACTION row until
#: this was caught by the test suite; ``yellow`` is the same warning colour
#: already used literally elsewhere in this module (``_set_title``,
#: ``UNAVAILABLE_LINE``).
_KIND_STYLES = {
    "self": ("POST", "cyan"),
    "reply": ("REPLY", "dim"),
    "action": ("ACTION", "yellow"),
    "fund": ("FUND", "magenta"),
}


def _wrap_no_widow(raw: str, budget: int) -> list[str]:
    """Greedy word-wrap ``raw`` at ``budget`` columns, avoiding widows.

    Plain ``textwrap.wrap`` fills greedily from the front, which can strand
    a short final fragment on its own line -- a real captured 227-char post
    ends ``"...as always 0 promises."`` and a plain greedy fill at this
    panel's real column budget splits ``"0"`` from ``"promises."``, putting
    the tail of the message on a line by itself.  That is not a hostile
    input -- it is what a genuine dev post does to an honest word-wrapper,
    and it is what this widget's own tests caught.

    The fix is bounded widow control: if the last line is much shorter than
    the budget, retry at a narrower target width (never wider -- a wider
    retry could produce a line ``RichLog`` would silently shrink/clip, since
    it is configured ``wrap=False`` and relies on this function to have
    already fit every line inside the panel). The search is capped and
    always falls back to the plain wrap if no narrower width helps, so this
    never loops unboundedly and never exceeds ``budget`` on any line.
    """
    wrapped = textwrap.wrap(
        raw, budget, break_long_words=False, break_on_hyphens=False
    ) or [""]
    if len(wrapped) <= 1:
        return wrapped

    widow_floor = max(budget // 3, _MIN_TEXT_BUDGET)
    if len(wrapped[-1]) >= widow_floor:
        return wrapped

    floor = max(budget // 2, _MIN_TEXT_BUDGET)
    for trial in range(budget - 1, floor - 1, -1):
        candidate = textwrap.wrap(
            raw, trial, break_long_words=False, break_on_hyphens=False
        ) or [""]
        if len(candidate[-1]) >= widow_floor:
            return candidate
    return wrapped


def _item_lines(item, width: int) -> tuple[list[str], bool] | None:
    """Render one feed item at ``width`` columns.

    Returns ``(markup_lines, clipped)`` or ``None`` for malformed input.
    Escaping happens after wrapping/truncation, per token, so a cut can
    never bisect an escape sequence.
    """
    if not isinstance(item, dict):
        return None
    try:
        stamp = f"{mmdd(item.get('ts'))} {hhmm(item.get('ts'))}"
        kind = str(item.get("kind") or "").strip().lower()
        badge, color = _KIND_STYLES.get(kind, ("?", "dim"))
        prefix = f"{stamp}  [{color}]{badge:<6}[/] "
        indent = " " * _PREFIX_WIDTH

        # Flatten on-chain newlines/tabs to single spaces first.
        raw = " ".join(str(item.get("text") or "").split())
        budget = max(width - _PREFIX_WIDTH, _MIN_TEXT_BUDGET)

        if width >= FULL_TEXT_WIDTH:
            wrapped = _wrap_no_widow(raw, budget)
            # An unbreakable token -- a base64 blob, a long URL, a hash --
            # is exactly what ``textwrap.wrap(..., break_long_words=False)``
            # will not split: it lands on its own line wider than ``budget``
            # and passes through untouched.  RichLog would then clip it
            # itself with no visible sign at all (the same silent-clip
            # failure mode fixed above for the scrollbar gutter), which
            # breaks the house rule that a clipped row is always announced.
            # Force it to the same visible ``…`` truncation the narrow tier
            # uses, and light the widen hint -- never widen a retry (that
            # risks the identical RichLog clip), only ever shrink to fit.
            clipped = False
            fitted = []
            for chunk in wrapped:
                if len(chunk) > budget:
                    chunk = chunk[: max(budget - 1, 0)] + "…"
                    clipped = True
                fitted.append(chunk)
            lines = [prefix + safe_markup(fitted[0])]
            lines += [indent + safe_markup(chunk) for chunk in fitted[1:]]
            return lines, clipped

        if len(raw) > budget:
            return [prefix + safe_markup(raw[: budget - 1] + "…")], True
        return [prefix + safe_markup(raw)], False
    except Exception:
        # A single malformed item must never take down the panel.
        return None


class SurfFeed(Vertical):
    """Announce-channel feed with kind badges and width tiers."""

    DEFAULT_CSS = """
    SurfFeed > .surf-feed-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    SurfFeed > RichLog {
        height: 1fr;
        padding: 0 1;
        scrollbar-size: 1 1;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._payload: dict = {}

    def compose(self) -> ComposeResult:
        yield Static(FEED_TITLE, classes="surf-feed-title", id="surf-feed-title")
        yield Static(" ", classes="surf-feed-spacer")
        yield RichLog(
            id="surf-feed-log",
            wrap=False,
            highlight=False,
            markup=True,
            max_lines=200,
        )

    def update_data(
        self,
        feed_nonce=None,
        feed_last_post_age_s=None,
        feed_items=None,
        **_kwargs,
    ) -> None:
        """Rewrite the log.  Kwargs are exactly the PRD §5 feed keys."""
        self._payload = {
            "nonce": feed_nonce,
            "age_s": feed_last_post_age_s,
            "items": feed_items,
        }
        self._render_view()

    def on_resize(self, _event=None) -> None:
        """Re-lay out: the tier depends on the width."""
        if self._payload:
            self._render_view()

    # -- rendering -----------------------------------------------------

    def _set_title(self, nonce, age_s, clipped: bool, unavailable: bool) -> None:
        title = self.query_one("#surf-feed-title", Static)
        parts = [FEED_TITLE]
        try:
            parts.append(f"· #{int(nonce)}")
        except (TypeError, ValueError):
            pass
        age = fmt_age(age_s)
        if age != DASH:
            parts.append(f"· last {age} ago")
        if unavailable:
            parts.append("· [yellow]unavailable[/]")
        text = " ".join(parts)
        if clipped:
            text += f"  [yellow]{WIDEN_HINT}[/]"
        title.update(text)

    def _render_view(self) -> None:
        try:
            log = self.query_one("#surf-feed-log", RichLog)
        except Exception:  # not composed yet
            return

        items = self._payload.get("items")
        nonce = self._payload.get("nonce")
        age_s = self._payload.get("age_s")

        # ``log.content_size.width`` does *not* account for the vertical
        # scrollbar gutter: ``RichLog``'s own ``DEFAULT_CSS`` sets
        # ``overflow-y: scroll`` (always-on, not ``auto``), so the gutter is
        # reserved even for a two-line log.  ``RichLog.write()`` itself
        # shrinks any line wider than ``scrollable_content_region.width`` --
        # one column narrower than ``content_size.width`` -- with no visible
        # marker.  Measuring against ``content_size`` here silently clipped
        # the last character of a narrow-tier row (dropping the truncation
        # ``…`` this module exists to guarantee); measuring against the same
        # region ``write()`` shrinks to keeps both in agreement.
        width = log.scrollable_content_region.width
        if width <= 0:
            width = max(self.content_size.width - 3, 0)

        log.clear()
        log.auto_scroll = False

        if items is None:
            # Source dead: explicit state, never a blank panel (PRD §5 meta).
            self._set_title(nonce, age_s, clipped=False, unavailable=True)
            log.write(f"[yellow]⚠ {UNAVAILABLE_LINE}[/]")
            return

        try:
            item_list = [i for i in list(items)[:_MAX_ROWS] if isinstance(i, dict)]
        except TypeError:
            item_list = []

        clipped_any = False
        lines: list[str] = []
        for item in item_list:
            rendered = _item_lines(item, width)
            if rendered is None:
                continue
            item_markup, clipped = rendered
            clipped_any = clipped_any or clipped
            lines.extend(item_markup)
            # A blank line after every post. These are multi-line messages
            # with no other separator, so without one a long post runs
            # straight into the next post's date and the two read as a
            # single message. After the last one too: the log scrolls, so a
            # trailing blank costs nothing, and omitting it would drop the
            # separator exactly when the final post is what got scrolled to.
            lines.append("")

        self._set_title(nonce, age_s, clipped=clipped_any, unavailable=False)
        if not lines:
            log.write("[dim]  no posts in window[/]")
            return
        for line in lines:
            log.write(line)
        self.call_after_refresh(log.scroll_home, animate=False)
