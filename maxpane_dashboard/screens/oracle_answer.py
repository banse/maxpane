"""A cached answer.json snapshot; this modal never fetches data."""
from rich.text import Text
from maxpane_dashboard.screens.record_detail import RecordDetailScreen

from maxpane_dashboard.widgets.address import address_prose, address_text
from maxpane_dashboard.widgets.explorer import for_chain_id
from maxpane_dashboard.widgets.markup_safety import strip_tags
from maxpane_dashboard.widgets.surf._oracle_answer import bytes32_text, seat_value, panel_text, failed_answer
from maxpane_dashboard.widgets.surf._swarm_seat import NODE_TITLES


def _paragraphs(value):
    return '\n'.join(strip_tags(line) for line in value.split('\n')) if isinstance(value, str) else '—'


class OracleAnswerScreen(RecordDetailScreen):
    TITLE_WORD = 'ANSWER'
    ID_PREFIX = 'oracle-answer'

    def title_node(self):
        return NODE_TITLES.get(self.row.get('node_key'), 'oracle').lower()

    def compose_sections(self):
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
        elif str(row.get('panel_answer_type') or '').endswith('[]') and row.get('oracle_seat_answer') is not None:
            values = row['oracle_seat_answer'].split()
            value.append('\n            '.join(values) if values else '0 values')
        else:
            value.append_text(address_prose(seat_value(row), explorer=explorer))
            text = bytes32_text(row.get('oracle_seat_answer')) if row.get('panel_answer_type') == 'bytes32' else None
            if text is not None:
                # The decoded text on its own line under the hex (owner, 2026-09-25);
                # ``Text.append`` parses no markup.
                value.append('\n            ').append(text)
        yield from self.section('QUESTION', address_prose(_paragraphs(row.get('oracle_question')), explorer=explorer), first=True)
        yield from self.section('ANSWER', value, Text('panel       ') + panel_text(row, detail=True))
        yield from self.section('NOTES', address_prose(_paragraphs(row.get('oracle_notes')), explorer=explorer))
