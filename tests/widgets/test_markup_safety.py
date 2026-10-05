"""Regression tests for HIGH-7: hostile third-party names must not crash the app.

Textual's ``DataTable.add_row`` stores cell values verbatim and defers
``Text.from_markup`` to ``_on_idle -> _update_dimensions ->
default_cell_formatter``. A test that merely calls ``update_data()`` and
asserts "no exception" therefore passes *while the bug is still present* --
the ``MarkupError`` fires later, inside the message pump, where the screen's
``try/except`` cannot see it and the whole app dies.

Every test here consequently mounts the real widget in a real ``App`` and
pumps at least one idle cycle via ``pilot.pause()`` so the deferred formatter
actually runs. ``test_harness_detects_unescaped_markup`` is the control: it
proves this harness really does surface the crash, so the tests below are
meaningful rather than vacuous.
"""

from __future__ import annotations

import pytest
from rich.cells import cell_len
from rich.errors import MarkupError
from rich.text import Text
from textual.app import App, ComposeResult
from textual.widgets import DataTable

from maxpane_dashboard.data.models import ActivityEvent, BakerySummary
from maxpane_dashboard.widgets.address import ICON_COLS, address_text
from maxpane_dashboard.widgets.explorer import ETHEREUM
from maxpane_dashboard.widgets.leaderboard import Leaderboard
from maxpane_dashboard.widgets.markup_safety import (
    TAG_LIKE,
    flatten,
    safe_markup,
    sanitize_cell,
    strip_tags,
    visible_len,
)
from maxpane_dashboard.widgets.panels import TableLeaderboard

# Names a griefer can set on a public leaderboard. Each is malformed Rich
# markup in a different way; every one of them raises MarkupError if it
# reaches Text.from_markup unescaped.
HOSTILE_NAMES = [
    "[/x] Bakers",  # closing tag matching no open tag (the reported case)
    "[/]",  # bare close with nothing open
    "[/bold] Crew",  # close of a tag that was never opened
    "[bold] Unclosed",  # valid-but-unclosed: no error, but leaks styling
    "[not a tag] Guild",  # bracketed text that is not a real tag
    "[#00ff00 on]",  # malformed style definition
]


class _Harness(App):
    """Mount a single widget so ``update_data`` can be driven headlessly."""

    def __init__(self, widget) -> None:
        super().__init__()
        self._widget = widget

    def compose(self) -> ComposeResult:
        yield self._widget


def _bakery(idx: int, name: str) -> BakerySummary:
    return BakerySummary(
        id=idx,
        name=name,
        creator="0x" + "1" * 40,
        leader="0x" + "2" * 40,
        top_cook=None,
        member_count=3,
        active_cook_count=2,
        season_id=1,
        created_at="1700000000",
        tx_count=str(10_000_000 - idx),
        raw_tx_count=str(10_000_000 - idx),
        buffs=0,
        debuffs=0,
        active_buffs=(),
        active_debuffs=(),
    )


# -- control: prove the harness can see the crash ----------------------


@pytest.mark.parametrize("hostile", ["[/x] Bakers", "[/]", "[/bold] Crew"])
async def test_harness_detects_unescaped_markup(hostile: str) -> None:
    """An unescaped hostile value must still blow up through this harness.

    This is what makes the rest of the file trustworthy. If Textual ever
    stops deferring markup parsing to idle, this test fails and tells us the
    other tests here have quietly become vacuous.
    """

    class _Raw(App):
        def compose(self) -> ComposeResult:
            yield DataTable(id="t")

        def on_mount(self) -> None:
            table = self.query_one("#t", DataTable)
            table.add_column("Name")
            table.add_row(hostile)  # deliberately unescaped

    with pytest.raises(MarkupError):
        async with _Raw().run_test() as pilot:
            await pilot.pause()


# -- the fix: Leaderboard (widgets/leaderboard.py) ---------------------


async def test_leaderboard_survives_hostile_leader_name() -> None:
    """The reported crash: hostile name in the bold-highlighted leader row."""
    widget = Leaderboard()
    async with _Harness(widget).run_test() as pilot:
        widget.update_data([_bakery(1, "[/x] Bakers")], {}, 1000.0)
        await pilot.pause()
        await pilot.pause()

        table = widget.query_one("#leaderboard-table", DataTable)
        assert table.row_count == 1
        # Rendered literally, not swallowed as a markup tag.
        rendered = table.get_row_at(0)[1]
        assert "[/x] Bakers" in str(rendered)


@pytest.mark.parametrize("hostile", HOSTILE_NAMES)
async def test_leaderboard_survives_hostile_names_every_row(hostile: str) -> None:
    """Hostile names crash in the leader row *and* in the plain rows."""
    widget = Leaderboard()
    async with _Harness(widget).run_test() as pilot:
        # Same hostile name in row 1 (markup-wrapped) and row 2 (raw).
        widget.update_data(
            [_bakery(1, hostile), _bakery(2, hostile)],
            {},
            1000.0,
        )
        await pilot.pause()
        await pilot.pause()

        table = widget.query_one("#leaderboard-table", DataTable)
        assert table.row_count == 2


async def test_leaderboard_survives_repeated_refreshes() -> None:
    """The real failure recurs on every refresh, so re-render repeatedly."""
    widget = Leaderboard()
    async with _Harness(widget).run_test() as pilot:
        for _ in range(3):
            widget.update_data(
                [_bakery(i, name) for i, name in enumerate(HOSTILE_NAMES, start=1)],
                {},
                1000.0,
            )
            await pilot.pause()
            await pilot.pause()

        table = widget.query_one("#leaderboard-table", DataTable)
        assert table.row_count == len(HOSTILE_NAMES)


async def test_leaderboard_keeps_leader_bold_styling() -> None:
    """Escaping must not destroy the intended bold markup on the leader row."""
    widget = Leaderboard()
    async with _Harness(widget).run_test() as pilot:
        widget.update_data([_bakery(1, "Normal Name")], {}, 1000.0)
        await pilot.pause()

        table = widget.query_one("#leaderboard-table", DataTable)
        assert str(table.get_row_at(0)[1]) == "[bold]Normal Name[/]"


# -- the base new leaderboards are built on ----------------------------
#
# Until Branch 8 WP-B these two tests drove ``templates/leaderboard_template
# .GameLeaderboard``, the copy-source new dashboards were seeded from. The
# templates are gone; a new leaderboard subclasses ``panels.TableLeaderboard``
# and writes its cells in ``build_row``, so the subject is now the smallest
# such subclass, with the template's five columns and its two escape paths:
# ``safe_markup`` on the API-sourced detail/status cells and ``address_text``
# (a pre-built ``Text``, never a markup string) on the name-or-address cell.


class _HostileBoard(TableLeaderboard):
    TITLE = "LEADERBOARD"
    TABLE_ID = "game-leaderboard-table"
    COLUMNS = (
        ("#", 4), ("Name", 16 + ICON_COLS), ("Score", 12), ("Detail", 12),
        ("Status", 10),
    )
    EMPTY_ROW = ("--", "No data", "--", "--", "--")

    def update_data(self, entries: list[dict] | None = None) -> None:
        self.render_table(entries)

    def build_row(self, index: int, entry: dict) -> tuple:
        name = address_text(
            entry.get("address"), label=entry.get("name") or None, width=16,
            style="bold" if index == 0 else "", explorer=ETHEREUM,
        )
        score = f"{float(entry.get('score', 0)):,.0f}"
        return (
            str(index + 1), name, f"[bold]{score}[/]" if index == 0 else score,
            safe_markup(entry.get("detail", "")), safe_markup(entry.get("status", "")),
        )


@pytest.mark.parametrize("hostile", HOSTILE_NAMES)
async def test_table_leaderboard_survives_hostile_entries(hostile: str) -> None:
    """A ``TableLeaderboard`` built the documented way must not carry the bug."""
    widget = _HostileBoard()
    async with _Harness(widget).run_test() as pilot:
        widget.update_data(
            [
                {"name": hostile, "score": 1234, "detail": hostile, "status": hostile},
                {"name": hostile, "score": 12, "detail": hostile, "status": hostile},
            ]
        )
        await pilot.pause()
        await pilot.pause()

        table = widget.query_one("#game-leaderboard-table", DataTable)
        assert table.row_count == 2


async def test_table_leaderboard_survives_hostile_address_fallback() -> None:
    """The name falls back to the address, which is API-sourced too."""
    widget = _HostileBoard()
    async with _Harness(widget).run_test() as pilot:
        widget.update_data([{"name": "", "address": "[/x]", "score": 1}])
        await pilot.pause()
        await pilot.pause()

        table = widget.query_one("#game-leaderboard-table", DataTable)
        assert table.row_count == 1


# -- the helper itself -------------------------------------------------


@pytest.mark.parametrize("hostile", HOSTILE_NAMES)
def test_safe_markup_output_parses_as_markup(hostile: str) -> None:
    """Escaped output must round-trip through from_markup to the original."""
    from rich.text import Text

    assert Text.from_markup(safe_markup(hostile)).plain == hostile


def test_safe_markup_handles_none_and_non_strings() -> None:
    assert safe_markup(None) == ""
    assert safe_markup(42) == "42"
    assert safe_markup("plain") == "plain"


# -- the rest of the fleet ---------------------------------------------
#
# The same crash exists wherever another party's text reaches a DataTable or
# a markup string: token symbols (anyone can deploy an ERC-20 called "[/x]"),
# NFT collection names, pet names, player handles. These drive each widget
# through a real mount + idle cycle with hostile values in every row, so the
# non-leader ("bare cell") branches are exercised too -- those are just as
# fatal as the bold ones, because DataTable markup-parses any cell containing
# a "[".


@pytest.mark.parametrize("hostile", HOSTILE_NAMES)
async def test_dota_leaderboard_survives_hostile_handles(hostile: str) -> None:
    from maxpane_dashboard.widgets.dota.dota_leaderboard import DOTALeaderboard

    widget = DOTALeaderboard()
    async with _Harness(widget).run_test() as pilot:
        widget.update_data(
            [
                {"rank": r, "name": hostile, "wins": 1, "games": 2,
                 "win_rate": 50.0, "player_type": hostile}
                for r in (1, 2, 3)
            ]
        )
        await pilot.pause()
        await pilot.pause()
        assert widget.query_one("#dota-leaderboard-table", DataTable).row_count == 3


@pytest.mark.parametrize("hostile", HOSTILE_NAMES)
async def test_ttt_leaderboard_survives_hostile_symbols(hostile: str) -> None:
    """Anyone can deploy a token whose symbol is malformed markup."""
    from maxpane_dashboard.widgets.ttt.ttt_leaderboard import TTTLeaderboard

    widget = TTTLeaderboard()
    async with _Harness(widget).run_test() as pilot:
        widget.update_data(
            top_tokens_by_volume=[
                {"rank": r, "symbol": hostile, "price_usd": 1.0,
                 "change_h24": 1.0, "vol_usd_h24": 1.0, "age_str": "1d",
                 "mcap_usd": 1.0}
                for r in (1, 2, 3)
            ]
        )
        await pilot.pause()
        await pilot.pause()
        assert widget.query_one("#ttt-leaderboard-table", DataTable).row_count == 3


@pytest.mark.parametrize("hostile", HOSTILE_NAMES)
async def test_cattown_leaderboard_survives_hostile_basenames(hostile: str) -> None:
    from maxpane_dashboard.widgets.cattown.ct_leaderboard import CTLeaderboard

    widget = CTLeaderboard()
    async with _Harness(widget).run_test() as pilot:
        widget.update_data(
            [
                {"rank": r, "display_name": hostile, "fish_species": hostile,
                 "fish_weight_kg": 1.0, "rarity": "Common"}
                for r in (1, 2, 3)
            ]
        )
        await pilot.pause()
        await pilot.pause()
        assert widget.query_one("#ct-leaderboard-table", DataTable).row_count == 3


@pytest.mark.parametrize("hostile", HOSTILE_NAMES)
async def test_base_leaderboard_survives_hostile_symbols(hostile: str) -> None:
    from maxpane_dashboard.widgets.base.overview.bt_overview_leaderboard import (
        BTOverviewLeaderboard,
    )

    widget = BTOverviewLeaderboard()
    async with _Harness(widget).run_test() as pilot:
        widget.update_data(
            [
                {"symbol": hostile, "price_usd": 1.0, "price_change_24h": 1.0,
                 "volume_24h": 100.0, "liquidity_usd": 100.0}
                for _ in range(3)
            ]
        )
        await pilot.pause()
        await pilot.pause()
        assert widget.query_one("#bto-lb-table", DataTable).row_count == 3


@pytest.mark.parametrize("hostile", HOSTILE_NAMES)
async def test_bakery_activity_feed_survives_hostile_event_text(hostile: str) -> None:
    """RichLog(markup=True) defers rendering to on_resize -- same crash class."""
    from maxpane_dashboard.widgets.activity_feed import ActivityFeed

    widget = ActivityFeed()
    async with _Harness(widget).run_test() as pilot:
        widget.update_data(
            [
                ActivityEvent(
                    type="rug",
                    title=hostile,
                    description=hostile,
                    launcher="0x" + "1" * 40,
                    timestamp="1700000000",
                    boost_type_name=None,
                    boost_multiplier_bps=None,
                    boost_duration=None,
                    is_shield=None,
                    is_outgoing=True,
                    success=True,
                    linked_bakery_id=None,
                    linked_bakery_name=hostile,
                )
            ]
        )
        await pilot.pause()
        await pilot.pause()


async def test_cookie_chart_survives_hostile_bakery_names() -> None:
    from maxpane_dashboard.widgets.cookie_chart import CookieChart

    widget = CookieChart()
    async with _Harness(widget).run_test() as pilot:
        widget.update_data({name: [(0, 1.0), (1, 2.0)] for name in HOSTILE_NAMES})
        await pilot.pause()
        await pilot.pause()


async def test_hero_metrics_survives_hostile_leader_name() -> None:
    from maxpane_dashboard.widgets.hero_metrics import HeroMetrics

    widget = HeroMetrics()
    async with _Harness(widget).run_test() as pilot:
        widget.update_data(
            prize_pool_eth=1.0,
            prize_pool_usd=1000.0,
            hours_remaining=48.0,
            season_id=1,
            season_active=True,
            leader_name="[/x] Bakers",
            leader_cookies=1000.0,
            leader_rate=1.0,
        )
        await pilot.pause()
        await pilot.pause()


# -- Branch 2 (docs/refactor_programme_2026_09.md): TAG_LIKE / flatten /
# strip_tags / sanitize_cell, hoisted out of widgets/surf/launchpad.py,
# launchpad_activity.py, burnkeepers.py and _pool4.py -------------------
#
# These four names formerly lived as four separate private copies (one per
# module above); this section is the contract the hoist has to satisfy
# rather than a copy of any one module's own tests.


class _RaisingStr:
    """An object whose ``__str__`` raises -- ``flatten``/``strip_tags``/
    ``sanitize_cell`` must degrade rather than propagate the exception, the
    same "a single malformed value must never take down the panel" rule
    every calling widget already holds itself to.
    """

    def __str__(self) -> str:  # pragma: no cover - exercised via flatten etc.
        raise RuntimeError("boom")


def test_sanitize_cell_clips_before_it_escapes():
    """The order inside :func:`sanitize_cell` does not commute.

    Escaping first and clipping after can cut the ``\\[`` escape pair that
    :func:`safe_markup` writes for a surviving bracket in half at the cell
    boundary -- the user then sees a literal backslash and the ``[`` is
    gone. Fixture: eight filler characters, then the nested-bracket shape
    that one ``TAG_LIKE`` pass reduces to ``[/word]``; a 10-cell budget
    lands the cut right on the escape.
    """
    result = sanitize_cell("xxxxxxxx[[inner]/word]", 10)
    assert result == "xxxxxxxx[…", result          # escape-then-clip gives 'xxxxxxxx\\…'
    assert Text.from_markup(result).plain == "xxxxxxxx[…"


def test_tag_like_matches_a_complete_bracket_run_only():
    """A well-formed style tag and a bare close both match; an unmatched
    ``[`` with no closing bracket does not. (It does not need to: the
    installed Rich renders a lone ``[`` literally. What :func:`safe_markup`
    still catches in :func:`sanitize_cell` is the nested-bracket shape a
    single ``TAG_LIKE`` pass reduces to a bare close -- see
    ``test_sanitize_cell_escapes_what_tag_like_cannot_strip_in_one_pass``.)
    """
    assert TAG_LIKE.fullmatch("[bold red]")
    assert TAG_LIKE.fullmatch("[/x]")
    assert TAG_LIKE.sub("", "before [/x] after") == "before  after"
    assert not TAG_LIKE.search("[unclosed")


def test_flatten_none_is_empty_string():
    assert flatten(None) == ""


def test_flatten_collapses_embedded_newlines():
    assert flatten("line one\nline two\r\nline three") == "line one line two line three"


def test_flatten_never_raises_on_a_non_string():
    assert flatten(42) == "42"
    assert flatten({"a": 1}) == "{'a': 1}"
    assert flatten(_RaisingStr()) == ""


def test_strip_tags_none_is_empty_string():
    assert strip_tags(None) == ""


def test_strip_tags_collapses_embedded_newlines():
    assert "\n" not in strip_tags("a\nb\r\nc")


def test_strip_tags_removes_a_complete_bracket_run():
    """A well-formed ``[/x]`` run is stripped outright, not merely escaped --
    an *escaped* ``[/x]`` still renders as the literal text ``[/x]`` once
    Rich unescapes it for display (the rationale carried in ``launchpad.py``'s
    module docstring and ``_pool4.strip_tags``).
    """
    assert strip_tags("[/x] Bakers") == "Bakers"
    assert strip_tags("[bold red]pwn[/]") == "pwn"


def test_strip_tags_never_raises_on_a_non_string():
    assert strip_tags(42) == "42"
    assert strip_tags(_RaisingStr()) == ""


def test_sanitize_cell_none_is_empty_string():
    assert sanitize_cell(None, 10) == ""


def test_sanitize_cell_clips_on_cells_not_characters():
    """Eight CJK characters are sixteen columns -- a ``len()``-sized clip
    would let all eight through a ten-column budget. Measured on
    ``rich.cells.cell_len``, the mutation this hoist exists to prevent
    (see the module docstring on ``widgets/rowfit.clip``).
    """
    wide = "海豚" * 4
    result = sanitize_cell(wide, width=10)
    assert cell_len(result) <= 10
    assert result.endswith("…")


def test_sanitize_cell_escapes_what_tag_like_cannot_strip_in_one_pass():
    """``TAG_LIKE.sub`` runs a single left-to-right pass, so a *nested*
    bracket can make it delete an inner pair and leave the outer fragments
    sitting next to each other, reconstructing a hostile closing tag it
    never matched as such: ``"[[inner]/word]"`` strips to ``"[/word]"`` --
    exactly the "closing tag matching no open tag" shape that raises
    ``rich.errors.MarkupError`` when parsed unescaped (proven directly below,
    not assumed -- and it is the reconstructed leftover that bites, not the
    raw fixture: a truly bare, unmatched ``[`` with nothing else around it
    never reaches ``Text.from_markup`` as anything but literal text,
    verified empirically against this repo's live Rich version, so it is
    not what this step exists to catch).

    :func:`safe_markup` is the net that keeps the reconstructed tag from
    reaching ``Text.from_markup`` unescaped: the plain text must still
    contain the literal ``[``, and parsing the escaped result must not
    raise.
    """
    from rich.errors import MarkupError
    from rich.text import Text

    hostile = "[[inner]/word]"
    leftover = TAG_LIKE.sub("", hostile)
    assert leftover == "[/word]"
    with pytest.raises(MarkupError):
        Text.from_markup(leftover)  # the control: the leftover alone bites

    result = sanitize_cell(hostile, width=40)
    assert "[" in result
    parsed = Text.from_markup(result)  # must not raise
    assert "[" in parsed.plain


def test_sanitize_cell_strips_a_complete_run_before_clipping():
    assert sanitize_cell("[/x] Bakers", width=40) == "Bakers"


def test_sanitize_cell_never_raises_on_a_non_string():
    assert sanitize_cell(42, width=10) == "42"
    assert isinstance(sanitize_cell({"a": 1}, width=10), str)
    assert sanitize_cell(_RaisingStr(), width=10) == ""


@pytest.mark.parametrize(
    ("markup", "expected"),
    [
        ("[bold]x[/]", 1),
        ("[/x]", 0),
        ("a[b", 3),
        ("[x/y]", 0),
        ("plain", 5),
        ("[[a]b]", 3),
    ],
)
def test_visible_len_is_unchanged_by_the_tag_pattern_alias(markup, expected):
    """``docs/handover_followups_2026_09.md`` #9 (Branch 3): ``visible_len``
    used to measure with its own ``\\[/?[^\\[\\]]*\\]`` and now measures with
    :data:`TAG_LIKE`. The expected values are literals computed from the
    *old* pattern before the alias was made, so this reddens if the two
    languages ever were -- or ever become -- different on a closing tag, an
    unclosed bracket, a slash inside a tag or a nested bracket run.
    """
    assert visible_len(markup) == expected


# Controls are removed before fitting/Rich parsing; flatten preserves word boundaries.
CONTROL_PAYLOAD = "ok\x1b]0;PWNED\x07\x1b[31mred\x00\x9b"
CONTROL_REMAINDER = "ok]0;PWNED[31mred"


@pytest.mark.parametrize("helper", ["strip_controls", "flatten", "safe_markup", "strip_tags", "sanitize_cell"])
@pytest.mark.parametrize("control", [chr(n) for n in (*range(32), *range(127, 160)) if n not in (9, 10)])
def test_helpers_drop_controls(helper, control):
    from maxpane_dashboard.widgets import markup_safety

    fn = getattr(markup_safety, helper)
    value = "a" + control + "b"
    result = fn(value, 100) if helper == "sanitize_cell" else fn(value)
    whitespace = control in "\r\v\f\x85\x1c\x1d\x1e\x1f"
    expected = "a b" if whitespace and helper in ("flatten", "strip_tags", "sanitize_cell") else "ab"
    assert result == expected


def test_strip_controls_keeps_newlines_tabs_and_format_characters():
    from maxpane_dashboard.widgets import markup_safety

    value = "海豚 👩\u200d💻\n\t\u202e\u2066"
    assert markup_safety.strip_controls(value) == value


@pytest.mark.parametrize("helper", [flatten, safe_markup, strip_tags, lambda s: sanitize_cell(s, 100)])
def test_helpers_preserve_cjk_and_zwj(helper):
    assert helper("海豚 👩\u200d💻") == "海豚 👩\u200d💻"


async def test_flatten_static_drops_controls():
    from textual.widgets import Static

    async with _Harness(Static(Text(flatten(CONTROL_PAYLOAD + "A\x85B [/x]")))).run_test() as pilot:
        await pilot.pause()
        output = "\n".join(strip.text for strip in pilot.app.screen._compositor.render_strips())
        assert not any(c in output for c in ("\x1b", "\x00", "\x9b"))
        assert CONTROL_REMAINDER + "A B [/x]" in output


@pytest.mark.parametrize("sink", ["address-label", "address-prose", "hash-fallback", "surf-counterparty", "bakery", "cattown", "ocm", "ttt-burn", "fwa-token", "fwa-signal", "curator-title"])
async def test_literal_text_sinks_drop_controls(sink):
    from types import SimpleNamespace
    from textual.widgets import Static
    from maxpane_dashboard.widgets.address import address_prose, hash_text
    from maxpane_dashboard.widgets.surf.activity import _row_text as surf_activity
    from maxpane_dashboard.widgets.activity_feed import _event_to_text as bakery
    from maxpane_dashboard.widgets.cattown.ct_activity_feed import _catch_to_text
    from maxpane_dashboard.widgets.ocm.ocm_activity_feed import _event_to_text as ocm
    from maxpane_dashboard.widgets.ttt.ttt_activity_feed import _fmt_burn
    from maxpane_dashboard.widgets.fwa.fwa_activity_feed import _what_cell
    from maxpane_dashboard.widgets.fwa.fwa_signals import _fmt_drift
    from maxpane_dashboard.widgets.curator.list_hero import _wallet_text

    payload = CONTROL_PAYLOAD
    factories = {
        "address-label": lambda: address_text(None, label=payload),
        "address-prose": lambda: address_prose(payload),
        "hash-fallback": lambda: hash_text(payload, 100),
        "surf-counterparty": lambda: surf_activity({"counterparty_known": True, "counterparty": payload, "kind": "transfer", "value_eth": 1}, "full", 180, 10, True),
        "bakery": lambda: bakery(SimpleNamespace(type="simple", title=payload)),
        "cattown": lambda: _catch_to_text({"species": payload}),
        "ocm": lambda: ocm({"event_type": payload}),
        "ttt-burn": lambda: _fmt_burn({"token_id": payload}, "00:00", "TOK"),
        "fwa-token": lambda: _what_cell({"token_id": payload}, 100),
        "fwa-signal": lambda: _fmt_drift({"value_str": payload}, {}, 150),
        "curator-title": lambda: _wallet_text({"you_ens": payload}, "full"),
    }
    async with _Harness(Static(factories[sink]())).run_test(size=(180, 12)) as pilot:
        await pilot.pause()
        output = "\n".join(strip.text for strip in pilot.app.screen._compositor.render_strips())
        assert not any(c in output for c in ("\x1b", "\x00", "\x9b"))
        assert CONTROL_REMAINDER in output


async def test_base_token_symbol_drops_controls():
    from maxpane_dashboard.widgets.base.overview.bt_overview_leaderboard import BTOverviewLeaderboard
    from tests.widgets.surf_compositing import composite_lines

    output = "\n".join(await composite_lines(BTOverviewLeaderboard, (180, 12),
        trending_tokens=[{"symbol": CONTROL_PAYLOAD}]))
    assert not any(c in output for c in ("\x1b", "\x00", "\x9b"))
    assert "ok]0;PWNE…" in output  # the existing ten-cell label budget


async def test_curator_wallet_facts_drop_controls():
    from maxpane_dashboard.widgets.curator.wallet import CuratorWalletAddress
    from tests.widgets.surf_compositing import composite_lines

    output = "\n".join(await composite_lines(CuratorWalletAddress, (180, 12),
        you_address="0x" + "12" * 20, you_ens=CONTROL_PAYLOAD))
    assert not any(c in output for c in ("\x1b", "\x00", "\x9b"))
    assert CONTROL_REMAINDER in output


async def test_surf_feed_row_drops_controls():
    from textual.widgets import Static
    from maxpane_dashboard.widgets.surf.feed import _row_text

    row, _ = _row_text({"kind": "announce", "text": CONTROL_PAYLOAD}, 180)
    async with _Harness(Static(row)).run_test(size=(180, 12)) as pilot:
        await pilot.pause()
        output = "\n".join(strip.text for strip in pilot.app.screen._compositor.render_strips())
        assert not any(c in output for c in ("\x1b", "\x00", "\x9b"))
        assert CONTROL_REMAINDER in output


async def test_surf_signal_with_address_drops_controls():
    from textual.widgets import Static
    from maxpane_dashboard.widgets.surf.signals import _signal_row_content

    content = _signal_row_content("SIGNAL", "fired", CONTROL_PAYLOAD + " 0x" + "12" * 20, 0, 180)
    async with _Harness(Static(content)).run_test(size=(180, 12)) as pilot:
        await pilot.pause()
        output = "\n".join(strip.text for strip in pilot.app.screen._compositor.render_strips())
        assert not any(c in output for c in ("\x1b", "\x00", "\x9b"))
        assert CONTROL_REMAINDER in output


async def test_fwa_crown_rank_drops_controls():
    from maxpane_dashboard.widgets.fwa.fwa_settlement_table import FWASettlementTable
    from tests.widgets.surf_compositing import composite_lines

    output = "\n".join(await composite_lines(FWASettlementTable, (180, 20),
        crown_history=[{"rank": "1\x1b\x00\x9b", "holder": "0x" + "12" * 20}], settle_available=True))
    assert not any(c in output for c in ("\x1b", "\x00", "\x9b"))
    assert "1. " in output


def test_flatten_collapses_whitespace_before_stripping_controls():
    assert flatten("line one\rline two\vline three\fline four\x85line five\x1cline six\x1dline seven\x1eline eight\x1fline nine\x00!") == (
        "line one line two line three line four line five line six line seven line eight line nine!"
    )
