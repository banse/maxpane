"""Reference discovery must not turn a mentioned NFT into a swarm deployment."""
import pathlib
import sys
import unittest
from unittest.mock import patch

import maxpane_dashboard.data.surf_nft_rules.references as refs

A = "0x" + "12" * 20
B = "0x" + "34" * 20
JOB = "12345678-1234-1234-1234-123456789abc"


def job(text, **extra):
    return {"id": JOB, "objective": text, "state": "completed", **extra}


class ReferenceDiscoveryTests(unittest.TestCase):
    def scan(self, *jobs, **extra):
        return refs.discover_references({"jobDetails": {str(i): j for i, j in enumerate(jobs)}, **extra})

    def test_deployed_reference_preserves_provenance_but_never_promotes(self):
        result = self.scan(job(f"Our NFT was successfully deployed on Ethereum mainnet at {A}.",
                              delivery={"repoUrl": "https://github.com/identity-md-launches/launch-10-thing"}))
        candidate = result["candidates"][0]
        self.assertEqual((candidate["chainId"], candidate["address"]), (1, A))
        self.assertTrue(candidate["verificationEligible"])
        self.assertFalse(candidate["promoted"])
        self.assertIn(JOB, candidate["sourceJobIds"])

    def test_intended_future_deployment_is_not_success(self):
        result = self.scan(job(f"Build an NFT on Ethereum mainnet and deploy it at {A}."))
        self.assertEqual(result["candidates"], [])

    def test_testnet_deployment_not_relabelled_by_mainnet_identity_reference(self):
        result = self.scan(job(f"NFT deployed on Sepolia at {A}. Identity NFT is on Ethereum mainnet."))
        self.assertEqual(result["candidates"], [])

    def test_unknown_chain_remains_excluded(self):
        result = self.scan(job(f"Our NFT was deployed successfully at {A}."))
        self.assertEqual(result["candidates"], [])
        self.assertGreater(result["excludedCounts"].get("unsupported-or-ambiguous-chain", 0), 0)

    def test_known_launches_and_gating_dependencies_are_excluded(self):
        result = self.scan(job(f"Our NFT was deployed on Ethereum mainnet at {A}.\nPayment token: {B}."),
                           launches=[{"chainId": 1, "artifacts": [{"address": A}]}])
        self.assertEqual(result["candidates"], [])

    def test_existing_third_party_collection_is_diagnostic_only(self):
        result = self.scan(job(f"Integrate the existing NFT deployed on Ethereum mainnet at {A}."))
        self.assertEqual(len(result["candidates"]), 1)
        self.assertFalse(result["candidates"][0]["verificationEligible"])

    def test_dedup_uses_chain_and_address_and_preserves_job_links(self):
        result = self.scan(job(f"NFT deployed on Ethereum mainnet at {A}."),
                           job(f"NFT deployed on Robinhood mainnet at {A}."))
        self.assertEqual(len(result["candidates"]), 2)

    def test_publication_versions_include_full_body(self):
        result = refs.discover_references({"publications": [{"id": "job:" + JOB, "versions": [
            {"jobId": JOB, "state": "completed", "objective": f"NFT deployed on Ethereum mainnet at {A}."}]}]})
        self.assertEqual(result["candidates"][0]["sourceJobIds"], [JOB])

    def test_verify_never_probes_unassociated_references(self):
        result = self.scan(job(f"Integrate existing NFT deployed on Ethereum mainnet at {A}."))
        def unexpected(*args, **kwargs):
            self.fail("Unassociated NFT must not trigger network discovery")
        refs.verify_references(result, unexpected, unexpected)
        self.assertFalse(result["candidates"][0]["promoted"])

    def test_live_launch_child_reference_requires_direct_nft_label_and_matching_repo(self):
        repo = "https://github.com/identity-md-launches/launch-1033-place"
        body = (f"Build the site against live launch #1033 on Robinhood Chain (4663).\n\n"
                f"Contracts: PlaceHook {B}, Seasons (NFT + auction) {A}. Paired with IMD on Robinhood Chain.")
        result = self.scan(job(body, delivery={"repoUrl": repo}), launches=[{
            "id": "launch-id", "launchNumber": 1033, "chainId": 4663, "status": "live",
            "sourceRepoUrl": repo, "artifacts": [{"address": B}]}])
        self.assertEqual([row["address"] for row in result["candidates"]], [A])
        self.assertTrue(result["candidates"][0]["verificationEligible"])
        self.assertEqual(result["candidates"][0]["referencedLaunches"], [
            {"id": "launch-id", "launchNumber": 1033, "chainId": 4663}])

    def test_live_launch_claim_cannot_override_testnet_context(self):
        repo = "https://github.com/identity-md-launches/launch-1033-place"
        body = f"Live launch #1033 on Robinhood Chain.\n\nTestnet NFT contract {A}."
        result = self.scan(job(body, delivery={"repoUrl": repo}), launches=[{
            "id": "launch-id", "launchNumber": 1033, "chainId": 4663, "status": "live",
            "sourceRepoUrl": repo, "artifacts": []}])
        self.assertEqual(result["candidates"], [])

    def test_proven_child_disabled_when_parent_runtime_changes(self):
        config = refs.SEASONS
        key = f"4663:{config['hook']}"
        parent = {"launch": {"id": "launch", "sourceCommit": config["commit"]}, "artifact": {"txHash": "0x" + "ab" * 32}}
        class Inspector:
            observed_at = "2026-10-16T00:00:00Z"
            def _snapshot(self, chain):
                return "0x100", "2026-10-16T00:00:00Z"
            def rpc(self, chain, method, params):
                if method != "eth_getCode":
                    raise AssertionError("changed bytecode must disable getters")
                return "0x6001"
        checked = {}
        self.assertEqual(refs.discover_proven_children({}, {key: parent}, checked, Inspector()), [])
        self.assertFalse(checked[key]["childDiscovery"]["complete"])
        self.assertIn("runtime", checked[key]["childDiscovery"]["warnings"][0])

    def child_fixture(self, failure=None):
        config = refs.SEASONS
        codes = {target: "0x600" + str(i) for i, target in enumerate(config["hashes"])}
        hashes = {target: "0x" + refs.keccak256(bytes.fromhex(code[2:])) for target, code in codes.items()}
        tx = "0x" + "ab" * 32
        parent = {"launch": {"id": "launch", "sourceCommit": config["commit"]}, "artifact": {"txHash": tx}}
        class Inspector:
            observed_at = "2026-10-16T00:00:00Z"
            def _snapshot(self, chain):
                return "0x64", "2026-10-16T00:00:00Z"
            def rpc(self, chain, method, params):
                if method == "eth_getCode":
                    if params[1] == "0x59":
                        if failure == "no-archive":
                            raise RuntimeError("historical state unavailable")
                        return codes[params[0]] if failure == "preexisting" else "0x"
                    return codes[params[0]]
                if method == "eth_getTransactionReceipt":
                    events = ((config["hook"], "PoolBound(bytes32,address,uint256)"), (config["canvas"], "Started(address,uint256)"))
                    return {"status": "0x1", "transactionHash": tx, "blockNumber": "0x5a",
                            "logs": [] if failure == "events" else [{
                                "address": config["factory"], "transactionHash": tx,
                                "topics": [config["launchEventTopic"], "0x" + format(1033, "064x"),
                                           "0x" + "00" * 12 + config["token"][2:], "0x" + "00" * 12 + config["hook"][2:]]}] + [
                                {"address": target, "topics": ["0x" + refs.keccak256(signature.encode())], "transactionHash": tx}
                                for target, signature in events]}
                if method == "eth_call":
                    data = params[0]["data"]
                    address = (config["canvas"] if data == refs.selector("canvas()") else
                               config["child"] if data == refs.selector("seasons()") else None)
                    if address:
                        return "0x" + ("00" * 32 if failure == "getter" else "00" * 12 + address[2:])
                    return "0x" + format(1, "064x")
                raise AssertionError(method)
            def inspect_contract(self, *args, **kwargs):
                return {"standard": None if failure == "not-nft" else "ERC-721", "codeHash": hashes[config["child"]], "reads": {}}
        return {"4663:" + config["hook"]: parent}, hashes, Inspector()

    def test_proven_child_requires_complete_construction_proof(self):
        parents, hashes, inspector = self.child_fixture()
        checked = {}
        with patch.dict(refs.SEASONS, {"hashes": hashes}):
            children = refs.discover_proven_children({}, parents, checked, inspector)
        self.assertEqual(len(children), 1)
        self.assertTrue(children[0]["evidence"]["factoryCreationVerified"])
        self.assertEqual(children[0]["evidence"]["stats"]["totalSupply"], 0)
        self.assertEqual(children[0]["evidence"]["dependencyReads"]["Canvas"]["reads"]["currentSeason"], 1)

    def test_archive_unavailability_is_explicit_with_independent_constructor_proof(self):
        parents, hashes, inspector = self.child_fixture("no-archive")
        with patch.dict(refs.SEASONS, {"hashes": hashes}):
            children = refs.discover_proven_children({}, parents, {}, inspector)
        self.assertEqual(len(children), 1)
        proof = children[0]["evidence"]["constructorProof"]
        self.assertFalse(proof["historicalCodeVerified"])
        self.assertIsNone(proof["absentBeforeBlock"])
        self.assertTrue(proof["launchFactoryEventVerified"])

    def test_child_not_promoted_with_missing_events_existing_code_wrong_getter_or_non_nft(self):
        for failure in ("events", "preexisting", "getter", "not-nft"):
            with self.subTest(failure=failure):
                parents, hashes, inspector = self.child_fixture(failure)
                checked = {}
                with patch.dict(refs.SEASONS, {"hashes": hashes}):
                    children = refs.discover_proven_children({}, parents, checked, inspector)
                self.assertEqual(children, [])
                self.assertFalse(next(iter(checked.values()))["childDiscovery"]["complete"])


if __name__ == "__main__":
    unittest.main()

import json
import pytest
from maxpane_dashboard.data.surf_nft_chain import SurfNftInspector
from maxpane_dashboard.data.surf_nft_client import Budget, SourceUnavailable


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', [None, 'parent-code', 'missing-marker', 'missing-origin', 'missing-events', 'no-archive'])
async def test_serialized_seasons_child_refresh_rechecks_constructor_provenance(monkeypatch, failure):
    parents, hashes, initial = ReferenceDiscoveryTests().child_fixture()
    monkeypatch.setitem(refs.SEASONS, 'hashes', hashes)
    discovered = refs.discover_proven_children({}, parents, {}, initial)
    assert len(discovered) == 1
    candidate = json.loads(json.dumps(discovered[0]['candidate']))
    candidate['chainId'] = 4663
    candidate['launch']['chainId'] = 4663
    if failure in ('missing-marker', 'missing-origin'):
        candidate.pop('constructorProof', None)
    if failure == 'missing-origin':
        candidate.pop('factoryAddress', None)
    sent=[]
    class Client:
        async def rpc(self, chain, method, params, *, budget):
            budget.consume(http=1, rpc=1)
            sent.append((method, params))
            if method == 'eth_chainId': return hex(4663)
            if method == 'eth_blockNumber': return '0x64'
            if method == 'eth_getBlockByNumber': return {'number': params[0], 'timestamp': '0x69000000'}
            if method == 'eth_getCode' and params[0] == refs.SEASONS['hook'] and failure == 'parent-code':
                return '0x6009'
            if method == 'eth_getCode' and params[1] == '0x59' and failure == 'no-archive':
                raise SourceUnavailable('missing trie node: historical state unavailable')
            if method == 'eth_call' and params[0]['data'].startswith('0x01ffc9a7'):
                supported = params[0]['data'][10:18] in ('01ffc9a7', '80ac58cd')
                return '0x' + format(int(supported), '064x')
            result = initial.rpc(chain, method, params)
            if method == 'eth_getTransactionReceipt' and failure == 'missing-events':
                result['logs'] = []
            return result
        async def source_json(self, *args, **kwargs):
            raise AssertionError('No source HTTP expected')
        async def source_text(self, *args, **kwargs):
            raise AssertionError('No source HTTP expected')
    reader = SurfNftInspector(Client(), clock=lambda:1792200000.)
    first = await reader.advance(candidate, None, budget=Budget(http_limit=10, rpc_limit=10, monotonic=lambda:1.))
    assert first.evidence is None or first.evidence.get('deploymentConfirmed') is not True
    result = await reader.advance(candidate, json.loads(json.dumps(first.progress)),
                                  budget=Budget(http_limit=128, rpc_limit=128, monotonic=lambda:1.))
    assert result.complete
    if failure not in (None, 'no-archive'):
        assert result.evidence['deploymentConfirmed'] is False
        assert result.evidence.get('factoryCreationVerified') is not True
        assert result.evidence.get('constructorProof') is None
    else:
        assert candidate['constructorProof']['kind'] == 'seasons'
        assert result.evidence['deploymentConfirmed'] is True
        assert result.evidence['factoryCreationVerified'] is True
        assert result.evidence['constructorProof']['parent'] == refs.SEASONS['hook']
        assert result.evidence['constructorProof']['launchFactoryEventVerified'] is True
        assert result.evidence['constructorProof']['historicalCodeVerified'] is (failure != 'no-archive')
    if failure not in ('missing-marker', 'missing-origin'):
        assert any(method == 'eth_getCode' and params == [refs.SEASONS['hook'], '0x64'] for method, params in sent)
