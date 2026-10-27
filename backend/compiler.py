"""
Flight Finder â€” Task Compiler
Converts raw UI inputs + financial profile into a validated TaskSchema
that the dispatcher uses to launch workers.
"""

import json
import os
import uuid
from pathlib import Path
from datetime import datetime, timezone, date
import re
from typing import Optional

from loguru import logger

_AIRPORT_REFERENCE = json.loads((Path(__file__).parent/'data'/'indian_airports.json').read_text(encoding='utf-8'))
INDIAN_AIRPORT_CODES = frozenset(row['code'] for row in _AIRPORT_REFERENCE['airports'])


def is_indian_airport(code: str) -> bool:
    """Country reference, not proof that an airport has a bookable service."""
    return isinstance(code,str) and code.upper().strip() in INDIAN_AIRPORT_CODES

def is_domestic_route(origin: str, dest: str) -> bool:
    """Check if both origin and destination airports are in India."""
    return is_indian_airport(origin) and is_indian_airport(dest)

def is_international_only_coupon(code: str, description: str) -> bool:
    """Determine if a coupon is valid ONLY for international flights."""
    code_upper = code.upper()
    desc_lower = description.lower()
    
    intl_keywords = [
        "intl", "international", "videsh", "pardes",
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

    async def compile(self, search_input: dict, *, persist: bool = True) -> dict:
        """
        Convert raw UI SearchSchema into a complete TaskSchema.
        - Validate all fields
        - Fetch relevant coupons from SQLite for each platform
        - Parse custom instructions through LLM for soft rules
        - Return complete TaskSchema ready for dispatch
        """
        if not isinstance(search_input,dict):
            raise ValueError('Search must be an object')
        search_id = search_input.get("searchId", str(uuid.uuid4()))
        trip = search_input.get("trip", {})
        financial = search_input.get("financial", {})
        platforms = search_input.get("platforms", [])
        cloak = search_input.get("cloak", {})
        if not all(isinstance(value,dict) for value in (trip,financial,cloak)):
            raise ValueError('Trip, financial settings and browser settings must be objects')
        self._validate_trip(trip)
        if not isinstance(platforms,list) or not platforms or len(platforms)>12 or any(not isinstance(p,str) or not p.strip() for p in platforms):
            raise ValueError('Select between one and twelve platforms')
        for key in ('whitelistedBanks','blacklistedBanks','ownedCardNames','excludedCardNames','allowedCardTypes'):
            if key in financial and (not isinstance(financial[key],list) or any(not isinstance(item,str) or not item.strip() for item in financial[key])):
                raise ValueError(key+' must be a list of names')
        for key in ('allowEMI','allowBNPL','allowWalletOffers','allowAppOnly'):
            if key in financial and type(financial[key]) is not bool:
                raise ValueError(key+' must be true or false')
        if 'allowedCardTypes' in financial and (not financial['allowedCardTypes'] or set(financial['allowedCardTypes'])-{'CREDIT','DEBIT','NET_BANKING','UPI','WALLET'}):
            raise ValueError('Unsupported or empty payment methods')
        if not isinstance(financial.get('customInstructions',''),str):
            raise ValueError('Custom instructions must be text')
        cap=financial.get('maxFinalPrice')
        if cap is not None and (isinstance(cap,bool) or not isinstance(cap,(int,float)) or not 0<cap<float('inf')):
            raise ValueError('Budget must be a finite positive number')
        if type(cloak.get('maxConcurrentBots',3)) is not int or not 1<=cloak.get('maxConcurrentBots',3)<=3:
            raise ValueError('Browser concurrency must be between one and three')
        if cloak.get('proxyMode','OFF') not in ('OFF','ON'):
            raise ValueError('Unsupported proxy mode')
        # Extract codes supporting dict or string
        origin = trip.get("origin", {})
        dest = trip.get("destination", {})
        origin_code = (origin.get("code", "") if isinstance(origin, dict) else (origin or "")).strip().upper()
        dest_code = (dest.get("code", "") if isinstance(dest, dict) else (dest or "")).strip().upper()

        # Validate required fields
        self._validate_trip(trip)
        if not platforms or len(platforms) > 12 or any(not isinstance(p, str) for p in platforms):
            raise ValueError("Select between one and twelve platforms")
        platforms = list(dict.fromkeys(platforms))
        if cloak.get("engine", "playwright") not in ("playwright", "camoufox"):
            raise ValueError("Unknown browser engine")

        # Route classification
        is_domestic = is_domestic_route(origin_code, dest_code)
        logger.info(f"Route classified as: {'DOMESTIC' if is_domestic else 'INTERNATIONAL'} ({origin_code} -> {dest_code})")

        # Fetch coupons per platform from DB
        coupons_by_platform = {}
        for platform in platforms:
            all_coupons = await self.db.get_live_coupons(platform)
            
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

        if custom_text and (not soft_rules or any(r.get('type') in ('raw','raw_rule') for r in soft_rules)):
            raise ValueError('Custom rules support bank ownership/exclusions and EMI/BNPL exclusions. Use the form for other criteria; unrecognized rules cannot be enforced.')

        # Build TaskSchema
        financial = dict(financial)
        for rule in soft_rules:
            if rule.get('type') == 'whitelist_bank':
                financial['whitelistedBanks'] = list(set(financial.get('whitelistedBanks', []) + [rule['bank']]))
            elif rule.get('type') == 'blacklist_bank':
                financial['blacklistedBanks'] = list(set(financial.get('blacklistedBanks', []) + [rule['bank']]))
            elif rule.get('type') == 'block_emi':
                financial['allowEMI'] = False
            elif rule.get('type') == 'block_bnpl':
                financial['allowBNPL'] = False
            elif rule.get('type') == 'only_upi':
                financial['allowedCardTypes'] = ['UPI']
            elif rule.get('type') == 'owned_card':
                financial['ownedCardNames'] = list(dict.fromkeys([*financial.get('ownedCardNames',[]),rule['card']]))
            elif rule.get('type') == 'excluded_card':
                financial['excludedCardNames'] = list(dict.fromkeys([*financial.get('excludedCardNames',[]),rule['card']]))
        cap = financial.get('maxFinalPrice')
        if cap is not None and (isinstance(cap,bool) or not isinstance(cap,(int,float)) or not 0 < cap < float('inf')):
            raise ValueError('Budget must be a finite positive number')
        task = {
            "search_id": search_id,
            "trip": {
                "trip_type": trip.get("tripType", "one_way"),
                "is_domestic": is_domestic,
                "origin": origin_code,
                "destination": dest_code,
                "departure_date": trip.get("departureDate", ""),
                "return_date": trip.get("returnDate"),
                "preferred_time": trip.get("preferredTime", "ANY"),
                "max_stops": trip.get('maxStops'),
                "passenger_count": trip.get("passengerCount", 1),
                "cabin_class": trip.get("cabinClass", "ECONOMY"),
                "specific_flight_number": trip.get("specificFlightNumber"),
                "nearby_dates_range": max(0, min(3, int(trip.get("nearbyDatesRange", 0)))),
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
                "owned_card_names": financial.get("ownedCardNames", []),
                "excluded_card_names": financial.get("excludedCardNames", []),
                "passenger_count": trip.get("passengerCount",1),
                "is_domestic": is_domestic,
                "soft_rules": soft_rules,
            },
            "platforms": platforms,
            "cloak": {
                "engine": "playwright",
                "showBrowser": bool(cloak.get("showBrowser", False)),
                "proxy_mode": cloak.get("proxyMode", "OFF"),
                "proxy_credentials": cloak.get("proxyCredentials"),
                "session_isolation": True,
                "human_sim_intensity": "HIGH",
                "request_cooldown_sec": 2.0,
                "fingerprint_rotation": True,
                "max_concurrent_bots": max(1, min(3, int(cloak.get("maxConcurrentBots", 3)))),
            },
            "coupons_by_platform": coupons_by_platform,
            "timestamp": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        }

        # Validation-only compilation must not create a phantom queued search.
        if persist:
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
            f"âœ… TaskSchema compiled: {search_id} | "
            f"{task['trip']['origin']}â†’{task['trip']['destination']} | "
            f"{len(platforms)} platforms | {total_coupons} coupons"
        )

        return task

    def _validate_trip(self, trip: dict):
        """Validate required trip fields."""
        if not isinstance(trip,dict):
            raise ValueError('Trip must be an object')
        if trip.get('preferredTime','ANY') not in ('ANY','MORNING','AFTERNOON','EVENING','NIGHT'):
            raise ValueError('Unsupported departure time preference')
        if type(trip.get('nearbyDatesRange',0)) is not int or not 0<=trip.get('nearbyDatesRange',0)<=3:
            raise ValueError('Nearby date range must be between zero and three days')
        if 'nearbyAirports' in trip and type(trip['nearbyAirports']) is not bool:
            raise ValueError('Nearby airports must be true or false')
        if trip.get('specificFlightNumber') not in (None,'') and (not isinstance(trip['specificFlightNumber'],str) or not re.fullmatch(r'[A-Za-z0-9 -]{2,25}',trip['specificFlightNumber'])):
            raise ValueError('Enter a valid flight number or leave it unspecified')
        if trip.get('maxStops') is not None and (type(trip['maxStops']) is not int or not 0<=trip['maxStops']<=2):
            raise ValueError('Maximum stops must be 0, 1, 2 or unspecified')
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
        for code in (origin_code, dest_code):
            if not isinstance(code, str) or not re.fullmatch(r"[A-Z]{3}", code.strip().upper()):
                raise ValueError("Airport codes must contain three letters")
            if not is_indian_airport(code):
                raise ValueError("Only domestic Indian airport pairs are supported. Select a known Indian airport code.")
        if origin_code.strip().upper() == dest_code.strip().upper():
            raise ValueError("Origin and destination cannot be the same")
        departure = date.fromisoformat(trip["departureDate"])
        if departure < date.today():
            raise ValueError("Departure date cannot be in the past")
        if trip.get("tripType", "one_way") not in ("one_way", "round_trip"):
            raise ValueError("Unsupported trip type")
        if trip.get("tripType") == "round_trip":
            if not trip.get("returnDate") or date.fromisoformat(trip["returnDate"]) < departure:
                raise ValueError("Return date must be on or after departure")
        if type(trip.get("passengerCount", 1)) is not int or not 1 <= trip.get("passengerCount", 1) <= 9:
            raise ValueError("Passenger count must be between one and nine")
        if trip.get("cabinClass", "ECONOMY") not in ("ECONOMY", "PREMIUM_ECONOMY", "BUSINESS", "FIRST"):
            raise ValueError("Unsupported cabin class")
