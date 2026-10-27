import pytest
import os
import json
from pathlib import Path
from smart_advisor import SmartAdvisor

class MockPredictor:
    async def predict(self, origin, destination, date):
        return {
            "decision": {
                "signal": "MONITOR",
                "urgency": "MEDIUM",
                "confidence": 0.8,
                "reasoning": "Stable prices."
            },
            "scenarios": []
        }

@pytest.mark.asyncio
async def test_round_trip_split_advisor(tmp_path):
    # Setup mock user profile
    config_dir = tmp_path / "config"
    config_dir.mkdir(exist_ok=True)
    profile_path = config_dir / "user_profile.json"
    
    # Save a mock user profile with an HDFC card
    mock_profile = {
        "cardRewardRates": [
            {"bank": "HDFC", "rate": 3.0}
        ]
    }
    profile_path.write_text(json.dumps(mock_profile), encoding="utf-8")
    
    try:
        advisor = SmartAdvisor(db=None, predictor=MockPredictor(), profile_path=profile_path)
        
        trip = {
            "origin": "DEL",
            "destination": "BOM",
            "departure_date": "2026-08-15",
            "return_date": "2026-08-22",
            "trip_type": "round_trip"
        }
        
        # Scraped flights containing outbound and inbound directions
        flights = [
            # Outbound flights
            {
                "id": "outbound-nonstop",
                "flight_number": "6E-101 (DEL ➔ BOM)",
                "airline": "IndiGo",
                "departure_time": "06:00",
                "arrival_time": "08:15",
                "duration": "2h 15m",
                "stops": 0,
                "base_price": 5000.0,
                "final_price": 4500.0,
                "effective_price": 4350.0,
                "best_coupon_code": "MMTHDFC",
                "departure_date": "2026-08-15"
            },
            # Inbound flights
            {
                "id": "inbound-nonstop",
                "flight_number": "AI-202 (BOM ➔ DEL)",
                "airline": "Air India",
                "departure_time": "18:00",
                "arrival_time": "20:15",
                "duration": "2h 15m",
                "stops": 0,
                "base_price": 6000.0,
                "final_price": 5500.0,
                "effective_price": 5335.0,
                "best_coupon_code": "MMTSBI",
                "departure_date": "2026-08-22"
            }
        ]
        
        res = await advisor.get_advisory(trip, flights)
        
        # 1. Verify response structure
        assert res["route"] == "DEL ⇄ BOM"
        assert "2026-08-15 to 2026-08-22" in res["travel_date"]
        
        suggestions = res["suggestions"]
        assert len(suggestions) > 0
        
        # 2. Verify split combo suggestion card
        combo_sug = next((s for s in suggestions if s["type"] == "COMBO"), None)
        assert combo_sug is not None
        assert combo_sug["title"] == "Split-Ticket Round-Trip Strategy"
        assert combo_sug["saving"] == 1315
        assert "separate one-way tickets" in combo_sug["detail"]
        
    finally:
        # Cleanup mock profile
        if profile_path.exists():
            try:
                os.remove(profile_path)
            except Exception:
                pass
