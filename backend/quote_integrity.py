"""Reject malformed output and quarantine unexplained comparable-fare disagreements.

Low fares are not inherently wrong. Cross-source checks use exact trip identity,
never a fixed price floor or the reversed route. Single-source quotes remain
visible as uncorroborated observations, but cannot train the booking brain.
"""
import math
import re
from datetime import datetime, timezone, timedelta
from statistics import median
from quotes import matches_preferences
from advisor_evidence import quote_segment_problem


def number(value):
    return re.sub('[^A-Z0-9]','',str(value or '').upper())


def same_itinerary(a,b):
    am,bm=a.get('savings_breakdown',{}),b.get('savings_breakdown',{})
    fields=('origin','destination','passenger_count','cabin_class','direction')
    if any(am.get(k)!=bm.get(k) for k in fields):
        return False
    if any(a.get(k)!=b.get(k) for k in ('departure_date','departure_time','arrival_time','stops')):
        return False
    if number(a.get('airline'))!=number(b.get('airline')):
        return False
    an,bn=number(a.get('flight_number')),number(b.get('flight_number'))
    # Missing identity cannot vote as the same flight. Schedule similarity alone
    # is useful to display candidates, not enough to teach the prediction model.
    if a.get('stops',0)==0 and (not an or not bn or an!=bn):
        return False
    for key in ('fare_family','baggage'):
        av,bv=am.get(key),bm.get(key)
        if (av is not None or bv is not None) and av!=bv:
            return False
    if a.get('stops',0)>0:
        aseg,bseg=am.get('segments'),bm.get('segments')
        if not aseg or not bseg:
            return False
        keys=('origin','destination','flight_number','departure_datetime','arrival_datetime')
        if len(aseg)!=a['stops']+1 or any(not s.get(k) for s in aseg+bseg for k in keys):
            return False
        if [[s.get(k) for k in keys] for s in aseg]!=[[s.get(k) for k in keys] for s in bseg]:
            return False
    return True


def check_outputs(rows,trip):
    """Returns quality/reasons per ID. Google is a comparator, not infallible."""
    outcomes={}
    valid=[]
    for row in rows:
        meta=row.get('savings_breakdown',{})
        reasons=[]
        inbound=meta.get('direction')=='inbound'
        expected_origin=trip['destination'] if inbound else trip['origin']
        expected_destination=trip['origin'] if inbound else trip['destination']
        expected_day=trip.get('return_date') if inbound else trip['departure_date']
        if (meta.get('origin'),meta.get('destination'),row.get('departure_date'))!=(expected_origin,expected_destination,expected_day):
            reasons.append('Output does not match the requested directed route and departure date')
        if (meta.get('passenger_count'),meta.get('cabin_class'))!=(trip['passenger_count'],trip['cabin_class']):
            reasons.append('Passenger count or cabin differs from the request')
        if meta.get('currency')!='INR':
            reasons.append('Currency was not confirmed as INR')
        if not matches_preferences(row,trip):
            reasons.append('Stop count or departure time does not match the request')
        # Missing connecting evidence stays visible but cannot corroborate.
        # Present contradictory evidence is a flag, rather than just missing data.
        segment_problem=quote_segment_problem(row) if meta.get('segments') is not None and meta.get('segments') != [] else None
        if segment_problem:
            reasons.append(segment_problem)
        price=row.get('final_price')
        if isinstance(price,bool) or not isinstance(price,(int,float)) or not math.isfinite(price) or price<=0:
            reasons.append('Price is not a positive finite amount')
        if row.get('platform')=='mock':
            reasons.append('Demo output cannot be used in a live search')
        try:
            age=datetime.now(timezone.utc)-datetime.fromisoformat(meta.get('observed_at',''))
            if age < -timedelta(minutes=5) or age>timedelta(hours=24):
                reasons.append('Observation time is stale or in the future')
        except (ValueError,TypeError):
            reasons.append('Observation time is missing or invalid')
        if reasons:
            outcomes[row['id']]=dict(status='flagged',reasons=reasons,compared_sources=[])
        elif meta.get('source_learning_allowed') is False or meta.get('source_transport')=='makemytrip_public_mcp':
            outcomes[row['id']]=dict(status='uncorroborated',reasons=[
                'MakeMyTrip AI reference may be cached; cache age and payment fees are unknown. Excluded from source corroboration and model learning.'],compared_sources=[])
        else:
            valid.append(row)
    for row in valid:
        if row['savings_breakdown'].get('verification')=='checkout':
            outcomes[row['id']]=dict(status='checkout_verified',reasons=['Selected itinerary and payment total were verified by the checkout reader'],compared_sources=[])
            continue
        peers=[r for r in valid if r['platform']!=row['platform'] and r['savings_breakdown'].get('verification')=='listed' and same_itinerary(row,r)]
        # One cheapest comparable listing per independent website; duplicates do not vote.
        prices={}
        for peer in peers:
            prices[peer['platform']]=min(prices.get(peer['platform'],math.inf),peer['final_price'])
        sources=list(prices)
        if not prices:
            outcomes[row['id']]=dict(status='uncorroborated',reasons=['No second website returned this exact itinerary. Excluded from model learning until corroborated or checkout-verified.'],compared_sources=[])
            continue
        center=median(prices.values())
        close=[p for p in prices.values() if abs(row['final_price']-p)<=max(100,min(row['final_price'],p)*.05)]
        if close:
            outcomes[row['id']]=dict(status='corroborated',reasons=['A second source lists a comparable fare; checkout charges and fare conditions may still differ'],compared_sources=sources)
        elif row['final_price']<center*.6 or row['final_price']>center*1.8:
            outcomes[row['id']]=dict(status='flagged',reasons=[f'Unexplained fare disagreement for the same itinerary: this source INR {row["final_price"]:,.0f}; comparable sources around INR {center:,.0f}. Recheck before using this result.'],compared_sources=sources)
        else:
            outcomes[row['id']]=dict(status='uncorroborated',reasons=['Comparable websites disagree; no close fare match. Excluded from model learning.'],compared_sources=sources)
    return outcomes
