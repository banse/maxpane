"""The capture rig's own tests -- driven by a canned transport, never the network.

``scripts/capture_curator_state.py`` is the one piece of this dashboard that is
*meant* to talk to Ethereum, which is exactly why its tests must not: the whole
point of the script is that it still works at 20:58:47 UTC on a night when
nothing can be retried, and a test that quietly depends on a live endpoint
proves nothing about that.  Every test here injects an opener; the ones that
must never reach a socket inject an opener that raises on use.

The script is loaded from its path rather than imported as a module, because it
is deliberately not importable: nothing in ``maxpane_dashboard/`` may depend on
``scripts/``.
"""

from __future__ import annotations

import importlib.util
import json
import os

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT_PATH = os.path.join(REPO_ROOT, "scripts", "capture_curator_state.py")
CAPTURES = os.path.join(REPO_ROOT, "tests", "fixtures", "curator", "captures")
LIVE = os.path.join(CAPTURES, "live")


def _load_script():
    spec = importlib.util.spec_from_file_location("capture_curator_state", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cap = _load_script()


# --------------------------------------------------------------------------
# Canned transports.
# --------------------------------------------------------------------------


class Recorder:
    """An opener with a scripted answer per URL, recording every request."""

    def __init__(self, answers):
        #: ``{url: response}`` where a response is a dict/list (200 JSON), a
        #: ``(status, bytes)`` pair, or a callable taking the decoded payload.
        self.answers = answers
        self.requests = []

    def __call__(self, url, body, headers, timeout):
        payload = json.loads(body.decode("utf-8")) if body else None
        self.requests.append(
            {"url": url, "payload": payload, "headers": headers, "timeout": timeout}
        )
        answer = self.answers[url]
        if callable(answer):
            answer = answer(payload)
        if isinstance(answer, tuple):
            return answer
        return 200, json.dumps(answer).encode("utf-8")


def exploding_opener(url, body, headers, timeout):
    raise AssertionError(f"the network was touched: {url}")


def _no_sleep(_seconds):
    return None


def _ok(result, request_id=1):
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _batch_ok(results):
    return [
        {"jsonrpc": "2.0", "id": index + 1, "result": value}
        for index, value in enumerate(results)
    ]


WORD_ZERO = "0x" + "00" * 32
WORD_ONE = "0x" + "00" * 31 + "01"


# --------------------------------------------------------------------------
# Keccak / selectors -- computed, and proven not to be SHA-3.
# --------------------------------------------------------------------------


def test_the_inlined_keccak_reproduces_a_vendored_selector():
    # If this is ever SHA-3 instead of Keccak-256 the four bytes stay
    # plausible-looking and call nothing at all, so the script checks itself
    # before it sends a computed selector.
    assert cap.selector("isSettled()") == "0x3270bb5b"
    assert cap.keccak_self_check() is True


def test_keccak_matches_a_famous_selector_outside_this_contract():
    assert cap.selector("transfer(address,uint256)") == "0xa9059cbb"


def test_the_curve_selectors_are_computed_not_typed():
    # Recomputing them here from the same literals is a tautology; what is not
    # a tautology is that they differ from SHA-3's answer for the same string.
    import hashlib

    for signature in cap.CURVE_UINT_FUNCTIONS + cap.CURVE_ADDRESS_FUNCTIONS:
        sha3 = "0x" + hashlib.sha3_256(signature.encode()).digest()[:4].hex()
        assert cap.selector(signature) != sha3


# --------------------------------------------------------------------------
# The selector table.
# --------------------------------------------------------------------------


def test_the_selectors_are_read_out_of_the_committed_batch_payload():
    selectors, source = cap.load_selectors()
    assert source == "batch.json"
    assert len(selectors) == 21


def test_the_inlined_fallback_agrees_with_the_committed_batch():
    # The fallback exists so the script runs from a checkout without the
    # fixtures.  It is only useful if it has not drifted from the list that
    # actually answered 21/21 on publicnode.
    from_file, _ = cap.load_selectors()
    inlined = [sel for sel, _ in cap.VIEWS]
    assert from_file == inlined


def test_a_missing_batch_file_falls_back_to_the_inlined_copy(tmp_path):
    selectors, source = cap.load_selectors(str(tmp_path / "nope.json"))
    assert source == "inlined"
    assert selectors == [sel for sel, _ in cap.VIEWS]


def test_every_selector_has_a_signature():
    assert set(cap.SELECTOR_NAMES) == {sel for sel, _ in cap.VIEWS}
    assert all(name.endswith("()") for name in cap.SELECTOR_NAMES.values())


# --------------------------------------------------------------------------
# Decoding -- a failed read is None, never 0.
# --------------------------------------------------------------------------


def test_a_legitimate_zero_decodes_to_zero_and_a_failed_read_to_none():
    # currentHourTotal() at an hour boundary and ethNeededThisHour() during
    # grace are both honestly 0.  Confusing either with an outage is the bug
    # this repo keeps re-fixing.
    assert cap.decode_uint(WORD_ZERO) == 0
    assert cap.decode_uint(None) is None
    assert cap.decode_uint("0x") is None
    assert cap.decode_uint("0xnonsense") is None


def test_a_two_word_return_decodes_word_by_word():
    # lastActiveHour() returns (hour, total) and firstHourOf() returns
    # (hour, hasJoined) -- two words, not scalars.
    word = "0x" + f"{2:064x}" + f"{123456:064x}"
    assert cap.decode_uint(word, 0) == 2
    assert cap.decode_uint(word, 1) == 123456
    assert cap.decode_uint(word, 2) is None


def test_quantities_are_not_decoded_as_abi_words():
    # A block number is minimal-length hex; reading it with the 32-byte word
    # decoder made every eth_blockNumber look like a failed read.
    assert cap.hex_to_int("0x189378e") == 25769870
    assert cap.decode_uint("0x189378e") is None
    assert cap.hex_to_int(None) is None


def test_uint_and_address_arguments_are_left_padded_to_32_bytes():
    assert cap.encode_uint(10**18) == f"{10**18:064x}"
    assert len(cap.encode_uint(0)) == 64
    encoded = cap.encode_address("0x381fe486d87c7f2633c777f1b5be3105a2a51744")
    assert len(encoded) == 64
    assert encoded.endswith("381fe486d87c7f2633c777f1b5be3105a2a51744")
    assert encoded.startswith("0" * 24)
    with pytest.raises(ValueError):
        cap.encode_address("0xdeadbeef")


# --------------------------------------------------------------------------
# Transport: the User-Agent, retries, and status handling.
# --------------------------------------------------------------------------


def test_every_request_carries_a_real_user_agent():
    # publicnode answered HTTP 403 to python-urllib's default UA and accepted
    # the identical batch from curl.  H9.
    opener = Recorder({cap.STATE_URL: _ok("0x1")})
    cap.fetch_head(errors=[], opener=opener, sleeper=_no_sleep)
    agent = opener.requests[0]["headers"]["User-Agent"]
    assert agent
    lowered = agent.lower()
    assert "python" not in lowered
    assert "urllib" not in lowered
    assert "httpx" not in lowered


def test_a_post_declares_json_and_a_get_does_not():
    opener = Recorder({
        cap.STATE_URL: _ok("0x1"),
        f"{cap.BLOCKSCOUT_URL}/addresses/{cap.CONTRACT}/logs": {"items": []},
    })
    cap.fetch_head(errors=[], opener=opener, sleeper=_no_sleep)
    cap.fetch_blockscout(errors=[], opener=opener, sleeper=_no_sleep)
    assert opener.requests[0]["headers"]["Content-Type"] == "application/json"
    assert "Content-Type" not in opener.requests[1]["headers"]


def test_a_failing_request_is_retried_twice_with_backoff():
    attempts = {"n": 0}

    def flaky(url, body, headers, timeout):
        attempts["n"] += 1
        if attempts["n"] < 3:
            return 503, b"upstream unavailable"
        return 200, json.dumps(_ok("0x189378e")).encode()

    slept = []
    head = cap.fetch_head(errors=[], opener=flaky, sleeper=slept.append)
    assert head == 25769870
    assert attempts["n"] == 3
    assert slept == [1.0, 3.0]


def test_a_persistent_http_failure_raises_with_the_status_and_the_url():
    def dead(url, body, headers, timeout):
        return 403, b"Forbidden"

    with pytest.raises(cap.CaptureError) as excinfo:
        cap.http_json(cap.STATE_URL, {"a": 1}, opener=dead, sleeper=_no_sleep)
    assert excinfo.value.status == 403
    assert excinfo.value.url == cap.STATE_URL
    assert "403" in excinfo.value.message


def test_unparseable_json_is_a_capture_error_not_a_crash():
    def garbage(url, body, headers, timeout):
        return 200, b"<html>gateway</html>"

    with pytest.raises(cap.CaptureError):
        cap.http_json(cap.STATE_URL, {"a": 1}, opener=garbage, sleeper=_no_sleep)


# --------------------------------------------------------------------------
# Error classification -- on message text, never on code.
# --------------------------------------------------------------------------


def test_a_routing_message_is_an_endpoint_limitation_whatever_its_code():
    assert cap.looks_like_endpoint_limitation("Can't route your request")
    assert cap.looks_like_endpoint_limitation("method not supported: eth_getLogs")
    assert not cap.looks_like_endpoint_limitation("invalid params: fromBlock")


def test_a_range_complaint_is_recognised_by_its_words():
    assert cap.is_range_limitation("query returned more than 10000 results")
    assert cap.is_range_limitation("block range is too large")
    assert not cap.is_range_limitation("Can't route your request")


# --------------------------------------------------------------------------
# Stages.
# --------------------------------------------------------------------------


def test_the_state_round_is_one_batch_keyed_by_selector():
    selectors = ["0x3270bb5b", "0x020e185d"]
    opener = Recorder({cap.STATE_URL: _batch_ok([WORD_ZERO, WORD_ONE])})
    errors = []
    state = cap.fetch_state(selectors, errors=errors, opener=opener, sleeper=_no_sleep)
    assert len(opener.requests) == 1, "the 21 views must cost one round trip, not 21"
    assert state["0x3270bb5b"] == {"name": "isSettled()", "result": WORD_ZERO}
    assert state["0x020e185d"]["name"] == "currentHour()"
    assert errors == []
    sent = opener.requests[0]["payload"]
    assert [call["method"] for call in sent] == ["eth_call", "eth_call"]
    assert sent[0]["params"][0]["to"] == cap.CONTRACT.lower()
    assert sent[0]["params"][1] == "latest"


def test_one_reverting_view_does_not_lose_the_other_twenty():
    selectors = ["0x3270bb5b", "0x020e185d"]
    response = [
        {"jsonrpc": "2.0", "id": 1, "error": {"code": -32000, "message": "execution reverted"}},
        {"jsonrpc": "2.0", "id": 2, "result": WORD_ONE},
    ]
    opener = Recorder({cap.STATE_URL: response})
    errors = []
    state = cap.fetch_state(selectors, errors=errors, opener=opener, sleeper=_no_sleep)
    assert "result" not in state["0x3270bb5b"]
    assert "execution reverted" in state["0x3270bb5b"]["error"]
    assert state["0x020e185d"]["result"] == WORD_ONE
    assert len(errors) == 1 and errors[0]["url"] == cap.STATE_URL


def test_a_short_batch_is_recorded_as_an_error_not_as_a_silent_none():
    # The one path that could write a genuinely silent empty bundle: HTTP 200
    # with fewer items than calls.  Every view came back `result: None` while
    # `errors` stayed `[]`, so the archived bundle asserted a clean capture
    # that never happened -- and the manifest row said `err = 0` with every
    # decoded column `?`.  A 403 was loud; this was not.
    selectors = ["0x3270bb5b", "0x020e185d", "0xd8631b3d"]
    opener = Recorder({cap.STATE_URL: [{"jsonrpc": "2.0", "id": 2, "result": WORD_ONE}]})
    errors = []
    state = cap.fetch_state(selectors, errors=errors, opener=opener, sleeper=_no_sleep)
    assert state["0x020e185d"]["result"] == WORD_ONE, "the answered view survives"
    assert "result" not in state["0x3270bb5b"]
    assert "no response for id 1" in state["0x3270bb5b"]["error"]
    assert "no response for id 3" in state["0xd8631b3d"]["error"]
    assert [error["stage"] for error in errors] == ["state 0x3270bb5b", "state 0xd8631b3d"]
    assert all(error["url"] == cap.STATE_URL for error in errors)


def test_a_response_carrying_neither_result_nor_error_is_a_miss_too():
    # A renumbered or truncated item is one shape; `{"jsonrpc": .., "id": 1}`
    # is the other, and it reaches the same `result: None`.
    opener = Recorder({cap.STATE_URL: [{"jsonrpc": "2.0", "id": 1}]})
    errors = []
    state = cap.fetch_state(["0x3270bb5b"], errors=errors, opener=opener, sleeper=_no_sleep)
    assert "result" not in state["0x3270bb5b"]
    assert "no result for id 1" in state["0x3270bb5b"]["error"]
    assert len(errors) == 1


def test_an_unanswered_block_and_an_unstamped_header_both_reach_the_error_list():
    logs = [{"blockNumber": "0x10"}, {"blockNumber": "0x11"}]
    opener = Recorder({cap.STATE_URL: [{"jsonrpc": "2.0", "id": 2, "result": None}]})
    errors = []
    stamps = cap.fetch_block_timestamps(logs, errors=errors, opener=opener, sleeper=_no_sleep)
    assert stamps == {}, "still sparse -- a missing stamp renders --:--, never 00:00"
    assert "no response for id 1" in errors[0]["message"]
    assert "no timestamp" in errors[1]["message"], "a null block is a gap, not a silence"
    assert len(errors) == 2


def test_a_short_curve_batch_names_the_call_that_went_unanswered():
    weights = (0, 10**18)
    wallets = (("0x" + "11" * 20, "a wallet"),)
    opener = Recorder({cap.STATE_URL: [{"jsonrpc": "2.0", "id": 1, "result": WORD_ZERO}]})
    errors = []
    probe = cap.fetch_curve_probe(
        errors=errors, weights=weights, wallets=wallets, opener=opener, sleeper=_no_sleep,
    )
    assert probe["weights"][0]["result"] == WORD_ZERO
    assert "no response for id 2" in probe["weights"][1]["error"]
    assert len(errors) == 3, "one unanswered previewPoints, one pointsOf, one weightOf"
    assert errors[0]["stage"] == f"curve previewPoints(uint256)({10**18})"


def test_a_bundle_from_a_short_batch_does_not_claim_a_clean_capture():
    # `errors: []` in a committed archive is a claim.  It has to be true.
    opener = _full_transport()
    opener.answers[cap.STATE_URL] = lambda payload: (
        [] if isinstance(payload, list) else _ok("0x189378e")
    )
    bundle = cap.capture(label="settlement", skip_logs=True, skip_blockscout=True,
                         opener=opener, now=1787000000, sleeper=_no_sleep)
    assert len(bundle["state"]) == 21
    assert bundle["errors"], "21 unanswered views must not archive as a clean bundle"
    assert cap.summarise(bundle)["views_answered"] == 0
    assert "21 error(s)" in cap.summary_line(bundle)
    assert cap.manifest_row("x.json", bundle).endswith("| 21 |\n"), "the err column bites"


def test_a_log_pool_answering_200_with_no_array_fails_over_rather_than_reading_empty():
    # `logs: []` is a real state (a fresh contract); an unreadable answer is
    # not, and it used to become one, with `logs_endpoint` naming the host that
    # never actually answered.
    opener = Recorder({
        cap.LOGS_URL: {"jsonrpc": "2.0", "id": 1},
        cap.LOGS_FALLBACK_URL: _ok([{"blockNumber": "0x1", "topics": []}]),
    })
    errors = []
    logs, endpoint = cap.fetch_logs(
        cap.DEPLOY_BLOCK, to_block=cap.DEPLOY_BLOCK + 10, errors=errors,
        opener=opener, sleeper=_no_sleep,
    )
    assert endpoint == cap.LOGS_FALLBACK_URL
    assert len(logs) == 1
    assert "not a list" in errors[0]["message"]


def test_the_log_sweep_fails_over_to_the_second_host_on_a_routing_message():
    # drpc answers -32602 for "can't route", and tenderly answers -32602 for a
    # range complaint.  The code is worthless; the words decide.  H10.
    routing = {"jsonrpc": "2.0", "id": 1,
               "error": {"code": -32602, "message": "Can't route your request"}}
    opener = Recorder({
        cap.LOGS_URL: routing,
        cap.LOGS_FALLBACK_URL: _ok([{"blockNumber": "0x1", "topics": []}]),
    })
    errors = []
    logs, endpoint = cap.fetch_logs(
        cap.DEPLOY_BLOCK, to_block=cap.DEPLOY_BLOCK + 10, errors=errors,
        opener=opener, sleeper=_no_sleep,
    )
    assert endpoint == cap.LOGS_FALLBACK_URL
    assert len(logs) == 1
    assert any("route" in error["message"] for error in errors)


def test_a_range_complaint_halves_the_window_and_never_follows_the_suggestion():
    # One provider's "suggested retry range" decrements by a single block per
    # round trip and livelocks anything that follows it verbatim.
    asked = []

    def transport(payload):
        params = payload["params"][0]
        frm, to = int(params["fromBlock"], 16), int(params["toBlock"], 16)
        asked.append((frm, to))
        if to - frm > 50:
            return {"jsonrpc": "2.0", "id": 1, "error": {
                "code": -32602,
                "message": "block range is too large, retry with [%d, %d]" % (frm, frm + 1),
            }}
        return _ok([{"blockNumber": hex(frm), "topics": []}])

    opener = Recorder({cap.LOGS_URL: transport})
    errors = []
    logs, endpoint = cap.fetch_logs(
        1000, to_block=1200, errors=errors, opener=opener, sleeper=_no_sleep,
    )
    assert endpoint == cap.LOGS_URL
    assert asked[0] == (1000, 1200)
    assert asked[1] == (1000, 1100), "the window halves; the suggestion is ignored"
    assert (1000, 1001) not in asked
    assert len(logs) == 4  # 200 blocks -> four sub-windows of 50
    assert [int(log["blockNumber"], 16) for log in logs] == sorted(
        int(log["blockNumber"], 16) for log in logs
    ), "the halves come back in block order"


def test_block_timestamps_cover_the_distinct_blocks_of_the_newest_logs():
    # Tenderly's logs carry no blockTimestamp, so the activity feed's HH:MM has
    # no other keyless source.  H14.
    logs = [{"blockNumber": "0x10"}, {"blockNumber": "0x10"}, {"blockNumber": "0x11"}]
    opener = Recorder({cap.STATE_URL: _batch_ok([
        {"timestamp": "0x6a821677"}, {"timestamp": "0x6a821683"},
    ])})
    stamps = cap.fetch_block_timestamps(logs, errors=[], opener=opener, sleeper=_no_sleep)
    sent = opener.requests[0]["payload"]
    assert [call["params"][0] for call in sent] == ["0x10", "0x11"], "distinct blocks only"
    assert all(call["params"][1] is False for call in sent), "headers, not full bodies"
    assert stamps == {"0x10": "0x6a821677", "0x11": "0x6a821683"}


def test_an_unresolved_block_is_absent_rather_than_stamped_zero():
    # A missing stamp must render --:-- downstream; a zero would render 00:00
    # and look like a real time at the epoch.
    logs = [{"blockNumber": "0x10"}, {"blockNumber": "0x11"}]
    response = [
        {"jsonrpc": "2.0", "id": 1, "result": {"timestamp": "0x6a821677"}},
        {"jsonrpc": "2.0", "id": 2, "error": {"code": -32000, "message": "unknown block"}},
    ]
    opener = Recorder({cap.STATE_URL: response})
    errors = []
    stamps = cap.fetch_block_timestamps(logs, errors=errors, opener=opener, sleeper=_no_sleep)
    assert stamps == {"0x10": "0x6a821677"}
    assert "0x11" not in stamps
    assert len(errors) == 1


def test_the_curve_probe_batches_twelve_weights_and_four_wallets():
    weights = (0, 10**18)
    wallets = (("0x" + "11" * 20, "a wallet"),)
    results = [WORD_ZERO] * (len(weights) + 2 * len(wallets))
    opener = Recorder({cap.STATE_URL: _batch_ok(results)})
    probe = cap.fetch_curve_probe(
        errors=[], weights=weights, wallets=wallets, opener=opener, sleeper=_no_sleep,
    )
    sent = opener.requests[0]["payload"]
    assert len(sent) == 4, "one batch: previewPoints x2, pointsOf, weightOf"
    preview = cap.selector("previewPoints(uint256)")
    assert sent[0]["params"][0]["data"] == preview + cap.encode_uint(0)
    assert sent[1]["params"][0]["data"] == preview + cap.encode_uint(10**18)
    assert probe["weights"][1]["argument"] == str(10**18)
    assert probe["wallets"][0]["note"] == "a wallet"
    # The real defaults are the ones the ledger's claims are made about.
    assert len(cap.CURVE_WEIGHTS) == 12
    assert len(cap.CURVE_WALLETS) == 4


# --------------------------------------------------------------------------
# The bundle.
# --------------------------------------------------------------------------


def _full_transport():
    logs = [{"address": cap.CONTRACT.lower(), "topics": ["0xdead"], "data": "0x",
             "blockNumber": "0x189378e", "transactionHash": "0xabc", "logIndex": "0x0"}]
    state_results = [WORD_ZERO] * 21

    def state(payload):
        if isinstance(payload, list) and payload[0]["method"] == "eth_getBlockByNumber":
            return _batch_ok([{"timestamp": "0x6a821677"}])
        if isinstance(payload, list):
            return _batch_ok(state_results)
        if payload["method"] == "eth_blockNumber":
            return _ok("0x189378e")
        if payload["method"] == "eth_getBalance":
            return _ok("0x0")
        raise AssertionError(f"unexpected state call: {payload}")

    return Recorder({
        cap.STATE_URL: state,
        cap.LOGS_URL: _ok(logs),
        f"{cap.BLOCKSCOUT_URL}/addresses/{cap.CONTRACT}/logs": {"items": [], "next_page_params": None},
    })


def test_a_bundle_is_one_self_describing_object():
    opener = _full_transport()
    bundle = cap.capture(label="post-grace", opener=opener, now=1787000000, sleeper=_no_sleep)
    assert bundle["label"] == "post-grace"
    assert bundle["captured_at"] == 1787000000
    assert bundle["captured_at_utc"] == "2026-08-17T20:53:20Z"
    assert bundle["chain_head"] == 25769870
    assert bundle["balance"] == "0x0"
    assert len(bundle["state"]) == 21
    assert len(bundle["logs"]) == 1
    assert bundle["logs_endpoint"] == cap.LOGS_URL
    assert bundle["block_timestamps"] == {"0x189378e": "0x6a821677"}
    assert bundle["blockscout_page_0"] == {"items": [], "next_page_params": None}
    assert bundle["errors"] == []
    assert bundle["endpoints"]["state"] == cap.STATE_URL


def test_raw_payloads_go_into_the_bundle_verbatim():
    # A capture that pretty-prints 19491 as 1.9491x is a capture that cannot be
    # replayed through the real decoder.
    opener = _full_transport()
    bundle = cap.capture(label="grace-late", opener=opener, now=1787000000, sleeper=_no_sleep)
    assert all(
        entry["result"].startswith("0x") and len(entry["result"]) == 66
        for entry in bundle["state"].values()
    )
    assert bundle["logs"][0]["blockNumber"] == "0x189378e"


def test_a_dead_log_pool_still_produces_a_bundle():
    # Three sections out of four at 20:58 UTC beats no bundle forever.
    opener = _full_transport()
    opener.answers[cap.LOGS_URL] = (502, b"bad gateway")
    opener.answers[cap.LOGS_FALLBACK_URL] = (502, b"bad gateway")
    bundle = cap.capture(label="settlement", opener=opener, now=1787000000, sleeper=_no_sleep)
    assert len(bundle["state"]) == 21
    assert bundle["logs"] == []
    assert bundle["logs_endpoint"] is None
    assert [error["stage"] for error in bundle["errors"]] == ["logs", "logs"]
    assert all(error["url"] for error in bundle["errors"])


def test_the_capture_never_asks_for_a_key_and_never_writes_the_chain():
    opener = _full_transport()
    cap.capture(label="grace-late", opener=opener, curve_probe=True,
                now=1787000000, sleeper=_no_sleep)
    for request in opener.requests:
        assert "Authorization" not in request["headers"]
        assert "?" not in request["url"], "a query string is where an API key would hide"
        assert not any(word in request["url"].lower()
                       for word in ("key=", "token", "apikey", "auth"))
        payload = request["payload"]
        calls = payload if isinstance(payload, list) else [payload] if payload else []
        for call in calls:
            assert call["method"] in {
                "eth_call", "eth_getBalance", "eth_blockNumber",
                "eth_getLogs", "eth_getBlockByNumber",
            }


# --------------------------------------------------------------------------
# Writing: never overwrite, always index.
# --------------------------------------------------------------------------


def test_a_second_run_in_the_same_second_never_overwrites_the_first(tmp_path):
    bundle = {"label": "hour-boundary", "captured_at": 1787000000,
              "captured_at_utc": "2026-08-17T20:53:20Z", "state": {}, "logs": []}
    first = cap.write_bundle(bundle, directory=str(tmp_path))
    second = cap.write_bundle(bundle, directory=str(tmp_path))
    assert os.path.basename(first) == "20260817T205320Z_hour-boundary.json"
    assert os.path.basename(second) == "20260817T205320Z_hour-boundary-2.json"
    assert os.path.exists(first)


def test_the_manifest_gets_its_header_once_and_a_row_per_bundle(tmp_path):
    bundle = {"label": "grace-late", "captured_at": 1787000000,
              "captured_at_utc": "2026-08-17T20:53:20Z",
              "state": {cap.SEL_CURRENT_HOUR: {"name": "currentHour()",
                                               "result": "0x" + f"{24:064x}"},
                        cap.SEL_IS_SETTLED: {"name": "isSettled()", "result": WORD_ZERO}},
              "logs": [], "errors": []}
    cap.write_bundle(bundle, directory=str(tmp_path))
    cap.write_bundle(bundle, directory=str(tmp_path))
    manifest = (tmp_path / "MANIFEST.md").read_text()
    assert manifest.count("| bundle | captured (UTC) |") == 1
    rows = [line for line in manifest.splitlines() if line.startswith("| `2026")]
    assert len(rows) == 2
    assert "| 24 |" in rows[0]
    assert "| false |" in rows[0]


def test_a_label_cannot_escape_the_capture_directory(tmp_path):
    bundle = {"label": "../../etc/passwd", "captured_at": 1787000000,
              "captured_at_utc": "2026-08-17T20:53:20Z", "state": {}, "logs": []}
    path = cap.write_bundle(bundle, directory=str(tmp_path))
    assert os.path.dirname(os.path.abspath(path)) == str(tmp_path)


# --------------------------------------------------------------------------
# The summary line and the manifest row, read off a real committed bundle.
# --------------------------------------------------------------------------


def _committed_bundle(name):
    with open(os.path.join(LIVE, name), "r", encoding="utf-8") as handle:
        return json.load(handle)


def test_the_summary_decodes_the_real_curve_probe_bundle():
    bundle = _committed_bundle("20260816T225143Z_curve-probe.json")
    summary = cap.summarise(bundle)
    assert summary["views_answered"] == 21
    assert summary["views_total"] == 21
    assert summary["current_hour"] == 2
    assert summary["early_bps"] == 18800
    assert summary["settled"] is False
    assert summary["eth_needed_wei"] == 0, "grace: honestly zero, not a failed read"
    assert summary["balance_wei"] == 0, "nothing has ever been force-fed"
    assert summary["errors"] == 0


def test_the_real_curve_probe_returns_match_the_contracts_floor():
    # The onchain witness for H7: points = (isqrt(weight) * 1000) // 1e9, with
    # the multiplication before the division and no rounding anywhere.
    import math

    bundle = _committed_bundle("20260816T225143Z_curve-probe.json")
    entries = bundle["curve_probe"]["weights"]
    assert len(entries) == 12
    for entry in entries:
        weight = int(entry["argument"])
        onchain = int(entry["result"], 16)
        assert onchain == (math.isqrt(weight) * 1000) // 10**9
    by_weight = {int(entry["argument"]): int(entry["result"], 16) for entry in entries}
    assert by_weight[10**18] == 1000
    assert by_weight[10**9] == 0, "the floor is real: a gigawei of weight is worth no points"
    assert by_weight[2000 * 10**18] == 44721


def test_a_manifest_row_states_the_phase_facts_of_a_real_bundle():
    bundle = _committed_bundle("20260816T225143Z_curve-probe.json")
    row = cap.manifest_row("20260816T225143Z_curve-probe.json", bundle)
    assert row.startswith("| `20260816T225143Z_curve-probe.json` |")
    assert "| curve-probe |" in row
    assert "| 18,800 |" in row
    assert "| false |" in row
    assert row.endswith("|\n")


def test_the_row_that_records_death_is_the_one_that_stands_out():
    # The night this matters, the operator is reading MANIFEST.md by eye to
    # find the first bundle that flipped.
    settled = {"label": "settlement", "captured_at": 1787000000,
               "captured_at_utc": "2026-08-17T20:53:20Z", "logs": [], "errors": [],
               "state": {cap.SEL_IS_SETTLED: {"name": "isSettled()", "result": WORD_ONE},
                         cap.SEL_CURRENT_HOUR: {"name": "currentHour()",
                                                "result": "0x" + f"{24:064x}"}}}
    row = cap.manifest_row("x.json", settled)
    assert "| **true** |" in row
    assert cap.summarise(settled)["settled"] is True
    assert "isSettled=true" in cap.summary_line(settled)


def test_a_bundle_whose_state_round_failed_reads_as_unknown_not_as_zero():
    # Every decoded column has to be able to say "I do not know" -- printing 0
    # for a failed read is how an outage becomes a fact in the archive.
    broken = {"label": "settlement", "captured_at": 1787000000,
              "captured_at_utc": "2026-08-17T20:53:20Z", "state": {}, "logs": [],
              "errors": [{"stage": "state", "url": cap.STATE_URL, "message": "HTTP 403"}]}
    summary = cap.summarise(broken)
    assert summary["settled"] is None
    assert summary["current_hour"] is None
    assert summary["views_answered"] == 0
    row = cap.manifest_row("x.json", broken)
    assert row.count("| ? |") >= 5
    assert "| 0.0000 |" not in row and "| 0.00 |" not in row, "no fabricated zeroes"
    assert "isSettled=?" in cap.summary_line(broken)


def test_the_summary_line_names_the_states_an_operator_is_hunting():
    bundle = _committed_bundle("20260816T225143Z_curve-probe.json")
    line = cap.summary_line(bundle)
    assert "21/21 views" in line
    assert "isSettled=false" in line
    assert "hour=2" in line


# --------------------------------------------------------------------------
# The timed window sweep.
# --------------------------------------------------------------------------


def test_the_next_boundary_is_derived_from_launch_time():
    # Every crossing is at HH:58:47 UTC, but the arithmetic is launchTime's,
    # not the wall clock's.
    launch = 1786910327
    assert cap.next_hour_boundary(launch) == launch + 3600
    assert cap.next_hour_boundary(launch + 1) == launch + 3600
    assert cap.next_hour_boundary(launch + 3599) == launch + 3600
    assert cap.next_hour_boundary(launch + 3600) == launch + 7200
    # 2026-08-17 20:58:47 UTC, the earliest possible settlement.
    assert cap.next_hour_boundary(launch + 24 * 3600 + 5) == launch + 25 * 3600


def _utc(text):
    """``"2026-08-17 20:57:30"`` -> an epoch second, UTC, no tz database."""
    import calendar
    import time as _time

    return calendar.timegm(_time.strptime(text, "%Y-%m-%d %H:%M:%S"))


def test_a_wall_clock_start_still_ahead_is_todays_instant():
    now = 1786910327  # 2026-08-16 19:58:47 UTC
    assert _utc("2026-08-16 19:58:47") == now
    assert cap.parse_start_at("20:58:20", now) == now + 3573
    assert cap.parse_start_at("@1787000000", now) == 1787000000
    assert cap.parse_start_at("boundary", now) == now + 3600
    with pytest.raises(ValueError):
        cap.parse_start_at("tea time", now)


def test_a_start_instant_that_has_just_gone_means_now_not_tomorrow():
    # The most expensive bug this rig could have had.  The runbook says to type
    # `--start-at 20:57:00` at 20:57 and `--start-at 19:58:52` at 19:58; firing
    # either one second late used to resolve to the SAME TIME TOMORROW, print
    # one line of stderr and block for ~86 400 s.  The settlement transition
    # happens once, at 20:58:47 UTC, with no transaction and no log.
    for target, wall, missed_by in (
        ("20:57:00", "2026-08-17 20:57:30", 30),      # capture C, 30 s late
        ("19:58:52", "2026-08-17 19:59:10", 18),      # capture B, 18 s late
        ("20:00:00", "2026-08-17 20:01:00", 60),      # the deficit poll
        ("22:58:22", "2026-08-17 23:00:00", 98),      # an hour-boundary sweep
    ):
        now = _utc(wall)
        resolved = cap.parse_start_at(target, now)
        assert now - resolved == missed_by, f"{target} typed at {wall}"
        assert resolved < now + 60, "a missed start must never arm a day-long wait"


def test_only_a_time_hours_behind_is_read_as_tomorrows():
    # The rollover is still there for the case it was written for: a time far
    # enough back to be nobody's "I am a bit late".
    now = _utc("2026-08-17 20:00:00")
    assert cap.parse_start_at("19:00:00", now) == now - 3600      # an hour ago -> now
    assert cap.parse_start_at("13:59:59", now) == now - 21601 + 86400  # 6 h 0 m 1 s -> tomorrow
    assert cap.parse_start_at("14:00:01", now) == now - 21599     # 5 h 59 m 59 s -> now
    assert cap.PAST_START_GRACE_SECONDS == 6 * 3600


def test_a_start_that_went_as_midnight_passed_is_not_a_day_away():
    # The mirror of the same bug: the crossings are at HH:58:47, so 23:58:22 is
    # a real sweep instant.  Typed 98 s late, "today's 23:58:22" is 23 h 58 m
    # AHEAD -- which is the day-long wait wearing a different hat.
    now = _utc("2026-08-18 00:00:00")
    assert cap.parse_start_at("23:58:22", now) == _utc("2026-08-17 23:58:22")
    assert cap.parse_start_at("23:58:22", now) < now


def test_waiting_sleeps_in_small_steps_and_returns_at_the_instant():
    clock = {"t": 100.0}
    slept = []

    def sleeper(seconds):
        slept.append(seconds)
        clock["t"] += seconds

    cap.wait_until(103.5, now=lambda: clock["t"], sleeper=sleeper)
    assert sum(slept) == pytest.approx(3.5)
    assert max(slept) <= 1.0, "a long sleep swallows Ctrl-C at the worst moment"
    assert clock["t"] >= 103.5


def test_a_past_target_does_not_wait_at_all():
    cap.wait_until(10, now=lambda: 20, sleeper=lambda s: pytest.fail("slept anyway"))


class _Args:
    label = "hour-boundary"
    logs_from = cap.DEPLOY_BLOCK
    curve_probe = False
    no_logs = True
    no_blockscout = True
    dry_run = True
    out_dir = ""
    start_at = None
    every = 0.0
    repeat = 1


def test_a_window_sweep_is_one_command_and_does_not_drift(capsys):
    # The slot is start + i*every, not "previous + every": a 3-second round
    # trip must not walk a boundary sweep off the boundary.
    clock = {"t": 1000.0}

    def sleeper(seconds):
        clock["t"] += seconds

    def slow_opener(url, body, headers, timeout):
        payload = json.loads(body.decode())
        if isinstance(payload, list):
            clock["t"] += 1.0  # the state round is what costs time
            return 200, json.dumps(_batch_ok([WORD_ZERO] * len(payload))).encode()
        if payload["method"] == "eth_blockNumber":
            return 200, json.dumps(_ok("0x1")).encode()
        return 200, json.dumps(_ok("0x0")).encode()

    args = _Args()
    args.every, args.repeat = 4.0, 3
    cap.run_series(args, opener=slow_opener, now=lambda: clock["t"], sleeper=sleeper)
    lines = [line for line in capsys.readouterr().out.splitlines() if line]
    assert len(lines) == 3
    # Slots at +0, +4, +8; the last capture costs one more second.  Scheduling
    # from "previous + every" instead would land at +11.
    assert clock["t"] == pytest.approx(1000.0 + 8.0 + 1.0)


def test_a_sweep_waits_for_its_start_instant_before_the_first_capture(capsys):
    clock = {"t": 1786910327.0}

    def sleeper(seconds):
        clock["t"] += seconds

    def opener(url, body, headers, timeout):
        payload = json.loads(body.decode())
        if isinstance(payload, list):
            return 200, json.dumps(_batch_ok([WORD_ZERO] * len(payload))).encode()
        return 200, json.dumps(_ok("0x1")).encode()

    args = _Args()
    args.start_at = "20:58:20"
    cap.run_series(args, opener=opener, now=lambda: clock["t"], sleeper=sleeper)
    assert clock["t"] >= 1786910327 + 3573
    assert "waiting until 2026-08-16T20:58:20Z" in capsys.readouterr().err


def test_a_sweep_fired_late_captures_now_and_still_takes_every_capture(capsys):
    # 20:57:30 on settlement night, typing the runbook's own command thirty
    # seconds late.  It must capture immediately and say so -- not arm a
    # 86 370-second wait behind one line of stderr and lose the transition.
    clock = {"t": float(_utc("2026-08-17 20:57:30"))}

    def sleeper(seconds):
        clock["t"] += seconds

    def opener(url, body, headers, timeout):
        payload = json.loads(body.decode())
        if isinstance(payload, list):
            return 200, json.dumps(_batch_ok([WORD_ZERO] * len(payload))).encode()
        return 200, json.dumps(_ok("0x1")).encode()

    args = _Args()
    args.label, args.start_at = "settlement", "20:57:00"
    args.every, args.repeat = 4.0, 3
    cap.run_series(args, opener=opener, now=lambda: clock["t"], sleeper=sleeper)

    captured = capsys.readouterr()
    assert len([line for line in captured.out.splitlines() if line]) == 3
    assert "passed 30 s ago" in captured.err
    assert "20:57:00Z" in captured.err
    # The grid re-anchors to the real start, so the whole sweep is 8 s of
    # spacing -- and nothing anywhere near a day.
    assert clock["t"] == pytest.approx(_utc("2026-08-17 20:57:30") + 8.0)
    assert clock["t"] < _utc("2026-08-17 20:58:47"), "still ahead of the boundary"


# --------------------------------------------------------------------------
# Structure: standalone, keyless, read-only.
# --------------------------------------------------------------------------


def _source():
    with open(SCRIPT_PATH, "r", encoding="utf-8") as handle:
        return handle.read()


def _imported_roots():
    """Top-level module names the script imports, read out of its AST.

    Grepping the text does not work and should not: the module docstring names
    ``maxpane_dashboard`` on purpose, to say that the keccak below is a *copy*
    of the package's and why.  What matters is the import list.
    """
    import ast

    roots = set()
    for node in ast.walk(ast.parse(_source())):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_the_script_imports_nothing_but_the_standard_library():
    # It has to run from a bare checkout with no venv, at short notice, by
    # someone who has read nothing else.  One `import httpx` breaks that.
    import sys

    roots = _imported_roots()
    assert "maxpane_dashboard" not in roots
    assert not roots & {"httpx", "requests", "web3", "eth_abi", "eth_hash", "pytest"}
    assert "urllib" in roots
    stdlib = set(getattr(sys, "stdlib_module_names", ()))
    if stdlib:  # 3.10+
        assert roots <= stdlib | {"__future__"}


def test_the_script_never_names_a_write_method_or_a_key():
    source = _source().lower()
    for banned in (
        "eth_sendtransaction", "eth_sendrawtransaction", "eth_sign", "personal_",
        "private_key", "privatekey", "keystore", "mnemonic", "api_key", "apikey",
        "authorization",
    ):
        assert banned not in source, f"{banned} has no business in a read-only rig"


def test_no_banned_host_is_reachable_from_the_defaults():
    # publicnode refuses archive eth_getLogs, so it must not be in the logs
    # pool; the keyed and dead hosts must not be anywhere.  H11.
    pools = (cap.STATE_URL, cap.LOGS_URL, cap.LOGS_FALLBACK_URL, cap.BLOCKSCOUT_URL)
    for banned in ("llamarpc", "ankr", "cloudflare-eth", "reservoir", "alchemy",
                   "infura", "etherscan"):
        assert not any(banned in url for url in pools)
    assert "publicnode" not in cap.LOGS_URL
    assert "publicnode" not in cap.LOGS_FALLBACK_URL


def test_the_self_test_asks_one_question_and_reports_the_answer(capsys):
    opener = Recorder({cap.STATE_URL: _ok("0x189378e")})
    assert cap.self_test(opener=opener, sleeper=_no_sleep) == 0
    assert capsys.readouterr().out.strip() == "OK 25769870"
    assert len(opener.requests) == 1
    assert opener.requests[0]["payload"]["method"] == "eth_blockNumber"


def test_the_self_test_reports_a_403_rather_than_pretending(capsys):
    def forbidden(url, body, headers, timeout):
        return 403, b"Forbidden"

    assert cap.self_test(opener=forbidden, sleeper=_no_sleep) == 1
    assert "403" in capsys.readouterr().err


def test_nothing_here_reaches_the_network():
    # The structural half of "no test may touch the network": every stage
    # takes the opener, so an exploding one proves there is no second path out.
    errors = []
    with pytest.raises(AssertionError):
        cap.fetch_head(errors=None, opener=exploding_opener, sleeper=_no_sleep)
    for stage in (
        lambda: cap.fetch_state(["0x3270bb5b"], errors=errors, opener=exploding_opener,
                                sleeper=_no_sleep),
        lambda: cap.fetch_balance(errors=errors, opener=exploding_opener, sleeper=_no_sleep),
        lambda: cap.fetch_blockscout(errors=errors, opener=exploding_opener,
                                     sleeper=_no_sleep),
    ):
        with pytest.raises(AssertionError):
            stage()
