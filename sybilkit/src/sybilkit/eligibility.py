"""Eligibility policies — which links a consumer treats as disqualifying.

Three repositories divide this work: the **contract** is the model, holding what
actually happened; **sybilkit** is the controller, deriving what that means; a
dashboard is the view. A policy is derivation, so it lives here — beside the
rules whose output it reads, not beside the page that renders it.

A policy answers a different question from the analysis. The analysis says which
wallets are *linked*. A policy says which of those links a downstream consumer
treats as disqualifying, and different consumers may reasonably differ. THE
LIST's record NFT is the first such consumer, and its specification currently
reads ``flagged -> excluded`` (policy ``E0`` here). The WhitelistCurator author
asked for something narrower — "removes **clear** sybills" — so two narrower
standards are published beside it.

Nothing here is binding: no eligibility root exists, and exactly one policy will
eventually be frozen into one. Until then all three are published so a wallet
can see its own standing under each.

The module reads only the *published payload shapes* — ``wallets[].status``,
``wallets[].member_families`` and ``clusters[].families`` — plus the standalone
audited-window artifact. It imports nothing from any dashboard, and nothing from
the rule set: any analysis that produces those shapes can be evaluated, including
a retuned one.

Policies never *add* an exclusion: a wallet the analysis did not flag is eligible
under every policy. They only narrow what being flagged costs, which is why a
wallet can be **linked but eligible**, and why status and eligibility must be
reported as two separate facts rather than collapsed into one word.
"""

from __future__ import annotations

import gzip
import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

#: Only a flagged wallet can be excluded by any policy.
EXCLUDABLE_STATUS = "flagged"


@dataclass(frozen=True, slots=True)
class Policy:
    id: str
    label: str
    rule: str
    rationale: str
    #: False only for the standard a downstream specification already names.
    proposal: bool
    #: True when the policy needs the audited-window artifact to be evaluated.
    needs_windows: bool
    predicate: Callable[[Mapping, int, frozenset], bool]

    def excludes(self, wallet: Mapping, cluster_families: int, windows: frozenset) -> bool:
        if wallet.get("status") != EXCLUDABLE_STATUS:
            return False
        return self.predicate(wallet, cluster_families, windows)


def _families(wallet: Mapping) -> int:
    return len(wallet.get("member_families") or ())


POLICIES: tuple[Policy, ...] = (
    Policy(
        id="E0",
        label="Every linked wallet",
        rule="Excluded when the analysis flags the wallet.",
        rationale=(
            "The standard LIST-RECORD-1 §5.1 names today: clean and review are eligible, "
            "flagged is excluded."
        ),
        proposal=False,
        needs_windows=False,
        predicate=lambda wallet, cluster_families, windows: True,
    ),
    Policy(
        id="E3",
        label="Three families or an audited pattern",
        rule=(
            "Excluded when the wallet carries three or more evidence families, or belongs to a "
            "hand-audited operator window."
        ),
        rationale=(
            "Reads the author's \"removes clear sybills\" as a precision bar. Keeps every "
            "hand-verified operator pattern, and releases wallets whose entire case was two "
            "evidence families with no audited pattern behind it."
        ),
        proposal=True,
        needs_windows=True,
        predicate=lambda wallet, cluster_families, windows: (
            _families(wallet) >= 3 or wallet["address"] in windows
        ),
    ),
    Policy(
        id="E9",
        label="Three families in the group, two on the wallet",
        rule=(
            "Excluded when the wallet's group carries three or more evidence families and the "
            "wallet itself carries at least two."
        ),
        rationale=(
            "The same precision bar expressed only in rules, with no hand-curated input. "
            "Weaker on the wallets an audited window would catch, stronger on reproducibility."
        ),
        proposal=True,
        needs_windows=False,
        predicate=lambda wallet, cluster_families, windows: (
            cluster_families >= 3 and _families(wallet) >= 2
        ),
    ),
)

POLICIES_BY_ID = {policy.id: policy for policy in POLICIES}
DEFAULT_POLICY_ID = "E0"


@dataclass(frozen=True, slots=True)
class AuditedWindows:
    """The hand-audited operator windows, loaded from their own artifact."""

    members: frozenset
    windows: tuple[dict, ...]
    provenance: dict

    @classmethod
    def empty(cls) -> AuditedWindows:
        return cls(frozenset(), (), {})

    @classmethod
    def load(cls, path: Path) -> AuditedWindows:
        """Load the artifact, or fall back to empty when it is absent.

        A missing artifact must not take the service down: it disables the one
        policy that needs it rather than every route that touches eligibility.
        """
        if not path.exists():
            return cls.empty()
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            payload = json.load(handle)
        return cls(
            members=frozenset(str(a).lower() for a in payload.get("members", ())),
            windows=tuple(
                {"id": w["id"], "predicate": w["predicate"], "count": w["count"]}
                for w in payload.get("windows", ())
            ),
            provenance=dict(payload.get("provenance") or {}),
        )

    @property
    def available(self) -> bool:
        return bool(self.members)


def _cluster_family_counts(clusters: Iterable[Mapping]) -> dict[int, int]:
    return {cluster["id"]: len(cluster.get("families") or ()) for cluster in clusters}


def evaluate(
    wallets: Sequence[Mapping],
    clusters: Iterable[Mapping],
    windows: AuditedWindows,
    *,
    points: Mapping[str, int] | None = None,
) -> list[dict]:
    """Summarise every policy over one analysis version."""
    families_by_cluster = _cluster_family_counts(clusters)
    total_points = sum(points.values()) if points else 0
    summaries = []
    for policy in POLICIES:
        if policy.needs_windows and not windows.available:
            summaries.append(
                {
                    "id": policy.id,
                    "label": policy.label,
                    "rule": policy.rule,
                    "rationale": policy.rationale,
                    "proposal": policy.proposal,
                    "available": False,
                    "unavailable_reason": "the audited-window artifact is not present",
                }
            )
            continue
        excluded = 0
        excluded_points = 0
        eligible_by_status: dict[str, int] = {}
        for wallet in wallets:
            cluster_id = wallet.get("cluster_id")
            families = families_by_cluster.get(cluster_id, 0) if cluster_id is not None else 0
            if policy.excludes(wallet, families, windows.members):
                excluded += 1
                if points:
                    excluded_points += points.get(wallet["address"], 0)
            else:
                status = str(wallet.get("status"))
                eligible_by_status[status] = eligible_by_status.get(status, 0) + 1
        summary = {
            "id": policy.id,
            "label": policy.label,
            "rule": policy.rule,
            "rationale": policy.rationale,
            "proposal": policy.proposal,
            "available": True,
            "excluded": excluded,
            "eligible": len(wallets) - excluded,
            "eligible_by_analysis_status": eligible_by_status,
        }
        if points:
            summary["excluded_points_share"] = (
                round(excluded_points / total_points, 6) if total_points else 0.0
            )
        summaries.append(summary)
    return summaries


def wallet_standing(
    wallet: Mapping,
    cluster: Mapping | None,
    windows: AuditedWindows,
) -> list[dict]:
    """One wallet's standing under each policy, as separate facts from its status."""
    families = len(cluster.get("families") or ()) if cluster is not None else 0
    standing = []
    for policy in POLICIES:
        if policy.needs_windows and not windows.available:
            continue
        standing.append(
            {
                "id": policy.id,
                "label": policy.label,
                "proposal": policy.proposal,
                "eligible": not policy.excludes(wallet, families, windows.members),
            }
        )
    return standing
