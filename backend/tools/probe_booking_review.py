"""Inspect real booking-review coupon controls. Never enters passenger/payment data."""
import argparse
import asyncio
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from stealth.browser_factory import BrowserFactory
from workers.cleartrip_worker import CleartripWorker
from workers.easemytrip_worker import EaseMyTripWorker
from quotes import valid_flights


async def main():
    parser=argparse.ArgumentParser();parser.add_argument('platform',choices=['cleartrip','easemytrip'])
    parser.add_argument('--route',default='BOM-HYD');parser.add_argument('--date',default='2026-11-15')
    parser.add_argument('--test-coupons',action='store_true')
    args=parser.parse_args();origin,destination=args.route.split('-')
    trip=dict(origin=origin,destination=destination,departure_date=args.date,passenger_count=1,cabin_class='ECONOMY',is_domestic=True,preferred_time='ANY')
    worker=CleartripWorker() if args.platform=='cleartrip' else EaseMyTripWorker()
    factory=BrowserFactory();browser=None
    folder=Path(__file__).resolve().parents[2]/'sessions'/'booking-probe';folder.mkdir(parents=True,exist_ok=True)
    try:
        async with asyncio.timeout(100):
            browser,context,page=await factory.create_cloak_browser(cloak_config={'engine':'playwright'})
            await worker.input_search_criteria(page,trip);await worker.execute_search(page)
            flights=valid_flights(await worker.parse_search_results(page),trip)
            if not flights: raise ValueError('No exact-trip flights')
            chosen=min(flights,key=lambda f:f['base_price'])
            print(json.dumps(dict(stage='listing',trip=trip,chosen=chosen)),flush=True)
            await worker.select_flight(page,chosen)
            # Cleartrip's selected fare family exposes Continue before booking review.
            page=context.pages[-1]
            await page.wait_for_timeout(6000)
            report=dict(url=page.url,body=(await page.inner_text('body'))[:14000],offers=await worker.scrape_onsite_coupons(page),
                total=await worker.read_checkout_total(page),selected_payment=await worker.read_selected_payment(page),
                controls=await page.evaluate('() => [...document.querySelectorAll("input,button,[role=button]")].filter(x=>x.getBoundingClientRect().width).map(x=>({tag:x.tagName,id:x.id,type:x.type,placeholder:x.placeholder,text:(x.innerText || "").slice(0,80)})).slice(0,100)'))
            (folder/(args.platform+'.json')).write_text(json.dumps(report,indent=2),encoding='utf-8')
            (folder/(args.platform+'.html')).write_text(await page.content(),encoding='utf-8')
            if args.test_coupons:
                trials=[]
                for code in ('BOOKNOW','EMTUPI','EMTNCF'):
                    await worker.clear_coupon_field(page)
                    baseline=await worker.read_checkout_total(page)
                    await worker.enter_coupon_code(page,code);await worker.click_apply_coupon(page)
                    await page.wait_for_timeout(1500)
                    trials.append(dict(code=code,baseline=baseline,total=await worker.read_checkout_total(page),
                        acceptance=await worker.check_coupon_applied(page),body=(await page.inner_text('body'))[-7000:]))
                    print(json.dumps({k:v for k,v in trials[-1].items() if k!='body'}),flush=True)
                    (folder/(args.platform+'-'+code+'.html')).write_text(await page.content(),encoding='utf-8')
                await worker.clear_coupon_field(page)
                (folder/(args.platform+'-trials.json')).write_text(json.dumps(trials,indent=2),encoding='utf-8')
            await page.screenshot(path=str(folder/(args.platform+'.png')),full_page=True)
            print(json.dumps({**report,'body':report['body'][:5500],'offers':[dict(code=o['code'],description=o['description']) for o in report['offers']]}),flush=True)
    except Exception as exc:
        print(json.dumps(dict(error=str(exc))),flush=True)
    finally:
        if browser: await browser.close()
        await factory.cleanup()

if __name__=='__main__':asyncio.run(main())
