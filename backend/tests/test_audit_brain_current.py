"""Audit regressions; all fares/reports are local fixtures in temporary SQLite."""
import asyncio
import json
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from alternative_planner import AlternativePlanner
from booking_advisor import PricePredictor
from compiler import TaskCompiler
from intelligence import MarketContext, SuggestionBrain
from red_room import RedRoom
from tests.test_verified_pricing import database, TRIP, DAY
from tests.test_quote_integrity import quote


@pytest.mark.asyncio
async def test_checkout_ledger_preserves_conditions_without_claiming_a_live_cart(database):
    row=quote('receipt','cleartrip',4000,verification='checkout',
        integrity={'status':'checkout_verified'},selected_payment={'method':'CREDIT','banks':['HDFC']},
        cart_options={'baggage':'none'},fee_scope='merchant only',fee_breakdown=[{'name':'fee','amount':99}],
        coupon_coverage={'complete':False})
    row['best_coupon_code']='HDFCTEST'
    await database.record_quote(row)
    history=await database.get_quotes('DEL-BOM',DAY)
    evidence=json.loads(history[0]['evidence'])
    for field in ('selected_payment','cart_options','fee_scope','fee_breakdown','coupon_coverage'):
        assert evidence[field]==row['savings_breakdown'][field]
    report=await PricePredictor(database).predict('DEL-BOM',DAY)
    assert report['current_price'] is None
    assert report['current_best_coupon'] is None
    assert report['decision']['signal']=='MONITOR'


@pytest.mark.asyncio
async def test_checkout_advice_requires_explicit_live_session_evidence(database):
    context=MarketContext(database);await context.initialize()
    brain=SuggestionBrain(database,context)
    row=quote('receipt','cleartrip',4000,verification='checkout',integrity={'status':'checkout_verified'})
    report=await brain.assess(TRIP,target_price=5000,current_quotes=[row])
    assert report['price'] is None and report['signal']=='MONITOR'
    brain.checkout_session_valid=lambda candidate: candidate is row
    report=await brain.assess(TRIP,target_price=5000,current_quotes=[row])
    assert report['price']==4000 and report['signal']=='BUY_CANDIDATE'


@pytest.mark.asyncio
async def test_explicit_budget_overrides_departure_deadline(database):
    context=MarketContext(database);await context.initialize()
    trip={**TRIP,'departure_date':(date.today()+timedelta(days=5)).isoformat()}
    row=quote('over-budget','cleartrip',7000,integrity={'status':'corroborated'})
    row['departure_date']=trip['departure_date']
    report=await SuggestionBrain(database,context).assess(trip,{'max_final_price':5000},current_quotes=[row])
    assert report['signal']=='MONITOR'
    assert report['decision_basis']['target_met'] is False
    assert report['decision_basis']['target_price']==5000


@pytest.mark.asyncio
async def test_outbound_price_cannot_approve_a_round_trip_budget(database):
    context=MarketContext(database);await context.initialize()
    trip={**TRIP,'trip_type':'round_trip','return_date':(date.today()+timedelta(days=40)).isoformat()}
    row=quote('outbound-only','cleartrip',4000,integrity={'status':'corroborated'})
    report=await SuggestionBrain(database,context).assess(trip,target_price=5000,current_quotes=[row])
    assert report['signal']=='MONITOR'
    assert report['decision_basis']['target_met'] is None
    assert report['forecast']['forecast_7d'] is None
    assert 'outbound-only' in report['reasoning']
    assert 'meets your target' not in report['reasoning']


@pytest.mark.asyncio
async def test_red_room_alerts_again_when_same_deal_returns(database):
    context=MarketContext(database);await context.initialize()
    row=quote('fare','cleartrip',5000,integrity={'status':'corroborated'})
    database.get_search_results=AsyncMock(return_value=[row])
    reports=[dict(signal=signal,price=price,platform='cleartrip',reasoning='Fixture decision')
        for signal,price in [('BUY_CANDIDATE',5000),('MONITOR',7000),('BUY_CANDIDATE',5000),('BUY_CANDIDATE',5000)]]
    room=RedRoom(database,TaskCompiler(database,None),SimpleNamespace(dispatch_all=AsyncMock()),
        SimpleNamespace(assess=AsyncMock(side_effect=reports)),SimpleNamespace(refresh=AsyncMock()),
        SimpleNamespace(quick_harvest=AsyncMock()),lambda *args:None)
    rid=await room.add(dict(trip=dict(origin='DEL',destination='BOM',departureDate=DAY),targetPrice=6000))
    for _ in reports:
        await room.check(rid)
    notifications=await database.get_notifications()
    assert len(notifications)==2


@pytest.mark.asyncio
async def test_all_alternative_routes_share_two_worker_limit(database):
    trip={**TRIP,'origin':'GOI','destination':'HYD','trip_type':'one_way'}
    task={'search_id':'original','trip':trip,'financial':{}}
    row=quote('source','cleartrip',8000,origin='GOI',destination='HYD',integrity={'status':'corroborated'})
    database.get_search_results=AsyncMock(return_value=[row])
    active=0;peak=0
    async def run(platform,child,limit):
        nonlocal active,peak
        async with limit:
            active+=1;peak=max(peak,active)
            await asyncio.sleep(.005)
            active-=1
    engine=SimpleNamespace(_search_tasks={'original':task},db=database,emit_log=lambda *args:None,
        _run_platform=run,apply_integrity=AsyncMock(return_value=[]))
    assert await AlternativePlanner(engine).explore('original')==[]
    assert peak==2
