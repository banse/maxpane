"""Tier C: the first-funder lookup, keyset-paginated and resumable.

Blockscout's REST API (``eth.blockscout.com/api/v2``) is keyless, answers
httpx and curl in under a second while stalling python-urllib outright, and ran
clean at ~3 requests a second across 221 lookups with zero ``429``s.

**Resumability is the design, not a nicety.**  A funding sweep is the slow
tier: one to two calls per address, minutes long over a real cluster, and the
consumer (maxpane's detached sweep) runs it in the background across many
cycles.  So this module never takes "the population" — it takes exactly the
subset the caller wants, skips whatever the caller already ``known``s, and
reports what it could not reach in :attr:`FundingSweep.pending`.  Feeding
``pending`` back in as *addresses*, with the previous ``funding`` as ``known``,
extends coverage without re-reading a byte.

The bounded-out case is the one to get right.  ``funder is None`` means *we
could not resolve one* — never *this address has no funder*; an EOA that has
transacted always had a first funder, we may simply not have found it.  Such an
address is emitted with a ``None`` funder **and** stays in ``pending``: the row
says honestly that we looked, and the cursor says honestly that we are not
finished.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Iterable, Mapping

from ..model import Funding
from . import DEFAULT_CONFIG, DEAD_STATUS_CODES, SourceConfig, _Session, require_httpx


@dataclass(frozen=True, slots=True)
class FundingSweep:
    """What one bounded pass resolved, and what it did not.

    ``pending`` **is** the cursor: pass it back as *addresses* on the next call,
    with ``funding`` as ``known``, and coverage extends.  ``truncated`` is True
    only when the pass stopped because it ran out of budget while addresses
    were still unread — a *configuration* fact, not a source failure, and the
    caller is entitled to tell the two apart.
    """

    funding: dict[str, Funding]
    pending: tuple[str, ...]
    truncated: bool


def _first_incoming(items: Iterable[Any], address: str) -> tuple[str, int] | None:
    """The oldest transfer *into* ``address`` in *items*, as ``(funder, block)``."""
    best: tuple[str, int] | None = None
    for item in items:
        if not isinstance(item, Mapping):
            continue
        to = item.get("to")
        frm = item.get("from")
        to_hash = to.get("hash") if isinstance(to, Mapping) else to
        frm_hash = frm.get("hash") if isinstance(frm, Mapping) else frm
        if not isinstance(to_hash, str) or not isinstance(frm_hash, str):
            continue
        if to_hash.lower() != address:
            continue
        block = item.get("block_number")
        if not isinstance(block, int):
            try:
                block = int(str(block))
            except (TypeError, ValueError):
                continue
        if best is None or block < best[1]:
            best = (frm_hash.lower(), block)
    return best


async def _funder_of(
    session: _Session, address: str, max_pages: int
) -> tuple[str | None, bool, bool]:
    """``(funder, complete, reachable)`` for one address.

    Blockscout serves newest-first with a keyset cursor, so the **first**
    funder is on the last page and the cursor is followed verbatim, as query
    params, exactly as the server handed it back.

    Three answers rather than two, and the third is what keeps an outage from
    looking like a budget problem: ``complete`` is False when the pager hit its
    bound with a cursor still open, and ``reachable`` is True as soon as one
    page parsed — an address whose history simply outran the budget was read
    fine, and a pass full of those is not an outage.
    """
    httpx = require_httpx()
    url = f"{session.config.blockscout_base}/addresses/{address}/transactions"
    params: Any = {"filter": "to"}
    oldest: tuple[str, int] | None = None
    reachable = False
    for _page in range(max_pages):
        try:
            resp = await session.get(
                url, params=params, delay=session.config.blockscout_min_interval
            )
            if resp.status_code in DEAD_STATUS_CODES:
                return None, False, reachable
            resp.raise_for_status()
            body = resp.json()
        except (httpx.HTTPError, ValueError):
            return None, False, reachable
        if not isinstance(body, Mapping) or "items" not in body:
            return None, False, reachable
        reachable = True
        found = _first_incoming(body.get("items") or (), address)
        if found is not None and (oldest is None or found[1] < oldest[1]):
            oldest = found
        nxt = body.get("next_page_params")
        if not nxt:
            return (oldest[0] if oldest else None), True, True
        params = nxt  # the server's cursor, verbatim
    return None, False, reachable


async def fetch_funding(
    addresses: Iterable[str],
    *,
    known: Mapping[str, Funding] | None = None,
    budget: int | None = None,
    max_pages: int | None = None,
    config: SourceConfig = DEFAULT_CONFIG,
    client: Any = None,
    transport: Any = None,
    sleep: Callable[[float], Awaitable[None]] | None = None,
) -> FundingSweep | None:
    """First funders for *addresses*, bounded, throttled and resumable.

    *known* is whatever a previous pass resolved: those addresses are carried
    into the result untouched and are never re-read.  *budget* caps how many
    **new** addresses this pass will look up; anything beyond it lands in
    ``pending`` with ``truncated=True``.

    ``None`` only when the source could not be reached at all — never an empty
    map, which reads as "nobody has a funder".
    """
    resolved: dict[str, Funding] = {
        a.lower(): f for a, f in (known or {}).items()
    }
    wanted: list[str] = []
    seen: set[str] = set()
    for raw in addresses:
        if not isinstance(raw, str):
            continue
        key = raw.lower()
        if key in seen or key in resolved:
            continue
        seen.add(key)
        wanted.append(key)
    if not wanted:
        return FundingSweep(funding=resolved, pending=(), truncated=False)

    pages = config.blockscout_max_pages if max_pages is None else max_pages
    todo = wanted if budget is None else wanted[:budget]
    deferred = [] if budget is None else wanted[budget:]
    pending: list[str] = list(deferred)
    attempted = 0
    reached = 0

    async with _Session(config, client=client, transport=transport, sleep=sleep) as s:
        for address in todo:
            attempted += 1
            funder, complete, reachable = await _funder_of(s, address, pages)
            if reachable:
                reached += 1
            if not complete:
                # Bounded out or unreadable: the row says we looked and found
                # nothing resolvable, the cursor says we are not finished.
                pending.append(address)
            resolved[address] = Funding(
                address=address,
                funder=funder,
                hops=1 if funder else None,
            )
    if attempted and reached == 0 and not deferred:
        # Not one address answered: that is an outage, not a population of
        # wallets that nobody ever funded.
        return None
    return FundingSweep(
        funding=resolved,
        pending=tuple(pending),
        truncated=bool(deferred),
    )


__all__ = ["FundingSweep", "fetch_funding"]
