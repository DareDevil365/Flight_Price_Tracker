import asyncio
from types import SimpleNamespace
import pytest
from coupon_audit import CouponAudit, history
from coupon_brute_forcer import CouponBruteForcer
from financial_filter import FinancialFilter
from tests.test_verified_pricing import database
from tests.test_navigation_audit import StatefulCart, fast_coupon_waits


@pytest.mark.asyncio
async def test_scoped_trials_preserved_without_global_reliability_learning(database,fast_coupon_waits):
    cart=StatefulCart()
    result=await CouponBruteForcer(cart,FinancialFilter(),lambda *a:None).brute_force(SimpleNamespace(url='https://www.cleartrip.com/booking'),
        [{'code':'BEST','description':'Domestic flight discount','source_url':'https://www.cleartrip.com/offers/save?session=secret'},
         {'code':'OLD','valid_until':'2000-01-01'}],{},'audit',db=database,
        audit_scope={'origin':'BOM','destination':'HYD','departure_date':'2026-12-12',
            'passenger_count':1,'stage':'review','selected_payment':{'method':'UPI','label':'private@example.com'},
            'passenger_name':'Private Person'})
    records=await history(database,'cleartrip')
    record=records[0]
    assert record['status']=='review_only'
    assert record['scope']['origin']=='BOM' and record['scope']['destination']=='HYD'
    assert 'private' not in str(record).lower() and 'session=secret' not in str(record)
    assert any(t['code']=='OLD' and t['status']=='pre_filtered' for t in record['trials'])
    assert any(t['code']=='BEST' and t['status']=='valid_match' for t in record['trials'])
    assert record['id']==result['audit_run_id']
    async with database.db.execute('SELECT count(*) FROM coupon_learnings') as c:
        assert (await c.fetchone())[0]==0


@pytest.mark.asyncio
async def test_cancelled_trial_keeps_explicit_untested_rows(database,fast_coupon_waits):
    cart=StatefulCart(pause_first_removal=True)
    runner=CouponBruteForcer(cart,FinancialFilter(),lambda *a:None)
    task=asyncio.create_task(runner.brute_force(SimpleNamespace(url='https://www.cleartrip.com/booking'),[{'code':'BEST'}],{},'audit',db=database))
    await cart.entered.wait();task.cancel()
    with pytest.raises(asyncio.CancelledError):await task
    record=(await history(database,'cleartrip'))[0]
    assert record['status']=='interrupted'
    assert record['trials'][0]['status']=='not_tested'
    assert cart.applied=='ORIG'


@pytest.mark.asyncio
async def test_onsite_failure_cannot_claim_complete_coverage(database,fast_coupon_waits):
    result=await CouponBruteForcer(StatefulCart(),FinancialFilter(),lambda *a:None).brute_force(SimpleNamespace(url='https://www.cleartrip.com/booking'),
        [{'code':'BEST'}],{},'audit',db=database,
        audit_scope={'stage':'merchant_payment','onsite_collection':'failed'})
    assert not result['coverage']['complete']
    assert (await history(database,'cleartrip'))[0]['status']=='awaiting_checkout_confirmation'


@pytest.mark.asyncio
async def test_browser_error_is_not_a_rejected_coupon(database,fast_coupon_waits):
    cart=StatefulCart()
    # Start coupon-free: an existing discount must now be restored or fail the
    # whole optimization if trial failures would leave a more expensive cart.
    cart.applied=None;cart.total=6000
    async def broken(page):raise RuntimeError('Browser disconnected')
    cart.click_apply_coupon=broken
    result=await CouponBruteForcer(cart,FinancialFilter(),lambda *a:None).brute_force(SimpleNamespace(url='https://www.cleartrip.com/booking'),
        [{'code':'BEST'}],{},'audit',db=database)
    assert next(t for t in result['all_results'] if t['code']=='BEST')['status']=='error'
    assert not result['coverage']['complete']
    assert next(t for t in (await history(database,'cleartrip'))[0]['trials'] if t['code']=='BEST')['status']=='error'


@pytest.mark.asyncio
async def test_unknown_bank_offer_is_not_tested_without_payment(database,fast_coupon_waits):
    result=await CouponBruteForcer(StatefulCart(),FinancialFilter(),lambda *a:None).brute_force(
        SimpleNamespace(url='https://www.cleartrip.com/booking'),
        [{'code':'BANK','description':'Domestic flights only with HDFC credit cards'},{'code':'ORIG'}],
        {},'audit',db=database)
    assert next(t for t in result['all_results'] if t['code']=='BANK')['status']=='conditional'
    assert result['best_coupon']!='BANK'


@pytest.mark.asyncio
async def test_newly_displayed_bank_terms_cannot_win_at_review(database,fast_coupon_waits):
    cart=StatefulCart()
    async def terms(page):
        return 'Domestic flight discount valid only with HDFC credit cards' if cart.applied=='BEST' else ''
    cart.get_coupon_validation_text=terms
    result=await CouponBruteForcer(cart,FinancialFilter(),lambda *a:None).brute_force(
        SimpleNamespace(url='https://www.cleartrip.com/booking'),
        [{'code':'BEST','description':'Domestic flight discount'},{'code':'ORIG'}],{},'audit',db=database)
    assert result['best_coupon']!='BEST'
    trial=next(t for t in result['all_results'] if t['code']=='BEST')
    assert trial['status']=='conditional' and trial['price']==5000
    assert not result['coverage']['complete']


@pytest.mark.parametrize('terms,status',[
    ('Flight discount only for Doctors and Nurses','unknown'),
    ('Flight offer for Army & Government Personnel','unknown'),
    ('Flight discount for existing users','unknown'),
    ('Flight discount for all new and existing users','eligible'),
    ('One lucky customer gets a chance to win a free flight','ineligible'),
])
def test_no_assumed_profession_account_or_lottery_discount(terms,status):
    assert FinancialFilter().assess({'code':'TEST','description':terms},{}).status==status


@pytest.mark.asyncio
async def test_login_overlay_stops_remaining_trials_and_preserves_failure(database,fast_coupon_waits):
    cart=StatefulCart();cart.applied=None;cart.total=6000
    cart.calls=0
    original=cart.click_apply_coupon
    async def apply(page):
        cart.calls+=1;await original(page)
    async def blocker(page):
        return 'Sign-in required' if cart.calls else None
    cart.click_apply_coupon=apply;cart.coupon_navigation_blocker=blocker
    with pytest.raises(ValueError,match='Sign-in required'):
        await CouponBruteForcer(cart,FinancialFilter(),lambda *a:None).brute_force(
            SimpleNamespace(url='https://www.cleartrip.com/booking'),
            [{'code':'BEST'},{'code':'NEXT'}],{},'audit',db=database)
    run=(await history(database,'cleartrip'))[0]
    assert run['status']=='failed' and cart.calls==1
    assert next(t for t in run['trials'] if t['code']=='NEXT')['status']=='not_tested'
