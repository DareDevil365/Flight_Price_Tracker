"""Read-only running-app contract audit. No fake fares, booking or saved monitors.

Run after start.ps1. It checks actual WebSocket replies and directional history;
live merchant searches remain in validate_live_routes.py. Only derived counts,
pass/fail details and timing are written, never page or account contents.
"""
import argparse
import asyncio
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import time
import uuid

import websockets


async def audit(url):
    checks=[]
    async with websockets.connect(url,origin='http://127.0.0.1:5173',max_size=8_000_000) as ws:
        async def request(kind,payload,reply,validate,timeout=20):
            started=time.monotonic()
            try:
                await ws.send(json.dumps({'type':kind,'payload':payload}))
                async with asyncio.timeout(timeout):
                    while True:
                        event=json.loads(await ws.recv())
                        data=event.get('payload')
                        if event.get('type')=='error' and isinstance(data,dict) and data.get('originalType')==kind:
                            raise ValueError(data.get('message','Request rejected'))
                        if event.get('type')!=reply:
                            continue
                        if payload.get('requestId') and (not isinstance(data,dict) or data.get('requestId')!=payload['requestId']):
                            continue
                        detail=validate(data)
                        checks.append(dict(request=kind,status='passed',detail=detail,seconds=round(time.monotonic()-started,2)))
                        return
            except Exception as exc:
                checks.append(dict(request=kind,status='failed',error=str(exc) or type(exc).__name__,seconds=round(time.monotonic()-started,2)))

        def array(data):
            if not isinstance(data,list):raise ValueError('Expected a list')
            return {'count':len(data)}
        def items(data):return array(data['items'])
        def coupons(data):
            rows=data['coupons'];runs=data['trackRecord']
            if not isinstance(rows,list) or not isinstance(runs,list):raise ValueError('Missing coupon candidates or trial history')
            if any(not isinstance(r.get('trials'),list) for r in runs):raise ValueError('Missing scoped coupon trials')
            return {'candidates':len(rows),'runs':len(runs),'trials':sum(len(r['trials']) for r in runs)}

        await request('platform:list',{},'platform:list:data',array)
        await request('search:history:get',{},'search:history:data',array)
        await request('redroom:list',{},'redroom:data',items)
        await request('watchlist:list',{},'watchlist:data',items)
        await request('notifications:get',{},'notifications:data',items)
        for platform in ('easemytrip','cleartrip','makemytrip'):
            await request('coupon:list',{'platform':platform},'coupon:list:result',coupons)
        day=(date.today()+timedelta(days=43)).isoformat()
        for route in ('BOM-HYD','HYD-BOM'):
            payload=dict(route=route,date=day,passengerCount=1,cabinClass='ECONOMY',requestId=str(uuid.uuid4()))
            def history(data,route=route):
                rows=data['history']
                if data['route']!=route or any(r['route']!=route or r['departure_date']!=day or r['passenger_count']!=1 or r['cabin_class']!='ECONOMY' for r in rows):
                    raise ValueError('History scope mismatch')
                return {'route':route,'rows':len(rows)}
            await request('history:get',payload,'history:data',history)
        # An invalid target must fail explicitly rather than start fetching feeds
        # and leave the advice screen pending. This request changes no data.
        payload=dict(route='BOM-HYD',date=day,targetPrice=-1,requestId=str(uuid.uuid4()))
        def explicit_error(data):
            if not data.get('message'):raise ValueError('Missing advice failure explanation')
            return {'explicit_failure':True}
        await request('brain:get',payload,'brain:error',explicit_error)
    return {'checked_at':datetime.now(timezone.utc).isoformat(),
        'checks':checks,'passed':all(c['status']=='passed' for c in checks),
        'scope':'Application response contracts only; not merchant availability, final fees or coupon success.'}


async def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',default='ws://127.0.0.1:8765/ws')
    parser.add_argument('--output',type=Path,default=Path(__file__).resolve().parents[2]/'sessions'/'validation'/'runtime-audit.json')
    args=parser.parse_args()
    result=await audit(args.url)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))
    raise SystemExit(0 if result['passed'] else 1)


if __name__=='__main__':asyncio.run(main())
