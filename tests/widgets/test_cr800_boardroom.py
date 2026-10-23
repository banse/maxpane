import pytest

from maxpane_dashboard.widgets.surfboard.rack import SurfboardCard, SurfboardRack
from tests.screens.test_surfboard_layout import HubHarness
from tests.surfboard_fixtures import hub_payload
from tests.widgets.test_surfboard_rack import card_strips


@pytest.mark.parametrize('count', [0, 3, None])
async def test_workflows_footer_and_swarm_history_stay_with_their_sources(count):
    payload = hub_payload()
    rows = {row['key']: row for row in payload['surfboard_cards']}
    rows['work']['work_summary']['workflows'] = count
    rows['work']['secondary'] = '0 working'
    app = HubHarness(payload)
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        work = app.hub.query_one('#surfboard-card-work', SurfboardCard)
        swarm = app.hub.query_one('#surfboard-card-swarm', SurfboardCard)
        assert f"{'—' if count is None else count} workflows" in card_strips(app, work)[-1].text
        assert '0 working' in '\n'.join(s.text for s in card_strips(app, work))
        assert '24H' in card_strips(app, swarm)[-1].text
        assert 'build' not in card_strips(app, swarm)[-1].text


@pytest.mark.parametrize('signals', [0, 3, 11, None])
async def test_signal_count_precedes_label_and_bar_has_exact_number_of_lit_cells(signals):
    payload = hub_payload()
    row = next(r for r in payload['surfboard_cards'] if r['key'] == 'announce')
    row.update(numerator=signals, denominator=11)
    app = HubHarness(payload)
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        card = app.hub.query_one('#surfboard-card-announce', SurfboardCard)
        text = card_strips(app, card)[-1].text
        assert f"{'—' if signals is None else signals} SIGNALS" in text
        if '▰' in text:
            assert text.count('▰') == signals


async def test_token_card_renders_latest_three_without_market_coverage_dependency():
    payload = hub_payload()
    row = next(r for r in payload['surfboard_cards'] if r['key'] == 'swarm-tokens')
    row['token_ranking'].update(state='partial', latest=[
        dict(symbol=name, age_s=age, chain='eth') for name, age in
        [('NEWEST', 60), ('SECOND', 1800), ('OLD', 172800)]])
    app = HubHarness(payload)
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        card = app.hub.query_one('#surfboard-card-swarm-tokens', SurfboardCard)
        text = '\n'.join(s.text for s in card_strips(app, card))
        assert 'LATEST' in text
        assert text.index('NEWEST') < text.index('SECOND') < text.index('OLD')
        assert 'SFPT' not in text
