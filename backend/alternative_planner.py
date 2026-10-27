"""Compare fresh quotes. Separate tickets require conservative transfer buffers."""
from datetime import date, datetime, timedelta, timezone
from travel_advisor import parse_duration_to_minutes
from quote_contract import listing_view
from quote_contract import positive_amount
from advisor_evidence import matching_quote


def departure_at(row):
    return datetime.fromisoformat(row['departure_date']+'T'+row['departure_time'])


def connection_candidates(first,second,reference_price,min_transfer_minutes=240,max_stops=None):
    candidates=[]
    if not positive_amount(reference_price) or not isinstance(min_transfer_minutes,(int,float)) or isinstance(min_transfer_minutes,bool) or not 0<min_transfer_minutes<=720:
        return candidates
    for a in first:
        for b in second:
            a,b=listing_view(a),listing_view(b)
            if not a or not b:
                continue
            am,bm=a['savings_breakdown'],b['savings_breakdown']
            if am['destination']!=bm['origin']:
                continue
            if (am['passenger_count'],am['cabin_class'])!=(bm['passenger_count'],bm['cabin_class']):
                continue
            total_stops=a.get('stops',0)+b.get('stops',0)+1
            if max_stops is not None and total_stops>max_stops:
                continue
            duration=parse_duration_to_minutes(a.get('duration'))
            if not duration:
                continue
            try:
                arrival=departure_at(a)+timedelta(minutes=duration)
                second_duration=parse_duration_to_minutes(b.get('duration'))
                if not second_duration or (departure_at(b)+timedelta(minutes=second_duration)).strftime('%H:%M')!=b.get('arrival_time'):
                    continue
            except (TypeError,ValueError,KeyError,OverflowError):
                continue
            # Domestic routes share a timezone. Reject contradictory duration/time evidence.
            if arrival.strftime('%H:%M')!=a.get('arrival_time'):
                continue
            wait=int((departure_at(b)-arrival).total_seconds()/60)
            same_terminal=bool(a.get('arrival_terminal') and b.get('departure_terminal') and a['arrival_terminal']==b['departure_terminal'])
            different_terminal=bool(a.get('arrival_terminal') and b.get('departure_terminal') and a['arrival_terminal']!=b['departure_terminal'])
            minimum=max(min_transfer_minutes,300 if different_terminal else 240)
            if not minimum<=wait<=720:
                continue
            total=a['final_price']+b['final_price']
            if total>=reference_price:
                continue
            candidates.append(dict(type='SELF_TRANSFER',title='Separate tickets via '+am['destination'],
                saving=round(reference_price-total,2),net_saving=None,listed_total=total,
                connection_minutes=wait,same_airport=True,airport=am['destination'],
                terminal_status='same' if same_terminal else 'different' if different_terminal else 'unknown',
                total_stops=total_stops,comparison_basis='listed',fees_verified=False,
                legs=[a,b],detail=f'Listed fares save INR {reference_price-total:,.0f} before two sets of booking fees and any baggage charges. Connection is {wait//60}h {wait%60}m at {am["destination"]}. Terminals '+('match.' if same_terminal else 'differ.' if different_terminal else 'are not published in these quotes; confirm both.')+' Separate tickets have no guaranteed missed-connection protection. Recheck baggage, check-in deadlines and transit requirements before booking.'))
    return sorted(candidates,key=lambda c:c['listed_total'])[:3]


class AlternativePlanner:
    def __init__(self,dispatcher):
        self.engine=dispatcher
        self._cache={}

    async def explore(self,search_id,transfer_budget=2000,hubs=None):
        import asyncio
        import math
        task=self.engine._search_tasks.get(search_id)
        if not task:
            raise ValueError('Run a fresh search before exploring alternatives')
        if not isinstance(transfer_budget,(int,float)) or not math.isfinite(transfer_budget) or transfer_budget<0:
            raise ValueError('Ground transfer estimate must be a finite nonnegative INR amount')
        trip=task['trip']
        if not trip['is_domestic'] or trip['trip_type']!='one_way':
            raise ValueError('Alternative exploration currently supports domestic one-way trips')
        hubs=list(dict.fromkeys(hubs or ['BOM','AMD']))[:2]
        if any(h not in {'BOM','AMD','DEL','HYD','BLR'} for h in hubs):
            raise ValueError('Supported connection airports: BOM, AMD, DEL, HYD, BLR')
        hubs=[h for h in hubs if h not in (trip['origin'],trip['destination'])]
        if trip.get('max_stops') == 0:
            hubs=[]
        if trip.get('specific_flight_number'):
            hubs=[]
        rows=await self.engine.db.get_search_results(search_id)
        rows=[r for r in rows if matching_quote(r,trip,listing=True)]
        if not rows:
            raise ValueError('The original trip has no comparable quotes')
        def recent_listing(row):
            meta=row['savings_breakdown']
            try:
                age=datetime.now(timezone.utc)-datetime.fromisoformat(meta.get('listed_observed_at') or meta.get('observed_at',''))
                return timedelta(0)<=age<timedelta(minutes=20)
            except (ValueError,TypeError):
                return False
        rows=[row for row in rows if recent_listing(row)]
        if not rows:
            raise ValueError('The original listing is older than twenty minutes. Refresh it before comparing alternatives.')
        # A verified payment total must never be compared to unverified alternatives as certain savings.
        listed=[view for row in rows if (view:=listing_view(row))]
        if not listed:
            raise ValueError('The original listing was not preserved. Run a fresh search before comparing listed alternatives.')
        reference=min(r['final_price'] for r in listed)
        self.engine.emit_log(search_id,'planner','info','Searching adjacent dates, nearby airports and up to two self-transfer hubs. Every alternative remains separately labelled.')
        self._cache={k:v for k,v in self._cache.items() if datetime.now()-v[0]<timedelta(minutes=20)}
        targets=[]
        day=date.fromisoformat(trip['departure_date'])
        for offset in (-1,1):
            if day+timedelta(days=offset)>=date.today():
                targets.append((trip['origin'],trip['destination'],(day+timedelta(days=offset)).isoformat()))
        alternatives={'GOI':'GOX','GOX':'GOI'}
        for field in ('origin','destination'):
            if trip[field] in alternatives:
                targets.append((alternatives[trip['origin']] if field=='origin' else trip['origin'],
                    alternatives[trip['destination']] if field=='destination' else trip['destination'],day.isoformat()))
        for hub in hubs:
            targets.extend([(trip['origin'],hub,day.isoformat()),(hub,trip['destination'],day.isoformat()),
                (hub,trip['destination'],(day+timedelta(days=1)).isoformat())])
        found={}
        limit=asyncio.Semaphore(2)
        async def gather_route(origin,destination,departure):
            # Journey-start preferences apply only to its first leg. Whole-journey
            # stops are checked after combining legs; each leg consumes a stop.
            second_leg=origin in hubs and destination==trip['destination']
            leg_time='ANY' if second_leg else trip.get('preferred_time','ANY')
            leg_stops=trip.get('max_stops')
            if leg_stops is not None and (origin in hubs or destination in hubs):
                leg_stops=max(0,leg_stops-1)
            key=(origin,destination,departure,trip['passenger_count'],trip['cabin_class'],leg_time,leg_stops)
            cached=self._cache.get(key)
            if cached and datetime.now()-cached[0]<timedelta(minutes=20):
                found[(origin,destination,departure)]=cached[1]
                return
            import uuid
            sid=str(uuid.uuid4())
            child={**task,'search_id':sid,'background':True,'trip':{**trip,'origin':origin,'destination':destination,'departure_date':departure,'nearby_dates_range':0,'preferred_time':leg_time,'max_stops':leg_stops},
                'financial':{**task['financial'],'max_final_price':None}}
            await self.engine.db.save_search(dict(search_id=sid,origin=origin,destination=destination,departure_date=departure,
                return_date=None,passenger_count=trip['passenger_count'],cabin_class=trip['cabin_class'],platforms=['google_flights','easemytrip']))
            await asyncio.gather(*(self.engine._run_platform(p,child,limit) for p in ('google_flights','easemytrip')))
            results=await self.engine.apply_integrity(sid,child['trip'])
            results=[view for r in results if matching_quote(r,child['trip'],listing=True) and (view:=listing_view(r))]
            found[(origin,destination,departure)]=results
            self._cache[key]=(datetime.now(),results)
            if len(self._cache)>100:
                self._cache.pop(next(iter(self._cache)))
            await self.engine.db.db.execute('UPDATE searches SET status=?,completed_at=? WHERE id=?',('completed' if results else 'failed',datetime.now().isoformat(),sid))
            await self.engine.db.db.commit()
        await asyncio.gather(*(gather_route(*target) for target in dict.fromkeys(targets)))
        suggestions=[]
        for (origin,destination,departure),options in found.items():
            if not options:
                continue
            best=min(options,key=lambda r:r['final_price'])
            if origin==trip['origin'] and destination==trip['destination']:
                saving=reference-best['final_price']
                if saving>0:
                    suggestions.append(dict(type='DATE_SHIFT',title='Travel on '+departure,date=departure,saving=saving,net_saving=None,comparison_basis='listed',fees_verified=False,
                        detail=f'Listed fare INR {best["final_price"]:,.0f} saves INR {saving:,.0f}. Refresh this date and verify its own fees and coupon eligibility.',quote=best))
            elif (origin==trip['origin'] and destination==alternatives.get(trip['destination'])) or (destination==trip['destination'] and origin==alternatives.get(trip['origin'])):
                saving=reference-best['final_price'];net=saving-transfer_budget
                suggestions.append(dict(type='AIRPORT_ALT',title=f'Compare {origin}-{destination}',saving=saving,net_saving=net,comparison_basis='listed_plus_entered_ground_estimate',fees_verified=False,
                    recommended=net>0,ground_cost_estimate=transfer_budget,distance_km=None,quote=best,
                    detail=f'Listed fare difference INR {saving:,.0f}; after your INR {transfer_budget:,.0f} ground-transfer estimate, net difference is INR {net:,.0f}. '+('Potential saving.' if net>0 else 'This transfer estimate outweighs the airfare saving.')+' GOI and GOX are different airports. Road distance/time and cab fare to your actual destination need confirmation; fees remain unverified.'))
        for hub in hubs:
            first=found.get((trip['origin'],hub,day.isoformat()),[])
            second=found.get((hub,trip['destination'],day.isoformat()),[])+found.get((hub,trip['destination'],(day+timedelta(days=1)).isoformat()),[])
            suggestions.extend(connection_candidates(first,second,reference,max_stops=trip.get('max_stops')))
        return suggestions
