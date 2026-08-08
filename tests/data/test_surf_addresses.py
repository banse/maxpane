"""Frozen address surface for the surf dashboard.

Every constant here is re-derived in-test: the checksum is recomputed with the
repo's own keccak, so a transposed nibble pasted from a research doc fails here
instead of silently reading a different contract on mainnet.
"""

from __future__ import annotations

import pytest

from maxpane_dashboard.data import surf_addresses as A
from maxpane_dashboard.data.keccak import keccak256

# The 14 names the module contract froze, plus the additive label targets.
PRIMARY = (
    "DEV_WALLET",
    "OPS_WALLET",
    "ANNOUNCE",
    "IMD_TOKEN",
    "IDMD_NFT",
    "IDENTITY_RENDERER",
    "IDENTITY_REGISTRY",
    "POOL_V3",
    "NFPM",
    "BURN_EXECUTOR",
    "FP_TOKEN_BASE",
    "ERC8004_REGISTRY",
    "POOL_MANAGER_V4",
    "WETH",
)
SECONDARY = (
    "SEAPORT",
    "UNIVERSAL_ROUTER",
    "RELAY_DEPOSITORY",
    "FWA_SPLITTER",
    "DEV_SWEEP",
    "LP_FEE_SINK_A",
    "LP_FEE_SINK_B",
    "CREATE2_FACTORY",
    "VIBECOINS_HOOK",
    "IDMD_BASE_TWIN",
    "KRAKEN_HOT",
    "ZERO_ADDRESS",
)


def to_checksum(addr: str) -> str:
    """EIP-55, recomputed with the repo's keccak (not hashlib.sha3_256)."""
    body = addr.lower().removeprefix("0x")
    digest = keccak256(body.encode("ascii")).hex()
    return "0x" + "".join(
        ch.upper() if ch.isalpha() and int(digest[i], 16) >= 8 else ch
        for i, ch in enumerate(body)
    )


@pytest.mark.parametrize("name", PRIMARY + SECONDARY)
def test_every_address_is_checksummed(name: str) -> None:
    value = getattr(A, name)
    assert isinstance(value, str), name
    assert len(value) == 42 and value.startswith("0x"), name
    assert value == to_checksum(value), f"{name} is not EIP-55 checksummed"


def test_pinned_identities() -> None:
    """The four addresses a typo would silently redirect to someone else."""
    assert A.ANNOUNCE == "0x200E710aCAA6A93bbc77146026328C40F1d60fB1"
    assert A.IMD_TOKEN == "0xD34a99Bc0f67aE1bbd63C660e6d0b0dd03E263B7"
    assert A.IDMD_NFT == "0x0000eC93127BAA929E58E97dd0095A2BFb38ec1D"
    assert A.POOL_V3 == "0xD6A822D028bbf7b6EDfA1533e110Ee40c08551d9"


def test_lp_position_id() -> None:
    assert A.LP_POSITION_ID == 1167726
    assert isinstance(A.LP_POSITION_ID, int)


def test_addresses_are_distinct() -> None:
    values = [getattr(A, n).lower() for n in PRIMARY + SECONDARY]
    assert len(set(values)) == len(values), "duplicate address constant"


def test_labeled_addresses_is_the_union() -> None:
    assert set(A.LABELED_ADDRESSES) == {
        getattr(A, n) for n in PRIMARY + SECONDARY
    }


def test_module_imports_nothing_but_stdlib() -> None:
    """Constants must be importable from a widget test with no I/O stack."""
    import inspect

    source = inspect.getsource(A)
    for banned in ("import httpx", "import asyncio", "from textual", "import requests"):
        assert banned not in source, f"surf_addresses must not {banned}"
