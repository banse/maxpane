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
    "BURN_EXECUTOR_V1",
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
    "BURN_EXECUTOR_V2",
    "LAUNCHPAD_HOOK",
    "LAUNCHPAD_FACTORY",
    "POSITION_MANAGER_V4",
    "BASE_BURN_RECEIVER",
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


# ---------------------------------------------------------------------------
# KNOWN_LABELS — the allowlist that defeats address poisoning
# ---------------------------------------------------------------------------

# Live spoofs found in frenpet.eth's history on 2026-08-08.  Each sent exactly
# 1 gwei so it would appear in the wallet's tx list next to the real recipient.
LIVE_SPOOFS = (
    "0x61ccfd5d33f0f27a2cd5acb558d9281b110df14e",  # imitates LP_FEE_SINK_B
    "0xf3083828702c1989710ceca517412071c2f60ee6",  # imitates LP_FEE_SINK_A
    "0xf30875988b99489ac71ec2f5069de0dd80b70ee6",  # imitates LP_FEE_SINK_A
)


def test_known_labels_keys_are_lowercase_addresses() -> None:
    for key in A.KNOWN_LABELS:
        assert key == key.lower(), key
        assert len(key) == 42 and key.startswith("0x"), key


def test_known_labels_covers_every_labeled_address() -> None:
    assert set(A.KNOWN_LABELS) == {a.lower() for a in A.LABELED_ADDRESSES}


def test_labels_are_short_enough_for_a_narrow_column() -> None:
    for key, label in A.KNOWN_LABELS.items():
        assert label.strip() == label and label, key
        assert len(label) <= 22, f"{label!r} will blow up the activity column"


def test_no_spoof_is_ever_labeled() -> None:
    """The defence is an allowlist.  A poisoned lookalike must fall through to
    the dimmed unknown rendering, never to a label."""
    for spoof in LIVE_SPOOFS:
        assert spoof not in A.KNOWN_LABELS


def test_the_real_fee_sinks_are_labeled_and_differ_from_their_spoofs() -> None:
    assert A.KNOWN_LABELS[A.LP_FEE_SINK_A.lower()]
    assert A.KNOWN_LABELS[A.LP_FEE_SINK_B.lower()]
    assert A.LP_FEE_SINK_A.lower() not in LIVE_SPOOFS
    assert A.LP_FEE_SINK_B.lower() not in LIVE_SPOOFS
    # They differ only in the middle — first 6 and last 4 chars collide.
    assert A.LP_FEE_SINK_B.lower()[:6] == LIVE_SPOOFS[0][:6]
    assert A.LP_FEE_SINK_B.lower()[-4:] == LIVE_SPOOFS[0][-4:]


# ---------------------------------------------------------------------------
# v4 migration + IMD launchpad — the frozen contract addition (2026-08-23)
# ---------------------------------------------------------------------------


def test_launchpad_addresses_are_pinned() -> None:
    """The three contracts shipped 2026-08-19/20, read from chain 2026-08-23."""
    assert A.LAUNCHPAD_HOOK == "0x51768F5dA32BA2008304cC81674da51aCb802888"
    assert A.LAUNCHPAD_FACTORY == "0x73d1ae084F04f793A5bbd6B623d74400C9Fc3f42"
    assert A.BURN_EXECUTOR_V2 == "0xe29386719C155B6847aD5a4E97C6674f10ffc750"
    assert A.POSITION_MANAGER_V4 == "0xbD216513d74C8cf14cf4747E6AaA6420FF64ee9e"
    assert A.BASE_BURN_RECEIVER == "0xf9d7CBf5Bef2f5c9ba93a70F31DdCA6457716793"


def test_burn_executor_v1_is_kept_and_distinct() -> None:
    """V1 holds 0.664 IMD of residue and appears in the historical ledger."""
    assert A.BURN_EXECUTOR_V1 == "0x2EC59BEd2fB9deE447bbEC6e3BCA249782C9B88B"
    assert A.BURN_EXECUTOR_V1 != A.BURN_EXECUTOR_V2


def test_pool_v4_id_is_a_fallback_not_a_source() -> None:
    """Named FALLBACK so no reader mistakes it for the live value.

    The live id comes from LaunchpadHook.imdEthPoolId(); 37 decoy pools make a
    stale constant actively dangerous.
    """
    assert A.POOL_V4_ID_FALLBACK == (
        "0xb07d640fd9e2eb9dc81b953c8e4fd006bdfeaf276010fb5418eb763ca15abfb3"
    )
    assert not hasattr(A, "POOL_V4_ID")


def test_v4_pools_mapping_slot() -> None:
    """PoolManager._pools lives at storage slot 6; verified live via extsload."""
    assert A.V4_POOLS_MAPPING_SLOT == 6


def test_pinned_v4_and_launchpad_topics() -> None:
    assert A.TOPIC_MODIFY_LIQUIDITY == keccak256_hex(
        b"ModifyLiquidity(bytes32,address,int24,int24,int256,bytes32)"
    )
    assert A.TOPIC_LAUNCHED == keccak256_hex(
        b"Launched(bytes32,address,address,string,string,uint256,uint256)"
    )
    assert A.TOPIC_IMD_BURNED == keccak256_hex(b"ImdBurned(uint256)")


def test_pinned_launchpad_selectors() -> None:
    assert A.SEL_EXTSLOAD == keccak256_hex(b"extsload(bytes32)")[:10]
    assert A.SEL_IMD_ETH_POOL_ID == keccak256_hex(b"imdEthPoolId()")[:10]
    assert A.SEL_COIN_COUNT == keccak256_hex(b"coinCount()")[:10]
