"""Validate evidence again when advice is produced, without inventing defaults."""
import re
import json
from datetime import datetime, timedelta, timezone
from quote_contract import positive_amount
from quotes import matches_preferences
from segment_evidence import segment_identity_problem


def quote_segment_problem(row):
    """Reject present leg contradictions before an output can vote or advise."""
    meta = row.get('savings_breakdown') or {}
    if not isinstance(meta, dict):
        return 'Malformed itinerary metadata'
    return segment_identity_problem(meta.get('segments'),
        origin=meta.get('origin'), destination=meta.get('destination'),
        departure_date=row.get('departure_date'), departure_time=row.get('departure_time'),
        stops=row.get('stops'), flight_number=row.get('flight_number'),
        airline=row.get('airline'), cabin_class=meta.get('cabin_class'),
        arrival_time=row.get('arrival_time'))


def observed_timestamp(value):
    try:
        stamp = datetime.fromisoformat(value)
        if stamp.tzinfo is None:
            return None
        return stamp.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def fresh_timestamp(value, hours=24):
    stamp = observed_timestamp(value)
    return stamp is not None and timedelta(0) <= datetime.now(timezone.utc)-stamp < timedelta(hours=hours)


def history_row_problem(row):
    """Generic accepted-row boundary for both learning and provenance exports."""
    if not isinstance(row,dict):
        return 'Malformed fare row'
    if row.get('platform') not in ('google_flights','easemytrip','cleartrip','makemytrip'):
        return 'Unsupported or mock fare source'
    if row.get('evidence_version')!=2 or row.get('quality_status') not in ('corroborated','checkout_verified'):
        return 'Unsupported evidence or unaccepted quality'
    stamp=observed_timestamp(row.get('observed_at'))
    if stamp is None or stamp>datetime.now(timezone.utc):
        return 'Missing, ambiguous or future observation timestamp'
    if not positive_amount(row.get('price')):
        return 'Invalid INR fare amount'
    if type(row.get('passenger_count')) is not int or not 1<=row['passenger_count']<=9:
        return 'Invalid adult count'
    if row.get('cabin_class') not in ('ECONOMY','PREMIUM_ECONOMY','BUSINESS','FIRST'):
        return 'Unsupported cabin'
    if not re.fullmatch(r'[A-Z]{3}-[A-Z]{3}',row.get('route') or ''):
        return 'Missing directed route'
    from compiler import is_domestic_route
    origin,destination=row['route'].split('-')
    if origin==destination or not is_domestic_route(origin,destination):
        return 'Not a directed Indian domestic route'
    try:
        from datetime import date
        date.fromisoformat(row.get('departure_date'))
        if not matches_preferences(row,{}):
            return 'Missing or invalid schedule/stops evidence'
        if 'evidence' in row:
            evidence=json.loads(row['evidence']) if isinstance(row['evidence'],str) else row['evidence']
            if not isinstance(evidence,dict) or not isinstance(evidence.get('integrity'),dict) or evidence['integrity'].get('status')!=row['quality_status']:
                return 'Missing or inconsistent stored integrity evidence'
            if evidence.get('source_learning_allowed') is False or evidence.get('source_transport')=='makemytrip_public_mcp':
                return 'Cached reference source cannot establish fare observation freshness'
            problem=segment_identity_problem(evidence.get('segments'),
                origin=origin, destination=destination,
                departure_date=row['departure_date'], departure_time=row.get('departure_time'),
                stops=row.get('stops'), flight_number=row.get('flight_number'),
                airline=row.get('airline'), cabin_class=row.get('cabin_class'))
            if problem:
                return problem
    except (TypeError,ValueError,KeyError):
        return 'Malformed date, schedule or stored evidence'
    if row.get('verification') not in ('listed','checkout'):
        return 'Unknown price comparison basis'
    return None


def accepted_history_row(row):
    return history_row_problem(row) is None


def history_rows(rows, trip, airline=None):
    """DB predicates are necessary but timestamps and specific-flight constraints matter too."""
    requested = re.sub(r'[^A-Z0-9]', '', (trip.get('specific_flight_number') or '').upper())
    result = []
    for row in rows:
        if not accepted_history_row(row):
            continue
        stamp = observed_timestamp(row.get('observed_at'))
        if stamp is None or stamp > datetime.now(timezone.utc) or not positive_amount(row.get('price')):
            continue
        if row.get('route') != trip['origin']+'-'+trip['destination'] or row.get('departure_date') != trip['departure_date']:
            continue
        if row.get('passenger_count') != trip['passenger_count'] or row.get('cabin_class') != trip['cabin_class']:
            continue
        if requested and requested != re.sub(r'[^A-Z0-9]', '', str(row.get('flight_number', '')).upper()):
            continue
        if airline and str(row.get('airline') or '').casefold() != airline.casefold():
            continue
        if row.get('verification') not in ('listed', 'checkout'):
            continue
        try:
            if not matches_preferences(row,trip):
                continue
        except (TypeError,ValueError,KeyError):
            continue
        result.append(row)
    return result


def matching_quote(row, trip, *, listing=False, direction='outbound'):
    """Only exact, accepted and fresh output rows can support buying or savings advice."""
    if not isinstance(row, dict):
        return False
    meta = row.get('savings_breakdown') or {}
    if not isinstance(meta, dict):
        return False
    if meta.get('source_learning_allowed') is False or meta.get('source_transport')=='makemytrip_public_mcp':
        return False
    if quote_segment_problem(row):
        return False
    integrity=meta.get('integrity')
    if not isinstance(integrity,dict) or integrity.get('status') not in ('corroborated', 'checkout_verified'):
        return False
    if not isinstance(row.get('platform'),str) or row['platform'] in ('','mock','synthetic'):
        return False
    if meta.get('direction', 'outbound') != direction or row.get('departure_date') != trip['departure_date']:
        return False
    if any(meta.get(k) != trip[k] for k in ('origin', 'destination', 'passenger_count', 'cabin_class')):
        return False
    stage = meta.get('verification')
    if stage not in ('listed', 'checkout') or not positive_amount(row.get('final_price')):
        return False
    stamp = (meta.get('listed_observed_at') or meta.get('observed_at')) if listing else meta.get('observed_at')
    # A payment quote is tied to a live cart; it expires with the booking session.
    lifetime = 24 if listing or stage == 'listed' else .25
    try:
        return fresh_timestamp(stamp, lifetime) and matches_preferences(row, trip)
    except (KeyError, TypeError, ValueError):
        return False
