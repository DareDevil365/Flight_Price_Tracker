"""Read-only MakeMyTrip advertised inventory, never a live/final/learning quote.

The public MCP currently answers without credentials or payment. Its own
response warns that inventory may be cached; cache age/TTL are not exposed.
This is not a documented permanent free third-party API contract. Requests use
the server's channel default, ordinary protocol headers and no identity spoof.
Initial supported scope: one adult, Economy, domestic Indian one-way nonstops.
"""
import asyncio
import json
import math
import re
from datetime import date, datetime
from urllib.parse import parse_qs, urlparse

import aiohttp

from compiler import is_indian_airport
from quotes import duration_minutes, search_url, utc_now, valid_flights

ENDPOINT = "https://www.makemytrip.com/ai/mcp?src=cm"
MAX_BODY = 2_000_000
REQUEST_SECONDS = 20
TOTAL_SECONDS = 35
WIDGET_URI = "ui://widget/flights-listing.html"


class MakeMyTripSourceError(RuntimeError):
    """Source unavailable, unsupported request or insufficient exact evidence."""


def _supported(trip):
    try:
        day = date.fromisoformat(trip["departure_date"])
        codes = (trip["origin"], trip["destination"])
        if any(not isinstance(c, str) or not re.fullmatch(r"[A-Z]{3}", c) or not is_indian_airport(c) for c in codes):
            raise ValueError()
        if codes[0] == codes[1] or day <= date.today():
            raise ValueError()
        if type(trip.get("passenger_count", 1)) is not int or trip.get("passenger_count", 1) != 1:
            raise ValueError()
        if trip.get("cabin_class", "ECONOMY") != "ECONOMY" or trip.get("is_domestic", True) is not True:
            raise ValueError()
        if trip.get("return_date") or trip.get("is_round_trip") or trip.get("children", 0) != 0 or trip.get("infants", 0) != 0:
            raise ValueError()
        return day
    except (KeyError, ValueError, TypeError):
        raise MakeMyTripSourceError("MMT advertised source supports future Indian one-way flights, one adult Economy only") from None


def _decode(body):
    try:
        result = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        messages = []
        for line in body.splitlines():
            if line.startswith(b"data:"):
                try:
                    messages.append(json.loads(line[5:].strip()))
                except (ValueError, UnicodeDecodeError):
                    raise MakeMyTripSourceError("MMT malformed event response") from None
        if len(messages) != 1:
            raise MakeMyTripSourceError("MMT missing or ambiguous event response")
        result = messages[0]
    if not isinstance(result, dict) or result.get("error"):
        raise MakeMyTripSourceError("MMT protocol error")
    return result


def _schema_tool(listing):
    tools = listing.get("tools")
    if not isinstance(tools, list):
        raise MakeMyTripSourceError("MMT tool discovery unavailable")
    found = [t for t in tools if isinstance(t, dict) and t.get("name") == "fetch-flights"]
    if len(found) != 1:
        raise MakeMyTripSourceError("MMT exact flight tool not discovered")
    tool = found[0]
    schema = tool.get("inputSchema", {})
    props = schema.get("properties", {})
    required = {"prompt", "departureCityCode", "destinationCityCode", "departureDate"}
    if (tool.get("annotations", {}).get("readOnlyHint") is not True
            or tool.get("annotations", {}).get("destructiveHint") is True
            or schema.get("type") != "object" or set(schema.get("required", [])) != required
            or not required.issubset(props)
            or props.get("channel", {}).get("default") != "GPTApp_Flight"
            or props.get("cabinClass", {}).get("default") != "E"
            or props.get("adults", {}).get("default") != 1
            or props.get("isRoundTrip", {}).get("default") is not False
            or "oneWayFlightfilters" not in props
            or tool.get("_meta", {}).get("openai/outputTemplate") != WIDGET_URI):
        raise MakeMyTripSourceError("MMT flight source schema changed; withholding results")
    return tool


def _widget_asset(html):
    assets = re.findall(r'import\("(https://jsak\.mmtcdn\.com/pwa_v3/growth-gpt-templates/flights-listing/[^"?]+\.js)"\)', html)
    if len(assets) != 1:
        raise MakeMyTripSourceError("MMT currency display proof unavailable")
    return assets[0]


def _unit_proof(script):
    # Derived from the merchant's advertised flight widget, not inferred from
    # Indian geography. A changed component is withheld until inspected again.
    if not (re.search(r'price-amount.{0,100}[₹]', script) and re.search(r'price-label.{0,100}per adult', script)):
        raise MakeMyTripSourceError("MMT INR/per-adult display proof changed")


def _normalize(structured, trip):
    day = _supported(trip)
    if not isinstance(structured, dict) or structured.get("error"):
        raise MakeMyTripSourceError("MMT inventory unavailable")
    url = urlparse(structured.get("listingUrl", ""))
    if url.scheme != "https" or url.netloc != "www.makemytrip.com" or url.path != "/flight/search":
        raise MakeMyTripSourceError("MMT listing provenance mismatch")
    try:
        query = parse_qs(url.query, strict_parsing=True, max_num_fields=30)
    except ValueError:
        raise MakeMyTripSourceError("MMT listing criteria malformed") from None
    expected = {"itinerary": f'{trip["origin"]}-{trip["destination"]}-{day:%d/%m/%Y}', "tripType": "O", "paxType": "A-1_C-0_I-0", "cabinClass": "E"}
    if any(query.get(k) != [v] for k,v in expected.items()):
        raise MakeMyTripSourceError("MMT response route/date/passengers/cabin mismatch")
    offers = structured.get("flights")
    if not isinstance(offers, list) or len(offers) > 100:
        raise MakeMyTripSourceError("MMT inventory malformed or oversized")
    rows = []
    for offer in offers:
        try:
            if not isinstance(offer, dict) or offer.get("type") != "One Way":
                continue
            amount = offer["price"]
            if type(amount) not in (int, float) or not math.isfinite(amount) or amount <= 0:
                continue
            services = offer["services"]
            if not isinstance(services, dict):
                continue
            if services.get("cabinClass") != "Economy":
                continue
            journeys = offer["flights"]
            if not isinstance(journeys, list) or len(journeys) != 1:
                continue
            flight = journeys[0]
            if not isinstance(flight, dict):
                continue
            if (flight.get("departureCity"), flight.get("arrivalCity")) != (trip["origin"], trip["destination"]):
                continue
            legs = flight["legs"]
            if not isinstance(legs, list) or len(legs) != 1 or flight.get("stops") != "Non Stop":
                continue
            leg = legs[0]
            if not isinstance(leg, dict):
                continue
            if leg.get("techStops") != [] or leg.get("travelMode") != "AIR":
                continue
            if (leg["departureInfo"]["airportCode"], leg["arrivalInfo"]["airportCode"]) != (trip["origin"], trip["destination"]):
                continue
            dep = datetime.strptime(leg["depTime"], "%Y-%m-%d %H:%M")
            arr = datetime.strptime(leg["arrTime"], "%Y-%m-%d %H:%M")
            minutes = (arr-dep).total_seconds()/60
            if dep.date() != day or not 0 < minutes < 1440 or duration_minutes(flight.get("duration")) != minutes:
                continue
            if type(leg.get("durationInMins")) is not int or leg["durationInMins"] != minutes:
                continue
            if flight.get("departureTime") != dep.strftime("%H:%M") or flight.get("arrivalTime") != arr.strftime("%H:%M"):
                continue
            airline, number = flight["airline"], flight["flightNumber"]
            if not isinstance(airline, str) or not re.fullmatch(r"[A-Z0-9]{2}", airline):
                continue
            if not isinstance(number, str) or not re.fullmatch(r"[0-9]{1,5}[A-Z]?", number):
                continue
            if leg.get("marketingAirline") != airline or leg.get("flightNum") != number:
                continue
            family = services.get("fareType")
            if not isinstance(family, str) or not family.strip() or len(family) > 80:
                continue
            rows.append(dict(platform="makemytrip", airline=airline, flight_number=airline+number,
                base_price=float(amount), currency="INR", price_basis="total", original_price_basis="per_person",
                origin=trip["origin"], destination=trip["destination"], departure_date=day.isoformat(),
                passenger_count=1, cabin_class="ECONOMY", departure_time=dep.strftime("%H:%M"),
                arrival_time=arr.strftime("%H:%M"), arrival_date=arr.date().isoformat(),
                duration=flight["duration"], stops=0, fare_family=family,
                booking_url=search_url("makemytrip", trip),
                source_transport="makemytrip_public_mcp", source_freshness="cache_age_unknown",
                source_quote_timestamp=None, source_fetched_at=utc_now(), source_learning_allowed=False,
                source_inventory={"partial": True, "scope": "one adult Economy domestic one-way nonstops",
                    "limitation": "May be cached; age unknown. Merchant inventory subset; final fees and coupon eligibility unverified."},
                checkout_verified=False, fees_verified=False, coupons_verified=False))
        except (KeyError, ValueError, TypeError, OverflowError):
            continue
    rows = valid_flights(rows, trip)
    if not rows:
        raise MakeMyTripSourceError("MMT returned no exactly supported advertised flights")
    return rows


async def _fetch(trip):
    day = _supported(trip)
    session_id = None
    headers = {"Accept": "application/json, text/event-stream"}
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=REQUEST_SECONDS), cookie_jar=aiohttp.DummyCookieJar()) as client:
        async def body(response):
            chunks, size = [], 0
            while True:
                chunk = await response.content.read(min(65536, MAX_BODY+1-size))
                if not chunk:
                    return b"".join(chunks)
                size += len(chunk)
                if size > MAX_BODY:
                    raise MakeMyTripSourceError("MMT source response exceeds safety limit")
                chunks.append(chunk)
        async def rpc(method, params, request_id):
            nonlocal session_id
            payload = {"jsonrpc": "2.0", "method": method, "params": params}
            if request_id is not None:
                payload["id"] = request_id
            async with client.post(ENDPOINT, json=payload, headers=headers, allow_redirects=False) as response:
                if response.status not in (200, 202, 204):
                    raise MakeMyTripSourceError(f"MMT source HTTP {response.status}")
                returned_session = response.headers.get("Mcp-Session-Id")
                if returned_session:
                    if len(returned_session) > 512 or any(ord(c) < 32 for c in returned_session):
                        raise MakeMyTripSourceError("MMT invalid protocol session")
                    session_id = returned_session
                    headers["Mcp-Session-Id"] = session_id
                raw = await body(response)
                if request_id is None:
                    return {}
                message = _decode(raw)
                if message.get("id") != request_id or not isinstance(message.get("result"), dict):
                    raise MakeMyTripSourceError("MMT protocol response mismatch")
                return message["result"]
        try:
            initialized = await rpc("initialize", {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "flight-finder-public-reader", "version": "0.1"}}, 1)
            if initialized.get("protocolVersion") != "2025-03-26":
                raise MakeMyTripSourceError("MMT unsupported protocol version")
            headers["MCP-Protocol-Version"] = "2025-03-26"
            await rpc("notifications/initialized", {}, None)
            _schema_tool(await rpc("tools/list", {}, 2))
            result = await rpc("tools/call", {"name": "fetch-flights", "arguments": {
                "prompt": f'One-way {trip["origin"]} to {trip["destination"]} on {day.isoformat()}, one adult Economy, nonstop',
                "departureCityCode": trip["origin"], "destinationCityCode": trip["destination"],
                "departureDate": f'{day:%Y%m%d}', "adults": 1, "children": 0, "infants": 0,
                "cabinClass": "E", "isRoundTrip": False, "oneWayFlightfilters": {"stops": 0}, "sorter": "Cheapest"}}, 3)
            if result.get("isError"):
                raise MakeMyTripSourceError("MMT flight tool failed")
            resource = await rpc("resources/read", {"uri": WIDGET_URI}, 4)
            contents = resource.get("contents")
            if not isinstance(contents, list) or len(contents) != 1 or contents[0].get("uri") != WIDGET_URI:
                raise MakeMyTripSourceError("MMT widget provenance mismatch")
            asset = _widget_asset(contents[0].get("text", ""))
            async with client.get(asset, allow_redirects=False) as response:
                if response.status != 200:
                    raise MakeMyTripSourceError("MMT currency display unavailable")
                script = (await body(response)).decode("utf-8")
            _unit_proof(script)
            return _normalize(result.get("structuredContent"), trip)
        finally:
            if session_id:
                try:
                    async with asyncio.timeout(1):
                        async with client.delete(ENDPOINT, headers=headers, allow_redirects=False):
                            pass
                except (aiohttp.ClientError, TimeoutError):
                    pass


async def fetch_makemytrip(trip):
    """Return exact advertised references or explicit failure; never feed learning."""
    _supported(trip)
    try:
        async with asyncio.timeout(TOTAL_SECONDS):
            return await _fetch(trip)
    except MakeMyTripSourceError:
        raise
    except (aiohttp.ClientError, TimeoutError, UnicodeError, ValueError, TypeError, AttributeError, KeyError):
        raise MakeMyTripSourceError("MMT advertised source unavailable or timed out") from None
