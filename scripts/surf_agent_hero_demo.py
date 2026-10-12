"""Standalone AGENT proposal 4; all data and identities are fictional.

Run: .venv/bin/python scripts/surf_agent_hero_demo.py
Export: add --export /tmp/surf-agent-heroes.svg --size 149x45
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Grid, ScrollableContainer, Vertical
from textual.widgets import Static

from maxpane_dashboard.copy_action import CopyAddressMixin
from maxpane_dashboard.explorer_action import ExplorerLinkMixin
from maxpane_dashboard.themes import THEMES
from maxpane_dashboard.widgets.address import address_text
from maxpane_dashboard.widgets.surf._fmt import EXPLORER, hhmm
from maxpane_dashboard.widgets.surf.news_hero import HeroRecord, NewsHeroCard
from maxpane_dashboard.widgets.surf.swarm_seat_record import SurfSwarmSeatRecord
from maxpane_dashboard.widgets.surfboard.rack import meter_text
from scripts.surf_start_demo import parse_size


MOCK_TIME = datetime(2026,10,12,12,tzinfo=timezone.utc).timestamp()


def mock_snapshot():
    """Complete mock attempt history; receipt totals are independent facts."""
    accepted_nodes = ['adversarial_review']*500 + ['build_contract_project']*340 + ['oracle_assess']*120
    objectives = ('Audit router permissions and upgrade checks.', 'Build the token dashboard.',
                  'Check the oracle response against the source.', 'Review the updated vault tests.')
    rows = []
    accepted_index = 0
    for index in range(1000):
        exceptional = index // 25
        state = ('rejected' if exceptional < 20 else 'failed' if exceptional < 30 else 'pending') if index % 25 == 0 else 'accepted'
        node = accepted_nodes[accepted_index*37 % 960] if state == 'accepted' else 'adversarial_review'
        accepted_index += state == 'accepted'
        submitted = MOCK_TIME - 120 - index*600
        rows.append(dict(job_id=f'00000000-0000-4000-8000-{index+1:012d}',
                         submission_hash=f'{index+1:064x}', node_key=node,
                         work_status=state, job_state='completed' if state == 'accepted' else state,
                         objective=objectives[index % len(objectives)], submitted_ts=submitted,
                         accepted_ts=submitted + 30 if state == 'accepted' else None,
                         answer=objectives[index % len(objectives)], answer_state='read',
                         model='demo-model', took_s=1152, output_tokens=1800,
                         panel_state='not_oracle' if node != 'oracle_assess' else 'agreed',
                         panel_agreed=3, panel_quorum=3, panel_size=5))
    totals = Counter(row['work_status'] for row in rows)
    nodes = Counter(row['node_key'] for row in rows if row['work_status']=='accepted')
    return dict(rows=rows, attempts=len(rows), accepted=totals['accepted'], nodes=nodes,
                token_id=420, rank=27, ranked_of=1024, wall_clock_s=320*3600,
                output_tokens=1800000, owner_receipts=38.52, owner_seats=3,
                rewards_imd=38.52/3, imd_usd=9.41, working=2, capacity=3, devices=2,
                owner='0x0000000000000000000000000000000000000001', owner_label='example.eth',
                paired_ts=datetime(2026,10,1,tzinfo=timezone.utc).timestamp(),
                runtime='codex', runtime_version='vX.Y.Z', daemon='vX.Y',
                models=(('model A','high'),('model B','medium')),
                feedback=dict(sent=186,submitted=4,queued=2),
                teammates=[dict(token_id=527 if i==0 else i+1,shared_jobs=84 if i==0 else 52-i*4) for i in range(12)])


MOCK_DATA = mock_snapshot()
_OWNER = address_text(MOCK_DATA['owner'], label=MOCK_DATA['owner_label'], explorer=EXPLORER)
MOCK_CARDS = (
    HeroRecord('seat','SEAT','IDMD','SELECTED',digits=str(MOCK_DATA['token_id']),subtitle='saved seat'),
    HeroRecord('accepted','ACCEPTED','WORK','96%',digits=str(MOCK_DATA['accepted']),subtitle=f"{MOCK_DATA['attempts']:,} attempts"),
    HeroRecord('effort','EFFORT','HOURS','CONTRIBUTORS',digits=f"{MOCK_DATA['wall_clock_s']/3600:.0f}",subtitle=f"{MOCK_DATA['output_tokens']/1e6:.1f}M tokens"),
    HeroRecord('rewards','REWARDS','IMD','OWNER SHARE',digits=f"{MOCK_DATA['rewards_imd']:.2f}",subtitle=f"${MOCK_DATA['rewards_imd']*MOCK_DATA['imd_usd']:.2f}"),
    HeroRecord('rank','RANK','POSITION','RECORDS',digits=str(MOCK_DATA['rank']),subtitle=f"of {MOCK_DATA['ranked_of']:,}"),
    HeroRecord('status','STATUS','WORKER','BUSY',stats=tuple((key,str(MOCK_DATA[key])) for key in ('working','capacity','devices')),subtitle='worked 2m ago'),
    HeroRecord('owner','OWNER','WALLET','OPEN / COPY',digits=_OWNER.plain,subtitle='paired 10-01'),
    HeroRecord('runtime','RUNTIME','SOFTWARE','VERSION',stats=((MOCK_DATA['runtime'],MOCK_DATA['runtime_version']),('daemon',MOCK_DATA['daemon']),('devices',str(MOCK_DATA['devices']))),subtitle='up to date'),
    HeroRecord('models','MODELS','ADVERTISED','CONFIGURATION',stats=MOCK_DATA['models'],subtitle=f"{len(MOCK_DATA['models'])} models"),
    HeroRecord('feedback','FEEDBACK','DELIVERY',f"{MOCK_DATA['feedback']['queued']} QUEUED",stats=tuple((key,str(value)) for key,value in MOCK_DATA['feedback'].items()),subtitle='review msgs'),
    HeroRecord('collab','COLLAB','SEATS',f"TOP #{MOCK_DATA['teammates'][0]['token_id']} x{MOCK_DATA['teammates'][0]['shared_jobs']}",digits=str(len(MOCK_DATA['teammates'])),subtitle='collaborators'),
    HeroRecord('nodes','NODES','ACCEPTED','HISTORY',stats=tuple((label,str(MOCK_DATA['nodes'][key])) for label,key in (('review','adversarial_review'),('build','build_contract_project'),('oracle','oracle_assess'))),subtitle='work by node'),
)


class AgentMockCard(NewsHeroCard):
    """Demo-only footer styling and the existing rich owner affordance."""

    def _footer(self):
        if self.data.key == 'status':
            self.border_subtitle = meter_text(dict(key='agent',meter_state='busy'),width=max(5,self.size.width-6))
        elif self.data.key == 'accepted':
            rate = MOCK_DATA['accepted']/MOCK_DATA['attempts']
            label = f'{rate*100:.0f}% '
            # The shared generic meter prefixes AUX; keep only its styled track.
            track = meter_text(dict(key='accepted',numerator=MOCK_DATA['accepted'],denominator=MOCK_DATA['attempts']),
                               width=max(4,self.size.width-6-len(label)+4))[4:]
            self.border_subtitle = Text(label,style='dim').append_text(track)
        else:
            super()._footer()

    def render(self):
        text = super().render()
        if self.data.key == 'owner':
            offset = text.plain.find(_OWNER.plain)
            if offset >= 0:
                for span in _OWNER.spans:
                    text.stylize(span.style,offset+span.start,offset+span.end)
        return text


class SurfAgentHeroDemo(CopyAddressMixin, ExplorerLinkMixin, App):
    TITLE = 'AGENT / SURFBOARD — MOCK DATA'
    CSS_PATH = Path(__file__).resolve().parent.parent / 'maxpane_dashboard/themes/minimal.tcss'
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [Binding('q','quit','Quit',show=False)]
    CSS = """
    Screen { background: $background; color: $text; }
    #demo-title, #demo-footer { height: 1; padding: 0 1; background: $surface; color: $text-muted; }
    #viewport { height: 1fr; overflow: auto auto; scrollbar-size: 1 1; }
    #layout { height: 1fr; min-height: 41; min-width: 145; padding: 1 1; }
    #agent-heroes { height: 19; grid-size: 6 2; grid-columns: 1fr; grid-rows: 9; grid-gutter: 1 1; margin-bottom: 1; }
    #agent-record { height: 1fr; min-height: 10; padding: 0 1; }
    """

    def __init__(self,cards=MOCK_CARDS):
        if len(cards) != 12:
            raise ValueError('the selected proposal requires exactly twelve cards')
        super().__init__()
        self.cards = cards
        self.register_theme(THEMES['matrix'])
        self.theme = 'matrix'

    def compose(self) -> ComposeResult:
        yield Static(Text('AGENT / SURFBOARD                                MOCK DATA · HERO PROPOSAL 4'),id='demo-title')
        with ScrollableContainer(id='viewport'):
            with Vertical(id='layout'):
                yield Grid(*(AgentMockCard(card) for card in self.cards),id='agent-heroes')
                yield SurfSwarmSeatRecord(id='agent-record')
        yield Static(Text('q quit · MOCK DATA · fictional identity, work and rewards · no API connection'),id='demo-footer')

    def on_mount(self):
        self.query_one(SurfSwarmSeatRecord).update_data(swarm_seat_work_rows=MOCK_DATA['rows'],swarm_seat_state='ok',
            swarm_seat_as_of_hhmm=hhmm(MOCK_TIME),swarm_seat_read='ok')


async def export_demo(path: Path,size: tuple[int,int]):
    async with SurfAgentHeroDemo().run_test(size=size) as pilot:
        await pilot.pause()
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(pilot.app.export_screenshot(title='AGENT / SURFBOARD · MOCK DATA'))
        print(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--export',type=Path,help='export an SVG instead of opening the mockup')
    parser.add_argument('--size',type=parse_size,default=(149,45),help='export size (default: 149x45)')
    args = parser.parse_args()
    if args.export:
        asyncio.run(export_demo(args.export,args.size))
    else:
        SurfAgentHeroDemo().run()


if __name__ == '__main__':
    main()
