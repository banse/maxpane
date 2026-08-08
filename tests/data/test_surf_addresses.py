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
    """Constants must be importable from a widget test with no I/O stack.

    Structural, not textual: walks the module's AST rather than
    substring-matching import lines, so a disguised or renamed third-party
    import (``import  httpx`` with extra whitespace, ``import requests as
    r``, ``import yaml``) cannot sail through the way a literal-string
    denylist would.
    """
    import ast
    import inspect
    import sys

    source = inspect.getsource(A)
    tree = ast.parse(source)

    import_nodes = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
    ]
    assert import_nodes, "expected at least one import node (the __future__ import)"

    for node in import_nodes:
        if isinstance(node, ast.Import):
            roots = {alias.name.split(".")[0] for alias in node.names}
        else:
            assert node.module is not None, "relative import with no module"
            roots = {node.module.split(".")[0]}
        for root in roots:
            assert root in sys.stdlib_module_names, (
                f"surf_addresses must not import non-stdlib module {root!r}"
            )


# ---------------------------------------------------------------------------
# topics + selectors, recomputed from their preimages
# ---------------------------------------------------------------------------

from maxpane_dashboard.data.keccak import keccak256_hex  # noqa: E402


@pytest.mark.parametrize("name,preimage", sorted(A.TOPIC_PREIMAGES.items()))
def test_topic_matches_its_preimage(name: str, preimage: str) -> None:
    assert getattr(A, name) == keccak256_hex(preimage.encode("ascii"))


@pytest.mark.parametrize("name,preimage", sorted(A.SELECTOR_PREIMAGES.items()))
def test_selector_matches_its_preimage(name: str, preimage: str) -> None:
    assert getattr(A, name) == keccak256_hex(preimage.encode("ascii"))[:10]


def test_preimage_maps_cover_exactly_the_constants() -> None:
    """A vendored hash with no preimage is unverifiable; a preimage with no
    constant is dead weight.  Both are failures."""
    topic_names = {n for n in dir(A) if n.startswith("TOPIC_") and n != "TOPIC_PREIMAGES"}
    sel_names = {n for n in dir(A) if n.startswith("SEL_")}
    assert set(A.TOPIC_PREIMAGES) == topic_names
    assert set(A.SELECTOR_PREIMAGES) == sel_names


def test_pinned_topic_values() -> None:
    """Pinned literals, so a *matching pair* of typos (preimage + hash) fails.

    These four hexes were computed during planning with this repo's keccak and
    cross-checked against docs/surf_PRD.md §5.
    """
    assert A.TOPIC_TRANSFER == (
        "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
    )
    assert A.TOPIC_IDENTITY_HASH_UPDATED == (
        "0x57c85cf86ae80c7b372281c7dd1b0f8b99de39e76d757725a32b6bd88f7ff1b6"
    )
    assert A.TOPIC_V4_INITIALIZE == (
        "0xdd466e674ea557f56295e2d0218a125ea4b4f0f6f3307b95f85e6110838d6438"
    )
    assert A.TOPIC_SEAPORT_ORDER_FULFILLED == (
        "0x9d9af8e38d66c62e2c12f0225249fd9d721c54b83f48d9352c97c6cacdcb6f31"
    )


def test_pinned_selector_values() -> None:
    assert A.SEL_POSITIONS == "0x99fbab88"
    assert A.SEL_IDENTITY_ALLOWED == "0xac8f3de6"
    assert A.SEL_TOTAL_SUPPLY == "0x18160ddd"
    assert A.SEL_SLOT0 == "0x3850c7bd"
    assert A.SEL_NAME == "0x06fdde03"
    assert A.SEL_SYMBOL == "0x95d89b41"


def test_hash_strings_are_lowercase_and_sized() -> None:
    for name in A.TOPIC_PREIMAGES:
        value = getattr(A, name)
        assert len(value) == 66 and value == value.lower()
    for name in A.SELECTOR_PREIMAGES:
        value = getattr(A, name)
        assert len(value) == 10 and value == value.lower()
