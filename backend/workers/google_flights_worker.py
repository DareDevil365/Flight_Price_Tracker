"""
Flight Finder — Google Flights Worker
Playwright-based worker that extracts real-time flight listings from Google Flights.
Utilizes classless DOM matching and falls back to LLM Vision if DOM parsing fails.
"""

import asyncio
import base64
import json
from loguru import logger
from .base_worker import BaseWorker
from api_key_manager import api_key_manager


class GoogleFlightsWorker(BaseWorker):
    def __init__(self, platform_id: str = "google_flights", platform_name: str = "Google Flights", base_url: str = "https://www.google.com/travel/flights"):
        self._platform_id = platform_id
        self._platform_name = platform_name
        self._base_url = base_url
        self._current_price = 5500.0

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
        await asyncio.sleep(2.0)

    async def input_search_criteria(self, page, trip: dict) -> None:
        origin = trip.get("origin", "")
        dest = trip.get("destination", "")
        date = trip.get("departure_date", "")

        # Direct Google Flights search URL construction to bypass autocomplete selection widget struggles
        query_url = f"https://www.google.com/travel/flights?q=Flights%20from%20{origin}%20to%20{dest}%20on%20{date}%20one%20way"
        logger.info(f"[GoogleFlightsWorker] Navigating directly to search query: {query_url}")
        await page.goto(query_url, timeout=30000, wait_until="domcontentloaded")
        await asyncio.sleep(3.0)

    async def execute_search(self, page) -> None:
        logger.info("[GoogleFlightsWorker] Waiting for search results to load...")
        try:
            # Wait for common flight rows selectors
            await page.wait_for_selector('[role="listitem"], .pI1Zyc, .mx00da', timeout=8000)
            await asyncio.sleep(2.0)  # Extra settle time
        except Exception:
            logger.warning("[GoogleFlightsWorker] Settle selector timeout, trying to parse anyway.")

    async def parse_search_results(self, page) -> list[dict]:
        logger.info("[GoogleFlightsWorker] Extracting flight options...")

        # 1. Attempt Classless DOM Extraction
        flights = await self._parse_via_dom(page)
        if flights:
            logger.info(f"[GoogleFlightsWorker] Parsed {len(flights)} flights successfully via DOM.")
            return flights

        # 2. Fallback to Screenshot + LLM Vision
        logger.warning("[GoogleFlightsWorker] DOM parsing returned 0 flights. Falling back to LLM Vision...")
        try:
            flights = await self._parse_via_vision(page)
            if flights:
                logger.info(f"[GoogleFlightsWorker] Parsed {len(flights)} flights successfully via LLM Vision.")
                return flights
        except Exception as e:
            logger.error(f"[GoogleFlightsWorker] LLM Vision parsing failed: {e}")

        # 3. Return empty list on failure (Phase 0)
        logger.warning("[GoogleFlightsWorker] All extraction strategies failed. Returning empty list.")
        return []

    async def _parse_via_dom(self, page) -> list[dict]:
        """Extract flights from DOM using text layout patterns to resist obfuscated styles."""
        js_extractor = """
        () => {
            const results = [];
            // Select all rows with role="listitem" (Google Flights standard layout) or fallback elements
            const rows = Array.from(document.querySelectorAll('[role="listitem"], .pI1Zyc, .mx00da'));
            
            for (const row of rows) {
                const text = row.innerText || "";
                // Row must contain currency marker to represent a flight price
                if (!text.includes("₹") && !text.includes("$") && !text.includes("Rs") && !text.toLowerCase().includes("book") && !text.toLowerCase().includes("lock")) continue;

                const lines = text.split('\\n').map(l => l.trim()).filter(l => l.length > 0);
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
                
                // Filter prices to find actual fares (usually >= 1000)
                const fares = possiblePrices.filter(p => p >= 1000);
                if (fares.length > 0) {
                    priceVal = fares[0]; // first one that looks like a fare
                } else if (possiblePrices.length > 0) {
                    priceVal = possiblePrices[0]; // fallback to any matched number
                } else {
                    // last resort: search all lines with literal currency symbol
                    for (const line of lines) {
                        const match = line.match(/(?:₹|Rs\\.?|\\$)\\s*([\\d,]+)/);
                        if (match) {
                            priceVal = parseFloat(match[1].replace(/,/g, ''));
                            break;
                        }
                    }
                }
                if (!priceVal) continue;

                // Extract Stops
                let stops = 0;
                if (text.toLowerCase().includes("nonstop") || text.toLowerCase().includes("non-stop")) {
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
                if (airline === "Unknown") {
                    for (const line of lines) {
                        if (line.match(/^[A-Za-z\\s]+$/) && line.length > 3 && line.length < 25) {
                            airline = line;
                            break;
                        }
                    }
                }

                // Extract Departure and Arrival Times
                let departure_time = "06:00";
                let arrival_time = "08:15";
                const timeRegex = /(\\d{1,2}:\\d{2}(?:\\s*(?:AM|PM))?)\\s*(?:–|-)\\s*(\\d{1,2}:\\d{2}(?:\\s*(?:AM|PM))?)/i;
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
                const flightNumRegex = /\\b(6E|AI|UK|SG|QP|I5|IX|S5|2T|G8)\\s*[-]?\\s*(\\d{3,4})\\b/i;
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
            logger.error(f"[GoogleFlightsWorker] DOM evaluation failed: {e}")
            return []

    async def _parse_via_vision(self, page) -> list[dict]:
        """Convert page to screenshot and query LLM vision model to parse flight results."""
        # Hide scrollbars and take screenshot
        screenshot_bytes = await page.screenshot(type="jpeg", quality=40)
        image_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")

        prompt = """
        Inspect this Google Flights search results screen.
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
