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
    
    # Click search button
    try:
        search_btn = await page.query_selector("#btnSrch")
        if search_btn:
            print("Clicking search button #btnSrch...")
            await search_btn.click()
            # Wait for 12 seconds to ensure page transition/loading finishes
            await asyncio.sleep(12.0)
        else:
            print("Search button #btnSrch not found!")
    except Exception as e:
        print(f"Clicking search button failed: {e}")
        
    print(f"Final URL: {page.url}")
    
    # Save text
    body_text = await page.evaluate("() => document.body.innerText")
    with open("emt_text.txt", "w", encoding="utf-8") as f:
        f.write(body_text)
    print("Saved body text to emt_text.txt")
    
    # Save HTML
    html_content = await page.content()
    with open("emt_page.html", "w", encoding="utf-8") as f:
        f.write(html_content)
    print("Saved HTML to emt_page.html")
    
    await browser.close()
    await factory.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
