"""The hand-audited operator windows, as data a caller can check.

These windows are the second arm of the ``E3`` eligibility policy in
:mod:`sybilkit.eligibility`: a wallet is a *clear* sybil if it carries three or
more evidence families **or** it sits in one of these hand-verified patterns.
The first arm is already in every published analysis payload
(``wallets[].member_families``); this module supplies the second, and nothing
else does.

Membership is a property of a wallet's own deposits and first funder, so one
derivation serves every analysis version — including a retuned rule set. That is
why it is exported as its own artifact rather than as a field on a version:
a version is immutable and content-addressed, and this is not part of it.

:data:`PREDICATES` restates each window's rule in data. ``sk_v2`` remains the
definition of record — :func:`verify` is what catches a drift between the two,
and it fails loudly rather than exporting an unexplained list of addresses.
"""

from __future__ import annotations

from collections.abc import Mapping

from .sk_v2 import build_extra

PREDICATES = {
    "0.45@h3-4": {"deposits": 1, "amount_eth": "0.45", "first_hour": [3, 4]},
    "14.0@h3-15": {"deposits": 1, "amount_eth": "14.0", "first_hour": [3, 15]},
    "10.0@h5": {"deposits": 1, "amount_eth": "10.0", "first_hour": [5, 5]},
    "1.2@h1-2": {"deposits": 1, "amount_eth": "1.2", "first_hour": [1, 2]},
    "2.067": {"deposits": 1, "amount_eth": "2.067", "first_hour": [0, 66]},
    "0.45@h34-37": {"deposits": 1, "amount_eth": "0.45", "first_hour": [34, 37]},
    "ring99(any dep 90-110Ξ h16-19)": {
        "any_deposit_eth": [90, 110], "first_hour": [16, 19],
        "note": "the ≈99 ETH serial peel chain",
    },
    "ladder10.x(5-step h37-45)": {
        "deposits": 5, "min_deposit_eth": ["9.9", "10.0"], "max_deposit_eth": ["10.3", "10.4"],
    },
    "bitget-ladder(1.19-1.69 h17-31)": {
        "first_funder": "0x1ab4973a48dc892cd9971ece8e01dcc7688f8f23",
        "first_hour": [17, 31], "first_amount_eth": [1.1, 1.8],
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
        "deposits": 5, "amounts_eth": ["0.05", "0.15", "0.25", "0.35", "0.45"],
        "first_hour": [35, 37],
    },
    **{
        f"idxrun_{start}": {"first_index": [start, start + 99]}
        for start in (12058, 13326, 13795, 13897, 14001)
    },
}


def derive(dataset) -> dict[str, frozenset[str]]:
    """Every audited window over one dataset, verified against :data:`PREDICATES`."""
    # ``hour_saved`` only feeds the rescuer metric, which windows do not use.
    windows = {
        name: frozenset(members)
        for name, members in build_extra(dataset, {"hour_saved": []})["farm_windows"].items()
    }
    verify(windows)
    return windows


def verify(windows: Mapping[str, frozenset[str]]) -> None:
    """Every window must be named in :data:`PREDICATES`, and none may be empty."""
    missing = sorted(set(windows) - set(PREDICATES))
    if missing:
        raise ValueError(f"windows with no published predicate: {missing}")
    stale = sorted(set(PREDICATES) - set(windows))
    if stale:
        raise ValueError(f"predicates for windows the rules no longer build: {stale}")
    empty = sorted(name for name, members in windows.items() if not members)
    if empty:
        raise ValueError(f"empty windows (a published accusation must have members): {empty}")


def members(windows: Mapping[str, frozenset[str]]) -> frozenset[str]:
    """The distinct wallets across every window, lower-cased."""
    out: set[str] = set()
    for group in windows.values():
        out.update(a.lower() for a in group)
    return frozenset(out)
