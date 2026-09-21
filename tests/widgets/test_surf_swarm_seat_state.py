"""``widgets/surf/_swarm_seat`` -- the AGENT panels' seat-state words, typed once.

Pure helpers (no Textual), so these read the returned ``Text`` directly; the
composited proof of each word is in the hero and SEAT RECORD test files. The
state set is bound to the contract here: a fourth ``SWARM_SEAT_STATES`` value
reddens this file before it can fall through to ``unavailable`` unnoticed.
"""

from __future__ import annotations

import pytest
from rich.text import Text

from maxpane_dashboard.data.surf_models import SWARM_SEAT_STATES
from maxpane_dashboard.widgets.panels import LOADING, UNAVAILABLE
from maxpane_dashboard.widgets.surf._swarm_seat import (
    NEVER_PAIRED_STYLE,
    NEVER_PAIRED_TEMPLATE,
    NEVER_PAIRED_WORDS,
    never_paired,
    seat_state_line,
    seat_token,
)


def test_every_contract_state_has_a_word_of_its_own():
    """``ok`` paints numbers; every other contract state, and ``None``, is a
    different line -- a real negative is never the words of a failure."""
    assert set(SWARM_SEAT_STATES) == {"ok", "pending", "unknown_seat"}
    lines = {state: seat_state_line(state, 420) for state in (*SWARM_SEAT_STATES, None)}
    assert lines["ok"] is None
    shown = {state: line.plain for state, line in lines.items() if line is not None}
    assert len(set(shown.values())) == len(shown) == 3, shown


def test_pending_is_the_shared_loading_seed():
    assert seat_state_line("pending", 420).plain == Text.from_markup(LOADING).plain


@pytest.mark.parametrize("state", [None, "garbage", 0, ["ok"]])
def test_a_failed_or_malformed_state_is_unavailable(state):
    assert seat_state_line(state, 420).plain == Text.from_markup(UNAVAILABLE).plain


def test_unknown_seat_names_the_seat_that_never_paired():
    line = seat_state_line("unknown_seat", 420)
    assert line.plain == "#420 never paired" == NEVER_PAIRED_TEMPLATE.format(token=420)
    assert NEVER_PAIRED_STYLE in str(line.style)
    assert "unavailable" not in line.plain


@pytest.mark.parametrize("token", [None, True, -1, "420", 4.2])
def test_unknown_seat_without_a_usable_token_says_the_words_alone(token):
    assert seat_state_line("unknown_seat", token).plain == NEVER_PAIRED_WORDS
    assert never_paired(token) == NEVER_PAIRED_WORDS


def test_seat_token_takes_a_non_negative_int_only():
    assert seat_token(0) == 0 and seat_token(12345) == 12345
    for bad in (True, False, -1, "7", 7.0, None):
        assert seat_token(bad) is None, bad
