"""A literal, dated documentation atlas; selection only repaints local primitives."""
from __future__ import annotations

from rich.style import Style
from rich.text import Text
from textual import on
from textual.containers import Grid, Horizontal, Vertical, VerticalScroll
from textual.geometry import Region
from textual.message import Message
from textual.widgets import Static

from maxpane_dashboard.widgets.markup_safety import flatten, strip_controls
from maxpane_dashboard.widgets.panels import PanelBase
from maxpane_dashboard.widgets.rowfit import cell_len, clip
from maxpane_dashboard.widgets.surf.news_hero import HeroRecord, NewsHeroCard
from maxpane_dashboard.widgets.workflow_guide_diagrams import render_diagram


class _GuideText(Static):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.auto_links = False

    class TopicChosen(Message):
        def __init__(self, index):
            super().__init__()
            self.index = index

    class NodeChosen(Message):
        def __init__(self, index):
            super().__init__()
            self.index = index

    class SourceOpened(Message):
        pass

    def action_choose_topic(self, index):
        self.post_message(self.TopicChosen(index))

    def action_choose_node(self, index):
        self.post_message(self.NodeChosen(index))

    def action_open_source(self):
        self.post_message(self.SourceOpened())


class _GuidePanel(PanelBase):
    def __init__(self, title, *, id):
        super().__init__(id=id)
        self.TITLE = title

    def compose_body(self):
        with VerticalScroll(id=self.id + '-scroll', classes='workflow-panel-scroll'):
            yield _GuideText(Text('—'), id=self.id + '-content', classes='workflow-panel-content')


class WorkflowGuideView(Vertical):
    """The one dispatch target; internal controls never acquire data."""

    class Changed(Message):
        def __init__(self, state):
            super().__init__()
            self.state = state

    class SourceRequested(Message):
        def __init__(self, source, topic, node):
            super().__init__()
            self.source, self.topic, self.node = source, topic, node

    def __init__(self, *, selection=None, **kwargs):
        super().__init__(**kwargs)
        state = selection or {}
        self.topic_id = state.get('topic_id', 'contracts')
        self.node_id = state.get('node_id')
        self.index_open = bool(state.get('index_open', False))
        self.source = {}
        self.topics = []
        self._strip_cut = False
        self._diagram_boxes = {}

    def compose(self):
        with Grid(id='workflow-heroes'):
            for record in self._hero_records():
                yield NewsHeroCard(record)
        with Horizontal(id='workflow-main'):
            yield _GuidePanel('TOPIC INDEX', id='workflow-index')
            with Vertical(id='workflow-reading'):
                yield _GuideText(Text(), id='workflow-source')
                with Horizontal(id='workflow-details'):
                    yield _GuidePanel('EXPLANATION', id='workflow-explanation')
                    yield _GuidePanel('LIMITS', id='workflow-limits')
                    yield _GuidePanel('DOCUMENTED EXAMPLE', id='workflow-example')
                with Vertical(id='workflow-figure'):
                    yield _GuidePanel('WORKFLOW DIAGRAM', id='workflow-diagram')
        yield _GuideText(Text('—'), id='workflow-topics')

    @property
    def topic(self):
        return next((topic for topic in self.topics if topic['id'] == self.topic_id), None)

    @property
    def nodes(self):
        return (self.topic or {}).get('nodes') or []

    @property
    def node(self):
        return next((node for node in self.nodes if node['id'] == self.node_id), None)

    def update_data(self, *, workflow_guide=None):
        if isinstance(workflow_guide, dict):
            self.source = workflow_guide.get('source') or {}
            self.topics = workflow_guide.get('topics') or []
        if not self.topic:
            default = next((topic for topic in self.topics if topic['id'] == 'contracts'), None)
            self.topic_id = (default or (self.topics[0] if self.topics else {})).get('id')
        if not self.node:
            self.node_id = self.nodes[0]['id'] if self.nodes else None
        self._paint()

    def on_mount(self):
        self.query_one('#workflow-index').display = self.index_open

    def on_resize(self):
        self.call_after_refresh(self._paint_topics)
        self.call_after_refresh(self._paint_diagram)

    def _changed(self):
        self.post_message(self.Changed({'topic_id': self.topic_id, 'node_id': self.node_id,
                                       'index_open': self.index_open}))

    def select_topic(self, index):
        if type(index) is int and 0 <= index < len(self.topics):
            self.topic_id = self.topics[index]['id']
            self.node_id = self.nodes[0]['id'] if self.nodes else None
            self._paint()
            self.call_after_refresh(self._reveal_selection)

    def select_node(self, index):
        if type(index) is int and 0 <= index < len(self.nodes):
            self.node_id = self.nodes[index]['id']
            self._paint()
            self.call_after_refresh(self._reveal_selection)

    def _reveal_selection(self):
        if self.node_id not in self._diagram_boxes:
            return
        canvas = self.query_one('#workflow-diagram-content')
        region = Region(*self._diagram_boxes[self.node_id]).translate(canvas.content_region.offset)
        parent = canvas.parent
        while parent is not None and parent is not self.screen:
            if isinstance(parent, VerticalScroll):
                local = region.translate(-parent.scrollable_content_region.offset + parent.scroll_offset)
                delta = parent.scroll_to_region(local, animate=False, immediate=True)
                region = region.translate(-delta)
            parent = parent.parent

    def move_topic(self, delta):
        if self.topic:
            self.select_topic((self.topics.index(self.topic) + delta) % len(self.topics))

    def move_node(self, delta):
        if self.nodes:
            index = self.nodes.index(self.node) if self.node else 0
            self.select_node((index + delta) % len(self.nodes))

    def toggle_index(self):
        self.index_open = not self.index_open
        self.query_one('#workflow-index').display = self.index_open
        self._paint()
        self.call_after_refresh(self._paint_diagram)

    def open_source(self):
        if self.topic:
            self.post_message(self.SourceRequested(self.source, self.topic, self.node))

    @on(_GuideText.TopicChosen)
    def _topic_chosen(self, event):
        event.stop()
        self.select_topic(event.index)

    @on(_GuideText.NodeChosen)
    def _node_chosen(self, event):
        event.stop()
        self.select_node(event.index)

    @on(_GuideText.SourceOpened)
    def _source_opened(self, event):
        event.stop()
        self.open_source()

    def _selection_style(self, selected, action):
        return Style(color=self.app.get_css_variables()['accent'] if selected else None,
                     bold=selected, underline=selected, meta={'@click': action})

    def _paint_topics(self):
        strip = self.query_one('#workflow-topics', _GuideText)
        width = max(1, strip.content_size.width // 5)
        text, index_text = Text(), Text()
        selected_line = 0
        self._strip_cut = False
        for i, topic in enumerate(self.topics):
            selected = topic['id'] == self.topic_id
            style = self._selection_style(selected, f'choose_topic({i})')
            label = f"{topic['number']:02} {flatten(topic['short_title'])}"
            fitted = clip(label, max(1, width - 1))
            self._strip_cut |= cell_len(label) > width - 1
            text.append(fitted + ' ' * max(0, width - cell_len(fitted)), style=style)
            if i == 4:
                text.append('\n')
            if selected:
                selected_line = index_text.plain.count('\n')
            full = Text(f"{topic['number']:02} {flatten(topic['title'])}", style=style)
            index_text.append_text(Text('\n').join(full.wrap(self.app.console, 24)))
            if i + 1 < len(self.topics):
                index_text.append('\n')
        strip.update(text if self.topics else Text('—'))
        self.query_one('#workflow-index-content', _GuideText).update(index_text)
        if self.index_open:
            self.query_one('#workflow-index-scroll', VerticalScroll).scroll_to(
                y=max(0, selected_line - 2), animate=False)

    def _hero_records(self):
        guidance = (self.node or {}).get('guidance') or []
        for i, title in enumerate(('STEP INPUT', 'RENDERED', 'BODY', 'MORE ROOM', 'INTEGRATED', 'COST')):
            card = guidance[i] if i < len(guidance) else {}
            yield HeroRecord(key=f'workflow-capacity-{i}', title=flatten(card.get('title')) or title,
                heading=flatten(card.get('heading')), digits=flatten(card.get('value')),
                rows=tuple(flatten(row) for row in card.get('rows') or ['—']),
                subtitle=flatten(card.get('caption')), footer=flatten(card.get('footer')),
                accent=i == 0 and bool(card.get('value')))

    def _paint_diagram(self):
        topic, node = self.topic or {}, self.node or {}
        scroll = self.query_one('#workflow-diagram-scroll', VerticalScroll)
        diagram = render_diagram(topic, self.node_id,
            width=scroll.scrollable_content_region.width,
            palette=self.app.get_css_variables(), text_color=self.rich_style.color)
        self._diagram_boxes = diagram.boxes
        canvas = self.query_one('#workflow-diagram-content', _GuideText)
        canvas.styles.width = diagram.width
        canvas.update(diagram.text)
        caption = Text(flatten(topic.get('title')) or 'WORKFLOW DIAGRAM')
        self.query_one('#workflow-diagram .panel-title', Static).update(caption)
        # Use the viewport budget, independent of the current detail visibility.
        # The hero row occupies 10 rows including its margin; the topic strip 3.
        viewport = self.screen.query_one('#workflow-viewport', VerticalScroll)
        main_height = viewport.scrollable_content_region.height - 13
        show_details = main_height >= diagram.height + 4 + 9
        self.query_one('#workflow-details').display = show_details
        source = Text(flatten(node.get('label')) if show_details else '')
        if self.topic:
            source.append(('  ' if source.plain else '') + 'SOURCE DETAILS >>',
                          style=Style(bold=True, meta={'@click': 'open_source'}))
        self.query_one('#workflow-source', _GuideText).update(source)
        # Overflow hints must see the resized canvas, not its previous width.
        self.call_after_refresh(self._changed)

    def _paint(self):
        if not self.is_mounted:
            return
        topic, node = self.topic or {}, self.node or {}
        for record in self._hero_records():
            card = self.query_one(f'#hero-{record.key}', NewsHeroCard)
            card.set_record(record)
            card.tooltip = Text('DOCUMENTED ' + flatten(self.source.get('date')) + '\n' +
                                strip_controls('\n'.join(node.get('guidance_notes') or [])))
        self._paint_topics()
        self._paint_diagram()
        for field, value in (
            ('explanation', node.get('explanation') or topic.get('summary') or '—'),
            ('limits', '\n\n'.join(node.get('limits') or []) or '—'),
            ('example', node.get('example') or '—'),
        ):
            self.query_one(f'#workflow-{field}-content', _GuideText).update(Text(strip_controls(str(value))))
            self.query_one(f'#workflow-{field}-scroll', VerticalScroll).scroll_home(animate=False)

    @property
    def needs_widen(self):
        return self._strip_cut or self.query_one('#workflow-diagram-scroll', VerticalScroll).max_scroll_x > 0
