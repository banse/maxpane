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


#: Why an address is still in :attr:`FundingSweep.pending`.  Three reasons, and
#: the caller is entitled to tell them apart because only one of them is ours
#: to fix.
PENDING_BUDGET = "budget"        #: this pass's ``budget`` never got to it
PENDING_PAGES = "pages"          #: its history outran ``max_pages``
PENDING_UNREADABLE = "unreadable"  #: the source did not answer for it


@dataclass(frozen=True, slots=True)
class FundingSweep:
    """What one bounded pass resolved, and what it did not.

    ``pending`` **is** the cursor: pass it back as *addresses* on the next call,
    with ``funding`` as ``known``, and coverage extends.

    **A pending address has no row in ``funding``.**  That is the whole
    resume contract and it was got wrong once: writing
    ``Funding(funder=None)`` for an address that stays pending means the very
    next call — which passes ``funding`` as ``known``, exactly as the recipe
    says — skips it, so ``pending`` resumes nothing and a transient 503 is
    frozen into a permanent "this wallet has no funder".  That is the repo's
    "corruption outlives the outage" hazard, and in WP3's persisted slot it
    would outlive the process too.  So: **resolved rows are only ever written
    for addresses that are finished**, and a finished address is one whose
    history we walked to the end.  An address we walked to the end and found no
    incoming transfer for gets a real ``Funding(funder=None)`` row and is *not*
    pending — that is a measurement, not a gap.

    ``truncated`` is True only for the **budget** case: the pass stopped
    because it ran out of its own budget while addresses were still unread.  It
    is a *configuration* fact, not a source failure.  Page-bounded and
    unreadable addresses do not set it — they are visible in
    :attr:`pending_reasons`, and :attr:`page_bounded` names the ones whose
    history simply outran ``max_pages`` (the signal that the bound, not the
    source, is what needs raising).
    """

    funding: dict[str, Funding]
    pending: tuple[str, ...]
    truncated: bool
    pending_reasons: dict[str, str]

    @property
    def page_bounded(self) -> tuple[str, ...]:
        """Pending addresses whose history outran ``max_pages``.

        Non-empty means the *pager's* bound is what stopped us, which is the
        one truncation a caller fixes by asking for more pages rather than by
        waiting for an endpoint to come back.
        """
        return tuple(
            a for a in self.pending
            if self.pending_reasons.get(a) == PENDING_PAGES
        )

    @property
    def unreadable(self) -> tuple[str, ...]:
        """Pending addresses the source did not answer for."""
        return tuple(
            a for a in self.pending
            if self.pending_reasons.get(a) == PENDING_UNREADABLE
        )


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


#: ``_funder_of``'s "we walked the whole history" answer.  Not a pending
#: reason — it is the only outcome that produces a resolved row.
_COMPLETE = "complete"


async def _funder_of(
    session: _Session, address: str, max_pages: int
) -> tuple[str | None, str, bool]:
    """``(funder, outcome, reachable)`` for one address.

    Blockscout serves newest-first with a keyset cursor, so the **first**
    funder is on the last page and the cursor is followed verbatim, as query
    params, exactly as the server handed it back.

    ``outcome`` is one of :data:`_COMPLETE`, :data:`PENDING_PAGES` or
    :data:`PENDING_UNREADABLE`, and the distinction between the last two is the
    point of this function's shape.  "Reached page ``max_pages`` with a cursor
    still open" and "a request died on page 2" are **different problems with
    opposite fixes**: the first is solved by raising ``max_pages``, and doing
    that for the second just spends more requests on an endpoint that is
    failing.  A first cut classified both as ``pages`` because the loop only
    tracked whether *any* page had parsed, so the hand-off's own advice —
    "raise ``max_pages`` for the ``pages`` ones" — pointed at exactly the wrong
    action for a mid-history failure.

    ``reachable`` stays separate from both: it is True as soon as one page
    parsed, and it is what keeps a budget or page bound from being mistaken for
    an outage.
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
                return None, PENDING_UNREADABLE, reachable
            resp.raise_for_status()
            body = resp.json()
        except (httpx.HTTPError, ValueError):
            return None, PENDING_UNREADABLE, reachable
        if not isinstance(body, Mapping) or "items" not in body:
            return None, PENDING_UNREADABLE, reachable
        reachable = True
        found = _first_incoming(body.get("items") or (), address)
        if found is not None and (oldest is None or found[1] < oldest[1]):
            oldest = found
        nxt = body.get("next_page_params")
        if not nxt:
            return (oldest[0] if oldest else None), _COMPLETE, True
        params = nxt  # the server's cursor, verbatim
    # Fell out of the loop with a cursor still open: every page we asked for
    # answered, there are simply more of them than we were willing to walk.
    return None, PENDING_PAGES, reachable


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

    **An address that stays pending gets no row in the result.**  It is not
    written as ``Funding(funder=None)`` and then skipped by the next pass's
    ``known`` — see :class:`FundingSweep`.  Only a finished address is
    resolved, and "finished" means the history was walked to the end.

    ``None`` only when the source could not be reached at all — never an empty
    map, which reads as "nobody has a funder", and never a half-full one that
    quietly forgets an outage happened.
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
        return FundingSweep(
            funding=resolved, pending=(), truncated=False, pending_reasons={}
        )

    pages = config.blockscout_max_pages if max_pages is None else max_pages
    todo = wanted if budget is None else wanted[:budget]
    deferred = [] if budget is None else wanted[budget:]
    pending: list[str] = list(deferred)
    reasons: dict[str, str] = {a: PENDING_BUDGET for a in deferred}
    attempted = 0
    reached = 0

    async with _Session(config, client=client, transport=transport, sleep=sleep) as s:
        for address in todo:
            attempted += 1
            funder, outcome, reachable = await _funder_of(s, address, pages)
            if reachable:
                reached += 1
            if outcome != _COMPLETE:
                # NOT resolved.  A row here would be read as an answer by the
                # very next pass (which passes `funding` as `known`) and the
                # address would never be looked at again.  The reason comes
                # from `_funder_of`, which is the only place that knows whether
                # the page loop ended cleanly or a request died inside it.
                pending.append(address)
                reasons[address] = outcome
                continue
            resolved[address] = Funding(
                address=address,
                funder=funder,
                hops=1 if funder else None,
            )
    if attempted and reached == 0:
        # Not one attempted address answered: that is an outage.  Deferral does
        # NOT change that — a pass with `budget=2` over five addresses where
        # both requests died is exactly as dead as one over two, and returning
        # a half-full sweep there hides a total outage behind `truncated=True`.
        return None
    return FundingSweep(
        funding=resolved,
        pending=tuple(pending),
        truncated=bool(deferred),
        pending_reasons=reasons,
    )


__all__ = [
    "PENDING_BUDGET",
    "PENDING_PAGES",
    "PENDING_UNREADABLE",
    "FundingSweep",
    "fetch_funding",
]
