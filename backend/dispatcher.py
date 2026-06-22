import asyncio
import random
import uuid
import traceback
import json
from datetime import datetime, timedelta, timezone
from loguru import logger

from stealth.browser_factory import BrowserFactory
from proxy_manager import ProxyManager
from workers.mock_worker import MockWorker
from workers.google_flights_worker import GoogleFlightsWorker
from workers.makemytrip_worker import MakeMyTripWorker
from workers.easemytrip_worker import EaseMyTripWorker
from workers.cleartrip_worker import CleartripWorker
from workers.ai_worker import AIWorker

from compiler import is_domestic_route

def is_coupon_airline_match(coupon_desc: str, flight_airline: str) -> bool:
    if not coupon_desc or not flight_airline:
        return True
    
    known_airlines = {
        "indigo": ["indigo", "6e"],
        "spicejet": ["spicejet", "sg"],
        "vistara": ["vistara", "uk"],
        "air india": ["air india", "ai"],
        "akasa": ["akasa", "qp"],
        "air india express": ["air india express", "express", "ix"]
    }
    
    desc_lower = coupon_desc.lower()
    flight_airline_lower = flight_airline.lower()
    
    mentioned_airlines = []
    for brand, keywords in known_airlines.items():
        if any(kw in desc_lower for kw in keywords):
            mentioned_airlines.append(brand)
            
    if not mentioned_airlines:
        return True
        
    for brand in mentioned_airlines:
        for kw in known_airlines[brand]:
            if kw in flight_airline_lower:
                return True
                
    return False



class Dispatcher:
    def __init__(self, db, session_mgr, financial_filter, deal_scorer, savings_stacker, emit_ws, smart_advisor=None, coupon_instincts=None, pipeline_monitor=None):
        self.db = db
        self.session_mgr = session_mgr
        self.financial_filter = financial_filter
        self.deal_scorer = deal_scorer
        self.savings_stacker = savings_stacker
        self.emit_ws = emit_ws
        self.smart_advisor = smart_advisor
        self.coupon_instincts = coupon_instincts
        self.pipeline_monitor = pipeline_monitor
        
        self.proxy_mgr = ProxyManager()
        self.browser_factory = BrowserFactory()
        
        self._active_searches: dict[str, list[asyncio.Task]] = {}

    async def dispatch_all(self, task: dict):
        """Run all platform workers in parallel under a semaphore concurrency limit."""
        search_id = task["search_id"]
        platforms = task["platforms"]
        max_concurrent = task["cloak"].get("max_concurrent_bots", 4)
        
        logger.info(f"[Dispatcher] Starting search {search_id} on {len(platforms)} platforms (limit: {max_concurrent})...")
        self.emit_ws("search:status", {"searchId": search_id, "status": "running"})

        semaphore = asyncio.Semaphore(max_concurrent)
        start_time = datetime.now(timezone.utc)
        
        # Load platforms dynamic config from database
        db_platforms = {}
        if self.db:
            try:
                rows = await self.db.get_platforms()
                for r in rows:
                    db_platforms[r["id"]] = (r["name"], r["url"])
            except Exception as e:
                logger.error(f"[Dispatcher] Failed to fetch platforms from database: {e}")

        # Phase 1: Date Intelligence (Google Flights scan first)
        date_alternatives = []
        best_date = task["trip"]["departure_date"]
        target_price = None
        
        try:
            raw_alternatives = await self._run_nearby_dates_scan(task)
            # Find target date price (offset 0)
            target_date_str = task["trip"]["departure_date"]
            for alt in raw_alternatives:
                if alt["date"] == target_date_str:
                    target_price = alt["price"]
                    break
            
            # Populate date alternatives with relative savings
            for alt in raw_alternatives:
                if alt["date"] != target_date_str:
                    savings_alt = (target_price - alt["price"]) if target_price is not None else 0.0
                    date_alternatives.append({
                        "date": alt["date"],
                        "price": alt["price"],
                        "savings": savings_alt
                    })
            
            task["date_alternatives"] = date_alternatives
            # Emit date alternatives to frontend
            self.emit_ws("search:date_alternatives", {
                "searchId": search_id,
                "dateAlternatives": date_alternatives
            })
            
            # Find best date (cheapest date overall)
            if raw_alternatives:
                cheapest_run = min(raw_alternatives, key=lambda x: x["price"])
                best_date = cheapest_run["date"]
                logger.info(f"[Dispatcher] Date Intelligence complete. Target date: {target_date_str} (est: {target_price}). Best date: {best_date} (est: {cheapest_run['price']}).")
        except Exception as ex:
            logger.error(f"[Dispatcher] Failed to run Phase 1 Date Intelligence: {ex}")

        # Phase 2: Actual Scrapes
        # Filter out google_flights as it's only used for date intelligence in Phase 1
        booking_platforms = [p for p in platforms if p != "google_flights"]
        if not booking_platforms:
            booking_platforms = ["easemytrip", "cleartrip", "makemytrip"]

        # Instantiate worker classes
        workers = []
        for p in booking_platforms:
            worker = self._create_worker(p, db_platforms)
            if worker:
                workers.append(worker)
            else:
                logger.warning(f"[Dispatcher] Platform '{p}' worker not found. Skipping.")
                self.emit_log(search_id, p, "error", f"Platform {p} is currently unsupported.")

        if not workers:
            logger.error("[Dispatcher] No valid workers found to execute search.")
            self.emit_ws("search:failed", {"searchId": search_id, "error": "No valid workers configured"})
            return

        # Spawn tasks for target date
        async_tasks = []
        for worker in workers:
            t = asyncio.create_task(
                self._run_worker_with_semaphore(semaphore, worker, task)
            )
            async_tasks.append(t)
            
        # Spawn tasks for best date (if different)
        if best_date != task["trip"]["departure_date"]:
            best_date_task = task.copy()
            best_date_task["trip"] = task["trip"].copy()
            best_date_task["trip"]["departure_date"] = best_date
            
            for worker in workers:
                best_date_worker = self._create_worker(worker.platform_id, db_platforms)
                if best_date_worker:
                    t = asyncio.create_task(
                        self._run_worker_with_semaphore(semaphore, best_date_worker, best_date_task)
                    )
                    async_tasks.append(t)
            
        self._active_searches[search_id] = async_tasks
        
        # Wait for all workers to finish
        results = await asyncio.gather(*async_tasks, return_exceptions=True)
        
        # Cleanup search active list
        if search_id in self._active_searches:
            del self._active_searches[search_id]

        # Determine if search was cancelled
        is_cancelled = False
        if self.db:
            try:
                async with self.db.db.execute("SELECT status FROM searches WHERE id = ?", (search_id,)) as cur:
                    row = await cur.fetchone()
                    if row and row[0] == 'cancelled':
                        is_cancelled = True
            except Exception:
                pass

        if not is_cancelled:
            # 1. Recalculate ranks in DB based on effective_price
            if self.db:
                try:
                    await self.db.recalculate_ranks(search_id)
                except Exception as e:
                    logger.error(f"[Dispatcher] Failed to recalculate ranks: {e}")

            # 3. Run smart travel advisor ONCE on the aggregated results
            if self.smart_advisor:
                try:
                    if self.db:
                        all_results = await self.db.get_search_results(search_id)
                        if all_results:
                            logger.info(f"[Dispatcher] Generating unified smart suggestions for {len(all_results)} flights...")
                            advisory = await self.smart_advisor.get_advisory(task["trip"], all_results, date_alternatives, search_id=search_id)
                            self.emit_ws("search:suggestions", advisory)
                            await self.db.save_smart_suggestions(search_id, f"{task['trip']['origin']}-{task['trip']['destination']}", advisory)
                except Exception as ex:
                    logger.error(f"[Dispatcher] Failed to generate advisor suggestions: {ex}")

        duration = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
        
        if not is_cancelled:
            status = "completed"
            if self.db:
                try:
                    async with self.db.db.execute("SELECT COUNT(*) FROM search_results WHERE search_id = ?", (search_id,)) as cur:
                        row = await cur.fetchone()
                        if not row or row[0] == 0:
                            status = "failed"
                except Exception as e:
                    logger.warning(f"Error checking results count: {e}")

                try:
                    await self.db.db.execute(
                        """
                        UPDATE searches SET status = ?, completed_at = ?, total_duration_ms = ?
                        WHERE id = ?
                        """,
                        (status, datetime.now(timezone.utc).replace(tzinfo=None).isoformat(), duration, search_id),
                    )
                    await self.db.db.commit()
                except Exception as e:
                    logger.error(f"Error updating search status in DB: {e}")
            
            if status == "completed":
                logger.info(f"[Dispatcher] Search {search_id} finished. Duration: {duration}ms")
                self.emit_ws("search:completed", {"searchId": search_id, "durationMs": duration})
            else:
                logger.info(f"[Dispatcher] Search {search_id} failed. Duration: {duration}ms")
                self.emit_ws("search:failed", {"searchId": search_id, "error": "No flights or deals found."})
        else:
            logger.info(f"[Dispatcher] Search {search_id} cancelled.")

    async def cancel_search(self, search_id: str):
        """Cancel all running workers for a specific search ID."""
        if search_id in self._active_searches:
            logger.info(f"[Dispatcher] Cancelling search {search_id}...")
            for task in self._active_searches[search_id]:
                if not task.done():
                    task.cancel()
            del self._active_searches[search_id]
            
            if self.db:
                try:
                    await self.db.db.execute(
                        "UPDATE searches SET status = 'cancelled' WHERE id = ?", (search_id,)
                    )
                    await self.db.db.commit()
                except Exception as e:
                    logger.error(f"Error updating cancelled status: {e}")
                    
            self.emit_ws("search:cancelled", {"searchId": search_id})

    async def _run_nearby_dates_scan(self, task: dict) -> list[dict]:
        """Scan departure_date ± 2 days using a temporary Google Flights worker."""
        search_id = task["search_id"]
        trip = task["trip"]
        cloak = task["cloak"]
        
        base_dt = datetime.strptime(trip["departure_date"], "%Y-%m-%d")
        offsets = [0] + list(range(-2, 0)) + list(range(1, 3)) # Scan target date and ±2 days
        date_alternatives = []
        
        worker = GoogleFlightsWorker()
        proxy = self.proxy_mgr.get_fresh_proxy(worker.platform_id) if cloak.get("proxy_mode", "OFF") != "OFF" else None
        
        try:
            logger.info(f"[Dispatcher] Starting nearby dates scan for {trip['origin']} -> {trip['destination']} around {trip['departure_date']}")
            browser, context, page = await self.browser_factory.create_cloak_browser(
                proxy=proxy,
                cloak_config=cloak
            )
            try:
                for offset in offsets:
                    alt_date = (base_dt + timedelta(days=offset)).strftime("%Y-%m-%d")
                    alt_trip = trip.copy()
                    alt_trip["departure_date"] = alt_date
                    
                    await worker.navigate_to_search(page)
                    await worker.input_search_criteria(page, alt_trip)
                    await worker.execute_search(page)
                    alt_flights = await worker.parse_search_results(page)
                    
                    if alt_flights:
                        cheapest_alt = min(alt_flights, key=lambda f: f["base_price"])
                        price_alt = cheapest_alt["base_price"]
                        date_alternatives.append({
                            "date": alt_date,
                            "price": price_alt
                        })
                        
                        # Save to database price history
                        if self.db:
                            await self.db.save_nearby_date_price(
                                route=f"{trip['origin']}-{trip['destination']}",
                                date=alt_date,
                                price=price_alt,
                                platform="google_flights"
                            )
            finally:
                await context.close()
                await browser.close()
        except Exception as e:
            logger.error(f"[Dispatcher] Failed to scan nearby dates: {e}")
        finally:
            self.proxy_mgr.release_proxy(worker.platform_id)
            
        return date_alternatives

    async def _run_worker_with_semaphore(self, semaphore: asyncio.Semaphore, worker, task: dict):
        search_id = task["search_id"]
        platform = worker.platform_id

        async with semaphore:
            # Check if search has been cancelled in the meantime
            if search_id not in self._active_searches:
                return

            attempt = 0
            max_retries = 3
            should_retry = True
            
            while should_retry and attempt < max_retries:
                attempt += 1
                start_time = datetime.now()
                try:
                    await self._execute_worker_pipeline(worker, task, attempt)
                    
                    # Record metric for SUCCESS
                    latency = int((datetime.now() - start_time).total_seconds() * 1000)
                    if self.pipeline_monitor:
                        await self.pipeline_monitor.record_metric(
                            platform=platform,
                            phase="overall",
                            outcome="SUCCESS",
                            latency_ms=latency,
                            search_id=search_id
                        )
                    return  # Success
                except asyncio.CancelledError:
                    logger.info(f"[Dispatcher] Worker {platform} was cancelled.")
                    self.emit_log(search_id, platform, "warning", "Search was cancelled by user.")
                    raise
                except Exception as e:
                    # Classify error
                    error_category = "UNKNOWN"
                    retry_strategy = {"should_retry": True, "retry_count": 2, "delay_seconds": 5}
                    
                    if self.pipeline_monitor:
                        error_category = self.pipeline_monitor.classify_error(e, platform)
                        retry_strategy = self.pipeline_monitor.get_retry_strategy(error_category)
                    
                    # Record metric for FAILURE
                    latency = int((datetime.now() - start_time).total_seconds() * 1000)
                    if self.pipeline_monitor:
                        await self.pipeline_monitor.record_metric(
                            platform=platform,
                            phase="overall",
                            outcome="FAILURE",
                            error_category=error_category,
                            error_message=str(e),
                            latency_ms=latency,
                            search_id=search_id
                        )

                    logger.error(f"[Dispatcher] Worker {platform} error on attempt {attempt} (Category: {error_category}): {e}")
                    self.emit_log(search_id, platform, "error", f"Attempt {attempt} failed: {str(e)}")
                    
                    should_retry = retry_strategy["should_retry"]
                    max_retries = retry_strategy["retry_count"]
                    delay = retry_strategy["delay_seconds"]
                    
                    if not should_retry or attempt >= max_retries:
                        self.emit_ws("bot:status", {
                            "searchId": search_id,
                            "platform": platform,
                            "phase": "failed",
                            "progress": 100,
                            "error": str(e)
                        })
                        break
                    else:
                        self.emit_log(search_id, platform, "info", f"Retrying in {delay} seconds due to {error_category} error...")
                        await asyncio.sleep(delay)

    async def _execute_worker_pipeline(self, worker, task: dict, attempt: int):
        search_id = task["search_id"]
        platform = worker.platform_id
        trip = task["trip"]
        financial = task["financial"]
        cloak = task["cloak"]
        
        self.emit_ws("bot:status", {
            "searchId": search_id,
            "platform": platform,
            "phase": "initializing",
            "progress": 5,
        })
        self.emit_log(search_id, platform, "info", f"Launching stealth browser context (Attempt {attempt})...")

        # 1. Acquire Proxy
        proxy = self.proxy_mgr.get_fresh_proxy(platform) if cloak.get("proxy_mode", "OFF") != "OFF" else None
        
        # 2. Spawn Browser
        browser, context, page = await self.browser_factory.create_cloak_browser(
            proxy=proxy,
            cloak_config=cloak
        )
        
        # Extract window ID (if Chromium) to track window boundaries
        window_id = 1
        try:
            # Chromium CDP session query
            cdp = await context.new_cdp_session(page)
            win_info = await cdp.send("Browser.getWindowForTarget")
            window_id = win_info.get("windowId", 1)
        except Exception:
            pass

        # Register session in manager
        session_id = f"{search_id}_{platform}_{str(uuid.uuid4())[:8]}"
        await self.session_mgr.register_session(
            session_id=session_id,
            search_id=search_id,
            platform=platform,
            browser=browser,
            context=context,
            page=page,
            window_id=window_id
        )

        try:
            # Start screenshot loop
            screenshot_task = asyncio.create_task(self._screenshot_streamer(session_id, page, search_id, platform))

            is_mock = platform == "mock"

            if is_mock:
                # ── MOCK WATERFALL PIPELINE ──
                self.emit_ws("bot:status", {"searchId": search_id, "platform": platform, "phase": "navigating", "progress": 15})
                self.emit_log(search_id, platform, "info", f"Navigating to {worker.platform_name} homepage...")
                await worker.navigate_to_search(page)
                
                self.emit_ws("bot:status", {"searchId": search_id, "platform": platform, "phase": "searching", "progress": 30})
                self.emit_log(search_id, platform, "info", f"Searching flights: {trip['origin']} -> {trip['destination']}...")
                await worker.input_search_criteria(page, trip)
                await worker.execute_search(page)
                
                # Parse flights list
                flights = await worker.parse_search_results(page)
                if not flights:
                    raise ValueError("No flights found matching search criteria.")
                
                # Sort and select target flights (top 5 cheapest or specific matching flight)
                sorted_flights = sorted(flights, key=lambda f: f["base_price"])
                if trip.get("specific_flight_number"):
                    target_flights = [f for f in sorted_flights if f["flight_number"].upper() == trip["specific_flight_number"].upper()][:1]
                    if not target_flights:
                        raise ValueError(f"Specific flight {trip['specific_flight_number']} not found.")
                else:
                    target_flights = sorted_flights[:5]
                
                selected_flight = target_flights[0]
                self.emit_log(search_id, platform, "info", f"Selected flight {selected_flight['flight_number']} (Base: Rs. {selected_flight['base_price']})")
                await worker.select_flight(page, selected_flight)
                
                # ── PASSENGER PHASE ──
                self.emit_ws("bot:status", {"searchId": search_id, "platform": platform, "phase": "passenger_details", "progress": 50})
                self.emit_log(search_id, platform, "info", "Filling passenger details and skipping add-ons...")
                await worker.fill_passenger_details(page)
                await worker.skip_addons(page)
                
                # Extract actual seats remaining from the worker's seat map check if available
                actual_seats = getattr(worker, "actual_seats_remaining", None)
                if actual_seats is not None and actual_seats > 0:
                    selected_flight["seats_remaining"] = actual_seats
                    self.emit_log(search_id, platform, "info", f"Verified actual seats remaining from seat map: {actual_seats}")

                await worker.proceed_to_checkout(page)
                
                # Verify checkout page
                if not await worker.is_at_checkout(page):
                    raise ValueError("Failed to navigate to final checkout screen.")
                
                baseline_price = await worker.parse_current_price(page)
                self.emit_log(search_id, platform, "info", f"Reached checkout. Baseline Price: Rs. {baseline_price}")

                # ── BRUTE-FORCE PHASE ──
                self.emit_ws("bot:status", {"searchId": search_id, "platform": platform, "phase": "testing_coupons", "progress": 70})
                
                # Load coupons from task schema
                coupons = list(task.get("coupons_by_platform", {}).get(platform, []))
                try:
                    onsite_coupons = await worker.scrape_onsite_coupons(page)
                    if onsite_coupons:
                        self.emit_log(search_id, platform, "info", f"Scraped {len(onsite_coupons)} onsite coupons.")
                        existing_codes = {c["code"].upper() for c in coupons}
                        for c in onsite_coupons:
                            if c["code"].upper() not in existing_codes:
                                coupons.append(c)
                except Exception as e:
                    logger.warning(f"Failed to scrape onsite coupons: {e}")
                
                # Filter coupons by airline matching for the selected flight
                coupons = [c for c in coupons if is_coupon_airline_match(c.get("description", ""), selected_flight["airline"])]

                # Run sequential coupon testing
                from coupon_brute_forcer import CouponBruteForcer
                forcer = CouponBruteForcer(worker, self.financial_filter, self.emit_log)
                bf_result = await forcer.brute_force(
                    page,
                    coupons,
                    financial,
                    search_id,
                    db=self.db,
                    route=f"{trip['origin']}-{trip['destination']}"
                )
                
                # ── CALCULATE SCORES AND SAVE ALL TARGET FLIGHTS ──
                self.emit_ws("bot:status", {"searchId": search_id, "platform": platform, "phase": "aggregating", "progress": 90})
                
                # Get set of successful coupon codes from brute force
                successful_codes = {r["code"] for r in bf_result["all_results"] if r.get("status") == "valid_match"}
                
                is_dom = is_domestic_route(trip["origin"], trip["destination"])
                price_floor = 1200.0 if is_dom else 1.0

                for idx, f in enumerate(target_flights):
                    winning_coupon = None
                    if idx == 0:
                        f_base = baseline_price
                        f_coupon = bf_result["best_coupon"]
                        f_savings = min(bf_result["savings"], f_base)
                        f_final = max(price_floor, f_base - f_savings)
                        f_savings = max(0.0, f_base - f_final)
                        if f_coupon:
                            winning_coupon = next((c for c in coupons if c["code"].upper() == f_coupon.upper()), None)
                    else:
                        f_base = f["base_price"]
                        # Offline mathematical matching on successful codes
                        best_discount = 0.0
                        passed_coupons, _ = self.financial_filter.filter_coupons(coupons, financial)
                        for coupon in passed_coupons:
                            if coupon["code"] not in successful_codes:
                                continue
                            # Apply airline match filter
                            if not is_coupon_airline_match(coupon.get("description", ""), f["airline"]):
                                continue
                            min_booking = coupon.get("min_booking_value") or 0.0
                            if f_base >= min_booking:
                                discount = 0.0
                                val = coupon.get("discount_value") or 0.0
                                if coupon.get("discount_type") == "PERCENT":
                                    discount = f_base * (val / 100.0)
                                    max_disc = coupon.get("max_discount")
                                    if max_disc and discount > max_disc:
                                        discount = max_disc
                                else:
                                    discount = val
                                    
                                # Calculate net EMI savings for this offline coupon
                                from savings_stacker import calculate_net_emi_savings
                                net_discount, interest_cost, emi_warning = calculate_net_emi_savings(
                                    coupon_code=coupon["code"],
                                    coupon_desc=coupon.get("description", ""),
                                    requires_emi=coupon.get("requires_emi", False),
                                    base_price=f_base,
                                    face_discount=discount
                                )
                                if net_discount > best_discount:
                                    best_discount = net_discount
                                    winning_coupon = coupon
                        
                        f_coupon = winning_coupon["code"] if winning_coupon else ""
                        f_savings = best_discount
                        
                        # Apply coupon instincts check & correction
                        if self.coupon_instincts and f_coupon:
                            corrected_savings = await self.coupon_instincts.audit_and_correct(
                                platform=platform,
                                coupon_code=f_coupon,
                                base_price=f_base,
                                calculated_discount=f_savings,
                                is_domestic=is_dom,
                                search_id=search_id
                            )
                            f_savings = corrected_savings
                            
                        f_savings = min(f_savings, f_base)
                        f_final = max(price_floor, f_base - f_savings)
                        f_savings = max(0.0, f_base - f_final)
                    
                    # Stacking savings
                    bank_restriction = None
                    if winning_coupon:
                        bank_restriction = winning_coupon.get("bank") or winning_coupon.get("bank_restriction")

                    savings_breakdown = await self.savings_stacker.calculate_all_savings(
                        platform=platform,
                        checkout_price=f_final,
                        financial_profile=financial,
                        bank_restriction=bank_restriction
                    )
                    
                    # Calculate and layer in EMI interest overhead into the final effective price!
                    if winning_coupon:
                        from savings_stacker import calculate_net_emi_savings
                        orig_face_discount = f_savings
                        if idx == 0:
                            matching_r = next((r for r in bf_result["all_results"] if r["code"].upper() == f_coupon.upper()), None)
                            if matching_r:
                                orig_face_discount = matching_r.get("face_savings", f_savings)
                        else:
                            orig_face_discount = 0.0
                            if winning_coupon:
                                val = winning_coupon.get("discount_value") or 0.0
                                if winning_coupon.get("discount_type") == "PERCENT":
                                    orig_face_discount = f_base * (val / 100.0)
                                    max_disc = winning_coupon.get("max_discount")
                                    if max_disc and orig_face_discount > max_disc:
                                        orig_face_discount = max_disc
                                else:
                                    orig_face_discount = val
                                    
                        _, interest_cost, emi_warning = calculate_net_emi_savings(
                            coupon_code=f_coupon,
                            coupon_desc=winning_coupon.get("description", ""),
                            requires_emi=winning_coupon.get("requires_emi", False),
                            base_price=f_base,
                            face_discount=orig_face_discount
                        )
                        if interest_cost > 0:
                            savings_breakdown["emi_interest"] = interest_cost
                            savings_breakdown["emi_warning"] = emi_warning
                            savings_breakdown["effective_price"] += interest_cost
                            if "instructions" not in savings_breakdown:
                                savings_breakdown["instructions"] = []
                            savings_breakdown["instructions"].append(f"⚠️ {emi_warning}")
                    
                    effective_price = savings_breakdown["effective_price"]
                    
                    # Deal score
                    deal_score = await self.deal_scorer.calculate_score(
                        route=f"{trip['origin']}-{trip['destination']}",
                        final_price=f_final,
                        coupon_savings=f_savings,
                        auxiliary_savings=savings_breakdown["total_stacking_savings"],
                        date_alternatives=task.get("date_alternatives")
                    )
                    
                    # Save final result to SQLite
                    result = {
                        "id": str(uuid.uuid4()),
                        "search_id": search_id,
                        "platform": platform,
                        "flight_number": f["flight_number"],
                        "airline": f["airline"],
                        "departure_time": f["departure_time"],
                        "arrival_time": f["arrival_time"],
                        "duration": f["duration"],
                        "stops": f["stops"],
                        "base_price": f_base,
                        "final_price": f_final,
                        "best_coupon_code": f_coupon,
                        "savings": f_savings,
                        "effective_price": effective_price,
                        "deal_score": deal_score,
                        "all_tested_coupons": bf_result["all_results"] if idx == 0 else [],
                        "savings_breakdown": savings_breakdown,
                        "session_id": session_id if idx == 0 else None,
                        "rank": 1,
                        "departure_date": trip["departure_date"]
                    }
                    await self.db.save_result(result)
                    self.emit_ws("search:results", result)
                    
                    # Log actual observed price to DB
                    try:
                        observed_at = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
                        seats_remaining = f.get("seats_remaining", 15)
                        await self.db.db.execute("""
                            INSERT INTO observed_prices (route_key, airline, observed_at_timestamp, price, fare_class, seats_remaining_hint)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (f"{trip['origin']}-{trip['destination']}", f["airline"], observed_at, f_final, "Y", seats_remaining))
                        await self.db.db.commit()
                    except Exception as e:
                        logger.warning(f"Failed to log price observation: {e}")
                        
                    # Also log price to price_history
                    await self.db.log_price(
                        route=f"{trip['origin']}-{trip['destination']}",
                        departure_date=trip["departure_date"],
                        airline=f["airline"],
                        flight_number=f["flight_number"],
                        price=f_final,
                        platform=platform,
                        cabin_class=trip["cabin_class"]
                    )
                
                # Update session status to READY_FOR_HANDOFF so user can book it
                await self.session_mgr.set_session_ready(session_id)
                
                self.emit_ws("bot:status", {
                    "searchId": search_id,
                    "platform": platform,
                    "phase": "completed",
                    "progress": 100,
                    "currentBestPrice": bf_result["best_price"],
                    "currentCouponCode": bf_result["best_coupon"]
                })
                self.emit_log(search_id, platform, "success", f"Pipeline completed! Best Price: Rs. {bf_result['best_price']} (Saved Rs. {bf_result['savings']})")

            else:
                # ── REAL SITE SIMPLIFIED FLOW (GOOGLE FLIGHTS) ──
                self.emit_ws("bot:status", {"searchId": search_id, "platform": platform, "phase": "navigating", "progress": 15})
                self.emit_log(search_id, platform, "info", f"Navigating to {worker.platform_name}...")
                await worker.navigate_to_search(page)
                
                self.emit_ws("bot:status", {"searchId": search_id, "platform": platform, "phase": "searching", "progress": 40})
                self.emit_log(search_id, platform, "info", f"Searching flights: {trip['origin']} -> {trip['destination']}...")
                await worker.input_search_criteria(page, trip)
                await worker.execute_search(page)
                
                self.emit_ws("bot:status", {"searchId": search_id, "platform": platform, "phase": "aggregating", "progress": 70})
                # Parse flights list
                flights = await worker.parse_search_results(page)
                if not flights:
                    raise ValueError(f"No flights found on {worker.platform_name} matching search criteria.")
                
                # Sort and select target flights (top 5 cheapest or specific matching flight)
                sorted_flights = sorted(flights, key=lambda f: f["base_price"])
                if trip.get("specific_flight_number"):
                    target_flights = [f for f in sorted_flights if f["flight_number"].upper() == trip["specific_flight_number"].upper()][:1]
                    if not target_flights:
                        raise ValueError(f"Specific flight {trip['specific_flight_number']} not found.")
                else:
                    target_flights = sorted_flights[:5]
                
                # Load coupons from task schema
                coupons = list(task.get("coupons_by_platform", {}).get(platform, []))
                try:
                    onsite_coupons = await worker.scrape_onsite_coupons(page)
                    if onsite_coupons:
                        self.emit_log(search_id, platform, "info", f"Scraped {len(onsite_coupons)} onsite coupons.")
                        existing_codes = {c["code"].upper() for c in coupons}
                        for c in onsite_coupons:
                            if c["code"].upper() not in existing_codes:
                                coupons.append(c)
                except Exception as e:
                    logger.warning(f"Failed to scrape onsite coupons: {e}")
                
                for idx, f in enumerate(target_flights):
                    f_base = f["base_price"]
                    f_coupon = ""
                    f_savings = 0.0
                    
                    is_dom = is_domestic_route(trip["origin"], trip["destination"])
                    price_floor = 1200.0 if is_dom else 1.0
                    f_final = max(price_floor, f_base)
                    winning_coupon = None
                    
                    # Offline mathematical coupon matching
                    if coupons:
                        passed_coupons, _ = self.financial_filter.filter_coupons(coupons, financial)
                        best_discount = 0.0
                        for coupon in passed_coupons:
                            # Apply airline match filter
                            if not is_coupon_airline_match(coupon.get("description", ""), f["airline"]):
                                continue
                            min_booking = coupon.get("min_booking_value") or 0.0
                            if f_base >= min_booking:
                                discount = 0.0
                                val = coupon.get("discount_value") or 0.0
                                if coupon.get("discount_type") == "PERCENT":
                                    discount = f_base * (val / 100.0)
                                    max_disc = coupon.get("max_discount")
                                    if max_disc and discount > max_disc:
                                        discount = max_disc
                                else:
                                    discount = val
                                if discount > best_discount:
                                    best_discount = discount
                                    winning_coupon = coupon
                        
                        if winning_coupon:
                            f_savings = best_discount
                            f_coupon = winning_coupon["code"]
                            
                            # Apply coupon instincts check & correction
                            if self.coupon_instincts:
                                corrected_savings = await self.coupon_instincts.audit_and_correct(
                                    platform=platform,
                                    coupon_code=f_coupon,
                                    base_price=f_base,
                                    calculated_discount=f_savings,
                                    is_domestic=is_dom,
                                    search_id=search_id
                                )
                                f_savings = corrected_savings

                            f_final = max(price_floor, f_base - f_savings)
                            f_savings = max(0.0, f_base - f_final)
                            if idx == 0:
                                self.emit_log(search_id, platform, "success", f"Mathematically matched best coupon: {f_coupon} (saves Rs. {f_savings})")
                        else:
                            f_final = max(price_floor, f_base)
                            f_savings = max(0.0, f_base - f_final)
                    else:
                        f_final = max(price_floor, f_base)
                        f_savings = max(0.0, f_base - f_final)
                    
                    # Stacking savings
                    bank_restriction = None
                    if winning_coupon and f_coupon:
                        bank_restriction = winning_coupon.get("bank") or winning_coupon.get("bank_restriction")

                    savings_breakdown = await self.savings_stacker.calculate_all_savings(
                        platform=platform,
                        checkout_price=f_final,
                        financial_profile=financial,
                        bank_restriction=bank_restriction
                    )
                    effective_price = savings_breakdown["effective_price"]
                    
                    # Deal score
                    deal_score = await self.deal_scorer.calculate_score(
                        route=f"{trip['origin']}-{trip['destination']}",
                        final_price=f_final,
                        coupon_savings=f_savings,
                        auxiliary_savings=savings_breakdown["total_stacking_savings"],
                        date_alternatives=task.get("date_alternatives")
                    )
                    
                    # Save final result to SQLite
                    result = {
                        "id": str(uuid.uuid4()),
                        "search_id": search_id,
                        "platform": platform,
                        "flight_number": f["flight_number"],
                        "airline": f["airline"],
                        "departure_time": f["departure_time"],
                        "arrival_time": f["arrival_time"],
                        "duration": f["duration"],
                        "stops": f["stops"],
                        "base_price": f_base,
                        "final_price": f_final,
                        "best_coupon_code": f_coupon,
                        "savings": f_savings,
                        "effective_price": effective_price,
                        "deal_score": deal_score,
                        "all_tested_coupons": [],
                        "savings_breakdown": savings_breakdown,
                        "session_id": session_id if idx == 0 else None,
                        "rank": 1,
                        "departure_date": trip["departure_date"]
                    }
                    await self.db.save_result(result)
                    self.emit_ws("search:results", result)
                    
                    # Log observed prices to DB
                    try:
                        observed_at = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
                        await self.db.db.execute("""
                            INSERT INTO observed_prices (route_key, airline, observed_at_timestamp, price, fare_class, seats_remaining_hint)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (f"{trip['origin']}-{trip['destination']}", f["airline"], observed_at, f_final, "Y", 15))
                        await self.db.db.commit()
                    except Exception as e:
                        logger.warning(f"Failed to log price observation: {e}")
                        
                    # Also log price to price_history
                    await self.db.log_price(
                        route=f"{trip['origin']}-{trip['destination']}",
                        departure_date=trip["departure_date"],
                        airline=f["airline"],
                        flight_number=f["flight_number"],
                        price=f_final,
                        platform=platform,
                        cabin_class=trip["cabin_class"]
                    )
                
                # Update session status to READY_FOR_HANDOFF so user can book it
                await self.session_mgr.set_session_ready(session_id)
                
                self.emit_ws("bot:status", {
                    "searchId": search_id,
                    "platform": platform,
                    "phase": "completed",
                    "progress": 100,
                    "currentBestPrice": target_flights[0]["base_price"] - (target_flights[0]["base_price"] - f_final if f_coupon else 0),
                    "currentCouponCode": f_coupon
                })
                self.emit_log(search_id, platform, "success", f"Scrape completed! Cheapest flight: Rs. {target_flights[0]['base_price']}")
            
            # Keep browser open and context running for handoff!
            screenshot_task.cancel()

        except Exception as e:
            # Terminate and clean up context on failure
            await self.session_mgr.close_session(session_id)
            if 'screenshot_task' in locals() and not screenshot_task.done():
                screenshot_task.cancel()
            raise e
        finally:
            self.proxy_mgr.release_proxy(platform)

    async def _screenshot_streamer(self, session_id: str, page, search_id: str, platform: str):
        """Take a screenshot of the browser page every 2 seconds and stream it to UI."""
        await asyncio.sleep(2.0)
        while True:
            try:
                if page.is_closed():
                    break
                
                # Take low-quality screenshot to save CPU/Network bandwidth
                b64 = await page.screenshot(type="jpeg", quality=40, scale="css")
                import base64
                encoded = base64.b64encode(b64).decode("utf-8")
                
                self.emit_ws("bot:screenshot", {
                    "searchId": search_id,
                    "platform": platform,
                    "sessionId": session_id,
                    "imageBase64": encoded,
                    "timestamp": datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
                })
            except asyncio.CancelledError:
                break
            except Exception:
                pass
            await asyncio.sleep(2.5)

    def emit_log(self, search_id: str, platform: str, level: str, message: str):
        """Emit log entry to the UI console feed."""
        logger.info(f"[{platform.upper()}] {message}")
        self.emit_ws("bot:log", {
            "searchId": search_id,
            "platform": platform,
            "level": level,
            "message": message,
            "timestamp": datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        })

    def _create_worker(self, platform: str, db_platforms: dict = None):
        if platform == "mock":
            return MockWorker()
            
        url_map = {
            "makemytrip": ("MakeMyTrip", "https://www.makemytrip.com/"),
            "easemytrip": ("EaseMyTrip", "https://www.easemytrip.com/"),
            "cleartrip": ("Cleartrip", "https://www.cleartrip.com/"),
            "yatra": ("Yatra", "https://www.yatra.com/"),
            "ixigo": ("Ixigo", "https://www.ixigo.com/"),
            "paytm": ("Paytm Flights", "https://tickets.paytm.com/flights/"),
            "google_flights": ("Google Flights", "https://www.google.com/flights")
        }
        
        if db_platforms:
            url_map.update(db_platforms)
            
        if platform == "makemytrip":
            return MakeMyTripWorker()
        elif platform == "easemytrip":
            return EaseMyTripWorker()
        elif platform == "cleartrip":
            return CleartripWorker()
        elif platform == "google_flights":
            return GoogleFlightsWorker()
        elif platform in url_map:
            # Fallback for PayTM, Yatra, Ixigo
            name, url = url_map[platform]
            return AIWorker(platform_id=platform, platform_name=name, base_url=url)
            
        return None

