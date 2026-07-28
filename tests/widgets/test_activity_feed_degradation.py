"""MEDI-37: ActivityFeed must never raise and must say when it is empty.

``update_data`` calls ``log.clear()`` and *then* writes the events.  Any
exception between those two points leaves the panel blank -- and because
``BakeryScreen`` catches it and only logs a warning, it stays blank on
every subsequent refresh for as long as the offending event sits in the
feed window, with nothing on screen explaining why.

Every field the feed formats is API-sourced: ``title``, ``description``
and ``linked_bakery_name`` carry player-chosen bakery names, ``timestamp``
and ``launcher`` come straight off the wire.  The markup-safety sweep
closed the ``MarkupError`` path; this file covers the rest -- missing and
malformed values -- and pins the empty state.

Assertions run against composited output
(``screen._compositor.render_strips()``), not the widget's content string:
a line that never reaches a pixel would satisfy a naive test while being
invisible.  ``RichLog`` also defers markup parsing, so every case is
pumped through an idle cycle -- a raise inside Textual's message pump
bypasses the screen's ``try/except`` and takes the app down (HIGH-7).
"""

from __future__ import annotations

import pytest
from textual.app import App, ComposeResult

from maxpane_dashboard.data.models import ActivityEvent
from maxpane_dashboard.widgets.activity_feed import ActivityFeed

#: Field values a real payload can carry where a string was promised.
HOSTILE_TEXT = ["[/x] Bakers", "[/]", "[not a tag] Guild", "[#00ff00 on]"]


class _Harness(App):
    """Mount ActivityFeed at a size where its RichLog actually composites."""

    def __init__(self, widget) -> None:
        super().__init__()
        self._widget = widget

    def compose(self) -> ComposeResult:
        yield self._widget


def _event(**overrides) -> ActivityEvent:
    """A well-formed event, with *overrides* applied.

    ``model_construct`` bypasses validation on purpose: the point is to
    reproduce what the widget sees when the payload does not match the
    model, which is exactly the case the widget must survive.
    """
    fields = dict(
        type="simple",
        title="joined the bakery",
        description="",
        launcher="0x" + "1" * 40,
        timestamp="1700000000",
        boost_type_name=None,
        boost_multiplier_bps=None,
        success=None,
        is_outgoing=None,
        linked_bakery_name=None,
    )
    fields.update(overrides)
    return ActivityEvent.model_construct(**fields)


def _composited(app) -> str:
    return "\n".join(
        "".join(seg.text for seg in strip)
        for strip in app.screen._compositor.render_strips()
    )


async def _render(*calls) -> tuple[str, App, ActivityFeed]:
    """Drive a mounted feed through *calls* successive polls."""
    widget = ActivityFeed()
    app = _Harness(widget)
    async with app.run_test(size=(120, 24)) as pilot:
        for events in calls:
            widget.update_data(events)
            await pilot.pause()
        return _composited(app), app, widget


# ---------------------------------------------------------------------------
# missing and malformed events
# ---------------------------------------------------------------------------


async def test_all_none_event_does_not_blank_the_feed() -> None:
    """An event with every field null renders a line, not an exception."""
    blank = _event(
        type=None, title=None, description=None, launcher=None, timestamp=None
    )
    good = _event(title="joined the bakery")

    rendered, app, _ = await _render([blank, good])

    assert app._exception is None, f"died in the pump: {app._exception!r}"
    assert "joined the bakery" in rendered, (
        "one unformattable event truncated the feed and hid the events after "
        f"it: {rendered!r}"
    )
    assert "ACTIVITY" in rendered


@pytest.mark.parametrize(
    "bad_timestamp", [None, "", "not-a-number", {}, 10**20, float("nan")], ids=repr
)
async def test_malformed_timestamp_degrades_to_a_placeholder(bad_timestamp) -> None:
    """A bad clock value must cost that line's time, not the whole panel."""
    rendered, app, _ = await _render(
        [_event(timestamp=bad_timestamp, title="still visible")]
    )

    assert app._exception is None, f"{bad_timestamp!r} died in the pump"
    assert "still visible" in rendered
    assert "??:??" in rendered, (
        f"expected the unknown-time placeholder for {bad_timestamp!r}: {rendered!r}"
    )


@pytest.mark.parametrize("bad_launcher", [None, 12345, b"0xabc", {}], ids=repr)
async def test_malformed_launcher_still_renders_the_line(bad_launcher) -> None:
    """``len()`` on a non-string launcher used to raise ``TypeError``."""
    rendered, app, _ = await _render(
        [_event(launcher=bad_launcher, title="still visible")]
    )

    assert app._exception is None, f"{bad_launcher!r} died in the pump"
    assert "still visible" in rendered


async def test_an_object_that_is_not_an_event_is_reported_not_fatal() -> None:
    """A payload shape change degrades to one explicit line."""
    rendered, app, _ = await _render([object(), _event(title="still visible")])

    assert app._exception is None
    assert "still visible" in rendered, (
        f"the junk entry truncated the feed: {rendered!r}"
    )
    assert "unreadable event" in rendered, (
        "an entry the feed cannot format must say so rather than vanish "
        f"silently: {rendered!r}"
    )


@pytest.mark.parametrize("hostile", HOSTILE_TEXT)
@pytest.mark.parametrize(
    "field", ["title", "description", "linked_bakery_name"]
)
async def test_hostile_markup_in_any_text_field(hostile, field) -> None:
    """Player-chosen text is escaped wherever it appears in the line."""
    overrides = {field: hostile, "type": "rug", "success": True}
    rendered, app, _ = await _render([_event(**overrides), _event(title="after")])

    assert app._exception is None, f"{field}={hostile!r} crashed the pump"
    assert "after" in rendered, (
        f"{field}={hostile!r} truncated the feed: {rendered!r}"
    )


# ---------------------------------------------------------------------------
# the empty state
# ---------------------------------------------------------------------------


async def test_empty_feed_states_that_it_is_empty() -> None:
    """No events is a fact the user should be able to read."""
    rendered, app, _ = await _render([])

    assert app._exception is None
    assert "No activity yet" in rendered


async def test_none_is_treated_as_empty() -> None:
    """A manager that returned nothing must not raise here."""
    rendered, app, _ = await _render(None)

    assert app._exception is None
    assert "No activity yet" in rendered


async def test_repeated_empty_polls_do_not_stack_placeholders() -> None:
    """The placeholder is rewritten, not appended once per poll.

    ``update_data`` used to ``log.write`` the placeholder without clearing,
    so an idle dashboard grew one more "No activity yet" line every poll
    interval until the panel was full of them.
    """
    rendered, app, widget = await _render([], [], [], [], [])

    assert app._exception is None
    assert rendered.count("No activity yet") == 1, (
        f"the placeholder accumulated once per poll: {rendered!r}"
    )


async def test_a_transient_empty_poll_does_not_wipe_a_populated_feed() -> None:
    """One empty response must not erase what the user was reading."""
    rendered, app, _ = await _render([_event(title="joined the bakery")], [])

    assert app._exception is None
    assert "joined the bakery" in rendered
    assert "No activity yet" not in rendered


async def test_a_feed_of_only_unformattable_events_is_not_silently_blank() -> None:
    """If nothing could be written, say so rather than show an empty box."""
    rendered, app, _ = await _render([object(), object()])

    assert app._exception is None
    assert "unreadable event" in rendered or "No activity yet" in rendered


# ---------------------------------------------------------------------------
# the happy path still works
# ---------------------------------------------------------------------------


async def test_normal_events_still_render() -> None:
    """The hardening did not blunt the ordinary case."""
    rendered, app, _ = await _render(
        [
            _event(title="joined the bakery"),
            _event(
                type="rug",
                title="Sugar Rush",
                description="stole 400 cookies from",
                linked_bakery_name="Crumb Cartel",
                success=True,
                is_outgoing=True,
            ),
        ]
    )

    assert app._exception is None
    assert "joined the bakery" in rendered
    assert "Sugar Rush" in rendered
    assert "Crumb Cartel" in rendered
    assert "unreadable event" not in rendered
