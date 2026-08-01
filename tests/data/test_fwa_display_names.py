"""Collection names and ENS labels, end to end through client and cache.

The defect this closes: the odds board derived every collection name from the
*marketplace floor lookup*, so a collection was named only if it also happened
to be priced.  On the live pool that was 1 of 52 -- one row read ``Nakamigos``
and the other 51 read ``0x26d7…fb2e``.  ERC-721 ``name()`` answers for all of
them, costs one extra multicall, and never changes once read.

No network: the multicall is a stub and every payload is a literal.
"""

from __future__ import annotations

import pytest

from maxpane_dashboard.data.evm_abi import decode_string
from maxpane_dashboard.data.fwa_cache import FWACache
from maxpane_dashboard.data.fwa_client import FWAClient

ADDR_A = "0x26d7ad0e930b54b84c00daad077ee31ba9e2fb2e"
ADDR_B = "0xd774557b647330c91bf44cfeab205095f7e6c367"
ADDR_C = "0x0000000000000000000000000000000000000bad"


def _string_return(text: str) -> str:
    raw = text.encode()
    return (
        "0x"
        + "20".rjust(64, "0")
        + hex(len(raw))[2:].rjust(64, "0")
        + raw.hex().ljust(64, "0")
    )


# ---------------------------------------------------------------------------
# decode_string
# ---------------------------------------------------------------------------


def test_decodes_the_standard_dynamic_encoding() -> None:
    assert decode_string(_string_return("Ten Thousand Tokens")) == "Ten Thousand Tokens"


def test_decodes_a_bytes32_name() -> None:
    """Several pre-ERC-721 collections still return ``bytes32`` from ``name()``."""
    payload = "0x" + b"Milady".hex().ljust(64, "0")

    assert decode_string(payload) == "Milady"


@pytest.mark.parametrize(
    "payload",
    [
        "",
        "0x",
        None,
        "0xzz",
        "0x" + "20".rjust(64, "0"),                      # offset, no length
        "0x" + "20".rjust(64, "0") + "ff" * 32,          # length far past the data
        "0x" + "20".rjust(64, "0") + "0".rjust(64, "0"), # zero length
    ],
)
def test_unusable_payloads_decode_to_none_never_empty_string(payload) -> None:
    """``None`` distinguishes "no name" from "the read failed"."""
    assert decode_string(payload) is None


def test_a_huge_length_prefix_does_not_allocate() -> None:
    """A hostile contract can claim a 4 GB string with no data behind it."""
    payload = "0x" + "20".rjust(64, "0") + "f" * 64

    assert decode_string(payload) is None


def test_non_utf8_is_rejected() -> None:
    payload = "0x" + "20".rjust(64, "0") + "04".rjust(64, "0") + "ff" * 4 + "00" * 28

    assert decode_string(payload) is None


def test_control_characters_are_stripped() -> None:
    """A lone ``\\r`` rewrites the line it lands on, markup escaping or not."""
    assert decode_string(_string_return("Evil\r\nName")) == "EvilName"


@pytest.mark.parametrize("text", ["\r\n\t", "   ", "\x00\x01\x02"])
def test_a_name_that_strips_to_nothing_is_none_not_empty(text) -> None:
    """The strip path must also honour "no name is None".

    A well-formed payload whose content is entirely whitespace or control
    characters decodes to ``""`` unless the final ``or None`` is there -- and
    an empty string is falsy in every caller, so the bug hides everywhere
    except the one place that asks ``is None``.
    """
    assert decode_string(_string_return(text)) is None


def test_length_is_capped() -> None:
    assert len(decode_string(_string_return("A" * 500)) or "") <= 128


# ---------------------------------------------------------------------------
# the client batch
# ---------------------------------------------------------------------------


class _NameChain:
    def __init__(self, names: dict[str, str], fail: set[str] = frozenset()):
        self.names = names
        self.fail = fail
        self.calls: list[tuple[str, str]] = []

    async def multicall(self, calls, block="latest"):
        self.calls.extend(calls)
        out = []
        for target, _data in calls:
            if target in self.fail:
                out.append((False, "0x"))
            else:
                out.append((True, _string_return(self.names[target])))
        return out


@pytest.mark.asyncio
async def test_fetch_collection_names_reads_every_collection() -> None:
    client = FWAClient()
    chain = _NameChain({ADDR_A: "Ten Thousand Tokens", ADDR_B: "Nakamigos"})
    client._multicall = chain.multicall

    got = await client.fetch_collection_names([ADDR_A, ADDR_B])

    assert got == {ADDR_A: "Ten Thousand Tokens", ADDR_B: "Nakamigos"}
    assert all(data == "0x06fdde03" for _t, data in chain.calls), "wrong selector"
    await client.close()


@pytest.mark.asyncio
async def test_a_contract_without_name_does_not_kill_the_batch() -> None:
    """``allowFailure`` is what makes this safe against arbitrary addresses."""
    client = FWAClient()
    chain = _NameChain({ADDR_A: "Ten Thousand Tokens"}, fail={ADDR_C})
    client._multicall = chain.multicall

    got = await client.fetch_collection_names([ADDR_A, ADDR_C])

    assert got == {ADDR_A: "Ten Thousand Tokens"}
    await client.close()


@pytest.mark.asyncio
async def test_names_are_deduped_and_lowercased() -> None:
    client = FWAClient()
    chain = _NameChain({ADDR_A: "Ten Thousand Tokens"})
    client._multicall = chain.multicall

    await client.fetch_collection_names([ADDR_A, ADDR_A.upper(), "junk", ""])

    assert len(chain.calls) == 1
    await client.close()


@pytest.mark.asyncio
async def test_a_dead_pool_degrades_to_no_names(monkeypatch) -> None:
    client = FWAClient()

    async def dead(calls, block="latest"):
        raise RuntimeError("all endpoints down")

    client._multicall = dead

    assert await client.fetch_collection_names([ADDR_A]) == {}
    await client.close()


# ---------------------------------------------------------------------------
# cache behaviour
# ---------------------------------------------------------------------------


def test_collection_names_merge_never_replace() -> None:
    """A partial batch must not delete names we already had.

    Sub-calls fail independently, so a sweep that resolves 3 of 48 is normal.
    Replacing the map wholesale would make the board flicker back to hex.
    """
    cache = FWACache(clock=lambda: 1000.0)
    cache.set_collection_names({ADDR_A: "Ten Thousand Tokens"})
    cache.set_collection_names({ADDR_B: "Nakamigos"})

    assert cache.collection_names_snapshot() == {
        ADDR_A: "Ten Thousand Tokens",
        ADDR_B: "Nakamigos",
    }


def test_blank_names_are_not_stored() -> None:
    cache = FWACache(clock=lambda: 1000.0)
    cache.set_collection_names({ADDR_A: "", ADDR_B: "   "})

    assert cache.collection_names_snapshot() == {}


def test_ens_names_expire_but_collection_names_do_not() -> None:
    """A collection's ``name()`` is fixed; an ENS name can be transferred.

    Keeping a lapsed ENS name would label an address with someone else's
    former identity -- worse than showing the hex.
    """
    now = 1000.0
    cache = FWACache(clock=lambda: now)
    cache.set_collection_names({ADDR_A: "Ten Thousand Tokens"})
    cache.set_ens_names({ADDR_B: "someone.eth"}, ts=now)

    assert cache.ens_names_fresh(60, now=now + 30) == {ADDR_B: "someone.eth"}
    assert cache.ens_names_fresh(60, now=now + 90) == {}
    # unchanged by the passage of time
    assert cache.get_collection_name(ADDR_A) == "Ten Thousand Tokens"


def test_names_survive_a_save_load_round_trip(tmp_path) -> None:
    path = str(tmp_path / "fwa_cache.json")
    cache = FWACache(clock=lambda: 1000.0)
    cache.set_collection_names({ADDR_A: "Ten Thousand Tokens"})
    cache.set_ens_names({ADDR_B: "someone.eth"}, ts=1000.0)
    cache.save_to_file(path)

    restored = FWACache(clock=lambda: 1000.0)
    restored.load_from_file(path)

    assert restored.get_collection_name(ADDR_A) == "Ten Thousand Tokens"
    assert restored.ens_names_fresh(3600, now=1000.0) == {ADDR_B: "someone.eth"}


def test_a_malformed_cached_entry_does_not_cost_the_others(tmp_path) -> None:
    """One bad row in a hand-edited cache must not drop every name."""
    import json

    path = tmp_path / "fwa_cache.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "collection_names": {ADDR_A: "Ten Thousand Tokens", ADDR_B: None},
                "ens_names": {ADDR_A: ["good.eth", 1000.0], ADDR_B: "not-a-pair"},
            }
        )
    )

    cache = FWACache(clock=lambda: 1000.0)
    cache.load_from_file(str(path))

    assert cache.get_collection_name(ADDR_A) == "Ten Thousand Tokens"
    assert cache.ens_names_fresh(3600, now=1000.0) == {ADDR_A: "good.eth"}


def test_ens_misses_are_cached_so_we_stop_asking() -> None:
    """36 of 50 live feed wallets have no ENS name.

    Without a miss cache, "no name" and "never asked" are indistinguishable, so
    every one of them is re-resolved on every 30 s tick -- four multicalls of
    pure waste per refresh, forever, against endpoints nobody pays for.
    """
    now = 1000.0
    cache = FWACache(clock=lambda: now)
    cache.note_ens_misses([ADDR_A, ADDR_B], ts=now)

    assert cache.ens_misses_fresh(3600, now=now + 60) == {ADDR_A, ADDR_B}


def test_a_miss_expires_sooner_than_a_name() -> None:
    """A wallet that later registers a name must be able to pick it up."""
    now = 1000.0
    cache = FWACache(clock=lambda: now)
    cache.note_ens_misses([ADDR_A], ts=now)

    assert cache.ens_misses_fresh(60, now=now + 90) == set()


def test_a_miss_is_not_stored_as_an_empty_name() -> None:
    """Storing ``""`` would make the address permanently unnameable."""
    now = 1000.0
    cache = FWACache(clock=lambda: now)
    cache.note_ens_misses([ADDR_A], ts=now)

    assert ADDR_A not in cache.ens_names_fresh(3600, now=now)


def test_misses_survive_a_round_trip(tmp_path) -> None:
    path = str(tmp_path / "fwa_cache.json")
    cache = FWACache(clock=lambda: 1000.0)
    cache.note_ens_misses([ADDR_A], ts=1000.0)
    cache.save_to_file(path)

    restored = FWACache(clock=lambda: 1000.0)
    restored.load_from_file(path)

    assert restored.ens_misses_fresh(3600, now=1000.0) == {ADDR_A}
