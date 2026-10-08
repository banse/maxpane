import pytest
from maxpane_dashboard.analytics import surfboard as hub

@pytest.mark.parametrize('a,b,result',[(1,4,.25),(0,1,0),(0,0,None),(2,1,None),(True,1,None),(-1,3,None),(float('inf'),4,None)])
def test_ratio_rejects_invalid_and_preserves_real_zero(a,b,result):
    assert hub.ratio(a,b)==result

def test_command_preserves_arguments_and_refuses_unbounded_input():
    assert hub.parse_command('GrEp Case Sensitive')==('grep','Case Sensitive')
    assert hub.parse_command('#420')==('seat','#420')
    assert hub.parse_command('x'*513) is None

def test_sparkline_sums_only_complete_provider_day():
    assert hub.hourly_points(list(range(24)))==[3,12,21,30,39,48,57,66]
    assert hub.hourly_points([0]*23) is None
    assert hub.hourly_points([True]*24) is None
