"""Exercise the running app on public flight searches; no passenger or payment data."""
import argparse
import asyncio
import json
import time
from pathlib import Path
from datetime import date, timedelta
import websockets

async def run_case(ws, case, sites=None):
    payload = dict(trip=case,platforms=sites or ['google_flights','easemytrip','cleartrip','makemytrip'],
        cloak=dict(maxConcurrentBots=3,showBrowser=False),financial={})
    started=time.monotonic()
    await ws.send(json.dumps({'type':'search:start','payload':payload}))
    search_id=None
    quotes={}
    failures={}
    suggestions={}
    async with asyncio.timeout(300):
        while True:
            event=json.loads(await ws.recv())
            kind,p=event['type'],event.get('payload',{})
            if kind=='search:started': search_id=p['searchId']
            if kind=='error': raise RuntimeError(p)
            if not search_id or p.get('searchId',p.get('search_id'))!=search_id: continue
            if kind=='search:results': quotes[p['id']]=p
            if kind=='bot:status' and p.get('phase')=='failed': failures[p['platform']]=p.get('error')
            if kind=='search:suggestions': suggestions=p
            if kind in ('search:completed','search:failed','search:cancelled'): break
    rows=list(quotes.values())
    assert all(r['final_price']>0 and r['departure_date'] in (case['departureDate'],case.get('returnDate')) for r in rows)
    usable=[r for r in rows if r['savings_breakdown'].get('integrity',{}).get('status') in ('corroborated','checkout_verified')]
    quality={k:sum(r['savings_breakdown'].get('integrity',{}).get('status')==k for r in rows) for k in ('corroborated','uncorroborated','flagged')}
    report=dict(quality=quality,trip=case,search_id=search_id,status=kind,seconds=round(time.monotonic()-started,2),
        counts={site:sum(r['platform']==site for r in rows) for site in payload['platforms']},failures=failures,
        cheapest=min(usable,key=lambda r:r['final_price']) if usable else None,results=rows,suggestions=suggestions)
    print(json.dumps({k:v for k,v in report.items() if k not in ('results','cheapest','suggestions')}),flush=True)
    if report['cheapest']:
        best=report['cheapest']; print(f"Cheapest listed: {best['platform']} INR {best['final_price']} {best['airline']} {best['departure_time']}",flush=True)
    return report

async def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--label',default='baseline')
    parser.add_argument('--url',default='ws://127.0.0.1:8765/ws',help='Local application WebSocket endpoint')
    parser.add_argument('--route',help='Optional single route, such as GOI-HYD')
    parser.add_argument('--date',help='Exact YYYY-MM-DD for a single route')
    parser.add_argument('--fresh-matrix',action='store_true',help='New routes at one/four months, including a directed reverse pair')
    parser.add_argument('--adults',type=int,default=1)
    parser.add_argument('--cabin',default='ECONOMY')
    parser.add_argument('--return-days',type=int,default=0)
    parser.add_argument('--nearby-days',type=int,default=0)
    parser.add_argument('--time',default='ANY')
    parser.add_argument('--max-stops',type=int,default=None)
    parser.add_argument('--sites',default='google_flights,easemytrip,cleartrip,makemytrip')
    args=parser.parse_args()
    today=date.today()
    routes=[('GOI','HYD',35),('DEL','MAA',41),('GOX','JAI',58)]
    if args.fresh_matrix:
        import calendar
        def month_offset(months,extra=0):
            index=today.month-1+months
            day=date(today.year+index//12,index%12+1,min(today.day,calendar.monthrange(today.year+index//12,index%12+1)[1]))+timedelta(days=extra)
            return (day-today).days
        routes=[('JAI','BLR',month_offset(1)),('BOM','HYD',month_offset(1,7)),
            ('HYD','BOM',month_offset(4)),('MAA','DEL',month_offset(4,10)),
            ('PNQ','GOX',month_offset(1,14)),('BLR','JAI',month_offset(4,4))]
    if args.route:
        origin,destination=args.route.split('-');routes=[(origin,destination,(date.fromisoformat(args.date)-today).days if args.date else 35)]
    reports=[]
    folder=Path(__file__).resolve().parents[2]/'sessions'/'validation'
    folder.mkdir(parents=True,exist_ok=True)
    async with websockets.connect(args.url,origin='http://127.0.0.1:5173',max_size=8_000_000) as ws:
        for origin,destination,offset in routes:
            case=dict(origin=origin,destination=destination,departureDate=(today+timedelta(days=offset)).isoformat(),
                passengerCount=args.adults,cabinClass=args.cabin,tripType='round_trip' if args.return_days else 'one_way',
                preferredTime=args.time,maxStops=args.max_stops,nearbyDatesRange=args.nearby_days)
            if args.return_days:
                case['returnDate']=(today+timedelta(days=offset+args.return_days)).isoformat()
            reports.append(await run_case(ws,case,args.sites.split(',')))
            (folder/f'{args.label}.json').write_text(json.dumps(reports,indent=2),encoding='utf-8')

if __name__=='__main__': asyncio.run(main())
