"""Offline contract tests for the frozen FWA ecosystem deployment graph."""

from __future__ import annotations

import ast
import inspect
import json
import re
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from maxpane_dashboard.data import fwa_ecosystem_addresses as A

ADDRESS_RE = re.compile(r"^0x[0-9a-f]{40}$")
CODEHASH_RE = re.compile(r"^0x[0-9a-f]{64}$")
PACKAGE_ROOT = Path(A.__file__).resolve().parents[1]


EXPECTED = (
    (
        "core",
        "0xb276f62db0ce8ca2ca5bc522695be604521eac1c",
        25_546_793,
        "0xa53298a411a9ce5b5d352c45e3aaa90fac78632d21e7b928425cf6eb11ab8cc4",
        "abis/fwa/fwa_core.json",
    ),
    (
        "rewards",
        "0x6a1a1c0cfb3d3c538e13d36d608a5bcaa992fc78",
        25_546_795,
        "0xf638c9e341efecf99bd093cff9b780bb3f7bf03bbd814b80c092d7e3361b4555",
        "abis/fwa/fwa_rewards.json",
    ),
    (
        "vrf",
        "0xa084c33fb7a467307452898b8d58165ebd2e5d9f",
        25_546_791,
        "0x8ab6e6d4ca28ade13f80314ccd54b3a648734ee88a5bcd807711fe5ae037f4a4",
        "abis/fwa/fwa_vrf_service.json",
    ),
    (
        "token",
        "0xa0df17b5ac76ababa36e1450e2cbcd18a620c845",
        25_546_793,
        "0xd07b0280e4e25689956cff42290d843739714308e6fbe693017cede05c2c52fd",
        "abis/fwa/fwa_token.json",
    ),
    (
        "transfer_escrow",
        "0xce6d5b618e034f87c7a8b6dca65fb8669b8c301b",
        25_805_935,
        "0xfa15fdd90dc7d1fca0896bb6800d6ae75718369e621fe65a2c652cb812ac9f60",
        None,
    ),
    (
        "erc20_wrapper",
        "0x727c739f07a89f11e883fe0f34937c55e4c3d74a",
        25_626_109,
        "0x7290b8383665145791a739a5d8fd5c938fd70788571ad1d7999a7c7e87836c8b",
        None,
    ),
    (
        "renderer",
        "0x69cc9c633867eee71b17142bbbc2c6aaf14c61a4",
        25_626_109,
        "0x931f7f1b18e2b417c6d5bcdf80de1412f0b4b79551e30ddefd83586b16c2ce25",
        None,
    ),
    (
        "token_wrapper",
        "0x470879abd61fdca91436fe27ed87db2c8650f3e7",
        25_635_307,
        "0xe501d470b0c1cf04ac52b7021b40780d33642c74461304b32cdaff3f2cb3982e",
        None,
    ),
    (
        "hook",
        "0x2c67eba8a50af0db5fba55f725247a75cbda6444",
        25_546_793,
        "0x5eeafce23c30462750069d6313286eca9587da8ecffdff880288d31b75d41df0",
        "abis/fwa/fwa_token_hook.json",
    ),
    (
        "owner_splitter",
        "0x7400824eec17f86cc74385862810710f9c46ec04",
        25_747_691,
        "0x4806749cbc67c6cbc0a19960a776ec43597058b92dfb05b09c526e1aa0d02438",
        None,
    ),
    (
        "v1_claim",
        "0xd4085d38855f17edf0b1ccbfad7b3846fb305655",
        25_546_798,
        "0x2bcc7652822828e6672fe46b9f2330ea71bad315f2df8e740605e0e0fff89f0d",
        "abis/fwa/fwa_claim.json",
    ),
    (
        "whitelist_authority",
        "0x54b641ac97a9e9375665934b8e7a7d0b2c0e898b",
        25_818_569,
        "0x9599c4753ca705e17cb169d7c192298b45b55f0b98ba5c4d627d522d893c4a2e",
        None,
    ),
    (
        "fwair_manager",
        "0xfbc8b4ac9b827bde0fe8b2d6aa52043704d38628",
        25_818_681,
        "0x5844dd2b805ef433be410fcb954157e1f42cbfb070c20522fdf7dfd6bde566cf",
        "abis/fwa/fwair_manager.json",
    ),
)


def _as_tuple(deployment: A.OfficialDeployment) -> tuple[object, ...]:
    return (
        deployment.role,
        deployment.address,
        deployment.deployment_block,
        deployment.runtime_codehash,
        deployment.abi_resource,
    )


def test_official_manifest_is_the_exact_chain_checked_table() -> None:
    assert tuple(map(_as_tuple, A.OFFICIAL_DEPLOYMENTS)) == EXPECTED
    assert A.CHAIN_ID == 1
    assert A.REFERENCE_BLOCK == 25_849_738


def test_addresses_hashes_blocks_and_indexes_are_normalized() -> None:
    roles: list[str] = []
    addresses: list[str] = []
    for deployment in A.OFFICIAL_DEPLOYMENTS:
        assert ADDRESS_RE.fullmatch(deployment.address)
        assert CODEHASH_RE.fullmatch(deployment.runtime_codehash)
        assert 0 < deployment.deployment_block <= A.REFERENCE_BLOCK
        roles.append(deployment.role)
        addresses.append(deployment.address)

    assert len(roles) == len(set(roles))
    assert len(addresses) == len(set(addresses))
    assert dict(A.OFFICIAL_BY_ROLE) == {
        deployment.role: deployment for deployment in A.OFFICIAL_DEPLOYMENTS
    }
    assert dict(A.OFFICIAL_ADDRESSES) == {
        deployment.role: deployment.address
        for deployment in A.OFFICIAL_DEPLOYMENTS
    }


def test_every_declared_official_abi_is_packaged_and_json() -> None:
    for deployment in A.OFFICIAL_DEPLOYMENTS:
        if deployment.abi_resource is None:
            continue
        path = PACKAGE_ROOT / deployment.abi_resource
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(payload, list) and payload, deployment.role


def test_legacy_and_current_roles_can_never_be_equated() -> None:
    assert A.FWA_TTT_WHITELIST == "0x854352b275cf6a0dffcf2983c986fbe9345e17c3"
    assert A.FWA_NFT_FEE_SPLITTER == "0x1c175b9f0e8c73ed3e677e1cbb1b5a2dd4373bfe"
    assert A.FWAIR_WHITELIST_AUTHORITY == (
        "0x54b641ac97a9e9375665934b8e7a7d0b2c0e898b"
    )
    assert A.FWA_OWNER_SPLITTER == "0x7400824eec17f86cc74385862810710f9c46ec04"
    assert len(
        {
            A.FWA_TTT_WHITELIST,
            A.FWA_NFT_FEE_SPLITTER,
            A.FWAIR_WHITELIST_AUTHORITY,
            A.FWA_OWNER_SPLITTER,
        }
    ) == 4
    # The existing splitter ABI belongs to the legacy NFT-fee splitter, not
    # the current owner splitter.  Until a verified current ABI is vendored,
    # the current role remains codehash-only.
    assert A.OFFICIAL_BY_ROLE["owner_splitter"].abi_resource is None


def test_deployment_values_are_actually_frozen() -> None:
    with pytest.raises(FrozenInstanceError):
        A.OFFICIAL_DEPLOYMENTS[0].address = A.FWA_TOKEN  # type: ignore[misc]
    with pytest.raises(TypeError):
        A.OFFICIAL_BY_ROLE["core"] = A.OFFICIAL_DEPLOYMENTS[1]  # type: ignore[index]


def test_address_module_has_no_network_or_project_dependency() -> None:
    tree = ast.parse(inspect.getsource(A))
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".")[0])
    assert imported_roots == {"__future__", "dataclasses", "types", "typing"}
