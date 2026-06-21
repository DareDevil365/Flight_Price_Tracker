"""
Flight Finder — SQLite Database Manager
Async CRUD operations for coupons, searches, results, price history,
watchlist, external savings, predictions, and notifications.
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import aiosqlite
from loguru import logger

DB_PATH = Path(__file__).parent / "db" / "flight_agent.db"
SCHEMA_PATH = Path(__file__).parent / "db" / "schema.sql"


class CouponDB:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.db: Optional[aiosqlite.Connection] = None
        self.lock = asyncio.Lock()

    async def initialize(self):
        """Create database and tables from schema.sql."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db = await aiosqlite.connect(str(self.db_path))
        self.db.row_factory = aiosqlite.Row

        schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
        async with self.lock:
            await self.db.executescript(schema_sql)
            await self.db.commit()

            # Migration check for departure_date in search_results
            try:
                async with self.db.execute("PRAGMA table_info(search_results)") as cur:
                    columns = [row["name"] for row in await cur.fetchall()]
                    if "departure_date" not in columns:
                        await self.db.execute("ALTER TABLE search_results ADD COLUMN departure_date TEXT")
                        await self.db.commit()
                        logger.info("Migrated search_results table: added departure_date column.")
            except Exception as e:
                logger.error(f"Failed to migrate search_results: {e}")

            # Migration check for source in observed_prices
            try:
                async with self.db.execute("PRAGMA table_info(observed_prices)") as cur:
                    columns = [row["name"] for row in await cur.fetchall()]
                    if "source" not in columns:
                        await self.db.execute("ALTER TABLE observed_prices ADD COLUMN source TEXT DEFAULT 'scraped'")
                        await self.db.commit()
                        logger.info("Migrated observed_prices table: added source column.")
            except Exception as e:
                logger.error(f"Failed to migrate observed_prices: {e}")

            # Migration check for source in price_history
            try:
                async with self.db.execute("PRAGMA table_info(price_history)") as cur:
                    columns = [row["name"] for row in await cur.fetchall()]
                    if "source" not in columns:
                        await self.db.execute("ALTER TABLE price_history ADD COLUMN source TEXT DEFAULT 'scraped'")
                        await self.db.commit()
                        logger.info("Migrated price_history table: added source column.")
            except Exception as e:
                logger.error(f"Failed to migrate price_history: {e}")

            # Prepopulate default platforms if table is empty
            try:
                async with self.db.execute("SELECT COUNT(*) FROM custom_platforms") as cur:
                    row = await cur.fetchone()
                    if row and row[0] == 0:
                        defaults = [
                            ("makemytrip", "MakeMyTrip", "https://www.makemytrip.com/"),
                            ("easemytrip", "EaseMyTrip", "https://www.easemytrip.com/"),
                            ("cleartrip", "Cleartrip", "https://www.cleartrip.com/"),
                            ("yatra", "Yatra", "https://www.yatra.com/"),
                            ("ixigo", "Ixigo", "https://www.ixigo.com/"),
                            ("paytm", "Paytm Flights", "https://tickets.paytm.com/flights/"),
                            ("google_flights", "Google Flights", "https://www.google.com/flights")
                        ]
                        await self.db.executemany(
                            "INSERT INTO custom_platforms (id, name, url) VALUES (?, ?, ?)",
                            defaults
                        )
                        await self.db.commit()
                        logger.info("Pre-populated default dynamic platforms in database.")
            except Exception as e:
                logger.error(f"Failed to prepopulate platforms: {e}")

        logger.info(f"Database initialized at {self.db_path}")

    async def close(self):
        if self.db:
            await self.db.close()

    # ── Coupon Operations ──

    async def get_coupons_for_platform(
        self, platform: str, active_only: bool = True
    ) -> list[dict]:
        """Get all coupons for a specific platform, sorted by trust_score * discount_value."""
        query = """
            SELECT * FROM coupons 
            WHERE platform = ?
        """
        if active_only:
            query += " AND is_active = 1"
        query += " ORDER BY (trust_score * COALESCE(discount_value, 0)) DESC"

        async with self.db.execute(query, (platform,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def add_coupon(self, coupon: dict) -> int:
        """Insert or update a coupon code."""
        try:
            async with self.lock:
                await self.db.execute(
                    """
                    INSERT INTO coupons (
                        platform, code, description, bank_restriction, card_type,
                        requires_emi, requires_bnpl, requires_wallet, app_only,
                        discount_type, discount_value, max_discount, min_booking_value,
                        valid_from, valid_until, is_active, source, source_url,
                        source_type, trust_score
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(platform, code) DO UPDATE SET
                        description = COALESCE(excluded.description, description),
                        valid_until = COALESCE(excluded.valid_until, valid_until),
                        is_active = excluded.is_active,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        coupon.get("platform"),
                        coupon.get("code"),
                        coupon.get("description"),
                        coupon.get("bank_restriction"),
                        coupon.get("card_type", "ANY"),
                        coupon.get("requires_emi", False),
                        coupon.get("requires_bnpl", False),
                        coupon.get("requires_wallet", False),
                        coupon.get("app_only", False),
                        coupon.get("discount_type"),
                        coupon.get("discount_value"),
                        coupon.get("max_discount"),
                        coupon.get("min_booking_value"),
                        coupon.get("valid_from"),
                        coupon.get("valid_until"),
                        coupon.get("is_active", True),
                        coupon.get("source", "manual"),
                        coupon.get("source_url"),
                        coupon.get("source_type", "platform_native"),
                        coupon.get("trust_score", 0.5),
                    ),
                )
                await self.db.commit()
            return self.db.total_changes
        except Exception as e:
            logger.error(f"Error adding coupon: {e}")
            return 0

    async def add_coupons_batch(self, coupons: list[dict]) -> int:
        """Batch insert multiple coupons."""
        count = 0
        for c in coupons:
            count += await self.add_coupon(c)
        return count

    async def update_coupon_stats(self, coupon_id: int, success: bool):
        """Update success_rate and last_verified after a test using EMA (alpha=0.2)."""
        alpha = 0.2
        val = 1.0 if success else 0.0
        async with self.lock:
            await self.db.execute(
                """
                UPDATE coupons SET
                    success_rate = CASE
                        WHEN success_rate IS NULL THEN ?
                        ELSE (? * ?) + ((1.0 - ?) * success_rate)
                    END,
                    last_verified = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (val, alpha, val, alpha, coupon_id),
            )
            await self.db.commit()

    async def get_coupon_count(self, platform: str) -> int:
        async with self.db.execute(
            "SELECT COUNT(*) FROM coupons WHERE platform = ? AND is_active = 1",
            (platform,),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

    async def deactivate_expired(self):
        """Mark expired coupons as inactive."""
        today = datetime.now(timezone.utc).replace(tzinfo=None).strftime("%Y-%m-%d")
        async with self.lock:
            await self.db.execute(
                "UPDATE coupons SET is_active = 0 WHERE valid_until < ? AND is_active = 1",
                (today,),
            )
            await self.db.commit()

    # ── Search Operations ──

    async def save_search(self, search: dict):
        async with self.lock:
            await self.db.execute(
                """
                INSERT INTO searches (id, origin, destination, departure_date, return_date,
                    passenger_count, cabin_class, platforms, status, started_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    search["search_id"],
                    search.get("origin"),
                    search.get("destination"),
                    search.get("departure_date"),
                    search.get("return_date"),
                    search.get("passenger_count", 1),
                    search.get("cabin_class", "ECONOMY"),
                    json.dumps(search.get("platforms", [])),
                    "running",
                    datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
                ),
            )
            await self.db.commit()

    async def complete_search(self, search_id: str, duration_ms: int):
        async with self.lock:
            await self.db.execute(
                """
                UPDATE searches SET status = 'completed', completed_at = ?, total_duration_ms = ?
                WHERE id = ?
                """,
                (datetime.now(timezone.utc).replace(tzinfo=None).isoformat(), duration_ms, search_id),
            )
            await self.db.commit()

    # ── Search Results ──

    async def save_result(self, result: dict):
        async with self.lock:
            await self.db.execute(
                """
                INSERT INTO search_results (
                    id, search_id, platform, flight_number, airline,
                    departure_time, arrival_time, duration, stops,
                    base_price, final_price, best_coupon_code, savings,
                    effective_price, deal_score, all_tested_coupons,
                    savings_breakdown, session_id, rank, departure_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.get("id", str(__import__("uuid").uuid4())),
                    result["search_id"],
                    result["platform"],
                    result.get("flight_number"),
                    result.get("airline"),
                    result.get("departure_time"),
                    result.get("arrival_time"),
                    result.get("duration"),
                    result.get("stops", 0),
                    result.get("base_price"),
                    result.get("final_price"),
                    result.get("best_coupon_code"),
                    result.get("savings"),
                    result.get("effective_price"),
                    result.get("deal_score"),
                    json.dumps(result.get("all_tested_coupons", [])),
                    json.dumps(result.get("savings_breakdown", {})),
                    result.get("session_id"),
                    result.get("rank"),
                    result.get("departure_date"),
                ),
            )
            await self.db.commit()

    # ── Price History ──

    async def log_price(self, route: str, departure_date: str, airline: str,
                        flight_number: str, price: float, platform: str,
                        cabin_class: str = "ECONOMY", source: str = "scraped"):
        async with self.lock:
            await self.db.execute(
                """
                INSERT INTO price_history (route, departure_date, airline, flight_number,
                    price, platform, cabin_class, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (route, departure_date, airline, flight_number, price, platform, cabin_class, source),
            )
            await self.db.commit()

    async def get_price_history(self, route: str, days: int = 30, source: str = "scraped") -> list[dict]:
        cutoff = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)).isoformat()
        async with self.db.execute(
            """
            SELECT * FROM price_history
            WHERE route = ? AND recorded_at >= ? AND source = ?
            ORDER BY recorded_at ASC
            """,
            (route, cutoff, source),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_avg_price(self, route: str, days: int = 30, source: str = "scraped") -> Optional[float]:
        cutoff = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)).isoformat()
        async with self.db.execute(
            "SELECT AVG(price) FROM price_history WHERE route = ? AND recorded_at >= ? AND source = ? AND price >= 1500.0",
            (route, cutoff, source),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row and row[0] else None

    # ── Watchlist ──

    async def add_watchlist_item(self, item: dict):
        async with self.lock:
            await self.db.execute(
                """
                INSERT INTO watchlist (origin, destination, departure_date, target_price, check_frequency)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    item["origin"],
                    item["destination"],
                    item["departure_date"],
                    item.get("target_price"),
                    item.get("check_frequency", "daily"),
                ),
            )
            await self.db.commit()

    async def remove_watchlist_item(self, watch_id: int):
        async with self.lock:
            await self.db.execute("DELETE FROM watchlist WHERE id = ?", (watch_id,))
            await self.db.commit()

    async def get_watchlist(self) -> list[dict]:
        async with self.db.execute(
            "SELECT * FROM watchlist WHERE is_active = 1 ORDER BY created_at DESC"
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    # ── External Savings ──

    async def save_external_saving(self, saving: dict):
        async with self.lock:
            await self.db.execute(
                """
                INSERT INTO external_savings (
                    platform, savings_type, provider, savings_value, savings_unit,
                    max_savings, min_transaction, terms, source_url,
                    valid_from, valid_until, last_scraped
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    saving["platform"],
                    saving["savings_type"],
                    saving["provider"],
                    saving.get("savings_value"),
                    saving.get("savings_unit", "PERCENT"),
                    saving.get("max_savings"),
                    saving.get("min_transaction"),
                    saving.get("terms"),
                    saving.get("source_url"),
                    saving.get("valid_from"),
                    saving.get("valid_until"),
                    datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
                ),
            )
            await self.db.commit()

    async def get_external_savings(self, platform: str) -> list[dict]:
        async with self.db.execute(
            "SELECT * FROM external_savings WHERE platform = ? AND is_active = 1",
            (platform,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    # ── Notifications ──

    async def add_notification(self, notif_type: str, title: str, message: str, data: dict = None):
        async with self.lock:
            await self.db.execute(
                "INSERT INTO notifications (type, title, message, data) VALUES (?, ?, ?, ?)",
                (notif_type, title, message, json.dumps(data or {})),
            )
            await self.db.commit()

    async def get_notifications(self, unread_only: bool = False, limit: int = 50) -> list[dict]:
        query = "SELECT * FROM notifications"
        if unread_only:
            query += " WHERE is_read = 0"
        query += f" ORDER BY created_at DESC LIMIT {limit}"
        async with self.db.execute(query) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def mark_notification_read(self, notif_id: int):
        async with self.lock:
            await self.db.execute(
                "UPDATE notifications SET is_read = 1 WHERE id = ?", (notif_id,)
            )
            await self.db.commit()

    # ── Search History ──

    async def get_searches(self, limit: int = 50) -> list[dict]:
        async with self.db.execute(
            "SELECT * FROM searches ORDER BY created_at DESC LIMIT ?", (limit,)
        ) as cursor:
            rows = await cursor.fetchall()
            results = []
            for row in rows:
                d = dict(row)
                if d.get("platforms"):
                    try:
                        d["platforms"] = json.loads(d["platforms"])
                    except Exception:
                        pass
                results.append(d)
            return results

    async def get_search_results(self, search_id: str) -> list[dict]:
        async with self.db.execute(
            "SELECT * FROM search_results WHERE search_id = ? ORDER BY effective_price ASC", (search_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            results = []
            for row in rows:
                d = dict(row)
                if d.get("all_tested_coupons"):
                    try:
                        d["all_tested_coupons"] = json.loads(d["all_tested_coupons"])
                    except Exception:
                        pass
                if d.get("savings_breakdown"):
                    try:
                        d["savings_breakdown"] = json.loads(d["savings_breakdown"])
                    except Exception:
                        pass
                results.append(d)
            return results

    # ── Custom Platforms ──

    async def get_platforms(self) -> list[dict]:
        async with self.db.execute("SELECT * FROM custom_platforms WHERE is_active = 1") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def add_platform(self, name: str, url: str) -> str:
        import re
        platform_id = re.sub(r'[^a-z0-9]', '_', name.lower().strip())
        if not platform_id:
            platform_id = "custom_" + str(hash(url))[:6]
        async with self.lock:
            await self.db.execute(
                "INSERT OR REPLACE INTO custom_platforms (id, name, url, is_active) VALUES (?, ?, ?, 1)",
                (platform_id, name, url)
            )
            await self.db.commit()
        return platform_id

    async def deactivate_platform(self, platform_id: str):
        async with self.lock:
            await self.db.execute(
                "UPDATE custom_platforms SET is_active = 0 WHERE id = ?",
                (platform_id,)
            )
            await self.db.commit()

    # ── Nearby Date Results ──

    async def save_nearby_date_price(self, route: str, date: str, price: float, platform: str):
        """Save price point for alternative dates into price history."""
        await self.log_price(
            route=route,
            departure_date=date,
            airline="Cheapest",
            flight_number="ALT-DATE",
            price=price,
            platform=platform,
            cabin_class="ECONOMY"
        )

    async def get_nearby_date_prices(self, route: str, target_date: str, days_range: int = 2) -> list[dict]:
        """Query price history for dates within days_range of target_date."""
        try:
            base_dt = datetime.strptime(target_date, "%Y-%m-%d")
            dates = [(base_dt + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(-days_range, days_range + 1)]
            
            placeholders = ",".join(["?"] * len(dates))
            query = f"""
                SELECT departure_date as date, MIN(price) as price FROM price_history
                WHERE route = ? AND departure_date IN ({placeholders})
                GROUP BY departure_date
            """
            async with self.db.execute(query, [route] + dates) as cursor:
                rows = await cursor.fetchall()
                # Calculate savings against the target date price if we have it
                results = []
                target_price = None
                for row in rows:
                    row_dict = dict(row)
                    if row_dict["date"] == target_date:
                        target_price = row_dict["price"]
                    results.append(row_dict)
                
                # compute savings
                for r in results:
                    r["savings"] = (target_price - r["price"]) if target_price is not None else 0.0
                return results
        except Exception as e:
            logger.error(f"Error fetching nearby date prices: {e}")
            return []

    # ── Smart Suggestions ──

    async def save_smart_suggestions(self, search_id: str, route: str, suggestions: dict):
        """Save/cache the smart suggestions payload for a search."""
        async with self.lock:
            await self.db.execute(
                """
                INSERT INTO smart_suggestions (search_id, route, suggestions)
                VALUES (?, ?, ?)
                """,
                (search_id, route, json.dumps(suggestions)),
            )
            await self.db.commit()

    async def get_smart_suggestions(self, search_id: str) -> Optional[dict]:
        """Fetch the smart suggestions payload for a search."""
        async with self.db.execute(
            "SELECT suggestions FROM smart_suggestions WHERE search_id = ?",
            (search_id,),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                try:
                    return json.loads(row[0])
                except Exception:
                    pass
            return None

    async def recalculate_ranks(self, search_id: str):
        """Recalculate and update the rank of all search results for a search_id based on effective_price."""
        async with self.lock:
            async with self.db.execute(
                "SELECT id FROM search_results WHERE search_id = ? ORDER BY effective_price ASC",
                (search_id,),
            ) as cursor:
                rows = await cursor.fetchall()
            
            for index, row in enumerate(rows):
                rank = index + 1
                await self.db.execute(
                    "UPDATE search_results SET rank = ? WHERE id = ?",
                    (rank, row["id"]),
                )
            await self.db.commit()

    # ═══════════════════════════════════════════════════════════
    # Self-Learning Intelligence Methods
    # ═══════════════════════════════════════════════════════════

    async def save_coupon_test_result(self, code: str, platform: str, result: str,
                                      discount: float = None, base_price: float = None,
                                      route: str = None, search_id: str = None,
                                      error_msg: str = None):
        """Record an individual coupon test outcome for learning."""
        try:
            async with self.lock:
                await self.db.execute("""
                    INSERT INTO coupon_test_results 
                    (coupon_code, platform, test_result, discount_amount, base_price, route, search_id, error_message)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (code, platform, result, discount, base_price, route, search_id, error_msg))
                await self.db.commit()
        except Exception as e:
            logger.warning(f"Failed to save coupon test result: {e}")

    async def get_smartest_coupons(self, platform: str, route: str = None,
                                    price: float = None) -> list[dict]:
        """
        Get coupons ranked by historical success AND expected discount.
        Smart ordering: highest-success-rate coupons first, skip dead ones.
        """
        try:
            # Get coupons with their learning data joined
            query = """
                SELECT c.*, 
                       cl.success_rate as learned_success_rate,
                       cl.avg_discount_amount as learned_avg_discount,
                       cl.total_tests as learned_total_tests,
                       cl.is_dead as learned_is_dead,
                       cl.best_route as learned_best_route
                FROM coupons c
                LEFT JOIN coupon_learnings cl 
                    ON c.code = cl.coupon_code AND c.platform = cl.platform
                WHERE c.platform = ? AND c.is_active = 1
                AND (cl.is_dead IS NULL OR cl.is_dead = 0)
            """
            params = [platform]
            
            # Filter by min_booking_value if price provided
            if price is not None:
                query += " AND (c.min_booking_value IS NULL OR c.min_booking_value <= ?)"
                params.append(price)

            # Smart ordering: high success rate first, then by expected discount
            query += """
                ORDER BY 
                    COALESCE(cl.success_rate, 0.5) DESC,
                    COALESCE(cl.avg_discount_amount, c.discount_value, 0) DESC,
                    c.trust_score DESC
            """
            
            async with self.db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                results = []
                for row in rows:
                    d = dict(row)
                    # Add smart metadata
                    d["smart_priority"] = self._compute_coupon_priority(d, route)
                    results.append(d)
                
                # Re-sort by smart_priority
                results.sort(key=lambda x: x["smart_priority"], reverse=True)
                return results
        except Exception as e:
            logger.warning(f"get_smartest_coupons failed, falling back to basic: {e}")
            return await self.get_coupons_for_platform(platform)

    def _compute_coupon_priority(self, coupon: dict, route: str = None) -> float:
        """Compute a smart priority score for a coupon based on learned data."""
        success_rate = coupon.get("learned_success_rate") or coupon.get("success_rate") or 0.5
        avg_discount = coupon.get("learned_avg_discount") or coupon.get("discount_value") or 0
        total_tests = coupon.get("learned_total_tests") or 0
        best_route = coupon.get("learned_best_route")
        
        # Base score from success rate (0-100)
        score = success_rate * 60
        
        # Bonus for expected discount (normalized, cap at 30 points)
        score += min(30, avg_discount / 100)
        
        # Bonus if this coupon's best route matches current route
        if route and best_route and route.upper() in best_route.upper():
            score += 15
        
        # Small bonus for well-tested coupons (confidence)
        if total_tests >= 10:
            score += 5
        elif total_tests >= 5:
            score += 2
        
        return score

    async def get_airport_alternatives(self, airport_code: str) -> list[dict]:
        """Get alternative airports for a given airport code."""
        try:
            async with self.db.execute("""
                SELECT * FROM airport_alternatives 
                WHERE primary_code = ? AND is_active = 1
                ORDER BY ground_transport_cost ASC
            """, (airport_code.upper(),)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.warning(f"Failed to fetch airport alternatives for {airport_code}: {e}")
            return []

    async def save_suggestion_tracking(self, search_id: str, suggestion_type: str,
                                        potential_saving: float = 0.0) -> Optional[int]:
        """Record that a suggestion was shown to the user."""
        try:
            async with self.lock:
                cursor = await self.db.execute("""
                    INSERT INTO suggestion_tracking (search_id, suggestion_type, potential_saving)
                    VALUES (?, ?, ?)
                """, (search_id, suggestion_type, potential_saving))
                await self.db.commit()
                return cursor.lastrowid
        except Exception as e:
            logger.warning(f"Failed to save suggestion tracking: {e}")
            return None

    async def record_suggestion_click(self, suggestion_id: int):
        """Mark a suggestion as clicked."""
        try:
            async with self.lock:
                await self.db.execute(
                    "UPDATE suggestion_tracking SET was_clicked = 1 WHERE id = ?",
                    (suggestion_id,)
                )
                await self.db.commit()
        except Exception as e:
            logger.warning(f"Failed to record suggestion click: {e}")

    async def record_suggestion_accept(self, suggestion_id: int):
        """Mark a suggestion as accepted (user booked via it)."""
        try:
            async with self.lock:
                await self.db.execute(
                    "UPDATE suggestion_tracking SET was_accepted = 1 WHERE id = ?",
                    (suggestion_id,)
                )
                await self.db.commit()
        except Exception as e:
            logger.warning(f"Failed to record suggestion acceptance: {e}")

    async def seed_airport_alternatives(self):
        """Seed airport alternatives table with major Indian airport pairs."""
        alternatives = [
            # Goa
            ("GOI", "GOX", "Manohar Mopa Airport", "Goa", 40, 600, 50),
            ("GOX", "GOI", "Dabolim Airport", "Goa", 40, 600, 50),
            # Delhi NCR
            ("DEL", "HND", "Hindon Airport (Ghaziabad)", "Delhi NCR", 25, 500, 40),
            ("HND", "DEL", "Indira Gandhi International", "Delhi NCR", 25, 500, 40),
            # Mumbai / Pune
            ("BOM", "PNQ", "Pune Airport", "Western Maharashtra", 150, 1800, 180),
            ("PNQ", "BOM", "Chhatrapati Shivaji International", "Western Maharashtra", 150, 1800, 180),
            # Bangalore
            ("BLR", "MYQ", "Mysore Airport", "Karnataka", 170, 1500, 190),
            # Chennai / Pondicherry
            ("MAA", "PNY", "Puducherry Airport", "Tamil Nadu Coast", 150, 1200, 160),
            # Hyderabad
            ("HYD", "WGC", "Warangal Airport", "Telangana", 145, 1400, 170),
            # Kolkata
            ("CCU", "IXB", "Bagdogra Airport", "West Bengal", 600, 3500, 480),
            # Jaipur / Jodhpur
            ("JAI", "JDH", "Jodhpur Airport", "Rajasthan", 330, 2500, 300),
            ("JDH", "JAI", "Jaipur Airport", "Rajasthan", 330, 2500, 300),
            # Lucknow / Varanasi
            ("LKO", "VNS", "Varanasi Airport", "Uttar Pradesh", 320, 2200, 280),
            ("VNS", "LKO", "Lucknow Airport", "Uttar Pradesh", 320, 2200, 280),
            # Kochi / Trivandrum
            ("COK", "TRV", "Trivandrum Airport", "Kerala", 210, 1600, 240),
            ("TRV", "COK", "Kochi Airport", "Kerala", 210, 1600, 240),
            # Ahmedabad / Vadodara
            ("AMD", "BDQ", "Vadodara Airport", "Gujarat", 110, 1000, 120),
            ("BDQ", "AMD", "Ahmedabad Airport", "Gujarat", 110, 1000, 120),
        ]
        
        try:
            async with self.lock:
                for alt in alternatives:
                    await self.db.execute("""
                        INSERT OR IGNORE INTO airport_alternatives 
                        (primary_code, alt_code, alt_name, city, distance_km, ground_transport_cost, transport_time_mins)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, alt)
                await self.db.commit()
            logger.info(f"Seeded {len(alternatives)} airport alternative pairs.")
        except Exception as e:
            logger.warning(f"Failed to seed airport alternatives: {e}")

