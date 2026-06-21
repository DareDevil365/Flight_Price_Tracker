import asyncio
import sys
import os
import json
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

# Add parent directories to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

from stealth.browser_factory import BrowserFactory
from api_key_manager import api_key_manager

async def run_llm_extraction(platform: str, text_data: str):
    prompt = f"""
    You are an expert coupon crawler. Analyze the following web page text content from the official offers page of '{platform}'.
    Extract a list of valid active coupons and promotions.

    For each offer, extract:
    1. code: The promo code (e.g. EMTFIRST, CTICICI, etc.). If it's a general banking offer without a specific code, generate a descriptive code or set to "BANK_OFFER".
    2. description: Brief user-friendly description.
    3. bank_restriction: Restricted bank (e.g. HDFC, SBI, ICICI, AXIS, etc. or null if universal).
    4. card_type: "CREDIT", "DEBIT", or "ANY".
    5. discount_type: "FLAT", "PERCENT", or "CASHBACK".
    6. discount_value: The numerical value (e.g. 10.0 for 10% or 1000.0 for Rs. 1000).
    7. max_discount: Maximum discount cap (numeric value or null).
    8. min_booking_value: Minimum transaction amount required (numeric value or null).

    Offers Page Content:
    {text_data[:10000]}

    Format your output strictly as a JSON array of objects with the keys:
    [
      {{"code": "...", "description": "...", "bank_restriction": "...", "card_type": "...", "discount_type": "...", "discount_value": ..., "max_discount": ..., "min_booking_value": ...}}
    ]
    Do not wrap in markdown code blocks. Output only the JSON.
    """
    
    client, model, key = api_key_manager.get_client("brute")
    print(f"Using model: {model}")
    
    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are a professional browser automation helper. Output strictly valid JSON arrays."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.0
    )
    
    content = response.choices[0].message.content.strip()
    return content

async def main():
    api_key_manager.register_broadcast_callback(lambda t, p: None)
    
    platform = "easemytrip"
    url = "https://www.easemytrip.com/offers.html"
    print(f"Launching stealth browser context to open '{url}'...")
    
    factory = BrowserFactory()
    browser, context, page = await factory.create_cloak_browser(
        cloak_config={"showBrowser": False}
    )
    
    try:
        print(f"Navigating to {url}...")
        await page.goto(url, timeout=40000, wait_until="domcontentloaded")
        await asyncio.sleep(4.0) # wait for page to render
        
        print("Extracting page text...")
        text_content = await page.evaluate("() => document.body.innerText")
        lines = [l.strip() for l in text_content.split("\n") if l.strip()]
        cleaned_text = "\n".join(lines)
        print(f"Extracted {len(cleaned_text)} characters.")
        
        # Save a sample of the text for inspection
        Path("scratch/scraped_offers_sample.txt").write_text(cleaned_text[:5000], encoding="utf-8")
        
        if len(cleaned_text) > 100:
            print("Running LLM Extraction...")
            extracted_json = await run_llm_extraction(platform, cleaned_text)
            print("\nExtracted Coupons JSON:")
            print(extracted_json)
        else:
            print("Extracted text is too short. Scrape failed.")
            
    except Exception as e:
        print(f"Scraping error: {e}")
    finally:
        print("Cleaning up browser...")
        await page.close()
        await context.close()
        await browser.close()
        await factory.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
