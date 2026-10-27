"""Suggestions compare actual matching itineraries; no fabricated combined savings."""
import re
from booking_advisor import PricePredictor
from advisor_evidence import matching_quote
from quote_contract import listed_amount, listing_view


def parse_duration_to_minutes(text):
    h = re.search(r'(\d+)\s*h',text or '',re.I)
    m = re.search(r'(\d+)\s*m',text or '',re.I)
    return (int(h[1])*60 if h else 0)+(int(m[1]) if m else 0)


class SmartAdvisor:
    def __init__(self,db,predictor,user_prefs=None,brain=None):
        self.db,self.predictor=db,predictor
        self.brain=brain
        self.checkout_session_valid=None

    async def get_advisory(self,trip,flights,date_alternatives=None,search_id=None,**kwargs):
        relevant=[f for f in flights if matching_quote(f,trip)]
        # A stored receipt does not establish that its mutable cart is still open.
        # Keep its original listing eligible only under the listing evidence gate.
        current=[]
        for row in relevant:
            if row['savings_breakdown'].get('verification')=='checkout':
                if not self.checkout_session_valid or self.checkout_session_valid(row) is not True:
                    view=listing_view(row)
                    if view and matching_quote(view,trip,listing=True):
                        current.append(view)
                    continue
            current.append(row)
        relevant=current
        financial=kwargs.get('financial') or {}
        if financial:
            from deal_feedback import available_result
            offers=[]
            if self.db:
                for platform in {row['platform'] for row in relevant}:
                    offers.extend(await self.db.get_live_coupons(platform))
            relevant=[row for row in relevant if available_result(row,financial,offers)]
        verified=[f for f in relevant if f.get('savings_breakdown',{}).get('verification')=='checkout']
        pool=verified or relevant
        suggestions=[]
        direct=[f for f in pool if f.get('stops')==0]
        stops=[f for f in pool if f.get('stops',0)>0]
        if direct and stops:
            a,b=min(direct,key=lambda f:f['final_price']),min(stops,key=lambda f:f['final_price'])
            saving=a['final_price']-b['final_price']
            if saving>0:
                ad,bd=parse_duration_to_minutes(a.get('duration')),parse_duration_to_minutes(b.get('duration'))
                duration_note=f'Adds about {max(0,bd-ad)} minutes.' if ad and bd else 'Duration difference is unavailable.'
                suggestions.append(dict(type='LAYOVER',title='Consider a flight with a stop',saving=saving,
                    net_saving=saving if verified else None,flight_id=b['id'],detail=f'Saves ₹{saving:,.0f} versus the cheapest nonstop on the same date. {duration_note} '+('Both totals verified for their selected payment choices.' if verified else 'Listed fares; checkout fees need verification.')))
        for alt in date_alternatives or []:
            alternative,reference=alt.get('quote'),alt.get('reference_quote')
            if not isinstance(alt.get('date'),str) or not matching_quote(alternative,{**trip,'departure_date':alt['date']},listing=True) or not matching_quote(reference,trip,listing=True):
                continue
            a,b=listed_amount(reference),listed_amount(alternative)
            if a is not None and b is not None and a>b:
                suggestions.append(dict(type='DATE_SHIFT',title=f"Travel on {alt['date']}",date=alt['date'],
                    saving=a-b,net_saving=None,detail='Matching accepted listed fares; search this date to verify platform fees and coupons.'))
        prediction=await self.predictor.predict(trip['origin'],trip['destination'],trip['departure_date'],
            passenger_count=trip['passenger_count'],cabin_class=trip['cabin_class'],preferred_time=trip.get('preferred_time','ANY'),max_stops=trip.get('max_stops'))
        decision=prediction['decision']
        report=await self.brain.assess(trip,kwargs.get('financial'),current_quotes=relevant) if self.brain else None
        advice=report['reasoning'] if report else decision['reasoning']
        if trip.get('trip_type')=='round_trip':
            inbound_trip={**trip,'origin':trip['destination'],'destination':trip['origin'],'departure_date':trip.get('return_date'),
                          'preferred_time':'ANY','specific_flight_number':None}
            inbound=[f for f in flights if matching_quote(f,inbound_trip,listing=True,direction='inbound')]
            if pool and inbound:
                # Both legs share one comparison basis. A checkout on one leg
                # cannot silently be summed with an unverified return listing.
                out=[v for f in relevant if matching_quote(f,trip,listing=True) and (v:=listing_view(f))]
                back=[v for f in inbound if (v:=listing_view(f))]
                if out and back:
                    total=min(f['final_price'] for f in out)+min(f['final_price'] for f in back)
                    advice+=f' Cheapest separate outbound and return listed fares total ₹{total:,.0f}. Each leg is a separate booking; verify both fees and coupons before paying.'
        return dict(route=prediction['route'],travel_date=trip['departure_date'],verdict=report['signal'] if report else decision['signal'],
            brain=report,urgency=report.get('urgency',decision['urgency']) if report else decision['urgency'],
            confidence=report.get('confidence') if report else decision['confidence'],
            recommended_book_by=report.get('recommended_book_by') if report else decision['recommended_book_by'],
            potential_savings=0,advice=advice,scenarios=[],suggestions=suggestions)
