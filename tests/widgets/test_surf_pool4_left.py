"""WP5 -- the pool4 left column: ``SurfPool4Flow`` and ``SurfPool4Split``.

Every layout assertion here goes against **composited output**
(``screen._compositor.render_strips()``), joining segments per *row* first and
then rows by newline: joining every segment with a newline splits one painted
row into several apparent lines the moment a row carries two styles, and a
test written that way passes while the user sees something else.

Two things this file exists to pin above all others:

1. **A buy's zero legs are zeros, and a dead panel is not.** The three states
   (``None`` / ``[]`` / a buy row) must produce three different composited
   texts. This is the FARM-vs-HOUR-SAVED defect CLAUDE.md records, and it is
   the single most likely way this panel ships wrong.
2. **No row is ever silently narrowed.** ``RichLog(wrap=False)`` shrinks a
   too-wide line at write time with no ``…`` and no marker, so a row is either
   fitted or withheld -- never cut.
"""

from __future__ import annotations

import ast
import inspect
import pathlib
import re

import pytest
from rich.cells import cell_len
from textual.app import App

from maxpane_dashboard.data.surf_models import (
    POOL4_COUNTER_STATES,
    POOL4_REWARD_PATHS,
    POOL4_FLOW_LIMIT,
    POOL4_FLOW_SIDES,
    POOL4_KEYS,
    POOL4_NETWORKS,
    SURF_ROW_KEYS,
)
from maxpane_dashboard.widgets.surf import _pool4
from maxpane_dashboard.widgets.surf._fmt import DASH
from maxpane_dashboard.widgets.surf import pool4_flow as flow_mod
from maxpane_dashboard.widgets.surf import pool4_split as split_mod
from maxpane_dashboard.widgets.surf._pool4 import (
    NETWORK_UNKNOWN,
    TITLE_SEP,
    network_word,
    panel_title,
)
from maxpane_dashboard.widgets.surf.pool4_flow import (
    EMPTY_LINE,
    HEADER_CELLS,
    LEGEND_ACCRUED,
    SHORT_HINT,
    SIDE_WORDS,
    TITLE,
    UNAVAILABLE_LINE,
    SurfPool4Flow,
)
from maxpane_dashboard.widgets.surf.pool4_split import (
    DERIVED,
    DISTRIBUTOR_UNREAD,
    PATH_VIA_DISTRIBUTOR,
    REWARD_PATHS,
    LEG_WORD_STAKING,
    LEG_WORD_WHOLE,
    COUNTER_ALERT,
    COUNTER_NEVER,
    COUNTER_NOT_ESTABLISHED,
    COUNTER_NO_DETAIL,
    COUNTER_UNKNOWN,
    COUNTER_WORDS,
    DRIFT_ALERT,
    DRIFT_MATCH,
    DRIFT_UNREAD,
    SurfPool4Split,
)
from maxpane_dashboard.widgets.surf.pool4_split import TITLE as SPLIT_TITLE

# ---------------------------------------------------------------------------
# payloads -- shaped by the frozen contract, never by a live read
# ---------------------------------------------------------------------------

#: A settled sell: the hook split a fee, both legs paid.
SELL = {
    "ts": 1_756_000_000.0, "age_s": 120.0, "side": "sell", "size_imd": 1234.5,
    "burned_imd": 111.42, "stakers_imd": 12.38, "fee_imd": None,
    "fee_eth": 0.0057, "settled": True, "tx_hash": "0x" + "ab" * 32,
}

#: A buy. **No burn leg and no staker leg -- and those are zeros.**
BUY = {
    "ts": 1_755_999_000.0, "age_s": 420.0, "side": "buy", "size_imd": 987.65,
    "burned_imd": 0.0, "stakers_imd": 0.0, "fee_imd": 12.38, "fee_eth": None,
    "settled": True, "tx_hash": "0x" + "cd" * 32,
}

#: A sell whose ``ClaimsSettled`` has not fired yet: zero legs for a wholly
#: different reason from the buy's, which is why the row carries a flag.
ACCRUED = {
    "ts": 1_755_998_000.0, "age_s": 840.0, "side": "sell", "size_imd": 4500.0,
    "burned_imd": 0.0, "stakers_imd": 0.0, "fee_imd": None, "fee_eth": 0.0031,
    "settled": False, "tx_hash": "0x" + "ef" * 32,
}

ROWS = [SELL, BUY, ACCRUED]

#: A wei-exact mismatch detail of the shape the manager builds: which counter,
#: which sum, and by how much. Every token is 35 cells or fewer, so the width
#: sweep below exercises *wrapping*; the unbreakable-token path has its own
#: test.
COUNTER_DETAIL = (
    "totalBurned 102,030,338,541,400,000,000,000,000 wei vs "
    "sum(ClaimsSettled) 102,030,338,541,300,000,000,000,000 wei, "
    "short by 100,000,000,000 wei"
)

#: The live mainnet Distributor read (docs/imd_pool4_mainnet.md): stakingBps
#: and nftBps both 3000, bonding the 4000 remainder, and the earned/held
#: figures as they stood the day pool4 went live. ``nodes`` is the payload's
#: word for the chain's ``nft`` -- WP0's stated discipline, pinned in both
#: directions, and not to be "corrected" here.
DISTRIBUTOR_KW = {
    "pool4_distributor_staking_bps": 3000,
    "pool4_distributor_nodes_bps": 3000,
    "pool4_distributor_bonding_bps": 4000,
    "pool4_distributor_staking_earned": 3.1490,
    "pool4_distributor_nodes_earned": 3.1490,
    "pool4_distributor_bonding_earned": 4.1986,
    "pool4_distributor_held_nodes": 3.1490,
    "pool4_distributor_held_bonding": 4.1986,
}

SPLIT_KW = {
    "pool4_network": "SEPOLIA",
    "pool4_measured_inference_pct": 1.004,
    "pool4_measured_burn_pct": 89.102,
    "pool4_measured_stakers_pct": 9.894,
    "pool4_reward_share_bps": 990,
    "pool4_bps_denominator": 10_000,
    "pool4_split_drift_bps": 0.0,
    "pool4_total_burned": 102_030_338.5414,
    "pool4_total_rewarded": 1_234_567.25,
    "pool4_total_fee_token": 1_122_334.5,
    "pool4_retained_eth": 0.0,
    "pool4_last_claim_block": 8_123_456,
    "pool4_unsettled_burn": 0.0,
    "pool4_unsettled_stakers": 0.0,
    # ``direct``: Sepolia's shape, and the day-one path. The reward leg IS
    # the staker leg here, which is the fact the annotation states.
    "pool4_reward_path": "direct",
    "pool4_counter_state": "reconciled",
    "pool4_counter_detail": None,
    "pool4_as_of_hhmm": "14:32",
}


async def _lines(widget_cls, size, **kwargs) -> list[str]:
    """Composited output, **one string per painted terminal row**.

    Segments are joined per strip first. Joining them all with ``"\\n"``
    instead would break one styled row into several apparent lines, and every
    "which line is this on?" assertion below would be measuring a fiction.
    """
    class _A(App):
        def compose(self):
            yield widget_cls()

    async with _A().run_test(size=size) as pilot:
        widget = pilot.app.query_one(widget_cls)
        widget.update_data(**kwargs)
        await pilot.pause()
        strips = pilot.app.screen._compositor.render_strips()
        return ["".join(seg.text for seg in strip).rstrip() for strip in strips]


async def _flow(rows=None, size=(70, 24), **kwargs) -> tuple[list[str], str]:
    kwargs.setdefault("pool4_network", "SEPOLIA")
    lines = await _lines(SurfPool4Flow, size, pool4_flow=rows, **kwargs)
    return lines, "\n".join(lines)


async def _split(size=(70, 24), **overrides) -> tuple[list[str], str]:
    kwargs = dict(SPLIT_KW)
    kwargs.update(overrides)
    lines = await _lines(SurfPool4Split, size, **kwargs)
    return lines, "\n".join(lines)


def _index_of(lines: list[str], needle: str) -> int:
    for i, line in enumerate(lines):
        if needle in line:
            return i
    raise AssertionError(f"{needle!r} is on no composited line: {lines!r}")


# ---------------------------------------------------------------------------
# FLOW -- the load-bearing zero
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_flow_panel_renders_buys_sells_and_its_column_headings() -> None:
    _lines_, text = await _flow(ROWS)
    assert TITLE in text
    assert SIDE_WORDS["buy"] in text and SIDE_WORDS["sell"] in text
    for header in HEADER_CELLS.values():
        assert header in text


@pytest.mark.asyncio
async def test_a_buy_row_and_a_dead_panel_do_not_say_the_same_thing() -> None:
    """**The** test of this panel.

    A buy has no burn leg and no staker leg; those are *representable zeros*
    and render ``0.00``. ``None`` is reserved for the whole-panel unavailable
    state, which gets its own explicit line and no row at all. Curator's rail
    shipped the opposite -- FARM said ``-- unknown`` off a dead read while its
    two siblings, folded from the same dead group, said ``none yet``, so the
    panel read confident and green straight through an outage.
    """
    _l, buy = await _flow([BUY])
    _l, dead = await _flow(None)

    assert buy != dead

    assert "0.00" in buy
    assert UNAVAILABLE_LINE not in buy

    assert UNAVAILABLE_LINE in dead
    assert "0.00" not in dead
    assert SIDE_WORDS["buy"] not in dead


@pytest.mark.asyncio
async def test_a_quiet_sweep_and_a_dead_one_do_not_say_the_same_thing() -> None:
    """``[]`` is "we looked and there were no swaps"; ``None`` is "we could
    not look". Two different facts, so two different sentences.
    """
    _l, quiet = await _flow([])
    _l, dead = await _flow(None)

    assert quiet != dead
    assert EMPTY_LINE in quiet and UNAVAILABLE_LINE not in quiet
    assert UNAVAILABLE_LINE in dead and EMPTY_LINE not in dead


@pytest.mark.asyncio
async def test_a_buys_zero_legs_render_as_zero_and_never_as_a_dash() -> None:
    """Asserted on the buy's own composited *line*, not on the panel text: a
    dash elsewhere on the panel would let a whole-panel check pass while the
    legs themselves read ``--``.
    """
    lines, _text = await _flow([BUY])
    row = lines[_index_of(lines, SIDE_WORDS["buy"])]
    assert row.count("0.00") == 2       # the burn leg and the staker leg
    assert "--" not in row


@pytest.mark.asyncio
async def test_an_unread_leg_is_a_dash_and_not_a_zero() -> None:
    """The mirror image, and it is what makes the test above bite: a
    formatter that rendered *everything* as ``0.00`` would satisfy the zero
    check while erasing the difference between a buy and a broken decode.
    """
    broken = dict(BUY)
    broken.pop("burned_imd")
    lines, _text = await _flow([broken])
    row = lines[_index_of(lines, SIDE_WORDS["buy"])]
    assert "--" in row
    assert row.count("0.00") == 1       # the staker leg is still a real zero


@pytest.mark.asyncio
async def test_an_accrued_sell_is_flagged_and_the_flag_is_spelled_out() -> None:
    """A sell that has not settled carries ``0.00`` legs too -- a true zero
    for a completely different reason. Without the flag and its legend, "the
    hook took nothing" and "the hook has not paid out yet" are the same three
    characters on screen.
    """
    _l, accrued = await _flow([ACCRUED])
    _l, settled = await _flow([SELL])

    assert LEGEND_ACCRUED in accrued
    assert LEGEND_ACCRUED not in settled
    assert f'{SIDE_WORDS["sell"]}~' in accrued
    assert f'{SIDE_WORDS["sell"]}~' not in settled


@pytest.mark.asyncio
async def test_the_fee_cell_names_the_currency_the_fee_was_taken_in() -> None:
    _l, eth_fee = await _flow([SELL])
    _l, imd_fee = await _flow([BUY])
    assert "ETH" in eth_fee and "IMD" not in eth_fee
    assert "IMD" in imd_fee and "ETH" not in imd_fee


@pytest.mark.asyncio
async def test_a_zero_fee_is_a_number_and_two_unread_legs_are_a_dash() -> None:
    """``_fee_cell`` tests ``is not None``, never truthiness. A fee of exactly
    zero is a read that succeeded, and ``not 0.0`` would print a dash over it.
    """
    zero_fee = dict(SELL, fee_imd=0.0, fee_eth=None)
    unread = dict(SELL, fee_imd=None, fee_eth=None)

    lines, _t = await _flow([zero_fee])
    assert "0.00 IMD" in lines[_index_of(lines, SIDE_WORDS["sell"])]

    lines, _t = await _flow([unread])
    row = lines[_index_of(lines, SIDE_WORDS["sell"])]
    assert "IMD" not in row and "ETH" not in row and "--" in row


# ---------------------------------------------------------------------------
# FLOW -- the network word
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_panel_title_never_goes_networkless() -> None:
    """On the day this ships there is no mainnet pool4 deployment, so the
    numbers on screen are testnet numbers -- and a testnet number on an
    unmarked panel is not merely stale, it is fictional presented as live
    (implementation plan §5 R4). The word is in the title, not a footnote.
    """
    for network in POOL4_NETWORKS:
        _l, text = await _flow(ROWS, pool4_network=network)
        assert f"{TITLE}{TITLE_SEP}{network}" in text

    _l, text = await _flow(ROWS, pool4_network=None)
    assert f"{TITLE}{TITLE_SEP}{NETWORK_UNKNOWN}" in text

    # ...and it survives every payload state, including the dead one.
    _l, dead = await _flow(None, pool4_network="SEPOLIA")
    assert f"{TITLE}{TITLE_SEP}SEPOLIA" in dead


@pytest.mark.asyncio
async def test_an_unrecognised_network_is_never_laundered_into_either_title() -> None:
    """The allowlist, asserted where a reader meets it: **on both panels**.

    ``_pool4`` owns the vocabulary and ``test_surf_pool4_shared.py`` owns the
    both-directions agreement with ``POOL4_NETWORKS``; what this asserts is
    that these two panels actually route their titles through it, end to end
    and against composited output. A module could import the allowlist and
    still print ``str(network)`` beside its own name.
    """
    assert network_word("BASE") == NETWORK_UNKNOWN     # the premise, stated

    _l, flow = await _flow(ROWS, pool4_network="BASE")
    _l, split = await _split(pool4_network="BASE")
    assert f"{TITLE}{TITLE_SEP}{NETWORK_UNKNOWN}" in flow
    assert f"{SPLIT_TITLE}{TITLE_SEP}{NETWORK_UNKNOWN}" in split
    assert "BASE" not in flow and "BASE" not in split


def test_the_title_helper_is_imported_and_not_copied() -> None:
    """Amendment A13 step 2, from this package's side.

    These two modules had a local ``panel_title`` for one wave, and WP4 wrote
    the same helper for the rail with the opposite behaviour on unknown input
    -- so one body could paint ``THE SPLIT · —`` beside ``THE RATCHET · BASE``.
    There is now one definition; this asserts these two panels use *that
    object*, not a same-named local, and that the name is gone from both
    sources. ``test_surf_pool4_shared.py`` runs the complementary sweep over
    every pool4 module, so between the two a fourth copy cannot appear
    quietly.
    """
    assert flow_mod.panel_title is _pool4.panel_title
    assert panel_title(SPLIT_TITLE, "MAINNET") == f"{SPLIT_TITLE}{TITLE_SEP}MAINNET"

    for module in (flow_mod, split_mod):
        tree = ast.parse(pathlib.Path(module.__file__).read_text())
        defined = {
            node.name
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        assert "panel_title" not in defined, module.__name__
        assert "network_word" not in defined, module.__name__


def test_the_widen_marker_is_the_shared_spelling_not_a_second_literal() -> None:
    """``SHORT_HINT`` is the name this family of ``RichLog`` panels uses --
    ``activity.py`` and ``launchpad_activity.py`` both export it -- and it is
    now an **alias** of ``_pool4.WIDEN_HINT`` rather than a fourth copy of the
    string. The rail's narrower ``GLYPH_HINT`` is a different marker and must
    not end up under this name.
    """
    assert SHORT_HINT is _pool4.WIDEN_HINT
    assert SHORT_HINT != _pool4.GLYPH_HINT


# ---------------------------------------------------------------------------
# FLOW -- the producer's own vocabularies and caps
# ---------------------------------------------------------------------------


def test_the_side_cell_fits_the_producers_whole_vocabulary() -> None:
    """Both directions: every member is renderable, and the cell is exactly
    the widest member plus its one flag column -- not a column more, not one
    less. A cell one short cuts a word silently; a cell one long is a gulf on
    every row.
    """
    assert set(SIDE_WORDS) == set(POOL4_FLOW_SIDES)
    widest = max(cell_len(word) for word in SIDE_WORDS.values())
    flag = max(cell_len(f) for f in flow_mod.SETTLED_FLAGS.values())
    assert flow_mod._SIDE_COLS == widest + flag
    assert cell_len(HEADER_CELLS["side"]) <= flow_mod._SIDE_COLS


def test_the_row_cap_matches_the_producers_own() -> None:
    assert flow_mod._MAX_ROWS == POOL4_FLOW_LIMIT


def test_the_fixture_rows_are_exactly_the_frozen_row_shape() -> None:
    """If these rows drift from ``SURF_ROW_KEYS["pool4_flow"]`` every
    assertion above is about a payload the manager will never send.
    """
    expected = set(SURF_ROW_KEYS["pool4_flow"])
    for row in ROWS:
        assert set(row) == expected


def test_the_split_signature_covers_its_share_of_the_contract() -> None:
    """The two panels' ``update_data`` kwargs are all ``pool4_``-prefixed
    contract keys -- no short ``as_of_hhmm`` alias, which is the departure
    from the launchpad panels §0.1 makes deliberately.
    """
    for method in (SurfPool4Flow.update_data, SurfPool4Split.update_data):
        names = [
            name
            for name, param in inspect.signature(method).parameters.items()
            if param.kind is param.KEYWORD_ONLY or (
                param.kind is param.POSITIONAL_OR_KEYWORD and name != "self"
            )
        ]
        assert names, method
        for name in names:
            assert name.startswith("pool4_"), name
            assert name in POOL4_KEYS, name
        assert any(
            p.kind is p.VAR_KEYWORD
            for p in inspect.signature(method).parameters.values()
        ), method


# ---------------------------------------------------------------------------
# FLOW -- width, in both directions
# ---------------------------------------------------------------------------


def test_the_row_fit_ladder_is_imported_and_not_copied() -> None:
    """CLAUDE.md records this helper existing three times in this package and
    the ``len()``-vs-``cell_len()`` bug therefore needing three fixes. WP2
    hoisted it so this panel would be the first consumer that does not make a
    fourth copy, so the import is asserted rather than assumed.
    """
    source = pathlib.Path(flow_mod.__file__).read_text()
    assert "from maxpane_dashboard.widgets.surf import _rowfit" in source
    for helper in ("row_cols", "tier_for", "clip", "pad"):
        assert f"def {helper}(" not in source, helper
        assert f"_rowfit.{helper}" in source, helper


def test_the_tier_ladder_steps_in_both_directions() -> None:
    """The pure half of the ladder, asserted at each threshold *and one column
    below it*. A one-directional width test would have missed the defect that
    shipped here before.
    """
    cols = (4, 6, 6, 7, 12)
    full = flow_mod._row_cols("full", cols)
    compact = flow_mod._row_cols("compact", cols)
    minimal = flow_mod._row_cols("minimal", cols)
    assert full > compact > minimal

    assert flow_mod._tier_for(full, cols) == "full"
    assert flow_mod._tier_for(full - 1, cols) == "compact"
    assert flow_mod._tier_for(compact, cols) == "compact"
    assert flow_mod._tier_for(compact - 1, cols) == "minimal"
    assert flow_mod._tier_for(minimal, cols) == "minimal"
    # Not laid out yet: optimistic, then ``on_resize`` re-lays it out.
    assert flow_mod._tier_for(0, cols) == "full"


def test_the_column_budget_is_measured_not_assumed() -> None:
    """A nine-figure burn makes the burn column wider than its header, and the
    tier requirement has to grow with it. Sizing from a constant is the defect
    ``launchpad_activity``'s ``_AMOUNT_COLS`` records: the cell was one column
    short and the difference came off the end of the line unannounced.
    """
    small = [f for f in [flow_mod._row_fields(SELL)] if f]
    huge = [f for f in [flow_mod._row_fields(dict(SELL, burned_imd=1.2345e12))] if f]
    assert flow_mod._batch_cols(huge)[2] > flow_mod._batch_cols(small)[2]
    assert (
        flow_mod._row_cols("full", flow_mod._batch_cols(huge))
        > flow_mod._row_cols("full", flow_mod._batch_cols(small))
    )


@pytest.mark.asyncio
async def test_whenever_a_column_is_shed_the_title_says_so() -> None:
    """A **property**, swept across the whole reachable width band rather than
    pinned to a literal threshold: whenever the inference column is missing, a
    widen marker is lit; whenever it is present, none is. The literal would go
    stale silently the first time a column width moved.

    Both states are asserted to actually occur in the sweep, or the property
    would hold vacuously and the test could never fail.
    """
    seen_full = seen_shed = False
    for width in range(24, 92, 2):
        _l, text = await _flow(ROWS, size=(width, 24))
        if HEADER_CELLS["fee"] in text:
            assert SHORT_HINT not in text, width
            seen_full = True
        else:
            assert SHORT_HINT in text, width
            seen_shed = True
    assert seen_full and seen_shed


@pytest.mark.asyncio
async def test_the_inference_column_boundary_reddens_from_both_sides() -> None:
    """The measured boundary itself: the narrowest terminal that still carries
    the inference column, and the one column below it. Measured, never quoted
    -- and re-measured on every run, so it cannot agree with a stale constant
    by construction.
    """
    boundary = None
    for width in range(24, 92):
        _l, text = await _flow(ROWS, size=(width, 24))
        if HEADER_CELLS["fee"] in text:
            boundary = width
            break
    assert boundary is not None

    _l, at = await _flow(ROWS, size=(boundary, 24))
    _l, below = await _flow(ROWS, size=(boundary - 1, 24))
    assert HEADER_CELLS["fee"] in at and SHORT_HINT not in at
    assert HEADER_CELLS["fee"] not in below and SHORT_HINT in below


@pytest.mark.asyncio
async def test_a_row_wider_than_the_log_is_withheld_or_fitted_never_shrunk() -> None:
    """``RichLog(wrap=False)`` narrows a too-wide line at write time with no
    ``…``, no marker and nothing in the title -- so a cut number arrives
    looking like a whole one.

    The row here carries a nine-figure ETH fee, far wider than any tier at a
    narrow terminal. At every width the panel must either show the fee string
    **whole** or show no rows at all and say ``‹ widen``; a partial ``123,456``
    with its tail gone is the failure.
    """
    fee = 123_456_789.1234
    whale = dict(SELL, fee_imd=None, fee_eth=fee)
    rendered = f"{fee:,.4f} ETH"

    saw_withheld = saw_whole = False
    for width in range(20, 80, 2):
        _l, text = await _flow([whale], size=(width, 24))
        if SIDE_WORDS["sell"] in text:
            # A row was rendered, so its inference cell -- if the tier carries
            # one at all -- must be intact.
            if "ETH" in text:
                assert rendered in text, width
                saw_whole = True
        else:
            assert SHORT_HINT in text, width
            assert rendered.split(".")[0] not in text, width
            saw_withheld = True
    assert saw_withheld and saw_whole


# ---------------------------------------------------------------------------
# FLOW -- hostile input and the no-arg contract
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_hostile_row_never_reaches_markup() -> None:
    """A persisted cache file is third-party input too (CLAUDE.md, the curator
    ``pattern_language`` precedent), so a hand-edited row can carry anything.

    Rendered beside a well-formed neighbour, and the neighbour is asserted --
    "it did not crash" alone is satisfied by a panel that ate every row.
    """
    hostile = dict(BUY, side="[/x]")
    hostile_side = dict(SELL, settled="[$warning]")
    _l, text = await _flow([hostile, hostile_side, SELL])
    assert SIDE_WORDS["sell"] in text
    assert "[/x]" not in text


@pytest.mark.asyncio
async def test_a_hostile_as_of_marker_is_stripped_and_not_merely_escaped() -> None:
    """An *escaped* ``[/x]`` still paints the literal text ``[/x]`` once Rich
    unescapes it for display, so escaping alone stops the crash and not the
    bracket noise. Both panels run the marker through ``_pool4.strip_tags``
    first.
    """
    _l, text = await _flow(ROWS, pool4_as_of_hhmm="[/x]14:32")
    assert SIDE_WORDS["sell"] in text
    assert "14:32" in text
    assert "[/x]" not in text


@pytest.mark.asyncio
async def test_both_panels_render_with_no_arguments_at_all() -> None:
    """§0.4: no required constructor argument and ``**_kwargs`` mandatory, so
    the screen can compose them bare and splat a payload that has grown a key
    they do not know.
    """
    for widget_cls in (SurfPool4Flow, SurfPool4Split):
        class _A(App):
            def compose(self):
                yield widget_cls()

        async with _A().run_test(size=(70, 24)) as pilot:
            widget = pilot.app.query_one(widget_cls)
            widget.update_data()
            widget.update_data(a_key_from_the_future=object())
            await pilot.pause()


@pytest.mark.asyncio
async def test_a_non_list_payload_degrades_to_the_quiet_state() -> None:
    _l, text = await _flow(12345)
    assert EMPTY_LINE in text


# ---------------------------------------------------------------------------
# SPLIT
# ---------------------------------------------------------------------------


def test_no_researched_split_is_quoted_in_the_module_source() -> None:
    """The whole point of the panel: the split is **measured live**, never
    quoted from research. CLAUDE.md records a protocol documenting a 5% fee
    that is 1% on chain -- a number typed into a widget cannot drift with the
    chain, so none is.
    """
    source = pathlib.Path(split_mod.__file__).read_text()
    for pattern in (r"89\.1", r"9\.9", r"1\.0"):
        assert not re.search(pattern, source), pattern


@pytest.mark.asyncio
async def test_the_measured_shares_come_from_the_payload_and_move_with_it() -> None:
    """Not merely "the number appears" -- a hardcoded panel would pass that.
    A *different* payload must render *different* numbers.
    """
    _l, a = await _split(
        pool4_measured_inference_pct=1.004,
        pool4_measured_burn_pct=89.102,
        pool4_measured_stakers_pct=9.894,
    )
    assert "1.00%" in a and "89.10%" in a and "9.89%" in a

    _l, b = await _split(
        pool4_measured_inference_pct=2.5,
        pool4_measured_burn_pct=70.25,
        pool4_measured_stakers_pct=27.25,
    )
    assert "2.50%" in b and "70.25%" in b and "27.25%" in b
    assert "89.10%" not in b


@pytest.mark.asyncio
async def test_a_zero_drift_is_a_number_and_an_unread_one_is_not() -> None:
    """``0.0`` is the healthy value and renders as such, not as a dash --
    otherwise a passing cross-check reads as a missing read. ``None`` is the
    missing read, and it shares no sentence with either confident answer.
    """
    _l, healthy = await _split(pool4_split_drift_bps=0.0)
    _l, unread = await _split(pool4_split_drift_bps=None)

    assert "drift 0.00 bps" in healthy and DRIFT_MATCH in healthy
    assert DRIFT_UNREAD not in healthy and DRIFT_ALERT not in healthy

    assert DRIFT_UNREAD in unread
    assert "drift 0.00 bps" not in unread and DRIFT_ALERT not in unread
    assert healthy != unread


@pytest.mark.asyncio
async def test_a_non_zero_drift_is_the_most_prominent_thing_on_the_panel() -> None:
    """A disagreement between what the hook claims and what the chain did is
    the most important thing this panel can say, so it is also the first --
    above the measured shares themselves. When the drift is healthy it sits
    below them, which is what makes the ordering assertion bite.
    """
    lines, drifting = await _split(pool4_split_drift_bps=-12.4)
    assert DRIFT_ALERT in drifting
    assert "-12.40 bps" in drifting
    assert "below" in drifting
    assert _index_of(lines, DRIFT_ALERT) < _index_of(lines, "measured inference")

    lines, healthy = await _split(pool4_split_drift_bps=0.0)
    assert _index_of(lines, "drift 0.00") > _index_of(lines, "measured inference")

    lines, above = await _split(pool4_split_drift_bps=7.5)
    assert "+7.50 bps" in "\n".join(lines)
    assert "above" in "\n".join(lines)


@pytest.mark.asyncio
async def test_the_drift_line_is_styled_apart_when_it_is_alarming() -> None:
    """Position alone is not prominence: the alarming line is also the only
    one on the panel that is not muted. Asserted on the compositor's own
    segment styles rather than on the content string.
    """
    class _A(App):
        def compose(self):
            yield SurfPool4Split()

    async with _A().run_test(size=(70, 24)) as pilot:
        widget = pilot.app.query_one(SurfPool4Split)
        widget.update_data(**dict(SPLIT_KW, pool4_split_drift_bps=-12.4))
        await pilot.pause()
        strips = pilot.app.screen._compositor.render_strips()
        styles = [
            seg.style
            for strip in strips
            for seg in strip
            if DRIFT_ALERT in seg.text and seg.style is not None
        ]
        assert styles, "the drift line reached no compositor segment"
        assert any(style.bold for style in styles)


@pytest.mark.asyncio
async def test_the_split_title_never_goes_networkless() -> None:
    for network in POOL4_NETWORKS:
        _l, text = await _split(pool4_network=network)
        assert f"{SPLIT_TITLE}{TITLE_SEP}{network}" in text
    _l, text = await _split(pool4_network=None)
    assert f"{SPLIT_TITLE}{TITLE_SEP}{NETWORK_UNKNOWN}" in text


@pytest.mark.asyncio
async def test_settled_up_to_date_renders_as_zero_and_unread_as_a_dash() -> None:
    """``pool4_unsettled_burn == 0.0`` means "settled up to date" -- a fact
    about the hook, not a missing read.
    """
    lines, _t = await _split(pool4_unsettled_burn=0.0, pool4_unsettled_stakers=0.0)
    row = lines[_index_of(lines, "unsettled burn")]
    assert "0.00" in row and "--" not in row

    lines, _t = await _split(pool4_unsettled_burn=None)
    assert "--" in lines[_index_of(lines, "unsettled burn")]


@pytest.mark.asyncio
async def test_a_zero_retained_balance_is_a_number_not_a_dash() -> None:
    """``retainedEth()`` reads zero because the owner has withdrawn everything
    ever collected -- a cumulative counter beside a current balance, not a
    failed read (plan amendment A9).
    """
    lines, _t = await _split(pool4_retained_eth=0.0)
    assert "0.0000 ETH" in lines[_index_of(lines, "retained")]

    lines, _t = await _split(pool4_retained_eth=None)
    assert "--" in lines[_index_of(lines, "retained")]


@pytest.mark.asyncio
async def test_every_unread_counter_is_a_dash_and_the_panel_still_paints() -> None:
    """The cold payload: nothing has landed. Every value is a dash, no value
    is a zero, and the panel is still a complete frame.
    """
    lines = await _lines(SurfPool4Split, (70, 24))
    text = "\n".join(lines)
    assert SPLIT_TITLE in text
    assert f"{SPLIT_TITLE}{TITLE_SEP}{NETWORK_UNKNOWN}" in text
    assert "0.00 bps" not in text
    assert DRIFT_UNREAD in text


@pytest.mark.asyncio
async def test_a_pair_reflows_at_its_own_boundary_in_both_directions() -> None:
    """The tier ladder became a **per-group** fit, and this is where its
    boundary is still asserted from both sides.

    What moved is only *which* width sets it: it used to be the widest group
    on the whole panel, and it is now this group's own. The assertion is the
    same shape as before -- measure the boundary rather than quote it, then
    check the width at it and the width one below it -- and it still fails if
    either side stops behaving.

    Nothing is shed in either direction, so neither side advertises a marker:
    a reflow is not a loss.
    """
    def paired(lines):
        return any("burned" in line and "rewarded" in line for line in lines)

    boundary = None
    for width in range(30, 90):
        lines, _t = await _split(size=(width, 40))
        if paired(lines):
            boundary = width
            break
    assert boundary is not None

    wide, wide_text = await _split(size=(boundary, 40))
    narrow, narrow_text = await _split(size=(boundary - 1, 40))

    assert paired(wide), boundary
    assert not paired(narrow), boundary - 1
    assert SHORT_HINT not in wide_text and SHORT_HINT not in narrow_text
    for value in ("102,030,339", "1,234,567", "1,122,334", "8,123,456"):
        assert value in wide_text and value in narrow_text


@pytest.mark.asyncio
async def test_each_group_reflows_at_its_own_width_and_not_the_panels_widest() -> None:
    """The coverage the global tier could not express, and the reason the
    change was worth making.

    One threshold for the whole panel meant the **widest** group decided for
    all of them: at the rail's 48 columns ``unsettled`` needs 52, so it put
    ``burned · rewarded`` (46) and ``fees · retained`` (40) onto two lines
    each -- three rows spent because one group did not fit, in the column that
    binds the body's height pin.

    Asserted at a width where the two states must coexist: the narrow group is
    split and the two that fit are not.
    """
    lines, text = await _split(size=(50, 40))          # the rail's own width

    assert any("burned" in line and "rewarded" in line for line in lines)
    assert any("fees" in line and "retained" in line for line in lines)
    # ...and the group that does not fit is reflowed, not shed.
    assert not any("unsettled burn" in line and "unsettled stakers" in line
                   for line in lines)
    assert "unsettled burn" in text and "unsettled stakers" in text
    assert SHORT_HINT not in text


@pytest.mark.asyncio
async def test_the_counter_lines_do_not_move_the_pair_boundary() -> None:
    """Unchanged in intent from the version that measured the global tier: the
    counter control's state must not decide where an unrelated group reflows.

    It is a stronger claim now than it was, because the boundary it pins is
    the pair's own rather than a panel-wide threshold that the counter block
    could only have moved by being the widest thing on the panel.
    """
    async def boundary(**extra):
        for width in range(30, 90):
            lines, _t = await _split(size=(width, 40), **extra)
            if any("burned" in line and "rewarded" in line for line in lines):
                return width
        raise AssertionError("the pair never fitted on one line")

    quiet = await boundary(pool4_counter_state="reconciled")
    alarming = await boundary(
        pool4_counter_state="mismatch", pool4_counter_detail=COUNTER_DETAIL,
    )
    assert quiet == alarming, (quiet, alarming)


@pytest.mark.asyncio
async def test_a_panel_too_narrow_for_even_the_reflow_says_so() -> None:
    """Below the narrow layout the ``Static``'s CSS ellipsis starts cutting
    values, and a cut number is a wrong number. The marker is what stops that
    happening in silence.
    """
    _l, text = await _split(size=(34, 24))
    assert SHORT_HINT in text


@pytest.mark.asyncio
async def test_a_hostile_persisted_marker_never_reaches_markup() -> None:
    _l, text = await _split(pool4_as_of_hhmm="[/x]14:32")
    assert "14:32" in text
    assert "[/x]" not in text
    assert SPLIT_TITLE in text


# ---------------------------------------------------------------------------
# module boundaries (§0.5)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("module", [flow_mod, split_mod])
def test_the_pool4_left_widgets_import_no_data_analytics_or_clock(module) -> None:
    """§0.5 froze the boundary with the keys: these modules may see
    ``_fmt`` / ``_rowfit`` / ``markup_safety`` / ``sparkline_common`` and
    nothing from ``data/`` or ``analytics/``.

    ``time`` and ``datetime`` are on the list for their own reason: ``age_s``
    is precomputed by the manager, and a widget that read a clock would make
    every committed capture render differently tomorrow than it does today.
    """
    tree = ast.parse(pathlib.Path(module.__file__).read_text())
    seen: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            seen += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            seen.append(node.module)

    forbidden = ("time", "datetime", "httpx", "aiohttp")
    for name in seen:
        root = name.split(".")[0]
        assert root not in forbidden, name
        assert ".data." not in f".{name}.", name
        assert ".analytics." not in f".{name}.", name


# ---------------------------------------------------------------------------
# SPLIT -- the counter reconciliation (R1 control (c), finding W1)
# ---------------------------------------------------------------------------


def test_the_counter_vocabulary_agrees_with_the_producers() -> None:
    """Both directions. A widget may not import ``data/``, so this panel's
    word map restates ``POOL4_COUNTER_STATES`` -- and this test is what makes
    that safe. A renamed or added state reddens here, rather than falling
    through to the unrecognised branch on a reader's screen, where it would be
    indistinguishable from a control that genuinely could not run.
    """
    assert set(COUNTER_WORDS) == set(POOL4_COUNTER_STATES)
    assert len(COUNTER_WORDS) == len(POOL4_COUNTER_STATES)


def test_no_rendered_counter_word_is_a_substring_of_another() -> None:
    """The producer spells its states ``reconciled``/``mismatch`` rather than
    ``agree``/``disagree`` because ``agree`` is a substring of ``disagree``,
    and a widget testing ``"agree" in state`` would paint a mismatch as
    healthy. WP0 guards its own vocabulary; this panel renders **its own**
    words, so the hazard is reachable again here and gets its own guard.
    """
    words = list(COUNTER_WORDS.values()) + [COUNTER_NEVER, COUNTER_UNKNOWN]
    assert len(set(words)) == len(words)
    for word in words:
        others = [other for other in words if other != word]
        assert not any(word in other for other in others), word

    # The specific direction that would be a silent disaster: the healthy word
    # must not be findable inside any word that is not healthy.
    healthy = COUNTER_WORDS["reconciled"]
    for word in words:
        if word != healthy:
            assert healthy not in word, word


@pytest.mark.asyncio
async def test_a_counter_mismatch_outranks_even_a_non_zero_split_drift() -> None:
    """Both alarms at once, and the order is an argument rather than a taste:
    the drift is computed **from** these counters, so if the counters disagree
    with the hook's own logs the drift is a measurement of nothing. The deeper
    fault is reported first.
    """
    lines, text = await _split(
        pool4_counter_state="mismatch",
        pool4_counter_detail=COUNTER_DETAIL,
        pool4_split_drift_bps=-12.4,
    )
    assert COUNTER_ALERT in text and DRIFT_ALERT in text
    assert (
        _index_of(lines, COUNTER_ALERT)
        < _index_of(lines, DRIFT_ALERT)
        < _index_of(lines, "measured inference")
    )


@pytest.mark.asyncio
async def test_a_counter_mismatch_shows_every_word_of_its_evidence() -> None:
    """A claim whose evidence is shed at a narrow width is not a claim a
    reader can act on. The detail is **wrapped**, not clipped, so every token
    of the "by how much" survives at every width the panel is usable at --
    swept, not spot-checked at one comfortable size.
    """
    for width in range(40, 86, 2):
        _l, text = await _split(
            size=(width, 40),
            pool4_counter_state="mismatch",
            pool4_counter_detail=COUNTER_DETAIL,
        )
        for token in COUNTER_DETAIL.split():
            assert token in text, (width, token)


@pytest.mark.asyncio
async def test_wrapping_the_evidence_costs_no_widen_marker() -> None:
    """The alternative to wrapping was a hard line, and it was rejected here:
    a wei-exact difference is long by nature, so a hard line would light
    ``‹ widen`` at every realistic width and the marker would stop meaning
    anything. Wrapping keeps the evidence *visible* rather than merely
    *marked as cut*.
    """
    for width in range(40, 86, 2):
        _l, text = await _split(
            size=(width, 40),
            pool4_counter_state="mismatch",
            pool4_counter_detail=COUNTER_DETAIL,
        )
        assert SHORT_HINT not in text, width


@pytest.mark.asyncio
async def test_an_unbreakable_evidence_token_lights_the_marker() -> None:
    """The one case wrapping cannot answer: a single token wider than the
    whole panel. It is left over-long and flagged rather than cut, so the CSS
    ellipsis shows the cut *and* the marker says a value could not be shown.
    Without this the wrap would silently swallow the failure it exists to
    prevent.
    """
    _l, text = await _split(
        size=(60, 40),
        pool4_counter_state="mismatch",
        pool4_counter_detail="short-by " + "9" * 200,
    )
    assert COUNTER_ALERT in text
    assert SHORT_HINT in text


@pytest.mark.asyncio
async def test_the_states_that_established_nothing_are_neither_alarm_nor_health() -> None:
    """The hard part of this control: three of its five states are **not
    failures**, and the two tempting renderings are both wrong -- silence
    reads as health, a warning colour reads as alarm. They say *not
    established*, share no word with either verdict, and each still says which
    of the three it is.
    """
    texts = {}
    for state in ("window-limited", "unchecked", None):
        _l, text = await _split(pool4_counter_state=state)
        assert COUNTER_NOT_ESTABLISHED in text, state
        assert COUNTER_ALERT not in text, state
        assert COUNTER_WORDS["reconciled"] not in text, state
        texts[state] = text

    # Distinct: "we ran it over a partial window", "we could not run it" and
    # "it has never run" are three different facts, not one shrug.
    assert len(set(texts.values())) == 3
    assert COUNTER_NEVER in texts[None]


@pytest.mark.asyncio
async def test_a_reconciled_control_is_reported_quietly_and_not_hoisted() -> None:
    """A passing control is not news: it sits with the counters it is a
    verdict on, below them, in the muted style of an ordinary line.
    """
    lines, text = await _split(pool4_counter_state="reconciled")
    assert COUNTER_WORDS["reconciled"] in text
    assert COUNTER_ALERT not in text
    assert COUNTER_NOT_ESTABLISHED not in text
    assert _index_of(lines, "counters ") > _index_of(lines, "burned")


@pytest.mark.asyncio
async def test_a_mismatch_with_no_detail_states_that_the_evidence_is_missing() -> None:
    """"Something disagrees" with the "by how much" silently absent looks
    identical to a panel that simply did not render it.
    """
    _l, text = await _split(
        pool4_counter_state="mismatch", pool4_counter_detail=None,
    )
    assert COUNTER_ALERT in text
    assert COUNTER_NO_DETAIL in text


@pytest.mark.asyncio
async def test_an_unrecognised_counter_state_is_never_echoed_as_a_verdict() -> None:
    """A persisted payload is third-party input on this repo's own precedent
    (the curator ``pattern_language`` rule), so a hand-edited cache can put any
    word in this field. It lands in the third category -- never rendered as a
    verdict, and never echoed to the reader as though the panel understood it.
    """
    _l, text = await _split(pool4_counter_state="everything-is-fine")
    assert COUNTER_UNKNOWN in text
    assert "everything-is-fine" not in text
    assert COUNTER_ALERT not in text
    assert COUNTER_WORDS["reconciled"] not in text


@pytest.mark.asyncio
async def test_a_hostile_counter_detail_never_reaches_markup() -> None:
    """Manager-built, but it carries counter names and wei figures into markup
    and a cache file is editable. Stripped and escaped like every other
    third-party string on these two panels.
    """
    _l, text = await _split(
        pool4_counter_state="mismatch",
        pool4_counter_detail="[/x]short by 100 wei",
    )
    assert "short by 100 wei" in text
    assert "[/x]" not in text
    assert SPLIT_TITLE in text


# ---------------------------------------------------------------------------
# SPLIT -- the Reward Distributor's three-way subdivision (mainnet, 2026-09-02)
# ---------------------------------------------------------------------------


async def _mainnet(size=(70, 40), **overrides):
    """A mainnet payload: the live reads, three-way split, stakers already
    corrected by the producer to the staking leg alone.
    """
    kw = dict(
        pool4_network="MAINNET",
        pool4_measured_inference_pct=1.0,
        pool4_measured_burn_pct=85.0,
        pool4_measured_stakers_pct=4.5,
        pool4_reward_share_bps=1500,
        pool4_reward_path="via-distributor",
        **DISTRIBUTOR_KW,
    )
    kw.update(overrides)
    return await _split(size=size, **kw)


@pytest.mark.asyncio
async def test_the_reward_leg_reads_as_a_subdivision_and_not_as_four_peers() -> None:
    """The three legs are indented under the ``claimed reward`` line that
    names their parent, and they sit between it and the next top-level line.
    A flat list would read as three more peers beside the measured
    percentages, which is the shape that hides that they are *parts of* the
    15% rather than beside it.
    """
    lines, text = await _mainnet()
    parent = _index_of(lines, "claimed reward")
    legs = [_index_of(lines, leg) for leg in ("stakers 30", "nodes 30", "bonding 40")]

    assert legs == sorted(legs)
    assert all(parent < leg for leg in legs)
    # Contiguous with their parent: nothing top-level is interleaved.
    assert legs == [parent + 1, parent + 2, parent + 3]
    # ...and indented under it, which is what carries "part of" on screen.
    for leg in legs:
        assert lines[leg].index("stakers" if leg == legs[0] else
                                "nodes" if leg == legs[1] else "bonding") > \
               lines[parent].index("claimed")
    assert "1,500/10,000 bps" in text


@pytest.mark.asyncio
async def test_a_two_way_and_a_three_way_deployment_differ_in_a_word() -> None:
    """The requirement is that a reader tells them apart **without counting**.

    Two independent signals, and the word is the one that matters: the
    ``measured stakers`` line says which quantity it is, so the number whose
    meaning changed between deployments is the number that carries the label.
    """
    _l, two_way = await _split()                       # no distributor keys
    _l, three_way = await _mainnet()

    assert LEG_WORD_WHOLE in two_way and LEG_WORD_STAKING not in two_way
    assert LEG_WORD_STAKING in three_way and f"({LEG_WORD_WHOLE})" not in three_way
    # ...and the leg block is the second signal, present in exactly one.
    assert "bonding" in three_way and "bonding" not in two_way


def test_the_two_leg_words_share_no_substring() -> None:
    """These two words are the entire difference between a number that means
    15% and one that means 4.5%. If one contained the other, a reader (or a
    test) checking for the smaller would match the larger -- the ``agree``/
    ``disagree`` hazard, on the label that carried the original 3x bug.
    """
    assert LEG_WORD_STAKING not in LEG_WORD_WHOLE
    assert LEG_WORD_WHOLE not in LEG_WORD_STAKING


@pytest.mark.asyncio
async def test_the_derived_leg_says_it_is_derived_and_only_that_leg_does() -> None:
    """``bondingBps()`` does not exist -- bonding is ``denominator - staking -
    nodes``. The word sits on that leg's own line, ``cap_floor``'s *observed*
    precedent, and on no other: a marker that appeared on a leg the chain
    actually stated would make the word meaningless.
    """
    lines, _text = await _mainnet()
    assert DERIVED in lines[_index_of(lines, "bonding 40")]
    assert DERIVED not in lines[_index_of(lines, "stakers 30")]
    assert DERIVED not in lines[_index_of(lines, "nodes 30")]


@pytest.mark.asyncio
async def test_a_derived_share_that_lost_an_input_is_a_dash_not_a_number() -> None:
    """The honest signature of a derived value: it goes ``None`` whenever
    *either* input does. The panel must render that as a dash and must never
    quietly fall back to the 4,000 the chain reads today, which is exactly how
    a hardcoded remainder gets typed in and then goes stale in silence.
    """
    lines, _text = await _mainnet(pool4_distributor_bonding_bps=None)
    row = lines[_index_of(lines, "bonding")]
    assert DASH in row
    assert "40.00%" not in row


@pytest.mark.asyncio
async def test_held_is_rendered_for_the_two_legs_that_have_one_and_no_other() -> None:
    """There is deliberately no ``held_staking``: that leg is forwarded rather
    than held. Inventing one for symmetry would print a zero indistinguishable
    from a real "distributed up to date", so the stakers line carries no
    ``held`` clause at all.
    """
    lines, _text = await _mainnet()
    assert "held" not in lines[_index_of(lines, "stakers 30")]
    assert "held" in lines[_index_of(lines, "nodes 30")]
    assert "held" in lines[_index_of(lines, "bonding 40")]


@pytest.mark.asyncio
async def test_nothing_pending_distribution_is_a_zero_and_not_a_dash() -> None:
    """``heldNft() == 0`` means distributed up to date -- a fact about the
    Distributor, not a failed read.
    """
    lines, _text = await _mainnet(pool4_distributor_held_nodes=0.0)
    row = lines[_index_of(lines, "nodes 30")]
    assert "held 0.00" in row
    assert f"held {DASH}" not in row

    lines, _text = await _mainnet(pool4_distributor_held_nodes=None)
    assert f"held {DASH}" in lines[_index_of(lines, "nodes 30")]


@pytest.mark.asyncio
async def test_no_leg_block_is_invented_when_no_leg_reports() -> None:
    """Three dashes would suggest a Distributor whose values could not be
    read, which is a different claim from the one a two-way payload supports.
    """
    lines, text = await _split()
    assert DERIVED not in text
    for leg in ("stakers 30", "nodes ", "bonding"):
        assert not any(leg in line for line in lines), leg


@pytest.mark.asyncio
async def test_the_claimed_share_and_the_drift_name_the_whole_reward_leg() -> None:
    """Both labels were true on Sepolia and false on mainnet, which is the
    same defect as the 3x staker overstatement one layer out.

    ``rewardShareBps()`` is the claimed **reward** share -- on mainnet the
    claimed staker share is 450 bps of it, not 1,500 -- and
    ``split_drift_bps`` compares ``totalRewarded`` against it, i.e. the whole
    leg on both chains.
    """
    _l, text = await _mainnet()
    assert "claimed reward" in text
    assert "claimed stakers" not in text

    _l, drifting = await _mainnet(pool4_split_drift_bps=-12.4)
    assert "reward share below claimed" in drifting
    assert "measured stakers below" not in drifting


@pytest.mark.asyncio
async def test_the_three_measured_percentages_need_not_sum_to_a_hundred() -> None:
    """On mainnet they do not, and that is correct: bonding and nodes are the
    remainder and the leg block is where they are. The panel must not imply
    otherwise -- so this pins that the rendering carries the measured numbers
    it was handed and invents no balancing figure.
    """
    _l, text = await _mainnet()
    assert "1.00%" in text and "85.00%" in text and "4.50%" in text
    total = 1.0 + 85.0 + 4.5
    assert total != 100.0                       # the premise, stated
    assert "9.50%" not in text and "10.50%" not in text


@pytest.mark.asyncio
async def test_every_leg_line_fits_the_rail_the_panel_is_rendered_in() -> None:
    """The rail hands this panel 48 columns and it binds the body's height
    pin, so a leg that overflows costs a row there rather than a marker here.

    Asserted against composited output at the real width: every leg line is
    within the panel, and none of them wrapped.
    """
    lines, _text = await _mainnet(size=(50, 40))
    for leg in ("stakers 30", "nodes 30", "bonding 40"):
        row = lines[_index_of(lines, leg)]
        assert cell_len(row) <= 50, (leg, cell_len(row))
        assert "earned" in row, leg          # the clause did not reflow away


@pytest.mark.asyncio
async def test_a_distributor_that_cannot_be_read_is_not_rendered_as_absent() -> None:
    """``pool4_reward_path`` states the topology, and it separates the two
    states this panel would otherwise conflate.

    A Distributor in the path whose split could not be read is **not** a
    two-way deployment. Rendering it as one would describe the wrong protocol
    by omission -- the same failure as the 3x staker overstatement, arrived at
    from the other side.
    """
    _l, unread = await _mainnet(**{key: None for key in DISTRIBUTOR_KW})
    assert DISTRIBUTOR_UNREAD in unread
    assert f"({LEG_WORD_WHOLE})" not in unread        # never "the reward leg"
    assert DERIVED not in unread                      # and no invented block

    # A healthy three-way read says nothing of the sort...
    _l, healthy = await _mainnet()
    assert DISTRIBUTOR_UNREAD not in healthy
    # ...and neither does a deployment that genuinely has none.
    _l, two_way = await _split()
    assert DISTRIBUTOR_UNREAD not in two_way
    assert LEG_WORD_WHOLE in two_way


@pytest.mark.asyncio
async def test_the_pair_that_fits_the_rail_costs_one_row_and_not_two() -> None:
    """The row saving itself, pinned at the width the panel is really given.

    This is what paid for the mainnet leg block without moving the body's
    height pin, so it is asserted rather than left as a measurement in a
    report: at the rail's own 48 usable columns the two pairs that fit are on
    one line each.
    """
    lines, _text = await _split(size=(50, 40))
    burned = [line for line in lines if "burned" in line]
    fees = [line for line in lines if "fees" in line]
    assert len(burned) == 1 and "rewarded" in burned[0]
    assert len(fees) == 1 and "retained" in fees[0]


def test_the_reward_path_vocabulary_agrees_with_the_producers() -> None:
    """Both directions, on the restated-literal precedent: a widget may not
    import ``data/``, so a renamed path has to redden here rather than quietly
    annotate nothing on every payload -- which would look exactly like an
    unread ``rewardsRecipient()`` and hide a rename behind a legitimate state.
    """
    assert set(REWARD_PATHS) == set(POOL4_REWARD_PATHS)
    assert len(REWARD_PATHS) == len(POOL4_REWARD_PATHS)


@pytest.mark.asyncio
async def test_an_unknown_reward_path_annotates_nothing_in_either_direction() -> None:
    """The state WP0's argument turns on, and the reason this keys off a word
    rather than off ``pool4_distributor_addr``.

    The hook's getters are batched with ``allowFailure=True``, so "the
    counters answered, ``rewardsRecipient()`` did not" is a routine payload --
    and in it the address is ``None`` exactly as it is on a deployment with no
    Distributor. Reading absence-of-address as absence-of-Distributor would
    label mainnet's 15% as the staker share: the 3x bug, arriving through the
    door opened to prevent it.

    So an unknown path says **neither** word.
    """
    _l, unknown = await _split(pool4_reward_path=None,
                              pool4_measured_stakers_pct=15.0)
    assert f"({LEG_WORD_WHOLE})" not in unknown
    assert f"({LEG_WORD_STAKING})" not in unknown
    assert DISTRIBUTOR_UNREAD not in unknown
    assert "15.00%" in unknown          # the number is still shown, unlabelled

    # ...and the address alone must not resurrect the guess. This payload has
    # a Distributor address and an unknown path: still no annotation.
    _l, addressed = await _split(
        pool4_reward_path=None,
        pool4_distributor_addr="0x9046739E1535B40EfBe6AB3f45d0024b690eCA30",
        pool4_measured_stakers_pct=15.0,
    )
    assert f"({LEG_WORD_WHOLE})" not in addressed
    assert f"({LEG_WORD_STAKING})" not in addressed


@pytest.mark.asyncio
async def test_the_path_word_decides_the_annotation_and_the_legs_do_not() -> None:
    """A leg block without ``via-distributor`` behind it must not manufacture
    the label: the word is the stated fact and the legs are its evidence, not
    a second source of truth that could disagree with it.
    """
    _l, text = await _split(pool4_reward_path=PATH_VIA_DISTRIBUTOR)
    assert f"({LEG_WORD_STAKING})" in text
    assert DISTRIBUTOR_UNREAD in text          # legs unread, path known
