"""pool4 address discovery — the security suite (WP3).

The announce channel is permissionless and attacker-writable.  Six community
replies are already in it, anyone can send it a UTF-8 calldata transaction, and
a ``0x…`` scraped out of it is untrusted input whose failure mode is **rendering
an attacker's contract as the protocol's, with the reader's own money decision
behind it**.  So this file is not a correctness suite with some hostile cases
bolted on; every test here is an attack with a committed corpus behind it, and
the acceptance criterion for the package is that each one has been *proven to
bite* — invert the gate it guards, watch **that** test go red, restore.

The seven channel corpora are
``tests/fixtures/surf/pool4/announce_adversarial_*.json``.  Their manifest
entries name the attack; this file names the gate.  An eighth,
``discovery_persisted_hostile.json``, was covered here until 2026-09-02 and is
now read by ``tests/data/test_surf_pool4_client.py`` alone -- the retired
"Attack 8" banner below says why the cache-file gate went away rather than
moving.

**The day-one path is first on purpose** (plan R4).  There is no pool4 hook on
mainnet, so the code that actually executes on the day this ships is "discovery
finds nothing".  ``announce_undiscovered.json`` is the channel's *complete*
history — Blockscout returned ``next_page_params: null`` — so the claim that it
carries no candidate is exhaustive rather than a statement about a window.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from maxpane_dashboard.data.surf_models import POOL4_DISCOVERY_STATES
from maxpane_dashboard.data.surf_pool4 import (
    HOOK_TRIAGE_FLAGS,
    POOL4_REQUIRED_FLAGS,
    address_flag_word,
    candidate_addresses,
    checksum_address,
    discovery_verdict,
    fingerprint_verdict,
    flagged_candidates,
    has_pool4_flags,
    is_hook_shaped,
    is_self_post,
    adjudicate_candidates,
    discovery_source_word,
    docs_candidate_addresses,
    ranked_discovery,
    calldata_text,
    reestablish_provenance,
    self_post_addresses,
    triaged_candidates,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "surf" / "pool4"


def load(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text())


class ExplodingAnswers(dict):
    """A getter table that raises when asked about an address it does not hold.

    This is how "the nineteen decoys never reach a getter call" is *proven*
    rather than asserted.  A test that merely checked the adopted address would
    pass just as happily against an implementation that called every candidate's
    ``token()`` first and filtered afterwards — which is the implementation that
    turns the announce channel into an RPC amplifier.
    """

    def __init__(self, mapping):
        super().__init__({k.lower(): v for k, v in mapping.items()})
        self.asked: list[str] = []

    def __getitem__(self, key):
        self.asked.append(key.lower())
        if key.lower() not in self:
            raise AssertionError(
                f"a getter round was made against {key!r}, which no gate before "
                "the network should have let through"
            )
        return dict.__getitem__(self, key.lower())


def rows_of(fixture: dict) -> list[dict]:
    return fixture["rows"]


def announce_of(fixture: dict) -> str:
    return fixture["announce"]


def imd_of(fixture: dict) -> str:
    return fixture["known_mainnet_imd"]


# ---------------------------------------------------------------------------
# R4 — the day-one path, tested first
# ---------------------------------------------------------------------------


def test_the_complete_announce_history_yields_no_hook_candidate():
    """The primary path: nothing is deployed, so nothing may be adopted.

    The corpus is the whole channel, not a recent window, and its own scan
    lists every 20-byte word in every decoded self-post with that word's low
    14 bits.  Four distinct addresses are named across 22 self-posts — the burn
    executor, mainnet IMD, the channel itself and the dev wallet — and **not
    one of them is hook-shaped**.  That is the evidence for ``not-discovered``;
    the verdict is not a default.
    """
    fx = load("announce_undiscovered")
    assert fx["is_complete_channel_history"] is True
    assert fx["next_page_params"] is None

    rows = _rows_from_blockscout(fx["response"]["items"], fx["announce"])
    assert len(rows) == fx["self_post_count"], (
        "the row builder must see every self-post the fixture counted"
    )

    candidates = candidate_addresses(rows, fx["announce"])
    assert candidates, "a corpus with no addresses at all would make this vacuous"

    # The fixture's own scan is the independent list; ours must agree with it.
    scanned = {a["address"].lower() for a in fx["address_shaped_words_found"]}
    assert {c.lower() for c in candidates} == scanned

    assert triaged_candidates(candidates) == []
    assert flagged_candidates(candidates) == []
    assert [c.lower() for c in fx["hook_shaped_self_post_candidates"]] == []

    verdict = discovery_verdict(
        rows, fx["announce"], _MAINNET_IMD, ExplodingAnswers({}), network="MAINNET"
    )
    assert verdict.state == fx["expected"]["discovery_state"] == "not-discovered"
    assert verdict.hook_addr is None


_MAINNET_IMD = "0xD34a99Bc0f67aE1bbd63C660e6d0b0dd03E263B7"


def _rows_from_blockscout(items, announce: str) -> list[dict]:
    """Build ``feed_items``-shaped self-post rows from a raw Blockscout page.

    The manager does this in production; the test does it here so the corpus
    can stay the raw capture rather than a hand-derived one.
    """
    rows = []
    for item in items:
        frm = ((item.get("from") or {}).get("hash") or "")
        to = ((item.get("to") or {}).get("hash") or "")
        if frm.lower() != announce.lower() or to.lower() != announce.lower():
            continue
        raw = item.get("raw_input") or "0x"
        try:
            text = bytes.fromhex(raw[2:]).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            text = None
        rows.append(
            {
                "ts": None,
                "kind": "post",
                "from_addr": frm,
                "to_addr": to,
                "from_label": None,
                "text": text,
                "tx_hash": item.get("hash"),
                "label": None,
                "value_eth": 0.0,
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Attack 1 — provenance
# ---------------------------------------------------------------------------


def test_a_reply_and_an_inbound_tx_yield_no_candidate_and_no_getter_call():
    """PROVENANCE ATTACK.  Both hostile rows carry a *correctly flagged* address.

    That is what makes this the sharpest of the eight: the flag arithmetic
    would pass, the getters would pass, and the only thing standing between the
    reader and an attacker's pool is ``from == to == ANNOUNCE``.  The dev's own
    self-post in this corpus names no address, so the correct answer is no
    candidate at all — and zero ``eth_call`` rounds, which the exploding table
    below is what proves.
    """
    fx = load("announce_adversarial_reply_provenance")
    hostile = fx["attacker_addresses"]["hook_shaped"]
    assert has_pool4_flags(hostile), (
        "the attack is only a test of provenance if the address would otherwise "
        "pass every other gate"
    )

    candidates = candidate_addresses(rows_of(fx), announce_of(fx))
    assert candidates == fx["expected"]["candidates"] == []

    answers = ExplodingAnswers({})
    verdict = discovery_verdict(
        rows_of(fx), announce_of(fx), imd_of(fx), answers, network="MAINNET"
    )
    assert verdict.state == fx["expected"]["discovery_state"] == "not-discovered"
    assert len(answers.asked) == fx["expected"]["getter_calls_made"] == 0
    assert verdict.hook_addr is None


def test_the_hostile_rows_are_scanned_when_their_provenance_is_faked():
    """The provenance gate has to be the thing doing the work.

    Rewriting the reply's ``from_addr`` to the channel makes it a self-post and
    the same text then *does* yield the attacker's address.  Without this, a
    ``candidate_addresses`` that simply failed to find addresses in any text
    would pass the test above for the wrong reason.
    """
    fx = load("announce_adversarial_reply_provenance")
    hostile = fx["attacker_addresses"]["hook_shaped"]
    forged = [
        {**row, "from_addr": announce_of(fx), "to_addr": announce_of(fx)}
        for row in rows_of(fx)
    ]
    assert candidate_addresses(forged, announce_of(fx)) == [
        checksum_address(hostile)
    ]


# ---------------------------------------------------------------------------
# Attack 2 — the flag word.  0x0840 is the documented value and it is wrong.
# ---------------------------------------------------------------------------


def test_the_documented_flag_word_is_rejected_not_adopted():
    """FLAG ATTACK.  A genuine dev self-post naming a ``0x0840`` address.

    Provenance passes.  Every getter answers, and answers *correctly* —
    ``token()`` is real mainnet IMD, the bps pair is 1000/10000, the burn sink
    is ``0x…dEaD``.  The only thing wrong with this contract is that the
    PoolManager would never call ``beforeInitialize`` on it, because bit 13 is
    clear.

    A gate built from ``docs/imd_pool4_mechanics.md`` or from the plan body as
    written would **adopt** this address and **reject the real hook**.  Exactly
    backwards, and this test is the tripwire.
    """
    fx = load("announce_adversarial_flag_mismatch")
    candidate = fx["attacker_addresses"]["candidate"]
    assert address_flag_word(candidate) == int(
        fx["attacker_addresses"]["low_14_bits"], 16
    ) == 0x0840

    assert candidate_addresses(rows_of(fx), announce_of(fx)) == fx["expected"][
        "candidates"
    ]
    assert flagged_candidates([candidate]) == []

    state, detail = fingerprint_verdict(
        candidate, fx["eth_call_answers"][candidate.lower()], imd_of(fx)
    )
    assert state == fx["expected"]["verdict_state"] == "rejected"
    assert fx["expected"]["verdict_detail_names"] in detail

    verdict = discovery_verdict(
        rows_of(fx), announce_of(fx), imd_of(fx),
        ExplodingAnswers(fx["eth_call_answers"]), network="MAINNET",
    )
    assert verdict.state == fx["expected"]["discovery_state"] == "rejected"
    assert "flags" in (verdict.detail or "")
    assert verdict.hook_addr is None, (
        "a rejected verdict must not carry the address forward — a stale field "
        "is how a downstream read gets pointed at it anyway"
    )


def test_the_real_hook_passes_the_gate_that_rejects_the_documented_word():
    """The other half of A8, and the half a rejection-only test cannot show.

    All three Sepolia launch hooks and every synthetic ``…2840`` in the corpus
    must pass.  A gate that rejects everything would make every test above
    green.
    """
    ref = load("hook_flags_reference")
    assert ref["flag_word"] == "0x2840"
    assert ref["flag_word_int"] == POOL4_REQUIRED_FLAGS == 0x2840
    for addr, word in ref["address_low_14_bits"].items():
        assert address_flag_word(addr) == int(word, 16)
        assert has_pool4_flags(addr), f"{addr} is a real launch hook"


def test_the_triage_mask_is_not_the_gate():
    """``0x840`` survives in this module only as triage, and must stay apart.

    ``HOOK_TRIAGE_FLAGS`` decides which channel noise earns a *verdict*; it
    costs no network round trip and it adopts nothing.  If the two constants
    ever became equal, every test in this file that relies on a ``0x0840``
    rejection would still pass while the gate had silently become the
    documented, broken one.
    """
    assert HOOK_TRIAGE_FLAGS == 0x0840
    assert POOL4_REQUIRED_FLAGS == 0x2840
    assert HOOK_TRIAGE_FLAGS != POOL4_REQUIRED_FLAGS
    assert POOL4_REQUIRED_FLAGS & HOOK_TRIAGE_FLAGS == HOOK_TRIAGE_FLAGS
    # And the triage word alone never adopts.
    assert not has_pool4_flags("0x" + "0" * 36 + "0840")


# ---------------------------------------------------------------------------
# Attack 3 — subset vs equality
# ---------------------------------------------------------------------------


def test_a_returns_delta_hook_is_rejected_by_equality():
    """SUBSET-vs-EQUALITY ATTACK.  ``0x2844`` — every required bit, plus one.

    ``AFTER_SWAP_RETURNS_DELTA`` lets a hook take value out of the swap itself.
    A hook that can do that is a materially different contract from the one
    this dashboard describes, and a subset test (``low14 & required``) adopts
    it without noticing.  This is the case that decides whether the gate is
    written with ``&`` or ``==``.
    """
    fx = load("announce_adversarial_returns_delta")
    candidate = fx["attacker_addresses"]["candidate"]
    word = address_flag_word(candidate)
    assert word == 0x2844
    assert word & POOL4_REQUIRED_FLAGS == POOL4_REQUIRED_FLAGS, (
        "the attack is only a test of equality if a subset test would pass it"
    )
    assert not has_pool4_flags(candidate)

    state, detail = fingerprint_verdict(
        candidate, fx["eth_call_answers"][candidate.lower()], imd_of(fx)
    )
    assert state == "rejected"
    assert fx["expected"]["verdict_detail_names"] in detail

    verdict = discovery_verdict(
        rows_of(fx), announce_of(fx), imd_of(fx),
        ExplodingAnswers(fx["eth_call_answers"]), network="MAINNET",
    )
    assert verdict.state == fx["expected"]["discovery_state"] == "rejected"
    assert verdict.hook_addr is None


# ---------------------------------------------------------------------------
# Attack 4 — the token identity
# ---------------------------------------------------------------------------


def test_a_hook_shaped_contract_on_a_strangers_token_is_rejected():
    """TOKEN ATTACK — the most dangerous of the eight.

    Everything checks out: the flag word is the real ``0x2840``, all five
    getters answer, the bps pair is right, the burn sink is ``0x…dEaD``, the
    pool manager is the canonical one.  The *only* thing wrong is that
    ``token()`` is somebody else's ERC-20, and without that gate the panel
    renders an attacker's pool as the protocol's.
    """
    fx = load("announce_adversarial_wrong_token")
    candidate = fx["attacker_addresses"]["candidate"]
    assert has_pool4_flags(candidate), "flags must pass, or this tests the wrong gate"

    answers = fx["eth_call_answers"][candidate.lower()]
    state, detail = fingerprint_verdict(candidate, answers, imd_of(fx))
    assert state == fx["expected"]["verdict_state"] == "rejected"
    assert fx["expected"]["verdict_detail_names"] in detail
    assert fx["attacker_addresses"]["token_returned"].lower() in detail.lower()

    verdict = discovery_verdict(
        rows_of(fx), announce_of(fx), imd_of(fx),
        ExplodingAnswers(fx["eth_call_answers"]), network="MAINNET",
    )
    assert verdict.state == "rejected"
    assert verdict.hook_addr is None

    # And the same contract *with* the right token is adopted, so the gate is
    # the token identity and not some other accident of this fixture.
    healed = {**answers, "token": "0x" + "0" * 24 + imd_of(fx)[2:].lower()}
    assert fingerprint_verdict(candidate, healed, imd_of(fx))[0] == "adopted"


# ---------------------------------------------------------------------------
# Attack 5 — the silent contract (A10)
# ---------------------------------------------------------------------------


def test_a_candidate_that_answers_nothing_is_rejected_not_deferred():
    """SILENT-CONTRACT ATTACK.  Correct flag word, every getter dead.

    An EOA, a self-destructed contract or a contract with no fallback.  The
    rejection must name the first getter asked, and it must be a *verdict*: an
    unreadable candidate is not "we could not read it, try again", it is not
    adopted.
    """
    fx = load("announce_adversarial_dead_getters")
    candidate = fx["attacker_addresses"]["candidate"]
    assert has_pool4_flags(candidate)
    answers = fx["eth_call_answers"][candidate.lower()]
    assert all(v is None for v in answers.values())

    state, detail = fingerprint_verdict(candidate, answers, imd_of(fx))
    assert state == fx["expected"]["verdict_state"] == "rejected"
    assert fx["expected"]["verdict_detail_names"] in detail

    verdict = discovery_verdict(
        rows_of(fx), announce_of(fx), imd_of(fx),
        ExplodingAnswers(fx["eth_call_answers"]), network="MAINNET",
    )
    assert verdict.state == "rejected"
    assert verdict.hook_addr is None


def test_an_empty_return_is_a_failed_gate_not_a_passed_one():
    """A10, from the live capture: ``eth_call`` to an empty address gives ``"0x"``.

    No error, ``result: "0x"``.  So "the call did not error" is not "the getter
    answered", and a gate that conflates the two adopts an address with no code
    on it.  The probe below is real, captured from
    ``ethereum-sepolia-rpc.publicnode.com``, not imagined.
    """
    errors = load("rpc_error_states")
    empty = next(
        p for p in errors["probes"] if p["label"] == "call_to_an_empty_address"
    )
    assert "error" not in empty["response"], "the point of the capture"
    assert empty["response"]["result"] == "0x"

    good = "0x" + "0" * 24 + _MAINNET_IMD[2:].lower()
    candidate = "0x" + "0" * 36 + "2840"
    assert has_pool4_flags(candidate)

    answers = {
        "token": good,
        "rewardShareBps": "0x" + format(1000, "064x"),
        "BPS_DENOMINATOR": "0x" + format(10000, "064x"),
        "burnSink": "0x" + "0" * 60 + "dead",
        "poolManager": good,
    }
    assert fingerprint_verdict(candidate, answers, _MAINNET_IMD)[0] == "adopted"

    for dead in ("token", "rewardShareBps", "BPS_DENOMINATOR", "burnSink",
                 "poolManager"):
        state, detail = fingerprint_verdict(
            candidate, {**answers, dead: empty["response"]["result"]}, _MAINNET_IMD
        )
        assert state == "rejected", f"{dead} returning 0x must fail the gate"
        assert dead in detail


# ---------------------------------------------------------------------------
# Attack 6 — flooding
# ---------------------------------------------------------------------------


def test_nineteen_decoys_never_reach_a_getter_call():
    """FLOODING ATTACK.  Twenty address-shaped words, one real hook.

    The flag gate is pure arithmetic on the address and runs **before** any
    network round trip, so this post costs one ``eth_call`` round, not twenty.
    A discovery path that verifies first and filters second turns the announce
    channel into an RPC amplifier — and the decoys are chosen so a *subset*
    test would not save it either: every one of them is a strict superset of
    ``0x2840``.
    """
    fx = load("announce_adversarial_many_candidates")
    valid = fx["attacker_addresses"]["valid"]
    decoys = fx["attacker_addresses"]["decoys"]
    assert len(decoys) == 19

    for decoy in decoys:
        assert not has_pool4_flags(decoy), f"{decoy} must fail the equality gate"
    supersets = [
        d for d in decoys
        if address_flag_word(d) & POOL4_REQUIRED_FLAGS == POOL4_REQUIRED_FLAGS
    ]
    assert len(supersets) == 10, (
        "ten of the nineteen decoys are strict supersets of 0x2840, so a subset "
        "gate would call a getter on each of them; if that count reaches zero "
        "the flood no longer proves anything about & versus =="
    )

    # Provenance passes all twenty; arithmetic narrows to one, for free.
    candidates = candidate_addresses(rows_of(fx), announce_of(fx))
    assert len(candidates) == 20
    assert flagged_candidates(candidates) == fx["expected"]["candidates"] == [valid]
    assert len(triaged_candidates(candidates)) == 11, (
        "eleven survive triage and ten of those would survive a subset gate — "
        "the equality gate is what gets this to one round"
    )

    answers = ExplodingAnswers(fx["eth_call_answers"])
    verdict = discovery_verdict(
        rows_of(fx), announce_of(fx), imd_of(fx), answers, network="MAINNET"
    )
    assert verdict.state == fx["expected"]["discovery_state"] == "adopted"
    assert verdict.hook_addr == valid
    assert len(answers.asked) == fx["expected"]["expected_getter_rounds"] == 1
    assert answers.asked == [
        a.lower() for a in fx["expected"]["candidates_that_reach_a_getter"]
    ] == [valid.lower()]


# ---------------------------------------------------------------------------
# Attack 7 — markup, control characters and bidi
# ---------------------------------------------------------------------------


def test_markup_control_chars_and_bidi_yield_only_the_real_address():
    """MARKUP ATTACK.  Four self-posts, nothing may raise.

    * A valid address wrapped in Textual markup (``[/x]``, ``[$warning]``) and
      an ANSI escape — the address is extracted, the markup is not.
    * A literal ``0x`` followed by forty characters of markup: address-*shaped*
      in length, not hex, and therefore not a candidate.
    * An address wrapped in bidi overrides (U+202E/U+202C).  Those reorder what
      a reader **sees** without changing the bytes, so a scanner that strips
      them and then extracts would hand the panel an address whose rendered
      form is not its real form.  The regex requires a literal ``0x``
      immediately followed by forty hex digits, so this yields nothing.
    * A post whose ``text`` is ``None``.
    """
    fx = load("announce_adversarial_markup")
    candidates = candidate_addresses(rows_of(fx), announce_of(fx))

    assert candidates == [checksum_address(fx["attacker_addresses"]["valid"])]
    for must in fx["expected"]["candidates_must_include"]:
        assert checksum_address(must) in candidates

    bidi = fx["attacker_addresses"]["bidi_wrapped"]
    assert has_pool4_flags(bidi), (
        "the bidi address is correctly flagged — if it were not, excluding it "
        "would prove nothing about the reordering"
    )
    assert checksum_address(bidi) not in candidates

    assert any("[/x]" in (r["text"] or "") for r in rows_of(fx))
    assert any(r["text"] is None for r in rows_of(fx))

    verdict = discovery_verdict(
        rows_of(fx), announce_of(fx), imd_of(fx),
        ExplodingAnswers(fx["eth_call_answers"]), network="MAINNET",
    )
    assert verdict.state == "adopted"
    assert verdict.hook_addr == checksum_address(fx["attacker_addresses"]["valid"])


def test_a_tx_hash_is_not_an_address():
    """The same regex guard, stated as its own case.

    A 32-byte hash is 64 hex digits.  Without the trailing lookaround its first
    forty parse as an address, and the announce channel is full of hashes.
    """
    hash_hex = "0x" + "a" * 64
    rows = [{
        "from_addr": _MAINNET_IMD, "to_addr": _MAINNET_IMD,
        "text": f"see {hash_hex} for the details",
    }]
    assert candidate_addresses(rows, _MAINNET_IMD) == []


# ---------------------------------------------------------------------------
# Attack 8 — the cache file — RETIRED 2026-09-02
# ---------------------------------------------------------------------------
#
# Three tests here exercised ``surf_pool4.reverify_persisted`` against
# ``discovery_persisted_hostile.json``.  The function is gone: the manager no
# longer nominates the persisted address at all, so a cache file cannot put an
# address into the running, and re-verifying one could never have helped
# anyway -- the gates it re-ran are the forgeable half.  A ``…2840`` address is
# mineable (measured: 20,141 tries) and ``token()`` returns whatever the
# candidate's own contract chooses, so a hand-edited payload naming a mined
# address came back ADOPTED from the function whose docstring promised a
# rejection.  The full reasoning is the tombstone in ``data/surf_pool4.py``.
#
# The property that replaced it is provenance, and it is tested above rather
# than here: ``test_a_from_only_row_is_not_a_self_post`` and
# ``test_provenance_matches_across_the_case_mismatch_production_really_has``
# pin the only gate an attacker cannot satisfy.  The fixture is not orphaned --
# ``tests/data/test_surf_pool4_client.py`` still reads it.


# ---------------------------------------------------------------------------
# Cross-cutting properties of the gates
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fixture",
    [
        "announce_adversarial_reply_provenance",
        "announce_adversarial_flag_mismatch",
        "announce_adversarial_returns_delta",
        "announce_adversarial_wrong_token",
        "announce_adversarial_dead_getters",
        "announce_adversarial_many_candidates",
        "announce_adversarial_markup",
    ],
)
def test_no_adversarial_corpus_ever_adopts_an_attacker_address(fixture):
    """One sweep: across all seven channel corpora, only the intended hook wins.

    The per-attack tests each pin one gate.  This one pins the *outcome*, so a
    future refactor that moves a gate cannot quietly adopt an address that
    every attack fixture agrees is hostile.
    """
    fx = load(fixture)
    verdict = discovery_verdict(
        rows_of(fx), announce_of(fx), imd_of(fx),
        ExplodingAnswers(fx.get("eth_call_answers", {})), network="MAINNET",
    )
    hostile = {
        v.lower()
        for k, v in fx["attacker_addresses"].items()
        if isinstance(v, str) and k != "valid"
    }
    for decoy in fx["attacker_addresses"].get("decoys", []):
        hostile.add(decoy.lower())
    assert hostile, f"{fixture} names no hostile address -- nothing to sweep"

    benign = fx["attacker_addresses"].get("valid")
    if benign is None:
        # Five of the seven corpora have no address that may ever be adopted.
        # This branch used to be the *whole* body's ``if hook_addr is not
        # None`` guard, which meant those five ran zero assertions -- not even
        # ``state != "adopted"``.  It looked alive under mutation only because
        # a mutation that causes adoption makes ``hook_addr`` non-None; it was
        # blind in the direction the docstring actually promises.
        assert verdict.hook_addr is None, (
            f"{fixture} has no legitimate hook, so nothing may be adopted"
        )
        assert verdict.state != "adopted"
        assert verdict.state in POOL4_DISCOVERY_STATES
        assert verdict.token_addr is None
        return

    assert verdict.hook_addr is not None, (
        f"{fixture} carries one legitimate hook and it must win"
    )
    assert verdict.hook_addr.lower() not in hostile
    assert verdict.hook_addr.lower() == benign.lower()
    assert verdict.state == "adopted"


def test_the_gate_order_is_the_order_the_detail_names():
    """A rejection names the *first* gate that failed, not the last one checked.

    A candidate that fails everything must still say ``flags``: that is the
    cheapest gate and the one a reader can check themselves.
    """
    everything_wrong = "0x" + "0" * 36 + "0001"
    state, detail = fingerprint_verdict(everything_wrong, {}, _MAINNET_IMD)
    assert state == "rejected"
    assert detail.startswith("flags")


def test_get_hook_permissions_must_agree_with_the_address():
    """The corroborating source, and it can disagree.

    The address's low 14 bits are asserted by whoever mined the address; the
    permission struct is asserted by the contract.  Requiring agreement means a
    vanity address alone cannot carry an adoption.
    """
    from maxpane_dashboard.data.surf_pool4 import decode_hook_permissions

    ref = load("hook_flags_reference")
    assert decode_hook_permissions(ref["raw_result"]) == POOL4_REQUIRED_FLAGS

    hook = "0x" + "0" * 36 + "2840"
    base = {
        "token": "0x" + "0" * 24 + _MAINNET_IMD[2:].lower(),
        "rewardShareBps": "0x" + format(1000, "064x"),
        "BPS_DENOMINATOR": "0x" + format(10000, "064x"),
        "burnSink": "0x" + "0" * 60 + "dead",
        "poolManager": "0x" + "0" * 24 + _MAINNET_IMD[2:].lower(),
    }
    assert fingerprint_verdict(
        hook, {**base, "getHookPermissions": ref["raw_result"]}, _MAINNET_IMD
    )[0] == "adopted"

    # A hook whose struct says beforeInitialize is *not* set, on an address
    # that claims it is: a mined address plus a lying-by-omission contract.
    words = ["0" * 64] * 14
    words[2] = format(1, "064x")   # beforeAddLiquidity
    words[7] = format(1, "064x")   # afterSwap
    disagreeing = "0x" + "".join(words)
    assert decode_hook_permissions(disagreeing) == 0x0840
    state, detail = fingerprint_verdict(
        hook, {**base, "getHookPermissions": disagreeing}, _MAINNET_IMD
    )
    assert state == "rejected"
    assert "permissions" in detail

    state, detail = fingerprint_verdict(
        hook, {**base, "getHookPermissions": "0x"}, _MAINNET_IMD
    )
    assert state == "rejected"
    assert "permissions" in detail


def test_candidates_are_checksummed_deduplicated_and_order_preserving():
    """Three properties the plan names, and each has a failure behind it.

    **Checksummed** because the rest of the dashboard renders checksummed
    addresses and a lowercase one on the HATCHES panel would read as a
    different contract.  **Deduplicated** because a post naming the same
    address twice must not cost two getter rounds.  **Order-preserving**
    because the first spelling in the earliest post is the dev's own
    announcement order, and a set would make which candidate is adjudicated
    first depend on hash order.
    """
    lower = "0x5afe00d00c000000000000000000000000002840"
    upper = "0x5AFE00D00C000000000000000000000000002840"
    other = "0x5aFeBadF1a650000000000000000000000000840"
    rows = [
        {"from_addr": _MAINNET_IMD, "to_addr": _MAINNET_IMD,
         "text": f"first {other}"},
        {"from_addr": _MAINNET_IMD, "to_addr": _MAINNET_IMD,
         "text": f"then {lower} and again {upper} and {lower}"},
    ]
    got = candidate_addresses(rows, _MAINNET_IMD)
    assert got == [checksum_address(other), checksum_address(lower)]
    assert got == [
        "0x5aFeBadF1a650000000000000000000000000840",
        "0x5AfE00d00C000000000000000000000000002840",
    ], "EIP-55, recomputed with this repo's own keccak"
    assert len(got) == len(set(got))


def test_rows_that_are_not_rows_are_skipped_rather_than_raised_on():
    """Total over a payload shape nobody promised.

    A persisted feed, a half-decoded page and a producer mid-refactor all
    reach this, and the discovery path must not be the thing that takes the
    app down.
    """
    junk = [None, 42, "a string", {}, {"text": "0x" + "0" * 36 + "2840"},
            {"from_addr": _MAINNET_IMD, "to_addr": _MAINNET_IMD, "text": 7},
            {"from_addr": None, "to_addr": None, "text": None}]
    assert candidate_addresses(junk, _MAINNET_IMD) == []
    assert candidate_addresses(None, _MAINNET_IMD) == []
    assert discovery_verdict(None, _MAINNET_IMD, _MAINNET_IMD, {}).state == (
        "not-discovered"
    )


# ---------------------------------------------------------------------------
# The provenance gate, in the shape production actually hands it (S1, S2)
# ---------------------------------------------------------------------------
#
# Both tests below existed as holes rather than as failures: the corpora are
# all self-posts and to-only rows, spelled checksummed on both sides, so two
# separate halves of the gate did no work that any test could see.

#: What ``data/surf_client`` really puts in a ``feed_items`` row.  Blockscout's
#: ``from.hash`` / ``to.hash`` are checksummed on the wire and the client
#: lowercases both before they reach the row, while ``surf_addresses.ANNOUNCE``
#: is checksummed.  Every fixture in this directory spells both sides
#: checksummed, so no committed corpus has ever exercised the mismatch.
_ANNOUNCE_CHECKSUMMED = "0x200E710aCAA6A93bbc77146026328C40F1d60fB1"
_ANNOUNCE_LOWERCASE = _ANNOUNCE_CHECKSUMMED.lower()
_A_REAL_HOOK = "0x5AfE00d00C000000000000000000000000002840"


def test_provenance_matches_across_the_case_mismatch_production_really_has():
    """S2.  The comparison is case-insensitive because production needs it.

    ``surf_client`` lowercases ``from_addr`` and ``to_addr`` when it builds a
    feed row; ``surf_addresses.ANNOUNCE`` is EIP-55 checksummed.  So the two
    sides of this comparison **never match byte for byte in production**, and a
    case-sensitive ``==`` returns ``False`` for every real row.

    Dropping the ``.lower()`` from ``_same_addr`` reddens nothing in the rest
    of this suite, because every fixture spells both sides the same way.  It
    would ship a dashboard that discovers pool4 correctly against every
    committed corpus and finds **nothing at all** on mainnet -- A8's
    catastrophic direction reached without touching a flag constant, and
    silently, behind a fully green suite.

    So the assertion below deliberately uses the production spelling on each
    side rather than a matched pair.
    """
    assert _ANNOUNCE_LOWERCASE != _ANNOUNCE_CHECKSUMMED, (
        "if these ever became the same string this test would prove nothing"
    )
    row = {
        "from_addr": _ANNOUNCE_LOWERCASE,
        "to_addr": _ANNOUNCE_LOWERCASE,
        "text": f"pool4 hook {_A_REAL_HOOK}",
    }
    assert candidate_addresses([row], _ANNOUNCE_CHECKSUMMED) == [_A_REAL_HOOK]

    # And in the other direction, since either side may be the checksummed one.
    flipped = {**row, "from_addr": _ANNOUNCE_CHECKSUMMED,
               "to_addr": _ANNOUNCE_CHECKSUMMED}
    assert candidate_addresses([flipped], _ANNOUNCE_LOWERCASE) == [_A_REAL_HOOK]

    # Mixed case on one side only, which is what a half-normalised producer
    # would hand us.
    mixed = {**row, "to_addr": _ANNOUNCE_CHECKSUMMED}
    assert candidate_addresses([mixed], _ANNOUNCE_LOWERCASE) == [_A_REAL_HOOK]


def test_a_from_only_row_is_not_a_self_post():
    """S1.  The ``to_addr`` half of the gate, which no corpus exercises.

    Every adversarial corpus contains self rows (from == to == announce) and
    **to-only** rows (from = attacker, to = announce).  A hostile row therefore
    always fails on ``from_addr`` alone and the ``to_addr`` check never does
    work -- replacing it with ``if False:`` passes the whole suite.

    A **from-only** row is not hypothetical.  ``fetch_channel_txs`` returns
    every transaction touching the channel, including the announce wallet's own
    **outbound** transactions, and their calldata is decoded to text like any
    other row's.  Without the ``to_addr`` half, "self-post" silently widens to
    "anything the dev wallet ever sent" -- a swap, an approval, a transfer to a
    contract that happens to carry hook-shaped bytes.

    ``test_the_hostile_rows_are_scanned_when_their_provenance_is_faked`` forges
    *both* fields at once, so it cannot separate the halves.  This row forges
    exactly one.
    """
    stranger = "0x5AFeb0b0b0b0B0b0B0B0b0B0b0b0b0b0B0B00001"
    from_only = {
        "from_addr": _ANNOUNCE_CHECKSUMMED,
        "to_addr": stranger,
        "text": f"pool4 hook {_A_REAL_HOOK}",
    }
    assert candidate_addresses([from_only], _ANNOUNCE_CHECKSUMMED) == []

    to_only = {
        "from_addr": stranger,
        "to_addr": _ANNOUNCE_CHECKSUMMED,
        "text": f"pool4 hook {_A_REAL_HOOK}",
    }
    assert candidate_addresses([to_only], _ANNOUNCE_CHECKSUMMED) == []

    # Both halves together are what a self-post is, and it must still pass --
    # a gate that rejects everything would make the two assertions above
    # true for the wrong reason.
    self_post = {**from_only, "to_addr": _ANNOUNCE_CHECKSUMMED}
    assert candidate_addresses([self_post], _ANNOUNCE_CHECKSUMMED) == [_A_REAL_HOOK]

    # And end to end: a from-only row yields no verdict, not a rejection.
    answers = ExplodingAnswers({})
    assert discovery_verdict(
        [from_only], _ANNOUNCE_CHECKSUMMED, _MAINNET_IMD, answers
    ).state == "not-discovered"
    assert answers.asked == []


def test_the_address_prefix_is_lowercase_0x_and_that_is_a_decision():
    """S11.  ``0X`` is not accepted, deliberately.

    Widening ``ADDRESS_RE`` to ``0[xX]`` reddens nothing today, so the strict
    form could be relaxed by anyone who thought it was an oversight.  It is
    not.  The announce channel's **complete** history contains eight
    ``0x``-prefixed addresses and zero ``0X``-prefixed ones, so the tolerance
    would buy nothing real -- and on an attacker-writable channel every extra
    accepted spelling is one more form that renders differently from the way it
    parses, which is the whole subject of the bidi case above.
    """
    hook_body = _A_REAL_HOOK[2:]
    strict = {"from_addr": _MAINNET_IMD, "to_addr": _MAINNET_IMD,
              "text": f"hook 0x{hook_body}"}
    loose = {"from_addr": _MAINNET_IMD, "to_addr": _MAINNET_IMD,
             "text": f"hook 0X{hook_body}"}
    assert candidate_addresses([strict], _MAINNET_IMD) == [_A_REAL_HOOK]
    assert candidate_addresses([loose], _MAINNET_IMD) == []

    scan = load("announce_undiscovered")["address_shaped_words_found"]
    assert scan, "the corpus scan is the evidence for this decision"
    assert all(a["address"].startswith("0x") for a in scan)


def test_the_flags_detail_says_so_when_the_candidate_is_not_an_address():
    """S13.  The branch ``test_the_gate_order_...`` never reaches.

    That test passes a real, well-formed address whose bits are wrong, so
    ``address_flag_word`` returns a number and the detail renders a hex word.
    The other branch -- ``None``, junk, a truncated paste -- has its own
    wording, and it is the wording a reader sees when a *cache file* has been
    edited to something that is not an address at all.
    """
    for junk in (None, "", "0x", "not-an-address", "0x1234", 42,
                 "0x" + "٠" * 40):
        state, detail = fingerprint_verdict(junk, {}, _MAINNET_IMD)
        assert state == "rejected"
        assert detail.startswith("flags not an address"), detail

    state, detail = fingerprint_verdict(
        "0x" + "0" * 36 + "0001", {}, _MAINNET_IMD
    )
    assert detail.startswith("flags 0x0001"), (
        "a real address reports its real word, so the two branches are "
        "distinguishable in the panel"
    )


def test_a_non_ascii_digit_address_is_rejected_by_every_predicate(
):
    """S4.  Two predicates used to disagree about what an address is.

    ``int(body, 16)`` accepts every Unicode decimal digit; ``body.encode(
    "ascii")`` accepts none of them.  So forty FULLWIDTH DIGIT characters
    spelling ``…2840`` gave ``address_flag_word() == 0x2840``,
    ``has_pool4_flags() == True`` and ``is_hook_shaped() == True`` while
    ``checksum_address`` raised ``UnicodeEncodeError`` -- in a function whose
    docstring promises totality over third-party text.

    Reachable, not theoretical.  It was found on the persisted-cache path --
    a ``pool4_hook_addr`` of fullwidth digits passed the flag gate and the
    adopted branch then checksummed it and took the app down -- and that path
    has since been retired (see "Attack 8", above).  Retiring it removed one
    caller and not the class: an address reaches ``fingerprint_verdict`` from
    anywhere and ``expected_token`` is caller-supplied, so the end-to-end half
    below goes through those instead.  The unit half alone would not have
    caught the crash.
    """
    families = {
        "fullwidth": "０",          # FULLWIDTH DIGIT ZERO
        "arabic-indic": "٠",       # ARABIC-INDIC DIGIT ZERO
        "devanagari": "०",         # DEVANAGARI DIGIT ZERO
    }
    for name, zero in families.items():
        assert zero.isdigit() and not zero.isascii(), name
        body = zero * 36 + "2840"
        assert int(body[:36] + "2840", 16) == 0x2840, (
            f"{name} must really parse as 0x2840 under int(), or this test "
            "does not reproduce the defect"
        )
        addr = "0x" + body
        assert address_flag_word(addr) is None, name
        assert has_pool4_flags(addr) is False, name
        assert is_hook_shaped(addr) is False, name
        assert checksum_address(addr) is None, name

    # Wholly non-ASCII, and mixed ASCII/non-ASCII, both rejected.
    assert address_flag_word("0x" + "０" * 40) is None
    assert checksum_address("0x" + "a" * 39 + "０") is None

    # End to end, through the live entry points.
    #
    # The crash was first found on a cache-file path that has since been
    # retired, but retiring it removed one caller and not the class: an
    # address reaches ``fingerprint_verdict`` from anywhere, and
    # ``expected_token`` is caller-supplied.  Both must reject rather than
    # raise.
    hostile = "0x" + "０" * 36 + "2840"
    answers = {
        "token": "0x" + "0" * 24 + _MAINNET_IMD[2:].lower(),
        "rewardShareBps": "0x" + format(1000, "064x"),
        "BPS_DENOMINATOR": "0x" + format(10000, "064x"),
        "burnSink": "0x" + "0" * 60 + "dead",
        "poolManager": "0x" + "0" * 24 + _MAINNET_IMD[2:].lower(),
    }
    state, detail = fingerprint_verdict(hostile, answers, _MAINNET_IMD)
    assert state == "rejected"
    assert detail.startswith("flags not an address")

    real = "0x" + "0" * 36 + "2840"
    rows = [{"from_addr": _MAINNET_IMD, "to_addr": _MAINNET_IMD,
             "text": f"hook {real}"}]
    verdict = discovery_verdict(rows, _MAINNET_IMD, hostile, {real: answers})
    assert verdict.state == "rejected", (
        "a non-ASCII expected_token can match nothing -- and must not raise "
        "on its way to saying so"
    )
    assert verdict.hook_addr is None


def test_a_long_hex_string_never_acquires_a_flag_word():
    """S10.  The length test is equality, not a minimum.

    Short input was covered; long input was not.  Relaxing ``!= 40`` to
    ``< 40`` would give a 64-nibble transaction hash the flag word of its last
    fourteen bits -- and the announce channel is full of transaction hashes.
    """
    hash_ending_2840 = "0x" + "a" * 60 + "2840"
    assert len(hash_ending_2840) - 2 == 64
    assert address_flag_word(hash_ending_2840) is None
    assert has_pool4_flags(hash_ending_2840) is False
    assert checksum_address(hash_ending_2840) is None

    # 41 and 39 nibbles: one over and one under, both refused.
    assert len("0" * 37 + "2840") == 41 and len("0" * 35 + "2840") == 39
    assert address_flag_word("0x" + "0" * 37 + "2840") is None
    assert address_flag_word("0x" + "0" * 35 + "2840") is None
    # Exactly 40 is the one that works.
    assert address_flag_word("0x" + "0" * 36 + "2840") == 0x2840


def test_answered_needs_a_whole_word_not_merely_a_non_empty_body():
    """S6.  A10's control was pinned only at its degenerate point.

    Every test fed :func:`answered` the literal ``"0x"``, so the 64-nibble
    threshold could be relaxed all the way to ``>= 1`` with the suite green.
    A truncated answer is not a getter that answered: it is a word this module
    cannot decode, and letting it through means ``_uint`` reads a short slice
    and returns ``None`` while the *gate* has already said yes.
    """
    from maxpane_dashboard.data.surf_pool4 import answered

    assert answered("0x" + "0" * 64) is True
    assert answered("0x" + "0" * 63) is False, "one nibble short of a word"
    assert answered("0x00") is False
    assert answered("0xdead") is False
    assert answered("0x") is False
    assert answered(None) is False
    assert answered(0) is False

    # And the gate agrees with the decoder, which is the point of the
    # threshold: a body too short to decode must not pass.
    hook = "0x" + "0" * 36 + "2840"
    base = {
        "token": "0x" + "0" * 24 + _MAINNET_IMD[2:].lower(),
        "rewardShareBps": "0x" + format(1000, "064x"),
        "BPS_DENOMINATOR": "0x" + format(10000, "064x"),
        "burnSink": "0x" + "0" * 60 + "dead",
        "poolManager": "0x" + "0" * 24 + _MAINNET_IMD[2:].lower(),
    }
    assert fingerprint_verdict(hook, base, _MAINNET_IMD)[0] == "adopted"
    for truncated in ("0x" + "0" * 63, "0xdead", "0x00"):
        state, detail = fingerprint_verdict(
            hook, {**base, "rewardShareBps": truncated}, _MAINNET_IMD
        )
        assert state == "rejected", truncated
        assert "rewardShareBps" in detail


def test_decode_hook_permissions_refuses_a_short_struct():
    """S12.  The length guard on the corroborating source.

    ``getHookPermissions()`` returns fourteen ABI words.  A short answer means
    a different contract or a truncated read, and decoding it anyway would
    silently drop the trailing permissions -- reading the *absence* of bytes as
    the absence of a permission, which is how a returns-delta hook could
    corroborate a clean address.
    """
    from maxpane_dashboard.data.surf_pool4 import (
        HOOK_PERMISSION_BITS, decode_hook_permissions,
    )

    ref = load("hook_flags_reference")
    full = ref["raw_result"]
    assert decode_hook_permissions(full) == POOL4_REQUIRED_FLAGS
    assert len(full) - 2 == 64 * len(HOOK_PERMISSION_BITS)

    for short in (full[: 2 + 64 * 13], full[: 2 + 64 * 8], "0x" + "0" * 64, "0x"):
        assert decode_hook_permissions(short) is None, len(short)

    # The case the guard exists for, and the only one that distinguishes it
    # from the loop's own ValueError.
    #
    # Truncate on a *word* boundary and the loop's fourteenth slice is empty,
    # ``int("", 16)`` raises and the answer is None either way -- so a test
    # that only truncates on boundaries cannot see the guard at all.
    # Truncate MID-WORD and the fourteenth slice is 32 valid hex characters
    # that parse cleanly as zero, so without the guard this returns a
    # confident 0x2840 from an answer that was cut off: the absence of bytes
    # read as the absence of a permission. That is precisely how a
    # returns-delta hook could corroborate a clean address.
    mid_word = full[: 2 + 64 * 13 + 32]
    assert len(mid_word) - 2 == 64 * 13 + 32, "not on a word boundary"
    assert decode_hook_permissions(mid_word) is None, (
        "a truncated struct must be unread, never a clean flag word"
    )

    # Extra trailing words are tolerated -- ABI padding is not a truncation --
    # so the guard is a floor and not an equality, and it says which.
    assert decode_hook_permissions(full + "0" * 64) == POOL4_REQUIRED_FLAGS


# ---------------------------------------------------------------------------
# S15 - provenance that outlives the channel window
# ---------------------------------------------------------------------------
#
# feed_items keeps 25 rows against a channel running at ~2.55 days per post, so
# about 64 days after the hook is announced its self-post ages out and a
# genuine adoption lapses to Sepolia. Persisting the announcing transaction's
# HASH and fetching that transaction is the fix -- and the hash is a pointer to
# a credential, never a credential. Everything that decides is recomputed from
# the fetched transaction; the cache only says where to look.

_TX_HASH = "0x" + "5a" * 32
_BIDI_ON, _BIDI_OFF = "‮", "‬"


#: A mined block number.  Every helper below carries one, because an unmined
#: transaction is refused: see
#: ``test_a_pending_transaction_is_a_claim_and_not_a_fact``.
_MINED_BLOCK = "0x18a2c1"


def _self_post_tx(text, from_addr=None, to_addr=None, tx_hash=_TX_HASH,
                  block=_MINED_BLOCK, **extra):
    """A fetched transaction in ``eth_getTransactionByHash`` shape."""
    tx = {
        "hash": tx_hash,
        "blockNumber": block,
        "from": from_addr if from_addr is not None else _ANNOUNCE_LOWERCASE,
        "to": to_addr if to_addr is not None else _ANNOUNCE_LOWERCASE,
    }
    if isinstance(text, str):
        tx["input"] = "0x" + text.encode("utf-8").hex()
    tx.update(extra)
    return tx


def test_a_fetched_self_post_reestablishes_provenance_for_the_address_it_names():
    tx = _self_post_tx(f"pool4 is live at {_A_REAL_HOOK} -- enjoy")
    ok, detail = reestablish_provenance(
        tx, _ANNOUNCE_CHECKSUMMED, _A_REAL_HOOK, expected_tx_hash=_TX_HASH)
    assert ok is True
    assert _A_REAL_HOOK in detail

    # Production spelling on every side, per S2: the row is lowercased, ANNOUNCE
    # is checksummed, and whoever persisted the claim may have spelled it
    # either way.
    assert reestablish_provenance(
        tx, _ANNOUNCE_CHECKSUMMED, _A_REAL_HOOK.lower())[0] is True
    assert reestablish_provenance(
        tx, _ANNOUNCE_LOWERCASE, "0x" + _A_REAL_HOOK[2:].upper())[0] is True


def test_reestablishment_reuses_the_one_provenance_rule_rather_than_copying_it():
    """The S1 lesson, structurally.

    ``candidate_addresses`` and ``reestablish_provenance`` both go through
    :func:`self_post_addresses`, so the ``from``/``to`` rule and the
    ``ADDRESS_RE`` extraction have exactly one body. A second implementation is
    how one half of the gate ended up with no coverage the first time: deleting
    the ``to_addr`` check passed the entire suite.
    """
    import inspect

    from maxpane_dashboard.data import surf_pool4 as _P

    for fn in (_P.candidate_addresses, _P.reestablish_provenance):
        src = inspect.getsource(fn)
        assert "self_post_addresses" in src, fn.__name__
        assert "ADDRESS_RE" not in src, (
            f"{fn.__name__} extracts addresses itself instead of going through "
            "the shared rule"
        )
    # And the from/to rule itself has one body, reached by both paths.
    assert "_same_addr" not in inspect.getsource(_P.self_post_addresses)
    assert "is_self_post" in inspect.getsource(_P.self_post_addresses)
    assert "is_self_post" in inspect.getsource(_P.reestablish_provenance)

    # And they agree on the same input, which is the property that matters.
    text = f"hook {_A_REAL_HOOK} and {_MAINNET_IMD}"
    row = {"from_addr": _ANNOUNCE_LOWERCASE, "to_addr": _ANNOUNCE_LOWERCASE,
           "text": text}
    from_rows = candidate_addresses([row], _ANNOUNCE_CHECKSUMMED)
    assert from_rows == self_post_addresses(
        _ANNOUNCE_LOWERCASE, _ANNOUNCE_LOWERCASE, text, _ANNOUNCE_CHECKSUMMED)
    assert len(from_rows) == 2
    for addr in from_rows:
        assert reestablish_provenance(
            _self_post_tx(text), _ANNOUNCE_CHECKSUMMED, addr)[0] is True


def _refusal_cases():
    stranger = "0x5AFeb0b0b0b0B0b0B0B0b0B0b0b0b0b0B0B00001"
    return [
        ("not a self-post: inbound from a stranger",
         _self_post_tx("hook " + _A_REAL_HOOK, from_addr=stranger)),
        ("from the channel to somewhere else (the S1 asymmetry)",
         _self_post_tx("hook " + _A_REAL_HOOK, to_addr=stranger)),
        ("a self-post naming a DIFFERENT address",
         _self_post_tx("hook 0x5aFeBadF1a650000000000000000000000000840")),
        ("a self-post naming no address at all",
         _self_post_tx("pool4 is live, more soon")),
        ("calldata that is not valid UTF-8",
         _self_post_tx(None, input="0xff" + "fe" * 40)),
        ("calldata that is not hex", _self_post_tx(None, input="0xzz")),
        ("calldata of odd length", _self_post_tx(None, input="0xabc")),
        ("empty calldata", _self_post_tx(None, input="0x")),
        ("no calldata field at all", {"hash": _TX_HASH,
                                      "from": _ANNOUNCE_LOWERCASE,
                                      "to": _ANNOUNCE_LOWERCASE}),
        ("the address appears only inside a longer hex run",
         _self_post_tx("hash 0x" + _A_REAL_HOOK[2:] + "dead")),
        ("bidi-wrapped, so it renders as the address but is not one",
         _self_post_tx("hook 0x" + _BIDI_ON + _A_REAL_HOOK[2:] + _BIDI_OFF)),
        ("an explicitly failed transaction",
         _self_post_tx("hook " + _A_REAL_HOOK, status="error")),
        ("an explicitly reverted transaction",
         _self_post_tx("hook " + _A_REAL_HOOK, result="reverted")),
        ("a pending transaction, blockNumber null",
         _self_post_tx("hook " + _A_REAL_HOOK, block=None)),
        ("a contract creation, to is null",
         _self_post_tx("hook " + _A_REAL_HOOK, to_addr=None,
                       **{"to": None})),
        ("not a transaction at all", None),
        ("a transaction that is not a mapping", "0xdeadbeef"),
        ("a transaction that is a list", [_A_REAL_HOOK]),
    ]


@pytest.mark.parametrize("case, tx", _refusal_cases(), ids=lambda v: v if isinstance(v, str) else "")
def test_reestablishment_refuses_everything_that_is_not_the_credential(case, tx):
    """Each row is a way the cache's pointer could resolve to something else.

    None may return ``True`` and none may raise: a fetched transaction is
    third-party input exactly as a channel row is.
    """
    ok, detail = reestablish_provenance(tx, _ANNOUNCE_CHECKSUMMED, _A_REAL_HOOK)
    assert ok is False, case
    assert isinstance(detail, str) and detail, case


def test_a_self_post_naming_several_addresses_still_proves_the_claimed_one():
    """The flood shape, one layer out.

    A post may name a hook beside a token, a router and a sink. The claim under
    test is whether *this* address is among them -- not whether it is the only
    one, which would let one extra word in a legitimate announcement break a
    two-month-old adoption.
    """
    others = ["0x5aFedeC000000000000000000000000000002847", _MAINNET_IMD]
    text = f"migration: {others[0]} {_A_REAL_HOOK} {others[1]}"
    tx = _self_post_tx(text)
    assert reestablish_provenance(tx, _ANNOUNCE_CHECKSUMMED, _A_REAL_HOOK)[0] is True
    for other in others:
        assert reestablish_provenance(tx, _ANNOUNCE_CHECKSUMMED, other)[0] is True
    assert reestablish_provenance(
        tx, _ANNOUNCE_CHECKSUMMED, "0x" + "0" * 36 + "2840")[0] is False


def test_the_fetched_transaction_must_be_the_one_that_was_cited():
    """A client returning the wrong transaction must not be believed.

    This check lives here rather than in the client because "is this the
    transaction I asked for?" is part of the trust decision, not part of the
    transport -- and the transport is the thing that could be wrong. It
    compares the transaction's *self-reported* hash, so it catches an ordinary
    client bug and not an RPC that forges the field; recomputing the hash from
    the transaction is out of reach, agreement is not. Same posture as the
    curator's publisher-asserted ``content_hash``.
    """
    other = "0x" + "b1" * 32
    tx = _self_post_tx("hook " + _A_REAL_HOOK, tx_hash=other)
    ok, detail = reestablish_provenance(
        tx, _ANNOUNCE_CHECKSUMMED, _A_REAL_HOOK, expected_tx_hash=_TX_HASH)
    assert ok is False
    assert other in detail and _TX_HASH in detail

    stripped = {k: v for k, v in tx.items() if k != "hash"}
    assert reestablish_provenance(
        stripped, _ANNOUNCE_CHECKSUMMED, _A_REAL_HOOK,
        expected_tx_hash=_TX_HASH)[0] is False

    # With no hash cited there is nothing to check, and the rest still decides.
    assert reestablish_provenance(
        tx, _ANNOUNCE_CHECKSUMMED, _A_REAL_HOOK)[0] is True


def test_no_parameter_lets_a_cache_assert_the_address_it_wants():
    """The bypass this design exists to make impossible.

    A cache that supplied a hash **and** an address, where the address was
    believed because the hash resolved, is the persisted-adoption bypass in a
    new hat. No argument here can produce ``True`` on its own: ``expected_addr``
    is the claim under test, and only the fetched transaction's own calldata
    can satisfy it.
    """
    import inspect

    for tx in (None, {}, {"hash": _TX_HASH},
               {"hash": _TX_HASH, "from": _ANNOUNCE_LOWERCASE,
                "to": _ANNOUNCE_LOWERCASE}):
        assert reestablish_provenance(
            tx, _ANNOUNCE_CHECKSUMMED, _A_REAL_HOOK,
            expected_tx_hash=_TX_HASH)[0] is False

    # Every field right EXCEPT the calldata.
    assert reestablish_provenance(
        _self_post_tx("pool4 is live"), _ANNOUNCE_CHECKSUMMED, _A_REAL_HOOK,
        expected_tx_hash=_TX_HASH)[0] is False

    params = inspect.signature(reestablish_provenance).parameters
    assert set(params) == {"tx", "announce", "expected_addr", "expected_tx_hash"}, (
        "a new parameter here is a new way for a caller to assert provenance "
        "instead of proving it -- add it deliberately or not at all"
    )


def test_calldata_is_decoded_raw_and_never_normalised_before_extraction():
    """S16.  ``ADDRESS_RE`` must see the bytes as posted.

    Normalising first -- stripping bidi controls, case folding, NFKC -- is how
    a wrapper that reorders the rendered text becomes a candidate whose
    displayed form is not its real form. The decode is UTF-8 and nothing else.
    """
    text = "  [/x] hook " + _BIDI_ON + _A_REAL_HOOK + _BIDI_OFF + " \x1b[31m  "
    assert calldata_text("0x" + text.encode("utf-8").hex()) == text, (
        "byte for byte, including the leading whitespace and the controls"
    )
    assert calldata_text("0x") is None
    assert calldata_text("0xabc") is None
    assert calldata_text("0xzz") is None
    assert calldata_text(None) is None
    assert calldata_text(b"\x00") is None
    assert calldata_text("0xff") is None, "not UTF-8"

    # The bidi-wrapped address survives the decode and is still refused by the
    # extractor, which is the division of labour this test is about.
    wrapped = "hook 0x" + _BIDI_ON + _A_REAL_HOOK[2:] + _BIDI_OFF
    assert calldata_text("0x" + wrapped.encode("utf-8").hex()) == wrapped
    assert self_post_addresses(
        _ANNOUNCE_LOWERCASE, _ANNOUNCE_LOWERCASE, wrapped,
        _ANNOUNCE_CHECKSUMMED) == []


def test_reestablishment_reads_both_transaction_shapes():
    """``eth_getTransactionByHash`` and Blockscout disagree about spelling only.

    The field names are plumbing; the rule that decides is the same function in
    both cases. WP6 may hand either shape.
    """
    text = f"hook {_A_REAL_HOOK}"
    rpc = _self_post_tx(text)
    blockscout = {
        "hash": _TX_HASH,
        "from": {"hash": _ANNOUNCE_CHECKSUMMED},
        "to": {"hash": _ANNOUNCE_CHECKSUMMED},
        "raw_input": "0x" + text.encode("utf-8").hex(),
        "block_number": 1_614_017,
        "status": "ok",
        "result": "success",
    }
    expected = (True, f"{_A_REAL_HOOK} is named by self-post {_TX_HASH}")
    for shape, tx in (("rpc", rpc), ("blockscout", blockscout)):
        assert reestablish_provenance(
            tx, _ANNOUNCE_CHECKSUMMED, _A_REAL_HOOK,
            expected_tx_hash=_TX_HASH) == expected, shape


def test_a_pending_transaction_is_a_claim_and_not_a_fact():
    """``blockNumber: null`` is refused, and a confirmation depth is not required.

    An unmined transaction can be broadcast, cited, and then dropped from the
    mempool -- after which the dashboard would rest an adoption on a
    transaction that exists on no chain.

    **Mined is required; depth deliberately is not.** A depth rule would need a
    head block -- one more parameter, one more thing that can be stale -- to
    prevent a failure whose consequence is milder than the one it adds: a reorg
    that removes a cited post makes the next fetch come back pending and the
    view lapse to Sepolia, which is visible, temporary and self-correcting on
    the following tick. It would also delay a legitimate adoption by N blocks
    at the moment the view most wants to show it. Failing towards "no mainnet
    yet" is the safe direction.
    """
    text = "hook " + _A_REAL_HOOK
    assert reestablish_provenance(
        _self_post_tx(text, block=None), _ANNOUNCE_CHECKSUMMED, _A_REAL_HOOK
    ) == (False, "the cited transaction is not mined yet")

    # A transaction with no block field at all is equally unproven.
    naked = {k: v for k, v in _self_post_tx(text).items() if k != "blockNumber"}
    assert reestablish_provenance(
        naked, _ANNOUNCE_CHECKSUMMED, _A_REAL_HOOK)[0] is False

    # One confirmation is enough: no depth is demanded.
    for block in ("0x1", 1, "0x18a2c1", 1_614_017):
        assert reestablish_provenance(
            _self_post_tx(text, block=block), _ANNOUNCE_CHECKSUMMED,
            _A_REAL_HOOK)[0] is True, block

    # Blockscout's spelling counts as mined too.
    bs = {k: v for k, v in _self_post_tx(text).items() if k != "blockNumber"}
    bs["block_number"] = 1_614_017
    assert reestablish_provenance(bs, _ANNOUNCE_CHECKSUMMED, _A_REAL_HOOK)[0] is True


def test_a_contract_creation_is_not_a_self_post_and_says_so():
    """``to: null`` is "we looked and it is not one", never "we could not look".

    The distinction is the reason A10 exists. A failed read should make a view
    fall back; a transaction that is simply not a self-post is a settled
    negative, and the two must not share a detail line -- a reader who sees the
    same sentence for both cannot tell whether to retry or to stop believing
    the citation.
    """
    text = "hook " + _A_REAL_HOOK
    creation = _self_post_tx(text)
    creation["to"] = None
    ok, detail = reestablish_provenance(
        creation, _ANNOUNCE_CHECKSUMMED, _A_REAL_HOOK)
    assert ok is False
    assert "not a self-post" in detail
    assert "None" in detail, "the detail shows what the recipient actually was"

    assert is_self_post(_ANNOUNCE_LOWERCASE, None, _ANNOUNCE_CHECKSUMMED) is False
    assert is_self_post(None, None, _ANNOUNCE_CHECKSUMMED) is False
    assert is_self_post(_ANNOUNCE_LOWERCASE, _ANNOUNCE_CHECKSUMMED,
                        _ANNOUNCE_CHECKSUMMED) is True

    # ...and it does NOT share the wording used when the post is genuine but
    # names nothing, which is a different fact about a different thing.
    quiet = reestablish_provenance(
        _self_post_tx("pool4 is live"), _ANNOUNCE_CHECKSUMMED, _A_REAL_HOOK)[1]
    assert "names no address" in quiet
    assert quiet != detail


def test_the_docstring_does_not_promise_more_than_the_endpoint_delivers():
    """A27's deleted sentence, kept deleted.

    Nothing here recomputes ``keccak(rlp(tx))``, so a hostile endpoint can
    return arbitrary content for a hash and this function will believe it. What
    the design closes is the *cache*; what it cannot close is the RPC. A
    docstring that read "provenance re-established from the chain" without
    saying which chain-shaped thing is trusted is exactly the reassurance that
    had to be removed from ``reverify_persisted`` before it was retired.
    """
    import inspect

    doc = inspect.getdoc(reestablish_provenance) or ""

    # The limit itself, not merely the vocabulary of it. Checking that the word
    # "endpoint" appears would pass for a docstring that says the endpoint is
    # trusted to answer honestly -- the opposite claim in the same words. These
    # three phrases are the claim.
    assert "nothing recomputes" in doc, "what is NOT verified"
    assert "will believe it" in doc, "and what follows from that"
    assert "not closed" in doc, "and which half of the boundary stays open"
    assert "keccak" in doc

    for reassurance in ("guarantee", "guaranteed", "proves the chain",
                        "cannot be forged", "trusted to answer honestly",
                        "assumed honest"):
        assert reassurance not in doc.lower(), reassurance
    assert "redundant" in doc, (
        "the hash check's ownership is the client's; this copy must say so"
    )


# ---------------------------------------------------------------------------
# MAINNET 2026-09-02 - the docs candidate source, and how it is ranked
# ---------------------------------------------------------------------------
#
# The announce channel has not named the mainnet hook, so A27's gate correctly
# refuses and the view would show SEPOLIA while mainnet is live. The operator
# has chosen to accept pool4.imd.fun/docs as a CANDIDATE source. The fingerprint
# still applies unchanged, the cache still nominates nothing, and the channel
# still overrides -- what changes is that a second list of candidates exists and
# that an adoption now says which list it came from.

_MAINNET_HOOK = "0xc6C965Bd164c483e87d0B550671798e9A3602840"
_MAINNET_VAULT = "0x9Efa934D9fAd4AE28c998a40195646b965a97247"
_DISTRIBUTOR = "0x9046739E1535B40EfBe6AB3f45d0024b690eCA30"

_DOCS_HTML = (
    '<table><tr><td>Market hook</td><td><code>'
    + _MAINNET_HOOK.lower() + '</code></td></tr>'
    '<tr><td>sIMD vault</td><td><code>' + _MAINNET_VAULT.lower() + '</code></td></tr>'
    '<tr><td>Reward Distributor</td><td><code>' + _DISTRIBUTOR + '</code></td></tr>'
    '</table>'
)


def _live_answers(addr, token=None):
    return {addr.lower(): {
        "token": "0x" + "0" * 24 + (token or _MAINNET_IMD)[2:].lower(),
        "rewardShareBps": "0x" + format(1500, "064x"),
        "BPS_DENOMINATOR": "0x" + format(10000, "064x"),
        "burnSink": "0x" + "0" * 24 + "e29386719c155b6847ad5a4e97c6674f10ffc750",
        "poolManager": "0x" + "0" * 24 + "000000000004444c5dc75cb358380d2e3de08a90",
    }}


def _code_names(fn):
    """Every identifier a function's CODE references, docstrings excluded.

    ``inspect.getsource`` includes prose, so a docstring that *names* a symbol
    reads as a use of it. That is the bare-token failure in reverse: a
    structural claim ("this function does not touch ADDRESS_RE") checked
    against text passes or fails on wording rather than on behaviour.
    """
    import ast
    import inspect
    import textwrap

    tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    return {
        node.id if isinstance(node, ast.Name) else node.attr
        for node in ast.walk(tree)
        if isinstance(node, (ast.Name, ast.Attribute))
    }


def test_the_real_mainnet_hook_passes_the_gate_unchanged():
    """The 0x2840 work on the real deployment, asserted against the live values.

    ``low14 == 0x2840``, ``getHookPermissions()`` returns exactly the three
    bits, and ``token()`` is the known mainnet IMD. Nothing about the gate
    moved for mainnet.
    """
    assert address_flag_word(_MAINNET_HOOK) == POOL4_REQUIRED_FLAGS == 0x2840
    assert has_pool4_flags(_MAINNET_HOOK) is True
    assert is_hook_shaped(_MAINNET_HOOK) is True

    state, detail = fingerprint_verdict(
        _MAINNET_HOOK, _live_answers(_MAINNET_HOOK)[_MAINNET_HOOK.lower()],
        _MAINNET_IMD)
    assert state == "adopted"
    assert _MAINNET_HOOK in detail

    # The two things that moved are read, not pinned, so neither is in the gate.
    import inspect
    from maxpane_dashboard.data import surf_pool4 as _P
    gate = inspect.getsource(_P.fingerprint_verdict)
    assert "1000" not in gate and "1500" not in gate, "rewardShareBps is read"
    assert "capFloor" not in gate, "capFloor is read"


def test_the_docs_parser_refuses_exactly_what_the_channel_parser_refuses():
    """Same extraction, same refusals -- because it IS the same extraction.

    A docs page is HTML written by somebody else and earns the suspicion
    channel calldata earns. Each row below is a refusal the channel parser
    already makes, re-asserted against raw server-rendered HTML.
    """
    # The happy path first, so the refusals are not vacuous.
    assert docs_candidate_addresses(_DOCS_HTML) == [
        _MAINNET_HOOK, _MAINNET_VAULT, _DISTRIBUTOR]

    refusals = {
        "a bidi-wrapped address that RENDERS as the real hook":
            "<code>0x" + _BIDI_ON + _MAINNET_HOOK[2:] + _BIDI_OFF + "</code>",
        "a 32-byte hash whose first forty nibbles look like an address":
            "<code>0x" + "a" * 64 + "</code>",
        "an address glued to a longer hex run":
            "<code>0x" + _MAINNET_HOOK[2:] + "dead</code>",
        "forty characters of markup after a literal 0x":
            "<code>0x" + "[/x]" * 10 + "</code>",
        "an uppercase 0X prefix":
            "<code>0X" + _MAINNET_HOOK[2:] + "</code>",
        "no addresses at all": "<p>coming soon</p>",
    }
    for case, html in refusals.items():
        assert docs_candidate_addresses(html) == [], case

    # And every refusal is the CHANNEL parser's refusal, byte for byte -- the
    # property that makes drift impossible rather than merely unlikely.
    for case, html in refusals.items():
        assert docs_candidate_addresses(html) == self_post_addresses(
            _ANNOUNCE_LOWERCASE, _ANNOUNCE_LOWERCASE, html,
            _ANNOUNCE_CHECKSUMMED), case
    assert docs_candidate_addresses(_DOCS_HTML) == self_post_addresses(
        _ANNOUNCE_LOWERCASE, _ANNOUNCE_LOWERCASE, _DOCS_HTML,
        _ANNOUNCE_CHECKSUMMED)


def test_the_docs_page_is_read_raw_and_stripping_controls_would_admit_the_bidi_row():
    """S16, at the point the operator's decision made it reachable.

    Stripping control characters before extraction turns
    ``0x`` + U+202E + forty hex digits into a live ``0x2840``-shaped candidate
    whose rendered form is not its real form. The demonstration is inline: the
    same bytes, stripped, DO yield a candidate -- which is why nothing strips
    them.
    """
    hostile = "<code>0x" + _BIDI_ON + _MAINNET_HOOK[2:] + _BIDI_OFF + "</code>"
    assert docs_candidate_addresses(hostile) == []

    stripped = hostile.replace(_BIDI_ON, "").replace(_BIDI_OFF, "")
    assert docs_candidate_addresses(stripped) == [_MAINNET_HOOK], (
        "if the parser normalised first this is what it would have adopted -- "
        "a correctly flagged address that renders as something else"
    )
    assert has_pool4_flags(_MAINNET_HOOK), "and it would have passed the gate"

    # Nor is whitespace collapsed or case folded before extraction.
    assert docs_candidate_addresses("0x" + _MAINNET_HOOK[2:22] + " "
                                    + _MAINNET_HOOK[22:]) == []


def test_docs_candidates_are_deduplicated_and_order_preserving():
    html = _DOCS_HTML + "<p>hook again: " + _MAINNET_HOOK.upper()[:2] \
        + _MAINNET_HOOK[2:] + "</p>"
    got = docs_candidate_addresses(html)
    assert got == [_MAINNET_HOOK, _MAINNET_VAULT, _DISTRIBUTOR]
    assert len(got) == len(set(got))
    for bad in (None, 42, b"0x", []):
        assert docs_candidate_addresses(bad) == []


def test_a_self_post_overrides_the_docs_page_when_both_name_a_hook():
    """Ranked, never merged -- and the channel wins.

    Both sources name a valid, gate-passing hook, and they are DIFFERENT
    addresses. Merging the two candidate lists would let list position decide;
    ranking makes the dev-signed one win every time.
    """
    channel_hook = "0x" + "0" * 36 + "2840"
    rows = [{"from_addr": _ANNOUNCE_LOWERCASE, "to_addr": _ANNOUNCE_LOWERCASE,
             "text": f"pool4 mainnet hook {channel_hook}"}]
    answers = {**_live_answers(channel_hook), **_live_answers(_MAINNET_HOOK)}
    assert channel_hook.lower() != _MAINNET_HOOK.lower()

    verdict, source = ranked_discovery(
        rows, _ANNOUNCE_CHECKSUMMED, _MAINNET_IMD, answers,
        network="MAINNET", docs_text=_DOCS_HTML)
    assert verdict.state == "adopted"
    assert verdict.hook_addr.lower() == channel_hook.lower(), (
        "the dev-signed source wins over the docs page"
    )
    assert source == "self-post"

    # With the self-post gone, the same docs page adopts -- so the override is
    # the channel winning, not the docs source being inert.
    verdict, source = ranked_discovery(
        [], _ANNOUNCE_CHECKSUMMED, _MAINNET_IMD, answers,
        network="MAINNET", docs_text=_DOCS_HTML)
    assert verdict.hook_addr == _MAINNET_HOOK
    assert source == "docs"


def test_the_docs_source_still_faces_the_whole_fingerprint():
    """Candidates only. Nothing about A27 relaxes for the docs page.

    A docs page naming a wrongly-flagged address, an address on a stranger's
    token, or an address that answers nothing is rejected exactly as a
    self-post naming it would be.
    """
    wrong_flags = "0x5aFeBadF1a650000000000000000000000000840"
    wrong_token = "0x5aFeB050e0000000000000000000000000002840"
    silent = "0x5AFEDeADBEef0000000000000000000000002840"
    answers = {
        **_live_answers(wrong_token, token="0x5AFe1DFa1DFa1dFA1dfa1dFA1dFa1dFA1DFA0000"),
        silent.lower(): {k: None for k in
                         ("token", "rewardShareBps", "BPS_DENOMINATOR",
                          "burnSink", "poolManager")},
    }
    for addr, gate in ((wrong_flags, "flags"), (wrong_token, "token"),
                       (silent, "token")):
        verdict, source = ranked_discovery(
            [], _ANNOUNCE_CHECKSUMMED, _MAINNET_IMD, answers,
            network="MAINNET", docs_text=f"<code>{addr}</code>")
        assert verdict.state == "rejected", addr
        assert gate in (verdict.detail or ""), addr
        assert verdict.hook_addr is None, addr
        assert source is None, "a rejection has no adoption to attribute"


def test_a_channel_rejection_does_not_veto_the_docs_page():
    """A stale self-post must not permanently block the other source.

    A self-post naming an address that fails the chain fingerprint means THAT
    address is not a pool4 hook. It says nothing about a different, valid
    address the docs name, and letting one bad post block discovery for ever
    would be a worse failure than the one it prevents.
    """
    bad = "0x5aFeBadF1a650000000000000000000000000840"
    rows = [{"from_addr": _ANNOUNCE_LOWERCASE, "to_addr": _ANNOUNCE_LOWERCASE,
             "text": f"hook {bad}"}]
    verdict, source = ranked_discovery(
        rows, _ANNOUNCE_CHECKSUMMED, _MAINNET_IMD,
        _live_answers(_MAINNET_HOOK), network="MAINNET", docs_text=_DOCS_HTML)
    assert verdict.state == "adopted"
    assert verdict.hook_addr == _MAINNET_HOOK
    assert source == "docs"


def test_when_neither_source_adopts_the_stronger_sources_reason_is_reported():
    """The reader sees the authoritative source's answer, not the weaker one's."""
    bad_channel = "0x5AFeDe17aa110000000000000000000000002844"   # returns-delta
    rows = [{"from_addr": _ANNOUNCE_LOWERCASE, "to_addr": _ANNOUNCE_LOWERCASE,
             "text": f"hook {bad_channel}"}]
    verdict, source = ranked_discovery(
        rows, _ANNOUNCE_CHECKSUMMED, _MAINNET_IMD, {},
        network="MAINNET", docs_text="<code>0x5aFeBadF1a650000000000000000000000000840</code>")
    assert verdict.state == "rejected"
    assert "0x2844" in (verdict.detail or ""), (
        "the channel's candidate is the one reported, not the docs page's"
    )
    assert source is None

    # With nothing hook-shaped in the channel, the docs verdict is what is
    # reported -- otherwise the only source that looked at anything is silent.
    verdict, source = ranked_discovery(
        [{"from_addr": _ANNOUNCE_LOWERCASE, "to_addr": _ANNOUNCE_LOWERCASE,
          "text": "pool4 soon"}],
        _ANNOUNCE_CHECKSUMMED, _MAINNET_IMD, {}, network="MAINNET",
        docs_text="<code>0x5AFeDe17aa110000000000000000000000002844</code>")
    assert verdict.state == "rejected"
    assert "0x2844" in (verdict.detail or "")
    assert source is None


def test_no_docs_page_leaves_the_channel_path_exactly_as_it_was():
    """The widening must be additive: with no docs text, nothing changes."""
    for fixture in ("announce_adversarial_reply_provenance",
                    "announce_adversarial_flag_mismatch",
                    "announce_adversarial_many_candidates",
                    "announce_adversarial_wrong_token"):
        fx = load(fixture)
        answers = ExplodingAnswers(fx.get("eth_call_answers", {}))
        alone = discovery_verdict(rows_of(fx), announce_of(fx), imd_of(fx),
                                  answers, network="MAINNET")
        ranked, source = ranked_discovery(
            rows_of(fx), announce_of(fx), imd_of(fx),
            ExplodingAnswers(fx.get("eth_call_answers", {})),
            network="MAINNET", docs_text=None)
        assert ranked == alone, fixture
        assert source == ("self-post" if alone.state == "adopted" else None)


def test_an_adoption_never_reports_no_source():
    """The absence that must not exist.

    ``None`` keeps its house meaning -- no adoption to attribute -- on every
    non-adopted state. On an ADOPTED state it is not an answer: a renderer
    treating it as "nothing to say" would draw a docs-sourced adoption
    identically to a dev-signed one, undoing by omission the disclosure the
    operator's decision was conditioned on. So an adoption with no recorded
    source resolves to the weakest word instead of the strongest.
    """
    from maxpane_dashboard.data.surf_models import POOL4_DISCOVERY_SOURCES

    assert POOL4_DISCOVERY_SOURCES[0] == "self-post", "strongest first"

    for state in ("not-discovered", "rejected", None, "nonsense"):
        assert discovery_source_word(None, state) is None
        assert discovery_source_word("docs", state) is None

    assert discovery_source_word("self-post", "adopted") == "self-post"
    assert discovery_source_word("docs", "adopted") == "docs"
    for missing in (None, "", "dev", "chain", 42, True):
        assert discovery_source_word(missing, "adopted") == "unattributed", (
            f"{missing!r} must not resolve to the strong answer"
        )
    assert discovery_source_word(None, "adopted") != "self-post"

    # Every source ranked_discovery can emit is in the frozen vocabulary, and
    # never None beside an adoption.
    answers = _live_answers(_MAINNET_HOOK)
    verdict, source = ranked_discovery(
        [], _ANNOUNCE_CHECKSUMMED, _MAINNET_IMD, answers,
        network="MAINNET", docs_text=_DOCS_HTML)
    assert verdict.state == "adopted"
    assert source in POOL4_DISCOVERY_SOURCES
    assert discovery_source_word(source, verdict.state) == "docs"


def test_both_candidate_sources_adjudicate_through_one_body():
    """The docs path cannot acquire a weaker gate by drifting.

    There is one triage, one flag test and one fingerprint call, reached by
    both sources. A second adjudicator is how the to_addr half of the
    provenance gate ended up with no coverage.
    """
    from maxpane_dashboard.data import surf_pool4 as _P

    # AST, not text. A prose mention of ``ADDRESS_RE`` in a docstring is not a
    # use of it, and grepping the source cannot tell the two apart -- which is
    # the bare-token-in-a-docstring failure this branch has now found five
    # times, pointed the other way.
    for fn in (_P.discovery_verdict, _P.ranked_discovery):
        assert "adjudicate_candidates" in _code_names(fn), fn.__name__
    for fn in (_P.docs_candidate_addresses, _P.self_post_addresses):
        assert "ADDRESS_RE" not in _code_names(fn), fn.__name__
        assert "extract_addresses" in _code_names(fn), fn.__name__
    assert "ADDRESS_RE" in _code_names(_P.extract_addresses), (
        "one caller, and this is it -- if none used it the check above would "
        "be vacuous"
    )

    # Behaviourally: the same address adjudicates identically from either list.
    addr = _MAINNET_HOOK
    answers = _live_answers(addr)
    from_docs = _P.adjudicate_candidates([addr], _MAINNET_IMD, answers,
                                         "MAINNET", None, origin="docs")
    from_chan = _P.adjudicate_candidates([addr], _MAINNET_IMD, answers,
                                         "MAINNET", None, origin="self-post")
    assert from_docs.state == from_chan.state == "adopted"
    assert from_docs.hook_addr == from_chan.hook_addr
