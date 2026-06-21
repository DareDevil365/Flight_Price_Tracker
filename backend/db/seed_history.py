"""
Flight Finder — Historical Price Seeder & Dataset Generator
Generates c:/Users/yasha/Desktop/Flight Finder/backend/predictor/historical_dataset.csv
containing 12 months of price trends for DEL-GOI, DEL-BOM, BOM-GOI,
and seeds the price_history and observed_prices tables in SQLite.
"""

import os
import csv
import random
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta

DB_PATH = Path(__file__).parent.parent / "db" / "flight_agent.db"
CSV_PATH = Path(__file__).parent.parent / "predictor" / "historical_dataset.csv"


def generate_and_seed_history():
    print("[INFO] Starting historical dataset generation & database seeding...")
    
    # Ensure directories exist
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Setup database connection
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    # Create tables if not exists
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
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            route TEXT NOT NULL,
            departure_date TEXT NOT NULL,
            airline TEXT,
            flight_number TEXT,
            price REAL NOT NULL,
            platform TEXT NOT NULL,
            cabin_class TEXT DEFAULT 'ECONOMY',
            source TEXT DEFAULT 'scraped',
            recorded_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()

    # Generation parameters
    routes = [
        {"route": "DEL-GOI", "base_price": 5200.0, "season_mult": {1: 1.2, 2: 1.2, 3: 0.9, 4: 0.8, 5: 0.8, 6: 0.6, 7: 0.5, 8: 0.5, 9: 0.7, 10: 1.0, 11: 1.2, 12: 1.3}},
        {"route": "DEL-BOM", "base_price": 4600.0, "season_mult": {1: 1.0, 2: 1.0, 3: 1.0, 4: 1.0, 5: 1.0, 6: 0.9, 7: 0.8, 8: 0.8, 9: 1.0, 10: 1.0, 11: 1.0, 12: 1.1}},
        {"route": "BOM-GOI", "base_price": 3800.0, "season_mult": {1: 1.2, 2: 1.1, 3: 0.9, 4: 0.8, 5: 0.8, 6: 0.6, 7: 0.5, 8: 0.5, 9: 0.7, 10: 1.0, 11: 1.2, 12: 1.3}}
    ]
    
    airlines = [
        {"code": "6E", "name": "IndiGo", "flights": ["204", "312", "501"]},
        {"code": "AI", "name": "Air India", "flights": ["805", "624", "415"]},
        {"code": "QP", "name": "Akasa Air", "flights": ["112", "208"]}
    ]
    
    platforms = ["makemytrip", "easemytrip", "cleartrip"]
    fare_classes = ["Y", "B", "M", "K", "Q", "L"]

    dataset_rows = []
    observed_inserts = []
    history_inserts = []

    # Generate observations spanning the last 180 days
    today = datetime.now()
    start_date = today - timedelta(days=180)

    print(f"[INFO] Generating 180 days of price points...")
    
    for day_idx in range(180):
        obs_date = start_date + timedelta(days=day_idx)
        obs_date_str = obs_date.strftime("%Y-%m-%d %H:%M:%S")
        obs_month = obs_date.month

        # We generate a few searches per route each day
        for route_info in routes:
            route = route_info["route"]
            base = route_info["base_price"]
            s_mult = route_info["season_mult"][obs_month]

            # Generate departures 1 to 30 days in the future
            for days_to_dep in [3, 7, 14, 21, 30]:
                dep_date = obs_date + timedelta(days=days_to_dep)
                dep_date_str = dep_date.strftime("%Y-%m-%d")

                # Choose random airline
                air = random.choice(airlines)
                airline_code = air["code"]
                flight_num = f"{airline_code}-{random.choice(air['flights'])}"
                
                # Apply yield pricing formula
                # Prices rise as days to departure falls
                dep_mult = 1.0 + (30 - days_to_dep) / 45.0
                
                # Weekend surcharge
                weekend_mult = 1.1 if dep_date.weekday() in [4, 5, 6] else 1.0
                
                # Random noise
                noise = random.uniform(-150.0, 150.0)

                # Final price
                price = (base * s_mult * dep_mult * weekend_mult) + noise
                price = round(max(1500.0, price), 2)

                seats_remaining = random.randint(1, 25)
                f_class = random.choice(fare_classes)
                plat = random.choice(platforms)

                # Add to memory arrays
                dataset_rows.append({
                    "route": route,
                    "departure_date": dep_date_str,
                    "airline": airline_code,
                    "flight_number": flight_num,
                    "price": price,
                    "platform": plat,
                    "recorded_at": obs_date_str,
                    "days_to_departure": days_to_dep,
                    "seats_remaining": seats_remaining
                })

                observed_inserts.append((
                    route, airline_code, obs_date_str, price, f_class, seats_remaining, "synthetic"
                ))

                history_inserts.append((
                    route, dep_date_str, airline_code, flight_num, price, plat, obs_date_str, "synthetic"
                ))

    # Write CSV file
    print(f"[INFO] Writing dataset to CSV: {CSV_PATH}")
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["route", "departure_date", "airline", "flight_number", "price", "platform", "recorded_at", "days_to_departure", "seats_remaining"])
        writer.writeheader()
        writer.writerows(dataset_rows)
    print(f"[SUCCESS] Generated {len(dataset_rows)} historical rows in CSV.")

    # Insert into database
    print(f"[INFO] Inserting rows into database tables...")
    cursor.executemany("""
        INSERT INTO observed_prices (route_key, airline, observed_at_timestamp, price, fare_class, seats_remaining_hint, source)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, observed_inserts)
    
    cursor.executemany("""
        INSERT INTO price_history (route, departure_date, airline, flight_number, price, platform, recorded_at, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, history_inserts)

    conn.commit()
    conn.close()
    
    print(f"[SUCCESS] Database seeding complete! Seeded {len(observed_inserts)} rows into observed_prices.")


if __name__ == "__main__":
    generate_and_seed_history()
