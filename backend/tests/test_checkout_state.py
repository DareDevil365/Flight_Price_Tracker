"""Mutable carts must not retain an old successful verification after a failed recheck."""
import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from checkout_state import invalidate_checkout
from search_engine import Dispatcher


def receipt():
    return dict(id='quote', search_id='search', platform='cleartrip', base_price=6000,
        final_price=5500, effective_price=5500, best_coupon_code='OLD', savings=500,
        all_tested_coupons=[dict(code='OLD',status='valid_match')], savings_breakdown=dict(
            verification='checkout', checkout_price=5500, listed_price=6000,
            listed_observed_at='2026-10-09T01:00:00Z', observed_at='2026-10-09T02:00:00Z',
            integrity=dict(status='checkout_verified'), fee_breakdown=[dict(amount=300)],
            selected_payment=dict(method='UPI',banks=[]), cart_options=dict(baggage='none'),
            coupon_coverage=dict(complete=True)))


def test_withdraw_receipt_preserves_record_without_claiming_new_listing():
    row=receipt()
    assert invalidate_checkout(row)
    meta=row['savings_breakdown']
    assert row['final_price']==6000 and row['savings']==0 and row['best_coupon_code'] is None
    assert meta['previous_checkout']['price']==5500 and meta['previous_checkout']['coupon']=='OLD'
    assert meta['previous_checkout']['selected_payment']==dict(method='UPI',banks=[])
    assert meta['observed_at']=='2026-10-09T01:00:00Z'
    assert meta['verification']=='listed' and meta['integrity']['status']=='uncorroborated'
    assert meta['checkout_price'] is None and 'fee_breakdown' not in meta
    assert not invalidate_checkout(row)  # Failure/retry does not overwrite the old receipt.


@pytest.mark.parametrize('listed',[None,False,0,float('nan'),float('inf'),'6000'])
def test_missing_or_invalid_old_listing_cannot_be_invented(listed):
    row=receipt();row['savings_breakdown']['listed_price']=listed
    assert invalidate_checkout(row)
    assert row['savings_breakdown']['verification']=='unverified'
    assert row['savings_breakdown']['integrity']['status']=='flagged'


def engine_for(row, expiry=None):
    events=[]
    worker=SimpleNamespace(is_provider_page=lambda page:False)
    page=SimpleNamespace()
    session=dict(page=page,context=SimpleNamespace(pages=[page]))
    if expiry:session['expires_at']=expiry
    manager=SimpleNamespace(_sessions={'session':session},close_session=AsyncMock())
    db=SimpleNamespace(save_result=AsyncMock(),recalculate_ranks=AsyncMock())
    engine=Dispatcher(db,manager,None,None,None,lambda *args:events.append(args))
    engine._pending_checkouts['session']=dict(worker=worker,task=dict(search_id='search'),quote=row,lock=asyncio.Lock())
    return engine,events,db,manager


@pytest.mark.asyncio
async def test_failed_recheck_durably_withdraws_current_verification():
    row=receipt();engine,events,db,_=engine_for(row)
    with pytest.raises(ValueError,match='outside the expected HTTPS'):
        await engine.verify_checkout('session')
    db.save_result.assert_awaited_once_with(row)
    assert row['savings_breakdown']['verification']=='listed'
    statuses=[p['status'] for kind,p in events if kind=='session:verification']
    assert statuses==['running','failed']
    assert events[0][0]=='search:results'
    assert not engine._pending_checkouts['session']['lock'].locked()


@pytest.mark.asyncio
async def test_duplicate_request_does_not_invalidate_active_cart_or_emit_completion():
    row=receipt();engine,events,db,_=engine_for(row)
    lock=engine._pending_checkouts['session']['lock']
    async with lock:
        with pytest.raises(ValueError,match='already running'):
            await engine.verify_checkout('session')
    assert row['savings_breakdown']['verification']=='checkout' and not events
    db.save_result.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancelled_recheck_reports_failure_and_releases_cart_lock():
    row=receipt();engine,events,_,_=engine_for(row)
    engine._verify_checkout_locked=AsyncMock(side_effect=asyncio.CancelledError)
    with pytest.raises(asyncio.CancelledError):await engine.verify_checkout('session',persist=False)
    assert [p['status'] for k,p in events if k=='session:verification']==['running','failed']
    assert not engine._pending_checkouts['session']['lock'].locked()


@pytest.mark.asyncio
async def test_checkout_deadline_respects_non_utc_offset():
    india=timezone(timedelta(hours=5,minutes=30))
    expiry=(datetime.now(timezone.utc)-timedelta(minutes=5)).astimezone(india)
    engine,_,_,manager=engine_for(receipt(),expiry)
    with pytest.raises(ValueError,match='expired'):await engine.verify_checkout('session')
    manager.close_session.assert_awaited_once_with('session')
