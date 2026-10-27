"""Adversarial scraper tests: local DOM/child fixtures never enter live history."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import json
import pytest
import pytest_asyncio
from playwright.async_api import async_playwright
from google_source import normalize_result, fetch_google, leg_airline_label
from quotes import valid_flights
from workers.listing_parser import parse_cards
from workers.google_flights_worker import GoogleFlightsWorker

TRIP=dict(origin='DEL',destination='BOM',departure_date='2026-11-21',passenger_count=1,
          cabin_class='ECONOMY',is_domestic=True,preferred_time='ANY')
FARE=dict(airline='IndiGo',flight_number='6E-123',departure_time='08:00',arrival_time='10:00',
          duration='2h',stops=0,base_price=5000,currency='INR')


def source():
    return dict(price=5000,currency='INR',duration=120,stops=0,legs=[dict(origin='DEL',destination='BOM',
        departure_date=TRIP['departure_date'],departure_datetime='2026-11-21T08:00:00',
        arrival_datetime='2026-11-21T10:00:00',airline='IndiGo',flight_number='6E-123')])


def test_source_airline_enum_name_does_not_override_actual_google_label():
    obsolete_enum=SimpleNamespace(name='QP',value='Air Kenya Aviation')
    leg=SimpleNamespace(airline=obsolete_enum)
    row=SimpleNamespace(primary_airline=obsolete_enum,primary_airline_name='Akasa Air')
    assert leg_airline_label(row,leg)=='Akasa Air'
    row.primary_airline=SimpleNamespace(name='6E')
    assert leg_airline_label(row,leg)=='QP'


@pytest_asyncio.fixture
async def page():
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(headless=True)
        yield await browser.new_page()
        await browser.close()


@pytest.mark.parametrize('item',[None,{},[],42,{'legs':[None]}, {'legs':{'origin':'DEL'}}])
def test_malformed_optional_source_rows_are_individually_rejected(item):
    assert normalize_result(item,TRIP) is None


@pytest.mark.parametrize('field,value',[('departure_datetime','bad-date'),('departure_date','2026-11-22'),
    ('arrival_datetime','2026-11-21T10:00:00+05:30'),('flight_number',''),('flight_number','6E-123-invalid'),('origin','del'),('destination','DEL')])
def test_source_segment_contract(field,value):
    row=source();row['legs'][0][field]=value
    assert normalize_result(row,TRIP) is None


def test_source_total_duration_and_airport_change_cannot_be_ignored():
    assert normalize_result({**source(),'duration':180},TRIP) is None
    assert normalize_result({**source(),'stops':False},TRIP) is None
    assert normalize_result({**source(),'stops':0.0},TRIP) is None
    assert normalize_result({**source(),'airline':{}},TRIP) is not None  # Empty primary name falls back to a valid leg.
    assert normalize_result({**source(),'airline':{'bad':'type'}},TRIP) is None
    assert normalize_result({**source(),'layovers':[dict(change_of_airport=True)]},TRIP) is None
    assert normalize_result(source(),TRIP)['currency']=='INR'


def test_international_local_clock_requires_offsets():
    row=source();row['legs'][0].update(origin='DEL',destination='DXB')
    trip={**TRIP,'destination':'DXB','is_domestic':False}
    assert normalize_result(row,trip) is None
    row['legs'][0].update(departure_datetime='2026-11-21T08:00:00+05:30',arrival_datetime='2026-11-21T08:30:00+04:00')
    assert normalize_result(row,trip)['base_price']==5000


def test_domestic_source_cannot_route_via_foreign_hub():
    row=source();first=row['legs'][0]
    first.update(origin='COK',destination='CMB',arrival_datetime='2026-11-21T10:00:00')
    row.update(stops=1,duration=300,layovers=[dict(airport='CMB',duration=120,change_of_airport=False)])
    row['legs'].append({**first,'origin':'CMB','destination':'BLR','flight_number':'UL-172',
        'departure_datetime':'2026-11-21T12:00:00','arrival_datetime':'2026-11-21T13:00:00'})
    assert normalize_result(row,{**TRIP,'origin':'COK','destination':'BLR'}) is None
    assert valid_flights([{**FARE,'connection_airports':['CMB'],'stops':1}],TRIP)==[]


@pytest.mark.asyncio
async def test_bad_fli_row_does_not_discard_good_inventory():
    process=SimpleNamespace(returncode=0,communicate=AsyncMock(return_value=(json.dumps([None,{'legs':[{}]},source()]).encode(),b'')))
    with patch('google_source.asyncio.create_subprocess_exec',AsyncMock(return_value=process)):
        assert len(await fetch_google(TRIP))==1


@pytest.mark.parametrize('change',[{'currency':'USD'},{'currency':None},{'currency':'usd'},
    {'departure_date':'2026-11-22'},{'passenger_count':2},{'cabin_class':'BUSINESS'},
    {'nearby_airport':True,'destination':'BOM'},{'nearby_airport':True,'origin':'DEL'}])
def test_explicit_scope_disagreements_fail_validation(change):
    assert valid_flights([{**FARE,**change}],TRIP)==[]


def test_malformed_listing_does_not_poison_valid_batch():
    assert valid_flights([None,[],123,deepcopy(FARE)],TRIP)==[FARE]


def test_group_normalization_is_idempotent_and_fare_conditions_remain_distinct():
    trip={**TRIP,'passenger_count':2}
    once=valid_flights([{**FARE,'price_basis':'per_person'}],trip)
    assert once[0]['base_price']==10000
    assert valid_flights(once,trip)[0]['base_price']==10000
    families=[{**FARE,'fare_family':'Saver'},{**FARE,'fare_family':'Flex','base_price':5500}]
    assert len(valid_flights(families,TRIP))==2


def card(price,departure='08:00',arrival='10:00',extra=''):
    return f'<div class="card">IndiGo<br>6E-123<br>{departure}<br>{arrival}<br>2h<br>DEL–BOM<br>Nonstop<br>{price}<br>{extra}</div>'


@pytest.mark.asyncio
@pytest.mark.parametrize('money',['₹5,00','₹5000.999','₹5,000 ₹6,000','USD 60 / ₹5,000',
    '<span class="price">5,000</span>','<span>INR</span><span class="price">5,000 and 6,000</span>'])
async def test_ambiguous_or_malformed_dom_amounts_are_rejected(page,money):
    await page.set_content(card(money))
    assert await parse_cards(page,'.card')==[]


@pytest.mark.asyncio
async def test_struck_fare_does_not_replace_discounted_fare(page):
    await page.set_content(card('<s>₹9,999</s><br><span>₹4,999</span>'))
    assert (await parse_cards(page,'.card'))[0]['base_price']==4999
    await page.set_content(card('<div>INR<br><del><span class="price">9,999</span></del><span class="actual-price">4,999</span></div>'))
    assert (await parse_cards(page,'.card'))[0]['base_price']==4999
    await page.set_content(card('<div>INR<br><span class="price" style="display:none">9,999</span><span class="actual-price">4,999</span></div>'))
    assert (await parse_cards(page,'.card'))[0]['base_price']==4999


@pytest.mark.asyncio
async def test_same_clock_arrival_and_invalid_am_pm(page):
    await page.set_content(card('₹5000',departure='08:00',arrival='08:00'))
    assert len(await parse_cards(page,'.card'))==1
    await page.set_content(card('₹5000',departure='13:00 PM'))
    assert valid_flights(await parse_cards(page,'.card'),TRIP)==[]


@pytest.mark.asyncio
async def test_multi_adult_conflicting_units_are_unknown(page):
    await page.set_content(card('₹5000',extra='per adult<br>Total fare'))
    rows=await parse_cards(page,'.card')
    assert rows[0]['price_basis']=='unknown'
    assert valid_flights(rows,{**TRIP,'passenger_count':2})==[]


@pytest.mark.asyncio
async def test_large_nested_inventory_preserves_each_leaf(page):
    await page.set_content('<div class="wrapper">'+''.join(card('₹5000') for _ in range(100))+'</div>')
    assert len(await parse_cards(page,'.wrapper,.card'))==100


@pytest.mark.asyncio
async def test_google_must_confirm_airports_on_card(page):
    worker=GoogleFlightsWorker();worker._trip=TRIP
    header='<div>One way<br>1<br>Economy<br>Track prices departing 2026-11-21</div>'
    await page.set_content(header+card('₹5000').replace('class="card"','class="yR1fYc"').replace('DEL–BOM','DEL–NMI'))
    assert await worker._parse_via_dom(page)==[]
    await page.set_content(header+card('₹5000').replace('class="card"','class="yR1fYc"'))
    assert len(await worker._parse_via_dom(page))==1
