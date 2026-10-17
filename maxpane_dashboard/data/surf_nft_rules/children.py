"""Bounded discovery for reviewed mainnet NFT factories; no LLM or wallet access.

Only the reviewed factory runtime hashes below enable their getter adapters.
Counts and registries are read again on every invocation. Errors are recorded as
incomplete coverage, never as zero children. Call only during an online scan.
"""
import copy
import re
from datetime import datetime, timezone

from ..surf_nft_chain import CHAINS, _decode, keccak256, selector

ZERO = "0x" + "0" * 40
FACTORIES = [
    {"chainId": 1, "kind": "loom", "factory": "0x830c2349a83f2f53b9e7450d842d3272cd73e01a",
     "template": "0x84286f3c9276807a36730701d417f2bbdb85732a", "sourceName": "LoomCollection",
     "codeHash": "0xf7dc610c10bd79a36b654c4dc4e4f56cb09e10cca443e9d85cd19ce9ba55e9eb"},
    {"chainId": 1, "kind": "artifacts", "factory": "0x5051f8b21c55182ad4cf5fbf8236f5f29d74727f",
     "template": "0xc2517f76766b955260bf94c50da1b3366c9ae57b", "sourceName": "ArtifactsPiece",
     "codeHash": "0xaac3d6d25305e6d21309fab0ce26b635fd25556418e3c260d19b2ac7af24b27b"},
    {"chainId": 1, "kind": "arthouse", "factory": "0xdb36a049f351f4afdcdbdcf3932b444fe1d198c9",
     "template": "0xb2b22e5e40b1ebbfe393c0134436e4ca0eaf639a", "sourceName": "ArtCollection",
     "codeHash": "0x0d4b88a5019bdd3bf6e8040ff952352c957d6a2fae7a6cc99e1101c06b9ead06"},
]


def _call(inspector, chain, address, block, signature, kind="uint256", args=()):
    data = selector(signature) + "".join(format(value, "064x") for value in args)
    return _decode(inspector.rpc(chain, "eth_call", [{"to": address, "data": data}, block]), kind)


def _clone_target(code):
    match = re.fullmatch(r"0x363d3d373d3d3d363d73([0-9a-f]{40})5af43d82803e903d91602b57fd5bf3", str(code).lower())
    return "0x" + match[1] if match else None


def _creation_proof(inspector, config, address, block):
    """Use explorer only to locate a transaction, then independently check its event."""
    api = CHAINS[config["chainId"]]["api"]
    if not api:
        raise RuntimeError("creation transaction lookup unavailable")
    metadata = inspector.fetch_json(f"{api}/addresses/{address}")
    tx = metadata.get("creation_transaction_hash")
    if not isinstance(tx, str) or not re.fullmatch(r"0x[0-9a-fA-F]{64}", tx):
        raise RuntimeError("child creation transaction not indexed")
    receipt = inspector.rpc(config["chainId"], "eth_getTransactionReceipt", [tx])
    if not isinstance(receipt, dict) or receipt.get("status") != "0x1" or receipt.get("transactionHash", "").lower() != tx.lower():
        raise RuntimeError("child creation receipt is missing or unsuccessful")
    height = int(receipt["blockNumber"], 16)
    if height > int(block, 16):
        raise RuntimeError("child creation is newer than scan block")
    event = {"loom": "CollectionCreated(address,address,string,uint256)",
             "artifacts": "Claimed(uint16,address,address)",
             "arthouse": "CollectionCreated(uint256,address,address,string,string)"}[config["kind"]]
    topic = "0x" + keccak256(event.encode())
    for log in receipt.get("logs") or []:
        topics = log.get("topics") or []
        if (log.get("removed") or log.get("transactionHash", tx).lower() != tx.lower()
                or str(log.get("address", "")).lower() != config["factory"] or not topics or topics[0].lower() != topic):
            continue
        if config["kind"] == "loom":
            child_word = topics[1] if len(topics) > 1 else ""
        else:
            child_word = (log.get("data") or "")[2:66]
        if re.fullmatch(r"(?:0x)?0{24}" + address[2:], str(child_word).lower()):
            return tx, height
    raise RuntimeError("creation receipt lacks matching reviewed factory child event")


def discover_children(raw, candidates, checked, inspector, *, factories=None, max_children=256):
    """Return [{key,candidate,evidence}] and attach coverage to checked factories.

    The parent merges returned entries into its own dictionaries. Template entries
    are tagged isTemplate; no template is returned as a collection. This function
    never silently fabricates a deployment transaction for an undiscovered child.
    """
    del raw  # Reserved for the common scanner interface; no free-text inference.
    if not 1 <= max_children <= 1024:
        raise ValueError("max_children must be between 1 and 1024")
    found = []
    for config in FACTORIES if factories is None else factories:
        chain, factory = config["chainId"], config["factory"]
        if chain not in CHAINS:
            continue
        key = f"{chain}:{factory}"
        parent = candidates.get(key)
        if not parent:
            continue
        template_key = f"{chain}:{config['template']}"
        template = checked.setdefault(template_key, {})
        report = {"complete": False, "count": None, "children": [], "warnings": [], "readBlock": None}
        checked.setdefault(key, {})["factoryDiscovery"] = report
        try:
            block, stamp = inspector._snapshot(chain)
            report.update(readBlock=int(block, 16), readTimestamp=stamp)
            code = inspector.rpc(chain, "eth_getCode", [factory, block])
            if "0x" + keccak256(bytes.fromhex(code[2:])) != config["codeHash"]:
                raise RuntimeError("factory runtime changed; reviewed discovery adapter disabled")
            getter = {"loom": "implementation()", "artifacts": "pieceImplementation()", "arthouse": "collectionImplementation()"}[config["kind"]]
            implementation = _call(inspector, chain, factory, block, getter, "address")
            if implementation != config["template"]:
                raise RuntimeError("factory implementation does not match reviewed template")
            template.update(isTemplate=True, templateReason="Locked implementation; actual NFT collections are factory children")
            if config["kind"] == "artifacts":
                # Locking is irreversible and assignment requires it. An unlocked
                # factory cannot have any claimed children; no 256-call scan needed.
                locked = _call(inspector, chain, factory, block, "locked()", "bool")
                if not locked:
                    report.update(count=0, complete=True, status="unconfigured; factory not locked")
                    continue
                count = 256
                indices = range(1, 257)
            else:
                count = _call(inspector, chain, factory, block, "collectionCount()")
                indices = range(count) if config["kind"] == "loom" else range(1, count + 1)
            report["count"] = count
            report["complete"] = count <= max_children
            if count > max_children:
                report["warnings"].append(f"factory registry truncated at {max_children} entries")
            for position, index in enumerate(indices):
                if position >= max_children:
                    break
                cursor = getattr(inspector, "factory_cursors", {}).get(key, 0)
                if position < cursor:
                    continue
                if getattr(inspector, "factory_page_count", 0) >= 8:
                    report.update(complete=False, nextCursor=position)
                    break
                child_getter = {"loom": "collections(uint256)", "artifacts": "pieceContract(uint16)", "arthouse": "collection(uint256)"}[config["kind"]]
                address = _call(inspector, chain, factory, block, child_getter, "address", [index])
                if address == ZERO:  # Unclaimed ARTIFACTS slot or ArtHouse module-only collection.
                    if hasattr(inspector, "factory_cursors"):
                        inspector.factory_cursors[key] = position + 1
                        inspector.factory_page_count += 1
                    continue
                child_key = f"{chain}:{address}"
                child_code = inspector.rpc(chain, "eth_getCode", [address, block])
                if _clone_target(child_code) != implementation:
                    report["warnings"].append(f"child {address} is not the reviewed EIP-1167 implementation")
                    report["complete"] = False
                    if hasattr(inspector, "factory_cursors"):
                        inspector.factory_cursors[key] = position + 1
                        inspector.factory_page_count += 1
                    continue
                report["children"].append(address)
                tx, height, proof_error = None, None, None
                try:
                    tx, height = _creation_proof(inspector, config, address, block)
                except (RuntimeError, ValueError, KeyError, TypeError, AttributeError, OSError) as error:
                    proof_error = str(error)[:180]
                    report["warnings"].append(f"{address}: {proof_error}")
                    report["complete"] = False
                evidence = ({"chainId": chain, "address": address, "warnings": [], "inspectionComplete": False}
                            if getattr(inspector, "defer_children", False) else
                            inspector.inspect_contract(chain, address, tx, height, abi=template.get("abi")))
                evidence.update(factoryAddress=factory, implementationAddress=implementation,
                                factoryCreationVerified=bool(tx), checkedAt=inspector.observed_at)
                evidence["factoryDiscovery"] = {"factory": factory, "registryIndex": index, "readBlock": int(block, 16)}
                if proof_error:
                    evidence.setdefault("warnings", []).append(proof_error)
                source = copy.deepcopy(template.get("pinnedSource") or {})
                if source:
                    evidence["pinnedSource"] = source
                child = copy.deepcopy(parent)
                child.update(address=address, artifact={"name": config["sourceName"], "address": address,
                                                       "role": "collection", "txHash": tx, "blockNumber": height},
                             factoryAddress=factory, implementationAddress=implementation,
                             factoryProof={"kind": config["kind"], "registryIndex": index})
                found.append({"key": child_key, "candidate": child, "evidence": evidence})
                if hasattr(inspector, "record_child"):
                    inspector.record_child(found[-1])
                if hasattr(inspector, "factory_cursors"):
                    inspector.factory_cursors[key] = position + 1
                    inspector.factory_page_count += 1
            if hasattr(inspector, "factory_cursors"):
                report["nextCursor"] = inspector.factory_cursors.get(key, 0)
                report["enumerationFinished"] = report["nextCursor"] >= min(count, max_children)
        except (RuntimeError, ValueError, KeyError, TypeError, AttributeError, OSError) as error:
            report["warnings"].append(str(error)[:180])
            report["complete"] = False
    return found


def _dependencies(evidence, inspector, specs):
    chain = evidence["chainId"]
    try:
        block, _ = inspector._snapshot(chain)
    except (RuntimeError, ValueError, OSError) as error:
        evidence.setdefault("warnings", []).append("dependency snapshot unavailable: " + str(error)[:160])
        for name, address, _ in specs:
            evidence.setdefault("dependencyReads", {})[name] = {"chainId": chain, "address": address, "readBlock": None,
                                                                 "reads": {}, "errors": {"snapshot": str(error)[:160]}}
        return
    for name, address, getters in specs:
        output = {"chainId": chain, "address": address, "readBlock": int(block, 16), "reads": {}, "errors": {}}
        evidence.setdefault("dependencyReads", {})[name] = output
        try:
            output.update(inspector.dependency_code(chain, address, block))
            if output["codePresent"] is not True:
                raise ValueError("Dependency has no runtime code")
        except (RuntimeError, ValueError, TypeError, OSError) as error:
            output["errors"]["code"] = str(error)[:160]
            continue
        for function, kind in getters.items():
            try:
                output["reads"][function] = _call(inspector, chain, address, block, function + "()", kind)
            except (RuntimeError, ValueError, TypeError, OSError) as error:
                output["errors"][function] = str(error)[:160]


def _courier_items(evidence, inspector, max_items):
    """One bounded, filtered event query; unknown if provider rejects the range."""
    report = {"complete": False, "events": None, "items": None}
    evidence["eventScan"] = report
    try:
        block, _ = inspector._snapshot(4663)
        first = (evidence.get("deployment") or {}).get("blockNumber")
        last = int(block, 16)
        if not isinstance(first, int) or first < 0 or last < first:
            raise RuntimeError("Courier deployment block is unavailable")
        event = "ItemConfigured(uint256,uint256,uint256,uint256,bool,string)"
        topic = "0x" + keccak256(event.encode())
        scan = getattr(inspector, "courier_scan", {})
        start = max(first, scan.get("nextBlock", first))
        end = min(last, start + 9999)
        params = [{"address": evidence["address"], "fromBlock": hex(start), "toBlock": hex(end), "topics": [topic]}]
        logs = inspector.rpc(4663, "eth_getLogs", params)
        if not isinstance(logs, list):
            raise RuntimeError("Courier configuration event query unavailable")
        ids = sorted(set(scan.get("ids", [])) | {int(log["topics"][1], 16) for log in logs
                      if isinstance(log, dict) and str(log.get("address", "")).lower() == evidence["address"]
                      and not log.get("removed") and len(log.get("topics") or []) > 1 and log["topics"][0].lower() == topic
                      and start <= int(log.get("blockNumber", hex(start)), 16) <= end})
        if len(ids) > max_items:
            raise RuntimeError(f"Courier item enumeration exceeds {max_items}")
        scan["ids"] = ids
        if end < last:
            scan["nextBlock"] = end + 1
            report.update(fromBlock=first, toBlock=end, nextBlock=end + 1,
                          event=event, events=None, items=None)
            return
        records = []
        for item_id in ids:
            data = selector("items(uint256)") + format(item_id, "064x")
            raw = inspector.rpc(4663, "eth_call", [{"to": evidence["address"], "data": data}, block])
            raw = bytes.fromhex(raw[2:])
            if len(raw) != 192:
                raise ValueError("unexpected Courier item tuple")
            words = [int.from_bytes(raw[pos:pos + 32], "big") for pos in range(0, 192, 32)]
            if words[4] not in (0, 1) or words[5] not in (0, 1):
                raise ValueError("invalid Courier item flags")
            records.append(dict(zip(("price", "maxSupply", "perWalletLimit", "minted", "enabled", "exists"), words), id=item_id))
        report.update(complete=True, fromBlock=first, toBlock=last, event=event,
                      events=[{"itemId": item} for item in ids], items=records)
        evidence.setdefault("stats", {})["totalMinted"] = sum(item["minted"] for item in records)
        if not records:
            evidence["stats"]["totalSupply"] = 0  # Nothing has ever been configured, so nothing could mint.
    except (RuntimeError, ValueError, KeyError, TypeError, AttributeError, OSError) as error:
        report["error"] = str(error)[:180]
        evidence.setdefault("warnings", []).append("Courier item catalog unavailable: " + str(error)[:180])


def enrich_special_reads(chain_evidence, inspector, *, max_items=256):
    """Refresh reviewed dependency getters and bounded aggregates in place.

    Never applies an adapter merely because a contract has a familiar name.
    Code hash and chain/address must all match the reviewed deployment.
    """
    if not 1 <= max_items <= 1024:
        raise ValueError("max_items must be between 1 and 1024")
    identity = (chain_evidence.get("chainId"), chain_evidence.get("address"), chain_evidence.get("codeHash"))
    if identity == (1, "0x800504f0d471fa3647c2414167e55ca06df16ab6", "0x186d053da07fe71e470cc5d632ffef7ed61582b73bdf713707b78bac3c3c1c9f"):
        _dependencies(chain_evidence, inspector, [("HiveWars", "0xa7b90c8ec172fdbb03f885ab9d21a4e26d8db590",
                       dict.fromkeys(("startTime", "currentEpoch", "currentSeason", "lastSettledEpoch", "totalStaked"), "uint256"))])
        return chain_evidence
    if identity == (1, "0xd3630711f6d5e25b41d6bdbdb630fffefa170c5d", "0x5a59d352e85942b85b54d840a802da26af733a913331efef1e97e7ecb6a7ada4"):
        _dependencies(chain_evidence, inspector, [("UnionCard", chain_evidence["address"], {"strike": "address", "IDENTITY_MD": "address"})])
        return chain_evidence
    if identity == (4663, "0x2c328e6d3ae72e5b06e10884d83b01f1b0342f85", "0x245d6d99cbbecaa8df8e0c0e80840a3bd8648592357111fd587faa2b5bbd99c3"):
        _courier_items(chain_evidence, inspector, max_items)
        return chain_evidence
    if identity != (4663, "0xdda6387bf0244fc82eb3dbda168acc4d9eed56a3", "0xd4a23d86800de9b106d7929bedab057f0c02d244ea60bb6bec00bb259a7a4961"):
        return chain_evidence
    _dependencies(chain_evidence, inspector, [("StarterClaim", "0xcda5653467843137aadb2729151e5e8042a49b13",
                   {"launchTime": "uint256", "freeClaimEnds": "uint256", "freeClaimed": "uint256",
                    "root": "bytes32", "freeRoot": "bytes32", "snapshotBlock": "uint256"})])
    extra = {"complete": False, "liveItems": None, "beneficialHolders": None, "custodyHolders": None}
    chain_evidence["specialStats"] = extra
    try:
        block, _ = inspector._snapshot(4663)
        address = chain_evidence["address"]
        next_id = _call(inspector, 4663, address, block, "nextId()")
        extra.update(readBlock=int(block, 16), totalMinted=next_id - 1)
        if next_id < 1 or next_id - 1 > max_items:
            raise RuntimeError(f"FarmItems enumeration exceeds {max_items} records or invalid nextId")
        core = _call(inspector, 4663, address, block, "farmCore()", "address")
        beneficiary, custody, live = set(), set(), 0
        for item_id in range(1, next_id):
            data = selector("item(uint256)") + format(item_id, "064x")
            raw = inspector.rpc(4663, "eth_call", [{"to": address, "data": data}, block])
            data = bytes.fromhex(raw[2:])
            if len(data) != 224:
                raise ValueError("unexpected FarmItems tuple")
            holder = "0x" + data[12:32].hex()
            equipped = int.from_bytes(data[192:224], "big")
            if equipped not in (0, 1):
                raise ValueError("invalid equipped boolean")
            if holder != ZERO:
                live += 1
                beneficiary.add(holder)
                custody.add(core if equipped else holder)
        extra.update(complete=True, liveItems=live, burnedItems=next_id - 1 - live,
                     beneficialHolders=len(beneficiary), custodyHolders=len(custody))
        chain_evidence.setdefault("stats", {}).update(totalSupply=live, holders=len(custody), totalMinted=next_id - 1)
    except (RuntimeError, ValueError, KeyError, TypeError, OSError) as error:
        extra["error"] = str(error)[:180]
        chain_evidence.setdefault("warnings", []).append("FarmItems aggregate unavailable: " + str(error)[:180])
    return chain_evidence
