"""Hero row for the surf dashboard: HOOK · LP · GATE · SUPPLY.

Four boxes answering PRD §4's hero-left slot:

* **HOOK**   -- v4 hook status: NOT LIVE / LAUNCHED, always in words.
  ``None`` renders ``hook unconfirmed``, which has to be true of the *two*
  things the manager means by it (``SurfManager._hook_status``): the logs
  group never answered at all, **or** the window held a hooked
  ``Initialize`` whose signer could not be attributed. The second one did
  read something -- ``PoolManager.initialize()`` is permissionless, so an
  unattributed hooked pool is evidence of somebody, just not of the dev --
  so the older ``status unknown`` understated it. ``unconfirmed`` claims
  neither a launch nor a clean window, which is the only honest reading of
  both.
* **LP**     -- position #1167726's composition (IMD/WETH sides), raw
  liquidity, and the owner sanity flag.  ``lp_owner_ok=False`` means the
  position NFT moved -- the committed launch precondition -- and renders
  loud; ``None`` renders unknown, never the checkmark.
* **GATE**   -- identityAllowed() state + identities written.  The ``/2000``
  denominator is the IDMD cap: minted out 2026-05-14 on an
  ownership-bricked contract (identity_token.json ``total_supply: 2000``),
  so unlike every live metric it cannot drift.
* **SUPPLY** -- IMD totalSupply + the burn *this install has observed*.
  ``imd_burned_cum`` is an accumulator over successive supply readings
  (WP4.5), so it covers the observation window and nothing before it: the
  ~58,849 IMD burned across 05-16 / 07-31 / 08-05 predates every install and
  has no keyless source (WP4 open issue 4).  The copy therefore says
  ``observed``, never ``cum``, and the three states are distinct: ``None`` ->
  em-dash (no supply read yet, or the read failed), ``0.0`` -> ``no burn
  observed yet`` (we have watched, nothing moved -- printing ``burned 0``
  would assert that no IMD was ever burned, which is false), positive -> the
  quantity.  A ``None`` supply is a failed read and renders an em-dash:
  rendering ``0`` here is the visual twin of the false-BURN bug the data
  layer guards against.

Copied from ``fwa/fwa_hero_metrics.py`` and adapted to the surf data
contract (PRD §5 ``hero`` keys).  Primitives only: this module imports
nothing from the data layer.

Width behaviour
---------------

A hero box is one quarter of the **full-width** hero row, so its budget is
roughly the terminal's columns over four: measured on the real screen,
**16 content columns at 100 terminal columns, 22 at 119, 26 at 135, 27 at
139, 34 at 169, 42 at 200**.  ``1fr`` rounding leaves neighbouring boxes a
column apart, which is why each box picks its tier from *its own* width
rather than the row's (see :meth:`SurfHeroBox.render_lines_at_tier`).

Until 2026-08-09 the row was shared with ``SurfSignals`` and the four
boxes divided a ``3fr`` half of it: 13 content columns at 139, and the
``full`` tier's 24 arrived at about 220 -- past anything a laptop reaches
at the forced 17 pt, i.e. a tier nobody could ever see.  Full width makes
``full`` the tier every real terminal gets: it needs 24 content columns,
which arrives at **127 terminal columns**, and the marker below is
unreachable above **81**.  The tiers were not re-cut for that: they are
the widths their own copy measures, and it is the geometry that moved.

Two answers were considered and rejected.  A bare ``‹ widen`` marker would
be lit on every terminal anyone owns, which is the trap ``signals.py``
documents and ``fwa_signals.py`` records before it: a marker that is
always on says nothing.  Accepting the CSS ellipsis is worse, because the
boxes carry *numbers* and *titles* -- ``burned 15,74…`` still reads as a
quantity and ``IDENTITY GA…`` reads as a different panel.

So the boxes shed **whole fields**, in a fixed order, and the marker fires
only when the *narrowest* tier still does not fit (see :func:`_tier_for`):

===========  =====  ===================================================
Tier         Needs  What it gives up
===========  =====  ===================================================
``compact``  22     nothing
``tight``    17     ``burned N observed`` -> ``burn N``;
                    ``owner ✓ frenpet.eth`` -> ``owner ✓`` (the tick
                    *is* the assertion, the ENS name is decoration)
``minimal``  13     ``N/2000 written`` -> ``N/2000``;
                    ``since 2026-05-14`` -> ``2026-05-14``;
                    ``detectors armed`` -> ``armed``
===========  =====  ===================================================

The LP box carries no liquidity field.  There was one -- the position's
raw v3 ``L``, a uint128 that renders ``2.16e+18`` because K/M/B suffixes
lie at that magnitude -- and it was the widest tier's only content, so a
``full`` tier existed to hold it.  It was dropped on request: scientific
notation of an unnamed unit told a reader nothing that ``142.71 WETH``
does not, and it cost the most columns on the row.  The tier above
``compact`` went with it rather than becoming a tier that renders
identically to its neighbour.

Titles and quantities are never in that table: they are rendered whole at
every tier.  ``MINIMAL_WIDTH`` is 13 precisely because three of them are
13 columns wide -- ``IDENTITY GATE``, ``OWNER CHANGED`` and today's
``2,376,732 IMD``.  A supply that outgrows its box is the one case the
marker exists for, and it fires rather than the digits being cut.
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

#: The hook vocabulary the *manager* emits, spelled exactly as
#: ``SurfManager._hook_status()`` returns it and as WP0's ``SURF_KEYS`` comment
#: and PRD §4 freeze it.  Named constants rather than inline literals because
#: the widget and the manager have to agree on the spelling and nothing else
#: enforces it: a widget branching on ``"not_live"`` still *renders* -- through
#: the unknown-value arm -- so the disagreement is invisible until someone
#: reads the subtitle on launch day.
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
MINIMAL_WIDTH = 13  # "IDENTITY GATE" / "OWNER CHANGED" / "2,376,732 IMD"

# TIGHT_WIDTH was 16, measured off "since 2026-05-14", because the tier sweep
# only ever fed the gate box ``identities_written`` of 1 and None. The IDMD cap
# is 2000 and the counter can reach it, at which point the tight tier renders
# "2000/2000 written" -- 17 columns, one past its own advertised width. The
# effect was not a silent cut (the marker fires on the overflow, correctly) but
# a box on 16 columns advertising a loss instead of dropping to ``minimal``,
# which fits "2000/2000" in 9. The sweep now includes the cap.

TIER_WIDTHS = {
    "compact": COMPACT_WIDTH,
    "tight": TIGHT_WIDTH,
    "minimal": MINIMAL_WIDTH,
}

#: Hard cap on the *unrecognised* hook headline, independent of the tier: it
#: is third-party-ish text in a fixed-height box, so it is sliced (and only
#: then escaped) before it can reach the parser.
_HOOK_HEADLINE_CAP = 18


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


def _hook_lines(hook_status, tier: str) -> list[str]:
    """HOOK box: the launch state, always in words."""
    status = str(hook_status or "").strip()
    if not status:
        # Two producers, one copy, and it has to be true of both: the logs
        # group never answered, *or* the window held a hooked Initialize
        # whose signer could not be read. The second one *did* read
        # something, so "status unknown" understated it -- "unconfirmed"
        # says the only thing true either way: we have not earned an answer.
        return [
            "[dim]V4 HOOK[/]", "", f"[dim]{EMDASH}[/]",
            "[dim]unconfirmed[/]" if _short(tier) else "[dim]hook unconfirmed[/]",
            "[dim] [/]",
        ]

    # Canonical form: collapse whitespace, upper-case.  The manager already
    # sends "NOT LIVE"/"LAUNCHED"; this only absorbs case/spacing drift, it
    # does NOT invent a second vocabulary.
    canon = " ".join(status.split()).upper()
    if canon == HOOK_NOT_LIVE:
        big = f"[bold $warning]{HOOK_NOT_LIVE}[/]"
        sub = "armed" if tier == "minimal" else "detectors armed"
    elif canon == HOOK_LAUNCHED:
        # The flagship event: $success styling is the point (PRD §4).
        big = f"[bold $success]{HOOK_LAUNCHED}[/]"
        sub = "live" if tier == "minimal" else "v4 hook live"
    else:
        # Tomorrow's vocabulary: escaped AFTER flattening/slicing/upper-
        # casing so a hostile or merely novel value renders literally
        # (PRD §6.3).  Slicing ``canon`` rather than ``status`` also keeps a
        # newline out of a fixed-height box -- these are 5 content lines in
        # a height-7 frame, so an extra line clips silently.  The cut is
        # visible, because this is prose rather than a number or a title.
        limit = min(_HOOK_HEADLINE_CAP, TIER_WIDTHS[tier])
        head = canon if len(canon) <= limit else canon[: limit - 1] + "…"
        big = f"[bold]{safe_markup(head)}[/]"
        sub = "unrecognized" if _short(tier) else "unrecognized status"
    return ["[dim]V4 HOOK[/]", "", big, f"[dim]{sub}[/]", "[dim] [/]"]


def _lp_lines(lp_imd, lp_weth, lp_owner_ok, tier: str) -> list[str]:
    """LP box: the pool sides and the owner sanity flag.

    No liquidity field: the position's raw v3 ``L`` used to render here as
    ``2.16e+18`` and was dropped on request -- see the module docstring.
    ``lp_liquidity`` is still a manager key and still feeds the LP
    MIGRATION detector; it simply has no box of its own any more.
    """
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
        # MINIMAL_WIDTH at 13 along with the titles.
        third = "[bold $error]OWNER CHANGED[/]"
    else:
        third = f"[dim]owner {DASH}[/]"
    return ["[dim]LP #1167726[/]", "", big, f"[dim]{second}[/]", third]


def _gate_lines(gate_open, identities_written, tier: str) -> list[str]:
    """GATE box: identityAllowed() state + identities written."""
    if gate_open is True:
        big = "[bold $success]OPEN[/]"
        sub = (
            "can write"
            if tier == "minimal"
            else "can write now" if tier == "tight" else "holders can write now"
        )
    elif gate_open is False:
        big = "[bold]CLOSED[/]"
        # The date is the fact; "since" is grammar.
        sub = "2026-05-14" if tier == "minimal" else "since 2026-05-14"
    else:
        big = f"[dim]{EMDASH}[/]"
        sub = "gate unknown"
    try:
        # The `/2000` denominator is the IDMD cap (see the module docstring):
        # a documented number that cannot drift, unlike every live metric.
        count = f"{int(identities_written)}/2000"
        written = count if tier == "minimal" else f"{count} written"
    except (TypeError, ValueError):
        written = f"{DASH} written" if tier != "minimal" else DASH
    return ["[dim]IDENTITY GATE[/]", "", big, f"[dim]{written}[/]", f"[dim]{sub}[/]"]


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
    """Row of four hero boxes: HOOK · LP · GATE · SUPPLY."""

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
        for box_id in ("surf-hero-hook", "surf-hero-lp", "surf-hero-gate", "surf-hero-supply"):
            yield SurfHeroBox("[dim]Loading...[/]", id=box_id, classes="surf-hero-box")

    def update_data(
        self,
        hook_status=None,
        lp_imd=None,
        lp_weth=None,
        lp_owner_ok=None,
        gate_open=None,
        identities_written=None,
        imd_supply=None,
        imd_burned_cum=None,
        **_kwargs,
    ) -> None:
        """Refresh all four boxes from the manager's flat dict (PRD §5 hero)."""
        self._payload = {
            "hook_status": hook_status,
            "lp_imd": lp_imd,
            "lp_weth": lp_weth,
            "lp_owner_ok": lp_owner_ok,
            "gate_open": gate_open,
            "identities_written": identities_written,
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
                for key in ("hook", "lp", "gate", "supply")
            }
        except Exception:  # not composed yet
            return

        boxes["hook"].render_lines_at_tier(
            lambda tier: _hook_lines(data.get("hook_status"), tier)
        )
        boxes["lp"].render_lines_at_tier(
            lambda tier: _lp_lines(
                data.get("lp_imd"),
                data.get("lp_weth"),
                data.get("lp_owner_ok"),
                tier,
            )
        )
        boxes["gate"].render_lines_at_tier(
            lambda tier: _gate_lines(
                data.get("gate_open"), data.get("identities_written"), tier
            )
        )
        boxes["supply"].render_lines_at_tier(
            lambda tier: _supply_lines(
                data.get("imd_supply"), data.get("imd_burned_cum"), tier
            )
        )
