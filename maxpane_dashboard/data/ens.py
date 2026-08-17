"""Keyless ENS reverse resolution: address -> display name.

Used wherever a dashboard would otherwise print ``0x60ce..75f6`` at a human.

**Reverse records are self-asserted and must be forward-verified.** Anyone can
point the reverse record of *their own* address at ``vitalik.eth``; nothing
stops them, because setting a reverse record needs no permission from the name's
owner.  Resolving ``address -> name`` and rendering the answer would therefore
let any participant relabel themselves as anyone in the activity feed and the
crown leaderboard.  ENS specifies the fix and this module implements it: after
reading the claimed name, resolve that name *forward* and keep it only when it
resolves back to the address we started from.  An unverified name is discarded,
not shown with a caveat -- a caveat in a 12-column table is not read.

Everything here goes through the ENS **registry** at
``0x0000...C2E074eC69A0dFb2997BA6C7d2e1e``, unchanged since 2017 and the most
stable address in ENS.  The alternatives (UniversalResolver, ReverseRecords)
would each save a round trip but have both been redeployed at new addresses
more than once; a stale constant would fail silently and permanently, which is
exactly the failure this dashboard must not have.

Transport is injected -- this module never opens a socket.  Callers pass the
same ``_multicall`` their client already uses, so ENS lookups inherit its
endpoint pool, chunking and failure handling, and tests inject a transport that
raises.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Iterable, Mapping, Sequence

from maxpane_dashboard.data.evm_abi import decode_address, decode_string, strip0x
from maxpane_dashboard.data.keccak import keccak256, keccak256_text

logger = logging.getLogger(__name__)

#: ENS registry (mainnet).  Deployed 2017, never migrated.
ENS_REGISTRY = "0x00000000000c2e074ec69a0dfb2997ba6c7d2e1e"

#: ``resolver(bytes32)`` -- registry lookup for a node's resolver.
SEL_RESOLVER = "0x0178b8bf"
#: ``name(bytes32)`` -- reverse resolver, node -> claimed name.
SEL_NAME = "0x691f3431"
#: ``addr(bytes32)`` -- forward resolver, node -> address.
SEL_ADDR = "0x3b3b57de"

ZERO_ADDRESS = "0x" + "0" * 40

#: A resolved name is immutable enough to cache for a long time, but not
#: forever -- people do change them.
DEFAULT_TTL_SECONDS = 6 * 60 * 60

#: Cap on how many addresses one call will resolve.  Four batched round trips
#: times a huge address set is a lot of work for cosmetics; the caller decides
#: which addresses matter most (see ``limit``).
MAX_ADDRESSES = 256


def namehash(name: str) -> bytes:
    """EIP-137 ``namehash`` of a dot-separated ENS name.

    ``namehash("") == b"\\x00" * 32`` and each label is folded in from the
    right: ``keccak(parent_node || keccak(label))``.
    """
    node = b"\x00" * 32
    if name:
        for label in reversed(name.split(".")):
            node = keccak256(node + keccak256_text(label))
    return node


def reverse_name(address: str) -> str:
    """The reverse-lookup ENS name for *address*.

    Always lowercase and **without** the ``0x`` prefix: the reverse node is
    defined over the lowercase hex digits, so a checksummed address hashes to a
    different -- empty -- node.
    """
    return f"{strip0x(address).lower()}.addr.reverse"


def reverse_node(address: str) -> bytes:
    """``namehash`` of *address*'s reverse-lookup name."""
    return namehash(reverse_name(address))


def _call(selector: str, node: bytes) -> str:
    """Encode a ``selector(bytes32 node)`` call."""
    return selector + node.hex()


def _normalize(addresses: Iterable[str]) -> list[str]:
    """Lowercase, de-duplicate and drop anything that is not an address."""
    seen: dict[str, None] = {}
    for addr in addresses:
        if not addr:
            continue
        raw = strip0x(str(addr)).lower()
        if len(raw) != 40:
            continue
        try:
            int(raw, 16)
        except ValueError:
            continue
        candidate = "0x" + raw
        if candidate == ZERO_ADDRESS:
            continue
        seen.setdefault(candidate, None)
    return list(seen)


def _plausible_name(name: str | None) -> bool:
    """Reject names that cannot be real before spending a verification call.

    Cheap filter, not a validator: the forward check below is what actually
    decides.  This only avoids round trips on obvious junk.
    """
    if not name or "." not in name or len(name) > 255:
        return False
    return all(label for label in name.split("."))


#: A miss expires faster than a name: an address that registers one must be able
#: to pick it up without waiting out the long TTL.
MISS_TTL_SECONDS = 60 * 60


class NameStore:
    """TTL store for verified names and for known misses.

    Extracted here so the next dashboard does not write a fourth copy of it --
    ``fwa_cache`` has the original and predates this class; it is deliberately
    left alone rather than refactored under a live dashboard.  Two rules, both
    learned there:

    * **A name expires.**  It can be transferred or allowed to lapse, and
      labelling an address with someone else's former name is worse than showing
      the hex.
    * **A miss is not an empty name.**  Most wallets have no reverse record, and
      without recording the misses every one of them is re-queried on every
      tick, because "absent from the map" and "never asked" look identical.
      A miss carries its own shorter TTL so a new registration is picked up.

    An empty resolution is never stored as a name, so an RPC failure cannot
    erase a good one -- entries age out instead.
    """

    def __init__(self, clock: Callable[[], float]) -> None:
        self._clock = clock
        self.names: dict[str, tuple[str, float]] = {}
        self.misses: dict[str, float] = {}

    def _now(self, ts: float | None = None) -> float:
        return float(self._clock()) if ts is None else float(ts)

    def set_names(self, names: Mapping[str, str], *, ts: float | None = None) -> None:
        stamp = self._now(ts)
        for addr, name in (names or {}).items():
            if not isinstance(addr, str) or not isinstance(name, str) or not name:
                continue
            key = addr.lower()
            self.names[key] = (name, stamp)
            self.misses.pop(key, None)

    def names_fresh(self, ttl_seconds: float, now: float | None = None) -> dict[str, str]:
        cutoff = self._now(now) - float(ttl_seconds)
        return {a: n for a, (n, ts) in self.names.items() if ts >= cutoff}

    def note_misses(self, addresses: Iterable[str], *, ts: float | None = None) -> None:
        stamp = self._now(ts)
        for addr in addresses or ():
            if isinstance(addr, str) and addr:
                key = addr.lower()
                if key not in self.names:
                    self.misses[key] = stamp

    def misses_fresh(self, ttl_seconds: float, now: float | None = None) -> set[str]:
        cutoff = self._now(now) - float(ttl_seconds)
        return {addr for addr, ts in self.misses.items() if ts >= cutoff}

    def as_dict(self) -> dict:
        """Serialisable form for a cache file."""
        return {
            "names": {a: [n, ts] for a, (n, ts) in self.names.items()},
            "misses": dict(self.misses),
        }

    def load(self, blob: Any) -> None:
        """Restore from :meth:`as_dict`, dropping anything malformed.

        Fail-soft per entry: one bad row in a cache file must not cost the rest,
        and it must never raise on the startup path.
        """
        if not isinstance(blob, dict):
            return
        raw_names = blob.get("names")
        if isinstance(raw_names, dict):
            for addr, pair in raw_names.items():
                if not isinstance(addr, str) or not isinstance(pair, (list, tuple)):
                    continue
                if len(pair) != 2 or not isinstance(pair[0], str):
                    continue
                try:
                    self.names[addr.lower()] = (pair[0], float(pair[1]))
                except (TypeError, ValueError):
                    continue
        raw_misses = blob.get("misses")
        if isinstance(raw_misses, dict):
            for addr, ts in raw_misses.items():
                if not isinstance(addr, str):
                    continue
                try:
                    self.misses[addr.lower()] = float(ts)
                except (TypeError, ValueError):
                    continue


MulticallFn = Callable[[Sequence[tuple[str, str]]], Awaitable[Sequence[tuple[bool, str]]]]


async def resolve_names(
    addresses: Iterable[str],
    multicall: MulticallFn,
    *,
    limit: int = MAX_ADDRESSES,
) -> dict[str, str]:
    """Resolve *addresses* to verified ENS names.

    Returns only the addresses that have a name **and** whose name resolves
    back to them -- callers fall back to a shortened address for the rest.  A
    total RPC failure yields ``{}``; it never raises and never guesses.

    Four batched round trips, each one ``aggregate3``:

    1. registry: reverse node -> reverse resolver
    2. reverse resolver: node -> claimed name
    3. registry: namehash(claimed name) -> forward resolver
    4. forward resolver: node -> address        (must equal the input)
    """
    wanted = _normalize(addresses)[: max(0, int(limit))]
    if not wanted:
        return {}

    nodes = {addr: reverse_node(addr) for addr in wanted}

    # 1. reverse resolver per address
    results = await multicall([
        (ENS_REGISTRY, _call(SEL_RESOLVER, nodes[a])) for a in wanted
    ])
    stage2: list[tuple[str, str]] = []  # (address, resolver)
    for addr, (ok, data) in zip(wanted, results):
        if not ok:
            continue
        resolver = decode_address(data)
        if resolver and resolver != ZERO_ADDRESS:
            stage2.append((addr, resolver))
    if not stage2:
        return {}

    # 2. claimed name
    results = await multicall([
        (resolver, _call(SEL_NAME, nodes[addr])) for addr, resolver in stage2
    ])
    claimed: list[tuple[str, str]] = []  # (address, name)
    for (addr, _resolver), (ok, data) in zip(stage2, results):
        if not ok:
            continue
        name = decode_string(data)
        if _plausible_name(name):
            claimed.append((addr, name))  # type: ignore[arg-type]
    if not claimed:
        return {}

    # 3. forward resolver for each claimed name
    forward_nodes = {name: namehash(name) for _addr, name in claimed}
    results = await multicall([
        (ENS_REGISTRY, _call(SEL_RESOLVER, forward_nodes[name]))
        for _addr, name in claimed
    ])
    stage4: list[tuple[str, str, str]] = []  # (address, name, resolver)
    for (addr, name), (ok, data) in zip(claimed, results):
        if not ok:
            continue
        resolver = decode_address(data)
        if resolver and resolver != ZERO_ADDRESS:
            stage4.append((addr, name, resolver))
    if not stage4:
        return {}

    # 4. the verification itself
    results = await multicall([
        (resolver, _call(SEL_ADDR, forward_nodes[name]))
        for _addr, name, resolver in stage4
    ])
    verified: dict[str, str] = {}
    for (addr, name, _resolver), (ok, data) in zip(stage4, results):
        if not ok:
            continue
        forward = decode_address(data)
        if forward.lower() == addr.lower():
            verified[addr] = name
        else:
            logger.debug(
                "ENS reverse record for %s claims %r but resolves to %s -- discarded",
                addr, name, forward,
            )
    return verified


__all__ = [
    "DEFAULT_TTL_SECONDS",
    "ENS_REGISTRY",
    "MAX_ADDRESSES",
    "namehash",
    "NameStore",
    "MISS_TTL_SECONDS",
    "resolve_names",
    "reverse_name",
    "reverse_node",
]
