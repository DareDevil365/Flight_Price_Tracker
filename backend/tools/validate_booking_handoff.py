"""Test app booking handoff and fail-closed verification without traveller/payment data."""
import argparse
import asyncio
import json
from pathlib import Path
import websockets
from validate_live_routes import run_case


async def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('platform',choices=['cleartrip','easemytrip'])
    parser.add_argument('--route',required=True)
    parser.add_argument('--date',required=True)
    parser.add_argument('--url',default='ws://127.0.0.1:8765/ws')
    args=parser.parse_args()
    origin,destination=args.route.split('-')
    trip=dict(origin=origin,destination=destination,departureDate=args.date,
        passengerCount=1,cabinClass='ECONOMY',tripType='one_way',preferredTime='ANY',maxStops=None)
    report={}
    async with websockets.connect(args.url,origin='http://127.0.0.1:5173',max_size=8_000_000) as ws:
        search=await run_case(ws,trip,[args.platform])
        if not search['results']:
            raise ValueError('No public listing available for a booking-handoff check')
        chosen=min(search['results'],key=lambda row:row['final_price'])
        await ws.send(json.dumps(dict(type='session:prepare',payload=dict(searchId=search['search_id'],resultId=chosen['id']))))
        async with asyncio.timeout(110):
            while True:
                event=json.loads(await ws.recv());kind=event['type'];p=event.get('payload',{})
                if kind=='search:results' and p.get('id')==chosen['id']:
                    chosen=p
                if kind=='session:verify:ack' and p.get('status')=='failed':
                    report['prepare_error']=p.get('message');break
                if kind=='session:handoff:ack' and p.get('sessionId')==chosen.get('session_id'):
                    report['handoff']=p;break
        if chosen.get('session_id'):
            await ws.send(json.dumps(dict(type='session:verify',payload=dict(sessionId=chosen['session_id']))))
            async with asyncio.timeout(40):
                while True:
                    event=json.loads(await ws.recv());p=event.get('payload',{})
                    if event['type']=='session:verify:ack' and p.get('sessionId')==chosen['session_id']:
                        report['verification']=p;break
            # With no traveller/payment entry this flow must never publish a
            # verified payment price, whether it is review, consent or refusal.
            assert report['verification']['status']=='failed',report
            await ws.send(json.dumps(dict(type='session:check',payload=dict(sessionId=chosen['session_id']))))
            async with asyncio.timeout(10):
                while True:
                    event=json.loads(await ws.recv())
                    if event['type']=='session:status' and event['payload'].get('sessionId')==chosen['session_id']:
                        report['session_after_failure']=event['payload'];break
        report.update(trip=trip,platform=args.platform,quote=chosen)
        assert chosen['savings_breakdown']['verification']=='listed'
        folder=Path(__file__).resolve().parents[2]/'sessions'/'booking-handoff'
        folder.mkdir(parents=True,exist_ok=True)
        (folder/(args.platform+'.json')).write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps({**{k:v for k,v in report.items() if k!='quote'},
            'booking_problem':chosen['savings_breakdown'].get('booking_problem')},indent=2),flush=True)


if __name__=='__main__':asyncio.run(main())
