"""Five newest token, contract and site shipments in a plain aligned list."""
from copy import deepcopy

from rich.cells import cell_len
from rich.text import Text
from textual.message import Message
from textual.widgets import Static

from maxpane_dashboard.analytics.surf_launch_checks import address
from maxpane_dashboard.analytics.surf_launch_sites import is_current_site
from maxpane_dashboard.widgets import rowfit
from maxpane_dashboard.widgets.address import (
    ICON_COLS, address_text, is_copy_click, is_explorer_click, site_text,
)
from maxpane_dashboard.widgets.explorer import for_chain_id
from maxpane_dashboard.widgets.fmt import as_float
from maxpane_dashboard.widgets.markup_safety import flatten
from maxpane_dashboard.widgets.panels import PanelBase
from maxpane_dashboard.widgets.surf._fmt import SITE_EXPLORER


def launch_age(created, now):
    created, now = as_float(created), as_float(now)
    if created is None or now is None:
        return '--'
    seconds = max(0, now-created)
    if seconds < 60:
        return '<1m'
    if seconds < 3600:
        return f'{int(seconds//60)}m'
    if seconds < 86400:
        return f'{int(seconds//3600)}h'
    return f'{int(seconds//86400)}d'


def _rows(value):
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _site_name(row):
    name = flatten(row.get('label') or row.get('ens_name'))
    return name.removesuffix('.sites.imd.fun').removesuffix('.site.identitymd.eth')


def shipped_items(launches, sites):
    """Use live artifacts and successful naming; update times are only proxies."""
    items = []
    launch_rows = _rows(launches)
    for row in launch_rows:
        if row.get('production') is not True or row.get('status') != 'live':
            continue
        artifacts = [a for a in _rows(row.get('artifacts'))
                     if address(a.get('address')) and int(a['address'], 16)]
        timestamp = as_float(row.get('updated_ts'))
        source = 'API update time'
        if timestamp is None:
            timestamp = as_float(row.get('created_ts'))
            source = 'API request time'
        if row.get('kind') != 'evm_contracts':
            artifacts = [a for a in artifacts if a.get('role') == 'token'][:1]
        for artifact in artifacts:
            kind = 'contract' if row.get('kind') == 'evm_contracts' else 'token'
            if kind == 'token':
                ticker = flatten(row.get('ticker'))
                name = ('$' + ticker.lstrip('$')) if ticker else flatten(row.get('token_name'))
            else:
                name = flatten(artifact.get('name'))
            name = name or (('contract ' if kind == 'contract' else '') + f"#{row.get('launch_number', '--')}")
            items.append(dict(kind=kind, name=name, timestamp=timestamp, approximate=True,
                timing=source + ' (approximate; exact deployment time unavailable)',
                address=artifact['address'], chain_id=row.get('chain_id'), launch=deepcopy(row),
                key=('launch', row.get('chain_id'), artifact['address'].lower())))
    for row in _rows(sites):
        if not is_current_site(row) or row.get('status') not in ('named', 'published', 'live'):
            continue
        # Unlinked sites have no chain claim. Exclude confirmed Sepolia joins.
        associated = [launch for launch in launch_rows if
            (row.get('launch_number') is not None and row['launch_number'] == launch.get('launch_number'))
            or (row.get('job_id') and row['job_id'] == launch.get('job_id'))]
        if associated and all(launch.get('chain_id') == 11155111 for launch in associated):
            continue
        name = _site_name(row)
        if not name:
            continue
        items.append(dict(kind='site', name=name, timestamp=as_float(row.get('named_ts')),
            approximate=False, timing='Site naming time', site=deepcopy(row),
            key=('site', flatten(row.get('ens_name')).lower())))
    items.sort(key=lambda item: (item['timestamp'] is not None, item['timestamp'] or 0), reverse=True)
    seen, unique = set(), []
    for item in items:
        if item['key'] not in seen:
            seen.add(item['key'])
            unique.append(item)
    return unique[:5]


class ShippedRow(Static, can_focus=True):
    """Focus, click or Enter selects a launch; links keep their normal actions."""
    BINDINGS = [('enter', 'select', 'Open')]

    def action_select(self):
        self.parent.select_row(self)

    def on_click(self, event):
        if is_copy_click(event) or is_explorer_click(event):
            return
        event.stop()
        self.action_select()


class SurfSwarmLatestLaunches(PanelBase):
    TITLE = 'SHIPPED RECENTLY'
    ROW_CAP = 5
    DEFAULT_CSS = '''
    SurfSwarmLatestLaunches { height: auto; }
    SurfSwarmLatestLaunches > ShippedRow { height: 1; padding: 0 1; link-color: $foreground; }
    SurfSwarmLatestLaunches > ShippedRow:focus { text-style: bold; }
    SurfSwarmLatestLaunches > .shipped-status { height: 1; }
    '''

    class Selected(Message):
        def __init__(self, row):
            super().__init__()
            self.row = deepcopy(row)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._payload = None
        self._top_launch = None

    def compose_body(self):
        yield Static(Text('Loading...', style='dim'), classes='panel-line shipped-status')
        for index in range(self.ROW_CAP):
            yield ShippedRow('', id=f'shipped-row-{index}')

    def on_mount(self):
        self._repaint()

    def on_resize(self):
        self._repaint()

    def update_data(self, swarm_launch_rows=None, swarm_site_rows=None,
                    swarm_launches_as_of_hhmm=None, as_of=None, **_kwargs):
        launches = [deepcopy(row) for row in _rows(swarm_launch_rows) if row.get('production') is True]
        launches.sort(key=lambda row: (as_float(row.get('created_ts')) or 0,
                                       as_float(row.get('launch_number')) or 0), reverse=True)
        self._top_launch = launches[0] if launches else None
        if self._top_launch is not None:
            self._top_launch['as_of'] = as_of
        available = (isinstance(swarm_launch_rows, list), isinstance(swarm_site_rows, list))
        self._payload = dict(rows=shipped_items(swarm_launch_rows, swarm_site_rows),
            available=available, as_of=as_of, marker=swarm_launches_as_of_hhmm)
        for item in self._payload['rows']:
            if 'launch' in item:
                item['launch']['as_of'] = as_of
        self._repaint()

    def top_row(self):
        """The x shortcut still opens the newest production launch snapshot."""
        return deepcopy(self._top_launch)

    def select_row(self, widget):
        index = int(widget.id.rsplit('-', 1)[1])
        rows = (self._payload or {}).get('rows', [])
        if index < len(rows) and 'launch' in rows[index]:
            self.post_message(self.Selected(rows[index]['launch']))

    def _repaint(self):
        if not self.is_mounted:
            return
        payload = self._payload
        items = payload['rows'] if payload else []
        room = max(self.size.width - 2, 0)
        title = self.TITLE
        coverage = ''
        if payload:
            available = payload['available']
            missing = [name for name, present in zip(('Launches', 'Sites'), available) if not present]
            coverage = '; '.join(name + ' unavailable' for name in missing)
            if any(available) and not all(available):
                title += ' · partial'
            if rowfit.has_marker(payload['marker']):
                title += ' · as of ' + rowfit.clip(payload['marker'], 5)
        self.write('.panel-title', Text(rowfit.clip(title, room)))
        self.tooltip = Text(coverage + ('\n' if coverage else '') +
            '~ marks API update/request time, not exact deployment. Sites use naming time.\n'
            'Sorted newest known time first; unknown times last. Click age/type or press Enter to open launch.')
        status = self.query_one('.shipped-status', Static)
        status.display = not items
        if payload:
            word = ('unavailable' if not any(payload['available']) else
                    'no shipped items in available data' if not all(payload['available']) else 'no shipped items yet')
            status.update(Text(rowfit.clip(word, room), style='dim'))
        for index, widget in enumerate(self.query(ShippedRow)):
            widget.display = index < len(items)
            if widget.display:
                item = items[index]
                widget.update(self._item_text(item, room, payload['as_of']))
                widget.tooltip = Text(item['name'] + '\n' + item['timing'] +
                    (' unavailable' if item['timestamp'] is None else '') +
                    ('\n' + coverage if coverage else ''))

    def _item_text(self, item, room, now):
        age = launch_age(item['timestamp'], now)
        if age != '--' and item['approximate']:
            age = '~' + age
        age_width = min(5, max(room - 2, 0))
        # Below 20 cells names take priority over the type, still available on hover.
        type_width = 8 if room >= 20 else 0
        name_width = max(0, room - age_width - 1 - (type_width + 1 if type_width else 0))
        text = Text()
        text.append(rowfit.clip(age, age_width).rjust(age_width), style='dim')
        text.append(' ')
        if item['kind'] == 'site':
            name = site_text(item['name'], name_width, label=item['name'], explorer=SITE_EXPLORER, style='green')
        elif name_width > ICON_COLS:
            name = address_text(item['address'], label=item['name'], width=name_width - ICON_COLS,
                                explorer=for_chain_id(item['chain_id']), style='green')
        else:
            name = Text(rowfit.clip(item['name'], name_width), style='green')
        text.append_text(name)
        text.append(' ' * max(0, name_width-cell_len(name.plain)), style='default')
        if type_width:
            text.append(' ' + rowfit.pad(item['kind'], type_width), style='default')
        return text
