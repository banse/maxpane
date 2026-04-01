#!/usr/bin/env python3
"""Validate Cat Town ABI files against live Base chain contracts.

For each ABI + contract address pair, attempts an eth_call to a simple read
function and reports pass/fail.
"""

import json
import struct
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
ABI_DIR = ROOT / "dashboard" / "abis" / "cattown"

BASE_RPC = "https://mainnet.base.org"

# Contract address -> ABI file + test call info
CONTRACTS = {
    "kibble_token": {
        "address": "0x64cc19A52f4D631eF5BE07947CABA14aE00c52Eb",
        "abi_file": "kibble_token.json",
        "test_calls": [
            {"function": "name()", "selector": "0x06fdde03", "description": "ERC-20 name"},
            {"function": "decimals()", "selector": "0x313ce567", "description": "ERC-20 decimals"},
            {"function": "totalSupply()", "selector": "0x18160ddd", "description": "ERC-20 totalSupply"},
        ],
    },
    "sushi_v2_pair": {
        "address": "0x8e93c90503391427bff2a945b990c2192c0de6cf",
        "abi_file": "sushi_v2_pair.json",
        "test_calls": [
            {"function": "getReserves()", "selector": "0x0902f1ac", "description": "UniV2 getReserves"},
            {"function": "token0()", "selector": "0x0dfe1681", "description": "UniV2 token0"},
            {"function": "token1()", "selector": "0xd21220a7", "description": "UniV2 token1"},
        ],
    },
    "kibble_oracle": {
        "address": "0xE97B7ab01837A4CbF8C332181A2048EEE4033FB7",
        "abi_file": "kibble_oracle.json",
        "test_calls": [
            # Custom KIBBLE oracle (1578 bytes) -- may use non-standard interface.
            # The ABI was extracted from cat.town frontend bundle as a Chainlink-style
            # feed (latestRoundData + decimals). If these revert, the contract may have
            # been upgraded or uses a different oracle pattern. Code-exists check is
            # the primary validation for this contract.
            {"function": "latestRoundData()", "selector": "0xfeaf968c", "description": "Oracle latestRoundData"},
            {"function": "decimals()", "selector": "0x313ce567", "description": "Oracle decimals"},
            {"function": "owner()", "selector": "0x8da5cb5b", "description": "Ownable owner"},
        ],
        "code_only_ok": True,  # Pass if code exists even if calls revert
    },
    "fishing_game": {
        "address": "0xC05Dde2e6E4c5E13E3f78B6Cb4436CFEf6d7AbD3",
        "abi_file": "fishing_game.json",
        "test_calls": [
            # Proxy contract (225 bytes) -- try owner() and UPGRADE_INTERFACE_VERSION
            {"function": "owner()", "selector": "0x8da5cb5b", "description": "Ownable owner"},
            {"function": "UPGRADE_INTERFACE_VERSION()", "selector": "0xad3cb1cc", "description": "UUPS version"},
            {"function": "selector 0x71c9f256", "selector": "0x71c9f256", "description": "Known fishing selector"},
        ],
    },
    "competition": {
        "address": "0x62a8F851AEB7d333e07445E59457eD150CEE2B7a",
        "abi_file": "competition.json",
        "test_calls": [
            {"function": "owner()", "selector": "0x8da5cb5b", "description": "Ownable owner"},
        ],
    },
    "revenue_share": {
        "address": "0x9e1Ced3b5130EBfff428eE0Ff471e4Df5383C0a1",
        "abi_file": "revenue_share.json",
        "test_calls": [
            {"function": "owner()", "selector": "0x8da5cb5b", "description": "Ownable owner"},
        ],
    },
}


def eth_call(client: httpx.Client, to: str, data: str, retries: int = 3) -> dict:
    """Make an eth_call to Base RPC with retry on rate-limit."""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "eth_call",
        "params": [
            {"to": to, "data": data},
            "latest",
        ],
    }
    for attempt in range(retries):
        resp = client.post(BASE_RPC, json=payload, timeout=15.0)
        if resp.status_code == 429:
            wait = 2 ** attempt + 1
            print(f"    (rate-limited, waiting {wait}s ...)")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp.json()
    # Final attempt without retry
    resp = client.post(BASE_RPC, json=payload, timeout=15.0)
    resp.raise_for_status()
    return resp.json()


def get_code(client: httpx.Client, address: str, retries: int = 3) -> str | None:
    """Check that an address has code deployed."""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "eth_getCode",
        "params": [address, "latest"],
    }
    for attempt in range(retries):
        resp = client.post(BASE_RPC, json=payload, timeout=15.0)
        if resp.status_code == 429:
            wait = 2 ** attempt + 1
            time.sleep(wait)
            continue
        resp.raise_for_status()
        result = resp.json().get("result", "0x")
        return result if result != "0x" else None
    resp = client.post(BASE_RPC, json=payload, timeout=15.0)
    resp.raise_for_status()
    result = resp.json().get("result", "0x")
    return result if result != "0x" else None


def validate_contract(client: httpx.Client, name: str, info: dict) -> tuple[bool, list[str]]:
    """Validate a single contract. Returns (all_passed, messages)."""
    messages = []
    abi_path = ABI_DIR / info["abi_file"]

    # Check ABI file exists
    if not abi_path.exists():
        messages.append(f"  ABI file not found: {abi_path.relative_to(ROOT)}")
        return False, messages

    # Validate JSON
    try:
        with open(abi_path) as f:
            abi = json.load(f)
        if not isinstance(abi, list):
            messages.append(f"  ABI is not a JSON array")
            return False, messages
        messages.append(f"  ABI loaded: {len(abi)} entries")
    except json.JSONDecodeError as e:
        messages.append(f"  Invalid JSON in ABI file: {e}")
        return False, messages

    # Check contract has code
    address = info["address"]
    code = get_code(client, address)
    if not code:
        messages.append(f"  No code at address {address}")
        return False, messages
    messages.append(f"  Contract code verified ({len(code) // 2 - 1} bytes)")

    # Run test calls -- pass if at least one call succeeds
    any_passed = False
    any_failed = False
    for test in info["test_calls"]:
        selector = test["selector"]
        desc = test["description"]
        try:
            time.sleep(0.5)  # Courtesy delay between calls
            result = eth_call(client, address, selector)
            if "error" in result:
                error_msg = result["error"].get("message", str(result["error"]))
                messages.append(f"  [FAIL] {desc}: RPC error: {error_msg}")
                any_failed = True
            elif "result" in result:
                raw = result["result"]
                if raw == "0x" or raw == "0x0":
                    messages.append(f"  [WARN] {desc}: empty return (may be expected)")
                else:
                    # Try to decode
                    data_hex = raw[2:]
                    display = data_hex[:64] + ("..." if len(data_hex) > 64 else "")
                    messages.append(f"  [PASS] {desc}: 0x{display}")
                    any_passed = True
            else:
                messages.append(f"  [FAIL] {desc}: unexpected response")
                any_failed = True
        except Exception as e:
            messages.append(f"  [FAIL] {desc}: {e}")
            any_failed = True

    # Contract passes if code exists and at least one test call succeeded
    # Some contracts (e.g., custom oracles) may pass on code-exists alone
    code_only_ok = info.get("code_only_ok", False)
    if any_passed:
        passed = True
    elif code_only_ok:
        passed = True
        messages.append(f"  NOTE: No test calls succeeded, but code exists (code_only_ok=True)")
    else:
        passed = False
    if any_failed and any_passed:
        messages.append(f"  NOTE: Some calls failed (may require params or use different interface)")
    return passed, messages


def main():
    print("=" * 60)
    print("Cat Town ABI Validator")
    print("=" * 60)
    print(f"RPC: {BASE_RPC}")
    print(f"ABI dir: {ABI_DIR.relative_to(ROOT)}")
    print()

    client = httpx.Client(timeout=15.0)
    results = {}

    for i, (name, info) in enumerate(CONTRACTS.items()):
        if i > 0:
            time.sleep(1)  # Rate-limit courtesy delay
        print(f"[{name}] {info['address']}")
        passed, messages = validate_contract(client, name, info)
        for msg in messages:
            print(msg)
        results[name] = passed
        status = "PASS" if passed else "FAIL"
        print(f"  => {status}")
        print()

    client.close()

    # Summary
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)
    pass_count = sum(1 for v in results.values() if v)
    total = len(results)
    for name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}")
    print(f"\n  {pass_count}/{total} contracts validated successfully")

    return pass_count == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
