"""Bounded domestic public navigation/review audit. No DB, PII or purchase."""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from stealth.browser_factory import BrowserFactory
from workers.easemytrip_worker import EaseMyTripWorker
from workers.cleartrip_worker import CleartripWorker
from workers.makemytrip_worker import MakeMyTripWorker
from financial_filter import FinancialFilter
from quotes import valid_flights,utc_now


async def main():
    cli=argparse.ArgumentParser()
    cli.add_argument('platform',choices=['easemytrip','cleartrip','makemytrip'])
    cli.add_argument('--route',required=True);cli.add_argument('--date',required=True)
    cli.add_argument('--select',action='store_true');cli.add_argument('--coupons',action='store_true')
    args=cli.parse_args();origin,destination=args.route.split('-')
    trip=dict(origin=origin,destination=destination,departure_date=args.date,passenger_count=1,
        cabin_class='ECONOMY',is_domestic=True,preferred_time='ANY',max_stops=0)
    worker={'easemytrip':EaseMyTripWorker,'cleartrip':CleartripWorker,'makemytrip':MakeMyTripWorker}[args.platform]()
    factory=BrowserFactory();browser=None;began=time.monotonic()
    report=dict(trip=trip,platform=args.platform,observed_at=utc_now(),http_failures=[],coupon_trials=[])
    def observe(response):
        address=urlsplit(response.url)
        if response.status>=400 and response.request.resource_type in ('document','fetch','xhr'):
            report['http_failures'].append(dict(host=address.hostname,path=address.path,status=response.status))
    async def price_settles(expected=None):
        previous=None;stable=0
        for _ in range(20):
            total=await worker.read_checkout_total(page)
            value=total.get('total') if total else None
            if value is None:raise ValueError('No supported visible INR review total')
            stable=stable+1 if value==previous else 0;previous=value
            if stable>=3 and (expected is None or value==expected):return total
            await asyncio.sleep(.25)
        raise ValueError('Review total did not settle')
    try:
        async with asyncio.timeout(90):
            browser,context,page=await factory.create_cloak_browser(cloak_config={'engine':'playwright'})
            context.on('response',observe)
            await worker.input_search_criteria(page,trip)
            await worker.execute_search(page)
            raw=await worker.parse_search_results(page)
            flights=valid_flights(raw,trip)
            report.update(raw_count=len(raw),raw_sample=raw[:3])
            report['dom_audit']=await page.evaluate('''() => [...document.querySelectorAll('.main-bo-lis,.flight-list-item')].slice(0,4).map(card=>({
                textLength:card.innerText.length,textStart:card.innerText.slice(0,1300),rect: {width:card.getBoundingClientRect().width,height:card.getBoundingClientRect().height},
                opacity:getComputedStyle(card).opacity,visibility:getComputedStyle(card).visibility,
                prices:[...card.querySelectorAll('[id^="spnPrice"],.price,.actual-price,.fliFare,.flight-price')].map(el=>({id:el.id,raw:el.innerText,
                    width:el.getBoundingClientRect().width,height:el.getBoundingClientRect().height,opacity:getComputedStyle(el).opacity,visibility:getComputedStyle(el).visibility,
                    parentText:el.parentElement.innerText,icons:[...el.parentElement.querySelectorAll('i.CurrncyCD_Rs')].map(icon=>({
                        width:icon.getBoundingClientRect().width,height:icon.getBoundingClientRect().height,opacity:getComputedStyle(icon).opacity,visibility:getComputedStyle(icon).visibility}))}))}))''')
            report.update(search_seconds=round(time.monotonic()-began,2),flight_count=len(flights),sample=flights[:2])
            if args.select:
                if not flights:raise ValueError('No matching nonstop flight to select')
                await worker.select_flight(page,flights[0]);page=context.pages[-1]
                await page.wait_for_timeout(3500)
                report.update(selected=flights[0],review_total=await worker.read_checkout_total(page),
                    payment_stage=await worker.is_at_checkout(page),selected_payment=await worker.read_selected_payment(page))
                offers=await worker.scrape_onsite_coupons(page);report['published_offers']=offers
                if args.coupons and report['review_total'] and not report['payment_stage']:
                    original=await worker.get_applied_coupon_code(page)
                    original_applied=(await worker.check_coupon_applied(page)).get('success')
                    if original_applied and not original:raise ValueError('Unidentified original coupon; no trials performed')
                    baseline=None
                    try:
                        await worker.clear_coupon_field(page)
                        baseline=(await price_settles())['total'];report['coupon_free_review_total']=baseline
                        if (await worker.check_coupon_applied(page)).get('success'):raise ValueError('Removal unconfirmed')
                        candidates=[offer for offer in offers if FinancialFilter().assess(offer,
                            {'booking_total':baseline,'is_domestic':True,'passenger_count':1}).status=='eligible']
                        for offer in candidates[:2]:
                            await worker.clear_coupon_field(page);await price_settles(baseline)
                            await worker.enter_coupon_code(page,offer['code']);await worker.click_apply_coupon(page)
                            result=await price_settles()
                            report['coupon_trials'].append(dict(code=offer['code'],provider_feedback=await worker.check_coupon_applied(page),
                                displayed_review_total=result['total'],baseline=baseline,verification='review_only'))
                    finally:
                        await worker.clear_coupon_field(page);await price_settles(baseline)
                        if original_applied:
                            await worker.enter_coupon_code(page,original);await worker.click_apply_coupon(page)
                            await price_settles(report['review_total']['total'])
                        report['restored_review_total']=await worker.read_checkout_total(page)

    except Exception as exc:
        report['error']=str(exc)

    finally:
        report['elapsed_seconds']=round(time.monotonic()-began,2)
        folder=Path(__file__).resolve().parents[2]/'sessions'/'navigation-audit-20261009';folder.mkdir(parents=True,exist_ok=True)
        label=f'{args.platform}-{args.route}-{args.date}'
        (folder/(label+'.json')).write_text(json.dumps(report,indent=2),encoding='utf-8')
        if browser:
            await browser.close()
        await factory.cleanup()
        print(json.dumps({key:report.get(key) for key in ('platform','trip','flight_count','sample','search_seconds','review_total',
            'payment_stage','coupon_free_review_total','coupon_trials','restored_review_total','elapsed_seconds','error')},ensure_ascii=True))


if __name__=='__main__':asyncio.run(main())
