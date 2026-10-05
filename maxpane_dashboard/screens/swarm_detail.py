"""Cached SWARM workflow and throughput detail views."""
from rich.text import Text
from textual.widgets import Static

from maxpane_dashboard.screens.record_detail import RecordDetailScreen
from maxpane_dashboard.widgets.address import job_text
from maxpane_dashboard.widgets.markup_safety import flatten, sanitize_cell
from maxpane_dashboard.widgets.surf._fmt import JOB_EXPLORER, mmdd_hhmm
from maxpane_dashboard.widgets.surf._icons import link_prose, mark_addresses, unmark
from maxpane_dashboard.widgets.surf.swarm_throughput import throughput_detail_blocks


def _prose(value) -> Text:
    marked, _, _ = mark_addresses(flatten(value))
    return link_prose(Text(unmark(marked) or '—'), explorer=None)


class WorkflowDetailScreen(RecordDetailScreen):
    TITLE_WORD = 'WORKFLOW'
    ID_PREFIX = 'workflow-detail'

    def compose_sections(self):
        row = self.row
        yield from self.section('STATUS', _prose(row.get('status')), first=True)
        yield from self.section('CREATED / UPDATED', Text(
            f"{mmdd_hhmm(row.get('created_ts'))} / {mmdd_hhmm(row.get('updated_ts'))}"))
        yield from self.section('CONTRACTS JOB', job_text(row.get('contracts_job_id'), 36, explorer=JOB_EXPLORER))
        yield from self.section('FRONTEND JOB', job_text(row.get('frontend_job_id'), 36, explorer=JOB_EXPLORER))
        waiting = row.get('waiting_for_hosting')
        word = 'yes' if waiting is True else 'no' if waiting is False else 'unavailable'
        yield from self.section('WAITING FOR HOSTING', Text(word, style='yellow' if word == 'unavailable' else ''))
        yield from self.section('OBJECTIVE', _prose(row.get('objective')))
        yield from self.section('FAILURE', _prose(row.get('failure')))

    def _title(self):
        title = self.query_one('.record-detail-title', Static)
        title.update(Text.from_markup(sanitize_cell(
            f"WORKFLOW · {self.row.get('workflow_id') or '—'}", title.size.width), style='bold'))


class ThroughputDetailScreen(RecordDetailScreen):
    TITLE_WORD = 'THROUGHPUT'
    ID_PREFIX = 'throughput-detail'

    def compose_sections(self):
        yield Static(Text(), id='throughput-detail-states')
        yield Static(Text(), id='throughput-detail-cancels', classes='record-detail-heading')

    def _title(self):
        self.query_one('.record-detail-title', Static).update(Text(self.TITLE_WORD, style='bold'))
        states = self.query_one('#throughput-detail-states', Static)
        cancels = self.query_one('#throughput-detail-cancels', Static)
        state_text, cancel_text = throughput_detail_blocks(self.row, states.content_size.width)
        states.update(state_text)
        cancels.update(cancel_text)
