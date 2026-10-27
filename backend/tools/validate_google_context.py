"""Exercise real search -> optional Google guidance -> handoff over the app API."""
import asyncio
import json
from pathlib import Path
import websockets
from validate_live_routes import run_case


async def main():
    reports = []
    async with websockets.connect('ws://127.0.0.1:8765/ws', origin='http://127.0.0.1:5173', max_size=8_000_000) as ws:
        for origin, destination, day, adults in [('BOM','HYD','2026-11-19',1),('PNQ','HYD','2027-02-19',2)]:
            case = dict(origin=origin,destination=destination,departureDate=day,passengerCount=adults,
                        cabinClass='ECONOMY',tripType='one_way',preferredTime='ANY',maxStops=0)
            search = await run_case(ws, case, ['google_flights','easemytrip','cleartrip'])
            rows = [r for r in search['results'] if r['platform']=='google_flights' and r['savings_breakdown'].get('integrity',{}).get('status')!='flagged']
            if not rows:
                reports.append(dict(trip=case,status='no_google_quote',failures=search['failures']))
                continue
            row = min(rows,key=lambda r:r['final_price'])
            await ws.send(json.dumps(dict(type='search:booking-context:get',payload=dict(searchId=search['search_id'],resultId=row['id']))))
            async with asyncio.timeout(90):
                while True:
                    event = json.loads(await ws.recv())
                    if event['type']=='search:booking-context' and event['payload'].get('resultId')==row['id']:
                        context=event['payload']
                        break
            report = dict(trip=case,listed_price=row['final_price'],context=context,brain=search['suggestions'].get('brain'))
            if context['status']=='available':
                assert context['scope']['origin']==origin and context['scope']['destination']==destination
                assert context['scope']['departure_date']==day and context['scope']['passenger_count']==adults
                assert not context['insight'] or context['insight']['certainty_percent'] is None
                assert all(option['verification']=='google_partner_listing' for option in context['booking_options'])
                await ws.send(json.dumps(dict(type='session:handoff',payload=dict(sessionId=context['sessionId']))))
                async with asyncio.timeout(12):
                    while True:
                        event=json.loads(await ws.recv())
                        if event['type']=='session:handoff:ack' and event['payload'].get('sessionId')==context['sessionId']:
                            report['handoff']=event['payload']
                            break
                # A guidance-only session must never masquerade as a verified cart.
                await ws.send(json.dumps(dict(type='session:verify',payload=dict(sessionId=context['sessionId']))))
                async with asyncio.timeout(12):
                    while True:
                        event=json.loads(await ws.recv())
                        if event['type']=='session:verify:ack':
                            report['verification_rejection']=event['payload']
                            assert event['payload']['status']=='failed'
                            break
            reports.append(report)
            folder=Path(__file__).resolve().parents[2]/'sessions'/'new-approaches'
            folder.mkdir(parents=True,exist_ok=True)
            (folder/'app-google-guidance.json').write_text(json.dumps(reports,indent=2),encoding='utf-8')
            print(json.dumps(dict(trip=case,context_status=context['status'],insight=context.get('insight'),options=context.get('booking_options'),handoff=report.get('handoff'),error=context.get('message')),ensure_ascii=True),flush=True)


if __name__=='__main__':
    asyncio.run(main())
