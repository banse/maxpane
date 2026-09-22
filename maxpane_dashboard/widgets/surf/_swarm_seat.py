"""The AGENT body's seat-state words, typed once (plan ``surf_agent_seats`` §9 O).

``swarm_seat_state`` (``data/surf_models.SWARM_SEAT_STATES``) is what every
AGENT panel that shows the selected seat's lifetime record from ``/seats``
branches on before it paints a number:

==================  =====================================================
state               what the panel says
==================  =====================================================
``"ok"``            its numbers (:func:`seat_state_line` is ``None``)
``"pending"``       :data:`~maxpane_dashboard.widgets.panels.LOADING` --
                    no read of this token has finished yet, a switch in
                    flight included (plan Q-A)
``"unknown_seat"``  ``#N never paired`` -- the 404 real negative, a fact
                    about the seat and not a failure (decision D1)
``None``            :data:`~maxpane_dashboard.widgets.panels.UNAVAILABLE` --
                    the read failed and there is no last-good for this token
anything else       ``UNAVAILABLE`` too: a malformed state is not a fact
==================  =====================================================

Private to the surf package, not a shared ``widgets/*.py`` (plan §9 O): it
exists so the never-paired literal is not typed in four panels, and (since
2026-09-22) so the ``/contributors`` RANK and BOARD bodies, which sit in two
different rows, have one definition. Pure: no
Textual import, no clock, nothing raises.
"""

from __future__ import annotations

from rich.text import Text

from maxpane_dashboard.widgets.fmt import fmt_float, fmt_int
from maxpane_dashboard.widgets.panels import LOADING, UNAVAILABLE

__all__ = [
    "board_body",
    "contrib_body",
    "count",
    "rank_body",
    "NEVER_PAIRED_STYLE",
    "NEVER_PAIRED_TEMPLATE",
    "NEVER_PAIRED_WORDS",
    "never_paired",
    "seat_state_line",
    "seat_token",
]

#: The real negative's words on their own -- where the seat's number is
#: already on the line above (the hero's SEAT box), or not known to the panel.
NEVER_PAIRED_WORDS = "never paired"

#: ``#420 never paired``: ``/seats/{id}`` answered 404 ``unknown_seat``.
NEVER_PAIRED_TEMPLATE = "#{token} " + NEVER_PAIRED_WORDS

#: The never-paired line's style: a real negative worth the reader's eye,
#: not the ``unavailable`` of a failed read.
NEVER_PAIRED_STYLE = "yellow"


def seat_token(value: object) -> int | None:
    """An IDMD token id, or ``None``: an ``int`` that is not a ``bool`` and not negative."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def never_paired(token: object = None) -> str:
    """``#N never paired`` for a valid token, the bare words for anything else."""
    number = seat_token(token)
    if number is None:
        return NEVER_PAIRED_WORDS
    return NEVER_PAIRED_TEMPLATE.format(token=number)


def seat_state_line(state: object, token: object = None) -> Text | None:
    """What a seat panel shows *instead of* its numbers; ``None`` when ``state == "ok"``.

    ``token`` names the seat in the never-paired line; a panel whose
    signature carries no ``swarm_seat_selected`` passes nothing and gets the
    bare words.
    """
    if state == "ok":
        return None
    if state == "pending":
        return Text.from_markup(LOADING)
    if state == "unknown_seat":
        return Text(never_paired(token), style=NEVER_PAIRED_STYLE)
    return Text.from_markup(UNAVAILABLE)


# -- ``/contributors`` cards (RANK in the hero, BOARD in the node row) ------------
#
# Both read only ``swarm_seat_contrib`` and never borrow seats data, so they
# survive a pending or unavailable seat. Shared here since 2026-09-22, when
# the owner moved RANK into the hero row and BOARD into the node row.


def count(value) -> str | None:
    """A seat counter grouped for display, or ``None`` when it is not a count."""
    number = seat_token(value)
    return None if number is None else fmt_int(number)


def contrib_body(contrib, build) -> str | Text:
    """``build(contrib)`` for a listed seat; ``not listed`` / ``unavailable`` apart."""
    if not isinstance(contrib, dict):
        return UNAVAILABLE
    if contrib.get("listed") is not True:
        if contrib.get("listed") is False:
            return Text("not listed", style="dim")
        return UNAVAILABLE
    return build(contrib)


def board_body(contrib: dict) -> Text:
    n = {k: count(contrib.get(k)) or "--" for k in ("attempts", "accepted", "rejected", "pending")}
    return (Text()
            .append(n["accepted"], style="bold green").append(" acc of ", style="dim")
            .append(n["attempts"], style="bold")
            .append("\n").append(n["rejected"], style="bold").append(" rejected", style="dim")
            .append("\n").append(n["pending"], style="bold").append(" pending", style="dim"))


def rank_body(contrib: dict) -> Text:
    body = Text()
    rank, of = count(contrib.get("rank")), count(contrib.get("ranked_of"))
    if rank is None:
        body.append("unranked", style="dim")
    else:
        body.append(f"#{rank}", style="bold").append(" of ", style="dim").append(of or "--", style="bold")
    turns = count(contrib.get("turns"))
    body.append("\n").append(turns or "--", style="bold").append(" turns", style="dim")
    seconds = contrib.get("wall_clock_s")
    hours = (fmt_float(seconds / 3600, ".1f")
             if isinstance(seconds, (int, float)) and not isinstance(seconds, bool) else "--")
    return body.append("\n").append(hours, style="bold").append(" h", style="dim")
