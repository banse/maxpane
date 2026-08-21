"""Record summary hero shown only above THE LIST's ``l`` view."""

from __future__ import annotations

from rich.cells import cell_len
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from maxpane_dashboard.widgets.curator._fmt import (
    DASH,
    fmt_eth_compact,
    fmt_points,
    short_label,
)
from maxpane_dashboard.widgets.curator.hero import (
    LIST_EXPORT_SUBTITLE,
    LIST_EXPORT_SUBTITLE_SHORT,
    LIST_EXPORT_SUBTITLE_TINY,
    WIDEN_HINT,
)
from maxpane_dashboard.widgets.markup_safety import safe_markup, visible_len

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


def _lines(title: str, *body: str) -> list[str]:
    rows = list(body[:4]) + [""] * (4 - len(body[:4]))
    return [f"[dim]{title}[/]", *rows]


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


def _wallet_identity(data: dict, tier: str) -> str:
    ens = data.get("you_ens")
    address = data.get("you_address")
    has_ens = isinstance(ens, str) and bool(ens.strip())
    has_address = isinstance(address, str) and bool(address.strip())
    if not has_ens and not has_address:
        return "WALLET NOT SET"
    if tier != "full":
        return safe_markup(short_label(ens, address))
    if has_ens:
        return safe_markup(" ".join(ens.split()))
    return safe_markup(address.strip())


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
        safe_markup(complete)
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


def _wallet_lines(data: dict, tier: str, width: int = 0) -> list[str]:
    view, rank, total = _wallet_view(data)
    detail = (
        _compact_filter_summary(data.get("filter_summary"), tier, width)
        if view == "filtered" else _join_detail(data)
    )
    standing = (
        f"[$success][bold]{_rank(rank)} of {_total(total)}[/][/] "
        f"[$success-darken-2]· {view}[/]"
    )
    return _lines(
        "YOUR WALLET",
        standing,
        f"[$success]{detail}[/]",
        f"[$success]{_wallet_identity(data, tier)}[/]",
        f"[$success][bold]{fmt_points(data.get('you_points'))} pts[/][/]",
    )


def _cleaned_summary_lines(data: dict, tier: str, _width: int = 0) -> list[str]:
    note = "after linked removal" if tier != "minimal" else "after removal"
    return _lines(
        "THE LIST",
        f"[bold]{_count(data.get('clean_contributors'), 'wallets')}[/]",
        f"{fmt_points(data.get('clean_points'))} pts",
        f"[dim]{note}[/]",
        _list_label("cleaned"),
    )


def _filtered_summary_lines(data: dict, tier: str, _width: int = 0) -> list[str]:
    return _lines(
        "THE LIST",
        f"[bold]{_count(data.get('filtered_contributors'), 'wallets')}[/]",
        f"{fmt_points(data.get('filtered_points'))} pts",
        f"{fmt_eth_compact(data.get('filtered_routed_eth'))} ETH deposited",
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
        "'f' - for more filters",
    ]
    padded_width = max(visible_len(line) for line in shortcuts)
    padded = [
        line + " " * (padded_width - visible_len(line))
        for line in shortcuts
    ]
    return _lines("THE FILTER", *padded)


_BUILDERS = {
    "curator-list-hero-summary": _summary_lines,
    "curator-list-hero-wallet": _wallet_lines,
    "curator-list-hero-filter": _filter_lines,
}


class CuratorListHeroBox(Static):
    """One of the list view's raw, wallet, or cleaned summary cards."""

    def render_lines_at_tier(self, build) -> None:
        width = self.content_size.width
        lines = build(_tier_for(width), width)
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
        clean_contributors=None,
        clean_points=None,
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
            "clean_contributors": clean_contributors,
            "clean_points": clean_points,
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

    def _render_view(self) -> None:
        try:
            boxes = {
                box_id: self.query_one(f"#{box_id}", CuratorListHeroBox)
                for box_id in _BOX_IDS
            }
            note = self.query_one("#curator-list-hero-note", Static)
        except Exception:
            return

        for box_id, box in boxes.items():
            builder = _BUILDERS[box_id]
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
