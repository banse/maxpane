"""Selectable collection identities; names never become record keys."""
from rich.style import Style
from rich.text import Text
from textual.message import Message
from textual.widgets import DataTable, Static

from maxpane_dashboard.widgets.address import address_text, is_address, is_copy_click, is_explorer_click
from maxpane_dashboard.widgets.markup_safety import flatten
from maxpane_dashboard.widgets.panels import TableLeaderboard
from maxpane_dashboard.widgets.rowfit import clip, cell_len
from . import EXPLORER


class _CollectionTable(DataTable):
    async def _on_click(self,event):
        event.prevent_default(); event.stop()
        action=event.style.meta.get('@click','')
        if is_copy_click(event) or is_explorer_click(event) or action.startswith('screen.open_nft_detail('):
            await self.app.run_action(action)
            return
        row=event.style.meta.get('row')
        if type(row) is int and 0<=row<self.row_count:
            self.move_cursor(row=row)


class NftTable(TableLeaderboard):
    TITLE='COLLECTIONS'
    TABLE_ID='nft-table'
    ROW_CAP=None
    UNAVAILABLE_LINE='—'
    COLUMNS=(('COLLECTION',23),('CHAIN',5),('MINT',13),('IDMD',11),('MINTED/MAX',12))

    class Highlighted(Message):
        def __init__(self, row):
            super().__init__(); self.row=row

    class Selected(Highlighted):
        pass

    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.rows={}; self.stage='launched'; self._as_of=None; self.clipped=False

    def compose_body(self):
        yield _CollectionTable(id=self.TABLE_ID,cell_padding=1)

    def selected_row(self):
        table=self.query_one(DataTable)
        if not table.row_count:
            return None
        return self.rows.get(table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value)

    def select_identity(self,identity):
        if identity in self.rows:
            with self.query_one(DataTable).prevent(DataTable.RowHighlighted):
                self.query_one(DataTable).move_cursor(row=list(self.rows).index(identity))

    def build_row(self,index,row):
        name=flatten(row.get('name')) or flatten(row.get('symbol')) or 'Unnamed collection'
        if row.get('contract'):
            label=address_text(row['contract'],label=name,width=21,explorer=EXPLORER(row.get('chain_id')))
        elif is_address(name):
            label=address_text(name,width=21,explorer=EXPLORER(row.get('chain_id')))
        else:
            label=Text(clip(name,23))
        mint=row.get('mint') or {}; benefit=row.get('idmd_benefit') or {}; stats=row.get('stats') or {}
        minted,maximum=stats.get('totalMinted'),stats.get('maxSupply')
        quantity=lambda value: str(value) if type(value) is int and value>=0 else '—'
        values=[{1:'ETH',4663:'RH'}.get(row.get('chain_id'),'—'),
                flatten(mint.get('state')) or 'unknown',flatten(benefit.get('status')) or 'unknown',
                quantity(minted)+'/'+quantity(maximum)]
        widths=[width for _,width in self.COLUMNS[1:]]
        widths[-1]-=2  # Reserve the record popup button inside the existing final column.
        self.clipped |= any(cell_len(value)>width for value,width in zip(values,widths))
        cells=[Text(clip(value,width)) for value,width in zip(values,widths)]
        cells[-1].append(' '*(self.COLUMNS[-1][1]-cells[-1].cell_len-1))
        cells[-1].append('»',style=Style(color='green',meta={'@click':f'screen.open_nft_detail({index})'}))
        return (label,*cells)

    def update_data(self, *, nft_rows=None,nft_build_rows=None,as_of=None):
        current=self.selected_row(); selected=current['id'] if current else None
        values=nft_rows if self.stage=='launched' else nft_build_rows
        self.rows={row['id']:row for row in values or [] if isinstance(row,dict) and isinstance(row.get('id'),str)}
        self._as_of=as_of; self.clipped=False
        table=self.query_one(DataTable)
        with table.prevent(DataTable.RowHighlighted):
            table.clear()
            for index,(identity,row) in enumerate(self.rows.items()):
                table.add_row(*self.build_row(index,row),key=identity)
            if self.rows:
                self.select_identity(selected)
            else:
                message='—' if values is None else 'No matching collections' if self.stage=='launched' else 'No matching projects'
                table.add_row(Text(message),*[Text('') for _ in self.COLUMNS[1:]],key='_empty')
        self.refresh_title()

    def refresh_title(self):
        label='COLLECTIONS' if self.stage=='launched' else 'IN THE MAKING'
        table=self.query_one(DataTable)
        needed=sum(width+2 for _,width in self.COLUMNS)
        marker=' · ‹ widen' if self.clipped or table.content_size.width<needed else ''
        self.query_one('.panel-title',Static).update(Text(f'{label} · {len(self.rows)} shown{marker}',style='bold'))

    def on_resize(self):
        self.call_after_refresh(self.refresh_title)

    def on_data_table_row_highlighted(self,event):
        event.stop()
        self.post_message(self.Highlighted(self.rows.get(event.row_key.value)))

    def on_data_table_row_selected(self,event):
        event.stop()
        self.post_message(self.Selected(self.rows.get(event.row_key.value)))
