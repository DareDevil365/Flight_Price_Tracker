import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

# Add backend folder to sys.path so we can import workers
sys.path.append(str(Path(__file__).parent.parent))

from playwright.async_api import async_playwright
from workers.ai_worker import AIWorker

async def main():
    # Verify API key is set
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY or GEMINI_API_KEY is not set in environment or .env file.")
        return


    print("Starting AIWorker verification test...")
    worker = AIWorker(
        platform_id="easemytrip",
        platform_name="EaseMyTrip",
        base_url="https://www.easemytrip.com/"
    )

    from stealth.browser_factory import BrowserFactory
    factory = BrowserFactory()
    print("Launching stealth browser...")
    browser, context, page = await factory.create_cloak_browser(cloak_config={"showBrowser": True})

    print(f"1. Navigating to {worker.base_url}...")
    await worker.navigate_to_search(page)

    print("2. Entering search criteria (DEL -> BOM)...")
    trip = {
        "origin": "DEL",
        "destination": "BOM",
        "departure_date": "2026-07-15"
    }
    await worker.input_search_criteria(page, trip)

    print("3. Clicking search button...")
    await worker.execute_search(page)
    
    print("4. Parsing search results...")
    flights = await worker.parse_search_results(page)
    print("\nFlights found:")
    for idx, f in enumerate(flights):
        print(f"[{idx+1}] {f['airline']} {f['flight_number']} - Rs. {f['base_price']} (Selector: {f['selector']})")

    print("\nVerification completed successfully!")
    await asyncio.sleep(5)
    await browser.close()
    await factory.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
