"""Session launch notifications use captured events, never network reads."""
from types import SimpleNamespace
from uuid import UUID

import pytest
from rich.text import Text

from maxpane_dashboard.launch_notifications import LaunchNotifications, launch_toast_message
from tests.surf_launch_fixtures import launch_event


def fired(number=737, **overrides):
    return dict(launch_event(number), ts=1001., **overrides)


def snapshot(events=(), state="fired"):
    return dict(sig_swarm_state=state, swarm_launch_fired=list(events), swarm_launch_read_ts=1000.)


def tracker():
    clock = SimpleNamespace(now=1000.)
    return LaunchNotifications(clock=lambda: clock.now), clock


def test_first_ready_snapshot_is_silent_after_loading_or_failure_and_on_restart():
    watch, clock = tracker()
    for data in ({}, snapshot(state=None), snapshot(state="dead")):
        assert watch.consume(data) == []
    old = dict(fired(), ts=999.)
    assert watch.consume(snapshot([old])) == []
    clock.now = 1002.
    new = fired(747)
    assert watch.consume(snapshot([old, new])) == [new]
    restarted = LaunchNotifications(clock=lambda: clock.now)
    assert restarted.consume(snapshot([old, new])) == []


def test_retained_fired_signals_do_not_arm_before_first_session_read():
    watch, clock = tracker()
    old = dict(fired(), ts=999.)
    for read_ts in (None, 999.):
        assert watch.consume(dict(snapshot([old]), swarm_launch_read_ts=read_ts)) == []
    clock.now = 1010.
    first_live_batch = snapshot([old, dict(fired(747), ts=1009.)])
    first_live_batch['swarm_launch_read_ts'] = 1009.
    assert watch.consume(first_live_batch) == []
    clock.now = 1012.
    new = dict(fired(734), ts=1011.)
    assert watch.consume(dict(snapshot([new]), swarm_launch_read_ts=1011.)) == [new]


def test_multiple_new_tokens_emit_once_across_empty_windows_failures_and_reordering():
    watch, clock = tracker()
    assert watch.consume(snapshot(state="ok")) == []
    clock.now = 1002.
    a, b = fired(), fired(747)
    assert watch.consume(snapshot([a, b])) == [a, b]
    for data in (snapshot(), {}, snapshot(state=None), snapshot([b, a])):
        assert watch.consume(data) == []
    # Previously unseen persisted history delivered after an empty baseline is silent.
    assert watch.consume(snapshot([dict(fired(734), ts=999.)])) == []


def test_enrichment_and_token_aliases_do_not_notify_again_but_other_chains_do():
    watch, clock = tracker()
    watch.consume(snapshot(state="ok"))
    clock.now = 1002.
    tokenless = dict(fired(), token_address=None, ticker=None)
    assert watch.consume(snapshot([tokenless])) == [tokenless]
    enriched = fired()
    assert watch.consume(snapshot([enriched])) == []
    alias = dict(enriched, launch_id=str(UUID(int=99)), token_address=enriched['token_address'].upper().replace('0X', '0x'))
    assert watch.consume(snapshot([alias])) == []
    base = dict(alias, launch_id=str(UUID(int=100)), chain_id=8453)
    assert watch.consume(snapshot([base])) == [base]


@pytest.mark.parametrize("alias_first", [True, False])
def test_same_snapshot_enrichment_teaches_aliases_before_any_notification(alias_first):
    watch, clock = tracker()
    watch.consume(snapshot(state="ok"))
    clock.now = 1002.
    tokenless = dict(fired(), token_address=None)
    assert watch.consume(snapshot([tokenless])) == [tokenless]
    enriched = fired()
    alias = dict(enriched, launch_id=str(UUID(int=99)), number=748)
    events = [alias, enriched] if alias_first else [enriched, alias]
    assert watch.consume(snapshot(events)) == []


@pytest.mark.parametrize("changes", [
    {"chain_id": 11155111}, {"chain_id": 999}, {"chain_id": True},
    {"launch_id": "bad"}, {"number": None}, {"number": True},
    {"ts": float("nan")}, {"ts": float("inf")}, {"ts": True},
])
def test_bad_events_and_testnets_never_notify(changes):
    watch, clock = tracker()
    watch.consume(snapshot(state="ok"))
    clock.now = 1002.
    assert watch.consume(snapshot([None, {}, dict(fired(), **changes)])) == []


def test_future_timestamp_does_not_consume_identity():
    watch, clock = tracker()
    watch.consume(snapshot(state="ok"))
    event = dict(fired(), ts=1010.)
    assert watch.consume(snapshot([event])) == []
    clock.now = 1011.
    assert watch.consume(snapshot([event])) == [event]


def test_toast_text_escapes_ticker_flattens_controls_and_keeps_network_and_number():
    event = dict(fired(), ticker="[/red]\nX\x1b\u202e")
    text = Text.from_markup(launch_toast_message(event))
    assert text.plain == "$[/red] X · MAINNET\nLaunch #737"
    assert not text.spans
    assert Text.from_markup(launch_toast_message(dict(event, ticker=None))).plain == "Unknown token · MAINNET\nLaunch #737"
