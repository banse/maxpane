"""A bounded, cached submission snapshot; opening never reads an endpoint."""
import math

from rich.text import Text

from maxpane_dashboard.screens.record_detail import RecordDetailScreen
from maxpane_dashboard.widgets.address import address_prose
from maxpane_dashboard.widgets.fmt import hhmm
from maxpane_dashboard.widgets.surf._fmt import short_model
from maxpane_dashboard.widgets.surf._oracle_answer import _STATE_COLORS, tok_text


def _prose(value, *, style=''):
    return address_prose(str(value) if value is not None else '—', explorer=None, style=style)


def _count(value):
    return str(value) if type(value) is int and value >= 0 else '—'


def _runtime(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        return '—'
    minutes, seconds = divmod(int(value), 60)
    return f'{minutes}m {seconds:02d}s'


class SubmissionDetailScreen(RecordDetailScreen):
    TITLE_WORD = 'SUBMISSION'
    ID_PREFIX = 'submission-detail'
    SHOW_ROLE = True

    def compose_sections(self):
        row = self.row
        state = row.get('job_detail_state')
        if row.get('job_read') == 'read':
            job = str(state or '—')
            if row.get('job_blocked_reason'):
                job += ' · ' + row['job_blocked_reason']
        else:
            job = 'not read yet' if row.get('job_read') == 'not_read' else 'unavailable'
        if row.get('job_read') != 'not_read' and row.get('job_read_ts') is not None:
            job += ' · as of ' + hhmm(row['job_read_ts'])
        yield from self.section('JOB', _prose(job, style=_STATE_COLORS.get(state, '')), first=True)
        nodes = Text()
        for node in row.get('job_nodes') or []:
            if nodes:
                nodes.append(' · ')
            words = f"{node.get('key') or '—'} {node.get('state') or '—'}"
            if node.get('attempt'):
                words += ' ' + _count(node['attempt'])
            if node.get('failure_reason'):
                words += ' ' + node['failure_reason']
            nodes.append_text(_prose(words, style=_STATE_COLORS.get(node.get('state'), '')))
        yield from self.section('NODES', nodes if nodes else Text('—'))
        yield from self.section('OBJECTIVE', _prose(row.get('objective')))
        status = row.get('work_status') or row.get('job_state') or '—'
        this_seat = str(status)
        if row.get('sub_failure_reason'):
            this_seat += ' · ' + row['sub_failure_reason']
        usage = ' · '.join([short_model(row.get('model')) or '—', _count(row.get('sub_turns'))+' turns',
            _runtime(row.get('took_s')), tok_text(row.get('output_tokens'))+' out',
            tok_text(row.get('sub_cached_input_tokens'))+' cached in'])
        artifacts = ', '.join(f"{a['name']} ({_count(a.get('bytes'))} bytes)" for a in row.get('sub_artifacts') or []) or '—'
        facts = f"checks failed: {row.get('sub_failed_checks') or '—'} · findings {_count(row.get('sub_findings'))} · artifacts {artifacts}"
        yield from self.section('THIS SEAT', _prose(this_seat, style=_STATE_COLORS.get(status, '')), _prose(usage), _prose(facts))
        reply = []
        if row.get('sub_failure_reason') == 'local_build_failed':
            reply.append(Text('published excerpt only — the build error may not be in it', style='dim'))
        reply.append(_prose(row.get('sub_reply')))
        yield from self.section('REPLY', *reply)
        # The data layer uses None for oracle jobs; an empty list is a read with no other seats.
        if row.get('sub_others') is not None:
            others = []
            for other in row['sub_others']:
                outcome = other.get('failure_reason') or other.get('outcome') or '—'
                others.append(_prose(f"{other['node_key']}  #{other['token']}  {outcome}  {other['line']}"))
            total = row.get('sub_others_total')
            if type(total) is int and total > len(others):
                others.append(Text(f'+{total-len(others)} more', style='dim'))
            yield from self.section(f'OTHER SEATS ON THIS JOB ({_count(total)})', *others)
