"""POOL4 rail: THE RATCHET -- the reserve, the observed floor, and the
distance between them.

The pool4 hook burns IMD out of the pool's own reserve on every swap. What
stops it is ``capFloor()``: on Sepolia launch 1 a single buy took the reserve
from ``152,030,338.5414`` to **exactly ``50,000,000.000000000000000000``**,
the wei-exact ``capFloor()`` value, so the floor is not merely inferred from a
resting balance -- it *binds the swap path*, and the distance to it is a real
number a reader can act on.

Two things follow, and both are load-bearing here:

1. **The floor is still labelled** :data:`FLOOR_WORD` -- ``observed``, never
   *guaranteed* and never *enforced*. The hook is unverified source; what has
   been proven is that one code path came to rest exactly on the value, not
   that every path must. ``test_the_ratchet_never_promises_the_floor``
   greps the composited body for the forbidden words, and no "safe until" or
   "burns stop at" phrasing may be added.
2. **A reserve *below* the floor is a legitimate state**, not a bug and not a
   degraded read. Launch 1 sits below its own floor today, because a backstop
   rebalance can move the reserve where a swap cannot. The distance is
   therefore rendered signed and is **never clamped to zero**, never flagged
   as an error and never styled as a warning -- which is why the label reads
   ``vs floor`` rather than ``to floor``: one of those words is honest in both
   directions and the other is not.

``pool4_backstop_centred`` is a tri-state and renders three distinct words --
see :func:`_backstop_word`.

The reserve sparkline comes from ``widgets/sparkline_common`` (imported, never
copied -- MEDI-36), and is **omitted entirely** rather than drawn flat when
there are fewer than two points: ``build_sparkline_from_points`` renders a
short series as a flat baseline, and a flat line beside a live reserve is a
claim that the reserve has not moved, which is exactly the "confident and
green through an outage" failure CLAUDE.md records.

Primitives only -- this module imports nothing from ``data/`` or
``analytics/``. Its shared title/escaping helpers come from
``widgets/surf/_pool4.py`` (amendment A13), which also owns the network-word
allowlist every pool4 panel title renders.
"""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from maxpane_dashboard.widgets.markup_safety import safe_markup
from maxpane_dashboard.widgets.sparkline_common import (
    build_sparkline,
    coerce_points,
    fmt_compact,
)
from maxpane_dashboard.widgets.surf._fmt import DASH, as_float, fmt_liquidity
from maxpane_dashboard.widgets.surf._pool4 import (
    GLYPH_HINT,
    WIDEN_HINT,
    join_lines,
    parse_line,
    strip_tags,
    title_text,
    widest_line,
)

__all__ = [
    "COMPACT_WIDTH",
    "FLOOR_WORD",
    "FULL_WIDTH",
    "NO_DECAY_WORD",
    "GLYPH_HINT",
    "RESERVE_SPARK_WIDTH",
    "SurfPool4Ratchet",
    "TITLE",
    "UNAVAILABLE_LINE",
    "WIDEN_HINT",
]

TITLE = "THE RATCHET"
UNAVAILABLE_LINE = "ratchet unavailable"

#: The one word this panel is allowed to attach to the floor. The hook is
#: unverified source: ``capFloor()`` has been *seen* to stop a burn to the wei
#: on Sepolia launch 1, which is evidence about one code path, not a promise
#: about every one. ``guarantee``/``guaranteed``/``enforced`` are forbidden in
#: this panel's rendered body and a test asserts it.
FLOOR_WORD = "observed"

#: What ``pool4_cap_decay_per_day == 0.0`` renders as.
#:
#: **It is not a rate of zero, and it must never print as one.** On Sepolia
#: ``capDecayTokensPerDay()`` returns ``2**128 - 1`` -- a *sentinel* meaning
#: "this deployment has no decay", which divided into whole IMD is ~3.4e20 per
#: day: a confident, absurd number with nothing about it that looks like an
#: error, which is exactly how it would reach a reader unnoticed. WP3 owns the
#: threshold and WP7 resolves it to the representable zero ``0.0`` -- "we
#: looked, and it does not decay" -- keeping ``None`` for the ordinary failed
#: read.
#:
#: So this cell has three renderings and they share no substring:
#: :data:`~._fmt.DASH` (unread), :data:`NO_DECAY_WORD` (looked, no decay), and
#: a rate. ``0.00 IMD/day`` would collapse the middle one into the third and
#: assert a decay rate the chain never reported.
NO_DECAY_WORD = "no decay"

#: Narrow enough to sit beside the reserve value inside a ~40-column rail and
#: still show a shape. ``sparkline_common.SPARK_WIDTH`` (22) is the dashboard
#: body's width and would make this the widest line on the panel by ten
#: columns, which would spend the rail's budget on the least precise thing on
#: it.
RESERVE_SPARK_WIDTH = 16

_LABEL_COLS = 8      # widest label: "backstop", "vs floor"
_GAP = 1

#: Widest full-tier line: the reserve value plus its sparkline.
#: ``8 + 1 + len("152.0M IMD") + 1 + 16``. Pinned against composited output by
#: ``test_the_ratchet_full_width_pin_is_the_widest_full_tier_line``, which
#: compares with ``==`` and so reddens whether the pin is too low or too high.
#: Data-dependent by nature (a nine-figure reserve is one column wider than an
#: eight-figure one), which is why the runtime tier decision measures the
#: lines it actually built rather than comparing the budget against this
#: constant -- see :meth:`SurfPool4Ratchet._render_view`.
#: The binder moved on 2026-09-02. It was the reserve row plus its sparkline
#: (36); it is now the **tick row**, which carries the current tick, the
#: reference tick and the backstop word: ``8 + 1 + len("-34,567 · ref
#: -34,000 · centred")``. Merging the backstop onto that row bought the pool4
#: body a terminal row and cost this panel four columns, and the trade is only
#: sound because this panel is not the one that binds the body's *width* --
#: ``SurfPool4Flow`` needs 52 against this panel's 44 including its column's
#: own gutter, so 36 -> 40 does not reach ``SURF_POOL4_FULL_LAYOUT_COLUMNS``.
#: If FLOW ever narrows below 44, this becomes a width decision again.
FULL_WIDTH = _LABEL_COLS + _GAP + 31                                     # 40

#: One tier below full: the sparkline goes, and so do the three secondary
#: tails -- the supply behind the burn percentage, the raw position liquidity
#: and the reference tick. Every headline number stays: reserve, floor, the
#: signed distance *and its percentage*, the burn share and the backstop word.
COMPACT_WIDTH = _LABEL_COLS + _GAP + 21                                  # 30


def _backstop_word(centred: object) -> str:
    """``centred`` / ``drifted`` / ``unknown`` for ``pool4_backstop_centred``.

    ``SurfBurnPipeline._ready_word``'s tri-state precedent, and its rule:
    the ``None`` word must share **no substring** with either confident
    answer, so a reader (or a grep) can never mistake an indeterminate read
    for a confident negative one. ``NOT CENTRED`` would contain ``CENTRED``,
    and ``off-centre`` would contain ``centre`` -- both fail that rule, and
    both read as the positive answer when a row is scanned rather than read.
    ``centred`` / ``drifted`` / ``unknown`` share no three-character run
    between any pair.

    ``None`` must never render as centred and never as a confident
    "not centred" -- the tri-state sibling of "a failed read is None, never 0".
    """
    if centred is True:
        return "[bold green]centred[/]"
    if centred is False:
        return "[bold]drifted[/]"
    return "[dim]unknown[/]"


def _fmt_imd_compact(value: object) -> str:
    """A pool-scale IMD quantity: ``152.0M``, ``50.0M``, ``1.0B``, ``--``.

    ``_fmt.fmt_imd`` is the burn-scale formatter (two decimals below 1,000)
    and would render a nine-figure reserve as ``152,030,338.54`` -- thirteen
    columns for a number whose last eight digits nobody reads at this
    altitude. The reserve, the floor and the total supply are all in the same
    magnitude band, so they share one formatter.
    """
    v = as_float(value)
    return DASH if v is None else fmt_compact(v)


def _fmt_cap_decay(value: object) -> str:
    """``--`` / ``no decay`` / ``1.0K/day`` -- see :data:`NO_DECAY_WORD`.

    ``as_float`` first, so a bool never sneaks through as ``1.0``; the zero
    test is exact because the producer emits a literal ``0.0`` for the
    resolved sentinel rather than a rounded-down small rate.
    """
    v = as_float(value)
    if v is None:
        return DASH
    if v == 0.0:
        return NO_DECAY_WORD
    return f"{fmt_compact(v)}/day"


def _fmt_signed_imd(value: object) -> str:
    """The signed distance: ``+102.0M`` above the floor, ``-1.2M`` below it.

    **Never clamped.** A reserve below the observed floor is a real state a
    backstop rebalance can produce (see the module docstring), so the minus
    sign is the answer, not an error.
    """
    v = as_float(value)
    if v is None:
        return DASH
    body = fmt_compact(v)
    return f"+{body}" if v > 0 else body


def _fmt_signed_pct(value: object) -> str:
    """``+204.1%`` / ``-2.3%`` / ``--``.

    ``--`` covers both "the floor is zero or unread" and "we could not look":
    the contract makes ``pool4_floor_distance_pct`` ``None`` for either, and
    this panel must never print an infinity for the first.
    """
    v = as_float(value)
    return DASH if v is None else f"{v:+,.1f}%"


def _fmt_pct(value: object) -> str:
    v = as_float(value)
    return DASH if v is None else f"{v:,.2f}%"


def _fmt_eth(value: object) -> str:
    """Pooled ETH; sub-1 balances keep six decimals so a live pool with
    0.0057 ETH in it never renders as ``0.00``.
    """
    v = as_float(value)
    if v is None:
        return DASH
    return f"{v:.6f}" if abs(v) < 1 else f"{v:,.4f}"


def _fmt_tick(value: object) -> str:
    v = as_float(value)
    if v is None:
        return DASH
    try:
        return f"{int(v):,d}"
    except (TypeError, ValueError, OverflowError):
        return DASH


def _reserve_spark(series: object) -> str:
    """The reserve sparkline, or ``""`` when there is not enough history.

    Deliberately **not** ``build_sparkline_from_points``: that helper renders
    a series shorter than ``min_points`` as a flat baseline, and a flat line
    beside a live reserve claims the reserve has not moved. An absent
    sparkline says "no history yet"; a flat one says "nothing is happening",
    and only one of those is true on a cold cache.
    """
    points = coerce_points(series)
    if len(points) < 2:
        return ""
    return build_sparkline([v for _, v in points], width=RESERVE_SPARK_WIDTH)


def _row(label: str, value: str) -> str:
    """One ``label  value`` line. The label is a module literal, so only the
    value can carry third-party bytes and only the value is escaped.
    """
    return f"[dim]{label:<{_LABEL_COLS}}[/]{' ' * _GAP}{value}"


class SurfPool4Ratchet(Vertical):
    """The reserve, the observed floor, and the signed distance between them.

    Read-only (CLAUDE.md hard constraint 1 -- no signer, no transactor, no
    calldata construction anywhere in this repo).
    """

    DEFAULT_CSS = """
    SurfPool4Ratchet {
        height: auto;
    }
    SurfPool4Ratchet > Static {
        width: 100%;
        padding: 0 1;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    """

    #: See ``SurfPool4Hatches._TITLE_PADDING_COLS``: the ``padding: 0 1`` that
    #: eats columns lives on the child ``Static``, not on this container, so a
    #: fit decision made against ``self.size.width`` compares against two
    #: columns more room than a line really has.
    _TITLE_PADDING_COLS = 2

    _SCALAR_KEYS = (
        "tokens_in_pool", "cap_floor", "floor_distance", "floor_distance_pct",
        "burned_supply_pct", "total_supply", "inventory_cap",
        "cap_headroom", "cap_decay_per_day", "eth_in_pool",
        "position_liquidity", "current_tick", "ref_tick", "backstop_centred",
    )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._payload: dict = {}
        self._widen = False

    def compose(self) -> ComposeResult:
        yield Static(TITLE, id="surf-pool4-ratchet-body")

    def on_resize(self, _event=None) -> None:
        if self._payload:
            self._render_view()

    def update_data(
        self,
        pool4_network=None,
        pool4_tokens_in_pool=None,
        pool4_cap_floor=None,
        pool4_floor_distance=None,
        pool4_floor_distance_pct=None,
        pool4_burned_supply_pct=None,
        pool4_total_supply=None,
        pool4_inventory_cap=None,
        pool4_cap_headroom=None,
        pool4_cap_decay_per_day=None,
        pool4_reserve_series=None,
        pool4_eth_in_pool=None,
        pool4_position_liquidity=None,
        pool4_current_tick=None,
        pool4_ref_tick=None,
        pool4_backstop_centred=None,
        pool4_as_of_hhmm=None,
        **_kwargs,
    ) -> None:
        """Refresh the panel. Full ``pool4_`` prefixes on every keyword --
        see ``SurfPool4Hatches.update_data`` for why the short alias is not
        reused here.
        """
        self._payload = {
            "network": pool4_network,
            "tokens_in_pool": pool4_tokens_in_pool,
            "cap_floor": pool4_cap_floor,
            "floor_distance": pool4_floor_distance,
            "floor_distance_pct": pool4_floor_distance_pct,
            "burned_supply_pct": pool4_burned_supply_pct,
            "total_supply": pool4_total_supply,
            "inventory_cap": pool4_inventory_cap,
            "cap_headroom": pool4_cap_headroom,
            "cap_decay_per_day": pool4_cap_decay_per_day,
            "series": pool4_reserve_series,
            "eth_in_pool": pool4_eth_in_pool,
            "position_liquidity": pool4_position_liquidity,
            "current_tick": pool4_current_tick,
            "ref_tick": pool4_ref_tick,
            "backstop_centred": pool4_backstop_centred,
            "as_of": pool4_as_of_hhmm,
            "seen": True,
        }
        self._render_view()

    def _text_budget(self) -> int:
        return max(self.size.width - self._TITLE_PADDING_COLS, 0)

    def _title_text(self) -> str:
        """``THE RATCHET · SEPOLIA``, with the widen marker appended when the
        panel had to shed a column -- see ``_pool4.title_text``.
        """
        return title_text(
            TITLE, self._payload.get("network"), self._widen, self._text_budget()
        )

    def _is_blank(self) -> bool:
        """True only when every scalar this panel renders is unread. A single
        reverting getter is one dash inside an otherwise healthy panel, never
        a dead one (the field-by-field degradation the unverified hook needs).
        """
        payload = self._payload
        if any(payload.get(k) is not None for k in self._SCALAR_KEYS):
            return False
        return not coerce_points(payload.get("series"))

    def _content_lines(self, tier: str) -> list[Text]:
        p = self._payload
        full = tier == "full"
        markup: list[str] = []

        # Ceiling, reserve, floor -- in that order, because that is the
        # mechanism: the reserve sits between a decaying cap above it and an
        # owner-settable floor below it, and reading them top-to-bottom is the
        # only arrangement in which "the cap is sitting on the inventory"
        # (true to within 12 wei on both chains today) is visible at a glance.
        cap = f"{_fmt_imd_compact(p.get('inventory_cap'))} IMD"
        if full:
            cap = f"{cap} [dim]· {_fmt_cap_decay(p.get('cap_decay_per_day'))}[/]"
        markup.append(_row("cap", cap))

        # BETWEEN its two operands, on purpose: the contract requires the
        # subtraction be checkable against the numbers the reader is shown,
        # and `cap` is the line above while `reserve` is the line below.
        #
        # Labelled `headroom`, never `vs cap`. `vs floor` one row down is
        # `reserve - floor`; `vs cap` would read as `reserve - cap` by
        # analogy, which is the **inverted** operand order and renders a
        # binding cap as slack. Both are positive when healthy, so the
        # inversion does not announce itself -- the word `headroom` means
        # "room left under the ceiling" and can only be `cap - reserve`.
        markup.append(
            _row("headroom", f"{_fmt_signed_imd(p.get('cap_headroom'))} IMD")
        )

        reserve = f"{_fmt_imd_compact(p.get('tokens_in_pool'))} IMD"
        spark = _reserve_spark(p.get("series")) if full else ""
        if spark:
            reserve = f"{reserve} [dim]{spark}[/]"
        markup.append(_row("reserve", reserve))

        markup.append(
            _row(
                "floor",
                f"{_fmt_imd_compact(p.get('cap_floor'))} IMD "
                f"[dim]({FLOOR_WORD})[/]",
            )
        )
        markup.append(
            _row(
                "vs floor",
                f"{_fmt_signed_imd(p.get('floor_distance'))} IMD "
                f"[dim]·[/] {_fmt_signed_pct(p.get('floor_distance_pct'))}",
            )
        )

        burned = f"{_fmt_pct(p.get('burned_supply_pct'))} of supply"
        if full:
            burned = (
                f"{_fmt_pct(p.get('burned_supply_pct'))} of "
                f"{_fmt_imd_compact(p.get('total_supply'))} IMD"
            )
        markup.append(_row("burned", burned))

        pool = f"{_fmt_eth(p.get('eth_in_pool'))} ETH"
        if full:
            pool = (
                f"{pool} [dim]· L {fmt_liquidity(p.get('position_liquidity'))}[/]"
            )
        markup.append(_row("pool", pool))

        # The backstop word rides on the tick row rather than taking one of
        # its own. Not only for the row -- though the row is why it was looked
        # at -- but because "is the backstop centred" is a statement *about*
        # these two ticks, and it now sits beside both of the numbers a reader
        # would check it against. Same principle as `headroom` between its own
        # operands six lines above.
        #
        # The tri-state vocabulary is unchanged: `centred` / `drifted` /
        # `unknown`, three words sharing no three-character run, so a scanned
        # row still cannot read an indeterminate answer as a confident one.
        tick = _fmt_tick(p.get("current_tick"))
        if full:
            tick = f"{tick} [dim]· ref {_fmt_tick(p.get('ref_tick'))}[/]"
        tick = f"{tick} [dim]·[/] {_backstop_word(p.get('backstop_centred'))}"
        markup.append(_row("tick", tick))

        as_of = p.get("as_of")
        if as_of:
            markup.append(f"[dim]as of {safe_markup(strip_tags(as_of))}[/]")

        return [t for t in (parse_line(m) for m in markup) if t is not None]

    def _render_view(self) -> None:
        try:
            body = self.query_one("#surf-pool4-ratchet-body", Static)
        except Exception:  # not composed yet
            return

        if not self._payload:
            self._widen = False
            body.update(Text(self._title_text(), style="dim"))
            return

        if self._is_blank():
            self._widen = False
            body.update(
                join_lines(
                    [
                        Text(self._title_text(), style="dim"),
                        Text(""),
                        Text(f"⚠ {UNAVAILABLE_LINE}", style="yellow"),
                    ]
                )
            )
            return

        # Measure what was actually built, never `budget < FULL_WIDTH` -- see
        # `SurfPool4Hatches._render_view` for the reasoning; the reserve line
        # here is data-dependent in exactly the way that argument describes.
        budget = self._text_budget()
        content = self._content_lines("full")
        if budget and widest_line(content) > budget:
            self._widen = True
            content = self._content_lines("compact")
        else:
            self._widen = False

        # No blank row under the title. It was there on ``SurfBurnPipeline``'s
        # precedent -- "the rail's panels sat flush against their own headings
        # and read as one block of text" -- and that argument holds for a panel
        # whose body is prose. This one's body is a label/value grid in a dim-
        # labelled column, which already separates itself from a dim title, so
        # the row was buying less here than it costs: the pool4 body's height
        # pin is the tallest requirement in the repo and W7 records that nobody
        # has ever measured whether a real laptop clears it.
        body.update(
            join_lines([Text(self._title_text(), style="dim"), *content])
        )
