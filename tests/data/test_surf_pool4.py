"""``data/surf_pool4`` — selectors, decoders, reconciliation, maths, purity (WP3).

The hostile half of this package lives in ``test_surf_pool4_discovery.py``.
This file covers the rest, and three of its groups are worth naming up front
because each exists to stop a *specific* way a test can be green and wrong.

**Selectors and topics are recomputed, never compared against themselves.**
Every four-byte word and every resolved topic0 is derived from its signature
string with this repo's own keccak, and then checked against a value that came
from somewhere else entirely: ``token()`` and ``bond()`` against live RPC
probes in ``rpc_error_states.json``, ``getHookPermissions()`` against
``hook_flags_reference.json``, and all nine resolved topic0s against the
``topic0_map`` WP1 captured beside the logs.

**The reconciliations are recomputed from the raw fixtures.**
``counter_reconciliation.json`` is *derived*, and WP1 says so.  Reading its
answers back would be a test that cannot fail.  So every number here is summed
out of ``flow_logs_full.json`` and compared against ``hook_state_healthy.json``
and ``token_state.json`` — and the derived file is then checked as a *third*
party that must agree, which is the only thing it is good for.

**The maths tests feed mutated inputs.**  ``measured_split`` must reproduce
1.00 / 89.10 / 9.90 from the committed counters *and* move when a counter
moves; a test that only asserts the documented triple passes for an
implementation that returns it as a constant.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import json
import math
from pathlib import Path

import pytest

from maxpane_dashboard.data import surf_pool4 as P
from maxpane_dashboard.data import surf_v4
from maxpane_dashboard.data.surf_models import (
    POOL4_DISCOVERY_STATES,
    POOL4_FLOW_SIDES,
    Pool4DripperState,
    Pool4FlowEvent,
    Pool4HookState,
    Pool4VaultState,
)

# WP0's machine-readable copy of the frozen shapes.  Imported rather than
# retyped: the three shape changes of 2026-09-02 (the backstop triple, the
# added ``decimals``, ``total_shares_wei`` -> ``total_shares_raw``) each landed
# here as a *collection error* instead of a decoder quietly filling a field
# that no longer exists, which is exactly what a hand-typed list would have
# hidden until a panel went blank.
from tests.data.test_surf_pool4_models import CONSTRUCTOR_KWARGS

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "surf" / "pool4"
WEI = 10 ** 18


def load(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text())


def answers_of(fixture: dict) -> dict[str, str | None]:
    """``call_names`` + ``response`` -> ``{getter: raw hex or None}``.

    A reverting call becomes ``None``, which is what the client will hand the
    decoders: the hook is unverified source, so a getter that answers on
    Sepolia may revert on mainnet, and the round degrades **field by field**
    rather than being dropped.
    """
    by_id = {e["id"]: e for e in fixture["response"]}
    out: dict[str, str | None] = {}
    for call_id, name in fixture["call_names"].items():
        entry = by_id.get(int(call_id), {})
        out[name] = entry.get("result") if "error" not in entry else None
    return out


def logs_of(fixture: dict) -> list[dict]:
    return fixture["response"]["result"]


def _uint_of(raw: str) -> int:
    """One 32-byte word as an integer, for assertions about raw answers."""
    return int(raw, 16)


def words(data: str) -> list[int]:
    body = data[2:] if data.startswith("0x") else data
    return [int(body[64 * i: 64 * (i + 1)], 16) for i in range(len(body) // 64)]


# ---------------------------------------------------------------------------
# 1. Selectors and topics — derived, then corroborated from elsewhere
# ---------------------------------------------------------------------------


def test_every_selector_is_derived_from_its_signature():
    """No four-byte word in this module is pasted.

    The interface was recovered from ``PUSH4`` selectors in **unverified**
    bytecode, so the signature strings are the transcription and the selectors
    are computed from them.  A transposed nibble in a pasted selector would
    read a different function on a live contract and answer plausible garbage.
    """
    for table, sigs in (
        (P.HOOK_SELECTORS, P.HOOK_SIGNATURES),
        (P.VAULT_SELECTORS, P.VAULT_SIGNATURES),
        (P.DRIPPER_SELECTORS, P.DRIPPER_SIGNATURES),
        (P.ERC20_SELECTORS, P.ERC20_SIGNATURES),
    ):
        assert set(table) == set(sigs)
        for name, sig in sigs.items():
            assert table[name] == P.selector(sig)
            assert len(table[name]) == 10


def test_three_selectors_match_values_captured_from_a_live_chain():
    """Corroboration from outside this module, which is the point.

    ``test_every_selector_is_derived_from_its_signature`` compares the module
    against itself and could not catch a wrong *signature string*.  These three
    came off real RPC round trips recorded by WP1.
    """
    errors = load("rpc_error_states")
    probes = {p["label"]: p for p in errors["probes"]}
    assert (
        probes["call_to_an_empty_address"]["request"]["params"][0]["data"]
        == P.HOOK_SELECTORS["token"] == "0xfc0c546a"
    )
    assert (
        probes["unknown_selector_revert"]["request"]["params"][0]["data"]
        == P.selector("bond()") == "0x64c9ec6f"
    )
    ref = load("hook_flags_reference")
    assert P.HOOK_SELECTORS["getHookPermissions"] in ref["source"]
    assert P.HOOK_SELECTORS["getHookPermissions"] == "0xc4e833ce"


def test_the_nine_resolved_topic0s_recompute_from_their_signatures():
    fixture_map = load("flow_logs_mixed")["topic0_map"]
    resolved = {
        t: n for t, n in fixture_map.items() if not n.startswith("UNRESOLVED")
    }
    assert len(resolved) == 9
    for topic, signature in resolved.items():
        assert P.topic0(signature) == topic
        assert P.TOPIC0[topic] == signature


def test_the_three_unresolved_topics_keep_operand_names_and_no_invented_signature():
    """A ~143,640-candidate keccak sweep found no pre-image for these three.

    They are named for what their operands provably are.  Inventing a plausible
    signature string would compute a topic0 that matches no log at all, and the
    flow panel would go *quiet* rather than red — the worst failure shape there
    is, because it looks like a calm market.
    """
    fixture_map = load("flow_logs_mixed")["topic0_map"]
    unresolved = {
        t for t, n in fixture_map.items() if n.startswith("UNRESOLVED")
    }
    assert unresolved == set(P.UNRESOLVED_TOPIC_OPERANDS)
    assert unresolved == {P.TOPIC_ACCRUAL, P.TOPIC_POOL_RESERVE, P.TOPIC_BACKSTOP}
    for topic, shape in P.UNRESOLVED_TOPIC_OPERANDS.items():
        assert P.TOPIC0[topic].startswith("UNRESOLVED")
        assert shape.startswith("(")
        # No signature string anywhere in the module hashes to one of these.
        for sig in P.EVENT_SIGNATURES.values():
            assert P.topic0(sig) != topic


def test_the_topic_map_covers_every_topic_the_captures_contain():
    """A topic in the corpus that this module cannot name is a silent gap."""
    for fixture in ("flow_logs_mixed", "flow_logs_full"):
        for log in logs_of(load(fixture)):
            assert log["topics"][0] in P.TOPIC0, log["topics"][0]


# ---------------------------------------------------------------------------
# 2. The flag word
# ---------------------------------------------------------------------------


def test_the_permission_bits_decode_the_captured_struct():
    """``getHookPermissions()`` on the live launch-3 hook is ``0x2840``.

    The struct is 14 ABI booleans; the mapping onto bits 13..0 is Uniswap's,
    and the fixture records the decoded struct field by field so this test
    checks the *mapping*, not just the total.
    """
    ref = load("hook_flags_reference")
    assert len(P.HOOK_PERMISSION_BITS) == 14
    struct = ref["decoded_permissions"]
    assert [n for n, _ in P.HOOK_PERMISSION_BITS] == list(struct)

    expected = 0
    for name, bit in P.HOOK_PERMISSION_BITS:
        if struct[name]:
            expected |= bit
    assert expected == P.POOL4_REQUIRED_FLAGS == ref["flag_word_int"] == 0x2840
    assert P.decode_hook_permissions(ref["raw_result"]) == expected


def test_the_required_flags_are_three_named_bits_and_not_a_magic_number():
    assert P.POOL4_REQUIRED_FLAGS == (
        P.HOOK_FLAG_BEFORE_INITIALIZE
        | P.HOOK_FLAG_BEFORE_ADD_LIQUIDITY
        | P.HOOK_FLAG_AFTER_SWAP
    )
    assert P.HOOK_FLAG_BEFORE_INITIALIZE == 1 << 13
    assert P.HOOK_FLAG_BEFORE_ADD_LIQUIDITY == 1 << 11
    assert P.HOOK_FLAG_AFTER_SWAP == 1 << 6
    assert P.HOOK_FLAG_MASK == 0x3FFF
    # Neither RETURNS_DELTA bit is set: the hook cannot alter a swap's price
    # or take a delta mid-swap, which is what makes the position its own
    # balance sheet rather than a toll booth.
    assert not P.POOL4_REQUIRED_FLAGS & P.HOOK_FLAG_AFTER_SWAP_RETURNS_DELTA


def test_the_hook_state_captured_from_chain_passes_its_own_gate():
    healthy = load("hook_state_healthy")
    hook = healthy["addresses"]["hook"]
    assert P.has_pool4_flags(hook)
    answers = answers_of(healthy)
    assert P.decode_hook_permissions(answers["getHookPermissions"]) == (
        P.address_flag_word(hook)
    )


@pytest.mark.parametrize(
    "bad",
    [
        # ASCII shapes: absent, empty, prefix-only, junk, short, wrong type.
        None, "", "0x", "not-an-address", "0x1234", 42, b"\x00" * 20,
        "0x" + "z" * 40,
        # Too LONG -- a 32-byte hash must not acquire the flag word of its
        # last fourteen bits (the length test is equality, not a minimum).
        "0x" + "a" * 60 + "2840",
        "0x" + "0" * 37 + "2840",
        # NON-ASCII DIGITS.  ``int(body, 16)`` accepts every Unicode decimal
        # digit and ``body.encode("ascii")`` accepts none of them, so this
        # class is exactly what made these four helpers disagree about what an
        # address is -- three said 0x2840 while the fourth raised
        # UnicodeEncodeError.  The eight ASCII inputs above cannot fail for it.
        "0x" + "\uff10" * 36 + "2840",       # FULLWIDTH DIGIT ZERO
        "0x" + "\u0660" * 36 + "2840",       # ARABIC-INDIC DIGIT ZERO
        "0x" + "\u0966" * 36 + "2840",       # DEVANAGARI DIGIT ZERO
        "0x" + "a" * 39 + "\uff10",          # one non-ASCII nibble among 39
        # Whitespace and separators inside the body.
        "0x" + "0" * 36 + "28 4",
        "0x" + "0" * 36 + "28_4",
        "0x" + "0" * 36 + "28\u202e",
    ],
)
def test_the_flag_helpers_are_total_over_hostile_input(bad):
    """Third-party text reaches these.  Nothing here may raise.

    Four helpers, one answer.  ``address_flag_word``, ``has_pool4_flags``,
    ``is_hook_shaped`` and ``checksum_address`` must agree that a thing is not
    an address, and they now share :func:`_hex_body` so they cannot drift
    apart again.
    """
    assert P.address_flag_word(bad) is None
    assert P.has_pool4_flags(bad) is False
    assert P.is_hook_shaped(bad) is False
    assert P.checksum_address(bad) is None


# ---------------------------------------------------------------------------
# 3. Decoders — every WP1 state fixture round-trips
# ---------------------------------------------------------------------------


def test_hook_state_decodes_every_field_from_the_healthy_capture():
    fx = load("hook_state_healthy")
    a = answers_of(fx)
    state = P.decode_hook_state(a, block_number=fx["block_number"])
    assert isinstance(state, Pool4HookState)

    assert state.token.lower() == fx["addresses"]["token"].lower()
    assert state.pool_manager.lower() == fx["addresses"]["pool_manager"].lower()
    assert state.burn_sink.lower() == fx["addresses"]["burn_sink"].lower()
    assert state.rewards_recipient.lower() == fx["addresses"]["dripper"].lower()
    assert state.pool_id == a["poolId"]
    assert state.backstop_tick_lower == 204_180
    assert state.backstop_tick_upper == 887_220
    assert state.backstop_liquidity == 11_540_192_748_389_887_579_912
    assert state.market_open is True
    assert state.rebalance_enabled is True

    assert state.bps_denominator == 10_000
    assert state.reward_share_bps == 1_000
    assert state.lp_fee == 10_000
    assert state.cap_floor_wei == 250_000_000 * WEI
    assert state.keeper_reward_wei == 2 * 10 ** 15

    assert state.tick_spacing == 60
    assert state.tick_lower == -887_220, "a signed int24 that is actually negative"
    assert state.tick_upper == 887_220
    assert state.ref_tick == 204_150
    assert state.current_tick == 203_988

    assert state.tokens_in_pool_wei == 472_569_750_774_433_805_430_690_446
    assert state.retained_eth_wei == 0, (
        "a real zero: the owner has withdrawn every wei ever collected. It must "
        "not decode to None -- a representable zero is 0, never None"
    )
    assert state.last_claim_block == 11_609_969
    assert state.block_number == fx["block_number"]


def test_the_hook_state_model_still_has_no_vault_field():
    """A3, restated where a producer would be tempted to break it.

    The recovered interface has **no vault getter**.  The path is
    ``hook.rewardsRecipient()`` -> RewardDripper -> ``dripper.vault()``, and a
    ``vault`` field on the hook with nothing behind it is an invitation to fill
    it by scraping the announce channel — the one way this address must never
    be obtained.
    """
    assert not hasattr(Pool4HookState, "vault")
    assert "vault" not in Pool4HookState.__annotations__
    assert "vault" not in P.HOOK_SIGNATURES
    assert "vault" in P.DRIPPER_SIGNATURES


def test_the_partial_capture_degrades_field_by_field():
    """R1 control (a): three reverting getters are three ``None`` fields.

    The reverts are the chain's own — ``bondTerms()``, ``totalBonded()`` and
    ``bond()`` are selectors the launch-3 hook does not implement, picked
    because ``imd.fun/pool4`` advertises a bond tab no deployed contract
    carries.  This is what a differently-built mainnet hook looks like, and it
    must be one ``None`` per dead getter inside an otherwise-healthy payload,
    never a dropped round.
    """
    fx = load("hook_state_partial")
    a = answers_of(fx)
    assert fx["reverting_getters"] == ["bondTerms", "totalBonded", "bond"]
    for name in fx["reverting_getters"]:
        assert a[name] is None

    state = P.decode_hook_state(a)
    healthy = P.decode_hook_state(answers_of(load("hook_state_healthy")))
    assert state == healthy, (
        "three getters this module does not read reverting must change nothing"
    )

    # And every field this module *does* read degrades individually.
    for name in P.HOOK_SIGNATURES:
        one_dead = P.decode_hook_state({**a, name: None})
        assert isinstance(one_dead, Pool4HookState)


def test_vault_state_decodes_the_verified_source_capture():
    fx = load("vault_state")
    state = P.decode_vault_state(answers_of(fx), block_number=fx["block_number"])
    assert isinstance(state, Pool4VaultState)
    assert state.name == "Staked IMD"
    assert state.symbol == "sIMD"
    assert state.asset.lower() == fx["addresses"]["token"].lower()
    assert state.paused is False, "a tri-state that is genuinely False, not None"
    assert state.decimals == 24, (
        "read from the chain: 18 asset decimals plus _decimalsOffset() == 6. "
        "It is asserted here as a *measurement of this capture*, never as a "
        "constant the module may assume -- the mainnet vault does not exist "
        "yet and nothing binds its offset to Sepolia's"
    )
    assert fx["vault_decimals"] == 24
    assert fx["asset_decimals"] + fx["decimals_offset"] == fx["vault_decimals"]
    assert fx["decimals_read_before_the_round"] is True

    # Integers, not floats, for both of these.  ``totalAssets`` is 27,377 IMD
    # **plus one wei**; ``/ 1e18`` renders 27377.000000000004 and any float
    # tolerance wide enough to call that 27,377 is wide enough to hide a real
    # accounting drift.  Same lesson as the 267,300 remainder above.
    assert state.total_assets_wei == 27_377_000_000_000_000_000_001
    assert state.total_assets_wei != 27_377 * WEI, "one wei over a round number"
    assert state.total_shares_raw == 21_010_977_789_124_329_844_268_183_983

    assert state.share_price_wei == 1_302_985_528_554_070_473, (
        "convertToAssets(10 ** decimals) -- assets per ONE WHOLE share, so "
        "1.302985528554070473 IMD/share once the manager divides by 1e18"
    )
    assert P.SHARE_PRICE_CALL == "convertToAssets"
    assert fx["share_price_call"] == P.SHARE_PRICE_CALL
    assert fx["share_price_argument"] == P.whole_share_units(state.decimals) == 10 ** 24

    # SELF-VALIDATING: three independently returned values, no tolerance.
    #
    # This is what makes the capture evidence rather than something trusted.
    # ``totalAssets``, ``totalSupply`` and ``convertToAssets`` came back from
    # three separate calls, and the vault's own conversion has to be the one
    # the other two imply -- exactly, in wei, with the contract's own
    # round-down.  A wrong argument, a stale block or a mis-decoded word all
    # break this identity; none of them breaks a float comparison.
    implied = (
        state.total_assets_wei * (10 ** state.decimals) // state.total_shares_raw
    )
    assert implied == state.share_price_wei
    assert implied - state.share_price_wei == 0


def test_the_wrong_argument_answer_is_kept_as_evidence_and_never_read():
    """The 10^6 trap, proven by the pair rather than described.

    ``convertToAssets_millionth_of_a_share`` is the first capture's question
    re-asked at this block and kept deliberately.  On a 24-decimal vault
    ``1e18`` is a **millionth of a share**, so the answer is honest and the
    question was wrong: 1_302_985_528_554 renders as 0.0000013 IMD/share, a
    vault that looks dead while its share price is 1.302986.

    Two things are pinned here.  The **relationship**, which is what makes the
    fixture evidence: the two answers stand in the ratio ``10 ** (decimals -
    18)`` exactly.  And the **refusal**: :data:`SHARE_PRICE_CALL` is the only
    key the decoder reads, so a producer that asks the wrong question gets a
    dark row rather than a plausible wrong number.  That refusal is why this
    fixture was re-captured instead of the decoder being bent around it.
    """
    fx = load("vault_state")
    a = answers_of(fx)
    assert "convertToAssets_millionth_of_a_share" in a
    wrong = _uint_of(a["convertToAssets_millionth_of_a_share"])
    right = _uint_of(a["convertToAssets"])
    assert wrong == 1_302_985_528_554
    assert right // wrong == 10 ** (fx["vault_decimals"] - 18) == 1_000_000

    # Not a clean multiple: ERC4626 rounds *down*, so asking for a millionth
    # of a share and scaling back up loses 70,473 wei.  Reconstructing the
    # share price from the wrong call is lossy as well as wrong.
    assert wrong * 10 ** 6 != right
    assert right - wrong * 10 ** 6 == 70_473

    # The decoder ignores it.  With the correct key removed, the share price
    # is None -- it does not fall through to the millionth.
    stripped = {k: v for k, v in a.items() if k != P.SHARE_PRICE_CALL}
    assert P.decode_vault_state(stripped).share_price_wei is None
    assert "convertToAssets_1e18" not in a, "superseded by the re-capture"


def test_the_corpus_is_no_longer_single_block():
    """Recorded so nobody writes a test that assumes it is.

    The vault was re-captured at 11614276; the hook, dripper and token
    fixtures deliberately stayed at 11614022 because the assertions above
    stand on those exact bytes.  Nothing needs cross-fixture block agreement:
    the vault capture validates against itself, and every cross-fixture
    assertion in this file compares **addresses**, which do not move with the
    block.
    """
    blocks = {
        name: load(name)["block_number"]
        for name in ("hook_state_healthy", "dripper_state", "token_state",
                     "vault_state", "pool_slot0")
    }
    assert blocks["vault_state"] == 11_614_276
    assert load("vault_state")["supersedes_block"] == 11_614_022
    assert blocks["hook_state_healthy"] == blocks["dripper_state"] == (
        blocks["token_state"]
    ) == 11_614_022
    assert len(set(blocks.values())) == 3, (
        "three distinct blocks -- an assertion that all five agree would be "
        "wrong, not stricter"
    )


def test_dripper_state_decodes_and_names_the_vault():
    """The one hop that has the vault address on it (A3)."""
    fx = load("dripper_state")
    state = P.decode_dripper_state(
        answers_of(fx),
        balance_wei=words(load("token_state")["response"][5]["result"])[0],
        block_number=fx["block_number"],
    )
    assert isinstance(state, Pool4DripperState)
    assert state.vault.lower() == fx["addresses"]["vault"].lower()
    assert state.token.lower() == fx["addresses"]["token"].lower()
    assert state.drip_rate_per_second_wei == WEI
    assert state.max_catchup_seconds == 3_600
    assert state.min_drip_amount_wei == 1_000 * WEI
    assert state.drippable_wei == 3_600 * WEI
    assert state.can_drip is True
    assert state.balance_wei == 36_131_132_021_999_999_999_987_052


def test_the_dripper_vault_matches_the_hooks_rewards_recipient_chain():
    """The whole trust chain in one assertion.

    ``hook.rewardsRecipient()`` names the dripper, and ``dripper.vault()``
    names the vault.  Every address after the adopted hook is read off chain,
    so a single adoption is the only trust decision in the chain — nothing here
    is scraped from a page and nothing is hardcoded for mainnet.
    """
    hook = P.decode_hook_state(answers_of(load("hook_state_healthy")))
    dripper = P.decode_dripper_state(answers_of(load("dripper_state")))
    vault = P.decode_vault_state(answers_of(load("vault_state")))
    addresses = load("hook_state_healthy")["addresses"]

    assert hook.rewards_recipient.lower() == addresses["dripper"].lower()
    assert dripper.vault.lower() == addresses["vault"].lower()
    assert vault.asset.lower() == hook.token.lower()


def test_backstop_decodes_three_words_and_not_the_four_the_prose_claims():
    """``backstop()`` returns ``(int24, int24, uint128)`` on the live hook.

    ``docs/imd_pool4_mechanics.md`` quotes a fourth value (``0.4253 ETH``); the
    return is 96 bytes and carries no such word.  Decoding a fourth word we
    were not given would read past the answer and print a neighbour's memory as
    an ETH balance, so this stops at three.
    """
    raw = {e["id"]: e for e in load("hook_state_healthy")["response"]}[6]["result"]
    assert len(raw) - 2 == 3 * 64
    assert P.decode_backstop(raw) == (204_180, 887_220, 11_540_192_748_389_887_579_912)
    assert P.decode_backstop("0x" + "0" * 128) is None, "two words is not enough"
    assert P.decode_backstop(None) is None
    assert P.decode_backstop("0x") is None

    # ...and the *state* degrades per field rather than all-or-nothing, which
    # is why WP0 replaced the single ``backstop`` field with three.  A hook
    # that answers two of the three words loses one number, not the panel.
    short = P.decode_hook_state({"backstop": "0x" + "0" * 64 + format(7, "064x")})
    assert short.backstop_tick_lower == 0
    assert short.backstop_tick_upper == 7
    assert short.backstop_liquidity is None
    dead = P.decode_hook_state({"backstop": None})
    assert (dead.backstop_tick_lower, dead.backstop_tick_upper,
            dead.backstop_liquidity) == (None, None, None)


def test_pool_state_reuses_surf_v4s_derivation_and_decoders():
    """The v4 half is ``data/surf_v4`` plus ``data/keccak``, not a second copy.

    The fixture's own note says the slots were derived *by*
    ``pool_state_slots``, so this is a round trip through the repo's existing
    module rather than a re-implementation this module could get subtly wrong.
    """
    fx = load("pool_slot0")
    slot0_key, liquidity_key = surf_v4.pool_state_slots(
        fx["pool_id"], fx["mapping_slot"]
    )
    assert slot0_key == fx["slot0_key"]
    assert liquidity_key == fx["liquidity_key"]

    slot0_call, liquidity_call = P.pool_state_calls(fx["pool_id"], fx["mapping_slot"])
    assert slot0_call == P.SEL_EXTSLOAD + fx["slot0_key"][2:]
    assert liquidity_call == P.SEL_EXTSLOAD + fx["liquidity_key"][2:]

    by_id = {e["id"]: e for e in fx["response"]}
    sqrt, tick, lp_fee = surf_v4.decode_slot0(by_id[1]["result"])
    assert sqrt == fx["expected"]["sqrt_price_x96"]
    assert tick == fx["expected"]["tick"]
    assert lp_fee == fx["expected"]["lp_fee"]
    assert surf_v4.decode_liquidity(by_id[2]["result"]) == fx["expected"]["liquidity"]


def test_the_pool_and_the_hook_agree_about_the_same_pool():
    """Two independent reads of one pool, and they have to match.

    ``extsload`` walks ``PoolManager``'s raw storage; ``currentTick()`` and
    ``positionLiquidity()`` are the hook's own view.  They were captured one
    block apart and still agree, which is the cheapest available check that the
    recovered getters mean what their names say.
    """
    hook = P.decode_hook_state(answers_of(load("hook_state_healthy")))
    expected = load("pool_slot0")["expected"]
    assert hook.current_tick == expected["tick"]
    assert hook.lp_fee == expected["lp_fee"]
    assert hook.current_sqrt_price_x96 == expected["sqrt_price_x96"]
    assert hook.position_liquidity == expected["liquidity"]


def test_calldata_builders_produce_well_formed_words():
    addr = "0x000000000000000000000000000000000000dEaD"
    call = P.encode_balance_of(addr)
    assert call.startswith(P.ERC20_SELECTORS["balanceOf"])
    assert len(call) == 10 + 64
    assert call.endswith("dead")

    call = P.encode_convert_to_assets(WEI)
    assert call == P.VAULT_SELECTORS["convertToAssets"] + format(WEI, "064x")
    assert P.encode_getter(P.HOOK_SELECTORS["capFloor"]) == "0x6dd16b2c"


# ---------------------------------------------------------------------------
# 4. Flow logs
# ---------------------------------------------------------------------------


def test_the_mixed_window_decodes_a_buy_a_sell_and_a_bare_settlement():
    """The three shapes, from one 60-block capture.

    A buy takes its 1% in ETH and burns nothing.  A sell takes it in IMD and
    89.1% of the remainder is destroyed.  A settlement with no swap has no
    ``side`` and is therefore not a flow row at all — ``side`` is a closed,
    producer-owned vocabulary and inventing a third member for it would be a
    layout change dressed up as a data change.
    """
    fx = load("flow_logs_mixed")
    rows = P.decode_flow_events(logs_of(fx))
    assert {r.side for r in rows} <= set(POOL4_FLOW_SIDES)

    by_tx = {r.tx_hash: r for r in rows}
    assert "0x832f0efbe3" not in "".join(by_tx), "the bare settlement is not a row"

    buy = next(r for r in rows if r.tx_hash.startswith("0x841e5af58c"))
    assert buy.side == "buy"
    assert buy.burned_wei == 0 and buy.stakers_wei == 0, (
        "a representable zero: buys are not deflationary. None here would read "
        "identically to 'the read failed'"
    )
    assert buy.fee_eth_wei == 99_999_999_999_999
    assert buy.fee_token_wei is None
    assert buy.size_wei == 8_822_655_708_485_988_852_780_915, (
        "the reserve fell by exactly what the buyer received"
    )
    assert buy.ts == 1_788_228_900.0

    sell = next(r for r in rows if r.tx_hash.startswith("0x028d1448a9"))
    assert sell.side == "sell"
    assert sell.fee_token_wei == 84_999_999_999_999_999_999_999
    assert sell.fee_token_wei / WEI == pytest.approx(85_000.0, rel=1e-12)
    assert sell.fee_eth_wei is None
    assert sell.burned_wei + sell.stakers_wei + sell.fee_token_wei == sell.size_wei
    assert sell.size_wei == 8_499_999_999_999_999_999_988_708, (
        "size is read from the accrual plus the fee, never fee * 100 -- the 1% "
        "is what is being measured, not what is being assumed.  The wei-level "
        "shortfall against a round 8,500,000 is the pool's own rounding and is "
        "exactly why it must be read rather than multiplied."
    )
    assert sell.size_wei / WEI == pytest.approx(8_500_000.0, rel=1e-12)


def test_settlement_is_decided_by_log_order_not_by_transaction():
    """Settlement rides the **next** swap, and the amounts prove it.

    In this window ``ClaimsSettled(891.0, 99.0)`` opens tx ``0x48090d111b`` at
    log index 0x7b and matches the accrual in the *previous* transaction
    ``0xd161357a2b`` to the wei — while that transaction's own accrual sits
    later, at log index 0x82.  A same-transaction rule therefore marks the
    settled row unsettled and the unsettled row settled: exactly backwards.

    ``tests/fixtures/surf/pool4/MANIFEST.json`` states the same-transaction
    reading ("a SELL ... and NO settlement in the same tx ... is therefore the
    accrued-but-unsettled case").  The chain disagrees with the manifest and
    the chain wins: under the ordering rule the only outstanding accrual is the
    last one, and ``Sigma accrual - Sigma ClaimsSettled`` agrees with it to the
    wei, which is the independent arithmetic the same-transaction rule fails.
    """
    logs = logs_of(load("flow_logs_mixed"))
    rows = P.decode_flow_events(logs)

    settled_amounts = [
        (words(l["data"])[0], words(l["data"])[1])
        for l in logs if l["topics"][0] == P.TOPIC_CLAIMS_SETTLED
    ]
    accrued = {
        l["transactionHash"]: (words(l["data"])[1], words(l["data"])[2])
        for l in logs if l["topics"][0] == P.TOPIC_ACCRUAL
    }
    # Every accrual but the last has a settlement paying exactly its amounts.
    paid = [tx for tx, amt in accrued.items() if amt in settled_amounts]
    assert len(paid) == len(accrued) - 1

    unpaid = [tx for tx, amt in accrued.items() if amt not in settled_amounts]
    assert len(unpaid) == 1
    outstanding = accrued[unpaid[0]]

    sells = {r.tx_hash: r for r in rows if r.side == "sell"}
    for tx in paid:
        assert sells[tx].settled is True, f"{tx} was paid to the wei"
    assert sells[unpaid[0]].settled is False

    # The wei-exact half of the claim, asserted in integers.
    #
    # A float assertion here would be a test that cannot fail: the outstanding
    # burn leg is 267_299_999_999_999_999_994_537 wei -- 267,300 IMD minus
    # 5,463 wei -- and dividing that by 1e18 lands on exactly 267300.0 in
    # float64, so ``approx(267_300.0)`` passes for any implementation that gets
    # within a few thousand wei of the right answer, including several that are
    # wrong. The integers below are the reconciliation this docstring promises.
    accrued_burn = sum(
        words(l["data"])[1] for l in logs if l["topics"][0] == P.TOPIC_ACCRUAL
    )
    settled_burn = sum(
        words(l["data"])[0] for l in logs if l["topics"][0] == P.TOPIC_CLAIMS_SETTLED
    )
    accrued_stakers = sum(
        words(l["data"])[2] for l in logs if l["topics"][0] == P.TOPIC_ACCRUAL
    )
    settled_stakers = sum(
        words(l["data"])[1] for l in logs if l["topics"][0] == P.TOPIC_CLAIMS_SETTLED
    )
    assert accrued_burn - settled_burn == outstanding[0] == (
        267_299_999_999_999_999_994_537
    )
    assert accrued_stakers - settled_stakers == outstanding[1] == (
        29_699_999_999_999_999_999_393
    )
    assert outstanding[0] != 267_300 * WEI, (
        "the remainder is 5,463 wei short of a round 267,300 -- the pool's own "
        "rounding, and the reason this test compares integers"
    )

    burn, stakers = P.unsettled_legs(logs)
    assert burn == outstanding[0] / WEI
    assert stakers == outstanding[1] / WEI


def test_an_empty_window_is_an_empty_list_and_never_none():
    """Swept and genuinely quiet.  ``[]``, not ``None`` — the distinction is
    the whole difference between "the market is calm" and "the RPC is down".
    """
    fx = load("flow_logs_empty")
    assert fx["log_count"] == 0
    assert P.decode_flow_events(logs_of(fx)) == []
    assert P.reserve_series(logs_of(fx)) == []
    assert P.unsettled_legs(logs_of(fx)) == (0.0, 0.0)

    assert P.decode_flow_events(None) == []
    assert P.reserve_series(None) is None
    assert P.unsettled_legs(None) == (None, None)


def test_the_reserve_series_is_monotonically_non_increasing_and_carries_no_sentinel():
    """The ratchet, as a series.

    Buys take IMD out of the pool and sells do not put it back — 89.1% of a
    sell is destroyed — so the reserve is monotonically non-increasing.  The
    series must carry no sentinel: a ``0`` appended during an outage outlives
    the outage and draws a crash that never happened.
    """
    series = P.reserve_series(logs_of(load("flow_logs_full")))
    assert len(series) == 15
    assert series == sorted(series, key=lambda p: p[0]), "oldest first"
    values = [v for _ts, v in series]
    assert values == sorted(values, reverse=True)
    assert all(v > 0 for v in values), "no zero sentinel is ever appended"
    # The series carries the reserve *after* each buy, so the first point is
    # the first post-buy level and the last is what ``tokensInPool()`` reads.
    assert values[0] == pytest.approx(891_177_344.2915155)
    hook = P.decode_hook_state(answers_of(load("hook_state_healthy")))
    assert values[-1] == pytest.approx(hook.tokens_in_pool_wei / WEI)


def test_flow_rows_are_newest_first():
    rows = P.decode_flow_events(logs_of(load("flow_logs_full")))
    assert rows
    blocks = [r.block_number for r in rows]
    assert blocks == sorted(blocks, reverse=True)


# ---------------------------------------------------------------------------
# 5. R1's cross-checks — recomputed, never read back
# ---------------------------------------------------------------------------


def test_four_counter_reconciliations_hold_to_the_wei():
    """The control that makes the recovered getter set trustworthy here.

    Every number below is summed out of ``flow_logs_full.json`` and compared
    against ``hook_state_healthy.json`` and ``token_state.json``.
    ``counter_reconciliation.json`` is *derived* and is only consulted at the
    end, as a third party that must agree — reading its answers in as the
    expectation would be a test that cannot fail.
    """
    logs = logs_of(load("flow_logs_full"))
    hook = P.decode_hook_state(answers_of(load("hook_state_healthy")))
    token = load("token_state")
    dead_balance = words({e["id"]: e for e in token["response"]}[5]["result"])[0]

    checks = P.reconcile_counters(logs, hook, dead_balance)
    for name, check in checks.items():
        assert check["agree"] is True, f"{name} disagrees by {check['delta_wei']} wei"
        assert check["delta_wei"] == 0

    assert checks["sum_FeeCollected_imd == totalFeeToken()"]["from_logs"] == (
        3_650_057_779_999_999_999_999_983
    )
    assert checks["sum_ClaimsSettled_0 == totalBurned()"]["from_logs"] == (
        325_220_148_197_999_999_999_883_540
    )
    assert checks["sum_ClaimsSettled_1 == totalRewarded()"]["from_logs"] == (
        36_135_572_021_999_999_999_987_052
    )

    # Only now, and only as corroboration.
    derived = load("counter_reconciliation")["checks"]
    for name in ("sum_FeeCollected_imd == totalFeeToken()",
                 "sum_ClaimsSettled_0 == totalBurned()",
                 "sum_ClaimsSettled_1 == totalRewarded()",
                 "totalBurned() == token.balanceOf(0xdEaD)"):
        assert derived[name]["agree"] is True
        assert derived[name]["from_logs"] == checks[name]["from_logs"]


def test_the_eth_check_is_asymmetric_and_a_symmetric_one_would_cry_wolf():
    """A9, and it is a copy decision as much as an arithmetic one.

    ``totalFeeToken()`` is **cumulative**; ``retainedEth()`` is a **current
    balance**.  The owner has withdrawn every wei of ETH fee ever collected, so
    the symmetric check reads 0.0057 vs 0 on a perfectly healthy hook and would
    publish "the recovered interface is wrong" on every owner withdrawal.  What
    holds is ``Sigma FeeCollected[eth] == Sigma FeesWithdrawn[eth] + retainedEth()``.
    """
    logs = logs_of(load("flow_logs_full"))
    hook = P.decode_hook_state(answers_of(load("hook_state_healthy")))

    fee_eth = sum(
        words(l["data"])[1] for l in logs if l["topics"][0] == P.TOPIC_FEE_COLLECTED
    )
    withdrawn_eth = sum(
        words(l["data"])[1] for l in logs if l["topics"][0] == P.TOPIC_FEES_WITHDRAWN
    )
    assert hook.retained_eth_wei == 0
    assert fee_eth == 5_699_999_999_999_985
    assert fee_eth != hook.retained_eth_wei, (
        "the symmetric check that must NOT be published as a defect"
    )
    assert fee_eth == withdrawn_eth + hook.retained_eth_wei

    checks = P.reconcile_counters(logs, hook)
    assert "sum_FeeCollected_eth == retainedEth()" not in checks, (
        "the symmetric check must not exist at all -- a check that is present "
        "and known-failing is a check somebody eventually renders"
    )
    assert checks[
        "sum_FeeCollected_eth == sum_FeesWithdrawn_eth + retainedEth()"
    ]["agree"] is True


def test_a_reconciliation_can_actually_fail():
    """Prove the control bites: move one counter and the check must notice."""
    logs = logs_of(load("flow_logs_full"))
    healthy = answers_of(load("hook_state_healthy"))
    tampered = {**healthy, "totalBurned": "0x" + format(1, "064x")}
    checks = P.reconcile_counters(logs, P.decode_hook_state(tampered))
    assert checks["sum_ClaimsSettled_0 == totalBurned()"]["agree"] is False
    assert checks["sum_ClaimsSettled_0 == totalBurned()"]["delta_wei"] != 0
    assert checks["sum_ClaimsSettled_1 == totalRewarded()"]["agree"] is True

    # An unread counter is not a disagreement -- it is unread.
    #
    # ``agree`` used to be ``from_counter is not None and from_logs ==
    # from_counter``, so this case returned ``False``: byte-identical to the
    # genuine mismatch above. That is the same "we could not look" versus
    # "the value is wrong" conflation the control exists to catch, applied to
    # the control itself -- and the manager decides between "mismatch" and
    # "unchecked" from exactly this dict, so a failed read would have made the
    # dashboard cry wolf on its own day-one detector.
    unread = P.reconcile_counters(logs, P.decode_hook_state({**healthy,
                                                             "totalBurned": None}))
    one = unread["sum_ClaimsSettled_0 == totalBurned()"]
    assert one["from_counter"] is None
    assert one["delta_wei"] is None
    assert one["agree"] is None, "not False -- False is what a mismatch says"
    assert one["state"] == "unchecked"
    # ...and its neighbours are unaffected, so one unread counter is one
    # unchecked identity rather than a dead control.
    assert unread["sum_ClaimsSettled_1 == totalRewarded()"]["state"] == "reconciled"
    assert P.counter_verdict(unread)[0] == "unchecked"


# ---------------------------------------------------------------------------
# 6. The maths — total functions, and none of them can quote the doc
# ---------------------------------------------------------------------------


def test_measured_split_reproduces_the_split_from_the_committed_counters():
    """1.00 / 89.10 / 9.90 — computed, never quoted."""
    hook = P.decode_hook_state(answers_of(load("hook_state_healthy")))
    inference, burn, stakers = P.measured_split(
        hook.total_fee_token_wei, hook.total_burned_wei, hook.total_rewarded_wei
    )
    assert inference == pytest.approx(1.00, abs=1e-9)
    assert burn == pytest.approx(89.10, abs=1e-9)
    assert stakers == pytest.approx(9.90, abs=1e-9)
    assert inference + burn + stakers == pytest.approx(100.0)

    derived = load("counter_reconciliation")["measured_split_pct_from_counters"]
    assert (inference, burn, stakers) == pytest.approx(
        (derived["inference"], derived["burn"], derived["stakers"])
    )


def test_measured_split_moves_when_a_counter_moves():
    """The test above must not be passable by returning the documented triple.

    Doubling the burn leg has to change the answer; if it does not, the
    function is quoting the mechanics doc rather than reading the chain.
    """
    hook = P.decode_hook_state(answers_of(load("hook_state_healthy")))
    base = P.measured_split(
        hook.total_fee_token_wei, hook.total_burned_wei, hook.total_rewarded_wei
    )
    moved = P.measured_split(
        hook.total_fee_token_wei, hook.total_burned_wei * 2, hook.total_rewarded_wei
    )
    assert moved != base
    assert moved[1] > base[1] and moved[2] < base[2]
    assert sum(moved) == pytest.approx(100.0)


def test_split_drift_is_zero_and_zero_is_a_number():
    """``0.0`` is the healthy answer and must render as one, not as a dash.

    Like for like: ``rewardShareBps()`` is a share of the **post-fee** amount,
    so the measured side is ``stakers / (burn + stakers)``.  Comparing against
    the gross share would print a permanent 100 bps drift on a hook behaving
    exactly as documented.
    """
    hook = P.decode_hook_state(answers_of(load("hook_state_healthy")))
    drift = P.split_drift_bps(
        hook.total_burned_wei, hook.total_rewarded_wei,
        hook.reward_share_bps, hook.bps_denominator,
    )
    assert drift is not None
    assert drift == pytest.approx(0.0, abs=1e-6)

    claimed = load("counter_reconciliation")["claimed_share"]
    assert hook.reward_share_bps == claimed["rewardShareBps"] == 1_000
    assert hook.bps_denominator == claimed["BPS_DENOMINATOR"] == 10_000

    # It moves, and in the right direction.
    assert P.split_drift_bps(
        hook.total_burned_wei, hook.total_rewarded_wei * 2,
        hook.reward_share_bps, hook.bps_denominator,
    ) > 0


def test_the_ratchet_numbers_come_out_of_the_capture():
    hook = P.decode_hook_state(answers_of(load("hook_state_healthy")))
    token = load("token_state")
    supply = words({e["id"]: e for e in token["response"]}[1]["result"])[0]

    ratchet = load("counter_reconciliation")["ratchet"]
    assert hook.tokens_in_pool_wei == ratchet["tokensInPool_wei"]
    assert hook.cap_floor_wei == ratchet["capFloor_wei"]
    assert supply == ratchet["total_supply_wei"]

    assert P.floor_distance(hook.tokens_in_pool_wei, hook.cap_floor_wei) == (
        pytest.approx(ratchet["floor_distance_wei"] / WEI)
    )
    assert P.floor_distance_pct(hook.tokens_in_pool_wei, hook.cap_floor_wei) == (
        pytest.approx(89.02790030977353)
    )
    assert P.burned_supply_pct(hook.total_burned_wei, supply) == (
        pytest.approx(ratchet["burned_supply_pct"])
    )


def test_a_reserve_below_its_own_floor_is_a_real_state_and_is_not_clamped():
    """A7.  Launch 1 sits below its own ``capFloor()`` today.

    The floor binds the **swap** path — launch 1's reserve came to rest on
    ``50,000,000.000000000000000000`` exactly — but a backstop rebalance can
    move the reserve where a swap cannot, and launch 1's live
    ``tokensInPool()`` reads 48,849,555.29.  That is a legitimate state, not a
    bug and not a degraded read.  Clamping it to zero distance would erase the
    single most interesting thing the panel can say.
    """
    below = P.floor_distance(48_849_555_290_000_000_000_000_000, 50_000_000 * WEI)
    assert below < 0
    assert below == pytest.approx(-1_150_444.71, abs=0.01)
    assert P.floor_distance_pct(
        48_849_555_290_000_000_000_000_000, 50_000_000 * WEI
    ) < 0

    exactly_on_it = P.floor_distance(50_000_000 * WEI, 50_000_000 * WEI)
    assert exactly_on_it == 0.0, "resting on the floor is zero distance, not None"


def test_whole_share_units_is_read_and_never_a_constant():
    """A14.  Both wrong forms of the habitual ``/ 1e18`` look entirely plausible.

    ``convertToAssets(1e18) / 1e18`` reads 0.0000013 IMD/share (a dead vault)
    and ``totalSupply / 1e18`` reads 21 *billion* shares (an emissions farm).
    Nothing downstream catches either, so the divisor is read off the chain.

    The cross-check is the corroboration: assets / shares must land on the
    share price the contract's own conversion implies.
    """
    vault = P.decode_vault_state(answers_of(load("vault_state")))
    assert P.whole_share_units(vault.decimals) == 10 ** 24
    shares = P.vault_shares(vault.total_shares_raw, vault.decimals)
    assert shares == pytest.approx(21_010.977789, abs=1e-6)

    assets = vault.total_assets_wei / WEI
    assert assets == pytest.approx(27_377.0)
    assert assets / shares == pytest.approx(1.302986, abs=1e-6)

    # The wrong form, stated so the test carries what it is defending against.
    assert vault.total_shares_raw / WEI == pytest.approx(21_010_977_789.12, abs=0.01)

    # Unread, absurd and non-integer decimals are all a dark row, never 1e18.
    for bad in (None, -1, 37, True, 18.0, "24"):
        assert P.whole_share_units(bad) is None
        assert P.vault_shares(vault.total_shares_raw, bad) is None
    assert P.vault_shares(None, 24) is None


def test_no_module_constant_hardcodes_the_share_decimals():
    """The hardcode must not come back wearing a name.

    WP0 refuses a ``POOL4_VAULT_DECIMALS``-style constant in ``surf_models``;
    this is the same refusal one layer out, where the divisor is actually
    applied.
    """
    for name, value in vars(P).items():
        if name.startswith("_") or not isinstance(value, int):
            continue
        assert value not in (24, 10 ** 24), (
            f"{name} = {value} looks like a hardcoded sIMD decimals/divisor; "
            "read decimals() instead"
        )


def test_the_vault_and_dripper_maths():
    dripper = P.decode_dripper_state(answers_of(load("dripper_state")))
    vault = P.decode_vault_state(answers_of(load("vault_state")))
    token = load("token_state")
    backlog = words({e["id"]: e for e in token["response"]}[6]["result"])[0] / WEI

    drip_per_day = dripper.drip_rate_per_second_wei / WEI * 86_400
    assert drip_per_day == 86_400.0

    days = P.backlog_days(backlog, drip_per_day)
    assert days == pytest.approx(418.18, abs=0.01), (
        "over a year deep at the current knobs -- the vault's yield is "
        "rate-limited, not flow-limited"
    )

    tvl = vault.total_assets_wei / WEI
    apr = P.implied_apr_pct(drip_per_day, tvl)
    assert apr == pytest.approx(86_400.0 * 365 / tvl * 100)
    assert apr > 0


def test_backstop_centred_is_tri_state_and_reads_the_capture():
    hook = P.decode_hook_state(answers_of(load("hook_state_healthy")))
    lower = hook.backstop_tick_lower
    assert lower == 204_180 and hook.ref_tick == 204_150 and hook.tick_spacing == 60
    assert P.backstop_centred(lower, hook.ref_tick, hook.tick_spacing) is True

    far = P.backstop_centred(204_180 + 600, hook.ref_tick, hook.tick_spacing)
    assert far is False
    for args in ((None, 1, 60), (1, None, 60), (1, 1, None), (1, 1, 0)):
        assert P.backstop_centred(*args) is None, (
            "None must never render as 'centred' nor as a confident 'not centred'"
        )


@pytest.mark.parametrize(
    "fn, args",
    [
        (P.floor_distance_pct, (WEI, 0)),
        (P.floor_distance_pct, (WEI, None)),
        (P.backlog_days, (1.0, 0.0)),
        (P.backlog_days, (1.0, None)),
        (P.implied_apr_pct, (1.0, 0.0)),
        (P.implied_apr_pct, (1.0, None)),
        (P.split_drift_bps, (0, 0, 1000, 10000)),
        (P.split_drift_bps, (1, 1, 1000, 0)),
        (P.share_price_delta_pct, (1.0, 0.0)),
        (P.share_price_delta_pct, (1.0, None)),
        (P.burned_supply_pct, (1, 0)),
    ],
)
def test_every_zero_denominator_path_returns_none_and_never_an_infinity(fn, args):
    """Four of these are named in the contract as "never an infinity".

    An ``inf`` reaching a widget renders as ``inf`` or as a float format error;
    a ``nan`` compares false against everything including itself and poisons a
    sparkline silently.  ``None`` is the only honest answer for a ratio with no
    denominator.
    """
    result = fn(*args)
    assert result is None
    assert not isinstance(result, float)


def test_share_price_delta_is_none_until_a_second_reading_exists():
    """Never ``0.0`` as a stand-in for "we have not looked twice"."""
    assert P.share_price_delta_pct(1.5, None) is None
    assert P.share_price_delta_pct(None, 1.5) is None
    assert P.share_price_delta_pct(1.5, 1.5) == 0.0, (
        "and once a second reading exists, an unchanged price is a real 0.0"
    )
    assert P.share_price_delta_pct(1.65, 1.5) == pytest.approx(10.0)
    assert P.share_price_delta_pct(1.35, 1.5) == pytest.approx(-10.0)


@pytest.mark.parametrize(
    "fn",
    [
        P.measured_split, P.split_drift_bps, P.floor_distance,
        P.floor_distance_pct, P.burned_supply_pct, P.backlog_days,
        P.implied_apr_pct, P.share_price_delta_pct, P.backstop_centred,
    ],
)
def test_the_maths_are_total_over_all_none(fn):
    """Nothing raises, and nothing returns an ``inf`` or a ``nan``."""
    arity = len(inspect.signature(fn).parameters)
    result = fn(*([None] * arity))
    values = result if isinstance(result, tuple) else (result,)
    for value in values:
        assert value is None or not (
            isinstance(value, float) and (math.isinf(value) or math.isnan(value))
        )


# ---------------------------------------------------------------------------
# 7. Purity, and the vocabularies
# ---------------------------------------------------------------------------

#: Modules ``data/surf_pool4`` may import, and why each is on the list.
#:
#: ``keccak`` and ``surf_v4`` are the plan's frozen boundary (§0.5).
#: ``surf_models`` is added by amendment A5, which requires the closed
#: vocabularies to be *imported* rather than hand-typed by five packages.
#: ``evm_abi`` is the repo's shared, stdlib-only ABI codec -- CLAUDE.md's
#: "reuse before you build" against a boundary table written before it was
#: considered; a second copy of ``strip0x`` here is exactly the divergence that
#: rule exists to stop.
#:
#: Every one of them is re-scanned below, transitively, so the allowance
#: carries its own proof rather than trusting a name.
_ALLOWED_DATA_MODULES = frozenset({
    "maxpane_dashboard.data.keccak",
    "maxpane_dashboard.data.surf_v4",
    "maxpane_dashboard.data.surf_models",
    "maxpane_dashboard.data.evm_abi",
})

#: What purity means here.  ``time`` and ``datetime`` are on it because an
#: injected clock is this repo's rule and a module that reads one cannot be
#: replayed from a committed capture.
_FORBIDDEN = ("httpx", "aiohttp", "textual", "requests", "urllib", "socket",
              "time", "datetime", "random", "asyncio")


def _imported_names(module) -> list[str]:
    """Every dotted name a module's own source imports.

    ``from X import Y`` yields **both** ``X`` and ``X.Y``: yielding only ``X``
    reads a submodule import as a package import, and the recursion below then
    walks an ``__init__`` that imports nothing, which is how a depth-1 version
    of this check goes green over a module that reaches the network two hops
    out (``tests/widgets/test_surf_widget_contract.py`` records that exact
    hole in the widget layer).
    """
    tree = ast.parse(inspect.getsource(module))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            names.append(base)
            names += [f"{base}.{a.name}" if base else a.name for a in node.names]
    return names


def test_surf_pool4_imports_nothing_that_can_reach_a_network_or_a_clock():
    names = _imported_names(P)
    assert names, "an unparsed module would make this vacuous"
    for name in names:
        root = name.split(".")[0]
        assert root not in _FORBIDDEN, f"surf_pool4 imports {name}"
        assert not name.startswith("maxpane_dashboard.widgets")
        assert not name.startswith("maxpane_dashboard.screens")
        assert "surf_client" not in name, "the plan's boundary names this one"
        assert "surf_manager" not in name


def test_surf_pool4_imports_only_the_allowed_data_modules():
    reached = {
        n for n in _imported_names(P)
        if n.startswith("maxpane_dashboard.data.")
        and n.rsplit(".", 1)[0] == "maxpane_dashboard.data"
    }
    assert reached, "the module does import from data/, so this is not vacuous"
    assert reached <= _ALLOWED_DATA_MODULES, sorted(reached - _ALLOWED_DATA_MODULES)


def test_the_allowed_modules_are_themselves_pure_transitively():
    """The allowance carries its own proof.

    A name check alone would be weaker than the ban it relaxes: the moment one
    of the four grows an ``httpx`` import, ``surf_pool4`` has a transitive path
    to the network and the check above stays green.  This one follows every
    ``maxpane_dashboard.*`` name out of an allowed module and scans that one
    too, to a fixed point.
    """
    seen: set[str] = set()
    queue = sorted(_ALLOWED_DATA_MODULES)
    scanned = 0
    while queue:
        name = queue.pop()
        if name in seen:
            continue
        seen.add(name)
        try:
            module = importlib.import_module(name)
        except ImportError:
            continue  # ``X.Y`` that is a function, not a module
        try:
            names = _imported_names(module)
        except (OSError, TypeError, SyntaxError):
            continue
        scanned += 1
        for imported in names:
            root = imported.split(".")[0]
            assert root not in _FORBIDDEN, f"{name} imports {imported}"
            if imported.startswith("maxpane_dashboard."):
                queue.append(imported)
    assert scanned >= len(_ALLOWED_DATA_MODULES)


def test_surf_pool4_contains_no_local_keccak_or_slot_derivation():
    """The v4 half reuses ``data/surf_v4`` and ``data/keccak``, structurally.

    Three copies of a helper means a fix reaches one of them.  This module may
    *call* the derivation; it may not grow its own.
    """
    source = inspect.getsource(P)
    tree = ast.parse(source)
    defined = {
        node.name for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for banned in ("keccak256", "keccak256_hex", "keccak256_text", "_keccak_f1600",
                   "pool_state_slots", "decode_slot0", "decode_liquidity"):
        assert banned not in defined, f"surf_pool4 re-implements {banned}"
    imported = _imported_names(P)
    assert "maxpane_dashboard.data.surf_v4.pool_state_slots" in imported
    assert "maxpane_dashboard.data.keccak.keccak256" in imported


def test_no_module_level_state_is_mutable_after_import():
    """Two imports of a pure module must agree.

    A module that memoised a verdict, cached an answer or stamped a time at
    import would make one test's outcome depend on another's ordering.
    """
    first = importlib.import_module("maxpane_dashboard.data.surf_pool4")
    second = importlib.reload(first)
    assert second.POOL4_REQUIRED_FLAGS == 0x2840
    assert second.HOOK_SELECTORS == P.HOOK_SELECTORS
    assert second.TOPIC0 == P.TOPIC0


def test_the_closed_vocabularies_are_imported_and_never_hand_typed():
    """A5.  Five packages share one spelling of ``"not-discovered"``.

    A hand-typed member is how a payload key silently stops matching the widget
    that renders it, and the failure is a blank panel rather than a red test.
    """
    source = inspect.getsource(P)
    tree = ast.parse(source)
    imported_from_models = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module == "maxpane_dashboard.data.surf_models"
        for alias in node.names
    }
    assert {"POOL4_DISCOVERY_STATES", "POOL4_FLOW_SIDES"} <= imported_from_models

    # The members this module produces are unpacked out of the tuples, so a
    # string literal spelling one of them anywhere outside a docstring or a
    # comment is a retype.
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value in POOL4_DISCOVERY_STATES + POOL4_FLOW_SIDES:
                pytest.fail(
                    f"{node.value!r} is hand-typed at line {node.lineno}; "
                    "unpack it from the imported vocabulary instead"
                )


def test_every_public_name_is_exported():
    """``__all__`` is the surface five other packages code against."""
    for name in P.__all__:
        assert hasattr(P, name), f"__all__ names {name}, which does not exist"
    public = {
        n for n in vars(P)
        if not n.startswith("_")
        and not inspect.ismodule(vars(P)[n])
        and n != "annotations"
        and getattr(vars(P)[n], "__module__", P.__name__) == P.__name__
    }
    # ``WEI`` is a scale constant; the vocabularies are re-exports of
    # ``surf_models``'s own names and belong to that module's surface.
    reexported = {"POOL4_DISCOVERY_STATES", "POOL4_FLOW_SIDES", "POOL4_NETWORKS",
                  "POOL4_DISCOVERY_SOURCES",
                  "POOL4_COUNTER_STATES"}
    missing = public - set(P.__all__) - {"WEI"} - reexported
    assert not missing, f"public but unexported: {sorted(missing)}"


def test_the_decoders_fill_the_frozen_shapes_and_nothing_else():
    """Every decoder's output is exactly ``CONSTRUCTOR_KWARGS``' field list.

    Imported from WP0's copy rather than retyped, so the next rename is a
    collection error here instead of a decoder quietly writing a field that no
    longer exists.  The 2026-09-02 shape change is the worked example: the
    backstop triple, the added ``decimals`` and ``total_shares_wei`` ->
    ``total_shares_raw`` all landed as red tests rather than blank panels.
    """
    import dataclasses

    produced = {
        Pool4HookState: P.decode_hook_state(
            answers_of(load("hook_state_healthy"))
        ),
        Pool4VaultState: P.decode_vault_state(answers_of(load("vault_state"))),
        Pool4DripperState: P.decode_dripper_state(answers_of(load("dripper_state"))),
        Pool4FlowEvent: P.decode_flow_events(logs_of(load("flow_logs_mixed")))[0],
    }
    for model, instance in produced.items():
        names = tuple(f.name for f in dataclasses.fields(instance))
        assert names == CONSTRUCTOR_KWARGS[model], model.__name__
        assert isinstance(instance, model)

    # The three fields the shape change introduced or renamed, named once here
    # so a silent revert of any of them fails.
    assert "backstop" not in CONSTRUCTOR_KWARGS[Pool4HookState]
    assert {"backstop_tick_lower", "backstop_tick_upper", "backstop_liquidity"} <= (
        set(CONSTRUCTOR_KWARGS[Pool4HookState])
    )
    assert "decimals" in CONSTRUCTOR_KWARGS[Pool4VaultState]
    assert "total_shares_wei" not in CONSTRUCTOR_KWARGS[Pool4VaultState]
    assert "total_shares_raw" in CONSTRUCTOR_KWARGS[Pool4VaultState]


# ---------------------------------------------------------------------------
# The counter control's four states (W1)
# ---------------------------------------------------------------------------
#
# R1 control (c) is the day-one detector for a decoder recovered from bytecode
# selectors having an operand order wrong, and a detector is only worth having
# if it is believed when it fires. That means it has to be silent -- and
# visibly silent -- whenever it cannot run. Two ways it could not: a side was
# unread, or the sweep covers a trailing window rather than the hook's life.


def _reconcile(fixture="flow_logs_full", hook_overrides=None, dead=True):
    logs = None if fixture is None else logs_of(load(fixture))
    answers = {**answers_of(load("hook_state_healthy")), **(hook_overrides or {})}
    token = load("token_state")
    dead_balance = (
        words({e["id"]: e for e in token["response"]}[5]["result"])[0] if dead else None
    )
    return P.reconcile_counters(logs, P.decode_hook_state(answers), dead_balance)


def test_a_failed_sweep_is_unchecked_and_never_a_set_of_zero_sums():
    """``logs=None`` must not sum to zero and then report five mismatches.

    ``for log in logs or ()`` turned a failed read into nine zero sums, which
    then compared unequal against five live counters -- so an RPC outage
    rendered as *five simultaneous mismatches* on the one control whose whole
    value is being believed when it fires. A failed read is ``None``, never
    ``0``, and that rule applies to a sum as much as to a counter.
    """
    checks = _reconcile(fixture=None)
    assert len(checks) == 5
    for name, check in checks.items():
        assert check["from_logs"] is None, f"{name} manufactured a zero sum"
        assert check["state"] == "unchecked", name
        assert check["agree"] is None, name
        assert check["delta_wei"] is None, name
    assert P.counter_verdict(checks) == (
        "unchecked", "5 of 5 identities could not be computed",
    )


def test_a_trailing_window_is_window_limited_and_explicitly_not_a_pass():
    """The state that keeps the control from crying wolf for ever.

    Every identity here is a *cumulative* counter against a sum of **all**
    logs, while the manager sweeps a trailing window. Once the hook is older
    than that window the sums are short by everything preceding it and all
    five disagree **by construction** -- permanently. Reporting that as
    ``mismatch`` would retire the control as surely as deleting it.

    ``flow_logs_mixed.json`` is a sixty-block window over a hook that was
    already running, so it is exactly that case.
    """
    checks = _reconcile("flow_logs_mixed")
    for name, check in checks.items():
        assert check["state"] == "window-limited", name
        assert check["agree"] is None, (
            f"{name}: window-limited is not a pass, and not a failure either"
        )
        assert check["agree"] is not True, "explicitly NOT a pass"
        assert check["delta_wei"] is None, (
            f"{name}: the shortfall is a fact about the sweep, not the hook, "
            "so publishing it as a delta would invite a reader to act on it"
        )
    state, detail = P.counter_verdict(checks)
    assert state == "window-limited"
    assert "first block" in detail

    # The sums really are short -- so a naive check would have said mismatch.
    hook = P.decode_hook_state(answers_of(load("hook_state_healthy")))
    assert checks["sum_ClaimsSettled_0 == totalBurned()"]["from_logs"] < (
        hook.total_burned_wei
    )


def test_the_complete_sweep_still_reconciles_and_is_the_only_pass():
    checks = _reconcile("flow_logs_full")
    for name, check in checks.items():
        assert check["state"] == "reconciled", name
        assert check["agree"] is True, name
        assert check["delta_wei"] == 0, name
    assert P.counter_verdict(checks) == (
        "reconciled", "all 5 identities hold to the wei",
    )


def test_completeness_is_the_constructors_own_emission_not_any_ownership_change():
    """The genesis marker, and why the zero ``previousOwner`` is load-bearing.

    ``Ownable``'s constructor emits ``OwnershipTransferred(address(0), owner)``
    exactly once and no log of this contract can precede it, so its presence
    answers "does this sweep cover the whole history?" without trusting a
    caller-supplied deployment block or doing arithmetic on window bounds.

    A *later* ``transferOwnership`` emits the same topic0 with a non-zero first
    operand. Testing the topic alone would read an ownership change as a birth
    certificate and call a trailing window complete -- which is the failure
    that turns ``window-limited`` back into a false ``reconciled``.
    """
    full = logs_of(load("flow_logs_full"))
    assert P.logs_reach_genesis(full) is True

    genesis = [
        l for l in full if l["topics"][0] == P.TOPIC_OWNERSHIP_TRANSFERRED
    ]
    assert len(genesis) == 1
    assert int(genesis[0]["topics"][1], 16) == 0, "previousOwner is address(0)"
    assert int(genesis[0]["topics"][2], 16) != 0, "newOwner is the deployer"
    earliest = min(full, key=lambda l: (int(l["blockNumber"], 16),
                                        int(l["logIndex"], 16)))
    assert earliest is genesis[0], (
        "the birth certificate must be the earliest log in a complete set"
    )

    assert P.logs_reach_genesis(logs_of(load("flow_logs_mixed"))) is False
    assert P.logs_reach_genesis(logs_of(load("flow_logs_empty"))) is False
    assert P.logs_reach_genesis(None) is None, "unread, not incomplete"

    # A later ownership change, with a real previous owner, is not a genesis.
    later = {**genesis[0], "topics": [genesis[0]["topics"][0],
                                      "0x" + "0" * 24 + "a" * 16,
                                      genesis[0]["topics"][2]]}
    assert P.logs_reach_genesis([later]) is False
    # And a malformed or unindexed one is not either, rather than raising.
    assert P.logs_reach_genesis([{"topics": [P.TOPIC_OWNERSHIP_TRANSFERRED]}]) is False
    assert P.logs_reach_genesis([{"topics": [P.TOPIC_OWNERSHIP_TRANSFERRED,
                                             "nonsense", "x"]}]) is False
    assert P.logs_reach_genesis([{}]) is False


def test_counter_verdict_precedence_and_that_nothing_folds_to_none():
    """``mismatch`` > ``window-limited`` > ``unchecked`` > ``reconciled``.

    ``unchecked`` outranking ``reconciled`` is the one worth stating: "four of
    five held and the fifth was unread" must not render as a clean bill of
    health.
    """
    def fold(*states):
        return P.counter_verdict({
            f"check {i}": {"state": st, "agree": None, "delta_wei":
                           -1 if st == "mismatch" else None,
                           "from_logs": 0, "from_counter": 0}
            for i, st in enumerate(states)
        })[0]

    assert fold("reconciled", "reconciled") == "reconciled"
    assert fold("reconciled", "unchecked") == "unchecked"
    assert fold("reconciled", "unchecked", "window-limited") == "window-limited"
    assert fold("reconciled", "unchecked", "window-limited", "mismatch") == (
        "mismatch"
    )
    assert fold("mismatch") == "mismatch"

    # Nothing to fold is None, not a manufactured verdict about counters
    # nobody read.
    assert P.counter_verdict({}) == (None, None)
    assert P.counter_verdict(None) == (None, None)

    # Every state it can produce is a member of the frozen vocabulary.
    from maxpane_dashboard.data.surf_models import POOL4_COUNTER_STATES
    for fixture in (None, "flow_logs_full", "flow_logs_mixed", "flow_logs_empty"):
        state, detail = P.counter_verdict(_reconcile(fixture))
        assert state in POOL4_COUNTER_STATES
        assert isinstance(detail, str) and detail


def test_the_mismatch_detail_names_the_worst_offender():
    """A verdict a reader can act on has to say *which* identity and by how much."""
    logs = logs_of(load("flow_logs_full"))
    healthy = answers_of(load("hook_state_healthy"))
    tampered = {
        **healthy,
        "totalBurned": "0x" + format(1, "064x"),
        "totalRewarded": "0x" + format(
            36_135_572_021_999_999_999_987_052 - 5, "064x"),
    }
    checks = P.reconcile_counters(logs, P.decode_hook_state(tampered))
    state, detail = P.counter_verdict(checks)
    assert state == "mismatch"
    assert "totalBurned" in detail, (
        "the burn leg is out by 3.25e26 wei and the reward leg by 5 -- the "
        "detail names the larger one"
    )
    assert "wei" in detail
    assert checks["sum_ClaimsSettled_1 == totalRewarded()"]["delta_wei"] == 5


def test_a_log_sum_larger_than_its_counter_is_a_mismatch_even_in_a_short_window():
    """The sign of the delta outranks completeness, because arithmetic says so.

    Truncation removes addends, so a windowed sum can only ever be *smaller*
    than the monotone total it is compared against. A log sum that is LARGER is
    unexplainable by any window however narrow, and asking "is the sweep
    complete?" first files it as ``window-limited`` and goes silent -- a false
    negative on the one control whose entire value is being believed when it
    fires.

    It is also the shape the control most exists to catch. The hook's decoders
    were recovered from bytecode selectors; an operand read from the wrong
    position produces *arbitrary* sums, roughly half of them too big, while
    truncation is always one-signed.
    """
    logs = logs_of(load("flow_logs_mixed"))
    assert P.logs_reach_genesis(logs) is False, "an incomplete sweep, deliberately"

    # Counters set BELOW the window's own sums: impossible from truncation.
    healthy = answers_of(load("hook_state_healthy"))
    tiny = {
        **healthy,
        "totalBurned": "0x" + format(1, "064x"),
        "totalRewarded": "0x" + format(1, "064x"),
        "totalFeeToken": "0x" + format(1, "064x"),
    }
    checks = P.reconcile_counters(logs, P.decode_hook_state(tiny), dead_balance_wei=1)
    for name in ("sum_FeeCollected_imd == totalFeeToken()",
                 "sum_ClaimsSettled_0 == totalBurned()",
                 "sum_ClaimsSettled_1 == totalRewarded()",
                 "totalBurned() == token.balanceOf(0xdEaD)"):
        assert checks[name]["state"] == "mismatch", (
            f"{name}: a positive delta cannot be truncation"
        )
        assert checks[name]["agree"] is False
        assert checks[name]["delta_wei"] > 0
    assert P.counter_verdict(checks)[0] == "mismatch"

    # And the same counters over a COMPLETE sweep are a mismatch too -- the
    # hatch changes when the verdict is reached, never what it is.
    full = P.reconcile_counters(
        logs_of(load("flow_logs_full")), P.decode_hook_state(tiny), 1)
    assert P.counter_verdict(full)[0] == "mismatch"


def test_the_mirror_case_stays_window_limited_because_it_is_ambiguous():
    """A SHORT sum in an incomplete sweep gets no hatch, and must not.

    This is the mirror the sign argument does *not* extend to. Truncation and a
    genuine shortfall both look like "too small by an unknown amount", and no
    arithmetic available here separates them. ``window-limited`` is the honest
    answer *because* they are indistinguishable, not because the case was
    overlooked -- calling it ``mismatch`` would cry wolf on every sweep after
    the hook's first day.

    The same shortfall over a *complete* sweep is a mismatch, which is what
    makes this a statement about the evidence rather than about the number.
    """
    logs = logs_of(load("flow_logs_mixed"))
    hook = P.decode_hook_state(answers_of(load("hook_state_healthy")))
    checks = P.reconcile_counters(logs, hook)
    burn = checks["sum_ClaimsSettled_0 == totalBurned()"]
    assert burn["from_logs"] < burn["from_counter"], "short, as truncation is"
    assert burn["state"] == "window-limited"
    assert burn["agree"] is None
    assert burn["delta_wei"] is None

    # Byte-identical numbers, complete evidence -> mismatch.
    forged = [*logs_of(load("flow_logs_full"))]
    genesis = next(
        l for l in forged if l["topics"][0] == P.TOPIC_OWNERSHIP_TRANSFERRED)
    trimmed = [l for l in forged if l is not genesis]
    assert P.logs_reach_genesis(trimmed) is False
    assert P.reconcile_counters(trimmed, hook)[
        "sum_ClaimsSettled_0 == totalBurned()"]["state"] == "window-limited"
    assert P.reconcile_counters(forged, hook)[
        "sum_ClaimsSettled_0 == totalBurned()"]["state"] == "reconciled"


def test_the_eth_identity_is_excluded_from_the_sign_hatch():
    """The one check whose delta has no determined sign under any window.

    Identities one to four compare a windowed sum against a **monotone total**
    -- a cumulative counter, or the ``0xdEaD`` balance, which is non-decreasing
    because nobody holds that key -- so a subset is short unconditionally.

    The ETH identity is different: a windowed sum on the left, a windowed sum
    **plus a current balance** on the right. Both sides move with the window,
    so the reduction to ``Sigma_before(withdrawn) - Sigma_before(fee) <= 0``
    holds only for a *trailing* window. The production sweep is trailing, but
    that is the caller's choice and not this function's precondition.

    ``flow_logs_mixed.json`` proves the difference is real and not theoretical:
    it is a mid-history window whose two ``FeesWithdrawn`` both land *after*
    it, so the ETH check reads **+2e14 on a perfectly healthy hook**. With the
    hatch applied it would report a mismatch -- the hatch's own failure mode,
    pointed the other way.
    """
    logs = logs_of(load("flow_logs_mixed"))
    hook = P.decode_hook_state(answers_of(load("hook_state_healthy")))
    eth = P.reconcile_counters(logs, hook)[
        "sum_FeeCollected_eth == sum_FeesWithdrawn_eth + retainedEth()"]

    assert eth["from_logs"] > eth["from_counter"], (
        "a positive delta -- and the reason this check cannot take the hatch"
    )
    assert eth["from_logs"] - eth["from_counter"] == 199_999_999_999_998
    assert eth["state"] == "window-limited", (
        "healthy hook, mid-history window: not a mismatch"
    )
    assert eth["agree"] is None

    # The withdrawals really are outside and after the window -- the fixture's
    # own blocks are the evidence, so this test cannot pass by coincidence.
    full = load("flow_logs_full")
    mixed = load("flow_logs_mixed")
    withdrawals = [
        int(l["blockNumber"], 16) for l in logs_of(full)
        if l["topics"][0] == P.TOPIC_FEES_WITHDRAWN
    ]
    assert len(withdrawals) == 2
    assert all(b > mixed["to_block"] for b in withdrawals)

    # Over the complete sweep the identity holds exactly (A9).
    assert P.reconcile_counters(logs_of(full), hook)[
        "sum_FeeCollected_eth == sum_FeesWithdrawn_eth + retainedEth()"
    ]["state"] == "reconciled"


# ---------------------------------------------------------------------------
# S17 - sums that outlive the window
# ---------------------------------------------------------------------------
#
# The identities are cumulative counters against a sum of ALL logs, while the
# sweep reads a trailing 7,200-block window, so from about a day after
# deployment every check is window-limited for ever. Accumulating forward from
# genesis is the fix (the LaunchpadState.cursor precedent: a total cannot be
# recovered from its newest addend). The whole question is whether the total
# can HONESTLY claim to have no hole in it.


def _windows(logs, cuts):
    return [
        (f, t, [l for l in logs if f <= int(l["blockNumber"], 16) <= t])
        for f, t in cuts
    ]


def test_accumulating_three_windows_equals_summing_them_at_once():
    """The arithmetic, before any of the invariants.

    Three consecutive windows folded forward must produce byte-identical totals
    to one sweep over the union -- otherwise the accumulator is not the same
    measurement, and every claim built on it is about a different number.
    """
    full = load("flow_logs_full")
    logs = logs_of(full)
    lo, hi = full["from_block"], full["to_block"]
    acc = P.empty_accumulator()
    for f, t, window in _windows(logs, [(lo, lo + 150), (lo + 151, lo + 280),
                                        (lo + 281, hi)]):
        acc = P.accumulate_counters(acc, window, f, t)
    assert acc["genesis_block"] == 11_609_650
    assert acc["cursor_block"] == hi
    assert acc["sums"] == {k: v for k, v in P._sum_logs(logs).items()}


def test_an_accumulator_reaches_reconciled_where_a_window_cannot():
    """The point of the whole exercise.

    The same counters, the same logs: read as one trailing window the control
    is window-limited and detects nothing; accumulated from genesis and aligned
    with the counter read, it reconciles to the wei.
    """
    full = load("flow_logs_full")
    logs = logs_of(full)
    hook = P.decode_hook_state(answers_of(load("hook_state_healthy")),
                               block_number=full["to_block"])
    token = load("token_state")
    dead = words({e["id"]: e for e in token["response"]}[5]["result"])[0]

    acc = P.accumulate_counters(P.empty_accumulator(), logs,
                                full["from_block"], full["to_block"])
    assert P.accumulator_covers(acc, hook.block_number) is True
    assert P.counter_verdict(
        P.reconcile_counters(None, hook, dead, accumulator=acc)
    ) == ("reconciled", "all 5 identities hold to the wei")

    # A trailing window over the same hook, with no accumulator: silent.
    tail = logs_of(load("flow_logs_mixed"))
    assert P.counter_verdict(P.reconcile_counters(tail, hook, dead))[0] == (
        "window-limited"
    )


def test_an_accumulator_must_be_seeded_at_genesis_and_refuses_otherwise():
    """Invariant one. Nothing but the birth certificate can start a total.

    A window that does not contain ``OwnershipTransferred(address(0), owner)``
    cannot prove its sums start at the beginning, so folding it in would
    produce a total that is short by an unknown amount and looks exactly like a
    complete one.
    """
    mixed = load("flow_logs_mixed")
    acc = P.accumulate_counters(P.empty_accumulator(), logs_of(mixed),
                                mixed["from_block"], mixed["to_block"])
    assert acc == P.empty_accumulator(), "unseeded, and claiming nothing"
    assert acc["genesis_block"] is None
    assert P.accumulator_covers(acc, mixed["to_block"]) is False

    # An empty accumulator's zero sums must never read as a measurement.
    hook = P.decode_hook_state(answers_of(load("hook_state_healthy")),
                               block_number=mixed["to_block"])
    assert P.counter_verdict(
        P.reconcile_counters(None, hook, None, accumulator=acc)
    )[0] == "window-limited"


def test_a_gap_discards_the_accumulator_rather_than_being_papered_over():
    """Invariant two, and the judgement behind it.

    A total short by a missed sweep is indistinguishable from a total short
    because a decoder is wrong -- the same ambiguity as the mirror case. So a
    gap is not patched and not tolerated: the accumulator is thrown away, and
    the control falls back to single-window behaviour until a sweep containing
    genesis reseeds it. Losing two months of accumulation is cheap; a total
    that says ``reconciled`` when it means ``probably`` is not.
    """
    full = load("flow_logs_full")
    logs = logs_of(full)
    lo, hi = full["from_block"], full["to_block"]
    seeded = P.accumulate_counters(P.empty_accumulator(),
                                   [l for l in logs
                                    if int(l["blockNumber"], 16) <= lo + 150],
                                   lo, lo + 150)
    assert seeded["genesis_block"] is not None

    # Contiguous: from_block is exactly cursor + 1.
    contiguous = P.accumulate_counters(seeded, [], lo + 151, lo + 200)
    assert contiguous["genesis_block"] == seeded["genesis_block"]
    assert contiguous["cursor_block"] == lo + 200

    # One block of hole is a hole.
    holed = P.accumulate_counters(seeded, [], lo + 152, lo + 200)
    assert holed == P.empty_accumulator(), "discarded, not patched"

    # An overlapping re-sweep is idempotent, never double-counted.
    again = P.accumulate_counters(
        seeded, [l for l in logs if int(l["blockNumber"], 16) <= lo + 150],
        lo, lo + 150)
    assert again["sums"] == seeded["sums"]
    assert again["cursor_block"] == seeded["cursor_block"]


def test_a_failed_sweep_advances_nothing_and_loses_nothing():
    """Not counting is not the same as counting zero.

    An RPC outage must neither advance the cursor (which would manufacture a
    hole at the next window) nor reset the total (which would throw away
    months of accumulation for a transient failure).
    """
    full = load("flow_logs_full")
    seeded = P.accumulate_counters(P.empty_accumulator(), logs_of(full),
                                   full["from_block"], full["to_block"])
    after = P.accumulate_counters(seeded, None, full["to_block"] + 1,
                                  full["to_block"] + 50)
    assert after == seeded

    # And the next successful sweep still reaches back over the missed span,
    # so a short outage costs nothing at all.
    resumed = P.accumulate_counters(after, [], full["to_block"] + 1,
                                    full["to_block"] + 50)
    assert resumed["genesis_block"] == seeded["genesis_block"]
    assert resumed["sums"] == seeded["sums"]


def test_alignment_is_required_and_is_the_invariant_that_is_easy_to_miss():
    """Continuity alone is not enough, and this is the case that shows it.

    The sums cover ``[genesis, cursor]``; the counters cover
    ``[genesis, at_block]``. If those differ the identity is being asked to
    hold across two different moments. A cursor BEHIND the counter makes the
    sums short -- and because continuity says the evidence is complete, that
    short sum reads as a **mismatch**: a false alarm on every tick where a swap
    lands between the two reads. A cursor AHEAD makes the sums large, which the
    sign hatch also calls a mismatch.

    So the answer when they disagree is window-limited, and the fix belongs to
    the caller: read state at a pinned block and sweep logs to that same block.
    """
    full = load("flow_logs_full")
    acc = P.accumulate_counters(P.empty_accumulator(), logs_of(full),
                                full["from_block"], full["to_block"])
    cursor = acc["cursor_block"]
    token = load("token_state")
    dead = words({e["id"]: e for e in token["response"]}[5]["result"])[0]

    assert P.accumulator_covers(acc, cursor) is True
    for at in (cursor - 1, cursor + 1, None, "0xb13746"):
        assert P.accumulator_covers(acc, at) is False, at

    # Behind the counter: short sums that continuity would otherwise certify.
    behind = P.decode_hook_state(answers_of(load("hook_state_healthy")),
                                 block_number=cursor + 5_000)
    verdict = P.counter_verdict(
        P.reconcile_counters(None, behind, dead, accumulator=acc))
    assert verdict[0] == "window-limited", (
        "misalignment must not be certified as complete and then reported as "
        "a mismatch"
    )
    assert "accumulated sums stop at block" in verdict[1]

    # Aligned, the same numbers reconcile.
    aligned = P.decode_hook_state(answers_of(load("hook_state_healthy")),
                                  block_number=cursor)
    assert P.counter_verdict(
        P.reconcile_counters(None, aligned, dead, accumulator=acc))[0] == (
        "reconciled")


def test_a_hand_edited_accumulator_is_loud_rather_than_silently_believed():
    """The cache is third-party input here too, and the control self-checks.

    Unlike the discovery cache -- where a forged claim pointed the dashboard at
    an attacker's contract and nothing re-checked it -- a forged accumulator is
    compared against the chain's own counters on the very next tick, which is
    what the identity IS. Tampering therefore produces a **mismatch**, which is
    loud, rather than a silent false ``reconciled``.

    The residual is a total forged to match the counter exactly, which would
    mask a decoder bug. That requires knowing the counter and wanting to hide
    our own defect from us, and the blast radius is a diagnostic word rather
    than a money decision -- so it is recorded, not defended against.
    """
    full = load("flow_logs_full")
    hook = P.decode_hook_state(answers_of(load("hook_state_healthy")),
                               block_number=full["to_block"])
    acc = P.accumulate_counters(P.empty_accumulator(), logs_of(full),
                                full["from_block"], full["to_block"])

    inflated = {**acc, "sums": {**acc["sums"],
                                "settled_burn": acc["sums"]["settled_burn"] * 2}}
    state, detail = P.counter_verdict(P.reconcile_counters(
        None, hook, None, accumulator=inflated))
    assert state == "mismatch", "a positive delta, caught by the sign hatch"
    assert "totalBurned" in detail

    deflated = {**acc, "sums": {**acc["sums"], "settled_burn": 1}}
    assert P.counter_verdict(P.reconcile_counters(
        None, hook, None, accumulator=deflated))[0] == "mismatch"


def test_a_malformed_accumulator_is_unchecked_and_never_raises():
    """WP7 persists this to JSON, so every shape below is a real cache file."""
    full = load("flow_logs_full")
    hook = P.decode_hook_state(answers_of(load("hook_state_healthy")),
                               block_number=full["to_block"])
    for junk in (None, {}, {"sums": None}, {"genesis_block": 1},
                 {"genesis_block": 1, "cursor_block": "x", "sums": {}},
                 {"genesis_block": 1, "cursor_block": full["to_block"],
                  "sums": "nonsense"},
                 {"genesis_block": 1, "cursor_block": full["to_block"],
                  "sums": {"fee_imd": None}}):
        checks = P.reconcile_counters(None, hook, None, accumulator=junk)
        state, _detail = P.counter_verdict(checks)
        assert state in ("window-limited", "unchecked"), junk
        assert state != "reconciled"

    for junk in (None, "x", 42, [], {"genesis_block": None}):
        assert P.accumulator_covers(junk, 1) is False
        assert isinstance(P.accumulate_counters(junk, [], 1, 2), dict)

    assert P.accumulate_counters(P.empty_accumulator(), [], None, 2) == (
        P.empty_accumulator())


# ---------------------------------------------------------------------------
# MAINNET 2026-09-02 - the reward leg is three-way, and bonding has no getter
# ---------------------------------------------------------------------------

#: Live mainnet reads, 2026-09-02.  Wei, so the assertions below are exact.
_MN_BURNED = 59_480_700_000_000_000_000
_MN_REWARDED = 10_496_600_000_000_000_000
_MN_FEE_TOKEN = 843_700_000_000_000_000


def test_bonding_is_derived_as_the_remainder_and_never_hardcoded():
    """No ``bondingBps()`` exists, so the number must be computed or absent.

    The split has already moved once -- ``rewardShareBps`` 1000 -> 1500 between
    Sepolia and mainnet -- so a typed constant goes stale in silence the day it
    moves again. And the honest signature of a derived value is that it goes
    ``None`` whenever EITHER input does, which is what distinguishes it from a
    constant: a value that is always present is not derived from anything.
    """
    assert P.bonding_bps(3000, 3000, 10000) == 4000

    # It moves with its inputs, which a constant would not.
    assert P.bonding_bps(2000, 3000, 10000) == 5000
    assert P.bonding_bps(3000, 3000, 20000) == 14000
    assert P.bonding_bps(5000, 5000, 10000) == 0, "a real zero, not None"

    # None on any gap -- the split_drift_bps precedent.
    for args in ((None, 3000, 10000), (3000, None, 10000), (3000, 3000, None),
                 (None, None, None)):
        assert P.bonding_bps(*args) is None, args

    # A negative remainder is published, not clamped: two legs exceeding the
    # denominator is a fact about the contract and the panel may say so.
    assert P.bonding_bps(7000, 5000, 10000) == -2000


def test_no_bonding_constant_exists_anywhere_in_the_module():
    """The hardcode must not come back wearing a name.

    Same refusal as the sIMD decimals sweep: a module-level ``4000`` (or a
    ``bonding``-shaped constant of any value) would reproduce exactly the
    staleness the derivation exists to prevent.
    """
    for name, value in vars(P).items():
        if name.startswith("_") or not isinstance(value, int):
            continue
        assert value != 4000, f"{name} = 4000 looks like a hardcoded bonding share"
        assert "bonding" not in name.lower(), (
            f"{name} is a bonding constant; bonding has no getter and no constant"
        )

    # And there is no boolean saying the value is derived -- a flag that can
    # only ever be True is a constant dressed as data.
    assert not any(
        "derived" in n.lower() and isinstance(v, bool) for n, v in vars(P).items()
    )


def test_the_reward_leg_subdivides_into_the_live_mainnet_shape():
    """85 / 4.5 / 6.0 / 4.5 per 100 IMD retired, computed from live reads.

    Not quoted from the doc: the counters go in, the shape comes out, and the
    mutation battery moves an input to prove the numbers are not a constant.
    """
    inference, burn, reward = P.measured_split(
        _MN_FEE_TOKEN, _MN_BURNED, _MN_REWARDED)
    # Of the RETIRED amount (post-fee), which is what the doc's shape is per.
    retired_burn = _MN_BURNED / (_MN_BURNED + _MN_REWARDED) * 100
    retired_reward = _MN_REWARDED / (_MN_BURNED + _MN_REWARDED) * 100
    assert retired_burn == pytest.approx(85.00, abs=0.01)
    assert retired_reward == pytest.approx(15.00, abs=0.01)

    staking, bonding, nodes = P.reward_leg_split(retired_reward, 3000, 3000, 10000)
    assert staking == pytest.approx(4.5, abs=0.01)
    assert bonding == pytest.approx(6.0, abs=0.01)
    assert nodes == pytest.approx(4.5, abs=0.01)
    assert retired_burn + staking + bonding + nodes == pytest.approx(100.0)

    # The gross three-way still sums to 100 and still reports the WHOLE reward
    # share as its third leg -- which is the thing that must not be labelled
    # "stakers".
    assert inference + burn + reward == pytest.approx(100.0)
    assert reward == pytest.approx(retired_reward * (burn + reward) / 100, abs=0.01)
    assert reward > staking * 3, (
        "rendering measured_split's third leg as the staker share overstates "
        "it by more than three times"
    )


def test_the_subdivision_moves_with_its_inputs():
    """It cannot pass by returning the documented triple."""
    base = P.reward_leg_split(15.0, 3000, 3000, 10000)
    for moved in (P.reward_leg_split(30.0, 3000, 3000, 10000),
                  P.reward_leg_split(15.0, 1000, 3000, 10000),
                  P.reward_leg_split(15.0, 3000, 1000, 10000),
                  P.reward_leg_split(15.0, 3000, 3000, 20000)):
        assert moved != base
    # Whatever the bps, the three legs re-sum to the leg they subdivide.
    for staking_bps, nft_bps in ((3000, 3000), (1000, 500), (0, 0), (9000, 500)):
        legs = P.reward_leg_split(15.0, staking_bps, nft_bps, 10000)
        assert sum(legs) == pytest.approx(15.0)


@pytest.mark.parametrize(
    "args",
    [(None, 3000, 3000, 10000), (15.0, None, 3000, 10000),
     (15.0, 3000, None, 10000), (15.0, 3000, 3000, None),
     (15.0, 3000, 3000, 0)],
)
def test_the_subdivision_is_all_none_on_any_gap(args):
    """Three derived numbers, one gate: no partial answer and no infinity."""
    legs = P.reward_leg_split(*args)
    assert legs == (None, None, None)
    assert all(v is None for v in legs)


def test_the_two_new_mainnet_hook_getters_decode():
    """``inventoryCap()`` and ``capDecayTokensPerDay()`` -- neither on Sepolia.

    Both selectors were recovered from bytecode and are in no public signature
    database; they are computed here from the signature strings, and the two
    values that recomputation produces are the ones the live probe used.
    """
    assert P.HOOK_SELECTORS["capDecayTokensPerDay"] == "0x55e62941"
    assert P.HOOK_SELECTORS["inventoryCap"] == "0xdb445ee8"

    state = P.decode_hook_state({
        "inventoryCap": "0x" + format(5_487_346_500_000_000_000_000, "064x"),
        "capDecayTokensPerDay": "0x" + format(1_000 * WEI, "064x"),
        "capFloor": "0x" + format(1_000 * WEI, "064x"),
    })
    assert state.inventory_cap_wei == 5_487_346_500_000_000_000_000
    assert state.cap_decay_tokens_per_day_wei == 1_000 * WEI
    assert state.cap_floor_wei == 1_000 * WEI, "mainnet floor, read not pinned"

    # Absent on Sepolia: two Nones inside an otherwise-healthy payload.
    sepolia = P.decode_hook_state(answers_of(load("hook_state_healthy")))
    assert sepolia.inventory_cap_wei is None
    assert sepolia.cap_decay_tokens_per_day_wei is None
    assert sepolia.cap_floor_wei == 250_000_000 * WEI


def test_the_distributor_decodes_and_carries_no_bonding_field():
    """The model holds what was read; the remainder is derived downstream."""
    import dataclasses

    answers = {
        "stakingBps": "0x" + format(3000, "064x"),
        "nftBps": "0x" + format(3000, "064x"),
        "dripper": "0x" + "0" * 24 + "e6d3de6daeaf327fca42745f1998fcd989e00884",
        "asset": "0x" + "0" * 24 + "d34a99bc0f67ae1bbd63c660e6d0b0dd03e263b7",
        "owner": "0x" + "0" * 24 + "047f606fd5b2baa5f5c6c4ab8958e45cb6b054b7",
        "stakingEarned": "0x" + format(3_149_000_000_000_000_000, "064x"),
        "bondingEarned": "0x" + format(4_198_600_000_000_000_000, "064x"),
        "nftEarned": "0x" + format(3_149_000_000_000_000_000, "064x"),
        "heldBonding": "0x" + format(4_198_600_000_000_000_000, "064x"),
        "heldNft": "0x" + format(3_149_000_000_000_000_000, "064x"),
    }
    state = P.decode_distributor_state(answers, block_number=1)
    assert state.staking_bps == 3000 and state.nft_bps == 3000
    assert state.dripper.lower().endswith("e00884")
    assert state.held_bonding_wei == 4_198_600_000_000_000_000

    names = {f.name for f in dataclasses.fields(state)}
    assert "bonding_bps" not in names, (
        "a field with no getter behind it invites a hardcoded 4000"
    )
    assert P.bonding_bps(state.staking_bps, state.nft_bps, 10000) == 4000

    # The earned legs reproduce the 30/40/30 shape from the chain's own totals.
    total = (state.staking_earned_wei + state.bonding_earned_wei
             + state.nft_earned_wei)
    assert state.staking_earned_wei / total == pytest.approx(0.30, abs=0.001)
    assert state.bonding_earned_wei / total == pytest.approx(0.40, abs=0.001)
    assert state.nft_earned_wei / total == pytest.approx(0.30, abs=0.001)

    # Field by field, like every other decoder.
    for key in answers:
        assert P.decode_distributor_state({**answers, key: None}) is not None
    assert P.decode_distributor_state(None).staking_bps is None


def test_the_no_decay_sentinel_is_three_way_and_none_stays_the_failed_read():
    """``capDecayTokensPerDay()`` returns ``2**128 - 1`` on the Sepolia hook.

    As a rate that is 3.4e20 whole IMD per day -- 340 billion times the entire
    supply -- and it reaches a panel as a confident, absurd number that nothing
    about looks like an error. It means *this hook does not decay its cap*,
    which is a fact rather than a failure.

    Three answers, and the third is the one that must not be folded into the
    first: ``None`` unread, ``True`` sentinel, ``False`` a real rate. Collapsing
    the sentinel into ``None`` would conflate "this hook does not decay" with
    "we could not read it" -- the same conflation removed three times on this
    branch already.
    """
    assert P.is_no_decay(None) is None, "unread stays unread"
    assert P.is_no_decay(2 ** 128 - 1) is True, "the live Sepolia value"
    assert P.is_no_decay(2 ** 256 - 1) is True, "a wider spelling of the idiom"
    assert P.is_no_decay(1_000 * WEI) is False, "the live mainnet rate"
    assert P.is_no_decay(0) is False, (
        "a real zero rate is a rate, not a sentinel -- the producer decides "
        "what to call it"
    )

    # The absurd magnitude, stated so the test carries what it defends against.
    assert (2 ** 128 - 1) / WEI == pytest.approx(3.4028e20, rel=1e-4)
    assert (2 ** 128 - 1) / WEI > 10 ** 9 * 1e9, "billions of times the supply"


def test_the_sentinel_boundary_is_magnitude_and_leaves_real_rates_alone():
    """Recognition is by magnitude, never by a literal or a deployment name.

    The threshold sits above every conceivable real rate and below the sentinel
    family, and both halves of that claim are asserted rather than described.
    """
    assert P.POOL4_NO_DECAY_MIN_WEI == 1 << 96

    supply_wei = 10 ** 9 * WEI            # the whole IMD supply
    assert P.POOL4_NO_DECAY_MIN_WEI > supply_wei * 50, (
        "a decay cannot exceed what exists, so the floor must sit far above "
        "the entire supply per day"
    )
    for real in (0, 1, WEI, 1_000 * WEI, 10 ** 6 * WEI, supply_wei):
        assert P.is_no_decay(real) is False, real
    for sentinel in (2 ** 128 - 1, 2 ** 256 - 1, 1 << 96, (1 << 96) + 1):
        assert P.is_no_decay(sentinel) is True, sentinel
    assert P.is_no_decay((1 << 96) - 1) is False, "the boundary is inclusive"

    # uint64's max is 18.4 IMD/day -- a PLAUSIBLE rate -- so it must not be
    # read as a sentinel. Catching it would silently turn a real rate into
    # "no decay", which is the opposite error and the harder one to notice.
    assert (2 ** 64 - 1) / WEI == pytest.approx(18.45, abs=0.01)
    assert P.is_no_decay(2 ** 64 - 1) is False


def test_the_sentinel_threshold_has_exactly_one_authority():
    """A8's one-authority rule, applied to a number two packages could disagree on.

    If the producer carried its own idea of where the boundary sits, the same
    value would be a rate on one screen and a word on another. The constant is
    exported so there is one place to change it and one place to read it.
    """
    assert "POOL4_NO_DECAY_MIN_WEI" in P.__all__
    assert "is_no_decay" in P.__all__

    # No second magnitude-shaped constant that could drift from it.
    others = [
        n for n, v in vars(P).items()
        if not n.startswith("_") and isinstance(v, int) and not isinstance(v, bool)
        and v > 10 ** 20 and n != "POOL4_NO_DECAY_MIN_WEI"
    ]
    assert others == [], f"a second huge constant could disagree: {others}"


@pytest.mark.parametrize(
    "junk", [None, "", "0x", "many", 1.5, True, False, b"\x00", [], {}]
)
def test_the_sentinel_predicate_is_total(junk):
    """The value arrives from an unverified contract through a decoder."""
    result = P.is_no_decay(junk)
    assert result is None or isinstance(result, bool)


def test_the_sentinel_reads_through_the_decoder_end_to_end():
    """The whole path: raw word -> model field -> verdict."""
    sepolia = P.decode_hook_state(
        {"capDecayTokensPerDay": "0x" + format(2 ** 128 - 1, "064x")})
    assert sepolia.cap_decay_tokens_per_day_wei == 2 ** 128 - 1
    assert P.is_no_decay(sepolia.cap_decay_tokens_per_day_wei) is True

    mainnet = P.decode_hook_state(
        {"capDecayTokensPerDay": "0x" + format(1_000 * WEI, "064x")})
    assert P.is_no_decay(mainnet.cap_decay_tokens_per_day_wei) is False

    absent = P.decode_hook_state({})
    assert absent.cap_decay_tokens_per_day_wei is None
    assert P.is_no_decay(absent.cap_decay_tokens_per_day_wei) is None, (
        "a hook without the getter is unread, not non-decaying"
    )
    assert P.is_no_decay(
        P.decode_hook_state({"capDecayTokensPerDay": "0x"}).cap_decay_tokens_per_day_wei
    ) is None, "an empty return is unread too"
