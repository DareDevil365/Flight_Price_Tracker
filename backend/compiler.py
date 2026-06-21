"""
Flight Finder — Task Compiler
Converts raw UI inputs + financial profile into a validated TaskSchema
that the dispatcher uses to launch workers.
"""

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from loguru import logger

def is_indian_airport(code: str) -> bool:
    """Check if the airport code belongs to an Indian airport."""
    indian_airports = {
        "DEL", "BOM", "BLR", "MAA", "CCU", "HYD", "COK", "AMD", "PNQ", "GOI", "GOX", 
        "PAT", "LKO", "TRV", "ATQ", "NAG", "JAI", "BDQ", "BBI", "VNS", "VTZ", "RPR", 
        "IXC", "IXR", "IXB", "IXE", "IXD", "JJD", "IDR", "TRZ", "CJB", "IXM", "SXR", 
        "DED", "TIR", "UDR", "JLR", "RJA", "IXS", "SHL", "TEZ", "AJL", "DMU", "IMF", 
        "JRH", "DIB", "GAU", "IXZ", "IXA", "IXW", "IXU", "IXY", "IXG", "IXL", "IXV", 
        "IXK", "IXH", "IXN", "IXP", "IXQ", "IXT", "IXJ", "JGA", "HSR", "KHM", "KLH",
        "KNU", "KUU", "LDA", "MTE", "MUA", "MZA", "MZU", "MYQ", "NDC", "NGP", "NND",
        "NVY", "OMN", "PAB", "PGH", "PJT", "PUT", "RGH", "RJD", "RKM", "RUA", "RUP",
        "SBD", "SSE", "TEI", "YOL", "ZER", "KBH", "BEP", "BHU", "BHJ", "BHO", "CCJ"
    }
    if not code:
        return False
    return code.upper().strip() in indian_airports

def is_domestic_route(origin: str, dest: str) -> bool:
    """Check if both origin and destination airports are in India."""
    return is_indian_airport(origin) and is_indian_airport(dest)

def is_international_only_coupon(code: str, description: str) -> bool:
    """Determine if a coupon is valid ONLY for international flights."""
    code_upper = code.upper()
    desc_lower = description.lower()
    
    intl_keywords = [
        "intl", "international", "universal", "videsh", "pardes", 
        "outside india", "global", "world", "foreign", "overseas",
        # International destinations
        "singapore", "malaysia", "thailand", "bangkok", "phuket", "bali",
        "dubai", "dxb", "london", "lhr", "usa", "america", "europe", 
        "australia", "new zealand", "indonesia", "cambodia", "myanmar", 
        "vietnam", "philippines", "maldives", "canada", "germany", "france",
        # International airlines
        "singapore airlines", "malaysia airlines", "cathay", "lufthansa", 
        "emirates", "qatar", "etihad", "thai airways", "british airways", 
        "air france", "qantas", "gulf air", "oman air", "kuwait airways", 
        "saudia", "flydubai", "air arabia", "scoot", "srilankan", "malindo"
    ]
    
    if any(kw in code_upper for kw in ["INTL", "VIDESH", "PARDES", "GLOBAL", "WORLD"]):
        return True
        
    if any(kw in desc_lower for kw in intl_keywords):
        negatives = ["not valid on international", "domestic only", "excludes international"]
        if any(neg in desc_lower for neg in negatives):
            return False
        return True
        
    return False

def is_domestic_only_coupon(code: str, description: str) -> bool:
    """Determine if a coupon is valid ONLY for domestic flights."""
    code_upper = code.upper()
    desc_lower = description.lower()
    
    dom_keywords = ["domestic", "within india", "india only", "dom"]
    
    if any(kw in code_upper for kw in ["DOM", "DOMESTIC", "INDIA"]):
        if "AIRINDIA" in code_upper and "DOM" not in code_upper:
            pass
        else:
            return True
            
    if any(kw in desc_lower for kw in dom_keywords):
        negatives = ["not valid on domestic", "international only", "excludes domestic"]
        if any(neg in desc_lower for neg in negatives):
            return False
        return True
        
    return False


def is_flight_coupon(code: str, description: str) -> bool:
    """Determine if a coupon is valid for flights (filtering out hotels, bus, train, recharges, etc.)."""
    code_upper = code.upper()
    desc_lower = (description or "").lower()
    
    non_flight_keywords = [
        "hotel", "homestay", "bus", "train", "cab", "taxi", "recharge", 
        "gold", "dominos", "pizza", "bill payment", "electricity", "dth"
    ]
    
    flight_keywords = ["flight", "airline", "air ticket", "fly", "aviation", "videsh", "pardes"]
    
    has_non_flight = any(kw in desc_lower for kw in non_flight_keywords) or any(kw in code_upper for kw in ["BUS", "HOTEL", "TRAIN", "GOLD", "RECHARGE"])
    
    if has_non_flight:
        if any(kw in desc_lower for kw in flight_keywords) or any(kw in code_upper for kw in ["FLY", "FLIGHT"]):
            return True
        return False
        
    return True


class TaskCompiler:
    def __init__(self, db, text_ai):
        self.db = db
        self.text_ai = text_ai

    async def compile(self, search_input: dict) -> dict:
        """
        Convert raw UI SearchSchema into a complete TaskSchema.
        - Validate all fields
        - Fetch relevant coupons from SQLite for each platform
        - Parse custom instructions through LLM for soft rules
        - Return complete TaskSchema ready for dispatch
        """
        search_id = search_input.get("searchId", str(uuid.uuid4()))
        trip = search_input.get("trip", {})
        financial = search_input.get("financial", {})
        platforms = search_input.get("platforms", [])
        cloak = search_input.get("cloak", {})
        # Extract codes supporting dict or string
        origin = trip.get("origin", {})
        dest = trip.get("destination", {})
        origin_code = origin.get("code", "") if isinstance(origin, dict) else (origin or "")
        dest_code = dest.get("code", "") if isinstance(dest, dict) else (dest or "")

        # Validate required fields
        self._validate_trip(trip)

        # Route classification
        is_domestic = is_domestic_route(origin_code, dest_code)
        logger.info(f"Route classified as: {'DOMESTIC' if is_domestic else 'INTERNATIONAL'} ({origin_code} -> {dest_code})")

        # Fetch coupons per platform from DB
        coupons_by_platform = {}
        for platform in platforms:
            all_coupons = await self.db.get_coupons_for_platform(platform)
            
            # Filter coupons
            filtered_coupons = []
            for c in all_coupons:
                code = c.get("code", "")
                desc = c.get("description", "")
                
                # Exclude non-flight coupons
                if not is_flight_coupon(code, desc):
                    logger.info(f"Filtering out non-flight coupon {code} ({desc[:30]}...)")
                    continue
                
                is_intl_coupon = is_international_only_coupon(code, desc)
                is_dom_coupon = is_domestic_only_coupon(code, desc)
                
                if is_domestic:
                    # On domestic routes, exclude international-only coupons
                    if is_intl_coupon and not is_dom_coupon:
                        logger.info(f"Filtering out international-only coupon {code} for domestic route {origin_code}->{dest_code}")
                        continue
                else:
                    # On international routes, exclude domestic-only coupons
                    if is_dom_coupon and not is_intl_coupon:
                        logger.info(f"Filtering out domestic-only coupon {code} for international route {origin_code}->{dest_code}")
                        continue
                        
                filtered_coupons.append(c)
                
            coupons_by_platform[platform] = filtered_coupons
            logger.info(f"Loaded {len(filtered_coupons)} route-filtered flight coupons (out of {len(all_coupons)}) for {platform}")

        # Parse custom instructions through LLM (if provided)
        soft_rules = []
        custom_text = financial.get("customInstructions", "").strip()
        if custom_text and self.text_ai:
            try:
                soft_rules = await self.text_ai.parse_custom_instructions(custom_text)
            except Exception as e:
                logger.warning(f"LLM instruction parsing failed, using raw text: {e}")
                soft_rules = [{"type": "raw", "text": custom_text}]

        # Build TaskSchema
        task = {
            "search_id": search_id,
            "trip": {
                "trip_type": trip.get("tripType", "one_way"),
                "origin": origin_code,
                "destination": dest_code,
                "departure_date": trip.get("departureDate", ""),
                "return_date": trip.get("returnDate"),
                "preferred_time": trip.get("preferredTime", "ANY"),
                "passenger_count": trip.get("passengerCount", 1),
                "cabin_class": trip.get("cabinClass", "ECONOMY"),
                "specific_flight_number": trip.get("specificFlightNumber"),
                "nearby_dates_range": trip.get("nearbyDatesRange", 2),
                "nearby_airports": trip.get("nearbyAirports", True),
            },
            "financial": {
                "whitelisted_banks": financial.get("whitelistedBanks", []),
                "blacklisted_banks": financial.get("blacklistedBanks", []),
                "allowed_card_types": financial.get("allowedCardTypes", ["CREDIT", "DEBIT", "NET_BANKING", "UPI", "WALLET"]),
                "allow_emi": financial.get("allowEMI", False),
                "allow_bnpl": financial.get("allowBNPL", False),
                "allow_wallet_offers": financial.get("allowWalletOffers", True),
                "allow_app_only": financial.get("allowAppOnly", False),
                "max_final_price": financial.get("maxFinalPrice"),
                "custom_instructions": custom_text,
                "card_reward_rates": financial.get("cardRewardRates", []),
                "soft_rules": soft_rules,
            },
            "platforms": platforms,
            "cloak": {
                "engine": "playwright",
                "proxy_mode": "ON" if os.getenv("PROXY_PROVIDER") or cloak.get("proxyCredentials") else "OFF",
                "proxy_credentials": cloak.get("proxyCredentials"),
                "session_isolation": True,
                "human_sim_intensity": "HIGH",
                "request_cooldown_sec": 2.0,
                "fingerprint_rotation": True,
                "max_concurrent_bots": len(platforms),
            },
            "coupons_by_platform": coupons_by_platform,
            "timestamp": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        }

        # Save search to DB
        await self.db.save_search({
            "search_id": search_id,
            "origin": task["trip"]["origin"],
            "destination": task["trip"]["destination"],
            "departure_date": task["trip"]["departure_date"],
            "return_date": task["trip"]["return_date"],
            "passenger_count": task["trip"]["passenger_count"],
            "cabin_class": task["trip"]["cabin_class"],
            "platforms": platforms,
        })

        total_coupons = sum(len(c) for c in coupons_by_platform.values())
        logger.info(
            f"✅ TaskSchema compiled: {search_id} | "
            f"{task['trip']['origin']}→{task['trip']['destination']} | "
            f"{len(platforms)} platforms | {total_coupons} coupons"
        )

        return task

    def _validate_trip(self, trip: dict):
        """Validate required trip fields."""
        origin = trip.get("origin", {})
        dest = trip.get("destination", {})

        origin_code = origin.get("code") if isinstance(origin, dict) else origin
        dest_code = dest.get("code") if isinstance(dest, dict) else dest

        if not origin_code:
            raise ValueError("Origin airport is required")
        if not dest_code:
            raise ValueError("Destination airport is required")
        if not trip.get("departureDate"):
            raise ValueError("Departure date is required")
        if origin_code == dest_code:
            raise ValueError("Origin and destination cannot be the same")
