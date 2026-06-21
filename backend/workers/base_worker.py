"""
Flight Finder — Base Worker
Defines the abstract interface that all platform-specific scraper workers must implement.
"""

import asyncio
from abc import ABC, abstractmethod
from loguru import logger


class BaseWorker(ABC):
    """Abstract base class for all platform-specific flight workers."""

    @property
    @abstractmethod
    def platform_id(self) -> str:
        """Unique lower-case identifier, e.g. 'makemytrip'."""
        pass

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """User-friendly name, e.g. 'MakeMyTrip'."""
        pass

    @property
    @abstractmethod
    def base_url(self) -> str:
        """Homepage URL of the ticketing portal."""
        pass

    @property
    @abstractmethod
    def coupon_selector(self) -> str:
        """CSS selector of the coupon code text field on the checkout screen."""
        pass

    # ── Search Phase ──

    @abstractmethod
    async def navigate_to_search(self, page) -> None:
        """Load homepage or flight search page."""
        pass

    @abstractmethod
    async def input_search_criteria(self, page, trip: dict) -> None:
        """Fill in origin, destination, date, passengers, and class of travel."""
        pass

    @abstractmethod
    async def execute_search(self, page) -> None:
        """Click the Search button and wait for results page to load."""
        pass

    @abstractmethod
    async def parse_search_results(self, page) -> list[dict]:
        """
        Parse flight listings from search results page.
        Returns a list of dicts: [
            {
                'flight_number': '6E-2341',
                'airline': 'IndiGo',
                'departure_time': '06:15',
                'arrival_time': '08:25',
                'duration': '2h 10m',
                'stops': 0,
                'base_price': 5200.0,
            }, ...
        ]
        """
        pass

    @abstractmethod
    async def select_flight(self, page, flight: dict) -> None:
        """Select specific flight and proceed to passenger page."""
        pass

    # ── Passenger Details Phase ──

    @abstractmethod
    async def fill_passenger_details(self, page) -> None:
        """Fill in dummy passenger name, email, phone number."""
        pass

    @abstractmethod
    async def skip_addons(self, page) -> None:
        """Decline add-on upsells (insurance, meals, seats)."""
        pass

    @abstractmethod
    async def proceed_to_checkout(self, page) -> None:
        """Advance from passenger screen to final checkout payment screen."""
        pass

    # ── Checkout Phase ──

    @abstractmethod
    async def is_at_checkout(self, page) -> bool:
        """Verify that the browser is currently at the checkout page."""
        pass

    async def parse_current_price(self, page) -> float:
        """Scrape the active total checkout price (including taxes/fees)."""
        js_extractor = """
        () => {
            const priceRegex = /(?:₹|Rs\.?|\$)\s*([\d,]+)/;
            const selectors = [
                '.total-amount', '.totalAmount', '.grand-total', '.grandTotal',
                '#totalAmount', '#grandTotal', '.payable-amount', '.payableAmount',
                '[class*="totalAmount"]', '[class*="grandTotal"]', '[class*="payable"]',
                '.price-summary-total', '.fare-summary-total', '.totalPayable', '.netPayable'
            ];
            for (const selector of selectors) {
                const elements = document.querySelectorAll(selector);
                for (const el of elements) {
                    const text = el.innerText || "";
                    const match = text.match(priceRegex);
                    if (match) {
                        return parseFloat(match[1].replace(/,/g, ''));
                    }
                }
            }
            const bodyText = document.body.innerText || "";
            const matches = bodyText.match(/(?:Total Payable|Grand Total|Total Amount|Amount Payable|Net Payable)[^\n\d]*(?:₹|Rs\.?|\$)\s*([\d,]+)/i);
            if (matches) {
                return parseFloat(matches[1].replace(/,/g, ''));
            }
            return null;
        }
        """
        try:
            price = await page.evaluate(js_extractor)
            if price is not None:
                self._current_price = float(price)
                return self._current_price
        except Exception as e:
            logger.error(f"[{self.platform_name}] Failed to parse current checkout price: {e}")
        return self._current_price

    async def enter_coupon_code(self, page, code: str) -> None:
        """Type coupon code into input field using JS helper to locate it, with fallback."""
        try:
            logger.info(f"[{self.platform_name}] Entering coupon code: {code}")
            
            # Find the input element using custom JS evaluation
            js_find_input = """
            () => {
                const inputs = Array.from(document.querySelectorAll('input[type="text"], input:not([type])'));
                for (const input of inputs) {
                    const placeholder = (input.placeholder || "").toLowerCase();
                    const id = (input.id || "").toLowerCase();
                    const className = (input.className || "").toLowerCase();
                    const name = (input.name || "").toLowerCase();
                    
                    if (placeholder.includes('coupon') || placeholder.includes('promo') || placeholder.includes('offer') || placeholder.includes('deal') ||
                        id.includes('coupon') || id.includes('promo') ||
                        className.includes('coupon') || className.includes('promo') ||
                        name.includes('coupon') || name.includes('promo')) {
                        const rect = input.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0) {
                            return input;
                        }
                    }
                }
                return null;
            }
            """
            
            # Try to get the input element using JS, or fall back to self.coupon_selector
            input_found = False
            for selector in [self.coupon_selector, "input[placeholder*='promo' i]", "input[placeholder*='coupon' i]", "#promoCode", "#couponCode", "#coupon", "#promo"]:
                if selector:
                    try:
                        el = await page.query_selector(selector)
                        if el and await el.is_visible():
                            await el.click()
                            await el.fill("")
                            await page.keyboard.type(code, delay=100)
                            input_found = True
                            break
                    except Exception:
                        continue
            
            if not input_found:
                # Use JS finder
                await page.evaluate(f"""
                    () => {{
                        const findInput = {js_find_input};
                        const input = findInput();
                        if (input) {{
                            input.focus();
                            input.value = '{code}';
                            input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        }}
                    }}
                """)
                # Let playwright click & type to trigger event listeners
                el_handle = await page.evaluate_handle(js_find_input)
                if el_handle and el_handle.as_element():
                    await el_handle.as_element().click()
                    await el_handle.as_element().fill("")
                    await page.keyboard.type(code, delay=100)
                    input_found = True
                
            if not input_found:
                logger.warning(f"[{self.platform_name}] Coupon input field not found on page.")
        except Exception as e:
            logger.error(f"[{self.platform_name}] Error entering coupon: {e}")

    async def click_apply_coupon(self, page) -> None:
        """Click the apply button near the coupon input."""
        try:
            logger.info(f"[{self.platform_name}] Clicking apply coupon...")
            
            # JS helper to find Apply button
            js_find_button = """
            () => {
                const findInput = () => {
                    const inputs = Array.from(document.querySelectorAll('input[type="text"], input:not([type])'));
                    for (const input of inputs) {
                        const placeholder = (input.placeholder || "").toLowerCase();
                        const id = (input.id || "").toLowerCase();
                        const className = (input.className || "").toLowerCase();
                        const name = (input.name || "").toLowerCase();
                        if (placeholder.includes('coupon') || placeholder.includes('promo') || placeholder.includes('offer') || placeholder.includes('deal') ||
                            id.includes('coupon') || id.includes('promo') ||
                            className.includes('coupon') || className.includes('promo')) {
                            const rect = input.getBoundingClientRect();
                            if (rect.width > 0 && rect.height > 0) return input;
                        }
                    }
                    return null;
                };
                
                const input = findInput();
                if (input) {
                    let parent = input.parentElement;
                    for (let depth = 0; depth < 4 && parent; depth++) {
                        const clickables = Array.from(parent.querySelectorAll('button, a, [role="button"], input[type="button"], input[type="submit"], span'));
                        for (const el of clickables) {
                            const text = (el.innerText || el.value || "").trim().toLowerCase();
                            if (text === 'apply' || text === 'apply coupon' || text === 'submit' || el.id.toLowerCase().includes('apply') || el.className.toLowerCase().includes('apply')) {
                                const rect = el.getBoundingClientRect();
                                if (rect.width > 0 && rect.height > 0) return el;
                            }
                        }
                        parent = parent.parentElement;
                    }
                }
                
                const allButtons = Array.from(document.querySelectorAll('button, .apply-btn, [class*="apply" i]'));
                for (const btn of allButtons) {
                    const text = (btn.innerText || "").trim().toLowerCase();
                    if (text.includes('apply')) {
                        const rect = btn.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0) return btn;
                    }
                }
                return null;
            }
            """
            
            btn_handle = await page.evaluate_handle(js_find_button)
            if btn_handle and btn_handle.as_element():
                await btn_handle.as_element().click()
                await asyncio.sleep(2.0)
            else:
                selectors = [
                    "button:has-text('Apply')", "button:has-text('APPLY')",
                    ".apply-btn", "#apply-btn", "input[value='Apply']"
                ]
                button_clicked = False
                for sel in selectors:
                    try:
                        btn = await page.query_selector(sel)
                        if btn and await btn.is_visible():
                            await btn.click()
                            button_clicked = True
                            await asyncio.sleep(2.0)
                            break
                    except Exception:
                        continue
                if not button_clicked:
                    logger.warning(f"[{self.platform_name}] Apply button not found near coupon field.")
        except Exception as e:
            logger.error(f"[{self.platform_name}] Error clicking apply: {e}")

    async def check_coupon_applied(self, page) -> dict:
        """Check if coupon succeeded or failed, parsing validation errors."""
        try:
            js_check = """
            () => {
                const errorKeywords = [
                    'applicable on yatra app only', 'app only', 'invalid', 'expired', 'cannot be applied', 
                    'not valid', 'not applicable', 'code not found', 'error', 'only on app', 'only on android', 
                    'only on ios', 'coupon is not valid', 'enter a valid'
                ];
                const successKeywords = [
                    'applied successfully', 'saved', 'congratulations', 'coupon applied', 'offer applied', 'valid on'
                ];
                
                const divAndSpans = Array.from(document.querySelectorAll('div, span, p, label, .error, .warning, .message, [class*="error" i], [class*="message" i]'));
                
                for (const el of divAndSpans) {
                    const text = (el.innerText || "").trim().toLowerCase();
                    if (text.length === 0 || text.length > 250) continue;
                    
                    for (const kw of errorKeywords) {
                        if (text.includes(kw)) {
                            const rect = el.getBoundingClientRect();
                            if (rect.width > 0 && rect.height > 0) {
                                return { success: false, error: el.innerText.trim() };
                            }
                        }
                    }
                }
                
                for (const el of divAndSpans) {
                    const text = (el.innerText || "").trim().toLowerCase();
                    if (text.length === 0 || text.length > 250) continue;
                    
                    for (const kw of successKeywords) {
                        if (text.includes(kw)) {
                            const rect = el.getBoundingClientRect();
                            if (rect.width > 0 && rect.height > 0) {
                                return { success: true, error: null };
                            }
                        }
                    }
                }
                
                return null;
            }
            """
            res = await page.evaluate(js_check)
            if res:
                return res
            return {"success": True, "error": None}
        except Exception as e:
            logger.error(f"[{self.platform_name}] Error checking coupon applied: {e}")
            return {"success": True, "error": None}

    async def get_coupon_validation_text(self, page) -> str:
        """Get restriction warning text displayed on screen, if any."""
        try:
            js_text = """
            () => {
                const divAndSpans = Array.from(document.querySelectorAll('div, span, p, label, .error, .warning, .message, [class*="error" i], [class*="message" i], [class*="warning" i]'));
                for (const el of divAndSpans) {
                    const text = (el.innerText || "").trim().toLowerCase();
                    if (text.length > 0 && text.length < 250) {
                        if (text.includes('sbi') || text.includes('hdfc') || text.includes('icici') || 
                            text.includes('axis') || text.includes('card') || text.includes('valid only') ||
                            text.includes('app only') || text.includes('interest') || text.includes('emi')) {
                            const rect = el.getBoundingClientRect();
                            if (rect.width > 0 && rect.height > 0) {
                                return el.innerText.trim();
                            }
                        }
                    }
                }
                return "";
            }
            """
            return await page.evaluate(js_text) or ""
        except Exception:
            return ""

    async def clear_coupon_field(self, page) -> None:
        """Remove coupon code from input field (or click 'Remove' button)."""
        try:
            logger.info(f"[{self.platform_name}] Clearing coupon field...")
            js_find_remove = """
            () => {
                const elements = Array.from(document.querySelectorAll('button, a, [role="button"], span, div'));
                for (const el of elements) {
                    const text = (el.innerText || "").trim().toLowerCase();
                    if (text === 'remove' || text === 'remove coupon' || text === 'change coupon' || text === 'cancel' || el.className.toLowerCase().includes('remove-coupon') || el.id.toLowerCase().includes('remove-coupon')) {
                        const rect = el.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0) return el;
                    }
                }
                return null;
            }
            """
            
            remove_btn = await page.evaluate_handle(js_find_remove)
            if remove_btn and remove_btn.as_element():
                await remove_btn.as_element().click()
                await asyncio.sleep(2.0)
            else:
                js_clear_input = """
                () => {
                    const inputs = Array.from(document.querySelectorAll('input[type="text"], input:not([type])'));
                    for (const input of inputs) {
                        const placeholder = (input.placeholder || "").toLowerCase();
                        if (placeholder.includes('coupon') || placeholder.includes('promo') || placeholder.includes('offer')) {
                            input.focus();
                            input.value = '';
                            input.dispatchEvent(new Event('input', { bubbles: true }));
                            input.dispatchEvent(new Event('change', { bubbles: true }));
                        }
                    }
                }
                """
                await page.evaluate(js_clear_input)
                if self.coupon_selector:
                    try:
                        el = await page.query_selector(self.coupon_selector)
                        if el:
                            await el.fill("")
                    except Exception:
                        pass
        except Exception as e:
            logger.error(f"[{self.platform_name}] Error clearing coupon: {e}")

    # ── Utilities ──

    @abstractmethod
    async def detect_captcha(self, page) -> bool:
        """Check if CAPTCHA challenge is currently displayed on screen."""
        pass

    @abstractmethod
    async def health_check(self, page) -> bool:
        """Check if page structure / main selectors are still valid."""
        pass

    async def scrape_onsite_coupons(self, page) -> list[dict]:
        """
        Scrape native coupon codes offered natively on the platform's booking screens.
        Returns empty list by default; platform workers can override this.
        """
        return []
