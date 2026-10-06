"""Five newest production launches, selected from the current snapshot."""
from copy import deepcopy

from rich.text import Text
from rich.cells import cell_len
from textual.widgets import DataTable

from maxpane_dashboard.analytics.surf_swarm_signals import launch_verdict_label
from maxpane_dashboard.widgets import rowfit
from maxpane_dashboard.widgets.fmt import as_float
from maxpane_dashboard.widgets.panels import LOADING
from maxpane_dashboard.widgets.markup_safety import flatten
from maxpane_dashboard.widgets.surf._swarm_chain import chain_word
from maxpane_dashboard.widgets.surf._swarm_table import SwarmTableBase


def launch_age(created, now):
    created, now = as_float(created), as_float(now)
    if created is None or now is None:
        return '--'
    seconds = max(0, now-created)
    if seconds < 60:
        return '<1m'
    if seconds < 3600:
        return f'{int(seconds//60)}m'
    if seconds < 86400:
        return f'{int(seconds//3600)}h'
    return f'{int(seconds//86400)}d'


class SurfSwarmLatestLaunches(SwarmTableBase):
    TITLE = 'LATEST LAUNCHES'
    TABLE_ID = 'surf-swarm-latest-table'
    ROW_CAP = 5
    SELECTABLE = True
    CURSOR_TYPE = 'row'
    COLUMN_SPECS = (('launch', '', 44),)
    TIER_COLUMNS = {'full': ('launch',)}
    EMPTY_LINE = 'no production launch yet'
    EMPTY_ROW = ()
    LOADING_ROW = (LOADING,)
    DEFAULT_CSS = '''
    SurfSwarmLatestLaunches { height: auto; }
    SurfSwarmLatestLaunches > DataTable { height: 5; }
    '''

    class Selected(SwarmTableBase.Selected):
        pass

    def on_mount(self):
        self.query_one(DataTable).show_header = False

    def _budget(self):
        return self.size.width

    def column_plan(self, tier, budget):
        return (('launch', '', max(budget-2, 1)),)

    def update_data(self, swarm_launch_rows=None, swarm_launches_as_of_hhmm=None,
                    as_of=None, **_kwargs):
        rows = None
        if isinstance(swarm_launch_rows, list):
            rows = sorted((deepcopy(r) for r in swarm_launch_rows
                           if isinstance(r, dict) and r.get('production') is True),
                          key=lambda r: (as_float(r.get('created_ts')) or 0,
                                         as_float(r.get('launch_number')) or 0), reverse=True)[:5]
            for row in rows:
                row['as_of'] = as_of
        self.store(rows, swarm_launches_as_of_hhmm)

    def top_row(self):
        """Independent snapshot for the SWARM board's x action."""
        rows = (self._payload or {}).get('rows')
        return deepcopy(rows[0]) if rows else None

    def build_cells(self, item):
        room = max(self.size.width-2, 1)
        number = f"◆ #{item.get('launch_number')}"
        ticker = '--' if item.get('kind') == 'evm_contracts' else (
            '$'+flatten(item['ticker']) if item.get('ticker') else f"#{item.get('launch_number')}")
        verdict = launch_verdict_label(item.get('verdict'))
        age = launch_age(item.get('created_ts'), item.get('as_of'))
        chain = chain_word(item.get('chain_id'))
        # 6 + 10 + 7 + 9 cells and four single-cell gaps before age.
        show_chain = room >= 35
        show_age = room >= 36+len(age)
        tail = (8 if show_chain else 0) + (len(age)+1 if show_age else 0)
        verdict_cols = max(9, cell_len(verdict))
        ticker_cols = min(10, max(0, room-6-verdict_cols-2-tail))
        text = Text(rowfit.pad(number, 6), style='bold')
        if ticker_cols:
            text.append(' '+rowfit.pad(rowfit.clip(ticker, ticker_cols), ticker_cols))
        if show_chain:
            text.append(' '+rowfit.pad(chain, 7))
        text.append(' '+rowfit.pad(verdict, verdict_cols), style={
            'swarm': 'green', 'mismatch': 'red', 'failed': 'red',
        }.get((item.get('verdict') or {}).get('state'), 'dim'))
        if show_age:
            text.append(' '+age, style='dim')
        return {'launch': text}
