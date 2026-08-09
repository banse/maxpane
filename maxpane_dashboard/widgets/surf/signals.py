"""The six-detector panel for the surf dashboard (PRD §3).

One row per detector: NEW POST · LP MIGRATION · GATE OPEN · NEW DEPLOY ·
BRIDGE STAGE · BURN.  Each row renders ``state · age · one-line detail``
with the state always spelled in words:

* ``fired`` -- ``▶ NEW POST FIRED 2h ago · detail`` in loud bold ``$error``.
  The 24 h FIRED persistence and the baseline math live in
  ``analytics/surf_signals.py``; this widget renders whatever state string
  the manager hands it and adds nothing.
* ``watch`` -- ``◐ NEW DEPLOY WATCH · detail`` in ``$warning``.
* ``ok``    -- ``● LP MIGRATION OK · detail`` dim.
* ``None``/unknown -- ``● LP MIGRATION --`` dim: an unreadable detector is
  unknown, never OK (PRD §6.1's rendering half).

The labels are the PRD §3 names in full, at *every* width -- they are an
interface, asserted against composited output by the screen WP and by two
app-level acceptance tests.  ``DETECTOR_LABELS`` below is the single source;
importers use it instead of retyping the strings.  They are never shortened
to save columns: the label belongs to the row *head*, and the head is what
the width budget below protects.

Detail strings quote announce-channel text, which is attacker-writable by
design, so every detail passes ``safe_markup`` -- after newline flattening
*and after truncation*, so a cut can never bisect an escape sequence
(``feed._item_lines`` does the same, for the same reason).

Width budget -- the detail shrinks, the head never does
---------------------------------------------------------

This panel is the ``2fr`` of the hero row's ``3fr:2fr`` split, so it gets
``2W/5 - 4`` content columns; ``padding: 0 1`` on the body rows costs two
more.  At the pinned full-layout width ``W = 143`` that is 53 columns of
content and **51 usable**::

    head                                    cols
    "  ● BURN OK"                             11   <- shortest
    "  ▶ BRIDGE STAGE FIRED 12m ago"          30   <- realistic worst
    "  ▶ BRIDGE STAGE FIRED 100d ago"         31   <- absolute worst

The head is unshrinkable (glyph + full label + state word + age).  Whatever
is left after it and the ``· `` separator (``SEPARATOR_COLS``) is the detail
budget -- **17-18 columns worst case at the pinned width, ~37 on a short
label** -- and the detail is cut to fit with a visible ``…``.

``clipped``, which lights ``‹ widen`` in the title, is therefore set **only
when the head itself does not fit**.  Testing the whole row would light the
marker permanently: ``analytics/surf_signals`` builds details up to
``DETAIL_LIMIT`` (48) and its relaxed-FIRED form composes
``"... · last: ..."`` on top of that, so real rows run 80-105 columns against
a 51-column panel.  A marker that is always on means nothing, and widening
the layout to clear it would push ``FULL_LAYOUT_COLUMNS`` to ~190 -- past the
~169 columns a laptop gets at the forced 17 pt, i.e. a full layout nobody can
reach.  ``fwa_signals.py`` records the same trap in its ``_GATE_WORDS`` note.

Row budget: title + spacer + 6 rows = 8 lines.

Primitives only -- this module imports nothing from the data layer.
"""

from __future__ import annotations

import logging

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.css.query import QueryError
from textual.widgets import Static

from maxpane_dashboard.widgets.markup_safety import safe_markup, visible_len
from maxpane_dashboard.widgets.surf._fmt import DASH, fmt_age

logger = logging.getLogger(__name__)

#: Marker appended to the title when a *head* could not fit (see the module
#: docstring: a truncated detail is normal operation, not a clipped row).
WIDEN_HINT = "‹ widen"

#: Detail shown when a row's markup passes ``safe_markup`` but still fails
#: Textual's own markup parser at render time -- e.g. the unbalanced
#: ``]][[/][/ malformed`` shape, which ``rich.markup.escape`` renders inert
#: but ``textual.markup`` still rejects as a closing tag with no opener.  The
#: announce channel is an address anyone can write to (PRD §6.4), so this is
#: reachable with a real chain-sourced detail, not a synthetic string.
#:
#: Deliberately distinct from both a real detail (this is never quoted text)
#: and from ``DASH`` (the dead-detector marker): a render failure means the
#: read *succeeded* and produced an unparseable detail, which is a different,
#: narrower and less alarming fact than "this detector could not be read".
#: Rendering it as ``DASH`` would misreport a working read as a dead one --
#: exactly the failure mode this whole panel exists to avoid.
RENDER_FAILED_DETAIL = "⚠ detail failed to render"

#: Visible cost of the ``· `` that joins a head to its detail, counting the
#: space in front of it: ``" · "``.
SEPARATOR_COLS = 3

#: Below this many columns of remaining budget the detail is dropped rather
#: than rendered as a stub: two characters and an ellipsis say nothing.
MIN_DETAIL_COLS = 6

#: The state vocabulary this widget knows.  Anything else -- including
#: ``None`` -- is the unknown row, which is never OK (PRD §6.1).
_KNOWN_STATES = ("fired", "watch", "ok")

#: The six detector labels, PRD §3 spelling, PRD §3 order.  **Interface**:
#: the screen tests and the app-level acceptance tests assert these exact
#: strings reach the compositor -- import this tuple, never retype it, and
#: never shorten a label to save columns (see the module docstring).
DETECTOR_LABELS = (
    "NEW POST",
    "LP MIGRATION",
    "GATE OPEN",
    "NEW DEPLOY",
    "BRIDGE STAGE",
    "BURN",
)

#: payload prefix + child id per detector, aligned 1:1 with DETECTOR_LABELS.
_ROW_KEYS = (
    ("post", "#surf-sig-post"),
    ("lp", "#surf-sig-lp"),
    ("gate", "#surf-sig-gate"),
    ("deploy", "#surf-sig-deploy"),
    ("bridge", "#surf-sig-bridge"),
    ("burn", "#surf-sig-burn"),
)

#: (payload prefix, row label, child id) for the six detectors, in PRD order.
_ROWS = tuple(
    (prefix, label, selector)
    for (prefix, selector), label in zip(_ROW_KEYS, DETECTOR_LABELS)
)


def _head(label: str, state, age_s) -> str:
    """The unshrinkable part of a row, as markup.  Pure; unit-tested.

    Measure it with ``visible_len`` -- this is the width that decides whether
    the panel needs widening, and the only width the row cannot give back.
    """
    state_s = str(state or "").strip().lower()
    if state_s == "fired":
        age = fmt_age(age_s)
        body = f"{label} FIRED {age} ago" if age != DASH else f"{label} FIRED"
        return f"  [bold $error]▶ {body}[/]"
    if state_s == "watch":
        return f"  [$warning]◐ {label} WATCH[/]"
    if state_s == "ok":
        return f"  [$success]●[/] [dim]{label} OK[/]"
    # None or an unknown vocabulary word: unknown, never OK.
    return f"  [dim]● {label} {DASH}[/]"


def _fmt_signal_row(label: str, state, detail, age_s, available=None) -> str:
    """Render one detector row, fitting the detail to ``available`` columns.

    ``available`` is the row's column budget.  ``None`` -- the default, and
    what an unmounted widget reports -- means "width unknown, do not
    truncate"; the unit tests rely on that to inspect the full string.

    The head is never shortened.  The detail is cut to whatever is left after
    the head and ``SEPARATOR_COLS``, with a visible ``…``; below
    ``MIN_DETAIL_COLS`` it is dropped entirely.  Escaping happens *after* the
    cut so a slice can never bisect an escape sequence.
    """
    head = _head(label, state, age_s)
    if str(state or "").strip().lower() not in _KNOWN_STATES:
        # An unknown detector has no detail worth quoting.
        return head

    # Newlines flattened first: an announce body is multi-line, a row is not.
    flat = " ".join(str(detail or "").split())
    if not flat:
        return head

    if available:
        budget = int(available) - visible_len(head) - SEPARATOR_COLS
        if budget < MIN_DETAIL_COLS:
            return head
        if len(flat) > budget:
            flat = flat[: budget - 1].rstrip() + "…"

    return f"{head} [dim]· {safe_markup(flat)}[/]"


class SurfSignals(Vertical):
    """Detector panel with six rows."""

    DEFAULT_CSS = """
    SurfSignals > .surf-signals-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    SurfSignals > .surf-signals-body {
        padding: 0 1;
        width: 100%;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._payload: dict = {}

    def compose(self) -> ComposeResult:
        yield Static("SIGNALS", classes="surf-signals-title", id="surf-sig-title")
        yield Static("", classes="surf-signals-body", id="surf-sig-spacer")
        for _, _, selector in _ROWS:
            yield Static("", classes="surf-signals-body", id=selector.lstrip("#"))

    def update_data(
        self,
        sig_post_state=None,
        sig_post_detail=None,
        sig_post_age_s=None,
        sig_lp_state=None,
        sig_lp_detail=None,
        sig_lp_age_s=None,
        sig_gate_state=None,
        sig_gate_detail=None,
        sig_gate_age_s=None,
        sig_deploy_state=None,
        sig_deploy_detail=None,
        sig_deploy_age_s=None,
        sig_bridge_state=None,
        sig_bridge_detail=None,
        sig_bridge_age_s=None,
        sig_burn_state=None,
        sig_burn_detail=None,
        sig_burn_age_s=None,
        **_kwargs,
    ) -> None:
        """Refresh the six rows.  Kwargs are exactly the PRD §5 signal keys."""
        self._payload = {
            "sig_post_state": sig_post_state,
            "sig_post_detail": sig_post_detail,
            "sig_post_age_s": sig_post_age_s,
            "sig_lp_state": sig_lp_state,
            "sig_lp_detail": sig_lp_detail,
            "sig_lp_age_s": sig_lp_age_s,
            "sig_gate_state": sig_gate_state,
            "sig_gate_detail": sig_gate_detail,
            "sig_gate_age_s": sig_gate_age_s,
            "sig_deploy_state": sig_deploy_state,
            "sig_deploy_detail": sig_deploy_detail,
            "sig_deploy_age_s": sig_deploy_age_s,
            "sig_bridge_state": sig_bridge_state,
            "sig_bridge_detail": sig_bridge_detail,
            "sig_bridge_age_s": sig_bridge_age_s,
            "sig_burn_state": sig_burn_state,
            "sig_burn_detail": sig_burn_detail,
            "sig_burn_age_s": sig_burn_age_s,
        }
        self._render_view()

    def on_resize(self, _event=None) -> None:
        """Re-render on resize so the clipped-row marker tracks the width."""
        self._render_view()

    # -- rendering -----------------------------------------------------

    def _render_view(self) -> None:
        payload = self._payload
        # ``padding: 0 1`` on the body rows costs two columns.  0 means "not
        # laid out yet" -- pass None so rows render untruncated until we know.
        available = max(self.content_size.width - 2, 0) or None
        clipped = False

        for prefix, label, selector in _ROWS:
            state = payload.get(f"sig_{prefix}_state")
            age_s = payload.get(f"sig_{prefix}_age_s")
            head = _head(label, state, age_s)
            markup = _fmt_signal_row(
                label,
                state,
                payload.get(f"sig_{prefix}_detail"),
                age_s,
                available,
            )
            # Only an unfittable *head* is a clipped row: the detail was
            # already shrunk to fit, and flagging that as clipping would keep
            # the marker permanently lit (module docstring).
            if available and visible_len(head) > available:
                clipped = True

            try:
                row = self.query_one(selector, Static)
            except QueryError:
                # Not composed yet -- none of the six rows are, so there is
                # nothing left to update this cycle.  Distinct from the
                # render-failure branch below: this is "the widget tree
                # isn't ready", not "a detail broke the markup parser".
                return

            try:
                row.update(markup)
            except Exception as exc:
                # A detail string can clear ``safe_markup`` (which only
                # neutralises Rich's parser) and still break Textual's own,
                # stricter ``textual.markup`` parser -- the ``]][[/][/
                # malformed`` shape is a real example, and the announce
                # channel this quotes is attacker-writable (PRD §6.4). This
                # must stay a *per-row* failure: the other five detectors
                # still updated this cycle, so this one must not stop them.
                # ``head`` alone is always safe to render -- it is built
                # entirely from this module's own trusted strings (the
                # label, the state word, ``fmt_age``'s output), never from
                # chain-sourced text -- so the detector's true state still
                # shows; only the detail is replaced with an explicit,
                # visibly-wrong marker, never the dead-state dash (which
                # would misreport a successful read as a failed one).
                logger.warning(
                    "SurfSignals: row %s failed to render, showing head only: %s",
                    selector,
                    exc,
                )
                try:
                    row.update(f"{head} [$error]{RENDER_FAILED_DETAIL}[/]")
                except Exception:
                    pass  # even the fallback failed -- leave prior content

        try:
            title = self.query_one("#surf-sig-title", Static)
        except QueryError:
            return
        title.update(f"SIGNALS  [yellow]{WIDEN_HINT}[/]" if clipped else "SIGNALS")
