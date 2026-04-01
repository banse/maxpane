#!/usr/bin/env python3
"""Extract Cat Town contract ABIs from the frontend bundle at cat.town.

Fetches the Next.js app, downloads JS chunks, scans for ABI-shaped JSON arrays,
and saves candidates to dashboard/abis/cattown/.
"""

import json
import re
import hashlib
import sys
from pathlib import Path
from urllib.parse import urljoin

import httpx

ROOT = Path(__file__).resolve().parent.parent
ABI_DIR = ROOT / "dashboard" / "abis" / "cattown"
ABI_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = "https://cat.town"

# Known contract addresses (lowercase for matching)
TARGET_CONTRACTS = {
    "kibble_oracle":  "0xE97B7ab01837A4CbF8C332181A2048EEE4033FB7",
    "fishing_game":   "0xC05Dde2e6E4c5E13E3f78B6Cb4436CFEf6d7AbD3",
    "competition":    "0x62a8F851AEB7d333e07445E59457eD150CEE2B7a",
    "revenue_share":  "0x9e1Ced3b5130EBfff428eE0Ff471e4Df5383C0a1",
}

# Known function selector for fishing contract
FISHING_SELECTOR = "0x71c9f256"


def fetch_page(client: httpx.Client) -> str:
    """Fetch the cat.town homepage HTML."""
    print(f"Fetching {BASE_URL} ...")
    resp = client.get(BASE_URL, follow_redirects=True)
    resp.raise_for_status()
    return resp.text


def find_chunk_urls(html: str) -> list[str]:
    """Extract all _next/static/chunks/*.js URLs from HTML."""
    # Match script src attributes and also inline buildManifest/ssgManifest references
    patterns = [
        r'src=["\'](/[^"\']*?_next/static/[^"\']*?\.js)["\']',
        r'["\'](_next/static/chunks/[^"\']+\.js)["\']',
        r'["\'](_next/static/[^"\']+\.js)["\']',
    ]
    urls = set()
    for pat in patterns:
        for match in re.finditer(pat, html):
            path = match.group(1)
            if path.startswith("/"):
                urls.add(urljoin(BASE_URL, path))
            else:
                urls.add(urljoin(BASE_URL + "/", path))
    return sorted(urls)


def find_build_manifest_chunks(html: str, client: httpx.Client) -> list[str]:
    """Try to find the _buildManifest.js and extract additional chunk paths."""
    extra_urls = []
    manifest_pat = r'(_next/static/[^"\']+/_buildManifest\.js)'
    for match in re.finditer(manifest_pat, html):
        manifest_url = urljoin(BASE_URL + "/", match.group(1))
        try:
            resp = client.get(manifest_url, follow_redirects=True)
            if resp.status_code == 200:
                # Extract chunk paths from manifest
                chunk_pat = r'"(static/chunks/[^"]+\.js)"'
                for cm in re.finditer(chunk_pat, resp.text):
                    chunk_url = urljoin(BASE_URL + "/_next/", cm.group(1))
                    extra_urls.append(chunk_url)
        except Exception:
            pass
    return extra_urls


def download_chunks(client: httpx.Client, urls: list[str]) -> dict[str, str]:
    """Download JS chunks, return {url: content}."""
    chunks = {}
    print(f"Downloading {len(urls)} JS chunks ...")
    for i, url in enumerate(urls):
        try:
            resp = client.get(url, follow_redirects=True, timeout=15.0)
            if resp.status_code == 200:
                chunks[url] = resp.text
                if (i + 1) % 20 == 0:
                    print(f"  ... downloaded {i + 1}/{len(urls)}")
        except Exception as e:
            print(f"  WARN: failed to fetch {url}: {e}")
    print(f"  Downloaded {len(chunks)} chunks successfully")
    return chunks


def extract_abi_candidates(js_content: str) -> list[list[dict]]:
    """Extract ABI-shaped JSON arrays from JS content.

    ABIs are JSON arrays where elements have 'type' in ('function','event','constructor','error','receive','fallback')
    and typically have 'inputs', 'stateMutability', etc.
    """
    candidates = []

    # Strategy 1: Find JSON arrays that look like ABIs using bracket matching
    # Look for patterns like: [{"inputs":... or [{"type":"function"...
    abi_starts = [
        r'\[(?:\s*)\{(?:\s*)"(?:inputs|type|name|stateMutability)"',
    ]

    for pattern in abi_starts:
        for match in re.finditer(pattern, js_content):
            start = match.start()
            # Try to extract the full JSON array by bracket matching
            abi_json = extract_json_array(js_content, start)
            if abi_json and is_valid_abi(abi_json):
                candidates.append(abi_json)

    # Strategy 2: Look for ABI assigned as variable values
    # e.g., abi: [...] or ABI=[...]
    var_patterns = [
        r'(?:abi|ABI)\s*[:=]\s*(\[)',
    ]
    for pattern in var_patterns:
        for match in re.finditer(pattern, js_content):
            start = match.start(1)
            abi_json = extract_json_array(js_content, start)
            if abi_json and is_valid_abi(abi_json):
                candidates.append(abi_json)

    return candidates


def extract_json_array(text: str, start: int, max_len: int = 500_000) -> list | None:
    """Extract a JSON array starting at position `start` in text."""
    if start >= len(text) or text[start] != '[':
        return None

    depth = 0
    in_string = False
    escape_next = False
    end = min(start + max_len, len(text))

    for i in range(start, end):
        ch = text[i]
        if escape_next:
            escape_next = False
            continue
        if ch == '\\' and in_string:
            escape_next = True
            continue
        if ch == '"' and not escape_next:
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == '[':
            depth += 1
        elif ch == ']':
            depth -= 1
            if depth == 0:
                json_str = text[start:i + 1]
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    return None
    return None


def is_valid_abi(data: list) -> bool:
    """Check if a list looks like a valid Solidity ABI."""
    if not isinstance(data, list) or len(data) < 2:
        return False

    valid_types = {"function", "event", "constructor", "error", "receive", "fallback"}
    abi_entry_count = 0

    for item in data:
        if not isinstance(item, dict):
            return False
        item_type = item.get("type", "")
        if item_type in valid_types:
            abi_entry_count += 1

    # At least 50% of entries should be valid ABI types
    return abi_entry_count >= len(data) * 0.5 and abi_entry_count >= 2


def compute_abi_hash(abi: list) -> str:
    """Compute a stable hash for deduplication."""
    canonical = json.dumps(abi, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:12]


def abi_has_selector(abi: list, selector: str) -> bool:
    """Check if an ABI contains a function matching a given 4-byte selector."""
    try:
        from eth_abi import encode as eth_encode  # noqa: F401
        from eth_utils import function_signature_to_4byte_selector  # noqa: F401
    except ImportError:
        pass

    # Fallback: manually compute selectors using keccak256
    try:
        import hashlib as _hl

        def keccak256(data: bytes) -> bytes:
            """Use pycryptodome or fallback."""
            try:
                from Crypto.Hash import keccak
                k = keccak.new(digest_bits=256)
                k.update(data)
                return k.digest()
            except ImportError:
                pass
            try:
                import sha3
                k = sha3.keccak_256()
                k.update(data)
                return k.digest()
            except ImportError:
                pass
            # Try pysha3 via hashlib
            try:
                k = _hl.new('keccak_256')
                k.update(data)
                return k.digest()
            except Exception:
                pass
            return b''

        selector_bytes = bytes.fromhex(selector.replace("0x", ""))

        for item in abi:
            if item.get("type") != "function":
                continue
            name = item.get("name", "")
            inputs = item.get("inputs", [])
            param_types = ",".join(_solidity_type(inp) for inp in inputs)
            sig = f"{name}({param_types})"
            computed = keccak256(sig.encode())[:4]
            if computed == selector_bytes:
                return True
    except Exception:
        pass

    return False


def _solidity_type(inp: dict) -> str:
    """Get the canonical Solidity type string for an ABI input."""
    t = inp.get("type", "")
    if t == "tuple":
        components = inp.get("components", [])
        inner = ",".join(_solidity_type(c) for c in components)
        return f"({inner})"
    if t == "tuple[]":
        components = inp.get("components", [])
        inner = ",".join(_solidity_type(c) for c in components)
        return f"({inner})[]"
    return t


def match_abi_to_contract(abi: list, address_mentions: dict[str, list[str]]) -> str | None:
    """Try to match an ABI to a known contract by proximity in source."""
    # This is a heuristic -- if an address appears near where the ABI was found
    # For now just return None; we'll use function signatures instead
    return None


def scan_for_addresses(js_content: str) -> dict[str, list[int]]:
    """Find positions of known contract addresses in JS content."""
    positions = {}
    for name, addr in TARGET_CONTRACTS.items():
        addr_lower = addr.lower()
        for match in re.finditer(re.escape(addr_lower), js_content.lower()):
            positions.setdefault(name, []).append(match.start())
    return positions


def label_abis(
    candidates: list[list[dict]],
    all_js: str,
) -> dict[str, list[dict]]:
    """Try to label extracted ABIs with contract names."""
    labeled = {}

    # Find address positions in combined JS
    addr_positions = scan_for_addresses(all_js)

    # Check fishing selector
    for abi in candidates:
        if abi_has_selector(abi, FISHING_SELECTOR):
            labeled["fishing_game"] = abi
            print(f"  Matched fishing_game ABI via selector {FISHING_SELECTOR}")

    # For remaining, try to match by proximity to addresses
    # Build a map of ABI positions (approximate)
    abi_hashes_seen = set()
    unlabeled = []
    for abi in candidates:
        h = compute_abi_hash(abi)
        if h in abi_hashes_seen:
            continue
        abi_hashes_seen.add(h)
        if abi not in labeled.values():
            unlabeled.append(abi)

    # Try heuristic: look for function names that hint at contract purpose
    oracle_hints = {"getPrice", "latestAnswer", "latestRoundData", "getRoundData", "price", "getKibblePrice", "getTokenPrice"}
    competition_hints = {"compete", "competition", "enter", "enterCompetition", "getCompetition", "getCurrentCompetition", "winners"}
    revenue_hints = {"claim", "claimReward", "distribute", "getShare", "revenueShare", "pendingReward", "earned"}
    fishing_hints = {"fish", "cast", "reel", "startFishing", "endFishing", "getFishingState", "catch"}

    hint_map = {
        "kibble_oracle": oracle_hints,
        "competition": competition_hints,
        "revenue_share": revenue_hints,
        "fishing_game": fishing_hints,
    }

    for abi in unlabeled:
        func_names = {item.get("name", "") for item in abi if item.get("type") == "function"}
        best_match = None
        best_score = 0
        for contract_name, hints in hint_map.items():
            if contract_name in labeled:
                continue
            score = len(func_names & hints)
            if score > best_score:
                best_score = score
                best_match = contract_name
        if best_match and best_score >= 1:
            labeled[best_match] = abi
            print(f"  Matched {best_match} ABI via function name hints (score={best_score})")

    return labeled


def save_abi(name: str, abi: list[dict]) -> Path:
    """Save an ABI to its JSON file."""
    path = ABI_DIR / f"{name}.json"
    with open(path, "w") as f:
        json.dump(abi, f, indent=2)
    print(f"  Saved {path.relative_to(ROOT)} ({len(abi)} entries)")
    return path


def main():
    print("=" * 60)
    print("Cat Town ABI Extractor")
    print("=" * 60)

    client = httpx.Client(
        timeout=30.0,
        headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"},
        follow_redirects=True,
    )

    try:
        html = fetch_page(client)
    except Exception as e:
        print(f"ERROR: Could not fetch {BASE_URL}: {e}")
        sys.exit(1)

    chunk_urls = find_chunk_urls(html)
    manifest_urls = find_build_manifest_chunks(html, client)
    all_urls = sorted(set(chunk_urls + manifest_urls))
    print(f"Found {len(all_urls)} JS chunk URLs")

    if not all_urls:
        print("WARN: No JS chunks found. The site may use a different bundler.")
        print("Attempting to find any .js references...")
        js_refs = re.findall(r'["\']([^"\']+\.js)["\']', html)
        for ref in js_refs[:5]:
            print(f"  Found: {ref}")

    chunks = download_chunks(client, all_urls)

    # Combine all JS for address scanning
    all_js = "\n".join(chunks.values())
    print(f"Total JS content: {len(all_js):,} characters")

    # Scan for known addresses
    print("\nScanning for contract addresses...")
    for name, addr in TARGET_CONTRACTS.items():
        count = all_js.lower().count(addr.lower())
        if count > 0:
            print(f"  Found {name} address ({addr}) {count} time(s)")
        else:
            print(f"  {name} address ({addr}) NOT found")

    # Extract ABI candidates from each chunk
    print("\nExtracting ABI candidates...")
    all_candidates = []
    for url, content in chunks.items():
        candidates = extract_abi_candidates(content)
        if candidates:
            print(f"  {url.split('/')[-1]}: {len(candidates)} ABI(s) found")
            all_candidates.extend(candidates)

    # Deduplicate
    seen_hashes = {}
    unique_candidates = []
    for abi in all_candidates:
        h = compute_abi_hash(abi)
        if h not in seen_hashes:
            seen_hashes[h] = abi
            unique_candidates.append(abi)

    print(f"\nFound {len(unique_candidates)} unique ABI candidates (from {len(all_candidates)} total)")

    # Print info about each candidate
    for i, abi in enumerate(unique_candidates):
        func_names = sorted(item.get("name", "?") for item in abi if item.get("type") == "function")
        event_names = sorted(item.get("name", "?") for item in abi if item.get("type") == "event")
        print(f"\n  Candidate {i + 1}: {len(abi)} entries")
        print(f"    Functions: {', '.join(func_names[:10])}")
        if len(func_names) > 10:
            print(f"    ... and {len(func_names) - 10} more")
        if event_names:
            print(f"    Events: {', '.join(event_names[:5])}")

    # Try to label ABIs
    print("\nLabeling ABIs...")
    labeled = label_abis(unique_candidates, all_js)

    # Save labeled ABIs
    print("\nSaving ABIs...")
    saved = {}
    for name, abi in labeled.items():
        path = save_abi(name, abi)
        saved[name] = path

    # Save all unlabeled candidates for manual review
    unlabeled_dir = ABI_DIR / "candidates"
    unlabeled_dir.mkdir(exist_ok=True)
    labeled_hashes = {compute_abi_hash(abi) for abi in labeled.values()}

    unlabeled_count = 0
    for abi in unique_candidates:
        h = compute_abi_hash(abi)
        if h not in labeled_hashes:
            path = unlabeled_dir / f"candidate_{h}.json"
            with open(path, "w") as f:
                json.dump(abi, f, indent=2)
            unlabeled_count += 1

    if unlabeled_count:
        print(f"  Saved {unlabeled_count} unlabeled candidates to {unlabeled_dir.relative_to(ROOT)}/")

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for name in TARGET_CONTRACTS:
        if name in saved:
            print(f"  [OK]   {name}: {saved[name].relative_to(ROOT)}")
        else:
            print(f"  [MISS] {name}: not found")

    missing = [n for n in TARGET_CONTRACTS if n not in saved]
    if missing:
        print(f"\n  {len(missing)} contract ABI(s) still missing.")
        print("  Check candidates/ directory for unlabeled ABIs.")
        print("  You may also try fetching ABIs from BaseScan if contracts are verified.")

    client.close()
    return len(missing) == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
