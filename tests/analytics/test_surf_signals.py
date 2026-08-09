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

# SYNTHETIC: no hooked IMD v4 pool exists yet — all 19 live ones have
# hooks=0x0.  The hook address is the dev's *existing* Vibecoins launchpad
# hook, used here only to give the row a realistic non-zero value.
HOOKLESS_POOL = {
    "ts": 1_786_000_000.0,
    "tx_hash": "0x" + "b0" * 32,
    "hooks": "0x0000000000000000000000000000000000000000",
}
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
    # OPEN and NEW DEPLOY; WP2.7 appends BRIDGE STAGE and BURN, completing the
    # six-name PRD §3 roster.
    assert sig.SIGNAL_NAMES == ("post", "lp", "gate", "deploy", "bridge", "burn")
    assert len(sig.SIGNAL_OUTPUT_KEYS) == 18


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


# --- 2. LP MIGRATION --------------------------------------------------------
#
# He promised onchain to announce before moving the LP (nonce 8), so the
# decrease is the act itself.  An *increase* is movement worth watching but is
# the opposite event -- that is exactly what 2026-08-07 was.


def test_liquidity_holding_is_ok():
    assert _sig("lp", _baseline(), _readings()) == ("ok", "liquidity holds", None)


def test_liquidity_decrease_fires():
    assert _sig("lp", _baseline(), _readings(lp_liquidity=677_000_000_000)) == (
        "fired", "LIQUIDITY OUT -32.3%", 0.0
    )


def test_liquidity_increase_is_a_watch_not_a_fire():
    """The 2026-08-07 add: 33 ETH *into* the pool, not out of it."""
    assert _sig("lp", _baseline(), _readings(lp_liquidity=LP_LIQUIDITY_AFTER_ADD)) == (
        "watch", "LP added +33.0%", None
    )


def test_any_frenpet_eth_activity_is_a_watch():
    """29 lifetime txs on that wallet: any nonce move is signal (PRD §3 #2)."""
    assert _sig("lp", _baseline(), _readings(ops_nonce=37)) == (
        "watch", "frenpet.eth active · nonce 37", None
    )


def test_hooked_v4_initialize_fires_as_the_launch():
    """SYNTHETIC event, real rule: currency IMD and hooks != 0x0 IS the launch."""
    state, detail, age = _sig("lp", _baseline(), _readings(v4_hook_pools=[HOOKED_POOL]))
    assert state == "fired"
    assert detail == "V4 LAUNCH · hooks 0xd6C6d48e…CF7A44"
    assert age == pytest.approx(NOW - HOOKED_POOL["ts"])


def test_hookless_pools_are_noise():
    """All 19 live IMD v4 pools are third-party and hookless.

    Firing on them would make the flagship detector permanently wrong on day
    one, and would advance the baseline past a real hooked pool.
    """
    state, detail, _ = _sig("lp", _baseline(), _readings(v4_hook_pools=[HOOKLESS_POOL]))
    assert state == "ok"
    assert detail == "liquidity holds"
    _, advanced = sig.build_signals(_baseline(), _readings(v4_hook_pools=[HOOKLESS_POOL]), NOW)
    assert advanced["v4_tx"] == ""


def test_lp_outage_is_none():
    assert _sig(
        "lp",
        _baseline(),
        _readings(lp_liquidity=None, ops_nonce=None, v4_hook_pools=None),
    ) == (None, "LP state unavailable", None)


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
