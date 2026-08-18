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
address gets **no row at all** and stays in ``pending``.  Writing a
``Funding(funder=None)`` row for it would be read as an answer by the very next
pass — which passes ``funding`` back as ``known``, exactly as the resume recipe
says — so the address would never be looked at again and one bad minute would
be recorded as "this wallet has no funder", forever.  A resolved row is only
ever written for an address whose history was walked **to the end**; an address
walked to the end with no incoming transfer gets a real ``Funding(funder=None)``
row and is *not* pending, because that one is a measurement rather than a gap.
"""

from __future__ import annotations

from dataclasses import dataclass, field
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

    ``page_cursors`` is the **per-address** half of the cursor, and it is why a
    page-bounded address now finishes.  ``pending`` alone said "come back to
    this one" without saying where, so every pass re-walked the same first
    pages forever and pendings — which head the budget — crowded out addresses
    nobody had looked at yet.  Each entry is
    ``{"params": …, "funder": …, "block": …}``: where to ask next, and the
    oldest incoming transfer found so far.  Feed it back as ``cursors=``
    alongside ``pending``.  It is **defaulted and added last** so existing
    keyword construction and a payload persisted before it existed both still
    work — a consumer that ignores it simply restarts each walk at page 1.
    """

    funding: dict[str, Funding]
    pending: tuple[str, ...]
    truncated: bool
    pending_reasons: dict[str, str]
    page_cursors: dict[str, dict] = field(default_factory=dict)

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


def _cursor_of(params: Any, oldest: tuple[str, int] | None) -> dict:
    """One address's resume point: where to ask next, and the best so far.

    Blockscout serves newest-first, so a resumed walk needs exactly two things
    — the next page's params and the oldest incoming transfer seen so far.
    Everything behind the cursor is strictly older, so the answer a resumed
    walk reaches is the answer an unbounded one would have.
    """
    return {
        "params": dict(params) if isinstance(params, Mapping) else None,
        "funder": oldest[0] if oldest else None,
        "block": oldest[1] if oldest else None,
    }


def _resume_from(entry: Any) -> tuple[Any, tuple[str, int] | None]:
    """A persisted cursor entry → ``(starting params, best-so-far)``.

    Read tolerantly on purpose: this shape round-trips through a consumer's
    cache file, and a hand-edited payload is third-party input.  Anything
    unrecognisable simply starts the walk at page 1, which is the pre-cursor
    behaviour rather than an error.
    """
    if not isinstance(entry, Mapping):
        return None, None
    raw = entry.get("params")
    params = dict(raw) if isinstance(raw, Mapping) and raw else None
    funder = entry.get("funder")
    block = entry.get("block")
    oldest: tuple[str, int] | None = None
    if isinstance(funder, str) and isinstance(block, int) and not isinstance(block, bool):
        oldest = (funder.lower(), block)
    return params, oldest


async def _funder_of(
    session: _Session,
    address: str,
    max_pages: int,
    *,
    params: Any = None,
    oldest: tuple[str, int] | None = None,
) -> tuple[str | None, str, bool, dict | None]:
    """``(funder, outcome, reachable, cursor)`` for one address.

    *params* and *oldest* are a previous pass's resume point (see
    :func:`_resume_from`); with neither, the walk starts at page 1.  *cursor*
    is where this pass stopped, or ``None`` when there is nothing to resume —
    the walk finished, or it died before a single page parsed.

    Blockscout serves newest-first with a keyset cursor, so the **first**
    funder is on the last page and the cursor is followed verbatim, as query
    params, exactly as the server handed it back — **carrying our own
    ``filter=to`` with it**, because a cursor that replaces the filter asks
    every page after the first for the address's whole transaction history.

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
    query: Any = (
        {**params, "filter": "to"}
        if isinstance(params, Mapping) and params
        else {"filter": "to"}
    )
    reachable = False

    def stopped() -> dict | None:
        # A cursor is worth persisting only once a page has parsed: before
        # that, "resume here" and "start at the beginning" are the same place.
        return _cursor_of(query, oldest) if reachable else None

    for _page in range(max_pages):
        try:
            resp = await session.get(
                url, params=query, delay=session.config.blockscout_min_interval
            )
            if resp.status_code in DEAD_STATUS_CODES:
                return None, PENDING_UNREADABLE, reachable, stopped()
            resp.raise_for_status()
            body = resp.json()
        except (httpx.HTTPError, ValueError):
            return None, PENDING_UNREADABLE, reachable, stopped()
        if not isinstance(body, Mapping):
            return None, PENDING_UNREADABLE, reachable, stopped()
        items = body.get("items")
        if not isinstance(items, list):
            # `{"items": null}` from a 200 passed the old `"items" in body`
            # guard, so an unread page was treated as a finished walk and the
            # address got a resolved `funder=None` row.  A page we cannot read
            # is unreadable, whatever the status line said.
            return None, PENDING_UNREADABLE, reachable, stopped()
        reachable = True
        found = _first_incoming(items, address)
        if found is not None and (oldest is None or found[1] < oldest[1]):
            oldest = found
        nxt = body.get("next_page_params")
        if not nxt:
            return (oldest[0] if oldest else None), _COMPLETE, True, None
        if not isinstance(nxt, Mapping):
            # A cursor we cannot extend with our own filter is not the end of
            # the history: `_COMPLETE` here would resolve a row off a walk that
            # stopped early, and `{**nxt}` on a non-mapping would take the
            # caller down with a TypeError.
            return None, PENDING_UNREADABLE, reachable, stopped()
        # The server's cursor, verbatim — **plus our own filter**.  `params =
        # nxt` replaced it, so every page after the first asked for the whole
        # transaction history rather than its incoming half.
        query = {**nxt, "filter": "to"}
    # Fell out of the loop with a cursor still open: every page we asked for
    # answered, there are simply more of them than we were willing to walk.
    return None, PENDING_PAGES, reachable, stopped()


async def fetch_funding(
    addresses: Iterable[str],
    *,
    known: Mapping[str, Funding] | None = None,
    budget: int | None = None,
    max_pages: int | None = None,
    cursors: Mapping[str, Mapping] | None = None,
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

    *cursors* is the previous pass's :attr:`FundingSweep.page_cursors`, and it
    is what makes a page-bounded address finish: with it, that address's walk
    resumes at the page it stopped on instead of re-reading its first pages
    forever.  Keyword-only and defaulted, and read tolerantly — an entry that
    does not parse just starts the walk at page 1, which is what every caller
    written before ``page_cursors`` existed gets for free.

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
    prior_cursors: dict[str, Mapping] = {
        a.lower(): c
        for a, c in (cursors or {}).items()
        if isinstance(a, str) and isinstance(c, Mapping)
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
    # An address this pass never got to keeps the cursor it arrived with:
    # dropping it would restart its walk from page 1, which is the defect the
    # cursor exists to end.  A *resolved* address keeps none.
    walked_cursors: dict[str, dict] = {
        a: dict(prior_cursors[a]) for a in deferred if a in prior_cursors
    }
    attempted = 0
    reached = 0

    async with _Session(config, client=client, transport=transport, sleep=sleep) as s:
        for address in todo:
            attempted += 1
            start_params, start_oldest = _resume_from(prior_cursors.get(address))
            funder, outcome, reachable, cursor = await _funder_of(
                s, address, pages, params=start_params, oldest=start_oldest
            )
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
                if cursor is not None:
                    walked_cursors[address] = cursor
                elif address in prior_cursors:
                    walked_cursors[address] = dict(prior_cursors[address])
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
        page_cursors=walked_cursors,
    )


__all__ = [
    "PENDING_BUDGET",
    "PENDING_PAGES",
    "PENDING_UNREADABLE",
    "FundingSweep",
    "fetch_funding",
]
