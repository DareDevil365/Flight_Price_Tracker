"""
Flight Finder — Database Seeding Script
Seeds the database with initial coupons and external savings offers.
"""

import asyncio
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta

DB_PATH = Path(__file__).parent.parent / "db" / "flight_agent.db"


def seed_database():
    print("[INFO] Seeding database with real platform coupons...")
    db_dir = DB_PATH.parent
    db_dir.mkdir(parents=True, exist_ok=True)

    # We use sqlite3 (sync) here for simplicity of the standalone run script
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    # Create tables if not exists by reading schema
    schema_path = Path(__file__).parent / "schema.sql"
    if schema_path.exists():
        schema_sql = schema_path.read_text(encoding="utf-8")
        cursor.executescript(schema_sql)
        print("[SUCCESS] Tables created successfully.")

    today = datetime.now()
    expiry_date = (today + timedelta(days=90)).strftime("%Y-%m-%d")
    start_date = today.strftime("%Y-%m-%d")

    # Seed Coupons (Real Platforms Only)
    coupons = [
        # MakeMyTrip
        ("makemytrip", "MMTDEAL", "Flat Rs. 500 off on all domestic flights", None, "ANY", 0, 0, 0, 0, "FLAT", 500, None, 3000, start_date, expiry_date, 1, "manual", None, "platform_native", 0.9, 0.95),
        ("makemytrip", "MMTDEALICICI", "Up to Rs. 1,500 off on ICICI Credit Cards", "ICICI", "CREDIT", 0, 0, 0, 0, "FLAT", 1200, None, 5000, start_date, expiry_date, 1, "manual", None, "platform_native", 0.95, 0.90),
        ("makemytrip", "MMTDEALHDFC", "Up to Rs. 2,000 off on HDFC Credit Cards", "HDFC", "CREDIT", 0, 0, 0, 0, "FLAT", 1500, None, 6000, start_date, expiry_date, 1, "manual", None, "platform_native", 0.95, 0.92),
        ("makemytrip", "FLYHIGH", "Flat 10% off up to Rs. 1000 - App Only", None, "ANY", 0, 0, 0, 1, "PERCENT", 10, 1000, 3000, start_date, expiry_date, 1, "manual", None, "platform_native", 0.8, 0.85),
        ("makemytrip", "MMTEMINOW", "EMI offer: Rs. 1,000 off on Axis Bank EMI transactions", "AXIS", "CREDIT", 1, 0, 0, 0, "FLAT", 1000, None, 5000, start_date, expiry_date, 1, "manual", None, "platform_native", 0.85, 0.70),

        # EaseMyTrip
        ("easemytrip", "EASEFLY", "Rs. 300 off on domestic flight bookings", None, "ANY", 0, 0, 0, 0, "FLAT", 300, None, 2500, start_date, expiry_date, 1, "manual", None, "platform_native", 0.9, 0.92),
        ("easemytrip", "EMTFLY", "Flat Rs. 400 off for new users", None, "ANY", 0, 0, 0, 0, "FLAT", 400, None, 3000, start_date, expiry_date, 1, "manual", None, "platform_native", 0.9, 0.90),
        ("easemytrip", "EMTHDFC", "Up to Rs. 1,200 off on HDFC Bank Credit/Debit Cards", "HDFC", "ANY", 0, 0, 0, 0, "FLAT", 1200, None, 4000, start_date, expiry_date, 1, "manual", None, "platform_native", 0.95, 0.89),
        ("easemytrip", "EMTICICI", "Flat Rs. 1,000 off on ICICI Cards", "ICICI", "ANY", 0, 0, 0, 0, "FLAT", 1000, None, 4500, start_date, expiry_date, 1, "manual", None, "platform_native", 0.95, 0.87),
        ("easemytrip", "EMTSBI", "Flat Rs. 800 off on SBI Cards", "SBI", "ANY", 0, 0, 0, 0, "FLAT", 800, None, 4000, start_date, expiry_date, 1, "manual", None, "platform_native", 0.9, 0.86),

        # Cleartrip
        ("cleartrip", "CTDEAL", "Flat Rs. 400 off on domestic bookings", None, "ANY", 0, 0, 0, 0, "FLAT", 400, None, 3000, start_date, expiry_date, 1, "manual", None, "platform_native", 0.9, 0.94),
        ("cleartrip", "CTFLY", "Flat 10% off up to Rs. 1,500 on flights", None, "ANY", 0, 0, 0, 0, "PERCENT", 10, 1500, 3000, start_date, expiry_date, 1, "manual", None, "platform_native", 0.85, 0.88),
        ("cleartrip", "CTHDFC", "Up to Rs. 1,500 off on HDFC Credit Cards", "HDFC", "CREDIT", 0, 0, 0, 0, "FLAT", 1500, None, 5000, start_date, expiry_date, 1, "manual", None, "platform_native", 0.95, 0.91),
        ("cleartrip", "CTICICI", "Flat Rs. 1,200 off on ICICI Credit/Debit Cards", "ICICI", "ANY", 0, 0, 0, 0, "FLAT", 1200, None, 5000, start_date, expiry_date, 1, "manual", None, "platform_native", 0.95, 0.89),

        # Yatra
        ("yatra", "YTFESTIVAL", "Flat Rs. 400 off on all domestic flights", None, "ANY", 0, 0, 0, 0, "FLAT", 400, None, 3000, start_date, expiry_date, 1, "manual", None, "platform_native", 0.9, 0.93),
        ("yatra", "YTHDFC", "Flat Rs. 1,000 off on HDFC Credit Cards", "HDFC", "CREDIT", 0, 0, 0, 0, "FLAT", 1000, None, 4000, start_date, expiry_date, 1, "manual", None, "platform_native", 0.95, 0.91),
        ("yatra", "YTICICI", "Flat Rs. 1,200 off on ICICI Credit Cards", "ICICI", "CREDIT", 0, 0, 0, 0, "FLAT", 1200, None, 5000, start_date, expiry_date, 1, "manual", None, "platform_native", 0.95, 0.89),
        ("yatra", "YTINTL", "Up to Rs. 5,000 off on International Flights", None, "ANY", 0, 0, 0, 0, "FLAT", 3000, None, 15000, start_date, expiry_date, 1, "manual", None, "platform_native", 0.85, 0.80),

        # Paytm
        ("paytm", "FLYPAYTM", "Flat Rs. 300 off on domestic flight bookings", None, "ANY", 0, 0, 0, 0, "FLAT", 300, None, 2500, start_date, expiry_date, 1, "manual", None, "platform_native", 0.9, 0.92),
        ("paytm", "PTMHDFC", "Up to Rs. 1,500 off on HDFC Cards", "HDFC", "ANY", 0, 0, 0, 0, "FLAT", 1200, None, 4000, start_date, expiry_date, 1, "manual", None, "platform_native", 0.95, 0.88),
        ("paytm", "PTMICICI", "Up to Rs. 1,200 off on ICICI Credit Cards", "ICICI", "CREDIT", 0, 0, 0, 0, "FLAT", 1000, None, 4000, start_date, expiry_date, 1, "manual", None, "platform_native", 0.95, 0.87),
        ("paytm", "PTMINTL", "Flat 10% off up to Rs. 5,000 on International Flights", None, "ANY", 0, 0, 0, 0, "PERCENT", 10, 5000, 10000, start_date, expiry_date, 1, "manual", None, "platform_native", 0.85, 0.82),

        # Ixigo
        ("ixigo", "IXIGO400", "Flat Rs. 400 off on domestic bookings", None, "ANY", 0, 0, 0, 0, "FLAT", 400, None, 3000, start_date, expiry_date, 1, "manual", None, "platform_native", 0.9, 0.94),
        ("ixigo", "IXIHDFC", "Up to Rs. 1,500 off on HDFC Cards", "HDFC", "ANY", 0, 0, 0, 0, "FLAT", 1200, None, 5000, start_date, expiry_date, 1, "manual", None, "platform_native", 0.95, 0.90),
        ("ixigo", "IXICICI", "Flat Rs. 1,000 off on ICICI Cards", "ICICI", "ANY", 0, 0, 0, 0, "FLAT", 1000, None, 4000, start_date, expiry_date, 1, "manual", None, "platform_native", 0.95, 0.88),
        ("ixigo", "IXIINTL", "Rebate of Rs. 4,000 on International Flight Booking", None, "ANY", 0, 0, 0, 0, "FLAT", 4000, None, 12000, start_date, expiry_date, 1, "manual", None, "platform_native", 0.85, 0.83),
    ]

    cursor.executemany(
        """
        INSERT OR REPLACE INTO coupons (
            platform, code, description, bank_restriction, card_type,
            requires_emi, requires_bnpl, requires_wallet, app_only,
            discount_type, discount_value, max_discount, min_booking_value,
            valid_from, valid_until, is_active, source, source_url,
            source_type, trust_score, success_rate
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        coupons,
    )
    print(f"[SUCCESS] Seeded {len(coupons)} coupons into 'coupons' table.")

    # Seed External Savings (Real Platforms Only)
    savings = [
        # Cashback Portals
        ("makemytrip", "cashback_portal", "CashKaro", 3.5, "PERCENT", 300.0, 2000.0, "Earn 3.5% cashback on domestic flights booked via CashKaro link.", "https://cashkaro.com/stores/makemytrip", start_date, expiry_date),
        ("easemytrip", "cashback_portal", "CashKaro", 2.0, "PERCENT", 150.0, 1500.0, "Earn 2.0% cashback on domestic flights booked via CashKaro link.", "https://cashkaro.com/stores/easemytrip", start_date, expiry_date),
        ("cleartrip", "cashback_portal", "CashKaro", 3.0, "PERCENT", 250.0, 2000.0, "Earn 3.0% cashback on domestic flights booked via CashKaro link.", "https://cashkaro.com/stores/cleartrip", start_date, expiry_date),
        ("yatra", "cashback_portal", "CashKaro", 2.5, "PERCENT", 200.0, 2000.0, "Earn 2.5% cashback on domestic flights booked via CashKaro link.", "https://cashkaro.com/stores/yatra", start_date, expiry_date),
        ("paytm", "cashback_portal", "CashKaro", 1.5, "PERCENT", 100.0, 1500.0, "Earn 1.5% cashback on domestic flights booked via CashKaro link.", "https://cashkaro.com/stores/paytm", start_date, expiry_date),
        ("ixigo", "cashback_portal", "CashKaro", 3.0, "PERCENT", 250.0, 2000.0, "Earn 3.0% cashback on domestic flights booked via CashKaro link.", "https://cashkaro.com/stores/ixigo", start_date, expiry_date),
        
        # Payment Wallets
        ("ALL", "wallet_offer", "Amazon Pay", 5.0, "PERCENT", 200.0, 3000.0, "Get 5% back up to Rs. 200 using Amazon Pay wallet.", "https://www.amazon.in/amazonpay/home", start_date, expiry_date),
        ("makemytrip", "wallet_offer", "Paytm Wallet", 2.5, "PERCENT", 150.0, 2500.0, "Get flat Rs. 150 cashback on Paytm Wallet payment.", "https://paytm.com", start_date, expiry_date),
        
        # UPI Offers
        ("makemytrip", "upi_offer", "PhonePe", 100.0, "FLAT", 100.0, 2000.0, "Rs. 100 instant cashback on booking flights via PhonePe UPI.", "https://phonepe.com", start_date, expiry_date),
        ("easemytrip", "upi_offer", "GPay", 150.0, "FLAT", 150.0, 3000.0, "Rs. 150 cashback scratch card on Google Pay UPI transactions.", "https://pay.google.com", start_date, expiry_date),
    ]

    cursor.executemany(
        """
        INSERT OR REPLACE INTO external_savings (
            platform, savings_type, provider, savings_value, savings_unit,
            max_savings, min_transaction, terms, source_url,
            valid_from, valid_until, is_active
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        """,
        savings,
    )
    print(f"[SUCCESS] Seeded {len(savings)} external savings rules.")

    conn.commit()
    conn.close()
    print("[SUCCESS] Database seeding complete.")


def seed_mock_coupons(conn=None):
    """Seed coupons and savings specific to the MockBooking.com platform (for testing)."""
    print("[INFO] Seeding database with mock coupons...")
    should_close = False
    if conn is None:
        conn = sqlite3.connect(str(DB_PATH))
        should_close = True
    
    cursor = conn.cursor()
    today = datetime.now()
    expiry_date = (today + timedelta(days=90)).strftime("%Y-%m-%d")
    start_date = today.strftime("%Y-%m-%d")
    
    mock_coupons = [
        ("mock", "MOCK100", "Simulated Coupon for Rs. 100 off", None, "ANY", 0, 0, 0, 0, "FLAT", 100, None, 1000, start_date, expiry_date, 1, "manual", None, "platform_native", 1.0, 1.0),
        ("mock", "MOCKSBI", "Simulated Coupon for Rs. 500 off on SBI Card", "SBI", "CREDIT", 0, 0, 0, 0, "FLAT", 500, None, 2000, start_date, expiry_date, 1, "manual", None, "platform_native", 1.0, 1.0),
        ("mock", "MOCKHDFC", "Simulated Coupon for Rs. 800 off on HDFC Card", "HDFC", "CREDIT", 0, 0, 0, 0, "FLAT", 800, None, 3000, start_date, expiry_date, 1, "manual", None, "platform_native", 1.0, 1.0),
        ("mock", "MOCKICICI", "Simulated Coupon for Rs. 600 off on ICICI Debit", "ICICI", "DEBIT", 0, 0, 0, 0, "FLAT", 600, None, 2500, start_date, expiry_date, 1, "manual", None, "platform_native", 1.0, 1.0),
        ("mock", "MOCKEMI", "Simulated EMI Coupon: Rs. 400 off (Requires EMI)", "SBI", "CREDIT", 1, 0, 0, 0, "FLAT", 400, None, 2500, start_date, expiry_date, 1, "manual", None, "platform_native", 1.0, 0.9),
    ]
    
    mock_savings = [
        ("mock", "cashback_portal", "CashKaro Mock", 5.0, "PERCENT", 250.0, 1000.0, "Mock 5% cashback on flight bookings.", "https://cashkaro.com", start_date, expiry_date),
        ("mock", "upi_offer", "PhonePe Mock", 200.0, "FLAT", 200.0, 1500.0, "Flat Rs. 200 cashback on PhonePe UPI.", "https://phonepe.com", start_date, expiry_date),
    ]
    
    cursor.executemany(
        """
        INSERT OR REPLACE INTO coupons (
            platform, code, description, bank_restriction, card_type,
            requires_emi, requires_bnpl, requires_wallet, app_only,
            discount_type, discount_value, max_discount, min_booking_value,
            valid_from, valid_until, is_active, source, source_url,
            source_type, trust_score, success_rate
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        mock_coupons,
    )
    
    cursor.executemany(
        """
        INSERT OR REPLACE INTO external_savings (
            platform, savings_type, provider, savings_value, savings_unit,
            max_savings, min_transaction, terms, source_url,
            valid_from, valid_until, is_active
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        """,
        mock_savings,
    )
    
    conn.commit()
    if should_close:
        conn.close()
    print("[SUCCESS] Mock coupons seeded.")


def cleanup_expired_coupons(conn=None):
    """Deletes expired coupons from the coupons database table."""
    print("[INFO] Cleaning up expired coupons...")
    should_close = False
    if conn is None:
        conn = sqlite3.connect(str(DB_PATH))
        should_close = True
        
    cursor = conn.cursor()
    today_str = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("DELETE FROM coupons WHERE valid_until < ?", (today_str,))
    deleted = cursor.rowcount
    conn.commit()
    
    if should_close:
        conn.close()
    print(f"[SUCCESS] Cleaned up {deleted} expired coupons.")


if __name__ == "__main__":
    seed_database()
    cleanup_expired_coupons()
