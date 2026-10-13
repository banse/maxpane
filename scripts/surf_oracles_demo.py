"""Standalone ORACLES preview; every request, seat answer and value is fictional.

Run: .venv/bin/python scripts/surf_oracles_demo.py
Export: add --export /tmp/surf-oracles.svg --size 149x45
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.style import Style
from rich.text import Text
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal, ScrollableContainer, Vertical
from textual.widgets import DataTable, Input, Static, Tree

from maxpane_dashboard.screens.oracle_answer import OracleAnswerScreen
from maxpane_dashboard.themes import THEMES
from maxpane_dashboard.widgets.fmt import fmt_age
from maxpane_dashboard.widgets.panels import PanelBase
from maxpane_dashboard.widgets.rowfit import clip
from maxpane_dashboard.widgets.surf._oracle_answer import consensus_value, panel_text, seat_value
from maxpane_dashboard.widgets.surf.news_hero import HeroRecord, NewsHeroCard
from scripts.surf_start_demo import parse_size

MOCK_TIME = datetime(2026, 10, 13, 12, tzinfo=timezone.utc).timestamp()
STATE_LABELS = {"assessing": "assessing", "attested": "attested", "disagreed": "no quorum", "blocked": "blocked"}
STATE_COLORS = {"assessing": "yellow", "attested": "green", "disagreed": "yellow", "blocked": "red"}


def mock_requests():
    """A bounded, coherent fictional request list with exact per-submission records."""
    states = ["assessing", "attested", "disagreed", "attested", "blocked"]
    remaining = Counter(assessing=7, attested=86, disagreed=5, blocked=2) - Counter(states)
    states += list(remaining.elements())
    questions = (
        "Is the ETH/USD price above $3,000?",
        "Is the ETH/USD price above $3,000?",
        "Did this pool's swap volume exceed its requested threshold in the last 3h?",
        "Is the collection floor price above the requested threshold?",
        "Is the requested pool contract deployed on this chain?",
    )
    rows = []
    for index, status in enumerate(states):
        chain, chain_id = (("ETH", 1), ("ETH", 1), ("BASE", 8453), ("ETH", 1), ("RH", 4663))[index % 5]
        job = f"00000000-0000-4000-8000-{index + 1:012d}"
        agreed = 13 if status == "attested" else 11 if status == "disagreed" else None
        row = dict(id=str(index), job_id=job, status=status, chain=chain, chain_id=chain_id,
                   question=questions[index % 5], age_s=120 * (index + 1), panel_size=17, quorum=12,
                   agreed=agreed, panel_answer_type="bool", panel_answer_bool=True if status == "attested" else None,
                   members=[])
        seats = [527, 1207, *range(601, 612), 355, 712, 834, 920]
        count = 0 if status == "blocked" else 4 if status == "assessing" else 17
        for member_index, seat in enumerate(seats[:count]):
            in_cluster = agreed is not None and member_index < agreed
            state = ("assessing" if status == "assessing" else
                     "no_quorum_in" if status == "disagreed" and in_cluster else
                     "no_quorum_out" if status == "disagreed" else
                     "agreed" if in_cluster else "outvoted")
            answer = "true" if in_cluster or status == "assessing" else "false"
            notes = ("Mock observation exceeds the requested threshold. The seat returned true."
                     if answer == "true" else "Mock observation falls below the requested threshold. The seat returned false.")
            row["members"].append(dict(
                seat=seat, job_id=job, submission_hash=f"{index * 100 + member_index + 1:064x}",
                node_key="oracle_assess", submitted_ts=MOCK_TIME - row["age_s"],
                panel_state=state, panel_agreed=agreed, panel_quorum=12, panel_size=17,
                panel_answer_type="bool", panel_answer_bool=row["panel_answer_bool"],
                oracle_member_ok=True, oracle_seat_answer=answer, oracle_question=row["question"],
                oracle_chain_id=chain_id, oracle_notes=notes))
        rows.append(row)
    return rows


MOCK_REQUESTS = mock_requests()


def hero_records(rows):
    counts = Counter(row["status"] for row in rows)
    return tuple(HeroRecord(key, title, heading, footer, digits=str(value), accent=key not in ("requests", "networks"))
                 for key, title, heading, footer, value in (
                     ("requests", "REQUESTS", "LOADED", "request history", len(rows)),
                     ("assessing", "ASSESSING", "OPEN", "in progress", counts["assessing"]),
                     ("attested", "ATTESTED", "CLOSED", "with agreement", counts["attested"]),
                     ("disagreed", "NO QUORUM", "CLOSED", "without quorum", counts["disagreed"]),
                     ("blocked", "BLOCKED", "ATTENTION", "needs attention", counts["blocked"]),
                     ("networks", "NETWORKS", "CHAINS", "loaded requests", len({row["chain"] for row in rows}))))


class OracleMockCard(NewsHeroCard):
    def render(self):
        result = super().render()
        tone = STATE_COLORS.get(self.data.key)
        if tone and tone != "green":
            frame = result.style
            result.style = frame + Style(color=tone)
            result.spans = [span._replace(style=span.style + Style(color=tone))
                            if span.style == frame else span for span in result.spans]
        return result


class RequestPanel(PanelBase):
    TITLE = "REQUESTS"

    def compose_body(self):
        yield Static(Text(), id="request-coverage")
        yield Input(placeholder="find a question or chain", id="request-find")
        yield DataTable(id="requests", cursor_type="row", zebra_stripes=True)


class DetailPanel(PanelBase):
    TITLE = "SELECTED REQUEST"

    def compose_body(self):
        yield Static(Text(), id="request-summary")
        yield Static(Text(), id="answer-heading")
        tree = Tree("answers", id="answer-tree")
        tree.show_root = False
        yield tree
        yield Static(Text("click branches · enter full answer · esc closes", style="dim"), id="answer-hint")


class SurfOraclesDemo(App):
    TITLE = "ORACLES / SURFBOARD — MOCK DATA"
    CSS_PATH = Path(__file__).resolve().parent.parent / "maxpane_dashboard/themes/minimal.tcss"
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [Binding("q", "quit", show=False), Binding("f", "filter_status", show=False),
                Binding("c", "filter_chain", show=False), Binding("/", "find", show=False),
                Binding("escape", "clear_find", show=False)]
    CSS = """
    Screen { background: $background; color: $text; }
    #demo-title, #demo-footer { height: 1; padding: 0 1; background: $surface; color: $text-muted; }
    #demo-title { text-align: center; }
    #viewport { height: 1fr; overflow: auto auto; scrollbar-size: 1 1; }
    #layout { height: 1fr; min-height: 41; min-width: 145; padding: 1 1; }
    #oracle-heroes { height: 9; grid-size: 6 1; grid-columns: 1fr; grid-rows: 9; grid-gutter: 0 1; margin-bottom: 1; }
    #oracle-body { height: 1fr; min-height: 28; }
    #oracle-body PanelBase { border: round $panel; padding: 0 1; background: $background; height: 1fr; }
    #oracle-body .panel-title { height: 1; text-wrap: nowrap; }
    #requests-panel { width: 47%; margin-right: 1; }
    #detail-panel { width: 1fr; }
    #request-coverage { height: 1; margin-bottom: 1; color: $text-muted; }
    #request-find { display: none; height: 3; }
    #requests { height: 1fr; min-height: 8; scrollbar-gutter: stable; }
    #request-summary { height: auto; margin-bottom: 1; }
    #answer-heading { height: 1; margin-bottom: 1; color: $text-muted; }
    #answer-tree { height: 1fr; min-height: 8; padding: 0; background: $background; scrollbar-gutter: stable; }
    #answer-hint { height: 1; color: $text-muted; }
    """

    def __init__(self):
        super().__init__()
        self.register_theme(THEMES["matrix"])
        self.theme = "matrix"
        self.status_filter = "all"
        self.chain_filter = "all"
        self.search = ""
        self.selected_id = "1"
        self.by_id = {row["id"]: row for row in MOCK_REQUESTS}

    def compose(self) -> ComposeResult:
        yield Static(Text("ORACLES / SURFBOARD · MOCK DATA"), id="demo-title")
        with ScrollableContainer(id="viewport"):
            with Vertical(id="layout"):
                yield Grid(*(OracleMockCard(card) for card in hero_records(MOCK_REQUESTS)), id="oracle-heroes")
                with Horizontal(id="oracle-body"):
                    yield RequestPanel(id="requests-panel")
                    yield DetailPanel(id="detail-panel")
        yield Static(Text("q quit · tab pane · arrows select · enter open · / find · f status · c chain · MOCK DATA · no API"), id="demo-footer")

    def on_mount(self):
        table = self.query_one(DataTable)
        for label, width in (("AGE", 3), ("CHAIN", 5), ("STATE", 9), ("QUESTION", 37)):
            table.add_column(label, width=width)
        self.rebuild_requests()
        table.focus()

    def rebuild_requests(self):
        rows = [row for row in MOCK_REQUESTS if
                (self.status_filter == "all" or row["status"] == self.status_filter) and
                (self.chain_filter == "all" or row["chain"] == self.chain_filter) and
                self.search in (row["question"] + " " + row["chain"]).casefold()]
        table = self.query_one(DataTable)
        table.clear()
        for row in rows:
            table.add_row(Text(fmt_age(row["age_s"]), style="dim"), Text(row["chain"]),
                          Text(STATE_LABELS[row["status"]], style=STATE_COLORS[row["status"]]),
                          Text(clip(row["question"], 37)), key=row["id"])
        self.query_one("#request-coverage", Static).update(Text(
            f"{len(rows)} shown / 100 loaded · {STATE_LABELS.get(self.status_filter, 'all states')} · {self.chain_filter}"))
        selected = next((i for i, row in enumerate(rows) if row["id"] == self.selected_id), 0)
        if rows:
            table.move_cursor(row=selected)
            self.show_request(rows[selected])
        else:
            self.query_one("#request-summary", Static).update(Text("No matching requests", style="dim"))
            self.query_one("#answer-heading", Static).update(Text())
            self.query_one(Tree).clear()

    @on(DataTable.RowHighlighted, "#requests")
    def select_request(self, event):
        if event.row_key in self.query_one(DataTable).rows:
            self.show_request(self.by_id[event.row_key.value])

    @on(DataTable.RowSelected, "#requests")
    def open_request(self, event):
        self.show_request(self.by_id[event.row_key.value])
        self.query_one(Tree).focus()

    def show_request(self, row):
        self.selected_id = row["id"]
        status = row["status"]
        summary = Text(row["question"] + "\n\n")
        summary.append(STATE_LABELS[status].upper(), style=STATE_COLORS[status])
        summary.append(f" · {row['chain']} · {fmt_age(row['age_s'])} ago\n", style="dim")
        result = (consensus_value(row) + " · boolean" if status == "attested" else
                  "No attested answer · closed" if status == "disagreed" else
                  "Awaiting agreement" if status == "assessing" else "Source unavailable · request blocked")
        summary.append(result + "\n", style="bold" if status == "attested" else "dim")
        agreed = str(row["agreed"]) if row["agreed"] is not None else "—"
        summary.append(f"{agreed} agreed · {row['quorum']} required · {row['panel_size']} seats target", style="dim")
        self.query_one("#request-summary", Static).update(summary)
        self.query_one("#answer-heading", Static).update(Text(f"ANSWERS · {len(row['members'])} loaded records", style="bold"))
        tree = self.query_one(Tree)
        tree.clear()
        groups = {}
        labels = {"agreed": "AGREED", "outvoted": "OUTVOTED", "no_quorum_in": "IN CLUSTER · NO QUORUM",
                  "no_quorum_out": "OUTSIDE CLUSTER · NO QUORUM", "assessing": "ASSESSING"}
        counts = Counter(member["panel_state"] for member in row["members"])
        for member in row["members"]:
            state = member["panel_state"]
            if state not in groups:
                tone = "green" if state == "agreed" else "red" if state == "outvoted" else "yellow"
                groups[state] = tree.root.add(Text(f"{labels[state]} · {counts[state]}", style=tone), expand=not groups)
            label = Text(f"seat {member['seat']:<5}  ").append_text(panel_text(member))
            label.append("  " + seat_value(member, compact=True))
            node = groups[state].add(label, expand=member is row["members"][0])
            node.add_leaf(Text("answer  " + seat_value(member), style="bold"))
            node.add_leaf(Text("open full answer »", style="green"), data=member)
        if not row["members"]:
            tree.root.add_leaf(Text("No answer records loaded", style="dim"))
        tree.root.expand()

    @on(Tree.NodeSelected, "#answer-tree")
    def open_answer(self, event):
        if event.node.data:
            self.push_screen(OracleAnswerScreen(event.node.data))

    def action_filter_status(self):
        options = ("all", *STATE_LABELS)
        self.status_filter = options[(options.index(self.status_filter) + 1) % len(options)]
        self.rebuild_requests()

    def action_filter_chain(self):
        options = ("all", "ETH", "BASE", "RH")
        self.chain_filter = options[(options.index(self.chain_filter) + 1) % len(options)]
        self.rebuild_requests()

    def action_find(self):
        field = self.query_one(Input)
        field.display = True
        field.focus()

    @on(Input.Changed, "#request-find")
    def find_changed(self, event):
        self.search = event.value.casefold()
        self.rebuild_requests()

    @on(Input.Submitted, "#request-find")
    def find_submitted(self):
        self.query_one(DataTable).focus()

    def action_clear_find(self):
        field = self.query_one(Input)
        field.value = ""
        field.display = False
        self.search = ""
        self.rebuild_requests()
        self.query_one(DataTable).focus()


async def export_demo(path: Path, size: tuple[int, int]):
    async with SurfOraclesDemo().run_test(size=size) as pilot:
        await pilot.pause()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(pilot.app.export_screenshot(title="ORACLES / SURFBOARD · MOCK DATA"))
        print(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--export", type=Path, help="export an SVG instead of opening the mockup")
    parser.add_argument("--size", type=parse_size, default=(149, 45), help="export size (default: 149x45)")
    args = parser.parse_args()
    if args.export:
        asyncio.run(export_demo(args.export, args.size))
    else:
        SurfOraclesDemo().run()


if __name__ == "__main__":
    main()
