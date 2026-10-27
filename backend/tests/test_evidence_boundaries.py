"""Adversarial checks run only with temporary databases/local browser fixtures."""
from copy import deepcopy
from datetime import date,datetime,timedelta,timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from bs4 import BeautifulSoup
from google_source import normalize_result
from intelligence import MarketContext,SuggestionBrain,calibrated_trend,slope_forecast
from deal_feedback import parse_feedback,merge_feedback,available_result
from financial_filter import FinancialFilter
from coupon_harvester import CouponHarvester
from coupon_brute_forcer import CouponBruteForcer
from quote_integrity import check_outputs
from workers.listing_parser import parse_cards
from workers.easemytrip_worker import EaseMyTripWorker
from tests.test_verified_pricing import database,page,TRIP,DAY,LocalCheckout
from tests.test_quote_integrity import quote


def fli_row():
    return dict(price=5000,currency='INR',duration=120,stops=0,legs=[dict(origin='DEL',destination='BOM',
        departure_date=DAY,departure_datetime=DAY+'T08:30:00',arrival_datetime=DAY+'T10:30:00',airline='IndiGo',flight_number='6E-101')])


@pytest.mark.parametrize('change',[{'currency':'USD'},{'currency':None},{'price':True},{'price':float('nan')},
    {'price':-5},{'mixed_cabin':True},{'self_transfer':True},{'stops':1}])
def test_fli_cannot_promote_ambiguous_rows(change):
    assert normalize_result({**fli_row(),**change},TRIP) is None


def test_fli_direction_and_leg_continuity_are_exact():
    source=fli_row()
    assert normalize_result(source,TRIP)['base_price']==5000
    assert normalize_result(source,{**TRIP,'origin':'BOM','destination':'DEL'}) is None
    source['legs'][0]['arrival_datetime']=DAY+'T07:30:00'
    assert normalize_result(source,TRIP) is None


@pytest.mark.asyncio
async def test_list_wrapper_never_combines_two_flights(page):
    await page.set_content('''<div class="wrapper"><div class="card">IndiGo<br>6E-101<br>08:30<br>10:30<br>2h<br>Nonstop<br>₹5000</div>
        <div class="card">Air India<br>AI-202<br>11:30<br>13:30<br>2h<br>Nonstop<br>₹4500</div></div>''')
    rows=await parse_cards(page,'.wrapper,.card')
    assert len(rows)==2 and {(r['airline'],r['base_price']) for r in rows}=={('IndiGo',5000),('Air India',4500)}


def test_grabon_ignores_related_merchants_and_keeps_full_terms():
    soup=BeautifulSoup('''<div class="gc-box"><div class="gcbr" data-code="FLIGHT10">10% off flights</div>
        <div>HDFC credit cards. Valid Till: Oct 31, 2099</div></div>
        <span class="suggested-coupons-boxes"><div class="gc-box su"><div class="gcbr" data-code="AGODA">Other merchant flight deal</div></div></span>
        <div class="gc-box"><div class="gcbr" data-code="HOTEL10">10% off hotel stays</div></div>''','html.parser')
    rows=CouponHarvester.parse_grabon(soup,'cleartrip','https://www.grabon.in/cleartrip-coupons/')
    assert len(rows)==1 and rows[0]['code']=='FLIGHT10' and rows[0]['bank_restriction']=='HDFC'
    assert rows[0]['valid_until']=='2099-10-31'


def test_feedback_excludes_bank_or_product_without_assuming_ownership():
    rules=merge_feedback({},parse_feedback("I don't have HDFC; only UPI; no EMI"))
    assert rules['blacklisted_banks']==['HDFC'] and rules['allowed_card_types']==['UPI']
    special=merge_feedback({},parse_feedback('exclude Flipkart Axis'))
    assert not special['blacklisted_banks'] and special['excluded_card_names']==['FLIPKART AXIS']
    with pytest.raises(ValueError):parse_feedback('maybe cheaper please')
    filters=FinancialFilter()
    assert filters.passes(dict(bank_restriction='HDFC|SBI'),dict(blacklisted_banks=['HDFC']))[0]
    assert not filters.passes(dict(code='EMTUPI'),dict(selected_payment={'method':'CREDIT','banks':[]}))[0]
    assert filters.passes(dict(code='EMTUPI'),dict(selected_payment={'method':'UPI','banks':[]}))[0]


def test_unavailable_verified_payment_is_removed_across_sites():
    first=quote('a','cleartrip',4000,verification='checkout',selected_payment={'method':'CREDIT','banks':['HDFC']})
    second=quote('b','easemytrip',4200,verification='checkout',selected_payment={'method':'UPI','banks':[]})
    rules={'blacklisted_banks':['HDFC']}
    assert not available_result(first,rules,[]) and available_result(second,rules,[])


@pytest.mark.asyncio
async def test_native_emt_applied_state_and_css_currency(page):
    worker=EaseMyTripWorker()
    await page.set_content('''<div class="pr">Grand Total<div><i class="CurrncyCD_Rs" style="display:inline-block;width:8px;height:8px"></i><span id="spnGrndTotal">8,844</span></div></div>
        <div id="divCouponApplied"><div id="spnCouponDisplay">BOOKNOW</div><div ng-click="RemoveCouponeMob()">Remove</div></div>''')
    assert (await worker.read_checkout_total(page))['total']==8844
    assert (await worker.check_coupon_applied(page))==dict(success=True,code='BOOKNOW',error=None)
    assert not await worker.is_at_checkout(page)  # Review is not final payment.
    await page.set_content('<label class="radiocoupns">EMTUPI<input id="rdoCpnEMTUPI" type="radio" checked></label>')
    assert await worker.read_selected_payment(page) is None
    await page.set_content('<div class="pr">Grand Total<span id="spnGrndTotal">8,844</span></div>')
    assert await worker.read_checkout_total(page) is None


@pytest.mark.asyncio
async def test_partial_coupon_testing_is_reported_and_restores_baseline(page):
    await page.set_content('''<div>Total payable ₹5000</div><input id="coupon"><button id="remove">Remove coupon</button>''')
    bf=await CouponBruteForcer(LocalCheckout(),FinancialFilter(),lambda *args:None).brute_force(
        page,[{'code':'ONE'},{'code':'TWO'}],{},'test',budget_seconds=0)
    assert bf['coverage']==dict(eligible=2,tested=0,complete=False)
    assert all(r['status']=='not_tested' for r in bf['all_results']) and bf['best_coupon'] is None


def test_invalid_projection_and_regime_shift_withhold_forecast():
    today=date.today()
    falling=[(today-timedelta(days=99-i),10000-i*100) for i in range(100)]
    assert slope_forecast(falling,today+timedelta(days=7)) is None
    assert calibrated_trend(falling)['forecast_7d'] is None
    # A model which performs worse than last-price persistence must stay silent.
    alternating=[(today-timedelta(days=209-i),5000+(-1)**i*1500) for i in range(210)]
    result=calibrated_trend(alternating)
    assert result['forecast_7d'] is None
    assert result['certainty']['percent'] is None
    stale=[(d-timedelta(days=10),p) for d,p in falling]
    assert calibrated_trend(stale)['forecast_7d'] is None


def test_connecting_quotes_require_segment_identity():
    a=quote('a','google_flights',5000);b=quote('b','cleartrip',5010)
    a['stops']=b['stops']=1
    assert all(v['status']=='uncorroborated' for v in check_outputs([a,b],TRIP).values())


@pytest.mark.asyncio
async def test_brain_no_reverse_count_cabin_time_or_checkout_series_leak(database):
    context=MarketContext(database);await context.initialize()
    for origin,dest,count,cabin,depart,verification,price in [
        ('BOM','DEL',1,'ECONOMY','08:30','listed',100),('DEL','BOM',2,'ECONOMY','08:30','listed',200),
        ('DEL','BOM',1,'BUSINESS','08:30','listed',300),('DEL','BOM',1,'ECONOMY','22:30','listed',400),
        ('DEL','BOM',1,'ECONOMY','08:30','checkout',500)]:
        row=quote('x','cleartrip',price,origin=origin,destination=dest,passenger_count=count,cabin_class=cabin,
            verification=verification,integrity=dict(status='checkout_verified' if verification=='checkout' else 'corroborated'))
        row.update(departure_time=depart,best_coupon_code=None)
        await database.record_quote(row)
    report=await SuggestionBrain(database,context).assess({**TRIP,'preferred_time':'MORNING'},target_price=1000)
    assert report['price'] is None and report['signal']=='MONITOR' and report['forecast']['observed_days']==0

@pytest.mark.parametrize('product',['SBI Simply Save','SBI SimplyClick','ICICI Amazon','HSBC Travel One','Flipkart Axis'])
def test_special_card_requires_selected_product(product):
    from offer_parser import published_offer,card_product
    offer=published_offer('cleartrip','CARD10','Flight discount with '+product+' credit card','https://example.test')
    assert card_product(product)
    bank=offer['bank_restriction'].split('|')[0]
    filters=FinancialFilter()
    assert not filters.passes(offer,{'selected_payment':{'method':'CREDIT','banks':[bank],'label':bank+' credit card'}})[0]
    assert filters.passes(offer,{'selected_payment':{'method':'CREDIT','banks':[bank],'label':product+' credit card'}})[0]


def test_optional_cashback_does_not_restrict_base_coupon():
    from offer_parser import published_offer
    offer=published_offer('cleartrip','CTDOM','25% off flight bookings. Avail 5% additional cashback with Flipkart Axis Bank card.','https://example.test')
    assert offer['bank_restriction'] is None
    assert FinancialFilter().passes(offer,{'blacklisted_banks':['AXIS'],'selected_payment':{'method':'UPI','banks':[],'label':'UPI'}})[0]
    rules=parse_feedback("exclude Flipkart Axis; I don't have HDFC")
    assert rules['blacklisted_banks']==['HDFC']


@pytest.mark.asyncio
async def test_payment_fee_conflict_and_selected_tab(page):
    worker=EaseMyTripWorker()
    html='''<div class="pr">Grand Total<i class="CurrncyCD_Rs" style="display:inline-block;width:8px;height:8px"></i><span id="spnGrndTotal">9743</span></div>
    <div class="pay-m"><ul class="pay-mm"><li class="d4 blk-cls">UPI</li></ul><div class="upi-m">UPI</div><div class="pr-m2">9743</div>
    <div class="n-re">Convenience fee<span ng-bind="ConvenienceFee">449</span></div></div>'''
    await page.set_content(html)
    total=await worker.read_checkout_total(page)
    assert total['total']==9743 and total['fees'][0]['amount']==449 and total['stage']=='payment'
    assert (await worker.read_selected_payment(page))['method']=='UPI'
    await page.set_content(html.replace('class="pr-m2">9743','class="pr-m2">9999'))
    assert await worker.read_checkout_total(page) is None


@pytest.mark.asyncio
async def test_stop_and_time_preferences_guard_output_history_and_nlp(database):
    from text_ai import TextAI
    from compiler import TaskCompiler
    parsed=await TextAI().parse_trip_nlp('DEL to BOM on '+DAY+' morning nonstop for 2 adults')
    assert parsed['maxStops']==0 and parsed['preferredTime']=='MORNING' and parsed['passengerCount']==2
    with pytest.raises(ValueError):
        TaskCompiler(database,None)._validate_trip({**parsed,'maxStops':True})
    row=quote('x','cleartrip',5000,integrity=dict(status='corroborated'));row['best_coupon_code']=None
    row['stops']=1
    assert check_outputs([row],{**TRIP,'max_stops':0})['x']['status']=='flagged'
    await database.record_quote(row)
    assert await database.get_quotes('DEL-BOM',DAY,max_stops=0)==[]
    context=MarketContext(database);await context.initialize()
    report=await SuggestionBrain(database,context).assess({**TRIP,'max_stops':0},current_quotes=[row],target_price=6000)
    assert report['price'] is None
    row.update(stops=0,departure_time='23:00')
    assert check_outputs([row],{**TRIP,'preferred_time':'MORNING'})['x']['status']=='flagged'


def test_offer_route_scope_and_saved_optional_terms():
    from offer_parser import published_offer
    filters=FinancialFilter()
    offer=published_offer('cleartrip','INT10','10% off international flights','https://example.test')
    assert not filters.passes(offer,{'is_domestic':True})[0]
    assert filters.passes(offer,{'is_domestic':False})[0]


@pytest.mark.asyncio
async def test_saved_live_terms_reparsed_without_assuming_card_ownership(database):
    from offer_parser import published_offer
    offer=published_offer('cleartrip','CTDOM','25% off domestic flights. Avail 4% additional cashback with Flipkart Axis Bank credit card.','https://example.test',native=True)
    await database.add_coupon({**offer,'bank_restriction':'AXIS','card_type':'CREDIT'})
    rows=await database.get_live_coupons('cleartrip')
    assert rows[0]['bank_restriction'] is None and rows[0]['card_type']=='ANY'



@pytest.mark.asyncio
async def test_intelligence_replies_keep_request_identity_and_preferences(database,monkeypatch):
    import json,main
    from compiler import TaskCompiler
    context=MarketContext(database);await context.initialize()
    monkeypatch.setattr(main,'db',database)
    monkeypatch.setattr(main,'compiler',TaskCompiler(database,None))
    monkeypatch.setattr(main,'market_context',SimpleNamespace(refresh=AsyncMock()))
    monkeypatch.setattr(main,'suggestion_brain',SuggestionBrain(database,context))
    jobs=[];monkeypatch.setattr(main,'start_job',lambda job:jobs.append(job))
    socket=SimpleNamespace(send_text=AsyncMock())
    payload=dict(requestId='query-one',route='DEL-BOM',date=DAY,passengerCount=1,cabinClass='ECONOMY',preferredTime='MORNING',maxStops=0)
    await main.handle_message('history:get',payload,socket)
    await main.handle_message('brain:get',payload,socket)
    await jobs[0]
    replies=[json.loads(call.args[0]) for call in socket.send_text.call_args_list]
    assert {r['type'] for r in replies}=={'history:data','brain:data'}
    assert all(r['payload']['requestId']=='query-one' for r in replies)
    assert next(r for r in replies if r['type']=='brain:data')['payload']['price'] is None
