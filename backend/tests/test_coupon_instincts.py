import pytest
import sys
import os
import aiosqlite
from pathlib import Path

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coupon_instincts import CouponInstinctsEngine

class MockDB:
    def __init__(self, conn):
        self.db = conn

def test_deal_sanity_heuristics():
    engine = CouponInstinctsEngine(db=None)
    
    # 1. Test domestic sanity checks
    # Sane: Rs 300 off on 5500 ticket -> final 5200
    is_sane, reason = engine.evaluate_deal_sanity(base_price=5500.0, discount=300.0, final_price=5200.0, is_domestic=True)
    assert is_sane is True, f"Failed sane domestic check: {reason}"
    
    # Insane: Rs 5000 off on 5500 ticket -> final 500 (too low final price & too high discount)
    is_sane, reason = engine.evaluate_deal_sanity(base_price=5500.0, discount=5000.0, final_price=500.0, is_domestic=True)
    assert is_sane is False
    assert "high discount" in reason or "floor limit" in reason or "exceeds max" in reason
    
    # Insane: Rs 3000 off on 5500 ticket -> final 2500 (discount exceeds 35% cap of 1925)
    is_sane, reason = engine.evaluate_deal_sanity(base_price=5500.0, discount=3000.0, final_price=2500.0, is_domestic=True)
    assert is_sane is False
    assert "exceeds max" in reason
    
    # 2. Test international sanity checks
    # Sane: Rs 3000 off on 20000 ticket -> final 17000
    is_sane, reason = engine.evaluate_deal_sanity(base_price=20000.0, discount=3000.0, final_price=17000.0, is_domestic=False)
    assert is_sane is True, f"Failed sane international check: {reason}"
    
    # Insane: Rs 17000 off on 20000 ticket -> final 3000 (too low final price & too high discount)
    is_sane, reason = engine.evaluate_deal_sanity(base_price=20000.0, discount=17000.0, final_price=3000.0, is_domestic=False)
    assert is_sane is False
    assert "floor limit" in reason or "high discount" in reason

@pytest.mark.asyncio
async def test_db_logging_and_correction_mock():
    # Setup in-memory sqlite db
    async with aiosqlite.connect(":memory:") as conn:
        conn.row_factory = aiosqlite.Row
        mock_db = MockDB(conn)
        
        # Create coupons table and seed a suspicious coupon
        await conn.execute("""
            CREATE TABLE coupons (
                platform TEXT,
                code TEXT,
                description TEXT,
                discount_type TEXT,
                discount_value REAL,
                is_active BOOLEAN DEFAULT 1,
                updated_at TEXT,
                PRIMARY KEY (platform, code)
            )
        """)
        
        await conn.execute("""
            INSERT INTO coupons (platform, code, description, discount_type, discount_value, is_active)
            VALUES ('easemytrip', 'FAKEVIDESH', 'Get flat Rs. 5000 off on flights', 'FLAT', 5000.0, 1)
        """)
        await conn.commit()
        
        engine = CouponInstinctsEngine(db=mock_db)
        await engine.initialize() # Create audits table
        
        # Mock the AI analyzer call to simulate it correcting the coupon to Rs. 500
        async def mock_ai_call(code, desc, base_price, is_domestic):
            return {
                "is_applicable": True,
                "applicable_discount_value": 500.0,
                "discount_type": "FLAT",
                "reason": "Adjusted to Rs. 500 as per domestic flight restrictions"
            }
        engine.analyze_coupon_with_ai = mock_ai_call
        
        # Audit a suspect deal: Base 5500, calculated discount 5000, domestic
        corrected_discount = await engine.audit_and_correct(
            platform="easemytrip",
            coupon_code="FAKEVIDESH",
            base_price=5500.0,
            calculated_discount=5000.0,
            is_domestic=True,
            search_id="test-search-id"
        )
        
        # Verify corrected discount value returned
        assert corrected_discount == 500.0
        
        # Verify the database has been updated with the corrected value! (Self-Improving loop)
        async with conn.execute("SELECT discount_value, discount_type FROM coupons WHERE platform = 'easemytrip' AND code = 'FAKEVIDESH'") as cursor:
            row = await cursor.fetchone()
            assert row is not None
            assert row[0] == 500.0 # Corrected!
            
        # Verify the audit log was written
        async with conn.execute("SELECT * FROM coupon_audits WHERE coupon_code = 'FAKEVIDESH'") as cursor:
            row = await cursor.fetchone()
            assert row is not None
            assert row["calculated_discount"] == 5000.0
            assert row["corrected_discount"] == 500.0
            assert row["was_corrected"] == 1
