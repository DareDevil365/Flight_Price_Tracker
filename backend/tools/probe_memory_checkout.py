"""Public live probe: keep DOM/images in RAM, print bounded facts only.

Optional --ledger records coupon facts, never pages. No passenger/card entry.
"""
import argparse
import asyncio
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from coupon_brute_forcer import CouponBruteForcer
from coupon_db import CouponDB
from financial_filter import FinancialFilter
from page_inspection import inspect_page
from provider_homepage import makemytrip_home_search
from quotes import valid_flights
from stealth.browser_factory import BrowserFactory
from workers.easemytrip_worker import EaseMyTripWorker
from workers.makemytrip_worker import MakeMyTripWorker


async def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('provider',choices=['easemytrip','makemytrip'])
    parser.add_argument('route');parser.add_argument('date')
    parser.add_argument('--homepage',action='store_true')
    parser.add_argument('--ledger',action='store_true')
    parser.add_argument('--inspect-only',action='store_true')
    parser.add_argument('--max-tests',type=int,default=4,help='0 tests all eligible collected codes, within a bounded time budget')
    args=parser.parse_args()
    origin,destination=args.route.split('-')
    trip=dict(origin=origin,destination=destination,departure_date=args.date,
        passenger_count=1,cabin_class='ECONOMY',is_domestic=True,preferred_time='ANY',max_stops=0)
    worker=EaseMyTripWorker() if args.provider=='easemytrip' else MakeMyTripWorker()
    factory=BrowserFactory();browser=None;db=None;report={'provider':args.provider,'trip':trip}
    try:
        async with asyncio.timeout(240):
            browser,context,page=await factory.create_cloak_browser(cloak_config={'engine':'playwright'})
            if args.homepage:
                worker._trip=trip
                await makemytrip_home_search(page,trip)
            else:
                await worker.input_search_criteria(page,trip)
            await worker.execute_search(page)
            flights=valid_flights(await worker.parse_search_results(page),trip)
            report.update(flight_count=len(flights),sample=flights[:1])
            if not flights:raise ValueError('No exact matching flight parsed')
            if args.provider=='makemytrip':return
            await worker.select_flight(page,flights[0]);page=context.pages[-1]
            await page.wait_for_timeout(2500)
            report['review_total']=await worker.read_checkout_total(page)
            async with inspect_page(page,screenshots=True) as capture:
                report['inspection']={**capture.summary,'in_memory_images':len(capture.screenshots)}
            report['inspection_cleared']=not capture.summary and not capture.screenshots
            if args.inspect_only:
                report['currency_dom']=await page.evaluate('''() => {
                    const row=document.querySelector('#spnGrndTotal')?.closest('.pr');
                    if (!row) return null;
                    return [...row.querySelectorAll('*')].map(el=>({tag:el.tagName,
                        cls:el.className,width:el.getBoundingClientRect().width,height:el.getBoundingClientRect().height,
                        display:getComputedStyle(el).display,visibility:getComputedStyle(el).visibility,
                        before:getComputedStyle(el,'::before').content}));
                }''')
                return
            offers=await worker.scrape_onsite_coupons(page)
            if args.ledger:
                db=CouponDB();await db.initialize()
                offers=[*offers,*await db.get_live_coupons(args.provider)]
            report['candidate_count']=len(offers)
            result=await CouponBruteForcer(worker,FinancialFilter(),lambda *a:None).brute_force(
                page,offers,{'is_domestic':True,'passenger_count':1},'memory-review-probe',
                db=db,max_tests=args.max_tests or None,budget_seconds=150 if args.max_tests==0 else 90,
                audit_scope={**trip,'flight_number':flights[0].get('flight_number'),
                    'stage':'review','onsite_collection':'collected'})
            report['coupon_trials']=result
            report['final_payment_verified']=False
    except Exception as exc:
        report['error']=type(exc).__name__+': '+str(exc)
    finally:
        if db:await db.close()
        if browser:await browser.close()
        await factory.cleanup()
        print(json.dumps(report,ensure_ascii=True))


if __name__=='__main__':asyncio.run(main())
