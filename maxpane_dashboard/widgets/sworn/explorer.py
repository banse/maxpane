"""Selected-first card browsing; all paints consume reader-published values."""
from rich.style import Style
from rich.text import Text
from textual.containers import Horizontal, VerticalScroll
from textual.message import Message
from textual.widgets import DataTable, Static

from maxpane_dashboard.widgets.markup_safety import flatten
from maxpane_dashboard.widgets.panels import PanelBase
from .art import SwornArt
from .details import SwornFacts


class _CardTable(DataTable):
    async def _on_click(self, event):
        event.prevent_default(); event.stop()
        action = event.style.meta.get('@click', '')
        if action.startswith('screen.inspect_card('):
            await self.app.run_action(action)
        else:
            row = event.style.meta.get('row')
            if type(row) is int and 0 <= row < self.row_count:
                self.move_cursor(row=row)


class _Cards(PanelBase):
    TITLE = 'CARDS'
    def compose_body(self):
        yield _CardTable(id='sworn-cards', cursor_type='row', show_row_labels=False, cell_padding=1)


class _Artwork(PanelBase):
    TITLE = 'SWORN'
    def compose_body(self):
        yield SwornArt(id='sworn-art')
        yield Static(Text('» ARTWORK & SOURCE DETAILS', style=Style(meta={'@click': 'screen.inspect'})), id='sworn-inspect')


class SwornExplorer(PanelBase):
    TITLE = 'SWORN / EXPLORER'
    # After the live 149x45 preview: at 105 terminal columns the fixed 24-cell
    # list, 46-cell facts rail and gutters leave the complete 26-cell art link.
    # Below this, stack the body. The outer scroll keeps the body reachable
    # in short terminals; the artwork fills all space below the one-line title.
    DEFAULT_CSS = '''
    SwornExplorer {height: 1fr; overflow-y: auto; scrollbar-gutter: stable; scrollbar-size: 1 1;}
    SwornExplorer > .panel-title {height: 1; margin-bottom: 0;}
    SwornExplorer #sworn-message {height: auto; color: $text-muted;}
    SwornExplorer #sworn-content {height: 1fr; min-height: 16;}
    SwornExplorer #sworn-body {height: 1fr; min-height: 16;}
    SwornExplorer _Cards {width: 24; height: 1fr; min-height: 16; margin-right: 1;}
    SwornExplorer DataTable {height: 1fr; scrollbar-size: 1 1;}
    SwornExplorer _Artwork {width: 1fr; height: 1fr; min-height: 16; margin-right: 1;}
    SwornExplorer SwornArt {height: 1fr; min-height: 1;}
    SwornExplorer #sworn-inspect {height: 1; color: $primary;}
    SwornExplorer SwornFacts {width: 46;}
    SwornExplorer.compact #sworn-body {layout: vertical; height: auto;}
    SwornExplorer.compact _Cards {width: 100%; height: 9; min-height: 9;}
    SwornExplorer.compact _Artwork {width: 100%; height: 24;}
    SwornExplorer.compact SwornFacts {width: 100%; height: 24;}
    '''
    class Select(Message):
        def __init__(self, value):
            super().__init__(); self.value = value

    class Inspect(Message):
        def __init__(self, card):
            super().__init__(); self.card = card

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.selected = None; self.rows = []; self.supply = None
        self.requested = None; self._waiting_popup = False

    def compose_body(self):
        yield Static(Text(), id='sworn-message')
        with VerticalScroll(id='sworn-content'):
            with Horizontal(id='sworn-body'):
                yield _Cards()
                yield _Artwork()
                yield SwornFacts(id='sworn-facts')

    def on_mount(self):
        title = Text(self.TITLE + '  ·  ')
        title.append('w wallet', style=Style(meta={'@click': 'screen.search'}))
        self.query_one('.panel-title', Static).update(title)
        table = self.query_one(DataTable)
        for label, width in (('ID', 5), ('FAMILIES', 8), ('', 1)):
            table.add_column(label, width=width)
        self.on_resize()

    def on_resize(self):
        self.set_class(self.screen.size.width < 105, 'compact')

    def request(self, value, *, inspect=False):
        self.requested = value; self._waiting_popup = inspect
        if not self.selected or str(self.selected['token_id']) != value:
            self.selected = None
            self._show_selection()

    def _show_selection(self):
        card = self.selected
        self.query_one(SwornArt).update_art(card.get('art') if card else None)
        self.query_one(_Artwork).query_one('.panel-title', Static).update(Text(f"SWORN #{card['token_id']}" if card else 'SWORN'))
        self.query_one(SwornFacts).show_card(card)

    def update_data(self, *, sworn_supply=None, sworn_rows=None, sworn_selected=None,
                    sworn_selection=None, sworn_error=None, sworn_block=None, sworn_observed_at=None):
        self.supply = sworn_supply
        if sworn_selection != self.requested:
            return
        self.selected = sworn_selected
        self.rows = sworn_rows or []
        message = sworn_error or ('No cards minted yet' if sworn_supply == 0 else '')
        self.query_one('#sworn-message', Static).update(Text(flatten(message)))
        table = self.query_one(DataTable)
        with table.prevent(DataTable.RowHighlighted):
            table.clear()
            for row in self.rows:
                token = row['token_id']; families = row.get('families')
                table.add_row(Text(str(token)), Text('—' if families is None else f'{families}/13'),
                    Text('»', style=Style(meta={'@click': f'screen.inspect_card({token})'})), key=str(token))
            if self.selected:
                ids = [row['token_id'] for row in self.rows]
                if self.selected['token_id'] in ids:
                    table.move_cursor(row=ids.index(self.selected['token_id']))
        self._show_selection()
        if self._waiting_popup and self.selected:
            self._waiting_popup = False
            self.post_message(self.Inspect(self.selected))

    def on_data_table_row_highlighted(self, event):
        event.stop()
        if event.row_key.value and str((self.selected or {}).get('token_id')) != event.row_key.value:
            self.post_message(self.Select(event.row_key.value))

    def on_data_table_row_selected(self, event):
        event.stop()
        self.screen.action_inspect_card(int(event.row_key.value))
