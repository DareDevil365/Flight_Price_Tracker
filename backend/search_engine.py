"""Bounded search execution. Listed quotes and verified checkout totals stay distinct."""
import asyncio
import uuid
import os
from datetime import datetime, timedelta, timezone, date
from loguru import logger
from stealth.browser_factory import BrowserFactory
from session_manager import SessionManager
from proxy_manager import ProxyManager
from workers.makemytrip_worker import MakeMyTripWorker
from workers.easemytrip_worker import EaseMyTripWorker
from workers.cleartrip_worker import CleartripWorker
from workers.google_flights_worker import GoogleFlightsWorker
from workers.ai_worker import AIWorker
from coupon_brute_forcer import CouponBruteForcer
from quotes import valid_flights, search_url, utc_now
from alternative_planner import AlternativePlanner


class Dispatcher:
    def __init__(self, db, session_mgr, financial_filter, deal_scorer, savings_stacker,
                 emit_ws, smart_advisor=None, coupon_instincts=None, pipeline_monitor=None):
        self.db, self.session_mgr, self.filter = db, session_mgr, financial_filter
        self.emit_ws, self.smart_advisor = emit_ws, smart_advisor
        self.stacker = savings_stacker
        self.factory, self.proxy_mgr = BrowserFactory(), ProxyManager()
        self._active_searches = {}
        self._slots = asyncio.Semaphore(3)
        self._pending_checkouts = {}
        self._search_tasks = {}
        self._booking_lock = asyncio.Lock()
        self._google_context_lock = asyncio.Lock()
        self._google_context_sessions = {}
        self.planner = AlternativePlanner(self)

    def emit_log(self, search_id, platform, level, message):
        logger.info(f'[{platform}] {message}')
        self.emit_ws('bot:log', dict(searchId=search_id, platform=platform, level=level,
                                    message=message, timestamp=utc_now()))

    async def cancel_search(self, search_id):
        task = self._active_searches.get(search_id)
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def dispatch_all(self, task):
        sid, started = task['search_id'], datetime.now(timezone.utc)
        for session_id in list(self._pending_checkouts):
            if session_id not in self.session_mgr._sessions:
                self._pending_checkouts.pop(session_id)
        self._active_searches[sid] = asyncio.current_task()
        task['platform_failures']={}
        self._search_tasks[sid] = task
        if len(self._search_tasks)>20:
            self._search_tasks.pop(next(iter(self._search_tasks)))
        status = 'failed'
        try:
            trip = task['trip']
            limit = asyncio.Semaphore(task['cloak']['max_concurrent_bots'])
            tasks = [self._run_platform(p, task, limit) for p in task['platforms']]
            if trip['trip_type'] == 'round_trip':
                inbound = {**task, 'direction':'inbound', 'trip':{**trip,
                    'origin':trip['destination'], 'destination':trip['origin'],
                    'departure_date':trip['return_date'], 'return_date':None, 'trip_type':'one_way'}}
                tasks.extend(self._run_platform(p, inbound, limit) for p in task['platforms'])
            await asyncio.gather(*tasks, return_exceptions=True)
            results = await self.apply_integrity(sid,trip)
            usable=[r for r in results if r['savings_breakdown']['integrity']['status']!='flagged']
            if usable:
                status = 'completed'
                await self.db.recalculate_ranks(sid)
                if self.smart_advisor:
                    advice = await self.smart_advisor.get_advisory(trip, usable, task.get('date_alternatives'), search_id=sid, financial=task['financial'])
                    advice['searchId'] = sid
                    self.emit_ws('search:suggestions', advice)
                    await self.db.save_smart_suggestions(sid, f"{trip['origin']}-{trip['destination']}", advice)
        except asyncio.CancelledError:
            status = 'cancelled'
            raise
        except Exception as exc:
            self.emit_log(sid, 'system', 'error', str(exc))
        finally:
            self._active_searches.pop(sid, None)
            elapsed = int((datetime.now(timezone.utc)-started).total_seconds()*1000)
            await self.db.db.execute('UPDATE searches SET status=?, completed_at=?, total_duration_ms=? WHERE id=?',
                                     (status, utc_now(), elapsed, sid))
            await self.db.db.commit()
            self.emit_ws('search:'+status, dict(searchId=sid, durationMs=elapsed,
                error='No usable quotes were returned. See platform logs for blocks or parsing errors.' if status=='failed' else None))

    async def _run_platform(self, platform, task, limit):
        async with limit:
            async with self._slots:
                try:
                    async with asyncio.timeout(180):
                        await self._scrape(platform, task)
                    if self.db:
                        await self.db.record_provider_run(task,platform,'success')
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    if self.db:
                        await self.db.record_provider_run(task,platform,'failed',exc)
                    task.setdefault('platform_failures',{})[platform+' '+task.get('direction','outbound')]=str(exc)
                    self.emit_log(task['search_id'], platform, 'error', str(exc))
                    self.emit_ws('bot:status', dict(searchId=task['search_id'], platform=platform,
                        phase='failed', progress=100, error=str(exc),reasonCode=getattr(exc,'code','UNVERIFIED'),
                        manualUrl=search_url(platform,task['trip']) if platform in ('makemytrip','easemytrip','cleartrip','google_flights') else None))

    async def _worker(self, platform):
        classes = {'makemytrip':MakeMyTripWorker, 'easemytrip':EaseMyTripWorker,
                   'cleartrip':CleartripWorker, 'google_flights':GoogleFlightsWorker}
        if platform in classes:
            return classes[platform]()
        sites = {s['id']:s for s in await self.db.get_platforms() if s['is_active']}
        if platform not in sites:
            raise ValueError('Unsupported or disabled platform')
        raise ValueError('This website has no validated scraper adapter. Open it from Manage Websites for a manual comparison.')

    async def _scrape(self, platform, task):
        sid, trip = task['search_id'], task['trip']
        worker = await self._worker(platform)
        if (platform=='google_flights' and task['cloak']['proxy_mode']!='ON'
                and not trip.get('nearby_dates_range') and trip.get('max_stops') is None):
            try:
                from google_source import fetch_google
                flights=valid_flights(await fetch_google(trip),trip)
                if not flights:
                    raise ValueError('No validated Google fares')
            except Exception as exc:
                self.emit_log(sid,platform,'warning',f'Fast Google search unavailable ({exc}); retrying with the browser.')
            else:
                await self._save_listings(platform,task,flights,search_url(platform,trip))
                self.emit_ws('bot:status',dict(searchId=sid,platform=platform,phase='completed',progress=100))
                return
        session_id = str(uuid.uuid4())
        registered = False
        browser = context = page = None
        stream = None
        try:
            self.emit_ws('bot:status', dict(searchId=sid, platform=platform, phase='searching', progress=10))
            proxy = self.proxy_mgr.get_fresh_proxy(platform) if task['cloak']['proxy_mode']=='ON' else None
            browser, context, page = await self.factory.create_cloak_browser(proxy=proxy, cloak_config=task['cloak'])
            await self.session_mgr.register_session(session_id, sid, platform, browser, context, page, 1,
                is_shared_browser=(browser == self.factory._shared_browser))
            registered = True
            if not task.get('background'):
                stream = asyncio.create_task(self._screenshots(page, sid, platform, session_id))
            if platform=='mock':
                await worker.navigate_to_search(page)
            await worker.input_search_criteria(page, trip)
            await worker.execute_search(page)
            if await worker.detect_captcha(page):
                raise RuntimeError('Site requires human verification; this search cannot return reliable quotes.')
            flights = valid_flights(await worker.parse_search_results(page), trip)
            if not flights:
                from provider_status import page_problem
                problem=page_problem(await page.inner_text('body'),page.url,getattr(worker,'_http_failures',[]))
                if problem:
                    raise problem
                raise ValueError('No readable flights matching the requested trip. The site may be blocked or its layout changed.')
            search_page = page.url
            # Gather listing quotes first so a blocked checkout never loses search results.
            await self._save_listings(platform,task,flights,search_page)
            if platform != 'google_flights':
                try:
                    offers = await worker.scrape_onsite_coupons(page)
                    if offers:
                        await self.db.add_coupons_batch(offers)
                        self.emit_log(sid,platform,'info',f'Found {len(offers)} published offer codes; savings require checkout testing.')
                except Exception as exc:
                    self.emit_log(sid,platform,'warning',f'Coupon collection unavailable: {exc}. Keeping the readable flight fares without coupon savings.')
            # Flexible dates are explicit alternatives; they never replace the requested date.
            if platform=='google_flights' and trip.get('nearby_dates_range',0)>0 and trip['trip_type']=='one_way':
                alts = []
                for offset in range(-trip['nearby_dates_range'], trip['nearby_dates_range']+1):
                    day = date.fromisoformat(trip['departure_date'])+timedelta(days=offset)
                    if offset==0 or day < datetime.now().date():
                        continue
                    alt_trip = {**trip, 'departure_date':day.isoformat()}
                    try:
                        await worker.input_search_criteria(page,alt_trip)
                        await worker.execute_search(page)
                        found = valid_flights(await worker.parse_search_results(page),alt_trip)
                        if found:
                            alternative=min(found,key=lambda f:f['base_price'])
                            reference=min(flights,key=lambda f:f['base_price'])
                            alternative_quote=self._listed_quote(platform,{**task,'trip':alt_trip},alternative,page.url)
                            reference_quote=self._listed_quote(platform,task,reference,search_page)
                            for row in (alternative_quote,reference_quote):
                                row['savings_breakdown']['integrity']=dict(status='uncorroborated',
                                    reasons=['Single-source date comparison; final fees and source agreement are unverified.'],compared_sources=[])
                            alts.append(dict(date=day.isoformat(),price=alternative['base_price'],
                                savings=reference['base_price']-alternative['base_price'],
                                quote=alternative_quote,reference_quote=reference_quote))
                    except Exception as exc:
                        self.emit_log(sid,platform,'warning',f'Alternative date {day} unavailable: {exc}')
                self.emit_ws('search:date_alternatives',dict(searchId=sid,dateAlternatives=alts))
                task['date_alternatives'] = alts
            self.emit_ws('bot:status',dict(searchId=sid,platform=platform,phase='completed',progress=100))
        finally:
            if stream:
                stream.cancel()
                await asyncio.gather(stream,return_exceptions=True)
            if registered:
                await self.session_mgr.close_session(session_id)
            elif context:
                await context.close()
                if browser:
                    await browser.close()
            self.proxy_mgr.release_proxy(platform)

    def _listed_quote(self,platform,task,flight,search_page):
        sid,trip=task['search_id'],task['trip']
        return dict(id=str(uuid.uuid4()),search_id=sid,platform=platform,
                **{k:flight.get(k) for k in ['flight_number','airline','departure_time','arrival_time','duration','stops']},
                base_price=flight['base_price'],final_price=flight['base_price'],effective_price=flight['base_price'],
                best_coupon_code=None,savings=0,deal_score=0,all_tested_coupons=[],session_id=None,rank=0,
                departure_date=trip['departure_date'],savings_breakdown=dict(verification='listed',currency='INR',
                    origin=trip['origin'],destination=trip['destination'],direction=task.get('direction','outbound'),
                    passenger_count=trip['passenger_count'],cabin_class=trip['cabin_class'],observed_at=utc_now(),booking_url=search_page,
                    preferred_time=trip.get('preferred_time','ANY'),max_stops=trip.get('max_stops'),
                    listed_price=flight['base_price'],listed_observed_at=utc_now(),
                    fare_family=flight.get('fare_family'),baggage=flight.get('baggage'),
                    segments=flight.get('segments'),layovers=flight.get('layovers'),source_transport=flight.get('source_transport','browser'),
                    source_revision=flight.get('source_revision'),source_inventory=flight.get('source_inventory'),integrity=dict(status='pending',reasons=['Checking source agreement'],compared_sources=[]),
                    source_learning_allowed=flight.get('source_learning_allowed'),source_freshness=flight.get('source_freshness'),
                    fee_status=flight.get('fee_status') or 'Payment fees and coupon eligibility need checkout verification.',checkout_price=None,
                    effective_price=flight['base_price'],total_stacking_savings=0,cashback_portal=dict(provider='None',amount=0),
                    payment_method=dict(provider='None',amount=0),instructions=[]))

    async def _save_listings(self,platform,task,flights,search_page):
        for flight in flights[:12]:
            quote=self._listed_quote(platform,task,flight,search_page)
            cap=task['financial'].get('max_final_price')
            if cap:
                quote['savings_breakdown']['budget_check']=dict(limit=cap,
                    listed_over_budget=quote['final_price']>cap,
                    explanation='Budget applies to the verified payable total. Listed prices above it remain candidates because an eligible coupon may reduce the total; fees may increase it.')
            await self.db.save_result(quote)
            self.emit_ws('search:results',quote)

    async def _screenshots(self,page,sid,platform,session_id):
        import base64
        while True:
            try:
                await asyncio.sleep(4)
                encoded=base64.b64encode(await page.screenshot(type='jpeg',quality=40)).decode()
                self.emit_ws('bot:screenshot',dict(searchId=sid,platform=platform,sessionId=session_id,
                    imageBase64=encoded,timestamp=utc_now()))
            except asyncio.CancelledError:
                raise
            except Exception:
                return

    async def verify_checkout(self, session_id, persist=True):
        pending = self._pending_checkouts.get(session_id)
        session = self.session_mgr._sessions.get(session_id)
        if not pending or not session:
            raise ValueError('Booking session expired. Run a new search.')
        expires=session.get('expires_at')
        if expires and datetime.now(timezone.utc)>=SessionManager._expires(session):
            await self.session_mgr.close_session(session_id)
            self._pending_checkouts.pop(session_id,None)
            raise ValueError('Booking session expired. Run a new search.')
        if pending['lock'].locked():
            raise ValueError('Coupon verification is already running for this booking.')
        async with pending['lock']:
            task, quote = pending['task'], pending['quote']
            status = dict(sessionId=session_id, searchId=task.get('search_id'), platform=quote.get('platform'))
            from checkout_state import invalidate_checkout
            if invalidate_checkout(quote):
                if persist:
                    await self.db.save_result(quote)
                    await self.db.recalculate_ranks(task['search_id'])
                    self.emit_ws('search:results', quote)
            self.emit_ws('session:verification', dict(**status, status='running',
                message='Checking the current cart and eligible coupons. Keep the booking, add-ons and payment unchanged.'))
            try:
                result = await self._verify_checkout_locked(session_id, pending, session, persist)
            except BaseException as exc:
                self.emit_ws('session:verification', dict(**status, status='failed',
                    message='Verification interrupted.' if isinstance(exc, asyncio.CancelledError) else str(exc)))
                raise
            self.emit_ws('session:verification', dict(**status, status='success',
                message='Merchant payment total checked. Later gateway or issuer charges remain unknown.'))
            return result

    async def _verify_checkout_locked(self, session_id, pending, session, persist):
        worker, task, quote = pending['worker'], pending['task'], pending['quote']
        page = session['context'].pages[-1] if session['context'].pages else session['page']
        session['page'] = page
        if not worker.is_provider_page(page):
            raise ValueError('This browser page is outside the expected HTTPS booking provider. Return to its payment summary before verifying. External gateway or bank charges cannot be certified here.')
        if not await worker.is_at_checkout(page):
            raise ValueError('Continue to the payment page and select your payment method first. A final payable INR total must be visible.')
        if not await worker.confirm_checkout_flight(page, quote):
            raise ValueError('Could not confirm the selected flight on this payment page. Keep the itinerary visible and do not change flights before verifying.')
        if not await worker.confirm_checkout_passengers_and_cabin(page, task['trip']):
            raise ValueError('Could not confirm the requested adult count and cabin at checkout. Keep the booking summary visible and retain the same passengers and cabin.')
        selected_payment=await worker.read_selected_payment(page)
        if not selected_payment:
            raise ValueError('Could not confirm a selected payment method. Select it on the provider page and keep its payment summary visible before verifying fees or coupons.')
        if quote['savings_breakdown'].get('verification')=='listed':
            quote['savings_breakdown'].setdefault('listed_price',quote['final_price'])
            quote['savings_breakdown'].setdefault('listed_observed_at',quote['savings_breakdown'].get('observed_at'))
        cart_options=await worker.read_cart_options(page)
        async def check_context():
            if (await worker.read_selected_payment(page)!=selected_payment
                or await worker.read_cart_options(page)!=cart_options
                or not worker.is_provider_page(page)
                or not await worker.confirm_checkout_flight(page,quote)
                or not await worker.confirm_checkout_passengers_and_cabin(page,task['trip'])
                or not await worker.is_at_checkout(page)):
                raise ValueError('Booking, add-ons or payment changed during verification. No total can be verified.')
        session['expires_at'] = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=15)
        trip = task['trip']
        coupons = await self.db.get_live_coupons(quote['platform'])
        onsite_collection='collected'
        try:
            # Current native terms take precedence when the same code also
            # exists in older external/database candidates.
            coupons = [*await worker.scrape_onsite_coupons(page),*coupons]
        except Exception as exc:
            onsite_collection='failed'
            self.emit_log(task['search_id'],quote['platform'],'warning',f'Onsite coupon collection failed: {exc}. Testing only previously collected eligible codes.')
        async with asyncio.timeout(480):
            bf = await CouponBruteForcer(worker, self.filter, self.emit_log).brute_force(
                page, coupons, {**task['financial'],'selected_payment':selected_payment,'passenger_count':trip['passenger_count'],'is_domestic':trip['is_domestic']}, task['search_id'], db=self.db,
                route=f"{trip['origin']}-{trip['destination']}",context_check=check_context,
                audit_scope={**trip,'stage':'merchant_payment','onsite_collection':onsite_collection,
                    'selected_payment':selected_payment,'flight_number':quote.get('flight_number'),
                    'departure_time':quote.get('departure_time')})
        if (await worker.read_selected_payment(page)!=selected_payment
                or not await worker.confirm_checkout_flight(page,quote)
                or not await worker.confirm_checkout_passengers_and_cabin(page,trip)):
            raise ValueError('Booking criteria or payment changed while coupons were being tested. No total was saved; verify again with the intended booking unchanged.')
        await check_context()
        final_summary=await worker.read_checkout_total(page)
        if not final_summary or final_summary['total']!=bf['best_price']:
            raise ValueError('Payable total changed after the coupon trial. Reverify before using this result.')
        if bf.get('audit_run_id'):
            from coupon_audit import CouponAudit
            await CouponAudit(self.db,bf['audit_run_id']).finish('checkout_verified',bf)
        quote.update(base_price=bf['baseline_price'], final_price=bf['best_price'],
            effective_price=bf['best_price'], best_coupon_code=bf['best_coupon'],
            savings=bf['savings'], all_tested_coupons=bf['all_results'])
        quote['savings_breakdown'].update(verification='checkout', checkout_price=bf['best_price'],
            effective_price=bf['best_price'], observed_at=utc_now(),
            fee_status='Payable total includes the fees shown for the selected payment method. Reverify if you change payment, baggage or fare.')
        quote['savings_breakdown']['integrity']=dict(status='checkout_verified',reasons=['Itinerary and payable INR total verified at checkout'],compared_sources=[])
        quote['savings_breakdown']['selected_payment']=selected_payment
        quote['savings_breakdown'].pop('booking_problem',None)
        quote['savings_breakdown']['cart_options']=cart_options
        quote['savings_breakdown']['fee_scope']='Merchant-displayed payable total for this payment selection; later issuer/gateway charges are not confirmed.'
        quote['savings_breakdown']['coupon_coverage']=bf.get('coverage')
        quote['savings_breakdown']['fee_breakdown'] = final_summary.get('fees', [])
        if persist:
            await self.db.save_result(quote)
            if quote['platform'] != 'mock':
                await self.db.record_quote(quote)
            await self.db.recalculate_ranks(task['search_id'])
            self.emit_ws('search:results', quote)
            if self.smart_advisor:
                rows = await self.db.get_search_results(task['search_id'])
                advice = await self.smart_advisor.get_advisory(task['trip'], rows, search_id=task['search_id'], financial=task['financial'])
                advice['searchId'] = task['search_id']
                self.emit_ws('search:suggestions', advice)
        return quote

    async def prepare_checkout(self, search_id, result_id):
        if self._booking_lock.locked():
            raise ValueError('Another booking is being prepared. Please wait for it to open.')
        async with self._booking_lock:
            await self._prepare_checkout(search_id, result_id)

    async def google_booking_context(self, search_id, result_id):
        """Optional slow browser guidance, separate from fast search and learning."""
        if self._google_context_lock.locked():
            raise ValueError('Google booking guidance is already being checked. Please wait.')
        async with self._google_context_lock:
            task = self._search_tasks.get(search_id)
            if not task:
                raise ValueError('Run a fresh search before checking Google booking guidance.')
            rows = await self.db.get_search_results(search_id)
            quote = next((row for row in rows if row['id'] == result_id), None)
            if not quote or quote['savings_breakdown'].get('integrity', {}).get('status') == 'flagged':
                raise ValueError('This result is unavailable or quarantined. Run a fresh search.')
            for key, cached in list(self._google_context_sessions.items()):
                if self.session_mgr.get_session_status(cached['sessionId']) == 'expired':
                    self._google_context_sessions.pop(key)
                    await self.session_mgr.close_session(cached['sessionId'])
            key = (search_id, result_id)
            if key in self._google_context_sessions:
                return self._google_context_sessions[key]
            if len(self._google_context_sessions) >= 2:
                oldest = next(iter(self._google_context_sessions))
                previous = self._google_context_sessions.pop(oldest)
                await self.session_mgr.close_session(previous['sessionId'])
            meta = quote['savings_breakdown']
            trip = {**task['trip'], 'origin': meta['origin'], 'destination': meta['destination'],
                    'departure_date': quote['departure_date'], 'trip_type': 'one_way', 'return_date': None}
            browser, registered = None, False
            session_id = str(uuid.uuid4())
            try:
                from google_booking_context import load_booking_context
                async with self._slots, asyncio.timeout(75):
                    browser, context, page = await self.factory.create_cloak_browser(cloak_config=task['cloak'])
                    report = await load_booking_context(page, trip, quote)
                    await self.session_mgr.register_session(session_id, search_id, 'google_flights', browser, context, page, 1)
                    registered = True
                    await self.session_mgr.set_session_ready(session_id)
                    report.update(searchId=search_id, resultId=result_id, sessionId=session_id)
                    self._google_context_sessions[key] = report
                    return report
            except BaseException:
                if registered:
                    await self.session_mgr.close_session(session_id)
                elif browser:
                    await browser.close()
                raise

    async def _prepare_checkout(self, search_id, result_id):
        task = self._search_tasks.get(search_id)
        if not task:
            raise ValueError('This search is no longer active. Run it again to open a booking session.')
        rows = await self.db.get_search_results(search_id)
        quote = next((r for r in rows if r['id']==result_id), None)
        if quote and quote['savings_breakdown'].get('integrity',{}).get('status')=='flagged':
            raise ValueError('This quote was quarantined after an integrity check. Run a fresh search before opening it.')
        if not quote or quote['platform']=='google_flights':
            raise ValueError('Choose a supported booking website result.')
        if quote.get('session_id') in self.session_mgr._sessions:
            existing = quote['session_id']
            if self.session_mgr.get_session_status(existing) != 'expired':
                await self.session_mgr.handoff_to_user(existing)
                return
            await self.session_mgr.close_session(existing)
            self._pending_checkouts.pop(existing, None)
        if len(self._pending_checkouts) >= 3:
            expired = next((sid for sid,pending in self._pending_checkouts.items() if not pending['lock'].locked()),None)
            if expired is None:
                raise ValueError('All booking sessions are verifying coupons. Wait for one to finish before opening another cart.')
            self._pending_checkouts.pop(expired)
            await self.session_mgr.close_session(expired)
        meta = quote['savings_breakdown']
        trip = {**task['trip'], 'origin':meta['origin'], 'destination':meta['destination'],
                'departure_date':quote['departure_date'], 'trip_type':'one_way', 'return_date':None}
        task = {**task, 'trip':trip}
        # Opening a new cart invalidates the old payment claim immediately,
        # including when browser navigation or selecting the flight later fails.
        from checkout_state import invalidate_checkout
        if invalidate_checkout(quote):
            quote['session_id'] = None
            await self.db.save_result(quote)
            self.emit_ws('search:results', quote)
        worker = await self._worker(quote['platform'])
        session_id = str(uuid.uuid4())
        registered = False
        browser = None
        try:
            async with self._slots, asyncio.timeout(90):
                browser, context, page = await self.factory.create_cloak_browser(cloak_config=task['cloak'])
                await self.session_mgr.register_session(session_id, search_id, quote['platform'], browser, context, page, 1)
                registered = True
                await worker.input_search_criteria(page, trip)
                await worker.execute_search(page)
                flights = valid_flights(await worker.parse_search_results(page), trip)
                from quote_integrity import same_itinerary
                matches = [f for f in flights if same_itinerary(quote,
                    self._listed_quote(quote['platform'],
                        {**task,'search_id':search_id,'direction':meta.get('direction','outbound')}, f, page.url))]
                if len(matches)!=1:
                    raise ValueError('Flight no longer uniquely available. Refresh your search.')
                latest=matches[0]['base_price']
                previous=meta.get('listed_price',quote['final_price'])
                if latest!=previous:
                    self.emit_log(search_id,quote['platform'],'warning',f'This listing changed from INR {previous:,.0f} to INR {latest:,.0f}. Fees remain pending.')
                # A reopened browser is a new cart. Neither the previous payment
                # total nor its old corroboration certifies this current listing.
                quote.update(base_price=latest,final_price=latest,effective_price=latest,
                    best_coupon_code=None,savings=0,all_tested_coupons=[],session_id=None)
                meta.update(verification='listed',listed_price=latest,listed_observed_at=utc_now(),observed_at=utc_now(),
                    checkout_price=None,effective_price=latest,
                    fee_status='New booking cart opened. Its payment fees and coupons need fresh verification.',
                    integrity=dict(status='uncorroborated',reasons=['Booking re-search returned this listing; the new cart is not payment-verified.'],compared_sources=[]))
                for key in ('selected_payment','cart_options','fee_scope','fee_breakdown','coupon_coverage'):
                    meta.pop(key,None)
                for key in ('segments','layovers','fare_family','baggage','source_transport',
                            'source_revision','source_inventory','source_learning_allowed','source_freshness'):
                    meta[key] = matches[0].get(key)
                meta['booking_url'] = page.url
                # Publish the newly observed listing before the fallible click.
                # A failed selection must not leave an older price in the DB/UI.
                await self.db.save_result(quote)
                self.emit_ws('search:results', quote)
                await worker.select_flight(page, matches[0])
                chosen_page=context.pages[-1]
                body=(await chosen_page.inner_text('body')).lower()
                from provider_status import page_problem
                problem=page_problem(body,chosen_page.url,getattr(worker,'_http_failures',[]))
                if problem:
                    # Preserve a real browser for assisted recovery, but never
                    # promote its error page to a successful checkout.
                    quote['savings_breakdown']['booking_problem']=dict(code=problem.code,message=str(problem))
                    self.emit_log(search_id,quote['platform'],'warning',str(problem))
                else:
                    quote['savings_breakdown'].pop('booking_problem',None)
                self.session_mgr._sessions[session_id]['page'] = context.pages[-1]
                self._pending_checkouts[session_id] = dict(worker=worker,task=task,quote=quote,lock=asyncio.Lock())
                quote['session_id'] = session_id
                await self.db.save_result(quote)
                self.emit_ws('search:results', quote)
                await self.session_mgr.set_session_ready(session_id)
                await self.session_mgr.handoff_to_user(session_id)
        except BaseException:
            if registered:
                await self.session_mgr.close_session(session_id)
            elif browser:
                await browser.close()
            raise

    async def apply_integrity(self,search_id,trip):
        import json
        from quote_integrity import check_outputs
        rows=await self.db.get_search_results(search_id)
        checks=check_outputs(rows,trip)
        for row in rows:
            quality=checks[row['id']]
            row['savings_breakdown']['integrity']=quality
            await self.db.save_result(row)
            self.emit_ws('search:results',row)
            if quality['status']=='flagged':
                await self.db.db.execute('INSERT OR REPLACE INTO quote_quarantine VALUES (?,?,?,?)',
                    (row['id'],json.dumps(quality['reasons']),json.dumps(row),utc_now()))
                await self.db.db.commit()
                self.emit_log(search_id,row['platform'],'warning','Price quarantined: '+'; '.join(quality['reasons']))
            elif quality['status'] in ('corroborated','checkout_verified'):
                await self.db.record_quote(row)
        flagged=sum(q['status']=='flagged' for q in checks.values())
        self.emit_ws('search:integrity',dict(searchId=search_id,total=len(rows),flagged=flagged,
            learned=sum(q['status'] in ('corroborated','checkout_verified') for q in checks.values())))
        return rows

    async def explore_alternatives(self,search_id,transfer_budget=2000,hubs=None):
        return await self.planner.explore(search_id,transfer_budget,hubs)

    async def cleanup(self):
        for task in list(self._active_searches.values()):
            task.cancel()
        await asyncio.gather(*list(self._active_searches.values()),return_exceptions=True)
        await self.session_mgr.cleanup_all()
        await self.factory.cleanup()
        self._pending_checkouts.clear()
        self._google_context_sessions.clear()
        self._search_tasks.clear()
