"""Portfolio fields in the existing native draft filter editor."""
from textual.containers import Grid
from textual.widgets import Input
from maxpane_dashboard.widgets.swarm_tokens.filter import SwarmTokensFilterEditor


class PortfolioFilterEditor(SwarmTokensFilterEditor):
    SELECT_OPTIONS = {
        **SwarmTokensFilterEditor.SELECT_OPTIONS,
        'assets': (('Held + claimable', 'any'), ('Held', 'held'), ('Claimable', 'claimable')),
        'sort': (('Held value ↓', 'any'), ('Claimable value ↓', 'claimable'),
                 ('Volume ↓', 'volume'), ('24h change ↓', 'change'),
                 ('Newest first', 'newest'), ('Token A–Z', 'symbol')),
    }

    def compose(self):
        yield self.error_line()
        with Grid(classes='filter-groups'):
            for label, field in (('CHAIN', 'chain'), ('ASSETS', 'assets'),
                                 ('LIQUIDITY', 'liquidity'), ('SORT', 'sort')):
                yield self.select_group(label, field)
        yield self.titled_group('SEARCH', Input(placeholder='Token, name or launch #',
                                               compact=True, id='filter-query', classes='filter-field'))
        yield self.actions()
