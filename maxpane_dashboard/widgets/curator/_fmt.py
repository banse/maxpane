"""Shared pure formatters for the curator widgets (THE LIST).

One private module rather than a copy per widget: ``fmt_eth`` is needed by
the hero, the leaderboard, the activity feed, the signal rail and both swap
tables, and a second copy is how the sparkline helpers drifted apart before
MEDI-36.  Pure functions, no I/O, no Textual imports, **nothing raises** — a
widget that raises inside Textual's message pump takes the app down.

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

import time

from maxpane_dashboard.widgets.sparkline_common import fmt_compact

__all__ = [
    "DASH",
    "EMDASH",
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
    "short_addr",
    "short_label",
]

#: Unknown scalar.  Two columns, so a dashed cell never re-flows a table.
DASH = "--"

#: "Nothing here, and that is the expected state" — the FORCED ETH row's
#: healthy rendering (H5).  Deliberately distinct from :data:`DASH`, which
#: means "we could not read it".
EMDASH = "—"

#: Rendered width of :func:`short_addr`, i.e. of ``0x1234…abcd``.
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


def as_float(value):
    """Coerce to ``float`` or return ``None`` — never raise, never 0-coerce.

    ``bool`` is rejected on purpose: ``True`` is not ``1.0`` ETH, and
    ``isSettled()`` reaching an amount field is a bug worth rendering as
    unknown rather than as a quantity.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if out != out or out in (float("inf"), float("-inf")):  # NaN / ±inf
        return None
    return out


def fmt_eth(value, places: int = 2) -> str:
    """``3.60`` / ``8,401.00`` — a plain ETH quantity, no unit, no suffix.

    ``0`` renders ``0.00``: on this contract a zero is frequently the real
    answer (an hour that needs nothing is a *safe* hour), and rendering it
    as unknown would hide the healthiest state the game has.
    """
    v = as_float(value)
    if v is None:
        return DASH
    return f"{v:,.{places}f}"


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


def fmt_age(seconds) -> str:
    """``45s`` / ``12m`` / ``2h`` / ``3d``; ``--`` for unknown or negative.

    A negative age is an event from the future, i.e. corrupt input; ``0s``
    would claim "just now" about it.
    """
    s = as_float(seconds)
    if s is None or s < 0:
        return DASH
    if s < 90:
        return f"{s:.0f}s"
    if s < 90 * 60:
        return f"{s / 60:.0f}m"
    if s < 36 * 3600:
        return f"{s / 3600:.0f}h"
    return f"{s / 86400:.0f}d"


def fmt_countdown(seconds) -> str:
    """``H:MM:SS`` at or above an hour, ``MM:SS`` below it.

    Two contract edges shape this (H12): ``timeLeftInHour()`` returns
    ``hourDuration`` — 3600, not 0 — at an exact hour boundary, and
    ``grace_seconds_left`` is clamped at 0 by the analytics layer once grace
    is over.  So ``3600`` renders ``1:00:00`` and ``0`` renders ``00:00``,
    and both are real states.

    A **negative** input is nonsense rather than an edge (nothing upstream
    may produce one), so it renders :data:`DASH`.  It is never rendered as a
    negative clock: ``-00:05`` reads as a deadline five seconds gone, which
    is a claim this widget has no evidence for.
    """
    s = as_float(seconds)
    if s is None or s < 0:
        return DASH
    total = int(s)
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def fmt_points(value) -> str:
    """``31,622`` — a curve score.  ``0`` is a real score; ``None`` is not.

    Zero points is reachable on chain: any weight under 1e18 floors to zero
    through ``(isqrt(weight) * 1000) // 1e9``, so a real contributor can sit
    at 0.  It renders as the number.
    """
    v = as_float(value)
    if v is None:
        return DASH
    return f"{int(v):,}"


def fmt_pct(value) -> str:
    """``12.4%``; ``--`` when the share could not be computed.

    Never ``0.0%`` for an unknown: the flagged-points share is ``None``
    whenever total points are unknown (a division we refuse to do), and
    ``0.0%`` would assert that the flagged wallets scored nothing.
    """
    v = as_float(value)
    if v is None:
        return DASH
    return f"{v:.1f}%"


def hhmm(timestamp) -> str:
    """``HH:MM`` local time from unix seconds; :data:`NO_STAMP` when unusable.

    Local, like every other MaxPane feed stamp.  The one absolute instant on
    this dashboard — the end of grace — arrives from the manager already
    formatted as a UTC string, so the two never mix in one cell.

    ``None`` **and** ``0`` both render ``--:--``: the log-timestamp read can
    fail, and an epoch-zero stamp would print ``00:00`` on 1970-01-01, which
    looks like data (H14).
    """
    try:
        ts = int(timestamp or 0)
    except (TypeError, ValueError):
        return NO_STAMP
    if ts <= 0:
        return NO_STAMP
    try:
        t = time.localtime(ts)
    except (TypeError, ValueError, OSError, OverflowError):
        return NO_STAMP
    return f"{t.tm_hour:02d}:{t.tm_min:02d}"


def short_label(name, address) -> str:
    """A verified ENS name if there is one, else :func:`short_addr`.

    **Exactly :data:`ADDR_COLS` columns or fewer, always.**  A name is
    attacker-supplied and can be 255 characters, so it is truncated to the
    address cell's own width rather than allowed to widen a table -- every
    width in this dashboard was measured against a hex address, and a panel
    that grows when a stranger registers a long name is a panel whose measured
    width was fiction.  The full name has room in the wallet view's own panel,
    which is where it is shown whole.

    Returns raw, unescaped text: names are the most attacker-controlled strings
    on this screen and the caller escapes, the same contract ``short_addr``
    keeps.
    """
    if isinstance(name, str):
        cleaned = " ".join(name.split())
        if cleaned:
            if len(cleaned) <= NAME_COLS:
                return cleaned
            return f"{cleaned[: NAME_COLS - 1]}…"
    return short_addr(address)


def short_addr(value) -> str:
    """``0x1234…abcd`` — :data:`ADDR_COLS` columns, both ends kept.

    Lower-cased on purpose.  Addresses reach this dashboard from two
    sources with two spellings: ``eth_call`` returns are decoded to a
    checksummed string and log topics decode to lowercase hex, so the same
    wallet would otherwise render two ways in two panels and the
    leaderboard's "this row is you" match would depend on which panel you
    read.  One spelling, everywhere, and the comparison upstream is
    case-insensitive for the same reason.

    Returns raw, unescaped text — including for short inputs, which pass
    through verbatim so a mangled payload is visible rather than dressed up
    as an address.  The caller escapes.
    """
    if value is None:
        return DASH
    s = str(value).strip().lower()
    if not s:
        return DASH
    if len(s) <= ADDR_COLS:
        return s
    return f"{s[:6]}…{s[-4:]}"
