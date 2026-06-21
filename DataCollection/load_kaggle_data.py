"""
Flight Finder — Kaggle Dataset Loader
Expected files (download from Kaggle):
  - Clean_Dataset.csv  (from Shubham Bathwal's Flight Price Prediction)
  - OR economy.csv + business.csv (raw files)

Download link:
  https://www.kaggle.com/datasets/shubhambathwal/flight-price-prediction

After downloading, place the CSV(s) in DataCollection/kaggle/
"""
import pandas as pd
from pathlib import Path

DATA_DIR = Path(__file__).parent
KAGGLE_DIR = DATA_DIR / "kaggle"

def load_clean_dataset():
    path = KAGGLE_DIR / "Clean_Dataset.csv"
    if not path.exists():
        print(f"ERROR: {path} not found.")
        print("Download from: https://www.kaggle.com/datasets/shubhambathwal/flight-price-prediction")
        return None
    df = pd.read_csv(path)
    print(f"Loaded Clean_Dataset.csv: {len(df)} rows, {len(df.columns)} columns")
    return df

def load_raw_economy():
    path = KAGGLE_DIR / "economy.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path)
    print(f"Loaded economy.csv: {len(df)} rows")
    return df

def load_raw_business():
    path = KAGGLE_DIR / "business.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path)
    print(f"Loaded business.csv: {len(df)} rows")
    return df

def normalize_kaggle_df(df):
    """Convert Kaggle columns to our schema."""
    rename_map = {
        'airline': 'airline',
        'flight': 'flight_number',
        'source_city': 'origin_city',
        'departure_time': 'departure_time',
        'stops': 'stops',
        'arrival_time': 'arrival_time',
        'destination_city': 'destination_city',
        'class': 'cabin_class',
        'duration': 'duration_hours',
        'days_left': 'days_to_departure',
        'price': 'price_inr',
    }
    df = df.rename(columns=rename_map)
    # Normalize stops
    df['stops'] = df['stops'].map({'zero': 0, 'one': 1, 'two_or_more': 2})
    # Map cities to IATA codes
    city_to_iata = {
        'Delhi': 'DEL', 'Mumbai': 'BOM', 'Bangalore': 'BLR',
        'Hyderabad': 'HYD', 'Chennai': 'MAA', 'Kolkata': 'CCU',
        'Goa': 'GOI', 'Pune': 'PNQ', 'Jaipur': 'JAI',
    }
    df['origin'] = df['origin_city'].map(city_to_iata).fillna(df['origin_city'])
    df['destination'] = df['destination_city'].map(city_to_iata).fillna(df['destination_city'])
    df['route'] = df['origin'].astype(str) + '-' + df['destination'].astype(str)
    return df

if __name__ == "__main__":
    KAGGLE_DIR.mkdir(exist_ok=True)
    df = load_clean_dataset()
    if df is not None:
        df_norm = normalize_kaggle_df(df)
        print(df_norm.head())
        df_norm.to_csv(DATA_DIR / "kaggle_flight_prices_normalized.csv", index=False)
        print("Saved normalized data to kaggle_flight_prices_normalized.csv")
