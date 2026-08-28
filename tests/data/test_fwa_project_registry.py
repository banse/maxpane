"""Offline manifest, dependency, and ABI integrity tests for FWA projects."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from pydantic import ValidationError

from maxpane_dashboard.data.fwa_ecosystem_addresses import (
    FWA_CORE,
    FWA_REWARDS,
    FWA_TOKEN,
    REFERENCE_BLOCK,
)
from maxpane_dashboard.data.fwa_ecosystem_models import PROJECT_FAMILIES
from maxpane_dashboard.data.fwa_projects.base import (
    ProjectManifest,
    load_abi_resource,
    load_manifest_abi,
    resolve_abi_resource,
)
from maxpane_dashboard.data.fwa_projects.registry import (
    CURRENT_PROJECT_MANIFESTS,
    FWAP_HOUSE_V1,
    FWAP_HOUSE_V2,
    FWAP_RECEIPT_V1,
    FWAP_RECEIPT_V2,
    FWAP_SHARE_V1,
    FWAP_SHARE_V2,
    GROUP_ORDERS,
    GROUP_PULL,
    MEGARIP_V1,
    MEGARIP_V2,
    MEGARIP_V3,
    PROJECT_MANIFEST_BY_KEY,
    PROJECT_MANIFESTS,
    PULLPOOL_V1,
    PULLPOOL_V2,
    STANDING_ORDERS_V1,
    STANDING_ORDERS_V2,
    VENDORED_ABI_PROVENANCE,
    VENDORED_ABI_SHA256,
    get_project_manifest,
    manifests_for_family,
)
from maxpane_dashboard.data.keccak import keccak256_hex


def _key(manifest: ProjectManifest) -> tuple[str, str, str, str]:
    return manifest.family, manifest.surface, manifest.version, manifest.role


EXPECTED_DEPLOYMENTS = (
    (
        ("pullpool", "pullpool", "v1", "pool"),
        PULLPOOL_V1,
        25_625_281,
        "0x86d7b83bf3ea73cadd39330b4eb58ca5ca3b8a25459430843db0d1b4ac78f40a",
    ),
    (
        ("pullpool", "pullpool", "v2", "pool"),
        PULLPOOL_V2,
        25_639_384,
        "0x9086cc5f10b8b8ee1a775ae683f0770d151665a56e7b5f9632cc2253ec68a792",
    ),
    (
        ("standing_orders", "standing_orders", "v1", "factory"),
        STANDING_ORDERS_V1,
        25_631_178,
        "0x1f5161fb6b898fa6e5f2634022678109704011172c7b364bc8b53b9d56562073",
    ),
    (
        ("standing_orders", "standing_orders", "v2", "factory"),
        STANDING_ORDERS_V2,
        25_643_539,
        "0x52b7619ed66be42d34b84d32d4dafd9ead511fe74b024706de2ebf1c61280735",
    ),
    (
        ("group_pull", "group_pull", "v1", "pool"),
        GROUP_PULL,
        25_671_215,
        "0x3c53349d2d4b4c59cab54e3844c17ad6dc4c1967c0329801076923fb0e1957a7",
    ),
    (
        ("group_pull", "group_orders", "v1", "factory"),
        GROUP_ORDERS,
        25_683_290,
        "0xb2f3058bb25e51e28915a6f0fff1dbbb9adf637a8175bc371d1e220e915b4ba8",
    ),
    (
        ("megarip", "campaign", "v1", "campaign"),
        MEGARIP_V1,
        25_721_560,
        "0x7cd2bfa992850e1fb61393852e38f7c48b0e4fc01031ad820f3e3fd95d55ad8b",
    ),
    (
        ("megarip", "campaign", "v2", "campaign"),
        MEGARIP_V2,
        25_771_992,
        "0x56b1436bab9f9a603fb91de8fea2d10abbb3adfb2d280e3ac71386b2d5e60661",
    ),
    (
        ("megarip", "campaign", "v3", "campaign"),
        MEGARIP_V3,
        25_827_317,
        "0xca1db5711ba143cedd26c4e785e6f5f5c5698503105b373c7b060377d7077541",
    ),
    (
        ("fwap", "house", "v1", "house"),
        FWAP_HOUSE_V1,
        25_715_581,
        "0x82100575483b234c314eb63993560f7f4c5df57ab61eff7b463c7056dd72b43f",
    ),
    (
        ("fwap", "share", "v1", "share"),
        FWAP_SHARE_V1,
        25_715_580,
        "0x87422373388712bace9b4fdeb9b1864e9f366eb306044f6184262d84ae6519e2",
    ),
    (
        ("fwap", "receipt", "v1", "receipt"),
        FWAP_RECEIPT_V1,
        25_715_579,
        "0x0d6f24608304078fff0b229657ac4f68fbbb01cb91eaddfb48211456df66f744",
    ),
    (
        ("fwap", "house", "v2", "house"),
        FWAP_HOUSE_V2,
        25_791_179,
        "0x9994b7a30e8a3cb6600f44e921781cc83cd92ae25d3648bb7eadc3127047a071",
    ),
    (
        ("fwap", "share", "v2", "share"),
        FWAP_SHARE_V2,
        25_791_179,
        "0xd76dd5ad3f9c316c112c72bf05fd9d159a23f98d9fdbbc8d7c3a73ca93565c7a",
    ),
    (
        ("fwap", "receipt", "v2", "receipt"),
        FWAP_RECEIPT_V2,
        25_791_179,
        "0xcd9ed8aaac19ed7e7bf5869fa35d08b66a903ea9da3c1798efa65e49613863e9",
    ),
)


EXPECTED_DEPENDENCIES = {
    ("pullpool", "pullpool", "v1", "pool"): (
        ("FWA", FWA_CORE),
        ("FWA_REWARDS", FWA_REWARDS),
        ("FWA_TOKEN", FWA_TOKEN),
    ),
    ("pullpool", "pullpool", "v2", "pool"): (
        ("FWA", FWA_CORE),
        ("FWA_REWARDS", FWA_REWARDS),
        ("FWA_TOKEN", FWA_TOKEN),
    ),
    ("standing_orders", "standing_orders", "v1", "factory"): (
        ("POOL", PULLPOOL_V1),
    ),
    ("standing_orders", "standing_orders", "v2", "factory"): (
        ("pool", PULLPOOL_V2),
        ("LEGACY", PULLPOOL_V1),
        ("SUCCESSOR", PULLPOOL_V2),
    ),
    ("group_pull", "group_pull", "v1", "pool"): (
        ("pool", PULLPOOL_V2),
        ("FWA_TOKEN", FWA_TOKEN),
    ),
    ("group_pull", "group_orders", "v1", "factory"): (("GROUP", GROUP_PULL),),
    ("megarip", "campaign", "v1", "campaign"): (
        ("FWA", FWA_CORE),
        ("FWA_REWARDS", FWA_REWARDS),
        ("FWA_TOKEN", FWA_TOKEN),
    ),
    ("megarip", "campaign", "v2", "campaign"): (
        ("FWA", FWA_CORE),
        ("FWA_REWARDS", FWA_REWARDS),
        ("FWA_TOKEN", FWA_TOKEN),
    ),
    ("megarip", "campaign", "v3", "campaign"): (
        ("FWA", FWA_CORE),
        ("FWA_REWARDS", FWA_REWARDS),
        ("FWA_TOKEN", FWA_TOKEN),
    ),
    ("fwap", "house", "v1", "house"): (
        ("FWA", FWA_CORE),
        ("FWA_REWARDS", FWA_REWARDS),
        ("REWARD_TOKEN", FWA_TOKEN),
        ("SHARE_TOKEN", FWAP_SHARE_V1),
        ("RECEIPT_TOKEN", FWAP_RECEIPT_V1),
    ),
    ("fwap", "share", "v1", "share"): (
        ("house", FWAP_HOUSE_V1),
        ("REWARD_TOKEN", FWA_TOKEN),
    ),
    ("fwap", "receipt", "v1", "receipt"): (("recycler", FWAP_HOUSE_V1),),
    ("fwap", "house", "v2", "house"): (
        ("FWA", FWA_CORE),
        ("FWA_REWARDS", FWA_REWARDS),
        ("REWARD_TOKEN", FWA_TOKEN),
        ("SHARE_TOKEN", FWAP_SHARE_V2),
        ("RECEIPT_TOKEN", FWAP_RECEIPT_V2),
    ),
    ("fwap", "share", "v2", "share"): (
        ("house", FWAP_HOUSE_V2),
        ("REWARD_TOKEN", FWA_TOKEN),
    ),
    ("fwap", "receipt", "v2", "receipt"): (
        ("house", FWAP_HOUSE_V2),
        ("recycler", FWAP_HOUSE_V2),
    ),
}


REQUIRED_MEMBERS = {
    "fwair_manager.json": (
        {"nextLaunchId", "launches", "launchRuntimeCodeHash", "fwa", "whitelistAuthority"},
        {"LaunchRegistered", "LaunchRuntimeCodeHashSet"},
    ),
    "fwair_launch.json": (
        {
            "manager",
            "fwa",
            "rewardToken",
            "collection",
            "phase",
            "tokenCount",
            "supportedCount",
            "supporterCount",
            "launchedCount",
            "terminalCount",
            "artistETHCredit",
            "supporterTokenReserve",
        },
        {"PhaseChanged", "PositionSupported", "PositionLaunched", "PositionStatusSynced"},
    ),
    "pullpool_v1.json": (
        {"FWA", "FWA_REWARDS", "FWA_TOKEN", "accountedEth", "roundCount", "getRound"},
        {"RoundOpened", "RoundSettled", "RoundVoided", "RefundClaimed"},
    ),
    "pullpool_v2.json": (
        {
            "FWA",
            "FWA_REWARDS",
            "FWA_TOKEN",
            "accountedEth",
            "roundCount",
            "currentOpenRound",
            "pendingPullCount",
            "getRound",
        },
        {"RoundOpened", "RoundSettled", "RoundVoided", "ReferralRecorded"},
    ),
    "standing_orders_v1.json": ({"POOL", "orderCount", "allOrders"}, {"OrderCreated"}),
    "standing_orders_v2.json": (
        {"pool", "LEGACY", "SUCCESSOR", "orderCount", "allOrders"},
        {"OrderCreated"},
    ),
    "group_pull.json": (
        {"pool", "FWA_TOKEN", "accountedEth", "fwaAccounted", "roundCount", "getRound"},
        {"RoundOpened", "RoundClosed", "Claimed"},
    ),
    "group_orders.json": ({"GROUP", "orderCount", "allOrders"}, {"OrderCreated"}),
    "megarip_v1.json": (
        {
            "FWA",
            "FWA_REWARDS",
            "FWA_TOKEN",
            "state",
            "totalDeposited",
            "totalPaid",
            "pot",
            "acquisitionSpend",
            "pullsDone",
            "depositorCount",
            "depositorAt",
            "depositOf",
            "paidTo",
            "claimable",
        },
        {"Deposited", "Locked", "PullRequested", "Allocated", "SettledBid", "Finalized", "Claimed"},
    ),
    "megarip_v2.json": (
        {
            "FWA",
            "FWA_REWARDS",
            "FWA_TOKEN",
            "state",
            "totalDeposited",
            "totalPaid",
            "pot",
            "acquisitionSpend",
            "pullsDone",
            "depositorCount",
            "fwaReceived",
            "fwaTotalPaid",
            "fwaClaimable",
        },
        {"Deposited", "PullRequested", "SettledBid", "Finalized", "Claimed", "FwaClaimed"},
    ),
    "megarip_v3.json": (
        {
            "FWA",
            "FWA_REWARDS",
            "FWA_TOKEN",
            "state",
            "totalDeposited",
            "totalPaid",
            "pot",
            "acquisitionSpend",
            "pullsDone",
            "depositorCount",
            "fwaReceived",
            "fwaTotalPaid",
            "fwaClaimable",
            "requestBounty",
            "syncBounty",
            "settleBounty",
        },
        {"Deposited", "PullRequested", "SettledBid", "Finalized", "Claimed", "KeeperBountiesSet"},
    ),
    "fwap_house_v1.json": (
        {
            "FWA",
            "FWA_REWARDS",
            "REWARD_TOKEN",
            "SHARE_TOKEN",
            "RECEIPT_TOKEN",
            "nextPositionId",
            "bookNav",
            "liquidCapital",
            "position",
        },
        {"InventoryContributed", "PositionSynced", "Redeemed", "RewardsHarvested"},
    ),
    "fwap_house_v2.json": (
        {
            "FWA",
            "FWA_REWARDS",
            "REWARD_TOKEN",
            "SHARE_TOKEN",
            "RECEIPT_TOKEN",
            "nextPositionId",
            "bookNav",
            "liquidCapital",
            "epochInfo",
            "position",
        },
        {"InventoryContributed", "PositionSynced", "Redeemed", "RewardsHarvested"},
    ),
    "fwap_share_v1.json": (
        {"house", "REWARD_TOKEN", "totalSupply", "fwaLiability", "claimableFwa"},
        {"FwaRewardClaimed", "Transfer"},
    ),
    "fwap_share_v2.json": (
        {"house", "REWARD_TOKEN", "totalSupply", "fwaLiability", "claimableFwa"},
        {"FwaRewardClaimed", "Transfer"},
    ),
    "fwap_receipt_v1.json": ({"recycler", "balanceOf", "ownerOf"}, {"Transfer"}),
    "fwap_receipt_v2.json": ({"house", "recycler", "balanceOf", "ownerOf"}, {"Transfer"}),
}


def test_registry_is_the_exact_versioned_deployment_table() -> None:
    actual = tuple(
        (_key(manifest), manifest.address, manifest.deployment_block, manifest.runtime_codehash)
        for manifest in PROJECT_MANIFESTS
    )
    assert actual == EXPECTED_DEPLOYMENTS
    assert len(PROJECT_MANIFEST_BY_KEY) == len(PROJECT_MANIFESTS) == 15
    assert all(manifest.deployment_block <= REFERENCE_BLOCK for manifest in PROJECT_MANIFESTS)
    assert len({manifest.address for manifest in PROJECT_MANIFESTS}) == len(PROJECT_MANIFESTS)
    assert {manifest.family for manifest in PROJECT_MANIFESTS} == set(PROJECT_FAMILIES)


def test_current_surfaces_are_explicit_not_inferred_from_version_text() -> None:
    assert tuple(_key(manifest) for manifest in CURRENT_PROJECT_MANIFESTS) == (
        ("pullpool", "pullpool", "v2", "pool"),
        ("standing_orders", "standing_orders", "v2", "factory"),
        ("group_pull", "group_pull", "v1", "pool"),
        ("group_pull", "group_orders", "v1", "factory"),
        ("megarip", "campaign", "v3", "campaign"),
        ("fwap", "house", "v2", "house"),
        ("fwap", "share", "v2", "share"),
        ("fwap", "receipt", "v2", "receipt"),
    )


def test_dependency_manifests_are_exact_and_the_getters_exist() -> None:
    assert {_key(manifest): manifest.dependencies for manifest in PROJECT_MANIFESTS} == (
        EXPECTED_DEPENDENCIES
    )
    for manifest in PROJECT_MANIFESTS:
        abi = load_manifest_abi(manifest)
        functions = {
            entry["name"]: entry
            for entry in abi
            if entry.get("type") == "function"
        }
        for getter, _expected_address in manifest.dependencies:
            entry = functions[getter]
            assert entry["inputs"] == [], (manifest.abi_resource, getter)
            assert [output["type"] for output in entry["outputs"]] == ["address"]
            assert entry["stateMutability"] == "view"


def test_all_vendored_abi_bytes_match_the_offline_digest_manifest() -> None:
    assert set(VENDORED_ABI_SHA256) == {
        manifest.abi_resource for manifest in PROJECT_MANIFESTS
    } | {"abis/fwa/fwair_manager.json", "abis/fwa/fwair_launch.json"}
    for resource, expected_digest in VENDORED_ABI_SHA256.items():
        path = resolve_abi_resource(resource)
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected_digest


def test_new_abis_contain_only_read_functions_and_events() -> None:
    for resource in VENDORED_ABI_SHA256:
        abi = load_abi_resource(resource)
        signatures: set[tuple[str, str, tuple[str, ...]]] = set()
        for entry in abi:
            assert entry["type"] in {"function", "event"}, resource
            if entry["type"] == "function":
                assert entry["stateMutability"] in {"view", "pure"}, (
                    resource,
                    entry["name"],
                )
            signature = (
                entry["type"],
                entry["name"],
                tuple(item["type"] for item in entry.get("inputs", ())),
            )
            assert signature not in signatures, (resource, signature)
            signatures.add(signature)


@pytest.mark.parametrize("filename", sorted(REQUIRED_MEMBERS))
def test_adapter_required_read_and_event_surfaces_are_vendored(filename: str) -> None:
    abi = load_abi_resource(f"abis/fwa/{filename}")
    functions = {entry["name"] for entry in abi if entry["type"] == "function"}
    events = {entry["name"] for entry in abi if entry["type"] == "event"}
    required_functions, required_events = REQUIRED_MEMBERS[filename]
    assert required_functions <= functions
    assert required_events <= events


def test_megarip_v3_is_chain_read_only_and_never_verified() -> None:
    v3 = get_project_manifest("megarip", "campaign", "v3", "campaign")
    assert v3.source_status == "unverified"
    assert VENDORED_ABI_PROVENANCE[v3.abi_resource] == (
        "first-party-bundle+runtime-selectors+runtime-topics+observed-logs"
    )
    assert all(
        manifest.source_status == "verified"
        for manifest in PROJECT_MANIFESTS
        if manifest is not v3
    )

    # These v3-only read selectors were independently present in deployed
    # runtime bytecode.  Pinning them protects the CHAIN-READ surface from a
    # future frontend-bundle mutation being mistaken for verified source.
    signatures = {
        "MAX_REQUEST_BOUNTY()": "0x008df46f",
        "requestBounty()": "0x230bd25d",
        "MAX_SYNC_BOUNTY()": "0x7d335eb8",
        "settleBounty()": "0xa7fd0f04",
        "MAX_SETTLE_BOUNTY()": "0xdf1ac58c",
        "syncBounty()": "0xeb9392af",
        "MAX_PULLS_PER_CALL()": "0xf9db310a",
    }
    for signature, expected in signatures.items():
        assert keccak256_hex(signature.encode("ascii"))[:10] == expected
    assert keccak256_hex(b"KeeperBountiesSet(uint128,uint128,uint128)") == (
        "0x049db95e93efa74502c4efeedab59964bfd90ce9469557ba34cb87ae3e1f489c"
    )


def test_manifest_boundary_is_frozen_extra_forbidden_and_safe() -> None:
    original = PROJECT_MANIFESTS[0]
    with pytest.raises(ValidationError):
        original.address = PULLPOOL_V2  # type: ignore[misc]

    payload = original.model_dump()
    with pytest.raises(ValidationError):
        ProjectManifest(**payload, unexpected="no aliases")  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        ProjectManifest(**{**payload, "family": "unknown"})
    with pytest.raises(ValidationError):
        ProjectManifest(**{**payload, "address": original.address.upper()})
    with pytest.raises(ValidationError):
        ProjectManifest(**{**payload, "source_status": "frontend-says-so"})
    with pytest.raises(ValidationError):
        ProjectManifest(**{**payload, "abi_resource": "abis/fwa/../secret.json"})
    with pytest.raises(ValueError):
        resolve_abi_resource("abis/fwa/../secret.json")
    with pytest.raises(TypeError):
        PROJECT_MANIFEST_BY_KEY[_key(original)] = PROJECT_MANIFESTS[1]  # type: ignore[index]


def test_registry_lookup_helpers_preserve_registry_order() -> None:
    assert get_project_manifest(*_key(PROJECT_MANIFESTS[1])) is PROJECT_MANIFESTS[1]
    assert manifests_for_family("megarip") == PROJECT_MANIFESTS[6:9]
    assert manifests_for_family("megarip", current_only=True) == (PROJECT_MANIFESTS[8],)
    assert manifests_for_family("not-a-family") == ()
