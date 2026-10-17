"""Read-only, block-pinned token metadata and reviewed utility dependencies.

Relationships come from the source review, never a matching token symbol.
Metadata reads are not a full ERC-20 conformance or security audit.
"""
import copy
import re

from ..surf_nft_chain import CHAINS, _decode, selector


def _address(value):
    return isinstance(value, str) and re.fullmatch(r"0x[0-9a-fA-F]{40}", value) and int(value, 16) != 0


def _empty(chain_id, address, status, warning):
    return {"chainId": chain_id, "address": address, "status": status,
            "codePresent": None, "name": None, "symbol": None, "decimals": None,
            "totalSupply": None, "formattedSupply": None, "readBlock": None,
            "readTimestamp": None, "warnings": [warning] if warning else []}


def read_token(inspector, chain_id, address):
    """Read standard metadata without treating optional fields as mandatory."""
    if chain_id not in CHAINS or not _address(address):
        raise ValueError("Token reads require a nonzero address on Ethereum or Robinhood mainnet")
    address = address.lower()
    result = _empty(chain_id, address, "unavailable", None)
    try:
        block, stamp = inspector._snapshot(chain_id)
        result.update(readBlock=int(block, 16), readTimestamp=stamp)
        code = inspector.rpc(chain_id, "eth_getCode", [address, block])
        if not isinstance(code, str) or not re.fullmatch(r"0x(?:[0-9a-fA-F]{2})*", code):
            raise ValueError("Invalid runtime bytecode response")
        result["codePresent"] = bool(code[2:])
        if not result["codePresent"]:
            result.update(status="no-code", warnings=["No contract code at this address on the stated chain."])
            return result
    except (RuntimeError, ValueError, KeyError, TypeError, OSError) as error:
        result["warnings"].append(str(error)[:200])
        return result
    for name, kind in (("name", "string"), ("symbol", "string"), ("decimals", "uint8"), ("totalSupply", "uint256")):
        try:
            raw = inspector.rpc(chain_id, "eth_call", [{"to": address, "data": selector(name + "()")}, block])
            value = _decode(raw, kind)
            if name == "decimals" and not 0 <= value <= 255:
                raise ValueError("outside uint8 range")
            result[name] = str(value) if name == "totalSupply" else value
        except (RuntimeError, ValueError, KeyError, TypeError, OSError) as error:
            result["warnings"].append(f"{name}: {str(error)[:160]}")
    if result["decimals"] is not None and result["totalSupply"] is not None:
        decimals, supply = result["decimals"], result["totalSupply"]
        digits = supply.zfill(decimals + 1)
        result["formattedSupply"] = (digits[:-decimals] + "." + digits[-decimals:]).rstrip("0").rstrip(".") if decimals else digits
    result["status"] = "checked" if not result["warnings"] else "partial"
    return result


def refresh_utility_reads(chain, inspector, specs):
    """Execute ordered zero-argument specs already authorized by a code-hash rule.

    A dependent address may come from a preceding root getter. Namespaced reads
    never inherit evidence from another address or block. Failed reads remove
    any previous value so it cannot accidentally support a current claim.
    """
    if not specs:
        return
    chain_id = chain.get("chainId")
    if chain_id not in CHAINS:
        raise ValueError("Utility reads are mainnet-only")
    snapshot_error = None
    try:
        block, stamp = inspector._snapshot(chain_id)
        if chain.get("readBlock") != int(block, 16):
            raise ValueError("Utility and NFT evidence must use the same block")
    except (RuntimeError, ValueError, KeyError, TypeError, OSError) as error:
        snapshot_error = str(error)
        block, stamp = None, None
    for spec in specs:
        name, kind = spec["name"], spec["type"]
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) or kind not in {"address", "bool", "string", "uint8", "uint256"}:
            raise ValueError("Invalid reviewed getter specification")
        address = chain.get("reads", {}).get(spec["addressFrom"]) if spec.get("addressFrom") else spec.get("address", chain.get("address"))
        namespace = spec.get("namespace")
        if namespace:
            dependencies = chain.setdefault("dependencyReads", {})
            target = dependencies.get(namespace, {})
            if target.get("address") != address or target.get("readBlock") != chain.get("readBlock"):
                target = {"address": address, "chainId": chain_id, "readBlock": chain.get("readBlock"), "readTimestamp": stamp, "reads": {}, "errors": {}}
                dependencies[namespace] = target
            errors = target.setdefault("errors", {})
        else:
            target = chain
            errors = target.setdefault("readErrors", {})
        reads = target.setdefault("reads", {})
        reads.pop(name, None)
        errors.pop(name, None)
        try:
            if snapshot_error:
                raise ValueError(snapshot_error)
            if not _address(address):
                raise ValueError("Missing or invalid dependency address")
            if namespace:
                target.update(inspector.dependency_code(chain_id, address.lower(), block))
                if target["codePresent"] is not True:
                    raise ValueError("Dependency has no runtime code")
            raw = inspector.rpc(chain_id, "eth_call", [{"to": address.lower(), "data": selector(name + "()")}, block])
            value = _decode(raw, kind)
            if kind == "uint8" and value > 255:
                raise ValueError("outside uint8 range")
            reads[name] = value
        except (RuntimeError, ValueError, KeyError, TypeError, OSError) as error:
            errors[name] = str(error)[:200]


def attach_token_metadata(records, inspector, saved=None, offline=False, workers=6):
    """Add metadata to each reviewed token, deduplicating by chain and address.

    Returns the cache for persistence. Mutates only each token's `onchain` field;
    the reviewed relationship, roles, conditions and deployment status remain.
    Offline reads use saved evidence with its original timestamp.
    """
    saved = saved or {}
    targets = {}
    for record in records:
        for token in record.get("tokens", []):
            chain_id, address = token.get("chainId"), token.get("address")
            if chain_id in CHAINS and _address(address):
                targets[f"{chain_id}:{address.lower()}"] = (chain_id, address.lower())
    def inspect(item):
        key, (chain_id, address) = item
        if offline:
            cached = saved.get(key, {})
            value = cached if cached.get("chainId") == chain_id and cached.get("address") == address else _empty(chain_id, address, "unavailable", "No saved token metadata; run an online scan.")
        else:
            value = read_token(inspector, chain_id, address)
        return key, value
    results = dict(inspect(item) for item in targets.items())
    for record in records:
        for token in record.get("tokens", []):
            chain_id, address = token.get("chainId"), token.get("address")
            key = f"{chain_id}:{address.lower()}" if isinstance(address, str) else None
            token["onchain"] = copy.deepcopy(results.get(key) or _empty(chain_id, address, "unverified-address", "No reviewed token address on an allowed mainnet."))
    return results
