"""Two manual samples of SurfClient.fetch_market's four URLs; no app/cache writes.

Measures raw HTTP gather, excluding production pacing, retry and surrounding RPC/log work.
"""
import asyncio
import datetime as dt
import json
import time
from pathlib import Path
import httpx

ROOT=Path(__file__).parent
URLS={
 'dex_imd':'https://api.dexscreener.com/latest/dex/tokens/0xD34a99Bc0f67aE1bbd63C660e6d0b0dd03E263B7',
 'gecko_imd':'https://api.geckoterminal.com/api/v2/networks/eth/tokens/0xd34a99bc0f67ae1bbd63c660e6d0b0dd03e263b7?include=top_pools',
 'dex_fp':'https://api.dexscreener.com/latest/dex/tokens/0xFF0C532FDB8Cd566Ae169C1CB157ff2Bdc83E105',
 'coingecko_eth':'https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd',
}

async def main():
 out={'note':__doc__,'samples':[]}
 async with httpx.AsyncClient(timeout=15,trust_env=False,follow_redirects=False,headers={'Accept':'application/json'}) as client:
  async def get(name,url):
   start=time.perf_counter()
   try:
    r=await client.get(url)
    value=r.json()
    return {'name':name,'url':url,'ms':round((time.perf_counter()-start)*1000,2),
            'status':r.status_code,'bytes':len(r.content),
            'top_level_keys':list(value)[:6] if isinstance(value,dict) else None,
            'eth_usd':value.get('ethereum',{}).get('usd') if isinstance(value,dict) else None}
   except Exception as e:
    return {'name':name,'ms':round((time.perf_counter()-start)*1000,2),'error':type(e).__name__}
  for mode in ('cold','warm'):
   if mode=='warm':await asyncio.sleep(6.2)
   start=time.perf_counter();utc=dt.datetime.now(dt.timezone.utc).isoformat()
   rows=await asyncio.gather(*(get(k,u) for k,u in URLS.items()))
   sample={'connection':mode,'utc':utc,'total_ms':round((time.perf_counter()-start)*1000,2),'calls':rows}
   out['samples'].append(sample);print(json.dumps(sample),flush=True)
 (ROOT/'market_gather_results.json').write_text(json.dumps(out,indent=2))

asyncio.run(main())
