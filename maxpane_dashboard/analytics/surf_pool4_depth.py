"""POOL4 depth ladder -- what the hook's own liquidity bids as IMD falls.

PURE. Stdlib only: no I/O, no clock, no Textual, no ``data/``. PRD 6.5, 7.5.

**What this is and is not.** These are quotes from the position as it stands
*right now*. A ``rebalance()`` closes the backstop band and redeploys it from
just above spot, so every number here can move the moment a keeper acts. It is
never a floor, never a guarantee and never protection -- see PRD 8.2 and the
forbidden-word test in ``tests/widgets/test_surf_pool4u_depth.py``.

**Orientation.** ETH is currency0 and price is IMD per ETH, so **tick up means
IMD is cheaper**: a reader selling IMD pushes the tick up, the pool pays out
ETH (currency0) and absorbs IMD (currency1).

Constant-liquidity math over a tick range::

    amount0 (ETH)  = L * (sqrtB - sqrtA) / (sqrtA * sqrtB)
    amount1 (IMD)  = L * (sqrtB - sqrtA)
    sqrt(price@t)  = 1.0001 ** (t / 2)

Validated against an independent implementation -- the ``pool4hook-research``
skill, captured at block 25955365 in
``tests/fixtures/surf/pool4/oracle_25955365.json`` and cross-checked by
``tests/data/test_surf_pool4_oracle.py``.
"""

from __future__ import annotations

import math

#: v4's max usable tick. The backstop band runs from its lower tick to here,
#: which is what makes its ETH single-sided.
MAX_TICK = 887272

#: log(1.0001), hoisted: this is the hot constant in every conversion.
_LOG_BASE = math.log(1.0001)

#: The ladder's rungs, as percentage falls in IMD's price. Five rows, chosen
#: to fit the panel: -1 is "a normal candle", -50 is "a bad day". The skill's
#: own ladder runs to -90, which is past the point a reader learns anything.
DEPTH_MOVES: tuple[int, ...] = (1, 5, 10, 20, 50)

#: ``data/surf_models.POOL4_BACKSTOP_STATES`` **restated**, not imported: this
#: module is certified stdlib-only by ``test_surf_widget_contract``'s recursive
#: purity walk, and reaching into ``data/`` from here would put an
#: httpx-importing package behind the module that walk is meant to clear.
#:
#: Restatement plus an agreement test is this repo's pattern for exactly this
#: seam -- ``widgets/surf/_pool4.network_word`` is the worked example, and the
#: reason it is a pattern rather than a duplication is that a third state word
#: must redden a test instead of falling through a branch and being silently
#: treated as one of these two.
#: ``tests/analytics/test_surf_pool4_depth.py`` imports both tuples and asserts
#: they agree in both directions.
BAND_STATES: tuple[str, ...] = ("deployed", "none")

#: ``"deployed"``: a band exists and its numbers are published.
#: ``"none"``: we looked and there is no band.
BAND_DEPLOYED, BAND_NONE = BAND_STATES


def sqrt_ratio(tick: float) -> float:
    """sqrt(price) at ``tick``, where price is IMD per ETH."""
    return 1.0001 ** (tick / 2.0)


def eth_between(liquidity: float, tick_lo: int, tick_hi: int) -> float:
    """Whole ETH a position of ``liquidity`` pays as the tick rises lo -> hi.

    Returns 0.0 -- not a negative, not None -- when the range does not open,
    because "the price did not get there" is a representable zero.
    """
    if tick_hi <= tick_lo:
        return 0.0
    a, b = sqrt_ratio(tick_lo), sqrt_ratio(tick_hi)
    return liquidity * (b - a) / (a * b) / 1e18


def tick_for_price_drop(tick_now: int, drop_pct: float) -> int:
    """The tick IMD's price reaches after falling ``drop_pct`` percent.

    A fall in IMD's price is a *rise* in IMD-per-ETH, hence a rise in tick.
    """
    if drop_pct <= 0.0 or drop_pct >= 100.0:
        return tick_now
    ratio = 1.0 / (1.0 - drop_pct / 100.0)
    return tick_now + int(round(math.log(ratio) / _LOG_BASE))


def depth_rows(
    *,
    tick: int | None,
    position_liquidity: float | None,
    band_lower_tick: int | None,
    band_liquidity: float | None,
    band_state: str | None = None,
) -> list[dict] | None:
    """The cumulative ladder, or ``None`` if the position could not be read.

    Keyword-only on ``_pool4_cap_headroom``'s precedent: two tick arguments
    and two liquidity arguments sitting side by side is exactly the signature
    where a positional swap is silent, so make it a ``TypeError``.

    ``None`` for the whole ladder, never a ladder of zeros: a zero ladder
    renders as "this pool bids nothing", which is a confident wrong answer to
    a question we could not answer at all.

    ``band_state`` and the three answers it buys (PRD 6.5, AMENDED 2026-09-11)
    ---------------------------------------------------------------------
    Until this argument existed the ladder derived the band's existence from
    its numbers -- ``band_lower_tick is not None and band_liquidity is not
    None`` -- and that fold is wrong in exactly the way CLAUDE.md names: a real
    negative with no representable value renders identically for "we looked and
    there was nothing" and "we could not look". **Measured**, not reasoned
    about: ``depth_rows(tick=68181, position_liquidity=6.9047e20,
    band_lower_tick=68340, band_liquidity=0)`` and the same call with
    ``band_liquidity=None`` returned **equal lists**, and the painted column was
    byte-identical through the real screen.

    ``pool4_backstop_state`` is the key that already carries the distinction, so
    the ladder consults it instead of inferring:

    * ``None`` (or any word outside :data:`BAND_STATES`) -- the band was **not
      read**. ``band_used_pct`` is ``None``. The full-range leg is untouched and
      ``eth_paid`` is still a real number: the position is readable even when
      the band is not, and "the position bids this much, the band is unknown"
      serves a reader better than either silence or a confident zero.
    * ``"none"`` -- we looked and there is no band. ``band_used_pct`` is a true
      ``0.0``: none of a band that does not exist has been consumed, and the
      full-range position goes on bidding, so the ladder is real.
    * ``"deployed"`` -- the share of the band the move consumes, as before. If
      the band's own numbers are missing under this word the answer is ``None``
      again rather than ``0.0``: "deployed, amount unreadable" is an unread
      band whatever the state word says.

    An **allowlist**, not a pass-through, on ``_pool4.network_word``'s
    precedent: a fourth state word must land in the unknown branch and redden a
    test, never fall through to ``deployed`` and paint a share nobody computed.

    The default is ``None`` and it is the fail-safe end of the argument: a
    caller that forgets this keyword gets "unknown", never a confident zero.

    ``eth_paid`` is deliberately **not** gated on ``band_state``. It is a sum of
    quantities that were read, and it adds the band's leg whenever the band's
    numbers are there; ``band_used_pct`` is a claim about a *share of the band*
    and a share needs to know the band is there at all.
    """
    if tick is None or position_liquidity is None:
        return None

    readable = band_lower_tick is not None and band_liquidity is not None
    if band_state == BAND_NONE:
        unread = False
        share_known = False
    elif band_state == BAND_DEPLOYED and readable:
        unread = False
        share_known = True
    else:
        unread = True
        share_known = False

    band_total = (
        eth_between(band_liquidity, band_lower_tick, MAX_TICK) if readable else 0.0
    )

    rows: list[dict] = []
    for move in DEPTH_MOVES:
        target = tick_for_price_drop(tick, float(move))
        full = eth_between(position_liquidity, tick, target)
        band = 0.0
        if readable and target > band_lower_tick:
            band = eth_between(band_liquidity, max(tick, band_lower_tick), target)
        used: float | None
        if unread:
            used = None
        elif share_known and band_total > 0.0:
            used = min(band / band_total * 100.0, 100.0)
        else:
            used = 0.0
        rows.append(
            {
                "move_pct": move,
                "eth_paid": full + band,
                "band_used_pct": used,
            }
        )
    return rows


def _as_float(value) -> float | None:
    """``float(value)`` or ``None``; never raises.

    ``widgets/surf/_fmt.as_float`` is the same three lines one layer out, and
    it is deliberately **not** imported: ``analytics/`` sits under the widgets
    in the import order, not over them, and reaching up into
    ``maxpane_dashboard.widgets`` from here would put a Textual-importing
    package behind a module the purity walk is meant to certify as stdlib-only.
    Three lines is the cheaper end of that trade.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def band_distance_pct(tick_now, band_lower_tick) -> float | None:
    """How far under spot the backstop band opens, in percent of IMD's price.

    **The one definition of this conversion.** ``widgets/surf/pool4u_hero.py``
    derived it in-widget during WP5 because ``pool4_backstop_distance_pct`` was
    never frozen into ``SURF_KEYS`` -- and ``test_surf_widget_contract.py``
    refuses any ``update_data`` kwarg that is not a contract key, so the key
    could not simply be added. The correct cure is one source rather than the
    key: this module already owns every other tick conversion on this view, so
    it owns this one too, and both the hero card and the SIGNALS row import it
    from here. Two copies of a conversion is how two panels on one screen come
    to disagree about the same number.

    **Orientation, and it is the half that is easy to get backwards.** ETH is
    currency0 and the pool prices IMD per ETH, so *tick up means IMD is
    cheaper*. The band sits **above** spot in tick terms precisely because it
    sits **below** spot in price terms. IMD's price at the band's edge divided
    by its price at spot is ``1.0001 ** (tick_now - band_lower_tick)``, and
    what this returns is one minus that, as a percentage.

    Checked against numbers that came from outside this function rather than
    from itself:

    * the plan's own WP1 ladder inputs -- spot 68196, band opening 68280, 84
      ticks apart -- return **0.84%**, the figure the WP5 hero snippet passed
      as a payload key that does not exist;
    * the committed oracle capture (``tests/fixtures/surf/pool4/
      oracle_25955365.json``) -- spot 68181, band opening 68340, 159 ticks --
      returns **1.58%**.

    (A tick is one basis point by construction, so over a short span the tick
    delta and the percentage read almost alike; they diverge with distance and
    nothing here approximates one with the other.)

    ``0.0`` -- a representable zero, never ``None`` -- when the band opens at
    or below spot in tick terms: the band is *at* the money, which is a real
    reading. ``None`` is reserved for a tick that could not be read.
    """
    now = _as_float(tick_now)
    lower = _as_float(band_lower_tick)
    if now is None or lower is None:
        return None
    if lower <= now:
        return 0.0
    try:
        return (1.0 - 1.0001 ** (now - lower)) * 100.0
    except (OverflowError, ValueError):  # pragma: no cover - guarded by the clamp
        return None
