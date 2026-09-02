"""The surf capture set — the one source material, and the facts it pins.

Every surf work package derives its test data from ``tests/fixtures/surf/captures/``:
real keyless payloads (Blockscout REST v2, GeckoTerminal, DexScreener) fetched on
2026-08-08.  Two things are asserted here and nowhere else:

1.  The captures are committed, readable, keyless and read-only.
2.  Every number a later work package hardcodes is recomputed *from the capture* —
    the burn total, the poisoning rows, the holder disagreement, the parity spread,
    the nonce ladder.  A re-capture that moves one of them fails here, once.

WP0 commits no fixture file.  Each consuming work package owns a subdirectory of
``tests/fixtures/surf/`` (``client/``, ``signals/``, …); the root-directory guard
below is what keeps those from colliding with each other's globs.

No network: this module reads files only.
"""

from __future__ import annotations

import json

from tests.surf_fixtures import CAPTURES, SURF_FIXTURES


def test_captures_are_committed_and_readable() -> None:
    names = {p.name for p in CAPTURES.iterdir()}
    assert "README.md" in names, "the capture set must document its own provenance"
    json_files = sorted(CAPTURES.glob("*.json"))
    assert len(json_files) == 29
    for path in json_files:
        assert json.loads(path.read_text(encoding="utf-8")) is not None, path.name


def test_the_fixtures_root_holds_directories_only() -> None:
    """Ownership rule: WP0 owns ``captures/`` and every other work package owns its
    own subdirectory.  A loose ``*.json`` at the root is a file with no owner, and
    it is how one WP's slice lands in another WP's glob and turns its suite red in
    a file it may not edit."""
    loose = sorted(p.name for p in SURF_FIXTURES.iterdir() if p.is_file())
    assert loose == [], f"put these in a per-work-package subdirectory: {loose}"


def test_no_capture_carries_an_api_key() -> None:
    """Hard constraint: every source is keyless.  A captured URL with a key in it
    would mean the payload cannot be re-fetched by someone who installed the app."""
    for path in sorted(CAPTURES.iterdir()):
        text = path.read_text(encoding="utf-8", errors="replace").lower()
        for banned in ("api_key=", "apikey=", "x-api-key", "authorization:"):
            assert banned not in text, f"{path.name} contains {banned}"


# ---------------------------------------------------------------------------
# the announcement channel — calldata IS the message
# ---------------------------------------------------------------------------

from datetime import datetime  # noqa: E402

import pytest  # noqa: E402

from tests.surf_fixtures import capture  # noqa: E402

#: The three Blockscout address transaction pages.
TX_CAPTURES = (
    "announce_eth_txs.json",
    "wallet_eth_txs_page1.json",
    "ops_eth_txs.json",
)

ANNOUNCE = "0x200E710aCAA6A93bbc77146026328C40F1d60fB1"
DEV = "0x047F606fD5b2BaA5f5C6c4aB8958E45CB6B054B7"
OPS = "0xE764dA9bDeA91d845AAc2C7D53A8DfE59A369095"
NFPM = "0xC36442b4a4522E871399CD717aBDD847Ab11FE88"
BURN_EXECUTOR = "0x2EC59BEd2fB9deE447bbEC6e3BCA249782C9B88B"
IMD = "0xD34a99Bc0f67aE1bbd63C660e6d0b0dd03E263B7"
ZERO = "0x0000000000000000000000000000000000000000"


def body(row: dict) -> str:
    """The message a channel transaction carries, or ``UnicodeDecodeError``."""
    return bytes.fromhex(row["raw_input"][2:]).decode("utf-8")


def one(rows: list[dict], prefix: str, key: str = "hash") -> dict:
    """Exactly one row whose ``key`` starts with ``prefix``.

    Not a dict index: a dict would silently keep the last match, so a hash that
    stopped being unique after a re-capture would pick a different row than the
    comment above it claims.
    """
    matches = [r for r in rows if r[key].startswith(prefix)]
    assert len(matches) == 1, f"{prefix} matched {len(matches)} rows"
    return matches[0]


def rows_of(name: str) -> list[dict]:
    """Blockscout serves some captures bare and some wrapped in ``items``."""
    payload = capture(name)
    return payload["items"] if isinstance(payload, dict) else payload


def test_the_nonce_ladder() -> None:
    """The live counters every fast-tier read is compared against are the highest
    committed nonce + 1: announce 13 -> 14, dev 2349 -> 2350, ops 37 -> 38.  Any
    WP that fakes an ``eth_getTransactionCount`` response derives it from here."""
    channel = capture("announce_eth_txs.json")
    assert len(channel) == 21
    assert max(r["nonce"] for r in channel if r["from"]["hash"] == ANNOUNCE) == 13
    dev_rows = capture("wallet_eth_txs_page1.json")
    assert len(dev_rows) == 30
    assert max(r["nonce"] for r in dev_rows if r["from"]["hash"] == DEV) == 2349
    ops_rows = capture("ops_eth_txs.json")
    assert len(ops_rows) == 50
    assert max(r["nonce"] for r in ops_rows if r["from"]["hash"] == OPS) == 37


def test_the_register_call_is_the_only_non_utf8_body() -> None:
    """Signal 4 (NEW DEPLOY) keys on this shape: an outbound *contract call* from
    the channel whose calldata is ABI, not text.  Every other body decodes, which
    is what makes ``decode_utf8_calldata``'s failure path meaningful."""
    channel = capture("announce_eth_txs.json")
    undecodable = []
    for row in channel:
        try:
            body(row)
        except UnicodeDecodeError:
            undecodable.append(row["hash"])
    assert len(undecodable) == 1
    reg = one(channel, "0xa4ce159e5100")
    assert reg["hash"] == undecodable[0]
    assert reg["to"]["hash"] == "0x8004A169FB4a3325136EB29fA0ceB6D2e539a432"
    assert reg["raw_input"].startswith("0xf2c298be")  # register(string)


def test_the_funding_tx_and_the_paid_reply() -> None:
    """The permissionless-channel hazard, as data: the dev's own funding tx and a
    stranger's 1e13-wei begging tx sit in the same list as the posts."""
    channel = capture("announce_eth_txs.json")
    funding = one(channel, "0x632f5dc3e5aa")
    assert funding["from"]["hash"] == DEV and funding["to"]["hash"] == ANNOUNCE
    assert funding["raw_input"] == "0x" and funding["value"] == "54000000000000000"
    reply = one(channel, "0xd52c857d4df0")
    assert reply["from"]["hash"] != ANNOUNCE
    assert reply["value"] == "10000000000000"


def test_message_bodies_carry_the_typography_that_breaks_layout() -> None:
    channel = capture("announce_eth_txs.json")
    hook = body(one(channel, "0x0b72b4640117"))
    assert len(hook) == 219
    assert "\n" in hook and "—" in hook and "’" in hook
    spec = body(one(channel, "0xc189351772cb"))
    assert len(spec) == 952  # the long body the feed must truncate at narrow tiers


def test_no_captured_message_contains_a_markup_bracket() -> None:
    """Why every markup-hostile test vector in this plan set is synthetic and built
    inline by the WP that needs it: the channel is permissionless, but nobody has
    used it to post Textual markup *yet*.  If this ever fails, a real vector
    exists — slice it into that WP's directory and say so in its provenance."""
    for row in capture("announce_eth_txs.json"):
        try:
            text = body(row)
        except UnicodeDecodeError:
            continue
        assert "[" not in text, row["hash"]


# ---------------------------------------------------------------------------
# dev wallet — the activity feed's raw material
# ---------------------------------------------------------------------------


def test_dev_wallet_page_landmarks() -> None:
    rows = {r["hash"][:14]: r for r in capture("wallet_eth_txs_page1.json")}
    seaport = rows["0x5b4d1b4416bb"]        # the dev buying his own collection
    assert seaport["to"]["name"] == "Seaport"
    assert seaport["value"] == "363898900000000000"
    assert rows["0xcfb8f6e2c733"]["method"] == "bridgeToBaseBurnReceiver"
    claim = rows["0x139d860ed62f"]          # FWA income, NOT IMD economics
    assert claim["to"]["name"] == "Splitter" and claim["method"] == "claim"
    assert rows["0xdbfc446490ec"]["to"]["hash"] == (
        "0x58239Ad01D72811F179bAE08983F95Ac30274e55"   # swept ~1 minute later
    )
    stamps = [r["timestamp"] for r in rows.values()]
    assert min(stamps).startswith("2026-07-27") and max(stamps).startswith("2026-08-08")


def test_no_captured_transaction_creates_a_contract() -> None:
    """Documents why every NEW DEPLOY vector is synthetic and inline: none of the
    101 captured transactions carries ``created_contract``."""
    total = 0
    for name in TX_CAPTURES:
        rows = capture(name)
        total += len(rows)
        assert all(r.get("created_contract") is None for r in rows), name
    assert total == 101


def test_the_only_real_deploy_evidence_is_the_token_info_capture() -> None:
    """Whatever a later WP builds its flagged-synthetic deploy row from, these two
    values are the real ones and must be reused rather than invented."""
    info = capture("imd_info.json")
    assert info["creation_transaction_hash"] == (
        "0xb2e2587f18b440f2c492d911566cb979d4ec477dd69824d9ac17bdae2608704b"
    )
    assert info["creator_address_hash"] == DEV


# ---------------------------------------------------------------------------
# ops wallet — the LP choreography and the live poisoning rows
# ---------------------------------------------------------------------------


def test_the_lp_add_choreography_is_present_and_ordered() -> None:
    """PRD §11.2: bridge-in -> approve -> add, inside eight minutes on 2026-08-07."""
    rows = {r["hash"][:14]: r for r in capture("ops_eth_txs.json")}
    inbound = rows["0xd37239cfdbc1"]   # 33.693 ETH from a CEX hot wallet, 04:15:47
    approve = rows["0x0031c5c8cee0"]   # approve(IMD) to the NFPM,          04:22:23
    add = rows["0x90a0f8e2b039"]       # multicall into position 1167726,   04:23:23
    assert inbound["timestamp"] < approve["timestamp"] < add["timestamp"]
    assert inbound["to"]["hash"] == OPS
    assert inbound["value"] == "33693247247435751553"
    assert approve["method"] == "approve" and approve["to"]["hash"] == IMD
    assert add["to"]["hash"] == NFPM
    assert add["value"] == "33252659725872729307"
    assert add["method"] == "multicall"


def test_the_two_real_fee_sinks_received_real_eth() -> None:
    rows = {r["hash"][:14]: r for r in capture("ops_eth_txs.json")}
    assert rows["0x4628e535ea91"]["to"]["hash"] == (
        "0xF3084Bc7380D2dEfaA5bB42DCA6F517424D60eE6"
    )
    assert rows["0x4628e535ea91"]["value"] == "1428629183776324443"
    assert rows["0xed46d5f37715"]["to"]["hash"] == (
        "0x61CC704c7A5B7071c7B3f4Cc09A9CBC86373f14E"
    )
    assert rows["0xed46d5f37715"]["value"] == "300000000000000000"


def test_the_four_poisoning_rows_are_one_gwei_inbound_from_lookalikes() -> None:
    """Live address poisoning, as captured.  Every WP that renders a counterparty
    must drop these: inbound dust from senders that are not the dev wallets."""
    from maxpane_dashboard.data.surf_addresses import KNOWN_LABELS

    poison = [r for r in capture("ops_eth_txs.json") if r["value"] == "1000000000"]
    assert len(poison) == 4
    senders = {r["from"]["hash"].lower() for r in poison}
    assert senders == {
        "0x61ccfd5d33f0f27a2cd5acb558d9281b110df14e",
        "0xf3083828702c1989710ceca517412071c2f60ee6",
        "0xf30875988b99489ac71ec2f5069de0dd80b70ee6",
    }
    assert all(r["to"]["hash"] == OPS for r in poison)
    assert not senders & set(KNOWN_LABELS)


def test_each_spoof_shares_a_prefix_and_suffix_with_its_target() -> None:
    """This is why a truncated address must never be styled as trusted.

    The spoof set is derived from the captures, not typed in: every
    counterparty of the ops wallet's ETH-tx and token-transfer history that
    is *not* in ``KNOWN_LABELS`` is checked for a display-truncation
    collision (first 6 / last 4 characters, case-folded) against the two
    real fee-sink targets — imported from ``surf_addresses``, never
    re-typed.  This naturally finds all of them, including a lookalike that
    only shows up in the token-transfer capture (a fake outbound "ĖTḨ"
    transfer to a second address imitating ``LP_FEE_SINK_B``), not just the
    three 1-gwei inbound rows in the tx capture.
    """
    from maxpane_dashboard.data.surf_addresses import (
        KNOWN_LABELS,
        LP_FEE_SINK_A,
        LP_FEE_SINK_B,
    )

    targets = (LP_FEE_SINK_A.lower(), LP_FEE_SINK_B.lower())

    counterparties: set[str] = set()
    for name in ("ops_eth_txs.json", "ops_eth_token_transfers.json"):
        for row in rows_of(name):
            for side in ("from", "to"):
                party = (row.get(side) or {}).get("hash")
                if party:
                    counterparties.add(party.lower())

    spoofs_by_target: dict[str, set[str]] = {target: set() for target in targets}
    for addr in counterparties:
        if addr in KNOWN_LABELS:
            continue
        for target in targets:
            if addr[:6] == target[:6] and addr[-4:] == target[-4:]:
                spoofs_by_target[target].add(addr)

    # Not vacuous: both real fee sinks are actively being imitated, and the
    # collision property holds for every address the capture scan found.
    for target, spoofs in spoofs_by_target.items():
        assert spoofs, f"no captured lookalike collides with {target}"
        for spoof in spoofs:
            assert spoof[:6] == target[:6] and spoof[-4:] == target[-4:]

    # 3 senders in the ETH-tx poisoning rows + the token-transfer lookalike.
    # A lower bound, not an exact count that could exclude a real one found
    # later — the point is that a re-capture may only ever add spoofs here.
    all_spoofs = {addr for spoofs in spoofs_by_target.values() for addr in spoofs}
    assert len(all_spoofs) >= 4


# ---------------------------------------------------------------------------
# the IMD transfer ledger — burns, OFT mints, homoglyph tokens
# ---------------------------------------------------------------------------


def test_burn_ledger_sums_to_the_researched_total() -> None:
    """PRD §1's "~58,849 IMD".  ``imd_burned_cum`` is computed from this ledger,
    never typed in: 12039.394018716332754656 (2026-05-16) + 31064 (07-31) +
    15745 (08-05)."""
    burns = [
        r
        for r in rows_of("ops_eth_token_transfers.json")
        if (r.get("to") or {}).get("hash") == BURN_EXECUTOR
    ]
    assert len(burns) == 3
    total = sum(int(r["total"]["value"]) for r in burns)
    assert total == 58_848_394_018_716_332_754_656
    assert total / 10**18 == pytest.approx(58_848.394_018_716_33, rel=1e-12)


def test_bridge_in_mints_come_from_the_zero_address() -> None:
    """Signal 5 (BRIDGE STAGE): OFT mints to a dev wallet, minutes before the add.

    The token filter is load-bearing — a spoof token also mints from ``0x0`` in
    this same capture, so a filter on ``from == 0x0`` alone counts three.
    """
    rows = rows_of("ops_eth_token_transfers.json")
    from_zero = [r for r in rows if (r.get("from") or {}).get("hash") == ZERO]
    assert len(from_zero) == 3
    mints = [r for r in from_zero if r["token"]["address_hash"] == IMD]
    assert len(mints) == 2
    assert {int(r["total"]["value"]) for r in mints} == {
        114_366_899_256_000_000_000_000,
        10_000_000_000_000_000_000_000,
    }
    assert all(r["timestamp"].startswith("2026-08-07T04:") for r in mints)
    # LayerZero OFT sharedDecimals is 6, so every bridged amount is a multiple of
    # 1e12 wei.  A decoder that loses precision breaks this immediately.
    assert all(int(r["total"]["value"]) % 10**12 == 0 for r in mints)


def test_homoglyph_token_symbols_live_in_this_wallets_real_history() -> None:
    """These strings are why ``safe_markup`` runs on token symbols too — and why a
    symbol renderer must survive ``None``."""
    symbols = {r["token"]["symbol"] for r in rows_of("ops_eth_token_transfers.json")}
    # Escapes, not glyphs: an editor that normalises these on save would make the
    # assertion pass against a different string than the one on chain.
    assert "\u0116T\u1e28" in symbols                    # ĖTḨ
    assert "\u200aU\u0405D\u0421\u200a" in symbols     # hair spaces, Cyrillic Ѕ/С
    assert "USD\u0421" in symbols                        # Cyrillic С, unpadded
    assert None in symbols                                # a row with no symbol at all


# ---------------------------------------------------------------------------
# market — DexScreener displays, GeckoTerminal cross-checks
# ---------------------------------------------------------------------------


def test_dexscreener_imd_pair_values() -> None:
    pair = capture("dexscreener_imd.json")["pairs"][0]
    assert pair["baseToken"]["address"] == IMD
    assert pair["pairAddress"] == "0xD6A822D028bbf7b6EDfA1533e110Ee40c08551d9"
    assert pair["labels"] == ["v3"]
    assert pair["priceUsd"] == "0.7074"
    assert pair["priceChange"]["h24"] == 30.89
    assert pair["volume"]["h24"] == 244178
    assert pair["liquidity"] == {"usd": 548701.21, "base": 388421, "quote": 142.7067}


def test_geckoterminal_serves_a_two_renames_stale_name() -> None:
    """PRD §6.3: indexer names are display fallbacks.  DexScreener's are current;
    GeckoTerminal's are two renames behind, so its strings are barred at the
    client and only its numbers are used."""
    attrs = capture("geckoterminal_imd.json")["data"]["attributes"]
    assert attrs["name"] == "Vibe Coins"
    assert attrs["symbol"] == "VIBE"
    assert attrs["price_usd"] == "0.7127337345"
    base = capture("dexscreener_imd.json")["pairs"][0]["baseToken"]
    assert base["name"] == "Identity.md" and base["symbol"] == "IMD"


def test_parity_is_computable_from_the_two_market_captures() -> None:
    imd = float(capture("dexscreener_imd.json")["pairs"][0]["priceUsd"])
    fp = float(capture("dexscreener_fp.json")["pairs"][0]["priceUsd"])
    assert imd == 0.7074 and fp == 0.7274
    assert (imd / fp - 1.0) * 100.0 == pytest.approx(-2.749518834204012, rel=1e-12)


def test_the_two_indexers_disagree_by_under_one_percent() -> None:
    """Cross-check discipline: they are close, so a wild divergence later means one
    source is broken, not that the market moved."""
    dex = float(capture("dexscreener_imd.json")["pairs"][0]["priceUsd"])
    gecko = float(capture("geckoterminal_imd.json")["data"]["attributes"]["price_usd"])
    assert abs(dex - gecko) / dex < 0.01


def test_the_pool_price_is_derivable_from_the_capture() -> None:
    """Any synthetic ``slot0`` a later WP encodes derives its sqrtPriceX96 from
    this number, not from a remembered one (open issue 12).

    token0 = WETH (0xC02a…) < token1 = IMD (0xD34a…) by address order, so the pool
    price is IMD per WETH — the inverse of DexScreener's ``priceNative``.  Getting
    that direction backwards is the classic v3 decoding bug.
    """
    pair = capture("dexscreener_imd.json")["pairs"][0]
    assert pair["priceNative"] == "0.0003686"          # WETH per IMD
    assert 1 / float(pair["priceNative"]) == pytest.approx(
        2712.9679869777538, rel=1e-12
    )


# ---------------------------------------------------------------------------
# Blockscout token + counters
# ---------------------------------------------------------------------------


def test_imd_supply_and_the_two_disagreeing_holder_counts() -> None:
    """Documented, not smoothed over: ``/tokens`` says 1148, ``/counters`` says
    1132.  Both are Blockscout; the hero renders one and says which."""
    token = capture("imd_token.json")
    assert token["address_hash"] == IMD
    assert token["total_supply"] == "2376731868679000000000000"
    assert int(token["total_supply"]) / 10**18 == pytest.approx(
        2_376_731.868679, rel=1e-12
    )
    assert token["symbol"] == "IMD" and token["name"] == "Identity.md"
    assert token["holders_count"] == "1148"
    assert capture("imd_counters.json")["token_holders_count"] == "1132"
    assert capture("imd_counters.json")["transfers_count"] == "30441"
    # sharedDecimals = 6, so mainnet supply is always a multiple of 1e12 wei.
    assert int(token["total_supply"]) % 10**12 == 0


def test_bridged_share_is_computable_and_matches_the_research() -> None:
    imd = int(capture("imd_token.json")["total_supply"])
    fp = int(capture("fp_base_token.json")["total_supply"])
    assert fp == 7_195_584_582_643_610_841_108_662
    assert imd / fp * 100 == pytest.approx(33.030420827960086, rel=1e-12)


def test_idmd_collection_counters() -> None:
    token = capture("identity_token.json")
    assert token["total_supply"] == "2000"
    assert token["type"] == "ERC-721"
    assert token["holders_count"] == "667"
    counters = capture("identity_counters.json")
    assert counters["token_holders_count"] == "667"
    assert counters["transfers_count"] == "7411"


# ---------------------------------------------------------------------------
# IDMD transfers — the page that is not a day
# ---------------------------------------------------------------------------


def _ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def test_the_idmd_transfer_page_is_not_a_day() -> None:
    """Guards against counting *one page* as transfers/24h: the captured page spans
    2026-08-07T23:05:35 .. 2026-08-08T09:51:59 — under eleven hours.

    WP1.8's ``_count_transfers_24h()`` is what makes that safe: live, the endpoint
    paginates, and the count follows cursors until it sees a row older than
    ``now - 86400`` — answering ``None`` if the page budget runs out first, because
    a lower bound rendered as a daily rate is a wrong number.  Not a ``/counters``
    delta across refreshes: that measures the gap between two observations, so it
    is either a 60-second sample scaled up or a number that does not exist until
    the dashboard has run for a day."""
    stamps = sorted(r["timestamp"] for r in rows_of("identity_transfers_page1.json"))
    assert len(stamps) == 25
    assert (_ts(stamps[-1]) - _ts(stamps[0])).total_seconds() < 11 * 3600


def test_no_idmd_transfer_row_carries_a_price() -> None:
    """Realized prices live in Seaport ``OrderFulfilled`` logs, not here — which is
    why ``nft_last_sales[].eth`` has no source in this capture set (open issue 2)."""
    rows = rows_of("identity_transfers_page1.json")
    assert all(r["token"]["symbol"] == "IDMD" for r in rows)
    assert all(r["token_type"] == "ERC-721" for r in rows)
    assert all(set(r["total"]) == {"token_id", "token_instance"} for r in rows)
    assert all("value" not in r for r in rows)
    seaport = [r for r in rows if (r["method"] or "").startswith(("fulfill", "match"))]
    assert len(seaport) == 24


# ---------------------------------------------------------------------------
# suite-wide guards
# ---------------------------------------------------------------------------


def test_the_capture_inventory_is_complete() -> None:
    """29 JSON captures + the README + the agent card.  A later work package
    deleting one, or quietly re-capturing under a new name, fails loudly here."""
    assert {p.name for p in CAPTURES.iterdir()} == {
        "README.md",
        "agent_card_ipfs.txt",
        "announce_eth_info.json",
        "announce_eth_txs.json",
        "dexscreener_fp.json",
        "dexscreener_imd.json",
        "ens_surfsurf.json",
        "eth_search_frenpet.json",
        "fp_base_token.json",
        "geckoterminal_fp.json",
        "geckoterminal_imd.json",
        "identity_contract.json",
        "identity_counters.json",
        "identity_holders_page1.json",
        "identity_info.json",
        "identity_instances_sample.json",
        "identity_token.json",
        "identity_transfers_page1.json",
        "imd_contract.json",
        "imd_counters.json",
        "imd_holders.json",
        "imd_info.json",
        "imd_token.json",
        "ops_eth_info.json",
        "ops_eth_token_transfers.json",
        "ops_eth_txs.json",
        "reg_contract.json",
        "reg_info.json",
        "wallet_eth_info.json",
        "wallet_eth_token_transfers_page1.json",
        "wallet_eth_txs_page1.json",
    }


def test_the_capture_set_stays_small() -> None:
    """Provenance, not an archive.  1.6 MB on 2026-08-08; the captures were already
    trimmed at capture time (paginated lists cut to one page, strings over 4000
    chars end in ``...TRUNCATED``).  A re-capture that forgets that trimming shows
    up here before it shows up in a clone."""
    total = sum(p.stat().st_size for p in CAPTURES.rglob("*") if p.is_file())
    assert total < 4_000_000, f"capture set has grown to {total} bytes"


#: Substrings that would mean a shipped module is reaching into the test
#: fixtures at runtime.
_CAPTURE_PATH_MARKERS = ("fixtures/surf", "surf_fixtures")


def test_nothing_shipped_reads_the_captures() -> None:
    """``tests/fixtures/`` is test-only material and is not in the wheel, so a
    runtime read would be a ``FileNotFoundError`` on every installed copy.

    **Asked of the module's runtime strings, not of its text** (2026-09-01).
    This walked the raw source for the two markers, which is a different --
    and wrong -- question: a shipped module that *documents where a vendored
    constant was captured from* is not reading anything, and one that builds
    the path as ``"fixtures" + "/surf"`` is, while a substring scan gets both
    backwards.

    It went red for exactly the first reason: ``data/surf_manager.py``'s
    vendored Sepolia hook carries a ``#:`` block naming the WP1 corpus the
    address was captured with -- provenance for a constant, which is the
    thing this repo asks for everywhere else. Deleting that comment to keep a
    text scan green would have traded a real record for a fake signal.

    So the check parses the module and looks at **string constants only**.
    Comments are not in the AST at all, so a provenance note passes without
    an exemption list to maintain; a docstring is an AST constant and is
    still inert, so it is skipped by position rather than by guesswork; and
    an actual path -- in a ``Path(...)``, an ``open(...)``, a module-level
    constant, anywhere a value can be used -- is caught exactly as before.
    ``surf_fixtures`` is additionally checked as an *imported name*, which is
    how a shipped module would really reach the helper and which the string
    scan could not see at all.
    """
    import ast

    package = SURF_FIXTURES.parents[2] / "maxpane_dashboard"
    scanned = 0
    for path in package.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        scanned += 1

        # Docstrings are inert text; every other string constant is a value
        # the module can act on.
        docstrings = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                 ast.AsyncFunctionDef)):
                first = node.body[0] if node.body else None
                if (
                    isinstance(first, ast.Expr)
                    and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)
                ):
                    docstrings.add(id(first.value))

        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in docstrings
            ):
                for marker in _CAPTURE_PATH_MARKERS:
                    assert marker not in node.value, (
                        f"{path} carries {marker!r} in a runtime string -- "
                        "tests/fixtures/ is not in the wheel"
                    )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    assert "surf_fixtures" not in alias.name, path
            elif isinstance(node, ast.ImportFrom):
                assert "surf_fixtures" not in (node.module or ""), path
                for alias in node.names:
                    assert "surf_fixtures" not in alias.name, path

    assert scanned > 50, (
        f"only {scanned} modules were parsed -- the walk found nothing and "
        "proved nothing"
    )
