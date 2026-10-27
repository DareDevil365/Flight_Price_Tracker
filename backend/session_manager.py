"""
Flight Finder — Session Manager
Manages the lifecycle of headed browser sessions running off-screen.
Brings targeted browser windows to the foreground during user handoff.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from loguru import logger


class SessionManager:
    def __init__(self, emit_ws):
        self.emit_ws = emit_ws
        self._sessions: dict[str, dict] = {}
        self._cleanup_task = asyncio.create_task(self._periodic_cleanup())

    async def register_session(self, session_id: str, search_id: str, platform: str,
                                 browser, context, page, window_id: int, is_shared_browser: bool = False):
        """Register a new active browser session."""
        expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=15)
        self._sessions[session_id] = {
            "session_id": session_id,
            "search_id": search_id,
            "platform": platform,
            "browser": browser,
            "context": context,
            "page": page,
            "window_id": window_id,
            "status": "active",
            "is_shared_browser": is_shared_browser,
            "created_at": datetime.now(timezone.utc).replace(tzinfo=None),
            "expires_at": expires_at
        }
        # Google/merchant Continue controls open tabs in this same context. The
        # session owns the context, not just its original tab: closing Google
        # must not close a merchant checkout which is still open.
        self._track_page(session_id,page)
        context.on('page',lambda opened:self._track_page(session_id,opened))
        logger.info(f"[SessionManager] Session {session_id} registered. Expires at {expires_at}")

    @staticmethod
    def _expires(session):
        deadline=session['expires_at']
        return deadline.replace(tzinfo=timezone.utc) if deadline.tzinfo is None else deadline.astimezone(timezone.utc)

    def _track_page(self,session_id,page):
        session=self._sessions.get(session_id)
        if not session:
            return
        tracked=session.setdefault('tracked_pages',set())
        if id(page) in tracked:
            return
        tracked.add(id(page))
        page.on('close',lambda:asyncio.create_task(self._page_closed(session_id,page)))

    async def _page_closed(self,session_id,closed):
        await asyncio.sleep(0)  # Let Playwright remove the tab from context.pages.
        session=self._sessions.get(session_id)
        if not session:
            return
        remaining=[page for page in session['context'].pages if not page.is_closed()]
        if not remaining:
            await self.close_session(session_id)
        elif session['page'] is closed or session['page'].is_closed():
            session['page']=remaining[-1]

    async def set_session_ready(self, session_id: str):
        """Mark session as ready for user handoff."""
        if session_id in self._sessions:
            self._sessions[session_id]["status"] = "READY_FOR_HANDOFF"
            logger.info(f"[SessionManager] Session {session_id} is READY_FOR_HANDOFF")

    def get_session_status(self, session_id: str) -> str:
        """Get the current status of a session."""
        if session_id in self._sessions:
            session=self._sessions[session_id]
            if datetime.now(timezone.utc)>=self._expires(session):
                return 'expired'
            return session["status"]
        return "expired"

    async def handoff_to_user(self, session_id: str):
        """Bring the off-screen browser session into the foreground and hand control to the user."""
        session = self._sessions.get(session_id)
        if session and self.get_session_status(session_id)=='expired':
            await self.close_session(session_id)
            session=None
        if not session:
            logger.error(f"[SessionManager] Handoff failed: Session {session_id} not found.")
            self.emit_ws("session:handoff:ack", {
                "sessionId": session_id,
                "status": "failed",
                "message": "Session not found or expired."
            })
            return

        if session["status"] not in ["READY_FOR_HANDOFF", "active"]:
            logger.warning(f"[SessionManager] Handoff warning: Session {session_id} is in status {session['status']}")

        logger.info(f"[SessionManager] Commencing handoff for session {session_id}...")
        
        try:
            page = session["page"]
            context = session["context"]
            window_id = session["window_id"]
            await page.bring_to_front()

            # Restore normal image, font, and CSS styling for the user
            try:
                await page.unroute("**/*")
                logger.info(f"[SessionManager] Unrouted page resource interception for session {session_id}")
            except Exception as ue:
                logger.debug(f"Failed to unroute resources: {ue}")

            # Failure to restore this exact window must be reported as failure.
            cdp = await context.new_cdp_session(page)
            try:
                window_id = (await cdp.send("Browser.getWindowForTarget"))["windowId"]
                await cdp.send("Browser.setWindowBounds", {"windowId":window_id,"bounds":{
                    "left":320,"top":140,"width":1280,"height":800,"windowState":"normal"}})
            finally:
                await cdp.detach()

            session["status"] = "HANDED_OFF"
            session["handoff_time"] = datetime.now(timezone.utc).replace(tzinfo=None)
            
            # Emit success
            self.emit_ws("session:handoff:ack", {
                "sessionId": session_id,
                "status": "success",
                "message": ("Google itinerary opened. Review its listed partner options and continue on the merchant website. These offers are not verified payment totals."
                            if session['platform']=='google_flights' else
                            "Booking browser opened. Review the itinerary and continue if the provider allows it. Return here to verify its payment total.")
            })
            
            # 3. Start expiration watchdog (15 minutes limit)
            session["expires_at"] = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=15)
            
            self._track_page(session_id,page)

        except Exception as e:
            logger.error(f"[SessionManager] Focus handoff failed: {e}")
            self.emit_ws("session:handoff:ack", {
                "sessionId": session_id,
                "status": "failed",
                "message": f"Focus handoff failed: {str(e)}"
            })

    async def close_session(self, session_id: str):
        """Close browser resources for a session and delete it."""
        session = self._sessions.pop(session_id, None)
        if session:
            logger.info(f"[SessionManager] Closing session {session_id}...")
            resources = [session['context']]
            if not session.get('is_shared_browser'):
                resources.append(session['browser'])
            for resource in resources:
                try:
                    await resource.close()
                except Exception as exc:
                    logger.debug(f'Error closing browser resource: {exc}')

            self.emit_ws("session:expired", {
                "sessionId": session_id,
                "message": "Session resources cleaned up."
            })

    async def cleanup_all(self):
        """Shutdown all active browser windows on server shutdown."""
        logger.info("[SessionManager] Cleaning up all active sessions...")
        if hasattr(self, "_cleanup_task"):
            self._cleanup_task.cancel()
            await asyncio.gather(self._cleanup_task,return_exceptions=True)
        keys = list(self._sessions.keys())
        for k in keys:
            await self.close_session(k)

    async def _periodic_cleanup(self):
        """Periodically check for and close expired/stale sessions."""
        while True:
            try:
                await asyncio.sleep(30)
                now = datetime.now(timezone.utc)
                expired_session_ids = []
                
                for session_id, session in list(self._sessions.items()):
                    if now >= self._expires(session):
                        expired_session_ids.append(session_id)
                        
                for session_id in expired_session_ids:
                    await self.close_session(session_id)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[SessionManager] Error in periodic cleanup task: {e}")
