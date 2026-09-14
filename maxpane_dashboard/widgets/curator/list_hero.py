"""Record summary hero shown only above THE LIST's ``l`` view."""

from __future__ import annotations

from rich.cells import cell_len
from rich.style import Style
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from maxpane_dashboard.widgets.address import address_text
from maxpane_dashboard.widgets.curator._fmt import (
    DASH,
    fmt_eth,
    fmt_eth_compact,
    fmt_points,
)
from maxpane_dashboard.widgets.curator.hero import (
    LIST_EXPORT_SUBTITLE,
    LIST_EXPORT_SUBTITLE_SHORT,
    LIST_EXPORT_SUBTITLE_TINY,
    WIDEN_HINT,
)
from maxpane_dashboard.widgets.markup_safety import visible_len

#: ``$success``/``$success-darken-2``, with a plain Rich colour as the
#: last-resort fallback (the ``surf/pool4u_hero`` "$ trap": Rich's own
#: ``Text``/``Style`` cannot resolve a ``$``-prefixed theme token the way
#: Textual's ``Content.from_markup`` can -- and the wallet box now builds a
#: single ``Text`` for all five lines rather than handing ``Static`` a
#: markup string, because the address line's copy icon lives in a
#: ``Style(meta=...)`` span that only survives outside markup parsing).
#: Used only by the wallet card's :func:`_wallet_text`.
_TOKEN_FALLBACK = {"success": "green", "success-darken-2": "green"}

FULL_WIDTH = 42
COMPACT_WIDTH = 28

FILTER_EDITOR_NOTE = (
    "set ranges or options below · selected patterns and NFT collections "
    "match any"
)

_BOX_IDS = (
    "curator-list-hero-summary",
    "curator-list-hero-wallet",
    "curator-list-hero-filter",
)


def _tier_for(width: int) -> str:
    if width <= 0 or width >= FULL_WIDTH:
        return "full"
    if width >= COMPACT_WIDTH:
        return "compact"
    return "minimal"


def _lines(title: str, *body: str, title_style: str = "dim") -> list[str]:
    rows = list(body[:4]) + [""] * (4 - len(body[:4]))
    return [f"[{title_style}]{title}[/]", *rows]


def _count(value, noun: str) -> str:
    if not isinstance(value, int) or isinstance(value, bool):
        return f"{DASH} {noun}"
    return f"{value:,} {noun}"


def _list_label(view: str) -> str:
    if view == "cleaned":
        return "[$success]list CLEANED[/]"
    if view == "filtered":
        return "[$success]list FILTERED[/]"
    return "[bold]list FROZEN[/]"


def _raw_summary_lines(data: dict, tier: str, _width: int = 0) -> list[str]:
    wallets = _count(data.get("contributors_total"), "wallets")
    deposits = data.get("deposits_total")
    if (
        tier != "minimal"
        and isinstance(deposits, int)
        and not isinstance(deposits, bool)
    ):
        wallets = f"{wallets} · {deposits:,} tx"
    volume = fmt_eth_compact(data.get("volume_routed_eth"))
    return _lines(
        "THE LIST",
        f"[bold]{wallets}[/]",
        f"{volume} ETH",
        "[dim]routed (all refunded)[/]",
        _list_label("raw"),
    )


#: Shown when no wallet is configured -- the address line's non-address
#: fallback, so the icon's absence there is the correct behaviour rather
#: than a bug (``address_text`` only attaches one to a value that passes
#: :func:`~maxpane_dashboard.widgets.address.is_address`).
WALLET_NOT_SET = "WALLET NOT SET"


def _wallet_title(data: dict) -> str:
    """The verified ENS name, or ``YOUR WALLET``.

    Returned raw, unescaped: the caller builds a literal ``Text`` from it
    (never parsed as markup), so an attacker-chosen name with brackets in it
    (PRD §13 A9) renders as those literal characters rather than needing
    :func:`~maxpane_dashboard.widgets.markup_safety.safe_markup` to keep
    Rich from reading them as tags.
    """
    ens = data.get("you_ens")
    if not isinstance(ens, str) or not ens.strip():
        return "YOUR WALLET"
    return " ".join(ens.split())


def _rank(value) -> str:
    if not isinstance(value, int) or isinstance(value, bool):
        return DASH
    return f"#{value:,}"


def _total(value) -> str:
    if not isinstance(value, int) or isinstance(value, bool):
        return DASH
    return f"{value:,}"


def _join_detail(data: dict) -> str:
    join = data.get("you_first_index")
    hour = data.get("you_first_hour")
    details = []
    if isinstance(join, int) and not isinstance(join, bool):
        details.append(f"join #{join:,}")
    if isinstance(hour, int) and not isinstance(hour, bool):
        details.append(f"hour {hour:,}")
    return " · ".join(details) if details else DASH


def _compact_filter_summary(summary, tier: str, width: int = 0) -> str:
    if not isinstance(summary, (tuple, list)):
        return DASH
    clauses = [
        clause.strip()
        for clause in summary
        if isinstance(clause, str) and clause.strip()
    ]
    if not clauses:
        return DASH

    budget = width or (FULL_WIDTH if tier == "full" else COMPACT_WIDTH)
    complete = " · ".join(clauses)
    return (
        complete
        if cell_len(complete) <= budget
        else "multiple filters applied"
    )


def _wallet_view(data: dict) -> tuple[str, object, object]:
    if data.get("list_view") == "filtered":
        return (
            "filtered",
            data.get("you_filtered_index"),
            data.get("filtered_contributors"),
        )
    if data.get("list_view") == "cleaned":
        return "clean", data.get("you_clean_rank"), data.get("clean_contributors")
    return "raw", data.get("you_rank"), data.get("contributors_total")


def _wallet_text(
    data: dict, tier: str, width: int = 0,
    success: str = _TOKEN_FALLBACK["success"],
    success_dim: str = _TOKEN_FALLBACK["success-darken-2"],
) -> Text:
    """The wallet card's five lines as one composited ``Text``.

    Built by direct ``Text.append``, never markup parsing: the title is a
    reader-supplied ENS name (PRD §13 A9's attacker-controlled string, see
    :func:`_wallet_title`), and the address line's copy icon lives in a
    ``Style(meta=...)`` span that only survives outside markup parsing
    anyway (``address_text``).  ``$success``/``$success-darken-2`` are
    Textual theme tokens and Rich's own ``Text``/``Style`` cannot resolve a
    ``$``-prefixed colour (the ``surf/pool4u_hero`` "$ trap"), so the
    caller resolves both to the app's current concrete colours once and
    hands them in here; :data:`_TOKEN_FALLBACK` is the default for a caller
    with no app to ask (a bare unit test).

    Matches the record-list hero contract (CLAUDE.md): title, standing,
    points/ETH and the address in ``success``; the detail line (and the
    standing line's trailing ``· view`` word) in ``success_dim``.
    """
    view, rank, total = _wallet_view(data)
    detail = (
        _compact_filter_summary(data.get("filter_summary"), tier, width)
        if view == "filtered" else _join_detail(data)
    )

    out = Text()
    out.append(_wallet_title(data), style=Style(color=success))
    out.append("\n")
    out.append(f"{_rank(rank)} of {_total(total)}", style=Style(color=success, bold=True))
    out.append(f" · {view}", style=Style(color=success_dim))
    out.append("\n")
    out.append(detail, style=Style(color=success_dim))
    out.append("\n")
    out.append(
        f"{fmt_points(data.get('you_points'))} pts · "
        f"{fmt_eth(data.get('you_credit_eth'))} ETH",
        style=Style(color=success, bold=True),
    )
    out.append("\n")
    address = data.get("you_address")
    if isinstance(address, str) and address.strip():
        out.append_text(address_text(address.strip(), width=None, style=success))
    else:
        out.append(WALLET_NOT_SET, style=Style(color=success))
    return out


def _cleaned_summary_lines(data: dict, _tier: str, _width: int = 0) -> list[str]:
    """Points, then the ETH those wallets routed -- the filtered card's shape.

    The third line used to be the static note "after linked removal", which
    the ``list CLEANED`` label on the line below already says.  Spending a row
    on a restatement while the raw and filtered cards both showed a real total
    made the cleaned card the only one a reader could not compare against the
    other two, so it shows the same number they do: gross routed, all of it
    refunded, over the clean population.
    """
    return _lines(
        "THE LIST",
        f"[bold]{_count(data.get('clean_contributors'), 'wallets')}[/]",
        f"{fmt_points(data.get('clean_points'))} pts",
        f"{fmt_eth_compact(data.get('clean_routed_eth'))} ETH",
        _list_label("cleaned"),
    )


def _filtered_summary_lines(data: dict, tier: str, _width: int = 0) -> list[str]:
    return _lines(
        "THE LIST",
        f"[bold]{_count(data.get('filtered_contributors'), 'wallets')}[/]",
        f"{fmt_points(data.get('filtered_points'))} pts",
        f"{fmt_eth_compact(data.get('filtered_routed_eth'))} ETH",
        _list_label("filtered"),
    )


def _summary_lines(data: dict, tier: str, width: int = 0) -> list[str]:
    view = data.get("list_view")
    if view == "cleaned":
        return _cleaned_summary_lines(data, tier, width)
    if view == "filtered":
        return _filtered_summary_lines(data, tier, width)
    return _raw_summary_lines(data, tier, width)


def _filter_lines(_data: dict, _tier: str, _width: int = 0) -> list[str]:
    shortcuts = [
        "'1' - first 1000 wallets",
        "'2' - joined hour 0",
        "'3' - whale splash",
        "'f' - more filters",
    ]
    padded_width = max(visible_len(line) for line in shortcuts)
    padded = [
        line + " " * (padded_width - visible_len(line))
        for line in shortcuts
    ]
    return _lines("THE FILTER", *padded)


_BUILDERS = {
    "curator-list-hero-summary": _summary_lines,
    "curator-list-hero-wallet": _wallet_text,
    "curator-list-hero-filter": _filter_lines,
}


class CuratorListHeroBox(Static):
    """One of the list view's raw, wallet, or cleaned summary cards."""

    def render_lines_at_tier(self, build) -> None:
        """``build`` is one of :data:`_BUILDERS`'s three functions, called
        with this box's own width.  Two of them still return
        ``list[str]`` markup lines, joined and handed to ``Static.update``
        as a string exactly as before; the wallet card's :func:`_wallet_text`
        returns a pre-built ``Text`` instead (the address line's copy icon
        needs one), which ``Static.update`` also accepts directly and never
        markup-parses -- so the ``over``/``WIDEN_HINT`` check below measures
        the ``Text`` by splitting it on its own newlines rather than by
        re-joining strings that do not exist for this box.
        """
        width = self.content_size.width
        content = build(_tier_for(width), width)
        if isinstance(content, Text):
            sub_lines = content.split("\n")
            over = width > 0 and any(line.cell_len > width for line in sub_lines)
            self.border_subtitle = WIDEN_HINT if over else ""
            self.update(content)
            return
        lines = content
        over = width > 0 and any(visible_len(line) > width for line in lines)
        self.border_subtitle = WIDEN_HINT if over else ""
        self.update("\n".join(lines))


class CuratorListHero(Vertical):
    """Raw list, configured wallet, and cleaned list summaries."""

    DEFAULT_CSS = """
    CuratorListHero {
        height: 8;
    }
    CuratorListHero > #curator-list-hero-boxes {
        height: 7;
    }
    CuratorListHero CuratorListHeroBox {
        width: 1fr;
        height: 7;
        margin: 0 1;
        border: solid $panel;
        background: $surface;
        content-align: center middle;
        text-align: center;
        text-wrap: nowrap;
        text-overflow: ellipsis;
        border-subtitle-color: $warning;
    }
    /* The copy icon on the full, unshortened address (PRD's "address stays
       visible even when ENS exists") needs exactly one column this card
       did not have: content_size measured 43 against a 44-need (the
       42-char address + ICON_COLS) at the documented 138-column screen.
       Margin and a fixed width were both tried and neither changed the
       box's measured content width at all -- this box sits in a Horizontal
       of three `1fr` siblings, and its share is set once by that layout,
       not by its own margin. Dropping only the shared left border (kept on
       top/right/bottom, so it still reads as its own card) is the one
       change that actually moved the measured number, and it costs exactly
       the one column needed -- not two, which a full `border: none` would
       have spent for nothing. Summary and filter are untouched. */
    CuratorListHero #curator-list-hero-wallet {
        border-left: none;
    }
    CuratorListHero #curator-list-hero-filter {
        color: $text;
        text-style: none;
    }
    CuratorListHero > #curator-list-hero-note {
        width: 100%;
        height: 1;
        padding: 0 2;
        color: $text-muted;
        text-align: center;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._payload: dict = {}

    def compose(self) -> ComposeResult:
        with Horizontal(id="curator-list-hero-boxes"):
            for box_id in _BOX_IDS:
                yield CuratorListHeroBox(
                    "[dim]Loading...[/]", id=box_id, classes="curator-list-hero-box"
                )
        yield Static(LIST_EXPORT_SUBTITLE, id="curator-list-hero-note")

    def update_data(
        self,
        phase=None,
        list_view="raw",
        contributors_total=None,
        deposits_total=None,
        volume_routed_eth=None,
        you_address=None,
        you_ens=None,
        you_rank=None,
        you_clean_rank=None,
        you_filtered_index=None,
        you_first_index=None,
        you_first_hour=None,
        you_points=None,
        you_credit_eth=None,
        clean_contributors=None,
        clean_points=None,
        clean_routed_eth=None,
        filtered_contributors=None,
        filtered_points=None,
        filtered_routed_eth=None,
        filter_summary=None,
        filter_editor_open=False,
        **_kwargs,
    ) -> None:
        self._payload = {
            "phase": phase,
            "list_view": list_view,
            "contributors_total": contributors_total,
            "deposits_total": deposits_total,
            "volume_routed_eth": volume_routed_eth,
            "you_address": you_address,
            "you_ens": you_ens,
            "you_rank": you_rank,
            "you_clean_rank": you_clean_rank,
            "you_filtered_index": you_filtered_index,
            "you_first_index": you_first_index,
            "you_first_hour": you_first_hour,
            "you_points": you_points,
            "you_credit_eth": you_credit_eth,
            "clean_contributors": clean_contributors,
            "clean_points": clean_points,
            "clean_routed_eth": clean_routed_eth,
            "filtered_contributors": filtered_contributors,
            "filtered_points": filtered_points,
            "filtered_routed_eth": filtered_routed_eth,
            "filter_summary": filter_summary,
            "filter_editor_open": filter_editor_open,
        }
        self._render_view()

    def on_resize(self, _event=None) -> None:
        if self._payload:
            self._render_view()

    def _theme_colors(self) -> tuple[str, str]:
        """The app's current concrete ``success``/``success-darken-2``
        colours, or :data:`_TOKEN_FALLBACK`'s plain Rich names when
        unavailable (not yet mounted, or a bare harness with no theme) --
        Rich's own ``Style`` cannot resolve a ``$``-prefixed token the way
        Textual's own markup parser can, which is the whole reason the
        wallet card builds a ``Text`` instead of handing ``Static`` a
        markup string.  Used only by :func:`_wallet_text`.
        """
        try:
            variables = self.app.get_css_variables()
            return (
                variables.get("success", _TOKEN_FALLBACK["success"]),
                variables.get("success-darken-2", _TOKEN_FALLBACK["success-darken-2"]),
            )
        except Exception:
            return _TOKEN_FALLBACK["success"], _TOKEN_FALLBACK["success-darken-2"]

    def _render_view(self) -> None:
        try:
            boxes = {
                box_id: self.query_one(f"#{box_id}", CuratorListHeroBox)
                for box_id in _BOX_IDS
            }
            note = self.query_one("#curator-list-hero-note", Static)
        except Exception:
            return

        success, success_dim = self._theme_colors()
        for box_id, box in boxes.items():
            builder = _BUILDERS[box_id]
            if box_id == "curator-list-hero-wallet":
                box.render_lines_at_tier(
                    lambda tier, width, fn=builder: fn(
                        self._payload, tier, width, success, success_dim
                    )
                )
            else:
                box.render_lines_at_tier(
                    lambda tier, width, fn=builder: fn(self._payload, tier, width)
                )

        width = max(self.content_size.width - 4, 0)
        if self._payload.get("filter_editor_open"):
            note.update(FILTER_EDITOR_NOTE)
        else:
            for candidate in (
                LIST_EXPORT_SUBTITLE,
                LIST_EXPORT_SUBTITLE_SHORT,
                LIST_EXPORT_SUBTITLE_TINY,
            ):
                if not width or len(candidate) <= width:
                    note.update(candidate)
                    break
            else:
                note.update(LIST_EXPORT_SUBTITLE_TINY)
