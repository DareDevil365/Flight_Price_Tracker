"""
Unit & Integration Tests for Upgraded Flight Price Trend Predictor
"""

import sys
import os
import asyncio
import pytest
import aiosqlite

# Add backend to python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from price_predictor import PricePredictor
from predictor.pipeline import FeaturePipeline
from predictor.rules import Layer1RulesEngine


class MockDB:
    def __init__(self, conn):
        self.db = conn


@pytest.mark.asyncio
async def test_cyclical_encoding():
    """Verify that cyclical math coordinates are correctly mapped between -1 and 1."""
    pipeline = FeaturePipeline()
    dt = datetime = __import__("datetime").datetime(2026, 7, 15, 12, 0)
    cycle_feats = await pipeline.get_cyclical_features(dt, hour=12)

    assert "month_of_year_sin" in cycle_feats
    assert "month_of_year_cos" in cycle_feats
    assert "week_of_year_sin" in cycle_feats
    assert "week_of_year_cos" in cycle_feats

    # Since July (month 7) is in middle: sin is close to 0, cos close to -1
    # 2*pi * 7/12 = 3.665 radians. sin(3.66) = -0.5, cos(3.66) = -0.866
    assert abs(cycle_feats["month_of_year_sin"] - (-0.5)) < 0.1
    assert abs(cycle_feats["month_of_year_cos"] - (-0.866)) < 0.1


@pytest.mark.asyncio
async def test_layer1_rules_engine():
    """Verify that the rules engine triggers BUY_NOW / WAIT correctly on boundaries."""
    engine = Layer1RulesEngine()

    # Rule 1: High Urgency (< 7 days departure, < 10 seats)
    feats = {
        "days_to_departure": 5,
        "seats_remaining_estimate": 7
    }
    res = engine.evaluate(feats)
    assert res["signal"] == "BUY_NOW"
    assert "seats remaining" in res["rule_triggered"]

    # Rule 3: Anomaly low percentile
    feats = {
        "days_to_departure": 30,
        "seats_remaining_estimate": 50,
        "price_percentile_last_90_days": 10
    }
    res = engine.evaluate(feats)
    assert res["signal"] == "BUY_NOW"
    assert "percentile" in res["rule_triggered"]

    # Rule 4: Airline Sale Active
    feats = {
        "days_to_departure": 30,
        "seats_remaining_estimate": 50,
        "price_percentile_last_90_days": 60,
        "airline_sale_window_active": True
    }
    res = engine.evaluate(feats)
    assert res["signal"] == "WAIT"
    assert "sale window" in res["rule_triggered"]


@pytest.mark.asyncio
async def test_price_predictor_end_to_end():
    """Verify end to end prediction runs, logs to SQLite, and conforms to Section 4 JSON structure."""
    # Open in-memory temporary database
    async with aiosqlite.connect(":memory:") as conn:
        mock_db = MockDB(conn)
        
        # Initialize schema
        schema_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "db", "schema.sql")
        if os.path.exists(schema_path):
            with open(schema_path, "r", encoding="utf-8") as sf:
                await conn.executescript(sf.read())
                await conn.commit()

        # Initialize PricePredictor
        predictor = PricePredictor(mock_db)
        await predictor.storage.initialize_tables()

        # Seed mock observations for "DEL-GOI"
        # We write 40 observations so we bypass cold start check for Prophet (needs >= 30)
        now = __import__("datetime").datetime.now()
        for i in range(40):
            obs_time = (now - __import__("datetime").timedelta(days=i)).isoformat()
            # Log price history
            await conn.execute("""
                INSERT INTO price_history (route, departure_date, airline, price, platform, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, ("DEL-GOI", "2026-07-15", "IndiGo", 5400 - (i * 10) if i < 20 else 5200, "makemytrip", obs_time))
            # Log observed_prices
            await conn.execute("""
                INSERT INTO observed_prices (route_key, airline, observed_at_timestamp, price, fare_class, seats_remaining_hint)
                VALUES (?, ?, ?, ?, ?, ?)
            """, ("DEL-GOI", "IndiGo", obs_time, 5400 - (i * 10) if i < 20 else 5200, "Y", 15))
        await conn.commit()

        # Run Prediction
        res = await predictor.predict("DEL-GOI", "2026-07-15")

        # Assert JSON Structure (Section 4)
        assert res["route"] == "DEL → GOI"
        assert res["travel_date"] == "2026-07-15"
        assert "current_price" in res
        assert res["currency"] == "INR"

        # Decision
        assert "decision" in res
        assert res["decision"]["signal"] in ["BOOK_NOW", "WAIT", "MONITOR"]
        assert res["decision"]["urgency"] in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
        assert 0.0 <= res["decision"]["confidence"] <= 1.0
        assert "recommended_book_by" in res["decision"]
        assert "expected_price_on_book_by_date" in res["decision"]
        assert "potential_savings" in res["decision"]

        # Forecast
        assert "forecast" in res
        assert "price_7d" in res["forecast"]
        assert "price_14d" in res["forecast"]
        assert "price_30d" in res["forecast"]
        assert res["forecast"]["direction"] in ["RISING", "FALLING", "STABLE", "VOLATILE"]
        assert "low" in res["forecast"]["confidence_band"]
        assert "high" in res["forecast"]["confidence_band"]

        # Context
        assert "price_context" in res
        assert "vs_90d_average" in res["price_context"]
        assert "percentile_90d" in res["price_context"]
        assert "all_time_low_this_route" in res["price_context"]

        # Drivers & Flags
        assert isinstance(res["key_drivers"], list)
        assert len(res["key_drivers"]) > 0
        assert "factor" in res["key_drivers"][0]
        assert "impact" in res["key_drivers"][0]
        assert "magnitude" in res["key_drivers"][0]

        assert isinstance(res["risk_flags"], list)
        assert len(res["risk_flags"]) > 0

        # Strategy
        assert "best_day_to_book" in res["optimal_booking_strategy"]
        assert "best_time_to_book" in res["optimal_booking_strategy"]

        # Freshness
        assert "price_data_age_minutes" in res["data_freshness"]
        assert "model_trained_date" in res["data_freshness"]

        print("🎉 All upgraded predictor E2E assertions passed successfully!")


if __name__ == "__main__":
    # If run directly, run E2E test
    asyncio.run(test_price_predictor_end_to_end())
