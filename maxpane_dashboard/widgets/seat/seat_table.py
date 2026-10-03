"""Seat tables retain the selected row and viewport across snapshot rebuilds.

The shared table bases are intentionally unchanged. Identities are payload keys,
never fitted cell text; the top visible row anchors vertical scrolling too.
"""
from textual.coordinate import Coordinate
from textual.widgets import DataTable
from maxpane_dashboard.widgets.swarm_table import SwarmTableBase


class SeatTable(SwarmTableBase):
    ROW_ID = 'key'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._seat_rows = []
        self._seat_view = None
        self._seat_paint = 0
        self._seat_restore_pending = False

    def selected_row(self):
        try:
            index = self.query_one(DataTable).cursor_row
        except Exception:
            return None
        return self._seat_rows[index] if 0 <= index < len(self._seat_rows) else None

    def remember_view(self):
        # Hidden rebuilds clear the physical scroll position. Keep the saved
        # anchor until a visible paint has actually restored it.
        if not self._seat_rows or self._seat_restore_pending:
            return
        table = self.query_one(DataTable)
        selected = self.selected_row()
        top = min(int(table.scroll_y), len(self._seat_rows) - 1)
        self._seat_view = (selected.get(self.ROW_ID) if selected else None,
                           self._seat_rows[top].get(self.ROW_ID), table.scroll_y - top,
                           table.scroll_x, table.cursor_row, top)

    def build_row(self, index, item):
        cells = super().build_row(index, item)
        if cells is not None and isinstance(item, dict):
            self._seat_rows.append(item)
        return cells

    def _repaint(self):
        if not self.is_mounted:
            return
        table = self.query_one(DataTable)
        if self.is_on_screen:
            self.remember_view()
        self._seat_rows = []
        # A structural rebuild is not a user cursor move. clear() and even
        # move_cursor(scroll=False) otherwise schedule cursor auto-scrolling.
        table.set_reactive(DataTable.cursor_coordinate, Coordinate(0, 0))
        super()._repaint()
        self._seat_paint += 1
        generation = self._seat_paint
        view = self._seat_view
        self._seat_restore_pending = view is not None
        if view is None or not self._seat_rows:
            return
        identities = [r.get(self.ROW_ID) for r in self._seat_rows]
        chosen, anchor, offset, x, old_row, old_top = view
        row = identities.index(chosen) if chosen in identities else min(old_row, len(identities) - 1)
        top = identities.index(anchor) if anchor in identities else min(old_top, len(identities) - 1)
        table.set_reactive(DataTable.cursor_coordinate, Coordinate(row, 0))
        table.refresh()

        def restore_scroll():
            if generation == self._seat_paint and self.is_on_screen:
                table.scroll_to(x=x, y=top + offset, animate=False, force=True, immediate=True)
                self._seat_restore_pending = False
        self.call_after_refresh(restore_scroll)

    def on_show(self):
        if self._payload is not None:
            self.call_after_refresh(self._repaint)
