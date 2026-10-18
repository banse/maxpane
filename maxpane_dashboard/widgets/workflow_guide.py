"""A literal, dated documentation atlas; selection only repaints local primitives."""
from __future__ import annotations

import re

from rich.style import Style
from rich.text import Text
from textual import on
from textual.containers import Grid, Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.widgets import Static

from maxpane_dashboard.widgets.markup_safety import flatten, strip_controls
from maxpane_dashboard.widgets.panels import PanelBase
from maxpane_dashboard.widgets.rowfit import cell_len, clip
from maxpane_dashboard.widgets.surf.news_hero import HeroRecord, LocalSourceHeroCard


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

    def compose(self):
        with Grid(id='workflow-heroes'):
            for i in range(6):
                yield LocalSourceHeroCard(self._record(i, {}))
        yield _GuideText(Text('—'), id='workflow-topics')
        with Horizontal(id='workflow-main'):
            yield _GuidePanel('TOPIC INDEX', id='workflow-index')
            with Vertical(id='workflow-reading'):
                with Vertical(id='workflow-figure'):
                    yield _GuidePanel('WORKFLOW DIAGRAM', id='workflow-diagram')
                    yield _GuideText(Text(), id='workflow-source')
                with Horizontal(id='workflow-details'):
                    yield _GuidePanel('EXPLANATION', id='workflow-explanation')
                    yield _GuidePanel('LIMITS', id='workflow-limits')
                    yield _GuidePanel('DOCUMENTED EXAMPLE', id='workflow-example')

    @staticmethod
    def _record(index, stat):
        return HeroRecord(key=f'workflow-{index}', title=flatten(stat.get('title')) or '—',
            heading='DOCUMENTED', footer=flatten(stat.get('caption')),
            digits=flatten(stat.get('value')) or '—', accent=False)

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

    def _changed(self):
        self.post_message(self.Changed({'topic_id': self.topic_id, 'node_id': self.node_id,
                                       'index_open': self.index_open}))

    def select_topic(self, index):
        if type(index) is int and 0 <= index < len(self.topics):
            self.topic_id = self.topics[index]['id']
            self.node_id = self.nodes[0]['id'] if self.nodes else None
            self._paint()

    def select_node(self, index):
        if type(index) is int and 0 <= index < len(self.nodes):
            self.node_id = self.nodes[index]['id']
            self._paint()

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

    def _paint_diagram(self):
        topic, node = self.topic or {}, self.node or {}
        palette = self.app.get_css_variables()
        colors = {'step': self.rich_style.color, 'plane': self.rich_style.color,
                  'merge': palette['success'], 'failure': palette['error'], 'state': palette['warning']}
        lookup = {item['id']: (i, item) for i, item in enumerate(self.nodes)}
        figure = Text()
        lines = topic.get('diagram') or ['—']
        for row, line in enumerate(lines):
            offset = 0
            line = strip_controls(str(line))
            for match in re.finditer(r'\{([a-z][a-z0-9_]*)\}', line):
                figure.append(line[offset:match.start()])
                index, item = lookup[match[1]]
                selected = item['id'] == self.node_id
                style = self._selection_style(selected, f'choose_node({index})')
                if not selected:
                    style += Style(color=colors[item['kind']], dim=item['kind'] == 'plane')
                figure.append(flatten(item['label']), style=style)
                offset = match.end()
            figure.append(line[offset:])
            if row + 1 < len(lines):
                figure.append('\n')
        canvas = self.query_one('#workflow-diagram-content', _GuideText)
        canvas.styles.width = max((cell_len(row) for row in figure.plain.splitlines()), default=1)
        canvas.update(figure)
        caption = Text(flatten(topic.get('title')) or 'WORKFLOW DIAGRAM')
        caption.append(' · colors = diagram roles', style='dim')
        self.query_one('#workflow-diagram .panel-title', Static).update(caption)
        figure_height = max(8, len(lines) + 4)
        self.query_one('#workflow-figure').styles.height = figure_height
        floor = max(22, figure_height + 9)
        self.query_one('#workflow-main').styles.min_height = floor
        self.styles.min_height = 14 + floor
        source = Text(flatten(node.get('label')))
        if self.topic:
            source.append('  SOURCE DETAILS >>', style=Style(bold=True, meta={'@click': 'open_source'}))
        self.query_one('#workflow-source', _GuideText).update(source)

    def _paint(self):
        if not self.is_mounted:
            return
        topic, node = self.topic or {}, self.node or {}
        stats = topic.get('stats') or []
        for i, card in enumerate(self.query(LocalSourceHeroCard)):
            card.set_record(self._record(i, stats[i] if i < len(stats) else {}))
            stat = stats[i] if i < len(stats) else {}
            card.tooltip = Text(' · '.join((flatten(stat.get('title')), flatten(stat.get('value')),
                flatten(stat.get('caption')), 'DOCUMENTED ' + flatten(self.source.get('date')))))
        self._paint_topics()
        self._paint_diagram()
        for field, value in (
            ('explanation', node.get('explanation') or topic.get('summary') or '—'),
            ('limits', '\n\n'.join(node.get('limits') or []) or '—'),
            ('example', node.get('example') or '—'),
        ):
            self.query_one(f'#workflow-{field}-content', _GuideText).update(Text(strip_controls(str(value))))
            self.query_one(f'#workflow-{field}-scroll', VerticalScroll).scroll_home(animate=False)
        self._changed()

    @property
    def needs_widen(self):
        return self._strip_cut or self.query_one('#workflow-diagram-scroll', VerticalScroll).max_scroll_x > 0
