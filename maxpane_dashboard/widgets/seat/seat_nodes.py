"""Node table's stable identity and all/week selection; full metrics follow in WP5."""
from rich.text import Text
from maxpane_dashboard.widgets import rowfit
from maxpane_dashboard.widgets.seat.hero import _word
from maxpane_dashboard.widgets.seat.seat_table import SeatTable


class SeatNodes(SeatTable):
    TITLE = 'NODES'
    TABLE_ID = 'seat-nodes-table'
    ROW_ID = 'nodeKey'
    ROW_CAP = None
    EMPTY_LINE = 'no node attempts'
    COLUMN_SPECS = (('node', 'node', 24), ('role', 'role', 16), ('n', 'n', 8))
    TIER_COLUMNS = {'full': ('node', 'role', 'n')}
    LADDER = rowfit.Ladder(('full', 54))

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.week_only = False
        self._all = self._week = None

    def update_data(self, seat_nodes_all_rows=None, seat_nodes_week_rows=None, seat_nodes_coverage=None,
                    seat_sources=None, seat_offline=None, **_kwargs):
        self._all, self._week = seat_nodes_all_rows, seat_nodes_week_rows
        self.store(self._week if self.week_only else self._all, None)

    def toggle_window(self):
        self.week_only = not self.week_only
        self.store(self._week if self.week_only else self._all, None)

    def build_cells(self, item):
        return {'node': Text(rowfit.clip(_word(item.get('nodeKey')), 24)),
                'role': Text(rowfit.clip(_word(item.get('role')), 16)),
                'n': Text(str(item.get('attempts')) if item.get('attempts') is not None else '--')}
