"""Async request regressions use disposable database rows and fake transports."""
import asyncio
import json
from datetime import datetime,timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from brain_request import deliver_report
from red_room import RedRoom
from compiler import TaskCompiler
from tests.test_verified_pricing import database, DAY


@pytest.mark.asyncio
@pytest.mark.parametrize('payload',[dict(targetPrice=True),dict(targetPrice='5000'),dict(targetPrice=float('nan')),
    dict(targetPrice=-1),dict(refreshFeeds='false')])
async def test_invalid_advice_options_fail_before_any_feed_refresh(payload):
    context=SimpleNamespace(refresh=AsyncMock())
    brain=SimpleNamespace(assess=AsyncMock())
    ws=SimpleNamespace(send_text=AsyncMock())
    await deliver_report(ws,context,brain,{},dict(requestId='exact-request',**payload))
    context.refresh.assert_not_awaited()
    brain.assess.assert_not_awaited()
    event=json.loads(ws.send_text.await_args.args[0])
    assert event['type']=='brain:error' and event['payload']['requestId']=='exact-request'


@pytest.mark.asyncio
async def test_redroom_legacy_timestamps_and_one_broken_monitor_do_not_stop_others(monkeypatch):
    events=[]
    room=RedRoom(None,None,None,None,None,None,lambda *event:events.append(event))
    room.list=AsyncMock(return_value=[dict(id='broken',last_checked='2020-01-01T00:00:00',interval_hours=24),
        dict(id='bad-timestamp',last_checked='invalid',interval_hours=24)])
    room.check=AsyncMock(side_effect=[RuntimeError('Temporary read failure'),None])
    monkeypatch.setattr('red_room.asyncio.sleep',AsyncMock(side_effect=asyncio.CancelledError))
    with pytest.raises(asyncio.CancelledError):
        await room.loop()
    assert [call.args[0] for call in room.check.await_args_list]==['broken','bad-timestamp']
    assert events[0][0]=='redroom:error' and events[0][1]['id']=='broken'


@pytest.mark.asyncio
async def test_redroom_list_failure_retries_instead_of_terminating(monkeypatch):
    events=[]
    room=RedRoom(None,None,None,None,None,None,lambda *event:events.append(event))
    room.list=AsyncMock(side_effect=RuntimeError('Temporary database error'))
    monkeypatch.setattr('red_room.asyncio.sleep',AsyncMock(side_effect=asyncio.CancelledError))
    with pytest.raises(asyncio.CancelledError):
        await room.loop()
    assert events[0][0]=='redroom:error' and 'retrying' in events[0][1]['message']


async def saved_room(database,dispatcher=None):
    room=RedRoom(database,TaskCompiler(database,None),dispatcher or SimpleNamespace(dispatch_all=AsyncMock()),
        SimpleNamespace(assess=AsyncMock()),SimpleNamespace(refresh=AsyncMock()),
        SimpleNamespace(quick_harvest=AsyncMock()),lambda *event:None)
    rid=await room.add(dict(trip=dict(origin='DEL',destination='BOM',departureDate=DAY)))
    return room,rid


@pytest.mark.asyncio
async def test_initial_monitor_emit_failure_releases_running_marker_and_database_lease(database):
    room,rid=await saved_room(database)
    room.emit_list=AsyncMock(side_effect=[RuntimeError('Initial list failed'),None])
    await room.check(rid)
    item=(await room.list())[0]
    assert rid not in room.running and item['lease_owner'] is None and item['lease_until'] is None
    assert 'Initial list failed' in item['last_error']


@pytest.mark.asyncio
async def test_cancelled_monitor_releases_lease_without_advice_or_notification(database):
    dispatcher=SimpleNamespace(dispatch_all=AsyncMock(side_effect=asyncio.CancelledError))
    room,rid=await saved_room(database,dispatcher)
    with pytest.raises(asyncio.CancelledError):
        await room.check(rid)
    room.brain.assess.assert_not_awaited()
    item=(await room.list())[0]
    assert item['report'] is None and item['lease_owner'] is None and not room.running
    assert await database.get_notifications()==[]


@pytest.mark.asyncio
async def test_adding_monitor_validates_without_creating_phantom_search_history(database):
    room,rid=await saved_room(database)
    assert await database.get_searches()==[]
    await room.check(rid)
    searches=await database.get_searches()
    assert len(searches)==1
    assert searches[0]['origin']=='DEL' and searches[0]['destination']=='BOM'


@pytest.mark.asyncio
async def test_abnormal_websocket_close_always_removes_connection():
    import main
    ws=SimpleNamespace(headers={},accept=AsyncMock(),receive_text=AsyncMock(side_effect=RuntimeError('Socket closed')))
    with pytest.raises(RuntimeError,match='Socket closed'):
        await main.websocket_endpoint(ws)
    assert ws not in main.active_connections


@pytest.mark.asyncio
async def test_unknown_websocket_operation_reports_correlated_error():
    import main
    ws=SimpleNamespace(send_text=AsyncMock())
    await main.handle_message('missing:operation',dict(requestId='unknown-request'),ws)
    event=json.loads(ws.send_text.await_args.args[0])
    assert event['type']=='error' and event['payload']['originalType']=='missing:operation'
    assert event['payload']['requestId']=='unknown-request'


@pytest.mark.asyncio
async def test_search_ack_is_sent_before_any_workers_start(monkeypatch):
    import main
    order=[]
    async def sent(raw):
        order.append(json.loads(raw)['type'])
        await asyncio.sleep(0)
    def scheduled(coroutine):
        order.append('worker-scheduled')
        coroutine.close()
    compiler=SimpleNamespace(compile=AsyncMock(return_value={'search_id':'compiled','platforms':['cleartrip']}))
    harvester=SimpleNamespace(quick_harvest=AsyncMock())
    engine=SimpleNamespace(dispatch_all=AsyncMock())
    monkeypatch.setattr(main,'compiler',compiler)
    monkeypatch.setattr(main,'coupon_harvester',harvester)
    monkeypatch.setattr(main,'dispatcher',engine)
    monkeypatch.setattr(main,'user_prefs',None)
    monkeypatch.setattr(main,'start_job',scheduled)
    await main.handle_message('search:start',{},SimpleNamespace(send_text=sent))
    assert order==['search:started','worker-scheduled','worker-scheduled']
    assert harvester.quick_harvest.call_args.args[0]==['cleartrip']


@pytest.mark.asyncio
@pytest.mark.parametrize('operation',['session:prepare','coupon:refresh','redroom:check'])
async def test_background_request_failure_reaches_its_ui_with_request_context(monkeypatch,operation):
    import main
    ws=SimpleNamespace(send_text=AsyncMock())
    monkeypatch.setattr(main,'dispatcher',SimpleNamespace(prepare_checkout=AsyncMock(side_effect=ValueError('Unavailable checkout'))))
    monkeypatch.setattr(main,'coupon_harvester',SimpleNamespace(deep_harvest=AsyncMock(side_effect=RuntimeError('Offer refresh failed'))))
    monkeypatch.setattr(main,'red_room',SimpleNamespace(check=AsyncMock(side_effect=ValueError('Monitor not found'))))
    payload=dict(requestId='pending-request',searchId='current-search',resultId='selected-result',id='missing-monitor')
    await main.handle_message(operation,payload,ws)
    tasks=list(main.pending_jobs)
    assert tasks
    await asyncio.gather(*tasks)
    messages=[json.loads(call.args[0]) for call in ws.send_text.await_args_list]
    error=next(message for message in messages if message['type']=='error')['payload']
    assert error['originalType']==operation and error['requestId']=='pending-request'
    assert error['searchId']=='current-search' and error['resultId']=='selected-result'


@pytest.mark.asyncio
async def test_removed_watch_does_not_publish_a_late_alert(database,monkeypatch):
    import main
    await database.add_watchlist_item(dict(origin='DEL',destination='BOM',departure_date=DAY,target_price=6000))
    item=(await database.get_watchlist())[0]
    async def dispatch(task):
        await database.remove_watchlist_item(item['id'])
    monkeypatch.setattr(main,'db',database)
    monkeypatch.setattr(main,'compiler',TaskCompiler(database,None))
    monkeypatch.setattr(main,'dispatcher',SimpleNamespace(dispatch_all=dispatch))
    events=[]
    monkeypatch.setattr(main,'emit_ws',lambda *event:events.append(event))
    monkeypatch.setattr(database,'get_search_results',AsyncMock(return_value=[dict(final_price=5000,platform='cleartrip',savings_breakdown={'integrity':{'status':'corroborated'}})]))
    await main.check_watch_item(item)
    assert await database.get_notifications()==[]
    assert not any(event[0]=='watchlist:alert' for event in events)


@pytest.mark.asyncio
async def test_watch_scheduler_accepts_old_naive_and_new_aware_times_and_isolates_bad_rows(monkeypatch):
    import main
    now=datetime.now(timezone.utc)
    items=[dict(id='naive',departure_date=DAY,last_checked=now.replace(tzinfo=None).isoformat(),check_frequency='daily'),
           dict(id='aware',departure_date=DAY,last_checked=now.isoformat(),check_frequency='daily'),
           dict(id='broken',departure_date='invalid',last_checked=None,check_frequency='daily'),
           dict(id='due',departure_date=DAY,last_checked='bad timestamp',check_frequency='daily')]
    monkeypatch.setattr(main,'db',SimpleNamespace(get_watchlist=AsyncMock(return_value=items)))
    check=AsyncMock()
    monkeypatch.setattr(main,'check_watch_item',check)
    monkeypatch.setattr(main.asyncio,'sleep',AsyncMock(side_effect=asyncio.CancelledError))
    with pytest.raises(asyncio.CancelledError):
        await main.watchlist_scheduler_loop()
    assert [call.args[0]['id'] for call in check.await_args_list]==['due']
