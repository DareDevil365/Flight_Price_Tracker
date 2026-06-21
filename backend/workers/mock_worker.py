"""
Flight Finder — Mock Worker
A simulator worker that implements the BaseWorker interface. It loads a local, dynamic HTML page
representing 'MockBooking.com' to allow visual validation of the pipeline, screenshots, and handoff.
"""

import asyncio
import random
from loguru import logger
from .base_worker import BaseWorker


class MockWorker(BaseWorker):
    def __init__(self):
        self._current_price = 5500.0
        self._baseline_price = 5500.0
        self._applied_coupon = None

    @property
    def platform_id(self) -> str:
        return "mock"

    @property
    def platform_name(self) -> str:
        return "MockBooking.com"

    @property
    def base_url(self) -> str:
        return "data:text/html,mock"

    @property
    def coupon_selector(self) -> str:
        return "#coupon-input"

    async def navigate_to_search(self, page) -> None:
        logger.info("[MockWorker] Navigating to search homepage...")
        html = """
        <html>
        <head>
            <style>
                body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #0f172a; color: #f8fafc; padding: 40px; margin: 0; }
                .card { background: #1e293b; border-radius: 12px; padding: 24px; max-width: 600px; margin: auto; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); border: 1px solid #334155; }
                h1 { color: #38bdf8; text-align: center; margin-top: 0; }
                .status-badge { display: inline-block; background: #0284c7; padding: 4px 8px; border-radius: 6px; font-size: 12px; font-weight: bold; margin-bottom: 20px; }
                .field { margin-bottom: 15px; }
                label { display: block; font-size: 14px; color: #94a3b8; margin-bottom: 5px; }
                input { width: 100%; padding: 10px; background: #0f172a; border: 1px solid #475569; border-radius: 6px; color: white; box-sizing: border-box; }
                button { background: #38bdf8; color: #0f172a; border: none; padding: 12px 20px; font-weight: bold; border-radius: 6px; width: 100%; cursor: pointer; margin-top: 15px; transition: background 0.2s; }
                button:hover { background: #0ea5e9; }
            </style>
        </head>
        <body>
            <div class="card">
                <h1>🛫 MockBooking.com</h1>
                <div class="status-badge" id="status">Phase 1: Search Form</div>
                <div class="field">
                    <label>From</label>
                    <input type="text" id="origin" placeholder="e.g. DEL" value="">
                </div>
                <div class="field">
                    <label>To</label>
                    <input type="text" id="dest" placeholder="e.g. BOM" value="">
                </div>
                <div class="field">
                    <label>Date</label>
                    <input type="text" id="date" value="">
                </div>
                <button id="search-btn">Search Flights 🔍</button>
            </div>
        </body>
        </html>
        """
        await page.set_content(html)
        await asyncio.sleep(1.0)

    async def input_search_criteria(self, page, trip: dict) -> None:
        logger.info(f"[MockWorker] Inputting search criteria: {trip['origin']} -> {trip['destination']}...")
        await page.fill("#origin", trip["origin"])
        await asyncio.sleep(0.5)
        await page.fill("#dest", trip["destination"])
        await asyncio.sleep(0.5)
        await page.fill("#date", trip["departure_date"])
        await asyncio.sleep(0.5)

    async def execute_search(self, page) -> None:
        logger.info("[MockWorker] Clicking search button...")
        await page.click("#search-btn")

        # Load search results page content
        html = """
        <html>
        <head>
            <style>
                body { font-family: 'Segoe UI', sans-serif; background: #0f172a; color: #f8fafc; padding: 40px; margin: 0; }
                .card { background: #1e293b; border-radius: 12px; padding: 24px; max-width: 700px; margin: auto; border: 1px solid #334155; }
                h1 { color: #38bdf8; margin-top: 0; text-align: center; }
                .status-badge { display: inline-block; background: #059669; padding: 4px 8px; border-radius: 6px; font-size: 12px; font-weight: bold; margin-bottom: 20px; }
                .flight-option { display: flex; justify-content: space-between; align-items: center; background: #111827; padding: 15px; border-radius: 8px; margin-bottom: 10px; border: 1px solid #1f2937; }
                .flight-info h3 { margin: 0; color: #f1f5f9; }
                .flight-info p { margin: 5px 0 0 0; color: #94a3b8; font-size: 13px; }
                .price { font-size: 18px; font-weight: bold; color: #10b981; }
                button { background: #10b981; color: white; border: none; padding: 8px 16px; font-weight: bold; border-radius: 6px; cursor: pointer; }
                button:hover { background: #059669; }
            </style>
        </head>
        <body>
            <div class="card">
                <h1>🛫 MockBooking.com - Search Results</h1>
                <div class="status-badge">Phase 2: Flight Results</div>
                
                <div class="flight-option">
                    <div class="flight-info">
                        <h3>MockAir MB-101 (Direct)</h3>
                        <p>06:00 AM - 08:15 AM | 2h 15m</p>
                    </div>
                    <div>
                        <div class="price">Rs. 5,500</div>
                        <button class="book-btn" onclick="document.body.innerHTML='Selecting...';">Select Flight</button>
                    </div>
                </div>
                
                <div class="flight-option">
                    <div class="flight-info">
                        <h3>MockAir MB-205 (1 Stop)</h3>
                        <p>12:30 PM - 04:45 PM | 4h 15m</p>
                    </div>
                    <div>
                        <div class="price">Rs. 4,800</div>
                        <button class="book-btn">Select Flight</button>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
        await page.set_content(html)
        await asyncio.sleep(1.5)

    async def parse_search_results(self, page) -> list[dict]:
        logger.info("[MockWorker] Parsing flight options...")
        # Return mock results matching what's shown on page
        return [
            {
                "flight_number": "MB-101",
                "airline": "MockAir",
                "departure_time": "06:00",
                "arrival_time": "08:15",
                "duration": "2h 15m",
                "stops": 0,
                "base_price": 5500.0,
                "seats_remaining": 6,
            },
            {
                "flight_number": "MB-205",
                "airline": "MockAir",
                "departure_time": "12:30",
                "arrival_time": "16:45",
                "duration": "4h 15m",
                "stops": 1,
                "base_price": 4800.0,
                "seats_remaining": 12,
            },
        ]

    async def select_flight(self, page, flight: dict) -> None:
        logger.info(f"[MockWorker] Selecting flight {flight['flight_number']}...")
        self._current_price = flight["base_price"]
        self._baseline_price = flight["base_price"]

        html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: 'Segoe UI', sans-serif; background: #0f172a; color: #f8fafc; padding: 40px; margin: 0; }}
                .card {{ background: #1e293b; border-radius: 12px; padding: 24px; max-width: 600px; margin: auto; border: 1px solid #334155; }}
                h1 {{ color: #38bdf8; margin-top: 0; text-align: center; }}
                .status-badge {{ display: inline-block; background: #d97706; padding: 4px 8px; border-radius: 6px; font-size: 12px; font-weight: bold; margin-bottom: 20px; }}
                .field {{ margin-bottom: 15px; }}
                label {{ display: block; font-size: 14px; color: #94a3b8; margin-bottom: 5px; }}
                input {{ width: 100%; padding: 10px; background: #0f172a; border: 1px solid #475569; border-radius: 6px; color: white; box-sizing: border-box; }}
                button {{ background: #d97706; color: white; border: none; padding: 12px 20px; font-weight: bold; border-radius: 6px; width: 100%; cursor: pointer; }}
            </style>
        </head>
        <body>
            <div class="card">
                <h1>🛫 MockBooking.com - Passenger Details</h1>
                <div class="status-badge">Phase 3: Passenger Info</div>
                <div class="field">
                    <label>First Name</label>
                    <input type="text" id="fname" value="">
                </div>
                <div class="field">
                    <label>Last Name</label>
                    <input type="text" id="lname" value="">
                </div>
                <div class="field">
                    <label>Email</label>
                    <input type="email" id="email" value="">
                </div>
                <button id="passenger-btn">Proceed to Add-ons</button>
            </div>
        </body>
        </html>
        """
        await page.set_content(html)
        await asyncio.sleep(1.0)

    async def fill_passenger_details(self, page) -> None:
        logger.info("[MockWorker] Filling dummy passenger details...")
        await page.fill("#fname", "Raj")
        await asyncio.sleep(0.3)
        await page.fill("#lname", "Kumar")
        await asyncio.sleep(0.3)
        await page.fill("#email", "raj.kumar@example.com")
        await asyncio.sleep(0.5)
        await page.click("#passenger-btn")

    async def skip_addons(self, page) -> None:
        logger.info("[MockWorker] Skipping addons...")
        # Simulate simple addon screen
        html = """
        <html>
        <body style="background: #0f172a; color: white; font-family: sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh;">
            <div style="text-align: center;">
                <h2>Add Extras? (Insurance, Meals)</h2>
                <button id="skip-btn" style="padding: 10px 20px; background: #475569; border: none; color: white; border-radius: 6px; cursor: pointer;">Skip & Continue</button>
            </div>
        </body>
        </html>
        """
        await page.set_content(html)
        await asyncio.sleep(0.5)
        await page.click("#skip-btn")

    async def proceed_to_checkout(self, page) -> None:
        logger.info("[MockWorker] Proceeding to checkout...")
        await self._render_checkout_page(page)

    async def _render_checkout_page(self, page, coupon_status=None, coupon_msg="") -> None:
        badge_color = "#dc2626"  # red
        if coupon_status == "valid":
            badge_color = "#16a34a"  # green
        elif coupon_status == "invalid":
            badge_color = "#ea580c"  # orange

        html = f"""
        <html>
        <head>
            <title>Checkout</title>
            <style>
                body {{ font-family: 'Segoe UI', sans-serif; background: #0f172a; color: #f8fafc; padding: 40px; margin: 0; }}
                .card {{ background: #1e293b; border-radius: 12px; padding: 24px; max-width: 500px; margin: auto; border: 1px solid #334155; }}
                h1 {{ color: #38bdf8; margin-top: 0; text-align: center; }}
                .status-badge {{ display: inline-block; background: #7c3aed; padding: 4px 8px; border-radius: 6px; font-size: 12px; font-weight: bold; margin-bottom: 20px; }}
                .price-display {{ font-size: 32px; font-weight: bold; color: #10b981; margin: 20px 0; text-align: center; background: #0f172a; padding: 15px; border-radius: 8px; }}
                .coupon-section {{ margin-top: 20px; border-top: 1px solid #334155; padding-top: 20px; }}
                .input-group {{ display: flex; gap: 10px; margin-bottom: 10px; }}
                input {{ flex: 1; padding: 10px; background: #0f172a; border: 1px solid #475569; border-radius: 6px; color: white; }}
                .apply-btn {{ background: #7c3aed; color: white; border: none; padding: 10px 20px; font-weight: bold; border-radius: 6px; cursor: pointer; }}
                .apply-btn:hover {{ background: #6d28d9; }}
                .msg {{ padding: 10px; border-radius: 6px; font-size: 13px; margin-top: 10px; display: none; }}
                .msg-valid {{ background: rgba(22, 163, 74, 0.2); border: 1px solid #22c55e; color: #4ade80; display: block; }}
                .msg-invalid {{ background: rgba(220, 38, 38, 0.2); border: 1px solid #ef4444; color: #f87171; display: block; }}
            </style>
        </head>
        <body>
            <div class="card">
                <h1>🛬 MockBooking.com - Checkout</h1>
                <div class="status-badge">Phase 4: Checkout</div>
                
                <div class="price-display" id="total-price">
                    Rs. {self._current_price:,.2f}
                </div>
                
                <div class="coupon-section">
                    <label style="margin-bottom: 8px; display: block;">Have a Promo Code?</label>
                    <div class="input-group">
                        <input type="text" id="coupon-input" value="{self._applied_coupon or ''}" placeholder="Enter code">
                        <button class="apply-btn" id="apply-btn">Apply</button>
                    </div>
                    {f'<div class="msg {"msg-valid" if coupon_status == "valid" else "msg-invalid"}">{coupon_msg}</div>' if coupon_status else ''}
                </div>
                
                <div style="margin-top: 25px; font-size: 11px; color: #64748b; text-align: center;">
                    Secure handoff target. App will transfer window focus here.
                </div>
            </div>
        </body>
        </html>
        """
        await page.set_content(html)
        await asyncio.sleep(0.5)

    async def is_at_checkout(self, page) -> bool:
        title = await page.title()
        return "Checkout" in title

    async def parse_current_price(self, page) -> float:
        return self._current_price

    async def enter_coupon_code(self, page, code: str) -> None:
        logger.info(f"[MockWorker] Entering coupon code: {code}...")
        await page.fill("#coupon-input", code)
        self._applied_coupon = code

    async def click_apply_coupon(self, page) -> None:
        logger.info("[MockWorker] Clicking apply coupon...")
        # Simulate processing coupon logic
        code = self._applied_coupon.upper() if self._applied_coupon else ""

        if code == "MOCK100":
            self._current_price = 5400.0
            await self._render_checkout_page(page, "valid", "Coupon MOCK100 applied successfully! Rs. 100 off.")
        elif code == "MOCKSBI":
            self._current_price = 5000.0
            await self._render_checkout_page(page, "valid", "Valid SBI Card offer: Rs. 500 discount applied.")
        elif code == "MOCKHDFC":
            self._current_price = 4700.0
            await self._render_checkout_page(page, "valid", "Valid HDFC Card offer: Rs. 800 discount applied.")
        elif code == "MOCKICICI":
            self._current_price = 4900.0
            await self._render_checkout_page(page, "valid", "Valid ICICI Debit offer: Rs. 600 discount applied.")
        elif code == "MOCKEMI":
            self._current_price = 5100.0
            await self._render_checkout_page(page, "valid", "EMI Offer: Rs. 400 off. Requires SBI credit card EMI transaction.")
        else:
            await self._render_checkout_page(page, "invalid", f"Coupon {code} is invalid or expired.")

    async def check_coupon_applied(self, page) -> dict:
        code = self._applied_coupon.upper() if self._applied_coupon else ""
        valid_codes = ["MOCK100", "MOCKSBI", "MOCKHDFC", "MOCKICICI", "MOCKEMI"]
        if code in valid_codes:
            return {"success": True, "error": None}
        return {"success": False, "error": "Invalid promo code"}

    async def get_coupon_validation_text(self, page) -> str:
        code = self._applied_coupon.upper() if self._applied_coupon else ""
        if code == "MOCKSBI":
            return "Requires SBI credit card payment."
        if code == "MOCKHDFC":
            return "Requires HDFC credit card payment."
        if code == "MOCKICICI":
            return "Requires ICICI debit card payment."
        if code == "MOCKEMI":
            return "Requires SBI Credit Card EMI transaction."
        return ""

    async def clear_coupon_field(self, page) -> None:
        logger.info("[MockWorker] Clearing coupon field...")
        # Reset price to baseline if clearing
        self._current_price = self._baseline_price
        self._applied_coupon = None
        await self._render_checkout_page(page)

    async def detect_captcha(self, page) -> bool:
        return False

    async def health_check(self, page) -> bool:
        return True
