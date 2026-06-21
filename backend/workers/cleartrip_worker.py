"""
Flight Finder — Cleartrip Worker
Playwright-based worker that extracts real-time flight listings from Cleartrip.
Utilizes classless DOM matching and falls back to LLM Vision if DOM parsing fails.
"""

import asyncio
import base64
import json
from datetime import datetime
from loguru import logger
from .base_worker import BaseWorker
from api_key_manager import api_key_manager


class CleartripWorker(BaseWorker):
    def __init__(self):
        self._current_price = 5500.0
        self._intercepted_responses = []
        self._interception_event = asyncio.Event()

    @property
    def platform_id(self) -> str:
        return "cleartrip"

    @property
    def platform_name(self) -> str:
        return "Cleartrip"

    @property
    def base_url(self) -> str:
        return "https://www.cleartrip.com/"

    @property
    def coupon_selector(self) -> str:
        return "input[placeholder*='coupon'], input[placeholder*='promo'], #coupon-input"

    async def _response_handler(self, response):
        url = response.url
        if "cleartrip" in url.lower() and any(k in url.lower() for k in ["flight", "search", "api"]):
            try:
                headers = response.headers
                content_type = headers.get("content-type", "")
                if "application/json" in content_type or "text/plain" in content_type:
                    data = await response.json()
                    self._intercepted_responses.append((url, data))
                    logger.info(f"[CleartripWorker] Intercepted API response: {url}")
                    self._interception_event.set()
            except Exception:
                pass

    def find_value_by_keys(self, d, keys, default=None):
        for key in keys:
            val = self._find_key_recursive(d, key)
            if val is not None:
                return val
        return default

    def _find_key_recursive(self, d, target_key):
        if not isinstance(d, dict):
            return None
        if target_key in d:
            return d[target_key]
        for k, v in d.items():
            if isinstance(v, dict):
                res = self._find_key_recursive(v, target_key)
                if res is not None:
                    return res
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, dict):
                        res = self._find_key_recursive(item, target_key)
                        if res is not None:
                            return res
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
        if price is None or price < 1200:
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
            flight_number = f"{prefix}-0000"
            
        departure_time = self.parse_time_value(self.find_value_by_keys(d, ["departureTime", "depTime", "dt", "fdt", "departure", "startTime", "departure_time"])) or "06:00"
        arrival_time = self.parse_time_value(self.find_value_by_keys(d, ["arrivalTime", "arrTime", "at", "fat", "arrival", "endTime", "arrival_time"])) or "08:15"
        
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
        logger.info("[CleartripWorker] Navigating to Cleartrip homepage...")
        self._intercepted_responses = []
        self._interception_event.clear()
        
        # Register response listener
        page.on("response", self._response_handler)
        
        await page.goto(self.base_url, timeout=30000, wait_until="domcontentloaded")
        await asyncio.sleep(2.0)

    async def input_search_criteria(self, page, trip: dict) -> None:
        origin = trip.get("origin", "")
        dest = trip.get("destination", "")
        date_str = trip.get("departure_date", "") # Expects YYYY-MM-DD

        # Direct Cleartrip search URL construction
        query_url = f"https://www.cleartrip.com/flights/results?from={origin}&to={dest}&date={date_str}&adults=1&children=0&infants=0&cabinClass=Economy"
        logger.info(f"[CleartripWorker] Navigating directly to search query: {query_url}")
        await page.goto(query_url, timeout=35000, wait_until="domcontentloaded")
        await asyncio.sleep(4.0)

    async def execute_search(self, page) -> None:
        logger.info("[CleartripWorker] Waiting for flight search API response...")
        try:
            # Wait up to 25 seconds for the API interception event
            await asyncio.wait_for(self._interception_event.wait(), timeout=25.0)
            logger.info("[CleartripWorker] Intercepted flight search API response successfully.")
        except asyncio.TimeoutError:
            logger.warning("[CleartripWorker] API response interception timed out, waiting for DOM elements instead.")
            try:
                # Wait for common flight rows selectors on Cleartrip
                await page.wait_for_selector(".flight-list-item, [data-testid='flight-card'], .flight-card", timeout=12000)
                await asyncio.sleep(2.0)  # Extra settle time
            except Exception:
                logger.warning("[CleartripWorker] Settle selector timeout, trying to parse anyway.")

    async def parse_search_results(self, page) -> list[dict]:
        logger.info("[CleartripWorker] Extracting flight options...")
        
        try:
            page.remove_listener("response", self._response_handler)
        except Exception:
            pass

        # 1. Attempt API Interception Parsing
        if self._intercepted_responses:
            logger.info(f"[CleartripWorker] Attempting to parse {len(self._intercepted_responses)} intercepted responses...")
            flights = []
            for url, data in self._intercepted_responses:
                try:
                    parsed = self.find_flight_arrays(data)
                    if parsed:
                        flights.extend(parsed)
                except Exception as e:
                    logger.error(f"[CleartripWorker] Error parsing API data: {e}")
            
            if flights:
                deduped = []
                seen = set()
                for f in flights:
                    key = (f["flight_number"], f["departure_time"], f["base_price"])
                    if key not in seen:
                        seen.add(key)
                        deduped.append(f)
                logger.info(f"[CleartripWorker] Parsed {len(deduped)} unique flights successfully via API interception.")
                return deduped

        # 2. Attempt Classless DOM Extraction
        flights = await self._parse_via_dom(page)
        if flights:
            logger.info(f"[CleartripWorker] Parsed {len(flights)} flights successfully via DOM.")
            return flights

        # 2. Fallback to Screenshot + LLM Vision
        logger.warning("[CleartripWorker] DOM parsing returned 0 flights. Falling back to LLM Vision...")
        try:
            flights = await self._parse_via_vision(page)
            if flights:
                logger.info(f"[CleartripWorker] Parsed {len(flights)} flights successfully via LLM Vision.")
                return flights
        except Exception as e:
            logger.error(f"[CleartripWorker] LLM Vision parsing failed: {e}")

        # 3. Return empty list on failure (Phase 0)
        logger.warning("[CleartripWorker] All extraction strategies failed. Returning empty list.")
        return []

    async def _parse_via_dom(self, page) -> list[dict]:
        """Extract flights from DOM using Cleartrip layout markers."""
        js_extractor = """
        () => {
            const results = [];
            // Select Cleartrip listing card elements
            const cards = Array.from(document.querySelectorAll('.flight-list-item, [data-testid="flight-card"], .flight-card, div[class*="flight-card"]'));
            
            for (const card of cards) {
                const text = card.innerText || "";
                if (!text.includes("₹") && !text.includes("Rs") && !text.toLowerCase().includes("book") && !text.toLowerCase().includes("lock")) continue;

                const lines = text.split('\n').map(l => l.trim()).filter(l => l.length > 0);
                if (lines.length < 3) continue;

                // Extract Price
                let priceVal = 0;
                const priceRegex = /(?:₹|Rs\\.?|\\$)?\\s*([\\d,]+)/;
                let possiblePrices = [];
                for (let i = 0; i < lines.length; i++) {
                    const line = lines[i];
                    const lowLine = line.toLowerCase();
                    
                    // Skip lock prices or promo/discount lines
                    if (lowLine.includes("lock") || (i > 0 && lines[i-1].toLowerCase().includes("lock"))) {
                        continue;
                    }
                    if (lowLine.includes("off") || lowLine.includes("save") || lowLine.includes("discount") || 
                        lowLine.includes("cashback") || lowLine.includes("coupon") || lowLine.includes("promo") || 
                        lowLine.includes("fee") || lowLine.includes("tax") || lowLine.includes("gst") || 
                        lowLine.includes("charge") || lowLine.includes("seat") || lowLine.includes("extra")) {
                        continue;
                    }
                    
                    // Clean line of currency/spaces/commas
                    const cleanLine = lowLine.replace(/[₹\$\s,]/g, "");
                    // If it contains letters (except 'rs') or colons, skip (e.g. times, flight numbers, duration)
                    if (cleanLine.match(/[a-z:]/i)) {
                        if (!cleanLine.startsWith("rs")) {
                            continue;
                        }
                    }
                    
                    const match = line.match(priceRegex);
                    if (match) {
                        const parsed = parseFloat(match[1].replace(/,/g, ''));
                        if (parsed > 0) {
                            possiblePrices.push(parsed);
                        }
                    }
                }
                
                // Filter prices to find actual fares (usually >= 1200)
                const fares = possiblePrices.filter(p => p >= 1200);
                if (fares.length > 0) {
                    priceVal = fares[0]; // first one that looks like a fare
                } else {
                    // last resort: search all lines with literal currency symbol
                    for (const line of lines) {
                        const match = line.match(/(?:₹|Rs\\.?|\\$)\\s*([\\d,]+)/);
                        if (match) {
                            const val = parseFloat(match[1].replace(/,/g, ''));
                            if (val >= 1200) {
                                priceVal = val;
                                break;
                            }
                        }
                    }
                }
                if (!priceVal) continue;

                // Extract Stops
                let stops = 0;
                if (text.toLowerCase().includes("nonstop") || text.toLowerCase().includes("non-stop") || text.toLowerCase().includes("non stop")) {
                    stops = 0;
                } else if (text.toLowerCase().includes("1 stop")) {
                    stops = 1;
                } else if (text.toLowerCase().includes("2 stops")) {
                    stops = 2;
                }

                // Extract Airline
                const knownAirlines = ["IndiGo", "Air India", "Vistara", "Akasa Air", "SpiceJet", "Alliance Air", "Air India Express", "FlyBig", "Star Air"];
                let airline = "Unknown";
                for (const line of lines) {
                    const matched = knownAirlines.find(a => line.toLowerCase() === a.toLowerCase() || line.includes(a));
                    if (matched) {
                        airline = matched;
                        break;
                    }
                }
                
                // Extract Times
                let departure_time = "06:00";
                let arrival_time = "08:15";
                const timeRegex = /(\\d{2}:\\d{2})\\s*(?:–|-|\\n)?\\s*(\\d{2}:\\d{2})/;
                const timeMatch = text.match(timeRegex);
                if (timeMatch) {
                    departure_time = timeMatch[1].trim();
                    arrival_time = timeMatch[2].trim();
                }

                // Extract Duration
                let duration = "2h 15m";
                const durationRegex = /(\\d+h\\s*\\d*m?)/i;
                const durMatch = text.match(durationRegex);
                if (durMatch) {
                    duration = durMatch[1].trim();
                }

                // Extract real flight number from card text or generate deterministically
                const flightNumRegex = /\b(6E|AI|UK|SG|QP|I5|IX|S5|2T|G8)\s*[-]?\s*(\d{3,4})\b/i;
                const fnMatch = text.match(flightNumRegex);
                let flight_number = "";
                if (fnMatch) {
                    flight_number = fnMatch[1].toUpperCase() + "-" + fnMatch[2];
                } else {
                    const cleanTime = (departure_time + arrival_time).replace(/[^0-9]/g, '');
                    const prefixMap = { "indigo": "6E", "air india": "AI", "vistara": "UK", "akasa": "QP", "spicejet": "SG" };
                    let prefix = "FL";
                    for (const k in prefixMap) {
                        if (airline.toLowerCase().includes(k)) {
                            prefix = prefixMap[k];
                            break;
                        }
                    }
                    flight_number = prefix + "-" + (cleanTime || "0000");
                }

                results.push({
                    flight_number,
                    airline,
                    departure_time,
                    arrival_time,
                    duration,
                    stops,
                    base_price: priceVal
                });
            }
            return results;
        }
        """
        try:
            return await page.evaluate(js_extractor)
        except Exception as e:
            logger.error(f"[CleartripWorker] DOM evaluation failed: {e}")
            return []

    async def _parse_via_vision(self, page) -> list[dict]:
        """Convert page to screenshot and query LLM vision model to parse flight results."""
        screenshot_bytes = await page.screenshot(type="jpeg", quality=40)
        image_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")

        prompt = """
        Inspect this Cleartrip flight search results screen.
        Identify and extract the top 3 cheapest flight options.
        For each flight, output a JSON object containing:
        - flight_number: (e.g. 6E-201, generate based on airline if not explicitly visible)
        - airline: (e.g. IndiGo, Air India, Vistara)
        - departure_time: (e.g. 06:15)
        - arrival_time: (e.g. 08:30)
        - duration: (e.g. 2h 15m)
        - stops: (integer, 0 for nonstop, 1, 2)
        - base_price: (numeric value, e.g. 5400)

        Return strictly a JSON array of objects with these keys. No markdown backticks, no wrapping in ```json, and no other text.
        """
        
        client, model, key_str = api_key_manager.get_client("brute")
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a professional browser automation helper with vision capabilities. Output strictly valid JSON arrays."},
                {"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {
                        "url": f"data:image/jpeg;base64,{image_b64}"
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
        return flights

    # ── No-Op implementations for ticketing automation pipeline phases ──
    async def select_flight(self, page, flight: dict) -> None:
        pass

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

    async def scrape_onsite_coupons(self, page) -> list[dict]:
        """Scrape coupon codes visible on the Cleartrip checkout screen."""
        from datetime import datetime, timedelta
        import re
        
        js_extractor = """
        () => {
            const coupons = [];
            const cards = Array.from(document.querySelectorAll('.couponItem, .coupon-list-item, .promo-item, .offer-card, [class*="coupon"], [class*="promo"]'));
            
            const seen = new Set();
            const codeRegex = /^[A-Z0-9]{3,15}$/;
            
            for (const card of cards) {
                const text = card.innerText || "";
                let code = "";
                const codeEl = card.querySelector('.couponCode, .promo-code, [class*="code"], strong, b');
                if (codeEl) {
                    code = codeEl.innerText.trim().toUpperCase();
                }
                
                if (!code || !codeRegex.test(code) || code === "APPLY" || code === "REMOVE") {
                    const words = text.split(/\\s+/);
                    for (const w of words) {
                        const cleanW = w.replace(/[^A-Za-z0-9]/g, '').toUpperCase();
                        if (codeRegex.test(cleanW) && cleanW !== "APPLY" && cleanW !== "REMOVE" && cleanW !== "COUPON" && cleanW !== "PROMO" && cleanW.length >= 3) {
                            code = cleanW;
                            break;
                        }
                    }
                }
                
                if (code && !seen.has(code) && codeRegex.test(code) && code !== "APPLY" && code !== "REMOVE") {
                    seen.add(code);
                    
                    let desc = "";
                    const descEl = card.querySelector('.couponDescription, .promo-desc, [class*="desc"], [class*="detail"]');
                    if (descEl) {
                        desc = descEl.innerText.trim();
                    } else {
                        desc = text.replace(code, "").replace(/\\n/g, " ").trim();
                    }
                    
                    coupons.push({
                        "platform": "cleartrip",
                        "code": code,
                        "description": desc || `Cleartrip checkout promo code ${code}`
                    });
                }
            }
            return coupons;
        }
        """
        try:
            results = await page.evaluate(js_extractor)
            parsed_coupons = []
            today = datetime.now()
            expiry = (today + timedelta(days=60)).strftime("%Y-%m-%d")
            
            for c in results:
                desc = c["description"]
                code = c["code"]
                
                discount_type = "FLAT"
                discount_value = 100.0
                min_booking_value = 0.0
                bank_restriction = None
                card_type = "ANY"
                
                pct_match = re.search(r'(\d+)\s*%', desc)
                if pct_match:
                    discount_type = "PERCENT"
                    discount_value = float(pct_match.group(1))
                else:
                    flat_match = re.search(r'(?:Rs\.?|₹|Rs)\s*(\d+[\d,]*)', desc, re.IGNORECASE)
                    if flat_match:
                        discount_type = "FLAT"
                        discount_value = float(flat_match.group(1).replace(",", ""))
                
                min_match = re.search(r'(?:min(?:imum)?\b.*?|above\s+|spend\s+)(?:Rs\.?|₹|Rs)?\s*(\d+[\d,]*)', desc, re.IGNORECASE)
                if min_match:
                    min_booking_value = float(min_match.group(1).replace(",", ""))
                    
                known_banks = ["HDFC", "ICICI", "SBI", "AXIS", "HSBC", "KOTAK", "CITI", "YES", "BOB"]
                for b in known_banks:
                    if re.search(r'\b' + b + r'\b', desc, re.IGNORECASE):
                        bank_restriction = b
                        break
                        
                if re.search(r'\bcredit\b', desc, re.IGNORECASE):
                    card_type = "CREDIT"
                elif re.search(r'\bdebit\b', desc, re.IGNORECASE):
                    card_type = "DEBIT"
                    
                parsed_coupons.append({
                    "platform": "cleartrip",
                    "code": code,
                    "description": desc,
                    "bank_restriction": bank_restriction,
                    "card_type": card_type,
                    "discount_type": discount_type,
                    "discount_value": discount_value,
                    "min_booking_value": min_booking_value,
                    "valid_from": today.strftime("%Y-%m-%d"),
                    "valid_until": expiry,
                    "is_active": 1,
                    "source": "scraped",
                    "source_type": "platform_native",
                    "trust_score": 0.95
                })
            return parsed_coupons
        except Exception as e:
            logger.warning(f"[CleartripWorker] Failed to scrape onsite coupons: {e}")
            return []
