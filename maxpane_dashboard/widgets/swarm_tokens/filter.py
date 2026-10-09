"""SWARM TOKENS fields in THE LIST / RECORD's shared filter editor."""
from textual.containers import Grid
from textual.message import Message
from textual.widgets import Input

from maxpane_dashboard.widgets.filter_editor import FilterEditorBase, field_id


class SwarmTokensFilterApplyRequested(Message):
    """Apply this editor's draft."""


class SwarmTokensFilterResetRequested(Message):
    """Clear this editor's draft without applying it."""


class SwarmTokensFilterEditor(FilterEditorBase):
    APPLY_MESSAGE = SwarmTokensFilterApplyRequested
    RESET_MESSAGE = SwarmTokensFilterResetRequested
    SELECT_OPTIONS = {
        'chain': (('Any','any'),('Ethereum','eth'),('Base','base'),('Robinhood','rh')),
        'liquidity': (('Any','any'),('Two-sided','two-sided'),
                      ('One-sided','one-sided'),('Withdrawn / unknown','issues')),
        'sort': (('Volume ↓','any'),('24h change ↓','change'),
                 ('Newest first','newest'),('Token A–Z','symbol')),
    }
    DEFAULT_CSS = '''
    SwarmTokensFilterEditor .filter-group {
        margin-bottom: 0; padding-bottom: 1;
    }
    SwarmTokensFilterEditor .filter-group Select,
    SwarmTokensFilterEditor .filter-group Input { height: 1; }
    '''

    def compose(self):
        yield self.error_line()
        with Grid(classes='filter-groups'):
            yield self.select_group('CHAIN','chain')
            yield self.select_group('LIQUIDITY','liquidity')
            yield self.select_group('SORT','sort')
            yield self.titled_group('SEARCH',Input(
                placeholder='Token, name or launch #', compact=True,
                id=field_id('query'), classes='filter-field'))
        yield self.actions()

    def values(self):
        return dict(super().values(), query=self.query_one('#filter-query',Input).value)

    def set_values(self, values):
        super().set_values(values)
        self.query_one('#filter-query',Input).value=str(values.get('query') or '')
