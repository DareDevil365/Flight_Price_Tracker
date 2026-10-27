"""Return a trip-scoped report or an explicit failure for asynchronous requests."""
import asyncio
import json
from quote_contract import positive_amount


async def deliver_report(ws, context, brain, trip, payload, timeout_seconds=90):
    try:
        if payload.get('targetPrice') is not None and not positive_amount(payload['targetPrice']):
            raise ValueError('Target price must be a finite positive INR amount')
        if 'refreshFeeds' in payload and type(payload['refreshFeeds']) is not bool:
            raise ValueError('refreshFeeds must be true or false')
        async with asyncio.timeout(timeout_seconds):
            await context.refresh(force=bool(payload.get('refreshFeeds')))
            report=await brain.assess(trip,target_price=payload.get('targetPrice'))
            report['requestId']=payload.get('requestId')
            await ws.send_text(json.dumps(dict(type='brain:data',payload=report)))
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        await ws.send_text(json.dumps(dict(type='brain:error',payload=dict(
            requestId=payload.get('requestId'),
            originalType='brain:get',
            message='Booking advice could not be produced: '+('request timed out' if isinstance(exc,TimeoutError) else str(exc))
        ))))
