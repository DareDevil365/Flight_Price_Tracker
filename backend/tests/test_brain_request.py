import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from brain_request import deliver_report


@pytest.mark.asyncio
async def test_success_and_failure_keep_request_identity():
    ws=SimpleNamespace(send_text=AsyncMock())
    context=SimpleNamespace(refresh=AsyncMock())
    brain=SimpleNamespace(assess=AsyncMock(return_value={'signal':'MONITOR'}))
    await deliver_report(ws,context,brain,{},dict(requestId='exact-trip',targetPrice=5000))
    event=json.loads(ws.send_text.await_args.args[0])
    assert event['type']=='brain:data' and event['payload']['requestId']=='exact-trip'
    brain.assess=AsyncMock(side_effect=ValueError('invalid target'))
    await deliver_report(ws,context,brain,{},dict(requestId='other-trip'))
    event=json.loads(ws.send_text.await_args.args[0])
    assert event['type']=='brain:error' and event['payload']['requestId']=='other-trip'
    assert 'invalid target' in event['payload']['message'] and 'signal' not in event['payload']


@pytest.mark.asyncio
async def test_refresh_timeout_reports_failure_without_running_brain():
    ws=SimpleNamespace(send_text=AsyncMock())
    async def slow_refresh(**kwargs):
        await asyncio.Event().wait()
    brain=SimpleNamespace(assess=AsyncMock())
    await deliver_report(ws,SimpleNamespace(refresh=slow_refresh),brain,{},dict(requestId='timeout'),.01)
    brain.assess.assert_not_awaited()
    assert 'timed out' in json.loads(ws.send_text.await_args.args[0])['payload']['message']


@pytest.mark.asyncio
async def test_cancellation_does_not_become_fabricated_failure_or_report():
    ws=SimpleNamespace(send_text=AsyncMock())
    context=SimpleNamespace(refresh=AsyncMock(side_effect=asyncio.CancelledError))
    with pytest.raises(asyncio.CancelledError):
        await deliver_report(ws,context,SimpleNamespace(assess=AsyncMock()),{},dict(requestId='cancelled'))
    ws.send_text.assert_not_awaited()
