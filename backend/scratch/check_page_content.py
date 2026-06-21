import asyncio
import sys
from pathlib import Path

# Add backend folder to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from stealth.browser_factory import BrowserFactory

async def main():
    factory = BrowserFactory()
    print("Launching stealth browser...")
    browser, context, page = await factory.create_cloak_browser(cloak_config={"showBrowser": False})
    
    url = "https://flight.easemytrip.com/FlightList/Index?srch=DEL|BOM|15/07/2026&px=1-0-0&ccls=O&tp=O&c=IN"
    print(f"Navigating to: {url}")
    try:
        await page.goto(url, timeout=30000, wait_until="domcontentloaded")
    except Exception as e:
        print(f"Goto timed out or failed: {e}")
        
    await asyncio.sleep(3.0)
    
    # Check if there is a search button and click it
    try:
        search_btn = await page.query_selector("#btnSrch")
        if search_btn:
            print("Clicking search button #btnSrch...")
            await search_btn.click()
            await asyncio.sleep(8.0)  # Wait for results to load
        else:
            print("Search button #btnSrch not found!")
    except Exception as e:
        print(f"Clicking search button failed: {e}")
        
    # Check current URL and page title
    print(f"Current URL: {page.url}")
    
    # Check visibility of flight cards or flight list
    has_flight_list = await page.query_selector(".flight-list, .row-grid, div[id*='ResultDiv']")
    print(f"Flight list selector found: {has_flight_list is not None}")
    
    # Count of flight cards found
    card_count = await page.evaluate("""
        () => {
            const cards = document.querySelectorAll('.flight-list, .row-grid, div[id*="ResultDiv"], [id*="row-"]');
            return cards.length;
        }
    """)
    print(f"Number of flight card elements: {card_count}")
    
    # Let's dump text of the flight card elements (ignoring non-ascii characters)
    card_texts = await page.evaluate("""
        () => {
            const cards = Array.from(document.querySelectorAll('.flight-list, .row-grid, div[id*="ResultDiv"], [id*="row-"]'));
            return cards.slice(0, 5).map(c => c.innerText.substring(0, 200));
        }
    """)
    print("\nFirst 5 flight card text snippets:")
    for idx, text in enumerate(card_texts):
        clean_text = text.encode('ascii', errors='ignore').decode('ascii')
        print(f"[{idx+1}] {repr(clean_text)}")
        
    await browser.close()
    await factory.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
