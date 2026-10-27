"""Navigation/coupon adversarial tests use local fixtures, never live carts."""
import asyncio
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from coupon_brute_forcer import CouponBruteForcer
from financial_filter import FinancialFilter
from offer_parser import published_offer
from search_engine import Dispatcher
from session_manager import SessionManager
from tests.test_verified_pricing import page,TRIP,DAY,LocalCheckout
from tests.test_quote_integrity import quote
from workers.cleartrip_worker import CleartripWorker
from workers.easemytrip_worker import EaseMyTripWorker


def test_native_multiline_terms_keep_positive_payment_requirement():
    offer=published_offer('cleartrip','BANKSAVE',
        'Flight discount on ICICI net banking\nNot valid on credit cards or UPI','https://example.test',native=True)
    rules={'selected_payment':{'method':'UPI','banks':[]}}
    assert FinancialFilter().assess(offer,rules).status=='ineligible'
    rules['selected_payment']={'method':'NET_BANKING','banks':['ICICI']}
    assert FinancialFilter().assess(offer,rules).status=='eligible'
    rules['selected_payment']={'method':'NET_BANKING','banks':['HDFC']}
    assert FinancialFilter().assess(offer,rules).status=='ineligible'


def test_truncated_terms_are_not_complete_eligibility_evidence():
    offer=published_offer('cleartrip','LONGTERMS','Flight discount. '+('General published terms '*100),
        'https://example.test',native=True)
    assert offer['eligibility_unconfirmed']
    assert FinancialFilter().assess(offer,{'selected_payment':{'method':'UPI'}}).status=='unknown'


@pytest.mark.parametrize('terms,count,status',[
    ('Flight discount for 2 passengers only',3,'ineligible'),
    ('Flight discount for 2 passengers only',2,'eligible'),
    ('Flight discount for 2 or more passengers',3,'eligible'),
    ('Flight discount for new customers',1,'unknown'),
    ('Flight discount on first transaction',1,'unknown'),
])
def test_account_and_passenger_restrictions(terms,count,status):
    assert FinancialFilter().assess({'code':'SAVE','description':terms},
        {'passenger_count':count,'selected_payment':{'method':'UPI'}}).status==status


class StatefulCart:
    platform_id='cleartrip'
    def __init__(self,*,ignore_first_removal=False,fail_winner=False,pause_first_removal=False):
        self.applied='ORIG';self.input='ORIG';self.total=5800
        self.clear_count=0;self.best_count=0
        self.ignore_first_removal=ignore_first_removal
        self.fail_winner=fail_winner;self.pause_first_removal=pause_first_removal
        self.entered=asyncio.Event()
    async def parse_current_price(self,page):return self.total
    async def get_applied_coupon_code(self,page):return self.applied
    async def check_coupon_applied(self,page):return {'success':bool(self.applied),'code':self.applied}
    async def get_coupon_validation_text(self,page):return ''
    async def enter_coupon_code(self,page,code):self.input=code
    async def click_apply_coupon(self,page):
        self.applied=self.input
        self.total={'ORIG':5800,'BEST':5000}.get(self.input,6000)
        if self.input=='BEST':
            self.best_count+=1
            if self.fail_winner and self.best_count>1:raise ValueError('Winner reapplication failed')
    async def clear_coupon_field(self,page):
        self.clear_count+=1
        if self.ignore_first_removal and self.clear_count==1:return
        self.applied=None;self.input='';self.total=6000
        if self.pause_first_removal and self.clear_count==1:
            self.entered.set()
            await asyncio.Future()


@pytest.fixture
def fast_coupon_waits(monkeypatch):
    async def no_delay(seconds):pass
    monkeypatch.setattr('coupon_brute_forcer.asyncio.sleep',no_delay)


@pytest.mark.asyncio
async def test_failed_coupon_removal_cannot_be_a_discounted_baseline(fast_coupon_waits):
    cart=StatefulCart(ignore_first_removal=True)
    runner=CouponBruteForcer(cart,FinancialFilter(),lambda *args:None)
    with pytest.raises(ValueError,match='not removed'):
        await runner.brute_force(None,[{'code':'ORIG'},{'code':'BEST'}],{},'isolated')
    assert cart.applied=='ORIG' and cart.total==5800


@pytest.mark.asyncio
async def test_final_winner_failure_restores_original_coupon_and_total(fast_coupon_waits):
    cart=StatefulCart(fail_winner=True)
    runner=CouponBruteForcer(cart,FinancialFilter(),lambda *args:None)
    with pytest.raises(ValueError,match='Winner reapplication failed'):
        await runner.brute_force(None,[{'code':'ORIG'},{'code':'BEST'}],{},'isolated')
    assert cart.applied=='ORIG' and cart.total==5800


@pytest.mark.asyncio
async def test_cancellation_during_initial_removal_restores_original_cart(fast_coupon_waits):
    cart=StatefulCart(pause_first_removal=True)
    runner=CouponBruteForcer(cart,FinancialFilter(),lambda *args:None)
    task=asyncio.create_task(runner.brute_force(None,[{'code':'ORIG'},{'code':'BEST'}],{},'isolated'))
    await asyncio.wait_for(cart.entered.wait(),2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):await task
    assert cart.applied=='ORIG' and cart.total==5800


@pytest.mark.asyncio
async def test_expired_session_cannot_verify_before_periodic_cleanup():
    sessions=SimpleNamespace(_sessions={'expired':{'expires_at':datetime.now(timezone.utc)-timedelta(seconds=1)}},
        close_session=AsyncMock())
    engine=Dispatcher(None,sessions,None,None,None,lambda *args:None)
    engine._pending_checkouts['expired']={'lock':asyncio.Lock()}
    with pytest.raises(ValueError,match='expired'):await engine.verify_checkout('expired')
    sessions.close_session.assert_awaited_once_with('expired')
    assert 'expired' not in engine._pending_checkouts


@pytest.mark.asyncio
async def test_handoff_does_not_extend_an_expired_session():
    events=[];manager=SessionManager(lambda *args:events.append(args))
    context=SimpleNamespace(close=AsyncMock());browser=SimpleNamespace(close=AsyncMock())
    manager._sessions['expired']={'status':'READY_FOR_HANDOFF','expires_at':datetime.now(timezone.utc)-timedelta(seconds=1),
        'context':context,'browser':browser}
    try:
        await manager.handoff_to_user('expired')
        assert events[-1][1]['status']=='failed'
        context.close.assert_awaited_once();browser.close.assert_awaited_once()
    finally:await manager.cleanup_all()


@pytest.mark.asyncio
async def test_new_booking_cannot_evict_running_coupon_verification():
    row=quote('selected','cleartrip',5000);row['session_id']=None
    sessions=SimpleNamespace(_sessions={})
    database=SimpleNamespace(get_search_results=AsyncMock(return_value=[row]))
    engine=Dispatcher(database,sessions,None,None,None,lambda *args:None)
    engine._search_tasks['search']={'trip':TRIP}
    for index in range(3):
        lock=asyncio.Lock();await lock.acquire()
        engine._pending_checkouts[str(index)]={'lock':lock}
    with pytest.raises(ValueError,match='All booking sessions'):
        await engine.prepare_checkout('search','selected')
    assert len(engine._pending_checkouts)==3


@pytest.mark.asyncio
async def test_coupon_feedback_does_not_read_unrelated_payment_labels(page):
    worker=CleartripWorker()
    await page.set_content('<div>HDFC credit card</div><div class="coupon-card">Unrelated card offer valid only on SBI credit cards</div><div class="coupon-message">Offer valid only on UPI</div>')
    assert await worker.get_coupon_validation_text(page)=='Offer valid only on UPI'
    await page.set_content('<div class="coupon-message">Coupon OTHER applied successfully</div>')
    assert (await worker.check_coupon_applied(page))['code']=='OTHER'


@pytest.mark.asyncio
async def test_coupon_apply_never_clicks_generic_payment_submit(page):
    await page.set_content('''<form><input placeholder="Coupon code"><button id="payment" type="button">Submit</button></form>
        <script>window.paymentClicked=false;document.querySelector('#payment').onclick=()=>window.paymentClicked=true;</script>''')
    with pytest.raises(ValueError,match='Apply coupon control'):await CleartripWorker().click_apply_coupon(page)
    assert not await page.evaluate('window.paymentClicked')


@pytest.mark.asyncio
async def test_semantic_coupon_fill_emits_one_input_event_and_never_interpolates_data(page):
    worker=CleartripWorker()
    await page.set_content('''<input name="couponSpecial"><script>window.inputEvents=0;
        document.querySelector('input').addEventListener('input',()=>window.inputEvents++);</script>''')
    await worker.enter_coupon_code(page,'NATIVE500')
    assert await page.input_value('input')=='NATIVE500'
    assert await page.evaluate('window.inputEvents')==1
    with pytest.raises(ValueError,match='Malformed coupon'):
        await worker.enter_coupon_code(page,"SAVE'; window.injected=true; //")
    assert not await page.evaluate('Boolean(window.injected)')


def test_flexible_lookup_quote_has_exact_scope_without_invented_corroboration():
    engine=Dispatcher(None,None,None,None,None,lambda *args:None)
    row=engine._listed_quote('google_flights',{'search_id':'isolated','trip':{**TRIP,'max_stops':0}},
        dict(flight_number='6E-101',airline='IndiGo',departure_time='08:30',arrival_time='10:30',duration='2h',stops=0,base_price=5000),
        'https://example.test')
    meta=row['savings_breakdown']
    assert (meta['origin'],meta['destination'],row['departure_date'])==('DEL','BOM',DAY)
    assert meta['passenger_count']==1 and meta['cabin_class']=='ECONOMY'
    assert meta['max_stops']==0 and meta['verification']=='listed' and meta['currency']=='INR'
    assert meta['observed_at'] and meta['integrity']['status']=='pending' and meta['checkout_price'] is None


@pytest.mark.parametrize('url,valid',[
    ('https://www.cleartrip.com/payment',True),('https://flight.cleartrip.com/payment',True),
    ('https://evilcleartrip.com/payment',False),('https://cleartrip.com.evil.test/payment',False),
    ('http://www.cleartrip.com/payment',False),('https://gateway.example.test/payment',False),
])
def test_payment_evidence_requires_exact_https_provider_domain(url,valid):
    assert CleartripWorker().is_provider_page(SimpleNamespace(url=url)) is valid


@pytest.mark.asyncio
async def test_unrelated_popup_cannot_verify_matching_total():
    worker=CleartripWorker()
    popup=SimpleNamespace(url='https://unrelated.example.test/payment')
    sessions=SimpleNamespace(_sessions={'session':dict(page=popup,context=SimpleNamespace(pages=[popup]))})
    engine=Dispatcher(None,sessions,None,None,None,lambda *args:None)
    engine._pending_checkouts['session']=dict(worker=worker,task={},quote={},lock=asyncio.Lock())
    with pytest.raises(ValueError,match='outside the expected HTTPS'):await engine.verify_checkout('session')


@pytest.mark.asyncio
async def test_current_native_coupon_restriction_precedes_stale_duplicate(page,fast_coupon_waits):
    worker=LocalCheckout()
    worker.scrape_onsite_coupons=AsyncMock(return_value=[{'code':'SAMECODE','description':'Flight discount only on UPI'}])
    worker.enter_coupon_code=AsyncMock()
    await page.set_content(f'''<section aria-label="Selected flight">DEL to BOM IndiGo 6E-101 Nonstop 08:30 10:30 {DAY}</section><div>1 Adult</div><div>Economy</div>
        <div>Payment method: ICICI credit card</div><div>Total payable ₹5350</div>
        <input id="coupon"><button id="remove">Remove coupon</button>''')
    row=quote('native','cleartrip',5000)
    sessions=SimpleNamespace(_sessions={'session':dict(page=page,context=SimpleNamespace(pages=[page]))})
    db=SimpleNamespace(get_live_coupons=AsyncMock(return_value=[{'code':'SAMECODE','description':'Flight discount'}]))
    engine=Dispatcher(db,sessions,FinancialFilter(),None,None,lambda *args:None)
    engine._pending_checkouts['session']=dict(worker=worker,task={'trip':TRIP,'financial':{},'search_id':'isolated'},quote=row,lock=asyncio.Lock())
    verified=await engine.verify_checkout('session',persist=False)
    assert verified['best_coupon_code'] is None and verified['final_price']==5350
    assert verified['all_tested_coupons'][0]['status']=='pre_filtered'
    worker.enter_coupon_code.assert_not_awaited()


@pytest.mark.asyncio
async def test_emt_readiness_uses_current_visible_price_not_hidden_attribute_span(page):
    await page.set_content('''<div class="main-bo-lis">IndiGo 6E-6944<br>05:00<br>00h55m<br>Non-stop<br>05:55
        <div><i class="CurrncyCD_Rs" style="display:inline-block;width:8px;height:8px"></i>
        <span id="spnPrice6">4,703</span><span id="spnPrice6" price="4903" style="display:none">4,903</span></div></div>''')
    assert await page.locator('[price][id^="spnPrice"]').count()==1
    assert not await page.locator('[price][id^="spnPrice"]').is_visible()
    await asyncio.wait_for(EaseMyTripWorker().execute_search(page),1)


@pytest.mark.asyncio
@pytest.mark.parametrize('price_markup',[
    '<div class="coupon-card">Save ₹500<span class="price">₹500</span></div>',
    '<div><span class="price">USD 50</span></div>',
    '<div><span class="price" style="text-decoration:line-through">₹4703</span></div>',
    '<div><span class="price" style="display:none">₹4703</span></div>',
    '<div><span id="spnPriceLock1">₹179</span></div>',
])
async def test_emt_readiness_does_not_use_coupon_foreign_hidden_or_lock_amount(page,price_markup):
    await page.set_content('<div class="main-bo-lis">IndiGo 6E-6944<br>05:00<br>Non-stop<br>05:55'+price_markup+'</div>')
    assert not await page.evaluate(EaseMyTripWorker.LISTINGS_READY)
