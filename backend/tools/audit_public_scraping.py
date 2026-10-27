"""Bounded, read-only scraper timing audit; never loads or modifies the database."""
import asyncio
from datetime import datetime,timezone
import json
from pathlib import Path
import sys
from time import perf_counter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from google_source import fetch_google
from quotes import valid_flights
from stealth.browser_factory import BrowserFactory
from workers.google_flights_worker import GoogleFlightsWorker
from workers.easemytrip_worker import EaseMyTripWorker

CASES=[dict(origin='PNQ',destination='JAI',departure_date='2026-11-18',passenger_count=1,cabin_class='ECONOMY'),
       dict(origin='BBI',destination='HYD',departure_date='2027-02-20',passenger_count=2,cabin_class='ECONOMY'),
       dict(origin='ATQ',destination='DEL',departure_date='2027-02-23',passenger_count=1,cabin_class='BUSINESS')]


async def main():
    factory=BrowserFactory()
    folder=Path(__file__).resolve().parents[2]/'sessions'/'scraping-audit-2026-10-09'
    folder.mkdir(parents=True,exist_ok=True)
    report=dict(observed_at=datetime.now(timezone.utc).isoformat(),scope='public_listing_only',cases=[])
    try:
        for case in CASES:
            trip={**case,'is_domestic':True,'preferred_time':'ANY'}
            entry=dict(trip=trip,sources=[]);report['cases'].append(entry)
            started=perf_counter()
            try:
                raw=await fetch_google(trip)
                valid=valid_flights(raw,trip)
                entry['sources'].append(dict(source='fli_public_page',elapsed_seconds=round(perf_counter()-started,3),
                    parsed=len(raw),valid=len(valid),inventory=raw[0].get('source_inventory') if raw else None,sample=valid[:3]))
            except Exception as exc:
                entry['sources'].append(dict(source='fli_public_page',elapsed_seconds=round(perf_counter()-started,3),error=str(exc)))
            for cls in (GoogleFlightsWorker,EaseMyTripWorker):
                worker=cls();browser=page=None;timings={};started=perf_counter()
                outcome=dict(source=worker.platform_id,timings=timings)
                entry['sources'].append(outcome)
                try:
                    async with asyncio.timeout(65):
                        tick=perf_counter();browser,context,page=await factory.create_cloak_browser(cloak_config={'engine':'playwright'})
                        timings['browser_launch']=round(perf_counter()-tick,3)
                        tick=perf_counter();await worker.input_search_criteria(page,trip)
                        timings['navigate']=round(perf_counter()-tick,3)
                        tick=perf_counter();await worker.execute_search(page)
                        timings['ready']=round(perf_counter()-tick,3)
                        if await worker.detect_captcha(page):raise ValueError('Human verification encountered; not bypassed')
                        tick=perf_counter();raw=await worker.parse_search_results(page)
                        timings['parse_first']=round(perf_counter()-tick,3)
                        valid=valid_flights(raw,trip)
                        outcome.update(parsed=len(raw),valid=len(valid),inventory=raw[0].get('source_inventory') if raw else None,sample=valid[:3])
                        await page.wait_for_timeout(1000)
                        tick=perf_counter();second=await worker.parse_search_results(page)
                        timings['parse_second']=round(perf_counter()-tick,3)
                        validated_second=valid_flights(second,trip)
                        outcome.update(parsed_after_one_second=len(second),valid_after_one_second=len(validated_second),
                            minimum_after_one_second=validated_second[0]['base_price'] if validated_second else None)
                        stem=f"{case['origin']}-{case['destination']}-{case['departure_date']}-{worker.platform_id}"
                        (folder/(stem+'.txt')).write_text(await page.inner_text('body'),encoding='utf-8')
                        outcome['public_page_text']=stem+'.txt'
                except Exception as exc:
                    outcome['error']=str(exc)
                finally:
                    if browser:await browser.close()
                    timings['total_with_one_second_recheck']=round(perf_counter()-started,3)
            print(json.dumps(entry,ensure_ascii=True),flush=True)
            (folder/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    finally:
        await factory.cleanup()


if __name__=='__main__':asyncio.run(main())
