"""A nested documentation screen and its cached, dated source popup."""
from rich.text import Text
from textual import on
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.widgets import Static

from maxpane_dashboard.screens.dashboard_screen import keys
from maxpane_dashboard.screens.record_detail import RecordDetailScreen
from maxpane_dashboard.screens.surf_loading import SurfDashboardScreen, SurfStatusBar
from maxpane_dashboard.widgets.markup_safety import flatten, strip_controls
from maxpane_dashboard.widgets.rowfit import cell_len, clip
from maxpane_dashboard.widgets.workflow_guide import WorkflowGuideView


#: Measured 2026-10-18 with the genuine bundled document in Matrix at 149×45.
#: The guide has its own width; the app-wide 143-column recommendation is unchanged.
#: Six nine-row capacity heroes are restored above the unchanged framed diagram.
#: Their one-row lower margin and the three-row topic strip use 13 viewport rows.
#: The view's 143-column floor plus its composed padding/gutter needs 148 columns.
#: At 147 columns the outer viewport scrolls one column; 148 clears it.
#: Both the closed and 28-column expanded topic index preserve every diagram node.
#: Native inset nodes use four rows with two centered label rows and full-box clicks.
#: At the width boundary five-column graphs use 106 cells with index open.
#: At 149 columns they use 110 cells open and 135 closed, including branch rails.
#: CONTRACTS is tallest: six parallel stages stack spatially into 24 diagram rows.
#: Its figure adds four title/source rows; its source link is outside graph scrolling.
#: The complete graph plus heroes clears at 44 rows; at 43 the graph scrolls one row.
#: The lower nine-row detail group appears only when the whole diagram also fits.
#: CONTRACTS details are hidden at 52 rows and return at 53, with either index state.
#: At 149×45 all graphs fit; purchase, single skill, company and intake show details.
#: At 24 rows graphs scroll internally while SOURCE DETAILS remains visible.
#: At narrower widths the horizontal scrollbar may consume one vertical row.
#: Source popup uses the existing RecordDetailScreen frame and scroll behavior.
#: Default screen CSS and the production stylesheet are checked for agreement.
#: Boundary tests compare actual overflow and painted hints on both sides of each pin.
WORKFLOW_GUIDE_FULL_LAYOUT_COLUMNS = 148
WORKFLOW_GUIDE_FULL_LAYOUT_ROWS = 44
WORKFLOW_GUIDE_DETAILS_ROWS = 53


class WorkflowSourceScreen(RecordDetailScreen):
    ID_PREFIX = 'workflow-source-popup'

    def __init__(self, source, topic, node=None):
        super().__init__({'source': source, 'topic': topic, 'node': node or {}})

    def compose_sections(self):
        source, topic, node = (self.row[key] for key in ('source', 'topic', 'node'))
        guidance = '\n'.join(
            flatten(card.get('title')) + ': ' + ' · '.join(filter(None, [
                flatten(card.get('heading')), flatten(card.get('value')),
                *[flatten(row) for row in card.get('rows') or []],
                flatten(card.get('caption')), flatten(card.get('footer'))]))
            for card in node.get('guidance') or [])
        guidance += '\n\n' + '\n'.join(node.get('guidance_notes') or [])
        for title, value in (
            ('SOURCE SNAPSHOT', f"{source.get('title', '—')}\nDOCUMENTED {source.get('date', '—')}\n"
             f"Plane {source.get('plane', '—')} · Worker {source.get('worker', '—')}"),
            ('SELECTED NODE', node.get('label') or topic.get('title') or '—'),
            ('EXPLANATION', node.get('explanation') or topic.get('summary') or '—'),
            ('LIMITS', '\n'.join(node.get('limits') or []) or '—'),
            ('DOCUMENTED EXAMPLE', node.get('example') or '—'),
            ('NODE SOURCE EXCERPT', node.get('source_excerpt') or '—'),
            ('TOPIC SOURCE EXCERPT', topic.get('source_excerpt') or '—'),
            ('REFERENCES', '\n'.join(source.get('references') or []) or '—'),
            ('CAPACITY & ALTERNATIVES', guidance.strip() or '—'),
            ('DOCUMENTED FACTS', '\n'.join(
                f"{flatten(stat.get('title'))}: {flatten(stat.get('value'))} · {flatten(stat.get('caption'))}"
                for stat in topic.get('stats') or []) or '—'),
        ):
            yield from self.section(title, Text(strip_controls(str(value))), first=title == 'SOURCE SNAPSHOT')

    def _title(self):
        source, topic = self.row['source'], self.row['topic']
        self.query_one('.record-detail-title', Static).update(Text(
            'WORKFLOWS · DOCUMENTED ' + flatten(source.get('date')) + ' · ' + flatten(topic.get('title')),
            style='bold'))


class WorkflowGuideScreen(SurfDashboardScreen):
    GAME_NAME = 'WORKFLOWS'
    REFRESH_WORKER_NAME = 'workflow-guide-refresh'
    POLL_DATA = False
    PANELS = ((WorkflowGuideView, keys('workflow_guide')),)
    BINDINGS = [Binding('escape', 'back', show=False), Binding('i', 'index', show=False),
                Binding('left', 'topic(-1)', show=False, priority=True),
                Binding('right', 'topic(1)', show=False, priority=True),
                Binding('up', 'node(-1)', show=False, priority=True),
                Binding('down', 'node(1)', show=False, priority=True),
                Binding('enter', 'source', show=False)]
    DEFAULT_CSS = '''
    WorkflowGuideScreen {background: $background; color: $text;}
    WorkflowGuideScreen #workflow-title {height: 1; margin: 1 1 0 1; text-wrap: nowrap;}
    WorkflowGuideScreen #workflow-viewport {height: 1fr; padding: 0 1; overflow: auto auto;
        scrollbar-gutter: stable; scrollbar-size: 1 1;}
    WorkflowGuideScreen WorkflowGuideView {width: 1fr; min-width: 143; height: 1fr; min-height: 21;}
    WorkflowGuideScreen #workflow-heroes {height: 9; margin-bottom: 1; grid-size: 6 1;
        grid-columns: 1fr; grid-rows: 9; grid-gutter: 0 1;}
    WorkflowGuideScreen #workflow-topics {height: 2; margin-bottom: 1; text-wrap: nowrap;}
    WorkflowGuideScreen #workflow-main {height: 1fr; min-height: 8;}
    WorkflowGuideScreen #workflow-index {width: 28; height: 1fr; margin-right: 1; display: none;}
    WorkflowGuideScreen #workflow-reading {width: 1fr; height: 1fr;}
    WorkflowGuideScreen #workflow-figure {height: 1fr; min-height: 8;}
    WorkflowGuideScreen #workflow-diagram {height: 1fr;}
    WorkflowGuideScreen #workflow-diagram-content {height: auto; text-wrap: nowrap;}
    WorkflowGuideScreen #workflow-source {height: 1; margin: 0 1 1 1; text-wrap: nowrap;}
    WorkflowGuideScreen #workflow-details {height: 9; min-height: 9;}
    WorkflowGuideScreen #workflow-details > _GuidePanel {width: 1fr; height: 1fr;}
    WorkflowGuideScreen #workflow-explanation {margin-right: 1;}
    WorkflowGuideScreen #workflow-limits {margin-right: 1;}
    WorkflowGuideScreen _GuidePanel {border: none;}
    WorkflowGuideScreen .panel-title {height: 1; padding: 0 1; margin-bottom: 1;
        color: $text-muted; text-wrap: nowrap; text-overflow: ellipsis;}
    WorkflowGuideScreen .workflow-panel-scroll {height: 1fr; padding: 0 1; overflow: auto auto;
        scrollbar-gutter: stable; scrollbar-size: 1 1;}
    WorkflowGuideScreen .workflow-panel-content {height: auto; width: 100%;}
    '''

    def __init__(self, manager, *, view_state=None, poll_interval=30, **kwargs):
        super().__init__(manager, poll_interval, **kwargs)
        self._view_state = view_state if isinstance(view_state, dict) else {}

    def compose(self):
        yield Static(Text('WORKFLOWS'), id='workflow-title')
        with VerticalScroll(id='workflow-viewport'):
            yield WorkflowGuideView(selection=self._view_state)
        yield SurfStatusBar()

    def on_mount(self):
        self.query_one('#workflow-viewport', VerticalScroll).focus()

    def on_resize(self):
        self.call_after_refresh(self._chrome)

    @on(WorkflowGuideView.Changed)
    def _selection_changed(self, event):
        event.stop()
        self._view_state.update(event.state)
        self.call_after_refresh(self._chrome)

    @on(WorkflowGuideView.SourceRequested)
    def _source_requested(self, event):
        event.stop()
        self.app.push_screen(WorkflowSourceScreen(event.source, event.topic, event.node))

    def _chrome(self):
        view = self.query_one(WorkflowGuideView)
        viewport = self.query_one('#workflow-viewport', VerticalScroll)
        suffix = ' · ‹ widen' if viewport.max_scroll_x > 0 or view.needs_widen else ''
        diagram = view.query_one('#workflow-diagram-scroll', VerticalScroll)
        suffix += ' · ‹ taller' if viewport.max_scroll_y > 0 or diagram.max_scroll_y > 0 else ''
        title = self.query_one('#workflow-title', Static)
        caption = 'WORKFLOWS · DOCUMENTED ' + (flatten(view.source.get('date')) or '—')
        title.update(Text(clip(caption, max(1, title.size.width - cell_len(suffix))) + suffix))

    def action_topic(self, delta):
        self.query_one(WorkflowGuideView).move_topic(delta)

    def action_node(self, delta):
        self.query_one(WorkflowGuideView).move_node(delta)

    def action_index(self):
        self.query_one(WorkflowGuideView).toggle_index()

    def action_source(self):
        self.query_one(WorkflowGuideView).open_source()

    def action_back(self):
        self.app.pop_screen()
