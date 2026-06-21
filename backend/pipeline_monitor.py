"""
Flight Finder — Pipeline Health Monitor
Tracks success/failure rates, latency, and error classifications
for each scraping platform and pipeline phase.
"""

import json
from datetime import datetime, timedelta
from loguru import logger


class PipelineMonitor:
    def __init__(self, db):
        self.db = db

    async def record_metric(self, platform: str, phase: str, outcome: str,
                            error_category: str = None, error_message: str = None,
                            latency_ms: int = None, search_id: str = None):
        """Record a pipeline execution metric."""
        try:
            conn = self.db.db
            await conn.execute("""
                INSERT INTO pipeline_metrics 
                (platform, phase, outcome, error_category, error_message, latency_ms, search_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (platform, phase, outcome, error_category, error_message, latency_ms, search_id))
            await conn.commit()
        except Exception as e:
            logger.warning(f"[PipelineMonitor] Failed to record metric: {e}")

    def classify_error(self, error: Exception, platform: str = "") -> str:
        """
        Classify a pipeline error into a category for systematic tracking.
        Returns one of: CAPTCHA, TIMEOUT, ANTI_BOT, DOM_CHANGE, NETWORK, PARSE_ERROR, UNKNOWN
        """
        error_str = str(error).lower()
        error_type = type(error).__name__.lower()
        
        # CAPTCHA detection
        captcha_keywords = ["captcha", "recaptcha", "hcaptcha", "challenge", "verify you are human", "bot detection"]
        if any(kw in error_str for kw in captcha_keywords):
            return "CAPTCHA"
        
        # Timeout detection
        timeout_keywords = ["timeout", "timed out", "deadline", "took too long", "asyncio.timeout"]
        if any(kw in error_str for kw in timeout_keywords) or "timeout" in error_type:
            return "TIMEOUT"
        
        # Anti-bot detection
        antibot_keywords = ["access denied", "forbidden", "blocked", "rate limit", "429", "too many requests",
                           "suspicious", "automated", "unusual traffic", "cloudflare"]
        if any(kw in error_str for kw in antibot_keywords):
            return "ANTI_BOT"
        
        # DOM change detection (selectors not found)
        dom_keywords = ["selector", "element not found", "no such element", "stale element",
                       "locator", "query_selector", "wait_for_selector", "not attached", "detached"]
        if any(kw in error_str for kw in dom_keywords):
            return "DOM_CHANGE"
        
        # Network errors
        network_keywords = ["connection", "refused", "reset", "dns", "unreachable", "ssl", "certificate",
                           "econnrefused", "enotfound", "network", "socket"]
        if any(kw in error_str for kw in network_keywords) or "connection" in error_type:
            return "NETWORK"
        
        # Parse errors
        parse_keywords = ["parse", "json", "decode", "extract", "no flights found", "price", "format"]
        if any(kw in error_str for kw in parse_keywords):
            return "PARSE_ERROR"
        
        return "UNKNOWN"

    def get_retry_strategy(self, error_category: str) -> dict:
        """
        Get the recommended retry strategy based on error category.
        Returns dict with retry_count, delay_seconds, and should_retry.
        """
        strategies = {
            "CAPTCHA": {"should_retry": True, "retry_count": 1, "delay_seconds": 10, "note": "Wait and retry once — CAPTCHA may be session-specific"},
            "TIMEOUT": {"should_retry": True, "retry_count": 3, "delay_seconds": 5, "note": "Aggressive retry with backoff"},
            "ANTI_BOT": {"should_retry": True, "retry_count": 2, "delay_seconds": 15, "note": "Long delay, rotate proxy/fingerprint"},
            "DOM_CHANGE": {"should_retry": False, "retry_count": 0, "delay_seconds": 0, "note": "Worker needs code update — do not retry"},
            "NETWORK": {"should_retry": True, "retry_count": 3, "delay_seconds": 3, "note": "Quick retry — likely transient"},
            "PARSE_ERROR": {"should_retry": True, "retry_count": 1, "delay_seconds": 2, "note": "Page may not have loaded fully"},
            "UNKNOWN": {"should_retry": True, "retry_count": 2, "delay_seconds": 5, "note": "Default retry strategy"}
        }
        return strategies.get(error_category, strategies["UNKNOWN"])

    async def get_platform_health(self, platform: str = None, days: int = 7) -> dict:
        """Get platform health summary."""
        conn = self.db.db
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        
        if platform:
            query = """
                SELECT platform, phase, outcome, error_category, COUNT(*) as cnt, AVG(latency_ms) as avg_lat
                FROM pipeline_metrics
                WHERE platform = ? AND recorded_at >= ?
                GROUP BY platform, phase, outcome, error_category
            """
            params = (platform, cutoff)
        else:
            query = """
                SELECT platform, phase, outcome, error_category, COUNT(*) as cnt, AVG(latency_ms) as avg_lat
                FROM pipeline_metrics
                WHERE recorded_at >= ?
                GROUP BY platform, phase, outcome, error_category
            """
            params = (cutoff,)
        
        health = {}
        try:
            async with conn.execute(query, params) as cursor:
                rows = await cursor.fetchall()
            
            for row in rows:
                p = row[0]
                if p not in health:
                    health[p] = {"total": 0, "successes": 0, "failures": 0, "errors": {}, "avg_latency_ms": 0, "phases": {}}
                
                cnt = row[4]
                health[p]["total"] += cnt
                if row[2] == "SUCCESS":
                    health[p]["successes"] += cnt
                else:
                    health[p]["failures"] += cnt
                    if row[3]:
                        health[p]["errors"][row[3]] = health[p]["errors"].get(row[3], 0) + cnt
                
                # Track per-phase stats
                phase = row[1]
                if phase not in health[p]["phases"]:
                    health[p]["phases"][phase] = {"total": 0, "successes": 0}
                health[p]["phases"][phase]["total"] += cnt
                if row[2] == "SUCCESS":
                    health[p]["phases"][phase]["successes"] += cnt
            
            # Calculate success rates
            for p in health:
                if health[p]["total"] > 0:
                    health[p]["success_rate"] = round(health[p]["successes"] / health[p]["total"], 3)
                else:
                    health[p]["success_rate"] = 0.0
                    
        except Exception as e:
            logger.error(f"[PipelineMonitor] Error fetching platform health: {e}")
        
        return health
