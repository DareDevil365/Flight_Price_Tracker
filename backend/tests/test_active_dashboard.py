"""Dashboard cannot borrow legacy research success or accuracy claims."""
import pytest

from learning_engine import SelfLearningEngine
from tests.test_verified_pricing import database


@pytest.mark.asyncio
async def test_empty_active_dashboard_has_no_invented_forecast_accuracy(database):
    await database.db.execute('CREATE TABLE prediction_queries(route TEXT,prediction_error REAL,audited INTEGER)')
    await database.db.execute('INSERT INTO prediction_queries(route,prediction_error,audited) VALUES (?,?,?)',
        ('DEL-BOM',0,1))
    await database.db.commit()
    report=await SelfLearningEngine(database).get_dashboard_data()
    assert report['data_source']=='active_audits'
    assert report['prediction_accuracy']['available'] is False
    assert report['prediction_accuracy']['avg_mape'] is None
    assert report['coupon_stats']['run_count']==0
    assert report['coupon_stats']['trial_count']==0
    assert report['coupon_stats']['avg_success_rate'] is None


@pytest.mark.asyncio
async def test_live_coupon_dashboard_counts_review_only_separately(database):
    from coupon_audit import CouponAudit
    audit=await CouponAudit.start(database,'easemytrip','search',
        {'origin':'DEL','destination':'BOM','departure_date':'2026-11-25','stage':'review'})
    await audit.trial({'code':'REALTEST','status':'valid_match','price':5000,'savings':100})
    await audit.finish('review_only',{'baseline_price':5100,'best_price':5000,'best_coupon':'REALTEST'})
    report=await SelfLearningEngine(database).get_dashboard_data()
    counts=report['coupon_stats']
    assert counts['run_count']==1 and counts['trial_count']==1
    assert counts['review_accepted_trials']==1
    assert counts['checkout_accepted_trials']==0
    assert counts['avg_success_rate'] is None
