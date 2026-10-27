"""
Flight Finder â€” EaseMyTrip Worker
Playwright-based worker that extracts real-time flight listings from EaseMyTrip.
Live fare evidence comes only from visible itinerary cards.
"""

import asyncio
import json
from datetime import datetime
from loguru import logger
from .base_worker import BaseWorker


class EaseMyTripWorker(BaseWorker):
    # EMT currently keeps an undiscounted [price] span hidden while rendering
    # the current fare in another spnPrice span without that attribute. Waiting
    # only for [price] caused 35-second timeouts despite readable listings.
    LISTINGS_READY = r'''() => {
        const text=(document.body?.innerText || '').toLowerCase().trim();
        if (/network problem|unable to connect to our systems|server error|access denied|no flights found|no flights available/.test(text)
            || text==='200-ok' || text==='200 ok') return true;
        const visible=el=>el.getBoundingClientRect().width>0 && el.getBoundingClientRect().height>0;
        for (const card of document.querySelectorAll('.main-bo-lis,.flight-list-item')) {
            if (!visible(card) || card.querySelector('.main-bo-lis,.flight-list-item')) continue;
            const body=card.innerText || '';
            if ((body.match(/\b\d{1,2}:\d{2}\b/g)||[]).length<2 || !/non.?stop|\b\d+\s*stops?\b/i.test(body)) continue;
            if (/\(\d+\s*km from /i.test(body)) continue;
            for (const price of card.querySelectorAll('[id^="spnPrice"], [data-testid*="price"], .actual-price, .price, .priceSection, .fliFare, .flight-price')) {
                if (!visible(price) || /lock|coupon|promo|discount|saving/i.test(price.id)) continue;
                let excluded=false;
                for (let ancestor=price;ancestor && ancestor!==card;ancestor=ancestor.parentElement) {
                    if (ancestor.matches('s,del,[class*="coupon" i],[class*="promo" i]')
                        || /line-through/.test(getComputedStyle(ancestor).textDecorationLine)) {excluded=true;break;}
                }
                if (excluded) continue;
                const scope=price.parentElement;
                const currency=scope && (/₹|\bINR\b|\bRs\.?/i.test(scope.innerText)
                    || [...scope.querySelectorAll('i.CurrncyCD_Rs,[data-currency="INR"]')].some(visible));
                if (!currency || /\$|\bUSD\b|\bEUR\b|\bGBP\b|£|€/i.test(scope.innerText)) continue;
                const value=price.innerText.trim().replace(/^(?:₹|INR|Rs\.?)\s*/i,'');
                if (/^(?:\d+|\d{1,3}(?:,\d{3})+|\d{1,2}(?:,\d{2})*,\d{3})(?:\.\d{1,2})?$/.test(value)
                    && Number(value.replace(/,/g,''))>0) return true;
            }
        }
        return false;
    }'''

    def __init__(self):
        self._intercepted_responses = []
        self._interception_event = asyncio.Event()

    @property
    def platform_id(self) -> str:
        return "easemytrip"

    @property
    def platform_name(self) -> str:
        return "EaseMyTrip"

    @property
    def base_url(self) -> str:
        return "https://www.easemytrip.com/"

    @property
    def coupon_selector(self) -> str:
        return "input[placeholder*='coupon'], input[placeholder*='promo'], #coupon-input"

    async def _response_handler(self, response):
        # DOM readers establish fares and coupons; unused JSON response bodies
        # add memory/decoding cost and could contain booking or passenger data.
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
        if isinstance(obj, dict):
            parsed = self.parse_single_flight(obj)
            if parsed:
                return [parsed]
            results = []
            for val in obj.values():
                results.extend(self.find_flight_arrays(val))
            return results
        elif isinstance(obj, list):
            parsed_list = []
            for item in obj:
                if isinstance(item, dict):
                    parsed = self.parse_single_flight(item)
                    if parsed:
                        parsed_list.append(parsed)
                    else:
                        parsed_list.extend(self.find_flight_arrays(item))
                elif isinstance(item, (list, dict)):
                    parsed_list.extend(self.find_flight_arrays(item))
            return parsed_list
        return []

    async def navigate_to_search(self, page) -> None:
        logger.info("[EaseMyTripWorker] Navigating to EaseMyTrip homepage...")
        self._intercepted_responses = []
        self._interception_event.clear()
        
        # Register response listener
        self.attach_response_listener(page)
        
        await page.goto(self.base_url, timeout=30000, wait_until="domcontentloaded")
        await asyncio.sleep(2.0)

    async def input_search_criteria(self, page, trip: dict) -> None:
        from quotes import search_url
        self._trip = trip
        self._intercepted_responses.clear()
        self._interception_event.clear()
        self.attach_response_listener(page)
        await page.goto(search_url('easemytrip', trip), timeout=45000, wait_until='domcontentloaded')


    async def execute_search(self, page) -> None:
        from playwright.async_api import TimeoutError as PlaywrightTimeout
        try:
            await page.wait_for_function(self.LISTINGS_READY,timeout=3000)
        except PlaywrightTimeout:
            # This site's direct URL pre-fills criteria but sometimes needs submission.
            button = page.locator('#btnSrch, input[value="Search"], input[value="SEARCH"]').first
            if await button.count() and await button.is_visible():
                await button.click(timeout=8000)
        try:
            await page.wait_for_function(self.LISTINGS_READY,timeout=35000)
        except PlaywrightTimeout:
            logger.warning('Flight prices unavailable; checking page for blocks or layout changes.')
        from provider_status import page_problem
        problem=page_problem(await page.inner_text('body'),page.url,getattr(self,'_http_failures',[]))
        if problem:
            raise problem

    async def parse_search_results(self, page) -> list[dict]:
        # Generic recursive JSON matching and vision estimates are retained below
        # only for research tests. Live fares require exact visible card evidence.
        return await self._parse_via_dom(page)

    async def _parse_via_dom(self, page) -> list[dict]:
        from .listing_parser import parse_cards
        if hasattr(self, '_trip'):
            from datetime import date
            import re
            trip = self._trip
            criteria = await page.evaluate('''() => ({day:document.querySelector('#ddate')?.value,
                origin:document.querySelector('#FromSector_show')?.value,
                destination:document.querySelector('#Editbox13_show')?.value,
                cabin:document.querySelector('#optClass')?.selectedOptions[0]?.textContent})''')
            text = await page.inner_text('body')
            adults = re.search(r'\b(\d+)\s+Travellers?\b',text,re.I)
            expected_cabin = trip['cabin_class'].replace('_','').lower()
            if (criteria['day'] != date.fromisoformat(trip['departure_date']).strftime('%d/%m/%Y')
                or trip['origin'] not in (criteria['origin'] or '') or trip['destination'] not in (criteria['destination'] or '')
                or not adults or int(adults[1]) != trip['passenger_count']
                or (criteria['cabin'] or '').replace(' ','').lower() != expected_cabin):
                raise ValueError('EaseMyTrip did not confirm the requested airports, date, adults and cabin.')
        return await parse_cards(page, '.main-bo-lis, .flight-list-item')


    async def fill_passenger_details(self, page) -> None:
        pass

    async def skip_addons(self, page) -> None:
        pass

    async def proceed_to_checkout(self, page) -> None:
        pass

    async def is_at_checkout(self, page) -> bool:
        data=await self.read_checkout_total(page)
        return bool(data and data.get('stage')=='payment') or await super().is_at_checkout(page)

    async def read_selected_payment(self,page):
        active=page.locator('.pay-m .pay-mm li.d4.blk-cls')
        panel=page.locator('.pay-m .upi-m')
        if await active.count()==1 and await active.is_visible() and await panel.count()==1 and await panel.is_visible():
            return dict(method='UPI',banks=[],label='EaseMyTrip selected UPI payment tab')
        return await super().read_selected_payment(page)




    async def detect_captcha(self, page) -> bool:
        return await super().detect_captcha(page)


    async def health_check(self, page) -> bool:
        return True

    async def scrape_onsite_coupons(self, page) -> list[dict]:
        from offer_parser import scrape_published_offers
        more=page.locator('.offer_popup_btn').filter(has_text='View All Coupons')
        if await more.count() and await more.first.is_visible():
            await more.first.click(timeout=4000)
            await page.wait_for_timeout(500)
        offers=await scrape_published_offers(page, self.platform_id)
        # Public View All Coupons is a dialog; close it before handoff/testing.
        close=page.locator('#cpnpop .fr_close_popup')
        if await close.count() and await close.first.is_visible():
            await close.first.click(timeout=3000)
        return offers

    async def read_checkout_total(self,page):
        # EMT renders the INR symbol as a CSS icon, so innerText drops it.
        # Require that exact visible symbol beside the labeled grand total.
        result=await page.evaluate(r'''() => {
            const value=document.querySelector('#spnGrndTotal');
            const parent=value?.closest('.pr');
            if (!value?.getBoundingClientRect().width || !parent || !/Grand Total/i.test(parent.innerText)) return null;
            const currency=parent.querySelector('i.CurrncyCD_Rs');
            if (!currency?.getBoundingClientRect().width) return null;
            const raw=value.innerText.trim();
            if (!/^(?:\d+|\d{1,3}(?:,\d{3})+|\d{1,2}(?:,\d{2})*,\d{3})(?:\.\d{1,2})?$/.test(raw)) return null;
            const total=Number(raw.replace(/,/g,''));
            const paymentTotals=[...document.querySelectorAll('.pay-m .pr-m2')].filter(el=>el.getBoundingClientRect().width>0).map(el=>Number(el.innerText.trim().replace(/,/g,'')));
            if (paymentTotals.some(amount=>amount!==total)) return null;
            const fees=[...document.querySelectorAll('.pay-m .n-re')].filter(el=>el.getBoundingClientRect().width>0).map(el=>({label:'Convenience fee',amount:Number(el.querySelector('[ng-bind="ConvenienceFee"]')?.innerText?.replace(/,/g,''))})).filter(f=>Number.isFinite(f.amount));
            return Number.isFinite(total) && total>0 ? {total,fees,currency:'INR',stage:paymentTotals.length?'payment':'review'} : null;
        }''')
        native=page.locator('#spnGrndTotal')
        if await native.count() and await native.first.is_visible():
            return result
        return await super().read_checkout_total(page)

    async def enter_coupon_code(self,page,code):
        if not isinstance(code,str) or not __import__('re').fullmatch(r'[A-Z0-9_-]{2,40}',code):
            raise ValueError('Malformed coupon code; refusing browser interaction')
        field=page.locator('#txtCouponCode')
        if await field.count() and await field.is_visible():
            await field.fill(code)
        else:
            await super().enter_coupon_code(page,code)

    async def get_applied_coupon_code(self,page):
        label=page.locator('#divCouponApplied #spnCouponDisplay')
        if await label.count() and await label.is_visible():
            return (await label.inner_text()).strip().upper()
        return await super().get_applied_coupon_code(page)

    async def check_coupon_applied(self,page):
        error=page.locator('#divCouponErrMessage')
        if await error.count() and await error.is_visible() and (await error.inner_text()).strip():
            return dict(success=False,error=(await error.inner_text()).strip())
        container=page.locator('#divCouponApplied')
        if await container.count() and await container.is_visible():
            code=await self.get_applied_coupon_code(page)
            remove=container.locator('[ng-click="RemoveCouponeMob()"]')
            if code and await remove.count() and await remove.is_visible():
                return dict(success=True,code=code,error=None)
        return await super().check_coupon_applied(page)

    async def get_coupon_validation_text(self,page):
        code=await self.get_applied_coupon_code(page)
        if code and __import__('re').fullmatch('[A-Z0-9_-]{2,40}',code):
            card=page.locator('#lblCpn'+code+'VM').first
            if await card.count():
                return await card.text_content() or ''
        return ''

    async def click_apply_coupon(self,page):
        button=page.locator('#spnApply')
        if await button.count() and await button.is_visible():
            await button.click(timeout=4000)
            await page.wait_for_timeout(1200)
        else:
            await super().click_apply_coupon(page)

    async def clear_coupon_field(self,page):
        remove=page.locator('#spnCpnRemoveVM, [ng-click="RemoveCouponeMob()"], [ng-click="RemoveCoupone()"]')
        for button in await remove.all():
            if await button.is_visible():
                await button.click(timeout=4000)
                await page.wait_for_timeout(800)
                break
        field=page.locator('#txtCouponCode')
        if await field.count() and await field.is_visible():
            await field.fill('')
        else:
            await super().clear_coupon_field(page)
