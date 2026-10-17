"""Conservative diagnostics for NFT addresses outside IMD launch artifacts.

Discovery is deterministic and network-free. Text is untrusted evidence, never
instructions. Even a confirmed NFT is not automatically a swarm-built collection.
"""
import copy
import re
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import urlsplit

from ..surf_nft_chain import _decode, keccak256, selector

ADDRESS = re.compile(r"\b0x[0-9a-fA-F]{40}\b")
NFT = re.compile(r"\bnfts?\b|erc[- ]?(?:721|1155)|non[- ]fungible", re.I)
DEPLOYED = re.compile(r"\b(?:deployed|launched)\b|\blive\s+(?:NFT|ERC|collection|contract)", re.I)
LIVE_LAUNCH = re.compile(r"\blive\s+launch\s*#?(\d+)\b", re.I)
FUTURE = re.compile(r"\b(?:not|never|to be|will be|should be|must be|not yet)\s+(?:successfully\s+)?(?:deployed|launched)", re.I)
OWN_WORK = re.compile(r"\b(?:our|we)\b.{0,80}\b(?:deployed|launched)\b|(?:swarm[- ]built|deployed by (?:the )?swarm)|successfully deployed", re.I)
GATE = re.compile(r"(?:payment\s+token|paired\s+currency|gate\s+(?:token|contract)|identity\s+(?:NFT|collection)|IDMD\s*(?:address|collection|NFT)?|(?:IMD|WETH|USDC|USDT)\s*(?:token|address)?|delegate\s+registry)\s*[:=(\-]?\s*$", re.I)
CANONICAL_DEPENDENCIES = {
    "0x0000ec93127baa929e58e97dd0095a2bfb38ec1d",  # IDMD identity, not newly deployed work.
    "0xd34a99bc0f67ae1bbd63c660e6d0b0dd03e263b7",
    "0x5f7bb59365ce557c26dbcaa4ee9d39a4b95b7127",
    "0xa7d8d9ef8d8ce8992df33d8b8cf4aebabd5bd270",  # Art Blocks eligibility dependency.
    "0x00000000000000447e69651d841bd8d104bed493",
    "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
    "0x0000000000000000000000000000000000000000",
    "0x000000000000000000000000000000000000dead",
}

# Reviewed immutable constructor chain at the pinned launch source. Runtime
# hashes include immutable addresses and therefore deliberately differ from the
# compiler's unlinked attestation hashes. Never enable this adapter by name alone.
SEASONS = {
    "hook": "0x512b15372f42f687d366fc0c3342267dc73120cc",
    "canvas": "0xda4339c3b9a4e2d6e1cd7706b8419ccc7d112086",
    "child": "0xd29e47e4c4c337cd4226dd523a73af398585d1dc",
    "launchNumber": 1033,
    "factory": "0xa25b02a1e93903b790e6aaf7da1b8b8d50294645",
    "token": "0x9aa7bef88c90d237b19afe77c8883ff119b606e7",
    "launchEventTopic": "0x81a480ee97308470997e0b8b5cbc5ed561408e4757971c1366ce3d55a28185a4",
    "commit": "4ba07cc1aa427c5cf5ca67f6a0494adf57222ec4",
    "hashes": {
        "0x512b15372f42f687d366fc0c3342267dc73120cc": "0x4071d7a0485af0ef5957bec2f9d494048af92b8634faec24ada33c7a93997d1a",
        "0xda4339c3b9a4e2d6e1cd7706b8419ccc7d112086": "0xc7fd5784f1b71b44285fb4c809b8d41eb8aa60e8494d0658071d6c7a37b1ce32",
        "0xd29e47e4c4c337cd4226dd523a73af398585d1dc": "0x3d6a338984119a6c9fb77acd9900c8af989bc3e3a09646889380d4e232fe868b",
    },
}


def _swarm_repo(value):
    parsed = urlsplit(str(value or ""))
    return parsed.scheme == "https" and parsed.hostname == "github.com" and parsed.path.lower().startswith("/identity-md-launches/")


def _documents(raw):
    """Yield full public bodies with explicit source links; list previews are excluded."""
    details = raw.get("jobDetails") or {}
    for row in details.values() if isinstance(details, dict) else details:
        if isinstance(row, dict):
            yield row.get("id"), row.get("objective") or "", row, "job"
    for publication in raw.get("publications") or []:
        pid = str(publication.get("id") or "")
        jid = pid.removeprefix("job:") if pid.startswith("job:") else None
        yield jid, publication.get("title") or "", publication, "publication"
        for version in publication.get("versions") or []:
            yield version.get("jobId"), version.get("objective") or "", version, "publication-version"


def _chain(context):
    # Mainnet identity/payment references elsewhere never override a testnet target.
    if re.search(r"sepolia|testnet|goerli|holesky|hoodi|no mainnet|not on mainnet", context, re.I):
        return None
    eth = bool(re.search(r"ethereum(?:\s+mainnet)?|(?<![\w.])etherscan\.io/|chain\s*(?:id)?\s*[:=(]?\s*1\b", context, re.I))
    robin = bool(re.search(r"robinhood(?:\s+chain)?|\b4663\b", context, re.I))
    return 1 if eth and not robin else 4663 if robin and not eth else None


def discover_references(raw, *, observed_at=None):
    """Return supplementary candidates; never promote text claims to deployments.

    ``raw`` accepts collector launch rows, full jobDetails and publications. Every
    candidate carries its source job links and a bounded excerpt. Coverage states
    the heuristic limits explicitly, including inherited input incompleteness.
    """
    known = set()
    launches = list(raw.get("launches") or [])
    details = raw.get("launchDetails") or {}
    launches.extend(details.values() if isinstance(details, dict) else details)
    for launch in launches:
        for artifact in launch.get("artifacts") or []:
            known.add((launch.get("chainId"), str(artifact.get("address") or "").lower()))
    by_number = {str(row.get("launchNumber")): row for row in launches
                 if row.get("status") == "live" and row.get("chainId") in (1, 4663)}
    candidates, excluded, seen_documents = {}, Counter(), set()
    scanned = 0
    for job_id, text, row, kind in _documents(raw):
        if not isinstance(text, str) or not text:
            continue
        signature = (job_id, text)
        if signature in seen_documents:
            continue
        seen_documents.add(signature)
        scanned += 1
        live_launches = [by_number[number] for number in LIVE_LAUNCH.findall(text) if number in by_number]
        if not NFT.search(text) or not (DEPLOYED.search(text) or live_launches):
            continue
        for match in ADDRESS.finditer(text):
            address = match.group().lower()
            # Local paragraph protects against relabeling another chain elsewhere.
            paragraph_start = text.rfind("\n\n", 0, match.start())
            start = max(paragraph_start + 2 if paragraph_start >= 0 else 0, match.start() - 350)
            end_paragraph = text.find("\n\n", match.end())
            end = min(end_paragraph if end_paragraph >= 0 else len(text), match.end() + 250)
            context = text[start:end]
            # Child contracts may be described as a list under a live launch.
            # Require an immediately preceding NFT label, not an unrelated NFT
            # elsewhere in the paragraph, plus the matching completed delivery.
            repo = row.get("repoUrl") or (row.get("delivery") or {}).get("repoUrl")
            label = re.split(r"0x[0-9a-fA-F]{40}|[\n,;]", text[max(0, match.start() - 100):match.start()])[-1]
            child_launches = [launch for launch in live_launches
                              if NFT.search(label) and row.get("state") == "completed"
                              and _swarm_repo(repo) and repo == launch.get("sourceRepoUrl")
                              and _chain(context) == launch.get("chainId")]
            if address in CANONICAL_DEPENDENCIES or GATE.search(text[max(0, match.start() - 90):match.start()]):
                excluded["identity-payment-or-gating-dependency"] += 1
                continue
            if not NFT.search(context) or not (DEPLOYED.search(context) or child_launches) or FUTURE.search(context):
                excluded["no-local-completed-nft-deployment-claim"] += 1
                continue
            chain_id = _chain(context)
            if chain_id is None:
                excluded["unsupported-or-ambiguous-chain"] += 1
                continue
            key = (chain_id, address)
            if key in known:
                excluded["already-in-launch-artifacts"] += 1
                continue
            linked = bool(child_launches) or (row.get("state") == "completed" and _swarm_repo(repo) and bool(OWN_WORK.search(context)))
            record = candidates.setdefault(key, {
                "chainId": chain_id, "address": address, "sourceJobIds": [], "sourceLinks": [],
                "evidence": [], "referencedLaunches": [], "verificationEligible": False, "promoted": False,
                "provenance": "Unverified address reference; text alone does not prove swarm implementation or deployment.",
            })
            record["verificationEligible"] |= linked
            for launch in child_launches:
                reference = {key: launch.get(key) for key in ("id", "launchNumber", "chainId")}
                if reference not in record["referencedLaunches"]:
                    record["referencedLaunches"].append(reference)
            if job_id and job_id not in record["sourceJobIds"]:
                record["sourceJobIds"].append(job_id)
                record["sourceLinks"].append("https://explorer.imd.fun/jobs/" + str(job_id))
            excerpt = re.sub(r"[\x00-\x1f\x7f]", " ", context).strip()[:700]
            evidence = {"kind": kind, "jobId": job_id, "excerpt": excerpt, "sourceRepo": repo,
                        "completedDeliveryLinked": linked}
            if evidence not in record["evidence"] and len(record["evidence"]) < 8:
                record["evidence"].append(evidence)
    return {
        "generatedAt": observed_at,
        "candidates": [candidates[k] for k in sorted(candidates)], "excludedCounts": dict(excluded),
        "coverage": {"fullDocumentsScanned": scanned, "knownLaunchAddresses": len(known),
                     "inputComplete": (raw.get("coverage") or {}).get("complete"),
                     "method": "Explicit local NFT + past deployment wording or matching completed live-launch delivery + unambiguous supported mainnet; no LLM."},
        "warnings": ["Supplementary diagnostic, not exhaustive proof of external deployments. Text can mention third-party collections.",
                     "References without explicit chain/deployment context are excluded; no private jobs or testnet RPCs inspected."],
    }


def verify_references(report, inspector, fetch_json, max_candidates=20):
    """Inspect only completed-delivery-linked claims; leave all results diagnostic.

    ``inspector`` is an Inspector or inspect_contract callable; ``fetch_json`` is
    a public GET client. Ethereum Blockscout supplies the creation transaction.
    Robinhood creation indexing is unavailable here, so those claims stay pending.
    No network is used for unassociated references or known bluechip dependencies.
    """
    inspect = getattr(inspector, "inspect_contract", inspector)
    attempted = 0
    for record in report.get("candidates") or []:
        if not record.get("verificationEligible"):
            record["verification"] = {"status": "not-probed", "reason": "No completed swarm implementation linkage."}
            continue
        if record.get("chainId") != 1:
            record["verification"] = {"status": "unavailable", "reason": "No configured public creation index for this mainnet."}
            continue
        if attempted >= max_candidates:
            record["verification"] = {"status": "not-probed", "reason": "Verification budget reached."}
            continue
        attempted += 1
        try:
            address = record["address"]
            metadata = fetch_json("https://eth.blockscout.com/api/v2/addresses/" + address)
            tx = metadata.get("creation_transaction_hash") or metadata.get("creation_tx_hash")
            evidence = inspect(1, address, tx_hash=tx)
            record["verification"] = {"status": "inspected", "chainEvidence": evidence,
                                      "creationTransactionSource": "https://eth.blockscout.com/api/v2/addresses/" + address,
                                      "swarmProvenanceConfirmed": False}
        except (OSError, RuntimeError, ValueError, TypeError, KeyError) as error:
            record["verification"] = {"status": "unavailable", "reason": str(error)[:300]}
    report["verificationAttempts"] = attempted
    return report


def verify_seasons_constructor(candidate, inspector):
    """Recheck the complete reviewed constructor chain in the current snapshot."""
    config = SEASONS
    hook, canvas, address = (config[key] for key in ("hook", "canvas", "child"))
    if candidate.get("chainId", 4663) != 4663 or candidate.get("launch", {}).get("chainId", 4663) != 4663:
        raise RuntimeError("constructor chain identity mismatch")
    warnings = []
    if candidate["launch"].get("sourceCommit") != config["commit"]:
        raise RuntimeError("parent source commit changed; reviewed child adapter disabled")
    block, stamp = inspector._snapshot(4663)
    for target, expected in config["hashes"].items():
        code = inspector.rpc(4663, "eth_getCode", [target, block])
        if "0x" + keccak256(bytes.fromhex(code[2:])) != expected:
            raise RuntimeError("reviewed runtime mismatch: " + target)
    def call(target, signature, kind="uint256", args=()):
        data = selector(signature) + "".join(format(value, "064x") for value in args)
        return _decode(inspector.rpc(4663, "eth_call", [{"to": target, "data": data}, block]), kind)
    for creator, child, getter in ((hook, canvas, "canvas()"), (canvas, address, "seasons()")):
        if call(creator, getter, "address") != child:
            raise RuntimeError("immutable child getter mismatch: " + getter)
        # Both are the first CREATE in their parent's reviewed constructor.
        if "0x" + keccak256(bytes.fromhex("d694" + creator[2:] + "01"))[-40:] != child:
            raise RuntimeError("constructor CREATE address mismatch")
    tx = candidate["artifact"].get("txHash")
    receipt = inspector.rpc(4663, "eth_getTransactionReceipt", [tx])
    if not isinstance(receipt, dict) or receipt.get("status") != "0x1" or receipt.get("transactionHash") != tx:
        raise RuntimeError("constructor transaction receipt missing or unsuccessful")
    height = int(receipt["blockNumber"], 16)
    if height < 1 or height > int(block, 16):
        raise RuntimeError("constructor receipt outside current snapshot")
    expected_topics = [config["launchEventTopic"], "0x" + format(config["launchNumber"], "064x"),
                       "0x" + "00" * 12 + config["token"][2:], "0x" + "00" * 12 + hook[2:]]
    if not any(str(log.get("address", "")).lower() == config["factory"] and log.get("topics") == expected_topics
               and log.get("transactionHash") == tx and not log.get("removed") for log in receipt.get("logs", [])):
        raise RuntimeError("receipt missing reviewed factory launch event and matching parent")
    required_events = ((hook, "PoolBound(bytes32,address,uint256)"), (canvas, "Started(address,uint256)"))
    for emitter, signature in required_events:
        topic = "0x" + keccak256(signature.encode())
        if not any(str(log.get("address", "")).lower() == emitter and (log.get("topics") or [None])[0] == topic
                   and log.get("transactionHash") == tx and not log.get("removed") for log in receipt.get("logs", [])):
            raise RuntimeError("constructor receipt missing reviewed event: " + signature)
    historical_verified = True
    for target in (hook, canvas, address):
        try:
            before = inspector.rpc(4663, "eth_getCode", [target, hex(height - 1)])
            code = inspector.rpc(4663, "eth_getCode", [target, hex(height)])
        except (OSError, RuntimeError) as error:
            historical_verified = False
            warnings.append("Historical bytecode unavailable; immutable constructor/CREATE/event proof used: " + str(error)[:120])
            break
        if before != "0x":
            raise RuntimeError("contract already existed before claimed constructor transaction")
        if "0x" + keccak256(bytes.fromhex(code[2:])) != config["hashes"][target]:
            raise RuntimeError("constructor block runtime mismatch")
    proof = {"parent": hook, "intermediate": canvas, "getters": ["canvas()", "seasons()"],
             "createNonce": 1, "historicalCodeVerified": historical_verified,
             "absentBeforeBlock": height if historical_verified else None, "runtimeHashes": config["hashes"],
             "launchFactoryEventVerified": True, "startupEventsVerified": True}
    return {"block": block, "timestamp": stamp, "tx": tx, "height": height, "proof": proof, "warnings": warnings}


def discover_proven_children(raw, candidates, checked, inspector, *, client=None):
    """Discover reviewed immutable children, with construction proof and fresh reads.

    Return the same [{key,candidate,evidence}] schema as _nft_children. Free-text
    references never authorize promotion. The Seasons adapter requires all three
    reviewed runtime hashes, immutable getters, deterministic CREATE addresses,
    and the launch factory/constructor transaction's events. Historical code is
    checked when the RPC provides it; archive unavailability remains explicit.
    """
    del raw
    config = SEASONS
    hook, canvas, address = (config[key] for key in ("hook", "canvas", "child"))
    key = "4663:" + hook
    parent = candidates.get(key)
    if not parent:
        return []
    report = {"complete": False, "children": [], "warnings": []}
    checked.setdefault(key, {})["childDiscovery"] = report
    try:
        verified = verify_seasons_constructor(parent, inspector)
        block, stamp, tx, height = (verified[key] for key in ("block", "timestamp", "tx", "height"))
        report.update(readBlock=int(block, 16), readTimestamp=stamp)
        report["warnings"].extend(verified["warnings"])
        def call(target, signature, kind="uint256", args=()):
            data = selector(signature) + "".join(format(value, "064x") for value in args)
            return _decode(inspector.rpc(4663, "eth_call", [{"to": target, "data": data}, block]), kind)
        child = copy.deepcopy(parent)
        child.update(chainId=4663, chain_id=4663, address=address, factoryAddress=hook,
                     constructorProof={"kind": "seasons", "parent": hook, "intermediate": canvas,
                                       "sourceCommit": config["commit"]},
                     artifact={"name": "Seasons", "address": address, "role": "collection", "txHash": tx, "blockNumber": height})
        abi = [{"type": "function", "name": name, "stateMutability": "view", "inputs": [], "outputs": [{"type": kind}]}
               for name, kind in (("canvas", "address"), ("totalPaid", "uint256"), ("totalEscrow", "uint256"))]
        evidence = inspector.inspect_contract(4663, address, tx, height, abi=abi)
        if not evidence.get("standard") or evidence.get("codeHash") != config["hashes"][address]:
            raise RuntimeError("child NFT interface or runtime confirmation failed")
        evidence.update(factoryAddress=hook, factoryCreationVerified=True, checkedAt=inspector.observed_at,
                        constructorProof=verified["proof"])
        evidence["warnings"] = [warning for warning in evidence.get("warnings", [])
                                if warning != "factory receipt confirms transaction success; address linkage relies on the launch artifact"]
        evidence.setdefault("warnings", []).extend(report["warnings"])
        if client:
            from .catalog import pinned_source
            evidence["pinnedSource"] = pinned_source(client, child)
        dependencies = {"chainId": 4663, "address": canvas, "readBlock": int(block, 16), "reads": {}, "errors": {}}
        dependencies.update(codePresent=True, codeHash=config["hashes"][canvas], codeReviewed=True)
        evidence.setdefault("dependencyReads", {})["Canvas"] = dependencies
        for name, kind in (("currentSeason", "uint256"), ("seasonStart", "uint256"), ("DURATION", "uint256"), ("imd", "address")):
            try:
                dependencies["reads"][name] = call(canvas, name + "()", kind)
            except (OSError, RuntimeError, ValueError, TypeError) as error:
                dependencies["errors"][name] = str(error)[:160]
        season = dependencies["reads"].get("currentSeason")
        if isinstance(season, int) and season > 0:
            evidence.setdefault("stats", {})["totalSupply"] = season - 1  # One mint per endSeason; no burn path.
            evidence["stats"]["totalSupplyMethod"] = "Canvas.currentSeason() - 1; one NFT minted per endSeason and no burn path in reviewed source."
        if isinstance(season, int) and season > 1:
            try:
                auction_id = season - 1
                data = selector("auctions(uint256)") + format(auction_id, "064x")
                encoded = inspector.rpc(4663, "eth_call", [{"to": address, "data": data}, block])
                words = bytes.fromhex(encoded[2:])
                if len(words) != 352:
                    raise ValueError("unexpected Seasons auction tuple")
                names = ("end", "occupied", "painters", "paints", "topPainter", "bidder", "finalized", "highBid", "pot", "payout", "paid")
                values = [_decode("0x" + words[i * 32:(i + 1) * 32].hex(), "address" if i in (4, 5) else "bool" if i == 6 else "uint256") for i in range(11)]
                evidence["reads"]["latestAuction"] = {"id": auction_id, **dict(zip(names, values))}
                try:
                    evidence["reads"]["minimumBid"] = call(address, "minimumBid(uint256)", args=(auction_id,))
                except (OSError, RuntimeError, ValueError, TypeError):
                    pass  # Expected for a closed, blank or finalized auction.
            except (OSError, RuntimeError, ValueError, TypeError) as error:
                evidence.setdefault("readErrors", {})["latestAuction"] = str(error)[:160]
        report.update(complete=True, children=[address])
        return [{"key": "4663:" + address, "candidate": child, "evidence": evidence}]
    except (OSError, RuntimeError, ValueError, TypeError, KeyError, AttributeError) as error:
        report["warnings"].append(str(error)[:220])
        return []
