"""FEEDBACK -- the selected seat's scored reviews, lifetime, newest first (plan WP4).

Composited assertions only. Rows are **folded** from the committed ``/seats``
captures by ``data/surf_swarm.seat_review_rows`` (the manager's own fold) and
every expected value is read off that fold, never hand-typed. The per-class
contract is imposed against ``SWARM_WIDGET_SIGNATURES`` and
``SURF_ROW_KEYS["swarm_seat_feedback_rows"]`` (both flipped in WP5).
"""

from __future__ import annotations

import inspect

from textual.app import App

from maxpane_dashboard.data.surf_models import (
    SURF_ROW_KEYS,
    SWARM_WIDGET_SIGNATURES,
)
from maxpane_dashboard.data.surf_swarm import seat_review_rows
from maxpane_dashboard.widgets.address import COPY_GLYPH, MIN_SHORT_COLS
from maxpane_dashboard.widgets.explorer import for_chain_id, tx_url
from maxpane_dashboard.widgets.fmt import hhmm
from maxpane_dashboard.widgets.surf._swarm_chain import chain_word
from maxpane_dashboard.widgets.surf._swarm_seat import NEVER_PAIRED_WORDS
from maxpane_dashboard.widgets.surf._swarm_table import SwarmTableBase
from maxpane_dashboard.widgets.surf.swarm_seat_feedback import (
    COMPACT_WIDTH,
    EMPTY_LINE,
    FULL_WIDTH,
    TIGHT_WIDTH,
    TX_COLS,
    SurfSwarmSeatFeedback,
)
from tests.surf_swarm_fixtures import swarm_seat_capture
from tests.widgets.address_probe import link_targets
from tests.widgets.surf_compositing import composite_lines

SIGNATURE = SWARM_WIDGET_SIGNATURES["SurfSwarmSeatFeedback"]

ROWS_420 = seat_review_rows(swarm_seat_capture("seat_420"))
ROWS_0 = seat_review_rows(swarm_seat_capture("seat_0"))
SENT = next(r for r in ROWS_420 if r["status"] == "sent")
SUBMITTED = next(r for r in ROWS_420 if r["status"] == "submitted")
QUEUED = next(r for r in ROWS_420 if r["status"] == "queued")
AS_OF = "04:06"
SIZE = (110, 12)


def _job(row) -> str:
    return row["job_id"][:8]


def test_the_folded_rows_carry_exactly_the_target_shape():
    assert ROWS_420 and ROWS_0
    for row in ROWS_420 + ROWS_0:
        assert tuple(row) == SURF_ROW_KEYS["swarm_seat_feedback_rows"]
    assert QUEUED["tx_hash"] is None and QUEUED["chain_id"] is None and QUEUED["sent_ts"] is None
    assert SUBMITTED["sent_ts"] is None and SUBMITTED["tx_hash"]


async def _feedback(size=SIZE, **kwargs):
    kwargs.setdefault("swarm_seat_feedback_rows", ROWS_420)
    kwargs.setdefault("swarm_seat_state", "ok")
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
        widget.update_data(swarm_seat_feedback_rows=rows, swarm_seat_state="ok",
                           swarm_seat_as_of_hhmm=AS_OF)
        await pilot.pause()
        return sorted({url for _x, _y, _n, _k, _v, url in link_targets(pilot.app) if url})


def _url(row) -> str:
    return tx_url(for_chain_id(row["chain_id"]), row["tx_hash"])


# -- the self-imposed contract -----------------------------------------------------


def test_update_data_names_exactly_the_target_signature_in_order():
    sig = inspect.signature(SurfSwarmSeatFeedback.update_data)
    params = [n for n, p in sig.parameters.items() if n != "self" and p.kind is not p.VAR_KEYWORD]
    assert tuple(params) == SIGNATURE
    assert any(p.kind is p.VAR_KEYWORD for p in sig.parameters.values())


async def test_a_row_missing_a_key_dashes_that_cell_and_never_raises():
    """A hand-edited persisted row (third-party input): no ``status``, and a
    stray ``block_number`` the contract no longer carries."""
    old = {key: SENT.get(key) for key in SURF_ROW_KEYS["swarm_seat_feedback_rows"]
           if key != "status"}
    old["block_number"] = 1
    assert "status" not in old
    row = _row_with(await _feedback(swarm_seat_feedback_rows=[old]), _job(SENT))
    assert hhmm(SENT["sent_ts"]) in row and "--" in row


# -- the four seat states stay distinct ----------------------------------------------


async def test_no_args_and_all_none_render_unavailable_without_raising():
    bare = "\n".join(await composite_lines(SurfSwarmSeatFeedback, SIZE))
    assert "unavailable" in bare and "Loading" not in bare and EMPTY_LINE not in bare
    none = "\n".join(await composite_lines(
        SurfSwarmSeatFeedback, SIZE, **{k: None for k in SIGNATURE},
    ))
    assert "unavailable" in none and EMPTY_LINE not in none


async def test_a_failed_read_is_unavailable_and_never_the_real_empty_sentence():
    for rows in (None, [], ROWS_420):
        text = "\n".join(await _feedback(swarm_seat_feedback_rows=rows, swarm_seat_state=None))
        assert "unavailable" in text, rows
        assert EMPTY_LINE not in text and _job(SENT) not in text


async def test_ok_with_empty_rows_is_the_real_empty_sentence_and_unread_is_unavailable():
    empty = "\n".join(await _feedback(swarm_seat_feedback_rows=[]))
    assert EMPTY_LINE in empty and "unavailable" not in empty
    unread = "\n".join(await _feedback(swarm_seat_feedback_rows=None))
    assert "unavailable" in unread and EMPTY_LINE not in unread


async def test_unknown_seat_says_never_paired_and_pending_says_loading():
    unknown = "\n".join(await _feedback(swarm_seat_feedback_rows=[],
                                        swarm_seat_state="unknown_seat"))
    assert NEVER_PAIRED_WORDS in unknown
    assert EMPTY_LINE not in unknown and "unavailable" not in unknown
    pending = "\n".join(await _feedback(swarm_seat_state="pending"))
    assert "Loading" in pending and _job(SENT) not in pending
    assert "unavailable" not in pending and EMPTY_LINE not in pending


# -- rows ---------------------------------------------------------------------------


async def test_a_sent_row_renders_when_value_node_job_status_chain_and_a_windowed_hash():
    lines = await _feedback()
    row = _row_with(lines, _job(SENT))
    assert hhmm(SENT["sent_ts"]) in row and SENT["node_key"] in row
    assert f" {SENT['value']} " in row and " sent " in row
    assert chain_word(SENT["chain_id"]) in row
    assert SENT["tx_hash"][:6] in row and SENT["tx_hash"] not in row, "windowed, never whole"
    text = "\n".join(lines)
    assert COPY_GLYPH not in text, "a hash carries no copy icon"
    assert "FEEDBACK" in text and f"as of {AS_OF}" in text
    header = _row_with(lines, "status").split()
    assert header == ["when", "value", "node", "job", "status", "chain", "tx"]


async def test_the_submitted_row_shows_submitted_in_when_and_still_links():
    row = _row_with(await _feedback(swarm_seat_feedback_rows=[SUBMITTED]), _job(SUBMITTED))
    assert row.split()[0] == "submitted"
    assert SUBMITTED["tx_hash"][:6] in row
    assert await _links([SUBMITTED]) == [_url(SUBMITTED)]


async def test_the_queued_row_has_no_tx_cell_and_no_link():
    row = _row_with(await _feedback(swarm_seat_feedback_rows=[QUEUED]), _job(QUEUED))
    assert row.split()[0] == "queued"
    assert "0x" not in row and "—" in row, "no hash; the chain is the em dash"
    assert await _links([QUEUED]) == []
    # A hand-edited cache that put a hash on a queued review still links nothing.
    forged = dict(QUEUED, tx_hash=SENT["tx_hash"], chain_id=SENT["chain_id"])
    assert "0x" not in _row_with(await _feedback(swarm_seat_feedback_rows=[forged]), _job(QUEUED))
    assert await _links([forged]) == []


async def test_each_row_links_its_own_chain_and_an_unknown_one_links_nothing():
    assert await _links([SENT]) == [_url(SENT)]
    assert await _links([dict(SENT, chain_id=11155111)]) == [
        tx_url(for_chain_id(11155111), SENT["tx_hash"])]
    assert await _links([dict(SENT, chain_id=999_999_999)]) == []
    assert await _links([dict(SENT, chain_id=None)]) == []


async def test_a_hostile_node_key_and_status_render_literally_and_never_raise():
    hostile = dict(SENT, node_key="[/x]PWNED", job_id="[$error]job", status="[/z]ST")
    lines = await _feedback(swarm_seat_feedback_rows=[hostile], region_only=True)
    text = "\n".join(lines)
    assert "PWNED" in text and "ST" in text and "[" not in text and "]" not in text


async def test_a_malformed_row_field_dashes_and_a_non_dict_row_is_skipped():
    bad = dict(SENT, value="lots", tx_hash=12345, sent_ts="yesterday")
    lines = await _feedback(swarm_seat_feedback_rows=[bad, "garbage", None, SUBMITTED])
    line = _row_with(lines, "??:??")
    assert "--" in line
    assert "submitted" in "\n".join(lines)


async def test_the_largest_seat_shows_twelve_rows_and_names_the_rest_older():
    lines = await _feedback((110, 30), swarm_seat_feedback_rows=ROWS_0)
    shown = [l for l in lines if any(_job(r) in l for r in ROWS_0)]
    assert len(shown) == SurfSwarmSeatFeedback.ROW_CAP == 12
    older = len(ROWS_0) - SurfSwarmSeatFeedback.ROW_CAP
    assert older == len(swarm_seat_capture("seat_0")["reviews"]) - 12
    assert f"+{older} older" in "\n".join(lines)


# -- tiers (provisional; WP6 measures) ------------------------------------------------


def test_the_tier_thresholds_descend():
    assert FULL_WIDTH > COMPACT_WIDTH > TIGHT_WIDTH > 0
    assert TX_COLS > MIN_SHORT_COLS


async def test_one_below_full_sheds_job_and_says_widen():
    gutter = SwarmTableBase.GUTTER_COLS
    full = "\n".join(await _feedback((FULL_WIDTH + gutter, 12), swarm_seat_feedback_rows=[SENT]))
    compact = "\n".join(await _feedback((FULL_WIDTH + gutter - 1, 12),
                                        swarm_seat_feedback_rows=[SENT]))
    assert _job(SENT) in full and "‹" not in full
    assert _job(SENT) not in compact and "‹" in compact
    assert SENT["node_key"] in compact


async def test_one_below_compact_sheds_node_and_shortens_the_hash_which_still_links():
    gutter = SwarmTableBase.GUTTER_COLS
    size = (COMPACT_WIDTH + gutter - 1, 12)
    tight = await _feedback(size, swarm_seat_feedback_rows=[SENT])
    compact = await _feedback((FULL_WIDTH + gutter - 1, 12), swarm_seat_feedback_rows=[SENT])
    word = chain_word(SENT["chain_id"])
    assert SENT["node_key"] not in "\n".join(tight) and "‹" in "\n".join(tight)
    tx_tight = _row_with(tight, word).split(word)[1].strip()
    tx_compact = _row_with(compact, word).split(word)[1].strip()
    assert len(tx_tight) < len(tx_compact) and tx_tight.startswith(SENT["tx_hash"][:6])
    assert await _links([SENT], size) == [_url(SENT)]
