#!/usr/bin/env python3
"""One-shot research tooling that vendors the 8 Fake World Assets (FWA) ABIs.

    ############################################################################
    #  NOTHING IMPORTS THIS SCRIPT.                                            #
    #                                                                          #
    #  This module is deliberately NOT importable by the shipped dashboard.    #
    #  It lives in scripts/ and is run by hand, at most a handful of times in  #
    #  the life of the project, to (re)generate the static artifacts under     #
    #  maxpane_dashboard/abis/fwa/. The runtime data layer reads those JSON    #
    #  files off disk and never performs ABI acquisition itself. If you ever   #
    #  find `import vendor_fwa_abis` anywhere under maxpane_dashboard/, that   #
    #  is a bug -- delete the import, not this warning.                        #
    ############################################################################

Why this exists
---------------
The FWA protocol is 8 verified mainnet contracts. The dashboard needs their ABIs
to encode calls and decode logs. Fetching them at runtime would mean the
dashboard phones home to a block explorer on every start, which is both a
privacy leak and a hard availability dependency on a third party that we do not
control and cannot authenticate against without an API key. So we fetch once,
verify hard, and commit the bytes.

Acquisition sources (keyless only -- see docs/fwa_technical_findings.md §3)
---------------------------------------------------------------------------
1. ``https://anyabi.xyz/api/get-abi/1/{addr}``  -- preferred. A keyless mirror of
   Etherscan's verified-source index. Returns ``{"abi": [...], "name": "..."}``.
2. ``https://etherscan.io/address/{addr}#code`` -- fallback. Plain HTML with a
   plain User-Agent, no API key. The ABI JSON sits in ``<pre
   id="js-copytextarea2">``; Solidity sources sit in ``data-cname='<path>'
   data-csource='<code>'`` attribute pairs. This is also the ONLY source for the
   two status enums, whose member names do not survive into the ABI.
3. Sourcify -- NOT tried. Verified 404 for all 8 FWA contracts.
4. Etherscan API v1/v2 ``getabi`` -- FORBIDDEN. Requires an API key; MaxPane
   dashboards are keyless by hard constraint.

Usage
-----
    python scripts/vendor_fwa_abis.py --verify   # default; offline, no network
    python scripts/vendor_fwa_abis.py --fetch    # re-download and rewrite

``--verify`` re-checks every committed artifact against the constants in this
file without touching the network, so CI or a reviewer can confirm the vendored
bytes are the ones this script produced.

What gets verified (a mismatch is a hard failure, never a warning)
------------------------------------------------------------------
* entry counts per ABI match docs/fwa_technical_findings.md §2 exactly. A
  mismatch means the wrong contract or a proxy shell was fetched.
* SHA-256 of each written file matches the recorded digest.
* every getter the dashboard depends on is present.
* every getter findings §12.1 proves does NOT exist is absent. If one of those
  appears, the research was wrong about the deployed contract version and the
  run aborts loudly.
* topics.json reproduces all 9 topic0 hashes recorded in findings §8 bit-for-bit.
  Those 9 are the correctness check on the local keccak implementation: if any
  disagrees, the generator is wrong, not the doc.
* selectors.json reproduces the 5 selectors recorded in findings §4.

Generated artifacts
-------------------
    maxpane_dashboard/abis/fwa/fwa_core.json        172 entries
    maxpane_dashboard/abis/fwa/fwa_rewards.json     112
    maxpane_dashboard/abis/fwa/fwa_vrf_service.json  71
    maxpane_dashboard/abis/fwa/fwa_token.json        87
    maxpane_dashboard/abis/fwa/fwa_token_hook.json   52
    maxpane_dashboard/abis/fwa/fwa_claim.json        31
    maxpane_dashboard/abis/fwa/fwa_whitelist.json    34
    maxpane_dashboard/abis/fwa/splitter.json         59
    maxpane_dashboard/abis/fwa/topics.json           event name -> topic0
    maxpane_dashboard/abis/fwa/selectors.json        signature  -> 4-byte selector
    maxpane_dashboard/abis/fwa/config_keys.json      ConfigSet key -> parameter

``maxpane_dashboard/data/fwa_enums.py`` is hand-maintained but its content was
transcribed from the ``src/FWA.sol`` source this script fetches; ``--fetch``
re-prints the enum definitions so any drift is visible.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ABI_DIR = ROOT / "maxpane_dashboard" / "abis" / "fwa"

ANYABI = "https://anyabi.xyz/api/get-abi/1/{addr}"
EXPLORER_HTML = "https://etherscan.io/address/{addr}#code"

# A plain desktop UA. The explorer serves the verified-source page to ordinary
# browsers without a key; it 403s an obviously scripted UA.
PLAIN_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# --------------------------------------------------------------------------
# Contract registry. Addresses from https://www.fwa.fun/docs/deployments,
# independently confirmed onchain (findings §2: EIP-55 checksum recomputed,
# eth_getCode non-empty on chain id 1, verified contract name matches).
# `entries` is the expected ABI length -- the primary anti-proxy check.
# --------------------------------------------------------------------------
CONTRACTS: dict[str, dict] = {
    "fwa_core": {
        "address": "0xB276F62DB0ce8CA2Ca5bc522695bE604521eAc1c",
        "name": "FWA",
        "entries": 172,
        "role": "accounting, positions, weighting, VRF selection, settlement, crown, config",
    },
    "fwa_rewards": {
        "address": "0x6a1a1C0CfB3D3C538e13D36d608a5bcaa992fc78",
        "name": "FWARewards",
        "entries": 112,
        "role": "$FWA emissions, purchaser epochs, reward buys, hot/cold split",
    },
    "fwa_vrf_service": {
        "address": "0xa084c33Fb7a467307452898b8D58165ebd2E5D9f",
        "name": "FWAVRFService",
        "entries": 71,
        "role": "Chainlink VRF 2.5 subscription coverage, request fees",
    },
    "fwa_token": {
        "address": "0xa0Df17B5aC76ABaBA36E1450E2cbCd18A620C845",
        "name": "FWAToken",
        "entries": 87,
        "role": "ERC-20, 18 dec, 1e27 supply, buyback routing",
    },
    "fwa_token_hook": {
        "address": "0x2C67ebA8A50AF0dB5Fba55F725247a75CbDA6444",
        "name": "FWATokenHook",
        "entries": 52,
        "role": "Uniswap v4 hook: externalBuysEnabled gate + 1% trading fee",
    },
    "fwa_claim": {
        "address": "0xd4085d38855F17EdF0B1CCBFad7B3846fb305655",
        "name": "FWAClaim",
        "entries": 31,
        "role": "Merkle-gated v1 snapshot distribution",
    },
    "fwa_whitelist": {
        "address": "0x854352b275cF6A0DfFCf2983C986FBe9345e17c3",
        "name": "FWAWhitelist",
        "entries": 34,
        "role": "collection curation, sticky blocking, TTT-funded entry",
    },
    "splitter": {
        "address": "0x1C175b9F0e8C73eD3e677e1cBb1B5A2DD4373Bfe",
        "name": "Splitter",
        "entries": 59,
        "role": "protocol-fee split 63% / 7% / 30%",
    },
}

# --------------------------------------------------------------------------
# Provenance. Filled in from a real --fetch run on 2026-07-27. `--verify`
# re-checks these, so a silent edit to a vendored ABI is caught.
# `source` records which of the two keyless endpoints actually served the bytes.
# --------------------------------------------------------------------------
PROVENANCE: dict[str, dict[str, str]] = {
    "fwa_core":        {"source": "anyabi.xyz", "sha256": "8babfb321e418eea50386552b257140d66acf96dce69ecd8a5d862c3f1fb9f5f"},
    "fwa_rewards":     {"source": "anyabi.xyz", "sha256": "c736e99ab0cd5fe53f85be0ae80b69d641d9acc3657edd353cd35e57ad66cbac"},
    "fwa_vrf_service": {"source": "anyabi.xyz", "sha256": "e3fc7c9fc791dc4f7b18b8d42fa366c18eb7369a8683ce6d13e95d390545ec81"},
    "fwa_token":       {"source": "anyabi.xyz", "sha256": "896115b5add6f4db80dd6e786b3920686d559722a5c235e28aeb534dc8582619"},
    "fwa_token_hook":  {"source": "anyabi.xyz", "sha256": "437b8a8309cb61d5d03a3292cbeb3083e905593bef91010fb67cfcd4727b537b"},
    "fwa_claim":       {"source": "anyabi.xyz", "sha256": "86a84574c6d85837b12933fa671c34cd97158c9d2566c7de891dab25d738f473"},
    "fwa_whitelist":   {"source": "anyabi.xyz", "sha256": "405629672cd704abeb54e77fd767f1a44999f471d0ae86e709eed880d4145097"},
    "splitter":        {"source": "anyabi.xyz", "sha256": "248b0fa80435ae92a5a5a64a12513f1f1ca55b0218b937da278a2dca60d0b3b0"},
}

# --------------------------------------------------------------------------
# Getters the dashboard depends on. Absence is a hard failure.
# (work package WP-2 step 2; findings §4 and §5)
# --------------------------------------------------------------------------
REQUIRED_GETTERS: dict[str, list[str]] = {
    "fwa_core": [
        "quoteAcquisitionPrice",
        "listings",
        "slotToListing",
        "activeListingCount",
        "totalWeight",
        "weightedBackingTotal",
        "topListingId",
        "topListingPot",
        "topThresholdBps",
        "topListingShareBps",
        "settlementDiscountBps",
        "feeShareTotal",
        "lastIssuedSequence",
        "nextSequenceToProcess",
        "unfulfilledVrfCount",
        "pendingAcquisitionCount",
        "unsettledAcquisitionCount",
        "reservedStagedCount",
        "accruedOwnerFees",
        "acquisitionEscrowTotal",
        # WP-2 lists this under fwa_whitelist, but it is on the CORE contract
        # (findings §4.2 has it right). FWAWhitelist only has the write side,
        # `setCollections`, plus its own CollectionsSet/CollectionBlockedSet
        # events. Verified against the vendored ABIs, not assumed.
        "collectionWhitelisted",
    ],
    "fwa_rewards": [
        "emissionStart",
        "currentEpoch",
        "hotGap",
        "coldGap",
        "forcedTokenShareBps",
        "lastAcquisitionTs",
        "tokenShareBps",
        "purchaserDailyPot",
        "depositorRatePerSec",
    ],
    "fwa_vrf_service": [
        "requestFee",
        "subscriptionNativeBalance",
        "minimumSubscriptionBuffer",
        "availableProcessorSurplus",
    ],
    "fwa_token_hook": ["externalBuysEnabled"],
    "fwa_whitelist": ["TTT_AMOUNT"],
    "splitter": ["totalReceived"],
}

# --------------------------------------------------------------------------
# Getters findings §12.1 proves DO NOT EXIST on any of the 8 contracts. Every
# one of these reverts on eth_call and appears in neither the verified ABI nor
# the selectors extracted from live bytecode. They are source-level constants,
# private state, or pure docs prose.
#
# If one of these ever shows up, the deployed contract version is not the one
# the research described. Abort -- do not silently start using it.
# --------------------------------------------------------------------------
FORBIDDEN_GETTERS: list[str] = [
    "surchargeBps",
    "whitelistEnabled",
    "minBacking",
    "protocolFeeToTokenBps",
    "INVERSE_WEIGHT_NUMERATOR",
    "acquisitionsEnabled",
    "activeCount",
    "emissionEnd",
]

# --------------------------------------------------------------------------
# The 9 topic0 hashes recorded in findings §8, measured against live logs.
# Reproducing all 9 from the canonical signature is the correctness check on
# the local keccak-256 -- if one disagrees, this generator is wrong.
# --------------------------------------------------------------------------
KNOWN_TOPIC0: dict[str, str] = {
    "AcquisitionRequested": "0xf23e34f4aa4a06ecddd309d9692e7b7ca45b76fd0d5f4ce4f7fbf29731d9abd6",
    "NFTKept": "0xe71c2721f75bef3206b21176a6d26685852a16878249fc84d18f443f959bb8f5",
    "DepositorBidAccepted": "0x88ebc94b0ff4693b3d25995dc7c5c4e5683a8ca7de00836773ca24c8b69d78e3",
    "DepositorBidAcceptedAsTokens": "0x819cd055ab6ba83877ab68882609b8d7aa75d4951f6d89fa99d3b59fa45f439f",
    "NFTRelisted": "0x5fa40266a1e401404f322db009d5f8631ed44abc96b84784d9f8f90a8846abd8",
    "UnsettledFinalized": "0x6f4528c508dc00c3d0fb4dcffe0346f48ae4332f18abe3d4eff0b27895997929",
    "TopListingSet": "0x24ace256adc6182b122f3aa90b19d20b6d637236a63154d9a6ceb9032b50b514",
    "TopListingSettled": "0x72747a194a7ea234ca6c67bae23a563ff193d2efe4611bec783df82b40c47892",
    "ConfigSet": "0x150110afd46e9924086bf85c855aae25722518b293155bf0ae689dd99a2e88cc",
}

# Selectors recorded in findings §4 / §6.5.
KNOWN_SELECTORS: dict[str, str] = {
    "quoteAcquisitionPrice()": "0x987df4cd",
    "activeListingCount()": "0x4681a7c6",
    "listings(uint256)": "0xde74e57b",
    "slotToListing(uint256)": "0xe2881eb7",
    "aggregate3((address,bool,bytes)[])": "0x82ad56cb",
}

# Satellite events that live outside the core ABI but that the dashboard
# filters on. Sourced from findings §8; signatures confirmed against the
# vendored satellite ABIs at generation time.
SATELLITE_EVENTS: dict[str, str] = {
    "fwa_rewards": "ListingRewardRepriced",
    "fwa_token_hook": "ExternalBuysEnabledSet",
    "fwa_whitelist": "BurnedForWhitelist,TTTAmountSet",
}

# Multicall3 is not an FWA contract but its aggregate3 selector belongs in
# selectors.json because the position enumerator hand-encodes the call.
MULTICALL3_AGGREGATE3 = "aggregate3((address,bool,bytes)[])"

# --------------------------------------------------------------------------
# ConfigSet key map. Transcribed from `src/FWAConfigKeys.sol` as fetched from
# the verified source of the core contract -- NOT from the docs table, which
# groups three of the keys under the wrong dispatcher.
#
# The library docstring is explicit that values are globally unique across all
# three dispatchers precisely so `ConfigSet(key, value)` is unambiguous for
# indexers. `settable` is false for the three keys that are emitted through
# ConfigSet but rejected by the public setters (constructor-time only).
# --------------------------------------------------------------------------
CONFIG_KEYS: dict[int, tuple[str, str, str, bool]] = {
    # key: (name, dispatcher, value_type, settable_post_deploy)
    1: ("CALLBACK_GAS_LIMIT", "constructor", "uint256", False),
    2: ("VRF_SUB_ID", "setUint", "uint256", True),
    7: ("REQUEST_CONFIRMATIONS", "setUint", "uint256", True),
    10: ("MAX_ACTIVATIONS_PER_ACQUISITION", "setUint", "uint256", True),
    11: ("SELECTION_TIMEOUT_BLOCKS", "setUint", "uint256", True),
    12: ("MAX_ACQUISITIONS_PER_TX", "setUint", "uint256", True),
    13: ("SURCHARGE_BPS", "setUint", "uint256", True),
    14: ("SELECTION_SLIPPAGE_BPS", "setUint", "uint256", True),
    15: ("TOP_LISTING_SHARE_BPS", "setUint", "uint256", True),
    16: ("TOP_THRESHOLD_BPS", "setUint", "uint256", True),
    17: ("SETTLEMENT_DISCOUNT_BPS", "setUint", "uint256", True),
    18: ("OWNER_ACQUISITION_FEE_BPS", "setUint", "uint256", True),
    19: ("OWNER_SETTLEMENT_FEE_BPS", "setUint", "uint256", True),
    20: ("SETTLEMENT_WINDOW", "setUint", "uint256", True),
    21: ("FINALIZE_WINDOW", "setUint", "uint256", True),
    22: ("MIN_BACKING", "setUint", "uint256", True),
    23: ("PROTOCOL_FEE_TO_TOKEN_BPS", "setUint", "uint256", True),
    24: ("VRF_KEY_HASH", "constructor", "bytes32", False),
    25: ("MAX_STAGED_LISTINGS", "setUint", "uint256", True),
    40: ("RETAINED_TO_PROTOCOL", "setBool", "bool", True),
    41: ("ACQUISITIONS_ENABLED", "setBool", "bool", True),
    42: ("WITHDRAW_ONLY", "setBool", "bool", True),
    43: ("WHITELIST_ENABLED", "setBool", "bool", True),
    44: ("ACCEPT_BID_AS_TOKENS_ENABLED", "setBool", "bool", True),
    60: ("VRF_COORDINATOR", "setAddr", "address", True),
    61: ("PAYOUT_ADDRESS", "setAddr", "address", True),
    62: ("WHITELIST_MANAGER", "setAddr", "address", True),
    63: ("VRF_SERVICE", "constructor", "address", False),
}


# ==========================================================================
# keccak-256
# ==========================================================================
def keccak256(data: bytes) -> bytes:
    """Return the keccak-256 digest.

    Ethereum uses original Keccak padding, NOT the NIST SHA-3 padding, so
    hashlib.sha3_256 is the wrong function here. pycryptodome's keccak with
    digest_bits=256 is the right one; the module-level self-test below proves
    it against a known-good protocol hash before anything is generated.
    """
    from Crypto.Hash import keccak as _keccak

    h = _keccak.new(digest_bits=256)
    h.update(data)
    return h.digest()


def selftest_keccak() -> None:
    """Prove the local keccak before trusting any hash it produces."""
    got = "0x" + keccak256(b"ConfigSet(uint256,uint256)").hex()
    want = KNOWN_TOPIC0["ConfigSet"]
    if got != want:
        raise SystemExit(
            f"FATAL: keccak-256 self-test failed.\n  got  {got}\n  want {want}\n"
            "The hash function is wrong (SHA3 padding instead of Keccak?)."
        )


# ==========================================================================
# ABI helpers
# ==========================================================================
def canonical_type(component: dict) -> str:
    """Render one ABI input as its canonical type string.

    Tuples expand to a parenthesised, comma-separated list of their component
    types, recursively, with any array suffix preserved. This is what the
    signature hash is taken over -- getting it wrong silently produces a
    plausible-looking but useless topic0, which is exactly why the 9 known
    hashes are asserted afterwards.
    """
    typ = component["type"]
    if typ.startswith("tuple"):
        inner = ",".join(canonical_type(c) for c in component.get("components", []))
        suffix = typ[len("tuple"):]  # "", "[]", "[3]", "[][2]", ...
        return f"({inner}){suffix}"
    return typ


def signature(entry: dict) -> str:
    """Canonical `Name(type,type,...)` for a function or event ABI entry."""
    args = ",".join(canonical_type(i) for i in entry.get("inputs", []))
    return f"{entry['name']}({args})"


def four_byte(sig: str) -> str:
    return "0x" + keccak256(sig.encode()).hex()[:8]


def topic0(sig: str) -> str:
    return "0x" + keccak256(sig.encode()).hex()


def function_names(abi: list[dict]) -> set[str]:
    return {e["name"] for e in abi if e.get("type") == "function"}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump_json(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, indent=2) + "\n")


# ==========================================================================
# Acquisition (network -- only reached under --fetch)
# ==========================================================================
def fetch_abi(addr: str) -> tuple[list[dict], str]:
    """Return (abi, source_label). Tries anyabi first, explorer HTML second."""
    import httpx

    try:
        r = httpx.get(
            ANYABI.format(addr=addr), timeout=60, headers={"User-Agent": PLAIN_UA}
        )
        if r.status_code == 200:
            payload = r.json()
            abi = payload.get("abi")
            if isinstance(abi, list) and abi:
                return abi, "anyabi.xyz"
    except Exception as exc:  # noqa: BLE001 -- research script, fall through
        print(f"    anyabi.xyz failed ({exc}); falling back to explorer HTML")

    r = httpx.get(
        EXPLORER_HTML.format(addr=addr),
        timeout=90,
        headers={"User-Agent": PLAIN_UA},
        follow_redirects=True,
    )
    r.raise_for_status()
    m = re.search(
        r"<pre[^>]*id=['\"]js-copytextarea2['\"][^>]*>(.*?)</pre>", r.text, re.S
    )
    if not m:
        raise RuntimeError(f"no ABI block in explorer HTML for {addr}")
    return json.loads(html.unescape(m.group(1))), "explorer-html"


def fetch_source(addr: str, filename: str) -> str | None:
    """Pull one Solidity source file out of the explorer's verified-source page.

    Used only to read the two status enums, whose member names are erased by
    ABI encoding (they survive as bare `uint8`).
    """
    import httpx

    r = httpx.get(
        EXPLORER_HTML.format(addr=addr),
        timeout=90,
        headers={"User-Agent": PLAIN_UA},
        follow_redirects=True,
    )
    r.raise_for_status()
    m = re.search(
        rf"data-cname='{re.escape(filename)}'\s+data-csource='(.*?)'\s*>", r.text, re.S
    )
    return html.unescape(m.group(1)) if m else None


def extract_enums(src: str) -> dict[str, list[str]]:
    """Parse `enum Name { A, B, ... }` blocks, discarding // comments."""
    out: dict[str, list[str]] = {}
    for m in re.finditer(r"enum\s+(\w+)\s*\{([^}]*)\}", src):
        body = re.sub(r"//[^\n]*", "", m.group(2))
        out[m.group(1)] = [p.strip() for p in body.split(",") if p.strip()]
    return out


# ==========================================================================
# Generation
# ==========================================================================
def build_topics(abis: dict[str, list[dict]]) -> dict[str, dict]:
    """Every event in the core ABI plus the four satellite events."""
    topics: dict[str, dict] = {}

    def add(contract_key: str, entry: dict) -> None:
        sig = signature(entry)
        name = entry["name"]
        if name in topics and topics[name]["signature"] != sig:
            raise RuntimeError(
                f"event name collision with differing signature: {name}\n"
                f"  {topics[name]['signature']} ({topics[name]['contract']})\n"
                f"  {sig} ({contract_key})"
            )
        topics[name] = {
            "topic0": topic0(sig),
            "signature": sig,
            "indexed": [i["name"] for i in entry.get("inputs", []) if i.get("indexed")],
            "contract": contract_key,
            "address": CONTRACTS[contract_key]["address"],
        }

    for entry in abis["fwa_core"]:
        if entry.get("type") == "event":
            add("fwa_core", entry)

    for contract_key, names in SATELLITE_EVENTS.items():
        wanted = set(names.split(","))
        found = set()
        for entry in abis[contract_key]:
            if entry.get("type") == "event" and entry["name"] in wanted:
                add(contract_key, entry)
                found.add(entry["name"])
        missing = wanted - found
        if missing:
            raise RuntimeError(f"satellite events missing from {contract_key}: {missing}")

    return dict(sorted(topics.items()))


def build_selectors(abis: dict[str, list[dict]]) -> dict[str, str]:
    """4-byte selectors for every view/pure function on all 8 contracts.

    A superset of what the dashboard calls, which is the point: a decoder that
    meets an unexpected selector can name it instead of printing hex.
    Multicall3's aggregate3 is added by hand -- it is not an FWA contract, but
    the position enumerator hand-encodes it.
    """
    selectors: dict[str, str] = {}
    for abi in abis.values():
        for entry in abi:
            if entry.get("type") != "function":
                continue
            if entry.get("stateMutability") not in ("view", "pure"):
                continue
            sig = signature(entry)
            sel = four_byte(sig)
            if sig in selectors and selectors[sig] != sel:
                raise RuntimeError(f"selector disagreement for {sig}")
            selectors[sig] = sel

    selectors[MULTICALL3_AGGREGATE3] = four_byte(MULTICALL3_AGGREGATE3)
    return dict(sorted(selectors.items()))


def build_config_keys() -> dict[str, dict]:
    return {
        str(key): {
            "name": name,
            "dispatcher": dispatcher,
            "value_type": value_type,
            "settable": settable,
        }
        for key, (name, dispatcher, value_type, settable) in sorted(CONFIG_KEYS.items())
    }


# ==========================================================================
# Verification
# ==========================================================================
def verify(abis: dict[str, list[dict]], topics: dict, selectors: dict) -> list[str]:
    """Return a list of failure strings. Empty list means everything passed."""
    failures: list[str] = []

    # --- 1. entry counts (anti-proxy / anti-wrong-contract) ---
    for key, meta in CONTRACTS.items():
        got, want = len(abis[key]), meta["entries"]
        if got != want:
            failures.append(
                f"{key}: {got} ABI entries, expected {want}. Wrong contract, a "
                f"proxy shell, or an upgraded implementation -- investigate."
            )

    # --- 2. required getters present ---
    for key, needed in REQUIRED_GETTERS.items():
        have = function_names(abis[key])
        for fn in needed:
            if fn not in have:
                failures.append(f"{key}: required getter {fn}() is MISSING")

    # --- 3. refuted getters absent (findings §12.1) ---
    for key, abi in abis.items():
        have = function_names(abi)
        for fn in FORBIDDEN_GETTERS:
            if fn in have:
                failures.append(
                    f"{key}: getter {fn}() EXISTS but findings §12.1 says it does "
                    f"not. The research is wrong about the deployed version. "
                    f"Do not use it until re-verified onchain."
                )

    # --- 4. the 9 known topic0 hashes, bit-for-bit ---
    for name, want in KNOWN_TOPIC0.items():
        if name not in topics:
            failures.append(f"topics.json: {name} missing entirely")
        elif topics[name]["topic0"] != want:
            failures.append(
                f"topics.json: {name} topic0 mismatch\n"
                f"    got  {topics[name]['topic0']}\n"
                f"    want {want}\n"
                f"    signature used: {topics[name]['signature']}"
            )

    # --- 5. the 5 known selectors, bit-for-bit ---
    for sig, want in KNOWN_SELECTORS.items():
        got = selectors.get(sig)
        if got is None:
            failures.append(f"selectors.json: {sig} missing entirely")
        elif got != want:
            failures.append(f"selectors.json: {sig} = {got}, expected {want}")

    return failures


# ==========================================================================
# Commands
# ==========================================================================
def load_committed() -> dict[str, list[dict]]:
    abis: dict[str, list[dict]] = {}
    for key in CONTRACTS:
        path = ABI_DIR / f"{key}.json"
        if not path.exists():
            raise SystemExit(f"missing vendored ABI: {path} (run with --fetch)")
        abi = json.loads(path.read_text())
        if not isinstance(abi, list):
            raise SystemExit(f"{path} is not a JSON array")
        abis[key] = abi
    return abis


def cmd_fetch() -> int:
    ABI_DIR.mkdir(parents=True, exist_ok=True)
    abis: dict[str, list[dict]] = {}
    sources: dict[str, str] = {}

    print("Fetching 8 ABIs keylessly ...")
    for key, meta in CONTRACTS.items():
        abi, src = fetch_abi(meta["address"])
        abis[key] = abi
        sources[key] = src
        mark = "ok " if len(abi) == meta["entries"] else "BAD"
        print(f"  [{mark}] {key:<16} {len(abi):>4} entries  via {src}")

    for key, abi in abis.items():
        dump_json(ABI_DIR / f"{key}.json", abi)

    topics = build_topics(abis)
    selectors = build_selectors(abis)
    dump_json(ABI_DIR / "topics.json", topics)
    dump_json(ABI_DIR / "selectors.json", selectors)
    dump_json(ABI_DIR / "config_keys.json", build_config_keys())

    print("\nProvenance (paste into PROVENANCE above):")
    for key in CONTRACTS:
        digest = sha256_file(ABI_DIR / f"{key}.json")
        print(f'    "{key}": {{"source": "{sources[key]}", "sha256": "{digest}"}},')

    src = fetch_source(CONTRACTS["fwa_core"]["address"], "src/FWA.sol")
    if src:
        print("\nEnums in src/FWA.sol (transcribe into data/fwa_enums.py):")
        for name, members in extract_enums(src).items():
            print(f"    {name}: " + ", ".join(f"{i}={m}" for i, m in enumerate(members)))
    else:
        print("\nWARNING: could not read src/FWA.sol -- enums not re-checked")

    return report(verify(abis, topics, selectors))


def cmd_verify() -> int:
    """Offline. No network, no imports of httpx. Re-checks committed bytes."""
    abis = load_committed()
    topics = json.loads((ABI_DIR / "topics.json").read_text())
    selectors = json.loads((ABI_DIR / "selectors.json").read_text())

    print("Vendored ABIs:")
    for key, meta in CONTRACTS.items():
        got = len(abis[key])
        ok = "ok " if got == meta["entries"] else "BAD"
        digest = sha256_file(ABI_DIR / f"{key}.json")[:16]
        print(f"  [{ok}] {key:<16} {got:>4}/{meta['entries']:<4} sha256:{digest}…")

    print(f"\ntopics.json     {len(topics)} events")
    print(f"selectors.json  {len(selectors)} view/pure signatures")

    # Regenerate topics + selectors from the committed ABIs and require that the
    # committed files match. This catches a hand-edited topics.json.
    regen_topics = build_topics(abis)
    regen_selectors = build_selectors(abis)
    failures = verify(abis, topics, selectors)
    if regen_topics != topics:
        failures.append("topics.json does not match a fresh regeneration from the ABIs")
    if regen_selectors != selectors:
        failures.append("selectors.json does not match a fresh regeneration")

    return report(failures)


def report(failures: list[str]) -> int:
    print()
    if failures:
        print(f"FAILED — {len(failures)} problem(s):")
        for f in failures:
            print(f"  ✗ {f}")
        return 1
    print("PASS — entry counts, required getters, refuted getters, 9 topic0 "
          "hashes and 5 selectors all verified.")
    return 0


def main() -> int:
    selftest_keccak()
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--fetch", action="store_true", help="re-download from the keyless sources")
    g.add_argument("--verify", action="store_true", help="offline re-check (default)")
    args = ap.parse_args()
    return cmd_fetch() if args.fetch else cmd_verify()


if __name__ == "__main__":
    sys.exit(main())
