"""BOARD hero facts and each source's independent clock, composited."""
import pytest
from maxpane_dashboard.app import CSS_PATH
from maxpane_dashboard.data import surf_swarm as fold
from maxpane_dashboard.widgets.surf.swarm_board_hero import SurfSwarmBoardHero
from tests.surf_swarm_fixtures import swarm_capture_v3
from tests.widgets.surf_compositing import composite_lines

SUMMARY = fold.board_summary(swarm_capture_v3('contributors'), swarm_capture_v3('workers'))
async def render(summary=SUMMARY):
    return '\n'.join(await composite_lines(SurfSwarmBoardHero, (150,9), css_path=CSS_PATH,
        swarm_board_summary=summary, swarm_board_as_of_hhmm='03:01', swarm_workers_as_of_hhmm='04:02'))

async def test_six_titles_and_separate_source_clocks():
    text=await render()
    for title in ('SEATS','LIVE','PAUSED','CAPACITY','ACCEPT RATE','RECEIPTS','workers','03:01','04:02'):
        assert title in text
    assert str(SUMMARY['seats']) in text
    assert f"{SUMMARY['accepted']/SUMMARY['attempts']*100:.1f} %" in text

@pytest.mark.parametrize('contributors,workers', [(None,'workers'),('contributors',None),(None,None)])
async def test_sources_fail_independently(contributors,workers):
    summary=fold.board_summary(swarm_capture_v3(contributors) if contributors else None,
                               swarm_capture_v3(workers) if workers else None)
    text=await render(summary)
    assert 'unavailable' in text
    if contributors: assert f"{summary['accepted']/summary['attempts']*100:.1f} %" in text
    if workers: assert f"{summary['live']} workers" in text

async def test_zero_attempts_is_not_a_rate():
    assert 'no attempts' in await render(dict(SUMMARY,attempts=0,accepted=0))

@pytest.mark.parametrize("widget_name", ["SurfSwarmBoardHero", "SurfSwarmLeaderboard", "SurfSwarmFleet"])
async def test_invalid_source_clocks_are_explicit_and_never_painted(widget_name):
    import maxpane_dashboard.widgets.surf as widgets
    text = "\n".join(await composite_lines(getattr(widgets, widget_name), (150, 20), css_path=CSS_PATH,
        swarm_board_summary=SUMMARY,
        swarm_board_rows=fold.board_rows(swarm_capture_v3("contributors"), swarm_capture_v3("workers")),
        swarm_fleet=fold.fleet(swarm_capture_v3("workers")),
        swarm_board_as_of_hhmm="[/x]PWNED", swarm_workers_as_of_hhmm="99:99"))
    assert "as of unavailable" in text
    assert "PWNED" not in text and "99:99" not in text and "[/x]" not in text
