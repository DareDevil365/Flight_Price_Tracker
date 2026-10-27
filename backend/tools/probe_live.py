"""Read-only smoke test of public search pages; never books, supplies passenger data, or saves page dumps."""
import asyncio
import json
import sys
import os
from pathlib import Path
from datetime import date, timedelta
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stealth.browser_factory import BrowserFactory
from workers.makemytrip_worker import MakeMyTripWorker
from workers.easemytrip_worker import EaseMyTripWorker
from workers.cleartrip_worker import CleartripWorker
from workers.google_flights_worker import GoogleFlightsWorker
from quotes import valid_flights

async def main():
    factory = BrowserFactory()
    trip = dict(origin=os.getenv('PROBE_ORIGIN','DEL'),destination=os.getenv('PROBE_DEST','BOM'),departure_date=os.getenv('PROBE_DATE',(date.today()+timedelta(days=30)).isoformat()),
                passenger_count=int(os.getenv('PROBE_ADULTS','1')),cabin_class=os.getenv('PROBE_CABIN','ECONOMY'),is_domestic=True,preferred_time='ANY')
    for cls in [GoogleFlightsWorker, MakeMyTripWorker, EaseMyTripWorker, CleartripWorker]:
        worker = cls()
        if len(sys.argv)>1 and worker.platform_id not in sys.argv[1:]:
            continue
        browser = None
        try:
            async with asyncio.timeout(65):
                browser,context,page = await factory.create_cloak_browser(cloak_config={'engine':'playwright'})
                await worker.input_search_criteria(page,trip)
                await worker.execute_search(page)
                await page.wait_for_timeout(4000)
                blocked = await worker.detect_captcha(page)
                raw = [] if blocked else await worker._parse_via_dom(page)
                flights = valid_flights(raw,trip)
                print(json.dumps(dict(platform=worker.platform_id,url=page.url,title=await page.title(),
                    blocked=blocked,count=len(flights),raw_count=len(raw),sample=flights[:2],rejected_sample=raw[:2] if not flights else [])), flush=True)
                offers=await worker.scrape_onsite_coupons(page) if worker.platform_id!='google_flights' else []
                print(json.dumps(dict(platform=worker.platform_id,offers=offers)),flush=True)
        except Exception as exc:
            print(json.dumps(dict(platform=worker.platform_id,error=str(exc))),flush=True)
        finally:
            if browser:
                await browser.close()
    await factory.cleanup()

if __name__=='__main__':
    asyncio.run(main())
