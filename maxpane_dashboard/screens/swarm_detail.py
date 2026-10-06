"""Cached SWARM launch, workflow and throughput detail views."""
from rich.text import Text
from textual.widgets import Static

from maxpane_dashboard.screens.record_detail import RecordDetailScreen
from maxpane_dashboard.widgets.address import address_text, job_text, site_text, token_text
from maxpane_dashboard.widgets.explorer import IMD, SITES, for_chain_id
from maxpane_dashboard.widgets.surf._swarm_chain import chain_word
from maxpane_dashboard.analytics.surf_swarm_signals import launch_verdict_label
from maxpane_dashboard.widgets.markup_safety import flatten, sanitize_cell
from maxpane_dashboard.widgets.surf._fmt import JOB_EXPLORER, mmdd_hhmm
from maxpane_dashboard.widgets.surf._icons import link_prose, mark_addresses, unmark
from maxpane_dashboard.widgets.surf.swarm_throughput import throughput_detail_blocks
from maxpane_dashboard.widgets.surf._launch_liquidity import amount, fee_percent
from maxpane_dashboard.widgets.surf.swarm_latest import launch_age
from maxpane_dashboard.widgets.fmt import hhmm

CHECK_DESCRIPTIONS = {
    "K1": "a launch row on a production chain",
    "K2": "deployed by the swarm's launch wallet",
    "K3": "deployed code matches the swarm's attested build",
    "K4": "passed the swarm's admission checks",
    "K6": "who holds the pool liquidity",
    "K7": "outside audits or bounties on record",
    "K8": "pool liquidity: paired amount, range, lock",
}



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


class LaunchDetailScreen(RecordDetailScreen):
    """The selected launch's cached provenance evidence, without a new read."""
    TITLE_WORD = 'LAUNCH'
    ID_PREFIX = 'launch-detail'
    DEFAULT_CSS = '''
    LaunchDetailScreen .launch-check-heading {
        height: 1; text-wrap: nowrap; text-overflow: ellipsis;
    }
    '''

    def _literal(self, value):
        marked, _, _ = mark_addresses(flatten(value))
        return link_prose(Text(unmark(marked) or '—'), explorer=for_chain_id(self.row.get('chain_id')))

    def _evidence(self, value, prefix=''):
        if isinstance(value, dict):
            for key, item in value.items():
                if key != 'rule_version' and item is not None:
                    yield from self._evidence(item, f'{prefix}{flatten(key)}: ')
        elif isinstance(value, list):
            if not value:
                yield self._literal(prefix + 'none')
            for item in value:
                yield from self._evidence(item, prefix)
        else:
            yield self._literal(prefix + ('unavailable' if value is None else str(value)))

    def compose_sections(self):
        row = self.row
        explorer = for_chain_id(row.get('chain_id'))
        ticker = '$' + flatten(row['ticker']) if row.get('ticker') else '--'
        yield from self.section('TOKEN', self._literal(ticker), self._literal(row.get('token_name')), first=True)
        yield from self.section('STATUS / VERDICT', self._literal(
            f"{row.get('status') or '—'} · {launch_verdict_label(row.get('verdict'))}"))
        yield from self.section('PAIR', self._literal(row.get('pair')))
        yield from self.section('POOL FEE', Text(fee_percent(row.get('pool_fee'))))
        yield from self.section('REQUESTER', address_text(row.get('requester'), explorer=explorer))
        yield from self.section('POLICY VERSION', self._literal(row.get('policy_version')))
        artifacts = row.get('artifacts') or []
        yield from self.section('ARTIFACTS', *[
            Text.assemble(self._literal(f"{a.get('role') or 'artifact'} · {a.get('name') or '—'} · "),
                          address_text(a.get('address'), explorer=explorer))
            for a in artifacts if isinstance(a, dict)])
        if row.get('token_address'):
            yield from self.section('IMD TOKEN PAGE', token_text(row['token_address'], explorer=IMD))
        else:
            yield from self.section('JOB', job_text(row.get('job_id'), 36, explorer=JOB_EXPLORER))
        if row.get('site_ens_name') or row.get('site_label'):
            yield from self.section('SITE', site_text(row.get('site_ens_name'), 80,
                label=row.get('site_label'), explorer=SITES), self._literal(
                f"{row.get('site_link_method') or 'unavailable'} · "
                f"{'trusted' if row.get('site_link_trusted') is True else 'untrusted' if row.get('site_link_trusted') is False else 'unavailable'}"))
        else:
            yield from self.section('SITE', Text('none' if row.get('production') is True else '--'))
        checks = row.get('checks') or {}
        for key in ('K1', 'K2', 'K3', 'K4', 'K6', 'K7', 'K8'):
            if row.get('production') is not True:
                yield from self._check_section(key, '--')
                continue
            if key == 'K8':
                liquidity = row.get('liquidity') or checks.get(key) or {}
                yield from self._check_section(key, liquidity.get('state') or 'unknown', *self._liquidity(liquidity))
                continue
            check = checks.get(key) or {}
            evidence = check.get('evidence') or {}
            contents = list(self._evidence(evidence))
            if key == 'K6' and evidence.get('owner'):
                suffix = ' (factory, unverified)' if evidence.get('owner_is_factory') else ' (unverified)'
                contents = [Text.assemble('liquidity held by ',
                    address_text(evidence['owner'], explorer=explorer), suffix)]
                if evidence.get('emitter'):
                    contents.append(Text.assemble('emitter: ', address_text(evidence['emitter'], explorer=explorer)))
            state = 'pass (immutables)' if check.get('state') == 'pass_immutables' else flatten(check.get('state') or 'unknown')
            yield from self._check_section(key, state, *contents)

    def _check_section(self, key, state, *contents):
        heading = Text(f'{key} · {flatten(state)}', style='bold')
        heading.append(' — '+CHECK_DESCRIPTIONS[key], style='dim not bold')
        yield Static(heading, id='launch-check-'+key,
                     classes='record-detail-heading launch-check-heading')
        for content in contents:
            yield Static(content)

    def _liquidity(self, value):
        if value.get('state') in (None, 'unknown', 'na'):
            return
        ticker = flatten(self.row.get('ticker')) or '--'
        yield self._literal(f"paired {amount(value.get('paired_amount'))} {flatten(value.get('paired_symbol'))} · "
                           f"token {amount(value.get('token_amount'))} {ticker} · {value.get('range_state') or '--'}")
        yield Text(f"pool fee {fee_percent(value.get('pool_fee'))} · tick {value.get('tick')} "
                   f"in [{value.get('tick_lower')}, {value.get('tick_upper')}]")
        lock = value.get('lock')
        if lock == 'withdrawn':
            line = Text(f"liquidity withdrawn {amount(value.get('withdrawn_pct'))}% · owner ", style='red')
        elif lock == 'burned':
            line = Text('liquidity burned · owner ')
        else:
            line = Text('liquidity locked in factory ' if value.get('owner_is_factory') is True
                        else 'liquidity held by ')
        line.append_text(address_text(value.get('owner'), width=17, explorer=for_chain_id(self.row.get('chain_id'))))
        if lock == 'locked':
            line.append(' (unverified) · never withdrawn')
        yield line
        share = value.get('share')
        if isinstance(share, (int, float)) and not isinstance(share, bool):
            yield Text(f'launch position {share*100:g}% of active liquidity')
        stamp = value.get('read_ts')
        if stamp is not None:
            age = launch_age(stamp, self.row.get("as_of"))
            suffix = f" · {age} ago" if age != "--" else ""
            yield Text(f"as of {hhmm(stamp)}{suffix}", style="dim")

    def _title(self):
        title = self.query_one('.record-detail-title', Static)
        title.update(Text.from_markup(sanitize_cell(
            f"LAUNCH #{self.row.get('launch_number') or '—'} · {chain_word(self.row.get('chain_id'))}",
            title.size.width), style='bold'))
