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
