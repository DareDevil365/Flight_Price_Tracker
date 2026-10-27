"""
Flight Finder â€” Base Worker
Defines the abstract interface that all platform-specific scraper workers must implement.
"""

import asyncio
import re
import weakref
from urllib.parse import urlsplit
from abc import ABC, abstractmethod
from loguru import logger


def _number(value):
    return re.sub(r'[\s-]','',value).upper() if isinstance(value,str) else ''


def _same_listing(expected, current):
    """Reidentify an itinerary, independent of list position or current fare."""
    for key in ('airline','departure_time','arrival_time','stops'):
        value=expected.get(key)
        if value is None or value=='' or isinstance(value,bool):
            return False
        if key=='airline':
            if not isinstance(value,str) or re.sub(r'\s+','',value).casefold()!=re.sub(r'\s+','',str(current.get(key,''))).casefold():
                return False
        elif isinstance(current.get(key),bool) or current.get(key)!=value:
            return False
    if expected.get('flight_number') and _number(expected['flight_number'])!=_number(current.get('flight_number')):
        return False
    for key in ('origin','destination','departure_date','passenger_count','cabin_class','currency'):
        if expected.get(key) is not None and current.get(key)!=expected[key]:
            return False
    if expected.get('connection_airports') and current.get('connection_airports')!=expected['connection_airports']:
        return False
    segments=expected.get('segments')
    if segments:
        actual=current.get('segments')
        if not isinstance(segments,list) or not isinstance(actual,list) or len(segments)!=len(actual):
            return False
        for wanted,found in zip(segments,actual):
            if not isinstance(wanted,dict) or not isinstance(found,dict):
                return False
            for key in ('origin','destination','flight_number','departure_time','arrival_time'):
                if not wanted.get(key):
                    return False
                if (_number(wanted[key]) if key=='flight_number' else wanted[key]) != (_number(found.get(key)) if key=='flight_number' else found.get(key)):
                    return False
            for key in ('departure_date','arrival_date','departure_terminal','arrival_terminal'):
                if wanted.get(key) is not None and found.get(key)!=wanted[key]:
                    return False
    return True


class BaseWorker(ABC):
    """Abstract base class for all platform-specific flight workers."""

    def is_provider_page(self,page):
        """A matching total on an unrelated popup is not merchant evidence."""
        from urllib.parse import urlsplit
        address=urlsplit(page.url)
        domain=(urlsplit(self.base_url).hostname or '').lower().removeprefix('www.')
        host=(address.hostname or '').lower()
        return bool(domain and address.scheme=='https' and (host==domain or host.endswith('.'+domain)))

    def attach_response_listener(self, page):
        # Removing an unregistered callback raises KeyError when another observer
        # (diagnostics, tracing) is present. Attach once without disturbing it.
        pages=getattr(self, '_response_pages', None)
        if pages is None:
            self._response_pages=pages=weakref.WeakSet()
        if page not in pages:
            page.on('response', self._response_handler)
            pages.add(page)
        contexts=getattr(self,'_response_contexts',None)
        if contexts is None:
            self._response_contexts=contexts=weakref.WeakSet()
        if page.context not in contexts:
            domain=(urlsplit(self.base_url).hostname or '').lower().removeprefix('www.')
            context_ref=weakref.ref(page.context)
            self._failure_context_ref=context_ref
            self._http_failures=[]
            def observe(response):
                address=urlsplit(response.url)
                host=(address.hostname or '').lower()
                if context_ref()!=getattr(self,'_failure_context_ref',lambda:None)():
                    return
                if domain and address.scheme=='https' and (host==domain or host.endswith('.'+domain)) and response.status>=400:
                    failures=getattr(self,'_http_failures',[])
                    self._http_failures=(failures+[(address.path,response.status)])[-30:]
            page.context.on('response',observe)
            contexts.add(page.context)

    async def wait_for_listings(self,page,selectors):
        from provider_status import page_problem
        try:
            await page.wait_for_function(r'''selectors => {
                const text=(document.body?.innerText || '').toLowerCase().trim();
                return [...document.querySelectorAll(selectors)].some(el=>el.getBoundingClientRect().width>0)
                    || /network problem|unable to connect to our systems|server error|access denied|no flights found|no flights available/.test(text)
                    || text==='200-ok' || text==='200 ok';
            }''',arg=selectors,timeout=25000)
        except __import__('playwright.async_api',fromlist=['TimeoutError']).TimeoutError:
            pass
        problem=page_problem(await page.inner_text('body'),page.url,getattr(self,'_http_failures',[]))
        if problem:
            raise problem

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

    # â”€â”€ Search Phase â”€â”€

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

    async def select_flight(self, page, flight: dict) -> None:
        if not self.is_provider_page(page):
            raise ValueError('Could not select a flight on an unrelated provider page')
        # Cached selectors describe positions, not identity. Re-read the current
        # listing even when a selector was supplied, and require one exact match.
        cards = await self._parse_via_dom(page)
        matches=[row for row in cards if _same_listing(flight,row)]
        if len(matches)!=1:
            raise ValueError('Could not uniquely identify this exact flight card for checkout')
        selector=matches[0].get('selector')
        if not selector:
            raise ValueError('Could not identify this exact flight card for checkout')
        card = page.locator(selector)
        if await card.count()!=1 or not await card.is_visible():
            raise ValueError('Selected flight card is missing or ambiguous')
        button = card.get_by_role('button',name=re.compile('book|select|view fare',re.I))
        if await button.count()==1:
            control=button
        elif await button.count()>1:
            raise ValueError('Booking control is ambiguous on the selected flight card')
        else:
            link = card.locator('a:visible, button:visible, [role="button"]:visible').filter(has_text=re.compile('book|select|view fare',re.I))
            if await link.count()!=1:
                raise ValueError('Booking control missing on the selected flight card')
            control=link
        # Bind the element so a reordering during Playwright's actionability
        # checks cannot silently redirect this click to another nth selector.
        handle=await control.element_handle()
        if handle is None:
            raise ValueError('Booking control disappeared before selection')
        try:
            await handle.click(timeout=8000)
        finally:
            await handle.dispose()
        await page.wait_for_timeout(2000)
        # Fare-family controls are provider-specific. A global Book Now search
        # can select a different flight elsewhere on the listing page.


    # â”€â”€ Passenger Details Phase â”€â”€

    @abstractmethod
    async def fill_passenger_details(self, page) -> None:
        """Reserved for user-assisted passenger entry; never invent identity."""
        pass

    @abstractmethod
    async def skip_addons(self, page) -> None:
        """Decline add-on upsells (insurance, meals, seats)."""
        pass

    @abstractmethod
    async def proceed_to_checkout(self, page) -> None:
        """Advance from passenger screen to final checkout payment screen."""
        pass

    # â”€â”€ Checkout Phase â”€â”€

    @abstractmethod
    async def is_at_checkout(self, page) -> bool:
        text = (await page.inner_text('body')).lower()
        has_payment = any(marker in text for marker in ('payment method', 'select payment', 'pay securely', 'payment options', 'choose payment'))
        return has_payment and bool(await self.read_checkout_total(page))


    async def parse_current_price(self, page) -> float:
        data = await self.read_checkout_total(page)
        if not data or not data.get('total'):
            raise ValueError('Could not read a final payable INR total; refusing a fallback price')
        return data['total']

    async def read_cart_options(self, page):
        """Only selected add-on/fare labels; never inspect passenger/card inputs."""
        return await page.evaluate(r'''() => {
            const options=[];
            for (const el of document.querySelectorAll('input[type=checkbox],input[type=radio],[role=checkbox],[role=radio],select')) {
                const parent=el.closest('label') || el.parentElement;
                if (!parent?.getBoundingClientRect().width) continue;
                const label=[el.name,el.id,el.getAttribute('aria-label'),parent.innerText].join(' ');
                if (!/baggage|insurance|meal|seat|fare.family|protection/i.test(label)
                    || /coupon|promo|payment|credit|debit|upi/i.test(label)) continue;
                const selected=el.tagName==='SELECT' ? el.selectedOptions[0]?.textContent : (el.checked || el.getAttribute('aria-checked')==='true');
                options.push({label:label.replace(/\s+/g,' ').slice(0,160),selected});
            }
            return options.sort((a,b)=>a.label.localeCompare(b.label));
        }''')

    async def read_selected_itinerary_text(self, page):
        """Read one explicitly named, visible selected itinerary, never body text.

        Unknown merchant layouts fail closed. This is a semantic contract; a
        provider adapter may implement its own equivalently scoped reader.
        """
        from page_inspection import DOM_HELPERS
        return await page.evaluate('() => {'+DOM_HELPERS+r'''
            const regions=[...document.querySelectorAll('section,[role="region"]')];
            const name=el => {
                const explicit=el.getAttribute('aria-label');
                if (explicit) return clean(explicit);
                const ids=(el.getAttribute('aria-labelledby') || '').split(/\s+/).filter(Boolean);
                if (ids.length) return clean(ids.map(id=>document.getElementById(id)?.innerText || '').join(' '));
                const headings=[...el.querySelectorAll('h1,h2,h3,h4,h5,h6,[role="heading"]')]
                    .filter(h=>visible(h) && h.closest('section,[role="region"]')===el);
                return headings.length===1 ? clean(headings[0].innerText) : '';
            };
            const recommendations=el => {
                for (let parent=el;parent && parent!==document.body;parent=parent.parentElement) {
                    if (parent.matches('aside,nav,[role="complementary"],[class*="recommend" i],[id*="recommend" i]')) return true;
                    if (parent.matches('section,[role="region"]') && /recommend|alternative|similar flights?|other flights?/i.test(name(parent))) return true;
                }
                return false;
            };
            const selected=regions.filter(el=>visible(el) && !recommendations(el)
                && /^(?:flight itinerary|selected flight|booking summary|trip summary)$/i.test(name(el)));
            if (selected.length!==1) return null;
            const root=selected[0],walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);
            const text=[];let node,visited=0;
            while ((node=walker.nextNode())) {
                if (++visited>2000) return null;
                const parent=node.parentElement;
                if (!visible(parent) || recommendations(parent)
                    || parent.closest('script,style,template,input,textarea,select,[contenteditable="true"]')) continue;
                text.push(node.textContent);
            }
            const rendered=text.join(' ').replace(/\s+/g,' ').trim();
            return rendered && rendered.length<=6000 ? rendered : null;
        }''')

    async def confirm_checkout_flight(self, page, quote):
        """A user can change flights in the handed-off browser; reject stale identity."""
        import re
        selected = await self.read_selected_itinerary_text(page)
        if not isinstance(selected,str) or not selected.strip():
            return False
        raw = selected.upper()
        meta=quote.get('savings_breakdown',{})
        # A first flight number does not establish an entire connection. Each
        # provider needs a scoped segment reader before it may certify those
        # carts. Likewise an upsell's fare/baggage label in body text cannot
        # prove that entitlement is selected in the current cart.
        if type(quote.get('stops')) is not int or quote['stops'] != 0:
            return False
        if any(meta.get(key) not in (None, '', {}, []) for key in ('fare_family','baggage')):
            return False
        if not re.search(r'\b(?:NON[ -]?STOP|NO STOPS?|0 STOPS?)\b',raw):
            return False
        if re.search(r'\b[1-9]\d*\s*STOPS?\b|\bCONNECTING\b|\bLAYOVER\b',raw):
            return False
        airline=quote.get('airline')
        if not isinstance(airline,str) or not airline.strip():
            return False
        if not re.search(r'(?<![A-Z0-9])'+re.escape(airline.strip().upper())+r'(?![A-Z0-9])',raw):
            return False
        origin,destination=meta.get('origin'),meta.get('destination')
        if not origin or not destination or not re.search(r'\b'+re.escape(origin)+r'\b[\s\S]*?\b'+re.escape(destination)+r'\b',raw):
            return False
        number = re.sub(r'[^A-Z0-9]', '', (quote.get('flight_number') or '').upper())
        displayed_numbers={code+digits for code,digits in re.findall(
            r'\b([A-Z][A-Z0-9]|[0-9][A-Z])[\s-]*(\d{1,5})(?![\d:])\b',raw)
            if code not in ('AM','PM')}
        if not number or displayed_numbers!={number}:
            return False
        def expected_time(value):
            if not isinstance(value,str) or not re.fullmatch(r'\d{2}:\d{2}',value):
                return None
            h,m=map(int,value.split(':'))
            if h>23 or m>59:
                return None
            return h,m
        displayed_times=[]
        for hour,minute,period in re.findall(r'(?<!\d)(\d{1,2}):(\d{2})(?:\s*(AM|PM))?(?![\dA-Z])',raw):
            hour,minute=int(hour),int(minute)
            if minute>59 or hour>23 or (period and not 1<=hour<=12):
                return False
            if period:
                hour=hour%12+(12 if period=='PM' else 0)
            displayed_times.append((hour,minute))
        expected_times=[expected_time(quote.get('departure_time')),expected_time(quote.get('arrival_time'))]
        # Two matching clocks elsewhere in this scope must not certify swapped
        # departure/arrival labels or a summary with contradictory schedules.
        matches_time=None not in expected_times and displayed_times==expected_times
        from datetime import date, timedelta
        month_names = ['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC']
        try:
            day = date.fromisoformat(quote['departure_date'])
            displayed_dates=set()
            for y,m,d in re.findall(r'\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b', raw):
                displayed_dates.add(date(int(y),int(m),int(d)))
            for d,m,y in re.findall(r'\b(\d{1,2})[-/](\d{1,2})[-/](20\d{2})\b', raw):
                displayed_dates.add(date(int(y),int(m),int(d)))
            months = '|'.join(month_names)
            tokens = re.findall(r'\b(\d{1,2})[\s,/-]*('+months+r')[A-Z]*(?:[\s,/-]*(20\d{2}))?\b', raw)
            tokens += [(d,m,y) for m,d,y in re.findall(r'\b('+months+r')[A-Z]*[\s,/-]+(\d{1,2})(?:[\s,/-]+(20\d{2}))?\b',raw)]
            for d,m,y in tokens:
                if not y:
                    return False
                displayed_dates.add(date(int(y),month_names.index(m)+1,int(d)))
            allowed_dates={day}
            if matches_time and expected_times[1]<expected_times[0]:
                allowed_dates.add(day+timedelta(days=1))
        except (ValueError,TypeError,KeyError,OverflowError):
            return False
        if day not in displayed_dates or not displayed_dates<=allowed_dates:
            return False
        if number:
            pattern = r'\b' + r'[\s-]*'.join(re.escape(c) for c in number.upper()) + r'\b'
            return bool(re.search(pattern,raw)) and matches_time
        # A schedule/airline resemblance is insufficient to verify a booking.
        # Connecting flights without an aggregate number need a provider-specific
        # exact segment reader before they can qualify here.
        return False

    async def read_checkout_total(self, page) -> dict | None:
        from page_inspection import inspect_page
        async with inspect_page(page) as inspection:
            data=inspection.summary
            totals=data.get('totals',[])
            if len(totals)!=1 or data.get('truncated'):
                return None
            # Reading a row never establishes itinerary, payment or final fees.
            # Dispatcher must still verify the unchanged booking and payment.
            return {'total':totals[0], 'fees':data.get('fees',[]), 'currency':'INR'}

    async def read_selected_payment(self,page):
        """Require a selected method, rather than a page listing payment options."""
        import re
        labels=await page.evaluate(r'''() => {
            const explicit=(document.body.innerText || '').split('\n').filter(line=>/^(?:selected payment(?: method)?|payment method|paying with)\s*[:\-]\s*\S/i.test(line));
            const checked=[...document.querySelectorAll('input[type=radio]:checked,[role=radio][aria-checked=true]')].filter(el=>{
                if (/coupon|promo|rdoCpn/i.test([el.id,el.name,el.getAttribute('ng-click')].join(' ')) || el.closest('.radiocoupns,[id*="Coupon"],[class*="coupon" i]')) return false;
                return (el.closest('label') || el).getBoundingClientRect().width>0;
            }).map(el=>el.closest('label')?.innerText || el.getAttribute('aria-label') || '');
            return [...new Set([...explicit,...checked].filter(Boolean))];
        }''')
        if not isinstance(labels,list) or not labels or len(labels)>10:
            return None
        from offer_parser import BANKS, card_product
        facts=[]
        for text in labels:
            if not isinstance(text,str) or len(text)>500:
                return None
            methods=[name for name,pattern in [('UPI',r'\bUPI\b'),('CREDIT',r'\bcredit\b'),('DEBIT',r'\bdebit\b'),('NET_BANKING',r'net\s*banking'),('WALLET',r'\bwallet\b')] if re.search(pattern,text,re.I)]
            banks=[b for b in BANKS if re.search(r'\b'+re.escape(b)+r'\b',text,re.I)]
            if len(methods)!=1 or len(banks)>1:
                return None
            product=card_product(text)
            extras=[name for name in ('EMI','BNPL','PAY LATER') if re.search(r'\b'+name+r'\b',text,re.I)]
            # Store recognized facts, never card suffixes/account identifiers.
            label=' '.join([methods[0],*banks,*([product[0]] if product else []),*extras])
            facts.append(dict(method=methods[0],banks=banks,label=label))
        # Two selected labels cannot be unioned into a fictional multi-bank card.
        return facts[0] if all(fact==facts[0] for fact in facts) else None

    async def confirm_checkout_passengers_and_cabin(self, page, trip):
        import re
        text = await page.inner_text('body')
        counts = {int(n) for n in re.findall(r'\b(\d+)\s*(?:adults?|travellers?|travelers?|passengers?)\b',text,re.I)}
        counts.update(int(n) for n in re.findall(r'\b(?:adults?|travellers?|travelers?|passengers?)\s*:\s*(\d+)\b',text,re.I))
        counts.update(int(n) for n in re.findall(r'\badults?\s*(?:x|×)\s*(\d+)\b',text,re.I))
        cabins = set()
        for line in text.splitlines():
            match = re.fullmatch(r'\s*(?:(?:cabin|class|cabin class)\s*[:\-]?\s*)?(Premium economy|Economy|Business|First)(?:\s+class)?\s*',line,re.I)
            if match:
                cabins.add(match[1].replace(' ','_').upper())
        return counts == {trip['passenger_count']} and cabins == {trip['cabin_class']}

    async def enter_coupon_code(self, page, code: str) -> None:
        from page_inspection import coupon_control
        await coupon_control(page,'fill',code=code)

    async def get_applied_coupon_code(self,page):
        from page_inspection import DOM_HELPERS
        return await page.evaluate('() => {'+DOM_HELPERS+r'''
            const inputs=couponFields();
            if (inputs.length!==1) return null;
            const code=(inputs[0].value || '').trim().toUpperCase();
            return /^[A-Z0-9_-]{2,40}$/.test(code) ? code : null;
        }''')

    async def click_apply_coupon(self, page) -> None:
        from page_inspection import coupon_control
        await coupon_control(page,'apply')
        await asyncio.sleep(0.5)

    async def coupon_navigation_blocker(self,page):
        # Stop at authentication; never force-click through its overlay.
        selectors='[role="dialog"] input[type="password"],[role="dialog"] input[autocomplete="one-time-code"]'
        if self.platform_id=='easemytrip':
            selectors+=',._newlognsec'
        for element in await page.locator(selectors).all():
            if await element.is_visible():
                return 'A sign-in screen is blocking coupon testing. Complete or dismiss it yourself, then verify again.'
        return None

    async def check_coupon_applied(self, page) -> dict:
        try:
            return await page.evaluate(r"""() => {
                for (const el of document.querySelectorAll('[role="alert"], [class*="coupon" i], [class*="promo" i], [class*="offer" i]')) {
                    const text = (el.innerText||'').trim();
                    if (!el.getBoundingClientRect().width || text.length>250) continue;
                    if (/invalid|expired|not valid|not applicable|cannot be applied|not found|enter a valid/i.test(text)) return {success:false, error:text};
                    if (/coupon applied|offer applied|(?:code|coupon|offer).{0,60}applied successfully|applied successfully.{0,60}(?:code|coupon|offer)/i.test(text)) {
                        const code=text.match(/(?:code|coupon|offer)\s*[:\-]?\s+([A-Z0-9_-]{2,40})\s+(?:has been\s+)?applied\b/i)?.[1];
                        return {success:true,error:null,...(code ? {code:code.toUpperCase()} : {})};
                    }
                }
                return {success:false,error:null};
            }""")
        except Exception:
            return {'success':False, 'error':None}

    async def get_coupon_validation_text(self, page) -> str:
        """Get restriction warning text displayed on screen, if any."""
        try:
            js_text = r"""
            (code) => {
                // Payment navigation labels such as "HDFC credit card" are not
                // coupon restrictions. Read only visible offer/coupon feedback.
                const scopes = [...document.querySelectorAll('[class*="coupon" i], [class*="promo" i], [id*="coupon" i], [id*="promo" i], [role="alert"]')];
                const terms=[];
                for (const el of scopes) {
                    const text=(el.innerText || '').trim();
                    const marker=[el.id,el.className,el.getAttribute('role')].join(' ');
                    const currentCode=code && (el.getAttribute('data-code')===code
                        || new RegExp('\\b'+code+'\\b','i').test(text));
                    const feedback=/message|validation|error|warning|applied|selected|terms/i.test(marker);
                    if (el.getBoundingClientRect().width && text && text.length<=2000
                        && (currentCode || feedback || (el.getAttribute('role')==='alert' && /coupon|promo|offer|code/i.test(text)))
                        && /valid|applicable|eligible|minimum|only|exclud|expires|bank|card|emi|interest|upi/i.test(text)) terms.push(text);
                }
                return [...new Set(terms)].join('\n');
            }
            """
            return await page.evaluate(js_text,await self.get_applied_coupon_code(page)) or ""
        except Exception:
            return ""

    async def clear_coupon_field(self, page) -> None:
        import re
        # Exact coupon-removal actions only. Avoid first-match div/class guesses.
        controls=page.locator('button,a,[role="button"]').filter(
            has_text=re.compile(r'^\s*Remove (?:coupon|promo code|code)\s*$',re.I))
        visible=[control for control in await controls.all() if await control.is_visible()]
        if len(visible)>1:
            raise ValueError('Coupon removal control is ambiguous; no action taken')
        if visible:
            await visible[0].click(timeout=4000)
        from page_inspection import coupon_control
        await coupon_control(page,'clear')

    # â”€â”€ Utilities â”€â”€

    @abstractmethod
    async def detect_captcha(self, page) -> bool:
        text = (await page.inner_text('body')).lower()
        return any(marker in text for marker in ('verify you are human','unusual traffic','access denied','security check','captcha'))


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

    async def fill_input_semantically(self, page, label_name: str, value: str) -> bool:
        """
        Finds an input element associated with label_name and fills it.
        Uses a list of synonyms and parses the DOM.
        """
        logger.info(f"[{self.platform_name}] Semantically filling input for '{label_name}' with '{value}'...")
        js_find_input = r"""
        (labelName) => {
            const labelLower = labelName.toLowerCase();

            // Synonym mapping
            const synonymMap = {
                "first name": ["first name", "given name", "fname", "first_name", "first-name", "name"],
                "last name": ["last name", "family name", "surname", "lname", "last_name", "last-name"],
                "email": ["email", "e-mail", "email address", "email_address", "mail"],
                "phone": ["phone", "mobile", "mobile number", "phone number", "contact", "tel"],
                "gender": ["gender", "sex"]
            };

            const targets = synonymMap[labelLower] || [labelLower];

            // Check placeholders, names, IDs, classes first
            const inputs = Array.from(document.querySelectorAll('input[type="text"], input[type="email"], input[type="tel"], input:not([type])'));
            for (const input of inputs) {
                const id = (input.id || "").toLowerCase();
                const name = (input.name || "").toLowerCase();
                const placeholder = (input.placeholder || "").toLowerCase();
                const className = (input.className || "").toLowerCase();
                const ariaLabel = (input.getAttribute("aria-label") || "").toLowerCase();

                if (targets.some(t => id.includes(t) || name.includes(t) || placeholder.includes(t) || className.includes(t) || ariaLabel.includes(t))) {
                    const rect = input.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {
                        return { selector: "", id: input.id, foundByAttr: true };
                    }
                }
            }

            // Look for labels or text nodes containing target words near inputs
            const labels = Array.from(document.querySelectorAll('label, span, div, p'));
            for (const lbl of labels) {
                const text = (lbl.innerText || "").trim().toLowerCase();
                if (text.length > 0 && text.length < 50 && targets.some(t => text.includes(t))) {
                    if (lbl.tagName.toLowerCase() === 'label' && lbl.htmlFor) {
                        const input = document.getElementById(lbl.htmlFor);
                        if (input) {
                            return { selector: "#" + lbl.htmlFor, id: lbl.htmlFor, foundByLabelFor: true };
                        }
                    }

                    const parent = lbl.parentElement;
                    if (parent) {
                        const input = parent.querySelector('input');
                        if (input) {
                            return { selector: "", id: input.id, foundByParentSibling: true };
                        }
                    }
                }
            }
            return null;
        }
        """
        try:
            res = await page.evaluate(f"({js_find_input})({repr(label_name)})")
            if res:
                selector = res.get("selector")
                input_id = res.get("id")

                if selector:
                    await page.click(selector)
                    await page.fill(selector, "")
                    await page.keyboard.type(value, delay=50)
                    return True
                elif input_id:
                    sel = f"#{input_id}"
                    await page.click(sel)
                    await page.fill(sel, "")
                    await page.keyboard.type(value, delay=50)
                    return True
                else:
                    return False
            else:
                logger.warning(f"[{self.platform_name}] Semantic input field for '{label_name}' not found.")
                return False
        except Exception as e:
            logger.error(f"[{self.platform_name}] Semantic fill failed for '{label_name}': {e}")
            return False

    async def click_button_semantically(self, page, button_label: str) -> bool:
        """
        Finds a clickable element matching button_label and clicks it.
        """
        logger.info(f"[{self.platform_name}] Semantically clicking button '{button_label}'...")
        js_find_button = r"""
        (btnLabel) => {
            const labelLower = btnLabel.toLowerCase();

            // Synonym mapping
            const synonymMap = {
                "skip": ["skip", "no thanks", "no, thanks", "proceed without", "skip & continue", "not now", "continue without"],
                "continue": ["continue", "proceed", "next", "confirm", "go to checkout", "proceed to checkout", "passenger-btn", "skip-btn"],
                "apply": ["apply", "submit", "apply coupon", "verify"]
            };

            const targets = synonymMap[labelLower] || [labelLower];

            const clickables = Array.from(document.querySelectorAll('button, a, [role="button"], input[type="button"], input[type="submit"], span, div'));
            for (const el of clickables) {
                const text = (el.innerText || el.value || "").trim().toLowerCase();
                const id = (el.id || "").toLowerCase();
                const className = (el.className || "").toLowerCase();

                if (text.length > 0 && text.length < 50 && targets.some(t => text.includes(t) || id.includes(t) || className.includes(t))) {
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {
                        if (el.id) return { id: el.id };
                        return { text: el.innerText.trim(), tag: el.tagName.toLowerCase() };
                    }
                }
            }
            return null;
        }
        """
        try:
            res = await page.evaluate(f"({js_find_button})({repr(button_label)})")
            if res:
                btn_id = res.get("id")
                btn_text = res.get("text")
                btn_tag = res.get("tag")

                if btn_id:
                    await page.click(f"#{btn_id}")
                    return True
                elif btn_text and btn_tag:
                    escaped_text = btn_text.replace("'", "\\'")
                    sel = f"{btn_tag}:has-text('{escaped_text}')"
                    try:
                        await page.click(sel)
                        return True
                    except Exception:
                        js_click = f"""
                        (text, tag) => {{
                            const clickables = Array.from(document.querySelectorAll(tag));
                            for (const el of clickables) {{
                                if (el.innerText.trim() === text) {{
                                    el.click();
                                    return true;
                                }}
                            }}
                            return false;
                        }}
                        """
                        return await page.evaluate(f"({js_click})({repr(btn_text)}, {repr(btn_tag)})")
            logger.warning(f"[{self.platform_name}] Semantic button for '{button_label}' not found.")
            return False
        except Exception as e:
            logger.error(f"[{self.platform_name}] Semantic click failed for '{button_label}': {e}")
            return False
