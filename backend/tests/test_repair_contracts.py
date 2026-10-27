"""Adversarial local fixtures; no test data is stored in the live application."""
import asyncio
from datetime import date,datetime,timedelta,timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from offer_rules import evaluate_tree,evaluate_offer
from offer_parser import published_offer
from financial_filter import FinancialFilter
from quote_contract import listed_amount
from quote_integrity import check_outputs
from alternative_planner import connection_candidates,AlternativePlanner
from provider_status import page_problem
from intelligence import daily_prices,MarketContext,SuggestionBrain
from red_room import RedRoom
from compiler import TaskCompiler
from tests.test_verified_pricing import database,page,TRIP,DAY,LocalCheckout
from tests.test_quote_integrity import quote
from tests.test_intelligence_and_red_room import leg
from coupon_brute_forcer import CouponBruteForcer
from search_engine import Dispatcher


def test_unknown_logic_cannot_become_proven_eligibility():
    known=dict(op='eq',field='method',value='UPI')
    unknown=dict(op='eq',field='account_eligible',value=True)
    assert evaluate_tree(dict(op='all',conditions=[known,unknown]),{'method':'UPI'}).status=='unknown'
    assert evaluate_tree(dict(op='any',conditions=[known,unknown]),{'method':'UPI'}).status=='eligible'
    assert evaluate_tree(dict(op='not',condition=unknown),{}).status=='unknown'
    assert evaluate_tree(dict(op='any',conditions=[]),{}).status=='unknown'


def test_excluded_cards_do_not_become_required_cards():
    terms='Flight discount using ICICI Bank net banking only. Not valid on credit cards, debit cards or UPI.'
    offer=published_offer('easemytrip','ICICINB',terms,'https://example.test')
    assert offer['card_type']=='NET_BANKING'
    net={'selected_payment':{'method':'NET_BANKING','banks':['ICICI'],'label':'ICICI net banking'}}
    assert FinancialFilter().passes(offer,net)[0]
    assert not FinancialFilter().passes(offer,{'selected_payment':{'method':'UPI','banks':[],'label':'UPI'}})[0]


def test_bank_method_pairs_and_scoped_exclusions():
    offer={'description':'Flight discount on ICICI Bank credit cards. Or HDFC Bank debit cards.'}
    def rules(method,bank,label=''):
        return {'selected_payment':{'method':method,'banks':[bank],'label':label}}
    assert evaluate_offer(offer,rules('CREDIT','ICICI')).status=='eligible'
    assert evaluate_offer(offer,rules('DEBIT','HDFC')).status=='eligible'
    assert evaluate_offer(offer,rules('CREDIT','HDFC')).status=='ineligible'
    offer={'description':'Flight discount on credit cards. Not valid on HDFC Bank credit cards.'}
    assert evaluate_offer(offer,rules('CREDIT','ICICI')).status=='eligible'
    assert evaluate_offer(offer,rules('CREDIT','HDFC')).status=='ineligible'


def test_weekday_limits_and_minimum_spend_are_checked():
    offer={'code':'LIMITED','description':'Flight discount. Every Thursday. Once per account per month.',
           'min_booking_value':5000,'valid_until':'2026-03-31'}
    rules={'booking_date':'2026-03-05','booking_total':6000,'selected_payment':{'method':'UPI','banks':[]}}
    assert evaluate_offer(offer,rules).status=='unknown'
    assert evaluate_offer(offer,{**rules,'eligibility_facts':{'redemption_available':True}}).status=='eligible'
    assert evaluate_offer(offer,{**rules,'booking_date':'2026-03-06'}).status=='ineligible'
    assert evaluate_offer(offer,{**rules,'booking_date':'2026-04-02'}).status=='ineligible'
    assert evaluate_offer(offer,{**rules,'booking_total':4000}).status=='ineligible'


def test_unknown_original_and_account_offer_stay_conditional():
    offer={'code':'NEWFLY','description':'Flight offer for new users'}
    assert FinancialFilter().passes(offer,{})[0]
    assert not FinancialFilter().passes(offer,{'selected_payment':{'method':'UPI','banks':[]}})[0]
    assert evaluate_offer({'code':'OLD','eligibility_unconfirmed':True},{}).status=='unknown'


def test_published_expired_window_is_not_renewed_by_a_new_crawl():
    offer=published_offer('easemytrip','ICICINB',
        'Flight discount. Offer validity: Every Thursday from Feb 05 to Mar 31, 2026.',
        'https://example.test')
    assert offer['valid_until']=='2026-03-31'
    assert evaluate_offer(offer,{'booking_date':'2026-10-08'}).status=='ineligible'
    weekend={'description':'Flight offer valid on Saturday and Sunday'}
    assert evaluate_offer(weekend,{'booking_date':'2026-10-11'}).status=='eligible'
    assert evaluate_offer(weekend,{'booking_date':'2026-10-12'}).status=='ineligible'


def test_missing_flight_identity_and_fare_mismatch_cannot_corroborate():
    a,b=quote('a','cleartrip',5000),quote('b','easemytrip',5010)
    b['flight_number']=''
    assert check_outputs([a,b],TRIP)['a']['status']=='uncorroborated'
    b['flight_number']=a['flight_number']
    b['savings_breakdown']['baggage']='Cabin only'
    a['savings_breakdown']['baggage']='15 kg checked'
    assert check_outputs([a,b],TRIP)['a']['status']=='uncorroborated'
    a['savings_breakdown'].pop('baggage');b['savings_breakdown'].pop('baggage')
    b['final_price']=6000
    assert check_outputs([a,b],TRIP)['a']['status']=='uncorroborated'


def test_payment_total_never_substitutes_for_listing():
    row=quote('a','cleartrip',8000,verification='checkout',listed_price=5000)
    assert listed_amount(row)==5000
    row['savings_breakdown'].pop('listed_price')
    assert listed_amount(row) is None
    row['savings_breakdown']['listed_price']=True
    assert listed_amount(row) is None


def test_separate_tickets_enforce_whole_journey_stops_and_price_basis():
    a=leg('DEL','BOM',DAY,'06:00','08:00','2h',3000)
    b=leg('BOM','GOI',DAY,'13:00','14:20','1h 20m',2000)
    a['stops']=1;b['stops']=0
    assert not connection_candidates([a],[b],6000,max_stops=1)
    a['stops']=0
    assert connection_candidates([a],[b],6000,max_stops=1)[0]['saving']==1000
    a['savings_breakdown'].update(verification='checkout',listed_price=3000)
    a['final_price']=100
    assert connection_candidates([a],[b],6000)[0]['listed_total']==5000
    a['savings_breakdown'].pop('listed_price')
    assert not connection_candidates([a],[b],6000)


@pytest.mark.asyncio
async def test_planner_second_leg_time_and_listing_snapshot():
    trip={**TRIP,'trip_type':'one_way','preferred_time':'MORNING','max_stops':1}
    original=quote('original','cleartrip',9000,verification='checkout',listed_price=6000)
    original['savings_breakdown']['integrity']={'status':'checkout_verified'}
    children=[]
    async def run(platform,child,limit):
        children.append(child['trip'])
    db=SimpleNamespace(get_search_results=AsyncMock(return_value=[original]),save_search=AsyncMock(),
                       db=SimpleNamespace(execute=AsyncMock(),commit=AsyncMock()))
    engine=SimpleNamespace(_search_tasks={'search':{'trip':trip,'financial':{}}},
        db=db,emit_log=lambda *args:None,_run_platform=run,apply_integrity=AsyncMock(return_value=[]))
    assert await AlternativePlanner(engine).explore('search',hubs=['AMD'])==[]
    second=[t for t in children if t['origin']=='AMD']
    assert second and all(t['preferred_time']=='ANY' and t['max_stops']==0 for t in second)
    assert all(t['preferred_time']=='MORNING' for t in children if t['origin']=='DEL')
    original['savings_breakdown'].pop('listed_price')
    with pytest.raises(ValueError,match='listing was not preserved'):
        await AlternativePlanner(engine).explore('search')


def test_coverage_loss_does_not_create_fake_fare_increase():
    day=date.today()-timedelta(days=1)
    def observation(offset,platform,price):
        return {'observed_at':(day+timedelta(days=offset)).isoformat(),'platform':platform,'price':price}
    points=daily_prices([observation(0,'cleartrip',4000),observation(0,'easemytrip',5000),observation(1,'easemytrip',5000)])
    assert [p for d,p in points]==[5000,5000]
    assert daily_prices([observation(0,'cleartrip',4000),observation(1,'easemytrip',5000)])==[]


@pytest.mark.asyncio
async def test_news_model_cannot_compare_checkout_with_listing_forecast(database,monkeypatch):
    import intelligence
    context=MarketContext(database);await context.initialize()
    real=quote('a','cleartrip',8000,verification='checkout',listed_price=4000,integrity={'status':'checkout_verified'})
    monkeypatch.setattr(intelligence,'calibrated_trend',lambda points:{
        'forecast_7d':5000,'confidence':'LOW','certainty':{'percent':None}})
    brain=SuggestionBrain(database,context)
    brain.checkout_session_valid=lambda row:True  # fixture models a live cart
    report=await brain.assess(
        {**TRIP,'departure_date':(date.today()+timedelta(days=90)).isoformat()},
        current_quotes=[{**real,'departure_date':(date.today()+timedelta(days=90)).isoformat()}])
    assert report['signal']=='MONITOR' and report['price']==8000


@pytest.mark.asyncio
async def test_stale_current_quote_cannot_trigger_buy(database):
    context=MarketContext(database);await context.initialize()
    row=quote('old','cleartrip',3000,integrity={'status':'corroborated'})
    row['savings_breakdown']['observed_at']=(datetime.now(timezone.utc)-timedelta(days=2)).isoformat()
    report=await SuggestionBrain(database,context).assess(TRIP,target_price=6000,current_quotes=[row])
    assert report['price'] is None and report['signal']=='MONITOR'


@pytest.mark.asyncio
async def test_fee_waiver_beats_coupon_with_larger_headline_discount(page):
    await page.set_content('''<div>Total payable <span id="total">₹5350</span></div>
      <input id="coupon"><button id="apply">Apply</button><button id="remove">Remove coupon</button>
      <div class="coupon-message" id="message"></div>
      <script>
      document.querySelector('#apply').onclick=()=>{const c=document.querySelector('#coupon').value;
        document.querySelector('#total').textContent=c==='WAIVER'?'₹5000':c==='DISCOUNT'?'₹5150':'₹5350';
        document.querySelector('#message').textContent='Coupon applied successfully';};
      document.querySelector('#remove').onclick=()=>{document.querySelector('#total').textContent='₹5350';
        document.querySelector('#coupon').value='';document.querySelector('#message').textContent='';};
      </script>''')
    result=await CouponBruteForcer(LocalCheckout(),FinancialFilter(),lambda *args:None).brute_force(
        page,[{'code':'DISCOUNT','discount_value':500},{'code':'WAIVER','discount_value':350}],{},'isolated')
    assert result['best_coupon']=='WAIVER' and result['best_price']==5000


@pytest.mark.asyncio
async def test_cart_change_prevents_price_publication(page):
    await page.set_content('<div>Total payable ₹5000</div>')
    async def changed():
        raise ValueError('Selected baggage changed')
    with pytest.raises(ValueError,match='baggage changed'):
        await CouponBruteForcer(LocalCheckout(),FinancialFilter(),lambda *args:None).brute_force(
            page,[],{},'isolated',context_check=changed)


@pytest.mark.parametrize('text,url,responses,code',[
    ('NETWORK PROBLEM','','','PROVIDER_NETWORK'),
    ('Server error','https://example.test/itinerary/failure',[('/itin/v7/itinerary/create',403)],'ACCESS_DENIED'),
    ('200-OK','',[],'ACCESS_DENIED'),
    ('No flights available','',[],'NO_INVENTORY')])
def test_provider_failures_are_not_empty_inventory(text,url,responses,code):
    assert page_problem(text,url,responses).code==code


@pytest.mark.asyncio
async def test_notifications_have_persistent_deduplication(database):
    await database.add_notification('red_room','Title','Message',dedup_key='same')
    await database.add_notification('red_room','Title','Message',dedup_key='same')
    assert len(await database.get_notifications())==1


@pytest.mark.asyncio
async def test_old_integrity_contract_cannot_teach_new_brain(database):
    row=quote('old','cleartrip',3000,integrity={'status':'corroborated'})
    row['best_coupon_code']=None
    await database.record_quote(row)
    assert len(await database.get_quotes('DEL-BOM',DAY))==1
    await database.db.execute('UPDATE fare_quotes SET evidence_version=0')
    await database.db.commit()
    assert await database.get_quotes('DEL-BOM',DAY)==[]


@pytest.mark.asyncio
async def test_checkout_missing_year_route_or_number_is_unverified(page):
    worker=LocalCheckout()
    row=quote('flight','cleartrip',5000)
    row['departure_date']='2026-11-07'
    for text in ('DEL BOM 6E101 08:30 7 Nov','HYD MAA 6E101 08:30 2026-11-07'):
        await page.set_content('<div>'+text+'</div>')
        assert not await worker.confirm_checkout_flight(page,row)
    row['flight_number']=''
    await page.set_content('<div>DEL BOM IndiGo 08:30 10:30 2026-11-07</div>')
    assert not await worker.confirm_checkout_flight(page,row)


@pytest.mark.asyncio
async def test_cleartrip_waits_for_exact_airport_after_promotions(monkeypatch):
    from workers.cleartrip_worker import CleartripWorker
    worker=CleartripWorker();worker._trip=TRIP
    row={**quote('a','cleartrip',5000),'base_price':5000}
    worker._parse_via_dom=AsyncMock(side_effect=[[{**row,'nearby_airport':True}],[row]])
    monkeypatch.setattr(asyncio,'sleep',AsyncMock())
    assert await worker.parse_search_results(None)==[row]
    assert worker._parse_via_dom.await_count==2


@pytest.mark.asyncio
async def test_old_red_room_report_is_preserved_but_not_recommended(database):
    import json
    context=MarketContext(database);await context.initialize()
    room=RedRoom(database,TaskCompiler(database,None),None,None,None,None,lambda *args:None)
    rid=await room.add({'trip':{'origin':'DEL','destination':'BOM','departureDate':DAY}})
    await database.db.execute('UPDATE red_room SET report=? WHERE id=?',(json.dumps({'signal':'BUY_CANDIDATE','price':100}),rid))
    await database.db.commit()
    item=(await room.list())[0]
    assert item['report'] is None and 'predates' in item['last_error']
    async with database.db.execute('SELECT report FROM red_room WHERE id=?',(rid,)) as cursor:
        assert json.loads((await cursor.fetchone())[0])['price']==100


@pytest.mark.asyncio
async def test_reopened_checkout_does_not_keep_old_verified_price():
    row=quote('reopen','cleartrip',4800,verification='checkout',listed_price=5000,
        integrity={'status':'checkout_verified'},selected_payment={'method':'UPI'})
    row.update(search_id='search',session_id='expired',base_price=5350,effective_price=4800,
        best_coupon_code='OLD',savings=550,all_tested_coupons=[{'code':'OLD'}])
    page=SimpleNamespace(inner_text=AsyncMock(return_value='Booking review'),url='https://example.test/review')
    context=SimpleNamespace(pages=[page])
    sessions=SimpleNamespace(_sessions={},set_session_ready=AsyncMock(),handoff_to_user=AsyncMock(),close_session=AsyncMock())
    async def register(sid,*args):
        sessions._sessions[sid]={'page':page}
    sessions.register_session=register
    database=SimpleNamespace(get_search_results=AsyncMock(return_value=[row]),save_result=AsyncMock())
    engine=Dispatcher(database,sessions,FinancialFilter(),None,None,lambda *args:None)
    worker=SimpleNamespace(input_search_criteria=AsyncMock(),execute_search=AsyncMock(),
        parse_search_results=AsyncMock(return_value=[{**row,'base_price':6200}]),select_flight=AsyncMock())
    engine._worker=AsyncMock(return_value=worker)
    engine.factory=SimpleNamespace(create_cloak_browser=AsyncMock(return_value=(object(),context,page)))
    engine._search_tasks['search']={'trip':{**TRIP,'trip_type':'one_way'},'cloak':{}}
    await engine.prepare_checkout('search','reopen')
    saved=database.save_result.call_args.args[0]
    assert saved['final_price']==6200 and saved['best_coupon_code'] is None
    assert saved['savings_breakdown']['verification']=='listed'
    assert saved['savings_breakdown']['integrity']['status']=='uncorroborated'
    assert 'selected_payment' not in saved['savings_breakdown']


@pytest.mark.asyncio
async def test_monitor_lease_prevents_duplicate_jobs_and_releases_on_cancel(database):
    context=MarketContext(database);await context.initialize()
    entered=asyncio.Event()
    async def search(task):
        entered.set()
        await asyncio.sleep(60)
    engine=SimpleNamespace(dispatch_all=search)
    market=SimpleNamespace(refresh=AsyncMock())
    harvester=SimpleNamespace(quick_harvest=AsyncMock())
    args=(database,TaskCompiler(database,None),engine,SuggestionBrain(database,context),market,harvester,lambda *args:None)
    one,two=RedRoom(*args),RedRoom(*args)
    rid=await one.add({'trip':{'origin':'DEL','destination':'BOM','departureDate':DAY},'intervalHours':24})
    task=asyncio.create_task(one.check(rid))
    await asyncio.wait_for(entered.wait(),5)
    await asyncio.wait_for(two.check(rid),1)
    task.cancel();await asyncio.gather(task,return_exceptions=True)
    item=(await one.list())[0]
    assert item['lease_owner'] is None and item['last_attempt'] and not item['last_success']
