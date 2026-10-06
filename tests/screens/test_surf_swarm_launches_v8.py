"""Production launch screen behavior, entirely from the v8 capture."""
import pytest
from rich.text import Text
from textual.containers import VerticalScroll
from textual.widgets import DataTable

from maxpane_dashboard.screens.surf import _title_line
from maxpane_dashboard.widgets.surf import SurfSwarmLaunches
from tests.screens.test_surf_screen import _frozen_payload, _region_text, _screen_text, _surf_app
from tests.screens.test_surf_swarm_screen import _open
from tests.surf_launch_fixtures import launch_event, launch_row
from tests.widgets.address_probe import icon_targets, link_targets


def fired(**overrides):
    return dict(launch_event(), ts=1000., **overrides)


@pytest.mark.parametrize('agent,swarm', [(False, False), (True, False), (False, True)])
def test_launch_news_uses_typed_events_in_every_body_and_expires(agent, swarm):
    payload = _frozen_payload(as_of=4599., swarm_launch_fired=[fired()], sig_swarm_detail='WRONG')
    title = Text.from_markup(_title_line(payload, agent=agent, swarm=swarm)).plain
    assert '▲ SWARM LAUNCH $ZTO #737' in title
    assert 'WRONG' not in title
    payload['as_of'] = 4600.
    assert '▲' not in Text.from_markup(_title_line(payload, agent=agent, swarm=swarm)).plain


def test_launch_news_multiple_literal_and_default_worst_case_fit():
    from tests.screens.test_surf_screen import _worst_case_title_payload, WORST_CASE_TITLE_COLUMNS
    payload = _worst_case_title_payload()
    payload['swarm_launch_fired'] = [dict(fired(), ts=payload['as_of'], ticker='[red]X')]
    wide = Text.from_markup(_title_line(payload, row_hint=True, columns=220)).plain
    assert '▲ SWARM LAUNCH $[red]X #737' in wide
    assert wide.index('LP owner changed') < wide.index('▲') < wide.index('⚠ activity')
    narrow = Text.from_markup(_title_line(payload, row_hint=True, columns=143)).plain
    assert len(narrow) <= WORST_CASE_TITLE_COLUMNS
    assert '▲ SWARM LAUNCH #737' in narrow and '⚠ 8 src' in narrow
    assert narrow.index('LP owner changed') < narrow.index('▲') < narrow.index('⚠ 8 src')
    payload['swarm_launch_fired'].append(dict(fired(), ts=payload['as_of'], number=747))
    assert '▲ 2 SWARM LAUNCHES' in Text.from_markup(_title_line(payload)).plain


@pytest.mark.parametrize('opening', ['enter', 'click'])
async def test_launch_popup_opens_literal_snapshot_without_fetching(opening):
    from maxpane_dashboard.screens.swarm_detail import LaunchDetailScreen
    row = launch_row(ticker='[red]X', token_name='[bold]Literal name', site_label='zto',
                     site_ens_name='zto.site.identitymd.eth', site_link_method='named', site_link_trusted=True)
    async with _surf_app(_frozen_payload(swarm_launch_rows=[row])).run_test(size=(150, 46)) as pilot:
        screen = await _open(pilot)
        table = screen.query_one(SurfSwarmLaunches).query_one(DataTable)
        calls = screen._data_manager.calls
        table.focus()
        if opening == 'enter':
            await pilot.press('enter')
        else:
            await pilot.click(table, offset=(2, 1))
        await pilot.pause()
        popup = pilot.app.screen
        assert isinstance(popup, LaunchDetailScreen)
        row['token_name'] = 'MUTATED'
        scroll = popup.query_one(VerticalScroll)
        seen, icons, links = '', set(), set()
        while True:
            seen += '\n' + _screen_text(pilot.app)
            icons.update(a for _, _, a in icon_targets(pilot.app))
            links.update(v[5] for v in link_targets(pilot.app))
            if scroll.scroll_y >= scroll.max_scroll_y:
                break
            scroll.scroll_relative(y=10, animate=False)
            await pilot.pause()
        for word in ('$[red]X', '[bold]Literal name', 'PAIR', 'IMD', 'POOL FEE', '1.25%',
                     'REQUESTER', 'POLICY VERSION', '26', 'K1', 'K2', 'K3', 'K4', 'K6', 'K7',
                     'liquidity held by', '(unverified)', 'named', 'trusted'):
            assert word in seen, word
        assert 'MUTATED' not in seen
        assert row['checks']['K6']['evidence']['owner_is_factory'] is None
        assert '(factory, unverified)' not in seen
        assert not any(word in seen.lower() for word in ('locked', 'safe', 'audited'))
        assert {a['address'] for a in row['artifacts']} <= icons
        assert {f"https://etherscan.io/address/{a['address']}" for a in row['artifacts']} <= links
        assert 'https://zto.sites.imd.fun/' in links
        assert f"https://explorer.imd.fun/token/{row['token_address']}" in links
        assert screen._data_manager.calls == calls
        await pilot.press('escape')
        await pilot.pause()
        assert pilot.app.screen is screen


@pytest.mark.parametrize('chain_id,base', [(8453, 'https://basescan.org'), (4663, 'https://robinhoodchain.blockscout.com')])
async def test_launch_popup_chain_links_and_unknown_pair(chain_id, base):
    from maxpane_dashboard.screens.swarm_detail import LaunchDetailScreen
    row = launch_row(chain_id=chain_id, pair='0x'+'aa'*20)
    async with _surf_app(_frozen_payload()).run_test(size=(150, 46)) as pilot:
        await pilot.app.push_screen(LaunchDetailScreen(row))
        await pilot.pause()
        links = {v[5] for v in link_targets(pilot.app)}
        assert {f"{base}/address/{a['address']}" for a in row['artifacts']} <= links
        assert f"{base}/address/{row['pair']}" in links


async def test_launch_popup_tokenless_uses_job_and_immutables_evidence():
    from maxpane_dashboard.screens.swarm_detail import LaunchDetailScreen
    for number in (734, 747):
        row = launch_row(number)
        async with _surf_app(_frozen_payload()).run_test(size=(150, 80)) as pilot:
            await pilot.app.push_screen(LaunchDetailScreen(row))
            await pilot.pause()
            text = _screen_text(pilot.app)
            links = {v[5] for v in link_targets(pilot.app)}
            if number == 734:
                assert 'K6 · na' in text
                assert f"https://explorer.imd.fun/jobs/{row['job_id']}" in links
            else:
                # The shared hook needs no attestation; creation code proves the token.
                assert 'K3 · pass (immutables)' in text and 'state: pass_immutables' in text
                assert 'creation_offset: 740' in text


@pytest.mark.parametrize('count,word', [(1, '⚠ launch #737 K3'), (2, '⚠ 2 launch checks')])
def test_launch_mismatch_alarm_is_swarm_only(count, word):
    row = launch_row(verdict={'state':'mismatch', 'failed':'K3', 'passed':3})
    payload = _frozen_payload(swarm_launch_rows=[row]*count)
    assert word in Text.from_markup(_title_line(payload, swarm=True)).plain
    assert word not in Text.from_markup(_title_line(payload)).plain


@pytest.mark.parametrize('chain_id', [8453, 4663])
async def test_launch_popup_click_routes_copy_and_chain_explorer(chain_id):
    from maxpane_dashboard.screens.swarm_detail import LaunchDetailScreen
    row = launch_row(chain_id=chain_id)
    app = _surf_app(_frozen_payload())
    copied, opened = [], []
    app.action_copy_address = lambda address: copied.append(address)
    app.action_open_explorer = lambda explorer, kind, value: opened.append((explorer, kind, value))
    async with app.run_test(size=(150, 46)) as pilot:
        await app.push_screen(LaunchDetailScreen(row))
        await pilot.pause()
        address = row['artifacts'][0]['address']
        x, y, _ = next(t for t in icon_targets(app) if t[2] == address)
        await pilot.click(offset=(x, y))
        await pilot.pause()
        assert copied == [address]
        x, y, explorer, kind, value, _ = next(t for t in link_targets(app) if t[4] == address)
        await pilot.click(offset=(x, y))
        await pilot.pause()
        assert opened == [(explorer, kind, value)]
        assert isinstance(app.screen, LaunchDetailScreen)


@pytest.mark.parametrize('key', [None, 's', 'a', 'b', 'l', 'e', '4'])
async def test_launch_title_is_literal_accent_news_in_composited_bodies(key):
    payload = _frozen_payload()
    payload['swarm_launch_fired'] = [dict(fired(), ts=payload['as_of'], ticker='[red]X')]
    async with _surf_app(payload).run_test(size=(200, 48)) as pilot:
        screen = pilot.app.screen
        await screen._do_refresh()
        if key:
            await pilot.press(key)
        await pilot.pause()
        title = screen.query_one('#title-bar')
        assert '▲ SWARM LAUNCH $[red]X #737' in _region_text(pilot.app, title)
        from rich.color import Color
        accent = Color.parse(pilot.app.get_css_variables()['accent']).get_truecolor()
        segments = [seg for seg in screen._compositor.render_strips()[title.region.y] if '▲' in seg.text]
        assert segments and all(seg.style.color.get_truecolor(pilot.app.ansi_theme) == accent for seg in segments)


def test_launch_news_expires_while_the_signal_remains_fired():
    from maxpane_dashboard.analytics.surf_signals import build_signals
    event = launch_event()
    _, base = build_signals({}, {'swarm_launch_events': {'events': [], 'ts': 1000.}}, 1000.)
    _, base = build_signals(base, {'swarm_launch_events': {'events': [event], 'ts': 1001.}}, 1001.)
    for now, visible in ((4600., True), (4601., False)):
        signals, _ = build_signals(base, {'swarm_launch_events': None}, now)
        assert signals['sig_swarm_state'] == 'fired'
        payload = _frozen_payload(as_of=now, **signals)
        assert ('▲ SWARM LAUNCH' in Text.from_markup(_title_line(payload)).plain) is visible


@pytest.mark.parametrize('width', [129, 150])
@pytest.mark.parametrize('news_count,mismatch_count', [(1, 1), (1, 2), (2, 1), (2, 2), (0, 1), (0, 2), (1, 0), (2, 0)])
@pytest.mark.parametrize('health', ['abcdefghijkl', None])
async def test_crowded_swarm_title_keeps_every_fact(width, news_count, mismatch_count, health):
    from rich.color import Color
    from tests.screens.test_surf_screen import _worst_case_title_payload
    payload = _worst_case_title_payload()
    payload.update(swarm_breaker={'tripped': True},
                   swarm_services_up={'verifier': False, 'publisher': False, 'deployer': False},
                   swarm_health_status=health,
                   swarm_launch_fired=[dict(launch_event(), ts=payload['as_of'], ticker='[red]X')] * news_count,
                   swarm_launch_rows=[launch_row(verdict={'state': 'mismatch', 'failed': 'K3', 'passed': 3})] * mismatch_count)
    async with _surf_app(payload).run_test(size=(width, 30)) as pilot:
        screen = await _open(pilot)
        bar = screen.query_one('#title-bar')
        painted = _region_text(pilot.app, bar).strip()
        rendered = Text.from_markup(_title_line(payload, row_hint=True, swarm=True,
                                               columns=bar.content_size.width)).plain
        assert painted == rendered
        assert Text(painted).cell_len <= bar.content_size.width
        for word in ('IMD $0.71', 'par -2.7%', 'as of ', '‹ taller', 'LP changed',
                     '⚠ 8 src', 'breaker open', '3 svc down', 'health '):
            assert word in painted, (word, painted)
        if mismatch_count:
            assert ('launch #737 K3' if mismatch_count == 1 else '2 launch checks') in painted
        if news_count:
            assert '▲' in painted
            assert ('#737' if news_count == 1 else '2') in painted
            assert ('LAUNCHES' if news_count > 1 else 'LAUNCH') in painted
            assert painted.index('LP changed') < painted.index('▲') < painted.index('⚠ 8 src')
            accent = Color.parse(pilot.app.get_css_variables()['accent']).get_truecolor()
            segments = [seg for seg in screen._compositor.render_strips()[bar.region.y] if '▲' in seg.text]
            assert segments and all(seg.style.color.get_truecolor(pilot.app.ansi_theme) == accent for seg in segments)
        else:
            assert '▲' not in painted
        shown_health = painted.split('health ', 1)[1].split(' ', 1)[0]
        assert shown_health == (health or 'unavailable') or (
            shown_health.endswith('…') and (health or 'unavailable').startswith(shown_health[:-1]))


@pytest.mark.parametrize("height", [40, 41, 42, 43, 44, 46])
async def test_default_rail_all_eleven_detectors_has_honest_height_boundary(height):
    """143 columns: all WATCH rows clear at 43, and every shorter rail marks."""
    from maxpane_dashboard.widgets.surf.signals import DETECTOR_LABELS
    from maxpane_dashboard.analytics.surf_signals import SIGNAL_NAMES
    from tests.screens.test_surf_screen import _screen_at, _visible_panel
    from maxpane_dashboard.widgets.surf.signals import SurfSignals
    payload = _frozen_payload(swarm_launch_rows=[launch_row()])
    for name in SIGNAL_NAMES:
        payload[f"sig_{name}_state"] = "watch"
        payload[f"sig_{name}_detail"] = "pending"
    async with _screen_at(143, height, payload) as (app, screen, _pilot):
        rail = screen.query_one("#surf-right-rail")
        assert rail.show_vertical_scrollbar is (height < 43)
        assert ("‹ taller" in _screen_text(app)) is (height < 43)
        if height >= 43:
            visible = _visible_panel(app, screen.query_one(SurfSignals), rail)
            assert all(label in visible for label in DETECTOR_LABELS)

@pytest.mark.parametrize('ticker',['ZTO','字'*60,'Q[31mEVIL[/]R'])
async def test_fix1_default_pin_swarm_detail_literal_fits_and_sheds_address(ticker):
    from rich.cells import cell_len
    from maxpane_dashboard.widgets.surf.signals import SurfSignals
    from tests.screens.test_surf_screen import _screen_at
    row=launch_row(ticker=ticker)
    payload=_frozen_payload(sig_swarm_state='fired',sig_swarm_age_s=60,sig_swarm_chain_id=1,
        sig_swarm_detail=f'${ticker} #737 MAINNET ✓ {row["token_address"]}')
    async with _screen_at(143,46,payload) as (app,screen,pilot):
        panel=screen.query_one(SurfSignals)
        text=_region_text(app,panel)
        line=next(line for line in text.splitlines() if 'SWARM LAUNCH' in line)
        assert '#737' in line and '\\' not in line and '0x' not in line and '⧉' not in line
        assert cell_len(line.strip())<=panel.size.width
        if ticker.startswith('Q'):
            assert '$Q[31mEVIL[/]R' in line

@pytest.mark.parametrize('production,chain_id',[(True,1),(False,11155111)])
async def test_fix1_launch_popup_missing_site_nonproduction_checks_and_title(production,chain_id):
    from maxpane_dashboard.screens.swarm_detail import LaunchDetailScreen
    row=launch_row(production=production,chain_id=chain_id,site_label=None,site_ens_name=None)
    async with _surf_app(_frozen_payload()).run_test(size=(150,100)) as pilot:
        await pilot.app.push_screen(LaunchDetailScreen(row)); await pilot.pause()
        popup=pilot.app.screen
        text=_screen_text(pilot.app)
        if production:
            site_lines=text.split('SITE',1)[1].split('K1',1)[0]
            assert 'none' in site_lines and 'unavailable' not in site_lines
            assert 'unavailable · unavailable' not in text
        else:
            for key in ('K1','K2','K3','K4','K6','K7'):
                assert f'{key} · --' in text
            assert 'unknown' not in text
        title=popup.query_one('.record-detail-title')
        segments=[seg for strip in popup._compositor.render_strips()[title.region.y:title.region.bottom] for seg in strip if 'LAUNCH #' in seg.text]
        assert segments and all(seg.style.bold for seg in segments)
        title.styles.width=15; await pilot.pause(); popup._title(); await pilot.pause()
        painted=_region_text(pilot.app,title).strip()
        assert painted.endswith('…') and Text(painted).cell_len<=15
        assert title.render().cell_length<=15

@pytest.mark.parametrize('ticker,verdict',[('X'*120,'✗ K2'),('字'*60,'✓'),('Q[31mEVIL[/]R','✓')],ids=['long-ascii','wide','literal'])
async def test_fix2_signal_reserves_number_chain_and_verdict_at_pin(ticker,verdict):
    from rich.cells import cell_len
    from maxpane_dashboard.widgets.surf.signals import SurfSignals
    from tests.screens.test_surf_screen import _screen_at
    row=launch_row(ticker=ticker)
    payload=_frozen_payload(sig_swarm_state='fired',sig_swarm_age_s=60,sig_swarm_chain_id=1,
        sig_swarm_detail=f'${ticker} #737 MAINNET {verdict} {row["token_address"]} +2')
    async with _screen_at(143,46,payload) as (app,screen,pilot):
        panel=screen.query_one(SurfSignals)
        line=next(line for line in _region_text(app,panel).splitlines() if 'SWARM LAUNCH' in line)
        assert f'#737 MAINNET {verdict}' in line
        assert '\\' not in line and '0x' not in line and '⧉' not in line and '+2' not in line
        assert cell_len(line.strip())<=panel.size.width
        if ticker.startswith('Q'): assert '$Q[31mEVIL[/]R' in line
        else: assert '…' in line


async def test_fix2_popup_omits_absent_evidence_and_internal_metadata():
    from maxpane_dashboard.screens.swarm_detail import LaunchDetailScreen
    row = launch_row()
    row['checks']['K3']['evidence']['contracts'].append({
        'name': 'Undeployed', 'state': 'na', 'reason': 'not deployed by this launch',
        'address': None, 'tx_hash': None, 'expected_hash': None,
        'actual_hash': None, 'creation_hash': None, 'creation_offset': None})
    row['checks']['K3']['evidence']['contracts'][0].update(reason=None, creation_offset=0)
    row['checks']['K3']['evidence']['fixture_false'] = False
    async with _surf_app(_frozen_payload()).run_test(size=(150, 46)) as pilot:
        await pilot.app.push_screen(LaunchDetailScreen(row)); await pilot.pause()
        scroll = pilot.app.screen.query_one(VerticalScroll); seen = ''
        while True:
            seen += '\n' + _screen_text(pilot.app)
            if scroll.scroll_y >= scroll.max_scroll_y: break
            scroll.scroll_relative(y=10, animate=False); await pilot.pause()
        assert 'not deployed by this launch' in seen
        assert 'unavailable' not in seen and 'rule_version' not in seen
        assert 'creation_offset: 0' in seen and 'fixture_false: False' in seen
        assert 'PoolInitializationGuard' in seen


@pytest.mark.parametrize('ticker', ['FOO #1', 'FOO #1 MAINNET ✓ ' + 'X'*120], ids=['number-in-ticker', 'spoofed-identity'])
async def test_fix2_signal_reserves_final_launch_identity(ticker):
    from maxpane_dashboard.widgets.surf.signals import SurfSignals
    from tests.screens.test_surf_screen import _screen_at
    row = launch_row(ticker=ticker)
    payload = _frozen_payload(sig_swarm_state='fired', sig_swarm_age_s=60,
        sig_swarm_chain_id=1, sig_swarm_detail=f'${ticker} #737 MAINNET ✗ K2 {row["token_address"]} +2')
    async with _screen_at(143,46,payload) as (app,screen,pilot):
        line = next(line for line in _region_text(app,screen.query_one(SurfSignals)).splitlines() if 'SWARM LAUNCH' in line)
        assert '#737 MAINNET ✗ K2' in line
        assert '0x' not in line and '\\' not in line
        assert ('+2' in line) is (ticker == 'FOO #1')


@pytest.mark.parametrize('state,ticker,chain', [('watch','字'*120,1), ('watch','FOO #1 MAINNET ✓ '+'X'*120,1), ('fired','字'*120,None), ('fired','ZTO',1)], ids=['watch-wide','watch-spoof','fired-unknown-chain','fired-count'])
async def test_fix3_structured_signal_identity_and_count_at_pin(state, ticker, chain):
    from rich.cells import cell_len
    from maxpane_dashboard.widgets.surf.signals import SurfSignals
    from tests.screens.test_surf_screen import _screen_at
    from tests.surf_launch_fixtures import launch_event
    selected = launch_event(737, ticker=ticker)
    selected.update(chain_id=chain, verdict_state='mismatch', verdict_failed='K2', extra_count=2)
    payload = _frozen_payload(sig_swarm_state=state, sig_swarm_age_s=60,
        sig_swarm_chain_id=chain, sig_swarm_detail='untrusted stale #999', sig_swarm_launch=selected)
    async with _screen_at(143,46,payload) as (app,screen,pilot):
        panel = screen.query_one(SurfSignals)
        line = next(line for line in _region_text(app,panel).splitlines() if 'SWARM LAUNCH' in line)
        assert '#737' in line and '#999' not in line and '0x' not in line and '⧉' not in line
        assert cell_len(line.strip()) <= panel.size.width
        if state == 'watch': assert 'deploying' in line
        else: assert ('#737 -- ✗ K2' if chain is None else '#737 MAINNET ✗ K2') in line
        if ticker == 'ZTO': assert '+2' in line


@pytest.mark.parametrize('state,detail,identity', [
    ('watch', 'deploying $'+'X'*120+' #737', 'deploying'),
    ('fired', '$'+'X'*120+' #737 -- ✗ K2', '#737 -- ✗ K2'),
    ('fired', '$ZTO #737 MAINNET ✓ '+launch_row()['token_address']+' +2', '+2'),
], ids=['watch', 'unknown-chain', 'count'])
async def test_fix3_legacy_signal_detail_keeps_identity_and_count(state, detail, identity):
    from maxpane_dashboard.widgets.surf.signals import SurfSignals
    from tests.screens.test_surf_screen import _screen_at
    payload = _frozen_payload(sig_swarm_state=state, sig_swarm_detail=detail, sig_swarm_age_s=60)
    async with _screen_at(143,46,payload) as (app,screen,pilot):
        line = next(line for line in _region_text(app,screen.query_one(SurfSignals)).splitlines() if 'SWARM LAUNCH' in line)
        assert '#737' in line and identity in line
        assert '0x' not in line and '⧉' not in line
