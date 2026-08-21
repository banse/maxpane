# Curator Filter Follow-ups And NFT Holders Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Improve THE LIST filter editor and list-only hero, show active criteria in the filtered title, and add keyless cached Ethereum/Base NFT-holder filtering.

**Architecture:** The pure filter model owns typed collection references and OR-within-NFT matching. A dedicated keyless Multicall3 reader and additive curator cache slot own current NFT balances; CuratorManager schedules detached scans and exposes last-good holder sets; CuratorScreen controls accepted draft/pending state; curator-only widgets render titled controls, reset/add/remove commands, hero markup, and criteria titles.

**Tech Stack:** Python 3.11+, Textual 8.1.1, Rich, httpx, Ethereum/Base JSON-RPC, Multicall3 aggregate3, pytest/pytest-asyncio.

**Spec:** docs/superpowers/specs/2026-08-21-curator-filter-followups-nft-design.md

## Global Constraints

- Work only on feature/curator-list-record-hero; never commit this work to main.
- Follow KISS and frontend MVC: model/manager computes, screen controls, widgets render primitives.
- Do not modify shared hero cards or any non-curator view.
- Keep MaxPane read-only and keyless. Add no signer, transaction path, API key, keyed endpoint, or dependency.
- NFT ownership is current state from keyless eth_call through Multicall3; do not scan historical Transfer logs.
- No NFT request occurs until an accepted filter selects at least one collection.
- Tests are offline and inject a transport that raises on unexpected I/O.
- Preserve raw/cleaned/filtered ADDRESS 42, ENS 19, POINTS 7, CREDIT 6, INDEX behavior, aligned YOU footer, and the 143-column no-horizontal-scroll contract.
- NFT choices combine with OR; the NFT category combines with every other active category using AND.
- Preserve valid-empty versus pending/unavailable distinctions. Pending or unavailable NFT data never exports or overwrites prior JSON.
- CryptoPunks support is balanceOf-based and must not require ERC-165.
- Custom filters remain session-only. Holder last-good data may persist in the additive curator cache slot.
- Use apply_patch for manual edits.
- Follow TDD for each task: named red test, minimal implementation, green test, named mutation, restore, explicit-path commit.
- Never stage the pre-existing untracked tests/fixtures/curator/captures/live/ files.

## File Map

**Create**

- maxpane_dashboard/data/curator_nft_holders.py - chain-neutral NFT collection identifiers, wallet-universe fingerprints, keyless RPC/Multicall reader, and scan result types.
- tests/data/test_curator_nft_holders.py - encoding, chain routing, chunking, degradation, and lifecycle tests.

**Modify**

- maxpane_dashboard/data/curator_list_filters.py - immutable NFT references, exact integer parsing, summaries, and NFT matching.
- maxpane_dashboard/data/curator_cache.py - additive NFT-holder last-good slot and per-collection persistence helpers.
- maxpane_dashboard/data/curator_manager.py - detached scan queue, freshness/failure handling, holder context, and close ordering.
- maxpane_dashboard/widgets/curator/list_filter.py - titled field groups, predefined/custom NFT controls, add/remove/reset messages, and acceptance footer.
- maxpane_dashboard/widgets/curator/list_hero.py - editor-only note, third-card title/alignment, and filtered-wallet markup.
- maxpane_dashboard/widgets/curator/lists.py - regular dim criteria suffix in the filtered title and NFT source receipts.
- maxpane_dashboard/widgets/curator/__init__.py - export new filter-editor messages.
- maxpane_dashboard/screens/curator.py - predefined primitive choices, editor events, accepted NFT pending state, note dispatch, refresh publication, title data, and export gating.
- maxpane_dashboard/themes/minimal.tcss - responsive titled-group, custom NFT row, reset, and footer layout.
- tests/data/test_curator_list_filters.py
- tests/data/test_curator_cache.py
- tests/data/test_curator_manager.py
- tests/widgets/test_curator_widgets.py
- tests/screens/test_curator_screen.py
- tests/test_curator_registration.py

---

### Task 1: Pure NFT Filter Contract And Exact Integer Bounds

**Files:**
- Modify: maxpane_dashboard/data/curator_list_filters.py
- Modify: tests/data/test_curator_list_filters.py

**Interfaces:**
- Produces NftCollectionRef(chain: str, address: str, label: str), PREDEFINED_NFT_COLLECTIONS, parse_nft_collection(), nft_collection_key(), and custom_nft_label().
- Extends FilterSpec with nft_collections: tuple[NftCollectionRef, ...].
- Extends FilterContext with nft_holders_by_collection: Mapping[str, frozenset[str]] | None.
- empty_filter_values() includes nft_collections=().
- filter_summary() adds one stable NFT clause after existing categories.

- [ ] **Step 1: Write failing model tests**

Add imports and these tests:

~~~python
from maxpane_dashboard.data.curator_list_filters import (
    FilterContext,
    FilterDataUnavailable,
    FilterSpec,
    FilterValidationError,
    NftCollectionRef,
    PREDEFINED_NFT_COLLECTIONS,
    custom_nft_label,
    filter_rows,
    filter_summary,
    parse_filter_values,
    parse_nft_collection,
)


def test_the_four_predefined_nft_collections_are_exact():
    assert [
        (item.label, item.chain, item.address)
        for item in PREDEFINED_NFT_COLLECTIONS
    ] == [
        (
            "Identity.md",
            "ethereum",
            "0x0000ec93127baa929e58e97dd0095a2bfb38ec1d",
        ),
        (
            "Fren Pet",
            "base",
            "0x5b51cf49cb48617084ef35e7c7d7a21914769ff1",
        ),
        (
            "Milady",
            "ethereum",
            "0x5af0d9827e0c53e4799bb226655a1de152a425a5",
        ),
        (
            "Crypto Punks",
            "ethereum",
            "0xb47e3cd837ddf8e4c57f05d70ab865de6e193bbb",
        ),
    ]


def test_custom_nft_collections_validate_normalise_and_deduplicate():
    address = "0xABCDEFabcdefABCDEFabcdefABCDEFabcdefABCD"
    spec = parse_filter_values(
        {
            "nft_collections": (
                {"chain": "base", "address": address},
                {"chain": "base", "address": address.lower()},
            )
        }
    )
    assert spec.nft_collections == (
        NftCollectionRef(
            chain="base",
            address=address.lower(),
            label="BASE 0xabcd…abcd",
        ),
    )
    assert custom_nft_label("ethereum", address.lower()) == "ETH 0xabcd…abcd"


@pytest.mark.parametrize(
    ("value", "field"),
    [
        ({"chain": "arbitrum", "address": "0x" + "1" * 40}, "nft_collections"),
        ({"chain": "ethereum", "address": "0x1234"}, "nft_collections"),
        ({"chain": "ethereum", "address": "0x" + "z" * 40}, "nft_collections"),
    ],
)
def test_invalid_custom_nft_collections_name_the_editor_field(value, field):
    with pytest.raises(FilterValidationError) as caught:
        parse_filter_values({"nft_collections": (value,)})
    assert caught.value.field == field


def test_selected_nft_collections_are_or_with_each_other_and_and_with_points():
    identity, frenpet = PREDEFINED_NFT_COLLECTIONS[:2]
    rows = [
        {"address": "0x" + "1" * 40, "points": 10},
        {"address": "0x" + "2" * 40, "points": 20},
        {"address": "0x" + "3" * 40, "points": 30},
    ]
    context = FilterContext(
        nft_holders_by_collection={
            identity.key: frozenset({rows[0]["address"]}),
            frenpet.key: frozenset({rows[1]["address"]}),
        }
    )
    spec = FilterSpec(
        points_min=15,
        nft_collections=(identity, frenpet),
    )
    assert [row["address"] for row in filter_rows(rows, spec, context)] == [
        rows[1]["address"]
    ]


@pytest.mark.parametrize(
    ("spec_values", "first_values", "second_values"),
    (
        ({"join_min": 2}, {"first_index": 2}, {"first_index": 1}),
        ({"hour_min": 2}, {"first_hour": 2}, {"first_hour": 1}),
        ({"rank_min": 2}, {"rank": 2}, {"rank": 1}),
        ({"points_min": 2}, {"points": 2}, {"points": 1}),
        ({"credit_min": 2}, {"credit_eth": 2}, {"credit_eth": 1}),
        ({"weight_min": 2}, {"weight_eth": 2}, {"weight_eth": 1}),
        ({"deposits_min": 2}, {"tx_count": 2}, {"tx_count": 1}),
        ({"ens": "set"}, {"name": "one.eth"}, {"name": None}),
        ({"window": "judged"}, {"first_hour": 24}, {"first_hour": 0}),
        ({"band": "high"}, {"link_conf": "high"}, {"link_conf": "clean"}),
    ),
)
def test_nft_category_ands_with_each_row_backed_category(
    spec_values, first_values, second_values
):
    collection = PREDEFINED_NFT_COLLECTIONS[0]
    first = {"address": "0x" + "1" * 40, **first_values}
    second = {"address": "0x" + "2" * 40, **second_values}
    context = FilterContext(nft_holders_by_collection={
        collection.key: frozenset({first["address"], second["address"]})
    })
    spec = FilterSpec(nft_collections=(collection,), **spec_values)
    assert filter_rows([first, second], spec, context) == [first]


def test_nft_category_ands_with_linked_family_and_whale_evidence():
    collection = PREDEFINED_NFT_COLLECTIONS[0]
    first = "0x" + "1" * 40
    second = "0x" + "2" * 40
    rows = [{"address": first}, {"address": second}]
    holders = {collection.key: frozenset({first, second})}
    family_context = FilterContext(
        families_by_address={
            first: frozenset({"amount"}),
            second: frozenset({"funding"}),
        },
        nft_holders_by_collection=holders,
    )
    assert filter_rows(
        rows,
        FilterSpec(
            families=frozenset({"amount"}),
            nft_collections=(collection,),
        ),
        family_context,
    ) == [rows[0]]
    whale_context = FilterContext(
        whale_addresses=frozenset({first}),
        nft_holders_by_collection=holders,
    )
    assert filter_rows(
        rows,
        FilterSpec(whale=True, nft_collections=(collection,)),
        whale_context,
    ) == [rows[0]]


def test_every_selected_nft_collection_must_have_truthful_holder_data():
    identity, frenpet = PREDEFINED_NFT_COLLECTIONS[:2]
    with pytest.raises(FilterDataUnavailable, match="NFT holder data"):
        filter_rows(
            [{"address": "0x" + "1" * 40}],
            FilterSpec(nft_collections=(identity, frenpet)),
            FilterContext(
                nft_holders_by_collection={identity.key: frozenset()}
            ),
        )


def test_nft_filter_summary_is_stable_and_last():
    identity, frenpet = PREDEFINED_NFT_COLLECTIONS[:2]
    assert filter_summary(
        FilterSpec(
            join_min=1,
            join_max=100,
            nft_collections=(identity, frenpet),
        )
    ) == (
        "join #1-100",
        "NFT Identity.md or Fren Pet",
    )


def test_integer_bounds_remain_exact_above_binary_float_precision():
    exact = 2**53 + 1
    spec = parse_filter_values({"points_max": str(exact - 1)})
    assert filter_rows(
        [{"address": "0x" + "1" * 40, "points": exact}],
        spec,
        FilterContext(),
    ) == []
~~~

- [ ] **Step 2: Run the tests and verify the intended red state**

Run:

~~~bash
.venv/bin/pytest tests/data/test_curator_list_filters.py -k "nft or binary_float" -q
~~~

Expected: collection imports fail before test collection. After adding only the names, matching and exact-integer tests fail because FilterSpec/FilterContext do not yet carry NFT state and integer values still pass through float().

- [ ] **Step 3: Implement immutable collection parsing and exact numeric comparison**

Add these definitions above FilterSpec:

~~~python
import re

NFT_CHAINS = frozenset({"ethereum", "base"})
_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


@dataclass(frozen=True, slots=True)
class NftCollectionRef:
    chain: str
    address: str
    label: str

    @property
    def key(self) -> str:
        return nft_collection_key(self.chain, self.address)


def nft_collection_key(chain: str, address: str) -> str:
    return f"{chain}:{address.casefold()}"


def custom_nft_label(chain: str, address: str) -> str:
    prefix = "ETH" if chain == "ethereum" else "BASE"
    return f"{prefix} {address[:6]}…{address[-4:]}"


def parse_nft_collection(value: object) -> NftCollectionRef:
    if isinstance(value, NftCollectionRef):
        raw_chain, raw_address, raw_label = (
            value.chain,
            value.address,
            value.label,
        )
    elif isinstance(value, Mapping):
        raw_chain = value.get("chain")
        raw_address = value.get("address")
        raw_label = value.get("label")
    else:
        raise FilterValidationError(
            "nft_collections", "invalid NFT collection"
        )
    if not isinstance(raw_chain, str) or raw_chain not in NFT_CHAINS:
        raise FilterValidationError(
            "nft_collections", "NFT chain must be Ethereum or Base"
        )
    if not isinstance(raw_address, str) or not _ADDRESS_RE.fullmatch(
        raw_address.strip()
    ):
        raise FilterValidationError(
            "nft_collections", "NFT contract must be a 20-byte 0x address"
        )
    address = raw_address.strip().casefold()
    label = (
        " ".join(raw_label.split())
        if isinstance(raw_label, str) and raw_label.strip()
        else custom_nft_label(raw_chain, address)
    )
    return NftCollectionRef(raw_chain, address, label)


PREDEFINED_NFT_COLLECTIONS = (
    NftCollectionRef(
        "ethereum",
        "0x0000ec93127baa929e58e97dd0095a2bfb38ec1d",
        "Identity.md",
    ),
    NftCollectionRef(
        "base",
        "0x5b51cf49cb48617084ef35e7c7d7a21914769ff1",
        "Fren Pet",
    ),
    NftCollectionRef(
        "ethereum",
        "0x5af0d9827e0c53e4799bb226655a1de152a425a5",
        "Milady",
    ),
    NftCollectionRef(
        "ethereum",
        "0xb47e3cd837ddf8e4c57f05d70ab865de6e193bbb",
        "Crypto Punks",
    ),
)


def _parse_nft_collections(value: object) -> tuple[NftCollectionRef, ...]:
    if value in (None, (), []):
        return ()
    if isinstance(value, (str, bytes, Mapping)):
        raise FilterValidationError(
            "nft_collections", "invalid NFT collection list"
        )
    try:
        candidates = tuple(value)
    except TypeError as exc:
        raise FilterValidationError(
            "nft_collections", "invalid NFT collection list"
        ) from exc
    out: list[NftCollectionRef] = []
    seen: set[str] = set()
    for candidate in candidates:
        item = parse_nft_collection(candidate)
        if item.key not in seen:
            out.append(item)
            seen.add(item.key)
    return tuple(out)
~~~

Append `nft_collections` to the existing `FilterSpec` fields, add the last
term to its existing `active` expression, and replace `FilterContext` and
`empty_filter_values()` with these definitions:

~~~python
@dataclass(frozen=True, slots=True)
class FilterSpec:
    nft_collections: tuple[NftCollectionRef, ...] = ()

    @property
    def active(self) -> bool:
        ranged = any(
            getattr(self, field) is not None
            for field in (*_INTEGER_FIELDS, *_DECIMAL_FIELDS)
        )
        return (
            ranged
            or self.ens != "any"
            or self.window != "any"
            or self.band != "any"
            or bool(self.families)
            or self.whale
            or bool(self.nft_collections)
        )


@dataclass(frozen=True, slots=True)
class FilterContext:
    families_by_address: Mapping[str, frozenset[str]] | None = None
    whale_addresses: frozenset[str] | None = None
    nft_holders_by_collection: (
        Mapping[str, frozenset[str]] | None
    ) = None


def empty_filter_values() -> dict[str, object]:
    values = {
        field: "" for field in (*_INTEGER_FIELDS, *_DECIMAL_FIELDS)
    }
    values.update(
        ens="any",
        window="any",
        band="any",
        families=frozenset(),
        whale=False,
        nft_collections=(),
    )
    return values
~~~

Replace integer float parsing with an exact path and retain float parsing only for decimal fields:

~~~python
def _parse_number(field: str, value: object, *, integer: bool):
    if value is None or (
        isinstance(value, str) and not value.strip()
    ):
        return None
    if isinstance(value, bool):
        raise FilterValidationError(
            field, f"{field} must be a non-negative number"
        )
    if integer:
        if isinstance(value, int):
            number = value
        elif isinstance(value, float):
            if not math.isfinite(value) or not value.is_integer():
                raise FilterValidationError(
                    field, f"{field} must be a non-negative number"
                )
            number = int(value)
        elif isinstance(value, str) and value.strip().isdigit():
            number = int(value.strip())
        else:
            raise FilterValidationError(
                field, f"{field} must be a non-negative number"
            )
        if number < 0:
            raise FilterValidationError(
                field, f"{field} must be a non-negative number"
            )
        return number
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise FilterValidationError(
            field, f"{field} must be a non-negative number"
        ) from exc
    if not math.isfinite(number) or number < 0:
        raise FilterValidationError(
            field, f"{field} must be a non-negative number"
        )
    return number
~~~

In `parse_filter_values()`, assign
`parsed["nft_collections"] = _parse_nft_collections(values.get("nft_collections", ()))`.
In `filter_rows()`, preserve exact ints for integer-backed row fields and add
NFT availability/matching:

~~~python
def _row_number(
    row: Mapping[str, object], field: str, *, integer: bool
) -> int | float | None:
    value = row.get(field)
    if isinstance(value, bool):
        return None
    if integer:
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.strip().isdigit():
            return int(value.strip())
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None
~~~

Call `_row_number(..., integer=low_field in _INTEGER_FIELDS)` inside the range
loop and `_row_number(row, "first_hour", integer=True)` for window matching.
Before iterating rows, validate every selected collection key exists:

~~~python
    if spec.nft_collections:
        holders = context.nft_holders_by_collection
        if holders is None or any(
            collection.key not in holders
            for collection in spec.nft_collections
        ):
            raise FilterDataUnavailable("NFT holder data unavailable")
~~~

After the whale test, add:

~~~python
        if spec.nft_collections and not any(
            key in context.nft_holders_by_collection[collection.key]
            for collection in spec.nft_collections
        ):
            continue
~~~

Append one NFT clause at the end of filter_summary():

~~~python
    if spec.nft_collections:
        clauses.append(
            "NFT " + " or ".join(
                collection.label for collection in spec.nft_collections
            )
        )
~~~

- [ ] **Step 4: Run the full pure-model suite**

Run:

~~~bash
.venv/bin/pytest tests/data/test_curator_list_filters.py -q
~~~

Expected: all tests pass.

- [ ] **Step 5: Prove OR semantics and exact integer handling bite**

Mutation A: replace any( with all( in the NFT row match. Run:

~~~bash
.venv/bin/pytest tests/data/test_curator_list_filters.py::test_selected_nft_collections_are_or_with_each_other_and_and_with_points -q
~~~

Expected: FAIL because the Fren Pet holder does not also hold Identity.md.

Restore. Mutation B: change the exact integer row path to float(value). Run:

~~~bash
.venv/bin/pytest tests/data/test_curator_list_filters.py::test_integer_bounds_remain_exact_above_binary_float_precision -q
~~~

Expected: FAIL because 2**53 + 1 rounds down. Restore and rerun both tests green.

- [ ] **Step 6: Commit Task 1**

~~~bash
git add maxpane_dashboard/data/curator_list_filters.py tests/data/test_curator_list_filters.py
git commit -m "feat(curator): add NFT filter model"
~~~

### Task 2: Keyless Ethereum And Base NFT Holder Reader

**Files:**
- Create: maxpane_dashboard/data/curator_nft_holders.py
- Create: tests/data/test_curator_nft_holders.py

**Interfaces:**
- Consumes NftCollectionRef and nft_collection_key() from Task 1.
- Produces NftHolderClient.scan(collection, wallets) -> NftHolderScan.
- Produces wallet_universe_fingerprint(wallets) -> str.
- Produces NftHolderPending and NftHolderUnavailable, both FilterDataUnavailable subclasses used by manager/screen tasks.
- Makes no request at construction time.

- [ ] **Step 1: Write failing encoding, routing, and degradation tests**

Create `tests/data/test_curator_nft_holders.py`. Use these test-only ABI
helpers so responses are structurally valid and request-size assertions read
the real `aggregate3` array length:

~~~python
from __future__ import annotations

import json

import httpx
import pytest

from maxpane_dashboard.data.curator_list_filters import (
    PREDEFINED_NFT_COLLECTIONS,
)
from maxpane_dashboard.data.curator_nft_holders import (
    NftHolderClient,
    NftHolderUnavailable,
    wallet_universe_fingerprint,
)
from maxpane_dashboard.data.evm_abi import encode_uint


def _rpc_result(request_id, result):
    return httpx.Response(
        200,
        json={"jsonrpc": "2.0", "id": request_id, "result": result},
    )


def _call_count(calldata: str) -> int:
    raw = calldata[10:]
    array_offset = int(raw[:64], 16) * 2
    return int(raw[array_offset : array_offset + 64], 16)


def _results(values: list[tuple[bool, int | None]]) -> str:
    tuples = []
    for success, value in values:
        body = "" if value is None else encode_uint(value)
        padded = body + "0" * ((64 - len(body) % 64) % 64)
        tuples.append(
            encode_uint(1 if success else 0)
            + encode_uint(64)
            + encode_uint(len(body) // 2)
            + padded
        )
    cursor = len(values) * 32
    offsets = []
    for item in tuples:
        offsets.append(encode_uint(cursor))
        cursor += len(item) // 2
    return "0x" + "".join(
        (encode_uint(32), encode_uint(len(values)), *offsets, *tuples)
    )


def _client(handler):
    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    )
    client = NftHolderClient(
        http_client=http_client,
        rpc_pools={
            "ethereum": ("https://eth.invalid",),
            "base": ("https://base.invalid",),
        },
        min_interval=0,
    )
    return client, http_client


@pytest.mark.asyncio
async def test_ethereum_and_base_route_to_separate_keyless_pools():
    urls = []

    async def handler(request):
        urls.append(str(request.url))
        body = json.loads(request.content)
        if body["method"] == "eth_getCode":
            return _rpc_result(body["id"], "0x6000")
        if body["method"] == "eth_blockNumber":
            return _rpc_result(body["id"], "0x123")
        return _rpc_result(body["id"], _results([(True, 0)]))

    client, http_client = _client(handler)
    wallet = "0x" + "1" * 40
    await client.scan(PREDEFINED_NFT_COLLECTIONS[0], [wallet])
    await client.scan(PREDEFINED_NFT_COLLECTIONS[1], [wallet])
    assert any(url.startswith("https://eth.invalid") for url in urls)
    assert any(url.startswith("https://base.invalid") for url in urls)
    await client.close()
    await http_client.aclose()


@pytest.mark.asyncio
async def test_dead_endpoint_fails_over_and_total_failure_is_explicit():
    requests = []

    async def handler(request):
        requests.append((request.url.host, json.loads(request.content)["method"]))
        body = json.loads(request.content)
        if request.url.host == "dead.invalid":
            return httpx.Response(503)
        if body["method"] == "eth_getCode":
            return _rpc_result(body["id"], "0x6000")
        if body["method"] == "eth_blockNumber":
            return _rpc_result(body["id"], "0x1")
        return _rpc_result(body["id"], _results([(True, 0)]))

    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    )
    client = NftHolderClient(
        http_client=http_client,
        rpc_pools={"ethereum": (
            "https://dead.invalid", "https://good.invalid"
        )},
        min_interval=0,
    )
    await client.scan(
        PREDEFINED_NFT_COLLECTIONS[0], ["0x" + "1" * 40]
    )
    assert {host for host, _method in requests} == {
        "dead.invalid", "good.invalid"
    }

    dead_only = NftHolderClient(
        http_client=http_client,
        rpc_pools={"ethereum": ("https://dead.invalid",)},
        min_interval=0,
    )
    with pytest.raises(NftHolderUnavailable, match="RPC unavailable"):
        await dead_only.scan(
            PREDEFINED_NFT_COLLECTIONS[0], ["0x" + "1" * 40]
        )
    await client.close()
    await dead_only.close()
    await http_client.aclose()


@pytest.mark.asyncio
async def test_balance_scans_chunk_at_exactly_500_and_keep_alignment():
    chunks = []
    wallets = [f"0x{index:040x}" for index in range(1, 1002)]

    async def handler(request):
        body = json.loads(request.content)
        if body["method"] == "eth_getCode":
            return _rpc_result(body["id"], "0x6000")
        if body["method"] == "eth_blockNumber":
            return _rpc_result(body["id"], "0x999")
        count = _call_count(body["params"][0]["data"])
        chunks.append(count)
        return _rpc_result(
            body["id"],
            _results([(True, index % 2) for index in range(count)]),
        )

    client, http_client = _client(handler)
    scan = await client.scan(PREDEFINED_NFT_COLLECTIONS[0], wallets)
    assert chunks == [500, 500, 1]
    assert (scan.checked, scan.failed) == (1001, 0)
    assert len(scan.holders) == 500
    await client.close()
    await http_client.aclose()


@pytest.mark.asyncio
async def test_subcall_failure_is_incomplete_not_a_false_nonholder():
    methods = []

    async def handler(request):
        body = json.loads(request.content)
        methods.append(body["method"])
        if body["method"] == "eth_getCode":
            return _rpc_result(body["id"], "0x6000")
        if body["method"] == "eth_blockNumber":
            return _rpc_result(body["id"], "0x999")
        return _rpc_result(body["id"], _results([
            (True, 0), (False, None)
        ]))

    client, http_client = _client(handler)
    scan = await client.scan(
        PREDEFINED_NFT_COLLECTIONS[3],
        ["0x" + "1" * 40, "0x" + "2" * 40],
    )
    assert (scan.checked, scan.failed, scan.complete) == (1, 1, False)
    assert methods == ["eth_getCode", "eth_blockNumber", "eth_call"]
    await client.close()
    await http_client.aclose()


@pytest.mark.asyncio
async def test_no_code_is_unavailable_and_never_runs_multicall():
    methods = []

    async def handler(request):
        body = json.loads(request.content)
        methods.append(body["method"])
        return _rpc_result(body["id"], "0x")

    client, http_client = _client(handler)
    with pytest.raises(NftHolderUnavailable, match="no contract code"):
        await client.scan(
            PREDEFINED_NFT_COLLECTIONS[0], ["0x" + "1" * 40]
        )
    assert methods == ["eth_getCode"]
    await client.close()
    await http_client.aclose()


def test_wallet_universe_fingerprint_is_case_and_order_stable():
    first = "0x" + "a" * 40
    second = "0x" + "b" * 40
    assert wallet_universe_fingerprint([second, first.upper()]) == (
        wallet_universe_fingerprint([first, second])
    )
~~~

- [ ] **Step 2: Run the new module and verify import failure**

~~~bash
.venv/bin/pytest tests/data/test_curator_nft_holders.py -q
~~~

Expected: FAIL during collection because curator_nft_holders does not exist.

- [ ] **Step 3: Implement the keyless reader**

Create maxpane_dashboard/data/curator_nft_holders.py:

~~~python
"""Keyless current-state NFT holder scans for curator list filters."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

import httpx

from maxpane_dashboard.data.curator_list_filters import (
    FilterDataUnavailable,
    NftCollectionRef,
)
from maxpane_dashboard.data.evm_abi import (
    decode_aggregate3_result,
    encode_aggregate3,
)
from maxpane_dashboard.data.rpc_common import (
    ENDPOINT_DEAD_CODES,
    OwnedHttpClient,
    jsonrpc_payload,
    pace,
)

logger = logging.getLogger(__name__)

MULTICALL3 = "0xca11bde05977b3631167028862be2a173976ca11"
BALANCE_OF = "0x70a08231"
MAX_BALANCES_PER_CALL = 500
DEFAULT_MIN_INTERVAL = 0.12
RPC_POOLS: Mapping[str, tuple[str, ...]] = {
    "ethereum": (
        "https://ethereum-rpc.publicnode.com",
        "https://eth.drpc.org",
    ),
    "base": (
        "https://base-rpc.publicnode.com",
        "https://mainnet.base.org",
        "https://base.llamarpc.com",
    ),
}


class NftHolderPending(FilterDataUnavailable):
    pass


class NftHolderUnavailable(FilterDataUnavailable):
    pass


@dataclass(frozen=True, slots=True)
class NftHolderScan:
    collection: NftCollectionRef
    holders: frozenset[str]
    checked: int
    failed: int
    block_number: int | None

    @property
    def complete(self) -> bool:
        return self.failed == 0


def _normalise_wallets(wallets: Iterable[object]) -> tuple[str, ...]:
    valid = {
        wallet.casefold()
        for wallet in wallets
        if isinstance(wallet, str)
        and len(wallet) == 42
        and wallet.startswith(("0x", "0X"))
        and all(char in "0123456789abcdefABCDEF" for char in wallet[2:])
    }
    return tuple(sorted(valid))


def wallet_universe_fingerprint(wallets: Iterable[object]) -> str:
    body = "\n".join(_normalise_wallets(wallets)).encode("ascii")
    return hashlib.sha256(body).hexdigest()


def _address_word(address: str) -> str:
    return address[2:].casefold().rjust(64, "0")


def _balance_call(address: str) -> str:
    return BALANCE_OF + _address_word(address)


def _uint_result(value: str) -> int | None:
    if not isinstance(value, str) or not value.startswith("0x"):
        return None
    try:
        raw = bytes.fromhex(value[2:])
    except ValueError:
        return None
    if len(raw) != 32:
        return None
    return int.from_bytes(raw, "big")


class NftHolderClient(OwnedHttpClient):
    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient | None = None,
        rpc_pools: Mapping[str, Sequence[str]] = RPC_POOLS,
        min_interval: float = DEFAULT_MIN_INTERVAL,
    ) -> None:
        self._client = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(20.0),
            headers={"User-Agent": "MaxPane/curator-nft-holders"},
        )
        self._owns_client = http_client is None
        self._rpc_pools = {
            chain: tuple(urls) for chain, urls in rpc_pools.items()
        }
        self._min_interval = float(min_interval)
        self._last_rpc_at = 0.0
        self._request_id = 0

    async def _rpc(self, chain: str, method: str, params: list):
        urls = self._rpc_pools.get(chain, ())
        if not urls:
            raise NftHolderUnavailable(f"no keyless {chain} RPC")
        last_error: Exception | None = None
        for url in urls:
            self._last_rpc_at = await pace(
                self._last_rpc_at, self._min_interval
            )
            self._request_id += 1
            request_id = self._request_id
            try:
                response = await self._client.post(
                    url,
                    json=jsonrpc_payload(request_id, method, params),
                )
                if response.status_code in ENDPOINT_DEAD_CODES:
                    raise RuntimeError(
                        f"{url}: HTTP {response.status_code}"
                    )
                response.raise_for_status()
                body = response.json()
                if not isinstance(body, dict):
                    raise RuntimeError(f"{url}: non-object RPC response")
                if body.get("id") != request_id:
                    raise RuntimeError(f"{url}: mismatched RPC id")
                if body.get("error") is not None:
                    raise RuntimeError(f"{url}: {body['error']}")
                return body.get("result")
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "NFT holder RPC %s %s failed: %s",
                    chain,
                    method,
                    exc,
                )
        raise NftHolderUnavailable(
            f"{chain} NFT holder RPC unavailable"
        ) from last_error

    async def scan(
        self,
        collection: NftCollectionRef,
        wallets: Iterable[object],
    ) -> NftHolderScan:
        addresses = _normalise_wallets(wallets)
        code = await self._rpc(
            collection.chain,
            "eth_getCode",
            [collection.address, "latest"],
        )
        if not isinstance(code, str) or code in ("0x", "0x0"):
            raise NftHolderUnavailable(
                f"{collection.label}: no contract code"
            )
        raw_block = await self._rpc(
            collection.chain, "eth_blockNumber", []
        )
        try:
            block_number = int(raw_block, 16)
        except (TypeError, ValueError):
            block_number = None

        holders: set[str] = set()
        checked = 0
        failed = 0
        for start in range(0, len(addresses), MAX_BALANCES_PER_CALL):
            chunk = addresses[
                start : start + MAX_BALANCES_PER_CALL
            ]
            calldata = encode_aggregate3(
                [
                    (collection.address, _balance_call(address), True)
                    for address in chunk
                ]
            )
            raw = await self._rpc(
                collection.chain,
                "eth_call",
                [{"to": MULTICALL3, "data": calldata}, "latest"],
            )
            decoded = (
                decode_aggregate3_result(raw)
                if isinstance(raw, str)
                else []
            )
            if len(decoded) != len(chunk):
                decoded = list(decoded[: len(chunk)])
                decoded.extend(
                    [(False, "0x")] * (len(chunk) - len(decoded))
                )
            for address, (success, value) in zip(chunk, decoded):
                balance = _uint_result(value) if success else None
                if balance is None:
                    failed += 1
                    continue
                checked += 1
                if balance > 0:
                    holders.add(address)
        return NftHolderScan(
            collection=collection,
            holders=frozenset(holders),
            checked=checked,
            failed=failed,
            block_number=block_number,
        )
~~~

Finish the new reader with this explicit export surface:

~~~python
__all__ = [
    "MAX_BALANCES_PER_CALL",
    "NftHolderClient",
    "NftHolderPending",
    "NftHolderScan",
    "NftHolderUnavailable",
    "RPC_POOLS",
    "wallet_universe_fingerprint",
]
~~~

- [ ] **Step 4: Run the reader suite**

~~~bash
.venv/bin/pytest tests/data/test_curator_nft_holders.py -q
~~~

Expected: all tests pass with no real network requests.

- [ ] **Step 5: Prove chunking and no-code validation bite**

Mutation A: change MAX_BALANCES_PER_CALL from 500 to 501. Run the chunk test; expected FAIL with [501, 500].

Mutation B: remove the eth_getCode guard. Run test_no_code_is_unavailable_and_never_runs_multicall; expected FAIL because an eth_call is recorded.

Restore both and rerun the module green.

- [ ] **Step 6: Commit Task 2**

~~~bash
git add maxpane_dashboard/data/curator_nft_holders.py tests/data/test_curator_nft_holders.py
git commit -m "feat(curator): add keyless NFT holder reader"
~~~

### Task 3: Persist Complete NFT Holder Last-Good Entries

**Files:**
- Modify: `maxpane_dashboard/data/curator_cache.py`
- Modify: `tests/data/test_curator_cache.py`

**Interfaces:**
- Consumes collection keys and wallet fingerprints as strings.
- Produces `SLOT_NFT_HOLDERS`, `NFT_HOLDER_TTL_SECONDS = 1800.0`, and
  `NftHolderCacheEntry`.
- Produces `CuratorCache.store_nft_holders(...)` and
  `CuratorCache.nft_holders(...)`.
- The additive slot is persisted by the existing generic `last_good` payload
  and is excluded from the dashboard-wide `newest_as_of()` timestamp.

- [ ] **Step 1: Write cache contract tests**

Add these imports and tests to `tests/data/test_curator_cache.py`:

~~~python
from maxpane_dashboard.data.curator_cache import (
    NFT_HOLDER_TTL_SECONDS,
    SLOT_NFT_HOLDERS,
)


def test_the_seven_slots_are_the_seven_independently_failing_sources():
    assert SLOTS == (
        SLOT_STATE,
        SLOT_LOGS,
        SLOT_WALLET,
        SLOT_CONFIG,
        SLOT_BLOCKSCOUT,
        SLOT_CLUSTERS,
        SLOT_NFT_HOLDERS,
    )


def test_nft_holder_entry_round_trips_and_expires_for_same_universe(
    cache, clock
):
    key = "ethereum:0x" + "a" * 40
    cache.store_nft_holders(
        key,
        wallet_fingerprint="fingerprint-a",
        holders=("0x" + "1" * 40,),
        checked=2,
        failed=0,
        block_number=123,
        ts=clock(),
    )
    hit = cache.nft_holders(key, "fingerprint-a")
    assert hit is not None
    assert hit.holders == frozenset({"0x" + "1" * 40})
    assert hit.fresh is True
    assert (hit.checked, hit.failed, hit.block_number) == (2, 0, 123)

    clock.advance(NFT_HOLDER_TTL_SECONDS + 1)
    stale = cache.nft_holders(key, "fingerprint-a")
    assert stale is not None and stale.fresh is False
    assert cache.nft_holders(key, "fingerprint-b") is None


def test_incomplete_nft_scan_cannot_overwrite_last_good(cache, clock):
    key = "base:0x" + "b" * 40
    cache.store_nft_holders(
        key,
        wallet_fingerprint="wallets",
        holders=(),
        checked=3,
        failed=0,
        block_number=9,
        ts=clock(),
    )
    with pytest.raises(ValueError, match="incomplete NFT holder scan"):
        cache.store_nft_holders(
            key,
            wallet_fingerprint="wallets",
            holders=("0x" + "2" * 40,),
            checked=2,
            failed=1,
            block_number=10,
            ts=clock(),
        )
    assert cache.nft_holders(key, "wallets").holders == frozenset()


def test_nft_holder_slot_persists_without_moving_global_as_of(
    tmp_path, clock
):
    path = str(tmp_path / "curator_cache.json")
    cache = CuratorCache(path=path, clock=clock)
    cache.store_last_good(SLOT_STATE, {"hour": 7}, ts=clock())
    clock.advance(60)
    cache.store_nft_holders(
        "ethereum:0x" + "c" * 40,
        wallet_fingerprint="wallets",
        holders=("0x" + "3" * 40,),
        checked=1,
        failed=0,
        block_number=None,
        ts=clock(),
    )
    assert cache.newest_as_of() == NOW
    cache.save()

    restored = CuratorCache(path=path, clock=clock)
    restored.load()
    hit = restored.nft_holders(
        "ethereum:0x" + "c" * 40, "wallets"
    )
    assert hit is not None and hit.holders == frozenset({
        "0x" + "3" * 40
    })


def test_missing_or_corrupt_nft_holder_slot_degrades_to_no_entry(
    cache, clock
):
    assert cache.nft_holders("ethereum:0x" + "d" * 40, "wallets") is None
    cache.store_last_good(
        SLOT_NFT_HOLDERS,
        {"entries": {"bad": {"holders": "not-a-list"}}},
        ts=clock(),
    )
    assert cache.nft_holders("bad", "wallets") is None
~~~

Replace the existing six-slot assertion with the seven-slot test above; do not
leave both names in the module.

- [ ] **Step 2: Run the named cache tests red**

~~~bash
.venv/bin/pytest tests/data/test_curator_cache.py -k nft_holder -q
~~~

Expected: import errors for the new slot, TTL, and methods.

- [ ] **Step 3: Add the additive slot and validated entry API**

In `curator_cache.py`, import `dataclass`, add the slot to `SLOTS`, and add
the entry type next to `LastGood`:

~~~python
from dataclasses import dataclass

SLOT_NFT_HOLDERS = "nft_holders"
NFT_HOLDER_TTL_SECONDS = 1800.0

SLOTS: tuple[str, ...] = (
    SLOT_STATE,
    SLOT_LOGS,
    SLOT_WALLET,
    SLOT_CONFIG,
    SLOT_BLOCKSCOUT,
    SLOT_CLUSTERS,
    SLOT_NFT_HOLDERS,
)


@dataclass(frozen=True, slots=True)
class NftHolderCacheEntry:
    holders: frozenset[str]
    wallet_fingerprint: str
    checked: int
    failed: int
    block_number: int | None
    ts: float
    fresh: bool

    def as_of_hhmm(self) -> str:
        return time.strftime("%H:%M", time.localtime(self.ts))
~~~

Add these methods beside the analysis last-good methods:

~~~python
    def store_nft_holders(
        self,
        collection_key: str,
        *,
        wallet_fingerprint: str,
        holders: Any,
        checked: int,
        failed: int,
        block_number: int | None,
        ts: float,
    ) -> LastGood:
        if failed != 0:
            raise ValueError("incomplete NFT holder scan cannot be cached")
        if checked < 0:
            raise ValueError("NFT checked count must be non-negative")
        addresses = sorted({
            value.casefold()
            for value in holders
            if isinstance(value, str)
            and len(value) == 42
            and value.startswith(("0x", "0X"))
            and all(char in "0123456789abcdefABCDEF" for char in value[2:])
        })
        current = self.get_last_good(SLOT_NFT_HOLDERS)
        payload = current.payload if current is not None else None
        raw_entries = payload.get("entries") if isinstance(payload, Mapping) else None
        entries = dict(raw_entries) if isinstance(raw_entries, Mapping) else {}
        entries[collection_key] = {
            "wallet_fingerprint": wallet_fingerprint,
            "holders": addresses,
            "checked": checked,
            "failed": 0,
            "block_number": block_number,
            "ts": float(ts),
        }
        return self.store_last_good(
            SLOT_NFT_HOLDERS, {"entries": entries}, ts=ts
        )

    def nft_holders(
        self,
        collection_key: str,
        wallet_fingerprint: str,
        *,
        now: float | None = None,
    ) -> NftHolderCacheEntry | None:
        outer = self.get_last_good(SLOT_NFT_HOLDERS)
        payload = outer.payload if outer is not None else None
        entries = payload.get("entries") if isinstance(payload, Mapping) else None
        raw = entries.get(collection_key) if isinstance(entries, Mapping) else None
        if not isinstance(raw, Mapping):
            return None
        holders = raw.get("holders")
        fingerprint = raw.get("wallet_fingerprint")
        checked = raw.get("checked")
        failed = raw.get("failed")
        block = raw.get("block_number")
        ts = raw.get("ts")
        valid_block = block is None or (
            isinstance(block, int) and not isinstance(block, bool) and block >= 0
        )
        if not (
            fingerprint == wallet_fingerprint
            and isinstance(holders, list)
            and all(
                isinstance(value, str)
                and len(value) == 42
                and value.startswith(("0x", "0X"))
                and all(
                    char in "0123456789abcdefABCDEF"
                    for char in value[2:]
                )
                for value in holders
            )
            and isinstance(checked, int) and not isinstance(checked, bool)
            and checked >= 0
            and failed == 0
            and valid_block
            and isinstance(ts, (int, float)) and not isinstance(ts, bool)
            and math.isfinite(float(ts)) and float(ts) > 0
        ):
            return None
        stamp = float(ts)
        return NftHolderCacheEntry(
            holders=frozenset(value.casefold() for value in holders),
            wallet_fingerprint=fingerprint,
            checked=checked,
            failed=0,
            block_number=block,
            ts=stamp,
            fresh=self._now(now) - stamp <= NFT_HOLDER_TTL_SECONDS,
        )
~~~

Change `newest_as_of()` to exclude both detached derived/cross-chain slots:

~~~python
        stamps = [
            entry.ts
            for slot, entry in self.last_good.items()
            if slot not in {SLOT_CLUSTERS, SLOT_NFT_HOLDERS}
        ]
~~~

Append these exact names to the existing `__all__` list:

~~~python
    "NFT_HOLDER_TTL_SECONDS",
    "NftHolderCacheEntry",
    "SLOT_NFT_HOLDERS",
~~~

- [ ] **Step 4: Run cache tests green**

~~~bash
.venv/bin/pytest tests/data/test_curator_cache.py -q
~~~

Expected: all cache tests pass, including old-file/additive-slot cases.

- [ ] **Step 5: Prove incomplete and fingerprint guards bite**

Mutation A: remove the `failed != 0` rejection. The named incomplete test
must fail because the prior empty last-good is overwritten. Restore it.

Mutation B: remove `fingerprint == wallet_fingerprint` from the read guard.
The round-trip test must fail because `fingerprint-b` incorrectly returns the
entry. Restore it and rerun both named tests green.

- [ ] **Step 6: Commit Task 3**

~~~bash
git add maxpane_dashboard/data/curator_cache.py tests/data/test_curator_cache.py
git commit -m "feat(curator): cache NFT holder scans"
~~~

### Task 4: Detached Manager Scan Queue And Truthful Source States

**Files:**
- Modify: `maxpane_dashboard/data/curator_manager.py`
- Modify: `tests/data/test_curator_manager.py`

**Interfaces:**
- Consumes `NftHolderClient`, the Task 3 cache API, and the source rows already
  selected by `load_export_list()`.
- Extends `FilteredListResult` with `holder_receipt: str | None = None`.
- `CuratorManager.__init__` accepts
  `nft_client_factory: Callable[[], NftHolderClient] = NftHolderClient`.
- A missing uncached collection raises `NftHolderPending`; a failed collection
  with no last-good raises `NftHolderUnavailable`; stale complete data filters
  immediately and returns `NFT holders as of HH:MM`.
- The manager creates no NFT client and schedules no task for non-NFT filters.

- [ ] **Step 1: Write pending, stale, publication, and lifecycle tests**

Add the following imports and doubles to `tests/data/test_curator_manager.py`:

~~~python
from maxpane_dashboard.data.curator_list_filters import (
    PREDEFINED_NFT_COLLECTIONS,
)
from maxpane_dashboard.data.curator_nft_holders import (
    NftHolderPending,
    NftHolderScan,
    NftHolderUnavailable,
    wallet_universe_fingerprint,
)


class FakeNftClient:
    def __init__(self, answers=()):
        self.answers = list(answers)
        self.calls = []
        self.closed = False

    async def scan(self, collection, wallets):
        self.calls.append((collection.key, tuple(wallets)))
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    async def close(self):
        self.closed = True


def _nft_row(address, points=1):
    return {
        "rank": 1,
        "address": address,
        "points": points,
        "credit_eth": 1.0,
        "tx_count": 1,
        "flagged": False,
        "name": None,
        "weight_eth": 1.0,
        "first_hour": 0,
        "first_index": 1,
        "link_conf": "clean",
    }


@pytest.mark.asyncio
async def test_nft_filter_queues_once_without_blocking_or_opening_early(
    tmp_path, clock
):
    made = []
    gate = asyncio.Event()

    class BlockingNft(FakeNftClient):
        async def scan(self, collection, wallets):
            self.calls.append((collection.key, tuple(wallets)))
            await gate.wait()
            return NftHolderScan(
                collection, frozenset(), len(tuple(wallets)), 0, 1
            )

    def factory():
        client = BlockingNft()
        made.append(client)
        return client

    manager = _manager(
        tmp_path, clock, nft_client_factory=factory
    )
    assert made == []
    row = _nft_row("0x" + "1" * 40)
    spec = parse_filter_values({
        **empty_filter_values(),
        "nft_collections": (PREDEFINED_NFT_COLLECTIONS[0],),
    })
    with pytest.raises(NftHolderPending, match="loading"):
        manager.filtered_list_rows(
            tmp_path, expected_count=1, live_rows=[row],
            you_row=None, spec=spec
        )
    with pytest.raises(NftHolderPending, match="loading"):
        manager.filtered_list_rows(
            tmp_path, expected_count=1, live_rows=[row],
            you_row=None, spec=spec
        )
    await asyncio.sleep(0)
    assert len(made) == 1 and len(made[0].calls) == 1
    gate.set()
    await manager._nft_task
    await manager.close()


@pytest.mark.asyncio
async def test_fresh_and_stale_holder_sets_filter_without_false_empty(
    tmp_path, clock
):
    collection = PREDEFINED_NFT_COLLECTIONS[0]
    refreshed = NftHolderScan(
        collection, frozenset({"0x" + "1" * 40}), 2, 0, 2
    )
    nft = FakeNftClient([refreshed])
    made = []

    def factory():
        made.append(nft)
        return nft

    manager = _manager(
        tmp_path, clock,
        nft_client_factory=factory,
    )
    holder = "0x" + "1" * 40
    other = "0x" + "2" * 40
    rows = [_nft_row(holder), _nft_row(other)]
    fingerprint = wallet_universe_fingerprint(
        row["address"] for row in rows
    )
    manager.cache.store_nft_holders(
        collection.key,
        wallet_fingerprint=fingerprint,
        holders=(holder,), checked=2, failed=0,
        block_number=1, ts=clock(),
    )
    spec = FilterSpec(nft_collections=(collection,))
    fresh = manager.filtered_list_rows(
        tmp_path, expected_count=2, live_rows=rows,
        you_row=None, spec=spec
    )
    assert fresh.rows == [rows[0]]
    assert fresh.holder_receipt is None
    assert made == []

    clock.advance(NFT_HOLDER_TTL_SECONDS + 1)
    stale = manager.filtered_list_rows(
        tmp_path, expected_count=2, live_rows=rows,
        you_row=None, spec=spec
    )
    assert stale.rows == [rows[0]]
    assert stale.holder_receipt == (
        "NFT holders as of "
        + time.strftime("%H:%M", time.localtime(NOW))
    )
    assert manager._nft_task is not None
    await manager._nft_task
    await manager.close()


@pytest.mark.asyncio
async def test_complete_scan_publishes_and_incomplete_scan_preserves_last_good(
    tmp_path, clock
):
    collection = PREDEFINED_NFT_COLLECTIONS[0]
    holder = "0x" + "1" * 40
    complete = NftHolderScan(
        collection, frozenset({holder}), 1, 0, 12
    )
    incomplete = NftHolderScan(
        collection, frozenset(), 0, 0, 13
    )
    nft = FakeNftClient([complete, incomplete])
    manager = _manager(
        tmp_path, clock, nft_client_factory=lambda: nft
    )
    row = _nft_row(holder)
    spec = FilterSpec(nft_collections=(collection,))
    with pytest.raises(NftHolderPending):
        manager.filtered_list_rows(
            tmp_path, expected_count=1, live_rows=[row],
            you_row=None, spec=spec
        )
    await manager._nft_task
    hit = manager.filtered_list_rows(
        tmp_path, expected_count=1, live_rows=[row],
        you_row=None, spec=spec
    )
    assert hit.rows == [row]

    clock.advance(NFT_HOLDER_TTL_SECONDS + 1)
    manager.filtered_list_rows(
        tmp_path, expected_count=1, live_rows=[row],
        you_row=None, spec=spec
    )
    await manager._nft_task
    assert manager.cache.nft_holders(
        collection.key, wallet_universe_fingerprint([holder])
    ).holders == frozenset({holder})
    await manager.close()
    assert nft.closed is True


@pytest.mark.asyncio
async def test_total_failure_backs_off_without_second_request(
    tmp_path, clock
):
    collection = PREDEFINED_NFT_COLLECTIONS[1]
    failed = FakeNftClient([
        NftHolderUnavailable("RPC unavailable")
    ])
    manager = _manager(
        tmp_path, clock, nft_client_factory=lambda: failed
    )
    row = _nft_row("0x" + "1" * 40)
    spec = FilterSpec(nft_collections=(collection,))
    with pytest.raises(NftHolderPending):
        manager.filtered_list_rows(
            tmp_path, expected_count=1, live_rows=[row],
            you_row=None, spec=spec
        )
    await manager._nft_task
    with pytest.raises(NftHolderUnavailable, match="unavailable"):
        manager.filtered_list_rows(
            tmp_path, expected_count=1, live_rows=[row],
            you_row=None, spec=spec
        )
    assert len(failed.calls) == 1
    await manager.close()


@pytest.mark.asyncio
async def test_close_cancels_and_awaits_active_nft_scan(tmp_path, clock):
    started = asyncio.Event()
    cancelled = asyncio.Event()

    class BlockingNft(FakeNftClient):
        async def scan(self, collection, wallets):
            started.set()
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                cancelled.set()
                raise

    nft = BlockingNft()
    manager = _manager(
        tmp_path, clock, nft_client_factory=lambda: nft
    )
    row = _nft_row("0x" + "1" * 40)
    spec = FilterSpec(nft_collections=(PREDEFINED_NFT_COLLECTIONS[0],))
    with pytest.raises(NftHolderPending):
        manager.filtered_list_rows(
            tmp_path, expected_count=1, live_rows=[row],
            you_row=None, spec=spec
        )
    await started.wait()
    await manager.close()
    assert cancelled.is_set()
    assert nft.closed is True
~~~

Add `time` and `NFT_HOLDER_TTL_SECONDS` to the test module's imports for these
tests.

- [ ] **Step 2: Run the manager NFT tests red**

~~~bash
.venv/bin/pytest tests/data/test_curator_manager.py -k nft -q
~~~

Expected: constructor/signature failures and missing pending/task state.

- [ ] **Step 3: Add the lazy scan queue and holder context**

Add imports for `Callable`, `NFT_HOLDER_TTL_SECONDS`, Task 2 types, and
`wallet_universe_fingerprint`. Add these private contracts near
`FilteredListResult`:

~~~python
NFT_FAILURE_BACKOFF_SECONDS = 300.0


@dataclass(frozen=True, slots=True)
class _NftScanRequest:
    collections: tuple[NftCollectionRef, ...]
    wallets: tuple[str, ...]
    fingerprint: str

    @property
    def key(self) -> tuple[tuple[str, ...], str]:
        return tuple(item.key for item in self.collections), self.fingerprint


@dataclass(frozen=True, slots=True)
class FilteredListResult:
    rows: list[dict] | None
    complete: bool
    source_reason: str | None
    holder_receipt: str | None = None
~~~

Extend `CuratorManager.__init__` and initialize state without constructing the
client:

~~~python
        nft_client_factory: Callable[[], Any] = NftHolderClient,
    ) -> None:
        self._nft_client_factory = nft_client_factory
        self._nft_client: Any = None
        self._nft_task: Any = None
        self._nft_running_request: _NftScanRequest | None = None
        self._nft_queued_request: _NftScanRequest | None = None
        self._nft_failed_until: dict[tuple[str, str], float] = {}
~~~

Add these manager methods before `filtered_list_rows()`:

~~~python
    def _queue_nft_scan(
        self,
        collections: tuple[NftCollectionRef, ...],
        wallets: tuple[str, ...],
        fingerprint: str,
    ) -> None:
        request = _NftScanRequest(collections, wallets, fingerprint)
        running = self._nft_task
        if running is not None and not running.done():
            if (
                self._nft_running_request is None
                or self._nft_running_request.key != request.key
            ):
                self._nft_queued_request = request
            return
        self._nft_task = asyncio.ensure_future(
            self._run_nft_scan_queue(request)
        )

    async def _run_nft_scan_queue(
        self, request: _NftScanRequest
    ) -> None:
        try:
            current: _NftScanRequest | None = request
            while current is not None:
                self._nft_running_request = current
                for collection in current.collections:
                    hit = self.cache.nft_holders(
                        collection.key, current.fingerprint
                    )
                    if hit is not None and hit.fresh:
                        continue
                    failure_key = (collection.key, current.fingerprint)
                    if self._nft_failed_until.get(failure_key, 0) > self._clock():
                        continue
                    if self._nft_client is None:
                        self._nft_client = self._nft_client_factory()
                    try:
                        scan = await self._nft_client.scan(
                            collection, current.wallets
                        )
                    except Exception as exc:  # source degradation boundary
                        logger.warning("NFT holder scan failed: %s", exc)
                        self._nft_failed_until[failure_key] = (
                            self._clock() + NFT_FAILURE_BACKOFF_SECONDS
                        )
                        continue
                    if (
                        not scan.complete
                        or scan.checked != len(current.wallets)
                    ):
                        self._nft_failed_until[failure_key] = (
                            self._clock() + NFT_FAILURE_BACKOFF_SECONDS
                        )
                        continue
                    self.cache.store_nft_holders(
                        collection.key,
                        wallet_fingerprint=current.fingerprint,
                        holders=scan.holders,
                        checked=scan.checked,
                        failed=scan.failed,
                        block_number=scan.block_number,
                        ts=self._clock(),
                    )
                    self._nft_failed_until.pop(failure_key, None)
                current = self._nft_queued_request
                self._nft_queued_request = None
        finally:
            self._nft_running_request = None
            self._nft_task = None

    def _nft_filter_context(
        self,
        spec: FilterSpec,
        rows: list[dict],
    ) -> tuple[dict[str, frozenset[str]] | None, str | None]:
        if not spec.nft_collections:
            return None, None
        wallets = tuple(
            row["address"].casefold()
            for row in rows
            if isinstance(row.get("address"), str)
        )
        fingerprint = wallet_universe_fingerprint(wallets)
        found: dict[str, frozenset[str]] = {}
        stale_stamps: list[float] = []
        missing: list[NftCollectionRef] = []
        refresh: list[NftCollectionRef] = []
        for collection in spec.nft_collections:
            hit = self.cache.nft_holders(collection.key, fingerprint)
            if hit is None:
                missing.append(collection)
                refresh.append(collection)
            else:
                found[collection.key] = hit.holders
                if not hit.fresh:
                    stale_stamps.append(hit.ts)
                    refresh.append(collection)
        refreshable = tuple(
            collection for collection in refresh
            if self._nft_failed_until.get(
                (collection.key, fingerprint), 0
            ) <= self._clock()
        )
        if refreshable:
            self._queue_nft_scan(refreshable, wallets, fingerprint)
        if missing:
            blocked = any(
                self._nft_failed_until.get(
                    (item.key, fingerprint), 0
                ) > self._clock()
                for item in missing
            )
            if blocked:
                raise NftHolderUnavailable("NFT holder data unavailable")
            raise NftHolderPending("NFT holder data loading")
        receipt = None
        if stale_stamps:
            oldest = min(stale_stamps)
            receipt = "NFT holders as of " + time.strftime(
                "%H:%M", time.localtime(oldest)
            )
        return found, receipt
~~~

In `filtered_list_rows()`, call `_nft_filter_context(spec, source.rows)` after
source validation, pass its mapping into `FilterContext`, and return the
receipt as the fourth `FilteredListResult` field:

~~~python
        nft_holders, holder_receipt = self._nft_filter_context(
            spec, source.rows
        )
        context = FilterContext(
            families_by_address=(
                self._filter_families() if spec.families else None
            ),
            whale_addresses=(
                self._filter_whales(expected_count) if spec.whale else None
            ),
            nft_holders_by_collection=nft_holders,
        )
        return FilteredListResult(
            filter_rows(source.rows, spec, context),
            source.complete,
            source.reason,
            holder_receipt,
        )
~~~

Add `_cancel_nft_scan()` using the existing `_cancel_analysis()` cancellation
pattern. Call it first in `close()`, then close the lazily created NFT client,
then preserve the existing crosscheck/analysis/main-client/cache order:

~~~python
    async def _cancel_nft_scan(self) -> None:
        task = self._nft_task
        self._nft_task = None
        self._nft_queued_request = None
        if task is None:
            return
        if not task.done():
            task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def close(self) -> None:
        await self._cancel_nft_scan()
        if self._nft_client is not None:
            try:
                await self._nft_client.close()
            except Exception as exc:  # noqa: BLE001
                logger.debug("closing NFT holder client failed: %s", exc)
        await self._cancel_crosscheck()
        await self._cancel_analysis()
        try:
            await self.client.close()
        except Exception as exc:  # noqa: BLE001
            logger.debug("closing the curator client failed: %s", exc)
        finally:
            self.save_cache()
~~~

- [ ] **Step 4: Run manager tests green**

~~~bash
.venv/bin/pytest tests/data/test_curator_manager.py -q
~~~

Expected: all manager tests pass without a live request.

- [ ] **Step 5: Prove lazy construction, incomplete preservation, and backoff bite**

Mutation A: instantiate `NftHolderClient` in `__init__`. The first named test
must fail at `made == []`. Restore it.

Mutation B: remove the `scan.checked != len(current.wallets)` coverage guard.
The complete/incomplete test must fail because the zero-coverage reply
overwrites the last-good holder. Restore it.

Mutation C: remove `_nft_failed_until`. The failure test must fail because a
second scan is scheduled during the 300-second backoff. Restore it and rerun
the manager module green.

- [ ] **Step 6: Commit Task 4**

~~~bash
git add maxpane_dashboard/data/curator_manager.py tests/data/test_curator_manager.py
git commit -m "feat(curator): manage NFT holder refreshes"
~~~

### Task 5: Titled Filter Editor, NFT Selection, And Reset Command

**Files:**
- Modify: `maxpane_dashboard/widgets/curator/list_filter.py`
- Modify: `maxpane_dashboard/widgets/curator/__init__.py`
- Modify: `maxpane_dashboard/themes/minimal.tcss`
- Modify: `tests/widgets/test_curator_widgets.py`

**Interfaces:**
- The widget constructor consumes primitive predefined choices as
  `(label, chain, address)` tuples; it imports no data/model module.
- Produces `NftCollectionAddRequested(chain, address)`,
  `NftCollectionRemoveRequested(key)`, and `FilterResetRequested` messages.
- `values()` includes primitive `nft_collections` dictionaries.
- `set_values()` restores all existing fields plus predefined/custom NFT
  choices; `set_custom_nfts()` renders validated custom primitive rows.
- The screen remains responsible for validation and for actually resetting the
  retained draft.

- [ ] **Step 1: Write editor rendering, message, round-trip, and reset tests**

Replace the existing
`test_filter_editor_renders_every_approved_category_and_control` with the first
test below, then add the remaining editor tests:

~~~python
NFT_CHOICES = (
    ("Identity.md", "ethereum", "0x" + "1" * 40),
    ("Fren Pet", "base", "0x" + "2" * 40),
    ("Milady", "ethereum", "0x" + "3" * 40),
    ("Crypto Punks", "ethereum", "0x" + "4" * 40),
)


async def test_filter_editor_titles_every_group_and_centers_acceptance_copy():
    editor = CuratorListFilterEditor(nft_choices=NFT_CHOICES)
    app = _Harness(editor)
    async with app.run_test(size=(143, 42)) as pilot:
        await pilot.pause()
        text = _screen_text(app)
        for heading in (
            "JOIN", "HOUR JOINED", "RANK", "POINTS", "CREDIT",
            "WEIGHT", "DEPOSITS", "ENS", "WINDOW", "LINK BAND",
            "WHALE DEPOSIT", "LINKED PATTERNS", "AMOUNT", "SEQUENCE",
            "CADENCE", "GAS", "FUNDING", "NFT HOLDERS",
        ):
            assert heading in text
        for label, _chain, _address in NFT_CHOICES:
            assert label in text
        assert "press 'f' to accept filters" in text
        footer = editor.query_one("#curator-filter-accept")
        assert footer.styles.text_align == "center"
        for control_id in (
            "filter-join-min", "filter-join-max", "filter-hour-min",
            "filter-hour-max", "filter-rank-min", "filter-rank-max",
            "filter-points-min", "filter-points-max", "filter-credit-min",
            "filter-credit-max", "filter-weight-min", "filter-weight-max",
            "filter-deposits-min", "filter-deposits-max", "filter-ens",
            "filter-window", "filter-band", "filter-whale",
            "filter-family-amount", "filter-family-sequence",
            "filter-family-cadence", "filter-family-gas",
            "filter-family-funding", "filter-nft-chain",
            "filter-nft-address", "filter-nft-add", "filter-reset-all",
        ):
            assert editor.query_one(f"#{control_id}") is not None


async def test_editor_emits_add_remove_and_reset_commands():
    editor = CuratorListFilterEditor(nft_choices=NFT_CHOICES)
    app = _MessageHarness(editor)
    async with app.run_test(size=(143, 42)) as pilot:
        editor.query_one("#filter-nft-chain", Select).value = "base"
        editor.query_one("#filter-nft-address", Input).value = (
            "0x" + "a" * 40
        )
        await pilot.click("#filter-nft-add")
        assert app.messages[-1] == (
            "add", "base", "0x" + "a" * 40
        )

        address_input = editor.query_one("#filter-nft-address", Input)
        address_input.value = "0x" + "b" * 40
        address_input.focus()
        await pilot.press("enter")
        assert app.messages[-1] == (
            "add", "base", "0x" + "b" * 40
        )

        editor.set_custom_nfts(({
            "label": "BASE 0xaaaa…aaaa",
            "chain": "base",
            "address": "0x" + "a" * 40,
        },))
        await pilot.pause()
        await pilot.click("#filter-nft-remove-0")
        assert app.messages[-1] == (
            "remove", "base:0x" + "a" * 40
        )

        await pilot.click("#filter-reset-all")
        assert app.messages[-1] == ("reset",)


async def test_editor_round_trips_predefined_and_custom_nfts():
    editor = CuratorListFilterEditor(nft_choices=NFT_CHOICES)
    app = _Harness(editor)
    custom = {
        "label": "ETH 0xbbbb…bbbb",
        "chain": "ethereum",
        "address": "0x" + "b" * 40,
    }
    async with app.run_test(size=(143, 42)) as pilot:
        editor.set_values({
            "points_min": "10",
            "nft_collections": (
                {"label": NFT_CHOICES[0][0], "chain": NFT_CHOICES[0][1],
                 "address": NFT_CHOICES[0][2]},
                custom,
            ),
        })
        await pilot.pause()
        values = editor.values()
        assert values["points_min"] == "10"
        assert values["nft_collections"] == (
            {"label": NFT_CHOICES[0][0], "chain": NFT_CHOICES[0][1],
             "address": NFT_CHOICES[0][2]},
            custom,
        )
        assert "ETH 0xbbbb…bbbb" in _screen_text(app)


async def test_editor_compact_layout_keeps_titles_with_their_controls():
    editor = CuratorListFilterEditor(nft_choices=NFT_CHOICES)
    app = _Harness(editor)
    async with app.run_test(size=(80, 60)) as pilot:
        await pilot.pause()
        assert editor.has_class("compact-filter")
        for group in editor.query(".curator-filter-group"):
            assert group.query_one(".curator-filter-group-title")
            assert group.query("Input, Select, Checkbox")
~~~

Define `_MessageHarness` beside `_Harness` and record the three exported
messages with exact primitive tuples:

~~~python
class _MessageHarness(_Harness):
    def __init__(self, widget):
        super().__init__(widget)
        self.messages = []

    def on_nft_collection_add_requested(self, event):
        self.messages.append(("add", event.chain, event.address))

    def on_nft_collection_remove_requested(self, event):
        self.messages.append(("remove", event.key))

    def on_filter_reset_requested(self, _event):
        self.messages.append(("reset",))
~~~

- [ ] **Step 2: Run the focused editor tests red**

~~~bash
.venv/bin/pytest tests/widgets/test_curator_widgets.py -k filter_editor -q
~~~

Expected: constructor, title, control, and message failures.

- [ ] **Step 3: Replace category-only ranges with complete titled groups**

In `list_filter.py`, import `Button`, `Horizontal`, and `Message`. Replace
`RANGE_FIELDS` with these stable groups:

~~~python
FILTER_GROUPS = (
    ("JOIN", (("join_min", "from"), ("join_max", "to"))),
    ("HOUR JOINED", (("hour_min", "from"), ("hour_max", "to"))),
    ("RANK", (("rank_min", "from"), ("rank_max", "to"))),
    ("POINTS", (("points_min", "from"), ("points_max", "to"))),
    ("CREDIT", (("credit_min", "from"), ("credit_max", "to"))),
    ("WEIGHT", (("weight_min", "from"), ("weight_max", "to"))),
    ("DEPOSITS", (("deposits_min", "from"), ("deposits_max", "to"))),
)

OPTION_GROUPS = (
    ("ENS", "ens"),
    ("WINDOW", "window"),
    ("LINK BAND", "band"),
)

FAMILY_TITLES = {
    "amount": "AMOUNT",
    "sequence": "SEQUENCE",
    "cadence": "CADENCE",
    "gas": "GAS",
    "funding": "FUNDING",
}

_RANGE_NAMES = tuple(
    field for _title, fields in FILTER_GROUPS for field, _placeholder in fields
)
~~~

Add the primitive messages:

~~~python
class NftCollectionAddRequested(Message):
    def __init__(self, chain: str, address: str) -> None:
        super().__init__()
        self.chain = chain
        self.address = address


class NftCollectionRemoveRequested(Message):
    def __init__(self, key: str) -> None:
        super().__init__()
        self.key = key


class FilterResetRequested(Message):
    pass
~~~

Change the constructor to normalize supplied primitives without importing the
model:

~~~python
    def __init__(
        self,
        *args,
        nft_choices: tuple[tuple[str, str, str], ...] = (),
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._error_field: str | None = None
        self._nft_choices = tuple(nft_choices)
        self._custom_nfts: tuple[dict[str, str], ...] = ()

    @staticmethod
    def _nft_key(chain: str, address: str) -> str:
        return f"{chain}:{address.casefold()}"
~~~

Replace `compose()` with a grid of complete titled groups. Use this helper for
each range, select, whale, and linked-pattern group so compact wrapping never
separates a heading from its control:

~~~python
    def _titled_group(self, title: str, *controls):
        return Vertical(
            Label(title, classes="curator-filter-group-title"),
            *controls,
            classes="curator-filter-group",
        )

    def compose(self) -> ComposeResult:
        yield Static("", id="curator-filter-error", markup=False)
        with Grid(classes="curator-filter-groups"):
            for title, fields in FILTER_GROUPS:
                yield self._titled_group(
                    title,
                    Grid(*(
                        Input(
                            placeholder=placeholder,
                            type="number",
                            valid_empty=True,
                            compact=True,
                            id=f"filter-{field.replace('_', '-')}",
                            classes="curator-filter-field",
                        )
                        for field, placeholder in fields
                    ), classes="curator-filter-range"),
                )
            for title, field in OPTION_GROUPS:
                yield self._titled_group(
                    title,
                    Select(
                        _SELECT_OPTIONS[field], allow_blank=False,
                        value="any", compact=True,
                        id=f"filter-{field}",
                        classes="curator-filter-field",
                    ),
                )
            yield self._titled_group(
                "WHALE DEPOSIT",
                Checkbox(
                    "25 ETH or more", compact=True,
                    id="filter-whale", classes="curator-filter-field"
                ),
            )
        yield Label("LINKED PATTERNS", classes="curator-filter-section-title")
        with Grid(classes="curator-filter-groups"):
            for family in FAMILIES:
                yield self._titled_group(
                    FAMILY_TITLES[family],
                    Checkbox(
                        FAMILY_LABELS[family], compact=True,
                        id=f"filter-family-{family}",
                        classes="curator-filter-field",
                    ),
                )
        yield Label("NFT HOLDERS", classes="curator-filter-section-title")
        with Grid(classes="curator-filter-nft-presets"):
            for index, (label, _chain, _address) in enumerate(self._nft_choices):
                yield Checkbox(
                    label, compact=True, id=f"filter-nft-choice-{index}"
                )
        with Horizontal(classes="curator-filter-nft-add-row"):
            yield Select(
                (("Ethereum", "ethereum"), ("Base", "base")),
                allow_blank=False, value="ethereum", compact=True,
                id="filter-nft-chain",
            )
            yield Input(
                placeholder="0x collection address",
                id="filter-nft-address",
            )
            yield Button("+", id="filter-nft-add", compact=True)
        yield Vertical(id="filter-nft-custom-list")
        yield Button("RESET ALL", id="filter-reset-all", compact=True)
        yield Static(
            "press 'f' to accept filters",
            id="curator-filter-accept",
            markup=False,
        )
~~~

Add message routing and custom-row rendering:

~~~python
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "filter-nft-add":
            self.post_message(NftCollectionAddRequested(
                str(self.query_one("#filter-nft-chain", Select).value),
                self.query_one("#filter-nft-address", Input).value,
            ))
        elif event.button.id == "filter-reset-all":
            self.post_message(FilterResetRequested())
        elif event.button.id and event.button.id.startswith("filter-nft-remove-"):
            self.post_message(NftCollectionRemoveRequested(
                str(event.button.name)
            ))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "filter-nft-address":
            self.post_message(NftCollectionAddRequested(
                str(self.query_one("#filter-nft-chain", Select).value),
                event.value,
            ))

    def set_custom_nfts(self, values) -> None:
        self._custom_nfts = tuple(dict(value) for value in values)
        try:
            container = self.query_one("#filter-nft-custom-list", Vertical)
        except NoMatches:
            return
        container.remove_children()
        for index, value in enumerate(self._custom_nfts):
            key = self._nft_key(value["chain"], value["address"])
            container.mount(Horizontal(
                Label(value["label"]),
                Button(
                    "×", id=f"filter-nft-remove-{index}",
                    name=key, compact=True,
                ),
                classes="curator-filter-nft-selected",
            ))
~~~

Extend `values()` with selected predefined dictionaries followed by
`self._custom_nfts`:

~~~python
        selected = []
        for index, (label, chain, address) in enumerate(self._nft_choices):
            if self.query_one(
                f"#filter-nft-choice-{index}", Checkbox
            ).value:
                selected.append({
                    "label": label, "chain": chain, "address": address
                })
        values["nft_collections"] = tuple(selected) + self._custom_nfts
~~~

At the end of the existing `set_values()` range/select/family/whale reset and
restore logic, add this exact NFT restore block:

~~~python
        predefined = {
            self._nft_key(chain, address): index
            for index, (_label, chain, address) in enumerate(self._nft_choices)
        }
        for index in range(len(self._nft_choices)):
            self.query_one(
                f"#filter-nft-choice-{index}", Checkbox
            ).value = False
        custom = []
        for raw in values.get("nft_collections", ()):
            if not isinstance(raw, Mapping):
                continue
            chain = raw.get("chain")
            address = raw.get("address")
            label = raw.get("label")
            if not (
                isinstance(chain, str)
                and isinstance(address, str)
                and isinstance(label, str)
            ):
                continue
            value = {
                "label": label,
                "chain": chain,
                "address": address.casefold(),
            }
            index = predefined.get(self._nft_key(chain, address))
            if index is None:
                custom.append(value)
            else:
                self.query_one(
                    f"#filter-nft-choice-{index}", Checkbox
                ).value = True
        self.set_custom_nfts(custom)
        self.query_one("#filter-nft-chain", Select).value = "ethereum"
        self.query_one("#filter-nft-address", Input).value = ""
~~~

Replace the single `list_filter` import in `widgets/curator/__init__.py` with:

~~~python
from .list_filter import (
    CuratorListFilterEditor,
    FilterResetRequested,
    NftCollectionAddRequested,
    NftCollectionRemoveRequested,
)
~~~

Append `"FilterResetRequested"`, `"NftCollectionAddRequested"`, and
`"NftCollectionRemoveRequested"` to that module's `__all__` list.

- [ ] **Step 4: Add responsive editor CSS**

Replace the widget's obsolete category-grid rules with the following functional
`DEFAULT_CSS` rules, and mirror the same selectors in the curator list section
of `minimal.tcss` so the shipped theme and the standalone widget harness agree:

~~~css
CuratorListFilterEditor .curator-filter-groups {
    height: auto;
    grid-size: 4;
    grid-columns: 1fr 1fr 1fr 1fr;
    grid-gutter: 0 1;
}
CuratorListFilterEditor.compact-filter .curator-filter-groups {
    grid-size: 2;
    grid-columns: 1fr 1fr;
}
CuratorListFilterEditor .curator-filter-group {
    height: auto;
    min-width: 14;
    margin-bottom: 1;
}
CuratorListFilterEditor .curator-filter-group-title,
CuratorListFilterEditor .curator-filter-section-title {
    height: 1;
    color: $text-muted;
}
CuratorListFilterEditor .curator-filter-range {
    height: 3;
    grid-size: 2;
    grid-columns: 1fr 1fr;
    grid-gutter: 0 1;
}
CuratorListFilterEditor .curator-filter-nft-presets {
    height: 3;
    grid-size: 4;
    grid-columns: 1fr 1fr 1fr 1fr;
}
CuratorListFilterEditor .curator-filter-nft-add-row {
    height: 3;
}
CuratorListFilterEditor #filter-nft-chain { width: 14; }
CuratorListFilterEditor #filter-nft-address { width: 1fr; }
CuratorListFilterEditor #filter-nft-add,
CuratorListFilterEditor .curator-filter-nft-selected Button {
    width: 5;
    min-width: 5;
}
CuratorListFilterEditor #curator-filter-accept {
    width: 100%;
    height: 1;
    text-align: center;
    color: $text-muted;
}
~~~

- [ ] **Step 5: Run widget tests green**

~~~bash
.venv/bin/pytest tests/widgets/test_curator_widgets.py -k filter_editor -q
~~~

Expected: all editor tests pass at 143 and 80 columns.

- [ ] **Step 6: Prove reset and add-message guards bite**

Mutation A: make the reset button clear controls locally without posting
`FilterResetRequested`. The message test must fail because the controller is
not notified. Restore it.

Mutation B: omit the selected chain from `NftCollectionAddRequested`. The add
test must fail because Base becomes indistinguishable from Ethereum. Restore
it and rerun the focused suite green.

- [ ] **Step 7: Commit Task 5**

~~~bash
git add maxpane_dashboard/widgets/curator/list_filter.py maxpane_dashboard/widgets/curator/__init__.py maxpane_dashboard/themes/minimal.tcss tests/widgets/test_curator_widgets.py
git commit -m "feat(curator): extend the filter editor"
~~~

### Task 6: List-Only Hero And Filtered Title Presentation

**Files:**
- Modify: `maxpane_dashboard/widgets/curator/list_hero.py`
- Modify: `maxpane_dashboard/widgets/curator/lists.py`
- Modify: `tests/widgets/test_curator_widgets.py`

**Interfaces:**
- `CuratorListHero.update_data()` gains `filter_editor_open=False` and renders
  exact editor-only note copy.
- `CuratorFilteredList.update_data()` gains `filter_summary=None`.
- `mark_filter_applied(limited, holder_receipt=None)` renders stale NFT
  provenance without losing the first-1,000 boundary.
- The list-only widgets still consume primitives and remain isolated from all
  shared/non-curator heroes.

- [ ] **Step 1: Write exact hero markup and filtered-title tests**

Add these imports and tests to `tests/widgets/test_curator_widgets.py`:

~~~python
from maxpane_dashboard.widgets.curator.list_hero import (
    FILTER_EDITOR_NOTE,
    _filter_lines,
    _wallet_lines,
)


def test_filter_card_title_is_dim_and_shortcuts_share_one_left_edge():
    lines = _filter_lines({}, "full", 42)
    assert lines[0] == "[dim]THE FILTER[/]"
    assert [len(line) for line in lines[1:]] == [
        len(lines[1])
    ] * 4
    assert [line.lstrip().split()[0] for line in lines[1:]] == [
        "'1'", "'2'", "'3'", "'f'"
    ]


def test_filtered_wallet_uses_regular_suffix_and_three_green_rows():
    lines = _wallet_lines({
        "list_view": "filtered",
        "you_filtered_index": 2,
        "filtered_contributors": 10,
        "filter_summary": ("points 10+",),
        "you_address": "0x" + "1" * 40,
        "you_points": 99,
    }, "full", 42)
    assert lines[1] == "[bold]#2 of 10[/] · filtered"
    assert lines[2].startswith("[$success]")
    assert lines[3].startswith("[$success]")
    assert lines[4].startswith("[$success]")
    assert "[bold]99 pts[/]" in lines[4]


async def test_list_hero_note_changes_only_for_open_filter_editor():
    hero = CuratorListHero()
    app = _Harness(hero)
    async with app.run_test(size=(143, 10)) as pilot:
        hero.update_data(filter_editor_open=True)
        await pilot.pause()
        assert FILTER_EDITOR_NOTE in _screen_text(app)
        hero.update_data(filter_editor_open=False)
        await pilot.pause()
        assert LIST_EXPORT_SUBTITLE in _screen_text(app)
        assert FILTER_EDITOR_NOTE not in _screen_text(app)


async def test_filtered_title_styles_and_compacts_active_criteria():
    panel = CuratorFilteredList()
    app = _Harness(panel)
    rows = [{
        "rank": 1, "address": "0x" + "1" * 40, "points": 1,
        "credit_eth": 1.0, "weight_eth": 1.0, "tx_count": 1,
        "first_hour": 0, "first_index": 1, "name": None,
    }]
    async with app.run_test(size=(143, 20)) as pilot:
        panel.update_data(
            filtered_rows=rows,
            filtered_complete=True,
            filter_summary=("join #1-1,000", "NFT Identity.md"),
        )
        await pilot.pause()
        markup = panel.query_one(".curator-list-title").content
        assert "THE FILTERED LIST - 1 wallets" in markup
        assert "[not bold dim]· join #1-1,000 · NFT Identity.md[/]" in markup

        panel.update_data(
            filtered_rows=rows,
            filtered_complete=True,
            filter_summary=tuple(f"criterion-{i}-long" for i in range(8)),
        )
        await pilot.pause()
        assert "+" in _screen_text(app)
        assert panel.query_one(
            "#curator-filtered-list-table", DataTable
        ).show_horizontal_scrollbar is False


async def test_stale_nft_receipt_coexists_with_limited_source():
    panel = CuratorFilteredList()
    app = _Harness(panel)
    async with app.run_test(size=(143, 12)) as pilot:
        panel.mark_filter_applied(
            limited=True,
            holder_receipt="NFT holders as of 12:34",
        )
        await pilot.pause()
        text = _screen_text(app)
        assert "first 1,000 wallets only" in text
        assert "NFT holders as of 12:34" in text
~~~

In the same widget module, replace the two frozen Filtered standing witnesses
`#14 of 568 (filtered)` and `-- of 568 (filtered)` with
`#14 of 568 · filtered` and `-- of 568 · filtered`. These are contract updates,
not additional assertions. Add `"filter_editor_open"` to the module's
`_SCREEN_SUPPLIED` set so the widget-signature totality guard recognizes the
new controller-owned primitive.

- [ ] **Step 2: Run presentation tests red**

~~~bash
.venv/bin/pytest tests/widgets/test_curator_widgets.py -k "filter_card or filtered_wallet or list_hero_note or filtered_title or stale_nft" -q
~~~

Expected: copy, markup, signature, title, and receipt failures.

- [ ] **Step 3: Implement hero note, shortcut alignment, and wallet colors**

In `list_hero.py`, add:

~~~python
FILTER_EDITOR_NOTE = (
    "set ranges or options below · selected patterns and NFT collections "
    "match any"
)


def _filter_lines(_data: dict, _tier: str, _width: int = 0) -> list[str]:
    shortcuts = [
        "'1' - first 1000 wallets",
        "'2' - joined hour 0",
        "'3' - whale splash",
        "'f' - for more filters",
    ]
    padded_width = max(visible_len(line) for line in shortcuts)
    padded = [
        line + " " * (padded_width - visible_len(line))
        for line in shortcuts
    ]
    return _lines("THE FILTER", *padded)
~~~

This pads only to the longest pre-existing shortcut, so it cannot create a
new width overflow. Replace only the Filtered branch and final return in
`_wallet_lines()`:

~~~python
    if view == "filtered":
        standing = (
            f"[bold]{_rank(data.get('you_filtered_index'))} of "
            f"{_total(data.get('filtered_contributors'))}[/] · filtered"
        )
        detail = _compact_filter_summary(
            data.get("filter_summary"), tier, width
        )
        return _lines(
            "THE WALLET",
            standing,
            f"[$success]{detail}[/]",
            f"[$success]{_wallet_identity(data, tier)}[/]",
            f"[$success][bold]{fmt_points(data.get('you_points'))} pts[/][/]",
        )
~~~

Leave raw and cleaned construction exactly as it is. Add
`filter_editor_open=False` to `update_data()`, store it in `_payload`, and in
`_render_view()` choose the exact editor note before the existing export-note
width candidates:

~~~python
        if self._payload.get("filter_editor_open"):
            note.update(FILTER_EDITOR_NOTE)
        else:
            for candidate in (
                LIST_EXPORT_SUBTITLE,
                LIST_EXPORT_SUBTITLE_SHORT,
                LIST_EXPORT_SUBTITLE_TINY,
            ):
                if not width or len(candidate) <= width:
                    note.update(candidate)
                    break
~~~

- [ ] **Step 4: Add stable filtered-title compaction and source receipts**

In `lists.py`, import `visible_len` with `safe_markup` and add:

~~~python
def _compact_criteria(summary, budget: int) -> str:
    clauses = tuple(
        value.strip()
        for value in (summary or ())
        if isinstance(value, str) and value.strip()
    )
    for shown in range(len(clauses), -1, -1):
        hidden = len(clauses) - shown
        candidate = " · ".join(clauses[:shown])
        if hidden:
            candidate = f"{candidate} +{hidden}" if candidate else f"+{hidden}"
        if visible_len(candidate) <= max(budget, 0):
            return candidate
    return ""
~~~

In `_set_heading()`, after building the base `heading` and before
`title_with_hint()`, append criteria only for `KIND == "filtered"`. Reserve
the visible width of the existing widen hint first:

~~~python
        summary = self._payload.get("filter_summary")
        if self.KIND == "filtered" and summary:
            hint_reserve = visible_len(f"  {self._hint}") if self._hint else 0
            budget = width - visible_len(heading) - 3 - hint_reserve
            criteria = _compact_criteria(summary, budget)
            if criteria:
                heading += (
                    " [not bold dim]· "
                    + safe_markup(criteria)
                    + "[/]"
                )
~~~

Extend the receipt method without changing export receipt priority:

~~~python
    def mark_filter_applied(
        self,
        limited: bool,
        holder_receipt: str | None = None,
    ) -> None:
        self._export_path = None
        self._export_failed = False
        receipts = []
        if limited:
            receipts.append("first 1,000 wallets only")
        if holder_receipt:
            receipts.append(holder_receipt)
        self._source_receipt = " · ".join(receipts) or None
        self._render_receipt()
~~~

Finally, extend `CuratorFilteredList.update_data()` and its payload:

~~~python
    def update_data(
        self,
        filtered_rows=None,
        you_list_row=None,
        filtered_complete=None,
        filter_summary=None,
        **_kwargs,
    ) -> None:
        self._payload = {
            "rows": filtered_rows,
            "you_list_row": you_list_row,
            "wallet_count": (
                len(filtered_rows) if isinstance(filtered_rows, list) else None
            ),
            "complete": bool(filtered_complete),
            "filter_summary": tuple(filter_summary or ()),
            "seen": True,
        }
        self._render_view()
~~~

- [ ] **Step 5: Run full widget tests green**

~~~bash
.venv/bin/pytest tests/widgets/test_curator_widgets.py -q
~~~

Expected: all curator widget tests pass.

- [ ] **Step 6: Prove style and compaction guards bite**

Mutation A: put `· filtered` inside the bold span. The exact standing test
must fail. Restore it.

Mutation B: remove the `$success` wrapper from the identity line. The three
green-row test must fail. Restore it.

Mutation C: append every criterion without `_compact_criteria()`. The long
title test must fail on `+N` or scrollbar/width. Restore it and rerun the named
tests green.

- [ ] **Step 7: Commit Task 6**

~~~bash
git add maxpane_dashboard/widgets/curator/list_hero.py maxpane_dashboard/widgets/curator/lists.py tests/widgets/test_curator_widgets.py
git commit -m "feat(curator): refine filtered list presentation"
~~~

### Task 7: Screen Controller Integration, Pending Publication, Reset, And Export Gate

**Files:**
- Modify: `maxpane_dashboard/screens/curator.py`
- Modify: `tests/screens/test_curator_screen.py`
- Modify: `tests/test_curator_registration.py`

**Interfaces:**
- The screen converts model constants to primitive editor choices.
- The screen validates add/remove events, owns draft reset, and preserves the
  active table until reset is accepted with `f`.
- Accepted NFT filters close the editor on `NftHolderPending` or
  `NftHolderUnavailable`, render the explicit table state, and are recomputed
  on normal refresh.
- Synchronous `FilterValidationError` and non-NFT `FilterDataUnavailable`
  continue to keep the editor open.
- Pending/unavailable rows remain `None`; valid zero matches remain `[]` and
  are exportable.

- [ ] **Step 1: Extend the fake manager and write controller-flow tests**

In `tests/screens/test_curator_screen.py`, extend `_FakeManager` with
`filtered_holder_receipt = None`, `nft_holders_by_collection = {}`, and pass
those values through its `FilterContext` / `FilteredListResult`:

~~~python
        context = FilterContext(
            families_by_address=(
                self.families_by_address if spec.families else None
            ),
            whale_addresses=(
                self.whale_addresses if spec.whale else None
            ),
            nft_holders_by_collection=(
                self.nft_holders_by_collection
                if spec.nft_collections else None
            ),
        )
        return FilteredListResult(
            filter_rows(live_rows, spec, context),
            self.filtered_complete,
            self.filtered_source_reason,
            self.filtered_holder_receipt,
        )
~~~

Add imports for `PREDEFINED_NFT_COLLECTIONS`, `NftHolderPending`,
`NftHolderUnavailable`, `FILTER_EDITOR_NOTE`, `LIST_EXPORT_SUBTITLE`,
`Checkbox`, `Input`, and `Select`, then add:

Also update the two pre-existing screen witnesses from
`#2 of 3 (filtered)` / `#3 of 3 (filtered)` to
`#2 of 3 · filtered` / `#3 of 3 · filtered`, and add
`"filter_editor_open"` to
`test_list_hero_screen_primitives_are_explicitly_named()`'s expected set.

~~~python
async def test_screen_adds_removes_and_deduplicates_custom_collection():
    screen = _screen(_list_payload(1))
    app = _ThemedHarness(screen)
    address = "0x" + "a" * 40
    async with app.run_test(size=(143, 48)) as pilot:
        await screen._do_refresh()
        await pilot.press("l", "f")
        editor = screen.query_one(CuratorListFilterEditor)
        editor.query_one("#filter-nft-chain", Select).value = "base"
        editor.query_one("#filter-nft-address", Input).value = address
        await pilot.click("#filter-nft-add")
        await pilot.pause()
        assert editor.values()["nft_collections"] == ({
            "label": "BASE 0xaaaa…aaaa",
            "chain": "base",
            "address": address,
        },)
        assert editor.query_one("#filter-nft-address", Input).value == ""

        editor.query_one("#filter-nft-address", Input).value = (
            "0x" + address[2:].upper()
        )
        await pilot.click("#filter-nft-add")
        await pilot.pause()
        assert "already selected" in _screen_text(app)
        assert len(editor.values()["nft_collections"]) == 1

        await pilot.click("#filter-nft-remove-0")
        await pilot.pause()
        assert editor.values()["nft_collections"] == ()

        nft_input = editor.query_one("#filter-nft-address", Input)
        nft_input.value = "0x1234"
        await pilot.click("#filter-nft-add")
        await pilot.pause()
        assert nft_input.has_class("filter-invalid")

        nft_input.value = PREDEFINED_NFT_COLLECTIONS[1].address
        await pilot.click("#filter-nft-add")
        await pilot.pause()
        assert "already available above" in _screen_text(app)
        assert editor.values()["nft_collections"] == ()


async def test_reset_all_clears_draft_but_not_active_filter_until_acceptance():
    payload = _list_payload(3)
    screen = _screen(payload)
    app = _ThemedHarness(screen)
    async with app.run_test(size=(143, 48)) as pilot:
        await screen._do_refresh()
        await pilot.press("l", "2", "f")
        active = screen._active_filter
        editor = screen.query_one(CuratorListFilterEditor)
        editor.query_one("#filter-points-min", Input).value = "10"
        editor.query_one("#filter-family-amount", Checkbox).value = True
        await pilot.click("#filter-reset-all")
        await pilot.pause()
        assert screen._active_filter == active
        assert editor.values() == empty_filter_values()
        await pilot.press("f")
        await pilot.pause()
        assert screen._active_filter.active is False
        assert screen._filtered_rows == []


async def test_accepting_uncached_nft_filter_closes_editor_and_shows_loading(
    monkeypatch,
):
    payload = _list_payload(1)
    screen = _screen(payload)

    def pending(*_args, **_kwargs):
        raise NftHolderPending("NFT holder data loading")

    monkeypatch.setattr(screen._data_manager, "filtered_list_rows", pending)
    app = _ThemedHarness(screen)
    async with app.run_test(size=(143, 48)) as pilot:
        await screen._do_refresh()
        await pilot.press("l", "f")
        screen.query_one("#filter-nft-choice-0", Checkbox).value = True
        await pilot.press("f")
        await pilot.pause()
        assert screen._filter_editor_open is False
        assert screen.query_one(CuratorFilteredList).display is True
        assert screen._active_filter.nft_collections == (
            PREDEFINED_NFT_COLLECTIONS[0],
        )
        assert screen._filtered_rows is None
        assert "NFT holder data loading" in _screen_text(app)
        assert FILTER_EDITOR_NOTE not in _screen_text(app)
        assert LIST_EXPORT_SUBTITLE in _screen_text(app)


async def test_normal_refresh_publishes_completed_nft_filter_and_title(
    monkeypatch,
):
    payload = _list_payload(2)
    screen = _screen(payload)
    calls = 0

    def result(*_args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise NftHolderPending("NFT holder data loading")
        return FilteredListResult(
            [payload["leaderboard_rows"][0]], True, None, None
        )

    monkeypatch.setattr(screen._data_manager, "filtered_list_rows", result)
    app = _ThemedHarness(screen)
    async with app.run_test(size=(143, 48)) as pilot:
        await screen._do_refresh()
        await pilot.press("l", "f")
        screen.query_one("#filter-nft-choice-0", Checkbox).value = True
        await pilot.press("f")
        await screen._do_refresh()
        await pilot.pause()
        panel = _region_text(app, screen.query_one(CuratorFilteredList), screen)
        assert screen._filtered_rows == [payload["leaderboard_rows"][0]]
        assert "THE FILTERED LIST - 1 wallets" in panel
        assert "NFT Identity.md" in panel


@pytest.mark.parametrize(
    ("error", "copy"),
    (
        (NftHolderPending("NFT holder data loading"), "loading"),
        (NftHolderUnavailable("NFT holder data unavailable"), "unavailable"),
    ),
)
async def test_pending_or_unavailable_nft_filter_never_overwrites_export(
    tmp_path, monkeypatch, error, copy
):
    path = tmp_path / "curator_filtered_list.json"
    path.write_bytes(b'[{"prior": true}]')
    screen = _export_screen(tmp_path, _list_payload(1))

    def fail(*_args, **_kwargs):
        raise error

    monkeypatch.setattr(screen._data_manager, "filtered_list_rows", fail)
    app = _ThemedHarness(screen)
    async with app.run_test(size=(143, 48)) as pilot:
        await screen._do_refresh()
        await pilot.press("l", "f")
        screen.query_one("#filter-nft-choice-0", Checkbox).value = True
        await pilot.press("f", "e")
        await pilot.pause()
        assert copy in _screen_text(app)
    assert path.read_bytes() == b'[{"prior": true}]'


async def test_valid_zero_nft_holders_exports_real_empty_array(tmp_path):
    payload = _list_payload(2)
    screen = _export_screen(tmp_path, payload)
    collection = PREDEFINED_NFT_COLLECTIONS[0]
    screen._data_manager.nft_holders_by_collection = {
        collection.key: frozenset()
    }
    screen._data_manager.filtered_complete = True
    screen._data_manager.filtered_source_reason = None
    app = _ThemedHarness(screen)
    async with app.run_test(size=(143, 48)) as pilot:
        await screen._do_refresh()
        await pilot.press("l", "f")
        screen.query_one("#filter-nft-choice-0", Checkbox).value = True
        await pilot.press("f", "e")
        await pilot.pause()
    assert json.loads(
        (tmp_path / "curator_filtered_list.json").read_text()
    ) == []
~~~

- [ ] **Step 2: Run screen flow tests red**

~~~bash
.venv/bin/pytest tests/screens/test_curator_screen.py -k "custom_collection or reset_all or uncached_nft or completed_nft or pending_or_unavailable_nft or zero_nft" -q
~~~

Expected: composition, event, pending-close, dispatch, and title failures.

- [ ] **Step 3: Compose primitive NFT choices and handle editor messages**

Import the Task 1 model names, Task 2 exceptions, and Task 5 messages. Compose
the editor as:

~~~python
            yield CuratorListFilterEditor(nft_choices=tuple(
                (item.label, item.chain, item.address)
                for item in PREDEFINED_NFT_COLLECTIONS
            ))
~~~

Add these controller helpers and handlers:

~~~python
    @staticmethod
    def _nft_primitive(item) -> dict[str, str]:
        return {
            "label": item.label,
            "chain": item.chain,
            "address": item.address,
        }

    def _custom_nft_values(self, editor) -> list[dict[str, str]]:
        predefined = {item.key for item in PREDEFINED_NFT_COLLECTIONS}
        custom = []
        for raw in editor.values().get("nft_collections", ()):
            item = parse_nft_collection(raw)
            if item.key not in predefined:
                custom.append(self._nft_primitive(item))
        return custom

    def on_nft_collection_add_requested(
        self, event: NftCollectionAddRequested
    ) -> None:
        editor = self.query_one(CuratorListFilterEditor)
        try:
            item = parse_nft_collection({
                "chain": event.chain,
                "address": event.address,
                "label": None,
            })
            predefined = {value.key for value in PREDEFINED_NFT_COLLECTIONS}
            existing = {
                parse_nft_collection(value).key
                for value in editor.values().get("nft_collections", ())
            }
            if item.key in predefined:
                raise FilterValidationError(
                    "nft_address", "collection is already available above"
                )
            if item.key in existing:
                raise FilterValidationError(
                    "nft_address", "collection is already selected"
                )
        except FilterValidationError as exc:
            editor.show_error("nft_address", str(exc))
            return
        custom = self._custom_nft_values(editor)
        custom.append(self._nft_primitive(item))
        editor.set_custom_nfts(custom)
        editor.query_one("#filter-nft-address", Input).value = ""
        editor.clear_error()

    def on_nft_collection_remove_requested(
        self, event: NftCollectionRemoveRequested
    ) -> None:
        editor = self.query_one(CuratorListFilterEditor)
        custom = [
            value for value in self._custom_nft_values(editor)
            if f"{value['chain']}:{value['address'].casefold()}" != event.key
        ]
        editor.set_custom_nfts(custom)
        editor.clear_error()

    def on_filter_reset_requested(self, _event: FilterResetRequested) -> None:
        self._custom_filter_values = empty_filter_values()
        editor = self.query_one(CuratorListFilterEditor)
        editor.set_values(self._custom_filter_values)
        editor.clear_error()
~~~

Add the `Input` import used by the controller. No widget imports a model.

- [ ] **Step 4: Store holder receipts and accept asynchronous source states**

Initialize `self._filtered_holder_receipt: str | None = None`. Extend storage:

~~~python
    def _store_filter_result(self, spec: FilterSpec, result) -> None:
        self._active_filter = spec
        self._filter_summary = filter_summary(spec)
        self._filtered_rows = result.rows
        self._filtered_complete = result.complete
        self._filtered_source_reason = result.source_reason
        self._filtered_holder_receipt = result.holder_receipt
        self._you_filtered_index = None

    def _store_filter_unavailable(self, spec: FilterSpec, reason: str) -> None:
        self._active_filter = spec
        self._filter_summary = filter_summary(spec)
        self._filtered_rows = None
        self._filtered_complete = False
        self._filtered_source_reason = reason
        self._filtered_holder_receipt = None
        self._you_filtered_index = None
~~~

In `_apply_filter()` and the success branch of `_refresh_active_filter()`, call:

~~~python
            panel.mark_filter_applied(
                limited=not result.complete,
                holder_receipt=result.holder_receipt,
            )
~~~

In `action_toggle_filter()`, keep parse/non-NFT evidence failures in the editor,
but accept cross-chain source states:

~~~python
        try:
            self._apply_filter(spec)
        except (NftHolderPending, NftHolderUnavailable) as exc:
            reason = str(exc)
            data = self._title_data or {}
            self._store_filter_unavailable(spec, reason)
            self._dispatch_filtered_list(data)
            self.query_one(CuratorFilteredList).mark_filter_unavailable(reason)
            self._dispatch_list_hero(data)
            self._filter_editor_open = False
            self._show_list_view()
            return
        except FilterDataUnavailable as exc:
            editor.show_error(None, str(exc))
            return
        self._filter_editor_open = False
        self._show_list_view()
~~~

The existing `_refresh_active_filter()` generic `FilterDataUnavailable` branch
already turns later pending/failure into `rows=None`. Keep its saved-receipt
preservation guard, and ensure a later success uses `result.holder_receipt`.

- [ ] **Step 5: Dispatch the editor flag and criteria summary**

Extend `WIDGET_SIGNATURES` and `SCREEN_SUPPLIED`:

~~~python
    "CuratorListHero": (
        "phase", "list_view", "contributors_total", "deposits_total",
        "volume_routed_eth", "you_address", "you_ens", "you_rank",
        "you_clean_rank", "you_filtered_index", "you_first_index",
        "you_first_hour", "you_points", "clean_contributors", "clean_points",
        "filtered_contributors", "filtered_points", "filter_summary",
        "filter_editor_open",
    ),
    "CuratorFilteredList": (
        "filtered_rows", "you_list_row", "filtered_complete",
        "filter_summary",
    ),

SCREEN_SUPPLIED = frozenset({
    "you_address", "list_view", "filtered_contributors", "filtered_points",
    "you_filtered_index", "you_first_index", "you_first_hour",
    "filter_summary", "filtered_rows", "filtered_complete",
    "filter_editor_open",
})
~~~

Replace the three existing definitions with the complete values above.
Dispatch the values:

~~~python
    def _dispatch_filtered_list(self, data: dict) -> None:
        self._dispatch(CuratorFilteredList, {
            **data,
            "filtered_rows": self._filtered_rows,
            "filtered_complete": self._filtered_complete,
            "filter_summary": self._filter_summary,
        })

    # In _dispatch_list_hero's mapping:
                "filter_summary": self._filter_summary,
                "filter_editor_open": self._filter_editor_open,
~~~

- [ ] **Step 6: Run registration, screen, and export tests green**

~~~bash
.venv/bin/pytest tests/test_curator_registration.py tests/screens/test_curator_screen.py -q
~~~

Expected: all structural/signature, flow, width, refresh, and export tests pass.

- [ ] **Step 7: Prove acceptance, reset, and export guards bite**

Mutation A: leave the editor open on `NftHolderPending`. The uncached test must
fail on visibility and editor-only note copy. Restore it.

Mutation B: have reset overwrite `_active_filter`. The reset test must fail
before the second `f`. Restore it.

Mutation C: convert pending rows from `None` to `[]`. The export-preservation
test must fail because the old file is overwritten. Restore it and rerun the
named tests green.

- [ ] **Step 8: Commit Task 7**

~~~bash
git add maxpane_dashboard/screens/curator.py tests/screens/test_curator_screen.py tests/test_curator_registration.py
git commit -m "feat(curator): integrate NFT list filters"
~~~

### Task 8: Cross-Layer Regression, Layout Sweep, And Final Verification

**Files:**
- Modify: `tests/screens/test_curator_screen.py`
- Modify: `tests/widgets/test_curator_widgets.py`
- Modify: `tests/test_curator_registration.py`

**Interfaces:**
- Adds no production API.
- Pins the final 143-column editor/list composites, keyless/MVC import
  boundaries, and unchanged raw/cleaned/shared views.

- [ ] **Step 1: Add final composite and structural regression tests**

Add these tests using the existing themed screen harness and repository-root
helpers:

~~~python
async def test_filter_editor_composite_fits_143_columns_and_keeps_footer():
    screen = _screen(_list_payload(100))
    app = _ThemedHarness(screen)
    async with app.run_test(size=(143, 48)) as pilot:
        await screen._do_refresh()
        await pilot.press("l", "f")
        await pilot.pause()
        editor = screen.query_one(CuratorListFilterEditor)
        editor.scroll_end(animate=False)
        await pilot.pause()
        text = _region_text(app, editor, screen)
        assert "NFT HOLDERS" in text
        assert "RESET ALL" in text
        assert "press 'f' to accept filters" in text
        assert editor.show_horizontal_scrollbar is False
        assert screen.query_one(
            CuratorListHero
        ).show_horizontal_scrollbar is False


@pytest.mark.parametrize("view", ("raw", "cleaned", "filtered"))
async def test_new_filter_copy_never_leaks_into_non_editor_list_notes(view):
    screen = _screen(_list_payload(100))
    app = _ThemedHarness(screen)
    async with app.run_test(size=(143, 48)) as pilot:
        await screen._do_refresh()
        await pilot.press("l")
        if view == "cleaned":
            await pilot.press("c")
        elif view == "filtered":
            await pilot.press("1")
        await pilot.pause()
        hero = _region_text(app, screen.query_one(CuratorListHero), screen)
        assert LIST_EXPORT_SUBTITLE in hero
        assert FILTER_EDITOR_NOTE not in hero


def test_nft_holder_data_layer_and_curator_widgets_keep_mvc_boundaries():
    root = Path(__file__).resolve().parents[1] / "maxpane_dashboard"
    holder_source = (
        root / "data" / "curator_nft_holders.py"
    ).read_text()
    assert "textual" not in holder_source
    assert "private_key" not in holder_source
    assert "eth_send" not in holder_source
    widget_source = (
        root / "widgets" / "curator" / "list_filter.py"
    ).read_text()
    assert "maxpane_dashboard.data" not in widget_source
    assert "httpx" not in widget_source
~~~

Place the first two tests in `test_curator_screen.py` and the structural test in
`test_curator_registration.py`; use that module's existing root constant when
it already exposes one.

- [ ] **Step 2: Run the final focused tests**

~~~bash
.venv/bin/pytest tests/test_curator_registration.py tests/screens/test_curator_screen.py -k "filter_editor_composite or filter_copy or nft_holder_data_layer" -q
.venv/bin/pytest tests/widgets/test_curator_widgets.py -k "filter_editor or filter_card or filtered_wallet or filtered_title or stale_nft" -q
~~~

Expected: both selections pass with no socket or horizontal scrollbar.

- [ ] **Step 3: Run all curator tests**

~~~bash
.venv/bin/pytest tests/data/test_curator_list_filters.py tests/data/test_curator_nft_holders.py tests/data/test_curator_cache.py tests/data/test_curator_manager.py tests/widgets/test_curator_widgets.py tests/screens/test_curator_screen.py tests/test_curator_registration.py -q
~~~

Expected: every curator test passes. Record the fresh pass count in the task
report rather than reusing an earlier run's count.

- [ ] **Step 4: Run the full repository suite and compare the baseline**

~~~bash
.venv/bin/pytest -q
~~~

Expected repository baseline: curator tests remain green; the only failures
permitted are the 13 already documented unrelated failures (12 FWA
accessibility nodes and 1 Surf matrix muted-floor node). Any new failure or any
curator failure blocks completion and must be diagnosed before committing.

- [ ] **Step 5: Inspect scope, secrets, and whitespace**

~~~bash
git diff --check
git diff --name-only 8e09562..HEAD
rg -n -i "private key|mnemonic|api[_ -]?key|eth_send" maxpane_dashboard/data/curator_nft_holders.py maxpane_dashboard/data/curator_manager.py
git status --short
~~~

Expected: `git diff --check` is clean; changed production files are confined to
the File Map; the scan finds no secret/signing path; the untracked live capture
fixtures remain untracked and unstaged.

- [ ] **Step 6: Prove the final MVC guard bites**

Mutation: temporarily add the following import to
`widgets/curator/list_filter.py`:

~~~python
from maxpane_dashboard.data.curator_list_filters import FilterSpec
~~~

Run `test_nft_holder_data_layer_and_curator_widgets_keep_mvc_boundaries`;
expected FAIL on `maxpane_dashboard.data`. Remove the import and rerun the
structural test green.

- [ ] **Step 7: Commit Task 8 tests explicitly**

~~~bash
git add tests/screens/test_curator_screen.py tests/widgets/test_curator_widgets.py tests/test_curator_registration.py
git commit -m "test(curator): verify NFT holder filters"
~~~

- [ ] **Step 8: Perform fresh post-commit verification**

~~~bash
.venv/bin/pytest tests/data/test_curator_list_filters.py tests/data/test_curator_nft_holders.py tests/data/test_curator_cache.py tests/data/test_curator_manager.py tests/widgets/test_curator_widgets.py tests/screens/test_curator_screen.py tests/test_curator_registration.py -q
git status --short
git log -8 --oneline
~~~

Expected: curator selection green; only the pre-existing live captures appear
in status; eight task commits appear in order after the plan commit.
