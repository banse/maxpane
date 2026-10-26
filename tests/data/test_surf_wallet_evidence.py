"""Receipt attribution and application-specific utility evidence, offline."""
from copy import deepcopy
import json
from pathlib import Path

import pytest
from maxpane_dashboard.data.surf_wallet_evidence import SurfWalletEvidence, RULES, ordered_refresh

PROOF = json.loads((Path(__file__).parents[1]/'fixtures/surf/wallet/chain_eth.json').read_text())
WALLET = '0x887b86b6b6957f7bbea88b8cefd392f39236a88c'
ASSET = '0xd34a99bc0f67ae1bbd63c660e6d0b0dd03e263b7'
PAYTO = '0x4e0fa57bde726079356537e2f34d671e9f41adbc'

class RPC:
    def __init__(self):
        self.responses = {json.dumps(c): deepcopy(r) for c,r in zip(PROOF['calls'],PROOF['results'])}
        self.receipt = deepcopy(PROOF['results'][3])
        self.head = int(PROOF['results'][1],16)
        self.chain = '0x1'; self.bad_hash = False; self.decimals = 18
        self.logs = []
    async def fetch_launch_pool_state(self,calls):
        out=[]
        for method,args in calls:
            if method=='eth_chainId': result=self.chain
            elif method=='eth_getBlockByNumber':
                number=self.head if args[0]=='latest' else int(args[0],16)
                receipts=[v for v in self.responses.values() if isinstance(v,dict) and 'transactionHash' in v]
                rec=next((r for r in receipts if int(r['blockNumber'],16)==number),None)
                result={'number':hex(number),'timestamp':hex(2000000000-(self.head-number)*12),
                        'hash':'0xbad' if self.bad_hash else (rec or {}).get('blockHash','0x'+'a'*64)}
            elif method=='eth_call':
                if args[0]['data']=='0x313ce567': result=None if self.decimals is None else '0x'+f'{self.decimals:064x}'
                else: result=None
            elif method=='eth_getTransactionReceipt' and args[0]==self.receipt['transactionHash']: result=deepcopy(self.receipt)
            else: result=deepcopy(self.responses.get(json.dumps([method,args])))
            out.append(result)
        return out
    async def _get_logs_window(self,*args,**kwargs): return self.logs

class Swarm:
    async def _get(self,path):
        assert path=='/requests/capabilities'
        return {'actions':[{'action':'job.open','payment':{'network':'eip155:1','asset':ASSET,'payTo':PAYTO}}]}

def order(rpc):
    return {'id':'one','payer':WALLET,'action':'job.open','tx_hash':rpc.receipt['transactionHash'],'payments':None}

async def test_payment_uses_exact_receipt_transfer_and_live_decimals():
    rpc=RPC(); adapter=SurfWalletEvidence(clients={1:rpc},swarm=Swarm())
    orders,_,_=await adapter.enrich([order(rpc)],[],now=2000000000)
    p=orders[0]['payments'][0]
    assert p['amount']=='0.5' and p['decimals']==18 and p['asset']==ASSET
    assert p['log_index']==int(rpc.receipt['logs'][0]['logIndex'],16)

@pytest.mark.parametrize('bad',['chain','failed','canonical','payer','decimals','ambiguous'])
async def test_unproven_payment_never_becomes_zero_or_estimate(bad):
    rpc=RPC(); row=order(rpc)
    if bad=='chain': rpc.chain='0x2105'
    if bad=='failed': rpc.receipt['status']='0x0'
    if bad=='canonical': rpc.bad_hash=True
    if bad=='payer': row['payer']='0x'+'1'*40
    if bad=='decimals': rpc.decimals=None
    if bad=='ambiguous': rpc.receipt['logs'].append(deepcopy(rpc.receipt['logs'][0]))
    rows,_,_=await SurfWalletEvidence(clients={1:rpc},swarm=Swarm()).enrich([row],[],now=2000000000)
    assert rows[0]['payments'] is None

async def test_factory_contract_requires_matching_runtime_attestation():
    rpc=RPC(); rule=RULES[0]
    candidate={'id':'contract','kind':'CONTRACT','chain_id':1,'address':rule['address'],
        'deployment':{'tx_hash':PROOF['results'][8]['transactionHash'],'expected_runtime_hash':rule['runtime_hash']}}
    evidence=SurfWalletEvidence(clients={1:rpc},swarm=Swarm())
    _,assets,_=await evidence.enrich([], [candidate],now=2000000000)
    assert len(assets)==1 and assets[0]['deployment']['confirmed'] is True
    assert 'launch artifact' in assets[0]['deployment']['linkage']
    assert assets[0]['usage']['count']==0 and assets[0]['usage']['complete'] is True
    candidate['deployment']['expected_runtime_hash']='0x'+'0'*64
    _,assets,_=await evidence.enrich([], [candidate],now=2000000000)
    assert assets[0]['evidence_invalidated'] is True
    assert assets[0]['usage'] is None and assets[0]['deployment']['confirmed'] is False

def log(kind=2):
    rule=RULES[0]
    return {'address':rule['address'],'topics':[rule['topic'],'0x'+'a'*64,'0x'+'0'*24+WALLET[2:]],
            'data':'0x'+f'{kind:064x}'+f'{1:064x}'+f'{96:064x}'+f'{0:064x}'}

def test_ordered_decoder_counts_refresh_only_not_setup_or_recovery():
    assert ordered_refresh(log(),RULES[0])==WALLET
    assert ordered_refresh(log(1),RULES[0]) is None
    assert ordered_refresh(log(3),RULES[0]) is None
    bad=log(); bad['topics'][0]='0x'+'0'*64
    assert ordered_refresh(bad,RULES[0]) is None
    bad=log(); bad['data']='0x02'
    assert ordered_refresh(bad,RULES[0]) is None

async def test_failed_window_is_unknown_and_duplicate_logs_count_once():
    rpc=RPC(); rpc.head=int(rpc.receipt['blockNumber'],16)+5000
    adapter=SurfWalletEvidence(clients={1:rpc},swarm=Swarm())
    await adapter._head(1)
    rpc.logs=None
    assert await adapter._usage(1,RULES[0],2000000000) is None
    event=log(); event.update(transactionHash=rpc.receipt['transactionHash'],blockNumber=rpc.receipt['blockNumber'],
        blockHash=rpc.receipt['blockHash'],logIndex='0x2')
    rpc.receipt['logs'].append(event); rpc.logs=[event,deepcopy(event)]
    result=await adapter._usage(1,RULES[0],2000000000)
    assert result['count']==1 and result['actors']==1
    rpc.receipt['status']='0x0'
    adapter._receipts.clear()
    assert await adapter._usage(1,RULES[0],2000000000) is None

async def test_malformed_matching_event_invalidates_zero_window():
    rpc=RPC(); event=log(); event['data']='0x02'; rpc.logs=[event]
    adapter=SurfWalletEvidence(clients={1:rpc},swarm=Swarm())
    assert await adapter._usage(1,RULES[0],2000000000) is None

async def test_interrupted_enrichment_advances_payments_and_deployments(monkeypatch):
    adapter=SurfWalletEvidence(clients={},swarm=Swarm())
    attempted=[]
    async def payment(row,targets,now):
        attempted.append(row['id'])
        if row['id']=='2': raise TimeoutError()
        return None
    async def deployment(row,now):
        attempted.append(row['id'])
        return dict(row,chain_id=1,address='0x'+'1'*40,usage=None,
                    deployment={'confirmed':True,'runtime_hash':'0x'+'0'*64})
    monkeypatch.setattr(adapter,'_payment',payment)
    monkeypatch.setattr(adapter,'_deployment',deployment)
    orders=[dict(id=str(i),payer=WALLET) for i in range(5)]
    for _ in range(3):
        await adapter.enrich(orders,[dict(id='contract',kind='CONTRACT')],now=2000000000)
    assert set(attempted)=={'0','1','2','3','4','contract'}

async def test_usage_read_state_distinguishes_failure_from_removed_rule(monkeypatch):
    rpc=RPC(); rule=RULES[0]
    candidate={'id':'contract','kind':'CONTRACT','chain_id':1,'address':rule['address'],
        'deployment':{'tx_hash':PROOF['results'][8]['transactionHash'],'expected_runtime_hash':rule['runtime_hash']}}
    adapter=SurfWalletEvidence(clients={1:rpc},swarm=Swarm())
    rpc.logs=None
    _,assets,_=await adapter.enrich([], [candidate],now=2000000000)
    assert assets[0]['deployment']['confirmed'] is True
    assert assets[0]['usage_state']=='unavailable' and assets[0]['usage'] is None
    monkeypatch.setattr('maxpane_dashboard.data.surf_wallet_evidence.RULES',[])
    _,assets,_=await adapter.enrich([], [candidate],now=2000000000)
    assert assets[0]['usage_state']=='unsupported' and assets[0]['usage'] is None

async def test_onchain_capability_chain_supplies_its_own_payment_asset():
    # Synthetic RH routing over the captured receipt shape; no live RH claim.
    rpc=RPC(); rpc.chain=hex(4663)
    asset='0x5f7bb59365ce557c26dbcaa4ee9d39a4b95b7127'
    rpc.receipt['logs'][0]['address']=asset
    class OnchainSwarm:
        async def _get(self,path):
            assert path=='/requests/capabilities'
            return {'actions':[], 'onchain':{'chains':[{'chainId':4663,'asset':asset,'payTo':PAYTO}]}}
    orders,_,_=await SurfWalletEvidence(clients={4663:rpc},swarm=OnchainSwarm()).enrich([order(rpc)],[],now=2000000000)
    assert orders[0]['payments'][0]['chain_id']==4663
    assert orders[0]['payments'][0]['asset']==asset
