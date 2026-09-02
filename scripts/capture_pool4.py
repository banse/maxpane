#!/usr/bin/env python3
"""Keyless, read-only capture of the IMD **pool4** deployment into committed fixtures.

WP1 of ``docs/surf_pool4_implementation_plan.md``.  Everything the surf ``p``
view will ever parse is captured here, once, as raw JSON, so that no test in
this repo ever opens a socket.

    python3 scripts/capture_pool4.py --dry-run          # replay + validate, no socket
    python3 scripts/capture_pool4.py --capture sepolia-state
    python3 scripts/capture_pool4.py --capture flow-logs
    python3 scripts/capture_pool4.py --capture pool-slot0
    python3 scripts/capture_pool4.py --capture announce
    python3 scripts/capture_pool4.py --capture mainnet-absent
    python3 scripts/capture_pool4.py --capture all
    python3 scripts/capture_pool4.py --synthesize       # the adversarial corpora
    python3 scripts/capture_pool4.py --manifest         # rewrite MANIFEST.json

Deliberate properties, each a constraint rather than a preference:

* **Read-only and keyless.**  ``eth_call`` / ``eth_getLogs`` / ``eth_getCode`` /
  ``eth_blockNumber`` / ``eth_getBlockByNumber`` and Blockscout GETs.  It never
  builds calldata for a state change, never signs, never asks for a key.  The
  hook's ``settleClaims()`` / ``rebalance()`` / ``setCapFloor()`` selectors are
  recorded in this file as *evidence of the recovered interface* and are never
  sent.
* **Stdlib only on the capture and replay paths.**  ``urllib`` and ``json``.
  ``--synthesize`` and the ``pool-slot0`` capture reach into the repo for
  ``data/keccak.py`` / ``data/surf_v4.py`` rather than re-implementing keccak or
  the v4 slot derivation, which CLAUDE.md forbids; both imports are lazy, so
  ``--dry-run`` needs nothing but the interpreter.
* **A real ``User-Agent``.**  publicnode answers HTTP 403 to python-urllib's
  default UA.  ``--self-test`` checks it first.
* **Every capture carries the request that produced it** in a sibling
  ``<name>.request.json``: URL, headers, the exact JSON-RPC body, and the
  id -> getter-name map.  A response with no request is not evidence.
* **Real captures are never hand-edited.**  The six-plus adversarial announce
  corpora ARE synthetic and say so in-file (``"synthetic": true``) with a
  ``note`` naming the attack each one encodes.
* ``--dry-run`` installs a socket guard that raises on any connection attempt,
  then loads, validates and replays every committed fixture.  That is this
  package's acceptance gate.

Measured 2026-09-01 while capturing (R8 in the plan: "Sepolia endpoint
availability is unmeasured"):

* ``https://ethereum-sepolia-rpc.publicnode.com`` — batches ``eth_call`` AND
  serves the hook's full archive ``eth_getLogs`` range.  Unlike its mainnet
  sibling it does **not** refuse archive logs.
* ``https://gateway.tenderly.co/public/sepolia`` — serves the same logs; HTTP
  429 on a 3-call ``eth_call`` batch immediately after.  Logs pool only.
* ``https://sepolia.drpc.org`` — HTTP 400 on a plain ``eth_blockNumber``.
* ``https://1rpc.io/sepolia`` — ``eth_getLogs`` capped at 50 blocks.
* ``https://rpc.sepolia.org`` — HTTP 404.
* ``https://endpoints.omniatech.io/v1/eth/sepolia/public`` — HTTP 521.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import pathlib
import socket
import sys
import urllib.error
import urllib.request

# --------------------------------------------------------------------------
# Where things live
# --------------------------------------------------------------------------

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "tests" / "fixtures" / "surf" / "pool4"

USER_AGENT = "maxpane-capture/1.0 (+https://pypi.org/project/maxpane)"

SEPOLIA_STATE_URL = "https://ethereum-sepolia-rpc.publicnode.com"
SEPOLIA_LOG_URL = "https://ethereum-sepolia-rpc.publicnode.com"
SEPOLIA_LOG_FALLBACK_URL = "https://gateway.tenderly.co/public/sepolia"
SEPOLIA_BLOCKSCOUT = "https://eth-sepolia.blockscout.com/api/v2"

MAINNET_STATE_URL = "https://ethereum-rpc.publicnode.com"
MAINNET_BLOCKSCOUT = "https://eth.blockscout.com/api/v2"

SEPOLIA_CHAIN_ID = 11155111
MAINNET_CHAIN_ID = 1

# --------------------------------------------------------------------------
# The cast.  docs/imd_pool4_mechanics.md is the research of record; these are
# transcribed from it and each was re-read live during the capture run.
# --------------------------------------------------------------------------

HOOK = "0xa1B997A9861B2b8aC17B4c615089cCC2a5416840"          # Sepolia launch 3
VAULT = "0x1600E14C663679c98B35B61e239F20792BB317cc"          # StakedIMD, verified
DRIPPER = "0x4dBE172254033aAC3a3374Fb10b422605B0B449B"        # RewardDripper, verified
TOKEN = "0xB37d54bC1F1d9271fc57D7E03192976baA39Cc82"          # IdentityMD Test
POOL_MANAGER = "0xE03A1074c86CFeDd5C142C4F04F1a1536e203543"   # Sepolia v4 canonical
POOL_ID = "0x6ec9cb73ed7cd8bb0ee08bcc69c86411d3f594dc716f302d8219b789dff37d37"
BURN_SINK = "0x000000000000000000000000000000000000dEaD"

HOOK_LAUNCH_1 = "0x1230007b24ADeC383B26CEaF3739E6D306016840"
HOOK_LAUNCH_2 = "0xCA0612FF8bC6298Dc8baFB7d40ACBb0d3eEaE840"

#: The announce channel EOA on mainnet.  ``data/surf_addresses.ANNOUNCE``.
ANNOUNCE = "0x200E710aCAA6A93bbc77146026328C40F1d60fB1"
#: Mainnet IMD.  The token a candidate hook must name to be adopted.
MAINNET_IMD = "0xD34a99Bc0f67aE1bbd63C660e6d0b0dd03E263B7"

#: The hook's deployment window on Sepolia, from the launch-3 log set.
FLOW_FROM_BLOCK = 11609600
FLOW_TO_BLOCK = 11610000
#: A compact window carrying a buy, a sell, a settlement and an accrual that is
#: not settled in its own transaction.
FLOW_MIXED_FROM = 11609700
FLOW_MIXED_TO = 11609760
#: Before the hook existed: swept, and genuinely quiet.
FLOW_EMPTY_FROM = 11605000
FLOW_EMPTY_TO = 11605100

# --------------------------------------------------------------------------
# The recovered interface.  Selectors are the FIRST FOUR BYTES OF THE CALLDATA
# ACTUALLY SENT in the 2026-09-01T15:05Z capture (captures/live/) and each one
# answered.  Nothing here is a guess.
# --------------------------------------------------------------------------

HOOK_GETTERS: dict[str, str] = {
    # state
    "token": "0xfc0c546a",
    "poolManager": "0xdc4c90d3",
    "owner": "0x8da5cb5b",
    "burnSink": "0x41becbce",
    "rewardsRecipient": "0xff2a7d30",
    "backstop": "0x7dea1817",
    "poolId": "0x3e0dc34e",
    "poolKey": "0x182148ef",
    "marketOpen": "0xc66bc046",
    "rebalanceEnabled": "0x81fdec27",
    # config
    "BPS_DENOMINATOR": "0xe1a45218",
    "rewardShareBps": "0x9124b5c7",
    "lpFee": "0x704ce43e",
    "capFloor": "0x6dd16b2c",
    "keeperReward": "0xa9ec75f6",
    # position
    "tickSpacing": "0xd0c93a7c",
    "tickLower": "0x59c4f905",
    "tickUpper": "0x55b812a8",
    "refTick": "0x7ac776be",
    "currentTick": "0x065e5360",
    "currentSqrtPriceX96": "0x47fd03d9",
    "positionLiquidity": "0x7211dc36",
    "ethInPool": "0x71d2cc5c",
    "tokensInPool": "0x40e1e4c7",
    # counters
    "totalBurned": "0xd89135cd",
    "totalRewarded": "0xaed29d07",
    "totalFeeToken": "0xb53cf8ac",
    "retainedEth": "0x9d3ec016",
    "lastClaimBlock": "0xa9d2293d",
    # the v4 permission struct, straight from the contract.  This is the
    # authority on the hook's flags; the address's low bits are a claim the
    # struct settles.
    "getHookPermissions": "0xc4e833ce",
}

#: Three selectors the launch-3 hook does NOT implement, chosen because the
#: imd.fun/pool4 teaser advertises a `bond` tab that no deployed contract
#: carries: exactly the "the mainnet hook is a different build" shape R1 warns
#: about.  Sending them produces a real revert from a real contract, which is
#: why `hook_state_partial` is a capture and not a hand-edit.
HOOK_ABSENT_GETTERS: dict[str, str] = {
    # keccak("bondTerms()")[:4], keccak("totalBonded()")[:4], keccak("bond()")[:4]
    "bondTerms": "0xde6efb31",
    "totalBonded": "0x44d96e95",
    "bond": "0x64c9ec6f",
}

VAULT_GETTERS: dict[str, str] = {
    "asset": "0x38d52e0f",
    "owner": "0x8da5cb5b",
    "paused": "0x5c975abb",
    "totalAssets": "0x01e1d114",
    "totalSupply": "0x18160ddd",
    "name": "0x06fdde03",
    "symbol": "0x95d89b41",
    "decimals": "0x313ce567",
    # NOTE: convertToAssets is NOT here, deliberately.  Its argument depends on
    # the vault's own decimals(), which must be READ, never assumed -- see
    # _vault_getters() below and AMENDMENT A17.
}

#: convertToAssets(uint256)
CONVERT_TO_ASSETS_SELECTOR = "0x07a2d13a"


def _convert_to_assets(shares: int) -> str:
    return CONVERT_TO_ASSETS_SELECTOR + format(shares, "064x")


def _vault_getters(decimals: int) -> dict[str, str]:
    """The vault round, with the share-price call sized to THIS vault.

    AMENDMENT A17 (2026-09-01).  The original capture asked
    ``convertToAssets(1e18)`` because 18 is what an ERC-20 usually is.  Solady's
    ``ERC4626`` reports ``asset decimals + _decimalsOffset()``, and StakedIMD
    sets the offset to 6, so ``decimals()`` is **24** and one whole share is
    1e24 units.  1e18 is therefore a MILLIONTH of a share, and the honest answer
    to that dishonest question (1_302_985_528_554) renders as 0.0000013 IMD per
    share: a vault that looks dead while its share price is 1.302986.

    The argument is built from the decimals the chain reports, in the same
    sweep, so a vault with a different offset is captured correctly without
    anyone editing this file.
    """
    g = dict(VAULT_GETTERS)
    g["convertToAssets"] = _convert_to_assets(10 ** decimals)
    # Kept deliberately, under a name that cannot be mistaken for a share
    # price: this is the wrong-argument answer, and having both in one fixture
    # is what lets a test prove the two differ by exactly 10**offset.
    g["convertToAssets_millionth_of_a_share"] = _convert_to_assets(10 ** 18)
    return g

DRIPPER_GETTERS: dict[str, str] = {
    "imd": "0xdd02e154",
    "vault": "0xfbfa77cf",
    "owner": "0x8da5cb5b",
    "dripRatePerSecond": "0x187f3334",
    "maxCatchupSeconds": "0x01e48edc",
    "minDripAmount": "0x1ac8b3bb",
    "keeperReward": "0xa9ec75f6",
    "lastDripAt": "0x98946200",
    "drippable": "0xd470b82c",
    "canDrip": "0x4f59d9d6",
}


def _balance_of(addr: str) -> str:
    return "0x70a08231" + "0" * 24 + addr.lower().replace("0x", "")


TOKEN_GETTERS: dict[str, str] = {
    "totalSupply": "0x18160ddd",
    "decimals": "0x313ce567",
    "symbol": "0x95d89b41",
    "name": "0x06fdde03",
    "balanceOf_dead": _balance_of(BURN_SINK),
    "balanceOf_dripper": _balance_of(DRIPPER),
    "balanceOf_vault": _balance_of(VAULT),
    "balanceOf_hook": _balance_of(HOOK),
}

#: topic0 -> what the operands provably are.  Three have no known pre-image;
#: they keep operand-shaped names, per the plan's "do not invent a signature".
TOPIC0_MAP: dict[str, str] = {
    # Four the mechanics doc does not list at all, recovered by keccak
    # pre-image search during this capture run and confirmed against the
    # deployment transactions that emitted them.
    "0x8be0079c531659141344cd1fd0a4f28419497f9722a3daafe3b4186f6b6457e0":
        "OwnershipTransferred(address,address)",
    "0x5f94feb4624474fb875ef3acdf106e9f8e1b7ad0881a6a86f1e67f67ccd4e5b4":
        "PoolInitialized(uint160,int24)",
    "0x4a16fcf994dd2b8d8fbfc45545d642ddf26debffd047664077e7d32726013e8d":
        "MarketOpened(uint128,uint256,uint256)",
    "0xa11f9f03282d5dbbf87eea2b08a2b19f333224fddc17402b016b8ae3021f8e9a":
        "RewardsRecipientUpdated(address,address)",
    "0xaf7c505ee772ec188af7067e1f73db08ab028e3d564273442b907742b9c41fa0":
        "FeeCollected(uint256,uint256)",
    "0x10ea71883ef0e28b7b04d488d5ffc5952921ddb354e9b56f9331956a80fc9bab":
        "ClaimsSettled(uint256,uint256,uint256)",
    "0xdeb5099d7943aa2b4c1142e5d53d2f7636aa8f7bd130ec79816f151572bcdf45":
        "FeesWithdrawn(address,uint256,uint256)",
    "0x0cbcc38bb40a7b0940c989eac5abd480ff9917c824c1fd6b2e38227d92c4c700":
        "KeeperRewardPaid(address,uint256)",
    "0x5da4124c44e7ab5ea52a261f5f3cb8e7dc215e9eaf017eadcefff627b8247b12":
        "Rebalanced(int24)",
    "0x32afb9555b0493ac0021ef7f6b122197e9e58510e694383410f667ec76e4f0fa":
        "UNRESOLVED accrual (uint128 liquidityRemoved, uint256 toBurn, "
        "uint256 toRewards, uint256 eth)",
    "0xa66e3643af3b5a570ea09b8d485f206950ff1ee042471a211388199518f539a6":
        "UNRESOLVED pool reserve (uint256 before, uint256 after)",
    "0xe3966151f83ca37a8d733ac53f8f5122134c74fc747f8ea857c2ba5e49f68b73":
        "UNRESOLVED backstop (int24,int24,uint128,uint256)",
    # Mainnet-only, 19 occurrences in the launch window, no pre-image found in
    # a 538,740-candidate sweep across two vocabularies.  Its two words are plainly TICKS and they
    # descend monotonically as the pool trades (73002 -> 72998 -> 72997 ->
    # 72993), so it is named for what its operands provably are.  Do not invent
    # a signature string for it.
    "0x73cd8288dc6e2d815bcc3fdbd71bdcc73cb3ad258d80587c5c90d8c85388cd54":
        "UNRESOLVED tick move (uint256 tickBefore, uint256 tickAfter)",
    # The three UNRESOLVED entries above survived a further 143,640-candidate
    # name x signature sweep on 2026-09-01 with no hit, on top of the ~45,000
    # the mechanics doc records.  They keep operand-shaped names; do not invent
    # a signature string for them.
    #
    # The mechanics doc also names a `0xbdf538ed...` "retired backstop" topic0
    # from an EARLIER launch.  It does not appear anywhere in launch 3's log
    # set, so its full 32-byte hash is not evidence this package holds and it
    # is deliberately NOT listed here with a guessed tail.
}

# --------------------------------------------------------------------------
# MAINNET -- pool4 went live 2026-09-02.  Additive: nothing here re-captures
# the Sepolia corpus, which other packages have tests standing on.
# --------------------------------------------------------------------------

MAINNET_HOOK = "0xc6c965bd164c483e87d0b550671798e9a3602840"
MAINNET_VAULT = "0x9efa934d9fad4ae28c998a40195646b965a97247"
#: NEW on mainnet.  No Sepolia counterpart, and the reason the vault is three
#: hops away instead of two.
MAINNET_DISTRIBUTOR = "0x9046739E1535B40EfBe6AB3f45d0024b690eCA30"
MAINNET_DRIPPER = "0xe6D3De6daEAf327fCA42745f1998FcD989e00884"
#: burnSink() on mainnet.  NOT 0x…dEaD -- see the identity warning below.
MAINNET_BURN_EXECUTOR = "0xe29386719C155B6847aD5a4E97C6674f10ffc750"
MAINNET_POOL_MANAGER = "0x000000000004444c5dc75cb358380d2e3de08a90"

MAINNET_LOG_RPCS = ("https://gateway.tenderly.co/public/mainnet",
                    "https://eth.drpc.org")

#: The operator's docs site, accepted as a CANDIDATE address source because the
#: announce channel has still not named this hook.  One operator's mutable
#: HTML: not consensus data, and the manifest says so.
DOCS_SITE_URL = "https://pool4.imd.fun/docs"

#: Two getters recovered from bytecode, in no public signature database.  Both
#: pre-images were CONFIRMED by keccak during this capture run, not guessed:
#: keccak("capDecayTokensPerDay()")[:4] == 0x55e62941 and
#: keccak("inventoryCap()")[:4] == 0xdb445ee8.
HOOK_CAP_GETTERS: dict[str, str] = {
    "capDecayTokensPerDay": "0x55e62941",
    "inventoryCap": "0xdb445ee8",
}

#: The Reward Distributor's recovered interface.  `vault()` is included
#: DELIBERATELY and is expected to REVERT: it is the call the old two-hop path
#: made, and its revert is what stops the walk.  A fixture that omitted it
#: could not replay the failure it exists to document.
DISTRIBUTOR_GETTERS: dict[str, str] = {
    "stakingBps": "0xe16314b5",
    "nftBps": "0xde6bb276",
    "dripper": "0x603ea03b",
    "asset": "0x38d52e0f",
    "owner": "0x8da5cb5b",
    "stakingEarned": "0x080348e4",
    "bondingEarned": "0x4985a39e",
    "nftEarned": "0x4c110e71",
    "heldBonding": "0x2915416e",
    "heldNft": "0x8d9f2fff",
    "vault": "0xfbfa77cf",
}


# --------------------------------------------------------------------------
# Transport.  Injectable so a test could drive it with a canned opener.
# --------------------------------------------------------------------------


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _open(req, timeout: int = 90):
    return urllib.request.urlopen(req, timeout=timeout)


def post_json(url: str, payload, *, opener=_open, timeout: int = 90):
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
    )
    with opener(req, timeout=timeout) as resp:
        return json.load(resp)


def get_json(url: str, *, opener=_open, timeout: int = 90):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with opener(req, timeout=timeout) as resp:
        return json.load(resp)


# --------------------------------------------------------------------------
# Fixture writing.  A fixture and its request sibling are written together or
# not at all.
# --------------------------------------------------------------------------


def write_pair(
    name: str,
    *,
    meta: dict,
    request: dict,
    response,
) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fixture = dict(meta)
    fixture["fixture"] = name
    fixture.setdefault("synthetic", False)
    fixture["response"] = response
    (OUT / f"{name}.json").write_text(
        json.dumps(fixture, indent=1, sort_keys=False) + "\n"
    )
    sibling = dict(request)
    sibling["fixture"] = name
    sibling["captured_at"] = fixture.get("captured_at")
    (OUT / f"{name}.request.json").write_text(
        json.dumps(sibling, indent=1, sort_keys=False) + "\n"
    )
    print(f"  wrote {name}.json + {name}.request.json")


def write_synthetic(name: str, payload: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    assert payload.get("synthetic") is True, name
    assert payload.get("note"), name
    payload = dict(payload)
    payload["fixture"] = name
    (OUT / f"{name}.json").write_text(
        json.dumps(payload, indent=1, sort_keys=False) + "\n"
    )
    print(f"  wrote {name}.json  [synthetic]")


# --------------------------------------------------------------------------
# eth_call rounds
# --------------------------------------------------------------------------


def _call_batch(url: str, to: str, getters: dict[str, str], block: str, *, opener=_open):
    """Return ``(request_body, response, id_to_name)`` for one batched round."""
    names = list(getters)
    body = [
        {
            "jsonrpc": "2.0",
            "id": i + 1,
            "method": "eth_call",
            "params": [{"to": to, "data": getters[n]}, block],
        }
        for i, n in enumerate(names)
    ]
    resp = post_json(url, body, opener=opener)
    id_to_name = {str(i + 1): n for i, n in enumerate(names)}
    return body, resp, id_to_name


def _head(url: str, *, opener=_open) -> tuple[int, str]:
    n = int(post_json(url, {"jsonrpc": "2.0", "id": 1, "method": "eth_blockNumber",
                            "params": []}, opener=opener)["result"], 16)
    blk = post_json(url, {"jsonrpc": "2.0", "id": 1,
                          "method": "eth_getBlockByNumber",
                          "params": [hex(n), False]}, opener=opener)["result"]
    return n, blk["hash"]


def capture_sepolia_state(opener=_open) -> None:
    print("capture: sepolia-state")
    block_n, block_hash = _head(SEPOLIA_STATE_URL, opener=opener)
    pinned = hex(block_n)
    common = {
        "captured_at": _now_iso(),
        "chain": "sepolia",
        "chain_id": SEPOLIA_CHAIN_ID,
        "launch": "launch-3 (2026-09-01T02:03Z)",
        "block_number": block_n,
        "block_hash": block_hash,
        "endpoint": SEPOLIA_STATE_URL,
        "addresses": {
            "hook": HOOK, "vault": VAULT, "dripper": DRIPPER,
            "token": TOKEN, "pool_manager": POOL_MANAGER, "burn_sink": BURN_SINK,
        },
    }

    # A17: read the vault's decimals BEFORE building its round.  This is the
    # "read values live; never hardcode a documented one" rule applied to an
    # ARGUMENT rather than to a result -- a wrong argument gets an honest
    # answer to the wrong question, which is worse than a revert because it
    # renders.
    dec_body = {"jsonrpc": "2.0", "id": 1, "method": "eth_call",
                "params": [{"to": VAULT, "data": VAULT_GETTERS["decimals"]},
                           pinned]}
    vault_decimals = int(post_json(SEPOLIA_STATE_URL, dec_body,
                                   opener=opener)["result"], 16)
    print(f"  vault decimals() = {vault_decimals} -> share-price call is "
          f"convertToAssets(10**{vault_decimals})")

    rounds = [
        ("hook_state_healthy", HOOK, HOOK_GETTERS,
         "One batched eth_call round over the whole recovered hook getter set. "
         "Every member answered."),
        ("vault_state", VAULT, _vault_getters(vault_decimals),
         "StakedIMD (verified source) full getter round.  AMENDMENT A17: "
         "decimals() is READ FIRST, in its own call, and the share-price "
         "argument is built from it -- convertToAssets(10**decimals), which is "
         "1e24 on this vault, NOT the 1e18 the first capture sent.  Solady's "
         "ERC4626 reports asset decimals + _decimalsOffset(), and StakedIMD's "
         "offset is 6.  The fixture carries the wrong-argument answer too, "
         "under convertToAssets_millionth_of_a_share, because the two together "
         "are the evidence for the trap: they differ by exactly 10**6.  "
         "SELF-VALIDATING CROSS-CHECK: totalAssets / totalSupply, each scaled "
         "by its own decimals, must equal convertToAssets(10**decimals) / "
         "10**asset_decimals.  On this capture that is 27,377.0 IMD / "
         "21,010.977789124329844268183983 sIMD = 1.3029855285540706, and "
         "convertToAssets(1e24) = 1_302_985_528_554_070_473.  A capture whose "
         "halves disagree tests the disagreement, not the code."),
        ("dripper_state", DRIPPER, DRIPPER_GETTERS,
         "RewardDripper (verified source) full getter round."),
        ("token_state", TOKEN, TOKEN_GETTERS,
         "The launch-3 test IMD: supply, decimals, and the balances the burn "
         "and reward legs must reconcile against."),
    ]
    for name, to, getters, note in rounds:
        body, resp, id_to_name = _call_batch(
            SEPOLIA_STATE_URL, to, getters, pinned, opener=opener)
        meta = dict(common, note=note, contract=to,
                    call_names=id_to_name, block_tag=pinned)
        if name == "vault_state":
            meta["vault_decimals"] = vault_decimals
            meta["asset_decimals"] = 18
            meta["decimals_offset"] = vault_decimals - 18
            meta["share_price_call"] = "convertToAssets"
            meta["share_price_argument"] = 10 ** vault_decimals
            meta["decimals_read_before_the_round"] = True
        write_pair(name, meta=meta,
                   request={"url": SEPOLIA_STATE_URL, "method": "POST",
                            "headers": {"Content-Type": "application/json",
                                        "User-Agent": USER_AGENT},
                            "body": body, "call_names": id_to_name},
                   response=resp)

    # The partial round: the same hook getters PLUS three the contract does not
    # implement.  A real revert from a real contract.
    partial = dict(HOOK_GETTERS)
    partial.update(HOOK_ABSENT_GETTERS)
    body, resp, id_to_name = _call_batch(
        SEPOLIA_STATE_URL, HOOK, partial, pinned, opener=opener)
    reverted = [id_to_name[str(e["id"])] for e in resp
                if isinstance(e, dict) and ("error" in e or e.get("result") == "0x")]
    write_pair(
        "hook_state_partial",
        meta=dict(
            common,
            contract=HOOK,
            call_names=id_to_name,
            block_tag=pinned,
            reverting_getters=reverted,
            note=(
                "The hook_state_healthy round plus bondTerms()/totalBonded()/"
                "bond() -- three selectors the launch-3 hook does not implement, "
                "picked because imd.fun/pool4 advertises a bond tab no deployed "
                "contract carries.  This is the 'the unverified contract "
                "answered some of it' case (plan R1), captured live rather than "
                "hand-edited: the reverts are the chain's own."
            ),
        ),
        request={"url": SEPOLIA_STATE_URL, "method": "POST",
                 "headers": {"Content-Type": "application/json",
                             "User-Agent": USER_AGENT},
                 "body": body, "call_names": id_to_name},
        response=resp,
    )

    # The flags reference, derived from the getHookPermissions answer above.
    healthy = json.loads((OUT / "hook_state_healthy.json").read_text())
    names = {v: k for k, v in healthy["call_names"].items()}
    by_id = {str(e["id"]): e for e in healthy["response"]}
    perms_raw = by_id[names["getHookPermissions"]].get("result")
    write_flags_reference(common, perms_raw)


def capture_vault_state(opener=_open) -> None:
    """Re-capture ONLY the vault round (A17).

    Deliberately narrow: ``--capture sepolia-state`` would rewrite the hook,
    dripper and token fixtures at a new block, and other packages already have
    tests standing on those bytes.  A fixture corpus is only coherent if a
    correction moves the one fixture that was wrong.
    """
    print("capture: vault-state (A17 re-capture)")
    block_n, block_hash = _head(SEPOLIA_STATE_URL, opener=opener)
    pinned = hex(block_n)
    dec_body = {"jsonrpc": "2.0", "id": 1, "method": "eth_call",
                "params": [{"to": VAULT, "data": VAULT_GETTERS["decimals"]},
                           pinned]}
    vault_decimals = int(post_json(SEPOLIA_STATE_URL, dec_body,
                                   opener=opener)["result"], 16)
    print(f"  decimals() = {vault_decimals}; share-price call is "
          f"convertToAssets(10**{vault_decimals})")
    getters = _vault_getters(vault_decimals)
    body, resp, id_to_name = _call_batch(
        SEPOLIA_STATE_URL, VAULT, getters, pinned, opener=opener)

    prev = OUT / "vault_state.json"
    old_block = json.loads(prev.read_text()).get("block_number") if prev.exists() \
        else None
    meta = {
        "captured_at": _now_iso(),
        "chain": "sepolia",
        "chain_id": SEPOLIA_CHAIN_ID,
        "launch": "launch-3 (2026-09-01T02:03Z)",
        "block_number": block_n,
        "block_hash": block_hash,
        "block_tag": pinned,
        "endpoint": SEPOLIA_STATE_URL,
        "contract": VAULT,
        "call_names": id_to_name,
        "vault_decimals": vault_decimals,
        "asset_decimals": 18,
        "decimals_offset": vault_decimals - 18,
        "share_price_call": "convertToAssets",
        "share_price_argument": 10 ** vault_decimals,
        "decimals_read_before_the_round": True,
        "supersedes_block": old_block,
        "addresses": {"vault": VAULT, "token": TOKEN, "dripper": DRIPPER,
                      "hook": HOOK},
        "note": (
            "StakedIMD (verified source) full getter round.  AMENDMENT A17 "
            "(2026-09-01): decimals() is READ FIRST, in its own call, and the "
            "share-price argument is built from it -- "
            "convertToAssets(10**decimals), which is 1e24 on this vault, NOT "
            "the 1e18 the first capture sent.  Solady's ERC4626 reports asset "
            "decimals + _decimalsOffset() and StakedIMD's offset is 6, so one "
            "whole sIMD is 1e24 units and 1e18 is a MILLIONTH of a share.  The "
            "first capture's answer was honest and the question was wrong: "
            "1_302_985_528_554 renders as 0.0000013 IMD/share, a vault that "
            "looks dead while its share price is 1.302986.  The wrong-argument "
            "answer is KEPT here under convertToAssets_millionth_of_a_share "
            "because the pair is the evidence for the trap -- they differ by "
            "exactly 10**offset -- and it is unmistakable as a share price.  "
            "SELF-VALIDATING: totalAssets/1e18 divided by totalSupply/1e24 "
            "must equal convertToAssets(10**decimals)/1e18."
        ),
    }
    write_pair(name := "vault_state", meta=meta,
               request={"url": SEPOLIA_STATE_URL, "method": "POST",
                        "headers": {"Content-Type": "application/json",
                                    "User-Agent": USER_AGENT},
                        "decimals_probe": dec_body,
                        "body": body, "call_names": id_to_name},
               response=resp)
    by_id = {str(e["id"]): e for e in resp}
    ids = {v: k for k, v in id_to_name.items()}
    val = lambda n: int(by_id[ids[n]]["result"], 16)  # noqa: E731
    ta, ts = val("totalAssets"), val("totalSupply")
    sp = val("convertToAssets")
    wrong = val("convertToAssets_millionth_of_a_share")
    print(f"  totalAssets  {ta / 10 ** 18:.6f} IMD")
    print(f"  totalSupply  {ts / 10 ** vault_decimals:.18f} sIMD")
    print(f"  share price  {sp / 10 ** 18:.12f} IMD/share")
    print(f"  cross-check  {(ta / 10 ** 18) / (ts / 10 ** vault_decimals):.12f}"
          f"   agrees: {abs((ta / 10 ** 18) / (ts / 10 ** vault_decimals) - sp / 10 ** 18) < 1e-9}")
    print(f"  wrong-arg    {wrong} (ratio {sp / wrong:.6f})")


def _mainnet_token_getters() -> dict[str, str]:
    g = {
        "totalSupply": "0x18160ddd",
        "decimals": "0x313ce567",
        "symbol": "0x95d89b41",
        "name": "0x06fdde03",
        # burnSink() is the BurnExecutor here, so THIS is the balance the burn
        # counter must be compared against -- not the dEaD balance.
        "balanceOf_burnExecutor": _balance_of(MAINNET_BURN_EXECUTOR),
        # Captured for CONTRAST, not for a cross-check: the Sepolia identity
        # totalBurned == balanceOf(0xdEaD) does not transfer to mainnet.
        "balanceOf_dead": _balance_of(BURN_SINK),
        "balanceOf_hook": _balance_of(MAINNET_HOOK),
        "balanceOf_vault": _balance_of(MAINNET_VAULT),
        "balanceOf_distributor": _balance_of(MAINNET_DISTRIBUTOR),
        "balanceOf_dripper": _balance_of(MAINNET_DRIPPER),
        "balanceOf_poolManager": _balance_of(MAINNET_POOL_MANAGER),
    }
    return g


def capture_mainnet_state(opener=_open) -> None:
    """The live mainnet deployment.  Additive -- touches no Sepolia fixture."""
    print("capture: mainnet-state")
    block_n, block_hash = _head(MAINNET_STATE_URL, opener=opener)
    pinned = hex(block_n)
    common = {
        "captured_at": _now_iso(),
        "chain": "mainnet",
        "chain_id": MAINNET_CHAIN_ID,
        "block_number": block_n,
        "block_hash": block_hash,
        "block_tag": pinned,
        "endpoint": MAINNET_STATE_URL,
        "addresses": {
            "hook": MAINNET_HOOK, "vault": MAINNET_VAULT,
            "distributor": MAINNET_DISTRIBUTOR, "dripper": MAINNET_DRIPPER,
            "burn_executor": MAINNET_BURN_EXECUTOR, "token": MAINNET_IMD,
            "pool_manager": MAINNET_POOL_MANAGER,
        },
    }

    hook_getters = dict(HOOK_GETTERS)
    hook_getters.update(HOOK_CAP_GETTERS)

    # The vault's decimals decide its share-price argument (A17), so read it
    # first here too rather than assuming Sepolia's 24 carries over.
    dec_body = {"jsonrpc": "2.0", "id": 1, "method": "eth_call",
                "params": [{"to": MAINNET_VAULT,
                            "data": VAULT_GETTERS["decimals"]}, pinned]}
    vault_decimals = int(post_json(MAINNET_STATE_URL, dec_body,
                                   opener=opener)["result"], 16)
    print(f"  mainnet vault decimals() = {vault_decimals}")

    rounds = [
        ("mainnet_hook_state", MAINNET_HOOK, hook_getters,
         "The live mainnet market hook, one batched round over the whole "
         "recovered getter set PLUS the two getters recovered from bytecode "
         "for this deployment: capDecayTokensPerDay() (0x55e62941) and "
         "inventoryCap() (0xdb445ee8).  Both pre-images were CONFIRMED by "
         "keccak during this capture run rather than assumed.  What differs "
         "from Sepolia and is read live, never hardcoded: rewardShareBps is "
         "1500 here against 1000 there, capFloor is 1,000 IMD against "
         "250,000,000, and burnSink() is the BurnExecutor rather than "
         "0x...dEaD."),
        ("mainnet_vault_state", MAINNET_VAULT, _vault_getters(vault_decimals),
         "The mainnet sIMD vault.  decimals() is read first and the "
         "share-price argument built from it (A17); it is 24 here as on "
         "Sepolia, but that was MEASURED, not carried over."),
        ("mainnet_distributor_state", MAINNET_DISTRIBUTOR,
         DISTRIBUTOR_GETTERS,
         "The Reward Distributor -- NEW on mainnet, no Sepolia counterpart, "
         "and the reason the vault is three hops away rather than two.  "
         "vault() IS INCLUDED AND IS EXPECTED TO REVERT: it is the call the "
         "old two-hop path made, and its revert is precisely what stops the "
         "walk.  A fixture that omitted it could not replay the failure it "
         "exists to document.  The three-way split is stakingBps 3000 and "
         "nftBps 3000 with bonding as the DERIVED remainder "
         "(10000 - 3000 - 3000 = 4000) -- bonding has no getter of its own, so "
         "any 4000 in code must be a derivation, never a literal."),
        ("mainnet_dripper_state", MAINNET_DRIPPER, DRIPPER_GETTERS,
         "The mainnet Reward Dripper, reached through the Distributor."),
        ("mainnet_token_state", MAINNET_IMD, _mainnet_token_getters(),
         "Mainnet IMD.  balanceOf(BurnExecutor) is the balance the burn "
         "counter must be reconciled against here, because burnSink() is the "
         "BurnExecutor.  balanceOf(0xdEaD) is captured for CONTRAST ONLY: the "
         "Sepolia identity totalBurned == balanceOf(0xdEaD) DOES NOT TRANSFER "
         "to mainnet and a control carrying it over would misreport."),
    ]
    for name, to, getters, note in rounds:
        body, resp, id_to_name = _call_batch(
            MAINNET_STATE_URL, to, getters, pinned, opener=opener)
        meta = dict(common, note=note, contract=to,
                    call_names=id_to_name)
        if name == "mainnet_vault_state":
            meta.update(vault_decimals=vault_decimals, asset_decimals=18,
                        decimals_offset=vault_decimals - 18,
                        share_price_call="convertToAssets",
                        share_price_argument=10 ** vault_decimals,
                        decimals_read_before_the_round=True)
        if name == "mainnet_distributor_state":
            reverted = [id_to_name[str(e["id"])] for e in resp
                        if isinstance(e, dict) and "error" in e]
            meta["reverting_getters"] = reverted
        write_pair(name, meta=meta,
                   request={"url": MAINNET_STATE_URL, "method": "POST",
                            "headers": {"Content-Type": "application/json",
                                        "User-Agent": USER_AGENT},
                            "body": body, "call_names": id_to_name},
                   response=resp)

    healthy = json.loads((OUT / "mainnet_hook_state.json").read_text())
    ids = {v: k for k, v in healthy["call_names"].items()}
    by_id = {str(e["id"]): e for e in healthy["response"]}
    write_flags_reference(
        common, by_id[ids["getHookPermissions"]].get("result"),
        name="mainnet_flags_reference", hook=MAINNET_HOOK,
        others=(MAINNET_HOOK,))


def capture_vault_path(opener=_open) -> None:
    """The THREE-HOP walk to the vault, captured as a replayable sequence.

    Sepolia: hook.rewardsRecipient() -> Dripper -> dripper.vault() -> vault.
    Mainnet: hook.rewardsRecipient() -> DISTRIBUTOR -> distributor.dripper()
             -> Dripper -> dripper.vault() -> vault.

    WP6 walks this by asking each node what it is rather than by assuming a
    shape, so the fixture records each hop as its own call with its own answer,
    INCLUDING the ``distributor.vault()`` revert that stops the two-hop walk.
    """
    print("capture: vault-path")
    block_n, block_hash = _head(MAINNET_STATE_URL, opener=opener)
    pinned = hex(block_n)
    steps = [
        ("hook.rewardsRecipient", MAINNET_HOOK, "0xff2a7d30",
         "hop 1 -- the hook names its reward recipient.  On Sepolia this "
         "answered the Dripper; here it answers the DISTRIBUTOR."),
        ("distributor.vault", MAINNET_DISTRIBUTOR, "0xfbfa77cf",
         "THE WALK-STOPPER.  The old two-hop path called vault() on whatever "
         "rewardsRecipient named.  The Distributor has no such method and this "
         "REVERTS -- which is why vault and dripper reads fail outright on "
         "mainnet until the walk learns the third hop.  Its presence in this "
         "fixture is the point."),
        ("distributor.dripper", MAINNET_DISTRIBUTOR, "0x603ea03b",
         "hop 2 -- the Distributor names the Dripper.  This is the hop that "
         "did not exist on Sepolia."),
        ("dripper.vault", MAINNET_DRIPPER, "0xfbfa77cf",
         "hop 3 -- the Dripper names the sIMD vault."),
        ("vault.asset", MAINNET_VAULT, "0x38d52e0f",
         "the walk closes: the vault's asset must be the same IMD the pool "
         "trades, or the path led somewhere else."),
        ("distributor.asset", MAINNET_DISTRIBUTOR, "0x38d52e0f",
         "corroboration -- the Distributor holds the same asset."),
        ("hook.token", MAINNET_HOOK, "0xfc0c546a",
         "the anchor the whole walk must agree with."),
    ]
    body = [{"jsonrpc": "2.0", "id": i + 1, "method": "eth_call",
             "params": [{"to": to, "data": d}, pinned]}
            for i, (_, to, d, _n) in enumerate(steps)]
    resp = post_json(MAINNET_STATE_URL, body, opener=opener)
    by_id = {str(e["id"]): e for e in resp}
    walk = []
    for i, (label, to, data, why) in enumerate(steps):
        e = by_id[str(i + 1)]
        res = e.get("result")
        walk.append({
            "step": label, "to": to, "calldata": data, "why": why,
            "reverted": "error" in e,
            "error": e.get("error"),
            "result": res,
            "answer_address": ("0x" + res[-40:]) if res and len(res) >= 42
            else None,
        })
    write_pair(
        "mainnet_vault_path",
        meta={
            "captured_at": _now_iso(), "chain": "mainnet",
            "chain_id": MAINNET_CHAIN_ID, "block_number": block_n,
            "block_hash": block_hash, "block_tag": pinned,
            "endpoint": MAINNET_STATE_URL,
            "call_names": {str(i + 1): st[0] for i, st in enumerate(steps)},
            "note": (
                "THE THREE-HOP VAULT PATH, captured hop by hop so the walk can "
                "be replayed rather than transcribed.  "
                "hook.rewardsRecipient() -> Distributor -> "
                "distributor.dripper() -> Dripper -> dripper.vault() -> sIMD.  "
                "distributor.vault() is included AND REVERTS; that revert is "
                "what stops the old two-hop walk, and a fixture without it "
                "could not reproduce the mainnet failure.  Every hop is a "
                "node ANSWERING WHAT IT IS -- no step assumes a shape."
            ),
            "walk": walk,
            "expected": {
                "hops": 3,
                "distributor_vault_reverts": True,
                "path": ["hook.rewardsRecipient", "distributor.dripper",
                         "dripper.vault"],
            },
        },
        request={"url": MAINNET_STATE_URL, "method": "POST",
                 "headers": {"Content-Type": "application/json",
                             "User-Agent": USER_AGENT},
                 "body": body,
                 "call_names": {str(i + 1): st[0]
                                for i, st in enumerate(steps)}},
        response=resp,
    )
    for w in walk:
        print(f"  {w['step']:24s} "
              f"{'REVERTED' if w['reverted'] else (w['answer_address'] or w['result'])}")


def capture_sepolia_cap_getters(opener=_open) -> None:
    """ADDITIVE Sepolia fixture: the two cap getters, on the OTHER chain.

    This does not re-capture anything -- it is a new file.  It exists because
    "these getters are mainnet-only" was an assumption that was never measured
    and turned out to be wrong: the Sepolia launch-3 hook answers both.  A test
    written from the assumption ("point it at Sepolia and watch the fields go
    None") would have PASSED FOR THE WRONG REASON.
    """
    print("capture: sepolia-cap-getters")
    block_n, block_hash = _head(SEPOLIA_STATE_URL, opener=opener)
    pinned = hex(block_n)
    getters = dict(HOOK_CAP_GETTERS)
    getters["tokensInPool"] = HOOK_GETTERS["tokensInPool"]
    getters["capFloor"] = HOOK_GETTERS["capFloor"]
    getters["rewardShareBps"] = HOOK_GETTERS["rewardShareBps"]
    # The control: a getter that genuinely does not exist, so the ABSENCE case
    # is driven by a real revert rather than by pointing at the wrong chain.
    getters["vault_control"] = "0xfbfa77cf"
    body, resp, id_to_name = _call_batch(
        SEPOLIA_STATE_URL, HOOK, getters, pinned, opener=opener)
    write_pair(
        "sepolia_cap_getters",
        meta={
            "captured_at": _now_iso(), "chain": "sepolia",
            "chain_id": SEPOLIA_CHAIN_ID, "block_number": block_n,
            "block_hash": block_hash, "block_tag": pinned,
            "endpoint": SEPOLIA_STATE_URL, "contract": HOOK,
            "call_names": id_to_name,
            "note": (
                "BOTH CAP GETTERS ANSWER ON SEPOLIA TOO.  An earlier claim "
                "that capDecayTokensPerDay() and inventoryCap() were "
                "mainnet-only was an assumption that was never measured, and "
                "it is wrong: the difference between the chains is the VALUE, "
                "not the presence.  Sepolia returns 2**128-1 for the decay "
                "rate -- the no-decay sentinel -- against 1,000 IMD/day on "
                "mainnet.  This fixture exists so the absence case is driven "
                "by a getter that genuinely reverts (vault_control, included "
                "here for exactly that) instead of by pointing the test at the "
                "other chain, which would pass for the wrong reason.  ADDITIVE: "
                "this file re-captures nothing -- every pre-existing Sepolia "
                "fixture is untouched at its own block."
            ),
        },
        request={"url": SEPOLIA_STATE_URL, "method": "POST",
                 "headers": {"Content-Type": "application/json",
                             "User-Agent": USER_AGENT},
                 "body": body, "call_names": id_to_name},
        response=resp,
    )
    by = {str(e["id"]): e for e in resp}
    ids = {v: k for k, v in id_to_name.items()}
    for n in getters:
        e = by[ids[n]]
        r = e.get("result")
        print(f"  {n:24s} "
              f"{'REVERTED' if 'error' in e else int(r, 16) if r else r}")


def get_text(url: str, *, opener=_open, timeout: int = 90):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with opener(req, timeout=timeout) as resp:
        raw = resp.read()
        return raw, dict(resp.headers), resp.status


def capture_docs_site(opener=_open) -> None:
    """The operator's docs page -- a candidate ADDRESS source, not chain data.

    The announce channel has still not named the mainnet hook, so under A27 the
    discovery gate correctly refuses to adopt it.  The operator has decided to
    accept this page as a CANDIDATE source.  Captured so the parser can be
    tested against real bytes; the parse is the SAME raw-text ADDRESS_RE the
    channel uses, and S16 applies unchanged -- the regex must see raw text, and
    normalisation belongs downstream of extraction, never upstream.
    """
    print("capture: docs-site")
    raw, headers, status = get_text(DOCS_SITE_URL, opener=opener)
    text = raw.decode("utf-8", errors="replace")
    found = scan_for_candidates(text)
    seen: dict[str, dict] = {}
    for a in found:
        key = a.lower()
        if key not in seen:
            seen[key] = {"address": a, "count": 0,
                         "low_14_bits": "0x%04x" % (int(a, 16) & 0x3FFF)}
        seen[key]["count"] += 1
    known = {
        MAINNET_HOOK.lower(): "hook", MAINNET_VAULT.lower(): "vault",
        MAINNET_DISTRIBUTOR.lower(): "distributor",
        MAINNET_DRIPPER.lower(): "dripper",
        MAINNET_BURN_EXECUTOR.lower(): "burn executor",
        MAINNET_IMD.lower(): "IMD token",
        MAINNET_POOL_MANAGER.lower(): "pool manager",
    }
    for k, v in seen.items():
        v["known_as"] = known.get(k)
    hook_shaped = [v for v in seen.values()
                   if int(v["address"], 16) & 0x3FFF == POOL4_FLAG_WORD]
    write_pair(
        "docs_site_page",
        meta={
            "captured_at": _now_iso(),
            "chain": None,
            "endpoint": DOCS_SITE_URL,
            "source_kind": "operator-controlled HTML",
            "http_status": status,
            "content_type": headers.get("Content-Type"),
            "byte_length": len(raw),
            "note": (
                "ONE OPERATOR'S MUTABLE HTML.  NOT CONSENSUS DATA.  This is a "
                "web page served by a host the protocol's operator controls; "
                "nothing about it is signed, replicated or verifiable after "
                "the fact, and it can differ between two readers or between "
                "two minutes.  It is captured because the operator has "
                "accepted it as a CANDIDATE address source -- the announce "
                "channel has still not named the mainnet hook, so under A27 "
                "the gate correctly refuses to adopt it and the view would "
                "show SEPOLIA while mainnet is live.\n\n"
                "WHAT THIS DOES AND DOES NOT BUY.  It supplies a candidate; "
                "the full chain fingerprint still runs on it.  But the "
                "fingerprint is forgeable (A27): a 0x2840-shaped address mines "
                "in ~20,000 tries, four of the five getters are pure liveness "
                "checks, and token() is the candidate's own choice.  So "
                "ANYONE WHO CAN CHANGE THIS PAGE CAN NAME A HOOK, and no "
                "downstream check will stop them.  Provenance -- a "
                "dev-signed self-post -- remains the only unforgeable gate, "
                "and the announce channel overrides this source when a "
                "self-post lands.  The mitigation is DISCLOSURE, not "
                "prevention: the panel must name which source an adoption came "
                "from, so weaker provenance identifies itself instead of "
                "hiding behind the same word as a dev-signed post.\n\n"
                "PARSING: the same raw-text ADDRESS_RE the channel uses, over "
                "the bytes as served.  S16 applies unchanged -- the regex sees "
                "raw text and normalisation belongs DOWNSTREAM of extraction, "
                "never upstream, or a control-character trick re-arms itself "
                "here exactly as it would on the channel."
            ),
            "addresses_found": sorted(seen.values(),
                                      key=lambda v: -v["count"]),
            "hook_shaped_candidates": hook_shaped,
            "expected": {
                "candidates_stage": "flag_filtered",
                "flag_filtered_candidates": [v["address"]
                                             for v in hook_shaped],
                "provenance": "NONE -- this source has no provenance gate at "
                              "all; that is its whole cost",
            },
        },
        request={"url": DOCS_SITE_URL, "method": "GET",
                 "headers": {"User-Agent": USER_AGENT}},
        response={"html": text},
    )
    print(f"  {status}, {len(raw)} bytes, {len(seen)} distinct addresses, "
          f"{len(hook_shaped)} hook-shaped")
    for v in sorted(seen.values(), key=lambda v: -v["count"]):
        print(f"    {v['address']}  low14={v['low_14_bits']}  "
              f"x{v['count']}  {v['known_as'] or ''}")


def _reaches_deployment(logs: list) -> bool:
    """True when the window contains the hook's one-time deployment events.

    This decides whether the log sums may be reconciled against the hook's
    CUMULATIVE counters at all: a window that starts after deployment holds a
    suffix of history, and reconciling a suffix against a cumulative counter
    reports a defect that is not there.
    """
    want = ("OwnershipTransferred", "PoolInitialized", "MarketOpened")
    seen = {TOPIC0_MAP.get(l["topics"][0], "") for l in logs}
    return all(any(s.startswith(w) for s in seen) for w in want)


def capture_announce_still_unnamed(opener=_open) -> None:
    """The channel AFTER pool4 went live -- and it still has not named it.

    Additive.  ``announce_undiscovered.json`` stays at its own bytes because
    other packages have tests standing on them, and it answered a question that
    is now historical ("is pool4 live anywhere?").  THIS fixture answers the
    question that matters now: pool4 IS live on mainnet, and the announce
    channel -- the only unforgeable provenance gate (A27) -- has still not
    named the hook.  That gap is the entire justification for accepting the
    operator's docs site as a candidate source, and it must be evidence rather
    than a claim.
    """
    print("capture: announce-still-unnamed")
    url = f"{MAINNET_BLOCKSCOUT}/addresses/{ANNOUNCE}/transactions"
    body = get_json(url, opener=opener)
    items = body.get("items") or []
    hits, names_hook, self_posts = [], [], []
    for it in items:
        frm = ((it.get("from") or {}).get("hash") or "").lower()
        to = ((it.get("to") or {}).get("hash") or "").lower()
        is_self = frm == to == ANNOUNCE.lower()
        if is_self:
            self_posts.append(it.get("hash"))
        text = _decode_calldata_text(it.get("raw_input") or "") or ""
        if MAINNET_HOOK.lower() in text.lower():
            names_hook.append(it.get("hash"))
        for addr in scan_for_candidates(text):
            if int(addr, 16) & 0x3FFF == POOL4_FLAG_WORD and is_self:
                hits.append({"address": addr, "tx_hash": it.get("hash")})
    write_pair(
        "announce_still_unnamed",
        meta={
            "captured_at": _now_iso(), "chain": "mainnet",
            "chain_id": MAINNET_CHAIN_ID, "endpoint": url,
            "announce": ANNOUNCE, "mainnet_hook": MAINNET_HOOK,
            "page_item_count": len(items),
            "self_post_count": len(self_posts),
            "next_page_params": body.get("next_page_params"),
            "is_complete_channel_history":
                body.get("next_page_params") is None,
            "newest_timestamp": items[0].get("timestamp") if items else None,
            "note": (
                "POOL4 IS LIVE ON MAINNET AND THE ANNOUNCE CHANNEL HAS NOT "
                "NAMED IT.  This is the complete channel history, captured "
                "after the deployment; no self-post mentions the live hook "
                "(" + MAINNET_HOOK + ") and no self-post carries any "
                "0x2840-shaped address at all.  Under A27 the discovery gate "
                "therefore refuses -- correctly -- and the view would show "
                "SEPOLIA while mainnet trades.  That refusal is not a bug and "
                "must not be 'fixed' by weakening the gate; it is the cost of "
                "provenance being the only unforgeable check, and it is the "
                "whole reason the operator accepted docs_site_page as a "
                "candidate source.  ADDITIVE: announce_undiscovered.json is "
                "untouched at its own bytes; it answered the question 'is "
                "pool4 live anywhere', which is now historical."
            ),
            "self_posts_naming_the_mainnet_hook": names_hook,
            "hook_shaped_self_post_candidates": hits,
            "expected": {
                "candidates_stage": "flag_filtered",
                "flag_filtered_candidates": [],
                "discovery_state": "not-discovered",
                "channel_names_the_live_hook": False,
            },
        },
        request={"url": url, "method": "GET",
                 "headers": {"User-Agent": USER_AGENT}, "params": None},
        response=body,
    )
    print(f"  {len(items)} txs, newest {items[0].get('timestamp')}, "
          f"names the live hook: {bool(names_hook)}, "
          f"hook-shaped self-post candidates: {len(hits)}")


def capture_mainnet_pool(opener=_open) -> None:
    """Mainnet pool slot0 + the hook's flow logs."""
    print("capture: mainnet-pool")
    sys.path.insert(0, str(ROOT))
    from maxpane_dashboard.data.surf_v4 import (  # noqa: E402
        decode_liquidity, decode_slot0, pool_state_slots,
    )
    hook_fx = json.loads((OUT / "mainnet_hook_state.json").read_text())
    ids = {v: k for k, v in hook_fx["call_names"].items()}
    by_id = {str(e["id"]): e for e in hook_fx["response"]}
    pool_id = by_id[ids["poolId"]]["result"]

    block_n, block_hash = _head(MAINNET_STATE_URL, opener=opener)
    pinned = hex(block_n)
    slot0_key, liq_key = pool_state_slots(pool_id)
    calls = {"slot0": "0x1e2eaeaf" + slot0_key[2:],
             "liquidity": "0x1e2eaeaf" + liq_key[2:]}
    body, resp, id_to_name = _call_batch(
        MAINNET_STATE_URL, MAINNET_POOL_MANAGER, calls, pinned, opener=opener)
    by = {str(e["id"]): e for e in resp}
    k = {v: kk for kk, v in id_to_name.items()}
    slot0_word = by[k["slot0"]]["result"]
    liq_word = by[k["liquidity"]]["result"]
    sqrt, tick, lp_fee = decode_slot0(slot0_word)
    write_pair(
        "mainnet_pool_slot0",
        meta={
            "captured_at": _now_iso(), "chain": "mainnet",
            "chain_id": MAINNET_CHAIN_ID, "block_number": block_n,
            "block_hash": block_hash, "block_tag": pinned,
            "endpoint": MAINNET_STATE_URL,
            "pool_manager": MAINNET_POOL_MANAGER, "pool_id": pool_id,
            "mapping_slot": 6, "slot0_key": slot0_key,
            "liquidity_key": liq_key, "call_names": id_to_name,
            "note": (
                "PoolManager.extsload for the live mainnet pool, pool id read "
                "off the hook rather than assumed.  Slots derived by "
                "data/surf_v4.pool_state_slots -- the same mapping slot 6 that "
                "holds on Sepolia, MEASURED here rather than carried over.  "
                "This is the corroboration that matters most on an unverified "
                "hook: the canonical, verified-source v4 singleton confirming "
                "the hook's own position getters.  Read it in the SAME sweep "
                "as the hook or a moving pool reports false drift."
            ),
            "expected": {"sqrt_price_x96": sqrt, "tick": tick,
                         "lp_fee": lp_fee,
                         "liquidity": decode_liquidity(liq_word)},
        },
        request={"url": MAINNET_STATE_URL, "method": "POST",
                 "headers": {"Content-Type": "application/json",
                             "User-Agent": USER_AGENT},
                 "body": body, "call_names": id_to_name},
        response=resp,
    )
    print(f"  slot0 tick {tick} lpFee {lp_fee} L {decode_liquidity(liq_word)}")

    # Logs: publicnode refuses archive eth_getLogs on mainnet (CLAUDE.md), so
    # this goes through the tenderly/drpc pool.
    lo = block_n - 20000
    params = {"address": MAINNET_HOOK, "fromBlock": hex(lo),
              "toBlock": hex(block_n)}
    log_body = {"jsonrpc": "2.0", "id": 1, "method": "eth_getLogs",
                "params": [params]}
    last_err = None
    for url in MAINNET_LOG_RPCS:
        try:
            lresp = post_json(url, log_body, opener=opener)
            if "error" not in lresp:
                break
            last_err = lresp["error"]
        except Exception as exc:  # noqa: BLE001
            last_err = repr(exc)
    else:
        print(f"  logs unavailable: {last_err}")
        return
    logs = lresp.get("result") or []
    write_pair(
        "mainnet_flow_logs",
        meta={
            "captured_at": _now_iso(), "chain": "mainnet",
            "chain_id": MAINNET_CHAIN_ID, "endpoint": url,
            "hook": MAINNET_HOOK, "from_block": lo, "to_block": block_n,
            "head_block": block_n, "log_count": len(logs),
            "topic0_map": TOPIC0_MAP,
            "note": (
                "The mainnet hook's logs over the 20,000 blocks to head, "
                "through the tenderly/drpc pool because "
                "ethereum-rpc.publicnode.com refuses archive eth_getLogs "
                "(CLAUDE.md).  Whether this window reaches the deployment is "
                "recorded as window_reaches_deployment rather than assumed; if "
                "it does not, the sums here are a SUFFIX of history and must "
                "not be reconciled against the hook's cumulative counters."
            ),
            # Computed, not assumed: the deployment-only events are either in
            # the window or they are not.
            "window_reaches_deployment": _reaches_deployment(logs),
            "deployment_events_seen": sorted(
                {TOPIC0_MAP[l["topics"][0]] for l in logs
                 if TOPIC0_MAP.get(l["topics"][0], "").startswith(
                     ("OwnershipTransferred", "PoolInitialized",
                      "MarketOpened"))}),
        },
        request={"url": url, "method": "POST",
                 "headers": {"Content-Type": "application/json",
                             "User-Agent": USER_AGENT},
                 "body": log_body},
        response=lresp,
    )
    print(f"  {len(logs)} logs from {url}")


V4_FLAG_BITS = [
    ("beforeInitialize", 13), ("afterInitialize", 12),
    ("beforeAddLiquidity", 11), ("afterAddLiquidity", 10),
    ("beforeRemoveLiquidity", 9), ("afterRemoveLiquidity", 8),
    ("beforeSwap", 7), ("afterSwap", 6),
    ("beforeDonate", 5), ("afterDonate", 4),
    ("beforeSwapReturnDelta", 3), ("afterSwapReturnDelta", 2),
    ("afterAddLiquidityReturnDelta", 1), ("afterRemoveLiquidityReturnDelta", 0),
]


def decode_hook_permissions(word: str) -> tuple[dict[str, bool], int]:
    raw = word[2:] if word.startswith("0x") else word
    words = [raw[i:i + 64] for i in range(0, len(raw), 64)]
    if len(words) != len(V4_FLAG_BITS):
        raise ValueError(f"expected 14 words, got {len(words)}")
    flags: dict[str, bool] = {}
    value = 0
    for (name, bit), w in zip(V4_FLAG_BITS, words):
        on = bool(int(w, 16))
        flags[name] = on
        if on:
            value |= 1 << bit
    return flags, value


def write_flags_reference(common: dict, perms_raw: str, *,
                          name: str = "hook_flags_reference",
                          hook: str = HOOK,
                          others: tuple = (HOOK, HOOK_LAUNCH_1,
                                           HOOK_LAUNCH_2)) -> None:
    flags, value = decode_hook_permissions(perms_raw)
    addr_masks = {
        a: "0x%04x" % (int(a, 16) & 0x3FFF)
        for a in others
    }
    payload = {
        "fixture": name,
        "synthetic": False,
        "captured_at": common["captured_at"],
        "chain": "sepolia",
        "chain_id": SEPOLIA_CHAIN_ID,
        "block_number": common["block_number"],
        "source": (
            "getHookPermissions() (selector 0xc4e833ce) on "
            + hook + ", in the same batched round as that hook's state fixture"
        ),
        "note": (
            "THE FLAG WORD IS 0x2840, NOT 0x840.  The address's visible '840' "
            "suffix is a mined vanity tail; the v4 permission field is the LOW "
            "14 BITS, and for all three Sepolia launch hooks that is 0x2840 = "
            "BEFORE_INITIALIZE (1<<13) | BEFORE_ADD_LIQUIDITY (1<<11) | "
            "AFTER_SWAP (1<<6).  The contract's own getHookPermissions() agrees "
            "bit for bit.  docs/imd_pool4_mechanics.md and the implementation "
            "plan both state 0x840 = (1<<11)|(1<<6); with the plan's mandated "
            "EQUALITY test that constant rejects the real hook."
        ),
        "raw_result": perms_raw,
        "decoded_permissions": flags,
        "flag_word": "0x%04x" % value,
        "flag_word_int": value,
        "address_low_14_bits": addr_masks,
        "hook_flag_mask": "0x3fff",
    }
    OUT.mkdir(parents=True, exist_ok=True)
    payload["chain"] = common.get("chain", payload.get("chain"))
    payload["chain_id"] = common.get("chain_id", payload.get("chain_id"))
    (OUT / f"{name}.json").write_text(json.dumps(payload, indent=1) + "\n")
    print(f"  wrote {name}.json")


# --------------------------------------------------------------------------
# logs
# --------------------------------------------------------------------------


def _getlogs(url: str, params: dict, *, opener=_open):
    body = {"jsonrpc": "2.0", "id": 1, "method": "eth_getLogs", "params": [params]}
    return body, post_json(url, body, opener=opener)


def capture_flow_logs(opener=_open) -> None:
    print("capture: flow-logs")
    block_n, _ = _head(SEPOLIA_STATE_URL, opener=opener)
    common = {
        "captured_at": _now_iso(),
        "chain": "sepolia",
        "chain_id": SEPOLIA_CHAIN_ID,
        "endpoint": SEPOLIA_LOG_URL,
        "head_block": block_n,
        "hook": HOOK,
        "topic0_map": TOPIC0_MAP,
    }
    windows = [
        ("flow_logs_mixed", FLOW_MIXED_FROM, FLOW_MIXED_TO,
         "A 60-block window carrying a BUY (0x841e5af58c -- FeeCollected in "
         "ETH plus the pool-reserve event), several SELLs, a standalone "
         "settlement (0x832f0efbe3 -- ClaimsSettled with no swap), and one "
         "genuinely unsettled accrual.  AMENDMENT A16 (2026-09-01): an "
         "earlier version of this note called the accrual in 0x028d1448a9 "
         "'the accrued-but-unsettled case' because no ClaimsSettled sits in "
         "that transaction.  THAT IS WRONG AND THIS CORPUS DISPROVES IT.  "
         "SETTLEMENT IS DECIDED BY LOG ORDER ACROSS THE WINDOW, NOT BY "
         "TRANSACTION BOUNDARY: 0x028d1448a9's accrual (7,573,500 / 841,500) "
         "is paid to the wei by ClaimsSettled in the LATER transaction "
         "0x832f0efbe3, and inside 0x48090d111b the ClaimsSettled sits at "
         "logIndex 0x7b -- BEFORE that transaction's own accrual at 0x82 -- "
         "paying the PREVIOUS transaction's 891 / 99.  Settlement rides the "
         "next swap.  A same-transaction rule mislabels rows in BOTH "
         "directions.  The one genuinely outstanding accrual in this window "
         "is the LAST one, in 0x8005a2272e: sum(accrual) - "
         "sum(ClaimsSettled) leaves 267,299.999999999999994537 burn / "
         "29,699.999999999999999393 stakers unpaid, and nothing after it "
         "settles them.  THOSE ARE THE EXACT WEI: they DISPLAY as a round "
         "267,300 / 29,700 at two decimal places but are not round, so an "
         "equality test written against the round figure fails on real "
         "data."),
        ("flow_logs_full", FLOW_FROM_BLOCK, FLOW_TO_BLOCK,
         "The complete launch-3 hook log set as of capture: every "
         "FeeCollected, every ClaimsSettled, both FeesWithdrawn, the single "
         "Rebalanced / KeeperRewardPaid / backstop transaction.  This is the "
         "set the R1 cross-checks reconcile against the counters in "
         "hook_state_healthy.  'Complete' is MEASURED, not assumed: a 20,000-"
         "block query to head returns the same 90 logs as this 400-block "
         "window, so nothing precedes block 11609650 or follows 11609981.  "
         "That holds only as of the captured_at above -- the hook is live and "
         "a later sweep may find more, at which point the counters in "
         "hook_state_healthy will no longer reconcile against this file and "
         "BOTH must be re-captured together."),
        ("flow_logs_empty", FLOW_EMPTY_FROM, FLOW_EMPTY_TO,
         "A window that closes before the hook was deployed: swept, and "
         "genuinely quiet.  The [] -- not None -- case."),
    ]
    for name, lo, hi, note in windows:
        params = {"address": HOOK, "fromBlock": hex(lo), "toBlock": hex(hi)}
        body, resp = _getlogs(SEPOLIA_LOG_URL, params, opener=opener)
        n = len(resp.get("result") or []) if isinstance(resp, dict) else -1
        write_pair(
            name,
            meta=dict(common, note=note, from_block=lo, to_block=hi, log_count=n),
            request={"url": SEPOLIA_LOG_URL, "method": "POST",
                     "headers": {"Content-Type": "application/json",
                                 "User-Agent": USER_AGENT},
                     "body": body},
            response=resp,
        )


# --------------------------------------------------------------------------
# v4 pool state via PoolManager.extsload
# --------------------------------------------------------------------------


def capture_pool_slot0(opener=_open) -> None:
    print("capture: pool-slot0")
    sys.path.insert(0, str(ROOT))
    from maxpane_dashboard.data.surf_v4 import (  # noqa: E402
        decode_liquidity, decode_slot0, pool_state_slots,
    )

    slot0_key, liq_key = pool_state_slots(POOL_ID)
    block_n, block_hash = _head(SEPOLIA_STATE_URL, opener=opener)
    pinned = hex(block_n)
    # extsload(bytes32)
    calls = {"slot0": "0x1e2eaeaf" + slot0_key[2:],
             "liquidity": "0x1e2eaeaf" + liq_key[2:]}
    body, resp, id_to_name = _call_batch(
        SEPOLIA_STATE_URL, POOL_MANAGER, calls, pinned, opener=opener)
    by_id = {str(e["id"]): e for e in resp}
    slot0_word = by_id[[k for k, v in id_to_name.items() if v == "slot0"][0]]["result"]
    liq_word = by_id[[k for k, v in id_to_name.items() if v == "liquidity"][0]]["result"]
    sqrt, tick, lp_fee = decode_slot0(slot0_word)
    write_pair(
        "pool_slot0",
        meta={
            "captured_at": _now_iso(),
            "chain": "sepolia",
            "chain_id": SEPOLIA_CHAIN_ID,
            "endpoint": SEPOLIA_STATE_URL,
            "block_number": block_n,
            "block_hash": block_hash,
            "block_tag": pinned,
            "pool_manager": POOL_MANAGER,
            "pool_id": POOL_ID,
            "mapping_slot": 6,
            "slot0_key": slot0_key,
            "liquidity_key": liq_key,
            "call_names": id_to_name,
            "note": (
                "PoolManager.extsload(bytes32) for the launch-3 pool, slots "
                "derived by data/surf_v4.pool_state_slots -- this fixture "
                "re-uses the repo's derivation rather than re-implementing it. "
                "The expected block below is what data/surf_v4.decode_slot0 and "
                "decode_liquidity return for these words."
            ),
            "expected": {
                "sqrt_price_x96": sqrt,
                "tick": tick,
                "lp_fee": lp_fee,
                "liquidity": decode_liquidity(liq_word),
            },
        },
        request={"url": SEPOLIA_STATE_URL, "method": "POST",
                 "headers": {"Content-Type": "application/json",
                             "User-Agent": USER_AGENT},
                 "body": body, "call_names": id_to_name},
        response=resp,
    )


# --------------------------------------------------------------------------
# the announce channel, as it is today
# --------------------------------------------------------------------------


def _decode_calldata_text(raw_input: str) -> str | None:
    if not raw_input or raw_input in ("0x", "0X"):
        return None
    try:
        return bytes.fromhex(raw_input[2:]).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None


def _looks_like_address(word: str) -> bool:
    return (len(word) == 42 and word.startswith("0x")
            and all(c in "0123456789abcdefABCDEF" for c in word[2:]))


def scan_for_candidates(text: str) -> list[str]:
    """Every 0x-prefixed 20-byte word in ``text``.  No filtering: this is the
    *unfiltered* scan, and it exists so the fixture can prove the channel is
    clean rather than assert it."""
    out: list[str] = []
    buf = ""
    for ch in text + " ":
        if ch in "0123456789abcdefABCDEFxX":
            buf += ch
        else:
            if _looks_like_address(buf):
                out.append(buf)
            buf = ""
    return out


def capture_announce(opener=_open) -> None:
    print("capture: announce")
    url = f"{MAINNET_BLOCKSCOUT}/addresses/{ANNOUNCE}/transactions"
    body = get_json(url, opener=opener)
    items = body.get("items") or []
    self_posts = []
    all_hits: list[dict] = []
    for it in items:
        frm = ((it.get("from") or {}).get("hash") or "").lower()
        to = ((it.get("to") or {}).get("hash") or "").lower()
        text = _decode_calldata_text(it.get("raw_input") or "")
        is_self = frm == to == ANNOUNCE.lower()
        if is_self:
            self_posts.append(it.get("hash"))
        for addr in scan_for_candidates(text or ""):
            all_hits.append({
                "address": addr,
                "tx_hash": it.get("hash"),
                "timestamp": it.get("timestamp"),
                "self_post": is_self,
                "from": frm,
                "to": to,
                "low_14_bits": "0x%04x" % (int(addr, 16) & 0x3FFF),
            })
    flagged = [h for h in all_hits
               if h["self_post"] and int(h["address"], 16) & 0x3FFF == 0x2840]
    write_pair(
        "announce_undiscovered",
        meta={
            "captured_at": _now_iso(),
            "chain": "mainnet",
            "chain_id": MAINNET_CHAIN_ID,
            "endpoint": url,
            "source": "blockscout /api/v2/addresses/{ANNOUNCE}/transactions",
            "announce": ANNOUNCE,
            "note": (
                "The announce channel exactly as it is today.  THE DAY-ONE "
                "PATH (plan R4): there is no mainnet pool4 post, so discovery "
                "must yield no candidate and pool4_discovery_state must read "
                "'not-discovered'.  The scan below is the evidence for that "
                "claim, not a restatement of it: every 0x-prefixed 20-byte "
                "word in every decoded calldata post on this page is listed, "
                "with its provenance and its low-14-bit flag field.  Blockscout "
                "returned next_page_params: null, so this single page is the "
                "channel's COMPLETE history -- the claim is exhaustive, not a "
                "statement about a recent window.\n\n"
                "SUPERSEDED 2026-09-02 for the question it was capturing: "
                "pool4 IS now live on mainnet.  What is captured here remains "
                "true of these bytes and this instant, and the DAY-ONE "
                "BEHAVIOUR it pins is unchanged and still the behaviour that "
                "runs -- the channel has not named the live hook even now.  "
                "See announce_still_unnamed.json for the post-launch capture "
                "of the same channel."
            ),
            "page_item_count": len(items),
            "next_page_params": body.get("next_page_params"),
            "is_complete_channel_history": body.get("next_page_params") is None,
            "self_post_count": len(self_posts),
            "address_shaped_words_found": all_hits,
            "hook_shaped_self_post_candidates": flagged,
            "expected": {
                "candidates": [],
                "discovery_state": "not-discovered",
                # AMENDMENT A16: name the stage.  This channel DOES carry
                # address-shaped words in self-posts, so the provenance stage
                # is NOT empty -- see address_shaped_words_found above, which
                # is the raw evidence rather than a normalised list this
                # package would be asserting on WP3's behalf.  What is empty is
                # the FLAG-FILTERED stage: not one of them masks to 0x2840.
                "candidates_stage": "flag_filtered",
                "flag_filtered_candidates": [],
                "provenance_candidates_evidence": "address_shaped_words_found",
            },
            "discovery_stages": {
                "provenance": "every address-shaped word in a self-post "
                              "(from_addr == to_addr == ANNOUNCE), "
                              "EIP-55-normalised and deduplicated",
                "flag_filtered": "the provenance output narrowed by "
                                 "addr & 0x3fff == 0x2840",
                "verdict": "fingerprint_verdict over the flag-filtered "
                           "survivors",
            },
        },
        request={"url": url, "method": "GET",
                 "headers": {"User-Agent": USER_AGENT}, "params": None},
        response=body,
    )
    if flagged:
        print("  !!! A HOOK-SHAPED ADDRESS APPEARS IN A SELF-POST:")
        for h in flagged:
            print("      ", json.dumps(h))
    else:
        print(f"  clean: {len(items)} txs, {len(self_posts)} self-posts, "
              f"{len(all_hits)} address-shaped words, 0 hook-shaped")


# --------------------------------------------------------------------------
# mainnet: proving nothing is there
# --------------------------------------------------------------------------


def capture_mainnet_absent(opener=_open) -> None:
    print("capture: mainnet-absent")
    block_n, block_hash = _head(MAINNET_STATE_URL, opener=opener)
    pinned = hex(block_n)
    probes = [
        ("sepolia_hook_launch3_on_mainnet", HOOK),
        ("sepolia_hook_launch1_on_mainnet", HOOK_LAUNCH_1),
        ("sepolia_hook_launch2_on_mainnet", HOOK_LAUNCH_2),
        ("sepolia_vault_on_mainnet", VAULT),
        ("sepolia_dripper_on_mainnet", DRIPPER),
        # The positive control.  Without it a page of "0x" answers proves the
        # probe was pointed at nothing, not that nothing is there.
        ("mainnet_imd_positive_control", MAINNET_IMD),
    ]
    body = []
    id_to_name = {}
    i = 0
    for label, addr in probes:
        i += 1
        body.append({"jsonrpc": "2.0", "id": i, "method": "eth_getCode",
                     "params": [addr, pinned]})
        id_to_name[str(i)] = f"{label}:eth_getCode"
        i += 1
        body.append({"jsonrpc": "2.0", "id": i, "method": "eth_call",
                     "params": [{"to": addr, "data": HOOK_GETTERS["token"]}, pinned]})
        id_to_name[str(i)] = f"{label}:token()"
    resp = post_json(MAINNET_STATE_URL, body, opener=opener)
    by_id = {str(e["id"]): e for e in resp}
    verdicts = {}
    for label, addr in probes:
        code_id = [k for k, v in id_to_name.items() if v == f"{label}:eth_getCode"][0]
        code = by_id[code_id].get("result")
        verdicts[label] = {
            "address": addr,
            "code": code,
            "code_bytes": 0 if code in (None, "0x") else (len(code) - 2) // 2,
            "deployed": bool(code and code != "0x"),
        }
    write_pair(
        "mainnet_absent",
        meta={
            "captured_at": _now_iso(),
            "chain": "mainnet",
            "chain_id": MAINNET_CHAIN_ID,
            "endpoint": MAINNET_STATE_URL,
            "block_number": block_n,
            "block_hash": block_hash,
            "block_tag": pinned,
            "call_names": id_to_name,
            "note": (
                "NO CODE EXISTS AT ANY OF THE FIVE PROBED ADDRESSES ON "
                "MAINNET.  Each Sepolia address is probed on mainnet with "
                "eth_getCode and a token() call; mainnet IMD is probed the "
                "same way as a POSITIVE CONTROL, so an empty answer is "
                "evidence of absence rather than evidence the probe was "
                "broken.  AMENDMENT A27 (2026-09-01) -- SCOPE: an earlier "
                "version of this note said 'mainnet has no pool4 hook, vault "
                "or dripper'.  THIS FIXTURE CANNOT PROVE THAT and does not.  A "
                "mainnet hook would be CREATE2-mined to a DIFFERENT address "
                "than any of these, so probing the Sepolia addresses can never "
                "enumerate the chain.  What this fixture proves is the narrow "
                "thing it measured: the launch-1/2/3 hooks, the vault and the "
                "dripper were not redeployed at the same addresses on mainnet. "
                "The evidence for 'pool4 is not live on mainnet' is "
                "announce_undiscovered.json -- the complete announce history "
                "with no post naming a hook -- and these probes corroborate "
                "it; neither is sufficient alone.\n\n"
                "SUPERSEDED 2026-09-02 -- POOL4 IS NOW LIVE ON MAINNET, at "
                "addresses none of these probes could ever have found: hook "
                + MAINNET_HOOK + ", vault " + MAINNET_VAULT + ", distributor "
                + MAINNET_DISTRIBUTOR + ".  This fixture is now HISTORICAL and "
                "its measurement is still exactly true -- those five Sepolia "
                "addresses hold no code on mainnet, and never did.  What it "
                "never proved, and what the launch demonstrates, is the "
                "general claim: an address-probe cannot enumerate a chain.  "
                "For the live deployment see the mainnet_* fixtures; for the "
                "state of discovery see announce_still_unnamed.json, which "
                "records that the channel has STILL not named the live hook."
            ),
            "verdicts": verdicts,
        },
        request={"url": MAINNET_STATE_URL, "method": "POST",
                 "headers": {"Content-Type": "application/json",
                             "User-Agent": USER_AGENT},
                 "body": body, "call_names": id_to_name},
        response=resp,
    )
    live = [k for k, v in verdicts.items()
            if v["deployed"] and k != "mainnet_imd_positive_control"]
    if live:
        print("  !!! SOMETHING IS DEPLOYED ON MAINNET AT:", live)
    else:
        print("  clean: no code at any pool4 address on mainnet; "
              "positive control has "
              f"{verdicts['mainnet_imd_positive_control']['code_bytes']} bytes")


# --------------------------------------------------------------------------
# Real provider errors.  The "dead" quadrant, captured rather than imagined.
# --------------------------------------------------------------------------

#: Endpoints measured 2026-09-01.  Each is here because it fails in a
#: DIFFERENT way, and CLAUDE.md's rule is that RPC errors are classified on
#: message text, not code -- providers reuse -32602/-32005 for unrelated
#: meanings.  This fixture is the evidence that rule is still true on Sepolia.
_ERROR_PROBES = [
    ("range_capped_getLogs", "https://1rpc.io/sepolia",
     {"jsonrpc": "2.0", "id": 1, "method": "eth_getLogs",
      "params": [{"address": HOOK, "fromBlock": hex(FLOW_FROM_BLOCK),
                  "toBlock": hex(FLOW_TO_BLOCK)}]},
     "A provider that serves eth_getLogs but caps the span. Its message names "
     "the cap; its CODE is the same -32602 another provider uses for a "
     "malformed param."),
    ("unknown_selector_revert", SEPOLIA_STATE_URL,
     {"jsonrpc": "2.0", "id": 1, "method": "eth_call",
      "params": [{"to": HOOK, "data": HOOK_ABSENT_GETTERS["bond"]}, "latest"]},
     "A getter the contract does not implement. This is what a mainnet hook "
     "built differently looks like, field by field."),
    ("call_to_an_empty_address", SEPOLIA_STATE_URL,
     {"jsonrpc": "2.0", "id": 1, "method": "eth_call",
      "params": [{"to": "0x00000000000000000000000000000000deadbeef",
                  "data": HOOK_GETTERS["token"]}, "latest"]},
     "An eth_call to an address with no code. Note it does NOT error: it "
     "returns 0x. A discovery gate that treats a successful response as an "
     "answered getter adopts an empty address."),
    ("malformed_params", SEPOLIA_STATE_URL,
     {"jsonrpc": "2.0", "id": 1, "method": "eth_call",
      "params": [{"to": "not-an-address", "data": "0x"}, "latest"]},
     "A genuinely malformed request, for contrast with the range cap above: "
     "same family of code, entirely different meaning."),
]


def capture_rpc_errors(opener=_open) -> None:
    print("capture: rpc-errors")
    observed = []
    for label, url, body, why in _ERROR_PROBES:
        entry = {"label": label, "url": url, "request": body, "why": why}
        try:
            entry["response"] = post_json(url, body, opener=opener)
        except urllib.error.HTTPError as exc:
            entry["http_status"] = exc.code
            entry["response"] = None
            entry["transport_error"] = str(exc)
        except Exception as exc:  # noqa: BLE001
            entry["response"] = None
            entry["transport_error"] = repr(exc)
        r = entry.get("response")
        if isinstance(r, dict) and "error" in r:
            entry["error_code"] = r["error"].get("code")
            entry["error_message"] = r["error"].get("message")
        elif isinstance(r, dict):
            entry["result"] = r.get("result")
        observed.append(entry)
        print(f"  {label:26s} "
              f"{entry.get('error_message') or entry.get('result') or entry.get('transport_error')}")
    write_pair(
        "rpc_error_states",
        meta={
            "captured_at": _now_iso(),
            "chain": "sepolia",
            "chain_id": SEPOLIA_CHAIN_ID,
            "endpoint": SEPOLIA_STATE_URL,
            "note": (
                "The 'dead' quadrant, captured from real providers rather than "
                "imagined.  Four failures with four different meanings.  Two "
                "things WP6 must read out of this: the error CODES collide "
                "across unrelated meanings, so classification goes on message "
                "text (CLAUDE.md); and an eth_call to an address with no code "
                "SUCCEEDS with '0x', so 'the call did not error' is not "
                "'the getter answered' -- a fingerprint gate that conflates "
                "the two adopts an empty address."
            ),
            "probes": observed,
        },
        request={"url": "several -- see probes[].url", "method": "POST",
                 "headers": {"Content-Type": "application/json",
                             "User-Agent": USER_AGENT},
                 "body": [p["request"] for p in observed],
                 "urls": [p["url"] for p in observed]},
        response=[p.get("response") for p in observed],
    )


# --------------------------------------------------------------------------
# The adversarial corpora.  SYNTHETIC, and every one says so.
# --------------------------------------------------------------------------

#: The flag word the chain actually shows (see hook_flags_reference.json).
POOL4_FLAG_WORD = 0x2840
HOOK_FLAG_MASK = 0x3FFF

_SYN_TS = 1788361200.0  # 2026-09-01T03:00:00Z, fixed so replays are deterministic


def _eip55(addr_hex: str) -> str:
    sys.path.insert(0, str(ROOT))
    from maxpane_dashboard.data.keccak import keccak256  # noqa: E402
    low = addr_hex.lower().replace("0x", "")
    digest = keccak256(low.encode()).hex()
    return "0x" + "".join(
        c.upper() if c in "abcdef" and int(digest[i], 16) >= 8 else c
        for i, c in enumerate(low)
    )


def _synth_addr(tag: str, low16: int) -> str:
    """A plainly synthetic 20-byte address whose low 16 bits are ``low16``.

    The ``5afe`` prefix and the tag make it obvious in a diff that this is not
    a chain address anybody should probe.
    """
    tag_hex = "".join(c for c in tag.lower() if c in "0123456789abcdef")
    middle = (tag_hex + "0" * 32)[:32]
    return _eip55("0x5afe" + middle + "%04x" % low16)


def _row(kind, frm, to, text, tx_hash, *, ts=_SYN_TS, label=None,
         from_label=None, value_eth=0.0):
    """One ``SURF_ROW_KEYS['feed_items']`` row, field-for-field."""
    return {
        "ts": ts,
        "kind": kind,
        "from_addr": frm,
        "to_addr": to,
        "from_label": from_label,
        "text": text,
        "tx_hash": tx_hash,
        "label": label,
        "value_eth": value_eth,
    }


def _blockscout_item(row: dict) -> dict:
    text = row["text"] or ""
    return {
        "hash": row["tx_hash"],
        "from": {"hash": row["from_addr"], "ens_domain_name": None,
                 "is_contract": False, "name": None},
        "to": {"hash": row["to_addr"], "ens_domain_name": None,
               "is_contract": False, "name": None},
        "raw_input": "0x" + text.encode("utf-8").hex(),
        "value": "0",
        "method": None,
        "decoded_input": None,
        "status": "ok",
        "result": "success",
        "timestamp": _dt.datetime.fromtimestamp(
            row["ts"], _dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000000Z"),
        "block_number": 25800000,
    }


def _answers(addr, *, token=None, reward_share_bps="0x3e8",
             bps_denominator="0x2710", burn_sink=None, pool_manager=None,
             dead=False):
    """One address's already-fetched ``eth_call`` answers.

    ``None`` for a getter means it reverted -- the shape ``fingerprint_verdict``
    takes.  ``dead=True`` reverts everything.
    """
    def w(v):
        if v is None:
            return None
        if v.startswith("0x") and len(v) == 42:
            return "0x" + "0" * 24 + v[2:].lower()
        return "0x" + v.replace("0x", "").rjust(64, "0")

    if dead:
        return {k: None for k in
                ("token", "rewardShareBps", "BPS_DENOMINATOR", "burnSink",
                 "poolManager")}
    return {
        "token": w(token),
        "rewardShareBps": w(reward_share_bps),
        "BPS_DENOMINATOR": w(bps_denominator),
        "burnSink": w(burn_sink or BURN_SINK),
        "poolManager": w(pool_manager
                         or "0x000000000004444c5dc75cB358380D2e3dE08A90"),
    }


def synthesize() -> None:
    print("synthesize: the adversarial announce corpora")
    ann = ANNOUNCE
    stranger = _eip55("0x5afe" + "b0b0" * 8 + "0001")

    good = _synth_addr("g00dh00c", POOL4_FLAG_WORD)
    wrong_flags = _synth_addr("badf1a65", 0x0840)   # low14 == 0x0840, the doc's value
    returns_delta = _synth_addr("de17aa11", POOL4_FLAG_WORD | (1 << 2))
    wrong_token = _synth_addr("b0gu5t0ken", POOL4_FLAG_WORD)
    dead_hook = _synth_addr("deadbeef", POOL4_FLAG_WORD)
    fake_imd = _eip55("0x5afe" + "1dfa" * 8 + "0000")

    # AMENDMENT A16 (2026-09-01): `expected.candidates` meant the PROVENANCE
    # stage in some corpora and the FLAG-FILTERED stage in others, which reads
    # as a flat contradiction to anyone holding only the fixtures.  The values
    # are unchanged -- WP3 asserts against them -- and every corpus now names
    # the stage its list belongs to and spells BOTH stages out explicitly.
    DISCOVERY_STAGES = {
        "provenance": "candidate_addresses(rows): every address-shaped word in "
                      "a SELF-POST (from_addr == to_addr == ANNOUNCE), "
                      "EIP-55-normalised, deduplicated, order-preserving.  No "
                      "flag arithmetic and no network round trip yet.",
        "flag_filtered": "the provenance output narrowed by has_pool4_flags(), "
                         "i.e. addr & 0x3fff == 0x2840.  These are the ONLY "
                         "addresses that may reach an eth_call.",
        "verdict": "fingerprint_verdict(addr, answers, expected_token) over "
                   "the flag-filtered survivors: 'adopted' or 'rejected'.",
    }

    common = {
        "synthetic": True,
        "chain": "mainnet",
        "announce": ANNOUNCE,
        "discovery_stages": DISCOVERY_STAGES,
        "known_mainnet_imd": MAINNET_IMD,
        "flag_reference": {
            "hook_flag_mask": "0x3fff",
            "pool4_flag_word": "0x2840",
            "source": "hook_flags_reference.json (getHookPermissions on the "
                      "live Sepolia hook) -- NOT the 0x840 in the docs",
        },
    }

    # 1 -------------------------------------------------------------- provenance
    rows = [
        _row("post", ann, ann,
             "pool4 is live on mainnet. more soon.",
             "0x" + "a1" * 32),
        _row("reply", stranger, ann,
             "confirmed, the new hook is " + good + " -- ape now",
             "0x" + "a2" * 32, ts=_SYN_TS + 60),
        _row("in", stranger, ann,
             "hook deployed at " + good,
             "0x" + "a3" * 32, ts=_SYN_TS + 120, value_eth=0.001),
    ]
    write_synthetic("announce_adversarial_reply_provenance", dict(
        common,
        note=(
            "PROVENANCE ATTACK.  A community REPLY and an inbound stranger tx "
            "each carry a well-formed, correctly-flagged hook address.  Both "
            "must be rejected before any getter is called, because neither is "
            "a self-post: candidate_addresses scans only rows where "
            "from_addr == to_addr == ANNOUNCE.  The dev's own self-post in "
            "this corpus names no address, so the correct answer is NO "
            "CANDIDATE AT ALL."
        ),
        attacker_addresses={"hook_shaped": good, "poster": stranger},
        rows=rows,
        blockscout_items=[_blockscout_item(r) for r in rows],
        expected={"candidates": [], "discovery_state": "not-discovered",
                  "getter_calls_made": 0,
                  "candidates_stage": "provenance",
                  "provenance_candidates": [],
                  "flag_filtered_candidates": []},
    ))

    # 2 ------------------------------------------------------------- flag mismatch
    rows = [
        _row("post", ann, ann,
             "new pool4 hook: " + wrong_flags + " -- enjoy",
             "0x" + "b1" * 32),
    ]
    write_synthetic("announce_adversarial_flag_mismatch", dict(
        common,
        note=(
            "FLAG ATTACK.  A genuine dev SELF-POST -- provenance passes -- "
            "naming an address whose low 14 bits are 0x0840, which is what "
            "docs/imd_pool4_mechanics.md and the implementation plan both "
            "claim the real hook carries.  The chain says the real value is "
            "0x2840 (BEFORE_INITIALIZE is set as well).  This address is "
            "therefore a hook the PoolManager would never call "
            "beforeAddLiquidity+beforeInitialize on, and it must be REJECTED "
            "with a detail naming the flag gate.  A gate built from the "
            "documented 0x840 would ADOPT this address and reject the real "
            "hook -- exactly backwards."
        ),
        attacker_addresses={"candidate": wrong_flags,
                            "low_14_bits": "0x0840"},
        rows=rows,
        blockscout_items=[_blockscout_item(r) for r in rows],
        eth_call_answers={wrong_flags.lower(): _answers(
            wrong_flags, token=MAINNET_IMD)},
        expected={"candidates": [wrong_flags],
                  "verdict_state": "rejected",
                  "verdict_detail_names": "flags",
                  "discovery_state": "rejected",
                  "candidates_stage": "provenance",
                  "provenance_candidates": [wrong_flags],
                  "flag_filtered_candidates": []},
    ))

    # 3 ------------------------------------------------------------ returns-delta
    rows = [
        _row("post", ann, ann,
             "pool4 mainnet hook " + returns_delta,
             "0x" + "c1" * 32),
    ]
    write_synthetic("announce_adversarial_returns_delta", dict(
        common,
        note=(
            "SUBSET-vs-EQUALITY ATTACK.  A self-post naming an address that "
            "sets every flag the real hook sets PLUS "
            "AFTER_SWAP_RETURNS_DELTA (1<<2).  A subset test ('does it have "
            "the flags we need?') lets it through the FLAG gate, and because "
            "this corpus's answers satisfy the rest of the fingerprint it is "
            "then ADOPTED end to end; the equality test the plan mandates "
            "rejects it at the flag gate.  A hook that returns a swap delta is a "
            "materially different contract -- it can take value out of the "
            "swap itself -- so this is the case that decides whether the gate "
            "is written with & or ==."
        ),
        attacker_addresses={"candidate": returns_delta,
                            "low_14_bits": "0x%04x" % (
                                POOL4_FLAG_WORD | (1 << 2))},
        rows=rows,
        blockscout_items=[_blockscout_item(r) for r in rows],
        eth_call_answers={returns_delta.lower(): _answers(
            returns_delta, token=MAINNET_IMD)},
        expected={"candidates": [returns_delta],
                  "verdict_state": "rejected",
                  "verdict_detail_names": "flags",
                  "discovery_state": "rejected",
                  "candidates_stage": "provenance",
                  "provenance_candidates": [returns_delta],
                  "flag_filtered_candidates": []},
    ))

    # 4 ---------------------------------------------------------------- token gate
    rows = [
        _row("post", ann, ann,
             "the new hook is live: " + wrong_token,
             "0x" + "d1" * 32),
    ]
    write_synthetic("announce_adversarial_wrong_token", dict(
        common,
        note=(
            "TOKEN ATTACK.  A self-post naming an address with the CORRECT "
            "flag word (0x2840) whose five getters all answer, but whose "
            "token() is a stranger's ERC-20 "
            "rather than mainnet IMD (" + MAINNET_IMD + ").  This is the most "
            "dangerous case in the set, because everything except the token "
            "identity checks out and the panel would render an attacker's pool "
            "as the protocol's.  Must be REJECTED with a detail naming token.  "
            "AMENDMENT A27 (2026-09-01): an earlier version of this note said "
            "the five answering getters made this 'a real hook-shaped "
            "contract'.  THEY DO NOT.  Four of the five are pure liveness "
            "checks that any contract passes, and token() is a value the "
            "candidate's own contract chooses -- which is why the whole "
            "fingerprint is forgeable and why PROVENANCE, not the fingerprint, "
            "is the gate that actually holds.  What this corpus demonstrates "
            "is narrower than it used to claim: given a candidate that already "
            "cleared provenance, the token gate is what separates the "
            "protocol's hook from a look-alike."
        ),
        attacker_addresses={"candidate": wrong_token, "token_returned": fake_imd},
        rows=rows,
        blockscout_items=[_blockscout_item(r) for r in rows],
        eth_call_answers={wrong_token.lower(): _answers(
            wrong_token, token=fake_imd)},
        expected={"candidates": [wrong_token],
                  "verdict_state": "rejected",
                  "verdict_detail_names": "token",
                  "discovery_state": "rejected",
                  "candidates_stage": "provenance",
                  "provenance_candidates": [wrong_token],
                  "flag_filtered_candidates": [wrong_token],
                  "stage_note": "this candidate clears BOTH the provenance and "
                                "the flag stage -- the two lists coincide here, "
                                "and the token gate is what rejects it"},
    ))

    # 5 --------------------------------------------------------------- dead getters
    rows = [
        _row("post", ann, ann,
             "pool4: " + dead_hook,
             "0x" + "e1" * 32),
    ]
    write_synthetic("announce_adversarial_dead_getters", dict(
        common,
        note=(
            "SILENT-CONTRACT ATTACK.  A self-post naming an address with the "
            "correct flag word whose every getter REVERTS -- a deployed "
            "contract with no such function and no fallback.  Must be "
            "REJECTED, and must never be mistaken for 'we could not read it, "
            "try again': an unreadable candidate is not an adopted one.  "
            "AMENDMENT A27 (2026-09-01): an earlier version of this note "
            "listed 'an EOA' among the causes.  IT IS NOT ONE, AND THIS "
            "CORPUS'S OWN rpc_error_states.json DISPROVES IT: an eth_call to "
            "an address with no code SUCCEEDS and returns '0x'.  An EOA is "
            "therefore the OPPOSITE case -- it answers every getter without "
            "erroring -- and it is caught by requiring a decodable word, not "
            "by noticing a revert.  A gate that only watches for reverts "
            "adopts the EOA."
        ),
        attacker_addresses={"candidate": dead_hook},
        rows=rows,
        blockscout_items=[_blockscout_item(r) for r in rows],
        eth_call_answers={dead_hook.lower(): _answers(dead_hook, dead=True)},
        expected={"candidates": [dead_hook],
                  "verdict_state": "rejected",
                  "verdict_detail_names": "token",
                  "verdict_detail_note": "the first gate in the plan's order "
                                         "whose getter is dead",
                  "discovery_state": "rejected",
                  "candidates_stage": "provenance",
                  "provenance_candidates": [dead_hook],
                  "flag_filtered_candidates": [dead_hook],
                  "stage_note": "clears provenance AND the flag stage; the "
                                "dead getters are what reject it"},
    ))

    # 6 ------------------------------------------------------------ many candidates
    # Every decoy must MISS the flag word, or the corpus does not encode the
    # attack it claims: "twenty addresses, exactly one of which is a hook".
    decoys = [_synth_addr("dec0%03d" % i,
                          (POOL4_FLAG_WORD + (i + 1) * 7) & HOOK_FLAG_MASK)
              for i in range(19)]
    assert all(int(d, 16) & HOOK_FLAG_MASK != POOL4_FLAG_WORD for d in decoys)
    blob = " ".join(decoys[:9] + [good] + decoys[9:])
    rows = [
        _row("post", ann, ann,
             "migration addresses, one of these is the hook: " + blob,
             "0x" + "f1" * 32),
    ]
    write_synthetic("announce_adversarial_many_candidates", dict(
        common,
        note=(
            "FLOODING ATTACK.  One self-post carrying TWENTY address-shaped "
            "words, exactly one of which carries the real flag word.  The "
            "nineteen decoys must never reach a getter call: the flag gate is "
            "pure arithmetic on the address and runs BEFORE any network round "
            "trip, so a post like this costs one eth_call round, not twenty. "
            "A discovery path that verifies first and filters second turns the "
            "announce channel into an RPC amplifier.  AMENDMENT A16 "
            "(2026-09-01): an earlier version of this note implied all "
            "nineteen decoys defeat a SUBSET test.  They do not.  TEN of the "
            "nineteen (0x2847, 0x284e, 0x2855, 0x285c, 0x2863, 0x286a, "
            "0x2871, 0x2878, 0x287f, 0x28c5) are supersets of 0x2840 and are "
            "the ones a subset gate would wrongly adopt; the other NINE "
            "(0x2886, 0x288d, 0x2894, 0x289b, 0x28a2, 0x28a9, 0x28b0, "
            "0x28b7, 0x28be) clear a bit the hook sets, so a subset gate "
            "rejects them anyway and they only exercise the flood.  All "
            "nineteen fail the EQUALITY gate, which is the one the plan "
            "mandates.  See expected.decoys_defeating_a_subset_test."
        ),
        attacker_addresses={"valid": good, "decoys": decoys},
        rows=rows,
        blockscout_items=[_blockscout_item(r) for r in rows],
        eth_call_answers={good.lower(): _answers(good, token=MAINNET_IMD)},
        expected={"candidates": [good],
                  "candidates_that_reach_a_getter": [good],
                  "verdict_state": "adopted",
                  "discovery_state": "adopted",
                  "expected_getter_rounds": 1,
                  "candidates_stage": "flag_filtered",
                  "provenance_candidates": decoys[:9] + [good] + decoys[9:],
                  "flag_filtered_candidates": [good],
                  "decoys_defeating_a_subset_test": [
                      d for d in decoys
                      if int(d, 16) & HOOK_FLAG_MASK & POOL4_FLAG_WORD
                      == POOL4_FLAG_WORD],
                  "decoys_a_subset_test_rejects_anyway": [
                      d for d in decoys
                      if int(d, 16) & HOOK_FLAG_MASK & POOL4_FLAG_WORD
                      != POOL4_FLAG_WORD],
                  "stage_note": "provenance yields all TWENTY; the flag stage "
                                "narrows it to one.  This fixture's "
                                "`candidates` is the FLAG-FILTERED list -- "
                                "that is the whole point of the attack"},
    ))

    # 7 ---------------------------------------------------------------- markup
    ctrl = "[31m"
    markup_rows = [
        _row("post", ann, ann,
             "[/x] hook at [$warning]" + good + "[/] see " + ctrl,
             "0x" + "1a" * 32),
        _row("post", ann, ann,
             "0x" + "[/x]" * 10 + "  <- forty characters of markup, not an address",
             "0x" + "1b" * 32, ts=_SYN_TS + 60),
        _row("post", ann, ann,
             "0x‮deadbeefdeadbeefdeadbeefdeadbeefdead2840‬",
             "0x" + "1c" * 32, ts=_SYN_TS + 120),
        _row("post", ann, ann, None, "0x" + "1d" * 32, ts=_SYN_TS + 180),
    ]
    write_synthetic("announce_adversarial_markup", dict(
        common,
        note=(
            "MARKUP / CONTROL-CHARACTER ATTACK.  Four self-posts: a valid "
            "address wrapped in Textual markup and an ANSI escape; a literal "
            "'0x' followed by forty characters of markup, which is address-"
            "SHAPED in length but is not hex and must yield no candidate; an "
            "address wrapped in bidi overrides (U+202E/U+202C), which reorder "
            "the rendered text without changing the bytes; and a post whose "
            "text is None.  Nothing here may raise, and the only candidate is "
            "the first post's address -- extracted, not the surrounding "
            "markup.  AMENDMENT A27 (2026-09-01) -- WHY, precisely, because "
            "the earlier note was right for a reason it never gave: the "
            "bidi-wrapped post yields no candidate ONLY because U+202E sits "
            "BETWEEN the '0x' and the hex, so a scanner reading raw text sees "
            "'0x' and forty hex digits as two separate tokens and matches "
            "neither.  A scanner that STRIPS control characters first would "
            "extract 0xdeadbeef...dead2840, which masks to 0x2840 and would "
            "reach a getter call.  That is the distinction this row exists to "
            "draw; either behaviour is defensible PROVIDED the rendered string "
            "is escaped, and what must never happen is extracting the address "
            "while rendering the reordered text.  Every string in this corpus "
            "must survive "
            "widgets/markup_safety.safe_markup and reach a Static as a "
            "pre-built rich.text.Text, per CLAUDE.md's SurfFeed._row_text rule."
        ),
        attacker_addresses={"valid": good,
                            "bidi_wrapped":
                                "0xdeadbeefdeadbeefdeadbeefdeadbeefdead2840"},
        rows=markup_rows,
        blockscout_items=[_blockscout_item(r) for r in markup_rows
                          if r["text"] is not None],
        eth_call_answers={good.lower(): _answers(good, token=MAINNET_IMD)},
        expected={"candidates_must_include": [good],
                  "must_not_raise": True,
                  "markup_word_is_not_a_candidate": True,
                  "candidates_stage": "provenance",
                  "stage_note": "a lower bound, not an exact list: the point "
                                "is that nothing raises and that the markup "
                                "run is not mistaken for an address"},
    ))

    # 8 ------------------------------------------------ hostile persisted payload
    hostile = _synth_addr("cac4ed00", 0x0000)
    write_synthetic("discovery_persisted_hostile", dict(
        common,
        note=(
            "A PERSISTED pool4 discovery payload, as it would sit in "
            "~/.maxpane/, hand-edited to claim 'adopted'.  The claimed hook's "
            "low 14 bits are 0x0000 and its token() answer is a stranger's "
            "ERC-20, so it fails both the flag gate and the token gate.  Those "
            "are the fixture's contents; the test that reads it names what it "
            "demonstrates.\n\n"
            "AMENDMENT A27 (2026-09-01) -- WHAT THIS FIXTURE NO LONGER SHOWS.  "
            "An earlier version of this note said 'the manager must RE-VERIFY "
            "a persisted adoption on read'.  THAT DEFENCE HAS BEEN DELETED, "
            "not weakened.  WP7 removed the persisted address from the "
            "candidate set entirely and WP3 deleted reverify_persisted, so "
            "THE CACHE NOMINATES NOTHING AND A PERSISTED ADDRESS IS NEVER "
            "ADJUDICATED -- there is no verdict to re-verify, because there is "
            "no candidate.  The reason is that the fingerprint is FORGEABLE: a "
            "0x2840-shaped address was mined in ~16,000 tries by the security "
            "pass and in 20,141 tries -- under a second -- by WP3, and "
            "fingerprint_verdict returns 'adopted' for such an address as soon "
            "as its own contract answers real mainnet IMD to token() and zero "
            "words to the rest, four of the five getters being pure liveness "
            "checks any contract passes.  The old promise held ONLY for this "
            "fixture's 0x0000 address; against an attacker who mines one it "
            "returned 'adopted'.  PROVENANCE -- a transaction signed by the "
            "announce wallet -- IS THE ONLY UNFORGEABLE GATE, and the "
            "persisted path was the one path that skipped it.  If the "
            "self-post naming the hook ever ages out of the channel window "
            "(~64 days, S15), the fix is to read more of the channel or to "
            "re-establish provenance from the chain, NEVER to re-nominate from "
            "storage."
        ),
        persisted_payload={
            "pool4_network": "MAINNET",
            "pool4_discovery_state": "adopted",
            "pool4_discovery_detail": "adopted from announce post 0x0000",
            "pool4_hook_addr": hostile,
            "pool4_token_addr": _eip55("0x5afe" + "1dfa" * 8 + "0000"),
            "pool4_vault_addr": _synth_addr("faceva17", 0x0000),
            "pool4_dripper_addr": _synth_addr("faced819", 0x0000),
            "pool4_as_of_hhmm": "03:00",
        },
        attacker_addresses={"claimed_hook": hostile,
                            "low_14_bits": "0x0000"},
        eth_call_answers={hostile.lower(): _answers(
            hostile, token=_eip55("0x5afe" + "1dfa" * 8 + "0000"))},
        # A27: `trusted_on_read` and `discovery_state_after_reverify` USED to
        # sit here.  They are DELETED, not deprecated: they named a
        # persisted-adoption re-verification that no longer exists, and a
        # reassuring key describing a deleted defence is the same
        # false-assurance shape as a reassuring sentence -- just in JSON.
        expected={"verdict_state": "rejected",
                  "verdict_detail_names": "flags",
                  "_amendment": (
                      "A27: the cache nominates nothing, so a persisted "
                      "address is never adjudicated by the manager at all.  "
                      "'verdict_state' is meaningful only because a TEST may "
                      "hand this address to verify_hook directly, which is a "
                      "thing a test can do and the discovery path cannot.  Two "
                      "keys naming a re-verification step -- 'trusted_on_read' "
                      "and 'discovery_state_after_reverify' -- were deleted "
                      "here rather than left as vestigial reassurance."),
                  "persisted_address_is_a_discovery_candidate": False},
    ))


# --------------------------------------------------------------------------
# --reconcile: settle the recovered interface against its own log set
# --------------------------------------------------------------------------

_WEI = 10 ** 18


def _answers_by_name(name: str) -> dict:
    fx = json.loads((OUT / f"{name}.json").read_text())
    ids = {v: k for k, v in fx["call_names"].items()}
    by_id = {str(e["id"]): e for e in fx["response"]}
    return {n: by_id[i].get("result") for n, i in ids.items()}


def _data_words(data: str) -> list[int]:
    raw = data[2:]
    return [int(raw[i:i + 64], 16) for i in range(0, len(raw), 64)]


def _corroborations() -> list[dict]:
    """What other committed fixtures settle, computed rather than asserted."""
    hook = _answers_by_name("hook_state_healthy")
    token = _answers_by_name("token_state")
    vault = _answers_by_name("vault_state")
    drip = _answers_by_name("dripper_state")
    slot = json.loads((OUT / "pool_slot0.json").read_text())
    exp = slot["expected"]

    def i(d, n):
        return int(d[n], 16)

    tick = i(hook, "currentTick")
    if tick >= 1 << 23:
        tick -= 1 << 24
    addr = lambda w: "0x" + w[-40:].lower()  # noqa: E731
    out = [
        {"getters": ["currentTick", "currentSqrtPriceX96",
                     "positionLiquidity", "lpFee"],
         "source": "pool_slot0.json -- PoolManager.extsload, the canonical v4 "
                   "singleton, VERIFIED SOURCE",
         "agrees": (tick == exp["tick"]
                    and i(hook, "currentSqrtPriceX96") == exp["sqrt_price_x96"]
                    and i(hook, "positionLiquidity") == exp["liquidity"]
                    and i(hook, "lpFee") == exp["lp_fee"]),
         "note": "the strongest corroboration in the corpus: an unverified "
                 "contract's four position getters, confirmed word for word by "
                 "the verified contract that owns the state.  CAVEAT FOR A "
                 "LIVE CONTROL: these two fixtures were captured one block "
                 "apart and agree only because the pool was quiet.  A control "
                 "must read the hook and the extsload words in THE SAME SWEEP, "
                 "or a moving pool reports false drift."},
        {"getters": ["burnSink"],
         "source": "token_state.json -- balanceOf(0xdEaD)",
         "agrees": (addr(hook["burnSink"]).endswith("dead")
                    and i(hook, "totalBurned") == i(token, "balanceOf_dead")),
         "note": "the totalBurned check settles the SINK ADDRESS as well as "
                 "the counter: the burned total lands at the address burnSink "
                 "names."},
        {"getters": ["rewardsRecipient"],
         "source": "dripper_state.json + vault_state.json -- the address chain",
         # Each link compared against the OTHER contract's answer or the
         # known address -- never against itself.  An earlier draft wrote
         # `x == "0x" + x[2:]`, which is true for every string.
         "agrees": (addr(hook["rewardsRecipient"]) == DRIPPER.lower()
                    and addr(drip["vault"]) == VAULT.lower()
                    and addr(drip["imd"]) == addr(vault["asset"])
                    and addr(vault["asset"]) == TOKEN.lower()),
         "note": "hook.rewardsRecipient -> dripper.vault -> vault.asset closes "
                 "on the same token the pool trades.  This is the chain a "
                 "hostile setRewardsRecipient would break, and each link is a "
                 "live read."},
        {"getters": ["vault.totalAssets"],
         "source": "token_state.json -- balanceOf(vault)",
         "agrees": i(token, "balanceOf_vault") == i(vault, "totalAssets"),
         "note": "the vault holds exactly what it reports."},
    ]
    return out


def reconcile() -> int:
    """R1's control (c): cross-checks the chain itself can settle.

    Reads only committed fixtures, so it runs offline.  Writes
    ``counter_reconciliation.json``: evidence ABOUT the corpus, not a lookup
    table -- WP3 must recompute these from the raw fixtures and compare, never
    read the numbers out of this file.
    """
    _install_socket_guard()
    hook = _answers_by_name("hook_state_healthy")
    token = _answers_by_name("token_state")
    logs = json.loads((OUT / "flow_logs_full.json").read_text())
    topics = {v: k for k, v in logs["topic0_map"].items()}

    fee_imd = fee_eth = burned = rewarded = settled_eth = 0
    wd_imd = wd_eth = 0
    for lg in logs["response"]["result"]:
        t0 = lg["topics"][0]
        w = _data_words(lg["data"])
        if t0 == topics["FeeCollected(uint256,uint256)"]:
            fee_imd += w[0]
            fee_eth += w[1]
        elif t0 == topics["ClaimsSettled(uint256,uint256,uint256)"]:
            burned += w[0]
            rewarded += w[1]
            settled_eth += w[2]
        elif t0 == topics["FeesWithdrawn(address,uint256,uint256)"]:
            wd_imd += w[0]
            wd_eth += w[1]

    def counter(n):
        return int(hook[n], 16)

    checks = {
        "sum_FeeCollected_imd == totalFeeToken()": {
            "from_logs": fee_imd, "from_counter": counter("totalFeeToken")},
        "sum_ClaimsSettled_0 == totalBurned()": {
            "from_logs": burned, "from_counter": counter("totalBurned")},
        "sum_ClaimsSettled_1 == totalRewarded()": {
            "from_logs": rewarded, "from_counter": counter("totalRewarded")},
        "totalBurned() == token.balanceOf(0xdEaD)": {
            "from_logs": int(token["balanceOf_dead"], 16),
            "from_counter": counter("totalBurned")},
        "sum_FeeCollected_eth == retainedEth()": {
            "from_logs": fee_eth, "from_counter": counter("retainedEth")},
    }
    for c in checks.values():
        c["agree"] = c["from_logs"] == c["from_counter"]
        c["delta_wei"] = c["from_logs"] - c["from_counter"]

    total = fee_imd + burned + rewarded
    payload = {
        "fixture": "counter_reconciliation",
        "synthetic": False,
        "derived_from": ["hook_state_healthy.json", "token_state.json",
                         "flow_logs_full.json"],
        "generated_at": _now_iso(),
        "note": (
            "R1's control (c), run over the committed corpus.  FOUR OF FIVE "
            "CROSS-CHECKS RECONCILE TO THE WEI.  SCOPE (A27): the five "
            "checks below settle SIX getters -- totalFeeToken, totalBurned, "
            "totalRewarded, retainedEth, rewardShareBps and BPS_DENOMINATOR -- "
            "against the log set and the token's dEaD balance, and that is ALL "
            "they settle.  A further SEVEN are settled by other fixtures and "
            "are listed under corroborated_by_other_fixtures; the strongest of "
            "those is currentTick / currentSqrtPriceX96 / positionLiquidity / "
            "lpFee, confirmed word for word by PoolManager.extsload -- the "
            "canonical, VERIFIED-SOURCE v4 singleton corroborating an "
            "unverified contract, which is a better class of evidence than any "
            "log sum.  (An earlier version of this note said the position "
            "getters had no cross-check.  Four of them do; it is just not a "
            "LOG cross-check.)  ELEVEN getters remain settled by nothing, "
            "listed under not_covered_by_any_cross_check, and the two that "
            "matter most are capFloor -- inferred, not proven (plan R2), and "
            "owner-settable -- and tokensInPool, the RATCHET headline, which "
            "nothing outside the hook states.  One plausible identity that "
            "does NOT hold is recorded under rejected_identities so a live "
            "control is not built on it.  THE FIFTH "
            "IS NOT A DEFECT AND MUST NOT BE PUBLISHED AS ONE: totalFeeToken() "
            "is CUMULATIVE and retainedEth() is a CURRENT BALANCE.  The owner "
            "withdrew 3,650,057.78 IMD and 0.0057 ETH across the two "
            "FeesWithdrawn events in this log set -- every token and every wei "
            "of fee ever collected -- and afterwards totalFeeToken() still "
            "reads the full 3,650,057.78 while retainedEth() reads 0.  A "
            "symmetric ETH cross-check would therefore report 'the recovered "
            "interface is wrong' on a perfectly healthy hook, every time the "
            "owner withdraws.  Compare Sum(FeeCollected eth) against "
            "Sum(FeesWithdrawn eth) + retainedEth() instead."
        ),
        "checks": checks,
        "withdrawn": {"imd_wei": wd_imd, "eth_wei": wd_eth,
                      "eth_identity_holds":
                          fee_eth == wd_eth + counter("retainedEth"),
                      "imd_identity_note":
                          "totalFeeToken() is unaffected by a withdrawal"},
        "measured_split_pct_from_counters": {
            "inference": 100.0 * fee_imd / total,
            "burn": 100.0 * burned / total,
            "stakers": 100.0 * rewarded / total,
        },
        "claimed_share": {
            "rewardShareBps": counter("rewardShareBps"),
            "BPS_DENOMINATOR": counter("BPS_DENOMINATOR"),
            "stakers_share_of_post_fee_pct":
                100.0 * rewarded / (burned + rewarded),
        },
        "ratchet": {
            "tokensInPool_wei": counter("tokensInPool"),
            "capFloor_wei": counter("capFloor"),
            "floor_distance_wei": counter("tokensInPool") - counter("capFloor"),
            "total_supply_wei": int(token["totalSupply"], 16),
            "burned_supply_pct":
                100.0 * counter("totalBurned") / int(token["totalSupply"], 16),
        },
        "settled_eth_wei": settled_eth,
        # A27 scoping.  The five checks above settle SIX getters.  These are
        # the ones settled by OTHER fixtures, and they matter because the
        # corroborating source is the canonical, VERIFIED-SOURCE v4
        # PoolManager rather than the unverified hook talking about itself.
        "corroborated_by_other_fixtures": _corroborations(),
        # Named so nobody has to rediscover them: getters nothing in this
        # corpus can settle.
        "not_covered_by_any_cross_check": [
            "capFloor -- meaning INFERRED, not proven (plan R2); the single "
            "most consequential number on the RATCHET panel and the one an "
            "owner can move with setCapFloor",
            "tokensInPool -- the ratchet headline; no log and no PoolManager "
            "word states the hook's own reserve.  Could be corroborated by "
            "token.balanceOf(PoolManager) on a chain where this token trades "
            "in only one pool; that call is NOT in this corpus",
            "ethInPool", "lastClaimBlock", "refTick", "tickLower", "tickUpper",
            "keeperReward", "marketOpen", "rebalanceEnabled",
            "backstop -- the second position; nothing outside the hook "
            "describes it",
        ],
        # A plausible identity that DOES NOT HOLD.  Recorded so the live
        # control is not built on it.
        "rejected_identities": [{
            "identity": "totalRewarded() - token.balanceOf(dripper) == "
                        "vault.totalAssets()",
            "holds": False,
            "measured": "rewarded - dripperBalance = 4,440 IMD dripped out, "
                        "but vault.totalAssets() = 27,377 IMD",
            "why": "StakedIMD is an ERC-4626 vault: totalAssets is staker "
                   "DEPOSITS plus what the dripper has streamed in, not the "
                   "stream alone.  The reward path is therefore NOT a closed "
                   "conservation loop and a control asserting it would fire on "
                   "every healthy vault that has any depositor.  Do not wire "
                   "this one.",
        }],
    }
    (OUT / "counter_reconciliation.json").write_text(
        json.dumps(payload, indent=1) + "\n")
    print("  wrote counter_reconciliation.json")
    for name, c in checks.items():
        print(f"    {'OK  ' if c['agree'] else 'DIFF'} {name}")
    return 0


# --------------------------------------------------------------------------
# --dry-run: the acceptance gate
# --------------------------------------------------------------------------


class _SocketGuard(socket.socket):
    def __init__(self, *a, **k):  # pragma: no cover - it is the guard
        raise AssertionError(
            "capture_pool4 --dry-run opened a socket; the replay path must be "
            "entirely offline"
        )


def _install_socket_guard() -> None:
    socket.socket = _SocketGuard  # type: ignore[misc]

    def _no(*a, **k):
        raise AssertionError("capture_pool4 --dry-run tried to connect")

    socket.create_connection = _no  # type: ignore[assignment]
    urllib.request.urlopen = _no  # type: ignore[assignment]


_REQUIRED_REAL = [
    "hook_state_healthy", "hook_state_partial", "vault_state", "dripper_state",
    "token_state", "flow_logs_mixed", "flow_logs_full", "flow_logs_empty",
    "pool_slot0", "announce_undiscovered", "mainnet_absent",
    "rpc_error_states",
    # mainnet -- pool4 went live 2026-09-02.  Additive.
    "mainnet_hook_state", "mainnet_vault_state", "mainnet_distributor_state",
    "mainnet_dripper_state", "mainnet_token_state", "mainnet_vault_path",
    "mainnet_pool_slot0", "mainnet_flow_logs",
    "sepolia_cap_getters", "docs_site_page", "announce_still_unnamed",
]
_REQUIRED_DERIVED = ["hook_flags_reference", "counter_reconciliation",
                     "mainnet_flags_reference",
                     "mainnet_counter_reconciliation"]
_REQUIRED_SYNTHETIC = [
    "announce_adversarial_reply_provenance",
    "announce_adversarial_flag_mismatch",
    "announce_adversarial_returns_delta",
    "announce_adversarial_wrong_token",
    "announce_adversarial_dead_getters",
    "announce_adversarial_many_candidates",
    "announce_adversarial_markup",
    "discovery_persisted_hostile",
]

_FEED_ROW_FIELDS = {
    "ts", "kind", "from_addr", "to_addr", "from_label", "text", "tx_hash",
    "label", "value_eth",
}


def _fail(problems: list[str], msg: str) -> None:
    problems.append(msg)
    print("  FAIL " + msg)


def reconcile_mainnet() -> int:
    """The mainnet analogue of --reconcile, over the mainnet fixtures only."""
    _install_socket_guard()
    hook = _answers_by_name("mainnet_hook_state")
    token = _answers_by_name("mainnet_token_state")
    dist = _answers_by_name("mainnet_distributor_state")
    logs_fx = json.loads((OUT / "mainnet_flow_logs.json").read_text())
    slot = json.loads((OUT / "mainnet_pool_slot0.json").read_text())
    topics = {v: k for k, v in logs_fx["topic0_map"].items()}

    fee_imd = burned = rewarded = 0
    for lg in logs_fx["response"]["result"]:
        w = _data_words(lg["data"])
        if lg["topics"][0] == topics["FeeCollected(uint256,uint256)"]:
            fee_imd += w[0]
        elif lg["topics"][0] == topics["ClaimsSettled(uint256,uint256,uint256)"]:
            burned += w[0]
            rewarded += w[1]

    def c(n):
        return int(hook[n], 16)

    def t(n):
        return int(token[n], 16)

    def dv(n):
        return int(dist[n], 16)

    checks = {
        "sum_FeeCollected_imd == totalFeeToken()": (fee_imd, c("totalFeeToken")),
        "sum_ClaimsSettled_0 == totalBurned()": (burned, c("totalBurned")),
        "sum_ClaimsSettled_1 == totalRewarded()": (rewarded, c("totalRewarded")),
    }
    out = {k: {"from_logs": a, "from_counter": b, "agree": a == b,
               "delta_wei": a - b} for k, (a, b) in checks.items()}

    earned = dv("stakingEarned") + dv("nftEarned") + dv("bondingEarned")
    tick = c("currentTick")
    if tick >= 1 << 23:
        tick -= 1 << 24
    payload = {
        "fixture": "mainnet_counter_reconciliation",
        "synthetic": False,
        "chain": "mainnet",
        "derived_from": ["mainnet_hook_state.json", "mainnet_token_state.json",
                         "mainnet_distributor_state.json",
                         "mainnet_flow_logs.json", "mainnet_pool_slot0.json"],
        "generated_at": _now_iso(),
        "log_window_reaches_deployment":
            logs_fx.get("window_reaches_deployment"),
        "note": (
            "The mainnet analogue of counter_reconciliation.json.  The three "
            "log-vs-counter checks reconcile TO THE WEI and they are only "
            "legitimate because the log window reaches the deployment "
            "(log_window_reaches_deployment above) -- a window starting later "
            "would hold a SUFFIX of history and reconciling a suffix against a "
            "cumulative counter reports a defect that is not there.\n\n"
            "THE SEPOLIA BURN IDENTITY DOES NOT TRANSFER, and not merely "
            "because the address changed.  burnSink() is the BurnExecutor "
            "here, and totalBurned (80.96 IMD) equals NEITHER "
            "balanceOf(BurnExecutor) (21.48) NOR balanceOf(0xdEaD) (0.00).  "
            "The BurnExecutor is a PASS-THROUGH that burns onward, so its "
            "balance is what is QUEUED, not what has been burned -- a "
            "structural difference from 0x...dEaD, which only ever "
            "accumulates.  Any control carrying "
            "'totalBurned == balanceOf(burnSink)' from Sepolia to mainnet "
            "would misreport a healthy hook on every tick.\n\n"
            "THE 85/15 SPLIT IS TAKEN FROM THE COUNTERS, never from a "
            "document, and rewardShareBps is 1500 here against 1000 on "
            "Sepolia -- the live-read discipline earning its keep.\n\n"
            "THE DISTRIBUTOR'S THREE-WAY SPLIT reconciles from its own *Earned "
            "counters to 30/30/40, which is the self-validating check for a "
            "contract whose bonding share HAS NO GETTER: bonding is the "
            "DERIVED remainder 10000 - stakingBps - nftBps, and any literal "
            "4000 in code is a bug waiting for the operator to change a bps."
        ),
        "checks": out,
        "split_from_counters_pct": {
            "burn": 100.0 * c("totalBurned") / (c("totalBurned")
                                                + c("totalRewarded")),
            "stakers": 100.0 * c("totalRewarded") / (c("totalBurned")
                                                     + c("totalRewarded")),
        },
        "claimed_share": {
            "rewardShareBps": c("rewardShareBps"),
            "BPS_DENOMINATOR": c("BPS_DENOMINATOR"),
            "sepolia_rewardShareBps_for_contrast": 1000,
        },
        "distributor_split": {
            "stakingBps": dv("stakingBps"),
            "nftBps": dv("nftBps"),
            "bondingBps_derived": 10000 - dv("stakingBps") - dv("nftBps"),
            "bonding_has_its_own_getter": False,
            "from_earned_counters_pct": {
                "staking": 100.0 * dv("stakingEarned") / earned,
                "nft": 100.0 * dv("nftEarned") / earned,
                "bonding": 100.0 * dv("bondingEarned") / earned,
            },
            "held_equals_earned": {
                "nft": dv("heldNft") == dv("nftEarned"),
                "bonding": dv("heldBonding") == dv("bondingEarned"),
            },
            "stakingEarned_minus_nftEarned_wei":
                dv("stakingEarned") - dv("nftEarned"),
            "note": "stakingBps == nftBps, but the two Earned counters differ "
                    "by a few wei from integer division.  An exact-equality "
                    "test between them fails; they are equal to the bps, not "
                    "to the wei.",
        },
        "burn_sink": {
            "burnSink": "0x" + hook["burnSink"][-40:],
            "is_dead_address": hook["burnSink"][-40:].lower().endswith("dead"),
            "totalBurned_wei": c("totalBurned"),
            "balanceOf_burnSink_wei": t("balanceOf_burnExecutor"),
            "balanceOf_dead_wei": t("balanceOf_dead"),
            "sepolia_identity_transfers": False,
        },
        "inventory_cap": {
            "inventoryCap_wei": c("inventoryCap"),
            "tokensInPool_wei": c("tokensInPool"),
            "difference_wei": c("inventoryCap") - c("tokensInPool"),
            "equal": c("inventoryCap") == c("tokensInPool"),
            "capDecayTokensPerDay_wei": c("capDecayTokensPerDay"),
            "note": "MEASURED, and it contradicts the claim that inventoryCap "
                    "== tokensInPool on both chains.  It holds on Sepolia (see "
                    "sepolia_cap_getters.json, where the decay rate is the "
                    "2**128-1 no-decay sentinel so the cap never moves) and it "
                    "is FALSE on mainnet, where the cap decays at 1,000 "
                    "IMD/day and the two drift apart between events.  An "
                    "equality test would be flaky on mainnet and green on "
                    "Sepolia for the wrong reason.",
        },
        "position_getters_vs_poolmanager": {
            "source": "mainnet_pool_slot0.json -- PoolManager.extsload, "
                      "canonical verified-source v4 singleton",
            "currentTick": {"hook": tick, "poolmanager": slot["expected"]["tick"],
                            "agree": tick == slot["expected"]["tick"]},
            "lpFee": {"hook": c("lpFee"),
                      "poolmanager": slot["expected"]["lp_fee"],
                      "agree": c("lpFee") == slot["expected"]["lp_fee"]},
            "positionLiquidity": {
                "hook": c("positionLiquidity"),
                "poolmanager": slot["expected"]["liquidity"],
                "agree": c("positionLiquidity") == slot["expected"]["liquidity"]},
            "caveat": "the hook and the extsload words were captured in "
                      "separate rounds; on a moving mainnet pool they can "
                      "legitimately disagree, so a LIVE control must read both "
                      "in one sweep before treating a mismatch as a defect.",
        },
    }
    (OUT / "mainnet_counter_reconciliation.json").write_text(
        json.dumps(payload, indent=1) + "\n")
    print("  wrote mainnet_counter_reconciliation.json")
    for k, v in out.items():
        print(f"    {'OK  ' if v['agree'] else 'DIFF'} {k}")
    d = payload["distributor_split"]["from_earned_counters_pct"]
    print(f"    split from counters: burn "
          f"{payload['split_from_counters_pct']['burn']:.4f}% / stakers "
          f"{payload['split_from_counters_pct']['stakers']:.4f}%")
    print(f"    distributor: {d['staking']:.4f} / {d['nft']:.4f} / "
          f"{d['bonding']:.4f}  (bonding derived "
          f"{payload['distributor_split']['bondingBps_derived']} bps)")
    return 0


def dry_run() -> int:
    _install_socket_guard()
    print("dry-run: replaying every committed fixture with no socket\n")
    problems: list[str] = []

    for name in _REQUIRED_REAL:
        path = OUT / f"{name}.json"
        req_path = OUT / f"{name}.request.json"
        if not path.exists():
            _fail(problems, f"{name}.json missing")
            continue
        if not req_path.exists():
            _fail(problems, f"{name}.request.json missing -- a response with "
                            "no request is not evidence")
            continue
        fx = json.loads(path.read_text())
        rq = json.loads(req_path.read_text())
        if fx.get("synthetic") is not False:
            _fail(problems, f"{name}: a real capture must carry synthetic:false")
        for key in ("captured_at", "note", "response"):
            if not fx.get(key):
                _fail(problems, f"{name}: missing {key}")
        if (rq.get("url") != fx.get("endpoint") and "endpoint" in fx
                and not rq.get("urls")):
            _fail(problems, f"{name}: request url != fixture endpoint")
        body = rq.get("body")
        resp = fx["response"]
        if isinstance(body, list):
            req_ids = {str(e["id"]) for e in body}
            resp_ids = {str(e["id"]) for e in resp}
            if req_ids != resp_ids:
                _fail(problems, f"{name}: request/response id sets disagree")
            names = rq.get("call_names") or {}
            if names and set(names) != req_ids:
                _fail(problems, f"{name}: call_names does not cover every id")
            ok = sum(1 for e in resp if "result" in e)
            bad = len(resp) - ok
            print(f"  {name:34s} {len(resp):3d} calls, {ok} answered, {bad} reverted")
        elif isinstance(body, dict) and body.get("method") == "eth_getLogs":
            logs = resp.get("result")
            if logs is None:
                _fail(problems, f"{name}: no result array")
            else:
                kinds: dict[str, int] = {}
                for lg in logs:
                    t0 = (lg.get("topics") or ["?"])[0]
                    kinds[fx.get("topic0_map", {}).get(t0, t0)[:32]] = \
                        kinds.get(fx.get("topic0_map", {}).get(t0, t0)[:32], 0) + 1
                print(f"  {name:34s} {len(logs):3d} logs, "
                      f"{len(kinds)} distinct topic0")
        else:
            n = len(resp.get("items", [])) if isinstance(resp, dict) else 0
            print(f"  {name:34s} {n} items")

    # A27: the retired persisted-adoption defence must never be re-asserted.
    # The phrase may appear ONLY inside the amendment that retires it -- i.e.
    # after the "AMENDMENT A27" marker.  A note that promises the defence
    # again, at the top, fails here.
    ph = OUT / "discovery_persisted_hostile.json"
    if ph.exists():
        fx = json.loads(ph.read_text())
        note = fx.get("note") or ""
        marker = note.find("AMENDMENT A27")
        claim = "RE-VERIFY a persisted adoption"
        pos = note.find(claim)
        if pos != -1 and (marker == -1 or pos < marker):
            _fail(problems,
                  "discovery_persisted_hostile: the note asserts the "
                  "persisted-adoption re-verification defence outside the "
                  "amendment that retires it.  That defence was DELETED (A27) "
                  "-- the cache nominates nothing and a persisted address is "
                  "never adjudicated")
        if fx.get("expected", {}).get(
                "persisted_address_is_a_discovery_candidate") is not False:
            _fail(problems,
                  "discovery_persisted_hostile: expected must record that a "
                  "persisted address is NOT a discovery candidate (A27)")
        else:
            print("  discovery_persisted_hostile        the retired "
                  "persisted-adoption defence is not re-asserted (A27)")

    # ---- mainnet (2026-09-02) ------------------------------------------
    vp = OUT / "mainnet_vault_path.json"
    if vp.exists():
        fx = json.loads(vp.read_text())
        walk = {w["step"]: w for w in fx["walk"]}
        dv = walk.get("distributor.vault")
        if not dv or not dv["reverted"]:
            _fail(problems,
                  "mainnet_vault_path: distributor.vault() does not revert in "
                  "this capture, so the fixture no longer reproduces what "
                  "stops the old two-hop walk")
        chain = [("hook.rewardsRecipient", MAINNET_DISTRIBUTOR),
                 ("distributor.dripper", MAINNET_DRIPPER),
                 ("dripper.vault", MAINNET_VAULT)]
        for step, want in chain:
            got = (walk.get(step) or {}).get("answer_address") or ""
            if got.lower() != want.lower():
                _fail(problems,
                      f"mainnet_vault_path: {step} answers {got}, not {want} "
                      "-- the three-hop path does not lead where it claims")
        tok = (walk.get("hook.token") or {}).get("answer_address", "").lower()
        for step in ("vault.asset", "distributor.asset"):
            if (walk.get(step) or {}).get("answer_address", "").lower() != tok:
                _fail(problems,
                      f"mainnet_vault_path: {step} does not close on the token "
                      "the pool trades")
        if tok != MAINNET_IMD.lower():
            _fail(problems, "mainnet_vault_path: the walk does not anchor on "
                            "the known mainnet IMD")
        else:
            print("  mainnet_vault_path                 3 hops, "
                  "distributor.vault() reverts, walk closes on mainnet IMD")

    mr = OUT / "mainnet_counter_reconciliation.json"
    if mr.exists():
        fx = json.loads(mr.read_text())
        if not fx.get("log_window_reaches_deployment"):
            _fail(problems,
                  "mainnet_counter_reconciliation: the log window does not "
                  "reach the deployment, so its sums are a SUFFIX of history "
                  "and must not be reconciled against cumulative counters")
        for k, c in fx["checks"].items():
            if not c["agree"]:
                _fail(problems,
                      f"mainnet_counter_reconciliation: {k} no longer "
                      f"reconciles (delta {c['delta_wei']} wei)")
        sp = fx["split_from_counters_pct"]
        if abs(sp["stakers"] - 15.0) > 1e-9 or abs(sp["burn"] - 85.0) > 1e-9:
            _fail(problems,
                  f"mainnet_counter_reconciliation: the split from the "
                  f"counters is {sp['burn']:.4f}/{sp['stakers']:.4f}, not "
                  "85/15")
        if fx["claimed_share"]["rewardShareBps"] != 1500:
            _fail(problems, "mainnet_counter_reconciliation: rewardShareBps is "
                            "not 1500 on mainnet")
        if (fx["claimed_share"]["rewardShareBps"]
                == fx["claimed_share"]["sepolia_rewardShareBps_for_contrast"]):
            _fail(problems, "mainnet_counter_reconciliation: the two chains' "
                            "rewardShareBps no longer differ, so this fixture "
                            "stops demonstrating the live-read discipline")
        d = fx["distributor_split"]
        if d["bonding_has_its_own_getter"]:
            _fail(problems, "mainnet_counter_reconciliation: bonding is marked "
                            "as having its own getter; it does not, it is the "
                            "derived remainder")
        if d["bondingBps_derived"] != 10000 - d["stakingBps"] - d["nftBps"]:
            _fail(problems, "mainnet_counter_reconciliation: the bonding share "
                            "is not the derivation it claims to be")
        pct = d["from_earned_counters_pct"]
        for key, want in (("staking", 30.0), ("nft", 30.0), ("bonding", 40.0)):
            if abs(pct[key] - want) > 1e-6:
                _fail(problems,
                      f"mainnet_counter_reconciliation: the Distributor's "
                      f"{key} share reads {pct[key]:.6f}%, not {want}%")
        bs = fx["burn_sink"]
        if bs["is_dead_address"]:
            _fail(problems, "mainnet_counter_reconciliation: burnSink is "
                            "recorded as 0x...dEaD on mainnet; it is the "
                            "BurnExecutor")
        if bs["sepolia_identity_transfers"]:
            _fail(problems, "mainnet_counter_reconciliation: the Sepolia "
                            "totalBurned == balanceOf(sink) identity is marked "
                            "as transferring.  It does not: the BurnExecutor "
                            "is a pass-through and its balance is what is "
                            "queued, not what was burned")
        if bs["totalBurned_wei"] == bs["balanceOf_burnSink_wei"]:
            _fail(problems, "mainnet_counter_reconciliation: totalBurned now "
                            "equals the sink balance, so this fixture stops "
                            "demonstrating why the identity does not transfer")
        print("  mainnet_counter_reconciliation      85/15 from counters, "
              "30/30/40 from the Earned counters, burnSink is not dEaD")

    # Both cap getters, both chains, different values -- the claim that they
    # were mainnet-only was never measured and was wrong.
    scg = OUT / "sepolia_cap_getters.json"
    mhs = OUT / "mainnet_hook_state.json"
    if scg.exists() and mhs.exists():
        sep = _answers_by_name("sepolia_cap_getters")
        man = _answers_by_name("mainnet_hook_state")
        sentinel = (1 << 128) - 1
        for g in ("capDecayTokensPerDay", "inventoryCap"):
            if sep.get(g) is None or man.get(g) is None:
                _fail(problems,
                      f"{g} does not answer on both chains; the fixture pair "
                      "exists to prove it does")
        if sep.get("capDecayTokensPerDay") and int(
                sep["capDecayTokensPerDay"], 16) != sentinel:
            _fail(problems, "sepolia_cap_getters: capDecayTokensPerDay is no "
                            "longer the 2**128-1 no-decay sentinel")
        if (sep.get("capDecayTokensPerDay")
                and man.get("capDecayTokensPerDay")
                and int(sep["capDecayTokensPerDay"], 16)
                == int(man["capDecayTokensPerDay"], 16)):
            _fail(problems, "the two chains' capDecayTokensPerDay agree, so "
                            "the pair no longer shows a VALUE difference")
        ctrl = json.loads(scg.read_text())
        ids = {v: k for k, v in ctrl["call_names"].items()}
        by = {str(e["id"]): e for e in ctrl["response"]}
        if "error" not in by[ids["vault_control"]]:
            _fail(problems,
                  "sepolia_cap_getters: the vault_control getter does not "
                  "revert, so the ABSENCE case is not driven by a real revert "
                  "and a test using it would pass for the wrong reason")
        else:
            print("  sepolia_cap_getters                both cap getters "
                  "answer on BOTH chains with different values; the absence "
                  "case rides a real revert")

    ds = OUT / "docs_site_page.json"
    if ds.exists():
        fx = json.loads(ds.read_text())
        if fx.get("source_kind") != "operator-controlled HTML":
            _fail(problems, "docs_site_page: must declare that it is one "
                            "operator's mutable HTML, not consensus data")
        hs = fx.get("hook_shaped_candidates") or []
        if len(hs) != 1 or hs[0]["address"].lower() != MAINNET_HOOK.lower():
            _fail(problems,
                  "docs_site_page: the flag gate no longer narrows this page "
                  f"to exactly the live hook (got {[h['address'] for h in hs]})")
        else:
            print(f"  docs_site_page                     "
                  f"{len(fx['addresses_found'])} addresses -> 1 hook-shaped; "
                  "operator HTML, no provenance")

    # A17: the vault share-price call must be sized to the vault's OWN
    # decimals, and the fixture must prove it rather than assert it.
    vs = OUT / "vault_state.json"
    if vs.exists():
        fx = json.loads(vs.read_text())
        ids = {v: k for k, v in fx["call_names"].items()}
        by_id = {str(e["id"]): e for e in fx["response"]}

        def v(n):
            return int(by_id[ids[n]]["result"], 16)

        if "convertToAssets_1e18" in ids:
            _fail(problems,
                  "vault_state: the share-price call is keyed "
                  "convertToAssets_1e18 again.  1e18 is a MILLIONTH of a share "
                  "on a 24-decimal vault; that key laundered a wrong-argument "
                  "answer into a right-looking field (A17)")
        if "convertToAssets" not in ids:
            _fail(problems, "vault_state: no convertToAssets answer")
        else:
            dec = v("decimals")
            if dec != fx.get("vault_decimals"):
                _fail(problems,
                      f"vault_state: decimals() answers {dec} but the fixture "
                      f"records vault_decimals={fx.get('vault_decimals')} -- "
                      "the argument was not built from the value that was read")
            if fx.get("share_price_argument") != 10 ** dec:
                _fail(problems,
                      "vault_state: share_price_argument is not 10**decimals, "
                      "so the share price is quoted per fraction of a share")
            # Wei-exact, and it is the whole reason this fixture is
            # self-validating: three independently returned values must agree.
            expect = v("totalAssets") * 10 ** dec // v("totalSupply")
            if expect != v("convertToAssets"):
                _fail(problems,
                      "vault_state: totalAssets/totalSupply gives "
                      f"{expect} but convertToAssets returned "
                      f"{v('convertToAssets')} -- the halves of this capture "
                      "disagree")
            wrong_key = "convertToAssets_millionth_of_a_share"
            if wrong_key in ids:
                ratio = v("convertToAssets") // v(wrong_key)
                if ratio != 10 ** (dec - 18):
                    _fail(problems,
                          "vault_state: the kept wrong-argument answer no "
                          f"longer differs by 10**{dec - 18} (got {ratio}), so "
                          "it no longer demonstrates the decimals trap")
            print(f"  vault_state                        decimals {dec} "
                  f"(offset {dec - 18}); share price "
                  f"{v('convertToAssets') / 10 ** 18:.6f} IMD/share, "
                  "wei-exact against totalAssets/totalSupply")

    # A16: the settlement rule is log-ordered, and the corpus must keep
    # saying so.  This is a structural check, not a grep of the note: it
    # proves a same-transaction rule would be WRONG on this window.
    mixed = OUT / "flow_logs_mixed.json"
    if mixed.exists():
        fx = json.loads(mixed.read_text())
        t = {v: k for k, v in fx["topic0_map"].items()}
        acc = t["UNRESOLVED accrual (uint128 liquidityRemoved, uint256 toBurn, "
                "uint256 toRewards, uint256 eth)"]
        cs = t["ClaimsSettled(uint256,uint256,uint256)"]
        ordered = sorted(fx["response"]["result"],
                         key=lambda l: (int(l["blockNumber"], 16),
                                        int(l["logIndex"], 16)))
        a_b = a_s = c_b = c_s = 0
        cross_tx = 0
        pending: list[tuple[str, int, int]] = []
        for lg in ordered:
            w = _data_words(lg["data"])
            if lg["topics"][0] == acc:
                a_b += w[1]
                a_s += w[2]
                pending.append((lg["transactionHash"], w[1], w[2]))
            elif lg["topics"][0] == cs:
                c_b += w[0]
                c_s += w[1]
                for i, (tx, pb, ps) in enumerate(pending):
                    if (pb, ps) == (w[0], w[1]):
                        if tx != lg["transactionHash"]:
                            cross_tx += 1
                        pending.pop(i)
                        break
        if cross_tx == 0:
            _fail(problems,
                  "flow_logs_mixed: no settlement pays an accrual from an "
                  "earlier transaction, so this window no longer demonstrates "
                  "that settlement is log-ordered rather than per-transaction")
        # The EXACT wei, not the round number they display as.  267,300 /
        # 29,700 is correct to two decimal places and WRONG to the wei; an
        # equality test written against the round figure fails on real data.
        if (a_b - c_b, a_s - c_s) != (267299999999999999994537,
                                      29699999999999999999393):
            _fail(problems,
                  "flow_logs_mixed: outstanding accrual is "
                  f"{a_b - c_b} / {a_s - c_s} wei, not the values the note "
                  "states")
        else:
            print(f"  flow_logs_mixed                    settlement is "
                  f"log-ordered ({cross_tx} cross-transaction settlements); "
                  f"{(a_b - c_b) / 10 ** 18:.6f} / "
                  f"{(a_s - c_s) / 10 ** 18:.6f} left outstanding")

    # the two fixtures that carry their own claims
    ann = OUT / "announce_undiscovered.json"
    if ann.exists():
        fx = json.loads(ann.read_text())
        hits = fx.get("hook_shaped_self_post_candidates")
        if hits:
            _fail(problems,
                  "announce_undiscovered: a hook-shaped address IS present in "
                  "a self-post -- the mainnet deployment may have landed; "
                  "re-capture and tell the team: " + json.dumps(hits))
        else:
            print("  announce_undiscovered              no pool4 post in "
                  "this capture (historical; see announce_still_unnamed)")
    mab = OUT / "mainnet_absent.json"
    if mab.exists():
        fx = json.loads(mab.read_text())
        v = fx.get("verdicts") or {}
        live = [k for k, d in v.items()
                if d.get("deployed") and k != "mainnet_imd_positive_control"]
        if live:
            _fail(problems, "mainnet_absent: code IS deployed at " + str(live))
        ctrl = v.get("mainnet_imd_positive_control") or {}
        if not ctrl.get("deployed"):
            _fail(problems, "mainnet_absent: the positive control is empty, so "
                            "the absence proves nothing about the chain")
        else:
            print(f"  mainnet_absent                     nothing deployed; "
                  f"control has {ctrl['code_bytes']} bytes of code")

    for name in _REQUIRED_DERIVED:
        path = OUT / f"{name}.json"
        if not path.exists():
            _fail(problems, f"{name}.json missing")
            continue
        fx = json.loads(path.read_text())
        if name == "hook_flags_reference":
            flags, value = decode_hook_permissions(fx["raw_result"])
            if "0x%04x" % value != fx["flag_word"]:
                _fail(problems, "hook_flags_reference: the recorded flag word "
                                "does not follow from the recorded raw result")
            for addr, mask in fx["address_low_14_bits"].items():
                if int(mask, 16) != value:
                    _fail(problems,
                          f"hook_flags_reference: {addr} masks to {mask} but "
                          f"getHookPermissions says {fx['flag_word']}")
            print(f"  {name:34s} flag word {fx['flag_word']} "
                  f"({sum(flags.values())} permissions), agrees with all "
                  f"{len(fx['address_low_14_bits'])} launch addresses")
        if name == "counter_reconciliation":
            agreed = [k for k, c in fx["checks"].items() if c["agree"]]
            for k, c in fx["checks"].items():
                if not c["agree"] and "retainedEth" not in k:
                    _fail(problems,
                          f"counter_reconciliation: {k} no longer reconciles "
                          f"(delta {c['delta_wei']} wei) -- the recovered "
                          "interface is wrong on this deployment")
            if not fx["withdrawn"]["eth_identity_holds"]:
                _fail(problems,
                      "counter_reconciliation: sum(FeeCollected eth) != "
                      "sum(FeesWithdrawn eth) + retainedEth(), so the ETH leg "
                      "has no explanation")
            print(f"  {name:34s} {len(agreed)}/{len(fx['checks'])} checks "
                  "reconcile to the wei; the ETH leg is explained by the "
                  "withdrawals")

    for name in _REQUIRED_SYNTHETIC:
        path = OUT / f"{name}.json"
        if not path.exists():
            _fail(problems, f"{name}.json missing")
            continue
        fx = json.loads(path.read_text())
        if fx.get("synthetic") is not True:
            _fail(problems, f"{name}: a synthetic corpus must say so in-file")
        if not fx.get("note"):
            _fail(problems, f"{name}: synthetic corpus with no attack note")
        if (OUT / f"{name}.request.json").exists():
            _fail(problems, f"{name}: synthetic corpora have no request "
                            "sibling -- nothing produced them")
        rows = fx.get("rows")
        if rows is not None:
            for i, r in enumerate(rows):
                if set(r) != _FEED_ROW_FIELDS:
                    _fail(problems,
                          f"{name}: row {i} is not SURF_ROW_KEYS['feed_items'] "
                          f"shape (extra={sorted(set(r) - _FEED_ROW_FIELDS)}, "
                          f"missing={sorted(_FEED_ROW_FIELDS - set(r))})")
        for label, value in (fx.get("attacker_addresses") or {}).items():
            listed = value if isinstance(value, list) else [value]
            for addr in listed:
                if not (isinstance(addr, str) and addr.startswith("0x")
                        and len(addr) == 42):
                    continue
                mask = int(addr, 16) & 0x3FFF
                if label in ("valid", "hook_shaped") and mask != 0x2840:
                    _fail(problems, f"{name}: '{label}' {addr} masks to "
                                    f"0x{mask:04x}, so it is not the "
                                    "correctly-flagged address the note claims")
                if label == "decoys" and mask == 0x2840:
                    _fail(problems, f"{name}: a decoy ({addr}) carries the real "
                                    "flag word, so the corpus does not encode "
                                    "'exactly one of twenty'")
        declared = (fx.get("attacker_addresses") or {}).get("low_14_bits")
        cand = (fx.get("attacker_addresses") or {}).get("candidate")
        if declared and cand:
            if int(cand, 16) & 0x3FFF != int(declared, 16):
                _fail(problems, f"{name}: the note declares {declared} but "
                                f"{cand} masks to "
                                f"0x{int(cand, 16) & 0x3FFF:04x}")
        exp = fx.get("expected") or {}
        if any(k.startswith("candidates") for k in exp):
            stage = exp.get("candidates_stage")
            if stage not in ("provenance", "flag_filtered", "verdict"):
                _fail(problems,
                      f"{name}: expected carries a candidates list but does "
                      "not name which discovery stage it belongs to "
                      "(candidates_stage), so the corpus is not "
                      "self-describing")
            if not fx.get("discovery_stages"):
                _fail(problems, f"{name}: no discovery_stages glossary")
        n_rows = len(rows) if rows else 0
        n_ans = len(fx.get("eth_call_answers") or {})
        print(f"  {name:42s} {n_rows} rows, {n_ans} answer sets  [synthetic]")

    print()
    if problems:
        print(f"dry-run FAILED with {len(problems)} problem(s)")
        return 1
    print("dry-run OK: every fixture loaded, validated and replayed offline")
    return 0


# --------------------------------------------------------------------------
# manifest
# --------------------------------------------------------------------------


def write_manifest() -> None:
    entries = []
    for name in _REQUIRED_REAL + _REQUIRED_DERIVED + _REQUIRED_SYNTHETIC:
        path = OUT / f"{name}.json"
        if not path.exists():
            continue
        fx = json.loads(path.read_text())
        entries.append({
            "fixture": name + ".json",
            "synthetic": bool(fx.get("synthetic")),
            "request_sibling": (name + ".request.json"
                                if (OUT / f"{name}.request.json").exists()
                                else None),
            "chain": fx.get("chain"),
            "block_number": fx.get("block_number"),
            "captured_at": fx.get("captured_at"),
            "endpoint": fx.get("endpoint"),
            "note": fx.get("note"),
        })
    live_dir = OUT / "captures" / "live"
    live = sorted(p.name for p in live_dir.glob("*.json")) if live_dir.exists() else []
    payload = {
        "generated_by": "scripts/capture_pool4.py --manifest",
        "generated_at": _now_iso(),
        "work_package": "WP1 of docs/surf_pool4_implementation_plan.md",
        "acceptance": "python3 scripts/capture_pool4.py --dry-run",
        "raw_captures_kept_verbatim": ["captures/live/" + n for n in live],
        "fixtures": entries,
    }
    (OUT / "MANIFEST.json").write_text(json.dumps(payload, indent=1) + "\n")
    print(f"  wrote MANIFEST.json ({len(entries)} fixtures)")


# --------------------------------------------------------------------------


def self_test() -> int:
    print("self-test: the User-Agent that publicnode accepts")
    for url in (SEPOLIA_STATE_URL, MAINNET_STATE_URL):
        try:
            r = post_json(url, {"jsonrpc": "2.0", "id": 1,
                                "method": "eth_blockNumber", "params": []})
            print(f"  {url} -> block {int(r['result'], 16)}")
        except Exception as exc:  # noqa: BLE001
            print(f"  {url} -> FAILED {exc!r}")
            return 1
    return 0


_CAPTURES = {
    "sepolia-state": capture_sepolia_state,
    "flow-logs": capture_flow_logs,
    "pool-slot0": capture_pool_slot0,
    "announce": capture_announce,
    "mainnet-absent": capture_mainnet_absent,
    "rpc-errors": capture_rpc_errors,
    "vault-state": capture_vault_state,
    "mainnet-state": capture_mainnet_state,
    "vault-path": capture_vault_path,
    "sepolia-cap-getters": capture_sepolia_cap_getters,
    "docs-site": capture_docs_site,
    "mainnet-pool": capture_mainnet_pool,
    "announce-still-unnamed": capture_announce_still_unnamed,
}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true",
                    help="replay and validate every committed fixture, no socket")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--capture", choices=sorted(_CAPTURES) + ["all"])
    ap.add_argument("--synthesize", action="store_true",
                    help="(re)write the synthetic adversarial corpora")
    ap.add_argument("--reconcile", action="store_true",
                    help="settle the counters against the log set, offline")
    ap.add_argument("--reconcile-mainnet", action="store_true",
                    help="settle the mainnet counters, offline")
    ap.add_argument("--manifest", action="store_true")
    args = ap.parse_args(argv)

    if not any((args.dry_run, args.self_test, args.capture, args.synthesize,
                args.reconcile, args.reconcile_mainnet, args.manifest)):
        ap.print_help()
        return 2
    if args.dry_run:
        return dry_run()
    if args.self_test:
        return self_test()
    if args.capture:
        names = sorted(_CAPTURES) if args.capture == "all" else [args.capture]
        for n in names:
            _CAPTURES[n]()
    if args.synthesize:
        synthesize()
    if args.reconcile:
        reconcile()
    if args.reconcile_mainnet:
        reconcile_mainnet()
    if args.manifest:
        write_manifest()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
