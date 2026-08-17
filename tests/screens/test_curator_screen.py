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

Width is swept in two dimensions
--------------------------------

Every sweep here carries a ``height`` as well as a ``width``, and the pinned
number is asserted at a **tall** terminal and a **short** one.  The first
version of this module measured everything at 48 rows, and that was not a
neutral choice: the rail scrolls, and below 42 rows its scrollbar used to take
a column out of ``CuratorSignals`` -- the binding panel -- so the constant was
one column short of the truth on every terminal a laptop actually has open.
The gutter is reserved now (``scrollbar-gutter: stable``), which makes the
requirement height-independent, and ``_HEIGHTS`` keeps it honest by measuring
both anyway: a layout that starts depending on height again fails here rather
than in a user's 40-row window.

The rail's own rectangle
------------------------

Assertions about the seven detector rows are made against
``_region_text(app, screen.query_one(CuratorSignals), screen)``, not against
the whole screen.  Three of the seven labels are also printed by panels that
are *not* the rail -- the title bar prints ``· SETTLED ·`` in the settled
phase and the hero's CLOCK box prints ``SETTLED AT HOUR 28`` -- so a
whole-screen search cannot tell a rail that lost its first row from one that
kept it, in exactly the phase where that row is the headline.
"""

from __future__ import annotations

import asyncio
import inspect
import json
from pathlib import Path

import re

import pytest
from textual.app import App
from textual.widgets import Input

from maxpane_dashboard import __version__
from maxpane_dashboard.analytics.curator_signals import MANAGER_OWNED_KEYS
from maxpane_dashboard.data.curator_manager import SOURCES
from maxpane_dashboard.data.curator_models import CURATOR_KEYS, PHASES
from maxpane_dashboard.widgets.curator.wallet import (
    AT_THE_CAP,
    CAPPED_MARK,
    LADDER_TITLE,
    LADDER_UNAVAILABLE,
    NEXT_TITLE,
    TARGET_TITLE,
    HOLDS_RANK,
    TAKES_RANK,
    LABEL_COLS,
    NOT_ON_THE_LIST,
    NO_LADDER,
    STANDING_TITLE,
    TOP_OF_THE_LIST,
)
from maxpane_dashboard.screens.wallet_input import WalletInputScreen
from maxpane_dashboard.screens.curator import (
    CLOSEST_ID,
    CLUSTERS_ID,
    CURATOR_FULL_LAYOUT_COLUMNS,
    INITIAL_TITLE,
    MANAGER_FAILURE_SECONDS,
    META_KEYS,
    SCREEN_SUPPLIED,
    TALLER_HINT,
    VIEW_CLOSEST,
    VIEW_CLUSTERS,
    WIDGET_SIGNATURES,
    CuratorScreen,
    MODE_DASHBOARD,
    MODE_WALLET,
    WALLET_HERO_ID,
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
    CuratorWalletLadder,
    CuratorWalletNext,
    CuratorWalletStanding,
    CuratorWalletTarget,
    CuratorWalletHero,
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
    # The `y` view's three.  Listed here rather than in a second tuple because
    # every totality and dispatch guarantee below is about the screen, not
    # about whichever body happens to be visible.
    CuratorWalletLadder,
    CuratorWalletStanding,
    CuratorWalletTarget,
    CuratorWalletNext,
)

#: The window the width sweep scans.  Deliberately independent of
#: ``CURATOR_FULL_LAYOUT_COLUMNS`` -- a sweep that started at the pin would
#: agree with it by construction.
_SWEEP_LO, _SWEEP_HI = 118, 160

#: The terminal height every render defaults to: comfortably above
#: :data:`RAIL_FULL_HEIGHT`, so a width assertion measures width alone.
_TALL = 48

#: A short terminal that still has to show the whole layout's *width*
#: requirement.  It is below :data:`RAIL_FULL_HEIGHT`, so the rail is scrolling
#: here -- precisely the state the one-dimensional sweep never reached -- and
#: 30 rows is a real window, not a corner: a half-screen terminal on a laptop.
_SHORT = 30

#: Both, for the sweeps that must hold at either.
_HEIGHTS = (_TALL, _SHORT)

#: The terminal height at which ``#curator-right-rail`` stops scrolling, i.e.
#: the first height that shows all seven detector rows without one.  Measured,
#: not derived: the rail's content is a constant 14 rows (a four-row sparkline
#: panel, its one-row margin, and a nine-row signal panel -- title, spacer,
#: seven detector rows) and the rows above it in the screen's own layout take
#: the rest.  ``TALLER_HINT`` lights at
#: ``RAIL_FULL_HEIGHT - 1`` and is dark from here up, pinned in both
#: directions by ``test_the_taller_hint_lights_exactly_when_the_rail_scrolls``.
RAIL_FULL_HEIGHT = 42


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


def _all_none_payload(**overrides) -> dict:
    """Every contract key present, every value ``None`` -- under a full
    ``degraded`` list, because that is the only way the manager emits one.

    **This is the specified outage path**, not an exception:
    ``CuratorManager.fetch_and_compute`` never raises and returns the full
    contract with every value ``None`` when all three source groups are down
    (WP5's ``test_no_exception_escapes_when_every_call_raises``).  The
    ``raises=True`` double below is belt and braces for a mis-wired manager and
    must never be mistaken for the documented degradation contract.

    ``degraded`` is **not** ``None`` here and that is the point.  The manager's
    outermost guard publishes ``payload["degraded"] = sorted(SOURCES)``, and on
    the ordinary path ``_degraded()`` returns a list that can never be ``None``
    -- there is even a branch whose only job is to stop an all-``None`` payload
    shipping under an empty one (``curator_manager`` publishes ``SOURCES`` into
    ``_failed_groups`` when ``build_signals`` itself dies).  A bare
    ``dict.fromkeys`` renders a title bar with no ``⚠`` at all: 49 unreadable
    values wearing the face of a healthy picture, which is fiction of exactly
    the kind this module's docstring forbids.  ``_fmt_degraded``'s tolerance of
    ``None`` is pinned separately, on the pure helper.
    """
    payload = dict.fromkeys(CURATOR_KEYS)
    payload["degraded"] = sorted(SOURCES)
    payload.update(overrides)
    return payload


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
                  height: int = _TALL, view: str | None = None,
                  wallet=_WALLET) -> str:
    """Boot the real screen at *width* x *height*, refresh, composite it.

    ``height`` is a parameter rather than a constant because this layout's
    width requirement was measured at one height for one release and that made
    the pinned number true for a 48-row window and false for a 40-row one.
    """
    screen = _screen(payload, wallet=wallet)
    app = _ThemedHarness(screen)
    async with app.run_test(size=(width, height)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()
        if view is not None and screen._active_view != view:
            screen.action_toggle_view()
            await pilot.pause()
        return _screen_text(app)


async def _widen_markers(width: int, payload=None, view: str | None = None,
                         height: int = _TALL) -> int:
    """Composited ``‹ widen`` count at *width*, whole screen, cold boot."""
    return (await _render(payload, width=width, height=height,
                          view=view)).count("‹ widen")


async def _panels_asking_for_width(width: int, payload=None,
                                   view: str | None = None,
                                   height: int = _TALL) -> set[str]:
    """Which panels composite a ``‹ widen`` at *width*, by class name.

    A count alone cannot say *whose* marker is the last one standing, and that
    is the claim ``CURATOR_FULL_LAYOUT_COLUMNS`` is written around.
    """
    screen = _screen(payload)
    app = _ThemedHarness(screen)
    async with app.run_test(size=(width, height)) as pilot:
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


async def _first_clean_width(payload=None, view: str | None = None,
                             height: int = _TALL) -> int | None:
    """The narrowest width in the sweep window with no marker anywhere.

    Resizes one running app rather than booting one per column: the panels all
    implement ``on_resize`` and re-pick their tier, and
    ``test_a_resize_sweep_and_a_cold_boot_agree`` pins the two methods against
    each other at the boundary so this shortcut cannot drift.
    """
    screen = _screen(payload)
    app = _ThemedHarness(screen)
    async with app.run_test(size=(_SWEEP_LO, height)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()
        if view is not None and screen._active_view != view:
            screen.action_toggle_view()
            await pilot.pause()
        for width in range(_SWEEP_LO, _SWEEP_HI + 1):
            await pilot.resize_terminal(width, height)
            await pilot.pause()
            if _screen_text(app).count("‹ widen") == 0:
                return width
    return None


# =======================================================================
# WP6.1 -- skeleton: compose, bindings, the dispatch contract
# =======================================================================


def test_the_five_bindings_are_the_ones_this_screen_documents():
    """Hand-typed rather than derived: a set compared against itself could not
    catch a binding that was added, renamed or lost.

    `r` refresh, `c` swap the bottom-right slot, `w` set the wallet,
    `y` the wallet view, `escape` back out of it.
    """
    assert {binding.key for binding in CuratorScreen.BINDINGS} == {
        "r", "c", "w", "y", "escape",
    }


def test_every_binding_has_the_action_it_names():
    """A `Binding` naming a missing action fails silently at keypress time --
    Textual logs and moves on, so the key simply does nothing."""
    for binding in CuratorScreen.BINDINGS:
        assert hasattr(CuratorScreen, f"action_{binding.action}"), binding.key


def test_the_worker_name_is_the_screens_own():
    assert CuratorScreen.REFRESH_WORKER_NAME == "curator-refresh"


def test_the_initial_title_names_the_subject_before_the_first_payload():
    assert INITIAL_TITLE == "THE LIST · WhitelistCurator · Ethereum Mainnet"


async def test_screen_mounts_all_seven_widgets():
    screen = _screen()
    app = _ThemedHarness(screen)
    async with app.run_test(size=(CURATOR_FULL_LAYOUT_COLUMNS, _TALL)) as pilot:
        await pilot.pause()
        # Two heroes -- the game's and the `y` view's -- exactly one displayed.
        hero_row = screen.query_one("#hero-row").children
        assert len(hero_row) == 2
        assert [child.display for child in hero_row].count(True) == 1
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
    async with app.run_test(size=(CURATOR_FULL_LAYOUT_COLUMNS, _TALL)) as pilot:
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
    async with app.run_test(size=(CURATOR_FULL_LAYOUT_COLUMNS, _TALL)) as pilot:
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
    async with app.run_test(size=(CURATOR_FULL_LAYOUT_COLUMNS, _TALL)) as pilot:
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
    # ... and the reader is told *which* sources went quiet.  The manager can
    # only emit 49 None values alongside a full ``degraded`` list, so a title
    # bar with no warning glyph here would be the one frame on this screen
    # that looks healthy while nothing on it was read.
    assert "⚠ logs, state, wallet" in text
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
    async with app.run_test(size=(CURATOR_FULL_LAYOUT_COLUMNS, _TALL)) as pilot:
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
    async with app.run_test(size=(CURATOR_FULL_LAYOUT_COLUMNS, _TALL)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()
        assert "4 errors" in _screen_text(app)


async def test_a_widget_that_raises_does_not_cost_the_other_six():
    screen = _screen(_grace_payload())
    app = _ThemedHarness(screen)
    async with app.run_test(size=(CURATOR_FULL_LAYOUT_COLUMNS, _TALL)) as pilot:
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
    async with app.run_test(size=(CURATOR_FULL_LAYOUT_COLUMNS, _TALL)) as pilot:
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
    async with app.run_test(size=(CURATOR_FULL_LAYOUT_COLUMNS, _TALL)) as pilot:
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
    async with app.run_test(size=(CURATOR_FULL_LAYOUT_COLUMNS, _TALL)) as pilot:
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
    async with app.run_test(size=(CURATOR_FULL_LAYOUT_COLUMNS, _TALL)) as pilot:
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
    async with app.run_test(size=(CURATOR_FULL_LAYOUT_COLUMNS, _TALL)) as pilot:
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
    async with app.run_test(size=(CURATOR_FULL_LAYOUT_COLUMNS, _TALL)) as pilot:
        await pilot.pause()
        await screen.query_one(CuratorClusters).remove()
        await pilot.pause()
        screen.action_toggle_view()          # must not raise
        screen.action_toggle_view()
        await pilot.pause()


async def test_the_status_bar_names_the_active_view():
    screen = _screen(_grace_payload())
    app = _ThemedHarness(screen)
    async with app.run_test(size=(CURATOR_FULL_LAYOUT_COLUMNS, _TALL)) as pilot:
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


async def _rail_text(payload=None, *, width: int = CURATOR_FULL_LAYOUT_COLUMNS,
                     height: int = _TALL) -> str:
    """Composited text **inside ``CuratorSignals``' own rectangle**.

    The whole-screen composite cannot answer "did the rail render this row":
    ``SETTLED`` is printed by the title bar and by the hero's CLOCK box in the
    settled phase, so a rail that dropped its first row entirely leaves a
    whole-screen search green in the very phase where that row is the
    headline.  (Verified by mutation: deleting ``settled`` from
    ``SIGNAL_KEYS``/``SIGNAL_LABELS`` leaves the old assertion passing for
    ``settled`` and failing only for the other two phases.)
    """
    screen = _screen(payload)
    app = _ThemedHarness(screen)
    async with app.run_test(size=(width, height)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()
        return _region_text(app, screen.query_one(CuratorSignals), screen)


async def test_all_seven_detector_rows_reach_the_compositor_in_every_phase():
    """The rail is inside a column with a fixed top; YOU is last and goes
    first if the rail is ever starved of rows.

    Asserted inside the rail's own rectangle -- see ``_rail_text``."""
    for phase in PHASES:
        text = await _rail_text(_payload_for(phase))
        for label in SIGNAL_LABELS:
            assert label in text, (label, phase)


async def test_the_dead_logs_pool_reaches_the_three_rows_it_feeds():
    """End to end: ``degraded`` is dispatched, and the rail acts on it.

    The realistic outage, not the total one -- state alive, logs dead, which
    CLAUDE.md calls the expected case because the two sit on different
    endpoint pools.  HOUR SAVED and WHALE used to render a green ``none yet``
    / ``none this hour`` here while FARM, folded from the same group, said
    ``-- unknown``; ``degraded`` was not in this widget's signature, so the
    rail could not have told them apart even if it wanted to.
    """
    payload = _grace_payload(
        degraded=["logs"],
        last_saved_hour=None, last_saved_wallet=None, last_saved_age_s=None,
        whale_amount_eth=None, whale_wallet=None, whale_age_s=None,
        clusters_count=None,
    )
    rail = await _rail_text(payload)
    for label in ("HOUR SAVED", "WHALE", "FARM"):
        line = next(line for line in rail.splitlines() if label in line)
        assert "unknown" in line, f"{label}: {line!r}"

    # The clock keeps its own state: only the group that died goes unknown.
    assert "n/a until hour" in rail          # HOUR AT RISK, off the live state
    assert "list open" in rail               # SETTLED, off isSettled()


async def test_a_rail_row_lost_off_the_bottom_is_named_on_the_title_bar():
    """The failure ``TALLER_HINT`` exists for, demonstrated end to end.

    Below :data:`RAIL_FULL_HEIGHT` the rail scrolls and its last rows -- YOU
    first, the one row carrying an actionable number -- stop reaching the
    compositor.  Nothing else on the screen says so: the scrollbar is one cell
    in a gutter, and at very short heights Textual paints it outside the
    rail's rectangle entirely.
    """
    height = RAIL_FULL_HEIGHT - 2
    rail = await _rail_text(_grace_payload(), height=height)
    assert SIGNAL_LABELS[-1] == "YOU"
    assert "YOU" not in rail, "expected the last rail row to be below the fold"

    text = await _render(_grace_payload(), height=height)
    assert TALLER_HINT in text, "a row went off the bottom with nothing saying so"


async def test_the_taller_hint_lights_exactly_when_the_rail_scrolls():
    """Pinned in both directions, the way surf pins its own 36 rows.

    A marker that is always lit is noise and a marker that is never lit is
    dead code; the row it turns on at is the measurement.
    """
    lit = await _render(_grace_payload(), height=RAIL_FULL_HEIGHT - 1)
    dark = await _render(_grace_payload(), height=RAIL_FULL_HEIGHT)
    assert TALLER_HINT in lit
    assert TALLER_HINT not in dark
    # ... and the height it turns on at is exactly the height the seventh row
    # stops reaching the compositor, so the marker never lags the loss.
    assert "YOU" in await _rail_text(_grace_payload(), height=RAIL_FULL_HEIGHT)
    assert "YOU" not in await _rail_text(
        _grace_payload(), height=RAIL_FULL_HEIGHT - 1
    )


async def test_the_taller_hint_tracks_a_resize_rather_than_the_last_refresh():
    """``on_resize`` re-renders the title; a marker written only by
    ``_do_refresh`` would be stale until the next 30-second tick -- lit on a
    terminal that now fits, dark on one that no longer does."""
    screen = _screen(_grace_payload())
    app = _ThemedHarness(screen)
    async with app.run_test(size=(CURATOR_FULL_LAYOUT_COLUMNS, _TALL)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()
        assert TALLER_HINT not in _screen_text(app)

        await pilot.resize_terminal(
            CURATOR_FULL_LAYOUT_COLUMNS, RAIL_FULL_HEIGHT - 1
        )
        await pilot.pause()
        await pilot.pause()
        assert TALLER_HINT in _screen_text(app), "no refresh ran; the resize must"

        await pilot.resize_terminal(CURATOR_FULL_LAYOUT_COLUMNS, _TALL)
        await pilot.pause()
        await pilot.pause()
        assert TALLER_HINT not in _screen_text(app)
        # ... and the payload's own fields are still on the line, i.e. the
        # re-render recomposed the title rather than replacing it.
        assert "THE LIST · hour 4 · GRACE" in _screen_text(app)


async def test_the_taller_hint_rides_ahead_of_the_degraded_list():
    """Order is the only priority mechanism a one-row Static has.

    Every degraded group is mirrored by its own panel's unavailable state and
    the version is mirrored by the StatusBar; a lost rail row is named here
    and nowhere else, so it goes first.
    """
    line = _title_line(_settled_payload(degraded=sorted(SOURCES)), row_hint=True)
    assert line.index(TALLER_HINT) < line.index("⚠") < line.index(f"v{__version__}")


async def test_the_initial_title_takes_the_marker_too():
    """A screen whose first payload has not landed is still a screen whose
    rail may be cut, so ``INITIAL_TITLE`` carries the marker as well.

    The manager here never returns, which is the only way to hold a booted
    screen in that state: ``on_screen_resume`` fires an initial refresh and the
    frozen payload otherwise lands within one ``pause()``.
    """
    manager = _BlockingManager(_grace_payload())          # never released
    screen = CuratorScreen(manager, poll_interval=30, name="curator",
                           wallet=_WALLET)
    app = _ThemedHarness(screen)
    async with app.run_test(size=(CURATOR_FULL_LAYOUT_COLUMNS, _TALL)) as pilot:
        await pilot.pause()
        assert INITIAL_TITLE in _screen_text(app)
        assert TALLER_HINT not in _screen_text(app)
        await pilot.resize_terminal(
            CURATOR_FULL_LAYOUT_COLUMNS, RAIL_FULL_HEIGHT - 1
        )
        await pilot.pause()
        await pilot.pause()
        text = _screen_text(app)
        assert INITIAL_TITLE in text and TALLER_HINT in text


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


async def test_the_measured_width_holds_at_a_short_terminal_too():
    """The second dimension, and the one this sweep was missing.

    ``#curator-right-rail`` scrolls, so on a terminal under
    :data:`RAIL_FULL_HEIGHT` rows its scrollbar wants a column -- and it would
    take that column out of ``CuratorSignals``, the panel that binds this
    width.  Measured at 48 rows alone, ``CURATOR_FULL_LAYOUT_COLUMNS`` was
    therefore true for a full-screen terminal and one column short of the
    truth for a half-screen one: the pin cleared at 48 rows and lit
    ``‹ widen`` at 40.  The gutter is reserved now, and this asserts the
    number at a height where the scrollbar is actually engaged.
    """
    for height in _HEIGHTS:
        assert await _widen_markers(
            CURATOR_FULL_LAYOUT_COLUMNS, height=height
        ) == 0, height
        assert await _widen_markers(
            CURATOR_FULL_LAYOUT_COLUMNS - 1, height=height
        ) > 0, height


async def test_the_width_requirement_does_not_move_with_the_terminal_height():
    """The property the reserved gutter buys, asserted on the binding panel.

    ``CuratorSignals``' inner width is what every column of this sweep is
    really measuring; if it ever changes with the terminal's height again, the
    pinned constant becomes a function of the window the sweep was run in.
    """
    widths = {}
    for height in (_SHORT, RAIL_FULL_HEIGHT - 1, RAIL_FULL_HEIGHT, _TALL):
        screen = _screen(_grace_payload())
        app = _ThemedHarness(screen)
        async with app.run_test(
            size=(CURATOR_FULL_LAYOUT_COLUMNS, height)
        ) as pilot:
            await pilot.pause()
            await screen._do_refresh()
            await pilot.pause()
            widths[height] = screen.query_one(CuratorSignals).size.width
    assert len(set(widths.values())) == 1, widths


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
            await _first_clean_width(_payload_for(phase), view=view, height=height)
            for view in (VIEW_CLUSTERS, VIEW_CLOSEST)
            for height in _HEIGHTS
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
    for height in _HEIGHTS:
        assert await _panels_asking_for_width(
            CURATOR_FULL_LAYOUT_COLUMNS - 1, height=height
        ) == {"CuratorSignals"}, height
        assert await _panels_asking_for_width(
            CURATOR_FULL_LAYOUT_COLUMNS, height=height
        ) == set(), height


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
#: ``as of HH:MM`` marker, the ``‹ taller`` row marker and the version tail.
#:
#: ``#title-bar`` is a ``height: 1`` ``Static`` that **wraps out of existence**
#: rather than ellipsising, so a lost tail leaves no ``…`` and no trace.  That
#: is why this is swept over the real screen rather than counted: ``⚠`` is not
#: a one-column glyph on every width table and the centred ``Static`` rounds.
#: The arithmetic is not the test.
#:
#: **The row marker is part of the worst case, and it was not always here.**
#: This constant was 79 while the line's longest form was the settled outage
#: alone; ``TALLER_HINT`` only lights on a terminal shorter than
#: :data:`RAIL_FULL_HEIGHT`, and a short terminal is exactly where a wrapped
#: tail is most likely -- so the worst case is measured *with* it, on a short
#: terminal, rather than on the one state where the marker happens to be dark.
#:
#: **It moves with the version string.**  The tail is `` · v{__version__}`` and
#: this was swept at ``v0.6.1``; a release that makes that string longer moves
#: this constant.  That is the pin doing its job -- re-measure, do not derive.
WORST_CASE_TITLE_COLUMNS = 90

#: The height the worst case is measured at: one row short of a rail that
#: fits, so ``TALLER_HINT`` is lit.
_WORST_CASE_HEIGHT = RAIL_FULL_HEIGHT - 1


def _worst_case_title() -> str:
    return _title_line(_settled_payload(degraded=sorted(SOURCES)), row_hint=True)


async def test_the_whole_worst_case_title_reaches_the_compositor():
    payload = _settled_payload(degraded=sorted(SOURCES))
    text = await _render(payload, width=WORST_CASE_TITLE_COLUMNS,
                         height=_WORST_CASE_HEIGHT)
    assert _worst_case_title() in text


async def test_one_column_narrower_loses_the_tail_silently():
    """The failure mode this constant exists to prevent, demonstrated.

    Pinned in both directions so the constant is tight rather than generous:
    a padded number would let the tail start disappearing with the suite green.
    """
    payload = _settled_payload(degraded=sorted(SOURCES))
    text = await _render(payload, width=WORST_CASE_TITLE_COLUMNS - 1,
                         height=_WORST_CASE_HEIGHT)
    assert _worst_case_title() not in text
    # ... and it goes quietly: no ellipsis, no marker, nothing on the row says
    # a field was lost.  That silence is the whole reason for the constant.
    assert "…" not in text.split("\n")[0]


def test_the_worst_case_title_is_the_state_the_manager_really_emits():
    """Not a hypothetical: a failed cycle publishes every group at once, and
    a rail that does not fit is a terminal size, not a fault."""
    assert "⚠ logs, state, wallet" in _worst_case_title()
    assert "SETTLED" in _worst_case_title()
    assert TALLER_HINT in _worst_case_title()
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
    async with app.run_test(size=(CURATOR_FULL_LAYOUT_COLUMNS, _TALL)) as pilot:
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
    async with app.run_test(size=(CURATOR_FULL_LAYOUT_COLUMNS, _TALL)) as pilot:
        await pilot.pause()
        screen.on_screen_resume()
        await pilot.pause()
        assert screen._refresh_timer is not None
        screen.on_screen_suspend()
        assert screen._refresh_timer is None


# ---------------------------------------------------------------------------
# The `w` key -- naming the wallet the YOU row is about, from inside the app
# ---------------------------------------------------------------------------
#
# The YOU row is the only actionable number on this screen and it is dark until
# somebody names an address, so `w` prompts for one.  These tests drive the real
# `WalletInputScreen` through the pilot rather than calling the callback
# directly: the callback is trivial and the wiring is what breaks.
#
# `save_wallet` is monkeypatched in every one of them.  It writes
# `~/.maxpane/config.toml`, and a "zero network, zero side effect" suite that
# rewrites the developer's own config is precisely the failure this repo found
# in `MANAGER_ATTRS` and wrote into CLAUDE.md.


class _WalletManager(_FakeManager):
    """A manager whose YOU keys arrive only once a wallet has been set.

    That is what the real one does: `set_wallet` expires the fast tier, and the
    next cycle's six YOU reads populate the row.
    """

    def __init__(self) -> None:
        self._no_wallet = _grace_payload(
            you_rank=None, you_points=None, you_credit_eth=None,
            you_required_next_eth=None, you_marginal_points=None,
        )
        super().__init__(payload=self._no_wallet)
        self.set_calls: list[str | None] = []

    def set_wallet(self, address: str | None) -> bool:
        self.set_calls.append(address)
        moved = (address or None) != getattr(self, "_wallet", None)
        self._wallet = address or None
        self._payload = _grace_payload() if self._wallet else self._no_wallet
        return moved


@pytest.fixture()
def saved_wallets(monkeypatch) -> list[str]:
    """Capture what `WalletInputScreen` would persist, writing no file."""
    saved: list[str] = []
    monkeypatch.setattr(
        "maxpane_dashboard.screens.wallet_input.save_wallet", saved.append
    )
    monkeypatch.setattr(
        "maxpane_dashboard.screens.wallet_input.get_wallet", lambda: ""
    )
    return saved


async def test_w_opens_the_wallet_prompt(saved_wallets):
    screen = _screen(_grace_payload(), wallet=None)
    app = _ThemedHarness(screen)
    async with app.run_test(size=(CURATOR_FULL_LAYOUT_COLUMNS, _TALL)) as pilot:
        await pilot.pause()
        await pilot.press("w")
        await pilot.pause()
        assert isinstance(app.screen, WalletInputScreen)


async def test_the_you_row_goes_from_no_wallet_to_a_real_rank(saved_wallets):
    """The whole point of the key, asserted on composited output at both ends."""
    manager = _WalletManager()
    screen = CuratorScreen(manager, poll_interval=30, name="curator", wallet=None)
    app = _ThemedHarness(screen)
    async with app.run_test(size=(CURATOR_FULL_LAYOUT_COLUMNS, _TALL)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()
        before = _region_text(app, screen.query_one(CuratorSignals), screen)
        assert NO_WALLET in before
        assert "rank 1" not in before

        await pilot.press("w")
        await pilot.pause()
        app.screen.query_one("#wi-input", Input).value = _WALLET
        await pilot.press("enter")
        await pilot.pause()
        await screen._do_refresh()          # the refresh the key scheduled
        await pilot.pause()

        after = _region_text(app, screen.query_one(CuratorSignals), screen)
        assert NO_WALLET not in after
        assert "rank 1" in after
        # Both halves moved: the manager owns the six YOU reads, the screen owns
        # `you_address`, which is what the leaderboard emphasises.
        assert manager.set_calls == [_WALLET]
        assert screen._wallet == _WALLET
        # Persisted, so the choice outlives the process -- without touching the
        # real config file.
        assert saved_wallets == [_WALLET]


async def test_escaping_the_prompt_changes_nothing(saved_wallets):
    manager = _WalletManager()
    screen = CuratorScreen(manager, poll_interval=30, name="curator", wallet=None)
    app = _ThemedHarness(screen)
    async with app.run_test(size=(CURATOR_FULL_LAYOUT_COLUMNS, _TALL)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()
        await pilot.press("w")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()

        assert manager.set_calls == []
        assert screen._wallet is None
        assert saved_wallets == []
        text = _region_text(app, screen.query_one(CuratorSignals), screen)
        assert NO_WALLET in text


async def test_an_invalid_address_never_reaches_the_manager(saved_wallets):
    """`WalletInputScreen` validates and stays open; the row must not change on
    the strength of something that is not an address."""
    manager = _WalletManager()
    screen = CuratorScreen(manager, poll_interval=30, name="curator", wallet=None)
    app = _ThemedHarness(screen)
    async with app.run_test(size=(CURATOR_FULL_LAYOUT_COLUMNS, _TALL)) as pilot:
        await pilot.pause()
        await pilot.press("w")
        await pilot.pause()
        app.screen.query_one("#wi-input", Input).value = "0xnothex"
        await pilot.press("enter")
        await pilot.pause()

        assert isinstance(app.screen, WalletInputScreen)   # still open
        assert manager.set_calls == []
        assert saved_wallets == []


async def _refreshes_after_entering(address, *, starting_wallet):
    """Count the refreshes the *keypress* asks for, entering *address*.

    Counts `action_refresh` rather than the manager's cycles: RefreshGuard runs
    its own startup refresh and its own interval timer, so a cycle count would
    be measuring the guard, not the decision this test is about.
    """
    manager = _WalletManager()
    manager._wallet = starting_wallet
    manager._payload = _grace_payload() if starting_wallet else manager._no_wallet
    screen = CuratorScreen(
        manager, poll_interval=30, name="curator", wallet=starting_wallet
    )
    asked: list[int] = []
    original = screen.action_refresh
    screen.action_refresh = lambda: (asked.append(1), original())[1]  # type: ignore[method-assign]

    app = _ThemedHarness(screen)
    async with app.run_test(size=(CURATOR_FULL_LAYOUT_COLUMNS, _TALL)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()
        await pilot.press("w")
        await pilot.pause()
        app.screen.query_one("#wi-input", Input).value = address
        await pilot.press("enter")
        await pilot.pause()
    return len(asked), manager.set_calls


async def test_re_entering_the_same_wallet_costs_no_refresh(saved_wallets):
    """`set_wallet` returns False for an unchanged address, and the screen
    spends a refresh only when something actually moved."""
    refreshes, set_calls = await _refreshes_after_entering(
        _WALLET, starting_wallet=_WALLET
    )
    assert set_calls == [_WALLET]          # the manager was still told
    assert refreshes == 0                  # but nothing was refetched


async def test_entering_a_different_wallet_does_cost_a_refresh(saved_wallets):
    """The other half of the pair: without it, the test above passes just as
    well on a screen that never refreshes at all."""
    refreshes, set_calls = await _refreshes_after_entering(
        _WALLET, starting_wallet=None
    )
    assert set_calls == [_WALLET]
    assert refreshes == 1


# ---------------------------------------------------------------------------
# The `y` view -- the reader's own standing on THE LIST
# ---------------------------------------------------------------------------


def _wallet_payload(**overrides) -> dict:
    """The grace payload plus the folded YOU fields the view renders.

    Values are the capture's own rank-1 wallet, so the numbers are consistent
    with the leaderboard the other body shows.
    """
    payload = _grace_payload()
    payload.update(
        you_weight_eth=947.31,
        you_tx_count=3,
        you_first_hour=0,
        you_joined_utc="2026-08-16 19:58 UTC",
        you_weight_share_pct=2.94,
        you_ladder_rows=[
            {"hour": 0, "amount_eth": 1.1, "credited_eth": 1.1,
             "weight_eth": 2.13, "early_x": 1.94, "capped": False, "ts": None},
            {"hour": 0, "amount_eth": 63.5, "credited_eth": 62.4,
             "weight_eth": 120.4, "early_x": 1.93, "capped": False, "ts": None},
            {"hour": 1, "amount_eth": 1200.0, "credited_eth": 0.0,
             "weight_eth": 0.0, "early_x": 1.91, "capped": True, "ts": None},
        ],
        you_next_rank=None,
        you_next_rank_needs_eth=None,
        you_next_send_passes=None,
    )
    payload.update(overrides)
    return payload


async def _wallet_rail_text(payload=None, *, width=CURATOR_FULL_LAYOUT_COLUMNS,
                            height=_TALL) -> str:
    """Composited text **inside the wallet rail's own rectangle**.

    The whole-screen composite cannot answer a question about this rail's
    columns: every one of its rows also carries a ladder row to its left, so a
    line starting with `rank` never exists there.
    """
    screen = _screen(payload if payload is not None else _wallet_payload())
    app = _ThemedHarness(screen)
    async with app.run_test(size=(width, height)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()
        await pilot.press("y")
        await pilot.pause()
        return _region_text(app, screen.query_one("#curator-wallet-rail"), screen)


async def _wallet_view_text(payload=None, *, width=CURATOR_FULL_LAYOUT_COLUMNS,
                            height=_TALL) -> str:
    """Composite the screen with the `y` view showing."""
    screen = _screen(payload if payload is not None else _wallet_payload())
    app = _ThemedHarness(screen)
    async with app.run_test(size=(width, height)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()
        await pilot.press("y")
        await pilot.pause()
        return _screen_text(app)


async def test_y_swaps_the_body_and_keeps_the_clock_on_screen():
    """The whole reason the hero sits outside both bodies: this view exists to
    decide what to send, and that decision is worthless without the clock it is
    racing."""
    screen = _screen(_wallet_payload())
    app = _ThemedHarness(screen)
    async with app.run_test(size=(CURATOR_FULL_LAYOUT_COLUMNS, _TALL)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()
        dashboard = _screen_text(app)
        assert LEADERBOARD_TITLE in dashboard
        assert LADDER_TITLE not in dashboard

        await pilot.press("y")
        await pilot.pause()
        wallet = _screen_text(app)

        assert screen._mode == MODE_WALLET
        assert LADDER_TITLE in wallet and STANDING_TITLE in wallet
        assert NEXT_TITLE in wallet and TARGET_TITLE in wallet
        # The game's own panels are gone...
        assert LEADERBOARD_TITLE not in wallet
        assert ACTIVITY_TITLE not in wallet
        # ...but the clock and the title bar are not.
        assert "THE LIST" in wallet
        assert "GRACE" in wallet


async def test_y_toggles_back_and_escape_only_goes_one_way():
    screen = _screen(_wallet_payload())
    app = _ThemedHarness(screen)
    async with app.run_test(size=(CURATOR_FULL_LAYOUT_COLUMNS, _TALL)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()

        await pilot.press("y")
        await pilot.pause()
        assert screen._mode == MODE_WALLET
        await pilot.press("y")
        await pilot.pause()
        assert screen._mode == MODE_DASHBOARD

        await pilot.press("y")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert screen._mode == MODE_DASHBOARD
        # Escape on the dashboard is a no-op, never a toggle back in.
        await pilot.press("escape")
        await pilot.pause()
        assert screen._mode == MODE_DASHBOARD


async def test_the_ladder_renders_every_send_with_the_multiplier_it_got():
    text = await _wallet_view_text()
    assert "1.94×" in text and "1.93×" in text        # the decay the reader paid
    assert "63.50" in text


async def test_a_capped_send_says_capped_rather_than_crediting_zero():
    """Above the 1000 ETH cap a deposit credits nothing while still counting in
    full toward its hour's survival.  A bare 0.00 in the credit column reads as
    a decode that failed."""
    text = await _wallet_view_text()
    assert CAPPED_MARK in text


async def test_the_standing_names_the_share_as_a_share_of_all_weight():
    text = await _wallet_view_text()
    assert "of all weight" in text
    # `rank` is a label now, so the value beside it is the place alone.
    assert "rank" in text and "1 of" in text


async def test_a_dead_logs_pool_costs_the_ladder_and_says_so():
    """`None` is "the logs pool did not read", never "you never sent"."""
    text = await _wallet_view_text(_wallet_payload(you_ladder_rows=None))
    assert LADDER_UNAVAILABLE in text
    assert NO_LADDER not in text


async def test_a_wallet_that_never_deposited_is_not_a_wallet_scoring_zero():
    text = await _wallet_view_text(
        _wallet_payload(
            you_rank=None, you_points=None, you_credit_eth=None,
            you_weight_eth=None, you_tx_count=None, you_weight_share_pct=None,
            you_ladder_rows=[], you_first_hour=None, you_joined_utc=None,
        )
    )
    assert NOT_ON_THE_LIST in text
    assert NO_LADDER in text
    assert "rank 0" not in text


async def test_rank_one_is_told_there_is_nobody_above():
    text = await _wallet_view_text(_wallet_payload(you_rank=1))
    assert TOP_OF_THE_LIST in text


async def test_a_reachable_rank_above_is_quoted_as_one_send():
    text = await _wallet_view_text(
        _wallet_payload(you_rank=12, you_next_rank=11, you_next_rank_needs_eth=604.0,
                        you_next_send_passes=False)
    )
    assert "rank 11 needs" in text
    assert "604.00" in text
    # ...and the reader is told their minimum legal send is not enough for it.
    assert HOLDS_RANK in text


async def test_a_capped_wallet_is_told_no_send_buys_weight():
    """The honest answer where a number would be a promise the contract will
    not keep: past the credit cap no deposit adds weight at any price."""
    text = await _wallet_view_text(
        _wallet_payload(you_rank=12, you_next_rank=11, you_next_rank_needs_eth=None)
    )
    assert AT_THE_CAP in text


async def test_the_wallet_view_clears_at_the_pinned_full_layout_width():
    """Measured, not reasoned: the view must not push the screen's number up.

    Swept independently of the pin, both bodies, so a `y` view that needed 150
    columns could not hide behind a dashboard that clears at 138.
    """
    for width in range(CURATOR_FULL_LAYOUT_COLUMNS, _SWEEP_HI + 1):
        text = await _wallet_view_text(width=width)
        if "‹ widen" not in text:
            assert width == CURATOR_FULL_LAYOUT_COLUMNS, (
                f"the y view first clears at {width}, not the pinned "
                f"{CURATOR_FULL_LAYOUT_COLUMNS}"
            )
            return
    raise AssertionError("the y view never cleared inside the sweep window")


async def test_an_unknown_pass_verdict_says_neither_enough_nor_not_enough():
    """`you_next_send_passes is None` means the comparison could not be made.
    Rendered as either verdict it becomes a claim about a number nobody read."""
    text = await _wallet_view_text(
        _wallet_payload(you_rank=12, you_next_rank=11, you_next_rank_needs_eth=604.0,
                        you_next_send_passes=None)
    )
    assert HOLDS_RANK not in text
    assert TAKES_RANK not in text
    # ...while the half that IS known still renders.
    assert "rank 11 needs" in text


async def test_a_send_that_takes_the_rank_says_so():
    text = await _wallet_view_text(
        _wallet_payload(you_rank=12, you_next_rank=11, you_next_rank_needs_eth=604.0,
                        you_next_send_passes=True)
    )
    assert TAKES_RANK in text
    assert HOLDS_RANK not in text


async def test_y_swaps_the_hero_for_wallet_metrics_too():
    """The game's CLOCK / LIST / CURVE is about the list; in this view the
    reader is asking about themselves.  The phase and hour stay legible in the
    title bar above, which is why the countdown can leave the hero."""
    screen = _screen(_wallet_payload())
    app = _ThemedHarness(screen)
    async with app.run_test(size=(CURATOR_FULL_LAYOUT_COLUMNS, _TALL)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()
        dashboard = _screen_text(app)
        assert "CLOCK" in dashboard and "YOUR RANK" not in dashboard

        await pilot.press("y")
        await pilot.pause()
        wallet = _screen_text(app)
        assert "YOUR RANK" in wallet and "YOUR SCORE" in wallet
        assert "YOUR NEXT SEND" in wallet
        # Structural, not "CLOCK is absent from the text": two heroes sharing
        # one row would still composite *something* legible, so the flags are
        # what this pins.
        assert screen.query_one(CuratorHero).display is False
        assert screen.query_one(f"#{WALLET_HERO_ID}").display is True
        assert "CLOCK" not in wallet
        # The one honest capital sentence stays on screen in both views.
        assert "EOA-only gate" in wallet
        # ...and so does the phase, one row up.
        assert "GRACE" in wallet

        await pilot.press("y")
        await pilot.pause()
        assert "CLOCK" in _screen_text(app)
        assert screen.query_one(CuratorHero).display is True
        assert screen.query_one(f"#{WALLET_HERO_ID}").display is False


async def test_every_label_in_the_rail_puts_its_value_in_the_same_column():
    """One label column for all three panels: a per-panel width would step the
    values in and out down the rail."""
    text = await _wallet_rail_text(
        _wallet_payload(you_rank=12, you_next_rank=11, you_next_rank_needs_eth=604.0,
                        you_next_send_passes=False)
    )
    labels = ("rank", "score", "banked", "share", "joined", "send", "to beat",
              "gain", "to pass")
    starts, seen = set(), set()
    for line in text.split("\n"):
        stripped = line.lstrip()
        label = next((l for l in labels if stripped.startswith(l + " ")), None)
        if label is None:
            continue
        seen.add(label)
        indent = len(line) - len(stripped)
        # The value begins exactly one label field plus one gutter in, whatever
        # the label's own length -- and the gutter may hold a `≥`.
        value_col = indent + LABEL_COLS + len("  ")
        assert line[value_col] != " ", (label, repr(line))
        starts.add(value_col)
    assert seen == set(labels), f"missing labels: {sorted(set(labels) - seen)}"
    assert len(starts) == 1, f"values start in {sorted(starts)}, not one column"


async def test_the_comparison_glyph_rides_in_the_gutter_not_in_the_value():
    """`≥` is spent out of the two columns between label and value, which is
    what lets the amount line up with `4 of 10,643` two panels above."""
    text = await _wallet_rail_text()
    send = next(l for l in text.split("\n") if l.lstrip().startswith("send "))
    indent = len(send) - len(send.lstrip())
    assert send[indent + LABEL_COLS] == "≥"


async def test_the_two_amounts_in_your_next_move_share_a_column():
    """The `≥` is spent out of the label gutter, so the two amounts -- and every
    other value in the rail -- start in the same column."""
    text = await _wallet_rail_text()
    send = next(l for l in text.split("\n") if "send" in l and "≥" in l)
    beat = next(l for l in text.split("\n") if "to beat" in l)
    assert send.index("491.00") == beat.index("490.90")


async def test_the_verdict_hangs_on_its_own_line_under_the_points():
    """Not trailing the points behind a `·`: it is a sentence, not a statistic."""
    text = await _wallet_view_text(
        _wallet_payload(you_rank=12, you_next_rank=11, you_next_rank_needs_eth=604.0,
                        you_next_send_passes=False)
    )
    gain = next(l for l in text.split("\n") if "gain" in l)
    assert "pts" in gain
    assert HOLDS_RANK not in gain
    verdict = next(l for l in text.split("\n") if HOLDS_RANK in l)
    assert "pts" not in verdict
