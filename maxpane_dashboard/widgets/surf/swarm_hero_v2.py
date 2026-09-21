"""The `s` swarm body's hero, rebuilt on ``panels.HeroRow`` (swarm v2, WP5).

Six boxes -- AGENTS · WORKING · ACCEPTED 24h · QUEUE · BREAKER · SERVICES --
each one fact off the frozen ``swarm_*`` contract
(``data/surf_models.SWARM_WIDGET_SIGNATURES["SurfSwarmHero"]``, plan §1.1/§2).

**Transitional names, unwired until WP7.** The live screen still mounts the
old ``swarm_hero.SurfSwarmHero``; this module is ``swarm_hero_v2`` and its
classes carry a ``V2`` suffix so both can exist in one tree while WP6/WP6a
write beside it. WP7 deletes the old module, renames this one to
``swarm_hero.py`` / ``SurfSwarmHero`` / ``SurfSwarmHeroBox`` in a single
commit, exports it from ``widgets/surf/__init__.py`` and writes the
stylesheet block that gives ``SurfSwarmHeroBoxV2`` its geometry. Its tests
already bind to the final name's signature, so the rename costs them no
edit.

What is kept from the old hero, behaviour not code
--------------------------------------------------
* **A real zero is a zero; only ``None`` is unavailable.** ``0`` working,
  ``0`` accepted, ``0`` queued all print ``0`` (``fmt_int``); ``None`` lands
  on :data:`panels.UNAVAILABLE`. The curator rail bug applied to a hero.
* **Services carry three states.** ``True`` up, ``False`` down, missing
  *unreported* -- a service nobody asked about is not one that said no. The
  all-up case is **summarised** (:data:`ALL_SERVICES_UP`, 15 cells) rather
  than listing three green dots on every render; anything less than all-up
  lists **every** service once, with a green or red ``●`` beside its name
  and a dim ``?`` for one the dict does not report. Worst case
  ``verifier ● publisher ● deployer ?`` is 33 cells measured on
  ``rich.cells.cell_len`` -- WP7's sweep decides what box width buys it.
  A ``swarm_services_up`` that is ``None`` or not a dict at all is the
  **whole read failing** and says ``unavailable`` like every other box
  (the common rule "a dict that is ``None`` → unavailable"; the old hero
  folded that case into three ``?``, which claimed three separate
  unreported services where there was one failed read).

New in v2
---------
* **AGENTS** is ``online/enrolled`` -- ``27/32`` -- and a missing *half*
  is ``--`` on its own side (``--/32``), because the other half is still a
  real read; only both missing is ``unavailable``.
* **QUEUE** is ``swarm_queue_total``, the sum of every ``/health.pending*``
  counter; ``0`` is a real empty queue.
* **BREAKER** is the deploy breaker, three facts kept apart: not tripped
  is the em dash (a clean negative, not a number); tripped is the host's
  ``detail`` in red, or the word ``tripped`` when there is none; ``None``
  (or anything but a dict) is ``unavailable`` -- the two are different
  facts and must never look alike (plan §1.1).

Third-party text
----------------
The breaker ``detail`` is the one string here the host writes. It is
flattened, clipped to the box's own measured width (``rowfit.clip`` on
``cell_len``, a visible ``…``) and handed to ``render_box`` as a
pre-built ``rich.text.Text`` -- ``Text(...)`` parses nothing, so a
``[/x]`` renders as the literal four characters and a ``[$success]``
cannot raise; there is no markup step for an escape to guard.
``markup_safety.sanitize_cell`` was *not* used for it on purpose: its
``strip_tags`` step deletes a complete ``[...]`` run outright, and the plan
(WP5) requires a hostile tag to **render literally**, which a stripped
string cannot do. Every other value is a count the manager's own fold
produced; those go through the ``str`` path with ``safe_markup`` on the
belt-and-suspenders convention the old hero kept.

Geometry
--------
None here (``rules/widgets.md``, ``HeroBoxBase``): ``SurfSwarmHeroBoxV2``
exists so WP7's ``minimal.tcss`` can name it. The label / blank / value
rows are ``HeroRow.render_box``'s ``\\n\\n``. The row re-renders on
resize because the breaker detail is clipped to a measured width.

Purity: stdlib, ``rich``, ``textual``, ``widgets/panels``, ``widgets/fmt``,
``widgets/rowfit``, ``widgets/markup_safety``. No ``data/``, no
``analytics/``, no clock, no I/O.
"""

from __future__ import annotations

from rich.text import Text

from maxpane_dashboard.widgets.fmt import DASH, EMDASH, fmt_int
from maxpane_dashboard.widgets.markup_safety import flatten, safe_markup
from maxpane_dashboard.widgets.panels import UNAVAILABLE, HeroBoxBase, HeroRow
from maxpane_dashboard.widgets.rowfit import clip

__all__ = [
    "ALL_SERVICES_UP",
    "BOX_IDS",
    "SERVICE_NAMES",
    "SurfSwarmHeroBoxV2",
    "SurfSwarmHeroV2",
]

#: The all-up summary, the old hero's own wording (15 cells).
ALL_SERVICES_UP = "all services up"

#: Fixed rendering order for the three swarm services -- the order the
#: contract's own comment names them (``surf_models.SWARM_KEYS``:
#: ``swarm_services_up  # dict | None  -- verifier/publisher/deployer``).
SERVICE_NAMES = ("verifier", "publisher", "deployer")

#: ``(widget id, label)`` per box, in row order (plan §2's hero line).
BOXES: tuple[tuple[str, str], ...] = (
    ("surf-swarm-hero-agents", "AGENTS"),
    ("surf-swarm-hero-working", "WORKING"),
    ("surf-swarm-hero-accepted", "ACCEPTED 24h"),
    ("surf-swarm-hero-queue", "QUEUE"),
    ("surf-swarm-hero-breaker", "BREAKER"),
    ("surf-swarm-hero-services", "SERVICES"),
)

BOX_IDS: tuple[str, ...] = tuple(box_id for box_id, _label in BOXES)

_VALUE_STYLE = "bold white"


def _int_or_none(value) -> int | None:
    """``fmt_int``'s own acceptance, as a predicate: ``None`` when it would dash."""
    if value is None or isinstance(value, bool):
        return None
    text = fmt_int(value)
    return None if text == DASH else int(value)


def _value(text: str) -> str:
    return f"[{_VALUE_STYLE}]{safe_markup(text)}[/]"


# -- box bodies -----------------------------------------------------------------


def _agents_body(online, enrolled) -> str:
    """``online/enrolled``; ``--`` for a missing half; unavailable for both."""
    o = _int_or_none(online)
    e = _int_or_none(enrolled)
    if o is None and e is None:
        return UNAVAILABLE
    return _value(f"{fmt_int(o)}/{fmt_int(e)}")


def _count_body(value) -> str:
    """One grouped integer; ``0`` is a number; ``None`` is unavailable."""
    if _int_or_none(value) is None:
        return UNAVAILABLE
    return _value(fmt_int(value))


def _breaker_body(breaker, width: int) -> "str | Text":
    """Em dash / red detail (or ``tripped``) / unavailable -- three facts."""
    if not isinstance(breaker, dict):
        return UNAVAILABLE
    if not breaker.get("tripped"):
        return _value(EMDASH)
    detail = breaker.get("detail")
    if detail is None:
        return Text("tripped", style="red")
    flat = flatten(detail)
    if not flat:
        return Text("tripped", style="red")
    shown = clip(flat, width) if width > 0 else flat
    return Text(shown, style="red")


def _services_body(services_up) -> "str | Text":
    """``all services up``, or every service once with its own glyph."""
    if not isinstance(services_up, dict):
        return UNAVAILABLE
    states = [services_up.get(name) for name in SERVICE_NAMES]
    if all(state is True for state in states):
        return _value(ALL_SERVICES_UP)
    line = Text()
    for index, (name, state) in enumerate(zip(SERVICE_NAMES, states)):
        if index:
            line.append(" ")
        line.append(name, style=_VALUE_STYLE)
        line.append(" ")
        if state is True:
            line.append("●", style="green")
        elif state is False:
            line.append("●", style="red")
        else:
            line.append("?", style="dim")
    return line


# -- widgets ----------------------------------------------------------------------


class SurfSwarmHeroBoxV2(HeroBoxBase):
    """One swarm hero box. No geometry here: WP7's stylesheet names this class."""


class SurfSwarmHeroV2(HeroRow):
    """AGENTS · WORKING · ACCEPTED 24h · QUEUE · BREAKER · SERVICES."""

    BOX_CLASS = SurfSwarmHeroBoxV2
    BOXES = BOXES

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        #: The raw payload, kept so a resize re-clips the breaker detail to
        #: the box's new width rather than leaving last width's cut on screen.
        self._payload: dict | None = None

    def update_data(
        self,
        swarm_agents_online=None,
        swarm_agents_enrolled=None,
        swarm_working_now=None,
        swarm_accepted_today=None,
        swarm_queue_total=None,
        swarm_breaker=None,
        swarm_services_up=None,
        **_kwargs,
    ) -> None:
        """Refresh all six boxes; every box is written on every poll (MEDI-38).

        ``**_kwargs`` is mandatory: the screen splats the whole flat dict.
        """
        self._payload = {
            "online": swarm_agents_online,
            "enrolled": swarm_agents_enrolled,
            "working": swarm_working_now,
            "accepted": swarm_accepted_today,
            "queue": swarm_queue_total,
            "breaker": swarm_breaker,
            "services": swarm_services_up,
        }
        self._render_view()

    def on_resize(self, _event=None) -> None:
        if self._payload is not None:
            self._render_view()

    def _box_width(self, box_id: str) -> int:
        """The box's own content width, measured in situ; ``0`` before layout."""
        try:
            return max(self.query_one(f"#{box_id}", HeroBoxBase).content_size.width, 0)
        except Exception:
            return 0

    def _render_view(self) -> None:
        data = self._payload or {}
        agents, working, accepted, queue, breaker, services = BOX_IDS
        self.render_box(
            f"#{agents}", "AGENTS",
            lambda: _agents_body(data.get("online"), data.get("enrolled")),
        )
        self.render_box(
            f"#{working}", "WORKING", lambda: _count_body(data.get("working")),
        )
        self.render_box(
            f"#{accepted}", "ACCEPTED 24h", lambda: _count_body(data.get("accepted")),
        )
        self.render_box(
            f"#{queue}", "QUEUE", lambda: _count_body(data.get("queue")),
        )
        self.render_box(
            f"#{breaker}", "BREAKER",
            lambda: _breaker_body(data.get("breaker"), self._box_width(breaker)),
        )
        self.render_box(
            f"#{services}", "SERVICES", lambda: _services_body(data.get("services")),
        )
