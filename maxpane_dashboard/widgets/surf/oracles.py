"""Read-only oracle request desk; widgets consume projected snapshots only."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from math import isfinite

from rich.style import Style
from rich.text import Text
from textual import on
from textual.binding import Binding
from textual.containers import Grid, Horizontal
from textual.message import Message
from textual.widgets import DataTable, Input, Static, Tree

from maxpane_dashboard.widgets.address import address_prose
from maxpane_dashboard.widgets.explorer import for_chain_id
from maxpane_dashboard.widgets.fmt import fmt_age, hhmm
from maxpane_dashboard.widgets.markup_safety import flatten
from maxpane_dashboard.widgets.panels import PanelBase
from maxpane_dashboard.widgets.rowfit import cell_len, clip, title_with_hint
from ._icons import fit_prose, keep_units, link_in_order, link_prose, mark_addresses, unmark
from ._oracle_answer import consensus_value, failed_answer, panel_text, seat_value
from .news_hero import HeroRecord, LocalSourceHeroCard, _count

_STATES = {"assessing": "assessing", "attested": "attested", "disagreed": "no quorum", "blocked": "blocked"}
_COLORS = {"assessing": "yellow", "attested": "green", "disagreed": "yellow", "blocked": "red"}
_CHAINS = {1: "ETH", 8453: "BASE", 4663: "RH"}


def _chain(row):
    value = row.get("chain_id")
    return _CHAINS.get(value, str(value)) if type(value) is int and value > 0 else "--"


def _age(row, now):
    stamp = row.get("created_ts")
    if any(type(value) not in (int, float) or not isfinite(value) or value <= 0 for value in (stamp, now)) or stamp > now:
        return "--"
    return fmt_age(now - stamp)


def _wrapped_prose(value, width, explorer, *, style=""):
    """Wrap on cells while keeping the shared helper's address/icon units whole."""
    value = flatten(value)
    if width < 13:  # The shared address window's minimum plus its copy icon.
        return link_prose(fit_prose(value, max(1, width), style=style), explorer=explorer)
    marked, addresses, spans = mark_addresses(value, width=width - 2)
    lines, cursor = [], 0
    while cursor < len(marked):
        end, used = cursor, 0
        for char in marked[cursor:]:
            cells = cell_len(char)
            if used + cells > width:
                break
            end, used = end + 1, used + cells
        for start, stop in spans:
            if start < end < stop:
                end = start
                break
        if end < len(marked) and marked[end:end + 1] != " ":
            space = marked.rfind(" ", cursor, end)
            if space > cursor:
                end = space
        lines.append(Text(unmark(marked[cursor:end].rstrip()), style=style))
        cursor = end
        while cursor < len(marked) and marked[cursor] == " ":
            cursor += 1
    link_in_order(lines, addresses, explorer)
    return Text("\n").join(lines)


class _OracleCard(LocalSourceHeroCard):
    def render(self):
        result = super().render()
        tone = _COLORS.get(self.data.key.removeprefix("oracle-"))
        if tone and self.data.accent:
            frame = result.style
            result.style = frame + Style(color=tone)
            result.spans = [span._replace(style=span.style + Style(color=tone))
                            if span.style == frame else span for span in result.spans]
        return result


class SurfOraclesHero(Grid):
    DEFAULT_CSS = """
    SurfOraclesHero { width: 1fr; height: 9; grid-size: 6 1; grid-columns: 1fr;
        grid-rows: 9; grid-gutter: 0 1; }
    """
    CARDS = (("requests", "REQUESTS", "LATEST 100", "request history"),
             ("assessing", "ASSESSING", "OPEN", "in progress"),
             ("attested", "ATTESTED", "CLOSED", "with agreement"),
             ("disagreed", "NO QUORUM", "CLOSED", "without quorum"),
             ("blocked", "BLOCKED", "ATTENTION", "needs attention"),
             ("networks", "NETWORKS", "CHAINS", "loaded requests"))

    def compose(self):
        for key, title, heading, footer in self.CARDS:
            yield _OracleCard(HeroRecord("oracle-" + key, title, heading, footer,
                                         digits="--", state="unavailable", accent=False))

    def update_data(self, *, surf_oracles=None, **_):
        payload = surf_oracles or {}
        rows = payload.get("rows")
        counts = Counter(row.get("status") for row in rows or [])
        counts.update(requests=len(rows or []), networks=len({r["chain_id"] for r in rows or [] if _chain(r) != "--"}))
        state = payload.get("state", "unavailable")
        for key, title, heading, footer in self.CARDS:
            value = _count(counts[key]) if rows is not None else "--"
            if key == "networks" and any(_chain(row) == "--" for row in rows or []):
                value = "--"
            self.query_one(f"#hero-oracle-{key}", _OracleCard).set_record(HeroRecord(
                "oracle-" + key, title, heading, footer, digits=value, state=state,
                read_ts=payload.get("read_ts"), accent=state in ("ok", "partial") and key in _COLORS and value not in ("0", "--")))


class _AnswerTree(Tree):
    BINDINGS = [Binding("left", "fold", show=False), Binding("right", "unfold", show=False)]

    def render_label(self, node, base_style, style):
        depth, parent = 0, node.parent
        while parent and parent is not self.root:
            depth, parent = depth + 1, parent.parent
        width = max(1, self.scrollable_content_region.width - depth * self.guide_depth)
        if node.allow_expand:
            label = super().render_label(node, base_style, style)
            label.truncate(width, overflow="ellipsis")
            return label
        marked, addresses, spans = mark_addresses(node.label.plain, width=max(11, width - 10))
        fitted = keep_units(marked, spans, clip(marked, width))
        label = Text(unmark(fitted) or "…", style=node.label.style)
        link_in_order([label], addresses, explorer=for_chain_id((node.data or {}).get("oracle_chain_id")))
        label.stylize(style)
        return label

    def action_fold(self):
        if self.cursor_node and self.cursor_node.is_expanded:
            self.cursor_node.collapse()
        else:
            self.action_cursor_parent()

    def action_unfold(self):
        if self.cursor_node:
            self.cursor_node.expand()


class _RequestPanel(PanelBase):
    TITLE = "REQUESTS"

    def compose_body(self):
        yield Static(Text(), id="oracle-coverage")
        yield Input(placeholder="find question, chain or request", id="oracle-find")
        yield DataTable(id="oracle-requests", cursor_type="row", zebra_stripes=True)


class _DetailPanel(PanelBase):
    TITLE = "SELECTED REQUEST"

    def compose_body(self):
        yield Static(Text("Select a request."), id="oracle-summary")
        yield Static(Text(), id="oracle-answer-heading")
        tree = _AnswerTree("answers", id="oracle-answers")
        tree.show_root, tree.auto_expand = False, False
        yield tree
        yield Static(Text("space fold · enter answer", style="dim"), id="oracle-answer-hint")


class SurfOraclesBody(Horizontal):
    """Local filters and selection; messages delegate reads and popups to the screen."""
    DEFAULT_CSS = """
    SurfOraclesBody { width: 1fr; height: 1fr; min-height: 28; }
    SurfOraclesBody PanelBase { border: round $panel; background: $background; padding: 0 1;
        height: 1fr; min-height: 28; }
    SurfOraclesBody > _RequestPanel { width: 66%; margin-right: 1; }
    SurfOraclesBody > _DetailPanel { width: 1fr; overflow-y: auto; scrollbar-gutter: stable; }
    SurfOraclesBody .panel-title { height: 1; text-wrap: nowrap; }
    SurfOraclesBody #oracle-coverage { height: auto; margin-bottom: 1; color: $text-muted; }
    SurfOraclesBody #oracle-find { display: none; height: 3; }
    SurfOraclesBody #oracle-requests { height: 1fr; min-height: 8; scrollbar-gutter: stable; }
    SurfOraclesBody #oracle-summary { height: auto; margin-bottom: 1; }
    SurfOraclesBody #oracle-answer-heading { height: auto; margin-bottom: 1; color: $text-muted; }
    SurfOraclesBody #oracle-answers { height: 1fr; min-height: 8; padding: 0; background: $background;
        overflow-x: hidden; overflow-y: auto; scrollbar-gutter: stable; }
    SurfOraclesBody #oracle-answer-hint { height: auto; color: $text-muted; }
    """

    class RequestSelected(Message):
        def __init__(self, request_id):
            super().__init__()
            self.request_id = request_id

    class AnswerSelected(Message):
        def __init__(self, row):
            super().__init__()
            self.row = row

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._payload, self._rows = {}, {}
        self._selected = None
        self._filter, self._chain_filter, self._search = "all", "all", ""
        self._visible_ids, self._tree_signature, self._answer_nodes = [], None, {}

    def compose(self):
        yield _RequestPanel(id="oracle-request-panel")
        yield _DetailPanel(id="oracle-detail-panel")

    def update_data(self, *, surf_oracles=None, **_):
        self._payload = surf_oracles or {}
        self._rows = {row["id"]: row for row in self._payload.get("rows") or []}
        self._refresh_requests()

    def focus_requests(self):
        self.query_one("#oracle-requests", DataTable).focus()

    def focus_find(self):
        field = self.query_one("#oracle-find", Input)
        field.display = True
        field.focus()

    def close_find(self) -> bool:
        field = self.query_one("#oracle-find", Input)
        if not field.display:
            return False
        field.display, field.value, self._search = False, "", ""
        self._refresh_requests()
        self.focus_requests()
        return True

    def cycle_filter(self):
        options = ("all", *_STATES, "other")
        self._filter = options[(options.index(self._filter) + 1) % len(options)]
        self._refresh_requests()

    def cycle_chain(self):
        options = ["all", *dict.fromkeys(_chain(row) for row in self._rows.values())]
        index = options.index(self._chain_filter) if self._chain_filter in options else 0
        self._chain_filter = options[(index + 1) % len(options)]
        self._refresh_requests()

    @on(Input.Changed, "#oracle-find")
    def _find_changed(self, event):
        self._search = flatten(event.value).casefold()
        self._refresh_requests()

    @on(Input.Submitted, "#oracle-find")
    def _find_submitted(self):
        self.focus_requests()

    def on_resize(self):
        self.call_after_refresh(self._refresh_requests)

    def _refresh_requests(self):
        table = self.query_one("#oracle-requests", DataTable)
        if not table.columns:
            for label, width in (("AGE", 4), ("CHAIN", 5), ("STATE", 9), ("QUESTION", 1)):
                table.add_column(label, width=width, key=label)
        fixed = table.ordered_columns[:-1]
        question = table.ordered_columns[-1]
        question.width = max(1, table.scrollable_content_region.width - sum(c.get_render_width(table) for c in fixed) - 2 * table.cell_padding)
        rows = [row for row in self._rows.values() if
                (self._filter == "all" or row.get("status") == self._filter or
                 self._filter == "other" and row.get("status") not in _STATES) and
                (self._chain_filter == "all" or _chain(row) == self._chain_filter) and
                self._search in flatten(f"{row.get('question', '')} {_chain(row)} {row['id']} {row.get('job_id', '')}").casefold()]
        visible = [row["id"] for row in rows]
        changed = visible != self._visible_ids
        scroll = table.scroll_offset
        if changed:
            with table.prevent(DataTable.RowHighlighted):
                table.clear()
            self._visible_ids = visible
        for row in rows:
            status = flatten(row.get("status")) or "unknown"
            cells = [Text(clip(_age(row, self._payload.get("now_ts")), 4), style="dim"),
                     Text(clip(_chain(row), 5)), fit_prose(_STATES.get(status, status), 9, style=_COLORS.get(status, "grey62")),
                     link_prose(fit_prose(flatten(row.get("question")) or "Question unavailable", question.width),
                                explorer=for_chain_id(row.get("chain_id")))]
            with table.prevent(DataTable.RowHighlighted):
                if changed:
                    table.add_row(*cells, key=row["id"])
                else:
                    for column, cell in zip(table.ordered_columns, cells):
                        if table.get_cell(row["id"], column.key) != cell:
                            table.update_cell(row["id"], column.key, cell)
        preferred = self._selected or self._payload.get("selected_id")
        selected = preferred if preferred in visible else next(iter(visible), None)
        if changed and selected:
            with table.prevent(DataTable.RowHighlighted):
                table.move_cursor(row=visible.index(selected), scroll=selected != self._selected)
            if selected == self._selected:
                table.scroll_to(x=scroll.x, y=scroll.y, animate=False, immediate=True)
        self._select(selected)
        table.refresh(layout=True)
        state = self._payload.get("state", "unavailable")
        coverage = f"LATEST 100 · {len(rows)} shown / {len(self._rows)} loaded · {_STATES.get(self._filter, self._filter)} · {self._chain_filter}"
        other = sum(row.get("status") not in _STATES for row in self._rows.values())
        if other:
            coverage += f" · {other} other"
        if self._payload.get("rows") is None:
            coverage = "Requests unavailable"
        coverage += f" · {state} · as of {hhmm(self._payload.get('read_ts'), unknown='--:--')}"
        self.query_one("#oracle-coverage", Static).update(Text(coverage))
        clipped = any(address_prose(flatten(row.get("question"))).cell_len > question.width or len(_chain(row)) > 5 or len(flatten(row.get("status"))) > 9 for row in rows)
        self.query_one("#oracle-request-panel .panel-title", Static).update(Text(title_with_hint("REQUESTS", clipped, table.size.width)))

    def _select(self, request_id):
        changed = request_id != self._selected
        self._selected = request_id
        if changed:
            self.query_one("#oracle-detail-panel").scroll_home(animate=False)
        self._detail()
        if changed and request_id is not None and request_id != self._payload.get("selected_id"):
            self.post_message(self.RequestSelected(request_id))

    @on(DataTable.RowHighlighted, "#oracle-requests")
    def _highlight(self, event):
        if event.row_key.value in self._visible_ids:
            self._select(event.row_key.value)

    @on(DataTable.RowSelected, "#oracle-requests")
    def _open_request(self, event):
        self._select(event.row_key.value)
        self.query_one("#oracle-answers", Tree).focus()

    def _detail(self):
        row = self._rows.get(self._selected)
        detail = self._payload.get("detail")
        state = self._payload.get("detail_state", "unavailable")
        if self._selected != self._payload.get("selected_id"):
            state, detail = "loading", None
        elif detail and (detail.get("id") != self._selected or detail.get("job_id") != row.get("job_id")):
            state, detail = "mismatch", None
        out = Text()
        width = self.query_one("#oracle-summary", Static).content_size.width
        if row:
            explorer = for_chain_id(row.get("chain_id"))
            out.append_text(_wrapped_prose((detail or row).get("question") or "Question unavailable", width, explorer))
            status = flatten((detail or row).get("status")) or "unknown"
            out.append("\n\n" + _STATES.get(status, status).upper(), style=_COLORS.get(status, "grey62"))
            out.append(f" · {_chain(row)} · {_age(row, self._payload.get('now_ts'))}\n", style="dim")
            if detail and state in ("ok", "stale", "partial"):
                result = (consensus_value(detail) + " · " + (flatten(detail.get("panel_answer_type")) or "unknown type") if status == "attested" else {
                    "disagreed": "No attested answer · closed", "assessing": "Awaiting agreement", "blocked": "Request blocked"}.get(status, "Unrecognized request state"))
                out.append_text(_wrapped_prose(result, width, explorer, style="bold")).append("\n")
                out.append(f"{_count(detail.get('agreed'))} agreed · {_count(detail.get('quorum'))} required\n{_count(detail.get('panel_size'))} seats target\n", style="dim")
            elif state == "ok":
                state = "unavailable"
            out.append(f"{state} · as of {hhmm(self._payload.get('detail_read_ts'), unknown='--:--')}", style="dim" if state == "ok" else "yellow")
        else:
            out.append("Requests unavailable" if self._payload.get("rows") is None else "No matching requests", style="dim")
        self.query_one("#oracle-summary", Static).update(out)
        members = detail.get("members") if row and detail and state in ("ok", "stale", "partial") else None
        heading = "ANSWERS · unavailable" if detail and members is None else ""
        if detail and members is not None:
            heading = f"ANSWERS · {len(members)} loaded / {_count(detail.get('member_count'))} reported"
            if detail.get("truncated"):
                heading += " · partial"
        self.query_one("#oracle-answer-heading", Static).update(Text(heading))
        self._answers(members)

    def _answers(self, members):
        tree = self.query_one("#oracle-answers", Tree)
        signature = (self._selected, members)
        if signature == self._tree_signature:
            for member in members or []:
                key = (member.get("job_id"), member.get("submission_hash"))
                for leaf in self._answer_nodes[key].children:
                    leaf.data = member
            return
        same_request = self._tree_signature is not None and self._tree_signature[0] == self._selected
        collapsed = {key for key, node in self._answer_nodes.items() if not node.is_expanded} if same_request else set()
        selected_key = next((key for key, node in self._answer_nodes.items() if node is tree.cursor_node), None)
        scroll = tree.scroll_offset
        tree.clear()
        self._answer_nodes, groups = {}, {}
        counts = Counter(member.get("panel_state") for member in members or [])
        labels = {"agreed": "AGREED", "outvoted": "OUTVOTED", "no_quorum_in": "IN CLUSTER · NO QUORUM", "no_quorum_out": "OUTSIDE CLUSTER · NO QUORUM"}
        for member in members or []:
            state = member.get("panel_state")
            if state not in groups:
                key = ("group", state)
                groups[state] = tree.root.add(Text(f"{labels.get(state, flatten(state).upper() or 'UNKNOWN')} · {counts[state]}", style="green" if state == "agreed" else "yellow"), expand=key not in collapsed and (same_request or not groups))
                self._answer_nodes[key] = groups[state]
            seat = member.get("seat")
            name = f"seat {seat}" if type(seat) is int and seat >= 0 else "unknown seat · " + flatten(member.get("submission_hash"))[:8]
            key = (member.get("job_id"), member.get("submission_hash"))
            label = Text(name + "  ").append_text(panel_text(member))
            node = groups[state].add(label, expand=key not in collapsed and (same_request or member is members[0]))
            self._answer_nodes[key] = node
            explorer = for_chain_id(member.get("oracle_chain_id"))
            answer = failed_answer(member) if member.get("oracle_member_ok") is False else seat_value(member)
            self._answer_nodes[(*key, "answer")] = node.add_leaf(address_prose("answer  " + answer, explorer=explorer), data=member)
            if member.get("oracle_notes"):
                self._answer_nodes[(*key, "notes")] = node.add_leaf(address_prose(flatten(member["oracle_notes"]), explorer=explorer), data=member)
            self._answer_nodes[(*key, "open")] = node.add_leaf(Text("open full answer »", style="green"), data=member)
        if members == []:
            tree.root.add_leaf(Text("No answer records loaded", style="dim"))
        tree.root.expand()
        self._tree_signature = deepcopy(signature)
        if same_request:
            if selected_key in self._answer_nodes:
                tree._tree_lines  # Lay out refreshed nodes before restoring their cursor line.
                tree.move_cursor(self._answer_nodes[selected_key])
            tree.scroll_to(x=scroll.x, y=scroll.y, animate=False, immediate=True)

    @on(Tree.NodeSelected, "#oracle-answers")
    def _open_answer(self, event):
        if event.node.data is not None:
            self.post_message(self.AnswerSelected(event.node.data))
