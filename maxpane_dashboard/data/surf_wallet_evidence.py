"""Read-only wallet receipts and version-bound non-trading application usage.

All transports are borrowed. Failed reads stay unknown. Historical payment
amounts come from payer transfers, never current capability quote amounts.
"""
import asyncio
from copy import deepcopy
from decimal import Decimal, localcontext
import json
from pathlib import Path
import re

from maxpane_dashboard.data.evm_abi import decode_string
from maxpane_dashboard.data.keccak import keccak256

TRANSFER = '0x' + keccak256(b'Transfer(address,address,uint256)').hex()
RULES = json.loads(Path(__file__).with_name('surf_wallet_usage.json').read_text())


def _hex(value, size=None):
    return isinstance(value, str) and re.fullmatch(r'0x[0-9a-fA-F]+', value) is not None and (size is None or len(value) == 2 + size * 2)


def _number(value):
    return int(value, 16) if _hex(value) else None


def _ordered(log, rule):
    """Decode the complete supported ABI; malformed matching logs are not zero."""
    topics, data = log.get('topics'), log.get('data')
    if (log.get('address', '').lower() != rule['address'] or not isinstance(topics, list)
            or len(topics) != 3 or not all(_hex(t, 32) for t in topics)
            or topics[0].lower() != rule['topic'] or topics[2][2:26] != '0' * 24
            or not _hex(data) or len(data) < 258 or (len(data)-2) % 64):
        return None
    kind = int(data[2:66], 16)
    if kind not in (1, 2, 3):
        return None
    # The third non-indexed slot points to the trailing parentJobId string.
    offset, length = int(data[130:194], 16), int(data[194:258], 16)
    if offset != 96 or len(data) != 258 + ((length + 31)//32)*64:
        return None
    return kind, '0x' + topics[2][-40:].lower()


def ordered_refresh(log, rule):
    decoded = _ordered(log, rule)
    return decoded[1] if decoded is not None and decoded[0] == 2 else None


class SurfWalletEvidence:
    def __init__(self, *, clients, swarm, budget=150):
        self.clients, self.swarm, self.budget = clients, swarm, budget
        self._heads, self._blocks, self._receipts = {}, {}, {}
        self._cursor = {}

    async def _rpc(self, chain, calls):
        client = self.clients.get(chain)
        if client is None:
            return [None] * len(calls)
        try:
            result = await client.fetch_launch_pool_state(calls)
            return result if isinstance(result, list) and len(result) == len(calls) else [None] * len(calls)
        except (RuntimeError, ValueError, TypeError, OSError):
            return [None] * len(calls)

    async def _head(self, chain):
        if chain not in self._heads:
            identity, head = await self._rpc(chain, [('eth_chainId', []), ('eth_getBlockByNumber', ['latest', False])])
            self._heads[chain] = head if (_number(identity) == chain and isinstance(head, dict)
                and _number(head.get('number')) is not None and _number(head.get('timestamp')) is not None
                and _hex(head.get('hash'), 32)) else None
        return self._heads[chain]

    async def _block(self, chain, number):
        key = chain, number
        if key not in self._blocks:
            result, = await self._rpc(chain, [('eth_getBlockByNumber', [hex(number), False])])
            self._blocks[key] = result if (isinstance(result, dict) and _number(result.get('number')) == number
                and _hex(result.get('hash'),32) and _number(result.get('timestamp')) is not None) else None
        return self._blocks[key]

    async def _receipt(self, chain, tx):
        key = chain, tx
        if not _hex(tx,32):
            return None
        if key not in self._receipts:
            head = await self._head(chain)
            receipt, = await self._rpc(chain, [('eth_getTransactionReceipt',[tx])])
            number = _number(receipt.get('blockNumber')) if isinstance(receipt,dict) else None
            valid = (head is not None and number is not None and number <= _number(head['number']) - 2
                and receipt.get('transactionHash','').lower() == tx.lower() and receipt.get('status') == '0x1')
            block = await self._block(chain,number) if valid else None
            self._receipts[key] = receipt if block and block['hash'].lower() == receipt.get('blockHash','').lower() else None
        return self._receipts[key]

    async def _payment(self, order, targets, now):
        matches=[]
        payer, tx = order.get('payer'), order.get('tx_hash')
        if not _hex(payer,20) or not _hex(tx,32):
            return None
        for chain,asset,recipient in targets:
            receipt=await self._receipt(chain,tx)
            if receipt is None:
                continue
            for log in receipt.get('logs') or []:
                topics=log.get('topics') or []
                if (log.get('address','').lower()==asset and len(topics)==3
                        and all(_hex(t,32) for t in topics) and topics[0].lower()==TRANSFER
                        and topics[1].lower()=='0x'+'0'*24+payer[2:].lower()
                        and topics[2].lower()=='0x'+'0'*24+recipient[2:]
                        and _hex(log.get('data'),32) and not log.get('removed')):
                    matches.append((chain,asset,receipt,log))
        if len(matches)!=1:
            return None
        chain,asset,receipt,log=matches[0]
        decimals,symbol=await self._rpc(chain,[('eth_call',[{'to':asset,'data':selector},receipt['blockNumber']])
                                              for selector in ('0x313ce567','0x95d89b41')])
        if not _hex(decimals,32) or not 0<=int(decimals,16)<=255 or _number(log.get('logIndex')) is None:
            return None
        decimals=int(decimals,16)
        with localcontext() as context:
            context.prec=340
            amount=format(Decimal(int(log['data'],16)).scaleb(-decimals),'f').rstrip('0').rstrip('.') if decimals else str(int(log['data'],16))
        return [dict(chain_id=chain,asset=asset,symbol=decode_string(symbol) if isinstance(symbol,str) else None,
            decimals=decimals,amount=amount or '0',tx_hash=tx,log_index=_number(log['logIndex']),observed_at=now)]

    async def _deployment(self, candidate, now):
        chain,address=candidate.get('chain_id'),candidate.get('address')
        deployment=candidate.get('deployment') or {}
        if chain not in self.clients or not _hex(address,20):
            return None
        receipt=await self._receipt(chain,deployment.get('tx_hash'))
        if receipt is None:
            return None
        code,=await self._rpc(chain,[('eth_getCode',[address,'latest'])])
        if not _hex(code) or len(code)%2 or len(code)<=2:
            return None
        runtime='0x'+keccak256(bytes.fromhex(code[2:])).hex()
        expected=deployment.get('expected_runtime_hash')
        if expected:
            expected='0x'+expected.removeprefix('0x').lower()
            if runtime!=expected:
                candidate.update(usage=None,usage_state='invalidated',evidence_invalidated=True,evidence_state='invalidated',evidence_observed_at=now)
                candidate['deployment']=dict(deployment,confirmed=False,current_runtime_hash=runtime)
                return candidate
        direct=receipt.get('contractAddress')
        if direct and direct.lower()!=address.lower() or not direct and not expected:
            return None
        candidate['deployment']=dict(deployment,confirmed=True,observed_at=now,runtime_hash=runtime,
            block_number=_number(receipt['blockNumber']),
            linkage='direct creation receipt' if direct else 'factory receipt + runtime match; address linkage relies on launch artifact')
        candidate.update(usage=None,usage_state='unsupported',evidence_state='ok',evidence_observed_at=now)
        return candidate

    async def _usage(self, chain, rule, now):
        head=await self._head(chain)
        client=self.clients.get(chain)
        if head is None or not callable(getattr(client,'_get_logs_window',None)):
            return None
        # Pin a two-block-confirmed head. Binary search actual timestamps, not a
        # guessed block rate. A lagging chain exposes its actual window endpoint.
        end=_number(head['number'])-2
        upper=await self._block(chain,end)
        if upper is None or _number(upper['timestamp'])<now-86400:
            return None
        cutoff=now-86400
        lo,hi=0,end
        while lo<hi:
            mid=(lo+hi)//2
            block=await self._block(chain,mid)
            if block is None:
                return None
            if _number(block['timestamp'])<cutoff:
                lo=mid+1
            else:
                hi=mid
        logs=await client._get_logs_window({'address':rule['address'],'topics':[rule['topic']]},lo,end,
            group='wallet_usage_'+rule['address'])
        if logs is None or len(logs)>1000:
            return None
        seen,actors,latest=set(),set(),None
        for log in logs:
            decoded=_ordered(log,rule)
            if decoded is None:
                return None
            if decoded[0] != 2:
                continue
            actor=decoded[1]
            number=_number(log.get('blockNumber')); index=_number(log.get('logIndex'))
            if number is None or index is None or not lo<=number<=end or log.get('removed'):
                return None
            tx=log.get('transactionHash'); receipt=await self._receipt(chain,tx)
            if receipt is None or receipt.get('blockHash')!=log.get('blockHash'):
                return None
            same=lambda entry: all(entry.get(k)==log.get(k) for k in ('address','topics','data','logIndex','transactionHash','blockHash','blockNumber'))
            if not any(same(entry) for entry in receipt.get('logs') or []):
                return None
            seen.add((tx,index)); actors.add(actor); latest=tx
        # Re-read the pinned endpoint after the history sweep to reject a reorg.
        final,=await self._rpc(chain,[('eth_getBlockByNumber',[hex(end),False])])
        if not isinstance(final,dict) or final.get('hash')!=upper['hash']:
            return None
        return dict(count=len(seen),actors=len(actors),unit=rule['unit'],complete=True,first_seen=False,
            rule=rule['id'],evidence=rule['source'],latest=latest,observed_at=now,from_block=lo,to_block=end,
            through_timestamp=_number(upper['timestamp']),tracking_since=None)

    async def enrich(self, orders, candidates, *, now):
        orders,candidates=deepcopy(orders),deepcopy(candidates)
        self._heads,self._blocks,self._receipts={},{},{}
        artifacts=[c for c in candidates if c.get('kind')=='SITE']
        coverage=['Payments: receipt-proven outflows; refund history unavailable',
                  'Usage: reviewed application events only; sites do not prove frontend traffic']
        try:
            async with asyncio.timeout(self.budget):
                try:
                    async with asyncio.timeout(10):
                        caps=await self.swarm._get('/requests/capabilities')
                except (TimeoutError,RuntimeError,ValueError,TypeError,OSError):
                    caps=None
                targets=set()
                for entry in (caps or {}).get('actions',[]):
                    p=entry.get('payment') or {}; network=p.get('network','')
                    if re.fullmatch(r'eip155:\d+',network) and _hex(p.get('asset'),20) and _hex(p.get('payTo'),20):
                        targets.add((int(network.split(':')[1]),p['asset'].lower(),p['payTo'].lower()))
                for p in ((caps or {}).get('onchain') or {}).get('chains',[]):
                    chain=p.get('chainId')
                    if type(chain) is int and chain in self.clients and _hex(p.get('asset'),20) and _hex(p.get('payTo'),20):
                        targets.add((chain,p['asset'].lower(),p['payTo'].lower()))
                work=[('payment',r) for r in orders]+[('deployment',c) for c in candidates if c.get('kind')!='SITE']
                wallet=next((r.get('payer') for r in orders if r.get('payer')), '')
                identities=[(kind,row['id']) for kind,row in work]
                cursor=self._cursor.get(wallet)
                offset=identities.index(cursor) if cursor in identities else 0
                work=work[offset:]+work[:offset]
                for index,(kind,row) in enumerate(work):
                    next_kind,next_row=work[(index+1)%len(work)]
                    # Advance before a potentially cancelled read so a slow item
                    # cannot monopolize subsequent cycles or starve deployments.
                    self._cursor[wallet]=(next_kind,next_row['id'])
                    if kind=='payment':
                        row['payments']=await self._payment(row,sorted(targets),now)
                        row['evidence_state']='ok' if row['payments'] else 'unavailable'
                        if row['payments']:
                            row['evidence_observed_at']=now
                    else:
                        confirmed=await self._deployment(row,now)
                        if confirmed:
                            artifacts.append(confirmed)
                            if confirmed.get('evidence_invalidated'):
                                continue
                            rule=next((r for r in RULES if r['chain_id']==confirmed['chain_id']
                                and r['address']==confirmed['address'].lower()
                                and r['runtime_hash']==confirmed['deployment']['runtime_hash']),None)
                            if rule:
                                confirmed['usage_state']='unavailable'
                                confirmed['usage']=await self._usage(confirmed['chain_id'],rule,now)
                                if confirmed['usage'] is not None:
                                    confirmed['usage_state']='ok'
        except (TimeoutError,RuntimeError,ValueError,TypeError,OSError) as exc:
            coverage.append('Onchain evidence partial: '+type(exc).__name__)
        pending=len(candidates)-len(artifacts)
        if pending:
            coverage.append(f'{pending} claimed deployments awaiting onchain confirmation')
        return orders,artifacts,coverage
