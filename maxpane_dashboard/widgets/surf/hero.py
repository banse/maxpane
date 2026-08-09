"""Hero row for the surf dashboard: HOOK · LP · GATE · SUPPLY.

Four boxes answering PRD §4's hero-left slot:

* **HOOK**   -- v4 hook status: NOT LIVE / LAUNCHED, always in words.
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
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static

from maxpane_dashboard.widgets.markup_safety import safe_markup
from maxpane_dashboard.widgets.surf._fmt import (
    DASH,
    EMDASH,
    as_float,
    fmt_compact,
    fmt_liquidity,
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


class SurfHeroBox(Static):
    """A single hero box: title, big line, two subtitle lines."""


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
    }
    """

    def compose(self) -> ComposeResult:
        for box_id in ("surf-hero-hook", "surf-hero-lp", "surf-hero-gate", "surf-hero-supply"):
            yield SurfHeroBox("[dim]Loading...[/]", id=box_id, classes="surf-hero-box")

    def update_data(
        self,
        hook_status=None,
        lp_liquidity=None,
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
        self._update_hook(hook_status)
        self._update_lp(lp_liquidity, lp_imd, lp_weth, lp_owner_ok)
        self._update_gate(gate_open, identities_written)
        self._update_supply(imd_supply, imd_burned_cum)

    # -- boxes ----------------------------------------------------------

    def _update_hook(self, hook_status) -> None:
        box = self.query_one("#surf-hero-hook", SurfHeroBox)
        status = str(hook_status or "").strip()
        if not status:
            box.update(f"[dim]V4 HOOK[/]\n\n[dim]{EMDASH}[/]\n[dim]status unknown[/]\n[dim] [/]")
            return
        # Canonical form: collapse whitespace, upper-case.  The manager already
        # sends "NOT LIVE"/"LAUNCHED"; this only absorbs case/spacing drift, it
        # does NOT invent a second vocabulary.
        canon = " ".join(status.split()).upper()
        if canon == HOOK_NOT_LIVE:
            big = f"[bold $warning]{HOOK_NOT_LIVE}[/]"
            sub = "detectors armed"
        elif canon == HOOK_LAUNCHED:
            # The flagship event: $success styling is the point (PRD §4).
            big = f"[bold $success]{HOOK_LAUNCHED}[/]"
            sub = "v4 hook live"
        else:
            # Tomorrow's vocabulary: escaped AFTER flattening/slicing/upper-
            # casing so a hostile or merely novel value renders literally
            # (PRD §6.3).  Slicing ``canon`` rather than ``status`` also keeps a
            # newline out of a fixed-height box -- these are 5 content lines in
            # a height-7 frame, so an extra line clips silently.
            big = f"[bold]{safe_markup(canon[:18])}[/]"
            sub = "unrecognized status"
        box.update(f"[dim]V4 HOOK[/]\n\n{big}\n[dim]{sub}[/]\n[dim] [/]")

    def _update_lp(self, lp_liquidity, lp_imd, lp_weth, lp_owner_ok) -> None:
        box = self.query_one("#surf-hero-lp", SurfHeroBox)
        imd = as_float(lp_imd)
        weth = as_float(lp_weth)
        big = f"[bold]{fmt_compact(imd)} IMD[/]" if imd is not None else f"[dim]{EMDASH}[/]"
        weth_str = f"{weth:,.2f} WETH" if weth is not None else f"{DASH} WETH"
        second = f"{weth_str} · L {fmt_liquidity(lp_liquidity)}"
        if lp_owner_ok is True:
            third = "[dim]owner ✓ frenpet.eth[/]"
        elif lp_owner_ok is False:
            # The position NFT moved: the committed launch precondition.
            third = "[bold $error]OWNER CHANGED[/]"
        else:
            third = f"[dim]owner {DASH}[/]"
        box.update(f"[dim]LP #1167726[/]\n\n{big}\n[dim]{second}[/]\n{third}")

    def _update_gate(self, gate_open, identities_written) -> None:
        box = self.query_one("#surf-hero-gate", SurfHeroBox)
        if gate_open is True:
            big = "[bold $success]OPEN[/]"
            sub = "holders can write now"
        elif gate_open is False:
            big = "[bold]CLOSED[/]"
            sub = "since 2026-05-14"
        else:
            big = f"[dim]{EMDASH}[/]"
            sub = "gate unknown"
        try:
            written = f"{int(identities_written)}/2000 written"
        except (TypeError, ValueError):
            written = f"{DASH} written"
        box.update(f"[dim]IDENTITY GATE[/]\n\n{big}\n[dim]{written}[/]\n[dim]{sub}[/]")

    def _update_supply(self, imd_supply, imd_burned_cum) -> None:
        box = self.query_one("#surf-hero-supply", SurfHeroBox)
        supply = as_float(imd_supply)
        burned = as_float(imd_burned_cum)
        # None is a failed read, never 0 -- the false-BURN twin (PRD §6.1).
        big = f"[bold]{supply:,.0f} IMD[/]" if supply is not None else f"[dim]{EMDASH}[/]"
        # Three states, because the key has three meanings (WP4.5):
        #   None -> no successful supply read yet / read failed  -> dash
        #   0.0  -> watched, nothing moved                       -> say so in words
        #   >0   -> the burn observed since we started watching  -> quantity
        # "observed", not "cum": the ~58,849 IMD of PRD §1 was burned before any
        # install existed and this widget can never see it, so a bare
        # "burned 0 cum" on day one would be a confident false statement.
        if burned is None:
            second = f"burned {DASH}"
        elif burned <= 0:
            second = "no burn observed yet"
        else:
            second = f"burned {burned:,.0f} observed"
        box.update(f"[dim]IMD SUPPLY[/]\n\n{big}\n[dim]{second}[/]\n[dim] [/]")
