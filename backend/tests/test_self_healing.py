import pytest
import asyncio
from playwright.async_api import async_playwright
from workers.mock_worker import MockWorker

@pytest.mark.asyncio
async def test_mock_worker_self_healing_checkout():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        
        worker = MockWorker()
        
        # 1. Search phase
        await worker.navigate_to_search(page)
        trip = {
            "origin": "DEL",
            "destination": "GOI",
            "departure_date": "2026-07-15"
        }
        await worker.input_search_criteria(page, trip)
        await worker.execute_search(page)
        
        # 2. Select flight
        results = await worker.parse_search_results(page)
        assert len(results) > 0
        await worker.select_flight(page, results[0])
        
        # 3. Fill passenger details (this will use self-healing filling and clicking)
        await worker.fill_passenger_details(page)
        await asyncio.sleep(0.5)
        
        # 4. Skip addons (this will use self-healing clicking)
        await worker.skip_addons(page)
        await asyncio.sleep(0.5)
        
        # 5. Proceed to checkout
        await worker.proceed_to_checkout(page)
        await asyncio.sleep(0.5)
        
        # 6. Verify we reached the checkout page
        is_checkout = await worker.is_at_checkout(page)
        assert is_checkout is True
        
        await browser.close()
