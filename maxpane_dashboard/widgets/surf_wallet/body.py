"""Two mounted views of wallet facts, preserving identity through refreshes."""
from copy import deepcopy

from rich.text import Text
from textual import on
from textual.containers import Grid, Horizontal, ScrollableContainer, Vertical, VerticalScroll
from textual.message import Message
from textual.widgets import DataTable, Static

from maxpane_dashboard.analytics.surf_wallet import summary, usage_signal, usage_text
from maxpane_dashboard.widgets.address import is_copy_click, is_explorer_click
from maxpane_dashboard.widgets.markup_safety import flatten
from maxpane_dashboard.widgets.panels import PanelBase
from maxpane_dashboard.widgets.rowfit import clip
from maxpane_dashboard.widgets.surf.news_hero import NewsHeroCard
from maxpane_dashboard.widgets.surfboard.terminal import fit_prose
from .presentation import artifact_detail, clock, hero_records, insights, literal, name_text, number


class WalletTable(DataTable):
    async def _on_click(self, event):
        action = event.style.meta.get("@click", "")
        if is_copy_click(event) or is_explorer_click(event) or action.startswith("screen.open_wallet_source("):
            event.prevent_default()
            event.stop()
            await self.app.run_action(action)
            return
        await super()._on_click(event)


class WalletInsight(PanelBase):
    def __init__(self, title, **kwargs):
        super().__init__(**kwargs)
        self.TITLE = title

    def compose_body(self):
        with VerticalScroll(classes="wallet-insight-scroll"):
            yield Static(Text("--"), id=f"{self.id}-content", classes="wallet-insight-content")

    def set_content(self, content, title=None):
        self.query_one(f"#{self.id}-content", Static).update(content)
        if title is not None:
            self.query_one(".panel-title", Static).update(Text(title))


class WalletCreated(PanelBase):
    TITLE = "CREATED / ALL KNOWN"

    def compose_body(self):
        yield Static(Text("--"), classes="wallet-empty")
        yield WalletTable(id=f"{self.id.removesuffix('-created')}-assets", cursor_type="row", zebra_stripes=True)


class WalletRecord(PanelBase):
    TITLE = "RECORD / OBSERVED REQUESTS · 30D"

    def compose_body(self):
        yield Static(Text("--"), classes="wallet-empty")
        yield WalletTable(id="wallet-orders", cursor_type="row", zebra_stripes=True)


class WalletDetail(PanelBase):
    TITLE = "SELECTED ARTIFACT"

    def compose_body(self):
        with VerticalScroll(id="wallet-detail-scroll"):
            yield Static(Text("Select a created artifact"), id="wallet-artifact-detail")


class WalletBody(Vertical):
    """The screen dispatches one snapshot; all heroes and panels update together."""

    DEFAULT_CSS = """
    WalletBody { height: 1fr; }
    WalletBody #wallet-viewport { height: 1fr; overflow: auto auto; scrollbar-size: 1 1; }
    WalletBody #wallet-layout { height: 1fr; min-height: 43; min-width: 145; padding: 1 1; }
    WalletBody #wallet-overview, WalletBody #wallet-detail { height: 1fr; }
    WalletBody .wallet-heroes { height: 9; grid-size: 6; grid-columns: 1fr; grid-rows: 9; grid-gutter: 1 1; margin-bottom: 1; }
    WalletBody .wallet-scopes, WalletBody .wallet-coverage { height: 1; color: $text-muted; text-wrap: nowrap; }
    WalletBody .panel-title { height: 1; text-wrap: nowrap; }
    WalletBody DataTable { height: 1fr; min-height: 4; scrollbar-gutter: stable; }
    WalletBody .wallet-empty { height: 1; padding: 0 1; color: $text-muted; }
    WalletBody #wallet-insights { height: 8; margin-bottom: 1; grid-size: 4; grid-columns: 1fr; grid-gutter: 0 1; }
    WalletBody #wallet-insights WalletInsight { height: 8; }
    WalletBody .wallet-insight-scroll { height: 1fr; scrollbar-size: 1 1; }
    WalletBody .wallet-insight-content { height: auto; padding: 0 1; text-wrap: nowrap; }
    WalletBody #wallet-states, WalletBody #wallet-onchain, WalletBody #wallet-payments { border-left: solid $panel; }
    WalletBody #wallet-overview-body { height: 1fr; min-height: 14; }
    WalletBody #wallet-overview-created { width: 2fr; height: 1fr; margin-right: 1; }
    WalletBody #wallet-overview-context { width: 1fr; min-width: 44; border-left: solid $panel; }
    WalletBody #wallet-artifact-path { height: 8; }
    WalletBody #wallet-followups { height: 6; }
    WalletBody #wallet-overview-record { height: 6; }
    WalletBody #wallet-detail-body { height: 1fr; min-height: 27; }
    WalletBody #wallet-detail-left { width: 58%; margin-right: 1; }
    WalletBody #wallet-detail-created { height: 1fr; min-height: 13; }
    WalletBody #wallet-detail-payments { height: 9; padding: 1 0 0 0; }
    WalletBody #wallet-selected { width: 1fr; padding: 0 1; border-left: solid $panel; }
    WalletBody #wallet-detail-scroll { height: 1fr; scrollbar-gutter: stable; }
    WalletBody #wallet-artifact-detail { height: auto; }
    """

    class ViewChanged(Message):
        def __init__(self, view):
            super().__init__()
            self.view = view

    def __init__(self, view_state=None):
        super().__init__()
        self.view_state = view_state if isinstance(view_state, dict) else {}
        self.view = self.view_state.get("view", "overview")
        if self.view not in ("overview", "detail"):
            self.view = "overview"
        self.selected_id = self.view_state.get("selected_id")
        self.snapshot, self.by_id, self.source_links = {}, {}, []
        self._table_payload, self._orders_payload = None, None
        self._ready = self._tables_ready = False
        self._overview_scroll = self._outer_scroll = (0, 0)

    def compose(self):
        empty = summary({}, None)
        with ScrollableContainer(id="wallet-viewport"):
            with Vertical(id="wallet-layout"):
                with Vertical(id="wallet-overview"):
                    yield Grid(*(NewsHeroCard(record) for record in hero_records(empty, "overview")), classes="wallet-heroes")
                    yield Static(Text("Orders 30D · Assets ALL KNOWN · Usage 24H / ALL ACTORS · ETH / BASE / RH"), classes="wallet-scopes")
                    yield Static(Text("Coverage: --"), classes="wallet-coverage")
                    with Grid(id="wallet-insights"):
                        for key, title in (("activity", "REQUEST ACTIVITY / 30D"), ("states", "REQUEST STATUS / 30D"),
                                           ("onchain", "ONCHAIN USE / 24H"), ("payments", "PAYMENTS / 30D")):
                            yield WalletInsight(title, id=f"wallet-{key}")
                    with Horizontal(id="wallet-overview-body"):
                        yield WalletCreated(id="wallet-overview-created")
                        with Vertical(id="wallet-overview-context"):
                            yield WalletInsight("SELECTED / ONCHAIN PATH", id="wallet-artifact-path")
                            yield WalletInsight("ATTENTION / OPEN FOLLOW-UPS", id="wallet-followups")
                    yield WalletRecord(id="wallet-overview-record")
                with Vertical(id="wallet-detail"):
                    yield Grid(*(NewsHeroCard(record) for record in hero_records(empty, "detail")), classes="wallet-heroes")
                    yield Static(Text("Orders 30D · Assets ALL KNOWN · Usage 24H / ALL ACTORS · ETH / BASE / RH"), classes="wallet-scopes")
                    yield Static(Text("Coverage: --"), classes="wallet-coverage")
                    with Horizontal(id="wallet-detail-body"):
                        with Vertical(id="wallet-detail-left"):
                            yield WalletCreated(id="wallet-detail-created")
                            yield WalletInsight("REQUESTS / PAYMENTS · 30D", id="wallet-detail-payments")
                        yield WalletDetail(id="wallet-selected")

    def on_mount(self):
        for view in ("overview", "detail"):
            table = self.query_one(f"#wallet-{view}-assets", DataTable)
            columns = [("TYPE", 9), ("OUTPUT", 20), ("CHAIN", 5)]
            if view == "overview":
                columns.append(("ONCHAIN USE / 24H", 23))
            columns.append(("SIGNAL", 16))
            for label, width in columns:
                table.add_column(label, width=width)
        table = self.query_one("#wallet-orders", DataTable)
        for label, width in (("WHEN UTC", 11), ("ACTION", 18), ("OBJECT", 20), ("PAYMENT", 10), ("RESULT", 28)):
            table.add_column(label, width=width)
        self._ready = True
        self.update_data(wallet_snapshot=self.snapshot)
        self.show_view(self.view)

    def update_data(self, wallet_snapshot=None):
        incoming = wallet_snapshot if isinstance(wallet_snapshot, dict) else {}
        changed_wallet = bool(self.snapshot) and flatten(incoming.get("wallet")).lower() != flatten(self.snapshot.get("wallet")).lower() and "wallet" in incoming
        if changed_wallet:
            self.snapshot = {}
            self.selected_id = None
            self.source_links = []
            self._table_payload = self._orders_payload = None
            self._overview_scroll = self._outer_scroll = (0, 0)
            for card in self.query(NewsHeroCard):
                card.reset_display_values()
        # Retain only observed populations for the same wallet. Successful [] replaces them.
        retained = dict(self.snapshot)
        retained.update(incoming)
        for key in ("orders", "artifacts", "schedules", "payment_totals", "as_of"):
            if incoming.get(key) is None and self.snapshot.get(key) is not None:
                retained[key] = self.snapshot[key]
        self.snapshot = deepcopy(retained)
        if not self._ready:
            return
        metrics = summary(self.snapshot, self.snapshot.get("as_of"))
        for view in ("overview", "detail"):
            for record in hero_records(metrics, view):
                self.query_one(f"#hero-{record.key}", NewsHeroCard).set_record(record)
        contents = insights(metrics)
        usage_source = (self.snapshot.get("sources") or {}).get("usage") or {}
        usage_clock = clock(usage_source.get("observed_at"), time_only=True)
        for key, content in contents.items():
            title = "ONCHAIN USE / 24H" + (f" · {usage_clock}Z" if usage_clock != "--" else "") if key == "onchain" else None
            self.query_one(f"#wallet-{key}", WalletInsight).set_content(content, title=title)
        self.query_one("#wallet-detail-payments", WalletInsight).set_content(contents["payments"])
        coverage = "Coverage: " + " · ".join(flatten(item) for item in metrics["coverage"] or ["--"])
        for widget in self.query(".wallet-coverage"):
            widget.update(literal(clip(coverage, max(30, self.size.width-4))))
            widget.tooltip = literal(coverage)
        artifacts = self.snapshot.get("artifacts")
        self.by_id = {row["id"]: row for row in artifacts or []}
        if artifacts is not None and self.selected_id not in self.by_id:
            self.selected_id = next(iter(self.by_id), None)
        self._tables_ready = False
        if artifacts != self._table_payload or changed_wallet:
            for view in ("overview", "detail"):
                self._fill_artifacts(view, artifacts)
            self._table_payload = deepcopy(artifacts)
        orders = metrics["orders"]
        if orders != self._orders_payload or changed_wallet:
            self._fill_orders(orders)
            self._orders_payload = deepcopy(orders)
        self._population_titles(metrics)
        followups = Text()
        for row in orders or []:
            if row.get("follow_up"):
                followups.append("! ", style="yellow")
                followups.append(literal(clip(flatten(row.get("name")), 24)))
                followups.append(" " + clip(flatten(row.get("outcome")), 15) + "\n")
        self.query_one("#wallet-followups", WalletInsight).set_content(followups if followups else Text("No open follow-ups" if orders is not None else "--"),
            title=f"ATTENTION / {number(metrics['counts'].get('ATTENTION'))} FOLLOW-UPS")
        self._update_detail()
        self.call_after_refresh(self._sync_selection)

    def _fill_artifacts(self, view, artifacts):
        table = self.query_one(f"#wallet-{view}-assets", DataTable)
        table.clear()
        for row in artifacts or []:
            signal = usage_signal(row, self.by_id)
            values = [literal(row.get("kind")), name_text(row, width=20), literal(row.get("chain"))]
            if view == "overview":
                values.append(literal(clip(usage_text(row, self.by_id).split(" / ")[0], 23)))
            values.append(literal(signal, "bright_green" if "ACTIVE" in signal or signal == "FIRST SEEN" else "dim"))
            table.add_row(*values, key=row["id"])
        notice = self.query_one(f"#wallet-{view}-created .wallet-empty", Static)
        notice.display = not artifacts
        notice.update(Text("No created artifacts" if artifacts == [] else "--"))

    def _fill_orders(self, orders):
        table = self.query_one("#wallet-orders", DataTable)
        table.clear()
        for row in orders or []:
            values = (literal(clock(row.get("timestamp"))), literal(clip(flatten(row.get("action")), 18)),
                      fit_prose(row.get("name"), 20, explorer=None)[0],
                      literal(clip(flatten(row.get("payment_state")), 10)), literal(clip(flatten(row.get("outcome")), 28)))
            table.add_row(*values, key=row["id"])
        notice = self.query_one("#wallet-overview-record .wallet-empty", Static)
        notice.display = not orders
        notice.update(Text("No observed requests" if orders == [] else "--"))

    def _population_titles(self, metrics):
        counts = metrics["counts"]
        title = f"CREATED / {number(counts.get('SITES'))} sites + {number(counts.get('CONTRACTS'))} contracts (incl. {number(counts.get('TOKENS'))} tokens)"
        for panel in self.query(WalletCreated):
            panel.query_one(".panel-title", Static).update(Text(title))
        self.query_one("#wallet-overview-record .panel-title", Static).update(Text(f"RECORD / {number(counts.get('REQUESTS'))} observed requests · newest first"))

    def show_view(self, view):
        if view not in ("overview", "detail"):
            raise ValueError(f"Unknown wallet view: {view}")
        self.view = view
        self.view_state["view"] = view
        if not self._ready:
            return
        self._tables_ready = False
        self.query_one("#wallet-overview").display = view == "overview"
        self.query_one("#wallet-detail").display = view == "detail"
        self._update_detail()
        self.post_message(self.ViewChanged(view))
        self.call_after_refresh(self.focus_selection)

    def back(self):
        if self.view != "detail":
            return False
        self.show_view("overview")
        return True

    def _sync_selection(self):
        if self.selected_id in self.by_id:
            row = list(self.by_id).index(self.selected_id)
            for view in ("overview", "detail"):
                self.query_one(f"#wallet-{view}-assets", DataTable).move_cursor(row=row, animate=False)
        self._tables_ready = True

    def focus_selection(self):
        if not self._ready:
            return
        table = self.query_one(f"#wallet-{self.view}-assets", DataTable)
        self._sync_selection()
        table.focus()
        if self.view == "overview":
            table.scroll_to(x=self._overview_scroll[0], y=self._overview_scroll[1], animate=False)
            self.query_one("#wallet-viewport").scroll_to(x=self._outer_scroll[0], y=self._outer_scroll[1], animate=False)

    @on(DataTable.RowHighlighted)
    def highlight_artifact(self, event):
        if not self._tables_ready or event.data_table.id != f"wallet-{self.view}-assets" or not event.data_table.row_count:
            return
        current = event.data_table.coordinate_to_cell_key(event.data_table.cursor_coordinate).row_key.value
        if event.row_key.value != current or current not in self.by_id:
            return
        if self.selected_id != current:
            self.selected_id = current
            self._update_detail()

    @on(DataTable.RowSelected)
    def open_artifact(self, event):
        if self.view != "overview" or event.data_table.id != "wallet-overview-assets" or event.row_key.value not in self.by_id:
            return
        self.selected_id = event.row_key.value
        self._overview_scroll = tuple(event.data_table.scroll_offset)
        self._outer_scroll = tuple(self.query_one("#wallet-viewport").scroll_offset)
        self.show_view("detail")

    def _update_detail(self):
        detail, path, links = artifact_detail(self.by_id.get(self.selected_id), self.by_id, self.snapshot)
        self.source_links = links
        self.view_state["selected_id"] = self.selected_id
        self.query_one("#wallet-artifact-detail", Static).update(detail)
        self.query_one("#wallet-artifact-path", WalletInsight).set_content(path)
