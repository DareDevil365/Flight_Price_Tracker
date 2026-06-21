import asyncio
import sys
from pathlib import Path

# Add backend folder to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from coupon_harvester import CouponHarvester
from coupon_db import CouponDB

async def main():
    db = CouponDB()
    await db.initialize()
    harvester = CouponHarvester(db)
    
    print("Testing crawl for yatra...")
    coupons = await harvester._crawl_platform_deals("yatra")
    print(f"Yatra coupons found: {len(coupons)}")
    for c in coupons[:5]:
        print(f"  Code: {c['code']} | Disc: {c['discount_value']} | Description: {c['description'][:50]}")
        
    print("\nTesting crawl for paytm...")
    coupons_paytm = await harvester._crawl_platform_deals("paytm")
    print(f"Paytm coupons found: {len(coupons_paytm)}")
    for c in coupons_paytm[:5]:
        print(f"  Code: {c['code']} | Disc: {c['discount_value']} | Description: {c['description'][:50]}")
        
    await db.close()

if __name__ == "__main__":
    asyncio.run(main())
