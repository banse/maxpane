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
    return '\n'.join(await composite_lines(SurfSwarmFleet,(37,30),css_path=CSS_PATH,
        swarm_fleet=fleet,swarm_board_summary=summary,
        swarm_board_as_of_hhmm='03:01',swarm_workers_as_of_hhmm='04:02'))
async def test_mixes_tokens_and_clocks_have_distinct_sources():
    text=await render()
    for word in ('FLEET','runtime','daemon','os','profile','slots','heartbeat','tokens/job','served','paused','03:01','04:02'):
        assert word in text
async def test_empty_metadata_is_none_reported_and_unread_is_unavailable():
    assert 'none reported' in await render(dict(FLEET,runtimes=[]))
    text=await render(None)
    assert 'runtime    unavailable' in text and 'served' in text
    text=await render(FLEET,None)
    assert 'tokens/job' in text and 'unavailable' in text and 'runtime    unavailable' not in text
async def test_mix_omissions_are_exact_and_hostile_text_is_sanitized():
    values=[{'value':'[/x]alpha','count':9}]+[{'value':f'daemon{i}','count':8-i} for i in range(7)]
    text=await render(dict(FLEET,daemons=values))
    line=next(line for line in text.splitlines() if 'daemon' in line)
    assert 'alpha 9' in line and '+7' in line and '[/x]' not in text
async def test_paused_omission_count_is_exact():
    paused=[{'token_id':i,'until_ts':1_758_456_000+i,'failures':3} for i in range(99)]
    text=await render(dict(FLEET,paused=paused))
    assert 'paused     99' in text
    line=next(line for line in text.splitlines() if '#0 until' in line)
    assert '#0 until' in line and '+98' in line

@pytest.mark.parametrize('key,label',[('runtimes','runtime'),('daemons','daemon'),('os','os'),('profiles','profile'),('concurrency','slots')])
async def test_every_metadata_mix_strips_third_party_markup(key,label):
    text=await render(dict(FLEET,**{key:[{'value':'[/x]PWNED','count':1}]}))
    assert f'{label:<11}PWNED 1' in text and '[/x]' not in text

async def test_full_served_daemon_is_retained_when_it_fits():
    text=await render(dict(FLEET,daemons=[{'value':'abcdef0123456789','count':67}]))
    assert 'abcdef0123456789 67' in text

async def test_long_metadata_is_counted_as_omitted():
    text=await render(dict(FLEET,daemons=[{'value':'x'*64,'count':67}]))
    assert 'daemon     +1' in text

async def test_malformed_paused_tokens_never_reach_display():
    paused=[{'token_id':'[/x]PWNED','until_ts':1758456000,'failures':3},
            {'token_id':0,'until_ts':1758456000,'failures':3}]
    text=await render(dict(FLEET,paused=paused))
    assert '#0 until' in text and 'PWNED' not in text and '[/x]' not in text


async def test_polish_groups_align_labels_and_keep_the_advertised_model_prefix():
    from tests.surf_swarm_fixtures import swarm_capture_v4
    text=await render(fold.fleet(swarm_capture_v4('workers')))
    lines=text.splitlines()
    labels=('runtime','model','daemon','os','profile','slots','heartbeat','paused','tokens/job')
    for label in labels:
        line=next(line.strip() for line in lines if line.strip().startswith(label+' '))
        assert line.startswith(label.ljust(11)), (label,line)
    assert 'astra 6 xhigh 43' in text and '+2 (advertised)' in text
    header=next(i for i,line in enumerate(lines) if 'CONTRIBUTORS · as of 03:01' in line)
    paused=next(i for i,line in enumerate(lines) if line.strip().startswith('paused '))
    assert not lines[paused-1].strip() and not lines[header-1].strip()
    assert 'FLEET · workers as of 04:02' in text
    assert 'tokens / completed job' not in text
    assert not lines[header+1].strip(), 'owner 2026-09-22: a blank row under CONTRIBUTORS'
    assert 'served' in lines[header+7]


async def test_contributors_show_devices_outcomes_turns_and_tokens():
    lines=(await render(summary=SUMMARY)).splitlines()
    header=next(i for i,line in enumerate(lines) if 'CONTRIBUTORS' in line)
    body=[line.strip() for line in lines[header+2:header+7]]
    s=SUMMARY
    assert body==[
        f"devices    {s['devices']:,} · {s['seats']:,} seats",
        f"accepted   {s['accepted']:,} of {s['attempts']:,}",
        f"rejected   {s['rejected']:,} · {s['pending']:,} pending",
        f"turns      {s['turns']:,} · {(s['wall_clock_ms']+1_800_000)//3_600_000:,} h",
        f"tokens     {s['input_tokens']/1e6:.1f}M in · {s['output_tokens']/1e6:.1f}M out",
    ]


@pytest.mark.parametrize('ms,shown',[(59*60_000,'1 h'),(int(5.9*3_600_000),'6 h'),
    (int(5.4*3_600_000),'5 h'),(29*60_000+29_000,'29 min'),(0,'0 min'),(30*60_000,'1 h')])
async def test_contributor_hours_round_and_under_half_an_hour_read_minutes(ms,shown):
    """F64: 59 minutes floored to ``0 h`` and 5.9 h to ``5 h``."""
    lines=(await render(summary=dict(SUMMARY,wall_clock_ms=ms))).splitlines()
    turns=next(l.strip() for l in lines if l.strip().startswith('turns '))
    assert turns==f"turns      {SUMMARY['turns']:,} · {shown}"


async def test_an_unread_contributor_value_is_unavailable_never_zero():
    text=await render(summary=dict(SUMMARY,devices=None,attempts=None,input_tokens=None,
                                   wall_clock_ms=None))
    assert 'devices    unavailable' in text and 'tokens     unavailable' in text
    assert any(l.strip()==f"accepted   {SUMMARY['accepted']:,}" for l in text.splitlines())
    assert any(l.strip()==f"turns      {SUMMARY['turns']:,}" for l in text.splitlines())
    none=await render(summary=None)
    for label in ('devices','accepted','rejected','turns','tokens'):
        assert f'{label:<11}unavailable' in none


async def test_a_contributor_pair_too_wide_for_its_line_counts_its_second_value():
    text=await render(summary=dict(SUMMARY,rejected=99_999_999,pending=99_999_999))
    assert any(l.strip()=='rejected   99,999,999 · +1' for l in text.splitlines()), text


async def test_polish_model_missing_none_and_hostile_values_are_distinct():
    none=await render(dict(FLEET,models=[dict(model=None,effort=None,count=3)]))
    assert 'none 3' in none and '(advertised)' in none
    unread=await render(dict(FLEET,models=None))
    assert 'model      unavailable' in unread and 'none 3' not in unread
    hostile=await render(dict(FLEET,models=[dict(model='[/x]astra',effort='[$success]high',count=2)]))
    assert 'astra high 2' in hostile and '[/x]' not in hostile and '[$success]' not in hostile
    long=await render(dict(FLEET,models=[dict(model='x'*64,effort='high',count=99999)]))
    assert 'model      +1' in long and '…' not in long


@pytest.mark.parametrize('paused,color', [([],2),([dict(token_id=420,until_ts=1758456000,failures=3)],1)])
async def test_polish_paused_state_and_numbers_have_composited_styles(paused,color):
    from textual.app import App
    class Harness(App):
        CSS_PATH=CSS_PATH
        def compose(self):yield SurfSwarmFleet()
    async with Harness().run_test(size=(37,30)) as pilot:
        pilot.app.query_one(SurfSwarmFleet).update_data(swarm_fleet=dict(FLEET,paused=paused),swarm_board_summary=SUMMARY)
        await pilot.pause()
        lines=[''.join(seg.text for seg in strip) for strip in pilot.app.screen._compositor.render_strips()]
        y=next(i for i,line in enumerate(lines) if line.strip().startswith('paused '))
        value='1' if paused else 'none'
        x=lines[y].index(value,lines[y].index('paused')+6)
        state=pilot.app.screen.get_style_at(x,y)
        assert state.color.get_truecolor()==pilot.app.ansi_theme.ansi_colors[color]
        label=pilot.app.screen.get_style_at(lines[y].index('paused'),y)
        assert label.color!=state.color
        if paused:assert state.bold
        token_y=next(i for i,line in enumerate(lines) if 'tokens/job' in line)
        count_x=lines[token_y].index(str(SUMMARY['tokens_per_completed_job'])[0],lines[token_y].index('tokens/job')+10)
        assert pilot.app.screen.get_style_at(count_x,token_y).bold
        if paused:assert '#420 until' in '\n'.join(lines)
