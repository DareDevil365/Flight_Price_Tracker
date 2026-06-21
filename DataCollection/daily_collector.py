"""
Flight Finder — Daily Data Collector
Run this once per day (or per search) to append new price observations
to the training dataset. Over time, this builds real historical data.

Usage:  python daily_collector.py --route DEL-GOI --date 2025-08-15 --price 5200
"""
import argparse
import pandas as pd
from pathlib import Path
from datetime import datetime
import json

DATA_DIR = Path(__file__).parent
TRAINING_PATH = DATA_DIR / "training_dataset.csv"
OBSERVATIONS_PATH = DATA_DIR / "observed_prices_log.csv"

def append_observation(route, travel_date, price, platform="manual", 
                        airline="Unknown", days_to_departure=None, 
                        bank_offer_used=None, coupon_code=None):
    """Log a real price observation."""
    
    travel_dt = datetime.strptime(travel_date, "%Y-%m-%d")
    booking_dt = datetime.now()
    
    if days_to_departure is None:
        days_to_departure = (travel_dt - booking_dt).days
    
    row = {
        "route": route,
        "travel_date": travel_date,
        "observed_date": booking_dt.strftime("%Y-%m-%d"),
        "days_to_departure": days_to_departure,
        "price_inr": price,
        "platform": platform,
        "airline": airline,
        "bank_offer_used": bank_offer_used,
        "coupon_code": coupon_code,
    }
    
    df = pd.DataFrame([row])
    
    if OBSERVATIONS_PATH.exists():
        df.to_csv(OBSERVATIONS_PATH, mode='a', header=False, index=False)
    else:
        df.to_csv(OBSERVATIONS_PATH, index=False)
    
    print(f"Logged observation: {route} {travel_date} = ₹{price} (platform: {platform})")
    print(f"Total observations: {len(pd.read_csv(OBSERVATIONS_PATH))}")

def show_stats():
    """Show current observation stats."""
    if not OBSERVATIONS_PATH.exists():
        print("No observations yet. Start collecting!")
        return
    
    df = pd.read_csv(OBSERVATIONS_PATH)
    print(f"\nTotal observations: {len(df)}")
    print(f"Routes covered: {df['route'].nunique()}")
    print(f"Date range: {df['travel_date'].min()} to {df['travel_date'].max()}")
    print(f"\nTop routes:")
    print(df['route'].value_counts().head(10))
    print(f"\nPrice stats by route:")
    print(df.groupby('route')['price_inr'].agg(['count', 'mean', 'min', 'max']).round(2))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Daily flight price collector")
    parser.add_argument("--route", required=True, help="e.g., DEL-GOI")
    parser.add_argument("--date", required=True, help="Travel date YYYY-MM-DD")
    parser.add_argument("--price", required=True, type=float, help="Observed price in INR")
    parser.add_argument("--platform", default="manual", help="makemytrip, easemytrip, etc.")
    parser.add_argument("--airline", default="Unknown", help="Airline name")
    parser.add_argument("--days-left", type=int, help="Days to departure (auto-calculated if omitted)")
    parser.add_argument("--bank-offer", help="Bank offer used, if any")
    parser.add_argument("--coupon", help="Coupon code used, if any")
    parser.add_argument("--stats", action="store_true", help="Show stats only")
    
    args = parser.parse_args()
    
    if args.stats:
        show_stats()
    else:
        append_observation(
            route=args.route,
            travel_date=args.date,
            price=args.price,
            platform=args.platform,
            airline=args.airline,
            days_to_departure=args.days_left,
            bank_offer_used=args.bank_offer,
            coupon_code=args.coupon
        )
