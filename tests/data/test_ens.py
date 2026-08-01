"""ENS reverse resolution, and the impersonation it must refuse.

The security-relevant property is in :func:`test_unverified_reverse_record_is_discarded`.
A reverse record is set by the address that owns it and needs no permission
from the name's owner, so anyone can point theirs at ``vitalik.eth``.  A
dashboard that renders the claimed name would let any participant relabel
themselves as anyone else in the activity feed and the crown leaderboard.  The
forward check is the only thing standing between those two states, so it is
tested by asserting the *spoof* is dropped, not merely that the honest case
works.

Transport is a stub throughout -- ``resolve_names`` takes its multicall as an
argument and this module never opens a socket.  The calldata the stub receives
is asserted against, so the encoding is pinned too.
"""

from __future__ import annotations

import pytest

from maxpane_dashboard.data import ens
from maxpane_dashboard.data.keccak import keccak256, keccak256_text

VITALIK = "0xd8da6bf26964af9d7eed9e03e53415d37aa96045"
IMPOSTOR = "0x00000000000000000000000000000000deadbeef"


# ---------------------------------------------------------------------------
# namehash
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name,expected",
    [
        ("", "00" * 32),
        ("eth", "93cdeb708b7545dc668eb9280176169d1c33cfd8ed6f04690a0bcc88a93fc4ae"),
        ("foo.eth", "de9b09fd7c5f901e23a3f19fecc54828e9c848539801e86591bd9801b019f84f"),
    ],
)
def test_namehash_matches_eip137(name, expected) -> None:
    """The vectors published in EIP-137 itself."""
    assert ens.namehash(name).hex() == expected


def test_namehash_is_recursive_not_flat() -> None:
    """``keccak(parent || keccak(label))``, not a hash of the whole string.

    Hashing the joined name is the natural-looking shortcut and produces a
    node that resolves nothing.
    """
    expected = keccak256(ens.namehash("eth") + keccak256_text("foo"))
    assert ens.namehash("foo.eth") == expected
    assert ens.namehash("foo.eth") != keccak256_text("foo.eth")


def test_reverse_name_is_lowercase_and_unprefixed() -> None:
    """The reverse node is defined over lowercase hex with no ``0x``.

    A checksummed address hashes to a different -- and empty -- node, so this
    is the difference between resolving every name and resolving none.
    """
    checksummed = "0xD8dA6BF26964aF9D7eEd9e03E53415D37aA96045"
    assert ens.reverse_name(checksummed) == f"{VITALIK[2:]}.addr.reverse"
    assert ens.reverse_node(checksummed) == ens.reverse_node(VITALIK)


# ---------------------------------------------------------------------------
# a scripted chain
# ---------------------------------------------------------------------------


def _word(value: str) -> str:
    return value.lower().replace("0x", "").rjust(64, "0")


def _string_return(text: str) -> str:
    raw = text.encode()
    return (
        "0x"
        + _word("20")
        + _word(hex(len(raw))[2:])
        + raw.hex().ljust(64, "0")
    )


class _Chain:
    """A scripted ENS: address -> claimed name, and name -> forward address."""

    def __init__(self, claims: dict[str, str], forwards: dict[str, str]):
        self.claims = claims
        self.forwards = forwards
        self.resolver = "0x000000000000000000000000000000000000fee1"
        self.batches: list[list[tuple[str, str]]] = []

    async def multicall(self, calls):
        self.batches.append(list(calls))
        out = []
        for target, data in calls:
            selector, arg = data[:10], data[10:]
            if selector == ens.SEL_RESOLVER:
                known = {
                    ens.reverse_node(a).hex() for a in self.claims
                } | {ens.namehash(n).hex() for n in self.forwards}
                out.append(
                    (True, "0x" + _word(self.resolver))
                    if arg in known
                    else (True, "0x" + _word("0"))
                )
            elif selector == ens.SEL_NAME:
                match = next(
                    (n for a, n in self.claims.items()
                     if ens.reverse_node(a).hex() == arg),
                    None,
                )
                out.append((True, _string_return(match)) if match else (True, "0x"))
            elif selector == ens.SEL_ADDR:
                match = next(
                    (addr for name, addr in self.forwards.items()
                     if ens.namehash(name).hex() == arg),
                    None,
                )
                out.append(
                    (True, "0x" + _word(match)) if match else (True, "0x" + _word("0"))
                )
            else:  # pragma: no cover - the module issues no other calls
                raise AssertionError(f"unexpected selector {selector}")
        return out


@pytest.mark.asyncio
async def test_verified_name_is_returned() -> None:
    """The honest case: reverse and forward agree."""
    chain = _Chain({VITALIK: "vitalik.eth"}, {"vitalik.eth": VITALIK})

    assert await ens.resolve_names([VITALIK], chain.multicall) == {
        VITALIK: "vitalik.eth"
    }


@pytest.mark.asyncio
async def test_unverified_reverse_record_is_discarded() -> None:
    """**The impersonation guard.**

    ``IMPOSTOR`` claims ``vitalik.eth``.  Anyone can set that record; nothing
    on chain prevents it.  Forward resolution sends ``vitalik.eth`` to its real
    owner, so the claim must be dropped and the feed must keep showing hex.

    Delete the forward check in ``resolve_names`` and this test goes red while
    every other test in this file still passes.
    """
    chain = _Chain(
        {IMPOSTOR: "vitalik.eth", VITALIK: "vitalik.eth"},
        {"vitalik.eth": VITALIK},
    )

    resolved = await ens.resolve_names([IMPOSTOR, VITALIK], chain.multicall)

    assert IMPOSTOR not in resolved, "an unverified reverse record was rendered"
    assert resolved == {VITALIK: "vitalik.eth"}


@pytest.mark.asyncio
async def test_address_without_a_record_is_absent_not_blank() -> None:
    """No name means no key -- callers fall back to the short address."""
    chain = _Chain({}, {})

    assert await ens.resolve_names([VITALIK], chain.multicall) == {}


@pytest.mark.asyncio
async def test_failed_subcalls_never_raise() -> None:
    """A pool that returns failures degrades to no names, not an exception."""

    async def dead(calls):
        return [(False, "0x") for _ in calls]

    assert await ens.resolve_names([VITALIK], dead) == {}


@pytest.mark.asyncio
async def test_calldata_targets_the_registry_and_encodes_the_node() -> None:
    """Pins the encoding: ``resolver(bytes32)`` against the ENS registry."""
    chain = _Chain({VITALIK: "vitalik.eth"}, {"vitalik.eth": VITALIK})
    await ens.resolve_names([VITALIK], chain.multicall)

    target, data = chain.batches[0][0]
    assert target == ens.ENS_REGISTRY
    assert data == ens.SEL_RESOLVER + ens.reverse_node(VITALIK).hex()
    assert len(data) == 10 + 64


@pytest.mark.asyncio
async def test_input_is_deduped_and_junk_dropped() -> None:
    """Duplicates cost round trips; malformed entries would corrupt the node."""
    chain = _Chain({VITALIK: "vitalik.eth"}, {"vitalik.eth": VITALIK})

    await ens.resolve_names(
        [VITALIK, VITALIK.upper(), "", None, "0xnothex", "0x00", ens.ZERO_ADDRESS
         if hasattr(ens, "ZERO_ADDRESS") else "0x" + "0" * 40],
        chain.multicall,
    )

    assert len(chain.batches[0]) == 1


@pytest.mark.asyncio
async def test_empty_input_makes_no_calls() -> None:
    async def explode(calls):  # pragma: no cover - must never run
        raise AssertionError("resolve_names called the chain for nothing")

    assert await ens.resolve_names([], explode) == {}
