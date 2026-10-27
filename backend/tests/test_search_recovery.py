"""Failure recovery preserves explicit state rather than a stale success."""
import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from search_engine import Dispatcher
from tests.test_quote_integrity import quote
from tests.test_verified_pricing import TRIP, database


def booking_engine(fail_stage):
    row=quote('reopen','cleartrip',4800,verification='checkout',listed_price=5000,
        listed_observed_at='2026-10-10T01:00:00Z',integrity={'status':'checkout_verified'})
    row.update(search_id='search',session_id='expired',best_coupon_code='OLD')
    page=SimpleNamespace(url='https://www.cleartrip.com/flights/results',inner_text=AsyncMock(return_value='Review'))
    sessions=SimpleNamespace(_sessions={},close_session=AsyncMock(),
        handoff_to_user=AsyncMock(),set_session_ready=AsyncMock())
    async def register(sid,*args):sessions._sessions[sid]={'page':page}
    sessions.register_session=register
    saved=[]
    async def save(value):saved.append(deepcopy(value))
    db=SimpleNamespace(get_search_results=AsyncMock(return_value=[row]),save_result=save)
    worker=SimpleNamespace(input_search_criteria=AsyncMock(),execute_search=AsyncMock(),
        parse_search_results=AsyncMock(return_value=[{**row,'base_price':6200}]),select_flight=AsyncMock())
    getattr(worker,fail_stage).side_effect=RuntimeError('Provider failed')
    engine=Dispatcher(db,sessions,None,None,None,lambda *args:None)
    engine._worker=AsyncMock(return_value=worker)
    engine.factory=SimpleNamespace(create_cloak_browser=AsyncMock(return_value=(object(),SimpleNamespace(pages=[page]),page)))
    engine._search_tasks['search']={'search_id':'search','trip':{**TRIP,'trip_type':'one_way'},'cloak':{}}
    return engine,saved,sessions


@pytest.mark.asyncio
@pytest.mark.parametrize('stage,expected_price',[
    ('input_search_criteria',5000),('select_flight',6200),
])
async def test_reopen_failure_cannot_leave_old_verified_amount(stage,expected_price):
    engine,saved,sessions=booking_engine(stage)
    with pytest.raises(RuntimeError,match='Provider failed'):
        await engine.prepare_checkout('search','reopen')
    final=saved[-1]
    assert final['final_price']==expected_price
    assert final['session_id'] is None and final['best_coupon_code'] is None
    assert final['savings_breakdown']['verification']=='listed'
    assert final['savings_breakdown']['integrity']['status']=='uncorroborated'
    assert final['savings_breakdown']['previous_checkout']['price']==4800
    sessions.close_session.assert_awaited_once()
    sessions.handoff_to_user.assert_not_awaited()


@pytest.mark.asyncio
async def test_expired_registered_session_retries_fresh_cart_on_first_click():
    engine,saved,sessions=booking_engine('input_search_criteria')
    sessions._sessions['expired']={}
    sessions.get_session_status=lambda sid:'expired'
    with pytest.raises(RuntimeError,match='Provider failed'):
        await engine.prepare_checkout('search','reopen')
    assert sessions.close_session.await_args_list[0].args==('expired',)
    engine.factory.create_cloak_browser.assert_awaited_once()
    sessions.handoff_to_user.assert_not_awaited()
    assert saved[-1]['savings_breakdown']['verification']=='listed'


@pytest.mark.asyncio
async def test_cancelled_search_propagates_to_monitor_caller(database):
    events=[]
    engine=Dispatcher(database,SimpleNamespace(_sessions={}),None,None,None,
        lambda *args:events.append(args))
    started=asyncio.Event()
    async def scrape(*args):
        started.set()
        await asyncio.Future()
    engine._run_platform=scrape
    engine.apply_integrity=AsyncMock(return_value=[])
    task={'search_id':'cancelled','trip':{**TRIP,'trip_type':'one_way'},
        'cloak':{'max_concurrent_bots':1},'platforms':['cleartrip']}
    job=asyncio.create_task(engine.dispatch_all(task))
    await started.wait()
    job.cancel()
    with pytest.raises(asyncio.CancelledError):await job
    assert [kind for kind,_ in events]==['search:cancelled']
    engine.apply_integrity.assert_not_awaited()
    assert 'cancelled' not in engine._active_searches
