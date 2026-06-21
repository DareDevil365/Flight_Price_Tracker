"""
Flight Finder — Centralized API Key Rotation Manager
Manages the pool of Gemini/OpenAI API keys, tracks rate limits, usage metrics,
and dynamically routes calls to cheaper vs. thinking models based on task complexity.
"""

import os
import json
from datetime import datetime, timedelta, timezone
from loguru import logger
from openai import AsyncOpenAI


class APIKeyManager:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(APIKeyManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
            
        self.keys = []
        self.broadcast_callback = None
        self._load_keys()
        self._initialized = True

    def register_broadcast_callback(self, callback):
        """Register a callback (like emit_ws) to stream key status updates to the UI."""
        self.broadcast_callback = callback

    def _load_keys(self):
        """Parse key pool from environment variables."""
        keys_env = os.getenv("GEMINI_API_KEYS")
        raw_keys = []
        if keys_env:
            raw_keys = [k.strip() for k in keys_env.split(",") if k.strip()]
        else:
            single = os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY")
            if single:
                raw_keys = [single]

        # Deduplicate
        seen = set()
        deduped = []
        for k in raw_keys:
            if k not in seen:
                seen.add(k)
                deduped.append(k)

        self.keys = []
        for idx, k in enumerate(deduped):
            # Generate mask: e.g. AQ.Ab8RN6...VBLg
            masked = k
            if len(k) > 15:
                masked = f"{k[:10]}...{k[-5:]}"

            is_gemini = k.startswith(("AIzaSy", "AQ."))
            
            self.keys.append({
                "index": idx,
                "key": k,
                "masked": masked,
                "status": "ACTIVE",
                "is_gemini": is_gemini,
                "exhausted_until": None,
                "use_count": 0,
                "failed_count": 0,
                "last_used": None
            })
        
        logger.info(f"[APIKeyManager] Initialized with {len(self.keys)} keys.")

    def get_client(self, complexity: str = "brute") -> tuple[AsyncOpenAI, str, str]:
        """
        Retrieve an active client, model name, and the raw key string.
        Complexity triggers model routing:
        - "brute": gemini-2.5-flash (cheap & fast)
        - "thinking": gemini-2.5-pro (high-IQ parsing/reasoning)
        """
        self.recharge_keys()
        active_keys = [k for k in self.keys if k["status"] == "ACTIVE"]

        if not active_keys:
            # Fallback: if all keys are exhausted, find the one that recharges earliest
            logger.warning("[APIKeyManager] All API keys in the pool are exhausted! Finding earliest recharge...")
            exhausted_keys = [k for k in self.keys if k["status"] == "EXHAUSTED" and k["exhausted_until"]]
            if exhausted_keys:
                sorted_keys = sorted(exhausted_keys, key=lambda x: x["exhausted_until"])
                selected_key_info = sorted_keys[0]
            else:
                # Absolute fallback
                selected_key_info = self.keys[0]
        else:
            # Load balance: choose active key that has been used the least or has no last_used timestamp
            # Sort by last_used (None first), then by use_count ascending
            selected_key_info = min(
                active_keys,
                key=lambda x: (
                    0 if x["last_used"] is None else 1,
                    x["last_used"] or datetime.min,
                    x["use_count"]
                )
            )

        # Update stats
        selected_key_info["use_count"] += 1
        selected_key_info["last_used"] = datetime.now(timezone.utc)

        # Build client
        key_str = selected_key_info["key"]
        
        if selected_key_info["is_gemini"]:
            # Gemini OpenAI compatibility endpoint
            client = AsyncOpenAI(
                api_key=key_str,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
            )
            # Route model
            model = "gemini-2.5-flash" if complexity == "brute" else "gemini-2.5-pro"
        else:
            # Real OpenAI
            client = AsyncOpenAI(api_key=key_str)
            model = "gpt-4o-mini" if complexity == "brute" else "gpt-4o"

        self._trigger_broadcast()
        return client, model, key_str

    def mark_exhausted(self, key_str: str, duration_seconds: int = 60):
        """Mark a specific key as exhausted for a cooling-off period."""
        for k in self.keys:
            if k["key"] == key_str:
                k["status"] = "EXHAUSTED"
                k["failed_count"] += 1
                cooloff = duration_seconds * (2 ** min(k["failed_count"] - 1, 6))
                k["exhausted_until"] = datetime.now(timezone.utc) + timedelta(seconds=cooloff)
                logger.warning(f"[APIKeyManager] Key {k['masked']} marked EXHAUSTED until {k['exhausted_until']} (cooloff: {cooloff}s, failed: {k['failed_count']})")
                self._trigger_broadcast()
                break

    def mark_success(self, key_str: str):
        """Reset failed count on successful use."""
        for k in self.keys:
            if k["key"] == key_str:
                if k["failed_count"] > 0:
                    logger.info(f"[APIKeyManager] Key {k['masked']} call succeeded. Resetting failed count from {k['failed_count']} to 0.")
                k["failed_count"] = 0
                break

    def recharge_keys(self) -> bool:
        """
        Check if any exhausted keys can be recharged.
        Returns True if any key status changed.
        """
        changed = False
        now = datetime.now(timezone.utc)
        for k in self.keys:
            if k["status"] == "EXHAUSTED" and k["exhausted_until"]:
                if now >= k["exhausted_until"]:
                    k["status"] = "ACTIVE"
                    k["exhausted_until"] = None
                    logger.info(f"[APIKeyManager] Key {k['masked']} has recharged and is now ACTIVE.")
                    changed = True
        
        if changed:
            self._trigger_broadcast()
        return changed

    def get_status_list(self) -> list[dict]:
        """Return a JSON-serializable list of key states for UI monitoring."""
        status_list = []
        for k in self.keys:
            status_list.append({
                "index": k["index"],
                "masked": k["masked"],
                "status": k["status"],
                "exhausted_until": k["exhausted_until"].isoformat() if k["exhausted_until"] else None,
                "use_count": k["use_count"],
                "failed_count": k["failed_count"],
                "last_used": k["last_used"].isoformat() if k["last_used"] else None
            })
        return status_list

    def _trigger_broadcast(self):
        """Broadcast updated API states to active WebSockets."""
        if self.broadcast_callback:
            try:
                self.broadcast_callback("api:status:update", self.get_status_list())
            except Exception as e:
                logger.error(f"[APIKeyManager] Failed to broadcast status update: {e}")


# Global Singleton Instance
api_key_manager = APIKeyManager()
