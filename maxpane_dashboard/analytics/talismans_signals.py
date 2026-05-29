"""Signal analytics for the Talismans NFT dashboard.

Pure functions that take raw state (TalismanToken, TalismanActivityEvent,
TalismanCollectionState) and return ``TalismanSignal`` instances (or scalar
derived values).

All ``TalismanSignal`` instances expose the same four keys when serialized via
``model_dump()``: ``label``, ``value_str``, ``indicator``, ``color``.  ``color``
is always one of ``"green"``, ``"yellow"``, ``"red"``, ``"dim"``.

Pattern: ``maxpane_dashboard/analytics/ttt_signals.py``.
"""

from __future__ import annotations

from maxpane_dashboard.data.talismans_materials import essence_of, material_name
from maxpane_dashboard.data.talismans_models import (
    TalismanActivityEvent,
    TalismanSignal,
    TalismanToken,
)

# ---------------------------------------------------------------------------
# Scalar helpers
# ---------------------------------------------------------------------------

_ESSENCES = ["Lithic", "Lumic", "Mythic"]
_TIER_KEYS = ["raw", "cut", "fine", "prime", "bonded"]
_TIER_MAP = {"Raw": "raw", "Cut": "cut", "Fine": "fine", "Prime": "prime", "Bonded": "bonded"}


def total_cores(tokens: list[TalismanToken]) -> int:
    """Sum of core_count across all tokens."""
    return sum(t.core_count for t in tokens)


def mythic_count(tokens: list[TalismanToken]) -> int:
    """Count tokens whose essence == ``"Mythic"``."""
    return sum(1 for t in tokens if t.essence == "Mythic")


def mythic_scarcity_pct(mythic: int, live: int) -> float:
    """Fraction of live supply that is Mythic, expressed as a percentage.

    Returns 0.0 if ``live <= 0``.
    """
    if live <= 0:
        return 0.0
    return mythic / live * 100


# ---------------------------------------------------------------------------
# Distribution tables
# ---------------------------------------------------------------------------


def essence_tier_matrix(tokens: list[TalismanToken]) -> dict:
    """Count tokens by (essence, tier) pair.

    Returns::

        {
            "rows": [
                {"essence": str, "raw": int, "cut": int, "fine": int,
                 "prime": int, "bonded": int, "total": int},
                ...  # always Lithic, Lumic, Mythic in that order
            ],
            "totals": {"raw": int, "cut": int, "fine": int, "prime": int,
                       "bonded": int, "total": int},
        }

    Tokens with an unknown tier (e.g. ``"--"``) are counted only in
    ``"total"``, not in any tier bucket.
    """
    # Build per-essence accumulator
    rows: dict[str, dict] = {
        ess: {"essence": ess, "raw": 0, "cut": 0, "fine": 0, "prime": 0, "bonded": 0, "total": 0}
        for ess in _ESSENCES
    }

    for tok in tokens:
        ess = tok.essence
        if ess not in rows:
            # Unknown essence: skip (shouldn't happen with well-formed data)
            continue
        rows[ess]["total"] += 1
        tier_key = _TIER_MAP.get(tok.tier)
        if tier_key is not None:
            rows[ess][tier_key] += 1

    totals: dict[str, int] = {k: 0 for k in _TIER_KEYS + ["total"]}
    for row in rows.values():
        for k in _TIER_KEYS + ["total"]:
            totals[k] += row[k]

    return {
        "rows": [rows[ess] for ess in _ESSENCES],
        "totals": totals,
    }


def materials_ledger(tokens: list[TalismanToken], top_n: int = 32) -> list[dict]:
    """Group tokens by material and return a ranked ledger.

    Each entry::

        {"rank": int, "material": str, "essence": str, "tokens": int, "cores": int}

    Sorted by ``tokens`` descending; tie-break by ``cores`` descending.
    Truncated to ``top_n`` entries.
    """
    groups: dict[int, dict] = {}
    for tok in tokens:
        mid = tok.material_id
        if mid not in groups:
            groups[mid] = {
                "material": material_name(mid),
                "essence": essence_of(mid),
                "tokens": 0,
                "cores": 0,
            }
        groups[mid]["tokens"] += 1
        groups[mid]["cores"] += tok.core_count

    sorted_groups = sorted(
        groups.values(),
        key=lambda g: (g["tokens"], g["cores"]),
        reverse=True,
    )[:top_n]

    return [{"rank": i + 1, **g} for i, g in enumerate(sorted_groups)]


def top_collectors(tokens: list[TalismanToken], top_n: int = 10) -> list[dict]:
    """Group tokens by owner and return a ranked collector list.

    Each entry::

        {"rank": int, "address": str, "tokens": int, "cores": int, "mythics": int}

    Sorted by ``cores`` descending; tie-break by ``tokens`` descending.
    Truncated to ``top_n`` entries.
    """
    collectors: dict[str, dict] = {}
    for tok in tokens:
        addr = tok.owner
        if addr not in collectors:
            collectors[addr] = {"address": addr, "tokens": 0, "cores": 0, "mythics": 0}
        collectors[addr]["tokens"] += 1
        collectors[addr]["cores"] += tok.core_count
        if tok.essence == "Mythic":
            collectors[addr]["mythics"] += 1

    sorted_collectors = sorted(
        collectors.values(),
        key=lambda c: (c["cores"], c["tokens"]),
        reverse=True,
    )[:top_n]

    return [{"rank": i + 1, **c} for i, c in enumerate(sorted_collectors)]


# ---------------------------------------------------------------------------
# Activity aggregations
# ---------------------------------------------------------------------------


def count_operations(
    events: list[TalismanActivityEvent],
    window_sec: int = 86400,
    now_ts: int | None = None,
) -> int:
    """Count events within a trailing time window.

    ``now_ts`` anchors the window.  If ``None``, anchors to the maximum event
    timestamp in the list (stable whether events are fresh-from-chain or
    replayed from cache).  Returns 0 for an empty list.
    """
    if not events:
        return 0
    anchor = now_ts if now_ts is not None else max(e.timestamp for e in events)
    cutoff = anchor - window_sec
    return sum(1 for e in events if e.timestamp >= cutoff)


# ---------------------------------------------------------------------------
# Signal builders
# ---------------------------------------------------------------------------


def conservation_signal(total: int, baseline: int) -> TalismanSignal:
    """Signal for the core conservation invariant.

    * ``total == baseline`` → INTACT, green.
    * Otherwise → ``DRIFT Δ{delta:+d}``, red.
    """
    if total == baseline:
        return TalismanSignal(
            label="CONSERVATION",
            value_str="INTACT",
            indicator="●",
            color="green",
        )
    delta = total - baseline
    return TalismanSignal(
        label="CONSERVATION",
        value_str=f"DRIFT Δ{delta:+d}",
        indicator="●",
        color="red",
    )


def cutmerge_signal(bond_cleave: bool, cut_merge: bool) -> TalismanSignal:
    """Signal for whether cut/merge operations are enabled.

    * ``cut_merge`` True → LIVE, green.
    * ``cut_merge`` False → LOCKED, yellow.
    """
    if cut_merge:
        return TalismanSignal(
            label="CUT/MERGE",
            value_str="LIVE",
            indicator="●",
            color="green",
        )
    return TalismanSignal(
        label="CUT/MERGE",
        value_str="LOCKED",
        indicator="●",
        color="yellow",
    )


def forge_momentum_signal(
    token_count_history: list[tuple[float, float]],
) -> TalismanSignal:
    """Signal derived from the trend of total token count over time.

    Compares the earliest and latest token counts in the history:

    * ``< 2 points`` → STABLE, dim.
    * ``latest < earliest`` → CONSOLIDATING ▼, green (net fusion into Mythics).
    * ``latest > earliest`` → SPLITTING ▲, yellow (net splitting).
    * ``latest == earliest`` → STABLE, dim.
    """
    if len(token_count_history) < 2:
        return TalismanSignal(
            label="FORGE MOMENTUM",
            value_str="STABLE",
            indicator="●",
            color="dim",
        )
    earliest_count = token_count_history[0][1]
    latest_count = token_count_history[-1][1]

    if latest_count < earliest_count:
        value_str = "CONSOLIDATING ▼"
        color = "green"
    elif latest_count > earliest_count:
        value_str = "SPLITTING ▲"
        color = "yellow"
    else:
        value_str = "STABLE"
        color = "dim"

    return TalismanSignal(
        label="FORGE MOMENTUM",
        value_str=value_str,
        indicator="●",
        color=color,
    )


def mythic_scarcity_signal(mythic: int, live: int) -> TalismanSignal:
    """Signal for how scarce Mythic talismans are within the live supply."""
    pct = mythic_scarcity_pct(mythic, live)
    return TalismanSignal(
        label="MYTHIC SCARCITY",
        value_str=f"{mythic} — {pct:.1f}% of supply",
        indicator="●",
        color="dim",
    )
