"""New input/offer regressions use no production data or live merchant pages."""
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from compiler import TaskCompiler
from deal_feedback import parse_feedback, available_result
from text_ai import TextAI
from offer_parser import scrape_published_offers
from tests.test_verified_pricing import database, page, DAY, TRIP
from tests.test_quote_integrity import quote
from travel_advisor import SmartAdvisor
from workers.cleartrip_worker import CleartripWorker


def test_mixed_ownership_and_negation_are_local_to_each_bank():
    result=parse_feedback("I don't have HDFC but I have SBI")
    assert result['blacklisted_banks']==['HDFC']
    assert parse_feedback('no HDFC and ICICI')['blacklisted_banks']==['HDFC','ICICI']
    assert parse_feedback('exclude Flipkart Axis; I have HDFC')['excluded_card_names']==['FLIPKART AXIS']


@pytest.mark.asyncio
async def test_custom_instructions_cannot_turn_dont_have_into_ownership():
    result=await TextAI().parse_custom_instructions("I don't have HDFC; I have SBI; only UPI")
    assert {'type':'blacklist_bank','bank':'HDFC'} in result
    assert {'type':'whitelist_bank','bank':'SBI'} in result
    assert {'type':'whitelist_bank','bank':'HDFC'} not in result
    assert {'type':'only_upi'} in result
    with pytest.raises(ValueError):
        await TextAI().parse_custom_instructions('skip HDFC and flights after 6pm')


@pytest.mark.asyncio
@pytest.mark.parametrize('part',[
    {'trip':{'preferredTime':'AFTER_6PM'}}, {'trip':{'nearbyDatesRange':1.9}},
    {'financial':{'maxFinalPrice':True}}, {'financial':{'blacklistedBanks':'HDFC'}},
    {'financial':{'allowEMI':'false'}}, {'financial':{'allowedCardTypes':['CHEQUE']}},
    {'cloak':{'maxConcurrentBots':0}}, {'platforms':'cleartrip'}, {'trip':None},
])
async def test_invalid_search_fields_fail_before_database_access(part):
    raw=dict(trip=dict(origin='DEL',destination='BOM',departureDate=DAY),
             financial={},cloak={},platforms=['cleartrip'])
    for field,value in part.items():
        raw[field]={**raw[field],**value} if isinstance(value,dict) else value
    db=SimpleNamespace(get_live_coupons=AsyncMock(),save_search=AsyncMock())
    with pytest.raises(ValueError):
        await TaskCompiler(db,None).compile(raw)
    db.get_live_coupons.assert_not_awaited()
    db.save_search.assert_not_awaited()


@pytest.mark.asyncio
async def test_only_upi_and_specific_card_restrictions_reach_task():
    db=SimpleNamespace(get_live_coupons=AsyncMock(return_value=[]),save_search=AsyncMock())
    task=await TaskCompiler(db,TextAI()).compile(dict(
        trip=dict(origin='DEL',destination='BOM',departureDate=DAY,specificFlightNumber=''),
        platforms=['cleartrip'],financial=dict(customInstructions='only UPI; exclude Flipkart Axis')))
    assert task['financial']['allowed_card_types']==['UPI']
    assert task['financial']['excluded_card_names']==['FLIPKART AXIS']


@pytest.mark.asyncio
@pytest.mark.parametrize('suffix',['for 12 adults','with 1 infant','via HYD','round trip','on '+DAY+' and '+DAY+' and '+DAY])
async def test_nlp_never_silently_changes_unsupported_request(suffix):
    with pytest.raises(ValueError):
        await TextAI().parse_trip_nlp('DEL to BOM on '+DAY+' '+suffix)


@pytest.mark.asyncio
async def test_nlp_uses_complete_indian_airport_reference():
    parsed=await TextAI().parse_trip_nlp('IXM to TRZ on '+DAY+' for 2 travelers 1 stop')
    assert (parsed['origin'],parsed['destination'],parsed['passengerCount'],parsed['maxStops'])==('IXM','TRZ',2,1)


@pytest.mark.asyncio
async def test_native_heading_case_and_hidden_offers(page):
    await page.set_content('''<div class="offer-card">Use Code: FLAT500<br>Flight discount INR 500 off</div>
      <div style="opacity:0"><div class="offer-card">Use Code: SECRET<br>Flight discount INR 900 off</div></div>
      <div class="offer-card" style="visibility:hidden" data-code="HIDDEN">Flight discount INR 900 off</div>''')
    offers=await scrape_published_offers(page,'cleartrip')
    assert [offer['code'] for offer in offers]==['FLAT500']


@pytest.mark.asyncio
async def test_coupon_refresh_updates_discount_cap_and_indian_booking_day(database,monkeypatch):
    indian_day=(date.today()+timedelta(days=1)).isoformat()
    coupon=dict(platform='cleartrip',code='AUDITTEST',source='user',discount_type='PERCENT',
        discount_value=10,max_discount=500,valid_from=indian_day,valid_until=indian_day)
    await database.add_coupon(coupon)
    await database.add_coupon({**coupon,'max_discount':800})
    monkeypatch.setattr('quotes.india_today',lambda:date.fromisoformat(indian_day))
    found=await database.get_live_coupons('cleartrip')
    assert len(found)==1 and found[0]['max_discount']==800
    monkeypatch.setattr('quotes.india_today',lambda:date.fromisoformat(indian_day)+timedelta(days=1))
    assert await database.get_live_coupons('cleartrip')==[]


@pytest.mark.asyncio
async def test_advisor_withdraws_expired_cart_from_current_savings(database):
    row=quote('cart','cleartrip',4000,verification='checkout',listed_price=6000,
              integrity={'status':'checkout_verified'})
    predictor=SimpleNamespace(predict=AsyncMock(return_value=dict(route='DEL-BOM',decision=dict(
        signal='MONITOR',urgency='LOW',confidence=None,recommended_book_by=None,reasoning='fixture'))))
    brain=SimpleNamespace(assess=AsyncMock(return_value=dict(signal='MONITOR',reasoning='fixture',confidence=None)))
    advisor=SmartAdvisor(database,predictor,brain=brain)
    await advisor.get_advisory(TRIP,[row])
    sent=brain.assess.await_args.kwargs['current_quotes']
    assert sent and sent[0]['savings_breakdown']['verification']=='listed'
    assert sent[0]['final_price']==6000


def test_receipt_must_match_actual_payment_and_excluded_card():
    row=quote('cart','cleartrip',4000,verification='checkout',integrity={'status':'checkout_verified'},
              selected_payment={'method':'CREDIT','banks':['AXIS'],'label':'CREDIT AXIS FLIPKART AXIS'})
    assert not available_result(row,{'excluded_card_names':['FLIPKART AXIS']},[])
    row['best_coupon_code']='PAYMENTTEST'
    offer={'platform':'cleartrip','code':'PAYMENTTEST','description':'Flight discount on ICICI credit cards'}
    assert not available_result(row,{},[offer])


@pytest.mark.asyncio
async def test_payment_facts_do_not_store_masked_card_identifiers(page):
    await page.set_content('<div>Selected payment method: HDFC Regalia credit card ending 4567</div>')
    selected=await CleartripWorker().read_selected_payment(page)
    assert selected['method']=='CREDIT' and selected['banks']==['HDFC']
    assert 'REGALIA' in selected['label'] and '4567' not in str(selected)


@pytest.mark.asyncio
@pytest.mark.parametrize('markup',[
    '<div>Payment method: HDFC Credit card</div><div>Selected payment method: ICICI Credit card</div>',
    '<div>Payment method: HDFC or ICICI credit card</div>',
    '<div>Payment method: UPI</div><label><input type="radio" checked>HDFC credit card</label>',
])
async def test_conflicting_selected_payment_labels_are_not_merged(page,markup):
    await page.set_content(markup)
    assert await CleartripWorker().read_selected_payment(page) is None


@pytest.mark.asyncio
async def test_feedback_cannot_change_rules_during_coupon_trial(monkeypatch):
    import asyncio
    import main
    lock=asyncio.Lock()
    await lock.acquire()
    original={'blacklisted_banks':[]}
    task={'financial':original}
    pending={'task':{'search_id':'search','financial':original},'lock':lock}
    monkeypatch.setattr(main,'dispatcher',SimpleNamespace(_search_tasks={'search':task},_pending_checkouts={'cart':pending}))
    with pytest.raises(ValueError,match='verification to finish'):
        await main.handle_message('search:feedback',{'searchId':'search','text':'no HDFC'},None)
    assert task['financial'] is original and pending['task']['financial'] is original
    lock.release()


@pytest.mark.asyncio
async def test_feedback_updates_prepared_cart_rules(monkeypatch):
    import asyncio
    import main
    task={'financial':{},'platforms':['cleartrip'],'trip':TRIP}
    pending={'task':{'search_id':'search','financial':{}},'lock':asyncio.Lock()}
    monkeypatch.setattr(main,'dispatcher',SimpleNamespace(_search_tasks={'search':task},_pending_checkouts={'cart':pending}))
    monkeypatch.setattr(main,'db',SimpleNamespace(get_live_coupons=AsyncMock(return_value=[]),get_search_results=AsyncMock(return_value=[])))
    monkeypatch.setattr(main,'financial_filter',SimpleNamespace(filter_coupons=lambda *args:([],[])))
    monkeypatch.setattr(main,'smart_advisor',SimpleNamespace(get_advisory=AsyncMock(return_value={})))
    monkeypatch.setattr(main,'emit_ws',lambda *args:None)
    ws=SimpleNamespace(send_text=AsyncMock())
    await main.handle_message('search:feedback',{'searchId':'search','text':'no HDFC'},ws)
    assert task['financial']['blacklisted_banks']==['HDFC']
    assert pending['task']['financial'] is task['financial']


@pytest.mark.asyncio
async def test_locally_waiting_workers_do_not_take_global_browser_slots():
    import asyncio
    from search_engine import Dispatcher
    dispatcher=Dispatcher(None,None,None,None,None,lambda *args:None)
    dispatcher._scrape=AsyncMock()
    blocked=asyncio.Semaphore(0)
    waiters=[asyncio.create_task(dispatcher._run_platform('cleartrip',{},blocked)) for _ in range(3)]
    try:
        await asyncio.sleep(0)
        await asyncio.wait_for(dispatcher._run_platform('cleartrip',{},asyncio.Semaphore(1)),timeout=.5)
        dispatcher._scrape.assert_awaited_once()
    finally:
        for task in waiters:
            task.cancel()
        await asyncio.gather(*waiters,return_exceptions=True)
