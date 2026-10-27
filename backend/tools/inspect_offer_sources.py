"""Inspect public coupon-source markup without treating advertisements as savings."""
import asyncio
import json
from pathlib import Path
import aiohttp
from bs4 import BeautifulSoup


async def main():
    urls=['https://www.grabon.in/cleartrip-coupons/',
          'https://www.grabon.in/easemytrip-coupons/',
          'https://www.coupondunia.in/cleartrip',
          'https://www.couponzeta.in/cleartrip-coupons',
          'https://www.cleartrip.com/offers/india/flights',
          'https://www.easemytrip.com/offers/flight.html']
    slot=asyncio.Semaphore(3)
    folder=Path(__file__).resolve().parents[2]/'sessions'/'coupon-sources';folder.mkdir(parents=True,exist_ok=True)
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
        async def check(index,url):
            async with slot:
                try:
                    async with session.get(url) as response:
                        status=response.status;html=await response.text()
                    soup=BeautifulSoup(html,'html.parser')
                    nodes=soup.select('[data-code], [data-coupon], [data-coupon-code], [class*="coupon-code"], [class*="couponCode"], [class*="coupon_code"], [class*="promo-code"]')
                    report=dict(url=url,status=status,title=soup.title.get_text() if soup.title else None,explicit_nodes=[str(n)[:700] for n in nodes[:8]],count=len(nodes))
                    (folder/(str(index)+'.html')).write_text(html,encoding='utf-8')
                    print(json.dumps(report),flush=True);return report
                except Exception as exc:
                    report=dict(url=url,error=str(exc));print(json.dumps(report),flush=True);return report
        reports=await asyncio.gather(*(check(i,url) for i,url in enumerate(urls)))
    (folder/'report.json').write_text(json.dumps(reports,indent=2),encoding='utf-8')

if __name__=='__main__':asyncio.run(main())
