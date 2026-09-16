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
2. **``swarm_services_up`` carries three states, not two.** ``True`` is up,
   ``False`` is down, and a missing key (or the whole dict read as anything
   but a ``dict``) is *unreported* -- a service nobody asked about, which is
   not the same claim as "asked and it said no". All three render with a
   different word and colour (``up`` green, ``down`` red, ``?`` dim) rather
   than collapsing the unreported case into either neighbour.

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
    """One service's rendered word -- three states, three spellings.

    ``True`` -> up (green). ``False`` -> down (red), the state
    ``test_a_service_that_is_down_is_named`` pins. Anything else, ``None``
    included, is *unreported* -- rendered dim with ``?`` rather than folded
    into ``down``, which would claim a service failed when nobody actually
    asked it.
    """
    if state is True:
        return f"[green]{safe_markup(f'{name} up')}[/]"
    if state is False:
        return f"[red]{safe_markup(f'{name} down')}[/]"
    return f"[dim]{safe_markup(f'{name} ?')}[/]"


def _services_line(services_up: object) -> str:
    """All three services, in fixed order, each in its own distinguishable state.

    A non-``dict`` payload (``None`` included -- the whole read failed)
    renders every service ``?`` rather than raising or going blank: a
    missing dict and a dict with no keys mean the same thing to a caller
    who only ever does ``.get(name)``.
    """
    data = services_up if isinstance(services_up, dict) else {}
    return " · ".join(_service_word(name, data.get(name)) for name in _SERVICE_NAMES)


# ---------------------------------------------------------------------------
# Card bodies.  Each returns (value markup, subtitle markup).
# ---------------------------------------------------------------------------


def _agents_card(online, enrolled, working) -> tuple[str, str]:
    """AGENTS -- ``N of M`` connected of enrolled, and how many work now.

    Both halves of the fraction have to be real reads: an enrolled count
    with no online count (or the reverse) is not a fraction anyone can act
    on, so either missing half takes the whole value to
    :data:`UNAVAILABLE` rather than printing a fraction with a guessed side.
    """
    o = as_float(online)
    e = as_float(enrolled)
    if o is None or e is None:
        value = ""
    else:
        value = f"[bold white]{safe_markup(f'{int(o)} of {int(e)}')}[/]"

    w = as_float(working)
    subtitle = f"working {int(w)}" if w is not None else f"working {DASH}"
    return value, subtitle


def _in_flight_card(in_flight, blocked) -> tuple[str, str]:
    """IN FLIGHT -- jobs executing now, and how many sit blocked beside them."""
    f = as_float(in_flight)
    value = (
        f"[bold white]{safe_markup(f'{int(f)} in flight')}[/]"
        if f is not None
        else ""
    )

    b = as_float(blocked)
    subtitle = f"{int(b)} blocked" if b is not None else f"{DASH} blocked"
    return value, subtitle


def _accepted_card(accepted_today, services_up) -> tuple[str, str]:
    """ACCEPTED TODAY -- jobs accepted in the last day, and the three services."""
    a = as_float(accepted_today)
    value = (
        f"[bold white]{safe_markup(f'accepted {int(a)}')}[/]"
        if a is not None
        else ""
    )
    subtitle = _services_line(services_up)
    return value, subtitle


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
                data.get("working_now"),
            )),
            (CARD_IDS[1], TITLE_IN_FLIGHT, _in_flight_card(
                data.get("jobs_in_flight"),
                data.get("jobs_blocked"),
            )),
            (CARD_IDS[2], TITLE_ACCEPTED, _accepted_card(
                data.get("accepted_today"),
                data.get("services_up"),
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
