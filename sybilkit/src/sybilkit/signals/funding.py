"""The ``funding`` family: the first-funder graph, folded onto the clusters.

The measured hierarchy (research §5.1):

* **funder ∈ same cluster** — the peel chain, 10/10 on fully-resolved farm
  samples against 0/47 controls.  The strongest discriminator this library
  has.
* **funder is any contributor** — NOISY: 35 of 47 resolved controls fund
  from their own main wallet, which is a contributor, and which is normal.
* **shared CEX / infra funder** — the recurring false-positive class
  (research §7): excluded outright via :func:`sybilkit.labels.is_infra_funder`.

**The fold** is the difference between the first two: an edge exists only
when funder and funded already share a behavioural (tier-A) component — the
funding family corroborates a cluster, it never *builds* one out of a
family's shared main wallet or an exchange's Tuesday.  This fold is the
mandated mutation bite of WP1.4: firing on any contributor funder reddens
``test_a_main_wallet_funder_outside_the_component_is_not_evidence``.

``funder is None`` (tier C not run, or the lookup bounded out) produces no
edge — never a false one.  Neither does ``funder == address``: a wallet is
not its own first funder, so such a row is edited rather than measured, and a
persisted payload is third-party input.  The union of an address with itself
is a no-op, but the *family* it would book is not — a one-family component
that gains ``funding`` clears the ≥2-family gate on one edited line.  The
comparison lowercases both sides, so the guard holds for a hand-built
:class:`sybilkit.model.Funding` that never passed the mapping coercers.
"""

from __future__ import annotations

from collections import defaultdict

from ..cluster import Edge
from ..labels import is_infra_funder
from ..model import Dataset
from ..report import Reason
from . import tier_a_components

STRENGTH_CHAIN = 0.95
STRENGTH_SHARED = 0.75


def funding_edges(ds: Dataset, cfg, *, groups=None) -> list[Edge]:
    """Peel-chain and shared-funder edges, folded onto *groups* (default: the
    tier-A components)."""
    if not ds.funding:
        return []  # tier C not run: silent, never synthetic
    if groups is None:
        groups = tier_a_components(ds, cfg)
    component_of: dict[str, int] = {}
    for i, group in enumerate(groups):
        for member in group:
            component_of[member] = i

    edges: list[Edge] = []

    # ---- the peel chain: funder is a member of the same cluster ---------
    chain_reason = Reason(
        "funding",
        "first funder is a member of the same cluster (peel chain)",
        STRENGTH_CHAIN,
    )
    for addr, entry in sorted(ds.funding.items()):
        funder = entry.funder
        if (
            funder is None
            or funder.lower() == addr.lower()
            or is_infra_funder(funder)
        ):
            continue
        comp = component_of.get(addr)
        if comp is not None and comp == component_of.get(funder):
            edges.append(Edge(addr, funder, "funding", STRENGTH_CHAIN, chain_reason))

    # ---- the hub: one non-infra funder, many members of one cluster -----
    by_funder: dict[str, list[str]] = defaultdict(list)
    for addr, entry in ds.funding.items():
        if (
            entry.funder is not None
            and entry.funder.lower() != addr.lower()
            and not is_infra_funder(entry.funder)
        ):
            by_funder[entry.funder].append(addr)
    for funder, funded in sorted(by_funder.items()):
        if len(funded) < 2:
            continue
        by_comp: dict[int, list[str]] = defaultdict(list)
        for addr in funded:
            comp = component_of.get(addr)
            if comp is not None:
                by_comp[comp].append(addr)
        for comp, members in sorted(by_comp.items()):
            if len(members) < 2:
                continue
            reason = Reason(
                "funding",
                f"shared first funder {funder[:10]}… ×{len(members)} inside one cluster",
                STRENGTH_SHARED,
            )
            members.sort()
            for a, b in zip(members, members[1:]):
                edges.append(Edge(a, b, "funding", STRENGTH_SHARED, reason))
    return edges


__all__ = ["funding_edges"]
