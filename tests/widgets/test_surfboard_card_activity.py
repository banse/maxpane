"""Card footer semantics observed through Textual's compositor."""
import pytest
from maxpane_dashboard.widgets.surfboard.rack import SurfboardCard
from tests.widgets.test_surfboard_rack import RackApp


def strips(app, card):
    return [line.crop(card.region.x, card.region.right) for line in
            app.screen._compositor.render_strips()[card.region.y:card.region.bottom]]


@pytest.mark.parametrize('key', ['agent', 'board'])
async def test_activity_footer_labels_colors_and_full_half_empty_unknown(key):
    async with RackApp().run_test(size=(149, 45)) as pilot:
        card = pilot.app.query_one(f'#surfboard-card-{key}', SurfboardCard)
        for state, remaining, label, ratio, color in [
            ('busy', 86400, 'BUSY', 1, 3), ('idle', 43200, 'IDLE', .5, 2),
            ('idle', 0, 'IDLE', 0, 2), ('idle', None, 'IDLE', None, 2),
            ('stale', None, '—', None, 3), ('unavailable', None, '—', None, 3),
        ]:
            card.set_data(dict(primary='420', secondary='0 of 3 slots', status='active',
                meter_kind='activity', meter_state=state, numerator=remaining, denominator=86400))
            await pilot.pause()
            footer = strips(pilot.app, card)[-1]
            assert 'PASS' not in footer.text
            assert footer.text.startswith('╰─ ' + label + ' ')
            ink = next(segment.style.color.get_truecolor() for segment in footer if label in segment.text)
            assert ink == pilot.app.ansi_theme.ansi_colors[color]
            if ratio is None:
                assert '▰' not in footer.text and '▱' not in footer.text
            else:
                cells = footer.text.count('▰') + footer.text.count('▱')
                assert cells > 0 and footer.text.count('▰') == int(cells * ratio)


@pytest.mark.parametrize('key', ['announce', 'swarm-tokens'])
async def test_news_footer_hides_only_known_zero(key):
    async with RackApp().run_test(size=(149, 45)) as pilot:
        card = pilot.app.query_one(f'#surfboard-card-{key}', SurfboardCard)
        for value, expected in [('0 new replies' if key == 'announce' else '0 new', ''),
                                ('2 new replies' if key == 'announce' else '2 new', '2 new'),
                                ('unavailable', 'unavailable')]:
            card.set_data(dict(primary='post', secondary=value))
            await pilot.pause()
            lines = strips(pilot.app, card)
            bottom = next(line.text for line in lines if '└' in line.text)
            assert bottom[bottom.index('└')+1:bottom.index('┘')].strip('─ ') == expected


async def test_protocol_columns_are_amount_unit_label_without_colons():
    async with RackApp().run_test(size=(149, 45)) as pilot:
        card = pilot.app.query_one('#surfboard-card-protocol', SurfboardCard)
        card.set_data(dict(primary='★ burned 33k IMD\n★ rewarded 6k IMD\n★ fees 4k IMD', secondary='0.47%'))
        await pilot.pause()
        lines = strips(pilot.app, card)
        top = next(i for i, line in enumerate(lines) if '┌' in line.text)
        body = [line.text[line.text.index('│', 1)+1:line.text.rindex('│')].strip('│ ')
                for line in lines[top+1:top+4]]
        assert [line.split() for line in body] == [['33k', 'IMD', 'burned'], ['6k', 'IMD', 'rewarded'], ['4k', 'IMD', 'fees']]
        assert len({line.index('IMD') for line in body}) == 1
        assert len({line.index(label) for line, label in zip(body, ('burned', 'rewarded', 'fees'))}) == 1
        assert not any(':' in line or '★' in line for line in body)


async def test_launches_volume_has_real_buckets_and_visible_partial_gaps():
    async with RackApp().run_test(size=(149, 45)) as pilot:
        card = pilot.app.query_one('#surfboard-card-swarm-tokens', SurfboardCard)
        for state, points in [('ok', list(range(8))), ('partial', [0, 1, None, 3, 4, 5, 6, 7]), ('unavailable', None)]:
            card.set_data(dict(meter_kind='sparkline', meter_state=state, points=points, secondary='0 new'))
            await pilot.pause()
            footer = strips(pilot.app, card)[-1]
            assert 'TOKENS' not in footer.text
            if state == 'ok':
                assert '24H ' in footer.text and '█' in footer.text and '▁' in footer.text
            elif state == 'partial':
                assert '~24H ' in footer.text and '·' in footer.text and '█' in footer.text
            else:
                assert '24H —' in footer.text
                assert not any(char in footer.text for char in '▁▂▃▄▅▆▇█')


async def test_pool4_share_rate_uses_available_precision_and_explicit_unknown():
    async with RackApp().run_test(size=(149, 45)) as pilot:
        card = pilot.app.query_one('#surfboard-card-pool4', SurfboardCard)
        card.set_data(dict(share_price=7.963529, primary='8.77', secondary='USD'))
        for width, expected in [(149, '1 sIMD = 7.964 IMD'), (180, '1 sIMD = 7.963529 IMD')]:
            await pilot.resize_terminal(width, 45)
            await pilot.pause()
            assert expected in strips(pilot.app, card)[-1].text
        card.set_data(dict(share_price=None))
        await pilot.pause()
        assert '1 sIMD = — IMD' in strips(pilot.app, card)[-1].text
