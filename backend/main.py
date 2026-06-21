"""
Flight Finder — FastAPI Backend + WebSocket Server
Main entry point. Handles all WebSocket IPC with the Electron/React frontend.
"""

import asyncio
import sys
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
import json
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Body
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from coupon_db import CouponDB
from compiler import TaskCompiler
from dispatcher import Dispatcher
from session_manager import SessionManager
from financial_filter import FinancialFilter
from price_tracker import PriceTracker
from deal_scorer import DealScorer
from savings_stacker import SavingsStacker
from coupon_harvester import CouponHarvester
from price_predictor import PricePredictor
from vision_intake import VisionIntake
from text_ai import TextAI
from coupon_instincts import CouponInstinctsEngine
from learning_engine import SelfLearningEngine
from user_preferences import UserPreferences
from pipeline_monitor import PipelineMonitor

# ── Configure Logging ──
LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
logger.add(LOG_DIR / "app.log", rotation="10 MB", retention="7 days", level="INFO")

# ── Core Services (initialized on startup) ──
db: Optional[CouponDB] = None
compiler: Optional[TaskCompiler] = None
dispatcher: Optional[Dispatcher] = None
session_mgr: Optional[SessionManager] = None
financial_filter: Optional[FinancialFilter] = None
price_tracker: Optional[PriceTracker] = None
deal_scorer: Optional[DealScorer] = None
savings_stacker: Optional[SavingsStacker] = None
coupon_harvester: Optional[CouponHarvester] = None
price_predictor: Optional[PricePredictor] = None
vision_intake: Optional[VisionIntake] = None
text_ai: Optional[TextAI] = None
smart_advisor: Optional[object] = None
coupon_instincts: Optional[CouponInstinctsEngine] = None
learning_engine: Optional[SelfLearningEngine] = None
user_prefs: Optional[UserPreferences] = None
pipeline_monitor: Optional[PipelineMonitor] = None



# ── Active WebSocket connections ──
active_connections: list[WebSocket] = []


async def broadcast(message: dict):
    """Send a message to all connected WebSocket clients."""
    data = json.dumps(message, default=str)
    disconnected = []
    for ws in active_connections:
        try:
            await ws.send_text(data)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        active_connections.remove(ws)


def emit_ws(msg_type: str, payload: dict):
    """Fire-and-forget WebSocket broadcast (schedules on event loop)."""
    message = {"type": msg_type, "payload": payload}
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(broadcast(message))
    except RuntimeError:
        pass


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Modern FastAPI lifespan handler for startup/shutdown."""
    global db, compiler, dispatcher, session_mgr, financial_filter
    global price_tracker, deal_scorer, savings_stacker, coupon_harvester
    global price_predictor, vision_intake, text_ai, smart_advisor, coupon_instincts
    global learning_engine, user_prefs, pipeline_monitor

    logger.info("🛫 Flight Finder backend starting...")

    # Initialize database
    db = CouponDB()
    await db.initialize()
    logger.info("✅ Database initialized")

    # Seed airport alternatives on startup
    await db.seed_airport_alternatives()

    # Initialize services
    financial_filter = FinancialFilter()
    price_tracker = PriceTracker(db)
    deal_scorer = DealScorer(price_tracker)
    savings_stacker = SavingsStacker(db)
    coupon_harvester = CouponHarvester(db)
    coupon_instincts = CouponInstinctsEngine(db)
    await coupon_instincts.initialize()
    vision_intake = VisionIntake()
    text_ai = TextAI()
    price_predictor = PricePredictor(db)
    
    # Initialize self-learning services
    learning_engine = SelfLearningEngine(db)
    user_prefs = UserPreferences(db)
    pipeline_monitor = PipelineMonitor(db)

    from smart_advisor import SmartAdvisor
    smart_advisor = SmartAdvisor(db, price_predictor, user_prefs)
    compiler = TaskCompiler(db, text_ai)
    session_mgr = SessionManager(emit_ws)
    dispatcher = Dispatcher(
        db=db,
        session_mgr=session_mgr,
        financial_filter=financial_filter,
        deal_scorer=deal_scorer,
        savings_stacker=savings_stacker,
        emit_ws=emit_ws,
        smart_advisor=smart_advisor,
        coupon_instincts=coupon_instincts,
        pipeline_monitor=pipeline_monitor
    )

    logger.info("✅ All services initialized")
    from api_key_manager import api_key_manager
    api_key_manager.register_broadcast_callback(emit_ws)
    asyncio.create_task(api_key_recharger_loop())
    asyncio.create_task(watchlist_scheduler_loop())

    # Schedule background self-learning cycle loop (runs every 6 hours)
    async def learning_cycle_loop():
        # Short initial delay to let startup finalize
        await asyncio.sleep(10)
        while True:
            try:
                await learning_engine.run_learning_cycle()
                await user_prefs.learn_preferences()
            except Exception as e:
                logger.error(f"[LearningLoop] Error in learning cycle: {e}")
            await asyncio.sleep(6 * 3600)
    asyncio.create_task(learning_cycle_loop())

    yield  # App is running

    # Shutdown
    logger.info("🛬 Flight Finder backend shutting down...")
    if session_mgr:
        await session_mgr.cleanup_all()
    if db:
        await db.close()


# ── App Init ──
app = FastAPI(title="Flight Finder Backend", version="1.0.0", lifespan=lifespan)

# ── CORS Middleware ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    active_connections.append(ws)
    logger.info(f"🔌 WebSocket client connected (total: {len(active_connections)})")

    try:
        while True:
            raw = await ws.receive_text()
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_text(json.dumps({
                    "type": "error",
                    "payload": {"message": "Invalid JSON"}
                }))
                continue

            msg_type = message.get("type", "")
            payload = message.get("payload", {})

            logger.info(f"📨 Received: {msg_type}")

            # ── Route messages to handlers ──
            try:
                await handle_message(msg_type, payload, ws)
            except Exception as e:
                logger.error(f"Error handling {msg_type}: {e}")
                await ws.send_text(json.dumps({
                    "type": "error",
                    "payload": {"message": str(e), "originalType": msg_type}
                }))

    except WebSocketDisconnect:
        active_connections.remove(ws)
        logger.info(f"🔌 WebSocket client disconnected (total: {len(active_connections)})")


async def handle_message(msg_type: str, payload: dict, ws: WebSocket):
    """Route incoming WebSocket messages to appropriate handlers."""

    # ── API Status ──
    if msg_type == "api:status:get":
        from api_key_manager import api_key_manager
        status_list = api_key_manager.get_status_list()
        await ws.send_text(json.dumps({
            "type": "api:status:data",
            "payload": status_list
        }))
        return

    # ── Search Operations ──
    elif msg_type == "search:start":
        search_id = str(uuid.uuid4())
        payload["searchId"] = search_id

        # Track search pattern
        if user_prefs:
            await user_prefs.record_search(search_id, payload.get("trip", {}))

        # Quick harvest external coupons before compiling task
        await coupon_harvester.quick_harvest(payload.get("platforms", []))

        # Compile task schema
        task = await compiler.compile(payload)

        # Dispatch parallel workers
        asyncio.create_task(dispatcher.dispatch_all(task))

        await ws.send_text(json.dumps({
            "type": "search:started",
            "payload": {"searchId": search_id}
        }))

    elif msg_type == "search:cancel":
        search_id = payload.get("searchId")
        if search_id and dispatcher:
            await dispatcher.cancel_search(search_id)

    elif msg_type == "search:history:get":
        if db:
            history = await db.get_searches()
            await ws.send_text(json.dumps({
                "type": "search:history:data",
                "payload": history
            }))

    elif msg_type == "search:history:results:get":
        search_id = payload.get("searchId")
        if db and search_id:
            results = await db.get_search_results(search_id)
            await ws.send_text(json.dumps({
                "type": "search:history:results:data",
                "payload": {"searchId": search_id, "results": results}
            }))

    # ── Session / Handoff ──
    elif msg_type == "session:handoff":
        session_id = payload.get("sessionId")
        if session_id and session_mgr:
            await session_mgr.handoff_to_user(session_id)
            
            # Record handoff preference
            if db and user_prefs:
                try:
                    async with db.db.execute("SELECT search_id FROM sessions WHERE id = ?", (session_id,)) as cur:
                        row = await cur.fetchone()
                        if row:
                            await user_prefs.record_handoff(row[0])
                except Exception as e:
                    logger.warning(f"Failed to record handoff tracking: {e}")

    elif msg_type == "session:check":
        session_id = payload.get("sessionId")
        if session_id and session_mgr:
            status = session_mgr.get_session_status(session_id)
            await ws.send_text(json.dumps({
                "type": "session:status",
                "payload": {"sessionId": session_id, "status": status}
            }))

    # ── AI Vision ──
    elif msg_type == "ai:extract":
        image_b64 = payload.get("imageBase64", "")
        if vision_intake:
            result = await vision_intake.extract_trip_details(image_b64)
            await ws.send_text(json.dumps({
                "type": "ai:result",
                "payload": result
            }))

    # ── Platform / Site Operations ──
    elif msg_type == "platform:list":
        if db:
            platforms_list = await db.get_platforms()
            await ws.send_text(json.dumps({
                "type": "platform:list:data",
                "payload": platforms_list
            }))

    elif msg_type == "platform:add":
        name = payload.get("name")
        url = payload.get("url")
        if db and name and url:
            # Check if url is reachable (legit check)
            is_legit = False
            try:
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    # Disable SSL verification for reachability check and use a realistic User-Agent
                    headers = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    }
                    async with session.get(url, timeout=5, ssl=False, headers=headers) as resp:
                        # Any response code (including 403 Forbidden or 405) indicates the server is active and reachable
                        if resp.status < 500 or resp.status in (502, 503, 504):
                            is_legit = True
            except Exception as e:
                logger.warning(f"Reachability check failed for {url}: {e}")
                
            if is_legit:
                new_id = await db.add_platform(name, url)
                platforms_list = await db.get_platforms()
                await ws.send_text(json.dumps({
                    "type": "platform:list:data",
                    "payload": platforms_list
                }))
            else:
                await ws.send_text(json.dumps({
                    "type": "error",
                    "payload": {"message": f"Website {url} could not be verified or is unreachable. Not adding."}
                }))

    elif msg_type == "platform:deactivate":
        platform_id = payload.get("platformId")
        if db and platform_id:
            await db.deactivate_platform(platform_id)
            # Send updated list
            platforms_list = await db.get_platforms()
            await ws.send_text(json.dumps({
                "type": "platform:list:data",
                "payload": platforms_list
            }))

    # ── Coupon Operations ──
    elif msg_type == "coupon:list":
        platform = payload.get("platform")
        if db and platform:
            coupons = await db.get_coupons_for_platform(platform)
            await ws.send_text(json.dumps({
                "type": "coupon:list:result",
                "payload": {"platform": platform, "coupons": coupons}
            }))

    elif msg_type == "coupon:add":
        if db:
            await db.add_coupon(payload)
            await ws.send_text(json.dumps({
                "type": "coupon:added",
                "payload": {"code": payload.get("code")}
            }))

    elif msg_type == "coupon:refresh":
        platforms = payload.get("platforms")
        if coupon_harvester:
            asyncio.create_task(coupon_harvester.deep_harvest(platforms))
            await ws.send_text(json.dumps({
                "type": "coupon:refresh:started",
                "payload": {}
            }))

    # ── Settings ──
    elif msg_type == "settings:get":
        config_path = Path(__file__).parent.parent / "config" / "user_profile.json"
        profile = {}
        if config_path.exists():
            profile = json.loads(config_path.read_text(encoding="utf-8"))
        await ws.send_text(json.dumps({
            "type": "settings:data",
            "payload": profile
        }))

    elif msg_type == "settings:update":
        config_path = Path(__file__).parent.parent / "config" / "user_profile.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        await ws.send_text(json.dumps({
            "type": "settings:saved",
            "payload": {}
        }))

    # ── Self-Learning Intelligence ──
    elif msg_type == "learning:dashboard:get":
        if learning_engine:
            data = await learning_engine.get_dashboard_data()
            await ws.send_text(json.dumps({
                "type": "learning:dashboard:data",
                "payload": data
            }))

    elif msg_type == "learning:journal:get":
        if db:
            try:
                async with db.db.execute("""
                    SELECT category, action, reason, before_value, after_value, recorded_at
                    FROM process_journal ORDER BY recorded_at DESC LIMIT 50
                """) as cur:
                    rows = await cur.fetchall()
                    journal = [dict(r) for r in rows]
                await ws.send_text(json.dumps({
                    "type": "learning:journal:data",
                    "payload": journal
                }))
            except Exception as e:
                logger.error(f"Failed to fetch journal: {e}")

    elif msg_type == "suggestion:click":
        suggestion_id = payload.get("suggestionId")
        if db and suggestion_id:
            await db.record_suggestion_click(suggestion_id)
            await ws.send_text(json.dumps({
                "type": "suggestion:clicked",
                "payload": {"suggestionId": suggestion_id}
            }))

    elif msg_type == "suggestion:accept":
        suggestion_id = payload.get("suggestionId")
        if db and suggestion_id:
            await db.record_suggestion_accept(suggestion_id)
            await ws.send_text(json.dumps({
                "type": "suggestion:accepted",
                "payload": {"suggestionId": suggestion_id}
            }))

    elif msg_type == "preferences:get":
        if user_prefs:
            profile = await user_prefs.get_profile()
            await ws.send_text(json.dumps({
                "type": "preferences:data",
                "payload": profile
            }))

    elif msg_type == "search:nlp_parse":
        text = payload.get("text", "")
        if text_ai:
            parsed = await text_ai.parse_trip_nlp(text)
            await ws.send_text(json.dumps({
                "type": "search:nlp_parsed",
                "payload": parsed
            }))
            

    # ── Price History ──
    elif msg_type == "history:get":
        route = payload.get("route", "")
        days = payload.get("days", 30)
        if price_tracker:
            history = await price_tracker.get_history(route, days)
            await ws.send_text(json.dumps({
                "type": "history:data",
                "payload": {"route": route, "history": history}
            }))

    # ── Price Prediction ──
    elif msg_type == "predict:get":
        route = payload.get("route", "")
        date = payload.get("date", "")
        if price_predictor:
            prediction = await price_predictor.predict(route, date)
            await ws.send_text(json.dumps({
                "type": "predict:result",
                "payload": prediction
            }))

    # ── Watchlist ──
    elif msg_type == "watchlist:add":
        if db:
            await db.add_watchlist_item(payload)
            await ws.send_text(json.dumps({
                "type": "watchlist:added", "payload": {}
            }))

    elif msg_type == "watchlist:remove":
        watch_id = payload.get("watchId")
        if db and watch_id:
            await db.remove_watchlist_item(watch_id)

    elif msg_type == "watchlist:list":
        if db:
            items = await db.get_watchlist()
            await ws.send_text(json.dumps({
                "type": "watchlist:data",
                "payload": {"items": items}
            }))

    # ── Proxy Test ──
    elif msg_type == "proxy:test":
        from proxy_manager import ProxyManager
        pm = ProxyManager()
        result = await pm.test_connection(payload)
        await ws.send_text(json.dumps({
            "type": "proxy:test:result",
            "payload": result
        }))

    else:
        logger.warning(f"Unknown message type: {msg_type}")


async def watchlist_scheduler_loop():
    """
    Background loop that sweeps active watchlist items hourly.
    If a route exhibits high volatility (price_velocity > 10% change in 12 hours),
    it dynamically schedules hourly scrapes for that route for the next 24 hours.
    Otherwise, sweeps run according to normal daily/weekly frequency.
    """
    logger.info("[WatchlistScheduler] Starting watchlist background loop...")
    high_frequency_routes = {}  # route_key: expiration_timestamp
    
    while True:
        try:
            if db and dispatcher:
                items = await db.get_watchlist()
                now = datetime.now()
                
                # Clean expired high frequency routes
                expired_routes = [r for r, exp in high_frequency_routes.items() if now > exp]
                for r in expired_routes:
                    del high_frequency_routes[r]
                
                for item in items:
                    route = f"{item['origin']}-{item['destination']}"
                    
                    # Check if we need to run a check now
                    should_run = False
                    
                    # Check if route is marked for high-frequency (volatility trigger)
                    if route in high_frequency_routes:
                        should_run = True
                    else:
                        # Regular frequency check
                        freq = item.get("check_frequency", "daily")
                        last_checked_str = item.get("last_checked")
                        if not last_checked_str:
                            should_run = True
                        else:
                            last_checked = datetime.fromisoformat(last_checked_str)
                            elapsed = (now - last_checked).total_seconds()
                            if freq == "hourly" and elapsed >= 3600:
                                should_run = True
                            elif freq == "daily" and elapsed >= 86400:
                                should_run = True
                            elif freq == "weekly" and elapsed >= 86400 * 7:
                                should_run = True

                    if should_run:
                        logger.info(f"[WatchlistScheduler] Triggering run for {route} (freq: {item.get('check_frequency')})")
                        
                        # Compile task payload for Dispatcher
                        task_payload = {
                            "origin": item["origin"],
                            "destination": item["destination"],
                            "departure_date": item["departure_date"],
                            "return_date": None,
                            "passenger_count": 1,
                            "cabin_class": "ECONOMY",
                            "platforms": ["mock"],  # Default mock platform
                            "cloak": {"proxy_mode": "OFF", "max_concurrent_bots": 2},
                            "financial": {
                                "bank_cards": [],
                                "wallet_providers": [],
                                "emi_eligible": False,
                                "bnpl_eligible": False
                            }
                        }
                        
                        # Compile task and trigger search
                        task = await compiler.compile(task_payload)
                        
                        # Monitor results in the background
                        async def run_search_and_check_alerts(t_task, t_item):
                            try:
                                await dispatcher.dispatch_all(t_task)
                                
                                # Fetch final price saved for this search
                                q = "SELECT final_price FROM search_results WHERE search_id = ? ORDER BY final_price ASC LIMIT 1"
                                async with db.db.execute(q, (t_task["search_id"],)) as cur:
                                    row = await cur.fetchone()
                                    if row:
                                        final_price = row[0]
                                        target_price = t_item.get("target_price")
                                        logger.info(f"[WatchlistScheduler] Best price for {route}: Rs. {final_price} (Target: {target_price})")
                                        
                                        # Check volatility (compare last price with price 12h ago)
                                        hist_q = """
                                            SELECT price FROM price_history 
                                            WHERE route = ? AND recorded_at >= ?
                                            ORDER BY recorded_at ASC
                                        """
                                        twelve_hours_ago = (datetime.now() - timedelta(hours=12)).isoformat()
                                        async with db.db.execute(hist_q, (route, twelve_hours_ago)) as hist_cur:
                                            prices = [r[0] for r in await hist_cur.fetchall()]
                                            if len(prices) >= 2:
                                                old_price = prices[0]
                                                new_price = prices[-1]
                                                pct_change = abs(new_price - old_price) / old_price
                                                if pct_change >= 0.10:  # > 10% volatility trigger
                                                    high_frequency_routes[route] = datetime.now() + timedelta(hours=24)
                                                    logger.warning(f"[WatchlistScheduler] HIGH VOLATILITY detected on {route} ({pct_change*100:.1f}% change). Escalating to hourly cadence for 24h.")
                                        
                                        # Trigger alerts if price is below target
                                        if target_price and final_price <= target_price:
                                            logger.success(f"[WatchlistScheduler] Watchlist target met for {route}! Price: {final_price} <= {target_price}")
                                            
                                            # Add notification
                                            title = f"Price Drop Alert: {route}"
                                            message = f"Good news! The flight price for {route} on {t_item['departure_date']} has dropped to Rs. {int(final_price)}, which is below your target of Rs. {int(target_price)}."
                                            await db.add_notification(
                                                notif_type="watchlist_alert",
                                                title=title,
                                                message=message,
                                                data={"route": route, "price": final_price, "target": target_price}
                                            )
                                            
                                            # Broadcast to WebSockets
                                            emit_ws("watchlist:alert", {
                                                "route": route,
                                                "departureDate": t_item["departure_date"],
                                                "currentPrice": final_price,
                                                "targetPrice": target_price,
                                                "message": message
                                            })
                                
                                # Update last checked timestamp
                                await db.db.execute(
                                    "UPDATE watchlist SET last_checked = ? WHERE id = ?",
                                    (datetime.now().isoformat(), t_item["id"])
                                )
                                await db.db.commit()
                            except Exception as ex:
                                logger.error(f"Error checking alerts for watchlist: {ex}")
                        
                        # Start checking in background
                        asyncio.create_task(run_search_and_check_alerts(task, item))
                        
            # Run checks every hour (using 10s sleep for testing / speed in real environment is 1h)
            # We will use 3600s, but check loop regularly
            await asyncio.sleep(3600)
        except Exception as e:
            logger.error(f"Error in watchlist background loop: {e}")
            await asyncio.sleep(60)


async def api_key_recharger_loop():
    """Background loop that periodically recharges exhausted API keys."""
    logger.info("[APIKeyManager] Starting API key recharger background loop...")
    from api_key_manager import api_key_manager
    while True:
        try:
            api_key_manager.recharge_keys()
        except Exception as e:
            logger.error(f"Error in API key recharger loop: {e}")
        await asyncio.sleep(5)


# ── HTTP health check ──
@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).replace(tzinfo=None).isoformat()}


@app.post("/api/search")
async def api_search(payload: dict = Body(...)):
    """Synchronously trigger search and return the completed search results."""
    from fastapi import HTTPException

    try:
        search_id = str(uuid.uuid4())
        payload["searchId"] = search_id

        # Quick harvest external coupons before compiling task
        if coupon_harvester:
            await coupon_harvester.quick_harvest(payload.get("platforms", []))

        # Compile task
        task = await compiler.compile(payload)

        # Dispatch and wait for completion
        await dispatcher.dispatch_all(task)

        # Fetch results from DB
        results = await db.get_search_results(search_id)
        
        # Fetch advisor suggestions if available
        suggestions = {}
        try:
            async with db.db.execute("SELECT suggestions FROM smart_suggestions WHERE search_id = ?", (search_id,)) as cur:
                row = await cur.fetchone()
                if row:
                    suggestions = json.loads(row[0])
        except Exception as e:
            logger.warning(f"Error fetching suggestions for api endpoint: {e}")

        return {
            "searchId": search_id,
            "results": results,
            "suggestions": suggestions
        }
    except Exception as ex:
        logger.error(f"HTTP Search endpoint failed: {ex}")
        raise HTTPException(status_code=500, detail=str(ex))



if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8765,
        ws="websockets",
        log_level="info",
    )
