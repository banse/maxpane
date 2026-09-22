"""Worker metadata mixes and source-labelled served token count."""
import pytest
from maxpane_dashboard.app import CSS_PATH
from maxpane_dashboard.data import surf_swarm as fold
from maxpane_dashboard.widgets.surf.swarm_fleet import SurfSwarmFleet
from tests.surf_swarm_fixtures import swarm_capture_v3
from tests.widgets.surf_compositing import composite_lines
WORKERS=swarm_capture_v3('workers')
FLEET=fold.fleet(WORKERS)
SUMMARY=fold.board_summary(swarm_capture_v3('contributors'),WORKERS)
async def render(fleet=FLEET,summary=SUMMARY):
    return '\n'.join(await composite_lines(SurfSwarmFleet,(37,20),css_path=CSS_PATH,
        swarm_fleet=fleet,swarm_board_summary=summary,
        swarm_board_as_of_hhmm='03:01',swarm_workers_as_of_hhmm='04:02'))
async def test_mixes_tokens_and_clocks_have_distinct_sources():
    text=await render()
    for word in ('FLEET','runtime','daemon','os','profile','slots','heartbeat','tokens / completed job','served','PAUSED','03:01','04:02'):
        assert word in text
async def test_empty_metadata_is_none_reported_and_unread_is_unavailable():
    assert 'none reported' in await render(dict(FLEET,runtimes=[]))
    text=await render(None)
    assert 'runtime unavailable' in text and 'served' in text
    text=await render(FLEET,None)
    assert 'tokens / completed job' in text and 'unavailable' in text and 'runtime unavailable' not in text
async def test_mix_omissions_are_exact_and_hostile_text_is_sanitized():
    values=[{'value':'[/x]alpha','count':9}]+[{'value':f'daemon{i}','count':8-i} for i in range(7)]
    text=await render(dict(FLEET,daemons=values))
    line=next(line for line in text.splitlines() if 'daemon' in line)
    assert 'alpha 9' in line and '+6' in line and '[/x]' not in text
async def test_paused_omission_count_is_exact():
    paused=[{'token_id':i,'until_ts':1_758_456_000+i,'failures':3} for i in range(99)]
    text=await render(dict(FLEET,paused=paused))
    line=next(line for line in text.splitlines() if 'PAUSED' in line)
    assert '#0 until' in line and '+98' in line

@pytest.mark.parametrize('key,label',[('runtimes','runtime'),('daemons','daemon'),('os','os'),('profiles','profile'),('concurrency','slots')])
async def test_every_metadata_mix_strips_third_party_markup(key,label):
    text=await render(dict(FLEET,**{key:[{'value':'[/x]PWNED','count':1}]}))
    assert f'{label} PWNED 1' in text and '[/x]' not in text

async def test_full_served_daemon_is_retained_when_it_fits():
    text=await render(dict(FLEET,daemons=[{'value':'abcdef0123456789','count':67}]))
    assert 'abcdef0123456789 67' in text

async def test_long_metadata_is_counted_as_omitted():
    text=await render(dict(FLEET,daemons=[{'value':'x'*64,'count':67}]))
    assert 'daemon +1' in text

async def test_malformed_paused_tokens_never_reach_display():
    paused=[{'token_id':'[/x]PWNED','until_ts':1758456000,'failures':3},
            {'token_id':0,'until_ts':1758456000,'failures':3}]
    text=await render(dict(FLEET,paused=paused))
    assert '#0 until' in text and 'PWNED' not in text and '[/x]' not in text
