"""Read-only work desk: loaded workflows, jobs and their actual step outcomes."""
from __future__ import annotations

from rich.style import Style
from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal, Vertical, VerticalScroll
from textual.widgets import Input, Static, Tree

from maxpane_dashboard.widgets.address import address_prose, job_text
from maxpane_dashboard.widgets.fmt import fmt_age, hhmm
from maxpane_dashboard.widgets.markup_safety import flatten
from maxpane_dashboard.widgets.panels import PanelBase
from maxpane_dashboard.widgets.rowfit import WIDEN_HINT, cell_len, clip, pad
from maxpane_dashboard.widgets.selection_tree import ClickSelectTree
from ._fmt import JOB_EXPLORER
from ._icons import fit_prose, post_preview
from .news_hero import HeroRecord, NewsHeroCard, _count, _number
from .pool4_hero import Pool4HeroCard

_BUILD = {"implement", "integrate", "test", "tests"}
_TERMINAL = {"completed", "cancelled", "failed", "superseded"}
_FILTERS = ("open", "blocked", "build", "review")


def _tone(state, accent):
    if state in ("blocked", "failed", "rejected"):
        return "red"
    if state in ("accepted", "completed"):
        return accent
    if state in ("working", "executing", "pass"):
        return "green"
    return "yellow" if state in ("queued", "waiting", "pending") else "grey62"


def _age(timestamp, now):
    stamp, now = _number(timestamp), _number(now)
    return fmt_age(max(0, now - stamp)) + " ago" if stamp is not None and now is not None else "--"


def _project_job_ids(project, workflows):
    ids = dict.fromkeys(project.get("job_ids", []))
    for workflow in workflows or []:
        if workflow["id"] in project.get("workflow_ids", []):
            ids.update(dict.fromkeys(workflow[key] for key in ("contracts_job_id", "frontend_job_id") if workflow.get(key)))
    return list(ids)


class _WorkHeroCard(Pool4HeroCard):
    # Source coverage remains in the tooltip; the outer footer stays empty.
    _footer = NewsHeroCard._footer

    def _frame_style(self):
        frame = super()._frame_style()
        if self.data.key == "work-blocked" and self.data.accent:
            frame += Style(color="red")
        return frame


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
            yield _WorkHeroCard(HeroRecord("work-" + key, title, heading, "", subtitle=footer,
                                          digits="--", state="unavailable", accent=False))

    def update_data(self, *, surf_work=None, **_kwargs):
        payload = surf_work if isinstance(surf_work, dict) else {}
        summary = payload.get("summary") or {}
        state = payload.get("state", "unavailable")
        for key, title, heading, footer in self.CARDS:
            count = _count(summary.get(key)) if state != "unavailable" else "--"
            record = HeroRecord("work-" + key, title, heading, "", subtitle=footer, digits=count,
                                state=state, read_ts=_number(payload.get("read_ts")),
                                accent=state == "ok" and count not in ("--", "0"))
            self.query_one(f"#hero-work-{key}", _WorkHeroCard).set_record(record)


class _WorkTree(ClickSelectTree):
    BINDINGS = [Binding("left", "fold", show=False), Binding("right", "unfold", show=False)]

    async def _on_click(self, event):
        line = event.style.meta.get("line")
        unchanged = isinstance(line, int) and line == self.cursor_line
        await super()._on_click(event)
        if unchanged and self.cursor_node and not (event.style.meta.get("toggle") or event.style.meta.get("@click")):
            self.post_message(self.NodeHighlighted(self.cursor_node))

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
        return Text.assemble((prefix, base_style + Style(meta={"toggle": True})), label)


class _WorkTreePanel(PanelBase):
    TITLE = "WORKFLOWS"
    def compose_body(self):
        yield Static(Text(""), id="work-coverage")
        yield Input(placeholder="find project, workflow, job or seat", id="work-find")
        tree = _WorkTree("work", id="work-tree")
        tree.show_root = False
        tree.auto_expand = False
        yield tree


class _WorkJobsPanel(PanelBase):
    TITLE = "JOBS"
    def compose_body(self):
        tree = _WorkTree("jobs", id="work-jobs-tree")
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
    SurfWorkBody > #work-navigation { width: 1fr; height: 1fr; min-height: 16; margin-right: 1; }
    SurfWorkBody #work-tree-panel { height: 1fr; min-height: 6; margin-bottom: 1; }
    SurfWorkBody #work-jobs-panel { height: 2fr; min-height: 8; }
    SurfWorkBody > _WorkDetailPanel { width: 1fr; height: 1fr; min-height: 16; }
    SurfWorkBody PanelBase { border: none; background: $background; padding: 0 1; }
    SurfWorkBody .panel-title { height: 1; text-wrap: nowrap; }
    SurfWorkBody #work-coverage { height: 1; color: $text-muted; text-wrap: nowrap; }
    SurfWorkBody #work-find { display: none; height: 3; }
    SurfWorkBody _WorkTree { height: 1fr; min-height: 1; padding: 0; background: $background;
        overflow-x: hidden; overflow-y: auto; scrollbar-gutter: stable; }
    SurfWorkBody #work-detail-scroll { height: 1fr; min-height: 8; overflow-x: hidden;
        overflow-y: auto; scrollbar-gutter: stable; }
    SurfWorkBody #work-detail { height: auto; width: 1fr; }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._payload = {}
        self._selected = None
        self._filter = "open"
        self._search = ""
        self._work_nodes = {}
        self._entries = {}
        self._expansion = {}
        self._tree_search = False

    def compose(self):
        with Vertical(id="work-navigation"):
            yield _WorkTreePanel(id="work-tree-panel")
            yield _WorkJobsPanel(id="work-jobs-panel")
        yield _WorkDetailPanel(id="work-detail-panel")

    def update_data(self, *, surf_work=None, **_kwargs):
        self._payload = surf_work if isinstance(surf_work, dict) else {}
        self._rebuild()

    def focus_tree(self):
        selected = self._work_nodes.get(self._selected)
        (selected.tree if selected else self.query_one("#work-tree", Tree)).focus()

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
        self._filter = _FILTERS[(_FILTERS.index(self._filter) + 1) % len(_FILTERS)]
        self._rebuild()

    def on_click(self, event):
        choice = event.style.meta.get("work_filter")
        if choice in _FILTERS:
            self._filter = choice
            self._rebuild()
            self.focus_tree()
            event.stop()

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
        if self._filter != "blocked" and (job.get("state") == "blocked" or workflow_blocked):
            return False
        if self._filter == "blocked" and job.get("state") != "blocked" and not workflow_blocked:
            return False
        if self._filter in ("build", "review"):
            roles = _BUILD if self._filter == "build" else {"review"}
            if job.get("state") != "executing" or not any(n.get("state") == "working" and n.get("role") in roles for n in nodes):
                return False
        haystack = flatten(" ".join(str(job.get(k) or "") for k in ("id", "objective", "template")))
        haystack += " " + " ".join(f"{n.get('key')} {n.get('seat')} {n.get('role')}" for n in nodes)
        return not self._search or workflow_match or self._search in haystack.casefold()

    def _rebuild(self):
        tree, jobs_tree = self.query_one("#work-tree", Tree), self.query_one("#work-jobs-tree", Tree)
        if not self._tree_search:
            self._expansion.update((key, node.is_expanded) for key, node in self._work_nodes.items() if node.allow_expand)
        self._tree_search = bool(self._search)
        selected = self._selected
        tree.clear()
        jobs_tree.clear()
        self._work_nodes, self._entries = {}, {}
        jobs = self._payload.get("jobs")
        workflows = self._payload.get("workflows")
        projects = self._payload.get("projects") or []
        by_id = {j["id"]: j for j in jobs or []}
        flow_by_id = {w["id"]: w for w in workflows or []}
        project_flows = {wid for project in projects for wid in project.get("workflow_ids", [])}

        def add(parent, key, kind, row, label, children=False, suffix="", expanded=True):
            label, suffix = flatten(label), flatten(suffix)
            entry = (key, kind, row, label, suffix)
            state = row.get("state", row.get("status"))
            tone = _tone(state, self.app.get_css_variables()["accent"])
            node = parent.add(Text(label + ("  " + suffix if suffix else ""), style=tone),
                              data=entry, allow_expand=children,
                              expand=bool(self._search) or self._expansion.get(key, expanded))
            self._work_nodes[key], self._entries[key] = node, entry
            return node

        def matches_row(row):
            return self._search in flatten(f"{row['id']} {row.get('objective') or ''}").casefold()

        context_matches = {jid for project in projects if matches_row(project)
                           for jid in _project_job_ids(project, workflows)}
        context_matches.update(workflow[key] for workflow in workflows or [] if matches_row(workflow)
                               for key in ("contracts_job_id", "frontend_job_id") if workflow.get(key))
        visible_jobs = {job["id"] for job in jobs or []
                        if self._matches(job, workflow_match=job["id"] in context_matches)}
        missing_jobs = set()

        def flow_view(workflow, parent_match=False):
            linked = {workflow[key] for key in ("contracts_job_id", "frontend_job_id") if workflow.get(key)}
            blocked = workflow.get("status") == "blocked"
            if blocked and self._filter != "blocked":
                return False
            state_match = self._filter == "open" and not blocked or self._filter == "blocked" and blocked
            show = bool(linked & visible_jobs) or (parent_match or matches_row(workflow)) and state_match
            if show and state_match:
                missing_jobs.update(linked - by_id.keys())
            return show

        def add_flow(parent, workflow):
            key = "workflow:" + workflow["id"]
            if key not in self._entries:
                add(parent, key, "workflow", workflow, workflow.get("objective") or workflow["id"],
                    suffix=workflow.get("status") or "unknown")

        for project in sorted(projects, key=lambda p: not p.get("active_job_ids")):
            match = matches_row(project)
            flows = [flow_by_id[wid] for wid in project.get("workflow_ids", [])
                     if wid in flow_by_id and flow_view(flow_by_id[wid], match)]
            missing_flows = [wid for wid in project.get("workflow_ids", []) if wid not in flow_by_id
                             and self._filter == "open" and (match or self._search in wid.casefold())]
            project_jobs = set(_project_job_ids(project, workflows))
            if not flows and not missing_flows and not project_jobs & visible_jobs and not (match and self._filter == "open"):
                continue
            parent = add(tree.root, "project:" + project["id"], "project", project,
                         project.get("objective") or project["id"], bool(flows or missing_flows), suffix="project")
            for workflow in flows:
                add_flow(parent, workflow)
            for wid in missing_flows:
                if "missing-workflow:" + wid not in self._entries:
                    add(parent, "missing-workflow:" + wid, "missing workflow", {"id": wid}, wid, suffix="workflow not loaded")
            if self._filter == "open" and match:
                missing_jobs.update(project_jobs - by_id.keys())

        for workflow in sorted(workflows or [], key=lambda w: (w.get("status") == "blocked", -(w.get("created_ts") or 0))):
            if workflow["id"] not in project_flows and flow_view(workflow):
                add_flow(tree.root, workflow)
        for job in sorted((j for j in jobs or [] if j["id"] in visible_jobs),
                          key=lambda j: (j.get("state") != "executing", -(j.get("updated_ts") or j.get("created_ts") or 0))):
            nodes = job.get("nodes") or []
            branch = add(jobs_tree.root, "job:" + job["id"], "job", job,
                         job.get("objective") or job["id"], bool(nodes), suffix=job.get("state") or "unknown",
                         expanded=job.get("state") == "executing")
            for step in nodes:
                seat = f"#{step['seat']}" if step.get("seat") is not None else "seat --"
                add(branch, f"step:{job['id']}:{step['key']}", "step", step, step['key'],
                    suffix=f"{seat} {step.get('role') or '--'} {step.get('state') or 'unknown'}")
        for jid in sorted(missing_jobs):
            add(jobs_tree.root, "missing:" + jid, "missing", {"id": jid}, jid + " · job not loaded")
        for target, noun in ((tree, "workflows"), (jobs_tree, "jobs")):
            if not target.root.children:
                unavailable = jobs is None or workflows is None
                target.root.add_leaf(Text("" if unavailable else "No matching " + noun if self._search or self._filter != "open"
                                          else "No " + noun + " loaded", style="dim"))
        if selected not in self._entries:
            def newest(rows):
                return sorted(rows, key=lambda row: (row.get("updated_ts") or row.get("created_ts") or 0,
                                                     row.get("created_ts") or 0, row["id"]), reverse=True)
            visible = newest(j for j in jobs or [] if "job:" + j["id"] in self._entries)
            active = [j for j in visible if j.get("state") == "executing"]
            flows = newest(w for w in workflows or [] if "workflow:" + w["id"] in self._entries and w.get("status") not in _TERMINAL)
            if active:
                selected = "job:" + active[0]["id"]
            elif flows:
                selected = "workflow:" + flows[0]["id"]
            else:
                selected = "job:" + visible[0]["id"] if visible else next(iter(self._entries), None)
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
        tree = self._work_nodes[selected].tree
        if isinstance(self.app.focused, _WorkTree):
            self.screen.set_focus(tree, scroll_visible=False)
        tree._tree_lines  # Lay out node line numbers before moving the cursor.
        node = self._work_nodes[selected]
        self._selected = selected
        if node._line >= 0:
            tree.move_cursor(node)
        self._detail()

    def _titles(self):
        tree = self.query_one("#work-tree", _WorkTree)
        clipped = any(cell_len(node.label.plain) > tree.label_width(node) - (2 if node.allow_expand else 0)
                      for node in self._work_nodes.values() if node.tree is tree)
        state = self._payload.get("state", "unavailable")
        title = Text("WORKFLOWS · ")
        for index, choice in enumerate(_FILTERS):
            if index: title.append(" · ")
            active = choice == self._filter
            title.append(choice.title(), style=Style(color=self.app.get_css_variables()["accent"] if active else None,
                         bold=active, dim=not active, meta={"work_filter": choice}))
        panel = self.query_one("#work-tree-panel", PanelBase)
        room = max(1, panel.content_size.width - 2)
        clipped |= title.cell_len > room
        title.truncate(max(1, room - (len(WIDEN_HINT) + 2 if clipped else 0)), overflow="ellipsis")
        if clipped: title.append(" · " + WIDEN_HINT)
        panel.query_one(".panel-title", Static).update(title)
        jobs_tree = self.query_one("#work-jobs-tree", _WorkTree)
        shown = sum(entry[1] == 'job' for entry in self._entries.values()) if self._payload.get('jobs') is not None else None
        jobs_title = f"JOBS · {_count(shown)} shown"
        if any(cell_len(node.label.plain) > jobs_tree.label_width(node) - (2 if node.allow_expand else 0)
               for node in self._work_nodes.values() if node.tree is jobs_tree):
            jobs_title += " · " + WIDEN_HINT
        self.query_one("#work-jobs-panel .panel-title", Static).update(Text(jobs_title))
        coverage = f"{_count(self._payload.get('jobs_loaded'))} jobs · {_count(self._payload.get('workflows_loaded'))} workflows loaded · {hhmm(self._payload.get('read_ts'), unknown='--:--')}"
        if self._payload.get("partial"):
            coverage += " · partial"
        if state == "unavailable":
            coverage = ""
        self.query_one("#work-coverage", Static).update(fit_prose(coverage, max(1, tree.content_size.width)))

    @on(Tree.NodeHighlighted, "#work-tree, #work-jobs-tree")
    def _highlight(self, event):
        if event.control.has_focus and event.node.data and self._work_nodes.get(event.node.data[0]) is event.node:
            if self._selected != event.node.data[0]:
                self.query_one("#work-detail-scroll", VerticalScroll).scroll_home(animate=False)
            self._selected = event.node.data[0]
            self._detail()

    @on(Tree.NodeSelected, "#work-tree, #work-jobs-tree")
    def _open(self, event):
        if event.node.data and self._work_nodes.get(event.node.data[0]) is event.node:
            self._selected = event.node.data[0]
            self._detail()
            if event.node.data[1] in ("project", "workflow", "group") and event.node.allow_expand:
                event.node.toggle()
            else:
                self.query_one("#work-detail-scroll", VerticalScroll).focus()

    def _detail(self):
        entry = self._entries.get(self._selected)
        panel = self.query_one("#work-detail-panel", PanelBase)
        if entry is None:
            panel.query_one(".panel-title", Static).update(Text("SELECTED WORK"))
            self.query_one("#work-detail", Static).update(Text("" if self._payload.get("state", "unavailable") == "unavailable" else "Select a workflow, job or step.", style="dim"))
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
        accent = self.app.get_css_variables()["accent"]
        if kind in ("project", "job", "workflow"):
            objective = flatten(row.get("objective")) or "—"
            preview = post_preview(objective, max(8, panel.content_size.width - 2), Style())
            out.append_text(Text("\n").join(preview)).append("\n\n")
            if kind == "job":
                out.append("JOB            ", style="dim").append_text(job_text(row.get("id"), 36, explorer=JOB_EXPLORER)).append("\n")
            if kind != "project":
                field("STATE", row.get("state", row.get("status")), _tone(row.get("state", row.get("status")), accent))
                field("CREATED", _age(row.get("created_ts"), now))
                field("LAST UPDATE", _age(row.get("updated_ts"), now))
        if kind == "project":
            jobs = {j["id"]: j for j in self._payload.get("jobs") or []}
            out.append("PROJECT JOBS\n", style="dim")
            for jid in _project_job_ids(row, self._payload.get("workflows")):
                out.append_text(job_text(jid, 36, explorer=JOB_EXPLORER))
                state = (jobs[jid].get("state") or "unknown") if jid in jobs else "not loaded"
                out.append(" · " + flatten(state) + "\n", style=_tone(state, accent))
        elif kind == "workflow":
            jobs = {j["id"]: j for j in self._payload.get("jobs") or []}
            out.append("\nLINKED JOBS\n", style="dim")
            for label, key in (("Contracts", "contracts_job_id"), ("Frontend", "frontend_job_id")):
                jid = row.get(key)
                out.append(label.ljust(12))
                out.append_text(job_text(jid, 36, explorer=JOB_EXPLORER))
                out.append(" · " + (flatten(jobs[jid].get("state")) or "unknown" if jid in jobs else "not loaded" if jid else "not assigned") + "\n")
            if row.get("waiting_for_hosting"):
                section("WAITING", "Hosting", "yellow")
            if row.get("failure"):
                section("FAILURE", row["failure"], "red")
        elif kind == "job":
            field("TEMPLATE", row.get("template"))
            nodes = row.get("nodes")
            out.append("\nSTEPS\n", style="dim")
            if nodes is None:
                out.append("—\n", style="dim")
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
                    out.append(pad(clip(state, 10), 10), style=_tone(step.get("state"), accent))
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
            for project in self._payload.get("projects") or []:
                ids = _project_job_ids(project, self._payload.get("workflows"))
                if row["id"] in ids:
                    related.update((jid, "Project") for jid in ids if jid != row["id"])
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
            field("STATE", row.get("state"), _tone(row.get("state"), accent))
            field("LAST UPDATE", _age(row.get("updated_ts"), now))
            field("ATTEMPT", _count(row.get("attempt")))
            field("REVISIONS", _count(row.get("revisions")))
            dependencies = row.get("depends_on")
            section("DEPENDENCIES", ", ".join(dependencies) if dependencies else "none" if dependencies == [] else "—")
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
        elif kind == "missing workflow":
            out.append("Linked workflow was not included in this read.\n", style="yellow")
            field("WORKFLOW", row.get("id"))
        else:
            out.append("Jobs without a workflow in the loaded records.")
        if kind in ("project", "job", "workflow") and cell_len(objective) > max(8, panel.content_size.width - 2) * 3:
            section("FULL OBJECTIVE", objective)
        self.query_one("#work-detail", Static).update(out)
