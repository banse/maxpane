"""Literal display formats for launch liquidity; no clock or I/O."""
from rich.text import Text

from maxpane_dashboard.widgets import rowfit
from maxpane_dashboard.widgets.address import is_address
from maxpane_dashboard.widgets.fmt import as_float
from maxpane_dashboard.widgets.markup_safety import flatten
from maxpane_dashboard.widgets.sparkline_common import fmt_compact


def fee_percent(value):
    value = as_float(value)
    return '--' if value is None else f'{value/10000:g}%'


def amount(value):
    value = as_float(value)
    if value is None:
        return '--'
    return f'{value:,.2f}'.rstrip('0').rstrip('.') if value >= 1 else f'{value:.4g}'


def liquidity_cell(row):
    value = row.get('liquidity') or {}
    if row.get('production') is not True or value.get('state') == 'na':
        return Text('--', style='dim')
    if value.get('state') in (None, 'unknown'):
        return Text('…', style='dim')
    if value.get('lock') == 'withdrawn':
        return Text('withdrawn', style='red')
    if value.get('range_state') == 'at limit':
        return Text('no liq', style='yellow')
    if value.get('range_state') == 'token only':
        return Text('one-sided', style='dim')
    symbol = flatten(value.get('paired_symbol'))
    if is_address(symbol):
        symbol = '?'  # Unknown currency: never print a sliced, unlinked address.
    paired = as_float(value.get('paired_amount'))
    text = '--' if paired is None else (f'{paired:.2g}' if 0 < paired < 1 else fmt_compact(paired))
    return Text(rowfit.clip(f'{text} {symbol}'.rstrip(), 12))
