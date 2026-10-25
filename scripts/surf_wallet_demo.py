"""Standalone WALLET / SWARM A/B preview; every record is fictional.

Run: .venv/bin/python scripts/surf_wallet_demo.py
Export: add --export /tmp/surf-wallet.svg --size 149x45 --view overview
Detail: add --view detail --select token-credits
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.text import Text
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal, ScrollableContainer, Vertical, VerticalScroll
from textual.widgets import DataTable, Static

from maxpane_dashboard.themes import THEMES
from maxpane_dashboard.widgets.markup_safety import flatten
from maxpane_dashboard.widgets.panels import PanelBase
from maxpane_dashboard.widgets.sparkline_common import build_sparkline
from maxpane_dashboard.widgets.surf.news_hero import HeroRecord, NewsHeroCard
from scripts.surf_start_demo import parse_size


MOCK_TIME = datetime(2026, 10, 25, 12, tzinfo=timezone.utc)
SCOPES = "Orders 30D  ·  Assets ALL KNOWN  ·  Usage 24H / ALL ACTORS  ·  ETH / BASE / RH"
COVERAGE = "Coverage: orders latest 100 · Intake partial · usage rules 6/18 (2/4 tokens) · complete windows 4/6"


def mock_snapshot():
    """Complete synthetic populations; no config, cache, clock or live reads."""
    actions = (["job.open"] * 32 + ["job.continue"] * 10 + ["workflow.open"] * 12
               + ["launch.open"] * 8 + ["oracle.request"] * 16
               + ["schedule.create"] * 2 + ["schedule.topup"] * 4)
    orders = []
    default_outcomes = {"job.open": "delivered", "job.continue": "delivered",
                        "workflow.open": "shipped", "launch.open": "deployed",
                        "oracle.request": "attested", "schedule.create": "active",
                        "schedule.topup": "runs added"}
    for i, action in enumerate(actions):
        settled = i not in range(36, 42)
        amount = Decimal("0.5") if settled else Decimal(0)
        if i >= 78:
            amount = (Decimal(4), Decimal(4), Decimal(4), Decimal(4), Decimal(5), Decimal("5.5"))[i - 78]
        orders.append(dict(id=f"demo-order-{i + 1:03}", action=action, name=f"Demo request {i + 1}",
                           timestamp=MOCK_TIME.timestamp() - 172800 - i * 27800,
                           payment_state="settled" if settled else "failed", paid_imd=amount,
                           refund_imd=Decimal("0.5") if i in (20, 21) else Decimal(0),
                           outcome=default_outcomes[action] if settled else "not admitted",
                           in_flight=i in (0, 32, 43, 55, 63), follow_up=i in (1, 2, 42, 79)))
    for i in (0, 32, 43):
        orders[i]["outcome"] = "working"
    for i in (1, 42):
        orders[i]["outcome"] = "blocked"
    for i in (2, 56, 64):
        orders[i]["outcome"] = "failed"
    orders[55]["outcome"] = "review"
    orders[63]["outcome"] = "pending"
    orders[79]["outcome"] = "paused"
    for i, name, when in (
        (32, "Atlas v2", "10-25 11:42"), (62, "Check release", "10-25 10:18"),
        (54, "Harbor", "10-25 09:45"), (42, "Atlas site", "10-24 19:10"),
        (80, "Daily check", "10-24 18:30"), (36, "New request", "10-24 16:30"),
        (78, "Daily report", "10-24 15:10"),
    ):
        orders[i].update(name=name, timestamp=datetime.strptime("2026-" + when, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc).timestamp())

    def usage(identity, count, actors, unit, *, complete=True, first_seen=False):
        return dict(count=count, actors=actors, unit=unit, complete=complete,
                    first_seen=first_seen, rule=f"{unit}@demo-v1", evidence=f"<demo-{identity}-receipt>",
                    latest="10-25 11:20 UTC" if first_seen else "10-25 11:32 UTC" if count else "--")

    def artifact(identity, kind, name, chain, order, *, linked=None, checked=True, activity=None):
        return dict(id=identity, kind=kind, name=name, chain=chain, order_id=orders[order]["id"],
                    project=f"demo-project-{identity}", linked_id=linked, binding_checked=checked,
                    usage=activity, version="demo-v1")

    registry = artifact("contract-registry", "CONTRACT", "Atlas Registry", "BASE", 44,
                        activity=usage("registry", 27, 9, "registrations"))
    vault = artifact("contract-vault", "CONTRACT", "Harbor Vault", "ETH", 54,
                     activity=usage("vault", 0, 0, "deposits"))
    credits = artifact("token-credits", "TOKEN", "Harbor Credits", "BASE", 58,
                       activity=usage("credits", 4, 3, "redemptions", first_seen=True))
    access = artifact("token-access", "TOKEN", "Signal Access", "RH", 57)
    assets = [
        artifact("site-atlas", "SITE", "Atlas portal", "BASE", 44, linked=registry["id"]),
        artifact("site-harbor", "SITE", "Harbor portal", "ETH", 45, linked=vault["id"]),
        registry, vault, credits, access,
        artifact("site-static", "SITE", "Cedar handbook", "--", 3),
        artifact("site-unresolved", "SITE", "Signal portal", "RH", 4, checked=False),
    ]
    for i in range(1, 13):
        activity = (usage("claims", 3, 2, "claims") if i == 1 else
                    usage("entries", 2, 1, "entries", complete=False) if i == 2 else None)
        assets.append(artifact(f"contract-utility-{i}", "CONTRACT", f"Utility module {i}",
                               ("BASE", "ETH", "RH")[(i - 1) % 3], (58, 54, 57)[(i - 1) % 3], activity=activity))
    assets += [artifact("token-voucher", "TOKEN", "Cedar Voucher", "ETH", 54,
                        activity=usage("voucher", 0, 0, "redemptions", complete=False)),
               artifact("token-pass", "TOKEN", "Atlas Pass", "BASE", 58)]
    for i in range(1, 7):
        assets.append(artifact(f"site-utility-{i}", "SITE", f"Utility portal {i}",
                               ("BASE", "ETH", "RH")[(i - 1) % 3], 45 + i,
                               linked=f"contract-utility-{i}"))
    return dict(orders=sorted(orders, key=lambda row: -row["timestamp"]), artifacts=assets)


def usage_source(artifact, by_id):
    """A linked site shares its contract's evidence; it creates no extra event."""
    if artifact["kind"] != "SITE":
        return artifact
    return by_id.get(artifact["linked_id"])


def usage_signal(artifact, by_id):
    source = usage_source(artifact, by_id)
    if source is None:
        return "NO ONCHAIN LINK" if artifact["binding_checked"] else "NO DATA"
    usage = source["usage"]
    if not usage or usage["count"] is None or (usage["count"] == 0 and not usage["complete"]):
        return "NO DATA"
    signal = "QUIET" if usage["count"] == 0 else "FIRST SEEN" if usage["first_seen"] else "ACTIVE"
    if artifact["kind"] == "SITE":
        return "LINKED QUIET" if signal == "QUIET" else "LINKED ACTIVE"
    return signal


def usage_text(artifact, by_id):
    if usage_signal(artifact, by_id) in ("NO DATA", "NO ONCHAIN LINK"):
        return "--"
    value = usage_source(artifact, by_id)["usage"]
    text = ("" if value["complete"] else ">=") + f"{value['count']} {value['unit']}"
    if value["count"] and value["actors"] is not None:
        text += f" / {value['actors']} addresses"
    return text


def hero_records(snapshot, view):
    orders, assets = snapshot["orders"], snapshot["artifacts"]
    counts = Counter(row["action"] for row in orders)
    specs = (
        ("requests", "REQUESTS", "ORDERS", "paid 62.5 IMD", len(orders), "paid + attempts"),
        ("jobs", "JOBS", "REQUESTS", "all: 5 in flight", counts["job.open"] + counts["job.continue"], "32 new / 10 cont"),
        ("workflows", "WORKFLOWS", "REQUESTS", "10 sites, 8 linked", counts["workflow.open"], "10 shipped"),
        ("launches", "LAUNCHES", "REQUESTS", "18 ctr / 4 tokens", counts["launch.open"], "6 deployed"),
        ("oracles", "ORACLES", "REQUESTS", "all: 4 follow-ups", counts["oracle.request"], "14 attested"),
        ("schedules", "SCHEDULES", "REQUESTS", "2 new / 4 topups", counts["schedule.create"] + counts["schedule.topup"], "not run count"),
        ("sites", "SITES", "PROJECTS", "ALL KNOWN", sum(a["kind"] == "SITE" for a in assets), "8 linked"),
        ("contracts", "CONTRACTS", "DEPLOYED", "6 usage rules", sum(a["kind"] != "SITE" for a in assets), "incl. 4 tokens"),
        ("tokens", "TOKENS", "DEPLOYED", "ALL KNOWN", sum(a["kind"] == "TOKEN" for a in assets), "in contracts"),
        ("inflight", "IN FLIGHT", "REQUESTS", "excludes blocked", sum(r["in_flight"] for r in orders), "work running"),
        ("paid", "PAID", "IMD", "78 settled", sum(r["paid_imd"] for r in orders), "refunds 1.0 IMD"),
        ("attention", "ATTENTION", "REQUESTS", "follow-ups", sum(r["follow_up"] for r in orders), "2 blocked + 2"),
    )
    indices = range(6) if view == "overview" else (0, 6, 7, 8, 10, 11)
    return tuple(HeroRecord(f"{view}-{key}", title, heading, footer, digits=str(value), subtitle=subtitle,
                            read_ts=MOCK_TIME.timestamp())
                 for key, title, heading, footer, value, subtitle in (specs[i] for i in indices))


def literal(value, style=""):
    return Text(flatten(str(value)), style=style)


def wallet_metrics(snapshot):
    """Observed requests and contract identities; linked sites never add usage."""
    orders, assets = snapshot["orders"], snapshot["artifacts"]
    by_id = {a["id"]: a for a in assets}
    daily = [0] * 30
    start = MOCK_TIME.timestamp() - 30 * 86400
    states = dict.fromkeys(("Completed", "In flight", "Exceptions", "Not admitted"), 0)
    for order in orders:
        day = int((order["timestamp"] - start) // 86400)
        if 0 <= day < 30:
            daily[day] += 1
        state = ("Not admitted" if order["payment_state"] != "settled" else
                 "In flight" if order["in_flight"] else
                 "Exceptions" if order["outcome"] in ("blocked", "failed", "paused") else "Completed")
        states[state] += 1
    signals = dict.fromkeys(("Active", "Quiet", "Unknown"), 0)
    for artifact in assets:
        if artifact["kind"] == "SITE":
            continue
        signal = usage_signal(artifact, by_id)
        signals["Quiet" if signal == "QUIET" else "Unknown" if signal == "NO DATA" else "Active"] += 1
    paid = sum((r["paid_imd"] for r in orders), Decimal(0))
    refunded = sum((r["refund_imd"] for r in orders), Decimal(0))
    rules = [a["usage"] for a in assets if a["kind"] != "SITE" and a["usage"]]
    return dict(daily=daily, states=states, signals=signals, paid=paid, refunded=refunded,
                rules=len(rules), complete=sum(u["complete"] for u in rules),
                net_paid=paid - refunded, settled=sum(r["payment_state"] == "settled" for r in orders))


def meter(value, total, width=12, color="bright_green"):
    filled = round(width * value / total) if total else 0
    return Text.assemble(("█" * filled, color), ("░" * (width - filled), "dim"))


def insight_texts(snapshot):
    metrics = wallet_metrics(snapshot)
    total = len(snapshot["orders"])
    activity = Text(f"{total} observed requests\n", style="bold")
    activity.append(build_sparkline(metrics["daily"], width=30) + "\n", style="bright_green")
    activity.append("09-25 → 10-25 UTC\n", style="dim")
    activity.append(f"Peak {max(metrics['daily'])}/day · last 24h {metrics['daily'][-1]}\n")
    activity.append("Each bar = 24 hours\nSampled request history", style="dim")
    states = Text()
    for label, count in metrics["states"].items():
        states.append(f"{label:13}")
        states.append(meter(count, total, color="yellow" if label == "Exceptions" else "bright_green"))
        states.append(f" {count:2}\n")
    states.append("4 open follow-ups\nMutually exclusive states", style="dim")
    onchain = Text()
    for label, count in metrics["signals"].items():
        onchain.append(f"{label:9}")
        onchain.append(meter(count, sum(metrics["signals"].values()), color="dim" if label == "Unknown" else "bright_green"))
        onchain.append(f" {count:2}\n")
    contracts = sum(metrics["signals"].values())
    onchain.append("18 contracts incl. 4 tokens\n", style="dim")
    onchain.append(f"{metrics['rules']}/{contracts} rules   ")
    onchain.append(meter(metrics["rules"], contracts))
    onchain.append(f"\n{metrics['complete']}/{metrics['rules']} complete ")
    onchain.append(meter(metrics["complete"], metrics["rules"]))
    payments = Text(f"Paid       {metrics['paid']:>5} IMD\nRefunded   {metrics['refunded']:>5} IMD\n")
    payments.append(f"Net paid   {metrics['net_paid']:>5} IMD\n", style="bold")
    payments.append(meter(metrics["settled"], total, width=28))
    payments.append(f"\n{metrics['settled']} settled / {total - metrics['settled']} unsettled\n")
    payments.append("30D · refunds counted separately", style="dim")
    return dict(activity=activity, **{"request-states": states}, onchain=onchain, payments=payments)


class InsightPanel(PanelBase):
    """A small diagram, sparkline or meter panel using the shared panel frame."""

    def __init__(self, title, content, **kwargs):
        super().__init__(**kwargs)
        self.TITLE, self.content = title, content

    def compose_body(self):
        yield Static(self.content, id=f"{self.id}-content", classes="insight-content")


class CreatedPanel(PanelBase):
    TITLE = "CREATED / 28 · 10 sites + 18 contracts (incl. 4 tokens)"

    def compose_body(self):
        yield DataTable(id=f"{self.id.removesuffix('-created')}-assets", cursor_type="row", zebra_stripes=True)


class RecordPanel(PanelBase):
    TITLE = "RECORD / 84 observed requests · newest first"

    def compose_body(self):
        yield DataTable(id="orders", cursor_type="row", zebra_stripes=True)


class DetailPanel(PanelBase):
    TITLE = "SELECTED ARTIFACT"

    def compose_body(self):
        with VerticalScroll(id="detail-scroll"):
            yield Static(Text(), id="artifact-detail")


class SurfWalletDemo(App):
    TITLE = "WALLET / SWARM · DEMO DATA"
    CSS_PATH = Path(__file__).resolve().parent.parent / "maxpane_dashboard/themes/minimal.tcss"
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [Binding("q", "quit", show=False), Binding("escape", "back", show=False)]
    CSS = """
    Screen { background: $background; color: $text; }
    #demo-title, #demo-footer { height: 1; padding: 0 1; background: $surface; color: $text-muted; }
    #demo-title { text-align: center; }
    #viewport { height: 1fr; overflow: auto auto; scrollbar-size: 1 1; }
    #layout { height: 1fr; min-height: 43; min-width: 145; padding: 1 1; }
    #overview, #detail { height: 1fr; }
    .heroes { grid-size: 6; grid-columns: 1fr; grid-rows: 9; grid-gutter: 1 1; margin-bottom: 1; }
    #overview-heroes, #detail-heroes { height: 9; }
    .scopes { height: 1; color: $text-muted; }
    .coverage { height: 1; color: $text-muted; }
    .panel-title { height: 1; text-wrap: nowrap; }
    DataTable { height: 1fr; min-height: 4; scrollbar-gutter: stable; }
    #insights { height: 8; margin-bottom: 1; grid-size: 4; grid-columns: 1fr; grid-gutter: 0 1; }
    #insights InsightPanel { height: 8; }
    .insight-content { height: auto; padding: 0 1; text-wrap: nowrap; }
    #request-states, #onchain, #payments { border-left: solid $panel; }
    #overview-body { height: 1fr; min-height: 14; }
    #overview-created { width: 2fr; height: 1fr; margin-right: 1; }
    #overview-context { width: 1fr; min-width: 44; border-left: solid $panel; }
    #artifact-path { height: 8; }
    #followups { height: 6; }
    #overview-record { height: 6; }
    #detail-body { height: 1fr; min-height: 27; }
    #detail-left { width: 58%; margin-right: 1; }
    #detail-created { height: 1fr; min-height: 13; }
    #detail-context-panel { height: 9; padding: 1 0 0 0; }
    #selected-panel { width: 1fr; padding: 0 1; border-left: solid $panel; }
    #detail-scroll { height: 1fr; scrollbar-gutter: stable; }
    #artifact-detail { height: auto; }
    """

    def __init__(self, view="overview", selected_id="site-atlas"):
        super().__init__()
        self.snapshot = mock_snapshot()
        self.by_id = {a["id"]: a for a in self.snapshot["artifacts"]}
        if selected_id not in self.by_id:
            raise ValueError(f"unknown demo artifact: {selected_id}")
        if view not in ("overview", "detail"):
            raise ValueError(f"unknown demo view: {view}")
        self.view, self.selected_id = view, selected_id
        self._tables_ready = False
        self._overview_scroll = (0, 0)
        self._outer_scroll = (0, 0)
        self.register_theme(THEMES["matrix"])
        self.theme = "matrix"

    def compose(self) -> ComposeResult:
        insights = insight_texts(self.snapshot)
        followups = Text()
        for r in self.snapshot["orders"]:
            if r["follow_up"]:
                followups.append(f"! {flatten(r['name']):24} ", style="yellow")
                followups.append(flatten(r["outcome"]) + "\n")
        yield Static(Text("WALLET / SWARM · <demo-wallet> · DEMO DATA · 2026-10-25 12:00 UTC"), id="demo-title")
        with ScrollableContainer(id="viewport"):
            with Vertical(id="layout"):
                with Vertical(id="overview"):
                    yield Grid(*(NewsHeroCard(r) for r in hero_records(self.snapshot, "overview")), id="overview-heroes", classes="heroes")
                    yield Static(Text(SCOPES), classes="scopes")
                    yield Static(Text(COVERAGE), classes="coverage")
                    with Grid(id="insights"):
                        for key, title in (("activity", "REQUEST ACTIVITY / 30D"), ("request-states", "REQUEST STATUS / 84"),
                                           ("onchain", "ONCHAIN USE / 24H"), ("payments", "PAYMENTS / IMD")):
                            yield InsightPanel(title, insights[key], id=key)
                    with Horizontal(id="overview-body"):
                        yield CreatedPanel(id="overview-created")
                        with Vertical(id="overview-context"):
                            yield InsightPanel("SELECTED / ONCHAIN PATH", Text(), id="artifact-path")
                            yield InsightPanel("ATTENTION / 4 OPEN FOLLOW-UPS", followups, id="followups")
                    yield RecordPanel(id="overview-record")
                with Vertical(id="detail"):
                    yield Grid(*(NewsHeroCard(r) for r in hero_records(self.snapshot, "detail")), id="detail-heroes", classes="heroes")
                    yield Static(Text(SCOPES), classes="scopes")
                    yield Static(Text(COVERAGE), classes="coverage")
                    with Horizontal(id="detail-body"):
                        with Vertical(id="detail-left"):
                            yield CreatedPanel(id="detail-created")
                            yield InsightPanel("REQUESTS / PAYMENTS · 30D", insights["payments"], id="detail-context-panel")
                        yield DetailPanel(id="selected-panel")
        yield Static(Text(), id="demo-footer")

    def on_mount(self):
        for mode in ("overview", "detail"):
            table = self.query_one(f"#{mode}-assets", DataTable)
            columns = (("TYPE", 9), ("OUTPUT", 20), ("CHAIN", 5))
            if mode == "overview":
                columns += (("ONCHAIN USE / 24H", 23),)
            columns += (("SIGNAL", 16),)
            for label, width in columns:
                table.add_column(label, width=width)
            for a in self.snapshot["artifacts"]:
                signal = usage_signal(a, self.by_id)
                color = "green" if "ACTIVE" in signal or signal == "FIRST SEEN" else "dim"
                values = [literal(a["kind"]), literal(a["name"]), literal(a["chain"])]
                if mode == "overview":
                    values.append(literal(usage_text(a, self.by_id).split(" / ")[0]))
                table.add_row(*values, literal(signal, color), key=a["id"])
        orders = self.query_one("#orders", DataTable)
        for label, width in (("WHEN UTC", 11), ("ACTION", 18), ("OBJECT", 20), ("PAYMENT", 10), ("RESULT", 20)):
            orders.add_column(label, width=width)
        for r in self.snapshot["orders"]:
            when = datetime.fromtimestamp(r["timestamp"], timezone.utc).strftime("%m-%d %H:%M")
            orders.add_row(*(literal(v) for v in (when, r["action"], r["name"], r["payment_state"], r["outcome"])), key=r["id"])
        self.show_view(self.view)

    def show_view(self, view):
        self._tables_ready = False
        self.view = view
        self.query_one("#overview").display = view == "overview"
        self.query_one("#detail").display = view == "detail"
        hint = "Enter artifact detail · Tab records · Esc/q quit" if view == "overview" else "Tab pane · Esc overview · q quit"
        self.query_one("#demo-footer", Static).update(Text(f"arrows select · {hint} · DEMO DATA · no API / external actions"))
        self.update_detail()
        self.call_after_refresh(self._focus_selection)

    def _focus_selection(self):
        table = self.query_one(f"#{self.view}-assets", DataTable)
        row = list(self.by_id).index(self.selected_id)
        if self.view == "overview":
            table.scroll_to(x=self._overview_scroll[0], y=self._overview_scroll[1], animate=False)
            self.query_one("#viewport").scroll_to(x=self._outer_scroll[0], y=self._outer_scroll[1], animate=False)
        table.move_cursor(row=row, animate=False)
        table.focus()
        self._tables_ready = True

    @on(DataTable.RowHighlighted)
    def highlight_artifact(self, event):
        if not self._tables_ready or event.data_table.id != f"{self.view}-assets":
            return
        # Queued highlights from a hidden view or an earlier cursor cannot overwrite identity.
        table = event.data_table
        current = table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
        if event.row_key.value != current or current not in self.by_id:
            return
        self.selected_id = current
        self.update_detail()

    @on(DataTable.RowSelected)
    def open_artifact(self, event):
        if self.view != "overview" or event.data_table.id != "overview-assets":
            return
        self.selected_id = event.row_key.value
        self._overview_scroll = tuple(event.data_table.scroll_offset)
        self._outer_scroll = tuple(self.query_one("#viewport").scroll_offset)
        self.show_view("detail")

    def action_back(self):
        if self.view == "detail":
            self.show_view("overview")
        else:
            self.exit()

    def update_detail(self):
        a = self.by_id[self.selected_id]
        signal = usage_signal(a, self.by_id)
        source = usage_source(a, self.by_id)
        usage = source["usage"] if source else None
        lines = [a["name"], f"{a['kind']} / {a['chain']} · {signal}", "",
                 f"Order    {a['order_id']}", f"Project  {a['project']}", f"Version  {a['version']}"]
        if a["kind"] == "SITE":
            lines += [f"Site     <demo-{a['id']}-url>", f"Linked   {source['name'] if source else '--'}"]
        else:
            lines += [f"Address  <demo-{a['id']}-address>"]
        lines += ["", "ONCHAIN USE / 24H", usage_text(a, self.by_id)]
        if usage:
            lines += [f"Rule     {usage['rule']}",
                      "Window   " + ("complete" if usage["complete"] else "partial / lower bound only"),
                      "10-24 12:00 to 10-25 12:00 UTC", f"Blocks   <demo-{a['chain']}-from..to>",
                      f"Latest   {usage['latest']}"]
            if a["kind"] == "TOKEN":
                lines += [f"Consumer <demo-{a['id']}-consumer>"]
            if usage["first_seen"]:
                lines += ["Tracking since 10-24 12:00 UTC.", "First observed; not first-ever use."]
            lines += ["", "DEMO EVIDENCE", usage["evidence"]]
        elif signal == "NO ONCHAIN LINK":
            lines += ["Mapping checked: static site.", "No observed onchain path; not proof of nonuse."]
        else:
            lines += ["No verified usage rule or complete observation.", "Unknown is not zero activity."]
        if a["kind"] == "SITE" and source:
            lines += ["", "Linked contract evidence only:", "frontend origin not proven."]
        lines += ["", "DEMO DATA · no live chain reads"]
        self.query_one("#artifact-detail", Static).update(Text("\n".join(flatten(line) for line in lines)))
        path = Text(f"{flatten(a['name'])} / {a['kind']}\n", style="bold")
        path.append(f"├─ order {a['order_id']}\n", style="dim")
        target = (source["name"] if source else "no linked contract" if a["binding_checked"] else "link not verified") if a["kind"] == "SITE" else a["chain"] + " contract"
        path.append(f"└─ {flatten(target)}\n", style="bright_green" if source else "dim")
        path.append(f"   └─ {usage_text(a, self.by_id).split(' / ')[0]}\n")
        actors = f"{usage['actors']} addresses · " if usage and usage["count"] and usage["actors"] is not None else ""
        path.append(actors + signal + "\n")
        if a["kind"] == "SITE" and source:
            path.append("frontend origin not proven", style="dim")
        else:
            path.append("Enter: rule, coverage and evidence", style="dim")
        self.query_one("#artifact-path-content", Static).update(path)
        self.query_one("#detail-scroll").scroll_home(animate=False)


async def export_demo(path: Path, size: tuple[int, int], view="overview", selected_id="site-atlas"):
    async with SurfWalletDemo(view=view, selected_id=selected_id).run_test(size=size) as pilot:
        await pilot.pause()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(pilot.app.export_screenshot(title=f"WALLET / SWARM · {view.upper()} · DEMO DATA"))
        print(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--export", type=Path, help="write an SVG instead of opening the preview")
    parser.add_argument("--size", type=parse_size, default=(149, 45))
    parser.add_argument("--view", choices=("overview", "detail"), default="overview")
    parser.add_argument("--select", default="site-atlas", dest="selected_id")
    args = parser.parse_args()
    try:
        if args.export:
            asyncio.run(export_demo(args.export, args.size, args.view, args.selected_id))
        else:
            SurfWalletDemo(view=args.view, selected_id=args.selected_id).run()
    except ValueError as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
