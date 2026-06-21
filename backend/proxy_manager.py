"""
Flight Finder — Proxy Manager
Allocates and rotates residential/datacenter proxies per platform.
Supports BrightData, Oxylabs, Smartproxy, and custom providers.
"""

import os
import random
import asyncio
from typing import Optional

import aiohttp
from loguru import logger
from dotenv import load_dotenv

load_dotenv()


class ProxyManager:
    """Manages proxy allocation, rotation, and health checking."""

    def __init__(self):
        self.provider = os.getenv("PROXY_PROVIDER", "").lower()
        self._assigned: dict[str, dict] = {}  # platform -> proxy
        self._pool: list[dict] = []

        # Load provider config from env
        if self.provider == "brightdata":
            self._pool = self._build_brightdata_pool()
        elif self.provider == "oxylabs":
            self._pool = self._build_oxylabs_pool()
        elif self.provider == "smartproxy":
            self._pool = self._build_smartproxy_pool()

        logger.info(
            f"ProxyManager initialized: provider={self.provider or 'none'}, "
            f"pool_size={len(self._pool)}"
        )

    def get_fresh_proxy(self, platform: str) -> Optional[dict]:
        """
        Get a proxy for a specific platform.
        Each platform gets a unique proxy to avoid cross-session tracking.
        """
        if not self._pool:
            logger.debug(f"No proxies available, {platform} will use direct connection")
            return None

        # If already assigned, return the same one (session consistency)
        if platform in self._assigned:
            return self._assigned[platform]

        # Get an unassigned proxy
        assigned_proxies = set(id(p) for p in self._assigned.values())
        available = [p for p in self._pool if id(p) not in assigned_proxies]

        if not available:
            # All proxies assigned, recycle from pool
            proxy = random.choice(self._pool)
        else:
            proxy = random.choice(available)

        self._assigned[platform] = proxy
        logger.info(f"Proxy assigned to {platform}: {proxy['host']}:{proxy['port']}")
        return proxy

    def release_proxy(self, platform: str):
        """Release a proxy assignment when a worker finishes."""
        if platform in self._assigned:
            del self._assigned[platform]

    def get_regional_proxy(self, city_tier: str) -> Optional[dict]:
        """
        Get a proxy targeted to a specific Indian city tier:
        - 'tier_1': Mumbai/Delhi (High pricing tier)
        - 'tier_3': Patna/Ranchi (Low pricing tier)
        """
        if not self.provider:
            return None

        if self.provider == "oxylabs":
            username = os.getenv("OXYLABS_USERNAME", "")
            password = os.getenv("OXYLABS_PASSWORD", "")
            city = "mumbai" if city_tier == "tier_1" else "patna"
            return {
                "provider": "oxylabs",
                "protocol": "http",
                "host": "pr.oxylabs.io",
                "port": 7777,
                "username": f"{username}-cc-in-city-{city}-sessid-{random.randint(1000, 9999)}",
                "password": password
            }
        elif self.provider == "brightdata":
            host = os.getenv("BRIGHTDATA_HOST", "brd.superproxy.io")
            port = int(os.getenv("BRIGHTDATA_PORT", "22225"))
            username = os.getenv("BRIGHTDATA_USERNAME", "")
            password = os.getenv("BRIGHTDATA_PASSWORD", "")
            city = "bom" if city_tier == "tier_1" else "pat"
            return {
                "provider": "brightdata",
                "protocol": "http",
                "host": host,
                "port": port,
                "username": f"{username}-country-in-city-{city}",
                "password": password
            }

        return self.get_fresh_proxy(f"regional_{city_tier}")

    async def test_connection(self, credentials: dict) -> dict:
        """Test proxy connectivity and return latency + IP info."""
        proxy_url = (
            f"http://{credentials.get('username', '')}:{credentials.get('password', '')}"
            f"@{credentials.get('host', '')}:{credentials.get('port', '')}"
        )

        try:
            async with aiohttp.ClientSession() as session:
                start = asyncio.get_event_loop().time()
                async with session.get(
                    "https://api.ipify.org?format=json",
                    proxy=proxy_url,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    elapsed = (asyncio.get_event_loop().time() - start) * 1000
                    data = await resp.json()
                    return {
                        "status": "connected",
                        "ip": data.get("ip", "unknown"),
                        "latency_ms": round(elapsed),
                        "provider": credentials.get("provider", "unknown"),
                    }
        except Exception as e:
            return {
                "status": "failed",
                "error": str(e),
                "provider": credentials.get("provider", "unknown"),
            }

    def _build_brightdata_pool(self) -> list[dict]:
        """Build proxy pool from BrightData config."""
        host = os.getenv("BRIGHTDATA_HOST", "brd.superproxy.io")
        port = int(os.getenv("BRIGHTDATA_PORT", "22225"))
        username = os.getenv("BRIGHTDATA_USERNAME", "")
        password = os.getenv("BRIGHTDATA_PASSWORD", "")

        if not username or not password:
            logger.warning("BrightData credentials not configured")
            return []

        # Create multiple session-based proxies
        proxies = []
        for i in range(8):
            proxies.append({
                "provider": "brightdata",
                "protocol": "http",
                "host": host,
                "port": port,
                "username": f"{username}-session-flight{i}",
                "password": password,
            })
        return proxies

    def _build_oxylabs_pool(self) -> list[dict]:
        """Build proxy pool from Oxylabs config."""
        username = os.getenv("OXYLABS_USERNAME", "")
        password = os.getenv("OXYLABS_PASSWORD", "")

        if not username or not password:
            return []

        proxies = []
        for i in range(8):
            proxies.append({
                "provider": "oxylabs",
                "protocol": "http",
                "host": "pr.oxylabs.io",
                "port": 7777,
                "username": f"{username}-cc-in-sessid-flight{i}",
                "password": password,
            })
        return proxies

    def _build_smartproxy_pool(self) -> list[dict]:
        """Build proxy pool from Smartproxy config."""
        username = os.getenv("SMARTPROXY_USERNAME", "")
        password = os.getenv("SMARTPROXY_PASSWORD", "")

        if not username or not password:
            return []

        proxies = []
        for i in range(8):
            proxies.append({
                "provider": "smartproxy",
                "protocol": "http",
                "host": "gate.smartproxy.com",
                "port": 7000 + i,
                "username": username,
                "password": password,
            })
        return proxies
