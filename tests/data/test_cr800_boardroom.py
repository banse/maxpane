from maxpane_dashboard.data import surfboard
from maxpane_dashboard.analytics.surf_signals import SIGNAL_NAMES


def test_confirmed_zero_jobs_needs_no_node_details_to_show_zero_working():
    data = dict(surf_work=dict(state='ok', summary=dict(jobs=0, workflows=0)))
    card = next(r for r in surfboard.cards(data, {}, now=1000) if r['key'] == 'work')
    assert card['secondary'] == '0 working'
    assert card['work_summary']['workflows'] == 0


def test_signal_count_is_fired_detectors_not_feed_posts_or_watches():
    data = {f'sig_{name}_state': 'ok' for name in SIGNAL_NAMES}
    data[f'sig_{SIGNAL_NAMES[0]}_state'] = 'watch'
    def count():
        return next(r['numerator'] for r in surfboard.cards(data, {}, now=1000) if r['key']=='announce')
    assert count() == 0
    data[f'sig_{SIGNAL_NAMES[1]}_state'] = 'fired'
    data[f'sig_{SIGNAL_NAMES[2]}_state'] = 'fired'
    assert count() == 2
    data[f'sig_{SIGNAL_NAMES[-1]}_state'] = None
    assert count() is None
