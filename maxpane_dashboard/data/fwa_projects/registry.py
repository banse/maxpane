"""Immutable registry for independently deployed projects built on FWA.

The registry is an allowlist, not ecosystem discovery.  A row is present only
because its deployment, runtime bytecode, ABI surface, and declared canonical
FWA dependencies were checked during the approved research pass.  Mutable state
is never stored here.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Mapping

from maxpane_dashboard.data.fwa_ecosystem_addresses import (
    FWA_CORE,
    FWA_REWARDS,
    FWA_TOKEN,
)

from .base import ProjectManifest


def _manifest(
    *,
    family: str,
    surface: str,
    version: str,
    role: str,
    address: str,
    deployment_block: int,
    abi: str,
    codehash: str,
    source_status: str = "verified",
    is_current: bool,
    dependencies: tuple[tuple[str, str], ...],
) -> ProjectManifest:
    return ProjectManifest(
        family=family,
        surface=surface,
        version=version,
        role=role,
        address=address,
        deployment_block=deployment_block,
        abi_resource=f"abis/fwa/{abi}.json",
        runtime_codehash=codehash,
        source_status=source_status,
        is_current=is_current,
        dependencies=dependencies,
    )


PULLPOOL_V1 = "0xb2d80254af189854bf90d2c338d87236d67d2bf3"
PULLPOOL_V2 = "0x03c45c9c594b19ca5fde54f38c7e6b6a5f2329d7"
STANDING_ORDERS_V1 = "0xe60a9341c3c73636b911e609defaf05b09edeb9c"
STANDING_ORDERS_V2 = "0xfba041453dabbfe8b34409cf88417913cc483d1e"
GROUP_PULL = "0xd23dcbfd47e849dac946689e264aad3c6bbd4187"
GROUP_ORDERS = "0x2315f319c0e47afa26c6167e0e3a4dc46585f605"
MEGARIP_V1 = "0x68f8e0bd62ed310f692ae0d01f7e568948818d25"
MEGARIP_V2 = "0x6769944589f5cc96d5f900f06539681db84ac5c6"
MEGARIP_V3 = "0x58a1d8daf6d68eec8b350684e8fecc4379d13d7d"
FWAP_HOUSE_V1 = "0x00000000000e56073987eaf8694fe54fca2f53de"
FWAP_SHARE_V1 = "0x00000000007209d66e4128f17e82348d9348ac50"
FWAP_RECEIPT_V1 = "0x00000000003031738a7cf786baadd372f4c45cbb"
FWAP_HOUSE_V2 = "0x000000000095f80f42f09c4515d3ff841e65a541"
FWAP_SHARE_V2 = "0x0000000000f7795f0e6f5c7faf837bfb8b512c8a"
FWAP_RECEIPT_V2 = "0x000000000026185bdcb69f4a2631ffc4483f8635"


PROJECT_MANIFESTS: tuple[ProjectManifest, ...] = (
    _manifest(
        family="pullpool",
        surface="pullpool",
        version="v1",
        role="pool",
        address=PULLPOOL_V1,
        deployment_block=25_625_281,
        abi="pullpool_v1",
        codehash="0x86d7b83bf3ea73cadd39330b4eb58ca5ca3b8a25459430843db0d1b4ac78f40a",
        is_current=False,
        dependencies=(
            ("FWA", FWA_CORE),
            ("FWA_REWARDS", FWA_REWARDS),
            ("FWA_TOKEN", FWA_TOKEN),
        ),
    ),
    _manifest(
        family="pullpool",
        surface="pullpool",
        version="v2",
        role="pool",
        address=PULLPOOL_V2,
        deployment_block=25_639_384,
        abi="pullpool_v2",
        codehash="0x9086cc5f10b8b8ee1a775ae683f0770d151665a56e7b5f9632cc2253ec68a792",
        is_current=True,
        dependencies=(
            ("FWA", FWA_CORE),
            ("FWA_REWARDS", FWA_REWARDS),
            ("FWA_TOKEN", FWA_TOKEN),
        ),
    ),
    _manifest(
        family="standing_orders",
        surface="standing_orders",
        version="v1",
        role="factory",
        address=STANDING_ORDERS_V1,
        deployment_block=25_631_178,
        abi="standing_orders_v1",
        codehash="0x1f5161fb6b898fa6e5f2634022678109704011172c7b364bc8b53b9d56562073",
        is_current=False,
        dependencies=(("POOL", PULLPOOL_V1),),
    ),
    _manifest(
        family="standing_orders",
        surface="standing_orders",
        version="v2",
        role="factory",
        address=STANDING_ORDERS_V2,
        deployment_block=25_643_539,
        abi="standing_orders_v2",
        codehash="0x52b7619ed66be42d34b84d32d4dafd9ead511fe74b024706de2ebf1c61280735",
        is_current=True,
        dependencies=(
            ("pool", PULLPOOL_V2),
            ("LEGACY", PULLPOOL_V1),
            ("SUCCESSOR", PULLPOOL_V2),
        ),
    ),
    _manifest(
        family="group_pull",
        surface="group_pull",
        version="v1",
        role="pool",
        address=GROUP_PULL,
        deployment_block=25_671_215,
        abi="group_pull",
        codehash="0x3c53349d2d4b4c59cab54e3844c17ad6dc4c1967c0329801076923fb0e1957a7",
        is_current=True,
        dependencies=(("pool", PULLPOOL_V2), ("FWA_TOKEN", FWA_TOKEN)),
    ),
    _manifest(
        family="group_pull",
        surface="group_orders",
        version="v1",
        role="factory",
        address=GROUP_ORDERS,
        deployment_block=25_683_290,
        abi="group_orders",
        codehash="0xb2f3058bb25e51e28915a6f0fff1dbbb9adf637a8175bc371d1e220e915b4ba8",
        is_current=True,
        dependencies=(("GROUP", GROUP_PULL),),
    ),
    _manifest(
        family="megarip",
        surface="campaign",
        version="v1",
        role="campaign",
        address=MEGARIP_V1,
        deployment_block=25_721_560,
        abi="megarip_v1",
        codehash="0x7cd2bfa992850e1fb61393852e38f7c48b0e4fc01031ad820f3e3fd95d55ad8b",
        is_current=False,
        dependencies=(
            ("FWA", FWA_CORE),
            ("FWA_REWARDS", FWA_REWARDS),
            ("FWA_TOKEN", FWA_TOKEN),
        ),
    ),
    _manifest(
        family="megarip",
        surface="campaign",
        version="v2",
        role="campaign",
        address=MEGARIP_V2,
        deployment_block=25_771_992,
        abi="megarip_v2",
        codehash="0x56b1436bab9f9a603fb91de8fea2d10abbb3adfb2d280e3ac71386b2d5e60661",
        is_current=False,
        dependencies=(
            ("FWA", FWA_CORE),
            ("FWA_REWARDS", FWA_REWARDS),
            ("FWA_TOKEN", FWA_TOKEN),
        ),
    ),
    _manifest(
        family="megarip",
        surface="campaign",
        version="v3",
        role="campaign",
        address=MEGARIP_V3,
        deployment_block=25_827_317,
        abi="megarip_v3",
        codehash="0xca1db5711ba143cedd26c4e785e6f5f5c5698503105b373c7b060377d7077541",
        source_status="unverified",
        is_current=True,
        dependencies=(
            ("FWA", FWA_CORE),
            ("FWA_REWARDS", FWA_REWARDS),
            ("FWA_TOKEN", FWA_TOKEN),
        ),
    ),
    _manifest(
        family="fwap",
        surface="house",
        version="v1",
        role="house",
        address=FWAP_HOUSE_V1,
        deployment_block=25_715_581,
        abi="fwap_house_v1",
        codehash="0x82100575483b234c314eb63993560f7f4c5df57ab61eff7b463c7056dd72b43f",
        is_current=False,
        dependencies=(
            ("FWA", FWA_CORE),
            ("FWA_REWARDS", FWA_REWARDS),
            ("REWARD_TOKEN", FWA_TOKEN),
            ("SHARE_TOKEN", FWAP_SHARE_V1),
            ("RECEIPT_TOKEN", FWAP_RECEIPT_V1),
        ),
    ),
    _manifest(
        family="fwap",
        surface="share",
        version="v1",
        role="share",
        address=FWAP_SHARE_V1,
        deployment_block=25_715_580,
        abi="fwap_share_v1",
        codehash="0x87422373388712bace9b4fdeb9b1864e9f366eb306044f6184262d84ae6519e2",
        is_current=False,
        dependencies=(("house", FWAP_HOUSE_V1), ("REWARD_TOKEN", FWA_TOKEN)),
    ),
    _manifest(
        family="fwap",
        surface="receipt",
        version="v1",
        role="receipt",
        address=FWAP_RECEIPT_V1,
        deployment_block=25_715_579,
        abi="fwap_receipt_v1",
        codehash="0x0d6f24608304078fff0b229657ac4f68fbbb01cb91eaddfb48211456df66f744",
        is_current=False,
        dependencies=(("recycler", FWAP_HOUSE_V1),),
    ),
    _manifest(
        family="fwap",
        surface="house",
        version="v2",
        role="house",
        address=FWAP_HOUSE_V2,
        deployment_block=25_791_179,
        abi="fwap_house_v2",
        codehash="0x9994b7a30e8a3cb6600f44e921781cc83cd92ae25d3648bb7eadc3127047a071",
        is_current=True,
        dependencies=(
            ("FWA", FWA_CORE),
            ("FWA_REWARDS", FWA_REWARDS),
            ("REWARD_TOKEN", FWA_TOKEN),
            ("SHARE_TOKEN", FWAP_SHARE_V2),
            ("RECEIPT_TOKEN", FWAP_RECEIPT_V2),
        ),
    ),
    _manifest(
        family="fwap",
        surface="share",
        version="v2",
        role="share",
        address=FWAP_SHARE_V2,
        deployment_block=25_791_179,
        abi="fwap_share_v2",
        codehash="0xd76dd5ad3f9c316c112c72bf05fd9d159a23f98d9fdbbc8d7c3a73ca93565c7a",
        is_current=True,
        dependencies=(("house", FWAP_HOUSE_V2), ("REWARD_TOKEN", FWA_TOKEN)),
    ),
    _manifest(
        family="fwap",
        surface="receipt",
        version="v2",
        role="receipt",
        address=FWAP_RECEIPT_V2,
        deployment_block=25_791_179,
        abi="fwap_receipt_v2",
        codehash="0xcd9ed8aaac19ed7e7bf5869fa35d08b66a903ea9da3c1798efa65e49613863e9",
        is_current=True,
        dependencies=(("house", FWAP_HOUSE_V2), ("recycler", FWAP_HOUSE_V2)),
    ),
)

ManifestKey = tuple[str, str, str, str]

PROJECT_MANIFEST_BY_KEY: Mapping[ManifestKey, ProjectManifest] = MappingProxyType(
    {
        (manifest.family, manifest.surface, manifest.version, manifest.role): manifest
        for manifest in PROJECT_MANIFESTS
    }
)

CURRENT_PROJECT_MANIFESTS: tuple[ProjectManifest, ...] = tuple(
    manifest for manifest in PROJECT_MANIFESTS if manifest.is_current
)

# Bytes are pinned so CI can prove that a vendored ABI has not silently changed.
# The verified files are the view/pure + event subset of their Etherscan-verified
# ABIs.  MegaRip v3 is deliberately different: the first-party bundle supplied
# layouts, while every function selector and event topic was independently found
# in deployed runtime bytecode; observed logs covered its active lifecycle.  That
# evidence is sufficient for CHAIN-READ, never VERIFIED.
VENDORED_ABI_SHA256: Mapping[str, str] = MappingProxyType(
    {
        "abis/fwa/fwair_manager.json": "8136e2bebfeb6308a860e441fe23c79fcbd7be71628da5bd18786143bc32eaa1",
        "abis/fwa/fwair_launch.json": "e585b400a43b3402da6dd64d88fb47f0acc7bc2b925cda7a1f41da5d4557729e",
        "abis/fwa/pullpool_v1.json": "11fd3199ed50f397005fc211fc7c77972dc274e1efdac44fae5043027f79fcab",
        "abis/fwa/pullpool_v2.json": "574ca7b10c7ca443f4ce13bdf08808e522322bfc357cba319c476103caa0392b",
        "abis/fwa/standing_orders_v1.json": "554254645ca9789b4aa1278e30c851d280224433c34fa15edfd60d07e968ac6b",
        "abis/fwa/standing_orders_v2.json": "fd2c23fa82ffe6cd24d4dacb2e6a3f3acb470e39177595dc65841255d1db3bea",
        "abis/fwa/group_pull.json": "95ea85d931785860cd6184b7e50cfdd4e2e81fdbce6836c6e5b82f9735a86923",
        "abis/fwa/group_orders.json": "8133939f65db0662ddf64358d08b21bcbc5bd1178c3e17612e438e425041749c",
        "abis/fwa/megarip_v1.json": "9d699324cc49ad12d22f8db98209d24fc79a4925393470c41198d0a9e0ea0a18",
        "abis/fwa/megarip_v2.json": "b6bf4f7b5ce4c4648090829c9c8f75a4e9923648b4d84dfa15151ad545c2f27f",
        "abis/fwa/megarip_v3.json": "c104b6d98a25be1666d286f320628ed87d98bcdf26e38d11a5a48bc5eec0a6f7",
        "abis/fwa/fwap_house_v1.json": "a838b2e5ddd86853f364bb534ebc1a3ec2d7608bbbee17dc929f83889938396d",
        "abis/fwa/fwap_house_v2.json": "dd5b2f900612aac915a1b5d34018456f0e16cff0cae4ea1093ca7df3faf3b139",
        "abis/fwa/fwap_share_v1.json": "b4c7ac0c3150d63a975db5e19b1c7c1cb76bf6de96c9fb08121ace05bf3ea1d0",
        "abis/fwa/fwap_share_v2.json": "af64f267fe5150d541b3dab7252ca46b7c7ea088797d60a13631b36db7720df9",
        "abis/fwa/fwap_receipt_v1.json": "f2337ce87f2a7dcee95926ca97437ddf60d0ee1b9da0bdcedf4eefb4cd8add91",
        "abis/fwa/fwap_receipt_v2.json": "d14c54ffd738a4e28731b5e9940a0fed1724dac2d8ee8f56d38697ed6020e87f",
    }
)

VENDORED_ABI_PROVENANCE: Mapping[str, str] = MappingProxyType(
    {
        resource: (
            "first-party-bundle+runtime-selectors+runtime-topics+observed-logs"
            if resource == "abis/fwa/megarip_v3.json"
            else "etherscan-verified-source"
        )
        for resource in VENDORED_ABI_SHA256
    }
)


def get_project_manifest(
    family: str, surface: str, version: str, role: str
) -> ProjectManifest:
    """Return one exact manifest, raising ``KeyError`` for an unknown surface."""

    return PROJECT_MANIFEST_BY_KEY[(family, surface, version, role)]


def manifests_for_family(
    family: str, *, current_only: bool = False
) -> tuple[ProjectManifest, ...]:
    """Return registry-order manifests for one frozen project family."""

    return tuple(
        manifest
        for manifest in PROJECT_MANIFESTS
        if manifest.family == family and (manifest.is_current or not current_only)
    )


__all__ = [
    "CURRENT_PROJECT_MANIFESTS",
    "PROJECT_MANIFESTS",
    "PROJECT_MANIFEST_BY_KEY",
    "VENDORED_ABI_PROVENANCE",
    "VENDORED_ABI_SHA256",
    "get_project_manifest",
    "manifests_for_family",
    "PULLPOOL_V1",
    "PULLPOOL_V2",
    "STANDING_ORDERS_V1",
    "STANDING_ORDERS_V2",
    "GROUP_PULL",
    "GROUP_ORDERS",
    "MEGARIP_V1",
    "MEGARIP_V2",
    "MEGARIP_V3",
    "FWAP_HOUSE_V1",
    "FWAP_SHARE_V1",
    "FWAP_RECEIPT_V1",
    "FWAP_HOUSE_V2",
    "FWAP_SHARE_V2",
    "FWAP_RECEIPT_V2",
]
