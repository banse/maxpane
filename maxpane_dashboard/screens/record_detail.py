"""Shared cached RECORD popup frame: snapshot, focused scroll and pinned close hint."""
from copy import deepcopy

from rich.text import Text
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

from maxpane_dashboard.widgets.markup_safety import sanitize_cell
from maxpane_dashboard.widgets.surf._fmt import mmdd_hhmm


class RecordDetailScreen(ModalScreen[None]):
    TITLE_WORD = ''
    ID_PREFIX = 'record-detail'
    SHOW_ROLE = False
    BINDINGS = [Binding('space', 'close', show=False, priority=True),
                Binding('escape', 'close', show=False, priority=True)]
    DEFAULT_CSS = '''
    RecordDetailScreen { align: center middle; padding: 1 0; }
    RecordDetailScreen .record-detail-box {
        width: 100%; max-width: 110; height: 100%; border: solid $accent; padding: 0 2;
    }
    RecordDetailScreen .record-detail-title {
        height: 1; margin: 0 0 1 0; text-wrap: nowrap; text-overflow: ellipsis;
    }
    RecordDetailScreen .record-detail-scroll { height: 1fr; min-height: 1; overflow-x: hidden; }
    RecordDetailScreen .record-detail-scroll Static { height: auto; width: 100%; }
    RecordDetailScreen .record-detail-heading { margin: 1 0 0 0; }
    RecordDetailScreen .record-detail-close { height: 1; margin: 1 0 0 0; text-align: center; }
    '''

    def __init__(self, row):
        super().__init__()
        self.row = deepcopy(row)

    def compose(self):
        prefix = self.ID_PREFIX
        with Vertical(id=prefix+'-box', classes='record-detail-box'):
            yield Static(Text(), id=prefix+'-title', classes='record-detail-title')
            with VerticalScroll(id=prefix+'-scroll', classes='record-detail-scroll'):
                yield from self.compose_sections()
            yield Static(Text('PRESS SPACE OR ESC TO CLOSE', style='dim'), id=prefix+'-close', classes='record-detail-close')

    def compose_sections(self):
        raise NotImplementedError

    def section(self, title, *contents, first=False):
        yield Static(Text(title, style='bold'), classes='' if first else 'record-detail-heading')
        for content in contents:
            yield Static(content)

    def title_node(self):
        return self.row.get('node_key') or '—'

    def on_mount(self):
        self.query_one(VerticalScroll).focus()
        self.call_after_refresh(self._title)

    def on_resize(self):
        self.call_after_refresh(self._title)

    def _title(self):
        title = self.query_one('.record-detail-title', Static)
        row = self.row
        stamp = row.get('submitted_ts') if row.get('submitted_ts') is not None else row.get('accepted_ts')
        parts = [self.TITLE_WORD, str(row.get('job_id') or '')[:8], self.title_node()]
        if self.SHOW_ROLE:
            parts.append(row.get('role') or '—')
        parts.append(mmdd_hhmm(stamp))
        title.update(Text.from_markup(sanitize_cell(' · '.join(parts), title.size.width), style='bold'))

    def action_close(self):
        self.dismiss(None)
