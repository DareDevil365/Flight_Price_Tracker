"""
Flight Finder — FastAPI Backend + WebSocket Server
Main entry point. Handles all WebSocket IPC with the Electron/React frontend.
"""

import asyncio
import sys
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
import json
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone, date
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
from search_engine import Dispatcher
from session_manager import SessionManager
from financial_filter import FinancialFilter
from price_tracker import PriceTracker
from deal_scorer import DealScorer
from savings_stacker import SavingsStacker
from coupon_harvester import CouponHarvester
from booking_advisor import PricePredictor
from vision_intake import VisionIntake
from text_ai import TextAI
from coupon_instincts import CouponInstinctsEngine
from learning_engine import SelfLearningEngine
from user_preferences import UserPreferences
from pipeline_monitor import PipelineMonitor
from intelligence import MarketContext, SuggestionBrain
from red_room import RedRoom

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
CONFIG_DIR = Path(os.environ.get('FLIGHT_FINDER_CONFIG_DIR', str(Path(__file__).parent.parent / 'config')))
pending_jobs = set()
watch_checks = {}
market_context = suggestion_brain = red_room = None


def start_job(coroutine):
    task = asyncio.create_task(coroutine)
    pending_jobs.add(task)
    def completed(job):
        pending_jobs.discard(job)
        if not job.cancelled() and job.exception():
            logger.error(f'Background operation failed: {job.exception()}')
    task.add_done_callback(completed)
    return task


def start_request_job(operation, msg_type, payload, ws):
    """Report asynchronous request failures to the initiating UI with identity."""
    async def guarded():
        try:
            await operation()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            identity={key:payload[key] for key in ('requestId','searchId','resultId','id') if key in payload}
            await ws.send_text(json.dumps(dict(type='error',payload=dict(
                message=str(exc),originalType=msg_type,**identity))))
    return start_job(guarded())


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
        if ws in active_connections:
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
    global learning_engine, user_prefs, pipeline_monitor, market_context, suggestion_brain, red_room

    logger.info("🛫 Flight Finder backend starting...")

    # Initialize database
    db = CouponDB()
    await db.initialize()
    logger.info("✅ Database initialized")

    # Seed airport alternatives on startup
    # Legacy airport tables contain illustrative ground costs. Active planning
    # uses fresh fares and a user-entered transfer estimate instead.

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

    market_context = MarketContext(db)
    await market_context.initialize()
    suggestion_brain = SuggestionBrain(db,market_context)
    from travel_advisor import SmartAdvisor
    smart_advisor = SmartAdvisor(db, price_predictor, user_prefs, brain=suggestion_brain)
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
    def current_checkout_session(row):
        session_id=row.get('session_id')
        pending=dispatcher._pending_checkouts.get(session_id)
        return bool(session_id and session_mgr.get_session_status(session_id)!='expired'
                    and pending and pending['quote']['id']==row.get('id'))
    suggestion_brain.checkout_session_valid=current_checkout_session
    smart_advisor.checkout_session_valid=current_checkout_session

    from desktop_notifications import notify_desktop
    red_room = RedRoom(db,compiler,dispatcher,suggestion_brain,market_context,coupon_harvester,emit_ws,desktop_notify=notify_desktop)
    logger.info("✅ All services initialized")
    from api_key_manager import api_key_manager
    api_key_manager.register_broadcast_callback(emit_ws)
    background = [asyncio.create_task(api_key_recharger_loop()),
                  asyncio.create_task(watchlist_scheduler_loop()),
                  asyncio.create_task(red_room.loop()),
                  asyncio.create_task(market_context.refresh())]

    # Legacy ML and self-learning remain research-only.

    yield  # App is running

    # Shutdown
    logger.info("🛬 Flight Finder backend shutting down...")
    for task in background:
        task.cancel()
    await asyncio.gather(*background, return_exceptions=True)
    jobs = list(pending_jobs)
    for job in jobs:
        job.cancel()
    await asyncio.gather(*jobs, return_exceptions=True)
    if session_mgr:
        await dispatcher.cleanup()
    if db:
        await db.close()


# ── App Init ──
app = FastAPI(title="Flight Finder Backend", version="1.0.0", lifespan=lifespan)

# ── CORS Middleware ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    if ws.headers.get('origin') not in (None, 'http://localhost:5173', 'http://127.0.0.1:5173'):
        await ws.close(code=1008)
        return
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

            if not isinstance(message, dict):
                await ws.send_text(json.dumps({'type':'error','payload':{'message':'Request must be a JSON object'}}))
                continue
            msg_type = message.get("type", "")
            payload = message.get("payload", {})
            if not isinstance(payload, dict):
                await ws.send_text(json.dumps({'type':'error','payload':{'message':'Request payload must be an object'}}))
                continue

            logger.info(f"📨 Received: {msg_type}")

            # ── Route messages to handlers ──
            try:
                await handle_message(msg_type, payload, ws)
            except Exception as e:
                logger.error(f"Error handling {msg_type}: {e}")
                await ws.send_text(json.dumps({
                    "type": "error",
                    "payload": {"message": str(e), "originalType": msg_type, "requestId": payload.get('requestId')}
                }))

    except WebSocketDisconnect:
        pass
    finally:
        if ws in active_connections:
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

        task = await compiler.compile(payload)

        # Track search pattern
        if user_prefs:
            await user_prefs.record_search(search_id, payload.get("trip", {}))

        await ws.send_text(json.dumps({
            "type": "search:started",
            "payload": {"searchId": search_id}
        }))
        # Register the search in the UI before workers can publish its events.
        start_job(coupon_harvester.quick_harvest(task['platforms']))
        start_job(dispatcher.dispatch_all(task))

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

    elif msg_type == 'search:booking-context:get':
        sid, result_id = payload.get('searchId'), payload.get('resultId')
        async def google_context():
            try:
                report = await dispatcher.google_booking_context(sid, result_id)
            except Exception as exc:
                report = dict(searchId=sid, resultId=result_id, status='unavailable', message=str(exc))
            emit_ws('search:booking-context', report)
        start_job(google_context())

    elif msg_type == 'session:prepare':
        start_request_job(lambda:dispatcher.prepare_checkout(payload.get('searchId'),payload.get('resultId')),msg_type,payload,ws)

    elif msg_type == 'search:feedback':
        from deal_feedback import parse_feedback,merge_feedback,available_result
        sid=payload.get('searchId')
        task=dispatcher._search_tasks.get(sid)
        if not task:
            raise ValueError('Run a fresh search before refining its deals')
        rules=merge_feedback(task['financial'],parse_feedback(payload.get('text')))
        for pending in dispatcher._pending_checkouts.values():
            if pending['task'].get('search_id')==sid:
                if pending['lock'].locked():
                    raise ValueError('Wait for coupon verification to finish before changing payment restrictions.')
        task['financial']=rules
        for pending in dispatcher._pending_checkouts.values():
            if pending['task'].get('search_id')==sid:
                pending['task']['financial']=rules
        offers=[]
        for platform in task['platforms']:
            offers.extend(await db.get_live_coupons(platform))
        rows=await db.get_search_results(sid)
        available=[r for r in rows if available_result(r,rules,offers)]
        accepted=[r for r in available if r['savings_breakdown'].get('integrity',{}).get('status') in ('corroborated','checkout_verified')]
        def best(kind):
            candidates=[r for r in accepted if r['savings_breakdown'].get('verification')==kind and r['savings_breakdown'].get('direction','outbound')=='outbound']
            if kind=='checkout':
                def current_cart(row):
                    session_id=row.get('session_id')
                    if not session_id or session_mgr.get_session_status(session_id)=='expired':
                        return False
                    try:
                        observed=datetime.fromisoformat(row['savings_breakdown']['observed_at'].replace('Z','+00:00'))
                        if observed.tzinfo is None:
                            observed=observed.replace(tzinfo=timezone.utc)
                        age=datetime.now(timezone.utc)-observed.astimezone(timezone.utc)
                        return timedelta(0)<=age<timedelta(minutes=15)
                    except (TypeError,ValueError,KeyError):
                        return False
                candidates=[r for r in candidates if current_cart(r)]
            return min(candidates,key=lambda r:r['final_price']) if candidates else None
        eligible,excluded=financial_filter.filter_coupons(offers,rules)
        advice=await smart_advisor.get_advisory(task['trip'],available,search_id=sid,financial=rules)
        advice['searchId']=sid
        emit_ws('search:suggestions',advice)
        await ws.send_text(json.dumps(dict(type='deal:options',payload=dict(searchId=sid,
            excludedResultIds=[r['id'] for r in rows if r not in available],rules=rules,
            bestListed=best('listed'),bestVerified=best('checkout'),eligibleOffers=eligible,excludedOffers=excluded,
            message='Excluded unavailable payment deals. The next options compare current prices across all searched websites. Conditional card offers still require their stated payment method; advertised savings are not verified totals.'))))

    elif msg_type == 'session:verify':
        session_id = payload.get('sessionId')
        async def verify():
            try:
                await dispatcher.verify_checkout(session_id)
                emit_ws('session:verify:ack', {'sessionId':session_id, 'status':'success', 'message':'Total and coupons verified.'})
            except Exception as exc:
                pending = dispatcher._pending_checkouts.get(session_id)
                emit_ws('session:verify:ack', {'sessionId':session_id, 'status':'failed', 'message':str(exc),
                    'inProgress':bool(pending and pending['lock'].locked())})
        start_job(verify())

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
        from urllib.parse import urlparse
        name, url = (payload.get('name') or '').strip(), (payload.get('url') or '').strip()
        parsed = urlparse(url)
        if not name or parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('Provide a website name and a valid HTTPS address without credentials.')
        if name.lower().replace(' ', '') in ['makemytrip','easemytrip','cleartrip','googleflights']:
            raise ValueError('Built-in adapters cannot be overwritten by a website link.')
        await db.add_platform(name,url)
        await ws.send_text(json.dumps({'type':'platform:list:data','payload':await db.get_platforms()}))

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
            coupons = await db.get_live_coupons(platform)
            from coupon_audit import history as coupon_history
            track_record=await coupon_history(db,platform)
            await ws.send_text(json.dumps({
                "type": "coupon:list:result",
                "payload": {"platform": platform, "coupons": coupons, "trackRecord":track_record}
            }))

    elif msg_type == "coupon:add":
        if db:
            import re
            code = (payload.get('code') or '').strip().upper()
            if not re.fullmatch(r'[A-Z0-9_-]{2,40}', code):
                raise ValueError('Coupon code must contain 2–40 letters, numbers, underscores or hyphens')
            payload['code'] = code
            payload['source'] = 'user'
            if not await db.add_coupon(payload):
                raise ValueError('Coupon could not be saved')
            await ws.send_text(json.dumps({
                "type": "coupon:added",
                "payload": {"code": payload.get("code"), "platform":payload.get("platform")}
            }))

    elif msg_type == "coupon:refresh":
        platforms = payload.get("platforms")
        if coupon_harvester:
            if platforms is not None and (not isinstance(platforms,list) or not all(isinstance(p,str) for p in platforms)):
                raise ValueError('Platforms must be a list of website IDs')
            async def refresh_offers():
                offers = await coupon_harvester.deep_harvest(platforms)
                emit_ws('coupon:refresh:completed',dict(count=len(offers),status=coupon_harvester.last_status))
            start_request_job(refresh_offers,msg_type,payload,ws)
            await ws.send_text(json.dumps({
                "type": "coupon:refresh:started",
                "payload": {}
            }))

    # ── Settings ──
    elif msg_type == "settings:get":
        config_path = CONFIG_DIR / "user_profile.json"
        profile = {}
        if config_path.exists():
            profile = json.loads(config_path.read_text(encoding="utf-8"))
        await ws.send_text(json.dumps({
            "type": "settings:data",
            "payload": profile
        }))

    elif msg_type == "settings:update":
        config_path = CONFIG_DIR / "user_profile.json"
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
            compiler._validate_trip({**parsed,'tripType':'round_trip' if parsed.get('returnDate') else 'one_way'})
            await ws.send_text(json.dumps({
                "type": "search:nlp_parsed",
                "payload": parsed
            }))
            

    # Persistent background booking requests and sourced market context.
    elif msg_type == 'redroom:list':
        await ws.send_text(json.dumps(dict(type='redroom:data',payload=dict(items=await red_room.list()))))
    elif msg_type == 'redroom:add':
        rid=await red_room.add(payload)
        await red_room.emit_list()
        start_request_job(lambda:red_room.check(rid),msg_type,{**payload,'id':rid},ws)
    elif msg_type == 'redroom:remove':
        await red_room.remove(payload.get('id'))
        await red_room.emit_list()
    elif msg_type == 'redroom:check':
        start_request_job(lambda:red_room.check(payload.get('id')),msg_type,payload,ws)
    elif msg_type == 'notifications:get':
        await ws.send_text(json.dumps(dict(type='notifications:data',payload=dict(items=await db.get_notifications()))))
    elif msg_type == 'notifications:read':
        await db.mark_notification_read(payload.get('id'))
        await ws.send_text(json.dumps(dict(type='notifications:data',payload=dict(items=await db.get_notifications()))))
    elif msg_type == 'brain:get':
        route=payload.get('route')
        if not isinstance(route,str) or len(route.split('-'))!=2:
            raise ValueError('Route must contain an Indian origin and destination, for example DEL-BOM')
        origin,destination=(code.strip().upper() for code in route.split('-'))
        raw=dict(origin=origin,destination=destination,departureDate=payload.get('date'),passengerCount=payload.get('passengerCount',1),cabinClass=payload.get('cabinClass','ECONOMY'),preferredTime=payload.get('preferredTime','ANY'),maxStops=payload.get('maxStops'))
        compiler._validate_trip(raw)
        from compiler import is_domestic_route
        trip=dict(origin=origin,destination=destination,departure_date=raw['departureDate'],passenger_count=raw['passengerCount'],cabin_class=raw['cabinClass'],preferred_time=raw['preferredTime'],max_stops=raw['maxStops'],is_domestic=is_domestic_route(origin,destination))
        from brain_request import deliver_report
        start_job(deliver_report(ws,market_context,suggestion_brain,trip,payload))
    elif msg_type == 'search:explore':
        sid=payload.get('searchId')
        async def explore():
            try:
                alternatives=await dispatcher.explore_alternatives(sid,payload.get('transferBudget',2000),payload.get('hubs',['BOM','AMD']))
                emit_ws('search:alternatives',dict(searchId=sid,alternatives=alternatives))
            except Exception as exc:
                emit_ws('search:alternatives',dict(searchId=sid,alternatives=[],error=str(exc)))
        start_job(explore())

    # ── Price History ──
    elif msg_type == "history:get":
        route = payload.get("route", "")
        if db:
            history = await db.get_quotes(route, payload['date'], payload.get('passengerCount', 1), payload.get('cabinClass', 'ECONOMY'),preferred_time=payload.get('preferredTime','ANY'),max_stops=payload.get('maxStops'))
            await ws.send_text(json.dumps({
                "type": "history:data",
                "payload": {"route": route, "history": history,"requestId":payload.get('requestId')}
            }))

    # ── Price Prediction ──
    elif msg_type == "predict:get":
        route = payload.get("route", "")
        date = payload.get("date", "")
        if price_predictor:
            prediction = await price_predictor.predict(route, date, passenger_count=payload.get("passengerCount", 1), cabin_class=payload.get("cabinClass", "ECONOMY"),preferred_time=payload.get('preferredTime','ANY'),max_stops=payload.get('maxStops'))
            await ws.send_text(json.dumps({
                "type": "predict:result",
                "payload": prediction
            }))

    # ── Watchlist ──
    elif msg_type == "watchlist:add":
        if db:
            compiler._validate_trip({'origin':payload.get('origin'), 'destination':payload.get('destination'), 'departureDate':payload.get('departure_date')})
            if isinstance(payload.get('target_price'),bool) or not isinstance(payload.get('target_price'), (int,float)) or not 0 < payload['target_price'] < float('inf'):
                raise ValueError('Target price must be a positive number')
            await db.add_watchlist_item(payload)
            await ws.send_text(json.dumps({
                "type": "watchlist:data", "payload": {'items':await db.get_watchlist()}
            }))

    elif msg_type == "watchlist:remove":
        watch_id = payload.get("watchId")
        if db and watch_id:
            await db.remove_watchlist_item(watch_id)
            await ws.send_text(json.dumps({'type':'watchlist:data','payload':{'items':await db.get_watchlist()}}))

    elif msg_type == 'watchlist:check':
        item = next((i for i in await db.get_watchlist() if i['id']==payload.get('watchId')),None)
        if not item:
            raise ValueError('Watch not found')
        start_job(check_watch_item(item))

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
        await ws.send_text(json.dumps(dict(type='error',payload=dict(message='Unsupported request type',originalType=msg_type,requestId=payload.get('requestId')))))


async def check_watch_item(item):
    """A manual check and the scheduler share one lock and notification policy."""
    if item['id'] in watch_checks:
        return
    watch_checks[item['id']] = True
    emit_ws('watchlist:checking',dict(watchId=item['id']))
    try:
        if date.fromisoformat(item['departure_date']) < date.today():
            raise ValueError('This departure date has passed')
        task = await compiler.compile({'trip':{'origin':item['origin'],'destination':item['destination'],
            'departureDate':item['departure_date'],'passengerCount':1,'cabinClass':'ECONOMY'},
            'platforms':['google_flights','easemytrip','cleartrip'],'cloak':{'maxConcurrentBots':2}})
        task['background'] = True
        await dispatcher.dispatch_all(task)
        results = await db.get_search_results(task['search_id'])
        results = [r for r in results if r['savings_breakdown'].get('integrity',{}).get('status') in ('corroborated','checkout_verified')]
        best = min(results,key=lambda r:r['final_price']) if results else None
        now = datetime.now(timezone.utc).isoformat()
        # A failed fetch must not erase the last successful observation.
        updated=await db.db.execute('UPDATE watchlist SET last_checked=?, last_price=COALESCE(?,last_price) WHERE id=? AND is_active=1',
            (now,best['final_price'] if best else None,item['id']))
        await db.db.commit()
        if updated.rowcount!=1:
            # A removed request must not publish a late price alert.
            return
        if not best:
            raise ValueError('No fresh quotes returned; the previous price has been retained')
        if best['final_price'] <= item['target_price']:
            previous = item.get('last_price')
            if previous is None or previous > item['target_price'] or best['final_price'] < previous:
                message = f"{item['origin']}-{item['destination']} on {item['departure_date']}: Listed fare INR {best['final_price']:,.0f} on {best['platform']}; checkout fees and coupons need verification."
                await db.add_notification('watchlist_alert','Flight price alert',message,
                    {'watch_id':item['id'],'price':best['final_price'],'verification':'listed'})
                emit_ws('watchlist:alert',{'message':message})
        emit_ws('watchlist:checked',dict(watchId=item['id'],status='success',message='Fresh listed fares checked'))
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        emit_ws('watchlist:checked',dict(watchId=item['id'],status='failed',message=str(exc)))
        logger.warning(f"Watch {item['id']} failed: {exc}")
    finally:
        watch_checks.pop(item['id'],None)
        emit_ws('watchlist:data',{'items':await db.get_watchlist()})


async def watchlist_scheduler_loop():
    """Monitor saved one-adult economy routes while the app is running."""
    while True:
        try:
            for item in await db.get_watchlist():
                try:
                    if date.fromisoformat(item['departure_date']) < date.today():
                        continue
                    now = datetime.now(timezone.utc)
                    frequency = {'hourly':3600,'daily':86400,'weekly':604800}.get(item['check_frequency'],86400)
                    try:
                        checked=datetime.fromisoformat(item['last_checked']) if item.get('last_checked') else None
                        # The previous writer stored UTC without its offset.
                        if checked and checked.tzinfo is None:
                            checked=checked.replace(tzinfo=timezone.utc)
                    except (TypeError,ValueError):
                        checked=None
                    if checked and 0<=(now-checked).total_seconds()<frequency:
                        continue
                    await check_watch_item(item)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.warning(f"Watch {item.get('id')} skipped: {exc}")
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error(f'Watchlist check failed: {exc}')
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
    return {"status": "ok", "service":"flight-finder", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.post("/api/search")
async def api_search(payload: dict = Body(...)):
    """Synchronously trigger search and return the completed search results."""
    from fastapi import HTTPException

    try:
        search_id = str(uuid.uuid4())
        payload["searchId"] = search_id

        # Validate before performing network requests.
        task = await compiler.compile(payload)

        # Quick harvest external coupons before dispatching task
        if coupon_harvester:
            await coupon_harvester.quick_harvest(payload.get("platforms", []))

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
    except ValueError as ex:
        raise HTTPException(status_code=400, detail=str(ex))
    except Exception as ex:
        logger.error(f"HTTP Search endpoint failed: {ex}")
        raise HTTPException(status_code=500, detail=str(ex))



if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=int(os.environ.get('FLIGHT_FINDER_PORT','8765')),
        ws="auto",
        log_level="info",
    )
