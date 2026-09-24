"""A cached answer.json snapshot; this modal never fetches data."""
from copy import deepcopy

from rich.text import Text
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

from maxpane_dashboard.widgets.address import address_prose, address_text
from maxpane_dashboard.widgets.explorer import for_chain_id
from maxpane_dashboard.widgets.markup_safety import sanitize_cell, strip_tags
from maxpane_dashboard.widgets.surf._fmt import mmdd_hhmm
from maxpane_dashboard.widgets.surf._oracle_answer import seat_value, panel_text, failed_answer
from maxpane_dashboard.widgets.surf._swarm_seat import NODE_TITLES


def _paragraphs(value):
    return '\n'.join(strip_tags(line) for line in value.split('\n')) if isinstance(value, str) else '—'


class OracleAnswerScreen(ModalScreen[None]):
    BINDINGS = [Binding('enter', 'close', show=False, priority=True),
                Binding('escape', 'close', show=False, priority=True)]
    DEFAULT_CSS = '''
    OracleAnswerScreen { align: center middle; padding: 1 0; }
    OracleAnswerScreen #oracle-answer-box {
        width: 100%; max-width: 110; height: 100%; border: solid $accent; padding: 0 2;
    }
    OracleAnswerScreen #oracle-answer-title {
        height: 1; margin: 0 0 1 0; text-wrap: nowrap; text-overflow: ellipsis;
    }
    OracleAnswerScreen #oracle-answer-scroll { height: 1fr; min-height: 1; overflow-x: hidden; }
    OracleAnswerScreen #oracle-answer-scroll Static { height: auto; width: 100%; }
    OracleAnswerScreen .oracle-answer-heading { margin: 1 0 0 0; }
    OracleAnswerScreen #oracle-answer-close { height: 1; margin: 1 0 0 0; text-align: center; }
    '''

    def __init__(self, row):
        super().__init__()
        self.row = deepcopy(row)

    def compose(self):
        row = self.row
        explorer = for_chain_id(row.get('oracle_chain_id'))
        value = Text('this seat   ')
        if row.get('oracle_member_ok') is False:
            value.append_text(address_prose(failed_answer(row),
                                             explorer=explorer, style='red'))
        elif row.get('panel_answer_type') == 'address[]' and row.get('oracle_seat_answer') is not None:
            addresses = row['oracle_seat_answer'].split()
            if not addresses:
                value.append('0 addresses')
            for index, address in enumerate(addresses):
                if index: value.append('\n            ')
                value.append_text(address_text(address, explorer=explorer))
        else:
            value.append_text(address_prose(seat_value(row), explorer=explorer))
        with Vertical(id='oracle-answer-box'):
            yield Static(Text(), id='oracle-answer-title')
            with VerticalScroll(id='oracle-answer-scroll'):
                yield Static(Text('QUESTION', style='bold'))
                yield Static(address_prose(_paragraphs(row.get('oracle_question')), explorer=explorer))
                yield Static(Text('ANSWER', style='bold'), classes='oracle-answer-heading')
                yield Static(value)
                yield Static(Text('panel       ') + panel_text(row, detail=True))
                yield Static(Text('NOTES', style='bold'), classes='oracle-answer-heading')
                yield Static(address_prose(_paragraphs(row.get('oracle_notes')), explorer=explorer))
            yield Static(Text('PRESS ENTER TO CLOSE', style='dim'), id='oracle-answer-close')

    def on_mount(self):
        self.query_one(VerticalScroll).focus()
        self.call_after_refresh(self._title)

    def on_resize(self):
        self.call_after_refresh(self._title)

    def _title(self):
        title = self.query_one('#oracle-answer-title', Static)
        row = self.row
        stamp = row.get('submitted_ts') if row.get('submitted_ts') is not None else row.get('accepted_ts')
        words = f"ANSWER · {str(row.get('job_id') or '')[:8]} · {NODE_TITLES.get(row.get('node_key'), 'oracle').lower()} · {mmdd_hhmm(stamp)}"
        title.update(Text.from_markup(sanitize_cell(words, title.size.width), style='bold'))

    def action_close(self):
        self.dismiss(None)
