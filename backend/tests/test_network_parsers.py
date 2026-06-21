import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from workers.makemytrip_worker import MakeMyTripWorker
from workers.easemytrip_worker import EaseMyTripWorker
from workers.cleartrip_worker import CleartripWorker

def test_makemytrip_json_parsing():
    worker = MakeMyTripWorker()
    
    # 1. Test standard nested MMT JSON payload
    data = {
        "success": True,
        "searchResult": {
            "flights": [
                {
                    "flightNumber": "6E-2015",
                    "airlineName": "IndiGo",
                    "departureTime": "12:30",
                    "arrivalTime": "14:45",
                    "duration": "2h 15m",
                    "stops": 0,
                    "price": {
                        "amount": 5400.0
                    }
                },
                {
                    "fN": "AI-102",
                    "alN": "Air India",
                    "dt": "06:15",
                    "at": "08:30",
                    "dur": 135,
                    "stp": "1 stop",
                    "pr": {
                        "fB": 6200
                    }
                }
            ]
        }
    }
    
    flights = worker.find_flight_arrays(data)
    assert len(flights) == 2
    
    # Check flight 1
    assert flights[0]["flight_number"] == "6E-2015"
    assert flights[0]["airline"] == "IndiGo"
    assert flights[0]["departure_time"] == "12:30"
    assert flights[0]["arrival_time"] == "14:45"
    assert flights[0]["duration"] == "2h 15m"
    assert flights[0]["stops"] == 0
    assert flights[0]["base_price"] == 5400.0
    
    # Check flight 2
    assert flights[1]["flight_number"] == "AI-102"
    assert flights[1]["airline"] == "Air India"
    assert flights[1]["departure_time"] == "06:15"
    assert flights[1]["arrival_time"] == "08:30"
    assert flights[1]["duration"] == "2h 15m"
    assert flights[1]["stops"] == 1
    assert flights[1]["base_price"] == 6200.0

def test_easemytrip_json_parsing():
    worker = EaseMyTripWorker()
    
    data = {
        "FlightList": [
            {
                "flightNo": "QP-1122",
                "airline": "Akasa Air",
                "depTime": "2026-06-21T21:00:00",
                "arrTime": "2026-06-21T23:10:00",
                "duration": 130,
                "stops": 0,
                "baseFare": 4999.0
            }
        ]
    }
    
    flights = worker.find_flight_arrays(data)
    assert len(flights) == 1
    assert flights[0]["flight_number"] == "QP-1122"
    assert flights[0]["airline"] == "Akasa Air"
    assert flights[0]["departure_time"] == "21:00"
    assert flights[0]["arrival_time"] == "23:10"
    assert flights[0]["duration"] == "2h 10m"
    assert flights[0]["stops"] == 0
    assert flights[0]["base_price"] == 4999.0

def test_cleartrip_json_parsing():
    worker = CleartripWorker()
    
    data = {
        "results": [
            {
                "fn": "SG-501",
                "carrier": "SpiceJet",
                "startTime": 1774098600000, # Epoch ms corresponding to some time
                "endTime": 1774106700000,
                "timeTaken": "2h 15m",
                "stopCount": 0,
                "fare": 5800
            }
        ]
    }
    
    flights = worker.find_flight_arrays(data)
    assert len(flights) == 1
    assert flights[0]["flight_number"] == "SG-501"
    assert flights[0]["airline"] == "SpiceJet"
    # Ensure it parsed the times from epoch milliseconds (HH:MM format)
    assert ":" in flights[0]["departure_time"]
    assert ":" in flights[0]["arrival_time"]
    assert flights[0]["base_price"] == 5800.0
