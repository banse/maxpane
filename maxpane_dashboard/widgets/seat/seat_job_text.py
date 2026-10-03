"""Literal public API question/result rendering shared by JOB and cached detail."""
import textwrap
from rich.text import Text
from maxpane_dashboard.analytics.seat_redact import redact
from maxpane_dashboard.analytics.seat_signals import as_of_hhmm
from maxpane_dashboard.widgets.address import address_prose
from maxpane_dashboard.widgets.explorer import for_chain_id
from maxpane_dashboard.widgets.fmt import DASH, fmt_age, fmt_int
from maxpane_dashboard.widgets.seat_oracle_answer import panel_text
from maxpane_dashboard.widgets.seat_icons import mark_addresses, link_in_order, unmark

API_FIELDS = ('objective', 'reply', 'oracleQuestion', 'oracleAnswer', 'oracleNotes', 'questionState', 'questionReason',
              'questionAsOfUtc', 'replyState', 'replyReason', 'replyAsOfUtc', 'textExpired', 'template', 'paid',
              'launch', 'workflowId', 'oracleRequestId', 'parentJobId', 'delivery', 'structuralCheck', 'panel', 'usage')


def plain(value):
    return redact(str(value)).replace('$', '') if value is not None else ''


def panel_row(panel):
    panel = panel or {}
    return {f'panel_{key}': panel.get(key) for key in ('state', 'agreed', 'quorum', 'size')} | {
        'panel_answer_type': panel.get('answerType'), 'panel_answer_bool': panel.get('answerBool'), 'panel_figure': panel.get('figure')}


def public_prose(value, *, explorer=None, width=None):
    # Fit marked units before linking: the address and its copy icon stay together.
    if width is None:
        return address_prose(plain(value), explorer=explorer)
    width = max(12, width)
    lines, addresses = [], []
    for line in plain(value).split('\n'):
        marked, values, _ = mark_addresses(line, width=min(42, width - 2))
        addresses.extend(values)
        lines.extend(textwrap.wrap(marked, width, break_long_words=True, break_on_hyphens=False) or [''])
    text = Text(unmark('\n'.join(lines)))
    link_in_order([text], addresses, explorer=explorer)
    return text


def _unread(label, state, reason, offline):
    if state == 'text expired':
        return 'text expired'
    if offline:
        return f'{label} unavailable (offline)'
    if state in (None, 'not read', 'not_read'):
        return f'{label} not read yet'
    return f'{label} unavailable (api: {plain(reason) or plain(state) or "unavailable"})'


def api_sections(row, *, working=False, offline=False, width=None):
    """Yield (heading, Text) with independent source states and ledger verdict."""
    oracle = bool(row.get('oracleRequestId') or row.get('oracleQuestion') is not None)
    panel = row.get('panel') or {}
    explorer = for_chain_id(panel.get('chainId')) if oracle else None
    question = row.get('oracleQuestion') if oracle and row.get('oracleQuestion') is not None else row.get('objective')
    stamp = as_of_hhmm(row.get('questionAsOfUtc'))
    heading = 'QUESTION (api' + (f' · as of {stamp}' if stamp else '') + ')'
    text = public_prose(question, explorer=explorer, width=width) if question else Text(_unread('question', row.get('questionState'), row.get('questionReason'), offline), style='dim')
    if offline and question:
        heading = 'QUESTION (cached)'
    yield heading, text
    answer = row.get('oracleAnswer') if oracle and row.get('oracleAnswer') is not None else row.get('reply')
    if oracle and panel.get('answerType') == 'bool' and isinstance(answer, str):
        answer = {'true':'YES', 'false':'NO'}.get(answer, answer)
    if working:
        text = Text(f'in progress · {plain(row.get("phase")) or DASH}', style='yellow')
        if row.get('elapsedS') is not None:
            text.append(f' · {row["elapsedS"]:g} s')
        if row.get('lastMessage'):
            text.append('\n').append_text(public_prose(row['lastMessage']))
    elif answer is not None:
        text = public_prose(answer, explorer=explorer, width=width)
    else:
        text = Text(_unread('reply', row.get('replyState'), row.get('replyReason'), offline), style='dim')
    if oracle and row.get('oracleNotes'):
        text.append('\n').append_text(public_prose(row['oracleNotes'], explorer=explorer, width=width))
    stamp = as_of_hhmm(row.get('replyAsOfUtc'))
    if oracle:
        text.append('\n').append_text(panel_text(panel_row(panel), detail=True))
    heading = 'RESULT (api' + (f' · as of {stamp}' if stamp else '') + ')'
    if offline and answer is not None and not working:
        heading = 'RESULT (cached)'
    yield heading, text


def facts(row):
    paid = row.get('paid')
    text = Text('paid: ' + ('yes (api paidBy)' if paid is True else 'no payer' if paid is False else 'not known'), style='dim')
    if row.get('template'):
        text.append(' · ' + plain(row['template']))
    launch = row.get('launch') or {}
    if launch:
        text.append(' · launch ' + (plain(launch.get('kind')) or DASH))
        text.append(' · requested ' + ('yes' if launch.get('requested') is True else 'no' if launch.get('requested') is False else DASH))
    workflow = row.get('workflowId') or launch.get('workflowId')
    if workflow:
        text.append(' · workflow ' + plain(workflow))
    delivery = row.get('delivery') or {}
    if delivery:
        text.append('\ndelivered ' + (as_of_hhmm(delivery.get('atUtc')) or DASH) + ' · ' + plain(delivery.get('url')))
    return text


def outcome_usage(row):
    text = Text()
    outcome = plain(row.get('outcome'))
    if outcome:
        verdict = outcome
        if outcome == 'accepted' and (lag := fmt_age(row.get('verdictLagS'))) != DASH:
            verdict += f' (+{lag})'
        elif outcome == 'failed' and row.get('failureReason'):
            verdict += ' ' + plain(row['failureReason'])
        text.append(verdict, style={'accepted':'green', 'rejected':'red', 'failed':'red', 'pending':'yellow'}.get(outcome, 'dim'))
    check = row.get('structuralCheck') or {}
    if check:
        text.append('\ncheck: ' + (plain(check.get('evaluation')) or plain(check.get('status')) or DASH), style='dim')
        if check.get('detail'):
            text.append(' — ' + plain(check['detail']), style='dim')
    use = row.get('usage') or {}
    words = []
    if use.get('model'):
        words.append(plain(use['model']))
    if use.get('turns') is not None:
        words.append(f'{use["turns"]} turns')
    tokens = use.get('tokens') or {}
    if tokens.get('output') is not None:
        words.append('out ' + fmt_int(tokens['output']))
    duration = use.get('wallS')
    if duration is None and use.get('wallMs') is not None:
        duration = use['wallMs'] / 1000
    if duration is not None:
        words.append(f'took {duration:g} s')
    if words:
        text.append('\n' + ' · '.join(words), style='dim')
    return text
