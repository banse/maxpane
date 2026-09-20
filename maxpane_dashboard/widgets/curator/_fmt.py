"""Curator-specific pure formatters (THE LIST), on top of ``widgets/fmt.py``.

One private module rather than a copy per widget: ``fmt_eth`` is needed by
the hero, the leaderboard, the activity feed, the signal rail and both swap
tables, and a second copy is how the sparkline helpers drifted apart before
MEDI-36.  Pure functions, no I/O, no Textual imports, **nothing raises** — a
widget that raises inside Textual's message pump takes the app down.

Since 2026-09-20 (``docs/refactor_programme_2026_09.md`` Branch 3 WP-B) the
dashboard-agnostic names — ``DASH``, ``EMDASH``, ``as_float``, ``fmt_eth``,
``fmt_age``, ``fmt_countdown``, ``fmt_points``, ``fmt_pct`` — are defined once
in ``widgets/fmt.py`` and re-exported here so the curator widgets' imports
did not move; their rationale (the bool rejection, the negative age, the
``timeLeftInHour`` edge, the zero score) moved with them.  ``hhmm`` here is
the shared one with :data:`NO_STAMP` as its unknown marker.  What this module
still defines is the curator-only set: ``fmt_eth_compact`` with its measured
:data:`COMPACT_ETH_COLS`, and the identity-cell widths :data:`ADDR_COLS` /
:data:`NAME_COLS`.

Three rules this dashboard makes load-bearing
---------------------------------------------

**A missing value is a dash, never a zero.**  ``WhitelistCurator`` has three
legitimate zeros — ``currentHourTotal()`` at an hour boundary,
``ethNeededThisHour()`` during grace or a safe judged hour, and
``creditedDelta`` above the 1000 ETH cap — so ``0`` and "we could not read it"
must render differently or the reader cannot tell a safe hour from a dead RPC.
Every formatter here returns :data:`DASH` for ``None`` and a real number for
``0``.

**Escaping is the caller's job.**  Everything here returns plain text, never
markup-safe text; the calling widget passes the result through
``widgets.markup_safety.safe_markup`` before it reaches ``Text.from_markup``
or a ``DataTable`` cell.  Escaping in both places would double-escape and
print a literal ``\\[`` to the user, so this module deliberately does not
import ``safe_markup`` at all.

**No clock is read here.**  ``hhmm`` converts a timestamp it is handed;
nothing in this package calls ``time.time()`` or ``datetime.now()``.  Every
countdown on this dashboard is poll-anchored (PRD §2) and arrives in the
payload already computed against the manager's injected clock.
"""

from __future__ import annotations

from maxpane_dashboard.widgets import fmt
from maxpane_dashboard.widgets.explorer import ETHEREUM
from maxpane_dashboard.widgets.fmt import (
    DASH,
    EMDASH,
    as_float,
    fmt_age,
    fmt_countdown,
    fmt_eth,
    fmt_pct,
    fmt_points,
)
from maxpane_dashboard.widgets.sparkline_common import fmt_compact

__all__ = [
    "DASH",
    "EMDASH",
    "EXPLORER",
    "ADDR_COLS",
    "NAME_COLS",
    "COMPACT_ETH_COLS",
    "COMPACT_ETH_PROBE",
    "NO_STAMP",
    "as_float",
    "fmt_eth",
    "fmt_eth_compact",
    "fmt_age",
    "fmt_countdown",
    "fmt_points",
    "fmt_pct",
    "hhmm",
]

#: Ethereum mainnet (Etherscan): read off ``data/curator_client.py:99`` --
#: ``STATE_RPC_PRIMARY`` ``ethereum-rpc.publicnode.com``, fallbacks
#: ``gateway.tenderly.co/public/mainnet``, ``rpc.mevblocker.io``.
#: ``data/curator_nft_holders.py`` reads Base too, but a wallet address is the
#: same on both chains, so every curator address links to Etherscan.
EXPLORER = ETHEREUM

#: The anti-poisoning window's own width, i.e. of ``0x1234…abcd`` --
#: :data:`~maxpane_dashboard.widgets.address.MIN_SHORT_COLS`'s value,
#: matched here rather than imported (this module is pure/stdlib-only,
#: :data:`~maxpane_dashboard.widgets.address.ICON_COLS`-adjacent code lives
#: in the widgets that call ``address_text`` with it).
#:
#: **Eleven, not thirteen.**  PRD §4 writes "``0x1234…abcd`` (13 cols)" and
#: the two halves of that sentence disagree: the literal form it names is
#: ``0x`` + 4 + ``…`` + 4 = 11 columns.  The literal wins — it is what the
#: PRD's own activity-feed and leaderboard examples render — and every cell
#: in this package is sized from this constant rather than from either
#: number, so the two can never drift again.  A cell padded to 13 would be
#: two dead columns on every row of every table (the ``dev``/``ops`` defect
#: in CLAUDE.md, which cost the surf dev-activity panel nine).
ADDR_COLS = 11

#: The identity cell's width wherever a **name** may appear.  Exactly ONE column
#: wider than the hex it replaces, and both halves of that are measurements:
#:
#: * twelve is what `surfsurf.eth` needs, and a name truncated to eleven
#:   (`surfsurf.e…`) is worse than the address it replaced -- neither a name you
#:   can read nor an address you can match;
#: * thirteen is what the screen cannot afford.  Swept: at 15 the full layout
#:   goes 138 -> 144, past the app-wide 143 that FWA sets, because this cell is
#:   in three panels and two of them share a row.  12 leaves the measured 138
#:   exactly where it was.
#:
#: A longer name ellipsises here and is shown whole in the wallet view's own
#: panel, which is the one place with room for it.
NAME_COLS = 12

#: The activity feed's missing-timestamp cell.  A log row whose block stamp
#: could not be read renders this, **never** ``00:00`` — an epoch-zero stamp
#: reads as 1970-01-01 data rather than as an absent measurement.
NO_STAMP = "--:--"


def fmt_eth_compact(value) -> str:
    """ETH at any magnitude this game produces, in :data:`COMPACT_ETH_COLS`.

    The width is **measured** — see :data:`COMPACT_ETH_PROBE` — and it is not
    a universal bound: the K/M/B forms reach *seven* columns at and above
    999,999 (``fmt_eth_compact(999999.0) == "1000.0K"``), a magnitude no
    field on this contract can carry.  Cells are sized from the probe, never
    from a remembered adjective.

    ``sparkline_common.fmt_compact`` is the house compact formatter and is
    used above 1000, but it renders **everything below 1.0 with zero decimal
    places** — a 0.05 ETH deposit (this contract's ``minDeposit``, and the
    single most common amount on the feed) comes out of it as ``0``.  A
    minimum deposit rendered as zero is the same false-zero this whole
    dashboard is built to avoid, so small amounts keep three decimals here
    and only the K/M range delegates.

    ==================  ========
    Input               Renders
    ==================  ========
    ``0``               ``0.000``
    ``0.05``            ``0.050``
    ``3.6``             ``3.60``
    ``461.1``           ``461.10``
    ``8401.0``          ``8.4K``
    ==================  ========
    """
    v = as_float(value)
    if v is None:
        return DASH
    magnitude = abs(v)
    if magnitude < 1:
        return f"{v:.3f}"
    if magnitude < 999.995:  # guards 999.999 -> "1,000.00", eight columns
        return f"{v:,.2f}"
    # Delegated to the house helper, never re-implemented (MEDI-36).
    return fmt_compact(v)


#: Every magnitude :func:`fmt_eth_compact` is handed on this contract, as a
#: probe rather than a remembered adjective.  ``minDeposit`` (0.05), the
#: captured feed amounts (3.60, the 9×60 fan-out, the 461.10 whale and the
#: 899.00 weight it produced), the two-decimal form's widest point (999.99),
#: the 1000 ETH credit cap, the routed total (8401) and a cumulative weight
#: an order of magnitude past anything this game has routed.
#:
#: The two-decimal form is the *widest* of these, not the largest number:
#: ``999.99`` is six columns where ``99,999`` compacts to ``100.0K``, also
#: six.  Sizing a cell to "the biggest value" gets this backwards.
COMPACT_ETH_PROBE = (
    0.0, 0.05, 3.6, 60.0, 461.1, 899.0, 999.99, 1000.0, 8401.0, 99_999.0,
)

#: Measured width of the widest string :func:`fmt_eth_compact` can return for
#: this contract's magnitudes.  Six.  Every ETH cell in this package is sized
#: from it — the ``dev``/``ops`` lesson in CLAUDE.md, where a cell sized to
#: the *small* example cut a real value mid-word with nothing in the title.
COMPACT_ETH_COLS = max(len(fmt_eth_compact(v)) for v in COMPACT_ETH_PROBE)


def hhmm(timestamp) -> str:
    """``HH:MM`` local time from unix seconds; :data:`NO_STAMP` when unusable.

    The shared :func:`widgets.fmt.hhmm` with this dashboard's marker: ``None``
    **and** ``0`` both render ``--:--`` (H14), and so does ``float("inf")``,
    which the pre-2026-09-20 copy here let raise ``OverflowError``.
    """
    return fmt.hhmm(timestamp, unknown=NO_STAMP)


# `short_label` and `short_addr` were deleted here in Task 3's own
# 2026-09-14 fix round (recipe step 2, "delete the private formatter"):
# every curator widget that used to call them now composes
# `widgets.address.address_text` directly, which carries a real copy icon
# neither of these plain-string formatters could. `ADDR_COLS`/`NAME_COLS`
# stay -- they are still the measured width every identity cell in this
# package is sized from, `address_text`'s own `width=` argument now rather
# than these two functions' internal cap.
