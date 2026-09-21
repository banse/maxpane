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
exists so the never-paired literal is not typed in four panels. Pure: no
Textual import, no clock, nothing raises.
"""

from __future__ import annotations

from rich.text import Text

from maxpane_dashboard.widgets.panels import LOADING, UNAVAILABLE

__all__ = [
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
