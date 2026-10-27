"""Adversarial timeline fixtures; never imported as real fare history."""
from datetime import date, timedelta

from intelligence import calibrated_trend


def falling(count, *, end=None, start_price=30000):
    end=end or date.today()
    return [(end-timedelta(days=count-i-1),start_price-i*20) for i in range(count)]


def test_fresh_quote_cannot_reactivate_old_successful_holdouts():
    old=falling(210,end=date.today()-timedelta(days=100))
    report=calibrated_trend(old+[(date.today(),25000)])
    assert report['forecast_7d'] is None
    assert report['certainty']['percent'] is None
    assert report['observed_days']==1
    assert report['historical_observed_days']==211
    assert report['excluded_pre_gap_days']==210
    readiness=report['readiness']
    assert readiness['training_days_remaining']==20
    assert readiness['weekly_outcomes_observed']==0
    assert readiness['minimum_additional_daily_observations_for_forecast']==69
    assert any('older observation days' in reason for reason in readiness['blockers'])


def test_resumed_quotes_cannot_borrow_old_percentage_certainty():
    old=falling(210,end=date.today()-timedelta(days=100))
    recent=falling(70,start_price=25000)
    report=calibrated_trend(old+recent)
    assert report['status']=='LOCAL_HOLDOUT_PASSED'
    assert report['observed_days']==70
    assert report['validation_outcomes']==7
    assert report['certainty']['percent'] is None
    assert report['certainty']['sample_count']==7
    assert report['readiness']['prior_observations_excluded_after_gap']==210


def test_forecast_after_restart_is_independent_of_old_prices():
    recent=falling(70,start_price=25000)
    old=falling(90,end=date.today()-timedelta(days=100))
    changed=[(day,1000 if i%2 else 100000) for i,(day,price) in enumerate(old)]
    a=calibrated_trend(old+recent)
    b=calibrated_trend(changed+recent)
    plain=calibrated_trend(recent)
    for key in ('forecast_7d','model_mae','baseline_mae','validation_outcomes'):
        assert a[key]==b[key]==plain[key]


def test_restart_uses_last_large_gap_and_preserves_input_history():
    oldest=falling(80,end=date.today()-timedelta(days=200))
    middle=falling(80,end=date.today()-timedelta(days=100))
    recent=falling(14,start_price=25000)
    points=oldest+middle+recent
    original=list(points)
    report=calibrated_trend(points)
    assert report['observed_days']==14
    assert report['excluded_pre_gap_days']==160
    assert report['collection_restart_date']==recent[0][0].isoformat()
    assert report['forecast_7d'] is None
    assert points==original


def test_exact_weekly_collection_does_not_restart():
    points=[(date.today()-timedelta(days=(29-i)*7),20000-i*20) for i in range(30)]
    report=calibrated_trend(points)
    assert report['status']=='LOCAL_HOLDOUT_PASSED'
    assert report['validation_outcomes']==9
    assert 'collection_restart_date' not in report


def test_sparse_recent_quotes_do_not_refresh_an_old_accuracy_measurement():
    # Each gap is within a week, but none of the three new dates has its exact
    # seven-day outcome. All completed validation windows are still old.
    old=falling(210,end=date.today()-timedelta(days=18))
    recent=[(date.today()-timedelta(days=offset),25000-offset*20) for offset in (12,6,0)]
    report=calibrated_trend(old+recent)
    assert report['status']=='STALE_VALIDATION_WITHHELD'
    assert report['forecast_7d'] is None
    assert report['certainty']['percent'] is None
    assert report['latest_validation_outcome_date']<=old[-1][0].isoformat()
    assert any('old outcome counts' in reason for reason in report['readiness']['blockers'])
    assert report['readiness']['earliest_forecast_evidence_date']==(date.today()+timedelta(days=1)).isoformat()
    assert report['readiness']['minimum_additional_daily_observations_for_forecast']==1
