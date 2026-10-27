"""Active search-path regressions on intercepted local pages, never live fares."""
import asyncio
from unittest.mock import AsyncMock

import pytest

from provider_status import ProviderError
from quotes import search_url
from workers.makemytrip_worker import MakeMyTripWorker
from tests.test_verified_pricing import page
from tests.test_provider_homepage import LOGIN, TRIP


async def install_search(page, html):
    await page.route(search_url('makemytrip', TRIP),
        lambda route: route.fulfill(status=200,body=html,content_type='text/html'))


@pytest.mark.asyncio
async def test_normal_direct_search_closes_login_without_dormant_homepage_method(page):
    await install_search(page, LOGIN+'<div class="listingCard">Local listing marker</div>')
    worker=MakeMyTripWorker()
    await worker.input_search_criteria(page,TRIP)
    await worker.execute_search(page)
    assert page.url==search_url('makemytrip',TRIP)
    assert await page.get_by_role('dialog').count()==0


@pytest.mark.asyncio
async def test_late_login_is_dismissed_during_active_listing_wait(page):
    late=LOGIN.replace('this.parentElement.remove()',
        "this.parentElement.remove(); document.body.insertAdjacentHTML('beforeend', '<div class=listingCard>Local listing marker</div>')")
    await install_search(page,'<div id="late" hidden>'+late+'</div>')
    await page.goto(search_url('makemytrip',TRIP))
    await page.evaluate("setTimeout(()=>document.querySelector('#late').hidden=false,300)")
    await MakeMyTripWorker().execute_search(page)
    assert await page.get_by_role('dialog').count()==0
    assert await page.locator('.listingCard').is_visible()


@pytest.mark.asyncio
async def test_network_error_after_closing_login_is_not_success(page):
    await install_search(page,LOGIN+'<div>Network problem</div>')
    worker=MakeMyTripWorker()
    await worker.input_search_criteria(page,TRIP)
    with pytest.raises(ProviderError) as error:
        await worker.execute_search(page)
    assert error.value.code=='PROVIDER_NETWORK'


@pytest.mark.asyncio
async def test_unknown_login_close_fails_on_active_path_instead_of_stalling(page):
    await install_search(page,LOGIN.replace('commonModal__close','unknown-X'))
    with pytest.raises(ProviderError) as error:
        await MakeMyTripWorker().input_search_criteria(page,TRIP)
    assert error.value.code=='LOGIN_BLOCKED'


@pytest.mark.asyncio
async def test_empty_search_is_bounded_and_explicit(page,monkeypatch):
    await install_search(page,'<body></body>')
    await page.goto(search_url('makemytrip',TRIP))
    monkeypatch.setattr('workers.makemytrip_worker.LISTINGS_WAIT_SECONDS',.15)
    with pytest.raises(ProviderError) as error:
        await MakeMyTripWorker().execute_search(page)
    assert error.value.code=='SEARCH_TIMEOUT'


@pytest.mark.asyncio
async def test_cancellation_interrupts_listing_wait(page):
    await install_search(page,'<body></body>')
    await page.goto(search_url('makemytrip',TRIP))
    waiting=asyncio.create_task(MakeMyTripWorker().execute_search(page))
    await asyncio.sleep(.1)
    waiting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiting


@pytest.mark.asyncio
async def test_overlay_is_rechecked_before_reading_result_cards(page):
    await install_search(page,LOGIN)
    await page.goto(search_url('makemytrip',TRIP))
    worker=MakeMyTripWorker()
    async def check_dialog_removed(actual_page):
        assert await actual_page.get_by_role('dialog').count()==0
        return []
    worker._parse_via_dom=AsyncMock(side_effect=check_dialog_removed)
    assert await worker.parse_search_results(page)==[]
    worker._parse_via_dom.assert_awaited_once()
