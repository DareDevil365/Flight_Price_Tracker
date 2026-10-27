"""Read a real public Google booking page without passengers, payment or DB writes."""
import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stealth.browser_factory import BrowserFactory
from workers.google_flights_worker import GoogleFlightsWorker
from google_booking_context import load_booking_context
from quotes import valid_flights


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--route', required=True)
    parser.add_argument('--date', required=True)
    args = parser.parse_args()
    origin, destination = args.route.upper().split('-')
    trip = dict(origin=origin, destination=destination, departure_date=args.date,
                passenger_count=1, cabin_class='ECONOMY', is_domestic=True,
                preferred_time='ANY', max_stops=0)
    factory = BrowserFactory()
    browser = None
    try:
        async with asyncio.timeout(90):
            browser, _, page = await factory.create_cloak_browser()
            worker = GoogleFlightsWorker()
            await worker.input_search_criteria(page, trip)
            await worker.execute_search(page)
            flights = valid_flights(await worker.parse_search_results(page), trip)
            if not flights:
                raise ValueError('No validated nonstop flight found')
            report = await load_booking_context(page, trip, flights[0])
            folder = Path(__file__).resolve().parents[2] / 'sessions' / 'new-approaches'
            folder.mkdir(parents=True, exist_ok=True)
            (folder / f'guidance-{origin}-{destination}-{args.date}.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
            print(json.dumps(report, ensure_ascii=True))
    finally:
        if browser:
            await browser.close()
        await factory.cleanup()


if __name__ == '__main__':
    asyncio.run(main())
