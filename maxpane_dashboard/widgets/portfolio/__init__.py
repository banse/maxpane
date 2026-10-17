"""Portfolio adapters for the native market dashboard's render-only widgets."""
from rich.text import Text
from textual.widgets import Static

from maxpane_dashboard.widgets.explorer import ETHEREUM
from maxpane_dashboard.widgets.fmt import fmt_int, hhmm
from maxpane_dashboard.widgets.swarm_tokens import (
    TokensHero, TokensTable, NewlyLaunched, BestPlays, TokenActivity,
    _cell, _quantity, _usd, _paired, _chart, _change, _change_color,
)
from maxpane_dashboard.widgets.swarm_tokens.detail import SwarmTokenDetail
from maxpane_dashboard.widgets.markup_safety import flatten

#: Wallet explorer matches THE LIST's wallet prompt. Synthetic token identities
#: deliberately have no explorer target; a live adapter must resolve per chain.
EXPLORER = ETHEREUM


class PortfolioHero(TokensHero):
    BOXES = (("pf-held", "HELD VALUE"), ("pf-claim", "CLAIMABLE"),
             ("pf-agents", "IMD AGENTS"), ("pf-pnl", "P/L"))

    def update_data(self, metrics=None):
        data = metrics or {}
        bodies = []
        for key, label in (("held", "held"), ("claimable", "ready")):
            known, total = data.get(key + '_known'), data.get(key + '_total')
            partial = data.get(key + '_partial') or known is not None and total is not None and known < total
            value = _usd(data.get(key + '_value'))
            if partial and data.get(key + '_value') is not None:
                value = '≥ ' + value
            subtitle = (f'partial · {known} valued' if data.get(key + '_partial') else
                        f'{known}/{total} valued · {label}' if partial else
                        f'{fmt_int(total)} {label} tokens')
            bodies.append((value, subtitle))
        bodies.append((f"{fmt_int(data.get('agents_total'))} linked",
                       f"{fmt_int(data.get('agents_online'))} online · wallet-wide"))
        if data.get('agents_state') not in (None, 'ok'):
            prefix = '~' if data.get('agents_total') is not None else ''
            state = data['agents_state']
            status = '' if state in ('stale', 'unavailable') else f'{state} · '
            bodies[-1] = (prefix + bodies[-1][0],
                          f"{status}as of {hhmm(data.get('agents_as_of'))}")
        pnl = data.get('pnl_usd')
        sign = '+' if pnl is not None and pnl > 0 else '-' if pnl is not None and pnl < 0 else ''
        bodies.append((sign + _usd(abs(pnl)) if pnl is not None else '--',
                       _change(data.get('pnl_percent')) + ' · unrealized' if pnl is not None
                       else '—'))
        for (widget_id, label), (main, sub) in zip(self.BOXES, bodies):
            color = _change_color(pnl) if widget_id == 'pf-pnl' else 'white'
            if data.get('wallet_required'):
                main, sub, color = '--', 'Set a wallet', 'white'
            elif metrics is None:
                main, sub, color = '--', '—', 'white'
            self.render_box('#' + widget_id, label,
                            lambda main=main, sub=sub, color=color: Text(main, style='bold ' + color)
                            + Text('\n' + sub, style='dim white'))


def _measurement(row, key, state):
    if row.get(state) == 'unavailable':
        return '--'
    value = _quantity(row.get(key))
    return ('~' if row.get(state) == 'stale' and value != '--' else '') + value


class PortfolioTable(TokensTable):
    TITLE = 'PORTFOLIO'
    COLUMNS = (("LAUNCH", 6), ("TOKEN", 9), ("CHAIN", 5), ("HELD", 12),
               ("CLAIMABLE", 12), ("HELD USD", 12), ("PRICE", 11), ("24H %", 8),
               ("PAIRED LP", 13), ("PRICE 24H", TokensTable.SPARK_WIDTH + 1))

    def build_row(self, index, item):
        change = item.get('change_24h')
        values = (fmt_int(item.get('launch_id')), item.get('symbol', '--'),
                  flatten(item.get('chain', '--')).upper(),
                  _measurement(item, 'held_quantity', 'balance_state'),
                  _measurement(item, 'claimable_quantity', 'claim_read_state'),
                  _usd(item.get('held_usd')),
                  ('~' if item.get('market_state') == 'stale' else '')
                  + _usd(item.get('price_usd'), price=True), _change(change), _paired(item),
                  ('~' if item.get('history_state') == 'stale' else '') + _chart(item, self.SPARK_WIDTH))
        styles = {1: 'bold', 7: _change_color(change), 9: _change_color(change)}
        for index, state in ((3, 'balance_state'), (4, 'claim_read_state'), (6, 'market_state')):
            if item.get(state, 'ok') != 'ok':
                styles[index] = 'yellow'
        return tuple(_cell(value, width, styles.get(i, ''), right=3 <= i <= 8)
                     for i, (value, (_, width)) in enumerate(zip(values, self.COLUMNS)))


class ClaimableTokens(NewlyLaunched):
    TITLE = 'CLAIMABLE'
    HEADER_LINE = Text('TOKEN     CHAIN    AMOUNT     VALUE  STATE\n', style='#b1b1b1')
    EMPTY_LINE = Text('No ready claims', style='dim white')

    def update_data(self, claimable=None):
        self.render_events(claimable)

    def format_row(self, row):
        state = row.get('claim_read_state', 'ok')
        return (_cell(row.get('symbol', '--'), 10, 'bold')
                + _cell(flatten(row.get('chain', '--')).upper(), 5)
                + _cell(_measurement(row, 'claimable_quantity', 'claim_read_state'), 9, right=True)
                + _cell(_usd(row.get('claimable_usd')), 10, right=True)
                + Text(' ' + ('ready' if state == 'ok' else state),
                       style='' if state == 'ok' else 'yellow'))


class PortfolioActivity(TokenActivity):
    TITLE = 'MARKET ACTIVITY'


class PortfolioMovers(BestPlays):
    TITLE = 'MOVERS / 24H'


class PortfolioDetail(SwarmTokenDetail):
    def compose_sections(self):
        row = self.row
        yield from self.section('YOUR POSITION', Text('Wallet balances and values'
                               + (' · MOCK DATA' if self.is_mock else '')), first=True)
        for label, quantity, value, state in (
            ('Held', 'held_quantity', 'held_usd', 'balance_state'),
            ('Ready to claim', 'claimable_quantity', 'claimable_usd', 'claim_read_state'),
        ):
            yield Static(Text(f'{label:18} {_measurement(row, quantity, state)}  /  {_usd(row.get(value))}'))
        state = row.get('claim_state', 'unavailable')
        if row.get('claim_read_state', 'ok') != 'ok':
            state = row['claim_read_state']
        yield from self.section('CLAIM STATUS', Text(flatten(state)))
        if row.get('claim_reason'):
            yield Static(Text(flatten(row['claim_reason'])))
        if row.get('locked_quantity'):
            yield Static(Text('Locked             ' + _quantity(row['locked_quantity'])))
        if row.get('claimed_quantity'):
            yield Static(Text('Already claimed    ' + _quantity(row['claimed_quantity'])))
        if row.get('unlock_at') is not None and self.as_of is not None:
            remaining = max(0, int(row['unlock_at'] - self.as_of))
            yield Static(Text(f'Unlocks in         {remaining // 60}m {remaining % 60}s'
                              + (' · mock clock' if self.is_mock else ' · at snapshot')))
        if not self.is_mock:
            for label, key in (('Balances', 'balance'), ('Claims', 'claim'), ('Cost basis', 'basis')):
                state_key = 'claim_read_state' if key == 'claim' else key + '_state'
                yield Static(Text(f'{label:18} {flatten(row.get(state_key, "unavailable"))}'
                                  f' · as of {hhmm(row.get(key + "_read_at"))}'))
            if row.get('basis_reason'):
                yield Static(Text(flatten(row['basis_reason'])))
        yield from super().compose_sections()
