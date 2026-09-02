"""POOL4 rail: sIMD VAULT -- the staking vault and the dripper that feeds it.

**What this panel's percentage is, and what it is not.** The protocol's own
docs (§06) are explicit about which number is the yield:

    "The APR on the stake page is trailing and real: the IMD the market *set
    aside for stakers* over the last seven days ... annualised against total
    staked. **The dripper's rate is only a cap on how fast that reaches the
    vault.**"

So the entitlement is the **flow** -- 4.5% of every retired batch -- and the
drip is a **delivery cap** on how fast that flow arrives. This panel computes
``drip_per_day x 365 / TVL``, which is neither: it is the delivery cap
annualised. Against a deep backlog it *understates* what stakers have already
earned (Sepolia's was a year deep); against an empty one it *overstates*,
because nothing can be dripped that has not arrived.

It is therefore **never called APR** -- :data:`DELIVERY_LABEL` and
:data:`DELIVERY_NOTE` name it for what it is, and
:data:`DELIVERY_NOT_APR_NOTE` says on screen that it is not the staker APR.
Publishing our number under the same word as a site that computes a different
one is the whole defect: the label was honest ("drip rate / TVL") while the
heading it sat under was not.

An earlier version of this docstring opened by asserting the vault's yield is
"rate-limited, not flow-limited". That was a reasonable reading of the
mechanism and it is not what the protocol says the number means -- the flow is
the entitlement and the rate is the cap on its delivery. The sentence is
recorded here rather than quietly deleted because the panel was built around
it, and a reader comparing this file to its history should find the correction
rather than a silent reversal.

What survives that correction, because it is about *delivery* rather than
about yield, and none of it may be dropped for width alone:

* ``drip`` always carries its unit as a **rate** -- ``IMD/day``, never a bare
  balance;
* ``queue`` always names ``pool4_backlog_days`` as **days of runway**, not as
  a number beside a balance;
* at the full tier a plain-language line says what the rate governs
  (:data:`RATE_LIMITED_NOTE`).

A raw balance alone would be a review failure, so the compact tier splits the
queue onto two lines rather than shedding the runway phrase.

``pool4_implied_apr_pct`` keeps its contract spelling -- the key is WP0's and
this panel does not get to rename it -- but nothing rendered from it says
"APR". ``None`` (TVL zero or unread) renders :data:`DELIVERY_SUPPRESSED`,
**never** ``0%`` and never ``INF``: a zero would claim stakers earn nothing and
an infinity would claim a division nobody performed.

``pool4_can_drip`` is a tri-state and renders three distinct words -- see
:func:`_drip_word`.

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
from maxpane_dashboard.widgets.sparkline_common import fmt_compact
from maxpane_dashboard.widgets.surf._fmt import DASH, as_float
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
    "DELIVERY_LABEL",
    "DELIVERY_NOTE",
    "DELIVERY_NOT_APR_NOTE",
    "DELIVERY_SUPPRESSED",
    "COMPACT_WIDTH",
    "FULL_WIDTH",
    "GLYPH_HINT",
    "NO_BASELINE",
    "RATE_LIMITED_NOTE",
    "RUNWAY_WORD",
    "SurfPool4Vault",
    "TITLE",
    "UNAVAILABLE_LINE",
    "WIDEN_HINT",
]

TITLE = "sIMD VAULT"
UNAVAILABLE_LINE = "vault unavailable"

#: The phrase ``pool4_backlog_days`` is rendered as, at **every** tier. The
#: number alone is meaningless beside a balance; "days of runway" is the
#: statement -- the queue divided by a fixed release rate.
RUNWAY_WORD = "days of runway"

#: The full-tier plain-language statement of the mechanism. Shed only at the
#: compact tier, and only because ``IMD/day`` and :data:`RUNWAY_WORD` still
#: carry it there.
#: 37 cells, and that ceiling is load-bearing: this panel shares the rail with
#: ``SurfPool4Hatches`` (49 including its column's gutter) and its own
#: :data:`FULL_WIDTH` is 38, so a note of 47 would have taken the rail's need
#: to 51 and the body's width pin past 106. Shorten the value, never the pin.
RATE_LIMITED_NOTE = "drip rate caps delivery, not earnings"

#: What the APR line says when ``pool4_implied_apr_pct is None`` -- i.e. TVL
#: is zero or unread. Not ``0%`` (a claim stakers earn nothing) and not ``∞``
#: (a claim about a division nobody performed).
DELIVERY_SUPPRESSED = "not computable"

#: The row label. **Not** ``apr``: the protocol publishes a differently
#: computed APR under that word (trailing seven-day flow annualised against
#: total staked), and two different numbers sharing one heading is how a
#: reader concludes one of the two sites is lying.
DELIVERY_LABEL = "deliv"

#: Said on screen at the full tier, so the distinction survives without the
#: reader having to know the mechanism.
#:
#: **It rides on the number's own line rather than taking one of its own**, and
#: that is a correctness fix, not a saving. As a standalone line it made this
#: panel eleven rows against the rail's ``min-height: 10`` -- and VAULT carries
#: the rail's ``1fr`` precisely *because* its line count was a constant ten, so
#: that floor is also its ceiling. A ``1fr`` child cannot overflow; it shrinks.
#: The eleventh line was dropped with no scrollbar, no ``‹ taller`` and no
#: trace, while the rail's ``virtual_size`` went on reporting ten.
#:
#: That is CLAUDE.md's ``1fr`` rule biting in the direction it does not spell
#: out: the rule warns about a ``1fr`` child with *no* floor shedding down to a
#: bare title. Here the floor existed and was one row too low, so exactly one
#: line vanished and everything else looked right.
#:
#: Short on purpose. ``"delivery cap, not the staker APR"`` on the same line
#: makes it 49 cells against this panel's :data:`FULL_WIDTH` of 38, which would
#: take the rail's need past ``SurfPool4Hatches``' 49 and the body's width pin
#: past 106. Shorten the value, not the pin -- and the label ``deliv`` plus
#: :data:`DELIVERY_NOTE` already carry the positive half of the statement.
DELIVERY_NOT_APR_NOTE = "not APR"

#: Where the APR comes from, said on the line itself so it is never mistaken
#: for a realised or fee-derived yield.
DELIVERY_NOTE = "drip rate ÷ TVL"

#: ``pool4_share_price_delta_pct is None`` means *no second reading yet*, not
#: *the read failed* and certainly not *zero change*. It gets its own words
#: rather than :data:`~._fmt.DASH` for the same reason ``not-discovered`` and
#: "discovery has not run" get different words in ``pool4_hatches``.
NO_BASELINE = "no baseline"

_LABEL_COLS = 5      # widest labels: "share", "queue"
_GAP = 1

#: Widest full-tier line: the queue and its runway.
#: ``5 + 1 + len("250.0K IMD · 20.0 days of runway")``. Pinned against
#: composited output by ``test_the_vault_full_width_pin_is_the_widest_full_
#: tier_line``, which compares with ``==`` and reddens in both directions.
#: Data-dependent (a nine-figure queue is wider than a six-figure one), which
#: is why the runtime tier decision measures the lines it actually built --
#: see :meth:`SurfPool4Vault._render_view`.
FULL_WIDTH = _LABEL_COLS + _GAP + 32                                     # 38

#: One tier below full: the sIMD share count, the APR's provenance note, the
#: drippable amount and :data:`RATE_LIMITED_NOTE` all go, the share price
#: loses its unit, and the queue splits onto two lines so
#: :data:`RUNWAY_WORD` survives. ``5 + 1 + len("20.0 days of runway")``.
COMPACT_WIDTH = _LABEL_COLS + _GAP + 19                                  # 25


def _drip_word(can_drip: object) -> str:
    """``ready`` / ``not yet`` / ``unknown`` for ``pool4_can_drip``.

    ``SurfBurnPipeline._ready_word``'s vocabulary, reused verbatim because it
    is the same question about the same kind of permissionless call, and
    because it already satisfies the rule that matters: the ``None`` word
    shares **no substring** with either confident answer. ``NOT READY``
    contains ``READY`` and reads as the positive answer when a row is scanned
    rather than read; ``not yet`` cannot.

    ``None`` must never render as ready and never as a confident negative --
    the tri-state sibling of "a failed read is None, never 0".
    """
    if can_drip is True:
        return "[bold green]ready[/]"
    if can_drip is False:
        return "[bold]not yet[/]"
    return "[dim]unknown[/]"


def _fmt_amount(value: object) -> str:
    """A vault-scale IMD/sIMD quantity: ``250.0K``, ``1.2M``, ``--``."""
    v = as_float(value)
    return DASH if v is None else fmt_compact(v)


def _fmt_share_price(value: object) -> str:
    """Six decimals: this number sits just above 1.0 and moves in the fifth
    decimal between drips, so a two-decimal rendering would show a frozen
    ``1.04`` through every reading of a live vault.
    """
    v = as_float(value)
    return DASH if v is None else f"{v:,.6f}"


def _fmt_signed_pct(value: object) -> str:
    v = as_float(value)
    return DASH if v is None else f"{v:+,.2f}%"


def _fmt_days(value: object) -> str:
    """Runway in days. ``--`` covers both "the drip rate is zero" and "we
    could not look" -- the contract makes ``pool4_backlog_days`` ``None`` for
    either, and this panel must never print an infinity for the first.
    """
    v = as_float(value)
    if v is None:
        return DASH
    return f"{v:,.0f}" if abs(v) >= 100 else f"{v:,.1f}"


def _row(label: str, value: str) -> str:
    """One ``label value`` line; the label is a module literal, so only the
    value can carry third-party bytes and only the value is escaped.
    """
    return f"[dim]{label:<{_LABEL_COLS}}[/]{' ' * _GAP}{value}"


class SurfPool4Vault(Vertical):
    """The staking vault, and the dripper that rate-limits what reaches it.

    Read-only (CLAUDE.md hard constraint 1 -- no signer, no transactor, no
    calldata construction anywhere in this repo): this panel *displays* that
    ``drip()`` is callable; it never offers to call it and never builds
    calldata.
    """

    DEFAULT_CSS = """
    SurfPool4Vault {
        height: auto;
    }
    SurfPool4Vault > Static {
        width: 100%;
        padding: 0 1;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    """

    #: See ``SurfPool4Hatches._TITLE_PADDING_COLS``.
    _TITLE_PADDING_COLS = 2

    _SCALAR_KEYS = (
        "share_price", "share_price_delta_pct", "vault_assets", "vault_shares",
        "drip_per_day", "drippable", "can_drip", "backlog_imd", "backlog_days",
        "implied_apr_pct",
    )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._payload: dict = {}
        self._widen = False

    def compose(self) -> ComposeResult:
        yield Static(TITLE, id="surf-pool4-vault-body")

    def on_resize(self, _event=None) -> None:
        if self._payload:
            self._render_view()

    def update_data(
        self,
        pool4_network=None,
        pool4_share_price=None,
        pool4_share_price_delta_pct=None,
        pool4_vault_assets=None,
        pool4_vault_shares=None,
        pool4_drip_per_day=None,
        pool4_drippable=None,
        pool4_can_drip=None,
        pool4_backlog_imd=None,
        pool4_backlog_days=None,
        pool4_implied_apr_pct=None,
        pool4_as_of_hhmm=None,
        **_kwargs,
    ) -> None:
        """Refresh the panel. Full ``pool4_`` prefixes on every keyword --
        see ``SurfPool4Hatches.update_data`` for why the short alias is not
        reused here.
        """
        self._payload = {
            "network": pool4_network,
            "share_price": pool4_share_price,
            "share_price_delta_pct": pool4_share_price_delta_pct,
            "vault_assets": pool4_vault_assets,
            "vault_shares": pool4_vault_shares,
            "drip_per_day": pool4_drip_per_day,
            "drippable": pool4_drippable,
            "can_drip": pool4_can_drip,
            "backlog_imd": pool4_backlog_imd,
            "backlog_days": pool4_backlog_days,
            "implied_apr_pct": pool4_implied_apr_pct,
            "as_of": pool4_as_of_hhmm,
            "seen": True,
        }
        self._render_view()

    def _text_budget(self) -> int:
        return max(self.size.width - self._TITLE_PADDING_COLS, 0)

    def _title_text(self) -> str:
        """``sIMD VAULT · SEPOLIA``, with the widen marker appended when the
        panel had to shed a column -- see ``_pool4.title_text``.
        """
        return title_text(
            TITLE, self._payload.get("network"), self._widen, self._text_budget()
        )

    def _is_blank(self) -> bool:
        """True only when every scalar this panel renders is unread -- a
        single reverting getter is one dash inside a healthy panel.
        """
        return all(self._payload.get(k) is None for k in self._SCALAR_KEYS)

    def _content_lines(self, tier: str) -> list[Text]:
        p = self._payload
        full = tier == "full"
        markup: list[str] = []

        delta = p.get("share_price_delta_pct")
        delta_cell = (
            _fmt_signed_pct(delta)
            if as_float(delta) is not None
            else f"[dim]{NO_BASELINE}[/]"
        )
        price = _fmt_share_price(p.get("share_price"))
        if full:
            price = f"{price} IMD/sIMD"
        markup.append(_row("share", f"{price} [dim]·[/] {delta_cell}"))

        tvl = f"{_fmt_amount(p.get('vault_assets'))} IMD"
        if full:
            tvl = f"{tvl} [dim]· {_fmt_amount(p.get('vault_shares'))} sIMD[/]"
        markup.append(_row("TVL", tvl))

        # Always a *rate*, never a bare balance: this is half of what makes
        # the queue below legible as runway rather than as a pile of money.
        markup.append(
            _row("drip", f"{_fmt_amount(p.get('drip_per_day'))} IMD/day")
        )

        # `implied_apr_pct` is the contract's spelling of the key; nothing
        # rendered from it says "APR". See the module docstring.
        rate = as_float(p.get("implied_apr_pct"))
        if rate is None:
            markup.append(_row(DELIVERY_LABEL, f"[dim]{DELIVERY_SUPPRESSED}[/]"))
        elif full:
            markup.append(
                _row(
                    DELIVERY_LABEL,
                    f"{rate:,.2f}% [dim]· {DELIVERY_NOTE}, "
                    f"{DELIVERY_NOT_APR_NOTE}[/]",
                )
            )
        else:
            markup.append(_row(DELIVERY_LABEL, f"{rate:,.2f}%"))

        queue = f"{_fmt_amount(p.get('backlog_imd'))} IMD"
        runway = f"{_fmt_days(p.get('backlog_days'))} {RUNWAY_WORD}"
        if full:
            markup.append(_row("queue", f"{queue} [dim]·[/] {runway}"))
        else:
            # Split rather than shed: the runway phrase is the point of the
            # line and never goes for width alone.
            markup.append(_row("queue", queue))
            markup.append(f"{' ' * (_LABEL_COLS + _GAP)}{runway}")

        drip_cell = _drip_word(p.get("can_drip"))
        if full:
            drip_cell = (
                f"{drip_cell} [dim]· {_fmt_amount(p.get('drippable'))} "
                f"IMD drippable[/]"
            )
        markup.append(_row("next", drip_cell))

        if full:
            markup.append(f"[dim]{RATE_LIMITED_NOTE}[/]")

        as_of = p.get("as_of")
        if as_of:
            markup.append(f"[dim]as of {safe_markup(strip_tags(as_of))}[/]")

        return [t for t in (parse_line(m) for m in markup) if t is not None]

    def _render_view(self) -> None:
        try:
            body = self.query_one("#surf-pool4-vault-body", Static)
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

        # Measure what was actually built -- see `SurfPool4Hatches.
        # _render_view` for why a `budget < FULL_WIDTH` marker would go dark
        # on exactly the payloads that need it.
        budget = self._text_budget()
        content = self._content_lines("full")
        if budget and widest_line(content) > budget:
            self._widen = True
            content = self._content_lines("compact")
        else:
            self._widen = False

        # No blank row under the title, matching RATCHET and HATCHES. It was
        # `SurfBurnPipeline`'s heading-room idiom, which earns its row for a
        # panel whose body is prose; this body is a dim-labelled label/value
        # grid that already separates itself from a dim title. Removing it
        # leaves this panel at nine rows against the rail's `min-height: 10`,
        # so the next line added here fails a test instead of vanishing.
        body.update(
            join_lines([Text(self._title_text(), style="dim"), *content])
        )
