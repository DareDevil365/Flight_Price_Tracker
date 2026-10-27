"""Fresh audit regressions: cart identity and budgets before coupon testing."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from search_engine import Dispatcher
from workers.cleartrip_worker import CleartripWorker
from tests.test_verified_pricing import page


def selected_quote():
    return dict(flight_number='6E-101',airline='IndiGo',stops=0,
        departure_time='08:30',arrival_time='10:30',departure_date='2026-11-07',
        savings_breakdown=dict(origin='DEL',destination='BOM'))


@pytest.mark.asyncio
@pytest.mark.parametrize('text,change,expected',[
    ('DEL BOM IndiGo 6E-101 Nonstop 08:30 10:30 7 Nov 2026',{},True),
    ('DEL BOM IndiGo 6E-101 Nonstop 8:30 AM 10:30 AM 7 Nov 2026',{},True),
    ('DEL BOM IndiGo 6E-101 Nonstop 08:30 PM 10:30 PM 7 Nov 2026',{},False),
    ('DEL BOM IndiGo 6E-101 Nonstop 08:30 12:30 7 Nov 2026',{},False),
    ('DEL BOM IndiGo 6E-101 Nonstop 08:30 10:30 7 Nov 2026 Changed date 8 Nov 2026',{},False),
    ('DEL BOM IndiGo 6E-101 Nonstop 08:30 10:30 2026-11-07 Changed date 07/11/2027',{},False),
    ('DEL BOM IndiGo 6E-101 Nonstop 23:30 01:30 7 Nov 2026 Arrival 8 Nov 2026',
        {'departure_time':'23:30','arrival_time':'01:30','duration':'2h'},True),
    ('DEL BOM IndiGo 6E-101 Nonstop 23:30 01:30 7 Nov 2026 Arrival 9 Nov 2026',
        {'departure_time':'23:30','arrival_time':'01:30','duration':'2h'},False),
    ('DEL BOM IndiGo 6E-101 Nonstop Departure 10:30 Arrival 08:30 7 Nov 2026',{},False),
    ('DEL BOM IndiGo 6E-101 Nonstop 08:30 10:30 Changed arrival 12:30 7 Nov 2026',{},False),
    ('DEL BOM IndiGo 6E-101 6E-999 Nonstop 08:30 10:30 7 Nov 2026',{},False),
    ('DEL BOM IndiGo 6E-101 Nonstop 1 Stop 08:30 10:30 7 Nov 2026',{},False),
    ('DEL BOM IndiGo 6E-101 1 Stop 08:30 10:30 7 Nov 2026',{},False),
    ('DEL BOM Air India 6E-101 Nonstop 08:30 10:30 7 Nov 2026',{},False),
    # A first flight number and end-to-end schedule cannot certify every leg.
    ('DEL BOM IndiGo 6E-101 Nonstop 08:30 10:30 7 Nov 2026',{'stops':1},False),
    # Generic body text cannot distinguish an upsell from the selected fare.
    ('DEL BOM IndiGo 6E-101 Nonstop 08:30 10:30 7 Nov 2026 Flexi',
        {'savings_breakdown':dict(origin='DEL',destination='BOM',fare_family='Flexi')},False),
])
async def test_current_checkout_must_prove_full_supported_identity(text,change,expected):
    quote={**selected_quote(),**deepcopy(change)}
    worker=CleartripWorker()
    worker.read_selected_itinerary_text=AsyncMock(return_value=text)
    assert await worker.confirm_checkout_flight(None,quote) is expected


@pytest.mark.asyncio
@pytest.mark.parametrize('markup,expected',[
    ('<section aria-label="Selected flight">{correct}</section>',True),
    ('<section><h2>Flight itinerary</h2>{correct}</section>',True),
    ('<div role="region" aria-labelledby="trip-title"><h2 id="trip-title">Trip summary</h2>{correct}</div>',True),
    ('<div>{correct}</div>',False),
    ('<section aria-label="Selected flight">{wrong}</section><section aria-label="Recommended flights">{correct}</section>',False),
    ('<section aria-label="Selected flight">{correct}</section><section aria-label="Booking summary">{correct}</section>',False),
    ('<aside><section aria-label="Selected flight">{correct}</section></aside>',False),
    ('<section aria-label="Selected flight" style="display:none">{correct}</section>',False),
    ('<section aria-label="Selected flight">{correct}<section aria-label="Recommended flights">{wrong}</section></section>',True),
    ('<section aria-label="Selected flight">{correct} {wrong}</section>',False),
])
async def test_checkout_identity_uses_only_one_named_selected_scope(page,markup,expected):
    correct='DEL BOM IndiGo 6E-101 Nonstop 08:30 10:30 7 Nov 2026'
    wrong='DEL BOM IndiGo 6E-999 Nonstop 09:30 11:30 7 Nov 2026'
    await page.set_content(markup.format(correct=correct,wrong=wrong))
    assert await CleartripWorker().confirm_checkout_flight(page,selected_quote()) is expected


@pytest.mark.asyncio
async def test_budget_does_not_discard_a_possible_coupon_winner():
    db=SimpleNamespace(save_result=AsyncMock())
    events=[]
    dispatcher=Dispatcher(db,None,None,None,None,lambda *args:events.append(args))
    task=dict(search_id='budget',financial=dict(max_final_price=5000),trip=dict(
        origin='DEL',destination='BOM',departure_date='2026-11-07',
        passenger_count=1,cabin_class='ECONOMY'))
    # An eligible INR 1,000 coupon could beat the INR 5,000 cap, so a raw
    # INR 5,500 listing must survive until its own payable total is checked.
    await dispatcher._save_listings('cleartrip',task,[dict(base_price=5500)],'https://www.cleartrip.com')
    row=db.save_result.await_args.args[0]
    assert row['final_price']==5500
    assert row['savings_breakdown']['budget_check']['listed_over_budget'] is True
    assert events[0][0]=='search:results'
