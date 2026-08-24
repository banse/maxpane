"""Hero row for the surf dashboard: LAUNCHPAD · FLOW · BURN · SUPPLY.

Four boxes answering PRD §4's hero-left slot. This is the row's second
rebuild. The 2026-08-23 v3->v4 migration already replaced **HOOK** (a v4
hook launch the dev publicly retracted on 2026-08-16) and **GATE** (which
moved to its own seat on the signals rail) with **POOL** and **LP** -- and
this rewrite, still 2026-08-23 and still the same plan, retires those two in
turn. Not because the migration reversed: because their information moved
elsewhere or simply ran out.

* **POOL**'s three facts are all duplicated now. Its USD liquidity is
  already ``pool $548.7K`` one row down in the IMD MARKET panel
  (``widgets/surf/market.py``); its decoy count already has a seat of its
  own on the signals rail as DECOY POOL (``widgets/surf/signals.py``); and
  its ``v4`` venue, which used to be news, is now permanent -- the v3
  position was burned 2026-08-17 and cannot come back. A box that only ever
  repeats facts shown elsewhere is not earning a quarter of the hero row.
* **LP** could only ever say one thing after that same burn:
  ``ownerOf(#1167726)`` reverts ``Invalid token ID`` forever, so
  ``lp_state`` is permanently ``"gone"`` and the box has read
  ``MIGRATED / v3 position migrated`` since the migration landed, with no
  path back to saying anything else. A box whose entire vocabulary is one
  fixed sentence is the same dead weight as POOL's, just reached by a
  different road.

What replaces them reads the launchpad sweep that already runs for the ``l``
LAUNCHPAD view (``SurfManager._launchpad_payload``, Task 8) -- **no new
request** -- and asks the two questions POOL/LP no longer could:

* **LAUNCHPAD** -- how big the coin population is (``launchpad_coin_count``),
  how fast it is growing (``launchpad_new_24h``, which is genuinely ``0`` on
  many days and must say so as a number rather than collapse into the same
  dash a failed read uses), and how many distinct creators are behind it
  (``launchpad_creator_count``).
* **FLOW** -- how much that population is actually trading
  (``launchpad_swap_count``, ``launchpad_trader_count``) and what the
  pipeline owes its creators (``launchpad_creator_eth_owed`` -- the ETH side
  of the same permissionless burn pipeline BURN displays the IMD side of).

**Both boxes carry the launchpad tier's own clock on their title line**
(``LAUNCHPAD · 20:20``, off ``launchpad_as_of_hhmm``) rather than the bare
titles BURN and SUPPLY keep. The title bar above shows the *fast* tier's
``as of``; the launchpad tier refreshes every 600s (its own slower slot, the
curator ``f`` analysis precedent), so a bare title would let these two boxes
sit under a clock claiming seconds while the numbers beneath it are up to
ten minutes old -- exactly "a stale number presented as live" (CLAUDE.md
Conventions). The clock shows only at ``compact``: at ``tight``/``minimal``
there is no room for it without crowding the numbers it exists to keep
honest about, and a terminal narrow enough to need those tiers (see Width
behaviour below) has nowhere near enough columns to read the whole row
anyway.

When *every* one of a box's own inputs is ``None`` -- the sweep has simply
never completed, not "completed and found nothing" -- that box's second
line reads ``no read yet`` instead of rendering a dash-filled shape that
would look like a partial, completed read. ``0`` is a different, real claim
(zero launches in the last 24h *is* some days' actual state) and must never
collapse into either the unread wording or the single-field dash a read
that fails for just one input still uses -- the inverse of the curator rail
bug where a dead group's ``-- unknown`` and a real ``none yet`` both read
confident and green through an outage.

* **BURN**   -- the permissionless bridge-and-burn pipeline's own state:
  how much IMD has accrued for burning, how much is already staged on the
  Base side, and whether ``bridgeToBaseBurnReceiver()`` would clear its own
  minimum right now. ``bridgeToBaseBurnReceiver()`` is callable by anyone --
  this box *displays* that fact, it never offers to call it (CLAUDE.md hard
  constraint 1: MaxPane never signs, never sends, never constructs
  calldata). ``burn_ready`` is tri-state: ``True``/``False``/``None`` render
  three distinct strings, because ``None`` means "cannot tell" and must not
  collapse into the same word as a genuine "not ready yet" -- the inverse of
  the curator rail bug where a dead group's "-- unknown" and a real "none
  yet" both read confident and green through an outage.
* **SUPPLY** -- IMD totalSupply + the burn *this install has observed*.
  Unchanged from the previous hero: ``imd_burned_cum`` is an accumulator
  over successive supply readings (WP4.5), so it covers the observation
  window and nothing before it, and the three states stay distinct --
  ``None`` -> em-dash (no supply read yet, or the read failed), ``0.0`` ->
  ``no burn observed yet`` (watched, nothing moved), positive -> the
  quantity. A ``None`` supply renders an em-dash: rendering ``0`` here is
  the false-BURN twin CLAUDE.md's "a failed read is None, never 0" exists
  to prevent.

Copied from ``fwa/fwa_hero_metrics.py`` and adapted to the surf data
contract (PRD §5 ``hero`` keys). Primitives only: this module imports
nothing from the data layer.

Width behaviour
---------------

A hero box is one quarter of the **full-width** hero row, so its budget is
roughly the terminal's columns over four: measured on the real screen,
**16 content columns at 100 terminal columns, 22 at 119, 26 at 135, 27 at
139, 34 at 169, 42 at 200**. ``1fr`` rounding leaves neighbouring boxes a
column apart, which is why each box picks its tier from *its own* width
rather than the row's (see :meth:`SurfHeroBox.render_lines_at_tier`).

The three tiers -- and their widths -- are unchanged by this rewrite:
``compact`` needs 22 columns and gives up nothing; ``tight`` needs 17 and
drops trailing words (``burned N observed`` -> ``burn N``, LAUNCHPAD's own
``· 24h`` and its clock); ``minimal`` needs 13 and drops units and
connective words down to bare numbers and flags.

``MINIMAL_WIDTH`` is still 13, but its anchor changed hands. It used to be
tied for widest by two strings: LP's alarm ``OWNER CHANGED`` and SUPPLY's
own quantity (``2,376,732 IMD``, both 13 columns). LP is gone, and nothing
LAUNCHPAD or FLOW renders comes close -- their longest minimal-tier line is
11 columns (``73 creators`` / ``-- creators``, and ``4,724 swaps``, from the
real 2026-08-23 launchpad state this row now reads). SUPPLY's quantity is
therefore the sole anchor left, unaccompanied rather than tied, and the
constant did not need to move to stay true: ``test_every_hero_tier_fits_
the_width_it_advertises`` still measures every state at every tier rather
than trusting this paragraph.

Titles and quantities are never shortened by tier: they are rendered whole
at every width (LAUNCHPAD/FLOW's own ``as of`` clock is the one exception,
and it is dropped rather than shortened -- see above). A quantity that
outgrows its box lights the border ``‹ widen`` marker instead of being cut
-- a number cut mid-digit still reads as a number, which is worse than an
announced omission.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static

from maxpane_dashboard.widgets.markup_safety import safe_markup, visible_len
from maxpane_dashboard.widgets.surf._fmt import (
    DASH,
    EMDASH,
    as_float,
    fmt_compact,
)

#: Marker raised in a box's bottom border when even ``minimal`` does not fit.
#: The border, not a content line: the boxes carry five content lines inside a
#: height-7 frame and have no sixth to spare (see the DEFAULT_CSS note below).
WIDEN_HINT = "‹ widen"

#: Rendered columns each layout needs.  Measured from the strings the boxes
#: below actually emit -- ``test_every_hero_tier_fits_the_width_it_advertises``
#: renders every state at every tier and measures it, so a copy edit that
#: outgrows its tier fails there rather than on a user's terminal.
COMPACT_WIDTH = 22  # "burned 15,745 observed"
TIGHT_WIDTH = 17    # "2000/2000 written" -- see below
MINIMAL_WIDTH = 13  # "2,376,732 IMD" (SUPPLY's quantity -- see the docstring)

TIER_WIDTHS = {
    "compact": COMPACT_WIDTH,
    "tight": TIGHT_WIDTH,
    "minimal": MINIMAL_WIDTH,
}


def _tier_for(width: int) -> str:
    """Widest box layout that fits ``width`` rendered columns.

    ``width <= 0`` means "not laid out yet" and optimistically picks the
    widest; :meth:`SurfHero.on_resize` re-renders once the box has a size.
    """
    if width <= 0 or width >= COMPACT_WIDTH:
        return "compact"
    if width >= TIGHT_WIDTH:
        return "tight"
    return "minimal"


def _short(tier: str) -> bool:
    """``tight`` or narrower: the tier that gives up decoration."""
    return tier in ("tight", "minimal")


def _as_int(value):
    """Coerce to ``int`` or return ``None`` -- never raise, never 0-coerce.

    LAUNCHPAD's three fields are counts, not amounts: ``as_float`` would
    accept them but formatting a coerced float with ``{:,}`` prints a
    trailing ``.0`` (``"146.0"``, not ``"146"``). A dedicated int coercion
    keeps the same never-raise, never-0-for-a-failure contract as
    ``as_float`` without that cosmetic bug, and rejects ``bool`` for the
    same reason ``as_float`` does -- ``True``/``False`` are ``int``
    subclasses in Python and would otherwise silently coerce to 1/0.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# -- box bodies (pure: a state and a tier in, markup lines out) --------


def _launchpad_lines(coin_count, new_24h, creator_count, as_of_hhmm, tier: str) -> list[str]:
    """LAUNCHPAD box: the population, its growth and who is building it.

    Carries the launchpad tier's OWN clock on the title line. The title bar
    above shows the fast tier's ``as of``, and these numbers are up to ten
    minutes older than that -- rendering them under the fast clock would be
    exactly the "stale number presented as live" the house rules forbid.
    At ``tight``/``minimal`` the clock is dropped; those widths belong to
    terminals with nowhere near enough columns to read the whole row anyway.

    ``new_24h`` gets its own three-state handling within the box: a genuine
    ``0`` (zero launches today, a real and common state) renders as ``0``,
    a failed read for that one field alone renders a dash, and only when
    *every* field here is unread does the line collapse to ``no read yet``
    instead -- three distinct claims, not two.
    """
    title = "LAUNCHPAD"
    if as_of_hhmm and not _short(tier):
        title = f"LAUNCHPAD · {safe_markup(str(as_of_hhmm))}"

    count = _as_int(coin_count)
    new = _as_int(new_24h)
    creators = _as_int(creator_count)

    big = f"[bold]{count:,} coins[/]" if count is not None else f"[dim]{EMDASH}[/]"

    if count is None and new is None and creators is None:
        # Nobody has ever answered -- distinct from a real "0 new" below.
        second = "[dim]no read yet[/]"
        third = "[dim] [/]"
    else:
        new_str = f"{new:,}" if new is not None else DASH
        second_body = f"{new_str} new" if _short(tier) else f"{new_str} new · 24h"
        second = f"[dim]{second_body}[/]"

        creators_str = f"{creators:,} creators" if creators is not None else f"{DASH} creators"
        third = f"[dim]{creators_str}[/]"

    return [f"[dim]{title}[/]", "", big, second, third]


def _flow_lines(swap_count, trader_count, creator_eth_owed, as_of_hhmm, tier: str) -> list[str]:
    """FLOW box: how much the launchpad population trades, and what it is owed.

    Same slower clock as LAUNCHPAD, off the identical ``as_of_hhmm`` -- both
    boxes are fed by the same 600s sweep, so they carry the same freshness
    marker rather than each guessing independently. ``creator_eth_owed`` is
    the ETH side of the pipeline BURN's own box displays the IMD side of
    (``burn_accrued``/``burn_staged``); the two never disagree because the
    manager builds both from the same read, but this box is the only one on
    the row that names the ETH the pipeline currently owes its creators.
    """
    title = "FLOW"
    if as_of_hhmm and not _short(tier):
        title = f"FLOW · {safe_markup(str(as_of_hhmm))}"

    swaps = _as_int(swap_count)
    traders = _as_int(trader_count)
    eth = as_float(creator_eth_owed)

    big = f"[bold]{swaps:,} swaps[/]" if swaps is not None else f"[dim]{EMDASH}[/]"

    if swaps is None and traders is None and eth is None:
        second = "[dim]no read yet[/]"
        third = "[dim] [/]"
    else:
        traders_str = f"{traders:,} traders" if traders is not None else f"{DASH} traders"
        second = f"[dim]{traders_str}[/]"

        eth_str = f"{eth:.4f} ETH" if eth is not None else f"{DASH} ETH"
        third = f"[dim]{eth_str}[/]"

    return [f"[dim]{title}[/]", "", big, second, third]


def _burn_lines(burn_accrued, burn_staged, burn_ready, imd_burned_cum, tier: str) -> list[str]:
    """BURN box: the permissionless bridge-and-burn pipeline's own state.

    Read-only: this box *displays* that ``bridgeToBaseBurnReceiver()`` is
    callable by anyone; it never offers to call it (CLAUDE.md hard
    constraint 1 -- no signer, no transactor, no calldata construction
    anywhere in this repo). ``burn_ready`` is tri-state and gets its own
    headline so ``True``/``False``/``None`` cannot collapse into two
    strings: ``None`` means "cannot tell", not "not ready".

    ``burn_accrued``/``burn_staged`` have a representable zero -- ``0.0``
    means "we looked and nothing has accrued/been staged", ``None`` means
    the read failed -- so they are formatted through ``fmt_compact`` (which
    turns ``None`` into ``"--"``, never ``"0"``) rather than coerced
    together. They share one line because the box has no third to spare,
    which is also why they are compact-formatted rather than full-precision
    like a raw amount would be: a combined line has no room for
    comma-grouped digits at this box's width budget.
    """
    accrued = as_float(burn_accrued)
    staged = as_float(burn_staged)
    cum = as_float(imd_burned_cum)

    if burn_ready is True:
        big = "[bold $success]READY[/]"
    elif burn_ready is False:
        big = "[bold]NOT READY[/]"
    else:
        big = f"[dim]{EMDASH}[/]"

    acc_str = fmt_compact(accrued) if accrued is not None else DASH
    stg_str = fmt_compact(staged) if staged is not None else DASH
    pipeline = f"{acc_str}/{stg_str}" if _short(tier) else f"acc {acc_str} · stg {stg_str}"

    # Same three-state shape as SUPPLY's own burn line (None -> dash,
    # <=0 -> "no burn yet" in words, >0 -> the quantity) -- it is the same
    # accumulator, just also relevant to the pipeline that produces it.
    if cum is None:
        cum_line = f"burn {DASH}" if _short(tier) else f"burned {DASH}"
    elif cum <= 0:
        cum_line = "no burn yet" if _short(tier) else "no burn observed yet"
    else:
        cum_line = f"burn {cum:,.0f}" if _short(tier) else f"burned {cum:,.0f} observed"

    return ["[dim]BURN[/]", "", big, f"[dim]{pipeline}[/]", f"[dim]{cum_line}[/]"]


def _supply_lines(imd_supply, imd_burned_cum, tier: str) -> list[str]:
    """SUPPLY box: IMD totalSupply + the burn *this install has observed*."""
    supply = as_float(imd_supply)
    burned = as_float(imd_burned_cum)
    # None is a failed read, never 0 -- the false-BURN twin (PRD §6.1).  The
    # quantity is never abbreviated or cut: if it outgrows the box the marker
    # fires instead, because a number cut mid-digits still reads as a number.
    big = f"[bold]{supply:,.0f} IMD[/]" if supply is not None else f"[dim]{EMDASH}[/]"
    # Three states, because the key has three meanings (WP4.5):
    #   None -> no successful supply read yet / read failed  -> dash
    #   0.0  -> watched, nothing moved                       -> say so in words
    #   >0   -> the burn observed since we started watching  -> quantity
    # "observed", not "cum": the ~58,849 IMD of PRD §1 was burned before any
    # install existed and this widget can never see it, so a bare
    # "burned 0 cum" on day one would be a confident false statement.  The
    # narrow forms keep that distinction -- "burn N" is still scoped by the
    # box, and "no burn yet" still refuses to claim none was ever burned.
    if burned is None:
        second = f"burn {DASH}" if _short(tier) else f"burned {DASH}"
    elif burned <= 0:
        second = "no burn yet" if _short(tier) else "no burn observed yet"
    else:
        second = (
            f"burn {burned:,.0f}" if _short(tier) else f"burned {burned:,.0f} observed"
        )
    return ["[dim]IMD SUPPLY[/]", "", big, f"[dim]{second}[/]", "[dim] [/]"]


class SurfHeroBox(Static):
    """A single hero box: title, big line, two subtitle lines."""

    def render_lines_at_tier(self, build) -> None:
        """Render ``build(tier)`` at this box's own width, marker and all.

        ``build`` takes a tier name and returns the five markup lines.  The
        tier comes from *this* box's width rather than the row's, because
        ``1fr`` rounding leaves neighbouring boxes a column apart and the
        narrow one is the one that has to fit.
        """
        width = self.content_size.width
        lines = build(_tier_for(width))
        # The marker is the last resort, not the first: it fires only when
        # the narrowest copy still does not fit, which is what keeps it dark
        # in normal operation and therefore worth reading.  `text-overflow:
        # ellipsis` remains the backstop underneath -- but now an announced
        # one.
        over = width > 0 and any(visible_len(line) > width for line in lines)
        self.border_subtitle = WIDEN_HINT if over else ""
        self.update("\n".join(lines))


class SurfHero(Horizontal):
    """Row of four hero boxes: LAUNCHPAD · FLOW · BURN · SUPPLY."""

    # Height 7 with zero vertical padding, like FWAHeroMetrics: the boxes
    # carry five content lines and `padding: 1 2` would clip the last one
    # silently (see the WP-10 hazard note in fwa_hero_metrics.py).
    DEFAULT_CSS = """
    SurfHero {
        height: 7;
    }
    SurfHero > SurfHeroBox {
        width: 1fr;
        height: 7;
        padding: 0 2;
        margin: 0 1;
        border: solid $panel;
        background: $surface;
        content-align: center middle;
        text-align: center;
        text-wrap: nowrap;
        text-overflow: ellipsis;
        border-subtitle-color: $warning;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # The raw values, not formatted lines, so a resize re-lays them out.
        self._payload: dict = {}

    def compose(self) -> ComposeResult:
        for box_id in ("surf-hero-launchpad", "surf-hero-flow", "surf-hero-burn", "surf-hero-supply"):
            yield SurfHeroBox("[dim]Loading...[/]", id=box_id, classes="surf-hero-box")

    def update_data(
        self,
        launchpad_coin_count=None,
        launchpad_new_24h=None,
        launchpad_creator_count=None,
        launchpad_swap_count=None,
        launchpad_trader_count=None,
        launchpad_creator_eth_owed=None,
        launchpad_as_of_hhmm=None,
        burn_accrued=None,
        burn_staged=None,
        burn_ready=None,
        imd_supply=None,
        imd_burned_cum=None,
        **_kwargs,
    ) -> None:
        """Refresh all four boxes from the manager's flat dict (PRD §5 hero).

        ``**_kwargs`` swallows any keyword the caller still passes that this
        signature no longer names -- e.g. ``screens/surf.py`` still sends
        ``pool_venue``/``lp_state``/etc. until Task 12 rewires it to the
        ``launchpad_*`` keys above. Those boxes are gone; the keys are
        silently ignored rather than raising, so an un-rewired screen
        degrades to LAUNCHPAD/FLOW showing ``no read yet`` instead of
        crashing.
        """
        self._payload = {
            "launchpad_coin_count": launchpad_coin_count,
            "launchpad_new_24h": launchpad_new_24h,
            "launchpad_creator_count": launchpad_creator_count,
            "launchpad_swap_count": launchpad_swap_count,
            "launchpad_trader_count": launchpad_trader_count,
            "launchpad_creator_eth_owed": launchpad_creator_eth_owed,
            "launchpad_as_of_hhmm": launchpad_as_of_hhmm,
            "burn_accrued": burn_accrued,
            "burn_staged": burn_staged,
            "burn_ready": burn_ready,
            "imd_supply": imd_supply,
            "imd_burned_cum": imd_burned_cum,
            "seen": True,
        }
        self._render_view()

    def on_resize(self, _event=None) -> None:
        """Re-render: each box's tier is a function of its own width."""
        if self._payload:
            self._render_view()

    # -- boxes ----------------------------------------------------------

    def _render_view(self) -> None:
        data = self._payload
        try:
            boxes = {
                key: self.query_one(f"#surf-hero-{key}", SurfHeroBox)
                for key in ("launchpad", "flow", "burn", "supply")
            }
        except Exception:  # not composed yet
            return

        boxes["launchpad"].render_lines_at_tier(
            lambda tier: _launchpad_lines(
                data.get("launchpad_coin_count"),
                data.get("launchpad_new_24h"),
                data.get("launchpad_creator_count"),
                data.get("launchpad_as_of_hhmm"),
                tier,
            )
        )
        boxes["flow"].render_lines_at_tier(
            lambda tier: _flow_lines(
                data.get("launchpad_swap_count"),
                data.get("launchpad_trader_count"),
                data.get("launchpad_creator_eth_owed"),
                data.get("launchpad_as_of_hhmm"),
                tier,
            )
        )
        boxes["burn"].render_lines_at_tier(
            lambda tier: _burn_lines(
                data.get("burn_accrued"),
                data.get("burn_staged"),
                data.get("burn_ready"),
                data.get("imd_burned_cum"),
                tier,
            )
        )
        boxes["supply"].render_lines_at_tier(
            lambda tier: _supply_lines(
                data.get("imd_supply"), data.get("imd_burned_cum"), tier
            )
        )
