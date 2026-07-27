"""Hero metric boxes for the Fake World Assets (FWA) dashboard.

Three boxes laid out horizontally:

* **PULL EV** -- the flagship metric, rendered as a *band* and never as a
  point: best estimate, lower bound, and a coverage badge.  Keyless floor
  prices cover only 22 of 38 collections holding live positions, so a
  single confident number here would be a lie that costs someone ETH.
  The coverage badge is therefore rendered *whenever an EV number is on
  screen* -- the two are inseparable (PRD §3).
* **PRICE** -- the live ``acquisitionFee()`` quote, the harmonic-vs-
  arithmetic gap bar, and the VRF leg *only when the returned tuple says
  it is nonzero* (findings §13.9 -- never a computed guess).
* **CROWN** -- the single-holder top-deposit crown: pot in ETH and USD
  plus the ETH needed to seize it.  A vacant crown renders ``vacant``,
  never ``0`` -- an empty throne and a zero pot are different states.

Two hard rules this file encodes:

1. **Colour is never the sole carrier of the EV sign.**  The band's sign
   is always spelled with an explicit ``▲``/``▼`` glyph *and* a ``+``/
   ``-`` sign in the number, so it survives greyscale and colour-blind
   viewing (PRD §11).
2. **Nothing is hardcoded.**  The harmonic/arithmetic gap is a live-
   varying ratio (measured 3.885× at one block and ≤3.49× two days
   later, findings §13.7); it is rendered from whatever the payload
   carries at the current block, or computed from the two live means --
   never printed as a constant.

Every value is exception-safe: a missing/``None`` scalar collapses to
``"--"``/``"—"`` rather than raising, and each card has an explicit
unavailable state driven by its ``*_available`` flag (PRD §9).

Copied from ``talismans/tal_hero_metrics.py`` and adapted to the FWA data
contract (``FWA_WIDGET_SIGNATURES["FWAHeroMetrics"]``).  Primitives only:
this module imports nothing from the data layer.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static

_DASH = "--"
_EMDASH = "—"

# Gold is reserved for the crown and is used nowhere else in the app (PRD §11).
_GOLD = "#f0c040"

_GAP_BAR_WIDTH = 8
_GAP_FILLED = "█"
_GAP_EMPTY = "░"


# -- format helpers ----------------------------------------------------


def _as_float(value):
    """Coerce to ``float`` or return ``None`` -- never raise."""
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if out != out or out in (float("inf"), float("-inf")):  # NaN / inf
        return None
    return out


def _fmt_eth(value, places: int = 4) -> str:
    v = _as_float(value)
    if v is None:
        return _DASH
    return f"{v:,.{places}f}"


def _fmt_signed(value, places: int = 4) -> str:
    """Signed fixed-point -- the sign glyph is always present."""
    v = _as_float(value)
    if v is None:
        return _DASH
    return f"{v:+,.{places}f}"


def _fmt_usd(value) -> str:
    v = _as_float(value)
    if v is None:
        return _DASH
    if abs(v) >= 1_000_000:
        return f"${v / 1_000_000:,.2f}M"
    if abs(v) >= 1_000:
        return f"${v:,.0f}"
    return f"${v:,.2f}"


def _fmt_int(value) -> str:
    if value is None or isinstance(value, bool):
        return _DASH
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return _DASH


def _short_addr(addr) -> str:
    if not addr:
        return _DASH
    s = str(addr).strip()
    if not s:
        return _DASH
    if len(s) <= 11:
        return s
    return f"{s[:6]}..{s[-4:]}"


def _ev_sign(value) -> tuple[str, str]:
    """Return ``(glyph, colour)`` for an EV figure.

    The glyph carries the sign on its own; the colour is redundant by
    design so the metric survives greyscale (PRD §11).

    Colours are the theme variables ``$success``/``$error``, never the CSS
    names ``green``/``red``.  Textual resolves content markup through the CSS
    name table, where ``green`` is ``#008000`` -- whose contrast tops out at
    **4.09:1 against pure black**, so it fails WCAG AA on *every* possible
    background and no theme can rescue it.  ``$success``/``$error`` are
    required ``Theme`` fields, resolve per theme, and measure 10.39:1 and
    6.82:1 under ``fwa``.  Verified by WP-16's contrast audit.
    """
    v = _as_float(value)
    if v is None:
        return "", "dim"
    if v > 0:
        return "▲", "$success"
    if v < 0:
        return "▼", "$error"
    return "●", "dim"


def _gap_bar(gap, width: int = _GAP_BAR_WIDTH) -> str:
    """Render the harmonic/arithmetic gap as a filled-fraction bar.

    The filled portion is ``width / gap`` -- a wide gap leaves a small
    filled head, which is the point.  The numeric multiple is always
    printed next to the bar, so the bar is never the only carrier.
    """
    g = _as_float(gap)
    if g is None or g <= 0:
        return _GAP_EMPTY * width
    filled = int(round(width / g)) if g >= 1 else width
    filled = max(1, min(width, filled))
    return _GAP_FILLED * filled + _GAP_EMPTY * (width - filled)


def _coverage_badge(priced, total, weight_pct) -> str:
    """``22/38 · 61.3% of weight priced`` -- never omitted next to a number."""
    p = _fmt_int(priced)
    t = _fmt_int(total)
    w = _as_float(weight_pct)
    w_str = f"{w:.1f}" if w is not None else _DASH
    return f"{p}/{t} · {w_str}% of weight priced"


# -- widgets -----------------------------------------------------------


class FWAHeroBox(Static):
    """A single hero metric box: title, big number, two subtitle lines."""

    DEFAULT_CSS = ""


class FWAHeroMetrics(Horizontal):
    """Row of three hero metric boxes: PULL EV · PRICE · CROWN."""

    # NOTE FOR THE THEME (WP-16): the box is `height: 7` like Talismans, but
    # its vertical padding MUST stay 0 -- these cards carry four lines
    # (title, band, bound, coverage badge) and `padding: 1 2` leaves only
    # three visible rows, which silently drops the coverage badge.  That is
    # exactly the failure PRD §3 forbids: an EV number with no coverage next
    # to it.  (TalismansHeroBox loses its subtitle the same way today; do not
    # copy that padding here.)
    DEFAULT_CSS = """
    FWAHeroMetrics {
        height: 7;
    }
    FWAHeroMetrics > FWAHeroBox {
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
        yield FWAHeroBox(
            "[dim]PULL EV[/]\n\n[dim]Loading...[/]",
            id="fwa-hero-ev",
            classes="fwa-hero-box",
        )
        yield FWAHeroBox(
            "[dim]PRICE[/]\n\n[dim]Loading...[/]",
            id="fwa-hero-price",
            classes="fwa-hero-box",
        )
        yield FWAHeroBox(
            "[dim]CROWN[/]\n\n[dim]Loading...[/]",
            id="fwa-hero-crown",
            classes="fwa-hero-box",
        )

    # -- update ---------------------------------------------------------

    def update_data(
        self,
        pull_ev_best_eth=None,
        pull_ev_lower_eth=None,
        ev_available=None,
        ev_collections_priced=None,
        ev_collections_total=None,
        ev_weight_priced_pct=None,
        ev_rebate_eth=None,
        acquisition_fee_eth=None,
        vrf_fee_eth=None,
        quote_total_eth=None,
        price_available=None,
        harmonic_mean_eth=None,
        arithmetic_mean_eth=None,
        hm_am_gap_x=None,
        crown_pot_eth=None,
        crown_pot_usd=None,
        crown_seize_eth=None,
        crown_holder=None,
        crown_vacant=None,
        crown_available=None,
        **_kwargs,
    ) -> None:
        """Refresh all three hero boxes from the manager's flat dict."""
        self._update_ev(
            pull_ev_best_eth,
            pull_ev_lower_eth,
            ev_available,
            ev_collections_priced,
            ev_collections_total,
            ev_weight_priced_pct,
            ev_rebate_eth,
        )
        self._update_price(
            acquisition_fee_eth,
            vrf_fee_eth,
            quote_total_eth,
            price_available,
            harmonic_mean_eth,
            arithmetic_mean_eth,
            hm_am_gap_x,
        )
        self._update_crown(
            crown_pot_eth,
            crown_pot_usd,
            crown_seize_eth,
            crown_holder,
            crown_vacant,
            crown_available,
        )

    # -- PULL EV --------------------------------------------------------

    def _update_ev(
        self,
        best_eth,
        lower_eth,
        available,
        priced,
        total,
        weight_pct,
        rebate_eth,
    ) -> None:
        box = self.query_one("#fwa-hero-ev", FWAHeroBox)
        best = _as_float(best_eth)
        badge = _coverage_badge(priced, total, weight_pct)

        if available is False or best is None:
            # Explicit unavailable state -- never a bare zero (PRD §9).
            box.update(
                f"[dim]PULL EV[/]\n"
                f"[dim]{_EMDASH}[/]\n"
                f"[dim]insufficient data[/]\n"
                f"[dim]{badge}[/]"
            )
            return

        glyph, colour = _ev_sign(best)
        # Sign is carried by the glyph AND the explicit +/- in the number,
        # so colour is redundant rather than load-bearing (PRD §11).
        big = f"[{colour}]{glyph} {_fmt_signed(best)}[/] [dim]ETH[/]"

        lower = _as_float(lower_eth)
        second = f"lower {_fmt_signed(lower)} ETH" if lower is not None else "lower --"
        rebate = _as_float(rebate_eth)
        if rebate is not None and rebate != 0:
            second = f"lower {_fmt_signed(lower)} · reb {_fmt_signed(rebate)}"

        box.update(
            f"[dim]PULL EV[/]\n{big}\n[dim]{second}[/]\n[dim]{badge}[/]"
        )

    # -- PRICE ----------------------------------------------------------

    def _update_price(
        self,
        acquisition_fee_eth,
        vrf_fee_eth,
        quote_total_eth,
        available,
        harmonic_mean_eth,
        arithmetic_mean_eth,
        hm_am_gap_x,
    ) -> None:
        box = self.query_one("#fwa-hero-price", FWAHeroBox)
        fee = _as_float(acquisition_fee_eth)

        if available is False or fee is None:
            box.update(
                f"[dim]PRICE[/]\n"
                f"[dim]{_EMDASH}[/]\n"
                f"[dim]quote unavailable[/]\n"
                f"[dim] [/]"
            )
            return

        big = f"[bold white]{_fmt_eth(fee)}[/] [dim]ETH[/]"

        # Gap line -- a live ratio, computed here only if the payload did
        # not carry it.  Never a constant (findings §13.7).
        harmonic = _as_float(harmonic_mean_eth)
        arithmetic = _as_float(arithmetic_mean_eth)
        gap = _as_float(hm_am_gap_x)
        if gap is None and harmonic is not None and arithmetic is not None and harmonic > 0:
            gap = arithmetic / harmonic
        if harmonic is None or arithmetic is None or gap is None:
            gap_line = f"[dim]hm/am gap {_DASH}[/]"
        else:
            gap_line = (
                f"[dim]{_fmt_eth(harmonic)}[/] [cyan]{_gap_bar(gap)}[/] "
                f"[dim]{_fmt_eth(arithmetic)}[/] [bold]{gap:.2f}×[/]"
            )

        # VRF leg only when the returned tuple says it is nonzero.
        vrf = _as_float(vrf_fee_eth)
        total = _as_float(quote_total_eth)
        parts: list[str] = []
        if vrf is not None and vrf != 0:
            parts.append(f"vrf {_fmt_eth(vrf)}")
        if total is not None:
            parts.append(f"total {_fmt_eth(total)} ETH")
        third = " · ".join(parts) if parts else f"quote {_DASH}"

        box.update(f"[dim]PRICE[/]\n{big}\n{gap_line}\n[dim]{third}[/]")

    # -- CROWN ----------------------------------------------------------

    def _update_crown(
        self,
        pot_eth,
        pot_usd,
        seize_eth,
        holder,
        vacant,
        available,
    ) -> None:
        box = self.query_one("#fwa-hero-crown", FWAHeroBox)

        if available is False:
            box.update(
                f"[dim]CROWN[/]\n"
                f"[dim]{_EMDASH}[/]\n"
                f"[dim]crown unavailable[/]\n"
                f"[dim] [/]"
            )
            return

        seize = _as_float(seize_eth)
        seize_line = (
            f"to seize {_fmt_eth(seize, 3)} ETH"
            if seize is not None and seize > 0
            else f"to seize {_DASH}"
        )

        if vacant:
            # An empty throne is not a zero pot.
            box.update(
                f"[dim]CROWN[/]\n"
                f"[{_GOLD}]vacant[/]\n"
                f"[dim]no incumbent[/]\n"
                f"[dim]{seize_line}[/]"
            )
            return

        pot = _as_float(pot_eth)
        if pot is None:
            big = f"[dim]{_EMDASH}[/]"
        else:
            big = f"[{_GOLD}]{_fmt_eth(pot, 3)}[/] [dim]ETH[/]"

        usd = _fmt_usd(pot_usd) if _as_float(pot_usd) is not None else "usd n/a"
        second = f"{usd} · {_short_addr(holder)}"

        box.update(
            f"[dim]CROWN[/]\n{big}\n[dim]{second}[/]\n[dim]{seize_line}[/]"
        )
