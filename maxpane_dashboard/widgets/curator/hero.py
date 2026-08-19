"""Hero row for the curator dashboard: CLOCK · THE LIST · CURVE (PRD §3).

Three boxes driven by one derived value, ``phase``.  The widget branches on
it; it never computes it, never reads a clock, and never decides whether the
game is over — ``analytics/curator_signals`` does all three against an
injected clock, and a countdown here is poll-anchored text (PRD §2).

======  ==========================  =========================  ==================
box     grace                       judged                     settled
======  ==========================  =========================  ==================
CLOCK   ``GRACE`` + judging begins  ``HOUR N`` + fed/left      ``SETTLED AT HOUR N``
LIST    wallets · routed · OPEN     same                       same, ``FROZEN``
CURVE   early-bird decay + rate     survival + closest call    final records
======  ==========================  =========================  ==================

Why the volume line reads "routed (all refunded)"
-------------------------------------------------

``WhitelistCurator`` refunds every wei inside the same transaction.  The
number under THE LIST is therefore *gas-priced flow*, not money at stake, and
the strings TVL / locked / at risk / capital next to it would not be loose
wording — they would be a false claim about money at risk, on a dashboard
somebody reads while deciding whether to send 60 ETH (H4).  The phrase is
kept **contiguous on one line** at every tier that can hold it, because a
"routed" on one line and an "all refunded" on the next is one clipped row
away from being just "routed".

The row **subtitle**, once, spanning the full width, tells the reader how to
turn the capped live list into the complete exported list.

Why there is a fourth line under the boxes
------------------------------------------

The hero is a ``Vertical``: three boxes (height 7) over that one subtitle
line, so the row is **8 rows tall**, one more than the surf/FWA hero.  The
alternative was a fourth content line inside a box, which would have put the
sentence beside a volume figure — exactly what H4 forbids — or a border
subtitle, which Textual truncates silently and which this row already spends
on the ``‹ widen`` marker.

Width behaviour
---------------

A box is one third of the full-width row: measured, **39 content columns at
the 143-column full layout**, 25 at 100 and 18 at 80.  Each box picks its
tier from *its own* width, because ``1fr`` rounding leaves neighbours a
column apart and the narrow one has to fit.

===========  =====  =====================================================
Tier         Needs  What it gives up
===========  =====  =====================================================
``full``     26     nothing
``compact``  21     ``judging begins in`` -> ``begins in``;
                    ``1 ETH ≈ N pts now`` -> ``1 ETH ≈ N pts``
``minimal``  18     the parenthetical form of ``routed (all refunded)``
                    (the two words survive on two lines); the absolute
                    grace end loses its date; ``@ hour H`` folds away
===========  =====  =====================================================

Below ``minimal`` the box raises ``‹ widen`` in its bottom border rather
than letting a number be cut mid-digits.  Nothing here raises
``FULL_LAYOUT_COLUMNS``: at 143 every box sits at ``full`` with 13 columns
to spare.

Primitives only — this module imports nothing from ``data/`` or
``analytics/``, and contains no ``time.time()`` / ``datetime.now()`` (pinned
by ``test_the_hero_reads_no_clock_of_its_own``).
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from maxpane_dashboard.widgets.curator._fmt import (
    DASH,
    EMDASH,
    NO_STAMP,
    as_float,
    fmt_countdown,
    fmt_eth,
    fmt_eth_compact,
    fmt_points,
    hhmm,
)
from maxpane_dashboard.widgets.markup_safety import safe_markup, visible_len

#: The phase vocabulary this widget branches on, spelled exactly as
#: ``data/curator_models.PHASES`` freezes it.  A widget may not import
#: ``data/``, so the tuple is restated here and
#: ``test_the_hero_branches_on_exactly_the_frozen_phase_vocabulary`` asserts
#: the two agree — the redundancy-plus-agreement-test pattern CLAUDE.md
#: documents for ``_GAME_CYCLE``.  A fourth spelling anywhere is a silent
#: fallback arm: it would render the grace countdown for a game that may
#: already be dead.
PHASE_GRACE = "grace"
PHASE_JUDGED = "judged"
PHASE_SETTLED = "settled"
PHASES = (PHASE_GRACE, PHASE_JUDGED, PHASE_SETTLED)

#: Rendered when ``phase`` is ``None`` or unrecognised.  ``None`` is what a
#: failed ``isSettled()`` read produces, and it is **not** grace: choosing
#: grace silently would render a countdown for a game that may be over.
PHASE_UNAVAILABLE = "phase unavailable"

#: The complete-list instruction under both hero variants. The shorter forms
#: retain the command and outcome on terminals that cannot hold the full copy.
LIST_EXPORT_SUBTITLE = (
    "press 'e' to export full list as json file - once exported the complete "
    "list will be shown below"
)
LIST_EXPORT_SUBTITLE_SHORT = (
    "press 'e' to export json - the complete list will be shown below"
)
LIST_EXPORT_SUBTITLE_TINY = "press 'e' to export full list"

#: Marker raised in a box's bottom border when even ``minimal`` overflows.
WIDEN_HINT = "‹ widen"

#: Rendered columns each tier needs.  Measured from the strings the builders
#: below emit — ``test_every_hero_tier_fits_the_width_it_advertises`` renders
#: every phase at every tier and measures it, so a copy edit that outgrows
#: its tier fails there rather than on a user's terminal.
FULL_WIDTH = 26     # "judging begins in 03:12:45"
COMPACT_WIDTH = 21  # "routed (all refunded)"
MINIMAL_WIDTH = 18  # "SETTLED AT HOUR 27" / "fed 10.0K/5.00 ETH"

TIER_WIDTHS = {
    "full": FULL_WIDTH,
    "compact": COMPACT_WIDTH,
    "minimal": MINIMAL_WIDTH,
}

_BOX_IDS = ("curator-hero-clock", "curator-hero-list", "curator-hero-curve")


def _tier_for(width: int) -> str:
    """Widest box layout that fits ``width`` rendered columns.

    ``width <= 0`` means "not laid out yet" and optimistically picks the
    widest; :meth:`CuratorHero.on_resize` re-renders once the box has a size.
    """
    if width <= 0 or width >= FULL_WIDTH:
        return "full"
    if width >= COMPACT_WIDTH:
        return "compact"
    return "minimal"


def _phase_of(value) -> str | None:
    """The payload's phase, or ``None`` for unknown — never a default."""
    text = str(value or "").strip().lower()
    return text if text in PHASES else None


def _lines(title: str, big: str, *rest: str) -> list[str]:
    """A box: dim title, one loud line, three detail lines.  Always five."""
    body = list(rest[:3]) + [""] * (3 - len(rest[:3]))
    return [f"[dim]{title}[/]", big, *body]


# -- CLOCK ---------------------------------------------------------------


def _clock_lines(data: dict, tier: str) -> list[str]:
    """The doomsday clock, one layout per phase (PRD §3's table)."""
    phase = _phase_of(data.get("phase"))
    hour = data.get("current_hour")
    hour_str = f"hour {int(hour)}" if isinstance(hour, int) else f"hour {DASH}"

    if phase is None:
        # Not grace.  A failed isSettled() read is unknown, and unknown says
        # so — the countdown of a dead game is worse than no countdown.
        return _lines("CLOCK", f"[dim]{EMDASH}[/]",
                      f"[$warning]{PHASE_UNAVAILABLE}[/]", f"[dim]{hour_str}[/]")

    if phase == PHASE_SETTLED:
        settled_hour = data.get("settled_hour")
        head = (
            f"SETTLED AT HOUR {int(settled_hour)}"
            if isinstance(settled_hour, int)
            else f"SETTLED AT HOUR {DASH}"
        )
        lived = str(data.get("lived_desc") or "").strip()
        stamp = data.get("settled_at_ts") or data.get("settled_observed_at")
        when = hhmm(stamp)
        # An archive, not a failure (PRD §11): no "stale", no "unavailable",
        # no warning colour anywhere in this box.
        return _lines(
            "CLOCK",
            f"[bold]{safe_markup(head)}[/]",
            f"[dim]{safe_markup(lived)}[/]" if lived else "",
            f"[dim]frozen {when}[/]" if when != NO_STAMP else "",
        )

    if phase == PHASE_JUDGED:
        fed = fmt_eth_compact(data.get("hour_fed_eth"))
        bar = fmt_eth(data.get("hourly_threshold_eth"))
        left = fmt_countdown(data.get("hour_seconds_left"))
        needed = as_float(data.get("hour_needed_eth"))
        if needed is None:
            third = ""
        elif needed > 0:
            third = f"[bold $error]needs {fmt_eth(needed)} ETH[/]"
        else:
            third = "[$success]hour is safe[/]"
        return _lines(
            "CLOCK",
            f"[bold]{hour_str.upper()}[/]",
            f"fed {fed}/{bar} ETH",
            f"[dim]{left} left[/]",
            third,
        )

    # grace
    left = fmt_countdown(data.get("grace_seconds_left"))
    ends = str(data.get("grace_ends_utc") or "").strip()
    if tier == "full":
        second = f"judging begins in {left}"
    elif tier == "compact":
        second = f"begins in {left}"
    else:
        second = f"in {left}"
    if ends and tier == "minimal":
        # Keep the time of day, drop the date: the countdown above already
        # says which day it lands on.
        ends = ends.split(" ")[-1] if " " in ends else ends
    return _lines(
        "CLOCK",
        "[bold $warning]GRACE[/]",
        second,
        f"[dim]{safe_markup(ends)}[/]" if ends else "",
        f"[dim]{hour_str}[/]",
    )


# -- THE LIST ------------------------------------------------------------


def _list_lines(data: dict, tier: str) -> list[str]:
    """Wallets, routed volume, and whether the list still accepts entries."""
    phase = _phase_of(data.get("phase"))
    people = data.get("contributors_total")
    wallets = (
        f"{int(people):,} wallets" if isinstance(people, int) else f"{DASH} wallets"
    )
    volume = fmt_eth_compact(data.get("volume_routed_eth"))
    deposits = data.get("deposits_total")

    if phase == PHASE_SETTLED:
        state = "[bold]list FROZEN[/]"
    elif phase is None:
        state = f"[dim]list {DASH}[/]"
    else:
        state = "[$success]list OPEN[/]"

    if tier == "minimal":
        # The parenthetical will not fit; the two words still do, split over
        # the amount line and its own.  "routed" never appears alone.
        third = f"{volume} ETH routed"
        fourth = "[dim]all refunded[/]"
    else:
        third = f"{volume} ETH"
        fourth = "[dim]routed (all refunded)[/]"

    if isinstance(deposits, int) and tier == "full":
        wallets = f"{wallets} · {deposits:,} tx"
    return _lines("THE LIST", f"[bold]{wallets}[/]", third, fourth, state)


# -- CURVE / SURVIVAL ----------------------------------------------------


def _curve_lines(data: dict, tier: str) -> list[str]:
    """Early-bird decay in grace, survival once judged, records once settled."""
    phase = _phase_of(data.get("phase"))

    if phase == PHASE_SETTLED:
        top = data.get("top_points")
        people = data.get("contributors_total")
        deposits = data.get("deposits_total")
        return _lines(
            "FINAL",
            f"[bold]top {fmt_points(top)} pts[/]",
            f"[dim]{fmt_points(people)} contributors[/]",
            f"[dim]{fmt_points(deposits)} deposits[/]",
            f"[dim]{fmt_eth_compact(data.get('volume_routed_eth'))} ETH routed[/]",
        )

    multiplier = as_float(data.get("early_multiplier_x"))
    mult_str = f"{multiplier:.2f}×" if multiplier is not None else DASH
    rate = data.get("points_per_eth_now")
    rate_str = fmt_points(rate)

    if phase == PHASE_JUDGED:
        streak = data.get("survival_streak_hours")
        streak_str = (
            f"survived {int(streak)} h" if isinstance(streak, int) else f"survived {DASH}"
        )
        margin = as_float(data.get("closest_call_margin_eth"))
        call_hour = data.get("closest_call_hour")
        if margin is None:
            call = f"[dim]closest call {DASH}[/]"
        elif isinstance(call_hour, int) and tier != "minimal":
            call = f"[dim]min margin {fmt_eth(margin)} @ h{int(call_hour)}[/]"
        else:
            call = f"[dim]min margin {fmt_eth(margin)}[/]"
        return _lines(
            "SURVIVAL",
            f"[bold]{streak_str}[/]",
            call,
            f"[dim]{mult_str} · {rate_str} pts[/]"
            if tier == "minimal"
            else f"[dim]{mult_str} · {rate_str} pts/ETH[/]",
        )

    # grace (and unknown: the curve is still a live, readable number)
    if tier == "full":
        rate_line = f"1 ETH ≈ {rate_str} pts now"
    else:
        rate_line = f"1 ETH ≈ {rate_str} pts"
    return _lines(
        "CURVE",
        f"[bold]{mult_str}[/]",
        "[dim]early-bird decay[/]",
        rate_line if rate is not None else f"[dim]1 ETH ≈ {DASH} pts[/]",
    )


_BUILDERS = {
    "curator-hero-clock": _clock_lines,
    "curator-hero-list": _list_lines,
    "curator-hero-curve": _curve_lines,
}


class CuratorHeroBox(Static):
    """A single hero box: title, one loud line, three detail lines."""

    def render_lines_at_tier(self, build) -> None:
        """Render ``build(tier)`` at this box's own width, marker and all."""
        width = self.content_size.width
        lines = build(_tier_for(width))
        over = width > 0 and any(visible_len(line) > width for line in lines)
        self.border_subtitle = WIDEN_HINT if over else ""
        self.update("\n".join(lines))


class CuratorHero(Vertical):
    """Three phase-driven boxes over the full-list export instruction."""

    DEFAULT_CSS = """
    CuratorHero {
        height: 8;
    }
    CuratorHero > #curator-hero-boxes {
        height: 7;
    }
    CuratorHero CuratorHeroBox {
        width: 1fr;
        height: 7;
        padding: 0 2;
        margin: 0 1;
        border: solid $panel;
        background: $surface;
        content-align: center middle;
        text-align: center;
        text-wrap: nowrap;
        text-overflow: ellipsis;
        border-subtitle-color: $warning;
    }
    CuratorHero > #curator-hero-note {
        width: 100%;
        height: 1;
        padding: 0 2;
        color: $text-muted;
        text-align: center;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # Raw values, not formatted lines, so a resize re-lays them out.
        self._payload: dict = {}

    def compose(self) -> ComposeResult:
        with Horizontal(id="curator-hero-boxes"):
            for box_id in _BOX_IDS:
                yield CuratorHeroBox(
                    "[dim]Loading...[/]", id=box_id, classes="curator-hero-box"
                )
        yield Static(LIST_EXPORT_SUBTITLE, id="curator-hero-note")

    def update_data(
        self,
        phase=None,
        current_hour=None,
        grace_seconds_left=None,
        grace_ends_utc=None,
        hour_fed_eth=None,
        hour_needed_eth=None,
        hour_seconds_left=None,
        hourly_threshold_eth=None,
        settled_hour=None,
        settled_at_ts=None,
        settled_observed_at=None,
        lived_desc=None,
        early_multiplier_x=None,
        points_per_eth_now=None,
        survival_streak_hours=None,
        closest_call_margin_eth=None,
        closest_call_hour=None,
        contributors_total=None,
        deposits_total=None,
        volume_routed_eth=None,
        top_points=None,
        **_kwargs,
    ) -> None:
        """Refresh all three boxes from the flat ``CURATOR_KEYS`` payload.

        ``hourly_threshold_eth`` is the ``/5.00 ETH`` denominator of the
        judged clock and it comes from the payload, never from a literal:
        it is read live off the ``once`` tier, and ``hour_fed_eth +
        hour_needed_eth`` does **not** reconstruct it (``ethNeededThisHour()``
        answers 0 all through grace and whenever a judged hour is already
        safe).
        """
        self._payload = {
            "phase": phase,
            "current_hour": current_hour,
            "grace_seconds_left": grace_seconds_left,
            "grace_ends_utc": grace_ends_utc,
            "hour_fed_eth": hour_fed_eth,
            "hour_needed_eth": hour_needed_eth,
            "hour_seconds_left": hour_seconds_left,
            "hourly_threshold_eth": hourly_threshold_eth,
            "settled_hour": settled_hour,
            "settled_at_ts": settled_at_ts,
            "settled_observed_at": settled_observed_at,
            "lived_desc": lived_desc,
            "early_multiplier_x": early_multiplier_x,
            "points_per_eth_now": points_per_eth_now,
            "survival_streak_hours": survival_streak_hours,
            "closest_call_margin_eth": closest_call_margin_eth,
            "closest_call_hour": closest_call_hour,
            "contributors_total": contributors_total,
            "deposits_total": deposits_total,
            "volume_routed_eth": volume_routed_eth,
            "top_points": top_points,
            "seen": True,
        }
        self._render_view()

    def on_resize(self, _event=None) -> None:
        """Re-render: each box's tier is a function of its own width."""
        if self._payload:
            self._render_view()

    # -- rendering -------------------------------------------------------

    def _render_view(self) -> None:
        data = self._payload
        try:
            boxes = {
                box_id: self.query_one(f"#{box_id}", CuratorHeroBox)
                for box_id in _BOX_IDS
            }
            note = self.query_one("#curator-hero-note", Static)
        except Exception:  # not composed yet
            return

        for box_id, box in boxes.items():
            builder = _BUILDERS[box_id]
            box.render_lines_at_tier(lambda tier, fn=builder: fn(data, tier))

        width = max(self.content_size.width - 4, 0)
        for candidate in (
            LIST_EXPORT_SUBTITLE,
            LIST_EXPORT_SUBTITLE_SHORT,
            LIST_EXPORT_SUBTITLE_TINY,
        ):
            if not width or len(candidate) <= width:
                note.update(candidate)
                break
        else:
            note.update(LIST_EXPORT_SUBTITLE_TINY)
