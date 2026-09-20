"""``data/rpc_classify.py``: the hoisted RPC error tables, read as each client binds them.

Branch 10 WP-A moved five endpoint tables, three range tables and five copies
of the malformed-request code set into one attributed module.  The tables are
data; the policy that reads them stayed in each client.  So this file does not
test the shared functions in the abstract -- it walks **every committed error
payload** through each of the five clients' own module-level predicates and
asserts the *action* the client's ``_rpc`` would take: rotate to the next
endpoint, shrink the window, or treat the error as terminal.

Two rules the expectations obey, both of them CLAUDE.md conventions:

* **The expected action per probe per client is hand-typed** from reading each
  client's predicate, never produced by running the code.  A table derived from
  the implementation it is checking cannot fail.
* **No "rotate" case stands alone.**  The corpus carries genuine
  not-a-limitation bodies (``malformed_params``,
  ``multicall3_invalid_hex_callData``, tenderly's two ``invalid params``
  messages whose cap text sits in ``data`` where no predicate reads it), and
  :func:`test_the_expectations_would_not_survive_an_empty_fragment_table`
  proves the table bites by re-running every walk against an empty table.

Payload provenance: ``tests/fixtures/surf/pool4/rpc_error_states.json`` (4
sepolia probes), ``tests/fixtures/surf/pool4/log_range_messages.json`` (10
mainnet probes plus mevblocker's honest cap) and
``tests/fixtures/fwa/rpc_errors.json`` (14 entries, 9 live-captured).  Nothing
here reaches the network and nothing here is invented, with one labelled
exception: :data:`_MINIMAL_PAIRS`, which isolates single fragments so that
dropping one from the union is a *behavioural* failure and not only a
membership one.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from maxpane_dashboard.data import (
    cattown_client,
    curator_client,
    rpc_classify,
    rpc_common,
    surf_client,
    surf_pool4_client,
    ttt_client,
)

POOL4_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "surf" / "pool4"
FWA_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "fwa"


def _load(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# The three committed corpora, read as error bodies
# ---------------------------------------------------------------------------

#: ``label -> the JSON-RPC ``error`` member``, gathered from the fixtures.
#: Built by reading each file's recorded *response*; no message is retyped
#: here, so a re-capture that changes a provider's wording changes this map.
def _error_corpus() -> dict[str, dict]:
    out: dict[str, dict] = {}

    states = _load(POOL4_FIXTURES / "rpc_error_states.json")
    for probe in states["probes"]:
        err = (probe.get("response") or {}).get("error")
        if isinstance(err, dict):
            out[probe["label"]] = err

    ranges = _load(POOL4_FIXTURES / "log_range_messages.json")
    for probe in ranges["probes"]:
        err = (probe.get("response") or {}).get("error")
        if isinstance(err, dict):
            # The four failing drpc probes carry the identical sentence; one
            # entry is enough for the action table, and the spans get their own
            # test below.
            out.setdefault("drpc_ranges_over_10000", err)
    out["mevblocker_range_cap"] = ranges["mevblocker_range_cap"]["error"]

    fwa = _load(FWA_FIXTURES / "rpc_errors.json")["errors"]
    for label, entry in fwa.items():
        body = entry.get("parsed")
        if isinstance(body, list):  # publicnode's 429 answers a batch
            body = body[0]
        if isinstance(body, dict) and isinstance(body.get("error"), dict):
            out[f"fwa:{label}"] = body["error"]
    return out


ERRORS = _error_corpus()

ROTATE = "rotate"
SHRINK = "shrink"
TERMINAL = "terminal"

#: Hand-typed from each client's predicate, one row per committed payload.
#:
#: Columns are ``ttt``, ``curator``, ``surf``, ``surf_pool4``, ``cattown``.
#: Spans are left out here (``requested_span=None``): what a span changes has
#: its own test.  Reading a row:
#:
#: * ``ttt`` and ``cattown`` have no range table, so they only ever rotate or
#:   go terminal.
#: * ``curator`` binds the span family **and** the result-count family; ``surf``
#:   and ``surf_pool4`` bind the span family only -- the two ``max results``
#:   rows are where that shows.
#: * ``cattown`` reads a *Base* table with no malformed-code fallback, which is
#:   why so much of its column is ``terminal``: ``_rpc`` raises there rather
#:   than rotating, and ``test_contract_revert_does_not_rotate`` is the reason.
EXPECTED: dict[str, tuple[str, str, str, str, str]] = {
    # 1rpc's honest 50-block cap, wearing -32602 -- the code publicnode spends
    # on genuinely bad input. Message-first classification is the whole point.
    "range_capped_getLogs": (ROTATE, SHRINK, SHRINK, SHRINK, TERMINAL),
    # A getter the contract does not implement. Code 3 is not a malformed
    # code, so the Ethereum four rotate; cattown deliberately raises.
    "unknown_selector_revert": (ROTATE, ROTATE, ROTATE, ROTATE, TERMINAL),
    # Genuinely our bug: no limitation language, and -32602.
    "malformed_params": (TERMINAL, TERMINAL, TERMINAL, TERMINAL, TERMINAL),
    # drpc's free-plan sentence: "ranges over" is in both Ethereum families.
    "drpc_ranges_over_10000": (ROTATE, SHRINK, SHRINK, SHRINK, TERMINAL),
    # mevblocker's honest cap: "exceeds limit of" is a span fragment.
    "mevblocker_range_cap": (ROTATE, SHRINK, SHRINK, SHRINK, TERMINAL),
    # publicnode's archive gate, twice in the fwa corpus under two labels.
    "fwa:publicnode_eth_getLogs_refusal": (
        ROTATE, ROTATE, ROTATE, ROTATE, TERMINAL,
    ),
    "fwa:publicnode_archive_refusal": (ROTATE, ROTATE, ROTATE, ROTATE, TERMINAL),
    # drpc code 35, the same sentence as above, captured independently by FWA.
    "fwa:drpc_block_range_cap": (ROTATE, SHRINK, SHRINK, SHRINK, TERMINAL),
    # The cap text is in ``data``; ``message`` is only "invalid params". No
    # predicate reads ``data``, so this is terminal everywhere -- and it is the
    # sibling that stops the rotate rows passing for free.
    "fwa:tenderly_result_count_cap": (
        TERMINAL, TERMINAL, TERMINAL, TERMINAL, TERMINAL,
    ),
    "fwa:tenderly_suggested_range_off_by_one": (
        TERMINAL, TERMINAL, TERMINAL, TERMINAL, TERMINAL,
    ),
    # A real caller bug: bad hex in a Multicall3 payload.
    "fwa:multicall3_invalid_hex_callData": (
        TERMINAL, TERMINAL, TERMINAL, TERMINAL, TERMINAL,
    ),
    # ankr after it went keyed: "unauthorized"/"authenticate"/"api key".
    # cattown's Base table carries "unauthorized" too, so it rotates here.
    "fwa:ankr_now_keyed": (ROTATE, ROTATE, ROTATE, ROTATE, ROTATE),
    # OnFinality's 429 body: "too many" (Ethereum) / "too many requests" (Base).
    "fwa:onerpc_rate_limit_429": (ROTATE, ROTATE, ROTATE, ROTATE, ROTATE),
    # publicnode's 429: "rate limit" on both tables, and "personal token" --
    # which must not make it read as a permanent archive gate.
    "fwa:publicnode_rate_limit_429": (ROTATE, ROTATE, ROTATE, ROTATE, ROTATE),
    # "query returns too many logs" -- note *returns*, not *returned*: it
    # misses curator's result family and rotates. Recorded as-is.
    "fwa:drpc_result_cap_too_many_logs": (
        ROTATE, ROTATE, ROTATE, ROTATE, TERMINAL,
    ),
    # "query exceeds max results 20000": curator's result family catches it and
    # shrinks; surf and surf_pool4 bind the span family only and rotate.
    "fwa:drpc_result_cap_with_suggested_range": (
        ROTATE, SHRINK, ROTATE, ROTATE, TERMINAL,
    ),
    # drpc's code-30 timeout: "timeout"/"free plan"/"upgrade" all rotate.
    "fwa:drpc_free_plan_timeout": (ROTATE, ROTATE, ROTATE, ROTATE, TERMINAL),
}

CLIENT_NAMES = ("ttt", "curator", "surf", "surf_pool4", "cattown")


def _action(client: str, err, *, requested_span: int | None = None) -> str:
    """The branch *client*'s ``_rpc`` would take for *err*.

    Deliberately calls each client's **own** module-level predicates, not the
    shared functions: a binding that quietly stopped passing
    ``unstructured_is_limitation=False`` has to show up here.
    """
    if client == "ttt":
        return ROTATE if ttt_client._looks_like_endpoint_limitation(err) else TERMINAL
    if client == "cattown":
        return (
            ROTATE
            if cattown_client._looks_like_endpoint_limitation(err)
            else TERMINAL
        )
    if client == "curator":
        if curator_client._is_range_limitation(err, requested_span):
            return SHRINK
        return (
            ROTATE
            if curator_client._looks_like_endpoint_limitation(err)
            else TERMINAL
        )
    if client == "surf":
        if surf_client._is_range_limitation(err):
            return SHRINK
        return (
            ROTATE if surf_client._looks_like_endpoint_limitation(err) else TERMINAL
        )
    if client == "surf_pool4":
        if surf_pool4_client._is_range_limitation(err, requested_span):
            return SHRINK
        return (
            ROTATE
            if surf_pool4_client._looks_like_endpoint_limitation(err)
            else TERMINAL
        )
    raise AssertionError(client)  # pragma: no cover


# ---------------------------------------------------------------------------
# (i) every committed payload, through every binding
# ---------------------------------------------------------------------------


def test_every_committed_error_payload_is_in_the_expectation_table() -> None:
    """The walk covers the corpora, not a chosen subset of them."""
    assert set(ERRORS) == set(EXPECTED), (
        "a committed error payload has no hand-typed expectation (or vice "
        f"versa): {sorted(set(ERRORS) ^ set(EXPECTED))}"
    )


@pytest.mark.parametrize("label", sorted(EXPECTED))
def test_each_payload_takes_the_action_its_client_would_take(label: str) -> None:
    err = ERRORS[label]
    expected = dict(zip(CLIENT_NAMES, EXPECTED[label]))
    actual = {name: _action(name, err) for name in CLIENT_NAMES}
    assert actual == expected, f"{label}: {err.get('message')!r}"


def test_the_corpus_carries_all_three_actions_for_the_clients_that_have_them() -> None:
    """A column that is one word everywhere proves nothing."""
    for idx, name in enumerate(CLIENT_NAMES):
        seen = {row[idx] for row in EXPECTED.values()}
        expected_actions = (
            {ROTATE, TERMINAL} if name in ("ttt", "cattown") else
            {ROTATE, SHRINK, TERMINAL}
        )
        assert seen == expected_actions, f"{name} only ever answers {seen}"


def test_the_expectations_would_not_survive_an_empty_fragment_table() -> None:
    """No row passes against a predicate that matches nothing.

    Re-walks every payload with empty tables. If the expectation table were
    satisfiable without the fragments -- which is how a classification test
    quietly stops biting -- this would find no difference to report.
    """
    for label, err in ERRORS.items():
        stripped = {
            "ttt": (
                ROTATE
                if rpc_classify.looks_like_endpoint_limitation(err, fragments=())
                else TERMINAL
            ),
            "cattown": (
                ROTATE
                if rpc_classify.looks_like_endpoint_limitation(
                    err,
                    fragments=(),
                    unstructured_is_limitation=False,
                    check_codes=False,
                )
                else TERMINAL
            ),
        }
        real = {name: _action(name, err) for name in ("ttt", "cattown")}
        if real != stripped:
            break
    else:  # pragma: no cover -- would mean the tables carry no weight at all
        pytest.fail("every payload classifies the same with no fragments at all")


# ---------------------------------------------------------------------------
# (ii) the drpc sentence at four spans
# ---------------------------------------------------------------------------

#: The spans ``log_range_messages.json`` captured against ``eth.drpc.org``.
#: Every one of them came back with the *same* sentence naming 10000 blocks --
#: the host's real limit is archive depth (~64 blocks), not page width.
DRPC_SPANS = (403_200, 10_000, 2_400, 300)


def _drpc_error() -> dict:
    probes = _load(POOL4_FIXTURES / "log_range_messages.json")["probes"]
    failing = [
        p for p in probes
        if isinstance((p.get("response") or {}).get("error"), dict)
    ]
    assert {p["requested_span_blocks"] for p in failing} == set(DRPC_SPANS), (
        "the fixture no longer captures the four spans this test reasons about"
    )
    messages = {p["response"]["error"]["message"] for p in failing}
    assert len(messages) == 1, "the fixture's whole point is one sentence"
    return failing[0]["response"]["error"]


@pytest.mark.parametrize("span", DRPC_SPANS)
@pytest.mark.parametrize("client", ("curator", "surf_pool4"))
def test_a_named_limit_the_request_already_meets_rotates(
    client: str, span: int
) -> None:
    """``rules/data.md``: *a provider's error message is only evidence about
    the request it was actually reading.*

    drpc names 10000 blocks whatever it was asked for. Above that the complaint
    could be about the window, so shrinking is still the conservative guess;
    at or below it the message is provably not about this request, and halving
    a 300-block window to 150 is how the STAKERS panel went dark with the data
    one endpoint away.

    ``curator`` is new here (Branch 10 decision P3): it still holds
    ``eth.drpc.org`` in its log pool and had no guard.
    """
    err = _drpc_error()
    expected = SHRINK if span > 10_000 else ROTATE
    assert _action(client, err, requested_span=span) == expected


def test_without_a_span_the_drpc_sentence_still_shrinks() -> None:
    """The guard is opt-in, and its absence is the old behaviour exactly.

    ``surf_client`` passes no span -- it removed drpc from its mainnet log pool
    instead -- so it must keep shrinking, and so must a direct call.
    """
    err = _drpc_error()
    assert _action("surf", err) == SHRINK
    assert _action("curator", err) == SHRINK
    assert _action("surf_pool4", err) == SHRINK


def test_a_result_cap_stays_shrinkable_at_every_span() -> None:
    """The named-limit guard counts **blocks**; a result cap counts rows.

    "result limit of 10000 reached" names ten thousand results. Measured
    against a 2000-block page it would read as a limit the request already
    meets -- and curator would rotate away from the one recovery that works,
    losing the whole log tier that
    ``test_a_result_cap_halves_the_window_instead_of_killing_the_sweep``
    exists to protect. The two units stay apart.
    """
    err = {"code": -32005, "message": "result limit of 10000 reached"}
    for span in (curator_client.LOG_PAGE_BLOCKS, 300, 10_000, 403_200):
        assert _action("curator", err, requested_span=span) == SHRINK, span


def test_the_mevblocker_cap_is_read_as_the_cap_and_not_as_the_span() -> None:
    """Its message carries both numbers; the first one is the request's own."""
    err = ERRORS["mevblocker_range_cap"]
    assert rpc_classify.named_block_limit(err["message"].lower()) == 10_000
    assert _action("surf_pool4", err, requested_span=50_400) == SHRINK
    assert _action("surf_pool4", err, requested_span=10_000) == ROTATE


# ---------------------------------------------------------------------------
# (iii) a body that is not a JSON-RPC error object
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("err", ["boom", None, [], 0, ["error"]])
def test_an_unstructured_error_rotates_on_ethereum_and_raises_on_base(err) -> None:
    """The flip a single shared predicate would have swallowed silently.

    The four Ethereum clients err toward rotating: a wasted request reaches the
    same final failure, while treating a capability limit as terminal takes the
    dashboard offline with healthy endpoints unused. cattown answers ``False``
    and its ``_rpc`` raises instead -- and no cattown test covered this path
    before Branch 10, so the flip would have shipped green.
    """
    assert ttt_client._looks_like_endpoint_limitation(err) is True
    assert curator_client._looks_like_endpoint_limitation(err) is True
    assert surf_client._looks_like_endpoint_limitation(err) is True
    assert surf_pool4_client._looks_like_endpoint_limitation(err) is True
    assert cattown_client._looks_like_endpoint_limitation(err) is False

    assert curator_client._is_range_limitation(err) is False
    assert surf_client._is_range_limitation(err) is False
    assert surf_pool4_client._is_range_limitation(err) is False


def test_cattown_consults_no_malformed_code_fallback() -> None:
    """Base policy, not an Ethereum default that happened to be inherited.

    A reverted ``eth_call`` is the *contract's* answer. cattown's table is
    message-only, so an unrecognised message is terminal whatever the code --
    where the Ethereum four fall through to the code check and rotate.
    """
    revert = {"code": 3, "message": "execution reverted"}
    assert cattown_client._looks_like_endpoint_limitation(revert) is False
    assert ttt_client._looks_like_endpoint_limitation(revert) is True


# ---------------------------------------------------------------------------
# (iv) the bindings are the shared objects, not copies of them
# ---------------------------------------------------------------------------


def test_each_client_binds_the_shared_table_itself() -> None:
    """``is``, not ``==``: a re-typed copy that happens to compare equal today
    is exactly the drift this module was created to end."""
    for module in (ttt_client, curator_client, surf_client, surf_pool4_client):
        assert (
            module._ENDPOINT_LIMITATION_PATTERNS
            is rpc_classify.ETH_ENDPOINT_LIMITATION_FRAGMENTS
        ), module.__name__
        assert (
            module._MALFORMED_REQUEST_CODES is rpc_classify.MALFORMED_REQUEST_CODES
        ), module.__name__
    assert (
        cattown_client._ENDPOINT_LIMITATION_PATTERNS
        is rpc_classify.BASE_ENDPOINT_LIMITATION_FRAGMENTS
    )
    for module in (surf_client, surf_pool4_client):
        assert (
            module._RANGE_LIMITATION_PATTERNS is rpc_classify.RANGE_CAP_FRAGMENTS
        ), module.__name__
    assert curator_client._RANGE_LIMITATION_PATTERNS == (
        rpc_classify.RANGE_CAP_FRAGMENTS + rpc_classify.RESULT_CAP_FRAGMENTS
    )
    assert surf_pool4_client._named_block_limit is rpc_classify.named_block_limit


def test_cattown_does_not_bind_the_ethereum_table() -> None:
    """The one merge that would have been silent and wrong."""
    assert (
        cattown_client._ENDPOINT_LIMITATION_PATTERNS
        is not rpc_classify.ETH_ENDPOINT_LIMITATION_FRAGMENTS
    )
    assert not hasattr(cattown_client, "_RANGE_LIMITATION_PATTERNS")
    assert not hasattr(cattown_client, "_MALFORMED_REQUEST_CODES")
    assert not hasattr(ttt_client, "_RANGE_LIMITATION_PATTERNS")


# ---------------------------------------------------------------------------
# (v) the module stays a leaf
# ---------------------------------------------------------------------------


@pytest.mark.guard
def test_rpc_classify_imports_nothing_from_maxpane() -> None:
    """A table module that imports a client inverts the dependency graph.

    ``rpc_common`` is a leaf on purpose (stdlib plus ``httpx``); this one is a
    leaf on stdlib alone. The moment it reaches for a pool constant or a policy
    it stops being data and the circular-import hazard arrives with it.
    """
    tree = ast.parse(Path(rpc_classify.__file__).read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
    assert imported, "the AST walk found no imports at all -- it cannot bite"
    for name in imported:
        assert not name.startswith("maxpane_dashboard"), (
            f"rpc_classify imports {name}; tables are passed in, never imported"
        )
        assert name in ("re", "typing", "__future__"), name


# ---------------------------------------------------------------------------
# (vi) the union actually happened
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fragment, contributed_by",
    [
        ("personal token", "ttt_client -- publicnode's archive gate"),
        ("api key", "ttt/surf/surf_pool4 -- ankr after it went keyed"),
        ("can't route", "curator_client -- drpc's routing failure"),
        ("cannot route", "curator_client -- drpc's routing failure"),
        ("route your request", "curator_client -- drpc's routing failure"),
    ],
)
def test_the_ethereum_union_carries_every_client_s_contribution(
    fragment: str, contributed_by: str
) -> None:
    """Each of these lived in one or three of the four tables and was missing
    from the rest, although every Ethereum pool can meet the refusal."""
    assert fragment in rpc_classify.ETH_ENDPOINT_LIMITATION_FRAGMENTS, contributed_by
    for module in (ttt_client, curator_client, surf_client, surf_pool4_client):
        assert fragment in module._ENDPOINT_LIMITATION_PATTERNS, module.__name__


#: Messages whose **only** limitation signal is the named fragment, under a
#: code that is otherwise terminal.  Hand-written, and labelled as such: no
#: provider sends exactly these, but every captured body that carries one of
#: these fragments carries a second one too, so a captured payload alone cannot
#: show that dropping a fragment changes an answer.
_MINIMAL_PAIRS = (
    ("personal token", "this route needs a personal token"),
    ("api key", "supply an api key to continue"),
    ("route your request", "we could not route your request"),
)


@pytest.mark.parametrize("fragment, message", _MINIMAL_PAIRS)
def test_one_fragment_is_the_whole_difference_between_rotate_and_terminal(
    fragment: str, message: str
) -> None:
    """Drop the fragment from the union and all four clients go terminal here."""
    err = {"code": -32602, "message": message}
    for name in ("ttt", "curator", "surf", "surf_pool4"):
        assert _action(name, err) == ROTATE, f"{name}: {message}"
    without = tuple(
        f for f in rpc_classify.ETH_ENDPOINT_LIMITATION_FRAGMENTS if f != fragment
    )
    assert len(without) == len(rpc_classify.ETH_ENDPOINT_LIMITATION_FRAGMENTS) - 1
    assert (
        rpc_classify.looks_like_endpoint_limitation(err, fragments=without) is False
    ), f"{message!r} matched something other than {fragment!r}"


def test_the_two_tables_are_the_sizes_the_survey_measured() -> None:
    """24 Ethereum fragments (the union of 21/22/20/20) and Base's 15, unmerged.

    A count is a weak assertion on its own; it is here so that a fragment
    added without a provider attribution, or a table quietly merged, arrives as
    a failing test rather than as a behaviour change nobody reads.
    """
    eth = rpc_classify.ETH_ENDPOINT_LIMITATION_FRAGMENTS
    base = rpc_classify.BASE_ENDPOINT_LIMITATION_FRAGMENTS
    assert len(eth) == 24 and len(set(eth)) == 24
    assert len(base) == 15 and len(set(base)) == 15
    assert not set(eth) & set(base) - {"block range", "capacity", "rate limit",
                                       "unauthorized"}
    assert len(rpc_classify.RANGE_CAP_FRAGMENTS) == 5
    assert len(rpc_classify.RESULT_CAP_FRAGMENTS) == 7
    assert rpc_classify.MALFORMED_REQUEST_CODES == frozenset(
        {-32600, -32601, -32602, -32604, -32700}
    )


def test_a_payload_with_no_error_member_never_reaches_a_predicate() -> None:
    """Three recorded failures carry no JSON-RPC error object at all.

    An ``eth_call`` that succeeds, a 429 with a batch body and a Cloudflare 521
    with a plain-text body: the status set in ``rpc_common`` handles the last
    one, the retry ladder handles the 429, and neither is the fragment tables'
    business.  Recorded here so the corpus walk above is honestly complete.
    """
    fwa = _load(FWA_FIXTURES / "rpc_errors.json")["errors"]
    ok = fwa["eth_call_gasprice_without_gas_bound"]["parsed"]
    assert "error" not in ok and ok["result"].startswith("0x")
    assert fwa["llamarpc_dead"]["parsed"] is None
    assert fwa["llamarpc_dead"]["http_status"] in rpc_common.ENDPOINT_DEAD_CODES
    assert fwa["publicnode_rate_limit_429"]["http_status"] == 429
    assert 429 not in rpc_common.ENDPOINT_DEAD_CODES


# ---------------------------------------------------------------------------
# ``requested_block_span``: the span a provider's complaint could be about
# (follow-up #65 -- talismans and fwa_logs read it off the request they sent)
# ---------------------------------------------------------------------------


def test_requested_block_span_reads_every_recorded_drpc_probe():
    """Each live probe records the span it asked for; the reader agrees."""
    probes = _load(POOL4_FIXTURES / "log_range_messages.json")["probes"]
    assert len(probes) == 10
    for probe in probes:
        request = probe["request"]
        assert (
            rpc_classify.requested_block_span(request["method"], request["params"])
            == probe["requested_span_blocks"]
        ), probe["label"]


@pytest.mark.parametrize(
    ("method", "params"),
    [
        ("eth_call", [{"fromBlock": "0x1", "toBlock": "0x10"}]),
        ("eth_getLogs", []),
        ("eth_getLogs", [{"toBlock": "0x10"}]),
        ("eth_getLogs", [{"fromBlock": "0x1"}]),
        ("eth_getLogs", [{"fromBlock": "0x1", "toBlock": "latest"}]),
        ("eth_getLogs", [{"fromBlock": "earliest", "toBlock": "0x10"}]),
        ("eth_getLogs", [{"fromBlock": "0x10", "toBlock": "0x1"}]),
        ("eth_getLogs", ["0x1"]),
        ("eth_getLogs", {"fromBlock": "0x1", "toBlock": "0x10"}),
    ],
    ids=[
        "not-getLogs", "no-filter", "no-from", "no-to", "to-tag", "from-tag",
        "inverted", "filter-not-a-dict", "params-not-a-list",
    ],
)
def test_requested_block_span_is_none_when_the_request_has_no_span(method, params):
    assert rpc_classify.requested_block_span(method, params) is None


def test_requested_block_span_is_inclusive():
    assert rpc_classify.requested_block_span(
        "eth_getLogs", [{"fromBlock": "0x10", "toBlock": "0x10"}]
    ) == 1
    assert rpc_classify.requested_block_span(
        "eth_getLogs", ({"fromBlock": "0x0", "toBlock": hex(299)},)
    ) == 300
