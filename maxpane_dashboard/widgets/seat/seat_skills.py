"""The complete skill listing with stable row identity; write flow is screen-owned."""
from rich.text import Text
from maxpane_dashboard.widgets import rowfit
from maxpane_dashboard.widgets.seat.hero import _word
from maxpane_dashboard.widgets.seat.seat_table import SeatTable


class SeatSkills(SeatTable):
    TITLE = 'SKILLS'
    TABLE_ID = 'seat-skills-table'
    ROW_ID = 'id'
    ROW_CAP = None
    EMPTY_LINE = 'no skills offered'
    COLUMN_SPECS = (('id', 'id', 24), ('on', 'on', 3), ('needs', 'needs', 14))
    TIER_COLUMNS = {'full': ('id', 'on', 'needs')}
    LADDER = rowfit.Ladder(('full', 47))

    def update_data(self, seat_skills_rows=None, seat_skills_offered=None, seat_skills_on=None,
                    seat_skills_needs_network=None, seat_tools=None, seat_control_restart_required=None,
                    seat_sources=None, seat_as_of_hhmm=None, seat_host_kind=None, **_kwargs):
        self.TITLE = 'SKILLS' + (' (container)' if seat_host_kind == 'docker' else '')
        self._counts = (seat_skills_offered, seat_skills_on, seat_skills_needs_network)
        self._tools = seat_tools
        self._restart = seat_control_restart_required
        source = (seat_sources or {}).get('skills', {})
        rows = seat_skills_rows if isinstance(seat_skills_rows, list) and source.get('ok') is not False else None
        self.store(rows, (seat_as_of_hhmm or {}).get('skills'))

    def build_cells(self, item):
        return {'id': Text(rowfit.clip(_word(item.get('id')), 24)),
                'on': Text('on' if item.get('on') is True else 'off' if item.get('on') is False else '--'),
                'needs': Text(rowfit.clip(_word(item.get('needs')), 14))}

    def _repaint(self):
        super()._repaint()
        if not self.is_mounted or not hasattr(self, '_tools'):
            return
        words = ['tools: ' + (', '.join(_word(t) for t in self._tools) if self._tools else 'none configured' if self._tools == [] else 'unavailable')]
        if self._restart:
            words.insert(0, 'restart required · shown state applies after restart')
        self._write_footer(words)
