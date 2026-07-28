"""MEDI-23: decoding a random event must not discard a bakery's whole feed.

``ActivityEvent.launcher`` was typed as a required ``str``.  Live random
events -- ``isRandomEvent: true``, the "Rush Order" family -- are fired by
the game rather than by a player and carry ``launcher: null``, so pydantic
rejected them.  ``GameDataClient.get_activity_feed`` builds its result with
a list comprehension, so that one rejection raised out of the whole call;
``get_activity_feed_global`` gathers with ``return_exceptions=True`` and
merely logged it, silently omitting *every* event of that bakery.  The
reviewer measured 80 of 100 events returned, with bakery 1568 gone.

The fixtures below are verbatim ``leaderboard.getActivityFeed`` element
shapes -- the null-launcher one is what the live API returned for the
dropped bakery.  Decoding is pinned against the raw payload rather than
against a hand-built model, because the bug lived entirely in the
payload -> model step: every widget-level test constructed
``ActivityEvent`` directly and so never saw a null launcher.

(The review files this as a "decode error".  It is a JSON/pydantic decode,
not an ABI one, so there is no calldata to pin -- the raw-payload fixture
below is the equivalent anchor.)
"""

from __future__ import annotations

from typing import Any

import pytest

from maxpane_dashboard.data.models import ActivityEvent
from maxpane_dashboard.widgets.activity_feed import _event_to_markup

# --- Verbatim getActivityFeed elements -------------------------------------

#: An ordinary player-triggered join.  launcher is a real address.
PLAYER_JOIN: dict[str, Any] = {
    "type": "simple",
    "title": "joined the bakery",
    "description": "",
    "launcher": "0xace4fd0f8ff152d0ebbf01d6b6263f7e9745deb6",
    "timestamp": "1774585632",
    "boostTypeName": None,
    "boostMultiplierBps": None,
    "boostDuration": None,
    "isShield": None,
    "isOutgoing": True,
    "success": True,
    "linkedBakeryId": None,
    "linkedBakeryName": None,
}

#: A game-generated random event.  ``launcher`` is null -- this is the
#: element that used to abort the whole per-bakery decode.
RANDOM_EVENT_RUSH_ORDER: dict[str, Any] = {
    "type": "rug",
    "title": "Rush Order",
    "description": "production surged",
    "launcher": None,
    "timestamp": "1774585999",
    "boostTypeName": "Rush Order",
    "boostMultiplierBps": 13000,
    "boostDuration": "900",
    "isShield": False,
    "isOutgoing": False,
    "success": True,
    "linkedBakeryId": None,
    "linkedBakeryName": None,
}

#: A player attack, to prove ordinary events still decode unchanged.
PLAYER_ATTACK: dict[str, Any] = {
    "type": "rug",
    "title": "Health Inspection",
    "description": "rugged",
    "launcher": "0xbb00000000000000000000000000000000000001",
    "timestamp": "1774586100",
    "boostTypeName": "Health Inspection",
    "boostMultiplierBps": 5000,
    "boostDuration": "600",
    "isShield": False,
    "isOutgoing": True,
    "success": False,
    "linkedBakeryId": 1568,
    "linkedBakeryName": "Rival Bakery",
}


def test_null_launcher_decodes_instead_of_raising() -> None:
    event = ActivityEvent.from_api(RANDOM_EVENT_RUSH_ORDER)
    assert event.launcher is None
    assert event.type == "rug"
    assert event.title == "Rush Order"
    assert event.boost_multiplier_bps == 13000


def test_one_random_event_does_not_discard_the_rest_of_the_feed() -> None:
    """The exact failure: a list comprehension over a mixed feed."""
    raw = [PLAYER_JOIN, RANDOM_EVENT_RUSH_ORDER, PLAYER_ATTACK]
    events = [ActivityEvent.from_api(e) for e in raw]

    assert len(events) == 3, "a null launcher still aborts the per-bakery feed"
    assert [e.launcher for e in events] == [
        PLAYER_JOIN["launcher"],
        None,
        PLAYER_ATTACK["launcher"],
    ]


def test_ordinary_events_are_unchanged() -> None:
    event = ActivityEvent.from_api(PLAYER_ATTACK)
    assert event.launcher == "0xbb00000000000000000000000000000000000001"
    assert event.title == "Health Inspection"
    assert event.description == "rugged"
    assert event.linked_bakery_id == 1568
    assert event.success is False


@pytest.mark.parametrize("field", ["title", "description"])
def test_null_title_and_description_are_tolerated(field: str) -> None:
    """Defensive half of the fix: neither field is load-bearing."""
    payload = dict(PLAYER_JOIN)
    payload[field] = None
    event = ActivityEvent.from_api(payload)
    assert getattr(event, field) is None


@pytest.mark.parametrize(
    "payload", [PLAYER_JOIN, RANDOM_EVENT_RUSH_ORDER, PLAYER_ATTACK]
)
def test_every_decoded_event_renders(payload: dict[str, Any]) -> None:
    """Accepting null must not just move the crash into the widget."""
    line = _event_to_markup(ActivityEvent.from_api(payload))
    assert isinstance(line, str) and line.strip()
    assert "unreadable event" not in line
