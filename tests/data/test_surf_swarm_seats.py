"""Tests for the pure ``/seats/{tokenId}`` fold in ``maxpane_dashboard.data.surf_swarm``
(plan ``docs/surf_agent_seats_plan.md`` WP1b).

Every payload is a committed 2026-09-21 capture under
``tests/fixtures/surf/swarm/seats/`` (WP0), or a hand-edited copy of one.  Every
literal pinned below was read off the JSON by hand (the field it came from is
named beside it), so no expectation was derived from the fold.  No network, no
clock.
"""

from __future__ import annotations

import copy
import datetime
from types import MappingProxyType

import pytest

from maxpane_dashboard.data import surf_swarm as fold
from maxpane_dashboard.data.surf_models import (
    SURF_ROW_KEYS,
    SWARM_ROSTER_WINDOW_FIELDS,
    SWARM_SEAT_FEEDBACK_ROW_KEYS_NEXT,
    SWARM_SEAT_REVIEW_STATUSES,
    SWARM_SEAT_SELECTED_FIELDS,
    SWARM_SEAT_STATES,
    SWARM_SEAT_SUMMARY_FIELDS,
)
from maxpane_dashboard.data.surf_swarm_client import UNKNOWN_SEAT
from tests.surf_swarm_fixtures import swarm_seat_capture


def _iso(stamp: str) -> float:
    return datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()


@pytest.fixture
def seat420() -> dict:
    return swarm_seat_capture("seat_420")


# ---------------------------------------------------------------------------
# seat_state
# ---------------------------------------------------------------------------


def test_seat_state_ok_for_every_fixture_seat_whose_decimal_string_token_matches():
    for token in (420, 0, 1649, 516):
        payload = swarm_seat_capture(f"seat_{token}")
        assert payload["tokenId"] == str(token)          # served as a decimal string
        assert fold.seat_state(payload, token) == "ok"


def test_seat_state_unknown_seat_for_the_constant_and_a_plain_dict_equal_to_it():
    assert fold.seat_state(UNKNOWN_SEAT, 420) == "unknown_seat"
    assert fold.seat_state(dict(UNKNOWN_SEAT), 420) == "unknown_seat"
    assert fold.seat_state({"error": "unknown_seat"}, 7) == "unknown_seat"


def test_seat_state_the_404_body_itself_is_not_the_normalised_result():
    """The raw 404 body carries a ``detail``; the client normalises it.  The fold
    answers ``unknown_seat`` only for the normalised result, never a lookalike."""
    body = swarm_seat_capture("unknown_seat_404")
    assert body["error"] == "unknown_seat" and "detail" in body
    assert fold.seat_state(body, 420) is None
    assert fold.seat_state({"error": "unknown_seat", "tokenId": "420"}, 420) is None


def test_seat_state_tokenid_mismatch_is_none(seat420):
    assert fold.seat_state(seat420, 421) is None
    assert fold.seat_state(seat420, 42) is None


@pytest.mark.parametrize("token_id", [
    "١٥٤٨",      # Arabic-Indic digits: str.isdigit() and int() both accept these
    "４２０",     # full-width digits
    " 420", "420 ", "+420", "-420", "4_20", "420.0", "", "0x1a4", None, 420.0, True,
    ["420"],
])
def test_seat_state_tokenid_parses_strictly(seat420, token_id):
    seat420["tokenId"] = token_id
    wanted = 1548 if token_id == "١٥٤٨" else 420
    assert fold.seat_state(seat420, wanted) is None


def test_seat_state_accepts_an_int_tokenid_and_leading_zeros_compare_as_int(seat420):
    seat420["tokenId"] = 420
    assert fold.seat_state(seat420, 420) == "ok"
    seat420["tokenId"] = "0420"
    assert fold.seat_state(seat420, 420) == "ok"


@pytest.mark.parametrize("token", [True, -1, "420", 420.0, None])
def test_seat_state_refuses_a_token_that_is_no_seat_id(seat420, token):
    assert fold.seat_state(seat420, token) is None


@pytest.mark.parametrize("payload", [None, [], "unknown_seat", {"error": "invalid_request"},
                                     swarm_seat_capture("invalid_request_400"), {}])
def test_seat_state_anything_else_is_none(payload):
    assert fold.seat_state(payload, 420) is None


# ---------------------------------------------------------------------------
# seat_summary_from_seat
# ---------------------------------------------------------------------------


def test_summary_420_is_the_explorer_record(seat420):
    summary = fold.seat_summary_from_seat(seat420)
    assert tuple(summary) == SWARM_SEAT_SUMMARY_FIELDS
    assert summary == {
        "attempts": 74,                     # attempts
        "accepted": 12,                     # accepted  ("12 of 74")
        "reviewed": 72,                     # len(reviews)
        "review_status": {"sent": 66, "submitted": 5, "queued": 1},
        "mean_score": 1.0,                  # every reviews[].value is 1
        "scored": 72,
        "roles": [{"role": "implement", "count": 71}, {"role": "review", "count": 1}],
        "online": True,
        "owner": "0xe5b1275fb926613d983da33fbfe1f331b7f64f2a",
        "paired_ts": _iso("2026-09-20T05:34:25.536Z"),        # pairedAt
        "last_active_ts": _iso("2026-09-21T06:42:05.562Z"),   # newest sentAt (> newest acceptedAt 04:10)
        "collaborators": 24,
        "runtime": "claude 2.1.278 (Claude Code)",            # runtimes[0] id + version, raw
    }
    assert tuple(summary["review_status"]) == SWARM_SEAT_REVIEW_STATUSES


def test_summary_0_offline_and_no_runtime():
    summary = fold.seat_summary_from_seat(swarm_seat_capture("seat_0"))
    assert summary["online"] is False
    assert summary["runtime"] is None                       # runtimes: []
    assert (summary["accepted"], summary["attempts"]) == (26, 209)
    assert summary["reviewed"] == 202 and summary["scored"] == 202
    assert summary["review_status"] == {"sent": 189, "submitted": 13, "queued": 0}
    assert summary["roles"] == [{"role": "implement", "count": 196},
                                {"role": "review", "count": 5},
                                {"role": "integrate", "count": 1}]
    assert summary["collaborators"] == 31


def test_summary_1649_codex_runtime():
    summary = fold.seat_summary_from_seat(swarm_seat_capture("seat_1649"))
    assert summary["runtime"] == "codex codex-cli 0.149.0"
    assert (summary["accepted"], summary["attempts"]) == (3, 17)


def test_summary_516_smallest_seat():
    summary = fold.seat_summary_from_seat(swarm_seat_capture("seat_516"))
    assert (summary["accepted"], summary["attempts"]) == (4, 10)
    assert summary["reviewed"] == 9
    assert summary["review_status"] == {"sent": 8, "submitted": 1, "queued": 0}
    assert summary["roles"] == [{"role": "implement", "count": 7}, {"role": "review", "count": 2}]


@pytest.mark.parametrize("payload", [None, [], "x", 0])
def test_summary_of_a_non_mapping_is_every_field_none(payload):
    summary = fold.seat_summary_from_seat(payload)
    assert tuple(summary) == SWARM_SEAT_SUMMARY_FIELDS
    assert all(value is None for value in summary.values())


# Each hand-edit breaks one field; exactly the fields it feeds go None.
_BAD_FIELD_CASES = {
    "attempts": ("attempts", "74", {"attempts"}),
    "attempts_bool": ("attempts", True, {"attempts"}),
    "attempts_negative": ("attempts", -1, {"attempts"}),
    "accepted": ("accepted", 12.0, {"accepted"}),
    "online": ("online", "true", {"online"}),
    "online_int": ("online", 1, {"online"}),
    "owner": ("owner", 42, {"owner"}),
    "pairedAt": ("pairedAt", "yesterday", {"paired_ts"}),
    "pairedAt_num": ("pairedAt", 1_758_000_000, {"paired_ts"}),
    "collaborators": ("collaborators", {"n": 24}, {"collaborators"}),
    "runtimes": ("runtimes", "claude", {"runtime"}),
    "runtimes_member": ("runtimes", [["claude", "2.1"]], {"runtime"}),
    "runtimes_types": ("runtimes", [{"id": 1, "version": None}], {"runtime"}),
}


@pytest.mark.parametrize("case", sorted(_BAD_FIELD_CASES))
def test_summary_a_wrong_type_in_one_field_is_none_in_that_field_only(seat420, case):
    good = fold.seat_summary_from_seat(seat420)
    field, bad, broken = _BAD_FIELD_CASES[case]
    seat420[field] = bad
    summary = fold.seat_summary_from_seat(seat420)
    for key in SWARM_SEAT_SUMMARY_FIELDS:
        if key in broken:
            assert summary[key] is None, key
        else:
            assert summary[key] == good[key], key


def test_summary_reviews_not_a_list_drops_only_the_review_fields(seat420):
    good = fold.seat_summary_from_seat(seat420)
    seat420["reviews"] = {"count": 72}
    summary = fold.seat_summary_from_seat(seat420)
    for key in ("reviewed", "review_status", "mean_score", "scored", "roles"):
        assert summary[key] is None, key
    # last_active falls back to the newest acceptedAt (work[0], 04:10:09.585Z)
    assert summary["last_active_ts"] == _iso("2026-09-21T04:10:09.585Z")
    for key in ("attempts", "accepted", "online", "owner", "paired_ts",
                "collaborators", "runtime"):
        assert summary[key] == good[key], key


def test_summary_no_parseable_stamp_anywhere_is_last_active_none(seat420):
    seat420["work"] = "gone"
    for review in seat420["reviews"]:
        review["sentAt"] = None
    assert fold.seat_summary_from_seat(seat420)["last_active_ts"] is None


def test_summary_bool_value_is_not_a_score(seat420):
    """``True == 1`` in Python; a hand-edited ``true`` must not count as a score."""
    seat420["reviews"][0]["value"] = True
    seat420["reviews"][1]["value"] = "1"
    seat420["reviews"][2]["value"] = None
    seat420["reviews"][3]["value"] = float("nan")
    summary = fold.seat_summary_from_seat(seat420)
    assert summary["scored"] == 68
    assert summary["reviewed"] == 72          # still reviews, just not scores
    assert summary["mean_score"] == 1.0


def test_summary_mean_score_is_over_the_numeric_values(seat420):
    seat420["reviews"][0]["value"] = 0
    seat420["reviews"][1]["value"] = 0.5
    summary = fold.seat_summary_from_seat(seat420)
    assert summary["scored"] == 72
    assert summary["mean_score"] == round((70 + 0.5) / 72, 2)   # 0.98


def test_summary_empty_lists_are_real_zeros_not_none(seat420):
    seat420.update({"attempts": 0, "accepted": 0, "work": [], "reviews": [],
                    "collaborators": [], "runtimes": []})
    summary = fold.seat_summary_from_seat(seat420)
    assert summary["attempts"] == 0 and summary["accepted"] == 0
    assert summary["reviewed"] == 0 and summary["scored"] == 0
    assert summary["review_status"] == {"sent": 0, "submitted": 0, "queued": 0}
    assert summary["roles"] == [] and summary["collaborators"] == 0
    assert summary["mean_score"] is None       # no score is not a zero score
    assert summary["runtime"] is None and summary["last_active_ts"] is None


def test_summary_roles_skip_non_strings_and_tie_break_on_role(seat420):
    seat420["reviews"] = [
        {"role": "review"}, {"role": "implement"}, {"role": None}, {"role": 3}, "junk",
    ]
    summary = fold.seat_summary_from_seat(seat420)
    assert summary["roles"] == [{"role": "implement", "count": 1}, {"role": "review", "count": 1}]
    assert summary["reviewed"] == 4           # the Mapping members; "junk" is no review


def test_summary_carries_third_party_strings_raw(seat420):
    seat420["runtimes"] = [{"id": "[bold]x", "version": "[/]"}]
    seat420["reviews"][0]["role"] = "[red]r"
    summary = fold.seat_summary_from_seat(seat420)
    assert summary["runtime"] == "[bold]x [/]"
    assert {"role": "[red]r", "count": 1} in summary["roles"]


def test_summary_does_not_mutate_the_payload(seat420):
    before = copy.deepcopy(seat420)
    fold.seat_summary_from_seat(seat420)
    fold.seat_work_rows(seat420)
    fold.seat_review_rows(seat420)
    assert seat420 == before


# ---------------------------------------------------------------------------
# seat_work_rows
# ---------------------------------------------------------------------------


def test_work_rows_420_source_order_frozen_shape(seat420):
    rows = fold.seat_work_rows(seat420)
    assert len(rows) == 12                                   # accepted == len(work)
    for row in rows:
        assert tuple(row) == SURF_ROW_KEYS["swarm_seat_work_rows"]
    assert rows[0] == {
        "job_id": "88d94855-f273-47c6-9db1-431b8a38a2de",
        "node_key": "adversarial_review",
        "role": "review",
        "job_state": "completed",
        "objective": seat420["work"][0]["objective"],
        "accepted_ts": _iso("2026-09-21T04:10:09.585Z"),
    }
    assert rows[-1]["accepted_ts"] == _iso("2026-09-20T17:48:55.121Z")
    assert [r["job_id"] for r in rows] == [w["jobId"] for w in seat420["work"]]


def test_work_rows_every_fixture_counts_its_accepted():
    for name, accepted in (("seat_0", 26), ("seat_1649", 3), ("seat_516", 4)):
        assert len(fold.seat_work_rows(swarm_seat_capture(name))) == accepted


def test_work_rows_a_bad_field_is_none_in_that_cell_and_junk_members_are_skipped(seat420):
    seat420["work"][0]["acceptedAt"] = "never"
    seat420["work"][0]["objective"] = ["x"]
    seat420["work"].insert(1, "junk")
    rows = fold.seat_work_rows(seat420)
    assert len(rows) == 12
    assert rows[0]["accepted_ts"] is None and rows[0]["objective"] is None
    assert rows[0]["job_id"] == "88d94855-f273-47c6-9db1-431b8a38a2de"


@pytest.mark.parametrize("payload", [None, [], {"work": "x"}, {"work": None}, dict(UNKNOWN_SEAT)])
def test_work_rows_nothing_to_fold_is_empty(payload):
    assert fold.seat_work_rows(payload) == []


# ---------------------------------------------------------------------------
# seat_review_rows
# ---------------------------------------------------------------------------


def _by_job(rows, job_id):
    (row,) = [r for r in rows if r["job_id"] == job_id]
    return row


def test_review_rows_420_source_order_frozen_shape(seat420):
    rows = fold.seat_review_rows(seat420)
    assert len(rows) == 72
    for row in rows:
        assert tuple(row) == SWARM_SEAT_FEEDBACK_ROW_KEYS_NEXT
    assert rows[0] == {
        "value": 1, "verdict": "accepted", "status": "sent",
        "node_key": "oracle_assess", "role": "implement",
        "job_id": "80c853bd-8cd7-43e5-b13b-79ea17ce5027",
        "tx_hash": "0x77cb6b8fa584b75e926e2b694c6245c6d27c4bd2abad2265f9bbbcf3a5682c49",
        "chain_id": 1, "sent_ts": _iso("2026-09-21T06:42:05.562Z"),
    }
    assert [r["job_id"] for r in rows] == [r["jobId"] for r in seat420["reviews"]]


def test_review_rows_queued_and_submitted(seat420):
    rows = fold.seat_review_rows(seat420)
    queued = _by_job(rows, "7cdfacfa-cf28-43f4-bf80-ba537ce8b9be")
    assert queued["status"] == "queued"
    assert (queued["tx_hash"], queued["chain_id"], queued["sent_ts"]) == (None, None, None)
    submitted = _by_job(rows, "2fc17259-07a4-4841-b4e1-a3fd827cd2a9")
    assert submitted["status"] == "submitted" and submitted["sent_ts"] is None
    assert submitted["tx_hash"] == "0x221de6cb7fe6be24a1f4f34d5e4a1d887da004c384b13aacf36b79b30f0e10d3"
    assert submitted["chain_id"] == 1


def test_review_rows_queued_never_carries_a_tx_even_if_hand_edited(seat420):
    for review in seat420["reviews"]:
        if review["status"] == "queued":
            review.update({"txHash": "0xdead", "chainId": 1, "sentAt": "2026-09-21T06:00:00Z"})
    queued = _by_job(fold.seat_review_rows(seat420), "7cdfacfa-cf28-43f4-bf80-ba537ce8b9be")
    assert (queued["tx_hash"], queued["chain_id"], queued["sent_ts"]) == (None, None, None)


def test_review_rows_bad_fields_are_none_in_that_cell(seat420):
    seat420["reviews"][0].update({"value": True, "chainId": "1", "txHash": 5, "sentAt": "x"})
    row = fold.seat_review_rows(seat420)[0]
    assert (row["value"], row["chain_id"], row["tx_hash"], row["sent_ts"]) == (None, None, None, None)
    assert row["job_id"] == "80c853bd-8cd7-43e5-b13b-79ea17ce5027"


def test_review_rows_0_has_202():
    assert len(fold.seat_review_rows(swarm_seat_capture("seat_0"))) == 202


@pytest.mark.parametrize("payload", [None, "x", {"reviews": {}}, dict(UNKNOWN_SEAT)])
def test_review_rows_nothing_to_fold_is_empty(payload):
    assert fold.seat_review_rows(payload) == []


# ---------------------------------------------------------------------------
# roster_window
# ---------------------------------------------------------------------------


def test_roster_window_over_the_100_job_capture():
    jobs = swarm_seat_capture("jobs_window_100")["jobs"]
    window = fold.roster_window(jobs)
    assert tuple(window) == SWARM_ROSTER_WINDOW_FIELDS
    assert window == {"jobs": 100, "oldest_ts": _iso("2026-09-21T02:26:32.542Z")}  # oldest createdAt


def test_roster_window_empty_list_is_a_real_zero():
    assert fold.roster_window([]) == {"jobs": 0, "oldest_ts": None}


def test_roster_window_skips_junk_and_unparseable_stamps():
    jobs = [{"createdAt": "2026-09-21T05:00:00Z"}, {"createdAt": "nope"}, "junk",
            {"createdAt": "2026-09-21T03:00:00Z"}]
    assert fold.roster_window(jobs) == {"jobs": 3, "oldest_ts": _iso("2026-09-21T03:00:00Z")}


@pytest.mark.parametrize("jobs", [None, {"count": 100, "jobs": []}, "jobs", 100])
def test_roster_window_non_list_is_none(jobs):
    assert fold.roster_window(jobs) is None


# ---------------------------------------------------------------------------
# choose_seat (decision D1)
# ---------------------------------------------------------------------------

ROSTER = [
    {"token_id": 47, "agent_id": "50950"},
    {"token_id": 420, "agent_id": "50939"},
    {"token_id": 0, "agent_id": "50906"},
]


def _sel(token, agent, how):
    return {"token_id": token, "agent_id": agent, "selected_by": how}


def test_choose_seat_truth_table():
    # cursor on the roster wins over everything
    assert fold.choose_seat(ROSTER, 0, 420) == _sel(420, "50939", "cursor")
    # cursor off the roster falls through to saved
    assert fold.choose_seat(ROSTER, 0, 9999) == _sel(0, "50906", "saved")
    # saved on the roster
    assert fold.choose_seat(ROSTER, 420, None) == _sel(420, "50939", "saved")
    # nothing chosen -> the most active (rows[0])
    assert fold.choose_seat(ROSTER, None, None) == _sel(47, "50950", "most_active")
    # nothing at all
    assert fold.choose_seat(None, None, None) is None
    assert fold.choose_seat([], None, 5) is None


def test_choose_seat_saved_off_the_roster_is_shown_d1():
    assert fold.choose_seat(ROSTER, 1649, None) == _sel(1649, None, "saved")
    assert fold.choose_seat(ROSTER, 1649, 9999) == _sel(1649, None, "saved")


def test_choose_seat_saved_with_no_roster_at_all_d1():
    assert fold.choose_seat(None, 1649, None) == _sel(1649, None, "saved")
    assert fold.choose_seat([], 1649, 420) == _sel(1649, None, "saved")


def test_choose_seat_frozen_shape_and_no_unseen_token():
    for picked in (fold.choose_seat(ROSTER, 1649, None), fold.choose_seat(ROSTER, None, None),
                   fold.choose_seat(ROSTER, None, 420)):
        assert tuple(picked) == SWARM_SEAT_SELECTED_FIELDS


@pytest.mark.parametrize("bad", [True, False, -1, "420", 420.0])
def test_choose_seat_refuses_a_token_that_is_no_seat_id(bad):
    assert fold.choose_seat(ROSTER, bad, None) == _sel(47, "50950", "most_active")
    assert fold.choose_seat(ROSTER, None, bad) == _sel(47, "50950", "most_active")


def test_choose_seat_agent_id_is_the_roster_rows_string_else_none():
    rows = [{"token_id": 5, "agent_id": 50939}, {"token_id": 6}]
    assert fold.choose_seat(rows, None, 5)["agent_id"] is None
    assert fold.choose_seat(rows, 6, None)["agent_id"] is None


def test_choose_seat_skips_junk_rows_for_most_active():
    rows = ["junk", {"token_id": "7"}, {"token_id": 8, "agent_id": "1"}]
    assert fold.choose_seat(rows, None, None) == _sel(8, "1", "most_active")


# ---------------------------------------------------------------------------
# coerce_seat_slot
# ---------------------------------------------------------------------------


def test_coerce_seat_slot_accepts_an_ok_slot_and_an_unknown_seat_slot(seat420):
    slot = {"token": 420, "state": "ok", "seat": seat420}
    assert fold.coerce_seat_slot(slot) == slot
    unknown = {"token": 7, "state": "unknown_seat", "seat": None}
    assert fold.coerce_seat_slot(unknown) == unknown
    assert fold.coerce_seat_slot(MappingProxyType(unknown)) == unknown


def test_coerce_seat_slot_returns_exactly_the_three_fields(seat420):
    got = fold.coerce_seat_slot({"token": 420, "state": "ok", "seat": seat420, "extra": 1})
    assert tuple(got) == ("token", "state", "seat")


@pytest.mark.parametrize("slot", [
    {"token": True, "state": "ok", "seat": {"tokenId": "1"}},              # bool token
    {"token": -1, "state": "ok", "seat": {"tokenId": "1"}},                # negative
    {"token": "420", "state": "ok", "seat": {"tokenId": "420"}},           # str token
    {"token": 420.0, "state": "ok", "seat": {"tokenId": "420"}},
    {"token": 420, "state": "gone", "seat": {"tokenId": "420"}},           # unknown state
    {"token": 420, "state": None, "seat": {"tokenId": "420"}},
    {"token": 420, "state": "ok", "seat": None},                           # None seat with ok
    {"token": 420, "state": "ok", "seat": ["tokenId", "420"]},             # list seat
    {"token": 420, "state": "unknown_seat", "seat": {"tokenId": "420"}},   # seat with unknown
    {"token": 420, "state": "pending", "seat": {"tokenId": "420"}},        # a slot is a finished read
    {"token": 420, "state": "pending", "seat": None},
    {"token": 420, "state": "ok", "seat": {"tokenId": "421"}},             # seat for another token
    {"state": "ok", "seat": {"tokenId": "420"}},                           # missing token
])
def test_coerce_seat_slot_refuses(slot):
    assert fold.coerce_seat_slot(slot) is None


@pytest.mark.parametrize("payload", [None, [], [420, "ok", {}], "slot", 420])
def test_coerce_seat_slot_refuses_a_non_mapping(payload):
    assert fold.coerce_seat_slot(payload) is None


def test_states_the_fold_can_emit_are_frozen_states(seat420):
    assert fold.seat_state(seat420, 420) in SWARM_SEAT_STATES
    assert fold.seat_state(UNKNOWN_SEAT, 420) in SWARM_SEAT_STATES


def test_new_names_are_exported():
    for name in ("seat_state", "seat_summary_from_seat", "seat_work_rows", "seat_review_rows",
                 "roster_window", "choose_seat", "coerce_seat_slot"):
        assert name in fold.__all__, name
