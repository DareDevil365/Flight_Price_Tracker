"""9 October follow-up scraper regressions; all pages and processes are fixtures."""
from copy import deepcopy
import pytest
from google_source import normalize_result
from quotes import valid_flights,duration_minutes,search_url
from workers.listing_parser import parse_cards
from workers.google_flights_worker import GoogleFlightsWorker
from tests.test_scraping_audit import page,source,card,TRIP,FARE


def test_unknown_provider_cannot_silently_become_google_search():
    with pytest.raises(ValueError,match='No validated search URL'):search_url('unsupported_custom_website',TRIP)
    assert search_url('google_flights',TRIP).startswith('https://www.google.com/travel/flights?')


@pytest.mark.parametrize('cabin',['BUSINESS','PREMIUM_ECONOMY','FIRST'])
def test_known_source_leg_cabin_disagreement_cannot_be_promoted(cabin):
    row=source();row['legs'][0]['cabin_class']='ECONOMY'
    assert normalize_result(row,{**TRIP,'cabin_class':cabin}) is None
    row['legs'][0]['cabin_class']=cabin
    assert normalize_result(row,{**TRIP,'cabin_class':cabin}) is not None


@pytest.mark.parametrize('offset',['Z','+00:00','+04:00','+06:00'])
def test_domestic_source_offset_must_be_ist(offset):
    row=source()
    for key in ('departure_datetime','arrival_datetime'):row['legs'][0][key]+=offset
    assert normalize_result(row,TRIP) is None


def test_domestic_ist_offset_and_supported_iso_formats_normalize_real_clocks():
    row=source()
    for key in ('departure_datetime','arrival_datetime'):row['legs'][0][key]+='+05:30'
    assert normalize_result(row,TRIP)['departure_time']=='08:00'
    row=source()
    for key in ('departure_datetime','arrival_datetime'):row['legs'][0][key]=row['legs'][0][key].replace('-','')
    assert normalize_result(row,TRIP)['arrival_time']=='10:00'


def test_group_price_must_remain_finite_after_multiplication():
    assert not valid_flights([{**FARE,'base_price':1e308,'price_basis':'per_person'}],{**TRIP,'passenger_count':9})


def test_known_source_leg_and_layover_duration_must_match_its_schedule():
    row=source();row['legs'][0]['duration']=180
    assert normalize_result(row,TRIP) is None
    first=source()['legs'][0];first['destination']='HYD'
    second={**first,'origin':'HYD','destination':'BOM','departure_datetime':'2026-11-21T12:00:00','arrival_datetime':'2026-11-21T14:00:00'}
    row={**source(),'duration':360,'stops':1,'legs':[first,second],'layovers':[dict(airport='HYD',duration=120,change_of_airport=False)]}
    assert normalize_result(row,TRIP) is not None
    row['layovers'][0]['duration']=60
    assert normalize_result(row,TRIP) is None


@pytest.mark.parametrize('duration,minutes',[('1 hr 10 min',70),('01h 10m',70),('45 min',45),('90m',90),('24h',1440),
    ('tax 2h',None),('2h 90m',None),('',None),('0m',None),(None,None)])
def test_full_duration_parser(duration,minutes):
    assert duration_minutes(duration)==minutes


def test_domestic_clock_duration_conflict_rejected_and_overnight_preserved():
    assert not valid_flights([{**FARE,'arrival_time':'08:00','duration':'2h'}],TRIP)
    assert not valid_flights([{**FARE,'arrival_time':'11:00','duration':'2h'}],TRIP)
    assert valid_flights([{**FARE,'departure_time':'22:30','arrival_time':'01:30','duration':'3h'}],TRIP)
    assert valid_flights([{**FARE,'arrival_time':'08:00','duration':'24h'}],TRIP)


@pytest.mark.asyncio
async def test_hidden_total_cannot_certify_group_unit(page):
    await page.set_content(card('₹5000',extra='<span style="display:none">Grand Total 5000</span>'))
    rows=await parse_cards(page,'.card')
    assert rows[0]['price_basis']=='unknown'
    assert not valid_flights(rows,{**TRIP,'passenger_count':2})
    await page.set_content(card('₹5000.50',extra='Grand Total 5000.50'))
    assert valid_flights(await parse_cards(page,'.card'),{**TRIP,'passenger_count':2})[0]['base_price']==5000.5


@pytest.mark.asyncio
async def test_invisible_card_and_invisible_price_are_not_evidence(page):
    await page.set_content(card('₹5000').replace('class="card"','class="card" style="opacity:0"'))
    assert not await parse_cards(page,'.card')
    await page.set_content(card('<div>INR<span class="price" style="visibility:hidden">5000</span></div>'))
    assert not await parse_cards(page,'.card')
    await page.set_content(card('<span style="opacity:0">₹5000</span>'))
    assert not await parse_cards(page,'.card')


@pytest.mark.asyncio
async def test_duplicate_formatted_flight_identity_does_not_look_like_two_legs(page):
    await page.set_content(card('₹5000',extra='6E - 123'))
    assert len(await parse_cards(page,'.card'))==1


@pytest.mark.asyncio
async def test_zero_bound_parent_does_not_hide_a_painted_price_child(page):
    money='<div style="display:contents"><i class="CurrncyCD_Rs" style="display:inline-block;width:8px;height:8px"></i><span price="5000" id="spnPrice1">5000</span></div>'
    await page.set_content(card(money))
    assert (await parse_cards(page,'.card'))[0]['base_price']==5000
    money='<div><i class="CurrncyCD_Rs" style="display:inline-block;width:8px;height:8px"></i><span id="spnPrice1">5000</span></div><div style="display:none"><span id="spnPrice1" price="9999">9999</span></div><div>Lock Price ₹<span id="spnPriceLock1">250</span></div>'
    await page.set_content(card(money))
    assert (await parse_cards(page,'.card'))[0]['base_price']==5000  # Current EMT variant omits price attribute.


@pytest.mark.asyncio
async def test_conflicting_stop_counts_are_rejected_and_minute_duration_supported(page):
    await page.set_content(card('₹5000',extra='1 stop'))
    assert not await parse_cards(page,'.card')
    await page.set_content(card('₹5000',arrival='08:45').replace('2h','45 min'))
    rows=await parse_cards(page,'.card')
    assert rows[0]['duration']=='45 min' and valid_flights(rows,TRIP)


@pytest.mark.asyncio
async def test_dom_counts_disclose_partial_parser_coverage(page):
    await page.set_content(card('₹5000')+card('USD 60'))
    rows=await parse_cards(page,'.card')
    assert rows[0]['source_inventory']['complete'] is False
    assert rows[0]['source_inventory']['candidate_cards']==2
    assert rows[0]['source_inventory']['parsed_rows']==1 and rows[0]['source_inventory']['rejected_cards']==1
    assert rows[0]['connection_airports']==[]  # The route after duration is not a layover.
    await page.set_content(card('₹5000',extra='1h 20m CMB').replace('Nonstop','1 stop'))
    assert (await parse_cards(page,'.card'))[0]['connection_airports']==['CMB']


@pytest.mark.asyncio
async def test_unrelated_google_iso_date_cannot_prove_active_departure(page):
    worker=GoogleFlightsWorker();worker._trip=TRIP
    header='<div>One way<br>1<br>Economy<br>News from 2026-11-21<br>Track prices departing 2027-11-21</div>'
    await page.set_content(header+card('₹5000').replace('class="card"','class="yR1fYc"'))
    with pytest.raises(ValueError,match='departure date'):await worker._parse_via_dom(page)
    await page.set_content('<div>Payment method: UPI</div><div>Total payable ₹5000</div>')
    assert not await worker.is_at_checkout(page)
