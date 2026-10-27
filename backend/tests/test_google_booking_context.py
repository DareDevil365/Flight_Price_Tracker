"""Fixtures reflect public page text; never imported into live fare history."""
from copy import deepcopy
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from google_booking_context import parse_booking_context, amount

TRIP = dict(origin='DEL', destination='GOI', departure_date='2026-12-16', passenger_count=1, cabin_class='ECONOMY')
FLIGHT = dict(airline='Air India Express', departure_time='18:35', arrival_time='21:15', stops=0)
TEXT = '''Itinerary summary
New Delhi
Goa
One wayEconomy
1 passenger
Selected flights
Wed, Dec 16
6:35 PM
–
9:15 PM
Air India Express
2 hr 40 min
DEL–GOI
Nonstop
Booking options
Book with Air India Express
₹14,994
Continue
Prices include required taxes + fees for 1 adult. Optional charges and bag fees may apply.
Price insights
₹14,745 is typical for Economy
The least expensive flights for similar trips to Goa usually cost between ₹7,800–21,000.
Price history for these flights
32 days ago
₹16,000
'''
LABEL = 'Continue to book with Air India Express airline for 14994 Indian rupees. Includes 249 Indian rupees convenience fee'


def test_separate_fare_context_and_partner_fee_no_forecast_or_checkout_proof():
    result = parse_booking_context(TEXT, [LABEL], TRIP, FLIGHT)
    assert result['insight']['quoted_price'] == 14745
    assert result['insight']['typical_high'] == 21000
    assert result['insight']['certainty_percent'] is None
    assert result['booking_options'][0]['listed_total'] == 14994
    assert result['booking_options'][0]['included_convenience_fee'] == 249
    assert result['booking_options'][0]['verification'] == 'google_partner_listing'
    assert 'forecast_7d' not in result
    assert 'history' not in result


@pytest.mark.parametrize('old,new', [('DEL–GOI','GOI–DEL'), ('Dec 16','Dec 17'),
    ('1 passenger','2 passengers'), ('Economy\n1 passenger','Business\n1 passenger'),
    ('for 1 adult','for 2 adults'), ('6:35 PM','6:35 AM'), ('Nonstop','1 stop'),
    ('Air India Express\n2 hr','IndiGo\n2 hr')])
def test_changed_selected_trip_is_rejected(old, new):
    with pytest.raises(ValueError):
        parse_booking_context(TEXT.replace(old, new), [LABEL], TRIP, FLIGHT)


def test_ranges_and_money_fail_closed():
    with pytest.raises(ValueError):
        parse_booking_context(TEXT.replace('₹7,800–21,000','₹21,000–7,800'), [LABEL], TRIP, FLIGHT)
    for invalid in ('1,2,3', 'nan', '0', '-100', '10000000'):
        with pytest.raises(ValueError):
            amount(invalid)
    assert amount('1,23,456') == 123456


def test_foreign_partner_offer_ignored_and_unknown_fee_not_zero():
    labels = ['Continue to book with Agency for 50 US dollars.',
              'Continue to book with Agency for 15000 Indian rupees. Payment fees may apply']
    result = parse_booking_context(TEXT, labels, TRIP, FLIGHT)
    assert len(result['booking_options']) == 1
    assert result['booking_options'][0]['included_convenience_fee'] is None


def test_real_partner_labels_without_fee_sentence_are_not_discarded():
    labels = ['Continue to book with Air India airline for 6693 Indian rupees',
              'Continue to book with FlightsMojo for 6956 Indian rupees',
              'Continue to book with Agency for 7000 Indian rupees. Includes 0 Indian rupees convenience fee']
    result = parse_booking_context(TEXT, labels, TRIP, FLIGHT)
    assert [option['listed_total'] for option in result['booking_options']] == [6693,6956,7000]
    assert result['booking_options'][0]['included_convenience_fee'] is None
    assert result['booking_options'][2]['included_convenience_fee'] == 0


def test_missing_guidance_never_creates_default():
    result = parse_booking_context(TEXT.split('Price insights')[0], [LABEL], TRIP, FLIGHT)
    assert result['insight'] is None
    with pytest.raises(ValueError):
        parse_booking_context(TEXT.split('Price insights')[0], [], TRIP, FLIGHT)


def test_explicit_selected_year_conflict_is_not_hidden_by_abbreviated_day():
    with pytest.raises(ValueError,match='year'):
        parse_booking_context(TEXT.replace('Dec 16','Dec 16, 2027'), [LABEL], TRIP, FLIGHT)
    assert parse_booking_context(TEXT.replace('Dec 16','Dec 16, 2026'), [LABEL], TRIP, FLIGHT)['status']=='available'


@pytest.mark.parametrize('bad',['21,000.505','21,000,00','21000e5'])
def test_partial_range_money_is_not_silently_promoted(bad):
    result = parse_booking_context(TEXT.replace('7,800–21,000','7,800–'+bad), [LABEL], TRIP, FLIGHT)
    assert result['insight']['typical_high'] is None


def test_reverse_or_different_preference_does_not_reuse_guidance():
    trip = deepcopy(TRIP)
    trip.update(origin='GOI', destination='DEL')
    with pytest.raises(ValueError):
        parse_booking_context(TEXT, [LABEL], trip, FLIGHT)


def dispatcher_fixture():
    from search_engine import Dispatcher
    dispatcher = Dispatcher.__new__(Dispatcher)
    row = {**FLIGHT, 'id':'result', 'platform':'google_flights', 'departure_date':TRIP['departure_date'],
           'savings_breakdown':{'origin':'DEL','destination':'GOI','integrity':{'status':'uncorroborated'}}}
    dispatcher.db = SimpleNamespace(get_search_results=AsyncMock(return_value=[row]),
                                    save_result=AsyncMock(side_effect=AssertionError('External context must not alter quotes')),
                                    record_quote=AsyncMock(side_effect=AssertionError('External context must not enter training')))
    dispatcher._search_tasks = {'search':{'trip':TRIP,'cloak':{}}}
    dispatcher._slots = asyncio.Semaphore(1)
    dispatcher._google_context_lock = asyncio.Lock()
    dispatcher._google_context_sessions = {}
    browser = SimpleNamespace(close=AsyncMock())
    dispatcher.factory = SimpleNamespace(create_cloak_browser=AsyncMock(return_value=(browser,object(),object())))
    dispatcher.session_mgr = SimpleNamespace(get_session_status=lambda sid:'active', close_session=AsyncMock(),
                                            register_session=AsyncMock(),set_session_ready=AsyncMock())
    return dispatcher, row, browser


@pytest.mark.asyncio
async def test_guidance_cache_retains_browser_but_never_mutates_quote_or_learning(monkeypatch):
    dispatcher, row, _ = dispatcher_fixture()
    monkeypatch.setattr('google_booking_context.load_booking_context', AsyncMock(return_value={'status':'available'}))
    report = await dispatcher.google_booking_context('search','result')
    assert report['resultId'] == row['id'] and report['sessionId']
    assert await dispatcher.google_booking_context('search','result') is report
    dispatcher.factory.create_cloak_browser.assert_awaited_once()
    dispatcher.db.save_result.assert_not_awaited()
    dispatcher.db.record_quote.assert_not_awaited()


@pytest.mark.asyncio
async def test_guidance_quarantine_rechecked_even_for_cached_result(monkeypatch):
    dispatcher, row, _ = dispatcher_fixture()
    dispatcher._google_context_sessions[('search','result')]={'sessionId':'cached'}
    row['savings_breakdown']['integrity']['status']='flagged'
    with pytest.raises(ValueError,match='quarantined'):
        await dispatcher.google_booking_context('search','result')
    dispatcher.factory.create_cloak_browser.assert_not_awaited()


@pytest.mark.asyncio
async def test_guidance_cancellation_closes_browser_without_registering(monkeypatch):
    dispatcher, _, browser = dispatcher_fixture()
    monkeypatch.setattr('google_booking_context.load_booking_context', AsyncMock(side_effect=asyncio.CancelledError))
    with pytest.raises(asyncio.CancelledError):
        await dispatcher.google_booking_context('search','result')
    browser.close.assert_awaited_once()
    dispatcher.session_mgr.register_session.assert_not_awaited()
    assert not dispatcher._google_context_sessions


@pytest.mark.asyncio
async def test_expired_guidance_closes_old_session_then_rereads(monkeypatch):
    dispatcher, _, _ = dispatcher_fixture()
    dispatcher._google_context_sessions[('search','result')]={'sessionId':'expired'}
    dispatcher.session_mgr.get_session_status=lambda sid:'expired'
    monkeypatch.setattr('google_booking_context.load_booking_context', AsyncMock(return_value={'status':'available'}))
    result = await dispatcher.google_booking_context('search','result')
    dispatcher.session_mgr.close_session.assert_awaited_once_with('expired')
    assert result['sessionId'] != 'expired'
