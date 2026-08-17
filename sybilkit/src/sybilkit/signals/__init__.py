"""The signal families — each module a pure ``(Dataset, DetectConfig) -> list[Edge]``.

Five families (:data:`sybilkit.cluster.FAMILIES`), six modules: ``amounts``
and ``split`` both speak for the ``amount`` family (a split is evidence about
an amount group, never a second family), ``sequence``/``cadence``/``gas``/
``funding`` each own the family of their name.

Shared vocabulary lives here so no detector re-derives it differently:

:func:`first_rows`
    Every contributor's first deposit, in chain order.

:func:`single_first_rows`
    The first deposits of **single-deposit** wallets only — the universe the
    amount and cadence groupers run over.  Multi-deposit wallets are humans
    laddering (0.05, 0.15, 0.25, ...) often *through* farm amounts on the way,
    and the measured false-positive controls are exactly those ladders.

:func:`near`
    The ±tol comparison, in integers end to end.  ``tol_bps`` comes off the
    config's float once, by ``round``, so ``0.10`` means exactly 1 000 bps.
"""

from __future__ import annotations

from ..model import Dataset, Deposit


def first_rows(ds: Dataset) -> dict[str, Deposit]:
    """Each contributor's first deposit by chain order ``(block, log_index)``.

    ``ds.deposits`` is already chain-ordered by ``Dataset.from_events``, but
    this helper does not rely on it — a hand-built ``Dataset`` may not be.
    """
    first: dict[str, Deposit] = {}
    for dep in ds.deposits:
        cur = first.get(dep.contributor)
        if cur is None or (dep.block_number, dep.log_index) < (
            cur.block_number,
            cur.log_index,
        ):
            first[dep.contributor] = dep
    return first


def deposit_counts(ds: Dataset) -> dict[str, int]:
    counts: dict[str, int] = {}
    for dep in ds.deposits:
        counts[dep.contributor] = counts.get(dep.contributor, 0) + 1
    return counts


def single_first_rows(ds: Dataset) -> dict[str, Deposit]:
    """First deposits of wallets that deposited exactly once."""
    counts = deposit_counts(ds)
    return {c: d for c, d in first_rows(ds).items() if counts[c] == 1}


def tol_bps_of(near_amount_tol: float) -> int:
    """The config's float tolerance as integer basis points, once."""
    return round(near_amount_tol * 10_000)


def near(a: int, b: int, tol_bps: int) -> bool:
    """±tol comparison computed in integers — no float touches a wei value."""
    return abs(a - b) * 10_000 <= tol_bps * max(a, b)


def eth_str(amount_wei: int) -> str:
    """A wei amount as a short ETH string for pattern-language reasons.

    Presentation only — nothing computes with this; trailing zeros trimmed,
    at least one decimal kept (``0.45``, ``14.0``, ``2.067``).
    """
    whole, frac = divmod(amount_wei, 10**18)
    text = f"{whole}.{frac:018d}".rstrip("0")
    return text + "0" if text.endswith(".") else text
