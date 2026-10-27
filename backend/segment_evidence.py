"""Check present itinerary evidence against its summary without inventing legs.

Airline names can describe a marketing or operating carrier. General name
equality is therefore not a safe identity rule; only a documented corrupt
legacy mapping is rejected here.
"""
import math
import re
from datetime import date, datetime, timedelta


def _number(value):
    return re.sub(r'[^A-Z0-9]', '', str(value or '').upper())


def segment_identity_problem(segments, *, origin, destination, departure_date,
                             departure_time, stops, flight_number=None,
                             airline=None, cabin_class=None, arrival_time=None):
    """Return a reason when supplied domestic segments contradict the summary.

    Absent legs remain allowed for corroborated nonstop DOM listings. Connecting
    itineraries require legs. Naive timestamps represent Indian local clocks;
    aware timestamps must use India's actual UTC offset.
    """
    if segments is None or segments == []:
        return None if stops == 0 else 'Connecting itinerary has no segment evidence'
    if not isinstance(segments, list) or type(stops) is not int or not 0 <= stops <= 4 or len(segments) != stops + 1:
        return 'Segment count does not match the itinerary stops'
    try:
        expected_date = date.fromisoformat(departure_date)
        previous = None
        last = None
        for index, leg in enumerate(segments):
            if not isinstance(leg, dict):
                return 'Malformed itinerary segment'
            if any(not isinstance(leg.get(key), str) or not re.fullmatch(r'[A-Z]{3}', leg[key])
                   for key in ('origin', 'destination')) or leg['origin'] == leg['destination']:
                return 'Malformed segment airport identity'
            from compiler import is_indian_airport
            if not is_indian_airport(leg['origin']) or not is_indian_airport(leg['destination']):
                return 'Domestic segment contains a non-Indian airport'
            if index == 0 and leg['origin'] != origin or index == len(segments)-1 and leg['destination'] != destination:
                return 'Segment endpoints contradict the directed route'
            number = leg.get('flight_number')
            if not isinstance(number, str) or not re.fullmatch(r'[A-Z0-9]{2,3}-?\d{1,5}', number):
                return 'Missing or malformed segment flight identity'
            if stops == 0 and _number(number) != _number(flight_number):
                return 'Segment flight identity contradicts the nonstop summary'
            # Fli's historical QP enum names a defunct unrelated carrier. The
            # visible primary label was Akasa Air; retaining the old enum in a
            # leg must not silently make that observation trustworthy.
            if number.startswith('QP') and re.sub(r'\s+', ' ', str(leg.get('airline') or '').strip()).casefold() == 'air kenya aviation':
                return 'Known corrupt QP airline label in retained segment evidence'
            if leg.get('cabin_class') is not None and cabin_class is not None and leg['cabin_class'] != cabin_class:
                return 'Segment cabin contradicts the requested cabin'
            if any(not isinstance(leg.get(key), str) or not re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}', leg[key])
                   for key in ('departure_datetime', 'arrival_datetime')):
                return 'Segment timestamp must include its full local date and time'
            departure = datetime.fromisoformat(leg['departure_datetime'])
            arrival = datetime.fromisoformat(leg['arrival_datetime'])
            if any(moment.utcoffset() not in (None, timedelta(hours=5, minutes=30)) for moment in (departure, arrival)):
                return 'Domestic segment timestamp does not use Indian local time'
            if (departure.tzinfo is None) != (arrival.tzinfo is None):
                return 'Segment mixes ambiguous and timezone-aware clocks'
            if leg.get('departure_date') is not None and date.fromisoformat(leg['departure_date']) != departure.date():
                return 'Segment date contradicts its departure timestamp'
            if index == 0 and (departure.date() != expected_date or departure.strftime('%H:%M') != departure_time):
                return 'First segment date or time contradicts the itinerary summary'
            # All legs use the same Indian clock. Normalize only the timezone
            # annotation after validating it, so naive/aware adjacent legs are
            # compared deterministically without changing their wall times.
            dep_clock, arr_clock = departure.replace(tzinfo=None), arrival.replace(tzinfo=None)
            if arr_clock <= dep_clock:
                return 'Segment arrival is not after departure'
            if previous and (previous['destination'] != leg['origin'] or dep_clock < last):
                return 'Segment chain or connection timeline is inconsistent'
            duration = leg.get('duration')
            if duration is not None and (isinstance(duration, bool) or not isinstance(duration, (int, float))
                    or not math.isfinite(duration) or duration <= 0 or abs(duration-(arr_clock-dep_clock).total_seconds()/60) > 2):
                return 'Segment duration contradicts its timestamps'
            last, previous = arr_clock, leg
        if arrival_time is not None and last.strftime('%H:%M') != arrival_time:
            return 'Last segment arrival time contradicts the itinerary summary'
    except (TypeError, ValueError, KeyError, OverflowError):
        return 'Malformed segment date or timestamp evidence'
    return None
