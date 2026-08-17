# WP2 — `data/curator_client.py` (the keyless fetch layer)

**Goal:** One async, keyless, read-only client that turns the two endpoint pools into the
frozen WP0 models, degrades one field at a time, and never lets a failed read become a zero.

**Dependencies:** WP0 (`curator_addresses`, `curator_models`). Runs in wave 2 in parallel with
WP3 and WP4; shares no file with either.

**Owner note.** This WP owns and creates:

- `maxpane_dashboard/data/curator_client.py`
- `tests/data/test_curator_client.py`
- `tests/fixtures/curator/client/` (its own slices of the WP0 captures)

It touches nothing else. `curator_addresses.py` and `curator_models.py` are **read-only** here:
if a selector or a field is missing, report it to WP0's owner with the preimage — do not add it.

### What this WP copies, and from where

`data/surf_client.py` is the closest existing artifact and is the model for the whole module:
`OwnedHttpClient`/`jsonrpc_payload`/`pace`/`ENDPOINT_DEAD_CODES` from `data/rpc_common.py`;
`_rpc_state` / `_rpc_state_batch` / `_rpc_logs` / `_get_json`; `_looks_like_endpoint_limitation`
/ `_is_range_limitation` / `_LogRangeError`; `_BANNED_RPC_HOSTS`; the `*_truncated` and
`log_group_failed` out-of-band flags. Decoding primitives come from `data/evm_abi.py`
(`strip0x`, `decode_uint`, `decode_address`, `encode_uint`, `encode_address`). **Do not
copy `surf_client`'s Multicall3 path** — this contract's whole fast tier is one JSON-RPC batch
array of plain `eth_call`s, which the research proved works in a single round trip with zero
failures.

### Ground rules

- **No test may touch the network.** Every test injects
  `httpx.AsyncClient(transport=httpx.MockTransport(handler))`, and at least one test injects a
  transport whose handler **raises** and asserts the client still returns `None` rather than
  propagating.
- **A failed read is `None`, never `0`.** Batch entries that came back as errors stay `None`.
  The three legitimate zeros (H2/H3 and grace's `ethNeededThisHour`) are real values.
- **Two pools, never crossed.** publicnode refuses archive `eth_getLogs`; it must not appear in
  the logs pool, and a test asserts that.
- **Classify on message text, not code.** Providers reuse `-32602`/`-32005`.
- **Never follow a provider's suggested range.** Halve the window; one provider decrements one
  block per round trip and livelocks verbatim followers.
- Commit after each task.

---

### Task WP2.1: Module skeleton, endpoint pools, and the User-Agent

**Files:** create `maxpane_dashboard/data/curator_client.py`, `tests/data/test_curator_client.py`

**Interfaces:**
- Produces: `STATE_RPC_PRIMARY = "https://ethereum-rpc.publicnode.com"`,
  `STATE_RPC_FALLBACKS`, `LOG_RPCS = ["https://gateway.tenderly.co/public/mainnet",
  "https://eth.drpc.org"]`, `BLOCKSCOUT_BASE`, `_BANNED_RPC_HOSTS`, `USER_AGENT`,
  `class CuratorClient(OwnedHttpClient)` with
  `__init__(state_rpc=…, state_fallbacks=None, log_rpcs=None, blockscout_base=…, *,
  http_client=None, inter_call_delay=…, backoff_seconds=…, now_fn=time.time,
  log_page_blocks=…)`, and the `state_endpoints` / `log_endpoints` properties.

**Steps:**

- [x] Write the failing tests:

```python
def test_the_client_sends_a_real_user_agent():
    """publicnode 403s python-urllib's default UA and accepted the identical
    batch from curl (captures/README.md). Every request must carry a real one.

    Asserted on the *transport's* view of the request, not on the constructor,
    because httpx merges client-level and request-level headers and only the
    merged value is what the endpoint sees.
    """
    seen = []

    def handler(request):
        seen.append(request.headers.get("user-agent", ""))
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": "0x1"})

    client = _client(handler)
    asyncio.run(client._rpc_state("eth_blockNumber", []))
    assert seen and seen[0]
    low = seen[0].lower()
    assert "maxpane" in low
    for default in ("python-urllib", "urllib", "python-httpx", "python-requests"):
        assert default not in low, f"{seen[0]!r} is a library default UA"


def test_publicnode_is_absent_from_the_logs_pool():
    """It refuses archive eth_getLogs (CLAUDE.md hazard table). A pool that
    contains it burns a round trip and a retry on every sweep."""
    assert all("publicnode" not in u for u in CuratorClient().log_endpoints)


def test_banned_hosts_are_refused_at_construction():
    for url in ("https://eth.llamarpc.com", "https://rpc.ankr.com/eth",
                "https://cloudflare-eth.com", "https://api.reservoir.tools",
                "https://eth-mainnet.g.alchemy.com/v2/x", "https://mainnet.infura.io/v3/x",
                "https://api.etherscan.io/api"):
        with pytest.raises(ValueError):
            CuratorClient(state_rpc=url)
        with pytest.raises(ValueError):
            CuratorClient(log_rpcs=[url])


def test_no_module_level_string_looks_like_a_key():
    import inspect
    src = inspect.getsource(curator_client)
    for banned in ("api_key", "apikey", "x-api-key", "Authorization",
                   "private_key", "keystore", "eth_sendRawTransaction",
                   "eth_sendTransaction", "eth_sign"):
        assert banned not in src, banned
```

- [x] Run: expect `ModuleNotFoundError`.
- [x] Write the skeleton. The module docstring states the two-pool rule, the UA hazard, and
      the "this contract has three legitimate zeros" rule with the three named.
- [x] Run to green.
- [x] **Prove it bites:** delete the UA from the header dict → `test_the_client_sends_a_real_user_agent` FAILS. Restore.
- [x] Commit: `feat(curator): client skeleton with two endpoint pools and a real User-Agent`

---

### Task WP2.2: `_rpc_state` and `_rpc_state_batch`

**Interfaces:** produces `_post_rpc`, `_rpc_state(method, params) -> Any` (retry + rotation;
raises on malformed-request), `_rpc_state_batch(calls) -> list[Any] | None` (per-entry results
aligned with `calls`; an errored entry is `None`, never `0`; returns `None` only when every
endpoint failed to serve the array).

**Steps:**

- [x] Failing tests: id-alignment (a provider that returns the array **out of order** must
      still map correctly — the surf client maps by `id`, and a test shuffles the response);
      one errored entry → that slot `None` and the rest intact; a non-list reply → rotate; a
      `ENDPOINT_DEAD_CODES` status → rotate without retrying; a malformed-request error →
      short-circuit the whole chain (it fails identically everywhere).
- [x] Implement, mirroring `surf_client._rpc_state_batch`.
- [x] **Prove it bites:** change the errored-entry branch to write `0` instead of leaving
      `None` → the "a failed leg is None" test FAILS. Restore.
- [x] Commit: `feat(curator): batched state RPC with per-entry None-never-zero semantics`

---

### Task WP2.3: `_rpc_logs`, message-text classification and window shrinking

**Interfaces:** produces `_rpc_logs`, `_LogRangeError`, `_ENDPOINT_LIMITATION_PATTERNS`,
`_RANGE_LIMITATION_PATTERNS`, `_get_logs_shrinking(topic0, from_block, to_block)`.

**Steps:**

- [x] Failing tests:

```python
def test_a_routing_message_fails_over_even_though_its_code_is_reused():
    """drpc's real failure: "Can't route your request..." arrives with a code
    other providers use for a malformed request. Classifying on the code sends
    a healthy query to the bin; classifying on the text fails over."""
    ...  # first endpoint returns {"code": -32602, "message": "Can't route your request ..."}
         # second returns the rows -> the rows are returned, no exception


def test_a_genuinely_malformed_request_short_circuits_the_chain():
    """Same code, different text. Rotating on our own bug triples the request
    count and hides it."""
    ...  # both endpoints return {"code": -32602, "message": "invalid argument 0"}
         # -> RuntimeError, and the second endpoint was NEVER called


def test_a_suggested_range_is_never_followed():
    """One provider decrements one block per round trip and livelocks anything
    that obeys it. The window halves instead."""
    windows = []
    # handler records each (fromBlock, toBlock) and always returns a range error
    ...
    spans = [b - a for a, b in windows]
    assert spans == sorted(spans, reverse=True)
    assert spans[1] <= spans[0] // 2 + 1
    assert len(windows) <= _LOG_MAX_SHRINKS + 1     # bounded, never a livelock
```

- [x] Implement, mirroring `surf_client._rpc_logs` — including classifying the JSON `error`
      body **before** `raise_for_status`, because drpc wraps its shrinkable range cap in an
      HTTP 400 and status-first handling demotes the one recoverable error to an opaque
      transport failure.
- [x] **Prove it bites:** move the `_is_range_limitation` check after `raise_for_status` →
      `test_a_suggested_range_is_never_followed` FAILS (the range error becomes an
      `HTTPStatusError`). Restore.
- [x] Commit: `feat(curator): logs RPC with message-text classification and bounded shrinking`

---

### Task WP2.4: `fetch_state()` and `fetch_config()`

**Interfaces:** produces `async fetch_state() -> CuratorState | None` (the eight fast views in
one batch array, plus `eth_blockNumber` as the last entry of the *same* array so the state and
its height describe the same block) and `async fetch_config() -> CuratorConfig | None` (the
ten `once`-tier views).

**Steps:**

- [x] Slice `tests/fixtures/curator/client/state_batch.json` out of
      `captures/batch.json` + `captures/results.json` — the full round, response order intact.
- [x] Failing tests:

```python
def test_fetch_state_decodes_the_captured_round():
    """Every field, against the real 2026-08-16 21:12 UTC payload."""
    st = asyncio.run(_client_from("state_batch.json").fetch_state())
    assert st.settled is False              # a bool, not 0
    assert st.current_hour == 1
    assert st.current_hour_total_wei == 0x27D2C90DCE228AE5B0
    assert st.hour_needed_wei == 0          # grace: a real 0, not a failed read
    assert st.hour_seconds_left == 2796
    assert st.last_active_hour == 1
    assert st.last_active_hour_total_wei == st.current_hour_total_wei
    assert st.early_bps == 19_491
    assert (st.volume_wei, st.contributors, st.tx_count) == (0x560119983627C22D4F, 143, 222)


def test_is_settled_decodes_to_a_bool_not_an_int():
    """``settled is False`` and ``settled is None`` must be different things.
    An int 0 here would make ``if not settled`` true for a failed read too."""
    st = ...
    assert st.settled is False
    assert _state_with_failed_entry(A.SEL_IS_SETTLED).settled is None


def test_the_multi_word_views_are_decoded_to_their_full_width():
    """lastActiveHour() is 2 words and stats() is 3. Decoding word 0 only would
    silently drop the hour total and both counters -- and the hour total is
    half of the boundary hazard."""
    ...


def test_the_batch_is_sent_in_the_frozen_order():
    """WP0.4 left the ORDER unpinned on purpose; this is where it is pinned.

    The client decodes positionally, so a reordered FAST_VIEW_SELECTORS is a
    silent field swap between two same-width uint256 views -- e.g. currentHour
    and earlyBps -- which no type check can catch.
    """
    sent = _recorded_batch()
    assert [c["params"][0]["data"] for c in sent[:-1]] == [
        sel for _name, sel in A.FAST_VIEW_SELECTORS
    ]
    assert sent[-1]["method"] == "eth_blockNumber"


def test_one_failed_entry_degrades_one_field():
    st = _state_with_failed_entry(A.SEL_EARLY_MULTIPLIER_BPS)
    assert st.early_bps is None
    assert st.current_hour == 1          # everything else survived


def test_a_dead_pool_returns_none_not_a_zeroed_state():
    assert asyncio.run(_client_all_endpoints_down().fetch_state()) is None
```

- [x] Implement. `fetch_config()` reads the eight immutables + `POINTS_PER_ETH` + `deployer()`
      and **must not** fall back to any constant in `curator_addresses` — `CLAUDE.md` rule 4.
      A test asserts the module contains no literal `86400`, `3600`, `5000000000000000000`,
      `1000` used as a config value (a scan with the same shape as FWA's guardrail).
- [x] **Prove it bites:** swap two entries of `FAST_VIEW_SELECTORS` →
      `test_the_batch_is_sent_in_the_frozen_order` FAILS **and** the decode test FAILS with
      two fields transposed. Restore.
- [x] Commit: `feat(curator): decode the fast view round and the immutable config`

---

### Task WP2.5: `fetch_wallet(address)`

**Interfaces:** produces `async fetch_wallet(address: str) -> WalletState | None` — six calls
in one batch: `pointsOf`, `weightOf`, `contributedBy`, `txCountOf`, `firstHourOf`,
`requiredNext`.

**Steps:**

- [x] Failing tests:

```python
def test_first_hour_of_un_shifts_and_reports_joined_separately():
    """H6. ``firstHourOf`` returns (0, false) for a stranger and (0, true) for
    an hour-0 founder. The client must never collapse them, and must never
    read the raw ``contributors()`` struct field, which carries the +1."""
    stranger = _wallet_returning({A.SEL_FIRST_HOUR_OF: _words(0, 0)})
    founder = _wallet_returning({A.SEL_FIRST_HOUR_OF: _words(0, 1)})
    assert (stranger.first_hour, stranger.has_joined) == (0, False)
    assert (founder.first_hour, founder.has_joined) == (0, True)


def test_the_client_never_calls_the_raw_contributors_getter():
    import inspect
    assert "SEL_CONTRIBUTORS" not in inspect.getsource(curator_client)


def test_required_next_is_the_wei_the_wallet_must_send():
    """Quoted so nobody burns gas on MustEscalate. A None here renders the
    unavailable state; a 0 would read as 'send anything'."""
    ...


def test_an_address_argument_is_left_padded_without_an_inner_0x():
    """The Multicall3 lesson applies to plain eth_call data too: an inner 0x
    makes the node reject the payload."""
    data = _recorded_call(A.SEL_POINTS_OF)["params"][0]["data"]
    assert data.count("0x") == 1 and len(data) == 10 + 64
```

- [x] Implement using `evm_abi.encode_address`.
- [x] Commit: `feat(curator): per-wallet view batch with firstHourOf un-shifting`

---

### Task WP2.6: `fetch_balance()` — the forced-ETH anomaly

**Interfaces:** produces `async fetch_balance() -> int | None`.

**Steps:**

- [x] Failing tests: a `0x0` balance decodes to `0` (the **expected** state, not a failure);
      a nonzero balance decodes to the integer; a dead pool gives `None`. Plus a docstring
      test-by-assertion that the value is only ever surfaced as an anomaly:
      `test_the_balance_is_never_folded_into_a_volume` — the client exposes it as its own
      return, not as a `CuratorState` volume field.
- [x] Implement `eth_getBalance(CURATOR, "latest")` on the state pool. The docstring states
      H5: refunds happen in-transaction, so between transactions this balance is **always
      exactly zero**; any nonzero value is forced ETH (selfdestruct or a block builder naming
      the contract as fee recipient) and never a deposit.
- [x] Commit: `feat(curator): read the contract balance as the forced-ETH anomaly`

---

### Task WP2.7: `fetch_logs()` — the six groups and the full-history backfill

**Interfaces:** produces
`async fetch_logs(from_block: int, to_block: int | str = "latest") -> LogSweep | None` and the
out-of-band `log_group_failed: dict[str, bool]` reset at the **start** of every call.

**Steps:**

- [x] Slice `tests/fixtures/curator/client/logs_full_sweep.json` from
      `captures/tenderly_logs.json` (all 377 rows, untrimmed — the pagination and grouping are
      what is under test), plus `logs_empty.json` and `logs_settled_row.json`
      (**`# SYNTHETIC — re-point at tests/fixtures/curator/captures/live/<bundle>`**, shape
      taken from the ABI).
- [x] Failing tests:

```python
def test_the_full_history_sweep_groups_every_event():
    sweep = asyncio.run(_client_from("logs_full_sweep.json")
                        .fetch_logs(A.CREATION_BLOCK))
    assert len(sweep.deposits) == 226
    assert len(sweep.launched) == 1
    assert len(sweep.first_deposits) == 145
    assert sweep.hour_saved == () and sweep.settled == () and sweep.rescued == ()
    # ...and () for a group that never fired is NOT the same as a failed filter:
    assert not any(client.log_group_failed.values())


def test_a_raw_row_survives_grouping_untouched():
    """The decoders are WP3/WP5's; this client normalises nothing away.

    ``logIndex`` in particular: PRD §4 de-dupes activity rows by (tx, log
    index), and a client that dropped it would make that impossible while every
    test stayed green.
    """
    row = sweep.deposits[0]
    assert {"topics", "data", "blockNumber", "transactionHash", "logIndex"} <= set(row)
    assert len(row["topics"]) == 3          # topic0 + contributor + hour


def test_one_failed_group_is_reported_out_of_band_not_as_an_empty_tuple():
    """A frozen tuple cannot hold None, so () is ambiguous on its own. The dict
    is what resolves it -- and without it a dead Settled filter would read as
    'the game is alive'."""
    ...
    assert sweep.settled == ()
    assert client.log_group_failed["settled"] is True


def test_every_group_failing_returns_none_not_a_hollow_sweep():
    assert asyncio.run(_client_all_log_endpoints_down().fetch_logs(0)) is None


def test_the_deposit_hour_comes_from_the_indexed_topic():
    """H2's foundation: the hour is topics[2], so the hourly series needs no
    timestamp and no state read. A client that only exposed ``data`` would push
    the fold back onto currentHourTotal."""
    assert int(sweep.deposits[0]["topics"][2], 16) >= 0
```

- [x] Implement. One `eth_getLogs` per topic0 (six filters) **or** one address-scoped filter
      with a topic0 `OR` array and local grouping — measure which the endpoints accept and pick
      one; the research proved a single address-scoped sweep returns all 377 in one call, so
      prefer that and group locally, falling back to per-topic filters on a range error.
- [x] Commit: `feat(curator): group the six curator event types out of one address sweep`

---

### Task WP2.8: Block timestamps for the activity feed (H14)

**Interfaces:** produces
`async fetch_block_timestamps(block_numbers: Iterable[int]) -> dict[int, int]`.

**Why this exists:** tenderly's `eth_getLogs` returns **no** `blockTimestamp`, and Blockscout's
log items carry only `block_number` (WP0.7 pins both). The activity feed's `HH:MM` has no other
source. Hour buckets need none — the hour is an indexed topic and its wall-clock is
`launchTime + hour * hourDuration`, exact by construction.

**Steps:**

- [x] Failing tests: distinct blocks only (25 rows over 9 blocks → 9 calls); bounded by
      `MAX_TIMESTAMP_BLOCKS` (default 40 — the rendered activity window, not the whole
      history); a failed entry yields **no key** for that block rather than a 0; an empty input
      makes zero requests; the batch uses `eth_getBlockByNumber(block, false)` (no
      transactions).
- [x] Implement on the **state** pool (batched array, same machinery as WP2.2).
- [x] **Prove it bites:** make a failed entry write `0` → the "no key rather than a 0" test
      FAILS. Restore. (A `0` here renders `1970-01-01 00:00`, which looks like data.)
- [x] Commit: `feat(curator): bounded block-timestamp batch for the activity feed`

---

### Task WP2.9: Blockscout cross-check and gap repair

**Interfaces:** produces
`async fetch_blockscout_logs(max_pages: int = 8) -> list[dict] | None` and
`blockscout_truncated: bool` (reset at the start of every call).

**Steps:**

- [x] Slice all eight `captures/bs_page_*.json` into `tests/fixtures/curator/client/`.
- [x] Failing tests: pagination follows `next_page_params` until exhausted or `max_pages`;
      hitting the bound with a cursor still present sets `blockscout_truncated`; the returned
      rows reconcile with the RPC sweep the way WP0.7 pinned (376 ⊂ 377, exactly one extra on
      the RPC side, explained by the two pulls being seconds apart); a 4xx returns `None`, not
      `[]` (an empty list would read as "the contract has no logs").
- [x] Implement with `_get_json`.
- [x] Commit: `feat(curator): Blockscout log pagination as the RPC sweep's cross-check`

---

### Task WP2.10: Structural no-network proof and degradation flags

**Steps:**

- [x] Add the structural test the house requires:

```python
def test_no_client_method_opens_a_socket():
    """Injected transport raises on use; every public coroutine is driven.

    Structural, not incidental: a method added later that builds its own
    httpx.AsyncClient (the ``PriceClient`` trap surf documented) bypasses every
    mock in this file and would be caught only in CI, or not at all.
    """
    def boom(request):
        raise AssertionError(f"network access attempted: {request.url}")

    client = CuratorClient(http_client=httpx.AsyncClient(
        transport=httpx.MockTransport(boom)))
    for call in (client.fetch_state(), client.fetch_config(), client.fetch_balance(),
                 client.fetch_logs(A.CREATION_BLOCK), client.fetch_wallet(ADDR),
                 client.fetch_blockscout_logs(), client.fetch_block_timestamps([1])):
        result = asyncio.run(call)
        assert result in (None, {}, []) or result == {}


def test_the_module_builds_no_http_client_of_its_own():
    import inspect
    src = inspect.getsource(curator_client)
    assert src.count("httpx.AsyncClient(") == 1     # only the constructor's
```

- [x] Add the truncation/degradation surface: `state_failed`, `logs_failed`,
      `wallet_failed`, `blockscout_truncated`, `log_group_failed` — all reset at the start of
      the call they describe, all documented as "true right now", never "true once, ever".
- [x] Commit: `test(curator): prove the client opens no socket and reports its own degradation`

---

### Task WP2.11: Lifecycle and the WP5 hand-off

**Steps:**

- [x] `close()` comes from `OwnedHttpClient`; add a test that an **injected** client is not
      closed (it belongs to the caller) and an owned one is.
- [x] Run the whole file: `.venv/bin/python -m pytest tests/data/test_curator_client.py -v`
- [x] Run the full suite: `.venv/bin/python -m pytest -q` — nothing outside curator may move.
- [x] Write the hand-off note for WP5 (in the final commit body): the exact method signatures,
      which return `None` vs a model vs a dict, the names and reset semantics of the six
      degradation flags, and the one thing WP5 must not assume — **`LogSweep`'s empty tuples
      are ambiguous without `log_group_failed`**.
- [x] Commit: `feat(curator): client lifecycle and the manager hand-off`

**Done when:** every public coroutine is tested against a committed payload, no test opens a
socket, and the degradation surface is documented for WP5.

---

## Landed 2026-08-17 — what differs from the instructions above

All eleven tasks are implemented and committed; 95 tests in
`tests/data/test_curator_client.py`, full suite green. Five places where the
code deliberately differs from this file, each with the reason:

1. **`test_no_client_method_opens_a_socket` (WP2.10) cannot hold as written.**
   The sketch raises `AssertionError` in the handler and then asserts the call
   *returned*. `httpx.MockTransport` does not wrap a handler exception and
   `AssertionError` is caught by none of the client's `except` clauses, so it
   propagates and the assertion is unreachable. Split into three: an
   `httpx.ConnectError` transport proves degrade-to-`None`, the recorded
   requests prove everything went through the injected transport, and
   `test_the_module_builds_no_http_client_of_its_own` closes the `PriceClient`
   hole. Paths that must issue *no* request keep the raising double.

2. **A reorder of `FAST_VIEW_SELECTORS` does NOT break the decode.** WP2.4's
   bite-proof predicts two transposed fields; verified in memory, only
   `test_the_batch_is_sent_in_the_frozen_order` goes red. `_decode_round` keys
   its output by selector *name* while indexing the reply by position, and the
   reply was already re-aligned by `id`, so name and value travel together.
   That is the safer arrangement and it stays — which is exactly why the order
   test has to be **hand-typed** rather than derived from the tuple.

3. **The big captures are read in place, not copied into
   `tests/fixtures/curator/client/`.** WP2.7 and WP2.9 ask for slices of
   `tenderly_logs.json` (328 KB) and the eight `bs_page_*.json` (790 KB); a
   byte-for-byte copy is a second source of truth that can drift from a set the
   brief declares read-only. `tests.curator_fixtures.capture()` reads them
   where they live. `client/` holds only what does not exist on chain:
   `state_batch.json` (a genuine 7 KB slice, requests+responses, correlated by
   `id`), `logs_settled_row.json` (**SYNTHETIC**) and `logs_empty.json`.

4. **231 Deposited rows, not 226** (WP2.7's snippet quotes the pre-correction
   number). The test writes the arithmetic out — `1 + 231 + 145 == 377`.

5. **`_get_logs_shrinking` does not copy `surf_client`'s shrink.** Surf raises
   `fromBlock`, which is right for a rolling recent window and wrong for a
   backfill: the blocks it walks past are this contract's whole early history.
   This one narrows the right edge and re-issues the same cursor; two tests pin
   that the covered block set is exactly the requested range.

Also added beyond the brief: `config_failed` (the sixth degradation flag —
WP2.10 lists five and WP2.11 promises six), a de-dupe on `(transactionHash,
logIndex)` in the log grouping, and `fetch_wallet` rejecting an unusable
address with zero requests.
