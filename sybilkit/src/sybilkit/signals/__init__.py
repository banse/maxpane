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

**The shared folds travel by keyword.**  One ``detect`` run used to derive the
first-deposit map seven times over, so every consumer of a fold takes it as a
keyword-only argument defaulting to ``None`` — ``firsts=`` for the first-row
map, ``singles=`` for the single-deposit slice.  Two rules make that safe to
rely on and both are pinned in ``tests/test_public_api.py``:

* the parameters are **additive and keyword-only**, because maxpane's adapter
  imports :func:`first_rows` and :func:`tier_a_components` across a
  distribution boundary this suite cannot see; and
* being handed a fold answers **exactly** what deriving it answers, so passing
  one is an optimisation and never a second opinion.  Hand in a map that is not
  the one :func:`first_rows` would derive and you are asking a different
  question — that is the caller's business, and the library does not check it.
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


def single_first_rows(ds: Dataset, *, firsts=None) -> dict[str, Deposit]:
    """First deposits of wallets that deposited exactly once.

    *firsts* is the :func:`first_rows` map when the caller already holds one;
    ``None`` derives it.  The counts are still walked here — they are a
    different fold over the same deposits, and cheap.
    """
    counts = deposit_counts(ds)
    if firsts is None:
        firsts = first_rows(ds)
    return {c: d for c, d in firsts.items() if counts[c] == 1}


def tol_bps_of(near_amount_tol: float) -> int:
    """The config's float tolerance as integer basis points, once."""
    return round(near_amount_tol * 10_000)


#: A "round" amount is a whole multiple of 0.01 ETH — a value a human picks.
ROUND_WEI = 10**16

#: Round-amount groups split where the gap between neighbouring deposit hours
#: exceeds this — one wave, one window.
MAX_HOUR_GAP = 1


def identical_amount_windows(
    ds: Dataset, cfg, *, singles=None
) -> list[tuple[int, list[tuple[int, int, str]]]]:
    """Byte-identical single-deposit groups under the ONE window discipline.

    Both amount-family signals (``amounts`` exact groups and ``split``) walk
    these, so neither can weld a crowd the other would have split
    (review I4 / ruling R13a):

    * an **odd** amount (``% ROUND_WEI != 0``) is one global group — the
      machine fingerprint reaches across waves;
    * a **round** amount splits into contiguous-hour wave windows
      (hour gap > :data:`MAX_HOUR_GAP` starts a new one);
    * the **protocol minimum** (``cfg.protocol_min_amount_wei``, when set)
      yields no group at all — everyone sends the minimum, so identicalness
      at the minimum identifies nobody (ruling R13b).

    Yields ``(amount_wei, window)`` with each window a sorted list of
    ``(hour, block_number, address)`` and ``len(window) >= 2``.

    *singles* is the :func:`single_first_rows` slice when the caller already
    holds one; ``None`` derives it.  Both amount-family signals walk these
    windows, so ``detect`` computes the pass once and hands the **same list
    objects** to each — nothing here or downstream mutates a window.
    """
    if singles is None:
        singles = single_first_rows(ds)
    by_amount: dict[int, list[tuple[int, int, str]]] = {}
    for addr, dep in singles.items():
        by_amount.setdefault(dep.amount_wei, []).append(
            (dep.hour, dep.block_number, addr)
        )
    windows: list[tuple[int, list[tuple[int, int, str]]]] = []
    exempt = cfg.protocol_min_amount_wei
    for amount, rows in sorted(by_amount.items()):
        if len(rows) < 2 or (exempt is not None and amount == exempt):
            continue
        rows.sort()
        if amount % ROUND_WEI:
            windows.append((amount, rows))
            continue
        window = [rows[0]]
        for row in rows[1:]:
            if row[0] - window[-1][0] > MAX_HOUR_GAP:
                if len(window) >= 2:
                    windows.append((amount, window))
                window = [row]
            else:
                window.append(row)
        if len(window) >= 2:
            windows.append((amount, window))
    return windows


def near(a: int, b: int, tol_bps: int) -> bool:
    """±tol comparison computed in integers — no float touches a wei value."""
    return abs(a - b) * 10_000 <= tol_bps * max(a, b)


def tier_a_components(ds: Dataset, cfg, *, firsts=None) -> list[set[str]]:
    """The behavioural pre-components: union-find over every tier-A edge
    (amount, split, sequence, cadence).

    This is what "funder ∈ same cluster" and "the component collapses to one
    fingerprint" are measured against.  ``gas`` and ``funding`` call it when
    the combiner has not handed them its own components; the corroborating
    families can therefore never *merge* groups — they only strengthen what
    the tier-A families already drew.

    Imported lazily to keep this package's import graph acyclic (the signal
    modules import their shared helpers from here).

    *firsts* is the :func:`first_rows` map when the caller already holds one;
    ``None`` derives it.
    """
    from .amounts import amount_edges
    from .cadence import cadence_edges
    from .sequence import sequence_edges
    from .split import split_edges

    if firsts is None:
        firsts = first_rows(ds)

    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    for edges in (
        amount_edges(ds, cfg, firsts=firsts),
        split_edges(ds, cfg, firsts=firsts),
        sequence_edges(ds, cfg, firsts=firsts),
        cadence_edges(ds, cfg, firsts=firsts),
    ):
        for e in edges:
            ra, rb = find(e.a), find(e.b)
            if ra != rb:
                parent[rb] = ra
    components: dict[str, set[str]] = {}
    for node in list(parent):
        components.setdefault(find(node), set()).add(node)
    return list(components.values())


def eth_str(amount_wei: int) -> str:
    """A wei amount as a short ETH string for pattern-language reasons.

    Presentation only — nothing computes with this; trailing zeros trimmed,
    at least one decimal kept (``0.45``, ``14.0``, ``2.067``).
    """
    whole, frac = divmod(amount_wei, 10**18)
    text = f"{whole}.{frac:018d}".rstrip("0")
    return text + "0" if text.endswith(".") else text
