"""Headless Textual tests for the curator dashboard screen -- THE LIST (WP6).

A fake manager returns the frozen ``CURATOR_KEYS`` dict (no network), the
screen is pushed via ``App.run_test()``, and every claim about what a reader
sees is asserted against **composited output**
(``app.screen._compositor.render_strips()``), never a widget's content string.

Zero network, zero wall clock
-----------------------------

Every time-derived string -- the grace countdown, the hour clock, the whale's
age, ``lived 1 d 4 h`` -- arrives pre-computed in the payload, because
``analytics/curator_signals.build_signals`` takes ``now_ts`` and the screen
takes nothing.  That is what lets the 2026-08-17T00:03:22Z capture replay
forever, and ``test_the_screen_reads_no_clock_of_its_own`` pins it.

Where the payloads come from
----------------------------

``tests/fixtures/curator/screen/{grace,judged,settled}_payload.json``.  All
three are the output of the **real producer** -- WP5's log decoders and WP3's
``build_signals`` -- run offline over the committed live capture
``tests/fixtures/curator/captures/live/20260817T000322Z_grace-late.json``
(2 930 ``Deposited`` + 2 291 ``FirstDeposit`` rows and the 21-view state batch,
all fetched in the same second, so the counters and the fold reconcile).
Nothing here is a plausible-looking number typed by hand: a payload the manager
can never emit would calibrate the width sweep against fiction.  The exact
transformation is recorded in that directory's ``README.md``.

The GRACE payload is real end to end.  JUDGED and SETTLED are **synthetic**:
capture B (a post-grace judged hour) and capture C (the settlement transition)
had not landed when this was written, so both are the same real deposits
replayed one grace period later -- every event's ``hour`` and ``ts`` shifted by
exactly ``gracePeriod`` -- with the fast-tier reads a post-grace contract would
answer.  Each loader carries the tree-wide re-point marker.

The one manual choice, and why
------------------------------

``_WALLET`` is the **top-of-list** wallet from the capture, not a middle-ranked
one.  The YOU row is the rail's widest and its width is data-dependent (a
six-figure credit prints two columns wider than a four-figure one), so the
full-layout sweep is calibrated against the widest *real* wallet the capture
contains, the way CLAUDE.md requires for the surf market panel's IMD/FP peg.
A narrower wallet would pin a number the rail exceeds the day someone rich
sets ``MAXPANE_WALLET``, and the row it would amputate is the only actionable
number the rail carries.

The binding panel
-----------------

At ``CURATOR_FULL_LAYOUT_COLUMNS - 1`` the last panel still asking for a column
is ``CuratorSignals``, the seven-row rail
(``test_the_binding_panel_is_the_signal_rail``).  That fact is pinned by
``_panels_asking_for_width`` rather than by prose: on the surf screen the same
claim changed hands three times and was restated in a paragraph each time with
no test that could contradict it.
"""

from __future__ import annotations

import asyncio
import inspect
import json
from pathlib import Path

from textual.app import App

from maxpane_dashboard import __version__
from maxpane_dashboard.analytics.curator_signals import MANAGER_OWNED_KEYS
from maxpane_dashboard.data.curator_manager import SOURCES
from maxpane_dashboard.data.curator_models import CURATOR_KEYS, PHASES
from maxpane_dashboard.screens.curator import (
    CLOSEST_ID,
    CLUSTERS_ID,
    CURATOR_FULL_LAYOUT_COLUMNS,
    INITIAL_TITLE,
    MANAGER_FAILURE_SECONDS,
    META_KEYS,
    SCREEN_SUPPLIED,
    VIEW_CLOSEST,
    VIEW_CLUSTERS,
    WIDGET_SIGNATURES,
    CuratorScreen,
    _default_view,
    _fmt_degraded,
    _fmt_int,
    _num,
    _phase_word,
    _title_line,
)
from maxpane_dashboard.screens.refresh_guard import RefreshGuard
from maxpane_dashboard.widgets.curator import (
    CuratorActivity,
    CuratorClosestCalls,
    CuratorClusters,
    CuratorHero,
    CuratorLeaderboard,
    CuratorSignals,
    CuratorSparklines,
)
# Imported, never re-spelled: these are WP4's rendered interface.  A literal
# retyped here would certify a string nobody renders.
from maxpane_dashboard.widgets.curator import (
    ACTIVITY_TITLE,
    CLOSEST_CALLS_TITLE,
    CLUSTERS_TITLE,
    LEADERBOARD_TITLE,
    NO_JUDGED_HOURS,
    NO_WALLET,
    SIGNAL_LABELS,
    SIGNALS_TITLE,
)
from maxpane_dashboard.widgets.status_bar import StatusBar

_ROOT = Path(__file__).resolve().parents[2]
_TCSS = _ROOT / "maxpane_dashboard" / "themes" / "minimal.tcss"
_FIXTURES = _ROOT / "tests" / "fixtures" / "curator" / "screen"

_PANELS = (
    CuratorHero,
    CuratorLeaderboard,
    CuratorSparklines,
    CuratorSignals,
    CuratorActivity,
    CuratorClosestCalls,
    CuratorClusters,
)

#: The window the width sweep scans.  Deliberately independent of
#: ``CURATOR_FULL_LAYOUT_COLUMNS`` -- a sweep that started at the pin would
#: agree with it by construction.
_SWEEP_LO, _SWEEP_HI = 118, 160


# -- payloads ------------------------------------------------------------


def _load(name: str) -> dict:
    with open(_FIXTURES / f"{name}_payload.json") as handle:
        return json.load(handle)


_GRACE = _load("grace")
# SYNTHETIC — re-point at tests/fixtures/curator/captures/live/<bundle>
_JUDGED = _load("judged")
# SYNTHETIC — re-point at tests/fixtures/curator/captures/live/<bundle>
_SETTLED = _load("settled")

#: The reader's own wallet: rank 1 in the capture (see the module docstring).
_WALLET = _GRACE["leaderboard_rows"][0]["address"]


def _frozen_payload(**overrides) -> dict:
    """The GRACE capture, as exactly ``CURATOR_KEYS`` and nothing else."""
    payload = {key: _GRACE.get(key) for key in CURATOR_KEYS}
    payload.update(overrides)
    return payload


def _grace_payload(**overrides) -> dict:
    return _frozen_payload(**overrides)


def _judged_payload(**overrides) -> dict:
    # SYNTHETIC — re-point at tests/fixtures/curator/captures/live/<bundle>
    payload = {key: _JUDGED.get(key) for key in CURATOR_KEYS}
    payload.update(overrides)
    return payload


def _settled_payload(**overrides) -> dict:
    # SYNTHETIC — re-point at tests/fixtures/curator/captures/live/<bundle>
    payload = {key: _SETTLED.get(key) for key in CURATOR_KEYS}
    payload.update(overrides)
    return payload


def _payload_for(phase: str, **overrides) -> dict:
    return {
        "grace": _grace_payload,
        "judged": _judged_payload,
        "settled": _settled_payload,
    }[phase](**overrides)


def _all_none_payload() -> dict:
    """Every contract key present, every value ``None``.

    **This is the specified outage path**, not an exception:
    ``CuratorManager.fetch_and_compute`` never raises and returns the full
    contract with every value ``None`` when all three source groups are down
    (WP5's ``test_no_exception_escapes_when_every_call_raises``).  The
    ``raises=True`` double below is belt and braces for a mis-wired manager and
    must never be mistaken for the documented degradation contract.
    """
    return dict.fromkeys(CURATOR_KEYS)


# -- harness -------------------------------------------------------------


class _FakeManager:
    """Returns a frozen payload.  Never opens a socket, never reads a clock."""

    def __init__(self, payload: dict | None = None, raises: bool = False) -> None:
        self._payload = payload if payload is not None else _frozen_payload()
        self._raises = raises
        #: Zero unless a test says otherwise: the StatusBar renders
        #: ``N errors``, and a harness that always reported some would make
        #: every "no fault language on screen" assertion below vacuous.
        self._error_count = 0
        self.calls = 0

    async def fetch_and_compute(self) -> dict:
        self.calls += 1
        if self._raises:
            raise RuntimeError("all three source groups are down")
        return dict(self._payload)

    async def close(self) -> None:
        pass


class _Harness(App):
    """Push a single CuratorScreen for testing (no app stylesheet)."""

    def __init__(self, screen) -> None:
        super().__init__()
        self._screen = screen

    def on_mount(self) -> None:
        self.push_screen(self._screen)


class _ThemedHarness(_Harness):
    """Same, but with the real ``minimal.tcss`` loaded.

    Valid before WP7 adds a curator block: loading the stylesheet without
    curator rules leaves ``CuratorScreen.DEFAULT_CSS`` in charge, and keeps
    passing after WP7 restates it.
    """

    CSS_PATH = _TCSS


def _screen(payload=None, *, raises: bool = False, wallet=_WALLET):
    manager = _FakeManager(payload=payload, raises=raises)
    return CuratorScreen(manager, poll_interval=30, name="curator", wallet=wallet)


def _screen_text(app) -> str:
    """Composited screen text -- what a user would actually see."""
    strips = app.screen._compositor.render_strips()
    return "\n".join("".join(seg.text for seg in strip) for strip in strips)


def _region_text(app, widget, clip) -> str:
    """The composited text inside *widget*'s rectangle, clipped to *clip*.

    Clipped rather than indexed: at a narrow width a panel's region can start
    below the last composited row, and that is the state being measured.
    """
    lines = _screen_text(app).split("\n")
    region = widget.region.intersection(clip.region)
    return "\n".join(
        lines[y][region.x : region.x + region.width]
        for y in range(region.y, min(region.y + region.height, len(lines)))
    )


async def _render(payload=None, *, width: int = CURATOR_FULL_LAYOUT_COLUMNS,
                  view: str | None = None, wallet=_WALLET) -> str:
    """Boot the real screen at *width*, refresh once, return composited text."""
    screen = _screen(payload, wallet=wallet)
    app = _ThemedHarness(screen)
    async with app.run_test(size=(width, 48)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()
        if view is not None and screen._active_view != view:
            screen.action_toggle_view()
            await pilot.pause()
        return _screen_text(app)


async def _widen_markers(width: int, payload=None, view: str | None = None) -> int:
    """Composited ``‹ widen`` count at *width*, whole screen, cold boot."""
    return (await _render(payload, width=width, view=view)).count("‹ widen")


async def _panels_asking_for_width(width: int, payload=None,
                                   view: str | None = None) -> set[str]:
    """Which panels composite a ``‹ widen`` at *width*, by class name.

    A count alone cannot say *whose* marker is the last one standing, and that
    is the claim ``CURATOR_FULL_LAYOUT_COLUMNS`` is written around.
    """
    screen = _screen(payload)
    app = _ThemedHarness(screen)
    async with app.run_test(size=(width, 48)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()
        if view is not None and screen._active_view != view:
            screen.action_toggle_view()
            await pilot.pause()
        marked = {
            cls.__name__
            for cls in _PANELS
            if "‹ widen" in _region_text(app, screen.query_one(cls), screen)
        }
        # No panel outside the tuple above may hide a marker from this helper.
        assert len(marked) == _screen_text(app).count("‹ widen"), marked
        return marked


async def _first_clean_width(payload=None, view: str | None = None) -> int | None:
    """The narrowest width in the sweep window with no marker anywhere.

    Resizes one running app rather than booting one per column: the panels all
    implement ``on_resize`` and re-pick their tier, and
    ``test_a_resize_sweep_and_a_cold_boot_agree`` pins the two methods against
    each other at the boundary so this shortcut cannot drift.
    """
    screen = _screen(payload)
    app = _ThemedHarness(screen)
    async with app.run_test(size=(_SWEEP_LO, 48)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()
        if view is not None and screen._active_view != view:
            screen.action_toggle_view()
            await pilot.pause()
        for width in range(_SWEEP_LO, _SWEEP_HI + 1):
            await pilot.resize_terminal(width, 48)
            await pilot.pause()
            if _screen_text(app).count("‹ widen") == 0:
                return width
    return None


# =======================================================================
# WP6.1 -- skeleton: compose, bindings, the dispatch contract
# =======================================================================


def test_bindings_are_refresh_and_the_view_toggle():
    assert {binding.key for binding in CuratorScreen.BINDINGS} == {"r", "c"}


def test_the_worker_name_is_the_screens_own():
    assert CuratorScreen.REFRESH_WORKER_NAME == "curator-refresh"


def test_the_initial_title_names_the_subject_before_the_first_payload():
    assert INITIAL_TITLE == "THE LIST · WhitelistCurator · Ethereum Mainnet"


async def test_screen_mounts_all_seven_widgets():
    screen = _screen()
    app = _ThemedHarness(screen)
    async with app.run_test(size=(CURATOR_FULL_LAYOUT_COLUMNS, 48)) as pilot:
        await pilot.pause()
        assert len(screen.query_one("#hero-row").children) == 1
        assert len(screen.query_one("#middle-row").children) == 2
        assert len(screen.query_one("#curator-right-rail").children) == 2
        bottom = screen.query_one("#bottom-row").children
        assert len(bottom) == 3
        # Exactly one of the swap pair is displayed.
        assert [child.display for child in bottom].count(True) == 2
        for cls in _PANELS:
            assert screen.query_one(cls) is not None
        # The two ids WP7's stylesheet places the swap pair by.
        assert screen.query_one(f"#{CLOSEST_ID}") is screen.query_one(
            CuratorClosestCalls
        )
        assert screen.query_one(f"#{CLUSTERS_ID}") is screen.query_one(CuratorClusters)


def test_curator_keys_covers_the_local_signature_map():
    """Dispatched ⊆ the contract, and the contract ⊆ dispatched + meta.

    The tripwire for WP0<->WP5<->WP6 drift in both directions: a kwarg here
    that left ``CURATOR_KEYS``, and a key added to ``CURATOR_KEYS`` that no
    widget receives, both fail loudly.
    """
    dispatched = {key for keys in WIDGET_SIGNATURES.values() for key in keys}
    stray = dispatched - set(CURATOR_KEYS) - SCREEN_SUPPLIED
    assert not stray, f"dispatched kwargs that are not contract keys: {sorted(stray)}"
    orphans = set(CURATOR_KEYS) - dispatched - set(META_KEYS)
    assert not orphans, f"contract keys reach no widget: {sorted(orphans)}"


def test_the_meta_keys_are_exactly_the_ones_the_manager_owns():
    """The screen renders these three itself; no widget takes them."""
    assert set(META_KEYS) == set(MANAGER_OWNED_KEYS)


def test_the_dispatch_map_matches_the_widgets_own_signatures():
    """Hand-typed map vs. the seven ``update_data`` signatures.

    The map is hand-typed on purpose (CLAUDE.md's redundancy rule); this is the
    agreement test that makes the redundancy safe.  Deriving the map from
    ``inspect.signature`` would make this compare a constant with itself.
    """
    for cls in _PANELS:
        params = inspect.signature(cls.update_data).parameters
        accepted = {
            name
            for name, param in params.items()
            if name != "self" and param.kind is param.POSITIONAL_OR_KEYWORD
        }
        assert set(WIDGET_SIGNATURES[cls.__name__]) == accepted, cls.__name__


def test_the_screen_reads_no_clock_of_its_own():
    """Every time-derived string arrives pre-computed in the payload."""
    source = (_ROOT / "maxpane_dashboard" / "screens" / "curator.py").read_text()
    for forbidden in ("time.time()", "datetime.now(", "time.localtime(",
                      "time.monotonic()"):
        assert forbidden not in source, forbidden


# =======================================================================
# WP6.2 -- the title line and the format helpers (pure)
# =======================================================================


def test_the_title_names_the_phase_in_words():
    assert _title_line(_judged_payload()).startswith(
        "THE LIST · hour 28 · JUDGED · as of 20:15"
    )


def test_an_unknown_phase_says_so_rather_than_guessing():
    """``phase=None`` is a failed ``isSettled()`` read.  ``GRACE`` would be a
    guess about whether the game is still alive."""
    assert "phase —" in _title_line(_frozen_payload(phase=None))


def test_all_none_shows_emdashes_never_zeros():
    line = _title_line(_all_none_payload())
    assert "hour —" in line and "phase —" in line
    assert "0.00" not in line and "hour 0" not in line


def test_degraded_groups_ride_the_house_warning_glyph():
    line = _title_line(_frozen_payload(degraded=sorted(SOURCES)))
    assert "⚠ logs, state, wallet" in line


def test_the_settled_title_carries_the_observation_time_not_a_staleness_alarm():
    """Under an outage after settlement the freshness marker moves and the
    phase word does not (PRD §3).  The title must make that legible without
    reading as a fault."""
    line = _title_line(_settled_payload(degraded=["state", "logs"]))
    assert "SETTLED" in line and "⚠" in line and "as of" in line
    for wrong in ("ERROR", "BROKEN", "no data"):
        assert wrong not in line


def test_the_version_tail_is_last_because_it_is_the_first_thing_lost():
    """``#title-bar`` wraps out of existence rather than ellipsising, so the
    order of this line is its only priority mechanism -- and the version is the
    one field the StatusBar already renders three rows down."""
    line = _title_line(_frozen_payload(degraded=sorted(SOURCES)))
    assert line.endswith(f" · v{__version__}")
    assert line.index("⚠") < line.index(f"v{__version__}")


def test_the_format_helpers_never_turn_a_failed_read_into_a_zero():
    assert _fmt_int(None) == "—" and _fmt_int(2291) == "2,291"
    assert _fmt_int("nonsense") == "—" and _fmt_int(True) == "—"
    assert _fmt_degraded(None) == "" and _fmt_degraded([]) == ""
    assert _fmt_degraded(["logs"]) == " · ⚠ logs"
    assert _phase_word(None) == "phase —" and _phase_word("grace") == "GRACE"
    assert _phase_word("nonsense") == "phase —"
    # _num is the one helper that *may* default, because StatusBar does
    # arithmetic on its arguments and cannot take None.
    assert _num(None) == 0.0 and _num("nonsense", 7.0) == 7.0 and _num(3) == 3.0


def test_every_phase_word_in_the_frozen_vocabulary_renders():
    for phase in PHASES:
        assert _phase_word(phase) == phase.upper()


# =======================================================================
# WP6.3 -- _do_refresh: dispatch, all-None, manager failure
# =======================================================================


def _record_dispatches(screen) -> dict[str, dict]:
    """Wrap every widget's ``update_data`` and record the kwargs it got."""
    seen: dict[str, dict] = {}

    def wrap(cls):
        widget = screen.query_one(cls)
        original = widget.update_data

        def recorder(**kwargs):
            seen[cls.__name__] = kwargs
            return original(**kwargs)

        widget.update_data = recorder

    for cls in _PANELS:
        wrap(cls)
    return seen


async def test_every_widget_receives_exactly_its_signature():
    """``set(kwargs) == set(signature)``: an extra and a missing both fail."""
    screen = _screen(_grace_payload())
    app = _ThemedHarness(screen)
    async with app.run_test(size=(CURATOR_FULL_LAYOUT_COLUMNS, 48)) as pilot:
        await pilot.pause()
        seen = _record_dispatches(screen)
        await screen._do_refresh()
        await pilot.pause()

    assert set(seen) == {cls.__name__ for cls in _PANELS}
    for name, kwargs in seen.items():
        assert set(kwargs) == set(WIDGET_SIGNATURES[name]), name


async def test_no_contract_key_reaches_no_widget():
    """Totality, measured on a live dispatch rather than on the map alone."""
    screen = _screen(_grace_payload())
    app = _ThemedHarness(screen)
    async with app.run_test(size=(CURATOR_FULL_LAYOUT_COLUMNS, 48)) as pilot:
        await pilot.pause()
        seen = _record_dispatches(screen)
        await screen._do_refresh()
        await pilot.pause()

    delivered = {key for kwargs in seen.values() for key in kwargs}
    orphans = set(CURATOR_KEYS) - delivered - set(META_KEYS)
    assert not orphans, f"contract keys reach no widget: {sorted(orphans)}"


async def test_the_screen_supplied_wallet_reaches_the_leaderboard():
    """``you_address`` is the only kwarg on this screen the manager does not
    produce; the screen passes the configured wallet straight through."""
    screen = _screen(_grace_payload())
    app = _ThemedHarness(screen)
    async with app.run_test(size=(CURATOR_FULL_LAYOUT_COLUMNS, 48)) as pilot:
        await pilot.pause()
        seen = _record_dispatches(screen)
        await screen._do_refresh()
        await pilot.pause()
    assert seen["CuratorLeaderboard"]["you_address"] == _WALLET


async def test_an_all_none_payload_renders_unavailable_not_zeros():
    """The specified outage path.  Nothing invents a measurement."""
    text = await _render(_all_none_payload())
    assert "0.00 ETH" not in text
    assert "0 wallets" not in text
    assert "hour 0" not in text
    assert "phase —" in text
    # The panels are present and say so, rather than being blank.
    for title in (LEADERBOARD_TITLE, SIGNALS_TITLE, ACTIVITY_TITLE):
        assert title in text
    # No wallet configured is stated, never rendered as a wallet scoring zero.
    assert NO_WALLET in text


async def test_a_raising_manager_touches_only_the_status_bar():
    """A mis-wired manager, NOT the documented outage path (see
    ``_all_none_payload``).  The previous frame must stay on screen."""
    screen = _screen(_grace_payload())
    app = _ThemedHarness(screen)
    async with app.run_test(size=(CURATOR_FULL_LAYOUT_COLUMNS, 48)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()
        before = _screen_text(app)
        assert "THE LIST · hour 4 · GRACE" in before

        screen._data_manager._raises = True
        await screen._do_refresh()
        await pilot.pause()
        after = _screen_text(app)

    assert "THE LIST · hour 4 · GRACE" in after, "the previous frame was lost"
    assert f"updated {MANAGER_FAILURE_SECONDS}s ago" in after


async def test_the_managers_error_count_reaches_the_status_bar():
    """``error_count`` is not a ``CURATOR_KEYS`` key -- the contract has no
    health counters -- so it is read off the manager itself, the way every
    other screen reads it on the failure path."""
    screen = _screen(_grace_payload())
    screen._data_manager._error_count = 4
    app = _ThemedHarness(screen)
    async with app.run_test(size=(CURATOR_FULL_LAYOUT_COLUMNS, 48)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()
        assert "4 errors" in _screen_text(app)


async def test_a_widget_that_raises_does_not_cost_the_other_six():
    screen = _screen(_grace_payload())
    app = _ThemedHarness(screen)
    async with app.run_test(size=(CURATOR_FULL_LAYOUT_COLUMNS, 48)) as pilot:
        await pilot.pause()

        def boom(**_kwargs):
            raise RuntimeError("this panel is broken")

        screen.query_one(CuratorLeaderboard).update_data = boom
        await screen._do_refresh()
        await pilot.pause()
        text = _screen_text(app)

    assert "THE LIST · hour 4 · GRACE" in text
    assert SIGNALS_TITLE in text and ACTIVITY_TITLE in text


async def test_a_manager_returning_a_non_dict_is_ignored_rather_than_rendered():
    screen = _screen(_grace_payload())
    app = _ThemedHarness(screen)
    async with app.run_test(size=(CURATOR_FULL_LAYOUT_COLUMNS, 48)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()
        screen._data_manager._payload = None

        async def not_a_dict():
            return ["nope"]

        screen._data_manager.fetch_and_compute = not_a_dict
        await screen._do_refresh()
        await pilot.pause()
        assert "THE LIST · hour 4 · GRACE" in _screen_text(app)


# =======================================================================
# WP6.4 -- the `c` swap with a phase-aware default
# =======================================================================


def test_the_default_view_follows_the_phase():
    """Clusters are the interesting table during grace -- there is nothing to
    survive yet, so a CLOSEST CALLS panel would open on an empty state for the
    dashboard's whole first day."""
    assert _default_view("grace") == VIEW_CLUSTERS
    assert _default_view("judged") == VIEW_CLOSEST
    assert _default_view("settled") == VIEW_CLOSEST
    assert _default_view(None) == VIEW_CLUSTERS  # unknown -> the never-empty one


async def test_the_default_flips_once_and_does_not_fight_the_user():
    """The phase-aware default applies until the reader presses ``c``.  After
    that the choice is theirs, even across a phase change -- a panel that snaps
    back while you are reading it is worse than a suboptimal default."""
    screen = _screen(_grace_payload())
    app = _ThemedHarness(screen)
    async with app.run_test(size=(CURATOR_FULL_LAYOUT_COLUMNS, 48)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()
        assert screen._active_view == VIEW_CLUSTERS

        await pilot.press("c")
        await pilot.pause()
        assert screen._active_view == VIEW_CLOSEST

        screen._data_manager._payload = _judged_payload()
        await screen._do_refresh()          # phase changed under them
        await pilot.pause()
        assert screen._active_view == VIEW_CLOSEST   # unchanged: user chose

        # And the direction that actually bites.  Above, the reader's choice
        # happens to agree with the new phase's default, so a screen that
        # re-applied the default on every refresh would still pass -- which is
        # exactly what the first version of this test did.  Here the reader
        # picks the table the phase default does *not* want, and it has to
        # survive two more phase-carrying refreshes.
        await pilot.press("c")
        await pilot.pause()
        assert screen._active_view == VIEW_CLUSTERS

        await screen._do_refresh()                   # still judged
        await pilot.pause()
        assert screen._active_view == VIEW_CLUSTERS

        screen._data_manager._payload = _settled_payload()
        await screen._do_refresh()
        await pilot.pause()
        assert screen._active_view == VIEW_CLUSTERS
        assert CLUSTERS_TITLE in _screen_text(app)


async def test_the_default_moves_with_the_phase_until_the_user_speaks():
    screen = _screen(_grace_payload())
    app = _ThemedHarness(screen)
    async with app.run_test(size=(CURATOR_FULL_LAYOUT_COLUMNS, 48)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()
        assert screen._active_view == VIEW_CLUSTERS

        screen._data_manager._payload = _judged_payload()
        await screen._do_refresh()
        await pilot.pause()
        assert screen._active_view == VIEW_CLOSEST
        assert CLOSEST_CALLS_TITLE in _screen_text(app)


async def test_the_hidden_view_still_receives_updates():
    """Both stay mounted and both are dispatched to, so toggling is a
    visibility flip with no refetch and no blank first frame."""
    screen = _screen(_judged_payload())
    app = _ThemedHarness(screen)
    async with app.run_test(size=(CURATOR_FULL_LAYOUT_COLUMNS, 48)) as pilot:
        await pilot.pause()
        seen = _record_dispatches(screen)
        await screen._do_refresh()
        await pilot.pause()
        assert screen._active_view == VIEW_CLOSEST
        assert screen.query_one(f"#{CLUSTERS_ID}").display is False
        # ... and the hidden one was still handed its rows.
        assert seen["CuratorClusters"]["cluster_rows"]

        await pilot.press("c")
        await pilot.pause()
        assert CLUSTERS_TITLE in _screen_text(app)


async def test_both_views_occupy_the_identical_slot():
    """Give either a different width and the layout jumps on every ``c``."""
    screen = _screen(_grace_payload())
    app = _ThemedHarness(screen)
    async with app.run_test(size=(CURATOR_FULL_LAYOUT_COLUMNS, 48)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()
        clusters = screen.query_one(CuratorClusters)
        clusters_size = (clusters.size.width, clusters.region.x)
        await pilot.press("c")
        await pilot.pause()
        closest = screen.query_one(CuratorClosestCalls)
        assert (closest.size.width, closest.region.x) == clusters_size


async def test_the_toggle_survives_a_missing_widget():
    screen = _screen(_grace_payload())
    app = _ThemedHarness(screen)
    async with app.run_test(size=(CURATOR_FULL_LAYOUT_COLUMNS, 48)) as pilot:
        await pilot.pause()
        await screen.query_one(CuratorClusters).remove()
        await pilot.pause()
        screen.action_toggle_view()          # must not raise
        screen.action_toggle_view()
        await pilot.pause()


async def test_the_status_bar_names_the_active_view():
    screen = _screen(_grace_payload())
    app = _ThemedHarness(screen)
    async with app.run_test(size=(CURATOR_FULL_LAYOUT_COLUMNS, 48)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()
        assert f"view: {VIEW_CLUSTERS}" in _screen_text(app)
        await pilot.press("c")
        await pilot.pause()
        assert f"view: {VIEW_CLOSEST}" in _screen_text(app)
        assert screen.query_one(StatusBar) is not None


# =======================================================================
# WP6.5 -- the three phases, rendered
# =======================================================================


async def test_the_grace_screen_renders_the_countdown_and_the_curve():
    text = await _render(_grace_payload())
    assert "GRACE" in text and "judging begins in" in text
    assert "2026-08-17 19:58:47 UTC" in text
    assert "1.83×" in text                          # WP4 owns the exact form
    assert "n/a until hour 24" in text              # HOUR AT RISK during grace
    assert "routed (all refunded)" in text
    assert "list OPEN" in text


async def test_the_grace_closest_calls_panel_states_it_has_nothing_yet():
    """The panel spends the whole grace period in this state, so it is not a
    corner: it names when judging starts rather than rendering an empty table."""
    text = await _render(_grace_payload(), view=VIEW_CLOSEST)
    assert NO_JUDGED_HOURS in text
    # The absolute UTC moment judging starts, read live off the ``once`` tier.
    # Only the leading part is asserted: at this slot's width WP4's note line
    # ellipsises its own tail (``… · hour 24``), visibly, which is their
    # panel's call and not something this screen may restyle.
    assert "judging begins 2026-08-17" in text


async def test_the_judged_screen_renders_the_hour_clock_and_the_risk_state():
    text = await _render(_judged_payload())
    assert "HOUR 28" in text and "/5.00 ETH" in text
    assert "1.00×" in text                          # the flat multiplier
    assert "HOUR AT RISK" in text
    assert "needs 3.52 ETH" in text
    assert "survived 4 h" in text


async def test_the_settled_screen_renders_an_archive_not_a_fault():
    """PRD §11: a settled contract renders an archive, not an error state."""
    text = await _render(_settled_payload())
    assert "SETTLED AT HOUR 28" in text and "list FROZEN" in text
    lowered = text.lower()
    for wrong in ("unavailable", "stale", "error", "no data"):
        assert wrong not in lowered, wrong
    assert "⚠" not in text


async def test_the_settled_screen_under_a_total_outage_keeps_the_phase():
    """The flagship.  The freshness marker moves; the verdict does not."""
    text = await _render(_settled_payload(degraded=sorted(SOURCES)))
    assert "SETTLED" in text
    assert "⚠ logs, state, wallet" in text
    assert "as of" in text


async def test_all_seven_detector_rows_reach_the_compositor_in_every_phase():
    """The rail is inside a column with a fixed top; YOU is last and goes
    first if the rail is ever starved of rows."""
    for phase in PHASES:
        text = await _render(_payload_for(phase))
        for label in SIGNAL_LABELS:
            assert label in text, (label, phase)


async def test_the_phase_word_is_the_analytics_layers_and_not_a_guess():
    for phase in PHASES:
        text = await _render(_payload_for(phase))
        assert f"· {phase.upper()} ·" in text


# =======================================================================
# WP6.6 -- the measured full-layout width
# =======================================================================


async def test_the_measured_width_clears_every_marker():
    assert await _widen_markers(CURATOR_FULL_LAYOUT_COLUMNS) == 0


async def test_the_measured_width_is_tight_not_padded():
    assert await _widen_markers(CURATOR_FULL_LAYOUT_COLUMNS - 1) > 0


async def test_both_c_views_clear_at_the_same_width():
    """The swap must not change the requirement; otherwise the documented
    number is true for one keypress and false for the other."""
    for phase in PHASES:
        payload = _payload_for(phase)
        for view in (VIEW_CLUSTERS, VIEW_CLOSEST):
            assert await _widen_markers(
                CURATOR_FULL_LAYOUT_COLUMNS, payload=payload, view=view
            ) == 0, (phase, view)


async def test_the_widest_phase_is_the_one_measured():
    """A data-dependent width must be measured against the state the data is
    normally in (CLAUDE.md, the IMD/FP peg lesson).  The three phases print
    different worst cases -- SETTLED the longest hero headline, JUDGED the
    longest clock line, GRACE the longest absolute timestamp -- so the pinned
    number is the MAX over all three, asserted here rather than assumed from
    whichever fixture was handy."""
    per_phase = {}
    for phase in PHASES:
        widths = [
            await _first_clean_width(_payload_for(phase), view=view)
            for view in (VIEW_CLUSTERS, VIEW_CLOSEST)
        ]
        assert None not in widths, (phase, widths)
        per_phase[phase] = max(widths)
    assert CURATOR_FULL_LAYOUT_COLUMNS == max(per_phase.values()), per_phase


async def test_a_narrow_tier_advertises_rather_than_truncating_silently():
    assert await _widen_markers(CURATOR_FULL_LAYOUT_COLUMNS - 20) > 0


async def test_the_binding_panel_is_the_signal_rail():
    """Which panel is the last one asking for a column is itself a
    measurement.  On the surf screen that claim changed hands three times and
    was restated in prose each time with nothing that could contradict it."""
    assert await _panels_asking_for_width(
        CURATOR_FULL_LAYOUT_COLUMNS - 1
    ) == {"CuratorSignals"}
    assert await _panels_asking_for_width(CURATOR_FULL_LAYOUT_COLUMNS) == set()


async def test_a_resize_sweep_and_a_cold_boot_agree():
    """``_first_clean_width`` resizes one app; the pinned assertions boot a
    fresh one per width.  If a panel ever kept a narrow terminal's tier after
    being widened (the surf ``SurfDevActivity`` defect) the two would diverge
    exactly here."""
    assert await _first_clean_width(_grace_payload()) == CURATOR_FULL_LAYOUT_COLUMNS
    assert await _widen_markers(CURATOR_FULL_LAYOUT_COLUMNS) == 0
    assert await _widen_markers(CURATOR_FULL_LAYOUT_COLUMNS - 1) > 0


def test_curator_fits_inside_the_documented_app_width():
    """WP7 coordination tripwire -- mechanical, not a comment."""
    from maxpane_dashboard.__main__ import FULL_LAYOUT_COLUMNS

    assert CURATOR_FULL_LAYOUT_COLUMNS <= FULL_LAYOUT_COLUMNS, (
        f"curator needs {CURATOR_FULL_LAYOUT_COLUMNS} columns but the app "
        f"documents {FULL_LAYOUT_COLUMNS}. Do NOT edit __main__.py from WP6 -- "
        "report to WP7, which owns it."
    )


async def test_nothing_clips_dark_below_the_measured_width():
    """Every column shed between the floor and the pin is advertised."""
    for width in (CURATOR_FULL_LAYOUT_COLUMNS - 1, CURATOR_FULL_LAYOUT_COLUMNS - 10):
        text = await _render(_grace_payload(), width=width)
        assert "‹ widen" in text
        # ... and the panels are still there saying it, not blanked.
        assert LEADERBOARD_TITLE in text and SIGNALS_TITLE in text


# =======================================================================
# WP6.7 -- the worst-case title bar
# =======================================================================

#: The narrowest terminal on which the **whole** worst-case title bar reaches a
#: pixel: the settled phase (longest phase word plus a two-digit hour), **all
#: three** ``SOURCES`` degraded -- the state the manager's outermost guard
#: actually emits, ``payload["degraded"] = sorted(SOURCES)`` -- the
#: ``as of HH:MM`` marker and the version tail.
#:
#: ``#title-bar`` is a ``height: 1`` ``Static`` that **wraps out of existence**
#: rather than ellipsising, so a lost tail leaves no ``…`` and no trace.  That
#: is why this is swept over the real screen rather than counted: the line is
#: 75 characters and needs **79 columns**, because ``⚠`` is not a one-column
#: glyph on every width table and the centred ``Static`` rounds.  The
#: arithmetic is not the test.
#:
#: **It moves with the version string.**  The tail is `` · v{__version__}`` and
#: this was swept at ``v0.6.1``; a release that makes that string longer moves
#: this constant.  That is the pin doing its job -- re-measure, do not derive.
WORST_CASE_TITLE_COLUMNS = 79


def _worst_case_title() -> str:
    return _title_line(_settled_payload(degraded=sorted(SOURCES)))


async def test_the_whole_worst_case_title_reaches_the_compositor():
    payload = _settled_payload(degraded=sorted(SOURCES))
    text = await _render(payload, width=WORST_CASE_TITLE_COLUMNS)
    assert _worst_case_title() in text


async def test_one_column_narrower_loses_the_tail_silently():
    """The failure mode this constant exists to prevent, demonstrated.

    Pinned in both directions so the constant is tight rather than generous:
    a padded number would let the tail start disappearing with the suite green.
    """
    payload = _settled_payload(degraded=sorted(SOURCES))
    text = await _render(payload, width=WORST_CASE_TITLE_COLUMNS - 1)
    assert _worst_case_title() not in text
    # ... and it goes quietly: no ellipsis, no marker, nothing on the row says
    # a field was lost.  That silence is the whole reason for the constant.
    assert "…" not in text.split("\n")[0]


def test_the_worst_case_title_is_the_state_the_manager_really_emits():
    """Not a hypothetical: a failed cycle publishes every group at once."""
    assert "⚠ logs, state, wallet" in _worst_case_title()
    assert "SETTLED" in _worst_case_title()
    assert _worst_case_title().endswith(f"v{__version__}")


def test_the_worst_case_title_fits_the_measured_layout():
    """Two independently swept constants, never one compared with itself."""
    assert WORST_CASE_TITLE_COLUMNS <= CURATOR_FULL_LAYOUT_COLUMNS


# =======================================================================
# WP6.8 -- RefreshGuard integration
# =======================================================================


def test_refresh_guard_precedes_screen_in_the_mro():
    from textual.screen import Screen

    mro = CuratorScreen.__mro__
    assert mro.index(RefreshGuard) < mro.index(Screen)


def test_the_screen_does_not_hand_roll_the_worker():
    source = (_ROOT / "maxpane_dashboard" / "screens" / "curator.py").read_text()
    assert "run_worker" not in source


class _BlockingManager:
    """Holds one ``fetch_and_compute`` open until the test releases it.

    Event-driven: no sleeps beyond the bare ``asyncio.sleep(0)`` yields the
    event loop needs to hand control to the worker.
    """

    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self._error_count = 0
        self.calls = 0
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def fetch_and_compute(self) -> dict:
        self.calls += 1
        self.entered.set()
        await self.release.wait()
        return dict(self._payload)

    async def close(self) -> None:
        pass


async def test_an_overrun_tick_is_skipped_never_queued():
    manager = _BlockingManager(_grace_payload())
    screen = CuratorScreen(manager, poll_interval=30, name="curator", wallet=_WALLET)
    app = _ThemedHarness(screen)
    async with app.run_test(size=(CURATOR_FULL_LAYOUT_COLUMNS, 48)) as pilot:
        await pilot.pause()
        screen.start_refresh()
        await manager.entered.wait()
        assert screen._refresh_in_flight is True

        before = screen._refresh_skipped
        assert screen.start_refresh() is None      # the tick that lands mid-flight
        assert screen._refresh_skipped == before + 1
        assert manager.calls == 1                  # not queued, not restarted

        manager.release.set()
        for _ in range(20):
            await pilot.pause()
            if not screen._refresh_in_flight:
                break
        assert screen._refresh_in_flight is False
        assert manager.calls == 1
        # ... and the refresh that survived actually rendered.
        assert "THE LIST · hour 4 · GRACE" in _screen_text(app)


async def test_the_interval_timer_starts_and_stops_with_the_screen():
    screen = _screen(_grace_payload())
    app = _ThemedHarness(screen)
    async with app.run_test(size=(CURATOR_FULL_LAYOUT_COLUMNS, 48)) as pilot:
        await pilot.pause()
        screen.on_screen_resume()
        await pilot.pause()
        assert screen._refresh_timer is not None
        screen.on_screen_suspend()
        assert screen._refresh_timer is None
