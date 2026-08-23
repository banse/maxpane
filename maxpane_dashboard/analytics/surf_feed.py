"""Thread the announce channel's own feed rows into display groups.

Pure. No I/O, no Textual, no ``time`` -- the channel rows already carry their
own ``ts``, so nothing here needs a clock, injected or otherwise.

Ported from ``0x/apps/web/src/model/surfThreads.ts`` (``buildSurfTimeline`` +
``buildSurfReplyRows``), the reference implementation for this exact channel
on a different project. The port keeps its one load-bearing idea --
``inboundByAuthor`` -- and drops the rest, because that other project models
a thread as an explicit tree the reader can drill into (``buildSurfConversation``,
ancestors, per-row ``hasNestedChild``) while this dashboard only ever renders
one flat list per root: newest post on top, every reply and every answer to
that reply flattened directly beneath it, oldest first. There is no second
consumer here that would need the recursive shape, so it is not built.

The rule that makes an answer a reply-to-a-reply, not a second reply
----------------------------------------------------------------------

The announce wallet answers by sending its own zero-value calldata tx back
to whoever asked (``classify_channel_tx`` in ``analytics/surf_signals.py``
calls this an ``answer``, never a ``reply`` -- see ``data/surf_models.py``'s
``CHANNEL_KINDS`` docstring for why folding it into ``action`` used to hide
the answer from the question it answered). Nothing in the payload says
*which* question an answer is for; the channel has no parent-tx field at
all. The only signal is *who it was sent to*, so :func:`build_threads`
tracks, per address, the most recent inbound ``reply`` that address sent --
``inbound_by_author`` below -- and an ``answer`` addressed to that address
nests one level under that specific reply, not under the root post. Get this
backwards (key the lookup on the answer's own ``from_addr`` instead of the
recipient's ``to_addr``) and every answer would nest under whatever the
announce wallet itself last said, which is nonsense the reference
implementation never produces either; the mutation drill in
``tests/analytics/test_surf_feed.py`` proves this the direct way, by making
that exact swap and watching the nesting test go red.

Answers are deliberately never recorded into ``inbound_by_author`` -- only
inbound replies are. Recording an answer there would let a later answer
addressed back to the announce wallet's own address parent itself under a
previous answer, which is not a rule this channel has; the announce wallet
does not reply to itself.

The channel is permissionless and attacker-writable
----------------------------------------------------

Anything can show up in these rows: a ``None``, a string where a mapping
belongs, a ``ts`` that will not coerce to a number, two items with the exact
same second. :func:`build_threads` must never raise on any of it -- a
malformed item is dropped rather than aborting the whole panel (CLAUDE.md's
"a dead source degrades to an explicit unavailable state" is about reads,
but the same instinct applies here: one bad row must not blank the feed).

``ts`` alone is not a total order (two posts can land in the same second)
and the chain's per-sender ``nonce`` is not a channel-wide one either, so
ties break on ``tx_hash`` -- an arbitrary but *stable* tiebreak, which is
the property that matters: whichever order the caller happens to hand items
in, the sort below always produces the same thread shape, so the feed does
not reshuffle itself between refreshes just because two async fetches raced
each other into a different item order.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

__all__ = ["build_threads"]


def _coerce_ts(value: Any) -> float | None:
    """``ts`` -> ``float``, or ``None`` if the channel handed us junk.

    ``bool`` is excluded even though ``isinstance(True, int)`` is true in
    Python -- a stray boolean in a hand-edited or attacker-crafted row must
    not silently become ``ts=1.0``.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _row(item: Mapping[str, Any], depth: int, parent_tx_hash: str | None) -> dict[str, Any]:
    return {"item": item, "depth": depth, "parent_tx_hash": parent_tx_hash, "replies": []}


def build_threads(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Group classified feed items into display rows, newest root first.

    Each returned dict is:
        {"item": <the feed item>, "depth": int, "parent_tx_hash": str | None,
         "replies": list[dict]}
    Roots have depth 0, ``parent_tx_hash is None``, and carry their
    descendants in ``replies``, already flattened and depth-tagged (a reply
    is depth 1, an answer to that reply depth 2). Top-level non-message rows
    (``action``, ``fund``) and unthreaded replies are returned as roots with
    an empty ``replies`` list.
    """
    coerced: list[dict[str, Any]] = []
    for raw in items or ():
        if not isinstance(raw, dict):
            continue
        ts = _coerce_ts(raw.get("ts"))
        if ts is None:
            continue
        item = dict(raw)
        item["ts"] = ts
        coerced.append(item)

    # Ascending by (ts, tx_hash): ts is not a total order on its own and the
    # tiebreak has to be something every caller agrees on, whatever order
    # they handed the items in -- see the module docstring.
    coerced.sort(key=lambda item: (item["ts"], str(item.get("tx_hash") or "")))

    roots: list[dict[str, Any]] = []
    active_root: dict[str, Any] | None = None
    inbound_by_author: dict[str, dict[str, Any]] = {}

    for item in coerced:
        kind = item.get("kind")
        from_addr = str(item.get("from_addr") or "").lower()
        to_addr = str(item.get("to_addr") or "").lower()

        if kind == "self":
            row = _row(item, 0, None)
            roots.append(row)
            active_root = row
            continue

        if kind == "reply":
            if active_root is None:
                # A reply that predates the first "self" post the manager
                # handed us -- the channel is permissionless, so this
                # happens. Dropping it would be silent data loss; it stays
                # visible as its own top-level row instead.
                row = _row(item, 0, None)
                roots.append(row)
            else:
                row = _row(item, 1, str(active_root["item"].get("tx_hash") or ""))
                active_root["replies"].append(row)
            if from_addr:
                inbound_by_author[from_addr] = row
            continue

        if kind == "answer":
            # There is no active thread to flatten this into at all -- emit
            # it as its own root regardless of whether an inbound reply was
            # found, the same "no active_root either" fallback the brief
            # gives the not-found case, extended to cover this one: without
            # an open thread there is nowhere for a depth>0 row to live.
            if active_root is None:
                roots.append(_row(item, 0, None))
                continue
            parent = inbound_by_author.get(to_addr) if to_addr else None
            if parent is not None:
                row = _row(item, 2, str(parent["item"].get("tx_hash") or ""))
            else:
                row = _row(item, 1, str(active_root["item"].get("tx_hash") or ""))
            active_root["replies"].append(row)
            # Answers are never recorded into inbound_by_author -- see the
            # module docstring for why (the announce wallet must not end up
            # answering itself).
            continue

        # "action" / "fund" / anything a future classifier adds: never
        # threaded, always its own root.
        roots.append(_row(item, 0, None))

    roots.reverse()
    return roots
