"""Card footer semantics observed through Textual's compositor."""
import pytest
from rich.color import Color
from maxpane_dashboard.widgets.surfboard.rack import SurfboardCard
from tests.widgets.test_surfboard_rack import RackApp
from tests.surfboard_fixtures import hub_payload


def strips(app, card):
    return [line.crop(card.region.x, card.region.right) for line in
            app.screen._compositor.render_strips()[card.region.y:card.region.bottom]]


@pytest.mark.parametrize('key', ['agent', 'agent-2', 'agent-3', 'agent-4', 'board'])
async def test_offline_footer_keeps_a_full_empty_track_and_red_off_label(key):
    async with RackApp().run_test(size=(149, 45)) as pilot:
        card = pilot.app.query_one(f'#surfboard-card-{key}', SurfboardCard)
        card.set_data(dict(token_id=420 if key != 'board' else None, primary='420', secondary='0 of 3 slots', status='offline',
            meter_kind='activity', meter_state='offline', numerator=43200, denominator=86400))
        await pilot.pause()
        footer = strips(pilot.app, card)[-1]
        assert footer.text == '╰─ OFF ' + '▱' * (card.region.width - 10) + ' ─╯'
        label = next(segment for segment in footer if 'OFF' in segment.text)
        assert label.style.color.get_truecolor() == pilot.app.ansi_theme.ansi_colors[1]


@pytest.mark.parametrize('status', ['working', 'idle', 'offline'])
async def test_leaderboard_inner_border_title_and_footer_match_agent_status(status):
    async with RackApp().run_test(size=(149, 45)) as pilot:
        colors = []
        for key in ('agent', 'agent-2', 'agent-3', 'agent-4', 'board'):
            card = pilot.app.query_one(f'#surfboard-card-{key}', SurfboardCard)
            card.set_data(dict(token_id=420 if key != 'board' else None, primary='420', secondary='0 of 3 slots', status=status))
        await pilot.pause()
        for key in ('agent', 'agent-2', 'agent-3', 'agent-4', 'board'):
            card = pilot.app.query_one(f'#surfboard-card-{key}', SurfboardCard)
            rows = strips(pilot.app, card)
            top = next(row for row in rows if '┌' in row.text)
            bottom = next(row for row in rows if '└' in row.text)
            colors.append([segment.style.color for row in (top, bottom)
                           for segment in row if '┌' in segment.text or '└' in segment.text])
        assert all(color == colors[0] for color in colors[1:])
        if status != 'idle':
            expected = (Color.parse(pilot.app.get_css_variables()['accent']).get_truecolor()
                        if status == 'working' else pilot.app.ansi_theme.ansi_colors[1])
            assert all(color.get_truecolor() == expected for color in colors[1])


@pytest.mark.parametrize('key', ['agent', 'board'])
async def test_projected_activity_drains_orange_from_24_to_72_hours_and_resets(key):
    from maxpane_dashboard.data import surfboard as hub
    from tests.data.test_surfboard_activity import NOW, TOKEN, stopped, workers

    data = dict(swarm_seat_selected={'token_id': TOKEN},
                swarm_board_rows=[dict(rank=1, token_id=TOKEN, accepted=10)])
    history = stopped()
    async with RackApp().run_test(size=(149, 45)) as pilot:
        card = pilot.app.query_one(f'#surfboard-card-{key}', SurfboardCard)
        for hours, green_fraction, orange_fraction in [
            (0, 1, 0), (12, .5, .5), (23.999, 1 / 24000, 0), (24, 0, 1), (36, 0, .75),
            (48, 0, .5), (60, 0, .25), (72, 0, 0), (96, 0, 0),
        ]:
            now = NOW + hours * 3600
            history = hub.work_activity.observe(history, workers(0), now=now)
            row = next(c for c in hub.cards(data, {}, now=now, activity=history) if c['key'] == key)
            card.set_data(row)
            await pilot.pause()
            cells = card.region.width - 11
            green = max(1, int(cells * green_fraction)) if hours < 24 else 0
            orange = cells - green if hours < 24 else int(cells * orange_fraction)
            footer = strips(pilot.app, card)[-1]
            assert footer.text == '╰─ IDLE ' + '▰' * (green + orange) + '▱' * (cells - green - orange) + ' ─╯'
            colors = [segment.style.color.get_truecolor() for segment in footer
                      for char in segment.text if char == '▰']
            assert colors == ([pilot.app.ansi_theme.ansi_colors[2]] * green
                              + [pilot.app.ansi_theme.ansi_colors[3]] * orange)
            idle = next(s.style for s in footer if 'IDLE' in s.text)
            protocol = pilot.app.query_one('#surfboard-card-protocol', SurfboardCard)
            neutral = next(s.style for s in strips(pilot.app, protocol)[-1] if 'unavailable' in s.text)
            assert (idle.color, idle.dim) == (neutral.color, neutral.dim)

        # A later job restores all green; its next stop starts a new first day.
        for count, label in [(1, 'BUSY'), (0, 'IDLE')]:
            now += 120
            history = hub.work_activity.observe(history, workers(count), now=now)
            card.set_data(next(c for c in hub.cards(data, {}, now=now, activity=history) if c['key'] == key))
            await pilot.pause()
            footer = strips(pilot.app, card)[-1]
            assert footer.text == f'╰─ {label} ' + '▰' * cells + ' ─╯'
            assert all(s.style.color.get_truecolor() == pilot.app.ansi_theme.ansi_colors[2]
                       for s in footer if '▰' in s.text)


@pytest.mark.parametrize('key', ['agent', 'agent-2', 'agent-3', 'agent-4', 'board'])
async def test_activity_footer_labels_colors_and_full_half_empty_unknown(key):
    async with RackApp().run_test(size=(149, 45)) as pilot:
        card = pilot.app.query_one(f'#surfboard-card-{key}', SurfboardCard)
        for state, remaining, label, ratio, color in [
            ('busy', 86400, 'BUSY', 1, 3), ('idle', 43200, 'IDLE', .5, 2),
            ('idle', 0, 'IDLE', 0, 2), ('idle', None, 'IDLE', None, 2),
            ('busy', 86400, 'BUSY', 1, 3),
            ('stale', None, '—', None, 3), ('unavailable', None, '—', None, 3),
        ]:
            card.set_data(dict(token_id=420 if key != 'board' else None, primary='420', secondary='0 of 3 slots', status='active',
                meter_kind='activity', meter_state=state, numerator=remaining, denominator=86400))
            await pilot.pause()
            footer = strips(pilot.app, card)[-1]
            assert 'PASS' not in footer.text
            assert footer.text.startswith('╰─ ' + label + ' ')
            ink = next(segment.style.color.get_truecolor() for segment in footer if label in segment.text)
            protocol = pilot.app.query_one('#surfboard-card-protocol', SurfboardCard)
            neutral = next(s.style for s in strips(pilot.app, protocol)[-1] if 'unavailable' in s.text)
            expected = (neutral.color.get_truecolor()
                        if state == 'idle' else pilot.app.ansi_theme.ansi_colors[color])
            assert ink == expected
            if ratio is None:
                assert '▰' not in footer.text and '▱' not in footer.text
            else:
                cells = card.region.width - 11
                assert footer.text == '╰─ ' + label + ' ' + '▰' * cells + ' ─╯'
                colors = [segment.style.color.get_truecolor() for segment in footer
                          for char in segment.text if char == '▰']
                green = int(cells * ratio)
                assert colors == ([pilot.app.ansi_theme.ansi_colors[2]] * green
                                  + [pilot.app.ansi_theme.ansi_colors[3]] * (cells - green))
                if remaining is None:
                    assert card.data['numerator'] is None


@pytest.mark.parametrize('key', ['announce', 'swarm-tokens'])
async def test_news_footer_hides_only_known_zero(key):
    async with RackApp().run_test(size=(149, 45)) as pilot:
        card = pilot.app.query_one(f'#surfboard-card-{key}', SurfboardCard)
        for value, expected in [('0 new replies' if key == 'announce' else '0 new', ''),
                                ('2 new replies' if key == 'announce' else '2 new', '2 new'),
                                ('unavailable', 'unavailable')]:
            ranking = next(row['token_ranking'] for row in hub_payload()['surfboard_cards'] if row['key']=='swarm-tokens')
            card.set_data(dict(primary='post', secondary=value, token_ranking=ranking if key=='swarm-tokens' else None))
            await pilot.pause()
            lines = strips(pilot.app, card)
            bottom = next(line.text for line in lines if '└' in line.text)
            assert bottom[bottom.index('└')+1:bottom.index('┘')].strip('─ ') == expected


async def test_protocol_columns_are_label_amount_unit_without_colons_or_inner_footer():
    async with RackApp().run_test(size=(149, 45)) as pilot:
        card = pilot.app.query_one('#surfboard-card-protocol', SurfboardCard)
        card.set_data(dict(primary='★ burned 33k IMD\n★ rewarded 6k IMD\n★ fees 4k IMD', secondary='0.47%'))
        await pilot.pause()
        lines = strips(pilot.app, card)
        top = next(i for i, line in enumerate(lines) if '┌' in line.text)
        body = [line.text[line.text.index('│', 1)+1:line.text.rindex('│')].strip('│ ')
                for line in lines[top+1:top+4]]
        assert [line.split() for line in body] == [['burned', '33k', 'IMD'], ['rewarded', '6k', 'IMD'], ['fees', '4k', 'IMD']]
        assert len({line.index('IMD') for line in body}) == 1
        assert len({line.index(label) for line, label in zip(body, ('burned', 'rewarded', 'fees'))}) == 1
        assert len({line.index(amount) for line, amount in zip(body, ('33k', '6k', '4k'))}) == 1
        assert not any(':' in line or '★' in line for line in body)
        bottom = lines[top+4].text
        assert bottom[bottom.index('└')+1:bottom.index('┘')].strip('─ ') == ''


@pytest.mark.parametrize('key,label', [('swarm-tokens', '24h')])
async def test_volume_has_green_buckets_and_visible_partial_gaps(key, label):
    async with RackApp().run_test(size=(149, 45)) as pilot:
        card = pilot.app.query_one(f'#surfboard-card-{key}', SurfboardCard)
        for state, points in [('ok', list(range(8))), ('partial', [0, 1, None, 3, 4, 5, 6, 7]),
                              ('stale', list(range(8))), ('unavailable', None)]:
            card.set_data(dict(meter_kind='sparkline', meter_state=state, points=points, secondary='0 new'))
            await pilot.pause()
            footer = strips(pilot.app, card)[-1]
            assert 'TOKENS' not in footer.text
            if state == 'ok':
                assert label + ' ' in footer.text and '█' in footer.text and '▁' in footer.text
            elif state == 'partial':
                assert label + ' ' in footer.text and '·' in footer.text and '█' in footer.text
            elif state == 'stale':
                assert label + ' ' in footer.text and '█' in footer.text
            else:
                assert label + ' —' in footer.text
                assert not any(char in footer.text for char in '▁▂▃▄▅▆▇█')
            for segment in footer:
                if any(char in segment.text for char in '▁▂▃▄▅▆▇█'):
                    assert segment.style.color.get_truecolor() == pilot.app.ansi_theme.ansi_colors[2]


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
        assert '1 sIMD = 7.963529 IMD' in strips(pilot.app, card)[-1].text
