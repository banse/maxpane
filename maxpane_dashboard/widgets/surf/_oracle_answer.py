"""Pure answer.json wording and fitting shared by RECORD and its popup."""
import re

from rich.style import Style
from rich.text import Text

from maxpane_dashboard.widgets import rowfit
from maxpane_dashboard.widgets.address import is_job_id
from maxpane_dashboard.widgets.explorer import for_chain_id
from maxpane_dashboard.widgets.markup_safety import sanitize_cell, strip_tags
from maxpane_dashboard.widgets.surf._icons import mark_addresses, keep_units, link_prose, unmark

_HASH = re.compile(r'[0-9a-f]{64}')


def valid_identity(job, submission_hash):
    return (is_job_id(job)
            and isinstance(submission_hash, str) and _HASH.fullmatch(submission_hash) is not None)


def joined(row):
    # The fold exposes a strict member_ok only for an exact-hash membership.
    return type(row.get('oracle_member_ok')) is bool


def seat_value(row, *, compact=False):
    value, kind = row.get('oracle_seat_answer'), row.get('panel_answer_type')
    if value is None:
        return '—'
    if kind == 'bool':
        return {'true': 'YES', 'false': 'NO'}.get(value, '—')
    if kind == 'address[]' and compact:
        count = len(value.split())
        return f'{count} address' + ('es' if count != 1 else '')
    if compact and kind not in ('uint256', 'address[]'):
        return rowfit.clip(strip_tags(value), 24)
    return strip_tags(value)


def consensus_value(row):
    if row.get('panel_answer_type') == 'bool':
        value = row.get('panel_answer_bool')
        return ('YES' if value else 'NO') if type(value) is bool else '—'
    return strip_tags(row.get('panel_figure')) or '—'


def _count(value):
    return str(value) if type(value) is int and value >= 0 else '—'


def panel_text(row, *, detail=False):
    state = row.get('panel_state')
    text, style = {
        'no_quorum_in': ('✓ no-q', 'dim green'), 'no_quorum_out': ('✗ no-q', 'dim red'),
        'blocked': ('blocked', 'dim'), 'off_panel': ('–', 'dim'),
        'not_oracle': ('–', 'dim'), 'not_read': ('not read', 'dim'),
    }.get(state, ('unavail', 'yellow'))
    agreed, quorum, size = (_count(row.get(key)) for key in ('panel_agreed','panel_quorum','panel_size'))
    if state in ('agreed', 'outvoted') and agreed != '—':
        text = f"{'✓' if state == 'agreed' else '✗'} {agreed}" + (f'/{quorum}' if quorum != '—' else '')
        style = 'green' if state == 'agreed' else 'red'
    elif state == 'assessing':
        text = '…' + (f' of {size}' if size != '—' else '')
    if detail:
        word = {'unavail': 'unavailable'}.get(text, text)
        if state in ('agreed', 'outvoted'):
            word = '' if state == 'agreed' else 'outvoted · '
        else:
            word += ' · '
        return Text(f'{word}agreed {agreed} · quorum {quorum} · panel {size} · {consensus_value(row)}', style=style)
    return Text.from_markup(sanitize_cell(text, 9), style=style)


def record_answer(row, width):
    failed = row.get('oracle_member_ok') is False
    raw = ('failed · ' + (strip_tags(row.get('oracle_member_reason')) or '—') if failed
           else seat_value(row, compact=True) + (' · ' + strip_tags(row.get('oracle_notes'))
                                                 if strip_tags(row.get('oracle_notes')) else ''))
    marked, _, spans = mark_addresses(raw)
    cut = rowfit.cell_len(marked) > width
    button = cut and valid_identity(row.get('job_id'), row.get('submission_hash'))
    budget = max(0, width - (2 if button else 0))
    fitted = keep_units(marked, spans, rowfit.clip(marked, budget))
    if cut and not fitted:
        fitted = '…'
    text = Text.from_markup(sanitize_cell(unmark(fitted), budget), style='red' if failed else '')
    link_prose(text, explorer=for_chain_id(row.get('oracle_chain_id')))
    if button:
        text.append(' ').append('»', style=Style(meta={
            '@click': f"screen.open_oracle_answer('{row['job_id']}','{row['submission_hash']}')"}))
    return text
