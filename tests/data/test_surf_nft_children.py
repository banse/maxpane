import pathlib
import sys
import unittest
from unittest.mock import patch

from maxpane_dashboard.data.surf_nft_chain import keccak256, selector
from maxpane_dashboard.data.surf_nft_rules.children import discover_children, enrich_special_reads

FACTORY = "0x" + "11" * 20
TEMPLATE = "0x" + "22" * 20
CHILD = "0x" + "33" * 20
TX = "0x" + "44" * 32
EVENT = "CollectionCreated(address,address,string,uint256)"
CONFIG = {"chainId": 1, "factory": FACTORY, "kind": "loom", "codeHash": "0x" + keccak256(bytes.fromhex("6000")), "template": TEMPLATE, "sourceName": "LoomCollection"}


def word(n):
    return "0x" + format(n, "064x")


class FakeInspector:
    observed_at = "2026-10-16T00:00:00Z"
    def __init__(self, count=1, fail_count=False, bad_clone=False, failed_receipt=False):
        self.count = count
        self.fail_count, self.bad_clone, self.failed_receipt = fail_count, bad_clone, failed_receipt
        self.calls = []

    def dependency_code(self, chain, address, block):
        return {"codePresent": True, "codeReviewed": True, "codeHash": "0x"+"aa"*32}

    def _snapshot(self, chain):
        return "0x100", "2026-10-16T00:00:00Z"

    def rpc(self, chain, method, params):
        self.calls.append((method, params))
        if method == "eth_getCode":
            if params[0] == FACTORY:
                return "0x6000"
            return "0x6000" if self.bad_clone else "0x363d3d373d3d3d363d73" + TEMPLATE[2:] + "5af43d82803e903d91602b57fd5bf3"
        if method == "eth_call":
            data = params[0]["data"]
            if data == selector("implementation()"):
                return word(int(TEMPLATE, 16))
            if data == selector("collectionCount()"):
                if self.fail_count:
                    raise RuntimeError("offline")
                return word(self.count)
            if data.startswith(selector("collections(uint256)")):
                return word(int(CHILD, 16))
        if method == "eth_getTransactionReceipt":
            return {"status": "0x0" if self.failed_receipt else "0x1", "blockNumber": "0x90", "transactionHash": TX,
                    "logs": [{"address": FACTORY, "topics": ["0x" + keccak256(EVENT.encode()), word(int(CHILD, 16))]}]}
        raise AssertionError((method, params))

    def fetch_json(self, url):
        return {"creation_transaction_hash": TX}

    def inspect_contract(self, chain, address, tx_hash=None, block_number=None, abi=None):
        return {"chainId": chain, "address": address, "standard": "ERC-721", "codePresent": True,
                "receiptSuccess": not self.failed_receipt, "name": "Real child", "codeHash": "0xabc", "warnings": [], "reads": {}}


class ChildDiscoveryTests(unittest.TestCase):
    def fixtures(self):
        launch = {"id": "launch", "chainId": 1, "sourceRepoUrl": "https://github.com/example/repo", "sourceCommit": "a" * 40}
        candidates = {"1:" + FACTORY: {"chainId": 1, "address": FACTORY, "launch": launch, "artifact": {"name": "LoomFactory"}, "launchIds": ["launch"], "jobIds": ["job"]}}
        checked = {"1:" + TEMPLATE: {"abi": [], "pinnedSource": {"text": "contract LoomCollection {}"}}}
        return candidates, checked

    def test_discovers_only_real_child_with_creation_receipt_and_clone_target(self):
        candidates, checked = self.fixtures()
        found = discover_children({}, candidates, checked, FakeInspector(), factories=[CONFIG])
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["candidate"]["address"], CHILD)
        self.assertTrue(found[0]["evidence"]["factoryCreationVerified"])
        self.assertTrue(checked["1:" + TEMPLATE]["isTemplate"])

    def test_count_failure_is_unknown_not_zero(self):
        candidates, checked = self.fixtures()
        self.assertEqual(discover_children({}, candidates, checked, FakeInspector(fail_count=True), factories=[CONFIG]), [])
        report = checked["1:" + FACTORY]["factoryDiscovery"]
        self.assertFalse(report["complete"])
        self.assertIsNone(report["count"])

    def test_foreign_clone_and_failed_receipt_do_not_pass(self):
        for inspector in (FakeInspector(bad_clone=True), FakeInspector(failed_receipt=True)):
            candidates, checked = self.fixtures()
            result = discover_children({}, candidates, checked, inspector, factories=[CONFIG])
            self.assertTrue(not result or not result[0]["evidence"]["factoryCreationVerified"])

    def test_child_limit_reports_incomplete(self):
        candidates, checked = self.fixtures()
        discover_children({}, candidates, checked, FakeInspector(count=10), factories=[CONFIG], max_children=1)
        self.assertFalse(checked["1:" + FACTORY]["factoryDiscovery"]["complete"])

    def test_counts_are_reread_every_run(self):
        candidates, checked = self.fixtures()
        inspector = FakeInspector(count=0)
        self.assertEqual(discover_children({}, candidates, checked, inspector, factories=[CONFIG]), [])
        inspector.count = 1
        self.assertEqual(len(discover_children({}, candidates, checked, inspector, factories=[CONFIG])), 1)

    def test_hivewars_dependency_reads_are_fresh_and_pinned(self):
        inspector = FakeInspector()
        calls = []
        def read(chain, method, params):
            calls.append((method, params))
            return word(123)
        inspector.rpc = read
        evidence = {"chainId": 1, "address": "0x800504f0d471fa3647c2414167e55ca06df16ab6",
                    "codeHash": "0x186d053da07fe71e470cc5d632ffef7ed61582b73bdf713707b78bac3c3c1c9f"}
        enrich_special_reads(evidence, inspector)
        dependency = evidence["dependencyReads"]["HiveWars"]
        self.assertEqual(dependency["reads"]["startTime"], 123)
        self.assertEqual(dependency["readBlock"], 256)
        self.assertTrue(all(params[-1] == "0x100" for method, params in calls))

    def test_unknown_code_does_not_enable_dependency_adapter(self):
        inspector = FakeInspector()
        evidence = {"chainId": 1, "address": "0x800504f0d471fa3647c2414167e55ca06df16ab6", "codeHash": "0xdead"}
        self.assertEqual(enrich_special_reads(evidence, inspector), evidence)
        self.assertFalse(inspector.calls)

    def test_farm_limit_keeps_live_supply_unknown(self):
        inspector = FakeInspector()
        inspector.rpc = lambda *args: word(1000)
        evidence = {"chainId": 4663, "address": "0xdda6387bf0244fc82eb3dbda168acc4d9eed56a3",
                    "codeHash": "0xd4a23d86800de9b106d7929bedab057f0c02d244ea60bb6bec00bb259a7a4961"}
        enrich_special_reads(evidence, inspector, max_items=1)
        self.assertIsNone(evidence["specialStats"]["liveItems"])
        self.assertFalse(evidence["specialStats"]["complete"])

    def test_courier_log_failure_never_means_empty_catalog(self):
        evidence = {"chainId": 4663, "address": "0x2c328e6d3ae72e5b06e10884d83b01f1b0342f85",
                    "codeHash": "0x245d6d99cbbecaa8df8e0c0e80840a3bd8648592357111fd587faa2b5bbd99c3",
                    "deployment": {"blockNumber": 100}}
        with patch.object(FakeInspector, "rpc", side_effect=RuntimeError("provider unavailable")):
            enrich_special_reads(evidence, FakeInspector())
        self.assertIsNone(evidence["eventScan"]["events"])
        self.assertFalse(evidence["eventScan"]["complete"])
        self.assertNotIn("totalSupply", evidence.get("stats", {}))

    def test_changed_factory_runtime_disables_discovery(self):
        candidates, checked = self.fixtures()
        config = {**CONFIG, "codeHash": "0xdead"}
        found = discover_children({}, candidates, checked, FakeInspector(), factories=[config])
        self.assertEqual(found, [])
        self.assertFalse(checked["1:" + FACTORY]["factoryDiscovery"]["complete"])


if __name__ == "__main__":
    unittest.main()


def test_courier_history_is_chunked_and_item_reads_use_owned_rpc():
    from maxpane_dashboard.data.surf_nft_rules.children import _courier_items
    address='0x'+'ab'*20
    topic='0x'+keccak256(b'ItemConfigured(uint256,uint256,uint256,uint256,bool,string)')
    class Reader:
        courier_scan={}
        ranges=[]
        def _snapshot(self,chain):return hex(10100),'2026-10-16T00:00:00Z'
        def rpc(self,chain,method,params):
            if method=='eth_getLogs':
                first,last=int(params[0]['fromBlock'],16),int(params[0]['toBlock'],16)
                self.ranges.append((first,last))
                return [{'address':address,'blockNumber':hex(first),'topics':[topic,word(7)]}]
            assert method=='eth_call'
            assert params[-1]==hex(10100)
            return '0x'+''.join(format(v,'064x') for v in (3,20,1,2,1,1))
    reader=Reader()
    evidence={'chainId':4663,'address':address,'deployment':{'blockNumber':100}}
    _courier_items(evidence,reader,256)
    assert evidence['eventScan']['complete'] is False
    assert evidence['eventScan']['nextBlock']==10100
    _courier_items(evidence,reader,256)
    assert evidence['eventScan']['complete'] is True
    assert evidence['eventScan']['items'][0]['minted']==2
    assert reader.ranges==[(100,10099),(10100,10100)]


def test_unlocked_artifacts_factory_is_a_checked_zero():
    config={**CONFIG,'kind':'artifacts'}
    inspector=FakeInspector()
    old=inspector.rpc
    def rpc(chain,method,params):
        if method=='eth_call' and params[0]['data']==selector('pieceImplementation()'):
            return word(int(TEMPLATE,16))
        if method=='eth_call' and params[0]['data']==selector('locked()'):
            return word(0)
        return old(chain,method,params)
    inspector.rpc=rpc
    candidates,checked=ChildDiscoveryTests().fixtures()
    assert discover_children({},candidates,checked,inspector,factories=[config])==[]
    report=checked['1:'+FACTORY]['factoryDiscovery']
    assert report['count']==0 and report['complete'] is True


def test_arthouse_child_requires_its_matching_unindexed_creation_event():
    config={**CONFIG,'kind':'arthouse'}
    inspector=FakeInspector()
    old=inspector.rpc
    def rpc(chain,method,params):
        if method=='eth_call':
            data=params[0]['data']
            if data==selector('collectionImplementation()'):return word(int(TEMPLATE,16))
            if data.startswith(selector('collection(uint256)')):return word(int(CHILD,16))
        if method=='eth_getTransactionReceipt':
            return {'status':'0x1','blockNumber':'0x90','transactionHash':TX,'logs':[{
                'address':FACTORY,'topics':['0x'+keccak256(b'CollectionCreated(uint256,address,address,string,string)')],
                'data':word(int(CHILD,16))}]}
        return old(chain,method,params)
    inspector.rpc=rpc
    candidates,checked=ChildDiscoveryTests().fixtures()
    found=discover_children({},candidates,checked,inspector,factories=[config])
    assert len(found)==1 and found[0]['evidence']['factoryCreationVerified'] is True
