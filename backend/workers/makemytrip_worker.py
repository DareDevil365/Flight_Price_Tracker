"""
Flight Finder â€” MakeMyTrip Worker
Playwright-based worker that extracts real-time flight listings from MakeMyTrip.
Live fare evidence comes only from visible itinerary cards.
"""

import asyncio
import json
from time import monotonic
from datetime import datetime
from loguru import logger
from .base_worker import BaseWorker

LISTINGS_WAIT_SECONDS = 25


class MakeMyTripWorker(BaseWorker):
    def __init__(self):
        self._intercepted_responses = []
        self._interception_event = asyncio.Event()

    @property
    def platform_id(self) -> str:
        return "makemytrip"

    @property
    def platform_name(self) -> str:
        return "MakeMyTrip"

    @property
    def base_url(self) -> str:
        return "https://www.makemytrip.com/"

    @property
    def coupon_selector(self) -> str:
        return "input[placeholder*='coupon'], input[placeholder*='promo'], #coupon-input"

    async def _response_handler(self, response):
        # Live parsing uses the visible DOM. Do not decode or retain unrelated
        # response bodies, especially after the user opens a booking session.
        # BaseWorker independently keeps bounded HTTP failure metadata.
        return

    def find_value_by_keys(self, d, keys, default=None):
        for key in keys:
            val = self._find_key_bfs(d, key)
            if val is not None:
                return val
        return default

    def _find_key_bfs(self, d, target_key):
        if not isinstance(d, dict):
            return None
        
        queue = [(d, None)]
        blacklist = {"tax", "taxes", "taxdetails", "tax_details", "fee", "fees", "conveniencefee", "charge", "charges", "seat", "extra"}
        
        while queue:
            curr, parent = queue.pop(0)
            if not isinstance(curr, dict):
                continue
            
            if target_key in curr:
                parent_lower = str(parent).lower() if parent else ""
                if not any(b in parent_lower for b in blacklist):
                    return curr[target_key]
            
            for k, v in curr.items():
                k_lower = str(k).lower()
                if any(b in k_lower for b in blacklist):
                    continue
                if isinstance(v, dict):
                    queue.append((v, k))
        return None

    def find_numeric_by_keys(self, d, keys):
        val = self.find_value_by_keys(d, keys)
        if val is None:
            return None
        if isinstance(val, (int, float)):
            return float(val)
        if isinstance(val, str):
            import re
            val = re.sub(r'[^\d.]', '', val)
            try:
                return float(val)
            except ValueError:
                return None
        if isinstance(val, dict):
            for subkey in ["amount", "value", "price", "fare", "fB", "base", "total", "val", "baseFare", "basefare", "Fare", "totalFare", "totalfare"]:
                subval = val.get(subkey)
                if isinstance(subval, (int, float)):
                    return float(subval)
                if isinstance(subval, str):
                    import re
                    subval = re.sub(r'[^\d.]', '', subval)
                    try:
                        return float(subval)
                    except ValueError:
                        pass
            for subval in val.values():
                if isinstance(subval, (int, float)):
                    return float(subval)
                if isinstance(subval, str):
                    import re
                    subval = re.sub(r'[^\d.]', '', subval)
                    try:
                        return float(subval)
                    except ValueError:
                        pass
        return None

    def find_string_by_keys(self, d, keys):
        val = self.find_value_by_keys(d, keys)
        if val is None:
            return None
        if isinstance(val, str):
            return val.strip()
        if isinstance(val, (int, float)):
            return str(val)
        if isinstance(val, dict):
            for subkey in ["name", "code", "title", "val", "alN"]:
                subval = val.get(subkey)
                if isinstance(subval, str):
                    return subval.strip()
                if isinstance(subval, (int, float)):
                    return str(subval)
            for subval in val.values():
                if isinstance(subval, str):
                    return subval.strip()
        return None

    def find_stops_by_keys(self, d, keys):
        val = self.find_value_by_keys(d, keys)
        if val is None:
            return None
        if isinstance(val, int):
            return val
        if isinstance(val, float):
            return int(val)
        if isinstance(val, str):
            val_lower = val.lower()
            if "non" in val_lower or "zero" in val_lower:
                return 0
            import re
            match = re.search(r'\d+', val)
            if match:
                return int(match.group())
        return None

    def parse_time_value(self, val):
        if val is None:
            return None
        if isinstance(val, (int, float)):
            try:
                if val > 1e11:
                    dt_obj = datetime.fromtimestamp(val / 1000.0)
                elif val > 1e8:
                    dt_obj = datetime.fromtimestamp(val)
                else:
                    return None
                return dt_obj.strftime("%H:%M")
            except Exception:
                return None
        if isinstance(val, str):
            val = val.strip()
            # Try ISO fromisoformat first
            try:
                clean_iso = val.replace("Z", "+00:00")
                dt_obj = datetime.fromisoformat(clean_iso)
                return dt_obj.strftime("%H:%M")
            except Exception:
                pass
            
            if "t" in val.lower() or "-" in val or ":" in val:
                import re
                match = re.search(r'\d{2}:\d{2}', val)
                if match:
                    return match.group()
            import re
            digits = re.sub(r'\D', '', val)
            if len(digits) == 4:
                return f"{digits[:2]}:{digits[2:]}"
            elif len(digits) == 3:
                return f"0{digits[0]}:{digits[1:]}"
        return None

    def parse_duration_value(self, val):
        if val is None:
            return None
        if isinstance(val, str):
            return val.strip()
        if isinstance(val, (int, float)):
            mins = int(val)
            hours = mins // 60
            rem_mins = mins % 60
            if hours > 0:
                return f"{hours}h {rem_mins}m" if rem_mins > 0 else f"{hours}h"
            return f"{rem_mins}m"
        return None

    def parse_single_flight(self, d):
        if not isinstance(d, dict):
            return None
        price = self.find_numeric_by_keys(d, ["basePrice", "price", "amount", "fB", "pr", "fare", "base_price", "val", "value", "numericValue", "baseFare", "basefare", "Fare", "totalFare", "totalfare"])
        if price is None or price <= 0:
            return None
        flight_number = self.find_string_by_keys(d, ["flightNumber", "flightNo", "fN", "fn", "flightCode", "code", "flightNum", "fltNum", "flight_number"])
        airline = self.find_string_by_keys(d, ["airlineName", "airline", "alN", "carrier", "name", "airline_name"])
        
        if not flight_number and not airline:
            return None
            
        import re
        if flight_number:
            fn_match = re.search(r'\b([A-Z0-9]{2})\s*[-]?\s*(\d{3,4})\b', flight_number.upper())
            if fn_match:
                flight_number = f"{fn_match.group(1)}-{fn_match.group(2)}"
                
        if not airline and flight_number:
            prefix = flight_number.split('-')[0]
            prefix_map = { "6E": "IndiGo", "AI": "Air India", "UK": "Vistara", "QP": "Akasa Air", "SG": "SpiceJet", "IX": "Air India Express" }
            airline = prefix_map.get(prefix, "Unknown")
            
        if not flight_number and airline:
            airline_lower = airline.lower()
            prefix = "FL"
            prefix_map = { "indigo": "6E", "air india": "AI", "vistara": "UK", "akasa": "QP", "spicejet": "SG", "express": "IX" }
            for k, v in prefix_map.items():
                if k in airline_lower:
                    prefix = v
                    break
            flight_number = ""
            
        departure_time = self.parse_time_value(self.find_value_by_keys(d, ["departureTime", "depTime", "dt", "fdt", "departure", "startTime", "departure_time"])) or ""
        arrival_time = self.parse_time_value(self.find_value_by_keys(d, ["arrivalTime", "arrTime", "at", "fat", "arrival", "endTime", "arrival_time"])) or ""
        
        duration = self.parse_duration_value(self.find_value_by_keys(d, ["duration", "totalDuration", "dur", "td", "flightDuration", "timeTaken"]))
        if not duration:
            try:
                t1 = datetime.strptime(departure_time, "%H:%M")
                t2 = datetime.strptime(arrival_time, "%H:%M")
                diff = t2 - t1
                diff_mins = int(diff.total_seconds() // 60)
                if diff_mins < 0:
                    diff_mins += 24 * 60
                hours = diff_mins // 60
                mins = diff_mins % 60
                duration = f"{hours}h {mins}m"
            except Exception:
                duration = "2h 15m"
                
        stops = self.find_stops_by_keys(d, ["stops", "stopCount", "stp", "ns", "noOfStops", "stop_count"])
        if stops is None:
            stops = 0
            
        return {
            "flight_number": flight_number,
            "airline": airline,
            "departure_time": departure_time,
            "arrival_time": arrival_time,
            "duration": duration,
            "stops": stops,
            "base_price": price
        }

    def find_flight_arrays(self, obj):
        results = []
        if isinstance(obj, list):
            for item in obj:
                results.extend(self.find_flight_arrays(item))
        elif isinstance(obj, dict):
            # A valid flight object in these APIs is usually a leaf node in terms of nested arrays.
            # If the dict contains a list, it's likely a container, not the flight itself.
            has_iterable = any(isinstance(v, (list, dict)) and len(v) > 2 for v in obj.values())
            
            # We first try to parse it
            parsed = None
            if not any(isinstance(v, list) for v in obj.values()):
                parsed = self.parse_single_flight(obj)
                
            if parsed:
                results.append(parsed)
            else:
                for val in obj.values():
                    results.extend(self.find_flight_arrays(val))
        return results

    async def navigate_to_search(self, page) -> None:
        logger.info("[MakeMyTripWorker] Navigating to MakeMyTrip homepage...")
        self._intercepted_responses = []
        self._interception_event.clear()
        
        # Register response listener
        self.attach_response_listener(page)
        
        await page.goto(self.base_url, timeout=30000, wait_until="domcontentloaded")
        await asyncio.sleep(2.0)
        
        from provider_homepage import dismiss_makemytrip_login
        await dismiss_makemytrip_login(page)

    async def input_search_criteria(self, page, trip: dict) -> None:
        from quotes import search_url
        self._trip = trip
        self._intercepted_responses.clear()
        self._interception_event.clear()
        self.attach_response_listener(page)
        await page.goto(search_url('makemytrip', trip), timeout=45000, wait_until='domcontentloaded')
        # Normal dispatch uses this direct URL, not navigate_to_search(). The
        # optional login dialog must therefore be handled on this active path.
        from provider_homepage import dismiss_makemytrip_login
        await dismiss_makemytrip_login(page)


    async def execute_search(self, page) -> None:
        from provider_homepage import dismiss_makemytrip_login
        from provider_status import page_problem, ProviderError
        deadline = monotonic() + LISTINGS_WAIT_SECONDS
        # A login dialog may hydrate after navigation. Recheck while waiting;
        # do not spend the entire listing timeout behind a closeable overlay.
        while True:
            await dismiss_makemytrip_login(page, wait_ms=0)
            state = await page.evaluate('''() => ({
                text: (document.body?.innerText || ''),
                cards: [...document.querySelectorAll('.listingCard, [id*="listing-id"], .fli-list')]
                    .some(e => e.checkVisibility() && e.getBoundingClientRect().width>0)
            })''')
            problem = page_problem(state['text'], page.url, getattr(self, '_http_failures', []))
            if problem:
                raise problem
            if state['cards']:
                return
            if monotonic() >= deadline:
                raise ProviderError('SEARCH_TIMEOUT',
                    'MakeMyTrip did not load readable flight listings within the search deadline. No fare or payment total was verified; use the manual search link.')
            await asyncio.sleep(min(.25, max(0, deadline-monotonic())))

    async def parse_search_results(self, page) -> list[dict]:
        # Generic recursive JSON matching and vision estimates are retained below
        # only for research tests. Live fares require exact visible card evidence.
        from provider_homepage import dismiss_makemytrip_login
        await dismiss_makemytrip_login(page, wait_ms=0)
        return await self._parse_via_dom(page)

    async def _parse_via_dom(self, page) -> list[dict]:
        from .listing_parser import parse_cards
        return await parse_cards(page, '.listingCard, [id*="listing-id"], .fli-list')


    async def fill_passenger_details(self, page) -> None:
        pass

    async def skip_addons(self, page) -> None:
        pass

    async def proceed_to_checkout(self, page) -> None:
        pass

    async def is_at_checkout(self, page) -> bool:
        return await super().is_at_checkout(page)




    async def detect_captcha(self, page) -> bool:
        return await super().detect_captcha(page)


    async def health_check(self, page) -> bool:
        return True

    async def scrape_onsite_coupons(self, page) -> list[dict]:
        from offer_parser import scrape_published_offers
        return await scrape_published_offers(page, self.platform_id)
