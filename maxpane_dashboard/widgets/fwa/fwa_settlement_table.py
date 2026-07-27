"""Settlement outcome mix + crown history for the FWA dashboard.

Two stacked sections in one ``DataTable``:

1. **Outcome mix** -- what purchasers actually do with the NFT they drew::

       accept bid, paid in $FWA   73.92%
       accept bid, paid in ETH    13.84%
       relist                      7.64%
       keep the NFT                4.60%
       force-finalized             0.00%

   ~88% sell straight back and almost nobody keeps the art. That is the most
   revealing statistic in the protocol, so the widget states it in words above
   the table rather than leaving it to be inferred from five percentages. The
   sell-back share is **computed from the rows**, never hardcoded.

2. **Crown history** -- a *per-holder* aggregation (``rank``, ``holder``,
   ``reigns``, ``payout_eth``, ``last_block``, ``last_ts``), not one row per
   event: the ``TopListingSettled`` vacate+set pairs are deduped upstream. One
   wallet currently holds 4 reigns. A summary row carries the totals
   (33 sets, 12 payouts, 91.096 ETH).

Both sections are log-derived, so both share one staleness header
(``as of HH:MM``) and one explicit unavailable state -- mandatory per PRD §9,
not polish.

The five shares sum to 100 only after rounding; the total row renders the
computed sum to two decimals and asserts nothing.

Primitives only -- this module imports nothing from ``fwa_models``.
"""

from __future__ import annotations

import re
import time

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Static
from maxpane_dashboard.widgets.markup_safety import safe_markup

_DASH = "--"
_EMDASH = "—"

#: Crown holders rendered; the tail is summarised by the totals row.
_MAX_CROWN_ROWS = 5

#: The explicit degraded text. Tested verbatim.
UNAVAILABLE_TEXT = "logs unavailable"

#: Outcomes that mean "sold straight back", for the headline share.
_SELLBACK_OUTCOMES = ("bid_fwa", "bid_eth")

#: Strips Textual markup so a line can be measured as the user sees it.
_MARKUP = re.compile(r"\[/?[^\[\]]*\]")

#: Short wordings used when the payload's own label does not fit the column.
#: ``accept bid · $FWA`` cut to 16 gives ``accept bid · $FW``, which reads as a
#: different token; the abbreviation says the same thing in fewer columns.
_OUTCOME_SHORT = {
    "bid_fwa": "bid · $FWA",
    "bid_eth": "bid · ETH",
    "relist": "relist",
    "kept": "keep NFT",
    "forced": "forced",
}


def _fit_label(label: str, outcome: str, width: int) -> str:
    """``label`` inside ``width`` columns, abbreviated rather than cut."""
    if len(label) <= width:
        return label
    short = _OUTCOME_SHORT.get(outcome)
    if short and len(short) <= width:
        return short
    return label[: max(width - 1, 1)] + "…"

#: Column layouts, widest first: ``(name, cost, columns, hint)`` where a
#: column is ``(key, header, width)`` and ``cost`` is ``sum(width) + 2`` per
#: column (DataTable pads each cell by one column on each side).
#:
#: =========  ====  ==================================
#: Tier       Cost  Columns
#: =========  ====  ==================================
#: full        55   OUTCOME/HOLDER COUNT SHARE ETH
#: compact     43   OUTCOME/HOLDER SHARE ETH
#: minimal     37   OUTCOME SHARE ETH   (narrower cells)
#: tiny        25   OUTCOME SHARE
#: =========  ====  ==================================
#:
#: The slot is 56 columns at a 200-column terminal and 38 at 140. ``SHARE`` is
#: never dropped: the outcome mix *is* the share column. ``COUNT`` goes first
#: because the share already carries the shape of the distribution.
_TIERS: tuple[tuple[str, int, tuple[tuple[str, str, int], ...], str], ...] = (
    (
        "full",
        55,
        (
            ("label", "OUTCOME / HOLDER", 22),
            ("count", "COUNT", 8),
            ("share", "SHARE", 8),
            ("eth", "ETH", 9),
        ),
        "",
    ),
    (
        "compact",
        43,
        (
            ("label", "OUTCOME / HOLDER", 21),
            ("share", "SHARE", 8),
            ("eth", "ETH", 8),
        ),
        "‹ widen: COUNT",
    ),
    (
        "minimal",
        37,
        (
            ("label", "OUTCOME", 16),
            ("share", "SHARE", 7),
            ("eth", "ETH", 8),
        ),
        "‹ widen: COUNT",
    ),
    (
        "tiny",
        25,
        (
            ("label", "OUTCOME", 14),
            ("share", "SHARE", 7),
        ),
        "‹ widen: COUNT + ETH",
    ),
)


def _tier_for(width: int) -> tuple[str, tuple[tuple[str, str, int], ...], str]:
    """``(name, columns, hint)`` -- the widest layout that fits ``width``."""
    for name, cost, columns, hint in _TIERS:
        if width <= 0 or width >= cost:
            return name, columns, hint
    name, _cost, columns, hint = _TIERS[-1]
    return name, columns, hint


def _cells(values: dict, columns: tuple, default: str = _DASH) -> list:
    """Project ``values`` onto the active columns."""
    return [values.get(key, default) for key, _header, _width in columns]


def _has(columns: tuple, key: str) -> bool:
    return any(col_key == key for col_key, _header, _width in columns)


def _width_of(columns: tuple, key: str, fallback: int) -> int:
    for col_key, _header, width in columns:
        if col_key == key:
            return width
    return fallback


def _grow_label(columns: tuple, width: int, cap: int = 30) -> tuple:
    """Spend leftover columns on the label, which is the one that truncates.

    A tier is chosen by the widest layout that *fits*, so there is usually
    slack between the layout's cost and the real width. Handing it to the
    outcome/holder column is what turns ``accept bid · $FW`` back into
    ``accept bid · $FWA``.
    """
    if width <= 0:
        return columns
    spare = width - (sum(w for _k, _h, w in columns) + 2 * len(columns))
    if spare <= 0:
        return columns
    return tuple(
        (key, header, min(w + spare, cap) if key == "label" else w)
        for key, header, w in columns
    )


def _fmt_int(value) -> str:
    if value is None:
        return _DASH
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return _DASH


def _fmt_pct(value) -> str:
    if value is None:
        return _DASH
    try:
        return f"{float(value):.2f}%"
    except (TypeError, ValueError):
        return _DASH


def _fmt_eth(value) -> str:
    if value is None:
        return _DASH
    try:
        return f"{float(value):,.3f}"
    except (TypeError, ValueError):
        return _DASH


def _as_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _short_addr(value) -> str:
    if value is None:
        return _DASH
    s = str(value).strip()
    if not s:
        return _DASH
    if len(s) <= 14:
        return s
    return f"{s[:6]}..{s[-4:]}"


def _hhmm(timestamp) -> str:
    try:
        ts = int(timestamp or 0)
        if ts <= 0:
            return "??:??"
        t = time.localtime(ts)
        return f"{t.tm_hour:02d}:{t.tm_min:02d}"
    except (TypeError, ValueError, OSError, OverflowError):
        return "??:??"


def _visible_len(markup: str) -> int:
    """Length of ``markup`` as rendered, i.e. with the tags removed."""
    return len(_MARKUP.sub("", markup or ""))


def _headline(mix_rows: list, short: bool = False) -> str:
    """``87.76% sell straight back · 4.60% keep the NFT`` -- computed, not fixed.

    ``short=True`` drops the keep share for narrow slots.
    """
    sellback = 0.0
    kept = None
    seen = False
    for row in mix_rows:
        if not isinstance(row, dict):
            continue
        share = _as_float(row.get("share_pct"))
        if share is None:
            continue
        outcome = str(row.get("outcome") or "").strip().lower()
        if outcome in _SELLBACK_OUTCOMES:
            sellback += share
            seen = True
        elif outcome == "kept":
            kept = share
    if not seen:
        return ""
    if short:
        return f"[bold]{sellback:.2f}%[/] sold back"
    text = f"[bold]{sellback:.2f}%[/] sell straight back"
    if kept is not None:
        text += f" · [dim]{kept:.2f}% keep the NFT[/]"
    return text


class FWASettlementTable(Vertical):
    """Settlement outcome mix stacked above the crown history."""

    DEFAULT_CSS = """
    FWASettlementTable > .fwa-settle-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    FWASettlementTable > .fwa-settle-note {
        width: 100%;
        padding: 0 1;
    }
    FWASettlementTable > DataTable {
        height: 1fr;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._payload: dict = {}
        self._tier: tuple = ()

    def compose(self) -> ComposeResult:
        yield Static(
            "SETTLEMENT & CROWN",
            classes="fwa-settle-title",
            id="fwa-settle-title",
        )
        yield Static("", classes="fwa-settle-note", id="fwa-settle-note")
        yield DataTable(id="fwa-settle-dt", classes="fwa-settle-table")

    def on_mount(self) -> None:
        table = self.query_one("#fwa-settle-dt", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        columns = self._apply_columns(table)
        table.add_row(*_cells({"label": "Loading..."}, columns))

    def on_resize(self, _event=None) -> None:
        """Re-render: the column set is a function of the width."""
        if self._payload:
            self._render_view()

    # -- layout --------------------------------------------------------

    def _table_width(self, table: DataTable) -> int:
        width = table.content_size.width
        if width <= 0:
            width = self.content_size.width
        return width

    def _apply_columns(self, table: DataTable) -> tuple:
        """Install the column set for the current width; return it."""
        table_width = self._table_width(table)
        name, columns, hint = _tier_for(table_width)
        columns = _grow_label(columns, table_width)
        if columns != self._tier:
            table.clear(columns=True)
            for _key, header, width in columns:
                table.add_column(header, width=width)
            self._tier = columns
        else:
            table.clear()
        self._hint = hint
        return columns

    # -- helpers -------------------------------------------------------

    def _set_title(self, suffix: str = "") -> None:
        """Title, staleness and the widen marker -- inside the width we have.

        Priority when they do not all fit: the widen marker outranks the
        ``as of HH:MM`` stamp, because a hidden column is a correctness problem
        and the stamp has somewhere else to go (the note line, see
        :meth:`_note_text`). The title itself is never abbreviated -- WP-13's
        screen test looks for it, and so does a user scanning the row.
        """
        hint = getattr(self, "_hint", "")
        base = "SETTLEMENT & CROWN"
        width = max(self.content_size.width - 2, 0)

        used = len(base) + (2 + len(hint) if hint else 0)
        show_suffix = bool(suffix) and (
            not width or used + 2 + len(suffix) <= width
        )

        text = base
        if show_suffix:
            # Unstyled: `#fwa-settle-title` is already `$text-muted`, and
            # `[dim]` on top of that measured 3.71:1 under `fwa` (WP-19).
            text += f"  {suffix}"
        if hint:
            text += f"  [yellow]{hint}[/]"
        self.query_one("#fwa-settle-title", Static).update(text)
        self._title_suffix_shown = show_suffix

    def _set_note(self, text: str) -> None:
        self.query_one("#fwa-settle-note", Static).update(text)

    # -- rendering -----------------------------------------------------

    def update_data(
        self,
        settlement_mix=None,
        crown_history=None,
        crown_sets_total=None,
        crown_payouts_total=None,
        crown_paid_eth=None,
        settle_available=None,
        settle_as_of_ts=None,
        **_kwargs,
    ) -> None:
        """Refresh both sections.

        Every kwarg matches ``FWA_WIDGET_SIGNATURES["FWASettlementTable"]``. No
        args, all-``None`` and a full payload all render without raising.
        """
        try:
            mix_rows = [r for r in list(settlement_mix or []) if isinstance(r, dict)]
        except TypeError:
            mix_rows = []
        try:
            crown_rows = [r for r in list(crown_history or []) if isinstance(r, dict)]
        except TypeError:
            crown_rows = []

        has_data = bool(mix_rows or crown_rows)
        self._payload = {
            "mix": mix_rows,
            "crown": crown_rows,
            "sets_total": crown_sets_total,
            "payouts_total": crown_payouts_total,
            "paid_eth": crown_paid_eth,
            "available": (
                has_data if settle_available is None else bool(settle_available)
            ),
            "as_of": settle_as_of_ts,
        }
        self._render_view()

    def _render_view(self) -> None:
        try:
            table = self.query_one("#fwa-settle-dt", DataTable)
        except Exception:  # not composed yet
            return
        if not self._payload:
            return

        columns = self._apply_columns(table)
        mix_rows = self._payload["mix"]
        crown_rows = self._payload["crown"]
        as_of = self._payload["as_of"]

        if not self._payload["available"]:
            # Two different markup dialects on two adjacent lines, and they do
            # not accept the same tokens (WP-19):
            #
            #   * the note is a `Static`, i.e. Textual *Content* markup. Colour
            #     names there resolve through the CSS name table, where `red`
            #     is #ff0000 -- 3.25-4.72 across the ten themes, below AA in
            #     seven. `$error` is better but still 3.81-4.43 under matrix,
            #     minimal, bakery and frenpet. `$warning` is the one required
            #     Theme field clearing 4.5:1 under all ten (4.59-11.16).
            #   * the table cell is `DataTable`, i.e. *Rich* markup, which does
            #     not know `$`-variables at all -- `[$warning]` there raises
            #     MarkupError. Its `yellow` is the ANSI #fd971f (5.30-7.81
            #     across the ten), so the cell spells the colour and the note
            #     names the variable, and both land on a passing yellow.
            #
            # A dead source is a warning rather than an error anyway, which is
            # what FWAChaseBoard and FWAOddsBoard already use. The glyph and
            # the word carry the state; colour is redundant either way.
            self._set_title("· unavailable")
            self._set_note(
                f"[$warning]  ⚠ {UNAVAILABLE_TEXT} — settlement mix paused[/]"
            )
            table.add_row(
                *_cells({"label": f"[yellow]⚠ {UNAVAILABLE_TEXT}[/]"}, columns)
            )
            table.add_row(*_cells({"label": "[dim]crown history[/]"}, columns))
            return

        self._set_title(f"· as of {_hhmm(as_of)}" if as_of else "")
        self._set_note(self._note_text(mix_rows, as_of))

        if not (mix_rows or crown_rows):
            table.add_row(*_cells({"label": "[dim]No data[/]"}, columns))
            return

        self._render_mix(table, columns, mix_rows)
        self._render_crown(
            table,
            columns,
            crown_rows,
            self._payload["sets_total"],
            self._payload["payouts_total"],
            self._payload["paid_eth"],
        )

    def _note_text(self, mix_rows: list, as_of) -> str:
        """Headline stat, plus the staleness stamp when the title lost it.

        Both shrink together: the long form states the sell-back and keep
        shares, the short form keeps only the sell-back number, which is the
        one that reframes the protocol.
        """
        width = max(self.content_size.width - 2, 0)
        stamp = ""
        if as_of and not getattr(self, "_title_suffix_shown", True):
            stamp = f"as of {_hhmm(as_of)}"

        long_headline = _headline(mix_rows)
        parts = [p for p in (stamp, long_headline.strip()) if p]
        if not parts:
            return ""
        long_text = "  " + " · ".join(parts)
        if not width or _visible_len(long_text) <= width:
            return long_text

        short = _headline(mix_rows, short=True).strip()
        parts = [p for p in (stamp, short) if p]
        return "  " + " · ".join(parts)

    def _crown_rows_shown(self, table: DataTable, wanted: int) -> int:
        """How many holder rows fit under the mix without pushing TOTAL out.

        The crown TOTAL row carries the only sets/payouts/ETH figures there
        are; losing it to a scroll would be losing data, so the holder list is
        capped to whatever is left instead.
        """
        wanted = min(wanted, _MAX_CROWN_ROWS)
        height = table.content_size.height
        if height <= 0:
            return wanted
        mix_count = len(self._payload.get("mix") or [])
        # column header + mix rows + mix TOTAL + blank + crown header + TOTAL
        overhead = 1 + mix_count + (1 if mix_count else 0) + 3
        return max(min(wanted, height - overhead), 1 if wanted else 0)

    def _render_mix(self, table: DataTable, columns: tuple, mix_rows: list) -> None:
        label_width = _width_of(columns, "label", 22)
        total_count = 0
        total_share = 0.0
        any_share = False

        for row in mix_rows:
            label = str(row.get("label") or row.get("outcome") or _DASH)
            count = row.get("count")
            share = _as_float(row.get("share_pct"))
            if isinstance(count, int):
                total_count += count
            if share is not None:
                total_share += share
                any_share = True
            outcome = str(row.get("outcome") or "").strip().lower()
            table.add_row(
                *_cells(
                    {
                        "label": safe_markup(_fit_label(label, outcome, label_width)),
                        "count": _fmt_int(count),
                        "share": _fmt_pct(share),
                        "eth": _EMDASH,
                    },
                    columns,
                )
            )

        if mix_rows:
            table.add_row(
                *_cells(
                    {
                        "label": "[bold]TOTAL[/]",
                        "count": f"[bold]{_fmt_int(total_count)}[/]",
                        "share": (
                            f"[bold]{_fmt_pct(total_share) if any_share else _DASH}[/]"
                        ),
                        "eth": _EMDASH,
                    },
                    columns,
                )
            )

    def _render_crown(
        self,
        table: DataTable,
        columns: tuple,
        crown_rows: list,
        sets_total,
        payouts_total,
        paid_eth,
    ) -> None:
        has_count = _has(columns, "count")
        has_eth = _has(columns, "eth")
        # Reigns live in COUNT when it exists and in SHARE when it does not --
        # SHARE is meaningless for a crown row, so nothing is displaced.
        reign_key = "count" if has_count else "share"

        # Vertical budget: the crown section shares one table with the five
        # outcome rows and both TOTAL rows, so the holder list -- not the
        # totals -- is what yields when the box is short. A shortened list says
        # so in its header rather than just ending.
        shown = self._crown_rows_shown(table, len(crown_rows))
        label_width = _width_of(columns, "label", 22)
        header = "CROWN HISTORY"
        if 0 < shown < len(crown_rows):
            # The "top N" qualifier is what makes the short list honest, so it
            # is fitted to the column rather than allowed to clip.
            for candidate in (
                f"CROWN HISTORY (top {shown})",
                f"CROWN · top {shown}",
                f"CROWN top {shown}",
            ):
                if len(candidate) <= label_width:
                    header = candidate
                    break
            else:
                header = f"CROWN {shown}"

        table.add_row(*_cells({}, columns, default=""))
        table.add_row(
            *_cells(
                {
                    "label": f"[bold]{header}[/]",
                    reign_key: "[dim]REIGNS[/]",
                    "eth": "[dim]PAID[/]",
                },
                columns,
                default="",
            )
        )

        if not crown_rows:
            table.add_row(*_cells({"label": "[dim]no reigns recorded[/]"}, columns))
        for idx, row in enumerate(crown_rows[:shown], start=1):
            rank = row.get("rank", idx)
            table.add_row(
                *_cells(
                    {
                        "label": f"{rank}. {_short_addr(row.get('holder'))}",
                        reign_key: _fmt_int(row.get("reigns")),
                        "eth": _fmt_eth(row.get("payout_eth")),
                    },
                    columns,
                    default=_EMDASH,
                )
            )

        if sets_total is None and payouts_total is None and paid_eth is None:
            return

        sets_str = f"{_fmt_int(sets_total)} sets" if sets_total is not None else _EMDASH
        payouts_str = (
            f"{_fmt_int(payouts_total)} paid" if payouts_total is not None else _EMDASH
        )
        if has_count:
            totals = {
                "label": "[bold]TOTAL[/]",
                "count": f"[bold]{sets_str}[/]",
                "share": f"[bold]{payouts_str}[/]",
                "eth": f"[bold]{_fmt_eth(paid_eth)}[/]",
            }
        else:
            # No COUNT column: fold the set total into the label so all three
            # crown numbers survive.
            totals = {
                "label": f"[bold]TOTAL {sets_str}[/]",
                "share": f"[bold]{payouts_str}[/]",
                "eth": f"[bold]{_fmt_eth(paid_eth)}[/]",
            }
        if not has_eth:
            totals["share"] = f"[bold]{sets_str}[/]"
            totals["label"] = f"[bold]TOTAL {payouts_str}[/]"
        table.add_row(*_cells(totals, columns, default=_EMDASH))
