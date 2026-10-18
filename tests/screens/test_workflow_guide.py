"""The dated workflow atlas selects only retained, literal documentation."""
from copy import deepcopy
from pathlib import Path

import pytest
from rich.cells import cell_len
from textual.app import App
from textual.containers import VerticalScroll

from maxpane_dashboard.screens.workflow_guide import WorkflowGuideScreen, WorkflowSourceScreen
from maxpane_dashboard.widgets.workflow_guide import WorkflowGuideView
from maxpane_dashboard.widgets.surf.news_hero import NewsHeroCard


TOPICS = ('purchase', 'single_skill', 'shapes', 'contracts', 'site', 'company',
          'oracle', 'intake', 'schedules', 'growth')


def catalogue():
    return {'source': {'title': 'Swarm workflow source', 'date': '2026-10-18',
            'plane': '745c1db4', 'worker': '0.1.2', 'references': ['Bundled source']},
            'topics': [{
                'id': key, 'number': i + 1, 'title': key.upper(), 'short_title': key,
                'summary': f'{key} documented overview',
                'stats': [{'title': f'FACT {n}', 'value': f'{i + 1}.{n} B',
                           'caption': f'{key} units'} for n in range(6)],
                'diagram': ['{start} ---> {review}', '                 |',
                            '                 v', '             {done}'],
                'nodes': [{'id': node, 'label': f'[{key} {node}]', 'kind': kind,
                    'explanation': f'{key} {node} explanation',
                    'limits': [f'{key} {node} limit'], 'example': f'{key} {node} example',
                    'source_excerpt': f'{key} {node} original [/x] source\x1b\u202e'}
                    for node, kind in [('start', 'step'), ('review', 'plane'), ('done', 'merge')]],
                'source_excerpt': f'{key} original topic source',
            } for i, key in enumerate(TOPICS)]}


class Manager:
    def __init__(self, payload=None):
        self.payload = {'workflow_guide': catalogue()} if payload is None else payload
        self.calls = 0

    def get_snapshot(self):
        return deepcopy(self.payload)

    async def fetch_and_compute(self):
        self.calls += 1
        return self.get_snapshot()


class Harness(App):
    CSS_PATH = Path(__file__).parents[2] / 'maxpane_dashboard/themes/minimal.tcss'

    def __init__(self, state=None, manager=None):
        super().__init__()
        self.state = state if state is not None else {}
        self.manager = manager or Manager()

    def on_mount(self):
        self.open_guide()

    def open_guide(self):
        self.push_screen(WorkflowGuideScreen(self.manager, view_state=self.state))


def painted(app):
    return '\n'.join(''.join(segment.text for segment in strip)
                     for strip in app.screen._compositor.render_strips())


def painted_widget(app, widget):
    region = widget.region
    return '\n'.join(row[region.x:region.right]
                     for row in painted(app).splitlines()[region.y:region.bottom])


def target(app, action, *, within=None):
    for y, strip in enumerate(app.screen._compositor.render_strips()):
        x = 0
        for segment in strip:
            if (segment.style and segment.style.meta.get('@click') == action
                    and (within is None or within.region.contains(x, y))):
                return x, y
            x += cell_len(segment.text)
    raise AssertionError(f'No visible action {action!r}:\n{painted(app)}')


async def test_every_topic_click_updates_boxed_diagram_and_explanation_without_fetch():
    app = Harness()
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        view = app.screen.query_one(WorkflowGuideView)
        assert view.topic_id == 'contracts'
        calls = app.manager.calls
        for i, key in enumerate(TOPICS):
            await pilot.click(offset=target(app, f'choose_topic({i})'))
            await pilot.pause()
            output = painted(app)
            assert view.topic_id == key
            assert len(view.query(NewsHeroCard)) == 6
            assert f'{key} start explanation' in output
            assert f'{key} start limit' in output
            assert f'{key} start example' in output
        assert app.manager.calls == calls


async def test_arrows_and_node_click_preserve_diagram_geometry_and_use_authored_order():
    app = Harness()
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        view = app.screen.query_one(WorkflowGuideView)
        initial = target(app, 'choose_node(1)')
        await pilot.press('down')
        assert view.node_id == 'review'
        assert 'contracts review explanation' in painted(app)
        assert target(app, 'choose_node(1)') == initial
        await pilot.press('down', 'up')
        assert view.node_id == 'review'
        await pilot.click(offset=target(app, 'choose_node(2)'))
        assert view.node_id == 'done'
        await pilot.press('right')
        assert view.topic_id == 'site' and view.node_id == 'start'
        await pilot.press('left')
        assert view.topic_id == 'contracts'


async def test_index_click_and_reopen_retain_borrowed_state():
    state = {}
    app = Harness(state)
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        await pilot.press('i')
        view = app.screen.query_one(WorkflowGuideView)
        assert view.query_one('#workflow-index').size.width == 28
        await pilot.click('#workflow-index-content', offset=(2, 9))
        await pilot.pause()
        assert view.topic_id == 'growth'
        await pilot.press('down')
        assert state == {'topic_id': 'growth', 'node_id': 'review', 'index_open': True}
        await pilot.press('escape')
        assert not isinstance(app.screen, WorkflowGuideScreen)
        app.open_guide()
        await pilot.pause()
        view = app.screen.query_one(WorkflowGuideView)
        assert (view.topic_id, view.node_id, view.index_open) == ('growth', 'review', True)
        await pilot.press('i')
        assert view.node_id == 'review' and not view.query_one('#workflow-index').display


@pytest.mark.parametrize('open_with', ['enter', 'click'])
async def test_source_popup_has_literal_dated_provenance_and_escape_returns_to_same_selection(open_with):
    app = Harness()
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        screen = app.screen
        await pilot.press('down')
        if open_with == 'enter':
            await pilot.press('enter')
        else:
            await pilot.click(offset=target(app, 'open_source'))
        assert isinstance(app.screen, WorkflowSourceScreen)
        output = painted(app)
        for word in ('DOCUMENTED 2026-10-18', '745c1db4', '0.1.2', 'contracts review original [/x] source'):
            assert word in output
        assert '\x1b' not in output and '\u202e' not in output
        await pilot.press('escape')
        assert app.screen is screen
        assert screen.query_one(WorkflowGuideView).node_id == 'review'


@pytest.mark.parametrize('size', [(160, 45), (149, 45)])
async def test_capacity_hero_row_preserves_large_inner_card_diagram(size):
    app = Harness()
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        screen = app.screen
        assert len(screen.query(NewsHeroCard)) == 6
        assert screen.query_one('#workflow-heroes').region.height == 9
        diagram = screen.query_one('#workflow-diagram')
        assert diagram.region.height >= 15
        output = painted(app)
        for key in TOPICS:
            assert key in output
        for text in ('contracts start', 'contracts review', 'contracts done',
                     'EXPLANATION', 'LIMITS', 'DOCUMENTED EXAMPLE', 'SOURCE DETAILS >>'):
            assert text in output
        for i in range(3):
            x, y = target(app, f'choose_node({i})')
            assert output.splitlines()[y][x] == '┌'
        viewport = screen.query_one('#workflow-viewport', VerticalScroll)
        assert viewport.max_scroll_x == viewport.max_scroll_y == 0


@pytest.mark.parametrize('topic_index, has_details', [(0, True), (3, False)])
@pytest.mark.parametrize('index_open', [False, True])
async def test_source_and_details_above_diagram_topics_below(topic_index, has_details, index_open):
    from maxpane_dashboard.data.workflow_guide_manager import WorkflowGuideManager

    app = Harness(manager=WorkflowGuideManager())
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        view = app.screen.query_one(WorkflowGuideView)
        view.select_topic(topic_index)
        if index_open:
            view.toggle_index()
        await pilot.pause()
        output = painted(app).splitlines()
        source_y = target(app, 'open_source')[1]
        node_rows = [target(app, f'choose_node({i})')[1] for i in range(len(view.nodes))]
        topics = view.query_one('#workflow-topics')
        topic_rows = [target(app, f'choose_topic({i})', within=topics)[1] for i in range(10)]
        assert view.query_one('#workflow-heroes').region.bottom <= source_y
        assert source_y < min(node_rows)
        assert max(node_rows) + 3 < min(topic_rows)  # Four-row framed nodes.
        assert view.query_one('#workflow-details').display == has_details
        for title in ('EXPLANATION', 'LIMITS', 'DOCUMENTED EXAMPLE'):
            title_rows = [i for i, line in enumerate(output) if title in line]
            if has_details:
                assert len(title_rows) == 1
                assert source_y < title_rows[0] < min(node_rows)
            else:
                assert not title_rows
        await pilot.click(offset=target(app, 'open_source'))
        assert isinstance(app.screen, WorkflowSourceScreen)
        await pilot.press('escape')
        await pilot.click(offset=target(app, 'choose_topic(9)', within=topics))
        assert view.topic_id == 'growth'


async def test_dense_diagram_hides_details_and_restores_them_when_room_returns():
    from maxpane_dashboard.data.workflow_guide_manager import WorkflowGuideManager

    app = Harness(manager=WorkflowGuideManager())
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        view = app.screen.query_one(WorkflowGuideView)
        assert len(view.query(NewsHeroCard)) == 6
        assert not view.query_one('#workflow-details').display
        assert 'EXPLANATION' not in painted(app)
        assert 'SOURCE DETAILS >>' in painted(app)
        assert '[audit imported code]' not in painted(app)
        assert view.query_one('#workflow-diagram-scroll').max_scroll_y == 0
        await pilot.click(offset=target(app, 'open_source'))
        assert isinstance(app.screen, WorkflowSourceScreen)
        assert 'EXPLANATION' in painted(app)
        await pilot.press('escape')
        await pilot.resize_terminal(149, 60)
        assert view.query_one('#workflow-details').display
        assert 'EXPLANATION' in painted(app)
        await pilot.resize_terminal(149, 45)
        assert not view.query_one('#workflow-details').display
        view.select_topic(0)  # Short purchase graph leaves room for the details.
        await pilot.pause()
        assert view.query_one('#workflow-details').display
        assert 'EXPLANATION' in painted(app)


async def test_selected_node_capacity_and_alternatives_are_literal_and_retained_in_popup():
    payload = catalogue()
    node = payload['topics'][3]['nodes'][0]
    node['guidance'] = [dict(title='STEP INPUT', heading='EST. WORDS', value='≈500',
        rows=[], caption='3,000 chars', footer='authored input')]
    node['guidance_notes'] = ['Estimate only: six characters per word. [/x]\x1b\u202e']
    payload['topics'][3]['nodes'][1]['guidance'] = [dict(title='STEP INPUT', heading='MANAGED',
        value='', rows=['No authored text'], caption='plane stage', footer='included in job')]
    app = Harness(manager=Manager({'workflow_guide': payload}))
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        view = app.screen.query_one(WorkflowGuideView)
        card = view.query_one('#hero-workflow-capacity-0')
        output = painted_widget(app, card)
        assert '≈500' in output and '3,000 chars' in output and 'EST. WORDS' in output
        calls = app.manager.calls
        await pilot.press('down')
        assert 'MANAGED' in painted_widget(app, card)
        assert '≈500' not in painted_widget(app, card)
        await pilot.press('up', 'enter')
        app.screen.query_one('.record-detail-scroll', VerticalScroll).scroll_end(animate=False)
        await pilot.pause()
        output = painted(app)
        assert 'CAPACITY & ALTERNATIVES' in output
        assert 'six characters per word' in output and '[/x]' in output
        assert '\x1b' not in output and '\u202e' not in output
        assert app.manager.calls == calls


async def test_narrow_short_terminal_keeps_source_link_and_scrollable_diagram():
    app = Harness()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        viewport = app.screen.query_one('#workflow-viewport', VerticalScroll)
        assert viewport.max_scroll_x > 0
        assert '‹ widen' in painted(app)
        assert not app.screen.query_one('#workflow-details').display
        viewport.scroll_to(x=viewport.max_scroll_x, y=viewport.max_scroll_y, animate=False)
        await pilot.pause()
        await pilot.click(offset=target(app, 'choose_topic(9)'))
        viewport.scroll_to(x=0, y=0, animate=False)
        await pilot.pause()
        await pilot.click(offset=target(app, 'open_source'))
        assert 'growth start example' in painted(app)


async def test_invalid_saved_ids_normalize_and_missing_refresh_retains_good_content():
    state = {'topic_id': 'unknown', 'node_id': 'unknown', 'index_open': False}
    app = Harness(state)
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        view = app.screen.query_one(WorkflowGuideView)
        assert state == {'topic_id': 'contracts', 'node_id': 'start', 'index_open': False}
        view.update_data(workflow_guide=None)
        assert 'contracts start explanation' in painted(app)


async def test_empty_catalogue_has_no_phantom_selection():
    app = Harness(manager=Manager({'workflow_guide': {'source': {}, 'topics': []}}))
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        view = app.screen.query_one(WorkflowGuideView)
        await pilot.press('down', 'right', 'enter')
        assert app.screen.query_one(WorkflowGuideView) is view
        assert view.topic_id is None and view.node_id is None
        assert 'SOURCE DETAILS >>' not in painted(app)


async def test_keyboard_selection_reveals_box_in_short_scrolled_view():
    from maxpane_dashboard.data.workflow_guide_manager import WorkflowGuideManager

    app = Harness(manager=WorkflowGuideManager())
    async with app.run_test(size=(100, 24)) as pilot:
        await pilot.pause()
        view = app.screen.query_one(WorkflowGuideView)
        await pilot.press('up')  # Wrap to the last authored contracts node.
        assert view.node_id == 'blocked'
        x, y = target(app, f'choose_node({len(view.nodes) - 1})')
        assert painted(app).splitlines()[y][x] == '┌'
        assert 'undeployed' in painted(app)


async def test_long_literal_prose_and_source_tail_remain_scroll_reachable():
    payload = catalogue()
    node = payload['topics'][3]['nodes'][0]
    node['explanation'] = '[/x] Unicode 東京 👩‍💻 ' + ('Long documentation. ' * 180) + 'EXPLANATION END'
    node['source_excerpt'] = ('Source documentation.\n' * 80) + 'SOURCE END'
    app = Harness(manager=Manager({'workflow_guide': payload}))
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        assert '[/x] Unicode 東京 👩‍💻' in painted(app)
        scroll = app.screen.query_one('#workflow-explanation-scroll', VerticalScroll)
        assert scroll.max_scroll_y > 0
        scroll.scroll_end(animate=False)
        await pilot.pause()
        assert 'EXPLANATION END' in painted(app)
        await pilot.press('enter')
        scroll = app.screen.query_one('.record-detail-scroll', VerticalScroll)
        scroll.scroll_end(animate=False)
        await pilot.pause()
        assert 'SOURCE END' in painted(app)


async def test_removed_hero_facts_remain_in_source_popup():
    from maxpane_dashboard.data.workflow_guide_manager import WorkflowGuideManager

    app = Harness(manager=WorkflowGuideManager())
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        view = app.screen.query_one(WorkflowGuideView)
        view.select_topic(next(i for i, topic in enumerate(view.topics) if topic['id'] == 'site'))
        await pilot.pause()
        await pilot.press('enter')
        scroll = app.screen.query_one('.record-detail-scroll', VerticalScroll)
        scroll.scroll_end(animate=False)
        await pilot.pause()
        output = painted(app)
        assert 'DOCUMENTED FACTS' in output
        for stat in view.topic['stats']:
            assert stat['title'] in output and stat['value'] in output


async def test_schedule_topup_is_an_action_from_exhausted_and_paused():
    from maxpane_dashboard.data.workflow_guide_manager import WorkflowGuideManager

    app = Harness(manager=WorkflowGuideManager())
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        view = app.screen.query_one(WorkflowGuideView)
        view.select_topic(next(i for i, topic in enumerate(view.topics) if topic['id'] == 'schedules'))
        await pilot.pause()
        index = next(i for i, node in enumerate(view.nodes) if node['id'] == 'topup')
        x, y = target(app, f'choose_node({index})')
        _, _, width, height = view._diagram_boxes['topup']
        rows = painted(app).splitlines()
        assert rows[y - 1][x + width // 2] == '▼'  # Exhausted leads to the action.
        assert rows[y + height][x + width // 2] == '▲'  # Paused also leads to it.


async def test_all_real_catalogue_nodes_are_mouse_reachable():
    from maxpane_dashboard.data.workflow_guide_manager import WorkflowGuideManager

    app = Harness(manager=WorkflowGuideManager())
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        view = app.screen.query_one(WorkflowGuideView)
        for topic_index, topic in enumerate(view.topics):
            await pilot.click(offset=target(app, f'choose_topic({topic_index})'))
            for node_index, node in enumerate(topic['nodes']):
                await pilot.click(offset=target(app, f'choose_node({node_index})'))
                assert view.node_id == node['id']
                assert app.state['node_id'] == node['id']
                for i, card in enumerate(node['guidance']):
                    output = painted_widget(app, view.query_one(f'#hero-workflow-capacity-{i}'))
                    for text in (card['title'], card['heading'], card['caption'], card['footer'], *card['rows']):
                        assert text in output
                    if not card['value'].replace('.', '').replace(',', '').isdigit():
                        assert card['value'] in output


async def test_clickable_nodes_keep_semantic_colors_and_selected_accent(monkeypatch):
    from rich.color import Color
    from maxpane_dashboard.data.workflow_guide_manager import WorkflowGuideManager

    monkeypatch.delenv('NO_COLOR', raising=False)
    app = Harness(manager=WorkflowGuideManager())
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        view = app.screen.query_one(WorkflowGuideView)
        palette = app.get_css_variables()
        for kind, token in (('merge', 'success'), ('failure', 'error')):
            index = next(i for i, node in enumerate(view.nodes) if node['kind'] == kind)
            x, y = target(app, f'choose_node({index})')
            role = 'JOIN' if kind == 'merge' else 'FAILED'
            role_x = painted(app).splitlines()[y].index(role, x)
            assert app.screen.get_style_at(role_x, y).color == Color.parse(palette[token])
        await pilot.click(offset=(x, y))
        assert app.screen.get_style_at(x, y).color == Color.parse(palette['accent'])
        assert app.screen.get_style_at(role_x, y).color == Color.parse(palette['error'])
