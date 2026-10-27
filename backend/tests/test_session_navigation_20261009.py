"""Session lifecycle checks use local pages and ephemeral browser contexts."""
import asyncio
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from session_manager import SessionManager
from tests.test_verified_pricing import page
from workers.cleartrip_worker import CleartripWorker
from workers.easemytrip_worker import EaseMyTripWorker
from financial_filter import FinancialFilter


async def wait_until(predicate):
    for _ in range(30):
        if predicate():return
        await asyncio.sleep(.01)
    raise AssertionError('Session event did not settle')


@pytest.mark.asyncio
async def test_closing_google_origin_tab_preserves_merchant_popup_session(page):
    manager=SessionManager(lambda *args:None)
    try:
        context=await page.context.browser.new_context()
        page=await context.new_page()
        await manager.register_session('session','search','google_flights',context.browser,context,page,1)
        merchant=await context.new_page()
        await merchant.set_content('<div>Local merchant booking review</div>')
        await page.close()
        await wait_until(lambda:manager._sessions['session']['page'] is merchant)
        assert not merchant.is_closed()
        assert manager.get_session_status('session')=='active'
        await merchant.close()
        await wait_until(lambda:'session' not in manager._sessions)
    finally:await manager.cleanup_all()


@pytest.mark.asyncio
async def test_closing_unrelated_secondary_tab_does_not_close_original_session(page):
    manager=SessionManager(lambda *args:None)
    try:
        context=await page.context.browser.new_context()
        page=await context.new_page()
        await manager.register_session('session','search','cleartrip',context.browser,context,page,1)
        other=await context.new_page()
        await other.close()
        await asyncio.sleep(.05)
        assert manager._sessions['session']['page'] is page and not page.is_closed()
        await page.close()
        await wait_until(lambda:'session' not in manager._sessions)
    finally:await manager.cleanup_all()


@pytest.mark.asyncio
async def test_timezone_aware_deadline_is_compared_as_instant():
    manager=SessionManager(lambda *args:None)
    try:
        # 05:30 offsets must not grant extra hours or prematurely expire carts.
        india=timezone(timedelta(hours=5,minutes=30))
        manager._sessions['active']={'expires_at':(datetime.now(timezone.utc)+timedelta(minutes=5)).astimezone(india),'status':'HANDED_OFF',
            'context':SimpleNamespace(close=AsyncMock()),'browser':SimpleNamespace(close=AsyncMock())}
        manager._sessions['expired']={'expires_at':(datetime.now(timezone.utc)-timedelta(minutes=5)).astimezone(india),'status':'HANDED_OFF',
            'context':SimpleNamespace(close=AsyncMock()),'browser':SimpleNamespace(close=AsyncMock())}
        assert manager.get_session_status('active')=='HANDED_OFF'
        assert manager.get_session_status('expired')=='expired'
    finally:await manager.cleanup_all()


@pytest.mark.asyncio
@pytest.mark.parametrize('money',['₹1,000,00','₹5,350.505','₹1e5','₹1 000','₹5350 + taxes','₹5350 per adult','₹5350 / adult'])
async def test_checkout_total_rejects_partial_or_ambiguous_amount(page,money):
    await page.set_content('<div>Grand total '+money+'</div>')
    assert await CleartripWorker().read_checkout_total(page) is None


@pytest.mark.asyncio
@pytest.mark.parametrize('money,expected',[('₹1,00,000.50',100000.50),('INR 1,000.50',1000.50),('₹5350',5350)])
async def test_checkout_total_reads_complete_valid_indian_amount(page,money,expected):
    await page.set_content('<div>Total payable '+money+'</div><div>1 Adult</div>')
    assert (await CleartripWorker().read_checkout_total(page))['total']==expected


@pytest.mark.asyncio
async def test_emt_css_currency_total_rejects_malformed_grouping(page):
    await page.set_content('''<div class="pr">Grand Total<i class="CurrncyCD_Rs" style="display:inline-block;width:8px;height:8px"></i>
        <span id="spnGrndTotal">1,000,00</span></div>''')
    assert await EaseMyTripWorker().read_checkout_total(page) is None


@pytest.mark.asyncio
async def test_unknown_fee_is_not_reported_as_observed_zero_or_null(page):
    await page.set_content('<div>Grand total ₹5350</div><div>Convenience fee calculated after payment method selection</div>')
    result=await CleartripWorker().read_checkout_total(page)
    assert result['total']==5350 and result['fees']==[]


@pytest.mark.parametrize('terms',[
    'Get an instant discount of Rs.550 on your flight booking and Acko insurance combo',
    'Flight discount only with travel insurance',
    'Flight discount requires baggage',
])
def test_required_addon_is_conditional_until_actual_combo_is_confirmed(terms):
    offer={'code':'EMTSECURE','description':terms}
    assert FinancialFilter().assess(offer,{}).status=='unknown'
    assert FinancialFilter().assess(offer,{'eligibility_facts':{'required_addon_confirmed':False}}).status=='ineligible'
    assert FinancialFilter().assess(offer,{'eligibility_facts':{'required_addon_confirmed':True}}).status=='eligible'


def test_optional_insurance_mention_does_not_restrict_flight_coupon():
    offer={'code':'BOOKNOW','description':'Get Rs.220 OFF on flight booking. Insurance is optional.'}
    assert FinancialFilter().assess(offer,{}).status=='eligible'


@pytest.mark.asyncio
async def test_emt_native_input_does_not_bypass_coupon_format_validation(page):
    await page.set_content('<input id="txtCouponCode" value="ORIGINAL">')
    with pytest.raises(ValueError,match='Malformed coupon'):
        await EaseMyTripWorker().enter_coupon_code(page,'INVALID CODE')
    assert await page.locator('#txtCouponCode').input_value()=='ORIGINAL'
