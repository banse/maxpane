"""Surf-specific pure formatters, on top of ``widgets/fmt.py``.

These live in one private module because ``fmt_age`` is needed by both the
signals panel (``FIRED 2h ago``) and the feed title (``last 2h ago``), and a
second copy is how the sparkline helpers drifted apart before MEDI-36.
Pure functions, no I/O, no Textual imports, nothing raises.

Since 2026-09-20 (``docs/refactor_programme_2026_09.md`` Branch 3 WP-B) the
dashboard-agnostic names -- ``DASH``, ``EMDASH``, ``as_float``, ``fmt_age``,
``hhmm``, ``mmdd`` -- are defined once in ``widgets/fmt.py`` and re-exported
here so the surf widgets' imports did not move.  What this module still
defines is the surf-only set: ``fmt_imd``, ``fmt_price``, ``fmt_liquidity``
and :data:`ANTI_POISONING_COLS`.

**Escaping contract: callers escape, not this module.** Every function here
returns plain text, never markup-safe text. The calling widget owns
escaping: pass every value this module returns through
``widgets.markup_safety.safe_markup`` before it reaches ``Text.from_markup``
or a ``DataTable`` cell. Escaping here as well as at the widget would
double-escape and print literal ``\\[`` to the user, so this module
deliberately does not import ``safe_markup`` at all.

**No address formatter lives here.** Every address a surf widget renders goes
through ``widgets/address.py``, which puts the copy icon beside it
(``docs/address_copy_PRD.md``); :data:`ANTI_POISONING_COLS` is the one surf
number that module is handed.
"""

from __future__ import annotations

from maxpane_dashboard.widgets.explorer import ETHEREUM, IMD, SITES
from maxpane_dashboard.widgets.fmt import DASH, EMDASH, as_float, fmt_age, fmt_float, hhmm, mmdd
from maxpane_dashboard.widgets.sparkline_common import fmt_compact

__all__ = [
    "ANTI_POISONING_COLS",
    "DASH",
    "EMDASH",
    "EXPLORER",
    "JOB_EXPLORER",
    "SITE_EXPLORER",
    "as_float",
    "fmt_age",
    "fmt_win_rate",
    "fmt_price",
    "fmt_compact",
    "fmt_imd",
    "fmt_liquidity",
    "hhmm",
    "mmdd",
    "mmdd_hhmm",
]

#: Surf's default explorer, Ethereum mainnet (Etherscan): read off
#: ``data/surf_client.py:84`` -- ``STATE_RPC_PRIMARY``
#: ``ethereum-rpc.publicnode.com``, fallbacks ``gateway.tenderly.co/public/mainnet``,
#: ``rpc.mevblocker.io``. The pool4 panels and the swarm rows are the exception:
#: they resolve ``explorer.for_network(pool4_network)`` / ``for_chain_id(chain_id)``
#: from the network their own payload names (``data/surf_pool4_client.py`` reads
#: Sepolia and mainnet, ``data/surf_swarm`` rows carry a ``chain_id``).
EXPLORER = ETHEREUM

#: Where a swarm job id links: the IMD swarm's own explorer
#: (``explorer.imd.fun/jobs/<uuid>``, owner 2026-09-22), the site whose
#: ``api.imd.fun`` the swarm tiers read. Not a chain explorer.
JOB_EXPLORER = IMD

#: Where a swarm site's ENS name links: its eth.limo gateway page,
#: ``https://<label>.site.identitymd.eth.limo/`` (owner, 2026-09-23).
SITE_EXPLORER = SITES


def fmt_imd(value) -> str:
    """An IMD quantity at any magnitude this pipeline produces.

    ``sparkline_common.fmt_compact`` is the house compact formatter and is
    delegated to above 1000, but it renders **everything below 1.0 with zero
    decimal places**, so 0.049 IMD accrued and a genuinely empty hook both
    come out as ``0``. That is the false zero this dashboard exists to avoid,
    and it is not hypothetical: the BURN box read ``acc 0`` while the hook was
    accruing, which is exactly what a dead read looks like.

    Curator hit the identical trap on ``minDeposit`` and answered it the same
    way -- ``widgets/curator/_fmt.fmt_eth_compact``, whose shape this follows
    rather than reinvents. The shared helper is deliberately left alone: its
    own suite pins the sub-1 behaviour, and six widget modules across two
    dashboards read it.

    ==================  ========
    Input               Renders
    ==================  ========
    ``0``               ``0.00``
    ``0.049``           ``0.05``
    ``1.2512``          ``1.25``
    ``29.979``          ``29.98``
    ``12440.8``         ``12.4K``
    ==================  ========

    Widest form is ``999.99`` at six columns; ``12.4K`` is five. Both fit the
    cells that call this, and the burn amounts on chain (31,064 IMD is the
    largest) compact well inside them.
    """
    v = as_float(value)
    if v is None:
        return DASH
    if abs(v) < 999.995:            # guards 999.999 -> "1,000.00", eight columns
        return f"{v:,.2f}"
    return fmt_compact(v)


def fmt_price(value) -> str:
    """USD price at IMD-scale precision (a ~$0.71 token, not a sub-cent one)."""
    v = as_float(value)
    if v is None:
        return DASH
    a = abs(v)
    if a >= 1:
        return f"${v:,.2f}"
    if a >= 0.01:
        return f"${v:.4f}"
    if a > 0:
        return f"${v:.6f}"
    return "$0.00"


def fmt_liquidity(value) -> str:
    """Raw v3 liquidity is a uint128 ~1e19; suffixes lie at that magnitude."""
    v = as_float(value)
    if v is None:
        return DASH
    if abs(v) >= 1e12:
        return f"{v:.2e}"
    return fmt_compact(v)


#: The anti-poisoning window, in cells, for a surf panel that mentions an
#: address in passing: ``0x`` + 8 hex + ``…`` + 6 hex through
#: ``widgets/address.short_address``. Live spoofs of both fee recipients exist
#: in frenpet.eth's history; they collide with the real addresses on the
#: classic first-6/last-4 form but not on this window (PRD §4).
#:
#: ``long_addr`` and ``full_addr`` lived here until 2026-09-14, when every
#: address on screen moved to ``widgets/address.py`` so a copy icon could sit
#: beside it (``docs/address_copy_PRD.md``). The window is the one thing of
#: ``long_addr``'s that is a surf decision rather than a formatter, so the
#: number stays here and the shortening does not.
ANTI_POISONING_COLS = 17


def mmdd_hhmm(value) -> str:
    """Local month/day and time, keeping accepted work distinct across midnight."""
    return f"{mmdd(value)} {hhmm(value)}"


def fmt_win_rate(rate: float) -> str:
    """A lifetime attempts rate, shared by the AGENT hero and SEAT."""
    return f"{fmt_float(rate * 100, '.1f')} %"


def source_clock(value) -> str:
    """A source's own HH:MM marker; never borrow another endpoint's clock."""
    import re
    return value if isinstance(value, str) and re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]', value) else 'unavailable'
