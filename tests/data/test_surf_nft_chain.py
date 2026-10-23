"""Behavioral fixtures for mainnet-only, read-only NFT inspection."""
import pathlib
import sys
import unittest

from maxpane_dashboard.data.surf_nft_chain import Inspector, selector


ADDRESS = "0x" + "12" * 20
TX = "0x" + "34" * 32


def word(value):
    return "0x" + format(value, "064x")


class FakeRPC:
    def __init__(self, chain=1, code="0x6000", receipt_status="0x1", liar=False):
        self.chain, self.code = chain, code
        self.receipt_status, self.liar = receipt_status, liar
        self.calls = []
        self.reads = {"totalSupply()": word(0), "maxSupply()": word(100)}

    def __call__(self, chain, method, params):
        self.calls.append((method, params))
        if method == "eth_chainId":
            return hex(self.chain)
        if method == "eth_blockNumber":
            return "0x100"
        if method == "eth_getBlockByNumber":
            return {"number": params[0], "timestamp": "0x65000000"}
        if method == "eth_getCode":
            return self.code
        if method == "eth_getTransactionReceipt":
            return {"status": self.receipt_status, "blockNumber": "0x90", "transactionHash": TX}
        if method == "eth_call":
            data = params[0]["data"]
            if data.startswith("0x01ffc9a7"):
                return word(self.liar or data[10:18] in ("01ffc9a7", "80ac58cd"))
            for sig, result in self.reads.items():
                if data == selector(sig):
                    return result
            raise RuntimeError("execution reverted")
        raise AssertionError(method)


class ChainInspectionTests(unittest.TestCase):
    def inspector(self, rpc):
        return Inspector(rpc=rpc, fetch_json=lambda url: {})

    def test_deployer_is_validated_from_confirmed_receipt(self):
        for sender, status, expected in [('0x'+'AB'*20, '0x1', '0x'+'ab'*20),
                                         ('invalid', '0x1', None),
                                         ('0x'+'00'*20, '0x1', None),
                                         ('0x'+'ab'*20, '0x0', None)]:
            rpc = FakeRPC(receipt_status=status)
            def source(chain, method, params):
                value = rpc(chain, method, params)
                if method == 'eth_getTransactionReceipt':
                    value['from'] = sender
                return value
            result = self.inspector(source).inspect_contract(1, ADDRESS, TX)
            self.assertEqual(result['deployment'].get('deployer'), expected)

    def test_selector_uses_ethereum_keccak(self):
        self.assertEqual(selector("totalSupply()"), "0x18160ddd")
        self.assertEqual(selector("supportsInterface(bytes4)"), "0x01ffc9a7")

    def test_testnets_are_rejected_before_any_request(self):
        rpc = FakeRPC()
        with self.assertRaises(ValueError):
            self.inspector(rpc).inspect_contract(11155111, ADDRESS)
        self.assertFalse(rpc.calls)

    def test_wrong_chain_fails_closed(self):
        rpc = FakeRPC(chain=11155111)
        result = self.inspector(rpc).inspect_contract(1, ADDRESS)
        self.assertIsNone(result["standard"])
        self.assertIsNone(result["codePresent"])
        self.assertTrue(any("chain ID" in item for item in result["warnings"]))
        self.assertEqual([x[0] for x in rpc.calls], ["eth_chainId"])

    def test_rejects_contract_claiming_every_interface(self):
        rpc = FakeRPC(liar=True)
        result = self.inspector(rpc).inspect_contract(1, ADDRESS)
        self.assertIsNone(result["standard"])
        self.assertNotIn("eth_getCode", [x[0] for x in rpc.calls])

    def test_ordinary_erc165_revert_is_unsupported_not_network_failure(self):
        rpc = FakeRPC()
        def reverts(chain, method, params):
            if method == "eth_call":
                raise RuntimeError("execution reverted")
            return rpc(chain, method, params)
        result = self.inspector(reverts).inspect_contract(1, ADDRESS)
        self.assertEqual(result["detectionStatus"], "unsupported")
        self.assertFalse(result["warnings"])

    def test_transport_failure_is_unknown_not_unsupported(self):
        rpc = FakeRPC()
        def offline(chain, method, params):
            if method == "eth_call":
                raise OSError("connection timed out")
            return rpc(chain, method, params)
        result = self.inspector(offline).inspect_contract(1, ADDRESS)
        self.assertEqual(result["detectionStatus"], "unavailable")
        self.assertTrue(result["warnings"])

    def test_no_code_cannot_be_a_confirmed_collection(self):
        result = self.inspector(FakeRPC(code="0x")).inspect_contract(1, ADDRESS, TX)
        self.assertFalse(result["codePresent"])
        self.assertFalse(result["deploymentConfirmed"])

    def test_reverted_receipt_does_not_confirm_deployment(self):
        result = self.inspector(FakeRPC(receipt_status="0x0")).inspect_contract(1, ADDRESS, TX)
        self.assertFalse(result["receiptSuccess"])
        self.assertFalse(result["deploymentConfirmed"])
        self.assertIsNone(result["deployment"]["timestamp"])

    def test_transient_missing_receipt_is_retried(self):
        rpc = FakeRPC()
        count = 0
        def transient(chain, method, params):
            nonlocal count
            if method == "eth_getTransactionReceipt":
                count += 1
                if count < 3:
                    return None
            return rpc(chain, method, params)
        result = self.inspector(transient).inspect_contract(1, ADDRESS, TX)
        self.assertTrue(result["deploymentConfirmed"])
        self.assertEqual(count, 3)

    def test_receipt_that_created_another_address_cannot_confirm_this_one(self):
        rpc = FakeRPC()
        def other_address(chain, method, params):
            value = rpc(chain, method, params)
            if method == "eth_getTransactionReceipt":
                value["contractAddress"] = "0x" + "ab" * 20
            return value
        result = self.inspector(other_address).inspect_contract(1, ADDRESS, TX)
        self.assertFalse(result["deploymentConfirmed"])
        self.assertFalse(result["receiptAddressMatches"])

    def test_without_receipt_bytecode_is_known_but_deployment_is_unconfirmed(self):
        result = self.inspector(FakeRPC()).inspect_contract(1, ADDRESS)
        self.assertTrue(result["codePresent"])
        self.assertIsNone(result["receiptSuccess"])
        self.assertFalse(result["deploymentConfirmed"])

    def test_zero_and_unknown_remain_distinct_and_reads_use_pinned_block(self):
        rpc = FakeRPC()
        result = self.inspector(rpc).inspect_contract(1, ADDRESS, TX)
        self.assertEqual(result["standard"], "ERC-721")
        self.assertEqual(result["stats"]["totalSupply"], 0)
        self.assertIsNone(result["stats"]["holders"])
        self.assertTrue(result["deploymentConfirmed"])
        self.assertEqual(result["deployment"]["blockNumber"], 144)
        self.assertTrue(all(params[-1] == "0x100" for method, params in rpc.calls if method in ("eth_call", "eth_getCode")))

    def test_supplied_abi_only_calls_read_methods_without_arguments(self):
        rpc = FakeRPC(chain=4663)
        rpc.reads["mintStart()"] = word(0)
        abi = [
            {"type": "function", "name": "mintStart", "inputs": [], "outputs": [{"type": "uint256"}], "stateMutability": "view"},
            {"type": "function", "name": "mint", "inputs": [], "outputs": [], "stateMutability": "nonpayable"},
        ]
        result = self.inspector(rpc).inspect_contract(4663, ADDRESS, abi=abi)
        self.assertEqual(result["reads"]["mintStart"], 0)
        self.assertEqual(result["abiSource"], "supplied")
        self.assertNotIn(selector("mint()"), [params[0].get("data") for method, params in rpc.calls if method == "eth_call"])

    def test_inconsistent_indexer_holder_count_is_not_reported_as_fact(self):
        inspector = Inspector(rpc=FakeRPC(), fetch_json=lambda url: {"holders_count": "101"} if "/tokens/" in url else {})
        result = inspector.inspect_contract(1, ADDRESS)
        self.assertIsNone(result["stats"]["holders"])
        self.assertTrue(any("holder" in text for text in result["warnings"]))

    def test_malformed_public_abi_and_explorer_data_do_not_crash_scan(self):
        inspector = Inspector(rpc=FakeRPC(), fetch_json=lambda url: [])
        result = inspector.inspect_contract(1, ADDRESS, abi=[None, "invalid", {"type": "function", "outputs": None}])
        self.assertEqual(result["standard"], "ERC-721")
        self.assertEqual(result["stats"]["totalSupply"], 0)
        self.assertTrue(result["warnings"])


if __name__ == "__main__":
    unittest.main()

import json
from pathlib import Path
import pytest
from maxpane_dashboard.data.surf_nft_chain import SurfNftInspector


class AsyncReads:
    def __init__(self):
        self.rpc_source = FakeRPC()
        self.sent = []
    async def rpc(self, chain, method, params, *, budget):
        from maxpane_dashboard.data.surf_nft_client import SourceUnavailable
        budget.consume(http=1, rpc=1)
        self.sent.append((method, json.dumps(params)))
        try:
            return self.rpc_source(chain, method, params)
        except RuntimeError as error:
            raise SourceUnavailable(str(error)) from error
    async def source_json(self, url, *, budget):
        budget.consume(http=1)
        self.sent.append(('source', url))
        return {}
    async def source_text(self, url, *, budget):
        raise AssertionError('no unpinned source')


@pytest.mark.asyncio
async def test_resume_sends_each_unique_operation_once_and_keeps_block():
    from maxpane_dashboard.data.surf_nft_client import Budget
    now = [1792200000.0]
    client = AsyncReads()
    reader = SurfNftInspector(client, clock=lambda: now[0])
    candidate = {'chainId': 1, 'address': ADDRESS, 'artifact': {'txHash': TX}, 'launch': {}}
    progress = None
    operations = []
    for _ in range(30):
        result = await reader.advance(candidate, progress, budget=Budget(http_limit=2, rpc_limit=2))
        progress = result.progress
        operations.append(progress['completed_operations'])
        now[0] += 1
        if result.complete:
            break
    assert result.complete
    assert all(b > a for a, b in zip(operations, operations[1:]))
    assert len(client.sent) == len(set(client.sent))
    assert result.evidence['readBlock'] == 256
    assert result.evidence['readTimestamp'] == '2023-09-12T06:06:56Z'
    assert result.evidence['checkedAt'] == result.progress['observed_at']
    assert result.evidence['checkedAt'] == '2026-10-17T01:20:00+00:00'


@pytest.mark.asyncio
async def test_expired_stage_discards_old_getters_and_starts_new_observation():
    from maxpane_dashboard.data.surf_nft_client import Budget
    now = [1792200000.0]
    client = AsyncReads()
    reader = SurfNftInspector(client, clock=lambda: now[0])
    candidate = {'chainId': 1, 'address': ADDRESS, 'artifact': {'txHash': TX}}
    first = await reader.advance(candidate, None, budget=Budget(http_limit=2, rpc_limit=2))
    now[0] += 601
    second = await reader.advance(candidate, first.progress, budget=Budget(http_limit=2, rpc_limit=2))
    assert second.progress['started_at'] == now[0]
    assert second.progress['observed_at'] != first.progress['observed_at']
    assert client.sent.count(('eth_chainId', '[]')) == 2


@pytest.mark.asyncio
async def test_discovery_metadata_refresh_does_not_restart_pinned_reads():
    from maxpane_dashboard.data.surf_nft_client import Budget
    client = AsyncReads()
    now = [1792200000.0]
    reader = SurfNftInspector(client, clock=lambda: now[0])
    candidate = {'chainId': 1, 'address': ADDRESS, 'artifact': {'txHash': TX},
                 'launch': {'_observed_at': now[0], 'updatedAt': 'first'},
                 'provenance': {'observed_at': now[0]}, 'jobIds': []}
    progress = None
    for cycle in range(30):
        candidate['artifact']['role'] = str(cycle)
        candidate['launch'].update(_observed_at=now[0], updatedAt=str(cycle))
        candidate['provenance']['observed_at'] = now[0]
        candidate['jobIds'] = [str(cycle)]
        candidate['sites'] = [{'url': f'https://example.org/{cycle}'}]
        result = await reader.advance(candidate, progress, budget=Budget(http_limit=2, rpc_limit=2))
        progress = result.progress
        now[0] += 1
        if result.complete:
            break
    assert result.complete
    assert result.evidence['deploymentConfirmed'] is True
    assert client.sent.count(('eth_chainId', '[]')) == 1
    assert len(client.sent) == len(set(client.sent))


@pytest.mark.asyncio
@pytest.mark.parametrize('change', [
    {'artifact': {'txHash': '0x' + 'ab' * 32}},
    {'launch': {'sourceRepoUrl': 'https://github.com/example/nft', 'sourceCommit': 'a' * 40}},
    {'launch': {'attestation': {'contracts': [{'name': 'NFT', 'path': 'src/NFT.sol'}]}}},
    {'abi': [{'type': 'function', 'name': 'mintPrice'}]},
    {'factoryAddress': '0x' + 'ab' * 20},
    {'factoryProof': {'registryIndex': 2}},
    {'constructorProof': {'transactionHash': TX}},
])
async def test_changed_inspection_inputs_restart_pinned_reads(change):
    from maxpane_dashboard.data.surf_nft_client import Budget
    client = AsyncReads()
    reader = SurfNftInspector(client, clock=lambda: 1792200000.)
    candidate = {'chainId': 1, 'address': ADDRESS, 'artifact': {'txHash': TX}}
    first = await reader.advance(candidate, budget=Budget(http_limit=2, rpc_limit=2))
    await reader.advance({**candidate, **change}, first.progress, budget=Budget(http_limit=2, rpc_limit=2))
    assert client.sent.count(('eth_chainId', '[]')) == 2

@pytest.mark.asyncio
async def test_factory_cursor_survives_expiry_and_children_are_deferred(monkeypatch):
    from maxpane_dashboard.data.surf_nft_client import Budget
    from maxpane_dashboard.data.surf_nft_rules import children
    from maxpane_dashboard.data.surf_nft_chain import keccak256
    factory, template = '0x'+'11'*20, '0x'+'22'*20
    config = {'chainId':1,'factory':factory,'template':template,'kind':'loom',
              'codeHash':'0x'+keccak256(bytes.fromhex('6000')),'sourceName':'LoomCollection'}
    monkeypatch.setattr(children, 'FACTORIES', [config])
    registry_reads = []
    class Client:
        async def rpc(self, chain, method, params, *, budget):
            budget.consume(http=1, rpc=1)
            if method=='eth_chainId': return '0x1'
            if method=='eth_blockNumber': return '0x100'
            if method=='eth_getBlockByNumber': return {'number':params[0],'timestamp':'0x65000000'}
            if method=='eth_getCode':
                return '0x6000' if params[0]==factory else '0x363d3d373d3d3d363d73'+template[2:]+'5af43d82803e903d91602b57fd5bf3'
            if method=='eth_call':
                data=params[0]['data']
                if data.startswith('0x01ffc9a7'): return word(0)
                if data==selector('implementation()'): return word(int(template,16))
                if data==selector('collectionCount()'): return word(12)
                if data.startswith(selector('collections(uint256)')):
                    index=int(data[10:],16);registry_reads.append(index);return word(index+1)
            if method=='eth_getTransactionReceipt':
                child=int(params[0],16)
                return {'status':'0x1','blockNumber':'0x90','transactionHash':params[0],
                        'logs':[{'address':factory,'topics':['0x'+keccak256(b'CollectionCreated(address,address,string,uint256)'),word(child)]}]}
            raise AssertionError((method,params))
        async def source_json(self,url,*,budget):
            budget.consume(http=1)
            return {'creation_transaction_hash':'0x'+format(int(url.rsplit('/',1)[1],16),'064x')}
    now=[1792200000.0]
    inspector=SurfNftInspector(Client(),clock=lambda:now[0])
    candidate={'chainId':1,'address':factory,'launch':{},'artifact':{}}
    progress=None
    seen=set()
    for cycle in range(80):
        result=await inspector.advance(candidate,progress,budget=Budget(http_limit=4,rpc_limit=4))
        progress=result.progress
        seen.update(child['key'] for child in result.children)
        if len(seen)==4 and cycle<30:
            now[0]+=601  # restart the block context, retaining successful registry cursor.
        if result.complete: break
    assert result.complete
    assert len(seen)==12
    assert set(registry_reads)==set(range(12))
    assert len(registry_reads)<=14  # at most the in-progress entry is replayed after expiry.
    assert all(child['evidence'].get('standard') is None for child in result.children)
    assert all(child['candidate']['factoryProof']['kind']=='loom' for child in result.children)

@pytest.mark.asyncio
async def test_malformed_retained_stage_restarts_without_crashing():
    from maxpane_dashboard.data.surf_nft_client import Budget
    client=AsyncReads()
    reader=SurfNftInspector(client,clock=lambda:1792200000.0)
    candidate={'chainId':1,'address':ADDRESS}
    first=await reader.advance(candidate,None,budget=Budget(http_limit=2,rpc_limit=2))
    first.progress['responses']=[]
    second=await reader.advance(candidate,first.progress,budget=Budget(http_limit=2,rpc_limit=2))
    assert isinstance(second.progress['responses'],dict)
    assert second.progress['completed_operations']==2


def test_retained_compressed_observation_has_a_bounded_inflate():
    import base64
    import zlib
    from maxpane_dashboard.data.surf_nft_chain import _Replay
    args=['https://eth.blockscout.com/api/v2/tokens/'+ADDRESS]
    key=json.dumps(['json',args],sort_keys=True,separators=(',',':'))
    compressed=base64.b64encode(zlib.compress(json.dumps('x'*(2*1024*1024+1)).encode())).decode()
    replay=_Replay({'responses':{key:{'compressed':compressed}}})
    with pytest.raises(RuntimeError,match='Invalid retained NFT observation'):
        replay.read('json',args)

@pytest.mark.asyncio
async def test_identity_checkpoint_paints_before_optional_reads_with_unknown_terms(monkeypatch):
    from copy import deepcopy
    from maxpane_dashboard.data.surf_nft_client import Budget
    from maxpane_dashboard.data.surf_nft_rules.rules import RULES, apply_rules
    from maxpane_dashboard.data.surf_nft_rules.utility import DEPLOYED, enrich_utility
    from maxpane_dashboard.data.surf_nft_chain import keccak256
    # Known union code has no dynamic mint gate; proof-only must still not claim open.
    rule=deepcopy(next(r for r in RULES.values() if r['adapter']=='union'))
    rule.update(contract=ADDRESS,codeHash='0x'+keccak256(bytes.fromhex('6000')))
    monkeypatch.setitem(RULES,'1:'+ADDRESS,rule)
    utility=deepcopy(next(r for r in DEPLOYED if r['contract']==rule['dependencies']['UnionCard']['address']))
    utility.update(contract=ADDRESS,codeHash=rule['codeHash'])
    monkeypatch.setattr('maxpane_dashboard.data.surf_nft_rules.utility.DEPLOYED',[utility])
    client=AsyncReads()
    reader=SurfNftInspector(client,clock=lambda:1792200000.0)
    result=await reader.advance({'chainId':1,'address':ADDRESS,'artifact':{'txHash':TX}},None,
                                budget=Budget(http_limit=10,rpc_limit=10))
    assert result.complete is False
    assert result.evidence is not None
    assert result.evidence['standard']=='ERC-721'
    assert result.evidence['deploymentConfirmed'] is True
    assert result.evidence['reads']=={}
    assert not any(method=='source' for method,_ in client.sent)
    assert apply_rules({},result.evidence,'2026-10-17T00:00:00Z')['mint']['state']=='unknown'
    utility=enrich_utility({'chainId':1,'contractAddress':ADDRESS},result.evidence)
    assert all(item['status']=='unknown' for item in utility['utility'])


@pytest.mark.asyncio
async def test_early_child_checkpoint_requires_matching_factory_proof():
    from maxpane_dashboard.data.surf_nft_client import Budget
    reader=SurfNftInspector(AsyncReads(),clock=lambda:1792200000.0)
    candidate={'chainId':1,'address':ADDRESS,'artifact':{'txHash':TX},
               'factoryAddress':'0x'+'ff'*20,'factoryProof':{'kind':'loom','registryIndex':0}}
    result=await reader.advance(candidate,None,budget=Budget(http_limit=10,rpc_limit=10))
    assert result.complete is False
    assert result.evidence is None or result.evidence['deploymentConfirmed'] is False
