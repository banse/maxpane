"""Read-only work desk: loaded workflows, jobs and their actual step outcomes."""
from __future__ import annotations

from rich.style import Style
from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal, VerticalScroll
from textual.widgets import Input, Static, Tree

from maxpane_dashboard.widgets.address import address_prose, job_text
from maxpane_dashboard.widgets.fmt import fmt_age, hhmm
from maxpane_dashboard.widgets.markup_safety import flatten
from maxpane_dashboard.widgets.panels import PanelBase
from maxpane_dashboard.widgets.rowfit import WIDEN_HINT, cell_len, clip, pad, title_with_hint
from ._fmt import JOB_EXPLORER
from ._icons import fit_prose, post_preview
from .news_hero import HeroRecord, NewsHeroCard, _count, _number

_BUILD = {"implement", "integrate", "test", "tests"}
_TERMINAL = {"completed", "cancelled", "failed", "superseded"}


def _tone(state):
    if state in ("blocked", "failed", "rejected"):
        return "red"
    if state in ("working", "executing", "accepted", "completed", "pass"):
        return "green"
    return "yellow" if state in ("queued", "waiting", "pending") else "grey62"


def _age(timestamp, now):
    stamp, now = _number(timestamp), _number(now)
    return fmt_age(max(0, now - stamp)) + " ago" if stamp is not None and now is not None else "--"


class _WorkHeroCard(NewsHeroCard):
    def _footer(self):
        super()._footer()
        room = self.size.width - 2
        title = "⊙ " + self.data.title
        footer = Text.from_markup(self.border_subtitle).plain
        if room > 0 and (cell_len(footer) > room or cell_len(title) > room):
            title = clip(title, max(1, room - len(WIDEN_HINT) - 1)) + " " + WIDEN_HINT
        self.border_title = Text(title)

    def render(self):
        result = super().render()
        if self.data.key == "work-blocked" and self.data.accent:
            # Recolor the inherited frame only; digits retain their own ink.
            frame = result.style
            result.style = frame + Style(color="red")
            result.spans = [span._replace(style=span.style + Style(color="red"))
                            if span.style == frame else span for span in result.spans]
        return result


class SurfWorkHero(Grid):
    DEFAULT_CSS = """
    SurfWorkHero { width: 1fr; height: 9; grid-size: 6 1; grid-columns: 1fr;
        grid-rows: 9; grid-gutter: 0 1; }
    """
    CARDS = (("jobs", "JOBS", "ACTIVE", "executing"),
             ("workflows", "WORKFLOWS", "ACTIVE", "in progress"),
             ("seats", "SEATS", "WORKING", "assigned seats"),
             ("build", "BUILD", "STEPS", "building"),
             ("review", "REVIEW", "STEPS", "reviewing"),
             ("blocked", "BLOCKED", "JOBS", "needs attention"))

    def compose(self) -> ComposeResult:
        for key, title, heading, footer in self.CARDS:
            yield _WorkHeroCard(HeroRecord("work-" + key, title, heading, footer, digits="--", state="unavailable", accent=False))

    def update_data(self, *, surf_work=None, **_kwargs):
        payload = surf_work if isinstance(surf_work, dict) else {}
        summary = payload.get("summary") or {}
        state = payload.get("state", "unavailable")
        for key, title, heading, footer in self.CARDS:
            count = _count(summary.get(key)) if state != "unavailable" else "--"
            record = HeroRecord("work-" + key, title, heading, footer, digits=count,
                                state=state, read_ts=_number(payload.get("read_ts")),
                                accent=state == "ok" and count not in ("--", "0"))
            self.query_one(f"#hero-work-{key}", _WorkHeroCard).set_record(record)


class _WorkTree(Tree):
    BINDINGS = [Binding("left", "fold", show=False), Binding("right", "unfold", show=False)]

    def action_fold(self):
        if self.cursor_node and self.cursor_node.is_expanded:
            self.cursor_node.collapse()
        else:
            self.action_cursor_parent()

    def action_unfold(self):
        if self.cursor_node:
            self.cursor_node.expand()

    def label_width(self, node):
        depth, parent = 0, node.parent
        while parent and parent is not self.root:
            depth, parent = depth + 1, parent.parent
        return max(1, self.scrollable_content_region.width - depth * self.guide_depth - 2)

    def render_label(self, node, base_style, style):
        prefix = self.ICON_NODE_EXPANDED if node.is_expanded else self.ICON_NODE
        prefix = prefix if node.allow_expand else ""
        width = max(1, self.label_width(node) - cell_len(prefix))
        left, right = node.data[3:] if node.data else (node.label.plain, "")
        if right:
            right = clip(right, max(1, width - 4))
            room = max(1, width - cell_len(right) - 2)
            label = fit_prose(left, room, style=node.label.style)
            label.append(" " * max(2, width - label.cell_len - cell_len(right)))
            label.append(right, style=node.label.style)
        else:
            label = fit_prose(node.label.plain, width, style=node.label.style)
        label.stylize(style)
        # Preserve Textual's expander action on the arrow at every tree depth.
        return Text(prefix, style=base_style + Style(meta={"toggle": True})) + label


class _WorkTreePanel(PanelBase):
    TITLE = "WORK TREE"
    def compose_body(self):
        yield Static(Text("unavailable"), id="work-coverage")
        yield Input(placeholder="find workflow, job or seat", id="work-find")
        tree = _WorkTree("work", id="work-tree")
        tree.show_root = False
        tree.auto_expand = False
        yield tree


class _WorkDetailPanel(PanelBase):
    TITLE = "SELECTED WORK"
    def compose_body(self):
        with VerticalScroll(id="work-detail-scroll", can_focus=True):
            yield Static(Text("Select a workflow, job or step."), id="work-detail", markup=False)


class SurfWorkBody(Horizontal):
    """Local tree navigation and detail selection; consumes one projected snapshot."""
    DEFAULT_CSS = """
    SurfWorkBody { width: 1fr; height: 1fr; min-height: 16; }
    SurfWorkBody > _WorkTreePanel { width: 42%; height: 1fr; min-height: 16; margin-right: 1; }
    SurfWorkBody > _WorkDetailPanel { width: 1fr; height: 1fr; min-height: 16; }
    SurfWorkBody PanelBase { border: round $panel; background: $background; padding: 0 1; }
    SurfWorkBody .panel-title { height: 1; text-wrap: nowrap; }
    SurfWorkBody #work-coverage { height: 1; color: $text-muted; text-wrap: nowrap; }
    SurfWorkBody #work-find { display: none; height: 3; }
    SurfWorkBody #work-tree { height: 1fr; min-height: 8; padding: 0; background: $background;
        overflow-x: hidden; overflow-y: auto; scrollbar-gutter: stable; }
    SurfWorkBody #work-detail-scroll { height: 1fr; min-height: 8; overflow-x: hidden;
        overflow-y: auto; scrollbar-gutter: stable; }
    SurfWorkBody #work-detail { height: auto; width: 1fr; }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._payload = {}
        self._selected = None
        self._filter = "all"
        self._search = ""
        self._work_nodes = {}
        self._entries = {}

    def compose(self):
        yield _WorkTreePanel(id="work-tree-panel")
        yield _WorkDetailPanel(id="work-detail-panel")

    def update_data(self, *, surf_work=None, **_kwargs):
        self._payload = surf_work if isinstance(surf_work, dict) else {}
        self._rebuild()

    def focus_tree(self):
        self.query_one("#work-tree", Tree).focus()

    def focus_find(self):
        field = self.query_one("#work-find", Input)
        field.display = True
        field.focus()

    def close_find(self) -> bool:
        field = self.query_one("#work-find", Input)
        if not field.display:
            return False
        field.display = False
        field.value = ""
        self._search = ""
        self._rebuild()
        self.focus_tree()
        return True

    def cycle_filter(self):
        options = ("all", "build", "review", "blocked")
        self._filter = options[(options.index(self._filter) + 1) % len(options)]
        self._rebuild()

    @on(Input.Changed, "#work-find")
    def _find_changed(self, event):
        self._search = flatten(event.value).casefold()
        self._rebuild()

    @on(Input.Submitted, "#work-find")
    def _find_submitted(self):
        self.focus_tree()

    def on_resize(self):
        self.call_after_refresh(self._titles)
        self.call_after_refresh(self._detail)

    def _matches(self, job, *, workflow_match=False, workflow_blocked=False):
        nodes = job.get("nodes") or []
        if self._filter == "blocked" and job.get("state") != "blocked" and not workflow_blocked:
            return False
        if self._filter in ("build", "review"):
            roles = _BUILD if self._filter == "build" else {"review"}
            if not any(n.get("state") == "working" and n.get("role") in roles for n in nodes):
                return False
        haystack = flatten(" ".join(str(job.get(k) or "") for k in ("id", "objective", "template")))
        haystack += " " + " ".join(f"{n.get('key')} {n.get('seat')} {n.get('role')}" for n in nodes)
        return not self._search or workflow_match or self._search in haystack.casefold()

    def _rebuild(self):
        tree = self.query_one("#work-tree", Tree)
        collapsed = {key for key, node in self._work_nodes.items() if node.allow_expand and not node.is_expanded}
        known = set(self._work_nodes)
        selected = self._selected
        tree.clear()
        self._work_nodes, self._entries = {}, {}
        jobs = self._payload.get("jobs")
        workflows = self._payload.get("workflows")
        by_id = {j["id"]: j for j in jobs or []}
        linked = {w.get(key) for w in workflows or [] for key in ("contracts_job_id", "frontend_job_id") if w.get(key)}

        def add(parent, key, kind, row, label, children=False, suffix=""):
            label, suffix = flatten(label), flatten(suffix)
            entry = (key, kind, row, label, suffix)
            node = parent.add(Text(label + ("  " + suffix if suffix else ""), style=_tone(row.get("state", row.get("status")))),
                              data=entry, allow_expand=children,
                              expand=key not in collapsed and not (kind == "workflow" and row.get("status") == "blocked" and key not in known))
            self._work_nodes[key], self._entries[key] = node, entry
            return node

        def add_job(parent, job, label=None):
            key = "job:" + job["id"]
            nodes = job.get("nodes") or []
            node = add(parent, key, "job", job,
                       label or job.get('objective') or job['id'], bool(nodes), suffix=job.get('state') or 'unknown')
            for step in nodes:
                seat = f"#{step['seat']}" if step.get("seat") is not None else "seat --"
                add(node, f"step:{job['id']}:{step['key']}", "step", step,
                    step['key'], suffix=f"{seat} {step.get('role') or '--'} {step.get('state') or 'unknown'}")

        def add_others():
            others = [j for j in jobs or [] if j["id"] not in linked and j.get("state") not in _TERMINAL and self._matches(j)]
            if others:
                group = add(tree.root, "other", "group", {}, "OTHER JOBS", True)
                for job in sorted(others, key=lambda j: (j.get("state") != "executing", -(j.get("updated_ts") or j.get("created_ts") or 0))):
                    add_job(group, job)

        others_added = False
        for workflow in sorted(workflows or [], key=lambda w: (w.get("status") == "blocked", -(w.get("created_ts") or 0))):
            if workflow.get("status") == "blocked" and not others_added:
                add_others()
                others_added = True
            ids = [("Contracts", workflow.get("contracts_job_id")), ("Frontend", workflow.get("frontend_job_id"))]
            if workflow.get("status") in _TERMINAL and not any(by_id.get(jid, {}).get("state") == "executing" for _, jid in ids):
                continue
            workflow_match = self._search in flatten(f"{workflow['id']} {workflow.get('objective') or ''}").casefold()
            blocked = workflow.get("status") == "blocked"
            visible = [(label, jid) for label, jid in ids if jid and (
                self._matches(by_id[jid], workflow_match=workflow_match, workflow_blocked=blocked)
                if jid in by_id else workflow_match and (self._filter == "all" or self._filter == "blocked" and blocked))]
            workflow_visible = workflow_match and (self._filter == "all" or self._filter == "blocked" and blocked)
            if not visible and not workflow_visible:
                continue
            parent = add(tree.root, "workflow:" + workflow["id"], "workflow", workflow,
                         workflow.get('objective') or workflow['id'], bool(visible), suffix=workflow.get('status') or 'unknown')
            for label, jid in visible:
                if jid in by_id:
                    add_job(parent, by_id[jid], label)
                else:
                    add(parent, "missing:" + jid, "missing", {"id": jid}, label + " · job not loaded")
        if not others_added:
            add_others()
        if not self._entries:
            unavailable = jobs is None or workflows is None
            tree.root.add_leaf(Text("unavailable" if unavailable else "No matching work" if self._search or self._filter != "all" else "No work in progress", style="dim"))
        if selected not in self._entries:
            def newest(rows):
                return sorted(rows, key=lambda row: (row.get("updated_ts") or row.get("created_ts") or 0,
                                                     row.get("created_ts") or 0, row["id"]), reverse=True)
            visible_jobs = newest(j for j in jobs or [] if "job:" + j["id"] in self._entries)
            active = [j for j in visible_jobs if j.get("state") == "executing"]
            flows = newest(w for w in workflows or [] if "workflow:" + w["id"] in self._entries and w.get("status") not in _TERMINAL)
            if active:
                selected = "job:" + active[0]["id"]
            elif flows:
                selected = "workflow:" + flows[0]["id"]
            else:
                selected = "job:" + visible_jobs[0]["id"] if visible_jobs else next(iter(self._entries), None)
        if selected != self._selected:
            self.query_one("#work-detail-scroll", VerticalScroll).scroll_home(animate=False)
        self._selected = selected
        if selected:
            self.call_after_refresh(self._restore_cursor, selected)
        self._detail()
        self._titles()

    def _restore_cursor(self, selected):
        if selected not in self._entries:
            return
        tree = self.query_one("#work-tree", Tree)
        tree._tree_lines  # Lay out node line numbers before moving the cursor.
        node = self._work_nodes[selected]
        self._selected = selected
        if node._line >= 0:
            tree.move_cursor(node)
        self._detail()

    def _titles(self):
        tree = self.query_one("#work-tree", _WorkTree)
        clipped = any(cell_len(node.label.plain) > tree.label_width(node) - (2 if node.allow_expand else 0) for node in self._work_nodes.values())
        state = self._payload.get("state", "unavailable")
        title = f"WORK TREE · {self._filter} · {state} · as of {hhmm(self._payload.get('read_ts'), unknown='--:--')}"
        panel = self.query_one("#work-tree-panel", PanelBase)
        room = max(1, panel.content_size.width - 2)
        if cell_len(title) + (len(WIDEN_HINT) + 2 if clipped else 0) > room:
            title = clip(title, max(1, room - len(WIDEN_HINT) - 2))
            clipped = True
        panel.query_one(".panel-title", Static).update(Text(title_with_hint(title, clipped, room)))
        coverage = f"{_count(self._payload.get('jobs_loaded'))} jobs · {_count(self._payload.get('workflows_loaded'))} workflows loaded"
        if self._payload.get("partial"):
            coverage += " · partial"
        if state == "unavailable":
            coverage = "Work unavailable"
        self.query_one("#work-coverage", Static).update(fit_prose(coverage, max(1, tree.content_size.width)))

    @on(Tree.NodeHighlighted, "#work-tree")
    def _highlight(self, event):
        if event.node.data and event.node.data[0] in self._entries:
            if self._selected != event.node.data[0]:
                self.query_one("#work-detail-scroll", VerticalScroll).scroll_home(animate=False)
            self._selected = event.node.data[0]
            self._detail()

    @on(Tree.NodeSelected, "#work-tree")
    def _open(self, event):
        if event.node.data:
            self._selected = event.node.data[0]
            self._detail()
            if event.node.data[1] in ("workflow", "group"):
                event.node.toggle()
            else:
                self.query_one("#work-detail-scroll", VerticalScroll).focus()

    def _detail(self):
        entry = self._entries.get(self._selected)
        panel = self.query_one("#work-detail-panel", PanelBase)
        if entry is None:
            panel.query_one(".panel-title", Static).update(Text("SELECTED WORK"))
            self.query_one("#work-detail", Static).update(Text("Work unavailable" if self._payload.get("state", "unavailable") == "unavailable" else "Select a workflow, job or step.", style="dim"))
            return
        _, kind, row, _, _ = entry
        panel.query_one(".panel-title", Static).update(Text("SELECTED " + kind.upper()))
        out = Text()
        def field(label, value, style=""):
            out.append(label.ljust(15), style="dim")
            out.append_text(address_prose(flatten(value) or "--", style=style, explorer=None)).append("\n")
        def section(label, value, style=""):
            out.append("\n" + label + "\n", style="dim")
            out.append_text(address_prose(flatten(value) or "--", style=style, explorer=None)).append("\n")
        now = self._payload.get("now_ts")
        if kind in ("job", "workflow"):
            objective = flatten(row.get("objective")) or "Objective unavailable"
            preview = post_preview(objective, max(8, panel.content_size.width - 2), Style())
            out.append_text(Text("\n").join(preview)).append("\n\n")
            if kind == "job":
                out.append("JOB            ", style="dim").append_text(job_text(row.get("id"), 36, explorer=JOB_EXPLORER)).append("\n")
            field("STATE", row.get("state", row.get("status")), _tone(row.get("state", row.get("status"))))
            field("CREATED", _age(row.get("created_ts"), now))
            field("LAST UPDATE", _age(row.get("updated_ts"), now))
        if kind == "workflow":
            jobs = {j["id"]: j for j in self._payload.get("jobs") or []}
            out.append("\nLINKED JOBS\n", style="dim")
            for label, key in (("Contracts", "contracts_job_id"), ("Frontend", "frontend_job_id")):
                jid = row.get(key)
                out.append(label.ljust(12))
                out.append_text(job_text(jid, 36, explorer=JOB_EXPLORER))
                out.append(" · " + (jobs[jid].get("state", "unknown") if jid in jobs else "not loaded" if jid else "not assigned") + "\n")
            if row.get("waiting_for_hosting"):
                section("WAITING", "Hosting", "yellow")
            if row.get("failure"):
                section("FAILURE", row["failure"], "red")
        elif kind == "job":
            field("TEMPLATE", row.get("template"))
            nodes = row.get("nodes")
            out.append("\nSTEPS\n", style="dim")
            if nodes is None:
                out.append("Step details unavailable\n", style="yellow")
            elif not nodes:
                out.append("No steps reported\n", style="dim")
            else:
                width = max(8, panel.content_size.width - 1)
                key_width = max(4, width - 33)
                out.append(pad("STEP", key_width) + "  SEAT     STATE       UPDATED\n", style="dim")
                clipped = width < 38
                for step in nodes:
                    seat = f"#{step['seat']}" if step.get("seat") is not None else "--"
                    key = flatten(step.get("key"))
                    state = flatten(step.get("state")) or "unknown"
                    clipped |= cell_len(key) > key_width or cell_len(state) > 10 or cell_len(seat) > 7
                    fitted = fit_prose(key, key_width)
                    fitted.pad_right(max(0, key_width - fitted.cell_len))
                    out.append_text(fitted).append("  " + pad(clip(seat, 7), 7) + "  ")
                    out.append(pad(clip(state, 10), 10), style=_tone(step.get("state")))
                    out.append("  " + _age(step.get("updated_ts"), now) + "\n")
                if clipped:
                    panel.query_one(".panel-title", Static).update(Text("SELECTED JOB · " + WIDEN_HINT))
                notes = [n for n in nodes if n.get("dispatch_note")]
                if notes:
                    latest = max(notes, key=lambda n: n.get("dispatch_ts") or 0)
                    section("LATEST NOTE · " + _age(latest.get("dispatch_ts"), now), latest["dispatch_note"])
            if row.get("blocked_reason"):
                section("BLOCKED", row["blocked_reason"], "red")
            related = {}
            for workflow in self._payload.get("workflows") or []:
                links = [("Contracts", workflow.get("contracts_job_id")), ("Frontend", workflow.get("frontend_job_id"))]
                if any(jid == row["id"] for _, jid in links):
                    related.update((jid, label) for label, jid in links if jid and jid != row["id"])
            out.append("\nRELATED JOBS\n", style="dim")
            if not related:
                out.append("none in loaded workflows\n", style="dim")
            for jid, label in related.items():
                out.append(label.ljust(12)).append_text(job_text(jid, 36, explorer=JOB_EXPLORER)).append("\n")
        elif kind == "step":
            field("STEP", row.get("key"))
            field("SEAT", f"#{row['seat']}" if row.get("seat") is not None else "--")
            field("ROLE", row.get("role"))
            field("STATE", row.get("state"), _tone(row.get("state")))
            field("LAST UPDATE", _age(row.get("updated_ts"), now))
            field("ATTEMPT", _count(row.get("attempt")))
            field("REVISIONS", _count(row.get("revisions")))
            dependencies = row.get("depends_on")
            section("DEPENDENCIES", ", ".join(dependencies) if dependencies else "none" if dependencies == [] else "unavailable")
            verdict = row.get("verdict")
            if verdict:
                section("VERDICT", f"{verdict.get('status') or '--'} · {verdict.get('detail') or '--'}")
            if row.get("dispatch_note"):
                section("LATEST NOTE · " + _age(row.get("dispatch_ts"), now), row["dispatch_note"])
            if row.get("failure"):
                section("FAILURE", row["failure"], "red")
        elif kind == "missing":
            out.append("Linked job was not included in this read.\n", style="yellow")
            out.append_text(job_text(row.get("id"), 36, explorer=JOB_EXPLORER))
        else:
            out.append("Jobs without a workflow in the loaded records.")
        if kind in ("job", "workflow") and cell_len(objective) > max(8, panel.content_size.width - 2) * 3:
            section("FULL OBJECTIVE", objective)
        self.query_one("#work-detail", Static).update(out)
