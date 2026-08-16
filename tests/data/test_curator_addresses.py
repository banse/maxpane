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


# --------------------------------------------------------------------------
# WP0.4 — the selector table
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name,preimage", sorted(A.SELECTOR_PREIMAGES.items()))
def test_selector_matches_its_preimage(name: str, preimage: str) -> None:
    assert getattr(A, name) == keccak256_hex(preimage.encode("ascii"))[:10]


@pytest.mark.parametrize("name", sorted(A.SELECTOR_PREIMAGES))
def test_every_selector_is_lowercase_4_byte_hex(name: str) -> None:
    assert re.fullmatch(r"0x[0-9a-f]{8}", getattr(A, name)), name


def test_every_selector_has_a_preimage_and_a_word_count_and_vice_versa() -> None:
    names = {n for n in dir(A) if n.startswith("SEL_")}
    assert set(A.SELECTOR_PREIMAGES) == names
    assert set(A.VIEW_RETURN_WORDS) == names


def test_the_selector_signatures_are_declared_by_the_verified_source() -> None:
    """No invented view.  Every preimage names something ``source.sol`` has."""
    src = capture_text("source.sol")
    for const, sig in A.SELECTOR_PREIMAGES.items():
        fname = sig.split("(")[0]
        declared = re.search(
            rf"\b(function|public\s+(constant|immutable)?\s*\w*\s*)\b.*\b{re.escape(fname)}\b",
            src,
        )
        assert declared, f"{const}: source.sol declares no {fname}"


def test_every_parameterless_selector_appears_in_the_captured_batch() -> None:
    """The cross-check that makes the table trustworthy without a network.

    ``captures/batch.json`` is the real 21-call round that publicnode answered.
    Every parameterless selector this module vendors must be one of those 21,
    and all 21 must be accounted for -- an unaccounted selector in the capture
    is a view the research used and this module forgot.
    """
    sent = {c["params"][0]["data"] for c in capture("batch.json")}
    assert len(sent) == 21
    vendored = {
        getattr(A, n) for n, p in A.SELECTOR_PREIMAGES.items() if p.endswith("()")
    }
    assert vendored == sent, (
        f"vendored-not-captured: {sorted(vendored - sent)}; "
        f"captured-not-vendored: {sorted(sent - vendored)}"
    )


def test_the_hour_boundary_views_table_agrees_with_the_recomputation() -> None:
    """``hour_boundary_h1_h2.json`` carries its own id → selector → signature
    table.  It is a *cross-check*, not an authority; recomputing every row from
    its signature is what makes quoting it safe."""
    views = capture("hour_boundary_h1_h2.json")["views"]
    assert len(views) == 21
    for row in views:
        assert row["selector"] == keccak256_hex(row["signature"].encode("ascii"))[:10]
    assert {row["selector"] for row in views} == {
        getattr(A, n) for n, p in A.SELECTOR_PREIMAGES.items() if p.endswith("()")
    }


def test_the_two_views_that_both_returned_zero_are_told_apart_by_hash() -> None:
    """``isSettled()`` and ``ethNeededThisHour()`` both answered 0x0 at capture
    (not settled; grace, so nothing is needed).  Positional reasoning over
    ``results.json`` therefore cannot distinguish them and must not be used --
    the recomputed hash is the only discriminator, and this test is the record
    that the question was asked."""
    assert A.SEL_IS_SETTLED != A.SEL_ETH_NEEDED_THIS_HOUR
    idx = {c["params"][0]["data"]: c["id"] for c in capture("batch.json")}
    results = {r["id"]: r["result"] for r in capture("results.json")}
    assert int(results[idx[A.SEL_IS_SETTLED]], 16) == 0
    assert int(results[idx[A.SEL_ETH_NEEDED_THIS_HOUR]], 16) == 0


def test_the_multi_word_views_are_declared_with_their_word_counts() -> None:
    """A 2- or 3-word return decoded as 1 word silently drops fields."""
    assert A.VIEW_RETURN_WORDS["SEL_LAST_ACTIVE_HOUR"] == 2
    assert A.VIEW_RETURN_WORDS["SEL_STATS"] == 3
    assert A.VIEW_RETURN_WORDS["SEL_FIRST_HOUR_OF"] == 2
    assert A.VIEW_RETURN_WORDS["SEL_IS_SETTLED"] == 1


def test_the_word_counts_are_recomputed_from_the_verified_source() -> None:
    """Not remembered.  ``lastActiveHour() -> (hour, total)`` and
    ``firstHourOf() -> (hour, hasJoined)`` are the two a scalar decode would
    silently truncate; public state variables and constants have no ``returns``
    clause at all and are one word by definition."""
    src = capture_text("source.sol")
    checked_multi = 0
    for const, sig in A.SELECTOR_PREIMAGES.items():
        fname = sig.split("(")[0]
        match = re.search(
            rf"function\s+{re.escape(fname)}\s*\([^)]*\)[^{{;]*?returns\s*\(([^)]*)\)",
            src,
        )
        if match is None:
            # A public immutable/constant/state variable: its generated getter
            # returns exactly one word.
            assert A.VIEW_RETURN_WORDS[const] == 1, const
            continue
        expected = len([p for p in match.group(1).split(",") if p.strip()])
        assert A.VIEW_RETURN_WORDS[const] == expected, const
        checked_multi += expected > 1
    assert checked_multi == 3, "stats, lastActiveHour and firstHourOf"


def test_the_bool_returning_view_is_declared_as_a_bool() -> None:
    """``isSettled()`` returns ``bool``, not ``uint256``.  A decoder that reads
    it as an int and a manager that stores it as one both work -- until
    ``settled == 0`` gets confused with ``settled is None``."""
    assert A.VIEW_RETURN_TYPES["SEL_IS_SETTLED"] == ("bool",)
    assert A.VIEW_RETURN_TYPES["SEL_FIRST_HOUR_OF"] == ("uint256", "bool")
    assert A.VIEW_RETURN_TYPES["SEL_DEPLOYER"] == ("address",)
    assert set(A.VIEW_RETURN_TYPES) == set(A.SELECTOR_PREIMAGES)
    for const, types in A.VIEW_RETURN_TYPES.items():
        assert len(types) == A.VIEW_RETURN_WORDS[const], const


def test_the_three_ordered_tuples_are_the_batch_contract() -> None:
    """WP2 sends these in order and decodes positionally.

    A reorder is a silent field swap, which is why the *order* test belongs to
    WP2.4 (against ``VIEW_RETURN_WORDS``): reordering here leaves this suite
    green on purpose, and the WP0 hand-off says so.
    """
    for tup in (A.FAST_VIEW_SELECTORS, A.ONCE_VIEW_SELECTORS, A.WALLET_VIEW_SELECTORS):
        assert isinstance(tup, tuple) and tup
        for name, selector in tup:
            assert getattr(A, name) == selector
            assert name in A.VIEW_RETURN_WORDS

    fast = {n for n, _ in A.FAST_VIEW_SELECTORS}
    once = {n for n, _ in A.ONCE_VIEW_SELECTORS}
    wallet = {n for n, _ in A.WALLET_VIEW_SELECTORS}
    cross = {n for n, _ in A.CROSS_CHECK_VIEW_SELECTORS}
    assert fast.isdisjoint(once) and fast.isdisjoint(wallet) and once.isdisjoint(wallet)
    assert cross.isdisjoint(fast | once | wallet)
    assert len(fast) == 8
    assert len(once) == 10
    assert len(wallet) == 6
    assert len(cross) == 3
    # The three batched groups reconstruct the captured 21-call round exactly.
    assert len(fast | once | cross) == 21
    for name in wallet:
        assert not A.SELECTOR_PREIMAGES[name].endswith("()")
    for name in fast | once | cross:
        assert A.SELECTOR_PREIMAGES[name].endswith("()")


def test_the_fast_tier_is_the_eight_views_the_prd_names() -> None:
    assert {n for n, _ in A.FAST_VIEW_SELECTORS} == {
        "SEL_IS_SETTLED",
        "SEL_CURRENT_HOUR",
        "SEL_CURRENT_HOUR_TOTAL",
        "SEL_ETH_NEEDED_THIS_HOUR",
        "SEL_TIME_LEFT_IN_HOUR",
        "SEL_LAST_ACTIVE_HOUR",
        "SEL_EARLY_MULTIPLIER_BPS",
        "SEL_STATS",
    }


def test_the_once_tier_is_the_eight_immutables_plus_the_constant_and_deployer() -> None:
    """Read live, never hardcoded (CLAUDE.md).  The eight ``immutable`` config
    values, ``POINTS_PER_ETH`` (a ``constant``) and ``deployer``."""
    assert {n for n, _ in A.ONCE_VIEW_SELECTORS} == {
        "SEL_LAUNCH_TIME",
        "SEL_HOURLY_THRESHOLD",
        "SEL_GRACE_PERIOD",
        "SEL_HOUR_DURATION",
        "SEL_MIN_DEPOSIT",
        "SEL_MIN_ESCALATION",
        "SEL_CREDIT_CAP",
        "SEL_FIRST_JUDGED_HOUR",
        "SEL_POINTS_PER_ETH",
        "SEL_DEPLOYER",
    }


def test_the_cross_check_selectors_read_the_same_numbers_stats_returns() -> None:
    """``totalVolume``/``totalContributors``/``totalTxCount`` are a *different*
    storage read of ``stats()``'s three words.  That is the whole value of the
    slow-tier cross-check, so the three are their own group rather than being
    lumped into ``once``."""
    assert {n for n, _ in A.CROSS_CHECK_VIEW_SELECTORS} == {
        "SEL_TOTAL_VOLUME",
        "SEL_TOTAL_CONTRIBUTORS",
        "SEL_TOTAL_TX_COUNT",
    }


def test_the_wallet_tier_reads_first_hour_of_and_never_the_raw_struct() -> None:
    """H6: ``contributors(address)`` carries a ``firstHour + 1`` offset.
    ``firstHourOf()`` un-shifts it and returns ``(hour, hasJoined)``.  The raw
    struct getter is deliberately **not** vendored, so no client can reach it."""
    assert {n for n, _ in A.WALLET_VIEW_SELECTORS} == {
        "SEL_POINTS_OF",
        "SEL_WEIGHT_OF",
        "SEL_CONTRIBUTED_BY",
        "SEL_TX_COUNT_OF",
        "SEL_REQUIRED_NEXT",
        "SEL_FIRST_HOUR_OF",
    }
    assert "contributors(address)" not in set(A.SELECTOR_PREIMAGES.values())


def test_preview_points_is_vendored_but_batched_with_nothing() -> None:
    """Plan amendment A2: the 21-call round holds only parameterless views, so
    the sqrt curve has no onchain witness.  WP1.6 captures one; the selector has
    to exist before it can.  It takes a ``uint256``, so it is *not* a member of
    any ordered parameterless tuple -- adding it there would shift every
    positional decode by one."""
    assert A.SELECTOR_PREIMAGES["SEL_PREVIEW_POINTS"] == "previewPoints(uint256)"
    assert A.SEL_PREVIEW_POINTS not in {
        c["params"][0]["data"] for c in capture("batch.json")
    }
    batched = {
        n
        for tup in (
            A.FAST_VIEW_SELECTORS,
            A.ONCE_VIEW_SELECTORS,
            A.CROSS_CHECK_VIEW_SELECTORS,
            A.WALLET_VIEW_SELECTORS,
        )
        for n, _ in tup
    }
    assert "SEL_PREVIEW_POINTS" not in batched


def test_no_state_changing_selector_is_vendored() -> None:
    """Read-only by hard constraint.  ``deposit()``, ``settle()`` and
    ``rescue()`` have selectors; this module must not know them, so no curator
    module can accidentally encode one."""
    for banned in ("deposit()", "settle()", "rescue()"):
        assert banned not in set(A.SELECTOR_PREIMAGES.values())
        banned_sel = keccak256_hex(banned.encode("ascii"))[:10]
        assert banned_sel not in {
            getattr(A, n) for n in A.SELECTOR_PREIMAGES
        }, f"{banned} selector is vendored"
