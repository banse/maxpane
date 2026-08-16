"""Frozen address, topic and selector surface for the curator dashboard.

Every constant here is re-derived in-test: checksums are recomputed with this
repo's own keccak, topic0s and selectors are recomputed from Solidity preimages
that are themselves checked against the verified source, and every deployment
fact is read out of the committed creation-tx capture rather than typed.  A
transposed nibble pasted from a research doc fails here instead of silently
reading a different contract on mainnet.
"""

from __future__ import annotations

import inspect
import json
import re
from pathlib import Path

import pytest

from maxpane_dashboard.data import curator_addresses as A
from maxpane_dashboard.data.keccak import keccak256, keccak256_hex
from tests.curator_fixtures import capture, capture_text

ADDRESS_NAMES = ("CURATOR", "DEPLOYER", "ANNOUNCE", "ZERO_ADDRESS")


def to_checksum(addr: str) -> str:
    """EIP-55, recomputed with the repo's keccak (not ``hashlib.sha3_256``)."""
    body = addr.lower().removeprefix("0x")
    digest = keccak256(body.encode("ascii")).hex()
    return "0x" + "".join(
        ch.upper() if ch.isalpha() and int(digest[i], 16) >= 8 else ch
        for i, ch in enumerate(body)
    )


# --------------------------------------------------------------------------
# WP0.2 — addresses and deployment facts
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", ADDRESS_NAMES)
def test_every_address_is_checksummed(name: str) -> None:
    value = getattr(A, name)
    assert isinstance(value, str), name
    assert len(value) == 42 and value.startswith("0x"), name
    assert value == to_checksum(value), f"{name} is not EIP-55 checksummed"


def test_pinned_identities() -> None:
    """The two addresses a typo would silently redirect to someone else.

    NOTE the case of ``CURATOR``.  ``docs/curator_work_packages/wp0.md`` quotes
    it as ``0xcB0b0531e86A9aC36fa865ca8e3DbcCF047fDA91``, which is *not* EIP-55:
    the real checksum is ``…36Fa865cA8e3dbccF047FDA91``, and that is exactly the
    string Blockscout returns for ``created_contract.hash`` in
    ``creation_tx.json``.  The chain wins; the doc was retyped by hand.
    """
    assert A.CURATOR == "0xcB0b0531e86A9aC36Fa865cA8e3dbccF047FDA91"
    assert A.DEPLOYER == "0x047F606fD5b2BaA5f5C6c4aB8958E45CB6B054B7"


def test_the_contract_address_is_the_one_blockscout_reports_creating() -> None:
    """Recomputed, not remembered: checksum of the capture's own lowercase form."""
    tx = capture("creation_tx.json")
    assert A.CURATOR == to_checksum(tx["created_contract"]["hash"])
    assert A.CURATOR == tx["created_contract"]["hash"]


def test_the_deployment_facts_come_from_the_creation_tx() -> None:
    """Not remembered — read out of the committed creation-tx capture."""
    tx = capture("creation_tx.json")
    assert A.CREATION_BLOCK == int(tx["block_number"])
    assert A.CREATION_TX.lower() == str(tx["hash"]).lower()
    assert A.DEPLOYER == to_checksum(tx["from"]["hash"])
    # launchTime == the creation timestamp, and the contract's own getter
    # returned it in the batch round (pinned again in test_curator_captures).
    assert A.LAUNCH_TIME == 1786910327
    stamp = str(tx["timestamp"]).replace("Z", "+00:00")
    import datetime as _dt

    assert A.LAUNCH_TIME == int(_dt.datetime.fromisoformat(stamp).timestamp())


def test_the_deployer_is_re_vendored_not_imported() -> None:
    """Constants never cross dashboard data layers (PRD §5).

    The string is identical to surf's DEV_WALLET on purpose.  Importing it
    would make an edit to the surf dashboard -- explicitly out of scope for
    this build -- a curator regression.
    """
    source = inspect.getsource(A)
    assert "surf_addresses" not in source
    assert "from maxpane_dashboard.data.surf" not in source
    # The module imports nothing at all beyond __future__, so state that
    # directly rather than only banning the one spelling we thought of.
    imports = [
        line.strip()
        for line in source.splitlines()
        if re.match(r"\s*(from|import)\s", line)
    ]
    assert imports == ["from __future__ import annotations"], imports


def test_module_imports_nothing_but_stdlib() -> None:
    source = inspect.getsource(A)
    for banned in (
        "import httpx",
        "import asyncio",
        "from textual",
        "import requests",
        "import urllib",
    ):
        assert banned not in source


def test_addresses_are_distinct_and_labeled_addresses_is_the_union() -> None:
    values = [getattr(A, n).lower() for n in ADDRESS_NAMES]
    assert len(set(values)) == len(values), "duplicate address constant"
    assert set(A.LABELED_ADDRESSES) == {getattr(A, n) for n in ADDRESS_NAMES}


def test_known_labels_is_a_lowercase_keyed_allowlist() -> None:
    """An allowlist, never a blocklist: anything absent renders dimmed."""
    for key, label in A.KNOWN_LABELS.items():
        assert key == key.lower(), key
        assert key in {a.lower() for a in A.LABELED_ADDRESSES}
        assert label and isinstance(label, str)


# --------------------------------------------------------------------------
# WP0.3 — event topics
# --------------------------------------------------------------------------

_VENDORED_ABI = (
    Path(inspect.getfile(A)).resolve().parents[1]
    / "abis"
    / "curator"
    / "whitelist_curator.json"
)


def _event_signatures_from_source() -> set[str]:
    """Canonical event signatures parsed out of ``captures/source.sol``.

    Indexed-ness does not enter topic0; the *types* do.  Everything between an
    event's parentheses is split on commas and reduced to its leading type,
    with ``indexed`` dropped.
    """
    src = capture_text("source.sol")
    sigs = set()
    for match in re.finditer(r"\bevent\s+(\w+)\s*\(([^;]*?)\)\s*;", src, re.DOTALL):
        name, params = match.group(1), match.group(2)
        types = []
        for raw in params.split(","):
            tokens = [t for t in raw.split() if t != "indexed"]
            if tokens:
                types.append(tokens[0])
        sigs.add(f"{name}({','.join(types)})")
    return sigs


@pytest.mark.parametrize("name,preimage", sorted(A.TOPIC_PREIMAGES.items()))
def test_topic_matches_its_preimage(name: str, preimage: str) -> None:
    assert getattr(A, name) == keccak256_hex(preimage.encode("ascii"))


def test_preimage_map_covers_exactly_the_topic_constants() -> None:
    """A vendored hash with no preimage is unverifiable; a preimage with no
    constant is dead weight.  Both are failures."""
    names = {n for n in dir(A) if n.startswith("TOPIC_") and n != "TOPIC_PREIMAGES"}
    assert set(A.TOPIC_PREIMAGES) == names


def test_the_preimages_match_the_verified_source() -> None:
    """``docs/curator_game_mechanics.md`` quotes the hashes abbreviated;
    ``src/WhitelistCurator.sol`` is the authority.

    Parsed out of the capture rather than retyped, so an argument-list edit in
    a re-capture fails here instead of shipping a filter that matches nothing.
    """
    assert set(A.TOPIC_PREIMAGES.values()) == _event_signatures_from_source()


def test_the_topics_the_abi_declares_are_the_topics_vendored() -> None:
    """A third, independent derivation of the same six, off the vendored ABI."""
    abi = json.loads(_VENDORED_ABI.read_text(encoding="utf-8"))
    from_abi = {
        f"{e['name']}({','.join(i['type'] for i in e['inputs'])})"
        for e in abi
        if e["type"] == "event"
    }
    assert from_abi == set(A.TOPIC_PREIMAGES.values())


def test_the_topic_leading_bytes_cross_check_the_mechanics_doc() -> None:
    """The doc quotes these abbreviated.  A mismatch means a wrong preimage --
    and the *source* wins the argument, not the doc."""
    assert A.TOPIC_DEPOSITED.startswith("0xb8385097")
    assert A.TOPIC_FIRST_DEPOSIT.startswith("0xe5a1ae96")
    assert A.TOPIC_HOUR_SAVED.startswith("0xab7cfcae")
    assert A.TOPIC_SETTLED.startswith("0x0b88c5bd")
    assert A.TOPIC_RESCUED.startswith("0x8aec0ce3")
    assert A.TOPIC_LAUNCHED.startswith("0x1a3476a1")


@pytest.mark.parametrize("name", sorted(A.TOPIC_PREIMAGES))
def test_every_topic_is_lowercase_32_byte_hex(name: str) -> None:
    value = getattr(A, name)
    assert re.fullmatch(r"0x[0-9a-f]{64}", value), value


def test_every_topic_appears_in_the_captured_log_sweep_or_is_documented_absent() -> None:
    """Three of the six have never fired.  Say which, in the test."""
    seen = {l["topics"][0] for l in capture("tenderly_logs.json")["result"]}
    assert A.TOPIC_LAUNCHED in seen
    assert A.TOPIC_DEPOSITED in seen
    assert A.TOPIC_FIRST_DEPOSIT in seen
    # Never fired as of 2026-08-16 21:14 UTC.  Their decoders therefore ship
    # against synthetic rows whose *shape* comes from the ABI (see the plan's
    # "synthetic until captured" table).  If one of these starts appearing,
    # this test tells you a real fixture is now available.
    assert A.TOPIC_HOUR_SAVED not in seen
    assert A.TOPIC_SETTLED not in seen
    assert A.TOPIC_RESCUED not in seen


def test_the_creation_block_is_the_log_sweep_floor() -> None:
    """The backfill starts at CREATION_BLOCK; ``Launched`` is in that block."""
    logs = capture("tenderly_logs.json")["result"]
    launched = [l for l in logs if l["topics"][0] == A.TOPIC_LAUNCHED]
    assert len(launched) == 1
    assert int(launched[0]["blockNumber"], 16) == A.CREATION_BLOCK
    assert min(int(l["blockNumber"], 16) for l in logs) == A.CREATION_BLOCK


def test_the_announce_channel_is_labeled_because_it_is_on_the_list() -> None:
    """Not a surf import — a fact of *this* contract's history.

    The announce EOA made deposit #1 (0.05 ETH at 19 975 bps, block 25 769 888),
    so it appears in the leaderboard and the activity feed.  Labelling it is the
    allowlist doing its job.
    """
    logs = capture("tenderly_logs.json")["result"]
    deposits = [l for l in logs if l["topics"][0] == A.TOPIC_DEPOSITED]
    first = min(
        deposits, key=lambda l: (int(l["blockNumber"], 16), int(l["logIndex"], 16))
    )
    assert "0x" + first["topics"][1][-40:] == A.ANNOUNCE.lower()
    assert A.ANNOUNCE.lower() in A.KNOWN_LABELS
