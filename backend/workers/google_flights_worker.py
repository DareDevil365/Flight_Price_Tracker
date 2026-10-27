"""
Flight Finder â€” Google Flights Worker
Playwright-based worker that extracts real-time flight listings from Google Flights.
Extracts visible quotes; unsupported or ambiguous criteria fail without guessed prices.
"""

from loguru import logger
from .base_worker import BaseWorker


class GoogleFlightsWorker(BaseWorker):
    def __init__(self, platform_id: str = "google_flights", platform_name: str = "Google Flights", base_url: str = "https://www.google.com/travel/flights"):
        self._platform_id = platform_id
        self._platform_name = platform_name
        self._base_url = base_url

    @property
    def platform_id(self) -> str:
        return self._platform_id

    @property
    def platform_name(self) -> str:
        return self._platform_name

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def coupon_selector(self) -> str:
        return ""

    async def navigate_to_search(self, page) -> None:
        logger.info("[GoogleFlightsWorker] Navigating to Google Flights homepage...")
        await page.goto(self.base_url, timeout=30000, wait_until="domcontentloaded")

    async def input_search_criteria(self, page, trip: dict) -> None:
        from quotes import search_url
        self._trip = trip
        await page.goto(search_url('google_flights', trip), timeout=45000, wait_until='domcontentloaded')


    async def execute_search(self, page) -> None:
        logger.info("[GoogleFlightsWorker] Waiting for search results to load...")
        try:
            # One bounded wait for dated flight cards, not navigation list items.
            # Known error pages return promptly and are rejected by the parser.
            await page.wait_for_function(r'''day => {
                const text=document.body?.innerText || '';
                if (/Oops, something went wrong|No results returned\.|verify you are human|unusual traffic/i.test(text)) return true;
                return (!day || text.includes(day)) && [...document.querySelectorAll('.yR1fYc,[role="listitem"]')]
                    .some(el=>el.getBoundingClientRect().width>0 && /\d{1,2}:\d{2}/.test(el.innerText));
            }''', arg=getattr(self,'_trip',{}).get('departure_date'), timeout=25000)
        except Exception:
            logger.warning("[GoogleFlightsWorker] Settle selector timeout, trying to parse anyway.")

    async def parse_search_results(self, page) -> list[dict]:
        logger.info("[GoogleFlightsWorker] Extracting flight options...")

        # 1. Attempt Classless DOM Extraction
        flights = await self._parse_via_dom(page)
        if flights:
            logger.info(f"[GoogleFlightsWorker] Parsed {len(flights)} flights successfully via DOM.")
            return flights

        # Monetary quotes require DOM or structured site evidence.
        return []

    async def _parse_via_dom(self, page) -> list[dict]:
        from .listing_parser import parse_cards
        total = None
        if hasattr(self, '_trip'):
            import re
            text = await page.inner_text('body')
            context = re.search(r'One way\s+(\d+)\s+(Premium economy|Economy|Business|First)', text, re.I)
            expected = self._trip['cabin_class'].replace('_',' ').lower()
            if not context or int(context[1])!=self._trip['passenger_count'] or context[2].lower()!=expected:
                raise ValueError('Google did not confirm the requested adult count and cabin. Use an exact-date search with supported criteria.')
            if 'Oops, something went wrong' in text or 'No results returned.' in text:
                raise ValueError('Google Flights could not load this trip. Retry or compare the other websites.')
            if not re.search(r'\bTrack prices[^\n]*\bdeparting\s+'+re.escape(self._trip['departure_date'])+r'\b',text,re.I):
                raise ValueError('Google did not confirm the requested departure date.')
            total = re.search(r'Prices include required taxes.*?for\s+(\d+)\s+adults?',text,re.I)
        rows = await parse_cards(page, '.yR1fYc, [role="listitem"]')
        if hasattr(self,'_trip'):
            # Google shows an explicit directed route on each current flight card.
            # The search URL alone cannot prove Google honored the airport choice.
            rows=[row for row in rows if row.get('origin')==self._trip['origin'] and row.get('destination')==self._trip['destination']]
            if total and int(total[1])==self._trip['passenger_count']:
                for row in rows:
                    row['price_basis'] = 'total'
        return rows


    async def select_flight(self, page, flight: dict) -> None:
        pass

    async def fill_passenger_details(self, page) -> None:
        pass

    async def skip_addons(self, page) -> None:
        pass

    async def proceed_to_checkout(self, page) -> None:
        pass

    async def is_at_checkout(self, page) -> bool:
        # Google comparison/booking-partner pages are not merchant payment pages.
        return False



    async def detect_captcha(self, page) -> bool:
        return await super().detect_captcha(page)

    async def health_check(self, page) -> bool:
        return True
