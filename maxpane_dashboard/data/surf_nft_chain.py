"""Block-pinned NFT evidence. Sync interpreters consume injected observations only.

SurfNftInspector is the runtime entry point: every missing observation is admitted
by the owned asynchronous client, then persisted for deterministic resumption.
"""
from __future__ import annotations
import copy
import base64
import hashlib
import json
import math
import re
import zlib
from dataclasses import dataclass
from datetime import datetime, timezone
from .keccak import keccak256 as _keccak256
from .evm_abi import decode_uint, decode_address
from .surf_transport import read_cycle

CHAINS = {
    1: {"rpc": "https://ethereum-rpc.publicnode.com", "explorer": "https://etherscan.io", "api": "https://eth.blockscout.com/api/v2"},
    4663: {"rpc": "https://rpc.mainnet.chain.robinhood.com", "explorer": "https://robinhoodchain.blockscout.com", "api": None},
}
MAX_GETTERS = 64
MAX_RESPONSE_BYTES = 5_000_000


def keccak256(data):
    return _keccak256(data).hex()

def _missing_source(url):
    raise RuntimeError("No source observation supplied")

def selector(signature):
    return "0x" + keccak256(signature.encode())[:8]


def _number(value):
    if value is None:
        return None
    return int(value, 16) if isinstance(value, str) and value.startswith("0x") else int(value)


def _timestamp(value):
    return datetime.fromtimestamp(_number(value), timezone.utc).isoformat().replace("+00:00", "Z")


def _decode(raw, kind):
    if not isinstance(raw, str) or not raw.startswith("0x"):
        raise ValueError("invalid ABI result")
    data = bytes.fromhex(raw[2:])
    if len(data) < 32:
        raise ValueError("empty or short ABI result")
    value = decode_uint(raw)
    if kind == "bool":
        if value not in (0, 1):
            raise ValueError("invalid ABI boolean")
        return bool(value)
    if re.fullmatch(r"uint(?:8|16|24|32|40|48|56|64|72|80|88|96|104|112|120|128|136|144|152|160|168|176|184|192|200|208|216|224|232|240|248|256)?", kind):
        bits = int(kind[4:] or 256)
        if value >= 1 << bits:
            raise ValueError("ABI integer outside declared width")
        return value
    if kind.startswith("int"):
        return value - (1 << 256) if value >= (1 << 255) else value
    if kind == "address":
        if value >> 160:
            raise ValueError("invalid ABI address")
        return decode_address(raw)
    if kind == "string":
        if len(data) == 32:  # Legacy name/symbol implementations use bytes32.
            return data.rstrip(b"\x00").decode("utf-8")[:500]
        offset = value
        if offset % 32 or offset + 32 > len(data):
            raise ValueError("invalid ABI string offset")
        size = int.from_bytes(data[offset:offset + 32], "big")
        if size > 8192 or offset + 32 + size > len(data):
            raise ValueError("invalid ABI string length")
        return data[offset + 32:offset + 32 + size].decode("utf-8")[:500]
    if re.fullmatch(r"bytes(?:[1-9]|[12][0-9]|3[0-2])", kind):
        return "0x" + data[:int(kind[5:])].hex()
    raise ValueError("unsupported ABI result type")


class Inspector:
    def __init__(self, *, rpc, fetch_json=_missing_source, observed_at=None, proof_checkpoint=None,
                 rpc_batch=None):
        self.rpc = rpc
        self.rpc_batch = rpc_batch
        self.fetch_json = fetch_json
        self.snapshots = {}
        self.snapshot_headers = {}
        self.snapshot_errors = {}
        self.observed_at = observed_at
        self.proof_checkpoint = proof_checkpoint

    def dependency_code(self, chain_id, address, block):
        """Current code is observable; reviewed semantics need an explicit hash."""
        from .surf_nft_rules.rules import RULES
        from .surf_nft_rules.references import SEASONS
        code = self.rpc(chain_id, "eth_getCode", [address, block])
        if not isinstance(code, str) or not re.fullmatch(r"0x(?:[0-9a-fA-F]{2})*", code):
            raise ValueError("invalid dependency bytecode")
        digest = "0x" + keccak256(bytes.fromhex(code[2:])) if code != "0x" else None
        rule = RULES.get(f"{chain_id}:{address}", {})
        expected = rule.get("codeHash")
        if chain_id == 4663:
            expected = expected or SEASONS["hashes"].get(address)
        return {"codePresent": code != "0x", "codeHash": digest,
                "codeReviewed": bool(expected and expected == digest)}

    def _snapshot(self, chain_id):
        if chain_id in self.snapshot_errors:
            raise RuntimeError(self.snapshot_errors[chain_id])
        if chain_id not in self.snapshots:
            try:
                actual = _number(self.rpc(chain_id, "eth_chainId", []))
                if actual != chain_id:
                    raise RuntimeError(f"RPC chain ID {actual} does not match required mainnet {chain_id}")
                block = self.rpc(chain_id, "eth_blockNumber", [])
                if _number(block) is None:
                    raise RuntimeError("RPC returned no block number")
                header = self.rpc(chain_id, "eth_getBlockByNumber", [block, False])
                if not isinstance(header, dict) or _number(header.get("number")) != _number(block):
                    raise ValueError("snapshot block header mismatch")
                self.snapshots[chain_id] = (block, _timestamp(header["timestamp"]))
                self.snapshot_headers[chain_id] = header
            except (RuntimeError, ValueError, TypeError, KeyError, OSError) as error:
                self.snapshot_errors[chain_id] = str(error)
                raise RuntimeError(str(error)) from error
        return self.snapshots[chain_id]
    def inspect_contract(self, chain_id, address, tx_hash=None, block_number=None, abi=None):
        """Return evidence with unknowns as None; never infer mint eligibility.

        ``abi`` is an optional supplied list of ABI items, e.g. from the pinned
        launch repository. It is labeled supplied, never explorer-verified.
        ``deploymentConfirmed`` combines a successful supplied receipt and code;
        factory receipts do not independently prove which child they created.
        """
        if chain_id not in CHAINS:
            raise ValueError("only Ethereum mainnet (1) and Robinhood mainnet (4663) are permitted")
        if not isinstance(address, str) or not re.fullmatch(r"0x[0-9a-fA-F]{40}", address):
            raise ValueError("invalid contract address")
        if tx_hash is not None and not re.fullmatch(r"0x[0-9a-fA-F]{64}", tx_hash):
            raise ValueError("invalid transaction hash")
        address = address.lower()
        result = {
            "chainId": chain_id, "address": address, "standard": None,
            "detectionStatus": "unavailable",
            "codePresent": None, "receiptSuccess": None, "deploymentConfirmed": False,
            "receiptContractAddress": None, "receiptLogsAddresses": [],
            "deployment": {"transactionHash": tx_hash, "blockNumber": None, "timestamp": None,
                           "reportedBlockNumber": block_number},
            "readBlock": None, "readTimestamp": None,
            "name": None, "symbol": None,
            "stats": {"totalSupply": None, "maxSupply": None, "holders": None},
            "reads": {}, "readErrors": {}, "abi": None, "abiSource": None,
            "sourceText": None, "sourceUrl": None, "warnings": [],
        }
        warnings = result["warnings"]
        try:
            block, stamp = self._snapshot(chain_id)
            result.update(readBlock=_number(block), readTimestamp=stamp, checkedAt=self.observed_at,
                          readBlockHash=self.snapshot_headers.get(chain_id, {}).get("hash"))
        except RuntimeError as error:
            warnings.append(str(error))
            return result

        def call(data):
            return self.rpc(chain_id, "eth_call", [{"to": address, "data": data}, block])

        def supports(interface):
            return _decode(call("0x01ffc9a7" + interface + "0" * 56), "bool")

        try:
            if not supports("01ffc9a7") or supports("ffffffff"):
                result["detectionStatus"] = "unsupported"
                return result
            erc721, erc1155 = supports("80ac58cd"), supports("d9b67a26")
            if not erc721 and not erc1155:
                result["detectionStatus"] = "not-nft"
                return result
            result["standard"] = "ERC-721 + ERC-1155" if erc721 and erc1155 else "ERC-721" if erc721 else "ERC-1155"
            result["detectionStatus"] = "confirmed"
        except (RuntimeError, ValueError, OSError) as error:
            message = str(error).lower()
            if "revert" in message or message == "empty or short abi result":
                result["detectionStatus"] = "unsupported"
                return result
            warnings.append("ERC-165 detection unavailable: " + str(error)[:180])
            return result

        try:
            code = self.rpc(chain_id, "eth_getCode", [address, block])
            if not isinstance(code, str) or not re.fullmatch(r"0x(?:[0-9a-fA-F]{2})*", code):
                raise ValueError("invalid bytecode result")
            result["codePresent"] = code != "0x"
            result["codeBytes"] = (len(code) - 2) // 2
            if not result["codePresent"]:
                warnings.append("ERC-165 response has no deployed bytecode at the pinned block")
                return result
            result["codeHash"] = "0x" + keccak256(bytes.fromhex(code[2:]))
        except (RuntimeError, ValueError, OSError) as error:
            warnings.append("bytecode unavailable: " + str(error)[:180])

        if tx_hash:
            try:
                receipt = self.rpc(chain_id, "eth_getTransactionReceipt", [tx_hash])
                # Public load-balanced RPCs can transiently return null for an
                # old mined receipt. Retry without inventing a success on failure.
                for _ in range(2):
                    if receipt is not None:
                        break
                    receipt = self.rpc(chain_id, "eth_getTransactionReceipt", [tx_hash])
                if not isinstance(receipt, dict):
                    raise ValueError("receipt not found")
                if receipt.get("transactionHash", "").lower() != tx_hash.lower():
                    raise ValueError("receipt transaction hash mismatch")
                status = _number(receipt.get("status"))
                if status not in (0, 1):
                    raise ValueError("missing or invalid receipt status")
                result["receiptSuccess"] = status == 1
                result["receiptContractAddress"] = receipt.get("contractAddress")
                result["receiptLogsAddresses"] = sorted({
                    log["address"].lower() for log in receipt.get("logs", [])
                    if isinstance(log, dict) and isinstance(log.get("address"), str)
                    and re.fullmatch(r"0x[0-9a-fA-F]{40}", log["address"])
                })
                if status == 1:
                    receipt_block = _number(receipt.get("blockNumber"))
                    if receipt_block is None or receipt_block > _number(block):
                        raise ValueError("receipt is outside pinned snapshot")
                    result["deployment"]["blockNumber"] = receipt_block
                    header = self.rpc(chain_id, "eth_getBlockByNumber", [hex(receipt_block), False])
                    if _number(header.get("number")) != receipt_block:
                        raise ValueError("receipt block header mismatch")
                    result["deployment"]["headerBlockNumber"] = receipt_block
                    result["deployment"]["timestamp"] = _timestamp(header["timestamp"])
                    created = receipt.get("contractAddress")
                    result["receiptAddressMatches"] = created.lower() == address if created else None
                    result["deploymentConfirmed"] = result["codePresent"] is True and result["receiptAddressMatches"] is not False
                    sender = receipt.get("from")
                    result["deployment"]["deployer"] = (sender.lower() if result["deploymentConfirmed"]
                        and isinstance(sender, str) and re.fullmatch(r"0x[0-9a-fA-F]{40}", sender)
                        and int(sender[2:], 16) else None)
                    if result["receiptAddressMatches"] is False:
                        warnings.append("supplied creation receipt created a different address")
                    elif result["receiptAddressMatches"] is None:
                        warnings.append("factory receipt confirms transaction success; address linkage relies on the launch artifact")
                else:
                    warnings.append("supplied deployment transaction reverted")
            except (RuntimeError, ValueError, TypeError, KeyError, OSError) as error:
                warnings.append("deployment receipt unavailable: " + str(error)[:180])

        if self.proof_checkpoint is not None:
            self.proof_checkpoint(result)

        api = CHAINS[chain_id]["api"]
        if api:
            try:
                contract = self.fetch_json(f"{api}/smart-contracts/{address}")
                if not isinstance(contract, dict):
                    raise ValueError("invalid explorer contract response")
                if contract.get("is_verified"):
                    if isinstance(contract.get("abi"), list):
                        result["abi"], result["abiSource"] = contract["abi"], "explorer-verified"
                    result["sourceText"] = contract.get("source_code")
                    result["sourceUrl"] = f"https://eth.blockscout.com/address/{address}?tab=contract"
                    result["sourceVerification"] = {key: contract.get(key) for key in ("is_verified", "is_fully_verified", "is_partially_verified")}
                    if contract.get("implementations"):
                        warnings.append("proxy implementation source may require separate review")
            except (RuntimeError, ValueError, OSError) as error:
                warnings.append("verified ABI/source unavailable: " + str(error)[:140])
        else:
            warnings.append("Robinhood public explorer API is unavailable (HTTP 403 observed); source and holder counts may be unknown")
        if result["abi"] is None and isinstance(abi, list):
            result["abi"], result["abiSource"] = abi, "supplied"

        getters = {"name": "string", "symbol": "string", "totalSupply": "uint256"}
        # These fallback calls are hints, not claims that every NFT implements them.
        for name in ("maxSupply", "MAX_SUPPLY", "totalMinted", "mintPrice", "mintStart", "mintEnd", "saleStart", "saleEnd", "paused"):
            getters[name] = "bool" if name == "paused" else "uint256"
        for item in result["abi"] or []:
            if not isinstance(item, dict):
                continue
            outputs = item.get("outputs") or []
            name = item.get("name", "")
            if (item.get("type") == "function" and item.get("stateMutability") in ("view", "pure")
                    and not item.get("inputs") and isinstance(outputs, list) and len(outputs) == 1
                    and isinstance(name, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name)
                    and isinstance(outputs[0], dict) and isinstance(outputs[0].get("type"), str)
                    and re.fullmatch(r"u?int(?:[0-9]+)?|bool|address|string|bytes[0-9]+", outputs[0]["type"])):
                getters[name] = outputs[0]["type"]
        if len(getters) > MAX_GETTERS:
            warnings.append(f"zero-argument getters limited to {MAX_GETTERS}")
        getters = list(getters.items())[:MAX_GETTERS]
        values = (self.rpc_batch(chain_id, [('eth_call', [{'to': address, 'data': selector(name + '()')}, block])
                                           for name, _ in getters]) if self.rpc_batch else None)
        for index, (name, kind) in enumerate(getters):
            try:
                raw = values[index] if values is not None else call(selector(name + "()"))
                if isinstance(raw, Exception):
                    raise raw
                result["reads"][name] = _decode(raw, kind)
            except (RuntimeError, ValueError, OSError) as error:
                result["readErrors"][name] = str(error)[:120]
        result["name"], result["symbol"] = result["reads"].get("name"), result["reads"].get("symbol")
        result["stats"]["totalSupply"] = result["reads"].get("totalSupply")
        result["stats"]["maxSupply"] = result["reads"].get("maxSupply", result["reads"].get("MAX_SUPPLY"))
        if api:
            try:
                token = self.fetch_json(f"{api}/tokens/{address}")
                if not isinstance(token, dict):
                    raise ValueError("invalid explorer token response")
                holders = _number(token.get("holders_count"))
                supply = result["stats"]["totalSupply"]
                if holders is not None and (holders < 0 or (result["standard"] == "ERC-721" and supply is not None and holders > supply)):
                    warnings.append("indexer holder count conflicts with pinned ERC-721 supply; omitted")
                else:
                    result["stats"]["holders"] = holders
                    if holders is not None:
                        result["stats"]["holdersSource"] = f"{api}/tokens/{address}"
                        warnings.append("holder count is an unpinned explorer estimate")
            except (RuntimeError, ValueError, OSError) as error:
                warnings.append("holder count unavailable: " + str(error)[:140])
        return result


@dataclass(frozen=True)
class InspectionResult:
    progress: dict
    evidence: dict | None
    children: list[dict]
    complete: bool


class _ProofReady(BaseException):
    """Exit the interpreter before any optional collection-detail reads."""


class _ReadNeeded(BaseException):
    """Control transfer, deliberately not an interpreter's source failure."""

    def __init__(self, kind, args, key):
        self.kind, self.args, self.key = kind, args, key


class _ReadBatchNeeded(BaseException):
    def __init__(self, requests):
        self.requests = requests


def inspection_revision(candidate):
    """Only proof inputs invalidate retained observations, not discovery clocks."""
    inputs = {name: candidate.get(name) for name in (
        "chainId", "address", "abi", "factoryAddress", "factoryProof", "constructorProof")}
    inputs["artifact"] = {name: (candidate.get("artifact") or {}).get(name) for name in (
        "name", "txHash", "blockNumber")}
    inputs["launch"] = {name: (candidate.get("launch") or {}).get(name) for name in (
        "chainId", "sourceRepoUrl", "sourceCommit", "attestation")}
    return hashlib.sha256(json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class _Replay:
    def __init__(self, progress):
        self.progress = progress

    def read(self, kind, args):
        key = json.dumps([kind, args], sort_keys=True, separators=(",", ":"))
        saved = self.progress["responses"].get(key)
        if saved is None:
            raise _ReadNeeded(kind, args, key)
        if saved.get("error") is not None:
            raise RuntimeError(saved["error"])
        if "compressed" in saved:
            try:
                inflater = zlib.decompressobj()
                decoded = inflater.decompress(base64.b64decode(saved["compressed"], validate=True), 2 * 1024 * 1024 + 1)
                if len(decoded) > 2 * 1024 * 1024 or inflater.unconsumed_tail or not inflater.eof:
                    raise ValueError("Retained NFT response exceeds decode limit")
                return json.loads(decoded)
            except (ValueError, zlib.error, TypeError) as error:
                raise RuntimeError("Invalid retained NFT observation") from error
        return copy.deepcopy(saved.get("value"))

    def rpc(self, chain, method, params):
        return self.read("rpc", [chain, method, params])

    def rpc_batch(self, chain, calls):
        values, missing = [], []
        for method, params in calls:
            try:
                values.append(self.rpc(chain, method, params))
            except _ReadNeeded as request:
                missing.append(request)
            except RuntimeError as error:
                values.append(error)
        if missing:
            raise _ReadBatchNeeded(missing)
        return values

    def source(self, url):
        return self.read("json", [url])

    def get(self, url):
        return self.read("text" if url.endswith(".sol") else "json", [url])


class SurfNftInspector:
    """Resume a deterministic inspection using only the owned budgeted client.

    The replay contains observations, not a second request cache. Its lifetime is
    one pinned inspection (at most ten minutes). Re-evaluation is CPU-only; every
    distinct physical read advances the persisted operation count exactly once.
    Completed evidence belongs to the manager's longer-lived evidence cache.
    """

    def __init__(self, client, *, clock):
        self.client, self.clock = client, clock

    @staticmethod
    def _valid_progress(progress):
        if not isinstance(progress, dict):
            return False
        responses = progress.get("responses")
        if not isinstance(responses, dict) or not all(isinstance(k, str) and isinstance(v, dict) for k, v in responses.items()):
            return False
        cursors = progress.get("factory_cursors", {})
        if not isinstance(cursors, dict) or not all(type(v) is int and 0 <= v <= 256 for v in cursors.values()):
            return False
        if not isinstance(progress.get("children", {}), dict) or not isinstance(progress.get("courier_scan", {}), dict):
            return False
        scan = progress.get("courier_scan", {})
        if "nextBlock" in scan and (type(scan["nextBlock"]) is not int or scan["nextBlock"] < 0):
            return False
        if not isinstance(scan.get("ids", []), list) or not all(type(v) is int and 0 <= v < 2**256 for v in scan.get("ids", [])):
            return False
        started = progress.get("started_at")
        return type(started) in (int, float) and math.isfinite(started) and type(progress.get("completed_operations")) is int

    def _evaluate(self, candidate, progress, *, proof_only=False):
        from .surf_nft_rules.catalog import pinned_source, pinned_abi, source_getter_abi
        from .surf_nft_rules.children import discover_children, enrich_special_reads
        from .surf_nft_rules.references import SEASONS, discover_proven_children
        from .surf_nft_rules.tokens import attach_token_metadata, refresh_utility_reads
        from .surf_nft_rules.utility import enrich_utility, utility_read_specs

        replay = _Replay(progress)
        reader = Inspector(rpc=replay.rpc, fetch_json=replay.source,
                           observed_at=progress["observed_at"], rpc_batch=replay.rpc_batch)
        reader.record_child = lambda child: progress.setdefault("children", {}).update({child["key"]: copy.deepcopy(child)})
        reader.defer_children = True
        reader.factory_cursors = progress.setdefault("factory_cursors", {})
        reader.factory_page_count = 0
        reader.courier_scan = progress.setdefault("courier_scan", {})
        chain, address = candidate["chainId"], candidate["address"]
        artifact = candidate.get("artifact", {})
        key = f"{chain}:{address}"
        needs_child_proof = bool(candidate.get("factoryProof") or candidate.get("constructorProof")
                                 or candidate.get("factoryAddress")
                                 or (chain == 4663 and address == SEASONS["child"]))

        def proof_checkpoint(proof):
            if proof.get("chainId") != chain or proof.get("address") != address:
                return  # A nested constructor child has its own proof boundary.
            if needs_child_proof and not proof_only:
                self._child_proof(candidate, proof, reader)
                if proof.get("factoryCreationVerified") is not True:
                    return
            provisional = copy.deepcopy(proof)
            provisional.update(proofOnly=True, inspectionComplete=False)
            progress["provisional"] = provisional
            progress["block_number"] = proof.get("readBlock")
            progress["block_timestamp"] = proof.get("readTimestamp")
            if proof_only:
                if needs_child_proof:
                    provisional['deploymentConfirmed'] = False
                raise _ProofReady

        reader.proof_checkpoint = proof_checkpoint
        evidence = reader.inspect_contract(chain, address, artifact.get("txHash"),
                                           artifact.get("blockNumber"), candidate.get("abi"))
        if proof_only:
            return evidence, []  # Negative/unknown detection also stops before detail discovery.
        if needs_child_proof:
            self._child_proof(candidate, evidence, reader)
        # Generic getter evidence can replace the earlier proof-only checkpoint.
        progress["provisional"] = copy.deepcopy(evidence)
        progress["block_number"] = evidence.get("readBlock")
        progress["block_timestamp"] = evidence.get("readTimestamp")
        if evidence.get("standard") and evidence.get("codePresent"):
            source = pinned_source(replay, candidate)
            if source:
                evidence["pinnedSource"] = source
            if not evidence.get("abi"):
                abi = pinned_abi(replay, source) or source_getter_abi(
                    source.get("text") or evidence.get("sourceText") or "")
                if abi:
                    evidence = reader.inspect_contract(chain, address, artifact.get("txHash"),
                                                       artifact.get("blockNumber"), abi)
                    evidence["pinnedSource"] = source
        if needs_child_proof:
            self._child_proof(candidate, evidence, reader)
        candidates, checked = {key: candidate}, {key: evidence}
        children = discover_children({}, candidates, checked, reader)
        children.extend(discover_proven_children({}, candidates, checked, reader, client=replay))
        for child in children:
            checked[child["key"]] = child["evidence"]
        for item in checked.values():
            if not item.get("standard"):
                continue
            enrich_special_reads(item, reader)
            refresh_utility_reads(item, reader, utility_read_specs(item))
            record = enrich_utility({"chainId": item["chainId"],
                                     "contractAddress": item["address"]}, item)
            item["tokenMetadata"] = attach_token_metadata([record], reader)
            item["inspectionComplete"] = not item.get("warnings")
        evidence["inspectionComplete"] = evidence.get("detectionStatus") in {"not-nft", "unsupported"} or not evidence.get("warnings")
        for child in children:
            progress.setdefault("children", {})[child["key"]] = child
        return evidence, list(progress.get("children", {}).values())

    @staticmethod
    def _child_proof(candidate, evidence, reader):
        from .surf_nft_rules.children import FACTORIES, _call, _clone_target, _creation_proof
        from .surf_nft_rules.references import SEASONS, verify_seasons_constructor

        config = next((item for item in FACTORIES if item["chainId"] == candidate["chainId"]
                       and item["factory"] == candidate.get("factoryAddress")), None)
        evidence["factoryCreationVerified"] = False
        evidence["deploymentConfirmed"] = False
        evidence.pop("constructorProof", None)
        try:
            if candidate.get("constructorProof"):
                expected = {"kind": "seasons", "parent": SEASONS["hook"], "intermediate": SEASONS["canvas"],
                            "sourceCommit": SEASONS["commit"]}
                if (candidate["constructorProof"] != expected or candidate["chainId"] != 4663
                        or candidate["address"] != SEASONS["child"] or candidate.get("factoryAddress") != SEASONS["hook"]):
                    raise ValueError("No reviewed constructor origin")
                verified = verify_seasons_constructor(candidate, reader)
                evidence.update(factoryCreationVerified=True, factoryAddress=SEASONS["hook"],
                                constructorProof=verified["proof"],
                                deploymentConfirmed=evidence.get("codePresent") is True and evidence.get("receiptSuccess") is True)
                evidence["warnings"] = [warning for warning in evidence.get("warnings", [])
                                        if warning != "factory receipt confirms transaction success; address linkage relies on the launch artifact"]
                for warning in verified["warnings"]:
                    if warning not in evidence["warnings"]:
                        evidence["warnings"].append(warning)
                return
            proof = candidate["factoryProof"]
            if config is None:
                raise ValueError("No reviewed child factory")
            block, _ = reader._snapshot(candidate["chainId"])
            code = reader.rpc(candidate["chainId"], "eth_getCode", [config["factory"], block])
            if "0x" + keccak256(bytes.fromhex(code[2:])) != config["codeHash"]:
                raise ValueError("Factory runtime changed")
            getter = {"loom": "collections(uint256)", "artifacts": "pieceContract(uint16)", "arthouse": "collection(uint256)"}[config["kind"]]
            if _call(reader, candidate["chainId"], config["factory"], block, getter, "address", [proof["registryIndex"]]) != candidate["address"]:
                raise ValueError("Factory registry child mismatch")
            child_code = reader.rpc(candidate["chainId"], "eth_getCode", [candidate["address"], block])
            if _clone_target(child_code) != config["template"]:
                raise ValueError("Child clone implementation changed")
            tx, height = _creation_proof(reader, config, candidate["address"], block)
            if tx != candidate["artifact"].get("txHash") or height > int(block, 16):
                raise ValueError("Child creation receipt does not match candidate")
            evidence.update(factoryCreationVerified=True, factoryAddress=config["factory"],
                            implementationAddress=config["template"],
                            deploymentConfirmed=evidence.get("codePresent") is True and evidence.get("receiptSuccess") is True)
        except (RuntimeError, ValueError, TypeError, KeyError) as error:
            evidence.setdefault("warnings", []).append(str(error)[:180])

    @read_cycle
    async def advance(self, candidate, progress=None, *, budget, proof_only=False):
        from .surf_nft_client import BudgetExhausted, SourceUnavailable

        candidate = copy.deepcopy(candidate)
        candidate.setdefault("chainId", candidate.get("chain_id"))
        candidate.setdefault("address", candidate.get("contract"))
        candidate["address"] = str(candidate.get("address", "")).lower()
        candidate.setdefault("artifact", {"txHash": candidate.get("tx_hash"),
                                           "blockNumber": candidate.get("block_number")})
        candidate.setdefault("launch", {})
        chain = candidate["chainId"]
        if chain not in CHAINS or not re.fullmatch(r"0x[0-9a-f]{40}", candidate["address"]):
            raise ValueError("NFT inspection requires a supported mainnet and exact address")
        key = f"{chain}:{candidate['address']}"
        # Discovery clocks, related jobs and sites change independently of a
        # pinned chain read. Only inputs used to inspect/prove this deployment
        # may invalidate it; otherwise head refreshes restart it indefinitely.
        revision = inspection_revision(candidate)
        now = self.clock()
        valid_progress = self._valid_progress(progress)
        if (not valid_progress or progress.get("candidate_key") != key
                or progress.get("revision") != revision
                or not isinstance(progress.get("started_at"), (int, float))
                or not 0 <= now - progress["started_at"] <= 600):
            retained = progress if valid_progress and progress.get("candidate_key") == key and progress.get("revision") == revision else {}
            progress = {"candidate_key": key, "revision": revision, "started_at": now,
                        "observed_at": datetime.fromtimestamp(now, timezone.utc).isoformat(),
                        "responses": {}, "completed_operations": retained.get("completed_operations", 0),
                        "factory_cursors": retained.get("factory_cursors", {}),
                        "children": retained.get("children", {}),
                        "courier_scan": retained.get("courier_scan", {}),
                        "block_number": None, "block_timestamp": None}
        else:
            progress = copy.deepcopy(progress)
        while True:
            try:
                evidence, children = self._evaluate(candidate, progress, proof_only=proof_only)
            except _ProofReady:
                return InspectionResult(progress, progress.get('provisional'), [], False)
            except (_ReadNeeded, _ReadBatchNeeded) as needed:
                requests = needed.requests if isinstance(needed, _ReadBatchNeeded) else [needed]
                batch = getattr(self.client, 'rpc_batch', None)
                batching = isinstance(needed, _ReadBatchNeeded) and callable(batch) and chain != 4663
                requests = requests[:min(32, budget.rpc_limit - budget.rpc_calls)] if batching else requests[:1]
                try:
                    if not requests:
                        raise BudgetExhausted('NFT RPC slice reached')
                    request = requests[0]
                    if batching:
                        values = await batch(chain, [(item.args[1], item.args[2]) for item in requests],
                                             budget=budget, return_exceptions=True)
                    elif request.kind == "rpc":
                        values = [await self.client.rpc(*request.args, budget=budget)]
                    elif request.kind == "text":
                        values = [await self.client.source_text(*request.args, budget=budget)]
                    else:
                        values = [await self.client.source_json(*request.args, budget=budget)]
                except BudgetExhausted:
                    return InspectionResult(progress, progress.get("provisional"), list(progress.get("children", {}).values()), False)
                except SourceUnavailable as error:
                    values = [error] * len(requests)
                for request, value in zip(requests, values):
                    # Only an unavailable pinned context abandons the stage.
                    # Older optional construction probes retain their own errors.
                    requested_block = None
                    if request.kind == "rpc":
                        _, method, params = request.args
                        if method in ("eth_getCode", "eth_call"):
                            requested_block = params[-1]
                        elif method == "eth_getBlockByNumber":
                            requested_block = params[0]
                    pinned = progress.get("block_number")
                    if (isinstance(value, SourceUnavailable) and pinned is not None and requested_block == hex(pinned)
                            and any(term in str(value).lower() for term in
                                    ("header not found", "unknown block", "missing trie", "historical state unavailable"))):
                        progress["restart_reason"] = str(value)[:180]
                        progress["started_at"] = now - 601
                        return InspectionResult(progress, None, [], False)
                    if isinstance(value, SourceUnavailable):
                        saved = {"error": str(value)[:200]}
                    else:
                        encoded = json.dumps(value, separators=(",", ":")).encode()
                        saved = {"compressed": base64.b64encode(zlib.compress(encoded)).decode()} if len(encoded) > 512 else {"value": value}
                    progress["responses"][request.key] = saved
                    progress["completed_operations"] += 1
                    if request.kind == "rpc" and request.args[1] == "eth_blockNumber" and "value" in saved:
                        progress["block_number"] = _number(saved["value"])
                # Cache contract bounds one unfinished stage to 256 KiB.
                if len(json.dumps(progress, separators=(",", ":")).encode()) > 256 * 1024:
                    evidence = progress.get("provisional") or {"chainId": chain, "address": candidate["address"]}
                    evidence.setdefault("warnings", []).append("Inspection evidence exceeds 256 KiB stage limit")
                    evidence["inspectionComplete"] = False
                    progress["responses"] = {}
                    progress["limited"] = True
                    return InspectionResult(progress, evidence, list(progress.get("children", {}).values()), True)
            else:
                factory = evidence.get("factoryDiscovery", {})
                event_scan = evidence.get("eventScan", {})
                if (factory.get("nextCursor") and not factory.get("enumerationFinished")) or event_scan.get("nextBlock"):
                    # A registry page is a complete observation; the next page
                    # gets a new block, retaining only the explicit registry cursor.
                    progress["started_at"] = now - 601
                    return InspectionResult(progress, evidence, children, False)
                progress["complete"] = True
                return InspectionResult(progress, evidence, children, True)
