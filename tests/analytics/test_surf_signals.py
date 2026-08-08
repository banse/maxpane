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
    assert sig._short_addr(None) == ""
