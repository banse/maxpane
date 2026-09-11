"""The `4` POOL4 MARKET body's own hero: IMD PRICE · DOWNSIDE BID · STAKING.

This is a **second** hero, swapped with the market body the way curator swaps
its per-mode heroes -- not a rewrite of ``widgets/surf/hero.py``, which keeps
answering LAUNCHPAD/FLOW/BURN/SUPPLY for the dashboard, ``l`` and ``p`` bodies.
Mounting and toggling both is WP7's job; this module only knows how to paint
three cards from the frozen contract (PRD §5).

Three rules this file exists to hold, each of which has shipped as a bug in
this repo before:

1. **Every card emits on every call.** A card skipped when its value is
   missing keeps whatever it last showed -- or ``Loading...`` forever if the
   first poll was the one that failed -- and the reader cannot tell stale from
   live (MEDI-38). :data:`UNAVAILABLE` is *rendered*, never a skip.
2. **DOWNSIDE BID branches on ``pool4_backstop_state``, three ways, never on
   ``pool4_backstop_eth is None``.** ``deployed`` renders the band, ``none``
   says :data:`NO_BAND` -- we looked, there is no band -- and ``None`` says
   :data:`UNAVAILABLE`: we could not look. Collapsing the middle into either
   neighbour is the curator rail bug verbatim, where a real negative with no
   representable value read confident and green straight through an outage.
3. **Every line reaches ``Static`` as a pre-built ``rich.text.Text``**, parsed
   here inside :func:`~maxpane_dashboard.widgets.surf._pool4.parse_line`'s own
   ``try``. ``Static.update("…[/x]…")`` parses nothing at call time: Textual
   defers ``Content.from_markup`` into the message pump, where the failure
   raises *outside* the screen's ``try/except`` and takes the app down.
   ``SurfFeed._row_text`` is the worked example.

Shared primitives come from ``widgets/surf/_pool4.py``
-----------------------------------------------------
``strip_tags`` / ``parse_line`` / ``join_lines`` / ``widest_line`` are imported,
never restated. The network word is deliberately *not* on a hero card: the hero
is four short columns with no room for a provenance clause, and the five panels
below it each carry ``· MAINNET`` / ``· SEPOLIA`` on their own titles, which is
where amendment A13 put that claim.

Purity
------
Stdlib, ``rich``, ``textual`` and this package's own primitives. No ``data/``,
no ``analytics/``, no clock, no I/O -- ``tests/widgets/test_surf_widget_
contract.py`` walks this file's AST and proves it.

The ``$`` trap
--------------
Rich cannot resolve Textual's ``$``-prefixed theme variables: a style token
spelled with a leading dollar parses cleanly and then raises ``MissingStyle``
at *render* time, inside ``Static.update``, i.e. outside this module's ``try``.
It took the app down once during the ``p`` build. Rich colour names only
(``green``, ``cyan``, ``yellow``, ``dim``) -- and the example is described
rather than written out here, because the test that enforces this reads this
file's own source.

Two contract gaps found while building this, filed rather than fixed
--------------------------------------------------------------------
The plan's own WP5 snippet renders ``pool4_backstop_distance_pct``. **There is
no such key**: WP0 froze nine fast-tier names and that is not one of them, and
``tests/widgets/test_surf_widget_contract.py::
test_update_data_kwargs_are_frozen_contract_keys`` refuses any kwarg that is
not in ``SURF_KEYS``. The distance is therefore *derived here* from two keys
that are frozen -- ``pool4_current_tick`` and ``pool4_backstop_lower_tick`` --
by :func:`band_distance_pct`, which is three lines of stdlib arithmetic and
reproduces the plan's own figure (68196 -> 68280 is 0.84% under) from the
ticks its WP1 fixture uses. See that function for why it is not imported from
``analytics/surf_pool4_depth``.
"""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static

from maxpane_dashboard.widgets.markup_safety import safe_markup
from maxpane_dashboard.widgets.surf._fmt import DASH, as_float, fmt_compact
from maxpane_dashboard.widgets.surf._pool4 import (
    join_lines,
    parse_line,
    strip_tags,
)

__all__ = [
    "BACKSTOP_STATES",
    "CARD_IDS",
    "NO_BAND",
    "NO_VENUE_EDGE",
    "STAKING_WINDOW",
    "TITLE_BID",
    "TITLE_PRICE",
    "TITLE_STAKING",
    "UNAVAILABLE",
    "VENUE_WORDS",
    "SurfPool4UserHero",
    "SurfPool4UserHeroBox",
    "band_distance_pct",
    "fmt_price_usd",
]

# ---------------------------------------------------------------------------
# Copy
# ---------------------------------------------------------------------------

TITLE_PRICE = "IMD PRICE"
TITLE_BID = "DOWNSIDE BID"
TITLE_STAKING = "STAKING"

#: What a card renders when its own read failed. One spelling, shared by all
#: three, so ``out.count("unavailable") == 3`` on an empty payload is a
#: meaningful assertion rather than an accident of three separate wordings.
UNAVAILABLE = "unavailable"

#: DOWNSIDE BID's middle state: ``pool4_backstop_state == "none"``. **We
#: looked and there is no band**, which is a different sentence from
#: :data:`UNAVAILABLE` and must never share its words. PRD §5.2.
NO_BAND = "none deployed"

#: IMD PRICE's subtitle when ``pool4_cheaper_venue`` is ``None`` *and* the gap
#: was read -- i.e. the gap is real but smaller than the two pools' fees
#: summed, so it cannot be arbitraged and naming a venue over it would be
#: telling the reader to lose the spread (PRD §8.3).
#:
#: Not silence, and not a number. Silence is what an unread gap looks like, so
#: reusing it here would merge "we could not look" into "we looked and there is
#: no edge" -- the same two-into-one the backstop card three lines up exists to
#: keep apart. And no venue *word* appears in it, which is what §8.3 asks: the
#: card says an edge does not exist, never which side it would have been on.
NO_VENUE_EDGE = "no venue edge"

#: The window that rides on STAKING's value. **Never the bare word APR**
#: (PRD §8.1): ``pool4_trailing_return_pct`` is realised drips over seven days,
#: lumpy by construction -- zero through a quiet stretch, spiking after a
#: sell-off -- and a bare rate over-promises it. ``pool4_implied_apr_pct`` is
#: the *delivery cap* and is a different number this card never shows.
STAKING_WINDOW = "trailing 7d"

#: ``surf_models.POOL4_BACKSTOP_STATES`` restated, because a widget may not
#: import ``data/`` (CLAUDE.md). Redundancy plus an agreement test is the shape
#: this repo mandates -- ``tests/widgets/test_surf_pool4u_hero.py`` imports both
#: and asserts they agree in both directions, so a third state reddens the
#: suite rather than falling through this module's ``else`` and being painted
#: as an outage.
BACKSTOP_STATES: tuple[str, ...] = ("deployed", "none")

#: ``surf_models.POOL4_VENUE_WORDS`` restated, same rule, same agreement test.
#: ``None`` is a member of neither: it means the gap is below combined fees.
VENUE_WORDS: tuple[str, ...] = ("here", "reference")

#: How each venue word reads on the card. The **magnitude** rides with it and
#: the sign does not: a signed percentage beside a named venue is a double
#: negative a reader has to unpick, and the venue word already carries the
#: direction.
_VENUE_PHRASES = {
    "here": "cheaper here",
    "reference": "cheaper on reference",
}

CARD_IDS = (
    "surf-pool4u-hero-price",
    "surf-pool4u-hero-bid",
    "surf-pool4u-hero-staking",
)

# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def fmt_price_usd(value) -> str:
    """USD per IMD at three decimals -- ``$2.845``, not ``$2.85``.

    ``_fmt.fmt_price`` rounds to cents above $1 and is right for the panels
    that use it, but **this card exists to compare two venues** whose gap is
    routinely under 2% of a ~$2.85 token. At cent precision a 0.2% gap is
    invisible and a 1.5% one is two ticks of the last digit, so the card would
    show a venue clause the number beside it could not corroborate.

    ``--`` on an unreadable price, never ``$0.00``: a zero price is a claim.
    """
    v = as_float(value)
    if v is None:
        return DASH
    if abs(v) >= 1000:
        return f"${v:,.2f}"
    return f"${v:,.3f}"


def band_distance_pct(tick_now, band_lower_tick) -> float | None:
    """How far under spot the backstop band starts, in percent of IMD's price.

    **ETH is currency0 and the pool prices IMD per ETH, so tick up means IMD is
    cheaper.** The band sits *above* spot in tick terms precisely because it
    sits *below* spot in price terms; IMD's price ratio between the band's edge
    and spot is ``1.0001 ** (tick_now - band_lower_tick)``, and what this
    returns is one minus that, as a percentage.

    Checked against the plan's own numbers rather than against itself: 68196
    spot with the band opening at 68280 is 84 ticks, and this returns 0.8365 --
    the ``0.84`` the WP5 hero snippet passed as a payload key that does not
    exist. (Ticks are 1 basis point apart by construction, which is why the
    tick delta and the percentage read almost the same; they diverge with
    distance and this does not approximate them together.)

    **Why it is not imported.** ``analytics/surf_pool4_depth`` (WP1) carries
    tick arithmetic, but it carries no distance helper -- this is a different
    function, not a second copy of one of its -- and it is not on
    ``test_surf_widget_contract._PURE_ANALYTICS_ALLOWED``, which WP9 extends.
    Importing it today reddens the purity sweep for every surf widget. If WP9's
    allowlist lands and that module grows this function, delete this one.

    ``0.0`` -- a representable zero, not ``None`` -- when the band opens at or
    below spot: the band is *at* the money, which is a real reading. ``None``
    is reserved for a tick we could not read.
    """
    now = as_float(tick_now)
    lower = as_float(band_lower_tick)
    if now is None or lower is None:
        return None
    if lower <= now:
        return 0.0
    try:
        return (1.0 - 1.0001 ** (now - lower)) * 100.0
    except (OverflowError, ValueError):  # pragma: no cover - guarded by the clamp
        return None


def _dim(text: str) -> str:
    return f"[dim]{safe_markup(text)}[/]" if text else "[dim] [/]"


# ---------------------------------------------------------------------------
# Card bodies.  Each returns (value markup, subtitle plain text).
# ---------------------------------------------------------------------------


def _price_card(price_usd, gap_pct, cheaper_venue) -> tuple[str, str]:
    """IMD PRICE -- the USD price, and the venue clause beneath it.

    Three subtitles and they are three different statements:

    * a named venue plus the magnitude, once the gap clears combined fees;
    * :data:`NO_VENUE_EDGE` when the gap was read and does not clear them;
    * ``venue gap --`` when the gap itself is unread.

    The last two are the pair that must not merge. An unread gap rendered as
    "no edge" is a confident answer to a question nobody asked the chain.
    """
    shown = fmt_price_usd(price_usd)
    value = f"[bold white]{safe_markup(shown)}[/]" if shown != DASH else ""

    word = strip_tags(cheaper_venue)
    gap = as_float(gap_pct)
    if word in VENUE_WORDS and gap is not None:
        subtitle = f"{_VENUE_PHRASES[word]} {abs(gap):.2f}%"
    elif gap is None:
        subtitle = f"venue gap {DASH}"
    else:
        subtitle = NO_VENUE_EDGE
    return value, subtitle


def _bid_card(state, backstop_eth, tick_now, band_lower_tick) -> tuple[str, str]:
    """DOWNSIDE BID -- the three-state card, and the reason this file exists.

    The branch is on *state* and nothing else. Reading ``backstop_eth is None``
    instead would make an unread ETH amount indistinguishable from a band that
    genuinely is not deployed, and a deployed band whose amount failed to read
    would silently claim there is no bid under the reader at all.
    """
    word = strip_tags(state)
    if word == "none":
        # We looked. There is no band. Said in its own words, and the subtitle
        # says what that means rather than leaving the line blank -- a blank
        # second line under a short value is what a half-rendered card looks
        # like.
        return f"[yellow]{safe_markup(NO_BAND)}[/]", "no band under spot"
    if word != "deployed":
        # Includes `None` and any future vocabulary member this build has not
        # been taught. Naming a band we cannot stand behind is the one thing
        # this card must never do.
        return "", ""

    eth = as_float(backstop_eth)
    shown = f"{eth:,.2f} ETH" if eth is not None else f"{DASH} ETH"
    value = f"[bold white]{safe_markup(shown)}[/]"

    distance = band_distance_pct(tick_now, band_lower_tick)
    if distance is None:
        subtitle = "distance unread"
    else:
        subtitle = f"standing {distance:.2f}% under"
    return value, subtitle


def _staking_card(trailing_pct, vault_assets, staker_count) -> tuple[str, str]:
    """STAKING -- the realised return with its window, and the vault beneath.

    ``0.0`` is a real answer and renders as ``0.0% trailing 7d``: the drip is
    lumpy by construction and a quiet week genuinely returned nothing. Only
    ``None`` reaches :data:`UNAVAILABLE`.
    """
    pct = as_float(trailing_pct)
    value = (
        f"[bold white]{safe_markup(f'{pct:.1f}% {STAKING_WINDOW}')}[/]"
        if pct is not None
        else ""
    )

    parts: list[str] = []
    assets = as_float(vault_assets)
    if assets is not None:
        parts.append(f"{fmt_compact(assets)} IMD")
    count = as_float(staker_count)
    if count is not None:
        parts.append(f"{int(count):,} addrs")
    return value, " · ".join(parts)


# ---------------------------------------------------------------------------
# Widgets
# ---------------------------------------------------------------------------


class SurfPool4UserHeroBox(Static):
    """One hero card: a dim label, a blank, the value, a dim subtitle.

    Four lines rather than ``SurfHero``'s five. That row carries a second
    subtitle line per box; these three cards each have exactly one fact and one
    clause about it, and an always-blank fifth line would spend a terminal row
    on nothing -- on the body PRD §10's open item W7 is about, where the row
    budget is the thing nobody has measured on a real laptop yet.
    """


class SurfPool4UserHero(Horizontal):
    """IMD PRICE · DOWNSIDE BID · STAKING -- the `4` body's own hero row."""

    #: Height 6 for four content lines: the ``solid`` border takes a row top
    #: and bottom and the padding is horizontal only. ``SurfHero`` is 7 for
    #: five lines on the same arithmetic. Vertical padding here would clip the
    #: subtitle in silence (the WP-10 hazard note in ``fwa_hero_metrics.py``).
    DEFAULT_CSS = """
    SurfPool4UserHero {
        height: 6;
    }
    SurfPool4UserHero > SurfPool4UserHeroBox {
        width: 1fr;
        height: 6;
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

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # The raw values, not formatted lines, so a resize re-lays them out.
        self._payload: dict = {}

    def compose(self) -> ComposeResult:
        for card_id in CARD_IDS:
            yield SurfPool4UserHeroBox(
                Text("Loading...", style="dim"),
                id=card_id,
                classes="surf-pool4u-hero-box",
            )

    def update_data(
        self,
        pool4_price_usd=None,
        pool4_venue_gap_pct=None,
        pool4_cheaper_venue=None,
        pool4_backstop_state=None,
        pool4_backstop_eth=None,
        pool4_backstop_lower_tick=None,
        pool4_current_tick=None,
        pool4_trailing_return_pct=None,
        pool4_vault_assets=None,
        pool4_staker_count=None,
        **_kwargs,
    ) -> None:
        """Refresh all three cards from the manager's flat dict.

        Every kwarg is spelled with its full ``pool4_`` contract prefix
        (contract §0.1) and every one of them is a member of ``SURF_KEYS`` --
        the launchpad panels' ``as_of_hhmm`` elision is a carve-out for one
        name on one body and no pool4 panel takes it.

        ``**_kwargs`` is mandatory: the screen splats the whole payload and a
        key added tomorrow must be ignored rather than raise.
        """
        self._payload = {
            "price_usd": pool4_price_usd,
            "venue_gap_pct": pool4_venue_gap_pct,
            "cheaper_venue": pool4_cheaper_venue,
            "backstop_state": pool4_backstop_state,
            "backstop_eth": pool4_backstop_eth,
            "backstop_lower_tick": pool4_backstop_lower_tick,
            "current_tick": pool4_current_tick,
            "trailing_return_pct": pool4_trailing_return_pct,
            "vault_assets": pool4_vault_assets,
            "staker_count": pool4_staker_count,
            "seen": True,
        }
        self._render_view()

    def on_resize(self, _event=None) -> None:
        if self._payload:
            self._render_view()

    def _render_view(self) -> None:
        data = self._payload
        cards = (
            (CARD_IDS[0], TITLE_PRICE, _price_card(
                data.get("price_usd"),
                data.get("venue_gap_pct"),
                data.get("cheaper_venue"),
            )),
            (CARD_IDS[1], TITLE_BID, _bid_card(
                data.get("backstop_state"),
                data.get("backstop_eth"),
                data.get("current_tick"),
                data.get("backstop_lower_tick"),
            )),
            (CARD_IDS[2], TITLE_STAKING, _staking_card(
                data.get("trailing_return_pct"),
                data.get("vault_assets"),
                data.get("staker_count"),
            )),
        )
        for card_id, label, (value, subtitle) in cards:
            self._render_card(card_id, label, value, subtitle)

    def _render_card(
        self, card_id: str, label: str, value: str, subtitle: str
    ) -> None:
        """Write one card, always, degrading to an explicit unavailable state.

        Never a skip and never an early return before the write: a card that
        is not written keeps its previous contents, so a poll that lost this
        one value would leave last poll's number on screen under a title bar
        claiming the payload is seconds old.
        """
        try:
            box = self.query_one(f"#{card_id}", SurfPool4UserHeroBox)
        except Exception:  # not composed yet
            return

        markup = [
            _dim(label),
            "",
            value or f"[yellow]{UNAVAILABLE}[/]",
            _dim(subtitle),
        ]
        lines = [t for t in (parse_line(m) for m in markup) if t is not None]
        try:
            box.update(join_lines(lines))
        except Exception:
            # Last resort: the label and the unavailable word, as plain text
            # with no parsing step left to fail.
            try:
                box.update(Text(f"{label}\n\n{UNAVAILABLE}"))
            except Exception:
                pass
