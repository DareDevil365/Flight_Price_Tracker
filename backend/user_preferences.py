"""
Flight Finder — User Preference Learning Engine
Learns user behavior from search patterns, flight selections, and booking decisions.
Builds a preference profile that personalizes recommendations.
"""

import json
from datetime import datetime, timedelta
from loguru import logger
from collections import Counter


class UserPreferences:
    def __init__(self, db):
        self.db = db

    async def record_search(self, search_id: str, trip: dict):
        """Record a search event for pattern learning."""
        try:
            conn = self.db.db
            dep_date = trip.get("departure_date", "")
            dep_dt = None
            dep_dow = None
            dep_month = None
            days_advance = None
            
            if dep_date:
                try:
                    dep_dt = datetime.strptime(dep_date, "%Y-%m-%d")
                    dep_dow = dep_dt.weekday()
                    dep_month = dep_dt.month
                    days_advance = (dep_dt - datetime.now()).days
                except Exception:
                    pass
            
            await conn.execute("""
                INSERT INTO search_patterns 
                (search_id, origin, destination, departure_date, departure_dow, departure_month, days_advance)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (search_id, trip.get("origin", ""), trip.get("destination", ""), 
                  dep_date, dep_dow, dep_month, days_advance))
            await conn.commit()
        except Exception as e:
            logger.warning(f"[UserPreferences] Failed to record search: {e}")

    async def record_flight_selection(self, search_id: str, flight: dict):
        """Record which flight the user selected for booking."""
        try:
            conn = self.db.db
            await conn.execute("""
                UPDATE search_patterns SET 
                    selected_flight_id = ?,
                    selected_airline = ?,
                    selected_stops = ?,
                    selected_departure_time = ?,
                    selected_price = ?
                WHERE search_id = ?
            """, (
                flight.get("id"),
                flight.get("airline"),
                flight.get("stops", 0),
                flight.get("departure_time"),
                flight.get("final_price") or flight.get("effective_price"),
                search_id
            ))
            await conn.commit()
        except Exception as e:
            logger.warning(f"[UserPreferences] Failed to record selection: {e}")

    async def record_handoff(self, search_id: str):
        """Record that user completed the handoff (intent to book)."""
        try:
            conn = self.db.db
            await conn.execute("""
                UPDATE search_patterns SET handoff_completed = 1 WHERE search_id = ?
            """, (search_id,))
            await conn.commit()
        except Exception as e:
            logger.warning(f"[UserPreferences] Failed to record handoff: {e}")

    async def learn_preferences(self):
        """
        Analyze search patterns and booking decisions to build a user preference profile.
        Updates the user_preferences table.
        """
        conn = self.db.db
        preferences = {}
        
        try:
            # 1. Learn preferred airlines
            async with conn.execute("""
                SELECT selected_airline, COUNT(*) as cnt
                FROM search_patterns
                WHERE selected_airline IS NOT NULL AND handoff_completed = 1
                GROUP BY selected_airline ORDER BY cnt DESC LIMIT 5
            """) as cursor:
                rows = await cursor.fetchall()
                if rows:
                    airlines = [{"airline": r[0], "count": r[1]} for r in rows]
                    total = sum(a["count"] for a in airlines)
                    top_airline = airlines[0]
                    confidence = min(0.95, top_airline["count"] / max(total, 1))
                    preferences["preferred_airline"] = {
                        "value": top_airline["airline"],
                        "all": airlines,
                        "confidence": round(confidence, 2),
                        "evidence": total
                    }

            # 2. Learn stop tolerance
            async with conn.execute("""
                SELECT selected_stops, COUNT(*) as cnt
                FROM search_patterns
                WHERE selected_stops IS NOT NULL AND handoff_completed = 1
                GROUP BY selected_stops ORDER BY cnt DESC
            """) as cursor:
                rows = await cursor.fetchall()
                if rows:
                    total = sum(r[1] for r in rows)
                    nonstop_count = sum(r[1] for r in rows if r[0] == 0)
                    nonstop_pref = nonstop_count / total if total > 0 else 0.5
                    
                    preferences["stop_tolerance"] = {
                        "value": "nonstop_preferred" if nonstop_pref > 0.7 else "flexible" if nonstop_pref < 0.4 else "slight_nonstop_preference",
                        "nonstop_ratio": round(nonstop_pref, 2),
                        "confidence": min(0.9, total / 20),  # Need 20+ bookings for high confidence
                        "evidence": total
                    }

            # 3. Learn time preference
            async with conn.execute("""
                SELECT selected_departure_time
                FROM search_patterns
                WHERE selected_departure_time IS NOT NULL AND handoff_completed = 1
            """) as cursor:
                rows = await cursor.fetchall()
                if rows:
                    time_buckets = {"early_morning": 0, "morning": 0, "afternoon": 0, "evening": 0, "night": 0}
                    for row in rows:
                        t = row[0]
                        if t < "06:00":
                            time_buckets["early_morning"] += 1
                        elif t < "12:00":
                            time_buckets["morning"] += 1
                        elif t < "17:00":
                            time_buckets["afternoon"] += 1
                        elif t < "21:00":
                            time_buckets["evening"] += 1
                        else:
                            time_buckets["night"] += 1
                    
                    total = sum(time_buckets.values())
                    preferred_time = max(time_buckets, key=time_buckets.get)
                    preferences["time_preference"] = {
                        "value": preferred_time,
                        "distribution": time_buckets,
                        "confidence": min(0.9, time_buckets[preferred_time] / max(total, 1)),
                        "evidence": total
                    }

            # 4. Learn price sensitivity
            async with conn.execute("""
                SELECT AVG(selected_price), MIN(selected_price), MAX(selected_price)
                FROM search_patterns
                WHERE selected_price IS NOT NULL AND handoff_completed = 1
            """) as cursor:
                row = await cursor.fetchone()
                if row and row[0]:
                    preferences["price_sensitivity"] = {
                        "avg_price": round(row[0], 0),
                        "min_price": round(row[1], 0),
                        "max_price": round(row[2], 0),
                        "confidence": 0.6,
                        "evidence": 0  # Will be filled below
                    }

            # 5. Learn frequently searched routes
            async with conn.execute("""
                SELECT origin, destination, COUNT(*) as cnt, 
                       GROUP_CONCAT(DISTINCT departure_month) as months
                FROM search_patterns
                GROUP BY origin, destination
                ORDER BY cnt DESC LIMIT 5
            """) as cursor:
                rows = await cursor.fetchall()
                if rows:
                    routes = []
                    for r in rows:
                        routes.append({
                            "origin": r[0], "destination": r[1],
                            "search_count": r[2],
                            "typical_months": r[3]
                        })
                    preferences["frequent_routes"] = {
                        "value": routes,
                        "confidence": 0.8,
                        "evidence": sum(r["search_count"] for r in routes)
                    }

            # 6. Learn booking lead time
            async with conn.execute("""
                SELECT AVG(days_advance), MIN(days_advance), MAX(days_advance)
                FROM search_patterns
                WHERE days_advance IS NOT NULL AND days_advance > 0
            """) as cursor:
                row = await cursor.fetchone()
                if row and row[0]:
                    preferences["booking_lead_time"] = {
                        "avg_days": round(row[0]),
                        "min_days": row[1],
                        "max_days": row[2],
                        "confidence": 0.6,
                        "evidence": 0
                    }

            # Save all preferences to database
            for key, pref in preferences.items():
                await conn.execute("""
                    INSERT INTO user_preferences (preference_key, preference_value, confidence, evidence_count, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(preference_key) DO UPDATE SET
                        preference_value = excluded.preference_value,
                        confidence = excluded.confidence,
                        evidence_count = excluded.evidence_count,
                        updated_at = excluded.updated_at
                """, (key, json.dumps(pref), pref.get("confidence", 0.5), 
                      pref.get("evidence", 0), datetime.now().isoformat()))
            
            await conn.commit()
            logger.info(f"🧠 [UserPreferences] Learned {len(preferences)} preference categories.")
            
        except Exception as e:
            logger.error(f"[UserPreferences] Error learning preferences: {e}")

    async def get_profile(self) -> dict:
        """Return the current user preference profile."""
        profile = {}
        try:
            conn = self.db.db
            async with conn.execute("SELECT preference_key, preference_value, confidence FROM user_preferences") as cursor:
                rows = await cursor.fetchall()
                for row in rows:
                    profile[row[0]] = {
                        **json.loads(row[1]),
                        "confidence": row[2]
                    }
        except Exception as e:
            logger.warning(f"[UserPreferences] Error fetching profile: {e}")
        return profile

    async def personalize_suggestions(self, suggestions: list[dict]) -> list[dict]:
        """Adjust suggestions based on user preferences."""
        profile = await self.get_profile()
        if not profile:
            return suggestions
        
        personalized = []
        stop_pref = profile.get("stop_tolerance", {}).get("value", "flexible")
        time_pref = profile.get("time_preference", {}).get("value", "")
        
        for suggestion in suggestions:
            s = suggestion.copy()
            stype = s.get("type", "")
            
            # Adjust layover suggestions based on stop tolerance
            if stype == "LAYOVER":
                if stop_pref == "nonstop_preferred":
                    s["personalized_note"] = "We know you usually prefer non-stop flights, but this layover could save you significantly."
                    s["priority_boost"] = -1  # Lower priority for nonstop lovers
                elif stop_pref == "flexible":
                    s["personalized_note"] = "Based on your history, you're comfortable with layovers."
                    s["priority_boost"] = 1  # Boost for flexible travelers
            
            # Adjust time shift suggestions
            if stype == "TIME_SHIFT":
                if time_pref == "early_morning":
                    s["personalized_note"] = "You often book early morning flights anyway — this is right in your comfort zone!"
                    s["priority_boost"] = 2
                elif time_pref in ["afternoon", "evening"]:
                    s["personalized_note"] = "This is earlier than your usual flights, but the savings are worth considering."
                    s["priority_boost"] = -1
            
            personalized.append(s)
        
        # Sort by savings with priority adjustment
        personalized.sort(
            key=lambda s: (s.get("net_saving", 0) + (s.get("priority_boost", 0) * 100)),
            reverse=True
        )
        
        return personalized
