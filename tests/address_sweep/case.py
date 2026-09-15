"""One screen the address sweep renders (PRD §7 E2/E3)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, Union

from textual.app import App

#: A view is either the keys that reach it, or a coroutine that drives the
#: harness there (for a body no key reaches, or one that needs input typed).
ViewAction = Callable[[App, object], Awaitable[None]]
View = Union[tuple[str, ...], ViewAction]


def view_name(view: View) -> str:
    return getattr(view, "__name__", None) or repr(view)


@dataclass(frozen=True)
class SweepCase:
    #: The screen's name: a GAMES id, or the hidden screen's install name.
    name: str
    #: The screen class this case renders; E3 checks every dashboard screen is here.
    screen_class: type
    #: Builds a CopyRecorder harness around the real screen with a fake manager.
    build: Callable[[], App]
    #: Everything that harness serves the screen: the ``fetch_and_compute``
    #: payload, plus anything else the screen is given and prints (a manager
    #: attribute such as frenpet's ``_wallet_address``, an address a view types
    #: into an input). E2 reads it to tell a wrong-address icon (one copying an
    #: address that appears nowhere in what the screen was given) from a right one.
    payload: Callable[[], dict]
    #: The views to sweep: key tuples or view coroutines; () is the default body.
    views: tuple[View, ...] = ((),)
    #: True when the dashboard shows no address at all (PRD §7 E3).
    address_free: bool = False
    #: Addresses deliberately placed where this dashboard renders them, in every
    #: shape it uses. HAND-LISTED, never derived from the payload: a payload
    #: carries addresses no panel shows (a pool manager, an internal sink), and a
    #: derived list would fail E2 on addresses that were never meant to render.
    seeded: tuple[str, ...] = ()
    #: Each view's own layout pin, ``(columns, rows)``, in ``views`` order. A
    #: ``None`` row count means the sweep's default height. A single entry
    #: pins every view; empty pins every view at
    #: ``__main__.FULL_LAYOUT_COLUMNS``. Always import the
    #: pin constants; never retype a number here.
    pins: tuple[tuple[int, int | None], ...] = ()
    #: Further ``(columns, rows)`` sizes to sweep every view at, below the
    #: pins, where a measured defect lived. Each one names its reason in the
    #: builder.
    extra_sizes: tuple[tuple[int, int | None], ...] = ()
