"""FEEDBACK -- the selected seat's on-chain ERC-8004 feedback (plan A1, WP6a).

Composited assertions only; the hand rows are bound to
``SURF_ROW_KEYS["swarm_seat_feedback_rows"]``. Unwired until WP7, so the
per-class contract checks are imposed here against ``SWARM_WIDGET_SIGNATURES``.
"""

from __future__ import annotations

import inspect

from textual.app import App

from maxpane_dashboard.data.surf_models import SURF_ROW_KEYS, SWARM_WIDGET_SIGNATURES
from maxpane_dashboard.widgets.address import COPY_GLYPH, MIN_SHORT_COLS
from maxpane_dashboard.widgets.fmt import hhmm
from maxpane_dashboard.widgets.surf._swarm_table import SwarmTableBase
from maxpane_dashboard.widgets.surf.swarm_seat_feedback import (
    COMPACT_WIDTH,
    EMPTY_LINE,
    FULL_WIDTH,
    TIGHT_WIDTH,
    TX_COLS,
    SurfSwarmSeatFeedback,
)
from tests.widgets.address_probe import link_targets
from tests.widgets.surf_compositing import composite_lines

TX = "0xc2cb3be4bf5c1bfc76cd3d6e4cdb62b0361411d758a5b0a2e13c6f83fd2d845b"
TX2 = "0x1111111111111111111111111111111111111111111111111111111111111111"
JOB = "ad7bebb8-fd1a-4268-b831-1c253a85ae4c"
SENT = 1_789_000_000.0

MAINNET = {
    "value": 1, "node_key": "build_contract_project", "job_id": JOB, "tx_hash": TX,
    "chain_id": 1, "block_number": 23_500_000, "sent_ts": SENT,
}
SEPOLIA = dict(MAINNET, value=100, node_key="review_oracle", tx_hash=TX2, chain_id=11155111,
               sent_ts=SENT - 60)
UNCHAINED = dict(MAINNET, chain_id=None, block_number=None, value=0.5, node_key="unchained")
ROWS = [MAINNET, SEPOLIA, UNCHAINED]
AS_OF = "04:06"
SIZE = (110, 12)


def test_the_hand_rows_carry_exactly_the_frozen_shape():
    for row in ROWS:
        assert tuple(row) == SURF_ROW_KEYS["swarm_seat_feedback_rows"]


async def _feedback(size=SIZE, **kwargs):
    kwargs.setdefault("swarm_seat_feedback_rows", ROWS)
    kwargs.setdefault("swarm_seat_as_of_hhmm", AS_OF)
    return await composite_lines(SurfSwarmSeatFeedback, size, **kwargs)


def _row_with(lines, needle):
    return next(line for line in lines if needle in line)


async def _links(rows, size=SIZE):
    class _A(App):
        def compose(self):
            yield SurfSwarmSeatFeedback()

    async with _A().run_test(size=size) as pilot:
        widget = pilot.app.query_one(SurfSwarmSeatFeedback)
        widget.update_data(swarm_seat_feedback_rows=rows, swarm_seat_as_of_hhmm=AS_OF)
        await pilot.pause()
        return sorted({url for _x, _y, _n, _k, _v, url in link_targets(pilot.app) if url})


# -- the self-imposed contract -----------------------------------------------------


def test_update_data_names_exactly_the_frozen_signature_in_order():
    sig = inspect.signature(SurfSwarmSeatFeedback.update_data)
    params = [n for n, p in sig.parameters.items() if n != "self" and p.kind is not p.VAR_KEYWORD]
    assert tuple(params) == SWARM_WIDGET_SIGNATURES["SurfSwarmSeatFeedback"]
    assert any(p.kind is p.VAR_KEYWORD for p in sig.parameters.values())


async def test_no_args_and_all_none_render_unavailable_without_raising():
    bare = "\n".join(await composite_lines(SurfSwarmSeatFeedback, SIZE))
    assert "unavailable" in bare and "Loading" not in bare
    none = "\n".join(await composite_lines(
        SurfSwarmSeatFeedback, SIZE,
        **{k: None for k in SWARM_WIDGET_SIGNATURES["SurfSwarmSeatFeedback"]},
    ))
    assert "unavailable" in none


# -- rows -------------------------------------------------------------------------


async def test_a_row_renders_when_value_node_job_chain_and_a_windowed_hash():
    lines = await _feedback()
    row = _row_with(lines, "build_contract_project")
    assert hhmm(SENT) in row and JOB[:8] in row and "MAINNET" in row
    assert TX[:6] in row and TX not in row, "the hash is windowed, never whole"
    assert COPY_GLYPH not in "\n".join(lines), "a hash carries no copy icon"
    assert "FEEDBACK" in "\n".join(lines) and f"as of {AS_OF}" in "\n".join(lines)
    assert "23,500,000" not in "\n".join(lines) and "23500000" not in "\n".join(lines)


async def test_values_100_1_and_a_fraction_all_render():
    lines = await _feedback()
    assert " 1 " in _row_with(lines, "build_contract_project")
    assert " 100 " in _row_with(lines, "review_oracle")
    assert " 0.5 " in _row_with(lines, "unchained")


async def test_the_chain_word_is_per_row_and_none_is_the_dash():
    lines = await _feedback()
    assert "SEPOLIA" in _row_with(lines, "review_oracle")
    assert "—" in _row_with(lines, "unchained")


async def test_each_row_links_its_own_chain_and_none_links_nothing():
    assert await _links([MAINNET]) == [f"https://etherscan.io/tx/{TX}"]
    assert await _links([SEPOLIA]) == [f"https://sepolia.etherscan.io/tx/{TX2}"]
    assert await _links([UNCHAINED]) == []
    assert await _links([dict(MAINNET, chain_id=999_999_999)]) == []


async def test_none_and_empty_differ():
    empty = "\n".join(await _feedback(swarm_seat_feedback_rows=[]))
    assert EMPTY_LINE in empty and "unavailable" not in empty
    unread = "\n".join(await _feedback(swarm_seat_feedback_rows=None))
    assert "unavailable" in unread and EMPTY_LINE not in unread


async def test_a_non_dict_row_is_skipped_and_the_rest_render():
    text = "\n".join(await _feedback(swarm_seat_feedback_rows=[MAINNET, "garbage", None, SEPOLIA]))
    assert "build_contract_project" in text and "review_oracle" in text


async def test_a_hostile_node_key_renders_stripped_and_never_raises():
    hostile = dict(MAINNET, node_key="[/x]PWNED", job_id="[$error]job")
    lines = await _feedback(swarm_seat_feedback_rows=[hostile], region_only=True)
    text = "\n".join(lines)
    assert "PWNED" in text and "[" not in text and "]" not in text


async def test_a_malformed_row_field_dashes_instead_of_crashing():
    row = dict(MAINNET, value="lots", tx_hash=12345, sent_ts="yesterday")
    line = _row_with(await _feedback(swarm_seat_feedback_rows=[row]), "build_contract_project")
    assert "--" in line and "??:??" in line


async def test_rows_past_the_cap_are_not_drawn():
    rows = [dict(MAINNET, node_key=f"node_{i:02d}") for i in range(15)]
    lines = await _feedback((110, 30), swarm_seat_feedback_rows=rows)
    assert len([l for l in lines if "node_" in l]) == SurfSwarmSeatFeedback.ROW_CAP == 12


# -- tiers -------------------------------------------------------------------------


def test_the_tier_thresholds_descend():
    assert FULL_WIDTH > COMPACT_WIDTH > TIGHT_WIDTH > 0
    assert TX_COLS > MIN_SHORT_COLS


async def test_one_below_full_sheds_job_and_says_widen():
    gutter = SwarmTableBase.GUTTER_COLS
    full = "\n".join(await _feedback((FULL_WIDTH + gutter, 12), swarm_seat_feedback_rows=[MAINNET]))
    compact = "\n".join(await _feedback((FULL_WIDTH + gutter - 1, 12),
                                        swarm_seat_feedback_rows=[MAINNET]))
    assert JOB[:8] in full and "‹" not in full
    assert JOB[:8] not in compact and "‹" in compact
    assert "build_contract_project" in compact


async def test_one_below_compact_sheds_node_and_shortens_the_hash():
    gutter = SwarmTableBase.GUTTER_COLS
    tight = "\n".join(await _feedback((COMPACT_WIDTH + gutter - 1, 12),
                                      swarm_seat_feedback_rows=[MAINNET]))
    assert "build_contract_project" not in tight and "‹" in tight
    assert "MAINNET" in tight
    compact = "\n".join(await _feedback((FULL_WIDTH + gutter - 1, 12),
                                        swarm_seat_feedback_rows=[MAINNET]))
    tx_tight = next(l for l in tight.splitlines() if "MAINNET" in l)
    tx_compact = next(l for l in compact.splitlines() if "MAINNET" in l)
    assert len(tx_tight.split("MAINNET")[1].strip()) < len(tx_compact.split("MAINNET")[1].strip())
    assert TX[:6] in tight


async def test_a_tight_hash_still_links():
    gutter = SwarmTableBase.GUTTER_COLS
    assert await _links([MAINNET], (COMPACT_WIDTH + gutter - 1, 12)) == [f"https://etherscan.io/tx/{TX}"]
