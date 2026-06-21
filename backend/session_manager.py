"""
Flight Finder — Session Manager
Manages the lifecycle of headed browser sessions running off-screen.
Brings targeted browser windows to the foreground during user handoff.
"""

import sys
import asyncio
from datetime import datetime, timedelta, timezone
from loguru import logger


class SessionManager:
    def __init__(self, emit_ws):
        self.emit_ws = emit_ws
        self._sessions: dict[str, dict] = {}
        self._cleanup_task = asyncio.create_task(self._periodic_cleanup())

    async def register_session(self, session_id: str, search_id: str, platform: str,
                                 browser, context, page, window_id: int):
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
            "created_at": datetime.now(timezone.utc).replace(tzinfo=None),
            "expires_at": expires_at
        }
        logger.info(f"[SessionManager] Session {session_id} registered. Expires at {expires_at}")

    async def set_session_ready(self, session_id: str):
        """Mark session as ready for user handoff."""
        if session_id in self._sessions:
            self._sessions[session_id]["status"] = "READY_FOR_HANDOFF"
            logger.info(f"[SessionManager] Session {session_id} is READY_FOR_HANDOFF")

    def get_session_status(self, session_id: str) -> str:
        """Get the current status of a session."""
        if session_id in self._sessions:
            return self._sessions[session_id]["status"]
        return "expired"

    async def handoff_to_user(self, session_id: str):
        """Bring the off-screen browser session into the foreground and hand control to the user."""
        session = self._sessions.get(session_id)
        if not session:
            logger.error(f"[SessionManager] Handoff failed: Session {session_id} not found.")
            self.emit_ws("session:handoff:result", {
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

            # 1. Bring window on-screen via CDP
            try:
                cdp = await context.new_cdp_session(page)
                await cdp.send("Browser.setWindowBounds", {
                    "windowId": window_id,
                    "bounds": {
                        "left": 320,    # Centered on a 1920px screen
                        "top": 140,     # Centered on a 1080px screen
                        "width": 1280,
                        "height": 800,
                        "windowState": "normal"
                    }
                })
            except Exception as e:
                logger.error(f"[SessionManager] CDP setWindowBounds failed: {e}")

            # 2. Windows specific: Focus window using Win32 API
            if sys.platform == "win32":
                await self._focus_window_win32()

            session["status"] = "HANDED_OFF"
            session["handoff_time"] = datetime.now(timezone.utc).replace(tzinfo=None)
            
            # Emit success
            self.emit_ws("session:handoff:ack", {
                "sessionId": session_id,
                "status": "success",
                "message": "Browser session brought to foreground. Please complete payment."
            })
            
            # 3. Start expiration watchdog (15 minutes limit)
            asyncio.create_task(self._session_watchdog(session_id, timeout_minutes=15))
            
            # Monitor if user closes the tab manually
            page.on("close", lambda: asyncio.create_task(self.close_session(session_id)))

        except Exception as e:
            logger.error(f"[SessionManager] Focus handoff failed: {e}")
            self.emit_ws("session:handoff:result", {
                "sessionId": session_id,
                "status": "failed",
                "message": f"Focus handoff failed: {str(e)}"
            })

    async def close_session(self, session_id: str):
        """Close browser resources for a session and delete it."""
        session = self._sessions.pop(session_id, None)
        if session:
            logger.info(f"[SessionManager] Closing session {session_id}...")
            try:
                # Close pages & browser
                await session["page"].close()
                await session["context"].close()
                # Camoufox doesn't have standard playwright browser stop, but we check if AsyncCamoufox:
                browser = session["browser"]
                if hasattr(browser, "close"):
                    await browser.close()
                elif hasattr(browser, "stop"):
                    await browser.stop()
            except Exception as e:
                logger.debug(f"Error closing session resources: {e}")
            
            self.emit_ws("session:expired", {
                "sessionId": session_id,
                "message": "Session resources cleaned up."
            })

    async def cleanup_all(self):
        """Shutdown all active browser windows on server shutdown."""
        logger.info("[SessionManager] Cleaning up all active sessions...")
        if hasattr(self, "_cleanup_task"):
            self._cleanup_task.cancel()
        keys = list(self._sessions.keys())
        for k in keys:
            await self.close_session(k)

    async def _session_watchdog(self, session_id: str, timeout_minutes: int):
        """Warn user and clean up browser resources after inactivity timeout."""
        # Warn user 2 minutes before timeout
        await asyncio.sleep((timeout_minutes - 2) * 60)
        if session_id in self._sessions and self._sessions[session_id]["status"] == "HANDED_OFF":
            self.emit_ws("session:warning", {
                "sessionId": session_id,
                "message": "Browser session expires in 2 minutes. Complete payment soon."
            })
            
            await asyncio.sleep(2 * 60)
            if session_id in self._sessions:
                logger.info(f"[SessionManager] Watchdog timeout. Expiring session {session_id}...")
                await self.close_session(session_id)

    async def _focus_window_win32(self):
        """Helper to bring Chromium/Firefox window to foreground using Windows pywin32 API."""
        try:
            import win32gui
            import win32con

            def callback(hwnd, extra):
                if win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd)
                    # We match Chromium (our default engine) or Firefox (Camoufox engine)
                    if any(engine in title for engine in ["Chromium", "Chrome", "Firefox", "MockBooking"]):
                        # Restore if minimized
                        if win32gui.IsIconic(hwnd):
                            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                        # Bring to front
                        win32gui.SetForegroundWindow(hwnd)
                        return False  # Stop searching
                return True

            win32gui.EnumWindows(callback, None)
        except Exception as e:
            logger.debug(f"pywin32 focus fallback failed: {e}")

    async def _periodic_cleanup(self):
        """Periodically check for and close expired/stale sessions."""
        while True:
            try:
                await asyncio.sleep(30)
                now = datetime.now(timezone.utc).replace(tzinfo=None)
                expired_session_ids = []
                
                for session_id, session in list(self._sessions.items()):
                    # If handed off, watchdog handles it
                    if session["status"] == "HANDED_OFF":
                        continue
                    
                    # For other states (active, READY_FOR_HANDOFF):
                    # Timeout after 5 minutes (300 seconds) from registration
                    lifespan = now - session["created_at"]
                    if lifespan.total_seconds() > 300:
                        logger.info(f"[SessionManager] Session {session_id} has exceeded 5 minute inactive timeout. Cleaning up.")
                        expired_session_ids.append(session_id)
                        
                for session_id in expired_session_ids:
                    await self.close_session(session_id)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[SessionManager] Error in periodic cleanup task: {e}")
