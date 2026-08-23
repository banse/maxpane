"""Tests for ``maxpane_dashboard.analytics.surf_signals``.

Zero network, zero wall clock.  Every clock is injected: ``build_signals``
takes ``now_ts`` and nothing in the module under test may call ``time.time()``
(``test_module_is_pure`` enforces that mechanically).  Every payload below is
lifted from ``tests/fixtures/surf/`` — the real 2026-08-08 captures — not
invented; the two synthetic values (a hooked v4 ``Initialize`` row) are marked
SYNTHETIC because the event has not happened on chain yet.

The one committed file this WP owns lives in ``fixtures/surf/signals/``.  The
fixtures *root* holds directories only — WP0.6's
``test_the_fixtures_root_holds_directories_only`` (in
``tests/data/test_surf_captures.py``) fails on any loose file, whatever is in
it — so a WP2 file there would turn red a suite WP2 does not own.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from maxpane_dashboard.analytics import surf_launchpad as L
from maxpane_dashboard.analytics import surf_signals as sig

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "surf"


@pytest.fixture(scope="module")
def calldata() -> dict:
    """The seven-tx slice of the announce channel (WP2.1 generator).

    The file carries WP2's own ``{"_meta": …, "response": …}`` provenance
    wrapper — WP0 defines no such convention, it pins its captures by name —
    and is checked for it here rather than in a test of its own: the assertion
    has to run before any decoder test can use the payload anyway, and keeping
    it in the fixture leaves every observed test count in this plan unchanged.
    """
    doc = json.loads(
        (_FIXTURES / "signals" / "announce_calldata.json").read_text(encoding="utf-8")
    )
    meta = doc["_meta"]
    assert meta["keyless"] is True and meta["captured_at"] and meta["source"]
    return doc["response"]


# --- decode_utf8_calldata ---------------------------------------------------
#
# The dev's own monitoring spec (channel nonce 2) is "decode the transaction
# input as UTF-8 text when possible".  "When possible" is the whole job: one of
# the 21 channel txs is an ABI-encoded register() call and must decode to None,
# not to mojibake.


def test_decodes_the_shortest_real_post(calldata: dict):
    """nonce 0, 2026-05-16: the four-byte post that started the channel."""
    assert calldata["self_soon"]["raw_input"] == "0x736f6f6e"
    assert sig.decode_utf8_calldata(calldata["self_soon"]["raw_input"]) == "soon"


def test_decodes_the_lp_add_post_byte_for_byte(calldata: dict):
    """nonce 13 — the post the whole BRIDGE STAGE replay ends on."""
    assert sig.decode_utf8_calldata(calldata["self_lp_add"]["raw_input"]) == (
        "I moved 33 eth to the LP on mainnet https://etherscan.io/tx/"
        "0x90a0f8e2b039e8d86d1b10e33e61e12d13728444e0a9e5ac258051cccb64d669. "
        "Hopefully in the coming days will be able to share more what been "
        "working on, as always 0 promises."
    )


def test_decodes_typographic_punctuation_and_newlines_unchanged(calldata: dict):
    """nonce 8: two U+2019 apostrophes, two U+2014 em-dashes, two newlines.

    The decoder returns raw text.  Escaping is the *widget's* job
    (``widgets/markup_safety.safe_markup``); a decoder that pre-escaped would
    double-escape downstream and corrupt the message.
    """
    text = sig.decode_utf8_calldata(calldata["self_hook_emdash"]["raw_input"])
    assert text == (
        "The hook will be highly experimental. I’ll\n"
        "  announce it before moving the LP. I’m also considering limiting "
        "trading to NFT holders for the first few hours—so the risks\n"
        "  are clear—then opening it to everyone. Thoughts?"
    )
    assert "’" in text and "—" in text and "\n" in text


def test_abi_encoded_register_call_is_not_a_message(calldata: dict):
    """nonce 4: ``register(string)`` — selector 0xf2c298be, invalid UTF-8.

    This is the one channel tx that is a contract call rather than a post.  A
    decoder that fell back to ``errors="replace"`` would put a wall of U+FFFD
    into the feed and label a contract call a message.
    """
    raw = calldata["action_register"]["raw_input"]
    assert raw.startswith("0xf2c298be")
    assert sig.decode_utf8_calldata(raw) is None


def test_invalid_utf8_with_no_control_bytes_is_none():
    """Isolates the ``UnicodeDecodeError`` branch from the control-char guard.

    The real ``register()`` fixture (nonce 4) is ABI-encoded, so its
    zero-padding is full of NUL bytes — the control-character guard rejects it
    on its own, independent of the UTF-8 decode step, so that test cannot tell
    which guard actually fired.  ``0xc328`` has none of that: ``0xc3`` is a
    valid two-byte UTF-8 lead byte, but ``0x28`` (``"("``) is not a valid
    continuation byte, so decoding raises ``UnicodeDecodeError`` and nothing
    else in the function can catch it.  A regression to
    ``errors="replace"`` would pass every other test in this file and still
    slip U+FFFD into the feed; this is the one test built to catch exactly
    that.
    """
    raw = bytes.fromhex("c328")
    with pytest.raises(UnicodeDecodeError):
        raw.decode("utf-8")
    assert sig.decode_utf8_calldata("0xc328") is None


def test_empty_calldata_is_not_a_message(calldata: dict):
    """The 0.054 ETH funding tx from surfsurf.eth carries no calldata at all."""
    assert calldata["fund_ownership_proof"]["raw_input"] == "0x"
    assert sig.decode_utf8_calldata("0x") is None
    assert sig.decode_utf8_calldata("") is None
    assert sig.decode_utf8_calldata("   ") is None


def test_trailing_whitespace_is_stripped(calldata: dict):
    """The begging reply ends with a space; the feed must not carry it."""
    assert sig.decode_utf8_calldata(calldata["reply_begging"]["raw_input"]) == (
        "Gm Adam. Help me. Donate 10 ETH, to me, pls. Thanks you."
    )


def test_crlf_is_normalised_to_lf():
    """A CRLF-terminated line decodes with the ``\\r`` dropped, not kept.

    ``0x6c696e65206f6e650d0a6c696e652074776f`` is ``"line one\\r\\nline
    two"`` UTF-8-encoded.  The feed renders one message per row, so a stray
    ``\\r`` must not survive into the widget layer.
    """
    text = sig.decode_utf8_calldata("0x6c696e65206f6e650d0a6c696e652074776f")
    assert text == "line one\nline two"
    assert "\r" not in text


@pytest.mark.parametrize(
    "bad",
    [
        "0xabc",        # odd number of nibbles
        "0xzz",         # not hex
        "not hex",
        "0x610062",     # "a\x00b" -- valid UTF-8, but NUL means ABI padding
        None,
        12345,
        b"0x736f6f6e",
    ],
)
def test_unparseable_calldata_is_none(bad):
    assert sig.decode_utf8_calldata(bad) is None


def test_markup_hostile_text_survives_verbatim():
    """``[/x]`` is returned as-is: escaping belongs to the widget layer.

    Token symbols and channel replies are attacker-controlled (CLAUDE.md), and
    the channel is permissionless by design (PRD §6.4) — so this input is
    realistic, not hypothetical.
    """
    assert sig.decode_utf8_calldata("0x5b2f785d") == "[/x]"
    assert sig.decode_utf8_calldata("0x5b626c696e6b5d") == "[blink]"


# --- classify_channel_tx ----------------------------------------------------
#
# The dev's spec: from == to == channel is a post; from == channel to anything
# else is an onchain action; from == a dev wallet is funding; everything else
# is a community reply.  All four kinds exist in the 21 captured txs.


def _kind(row: dict) -> str:
    return sig.classify_channel_tx(
        row["from"], row["to"], int(row["value"]), row["raw_input"]
    )


def test_self_post_is_self(calldata: dict):
    """nonce 13: from == to == 0x200E710a…, value 0."""
    row = calldata["self_lp_add"]
    assert row["from"].lower() == row["to"].lower()
    assert _kind(row) == "self"


def test_outbound_contract_call_is_action(calldata: dict):
    """nonce 4: the channel EOA calling the ERC-8004 registry.

    This is the exact shape the NEW DEPLOY detector watches for (PRD §3 #4).
    """
    row = calldata["action_register"]
    assert row["to"].lower() == "0x8004a169fb4a3325136eb29fa0ceb6d2e539a432"
    assert _kind(row) == "action"


def test_dev_wallet_value_transfer_is_fund(calldata: dict):
    """0.054 ETH from surfsurf.eth — the tx that proves he owns the channel."""
    row = calldata["fund_ownership_proof"]
    assert int(row["value"]) == 54_000_000_000_000_000
    assert _kind(row) == "fund"


@pytest.mark.parametrize("name", ["reply_pasta", "reply_begging"])
def test_strangers_are_replies_whatever_they_send(calldata: dict, name: str):
    """Both real replies: one value-0, one carrying 1e13 wei of bait.

    Value never promotes a stranger to ``fund``: ``fund`` is about *who*, and
    treating a funded-looking reply as the dev's own tx is how a spoofed feed
    row gets rendered as trusted (PRD §6.4/§6.5).
    """
    assert _kind(calldata[name]) == "reply"


def test_dev_wallet_message_is_not_mislabelled_as_funding():
    """A dev-wallet tx that carries a readable message is a reply, not funding.

    ``fund`` means value moved or empty calldata.  The literal spec says
    "from == dev wallet -> funding", but the feed renders these kinds as words
    next to a message body, and labelling a readable message "fund" would be a
    lie on screen.
    """
    from maxpane_dashboard.data.surf_addresses import ANNOUNCE, DEV_WALLET

    assert sig.classify_channel_tx(DEV_WALLET, ANNOUNCE, 0, "0x736f6f6e") == "reply"
    assert sig.classify_channel_tx(DEV_WALLET, ANNOUNCE, 0, "0x") == "fund"


def test_case_and_missing_addresses_never_raise():
    """RPC gives lowercase, Blockscout gives checksummed; both must classify.

    A contract-creation tx has ``to = None``; from the channel that is an
    action, and from a stranger it is not our business but must still return a
    kind rather than raising inside a render path.
    """
    from maxpane_dashboard.data.surf_addresses import ANNOUNCE

    assert sig.classify_channel_tx(ANNOUNCE.lower(), ANNOUNCE.upper(), 0, "0x736f6f6e") == "self"
    assert sig.classify_channel_tx(ANNOUNCE, None, 0, "0x") == "action"
    assert sig.classify_channel_tx(None, None, None, None) == "reply"

    # The vocabulary is WP0's, re-exported — *identity*, not equality.  A second
    # literal here would be a closed vocabulary with two green tests, and a fifth
    # kind added to one copy would pass both suites while the classifier and the
    # models disagreed.  WP0's test_channel_tx_kinds_are_the_four_frozen_strings
    # owns the contents; this line owns the fact that there is only one object.
    from maxpane_dashboard.data import surf_models

    assert sig.CHANNEL_KINDS is surf_models.CHANNEL_KINDS


# --- parity_pct and detail formatting ---------------------------------------
#
# IMD is FP bridged 1:1 (FP locks on Base, IMD mints on mainnet), so the two
# prices should track and the spread is a real arbitrage/health number.  It is
# computed every refresh and never hardcoded: the repo has watched a documented
# "constant" drift three days running (CLAUDE.md rule 4).

# dexscreener_imd.json / dexscreener_fp.json, captured 2026-08-08.
IMD_PRICE_USD = 0.7074
FP_PRICE_USD = 0.7274


def test_parity_uses_the_captured_prices():
    assert sig.parity_pct(IMD_PRICE_USD, FP_PRICE_USD) == pytest.approx(-2.7495188, abs=1e-6)


def test_parity_is_signed_both_ways():
    assert sig.parity_pct(1.10, 1.00) == pytest.approx(10.0)
    assert sig.parity_pct(1.00, 1.00) == pytest.approx(0.0)


@pytest.mark.parametrize(
    "imd,fp",
    [(None, 0.7274), (0.7074, None), (None, None), (0.7074, 0.0), (0.7074, -1.0), ("x", 1.0)],
)
def test_parity_is_none_when_a_price_is_missing_or_impossible(imd, fp):
    """A dead market feed is ``None``, never 0% — 0% would read as 'at parity'."""
    assert sig.parity_pct(imd, fp) is None


@pytest.mark.parametrize(
    "imd,fp",
    [
        (float("inf"), 0.7274),
        (0.7074, float("inf")),
        (float("nan"), 0.7274),
        (0.7074, float("nan")),
        ("1e400", 0.7274),
    ],
)
def test_parity_rejects_non_finite_or_overflowing_prices(imd, fp):
    """inf/nan/an overflowing numeric string must never surface as a computed
    spread (fix round 1).  Third-party keyless market payloads are not under
    our control, and ``float("1e400")`` overflows to ``inf`` without raising,
    so it would otherwise sail through as a "valid" price.  ``inf%``/``nan%``
    on screen would read as a genuine depeg rather than as missing data --
    the same class of lie a fabricated spread would be.
    """
    assert sig.parity_pct(imd, fp) is None


def test_parity_rejects_a_result_that_overflows_even_with_finite_inputs():
    """Two finite, legitimate-looking extremes can still divide out to inf.

    Neither input alone is invalid, so the inputs pass the finiteness guard
    in ``_as_float``; the computed ratio itself must be checked too.
    """
    assert sig.parity_pct(1e308, 1e-308) is None


def test_amounts_render_without_inventing_precision():
    assert sig._fmt_amount(114_366.899256) == "114,367"
    assert sig._fmt_amount(15_745.0) == "15,745"
    assert sig._fmt_amount(10_000.0) == "10,000"
    assert sig._fmt_amount(0.5) == "0.50"


def test_truncate_flattens_newlines_and_marks_the_cut(calldata: dict):
    """A feed detail is one line: the LP post's two sentences become 48 chars."""
    text = sig.decode_utf8_calldata(calldata["self_lp_add"]["raw_input"])
    assert sig._truncate(text) == "I moved 33 eth to the LP on mainnet https://eth…"
    assert len(sig._truncate(text)) == sig.DETAIL_LIMIT
    assert sig._truncate("soon") == "soon"
    assert sig._truncate("a\nb\n  c") == "a b c"


def test_short_addr_matches_the_prd_poisoning_format():
    """0x + first 8 + … + last 6 (PRD §4) — enough to be checked, never trusted."""
    assert sig._short_addr("0xd6C6d48e8ff38DD7F242E34442FBdaA10eCF7A44") == "0xd6C6d48e…CF7A44"
    assert sig._short_addr("0x8004A169FB4a3325136EB29fA0ceB6D2e539a432") == "0x8004A169…39a432"
    assert sig._short_addr("0x00") == "0x00"


# ---------------------------------------------------------------------------
# build_signals — the six detectors
#
# Every payload below is the real 2026-08-07 sequence out of
# tests/fixtures/surf/captures/.  NOW is 2026-08-07T05:20:00Z, 53 minutes after
# the LP-add post, so all of that day's events are inside the 24 h FIRED TTL.
# ---------------------------------------------------------------------------

NOW = 1_786_080_000.0        # 2026-08-07T05:20:00Z

# ops_eth_token_transfers.json — the two OFT bridge-in mints to frenpet.eth.
MINT_1 = {
    "ts": 1_786_076_339.0,
    "tx_hash": "0x17084b1bfc998a457416c1ba9689f50ca04efc6e160b7e28d4c75dc89bcea85c",
    "amount": 10_000.0,
    "to_label": "frenpet.eth",
}
MINT_2 = {
    "ts": 1_786_076_495.0,
    "tx_hash": "0xc7acbcc0b164a0eaecb1220484e97d410bb159ca42d3c61165a26fe03c1d0a01",
    "amount": 114_366.899256,
    "to_label": "frenpet.eth",
}
# ops_eth_txs.json / ops_eth_token_transfers.json — IMD -> BurnExecutor.
BURN_0731 = {
    "ts": 1_785_464_459.0,
    "tx_hash": "0xa25b08cfc4b2ca2ada16374001e377961514b50985d887ffcfc60a5194e5cd5c",
    "amount": 31_064.0,
}
BURN_0805 = {
    "ts": 1_785_903_035.0,
    "tx_hash": "0x11bf8d3e3fd83538faa906521c5f5f0592f6b6117c3d4967c97f05b3ae753a6e",
    "amount": 15_745.0,
}
# announce_eth_txs.json nonce 4 — the ERC-8004 registration, the exact shape
# NEW DEPLOY watches for.
REGISTER_ACTION = {
    "ts": 1_779_469_691.0,
    "tx_hash": "0xa4ce159e5100eba90d231efb103b2c727a25660bacf9a2f02de569a4a1d1c1c2",
    "kind": "action",
    "label": "register()",
    "wallet_label": "announce",
}
# The same call replayed into the current poll window.  The matrix pins one
# clock, and NEW DEPLOY's FIRED row is about an event that just happened; the
# real 2026-05-22 timestamp is exercised by
# ``test_an_event_older_than_the_ttl_renders_as_history_not_news``.
FRESH_ACTION = {**REGISTER_ACTION, "ts": NOW - 240.0}
# announce_eth_txs.json nonce 13.
LP_POST_TS = 1_786_076_831.0
LP_POST_TEXT = (
    "I moved 33 eth to the LP on mainnet https://etherscan.io/tx/"
    "0x90a0f8e2b039e8d86d1b10e33e61e12d13728444e0a9e5ac258051cccb64d669. "
    "Hopefully in the coming days will be able to share more what been "
    "working on, as always 0 promises."
)
LP_POST_DETAIL = '#14 "I moved 33 eth to the LP on mainnet https://eth…"'

# SYNTHETIC: a hooked IMD v4 pool -- LP MIGRATION's old flagship event, now
# spent (2026-08-17).  Kept only for test_a_hooked_v4_pool_no_longer_moves_
# this_row, which proves the now-removed branch stays removed.
HOOKED_POOL = {
    "ts": 1_786_079_000.0,
    "tx_hash": "0x" + "a5" * 32,
    "hooks": "0xd6C6d48e8ff38DD7F242E34442FBdaA10eCF7A44",
}

# Supply before the 2026-08-07 bridge-in: the live 2,376,731.868679 from
# imd_token.json minus the two mints.
SUPPLY_BEFORE = 2_252_364.969423
SUPPLY_AFTER_MINTS = 2_376_731.868679
LP_LIQUIDITY_BEFORE = 1_000_000_000_000
LP_LIQUIDITY_AFTER_ADD = 1_330_000_000_000     # +33.0%

# --- v4-launchpad fixtures (Task 7) -----------------------------------------
#
# CLAUDE.md: "37 decoy pools mean 'which pool is this' is a question with a
# wrong answer" -- 36 is the day-before baseline, 37 the live count.
DECOY_POOL_COUNT_BEFORE = 36
DECOY_POOL_COUNT_AFTER = 37
DECOY_NEWEST_FEE_BPS = 8_000  # 80% -- a predatory fee tier meant to look rich

# HOT COIN: five quiet coins plus one that clears the relative bar.  Reused
# verbatim between the escaped-detail test and the matrix's FIRED row so
# there is exactly one "hostile ticker crosses the bar" fixture in the file.
HOT_COIN_COUNTS_THIN = {"a": 50, "b": 1}                    # 2 active < HOT_MIN_ACTIVE
HOT_COIN_COUNTS_FIRED = {**{f"c{i}": 1 for i in range(5)}, "[/x]": 99}
HOT_COIN_COUNTS_WATCH = {"a": 2, "b": 2, "c": 2, "d": 2, "e": 4}


def _baseline(**overrides) -> dict:
    """The persisted state as of 2026-08-06 — the day before the LP add."""
    base = {
        "announce_nonce": 13,
        "channel_tx_count": 20,
        "lp_liquidity": LP_LIQUIDITY_BEFORE,
        "ops_nonce": 36,
        "dev_nonce": 2350,
        "gate_open": False,
        "identities_written": 1,
        "imd_supply": SUPPLY_BEFORE,
        "bridge_tx": "",
        "bridge_ts": 0.0,
        "deploy_tx": "",
        "deploy_ts": 0.0,
        "v4_tx": "",
        "v4_ts": 0.0,
        "burn_tx": BURN_0731["tx_hash"],
        "burn_ts": BURN_0731["ts"],
        "decoy_pool_count": DECOY_POOL_COUNT_BEFORE,
        # fix round 1: BURN READY's own edge baseline. False -- "was not
        # ready" -- is the quiet, day-before default; a True->True quiet
        # refresh is exercised explicitly where it matters.
        "burn_ready": False,
        "fired": {},
    }
    base.update(overrides)
    return base


def _readings(**overrides) -> dict:
    """A quiet refresh: everything read successfully, nothing moved."""
    read = {
        "announce_nonce": 13,
        "channel_tx_count": 20,
        "announce_last_text": None,
        "announce_last_ts": None,
        "lp_liquidity": LP_LIQUIDITY_BEFORE,
        "ops_nonce": 36,
        "dev_nonce": 2350,
        "v4_hook_pools": [],
        "gate_open": False,
        "identities_written": 1,
        "deploy_events": [],
        "bridge_mints": [],
        "burn_transfers": [],
        "imd_supply": SUPPLY_BEFORE,
        # -- v4-launchpad additions (Task 7) --
        "decoy_pool_count": DECOY_POOL_COUNT_BEFORE,
        "decoy_newest_fee_bps": None,
        "burn_ready": False,
        "burn_accrued": 0.0,
        "launchpad_swaps_by_coin": {},
        # Final fix wave (C1): the distribution's own read time. A quiet
        # refresh reads it *now*; a row that wants the stale branch overrides
        # this, which is the point -- the slot it comes from never expires.
        "launchpad_swaps_ts": NOW,
    }
    read.update(overrides)
    return read


def _sig(name: str, baselines: dict, readings: dict, now: float = NOW) -> tuple:
    """``(state, detail, age_s)`` for one detector."""
    out, _ = sig.build_signals(baselines, readings, now)
    return (
        out[f"sig_{name}_state"],
        out[f"sig_{name}_detail"],
        out[f"sig_{name}_age_s"],
    )


def test_output_keys_are_exactly_the_prd_contract():
    out, _ = sig.build_signals(_baseline(), _readings(), NOW)
    assert set(out) == set(sig.SIGNAL_OUTPUT_KEYS)
    # WP2.4 landed NEW POST; WP2.5 appended LP MIGRATION; WP2.6 appended GATE
    # OPEN and NEW DEPLOY; WP2.7 appended BRIDGE STAGE and BURN, completing
    # the original six-name PRD §3 roster.  Task 7 (v4 launchpad) appends
    # DECOY POOL, BURN READY and HOT COIN, and LP MIGRATION -- spent, its
    # migration finished -- is re-aimed rather than replaced, so ``lp`` stays
    # the payload prefix.
    assert sig.SIGNAL_NAMES == (
        "post", "lp", "gate", "deploy", "bridge", "burn", "decoy", "burnready", "hot",
    )
    assert len(sig.SIGNAL_OUTPUT_KEYS) == 27


def test_signal_output_keys_grew_to_twenty_seven():
    """SIGNAL_OUTPUT_KEYS is DERIVED from _DETECTORS, so registering the three
    new detectors is what publishes their keys -- there is no second list to
    keep in step inside this module."""
    assert len(sig.SIGNAL_NAMES) == 9
    assert len(sig.SIGNAL_OUTPUT_KEYS) == 27


def test_quiet_refresh_leaves_post_ok():
    assert _sig("post", _baseline(), _readings()) == (
        "ok", "nonce 13 · no new post", None
    )


def test_new_post_fires_with_the_decoded_body():
    """The flagship: nonce 13 -> 14 with the LP-add message."""
    state, detail, age = _sig(
        "post",
        _baseline(),
        _readings(
            announce_nonce=14,
            channel_tx_count=21,
            announce_last_text=LP_POST_TEXT,
            announce_last_ts=LP_POST_TS,
        ),
    )
    assert state == "fired"
    assert detail == LP_POST_DETAIL
    assert age == pytest.approx(NOW - LP_POST_TS)


def test_a_reply_is_a_watch_not_a_post():
    """Replies raise the Blockscout tx count without moving the nonce.

    Anyone can write to the channel; a reply is worth surfacing but it is not
    the dev speaking (PRD §6.4).
    """
    assert _sig("post", _baseline(), _readings(channel_tx_count=21)) == (
        "watch", "reply on channel · 21 txs", None
    )


def test_first_ever_read_seeds_the_baseline_and_never_fires():
    """An empty cache must not report the whole history as brand-new.

    This is the false-first-sweep regression that shipped once already
    (2b0b43c, 'stop the first sweep of every launch reporting a false
    mismatch').
    """
    state, detail, age = _sig("post", {}, _readings(announce_nonce=14))
    assert state == "ok"
    assert detail == "nonce 14 · baseline set"
    assert age is None


def test_channel_outage_is_none_not_ok():
    assert _sig(
        "post", _baseline(), _readings(announce_nonce=None, channel_tx_count=None)
    ) == (None, "channel unavailable", None)


def test_baselines_advance_only_on_successful_reads():
    _, advanced = sig.build_signals(
        _baseline(),
        _readings(announce_nonce=None, lp_liquidity=None, imd_supply=None, gate_open=None),
        NOW,
    )
    assert advanced["announce_nonce"] == 13
    assert advanced["lp_liquidity"] == LP_LIQUIDITY_BEFORE
    assert advanced["imd_supply"] == SUPPLY_BEFORE
    assert advanced["gate_open"] is False


def test_a_lagging_replica_cannot_drag_a_nonce_baseline_down():
    """Nonces only go up.

    A replica that answers 13 after we recorded 14 would otherwise reset the
    baseline, and the next correct answer (14) would re-fire NEW POST with a
    message the user already read.
    """
    _, advanced = sig.build_signals(
        _baseline(announce_nonce=14), _readings(announce_nonce=13), NOW
    )
    assert advanced["announce_nonce"] == 14
    state, _, _ = _sig("post", _baseline(announce_nonce=14), _readings(announce_nonce=13))
    assert state == "ok"


def test_fired_persists_for_24h_then_relaxes_with_a_last_detail():
    """PRD §3: FIRED holds for FIRED_TTL_S with its age, then relaxes."""
    fired_at = NOW - 3600.0
    base = _baseline(fired={"post": {"ts": fired_at, "detail": LP_POST_DETAIL}})
    assert _sig("post", base, _readings()) == ("fired", LP_POST_DETAIL, 3600.0)

    # Exactly at the TTL it is no longer FIRED (strict <).
    edge = _baseline(fired={"post": {"ts": NOW - sig.FIRED_TTL_S, "detail": LP_POST_DETAIL}})
    state, detail, age = _sig("post", edge, _readings())
    assert state == "ok"
    assert detail == f"nonce 13 · no new post · last: {LP_POST_DETAIL}"
    assert age == pytest.approx(float(sig.FIRED_TTL_S))


def test_fired_events_survive_a_restart_through_the_returned_baselines():
    """The advanced baselines carry the fired store back to the cache."""
    _, advanced = sig.build_signals(
        _baseline(),
        _readings(announce_nonce=14, announce_last_text="soon", announce_last_ts=LP_POST_TS),
        NOW,
    )
    assert advanced["fired"]["post"]["ts"] == LP_POST_TS
    assert advanced["fired"]["post"]["detail"] == '#14 "soon"'
    # Replayed from the persisted state with no new event: still FIRED.
    assert _sig("post", advanced, _readings(announce_nonce=14))[0] == "fired"
    assert sig._short_addr(None) == ""


# --- 2. LP MOVE --------------------------------------------------------------
#
# LP MIGRATION fired on 2026-08-17 (the ops wallet withdrew and burned v3
# position #1167726) and the migration it watched for is finished, so this
# row is re-aimed at the v4 position rather than re-armed for a second
# launch: the payload prefix stays ``lp``, only the meaning and wording move.
# The escalation itself survives unchanged from the old migration precursor:
# liquidity down fires, liquidity up or any frenpet.eth nonce move watches.


def test_lp_move_watches_the_v4_position_not_the_migration():
    """LP MIGRATION is spent -- it fired, and the migration is finished."""
    state, detail, _age = _sig("lp", {"lp_liquidity": 100}, {"lp_liquidity": 90})
    assert state == "fired"
    assert "v4" in detail or "position" in detail


def test_liquidity_holding_is_ok():
    assert _sig("lp", _baseline(), _readings()) == ("ok", "v4 position holds", None)


def test_liquidity_decrease_fires():
    assert _sig("lp", _baseline(), _readings(lp_liquidity=677_000_000_000)) == (
        "fired", "v4 position OUT -32.3%", 0.0
    )


def test_liquidity_increase_is_a_watch_not_a_fire():
    """The 2026-08-07 add: 33 ETH *into* the pool, not out of it."""
    assert _sig("lp", _baseline(), _readings(lp_liquidity=LP_LIQUIDITY_AFTER_ADD)) == (
        "watch", "v4 position +33.0%", None
    )


def test_any_frenpet_eth_activity_is_a_watch():
    """The ops wallet holds the v4 LP NFT(s); any nonce move is signal."""
    assert _sig("lp", _baseline(), _readings(ops_nonce=37)) == (
        "watch", "frenpet.eth active · nonce 37", None
    )


def test_a_hooked_v4_pool_no_longer_moves_this_row():
    """The migration this reading used to watch for already happened.

    Before Task 7 a hooked ``Initialize`` was the flagship, highest-priority
    branch of this detector (``test_hooked_v4_initialize_fires_as_the_launch``,
    now removed). ``v4_hook_pools`` is still wired by ``surf_manager.py`` (a
    file this task does not own) but this detector no longer consults it --
    a hooked row must not move this row at all, whatever the reading says.
    """
    state, detail, _ = _sig("lp", _baseline(), _readings(v4_hook_pools=[HOOKED_POOL]))
    assert state == "ok"
    assert detail == "v4 position holds"
    _, advanced = sig.build_signals(_baseline(), _readings(v4_hook_pools=[HOOKED_POOL]), NOW)
    # The v4_tx/v4_ts/v4_seq baseline still advances (BASELINE_EVENT_KEYS is
    # untouched -- surf_manager.py still produces the reading) but nothing
    # reads it back any more, so this is bookkeeping, not behaviour.
    assert advanced["v4_tx"] == HOOKED_POOL["tx_hash"]


def test_lp_outage_is_none():
    assert _sig(
        "lp",
        _baseline(),
        _readings(lp_liquidity=None, ops_nonce=None, v4_hook_pools=None),
    ) == (None, "v4 position unavailable", None)


# --- 3. GATE OPEN -----------------------------------------------------------
#
# identityAllowed() has been false since 2026-05-14 with 1/2000 written.  The
# moment "the agent" flips it, any IDMD holder can write an identity.
#
# The written count is rendered without a "/2000" denominator on purpose: the
# cap is a documented number and the hero widget reads it live (CLAUDE.md
# rule 4).


def test_closed_gate_is_ok_and_says_so():
    assert _sig("gate", _baseline(), _readings()) == ("ok", "closed · 1 written", None)


def test_gate_flip_fires():
    assert _sig("gate", _baseline(), _readings(gate_open=True)) == (
        "fired", "GATE OPEN · 1 written", 0.0
    )


def test_writes_without_a_flip_we_saw_are_a_watch():
    """The gate opened and closed between two polls — the write proves it."""
    assert _sig("gate", _baseline(), _readings(identities_written=2)) == (
        "watch", "1→2 written · gate closed", None
    )


def test_an_already_open_gate_on_first_read_does_not_fire():
    state, detail, age = _sig("gate", {}, _readings(gate_open=True))
    assert state == "ok"
    assert detail == "OPEN · 1 written"
    assert age is None


def test_gate_outage_is_none():
    assert _sig(
        "gate", _baseline(), _readings(gate_open=None, identities_written=None)
    ) == (None, "gate unavailable", None)


# --- 4. NEW DEPLOY ----------------------------------------------------------
#
# The ERC-8004 registration at channel nonce 4 was exactly this shape: an
# outbound contract call from the announce EOA.  Contract creations by
# surfsurf.eth are the other half.


def test_no_new_contract_is_ok():
    assert _sig("deploy", _baseline(), _readings()) == ("ok", "no new contract", None)


def test_an_outbound_contract_call_fires():
    state, detail, age = _sig("deploy", _baseline(), _readings(deploy_events=[FRESH_ACTION]))
    assert state == "fired"
    assert detail == "action register() · announce"
    assert age == pytest.approx(240.0)


def test_an_event_older_than_the_ttl_renders_as_history_not_news():
    """The real register() call is from 2026-05-22 — detected late, it is not news.

    A cold cache with a wide log window would otherwise shout FIRED about a
    76-day-old transaction: the false-first-sweep bug wearing a different hat.
    The event is still recorded, so the row says what it was.
    """
    state, detail, age = _sig("deploy", _baseline(), _readings(deploy_events=[REGISTER_ACTION]))
    assert state == "ok"
    assert detail == "last: action register() · announce"
    assert age == pytest.approx(NOW - REGISTER_ACTION["ts"])


def test_a_contract_creation_fires():
    event = {
        "ts": NOW - 120.0,
        "tx_hash": "0x" + "c0" * 32,
        "kind": "deploy",
        "label": "0x8004A169FB4a3325136EB29fA0ceB6D2e539a432",
        "wallet_label": "surfsurf.eth",
    }
    state, detail, age = _sig("deploy", _baseline(), _readings(deploy_events=[event]))
    assert state == "fired"
    assert detail == "new contract 0x8004A169…39a432 · surfsurf.eth"
    assert age == pytest.approx(120.0)


def test_dev_nonce_movement_alone_is_a_watch():
    assert _sig("deploy", _baseline(), _readings(dev_nonce=2351)) == (
        "watch", "surfsurf.eth nonce 2350→2351", None
    )


def test_deploy_outage_is_none():
    assert _sig(
        "deploy", _baseline(), _readings(deploy_events=None, dev_nonce=None)
    ) == (None, "dev activity unavailable", None)


# --- fix round 1: _advance must persist gate_open as strictly as _detect_gate
# reads it ---------------------------------------------------------------
#
# Regression: _advance's only guard used to be "reading is not None", so a
# malformed reading -- an int 0, which is neither a bool nor None -- sailed
# past _detect_gate's own isinstance guard (which correctly reports "gate
# unavailable" and refuses to compare it) and was persisted verbatim,
# corrupting the baseline's type. The following cycle's genuine False->True
# flip then read that corrupted, non-bool baseline as unset, silently
# re-seeded, and never fired: one bad read permanently disarmed the one
# transition GATE OPEN exists to catch.


def test_a_non_bool_gate_reading_never_corrupts_the_persisted_baseline():
    base = _baseline(gate_open=False)
    _, advanced = sig.build_signals(base, _readings(gate_open=0), NOW)
    # The garbage int must not reach the baseline -- the prior valid bool
    # (False) survives untouched, exactly as an outright None reading would
    # leave it.
    assert advanced["gate_open"] is False

    # The following cycle's real flip must still be seen as a flip, and fire.
    state, detail, age = _sig("gate", advanced, _readings(gate_open=True))
    assert state == "fired"
    assert detail == "GATE OPEN · 1 written"
    assert age == 0.0


def test_a_legitimate_false_is_still_persisted():
    """The hardening must not stop a genuinely valid False from persisting."""
    _, advanced = sig.build_signals(
        _baseline(gate_open=True), _readings(gate_open=False), NOW
    )
    assert advanced["gate_open"] is False


# --- 5. BRIDGE STAGE --------------------------------------------------------
#
# The earliest link in the 2026-08-07 chain: mint 04:18:59 -> mint 04:21:35 ->
# approve 04:22:23 -> add 04:23:23 -> announce 04:27:11.  Staging preceded the
# add by 12 minutes (PRD §3 #5).


def test_no_mints_in_window_is_ok():
    assert _sig("bridge", _baseline(), _readings()) == ("ok", "no mints in window", None)


def test_an_oft_mint_to_a_dev_wallet_fires_on_the_newest_row():
    state, detail, age = _sig("bridge", _baseline(), _readings(bridge_mints=[MINT_1, MINT_2]))
    assert state == "fired"
    assert detail == "mint 114,367 IMD → frenpet.eth"
    assert age == pytest.approx(NOW - MINT_2["ts"])


def test_supply_growth_with_no_dev_mint_is_a_watch():
    """Somebody bridged in, but not to a wallet we track."""
    assert _sig("bridge", _baseline(), _readings(imd_supply=SUPPLY_BEFORE + 10_000.0)) == (
        "watch", "supply +10,000 · no dev-wallet mint", None
    )


def test_bridge_outage_is_none():
    assert _sig(
        "bridge", _baseline(), _readings(bridge_mints=None, imd_supply=None)
    ) == (None, "bridge logs unavailable", None)


# --- 6. BURN ----------------------------------------------------------------
#
# LP fees (IMD side) -> BurnExecutor -> OFT-send to a Base burn receiver ->
# mainnet totalSupply drops.  The transfer to the executor lands *before* the
# supply moves, which is why it is a WATCH rather than nothing.


def test_flat_supply_is_ok():
    assert _sig("burn", _baseline(), _readings()) == ("ok", "supply flat", None)


def test_a_verified_supply_drop_fires():
    """The 2026-08-05 burn: 15,745 IMD, matching announce nonce 12 to the minute."""
    assert _sig("burn", _baseline(), _readings(imd_supply=SUPPLY_BEFORE - 15_745.0)) == (
        "fired", "burn 15,745 IMD", 0.0
    )


def test_a_transfer_to_the_burn_executor_is_a_watch():
    assert _sig("burn", _baseline(), _readings(burn_transfers=[BURN_0805])) == (
        "watch", "15,745 IMD → BurnExecutor", None
    )


def test_burn_outage_is_none():
    assert _sig(
        "burn", _baseline(), _readings(imd_supply=None, burn_transfers=None)
    ) == (None, "supply unavailable", None)


# --- 7. DECOY POOL -----------------------------------------------------------
#
# 37 third-party pools compete for the ETH/IMD pair (CLAUDE.md); nobody
# "un-deploys" a Uniswap pool, so a rising count is unambiguous.  Needs a
# baseline -- unlike BURN READY and HOT COIN below, this is a genuine delta.


def test_decoy_pool_count_holding_is_ok():
    assert _sig("decoy", _baseline(), _readings()) == ("ok", "36 decoy pools", None)


def test_decoy_pool_fires_on_a_new_spoof_pool():
    state, _, _ = _sig(
        "decoy",
        {"decoy_pool_count": 36},
        {"decoy_pool_count": 37, "decoy_newest_fee_bps": 8000},
    )
    assert state == "fired"


def test_decoy_pool_fires_with_the_fee_in_the_detail():
    assert _sig(
        "decoy",
        _baseline(),
        _readings(decoy_pool_count=DECOY_POOL_COUNT_AFTER, decoy_newest_fee_bps=DECOY_NEWEST_FEE_BPS),
    ) == ("fired", "decoy #37 · fee 80.0%", 0.0)


def test_a_new_decoy_pool_with_an_unread_fee_is_a_watch_not_a_fire():
    """Mirrors BURN READY's own rule: a partial read is not a confident one."""
    assert _sig("decoy", _baseline(), _readings(decoy_pool_count=DECOY_POOL_COUNT_AFTER)) == (
        "watch", "decoy #37 · fee unknown", None
    )


def test_first_ever_decoy_read_seeds_the_baseline_and_never_fires():
    state, detail, age = _sig("decoy", {}, _readings(decoy_pool_count=37))
    assert state == "ok"
    assert detail == "37 decoy pools · baseline set"
    assert age is None


def test_decoy_pool_is_unknown_when_the_scan_failed():
    """Not OK. An unreadable detector is unknown -- never a clean bill."""
    state, _, _ = _sig("decoy", {}, {"decoy_pool_count": None})
    assert state is None


def test_a_lagging_decoy_scan_cannot_drag_the_count_baseline_down():
    """Same protection as the five original counters: nobody un-deploys a pool."""
    _, advanced = sig.build_signals(
        _baseline(decoy_pool_count=37), _readings(decoy_pool_count=36), NOW
    )
    assert advanced["decoy_pool_count"] == 37


# --- 8. BURN READY -------------------------------------------------------------
#
# fix round 1: the launchpad's own burn gate (imdToBurn >= minBridgeAmount) is
# an EDGE detector with its own boolean baseline, not a level check. The first
# cut fired on every cycle burn_ready read True, which fired straight through
# a total outage (the launchpad slot's last-good is deliberately still served
# when the fast-tier chain read is dead) and broke this rail's own vocabulary
# -- FIRED means "something happened", never "a condition holds". WATCH is the
# right resting state for "callable right now and nobody has called it": the
# dev asked publicly for a bot to fire this, so a persistently callable
# pipeline is genuinely worth a row, just not as a fresh event forever.


def test_burn_ready_seeds_on_an_unset_baseline_and_does_not_fire():
    """The coordinator's own corrected table: an empty baseline is WATCH,
    not FIRED -- the false-first-sweep guard every other detector in this
    file already has for its own edge (GATE OPEN, NEW POST, ...)."""
    ready, detail, _ = _sig("burnready", {}, {"burn_ready": True, "burn_accrued": 15.06})
    assert ready == "watch"
    assert detail == "ready to burn · 15.06 IMD accrued"

    unknown, _, _ = _sig("burnready", {}, {"burn_ready": None})
    assert unknown is None

    idle, _, _ = _sig("burnready", {}, {"burn_ready": False, "burn_accrued": 0.0})
    assert idle == "ok"


def test_burn_ready_with_nothing_accrued_is_ok():
    assert _sig("burnready", _baseline(), _readings()) == ("ok", "not ready", None)


def test_burn_not_ready_but_accruing_is_ok_not_a_watch():
    """fix round 1: False is always OK, whatever is accrued -- the amount
    still rides along in the detail so the row is never silent about it."""
    assert _sig("burnready", _baseline(), _readings(burn_accrued=500.0)) == (
        "ok", "not ready · 500.00 IMD accrued", None
    )


def test_burn_ready_transition_fires_exactly_once():
    """The edge itself: not-ready -> ready fires; a second cycle at the same
    level does not re-fire (build_signals' own persistence carries the
    visible FIRED state forward, aging, without the detector re-declaring
    it -- exactly like every other edge detector in this file)."""
    base = _baseline(burn_ready=False)
    out1, advanced = sig.build_signals(
        base, _readings(burn_ready=True, burn_accrued=15.06), NOW
    )
    assert out1["sig_burnready_state"] == "fired"
    assert out1["sig_burnready_detail"] == "ready to burn · 15.06 IMD accrued"
    assert out1["sig_burnready_age_s"] == 0.0
    assert advanced["burn_ready"] is True
    fired_ts = advanced["fired"]["burnready"]["ts"]

    # Second cycle, 120s later, still ready: the row still reads FIRED (aged),
    # but the recorded event does not move -- the detector itself now sees
    # base_ready=True and would return WATCH; it is build_signals' persisted
    # entry that keeps the row FIRED, not a re-fire.
    out2, advanced2 = sig.build_signals(
        advanced, _readings(burn_ready=True, burn_accrued=15.06), NOW + 120.0
    )
    assert out2["sig_burnready_state"] == "fired"
    assert out2["sig_burnready_age_s"] == pytest.approx(120.0)
    assert advanced2["fired"]["burnready"]["ts"] == fired_ts


def test_burn_readiness_outage_leaves_the_fired_baseline_untouched():
    """The invariant this whole finding is about, at this layer: a cycle
    whose readings all went None must not move the burn_ready baseline or
    the fired store, whatever was recorded before it."""
    base = _baseline(burn_ready=False)
    _, seeded = sig.build_signals(base, _readings(burn_ready=True, burn_accrued=15.06), NOW)
    assert seeded["burn_ready"] is True
    assert "burnready" in seeded["fired"]

    out, advanced = sig.build_signals(
        seeded, _readings(burn_ready=None, burn_accrued=None), NOW + 240.0
    )
    # Outage: the row still shows FIRED (an outage may never un-fire a row --
    # PRD's own rule, shared by every detector here), but nothing NEW moved.
    assert out["sig_burnready_state"] == "fired"
    assert advanced["burn_ready"] == seeded["burn_ready"]
    assert advanced["fired"] == seeded["fired"]


def test_burn_readiness_outage_is_none():
    assert _sig("burnready", _baseline(), _readings(burn_ready=None)) == (
        None, "burn readiness unavailable", None
    )


def test_a_non_bool_burn_ready_reading_is_unknown_not_a_fire():
    """The gate_open regression, replayed: an int 0/1 must not read as a flag."""
    assert _sig("burnready", _baseline(), _readings(burn_ready=1)) == (
        None, "burn readiness unavailable", None
    )


def test_a_non_bool_burn_ready_baseline_never_corrupts_the_persisted_value():
    """Mirrors the gate_open regression on the write side: a malformed
    baseline (e.g. a stray int) must not sail past the coercer either."""
    _, advanced = sig.build_signals(
        _baseline(burn_ready=True), _readings(burn_ready=0), NOW
    )
    # 0 is not a bool reading (isinstance(0, bool) is False in Python, but
    # the coercer's own isinstance guard still rejects a genuine non-bool
    # int) -- the prior valid True survives untouched.
    assert advanced["burn_ready"] is True


# --- 9. HOT COIN -----------------------------------------------------------------
#
# The bar is analytics/surf_launchpad.hot_coin_threshold, never reimplemented
# here.  None (a thin hour) renders OK, never a fire.
#
# Final fix wave (C1): this is now an EDGE with a `hot_leader` baseline, like
# BURN READY -- a *new* coin over the bar fires, the same one still over it
# watches, the first judgeable hour seeds -- AND it refuses a distribution
# older than the hour it measures.  Both halves exist because the reading is
# served from a last-good slot that never expires: as a level it re-fired on
# every refresh through a total outage, off a distribution read the day before.


def _hot(counts, ts=NOW, **base_overrides):
    """``(state, detail, age)`` for HOT COIN off one distribution."""
    return _sig(
        "hot",
        _baseline(**base_overrides),
        _readings(launchpad_swaps_by_coin=counts, launchpad_swaps_ts=ts),
    )


def test_hot_coin_is_ok_not_fired_on_a_thin_hour():
    """Fewer than 5 active coins: no meaningful median, so no fire."""
    state, _, _ = _hot(HOT_COIN_COUNTS_THIN)
    assert state == "ok"


def test_hot_coin_with_no_activity_at_all_is_also_a_thin_hour():
    state, detail, _ = _sig("hot", _baseline(), _readings())
    assert state == "ok"
    assert detail == "hour too thin to judge"


def test_hot_coin_below_the_watch_bar_is_ok_with_a_count_not_a_ticker():
    """Five active coins, none within reach of the bar: quiet, not a fire."""
    state, detail, _ = _hot({"a": 5, "b": 5, "c": 5, "d": 5, "e": 5})
    assert state == "ok"
    assert detail == "busiest 5 swaps · below 15"


def test_hot_coin_warming_is_a_watch_below_the_bar():
    state, detail, _ = _hot(HOT_COIN_COUNTS_WATCH)
    assert state == "watch"
    assert detail == "e warming · 4 swaps (<6)"


def test_the_first_judgeable_hour_seeds_the_leader_without_firing():
    """The don't-fire-on-first-sight rule every other edge on this rail keeps.

    An unset ``hot_leader`` means we have never judged an hour, so a coin
    already over the bar the first time we look is a *state*, not an event.
    """
    state, detail, age = _hot(HOT_COIN_COUNTS_FIRED)
    assert state == "watch"
    assert detail == "x hot · 99 swaps (≥5)"
    assert age is None


def test_hot_coin_fires_when_a_new_coin_clears_the_bar():
    """Nobody was over the bar (``""``), now somebody is: that is the event."""
    state, detail, age = _hot(HOT_COIN_COUNTS_FIRED, hot_leader="")
    assert state == "fired"
    assert detail == "x · 99 swaps (≥5)"
    assert age == 0.0


def test_hot_coin_fires_again_when_the_lead_changes_hands():
    """A different coin over the bar is new news, not the same news."""
    state, detail, _ = _hot(HOT_COIN_COUNTS_FIRED, hot_leader="ICE")
    assert state == "fired"
    assert detail == "x · 99 swaps (≥5)"


def test_the_same_hot_coin_stays_a_watch_and_never_re_fires():
    """The level-detector bug in one assertion: hot yesterday and hot today is
    one event, and the rail's vocabulary reserves FIRED for events."""
    state, detail, age = _hot(HOT_COIN_COUNTS_FIRED, hot_leader="x")
    assert state == "watch"
    assert detail == "x still hot · 99 swaps (≥5)"
    assert age is None


def test_a_stale_swap_distribution_is_unknown_never_a_fire():
    """C1's regression test: the launchpad slot never expires.

    ``launchpad_swaps_by_coin`` is a *windowed* statistic ("swaps this hour"),
    unlike ``burn_ready``, which is a standing fact.  Replayed a day later it
    is a false present-tense claim in **any** state -- so past
    ``HOT_MAX_AGE_S`` the row goes explicitly unknown rather than quiet, and
    certainly rather than firing.
    """
    fresh = _hot(HOT_COIN_COUNTS_FIRED, hot_leader="")
    assert fresh[0] == "fired"

    state, detail, age = _hot(
        HOT_COIN_COUNTS_FIRED, ts=NOW - L.HOT_MAX_AGE_S - 1.0, hot_leader=""
    )
    assert state is None
    assert detail == "swap distribution stale"
    assert age is None


def test_an_unstamped_swap_distribution_is_treated_as_stale():
    """A reading that cannot be shown to be current fails safe, not open."""
    state, detail, _ = _hot(HOT_COIN_COUNTS_FIRED, ts=None, hot_leader="")
    assert state is None
    assert detail == "swap distribution stale"


def test_a_stale_distribution_never_seeds_the_leader_baseline():
    """Too old to render is too old to conclude anything from.

    Otherwise a restart against a day-old cache would seed ``hot_leader`` from
    it, and the first genuinely fresh sweep naming the same coin would then
    read as "already reported" and never fire.
    """
    base = _baseline()
    _, advanced = sig.build_signals(
        base,
        _readings(
            launchpad_swaps_by_coin=HOT_COIN_COUNTS_FIRED,
            launchpad_swaps_ts=NOW - L.HOT_MAX_AGE_S - 1.0,
        ),
        NOW,
    )
    assert "hot_leader" not in advanced


def test_a_judged_hour_with_nobody_hot_seeds_the_empty_leader():
    """``""`` is a real conclusion ("we judged, nobody cleared it") and is what
    lets the *next* coin over the bar fire instead of merely seeding."""
    _, advanced = sig.build_signals(
        _baseline(),
        _readings(
            launchpad_swaps_by_coin=HOT_COIN_COUNTS_WATCH, launchpad_swaps_ts=NOW
        ),
        NOW,
    )
    assert advanced["hot_leader"] == ""


def test_the_persisted_leader_is_the_filtered_ticker_not_the_raw_one():
    """This baseline goes to disk; a hostile ticker must not go with it."""
    _, advanced = sig.build_signals(
        _baseline(),
        _readings(
            launchpad_swaps_by_coin=HOT_COIN_COUNTS_FIRED, launchpad_swaps_ts=NOW
        ),
        NOW,
    )
    assert advanced["hot_leader"] == "x"


def test_a_non_str_hot_leader_baseline_never_corrupts_the_persisted_value():
    """Mirrors the gate_open/burn_ready regressions on the write side."""
    _, advanced = sig.build_signals(
        _baseline(hot_leader="ICE"),
        _readings(launchpad_swaps_by_coin=None, launchpad_swaps_ts=None),
        NOW,
    )
    assert advanced["hot_leader"] == "ICE"


def test_hot_coin_detail_never_carries_an_unescaped_markup_tag():
    """fix round 1, finding 2: the real property, not the wrong assertion.

    The original version of this test asserted ``"[/x]" not in detail``,
    which no *escaping* scheme can ever satisfy: ``rich.markup.escape``
    (this dashboard's standard treatment, applied to every detail at the
    widget layer) only ever prepends a backslash to a ``[`` -- it never
    removes the bracket, so the raw 4-char substring always survives intact
    inside the escaped text. That assertion could only ever pass because
    :func:`sig._safe_ticker` *drops* unsafe characters rather than escaping
    them -- a real, useful property, but the test was accidentally coupled
    to one specific implementation rather than to what actually matters.

    What actually matters: a hostile ticker must not be able to introduce a
    ``[`` into this module's own output at all -- the one character that can
    open a markup tag -- and the row must still name *a* coin rather than
    going silent about which one is hot.
    """
    counts = {f"c{i}": 1 for i in range(5)}
    counts["[/x]"] = 99
    _, detail, _ = _hot(counts, hot_leader="")
    assert "[" not in detail
    # _safe_ticker keeps "x" -- the one character of "[/x]" in the safe set
    # -- so the coin stays identifiable even though the hostile wrapper is gone.
    assert "x" in detail


def test_hot_coin_falls_back_to_a_generic_word_when_nothing_survives_the_filter():
    """A ticker built entirely from unsafe characters is not silently empty."""
    counts = {f"c{i}": 1 for i in range(4)}
    counts["[[[["] = 50
    _, detail, _ = _hot(counts, hot_leader="")
    assert "coin" in detail
    assert "[" not in detail


def test_hot_coin_outage_is_none():
    assert _hot(None) == (None, "swap distribution unavailable", None)


def test_hot_coin_ignores_malformed_rows_without_crashing():
    """A non-int count or a non-str ticker must not take the row down."""
    counts = {"good": 50, "bad": "lots", 7: 12, "ok2": True}
    state, _, _ = _hot(counts)
    # Only "good" (50) is a valid str->int entry, and one active coin is
    # still a thin hour.
    assert state == "ok"


def test_the_hot_coin_staleness_bound_is_the_window_it_measures():
    """``HOT_MAX_AGE_S`` is the hour the distribution counts, not a guess.

    ``surf_client`` owns the window (``LAUNCHPAD_HOUR_BLOCKS`` blocks at
    ``_LAUNCHPAD_BLOCK_SECONDS`` each); analytics may not import the client,
    so the two are pinned together here instead.  Re-cut the window and this
    goes red rather than letting the bound silently outgrow it.
    """
    from maxpane_dashboard.data import surf_client

    assert (
        surf_client.LAUNCHPAD_HOUR_BLOCKS * surf_client._LAUNCHPAD_BLOCK_SECONDS
        == L.HOT_MAX_AGE_S
    )


# --- ordering: equal timestamps must not hide a genuinely new event ---------
#
# Two ways a stream arrives with equal ``ts`` values, and both are ordinary:
#
# 1. ``_log_ts``'s fallback. Some keyless logs endpoints omit ``blockTimestamp``
#    (drpc does; tenderly does not), so every row in that sweep is stamped with
#    the same observation clock.
# 2. Two events in the SAME BLOCK carry identical real timestamps. Two OFT mints
#    in one block is nothing unusual — 2026-08-07's pair landed 156 s apart, but
#    nothing makes that a rule.
#
# Under either, ``max(rows, key=ts)`` returns the FIRST maximal element, which
# for the ascending order ``eth_getLogs`` serves is the OLDEST row — the one
# already recorded as the baseline. The new event behind it was structurally
# invisible, and then fired hours later when the old row rolled out of the
# window. BRIDGE STAGE is documented as the earliest of the six detectors, so
# it is the one with the most to lose.


def _mint(tx: str, *, ts: float, block: int, log_index: int, amount: float = 1000.0) -> dict:
    """A decoded bridge-mint row in the manager's shape, ordering fields and all."""
    return {
        "ts": ts, "tx_hash": tx, "amount": amount, "to_label": "frenpet.eth",
        "block": block, "log_index": log_index,
    }


def test_a_new_mint_behind_an_equally_stamped_row_still_fires():
    """Trigger 1: the whole group carries one observation stamp."""
    stamp = NOW - 60.0
    seen = _mint("0x" + "aa" * 32, ts=stamp, block=25_707_000, log_index=4)
    fresh = _mint("0x" + "bb" * 32, ts=stamp, block=25_707_010, log_index=1)

    state, detail, _age = _sig(
        "bridge",
        _baseline(bridge_tx=seen["tx_hash"], bridge_ts=stamp,
                  bridge_seq=[seen["block"], seen["log_index"]]),
        # Ascending, exactly as the endpoint serves it — the new row is LAST.
        _readings(bridge_mints=[seen, fresh]),
    )
    assert state == "fired"
    assert detail == "mint 1,000 IMD → frenpet.eth"


def test_a_second_event_in_the_same_block_still_fires():
    """Trigger 2: identical REAL timestamps, no fallback involved.

    ``_fresh_event`` required ``ts > base_ts`` strictly, so the second of two
    events in one block could never fire — not late, never.
    """
    stamp = NOW - 60.0
    seen = _mint("0x" + "aa" * 32, ts=stamp, block=25_707_000, log_index=4)
    fresh = _mint("0x" + "bb" * 32, ts=stamp, block=25_707_000, log_index=9)

    state, _detail, _age = _sig(
        "bridge",
        _baseline(bridge_tx=seen["tx_hash"], bridge_ts=stamp,
                  bridge_seq=[seen["block"], seen["log_index"]]),
        _readings(bridge_mints=[seen, fresh]),
    )
    assert state == "fired"


def test_the_baseline_advances_to_the_truly_newest_of_an_equally_stamped_group():
    """A baseline pinned to the oldest row re-fires it on the next refresh."""
    stamp = NOW - 60.0
    seen = _mint("0x" + "aa" * 32, ts=stamp, block=25_707_000, log_index=4)
    fresh = _mint("0x" + "bb" * 32, ts=stamp, block=25_707_010, log_index=1)

    _out, advanced = sig.build_signals(
        _baseline(bridge_tx="", bridge_ts=0.0),
        _readings(bridge_mints=[seen, fresh]),
        NOW,
    )
    assert advanced["bridge_tx"] == fresh["tx_hash"]
    assert advanced["bridge_seq"] == [fresh["block"], fresh["log_index"]]


def test_a_rolled_window_still_cannot_make_the_second_newest_look_new():
    """The rule the ordering must not break: losing the newest row is not news."""
    seen = _mint("0x" + "bb" * 32, ts=NOW - 60.0, block=25_707_010, log_index=1)
    older = _mint("0x" + "aa" * 32, ts=NOW - 600.0, block=25_707_000, log_index=4)

    state, _detail, _age = _sig(
        "bridge",
        _baseline(bridge_tx=seen["tx_hash"], bridge_ts=seen["ts"],
                  bridge_seq=[seen["block"], seen["log_index"]]),
        _readings(bridge_mints=[older]),
    )
    assert state == "ok"


def test_ordering_never_falls_back_to_iteration_order():
    """Position is not a tie-break, because the streams disagree about it.

    ``eth_getLogs`` serves ascending and ``_bridge_rows`` keeps that order, but
    ``deploy_events`` is sorted newest-first by the manager before it is handed
    over. A positional rule would therefore mean opposite things for two streams
    that share one code path — which is why the tie-break is ``(block, log
    index)``, both of which the client preserves verbatim.
    """
    stamp = NOW - 60.0
    seen = _mint("0x" + "aa" * 32, ts=stamp, block=25_707_000, log_index=4)
    fresh = _mint("0x" + "bb" * 32, ts=stamp, block=25_707_010, log_index=1)
    base = _baseline(bridge_tx=seen["tx_hash"], bridge_ts=stamp,
                     bridge_seq=[seen["block"], seen["log_index"]])

    for rows in ([seen, fresh], [fresh, seen]):
        state, _detail, _age = _sig("bridge", base, _readings(bridge_mints=rows))
        assert state == "fired", rows


# --- fix round 2: _advance must coerce imd_supply as strictly as BRIDGE STAGE
# and BURN read it ----------------------------------------------------------
#
# Mirrors the gate_open regression above.  _detect_bridge and _detect_burn
# both defend the *read* side with _as_float, so a garbage baseline value
# already can't be compared as a number -- but without a coercer in
# _SCALAR_COERCERS, _advance's only guard is "reading is not None", so that
# same garbage would still get persisted verbatim.  The next cycle then reads
# the corrupted baseline back as None (via _as_float) and both detectors treat
# an unset baseline as "seed, don't fire" -- so a genuine burn or bridge mint
# landing on exactly that cycle would be silently swallowed instead of firing.


def test_a_malformed_supply_reading_never_corrupts_the_persisted_baseline():
    base = _baseline(imd_supply=SUPPLY_BEFORE)
    _, advanced = sig.build_signals(base, _readings(imd_supply="not-a-number"), NOW)
    # The garbage string must not reach the baseline -- the prior valid float
    # survives untouched, exactly as an outright None reading would leave it.
    assert advanced["imd_supply"] == SUPPLY_BEFORE

    # A real burn on the following cycle must still be seen as a real drop.
    state, detail, age = _sig(
        "burn", advanced, _readings(imd_supply=SUPPLY_BEFORE - 15_745.0)
    )
    assert state == "fired"
    assert detail == "burn 15,745 IMD"
    assert age == 0.0


def test_a_legitimate_supply_reading_is_still_persisted():
    """The hardening must not stop a genuinely valid float from persisting."""
    _, advanced = sig.build_signals(
        _baseline(imd_supply=SUPPLY_BEFORE), _readings(imd_supply=SUPPLY_AFTER_MINTS), NOW
    )
    assert advanced["imd_supply"] == SUPPLY_AFTER_MINTS


# --- WP2.11: every BASELINE_SCALARS key needs a coercer, not just the two
# the earlier two regressions happened to name ------------------------------
#
# gate_open and imd_supply both got a coercer because a reviewer found a
# concrete exploit for each. The other six BASELINE_SCALARS keys were left
# exactly as permissive as before either fix -- and a reviewer proved that gap
# is exploitable too: ``_as_int(True)`` is ``None`` (a bool is never a nonce),
# so a bool reading not only slips past _advance's "reading is not None"
# guard, it also *bypasses the MONOTONIC_BASELINES down-guard in the same
# motion* -- that guard compares ``_as_int`` of both sides, and
# ``current is not None`` is already False for a bool, so "don't move
# backward" never runs, and the raw bool sails straight into
# ``out[key] = value``. The corrupted baseline then reads back as ``None`` on
# the next cycle (``_as_int(True)`` again), so every detector that gates on
# "the baseline is not None" treats it as unset and silently re-seeds instead
# of firing -- a genuine event swallowed, the exact shape of the imd_supply
# bug, for five more keys.


def test_every_baseline_scalar_has_a_coercer():
    """Closes the class of bug, not the eight keys that happen to exist today.

    A future BASELINE_SCALARS entry with no matching _SCALAR_COERCERS entry
    would silently fall back to the pre-WP2.11 lax behaviour -- this fails the
    moment that happens, instead of depending on someone remembering to add
    the key by hand.
    """
    assert set(sig._SCALAR_COERCERS) == set(sig.BASELINE_SCALARS)


@pytest.mark.parametrize(
    "key",
    [
        "dev_nonce", "announce_nonce", "channel_tx_count", "ops_nonce",
        "identities_written", "decoy_pool_count",
    ],
)
def test_a_bool_reading_never_corrupts_any_counter_baseline(key):
    """The dev_nonce=True exploit, generalised to every affected counter.

    MUTATION CHECK (run it, watch it go red, restore): trim
    ``_SCALAR_COERCERS`` back to only ``"gate_open"`` and ``"imd_supply"``
    (the state before this task) -> this fails with e.g.
    ``AssertionError: assert True == 2350``: the raw bool is exactly what got
    persisted, having sailed straight past the monotonic-down guard too
    (``_as_int(True)`` is ``None``, so that guard's own "is not None" check
    never fires).
    """
    base = _baseline(**{key: 2350})
    _, advanced = sig.build_signals(base, _readings(**{key: True}), NOW)
    assert advanced[key] == 2350


def test_a_bool_dev_nonce_reading_does_not_swallow_the_next_genuine_watch():
    """The concrete consequence of the exploit above, spelled out end to end.

    A corrupted ``dev_nonce`` baseline of ``True`` reads back as ``None``
    (``_as_int(True)``), so NEW DEPLOY's own ``base_dev is not None`` guard
    would treat the very next real nonce move as a first-ever read and
    silently re-seed instead of watching it -- one bad read permanently
    disarming NEW DEPLOY's nonce-only precursor for as long as the baseline
    stays poisoned. With the fix, the baseline survives the bool untouched and
    the genuine transition is still watched.
    """
    base = _baseline(dev_nonce=2350)
    _, advanced = sig.build_signals(base, _readings(dev_nonce=True), NOW)
    assert advanced["dev_nonce"] == 2350

    state, detail, age = _sig("deploy", advanced, _readings(dev_nonce=2351))
    assert state == "watch"
    assert detail == "surfsurf.eth nonce 2350→2351"


def test_a_bool_announce_nonce_reading_does_not_swallow_the_next_genuine_post():
    """Same exploit on the key whose genuine detection is a FIRED row, not a
    WATCH -- proving the fix holds where "swallowed" means a missed NEW POST,
    the single cheapest and earliest of the six detectors.
    """
    base = _baseline(announce_nonce=13)
    _, advanced = sig.build_signals(base, _readings(announce_nonce=True), NOW)
    assert advanced["announce_nonce"] == 13
    assert advanced["fired"] == {}

    state, detail, age = _sig(
        "post",
        advanced,
        _readings(
            announce_nonce=14,
            channel_tx_count=21,
            announce_last_text=LP_POST_TEXT,
            announce_last_ts=LP_POST_TS,
        ),
    )
    assert state == "fired"
    assert detail == LP_POST_DETAIL
    assert age == pytest.approx(NOW - LP_POST_TS)


# ---------------------------------------------------------------------------
# The matrix: every detector x every state.
#
# PRD §8 asks for exactly this table.  It is a coverage lock as much as a
# behaviour test: `test_the_matrix_covers_every_detector` fails the moment a
# seventh detector lands without its four rows, and the None column is the
# machine-checkable half of success criterion 3.
# ---------------------------------------------------------------------------

MATRIX: tuple[tuple[str, str, dict, dict, str], ...] = (
    # (signal, expected state, baseline overrides, reading overrides, expected detail)
    ("post", "ok", {}, {}, "nonce 13 · no new post"),
    ("post", "watch", {}, {"channel_tx_count": 21}, "reply on channel · 21 txs"),
    ("post", "fired", {},
     {"announce_nonce": 14, "announce_last_text": LP_POST_TEXT, "announce_last_ts": LP_POST_TS},
     LP_POST_DETAIL),
    ("post", None, {}, {"announce_nonce": None, "channel_tx_count": None}, "channel unavailable"),

    ("lp", "ok", {}, {}, "v4 position holds"),
    ("lp", "watch", {}, {"ops_nonce": 37}, "frenpet.eth active · nonce 37"),
    ("lp", "fired", {}, {"lp_liquidity": 677_000_000_000}, "v4 position OUT -32.3%"),
    ("lp", None, {}, {"lp_liquidity": None, "ops_nonce": None, "v4_hook_pools": None},
     "v4 position unavailable"),

    ("gate", "ok", {}, {}, "closed · 1 written"),
    ("gate", "watch", {}, {"identities_written": 2}, "1→2 written · gate closed"),
    ("gate", "fired", {}, {"gate_open": True}, "GATE OPEN · 1 written"),
    ("gate", None, {}, {"gate_open": None, "identities_written": None}, "gate unavailable"),

    ("deploy", "ok", {}, {}, "no new contract"),
    ("deploy", "watch", {}, {"dev_nonce": 2351}, "surfsurf.eth nonce 2350→2351"),
    ("deploy", "fired", {}, {"deploy_events": [FRESH_ACTION]}, "action register() · announce"),
    ("deploy", None, {}, {"deploy_events": None, "dev_nonce": None}, "dev activity unavailable"),

    ("bridge", "ok", {}, {}, "no mints in window"),
    ("bridge", "watch", {}, {"imd_supply": SUPPLY_BEFORE + 10_000.0},
     "supply +10,000 · no dev-wallet mint"),
    ("bridge", "fired", {}, {"bridge_mints": [MINT_1, MINT_2]}, "mint 114,367 IMD → frenpet.eth"),
    ("bridge", None, {}, {"bridge_mints": None, "imd_supply": None}, "bridge logs unavailable"),

    ("burn", "ok", {}, {}, "supply flat"),
    ("burn", "watch", {}, {"burn_transfers": [BURN_0805]}, "15,745 IMD → BurnExecutor"),
    ("burn", "fired", {}, {"imd_supply": SUPPLY_BEFORE - 15_745.0}, "burn 15,745 IMD"),
    ("burn", None, {}, {"imd_supply": None, "burn_transfers": None}, "supply unavailable"),

    ("decoy", "ok", {}, {}, "36 decoy pools"),
    ("decoy", "watch", {}, {"decoy_pool_count": DECOY_POOL_COUNT_AFTER}, "decoy #37 · fee unknown"),
    ("decoy", "fired", {},
     {"decoy_pool_count": DECOY_POOL_COUNT_AFTER, "decoy_newest_fee_bps": DECOY_NEWEST_FEE_BPS},
     "decoy #37 · fee 80.0%"),
    ("decoy", None, {}, {"decoy_pool_count": None}, "decoy scan unavailable"),

    # fix round 1: BURN READY is an edge detector, so WATCH (still callable,
    # already reported) needs a baseline that already says True -- reachable
    # only with a baseline override, unlike its siblings' reading-only rows.
    ("burnready", "ok", {}, {}, "not ready"),
    ("burnready", "watch", {"burn_ready": True}, {"burn_ready": True, "burn_accrued": 15.06},
     "ready to burn · 15.06 IMD accrued"),
    ("burnready", "fired", {"burn_ready": False}, {"burn_ready": True, "burn_accrued": 15.06},
     "ready to burn · 15.06 IMD accrued"),
    ("burnready", None, {}, {"burn_ready": None}, "burn readiness unavailable"),

    # Final fix wave (C1): HOT COIN is an edge too, so FIRED needs a baseline
    # that already judged an hour and found nobody over the bar ("") --
    # reachable only with a baseline override, exactly like BURN READY above.
    ("hot", "ok", {}, {"launchpad_swaps_by_coin": HOT_COIN_COUNTS_THIN}, "hour too thin to judge"),
    ("hot", "watch", {}, {"launchpad_swaps_by_coin": HOT_COIN_COUNTS_WATCH},
     "e warming · 4 swaps (<6)"),
    ("hot", "fired", {"hot_leader": ""}, {"launchpad_swaps_by_coin": HOT_COIN_COUNTS_FIRED},
     "x · 99 swaps (≥5)"),
    ("hot", None, {}, {"launchpad_swaps_by_coin": None}, "swap distribution unavailable"),
)


@pytest.mark.parametrize(
    "name,expected_state,base_overrides,overrides,expected_detail",
    MATRIX,
    ids=[f"{row[0]}-{row[1] or 'outage'}" for row in MATRIX],
)
def test_signal_matrix(name, expected_state, base_overrides, overrides, expected_detail):
    state, detail, _ = _sig(name, _baseline(**base_overrides), _readings(**overrides))
    assert state == expected_state
    assert detail == expected_detail


def test_the_matrix_covers_every_detector_and_every_state():
    covered = {(row[0], row[1]) for row in MATRIX}
    expected = {
        (name, state)
        for name in sig.SIGNAL_NAMES
        for state in ("ok", "watch", "fired", None)
    }
    assert covered == expected


@pytest.mark.parametrize("name,expected_state,base_overrides,overrides,_detail", MATRIX,
                         ids=[f"{row[0]}-{row[1] or 'outage'}" for row in MATRIX])
def test_no_row_of_the_matrix_moves_an_unread_baseline(
    name, expected_state, base_overrides, overrides, _detail
):
    """Whatever a detector decides, a ``None`` reading never writes a baseline."""
    base = _baseline(**base_overrides)
    _, advanced = sig.build_signals(base, _readings(**overrides), NOW)
    for key, value in overrides.items():
        if value is None and key in sig.BASELINE_SCALARS:
            assert advanced[key] == base[key], key


# ---------------------------------------------------------------------------
# The two poisoned-baseline regressions.
#
# Both are recorded failures, not hypotheticals: CLAUDE.md's "a failed read is
# None, never 0" exists because a client turned an outage into a zero and the
# zero got persisted, and PRD §6.1 names the supply case specifically.
# ---------------------------------------------------------------------------


def test_a_failed_supply_read_cannot_fire_burn():
    """supply None must not read as 0 and burn 2.37M tokens.

    MUTATION CHECK (run it, watch it go red, restore):
    in ``_detect_burn`` replace

        if supply is not None and base_supply is not None and supply < base_supply:

    with the coercion that shipped in the original bug

        supply = float(supply or 0)
        base_supply = float(base_supply or 0)
        if supply < base_supply:

    -> this test fails with ``AssertionError: assert 'fired' is None``, and the
    detail on that row reads ``burn 2,252,365 IMD``: the entire supply, burned
    by a network hiccup.  ``test_a_failed_supply_read_cannot_poison_the_
    persisted_baseline`` fails with it.
    """
    state, detail, age = _sig("burn", _baseline(), _readings(imd_supply=None))
    assert state is None
    assert detail == "supply unavailable"
    assert age is None


def test_a_failed_supply_read_cannot_poison_the_persisted_baseline():
    """The outage must not survive itself: the old supply stays in the cache."""
    base = _baseline()
    _, advanced = sig.build_signals(base, _readings(imd_supply=None), NOW)
    assert advanced["imd_supply"] == SUPPLY_BEFORE
    # And the next successful read compares against the real previous value,
    # so no burn is invented on recovery either.
    state, _, _ = _sig("burn", advanced, _readings(imd_supply=SUPPLY_BEFORE))
    assert state == "ok"


def test_an_lp_outage_cannot_un_fire_a_migration():
    """A network blip must never retract an event already shown.

    MUTATION CHECK (run it, watch it go red, restore):
    in ``build_signals`` replace

        if entry is not None and now - entry["ts"] < FIRED_TTL_S:

    with

        if det.state is not None and entry is not None and now - entry["ts"] < FIRED_TTL_S:

    -> this test fails with ``AssertionError: assert None == 'fired'``: the
    outage clears a FIRED row that is 1 h old.
    """
    fired_at = NOW - 3600.0
    base = _baseline(fired={"lp": {"ts": fired_at, "detail": "v4 position OUT -32.3%"}})
    state, detail, age = _sig(
        "lp", base, _readings(lp_liquidity=None, ops_nonce=None, v4_hook_pools=None)
    )
    assert state == "fired"
    assert detail == "v4 position OUT -32.3%"
    assert age == pytest.approx(3600.0)


def test_an_outage_does_not_extend_or_reset_the_fired_age():
    """The age tracks the event, not the last successful poll."""
    fired_at = NOW - 7200.0
    base = _baseline(fired={"lp": {"ts": fired_at, "detail": "v4 position OUT -32.3%"}})
    _, advanced = sig.build_signals(base, _readings(lp_liquidity=None), NOW)
    assert advanced["fired"]["lp"]["ts"] == fired_at
    _, _, age = _sig("lp", advanced, _readings(lp_liquidity=None), now=NOW + 600.0)
    assert age == pytest.approx(7800.0)


def test_a_fired_row_relaxes_but_the_event_is_never_forgotten():
    """After the TTL the row is ok/watch again and still names what happened."""
    base = _baseline(
        fired={"lp": {"ts": NOW - sig.FIRED_TTL_S - 1.0, "detail": "v4 position OUT -32.3%"}}
    )
    state, detail, age = _sig("lp", base, _readings())
    assert state == "ok"
    assert detail == "v4 position holds · last: v4 position OUT -32.3%"
    assert age == pytest.approx(float(sig.FIRED_TTL_S) + 1.0)


# ---------------------------------------------------------------------------
# Success criterion 2 (PRD §11): replay the real 2026-08-07 LP-add sequence and
# assert BRIDGE STAGE fires before NEW POST.
#
# The real choreography, from ops_eth_txs.json / ops_eth_token_transfers.json /
# announce_eth_txs.json:
#
#   04:18:59  OFT mint      10,000.000000 IMD -> frenpet.eth   0x17084b1b…
#   04:21:35  OFT mint     114,366.899256 IMD -> frenpet.eth   0xc7acbcc0…
#   04:22:23  approve      IMD -> NFPM (ops nonce 36)          0x0031c5c8…
#   04:23:23  multicall    increaseLiquidity (ops nonce 37)    0x90a0f8e2…
#   04:27:11  announce     "I moved 33 eth to the LP…"         0xe397869a…
#
# Eight minutes end to end.  BRIDGE STAGE flags it at the first mint, 492 s
# before the announcement everyone else was waiting for.  Each poll
# feeds the previous poll's advanced baselines back in, which is what the
# manager does and what makes the ordering claim real rather than staged.

T1_STAGED = 1_786_076_520.0   # 04:22:00Z -- both mints landed, LP untouched
T2_ADDED = 1_786_076_700.0    # 04:25:00Z -- liquidity added, no post yet
T3_POSTED = 1_786_076_900.0   # 04:28:20Z -- the announcement landed


def test_the_2026_08_07_sequence_fires_bridge_before_post():
    base = _baseline()

    # --- poll 1: 04:22:00Z.  Only the mints have happened.
    out1, base = sig.build_signals(
        base,
        _readings(bridge_mints=[MINT_1, MINT_2], imd_supply=SUPPLY_AFTER_MINTS),
        T1_STAGED,
    )
    assert out1["sig_bridge_state"] == "fired"
    assert out1["sig_bridge_detail"] == "mint 114,367 IMD → frenpet.eth"
    assert out1["sig_bridge_age_s"] == pytest.approx(T1_STAGED - MINT_2["ts"])
    assert out1["sig_post_state"] == "ok"
    assert out1["sig_lp_state"] == "ok"

    # --- poll 2: 04:25:00Z.  33 ETH went in; the LP row escalates to WATCH and
    # BRIDGE stays FIRED without re-firing on the mints it already reported.
    out2, base = sig.build_signals(
        base,
        _readings(
            bridge_mints=[MINT_1, MINT_2],
            imd_supply=SUPPLY_AFTER_MINTS,
            lp_liquidity=LP_LIQUIDITY_AFTER_ADD,
            ops_nonce=38,
        ),
        T2_ADDED,
    )
    assert out2["sig_lp_state"] == "watch"
    assert out2["sig_lp_detail"] == "v4 position +33.0%"
    assert out2["sig_bridge_state"] == "fired"
    assert out2["sig_bridge_age_s"] == pytest.approx(T2_ADDED - MINT_2["ts"])
    assert out2["sig_post_state"] == "ok"

    # --- poll 3: 04:28:20Z.  The announcement lands last, as it always does.
    out3, base = sig.build_signals(
        base,
        _readings(
            bridge_mints=[MINT_1, MINT_2],
            imd_supply=SUPPLY_AFTER_MINTS,
            lp_liquidity=LP_LIQUIDITY_AFTER_ADD,
            ops_nonce=38,
            announce_nonce=14,
            channel_tx_count=21,
            announce_last_text=LP_POST_TEXT,
            announce_last_ts=LP_POST_TS,
        ),
        T3_POSTED,
    )
    assert out3["sig_post_state"] == "fired"
    assert out3["sig_post_detail"] == LP_POST_DETAIL
    assert out3["sig_bridge_state"] == "fired"

    # The claim itself: BRIDGE STAGE's first FIRED poll is strictly earlier
    # than NEW POST's.  A bare timestamp comparison here would be tautological
    # -- `fired[name]["ts"]` is the chain event's own timestamp, not a
    # detection-order marker, so `fired["bridge"]["ts"] < fired["post"]["ts"]`
    # reduces to `MINT_2["ts"] < LP_POST_TS`, provable straight from the
    # fixture JSON with zero calls into build_signals, and it would hold even
    # if a single poll detected both signals at once or in reverse order.
    # This instead asks which *poll* first rendered each signal as "fired",
    # which is exactly the poll-order-sensitive claim the criterion makes.
    polls = (out1, out2, out3)

    def _first_fired_poll(name: str) -> int | None:
        for index, out in enumerate(polls, start=1):
            if out[f"sig_{name}_state"] == "fired":
                return index
        return None

    bridge_first_fired = _first_fired_poll("bridge")
    post_first_fired = _first_fired_poll("post")
    assert bridge_first_fired is not None and post_first_fired is not None
    assert bridge_first_fired < post_first_fired


def test_the_replay_never_re_fires_an_event_it_already_reported():
    """Polling the same window twice reports one event, not two."""
    base = _baseline()
    _, base = sig.build_signals(
        base, _readings(bridge_mints=[MINT_1, MINT_2], imd_supply=SUPPLY_AFTER_MINTS), T1_STAGED
    )
    first_fired = base["fired"]["bridge"]["ts"]
    out, base = sig.build_signals(
        base, _readings(bridge_mints=[MINT_1, MINT_2], imd_supply=SUPPLY_AFTER_MINTS), T2_ADDED
    )
    assert base["fired"]["bridge"]["ts"] == first_fired
    assert out["sig_bridge_age_s"] == pytest.approx(T2_ADDED - MINT_2["ts"])


def test_a_rolled_log_window_does_not_look_like_a_new_event():
    """When the newest mint scrolls out of the window, the older one is not news."""
    base = _baseline()
    _, base = sig.build_signals(base, _readings(bridge_mints=[MINT_1, MINT_2]), T1_STAGED)
    out, advanced = sig.build_signals(base, _readings(bridge_mints=[MINT_1]), T2_ADDED)
    assert out["sig_bridge_state"] == "fired"          # persisted, not re-fired
    assert advanced["fired"]["bridge"]["ts"] == MINT_2["ts"]
    assert advanced["bridge_tx"] == MINT_2["tx_hash"]


# ---------------------------------------------------------------------------
# Success criterion 3 (PRD §11): under a full outage no signal fires and no
# baseline moves.
# ---------------------------------------------------------------------------


def _blackout() -> dict:
    return {key: None for key in sig.READING_KEYS}


def test_total_outage_fires_nothing_and_moves_nothing():
    base = _baseline()
    out, advanced = sig.build_signals(base, _blackout(), NOW)

    for name in sig.SIGNAL_NAMES:
        assert out[f"sig_{name}_state"] is None, name
        assert out[f"sig_{name}_detail"].endswith("unavailable"), name
        assert out[f"sig_{name}_age_s"] is None, name

    assert {k: v for k, v in advanced.items() if k != "fired"} == {
        k: v for k, v in base.items() if k != "fired"
    }
    assert advanced["fired"] == {}


def test_total_outage_keeps_a_recent_fired_row_visible():
    """Criterion 3 says nothing *new* fires — not that history disappears."""
    base = _baseline(fired={"burn": {"ts": NOW - 600.0, "detail": "burn 15,745 IMD"}})
    out, advanced = sig.build_signals(base, _blackout(), NOW)
    assert out["sig_burn_state"] == "fired"
    assert out["sig_burn_age_s"] == pytest.approx(600.0)
    assert advanced["fired"]["burn"]["ts"] == NOW - 600.0
    assert advanced["imd_supply"] == SUPPLY_BEFORE


def test_an_empty_cache_plus_a_full_outage_is_completely_silent():
    """First launch with the network down: six unknowns, no invented state."""
    out, advanced = sig.build_signals({}, _blackout(), NOW)
    assert all(out[f"sig_{name}_state"] is None for name in sig.SIGNAL_NAMES)
    assert advanced == {"fired": {}}


# ---------------------------------------------------------------------------
# Structural guards.
#
# This module is required to be pure (CLAUDE.md: analytics/ is "PURE functions:
# signals, EV math. No I/O, no Textual imports.").  "No test touches the
# network" is asserted structurally rather than by mocking, because there is no
# transport here to inject a raising stub into: the assertion is that the
# module cannot reach a network or a clock at all.
# ---------------------------------------------------------------------------

import re

_MODULE_SOURCE = Path(sig.__file__).read_text(encoding="utf-8")


def _code_only(source: str) -> str:
    """Source with docstrings and comments stripped.

    The guards below assert on what the code *does*; a docstring is allowed to
    name the thing it forbids.
    """
    return re.sub(r"#[^\n]*", "", re.sub(r'"""(?:.|\n)*?"""', "", source))


def test_module_is_pure():
    code = _code_only(_MODULE_SOURCE)
    for forbidden in (
        "import requests", "import httpx", "import aiohttp", "import urllib",
        "import socket", "import time", "import datetime", "import asyncio",
        "from textual", "import textual",
        "time.time(", "datetime.now(", "utcnow(",
        "maxpane_dashboard.data.surf_client", "maxpane_dashboard.data.surf_cache",
        # Task 7's HOT COIN ticker filter is local (_safe_ticker); every
        # detail is still escaped once, uniformly, at the widget layer.
        "maxpane_dashboard.widgets", "maxpane_dashboard.data.surf_manager",
    ):
        assert forbidden not in code, forbidden


def test_the_only_data_imports_are_the_three_documented_boundary_modules():
    """Analytics-internal dependencies only, and the list is exact.

    ``surf_addresses`` and ``surf_models`` are WP0's boundary declarations —
    constants and dataclasses, no I/O.  ``surf_launchpad`` (Task 7) is the
    third: HOT COIN's threshold is computed there and must not be
    reimplemented here (the brief is explicit about this), and that module is
    itself analytics-pure (no I/O, no Textual, its own docstring says so).
    The client (WP1), the cache and the manager (WP4) are not importable from
    here at any point, and the list is compared exactly rather than by
    substring so a fourth import cannot arrive unnoticed -- in particular,
    ``widgets.markup_safety`` never appears here: HOT COIN's ticker is
    filtered locally (:func:`sig._safe_ticker`), and every detail -- HOT
    COIN's included -- is still escaped once, uniformly, at the widget,
    exactly like the other eight.

    The second half is the re-export rule: ``CHANNEL_KINDS`` is frozen once, in
    WP0's models module.  A local literal would give one closed vocabulary two
    green tests — WP0's ``test_channel_tx_kinds_are_the_four_frozen_strings``
    and this suite's — so a fifth kind added to one copy would pass both while
    the classifier and the models disagreed about what may be returned.
    """
    from maxpane_dashboard.data import surf_models

    imports = [line for line in _MODULE_SOURCE.splitlines() if line.startswith("from maxpane")]
    assert imports == [
        "from maxpane_dashboard.analytics.surf_launchpad import HOT_MAX_AGE_S, hot_coin_threshold",
        "from maxpane_dashboard.data.surf_addresses import ANNOUNCE, DEV_WALLET, OPS_WALLET",
        "from maxpane_dashboard.data.surf_models import CHANNEL_KINDS",
    ]
    assert sig.CHANNEL_KINDS is surf_models.CHANNEL_KINDS
    assert "CHANNEL_KINDS: tuple[str, ...] = (" not in _code_only(_MODULE_SOURCE)


def test_no_live_value_is_hardcoded():
    """CLAUDE.md rule 4: parity, supply, pool composition and burn totals are read.

    The numbers that appear in this module are structural (24 h, 48 columns,
    percent) — never a measured one.
    """
    code = _code_only(_MODULE_SOURCE)
    for measured in ("2376731", "2,376,731", "0.7074", "58849", "33.0", "1148", "2000"):
        assert measured not in code, measured


def test_public_surface_is_the_frozen_one():
    for name in (
        "decode_utf8_calldata", "classify_channel_tx", "parity_pct", "build_signals",
        "FIRED_TTL_S", "SIGNAL_NAMES", "SIGNAL_OUTPUT_KEYS", "READING_KEYS",
    ):
        assert name in sig.__all__, name
        assert hasattr(sig, name), name
    assert sig.FIRED_TTL_S == 86400


def test_signal_output_keys_match_the_prd_naming():
    """PRD §5: ``sig_{name}_{state,detail,age_s}`` for all nine detectors."""
    assert len(sig.SIGNAL_OUTPUT_KEYS) == 27
    assert sig.SIGNAL_OUTPUT_KEYS[:3] == ("sig_post_state", "sig_post_detail", "sig_post_age_s")
    assert set(sig.SIGNAL_OUTPUT_KEYS) == {
        f"sig_{name}_{field}"
        for name in ("post", "lp", "gate", "deploy", "bridge", "burn", "decoy", "burnready", "hot")
        for field in ("state", "detail", "age_s")
    }


def test_every_state_value_is_one_of_the_four():
    """No detector may invent a fifth state string (PRD §5)."""
    for _name, expected_state, base_overrides, overrides, _detail in MATRIX:
        out, _ = sig.build_signals(_baseline(**base_overrides), _readings(**overrides), NOW)
        for key, value in out.items():
            if key.endswith("_state"):
                assert value in ("ok", "watch", "fired", None), (key, value)


def test_details_fit_the_signals_panel():
    """Every freshly-built detail stays inside a plausible row width.

    The panel gets ~55 columns at the pinned full-layout width; a longer detail
    would leave the panel wearing a permanent ``‹ widen`` marker (the FWA
    buy-gate footnote lesson).  The budget covers what a detector *builds*; the
    composed ``… · last: …`` form deliberately exceeds it when both halves are
    long, and truncating that is the widget's call, not this module's.
    """
    for _name, _state, base_overrides, overrides, _detail in MATRIX:
        out, _ = sig.build_signals(_baseline(**base_overrides), _readings(**overrides), NOW)
        for key, value in out.items():
            if key.endswith("_detail"):
                assert len(value) <= 55, (key, len(value), value)
