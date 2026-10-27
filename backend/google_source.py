"""Optional Fli public-page search in a killable child process.

Fli is pinned separately; Playwright remains the fallback and booking engine.
This module's normalizer also validates every returned leg independently.
"""
import asyncio
import json
import math
import os
import re
from pathlib import Path
import sys
from datetime import datetime, timedelta

REVISION='881aee5ff4321e81ea2157cb44be94ce6a21dc1b'


def leg_airline_label(row, leg):
    """Use Google's displayed name, not Fli's outdated airline-name dictionary.

    The live QP enum currently says Air Kenya Aviation for an Akasa flight.
    For mixed-airline legs without a displayed name, retain only the actual code.
    """
    code=leg.airline.name.lstrip('_')
    primary=getattr(row,'primary_airline',None)
    label=getattr(row,'primary_airline_name',None)
    if primary is not None and primary.name.lstrip('_')==code and isinstance(label,str) and label.strip():
        return label.strip()
    return code


def normalize_result(item,trip):
    """Bad optional rows are rejected individually, never poison a valid batch."""
    try:
        return _normalize_result(item, trip)
    except (ValueError, TypeError, KeyError, AttributeError, IndexError, OverflowError):
        return None


def _normalize_result(item,trip):
    if not isinstance(item, dict):
        return None
    legs=item.get('legs') or []
    if not isinstance(legs, list) or not 1 <= len(legs) <= 5 or item.get('currency')!='INR' or item.get('mixed_cabin') or item.get('self_transfer'):
        return None
    price=item.get('price')
    if isinstance(price,bool) or not isinstance(price,(float,int)) or not math.isfinite(price) or price<=0:
        return None
    if legs[0]['origin']!=trip['origin'] or legs[-1]['destination']!=trip['destination']:
        return None
    if legs[0]['departure_date']!=trip['departure_date'] or not isinstance(item.get('stops'),int) or isinstance(item['stops'], bool) or item['stops']!=len(legs)-1:
        return None
    previous=None
    instants=[]
    for leg in legs:
        if not isinstance(leg, dict) or not all(isinstance(leg.get(key), str) and leg[key].strip()
            for key in ('origin','destination','departure_date','departure_datetime','arrival_datetime','airline','flight_number')):
            return None
        if not all(re.fullmatch(r'[A-Z]{3}',leg[key]) for key in ('origin','destination')) or leg['origin']==leg['destination']:
            return None
        if trip.get('is_domestic', True):
            from compiler import is_indian_airport
            if not is_indian_airport(leg['origin']) or not is_indian_airport(leg['destination']):
                return None
        if not re.fullmatch(r'[A-Z0-9]{2,3}-?\d{1,5}',leg['flight_number']):
            return None
        if leg.get('cabin_class') is not None and leg['cabin_class'] != trip.get('cabin_class','ECONOMY'):
            return None
        departure=datetime.fromisoformat(leg['departure_datetime'])
        arrival=datetime.fromisoformat(leg['arrival_datetime'])
        if departure.date().isoformat()!=leg['departure_date']:
            return None
        if trip.get('is_domestic',True) and any(moment.utcoffset() not in (None,timedelta(hours=5,minutes=30)) for moment in (departure,arrival)):
            return None
        # Local clocks cannot establish an international connection timeline.
        # Domestic Indian clocks share a timezone; offset-bearing rows work for either.
        if not trip.get('is_domestic', True) and (departure.utcoffset() is None or arrival.utcoffset() is None):
            return None
        if arrival<=departure or (previous and (previous['destination']!=leg['origin'] or departure<datetime.fromisoformat(previous['arrival_datetime']))):
            return None
        leg_duration=leg.get('duration')
        if leg_duration is not None and (isinstance(leg_duration,bool) or not isinstance(leg_duration,int)
            or leg_duration<=0 or abs(leg_duration-(arrival-departure).total_seconds()/60)>2):
            return None
        instants.append((departure,arrival))
        previous=leg
    duration=item.get('duration')
    if not isinstance(duration,int) or isinstance(duration,bool) or duration<=0:
        return None
    elapsed=(instants[-1][1]-instants[0][0]).total_seconds()/60
    if abs(duration-elapsed)>2:
        return None
    layovers=item.get('layovers')
    if layovers is not None and (not isinstance(layovers,list) or any(not isinstance(x,dict) or x.get('change_of_airport') for x in layovers)):
        return None
    if trip.get('is_domestic', True) and layovers:
        from compiler import is_indian_airport
        if any(not isinstance(x.get('airport'),str) or not is_indian_airport(x['airport']) for x in layovers):
            return None
    if layovers:
        if len(layovers)!=len(legs)-1:
            return None
        for index,layover in enumerate(layovers):
            wait=(instants[index+1][0]-instants[index][1]).total_seconds()/60
            recorded=layover.get('duration')
            if layover.get('airport')!=legs[index]['destination'] or isinstance(recorded,bool) or not isinstance(recorded,int) or abs(recorded-wait)>2:
                return None
    airline=item.get('airline') or legs[0]['airline']
    if not isinstance(airline,str) or not airline.strip():
        return None
    return dict(airline=airline,
        flight_number=legs[0]['flight_number'] if len(legs)==1 else '',
        origin=legs[0]['origin'],destination=legs[-1]['destination'],
        departure_time=instants[0][0].strftime('%H:%M'),arrival_time=instants[-1][1].strftime('%H:%M'),
        duration=f'{duration//60}h {duration%60}m',stops=item['stops'],base_price=price,price_basis='total',currency='INR',
        segments=legs,layovers=item.get('layovers'),source_transport='fli_public_page',source_revision=REVISION)


async def fetch_google(trip,timeout=20):
    process=await asyncio.create_subprocess_exec(sys.executable,str(Path(__file__).resolve()),
        stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,
        env={**os.environ,'FLI_TIMEOUT':'8','FLI_SOCS_COOKIE':'','PYTHONUTF8':'1'},
        creationflags=0x08000000 if os.name=='nt' else 0)
    try:
        async with asyncio.timeout(timeout):
            output,error=await process.communicate(json.dumps(trip).encode())
        if process.returncode:
            raise ValueError('Optional Google reader unavailable: '+error.decode(errors='replace')[-300:])
        rows=json.loads(output)
        if not isinstance(rows,list) or len(rows)>500:
            raise ValueError('Optional Google reader returned an unsupported inventory payload')
        valid=[row for item in rows if (row:=normalize_result(item,trip))]
        if not valid:
            raise ValueError('Optional Google reader returned no validated priced itineraries')
        inventory=dict(complete=False,scope='google_public_page',returned_rows=len(rows),normalized_rows=len(valid),
            rejected_rows=len(rows)-len(valid),limitation='Partial public-page inventory; missing rows are not evidence that flights do not exist.')
        for row in valid:
            row['source_inventory']=inventory
        return valid
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


def main():
    from fli.models import FlightSearchFilters
    from fli.models.google_flights.base import PassengerInfo, FlightSegment, SeatType
    from fli.models.airport import Airport
    from fli.search import SearchFlights
    from importlib.metadata import version
    if version('flights')!='0.10.0':
        raise ValueError('Install the tested version from requirements-google.txt')
    trip=json.load(sys.stdin)
    filters=FlightSearchFilters(passenger_info=PassengerInfo(adults=trip['passenger_count']),seat_type=SeatType[trip['cabin_class']],
        flight_segments=[FlightSegment(departure_airport=[[Airport[trip['origin']],0]],arrival_airport=[[Airport[trip['destination']],0]],travel_date=trip['departure_date'])])
    rows=SearchFlights().search(filters,currency='INR',language='en',country='IN') or []
    serialized=[]
    for row in rows:
        item=dict(price=row.price,currency=row.currency,duration=row.duration,stops=row.stops,
            mixed_cabin=row.mixed_cabin,self_transfer=row.self_transfer,airline=row.primary_airline_name,
            layovers=[dict(airport=x.airport.name,duration=x.duration,change_of_airport=x.change_of_airport) for x in row.layovers or []],legs=[])
        for leg in row.legs:
            item['legs'].append(dict(origin=leg.departure_airport.name,destination=leg.arrival_airport.name,
                departure_date=leg.departure_datetime.date().isoformat(),departure_datetime=leg.departure_datetime.isoformat(),
                arrival_datetime=leg.arrival_datetime.isoformat(),airline=leg_airline_label(row,leg),
                flight_number=leg.airline.name.lstrip('_')+'-'+leg.flight_number,duration=leg.duration,
                cabin_class=leg.cabin.name if leg.cabin is not None else None))
        serialized.append(item)
    print(json.dumps(serialized))


if __name__=='__main__':
    main()
