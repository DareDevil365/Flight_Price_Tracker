"""
Flight Finder — SQLite Storage & Performance Auditing Loop
Logs price observations, predictions, and calculates MAPE for weekly retraining decisions.
"""

import uuid
import sys
import asyncio
from datetime import datetime, timedelta
from loguru import logger
from pathlib import Path

class PredictorStorage:
    def __init__(self, db):
        self.db = db

    async def initialize_tables(self):
        """Create predictor specific SQLite tables if they do not exist."""
        try:
            conn = self.db.db
            # Observed prices log
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
            # Prediction query log for audits
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS prediction_queries (
                    prediction_id TEXT PRIMARY KEY,
                    route_key TEXT NOT NULL,
                    signal TEXT NOT NULL,
                    predicted_price_30d REAL NOT NULL,
                    current_price REAL NOT NULL,
                    predicted_at TEXT NOT NULL,
                    actual_price_30d REAL,
                    prediction_error REAL,
                    audited INTEGER DEFAULT 0
                )
            """)
            # Model performance tracking
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS model_performance (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    route_key TEXT NOT NULL,
                    mape REAL NOT NULL,
                    predictions_evaluated INTEGER NOT NULL,
                    calculated_at TEXT NOT NULL,
                    needs_retraining INTEGER DEFAULT 0
                )
            """)
            # Error attribution classification log
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS error_attribution (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    prediction_id TEXT NOT NULL,
                    route_key TEXT NOT NULL,
                    mape REAL NOT NULL,
                    error_reason TEXT NOT NULL,
                    attributed_at TEXT NOT NULL
                )
            """)
            # Dynamic feature weights configuration
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS dynamic_feature_weights (
                    feature_name TEXT PRIMARY KEY,
                    weight_multiplier REAL DEFAULT 1.0
                )
            """)
            await conn.commit()
            
            # Migration check for ensemble details in prediction_queries
            try:
                async with conn.execute("PRAGMA table_info(prediction_queries)") as cur:
                    columns = [row[1] for row in await cur.fetchall()]
                    if "rules_signal" not in columns:
                        await conn.execute("ALTER TABLE prediction_queries ADD COLUMN rules_signal TEXT")
                    if "prophet_price_30d" not in columns:
                        await conn.execute("ALTER TABLE prediction_queries ADD COLUMN prophet_price_30d REAL")
                    if "xgboost_price_30d" not in columns:
                        await conn.execute("ALTER TABLE prediction_queries ADD COLUMN xgboost_price_30d REAL")
                    if "rules_error" not in columns:
                        await conn.execute("ALTER TABLE prediction_queries ADD COLUMN rules_error REAL")
                    if "prophet_error" not in columns:
                        await conn.execute("ALTER TABLE prediction_queries ADD COLUMN prophet_error REAL")
                    if "xgboost_error" not in columns:
                        await conn.execute("ALTER TABLE prediction_queries ADD COLUMN xgboost_error REAL")
                    await conn.commit()
                    logger.info("Migrated prediction_queries table: added ensemble fields.")
            except Exception as e:
                logger.error(f"Failed to migrate prediction_queries: {e}")

            # Migration check for ensemble accuracies in model_performance
            try:
                async with conn.execute("PRAGMA table_info(model_performance)") as cur:
                    columns = [row[1] for row in await cur.fetchall()]
                    if "rules_accuracy" not in columns:
                        await conn.execute("ALTER TABLE model_performance ADD COLUMN rules_accuracy REAL")
                    if "prophet_mape" not in columns:
                        await conn.execute("ALTER TABLE model_performance ADD COLUMN prophet_mape REAL")
                    if "xgboost_mape" not in columns:
                        await conn.execute("ALTER TABLE model_performance ADD COLUMN xgboost_mape REAL")
                    await conn.commit()
                    logger.info("Migrated model_performance table: added ensemble fields.")
            except Exception as e:
                logger.error(f"Failed to migrate model_performance: {e}")

            logger.info("✅ Predictor SQLite tables verified/initialized")
        except Exception as e:
            logger.error(f"Failed to initialize predictor SQLite tables: {e}")

    async def log_observation(self, route_key: str, airline: str, price: float, fare_class: str = None, seats_remaining: int = None):
        """Log a price observation to SQLite."""
        try:
            conn = self.db.db
            observed_at = datetime.now().isoformat()
            await conn.execute("""
                INSERT INTO observed_prices (route_key, airline, observed_at_timestamp, price, fare_class, seats_remaining_hint)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (route_key, airline, observed_at, price, fare_class, seats_remaining))
            await conn.commit()
        except Exception as e:
            logger.warning(f"Failed to log price observation to SQLite: {e}")

    async def log_prediction(self, prediction_id: str, route_key: str, signal: str, predicted_price_30d: float, current_price: float,
                             rules_signal: str = None, prophet_price_30d: float = None, xgboost_price_30d: float = None) -> str:
        """Store the prediction query details for auditing 30 days later."""
        try:
            conn = self.db.db
            predicted_at = datetime.now().isoformat()
            await conn.execute("""
                INSERT INTO prediction_queries (
                    prediction_id, route_key, signal, predicted_price_30d, current_price, predicted_at,
                    rules_signal, prophet_price_30d, xgboost_price_30d
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (prediction_id, route_key, signal, predicted_price_30d, current_price, predicted_at,
                  rules_signal, prophet_price_30d, xgboost_price_30d))
            await conn.commit()
            return prediction_id
        except Exception as e:
            logger.warning(f"Failed to log prediction query to SQLite: {e}")
            return prediction_id

    async def audit_accuracy_loop(self):
        """
        Run audit check for predictions made >= 30 days ago.
        Looks up actual price in observed_prices at (predicted_at + 30 days) and computes MAPE.
        If last 20 predictions' MAPE > 25%, triggers flag for retraining.
        """
        try:
            conn = self.db.db
            now = datetime.now()
            thirty_days_ago = (now - timedelta(days=30)).isoformat()

            # Find unaudited predictions made >= 30 days ago
            query = """
                SELECT prediction_id, route_key, predicted_price_30d, predicted_at, current_price,
                       rules_signal, prophet_price_30d, xgboost_price_30d
                FROM prediction_queries 
                WHERE audited = 0 AND predicted_at <= ?
            """
            async with conn.execute(query, (thirty_days_ago,)) as cursor:
                rows = await cursor.fetchall()
                for row in rows:
                    pred_id, route_key, pred_price, pred_at_str, current_price, rules_signal, prophet_price_30d, xgboost_price_30d = row
                    pred_at = datetime.fromisoformat(pred_at_str)
                    target_time = pred_at + timedelta(days=30)
                    target_start = (target_time - timedelta(days=3)).isoformat()
                    target_end = (target_time + timedelta(days=3)).isoformat()
 
                    # Find actual observed price around that date
                    obs_query = """
                        SELECT price FROM observed_prices 
                        WHERE route_key = ? AND observed_at_timestamp BETWEEN ? AND ?
                        ORDER BY ABS(julianday(observed_at_timestamp) - julianday(?)) ASC
                        LIMIT 1
                    """
                    async with conn.execute(obs_query, (route_key, target_start, target_end, target_time.isoformat())) as obs_cursor:
                        obs_row = await obs_cursor.fetchone()
                        if obs_row:
                            actual_price = obs_row[0]
                            # Calculate MAPE
                            mape = abs(actual_price - pred_price) / actual_price
                            
                            # Calculate individual layer errors
                            prophet_err = None
                            if prophet_price_30d is not None and actual_price > 0:
                                prophet_err = abs(actual_price - prophet_price_30d) / actual_price

                            xgb_err = None
                            if xgboost_price_30d is not None and actual_price > 0:
                                xgb_err = abs(actual_price - xgboost_price_30d) / actual_price

                            rules_err = None
                            if rules_signal in ["BUY_NOW", "WAIT"]:
                                price_went_up = actual_price > current_price
                                if (rules_signal == "BUY_NOW" and price_went_up) or (rules_signal == "WAIT" and not price_went_up):
                                    rules_err = 0.0
                                else:
                                    rules_err = 1.0

                            # Update query record with ensemble errors
                            await conn.execute("""
                                UPDATE prediction_queries 
                                SET actual_price_30d = ?, prediction_error = ?,
                                    rules_error = ?, prophet_error = ?, xgboost_error = ?,
                                    audited = 1 
                                WHERE prediction_id = ?
                            """, (actual_price, mape, rules_err, prophet_err, xgb_err, pred_id))

                            # Self-Improving Error Attribution: Classify root cause if MAPE > 25%
                            if mape > 0.25:
                                # Classify using the enhanced 12-category classifier in SelfLearningEngine
                                error_reason = "General Prediction Variance"
                                adjust_feature = "booking_window_percentile"
                                adjust_factor = 0.95
                                
                                try:
                                    # Ensure paths are configured to find learning_engine
                                    backend_dir = Path(__file__).parent.parent
                                    if str(backend_dir) not in sys.path:
                                        sys.path.append(str(backend_dir))
                                    from learning_engine import SelfLearningEngine
                                    
                                    engine = SelfLearningEngine(self.db)
                                    error_reason = engine._classify_prediction_error(
                                        mape, pred_at, current_price, actual_price, route_key
                                    )
                                except Exception as ex:
                                    logger.warning(f"Failed to use SelfLearningEngine for error classification: {ex}")

                                # Map 12+ categories to feature scaling multipliers
                                if "Flash Sale" in error_reason:
                                    adjust_feature = "price_percentile_last_90_days"
                                    adjust_factor = 0.80
                                elif "Demand Surge" in error_reason:
                                    adjust_feature = "price_velocity"
                                    adjust_factor = 0.90
                                elif "Diwali" in error_reason or "Festive" in error_reason:
                                    adjust_feature = "holiday_pressure_score"
                                    adjust_factor = 1.15
                                elif "Christmas" in error_reason or "NYE" in error_reason:
                                    adjust_feature = "holiday_pressure_score"
                                    adjust_factor = 1.15
                                elif "Monsoon" in error_reason:
                                    adjust_feature = "destination_monsoon_active"
                                    adjust_factor = 0.85
                                elif "Vacation" in error_reason:
                                    adjust_feature = "is_school_vacation_period"
                                    adjust_factor = 1.10
                                elif "Exam" in error_reason:
                                    adjust_feature = "is_exam_period"
                                    adjust_factor = 0.75
                                elif "Weekend" in error_reason:
                                    adjust_feature = "is_weekend_travel"
                                    adjust_factor = 1.10
                                elif "Fuel" in error_reason or "FX" in error_reason:
                                    adjust_feature = "brent_crude_price_usd"
                                    adjust_factor = 1.05
                                elif "Competition" in error_reason or "Entrant" in error_reason:
                                    adjust_feature = "num_airlines_on_route"
                                    adjust_factor = 0.85
                                elif "Drift" in error_reason or "Staleness" in error_reason:
                                    adjust_feature = "days_to_departure"
                                    adjust_factor = 0.90

                                # Log the attributed cause
                                await conn.execute("""
                                    INSERT INTO error_attribution (prediction_id, route_key, mape, error_reason, attributed_at)
                                    VALUES (?, ?, ?, ?, ?)
                                """, (pred_id, route_key, mape, error_reason, now.isoformat()))
                                
                                # Adjust feature weight multiplier dynamically
                                await conn.execute("""
                                    INSERT INTO dynamic_feature_weights (feature_name, weight_multiplier)
                                    VALUES (?, ?)
                                    ON CONFLICT(feature_name) DO UPDATE SET weight_multiplier = weight_multiplier * ?
                                """, (adjust_feature, adjust_factor, adjust_factor))
                                logger.warning(f"[ErrorAttribution] Prediction {pred_id} error {mape:.2%}: classified as {error_reason}. Scaling '{adjust_feature}' multiplier by {adjust_factor}.")

            await conn.commit()

            # Now evaluate recent performance (last 20 audited predictions) per route
            routes_query = "SELECT DISTINCT route_key FROM prediction_queries WHERE audited = 1"
            async with conn.execute(routes_query) as cursor:
                routes = [r[0] for r in await cursor.fetchall()]

            for r_key in routes:
                perf_query = """
                    SELECT prediction_error, rules_error, prophet_error, xgboost_error 
                    FROM prediction_queries 
                    WHERE route_key = ? AND audited = 1 
                    ORDER BY predicted_at DESC LIMIT 20
                """
                async with conn.execute(perf_query, (r_key,)) as cursor:
                    p_rows = await cursor.fetchall()
                    if len(p_rows) >= 5:  # Needs at least 5 audited predictions to flag
                        errors = [row[0] for row in p_rows if row[0] is not None]
                        rules_errors = [row[1] for row in p_rows if row[1] is not None]
                        prophet_errors = [row[2] for row in p_rows if row[2] is not None]
                        xgb_errors = [row[3] for row in p_rows if row[3] is not None]

                        avg_mape = sum(errors) / len(errors) if errors else 0.0
                        avg_rules = (len(rules_errors) - sum(rules_errors)) / len(rules_errors) if rules_errors else None
                        avg_prophet = sum(prophet_errors) / len(prophet_errors) if prophet_errors else None
                        avg_xgb = sum(xgb_errors) / len(xgb_errors) if xgb_errors else None

                        needs_retrain = 1 if avg_mape > 0.25 else 0

                        await conn.execute("""
                            INSERT INTO model_performance (
                                route_key, mape, predictions_evaluated, calculated_at, needs_retraining,
                                rules_accuracy, prophet_mape, xgboost_mape
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """, (r_key, avg_mape, len(p_rows), now.isoformat(), needs_retrain, avg_rules, avg_prophet, avg_xgb))
                        await conn.commit()

                        if needs_retrain == 1:
                            # Automatically trigger XGBoost/Prophet model retraining
                            await self.trigger_retraining(r_key)
            logger.info("🎯 Predictor self-improving audit completed")
        except Exception as e:
            logger.error(f"Error executing predictor accuracy audit loop: {e}")

    async def trigger_retraining(self, route_key: str):
        """Invoke model retraining pipeline."""
        logger.info(f"🔄 [Retraining] Triggering model retraining for route: {route_key}")
        try:
            cmd = [sys.executable, "-m", "predictor.train_models"]
            cwd = str(Path(__file__).parent.parent)  # backend directory
            
            # Start retraining asynchronously as a background task
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            async def wait_for_process():
                stdout, stderr = await process.communicate()
                if process.returncode == 0:
                    logger.info(f"✅ [Retraining] Successfully retrained models for route: {route_key}")
                else:
                    logger.error(f"❌ [Retraining] Retraining failed for route {route_key}. Stderr: {stderr.decode()}")
            
            asyncio.create_task(wait_for_process())
        except Exception as e:
            logger.error(f"Failed to trigger model retraining: {e}")

    async def get_route_performance(self, route_key: str) -> dict:
        """Get the latest model performance and retraining status for a route."""
        try:
            conn = self.db.db
            query = """
                SELECT mape, needs_retraining, rules_accuracy, prophet_mape, xgboost_mape FROM model_performance 
                WHERE route_key = ? 
                ORDER BY calculated_at DESC LIMIT 1
            """
            async with conn.execute(query, (route_key,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return {
                        "mape": row[0],
                        "needs_retraining": bool(row[1]),
                        "rules_accuracy": row[2],
                        "prophet_mape": row[3],
                        "xgboost_mape": row[4]
                    }
        except Exception as e:
            logger.warning(f"Failed to fetch route performance for {route_key}: {e}")
        return {"mape": 0.0, "needs_retraining": False, "rules_accuracy": None, "prophet_mape": None, "xgboost_mape": None}
