"""Read-only diagnosis of MakeMyTrip's public MCP flight tools.

Uses ordinary MCP requests, no account, cookies, identity headers or booking
tools. Keeps responses in memory; writes only selected non-personal findings.
Not a production source or final-payment verifier.
"""
import asyncio
import json
import time
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import aiohttp

ENDPOINT = "https://www.makemytrip.com/ai/mcp?src=cm"


def shape(value, depth=0):
    if depth > 5:
        return type(value).__name__
    if isinstance(value, dict):
        return {k: shape(v, depth+1) for k,v in value.items()}
    if isinstance(value, list):
        return {"count": len(value), "first": shape(value[0], depth+1) if value else None}
    return type(value).__name__


def decode(body):
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        messages = []
        for line in body.splitlines():
            if line.startswith("data:"):
                try:
                    messages.append(json.loads(line[5:].strip()))
                except json.JSONDecodeError:
                    pass
        return messages[-1] if messages else {"unparsed": True}


async def main():
    report = {"endpoint": ENDPOINT, "observed_at": datetime.now(timezone.utc).isoformat(), "cases": [], "production_integrated": False}
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=45)) as client:
        headers = {"Accept": "application/json, text/event-stream"}
        async def rpc(method, params, request_id):
            payload = {"jsonrpc": "2.0", "method": method, "params": params}
            if request_id is not None:
                payload["id"] = request_id
            async with client.post(ENDPOINT, json=payload, headers=headers) as response:
                if response.headers.get("Mcp-Session-Id"):
                    headers["Mcp-Session-Id"] = response.headers["Mcp-Session-Id"]
                body = await response.text()
                return response.status, decode(body) if body else {}
        status, init = await rpc("initialize", {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "flight-finder-read-only-audit", "version": "0.1"}}, 1)
        print(json.dumps({"initialize_http": status, "protocol": init.get("result", {}).get("protocolVersion")}), flush=True)
        if status != 200 or "error" in init:
            return
        headers["MCP-Protocol-Version"] = init.get("result", {}).get("protocolVersion", "2025-03-26")
        await rpc("notifications/initialized", {}, None)
        status, listing = await rpc("tools/list", {}, 2)
        flight_tools = [tool for tool in listing.get("result", {}).get("tools", []) if tool.get("name") in {"fetch-flights", "fetch-flight-fare-calendar"}]
        print(json.dumps({"tools_http": status, "tool_names": [t["name"] for t in flight_tools]}), flush=True)
        report["tool_schemas"] = [{"name": t["name"], "description": t["description"], "inputSchema": t["inputSchema"], "annotations": t.get("annotations")} for t in flight_tools]
        cases = [] if "--resource-only" in sys.argv else [("AMD", "IXC", "20261117"), ("IXC", "AMD", "20270217")]
        for index, (origin, destination, departure) in enumerate(cases, start=3):
            arguments = {"prompt": f"One-way flight {origin} to {destination} on {departure}, one adult Economy", "departureCityCode": origin, "destinationCityCode": destination, "departureDate": departure, "adults": 1, "children": 0, "infants": 0, "cabinClass": "E", "isRoundTrip": False, "sorter": "Cheapest"}
            started = time.monotonic()
            status, result = await rpc("tools/call", {"name": "fetch-flights", "arguments": arguments}, index)
            print(json.dumps({"http": status, "request": arguments, "top_keys": list(result), "error": result.get("error"), "result_keys": list(result.get("result", {}))}), flush=True)
            data = result.get("result", {})
            for block in data.get("content", []):
                if block.get("type") == "text":
                    try:
                        parsed = json.loads(block.get("text", ""))
                        print(json.dumps({"response_shape": shape(parsed)}), flush=True)
                    except (json.JSONDecodeError, TypeError):
                        text_value = block.get("text", "")
                        print(json.dumps({"text_length": len(text_value), "error_text": text_value[:300] if data.get("isError") else None}), flush=True)
            if data.get("structuredContent"):
                structured = data["structuredContent"]
                case = {"http": status, "request": arguments, "elapsed_seconds": round(time.monotonic()-started, 2), "error": structured.get("error"), "has_more": structured.get("hasMoreFlights"), "flights": []}
                query = parse_qs(urlparse(structured.get("listingUrl", "")).query)
                case["listing_query_keys"] = list(query)
                case["listing_criteria"] = {k: v for k,v in query.items() if k.lower() in {"itinerary", "it", "triptype", "pax", "adult", "adults", "paxinfo", "paxtype", "cc", "cabinclass", "currency"}}
                for offer in structured.get("flights", []):
                    segments = [{k: f.get(k) for k in ("departureCity", "arrivalCity", "departureTime", "arrivalTime", "duration", "airline", "flightNumber", "stops")} for f in offer.get("flights", [])]
                    for segment, original in zip(segments, offer.get("flights", [])):
                        segment["legs"] = [{k: leg.get(k) for k in ("marketingAirline", "operatingAirline", "flightNum", "departureInfo", "arrivalInfo", "techStops", "depTime", "arrTime", "durationInMins", "operatingFlightNumber", "travelMode")} for leg in original.get("legs", [])]
                        segment["leg_keys"] = list(original.get("legs", [{}])[0]) if original.get("legs") else []
                    case["flights"].append({"price": offer.get("price"), "journeyDate": offer.get("journeyDate"), "type": offer.get("type"), "cabin": offer.get("services", {}).get("cabinClass"), "fare_type": offer.get("services", {}).get("fareType"), "segments": segments, "service_sections": {name: [row.get("text") for row in rows] for name, rows in offer.get("services", {}).get("sections", {}).items()}})
                case["cache_caveat"] = "Provider response explicitly says results might be cached; no live claim."
                case["fees_caveat"] = "Provider response says final prices and fees are reviewed before booking."
                report["cases"].append(case)
                print(json.dumps({"criteria": case["listing_criteria"], "count": len(case["flights"]), "first": case["flights"][:1], "elapsed_seconds": case["elapsed_seconds"]}), flush=True)
        status, resource = await rpc("resources/read", {"uri": "ui://widget/flights-listing.html"}, 10)
        snippets = []
        for item in resource.get("result", {}).get("contents", []):
            html = item.get("text", "")
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            import re
            observed_assets = re.findall(r'import\("(https://jsak\.mmtcdn\.com/[^"]+)"\)', html)
            print(json.dumps({"public_widget_text_length": len(html), "observed_public_assets": observed_assets}), flush=True)
            for url in observed_assets[:1]:
                async with client.get(url) as response:
                    body = await response.content.read(3_000_001)
                    if len(body) > 3_000_000 or response.status != 200:
                        continue
                    script = body.decode("utf-8", errors="replace")
                    for pattern in [r".{0,70}₹.{0,70}", r".{0,70}INR.{0,70}", r".{0,70}average_price_per_ticket.{0,70}", r".{0,70}\.price.{0,70}"]:
                        snippets += re.findall(pattern, script)[:4]
                    print(json.dumps({"public_asset_bytes": len(body), "observed_price_code": snippets}), flush=True)
            import re
            for pattern in [r".{0,90}average_price_per_ticket.{0,90}", r".{0,90}currency.{0,90}", r".{0,90}INR.{0,90}", r".{0,90}rupee.{0,90}", r".{0,90}₹.{0,90}", r".{0,90}toLocaleString.{0,90}"]:
                snippets += re.findall(pattern, html, flags=re.IGNORECASE)[:3]
        report["widget_read_http"] = status
        report["widget_resource_shape"] = shape(resource)
        report["widget_price_unit"] = "INR" if any("₹" in s for s in snippets) else "unconfirmed"
        report["widget_price_basis"] = "per adult" if any("per adult" in s for s in snippets) else "unconfirmed"
        output = Path(__file__).resolve().parents[2] / "sessions" / "mmt-source-audit" / "public-mcp-findings.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        if not cases and output.exists():
            previous = json.loads(output.read_text(encoding="utf-8"))
            previous.update({key: value for key,value in report.items() if key.startswith("widget_")})
            previous.pop("widget_price_logic_snippets", None)
            report = previous
        output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps({"widget_read_http": status, "price_logic": snippets, "report": str(output)}), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
