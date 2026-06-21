"""
Flight Finder — Macro Data Fetcher
Downloads real historical macro data using yfinance (free).
Run this in your venv:  python fetch_macro_data.py

Requires: pip install yfinance pandas
"""
import os
from datetime import datetime, timedelta
from pathlib import Path

try:
    import yfinance as yf
    import pandas as pd
except ImportError:
    print("ERROR: yfinance not installed. Run: pip install yfinance pandas")
    raise

DATA_DIR = Path(__file__).parent
START_DATE = (datetime.now() - timedelta(days=3*365)).strftime('%Y-%m-%d')
END_DATE = datetime.now().strftime('%Y-%m-%d')

def fetch_and_save(ticker, name, out_name):
    print(f"Fetching {name} ({ticker})...")
    df = yf.download(ticker, start=START_DATE, end=END_DATE, progress=False)
    if df.empty:
        print(f"  WARNING: No data returned for {ticker}")
        return None
    # Flatten MultiIndex columns if present
    df.columns = [' '.join(col).strip() if isinstance(col, tuple) else col for col in df.columns]
    # Keep only Close/Adj Close
    keep_cols = [c for c in df.columns if 'Close' in c]
    if keep_cols:
        df = df[keep_cols].copy()
    out_path = DATA_DIR / f"{out_name}.csv"
    df.to_csv(out_path)
    print(f"  Saved {len(df)} rows to {out_path}")
    return df

if __name__ == "__main__":
    fetch_and_save("BZ=F", "Brent Crude", "brent_crude_yf")
    fetch_and_save("USDINR=X", "USD/INR", "usd_inr_yf")
    fetch_and_save("^NSEI", "Nifty 50", "nifty50_yf")
    print("\n[OK] All macro data fetched. Files saved to DataCollection/")
