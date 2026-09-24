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

#: Panel glyph, space and three-digit agreed/quorum counts (105/112).
_PANEL_COLS = 1 + 1 + 3 + 1 + 3
_STATE_COLORS = {'completed': 'green', 'failed': 'red', 'cancelled': 'red',
                 'rejected': 'red', 'pending': 'yellow'}


def failed_answer(row):
    return 'failed · ' + (strip_tags(row.get('oracle_member_reason')) or '—')


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
    if isinstance(kind, str) and kind.endswith('[]') and compact:
        count = len(value.split())
        noun = 'address' if kind == 'address[]' else 'value'
        return f'{count} {noun}' + (('es' if kind == 'address[]' else 's') if count != 1 else '')
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
    return Text.from_markup(sanitize_cell(text, _PANEL_COLS), style=style)


def can_open_submission(row):
    return (not joined(row) and row.get('answer_state') in ('read', 'no_reply')
            and valid_identity(row.get('job_id'), row.get('submission_hash')))


def record_answer(row, width):
    failed = row.get('oracle_member_ok') is False
    raw = (failed_answer(row) if failed
           else seat_value(row, compact=True) + (' · ' + strip_tags(row.get('oracle_notes'))
                                                 if strip_tags(row.get('oracle_notes')) else ''))
    return fit_popup_text(row, raw, width, 'open_oracle_answer',
                          style='red' if failed else '', explorer=for_chain_id(row.get('oracle_chain_id')))[0]


def fit_popup_text(row, raw, width, action=None, *, force=False, style='', explorer=None):
    marked, _, spans = mark_addresses(raw)
    cut = rowfit.cell_len(marked) > width
    button = bool(action) and (cut or force) and valid_identity(row.get('job_id'), row.get('submission_hash'))
    budget = max(0, width - (2 if button else 0))
    fitted = keep_units(marked, spans, rowfit.clip(marked, budget))
    if cut and not fitted:
        fitted = '…'
    text = Text.from_markup(sanitize_cell(unmark(fitted), budget), style=style)
    link_prose(text, explorer=explorer)
    if button:
        text.append(' ').append('»', style=Style(meta={
            '@click': f"screen.{action}('{row['job_id']}','{row['submission_hash']}')"}))
    return text, cut, button
