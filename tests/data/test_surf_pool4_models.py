"""Interface freeze for the surf ``p`` POOL4 body (docs/surf_pool4_contract.md §0).

WP0 of the pool4 build. Five work packages code against ``POOL4_KEYS``, the two
row shapes and the five wire-level dataclasses **in parallel**, so the only
thing standing between a rename and five silently-``None`` panels is this file.
Every test here is deliberately cheap and structural: it should fail at
collection or in milliseconds, not after a fixture round-trip.

These tests are the *contract* side. The screen side (dispatch, composited
output, width pins) is WP8's, and the two are meant to be redundant — the
repo's standing pattern is a hand-typed copy plus an agreement test, never a
derivation that compares a constant against itself.
"""

from __future__ import annotations

import dataclasses
import inspect
import re

import pytest

from maxpane_dashboard.data import surf_models
from maxpane_dashboard.data.surf_models import (
    POOL4_DISCOVERY_SOURCES,
    POOL4_DISCOVERY_STATES,
    POOL4_FLOW_LIMIT,
    POOL4_FLOW_SIDES,
    POOL4_HATCH_LABELS,
    POOL4_HATCH_SCOPES,
    POOL4_HATCH_STATES,
    POOL4_COUNTER_STATES,
    POOL4_KEYS,
    POOL4_NETWORKS,
    POOL4_REWARD_PATHS,
    SURF_KEYS,
    SURF_ROW_KEYS,
    Pool4Discovery,
    Pool4DistributorState,
    Pool4DripperState,
    Pool4FlowEvent,
    Pool4HookState,
    Pool4VaultState,
)

#: The two payload keys that are *also* row shapes. They are members of
#: ``POOL4_KEYS`` for the same reason ``feed_items`` and ``launchpad_coins`` are
#: members of ``SURF_KEYS``: ``SURF_ROW_KEYS`` describes the shape of a row, it
#: does not excuse the key from the payload contract.
POOL4_ROW_PAYLOAD_KEYS = ("pool4_flow", "pool4_hatches")

def _flat_source(text: str) -> str:
    """:func:`_flat` for *source*, with comment markers stripped first.

    ``_flat`` alone is not enough on a ``#:``/``#`` comment block: collapsing
    whitespace leaves the markers behind, so a phrase wrapped across two
    comment lines flattens to ``"... None stays the # ordinary failed read"``
    and a content pin looking for the phrase never matches. Same family as the
    line-wrap problem ``_flat`` exists for, one layer out — and it surfaced the
    same way, as a pin that could not have failed.
    """
    return _flat(re.sub(r"(?m)^\s*#:?\s?", " ", text))


def _flat(text: str | None) -> str:
    """Collapse whitespace so a docstring assertion survives a rewrap.

    Every content pin below matches a *phrase*, and a phrase in a docstring is
    wrapped at some arbitrary column. Matching the raw text makes the test
    depend on where the wrap happens to fall: a reformat that changes nothing
    reddens it, and — far worse — a mutation that guts the sentence can leave
    the test green because the phrase it looked for was split across lines and
    was never being found in the first place. That happened here: a mutation
    rewriting "it is a pointer to one" came back green because the source reads
    "it is a\n    pointer to one".
    """
    return " ".join((text or "").split())


POOL4_MODELS = (
    Pool4HookState,
    Pool4VaultState,
    Pool4DripperState,
    Pool4DistributorState,
    Pool4FlowEvent,
    Pool4Discovery,
)


# ---------------------------------------------------------------------------
# POOL4_KEYS — the flat-dict block
# ---------------------------------------------------------------------------

def test_pool4_keys_has_no_duplicates() -> None:
    assert len(POOL4_KEYS) == len(set(POOL4_KEYS))


def test_every_pool4_key_carries_the_full_prefix() -> None:
    """§0.1's deliberate departure from the launchpad panels.

    The launchpad widgets take ``as_of_hhmm`` short and lean on
    ``test_surf_widget_contract._PREFIXED_KWARG_ALIASES`` to map it back onto
    ``launchpad_as_of_hhmm``. That alias maps one kwarg name onto one contract
    key. A second body whose panels also took ``as_of_hhmm`` would make one
    kwarg name stand for two different keys, and the alias would stop proving
    anything at all while still passing.

    So every pool4 key is spelled in full, in the payload *and* in the widget
    kwargs, and no new alias is added.
    """
    unprefixed = [k for k in POOL4_KEYS if not k.startswith("pool4_")]
    assert not unprefixed, f"pool4 keys without the prefix: {unprefixed}"


def test_pool4_keys_is_sixty_two_of_which_sixty_are_scalar() -> None:
    """The count the plan quotes, split the way the plan's own tables count it.

    §0.2 is headed "Scalar keys (45)" and tabulates 43; §0.4 then says "every
    one of the 45 scalar keys and both row keys has exactly one renderer",
    which would be 47. Both readings cannot be right. The tables and the five
    ``update_data`` signatures agree with each other at **43 scalars**, and 43
    + the two row keys is the 45 the heading and WP8 both quote, so that is
    what is frozen here — and pinned as two numbers rather than one, so a
    future edit cannot satisfy the total by adding a scalar and dropping a row.

    Three keys joined after the freeze. Finding W1 added ``pool4_counter_state``
    and ``pool4_counter_detail``, wiring R1 control (c), which was implemented
    and tested but had zero call sites. Then ``pool4_discovery_source_tx``
    stopped the citation being appended to a sentence that truncates. Then
    mainnet landed on 2026-09-02 and brought twelve more: the Reward
    Distributor's three-way split (nine), the ratchet's ceiling half (two), and
    ``pool4_discovery_source`` (one). Then ``pool4_reward_path``, because the
    Distributor's *presence* is a fact no address can state. Then
    ``pool4_cap_headroom``, on evidence that retired the grounds it had twice
    been refused on. So 43 + 2 became **60 + 2**.
    """
    scalars = [k for k in POOL4_KEYS if k not in POOL4_ROW_PAYLOAD_KEYS]
    assert len(scalars) == 60
    assert len(POOL4_KEYS) == 62


def test_every_pool4_key_appears_in_surf_keys_exactly_once() -> None:
    for key in POOL4_KEYS:
        assert SURF_KEYS.count(key) == 1, f"{key} appears {SURF_KEYS.count(key)}x"


def test_the_pool4_block_is_contiguous_inside_surf_keys() -> None:
    """One block, not 45 keys sprinkled through the contract.

    Contiguity is what lets a reader see the whole pool4 payload at once and
    what makes the block reviewable as a unit. ``SURF_KEYS`` unpacks
    ``*POOL4_KEYS`` rather than retyping it, so this holds by construction —
    and this test is what notices if someone "helpfully" flattens it back into
    45 literals and then interleaves one.
    """
    positions = [SURF_KEYS.index(k) for k in POOL4_KEYS]
    assert positions == sorted(positions), "the block was reordered"
    assert positions == list(range(positions[0], positions[0] + len(POOL4_KEYS)))


def test_the_pool4_block_sits_after_the_launchpad_block() -> None:
    first = SURF_KEYS.index(POOL4_KEYS[0])
    assert first == SURF_KEYS.index("launchpad_as_of_hhmm") + 1


def test_surf_keys_still_has_no_duplicates_after_the_splice() -> None:
    assert len(SURF_KEYS) == len(set(SURF_KEYS))


def test_no_pool4_wei_key_leaks_into_the_flat_dict() -> None:
    """The dict is the presentation boundary: whole IMD / whole ETH, never wei.

    The models are wei-native and the manager divides **exactly once**. A
    ``_wei`` key in the payload means somebody divided twice, or not at all.
    """
    assert not [k for k in POOL4_KEYS if k.endswith("_wei")]


def test_the_two_tri_state_booleans_are_named_as_values_not_as_questions() -> None:
    """``pool4_can_drip`` and ``pool4_backstop_centred`` are ``bool | None``.

    They are pinned by name here because their *rendering* rule is the part
    that gets lost: ``None`` must share no substring with either confident
    answer, on ``SurfBurnPipeline._ready_word``'s precedent (``ready`` /
    ``not yet`` / ``unknown``, deliberately not ``NOT READY``). A widget that
    renders ``None`` as "not centred" is confidently wrong, which is worse than
    a dash.
    """
    assert "pool4_can_drip" in POOL4_KEYS
    assert "pool4_backstop_centred" in POOL4_KEYS


def test_the_four_zero_denominator_keys_exist_and_are_the_ones_that_may_be_none() -> None:
    """Four derived keys have a divisor that can legitimately be zero.

    Each returns ``None`` rather than an infinity or a NaN. Freezing their
    names here is what lets WP3's maths tests and WP4/WP5's render tests name
    the same four things.
    """
    for key in (
        "pool4_floor_distance_pct",   # floor is 0 or unread
        "pool4_backlog_days",         # drip rate is 0 or unread
        "pool4_implied_apr_pct",      # TVL is 0 or unread
        "pool4_split_drift_bps",      # either side unread
    ):
        assert key in POOL4_KEYS


# ---------------------------------------------------------------------------
# the two row shapes
# ---------------------------------------------------------------------------

def test_both_row_shapes_are_declared_and_non_empty() -> None:
    for key in POOL4_ROW_PAYLOAD_KEYS:
        assert key in SURF_ROW_KEYS
        assert SURF_ROW_KEYS[key]


def test_both_row_keys_are_also_payload_keys() -> None:
    """``SURF_ROW_KEYS`` must stay a subset of ``SURF_KEYS``.

    ``tests/data/test_surf_models.py`` already asserts the containment for the
    whole dict; this states it for the two new members specifically, so a
    failure names which one.
    """
    for key in POOL4_ROW_PAYLOAD_KEYS:
        assert key in SURF_KEYS


def test_pool4_flow_row_is_exactly_the_frozen_ten_fields() -> None:
    assert SURF_ROW_KEYS["pool4_flow"] == (
        "ts",
        "age_s",
        "side",
        "size_imd",
        "burned_imd",
        "stakers_imd",
        "fee_imd",
        "fee_eth",
        "settled",
        "tx_hash",
    )


def test_pool4_hatches_row_is_exactly_the_frozen_six_fields() -> None:
    assert SURF_ROW_KEYS["pool4_hatches"] == (
        "scope",
        "label",
        "state",
        "detail",
        "addr",
        "addr_known",
    )


def test_the_flow_row_carries_a_precomputed_age_and_no_clock() -> None:
    """``age_s`` is the manager's, not the widget's.

    The widget and the screen are clock-free by contract, which is the only
    reason a committed capture replays forever. A row that carried only ``ts``
    would force the renderer to read a clock and every fixture would rot.
    """
    row = SURF_ROW_KEYS["pool4_flow"]
    assert "age_s" in row and "ts" in row


def test_the_flow_row_keeps_both_fee_legs_rather_than_one_amount() -> None:
    """The 1% is taken in ETH on a buy and in IMD on a sell.

    One ``fee`` field plus a unit would make "no fee in this currency"
    indistinguishable from "fee unread". Two exclusive legs cannot.
    """
    row = SURF_ROW_KEYS["pool4_flow"]
    assert "fee_imd" in row and "fee_eth" in row
    assert "fee" not in row


def test_the_hatches_row_uses_an_allowlist_flag_not_a_label() -> None:
    """``addr_known`` is the ``KNOWN_LABELS`` allowlist and nothing else.

    Never a blocklist, never a fallback, never a prefix match — a lookalike
    must not inherit its target's standing no matter how many leading hex
    digits it bought.
    """
    assert "addr_known" in SURF_ROW_KEYS["pool4_hatches"]


# ---------------------------------------------------------------------------
# the closed vocabularies
# ---------------------------------------------------------------------------

def test_the_closed_vocabularies_are_frozen_tuples_of_the_documented_words() -> None:
    assert POOL4_NETWORKS == ("SEPOLIA", "MAINNET")
    assert POOL4_DISCOVERY_STATES == ("not-discovered", "adopted", "rejected")
    assert POOL4_FLOW_SIDES == ("buy", "sell")
    assert POOL4_HATCH_STATES == (
        "live", "renounced", "paused", "open", "closed", "absent", "unknown",
    )
    assert POOL4_COUNTER_STATES == (
        "reconciled", "mismatch", "window-limited", "unchecked",
    )
    assert POOL4_DISCOVERY_SOURCES == ("self-post", "docs", "unattributed")
    assert POOL4_REWARD_PATHS == ("direct", "via-distributor")
    assert POOL4_HATCH_SCOPES == (
        "vault", "dripper", "distributor", "hook", "bond",
    )
    assert POOL4_HATCH_LABELS == (
        "owner", "paused", "rescue", "market", "rebalance", "burn sink",
        "rewards", "dripper", "deployed",
    )


def test_no_vocabulary_carries_a_none_or_an_empty_word() -> None:
    """``None`` is expressed by the *key* being ``None``, never by a member.

    A ``"none"``/``""`` member would let an unread state render as a confident
    word, which is the whole defect class these vocabularies exist to prevent.
    """
    for vocab in (
        POOL4_NETWORKS, POOL4_DISCOVERY_STATES, POOL4_FLOW_SIDES,
        POOL4_HATCH_SCOPES, POOL4_HATCH_LABELS, POOL4_HATCH_STATES,
        POOL4_COUNTER_STATES, POOL4_DISCOVERY_SOURCES, POOL4_REWARD_PATHS,
    ):
        assert all(isinstance(w, str) and w for w in vocab)
        assert len(vocab) == len(set(vocab))
        assert "none" not in {w.lower() for w in vocab}


def test_unknown_and_absent_are_separate_hatch_states() -> None:
    """"We looked and could not tell" is not "there is no such hatch".

    ``absent`` is what the BOND row says while no bond contract is deployed
    anywhere a reader could check; ``unknown`` is a failed read. Collapsing
    them would let an outage read as a settled fact about the protocol.
    """
    assert "unknown" in POOL4_HATCH_STATES
    assert "absent" in POOL4_HATCH_STATES


def test_the_citation_is_its_own_key_not_a_suffix_on_the_detail() -> None:
    """The credential and the sentence are two facts, and stay two keys.

    ``surf_manager``'s slot writer already said this, correctly: *"never merged
    into it: the detail is WP3's sentence, this is a pointer to a credential,
    and a later reader must be able to tell them apart."* The slot honoured it;
    the payload did not, appending a 66-character hash to a ~94-character
    sentence.

    The merge is what **guaranteed** the citation would be lost. After A27 the
    tail is the load-bearing half -- the citation is the only unforgeable
    evidence in the design -- so any tail-truncation deletes the evidence and
    keeps the hook address, which the reader could already see four lines below.
    A renderer handed two keys can give the citation its own line at a width it
    controls; a renderer handed one string cannot.
    """
    assert "pool4_discovery_source_tx" in POOL4_KEYS
    assert "pool4_discovery_detail" in POOL4_KEYS


def test_the_citation_and_the_verdict_are_always_published_together() -> None:
    """``None`` on the citation is read against ``pool4_discovery_state``.

    That pairing is why one key suffices and no second "why is it missing" key
    is needed:

    * ``not-discovered`` + ``None``  -- nothing to cite yet. Expected.
    * ``rejected``       + a hash    -- the rejection cites the post it judged.
    * ``adopted``        + a hash    -- the audit trail exists.
    * ``adopted``        + ``None``  -- **an adoption nothing can audit**, the
      one combination worth surfacing, and expressible only because the verdict
      and the citation are separate keys.

    So the contract must never carry one without the other, and the renderer
    that shows the citation must also receive the state.
    """
    assert {"pool4_discovery_state", "pool4_discovery_source_tx"} <= set(POOL4_KEYS)
    hatches = set(POOL4_WIDGET_SIGNATURES["SurfPool4Hatches"])
    assert {"pool4_discovery_state", "pool4_discovery_source_tx"} <= hatches, (
        "the panel rendering the citation must also receive the verdict, or it "
        "cannot tell an expected absence from an unauditable adoption"
    )


def test_the_citation_key_is_a_pointer_and_says_so() -> None:
    """A hash is where to look, not proof of anything.

    The chain remains the authority: re-establishing provenance means
    re-reading that transaction and re-checking the signer. Trusting a stored
    address because a hash sits beside it is A27's bypass wearing a new hat.
    This is the copy a *reader* sees, so the caveat belongs on this field too.
    """
    doc = _flat(Pool4Discovery.__doc__)
    assert "pool4_discovery_source_tx" in doc
    assert "pointer to one" in doc, (
        "the field must state that the hash is a pointer to a credential, not "
        "a credential"
    )


def test_an_adoption_can_always_name_which_source_nominated_it() -> None:
    """The operator accepted a second, weaker candidate source on 2026-09-02.

    The announce channel has not named the mainnet hook, so automatic discovery
    correctly refuses under A27 — and the operator chose to accept the project's
    documentation page as a *candidate* source rather than show SEPOLIA while
    mainnet is live.

    **The mitigation is disclosure, not prevention.** Anyone who can edit that
    page can name a hook, and the chain fingerprint alone will not stop them: a
    correctly-shaped address mines in ~20,000 tries, four of the five getters
    are pure liveness checks, and ``token()`` is the candidate's own choice. So
    an adoption must say where it came from, and weaker provenance has to
    identify itself instead of hiding behind the same word as a dev-signed post.

    That makes the source a **contract-level closed vocabulary**, not a string
    each panel invents.
    """
    assert "pool4_discovery_source" in POOL4_KEYS
    assert POOL4_DISCOVERY_SOURCES == ("self-post", "docs", "unattributed")
    hatches = set(POOL4_WIDGET_SIGNATURES["SurfPool4Hatches"])
    assert {"pool4_discovery_source", "pool4_discovery_state"} <= hatches, (
        "the panel disclosing the source must also receive the verdict"
    )


def test_the_source_vocabulary_is_ordered_strongest_first() -> None:
    """``self-post`` is unforgeable; ``docs`` is merely trusted.

    The order is part of the contract because the panel has to rank them, and a
    ranking invented per-panel is how two panels end up disagreeing about which
    provenance is stronger. ``unattributed`` is last on purpose: an adoption
    whose producer recorded no source must be shown at **least** as weakly as
    ``docs``, never as the strong case.
    """
    assert POOL4_DISCOVERY_SOURCES.index("self-post") == 0
    assert POOL4_DISCOVERY_SOURCES.index("docs") == 1
    assert POOL4_DISCOVERY_SOURCES.index("unattributed") == 2


def test_unattributed_exists_so_absence_cannot_read_as_the_strong_source() -> None:
    """The ``pool4_counter_state`` lesson, applied where it matters most.

    If the producer forgets to set the source, ``_finalise`` fills the key with
    ``None``. A renderer that treats ``None`` as "nothing to say" then draws a
    docs-sourced adoption identically to a dev-signed one — which is precisely
    the disclosure the operator's decision was conditioned on, silently undone
    by an omission.

    So the vocabulary carries an explicit word for "adopted but unattributed".
    ``None`` keeps its house meaning — there is no adoption to attribute — and
    is read against ``pool4_discovery_state``, exactly like
    ``pool4_discovery_source_tx``.
    """
    assert "unattributed" in POOL4_DISCOVERY_SOURCES
    assert None not in POOL4_DISCOVERY_SOURCES
    for word in POOL4_DISCOVERY_SOURCES:
        others = [w for w in POOL4_DISCOVERY_SOURCES if w != word]
        assert not [w for w in others if word in w or w in word], (
            f"{word!r} shares a substring with another source word"
        )


def test_bonding_bps_is_derived_and_has_no_getter_behind_it() -> None:
    """Bonding is the remainder. The model must not pretend otherwise.

    ``stakingBps()`` and ``nftBps()`` are getters; bonding is
    ``BPS_DENOMINATOR - staking - nft`` and has no getter at all. A
    ``bonding_bps`` field on the wire model would be a number with nothing
    behind it, which is exactly how a hardcoded ``4000`` gets typed in and then
    goes stale in silence the day the split moves — and it *did* move once
    already, ``rewardShareBps`` 1000 -> 1500 between Sepolia and mainnet.

    The derivation lives in the manager and is published, so there is one place
    it can be wrong. Its derived-ness needs **no boolean key**: a flag that is
    always ``True`` is a constant dressed as data. The honest signature is that
    it goes ``None`` whenever *either* input does — the
    ``pool4_split_drift_bps`` precedent — and the panel labels it derived, the
    ``pool4_cap_floor``/*observed* precedent.
    """
    fields = {f.name for f in dataclasses.fields(Pool4DistributorState)}
    assert {"staking_bps", "nft_bps"} <= fields
    assert "bonding_bps" not in fields, (
        "bonding has no getter; a field here invites a hardcoded 4000"
    )
    assert "pool4_distributor_bonding_bps" in POOL4_KEYS
    assert not [k for k in POOL4_KEYS if "derived" in k], (
        "derived-ness is a property of the value, not a boolean key that can "
        "only ever be True"
    )


def test_the_distributor_carries_no_held_staking_leg() -> None:
    """Two held legs, not three, because the chain has two.

    ``heldBonding()`` and ``heldNft()`` exist; the staking leg is forwarded to
    the Dripper rather than held, so there is no ``heldStaking()``. Inventing
    the field for symmetry would invite a producer to fill it with a plausible
    zero — and a plausible zero is indistinguishable from "distributed up to
    date", which is what the two real fields mean when they are ``0``.
    """
    fields = {f.name for f in dataclasses.fields(Pool4DistributorState)}
    assert {"held_bonding_wei", "held_nft_wei"} <= fields
    assert "held_staking_wei" not in fields
    assert "pool4_distributor_held_staking" not in POOL4_KEYS


def test_nodes_in_the_payload_is_nft_on_the_chain() -> None:
    """The module's stated naming discipline, applied to a real divergence.

    *Model fields mirror the chain, flat-dict keys mirror the docs* — the same
    split that makes ``identityAllowed()`` the field ``identity_allowed`` and
    the key ``gate_open``. The chain says ``nftBps()`` / ``nftEarned()`` /
    ``heldNft()``; the project's documentation calls them **nodes**, the
    NFT-holding compute daemons.

    This test exists because the divergence looks like a typo from either side,
    and a well-meaning sweep that "fixed" it would break the manager's mapping
    table in a way nothing else would catch.
    """
    fields = {f.name for f in dataclasses.fields(Pool4DistributorState)}
    assert {"nft_bps", "nft_earned_wei", "held_nft_wei"} <= fields
    assert not [f for f in fields if "nodes" in f], (
        "the wire model mirrors the chain, and the chain says nft"
    )
    for key in ("pool4_distributor_nodes_bps", "pool4_distributor_nodes_earned",
                "pool4_distributor_held_nodes"):
        assert key in POOL4_KEYS
    assert not [k for k in POOL4_KEYS if "_nft" in k], (
        "the payload mirrors the docs, and the docs say nodes"
    )


def test_the_ratchet_owns_both_ends_of_the_cap() -> None:
    """``inventoryCap`` and ``capDecayTokensPerDay`` are RATCHET keys.

    They are the ceiling half of the same mechanism ``pool4_cap_floor`` is the
    floor half of: the reserve sits between a decaying cap above and an
    owner-settable floor below, and the docs describe buys as lowering the cap.
    Rendering them anywhere but beside the floor and the reserve would scatter
    one mechanism across two panels.

    **Both chains answer both getters** (D13, measured). An earlier version of
    this docstring said Sepolia had neither, which was an assumption rather
    than a measurement. The difference is the value: ``capDecayTokensPerDay``
    is ``2**128-1`` (no decay) on Sepolia against 1,000 IMD/day on mainnet, and
    ``inventoryCap`` equals ``tokensInPool`` on both.

    That matters for how the absence case gets tested: "aim it at Sepolia and
    watch these go ``None``" would pass for the wrong reason. Absence has to be
    driven by a getter made to revert.
    """
    ratchet = set(POOL4_WIDGET_SIGNATURES["SurfPool4Ratchet"])
    assert {
        "pool4_cap_floor", "pool4_inventory_cap", "pool4_cap_decay_per_day",
        "pool4_tokens_in_pool", "pool4_floor_distance",
    } <= ratchet


def test_the_new_hook_getters_are_not_claimed_to_be_sepolia_absent() -> None:
    """**D13.** Both chains answer ``inventoryCap()`` and
    ``capDecayTokensPerDay()``; only the values differ.

    This module said the opposite until 2026-09-02 — mainnet-only, Sepolia has
    neither — which was assumed in a brief and never measured. It is the W3
    shape: a *reasoned* comment arguing for a world that does not exist, which
    is more durable than a bare wrong value because the reasoning makes it look
    checked.

    The reasoning it carried was load-bearing and wrong in a specific way: it
    licensed testing the absence case by aiming the reader at Sepolia and
    watching the fields go ``None``. That test would pass for the wrong reason.
    Absence has to be driven by a getter made to revert.
    """
    source = _flat_source(inspect.getsource(surf_models))
    for retired in (
        "Neither exists on Sepolia",
        "Sepolia has neither",
        "None on a deployment whose hook lacks the getters",
    ):
        assert retired not in source, (
            f"surf_models re-asserts the D13 claim: {retired!r} -- both chains "
            "answer both getters, only the values differ"
        )
    comment = _flat_source(inspect.getsource(surf_models))
    assert "**Both chains answer both getters** (D13, measured by WP6)" in comment, (
        "the correction must be stated, not merely the wrong claim removed"
    )
    assert "absence case cannot be driven by pointing at Sepolia" in comment


def test_the_no_decay_sentinel_is_named_as_a_sentinel() -> None:
    """``2**128-1`` is *no decay*, not 3.4e20 IMD/day.

    Sepolia carries the sentinel; mainnet carries a real 1,000 IMD/day. Divided
    into whole IMD the sentinel is ~3.4e20 per day, which is not a number any
    panel should print — and it is exactly the shape that renders as a
    confident, absurd, unmissable-in-hindsight figure.

    ``None`` stays the ordinary failed read, so the sentinel needs its own
    resolution by the producer rather than being collapsed into ``None``, which
    would conflate "this hook does not decay" with "we could not read it".
    """
    source = _flat_source(inspect.getsource(surf_models))
    assert "is a sentinel, not a rate" in source
    assert "no decay" in source
    assert "None stays the ordinary failed read" in source


def test_the_cap_headroom_is_published_and_reads_from_the_ceiling_down() -> None:
    """Refused twice, then admitted on evidence. **The sign is the trap.**

    ``pool4_floor_distance`` is ``reserve - floor``. ``pool4_cap_headroom`` is
    ``cap - reserve`` -- **the operand order flips**, so that both are positive
    when healthy. Writing the ceiling half as ``reserve - cap`` by analogy with
    its sibling inverts the sign and renders a *binding* cap as slack, which is
    the one reading this key exists to prevent.

    A negative is real -- inventory sitting above the cap -- and renders rather
    than clamping, on ``floor_distance``'s own precedent.

    Why it is a quantity and not the three-state word an earlier ruling
    converged on: headroom 94.68 IMD over a 1,000 IMD/day decay is **the cap
    binding in ~2.3 hours**, and the magnitude relative to the decay rate is
    the entire meaning. A word discards it. Two pools both rendering ``5.5K``
    through a compact formatter, one with a day of slack and one about to
    clamp, are different decisions.
    """
    assert "pool4_cap_headroom" in POOL4_KEYS
    ratchet = set(POOL4_WIDGET_SIGNATURES["SurfPool4Ratchet"])
    assert {"pool4_cap_headroom", "pool4_inventory_cap",
            "pool4_tokens_in_pool"} <= ratchet, (
        "the headroom and both its operands render on one panel, or a reader "
        "cannot check the subtraction they are being shown"
    )
    src = _flat_source(inspect.getsource(surf_models))
    assert "NOTE THE OPERAND ORDER" in src, (
        "the sign convention must be stated where the key is declared; it is "
        "the mirror of floor_distance, not a copy of it"
    )
    # and no _pct sibling was added along with it: there is no division here,
    # which is the one original ground that survives.
    assert "pool4_cap_headroom_pct" not in POOL4_KEYS


def test_the_headroom_refusals_are_recorded_as_superseded() -> None:
    """Three grounds expired; the record says so, so it is not relitigated.

    Two were retired by measurement -- the float-precision ground rested on a
    12-wei snapshot mistaken for a property, and the never-observed ground was
    self-sealing (Sepolia's cap cannot move *because* its decay is the
    sentinel). The third, "both operands are already published", proves too
    much: ``pool4_floor_distance`` has exactly that shape and nobody argues it
    is wrong.
    """
    src = _flat_source(inspect.getsource(surf_models))
    for claim in (
        "superseded, not wrong",
        "mistaken for a property",
        "self-sealing",
        "proves too much",
    ):
        assert claim in src, f"the supersession record no longer says: {claim!r}"


def test_the_binds_in_days_follow_up_names_its_own_inversion() -> None:
    """``headroom / decay`` is the more actionable form and is **not** a key.

    No panel has asked for it, and inventing it now is the surface-by-symmetry
    this contract keeps refusing. It is recorded rather than built because its
    hazard is worse than the zero-denominator one ``backlog_days`` carries: on
    the no-decay sentinel, ``94.68 / 3.4e20`` is ~2.8e-19 days, which renders as
    **"binds now"** when the truth is **"never binds"**. A sign-of-meaning
    inversion, not a missing value -- so whoever builds it must resolve the
    sentinel *before* dividing, not guard the denominator against zero.
    """
    assert not [k for k in POOL4_KEYS if "binds_in" in k]
    src = _flat_source(inspect.getsource(surf_models))
    assert "reads as *binds now* when the truth is *never binds*" in src


def test_the_distributor_owner_is_a_hatch_row_not_a_scalar_key() -> None:
    """A new trust surface goes where the trust surfaces are rendered.

    The Distributor has a live ``owner()`` with ``emergencyWithdraw`` and
    ``setDripper`` — the power to drain it and the power to re-point the whole
    rewards path. That is a hatch, and HATCHES exists to disclose exactly this.
    Publishing it as a scalar key instead would put one contract's trust surface
    on a different panel from the other three.
    """
    assert "distributor" in POOL4_HATCH_SCOPES
    assert "dripper" in POOL4_HATCH_LABELS   # setDripper, the re-pointing power
    assert "rescue" in POOL4_HATCH_LABELS    # emergencyWithdraw, same shape
    assert not [k for k in POOL4_KEYS if "distributor_owner" in k]
    assert not [k for k in POOL4_KEYS if "distributor_asset" in k]


def test_the_reward_path_is_a_word_because_an_address_cannot_say_unknown() -> None:
    """WP5 asked for ``pool4_distributor_addr`` on SPLIT. Granted — and it is
    **not sufficient on its own**, which is why this key exists beside it.

    SPLIT annotates the measured stakers percentage with *which leg* it is:
    ``4.50% (staking leg)`` on mainnet, ``9.89% (reward leg)`` on Sepolia. Those
    two words are three times apart, and they are the exact bug WP3 caught.

    ``pool4_distributor_addr`` is ``None`` in **two** worlds — there is no
    Distributor, and ``rewardsRecipient()`` was not read — and the hook's
    getters are batched with ``allowFailure=True``, so one reverted sub-call
    degrades one field rather than the round. "The counters answered,
    ``rewardsRecipient()`` did not" is therefore a routine payload, not a corner
    case, and in it a panel reading absence-of-address as absence-of-Distributor
    labels mainnet's 15% as the staker share. That is the 3x bug arriving
    through the door opened to prevent it.

    So the topology is a word with three states, on ``POOL4_COUNTER_STATES``'s
    reasoning: the healthy reading must be something a producer has to *say*,
    because ``None`` is what an omission produces.
    """
    assert "pool4_reward_path" in POOL4_KEYS
    assert POOL4_REWARD_PATHS == ("direct", "via-distributor")
    assert None not in POOL4_REWARD_PATHS
    for word in POOL4_REWARD_PATHS:
        others = [w for w in POOL4_REWARD_PATHS if w != word]
        assert not [w for w in others if word in w or w in word], (
            f"{word!r} shares a substring with another reward-path word"
        )


def test_every_panel_that_annotates_a_leg_receives_the_topology() -> None:
    """The agreement question, answered structurally.

    The shared *key* is what makes the two panels agree — one dispatch, one
    value, no second source to drift from — so no cross-panel equality test is
    needed or even possible. What does need pinning is the other half: a panel
    that renders a leg-dependent number must receive the fact that decides the
    leg, and must receive the address beside it so it can say *which*
    Distributor.

    SPLIT annotates the percentage; HATCHES renders the chain of custody. Both
    get both. A third panel that later starts annotating a leg has to be added
    here, and this test is what will notice.
    """
    topology = {"pool4_distributor_addr", "pool4_reward_path"}
    # Against the CONTRACT first, then the signature table. Asserting only
    # against ``POOL4_WIDGET_SIGNATURES`` would make this a statement about a
    # constant this test file owns: deleting the key from ``POOL4_KEYS``
    # outright left it green, because the table still listed it. A guard that
    # only sees edits to its own side of the redundancy is half a guard.
    assert topology <= set(POOL4_KEYS), (
        f"the topology left the contract: {sorted(topology - set(POOL4_KEYS))}"
    )
    for panel in ("SurfPool4Split", "SurfPool4Hatches"):
        kwargs = set(POOL4_WIDGET_SIGNATURES[panel])
        assert topology <= kwargs, (
            f"{panel} renders leg-dependent content without the topology"
        )
    # The legs themselves stay on SPLIT only: HATCHES shows custody, not maths.
    hatches = set(POOL4_WIDGET_SIGNATURES["SurfPool4Hatches"])
    assert not [k for k in hatches if k.endswith(("_bps", "_earned"))]


def test_the_topology_is_not_inferable_from_the_distributor_keys_alone() -> None:
    """Why the inference SPLIT was making could not stay.

    Every ``pool4_distributor_*`` value is ``None`` on a Sepolia-shaped
    deployment **and** on a failed read, so no combination of them separates the
    two. Neither does pairing the address with ``pool4_hook_addr``: that address
    comes from discovery or the vendored fallback, not from the getter round, so
    it can be present while ``rewardsRecipient()`` is unread.

    This test enumerates the distributor surface so that a future key which
    *would* disambiguate cannot be added without someone noticing that
    ``pool4_reward_path`` is the place for it.
    """
    dist = [k for k in POOL4_KEYS if k.startswith("pool4_distributor_")]
    assert dist, "the distributor surface vanished; this test is now vacuous"
    # every one is a plain value key -- none of them is a state word
    assert not [k for k in dist if k.endswith(("_state", "_path", "_source"))], (
        "a distributor key grew a state word of its own; the topology has one "
        "expression and it is pool4_reward_path"
    )


def test_the_vault_path_hop_count_is_network_dependent() -> None:
    """The one mainnet change that is not self-adapting.

    Sepolia: hook -> Dripper -> vault. Mainnet: hook -> **Distributor** ->
    Dripper -> vault. A two-hop reader calls ``vault()`` on the Distributor,
    which has no such method, and the vault and dripper reads fail outright.

    ``pool4_distributor_addr`` is what makes the hop count *visible* rather than
    assumed, and its ``None`` is a real answer about the topology — "there is no
    distributor in this path" — not a failed read.
    """
    assert "pool4_distributor_addr" in POOL4_KEYS
    doc = _flat(Pool4DripperState.__doc__)
    # Whole hop chains, not the bare word "Distributor" -- which survives
    # anywhere in the docstring and left this test green when a mutation
    # deleted the mainnet path outright. Fifth instance of that family on this
    # branch; the fix is always the same, pin the claim not a token.
    for chain in (
        "Sepolia: ``hook.rewardsRecipient()`` -> Dripper -> ``dripper.vault()``",
        "**Distributor** -> ``distributor.dripper()`` -> Dripper",
        "never assumed from the Sepolia shape",
    ):
        assert chain in doc, f"the dripper docstring no longer states: {chain!r}"


def test_none_never_means_the_counters_agree() -> None:
    """Finding W1's load-bearing decision, and the reason it needed two keys.

    The obvious shape was one key where ``None`` means "agree". It is wrong,
    and dangerously so: this is a **safety control** for R1 -- the hook
    interface is recovered from bytecode selectors and three event signatures
    are unresolved, so a wrong operand order surfaces as a confident wrong
    number with no signal anywhere. If the manager fails to compute the check
    at all, ``_finalise`` fills the key with ``None``; under "None means agree"
    that failure renders as a **clean bill of health**. A control that reports
    all-clear when it did not run is not a control.

    It also inverts the convention every other key in this contract obeys, on
    the one key where the inversion is least survivable.

    So ``None`` keeps its house meaning -- the check has never run -- and every
    outcome of actually looking is a word.
    """
    assert "pool4_counter_state" in POOL4_KEYS
    assert "reconciled" in POOL4_COUNTER_STATES
    # the healthy answer is a WORD, so it cannot be produced by omission
    assert "agree" not in POOL4_COUNTER_STATES
    assert None not in POOL4_COUNTER_STATES


def test_no_counter_state_word_is_a_substring_of_another() -> None:
    """``SurfBurnPipeline._ready_word``'s rule, applied where it bites hardest.

    ``agree``/``disagree`` was the natural pair and is a trap: ``agree`` is a
    substring of ``disagree``, so a widget testing ``"agree" in state`` renders
    a **mismatch as healthy** -- silently, and only on the one payload that
    matters. ``reconciled``/``mismatch`` cannot do that.
    """
    for word in POOL4_COUNTER_STATES:
        others = [w for w in POOL4_COUNTER_STATES if w != word]
        assert not [w for w in others if word in w or w in word], (
            f"{word!r} shares a substring with another counter state; a "
            "widget matching on it can render the wrong verdict"
        )


def test_could_not_check_is_separable_from_both_agreement_and_disagreement() -> None:
    """Three distinct failures-to-conclude, and none of them is a verdict.

    * ``window-limited`` -- WP7 sums a **trailing** window
      (``POOL4_LOG_WINDOW_BLOCKS``), not complete history. The three identities
      are cumulative-counter-vs-sum-of-all-logs, so over a partial window they
      cannot hold **by construction** -- the sum is short by everything older
      than the window. This is a design limit, permanent and expected, and it
      must never render as a mismatch.
    * ``unchecked`` -- the sweep failed or the counters are unread. Something
      broke; the action is different.
    * ``None`` -- it has never run at all.

    Collapsing any of these into ``reconciled`` is the FARM/HOUR-SAVED defect
    this repo already shipped: a panel reading confident and green through an
    outage. Collapsing them into ``mismatch`` is crying wolf, which retires the
    control just as effectively by teaching a reader to ignore it.
    """
    assert "window-limited" in POOL4_COUNTER_STATES
    assert "unchecked" in POOL4_COUNTER_STATES
    assert len(set(POOL4_COUNTER_STATES)) == 4


def test_the_counter_check_has_a_state_and_a_detail_like_every_other_detector() -> None:
    """Two keys, on the ``sig_*_state`` / ``sig_*_detail`` shape used nine
    times already in ``SURF_KEYS``.

    One key could only carry four outcomes plus a delta by making the string a
    delimited ``"mismatch: burn short by 1,234.5 IMD"`` that every consumer
    re-parses -- which is exactly the shape rejected for ``backstop`` two
    amendments ago, for reasons that apply here verbatim.
    """
    assert "pool4_counter_state" in POOL4_KEYS
    assert "pool4_counter_detail" in POOL4_KEYS


def test_no_counter_key_names_the_eth_identity() -> None:
    """Amendment A9: there is **no symmetric ETH check**, and there must not be.

    ``totalFeeToken()`` is cumulative while ``retainedEth()`` is a *current
    balance*, so ``Sigma FeeCollected[eth] == retainedEth()`` reads non-zero
    against zero on a perfectly healthy hook and would fire on **every owner
    withdrawal**. The identity that actually holds is
    ``Sigma FeeCollected[eth] == Sigma FeesWithdrawn[eth] + retainedEth()``.

    The contract carries one state and one detail, not a per-identity key, so
    there is nowhere for a naive ETH check to acquire its own payload slot
    without this test noticing.
    """
    eth_keys = [
        k for k in POOL4_KEYS
        if "counter" in k and ("eth" in k or "retained" in k)
    ]
    assert not eth_keys, f"a per-identity ETH counter key appeared: {eth_keys}"


def test_the_flow_limit_is_the_documented_cap() -> None:
    assert POOL4_FLOW_LIMIT == 25


# ---------------------------------------------------------------------------
# the wire-level dataclasses
# ---------------------------------------------------------------------------

#: The exact keyword names each producer passes. Same freeze, same reason as
#: ``test_surf_models.CONSTRUCTOR_KWARGS``: WP6 constructs these and WP7 reads
#: them, so a rename on either side becomes a collection error here instead of
#: a hero full of ``None``.
CONSTRUCTOR_KWARGS: dict[type, tuple[str, ...]] = {
    Pool4HookState: (
        "token", "pool_manager", "pool_id", "owner", "burn_sink",
        "rewards_recipient", "backstop_tick_lower", "backstop_tick_upper",
        "backstop_liquidity", "market_open", "rebalance_enabled",
        "bps_denominator", "reward_share_bps", "lp_fee", "cap_floor_wei",
        "inventory_cap_wei", "cap_decay_tokens_per_day_wei",
        "keeper_reward_wei",
        "tick_spacing", "tick_lower", "tick_upper",
        "ref_tick", "current_tick", "current_sqrt_price_x96",
        "position_liquidity", "eth_in_pool_wei", "tokens_in_pool_wei",
        "total_burned_wei", "total_rewarded_wei", "total_fee_token_wei",
        "retained_eth_wei", "last_claim_block", "total_supply_wei",
        "block_number",
    ),
    Pool4VaultState: (
        "name", "symbol", "decimals", "asset", "owner", "paused",
        "total_assets_wei", "total_shares_raw", "share_price_wei",
        "block_number",
    ),
    Pool4DripperState: (
        "vault", "token", "owner", "drip_rate_per_second_wei",
        "max_catchup_seconds", "min_drip_amount_wei", "keeper_reward_wei",
        "drippable_wei", "can_drip", "balance_wei", "block_number",
    ),
    Pool4DistributorState: (
        "staking_bps", "nft_bps", "dripper", "asset", "owner",
        "staking_earned_wei", "bonding_earned_wei", "nft_earned_wei",
        "held_bonding_wei", "held_nft_wei", "block_number",
    ),
    Pool4FlowEvent: (
        "tx_hash", "ts", "block_number", "side", "size_wei", "burned_wei",
        "stakers_wei", "fee_token_wei", "fee_eth_wei", "settled",
    ),
    Pool4Discovery: (
        "network", "state", "detail", "hook_addr", "token_addr",
        "source_tx_hash",
    ),
}


@pytest.mark.parametrize("model", POOL4_MODELS)
def test_pool4_models_are_frozen_slotted_dataclasses(model) -> None:
    assert dataclasses.is_dataclass(model)
    assert model.__dataclass_params__.frozen is True


@pytest.mark.parametrize("model", POOL4_MODELS)
def test_field_names_are_exactly_the_frozen_vocabulary(model) -> None:
    assert tuple(f.name for f in dataclasses.fields(model)) == CONSTRUCTOR_KWARGS[model]


@pytest.mark.parametrize("model", POOL4_MODELS)
def test_every_model_constructs_from_its_documented_kwargs(model) -> None:
    """Constructing by keyword — the way every producer does — must not TypeError."""
    assert model(**{name: None for name in CONSTRUCTOR_KWARGS[model]}) is not None


@pytest.mark.parametrize("model", POOL4_MODELS)
def test_total_outage_produces_an_all_none_state_never_zeros(model) -> None:
    instance = model(**{name: None for name in CONSTRUCTOR_KWARGS[model]})
    assert all(getattr(instance, f.name) is None for f in dataclasses.fields(instance))


@pytest.mark.parametrize("model", POOL4_MODELS)
def test_no_pool4_model_field_defaults_to_zero(model) -> None:
    """The house rule, stated structurally.

    A default of ``0`` is a sentinel that outlives the outage that produced it
    — and, in a persisted series, fires a false signal long after the RPC came
    back.

    **The identity check is load-bearing.** The obvious spelling of this test
    is ``assert field.default in (None, False, ())`` — which is what
    ``tests/data/test_surf_models.py::test_no_model_field_defaults_to_zero``
    said until 2026-09-01, and it **cannot fail on the defect it is named
    after**: ``in`` compares with ``==``, ``0 == False`` is ``True``, so a
    field defaulting to ``0`` passes it. Verified by mutation: adding
    ``burned_wei: int = 0`` to ``Pool4FlowEvent`` left the ``in``-spelled
    version fully green. ``is`` never conflates the two, because ``0 is
    False`` is ``False``.

    The original was fixed the same way (WP0 follow-up, task B) and proven to
    bite on ``LaunchpadState.creator_count``.
    """
    for field in dataclasses.fields(model):
        if field.default is dataclasses.MISSING:
            continue
        default = field.default
        allowed = default is None or default is False or default == ()
        assert allowed, (
            f"{model.__name__}.{field.name} defaults to {default!r} -- "
            "a persisted zero outlives the outage that produced it"
        )


def test_the_flow_event_zero_legs_are_required_not_defaulted() -> None:
    """``burned_wei``/``stakers_wei`` have no default at all.

    A default — even the correct ``0`` — would let a producer omit them, and an
    omitted leg is indistinguishable from a buy's genuine zero. Requiring them
    means the client has to have looked.
    """
    defaults = {
        f.name: f.default for f in dataclasses.fields(Pool4FlowEvent)
    }
    for name in ("burned_wei", "stakers_wei", "settled"):
        assert defaults[name] is dataclasses.MISSING, (
            f"Pool4FlowEvent.{name} acquired a default; the producer can now "
            "omit a leg and the row cannot tell that apart from a real zero"
        )


@pytest.mark.parametrize("model", POOL4_MODELS)
def test_pool4_models_are_immutable(model) -> None:
    instance = model(**{name: None for name in CONSTRUCTOR_KWARGS[model]})
    first = dataclasses.fields(model)[0].name
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(instance, first, 0)


@pytest.mark.parametrize("model", POOL4_MODELS)
def test_no_model_field_is_named_in_flat_dict_units(model) -> None:
    """Wei-native models, whole-unit dict. The suffixes are the tell.

    A model field ending ``_imd`` or ``_eth`` is a raw chain quantity that
    somebody has already divided — which means the manager will divide it
    again, or will not divide it at all, and either way one of the two layers
    is wrong. Chain amounts end ``_wei`` on this side of the boundary and drop
    the suffix on the other.
    """
    offenders = [
        f.name for f in dataclasses.fields(model)
        if f.name.endswith(("_imd", "_eth", "_pct"))
    ]
    assert not offenders, f"{model.__name__} carries flat-dict units: {offenders}"


def test_every_chain_amount_on_the_models_is_wei_suffixed() -> None:
    """The amounts, named. A getter returning a token or ETH quantity must
    reach this layer as ``_wei``; anything else is a unit bug waiting to be
    rendered as a plausible number.
    """
    for model, expected in (
        (Pool4HookState, {
            "cap_floor_wei", "keeper_reward_wei", "eth_in_pool_wei",
            "tokens_in_pool_wei", "total_burned_wei", "total_rewarded_wei",
            "total_fee_token_wei", "retained_eth_wei", "total_supply_wei",
            "inventory_cap_wei", "cap_decay_tokens_per_day_wei",
        }),
        (Pool4DistributorState, {
            "staking_earned_wei", "bonding_earned_wei", "nft_earned_wei",
            "held_bonding_wei", "held_nft_wei",
        }),
        (Pool4VaultState, {
            # NOT total_shares_raw: shares are 24-decimal, so they are
            # deliberately outside the ``_wei`` == "/1e18" convention.
            "total_assets_wei", "share_price_wei",
        }),
        (Pool4DripperState, {
            "drip_rate_per_second_wei", "min_drip_amount_wei",
            "keeper_reward_wei", "drippable_wei", "balance_wei",
        }),
        (Pool4FlowEvent, {
            "size_wei", "burned_wei", "stakers_wei", "fee_token_wei",
            "fee_eth_wei",
        }),
    ):
        names = {f.name for f in dataclasses.fields(model)}
        assert expected <= names, f"{model.__name__} is missing {expected - names}"


def test_the_two_liquidities_are_deliberately_not_wei_suffixed() -> None:
    """Uniswap's ``L`` is a raw ``uint128`` in the pool's own units.

    It is not an amount of IMD and not an amount of ETH, so dividing it by 1e18
    produces a number that means nothing. Both liquidities reach the flat dict
    unchanged. This test exists so a later sweep for "unsuffixed integers" does
    not helpfully rename them and hand the manager a divisor.
    """
    names = {f.name for f in dataclasses.fields(Pool4HookState)}
    for base in ("position_liquidity", "backstop_liquidity"):
        assert base in names
        assert f"{base}_wei" not in names


def test_the_flow_event_burn_and_staker_legs_cannot_be_none() -> None:
    """The single most likely way this build ships wrong.

    A buy has no burn leg and no staker leg. That is a **representable zero**,
    and it must render as ``0.00`` — visibly different from the whole panel
    being unavailable. ``None`` belongs one level up, on ``pool4_flow`` itself.
    This is the FARM/HOUR-SAVED defect CLAUDE.md records: a rail that said
    ``none yet`` while the source was dead, reading confident and green through
    an outage.
    """
    hints = {f.name: f.type for f in dataclasses.fields(Pool4FlowEvent)}
    assert hints["burned_wei"] == "int"
    assert hints["stakers_wei"] == "int"
    assert hints["settled"] == "bool"
    # and the amount that genuinely can be unread keeps its None
    assert hints["size_wei"] == "int | None"


def test_the_flow_event_is_clock_free() -> None:
    """No ``age_s`` on the wire model.

    The age is the manager's derivation from an injected clock. A model that
    carried it would either need a clock of its own or would freeze an age into
    a fixture, and every committed capture would rot the day after it landed.
    """
    names = {f.name for f in dataclasses.fields(Pool4FlowEvent)}
    assert "age_s" not in names
    assert "ts" in names


def test_the_backstop_is_three_typed_fields_not_a_delimited_string() -> None:
    """Amendment A15 + the WP0 call it asked for.

    ``backstop()`` returns ``(int24 lower, int24 upper, uint128 liquidity)`` --
    three words, 96 bytes, **no ETH word** (the fourth operand in the mechanics
    doc's earlier draft came from the event, not the getter). It was briefly
    typed ``str | None`` carrying ``"lower,upper,liquidity"``.

    Three ``int | None`` fields is the shape, matching ``positions()`` ->
    ``ChainState.lp_*`` in this same module. A string would make every consumer
    a parser -- of a value that comes off an **unverified** contract, so
    malformed input is a real case -- and would collapse three independent
    reads into one all-or-nothing ``None``.
    """
    hints = {f.name: f.type for f in dataclasses.fields(Pool4HookState)}
    for name in ("backstop_tick_lower", "backstop_tick_upper", "backstop_liquidity"):
        assert name in hints, f"{name} missing"
        assert hints[name] == "int | None", (
            f"{name} is {hints[name]!r}; the backstop words are ints, and a "
            "delimited string would make every consumer a parser"
        )
    assert "backstop" not in hints, (
        "the delimited-string backstop is back; A15 says three words"
    )


def test_no_docstring_restates_the_v4_permission_mask() -> None:
    """Amendment A8. One authority for the gate, and it is not this module.

    The hook address ends ``6840``; the visible ``840`` is a **mined vanity
    tail** and the permission field is the low *14* bits, so the real mask is
    ``0x6840 & 0x3FFF == 0x2840`` -- ``beforeInitialize`` as well as
    ``beforeAddLiquidity`` and ``afterSwap``.

    ``Pool4Discovery``'s docstring restated the mask and restated it wrong, and
    a gate rebuilt from that wording **rejects the real hook, so pool4 would
    never be discovered on any chain.** The mask belongs to WP3's
    ``data/surf_pool4.py`` under A8; this module points at it and does not keep
    a second copy, because two authorities for one constant is how the wrong
    one survives.
    """
    source = inspect.getsource(surf_models)
    assert "0x840" not in source, (
        "the superseded 0x840 mask is back in surf_models -- a gate built to "
        "it rejects the real hook (amendment A8)"
    )
    assert "0x2840" not in source, (
        "surf_models is restating WP3's permission mask; point at A8 instead "
        "so there is one authority for it"
    )
    assert "fixed by amendment A8" in _flat(Pool4Discovery.__doc__), (
        "the fingerprint paragraph must cite the amendment that owns the mask"
    )


def test_nothing_promises_the_retired_persisted_adoption_defence() -> None:
    """Amendment A27. The defence is gone; the sentences promising it must be.

    Discovery once re-verified a persisted ``adopted`` address on read, and the
    prose called that "never trusted from storage". It was empty: the
    fingerprint is forgeable by construction -- an address with the right
    permission bits was mined in **20,141 tries in under a second** -- four of
    its five getters are pure liveness checks any contract passes, and
    ``token()`` is a value the candidate's own contract chooses. The promise
    held only against the committed fixture, whose flag word is all zeros.

    WP7 removed the persisted address from the candidate set; WP3 then deleted
    ``reverify_persisted``, which the manager structurally could no longer
    call. What is left in this module is prose, and **prose is exactly the
    failure mode** -- a reassuring sentence beside a deleted defence is what
    someone finds when they grep for the cache-file protection. So it is
    scanned for, not merely removed once.
    """
    source = inspect.getsource(surf_models)
    for phrase in (
        "re-verified on read",
        "never trusted from storage",
        "gets the same two gates",
    ):
        assert phrase not in source, (
            f"surf_models promises the retired defence: {phrase!r} (A27). "
            "The persisted address is not a candidate at all; provenance is "
            "the only unforgeable gate."
        )


def test_the_discovery_docstrings_name_provenance_as_the_only_unforgeable_gate() -> None:
    """Deleting the false claim is half the job; the true one has to replace it.

    A reader arriving at this field needs to know what *does* protect it. The
    answer is the signature on the announce-wallet self-post -- forging that
    costs a private key, where forging the fingerprint costs a second of CPU --
    and that the cache nominates nothing.
    """
    doc = _flat(Pool4Discovery.__doc__)
    # Whole claims, not bare words. An earlier draft of this test asserted
    # ``"unforgeable" in doc``, and a mutation that downgraded the *provenance
    # bullet* to "the strict one" left it green because the word survived
    # elsewhere in the docstring. A word appearing somewhere is not the claim
    # being made in the place it has to be made.
    for claim in (
        "provenance -- the only unforgeable one",   # which gate, stated as such
        "Nothing is ever adopted from storage",     # what replaced the old promise
        "not in the candidate set at all",          # and how strongly
        "(amendment A27)",                          # the retirement that owns it
        # the vault docstring's own wrap-sensitive claim lives in its own test
    ):
        assert claim in doc, (
            f"Pool4Discovery no longer states: {claim!r} -- deleting the false "
            "promise is only half the job, the true one has to stand in its place"
        )
    states_comment = _flat(
        inspect.getsource(surf_models).split("POOL4_DISCOVERY_STATES: tuple")[0]
    ).replace("#: ", "")
    for claim in ("The cache does not get a vote", "is not a candidate"):
        assert claim in states_comment, (
            f"POOL4_DISCOVERY_STATES no longer states: {claim!r}"
        )


def test_the_vault_reads_its_own_decimals_rather_than_assuming_eighteen() -> None:
    """Amendment A14, and the house rule it is an instance of.

    Solady's ``ERC4626`` reports ``asset decimals + _decimalsOffset()``, and
    ``StakedIMD._decimalsOffset()`` is 6, so ``decimals()`` is **24** on
    Sepolia. The mainnet vault does not exist yet and nothing binds its offset
    to Sepolia's, so the number is *read*, never assumed -- "read values live,
    never hardcode a documented one".

    A module-level constant would be the hardcode wearing a name, so the test
    refuses that too: the value has to arrive per instance, with a ``None`` for
    the read that failed.
    """
    hints = {f.name: f.type for f in dataclasses.fields(Pool4VaultState)}
    assert hints.get("decimals") == "int | None", (
        "Pool4VaultState must carry a read decimals; without it the divisor "
        "for shares is a guess that is wrong by 1e6 whenever the offset moves"
    )
    for banned in ("POOL4_VAULT_DECIMALS", "POOL4_SHARE_DECIMALS", "SHARE_UNIT"):
        assert not hasattr(surf_models, banned), (
            f"{banned} hardcodes what A14 says to read live"
        )


def test_the_share_count_is_not_wei_suffixed_because_it_is_not_eighteen_decimal() -> None:
    """The naming asymmetry is the guardrail, not an oversight.

    Every ``_wei`` field in this module divides by ``1e18``. Shares divide by
    ``10 ** decimals`` (``1e24`` today). Two adjacent ``_wei`` fields with two
    different divisors is exactly the habit-trap that produced A14 -- and both
    wrong forms render as *plausible* numbers (a dead vault at ``1e18`` on the
    share price, an emissions farm at ``1e18`` on the supply), so nothing
    downstream would catch it.
    """
    names = {f.name for f in dataclasses.fields(Pool4VaultState)}
    assert "total_shares_raw" in names
    assert "total_shares_wei" not in names, (
        "the share count is back on the _wei convention it does not obey; "
        "a /1e18 there is wrong by a factor of a million and looks fine"
    )
    # the asset side genuinely is 18-decimal and keeps the suffix
    assert "total_assets_wei" in names
    assert "share_price_wei" in names


def test_the_vault_docstring_carries_the_decimals_warning() -> None:
    """WP7 reads this docstring at the moment it writes the divisor.

    The warning has to live where the mistake gets made, not only in the
    amendment log, so this pins that it is present and states the right
    divisor.
    """
    doc = _flat(Pool4VaultState.__doc__)
    assert "1e24" in doc
    assert "(amendment A14, verified live)" in doc
    assert "not an 18-decimal token" in doc


def test_the_hook_state_does_not_name_a_vault() -> None:
    """The vault address comes off the **dripper**, one hop further out.

    The hook's recovered interface names ``rewardsRecipient()`` and
    ``backstop()`` and no vault at all. A ``vault`` field here would be a field
    with no getter behind it — an open invitation to fill it by scraping the
    teaser page, which carries no addresses today and is not a source this
    dashboard would trust if it grew some.
    """
    hook = {f.name for f in dataclasses.fields(Pool4HookState)}
    assert "vault" not in hook
    assert "rewards_recipient" in hook
    assert "vault" in {f.name for f in dataclasses.fields(Pool4DripperState)}


def test_the_hook_state_carries_the_claimed_split_and_not_the_measured_one() -> None:
    """``rewardShareBps()`` is what the contract *claims*.

    The measured split is computed from the counters and the two are compared,
    never reconciled. A model field holding a measured percentage would be a
    derivation living in the wrong layer, and the drift key would have nothing
    left to disagree with.
    """
    names = {f.name for f in dataclasses.fields(Pool4HookState)}
    assert {"reward_share_bps", "bps_denominator"} <= names
    assert not [n for n in names if "measured" in n or n.endswith("_pct")]
    # the counters the measurement is taken over
    assert {
        "total_burned_wei", "total_rewarded_wei", "total_fee_token_wei",
    } <= names


def test_discovery_defaults_to_carrying_no_address() -> None:
    """A verdict, not an address.

    ``hook_addr`` defaults to ``None`` so a ``rejected`` or ``not-discovered``
    verdict cannot leave a stale address lying around for a downstream read to
    be pointed at. The address is something an ``adopted`` verdict *adds*.
    """
    d = Pool4Discovery(network=None, state="not-discovered")
    assert d.hook_addr is None
    assert d.token_addr is None
    assert d.detail is None
    assert d.source_tx_hash is None


def test_discovery_state_vocabulary_is_the_one_the_payload_key_uses() -> None:
    """One spelling of ``not-discovered``, not two.

    ``Pool4Discovery.state`` and ``pool4_discovery_state`` are the same word in
    two places; WP7 copies it from one to the other, and a hyphen-vs-underscore
    divergence would render an empty panel with no error anywhere.
    """
    for state in POOL4_DISCOVERY_STATES:
        assert Pool4Discovery(network="MAINNET", state=state).state == state


# ---------------------------------------------------------------------------
# §0.4 — every key has exactly one renderer
# ---------------------------------------------------------------------------

#: The five ``update_data`` signatures from §0.4, transcribed. This is the
#: **contract-side** copy; WP8 owns the screen-side ``SURF_WIDGET_SIGNATURES``
#: and the two are meant to be redundant. Deriving either from the other would
#: make the agreement test compare a constant against itself, which is the one
#: shape of test that can never fail.
POOL4_WIDGET_SIGNATURES: dict[str, tuple[str, ...]] = {
    "SurfPool4Flow": (
        "pool4_flow", "pool4_network", "pool4_as_of_hhmm",
    ),
    "SurfPool4Split": (
        "pool4_network",
        "pool4_measured_inference_pct", "pool4_measured_burn_pct",
        "pool4_measured_stakers_pct", "pool4_reward_share_bps",
        "pool4_bps_denominator", "pool4_split_drift_bps",
        "pool4_total_burned", "pool4_total_rewarded",
        "pool4_total_fee_token", "pool4_retained_eth",
        "pool4_last_claim_block", "pool4_unsettled_burn",
        "pool4_unsettled_stakers",
        # R1 control (c) belongs on the panel that renders the counters it
        # reconciles -- a disagreement rendered anywhere else would be a
        # verdict with its evidence on another screen.
        "pool4_counter_state", "pool4_counter_detail",
        # The Distributor's three-way split belongs on the panel named THE
        # SPLIT. It is a large panel now (23 kwargs) and WP4/WP5 may want to
        # revisit the panel budget -- but splitting the split across two
        # panels would be worse than a crowded one.
        "pool4_distributor_staking_bps", "pool4_distributor_nodes_bps",
        "pool4_distributor_bonding_bps",
        "pool4_distributor_staking_earned", "pool4_distributor_nodes_earned",
        "pool4_distributor_bonding_earned",
        "pool4_distributor_held_nodes", "pool4_distributor_held_bonding",
        # WP5: SPLIT annotates the measured stakers percentage with WHICH leg
        # it is, and the two annotations are 3x apart. It therefore needs the
        # topology as a fact rather than as an inference from another module's
        # internals. The address alone cannot carry it -- see
        # test_the_reward_path_is_a_word_because_an_address_cannot_say_unknown.
        "pool4_distributor_addr", "pool4_reward_path",
        "pool4_as_of_hhmm",
    ),
    "SurfPool4Ratchet": (
        "pool4_network", "pool4_tokens_in_pool", "pool4_cap_floor",
        "pool4_floor_distance", "pool4_floor_distance_pct",
        "pool4_burned_supply_pct", "pool4_total_supply",
        "pool4_inventory_cap", "pool4_cap_headroom",
        "pool4_cap_decay_per_day",
        "pool4_reserve_series", "pool4_eth_in_pool",
        "pool4_position_liquidity", "pool4_current_tick",
        "pool4_ref_tick", "pool4_backstop_centred", "pool4_as_of_hhmm",
    ),
    "SurfPool4Vault": (
        "pool4_network", "pool4_share_price", "pool4_share_price_delta_pct",
        "pool4_vault_assets", "pool4_vault_shares", "pool4_drip_per_day",
        "pool4_drippable", "pool4_can_drip", "pool4_backlog_imd",
        "pool4_backlog_days", "pool4_implied_apr_pct", "pool4_as_of_hhmm",
    ),
    "SurfPool4Hatches": (
        "pool4_hatches", "pool4_network", "pool4_discovery_state",
        "pool4_discovery_detail",
        # Its own kwarg, so the panel can give the citation its own line at a
        # width it controls -- rather than receiving it welded to the tail of a
        # sentence, where any fitting pass drops it first.
        "pool4_discovery_source_tx", "pool4_discovery_source",
        "pool4_hook_addr", "pool4_token_addr",
        "pool4_vault_addr", "pool4_distributor_addr", "pool4_reward_path",
        "pool4_dripper_addr",
        "pool4_as_of_hhmm",
    ),
}


def test_every_pool4_key_has_at_least_one_renderer() -> None:
    """§0.4: nothing joins ``_KEYS_WITHOUT_A_RENDERER``.

    A payload key nobody renders is a key the manager computes, persists and
    degrades for, that no reader will ever see.
    """
    rendered: set[str] = set()
    for kwargs in POOL4_WIDGET_SIGNATURES.values():
        rendered |= set(kwargs)
    orphans = sorted(set(POOL4_KEYS) - rendered)
    assert not orphans, f"pool4 keys with no renderer: {orphans}"


def test_no_pool4_widget_kwarg_is_missing_from_the_payload() -> None:
    """The other direction, and the one that actually bites.

    A kwarg with no key behind it is a panel line that is ``None`` forever and
    raises nothing, because the screen splats and ``**_kwargs`` swallows.
    """
    for widget, kwargs in POOL4_WIDGET_SIGNATURES.items():
        unbacked = sorted(set(kwargs) - set(POOL4_KEYS))
        assert not unbacked, f"{widget} takes keys not in the contract: {unbacked}"


def test_each_scalar_key_has_exactly_one_renderer_apart_from_the_two_shared_ones() -> None:
    """``pool4_network`` and ``pool4_as_of_hhmm`` are on all five panels by
    design — every title carries the network word and every panel carries the
    tier's own slower clock. Everything else is rendered exactly once, so
    there is one place to fix a wrong number.
    """
    counts: dict[str, int] = {}
    for kwargs in POOL4_WIDGET_SIGNATURES.values():
        for name in kwargs:
            counts[name] = counts.get(name, 0) + 1
    on_all_five = {"pool4_network", "pool4_as_of_hhmm"}
    # ``pool4_distributor_addr`` and ``pool4_reward_path`` are the deliberate
    # exception: one topology fact, needed by the two panels that would
    # otherwise disagree about it. That is the whole point -- a topology fact
    # split across two panels is how the next version of the 3x bug gets in --
    # so they are pinned at exactly two, not merely allowed to be > 1.
    on_two = {"pool4_distributor_addr", "pool4_reward_path"}
    assert {k for k, v in counts.items() if v > 1} == on_all_five | on_two
    assert counts["pool4_network"] == counts["pool4_as_of_hhmm"] == 5
    for key in on_two:
        assert counts[key] == 2, f"{key} reaches {counts[key]} panels, not 2"


def test_no_pool4_widget_takes_a_short_kwarg() -> None:
    """§0.1's no-new-alias decision, pinned from the contract side.

    WP8 pins it again on the widget side. Both copies are wanted: this one
    fails the moment the *plan* is departed from, before a widget exists.
    """
    for widget, kwargs in POOL4_WIDGET_SIGNATURES.items():
        short = [k for k in kwargs if not k.startswith("pool4_")]
        assert not short, f"{widget} takes short kwarg(s) {short}"


# ---------------------------------------------------------------------------
# purity
# ---------------------------------------------------------------------------

def test_the_module_still_imports_nothing_but_the_standard_library() -> None:
    """The pool4 block must not be what finally drags an import in here.

    Every surf module codes against this one, so an ``httpx`` or ``textual``
    import here would put a transport behind the widgets' own contract file.
    """
    source = inspect.getsource(surf_models)
    for banned in (
        "import httpx", "import asyncio", "from textual", "import textual",
        "import requests", "import time", "from datetime",
    ):
        assert banned not in source, f"surf_models reaches for {banned!r}"


def test_the_pool4_block_hardcodes_no_address() -> None:
    """Addresses live in ``data/surf_addresses.py`` and, on mainnet, are
    *discovered*. A literal here would be a testnet address one merge away from
    being rendered under a MAINNET title.
    """
    source = inspect.getsource(surf_models)
    import re

    literals = re.findall(r"0x[0-9a-fA-F]{40}", source)
    assert not literals, f"surf_models hardcodes address literal(s): {literals}"
