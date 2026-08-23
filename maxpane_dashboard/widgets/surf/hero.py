"""Hero row for the surf dashboard: POOL · LP · BURN · SUPPLY.

Four boxes answering PRD §4's hero-left slot, rebuilt 2026-08-23 for the v4
launchpad. The two boxes it replaces asked questions the world stopped
answering: **HOOK** hunted a v4 hook on the IMD/WETH pool that will never
exist -- the dev publicly retracted that plan on 2026-08-16 and the live
pool is hookless -- and **GATE** read ``identityAllowed()``, which now has a
seat of its own on the signals rail (``widgets/surf/signals.py``) alongside
the other eight detectors, so it does not need a hero box too.

* **POOL**   -- which pool is currently live (``pool_venue``, derived by the
  manager from ``lp_state``: ``"v3"`` while the old NFPM position still
  answers, ``"v4"`` once it reverts), its fee tier and USD liquidity, and
  how many other ETH/IMD v4 pools exist. 38 ETH/IMD v4 pools sit on mainnet
  and 37 of them are third-party decoys at fee tiers up to 98% -- so when
  ``pool_id_source == "fallback"`` (``LaunchpadHook.imdEthPoolId()`` did not
  answer this cycle and the vendored constant was used instead) the box
  says so instead of implying it knows which pool this is.
* **LP**     -- the v3 position's IMD/WETH sides and the owner sanity flag,
  *or* the fact that it migrated. ``lp_state == "gone"`` means
  ``ownerOf(#1167726)`` (or the equivalent balance read) reverted
  ``Invalid token ID`` this cycle -- the contract answered, and the answer
  was "this position does not exist any more". That is a **completed
  migration**, not an unknown, and it must never render the same as
  ``lp_state is None`` (nobody answered at all, still the honest dash).
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

``HOOK_NOT_LIVE``/``HOOK_LAUNCHED`` are kept as dead exports purely so
``tests/screens/test_surf_screen.py``'s top-level ``from ...hero import
HOOK_NOT_LIVE`` -- not yet updated, that file belongs to Tasks 12/13 --
does not fail to *collect*. Nothing in this module still branches on them.

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
drops trailing words (``burned N observed`` -> ``burn N``); ``minimal``
needs 13 and drops units and connective words down to bare numbers and
flags. ``MINIMAL_WIDTH`` is still 13 because two of the three anchors that
originally set it are still on the row -- ``OWNER CHANGED`` (LP's alarm,
unshortened at every tier) and today's ``2,376,732 IMD`` (SUPPLY's
quantity) -- even though the third, ``IDENTITY GATE``, left with GATE.

Titles and quantities are never shortened by tier: they are rendered whole
at every width. A quantity that outgrows its box lights the border
``‹ widen`` marker instead of being cut -- a number cut mid-digit still
reads as a number, which is worse than an announced omission. POOL's USD
liquidity is the one number on this row that *is* abbreviated (``$805.9K``,
via ``fmt_compact``) regardless of tier: it is a dollar estimate, not an
exact on-chain integer, and ``pool_liquidity_usd`` is already rendered the
same way in ``widgets/surf/market.py`` -- one convention, not two.
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

#: Dead exports -- see the module docstring's note on why these are kept.
HOOK_NOT_LIVE = "NOT LIVE"
HOOK_LAUNCHED = "LAUNCHED"

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
MINIMAL_WIDTH = 13  # "OWNER CHANGED" / "2,376,732 IMD"

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


# -- box bodies (pure: a state and a tier in, markup lines out) --------


def _pool_lines(
    pool_venue,
    pool_fee_bps,
    pool_liquidity_usd,
    pool_id_source,
    decoy_pool_count,
    tier: str,
) -> list[str]:
    """POOL box: which pool is currently live, and whether the id is trusted.

    ``pool_id_source == "fallback"`` means ``LaunchpadHook.imdEthPoolId()``
    did not answer this cycle and the vendored fallback constant was used
    instead. 38 ETH/IMD v4 pools exist on mainnet and 37 of them are
    third-party decoys, some at fee tiers up to 98%, so an unverified id
    must never be rendered as if the box knew which pool this is -- the
    fallback state pre-empts the fee/decoy line entirely rather than
    showing numbers that might belong to somebody else's pool.
    """
    venue = str(pool_venue or "").strip()
    big = f"[bold]{safe_markup(venue)}[/]" if venue else f"[dim]{EMDASH}[/]"

    liquidity = as_float(pool_liquidity_usd)
    liq_str = f"${fmt_compact(liquidity)}" if liquidity is not None else f"${DASH}"
    second = f"[dim]{liq_str}[/]"

    fallback = str(pool_id_source or "").strip().lower() == "fallback"
    if fallback:
        third = "[bold $warning]id ?[/]" if _short(tier) else "[bold $warning]pool id unverified[/]"
    else:
        try:
            fee_pct = int(pool_fee_bps) / 10000
            fee_str = f"{fee_pct:g}%"
        except (TypeError, ValueError):
            fee_str = None
        try:
            total = int(decoy_pool_count) + 1
            decoy_str = f"1/{total}" if _short(tier) else f"1 of {total}"
        except (TypeError, ValueError):
            decoy_str = None

        if fee_str is not None and decoy_str is not None:
            third = f"[dim]{fee_str} {decoy_str}[/]" if _short(tier) else f"[dim]{fee_str} · {decoy_str}[/]"
        elif fee_str is not None:
            third = f"[dim]{fee_str}[/]" if _short(tier) else f"[dim]{fee_str} fee[/]"
        elif decoy_str is not None:
            third = f"[dim]{decoy_str}[/]" if _short(tier) else f"[dim]{decoy_str} pools[/]"
        else:
            third = f"[dim]fee {DASH}[/]"

    return ["[dim]POOL[/]", "", big, second, third]


def _lp_lines(lp_state, lp_imd, lp_weth, lp_owner_ok, tier: str) -> list[str]:
    """LP box: the v3 position's composition, or the fact that it migrated.

    ``lp_state == "gone"`` is a completed migration and renders as one --
    never as ``unknown`` or a dash, which is what this box used to do when
    the position stopped answering (the whole reason this box was rebuilt).
    ``lp_state is None`` (nobody answered this cycle) still renders the
    honest unknown below; the two must never look the same.
    """
    if lp_state == "gone":
        big = "[bold $success]MIGRATED[/]"
        sub = "v3 closed" if _short(tier) else "v3 position migrated"
        return ["[dim]LP[/]", "", big, f"[dim]{sub}[/]", "[dim] [/]"]

    imd = as_float(lp_imd)
    weth = as_float(lp_weth)
    big = f"[bold]{fmt_compact(imd)} IMD[/]" if imd is not None else f"[dim]{EMDASH}[/]"
    second = f"{weth:,.2f} WETH" if weth is not None else f"{DASH} WETH"
    if lp_owner_ok is True:
        # The tick *is* the assertion; the ENS name is decoration, and
        # `fren…` would distinguish nothing.
        third = "[dim]owner ✓[/]" if _short(tier) else "[dim]owner ✓ frenpet.eth[/]"
    elif lp_owner_ok is False:
        # The position NFT moved: the committed launch precondition.  Never
        # shortened at any tier -- it is the alarm, and it is what sets
        # MINIMAL_WIDTH at 13 along with the SUPPLY quantity.
        third = "[bold $error]OWNER CHANGED[/]"
    else:
        third = f"[dim]owner {DASH}[/]"
    return ["[dim]LP[/]", "", big, f"[dim]{second}[/]", third]


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
    like LP's amounts: a combined line has no room for comma-grouped digits
    at this box's width budget.
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
    """Row of four hero boxes: POOL · LP · BURN · SUPPLY."""

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
        for box_id in ("surf-hero-pool", "surf-hero-lp", "surf-hero-burn", "surf-hero-supply"):
            yield SurfHeroBox("[dim]Loading...[/]", id=box_id, classes="surf-hero-box")

    def update_data(
        self,
        pool_venue=None,
        pool_fee_bps=None,
        pool_liquidity_usd=None,
        pool_id_source=None,
        decoy_pool_count=None,
        lp_state=None,
        lp_imd=None,
        lp_weth=None,
        lp_owner_ok=None,
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
        ``hook_status``/``gate_open``/``identities_written`` until Task 12
        rewires it. Those boxes are gone; the keys are silently ignored
        rather than raising, so an un-rewired screen degrades to POOL/BURN
        showing their unknown state instead of crashing.
        """
        self._payload = {
            "pool_venue": pool_venue,
            "pool_fee_bps": pool_fee_bps,
            "pool_liquidity_usd": pool_liquidity_usd,
            "pool_id_source": pool_id_source,
            "decoy_pool_count": decoy_pool_count,
            "lp_state": lp_state,
            "lp_imd": lp_imd,
            "lp_weth": lp_weth,
            "lp_owner_ok": lp_owner_ok,
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
                for key in ("pool", "lp", "burn", "supply")
            }
        except Exception:  # not composed yet
            return

        boxes["pool"].render_lines_at_tier(
            lambda tier: _pool_lines(
                data.get("pool_venue"),
                data.get("pool_fee_bps"),
                data.get("pool_liquidity_usd"),
                data.get("pool_id_source"),
                data.get("decoy_pool_count"),
                tier,
            )
        )
        boxes["lp"].render_lines_at_tier(
            lambda tier: _lp_lines(
                data.get("lp_state"),
                data.get("lp_imd"),
                data.get("lp_weth"),
                data.get("lp_owner_ok"),
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
