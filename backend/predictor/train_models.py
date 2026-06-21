"""
Flight Finder — Model Training & Database Bootstrapping Script
Loads compiled historical prices, populates the SQLite observed_prices table,
and trains/saves XGBoost and Prophet models for all routes.
"""

import os
import sys
import pickle
import sqlite3
from datetime import datetime
from pathlib import Path
import pandas as pd
from loguru import logger

# Add project root to sys path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.append(str(PROJECT_ROOT))

DB_PATH = PROJECT_ROOT / "backend" / "db" / "flight_agent.db"
CSV_PATH = PROJECT_ROOT / "backend" / "predictor" / "historical_dataset.csv"
MODELS_DIR = PROJECT_ROOT / "backend" / "predictor" / "models"

def bootstrap_database():
    """Populate the SQLite observed_prices table with historical dataset records."""
    if not CSV_PATH.exists():
        logger.error(f"Historical dataset CSV not found at {CSV_PATH}. Ingestion aborted.")
        return False

    df = pd.read_csv(CSV_PATH)
    logger.info(f"Loaded {len(df)} historical observations from CSV.")

    # Connect to SQLite
    os.makedirs(DB_PATH.parent, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    # Create table if not exists (in case schema has not run yet)
    cursor.execute("""
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

    # Check if table has data already to avoid duplicate boots
    cursor.execute("SELECT COUNT(*) FROM observed_prices")
    count = cursor.fetchone()[0]
    if count >= 1600:
        logger.info(f"observed_prices table already contains {count} records. Skipping database boost.")
        conn.close()
        return True

    # Clear and insert fresh to ensure proper schema format
    logger.info("Clearing and bootstrapping observed_prices table...")
    cursor.execute("DELETE FROM observed_prices")
    
    insert_rows = []
    for _, row in df.iterrows():
        # Map fields
        route_key = row["route"]
        airline = "IndiGo"  # Default domestic carrier
        # Format booking date to ISO timestamp
        obs_time = f"{row['booking_date']}T12:00:00"
        price = float(row["price_inr"])
        fare_class = "Y"
        seats = 15

        insert_rows.append((route_key, airline, obs_time, price, fare_class, seats))

    cursor.executemany("""
        INSERT INTO observed_prices (route_key, airline, observed_at_timestamp, price, fare_class, seats_remaining_hint, source)
        VALUES (?, ?, ?, ?, ?, ?, 'synthetic')
    """, insert_rows)
    conn.commit()
    logger.info(f"Successfully inserted {len(insert_rows)} price observations into SQLite.")
    conn.close()
    return True

def train_models():
    """Train XGBoost regressors and Prophet time-series models for all routes."""
    if not CSV_PATH.exists():
        logger.error("No historical dataset CSV available for training.")
        return

    os.makedirs(MODELS_DIR, exist_ok=True)
    df = pd.read_csv(CSV_PATH)
    routes = df["route"].unique()
    logger.info(f"Starting model training for routes: {list(routes)}")

    # Features used by Layer 3 XGBoost
    feature_cols = ["days_to_departure", "booking_window_percentile", "hour_of_departure", 
                    "days_since_last_price_drop", "days_to_nearest_public_holiday", 
                    "destination_peak_season_score", "brent_crude_price_usd", "usd_inr_rate"]

    try:
        import xgboost as xgb
        XGB_AVAILABLE = True
    except ImportError:
        logger.warning("XGBoost not available in environment. Skipping XGBoost training.")
        XGB_AVAILABLE = False

    try:
        from prophet import Prophet
        PROPHET_AVAILABLE = True
    except ImportError:
        logger.warning("Prophet not available in environment. Skipping Prophet training.")
        PROPHET_AVAILABLE = False

    for route in routes:
        route_df = df[df["route"] == route].copy()
        logger.info(f"--- Training models for {route} ({len(route_df)} rows) ---")

        # Map training features to prediction names
        route_df["booking_window_percentile"] = (route_df["days_to_departure"] / 90.0 * 100.0).clip(0, 100)
        route_df["hour_of_departure"] = 12.0
        route_df["days_since_last_price_drop"] = 3.0
        route_df["days_to_nearest_public_holiday"] = route_df["days_to_nearest_festival"]
        route_df["destination_peak_season_score"] = route_df["seasonality_score"]
        route_df["brent_crude_price_usd"] = route_df["brent_crude_usd"]
        route_df["usd_inr_rate"] = route_df["usd_inr"]

        # 1. Train XGBoost
        if XGB_AVAILABLE:
            try:
                X = route_df[feature_cols].astype(float)
                y = route_df["price_inr"].astype(float)

                model = xgb.XGBRegressor(
                    n_estimators=120,
                    max_depth=5,
                    learning_rate=0.07,
                    random_state=42
                )
                model.fit(X, y)

                model_path = MODELS_DIR / f"xgboost_{route}.pkl"
                with open(model_path, "wb") as f:
                    pickle.dump(model, f)
                logger.info(f"Saved XGBoost model: {model_path}")
            except Exception as e:
                logger.error(f"Failed to train XGBoost for {route}: {e}")

        # 2. Train Prophet
        if PROPHET_AVAILABLE:
            try:
                # Prophet expects ds (date) and y (target)
                pdf = pd.DataFrame()
                pdf["ds"] = pd.to_datetime(route_df["travel_date"])
                pdf["y"] = route_df["price_inr"].astype(float)

                # Deduplicate by ds using mean price
                pdf = pdf.groupby("ds")["y"].mean().reset_index()

                m = Prophet(
                    yearly_seasonality=True,
                    weekly_seasonality=True,
                    daily_seasonality=False
                )
                m.fit(pdf)

                model_path = MODELS_DIR / f"prophet_{route}.pkl"
                with open(model_path, "wb") as f:
                    pickle.dump(m, f)
                logger.info(f"Saved Prophet model: {model_path}")
            except Exception as e:
                logger.error(f"Failed to train Prophet for {route}: {e}")

    logger.info("✅ Model training process complete.")

if __name__ == "__main__":
    bootstrap_database()
    train_models()
