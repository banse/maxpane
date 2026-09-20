"""The RPC error-message tables, and the two predicates that read them.

What lives here is **data**: the message fragments a JSON-RPC ``error`` body
is matched against, each keeping the provider and the date it was measured
from, plus the two pure predicates that walk a table -- "is this endpoint
refusing?" and "is this window too wide?".  Before this module the four
Ethereum tables existed as four hand-typed copies and had already drifted:
``curator_client`` dropped ``api key`` with no note while restating the rest,
and ``personal token`` and drpc's routing triplet each lived in exactly one
client although every Ethereum pool can meet them.

What does **not** live here is any policy that consumes them.  The five
``_rpc`` bodies stay where they are, for the reason ``rpc_common``'s docstring
sets out at length (MEDI-17): they implement individually tested error
policies, each encoding a fact about a specific chain or provider, and a
shared one would be a policy switch with every client's behaviour reachable
from every other client's bug.  Tables are evidence; rotation, shrinking,
retry ladders, pagers and exception types are judgement.  Only the evidence is
shared.

**Why two endpoint tables and two range families, and not one of each.**  A
survey of the nine error policies (2026-09-20) found seven fragments or shapes
whose *meaning* flips between clients.  Merging the tables would ship every
one of them as a silent behaviour change:

===  =========================  ==========================================
#    fragment / shape           the flip
===  =========================  ==========================================
R1   a non-``dict`` ``err``     rotate in ttt/curator/surf/surf_pool4;
                                **do not rotate** in cattown, whose caller
                                then raises.  Hence
                                ``unstructured_is_limitation``.
R2   ``query returned more      rotate on Base (cattown has no pager at
     than`` / ``response size`` all); **shrink** for curator, whose
                                contract emits ~4.3 logs a block.
R3   ``timeout``                rotate for the four Ethereum booleans;
                                shrink for talismans/fwa_logs.
R4   drpc ``code 35`` /         shrink for talismans/fwa_logs; **rotate**
     ``ranges over 10000``      for surf_pool4 once the request's own span
                                is known (see ``is_range_limitation``).
R5   ``archive``                rotate everywhere.  The one safe merge.
R6   ``rate limit``             rotate for four; retry the *same* endpoint
                                with backoff in fwa_logs.
R7   ``exceeds`` vs             different substrings, overlapping intent:
     ``exceeded``               merging them widens both tables.
===  =========================  ==========================================

So: Ethereum keeps its table (24 fragments, the union of the four that had
drifted) and Base keeps cattown's (15, unchanged -- Base providers phrase
their refusals differently, and merging would make ttt rotate on ``method not
found`` where it is terminal today).  The span family and the result-count
family stay separate because ``surf_client``'s pager treats a short read as a
success: teaching it to shrink on a result cap would be silent data loss where
today it rotates.  Each caller composes the families it can actually recover
from -- ``curator_client`` takes both, ``surf_client`` and
``surf_pool4_client`` take the span family only.

Stdlib and ``typing`` only, on purpose: the moment this imports a client for a
pool constant or a caller for a policy, the dependency graph inverts and
``rpc_common``'s "no circular hazard" property goes with it.  Pools, spans and
policy flags are passed in.
"""

from __future__ import annotations

import re
from typing import Any

__all__ = [
    "BASE_ENDPOINT_LIMITATION_FRAGMENTS",
    "ETH_ENDPOINT_LIMITATION_FRAGMENTS",
    "MALFORMED_REQUEST_CODES",
    "RANGE_CAP_FRAGMENTS",
    "RESULT_CAP_FRAGMENTS",
    "is_range_limitation",
    "looks_like_endpoint_limitation",
    "named_block_limit",
    "requested_block_span",
]


# ---------------------------------------------------------------------------
# 1. "This endpoint will not serve this request"
# ---------------------------------------------------------------------------

#: Message fragments that mean "*this endpoint* will not serve this request" --
#: capability caps, archive gates, auth walls, plan limits. Providers ship
#: these under codes that also mean "your request is malformed": 1rpc's
#: 50-block log cap arrives as **-32602**, the same code as genuine bad input,
#: and publicnode's archive gate is a plain-language message too. Classifying
#: on the code alone therefore aborts the whole fallback chain at the first
#: endpoint that simply cannot do the job. Match on the message instead.
#: (Fragments were taken from live responses, see ``ttt_client._ENDPOINT_PROBE``.)
#:
#: The union of what ``ttt_client`` (21), ``surf_client`` (20),
#: ``surf_pool4_client`` (20) and ``curator_client`` (22) each carried on
#: 2026-09-20. It widens each of the four in the **rotate** direction only: a
#: fragment more means one more shape of refusal that reaches the next
#: endpoint instead of killing the chain. No shrink path reads this table.
ETH_ENDPOINT_LIMITATION_FRAGMENTS: tuple[str, ...] = (
    "limited to",
    "block range",
    "range is too large",
    "ranges over",
    "exceeds",
    "too large",
    "too many",
    "archive",
    # publicnode's archive gate, measured 2026-07-27 and again 2026-09-12:
    # "Archive requests require a personal token." Note ``fwa_logs`` warns the
    # other way -- a 429 body also says "request a personal token" -- which is
    # why this fragment only ever means *rotate*, never "permanent gate".
    "personal token",
    # ankr, measured 2026-07-27, after it went keyed: "You must authenticate
    # your request with an API key." ``curator_client`` had dropped this one
    # with no note while restating the rest of the table.
    "api key",
    "unauthorized",
    "authenticate",
    "free plan",
    "upgrade",
    "not supported",
    "unsupported",
    "capacity",
    "rate limit",
    "timeout",
    "try again",
    "cannot fulfill",
    # drpc, observed live: "Can't route your request. Try again later."
    # It arrives with -32602, which other providers spend on a genuinely
    # malformed request, so a code-first classifier bins a healthy query.
    "can't route",
    "cannot route",
    "route your request",
)

#: JSON-RPC error-message fragments that mean "this endpoint won't serve this",
#: not "this request is malformed". Matched on the message, never the code:
#: providers reuse codes freely, so classifying on the code turns a per-host
#: capability limit into a terminal failure and the fallback chain is skipped.
#:
#: **Base**, and deliberately not merged with the Ethereum table above: these
#: are the phrasings the Base pool (``base.llamarpc.com``,
#: ``base-rpc.publicnode.com``, ``base.drpc.org``) actually uses. Eleven of
#: them appear in no Ethereum client, and two of those would change an
#: Ethereum client's behaviour if they did: ``method not found`` is terminal
#: for ttt (a missing method is the request's problem, not the host's) and
#: ``query returned more than`` is a *shrink* signal for curator.
BASE_ENDPOINT_LIMITATION_FRAGMENTS: tuple[str, ...] = (
    "rate limit",
    "ratelimit",
    "too many requests",
    "exceeded",
    "quota",
    "capacity",
    "throttl",
    "block range",
    "query returned more than",
    "method not found",
    "method not supported",
    "unsupported method",
    "not available",
    "unauthorized",
    "forbidden",
)

#: JSON-RPC codes whose *conventional* meaning is "the caller's request is
#: malformed". Only consulted once the message has been cleared of endpoint
#: limitation language above.
MALFORMED_REQUEST_CODES: frozenset[int] = frozenset(
    {-32600, -32601, -32602, -32604, -32700}
)


# ---------------------------------------------------------------------------
# 2. "Your window is too wide" -- the shrinkable class, in two units
# ---------------------------------------------------------------------------

#: The **block-span** half of the shrinkable class: the provider is complaining
#: about how many *blocks* the call asked for.
RANGE_CAP_FRAGMENTS: tuple[str, ...] = (
    "limited to",
    "block range",
    "range is too large",
    "ranges over",
    # mevblocker, measured 2026-09-12: ``range 50400 exceeds limit of 10000``.
    # It matched NONE of the four above, and its code (-32602) is in
    # ``MALFORMED_REQUEST_CODES``, so an honest and perfectly shrinkable cap
    # was classified as a bad request and the endpoint was abandoned instead of
    # chunked. That is the mirror image of the drpc defect: there a message
    # that was NOT about the window drove a shrink, here one that WAS about it
    # drove none. Both come from a phrase list that only knows the providers it
    # has already met, which is why each entry names the provider it was
    # measured against and a new spelling gets measured, never guessed.
    "exceeds limit of",
)

#: The **result-count / response-size** half: the same hazard in a different
#: unit, recovered the same way, by halving the window.
#:
#: ``surf_client`` lists only the span family above, which is correct for its
#: subject -- a low-volume announce channel that cannot fill a result cap.
#: THE LIST's contract emits ~4.3 logs per block (5222 rows over blocks
#: 25769870..25771089, ``captures/live/20260817T000322Z_grace-late.json``), so
#: a full-history page is squarely in result-cap territory and a result cap
#: classified as merely "this endpoint can't" rotates, exhausts both log
#: endpoints, and takes the entire log tier -- leaderboard, activity, hourly
#: series, streak, closest calls -- to unavailable instead of paging down.
RESULT_CAP_FRAGMENTS: tuple[str, ...] = (
    "more than",
    "too many results",
    "max results",
    "maximum results",
    "result limit",
    "query returned",
    "response size",
)

#: The block count a range complaint names: ``"ranges over 10000 blocks"``,
#: ``"eth_getLogs is limited to 0 - 50 blocks range"``.
#:
#: Decimal digits immediately before the word *block(s)*, which is what makes
#: this safe to read while a *suggested toBlock* stays unread: a suggestion is
#: a hex block **number** (``"suggested toBlock 0xb12790"``) and matches
#: nothing here.  The distinction is the whole point -- this number is used
#: **only to decide whether the message is about our request**, never to size a
#: window, so no provider's arithmetic can steer a client's own.
_NAMED_BLOCK_LIMIT_RE = re.compile(r"(\d[\d,_]*)\s*blocks?\b")

#: The same number when a provider names it without the word *block*:
#: mevblocker's ``"range 50400 exceeds limit of 10000"``. Anchored on
#: ``limit of`` **specifically** so it reads the cap and not the span -- that
#: message carries both numbers, and taking the first would compare the
#: request against itself and conclude the complaint was never about it.
#: Hex block *numbers* still match nothing: a suggested ``toBlock 0xb12790``
#: has no ``limit of`` before it, and the suggestion stays unread.
_NAMED_LIMIT_OF_RE = re.compile(r"limit of\s+(\d[\d,_]*)")


def named_block_limit(message: str) -> int | None:
    """The largest block count *message* names, or ``None`` if it names none."""
    best: int | None = None
    for match in _NAMED_LIMIT_OF_RE.finditer(message):
        try:
            value = int(match.group(1).replace(",", "").replace("_", ""))
        except ValueError:  # pragma: no cover -- the pattern is digits only
            continue
        if best is None or value > best:
            best = value
    for match in _NAMED_BLOCK_LIMIT_RE.finditer(message):
        try:
            value = int(match.group(1).replace(",", "").replace("_", ""))
        except ValueError:  # pragma: no cover -- the pattern is digits only
            continue
        if best is None or value > best:
            best = value
    return best


def requested_block_span(method: str, params: Any) -> int | None:
    """How many blocks the ``eth_getLogs`` request *method*/*params* asked for.

    ``None`` for any other method, for a filter without both bounds, and for a
    named tag (``"latest"``, ``"earliest"``): those requests have no span for a
    provider's message to be about. The number is read from the request that
    produced the error -- the only request a provider's complaint is evidence
    about -- so a classifier can pass it as *requested_span* without its
    caller threading it through every transport layer.
    """
    if method != "eth_getLogs" or not isinstance(params, (list, tuple)) or not params:
        return None
    filt = params[0]
    if not isinstance(filt, dict):
        return None
    try:
        lo = int(str(filt["fromBlock"]), 16)
        hi = int(str(filt["toBlock"]), 16)
    except (KeyError, TypeError, ValueError):
        return None
    return hi - lo + 1 if hi >= lo else None


# ---------------------------------------------------------------------------
# 3. The two predicates
# ---------------------------------------------------------------------------


def looks_like_endpoint_limitation(
    err: Any,
    *,
    fragments: tuple[str, ...],
    unstructured_is_limitation: bool = True,
    check_codes: bool = True,
) -> bool:
    """True if *err* reads as "this endpoint can't", not "this request is bad".

    The message is read **first** and the code only as a fallback, and both
    live probes in ``tests/fixtures/surf/pool4/rpc_error_states.json`` are why:
    ``-32602`` carries "eth_getLogs is limited to 0 - 50 blocks range" on 1rpc
    and "Invalid params" on publicnode.  Code-first classification would treat
    the recoverable one as our own bug and stop rotating.

    The Ethereum callers err toward ``True`` on purpose: falling over to the
    next endpoint after a genuine caller bug costs a few wasted requests and
    reaches the same final failure, whereas treating a capability limit as
    terminal takes the whole dashboard offline while healthy endpoints sit
    unused.

    Two flags keep cattown's Base policy intact rather than quietly adopting
    the Ethereum one (survey flips R1 and R7):

    *unstructured_is_limitation* is what a non-``dict`` *err* means.  ``True``
    for the four Ethereum clients; ``False`` for cattown, whose caller then
    raises -- a body that is not a JSON-RPC error object is not evidence that
    the *host* is at fault, and rotating on it would triple the request count.

    *check_codes* enables the :data:`MALFORMED_REQUEST_CODES` fallback.
    cattown has never had one: on Base a reverted ``eth_call`` is the
    *contract's* answer, and its message-only table is what makes
    ``test_contract_revert_does_not_rotate`` true.
    """
    if not isinstance(err, dict):
        return unstructured_is_limitation
    message = str(err.get("message") or "").lower()
    if any(frag in message for frag in fragments):
        return True
    if not check_codes:
        return False
    return err.get("code") not in MALFORMED_REQUEST_CODES


def is_range_limitation(
    err: Any,
    *,
    fragments: tuple[str, ...],
    requested_span: int | None = None,
) -> bool:
    """True only for "you asked for too much in one call" -- the shrinkable class.

    *requested_span* is how many blocks the request that produced *err*
    actually asked for.  Pass it, and the classification gains the second half
    of CLAUDE.md's error rule: **classifying on message text is right, but a
    message that no longer describes the request must not drive the retry.**

    ``eth.drpc.org``, measured on 2026-09-12, answers *every* archive
    ``eth_getLogs`` -- a 300-block window included -- with ``code 35 "ranges
    over 10000 blocks are not supported on free plan"``.  Its free plan now
    serves roughly sixty-four blocks and blames the refusal on a range it is
    not reading; the real limit is archive depth, not width.  A client that
    takes that at face value halves 2400 -> 1200 -> 600 -> 300, reports
    "window 300 is already minimal: ranges over 10000 blocks", and returns
    ``None`` -- which is exactly how the STAKERS panel went dark while the data
    sat one endpoint away.

    So: a range complaint that names a limit the request **already satisfies**
    is not about the window.  Halving it is provably useless, and this returns
    ``False`` so the caller rotates to the next endpoint instead.  A complaint
    that names no limit at all, or names one the request genuinely exceeds,
    stays shrinkable -- the conservative direction, and the behaviour that was
    already here.

    That guard reads a **block** count, so it applies only when the message
    matched a fragment from :data:`RANGE_CAP_FRAGMENTS`.  A caller that also
    passes :data:`RESULT_CAP_FRAGMENTS` is asking about a second unit --
    *results* -- and the numbers in those messages are row counts, not spans:
    "result limit of 10000 reached" names ten thousand rows, and comparing a
    2000-block page against it would conclude the complaint was never about the
    request and refuse the one shrink that fixes it.  A result cap therefore
    stays shrinkable whatever the span.  (For ``surf_client`` and
    ``surf_pool4_client``, whose *fragments* are the span family exactly, this
    is the same predicate they already had, statement for statement.)
    """
    if not isinstance(err, dict):
        return False
    message = str(err.get("message") or "").lower()
    if not any(frag in message for frag in fragments):
        return False
    if requested_span is None:
        return True
    if not any(frag in message for frag in RANGE_CAP_FRAGMENTS):
        return True  # a result-count cap: its number is rows, not blocks
    named = named_block_limit(message)
    if named is None:
        return True
    return requested_span > named
