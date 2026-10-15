"""Pure selected-token display helpers; address actions remain shared."""
from rich.text import Text

from maxpane_dashboard.widgets.address import PROSE_ADDRESS_RE, address_prose
from maxpane_dashboard.widgets.explorer import for_chain_id
from maxpane_dashboard.widgets.fmt import hhmm
from maxpane_dashboard.widgets.markup_safety import flatten
from maxpane_dashboard.widgets.rowfit import clip, pad
from maxpane_dashboard.widgets.surf._icons import fit_prose, link_prose

EXPLORER = for_chain_id


def metric_label(value):
    """A compact metric face cannot own an address's copy/explorer actions."""
    return PROSE_ADDRESS_RE.sub('token', flatten(value))


def source(sources, name):
    item = (sources or {}).get(name) or {}
    return dict(state=flatten(item.get('state')) or 'unavailable', read_ts=item.get('read_ts'),
                partial=bool(item.get('partial')) or item.get('state') == 'partial')


def token_source(token, name):
    return dict(state=flatten(token.get(name + '_state')) or 'unavailable',
                read_ts=token.get(name + '_read_at'))


def source_label(item):
    state = item.get('state', 'unavailable')
    if item.get('partial') and state != 'partial':
        state += ' · partial'
    return ('' if state == 'ok' else state + ' · ') + 'as of ' + hhmm(item.get('read_ts'), unknown='--:--')


def title(panel, item):
    label = panel.TITLE + ' · ' + source_label(item)
    panel.write('.panel-title', Text(label, style='bold', no_wrap=True, overflow='ellipsis'))
    panel.tooltip = Text(label)


def prose(value, chain_id=None):
    return address_prose(flatten(value) or '--', explorer=EXPLORER(chain_id))


def cell(value, width, chain_id=None):
    return link_prose(fit_prose(flatten(value) or '--', width), EXPLORER(chain_id))


def line(label, value, chain_id=None):
    return Text(pad(clip(metric_label(label), 12), 13), style='dim').append_text(
        value if isinstance(value, Text) else prose(value, chain_id))
