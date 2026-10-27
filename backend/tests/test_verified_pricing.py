"""Regression tests for the live app, using temporary databases and local pages."""
import asyncio
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
import pytest
import pytest_asyncio
from playwright.async_api import async_playwright
from booking_advisor import PricePredictor
from compiler import TaskCompiler
from coupon_db import CouponDB
from coupon_brute_forcer import CouponBruteForcer
from financial_filter import FinancialFilter
from quotes import valid_flights, search_url, utc_now
from workers.cleartrip_worker import CleartripWorker
from workers.google_flights_worker import GoogleFlightsWorker
from workers.easemytrip_worker import EaseMyTripWorker
from search_engine import Dispatcher

DAY = (date.today()+timedelta(days=30)).isoformat()
TRIP = dict(origin='DEL', destination='BOM', departure_date=DAY,
            passenger_count=1, cabin_class='ECONOMY', preferred_time='ANY', is_domestic=True)

@pytest_asyncio.fixture
async def database(tmp_path):
    db = CouponDB(tmp_path/'test.db')
    await db.initialize()
    yield db
    await db.close()

@pytest_asyncio.fixture
async def page():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        # Local provider-origin fixtures exercise the real origin gate without
        # a production bypass or a network request to the provider.
        await page.route('https://www.cleartrip.com/local-test-fixture',lambda route:route.fulfill(status=200,body='<html><body></body></html>',content_type='text/html'))
        await page.goto('https://www.cleartrip.com/local-test-fixture')
        yield page
        await browser.close()

@pytest.mark.parametrize('platform', ['makemytrip','easemytrip','cleartrip','google_flights'])
def test_search_urls_preserve_adults_cabin_and_date(platform):
    url = search_url(platform, {**TRIP, 'passenger_count':3, 'cabin_class':'BUSINESS'})
    from urllib.parse import unquote_plus
    url = unquote_plus(url)
    assert 'DEL' in url and 'BOM' in url
    assert '3' in url
    assert ('BUSINESS'.lower() in url.lower() or 'cabinClass=B' in url or 'cbn=2' in url)
    assert ('2026' in url or str(date.fromisoformat(DAY).year) in url)
    if platform=='cleartrip':
        assert 'depart_date=' in url and 'class=Business' in url and 'childs=0' in url

def test_fare_validation_no_floor_guess_or_nearby_airport():
    flight = dict(airline='IndiGo',flight_number='6E-101',departure_time='08:30',arrival_time='10:30',stops=0,base_price=900)
    assert valid_flights([flight],TRIP)[0]['base_price']==900
    for change in [dict(base_price=float('nan')),dict(base_price=0),dict(departure_time='26:45'),dict(destination='NMI'),dict(nearby_airport=True)]:
        assert not valid_flights([{**flight,**change}],TRIP)
    assert not valid_flights([flight],{**TRIP,'passenger_count':3})
    assert valid_flights([{**flight,'price_basis':'per_person'}],{**TRIP,'passenger_count':3})[0]['base_price']==2700
    assert not valid_flights([flight],{**TRIP,'preferred_time':'NIGHT'})

@pytest.mark.parametrize('update', [{'origin':'bom'}, {'departureDate':(date.today()-timedelta(days=1)).isoformat()}, {'passengerCount':0}, {'tripType':'round_trip','returnDate':None}])
def test_trip_validation(update):
    with pytest.raises(ValueError):
        TaskCompiler(None,None)._validate_trip({'origin':'DEL','destination':'BOM','departureDate':DAY,**update})

def test_expired_emi_excluded_unknown_bank_is_conditional():
    filter = FinancialFilter()
    for coupon in [dict(valid_until='2000-01-01'),dict(description='EMI offer')]:
        assert not filter.passes(coupon,{})[0]
    assert filter.passes({'bank_restriction':'SBI'},{'whitelisted_banks':['SBI']})[0]
    assert filter.passes({'bank_restriction':'SBI'},{})[0]
    assert not filter.passes({'bank_restriction':'SBI'},{'blacklisted_banks':['SBI']})[0]

@pytest.mark.asyncio
async def test_listing_parser_current_google_and_emt_layouts(page):
    await page.set_content('''<div class="yR1fYc">8:40 PM<span style="display:none">8:40 PM on Sat</span><br>11:10 PM<br>Air India Express<br>2 hr 30 min<br>DEL–BOM<br>Nonstop<br>₹6,610</div>''')
    rows = valid_flights(await GoogleFlightsWorker()._parse_via_dom(page),TRIP)
    assert len(rows)==1 and rows[0]['departure_time']=='20:40' and rows[0]['arrival_time']=='23:10'
    assert rows[0]['duration']=='2 hr 30 min' and rows[0]['base_price']==6610
    await page.set_content('''<div class="main-bo-lis">IndiGo<br>6E - 101<br>08:30<br>New Delhi<br>2h 15m<br>Non-stop<br>10:45<br>Mumbai<br><div><i class="CurrncyCD_Rs" style="display:inline-block;width:8px;height:8px"></i><span price="6000" id="spnPrice22">6,000</span></div><br>BOOK NOW<br>Lock Price ₹<br>300<br>BOOKNOW: Get Rs.450 off</div>''')
    rows = valid_flights(await EaseMyTripWorker()._parse_via_dom(page),TRIP)
    assert len(rows)==1 and rows[0]['base_price']==6000

@pytest.mark.asyncio
async def test_no_guessed_total_or_false_coupon_success(page):
    worker = CleartripWorker()
    await page.set_content('<div>Save ₹1,000 on credit cards</div><div>Total fare ₹5,000</div>')
    assert not await worker.is_at_checkout(page)
    assert not (await worker.check_coupon_applied(page))['success']
    with pytest.raises(ValueError):
        await worker.parse_current_price(page)
    await page.set_content('<div>Payment methods</div><div>Grand total<br>USD 80</div>')
    with pytest.raises(ValueError):
        await worker.parse_current_price(page)
    await page.set_content('<div>Payment method</div><div>Convenience fee ₹350</div><div>Total payable<br>₹5,350.50</div>')
    assert await worker.is_at_checkout(page)
    data = await worker.read_checkout_total(page)
    assert data['total']==5350.50 and data['fees'][0]['amount']==350
    await page.set_content('<div>Grand total ₹1000</div><div>Amount payable ₹1200</div>')
    assert await worker.read_checkout_total(page) is None

class LocalCheckout(CleartripWorker):
    async def enter_coupon_code(self,page,code):
        await page.fill('#coupon',code)
    async def click_apply_coupon(self,page):
        await page.click('#apply')
    async def clear_coupon_field(self,page):
        await page.click('#remove')
    async def get_coupon_validation_text(self,page):
        return ''

@pytest.mark.asyncio
async def test_actual_fees_and_coupon_winner_restored(page):
    await page.set_content('''<div>Payment method: UPI</div><div>Convenience fee ₹350</div>
    <div>Total payable <span id="total">₹5,350</span></div><input id="coupon"><button id="apply">Apply</button>
    <button id="remove">Remove coupon</button><div class="coupon-message" id="message"></div>
    <script>document.querySelector('#apply').onclick=()=>{const c=document.querySelector('#coupon').value;
    document.querySelector('#total').textContent=c==='BEST'?'₹4,350':c==='LESS'?'₹4,950':'₹5,350';
    document.querySelector('#message').textContent=c==='BEST'||c==='LESS'?'Coupon applied successfully':'Invalid coupon';};
    document.querySelector('#remove').onclick=()=>{document.querySelector('#total').textContent='₹5,350';document.querySelector('#coupon').value='';document.querySelector('#message').textContent='';};</script>''')
    result = await CouponBruteForcer(LocalCheckout(),FinancialFilter(),lambda *args:None).brute_force(
        page,[{'code':'BEST'},{'code':'LESS'},{'code':'EXPIRED','valid_until':'2000-01-01'}],{},'test')
    assert result['best_price']==4350 and result['best_coupon']=='BEST' and result['savings']==1000
    assert await page.input_value('#coupon')=='BEST'
    assert await LocalCheckout().parse_current_price(page)==4350

@pytest.mark.asyncio
async def test_quote_history_and_advice_do_not_use_seeded_prices(database):
    await database.log_price('DEL-BOM',DAY,'IndiGo','6E-101',1,'mock',source='synthetic')
    advisor = PricePredictor(database)
    initial = await advisor.predict('DEL-BOM',DAY)
    assert initial['current_price'] is None and initial['decision']['signal']=='MONITOR'
    assert initial['decision']['confidence'] is None and initial['forecast']['price_7d'] is None
    row=dict(platform='cleartrip',airline='IndiGo',flight_number='6E-101',departure_date=DAY,departure_time='08:30',stops=0,
        final_price=6000,best_coupon_code=None,savings_breakdown=dict(origin='DEL',destination='BOM',passenger_count=1,cabin_class='ECONOMY',verification='checkout',observed_at=utc_now(),integrity={'status':'checkout_verified'}))
    await database.record_quote(row)
    await database.record_quote({**row,'final_price':1000,'savings_breakdown':{**row['savings_breakdown'],'verification':'listed'}})
    refreshed=await advisor.predict('DEL-BOM',DAY)
    assert refreshed['current_price'] is None
    assert refreshed['data_freshness']['archived_checkout_receipts']==1
    assert not await database.get_quotes('DEL-BOM',DAY,2,'ECONOMY')
    assert not await database.get_quotes('DEL-BOM',(date.today()+timedelta(days=31)).isoformat())

@pytest.mark.asyncio
async def test_per_search_concurrency_and_cancellation():
    events=[]
    dispatcher=Dispatcher(None,None,None,None,None,lambda kind,payload:events.append((kind,payload)))
    active=peak=0
    async def scrape(platform,task):
        nonlocal active,peak
        active+=1; peak=max(active,peak)
        try: await asyncio.sleep(.03)
        finally: active-=1
    dispatcher._scrape=scrape
    task={'search_id':'test','cloak':{'max_concurrent_bots':1}}
    limit=asyncio.Semaphore(1)
    await asyncio.gather(*(dispatcher._run_platform(p,task,limit) for p in ['a','b','c']))
    assert peak==1
    running=asyncio.create_task(asyncio.sleep(60)); dispatcher._active_searches['test']=running
    await dispatcher.cancel_search('test')
    assert running.cancelled()

@pytest.mark.asyncio
async def test_checkout_identity_rejects_another_date_or_flight(page):
    worker = CleartripWorker()
    quote = dict(flight_number='6E-101',airline='IndiGo',stops=0,departure_time='08:30',arrival_time='10:30',departure_date='2026-11-07',savings_breakdown={'origin':'DEL','destination':'BOM'})
    for text, expected in [('6E - 101 08:30 7 Nov 2026',True),
                           ('6E101 08:30 27 Nov 2026',False),
                           ('6E101 08:30 7 Nov 2027',False),
                           ('6E1010 08:30 2026-11-07',False),
                           ('6E101 09:30 2026-11-07',False)]:
        await page.set_content('<section aria-label="Selected flight">DEL to BOM IndiGo Nonstop '+text+' 10:30</section>')
        assert await worker.confirm_checkout_flight(page,quote) is expected

@pytest.mark.asyncio
async def test_checkout_verification_persists_only_observed_total(page,database):
    worker = LocalCheckout()
    await page.set_content(f'''<section aria-label="Selected flight">DEL to BOM IndiGo 6E-101 Nonstop 08:30 10:30 {DAY}</section><div>1 Adult</div><div>Economy</div><div>Payment method: UPI</div>
        <div>Platform fee ₹350</div><div>Total payable ₹5,350</div><input id="coupon">
        <button id="remove">Remove coupon</button>''')
    quote = dict(id='quote',search_id='search',platform='cleartrip',flight_number='6E-101',
        airline='IndiGo',departure_time='08:30',arrival_time='10:30',departure_date=DAY,stops=0,
        base_price=5000,final_price=5000,effective_price=5000,savings_breakdown=dict(
            origin='DEL',destination='BOM',passenger_count=1,cabin_class='ECONOMY',verification='listed'))
    sessions=SimpleNamespace(_sessions={'session':dict(page=page,context=SimpleNamespace(pages=[page]))})
    events=[]
    dispatcher=Dispatcher(database,sessions,FinancialFilter(),None,None,lambda *args:events.append(args))
    dispatcher._pending_checkouts['session']=dict(worker=worker,task=dict(trip=TRIP,financial={},search_id='search'),
        quote=quote,lock=asyncio.Lock())
    result=await dispatcher.verify_checkout('session')
    assert result['final_price']==5350 and result['savings']==0
    assert result['savings_breakdown']['verification']=='checkout'
    assert result['savings_breakdown']['fee_breakdown'][0]['amount']==350
    saved=await database.get_search_results('search')
    assert len(saved)==1 and saved[0]['final_price']==5350
    assert len(await database.get_quotes('DEL-BOM',DAY))==1
    await page.set_content(f'<section aria-label="Selected flight">DEL to BOM IndiGo 6E-101 Nonstop 08:30 10:30 {DAY}</section><div>3 Adults</div><div>Economy</div><div>Payment method: UPI</div><div>Total payable ₹5,350</div>')
    with pytest.raises(ValueError,match='adult count and cabin'):
        await dispatcher.verify_checkout('session')

@pytest.mark.asyncio
async def test_settings_and_watchlists_persist_without_real_profile(database,tmp_path,monkeypatch):
    import json
    import main
    messages=[]
    class Socket:
        async def send_text(self,text): messages.append(json.loads(text))
    socket=Socket()
    monkeypatch.setattr(main,'db',database)
    monkeypatch.setattr(main,'compiler',TaskCompiler(database,None))
    monkeypatch.setattr(main,'CONFIG_DIR',tmp_path/'config')
    profile={'whitelistedBanks':['SBI'],'blockEmi':True}
    await main.handle_message('settings:update',profile,socket)
    await main.handle_message('settings:get',{},socket)
    assert messages[-1]['payload']==profile
    await main.handle_message('watchlist:add',dict(origin='DEL',destination='BOM',departure_date=DAY,
        target_price=5000,check_frequency='daily'),socket)
    items=messages[-1]['payload']['items']
    assert len(items)==1 and items[0]['id']
    await main.handle_message('watchlist:remove',{'watchId':items[0]['id']},socket)
    assert messages[-1]['payload']['items']==[]

@pytest.mark.asyncio
async def test_provider_ignored_date_and_cabin_are_rejected(page):
    cleartrip=CleartripWorker()
    cleartrip._trip=TRIP
    cleartrip._confirmed_criteria={'from':'DEL','to':'BOM','depart_date':'08/10/2026','adults':'1','class':'Economy'}
    with pytest.raises(ValueError,match='did not confirm'):
        await cleartrip._parse_via_dom(page)
    cleartrip._confirmed_criteria['depart_date']=date.fromisoformat(DAY).strftime('%d/%m/%Y')
    assert await cleartrip._parse_via_dom(page)==[]
    await page.set_content(f'''<input id="ddate" value="{date.fromisoformat(DAY):%d/%m/%Y}">
        <input id="FromSector_show" value="NewDelhi(DEL)"><input id="Editbox13_show" value="Bombay(BOM)">
        <select id="optClass"><option selected>Economy</option></select><div>1 Traveller</div>''')
    emt=EaseMyTripWorker()
    emt._trip=TRIP
    assert await emt._parse_via_dom(page)==[]
    emt._trip={**TRIP,'cabin_class':'BUSINESS'}
    with pytest.raises(ValueError,match='did not confirm'):
        await emt._parse_via_dom(page)
