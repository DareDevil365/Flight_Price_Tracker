"""
Flight Finder — Graph RAG & Predictor Verification Test
Validates SQLite graph population, 2-hop entity retrieval, score weighting,
and the final advisory explanation inside the PricePredictor.
"""

import asyncio
import os
import sys
from pathlib import Path
from loguru import logger

# Add project root to sys path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

from coupon_db import CouponDB
from price_predictor import PricePredictor

async def main():
    logger.info("Initializing CouponDB...")
    db = CouponDB()
    await db.initialize()
    
    logger.info("Initializing PricePredictor...")
    predictor = PricePredictor(db)
    
    # Wait briefly for startup tasks to initialize tables
    await asyncio.sleep(2)
    
    # 1. Test direct Graph RAG retrieval for DEL-GOI in July (monsoon season, card offers)
    logger.info("--- Test 1: Direct Graph RAG Retrieval ---")
    route = "DEL-GOI"
    travel_date = "2026-07-15" # July (Month 7)
    
    # Test high Brent crude price scenario ($88.5/bbl)
    subgraph = await predictor.graph_rag.retrieve_subgraph(route, travel_date, brent_usd=88.5)
    logger.info(f"Retrieved Facts for {route} on {travel_date} (Brent: $88.5):")
    for fact in subgraph["facts"]:
        logger.info(f"  * {fact}")
    logger.info(f"Net Graph Score: {subgraph['net_score']}")
    logger.info(f"Retrieved Factors: {subgraph['factors']}")

    # 2. Test generation of explanation advisory
    logger.info("--- Test 2: Advisory Explanation Generation ---")
    explanation = await predictor.graph_rag.generate_explanation(subgraph["facts"], subgraph["net_score"], route, travel_date)
    logger.info(f"Generated Explanation:\n{explanation}")

    # 3. Test integrated PricePredictor.predict run
    logger.info("--- Test 3: Integrated PricePredictor.predict ---")
    
    # Inject a mock price in history so the predictor has a current price reference
    await db.log_price(
        route=route,
        departure_date=travel_date,
        airline="IndiGo",
        flight_number="6E-2034",
        price=5400.0,
        platform="EaseMyTrip"
    )
    
    result = await predictor.predict(route, travel_date)
    
    logger.info("Predict Result payload keys:")
    logger.info(list(result.keys()))
    
    logger.info(f"Final Signal: {result['decision']['signal']}")
    logger.info(f"Urgency: {result['decision']['urgency']}")
    logger.info(f"Confidence: {result['decision']['confidence']}")
    logger.info(f"Expected Price on Book Date: {result['decision']['expected_price_on_book_date']}")
    logger.info(f"Potential Savings if Wait: {result['decision']['potential_saving_if_wait']}")
    logger.info(f"RAG Advisory:\n{result['decision']['rag_advisory']}")
    
    # Verify outputs are clean and structured
    assert "VERDICT:" in result["decision"]["rag_advisory"]
    assert "REASON:" in result["decision"]["rag_advisory"]
    assert "RISK_IF_OPPOSITE:" in result["decision"]["rag_advisory"]
    assert result["decision"]["signal"] in ["BOOK_NOW", "WAIT", "MONITOR"]
    
    logger.info("✅ Graph RAG Verification passed successfully!")
    await db.close()

if __name__ == "__main__":
    asyncio.run(main())
