import sqlite3
from pathlib import Path

DB_PATH = Path("db/flight_agent.db")

def clean_database():
    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH.absolute()}")
        return

    print(f"Connecting to database at {DB_PATH.absolute()}...")
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    try:
        # Delete bad price history records
        cursor.execute("DELETE FROM price_history WHERE price < 1500")
        history_deleted = cursor.rowcount
        print(f"Deleted {history_deleted} records from price_history with price < 1500")

        # Delete bad observed prices
        cursor.execute("DELETE FROM observed_prices WHERE price < 1500")
        observed_deleted = cursor.rowcount
        print(f"Deleted {observed_deleted} records from observed_prices with price < 1500")

        # Delete bad search results
        cursor.execute("DELETE FROM search_results WHERE base_price < 1500 OR final_price < 1500")
        results_deleted = cursor.rowcount
        print(f"Deleted {results_deleted} records from search_results with price < 1500")

        # Clear predictions and suggestions based on bad data
        cursor.execute("DELETE FROM price_predictions")
        predictions_deleted = cursor.rowcount
        print(f"Cleared {predictions_deleted} price predictions")

        cursor.execute("DELETE FROM smart_suggestions")
        suggestions_deleted = cursor.rowcount
        print(f"Cleared {suggestions_deleted} smart suggestions")

        conn.commit()
        print("Database cleanup completed successfully!")

    except Exception as e:
        conn.rollback()
        print(f"Error cleaning database: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    clean_database()
