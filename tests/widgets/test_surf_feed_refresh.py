"""Reader age/loading publications leave unchanged announcement rows mounted."""
from copy import deepcopy

from maxpane_dashboard.widgets.surf.feed import SurfFeed, SurfFeedToggle
from tests.widgets.test_surf_widgets_b import _Harness, _THREADED, _screen_text


async def test_age_only_refresh_keeps_rows_focus_and_scroll_and_updates_title():
    feed = SurfFeed()
    app = _Harness(feed)
    async with app.run_test(size=(100, 15)) as pilot:
        feed.update_data(feed_nonce=14, feed_items=deepcopy(_THREADED), feed_last_post_age_s=60)
        await pilot.pause()
        toggle = next(iter(feed.query(SurfFeedToggle)))
        toggle.focus()
        await pilot.pause()
        body = feed.query_one('#surf-feed-body')
        rows = tuple(body.children)
        offset = body.scroll_offset
        feed.update_data(feed_nonce=15, feed_items=deepcopy(_THREADED), feed_last_post_age_s=120)
        await pilot.pause()
        assert tuple(body.children) == rows
        assert app.screen.focused is toggle
        assert body.scroll_offset == offset
        assert '#15' in _screen_text(app) and '2m' in _screen_text(app)


async def test_changed_items_and_signal_targets_still_refresh_announcements():
    feed = SurfFeed()
    app = _Harness(feed)
    items = deepcopy(_THREADED)
    async with app.run_test(size=(100, 24)) as pilot:
        feed.update_data(feed_items=items)
        await pilot.pause()
        body = feed.query_one('#surf-feed-body')
        rows = tuple(body.children)
        # Reusing a mutable input must not mask a real source update.
        items[0]['text'] = 'Changed announcement content'
        feed.update_data(feed_items=items)
        await pilot.pause()
        assert tuple(body.children) != rows
        assert 'Changed announcement content' in _screen_text(app)
        rows = tuple(body.children)
        feed.update_data(feed_items=items, feed_signal_tx_hashes=['0xq2'])
        await pilot.pause()
        assert tuple(body.children) != rows
        assert feed.query('.surf-feed-signal')
