"""Record-table composition and stable cursor; complete answer/panel cells follow in WP5."""
from rich.text import Text
from maxpane_dashboard.analytics.seat_records import record_state, record_window
from maxpane_dashboard.analytics.seat_signals import parse_iso
from maxpane_dashboard.widgets import rowfit
from maxpane_dashboard.widgets.fmt import mmdd_hhmm
from maxpane_dashboard.widgets.seat.hero import _word
from maxpane_dashboard.widgets.seat._chain import job_link_style
from maxpane_dashboard.widgets.seat.seat_table import SeatTable


class SeatRecords(SeatTable):
    TITLE = 'RECORDS'
    TABLE_ID = 'seat-records-table'
    ROW_CAP = 400
    EMPTY_LINE = 'no records'
    COLUMN_SPECS = (('when', 'when', 11), ('job', 'job', 8), ('node', 'node', 18), ('state', 'state', 10))
    TIER_COLUMNS = {'full': ('when', 'job', 'node', 'state')}
    LADDER = rowfit.Ladder(('full', 55))

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.limit = 40
        self.open_only = False
        self._records = None
        self._clock = None

    def update_data(self, seat_records_rows=None, seat_records_window=None, seat_sources=None,
                    seat_as_of_hhmm=None, seat_offline=None, **_kwargs):
        self.TITLE = 'RECORDS · offline · cached' if seat_offline else 'RECORDS'
        self._records = seat_records_rows
        self._clock = (seat_as_of_hhmm or {}).get('seatWork')
        self.set_window(self.limit, self.open_only)

    def set_window(self, limit, open_only):
        self.limit, self.open_only = max(40, min(400, limit)), open_only
        rows = record_window(self._records, self.limit, open_only) if isinstance(self._records, list) else None
        self.store(rows, self._clock)

    def build_cells(self, item):
        return {'when': mmdd_hhmm(parse_iso(item.get('submittedUtc') or item.get('acceptedUtc'))),
                'job': Text(_word(item.get('jobId'))[:8], style=job_link_style(item.get('jobId'))),
                'node': Text(rowfit.clip(_word(item.get('nodeKey')), 18)),
                'state': Text(rowfit.clip(_word(record_state(item)) or '--', 10))}
