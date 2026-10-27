"""Quote identity and validation shared by scrapers, ranking and price history."""
import math
import re
from datetime import date, datetime, timezone, timedelta
from urllib.parse import urlencode


def duration_minutes(value):
    """Parse only an entire supported displayed duration, not unrelated prose."""
    if not isinstance(value,str):
        return None
    match=re.fullmatch(r'\s*(?:(\d+)\s*h(?:rs?|ours?)?\s*)?(?:(\d+)\s*m(?:ins?|inutes?)?\s*)?',value,re.I)
    if not match or not any(match.groups()):
        return None
    hours,minutes=map(lambda x:int(x or 0),match.groups())
    if hours and minutes>=60:
        return None
    total=hours*60+minutes
    return total if total>0 else None


def search_url(platform: str, trip: dict) -> str:
    origin, dest, day = trip['origin'], trip['destination'], trip['departure_date']
    adults = trip.get('passenger_count', 1)
    cabin = trip.get('cabin_class', 'ECONOMY')
    dt = date.fromisoformat(day)
    if platform == 'makemytrip':
        params = dict(itinerary=f'{origin}-{dest}-{dt:%d/%m/%Y}', tripType='O',
                      paxType=f'A-{adults}_C-0_I-0', intl=str(not trip.get('is_domestic', True)).lower(),
                      cabinClass={'ECONOMY':'E', 'BUSINESS':'B', 'PREMIUM_ECONOMY':'PE', 'FIRST':'F'}[cabin])
        return 'https://www.makemytrip.com/flight/search?' + urlencode(params)
    if platform == 'easemytrip':
        # GOX is absent from this site's code-to-city lookup; full public form values
        # avoid an empty source city and the resulting hidden flight list.
        def sector(code):
            return f'{code}-Goa-India' if code == 'GOX' else code
        return 'https://flight.easemytrip.com/FlightList/Index?' + urlencode(dict(
            srch=f'{sector(origin)}|{sector(dest)}|{dt:%d/%m/%Y}', px=f'{adults}-0-0',
            cbn={'ECONOMY':'0', 'BUSINESS':'2', 'PREMIUM_ECONOMY':'4', 'FIRST':'1'}[cabin], tp='O', c='IN'))
    if platform == 'cleartrip':
        return 'https://www.cleartrip.com/flights/results?' + urlencode(dict(
            **{'from':origin,'class':{'ECONOMY':'Economy','BUSINESS':'Business','PREMIUM_ECONOMY':'Premium Economy','FIRST':'First'}[cabin]},
            to=dest, depart_date=f'{dt:%d/%m/%Y}', adults=adults, childs=0, infants=0))
    if platform!='google_flights':
        raise ValueError('No validated search URL adapter for this provider')
    query = f'Flights from {origin} to {dest} on {day} one way {adults} adults {cabin.lower().replace("_", " ")}'
    return 'https://www.google.com/travel/flights?' + urlencode({'q':query, 'curr':'INR', 'hl':'en'})


def valid_flights(flights: list, trip: dict) -> list[dict]:
    """Never invent a missing fare or schedule. Deduplicate comparable listings."""
    result = {}
    for flight in flights:
        try:
            if not isinstance(flight, dict):
                continue
            if 'currency' in flight and flight['currency'] != 'INR':
                continue
            if flight.get('departure_date') and flight['departure_date'] != trip['departure_date']:
                continue
            if flight.get('passenger_count') is not None and flight['passenger_count'] != trip.get('passenger_count', 1):
                continue
            if flight.get('cabin_class') and flight['cabin_class'] != trip.get('cabin_class', 'ECONOMY'):
                continue
            if trip.get('is_domestic',True) and flight.get('connection_airports'):
                from compiler import is_indian_airport
                if not isinstance(flight['connection_airports'],list) or any(not isinstance(code,str) or not is_indian_airport(code) for code in flight['connection_airports']):
                    continue
            if isinstance(flight.get('base_price'),bool):
                continue
            if not isinstance(flight.get('stops'),int) or isinstance(flight['stops'],bool) or not 0<=flight['stops']<=4:
                continue
            if trip.get('max_stops') is not None and flight['stops']>trip['max_stops']:
                continue
            if flight.get('origin') and flight['origin'] != trip['origin']:
                continue
            if flight.get('destination') and flight['destination'] != trip['destination']:
                continue
            if flight.get('nearby_airport') and (not flight.get('origin') or not flight.get('destination')):
                continue
            price = float(flight['base_price'])
            if not math.isfinite(price) or price <= 0:
                continue
            if trip.get('passenger_count',1) > 1:
                if flight.get('price_basis') == 'per_person':
                    price *= trip['passenger_count']
                elif flight.get('price_basis') != 'total':
                    continue
            if not math.isfinite(price) or price<=0:
                continue
            departure = flight.get('departure_time', '')
            if not re.fullmatch(r'\d{2}:\d{2}', departure) or int(departure[:2]) > 23 or int(departure[3:]) > 59:
                continue
            arrival = flight.get('arrival_time','')
            if not re.fullmatch(r'\d{2}:\d{2}',arrival) or int(arrival[:2])>23 or int(arrival[3:])>59:
                continue
            duration=duration_minutes(flight.get('duration'))
            if trip.get('is_domestic',True) and duration is not None:
                clock_difference=(int(arrival[:2])*60+int(arrival[3:])-int(departure[:2])*60-int(departure[3:]))%1440
                delta=abs(duration%1440-clock_difference)
                if min(delta,1440-delta)>2:
                    continue
            preferred = trip.get('preferred_time', 'ANY')
            hour = int(departure[:2])
            windows = {'MORNING': (6,12), 'AFTERNOON':(12,18), 'EVENING':(18,24), 'NIGHT':(0,6)}
            if preferred in windows and not windows[preferred][0] <= hour < windows[preferred][1]:
                continue
            requested = re.sub(r'[^A-Z0-9]', '', (trip.get('specific_flight_number') or '').upper())
            number = re.sub(r'[^A-Z0-9]', '', str(flight.get('flight_number', '')).upper())
            if requested and requested != number:
                continue
            key = (number, departure, flight.get('arrival_time'), flight.get('airline'), flight.get('stops'), flight.get('duration'),
                   repr(flight.get('segments')), repr(flight.get('fare_family')), repr(flight.get('baggage')))
            if key not in result or price < result[key]['base_price']:
                result[key] = {**flight, 'base_price': price}
                if flight.get('price_basis') == 'per_person':
                    # This output already contains the whole party's amount.
                    # Revalidating it must not multiply the adults a second time.
                    result[key].update(price_basis='total', original_price_basis='per_person')
        except (ValueError, TypeError, KeyError):
            continue
    return sorted(result.values(), key=lambda f:f['base_price'])


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def india_today() -> date:
    """Offer booking days use India time even when SQLite/host uses UTC."""
    return datetime.now(timezone(timedelta(hours=5,minutes=30))).date()


def matches_preferences(row: dict, trip: dict) -> bool:
    """Recheck preferences at output/learning boundaries, independent of parsing."""
    stops=row.get('stops')
    if isinstance(stops,bool) or not isinstance(stops,int) or not 0<=stops<=4:
        return False
    if trip.get('max_stops') is not None and stops>trip['max_stops']:
        return False
    requested=re.sub(r'[^A-Z0-9]','',(trip.get('specific_flight_number') or '').upper())
    if requested and requested!=re.sub(r'[^A-Z0-9]','',(row.get('flight_number') or '').upper()):
        return False
    departure=row.get('departure_time','')
    if not re.fullmatch(r'\d{2}:\d{2}',departure) or int(departure[:2])>23 or int(departure[3:])>59:
        return False
    windows={'MORNING':(6,12),'AFTERNOON':(12,18),'EVENING':(18,24),'NIGHT':(0,6)}
    window=windows.get(trip.get('preferred_time','ANY'))
    return not window or window[0]<=int(departure[:2])<window[1]
