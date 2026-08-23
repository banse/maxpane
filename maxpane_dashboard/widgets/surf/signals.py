"""The nine-detector panel for the surf dashboard (PRD §3, grown by v4).

One row per detector: NEW POST · LP MOVE · GATE OPEN · NEW DEPLOY ·
BRIDGE STAGE · BURN · DECOY POOL · BURN READY · HOT COIN.  Each row renders
``state · age · one-line detail`` with the state always spelled in words:

* ``fired`` -- ``▶ NEW POST FIRED 2h ago · detail`` in loud bold ``$error``.
  The 24 h FIRED persistence and the baseline math live in
  ``analytics/surf_signals.py``; this widget renders whatever state string
  the manager hands it and adds nothing.
* ``watch`` -- ``◐ NEW DEPLOY WATCH · detail`` in ``$warning``.
* ``ok``    -- ``● LP MOVE OK · detail`` dim.  An ``ok`` row never keeps its
  own line for long: see "Quiet-collapse" below.
* ``None``/unknown -- ``● LP MOVE --`` dim: an unreadable detector is
  unknown, never OK (PRD §6.1's rendering half), and -- unlike ``ok`` -- it
  never folds either (see "Quiet-collapse").

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
label** -- and the detail is cut to fit with a visible ``…`` by
``_cut_detail``, which never lands the cut inside a number: a quantity is shed
whole rather than rendered as ``mint 114,…``.

``clipped``, which lights ``‹ widen`` in the title, is therefore set **only
when the head itself does not fit**.  Testing the whole row would light the
marker permanently: ``analytics/surf_signals`` builds details up to
``DETAIL_LIMIT`` (48) and its relaxed-FIRED form composes
``"... · last: ..."`` on top of that, so real rows run 80-105 columns against
a 51-column panel.  A marker that is always on means nothing, and widening
the layout to clear it would push ``FULL_LAYOUT_COLUMNS`` to ~190 -- past the
~169 columns a laptop gets at the forced 17 pt, i.e. a full layout nobody can
reach.  ``fwa_signals.py`` records the same trap in its ``_GATE_WORDS`` note.

Quiet-collapse -- the rail must not eat the table below it
------------------------------------------------------------

Nine detectors is three more rows than this panel used to carry, and a row
per detector at all times would grow the panel enough to start eating the
dev-activity table beneath it.  So FIRED and WATCH rows always render, one
line each, in PRD §3 order -- but every row whose state is *exactly*
``"ok"`` folds into a single dim ``· N quiet`` line instead of N lines.

The rule this exists to get right, because a nearby dashboard shipped it
backwards: **unknown and dead rows never fold.**  Curator's rail folded a
dead detector group in with its healthy ones and rendered ``none yet`` --
confident and green straight through an outage.  Here, a row whose state is
``None`` or any word outside ``{fired, watch, ok}`` always keeps its own
``--`` line; only a *successful* read of ``ok`` is quiet enough to summarize
away.  ``_fold`` is the predicate; ``_visible_rows`` is its pure, testable
surface, decoupled from age/detail formatting.

Row budget: title + spacer + up to nine rows, minus whatever folds into the
one quiet line.  The panel breathes: roughly 6 lines on a calm day (a few
detectors keep their own line, the rest summarize into one ``quiet`` line)
up to 11 when everything fires (title + spacer + all nine rows, nothing to
fold).

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

#: Characters a written quantity is made of, for the mid-number guard in
#: :func:`_cut_detail`.  Group separators are in here as well as digits: a cut
#: after the comma of ``114,367`` leaves ``114,…``, which is no better than
#: ``114…``.
_NUMBER_CHARS = "0123456789,."


def _cut_detail(text: str, budget: int) -> str:
    """Fit *text* into *budget* columns with a visible ``…``, never mid-number.

    Truncating the detail is normal operation here (see the module docstring):
    it quotes announce-channel prose that routinely runs 80-105 columns against
    a panel with ~51, and it is why this panel's ``‹ widen`` is reserved for a
    head that does not fit.  *Where* the cut lands is the part that is not free
    -- ``mint 114,…`` renders 114,367 as something a reader cannot tell from
    114 thousand or 114 million, with nothing on screen marking the loss.

    So when the cut falls *between* two number characters -- the last kept and
    the first dropped one are both digits or group separators -- the whole
    trailing run goes with it: ``mint 114,367 IMD`` becomes ``mint…`` rather
    than ``mint 114,…`` or ``mint 114…``.  Both spellings were reachable: the
    budget that keeps ``114`` drops a *comma* first, so testing only the
    dropped character for ``isdigit()`` misses exactly one budget per figure.

    A quantity that fits is untouched -- ``burn 15,745 IMD`` cut after the
    figure keeps it whole -- because the guard fires only on a cut *through* a
    number.  This is the trade the hero made when it shed a whole field rather
    than render ``burned 15,74…``, and the same house rule: a number is never
    cut mid-digits.

    Returns ``""`` when nothing but the number would have survived; the caller
    renders the head alone rather than a bare ``…``.
    """
    if len(text) <= budget:
        return text
    kept = text[: budget - 1]
    if kept and kept[-1] in _NUMBER_CHARS and text[budget - 1] in _NUMBER_CHARS:
        kept = kept.rstrip(_NUMBER_CHARS)
    kept = kept.rstrip()
    return f"{kept}…" if kept else ""

#: The nine detector labels, PRD §3 spelling (v4-grown), PRD §3 order.
#: **Interface**: the screen tests and the app-level acceptance tests assert
#: these exact strings reach the compositor -- import this tuple, never
#: retype it, and never shorten a label to save columns (see the module
#: docstring).  ``BRIDGE STAGE`` (12 chars) is the widest and must stay the
#: widest: the row head is unshrinkable, so a longer label costs panel width
#: and this dashboard's layout constants do not move for it.
DETECTOR_LABELS = (
    "NEW POST",
    "LP MOVE",
    "GATE OPEN",
    "NEW DEPLOY",
    "BRIDGE STAGE",
    "BURN",
    "DECOY POOL",
    "BURN READY",
    "HOT COIN",
)

#: payload prefix + child id per detector, aligned 1:1 with DETECTOR_LABELS.
_ROW_KEYS = (
    ("post", "#surf-sig-post"),
    ("lp", "#surf-sig-lp"),
    ("gate", "#surf-sig-gate"),
    ("deploy", "#surf-sig-deploy"),
    ("bridge", "#surf-sig-bridge"),
    ("burn", "#surf-sig-burn"),
    ("decoy", "#surf-sig-decoy"),
    ("burnready", "#surf-sig-burnready"),
    ("hot", "#surf-sig-hot"),
)

#: (payload prefix, row label, child id) for the nine detectors, in PRD order.
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


#: The glyph and style for the collapsed ``ok`` summary line.  Dim, like an
#: OK row's own state word -- quiet detectors should read as quiet.
_QUIET_GLYPH = "·"


def _fold(states: dict) -> tuple[list[str], int]:
    """Split detector prefixes into (rows that keep their own line, quiet count).

    ``states`` maps a short detector prefix (``"post"``, ``"lp"``, ... -- the
    same prefixes as :data:`_ROW_KEYS`) to its raw state value.

    Only a state that is *exactly* ``"ok"`` folds.  ``None`` and anything
    else outside the known vocabulary is unknown, and an unknown row always
    keeps its own line -- see the module docstring's Quiet-collapse section:
    this is the rule curator's rail shipped backwards, where a dead detector
    group folded in with the healthy ones and read as confident and green
    straight through an outage.
    """
    visible_prefixes: list[str] = []
    quiet = 0
    for prefix, _selector in _ROW_KEYS:
        state = states.get(prefix)
        # NOTE: this predicate is the thing under test -- deliberately
        # comparing the *raw* state to the literal string "ok", not a
        # normalised/lower-cased form, so that `None` cannot accidentally
        # satisfy it.  See test_an_unknown_row_never_folds's mutation proof.
        if state == "ok":
            quiet += 1
        else:
            visible_prefixes.append(prefix)
    return visible_prefixes, quiet


#: prefix -> PRD §3 label, built once from the two aligned tuples above.
_LABEL_BY_PREFIX = dict(zip((prefix for prefix, _ in _ROW_KEYS), DETECTOR_LABELS))


def _visible_rows(states: dict) -> str:
    """Pure preview of the fold rule, keyed by short prefix -> raw state.

    This is a test surface for :func:`_fold`, decoupled from age/detail
    formatting: each row that keeps its own line renders as just its label,
    and every state-``"ok"`` row is summarized into one trailing
    ``"· N quiet"`` line (omitted entirely when nothing is quiet).  The real
    per-row rendering -- state word, age, detail -- happens in
    ``SurfSignals._render_view``, which calls :func:`_fold` for the same
    split and then builds each visible row with :func:`_head` /
    :func:`_fmt_signal_row` as before.
    """
    visible_prefixes, quiet = _fold(states)
    lines = [_LABEL_BY_PREFIX[prefix] for prefix in visible_prefixes]
    if quiet:
        lines.append(f"{_QUIET_GLYPH} {quiet} quiet")
    return "\n".join(lines)


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
        flat = _cut_detail(flat, budget)
        if not flat:
            # Only a bisected number would have fitted: the head renders
            # alone, which is what this widget already does for a budget
            # below MIN_DETAIL_COLS -- never a bare "…".
            return head

    return f"{head} [dim]· {safe_markup(flat)}[/]"


class SurfSignals(Vertical):
    """Detector panel with up to nine rows, collapsing quiet ones."""

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
        # The one collapsed-``ok`` summary line, positioned after all nine
        # detector slots so it always reads as "and everything else" rather
        # than displacing whichever detectors happen to keep their own line.
        yield Static("", classes="surf-signals-body", id="surf-sig-quiet")

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
        sig_decoy_state=None,
        sig_decoy_detail=None,
        sig_decoy_age_s=None,
        sig_burnready_state=None,
        sig_burnready_detail=None,
        sig_burnready_age_s=None,
        sig_hot_state=None,
        sig_hot_detail=None,
        sig_hot_age_s=None,
        **_kwargs,
    ) -> None:
        """Refresh the nine rows.  Kwargs are exactly the PRD §5 signal keys."""
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
            "sig_decoy_state": sig_decoy_state,
            "sig_decoy_detail": sig_decoy_detail,
            "sig_decoy_age_s": sig_decoy_age_s,
            "sig_burnready_state": sig_burnready_state,
            "sig_burnready_detail": sig_burnready_detail,
            "sig_burnready_age_s": sig_burnready_age_s,
            "sig_hot_state": sig_hot_state,
            "sig_hot_detail": sig_hot_detail,
            "sig_hot_age_s": sig_hot_age_s,
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

        states = {prefix: payload.get(f"sig_{prefix}_state") for prefix, _, _ in _ROWS}
        visible_prefixes, quiet = _fold(states)
        visible = set(visible_prefixes)

        for prefix, label, selector in _ROWS:
            try:
                row = self.query_one(selector, Static)
            except QueryError:
                # Not composed yet -- none of the rows are, so there is
                # nothing left to update this cycle.  Distinct from the
                # render-failure branch below: this is "the widget tree
                # isn't ready", not "a detail broke the markup parser".
                return

            if prefix not in visible:
                # Folded into the quiet line below: no line of its own, so
                # nothing to measure for clipping and nothing to render --
                # an ``ok`` row's detail is never shown once it is quiet.
                row.display = False
                continue
            row.display = True

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
                row.update(markup)
            except Exception as exc:
                # A detail string can clear ``safe_markup`` (which only
                # neutralises Rich's parser) and still break Textual's own,
                # stricter ``textual.markup`` parser -- the ``]][[/][/
                # malformed`` shape is a real example, and the announce
                # channel this quotes is attacker-writable (PRD §6.4). This
                # must stay a *per-row* failure: the other visible detectors
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
            quiet_row = self.query_one("#surf-sig-quiet", Static)
        except QueryError:
            return
        if quiet:
            quiet_row.display = True
            quiet_text = f"  [dim]{_QUIET_GLYPH} {quiet} quiet[/]"
            if available and visible_len(quiet_text) > available:
                clipped = True
            quiet_row.update(quiet_text)
        else:
            quiet_row.display = False

        try:
            title = self.query_one("#surf-sig-title", Static)
        except QueryError:
            return
        title.update(f"SIGNALS  [yellow]{WIDEN_HINT}[/]" if clipped else "SIGNALS")
