"""One screen the address sweep renders (PRD §7 E2/E3)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from textual.app import App


@dataclass(frozen=True)
class SweepCase:
    #: The screen's name: a GAMES id, or the hidden screen's install name.
    name: str
    #: The screen class this case renders; E3 checks all fourteen are here.
    screen_class: type
    #: Builds a CopyRecorder harness around the real screen with a fake manager.
    build: Callable[[], App]
    #: Everything that harness serves the screen: the ``fetch_and_compute``
    #: payload, plus any manager attribute the screen reads directly (the
    #: frenpet wallet screens print ``manager._wallet_address``). E2 reads it to
    #: tell a wrong-address icon (one copying an address that appears nowhere in
    #: what the screen was given) from a right one.
    payload: Callable[[], dict]
    #: Key sequences that reach each view; () is the default body.
    views: tuple[tuple[str, ...], ...] = ((),)
    #: True when the dashboard shows no address at all (PRD §7 E3).
    address_free: bool = False
    #: Addresses deliberately placed where this dashboard renders them, in every
    #: shape it uses. HAND-LISTED, never derived from the payload: a payload
    #: carries addresses no panel shows (a pool manager, an internal sink), and a
    #: derived list would fail E2 on addresses that were never meant to render.
    seeded: tuple[str, ...] = ()
    #: Widget packages (or single widget modules) the screen renders from, for
    #: the E3 agreement test. The screen's own module is always checked too.
    widget_packages: tuple[str, ...] = ()
