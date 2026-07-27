"""Expected value calculations for boosts and attacks.

The numbers used here are **game parameters that the game itself publishes**
(``/agent.json`` -> ``liveState.activeBoostCatalog``).  They change between
seasons: costs, success chances, durations and even the set of items are all
re-tuned, and items are added and removed.  Ranking must therefore be driven by
the live catalog; the hardcoded :data:`BOOST_CATALOG` below is a *fallback of
last resort* for when the live fetch fails, and a catalog built from it is
tagged :data:`CATALOG_SOURCE_FALLBACK` so the UI can say so out loud rather
than presenting season-old numbers as current.

Contrast, measured 2026-07-04 (hardcoded vs live): Ad Campaign 60% / 120
cookies / 14400s vs 85% / 2800 cookies / 1500s -- cost off by ~23x, duration by
~10x -- plus two hardcoded items that no longer exist and live items the table
had never heard of.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

CATALOG_SOURCE_LIVE = "live"
"""Catalog was built from the game's published live parameters."""

CATALOG_SOURCE_FALLBACK = "fallback"
"""Catalog came from the hardcoded table -- values may be season-old."""

# Types this module knows how to score.  The live catalog also carries
# ``randomEvent`` entries (Rush Order, Golden Batch, Oven Frenzy): those are
# not player-purchasable actions, so they are excluded from the rankings --
# but recorded in ``EVCatalog.skipped`` rather than silently dropped.
RANKABLE_TYPES = frozenset({"boost", "attack"})

# (id, name, type, success_rate, cookie_cost, multiplier_bps, duration_seconds)
# multiplier_bps: 10000 = 1.0x (no change), 12500 = 1.25x, 20000 = 2.0x
# For attacks, multiplier_bps represents the penalty (2500 = 25% reduction, 10000 = 100%)
# cookie_cost is in display units
#
# STALE BY CONSTRUCTION -- fallback only.  Do not use for ranking when a live
# catalog is available; see module docstring.
BOOST_CATALOG: list[tuple[int, str, str, float, int, int, int]] = [
    (1, "Ad Campaign", "boost", 0.60, 120, 12500, 14400),
    (2, "Motivational Speech", "boost", 0.40, 80, 12500, 14400),
    (3, "Secret Recipe", "boost", 0.35, 250, 15000, 28800),
    (4, "Chef's Help", "boost", 0.50, 450, 20000, 28800),
    (5, "Recipe Sabotage", "attack", 0.60, 120, 2500, 14400),
    (6, "Fake Partnership", "attack", 0.35, 60, 2500, 14400),
    (7, "Kitchen Fire", "attack", 0.20, 320, 10000, 7200),
    (8, "Supplier Strike", "attack", 0.30, 220, 5000, 14400),
]


@dataclass(frozen=True)
class CatalogEntry:
    """One rankable boost or attack, normalised from whatever source."""

    id: str
    name: str
    type: str
    """Either ``'boost'`` or ``'attack'``."""
    success_rate: float
    """Probability of success, 0.0-1.0."""
    cookie_cost: float
    """Display-unit cookie cost."""
    multiplier_bps: int
    """Effect strength in basis points (boost: production multiplier;
    attack: production penalty)."""
    duration_seconds: int


@dataclass(frozen=True)
class EVCatalog:
    """A set of rankable entries plus provenance.

    ``source`` is the whole point of this type: a catalog that fell back to the
    hardcoded table must be distinguishable downstream so the dashboard can
    label it, instead of stale numbers masquerading as live ones.
    """

    entries: tuple[CatalogEntry, ...]
    source: str
    skipped: tuple[tuple[str, str], ...] = field(default=())
    """``(name, reason)`` for every live item that could not be ranked."""

    @property
    def is_live(self) -> bool:
        return self.source == CATALOG_SOURCE_LIVE

    def get(self, entry_id: str | int) -> CatalogEntry:
        """Look up an entry by ID. Raises ``KeyError`` if not found."""
        key = str(entry_id)
        for entry in self.entries:
            if entry.id == key:
                return entry
        raise KeyError(f"Unknown boost/attack ID: {entry_id}")

    def of_type(self, entry_type: str) -> tuple[CatalogEntry, ...]:
        return tuple(e for e in self.entries if e.type == entry_type)


FALLBACK_CATALOG = EVCatalog(
    entries=tuple(
        CatalogEntry(
            id=str(entry_id),
            name=name,
            type=entry_type,
            success_rate=success_rate,
            cookie_cost=float(cookie_cost),
            multiplier_bps=multiplier_bps,
            duration_seconds=duration_seconds,
        )
        for (
            entry_id,
            name,
            entry_type,
            success_rate,
            cookie_cost,
            multiplier_bps,
            duration_seconds,
        ) in BOOST_CATALOG
    ),
    source=CATALOG_SOURCE_FALLBACK,
)


# ---------------------------------------------------------------------------
# Catalog construction
# ---------------------------------------------------------------------------


def build_live_catalog(items: Iterable[Any] | None) -> EVCatalog:
    """Normalise ``liveState.activeBoostCatalog`` items into an ``EVCatalog``.

    Accepts anything with the :class:`~maxpane_dashboard.data.models.BoostCatalogItem`
    attribute names.  Items the ranking cannot score -- unknown ``type``,
    inactive, not player-purchasable, unparsable numbers -- are excluded from
    ``entries`` and listed in ``skipped`` with a reason.  Never raises: a
    catalog full of surprises degrades to a shorter list, not a crash.
    """
    entries: list[CatalogEntry] = []
    skipped: list[tuple[str, str]] = []

    for item in items or ():
        name = str(getattr(item, "name", None) or "<unnamed>")
        try:
            entry_type = str(getattr(item, "type", "") or "")
            if not getattr(item, "active", True):
                skipped.append((name, "inactive"))
                continue
            if not getattr(item, "player_purchasable", True):
                skipped.append((name, "not player-purchasable"))
                continue
            if entry_type not in RANKABLE_TYPES:
                skipped.append((name, f"unsupported type {entry_type!r}"))
                continue
            entry = CatalogEntry(
                id=str(getattr(item, "id", name)),
                name=name,
                type=entry_type,
                success_rate=int(item.success_chance_bps) / 10000.0,
                cookie_cost=float(item.cost),
                multiplier_bps=int(item.multiplier_bps),
                duration_seconds=int(item.duration_seconds),
            )
        except (AttributeError, TypeError, ValueError) as exc:
            skipped.append((name, f"unparsable ({exc})"))
            continue
        entries.append(entry)

    if skipped:
        logger.debug(
            "live boost catalog: %d rankable, %d skipped (%s)",
            len(entries),
            len(skipped),
            ", ".join(f"{n}: {r}" for n, r in skipped),
        )

    return EVCatalog(
        entries=tuple(entries),
        source=CATALOG_SOURCE_LIVE,
        skipped=tuple(skipped),
    )


def resolve_catalog(items: Iterable[Any] | None) -> EVCatalog:
    """Return the live catalog, or the hardcoded fallback if it is unusable.

    The returned catalog's ``source`` tells the caller which happened; callers
    are expected to surface that, because the fallback's numbers are known to
    be season-old.
    """
    catalog = build_live_catalog(items)
    if not catalog.entries:
        logger.warning(
            "Live boost catalog unavailable or unusable (%d item(s) skipped); "
            "falling back to the hardcoded table -- EV numbers may be stale.",
            len(catalog.skipped),
        )
        return FALLBACK_CATALOG
    return catalog


def _production_delta(entry: CatalogEntry) -> float:
    """Fractional production change a boost grants, e.g. 1.25x -> 0.25.

    ``multiplier_bps == 0`` marks an item with no production multiplier at all
    (the live *Cleanup Crew* countermeasure is such an item).  Treat that as
    "no production effect" rather than -100% production.
    """
    if entry.multiplier_bps == 0:
        return 0.0
    return entry.multiplier_bps / 10000.0 - 1.0


# ---------------------------------------------------------------------------
# EV maths
# ---------------------------------------------------------------------------


def calculate_boost_ev(
    boost_id: str | int,
    bakery_production_rate: float,
    catalog: EVCatalog | None = None,
) -> float:
    """Calculate expected value of a boost in cookie units.

    EV = success_rate * production_rate * (multiplier - 1) * duration_hours - cookie_cost

    The multiplier is in basis points (10000 = 1.0x, 12500 = 1.25x, 20000 = 2.0x).
    production_rate is in cookies/hour. Returns EV in display-unit cookies.

    ``catalog`` defaults to the stale :data:`FALLBACK_CATALOG`; pass the live
    catalog from :func:`resolve_catalog` for correct numbers.
    """
    entry = (catalog or FALLBACK_CATALOG).get(boost_id)

    if entry.type != "boost":
        raise ValueError(f"ID {boost_id} is an attack, not a boost")

    duration_hours = entry.duration_seconds / 3600.0

    return (
        entry.success_rate
        * bakery_production_rate
        * _production_delta(entry)
        * duration_hours
        - entry.cookie_cost
    )


def calculate_attack_ev(
    attack_id: str | int,
    target_production_rate: float,
    catalog: EVCatalog | None = None,
) -> float:
    """Calculate gap-closure-per-cookie for an attack.

    gap_closure = success_rate * target_rate * penalty * duration_hours
    Returns gap_closure / cookie_cost (ratio, higher is better).

    The penalty is derived from multiplier_bps (2500 = 0.25, 10000 = 1.0).
    target_production_rate is in cookies/hour.

    ``catalog`` defaults to the stale :data:`FALLBACK_CATALOG`; pass the live
    catalog from :func:`resolve_catalog` for correct numbers.
    """
    entry = (catalog or FALLBACK_CATALOG).get(attack_id)

    if entry.type != "attack":
        raise ValueError(f"ID {attack_id} is a boost, not an attack")

    penalty = entry.multiplier_bps / 10000.0
    duration_hours = entry.duration_seconds / 3600.0

    gap_closure = entry.success_rate * target_production_rate * penalty * duration_hours
    if entry.cookie_cost == 0:
        return float("inf") if gap_closure > 0 else 0.0
    return gap_closure / entry.cookie_cost


# ---------------------------------------------------------------------------
# Rankings
# ---------------------------------------------------------------------------


def rank_boosts(
    bakery_production_rate: float,
    catalog: EVCatalog | None = None,
) -> list[tuple[str, float]]:
    """Return boosts ranked by EV, best first.

    Returns a list of (name, ev) tuples sorted by descending EV.
    """
    active = catalog or FALLBACK_CATALOG
    results = [
        (entry.name, calculate_boost_ev(entry.id, bakery_production_rate, active))
        for entry in active.of_type("boost")
    ]
    results.sort(key=lambda x: x[1], reverse=True)
    return results


def rank_attacks(
    target_production_rate: float,
    catalog: EVCatalog | None = None,
) -> list[tuple[str, float]]:
    """Return attacks ranked by gap-closure-per-cookie, best first.

    Returns a list of (name, ratio) tuples sorted by descending ratio.
    """
    active = catalog or FALLBACK_CATALOG
    results = [
        (entry.name, calculate_attack_ev(entry.id, target_production_rate, active))
        for entry in active.of_type("attack")
    ]
    results.sort(key=lambda x: x[1], reverse=True)
    return results
