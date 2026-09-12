"""Hand-audited operator windows, and the evaluator that proves they say what they mean.

These windows were built as **recall proxies** — "of this known farm, what share
did the detector flag?" — and that is still their primary job. They are published
as data because a named accusation a reader cannot recompute is not evidence, it
is an assertion.

Each window is a mechanical predicate over a wallet's own deposits, first funder
and join index. What is *not* mechanical is the choice of which patterns to name:
a person dissecting the settled population saw them and wrote them down. Nobody
can derive that list from first principles, and it cannot be priced on the null
model. Any use of these windows beyond measurement inherits that limit.

:func:`evaluate` re-derives every window from :data:`PREDICATES` alone, and
:func:`verify` checks that result against the rule set's own output. That check
exists because the first published copy of this table got one window wrong: the
ring's predicate read as two conditions on possibly different deposits, when the
rule is a single deposit satisfying both, and a reader following it recovered 390
of 419 wallets. A predicate nothing re-derives is documentation, not a check.
"""

from __future__ import annotations

import collections
from collections.abc import Mapping
from decimal import Decimal

ETH = 10**18

#: `deposit_eth` + `deposit_hour` describe ONE deposit meeting both conditions.
#: `first_hour`, `first_index`, `first_funder` and `first_amount_eth` describe the
#: wallet's first deposit. `deposits` and `amounts_eth` describe the whole set.
PREDICATES: dict[str, dict] = {
    "0.45@h3-4": {"deposits": 1, "amount_eth": "0.45", "first_hour": [3, 4]},
    "14.0@h3-15": {"deposits": 1, "amount_eth": "14.0", "first_hour": [3, 15]},
    "10.0@h5": {"deposits": 1, "amount_eth": "10.0", "first_hour": [5, 5]},
    "1.2@h1-2": {"deposits": 1, "amount_eth": "1.2", "first_hour": [1, 2]},
    "2.067": {"deposits": 1, "amount_eth": "2.067", "first_hour": [0, 66]},
    "0.45@h34-37": {"deposits": 1, "amount_eth": "0.45", "first_hour": [34, 37]},
    "ring99(any dep 90-110Ξ h16-19)": {
        "deposit_eth": [90, 110],
        "deposit_hour": [16, 19],
        "note": "the ≈99 ETH serial peel chain; one deposit meets both conditions",
    },
    "ladder10.x(5-step h37-45)": {
        "deposits": 5,
        "min_deposit_eth": ["9.9", "10.0"],
        "max_deposit_eth": ["10.3", "10.4"],
    },
    "bitget-ladder(1.19-1.69 h17-31)": {
        "first_funder": "0x1ab4973a48dc892cd9971ece8e01dcc7688f8f23",
        "first_hour": [17, 31],
        "first_amount_eth": [1.1, 1.8],
    },
    "0.05 recyclers(3 small hubs)": {
        "first_funder_in": [
            "0x3230466e58bb1019f5695ff55248ece1e753eb79",
            "0x2fc92dde494064724fd371e55172877f86d842e9",
            "0x2e0db3f849b19b8d23993c4434ed02bf930d94f2",
        ]
    },
    "jitter1.10-1.14(h36-55)": {
        "deposits": 1, "amount_eth": [1.10, 1.14], "min_decimals": 6, "first_hour": [36, 55],
    },
    "jitter1.00-1.05(h56-64)": {
        "deposits": 1, "amount_eth": [1.00, 1.05], "min_decimals": 6, "first_hour": [56, 64],
    },
    "ladder0.05→0.45(h35-37)": {
        "deposits": 5,
        "amounts_eth": ["0.05", "0.15", "0.25", "0.35", "0.45"],
        "first_hour": [35, 37],
    },
    **{
        f"idxrun_{start}": {"first_index": [start, start + 99]}
        for start in (12058, 13326, 13795, 13897, 14001)
    },
}


def _wei(value) -> int:
    return int(Decimal(str(value)) * ETH)


def _decimals(amount_wei: int) -> int:
    return len(f"{amount_wei % ETH:018d}".rstrip("0"))


def _rows(dataset) -> dict[str, list]:
    by: dict[str, list] = collections.defaultdict(list)
    for d in dataset.deposits:
        by[d.contributor.lower()].append(d)
    for rows in by.values():
        rows.sort(key=lambda d: (d.block_number, d.log_index))
    return by


def _matches(rows, funder, index, p: Mapping) -> bool:
    amounts = sorted(d.amount_wei for d in rows)
    first = rows[0]
    if "deposits" in p and len(rows) != p["deposits"]:
        return False
    if "first_hour" in p and not p["first_hour"][0] <= first.hour <= p["first_hour"][1]:
        return False
    if "first_index" in p and not (
        index is not None and p["first_index"][0] <= index <= p["first_index"][1]
    ):
        return False
    if "deposit_eth" in p or "deposit_hour" in p:
        lo, hi = p.get("deposit_eth", [0, 10**9])
        h0, h1 = p.get("deposit_hour", [0, 10**9])
        if not any(_wei(lo) <= d.amount_wei <= _wei(hi) and h0 <= d.hour <= h1 for d in rows):
            return False
    if "amounts_eth" in p and amounts != [_wei(x) for x in p["amounts_eth"]]:
        return False
    if "min_deposit_eth" in p and amounts[0] not in [_wei(x) for x in p["min_deposit_eth"]]:
        return False
    if "max_deposit_eth" in p and amounts[-1] not in [_wei(x) for x in p["max_deposit_eth"]]:
        return False
    if "first_funder" in p and funder != p["first_funder"]:
        return False
    if "first_funder_in" in p and funder not in p["first_funder_in"]:
        return False
    if "first_amount_eth" in p:
        lo, hi = p["first_amount_eth"]
        if not _wei(lo) <= first.amount_wei <= _wei(hi):
            return False
    if "min_decimals" in p and _decimals(first.amount_wei) < p["min_decimals"]:
        return False
    if "amount_eth" in p:
        want = p["amount_eth"]
        if isinstance(want, list):
            if not _wei(want[0]) <= amounts[0] <= _wei(want[1]):
                return False
        elif amounts[0] != _wei(want):
            return False
    return True


def evaluate(dataset) -> dict[str, frozenset[str]]:
    """Re-derive every window from :data:`PREDICATES` and the dataset alone."""
    rows = _rows(dataset)
    funders = {a.lower(): (f.funder or "").lower() for a, f in dataset.funding.items()}
    indexes = {a.lower(): i for a, i in dataset.first_index.items()}
    out = {}
    for name, predicate in PREDICATES.items():
        out[name] = frozenset(
            address
            for address, deposits in rows.items()
            if _matches(deposits, funders.get(address), indexes.get(address), predicate)
        )
    return out


def verify(windows: Mapping[str, frozenset[str]], dataset) -> None:
    """Fail unless every published predicate re-derives its own membership.

    Truthfulness only. Whether a window is *fit to publish* — an empty one names
    an accusation with nobody in it — is :func:`require_non_empty`, because a
    predicate that correctly yields nothing on some dataset is honest, just not
    worth shipping.
    """
    missing = sorted(set(windows) - set(PREDICATES))
    if missing:
        raise ValueError(f"windows with no published predicate: {missing}")
    stale = sorted(set(PREDICATES) - set(windows))
    if stale:
        raise ValueError(f"predicates for windows the rules no longer build: {stale}")
    derived = evaluate(dataset)
    for name, members in windows.items():
        mine = derived[name]
        published = frozenset(a.lower() for a in members)
        if mine != published:
            raise ValueError(
                f"predicate for {name!r} does not re-derive its membership: "
                f"published {len(published)}, predicate yields {len(mine)} "
                f"(+{len(mine - published)}/-{len(published - mine)})"
            )


def require_non_empty(windows: Mapping[str, frozenset[str]]) -> None:
    """Refuse to publish a window with no members."""
    empty = sorted(name for name, group in windows.items() if not group)
    if empty:
        raise ValueError(f"empty windows (a published accusation must have members): {empty}")


def members(windows: Mapping[str, frozenset[str]]) -> frozenset[str]:
    """The distinct wallets across every window, lower-cased."""
    out: set[str] = set()
    for group in windows.values():
        out.update(a.lower() for a in group)
    return frozenset(out)
