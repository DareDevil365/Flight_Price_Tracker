import asyncio
import os
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
    await page.goto(url, timeout=40000, wait_until="domcontentloaded")
    await asyncio.sleep(5.0)
    
    # Let's find all buttons, inputs, links on the page that could be the search button
    elements = await page.evaluate("""
        () => {
            const results = [];
            const tags = ['button', 'input', 'a', 'div', 'span'];
            for (const tag of tags) {
                const els = document.querySelectorAll(tag);
                for (const el of els) {
                    const text = (el.innerText || el.value || '').trim();
                    const id = el.id || '';
                    const className = el.className || '';
                    const onclick = el.getAttribute('onclick') || '';
                    
                    const isCandidate = 
                        text.toLowerCase().includes('search') || 
                        id.toLowerCase().includes('search') || 
                        className.toLowerCase().includes('search') || 
                        className.toLowerCase().includes('srch') || 
                        onclick.toLowerCase().includes('search');
                        
                    if (isCandidate) {
                        results.push({
                            tag: tag,
                            id: id,
                            className: className,
                            text: text.substring(0, 50),
                            onclick: onclick.substring(0, 100),
                            visible: el.offsetWidth > 0 && el.offsetHeight > 0
                        });
                    }
                }
            }
            return results;
        }
    """)
    
    print(f"\nFound {len(elements)} candidate elements:")
    for idx, el in enumerate(elements):
        if el['visible']:
            print(f"[{idx}] TAG: {el['tag']} | ID: {el['id']} | CLASS: {el['className']} | TEXT: '{el['text']}' | ONCLICK: '{el['onclick']}' | VISIBLE: {el['visible']}")
            
    await browser.close()
    await factory.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
