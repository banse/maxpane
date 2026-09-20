"""One screen the address sweep renders (PRD §7 E2/E3)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Awaitable, Callable, Mapping, Union

from textual.app import App

from maxpane_dashboard.widgets.explorer import Explorer

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
    #: The dashboard's explorer (PRD §7 E7): the one its package declares
    #: (``widgets/<game>/_chain.py`` or ``_fmt.py``), so this is the agreement
    #: test that binds that declaration to the chain the sweep expects. ``None``
    #: for an address-free dashboard, and for one on a chain
    #: ``widgets/explorer.py`` does not allowlist -- there, E7 asserts the
    #: opposite: no link at all, never a guessed one.
    explorer: Explorer | None = None
    #: The explorers a per-row override may pick from (surf lists all three:
    #: pool4 panels link by ``pool4_network``, swarm rows by ``chain_id``).
    #: Defaults to ``(explorer,)``; empty when ``explorer`` is ``None``.
    explorers: tuple[Explorer, ...] = ()
    #: The one explorer a particular seeded address must link on, lower-cased
    #: address -> explorer, for an address whose chain is NOT the package's
    #: (a custom NFT collection on Base in curator's editor: a contract
    #: address is not chain-agnostic the way a wallet is). E7 reports
    #: ``link on the wrong explorer`` for a listed address on any other
    #: explorer, allowed or not; an unlisted address may link on any member
    #: of ``explorers``. Every value must be in ``explorers``.
    explorer_for: Mapping[str, Explorer] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.explorer is not None and not self.explorers:
            object.__setattr__(self, "explorers", (self.explorer,))
        if self.explorer is not None and self.explorer not in self.explorers:
            raise ValueError(f"{self.name}: explorer {self.explorer.name} is not in its own allowed set")
        object.__setattr__(
            self, "explorer_for", {a.lower(): e for a, e in self.explorer_for.items()}
        )
        for address, explorer in self.explorer_for.items():
            if explorer not in self.explorers:
                raise ValueError(f"{self.name}: {address} names explorer {explorer.name} outside the allowed set")
