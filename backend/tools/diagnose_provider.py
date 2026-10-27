"""Bounded public-page diagnostics. No traveller data, login, payment or purchase."""
import argparse
import asyncio
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.async_api import async_playwright
from workers.makemytrip_worker import MakeMyTripWorker
from workers.cleartrip_worker import CleartripWorker
from quotes import valid_flights


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('platform', choices=['makemytrip', 'cleartrip'])
    parser.add_argument('--route', required=True)
    parser.add_argument('--date', required=True)
    parser.add_argument('--warmup', action='store_true')
    parser.add_argument('--select', action='store_true')
    parser.add_argument('--http1', action='store_true')
    parser.add_argument('--channel',choices=['chrome','msedge'])
    args = parser.parse_args()
    origin, destination = args.route.split('-')
    trip = dict(origin=origin, destination=destination, departure_date=args.date,
                passenger_count=1, cabin_class='ECONOMY', is_domestic=True, preferred_time='ANY')
    worker = MakeMyTripWorker() if args.platform == 'makemytrip' else CleartripWorker()
    network, errors, tasks = [], [], set()
    def safe_url(url):
        u = urlsplit(url)
        return u.netloc + u.path
    async def response_info(response):
        request = response.request
        if request.resource_type not in ('document','xhr','fetch'):
            return
        row = dict(url=safe_url(response.url), status=response.status, kind=request.resource_type)
        # Only top-level public error fields/keys. Never save request headers,
        # cookies, response bodies containing identifiers or traveller details.
        try:
            if 'json' in response.headers.get('content-type',''):
                data = await response.json()
                if isinstance(data, dict):
                    row['keys'] = list(data)[:25]
                    row['error'] = {k:str(data[k])[:300] for k in ('errorCode','errorMessage','statusCode','message')
                                    if k in data and isinstance(data[k], (str,int))}
        except Exception:
            pass
        if len(network) < 250:
            network.append(row)
    def on_response(response):
        task = asyncio.create_task(response_info(response))
        tasks.add(task)
        task.add_done_callback(tasks.discard)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False,channel=args.channel,args=['--disable-http2'] if args.http1 else [])
        context = await browser.new_context(locale='en-IN', timezone_id='Asia/Kolkata')
        page = await context.new_page()
        context.on('response', on_response)
        context.on('requestfailed', lambda r: errors.append(dict(url=safe_url(r.url), failure=r.failure)))
        page.on('pageerror', lambda e: errors.append(dict(script_error=str(e)[:500])))
        stage_error = None
        try:
            async with asyncio.timeout(100):
                if args.warmup:
                    await page.goto(worker.base_url, wait_until='domcontentloaded', timeout=25000)
                    await page.wait_for_timeout(2500)
                    await page.keyboard.press('Escape')
                await worker.input_search_criteria(page, trip)
                await worker.execute_search(page)
                flights = valid_flights(await worker.parse_search_results(page), trip)
                if args.select and flights:
                    await worker.select_flight(page, flights[0])
                    page = context.pages[-1]
                    await page.wait_for_timeout(4000)
        except Exception as exc:
            stage_error = str(exc)
        if tasks:
            _,pending=await asyncio.wait(tasks,timeout=3)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
        report = dict(trip=trip, engine=args.channel or 'unmodified Chromium', warmup=args.warmup,
                      http1=args.http1,error=stage_error, url=page.url, text=(await page.inner_text('body'))[:9000],
                      network=network, failures=errors)
        folder = Path(__file__).resolve().parents[2]/'sessions'/'provider-diagnostics'
        folder.mkdir(parents=True, exist_ok=True)
        label = args.platform + ('-warm' if args.warmup else '-direct') + ('-http1' if args.http1 else '') + ('-'+args.channel if args.channel else '')
        (folder/(label+'.json')).write_text(json.dumps(report,indent=2),encoding='utf-8')
        await page.screenshot(path=str(folder/(label+'.png')))
        print(json.dumps(dict(platform=args.platform, warmup=args.warmup, error=stage_error,
                              url=page.url, text=report['text'][-1200:],
                              problems=[r for r in network if r['status']>=400],
                              failures=[r for r in errors if r.get('failure')!='net::ERR_ABORTED'][:15])),flush=True)
        await browser.close()


if __name__ == '__main__':
    asyncio.run(main())
