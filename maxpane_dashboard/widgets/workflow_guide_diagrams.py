"""Authored documentation graphs rendered as native, clickable card insets.

Coordinates encode presentation only. The caller supplies every node label and
role; unknown node sets get an unconnected card gallery instead of guessed edges.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import groupby
from textwrap import wrap

from rich.cells import cell_len
from rich.console import Console
from rich.style import Style
from rich.text import Text

from maxpane_dashboard.widgets.card_inner import inner_styles, padded_inner_row
from maxpane_dashboard.widgets.markup_safety import flatten


@dataclass(frozen=True)
class DiagramRender:
    text: Text
    width: int
    height: int
    boxes: dict[str, tuple[int, int, int, int]]


def _plan(topic_id):
    """Return authored (column, row) boxes, port routes and group captions.

    Routes name source/target ports (left/right/top/bottom). The optional rail
    is a row for vertical ports; parallel horizontal routes share the gap rail.
    """
    if topic_id in ('purchase', 'company'):
        ids = ('check', 'quote', 'signatures', 'submit', 'settle', 'admitted') if topic_id == 'purchase' else (
            'contracts', 'deployment', 'frontend', 'publishing', 'validating', 'completed')
        boxes = dict(zip(ids, ((0, 1), (1, 1), (2, 1), (2, 10), (1, 10), (0, 10))))
        edges = [(ids[i], ids[i + 1], side) for i, side in enumerate(('rl', 'rl', 'bt', 'lr', 'lr'))]
        return boxes, edges, []
    if topic_id == 'single_skill':
        return dict(dispatch=(0, 3), working=(1, 3), verifying=(2, 3), verdict=(3, 3),
                    delivered=(3, 12), blocked=(2, 12)), [
            ('dispatch', 'working', 'rl'), ('working', 'verifying', 'rl'), ('verifying', 'verdict', 'rl'),
            ('verdict', 'dispatch', 'tt', 1), ('verdict', 'delivered', 'bt'), ('verdict', 'blocked', 'bt', 9),
        ], [(0, 0, 'FAILED: RETRY, MAX 3 ATTEMPTS'), (3, 11, 'ACCEPTED'), (1, 11, 'THIRD FAILURE')]
    if topic_id == 'shapes':
        return dict(chain_build=(0, 1), chain_check=(1, 1), chain_docs=(2, 1), component_a=(0, 8),
                    component_b=(0, 12), component_c=(0, 16), integrate=(1, 12), dag_build=(2, 8),
                    dag_check=(3, 8), dag_docs=(2, 16), dag_tests=(3, 16), critic=(4, 12)), [
            ('chain_build', 'chain_check', 'rl'), ('chain_check', 'chain_docs', 'rl'),
            ('component_a', 'integrate', 'rl'), ('component_b', 'integrate', 'rl'),
            ('component_c', 'integrate', 'rl'), ('dag_build', 'dag_check', 'rl'),
            ('dag_build', 'dag_docs', 'bt'), ('dag_docs', 'dag_tests', 'rl'),
            ('dag_check', 'critic', 'rl'), ('dag_tests', 'critic', 'rl'),
        ], [(0, 0, 'CHAIN'), (0, 7, 'FAN_OUT_JOIN'), (2, 7, 'DAG: BUILD -> DOCS')]
    if topic_id == 'contracts':
        audits = ('tests', 'manifest', 'audit_math', 'audit_permissions', 'audit_economics', 'audit_flow')
        boxes = dict(import_audit=(0, 0), adapt=(0, 12), judge=(2, 10), deploy=(3, 10),
                     live=(4, 10), blocked=(2, 20))
        boxes.update({key: (1, row * 4) for row, key in enumerate(audits)})
        edges = [('import_audit', 'adapt', 'bt')]
        edges += [('adapt', key, 'rl') for key in audits]
        edges += [(key, 'judge', 'rl') for key in audits]
        edges += [('judge', 'deploy', 'rl'), ('deploy', 'live', 'rl'), ('judge', 'blocked', 'bt')]
        return boxes, edges, [(2, 4, '6 PARALLEL STAGES'), (3, 8, 'ONE ATOMIC DEPLOY'),
                             (3, 18, 'BLOCKING FINDING')]
    if topic_id == 'site':
        return dict(build=(0, 1), check=(1, 1), docs=(2, 1), critic=(3, 9), hosted=(4, 9),
                    blocked=(3, 17), recovery=(0, 17)), [
            ('build', 'check', 'rl'), ('check', 'docs', 'rl'), ('build', 'critic', 'bt', 6),
            ('docs', 'critic', 'rt'), ('critic', 'hosted', 'rl'), ('critic', 'blocked', 'bt'),
        ], [(0, 0, 'OBSERVED: MISSING BUNDLE'), (4, 6, 'MERGE CONFLICT'), (4, 8, 'NOT REACHED'),
            (4, 16, 'CLONE_FAILED x3'), (0, 16, 'PROPOSED RECOVERY')]
    if topic_id == 'oracle':
        return dict(request=(0, 1), admit=(1, 1), panel=(2, 1), attest=(3, 1), writer=(3, 9),
                    registry=(2, 9), stored=(1, 9), missed=(1, 17)), [
            ('request', 'admit', 'rl'), ('admit', 'panel', 'rl'), ('panel', 'attest', 'rl'),
            ('attest', 'writer', 'bt'), ('writer', 'registry', 'lr'), ('registry', 'stored', 'lr'),
            ('registry', 'missed', 'br'),
        ], [(1, 16, 'QUORUM / RULE FAILURE')]
    if topic_id == 'intake':
        ids = ('received', 'paid', 'admitted', 'completing', 'completed')
        boxes = {key: (i, 1) for i, key in enumerate(ids)}
        boxes.update(refused=(0, 10), failed=(2, 10))
        return boxes, [(ids[i], ids[i + 1], 'rl') for i in range(4)] + [
            ('received', 'refused', 'bt'), ('admitted', 'failed', 'bt')], []
    if topic_id == 'schedules':
        return dict(create=(0, 1), slot=(1, 1), opened=(2, 1), remaining=(3, 1), exhausted=(4, 1),
                    skipped=(2, 9), failed=(2, 17), paused=(3, 17), topup=(4, 9)), [
            ('create', 'slot', 'rl'), ('slot', 'opened', 'rl'), ('opened', 'remaining', 'rl'),
            ('remaining', 'exhausted', 'rl'), ('slot', 'skipped', 'bl'), ('slot', 'failed', 'bl'),
            ('failed', 'paused', 'rl'), ('paused', 'topup', 'rb'), ('exhausted', 'topup', 'bt'),
        ], [(0, 8, 'SLOTS NEVER QUEUE'), (3, 8, 'EXTEND RUNS'), (3, 16, '3 FAILURES')]
    if topic_id == 'growth':
        return dict(launch=(0, 1), site=(1, 1), fix=(1, 9), feature=(2, 9), more=(3, 9), fresh=(0, 17)), [
            ('launch', 'site', 'rl'), ('fix', 'feature', 'rl'), ('feature', 'more', 'rl'),
        ], [(0, 0, 'OBSERVED'), (1, 8, 'PROPOSED CONTINUATIONS'), (0, 16, 'SEPARATE PROJECT')]
    return {}, [], []


_GLYPHS = {
    frozenset('lr'): '─', frozenset('bt'): '│', frozenset('rb'): '┌', frozenset('lb'): '┐',
    frozenset('rt'): '└', frozenset('lt'): '┘', frozenset('rbt'): '├', frozenset('lbt'): '┤',
    frozenset('lrb'): '┬', frozenset('lrt'): '┴', frozenset('lrbt'): '┼',
}


def _port(box, side):
    x, y, width, height = box
    return {'l': (x - 1, y + 2), 'r': (x + width, y + 2),
            't': (x + width // 2, y - 1), 'b': (x + width // 2, y + height)}[side]


def _route(boxes, edge):
    source, target, sides, *rail = edge
    a, b = _port(boxes[source], sides[0]), _port(boxes[target], sides[1])
    if sides[0] in 'lr' and sides[1] in 'lr':
        middle = (a[0] + b[0]) // 2
        return [a, (middle, a[1]), (middle, b[1]), b]
    if sides[0] in 'tb' and sides[1] in 'tb':
        middle = rail[0] if rail else (a[1] + b[1]) // 2
        return [a, (a[0], middle), (b[0], middle), b]
    return [a, (a[0], b[1]) if sides[0] in 'tb' else (b[0], a[1]), b]


def _label(node):
    label = flatten(node.get('label'))
    if label.startswith('[') and label.endswith(']'):
        label = label[1:-1]
    if node.get('kind') == 'plane' and label.startswith('- ') and label.endswith(' -'):
        label = label[2:-2]
    return label


def render_diagram(topic: dict, selected_node_id: str | None, *, width: int,
                   palette: dict, text_color) -> DiagramRender:
    nodes = topic.get('nodes') or []
    positions, edges, captions = _plan(topic.get('id'))
    if set(positions) != {node['id'] for node in nodes}:
        columns = max(1, min(5, width // 24))
        positions = {node['id']: (i % columns, i // columns * 6) for i, node in enumerate(nodes)}
        edges, captions = [], []
    columns = max((x for x, _ in positions.values()), default=0) + 1
    gap = 4 if width < 110 else 5
    box_width = max(18, min(25, (max(0, width) - (columns - 1) * gap) // columns))
    pitch = box_width + gap
    boxes = {key: (column * pitch, y, box_width, 4) for key, (column, y) in positions.items()}
    canvas_width = max((x + w for x, _, w, _ in boxes.values()), default=1)
    canvas_height = max((y + h for _, y, _, h in boxes.values()), default=1)
    canvas = [[(' ', Style()) for _ in range(canvas_width)] for _ in range(canvas_height)]

    def write(x, y, text, style):
        for char in text:
            cells = cell_len(char)
            if cells == 0:
                if x > 0 and 0 <= y < canvas_height:
                    old, old_style = canvas[y][x - 1]
                    canvas[y][x - 1] = (old + char, old_style)
                continue
            if 0 <= y < canvas_height and 0 <= x and x + cells <= canvas_width:
                canvas[y][x] = (char, style)
                for continuation in range(1, cells):
                    canvas[y][x + continuation] = ('', style)
            x += cells

    neutral = Style(color=text_color, dim=True)
    links, arrows = {}, {}
    kinds = {node['id']: node.get('kind') for node in nodes}
    for edge in edges:
        points = _route(boxes, edge)
        style = Style(color=palette['error']) if kinds[edge[1]] == 'failure' else neutral
        for a, b in zip(points, points[1:]):
            dx, dy = (b[0] > a[0]) - (b[0] < a[0]), (b[1] > a[1]) - (b[1] < a[1])
            length = abs(b[0] - a[0]) + abs(b[1] - a[1])
            for step in range(length + 1):
                point = (a[0] + dx * step, a[1] + dy * step)
                directions, _ = links.setdefault(point, (set(), style))
                if step:
                    directions.add('l' if dx > 0 else 'r' if dx < 0 else 't' if dy > 0 else 'b')
                if step < length:
                    directions.add('r' if dx > 0 else 'l' if dx < 0 else 'b' if dy > 0 else 't')
        arrows[points[-1]] = ({'l': '▶', 'r': '◀', 't': '▼', 'b': '▲'}[edge[2][1]], style)
    for (x, y), (directions, style) in links.items():
        glyph = _GLYPHS.get(frozenset(directions), '│' if directions & set('tb') else '─')
        write(x, y, glyph, style)
    for (x, y), (glyph, style) in arrows.items():
        write(x, y, glyph, style)
    for column, row, label in captions:
        caption = Text(label)
        # Captions may occupy a shared rail, never a neighboring card's label.
        caption.truncate(canvas_width - column * pitch, overflow='ellipsis')
        write(column * pitch, row, caption.plain, neutral)

    console = Console(width=max(18, box_width), color_system=None)
    role_names = dict(step='STEP', plane='PLANE', merge='JOIN', state='STATE', failure='FAILED')
    for index, node in enumerate(nodes):
        x, y, w, _ = boxes[node['id']]
        kind = node.get('kind', 'step')
        action = Style(meta={'@click': f'choose_node({index})'}, bgcolor=palette['background'])
        frame = action + Style(color=palette['accent'] if node['id'] == selected_node_id else text_color,
                               dim=node['id'] != selected_node_id)
        ink, _, _ = inner_styles(palette, text_color=text_color)
        ink += action
        role = role_names.get(kind, 'STEP')
        gap = w - len(role) - 4
        top = '┌' + '─' * (gap // 2) + ' ' + role + ' ' + '─' * (gap - gap // 2) + '┐'
        write(x, y, top, frame)
        role_style = action + Style(color=palette['error'] if kind == 'failure' else
                                   palette['success'] if kind == 'merge' else text_color,
                                   bold=True, dim=kind == 'plane')
        write(x + 2 + gap // 2, y, role, role_style)
        # Honor compound-word hyphens first; Rich then folds by terminal cells,
        # so wide glyphs still cannot move the right-hand frame.
        wrapped = [line for part in wrap(_label(node), w - 4, break_long_words=False)
                   for line in Text(part).wrap(console, w - 4, overflow='fold')]
        for row in range(2):
            value = wrapped[row] if row < len(wrapped) else Text()
            if row == 1 and len(wrapped) > 2:
                value = Text(' '.join(line.plain for line in wrapped[1:]))
            value.style = ink
            padded = padded_inner_row(value, w - 2, align='center')
            write(x, y + row + 1, '│', frame)
            write(x + 1, y + row + 1, padded.plain, ink)
            write(x + w - 1, y + row + 1, '│', frame)
        write(x, y + 3, '└' + '─' * (w - 2) + '┘', frame)

    result = Text(no_wrap=True)
    for y, row in enumerate(canvas):
        for style, run in groupby(row, key=lambda item: item[1]):
            result.append(''.join(char for char, _ in run), style)
        if y + 1 < canvas_height:
            result.append('\n')
    return DiagramRender(result, canvas_width, canvas_height, boxes)
