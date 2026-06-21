"""
Flight Finder — Smart Suggestions Engine
Combines real scraped flights, database price history, and ensemble price predictions
to generate actionable money-saving travel suggestions, personalized to user history.
"""

import json
from datetime import datetime, timedelta
from loguru import logger
from typing import Optional
from price_predictor import PricePredictor


class SmartAdvisor:
    def __init__(self, db, predictor: PricePredictor, user_prefs=None):
        self.db = db
        self.predictor = predictor
        self.user_prefs = user_prefs

    async def get_advisory(self, trip: dict, flights: list[dict], date_alternatives: list[dict] = None, search_id: str = None) -> dict:
        """
        Analyze current flights list and alternative dates to generate saving recommendations.
        """
        origin = trip.get("origin", "").upper()
        destination = trip.get("destination", "").upper()
        travel_date = trip.get("departure_date", "")
        route = f"{origin}-{destination}"
        
        if not search_id:
            search_id = trip.get("search_id") or trip.get("id")

        # Get base prediction from PricePredictor
        prediction = {}
        try:
            prediction = await self.predictor.predict(origin, destination, travel_date)
        except Exception as e:
            logger.error(f"[SmartAdvisor] Failed to fetch prediction: {e}")
            prediction = {
                "decision": {
                    "signal": "MONITOR",
                    "urgency": "MEDIUM",
                    "confidence": 0.5,
                    "reasoning": "Forecaster unavailable. Monitor price trends."
                },
                "scenarios": []
            }
 
        # Calculate actual Cheapest Non-stop vs 1-Stop from current scraped flights using final_price
        nonstop_flights = [f for f in flights if f.get("stops", 0) == 0]
        stop_flights = [f for f in flights if f.get("stops", 0) > 0]
 
        cheapest_nonstop = min(nonstop_flights, key=lambda f: f.get("final_price", 999999.0)) if nonstop_flights else None
        cheapest_stop = min(stop_flights, key=lambda f: f.get("final_price", 999999.0)) if stop_flights else None
 
        # Build dynamic advice/suggestions
        suggestions = []
 
        # 1. Layover suggestion (if layover is cheaper than non-stop)
        if cheapest_nonstop and cheapest_stop and cheapest_stop.get("final_price", 999999.0) < cheapest_nonstop.get("final_price", 999999.0):
            savings = cheapest_nonstop["final_price"] - cheapest_stop["final_price"]
            if savings > 100:  # Only suggest if savings are meaningful (> ₹100)
                suggestions.append({
                    "type": "LAYOVER",
                    "title": "Accept a 1-stop flight instead of non-stop",
                    "saving": int(savings),
                    "net_saving": int(savings),
                    "flight_id": cheapest_stop.get("id"),
                    "detail": f"A 1-stop flight is available for ₹{int(cheapest_stop['final_price']):,}, saving you ₹{int(savings):,} over the cheapest non-stop flight (₹{int(cheapest_nonstop['final_price']):,})."
                })
 
        # 2. Date flexibility suggestion using scanned/provided date alternatives (up to ±7 days)
        if date_alternatives:
            for np in date_alternatives:
                if np.get("savings", 0.0) > 100:  # Savings relative to the target date
                    savings_val = int(np["savings"])
                    alt_date_str = np["date"]
                    alt_dt = datetime.strptime(alt_date_str, "%Y-%m-%d")
                    
                    # Find cheapest flight on this alternative date to attach its flight_id
                    alt_flights = [f for f in flights if f.get("departure_date") == alt_date_str]
                    flight_id = None
                    if alt_flights:
                        cheapest_alt_flight = min(alt_flights, key=lambda f: f.get("final_price", 999999.0))
                        flight_id = cheapest_alt_flight.get("id")
                        
                    suggestions.append({
                        "type": "DATE_SHIFT",
                        "title": f"Shift date to {alt_dt.strftime('%b %d')} ({alt_date_str})",
                        "saving": savings_val,
                        "net_saving": savings_val,
                        "date": alt_date_str,
                        "flight_id": flight_id,
                        "detail": f"Flights on {alt_date_str} are cheaper. Saving: ₹{savings_val:,}."
                    })
        else:
            # Query from DB as fallback (scans ±7 days dynamically)
            try:
                nearby_prices = await self.db.get_nearby_date_prices(route, travel_date, days_range=7)
                for np in nearby_prices:
                    if np.get("savings", 0.0) > 100:
                        savings_val = int(np["savings"])
                        alt_date_str = np["date"]
                        alt_dt = datetime.strptime(alt_date_str, "%Y-%m-%d")
                        
                        # Find cheapest flight on this alternative date to attach its flight_id
                        alt_flights = [f for f in flights if f.get("departure_date") == alt_date_str]
                        flight_id = None
                        if alt_flights:
                            cheapest_alt_flight = min(alt_flights, key=lambda f: f.get("final_price", 999999.0))
                            flight_id = cheapest_alt_flight.get("id")
                            
                        suggestions.append({
                            "type": "DATE_SHIFT",
                            "title": f"Shift date to {alt_dt.strftime('%b %d')} ({alt_date_str})",
                            "saving": savings_val,
                            "net_saving": savings_val,
                            "date": alt_date_str,
                            "flight_id": flight_id,
                            "detail": f"Flights on {alt_date_str} are cheaper. Saving: ₹{savings_val:,}."
                        })
            except Exception as e:
                logger.warning(f"[SmartAdvisor] Failed to compute date shift savings from DB: {e}")
 
        # 3. Dynamic Airport Alternatives from DB
        if self.db:
            try:
                alts = await self.db.get_airport_alternatives(destination)
                for alt in alts:
                    alt_code = alt["alt_code"]
                    alt_name = alt["alt_name"]
                    extra = alt["ground_transport_cost"]
                    alt_route = f"{origin}-{alt_code}"
                    
                    current_route_avg = await self.db.get_avg_price(route, days=30, source="scraped")
                    alt_route_avg = await self.db.get_avg_price(alt_route, days=30, source="scraped")
                    
                    if current_route_avg and alt_route_avg and alt_route_avg < current_route_avg:
                        gross_saving = current_route_avg - alt_route_avg
                        net_saving = gross_saving - extra
                        if net_saving > 100:
                            suggestions.append({
                                "type": "AIRPORT_ALT",
                                "title": f"Fly to {alt_name} ({alt_code}) instead",
                                "gross_saving": int(gross_saving),
                                "extra_cost": int(extra),
                                "net_saving": int(net_saving),
                                "detail": f"Flights to {alt_code} are typically cheaper by ₹{int(gross_saving):,}, but ground transfer adds ₹{int(extra):,}. Net saving: ₹{int(net_saving):,}."
                            })
            except Exception as e:
                logger.warning(f"[SmartAdvisor] Failed to compute airport alternative savings: {e}")
 
        # 4. Timing / Early Morning Flight Suggestion
        early_morning_flights = [f for f in flights if f.get("departure_time", "") and f.get("departure_time", "") < "06:00"]
        later_flights = [f for f in flights if f.get("departure_time", "") and f.get("departure_time", "") >= "06:00"]
        
        if early_morning_flights and later_flights:
            cheapest_early = min(early_morning_flights, key=lambda f: f.get("final_price", 999999.0))
            later_avg = sum(f["final_price"] for f in later_flights) / len(later_flights)
            
            if cheapest_early["final_price"] < later_avg:
                savings = later_avg - cheapest_early["final_price"]
                if savings > 100:
                    suggestions.append({
                        "type": "TIME_SHIFT",
                        "title": "Take an early morning flight (before 6 AM)",
                        "saving": int(savings),
                        "net_saving": int(savings),
                        "flight_id": cheapest_early.get("id"),
                        "detail": f"Taking the early departure at {cheapest_early['departure_time']} saves you ₹{int(savings):,} compared to the average later flights (₹{int(later_avg):,})."
                    })

        # 5. External Savings & Combo Savings Calculator
        ext_savings = []
        if self.db:
            try:
                platforms = list(set([f.get("platform") for f in flights if f.get("platform")]))
                for p in platforms + ["ALL"]:
                    p_savings = await self.db.get_external_savings(p)
                    ext_savings.extend(p_savings)
            except Exception as e:
                logger.warning(f"[SmartAdvisor] Failed to fetch external savings for combo: {e}")

        # Find best external offer
        best_ext = None
        if ext_savings:
            ref_price = cheapest_nonstop["final_price"] if cheapest_nonstop else 5400.0
            def get_ext_val(ext):
                val = ext.get("savings_value") or 0.0
                if ext.get("savings_unit") == "PERCENT":
                    return ref_price * (val / 100.0)
                return val
            best_ext = max(ext_savings, key=get_ext_val, default=None)

        if best_ext:
            ref_price = cheapest_nonstop["final_price"] if cheapest_nonstop else 5400.0
            val = best_ext.get("savings_value") or 0.0
            ext_saving = int(ref_price * (val / 100.0)) if best_ext.get("savings_unit") == "PERCENT" else int(val)
            
            suggestions.append({
                "type": "CASHBACK",
                "title": f"Use {best_ext['provider']} for payment",
                "saving": ext_saving,
                "net_saving": ext_saving,
                "detail": f"Pay via {best_ext['provider']} to get additional savings. Saving: ₹{ext_saving:,}."
            })

        # Stack suggestions for Combo Savings Calculator
        best_date_shift = max([s for s in suggestions if s["type"] == "DATE_SHIFT"], key=lambda x: x["saving"], default=None)
        best_layover = max([s for s in suggestions if s["type"] == "LAYOVER"], key=lambda x: x["saving"], default=None)
        best_airport = max([s for s in suggestions if s["type"] == "AIRPORT_ALT"], key=lambda x: x["net_saving"], default=None)
        best_time_shift = max([s for s in suggestions if s["type"] == "TIME_SHIFT"], key=lambda x: x["saving"], default=None)
        best_cashback = max([s for s in suggestions if s["type"] == "CASHBACK"], key=lambda x: x["saving"], default=None)

        combo_parts = []
        combo_total_savings = 0
        
        if best_date_shift:
            combo_parts.append(best_date_shift["title"])
            combo_total_savings += best_date_shift["saving"]
        elif best_airport:
            combo_parts.append(best_airport["title"])
            combo_total_savings += best_airport["net_saving"]
            
        if best_layover:
            combo_parts.append("Accept 1-stop layover")
            combo_total_savings += best_layover["saving"]
        elif best_time_shift:
            combo_parts.append("Take early morning departure")
            combo_total_savings += best_time_shift["saving"]

        if best_cashback:
            combo_parts.append(best_cashback["title"])
            combo_total_savings += best_cashback["saving"]

        if len(combo_parts) >= 2:
            combo_desc = " + ".join(combo_parts)
            suggestions.append({
                "type": "COMBO",
                "title": "Combined Savings Strategy",
                "saving": combo_total_savings,
                "net_saving": combo_total_savings,
                "detail": f"Maximize savings by combining steps: {combo_desc}. Total Combined Saved: ₹{combo_total_savings:,}."
            })

        # 6. Personalize Suggestions based on User Preferences
        if self.user_prefs:
            try:
                suggestions = await self.user_prefs.personalize_suggestions(suggestions)
            except Exception as e:
                logger.warning(f"[SmartAdvisor] Suggestions personalization failed: {e}")

        # 7. Track Suggestions in SQLite suggestions tracking table
        if self.db and search_id:
            for s in suggestions:
                try:
                    s_id = await self.db.save_suggestion_tracking(
                        search_id=search_id,
                        suggestion_type=s.get("type"),
                        potential_saving=float(s.get("net_saving") or s.get("saving") or 0.0)
                    )
                    if s_id is not None:
                        s["id"] = s_id
                except Exception as ex:
                    logger.warning(f"[SmartAdvisor] Failed to record suggestion tracking in DB: {ex}")
 
        decision = prediction.get("decision", {})
        
        advisor_payload = {
            "route": f"{origin} → {destination}",
            "travel_date": travel_date,
            "verdict": decision.get("signal", "MONITOR"),
            "urgency": decision.get("urgency", "MEDIUM"),
            "confidence": decision.get("confidence", 0.75),
            "recommended_book_by": decision.get("recommended_book_by"),
            "potential_savings": decision.get("potential_savings", 0),
            "advice": decision.get("reasoning", "Monitor prices for upcoming deals."),
            "scenarios": prediction.get("scenarios", []),
            "suggestions": suggestions
        }
 
        return advisor_payload
