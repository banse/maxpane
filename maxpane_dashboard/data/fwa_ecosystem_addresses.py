"""Immutable Ethereum-mainnet deployment facts for the FWA ecosystem.

Only facts that cannot drift live here: addresses, creation blocks, vendored ABI
resources, and keccak256 hashes of deployed runtime bytecode.  Mutable protocol
configuration is deliberately absent and must be read from chain at a pinned block.

The table was rechecked on Ethereum mainnet (chain id 1) on 2026-08-28:

* every runtime hash matched ``keccak256(eth_getCode(address, "latest"))``;
* code was empty at ``deployment_block - 1`` and non-empty at
  ``deployment_block`` using a keyless archive endpoint.

No endpoint or acquisition code belongs in this module.  Runtime code consumes only
these frozen facts and the ABI files already packaged with MAXPANE.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

CHAIN_ID = 1
REFERENCE_BLOCK = 25_849_738


@dataclass(frozen=True, slots=True)
class OfficialDeployment:
    """One immutable node in the official FWA deployment graph."""

    role: str
    address: str
    deployment_block: int
    runtime_codehash: str
    abi_resource: str | None


# Addresses are lowercase by contract.  UI code may checksum them for display, but
# comparison and dependency validation always use these normalized forms.
FWA_CORE = "0xb276f62db0ce8ca2ca5bc522695be604521eac1c"
FWA_REWARDS = "0x6a1a1c0cfb3d3c538e13d36d608a5bcaa992fc78"
FWA_VRF = "0xa084c33fb7a467307452898b8d58165ebd2e5d9f"
FWA_TOKEN = "0xa0df17b5ac76ababa36e1450e2cbcd18a620c845"
FWA_TRANSFER_ESCROW = "0xce6d5b618e034f87c7a8b6dca65fb8669b8c301b"
FWA_ERC20_WRAPPER = "0x727c739f07a89f11e883fe0f34937c55e4c3d74a"
FWA_RENDERER = "0x69cc9c633867eee71b17142bbbc2c6aaf14c61a4"
FWA_TOKEN_WRAPPER = "0x470879abd61fdca91436fe27ed87db2c8650f3e7"
FWA_HOOK = "0x2c67eba8a50af0db5fba55f725247a75cbda6444"
# Legacy PULLS roles are intentionally named beside their successors.  They are
# different contracts with different semantics; visual similarity is no reason
# to reuse an ABI or label across them.
FWA_TTT_WHITELIST = "0x854352b275cf6a0dffcf2983c986fbe9345e17c3"
FWA_NFT_FEE_SPLITTER = "0x1c175b9f0e8c73ed3e677e1cbb1b5a2dd4373bfe"
FWA_OWNER_SPLITTER = "0x7400824eec17f86cc74385862810710f9c46ec04"
FWA_V1_CLAIM = "0xd4085d38855f17edf0b1ccbfad7b3846fb305655"
FWAIR_WHITELIST_AUTHORITY = "0x54b641ac97a9e9375665934b8e7a7d0b2c0e898b"
FWAIR_MANAGER = "0xfbc8b4ac9b827bde0fe8b2d6aa52043704d38628"


OFFICIAL_DEPLOYMENTS: tuple[OfficialDeployment, ...] = (
    OfficialDeployment(
        "core",
        FWA_CORE,
        25_546_793,
        "0xa53298a411a9ce5b5d352c45e3aaa90fac78632d21e7b928425cf6eb11ab8cc4",
        "abis/fwa/fwa_core.json",
    ),
    OfficialDeployment(
        "rewards",
        FWA_REWARDS,
        25_546_795,
        "0xf638c9e341efecf99bd093cff9b780bb3f7bf03bbd814b80c092d7e3361b4555",
        "abis/fwa/fwa_rewards.json",
    ),
    OfficialDeployment(
        "vrf",
        FWA_VRF,
        25_546_791,
        "0x8ab6e6d4ca28ade13f80314ccd54b3a648734ee88a5bcd807711fe5ae037f4a4",
        "abis/fwa/fwa_vrf_service.json",
    ),
    OfficialDeployment(
        "token",
        FWA_TOKEN,
        25_546_793,
        "0xd07b0280e4e25689956cff42290d843739714308e6fbe693017cede05c2c52fd",
        "abis/fwa/fwa_token.json",
    ),
    OfficialDeployment(
        "transfer_escrow",
        FWA_TRANSFER_ESCROW,
        25_805_935,
        "0xfa15fdd90dc7d1fca0896bb6800d6ae75718369e621fe65a2c652cb812ac9f60",
        None,
    ),
    OfficialDeployment(
        "erc20_wrapper",
        FWA_ERC20_WRAPPER,
        25_626_109,
        "0x7290b8383665145791a739a5d8fd5c938fd70788571ad1d7999a7c7e87836c8b",
        None,
    ),
    OfficialDeployment(
        "renderer",
        FWA_RENDERER,
        25_626_109,
        "0x931f7f1b18e2b417c6d5bcdf80de1412f0b4b79551e30ddefd83586b16c2ce25",
        None,
    ),
    OfficialDeployment(
        "token_wrapper",
        FWA_TOKEN_WRAPPER,
        25_635_307,
        "0xe501d470b0c1cf04ac52b7021b40780d33642c74461304b32cdaff3f2cb3982e",
        None,
    ),
    OfficialDeployment(
        "hook",
        FWA_HOOK,
        25_546_793,
        "0x5eeafce23c30462750069d6313286eca9587da8ecffdff880288d31b75d41df0",
        "abis/fwa/fwa_token_hook.json",
    ),
    OfficialDeployment(
        "owner_splitter",
        FWA_OWNER_SPLITTER,
        25_747_691,
        "0x4806749cbc67c6cbc0a19960a776ec43597058b92dfb05b09c526e1aa0d02438",
        None,
    ),
    OfficialDeployment(
        "v1_claim",
        FWA_V1_CLAIM,
        25_546_798,
        "0x2bcc7652822828e6672fe46b9f2330ea71bad315f2df8e740605e0e0fff89f0d",
        "abis/fwa/fwa_claim.json",
    ),
    OfficialDeployment(
        "whitelist_authority",
        FWAIR_WHITELIST_AUTHORITY,
        25_818_569,
        "0x9599c4753ca705e17cb169d7c192298b45b55f0b98ba5c4d627d522d893c4a2e",
        None,
    ),
    OfficialDeployment(
        "fwair_manager",
        FWAIR_MANAGER,
        25_818_681,
        "0x5844dd2b805ef433be410fcb954157e1f42cbfb070c20522fdf7dfd6bde566cf",
        "abis/fwa/fwair_manager.json",
    ),
)

OFFICIAL_BY_ROLE: Mapping[str, OfficialDeployment] = MappingProxyType(
    {deployment.role: deployment for deployment in OFFICIAL_DEPLOYMENTS}
)
OFFICIAL_ADDRESSES: Mapping[str, str] = MappingProxyType(
    {role: deployment.address for role, deployment in OFFICIAL_BY_ROLE.items()}
)


__all__ = [
    "CHAIN_ID",
    "REFERENCE_BLOCK",
    "OfficialDeployment",
    "FWA_CORE",
    "FWA_REWARDS",
    "FWA_VRF",
    "FWA_TOKEN",
    "FWA_TRANSFER_ESCROW",
    "FWA_ERC20_WRAPPER",
    "FWA_RENDERER",
    "FWA_TOKEN_WRAPPER",
    "FWA_HOOK",
    "FWA_TTT_WHITELIST",
    "FWA_NFT_FEE_SPLITTER",
    "FWA_OWNER_SPLITTER",
    "FWA_V1_CLAIM",
    "FWAIR_WHITELIST_AUTHORITY",
    "FWAIR_MANAGER",
    "OFFICIAL_DEPLOYMENTS",
    "OFFICIAL_BY_ROLE",
    "OFFICIAL_ADDRESSES",
]
