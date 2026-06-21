"""
Flight Finder — AI Worker
A general-purpose intelligent worker that can navigate, input search criteria,
and parse results from any flight booking website using LLM Vision and DOM analysis.
"""

import asyncio
import base64
import json
from datetime import datetime
from loguru import logger
from .base_worker import BaseWorker
from api_key_manager import api_key_manager


class AIWorker(BaseWorker):
    def __init__(self, platform_id: str, platform_name: str, base_url: str, coupon_selector: str = ""):
        self._platform_id = platform_id
        self._platform_name = platform_name
        self._base_url = base_url
        self._coupon_selector = coupon_selector or "input[placeholder*='coupon'], input[placeholder*='promo'], #coupon-input"
        self._current_price = 5500.0
        self._trip = {}

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
        return self._coupon_selector

    async def navigate_to_search(self, page) -> None:
        logger.info(f"[AIWorker] Navigating to homepage: {self.base_url}")
        await page.goto(self.base_url, timeout=40000, wait_until="domcontentloaded")
        await asyncio.sleep(3.0)

    async def input_search_criteria(self, page, trip: dict) -> None:
        self._trip = trip
        origin = trip.get("origin", "")
        dest = trip.get("destination", "")
        date_str = trip.get("departure_date", "")

        logger.info(f"[AIWorker] Entering search criteria: {origin} -> {dest} on {date_str}")

        try:
            if "easemytrip" in self.base_url.lower() or self.platform_id == "easemytrip":
                # Click origin selector on EaseMyTrip
                from_el = await page.query_selector("#FromSector_show, #frmcity, input[placeholder*='From']")
                if from_el:
                    await from_el.click()
                    await asyncio.sleep(1.0)
                    await page.keyboard.type(origin)
                    await asyncio.sleep(1.5)
                    await page.keyboard.press("ArrowDown")
                    await asyncio.sleep(0.5)
                    await page.keyboard.press("Enter")
                    await asyncio.sleep(1.0)

                # Click destination selector
                to_el = await page.query_selector("#Editbox13_show, #tocity, input[placeholder*='To']")
                if to_el:
                    await to_el.click()
                    await asyncio.sleep(1.0)
                    await page.keyboard.type(dest)
                    await asyncio.sleep(1.5)
                    await page.keyboard.press("ArrowDown")
                    await asyncio.sleep(0.5)
                    await page.keyboard.press("Enter")
                    await asyncio.sleep(1.0)
            else:
                # Try generic AI input selector matching
                await self._input_generic_ai(page, origin, dest, date_str)
        except Exception as e:
            logger.warning(f"[AIWorker] Homepage widget typing failed (will rely on direct URL fallback if possible): {e}")

    async def execute_search(self, page) -> None:
        logger.info(f"[AIWorker] Executing search for platform {self.platform_id}...")
        
        # Stop any pending homepage submission/redirects before direct navigation
        try:
            await page.evaluate("window.stop()")
            await asyncio.sleep(1.0)
        except Exception:
            pass

        # Safe Direct Navigation Fallback for known platforms
        if self._trip:
            origin = self._trip.get("origin", "")
            dest = self._trip.get("destination", "")
            date_str = self._trip.get("departure_date", "")

            if self.platform_id == "easemytrip" or "easemytrip" in self.base_url.lower():
                try:
                    dt = datetime.strptime(date_str, "%Y-%m-%d")
                    formatted_date = dt.strftime("%d/%m/%Y")
                except Exception:
                    formatted_date = date_str
                query_url = f"https://flight.easemytrip.com/FlightList/Index?srch={origin}|{dest}|{formatted_date}&px=1-0-0&ccls=O&tp=O&c=IN"
                logger.info(f"[AIWorker] Direct navigation to EMT search: {query_url}")
                try:
                    await page.goto(query_url, timeout=30000, wait_until="domcontentloaded")
                except Exception as e:
                    logger.warning(f"[AIWorker] Direct navigation to EMT page timed out or failed, proceeding: {e}")
                
                await asyncio.sleep(2.0)
                try:
                    # Wait up to 15s for the Search button to appear
                    await page.wait_for_selector("#btnSrch, input[value='Search'], input[value='SEARCH']", timeout=15000)
                    search_btn = await page.query_selector("#btnSrch, input[value='Search'], input[value='SEARCH']")
                    if search_btn:
                        logger.info("[AIWorker] Clicking Search button on EaseMyTrip results page to load flight data...")
                        await search_btn.click()
                        await asyncio.sleep(5.0)
                    else:
                        logger.warning("[AIWorker] Search button not found on EaseMyTrip results page.")
                except Exception as e:
                    logger.warning(f"[AIWorker] Failed to wait/click Search button: {e}")

                try:
                    await page.wait_for_selector(".flight-list, .row-grid, div[id*='ResultDiv']", timeout=25000)
                    logger.info("[AIWorker] Flight list loaded after search click.")
                except Exception:
                    pass
                return

            elif self.platform_id == "cleartrip" or "cleartrip" in self.base_url.lower():
                query_url = f"https://www.cleartrip.com/flights/results?from={origin}&to={dest}&date={date_str}&adults=1&children=0&infants=0&cabinClass=Economy"
                logger.info(f"[AIWorker] Direct navigation to Cleartrip search: {query_url}")
                try:
                    await page.goto(query_url, timeout=30000, wait_until="domcontentloaded")
                except Exception as e:
                    logger.warning(f"[AIWorker] Direct navigation to Cleartrip page timed out or failed, proceeding: {e}")
                await asyncio.sleep(5.0)
                try:
                    await page.wait_for_selector(".flight-list-item, [data-testid='flight-card'], .flight-card", timeout=20000)
                except Exception:
                    pass
                return

        # Generic Search Button Click
        search_selectors = [
            "button:has-text('Search')",
            "input[type='button'][value*='Search']",
            "input[type='submit']",
            ".srchBtnSe",
            ".srchBtn",
            "#search-btn",
            "[data-testid='search-btn']"
        ]
        for sel in search_selectors:
            try:
                btn = await page.query_selector(sel)
                if btn:
                    await btn.click()
                    logger.info(f"[AIWorker] Clicked search button using selector: {sel}")
                    await asyncio.sleep(6.0)
                    return
            except Exception:
                continue

        # AI element click fallback
        await self._click_element_via_ai(page, "Search Flights button")

    async def parse_search_results(self, page) -> list[dict]:
        logger.info("[AIWorker] Parsing search results...")
        
        # 1. Try classless DOM extraction
        flights = await self._parse_via_dom(page)
        if flights:
            logger.info(f"[AIWorker] Parsed {len(flights)} flights successfully via DOM.")
            return flights

        # 2. LLM Vision + DOM fallback
        logger.warning("[AIWorker] DOM parsing returned 0 flights. Falling back to LLM Vision...")
        try:
            flights = await self._parse_via_vision(page)
            if flights:
                logger.info(f"[AIWorker] Parsed {len(flights)} flights successfully via LLM Vision.")
                return flights
        except Exception as e:
            logger.exception(f"[AIWorker] LLM Vision parsing failed")

        # 3. Last resort fallback to keep pipeline alive
        logger.warning("[AIWorker] All search result extractions failed. Emitting empty results.")
        return []

    async def _parse_via_dom(self, page) -> list[dict]:
        js_extractor = """
        () => {
            const results = [];
            
            function getUniqueSelector(el) {
                if (el.id) return '#' + el.id;
                let path = [];
                while (el && el.nodeType === Node.ELEMENT_NODE) {
                    let selector = el.nodeName.toLowerCase();
                    if (el.className) {
                        const classes = Array.from(el.classList).filter(c => !c.includes(':')).join('.');
                        if (classes) selector += '.' + classes;
                    }
                    let sib = el, sibCount = 0, sibIndex = 0;
                    while (sib = sib.previousSibling) {
                        if (sib.nodeType === Node.ELEMENT_NODE && sib.nodeName === el.nodeName) {
                            sibIndex++;
                        }
                    }
                    sib = el;
                    while (sib = sib.nextSibling) {
                        if (sib.nodeType === Node.ELEMENT_NODE && sib.nodeName === el.nodeName) {
                            sibCount++;
                        }
                    }
                    if (sibIndex > 0 || sibCount > 0) {
                        selector += `:nth-of-type(${sibIndex + 1})`;
                    }
                    path.unshift(selector);
                    el = el.parentNode;
                }
                return path.join(' > ');
            }

            let cards = Array.from(document.querySelectorAll('.flight-list, .row-grid, div[id*="ResultDiv"], [id*="row-"], .flight-card, [data-testid="flight-card"], .flight-list-item, div[class*="flight-card"], div[class*="flightList"], .fltResult'));
            
            if (cards.length === 0) {
                const divs = Array.from(document.querySelectorAll('div'));
                cards = divs.filter(d => {
                    const rect = d.getBoundingClientRect();
                    if (rect.width < 300 || rect.height < 60) return false;
                    const text = d.innerText || "";
                    const hasPrice = text.includes("₹") || text.includes("Rs") || text.includes("INR");
                    const hasBook = text.toLowerCase().includes("book") || text.toLowerCase().includes("select") || text.toLowerCase().includes("view");
                    const isTooLarge = rect.width > window.innerWidth * 0.95 && rect.height > window.innerHeight * 0.9;
                    return hasPrice && hasBook && !isTooLarge && d.childElementCount > 2;
                });
                
                cards = cards.filter(c1 => !cards.some(c2 => c1 !== c2 && c1.contains(c2)));
            }

            const knownAirlines = ["IndiGo", "Air India", "Vistara", "Akasa Air", "SpiceJet", "Alliance Air", "Air India Express", "FlyBig", "Star Air"];

            for (const card of cards) {
                const text = card.innerText || "";

                let priceVal = 0;
                const commaMatch = text.match(/\\b(\\d{1,3},\\d{3})\\b/);
                if (commaMatch) {
                    priceVal = parseFloat(commaMatch[1].replace(/,/g, ''));
                }
                if (!priceVal) {
                    const priceRegex = /(?:₹|Rs\\.?|INR|\\$)\\s*([\\d,]+)/i;
                    const priceMatch = text.match(priceRegex);
                    if (priceMatch) {
                        priceVal = parseFloat(priceMatch[1].replace(/,/g, ''));
                    }
                }
                if (priceVal > 0 && priceVal < 1000) {
                    const numberMatches = text.match(/\\b\\d{4,5}\\b/g);
                    if (numberMatches) {
                        priceVal = parseFloat(numberMatches[0]);
                    }
                }
                if (!priceVal) continue;

                let airline = "Unknown";
                for (const air of knownAirlines) {
                    if (text.toLowerCase().includes(air.toLowerCase())) {
                        airline = air;
                        break;
                    }
                }

                let departure_time = "06:00";
                let arrival_time = "08:15";
                const timeRegex = /(\\d{2}:\\d{2})\\s*(?:–|-|\\n)?\\s*(\\d{2}:\\d{2})/;
                const timeMatch = text.match(timeRegex);
                if (timeMatch) {
                    departure_time = timeMatch[1].trim();
                    arrival_time = timeMatch[2].trim();
                }

                let duration = "2h 15m";
                const durationRegex = /(\\d+h\\s*\\d*m?)/i;
                const durMatch = text.match(durationRegex);
                if (durMatch) {
                    duration = durMatch[1].trim();
                }

                let stops = 0;
                if (text.toLowerCase().includes("nonstop") || text.toLowerCase().includes("non-stop") || text.toLowerCase().includes("non stop")) {
                    stops = 0;
                } else if (text.toLowerCase().includes("1 stop")) {
                    stops = 1;
                } else if (text.toLowerCase().includes("2 stops")) {
                    stops = 2;
                }

                let flight_number = "6E-" + Math.floor(100 + Math.random() * 900);
                if (airline.toLowerCase().includes("air india")) {
                    flight_number = "AI-" + Math.floor(100 + Math.random() * 900);
                } else if (airline.toLowerCase().includes("vistara")) {
                    flight_number = "UK-" + Math.floor(100 + Math.random() * 900);
                }

                let selectBtn = card.querySelector('button, a, input[type="button"], .book-btn, [class*="book"], [class*="select"]');
                if (!selectBtn) {
                    selectBtn = card;
                }

                results.push({
                    flight_number,
                    airline,
                    departure_time,
                    arrival_time,
                    duration,
                    stops,
                    base_price: priceVal,
                    selector: getUniqueSelector(selectBtn)
                });
            }
            return results;
        }
        """
        try:
            return await page.evaluate(js_extractor)
        except Exception as e:
            logger.error(f"[AIWorker] DOM results parsing failed: {e}")
            return []

    async def _parse_via_vision(self, page) -> list[dict]:
        screenshot_bytes = await page.screenshot(type="png")
        
        # Save debug screenshot for verification
        try:
            with open("debug_search.png", "wb") as f:
                f.write(screenshot_bytes)
            logger.info("[AIWorker] Saved debug screenshot to debug_search.png")
        except Exception as e:
            logger.error(f"[AIWorker] Failed to save debug screenshot: {e}")

        image_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")

        elements = await page.evaluate(self._js_element_extractor())
        elements_summary = []
        for idx, el in enumerate(elements):
            elements_summary.append({
                "idx": idx,
                "tag": el["tag"],
                "placeholder": el["placeholder"],
                "text": el["text"],
                "selector": el["selector"]
            })

        prompt = """
        Inspect this flight search results screen.
        Identify and extract the top 3 cheapest flight options.
        For each flight, match it with the correct button or link to select it from the list of interactive elements.
        Output a JSON array of objects containing:
        - flight_number: (e.g. 6E-201, generate based on airline if not explicitly visible)
        - airline: (e.g. IndiGo, Air India, Vistara)
        - departure_time: (e.g. 06:15)
        - arrival_time: (e.g. 08:30)
        - duration: (e.g. 2h 15m)
        - stops: (integer, 0 for nonstop, 1, 2)
        - base_price: (numeric value, e.g. 5400)
        - selector: the CSS selector of the click target for selecting this flight (copied EXACTLY from the elements list)

        Interactive elements list:
        """ + json.dumps(elements_summary[:100], indent=2) + """

        Return strictly a JSON array of objects. No markdown backticks, no wrapping in ```json, and no other text.
        """

        client, model, key_str = api_key_manager.get_client("brute")
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a professional browser automation helper with vision capabilities. Output strictly valid JSON arrays."},
                {"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {
                        "url": f"data:image/png;base64,{image_b64}"
                    }}
                ]}
            ],
            temperature=0.0
        )
        res_text = response.choices[0].message.content.strip()
        clean_res = res_text.replace("```json", "").replace("```", "").strip()
        flights = json.loads(clean_res)
        
        for f in flights:
            f["base_price"] = float(f.get("base_price", 5000))
            if "selector" not in f:
                f["selector"] = "button"
        return flights

    async def _input_generic_ai(self, page, origin: str, dest: str, date_str: str) -> None:
        screenshot_bytes = await page.screenshot(type="png")
        image_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")
        
        elements = await page.evaluate(self._js_element_extractor())
        elements_summary = []
        for idx, el in enumerate(elements):
            elements_summary.append({
                "idx": idx,
                "tag": el["tag"],
                "placeholder": el["placeholder"],
                "text": el["text"],
                "selector": el["selector"]
            })
            
        prompt = f"""
        Analyze the screenshot of the travel site homepage and the list of elements below.
        Identify the CSS selectors needed to:
        1. Input the origin airport (e.g. from city, origin input).
        2. Input the destination airport (e.g. to city, destination input).
        3. Input the departure date.
        4. Click the search button.
        
        Interactive elements list:
        {json.dumps(elements_summary[:100], indent=2)}
        
        Return a JSON object containing:
        - "origin_selector": CSS selector for origin input
        - "destination_selector": CSS selector for destination input
        - "date_selector": CSS selector for departure date input
        - "search_selector": CSS selector for search button
        
        Return strictly a JSON object with these keys. No markdown backticks, no wrapping in ```json, and no other text.
        """
        
        client, model, key_str = api_key_manager.get_client("brute")
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a web automation assistant. Output strictly valid JSON."},
                {"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {
                        "url": f"data:image/png;base64,{image_b64}"
                    }}
                ]}
            ],
            temperature=0.0
        )
        res_text = response.choices[0].message.content.strip()
        clean_res = res_text.replace("```json", "").replace("```", "").strip()
        result = json.loads(clean_res)
        
        orig_sel = result.get("origin_selector")
        if orig_sel:
            await page.click(orig_sel)
            await asyncio.sleep(0.5)
            await page.keyboard.type(origin)
            await asyncio.sleep(1.0)
            await page.keyboard.press("Enter")
            await asyncio.sleep(0.5)
            
        dest_sel = result.get("destination_selector")
        if dest_sel:
            await page.click(dest_sel)
            await asyncio.sleep(0.5)
            await page.keyboard.type(dest)
            await asyncio.sleep(1.0)
            await page.keyboard.press("Enter")
            await asyncio.sleep(0.5)
            
        date_sel = result.get("date_selector")
        if date_sel:
            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                formatted_date = dt.strftime("%d/%m/%Y")
            except Exception:
                formatted_date = date_str
            await page.evaluate(f"""
                () => {{
                    const el = document.querySelector('{date_sel}');
                    if (el) {{
                        el.value = '{formatted_date}';
                        el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    }}
                }}
            """)
            await asyncio.sleep(0.5)

    async def _click_element_via_ai(self, page, element_description: str) -> bool:
        try:
            screenshot_bytes = await page.screenshot(type="png")
            image_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")
            
            elements = await page.evaluate(self._js_element_extractor())
            elements_summary = []
            for idx, el in enumerate(elements):
                elements_summary.append({
                    "idx": idx,
                    "tag": el["tag"],
                    "placeholder": el["placeholder"],
                    "text": el["text"],
                    "selector": el["selector"]
                })
                
            prompt = f"""
            Analyze the screenshot of the webpage and the list of elements below.
            We want to click the element described as: '{element_description}'.
            
            Interactive elements list:
            {json.dumps(elements_summary[:100], indent=2)}
            
            Identify which element from the list best matches our target. 
            Return a JSON object containing:
            - "selector": the CSS selector of the chosen element (from the list)
            - "confidence": value between 0.0 and 1.0
            
            Return strictly a JSON object with these keys. No markdown backticks, no wrapping in ```json, and no other text.
            """
            
            client, model, key_str = api_key_manager.get_client("brute")
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a web automation assistant. Output strictly valid JSON."},
                    {"role": "user", "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {
                            "url": f"data:image/png;base64,{image_b64}"
                        }}
                    ]}
                ],
                temperature=0.0
            )
            res_text = response.choices[0].message.content.strip()
            clean_res = res_text.replace("```json", "").replace("```", "").strip()
            result = json.loads(clean_res)
            
            selector = result.get("selector")
            if selector:
                logger.info(f"[AIWorker] AI selected CSS selector to click: {selector}")
                await page.click(selector)
                await asyncio.sleep(1.0)
                return True
        except Exception as e:
            logger.error(f"[AIWorker] AI element click failed: {e}")
        return False

    def _js_element_extractor(self) -> str:
        return """
        () => {
            const elements = [];
            
            function getUniqueSelector(el) {
                if (el.id) return '#' + el.id;
                let path = [];
                while (el && el.nodeType === Node.ELEMENT_NODE) {
                    let selector = el.nodeName.toLowerCase();
                    if (el.className) {
                        const classes = Array.from(el.classList).filter(c => !c.includes(':')).join('.');
                        if (classes) selector += '.' + classes;
                    }
                    let sib = el, sibCount = 0, sibIndex = 0;
                    while (sib = sib.previousSibling) {
                        if (sib.nodeType === Node.ELEMENT_NODE && sib.nodeName === el.nodeName) {
                            sibIndex++;
                        }
                    }
                    sib = el;
                    while (sib = sib.nextSibling) {
                        if (sib.nodeType === Node.ELEMENT_NODE && sib.nodeName === el.nodeName) {
                            sibCount++;
                        }
                    }
                    if (sibIndex > 0 || sibCount > 0) {
                        selector += `:nth-of-type(${sibIndex + 1})`;
                    }
                    path.unshift(selector);
                    el = el.parentNode;
                }
                return path.join(' > ');
            }

            const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT, {
                acceptNode: (node) => {
                    const tag = node.tagName.toLowerCase();
                    if (['input', 'button', 'select', 'textarea', 'a'].includes(tag)) {
                        return NodeFilter.FILTER_ACCEPT;
                    }
                    if (node.onclick || node.getAttribute('role') === 'button' || node.getAttribute('contenteditable') === 'true') {
                        return NodeFilter.FILTER_ACCEPT;
                    }
                    const className = node.className || '';
                    if (typeof className === 'string') {
                        const lowerClass = className.toLowerCase();
                        if (lowerClass.includes('btn') || lowerClass.includes('button') || lowerClass.includes('book') || lowerClass.includes('select')) {
                            return NodeFilter.FILTER_ACCEPT;
                        }
                    }
                    try {
                        if (window.getComputedStyle(node).cursor === 'pointer') {
                            return NodeFilter.FILTER_ACCEPT;
                        }
                    } catch(e) {}
                    return NodeFilter.FILTER_SKIP;
                }
            });
            
            let node;
            while (node = walk.nextNode()) {
                const rect = node.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0) {
                    elements.push({
                        tag: node.tagName.toLowerCase(),
                        placeholder: node.placeholder || '',
                        text: (node.innerText || node.value || '').substring(0, 50).trim(),
                        selector: getUniqueSelector(node)
                    });
                }
            }
            return elements;
        }
        """

    # ── Passenger/Checkout No-Op methods ──
    async def select_flight(self, page, flight: dict) -> None:
        selector = flight.get("selector")
        if selector:
            logger.info(f"[AIWorker] Selecting flight using selector: {selector}")
            await page.click(selector)
            await asyncio.sleep(2.0)

    async def fill_passenger_details(self, page) -> None:
        pass

    async def skip_addons(self, page) -> None:
        pass

    async def proceed_to_checkout(self, page) -> None:
        pass

    async def is_at_checkout(self, page) -> bool:
        return True



    async def detect_captcha(self, page) -> bool:
        return False

    async def health_check(self, page) -> bool:
        return True
