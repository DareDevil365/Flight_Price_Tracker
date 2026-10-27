import asyncio
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from intelligence import MarketContext, SuggestionBrain, daily_prices, calibrated_trend
from alternative_planner import connection_candidates
from offer_parser import published_offer, scrape_published_offers
from red_room import RedRoom
from financial_filter import FinancialFilter
from quotes import valid_flights, search_url, utc_now
from tests.test_verified_pricing import database, page, DAY, TRIP


@pytest.mark.asyncio
async def test_seeded_coupons_are_not_live_evidence(database):
    await database.add_coupon(dict(platform='cleartrip',code='FAKE',description='HDFC birthday 50% off',valid_from='2099-01-01',source='seeded',source_url='https://example.com'))
    await database.add_coupon(dict(platform='cleartrip',code='USER',source='user'))
    offer=published_offer('cleartrip','REAL','10% off credit cards','https://www.cleartrip.com/offers',native=True)
    await database.add_coupon(offer)
    assert {c['code'] for c in await database.get_live_coupons('cleartrip')}=={'USER','REAL'}
    async with database.db.execute('SELECT count(*) FROM offer_observations') as cur:
        assert (await cur.fetchone())[0]==1


@pytest.mark.asyncio
async def test_published_codes_only_and_no_invented_expiry(page,database):
    await page.set_content('''<div class="coupon-card">GET Save 1000 today APPLY</div>
        <div class="coupon-card"><span class="couponCode">VALID10</span>10% off on HDFC or ICICI debit cards. Minimum spend INR 5,000. Valid until 2099-01-01</div>
        <div class="main-bo-lis"><div id="divNote1">BOOKNOW: Get extra Rs.220 instant discount on this flight</div></div>''')
    offers=await scrape_published_offers(page,'easemytrip')
    assert {o['code'] for o in offers}=={'VALID10','BOOKNOW'}
    real=next(o for o in offers if o['code']=='VALID10')
    assert real['bank_restriction']=='HDFC|ICICI' and real['min_booking_value']==5000
    assert FinancialFilter().passes(real,{'whitelisted_banks':['ICICI']})[0]
    assert next(o for o in offers if o['code']=='BOOKNOW')['valid_until'] is None
    assert published_offer('cleartrip','GET','Just a heading','https://www.cleartrip.com') is None


def test_forecast_cold_start_and_chronological_holdout():
    today=date.today()
    points=[(today-timedelta(days=209-i),30000-i*100) for i in range(210)]
    assert calibrated_trend(points[:10])['forecast_7d'] is None
    assert calibrated_trend(points[:30])['forecast_7d'] is None
    result=calibrated_trend(points)
    assert result['status']=='LOCAL_HOLDOUT_PASSED' and result['model_mae']<result['baseline_mae']
    assert result['certainty']['percent']==100 and result['certainty']['range'][0]<100
    repeated=[dict(observed_at=utc_now(),price=p) for p in (4000,5000,6000)]
    assert len(daily_prices(repeated))==1
    assert calibrated_trend([(d,5000) for d,p in points])['status']=='BASELINE_PREFERRED'


@pytest.mark.asyncio
async def test_news_alone_cannot_recommend_purchase_and_legacy_future_offer_ignored(database):
    context=MarketContext(database);await context.initialize()
    await context._save('reported_news',[dict(title='War threatens fuel supply',url='https://example.com/report',published_at=utc_now(),primary_source=False)])
    future=(date.today()+timedelta(days=7)).isoformat()
    await database.add_coupon(dict(platform='cleartrip',code='FAKE',valid_from=future,source_url='https://example.com',source='seeded'))
    brain=SuggestionBrain(database,context)
    report=await brain.assess(TRIP,target_price=6000)
    assert report['signal']=='MONITOR' and report['price'] is None
    assert report['upcoming_offers']==[] and report['forecast']['forecast_7d'] is None
    row=dict(platform='cleartrip',airline='IndiGo',flight_number='6E-1',departure_time='08:30',departure_date=DAY,stops=0,final_price=5000,best_coupon_code=None,
        savings_breakdown=dict(origin='DEL',destination='BOM',passenger_count=1,cabin_class='ECONOMY',verification='listed',observed_at=utc_now(),integrity={'status':'corroborated'}))
    await database.record_quote(row)
    report=await brain.assess(TRIP,target_price=6000)
    assert report['signal']=='BUY_CANDIDATE' and report['verification']=='listed'
    assert 'payment total' in report['reasoning']
    # A failed current search must not reuse a previously cheap quote to buy now.
    report=await brain.assess(TRIP,target_price=6000,current_quotes=[])
    assert report['signal']=='MONITOR' and report['price'] is None


def leg(origin,destination,day,depart,arrive,duration,price):
    return dict(departure_date=day,departure_time=depart,arrival_time=arrive,duration=duration,final_price=price,
        savings_breakdown=dict(origin=origin,destination=destination,passenger_count=1,cabin_class='ECONOMY',verification='listed'))


def test_separate_tickets_airport_buffer_and_overnight():
    a=leg('DEL','BOM',DAY,'20:00','22:00','2h',3000)
    next_day=(date.fromisoformat(DAY)+timedelta(days=1)).isoformat()
    b=leg('BOM','GOI',next_day,'03:00','04:20','1h 20m',2000)
    result=connection_candidates([a],[b],6000)
    assert result[0]['saving']==1000 and result[0]['connection_minutes']==300
    assert result[0]['terminal_status']=='unknown' and result[0]['net_saving'] is None
    assert not connection_candidates([a],[{**b,'savings_breakdown':{**b['savings_breakdown'],'origin':'NMI'}}],6000)
    assert not connection_candidates([a],[{**b,'departure_time':'23:00','departure_date':DAY}],6000)


@pytest.mark.asyncio
async def test_red_room_persistence_no_duplicate_alerts_and_removed_monitor(database):
    context=MarketContext(database);await context.initialize()
    from compiler import TaskCompiler
    compiler=TaskCompiler(database,None)
    row=dict(platform='cleartrip',airline='IndiGo',flight_number='6E-1',departure_time='08:30',departure_date=DAY,final_price=5000,best_coupon_code=None,
        stops=0,savings_breakdown=dict(origin='DEL',destination='BOM',passenger_count=2,cabin_class='BUSINESS',verification='listed',observed_at=utc_now(),integrity={'status':'corroborated'}))
    await database.record_quote(row)
    engine=SimpleNamespace(dispatch_all=AsyncMock(),explore_alternatives=AsyncMock(return_value=[]))
    database.get_search_results=AsyncMock(return_value=[row])
    events=[]
    market=SimpleNamespace(refresh=AsyncMock())
    harvester=SimpleNamespace(quick_harvest=AsyncMock())
    room=RedRoom(database,compiler,engine,SuggestionBrain(database,context),market,harvester,lambda *e:events.append(e))
    request=dict(trip=dict(origin='DEL',destination='BOM',departureDate=DAY,passengerCount=2,cabinClass='BUSINESS'),intervalHours=24,targetPrice=6000)
    rid=await room.add(request)
    await room.check(rid);await room.check(rid)
    items=await room.list()
    assert items[0]['report']['signal']=='BUY_CANDIDATE' and items[0]['last_price']==5000
    assert engine.dispatch_all.call_args[0][0]['trip']['passenger_count']==2
    assert len([e for e in events if e[0]=='redroom:alert'])==1
    assert len(await database.get_notifications())==1
    await room.remove(rid)
    assert await room.list()==[]


def test_gox_url_and_wrong_nearby_airport():
    from urllib.parse import unquote_plus
    assert 'GOX-Goa-India' in unquote_plus(search_url('easemytrip',{**TRIP,'origin':'GOX','destination':'JAI'}))
    row=dict(departure_time='10:00',arrival_time='11:00',base_price=1000,airline='IndiGo',stops=0,nearby_airport=True)
    assert not valid_flights([row],TRIP)


def test_real_offer_restrictions_require_matching_passengers_card_and_payment():
    filters=FinancialFilter()
    assert not filters.passes({'description':'15% off on 2 Passengers'},{'passenger_count':1})[0]
    assert not filters.passes({'description':'Up to 5000 off child / 100% off infant'},{})[0]
    coupon={'description':'10% off on Flipkart Axis Credit Card','bank_restriction':'AXIS','card_type':'CREDIT'}
    rules={'whitelisted_banks':['AXIS'],'owned_card_names':['Flipkart Axis']}
    assert filters.passes(coupon,rules)[0]
    assert filters.passes(coupon,{})[0]  # Ownership is not asked before searching.
    assert not filters.passes(coupon,{**rules,'selected_payment':{'method':'UPI','banks':[]}})[0]
    assert filters.passes(coupon,{**rules,'selected_payment':{'method':'CREDIT','banks':['AXIS'],'label':'Flipkart Axis Credit Card'}})[0]


@pytest.mark.asyncio
async def test_selected_payment_options_are_not_selection_evidence(page):
    from workers.cleartrip_worker import CleartripWorker
    worker=CleartripWorker()
    await page.set_content('<div>Payment options: UPI Credit card Debit card</div>')
    assert await worker.read_selected_payment(page) is None
    await page.set_content('<div>Payment method: HDFC Credit card</div>')
    assert await worker.read_selected_payment(page)=={'method':'CREDIT','banks':['HDFC'],'label':'CREDIT HDFC'}
