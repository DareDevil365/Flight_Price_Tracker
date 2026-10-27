"""
Flight Finder — Smart Suggestions Engine
Combines real scraped flights, database price history, and ensemble price predictions
to generate actionable money-saving travel suggestions, personalized to user history.
"""

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from loguru import logger
from typing import Optional
from price_predictor import PricePredictor


def parse_duration_to_minutes(duration_str: str) -> int:
    """Helper to parse duration strings like '2h 15m', '4h', '30m' into minutes."""
    if not duration_str:
        return 0
    hours = 0
    minutes = 0
    h_match = re.search(r'(\d+)\s*h', duration_str, re.IGNORECASE)
    m_match = re.search(r'(\d+)\s*m', duration_str, re.IGNORECASE)
    if h_match:
        hours = int(h_match.group(1))
    if m_match:
        minutes = int(m_match.group(1))
    return hours * 60 + minutes


class SmartAdvisor:
    def __init__(self, db, predictor: PricePredictor, user_prefs=None, profile_path=None):
        self.db = db
        self.predictor = predictor
        self.user_prefs = user_prefs
        self.profile_path = profile_path

    def _get_user_lounge_cards(self) -> list[str]:
        """Extract whitelisted cards from config/user_profile.json."""
        config_path = self.profile_path or Path(__file__).parent.parent / "config" / "user_profile.json"
        user_cards = []
        if config_path.exists():
            try:
                profile = json.loads(config_path.read_text(encoding="utf-8"))
                # Support flat list or nested financial rates
                card_rates = profile.get("cardRewardRates", [])
                if not card_rates and "financial" in profile:
                    card_rates = profile["financial"].get("cardRewardRates", [])

                for c in card_rates:
                    bank_name = c.get("bank") or c.get("bankName")
                    if bank_name:
                        user_cards.append(bank_name.upper())
            except Exception as e:
                logger.warning(f"[SmartAdvisor] Error reading user profile cards: {e}")
        return user_cards

    def _determine_layover_airport(self, origin: str, destination: str, flight: dict) -> str:
        """Find the layover airport based on flight attributes or fallback heuristics."""
        layover = flight.get("layover_airport") or flight.get("layover")
        if layover:
            return layover.upper()

        origin = origin.upper()
        destination = destination.upper()
        if destination in ["GOI", "GOX", "COK", "TRV"]:
            return "BOM"
        if destination in ["PAT", "CCU", "GAU", "IXZ"]:
            return "DEL"
        return "BOM"

    async def get_advisory(self, trip: dict, flights: list[dict], date_alternatives: list[dict] = None, search_id: str = None, is_sub_query: bool = False) -> dict:
        """
        Analyze current flights list and alternative dates to generate saving recommendations.
        """
        origin = trip.get("origin", "").upper()
        destination = trip.get("destination", "").upper()
        travel_date = trip.get("departure_date", "")
        route = f"{origin}-{destination}"
        
        if not search_id:
            search_id = trip.get("search_id") or trip.get("id")

        is_round_trip = trip.get("trip_type") == "round_trip" and not is_sub_query

        # If it is a round-trip and not a recursive sub-query, handle split aggregation
        if is_round_trip:
            outbound_flights = []
            inbound_flights = []
            return_date = trip.get("return_date")

            for f in flights:
                f_num = f.get("flight_number", "")
                if f.get("departure_date") == return_date or (f_num and f"{destination} ➔ {origin}" in f_num):
                    inbound_flights.append(f)
                else:
                    outbound_flights.append(f)

            # Run outbound and inbound advisories recursively
            outbound_trip = trip.copy()
            outbound_trip["trip_type"] = "one_way"

            inbound_trip = trip.copy()
            inbound_trip["origin"] = trip["destination"]
            inbound_trip["destination"] = trip["origin"]
            inbound_trip["departure_date"] = trip["return_date"]
            inbound_trip["return_date"] = None
            inbound_trip["trip_type"] = "one_way"

            outbound_payload = await self.get_advisory(outbound_trip, outbound_flights, date_alternatives, search_id, is_sub_query=True)
            inbound_payload = await self.get_advisory(inbound_trip, inbound_flights, None, search_id, is_sub_query=True)

            suggestions = []

            # Add split-ticket combo strategy
            cheapest_outbound = min(outbound_flights, key=lambda f: f.get("effective_price", f.get("final_price", 999999.0))) if outbound_flights else None
            cheapest_inbound = min(inbound_flights, key=lambda f: f.get("effective_price", f.get("final_price", 999999.0))) if inbound_flights else None

            total_savings = 0
            if cheapest_outbound and cheapest_inbound:
                out_eff = cheapest_outbound.get("effective_price", cheapest_outbound["final_price"])
                in_eff = cheapest_inbound.get("effective_price", cheapest_inbound["final_price"])
                out_base = cheapest_outbound.get("base_price", out_eff)
                in_base = cheapest_inbound.get("base_price", in_eff)

                out_savings = out_base - out_eff
                in_savings = in_base - in_eff
                total_savings = out_savings + in_savings

                out_plat = cheapest_outbound.get("platform", "OTA").upper()
                in_plat = cheapest_inbound.get("platform", "OTA").upper()
                out_coupon = cheapest_outbound.get("best_coupon_code")
                in_coupon = cheapest_inbound.get("best_coupon_code")

                out_coupon_str = f" using Coupon {out_coupon}" if out_coupon else " (no coupon)"
                in_coupon_str = f" using Coupon {in_coupon}" if in_coupon else " (no coupon)"

                detail_str = (
                    f"Maximize savings by booking separate one-way tickets: "
                    f"Book outbound on {out_plat}{out_coupon_str} (saves ₹{int(out_savings):,}) "
                    f"+ Book inbound on {in_plat}{in_coupon_str} (saves ₹{int(in_savings):,}). "
                    f"Total Combined Saved: ₹{int(total_savings):,}."
                )

                suggestions.append({
                    "type": "COMBO",
                    "title": "Split-Ticket Round-Trip Strategy",
                    "saving": int(total_savings),
                    "net_saving": int(total_savings),
                    "detail": detail_str
                })

            # Merge outbound suggestions
            for s in outbound_payload.get("suggestions", []):
                if s.get("type") != "COMBO":
                    s_copy = s.copy()
                    s_copy["title"] = f"Outbound: {s_copy['title']}"
                    suggestions.append(s_copy)

            # Merge inbound suggestions
            for s in inbound_payload.get("suggestions", []):
                if s.get("type") != "COMBO":
                    s_copy = s.copy()
                    s_copy["title"] = f"Inbound: {s_copy['title']}"
                    suggestions.append(s_copy)

            # Get base prediction from PricePredictor for outbound (or merge them)
            decision = outbound_payload.get("verdict", "MONITOR")

            # Record tracking for merged suggestions in SQLite
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

            return {
                "route": f"{origin} ⇄ {destination}",
                "travel_date": f"{travel_date} to {return_date}",
                "verdict": decision,
                "urgency": outbound_payload.get("urgency", "MEDIUM"),
                "confidence": outbound_payload.get("confidence", 0.75),
                "recommended_book_by": outbound_payload.get("recommended_book_by"),
                "potential_savings": int(total_savings) if cheapest_outbound and cheapest_inbound else 0,
                "advice": f"Outbound: {outbound_payload.get('advice')}\nInbound: {inbound_payload.get('advice')}",
                "scenarios": outbound_payload.get("scenarios", []) + inbound_payload.get("scenarios", []),
                "suggestions": suggestions
            }

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
                layover_airport = self._determine_layover_airport(origin, destination, cheapest_stop)
                user_cards = self._get_user_lounge_cards()

                # Check lounge support
                lounge_banks = ["HDFC", "SBI", "ICICI", "AXIS"]
                matching_card = next((card for card in user_cards if card in lounge_banks), None)

                lounge_support = {
                    "DEL": ["HDFC", "SBI", "ICICI", "AXIS"],
                    "BOM": ["HDFC", "SBI", "ICICI", "AXIS"],
                    "BLR": ["HDFC", "SBI", "ICICI", "AXIS"],
                    "HYD": ["HDFC", "SBI", "ICICI", "AXIS"],
                    "MAA": ["HDFC", "SBI", "ICICI", "AXIS"],
                    "CCU": ["HDFC", "SBI", "ICICI", "AXIS"],
                    "GOI": ["HDFC", "SBI", "ICICI"],
                    "GOX": ["HDFC", "SBI", "ICICI"],
                }

                has_lounge = False
                if matching_card and layover_airport in lounge_support:
                    if matching_card in lounge_support[layover_airport]:
                        has_lounge = True

                # Travel duration delta calculation
                nonstop_mins = parse_duration_to_minutes(cheapest_nonstop.get("duration", ""))
                stop_mins = parse_duration_to_minutes(cheapest_stop.get("duration", ""))
                extra_mins = max(30, stop_mins - nonstop_mins) if (stop_mins and nonstop_mins) else 120
                extra_hours = round(extra_mins / 60.0, 1)
                savings_per_hour = int(savings / (extra_mins / 60.0))

                if has_lounge:
                    detail_str = (
                        f"Comfortable Layover: A 1-stop flight via {layover_airport} is available for "
                        f"₹{int(cheapest_stop['final_price']):,}, saving you ₹{int(savings):,} over the cheapest non-stop flight "
                        f"(₹{int(cheapest_nonstop['final_price']):,}). Since you hold an {matching_card} card, you can wait "
                        f"comfortably in the airport lounge for free, bypassing the layover discomfort!"
                    )
                else:
                    detail_str = (
                        f"Budget Saver (Slight Discomfort): A 1-stop flight via {layover_airport} is available for "
                        f"₹{int(cheapest_stop['final_price']):,}, saving you ₹{int(savings):,} over the cheapest non-stop flight "
                        f"(₹{int(cheapest_nonstop['final_price']):,}). Even though free lounge access is not available at {layover_airport}, "
                        f"accepting this slight discomfort effectively earns you ₹{savings_per_hour:,}/hr for the extra {extra_hours}h wait time."
                    )

                suggestions.append({
                    "type": "LAYOVER",
                    "title": f"Accept 1-stop layover via {layover_airport} ({'Lounge Available' if has_lounge else 'Slight Discomfort'})",
                    "saving": int(savings),
                    "net_saving": int(savings),
                    "flight_id": cheapest_stop.get("id"),
                    "has_lounge": has_lounge,
                    "matching_card": matching_card,
                    "layover_airport": layover_airport,
                    "extra_hours": extra_hours,
                    "savings_per_hour": savings_per_hour,
                    "detail": detail_str
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
