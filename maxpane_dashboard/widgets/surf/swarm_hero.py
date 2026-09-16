"""The `s` swarm body's own hero: AGENTS · IN FLIGHT · ACCEPTED TODAY.

A **second** hero, swapped with the swarm body the way curator swaps its
per-mode heroes and the `4` POOL4 MARKET body swaps in
``SurfPool4UserHero`` -- not a rewrite of ``widgets/surf/hero.py``, which
keeps answering LAUNCHPAD/FLOW/BURN/SUPPLY for the dashboard, ``l`` and ``p``
bodies. Mounting and toggling both is a later task's job (the screen owns
``compose``); this module only knows how to paint three cards from the
frozen ``swarm_*`` contract (spec §4/§5).

Copied from ``widgets/surf/pool4u_hero.py``, the precedent this task was
pointed at: a ``Horizontal`` of three ``Static`` cards, ``height: 6``,
``padding: 0 2``, ``margin: 0 1``, ``border: solid $panel``, **no vertical
padding** (it silently clips the subtitle -- the WP-10 hazard note in
``fwa_hero_metrics.py``), every card rewritten on every ``update_data`` call
(a skipped card keeps last poll's number, or ``Loading...`` forever if the
first poll was the one that failed -- MEDI-38), ``update_data(..., **_kwargs)``
because the screen splats the whole payload, and ``on_resize`` re-rendering
at the new width.

Two rules worth restating because this module is where a fresh reader will
look for them:

1. **A successful read with nothing executing publishes ``0``; a missing
   read publishes ``None``.** ``swarm_agents_online`` through
   ``swarm_jobs_blocked`` are coerced with ``_fmt.as_float`` and a real zero
   renders as a zero -- ``"0 in flight"``, ``"working 0"``, ``"accepted 0"``
   -- never silently dropped or coerced from ``None``. Only ``None`` reaches
   :data:`UNAVAILABLE`. This is the curator rail bug (CLAUDE.md) applied to
   a hero card, and it is what the Step-3 mutation in the task brief proves:
   folding ``None`` into ``0`` turns ``test_an_unread_count_says_so_and_
   never_prints_zero`` red.
2. **``swarm_services_up`` carries three states, not two, and it lives on
   AGENTS.** Spec §5: *"AGENTS — online of enrolled, plus whether verifier,
   publisher and deployer are up."* ``True`` is up, ``False`` is down, and a
   missing key (or the whole dict read as anything but a ``dict``) is
   *unreported* -- a service nobody asked about, which is not the same claim
   as "asked and it said no". All three render with a different word and
   colour (``up`` green, ``down`` red, ``?`` dim) rather than collapsing the
   unreported case into either neighbour, but AGENTS's subtitle line does
   not *list* all three every time: naming all three unconditionally (every
   render, even the all-up case) ran the line to ~40 cells for no reason
   most of the time, so it **summarises** -- ``all services up`` when
   nothing is wrong, and otherwise only the exceptions (``verifier down``,
   or ``publisher ?``), joined by `` · `` -- which keeps the three-state
   distinction while fitting a card at any width this dashboard renders one
   at (worst case, all three exceptions named, is 48 cells measured with
   ``rich.cells.cell_len`` rather than ``len()``, comfortably inside a third
   of even a narrow terminal; ``SurfSwarmHeroBox``'s own CSS
   (``text-wrap: nowrap; text-overflow: ellipsis``) is the same fallback
   every other line in this file already relies on for anything narrower
   still).

``swarm_working_now`` is not part of AGENTS at all (spec §5 does not mention
it there): it is a "right now" fact and rides on IN FLIGHT's subtitle
instead, beside the blocked count (``"6 blocked · working 0"``). ACCEPTED
TODAY's subtitle carries no service text and, since spec §5 names nothing
else for it beyond the value itself ("accepted in the last day"), is blank.

Every line reaches ``Static`` as a pre-built ``rich.text.Text``, parsed here
inside ``_pool4.parse_line``'s own ``try`` -- ``Static.update("…[/x]…")``
parses nothing at call time, and the deferred ``Content.from_markup`` inside
Textual's message pump would raise outside this widget's own ``try/except``
and take the app down (``SurfFeed._row_text`` is the worked example this
rule comes from). None of this hero's inputs are third-party strings -- they
are counts and booleans off the manager's own fold -- but every value this
module writes still passes through ``safe_markup`` before it reaches a
markup tag, on the same belt-and-suspenders convention ``pool4u_hero`` uses.

Purity
------
Stdlib, ``rich``, ``textual``, and this package's own ``_fmt``/``_pool4``
primitives. No ``data/``, no ``analytics/``, no clock, no I/O.
"""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static

from maxpane_dashboard.widgets.markup_safety import safe_markup
from maxpane_dashboard.widgets.surf._fmt import DASH, as_float
from maxpane_dashboard.widgets.surf._pool4 import join_lines, parse_line

__all__ = [
    "CARD_IDS",
    "TITLE_ACCEPTED",
    "TITLE_AGENTS",
    "TITLE_IN_FLIGHT",
    "UNAVAILABLE",
    "SurfSwarmHero",
    "SurfSwarmHeroBox",
]

# ---------------------------------------------------------------------------
# Copy
# ---------------------------------------------------------------------------

TITLE_AGENTS = "AGENTS"
TITLE_IN_FLIGHT = "IN FLIGHT"
TITLE_ACCEPTED = "ACCEPTED TODAY"

#: What a card renders when its own read failed. One spelling, shared by all
#: three cards, the same convention ``pool4u_hero`` established.
UNAVAILABLE = "unavailable"

CARD_IDS = (
    "surf-swarm-hero-agents",
    "surf-swarm-hero-flight",
    "surf-swarm-hero-accepted",
)

#: Fixed rendering order for the three swarm services -- the order the
#: manager's own comment names them (``surf_models.SWARM_KEYS``:
#: ``swarm_services_up  # dict | None  -- verifier/publisher/deployer``).
_SERVICE_NAMES = ("verifier", "publisher", "deployer")

# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _dim(text: str) -> str:
    return f"[dim]{safe_markup(text)}[/]" if text else "[dim] [/]"


def _service_word(name: str, state: object) -> str:
    """One service's rendered word -- three states, three spellings, **plain**.

    ``True`` -> ``"{name} up"``. ``False`` -> ``"{name} down"``, the state
    ``test_a_down_service_is_named_and_the_others_are_not`` pins. Anything
    else, ``None`` included, is *unreported* -- ``"{name} ?"`` rather than
    folded into ``down``, which would claim a service failed when nobody
    actually asked it (``test_an_unreported_service_is_marked_distinctly``
    pins this one; a mutation that folds ``None`` into the down branch is
    what proves it).

    Deliberately **not** individually coloured. A per-word ``[red]``/
    ``[green]``/``[dim]`` tag here would be markup, and :func:`_services_line`
    hands its whole return value to ``_render_card``'s ``_dim()``, which
    ``safe_markup``-escapes the string before wrapping it -- correct for the
    plain text every other subtitle in this file is, and exactly why one
    subtitle secretly carrying its own tags is a bug rather than a style
    choice: escaping turns ``[red]verifier down[/]`` into the literal text
    ``\\[red]verifier down\\[/]`` on screen. Found rendering this card by eye
    during this fix. The three words already read as three different
    *states* without colour riding along; :func:`_dim` still dims the whole
    line, same as IN FLIGHT's and ACCEPTED TODAY's subtitles.
    """
    if state is True:
        return f"{name} up"
    if state is False:
        return f"{name} down"
    return f"{name} ?"


def _services_line(services_up: object) -> str:
    """AGENTS's own subtitle -- a summary, never all three named unconditionally.

    A non-``dict`` payload (``None`` included -- the whole read failed)
    treats every service as unreported rather than raising or going blank: a
    missing dict and a dict with no keys mean the same thing to a caller who
    only ever does ``.get(name)``, and with nothing marked ``True`` every one
    of the three becomes an "exception" below, which is the honest outcome
    for "we could not read any of this".

    Every service that reports ``True`` is silently fine and earns no
    mention; everything else -- ``down`` and unreported alike -- is named.
    All three up is the common case and costs nine cells
    (``all services up``); a mutation that hardcodes the down branch (making
    every service render ``"{name} down"`` regardless of its real state) is
    what ``test_all_services_up_summarises_instead_of_listing`` catches --
    it would stop saying ``all services up`` the moment any input is asked
    for, including the all-``True`` one. Worst case, all three exceptions
    named (``"verifier down · publisher down · deployer down"``, measured at
    46 cells with ``rich.cells.cell_len`` rather than ``len()``), still fits
    a hero card at any width this dashboard renders one at; ``SurfSwarmHeroBox``'s
    own CSS (``text-wrap: nowrap; text-overflow: ellipsis``) is the same
    fallback every other line in this file already relies on for anything
    narrower still, so no further compression is added here.

    Returns **plain text** -- see :func:`_service_word` for why this line
    carries no markup of its own and lets ``_render_card``'s ``_dim()`` do
    the one escape-and-style pass every other subtitle in this file gets.

    ``_service_word`` is called for **every** service, up ones included, and
    the "is this an exception" question is asked of its own *output*
    (``not word.endswith(" up")``) rather than re-deriving the up/down/
    unreported split here a second time. That is what makes the hardcoded-
    down mutation a real mutation of the summary itself: a version of
    :func:`_service_word` that always answers ``"{name} down"`` would make
    every rendered word fail the ``endswith(" up")`` check, including the
    all-``True`` case, so the all-up case would stop saying
    ``all services up`` -- which is exactly what
    ``test_all_services_up_summarises_instead_of_listing`` catches. Filtering
    on the *state* before calling :func:`_service_word` (an earlier draft of
    this function) would have called it only for exceptions and left that
    same mutation invisible to the all-up case entirely.
    """
    data = services_up if isinstance(services_up, dict) else {}
    words = [_service_word(name, data.get(name)) for name in _SERVICE_NAMES]
    exceptions = [word for word in words if not word.endswith(" up")]
    if not exceptions:
        return "all services up"
    return " · ".join(exceptions)


# ---------------------------------------------------------------------------
# Card bodies.  Each returns (value markup, subtitle markup).
# ---------------------------------------------------------------------------


def _agents_card(online, enrolled, services_up) -> tuple[str, str]:
    """AGENTS -- ``N of M`` connected of enrolled, and the three services.

    Spec §5: *"online of enrolled, plus whether verifier, publisher and
    deployer are up."* Both halves of the fraction have to be real reads: an
    enrolled count with no online count (or the reverse) is not a fraction
    anyone can act on, so either missing half takes the whole value to
    :data:`UNAVAILABLE` rather than printing a fraction with a guessed side.
    """
    o = as_float(online)
    e = as_float(enrolled)
    if o is None or e is None:
        value = ""
    else:
        value = f"[bold white]{safe_markup(f'{int(o)} of {int(e)}')}[/]"

    subtitle = _services_line(services_up)
    return value, subtitle


def _in_flight_card(in_flight, blocked, working) -> tuple[str, str]:
    """IN FLIGHT -- jobs executing now, how many sit blocked, and who works now.

    ``swarm_working_now`` rides here rather than on AGENTS: it is a "right
    now" fact about the swarm the same way ``jobs_in_flight`` is, and spec
    §5 does not mention it on AGENTS at all.
    """
    f = as_float(in_flight)
    value = (
        f"[bold white]{safe_markup(f'{int(f)} in flight')}[/]"
        if f is not None
        else ""
    )

    b = as_float(blocked)
    blocked_part = f"{int(b)} blocked" if b is not None else f"{DASH} blocked"
    w = as_float(working)
    working_part = f"working {int(w)}" if w is not None else f"working {DASH}"
    subtitle = f"{blocked_part} · {working_part}"
    return value, subtitle


def _accepted_card(accepted_today) -> tuple[str, str]:
    """ACCEPTED TODAY -- jobs accepted in the last day.

    Spec §5 names nothing else for this card beyond the count itself, so the
    subtitle carries no second fact -- blank rather than restating the value
    or borrowing a fact that belongs to another card.
    """
    a = as_float(accepted_today)
    value = (
        f"[bold white]{safe_markup(f'accepted {int(a)}')}[/]"
        if a is not None
        else ""
    )
    return value, ""


# ---------------------------------------------------------------------------
# Widgets
# ---------------------------------------------------------------------------


class SurfSwarmHeroBox(Static):
    """One hero card: a dim label, a blank, the value, a dim subtitle.

    Four lines, ``SurfPool4UserHeroBox``'s shape: this row's three cards
    each carry exactly one fact and one clause about it, same as that body's
    own hero.
    """


class SurfSwarmHero(Horizontal):
    """AGENTS · IN FLIGHT · ACCEPTED TODAY -- the `s` body's own hero row."""

    #: Height 6 for four content lines: the ``solid`` border takes a row top
    #: and bottom and the padding is horizontal only. Vertical padding here
    #: would clip the subtitle in silence (the WP-10 hazard note in
    #: ``fwa_hero_metrics.py``, repeated by ``pool4u_hero`` for the same
    #: reason).
    DEFAULT_CSS = """
    SurfSwarmHero {
        height: 6;
    }
    SurfSwarmHero > SurfSwarmHeroBox {
        width: 1fr;
        height: 6;
        padding: 0 2;
        margin: 0 1;
        border: solid $panel;
        background: $surface;
        content-align: center middle;
        text-align: center;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # The raw values, not formatted lines, so a resize re-lays them out.
        self._payload: dict = {}

    def compose(self) -> ComposeResult:
        for card_id in CARD_IDS:
            yield SurfSwarmHeroBox(
                Text("Loading...", style="dim"),
                id=card_id,
                classes="surf-swarm-hero-box",
            )

    def update_data(
        self,
        swarm_agents_online=None,
        swarm_agents_enrolled=None,
        swarm_working_now=None,
        swarm_accepted_today=None,
        swarm_jobs_in_flight=None,
        swarm_jobs_blocked=None,
        swarm_services_up=None,
        **_kwargs,
    ) -> None:
        """Refresh all three cards from the manager's flat dict.

        Every kwarg is spelled after its full ``swarm_`` contract key
        (``data/surf_models.SWARM_KEYS``). ``**_kwargs`` is mandatory: the
        screen splats the whole payload and a key added tomorrow (or one
        this hero simply does not need, like ``swarm_queue_depths``) must be
        ignored rather than raise.
        """
        self._payload = {
            "agents_online": swarm_agents_online,
            "agents_enrolled": swarm_agents_enrolled,
            "working_now": swarm_working_now,
            "accepted_today": swarm_accepted_today,
            "jobs_in_flight": swarm_jobs_in_flight,
            "jobs_blocked": swarm_jobs_blocked,
            "services_up": swarm_services_up,
            "seen": True,
        }
        self._render_view()

    def on_resize(self, _event=None) -> None:
        if self._payload:
            self._render_view()

    def _render_view(self) -> None:
        data = self._payload
        cards = (
            (CARD_IDS[0], TITLE_AGENTS, _agents_card(
                data.get("agents_online"),
                data.get("agents_enrolled"),
                data.get("services_up"),
            )),
            (CARD_IDS[1], TITLE_IN_FLIGHT, _in_flight_card(
                data.get("jobs_in_flight"),
                data.get("jobs_blocked"),
                data.get("working_now"),
            )),
            (CARD_IDS[2], TITLE_ACCEPTED, _accepted_card(
                data.get("accepted_today"),
            )),
        )
        for card_id, label, (value, subtitle) in cards:
            self._render_card(card_id, label, value, subtitle)

    def _render_card(
        self, card_id: str, label: str, value: str, subtitle: str
    ) -> None:
        """Write one card, always, degrading to an explicit unavailable state.

        Never a skip and never an early return before the write: a card that
        is not written keeps its previous contents, so a poll that lost this
        one value would leave last poll's number on screen under a title bar
        claiming the payload is seconds old.
        """
        try:
            box = self.query_one(f"#{card_id}", SurfSwarmHeroBox)
        except Exception:  # not composed yet
            return

        markup = [
            _dim(label),
            "",
            value or f"[yellow]{UNAVAILABLE}[/]",
            _dim(subtitle),
        ]
        lines = [t for t in (parse_line(m) for m in markup) if t is not None]
        try:
            box.update(join_lines(lines))
        except Exception:
            # Last resort: the label and the unavailable word, as plain text
            # with no parsing step left to fail.
            try:
                box.update(Text(f"{label}\n\n{UNAVAILABLE}"))
            except Exception:
                pass
