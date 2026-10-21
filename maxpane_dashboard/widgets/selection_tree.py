"""Tree labels select locally; disclosure icons alone fold with the mouse."""
from textual.widgets import Tree

from maxpane_dashboard.widgets.address import is_copy_click, is_explorer_click


class ClickSelectTree(Tree):
    async def _on_click(self, event):
        event.prevent_default()
        if is_copy_click(event) or is_explorer_click(event):
            await self.app.run_action(event.style.meta['@click'])
            event.stop()
            return
        if event.style.meta.get('toggle'):
            await super()._on_click(event)
        elif isinstance(line := event.style.meta.get('line'), int):
            self.cursor_line = line
            node = self.get_node_at_line(line)
            if node is not None and node.label.plain == 'open full answer »':
                self.action_select_cursor()
        event.stop()
