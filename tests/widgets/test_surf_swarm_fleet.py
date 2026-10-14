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
# Synthetic renderer contract: receipt accounting intentionally differs from canonical outcomes.
SUMMARY.update({f'receipt_{key}': SUMMARY[key] for key in ('seats','attempts','accepted','rejected','pending')})
SUMMARY.update(seats=50,attempts=100,accepted=80,rejected=5,failed=3,pending=12)
async def render(fleet=FLEET,summary=SUMMARY):
    return '\n'.join(await composite_lines(SurfSwarmFleet,(37,30),css_path=CSS_PATH,
        swarm_fleet=fleet,swarm_board_summary=summary,
        swarm_board_as_of_hhmm='02:00',swarm_contributors_as_of_hhmm='03:01',swarm_workers_as_of_hhmm='04:02'))
async def test_mixes_tokens_and_clocks_have_distinct_sources():
    text=await render()
    for word in ('FLEET','runtime','daemon','os','profile','slots','heartbeat','tokens/job','served','paused','03:01','04:02'):
        assert word in text

async def test_expanded_worker_groups_show_each_entry_and_top_three_models():
    fleet = dict(FLEET,
        runtimes=[dict(value='codex',count=453),dict(value='claude',count=401),dict(value='both',count=12)],
        models=[dict(model=None,effort=None,count=500),
                dict(model='gpt-6-astra',effort='xhigh',count=396),
                dict(model='claude-fable-5-1',effort='high',count=250),
                dict(model='claude-opus-5-5',effort='high',count=99),
                dict(model='claude-sonnet-5',effort='high',count=20)],
        daemons=[dict(value='0.1.0+35c7abcdef01234567',count=800),dict(value='older',count=66)],
        os=[dict(value='linux',count=853),dict(value='darwin',count=12),dict(value='windows',count=1)],
        concurrency=[dict(value=str(n),count=100-n) for n in (1,2,3,8)])
    lines=await composite_lines(SurfSwarmFleet,(37,50),css_path=CSS_PATH,swarm_fleet=fleet)
    for label,values in [('runtime',['codex 453','claude 401','both 12']),
                         ('model',['astra 6 xhigh 396','fable 5.1 high 250','opus 5.5 high 99']),
                         ('os',['linux 853','darwin 12','windows 1']),
                         ('slots',['1 99','2 98','3 97','8 92'])]:
        start=next(i for i,line in enumerate(lines) if line.strip().startswith(label+' '))
        assert [line.strip() for line in lines[start:start+len(values)]] == [label.ljust(11)+values[0],*values[1:]]
    daemon=next(line.strip() for line in lines if line.strip().startswith('daemon '))
    assert daemon.startswith('daemon     0.1.0+') and daemon.endswith('… 800')
    assert not any('older' in line or 'sonnet' in line for line in lines)
    assert any('+1 (advertised)' in line for line in lines)
async def test_empty_metadata_is_none_reported_and_unread_is_unavailable():
    assert 'none reported' in await render(dict(FLEET,runtimes=[]))
    text=await render(None)
    assert 'runtime    unavailable' in text and 'served' in text
    text=await render(FLEET,None)
    assert 'tokens/job' in text and 'unavailable' in text and 'runtime    unavailable' not in text
async def test_only_the_most_used_daemon_is_shown_and_hostile_text_is_sanitized():
    values=[{'value':'[/x]alpha','count':9}]+[{'value':f'daemon{i}','count':8-i} for i in range(7)]
    text=await render(dict(FLEET,daemons=values))
    line=next(line for line in text.splitlines() if 'daemon' in line)
    assert 'alpha 9' in line and '+7' not in line and '[/x]' not in text
    assert 'daemon0' not in text
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

async def test_long_daemon_keeps_its_name_prefix_and_exact_count():
    text=await render(dict(FLEET,daemons=[{'value':'x'*64,'count':67}]))
    line=next(line.strip() for line in text.splitlines() if line.strip().startswith('daemon '))
    assert line.startswith('daemon     xxx') and line.endswith('… 67')

async def test_expanded_groups_shrink_on_refresh_and_clear_unknown_tooltips():
    from textual.app import App
    class Harness(App):
        CSS_PATH=CSS_PATH
        def compose(self):yield SurfSwarmFleet()
    async with Harness().run_test(size=(60,50),tooltips=True) as pilot:
        widget=pilot.app.query_one(SurfSwarmFleet)
        version='0.1.0+'+'abc123'*6
        widget.update_data(swarm_fleet=dict(FLEET,daemons=[dict(value=version,count=777)]))
        await pilot.pause()
        before=widget.size.height
        await pilot.hover('#surf-fleet-daemon')
        pilot.app.screen._handle_tooltip_timer(widget.query_one('#surf-fleet-daemon'))
        await pilot.pause()
        text='\n'.join(''.join(seg.text for seg in strip) for strip in pilot.app.screen._compositor.render_strips())
        assert version in ''.join(text.split()) and '777' in text
        pilot.app.screen._clear_tooltip()
        widget.update_data(swarm_fleet=dict(FLEET,runtimes=[dict(value='codex',count=1)],os=[],concurrency=[]))
        await pilot.hover('#surf-fleet-runtime')
        await pilot.pause()
        assert widget.size.height < before
        text='\n'.join(''.join(seg.text for seg in strip) for strip in pilot.app.screen._compositor.render_strips())
        assert 'claude 37' not in text and 'darwin 12' not in text
        widget.update_data(swarm_fleet=None)
        await pilot.pause()
        for name in ('runtime','daemon','os','slots','model'):
            assert widget.query_one(f'#surf-fleet-{name}').tooltip is None

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
    assert 'astra 6 xhigh 43' in text and 'fable 5.1 high 34' in text
    assert '(advertised)' in text and '+2 (advertised)' not in text
    header=next(i for i,line in enumerate(lines) if 'RECEIPTS · read 03:01' in line)
    paused=next(i for i,line in enumerate(lines) if line.strip().startswith('paused '))
    assert not lines[paused-1].strip() and not lines[header-1].strip()
    assert 'FLEET · workers as of 04:02' in text
    assert 'tokens / completed job' not in text
    assert not lines[header+1].strip(), 'owner 2026-09-22: a blank row under CONTRIBUTORS'
    assert 'served' in lines[header+7]


async def test_contributors_show_devices_outcomes_turns_and_tokens():
    lines=(await render(summary=SUMMARY)).splitlines()
    header=next(i for i,line in enumerate(lines) if 'RECEIPTS' in line)
    body=[line.strip() for line in lines[header+2:header+7]]
    s=SUMMARY
    assert body==[
        f"devices    {s['devices']:,} · {s['receipt_seats']:,} seats",
        f"accepted   {s['receipt_accepted']:,} of {s['receipt_attempts']:,}",
        f"rejected   {s['receipt_rejected']:,} · {s['receipt_pending']:,} pending",
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
    text=await render(summary=dict(SUMMARY,devices=None,receipt_attempts=None,input_tokens=None,
                                   wall_clock_ms=None))
    assert 'devices    unavailable' in text and 'tokens     unavailable' in text
    assert any(l.strip()==f"accepted   {SUMMARY['receipt_accepted']:,}" for l in text.splitlines())
    assert any(l.strip()==f"turns      {SUMMARY['turns']:,}" for l in text.splitlines())
    none=await render(summary=None)
    for label in ('devices','accepted','rejected','turns','tokens'):
        assert f'{label:<11}unavailable' in none


async def test_a_contributor_pair_too_wide_for_its_line_counts_its_second_value():
    text=await render(summary=dict(SUMMARY,receipt_rejected=99_999_999,receipt_pending=99_999_999))
    assert any(l.strip()=='rejected   99,999,999 · +1' for l in text.splitlines()), text


async def test_polish_model_missing_none_and_hostile_values_are_distinct():
    none=await render(dict(FLEET,models=[dict(model=None,effort=None,count=3)]))
    assert 'model      none reported' in none and '(advertised)' in none
    unread=await render(dict(FLEET,models=None))
    assert 'model      unavailable' in unread and 'none 3' not in unread
    hostile=await render(dict(FLEET,models=[dict(model='[/x]astra',effort='[$success]high',count=2)]))
    assert 'astra high 2' in hostile and '[/x]' not in hostile and '[$success]' not in hostile
    long=await render(dict(FLEET,models=[dict(model='x'*64,effort='high',count=99999)]))
    assert 'model      xxx' in long and '… 99,999' in long


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


async def test_tag_only_model_uses_empty_dash_without_effort():
    text = await render(dict(FLEET, models=[dict(model='[/x][$success]', effort='high', count=2)]))
    model_line = next(line.strip() for line in text.splitlines() if line.strip().startswith('model '))
    assert model_line == 'model      — 2'
    assert 'high' not in model_line and 'none' not in model_line
