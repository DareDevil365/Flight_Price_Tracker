import pytest
import os
import json
import shutil
from pathlib import Path
from smart_advisor import SmartAdvisor, parse_duration_to_minutes

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
async def test_parse_duration():
    assert parse_duration_to_minutes("2h 15m") == 135
    assert parse_duration_to_minutes("4h") == 240
    assert parse_duration_to_minutes("45m") == 45
    assert parse_duration_to_minutes("") == 0

@pytest.mark.asyncio
async def test_layover_lounge_advisor(tmp_path):
    # Prepare directories and mock profiles
    config_dir = tmp_path / "config"
    config_dir.mkdir(exist_ok=True)
    profile_path = config_dir / "user_profile.json"
    
    # Save a mock user profile with an HDFC card
    mock_profile = {
        "cardRewardRates": [
            {"bank": "HDFC", "rate": 3.3}
        ]
    }
    profile_path.write_text(json.dumps(mock_profile), encoding="utf-8")
    
    try:
        advisor = SmartAdvisor(db=None, predictor=MockPredictor(), profile_path=profile_path)
        
        trip = {
            "origin": "DEL",
            "destination": "GOI",
            "departure_date": "2026-08-15"
        }
        
        flights = [
            {
                "id": "nonstop-1",
                "flight_number": "6E-101",
                "airline": "IndiGo",
                "departure_time": "06:00",
                "arrival_time": "08:15",
                "duration": "2h 15m",
                "stops": 0,
                "final_price": 6000.0
            },
            {
                "id": "stop-1",
                "flight_number": "6E-205",
                "airline": "IndiGo",
                "departure_time": "12:30",
                "arrival_time": "16:45",
                "duration": "4h 15m",
                "stops": 1,
                "final_price": 4500.0,
                "layover_airport": "BOM"
            }
        ]
        
        # Test Case 1: Lounge Access Available (HDFC card + BOM layover)
        res = await advisor.get_advisory(trip, flights)
        suggestions = res["suggestions"]
        
        layover_sug = next((s for s in suggestions if s["type"] == "LAYOVER"), None)
        assert layover_sug is not None
        assert layover_sug["has_lounge"] is True
        assert layover_sug["matching_card"] == "HDFC"
        assert "Lounge Available" in layover_sug["title"]
        assert "Comfortable Layover" in layover_sug["detail"]
        assert layover_sug["saving"] == 1500
        
        # Test Case 2: Slight Discomfort (No Lounge card)
        profile_path.write_text(json.dumps({"cardRewardRates": []}), encoding="utf-8")
        
        res = await advisor.get_advisory(trip, flights)
        suggestions = res["suggestions"]
        
        layover_sug = next((s for s in suggestions if s["type"] == "LAYOVER"), None)
        assert layover_sug is not None
        assert layover_sug["has_lounge"] is False
        assert "Slight Discomfort" in layover_sug["title"]
        assert "Budget Saver" in layover_sug["detail"]
        assert "earnings" in layover_sug["detail"] or "earns you" in layover_sug["detail"]
        
    finally:
        # Clean up config files created during test
        if profile_path.exists():
            profile_path.unlink()
        try:
            config_dir.rmdir()
        except OSError:
            pass
