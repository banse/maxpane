"""Manual bounded public-GET research probe, never imported by tests/app.

Run from repository: .venv/bin/python 'docs/research_notes/Keyless Marktdaten für Surfboard/market_probe.py'
One fresh client and two same-client repeats per endpoint; no retries, no keys.
"""
import datetime as dt
import json
import platform
import statistics
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx

ROOT = Path(__file__).parent
IMD = '0xd34a99bc0f67ae1bbd63c660e6d0b0dd03e263b7'
POOL = '0xb07d640fd9e2eb9dc81b953c8e4fd006bdfeaf276010fb5418eb763ca15abfb3'
ZTO = '0xd782bdea4ef02a0bd391eb9089470c8080f0a68e'
FREE = '0x4543e6b511a9a7a75b56607e27997c987ea05878'
TARGETS = [
 ('ds_legacy_imd', f'https://api.dexscreener.com/latest/dex/tokens/{IMD}'),
 ('ds_batch_imd', f'https://api.dexscreener.com/tokens/v1/ethereum/{IMD}'),
 ('ds_pair_imd', f'https://api.dexscreener.com/latest/dex/pairs/ethereum/{POOL}'),
 ('gt_pair_imd', f'https://api.geckoterminal.com/api/v2/networks/eth/pools/{POOL}'),
 ('gt_token_pools_imd', f'https://api.geckoterminal.com/api/v2/networks/eth/tokens/{IMD}/pools'),
 ('llama_imd_eth', f'https://coins.llama.fi/prices/current/ethereum:{IMD},coingecko:ethereum'),
 ('paprika_imd', f'https://api.dexpaprika.com/networks/ethereum/tokens/{IMD}'),
 ('ds_launches', f'https://api.dexscreener.com/tokens/v1/ethereum/{ZTO},{FREE}'),
 ('gt_launch_zto', f'https://api.geckoterminal.com/api/v2/networks/eth/tokens/{ZTO}/pools'),
 ('paprika_launch_zto', f'https://api.dexpaprika.com/networks/ethereum/tokens/{ZTO}'),
 ('llama_launches', f'https://coins.llama.fi/prices/current/ethereum:{ZTO},ethereum:{FREE}'),
]

def coverage(name, body):
    if name.startswith('ds_'):
        pairs = body if isinstance(body, list) else (body.get('pairs') or [])
        return [{'pool': p.get('pairAddress'), 'token': p.get('baseToken'),
                 **{k:p.get(k) for k in ('priceUsd','marketCap','fdv','volume','priceChange','liquidity','txns')}}
                for p in pairs if name == 'ds_launches' or p.get('pairAddress','').lower() == POOL]
    if name.startswith('gt_'):
        data = body.get('data', [])
        return [{k:p.get(k) for k in ('id','attributes','relationships')}
                for p in (data if isinstance(data,list) else [data])]
    return body

out = {'started_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
       'environment':{'platform':platform.platform(),'python':platform.python_version(),
                      'httpx':httpx.__version__,'trust_env':False,'http2':False,
                      'timeout_seconds':12,'redirects':False,'retries':0},
       'note':'Cold means fresh client/TCP/TLS; OS DNS and CDN caches uncontrolled. Warm means reuse-capable same client, not proof server kept connection. Tiny fixed-order probe; no UI timing or chain freshness proof.',
       'runs':[]}
last = {}
for name,url in TARGETS:
    host = urlsplit(url).hostname
    with httpx.Client(timeout=12, trust_env=False, follow_redirects=False,
                      headers={'Accept':'application/json','User-Agent':'MaxPane-research-readonly'}) as client:
        for n in range(3):
            interval = 6.2 if host in ('api.geckoterminal.com','api.dexpaprika.com') else .25
            time.sleep(max(0,interval-(time.monotonic()-last.get(host,0))))
            last[host] = time.monotonic()
            row={'endpoint':name,'url':url,'connection':'cold' if n==0 else 'warm',
                 'utc':dt.datetime.now(dt.timezone.utc).isoformat()}
            start=time.perf_counter()
            try:
                r=client.get(url)
                row.update(status=r.status_code,ms=round((time.perf_counter()-start)*1000,2),bytes=len(r.content),
                           headers={k:r.headers.get(k) for k in ('date','age','cache-control','last-modified','retry-after','x-ratelimit-remaining') if k in r.headers})
                try: row['coverage']=coverage(name,r.json()) if r.is_success else r.json()
                except (ValueError,TypeError,AttributeError): row['body_excerpt']=r.text[:200]
            except httpx.HTTPError as e:
                row.update(ms=round((time.perf_counter()-start)*1000,2),error=type(e).__name__,detail=str(e))
            out['runs'].append(row)
            (ROOT/'market_probe_results.json').write_text(json.dumps(out,indent=2))
            print(name,row['connection'],row.get('status',row.get('error')),row['ms'],flush=True)
            if row.get('status')==429: break
out['ended_utc']=dt.datetime.now(dt.timezone.utc).isoformat()
(ROOT/'market_probe_results.json').write_text(json.dumps(out,indent=2))
