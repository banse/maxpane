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
holds seat-state words, NODE_TITLES, the contributor RANK body and honest
count forms reused by the merged NODES card. No clock or I/O.
"""

from __future__ import annotations

from rich.text import Text

from maxpane_dashboard.widgets import rowfit
from maxpane_dashboard.widgets.sparkline_common import fmt_compact

from maxpane_dashboard.widgets.fmt import fmt_float, fmt_int
from maxpane_dashboard.widgets.panels import LOADING, UNAVAILABLE

__all__ = [
    "contrib_body",
    "count",
    "rank_body",
    "work_body",
    "NEVER_PAIRED_STYLE",
    "NODE_TITLES",
    "NEVER_PAIRED_TEMPLATE",
    "NEVER_PAIRED_WORDS",
    "never_paired",
    "seat_state_line",
    "seat_token",
]

#: The short word for each node key the swarm serves (owner, 2026-09-22):
#: the node cards' titles and RECORD's node column (lower-cased there, like
#: its other cells). An unknown key keeps its own fitted, escaped text.
NODE_TITLES = {
    "oracle_assess": "ORACLE",
    "adversarial_review": "REVIEW",
    "build_contract_project": "BUILD",
}

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


# -- Contributor RANK: independent of seat availability -------------------


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


def rank_body(contrib: dict, delta=None) -> Text:
    body = Text()
    rank, of = count(contrib.get("rank")), count(contrib.get("ranked_of"))
    if rank is None:
        body.append("unranked", style="dim")
    else:
        body.append(f"#{rank}", style="bold").append(" of ", style="dim").append(of or "--", style="bold")
    if rank is not None and isinstance(delta, int) and not isinstance(delta, bool) and delta:
        # A blank row above the move, as in STATUS (owner, 2026-09-25).
        body.append("\n\n").append(("▲" if delta > 0 else "▼") + fmt_int(abs(delta)),
                                style="bold green" if delta > 0 else "bold red")
    return body


def work_body(contrib: dict) -> Text:
    """Contributor work: hours, a blank line as in STATUS, then output tokens
    (owner, 2026-09-25; turns left WORK and stay on BOARD)."""
    seconds = contrib.get("wall_clock_s")
    hours = (fmt_float(seconds / 3600, ".1f")
             if isinstance(seconds, (int, float)) and not isinstance(seconds, bool) else "--")
    body = Text().append(hours, style="bold").append(" h", style="dim")
    tokens = seat_token(contrib.get("output_tokens"))
    try:
        text = "--" if tokens is None else fmt_int(tokens) if tokens < 1000 else fmt_compact(tokens)
        # Beyond the compact formatter's B suffix, use bounded scientific notation.
        if len(text) > 8:
            text = f"{tokens:.1e}"
    except (OverflowError, ValueError):
        text = "--"
    return body.append("\n\n").append(text, style="dim" if text == "--" else "bold").append(" tokens", style="dim")


def _whole(value: int) -> str:
    """A count in whole thousands or millions (``10K``, ``2M``): the node
    cards' last short form, for when ``fmt_compact``'s decimal does not fit."""
    if abs(value) < 1_000:
        return fmt_int(value)
    # A thousands count that rounds to 1000K is carried into ``M`` (F66:
    # 999,600 read ``1000K``).
    if abs(round(value / 1_000)) < 1_000:
        return f"{round(value / 1_000)}K"
    return f"{round(value / 1_000_000)}M"


_NUMS = (fmt_int, fmt_compact, _whole)
_UNITS = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}


def _reading(text: str) -> float:
    """The number a shown count reads as: ``100.0K`` and ``100K`` read alike."""
    text = text.replace(",", "")
    return float(text[:-1]) * _UNITS[text[-1]] if text[-1:] in _UNITS else float(text)


def _forms(values: tuple) -> list:
    """:data:`_NUMS` plus, for a pair, one value a decimal finer than the
    other -- the smaller first (``4.6K of 5K``), then the larger
    (``100K of 100.4K``, where ``100.0K of 100K`` would read alike) -- kept
    only while the readings keep the *values*' strict order: no two
    different counts read alike (F66: 4,600 of 5,400 read ``5K of 5K``) and
    none reads the wrong way round (5,460 of 5,480 as ``5.5K of 5K``)."""
    forms = list(_NUMS)
    if len(set(values)) > 1:
        low = min(values)
        forms.append(lambda v: fmt_compact(v) if v == low else _whole(v))
        forms.append(lambda v: _whole(v) if v == low else fmt_compact(v))
    ordered = sorted(set(values))
    return [num for num in forms
            if all(_reading(num(a)) < _reading(num(b)) for a, b in zip(ordered, ordered[1:]))]



def _num(room: int, line, *values):
    """The first of ``fmt_int``, ``fmt_compact`` (``10.0K``) and
    :func:`_whole` (``10K``) whose *line* fits *room* cells -- a shorter
    honest number, never a cut one; the last one stands if none fits.
    A form that reads two different *values* as one number, or the wrong
    way round, is not honest and is skipped (:func:`_forms`)."""
    honest = _forms(values)
    for num in honest:
        if rowfit.cell_len(line(num)) <= room:
            return num
    return honest[-1]

