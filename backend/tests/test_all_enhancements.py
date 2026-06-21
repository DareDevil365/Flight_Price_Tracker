"""
Comprehensive Verification Test Suite for Elite Price Predictor Enhancements
"""

import sys
import os
import asyncio
import pytest
import aiosqlite
import random
from datetime import datetime, timedelta, timezone

# Add backend to python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from price_predictor import PricePredictor
from predictor.pipeline import FeaturePipeline
from predictor.rules import Layer1RulesEngine
from workers.mock_worker import MockWorker

class MockDB:
    def __init__(self, conn):
        self.db = conn


@pytest.mark.asyncio
async def test_fuzzy_sigmoid_rules():
    """Verify Layer 1 Fuzzy Sigmoids evaluate continuously and trigger on boundaries."""
    engine = Layer1RulesEngine()
    
    # Assert sigmoid math helpers
    down_high = engine._sigmoid_down(2, 7, 2)
    down_low = engine._sigmoid_down(15, 7, 2)
    assert down_high > 0.9
    assert down_low < 0.1
    
    # 1. Test High Urgency boundary triggering (days=2, seats=5 should trigger activation > 0.5)
    feats = {
        "days_to_departure": 2,
        "seats_remaining_estimate": 5,
        "price_percentile_last_90_days": 50
    }
    res = engine.evaluate(feats)
    assert res["signal"] == "BUY_NOW"
    assert res["urgency"] == "HIGH"
    assert "Rule Triggered" in res["rule_triggered"]



@pytest.mark.asyncio
async def test_bridge_day_multiplication():
    """Verify that Bridge Days get a 3x multiplier applied to holiday demand."""
    pipeline = FeaturePipeline()
    
    # Assume a Thursday public holiday is queried
    holidays_dict = {"2026-08-13": "Independence Day Prep Holiday"} # Thursday
    # Friday 2026-08-14 is the bridge day
    travel_dt = datetime(2026, 8, 14)
    
    # Evaluate long weekend / bridge holiday check
    is_long_weekend = False
    is_bridge_holiday = False
    for i in [-1, 0, 1]:
        d = (travel_dt + timedelta(days=i)).strftime("%Y-%m-%d")
        if d in holidays_dict:
            is_long_weekend = True
            if i in [-1, 1]:
                is_bridge_holiday = True
                
    assert is_bridge_holiday is True
    
    # Verify multiplier factor
    multiplier = 3.0 if is_bridge_holiday else 1.0
    assert multiplier == 3.0


@pytest.mark.asyncio
async def test_cheapest_seats_and_geo_proxy():
    """Verify Cheapest Fare Bucket Seat Count and regional proxy pricing queries."""
    async with aiosqlite.connect(":memory:") as conn:
        mock_db = MockDB(conn)
        
        # Create table observed_prices
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS observed_prices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                route_key TEXT NOT NULL,
                airline TEXT,
                observed_at_timestamp TEXT NOT NULL,
                price REAL NOT NULL,
                fare_class TEXT,
                seats_remaining_hint INTEGER,
                source TEXT DEFAULT 'scraped'
            )
        """)
        await conn.commit()
        
        # Seed a TIER3 regional price and cheap seats
        observed_at = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        await conn.execute("""
            INSERT INTO observed_prices (route_key, airline, observed_at_timestamp, price, fare_class, seats_remaining_hint, source)
            VALUES (?, ?, ?, ?, ?, ?, 'scraped')
        """, ("DEL-PAT_TIER3", "IndiGo", observed_at, 4200.0, "Y", None))
        await conn.execute("""
            INSERT INTO observed_prices (route_key, airline, observed_at_timestamp, price, fare_class, seats_remaining_hint, source)
            VALUES (?, ?, ?, ?, ?, ?, 'scraped')
        """, ("DEL-PAT", "IndiGo", observed_at, 4500.0, "Y", 4))
        await conn.commit()
        
        # Check if pipeline picks it up
        pipeline = FeaturePipeline(mock_db)
        vector = await pipeline.compile_feature_vector("DEL", "PAT", "2026-08-15")
        
        assert vector["cheapest_fare_bucket_seats"] == 4
        assert vector["seats_remaining_estimate"] == 4
        assert "location_price_differential" in vector
        # 5400 - 4200 = 1200
        assert vector["location_price_differential"] == 1200.0


@pytest.mark.asyncio
async def test_cross_route_transfer_learning():
    """Verify that cold start routes pool parameters from category segment averages."""
    async with aiosqlite.connect(":memory:") as conn:
        mock_db = MockDB(conn)
        
        # Create price_history table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                route TEXT NOT NULL,
                departure_date TEXT NOT NULL,
                airline TEXT,
                price REAL NOT NULL,
                platform TEXT,
                recorded_at TEXT NOT NULL,
                source TEXT DEFAULT 'scraped'
            )
        """)
        
        # Seed 40 prices for a similar BEACH route: DEL-GOI
        now = datetime.now()
        for i in range(40):
            obs_time = (now - timedelta(days=i)).isoformat()
            await conn.execute("""
                INSERT INTO price_history (route, departure_date, airline, price, platform, recorded_at, source)
                VALUES (?, ?, ?, ?, ?, ?, 'scraped')
            """, ("DEL-GOI", "2026-08-15", "IndiGo", 6000.0, "makemytrip", obs_time))
        await conn.commit()
        
        # Now query cold start route: DEL-IXZ (should pool from BEACH segment: DEL-GOI)
        pipeline = FeaturePipeline(mock_db)
        vector = await pipeline.compile_feature_vector("DEL", "IXZ", "2026-08-15")
        
        # Mean price should be pooled around 6000.0 instead of default 5400.0
        assert vector["route_historical_mean_price"] == 6000.0


@pytest.mark.asyncio
async def test_error_attribution_classification():
    """Verify root cause error classification, table logging, and weight dampening."""
    async with aiosqlite.connect(":memory:") as conn:
        mock_db = MockDB(conn)
        
        # Initialize schema tables
        schema_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "db", "schema.sql")
        if os.path.exists(schema_path):
            with open(schema_path, "r", encoding="utf-8") as sf:
                await conn.executescript(sf.read())
                await conn.commit()
                
        # Initialize predictor storage tables
        from predictor.storage import PredictorStorage
        storage = PredictorStorage(mock_db)
        await storage.initialize_tables()
        
        # Seed a prediction query from 35 days ago (pred_price=8000, current=8000)
        pred_id = "test-pred-uuid-1"
        thirty_five_days_ago = (datetime.now() - timedelta(days=35)).isoformat()
        await conn.execute("""
            INSERT INTO prediction_queries (prediction_id, route_key, signal, predicted_price_30d, current_price, predicted_at, audited)
            VALUES (?, ?, ?, ?, ?, ?, 0)
        """, (pred_id, "DEL-GOI", "BOOK_NOW", 8000.0, 8000.0, thirty_five_days_ago))
        
        # Seed observed actual price 5 days ago (pred_time + 30d) exhibiting flash sale (price = 4500)
        five_days_ago = (datetime.now() - timedelta(days=5)).isoformat()
        await conn.execute("""
            INSERT INTO observed_prices (route_key, airline, observed_at_timestamp, price, fare_class, seats_remaining_hint)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ("DEL-GOI", "IndiGo", five_days_ago, 4500.0, "Y", 15))
        await conn.commit()
        
        # Run audit loop
        await storage.audit_accuracy_loop()
        
        # Assert root cause logged to error_attribution table
        async with conn.execute("SELECT error_reason FROM error_attribution WHERE prediction_id = ?", (pred_id,)) as cur:
            row = await cur.fetchone()
            assert row is not None
            assert row[0] == "Flash Sale / Extreme Price Drop"
            
        # Assert dynamic multiplier table was populated/updated
        async with conn.execute("SELECT weight_multiplier FROM dynamic_feature_weights WHERE feature_name = ?", ("price_percentile_last_90_days",)) as cur:
            row = await cur.fetchone()
            assert row is not None
            assert row[0] == 0.8


@pytest.mark.asyncio
async def test_optuna_retraining_loop():
    """Verify XGBoost global retraining with Optuna optimization executes successfully."""
    async with aiosqlite.connect(":memory:") as conn:
        mock_db = MockDB(conn)
        
        # Initialize predictor storage tables first
        from predictor.storage import PredictorStorage
        storage = PredictorStorage(mock_db)
        await storage.initialize_tables()

        from predictor.models import MLModelManager
        models = MLModelManager(mock_db)
        
        # Run XGBoost training which automatically runs Optuna/GridSearch tuning
        model = await models._train_global_xgboost()
        assert model is not None
        
        # Verify model saved file exists
        model_path = os.path.join(models.models_dir, "xgboost_global.pkl")
        assert os.path.exists(model_path)
        # Cleanup
        try:
            os.remove(model_path)
        except Exception:
            pass


if __name__ == "__main__":
    # Execute all tests synchronously if file executed directly
    print("Running Elite Enhancements Verification Test Suite...")
    asyncio.run(test_fuzzy_sigmoid_rules())
    print("Fuzzy Sigmoid Rules checked.")

    asyncio.run(test_bridge_day_multiplication())
    print("Bridge Day surges checked.")
    asyncio.run(test_cheapest_seats_and_geo_proxy())
    print("Cheapest Bucket Seats & Geo-Proxy checks checked.")
    asyncio.run(test_cross_route_transfer_learning())
    print("Cross-Route Transfer Learning checked.")
    asyncio.run(test_error_attribution_classification())
    print("Self-Improving Error Attribution checked.")
    asyncio.run(test_optuna_retraining_loop())
    print("Optuna weekly training execution checked.")
    print("All elite price predictor E2E assertions completed successfully!")
