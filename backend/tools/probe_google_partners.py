"""Read-only Google booking-partner diagnostics; no invented URL or passenger data."""
import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from stealth.browser_factory import BrowserFactory
from workers.google_flights_worker import GoogleFlightsWorker
from quotes import valid_flights


async def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--route',required=True)
    parser.add_argument('--date',required=True)
    parser.add_argument('--index',type=int,default=0)
    parser.add_argument('--max-stops',type=int,choices=[0,1],default=0)
    parser.add_argument('--continue-provider',choices=['MakeMyTrip','Cleartrip','Air India','IndiGo','FlightsMojo','wego','Travomint'])
    args=parser.parse_args()
    origin,destination=args.route.split('-')
    trip=dict(origin=origin,destination=destination,departure_date=args.date,passenger_count=1,
        cabin_class='ECONOMY',preferred_time='ANY',is_domestic=True,max_stops=args.max_stops)
    factory=BrowserFactory();browser=None;report={'trip':trip,'stages':[],'network':[]}
    def observe(response):
        address=urlsplit(response.url)
        if response.request.resource_type in ('document','xhr','fetch') and response.status>=400:
            report['network'].append({'host':address.hostname,'path':address.path,'status':response.status})
    async def snapshot(page,label):
        data=dict(label=label,url=page.url,text=(await page.inner_text('body'))[:20000],
            controls=await page.evaluate('''() => [...document.querySelectorAll('button,a,[role="button"]')]
            .filter(el=>el.getBoundingClientRect().width).map(el=>({tag:el.tagName,text:el.innerText,
              label:el.getAttribute('aria-label'),href:el.getAttribute('href')})).slice(0,100)'''))
        report['stages'].append(data)
        print(json.dumps(data,ensure_ascii=True),flush=True)
    try:
        async with asyncio.timeout(110):
            browser,context,page=await factory.create_cloak_browser(cloak_config={'engine':'playwright'})
            context.on('response',observe)
            worker=GoogleFlightsWorker()
            await worker.input_search_criteria(page,trip)
            await worker.execute_search(page)
            await page.wait_for_function("() => !/Fetching results/i.test(document.body?.innerText || '')",timeout=15000)
            report['search_text']=(await page.inner_text('body'))[:22000]
            flights=valid_flights(await worker.parse_search_results(page),trip)
            report['flights']=flights
            if not flights:raise ValueError('No exact public flight available')
            selected=flights[args.index]
            report['selected']=selected
            if not await page.locator(selected['selector']).count():
                refreshed=valid_flights(await worker.parse_search_results(page),trip)
                matches=[row for row in refreshed if all(row.get(key)==selected.get(key)
                    for key in ('airline','departure_time','arrival_time','stops','origin','destination'))]
                if len(matches)!=1:raise ValueError('Selected flight changed or is ambiguous after Google rerender')
                selected=matches[0];report['selected']=selected
            await page.locator(selected['selector']).click(timeout=8000)
            await page.wait_for_function("() => /Booking options|No booking options|Oops, something went wrong/i.test(document.body?.innerText || '')",timeout=35000)
            await snapshot(page,'selected')
            if args.continue_provider:
                button=page.get_by_role('button',name=re.compile(r'^Continue to book with '+re.escape(args.continue_provider)+r'\b',re.I))
                if await button.count()!=1:
                    raise ValueError('Requested partner has no unique observed Continue control; no link invented')
                async with context.expect_page(timeout=18000) as popup:
                    await button.click(timeout=6000)
                page=await popup.value
                await page.wait_for_load_state('domcontentloaded',timeout=25000)
                await page.wait_for_timeout(5000)
                await snapshot(page,'partner-'+args.continue_provider)
    except Exception as exc:
        report['error']=str(exc)
        if browser and not page.is_closed():
            await snapshot(page,'error-state')
        print(json.dumps({'error':str(exc)}),flush=True)
    finally:
        folder=Path(__file__).resolve().parents[2]/'sessions'/'new-approaches'
        folder.mkdir(parents=True,exist_ok=True)
        label=f'google-partners-{args.route}-{args.date}-{args.index}'+('-'+args.continue_provider.replace(' ','') if args.continue_provider else '')
        if args.max_stops:label+='-connecting'
        (folder/(label+'.json')).write_text(json.dumps(report,indent=2),encoding='utf-8')
        if browser:
            await page.screenshot(path=str(folder/(label+'.png')))
            await browser.close()
        await factory.cleanup()


if __name__=='__main__':asyncio.run(main())
