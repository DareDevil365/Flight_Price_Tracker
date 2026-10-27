"""Transient local pages exercise selection and bounded response observers."""
import gc
import weakref
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from workers.base_worker import BaseWorker, _same_listing
from workers.cleartrip_worker import CleartripWorker
from workers.listing_parser import parse_cards
from workers.makemytrip_worker import MakeMyTripWorker
from tests.test_verified_pricing import page


def card(number='101',arrival='10:30',extra_button=False):
    extra='<button>View fare</button>' if extra_button else ''
    return f'''<div class="flight-card"><p>IndiGo 6E-{number}</p><p>08:30</p><p>{arrival}</p>
        <p>DEL-BOM</p><p>Nonstop</p><p>₹5,350</p>
        <button onclick="window.selected='{number}'">Book now</button>{extra}</div>'''


def worker():
    instance=CleartripWorker()
    async def current(page):
        return await parse_cards(page,'.flight-card')
    instance._parse_via_dom=current
    return instance


@pytest.mark.asyncio
async def test_stale_position_selector_does_not_click_reordered_flight(page):
    await page.set_content('<div id="list">'+card('101')+card('202')+'</div>')
    instance=worker()
    chosen=(await instance._parse_via_dom(page))[0]
    chosen['selector']='.flight-card:nth-child(1)'
    await page.evaluate("const list=document.querySelector('#list');list.prepend(list.lastElementChild)")
    await BaseWorker.select_flight(instance,page,chosen)
    assert await page.evaluate('window.selected')=='101'


@pytest.mark.asyncio
async def test_missing_selector_uses_unique_complete_summary_not_first_clock_match(page):
    await page.set_content(card('101','10:30')+card('202','11:30'))
    instance=worker()
    chosen=(await instance._parse_via_dom(page))[1]
    chosen.pop('selector');chosen.pop('flight_number')
    await BaseWorker.select_flight(instance,page,chosen)
    assert await page.evaluate('window.selected')=='202'


@pytest.mark.asyncio
async def test_duplicate_same_itinerary_cannot_silently_select_first_fare_family(page):
    await page.set_content(card()+card())
    instance=worker();chosen=(await instance._parse_via_dom(page))[0]
    with pytest.raises(ValueError,match='uniquely'):
        await BaseWorker.select_flight(instance,page,chosen)
    assert await page.evaluate('window.selected===undefined')


@pytest.mark.asyncio
async def test_disappeared_itinerary_does_not_click_old_selector(page):
    await page.set_content(card('101'))
    instance=worker();chosen=(await instance._parse_via_dom(page))[0]
    await page.set_content(card('202'))
    with pytest.raises(ValueError,match='uniquely'):
        await BaseWorker.select_flight(instance,page,chosen)
    assert await page.evaluate('window.selected===undefined')


@pytest.mark.asyncio
async def test_multiple_booking_controls_do_not_guess(page):
    await page.set_content(card(extra_button=True))
    instance=worker();chosen=(await instance._parse_via_dom(page))[0]
    with pytest.raises(ValueError,match='ambiguous'):
        await BaseWorker.select_flight(instance,page,chosen)
    assert await page.evaluate('window.selected===undefined')


def test_directed_segments_are_part_of_connecting_identity():
    row=dict(airline='IndiGo',flight_number='',departure_time='08:30',arrival_time='14:30',stops=1,
        segments=[dict(origin='DEL',destination='BOM',flight_number='6E-101',departure_time='08:30',arrival_time='10:30'),
                  dict(origin='BOM',destination='HYD',flight_number='6E-202',departure_time='12:30',arrival_time='14:30')])
    assert _same_listing(row,{**row,'base_price':6000})
    assert not _same_listing(row,{**row,'segments':list(reversed(row['segments']))})
    assert not _same_listing(row,{**row,'segments':None})
    assert not _same_listing(row,{**row,'segments':[row['segments'][0],{**row['segments'][1],'flight_number':'6E-203'}]})


class Events:
    def __init__(self):self.handlers={}
    def on(self,event,callback):self.handlers.setdefault(event,[]).append(callback)
    def emit(self,event,value):
        for callback in self.handlers.get(event,[]):callback(value)


class Page(Events):
    def __init__(self,context):super().__init__();self.context=context


def response(url):
    return SimpleNamespace(url=url,status=403,json=AsyncMock(side_effect=AssertionError('No response body')))


def test_response_origin_is_exact_or_dot_separated_merchant_subdomain():
    instance=MakeMyTripWorker();context=Events();page=Page(context)
    instance.attach_response_listener(page)
    for host in ['evilmakemytrip.com','www.makemytrip.com.evil.invalid']:
        context.emit('response',response('https://'+host+'/flight/search'))
    context.emit('response',response('http://www.makemytrip.com/flight/search'))
    assert instance._http_failures==[]
    for host in ['makemytrip.com','www.makemytrip.com','flights.makemytrip.com']:
        context.emit('response',response('https://'+host+'/flight/search'))
    assert instance._http_failures==[('/flight/search',403)]*3


def test_repeated_attach_or_new_tab_preserves_current_context_failure_evidence():
    instance=MakeMyTripWorker();context=Events();page=Page(context)
    instance.attach_response_listener(page)
    context.emit('response',response('https://www.makemytrip.com/flight/search'))
    instance.attach_response_listener(page)
    instance.attach_response_listener(Page(context))
    assert len(context.handlers['response'])==1
    assert instance._http_failures==[('/flight/search',403)]


def test_new_context_does_not_accept_late_previous_context_failures():
    instance=MakeMyTripWorker();old=Events();new=Events()
    instance.attach_response_listener(Page(old));instance.attach_response_listener(Page(new))
    old.emit('response',response('https://www.makemytrip.com/flight/search'))
    assert instance._http_failures==[]
    for _ in range(35):new.emit('response',response('https://www.makemytrip.com/flight/search?private=discarded'))
    assert instance._http_failures==[('/flight/search',403)]*30


def test_observer_registry_does_not_keep_discarded_page_or_context_alive():
    instance=MakeMyTripWorker();context=Events();page=Page(context)
    instance.attach_response_listener(page)
    page_ref=weakref.ref(page);context_ref=weakref.ref(context)
    del page,context
    gc.collect()
    assert page_ref() is None and context_ref() is None
    assert len(instance._response_pages)==0 and len(instance._response_contexts)==0
