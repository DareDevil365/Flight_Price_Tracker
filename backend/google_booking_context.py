"""Public Google booking-page context; never checkout proof or training fares."""
import re
from datetime import date
from quotes import utc_now, search_url

MONEY = r'(?:\d{1,2}(?:,\d{2})*,\d{3}|\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?'


def amount(value, allow_zero=False):
    if not re.fullmatch(MONEY, value):
        raise ValueError('Ambiguous currency amount')
    result = float(value.replace(',', ''))
    if not (0 <= result < 10_000_000 if allow_zero else 0 < result < 10_000_000):
        raise ValueError('Invalid currency amount')
    return result


def visible_times(text):
    output = []
    for h, m, meridian in re.findall(r'\b(\d{1,2}):(\d{2})\s*(AM|PM)?\b', text, re.I):
        h, m = int(h), int(m)
        if m > 59 or (meridian and not 1 <= h <= 12) or (not meridian and h > 23):
            continue
        if meridian:
            h = h % 12 + (12 if meridian.upper() == 'PM' else 0)
        output.append(f'{h:02d}:{m:02d}')
    return output


def parse_booking_context(text, labels, trip, flight):
    """Scope to selected itinerary before accepting any external interpretation.

    The year was already verified on the dated listing before the selection;
    Google abbreviates that date in its selected-flight summary. This function
    is used only by the same-page selection flow, never on pasted page text.
    """
    if len(text) > 100_000 or 'Selected flights' not in text or 'Booking options' not in text:
        raise ValueError('Google did not show a selected itinerary and booking options')
    summary = text.split('Selected flights', 1)[1].split('Booking options', 1)[0]
    day = date.fromisoformat(trip['departure_date'])
    shown_day = re.search(rf'\b{day:%b}\s+0?{day.day}\b(?:,?\s+(20\d{{2}})\b)?', summary)
    if not shown_day:
        raise ValueError('Selected Google departure day does not match')
    if shown_day[1] and int(shown_day[1]) != day.year:
        raise ValueError('Selected Google departure year changed')
    route = re.findall(r'\b([A-Z]{3})\s*[–—-]\s*([A-Z]{3})\b', summary)
    if route != [(trip['origin'], trip['destination'])]:
        raise ValueError('Selected Google directed airports are ambiguous or changed')
    prefix = text.split('Selected flights', 1)[0]
    cabin = trip['cabin_class'].replace('_', ' ')
    if not re.search(r'One way\s*' + re.escape(cabin) + r'\b', prefix, re.I):
        raise ValueError('Google selected cabin or trip type changed')
    if not re.search(rf'\b{trip["passenger_count"]}\s+passengers?\b', prefix):
        raise ValueError('Google selected adult count changed')
    if not re.search(rf'Prices include required taxes.*?for\s+{trip["passenger_count"]}\s+adults?\b', text, re.I):
        raise ValueError('Google did not confirm adult-only group price scope')
    if visible_times(summary)[:2] != [flight['departure_time'], flight['arrival_time']]:
        raise ValueError('Selected Google schedule changed')
    if flight['airline'].lower().replace(' ', '') not in summary.lower().replace(' ', ''):
        raise ValueError('Selected Google airline changed')
    stops = 0 if re.search(r'non.?stop', summary, re.I) else None
    match = re.search(r'\b(\d+)\s+stops?\b', summary, re.I)
    if match:
        stops = int(match[1])
    if stops != flight['stops']:
        raise ValueError('Selected Google stops changed')

    options = []
    for label in labels[:50]:
        if not isinstance(label, str) or len(label) > 600:
            continue
        match = re.fullmatch(r'Continue to book with (.+?) for (' + MONEY + r') Indian rupees(?:\.(.*))?', label.strip(), re.I)
        if not match:
            continue
        tail = (match[3] or '').strip()
        fee = re.fullmatch(r'Includes (' + MONEY + r') Indian rupees convenience fee', tail, re.I)
        options.append(dict(merchant=match[1], listed_total=amount(match[2]),
                            included_convenience_fee=amount(fee[1], allow_zero=True) if fee else None,
                            fee_note=tail or 'No separate fee information displayed',
                            verification='google_partner_listing'))

    insight = None
    if 'Price insights' in text:
        context = text.split('Price insights', 1)[1].split('Price history', 1)[0][:4000]
        match = re.search(r'₹\s*(' + MONEY + r')\s+is\s+(low|typical|high)\s+for\s+' + re.escape(cabin), context, re.I)
        band = re.search(r'usually cost between\s+₹\s*(' + MONEY + r')\s*[–—-]\s*(' + MONEY + r')(?!(?:[\d,]|\.\d|[eE][+-]?\d))', context, re.I)
        if match:
            insight = dict(classification=match[2].lower(), quoted_price=amount(match[1]),
                           typical_low=None, typical_high=None,
                           comparison_scope='Google comparison with similar trips; not a prediction of this flight',
                           certainty_percent=None)
            if band:
                low, high = amount(band[1]), amount(band[2])
                if low >= high:
                    raise ValueError('Google comparison range is inconsistent')
                insight.update(typical_low=low, typical_high=high)

    if not insight and not options:
        raise ValueError('No supported Google price guidance or INR partner offers could be read')
    return dict(status='available', source='Google Flights', source_url=search_url('google_flights', trip),
                observed_at=utc_now(), scope=dict(origin=trip['origin'], destination=trip['destination'],
                departure_date=trip['departure_date'], passenger_count=trip['passenger_count'], cabin_class=trip['cabin_class'],
                airline=flight['airline'], departure_time=flight['departure_time'], arrival_time=flight['arrival_time'], stops=flight['stops']),
                insight=insight, booking_options=options,
                limitation='Google partner offers are listed totals. Recheck the merchant cart, coupons, payment fees and baggage before buying. External guidance is not used to train or calibrate our model.')


async def load_booking_context(page, trip, quote):
    from workers.google_flights_worker import GoogleFlightsWorker
    from quotes import valid_flights
    from urllib.parse import urlsplit
    from playwright.async_api import TimeoutError as BrowserTimeout
    worker = GoogleFlightsWorker()
    await worker.input_search_criteria(page, trip)
    await worker.execute_search(page)
    flights = valid_flights(await worker.parse_search_results(page), trip)
    def select(rows):
        matches = [f for f in rows if f['airline'] == quote['airline'] and
                   f['departure_time'] == quote['departure_time'] and f.get('arrival_time') == quote.get('arrival_time') and
                   f['stops'] == quote['stops'] and
                   (not quote.get('flight_number') or not f.get('flight_number') or
                    re.sub(r'[^A-Z0-9]', '', f['flight_number'].upper()) == re.sub(r'[^A-Z0-9]', '', quote['flight_number'].upper()))]
        if len(matches) != 1:
            raise ValueError('This itinerary is no longer uniquely available on Google. Run a fresh search.')
        return matches[0]
    flight = select(flights)
    try:
        await page.locator(flight['selector']).click(timeout=4000)
    except BrowserTimeout:
        # Google can replace card nodes after the first render. Re-read the real
        # dated cards once and match again; never fall back to a generic row.
        flight = select(valid_flights(await worker.parse_search_results(page), trip))
        await page.locator(flight['selector']).click(timeout=4000)
    await page.wait_for_function("() => document.body.innerText.includes('Booking options') && document.body.innerText.includes('Prices include required taxes')", timeout=25000)
    try:
        await page.locator('button[aria-label^="Continue to book with"]:visible').first.wait_for(timeout=8000)
    except BrowserTimeout:
        # Price guidance can still be useful when partner inventory is absent.
        # An empty options list means unavailable coverage, never zero fees.
        pass
    url = urlsplit(page.url)
    if url.scheme != 'https' or url.hostname != 'www.google.com' or not url.path.startswith('/travel/flights'):
        raise ValueError('Google booking context left the expected public source')
    labels = await page.locator('button[aria-label^="Continue to book with"]:visible').evaluate_all('(els) => els.map(el => el.getAttribute("aria-label"))')
    return parse_booking_context(await page.inner_text('body'), labels, trip, flight)
