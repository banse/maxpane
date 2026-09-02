"""pool4 — the pure layer.  Selectors, topics, the discovery gates, the maths.

This is WP3 of ``docs/surf_pool4_implementation_plan.md``.  Everything here is
a **total function over already-fetched bytes**: no I/O, no clock, no Textual,
no ``httpx``.  ``tests/data/test_surf_pool4.py`` proves that with an AST walk
rather than asserting it in prose, because a comment cannot fail.

Three things in this module are load-bearing enough to say once, at the top.

**1. The permission flag word is ``0x2840``, and it is a security gate.**

The hook address ends ``6840``.  The visible ``840`` is a *mined vanity tail*;
the Uniswap v4 permission field is the **low 14 bits**, and
``0x6840 & 0x3FFF == 0x2840``.  Reading the tail as the field silently drops
``BEFORE_INITIALIZE``.  Both failure modes are live and both are captured as
committed attacks:

* ``low14 == 0x840`` — the constant every version of the plan, the PRD and the
  mechanics doc originally mandated — **rejects the real hook**.  pool4 would
  never be discovered, on any chain, ever.
  (``announce_adversarial_flag_mismatch.json``.)
* ``low14 & 0x840`` — a subset test — **accepts a hook that does not gate pool
  initialisation**, and accepts one that also sets ``AFTER_SWAP_RETURNS_DELTA``
  and can therefore take value out of the swap itself.
  (``announce_adversarial_returns_delta.json``.)

So :data:`POOL4_REQUIRED_FLAGS` is all three bits and :func:`has_pool4_flags`
is an **equality** test.  ``getHookPermissions()`` is read as a *second,
independent* source that must agree with the address's own bits
(:func:`decode_hook_permissions`), because the address is asserted by whoever
mined it and the contract's answer is asserted by the contract.

**2. An ``eth_call`` that did not error is not a getter that answered.**

``eth_call`` to an address with no code returns ``"0x"`` and **no error**
(``rpc_error_states.json``, probe ``call_to_an_empty_address``).  A fingerprint
gate that treats "the call succeeded" as "the getter answered" adopts an empty
address.  :func:`answered` is the one place that distinction lives, and every
gate goes through it.

**3. The channel is attacker-writable, so provenance runs before arithmetic and
arithmetic runs before the network.**

:func:`candidate_addresses` reads **self-posts only** (``from == to ==
ANNOUNCE``): a reply or an inbound stranger tx carrying a perfectly-formed hook
address yields nothing at all.  Then :func:`triaged_candidates` and
:func:`flagged_candidates` are pure arithmetic on the address, so a post
carrying twenty decoys costs **one** ``eth_call`` round rather than twenty --
a discovery path that verifies first and filters second turns the announce
channel into an RPC amplifier.

The announce address and the expected token are **parameters, never imports**:
``data/surf_addresses.py`` is outside this module's frozen import boundary
(plan §0.5), and the caller that has a transport is the caller that has an
address book.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping, Sequence

from maxpane_dashboard.data.evm_abi import strip0x
from maxpane_dashboard.data.keccak import keccak256, keccak256_text
from maxpane_dashboard.data.surf_models import (
    POOL4_COUNTER_STATES,
    POOL4_DISCOVERY_SOURCES,
    POOL4_DISCOVERY_STATES,
    POOL4_FLOW_SIDES,
    POOL4_NETWORKS,
    Pool4Discovery,
    Pool4DistributorState,
    Pool4DripperState,
    Pool4FlowEvent,
    Pool4HookState,
    Pool4VaultState,
)
from maxpane_dashboard.data.surf_v4 import pool_state_slots

__all__ = [
    # selectors / topics
    "selector",
    "topic0",
    "HOOK_SIGNATURES",
    "HOOK_SELECTORS",
    "VAULT_SIGNATURES",
    "VAULT_SELECTORS",
    "DRIPPER_SIGNATURES",
    "DRIPPER_SELECTORS",
    "DISTRIBUTOR_SIGNATURES",
    "DISTRIBUTOR_SELECTORS",
    "ERC20_SIGNATURES",
    "ERC20_SELECTORS",
    "SEL_EXTSLOAD",
    "EVENT_SIGNATURES",
    "UNRESOLVED_TOPIC_OPERANDS",
    "TOPIC0",
    "TOPIC_FEE_COLLECTED",
    "TOPIC_CLAIMS_SETTLED",
    "TOPIC_FEES_WITHDRAWN",
    "TOPIC_ACCRUAL",
    "TOPIC_POOL_RESERVE",
    "TOPIC_BACKSTOP",
    # flags
    "HOOK_FLAG_MASK",
    "HOOK_FLAG_BEFORE_INITIALIZE",
    "HOOK_FLAG_AFTER_INITIALIZE",
    "HOOK_FLAG_BEFORE_ADD_LIQUIDITY",
    "HOOK_FLAG_AFTER_ADD_LIQUIDITY",
    "HOOK_FLAG_BEFORE_REMOVE_LIQUIDITY",
    "HOOK_FLAG_AFTER_REMOVE_LIQUIDITY",
    "HOOK_FLAG_BEFORE_SWAP",
    "HOOK_FLAG_AFTER_SWAP",
    "HOOK_FLAG_BEFORE_DONATE",
    "HOOK_FLAG_AFTER_DONATE",
    "HOOK_FLAG_BEFORE_SWAP_RETURNS_DELTA",
    "HOOK_FLAG_AFTER_SWAP_RETURNS_DELTA",
    "HOOK_FLAG_AFTER_ADD_LIQUIDITY_RETURNS_DELTA",
    "HOOK_FLAG_AFTER_REMOVE_LIQUIDITY_RETURNS_DELTA",
    "HOOK_PERMISSION_BITS",
    "POOL4_REQUIRED_FLAGS",
    "HOOK_TRIAGE_FLAGS",
    "address_flag_word",
    "has_pool4_flags",
    "is_hook_shaped",
    "decode_hook_permissions",
    # provenance / discovery
    "ADDRESS_RE",
    "checksum_address",
    "extract_addresses",
    "is_self_post",
    "self_post_addresses",
    "calldata_text",
    "reestablish_provenance",
    "candidate_addresses",
    "docs_candidate_addresses",
    "triaged_candidates",
    "flagged_candidates",
    "FINGERPRINT_GATES",
    "answered",
    "fingerprint_verdict",
    "adjudicate_candidates",
    "discovery_verdict",
    "ranked_discovery",
    "discovery_source_word",
    # calldata
    "encode_getter",
    "encode_balance_of",
    "encode_convert_to_assets",
    "encode_extsload",
    "pool_state_calls",
    # decoders
    "decode_hook_state",
    "decode_backstop",
    "SHARE_PRICE_CALL",
    "decode_vault_state",
    "decode_distributor_state",
    "decode_dripper_state",
    "decode_flow_events",
    "reserve_series",
    "COUNTER_SUM_FIELDS",
    "empty_accumulator",
    "accumulate_counters",
    "accumulator_covers",
    "reconcile_counters",
    "counter_verdict",
    "logs_reach_genesis",
    "TOPIC_OWNERSHIP_TRANSFERRED",
    # maths
    "measured_split",
    "POOL4_NO_DECAY_MIN_WEI",
    "is_no_decay",
    "bonding_bps",
    "reward_leg_split",
    "split_drift_bps",
    "floor_distance",
    "floor_distance_pct",
    "burned_supply_pct",
    "backlog_days",
    "implied_apr_pct",
    "share_price_delta_pct",
    "unsettled_legs",
    "whole_share_units",
    "vault_shares",
    "backstop_centred",
]

WEI = 10 ** 18

# The closed vocabularies are *imported*, and the members this module produces
# are looked up out of them rather than retyped (amendment A5).  Five packages
# code against one spelling of ``"not-discovered"``; a sixth hand-typed copy is
# how a payload key silently stops matching the widget that renders it.
_STATE_NOT_DISCOVERED, _STATE_ADOPTED, _STATE_REJECTED = POOL4_DISCOVERY_STATES
(_COUNTER_RECONCILED, _COUNTER_MISMATCH,
 _COUNTER_WINDOW_LIMITED, _COUNTER_UNCHECKED) = POOL4_COUNTER_STATES
_SIDE_BUY, _SIDE_SELL = POOL4_FLOW_SIDES


# ---------------------------------------------------------------------------
# Selectors — derived from signatures, never pasted
# ---------------------------------------------------------------------------
#
# Every name below is transcribed from ``docs/imd_pool4_mechanics.md``'s
# *Recovered interface* table, which was itself recovered from ``PUSH4``
# selectors in **unverified** bytecode plus Openchain lookups.  The four-byte
# words are *computed* from those signature strings with this repo's own
# keccak rather than pasted, so a transposed nibble cannot ship, and three of
# them are independently confirmed by the committed captures:
# ``token()`` == ``0xfc0c546a`` and ``bond()`` == ``0x64c9ec6f`` appear in
# ``rpc_error_states.json``'s live probes, and ``getHookPermissions()`` ==
# ``0xc4e833ce`` in ``hook_flags_reference.json``.


def selector(signature: str) -> str:
    """The 4-byte function selector for a Solidity signature."""
    return "0x" + keccak256_text(signature).hex()[:8]


def topic0(signature: str) -> str:
    """The 32-byte event topic0 for a Solidity event signature."""
    return "0x" + keccak256_text(signature).hex()


#: The hook's recovered getter set.  ``getHookPermissions()`` is the standard
#: v4 hook member and is the corroborating source for the flag word.
HOOK_SIGNATURES: dict[str, str] = {
    # --- state ---
    "token": "token()",
    "poolManager": "poolManager()",
    "owner": "owner()",
    "burnSink": "burnSink()",
    "rewardsRecipient": "rewardsRecipient()",
    "backstop": "backstop()",
    "poolId": "poolId()",
    "poolKey": "poolKey()",
    "marketOpen": "marketOpen()",
    "rebalanceEnabled": "rebalanceEnabled()",
    # --- config ---
    "BPS_DENOMINATOR": "BPS_DENOMINATOR()",
    "rewardShareBps": "rewardShareBps()",
    "lpFee": "lpFee()",
    "capFloor": "capFloor()",
    # Mainnet only, recovered from bytecode: neither exists on Sepolia and
    # neither is in any public signature database.  Computed here from the
    # docs' own vocabulary and confirmed against the live selectors --
    # ``0x55e62941`` and ``0xdb445ee8``.
    "capDecayTokensPerDay": "capDecayTokensPerDay()",
    "inventoryCap": "inventoryCap()",
    "keeperReward": "keeperReward()",
    # --- position ---
    "tickSpacing": "tickSpacing()",
    "tickLower": "tickLower()",
    "tickUpper": "tickUpper()",
    "refTick": "refTick()",
    "currentTick": "currentTick()",
    "currentSqrtPriceX96": "currentSqrtPriceX96()",
    "positionLiquidity": "positionLiquidity()",
    "ethInPool": "ethInPool()",
    "tokensInPool": "tokensInPool()",
    # --- counters ---
    "totalBurned": "totalBurned()",
    "totalRewarded": "totalRewarded()",
    "totalFeeToken": "totalFeeToken()",
    "retainedEth": "retainedEth()",
    "lastClaimBlock": "lastClaimBlock()",
    # --- the corroborating permission source ---
    "getHookPermissions": "getHookPermissions()",
}
HOOK_SELECTORS: dict[str, str] = {k: selector(v) for k, v in HOOK_SIGNATURES.items()}

#: ``StakedIMD`` — Solady ``ERC4626`` + ``Ownable``, **verified source**.
VAULT_SIGNATURES: dict[str, str] = {
    "asset": "asset()",
    "owner": "owner()",
    "paused": "paused()",
    "totalAssets": "totalAssets()",
    "totalSupply": "totalSupply()",
    "name": "name()",
    "symbol": "symbol()",
    "decimals": "decimals()",
    "convertToAssets": "convertToAssets(uint256)",
}
VAULT_SELECTORS: dict[str, str] = {k: selector(v) for k, v in VAULT_SIGNATURES.items()}

#: ``RewardDripper`` — **verified source**.  ``vault()`` lives here and nowhere
#: else: the hook has no vault getter (plan amendment A3), so the path is
#: ``hook.rewardsRecipient()`` -> RewardDripper -> ``dripper.vault()``.  A vault
#: field on the hook would invite a producer to fill it by scraping a page,
#: which is the one way this address must never be obtained.
DRIPPER_SIGNATURES: dict[str, str] = {
    "imd": "imd()",
    "vault": "vault()",
    "owner": "owner()",
    "dripRatePerSecond": "dripRatePerSecond()",
    "maxCatchupSeconds": "maxCatchupSeconds()",
    "minDripAmount": "minDripAmount()",
    "keeperReward": "keeperReward()",
    "lastDripAt": "lastDripAt()",
    "drippable": "drippable()",
    "canDrip": "canDrip()",
}
DRIPPER_SELECTORS: dict[str, str] = {
    k: selector(v) for k, v in DRIPPER_SIGNATURES.items()
}

#: ``RewardDistributor`` -- **mainnet only, no Sepolia counterpart**, and the
#: reason the vault is three hops away there instead of two:
#: ``hook.rewardsRecipient()`` names *this*, and ``distributor.dripper()`` is
#: the hop the Sepolia-shaped two-hop walk does not make.
DISTRIBUTOR_SIGNATURES: dict[str, str] = {
    "stakingBps": "stakingBps()",
    "nftBps": "nftBps()",
    "dripper": "dripper()",
    "asset": "asset()",
    "owner": "owner()",
    "stakingEarned": "stakingEarned()",
    "bondingEarned": "bondingEarned()",
    "nftEarned": "nftEarned()",
    "heldBonding": "heldBonding()",
    "heldNft": "heldNft()",
}
DISTRIBUTOR_SELECTORS: dict[str, str] = {
    k: selector(v) for k, v in DISTRIBUTOR_SIGNATURES.items()
}

ERC20_SIGNATURES: dict[str, str] = {
    "totalSupply": "totalSupply()",
    "decimals": "decimals()",
    "symbol": "symbol()",
    "name": "name()",
    "balanceOf": "balanceOf(address)",
}
ERC20_SELECTORS: dict[str, str] = {k: selector(v) for k, v in ERC20_SIGNATURES.items()}

#: ``PoolManager.extsload(bytes32)`` — v4 has no ``slot0()``; pool state is raw
#: storage.  The slot derivation is ``data/surf_v4.pool_state_slots`` and is
#: **not** re-implemented here.
SEL_EXTSLOAD = selector("extsload(bytes32)")


# ---------------------------------------------------------------------------
# Event topics
# ---------------------------------------------------------------------------
#
# Nine of the twelve topic0s this module cares about have a known pre-image and
# are computed from it.  Three do not: a ~143,640-candidate keccak sweep found
# no name that hashes to them, so they are recorded as literals and **named for
# what their operands provably are, not for what they are called**.  Do not
# invent a signature string for them -- a guessed name that happens to be
# wrong would compute a topic0 that matches no log, and the panel would go
# quiet rather than red.

EVENT_SIGNATURES: dict[str, str] = {
    "OwnershipTransferred": "OwnershipTransferred(address,address)",
    "PoolInitialized": "PoolInitialized(uint160,int24)",
    "MarketOpened": "MarketOpened(uint128,uint256,uint256)",
    "RewardsRecipientUpdated": "RewardsRecipientUpdated(address,address)",
    "FeeCollected": "FeeCollected(uint256,uint256)",
    "ClaimsSettled": "ClaimsSettled(uint256,uint256,uint256)",
    "FeesWithdrawn": "FeesWithdrawn(address,uint256,uint256)",
    "KeeperRewardPaid": "KeeperRewardPaid(address,uint256)",
    "Rebalanced": "Rebalanced(int24)",
}

#: topic0 -> the operand shape the decoded log sets prove, for the three events
#: whose *name* is unknown.  The keys are transcribed hex, deliberately: there
#: is no pre-image to derive them from.
UNRESOLVED_TOPIC_OPERANDS: dict[str, str] = {
    # Emitted on a SELL.  Proven by tx 0x028d1448a9: toBurn + toRewards ==
    # amount sold minus the 1% fee, to the wei.
    "0x32afb9555b0493ac0021ef7f6b122197e9e58510e694383410f667ec76e4f0fa":
        "(uint128 liquidityRemoved, uint256 toBurn, uint256 toRewards, uint256 eth)",
    # Emitted on a BUY.  Proven by tx 0x841e5af58c: before - after == the IMD
    # the buyer received.
    "0xa66e3643af3b5a570ea09b8d485f206950ff1ee042471a211388199518f539a6":
        "(uint256 before, uint256 after)",
    # The new backstop position, emitted by rebalance().
    "0xe3966151f83ca37a8d733ac53f8f5122134c74fc747f8ea857c2ba5e49f68b73":
        "(int24, int24, uint128, uint256)",
}

TOPIC_ACCRUAL = "0x32afb9555b0493ac0021ef7f6b122197e9e58510e694383410f667ec76e4f0fa"
TOPIC_POOL_RESERVE = "0xa66e3643af3b5a570ea09b8d485f206950ff1ee042471a211388199518f539a6"
TOPIC_BACKSTOP = "0xe3966151f83ca37a8d733ac53f8f5122134c74fc747f8ea857c2ba5e49f68b73"

TOPIC_FEE_COLLECTED = topic0(EVENT_SIGNATURES["FeeCollected"])
TOPIC_CLAIMS_SETTLED = topic0(EVENT_SIGNATURES["ClaimsSettled"])
TOPIC_FEES_WITHDRAWN = topic0(EVENT_SIGNATURES["FeesWithdrawn"])

#: topic0 -> a human name.  Resolved entries carry their signature; the three
#: unresolved ones carry their operand shape prefixed ``UNRESOLVED``, so a
#: reader of a log dump can never mistake a shape for a signature.
TOPIC0: dict[str, str] = {
    **{topic0(sig): sig for sig in EVENT_SIGNATURES.values()},
    **{t: f"UNRESOLVED {shape}" for t, shape in UNRESOLVED_TOPIC_OPERANDS.items()},
}


# ---------------------------------------------------------------------------
# The permission-flag gate
# ---------------------------------------------------------------------------

#: The v4 permission field is the address's **low 14 bits**.
HOOK_FLAG_MASK = (1 << 14) - 1

HOOK_FLAG_BEFORE_INITIALIZE = 1 << 13
HOOK_FLAG_AFTER_INITIALIZE = 1 << 12
HOOK_FLAG_BEFORE_ADD_LIQUIDITY = 1 << 11
HOOK_FLAG_AFTER_ADD_LIQUIDITY = 1 << 10
HOOK_FLAG_BEFORE_REMOVE_LIQUIDITY = 1 << 9
HOOK_FLAG_AFTER_REMOVE_LIQUIDITY = 1 << 8
HOOK_FLAG_BEFORE_SWAP = 1 << 7
HOOK_FLAG_AFTER_SWAP = 1 << 6
HOOK_FLAG_BEFORE_DONATE = 1 << 5
HOOK_FLAG_AFTER_DONATE = 1 << 4
HOOK_FLAG_BEFORE_SWAP_RETURNS_DELTA = 1 << 3
HOOK_FLAG_AFTER_SWAP_RETURNS_DELTA = 1 << 2
HOOK_FLAG_AFTER_ADD_LIQUIDITY_RETURNS_DELTA = 1 << 1
HOOK_FLAG_AFTER_REMOVE_LIQUIDITY_RETURNS_DELTA = 1 << 0

#: ``getHookPermissions()`` returns the ``Hooks.Permissions`` struct as 14
#: ABI-encoded booleans, in this order, mapping onto bits 13..0.
HOOK_PERMISSION_BITS: tuple[tuple[str, int], ...] = (
    ("beforeInitialize", HOOK_FLAG_BEFORE_INITIALIZE),
    ("afterInitialize", HOOK_FLAG_AFTER_INITIALIZE),
    ("beforeAddLiquidity", HOOK_FLAG_BEFORE_ADD_LIQUIDITY),
    ("afterAddLiquidity", HOOK_FLAG_AFTER_ADD_LIQUIDITY),
    ("beforeRemoveLiquidity", HOOK_FLAG_BEFORE_REMOVE_LIQUIDITY),
    ("afterRemoveLiquidity", HOOK_FLAG_AFTER_REMOVE_LIQUIDITY),
    ("beforeSwap", HOOK_FLAG_BEFORE_SWAP),
    ("afterSwap", HOOK_FLAG_AFTER_SWAP),
    ("beforeDonate", HOOK_FLAG_BEFORE_DONATE),
    ("afterDonate", HOOK_FLAG_AFTER_DONATE),
    ("beforeSwapReturnDelta", HOOK_FLAG_BEFORE_SWAP_RETURNS_DELTA),
    ("afterSwapReturnDelta", HOOK_FLAG_AFTER_SWAP_RETURNS_DELTA),
    ("afterAddLiquidityReturnDelta", HOOK_FLAG_AFTER_ADD_LIQUIDITY_RETURNS_DELTA),
    ("afterRemoveLiquidityReturnDelta",
     HOOK_FLAG_AFTER_REMOVE_LIQUIDITY_RETURNS_DELTA),
)

#: **The gate.**  ``0x2840``.  Three bits, and the architecture is in all three:
#:
#: * ``beforeInitialize`` — nobody else can open a pool with this hook, so
#:   there is exactly one pool4 and the hook initialised it itself.
#: * ``beforeAddLiquidity`` — nobody else can LP, which is what lets the hook
#:   treat the position as its own balance sheet.
#: * ``afterSwap`` — it reacts *after* the swap settles.  Neither RETURNS_DELTA
#:   bit is set, so it cannot alter a swap's price or take a delta mid-swap.
#:
#: Confirmed against ``getHookPermissions()`` on all three Sepolia launch
#: hooks, each of which agrees bit for bit with its own address's low 14 bits.
POOL4_REQUIRED_FLAGS = (
    HOOK_FLAG_BEFORE_INITIALIZE
    | HOOK_FLAG_BEFORE_ADD_LIQUIDITY
    | HOOK_FLAG_AFTER_SWAP
)

#: **Triage, and never the gate.**  The swap-and-LP core: an address whose low
#: 14 bits carry both of these is *making a claim to be a v4 hook that gates
#: liquidity and reacts to swaps*, and is therefore worth adjudicating.  An
#: address that carries neither is ordinary channel noise -- the announce
#: channel's real history names the burn executor, the IMD token and the
#: channel itself, and none of those is an attack.
#:
#: This is the value ``0x840`` that the plan, the PRD and the mechanics doc all
#: mandated as the **adoption gate**, and as that it is catastrophic in both
#: directions (see the module docstring).  It survives here only as the triage
#: predicate for *which candidates get a verdict at all*, it costs no network
#: round trip, and ``test_the_triage_mask_is_not_the_gate`` pins the two apart.
HOOK_TRIAGE_FLAGS = HOOK_FLAG_BEFORE_ADD_LIQUIDITY | HOOK_FLAG_AFTER_SWAP


#: The only characters an address body may contain.  ``str.isascii()`` plus a
#: set membership rather than ``int(body, 16)``, and that difference is a fixed
#: bug rather than a style choice.
_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")


def _hex_body(addr: Any, length: int) -> str | None:
    """The lowercase hex body of ``addr``, or ``None`` if it is not one.

    **One helper, because two of them disagreed.**  ``address_flag_word`` used
    to validate with ``int(body, 16)`` while ``checksum_address`` hashed
    ``body.encode("ascii")``, and Python's ``int`` accepts every Unicode
    decimal digit that ``ascii`` refuses.  Forty FULLWIDTH DIGIT characters
    spelling ``…2840`` therefore produced ``address_flag_word() == 0x2840``,
    ``has_pool4_flags() == True`` and ``is_hook_shaped() == True`` -- while
    ``checksum_address`` raised ``UnicodeEncodeError`` on the same string, in a
    function whose docstring promises totality.

    ``ADDRESS_RE`` blocks this on the announce-channel path, so the gap is
    every path that does not go through the regex: an address decoded out of
    an RPC answer (:func:`_decoded_address`), an ``expected_token`` a caller
    supplies, and any address handed straight to :func:`fingerprint_verdict`.
    Each of those is a live entry point whose contract is totality, and the
    crash was reachable through them: the defect was first found on a
    cache-file path that has since been retired (see the tombstone below
    :func:`discovery_verdict`), but retiring that path removed one caller, not
    the class.
    """
    if not isinstance(addr, str):
        return None
    body = strip0x(addr.strip())
    if len(body) != length:
        return None
    if not body.isascii() or not set(body) <= _HEX_DIGITS:
        return None
    return body.lower()


def address_flag_word(addr: str | None) -> int | None:
    """The low 14 bits of a 20-byte address, or ``None`` if it is not one.

    Total: a malformed string, a short or **long** string, a non-ASCII string,
    a non-hex string and ``None`` all return ``None`` rather than raising.
    Third-party text reaches this.

    "Long" is not padding: a 64-nibble transaction hash must not acquire a flag
    word from its last fourteen bits, so the length test is equality and
    :func:`_hex_body` is where it lives, shared with
    :func:`checksum_address` so the two can never disagree about what an
    address is again.
    """
    body = _hex_body(addr, 40)
    if body is None:
        return None
    return int(body, 16) & HOOK_FLAG_MASK


def has_pool4_flags(addr: str | None) -> bool:
    """``True`` iff the address's low 14 bits **equal** :data:`POOL4_REQUIRED_FLAGS`.

    Equality, never ``&``.  A subset test admits a hook that also sets
    ``AFTER_SWAP_RETURNS_DELTA`` -- a materially different contract that can
    take value out of the swap itself.
    """
    return address_flag_word(addr) == POOL4_REQUIRED_FLAGS


def is_hook_shaped(addr: str | None) -> bool:
    """``True`` iff the address claims the swap-and-LP core (see :data:`HOOK_TRIAGE_FLAGS`).

    Triage only.  Every address that passes :func:`has_pool4_flags` also
    passes this, and passing this alone earns a *verdict*, never an adoption.
    """
    word = address_flag_word(addr)
    return word is not None and word & HOOK_TRIAGE_FLAGS == HOOK_TRIAGE_FLAGS


def decode_hook_permissions(raw: str | None) -> int | None:
    """The flag word ``getHookPermissions()`` asserts, or ``None`` if unread.

    The contract's own answer, decoded independently of the address, so the
    two can be required to agree.  An empty return (``"0x"``) is unread, not
    "no permissions" -- see :func:`answered`.
    """
    if not answered(raw):
        return None
    body = strip0x(raw)  # type: ignore[arg-type]
    if len(body) < 64 * len(HOOK_PERMISSION_BITS):
        return None
    word = 0
    for idx, (_name, bit) in enumerate(HOOK_PERMISSION_BITS):
        try:
            value = int(body[64 * idx: 64 * (idx + 1)], 16)
        except ValueError:
            return None
        if value:
            word |= bit
    return word


# ---------------------------------------------------------------------------
# Provenance — the first gate
# ---------------------------------------------------------------------------

#: A 20-byte address, and nothing that merely looks like one.
#:
#: The lookarounds are the guard, and each one has a committed attack behind
#: it.  Trailing: without ``(?![0-9a-fA-F])`` the first 40 nibbles of a 32-byte
#: tx hash parse as an address.  Leading: without ``(?<![0-9a-zA-Z])`` the tail
#: of a longer word does.  And the match must start at a literal ``0x``, so
#: ``0x`` + U+202E + 40 hex digits -- bidi overrides reorder what a reader
#: *sees* without changing the bytes -- yields no candidate at all rather than
#: a candidate whose rendered form is not its real form.
ADDRESS_RE = re.compile(r"(?<![0-9a-zA-Z])0x([0-9a-fA-F]{40})(?![0-9a-fA-F])")


def checksum_address(addr: str | None) -> str | None:
    """EIP-55 checksum an address, or ``None`` if it is not one.

    The checksum is defined over the *lowercase* hex digits, so a
    checksummed input round-trips.  Total over third-party text.
    """
    body = _hex_body(addr, 40)
    if body is None:
        return None
    digest = keccak256(body.encode("ascii")).hex()
    out = "".join(
        ch.upper() if ch.isalpha() and int(digest[i], 16) >= 8 else ch
        for i, ch in enumerate(body)
    )
    return "0x" + out


def _same_addr(a: Any, b: Any) -> bool:
    """Case-insensitive address comparison over possibly-hostile input."""
    if not isinstance(a, str) or not isinstance(b, str):
        return False
    return strip0x(a.strip()).lower() == strip0x(b.strip()).lower()


def extract_addresses(text: Any) -> list[str]:
    """Every 20-byte address in ``text``, EIP-55, in the order they appear.

    **The extraction, in one place**, and the second thing this module has had
    to hoist for the same reason: :func:`self_post_addresses` reads announce
    calldata, :func:`docs_candidate_addresses` reads a documentation page, and
    a second ``ADDRESS_RE`` caller that could drift is exactly how one half of
    the provenance gate ended up with no coverage.

    **Nothing is normalised, and this is where that bites hardest.**  No strip,
    no case fold, no NFKC, and above all no stripping of control characters:
    doing that turns the committed bidi row -- ``0x`` + U+202E + forty hex
    digits, which *renders* as one address and *is* another -- into a live
    ``0x2840``-shaped candidate.  A documentation page is HTML written by
    somebody else and gets the same suspicion as channel calldata.

    Total over hostile input: a non-string yields ``[]``.  Duplicates are kept
    here; callers that want them collapsed do so themselves, because "which
    addresses appear" and "which distinct addresses appear" are different
    questions.
    """
    if not isinstance(text, str):
        return []
    out: list[str] = []
    for match in ADDRESS_RE.finditer(text):
        checksummed = checksum_address(match.group(1))
        if checksummed is not None:
            out.append(checksummed)
    return out


def is_self_post(from_addr: Any, to_addr: Any, announce: str) -> bool:
    """``from == to == announce``, case-insensitively.  **The provenance rule.**

    One body, three callers -- :func:`self_post_addresses`, and through it
    :func:`candidate_addresses` and :func:`reestablish_provenance`.  It is a
    function rather than two inline comparisons because the last time this rule
    existed in one place with no separate name, half of it (``to_addr``) had no
    test coverage at all and deleting that half passed the whole suite.

    Case-insensitive because production needs it: ``surf_client`` lowercases
    both row addresses while ``surf_addresses.ANNOUNCE`` is EIP-55 checksummed,
    so the two sides never match byte for byte on a real row.

    ``to_addr`` being ``None`` -- a **contract creation** -- is a genuine
    ``False`` here and not an error.  It is "we looked and it is not a
    self-post", which is a different answer from "we could not look", and only
    the second should make a view fall back.
    """
    return _same_addr(from_addr, announce) and _same_addr(to_addr, announce)


def self_post_addresses(
    from_addr: Any,
    to_addr: Any,
    text: Any,
    announce: str,
) -> list[str]:
    """**The provenance rule, in one place.**  Addresses named by one self-post.

    ``[]`` unless ``from_addr == to_addr == announce`` case-insensitively, and
    then every 20-byte address :data:`ADDRESS_RE` finds in ``text``, EIP-55
    checksummed, in the order they appear.

    This exists as its own function because there are now **two** callers --
    :func:`candidate_addresses` over a cycle's feed rows, and
    :func:`reestablish_provenance` over a single fetched transaction -- and a
    second implementation of the rule is how the ``from_addr``/``to_addr``
    asymmetry happened the first time: one half of the gate had no coverage
    because no corpus exercised it, and deleting that half passed the whole
    suite.  One rule, one body, both callers.

    Total over hostile input: a non-string ``text``, a non-string address, a
    ``None`` and text that is markup all yield ``[]`` rather than raising.
    """
    if not is_self_post(from_addr, to_addr, announce):
        return []
    return extract_addresses(text)


def candidate_addresses(
    rows: Sequence[Mapping[str, Any]] | None,
    announce: str,
) -> list[str]:
    """Addresses named by announce-wallet **self-posts**, EIP-55, deduplicated.

    ``rows`` are ``SURF_ROW_KEYS["feed_items"]``-shaped dicts -- the shape the
    manager already produces -- and a row qualifies only when
    ``from_addr == to_addr == announce``, case-insensitively.  A community
    reply and an inbound tx from a stranger are **never** scanned, even when
    they carry a perfectly-formed, correctly-flagged hook address: the failure
    this prevents is rendering an attacker's contract as the protocol's, with
    the reader's own money decision behind it.

    Order-preserving, first spelling wins, and total: a row whose ``text`` is
    ``None``, whose text is markup, or which is not a mapping at all is
    skipped rather than raised on.
    """
    out: list[str] = []
    seen: set[str] = set()
    for row in rows or ():
        if not isinstance(row, Mapping):
            continue
        named = self_post_addresses(
            row.get("from_addr") if isinstance(row, Mapping) else None,
            row.get("to_addr"),
            row.get("text"),
            announce,
        )
        for addr in named:
            body = addr[2:].lower()
            if body in seen:
                continue
            seen.add(body)
            out.append(addr)
    return out


#: Field names a fetched transaction may use, in the order they are tried.
#: ``eth_getTransactionByHash`` and Blockscout's ``/transactions`` disagree
#: about spelling and about nesting; this is plumbing, and it is deliberately
#: the *only* thing that differs between the two shapes -- the rule that
#: decides is :func:`self_post_addresses` either way.
_TX_FROM_KEYS = ("from", "from_addr")
_TX_TO_KEYS = ("to", "to_addr")
_TX_DATA_KEYS = ("input", "raw_input", "data", "calldata")
_TX_HASH_KEYS = ("hash", "tx_hash", "transactionHash")
_TX_BLOCK_KEYS = ("blockNumber", "block_number", "block")


def _tx_field(tx: Mapping[str, Any], keys: Sequence[str]) -> Any:
    """The first present field, unwrapping Blockscout's ``{"hash": …}`` nesting."""
    for key in keys:
        if key not in tx:
            continue
        value = tx[key]
        if isinstance(value, Mapping):
            value = value.get("hash")
        if value is not None:
            return value
    return None


def calldata_text(data: Any) -> str | None:
    """A transaction's calldata as the text it was posted as, or ``None``.

    The announce channel is UTF-8 bytes in the ``input`` field of a
    zero-value self-transfer, so this is the whole decode.  ``None`` for
    absent, empty, non-hex, odd-length or non-UTF-8 calldata -- every one of
    which is an ordinary thing to fetch and none of which may raise.

    **Nothing is normalised.**  No strip, no case fold, no Unicode
    normalisation: :data:`ADDRESS_RE` must see the raw text, because
    normalising first is how a bidi-wrapped or markup-wrapped address becomes
    a candidate whose rendered form is not its real form.
    """
    if not isinstance(data, str):
        return None
    body = strip0x(data.strip())
    if not body or len(body) % 2:
        return None
    try:
        return bytes.fromhex(body).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None


def reestablish_provenance(
    tx: Mapping[str, Any] | None,
    announce: str,
    expected_addr: str,
    expected_tx_hash: str | None = None,
) -> tuple[bool, str]:
    """Does this **fetched transaction** prove ``expected_addr`` was announced?

    ``True`` only when the transaction is a self-post of the announce channel
    (``from == to == announce``) whose calldata names ``expected_addr``.

    **Why this exists.**  Provenance is the only gate an attacker cannot
    satisfy, and it is re-established every cycle from ``feed_items`` -- which
    keeps 25 rows against a channel running at ~2.55 days per post.  So about
    64 days after the hook is announced the self-post ages out of the window
    and a genuine adoption lapses to Sepolia.  Persisting the announcing
    transaction's **hash** and fetching that transaction lets provenance
    outlive the window.

    **The line this must not cross, and it is the whole design.**  Persisting
    the hash makes re-establishment *possible*, not *safe*.  A hash is a
    pointer to a credential, never a credential.  The chain is the authority;
    the cache only says where to look.  So:

    * the cache may supply a **transaction hash and nothing else**;
    * every question that decides -- is this a self-post, does its calldata
      name this address -- is recomputed here from the fetched transaction;
    * ``expected_addr`` is not trusted because the hash looked plausible.  It
      is the *claim under test*, and this function's answer is what makes it
      true or false.

    A cache that supplied a hash **and** an address, where the address was
    believed because the hash resolved, would be the persisted-adoption bypass
    wearing a new hat.  There is no parameter here that would let a caller do
    that: nothing but the fetched transaction can make this return ``True``.

    **What "from the chain" actually means here, stated plainly because the
    phrase promises more than the mechanism delivers.**  The transaction is read
    through an RPC endpoint, and *nothing recomputes* ``keccak(rlp(tx))`` to
    prove the returned content commits to the hash that was asked for.  A
    hostile endpoint can therefore return arbitrary content for any hash, and
    this function will believe it.  What is closed is the *cache*: an attacker
    who can write ``~/.maxpane/`` gains nothing, because the cache supplies only
    a pointer and every decision is recomputed from the fetched object.  What is
    not closed, and cannot be from inside this module, is the endpoint.  That
    limit is shared by every read in this repo; it is named here so a reader of
    "provenance re-established from the chain" knows which chain-shaped thing
    is being trusted.

    ``expected_tx_hash`` is a **redundant** guard.  The authoritative identity
    check is the client's, and belongs there: only the client knows which hash
    was *requested* -- this predicate is handed an answer, never the question --
    and only the client can answer ``None``.  A hash mismatch is a fact about
    the endpoint (confused, stale, or hostile), so its correct outcome is "we
    could not read", and the loudest thing this function can say is "not a
    self-post", which would report an outage as an attack.  The copy here fires
    only if a mismatched object reaches this far, and it says so in those
    terms.
    """
    if not isinstance(tx, Mapping):
        return False, "no transaction to check"

    if expected_tx_hash is not None:
        got = _tx_field(tx, _TX_HASH_KEYS)
        if not isinstance(got, str) or not _same_addr(got, expected_tx_hash):
            return (
                False,
                f"the endpoint returned transaction {got}, not the cited "
                f"{expected_tx_hash}",
            )

    # PENDING.  ``blockNumber: null`` is an unmined transaction -- a claim, not
    # a fact.  The specific risk is a self-post that is broadcast, cited, and
    # then dropped from the mempool, after which the dashboard would be resting
    # an adoption on a transaction that exists on no chain.
    #
    # Mined is required; a confirmation DEPTH deliberately is not.  A depth rule
    # would need a head block -- one more parameter, one more thing that can be
    # stale -- to prevent a failure whose consequence is milder than the one it
    # adds: a reorg that removes a cited post makes the next cycle's fetch come
    # back pending and the view lapse to Sepolia, which is visible, temporary
    # and self-correcting on the following tick. It would also delay a
    # legitimate adoption by N blocks at exactly the moment the view most wants
    # to show it. Failing towards "no mainnet yet" is the safe direction, so
    # cheap and correct wins over deep and slow.
    block = _tx_field(tx, _TX_BLOCK_KEYS)
    if block is None:
        return False, "the cited transaction is not mined yet"

    status = tx.get("status")
    result = tx.get("result")
    if (isinstance(status, str) and status.lower() in {"error", "failed", "0x0"}) or (
        isinstance(result, str) and result.lower() not in {"success", ""}
    ):
        # An explicit failure only.  A missing status is unknown, not failed --
        # ``eth_getTransactionByHash`` carries no status at all.
        return False, "the cited transaction did not succeed"

    from_addr = _tx_field(tx, _TX_FROM_KEYS)
    to_addr = _tx_field(tx, _TX_TO_KEYS)
    if not is_self_post(from_addr, to_addr, announce):
        # A distinct answer, deliberately.  ``to`` being absent is a CONTRACT
        # CREATION, and this is "we looked and it is not a self-post" -- not
        # "we could not look".  Collapsing it into the address answer below
        # would lose the difference A10 exists to keep.
        return False, f"the cited transaction is not a self-post ({from_addr} -> {to_addr})"

    named = self_post_addresses(
        from_addr, to_addr, calldata_text(_tx_field(tx, _TX_DATA_KEYS)), announce
    )
    if not named:
        return False, "the cited self-post names no address"
    if not any(_same_addr(a, expected_addr) for a in named):
        return (
            False,
            f"the cited self-post names {', '.join(named)} — not {expected_addr}",
        )
    return True, f"{expected_addr} is named by self-post {_tx_field(tx, _TX_HASH_KEYS)}"


def docs_candidate_addresses(text: Any) -> list[str]:
    """Candidate addresses from the project's own documentation page.

    **A deliberate widening of the trust surface, decided by the operator, and
    implemented exactly this wide and no wider.**  The announce channel has not
    named the mainnet hook, so automatic discovery correctly refuses under A27
    and the view would show SEPOLIA while mainnet is live.  The operator has
    chosen to accept ``pool4.imd.fun/docs`` as a **candidate** source.

    What that does and does not change:

    * **Candidates only.**  The full chain fingerprint runs afterwards,
      unchanged -- flag equality, the permission corroboration, ``token()``
      identity, four live getters.  Nothing about A27 relaxes.
    * **The persisted cache still nominates nothing.**  This is a third
      *candidate source*, not a second way to trust storage.
    * **The channel stays stronger and overrides.**  See
      :func:`ranked_discovery`: the two lists are ranked, never merged.
    * **It is disclosed, not hidden.**  The verdict carries
      ``"docs"`` so a docs-sourced adoption cannot render identically to a
      dev-signed one.  Disclosure is the mitigation, because prevention is not
      available: anyone who can edit that page can name a hook, a
      ``0x2840``-shaped address mines in ~20,000 tries, four of the five
      getters are pure liveness checks and ``token()`` is the candidate's own
      choice.

    The parser is :func:`extract_addresses` and nothing else -- **the same
    extraction the channel gets**, over the **raw** server-rendered HTML.  It is
    not stripped of control characters, not NFKC-normalised and not
    whitespace-collapsed first, and S16 is the reason: stripping control
    characters turns ``0x`` + U+202E + forty hex digits into a live
    ``0x2840``-shaped candidate whose rendered form is not its real form.  A
    docs page is HTML written by somebody else and earns exactly the suspicion
    channel calldata earns.

    Deduplicated and order-preserving, like the channel's list.
    """
    out: list[str] = []
    seen: set[str] = set()
    for addr in extract_addresses(text):
        body = addr[2:].lower()
        if body in seen:
            continue
        seen.add(body)
        out.append(addr)
    return out


def triaged_candidates(addrs: Iterable[str] | None) -> list[str]:
    """The candidates worth adjudicating — pure arithmetic, no round trip."""
    return [a for a in (addrs or ()) if is_hook_shaped(a)]


def flagged_candidates(addrs: Iterable[str] | None) -> list[str]:
    """The candidates that pass the flag gate — pure arithmetic, no round trip.

    This runs **before** any ``eth_call``.  A self-post carrying twenty
    address-shaped words costs one getter round, not twenty.
    """
    return [a for a in (addrs or ()) if has_pool4_flags(a)]


# ---------------------------------------------------------------------------
# Fingerprint — the second gate
# ---------------------------------------------------------------------------

#: The gate order, and the order a ``rejected`` detail names.
#:
#: ``token`` comes first among the getters deliberately: it is the identity
#: check, the one gate an otherwise perfectly hook-shaped contract fails when
#: it is somebody else's pool.  ``announce_adversarial_dead_getters.json``
#: pins that ordering choice -- a candidate that answers nothing is rejected
#: naming ``token``, because ``token`` is the first getter asked.
FINGERPRINT_GATES: tuple[str, ...] = (
    "flags",
    "permissions",
    "token",
    "rewardShareBps",
    "BPS_DENOMINATOR",
    "burnSink",
    "poolManager",
)

#: The getters that merely have to *answer*, in order, after ``token``.
_MUST_ANSWER: tuple[str, ...] = (
    "rewardShareBps",
    "BPS_DENOMINATOR",
    "burnSink",
    "poolManager",
)


def answered(raw: Any) -> bool:
    """``True`` only when a getter really answered.

    ``eth_call`` to an address with no code returns ``"0x"`` and **no error**
    (``rpc_error_states.json``).  So "the call did not error" is not "the
    getter answered", and a gate that conflates the two adopts an empty
    address.  An empty return is a **failed** fingerprint.
    """
    return isinstance(raw, str) and len(strip0x(raw.strip())) >= 64


def _decoded_address(raw: Any) -> str | None:
    if not answered(raw):
        return None
    body = strip0x(raw.strip())  # type: ignore[union-attr]
    return checksum_address(body[-40:])


def fingerprint_verdict(
    addr: str,
    answers: Mapping[str, Any] | None,
    expected_token: str,
) -> tuple[str, str]:
    """``(state, detail)`` for one candidate.  ``state`` is in ``POOL4_DISCOVERY_STATES``.

    ``"adopted"`` only when **all** of these hold:

    * the address's low 14 bits **equal** :data:`POOL4_REQUIRED_FLAGS`;
    * if ``answers`` carries ``getHookPermissions``, the contract's own flag
      word agrees with the address's -- a second, independent source;
    * ``token()``, ``rewardShareBps()``, ``BPS_DENOMINATOR()``, ``burnSink()``
      and ``poolManager()`` all *answered* (see :func:`answered`);
    * ``token()`` equals ``expected_token``.

    Anything less is ``"rejected"``, with a detail naming the **first** gate
    that failed, in :data:`FINGERPRINT_GATES` order.  ``"rejected"`` is a
    verdict, never a "try again": an unreadable candidate is not an adopted
    one, and the caller must not carry the address forward.
    """
    answers = answers or {}

    word = address_flag_word(addr)
    if word != POOL4_REQUIRED_FLAGS:
        shown = "not an address" if word is None else f"0x{word:04x}"
        return (
            _STATE_REJECTED,
            f"flags {shown} — pool4 needs 0x{POOL4_REQUIRED_FLAGS:04x} exactly",
        )

    if "getHookPermissions" in answers:
        claimed = decode_hook_permissions(answers.get("getHookPermissions"))
        if claimed is None:
            return _STATE_REJECTED, "permissions unread — the hook named no permissions"
        if claimed != word:
            return (
                _STATE_REJECTED,
                f"permissions 0x{claimed:04x} disagree with the address 0x{word:04x}",
            )

    token_raw = answers.get("token")
    if not answered(token_raw):
        return _STATE_REJECTED, "token unread — the candidate answered nothing"
    token = _decoded_address(token_raw)
    if not _same_addr(token, expected_token):
        return _STATE_REJECTED, f"token {token} is not the known token"

    for name in _MUST_ANSWER:
        if not answered(answers.get(name)):
            return _STATE_REJECTED, f"{name} unread — the candidate answered nothing"

    return _STATE_ADOPTED, f"adopted {addr} — flags, token and four getters agree"


def discovery_verdict(
    rows: Sequence[Mapping[str, Any]] | None,
    announce: str,
    expected_token: str,
    answers_by_addr: Mapping[str, Mapping[str, Any]] | Any = None,
    network: str | None = None,
    source_tx_by_addr: Mapping[str, str] | None = None,
) -> Pool4Discovery:
    """Adjudicate an announce corpus.  Pure over already-fetched answers.

    The order is provenance -> triage -> flags -> getters, and it is the order
    for a reason: everything before the last step is arithmetic on strings the
    caller already has, so **the number of ``eth_call`` rounds is the number of
    flag-passing candidates**, not the number of address-shaped words in a
    post.

    ``answers_by_addr`` is looked up per flag-passing candidate only.  It may
    be any mapping-like object; passing one that raises on an unexpected key
    is how ``test_the_nineteen_decoys_never_reach_a_getter`` proves the
    ordering rather than asserting it.

    Outcomes:

    * no *hook-shaped* candidate at all -> ``"not-discovered"``.  This is the
      day-one path and the one that actually runs: the announce channel's
      complete history names the burn executor, the IMD token and the channel
      itself, and none of those is a rejection.
    * hook-shaped candidates but none flag-equal -> ``"rejected"``, naming
      flags.
    * a flag-equal candidate that fails a getter gate -> ``"rejected"``,
      naming that gate.  First flag-equal candidate to be adopted wins.
    """
    return adjudicate_candidates(
        candidate_addresses(rows, announce), expected_token,
        answers_by_addr, network, source_tx_by_addr, origin="self-post",
    )


def adjudicate_candidates(
    candidates: Sequence[str] | None,
    expected_token: str,
    answers_by_addr: Mapping[str, Mapping[str, Any]] | Any = None,
    network: str | None = None,
    source_tx_by_addr: Mapping[str, str] | None = None,
    origin: str = "self-post",
) -> Pool4Discovery:
    """Triage -> flags -> getters over one candidate list.  **One body.**

    Both candidate sources adjudicate through here, so the docs path cannot
    acquire a weaker gate than the channel path by drifting: there is only one
    ordering, one flag test and one fingerprint call.  ``origin`` is a word for
    the *detail line* -- it changes what a rejection says it looked at, never
    what it checks.
    """
    candidates = list(candidates or ())
    triaged = triaged_candidates(candidates)
    if not triaged:
        return Pool4Discovery(
            network=network,
            state=_STATE_NOT_DISCOVERED,
            detail=(
                f"no hook-shaped address in {len(candidates)} {origin} "
                f"address{'' if len(candidates) == 1 else 'es'}"
            ),
        )

    flagged = flagged_candidates(triaged)
    if not flagged:
        state, detail = fingerprint_verdict(triaged[0], {}, expected_token)
        return Pool4Discovery(
            network=network,
            state=state,
            detail=detail,
            source_tx_hash=(source_tx_by_addr or {}).get(triaged[0]),
        )

    first: tuple[str, str, str] | None = None
    for addr in flagged:
        answers = None
        if answers_by_addr is not None:
            try:
                answers = answers_by_addr[addr]
            except (KeyError, TypeError):
                try:
                    answers = answers_by_addr[addr.lower()]
                except (KeyError, TypeError):
                    answers = None
        state, detail = fingerprint_verdict(addr, answers, expected_token)
        if state == _STATE_ADOPTED:
            return Pool4Discovery(
                network=network,
                state=state,
                detail=detail,
                hook_addr=addr,
                token_addr=checksum_address(expected_token),
                source_tx_hash=(source_tx_by_addr or {}).get(addr),
            )
        if first is None:
            first = (addr, state, detail)

    addr, state, detail = first  # type: ignore[misc]
    return Pool4Discovery(
        network=network,
        state=state,
        detail=detail,
        source_tx_hash=(source_tx_by_addr or {}).get(addr),
    )


#: Ranked strongest first, and the order is the whole design.
_SOURCE_SELF_POST, _SOURCE_DOCS, _SOURCE_UNATTRIBUTED = POOL4_DISCOVERY_SOURCES


def discovery_source_word(source: Any, state: Any) -> str | None:
    """The source word for a verdict, with the one absence that must not exist.

    ``None`` keeps its house meaning -- *there is no adoption to attribute* --
    and is correct on every non-adopted state.  On an **adopted** state it is
    not an answer at all: a renderer that treats ``None`` as "nothing to say"
    would draw a docs-sourced adoption identically to a dev-signed one, undoing
    by omission the disclosure the operator's decision was conditioned on.  So
    an adoption with no recorded source resolves to ``unattributed``, which is
    shown at least as weakly as ``docs`` and makes a producer bug **visible**
    instead of silently promoting it to the strong case.

    A source word that is not in the frozen vocabulary is treated the same way:
    unrecognised is not a licence to render the strong answer.
    """
    if state != _STATE_ADOPTED:
        return None
    if isinstance(source, str) and source in POOL4_DISCOVERY_SOURCES:
        return source
    return _SOURCE_UNATTRIBUTED


def ranked_discovery(
    rows: Sequence[Mapping[str, Any]] | None,
    announce: str,
    expected_token: str,
    answers_by_addr: Mapping[str, Mapping[str, Any]] | Any = None,
    network: str | None = None,
    source_tx_by_addr: Mapping[str, str] | None = None,
    docs_text: Any = None,
) -> tuple[Pool4Discovery, str | None]:
    """``(verdict, source)`` across both candidate sources.  **Ranked, not merged.**

    The announce channel is adjudicated first and on its own.  Only if it
    adopts nothing does the docs page get a turn, and the two candidate lists
    are **never concatenated**: merging would let a docs address be adjudicated
    ahead of a channel one purely by list position, which is the strong source
    silently losing to the weak one.

    * the channel adopts -> ``(verdict, "self-post")``.  Docs is not consulted
      at all, so a self-post landing later overrides a docs adoption the next
      time this runs -- which is what "the channel overrides" has to mean when
      nothing is persisted.
    * the channel adopts nothing, docs does -> ``(verdict, "docs")``.
    * neither adopts -> the **stronger source's** non-adoption is reported, so
      the reason a reader sees is the reason from the authoritative source.
      Docs' verdict is used only when the channel had no hook-shaped candidate
      to say anything about.  ``source`` is ``None``: there is no adoption to
      attribute.

    A channel *rejection* does not veto docs.  A self-post naming an address
    that fails the chain fingerprint means that address is not a pool4 hook; it
    says nothing about a different, valid address the docs name, and letting
    one stale post permanently block the other source would be a worse failure
    than the one it prevents.
    """
    channel_candidates = candidate_addresses(rows, announce)
    channel = adjudicate_candidates(
        channel_candidates, expected_token, answers_by_addr, network,
        source_tx_by_addr, origin="self-post",
    )
    if channel.state == _STATE_ADOPTED:
        return channel, _SOURCE_SELF_POST

    docs_candidates = docs_candidate_addresses(docs_text)
    if docs_candidates:
        docs = adjudicate_candidates(
            docs_candidates, expected_token, answers_by_addr, network,
            None, origin="docs",
        )
        if docs.state == _STATE_ADOPTED:
            return docs, _SOURCE_DOCS
        if not triaged_candidates(channel_candidates):
            # The channel had nothing hook-shaped to say anything about, so the
            # docs page is the only source that actually looked at something.
            return docs, None
    return channel, None


# ---------------------------------------------------------------------------
# RETIRED 2026-09-02: ``reverify_persisted``
# ---------------------------------------------------------------------------
#
# A ``reverify_persisted(payload, expected_token, answers_by_addr)`` lived here.
# It re-ran the flag and fingerprint gates over a persisted ``~/.maxpane/``
# discovery payload, on the curator ``pattern_language()`` precedent that a
# hand-edited cache file is third-party input too.  It is gone, and the two
# reasons are worth keeping because the next reader to think "the cache should
# be re-verified" should find them rather than rewrite the function.
#
# **1. There is nothing left to re-verify.**  The manager no longer nominates
# the persisted address at all -- not first, not last, not corroborated.  A
# candidate can only come from :func:`candidate_addresses` over the current
# cycle's channel rows, so a cache file cannot put an address into the running
# and the function had no reachable caller.
#
# **2. Re-verifying it could never have helped, and the docstring said
# otherwise.**  That docstring promised that "a payload hand-edited to
# ``adopted`` for an address that passes no gate comes back ``rejected``",
# which was true only of the committed fixture, whose flag word is ``0x0000``.
# Against anyone trying: the flag gate is arithmetic on an address and any low
# fourteen bits are mineable -- measured here at **20,141 tries**, seconds of
# work -- four of the five getter gates only check that *something answered*,
# and the fifth, ``token()``, returns whatever the candidate's own contract
# chooses.  A mined ``…2840`` address plus a contract that answers real
# mainnet IMD to ``token()`` came back **adopted** from that function.  It was
# a reassuring sentence attached to a defence that a live demo defeated in
# twenty seconds, which is worse than no defence at all.
#
# The real answer is provenance: the self-post check is the only gate an
# attacker cannot satisfy, because it needs a transaction signed by the
# announce wallet's key.  Everything else narrows the field; that one is what
# makes the field trustworthy.  A cache-nominated address is precisely an
# address that skipped it.
#
# **The one future pressure to re-nominate from the cache, named so it can be
# refused on its merits:** the announce corpus is a paged fetch, and the
# self-post naming the hook could one day age off the page the client reads.
# Discovery would then lose a hook that is genuinely adopted.  The fix for that
# is to read enough of the channel, not to let the cache nominate -- reaching
# for the cache would trade a paging bug for the provenance bypass this
# retirement closed.
#
# Deleted with its ``__all__`` entry and its three tests.  ``Pool4Discovery``
# is still the verdict type and ``discovery_verdict`` still produces it.


# ---------------------------------------------------------------------------
# Calldata builders
# ---------------------------------------------------------------------------


def encode_getter(sel: str) -> str:
    """A zero-argument getter call: the selector and nothing else."""
    return sel if sel.startswith("0x") else "0x" + sel


def encode_balance_of(addr: str) -> str:
    body = strip0x(addr).lower().rjust(64, "0")
    return ERC20_SELECTORS["balanceOf"] + body


def encode_convert_to_assets(shares_wei: int) -> str:
    return VAULT_SELECTORS["convertToAssets"] + format(shares_wei, "064x")


def encode_extsload(slot: str) -> str:
    return SEL_EXTSLOAD + strip0x(slot).rjust(64, "0")


def pool_state_calls(pool_id: str, mapping_slot: int = 6) -> tuple[str, str]:
    """``(slot0 calldata, liquidity calldata)`` for ``PoolManager.extsload``.

    The slot derivation is ``data/surf_v4.pool_state_slots`` and the keccak is
    ``data/keccak``.  Neither is re-implemented here, and
    ``test_surf_pool4_contains_no_local_keccak_or_slot_derivation`` asserts
    that structurally.
    """
    slot0_key, liquidity_key = pool_state_slots(pool_id, mapping_slot)
    return encode_extsload(slot0_key), encode_extsload(liquidity_key)


# ---------------------------------------------------------------------------
# Response decoders — field by field, never all-or-nothing
# ---------------------------------------------------------------------------
#
# The hook is unverified source, so a getter that answers on Sepolia may revert
# on mainnet.  Every decoder below degrades **per field**: one dead getter is
# one ``None`` inside an otherwise-healthy payload, never a dropped round and
# never a dead panel (plan R1 control (a)).


def _uint(raw: Any, word: int = 0) -> int | None:
    if not answered(raw):
        return None
    body = strip0x(raw.strip())  # type: ignore[union-attr]
    chunk = body[64 * word: 64 * (word + 1)]
    if len(chunk) != 64:
        return None
    try:
        return int(chunk, 16)
    except ValueError:
        return None


def _int24(raw: Any, word: int = 0) -> int | None:
    value = _uint(raw, word)
    if value is None:
        return None
    value &= (1 << 24) - 1
    return value - (1 << 24) if value >= 1 << 23 else value


def _bool(raw: Any) -> bool | None:
    value = _uint(raw)
    return None if value is None else bool(value)


def _addr(raw: Any) -> str | None:
    return _decoded_address(raw)


def _bytes32(raw: Any) -> str | None:
    if not answered(raw):
        return None
    body = strip0x(raw.strip())  # type: ignore[union-attr]
    return "0x" + body[:64]


def _string(raw: Any) -> str | None:
    """Decode an ABI dynamic string.  ``None`` on anything malformed."""
    if not answered(raw):
        return None
    body = strip0x(raw.strip())  # type: ignore[union-attr]
    if len(body) < 128:
        return None
    try:
        length = int(body[64:128], 16)
    except ValueError:
        return None
    if length <= 0 or length > 128:
        return None
    chunk = body[128: 128 + length * 2]
    if len(chunk) != length * 2:
        return None
    try:
        return bytes.fromhex(chunk).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None


def decode_hook_state(
    answers: Mapping[str, Any] | None,
    total_supply_wei: int | None = None,
    block_number: int | None = None,
) -> Pool4HookState:
    """One batched round over the hook's recovered getter set -> the model.

    ``total_supply_wei`` is read off ``token()``'s own contract, not off the
    hook, and is passed in for that reason: the hook does not know the supply
    and a field it does not answer must not look like one it does.

    There is deliberately **no** ``vault`` field to fill (amendment A3): the
    recovered interface has no vault getter, and the path is
    ``rewardsRecipient()`` -> RewardDripper -> ``dripper.vault()``.
    """
    a = answers or {}
    return Pool4HookState(
        token=_addr(a.get("token")),
        pool_manager=_addr(a.get("poolManager")),
        pool_id=_bytes32(a.get("poolId")),
        owner=_addr(a.get("owner")),
        burn_sink=_addr(a.get("burnSink")),
        rewards_recipient=_addr(a.get("rewardsRecipient")),
        # Three fields, decoded word by word rather than through
        # :func:`decode_backstop`, so a short answer from a differently-built
        # mainnet hook loses one word rather than all three (WP0's per-field
        # outage discipline).
        backstop_tick_lower=_int24(a.get("backstop"), 0),
        backstop_tick_upper=_int24(a.get("backstop"), 1),
        backstop_liquidity=_uint(a.get("backstop"), 2),
        market_open=_bool(a.get("marketOpen")),
        rebalance_enabled=_bool(a.get("rebalanceEnabled")),
        bps_denominator=_uint(a.get("BPS_DENOMINATOR")),
        reward_share_bps=_uint(a.get("rewardShareBps")),
        lp_fee=_uint(a.get("lpFee")),
        cap_floor_wei=_uint(a.get("capFloor")),
        inventory_cap_wei=_uint(a.get("inventoryCap")),
        cap_decay_tokens_per_day_wei=_uint(a.get("capDecayTokensPerDay")),
        keeper_reward_wei=_uint(a.get("keeperReward")),
        tick_spacing=_int24(a.get("tickSpacing")),
        tick_lower=_int24(a.get("tickLower")),
        tick_upper=_int24(a.get("tickUpper")),
        ref_tick=_int24(a.get("refTick")),
        current_tick=_int24(a.get("currentTick")),
        current_sqrt_price_x96=_uint(a.get("currentSqrtPriceX96")),
        position_liquidity=_uint(a.get("positionLiquidity")),
        eth_in_pool_wei=_uint(a.get("ethInPool")),
        tokens_in_pool_wei=_uint(a.get("tokensInPool")),
        total_burned_wei=_uint(a.get("totalBurned")),
        total_rewarded_wei=_uint(a.get("totalRewarded")),
        total_fee_token_wei=_uint(a.get("totalFeeToken")),
        retained_eth_wei=_uint(a.get("retainedEth")),
        last_claim_block=_uint(a.get("lastClaimBlock")),
        total_supply_wei=total_supply_wei,
        block_number=block_number,
    )


def decode_backstop(raw: Any) -> tuple[int, int, int] | None:
    """``(tickLower, tickUpper, liquidity)`` from ``backstop()``.

    Three words on the live hook, **not** the four the mechanics doc's prose
    claims: the ETH figure quoted there is not in the return.  Decoding a
    fourth word we were not given would read a neighbour's memory as a number,
    so this stops at three and the caller gets ``None`` if fewer arrive.
    """
    lower = _int24(raw, 0)
    upper = _int24(raw, 1)
    liquidity = _uint(raw, 2)
    if lower is None or upper is None or liquidity is None:
        return None
    return lower, upper, liquidity


#: The **only** key :func:`decode_vault_state` reads a share price from, and
#: the reason it is a constant rather than a tolerant lookup.
#:
#: ``share_price_wei`` is ``convertToAssets(10 ** decimals())`` -- assets per
#: one *whole* share.  WP1's capture names its call ``convertToAssets_1e18``
#: because it asked with ``1e18``, which on a 24-decimal vault is a millionth
#: of a share; the answer is a real number and reads as a dead vault
#: (0.0000013 IMD/share).  Accepting that key as an alias would launder a
#: wrong-argument answer into a right-looking field, so it is not accepted:
#: a producer that asks the wrong question gets ``None`` and a dark row, which
#: is recoverable, rather than a plausible number, which is not.
SHARE_PRICE_CALL = "convertToAssets"


def decode_vault_state(
    answers: Mapping[str, Any] | None,
    block_number: int | None = None,
) -> Pool4VaultState:
    """``StakedIMD``'s getters -> the model.

    ``decimals`` is read, never assumed.  ``total_shares_raw`` divides by
    ``10 ** decimals``, not by ``1e18`` -- see :func:`vault_shares`.
    """
    a = answers or {}
    return Pool4VaultState(
        name=_string(a.get("name")),
        symbol=_string(a.get("symbol")),
        decimals=_uint(a.get("decimals")),
        asset=_addr(a.get("asset")),
        owner=_addr(a.get("owner")),
        paused=_bool(a.get("paused")),
        total_assets_wei=_uint(a.get("totalAssets")),
        total_shares_raw=_uint(a.get("totalSupply")),
        share_price_wei=_uint(a.get(SHARE_PRICE_CALL)),
        block_number=block_number,
    )


def decode_distributor_state(
    answers: Mapping[str, Any] | None,
    block_number: int | None = None,
) -> "Pool4DistributorState":
    """The Distributor's getters -> the model.

    **No ``bonding_bps`` is decoded, because there is no getter to decode.**
    Bonding is the remainder; see :func:`bonding_bps`, which derives it and
    goes ``None`` whenever either input does.
    """
    a = answers or {}
    return Pool4DistributorState(
        staking_bps=_uint(a.get("stakingBps")),
        nft_bps=_uint(a.get("nftBps")),
        dripper=_addr(a.get("dripper")),
        asset=_addr(a.get("asset")),
        owner=_addr(a.get("owner")),
        staking_earned_wei=_uint(a.get("stakingEarned")),
        bonding_earned_wei=_uint(a.get("bondingEarned")),
        nft_earned_wei=_uint(a.get("nftEarned")),
        held_bonding_wei=_uint(a.get("heldBonding")),
        held_nft_wei=_uint(a.get("heldNft")),
        block_number=block_number,
    )


def decode_dripper_state(
    answers: Mapping[str, Any] | None,
    balance_wei: int | None = None,
    block_number: int | None = None,
) -> Pool4DripperState:
    """``RewardDripper``'s getters -> the model.

    ``balance_wei`` is the **backlog** and comes from the token's
    ``balanceOf(dripper)``, not from the dripper, so it is a parameter.
    """
    a = answers or {}
    return Pool4DripperState(
        vault=_addr(a.get("vault")),
        token=_addr(a.get("imd")),
        owner=_addr(a.get("owner")),
        drip_rate_per_second_wei=_uint(a.get("dripRatePerSecond")),
        max_catchup_seconds=_uint(a.get("maxCatchupSeconds")),
        min_drip_amount_wei=_uint(a.get("minDripAmount")),
        keeper_reward_wei=_uint(a.get("keeperReward")),
        drippable_wei=_uint(a.get("drippable")),
        can_drip=_bool(a.get("canDrip")),
        balance_wei=balance_wei,
        block_number=block_number,
    )


# ---------------------------------------------------------------------------
# Flow logs
# ---------------------------------------------------------------------------


def _log_key(log: Mapping[str, Any]) -> tuple[int, int]:
    """``(blockNumber, logIndex)`` — total order over one chain's logs."""
    try:
        return (int(log.get("blockNumber", "0x0"), 16),
                int(log.get("logIndex", "0x0"), 16))
    except (TypeError, ValueError):
        return (0, 0)


def _log_words(log: Mapping[str, Any]) -> list[int]:
    body = strip0x(str(log.get("data") or ""))
    return [
        int(body[64 * i: 64 * (i + 1)], 16)
        for i in range(len(body) // 64)
    ]


def decode_flow_events(logs: Sequence[Mapping[str, Any]] | None) -> list[Pool4FlowEvent]:
    """One swap's worth of hook activity per row, newest first.

    A **buy** is ``FeeCollected(0, eth)`` beside the pool-reserve event: the
    fee is taken in ETH, nothing burns, and ``size`` is what the reserve fell
    by.  ``burned_wei`` and ``stakers_wei`` are ``0`` and that is a
    *representable zero* -- buys are not deflationary, sells are, and
    collapsing that into ``None`` is the FARM/HOUR-SAVED defect this repo has
    already shipped once.

    A **sell** is ``FeeCollected(imd, 0)`` beside the accrual event, and
    ``size`` is ``toBurn + toRewards + fee`` read from the logs -- never
    ``fee * 100``, which would be assuming the documented 1% instead of
    measuring it.

    ``settled`` is decided by **log order across the whole set**, not by what
    is in the same transaction, and the corpus proves the difference is real:
    in ``flow_logs_mixed.json`` the ``ClaimsSettled(891.0, 99.0)`` that opens
    tx ``0x48090d111b`` matches the accrual in the *previous* tx
    ``0xd161357a2b`` to the wei, and precedes that transaction's own accrual by
    log index.  Settlement rides the **next** swap, so a same-transaction rule
    marks the settled row unsettled and the unsettled row settled -- exactly
    backwards.  Under the ordering rule the leftover is the last accrual, and
    ``Sigma accrual - Sigma ClaimsSettled`` agrees with it to the wei.

    A settlement with no swap in its transaction is not a flow row: it has no
    ``side``, and the ``side`` vocabulary is closed.  It still counts towards
    :func:`unsettled_legs`.
    """
    if not logs:
        return []
    ordered = sorted(logs, key=_log_key)
    settle_keys = [
        _log_key(l) for l in ordered
        if (l.get("topics") or [None])[0] == TOPIC_CLAIMS_SETTLED
    ]
    last_settle = max(settle_keys) if settle_keys else None

    by_tx: dict[str, list[Mapping[str, Any]]] = {}
    for log in ordered:
        by_tx.setdefault(str(log.get("transactionHash") or ""), []).append(log)

    rows: list[Pool4FlowEvent] = []
    for tx_hash, tx_logs in by_tx.items():
        fee = next(
            (l for l in tx_logs
             if (l.get("topics") or [None])[0] == TOPIC_FEE_COLLECTED),
            None,
        )
        accrual = next(
            (l for l in tx_logs
             if (l.get("topics") or [None])[0] == TOPIC_ACCRUAL),
            None,
        )
        reserve = next(
            (l for l in tx_logs
             if (l.get("topics") or [None])[0] == TOPIC_POOL_RESERVE),
            None,
        )
        if fee is None and accrual is None and reserve is None:
            continue

        fee_words = _log_words(fee) if fee is not None else []
        fee_imd = fee_words[0] if len(fee_words) > 0 else None
        fee_eth = fee_words[1] if len(fee_words) > 1 else None

        block = _log_key(tx_logs[0])[0]
        try:
            ts: float | None = float(int(tx_logs[0].get("blockTimestamp"), 16))
        except (TypeError, ValueError):
            ts = None

        if accrual is not None:
            words = _log_words(accrual)
            burned = words[1] if len(words) > 1 else 0
            stakers = words[2] if len(words) > 2 else 0
            side = _SIDE_SELL
            size = burned + stakers + (fee_imd or 0)
            key = _log_key(accrual)
            settled = last_settle is not None and last_settle > key
            fee_token_wei = fee_imd
            fee_eth_wei = None
        elif reserve is not None:
            words = _log_words(reserve)
            side = _SIDE_BUY
            size = (
                words[0] - words[1]
                if len(words) > 1 and words[0] >= words[1]
                else None
            )
            burned = 0
            stakers = 0
            # A buy accrues nothing, so there is nothing outstanding on it.
            settled = True
            fee_token_wei = None
            fee_eth_wei = fee_eth
        else:
            # A fee with neither a reserve move nor an accrual: not a swap this
            # module can name a side for, and ``side`` is a closed vocabulary.
            continue

        rows.append(
            Pool4FlowEvent(
                tx_hash=tx_hash or None,
                ts=ts,
                block_number=block,
                side=side,
                size_wei=size,
                burned_wei=burned,
                stakers_wei=stakers,
                fee_token_wei=fee_token_wei,
                fee_eth_wei=fee_eth_wei,
                settled=settled,
            )
        )

    rows.sort(key=lambda r: (r.block_number or 0), reverse=True)
    return rows


def reserve_series(logs: Sequence[Mapping[str, Any]] | None) -> list[list[float]] | None:
    """``[[ts, imd], …]`` oldest first, from the pool-reserve event.

    ``None`` when the read failed; ``[]`` when the window was swept and
    genuinely quiet.  **No sentinel is ever appended** -- a series with a zero
    in it outlives the outage that put it there.
    """
    if logs is None:
        return None
    out: list[list[float]] = []
    for log in sorted(logs, key=_log_key):
        if (log.get("topics") or [None])[0] != TOPIC_POOL_RESERVE:
            continue
        words = _log_words(log)
        if len(words) < 2:
            continue
        try:
            ts = float(int(log.get("blockTimestamp"), 16))
        except (TypeError, ValueError):
            continue
        out.append([ts, words[1] / WEI])
    return out


#: The hook's birth certificate.  ``Ownable``'s constructor emits
#: ``OwnershipTransferred(address(0), owner)`` exactly once, and **no log of
#: this contract can precede it**.
#:
#: That makes it the one thing in the log set that can answer "does this sweep
#: cover the hook's whole history?" without trusting a caller-supplied
#: deployment block or doing arithmetic on window bounds.  The committed
#: corpus proves it both ways: ``flow_logs_full.json`` carries it as the
#: earliest of its ninety logs (block 11,609,650, window opening at
#: 11,609,600) and all four of its identities hold to the wei, while
#: ``flow_logs_mixed.json``'s sixty-block window carries no such log and its
#: sums are short by everything before it.
TOPIC_OWNERSHIP_TRANSFERRED = topic0(EVENT_SIGNATURES["OwnershipTransferred"])


def logs_reach_genesis(logs: Sequence[Mapping[str, Any]] | None) -> bool | None:
    """Does this log set cover the hook's whole history?

    ``True`` when it contains the constructor's
    ``OwnershipTransferred(address(0), owner)``; ``False`` when it does not;
    ``None`` when the logs were not read at all.

    The zero ``previousOwner`` is the load-bearing part.  A later
    ``transferOwnership`` emits the same topic0 with a *non-zero* first
    operand, so testing the topic alone would read an ownership change as a
    birth certificate and call a trailing window complete.
    """
    if logs is None:
        return None
    for log in logs:
        topics = log.get("topics") or []
        if len(topics) < 3 or topics[0] != TOPIC_OWNERSHIP_TRANSFERRED:
            continue
        try:
            if int(topics[1], 16) == 0:
                return True
        except (TypeError, ValueError):
            continue
    return False


#: The nine running totals the identities are built from.  A plain tuple of
#: names rather than a dataclass: WP7 persists this to JSON, and a model would
#: put a class between the cache file and the arithmetic for no gain.
COUNTER_SUM_FIELDS: tuple[str, ...] = (
    "fee_imd", "fee_eth",
    "settled_burn", "settled_stakers", "settled_eth",
    "withdrawn_imd", "withdrawn_eth",
    "accrued_burn", "accrued_stakers",
)


def _sum_logs(logs: Sequence[Mapping[str, Any]] | None) -> dict[str, int | None]:
    """The nine totals over one set of logs.

    ``logs is None`` yields nine ``None``s, never nine zeros: a failed sweep is
    not a set of empty sums, and summing over ``None`` silently produced one.
    """
    if logs is None:
        return {k: None for k in COUNTER_SUM_FIELDS}
    sums: dict[str, int | None] = {k: 0 for k in COUNTER_SUM_FIELDS}
    for log in logs:
        top = (log.get("topics") or [None])[0]
        words = _log_words(log)
        if top == TOPIC_FEE_COLLECTED and len(words) >= 2:
            sums["fee_imd"] += words[0]
            sums["fee_eth"] += words[1]
        elif top == TOPIC_CLAIMS_SETTLED and len(words) >= 3:
            sums["settled_burn"] += words[0]
            sums["settled_stakers"] += words[1]
            sums["settled_eth"] += words[2]
        elif top == TOPIC_FEES_WITHDRAWN and len(words) >= 2:
            sums["withdrawn_imd"] += words[0]
            sums["withdrawn_eth"] += words[1]
        elif top == TOPIC_ACCRUAL and len(words) >= 3:
            sums["accrued_burn"] += words[1]
            sums["accrued_stakers"] += words[2]
    return sums


def empty_accumulator() -> dict[str, Any]:
    """A running total that has not been seeded, and claims nothing.

    ``genesis_block is None`` is the only honest starting state: the sums are
    zero because nothing has been counted, not because nothing happened, and
    :func:`accumulator_covers` refuses it either way.
    """
    return {
        "genesis_block": None,
        "cursor_block": None,
        "sums": {k: 0 for k in COUNTER_SUM_FIELDS},
    }


def accumulate_counters(
    accumulator: Mapping[str, Any] | None,
    logs: Sequence[Mapping[str, Any]] | None,
    from_block: int | None,
    to_block: int | None,
) -> dict[str, Any]:
    """Fold one window's logs into a running total, or refuse to.

    The counter identities are *cumulative* counters against a sum of **all**
    logs, while the sweep reads a trailing window, so from about a day after
    deployment every check is ``window-limited`` for ever and the control
    detects nothing.  Carrying the sums forward is the fix -- the
    ``LaunchpadState.cursor`` precedent, because a total cannot be recovered
    from its newest addend.

    **A total is only worth more than a window if it has no hole in it, and a
    hole is invisible.**  A total short by a missed sweep is indistinguishable
    from a total short because a decoder is wrong -- the same ambiguity as the
    mirror case in :func:`reconcile_counters`.  So this function does not
    patch over a gap; it **discards the accumulator** and returns an unseeded
    one, and the caller falls back to single-window behaviour until a sweep
    containing genesis reseeds it.  Losing two months of accumulation is
    cheap; a total that says ``reconciled`` when it means ``probably`` is not.

    Two invariants, and both are checkable rather than asserted:

    * **Seeded at genesis.**  The first window folded in must contain
      ``OwnershipTransferred(address(0), owner)``, which no log of this
      contract can precede.  Nothing else can prove a total starts at the
      beginning.
    * **Contiguous since.**  Each window must satisfy
      ``from_block <= cursor_block + 1``.  Logs at or below the cursor are
      skipped rather than added, so an overlapping re-sweep is idempotent
      instead of double-counting -- a ``[from, to]`` range never splits a
      block, so block number is a sound dedupe key.

    A failed sweep (``logs is None``) advances nothing and returns the
    accumulator untouched: not counting is not the same as counting zero.
    """
    acc = accumulator if isinstance(accumulator, Mapping) else empty_accumulator()
    if logs is None:
        return dict(acc)
    if not isinstance(from_block, int) or not isinstance(to_block, int):
        return empty_accumulator()

    prior = acc.get("sums")
    prior = prior if isinstance(prior, Mapping) else {}
    genesis_block = acc.get("genesis_block")
    cursor = acc.get("cursor_block")

    if genesis_block is None or not isinstance(cursor, int):
        seed = _genesis_block(logs)
        if seed is None:
            # Cannot seed from a window that does not reach the hook's birth.
            return empty_accumulator()
        window = _sum_logs(logs)
        return {
            "genesis_block": seed,
            "cursor_block": to_block,
            "sums": {k: window[k] or 0 for k in COUNTER_SUM_FIELDS},
        }

    if from_block > cursor + 1:
        # A hole.  Anything built on top of it would be short by an unknown
        # amount and would read as a mismatch that nobody could explain.
        return empty_accumulator()

    fresh = [l for l in logs if _log_key(l)[0] > cursor]
    window = _sum_logs(fresh)
    return {
        "genesis_block": genesis_block,
        "cursor_block": max(cursor, to_block),
        "sums": {
            k: int(prior.get(k) or 0) + int(window[k] or 0)
            for k in COUNTER_SUM_FIELDS
        },
    }


def accumulator_covers(
    accumulator: Mapping[str, Any] | None,
    at_block: int | None,
) -> bool:
    """Can this accumulator be reconciled against counters read at ``at_block``?

    Two conditions, and **the second is the one that is easy to miss**:

    1. **Continuity** -- seeded at genesis and contiguous since, which
       :func:`accumulate_counters` maintains.
    2. **Alignment** -- ``cursor_block == at_block``, exactly.

    Alignment is not pedantry.  The sums cover ``[genesis, cursor]`` and the
    counter covers ``[genesis, at_block]``; if those differ, the identity is
    being asked to hold across two different moments.  A cursor *behind* the
    counter makes the sums short and, since continuity says the evidence is
    complete, that short sum reads as a **mismatch** -- a false alarm on every
    tick where a swap lands between the two reads.  A cursor *ahead* makes the
    sums large, which the sign hatch also calls a mismatch.  Either way an
    aligned-looking control fires on a healthy hook.

    So the answer when they disagree is ``False`` -- ``window-limited``, the
    control did not run -- and the fix is on the caller's side: read state at a
    pinned block and sweep logs to that same block, which the client already
    does (``block_tag`` on the state round, ``toBlock`` on the log round).
    """
    if not isinstance(accumulator, Mapping):
        return False
    if accumulator.get("genesis_block") is None:
        return False
    cursor = accumulator.get("cursor_block")
    if not isinstance(cursor, int) or not isinstance(at_block, int):
        return False
    return cursor == at_block


def _genesis_block(logs: Sequence[Mapping[str, Any]] | None) -> int | None:
    """The block of the constructor's ``OwnershipTransferred``, if present."""
    for log in logs or ():
        topics = log.get("topics") or []
        if len(topics) < 3 or topics[0] != TOPIC_OWNERSHIP_TRANSFERRED:
            continue
        try:
            if int(topics[1], 16) == 0:
                return _log_key(log)[0]
        except (TypeError, ValueError):
            continue
    return None


def reconcile_counters(
    logs: Sequence[Mapping[str, Any]] | None,
    hook: Pool4HookState | None,
    dead_balance_wei: int | None = None,
    accumulator: Mapping[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """R1 control (c): what the chain can settle about the recovered interface.

    The hook's getter set was recovered from ``PUSH4`` selectors in unverified
    bytecode and three of its event signatures are still unresolved, so a
    wrong operand order surfaces as a *confident wrong number* with no signal
    anywhere.  These identities are the day-one detector for that, and they
    are only worth having if they are believed when they fire -- which means
    they must be silent, and visibly silent, whenever they cannot run.

    Each check carries a ``state`` from :data:`POOL4_COUNTER_STATES` and a
    tri-state ``agree``:

    * ``reconciled`` / ``agree=True``  -- holds to the wei over complete history.
    * ``mismatch``   / ``agree=False`` -- complete history, and it does **not**
      hold.  This is the loud one and the only one a reader should act on.
    * ``window-limited`` / ``agree=None`` -- the sums cover a trailing window
      rather than the hook's whole life, so a cumulative counter cannot equal
      them **by construction**.  Not an error and explicitly **not a pass**.
    * ``unchecked`` / ``agree=None`` -- a side was unread.

    **The sign of the delta outranks completeness, and that is arithmetic
    rather than policy.**  Truncation removes addends, so a windowed sum can
    only ever be *smaller* than the total it is compared against.  This holds
    for all five identities and not merely the three obviously-cumulative
    ones:

    * ``totalFeeToken``, ``totalBurned``, ``totalRewarded`` are monotone
      cumulative counters, so ``window sum <= all-history sum == counter``.
    * ``balanceOf(0xdEaD)`` is non-decreasing (nobody holds that key) and also
      includes burns by anyone else, so it is ``>=`` the hook's own total,
      which is ``>=`` the window's.
    The fifth, the ETH identity, is the exception and is **excluded from the
    hatch**: it has a windowed sum on the left and a windowed sum plus a
    *current balance* on the right, so both sides move with the window and the
    reduction ``LHS - RHS == Sigma_before(withdrawn) - Sigma_before(fee) <= 0``
    only holds when the window is a **trailing** one.  The production sweep is
    trailing, but that is the caller's choice and not this function's
    precondition -- and the committed ``flow_logs_mixed.json``, a mid-history
    window whose two ``FeesWithdrawn`` fall *after* it, reads **+2e14** on a
    perfectly healthy hook.  Giving that check the hatch would report a
    ``mismatch`` there, which is the very failure the hatch exists to prevent,
    pointed the other way.

    So for the four monotone identities ``from_logs > from_counter`` is
    unexplainable by any window and is checked **first**.  Asking about completeness before the sign would file a
    positive delta as ``window-limited`` -- a false negative on the one control
    whose entire value is being believed when it fires, and on the failure
    shape it most exists to detect, since a decoder reading an operand in the
    wrong position produces arbitrary sums while truncation produces only
    short ones.

    The mirror does **not** hold and deliberately gets no hatch: a short sum in
    an incomplete sweep is indistinguishable from truncation by any arithmetic
    available here, so it stays ``window-limited``.

    One caveat on the ``0xdEaD`` identity, recorded rather than handled: a
    *third party* burning IMD to that address makes the balance exceed the
    hook's own burns and would show as a ``mismatch`` on a complete sweep that
    is nobody's decoding error.  It has not happened on this deployment (the
    committed corpus reconciles to the wei), and the honest response if it ever
    does is to compare against the hook's transfers rather than the sink's
    balance.

    **``agree`` used to be ``from_counter is not None and ...``**, which made an
    unread counter byte-identical to a genuine disagreement -- the same
    "we could not look" versus "the value is wrong" conflation this control
    exists to catch, one layer down, on the control itself.  A sweep that
    failed would have made the dashboard cry mismatch.  ``from_logs`` is
    ``None`` rather than ``0`` for the same reason: a failed read is never a
    zero, and summing over ``None`` silently produced one.

    **Window-limitedness is decided here rather than by the caller**, from
    :func:`logs_reach_genesis`.  The judgement is "are these sums the whole
    history?", which is a property of the log set and of these identities; a
    manager inferring it from ``POOL4_LOG_WINDOW_BLOCKS`` and a block number
    would be re-deriving arithmetic this module owns, and would get it wrong
    the first time anyone changed the window.

    **There is deliberately no symmetric ETH check** (amendment A9).
    ``totalFeeToken()`` is *cumulative* while ``retainedEth()`` is a *current
    balance*, so ``Sigma FeeCollected[eth] == retainedEth()`` reads 0.0057 vs 0
    on a perfectly healthy hook and would cry wolf on every owner withdrawal.
    What actually holds, and what is checked here, is
    ``Sigma FeeCollected[eth] == Sigma FeesWithdrawn[eth] + retainedEth()``.

    .. note::

       **This control goes permanently quiet once the hook outlives the log
       window, and that is a real limitation rather than a design.** Every
       identity is a *cumulative* counter against a sum of *all* logs, while
       the sweep reads a trailing window, so from roughly a day after
       deployment onwards every check is ``window-limited`` for ever. Honest,
       and worth publishing -- it says the control did not run rather than
       that nothing is wrong -- but it means the detector really works only
       while the hook is young, which happens to be exactly when a decoder
       recovered from bytecode is most likely to be wrong.

       Making it work in steady state needs the sums **accumulated forward
       from deployment** and persisted, on the ``LaunchpadState.cursor``
       precedent: a total cannot be recovered from its newest addend. That is
       a larger change and is deliberately not made here.
    """
    if accumulator is not None:
        # Accumulated across every window since genesis: complete iff the
        # accumulator can prove continuity AND covers the exact block the
        # counters were read at.  See :func:`accumulator_covers`.
        at_block = hook.block_number if hook is not None else None
        complete = accumulator_covers(accumulator, at_block)
        cursor = (
            accumulator.get("cursor_block")
            if isinstance(accumulator, Mapping) else None
        )
        window_reason = (
            "the accumulated sums stop at block "
            f"{cursor}, not the block the counters were read at ({at_block})"
        )
        raw = accumulator.get("sums") if isinstance(accumulator, Mapping) else None
        sums = (
            {k: raw.get(k) for k in COUNTER_SUM_FIELDS}
            if isinstance(raw, Mapping)
            else {k: None for k in COUNTER_SUM_FIELDS}
        )
    else:
        complete = logs_reach_genesis(logs)
        window_reason = "the log sweep does not reach the hook's first block"
        sums = _sum_logs(logs)

    def check(
        from_logs: int | None,
        from_counter: int | None,
        truncation_only_shortens: bool = True,
    ) -> dict[str, Any]:
        if from_logs is None or from_counter is None:
            state, agree, delta = _COUNTER_UNCHECKED, None, None
        elif truncation_only_shortens and from_logs > from_counter:
            # THE SIGN ESCAPE HATCH, and it runs BEFORE the completeness test.
            #
            # A sum over a subset of history cannot exceed a monotone
            # cumulative total, so truncation can only ever make the log sum
            # SHORT. A log sum that is LARGER is unexplainable by any window,
            # however narrow, and is a real disagreement -- so asking "is the
            # sweep complete?" first would file it as ``window-limited`` and
            # go silent on it.
            #
            # It is also the shape the control most exists to catch: a decoder
            # reading an operand in the wrong position produces *arbitrary*
            # sums, and roughly half of those are too big. Truncation is
            # always one-signed; a wrong operand order is not.
            state, agree, delta = (
                _COUNTER_MISMATCH, False, from_logs - from_counter,
            )
        elif not complete:
            # A SHORT sum in an incomplete sweep is exactly what truncation
            # looks like, and there is no arithmetic that separates it from a
            # genuine shortfall -- both are "too small by an unknown amount".
            # ``window-limited`` is the honest answer *because* the two are
            # indistinguishable here, not because the case was overlooked.
            state, agree, delta = _COUNTER_WINDOW_LIMITED, None, None
        elif from_logs == from_counter:
            state, agree, delta = _COUNTER_RECONCILED, True, 0
        else:
            state, agree, delta = (
                _COUNTER_MISMATCH, False, from_logs - from_counter,
            )
        return {
            "from_logs": from_logs,
            "from_counter": from_counter,
            "state": state,
            "agree": agree,
            "delta_wei": delta,
            # Only meaningful on ``window-limited``; the two causes read
            # differently to whoever has to act on them.
            "window_reason": (
                window_reason if state == _COUNTER_WINDOW_LIMITED else None
            ),
        }

    h = hook
    return {
        "sum_FeeCollected_imd == totalFeeToken()":
            check(sums["fee_imd"], h.total_fee_token_wei if h else None),
        "sum_ClaimsSettled_0 == totalBurned()":
            check(sums["settled_burn"], h.total_burned_wei if h else None),
        "sum_ClaimsSettled_1 == totalRewarded()":
            check(sums["settled_stakers"], h.total_rewarded_wei if h else None),
        "totalBurned() == token.balanceOf(0xdEaD)":
            check(sums["settled_burn"], dead_balance_wei),
        # A9: the asymmetric ETH identity, not the symmetric one.
        # The ONE check that does not get the sign hatch.  Both of its sides
        # move with the window -- a windowed sum on the left, a windowed sum
        # plus a *current balance* on the right -- so its delta has no
        # determined sign unless the window is a trailing one.  The committed
        # ``flow_logs_mixed.json`` is a mid-history window whose two
        # ``FeesWithdrawn`` fall AFTER it, and it reads +2e14 on a perfectly
        # healthy hook.  Handing this check the hatch would turn that into a
        # ``mismatch`` and cry wolf, which is the failure the hatch exists to
        # prevent, pointed the other way.
        "sum_FeeCollected_eth == sum_FeesWithdrawn_eth + retainedEth()":
            check(
                sums["fee_eth"],
                None if h is None or h.retained_eth_wei is None
                or sums["withdrawn_eth"] is None
                else sums["withdrawn_eth"] + h.retained_eth_wei,
                truncation_only_shortens=False,
            ),
    }


def counter_verdict(
    checks: Mapping[str, Mapping[str, Any]] | None,
) -> tuple[str | None, str | None]:
    """Fold :func:`reconcile_counters` into ``(pool4_counter_state, detail)``.

    The precedence lives here rather than in the manager so that one module
    owns both the arithmetic and the judgement about it:

    ``mismatch`` > ``window-limited`` > ``unchecked`` > ``reconciled``

    ``window-limited`` has two causes and names which one it is, from the
    check's own ``window_reason``: the sweep does not reach the hook's first
    block, or an accumulated total stops at a different block from the one the
    counters were read at.  They mean the same thing -- the sums and the
    counters are not about the same history -- but they call for different
    fixes, so the detail says which.

    ``mismatch`` outranks everything because it is the only outcome a reader
    should act on, and because it cannot co-occur with ``window-limited``
    anyway -- completeness is a property of the shared log set, so either
    every check has it or none does.  ``unchecked`` outranks ``reconciled``
    so that "four of five held and the fifth was unread" never renders as a
    clean bill of health.

    ``(None, None)`` when there is nothing to fold: discovery has not run, and
    a verdict about counters nobody read would be manufactured.
    """
    if not checks:
        return None, None

    by_state: dict[str, list[str]] = {}
    for name, check in checks.items():
        by_state.setdefault(check.get("state") or _COUNTER_UNCHECKED, []).append(name)

    if _COUNTER_MISMATCH in by_state:
        worst = max(
            (checks[n] for n in by_state[_COUNTER_MISMATCH]),
            key=lambda c: abs(c.get("delta_wei") or 0),
        )
        name = next(
            n for n in by_state[_COUNTER_MISMATCH] if checks[n] is worst
        )
        return _COUNTER_MISMATCH, f"{name} is out by {worst['delta_wei']} wei"
    if _COUNTER_WINDOW_LIMITED in by_state:
        reason = next(
            (checks[n].get("window_reason") for n in by_state[_COUNTER_WINDOW_LIMITED]
             if checks[n].get("window_reason")),
            "the sums do not cover the same history as the counters",
        )
        return (
            _COUNTER_WINDOW_LIMITED,
            f"{reason}, so the cumulative identities cannot be reconciled "
            "against them",
        )
    if _COUNTER_UNCHECKED in by_state:
        unread = sorted(by_state[_COUNTER_UNCHECKED])
        return (
            _COUNTER_UNCHECKED,
            f"{len(unread)} of {len(checks)} identities could not be computed",
        )
    return (
        _COUNTER_RECONCILED,
        f"all {len(checks)} identities hold to the wei",
    )


# ---------------------------------------------------------------------------
# The maths — total functions.  Never raise, never return an infinity or a NaN.
# ---------------------------------------------------------------------------


def measured_split(
    fee_wei: int | None,
    burn_wei: int | None,
    stakers_wei: int | None,
) -> tuple[float | None, float | None, float | None]:
    """``(inference%, burn%, reward%)`` **from the live counters**, never quoted.

    The third element is the **whole reward share**, not the staker leg.  The
    hook's counters cannot tell them apart: ``totalRewarded()`` is everything
    handed to ``rewardsRecipient()``, and on mainnet that recipient is a
    Distributor that splits it three ways.  Labelling this number "stakers"
    overstates the staker share by more than three times -- use
    :func:`reward_leg_split` to subdivide it.

    The mechanics doc says 1.00 / 89.10 / 9.90 and this function must not be
    able to pass by agreeing with it: the test feeds the committed counters and
    then a mutated set, and the answer has to move.
    """
    parts = (fee_wei, burn_wei, stakers_wei)
    if any(p is None for p in parts):
        return None, None, None
    total = sum(parts)  # type: ignore[arg-type]
    if total <= 0:
        return None, None, None
    return tuple(p / total * 100.0 for p in parts)  # type: ignore[return-value]


#: Above this, a per-day token amount is not a rate -- it is Solidity's
#: "no limit" idiom, ``type(uintN).max``.
#:
#: ``capDecayTokensPerDay()`` returns ``2**128 - 1`` on the Sepolia hook.  As a
#: rate that is **3.4e20 whole IMD per day** -- 340 *billion* times the entire
#: one-billion IMD supply -- and it reaches a panel as a confident, absurd
#: number that nothing about looks like an error.  It means *this hook does not
#: decay its cap*, which is a fact, not a failure.
#:
#: The threshold lives here rather than in the producer under the A8
#: one-authority rule: two packages disagreeing about where the boundary sits
#: is how a sentinel becomes a rate on one screen and a word on another.
#:
#: **Why ``1 << 96`` and not the exact sentinel.**  Recognition is by
#: *magnitude*, not by matching a literal or a deployment name, because the
#: next hook may spell "no limit" with a different width.  ``1 << 96`` wei is
#: ~7.9e10 whole IMD per day: seventy-nine times the entire supply, so no real
#: decay can reach it -- there would be nothing left to decay -- while it sits
#: below ``type(uint128).max`` and ``type(uint256).max``, which is the sentinel
#: family in practice.
#:
#: **``type(uint64).max`` is deliberately NOT caught.**  It is 18.4 IMD/day,
#: which is an entirely plausible decay rate; treating that width's maximum as
#: a sentinel would silently turn a real rate into "no decay", which is the
#: opposite error and the harder one to notice.
POOL4_NO_DECAY_MIN_WEI = 1 << 96


def is_no_decay(cap_decay_tokens_per_day_wei: int | None) -> bool | None:
    """Three-way: ``None`` unread, ``True`` sentinel, ``False`` a real rate.

    The three-way return is the point.  Collapsing the sentinel into ``None``
    would conflate *"this hook does not decay its cap"* with *"we could not
    read it"* -- the same conflation removed three times already on this
    branch (``agree`` on an unread counter, ``from_logs`` on a failed sweep,
    ``answered`` on an empty return).  ``None`` stays the ordinary failed
    read and nothing else.

    A negative value is a real rate as far as this predicate is concerned: it
    is not a sentinel, it is a contract saying something strange, and the panel
    should be able to show that rather than have it filtered out here.

    What the producer does with ``True`` is the producer's decision -- a word,
    or the representable zero "we looked and it does not decay".  What is
    fixed here is *where the boundary is*.
    """
    if cap_decay_tokens_per_day_wei is None:
        return None
    if not isinstance(cap_decay_tokens_per_day_wei, int) or isinstance(
        cap_decay_tokens_per_day_wei, bool
    ):
        return None
    return cap_decay_tokens_per_day_wei >= POOL4_NO_DECAY_MIN_WEI


def bonding_bps(
    staking_bps: int | None,
    nft_bps: int | None,
    bps_denominator: int | None,
) -> int | None:
    """The bonding share, **derived** as the remainder.  ``None`` on any gap.

    The Distributor splits the reward share three ways and publishes only two
    of them: ``stakingBps()`` and ``nftBps()`` have getters, bonding does not.
    ``BPS_DENOMINATOR - stakingBps - nftBps`` is the only way to get it.

    Two things this is deliberately **not**.  It is not a hardcoded ``4000``:
    the split already moved once (``rewardShareBps`` 1000 -> 1500 between
    Sepolia and mainnet) and a typed constant goes stale in silence the day it
    moves again.  And it is not accompanied by a "derived" boolean -- a flag
    that can only ever be ``True`` is a constant dressed as data.  The honest
    signature of a derived value is that it goes ``None`` whenever **either**
    input does, which is the :func:`split_drift_bps` precedent and is what the
    guard below implements.

    A negative remainder is returned as-is rather than clamped: if the two
    published legs ever exceed the denominator, that is a fact about the
    contract and the panel should be able to say so.
    """
    if staking_bps is None or nft_bps is None or bps_denominator is None:
        return None
    return bps_denominator - staking_bps - nft_bps


def reward_leg_split(
    reward_pct: float | None,
    staking_bps: int | None,
    nft_bps: int | None,
    bps_denominator: int | None,
) -> tuple[float | None, float | None, float | None]:
    """Subdivide the reward leg into ``(staking, bonding, nodes)`` percentages.

    ``measured_split``'s third element is the **whole** reward share, because
    that is all the hook's counters know: ``totalRewarded()`` is everything
    handed to ``rewardsRecipient()``.  On mainnet that recipient is the
    Distributor, which splits it three ways -- so rendering that number under a
    "stakers" label overstates the staker share by more than three times.

    On the live mainnet reads (15% reward share, 3000/3000 bps) this turns
    ``(1.0, 84.0, 15.0)`` of the gross into a staking leg of 4.5, a bonding leg
    of 6.0 and a nodes leg of 4.5 -- the 85 / 4.5 / 6.0 / 4.5 shape per 100 IMD
    retired.

    ``(None, None, None)`` whenever any input is missing or the denominator is
    zero: three derived numbers, one gate, no infinities.
    """
    bonding = bonding_bps(staking_bps, nft_bps, bps_denominator)
    if reward_pct is None or bonding is None or not bps_denominator:
        return None, None, None
    return (
        reward_pct * staking_bps / bps_denominator,   # type: ignore[operator]
        reward_pct * bonding / bps_denominator,
        reward_pct * nft_bps / bps_denominator,       # type: ignore[operator]
    )


def split_drift_bps(
    burn_wei: int | None,
    stakers_wei: int | None,
    reward_share_bps: int | None,
    bps_denominator: int | None,
) -> float | None:
    """Measured staker share minus the claimed one, in bps.

    Like for like: ``rewardShareBps()`` is a share of the **post-fee** amount,
    so the measured side is ``stakers / (burn + stakers)``.  Comparing it
    against the share of the gross would print a permanent 100 bps drift on a
    hook that is behaving exactly as documented.

    ``0.0`` is the healthy answer and a real number: it renders as ``0.0``, not
    as a dash.  ``None`` only when a side is unread or the denominator is zero.
    """
    if burn_wei is None or stakers_wei is None:
        return None
    if reward_share_bps is None or not bps_denominator:
        return None
    post_fee = burn_wei + stakers_wei
    if post_fee <= 0:
        return None
    return stakers_wei / post_fee * bps_denominator - reward_share_bps


def floor_distance(reserve_wei: int | None, floor_wei: int | None) -> float | None:
    """Reserve minus the observed floor, whole IMD.

    **A negative is a legitimate state, not a bug and not a degraded read.**
    The floor binds the *swap* path -- launch 1 came to rest on its
    ``capFloor()`` to the wei -- but a backstop rebalance can move the reserve
    where a swap cannot, and launch 1 sits below its own floor today.  Nothing
    here clamps.
    """
    if reserve_wei is None or floor_wei is None:
        return None
    return (reserve_wei - floor_wei) / WEI


def floor_distance_pct(reserve_wei: int | None, floor_wei: int | None) -> float | None:
    """Distance as a percentage of the floor.  ``None`` on a zero floor."""
    if reserve_wei is None or not floor_wei:
        return None
    return (reserve_wei - floor_wei) / floor_wei * 100.0


def burned_supply_pct(burned_wei: int | None, supply_wei: int | None) -> float | None:
    if burned_wei is None or not supply_wei:
        return None
    return burned_wei / supply_wei * 100.0


def backlog_days(backlog_imd: float | None, drip_per_day: float | None) -> float | None:
    """How deep the reward backlog is at the current rate.

    ``None`` when the rate is zero or unread -- **never an infinity**.  Idle
    time beyond ``maxCatchupSeconds`` is forfeited rather than banked, so the
    vault's yield is rate-limited, not flow-limited, and this number is that
    sentence.
    """
    if backlog_imd is None or not drip_per_day or drip_per_day <= 0:
        return None
    return backlog_imd / drip_per_day


def implied_apr_pct(drip_per_day: float | None, tvl_imd: float | None) -> float | None:
    """sIMD APR from the **drip rate and TVL only** — never from fee flow.

    The pool's earnings do not set this number; the dripper's knobs and the
    vault's size do.  ``None`` when TVL is zero or unread, never an infinity.
    """
    if drip_per_day is None or not tvl_imd or tvl_imd <= 0:
        return None
    return drip_per_day * 365.0 / tvl_imd * 100.0


def share_price_delta_pct(
    current: float | None,
    baseline: float | None,
) -> float | None:
    """Change since the session baseline.

    ``None`` until a second reading exists -- **never ``0.0`` as a stand-in**,
    which would render "we have not looked twice" as "nothing moved".
    """
    if current is None or not baseline:
        return None
    return (current - baseline) / baseline * 100.0


def unsettled_legs(
    logs: Sequence[Mapping[str, Any]] | None,
) -> tuple[float | None, float | None]:
    """``(unsettled burn, unsettled stakers)`` in whole IMD.

    Accrued minus settled over the log set.  ``0.0`` means settled up to date
    and is a real answer; ``(None, None)`` means the read failed.  Settlement
    is opportunistic -- it rides the next swap, and ``settleClaims()`` is the
    permissionless way to force it -- so a positive value is an ordinary
    steady-state reading, never an error.
    """
    if logs is None:
        return None, None
    accrued_burn = accrued_stakers = settled_burn = settled_stakers = 0
    for log in logs:
        top = (log.get("topics") or [None])[0]
        words = _log_words(log)
        if top == TOPIC_ACCRUAL and len(words) >= 3:
            accrued_burn += words[1]
            accrued_stakers += words[2]
        elif top == TOPIC_CLAIMS_SETTLED and len(words) >= 2:
            settled_burn += words[0]
            settled_stakers += words[1]
    return (
        (accrued_burn - settled_burn) / WEI,
        (accrued_stakers - settled_stakers) / WEI,
    )


def whole_share_units(decimals: int | None) -> int | None:
    """``10 ** decimals`` — the unit divisor for sIMD, and never a constant.

    ``StakedIMD`` reports ``asset decimals + _decimalsOffset()`` and the offset
    is 6, so Sepolia's vault answers **24**: one whole share is ``1e24`` units,
    not ``1e18``.  Both of the habitual ``/ 1e18`` forms are wrong by a factor
    of a million and **both render as entirely plausible numbers** -- a share
    price of 0.0000013 reads as a dead vault, 21 billion shares read as an
    emissions farm -- so nothing downstream catches them.

    The number is therefore read off the chain rather than hardcoded here.
    The mainnet vault does not exist yet and nothing binds its
    ``_decimalsOffset()`` to Sepolia's; a constant 24 would reproduce this
    defect at the switchover, silently.  A missing or absurd answer is
    ``None`` -- a dark row, not a guessed divisor.
    """
    if decimals is None or not isinstance(decimals, int) or isinstance(decimals, bool):
        return None
    if decimals < 0 or decimals > 36:
        return None
    return 10 ** decimals


def vault_shares(total_shares_raw: int | None, decimals: int | None) -> float | None:
    """Whole sIMD from the raw share count.  ``None`` on an unread ``decimals``."""
    units = whole_share_units(decimals)
    if total_shares_raw is None or not units:
        return None
    return total_shares_raw / units


def backstop_centred(
    backstop_tick_lower: int | None,
    ref_tick: int | None,
    tick_spacing: int | None,
) -> bool | None:
    """Is the backstop sitting where ``rebalance()`` would have put it?

    The backstop is a single-sided position above the current tick, re-centred
    against ``refTick()`` by the permissionless ``rebalance()``.  A re-centre
    can only land on a multiple of ``tickSpacing``, so "centred" is "within one
    spacing of the reference" -- on the committed capture that is
    ``|204180 - 204150| = 30`` against a spacing of ``60``.

    Tri-state on purpose: ``None`` must never render as "centred" nor as a
    confident "not centred".
    """
    if backstop_tick_lower is None or ref_tick is None or not tick_spacing:
        return None
    return abs(backstop_tick_lower - ref_tick) <= abs(tick_spacing)


