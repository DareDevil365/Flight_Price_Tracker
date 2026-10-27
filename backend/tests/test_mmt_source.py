"""Adversarial protocol/criteria fixtures; no test rows enter production data."""
import asyncio
import copy
import json
from datetime import date, timedelta
from urllib.parse import urlencode

import pytest

import mmt_source as source

DAY = date.today() + timedelta(days=60)
TRIP = dict(origin="AMD", destination="IXC", departure_date=DAY.isoformat(), passenger_count=1, cabin_class="ECONOMY", is_domestic=True, preferred_time="ANY")
TOOL = dict(name="fetch-flights", annotations={"readOnlyHint": True}, inputSchema={"type": "object", "required": ["prompt", "departureCityCode", "destinationCityCode", "departureDate"], "properties": {
    "prompt": {}, "departureCityCode": {}, "destinationCityCode": {}, "departureDate": {},
    "channel": {"default": "GPTApp_Flight"}, "cabinClass": {"default": "E"}, "adults": {"default": 1}, "isRoundTrip": {"default": False}, "oneWayFlightfilters": {}}}, _meta={"openai/outputTemplate": source.WIDGET_URI})


def inventory():
    leg = dict(marketingAirline="6E", flightNum="6506", techStops=[], travelMode="AIR", departureInfo={"airportCode": "AMD", "terminal": "T1"}, arrivalInfo={"airportCode": "IXC"}, depTime=f"{DAY} 20:35", arrTime=f"{DAY} 22:20", durationInMins=105)
    flight = dict(departureCity="AMD", arrivalCity="IXC", departureTime="20:35", arrivalTime="22:20", duration="1h 45m", airline="6E", flightNumber="6506", stops="Non Stop", legs=[leg])
    offer = dict(price=6719, type="One Way", journeyDate=DAY.strftime("%b %d"), flights=[flight], services={"cabinClass": "Economy", "fareType": "SAVER"}, crId="private-marker", deepLink="https://example.invalid/?token=private-marker")
    query = dict(itinerary=f"AMD-IXC-{DAY:%d/%m/%Y}", tripType="O", paxType="A-1_C-0_I-0", cabinClass="E")
    return dict(flights=[offer], error="", hasMoreFlights=True, listingUrl="https://www.makemytrip.com/flight/search?" + urlencode(query))


def test_exact_reference_keeps_direction_date_units_and_no_private_identifiers():
    row = source._normalize(inventory(), TRIP)[0]
    assert (row["origin"], row["destination"], row["departure_date"], row["flight_number"]) == ("AMD", "IXC", DAY.isoformat(), "6E6506")
    assert row["source_learning_allowed"] is False
    assert row["source_freshness"] == "cache_age_unknown"
    assert row["source_quote_timestamp"] is None
    assert row["source_inventory"]["partial"] is True
    assert row["fees_verified"] is False and row["coupons_verified"] is False
    assert "private-marker" not in json.dumps(row)
    assert row["currency"] == "INR" and row["base_price"] == 6719


@pytest.mark.parametrize("price", [True, False, float("nan"), float("inf"), -1, 0, "6719", {}, None])
def test_malformed_money_is_withheld(price):
    data = inventory(); data["flights"][0]["price"] = price
    with pytest.raises(source.MakeMyTripSourceError):
        source._normalize(data, TRIP)


@pytest.mark.parametrize("field,value", [("itinerary", "IXC-AMD-01/01/2027"), ("tripType", "R"), ("paxType", "A-2_C-0_I-0"), ("cabinClass", "B")])
def test_source_search_criteria_mismatch_fails(field, value):
    from urllib.parse import urlparse, parse_qs
    data = inventory(); q = parse_qs(urlparse(data["listingUrl"]).query); q[field] = [value]
    data["listingUrl"] = "https://www.makemytrip.com/flight/search?" + urlencode(q, doseq=True)
    with pytest.raises(source.MakeMyTripSourceError):
        source._normalize(data, TRIP)


@pytest.mark.parametrize("mutation", [
    lambda d: d.update(listingUrl=d["listingUrl"]+"&paxType=A-1_C-0_I-0"),
    lambda d: d.update(listingUrl=d["listingUrl"].replace("www.makemytrip.com", "www.makemytrip.com.evil.invalid")),
    lambda d: d["flights"][0]["services"].update(cabinClass="Business"),
    lambda d: d["flights"][0]["flights"][0].update(stops="1 stop"),
    lambda d: d["flights"][0]["flights"][0]["legs"][0].update(depTime="2027-01-01 20:35"),
    lambda d: d["flights"][0]["flights"][0]["legs"][0]["arrivalInfo"].update(airportCode="AMD"),
    lambda d: d["flights"][0]["flights"][0]["legs"][0].update(durationInMins=True),
    lambda d: d["flights"][0]["flights"][0]["legs"][0].update(flightNum="9999"),
    lambda d: d["flights"][0]["flights"][0]["legs"][0].update(techStops=["DEL"]),
    lambda d: d["flights"][0].update(services=None),
    lambda d: d["flights"][0].update(flights=[None]),
    lambda d: d["flights"][0]["flights"][0].update(legs=[None]),
])
def test_uncertain_itinerary_is_not_normalized(mutation):
    data = inventory(); mutation(data)
    with pytest.raises(source.MakeMyTripSourceError):
        source._normalize(data, TRIP)


@pytest.mark.parametrize("patch", [{"passenger_count": 2}, {"passenger_count": True}, {"origin": "DXB"}, {"cabin_class": "BUSINESS"}, {"return_date": DAY.isoformat()}, {"is_domestic": False}, {"departure_date": "invalid"}])
@pytest.mark.asyncio
async def test_unsupported_requests_stop_before_network(monkeypatch, patch):
    def forbidden(**kwargs):
        raise AssertionError("Unsupported request touched network")
    monkeypatch.setattr(source.aiohttp, "ClientSession", forbidden)
    with pytest.raises(source.MakeMyTripSourceError):
        await source.fetch_makemytrip({**TRIP, **patch})


def test_currency_widget_change_fails_closed():
    source._unit_proof('price-amount children:["₹",o] price-label children:"per adult"')
    for value in ["$ per adult", "₹ total", "price-amount₹ price-label per passenger", ""]:
        with pytest.raises(source.MakeMyTripSourceError):
            source._unit_proof(value)
    with pytest.raises(source.MakeMyTripSourceError):
        source._widget_asset('import("https://evil.invalid/widget.js")')


class Response:
    def __init__(self, data, status=200, headers=None):
        self.status, self.headers = status, headers or {}
        self.raw = data if isinstance(data, bytes) else json.dumps(data).encode()
        self.content = self
    async def read(self, limit):
        # Emulate partial network chunks: a single read is not the whole body.
        chunk = self.raw[:min(limit, 71)]; self.raw = self.raw[len(chunk):]
        return chunk
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass


class Client:
    def __init__(self, transform=None):
        self.calls, self.transform = [], transform
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass
    def post(self, url, **kwargs):
        payload = kwargs["json"]; self.calls.append(payload)
        method = payload["method"]; rid = payload.get("id")
        result = {"initialize": {"protocolVersion": "2025-03-26"}, "notifications/initialized": {}, "tools/list": {"tools": [copy.deepcopy(TOOL)]}, "tools/call": {"structuredContent": inventory()}, "resources/read": {"contents": [{"uri": source.WIDGET_URI, "text": 'import("https://jsak.mmtcdn.com/pwa_v3/growth-gpt-templates/flights-listing/widget.js")'}]}}[method]
        msg = {"jsonrpc": "2.0", "id": rid, "result": result}
        if self.transform: msg = self.transform(method, msg)
        return Response(msg, headers={"Mcp-Session-Id": "test-session"})
    def get(self, url, **kwargs):
        assert url.startswith("https://jsak.mmtcdn.com/") and kwargs["allow_redirects"] is False
        return Response(b'price-amount children:["\xe2\x82\xb9",o] price-label children:"per adult"')
    def delete(self, url, **kwargs):
        self.deleted = True
        return Response(b"", status=204)


@pytest.mark.asyncio
async def test_protocol_only_read_only_discovered_tools_no_spoof_channel(monkeypatch):
    client = Client(); monkeypatch.setattr(source.aiohttp, "ClientSession", lambda **kwargs: client)
    rows = await source.fetch_makemytrip(TRIP)
    assert len(rows) == 1 and client.deleted
    assert [c["method"] for c in client.calls] == ["initialize", "notifications/initialized", "tools/list", "tools/call", "resources/read"]
    call = client.calls[3]["params"]
    assert call["name"] == "fetch-flights" and "channel" not in call["arguments"]
    assert call["arguments"]["oneWayFlightfilters"] == {"stops": 0}


@pytest.mark.asyncio
@pytest.mark.parametrize("problem", ["id", "error", "schema", "destructive", "huge"])
async def test_protocol_size_error_and_schema_changes_fail_closed(monkeypatch, problem):
    def transform(method, msg):
        if method != "tools/list": return msg
        if problem == "id": msg["id"] = 999
        if problem == "error": msg = {"id": 2, "error": {"message": "invalid"}}
        if problem == "schema": msg["result"]["tools"][0]["annotations"]["readOnlyHint"] = False
        if problem == "destructive": msg["result"]["tools"][0]["annotations"]["destructiveHint"] = True
        if problem == "huge": msg["padding"] = "x" * 500
        return msg
    client = Client(transform); monkeypatch.setattr(source.aiohttp, "ClientSession", lambda **kwargs: client)
    if problem == "huge": monkeypatch.setattr(source, "MAX_BODY", 300)
    with pytest.raises(source.MakeMyTripSourceError):
        await source.fetch_makemytrip(TRIP)
    assert client.deleted
    assert not any(c["method"] == "tools/call" for c in client.calls)


@pytest.mark.asyncio
async def test_whole_operation_deadline_is_explicit(monkeypatch):
    async def stalled(trip): await asyncio.sleep(1)
    monkeypatch.setattr(source, "_fetch", stalled); monkeypatch.setattr(source, "TOTAL_SECONDS", 0.005)
    with pytest.raises(source.MakeMyTripSourceError, match="timed out"):
        await source.fetch_makemytrip(TRIP)


def test_malformed_ambiguous_event_stream_is_rejected():
    assert source._decode(b'data: {"result":{},"id":1}\n\n')["id"] == 1
    for raw in [b"nothing", b"data: {}\ndata: {}", b"[]", b'data: {"error":{"message":"failure"}}']:
        with pytest.raises(source.MakeMyTripSourceError): source._decode(raw)
